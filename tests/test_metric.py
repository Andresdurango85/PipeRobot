from __future__ import annotations

import pytest

from piperobot.results import EpisodeResult, EvalResults
from piperobot.stats.metric import MetricSummary, threshold_near_median


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([7.0], MetricSummary(1, 7, 7, 0)),
        ([0.0, 10.0], MetricSummary(2, 5, 9, 5)),
        ([10.0, 0.0, 6.0, 2.0, 4.0], MetricSummary(5, 4, 8.4, 4)),
    ],
)
def test_summary(values: list[float], expected: MetricSummary) -> None:
    results = EvalResults(
        "p", "e", tuple(EpisodeResult(i, True, metric=v) for i, v in enumerate(values))
    )
    assert MetricSummary.from_results(results) == expected


def test_no_metric() -> None:
    assert MetricSummary.from_results(EvalResults("p", "e", (EpisodeResult(0, True),))) is None


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        (3.0, True),
        (7.0, True),
        (5.0, True),
        (2.999, False),
        (7.001, False),
    ],
)
def test_warning_boundary(threshold: float, expected: bool) -> None:
    assert threshold_near_median(MetricSummary(4, 5, 8, 2), threshold) is expected


def test_zero_iqr() -> None:
    assert threshold_near_median(MetricSummary(1, 2, 2, 0), 2)
    assert not threshold_near_median(MetricSummary(1, 2, 2, 0), 2.001)
