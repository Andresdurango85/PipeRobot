"""Admit a task to paired comparisons using two fresh-process runs of one checkpoint.

Decision table:
- Any outcome or initial/final digest mismatch: NOT_REPEATABLE, unpaired Wilson/Newcombe
  (piperobot.stats.gate, ADR 0003). An outcome mismatch alone is conclusive.
- Matching outcomes without final digests: UNVERIFIED, no recommended gate; the caller decides.
- Matching outcomes and final digests (and initial digests if present): REPEATABLE,
  paired gate (piperobot.stats.paired, ADR 0032).
Digest presence must agree between files; policy and seed sets must match.

Usage: python -m piperobot.stats.repeatability --first a.json --second b.json [--json]
Exit codes: 0 REPEATABLE, 1 NOT_REPEATABLE, 3 UNVERIFIED, 2 invalid input or arguments.
Exit 1 is a finding, not a crash: the check ran and the task must use the unpaired gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Never

from piperobot.results import EvalResults, ResultsError, load_results


class Verdict(StrEnum):
    REPEATABLE = "REPEATABLE"
    NOT_REPEATABLE = "NOT_REPEATABLE"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class RepeatabilityResult:
    verdict: Verdict
    gate: str | None
    seeds: int
    matching_outcomes: int
    matching_final_digests: int | None
    matching_initial_digests: int | None
    mismatched_seeds: list[int]
    reason: str


def check_repeatability(first: EvalResults, second: EvalResults) -> RepeatabilityResult:
    a = {e.seed: e for e in first.episodes}
    b = {e.seed: e for e in second.episodes}
    if a.keys() != b.keys():
        raise ResultsError(
            "seed sets differ: "
            f"missing from first {sorted(b.keys() - a.keys())[:5]}; "
            f"missing from second {sorted(a.keys() - b.keys())[:5]}"
        )
    if first.policy != second.policy:
        raise ResultsError(f"policy strings differ: {first.policy!r} vs {second.policy!r}")
    fields = ("success", "final_state_sha256", "initial_state_sha256")
    matches: list[int | None] = []
    mismatched: set[int] = set()
    for field in fields:
        provided = getattr(first.episodes[0], field) is not None
        if provided != (getattr(second.episodes[0], field) is not None):
            raise ResultsError(f"{field} contract mismatch")
        differences = {seed for seed in a if getattr(a[seed], field) != getattr(b[seed], field)}
        mismatched.update(differences)
        matches.append(len(a) - len(differences) if provided else None)
    if mismatched:
        verdict, gate = Verdict.NOT_REPEATABLE, "unpaired"
        reason = "Episodes differ; use the unpaired Wilson/Newcombe gate (ADR 0003)."
    elif matches[1] is None:
        verdict, gate = Verdict.UNVERIFIED, None
        reason = (
            "Identical outcomes alone do not show that episodes reproduce; add final "
            "digests to the evaluator. No gate recommended; the caller decides."
        )
    else:
        verdict, gate = Verdict.REPEATABLE, "paired"
        reason = "Outcomes and supplied digests match; use the paired gate (ADR 0032)."
    return RepeatabilityResult(
        verdict,
        gate,
        len(a),
        len(a) - sum(a[s].success != b[s].success for s in a),
        matches[1],
        matches[2],
        sorted(mismatched)[:10],
        reason,
    )


def format_result(result: RepeatabilityResult) -> str:
    def count(value: int | None) -> str:
        return "not provided" if value is None else f"{value}/{result.seeds}"

    return "\n".join(
        [
            f"Seeds: {result.seeds}",
            f"Matching outcomes: {count(result.matching_outcomes)}",
            f"Matching final digests: {count(result.matching_final_digests)}",
            f"Matching initial digests: {count(result.matching_initial_digests)}",
            f"Mismatched seeds: {result.mismatched_seeds}",
            f"Verdict: {result.verdict.value}",
            f"Recommended gate: {result.gate or 'none (caller decides)'}",
            result.reason,
        ]
    )


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ResultsError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=(
            "Exit codes: 0 REPEATABLE, 1 NOT_REPEATABLE, 3 UNVERIFIED, 2 invalid input. "
            "Exit 1 is a finding, not a crash: use the unpaired gate."
        ),
    )
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = check_repeatability(load_results(args.first), load_results(args.second))
    except ResultsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(result)) if args.json else format_result(result))
    return {Verdict.REPEATABLE: 0, Verdict.NOT_REPEATABLE: 1, Verdict.UNVERIFIED: 3}[result.verdict]


if __name__ == "__main__":
    sys.exit(main())
