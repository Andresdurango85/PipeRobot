from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from piperobot.results import (
    EpisodeResult,
    EvalResults,
    ResultsError,
    load_results,
    parse_results,
    save_results,
)

DEEP = 100_000


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
    # The same bytes on Windows and Linux, so a certificate's sha256 matches on both.
    assert b"\r\n" not in path.read_bytes()
    assert path.read_bytes().endswith(b"}\n")


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


@pytest.mark.parametrize("entry", ["episode", "parse"])
@pytest.mark.parametrize("missing_success", [True, False], ids=["missing-success", "non-bool"])
def test_deep_episode_values_raise_results_error(entry: str, missing_success: bool) -> None:
    nested: list[object] = []
    for _ in range(5000):
        nested = [nested]
    episode = {"seed": 0, "extra": nested} if missing_success else {"seed": 0, "success": nested}
    message = (
        "episode without ['success'] (keys: ['extra', 'seed'])"
        if missing_success
        else "'success' must be true or false, got list"
    )
    action = (
        (lambda: EpisodeResult.from_dict(episode))
        if entry == "episode"
        else (lambda: parse_results(_data(episode)))
    )
    with pytest.raises(ResultsError, match=re.escape(message)):
        action()


def test_unreadable_file_is_a_results_error(tmp_path: Path) -> None:
    bad = tmp_path / "results.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(ResultsError, match="cannot read"):
        load_results(bad)
    with pytest.raises(ResultsError, match="cannot read"):
        load_results(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "payload",
    [b"[" * DEEP + b"]" * DEEP, b'{"episodes":' + b"[" * DEEP + b"]" * DEEP + b"}"],
    ids=["array", "episodes"],
)
def test_untrusted_deep_results(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "results.json"
    path.write_bytes(payload)
    with pytest.raises(ResultsError, match=re.escape(str(path))) as excinfo:
        load_results(path)
    assert isinstance(excinfo.value.__cause__, RecursionError)


def test_untrusted_results_encoding(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_bytes(b"\xff\xfe{")
    with pytest.raises(ResultsError, match=re.escape(str(path))):
        load_results(path)


def test_untrusted_episode_shape(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text('{"episodes": ["x"]}', encoding="utf-8")
    with pytest.raises(ResultsError, match=re.escape(str(path))):
        load_results(path)


@pytest.mark.parametrize("seed", [float("nan"), float("inf"), [], {}, None, "bad"])
@pytest.mark.parametrize("entry", ["load", "parse", "episode"])
def test_untrusted_episode_seed(tmp_path: Path, seed: object, entry: str) -> None:
    import json

    episode = {"seed": seed, "success": True}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_data(episode)), encoding="utf-8")
    actions: dict[str, Callable[[], object]] = {
        "load": lambda: load_results(path),
        "parse": lambda: parse_results(_data(episode)),
        "episode": lambda: EpisodeResult.from_dict(episode),
    }
    with pytest.raises(ResultsError, match=re.escape(str(path)) if entry == "load" else "seed"):
        actions[entry]()
