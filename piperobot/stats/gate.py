"""Compare a candidate policy's success rate against the stored baseline and decide the gate.

Each evaluation is a series of independent pass/fail episodes, so a policy's success rate is a
binomial proportion. The gate uses:

- the Wilson score interval for each success rate (well behaved for small n and rates near 0/1),
- Newcombe's hybrid score interval (method 10, Newcombe 1998) for the difference
  ``candidate - baseline``, which accounts for the uncertainty of both runs.

Verdict rule:
- BLOCK: the whole difference interval is below zero, i.e. the candidate is worse with the chosen
  confidence. When both policies are truly equal this happens with probability ~(1 - confidence)/2.
- WARN: not a confident regression, but the observed drop is larger than ``tolerance``. Passes,
  flagging that more episodes are needed to tell.
- PASS: otherwise. The reason says whether the interval includes zero (no significant
  difference) or lies entirely above it (the candidate is significantly better).

Usage:
    uv run python -m piperobot.stats.gate --candidate 38/50 --baseline 45/50
    uv run python -m piperobot.stats.gate --results out/results.json \\
        --baseline-file robots/mock/baseline.json

Exit codes: 0 PASS or WARN, 1 BLOCK, 2 invalid input files.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from statistics import NormalDist

DEFAULT_CONFIDENCE = 0.95
DEFAULT_TOLERANCE = 0.10


def format_percent(fraction: float) -> str:
    """Format a fraction as a decimal percentage: 0.125 -> '12.5', 0.95 -> '95'."""
    percent = format(Decimal(str(fraction)) * 100, "f")
    return percent.rstrip("0").rstrip(".") if "." in percent else percent


@dataclass(frozen=True)
class SuccessCount:
    successes: int
    trials: int

    def __post_init__(self) -> None:
        for name in ("successes", "trials"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an int, got {value!r}")
        if self.trials <= 0:
            raise ValueError(f"trials must be positive, got {self.trials}")
        if not 0 <= self.successes <= self.trials:
            raise ValueError(f"successes must be in [0, {self.trials}], got {self.successes}")

    @property
    def rate(self) -> float:
        return self.successes / self.trials

    @classmethod
    def parse(cls, text: str) -> SuccessCount:
        """Parse ``"successes/trials"``, e.g. ``"38/50"``."""
        successes, sep, trials = text.partition("/")
        if not sep:
            raise ValueError(f"expected 'successes/trials', got {text!r}")
        return cls(int(successes), int(trials))

    def __str__(self) -> str:
        return f"{self.successes}/{self.trials}"


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float

    def __str__(self) -> str:
        return f"[{self.lower:.3f}, {self.upper:.3f}]"


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105 - a verdict name, not a password
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class GateResult:
    candidate: SuccessCount
    baseline: SuccessCount
    confidence: float
    tolerance: float
    candidate_interval: Interval
    baseline_interval: Interval
    difference: float
    difference_interval: Interval
    verdict: Verdict
    reason: str


def _z(confidence: float) -> float:
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    return NormalDist().inv_cdf(0.5 + confidence / 2)


def wilson_interval(count: SuccessCount, confidence: float = DEFAULT_CONFIDENCE) -> Interval:
    """Wilson score interval for a binomial success rate."""
    z = _z(confidence)
    n, p = count.trials, count.rate
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    half_width = z / denominator * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    # Mathematically exact at the edges; computing them leaves float noise (e.g. 2.8e-17 for 0/n).
    lower = 0.0 if count.successes == 0 else center - half_width
    upper = 1.0 if count.successes == count.trials else center + half_width
    return Interval(lower, upper)


def newcombe_interval(
    candidate: SuccessCount,
    baseline: SuccessCount,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Interval:
    """Newcombe hybrid score interval for ``candidate.rate - baseline.rate``."""
    p1, p2 = candidate.rate, baseline.rate
    w1, w2 = wilson_interval(candidate, confidence), wilson_interval(baseline, confidence)
    difference = p1 - p2
    lower = difference - math.sqrt((p1 - w1.lower) ** 2 + (w2.upper - p2) ** 2)
    upper = difference + math.sqrt((w1.upper - p1) ** 2 + (p2 - w2.lower) ** 2)
    return Interval(lower, upper)


def decide(
    candidate: SuccessCount,
    baseline: SuccessCount,
    confidence: float = DEFAULT_CONFIDENCE,
    tolerance: float = DEFAULT_TOLERANCE,
) -> GateResult:
    """Apply the gate rule (see module docstring) to a candidate vs. baseline evaluation."""
    if not math.isfinite(tolerance):
        raise ValueError(f"tolerance must be finite, got {tolerance}")
    if tolerance < 0:
        raise ValueError(f"tolerance must be >= 0, got {tolerance}")
    difference = candidate.rate - baseline.rate
    # WARN compares exact counts with the tolerance as typed (0.1 is 1/10): with floats, a drop
    # of exactly the tolerance can round above it (0.7 - 0.8 == -0.10000000000000009).
    exact_drop = Fraction(baseline.successes, baseline.trials) - Fraction(
        candidate.successes, candidate.trials
    )
    diff_interval = newcombe_interval(candidate, baseline, confidence)

    if diff_interval.upper < 0:
        verdict = Verdict.BLOCK
        reason = (
            f"Regression: success rate dropped {-difference * 100:.1f} pp "
            f"and the {format_percent(confidence)}% "
            f"interval of the difference {diff_interval} is entirely below zero."
        )
    elif exact_drop > Fraction(str(tolerance)):
        verdict = Verdict.WARN
        reason = (
            f"Success rate dropped {-difference * 100:.1f} pp "
            f"(more than the {format_percent(tolerance)} pp tolerance), but it is not significant: "
            f"the difference interval {diff_interval} includes zero. "
            "Run more episodes to tell."
        )
    elif diff_interval.lower > 0:
        verdict = Verdict.PASS
        reason = (
            f"No regression: the candidate is significantly better; difference interval "
            f"{diff_interval} is entirely above zero."
        )
    else:
        verdict = Verdict.PASS
        reason = f"No significant difference: difference interval {diff_interval} includes zero."

    return GateResult(
        candidate=candidate,
        baseline=baseline,
        confidence=confidence,
        tolerance=tolerance,
        candidate_interval=wilson_interval(candidate, confidence),
        baseline_interval=wilson_interval(baseline, confidence),
        difference=difference,
        difference_interval=diff_interval,
        verdict=verdict,
        reason=reason,
    )


def format_result(result: GateResult) -> str:
    return "\n".join(
        [
            f"Candidate:  {result.candidate} = {result.candidate.rate:.1%}  "
            f"CI {result.candidate_interval}",
            f"Baseline:   {result.baseline} = {result.baseline.rate:.1%}  "
            f"CI {result.baseline_interval}",
            f"Difference: {result.difference:+.1%}  CI {result.difference_interval}",
            f"Verdict:    {result.verdict.value.upper()}",
            result.reason,
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    # Imported here: cli_inputs builds on this module, so a top-level import would be circular.
    from piperobot.stats.cli_inputs import InputError, add_input_arguments, resolve_inputs

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_input_arguments(parser)
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="Observed drop (as a fraction) above which a non-significant result is a WARN",
    )
    args = parser.parse_args(argv)

    try:
        inputs = resolve_inputs(args)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    result = decide(inputs.candidate, inputs.baseline, args.confidence, args.tolerance)
    print(format_result(result))
    return 1 if result.verdict is Verdict.BLOCK else 0


if __name__ == "__main__":
    sys.exit(main())
