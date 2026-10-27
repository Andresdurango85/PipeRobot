from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eval.results import (
    EpisodeResult,
    EvalResults,
    ResultsError,
    load_results,
    parse_results,
    save_results,
)


def _data(*episodes: dict[str, Any]) -> dict[str, Any]:
    return {"policy": "p", "evaluator": "mock", "episodes": list(episodes)}


def test_counts_and_failed_episodes() -> None:
    results = parse_results(
        _data(
            {"seed": 0, "success": True},
            {"seed": 1, "success": False, "failure": "timeout", "scene": "dim_light"},
            {"seed": 2, "success": True},
        )
    )

    assert (results.successes, results.trials) == (2, 3)
    assert results.failed == [
        EpisodeResult(seed=1, success=False, scene="dim_light", failure="timeout")
    ]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    results = EvalResults(
        policy="p",
        evaluator="mock",
        episodes=(EpisodeResult(0, True), EpisodeResult(1, False, "rack_left", "tube dropped")),
    )
    path = tmp_path / "nested" / "results.json"

    save_results(results, path)

    assert load_results(path) == results


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_data(), "no episodes"),
        (_data({"seed": 0, "success": True}, {"seed": 0, "success": False}), "duplicate seeds"),
        (_data({"success": True}), "seed"),
        (_data({"seed": 0, "success": "yes"}), "true or false"),
        ({"episodes": "not a list"}, "must be a list"),
    ],
)
def test_invalid_results_are_rejected(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ResultsError, match=message):
        parse_results(data)


def test_unreadable_file_is_a_results_error(tmp_path: Path) -> None:
    bad = tmp_path / "results.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(ResultsError, match="cannot read"):
        load_results(bad)
    with pytest.raises(ResultsError, match="cannot read"):
        load_results(tmp_path / "missing.json")
