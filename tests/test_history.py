from __future__ import annotations

import html
import json
import math
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from piperobot.reports.history import (
    HistoryError,
    HistoryRecord,
    append,
    compress_seeds,
    load_history,
    main,
    record_from_gate,
    render_html,
    save_history,
)
from piperobot.results import EpisodeResult, EvalResults, save_results
from piperobot.stats.gate import SuccessCount, decide


def _record(
    index: int = 1, successes: int = 45, trials: int = 50, baseline_successes: int = 45
) -> HistoryRecord:
    results = EvalResults(
        "policy", "sim", tuple(EpisodeResult(i, i < successes) for i in range(trials))
    )
    return record_from_gate(
        results,
        decide(SuccessCount(successes, trials), SuccessCount(baseline_successes, 50)),
        commit="a" * 40,
        commit_date="2026-11-03T10:00:00Z",
        evaluated_at="2026-11-03T10:01:00Z",
        run_url=f"https://github.com/owner/repo/actions/runs/{index}",
        run_id=index,
        run_attempt=1,
        platform="CPU A",
    )


def test_roundtrip() -> None:
    record = _record()
    assert HistoryRecord.from_dict(record.to_dict()) == record
    assert record.seeds == "0-49"
    assert record.baseline == SuccessCount(45, 50)
    assert record.interval == decide(SuccessCount(45, 50), record.baseline).candidate_interval


@pytest.mark.parametrize("field", list(HistoryRecord.__dataclass_fields__))
def test_all_fields_required_and_typed(field: str) -> None:
    data = _record().to_dict()
    del data[field]
    with pytest.raises(HistoryError, match="fields"):
        HistoryRecord.from_dict(data)
    data[field] = None
    with pytest.raises(HistoryError):
        HistoryRecord.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", True),
        ("schema", 2),
        ("run_id", -1),
        ("run_attempt", 0),
        ("successes", True),
        ("trials", 0),
        ("successes", 51),
        ("confidence", float("nan")),
        ("confidence", 1),
        ("confidence", False),
        ("tolerance", -1),
        ("tolerance", float("inf")),
        ("interval", [1, 0]),
        ("interval", [0, 2]),
        ("interval", [False, 1]),
        ("interval", [0]),
        ("difference_interval", [-2, 0]),
        ("baseline", {"successes": True, "trials": 1}),
        ("baseline", {"successes": 1, "trials": 1, "typo": 1}),
        ("verdict", "green"),
        ("commit_date", "yesterday"),
        ("evaluated_at", "2026-11-03T10:00:00"),
        ("evaluated_at", "2026-11-03T10:00:00+01:00"),
    ],
)
def test_invalid_values(field: str, value: object) -> None:
    data = _record().to_dict()
    data[field] = value
    with pytest.raises(HistoryError):
        HistoryRecord.from_dict(data)


def test_unknown_key() -> None:
    with pytest.raises(HistoryError, match="fields"):
        HistoryRecord.from_dict({**_record().to_dict(), "typo": 1})


@pytest.mark.parametrize(
    ("seeds", "expected"),
    [
        ([], ""),
        ([7], "7"),
        ([3, 2, 1, 2], "1-3"),
        ([0, 1, 2, 3, 4, 7, 9, 10], "0-4,7,9-10"),
        (list(range(1000, 1050)), "1000-1049"),
    ],
)
def test_seeds(seeds: list[int], expected: str) -> None:
    assert compress_seeds(iter(seeds)) == expected


def test_mismatch() -> None:
    record = _record()
    with pytest.raises(HistoryError, match="candidate"):
        record_from_gate(
            EvalResults("p", "e", (EpisodeResult(0, False),)),
            decide(SuccessCount(1, 1), record.baseline),
            **{
                key: record.to_dict()[key]
                for key in (
                    "commit",
                    "commit_date",
                    "evaluated_at",
                    "run_url",
                    "run_id",
                    "run_attempt",
                    "platform",
                )
            },
        )


def test_loading(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    assert load_history(path, allow_missing=True) == []
    with pytest.raises(HistoryError, match=r"history\.json"):
        load_history(path)
    for payload, message in [("{", "history.json"), ("{}", "list"), ("[{}, null]", "record 0")]:
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(HistoryError, match=message):
            load_history(path)
    path.write_text(json.dumps([_record().to_dict(), None]), encoding="utf-8")
    with pytest.raises(HistoryError, match="record 1"):
        load_history(path)


def test_append() -> None:
    first, second = _record(2), _record(1)
    assert append([first], first) == [first]
    assert append([first], second) == [first, second]
    with pytest.raises(HistoryError, match="conflicting"):
        append([first], replace(first, platform="other"))


def test_save(tmp_path: Path) -> None:
    records = [_record(1), _record(2)]
    path = tmp_path / "nested" / "history.json"
    save_history(records, path, previous=records[:1])
    assert path.read_bytes().endswith(b"\n")
    assert b"\r\n" not in path.read_bytes()
    assert load_history(path) == records
    for changed in (
        records[:1],
        list(reversed(records)),
        [replace(records[0], platform="edit"), records[1]],
    ):
        with pytest.raises(HistoryError, match="prefix"):
            save_history(changed, path, previous=records)
        assert load_history(path) == records


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    history, results, baseline = (
        tmp_path / name for name in ("history.json", "results.json", "baseline.json")
    )
    save_results(EvalResults("p", "e", (EpisodeResult(1, True),)), results)
    baseline.write_text('{"successes": 1, "trials": 1}', encoding="utf-8")
    args = [
        "append",
        "--history",
        str(history),
        "--results",
        str(results),
        "--baseline-file",
        str(baseline),
        "--commit",
        "a" * 40,
        "--commit-date",
        "2026-11-03T10:00:00Z",
        "--run-url",
        "https://example.org/run",
        "--run-id",
        "1",
        "--run-attempt",
        "1",
        "--evaluated-at",
        "2026-11-03T10:01:00Z",
        "--platform",
        "CPU",
    ]
    assert main(args) == 2
    assert capsys.readouterr().err.startswith("ERROR:")
    assert main([*args, "--new"]) == 0
    assert capsys.readouterr().out == "appended\n"
    assert main(args) == 0
    assert capsys.readouterr().out == "already present\n"
    assert len(load_history(history)) == 1
    output = tmp_path / "page.html"
    assert main(["render", "--history", str(history), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == render_html(load_history(history))
    for extra in (["--confidence", "nan"], ["--tolerance", "-1"], ["--commit-date", "bad"]):
        assert main([*args, *extra]) == 2
        assert capsys.readouterr().err.startswith("ERROR:")
    results.write_text("{", encoding="utf-8")
    assert main(args) == 2
    results.write_text('{"episodes": []}', encoding="utf-8")
    assert main(args) == 2
    assert main(["render", "--history", str(results), "--output", str(output)]) == 2


@given(st.lists(st.integers(min_value=0, max_value=10000), unique=True, max_size=20))
def test_prefix_property(ids: list[int]) -> None:
    history: list[HistoryRecord] = []
    earlier: list[list[HistoryRecord]] = [[]]
    for index in ids:
        history = append(history, _record(index))
        assert all(history[: len(old)] == old for old in earlier)
        earlier.append(history)


@given(st.integers(min_value=0, max_value=10000))
def test_idempotence(index: int) -> None:
    record = _record(index)
    assert append(append([], record), record) == append([], record)


@given(st.text())
def test_html_escaping(text: str) -> None:
    record = replace(_record(), policy=text, evaluator=text, platform=text, commit=text)
    page = render_html([record])
    assert "<script" not in page.lower()
    if any(char in text for char in '<>&"'):
        # Check the actual field boundaries: raw substrings can also be HTML syntax
        # (e.g. '<') or part of an entity ('&').
        escaped = html.escape(text, quote=True)
        assert f"<h2>{escaped} / {escaped}</h2>" in page
        assert f"<h2>{text} / {text}</h2>" not in page
        assert f"</svg> {escaped}</li>" in page
        assert f"<td>{html.escape(text[:7], quote=True)}</td>" in page


@given(st.integers(min_value=1, max_value=100000), st.integers(min_value=0, max_value=100000))
def test_svg_finite(trials: int, numerator: int) -> None:
    count = SuccessCount(numerator % (trials + 1), trials)
    result = decide(count, SuccessCount(45, 50))
    record = replace(
        _record(),
        successes=count.successes,
        trials=count.trials,
        interval=result.candidate_interval,
    )
    page = render_html([record])
    for svg in re.findall(r"<svg\b.*?</svg>", page, re.S):
        for attribute in re.findall(
            r'\s(?:x\d?|y\d?|cx|cy|r|width|height|points|viewBox)="([^"]*)"', svg
        ):
            assert all(math.isfinite(float(number)) for number in re.split(r"[ ,]+", attribute))


def test_links_and_empty() -> None:
    assert "No evaluations yet" in render_html([])
    page = render_html([replace(_record(), run_url='javascript:<script>"')])
    assert "href=" not in page
    assert "<td>#1.1</td>" in page  # the run label, as plain text
    assert "javascript:" not in page
    assert "/commit/" in render_html([_record()])


def test_golden() -> None:
    records = [
        replace(
            _record(i + 1, successes, baseline_successes=40 if i > 1 else 45),
            platform="CPU A" if i % 2 == 0 else "CPU B",
            policy="policy" if i < 4 else "second policy",
            commit_date=f"2026-11-{i + 3:02}T10:00:00Z",
        )
        for i, successes in enumerate((45, 38, 25, 45, 38, 25))
    ]
    page = render_html(records)
    path = Path(__file__).parent / "golden" / "history.html"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(page, encoding="utf-8", newline="\n")
    assert page == path.read_text(encoding="utf-8")
    assert page.count("<section>") == 2
    assert page.count("<table>") == 2


def test_golden_single() -> None:
    baseline = SuccessCount(265, 500)
    result = decide(SuccessCount(29, 50), baseline)
    record = replace(
        _record(successes=29),
        baseline=baseline,
        difference_interval=result.difference_interval,
        verdict=result.verdict,
        platform="AMD EPYC 7763 64-Core Processor, 4 CPUs",
    )
    page = render_html([record])
    path = Path(__file__).parent / "golden" / "history_single.html"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(page, encoding="utf-8", newline="\n")
    assert page == path.read_text(encoding="utf-8")


def test_golden_long_platform() -> None:
    records = [
        replace(
            _record(i + 1, successes, baseline_successes=40 if i == 2 else 45),
            platform=(
                f"AMD EPYC 7763 64-Core Processor, 4 CPUs, Linux x86_64, "
                f"self-hosted GPU runner {i + 1}, RTX 4090"
                if i < 2
                else "CPU A"
            ),
            commit_date=f"2026-11-{i + 3:02}T10:00:00Z",
        )
        for i, successes in enumerate((45, 38, 25))
    ]
    page = render_html(records)
    path = Path(__file__).parent / "golden" / "history_long_platform.html"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(page, encoding="utf-8", newline="\n")
    assert page == path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("baselines", "expected"),
    [
        ([45], [(60, 62), (660, 62)]),
        (
            [45, 40, 40, 35],
            [(60, 62), (260, 62), (260, 84), (660, 84), (660, 106), (660, 106)],
        ),
    ],
)
def test_baseline_spans_plot(baselines: list[int], expected: list[tuple[int, int]]) -> None:
    page = render_html([_record(i + 1, baseline_successes=b) for i, b in enumerate(baselines)])
    match = re.search(r'<polyline points="([^"]+)" class="baseline" />', page)
    assert match is not None
    vertices = [tuple(map(float, point.split(","))) for point in match[1].split()]
    assert len(vertices) >= 2
    assert vertices == expected
    assert vertices[0][0] == 60
    assert vertices[-1][0] == 660
    assert page.index("<polyline") < page.index("<g class=")
    assert "stroke-dasharray:6 4" in page


def test_tables_have_scroll_wrappers() -> None:
    page = render_html([_record(), replace(_record(2), policy="second policy")])
    wrapped = re.findall(r'<div class="table-wrap">\s*<table>.*?</table></div>', page, re.S)
    assert len(wrapped) == page.count("<table>") == 2
    assert ".table-wrap{overflow-x:auto}" in page
    assert "white-space:nowrap" in page


def test_cli_defaults_are_idempotent(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    results = tmp_path / "results.json"
    baseline = tmp_path / "baseline.json"
    save_results(EvalResults("p", "e", (EpisodeResult(7, True),)), results)
    baseline.write_text('{"successes": 1, "trials": 1}', encoding="utf-8")
    args = [
        "append",
        "--history",
        str(history),
        "--results",
        str(results),
        "--baseline-file",
        str(baseline),
        "--commit",
        "a" * 40,
        "--commit-date",
        "2026-11-03T10:00:00Z",
        "--run-url",
        "https://example.org/run",
        "--run-id",
        "1",
        "--run-attempt",
        "1",
        "--new",
    ]
    assert main(args) == 0
    original = history.read_bytes()
    assert main(args) == 0
    assert history.read_bytes() == original
    record = load_history(history)[0]
    assert record.evaluated_at.endswith("Z")
    assert record.platform.endswith(" CPUs")
    baseline.write_text("[]", encoding="utf-8")
    assert main(args) == 2


@pytest.mark.parametrize("value", [None, [], 1, "record"])
def test_non_object_record(value: Any) -> None:  # noqa: ANN401
    with pytest.raises(HistoryError, match="fields"):
        HistoryRecord.from_dict(value)
