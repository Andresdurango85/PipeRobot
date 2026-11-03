"""General laws of the statistical gate, with exact arithmetic for verdict oracles."""

from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from piperobot.stats.gate import (
    SuccessCount,
    Verdict,
    decide,
    format_percent,
    newcombe_interval,
    wilson_interval,
)

CONFIDENCES = st.floats(min_value=0.5, max_value=0.999)
TOLERANCES = st.floats(min_value=0, max_value=1)


@given(st.decimals(min_value=0, max_value=1, places=6))
def test_format_percent_preserves_decimal_value(value: Decimal) -> None:
    # The oracle is the decimal Hypothesis drew, not the float: up to 6 places round-trip exactly.
    assert Decimal(format_percent(float(value))) == value * 100


@st.composite
def counts(draw: DrawFn, *, minimum: int = 0, maximum_trials: int = 10_000) -> SuccessCount:
    trials = draw(st.integers(min_value=1, max_value=maximum_trials))
    return SuccessCount(draw(st.integers(min_value=minimum, max_value=trials)), trials)


@given(counts(), CONFIDENCES)
def test_wilson_bounds(count: SuccessCount, confidence: float) -> None:
    interval = wilson_interval(count, confidence)
    assert 0 <= interval.lower <= count.rate <= interval.upper <= 1
    assert interval.lower < interval.upper


@given(counts(minimum=1), CONFIDENCES)
def test_wilson_monotone(count: SuccessCount, confidence: float) -> None:
    previous = wilson_interval(SuccessCount(count.successes - 1, count.trials), confidence)
    current = wilson_interval(count, confidence)
    assert previous.lower <= current.lower
    assert previous.upper <= current.upper


@given(counts(maximum_trials=1000), st.integers(min_value=2, max_value=10), CONFIDENCES)
def test_wilson_narrows(count: SuccessCount, multiplier: int, confidence: float) -> None:
    small = wilson_interval(count, confidence)
    large = wilson_interval(
        SuccessCount(count.successes * multiplier, count.trials * multiplier), confidence
    )
    assert large.upper - large.lower < small.upper - small.lower


@given(counts(), CONFIDENCES, CONFIDENCES)
def test_wilson_nested(count: SuccessCount, first: float, second: float) -> None:
    low, high = sorted((first, second))
    inner, outer = wilson_interval(count, low), wilson_interval(count, high)
    assert outer.lower <= inner.lower
    assert inner.upper <= outer.upper


@given(counts(), CONFIDENCES)
def test_wilson_symmetry(count: SuccessCount, confidence: float) -> None:
    original = wilson_interval(count, confidence)
    reflected = wilson_interval(
        SuccessCount(count.trials - count.successes, count.trials), confidence
    )
    # Complementary float operations can differ by a few ulps.
    assert reflected.lower == pytest.approx(1 - original.upper, abs=1e-12, rel=0)
    assert reflected.upper == pytest.approx(1 - original.lower, abs=1e-12, rel=0)


@given(counts(), counts(), CONFIDENCES)
def test_newcombe_bounds(
    candidate: SuccessCount, baseline: SuccessCount, confidence: float
) -> None:
    interval = newcombe_interval(candidate, baseline, confidence)
    assert -1 <= interval.lower <= candidate.rate - baseline.rate <= interval.upper <= 1


@given(counts(), counts(), CONFIDENCES)
def test_newcombe_antisymmetry(
    candidate: SuccessCount, baseline: SuccessCount, confidence: float
) -> None:
    original = newcombe_interval(candidate, baseline, confidence)
    swapped = newcombe_interval(baseline, candidate, confidence)
    assert swapped.lower == -original.upper
    assert swapped.upper == -original.lower


@given(counts(), CONFIDENCES)
def test_newcombe_identical_contains_zero(count: SuccessCount, confidence: float) -> None:
    interval = newcombe_interval(count, count, confidence)
    assert interval.lower <= 0 <= interval.upper


@given(counts(), counts(), CONFIDENCES, TOLERANCES)
def test_verdict_exact_rule(
    candidate: SuccessCount, baseline: SuccessCount, confidence: float, tolerance: float
) -> None:
    result = decide(candidate, baseline, confidence, tolerance)
    drop = Fraction(baseline.successes, baseline.trials) - Fraction(
        candidate.successes, candidate.trials
    )
    block = newcombe_interval(candidate, baseline, confidence).upper < 0
    assert (result.verdict is Verdict.BLOCK) == block
    assert (result.verdict is Verdict.WARN) == (not block and drop > Fraction(str(tolerance)))


@given(counts(), counts(), CONFIDENCES)
def test_decide_intervals_use_confidence(
    candidate: SuccessCount, baseline: SuccessCount, confidence: float
) -> None:
    result = decide(candidate, baseline, confidence)

    assert result.candidate_interval == wilson_interval(candidate, confidence)
    assert result.baseline_interval == wilson_interval(baseline, confidence)
    assert result.difference_interval == newcombe_interval(candidate, baseline, confidence)


@st.composite
def boundary_counts(draw: DrawFn) -> tuple[SuccessCount, SuccessCount, float]:
    tolerance = draw(st.sampled_from([0.05, 0.1, 0.15, 0.2, 0.25, 0.3]))
    exact = Fraction(str(tolerance))
    # Up to 200 trials, PR-sized: with thousands of trials an exact-tolerance drop is nearly
    # always significant (BLOCK), so the WARN branch, where the float bug lived, is never reached.
    trials = exact.denominator * draw(st.integers(min_value=1, max_value=200 // exact.denominator))
    drop = int(trials * exact)
    successes = draw(st.integers(min_value=drop, max_value=trials))
    return SuccessCount(successes - drop, trials), SuccessCount(successes, trials), tolerance


@given(boundary_counts(), CONFIDENCES)
def test_exact_tolerance_never_warns(
    pair: tuple[SuccessCount, SuccessCount, float], confidence: float
) -> None:
    candidate, baseline, tolerance = pair
    assert decide(candidate, baseline, confidence, tolerance).verdict is not Verdict.WARN


@given(counts(), counts(), CONFIDENCES, TOLERANCES)
def test_improvement_passes(
    first: SuccessCount, second: SuccessCount, confidence: float, tolerance: float
) -> None:
    baseline, candidate = sorted((first, second), key=lambda c: Fraction(c.successes, c.trials))
    assert decide(candidate, baseline, confidence, tolerance).verdict is Verdict.PASS


@given(counts(minimum=1), counts(), CONFIDENCES, TOLERANCES)
def test_candidate_verdict_monotone(
    candidate: SuccessCount, baseline: SuccessCount, confidence: float, tolerance: float
) -> None:
    previous = SuccessCount(candidate.successes - 1, candidate.trials)
    order = {Verdict.BLOCK: 0, Verdict.WARN: 1, Verdict.PASS: 2}
    assert (
        order[decide(previous, baseline, confidence, tolerance).verdict]
        <= order[decide(candidate, baseline, confidence, tolerance).verdict]
    )


@given(st.integers(max_value=0))
def test_non_positive_trials_rejected(trials: int) -> None:
    with pytest.raises(ValueError, match="trials must be positive"):
        SuccessCount(0, trials)


@given(st.integers(min_value=1, max_value=10_000), st.integers(min_value=1))
def test_outside_successes_rejected(trials: int, excess: int) -> None:
    for successes in (-excess, trials + excess):
        with pytest.raises(ValueError, match="successes must be in"):
            SuccessCount(successes, trials)


@given(st.one_of(st.floats(), st.booleans(), st.text(), st.none()))
def test_non_integer_counts_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="successes must be an int"):
        # Wrong argument types are the point of this runtime validation test.
        SuccessCount(value, 5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="trials must be an int"):
        # Wrong argument types are the point of this runtime validation test.
        SuccessCount(0, value)  # type: ignore[arg-type]


INVALID_CONFIDENCES = st.one_of(
    st.floats(max_value=0), st.floats(min_value=1), st.just(float("nan"))
)


@given(counts(), INVALID_CONFIDENCES)
def test_invalid_confidence_rejected(count: SuccessCount, confidence: float) -> None:
    for operation in (
        lambda: wilson_interval(count, confidence),
        lambda: newcombe_interval(count, count, confidence),
        lambda: decide(count, count, confidence),
    ):
        with pytest.raises(ValueError, match=r"confidence must be in \(0, 1\)"):
            operation()


@given(st.one_of(st.floats(max_value=-5e-324), st.sampled_from([float("nan"), float("inf")])))
def test_invalid_tolerance_rejected(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance must be"):
        decide(SuccessCount(1, 2), SuccessCount(1, 2), tolerance=tolerance)
