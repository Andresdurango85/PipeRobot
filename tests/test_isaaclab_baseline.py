from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from piperobot.adapters.isaaclab.baseline import (
    GUARDED_KEYS,
    baseline_record,
    main,
    platform_mismatches,
)
from piperobot.results import EpisodeResult, EvalResults, save_results


def metadata() -> dict[str, Any]:
    return {
        "git_commit": "abc",
        "platform_differences": [],
        "platform": {
            **dict.fromkeys(GUARDED_KEYS, "version"),
            "options": {"physics": 1},
            "cpu": "CPU A",
        },
    }


def test_record() -> None:
    result = baseline_record(
        EvalResults("demo", "isaaclab", (EpisodeResult(0, True), EpisodeResult(1, False))),
        metadata(),
        seeds="0-1",
        run_url="https://example.org/run",
    )
    assert result == {
        "policy": "demo",
        "evaluator": "isaaclab",
        "successes": 1,
        "trials": 2,
        "seeds": "0-1",
        "commit": "abc",
        "platform": {key: metadata()["platform"][key] for key in GUARDED_KEYS},
        "updated": datetime.now(UTC).date().isoformat(),
        "how": "Recorded from Isaac Lab evaluation: https://example.org/run",
    }


@pytest.mark.parametrize("change", [{"platform_differences": [{"seed": 1}]}, {"platform": None}])
def test_refuse_record(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="run platform"):
        baseline_record(
            EvalResults("demo", "isaaclab", (EpisodeResult(0, True),)),
            metadata() | change,
            seeds="0",
            run_url=None,
        )


@pytest.mark.parametrize("key", GUARDED_KEYS)
def test_mismatch(key: str) -> None:
    baseline = metadata()
    run = metadata()
    run["platform"][key] = {"changed": True} if key == "options" else "changed"
    lines = platform_mismatches(baseline, run)
    assert len(lines) == 1
    assert lines[0].startswith(f"{key}: baseline ")
    assert ", run " in lines[0]


def test_match_and_cpu_ignored() -> None:
    run = metadata()
    run["platform"]["cpu"] = "CPU B"
    assert platform_mismatches(metadata(), run) == []


def test_missing_or_changing_run() -> None:
    assert platform_mismatches(metadata(), {"platform": None}) == ["run platform is missing"]
    run = metadata() | {"platform_differences": [{"seed": 2}]}
    assert platform_mismatches(metadata(), run) == ["run platform_differences is non-empty"]


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    results, meta, output = (
        tmp_path / name for name in ("results.json", "meta.json", "counts.json")
    )
    save_results(EvalResults("demo", "isaaclab", (EpisodeResult(0, True),)), results)
    meta.write_text(json.dumps(metadata()))
    record = [
        "record",
        "--results",
        str(results),
        "--metadata",
        str(meta),
        "--seeds",
        "0",
        "--output",
        str(output),
    ]
    assert main(record) == 0
    assert output.read_text().endswith("\n")
    check = ["check", "--baseline", str(output), "--metadata", str(meta)]
    assert main(check) == 0
    run = metadata()
    run["platform"]["driver_version"] = "changed"
    meta.write_text(json.dumps(run))
    assert main(check) == 3
    assert "baseline platform mismatch: re-measure the baseline" in capsys.readouterr().err
    meta.write_text("[]")
    assert main(check) == 2
    assert main(record) == 2
    meta.write_text("{")
    assert main(check) == 2
    meta.unlink()
    assert main(record) == 2


def test_import_without_simulator() -> None:
    script = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'torch', 'isaaclab'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import piperobot.adapters.isaaclab.baseline
"""
    result = subprocess.run(  # noqa: S603 -- fixed Python code, no shell.
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
