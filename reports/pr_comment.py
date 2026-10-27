"""Render the gate result as the Markdown comment posted on the pull request.

The comment starts with a hidden marker so the workflow can find and update its own previous
comment on every push instead of adding a new one.

Usage:
    uv run python -m reports.pr_comment --candidate 25/50 --baseline 45/50
    uv run python -m reports.pr_comment --results out/results.json \\
        --baseline-file stats/baseline.json --run-url "$RUN_URL" --commit "$HEAD_SHA"

With ``--results``, failed episodes (seed, scene, failure, video) come from the results file.
Exit codes: 0 rendered (whatever the verdict; `stats.gate` decides the merge), 2 invalid inputs.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from eval.results import EpisodeResult
from stats.cli_inputs import InputError, add_input_arguments, resolve_inputs
from stats.gate import (
    DEFAULT_CONFIDENCE,
    DEFAULT_TOLERANCE,
    GateResult,
    Interval,
    Verdict,
    decide,
)

COMMENT_MARKER = "<!-- piperobot-gate -->"
MAX_FAILED_LISTED = 10

VERDICT_HEADINGS = {
    Verdict.PASS: "✅ PipeRobot gate: PASS",
    Verdict.WARN: "⚠️ PipeRobot gate: WARN",
    Verdict.BLOCK: "❌ PipeRobot gate: BLOCK",
}


def _cell(text: str | None) -> str:
    """Make text safe inside a Markdown table cell."""
    if not text:
        return "—"
    return " ".join(text.split()).replace("|", "\\|")


def _rate_interval(interval: Interval) -> str:
    return f"{interval.lower:.1%} to {interval.upper:.1%}"


def _points(value: float) -> str:
    return f"{value * 100:+.1f} pp"


def _results_table(result: GateResult, commit: str | None) -> list[str]:
    confidence = f"{result.confidence:.0%} CI"
    candidate_label = f"Candidate (`{commit[:7]}`)" if commit else "Candidate"
    diff = result.difference_interval
    return [
        f"| | Episodes | Success rate | {confidence} |",
        "| --- | ---: | ---: | ---: |",
        f"| {candidate_label} | {result.candidate} | {result.candidate.rate:.1%} "
        f"| {_rate_interval(result.candidate_interval)} |",
        f"| Baseline | {result.baseline} | {result.baseline.rate:.1%} "
        f"| {_rate_interval(result.baseline_interval)} |",
        f"| **Difference** | | **{_points(result.difference)}** "
        f"| {_points(diff.lower)} to {_points(diff.upper)} |",
    ]


def _failed_section(
    failed: Sequence[EpisodeResult], total_failed: int, run_url: str | None
) -> list[str]:
    if total_failed == 0:
        return []
    lines = ["", f"### Failed episodes ({total_failed})", ""]
    if not failed:
        return [*lines, "_No per-episode details were provided._"]

    lines += ["| Seed | Scene | Failure | Video |", "| ---: | --- | --- | --- |"]
    shown = sorted(failed, key=lambda episode: episode.seed)[:MAX_FAILED_LISTED]
    for episode in shown:
        video = f"[▶ video]({episode.video_url})" if episode.video_url else "—"
        lines.append(
            f"| {episode.seed} | {_cell(episode.scene)} | {_cell(episode.failure)} | {video} |"
        )
    hidden = total_failed - len(shown)
    if hidden > 0:
        where = f" in the [workflow run]({run_url})" if run_url else " in the workflow artifacts"
        lines += ["", f"_…and {hidden} more{where}._"]
    return lines


def _explanation(result: GateResult) -> list[str]:
    return [
        "",
        "<details><summary>How to read this verdict</summary>",
        "",
        "Each episode is a pass/fail attempt at the task with its own seed and scene variation. "
        f"The {result.confidence:.0%} interval of the difference (candidate - baseline) "
        "accounts for the luck of both runs.",
        "",
        "- **BLOCK**: the whole interval is below zero, so the policy is worse. The PR is blocked.",
        f"- **WARN**: the rate dropped more than {result.tolerance * 100:.0f} pp, but the interval "
        "still includes zero. The PR passes; more episodes are needed to tell.",
        "- **PASS**: no regression detected.",
        "",
        "</details>",
    ]


def render_comment(
    result: GateResult,
    failed_episodes: Sequence[EpisodeResult] = (),
    run_url: str | None = None,
    commit: str | None = None,
) -> str:
    """Build the full Markdown body of the PR comment."""
    total_failed = result.candidate.trials - result.candidate.successes
    if len(failed_episodes) > total_failed:
        raise ValueError(
            f"{len(failed_episodes)} failed episodes given, "
            f"but the candidate only failed {total_failed}"
        )

    lines = [
        COMMENT_MARKER,
        f"## {VERDICT_HEADINGS[result.verdict]}",
        "",
        result.reason,
        "",
        *_results_table(result, commit),
        *_failed_section(failed_episodes, total_failed, run_url),
        *_explanation(result),
    ]
    footer = []
    if run_url:
        footer.append(f"[Workflow run]({run_url})")
    if commit:
        footer.append(f"commit `{commit[:7]}`")
    if footer:
        lines += ["", f"<sub>{' · '.join(footer)}</sub>"]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_input_arguments(parser)
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--run-url", help="Link to the GitHub Actions run")
    parser.add_argument("--commit", help="Commit SHA of the candidate")
    parser.add_argument("--output", type=Path, help="Write the comment here instead of stdout")
    args = parser.parse_args(argv)

    try:
        inputs = resolve_inputs(args)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    result = decide(inputs.candidate, inputs.baseline, args.confidence, args.tolerance)
    comment = render_comment(
        result, inputs.failed_episodes, run_url=args.run_url, commit=args.commit
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(comment, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(comment)
    # The verdict's exit code belongs to `stats.gate`; rendering the comment always succeeds.
    return 0


if __name__ == "__main__":
    sys.exit(main())
