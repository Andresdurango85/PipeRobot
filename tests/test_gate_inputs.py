from __future__ import annotations

import json
from pathlib import Path

import pytest

from stats.baseline import BaselineError, load_baseline
from stats.gate import SuccessCount, main

ROOT = Path(__file__).resolve().parent.parent
# Every committed baseline: the mock's and the real policies'.
COMMITTED_BASELINES = sorted(
    [ROOT / "stats" / "baseline.json", *(ROOT / "stats" / "baselines").glob("*.json")]
)


def _results_file(tmp_path: Path, successes: int, trials: int = 50) -> Path:
    episodes = [{"seed": seed, "success": seed < successes} for seed in range(trials)]
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"policy": "p", "episodes": episodes}), encoding="utf-8")
    return path


def _baseline_file(tmp_path: Path, successes: int, trials: int = 50) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"successes": successes, "trials": trials}), encoding="utf-8")
    return path


def test_real_policy_baselines_are_committed() -> None:
    # Guards the parametrized test below: an empty glob would skip it, not fail it.
    assert len(COMMITTED_BASELINES) >= 2


@pytest.mark.parametrize("path", COMMITTED_BASELINES, ids=lambda p: p.stem)
def test_committed_baseline_loads(path: Path) -> None:
    baseline = load_baseline(path)

    assert isinstance(baseline, SuccessCount)
    assert baseline.trials >= 50  # Phase 0: at least 50 episodes


@pytest.mark.parametrize("content", ['{"trials": 50}', '{"successes": 60, "trials": 50}', "{"])
def test_invalid_baseline_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(BaselineError):
        load_baseline(path)


@pytest.mark.parametrize(("successes", "exit_code"), [(43, 0), (25, 1)])
def test_gate_cli_with_files(tmp_path: Path, successes: int, exit_code: int) -> None:
    results = _results_file(tmp_path, successes)
    baseline = _baseline_file(tmp_path, 43)

    assert main(["--results", str(results), "--baseline-file", str(baseline)]) == exit_code


def test_gate_cli_mixes_counts_and_files(tmp_path: Path) -> None:
    results = _results_file(tmp_path, 43)

    assert main(["--results", str(results), "--baseline", "43/50"]) == 0


def test_gate_cli_returns_2_on_bad_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--candidate", "40/50", "--baseline-file", str(tmp_path / "nope.json")]) == 2
    assert "invalid baseline" in capsys.readouterr().err


def test_candidate_and_results_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--candidate", "40/50", "--results", "r.json", "--baseline", "40/50"])
