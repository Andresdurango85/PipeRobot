from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from piperobot.results import EpisodeResult, EvalResults, ResultsError, save_results
from piperobot.stats.repeatability import Verdict, check_repeatability, format_result, main


def run(*, final: bool = True, initial: bool = True) -> EvalResults:
    return EvalResults(
        "p",
        "e",
        tuple(
            EpisodeResult(
                i,
                True,
                final_state_sha256=f"{i:064x}" if final else None,
                initial_state_sha256=f"{i:064x}" if initial else None,
            )
            for i in range(12)
        ),
    )


@pytest.mark.parametrize(
    ("final", "verdict", "gate", "code"),
    [
        (True, Verdict.REPEATABLE, "paired", 0),
        (False, Verdict.UNVERIFIED, None, 3),
    ],
)
def test_matching(
    final: bool,
    verdict: Verdict,
    gate: str | None,
    code: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = run(final=final)
    report = check_repeatability(results, replace(results, episodes=results.episodes[::-1]))
    assert report.verdict is verdict
    assert report.gate == gate
    assert report.seeds == report.matching_outcomes == report.matching_initial_digests == 12
    assert report.matching_final_digests == (12 if final else None)
    assert report.mismatched_seeds == []
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_results(results, a)
    save_results(results, b)
    assert main(["--first", str(a), "--second", str(b), "--json"]) == code
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {
        "verdict",
        "gate",
        "seeds",
        "matching_outcomes",
        "matching_final_digests",
        "matching_initial_digests",
        "mismatched_seeds",
        "reason",
    }
    assert data["verdict"] == verdict.value
    assert data["gate"] == gate
    assert report.reason in format_result(report)
    if not final:
        assert "not provided" in format_result(report)


@pytest.mark.parametrize("field", ["success", "final_state_sha256", "initial_state_sha256"])
def test_mismatches(field: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = run()
    episodes = tuple(
        replace(e, success=False)
        if field == "success"
        else replace(e, final_state_sha256="f" * 64)
        if field == "final_state_sha256"
        else replace(e, initial_state_sha256=f"{e.seed + 100:064x}")
        for e in first.episodes
    )
    second = replace(first, episodes=episodes)
    report = check_repeatability(first, second)
    assert report.verdict is Verdict.NOT_REPEATABLE
    assert report.gate == "unpaired"
    assert report.mismatched_seeds == list(range(10))
    assert report.matching_outcomes == (0 if field == "success" else 12)
    assert report.matching_final_digests == (0 if field == "final_state_sha256" else 12)
    assert report.matching_initial_digests == (0 if field == "initial_state_sha256" else 12)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_results(first, a)
    save_results(second, b)
    assert main(["--first", str(a), "--second", str(b)]) == 1
    assert "NOT_REPEATABLE" in capsys.readouterr().out


def test_outcome_without_digests() -> None:
    first = run(final=False, initial=False)
    second = replace(first, episodes=tuple(replace(e, success=False) for e in first.episodes))
    assert check_repeatability(first, second).verdict is Verdict.NOT_REPEATABLE
    assert check_repeatability(first, first).matching_initial_digests is None


@pytest.mark.parametrize(
    ("second", "message"),
    [
        (replace(run(), policy="other"), "policy"),
        (replace(run(), episodes=run().episodes[1:]), "seed sets differ"),
        (run(final=False), "final_state_sha256"),
        (run(initial=False), "initial_state_sha256"),
    ],
)
def test_errors(
    second: EvalResults, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ResultsError, match=message):
        check_repeatability(run(), second)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_results(run(), a)
    save_results(second, b)
    assert main(["--first", str(a), "--second", str(b)]) == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["--bad"], ["--first", "missing", "--second", "missing"]])
def test_bad_arguments(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(args) == 2
    assert "ERROR:" in capsys.readouterr().err
