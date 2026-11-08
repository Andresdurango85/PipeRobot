"""Metric table shared by the two PR comment renderers."""

from collections.abc import Callable, Sequence

from piperobot.results import MetricSpec
from piperobot.stats.metric import MetricSummary, threshold_near_median


def metric_section(
    runs: Sequence[tuple[str, MetricSummary | None]],
    spec: MetricSpec | None,
    escape: Callable[[str], str],
) -> list[str]:
    present = [(run, summary) for run, summary in runs if summary is not None]
    if not present:
        return []
    name = escape(spec.name) if spec else "Metric"
    unit = escape(spec.unit) if spec and spec.unit else ""
    lines = [
        "",
        f"### {name}" + (f" ({unit})" if unit else ""),
        "",
        "| Run | Median | p90 | IQR |",
        "| --- | ---: | ---: | ---: |",
    ]
    for run, summary in present:
        lines.append(f"| {run} | {summary.median:.4g} | {summary.p90:.4g} | {summary.iqr:.4g} |")
    if spec:
        suffix = f" {unit}" if unit else ""
        lines += ["", f"Success when {name} is {spec.success_when} {spec.threshold:.4g}{suffix}."]
        for run, summary in present:
            if threshold_near_median(summary, spec.threshold):
                lines += [
                    "",
                    "> **Warning:** the threshold lies within one IQR of the "
                    f"{run.lower()} median, so the success rate is sensitive to "
                    f"small shifts in {name}.",
                ]
    return lines
