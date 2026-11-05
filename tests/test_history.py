from __future__ import annotations

import hashlib
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
from test_certificate import REPO, evidence, fake, write_bundle

from piperobot.reports.certificate import CertificateInputError, CertificateMismatch, verify
from piperobot.reports.history import (
    GATE_VERDICT_V2_PREDICATE_TYPE,
    HistoryError,
    HistoryRecord,
    PairedRecord,
    append,
    compress_seeds,
    cpu_flags_digest,
    load_history,
    main,
    paired_record,
    record_from_gate,
    render_html,
    save_history,
)
from piperobot.results import EpisodeResult, EvalResults, load_results, save_results
from piperobot.stats.gate import SuccessCount, decide
from piperobot.stats.paired import PairedCounts, decide_paired


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


@pytest.mark.parametrize("field", list(_record().to_dict()))
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
    assert ".table-wrap,pre{overflow-x:auto}" in page  # tables and verify commands scroll
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


def test_record_cli_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from piperobot.reports.history import GATE_VERDICT_PREDICATE_TYPE

    results, baseline, output, history = (
        tmp_path / name for name in ("results.json", "baseline.json", "record.json", "history.json")
    )
    save_results(EvalResults("p", "e", (EpisodeResult(7, True),)), results)
    baseline.write_text('{"successes": 1, "trials": 1}', encoding="utf-8")
    building = [
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
        "--evaluated-at",
        "2026-11-03T10:01:00Z",
        "--platform",
        "CPU",
    ]
    identity = ["--run-id", "1", "--run-attempt", "2"]
    assert main(["record", "--output", str(output), *building, *identity]) == 0
    record = HistoryRecord.from_dict(json.loads(output.read_text(encoding="utf-8")))
    assert record.schema == 2
    assert record.series == "main"
    assert output.read_bytes().endswith(b"\n")
    assert b"\r\n" not in output.read_bytes()
    assert main(["append", "--history", str(history), "--new", *building, *identity]) == 0
    assert load_history(history) == [replace(record, schema=1)]
    history.unlink()
    args = ["append", "--history", str(history), "--record", str(output), "--new"]
    assert main([*args, *identity]) == 0
    assert load_history(history) == [record]
    for run_id, attempt in ((9, 2), (1, 9)):
        assert main([*args, "--run-id", str(run_id), "--run-attempt", str(attempt)]) == 2
        assert f"record is for run 1.2, this is run {run_id}.{attempt}" in capsys.readouterr().err
    for option, value in [
        ("results", str(results)),
        ("baseline-file", str(baseline)),
        ("commit", "a"),
        ("commit-date", "date"),
        ("run-url", "url"),
        ("platform", "CPU"),
        ("evaluated-at", "date"),
        ("confidence", "0.95"),
        ("tolerance", "0.1"),
    ]:
        with pytest.raises(SystemExit) as error:
            main([*args, *identity, f"--{option}", value])
        assert error.value.code == 2
    for missing in ("--run-id", "--run-attempt"):
        incomplete = identity.copy()
        index = incomplete.index(missing)
        del incomplete[index : index + 2]
        with pytest.raises(SystemExit) as error:
            main([*args, *incomplete])
        assert error.value.code == 2
    for invalid in ("{", "{}", "null"):
        output.write_text(invalid, encoding="utf-8")
        assert main([*args, *identity]) == 2
    capsys.readouterr()
    assert main(["predicate-type"]) == 0
    assert capsys.readouterr().out == GATE_VERDICT_PREDICATE_TYPE + "\n"


def test_certified_golden() -> None:
    records = [_record(1), _record(2)]
    page = render_html(records, evidence=lambda record: record.run_id == 2)
    assert "<th>Certificate</th>" in page
    assert "<td>not signed</td>" in page
    assert '<a href="results/2.1.json">results</a>' in page
    assert '<a href="bundles/2.1.jsonl">bundle</a>' in page
    assert "Verify a point" in page
    assert (
        "python -m piperobot.reports.certificate verify results.json --bundle bundle.jsonl" in page
    )
    from piperobot.reports.certificate import verification_command

    assert html.escape(" ".join(verification_command(Path("results.json")))) in page
    path = Path(__file__).parent / "golden" / "history_certified.html"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(page, encoding="utf-8", newline="\n")
    assert page == path.read_text(encoding="utf-8")
    unsigned = render_html(records, evidence=lambda record: False)
    assert unsigned.count("<td>not signed</td>") == 2
    assert "Verify a point" not in unsigned
    assert "<th>Certificate</th>" not in render_html(records)


def test_render_evidence_directory(tmp_path: Path) -> None:
    history, output = tmp_path / "history.json", tmp_path / "index.html"
    save_history([_record()], history, previous=[])
    args = [
        "render",
        "--history",
        str(history),
        "--output",
        str(output),
        "--evidence-dir",
        str(tmp_path),
    ]
    for directory, suffix in (("results", "json"), ("bundles", "jsonl")):
        assert main(args) == 0
        assert "<td>not signed</td>" in output.read_text(encoding="utf-8")
        folder = tmp_path / directory
        folder.mkdir()
        (folder / f"1.1.{suffix}").write_text("evidence", encoding="utf-8")
    assert main(args) == 0
    assert '<a href="results/1.1.json">results</a>' in output.read_text(encoding="utf-8")


def nightly(index: int = 3) -> HistoryRecord:
    ref = EvalResults("policy", "sim", tuple(EpisodeResult(i, i < 47) for i in range(50)))
    cand = EvalResults("policy", "sim", tuple(EpisodeResult(i, i < 45) for i in range(50)))
    return replace(
        _record(index),
        schema=2,
        series="nightly",
        paired=paired_record(ref, cand, reference_commit="b" * 40),
    )


def test_schema1_bytes(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    fixture = Path("tests/golden/history_schema1.json").read_bytes()
    path.write_bytes(fixture)
    records = load_history(path)
    save_history(records, path, previous=records)
    assert path.read_bytes() == fixture
    assert records[0].series == "main"
    assert records[0].runner_image is None
    assert "runner_image" not in records[0].to_dict()


@pytest.mark.parametrize(
    "record",
    [
        replace(_record(), schema=2),
        nightly(),
        replace(nightly(), runner_image="ubuntu24 20261025.353.1"),
    ],
)
def test_schema2_roundtrip(record: HistoryRecord) -> None:
    assert HistoryRecord.from_dict(record.to_dict()) == record
    for key in record.to_dict():
        data = record.to_dict()
        del data[key]
        with pytest.raises(HistoryError):
            HistoryRecord.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", 3),
        ("schema", True),
        ("series", "other"),
        ("series", "main"),
        ("paired", None),
        ("runner_image", ""),
        ("runner_image", "   "),
        ("runner_image", "a" * 201),
        ("runner_image", "bad\x00image"),
        ("runner_image", "bad\x7fimage"),
        ("runner_image", 42),
        ("runner_image", []),
        ("cpu_flags_sha256", "A" * 64),
        ("cpu_flags_sha256", "a" * 63),
        ("successes", 44),
        ("trials", 51),
        ("unknown", 0),
    ],
)
def test_invalid_schema2(field: str, value: object) -> None:
    data = nightly().to_dict()
    data[field] = value
    with pytest.raises(HistoryError):
        HistoryRecord.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reference_commit", "A" * 40),
        ("reference_commit", "a" * 39),
        ("both", True),
        ("reference_only", -1),
        ("candidate_only", 1.0),
        ("neither", False),
        ("p_value", float("nan")),
        ("p_value", 1.1),
        ("p_value", -0.1),
        ("alpha", 0),
        ("alpha", 0.5),
        ("alpha", float("inf")),
        ("difference_interval", [-2, 0]),
        ("difference_interval", [1, 0]),
        ("difference_interval", [0, float("nan")]),
        ("verdict", "green"),
        ("unknown", 0),
    ],
)
def test_invalid_paired(field: str, value: object) -> None:
    record = nightly().paired
    assert record is not None
    data = record.to_dict()
    data[field] = value
    with pytest.raises(HistoryError):
        PairedRecord.from_dict(data)


def test_paired_and_flags() -> None:
    ref = EvalResults("p", "e", tuple(EpisodeResult(i, True) for i in range(4)))
    cand = EvalResults("p", "e", tuple(EpisodeResult(i, i < 2) for i in range(4)))
    expected = decide_paired(PairedCounts.from_results(ref, cand))
    actual = paired_record(ref, cand, reference_commit="a" * 40)
    assert (actual.p_value, actual.verdict, actual.difference_interval) == (
        expected.p_value,
        expected.verdict,
        expected.difference_interval,
    )
    assert cpu_flags_digest(" \tflags \t: sse   avx\n") == cpu_flags_digest("sse avx")
    assert cpu_flags_digest("sse avx") == hashlib.sha256(b"sse avx").hexdigest()


def test_predicate_and_golden(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(nightly().to_dict()), encoding="utf-8")
    assert main(["predicate-type", "--record", str(path)]) == 0
    assert capsys.readouterr().out.strip() == GATE_VERDICT_V2_PREDICATE_TYPE
    page = render_html(
        [
            _record(),
            replace(_record(2), schema=2, runner_image="ubuntu24 20261025.353.1"),
            nightly(),
            nightly(4),
        ]
    )
    path = Path("tests/golden/history_nightly.html")
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(page, encoding="utf-8", newline="\n")
    assert page == path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "options",
    [
        ["--series", "nightly"],
        ["--cpu-flags", "flags"],
        ["--runner-image", "image"],
        ["--paired-reference", "ref"],
        ["--reference-commit", "a" * 40],
        ["--schema", "2", "--series", "nightly", "--paired-reference", "ref"],
    ],
)
def test_cli_combinations(options: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["record", "--output", "unused", "--run-id", "1", "--run-attempt", "1", *options])
    assert exc.value.code == 2


def v2(path: Path, reference: Path | None = None) -> list[dict[str, Any]]:
    payload = evidence(path)
    verification = payload[0]["verificationResult"]
    statement = verification["statement"]
    record = HistoryRecord.from_dict(statement["predicate"])
    paired = None
    if reference is not None:
        results = load_results(path)
        reference_results = replace(
            results,
            episodes=tuple(
                replace(e, success=True) if e.seed == 49 else e for e in results.episodes
            ),
        )
        save_results(reference_results, reference)
        paired = paired_record(reference_results, results, reference_commit="b" * 40)
        statement["subject"].append(
            {
                "name": "reference",
                "digest": {"sha256": hashlib.sha256(reference.read_bytes()).hexdigest()},
            }
        )
    record = replace(
        record,
        schema=2,
        series="nightly" if reference else "main",
        paired=paired,
        runner_image="ubuntu24 20261025.353.1",
    )
    statement["predicate"] = record.to_dict()
    statement["predicateType"] = GATE_VERDICT_V2_PREDICATE_TYPE
    cert = verification["signature"]["certificate"]
    cert["buildSignerURI"] = (
        f"https://github.com/{REPO}/.github/workflows/certify.yml@refs/heads/main"
    )
    caller = "nightly" if reference else "history"
    cert["buildConfigURI"] = (
        f"https://github.com/{REPO}/.github/workflows/{caller}.yml@refs/heads/main"
    )
    return payload


@pytest.mark.parametrize("series", ["main", "nightly"])
def test_v2_success_and_bundle(tmp_path: Path, series: str) -> None:
    path = tmp_path / "results.json"
    reference = tmp_path / "reference.json" if series == "nightly" else None
    payload = v2(path, reference)
    bundle = tmp_path / "bundle.jsonl"
    write_bundle(bundle, [payload[0]["verificationResult"]["statement"]])
    for source in (None, bundle):
        result = verify(path, reference_path=reference, bundle=source, run=fake(payload))
        assert result.record.series == series
        assert result.record.runner_image == "ubuntu24 20261025.353.1"
        assert f"policy/sim {series} " in str(result)


@pytest.mark.parametrize("series", ["main", "nightly"])
@pytest.mark.parametrize("field", ["buildConfigURI", "buildSignerURI"])
def test_v2_binding(tmp_path: Path, series: str, field: str) -> None:
    path = tmp_path / "results.json"
    ref = tmp_path / "reference.json" if series == "nightly" else None
    payload = v2(path, ref)
    cert = payload[0]["verificationResult"]["signature"]["certificate"]
    caller = "history" if series == "nightly" else "nightly"
    cert[field] = f"https://github.com/{REPO}/.github/workflows/{caller}.yml@refs/heads/main"
    with pytest.raises(CertificateMismatch, match=f"series {series}, caller"):
        verify(path, reference_path=ref, run=fake(payload))


def test_nightly_reference_checks(tmp_path: Path) -> None:
    path, ref = tmp_path / "results.json", tmp_path / "reference.json"
    payload = v2(path, ref)
    with pytest.raises(CertificateInputError, match="a nightly certificate needs --reference"):
        verify(path, run=fake(payload))
    statement = payload[0]["verificationResult"]["statement"]
    statement["subject"].pop()
    with pytest.raises(CertificateMismatch, match="reference sha256"):
        verify(path, reference_path=ref, run=fake(payload))
    payload = v2(path, ref)
    paired = payload[0]["verificationResult"]["statement"]["predicate"]["paired"]
    paired["both"] -= 1
    paired["candidate_only"] += 1
    with pytest.raises(CertificateMismatch, match="paired cells"):
        verify(path, reference_path=ref, run=fake(payload))


@pytest.mark.parametrize("series", ["main", "nightly"])
def test_schema2_record_and_append_cli(
    tmp_path: Path, series: str, capsys: pytest.CaptureFixture[str]
) -> None:
    results = EvalResults("policy", "sim", tuple(EpisodeResult(i, i < 45) for i in range(50)))
    result_path = tmp_path / "results.json"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "record.json"
    flags = tmp_path / "flags.txt"
    image = tmp_path / "image.txt"
    image.write_text("  ubuntu24   20261025.353.1  \nignored second line", encoding="utf-8")
    history = tmp_path / "history.json"
    save_results(results, result_path)
    baseline.write_text(json.dumps({"successes": 45, "trials": 50}), encoding="utf-8")
    flags.write_text("flags : sse  avx", encoding="utf-8")
    args = [
        "record",
        "--output",
        str(output),
        "--results",
        str(result_path),
        "--baseline-file",
        str(baseline),
        "--commit",
        "a" * 40,
        "--commit-date",
        "2026-11-03T10:00:00Z",
        "--run-url",
        "https://github.com/owner/repo/actions/runs/1",
        "--run-id",
        "1",
        "--run-attempt",
        "1",
        "--schema",
        "2",
        "--series",
        series,
        "--cpu-flags",
        str(flags),
        "--runner-image",
        str(image),
    ]
    if series == "nightly":
        args += ["--paired-reference", str(result_path), "--reference-commit", "b" * 40]
    assert main(args) == 0
    record = HistoryRecord.from_dict(json.loads(output.read_text(encoding="utf-8")))
    assert record.series == series
    assert record.runner_image == "ubuntu24 20261025.353.1"
    image.write_text("", encoding="utf-8")
    assert main(args) == 2
    assert "runner_image file is empty" in capsys.readouterr().err
    assert record.cpu_flags_sha256 == cpu_flags_digest("sse avx")
    assert (
        main(
            [
                "append",
                "--record",
                str(output),
                "--history",
                str(history),
                "--run-id",
                "1",
                "--run-attempt",
                "1",
                "--new",
            ]
        )
        == 0
    )
    assert load_history(history) == [record]


@pytest.mark.parametrize(
    "options",
    [
        {"series": "nightly"},
        {"cpu_flags_sha256": "a" * 64},
        {"runner_image": "ubuntu24"},
        {"paired": "invalid"},
    ],
)
def test_record_from_gate_rejects_schema1_options(options: dict[str, Any]) -> None:
    results = EvalResults("policy", "sim", (EpisodeResult(1, True),))
    r = _record()
    with pytest.raises(HistoryError, match="schema 1"):
        record_from_gate(
            results,
            decide(SuccessCount(1, 1), SuccessCount(1, 1)),
            commit=r.commit,
            commit_date=r.commit_date,
            evaluated_at=r.evaluated_at,
            run_url=r.run_url,
            run_id=r.run_id,
            run_attempt=r.run_attempt,
            platform=r.platform,
            **options,
        )


def test_main_requires_null_paired() -> None:
    data = replace(_record(), schema=2).to_dict()
    data["paired"] = {}
    with pytest.raises(HistoryError, match="main requires"):
        HistoryRecord.from_dict(data)


def test_api_fallback_and_bundle_routing(tmp_path: Path) -> None:
    import subprocess

    from piperobot.reports.history import GATE_VERDICT_PREDICATE_TYPE

    path = tmp_path / "results.json"
    payload = evidence(path)
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if len(calls) == 1:
            return subprocess.CompletedProcess([], 1, "", "no attestations found")
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    assert verify(path, run=run).record.schema == 1
    assert [c[c.index("--predicate-type") + 1] for c in calls] == [
        GATE_VERDICT_V2_PREDICATE_TYPE,
        GATE_VERDICT_PREDICATE_TYPE,
    ]
    assert calls[0][calls[0].index("--signer-workflow") + 1].endswith("/certify.yml")
    payload = v2(path)
    bundle = tmp_path / "bundle.jsonl"
    write_bundle(bundle, [payload[0]["verificationResult"]["statement"]])
    calls.clear()

    def bundled(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    assert verify(path, bundle=bundle, run=bundled).record.schema == 2
    assert len(calls) == 1
    assert calls[0][calls[0].index("--predicate-type") + 1] == GATE_VERDICT_V2_PREDICATE_TYPE


def test_runner_image_normalization_and_platform() -> None:
    data = replace(_record(), schema=2).to_dict()
    data["runner_image"] = " \tubuntu24   <image>& \n"
    record = HistoryRecord.from_dict(data)
    assert record.runner_image == "ubuntu24 <image>&"
    assert HistoryRecord.from_dict(record.to_dict()) == record
    assert (
        f"<td>{html.escape(record.platform)} \u00b7 ubuntu24 &lt;image&gt;&amp;</td>"
        in render_html([record])
    )
    data["runner_image"] = "a" * 200
    assert HistoryRecord.from_dict(data).runner_image == "a" * 200


@pytest.mark.parametrize("missing", ["candidate", "reference", "bundle", None])
def test_nightly_evidence(tmp_path: Path, missing: str | None) -> None:
    record = nightly()
    history, output = tmp_path / "history.json", tmp_path / "index.html"
    save_history([record], history, previous=[])
    for label, name in {
        "candidate": "results/3.1.json",
        "reference": "results/3.1.reference.json",
        "bundle": "bundles/3.1.jsonl",
    }.items():
        if label != missing:
            path = tmp_path / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("evidence", encoding="ascii")
    assert (
        main(
            [
                "render",
                "--history",
                str(history),
                "--output",
                str(output),
                "--evidence-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    page = output.read_text(encoding="utf-8")
    if missing is not None:
        assert "<td>not signed</td>" in page
        assert "Verify a point" not in page
    else:
        for label, name in {
            "candidate": "results/3.1.json",
            "reference": "results/3.1.reference.json",
            "bundle": "bundles/3.1.jsonl",
        }.items():
            assert f'<a href="{name}">{label}</a>' in page
        assert "verify candidate.json --reference reference.json --bundle bundle.jsonl" in page


@pytest.mark.parametrize(
    "payload",
    [b"[" * 5000 + b"]" * 5000, b'{"episodes":' + b"[" * 5000 + b"]" * 5000 + b"}"],
    ids=["array", "episodes"],
)
def test_untrusted_deep_json(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    with pytest.raises(HistoryError, match=re.escape(str(path))):
        load_history(path)
