from __future__ import annotations

import random

import pytest

from piperobot.stats.gate import (
    Interval,
    SuccessCount,
    Verdict,
    decide,
    format_percent,
    format_result,
    main,
    newcombe_interval,
    wilson_interval,
)

EPISODES = 50
SIMULATIONS = 2000


def _approx(interval: Interval, lower: float, upper: float) -> None:
    assert interval.lower == pytest.approx(lower, abs=1e-4)
    assert interval.upper == pytest.approx(upper, abs=1e-4)


def _simulate(rng: random.Random, rate: float, trials: int = EPISODES) -> SuccessCount:
    return SuccessCount(rng.binomialvariate(trials, rate), trials)


# --- SuccessCount -----------------------------------------------------------------------------


def test_parse_success_count() -> None:
    count = SuccessCount.parse("38/50")

    assert count == SuccessCount(38, 50)
    assert count.rate == 0.76
    assert str(count) == "38/50"


def test_parse_requires_separator() -> None:
    with pytest.raises(ValueError, match="expected 'successes/trials'"):
        SuccessCount.parse("38")


@pytest.mark.parametrize("text", ["a/50", "38/"])
def test_parse_rejects_malformed_text(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - message comes from int() or our own check
        SuccessCount.parse(text)


@pytest.mark.parametrize(("successes", "trials"), [(1, 0), (-1, 10), (11, 10)])
def test_success_count_rejects_impossible_values(successes: int, trials: int) -> None:
    with pytest.raises(ValueError, match="must be"):
        SuccessCount(successes, trials)


@pytest.mark.parametrize(("successes", "trials"), [(2.5, 5), (2, 5.0), (True, 5), (0, True)])
def test_success_count_rejects_non_integer_values(successes: object, trials: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        # Wrong argument types are the point of this runtime validation test.
        SuccessCount(successes, trials)  # type: ignore[arg-type]


# --- Intervals: published reference values (Newcombe 1998) -------------------------------------


def test_wilson_matches_published_example() -> None:
    _approx(wilson_interval(SuccessCount(81, 263)), 0.2553, 0.3662)


def test_wilson_stays_inside_unit_interval_at_the_edges() -> None:
    zero = wilson_interval(SuccessCount(0, 10))
    full = wilson_interval(SuccessCount(10, 10))

    assert zero.lower == 0.0
    assert zero.upper == pytest.approx(0.2775, abs=1e-4)
    assert full.lower == pytest.approx(0.7225, abs=1e-4)
    assert full.upper == 1.0


def test_wilson_narrows_with_more_episodes() -> None:
    small = wilson_interval(SuccessCount(40, 50))
    large = wilson_interval(SuccessCount(400, 500))

    assert large.upper - large.lower < small.upper - small.lower


@pytest.mark.parametrize(
    ("candidate", "baseline", "lower", "upper"),
    [
        (SuccessCount(56, 70), SuccessCount(48, 80), 0.0524, 0.3339),
        (SuccessCount(9, 10), SuccessCount(3, 10), 0.1705, 0.8090),
    ],
)
def test_newcombe_matches_published_examples(
    candidate: SuccessCount, baseline: SuccessCount, lower: float, upper: float
) -> None:
    _approx(newcombe_interval(candidate, baseline), lower, upper)


def test_confidence_must_be_a_probability() -> None:
    with pytest.raises(ValueError, match="confidence"):
        wilson_interval(SuccessCount(5, 10), confidence=1.0)


# --- Verdict rule -----------------------------------------------------------------------------


def test_identical_results_pass() -> None:
    result = decide(SuccessCount(40, 50), SuccessCount(40, 50))

    assert result.verdict is Verdict.PASS
    assert result.difference == 0.0


def test_improvement_passes() -> None:
    assert decide(SuccessCount(48, 50), SuccessCount(40, 50)).verdict is Verdict.PASS


def test_pass_reason_when_the_interval_includes_zero() -> None:
    result = decide(SuccessCount(40, 50), SuccessCount(40, 50))

    assert result.reason == (
        "No significant difference: difference interval "
        f"{result.difference_interval} includes zero."
    )


def test_pass_reason_when_the_candidate_is_significantly_better() -> None:
    # The first nightly: 309/500 on fresh seeds against the stored 265/500.
    result = decide(SuccessCount(309, 500), SuccessCount(265, 500))

    assert result.verdict is Verdict.PASS
    assert result.difference_interval.lower > 0
    assert result.reason == (
        "No regression: the candidate is significantly better; difference interval "
        f"{result.difference_interval} is entirely above zero."
    )
    assert str(result.difference_interval) == "[0.027, 0.148]"


def test_large_drop_blocks() -> None:
    result = decide(SuccessCount(25, 50), SuccessCount(45, 50))

    assert result.verdict is Verdict.BLOCK
    assert result.difference_interval.upper < 0
    assert "Regression" in result.reason


def test_small_non_significant_drop_warns() -> None:
    result = decide(SuccessCount(34, 50), SuccessCount(40, 50))

    assert result.verdict is Verdict.WARN
    assert result.difference_interval.lower < 0 < result.difference_interval.upper
    assert result.reason == (
        "Success rate dropped 12.0 pp (more than the 10 pp tolerance), "
        "but it is not significant: "
        f"the difference interval {result.difference_interval} includes zero. "
        "Run more episodes to tell."
    )


def test_warn_reason_uses_custom_tolerance() -> None:
    # 0.55 rather than 0.15: a scale slip (x 101) would still print 15, but prints 56 here.
    result = decide(SuccessCount(0, 3), SuccessCount(2, 3), tolerance=0.55)

    assert result.verdict is Verdict.WARN
    assert "(more than the 55 pp tolerance)" in result.reason


def test_drop_within_tolerance_passes() -> None:
    assert decide(SuccessCount(36, 50), SuccessCount(40, 50)).verdict is Verdict.PASS


@pytest.mark.parametrize(("candidate", "baseline"), [(35, 40), (40, 45)])
def test_exact_tolerance_drop_passes(candidate: int, baseline: int) -> None:
    assert decide(SuccessCount(candidate, 50), SuccessCount(baseline, 50)).verdict is Verdict.PASS


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_tolerance_is_rejected(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance must be finite"):
        decide(SuccessCount(40, 50), SuccessCount(40, 50), tolerance=tolerance)


def test_same_drop_blocks_with_enough_episodes() -> None:
    # 80% -> 72% is not significant with 50 episodes but it is with 1000.
    assert decide(SuccessCount(36, 50), SuccessCount(40, 50)).verdict is not Verdict.BLOCK
    assert decide(SuccessCount(720, 1000), SuccessCount(800, 1000)).verdict is Verdict.BLOCK


def test_negative_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="tolerance"):
        decide(SuccessCount(40, 50), SuccessCount(40, 50), tolerance=-0.1)


# --- Statistical behaviour (seeded Monte Carlo, deterministic) --------------------------------


@pytest.mark.parametrize("rate", [0.5, 0.8, 0.95])
def test_wilson_coverage_is_close_to_nominal(rate: float) -> None:
    rng = random.Random(1234)
    covered = 0
    for _ in range(SIMULATIONS):
        interval = wilson_interval(_simulate(rng, rate))
        covered += interval.lower <= rate <= interval.upper

    assert 0.92 <= covered / SIMULATIONS <= 0.98


@pytest.mark.parametrize("rate", [0.8, 0.9])
def test_false_block_rate_is_low_when_policy_is_unchanged(rate: float) -> None:
    # A flaky gate would block good PRs; with 95% confidence we expect ~2.5% at most.
    rng = random.Random(42)
    blocks = sum(
        decide(_simulate(rng, rate), _simulate(rng, rate)).verdict is Verdict.BLOCK
        for _ in range(SIMULATIONS)
    )

    assert blocks / SIMULATIONS <= 0.04


def test_deliberately_broken_policy_is_blocked() -> None:
    # Phase 0 acceptance scenario: baseline 80%, sabotaged candidate 50%, 50 episodes each.
    rng = random.Random(7)
    blocks = sum(
        decide(_simulate(rng, 0.5), _simulate(rng, 0.8)).verdict is Verdict.BLOCK
        for _ in range(SIMULATIONS)
    )

    assert blocks / SIMULATIONS >= 0.85


# --- CLI --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.1, "10"),
        (0.125, "12.5"),
        (0.15, "15"),
        (0.55, "55"),
        (0.95, "95"),
        (0.975, "97.5"),
        (0.333, "33.3"),
        (0.0, "0"),
        (1e-5, "0.001"),
        (1e-9, "0.0000001"),  # without the "f" format, Decimal switches to "1.00E-7"
        (1e16, "1000000000000000000"),  # no decimal point: trailing zeros must stay
    ],
)
def test_format_percent(fraction: float, expected: str) -> None:
    assert format_percent(fraction) == expected


def test_warn_reason_preserves_fractional_tolerance() -> None:
    result = decide(SuccessCount(33, 50), SuccessCount(40, 50), tolerance=0.125)

    assert result.verdict is Verdict.WARN
    assert "12.5 pp tolerance" in result.reason


def test_block_reason_preserves_fractional_confidence() -> None:
    result = decide(SuccessCount(25, 50), SuccessCount(45, 50), confidence=0.975)

    assert result.verdict is Verdict.BLOCK
    assert "the 97.5% interval" in result.reason


def test_main_help(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert (
        "Compare a candidate policy's success rate against the stored baseline and decide the gate."
        in output
    )
    for option, help_text in (
        ("--candidate CANDIDATE", "Counts, e.g. 38/50"),
        ("--results RESULTS", "Evaluation results JSON"),
        ("--baseline BASELINE", "Counts, e.g. 45/50"),
        ("--baseline-file BASELINE_FILE", "Stored baseline JSON"),
        (
            "--tolerance TOLERANCE",
            "Observed drop (as a fraction) above which a non-significant result is a WARN",
        ),
    ):
        assert f"{option} {help_text} " in f"{output} "


def test_format_result_lines() -> None:
    result = decide(SuccessCount(34, 50), SuccessCount(40, 50))

    assert format_result(result).splitlines() == [
        "Candidate:  34/50 = 68.0%  CI [0.542, 0.792]",
        "Baseline:   40/50 = 80.0%  CI [0.670, 0.888]",
        "Difference: -12.0%  CI [-0.284, 0.052]",
        "Verdict:    WARN",
        result.reason,
    ]


def test_main_custom_tolerance(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--candidate", "34/50", "--baseline", "40/50"]

    assert main(args) == 0
    assert "Verdict:    WARN" in capsys.readouterr().out
    assert main([*args, "--tolerance", "0.15"]) == 0
    assert "Verdict:    PASS" in capsys.readouterr().out


def test_main_custom_confidence(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--candidate", "34/50", "--baseline", "40/50"]

    assert main(args) == 0
    assert "Verdict:    WARN" in capsys.readouterr().out
    assert main([*args, "--confidence", "0.8"]) == 1
    output = capsys.readouterr().out
    assert "Verdict:    BLOCK" in output
    assert "the 80% interval of the difference [-0.229, -0.007]" in output


def test_main_exit_code_is_1_on_block(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--candidate", "25/50", "--baseline", "45/50"]) == 1
    assert "Verdict:    BLOCK" in capsys.readouterr().out


def test_main_exit_code_is_0_on_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--candidate", "45/50", "--baseline", "45/50"]) == 0
    assert "Verdict:    PASS" in capsys.readouterr().out
