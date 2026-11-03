"""Compare a candidate with a reference policy evaluated on the same seeds, episode by episode.

When both policies run on the same seeds under the same reproducible conditions (same job, same
CPU: PushT on CPU is bit-reproducible there), episodes where both succeed or both fail say
nothing about a difference. Only the discordant ones do: ``b`` episodes the reference solved and
the candidate lost, ``c`` the reverse. If the policies are equally good, each discordant episode
is a fair coin, so ``b ~ Binomial(b + c, 1/2)`` (exact McNemar test, computed exactly).

Verdict rule:
- BLOCK: the one-sided p-value P(X >= b) is below ``alpha`` (default 0.025, the lower tail of
  the 95% two-sided intervals that gate.py uses). Identical outcomes (b = c = 0) never block.
- WARN: not significant, but the observed paired drop (b - c) / trials exceeds ``tolerance``.
- PASS: otherwise.
The Newcombe hybrid score interval for paired data, at confidence ``1 - 2 * alpha``, is reported
in pp but does not decide, so two criteria cannot disagree at the edge.

Usage:
    uv run python -m piperobot.stats.paired --reference ref.json --candidate cand.json

Exit codes: 0 PASS or WARN, 1 BLOCK, 2 invalid input or arguments.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Never

from piperobot.results import EvalResults, ResultsError, load_results
from piperobot.stats.gate import (
    DEFAULT_TOLERANCE,
    Interval,
    SuccessCount,
    Verdict,
    format_percent,
    wilson_interval,
)


def _validate_count(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


@dataclass(frozen=True)
class PairedCounts:
    both: int
    reference_only: int
    candidate_only: int
    neither: int

    def __post_init__(self) -> None:
        for name in ("both", "reference_only", "candidate_only", "neither"):
            _validate_count(name, getattr(self, name))
        if self.trials == 0:
            raise ValueError("trials must be positive")

    @property
    def trials(self) -> int:
        return self.both + self.reference_only + self.candidate_only + self.neither

    @property
    def reference(self) -> SuccessCount:
        return SuccessCount(self.both + self.reference_only, self.trials)

    @property
    def candidate(self) -> SuccessCount:
        return SuccessCount(self.both + self.candidate_only, self.trials)

    @property
    def discordant(self) -> int:
        return self.reference_only + self.candidate_only

    @classmethod
    def from_results(cls, reference: EvalResults, candidate: EvalResults) -> PairedCounts:
        first = {episode.seed: episode.success for episode in reference.episodes}
        second = {episode.seed: episode.success for episode in candidate.episodes}
        if first.keys() != second.keys():
            raise ResultsError(
                "seed sets differ: "
                f"missing from reference {sorted(second.keys() - first.keys())[:5]}; "
                f"missing from candidate {sorted(first.keys() - second.keys())[:5]}"
            )
        cells = [0, 0, 0, 0]
        for seed, success in first.items():
            cells[2 * (not success) + (not second[seed])] += 1
        return cls(cells[0], cells[1], cells[2], cells[3])


def exact_mcnemar_p(reference_only: int, candidate_only: int) -> float:
    """Exact upper binomial tail: evidence that the candidate is worse."""
    _validate_count("reference_only", reference_only)
    _validate_count("candidate_only", candidate_only)
    n = reference_only + candidate_only
    return float(Fraction(sum(math.comb(n, k) for k in range(reference_only, n + 1)), 2**n))


def newcombe_paired_interval(counts: PairedCounts, confidence: float = 0.95) -> Interval:
    """Newcombe (1998b) paired hybrid score interval for candidate minus reference."""
    reference, candidate = counts.reference, counts.candidate
    p1, p2 = reference.rate, candidate.rate
    w1, w2 = wilson_interval(reference, confidence), wilson_interval(candidate, confidence)
    a, b, c, d = counts.both, counts.reference_only, counts.candidate_only, counts.neither
    denominator = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    phi = (a * d - b * c) / denominator if denominator else 0.0
    theta = p2 - p1
    left, right = p2 - w2.lower, w1.upper - p1
    lower = theta - math.sqrt(max(0.0, left**2 - 2 * phi * left * right + right**2))
    left, right = w2.upper - p2, p1 - w1.lower
    upper = theta + math.sqrt(max(0.0, left**2 - 2 * phi * left * right + right**2))
    return Interval(max(-1.0, lower), min(1.0, upper))


@dataclass(frozen=True)
class PairedResult:
    counts: PairedCounts
    alpha: float
    tolerance: float
    p_value: float
    difference: float
    difference_interval: Interval
    verdict: Verdict
    reason: str


def decide_paired(
    counts: PairedCounts, alpha: float = 0.025, tolerance: float = DEFAULT_TOLERANCE
) -> PairedResult:
    """Apply the paired gate rule; the interval does not decide the verdict."""
    # The reported interval uses confidence 1 - 2 * alpha, which must stay in (0, 1).
    if not 0 < alpha < 0.5:
        raise ValueError(f"alpha must be in (0, 0.5), got {alpha}")
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(f"tolerance must be finite and >= 0, got {tolerance}")
    p = exact_mcnemar_p(counts.reference_only, counts.candidate_only)
    drop = Fraction(counts.reference_only - counts.candidate_only, counts.trials)
    difference = float(-drop)
    interval = newcombe_paired_interval(counts, 1 - 2 * alpha)
    episodes = f"{counts.reference_only} episodes lost, {counts.candidate_only} gained"
    if p < alpha:
        verdict = Verdict.BLOCK
        reason = f"Regression: success rate dropped {-difference * 100:.1f} pp ({episodes})."
    elif drop > Fraction(str(tolerance)):
        verdict = Verdict.WARN
        reason = (
            f"Success rate dropped {-difference * 100:.1f} pp ({episodes}), "
            f"more than the {format_percent(tolerance)} pp tolerance, but it is not significant. "
            "Run more episodes to tell."
        )
    else:
        verdict = Verdict.PASS
        reason = f"No regression detected: difference {difference * 100:+.1f} pp ({episodes})."
    reason += f" Exact McNemar p={p:.6g}, alpha={alpha:g}."
    return PairedResult(counts, alpha, tolerance, p, difference, interval, verdict, reason)


def format_paired_result(result: PairedResult) -> str:
    return "\n".join(
        [
            f"Candidate:  {result.counts.candidate} = {result.counts.candidate.rate:.1%}",
            f"Reference:  {result.counts.reference} = {result.counts.reference.rate:.1%}",
            f"Difference: {result.difference * 100:+.1f} pp  CI {result.difference_interval}",
            f"Verdict:    {result.verdict.value.upper()}",
            result.reason,
        ]
    )


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ResultsError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--alpha", type=float, default=0.025)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    try:
        args = parser.parse_args(argv)
        counts = PairedCounts.from_results(
            load_results(args.reference), load_results(args.candidate)
        )
        result = decide_paired(counts, args.alpha, args.tolerance)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(format_paired_result(result))
    return 1 if result.verdict is Verdict.BLOCK else 0


if __name__ == "__main__":
    sys.exit(main())
