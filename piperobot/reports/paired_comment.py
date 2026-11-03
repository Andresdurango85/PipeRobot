"""Render a paired gate verdict as a sticky Markdown comment."""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from piperobot.reports.sticky_comment import validate_marker
from piperobot.results import load_results
from piperobot.stats.gate import Verdict, format_percent
from piperobot.stats.paired import PairedCounts, PairedResult, decide_paired


def _escape(text: str) -> str:
    text = " ".join(text.split())
    return re.sub(r"([\\`*_{}\[\]()#+.!|~>-])", r"\\\1", html.escape(text))


def render_paired_comment(
    result: PairedResult,
    *,
    marker: str,
    title: str,
    run_url: str | None,
    commit: str | None,
    failed_seeds: Sequence[int],
) -> str:
    """Build a comment; the exact test decides, the interval only reports scale."""
    validate_marker(marker)
    emoji = {Verdict.PASS: "✅", Verdict.WARN: "⚠️", Verdict.BLOCK: "❌"}[result.verdict]
    counts = result.counts
    interval = result.difference_interval
    seeds = sorted(failed_seeds)
    if any(type(seed) is not int for seed in seeds):
        raise ValueError("failed seeds must be integers")
    failures = ", ".join(str(seed) for seed in seeds[:30]) or "None"
    if len(seeds) > 30:
        failures += f" … and {len(seeds) - 30} more"
    lines = [
        marker,
        f"## {emoji} {_escape(title)}: {result.verdict.value.upper()}",
        "",
        "| Measurement | Value |",
        "| --- | ---: |",
        f"| Reference | {counts.reference} ({counts.reference.rate:.1%}) |",
        f"| Candidate | {counts.candidate} ({counts.candidate.rate:.1%}) |",
        f"| Episodes lost / gained | {counts.reference_only} / {counts.candidate_only} |",
        f"| Exact McNemar p | {result.p_value:.6g} |",
        f"| Difference (candidate - reference) | {result.difference * 100:+.1f} pp |",
        f"| {format_percent(1 - 2 * result.alpha)}% paired CI | "
        f"{interval.lower * 100:+.1f} to {interval.upper * 100:+.1f} pp |",
        "",
        _escape(result.reason),
        "",
        f"**Candidate failed seeds:** {failures}",
        "",
        "<details><summary>How to read this verdict</summary>",
        "",
        "The reference and candidate run on the same seeds on the same runner. "
        "Only discordant episodes count in the exact McNemar test: episodes lost by "
        "the candidate or gained over the reference. Shared successes and failures "
        "provide no evidence of a difference.",
        "",
        f"- **BLOCK**: exact one-sided p < {result.alpha:g}.",
        f"- **WARN**: not significant, but the drop exceeds "
        f"{format_percent(result.tolerance)} pp; more episodes are needed.",
        "- **PASS**: no regression detected.",
        "",
        "The paired confidence interval reports the size of the difference; it does not decide.",
        "",
        "</details>",
    ]
    footer = []
    if commit:
        footer.append(f"commit {_escape(commit)}")
    if run_url:
        if urlsplit(run_url).scheme not in {"https", "http"}:
            raise ValueError("run URL must use HTTP or HTTPS")
        # Encode delimiters before placing the URL inside a Markdown link.
        from urllib.parse import quote

        footer.append(f"[Workflow run]({html.escape(quote(run_url, safe=':/-=&%'))})")
    if footer:
        lines += ["", " · ".join(footer)]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--run-url")
    parser.add_argument("--commit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        reference, candidate = load_results(args.reference), load_results(args.candidate)
        result = decide_paired(PairedCounts.from_results(reference, candidate))
        comment = render_paired_comment(
            result,
            marker=args.marker,
            title=args.title,
            run_url=args.run_url,
            commit=args.commit,
            failed_seeds=[episode.seed for episode in candidate.episodes if not episode.success],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(comment, encoding="utf-8", newline="\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 1 if result.verdict is Verdict.BLOCK else 0


if __name__ == "__main__":
    sys.exit(main())
