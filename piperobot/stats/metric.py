"""Continuous metric summaries using Hyndman-Fan type 7 linear quantiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

from piperobot.results import EvalResults


def _quantile(values: list[float], q: float) -> float:
    h = (len(values) - 1) * q
    lo, hi = math.floor(h), math.ceil(h)
    return values[lo] * (1 - (h - lo)) + values[hi] * (h - lo)


@dataclass(frozen=True)
class MetricSummary:
    count: int
    median: float
    p90: float
    iqr: float

    @classmethod
    def from_results(cls, results: EvalResults) -> MetricSummary | None:
        values = sorted(e.metric for e in results.episodes if e.metric is not None)
        if not values:
            return None
        return cls(
            len(values),
            _quantile(values, 0.5),
            _quantile(values, 0.9),
            _quantile(values, 0.75) - _quantile(values, 0.25),
        )


def threshold_near_median(summary: MetricSummary, threshold: float) -> bool:
    return abs(threshold - summary.median) <= summary.iqr
