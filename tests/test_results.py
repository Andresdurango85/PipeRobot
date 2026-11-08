from __future__ import annotations

import json
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
        episodes=(
            EpisodeResult(0, True),
            EpisodeResult(1, False, "rack_left", "tube dropped"),
            EpisodeResult(2**100, True),
        ),
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


@pytest.mark.parametrize(
    ("value", "type_name"),
    [
        (3.7, "float"),
        (3.0, "float"),
        (True, "bool"),
        ("42", "str"),
        (None, "NoneType"),
        ([], "list"),
    ],
)
@pytest.mark.parametrize("entry", ["load", "parse", "episode"])
def test_non_integer_episode_seed(
    tmp_path: Path, value: object, type_name: str, entry: str
) -> None:
    episode = {"seed": value, "success": True}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_data(episode)), encoding="utf-8")
    actions: dict[str, Callable[[], object]] = {
        "load": lambda: load_results(path),
        "parse": lambda: parse_results(_data(episode)),
        "episode": lambda: EpisodeResult.from_dict(episode),
    }
    with pytest.raises(
        ResultsError, match=re.escape(f"'seed' must be an integer, got {type_name}")
    ):
        actions[entry]()


@pytest.mark.parametrize(
    ("value", "type_name"), [(b"42", "bytes"), (bytearray(b"42"), "bytearray")]
)
@pytest.mark.parametrize("entry", ["parse", "episode"])
def test_bytes_episode_seed(value: bytes | bytearray, type_name: str, entry: str) -> None:
    episode = {"seed": value, "success": True}
    actions: dict[str, Callable[[], object]] = {
        "parse": lambda: parse_results(_data(episode)),
        "episode": lambda: EpisodeResult.from_dict(episode),
    }
    with pytest.raises(
        ResultsError, match=re.escape(f"'seed' must be an integer, got {type_name}")
    ):
        actions[entry]()


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


@pytest.mark.parametrize("field", ["initial_state_sha256", "final_state_sha256"])
@pytest.mark.parametrize("value", [None, True, 1, [], {}, "A" * 64, "a" * 63, "a" * 65, "g" * 64])
def test_invalid_digest(field: str, value: object) -> None:
    with pytest.raises(ResultsError, match=field):
        EpisodeResult.from_dict({"seed": 0, "success": True, field: value})


@pytest.mark.parametrize(
    "value", [None, True, "1", [], {}, float("nan"), float("inf"), -float("inf"), 10**400]
)
def test_invalid_metric(value: object) -> None:
    with pytest.raises(ResultsError, match="metric"):
        EpisodeResult.from_dict({"seed": 0, "success": True, "metric": value})


@pytest.mark.parametrize("value", [0, -2, 1.5])
def test_metric_stored_as_float(value: int | float) -> None:
    episode = EpisodeResult.from_dict({"seed": 0, "success": True, "metric": value})
    assert type(episode.metric) is float
    assert episode.metric == value


@pytest.mark.parametrize("field", ["metric", "initial_state_sha256", "final_state_sha256"])
def test_optional_all_or_none_direct(field: str) -> None:
    fields: dict[str, Any] = {field: 1.0 if field == "metric" else "a" * 64}
    with pytest.raises(ResultsError, match=field):
        EvalResults("p", "e", (EpisodeResult(0, True), EpisodeResult(1, True, **fields)))


def _spec() -> dict[str, Any]:
    return {"name": "distance", "unit": "m", "threshold": 0.02, "success_when": "below"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", 2),
        ("unit", None),
        ("success_when", "equal"),
        ("success_when", {}),
        ("threshold", True),
        ("threshold", 10**400),
        ("threshold", float("nan")),
        ("threshold", float("inf")),
    ],
)
def test_invalid_metric_spec_fields(field: str, value: object) -> None:
    spec = _spec()
    spec[field] = value
    with pytest.raises(ResultsError):
        parse_results({**_data({"seed": 0, "success": True, "metric": 1}), "metric_spec": spec})


@pytest.mark.parametrize(
    "spec",
    [
        None,
        [],
        {},
        {**_spec(), "extra": 1},
        *[{k: v for k, v in _spec().items() if k != missing} for missing in _spec()],
    ],
)
def test_invalid_metric_spec_shape(spec: object) -> None:
    with pytest.raises(ResultsError):
        parse_results({**_data({"seed": 0, "success": True, "metric": 1}), "metric_spec": spec})


def test_spec_needs_metric() -> None:
    with pytest.raises(ResultsError, match="metric_spec"):
        parse_results({**_data({"seed": 0, "success": True}), "metric_spec": _spec()})


def test_seed_variation() -> None:
    with pytest.raises(ResultsError, match=r"seeds do not vary the scene.*2.*9.*aaaaaaaaaaaa"):
        EvalResults(
            "p",
            "e",
            (
                EpisodeResult(2, True, initial_state_sha256="a" * 64),
                EpisodeResult(9, False, initial_state_sha256="a" * 64),
            ),
        )


@pytest.mark.parametrize("direction", ["below", "above"])
def test_new_fields_roundtrip(tmp_path: Path, direction: str) -> None:
    spec = {**_spec(), "unit": "", "success_when": direction}
    results = parse_results(
        {
            **_data(
                {
                    "seed": 0,
                    "success": False,
                    "metric": 0.01,
                    "initial_state_sha256": "a" * 64,
                    "final_state_sha256": "b" * 64,
                }
            ),
            "metric_spec": spec,
        }
    )
    path = tmp_path / "results.json"
    save_results(results, path)
    assert load_results(path) == results
    assert results.to_dict()["metric_spec"] == spec


def test_legacy_bytes(tmp_path: Path) -> None:
    data = _data({"seed": 0, "success": True})
    path = tmp_path / "results.json"
    save_results(parse_results(data), path)
    assert path.read_bytes() == (json.dumps(data, indent=2) + "\n").encode()


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1" + "0" * 400])
@pytest.mark.parametrize("field", ["metric", "threshold"])
def test_nonfinite_json_numbers(tmp_path: Path, literal: str, field: str) -> None:
    text = '{"episodes": [{"seed": 0, "success": true, "metric": ' + literal + "}]}"
    if field == "threshold":
        text = (
            '{"episodes": [{"seed": 0, "success": true, "metric": 1}], '
            '"metric_spec": {"name": "x", "unit": "", "success_when": "above", '
            '"threshold": ' + literal + "}}"
        )
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ResultsError, match=field):
        load_results(path)
