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
import html
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
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


class HistoryError(ValueError):
    """History is invalid or an append would rewrite existing records."""


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

    def to_dict(self) -> dict[str, Any]:
        data = dict(vars(self))
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
        if not isinstance(data, Mapping) or set(data) != set(cls.__dataclass_fields__):
            raise HistoryError("record must have exactly the schema 1 fields")
        values = dict(data)
        for name in ("schema", "run_id", "run_attempt", "successes", "trials"):
            if type(values[name]) is not int:
                raise HistoryError(f"{name} must be an int")
        if values["schema"] != 1:
            raise HistoryError("schema must equal 1")
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
) -> HistoryRecord:
    if result.candidate != SuccessCount(results.successes, results.trials):
        raise HistoryError("candidate does not match results successes/trials")
    record = HistoryRecord(
        1,
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
    )
    return HistoryRecord.from_dict(record.to_dict())


def load_history(path: Path, *, allow_missing: bool = False) -> list[HistoryRecord]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if allow_missing:
            return []
        raise HistoryError(f"{path}: {exc}") from exc
    except (OSError, ValueError) as exc:
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


def _series(records: Sequence[HistoryRecord]) -> list[str]:
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
    baseline: list[str] = []
    for i, (x, record) in enumerate(zip(positions, records, strict=True)):
        y = 260 - record.baseline.rate * 220
        if i:
            baseline.append(f"{x:.2f},{260 - records[i - 1].baseline.rate * 220:.2f}")
        baseline.append(f"{x:.2f},{y:.2f}")
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
        "<table><thead><tr><th>Commit date</th><th>Commit</th>"
        "<th>Successes/trials</th><th>Rate</th><th>Interval</th><th>Verdict</th>"
        "<th>Platform</th><th>Run</th></tr></thead><tbody>",
    ]
    for record in reversed(records):
        cells = [
            _escape(record.commit_date),
            _commit_link(record),
            f"{record.successes}/{record.trials}",
            f"{record.successes / record.trials:.1%}",
            f"{record.interval.lower:.1%} to {record.interval.upper:.1%}",
            _escape(record.verdict.value),
            _escape(record.platform),
            _link(record.run_url, f"#{record.run_id}.{record.run_attempt}"),
        ]
        lines.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return [*lines, "</tbody></table>"]


def render_html(history: Sequence[HistoryRecord], *, title: str = "PipeRobot gate history") -> str:
    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        '<head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:2rem;color:#222;background:#fff}"
        "table{border-collapse:collapse}"
        "td,th{padding:.5rem;border:1px solid #ccc;white-space:nowrap}"
        "ul{list-style:none;padding-left:0}"
        "svg{max-width:100%}.grid{stroke:#ddd}.baseline{fill:none;stroke:#444;stroke-dasharray:6 4}"
        ".pass{color:#164e35;fill:#164e35;stroke:#164e35}"
        ".warn{color:#98700a;fill:#98700a;stroke:#98700a}"
        ".block{color:#b91c1c;fill:#b91c1c;stroke:#b91c1c}",
        "</style></head><body>",
        f"<h1>{_escape(title)}</h1>",
    ]
    groups: dict[tuple[str, str], list[HistoryRecord]] = {}
    for record in history:
        groups.setdefault((record.policy, record.evaluator), []).append(record)
    if not groups:
        lines.append("<p>No evaluations yet.</p>")
    for (policy, evaluator), records in groups.items():
        lines += [
            f"<section><h2>{_escape(policy)} / {_escape(evaluator)}</h2>",
            *_series(records),
            "</section>",
        ]
    return "\n".join([*lines, "</body></html>", ""])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("append")
    for name in ("history", "results", "baseline-file"):
        add.add_argument(f"--{name}", type=Path, required=True)
    for name in ("commit", "commit-date", "run-url"):
        add.add_argument(f"--{name}", required=True)
    for name in ("run-id", "run-attempt"):
        add.add_argument(f"--{name}", type=int, required=True)
    add.add_argument("--platform")
    add.add_argument("--evaluated-at")
    add.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    add.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    add.add_argument(
        "--new", action="store_true", help="Allow a missing history for bootstrap or local use only"
    )
    render = commands.add_parser("render")
    render.add_argument("--history", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            page = render_html(load_history(args.history))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(page, encoding="utf-8", newline="\n")
        else:
            previous = load_history(args.history, allow_missing=args.new)
            results = load_results(args.results)
            result = decide(
                SuccessCount(results.successes, results.trials),
                load_baseline(args.baseline_file),
                args.confidence,
                args.tolerance,
            )
            # Preserve the first timestamp when retrying this exact workflow attempt.
            existing = next(
                (
                    r
                    for r in previous
                    if (r.run_id, r.run_attempt) == (args.run_id, args.run_attempt)
                ),
                None,
            )
            evaluated_at = args.evaluated_at or (
                existing.evaluated_at
                if existing is not None
                else datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
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
            )
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
