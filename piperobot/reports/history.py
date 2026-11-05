"""Append-only evaluation history and a standalone HTML trend report.

Schema 1 stores commit/run provenance, policy/evaluator, candidate counts and Wilson
interval, baseline counts, difference interval, confidence, tolerance, verdict,
compressed seeds and platform. JSON is a list of these records in insertion order.

Usage:
    python -m piperobot.reports.history append --history history.json --results results.json \
        --baseline-file baseline.json --commit SHA --commit-date ISO --run-url URL \
        --run-id 1 --run-attempt 1 --new
    python -m piperobot.reports.history render --history history.json --output history.html

Exit codes: 0 success, 2 invalid inputs. --new permits bootstrap/local creation only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from piperobot.platform_info import describe_platform
from piperobot.results import EvalResults, load_results
from piperobot.stats.baseline import load_baseline
from piperobot.stats.gate import (
    DEFAULT_CONFIDENCE,
    DEFAULT_TOLERANCE,
    GateResult,
    Interval,
    SuccessCount,
    Verdict,
    decide,
    format_percent,
)
from piperobot.stats.paired import PairedCounts, decide_paired

# Every certificate ever issued carries this exact string; never change it, make a v2 instead.
GATE_VERDICT_PREDICATE_TYPE = (
    "https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v1.md"
)


# Every certificate ever issued carries this exact string; never change it, make a new version.
GATE_VERDICT_V2_PREDICATE_TYPE = (
    "https://github.com/Andresdurango85/PipeRobot/blob/main/docs/attestations/gate-verdict-v2.md"
)


class HistoryError(ValueError):
    """History is invalid or an append would rewrite existing records."""


@dataclass(frozen=True)
class PairedRecord:
    reference_commit: str
    both: int
    reference_only: int
    candidate_only: int
    neither: int
    p_value: float
    alpha: float
    difference_interval: Interval
    verdict: Verdict

    def to_dict(self) -> dict[str, Any]:
        data = dict(vars(self))
        data["difference_interval"] = [
            self.difference_interval.lower,
            self.difference_interval.upper,
        ]
        data["verdict"] = self.verdict.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PairedRecord:
        if not isinstance(data, Mapping) or set(data) != set(cls.__dataclass_fields__):
            raise HistoryError("paired must have exactly the paired fields")
        values = dict(data)
        if (
            not isinstance(values["reference_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", values["reference_commit"]) is None
        ):
            raise HistoryError("reference_commit must be 40 lowercase hex characters")
        for name in ("both", "reference_only", "candidate_only", "neither"):
            if type(values[name]) is not int or values[name] < 0:
                raise HistoryError(f"{name} must be a nonnegative int")
        for name in ("p_value", "alpha"):
            if type(values[name]) not in (int, float) or not math.isfinite(values[name]):
                raise HistoryError(f"{name} must be finite numeric")
        if not 0 <= values["p_value"] <= 1 or not 0 < values["alpha"] < 0.5:
            raise HistoryError("invalid p_value or alpha")
        pair = values["difference_interval"]
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in pair)
            or not -1 <= pair[0] <= pair[1] <= 1
        ):
            raise HistoryError("difference_interval must be an ordered finite pair in [-1, 1]")
        values["difference_interval"] = Interval(*pair)
        if not isinstance(values["verdict"], str):
            raise HistoryError("paired verdict must be a string")
        try:
            values["verdict"] = Verdict(values["verdict"])
        except (TypeError, ValueError) as exc:
            raise HistoryError("invalid paired verdict") from exc
        return cls(**values)


def paired_record(
    reference: EvalResults,
    candidate: EvalResults,
    *,
    reference_commit: str,
    alpha: float = 0.025,
    tolerance: float = DEFAULT_TOLERANCE,
) -> PairedRecord:
    result = decide_paired(PairedCounts.from_results(reference, candidate), alpha, tolerance)
    return PairedRecord.from_dict(
        PairedRecord(
            reference_commit,
            **vars(result.counts),
            p_value=result.p_value,
            alpha=result.alpha,
            difference_interval=result.difference_interval,
            verdict=result.verdict,
        ).to_dict()
    )


def cpu_flags_digest(text: str) -> str:
    """Hash UTF-8 flags after dropping a leading ``flags :`` prefix and collapsing
    all whitespace runs to single spaces, with surrounding whitespace stripped.
    This normalization is part of the record's meaning; flag order is preserved.
    """
    text = re.sub(r"^\s*flags\s*:", "", text)
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def predicate_type_for(record: HistoryRecord) -> str:
    if record.schema == 1:
        return GATE_VERDICT_PREDICATE_TYPE
    if record.schema == 2:
        return GATE_VERDICT_V2_PREDICATE_TYPE
    raise HistoryError("schema must be 1 or 2")


@dataclass(frozen=True)
class HistoryRecord:
    schema: int
    commit: str
    commit_date: str
    evaluated_at: str
    run_url: str
    run_id: int
    run_attempt: int
    policy: str
    evaluator: str
    successes: int
    trials: int
    confidence: float
    interval: Interval
    baseline: SuccessCount
    difference_interval: Interval
    tolerance: float
    verdict: Verdict
    seeds: str
    platform: str
    series: str = "main"
    paired: PairedRecord | None = None
    cpu_flags_sha256: str | None = None
    runner_image: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = dict(vars(self))
        if self.schema == 1:
            for name in ("series", "paired", "cpu_flags_sha256", "runner_image"):
                del data[name]
        else:
            data["paired"] = self.paired.to_dict() if self.paired is not None else None
        data["interval"] = [self.interval.lower, self.interval.upper]
        data["difference_interval"] = [
            self.difference_interval.lower,
            self.difference_interval.upper,
        ]
        data["baseline"] = dict(vars(self.baseline))
        data["verdict"] = self.verdict.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HistoryRecord:
        extra = {"series", "paired", "cpu_flags_sha256", "runner_image"}
        if not isinstance(data, Mapping):
            raise HistoryError("record must have exactly the schema fields")
        schema = data.get("schema")
        expected = set(cls.__dataclass_fields__) - (extra if schema == 1 else set())
        if type(schema) is not int or schema not in (1, 2) or set(data) != expected:
            raise HistoryError("record must have exactly the schema 1 or 2 fields")
        values = dict(data)
        for name in ("schema", "run_id", "run_attempt", "successes", "trials"):
            if type(values[name]) is not int:
                raise HistoryError(f"{name} must be an int")
        if schema == 2:
            if values["series"] not in ("main", "nightly"):
                raise HistoryError("series must be main or nightly")
            paired = values["paired"]
            if values["series"] == "main":
                if paired is not None:
                    raise HistoryError("main requires paired null")
            else:
                paired = PairedRecord.from_dict(paired)
                if (
                    sum(
                        getattr(paired, n)
                        for n in ("both", "reference_only", "candidate_only", "neither")
                    )
                    != values["trials"]
                    or paired.both + paired.candidate_only != values["successes"]
                ):
                    raise HistoryError("paired cells disagree with trials/successes")
                values["paired"] = paired
            digest = values["cpu_flags_sha256"]
            if digest is not None and (
                not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise HistoryError("cpu_flags_sha256 must be null or 64 lowercase hex")
            image = values["runner_image"]
            if image is not None:
                if not isinstance(image, str):
                    raise HistoryError("runner_image must be a string or null")
                image = " ".join(image.split())
                if not image or len(image) > 200 or not image.isprintable():
                    raise HistoryError("runner_image must be 1-200 printable characters or null")
                values["runner_image"] = image
        if values["run_id"] < 0 or values["run_attempt"] < 1:
            raise HistoryError("run_id must be nonnegative and run_attempt positive")
        for name in (
            "commit",
            "commit_date",
            "evaluated_at",
            "run_url",
            "policy",
            "evaluator",
            "seeds",
            "platform",
            "verdict",
        ):
            if not isinstance(values[name], str):
                raise HistoryError(f"{name} must be a string")
        for name in ("commit_date", "evaluated_at"):
            try:
                date = datetime.fromisoformat(values[name])
                offset = date.utcoffset()
                if "T" not in values[name] or offset is None or offset.total_seconds() != 0:
                    raise ValueError("expected UTC timestamp")
            except ValueError as exc:
                raise HistoryError(f"{name} must be ISO 8601 UTC") from exc
        for name in ("confidence", "tolerance"):
            value = values[name]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise HistoryError(f"{name} must be finite numeric")
        if not 0 < values["confidence"] < 1 or values["tolerance"] < 0:
            raise HistoryError("confidence must be in (0, 1); tolerance must be nonnegative")
        for name, low, high in (("interval", 0, 1), ("difference_interval", -1, 1)):
            pair = values[name]
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in pair)
                or not low <= pair[0] <= pair[1] <= high
            ):
                raise HistoryError(f"{name} must be an ordered finite pair in [{low}, {high}]")
            values[name] = Interval(*pair)
        try:
            SuccessCount(values["successes"], values["trials"])
            baseline = values["baseline"]
            if not isinstance(baseline, dict) or set(baseline) != {"successes", "trials"}:
                raise ValueError("baseline must contain successes and trials")
            for name in ("successes", "trials"):
                if type(baseline[name]) is not int:
                    raise HistoryError(f"baseline {name} must be an int")
            values["baseline"] = SuccessCount(**baseline)
            values["verdict"] = Verdict(values["verdict"])
        except (TypeError, ValueError) as exc:
            raise HistoryError(str(exc)) from exc
        return cls(**values)


def compress_seeds(seeds: Iterable[int]) -> str:
    items = list(seeds)
    if any(type(seed) is not int for seed in items):
        raise HistoryError("seeds must be ints")
    ordered = sorted(set(items))
    ranges: list[str] = []
    index = 0
    while index < len(ordered):
        start = end = ordered[index]
        index += 1
        while index < len(ordered) and ordered[index] == end + 1:
            end = ordered[index]
            index += 1
        ranges.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(ranges)


def record_from_gate(
    results: EvalResults,
    result: GateResult,
    *,
    commit: str,
    commit_date: str,
    evaluated_at: str,
    run_url: str,
    run_id: int,
    run_attempt: int,
    platform: str,
    schema: int = 1,
    series: str = "main",
    paired: PairedRecord | None = None,
    cpu_flags_sha256: str | None = None,
    runner_image: str | None = None,
) -> HistoryRecord:
    if schema == 1 and (
        series != "main"
        or paired is not None
        or cpu_flags_sha256 is not None
        or runner_image is not None
    ):
        raise HistoryError(
            "schema 1 only allows default series, paired, cpu flags and runner image"
        )
    if result.candidate != SuccessCount(results.successes, results.trials):
        raise HistoryError("candidate does not match results successes/trials")
    record = HistoryRecord(
        schema,
        commit,
        commit_date,
        evaluated_at,
        run_url,
        run_id,
        run_attempt,
        results.policy,
        results.evaluator,
        result.candidate.successes,
        result.candidate.trials,
        result.confidence,
        result.candidate_interval,
        result.baseline,
        result.difference_interval,
        result.tolerance,
        result.verdict,
        compress_seeds(e.seed for e in results.episodes),
        platform,
        series,
        paired,
        cpu_flags_sha256,
        runner_image,
    )
    return HistoryRecord.from_dict(record.to_dict())


def load_history(path: Path, *, allow_missing: bool = False) -> list[HistoryRecord]:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if allow_missing:
            return []
        raise HistoryError(f"{path}: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise HistoryError(f"{path}: {exc}") from exc
    try:
        data = json.loads(contents)
    except (ValueError, RecursionError) as exc:
        raise HistoryError(f"{path}: {exc}") from exc
    if not isinstance(data, list):
        raise HistoryError(f"{path}: expected a JSON list")
    records = []
    for index, item in enumerate(data):
        try:
            records.append(HistoryRecord.from_dict(item))
        except HistoryError as exc:
            raise HistoryError(f"{path}: record {index}: {exc}") from exc
    return records


def append(history: Sequence[HistoryRecord], record: HistoryRecord) -> list[HistoryRecord]:
    for existing in history:
        if (existing.run_id, existing.run_attempt) == (record.run_id, record.run_attempt):
            if existing != record:
                raise HistoryError("conflicting record for run_id/run_attempt")
            return list(history)
    return [*history, record]


def save_history(
    history: Sequence[HistoryRecord], path: Path, *, previous: Sequence[HistoryRecord]
) -> None:
    if list(history[: len(previous)]) != list(previous):
        raise HistoryError("previous history must be an exact prefix")
    payload = json.dumps([r.to_dict() for r in history], indent=2) + "\n"
    _save_json(payload, path)


def _save_json(payload: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _link(url: str, label: str) -> str:
    escaped = _escape(label)
    return f'<a href="{_escape(url)}">{escaped}</a>' if url.startswith("https://") else escaped


def _commit_link(record: HistoryRecord) -> str:
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_-][A-Za-z0-9_.-]*)/actions/runs/[0-9]+",
        record.run_url,
    )
    if match and re.fullmatch(r"[0-9a-fA-F]{40}", record.commit):
        return _link(
            f"https://github.com/{match[1]}/{match[2]}/commit/{record.commit}", record.commit[:7]
        )
    return _escape(record.commit[:7])


def _marker(x: float, y: float, shape: int) -> str:
    match shape % 4:
        case 0:
            return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" />'
        case 1:
            return f'<rect x="{x - 5:.2f}" y="{y - 5:.2f}" width="10" height="10" />'
        case 2:
            points = f"{x:.2f},{y - 6:.2f} {x - 6:.2f},{y + 5:.2f} {x + 6:.2f},{y + 5:.2f}"
        case _:
            points = (
                f"{x:.2f},{y - 7:.2f} {x - 6:.2f},{y:.2f} {x:.2f},{y + 7:.2f} {x + 6:.2f},{y:.2f}"
            )
    return f'<polygon points="{points}" />'


def _series(
    records: Sequence[HistoryRecord], evidence: Callable[[HistoryRecord], bool] | None = None
) -> list[str]:
    platforms = list(dict.fromkeys(r.platform for r in records))
    lines = ['<svg viewBox="0 0 720 300" role="img" aria-label="Success rate history">']
    for percent in (0, 25, 50, 75, 100):
        y = 260 - percent * 2.2
        lines += [
            f'<line x1="60" y1="{y:.2f}" x2="660" y2="{y:.2f}" class="grid" />',
            f'<text x="5" y="{y:.2f}">{percent}%</text>',
        ]
    # The plot ends at x=660, leaving room for the last centred date label in the 720-wide box.
    positions = [60 + i * 600 / max(1, len(records) - 1) for i in range(len(records))]
    baseline_y = 260 - records[0].baseline.rate * 220
    baseline = [f"60.00,{baseline_y:.2f}"]
    for x, record in zip(positions, records, strict=True):
        y = 260 - record.baseline.rate * 220
        if y != baseline_y:
            baseline.extend((f"{x:.2f},{baseline_y:.2f}", f"{x:.2f},{y:.2f}"))
            baseline_y = y
    baseline.append(f"660.00,{baseline_y:.2f}")
    lines.append(f'<polyline points="{" ".join(baseline)}" class="baseline" />')
    stride = max(1, math.ceil(len(records) / 12))
    for i, (x, record) in enumerate(zip(positions, records, strict=True)):
        tooltip = " ".join(
            f"{record.commit_date} {record.policy} / {record.evaluator}: "
            f"{record.successes}/{record.trials} ({record.successes / record.trials:.1%}), "
            f"{record.verdict.value}, {record.platform}; "
            f"{format_percent(record.confidence)}% CI, "
            f"tolerance {format_percent(record.tolerance)} pp".splitlines()
        )
        lines += [
            f'<g class="{record.verdict.value}"><title>{_escape(tooltip)}</title>',
            f'<line x1="{x:.2f}" x2="{x:.2f}" '
            f'y1="{260 - record.interval.upper * 220:.2f}" '
            f'y2="{260 - record.interval.lower * 220:.2f}" />',
            _marker(
                x, 260 - record.successes / record.trials * 220, platforms.index(record.platform)
            ),
            "</g>",
        ]
        if i % stride == 0:
            lines.append(
                f'<text x="{x:.2f}" y="285" text-anchor="middle">'
                f"{_escape(record.commit_date[:10])}</text>"
            )
    lines += [
        "</svg>",
        '<p>Verdicts: <span class="pass">PASS</span> / '
        '<span class="warn">WARN</span> / <span class="block">BLOCK</span>. '
        "Dashed line: baseline.</p>",
        "<ul>",
    ]
    for index, platform in enumerate(platforms):
        lines.append(
            f'<li><svg width="24" height="24" viewBox="0 0 24 24">'
            f"{_marker(12, 12, index)}</svg> {_escape(platform)}</li>"
        )
    lines += [
        "</ul>",
        '<div class="table-wrap">',
        "<table><thead><tr><th>Commit date</th><th>Commit</th>"
        "<th>Successes/trials</th><th>Rate</th><th>Interval</th><th>Verdict</th>"
        "<th>Platform</th><th>Run</th>"
        + ("<th>Paired</th>" if records[0].series == "nightly" else "")
        + ("<th>Certificate</th>" if evidence is not None else "")
        + "</tr></thead><tbody>",
    ]
    for record in reversed(records):
        cells = [
            _escape(record.commit_date),
            _commit_link(record),
            f"{record.successes}/{record.trials}",
            f"{record.successes / record.trials:.1%}",
            f"{record.interval.lower:.1%} to {record.interval.upper:.1%}",
            _escape(record.verdict.value),
            _escape(record.platform)
            + (
                f" \u00b7 {_escape(record.runner_image)}" if record.runner_image is not None else ""
            ),
            _link(record.run_url, f"#{record.run_id}.{record.run_attempt}"),
        ]
        if record.paired is not None:
            p = record.paired
            cells.append(
                f"{p.reference_only} lost / {p.candidate_only} gained, "
                f"p={p.p_value:.3g}, {p.verdict.value.upper()}"
            )
        if evidence is not None:
            identity = f"{record.run_id}.{record.run_attempt}"
            label = "candidate" if record.series == "nightly" else "results"
            reference = (
                f'<a href="results/{identity}.reference.json">reference</a> '
                if record.series == "nightly"
                else ""
            )
            cells.append(
                f'<a href="results/{identity}.json">{label}</a> '
                + reference
                + f'<a href="bundles/{identity}.jsonl">bundle</a>'
                if evidence(record)
                else "not signed"
            )
        lines.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return [*lines, "</tbody></table></div>"]


def render_html(
    history: Sequence[HistoryRecord],
    *,
    title: str = "PipeRobot gate history",
    evidence: Callable[[HistoryRecord], bool] | None = None,
) -> str:
    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        '<head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:2rem;color:#222;background:#fff}"
        "table{border-collapse:collapse}"
        ".table-wrap,pre{overflow-x:auto}"
        "td,th{padding:.5rem;border:1px solid #ccc;white-space:nowrap}"
        "ul{list-style:none;padding-left:0}"
        "svg{max-width:100%}.grid{stroke:#ddd}.baseline{fill:none;stroke:#444;stroke-dasharray:6 4}"
        ".pass{color:#164e35;fill:#164e35;stroke:#164e35}"
        ".warn{color:#98700a;fill:#98700a;stroke:#98700a}"
        ".block{color:#b91c1c;fill:#b91c1c;stroke:#b91c1c}",
        "</style></head><body>",
        f"<h1>{_escape(title)}</h1>",
    ]
    groups: dict[tuple[str, str, str], list[HistoryRecord]] = {}
    for record in history:
        groups.setdefault((record.policy, record.evaluator, record.series), []).append(record)
    if not groups:
        lines.append("<p>No evaluations yet.</p>")
    for (policy, evaluator, series), records in groups.items():
        suffix = " \u00b7 nightly" if series == "nightly" else ""
        lines += [
            f"<section><h2>{_escape(policy)} / {_escape(evaluator)}{suffix}</h2>",
            *_series(records, evidence),
            "</section>",
        ]
    if evidence is not None and any(evidence(record) for record in history):
        from piperobot.reports.certificate import verification_command

        command = " ".join(verification_command(Path("results.json"))) + " --bundle bundle.jsonl"
        lines += [
            "<section><h2>Verify a point</h2>",
            "<p>Download both results and bundle, "
            "saving them as results.json and bundle.jsonl.</p>",
            "<pre>python -m piperobot.reports.certificate verify "
            "results.json --bundle bundle.jsonl</pre>",
            f"<p>Equivalent GitHub CLI verification:</p><pre>{_escape(command)}</pre>",
            "</section>",
        ]
        if any(record.series == "nightly" and evidence(record) for record in history):
            lines[-1:-1] = [
                "<p>For a nightly point, download candidate, reference and bundle as "
                "candidate.json, reference.json and bundle.jsonl.</p>",
                "<pre>python -m piperobot.reports.certificate verify candidate.json "
                "--reference reference.json --bundle bundle.jsonl</pre>",
            ]
    return "\n".join([*lines, "</body></html>", ""])


def _build_record(args: argparse.Namespace, previous: Sequence[HistoryRecord]) -> HistoryRecord:
    results = load_results(args.results)
    result = decide(
        SuccessCount(results.successes, results.trials),
        load_baseline(args.baseline_file),
        args.confidence,
        args.tolerance,
    )
    # Preserve the first timestamp when retrying this exact workflow attempt.
    existing = next(
        (r for r in previous if (r.run_id, r.run_attempt) == (args.run_id, args.run_attempt)),
        None,
    )
    evaluated_at = args.evaluated_at or (
        existing.evaluated_at
        if existing is not None
        else datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    runner_image = None
    if getattr(args, "runner_image", None) is not None:
        with args.runner_image.open(encoding="utf-8") as stream:
            runner_image = stream.readline()
        if not runner_image:
            raise HistoryError("runner_image file is empty")
    record = record_from_gate(
        results,
        result,
        commit=args.commit,
        commit_date=args.commit_date,
        evaluated_at=evaluated_at,
        run_url=args.run_url,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        platform=args.platform if args.platform is not None else describe_platform(),
        runner_image=runner_image,
        # `append` has no --schema: its unsigned local/bootstrap path stays schema 1.
        schema=getattr(args, "schema", 1),
        series=getattr(args, "series", "main"),
        paired=(
            paired_record(
                load_results(args.paired_reference),
                results,
                reference_commit=args.reference_commit,
                tolerance=args.tolerance,
            )
            if getattr(args, "series", "main") == "nightly"
            else None
        ),
        cpu_flags_sha256=(
            cpu_flags_digest(args.cpu_flags.read_text(encoding="utf-8"))
            if getattr(args, "cpu_flags", None) is not None
            else None
        ),
    )
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("append")
    record_parser = commands.add_parser("record")
    predicate = commands.add_parser("predicate-type")
    predicate.add_argument("--record", type=Path)
    record_parser.add_argument(
        "--schema",
        type=int,
        choices=(1, 2),
        default=2,
        help="Record schema version (default: 2)",
    )
    record_parser.add_argument("--series", choices=("main", "nightly"), default="main")
    record_parser.add_argument("--paired-reference", type=Path)
    record_parser.add_argument("--reference-commit")
    record_parser.add_argument("--cpu-flags", type=Path)
    record_parser.add_argument("--runner-image", type=Path)
    add.add_argument("--history", type=Path, required=True)
    add.add_argument("--record", type=Path)
    record_parser.add_argument("--output", type=Path, required=True)
    building = (
        "results",
        "baseline-file",
        "commit",
        "commit-date",
        "run-url",
        "platform",
        "evaluated-at",
        "confidence",
        "tolerance",
    )
    for command in (add, record_parser):
        for name in building:
            kind = (
                Path
                if name in ("results", "baseline-file")
                else (float if name in ("confidence", "tolerance") else str)
            )
            command.add_argument(f"--{name}", type=kind, default=argparse.SUPPRESS)
        for name in ("run-id", "run-attempt"):
            command.add_argument(f"--{name}", type=int, required=True)
    add.add_argument(
        "--new", action="store_true", help="Allow a missing history for bootstrap or local use only"
    )
    render = commands.add_parser("render")
    render.add_argument("--history", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    if args.command == "record":
        if args.series == "nightly":
            if args.schema != 2 or args.paired_reference is None or args.reference_commit is None:
                parser.error(
                    "nightly requires --schema 2, --paired-reference and --reference-commit"
                )
        elif args.paired_reference is not None or args.reference_commit is not None:
            parser.error("main rejects --paired-reference and --reference-commit")
        if args.cpu_flags is not None and args.schema != 2:
            parser.error("--cpu-flags requires --schema 2")
        if args.runner_image is not None and args.schema != 2:
            parser.error("--runner-image requires --schema 2")
    if args.command == "predicate-type":
        try:
            print(
                predicate_type_for(
                    HistoryRecord.from_dict(json.loads(args.record.read_text(encoding="utf-8")))
                )
                if args.record is not None
                else GATE_VERDICT_PREDICATE_TYPE
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command in ("append", "record"):
        if getattr(args, "record", None) is not None:
            forbidden = [f"--{name}" for name in building if hasattr(args, name.replace("-", "_"))]
            if forbidden:
                parser.error("--record cannot be combined with " + ", ".join(forbidden))
        else:
            for name in building[:5]:
                if not hasattr(args, name.replace("-", "_")):
                    parser.error(f"--{name} is required when building a record")
        for name, default in (
            ("platform", None),
            ("evaluated_at", None),
            ("confidence", DEFAULT_CONFIDENCE),
            ("tolerance", DEFAULT_TOLERANCE),
        ):
            if not hasattr(args, name):
                setattr(args, name, default)
    try:
        if args.command == "render":
            evidence = None
            if args.evidence_dir is not None:

                def evidence(record: HistoryRecord) -> bool:
                    identity = f"{record.run_id}.{record.run_attempt}"
                    return all(
                        (args.evidence_dir / directory / f"{identity}.{suffix}").is_file()
                        for directory, suffix in (
                            ("results", "json"),
                            ("bundles", "jsonl"),
                            *(
                                (("results", "reference.json"),)
                                if record.series == "nightly"
                                else ()
                            ),
                        )
                    )

            page = render_html(load_history(args.history), evidence=evidence)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(page, encoding="utf-8", newline="\n")
        else:
            previous = (
                load_history(args.history, allow_missing=args.new)
                if args.command == "append"
                else []
            )
            if getattr(args, "record", None) is not None:
                record = HistoryRecord.from_dict(
                    json.loads(args.record.read_text(encoding="utf-8"))
                )
                if (record.run_id, record.run_attempt) != (args.run_id, args.run_attempt):
                    raise HistoryError(
                        f"record is for run {record.run_id}.{record.run_attempt}, "
                        f"this is run {args.run_id}.{args.run_attempt}"
                    )
            else:
                record = _build_record(args, previous)
            if args.command == "record":
                _save_json(json.dumps(record.to_dict(), indent=2) + "\n", args.output)
                return 0
            updated = append(previous, record)
            save_history(updated, args.history, previous=previous)
            print("already present" if updated == previous else "appended")
    # Bad inputs raise ValueError (HistoryError, ResultsError, BaselineError) or OSError; anything
    # else is a bug in this code and keeps its traceback (ADR 0009).
    except (OSError, ValueError) as exc:
        print(f"ERROR: {' '.join(str(exc).splitlines())}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
