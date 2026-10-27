"""Command-line inputs shared by `stats.gate` and `reports.pr_comment`.

The candidate comes from counts (``--candidate 38/50``) or an evaluation results file
(``--results``); the baseline from counts (``--baseline 45/50``) or the stored baseline file
(``--baseline-file``). Bad input files raise `InputError`; CLIs exit 2 on it (ADR 0009).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from eval.results import EpisodeResult, ResultsError, load_results
from stats.baseline import BaselineError, load_baseline
from stats.gate import SuccessCount

InputError = (ResultsError, BaselineError)


@dataclass(frozen=True)
class GateInputs:
    candidate: SuccessCount
    baseline: SuccessCount
    failed_episodes: list[EpisodeResult] = field(default_factory=list)


def add_input_arguments(parser: argparse.ArgumentParser) -> None:
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--candidate", type=SuccessCount.parse, help="Counts, e.g. 38/50")
    candidate.add_argument("--results", type=Path, help="Evaluation results JSON")
    baseline = parser.add_mutually_exclusive_group(required=True)
    baseline.add_argument("--baseline", type=SuccessCount.parse, help="Counts, e.g. 45/50")
    baseline.add_argument("--baseline-file", type=Path, help="Stored baseline JSON")


def resolve_inputs(args: argparse.Namespace) -> GateInputs:
    baseline = args.baseline or load_baseline(args.baseline_file)
    if args.candidate:
        return GateInputs(candidate=args.candidate, baseline=baseline)
    results = load_results(args.results)
    return GateInputs(
        candidate=SuccessCount(results.successes, results.trials),
        baseline=baseline,
        failed_episodes=results.failed,
    )
