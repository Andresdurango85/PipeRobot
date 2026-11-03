from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from piperobot.results import EpisodeResult, EvalResults, ResultsError, save_results
from piperobot.stats.gate import Verdict, newcombe_interval
from piperobot.stats.paired import (
    PairedCounts,
    decide_paired,
    exact_mcnemar_p,
    format_paired_result,
    main,
    newcombe_paired_interval,
)


@pytest.mark.parametrize(("b", "c", "expected"), [(6, 0, 1 / 64), (5, 0, 1 / 32), (0, 0, 1)])
def test_exact_values(b: int, c: int, expected: float) -> None:
    assert exact_mcnemar_p(b, c) == expected


def test_exact_tail_independent_complement() -> None:
    expected = 1 - sum((Fraction(math.comb(28, k), 2**28) for k in range(20)), Fraction())
    assert exact_mcnemar_p(20, 8) == float(expected)
    assert exact_mcnemar_p(3, 3) > 0.5


@pytest.mark.parametrize(
    ("counts", "verdict"),
    [
        (PairedCounts(494, 6, 0, 0), Verdict.BLOCK),
        (PairedCounts(495, 5, 0, 0), Verdict.PASS),
        (PairedCounts(20, 7, 2, 11), Verdict.WARN),
        (PairedCounts(7, 1, 0, 2), Verdict.PASS),
    ],
)
def test_decisions(counts: PairedCounts, verdict: Verdict) -> None:
    # For b=7,c=2, p=(36+9+1)/512=0.08984375 and drop=5/40.
    assert decide_paired(counts).verdict is verdict


def test_threshold_is_strict() -> None:
    assert decide_paired(PairedCounts(0, 5, 0, 495), alpha=1 / 32).verdict is Verdict.PASS


def _results(episodes: list[tuple[int, bool]]) -> EvalResults:
    return EvalResults("policy", "test", tuple(EpisodeResult(*episode) for episode in episodes))


def test_seed_pairing_and_properties() -> None:
    reference = _results([(1, True), (2, True), (3, False), (4, False)])
    candidate = _results([(4, False), (3, True), (2, False), (1, True)])
    counts = PairedCounts.from_results(reference, candidate)
    assert counts == PairedCounts(1, 1, 1, 1)
    assert counts.trials == 4
    assert counts.discordant == 2
    assert counts.reference.successes == counts.candidate.successes == 2
    identical = decide_paired(PairedCounts.from_results(reference, reference))
    assert identical.verdict is Verdict.PASS
    assert identical.difference == 0


def test_seed_mismatch_names_both_sides() -> None:
    with pytest.raises(
        ResultsError, match=r"missing from reference \[2\]; missing from candidate \[1\]"
    ):
        PairedCounts.from_results(_results([(1, True)]), _results([(2, True)]))


@pytest.mark.parametrize("field", ["both", "reference_only", "candidate_only", "neither"])
@pytest.mark.parametrize("value", [True, 1.0, "1", None, -1])
def test_invalid_counts(field: str, value: object) -> None:
    values = dict.fromkeys(["both", "reference_only", "candidate_only", "neither"], 1)
    values[field] = value  # type: ignore[assignment]
    with pytest.raises((TypeError, ValueError), match=field):
        PairedCounts(**values)


def test_empty_counts() -> None:
    with pytest.raises(ValueError, match="trials"):
        PairedCounts(0, 0, 0, 0)


@pytest.mark.parametrize("value", [-1, True, 1.0])
def test_invalid_mcnemar_counts(value: int) -> None:
    with pytest.raises((TypeError, ValueError), match="reference_only"):
        exact_mcnemar_p(value, 0)
    with pytest.raises((TypeError, ValueError), match="candidate_only"):
        exact_mcnemar_p(0, value)


@pytest.mark.parametrize("alpha", [0.0, 0.5, 1.0, -0.1, float("nan"), float("inf")])
def test_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        decide_paired(PairedCounts(1, 0, 0, 0), alpha=alpha)


@pytest.mark.parametrize("tolerance", [-0.1, float("nan"), float("inf"), -float("inf")])
def test_invalid_tolerance(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        decide_paired(PairedCounts(1, 0, 0, 0), tolerance=tolerance)


SMALL = st.integers(min_value=0, max_value=200)
COUNTS = (
    st.tuples(SMALL, SMALL, SMALL, SMALL)
    .filter(lambda cells: sum(cells) > 0)
    .map(lambda cells: PairedCounts(*cells))
)


@given(SMALL, SMALL)
def test_p_laws(b: int, c: int) -> None:
    p = exact_mcnemar_p(b, c)
    assert 0 <= p <= 1
    if b <= c:
        assert p >= 0.5
    assert exact_mcnemar_p(b + 1, c) <= p
    assert exact_mcnemar_p(b, c + 1) >= p


@given(COUNTS)
def test_block_requires_losses(counts: PairedCounts) -> None:
    if decide_paired(counts).verdict is Verdict.BLOCK:
        assert counts.reference_only > counts.candidate_only


@given(COUNTS, st.floats(min_value=0.5, max_value=0.999))
def test_interval_laws(counts: PairedCounts, confidence: float) -> None:
    swapped = PairedCounts(
        counts.both, counts.candidate_only, counts.reference_only, counts.neither
    )
    original = newcombe_paired_interval(counts, confidence)
    reflected = newcombe_paired_interval(swapped, confidence)
    difference = counts.candidate.rate - counts.reference.rate
    assert -1 <= original.lower <= difference <= original.upper <= 1
    assert reflected.lower == pytest.approx(-original.upper, abs=1e-12, rel=0)
    assert reflected.upper == pytest.approx(-original.lower, abs=1e-12, rel=0)
    assert decide_paired(swapped).difference == -decide_paired(counts).difference


@given(st.integers(1, 100), st.floats(min_value=0.5, max_value=0.999))
def test_zero_phi_matches_unpaired(scale: int, confidence: float) -> None:
    # ad=bc gives phi=0 with a nonzero denominator.
    counts = PairedCounts(2 * scale, scale, 2 * scale, scale)
    paired = newcombe_paired_interval(counts, confidence)
    independent = newcombe_interval(counts.candidate, counts.reference, confidence)
    assert paired.lower == pytest.approx(independent.lower, abs=1e-12, rel=0)
    assert paired.upper == pytest.approx(independent.upper, abs=1e-12, rel=0)


@pytest.mark.parametrize("counts", [PairedCounts(0, 1, 2, 0), PairedCounts(1, 0, 0, 0)])
def test_degenerate_intervals(counts: PairedCounts) -> None:
    interval = newcombe_paired_interval(counts)
    assert (
        -1 <= interval.lower <= counts.candidate.rate - counts.reference.rate <= interval.upper <= 1
    )


def test_report() -> None:
    result = decide_paired(PairedCounts(20, 7, 2, 11))
    output = format_paired_result(result)
    assert "Candidate:  22/40 = 55.0%" in output
    assert "Reference:  27/40 = 67.5%" in output
    assert "Difference: -12.5 pp" in output
    assert "Verdict:    WARN" in output
    assert "7 episodes lost, 2 gained" in result.reason
    assert result.difference_interval == newcombe_paired_interval(
        result.counts, 1 - 2 * result.alpha
    )


@pytest.mark.parametrize(("lost", "code"), [(0, 0), (5, 0), (6, 1)])
def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str], lost: int, code: int) -> None:
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    save_results(_results([(seed, True) for seed in range(10)]), reference)
    save_results(_results([(seed, seed >= lost) for seed in range(10)]), candidate)
    assert main(["--reference", str(reference), "--candidate", str(candidate)]) == code
    assert "Verdict:" in capsys.readouterr().out
    assert (
        main(["--reference", str(reference), "--candidate", str(candidate), "--alpha", "nan"]) == 2
    )
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["--alpha", "x"], ["--unknown"]])
def test_argument_errors(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(args) == 2
    assert "ERROR:" in capsys.readouterr().err


def test_cli_invalid_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "missing.json"
    assert main(["--reference", str(path), "--candidate", str(path)]) == 2
    assert "ERROR:" in capsys.readouterr().err
    path.write_text("{", encoding="utf-8")
    assert main(["--reference", str(path), "--candidate", str(path)]) == 2
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize("counts", [PairedCounts(0, 0, 2, 3), PairedCounts(4, 0, 0, 0)])
def test_zero_denominator_matches_unpaired(counts: PairedCounts) -> None:
    paired = newcombe_paired_interval(counts)
    independent = newcombe_interval(counts.candidate, counts.reference)
    assert paired.lower == pytest.approx(independent.lower, abs=1e-12, rel=0)
    assert paired.upper == pytest.approx(independent.upper, abs=1e-12, rel=0)


def test_cli_mismatched_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    save_results(_results([(1, True)]), reference)
    save_results(_results([(2, True)]), candidate)
    assert main(["--reference", str(reference), "--candidate", str(candidate)]) == 2
    assert "seed sets differ" in capsys.readouterr().err
