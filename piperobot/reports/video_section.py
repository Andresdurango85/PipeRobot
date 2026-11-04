"""Render the separate sticky comment for optional video evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

VIDEO_MARKER = "<!-- piperobot-gate:so101-videos -->"
NOTHING_SELECTED = (
    "No lost episodes; nothing recorded (the baseline's own failures are not re-recorded)."
)
UNFINISHED = "Videos not recorded: the recording job did not finish (the verdict is unaffected)."


def render_video_section(
    selection: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    job_result: str = "success",
    artifact_url: str = "",
    *,
    commit: str = "",
    run_url: str = "",
    memory_skip_free_gib: float | None = None,
    memory_needed_gib: float | None = None,
) -> str:
    commit_url = run_url.split("/actions/runs/", 1)[0] + f"/commit/{commit}"
    lines = [
        VIDEO_MARKER,
        "## SO-101 failed-episode videos",
        "",
        f"Commit: [{commit[:7]}](<{commit_url}>) | [Workflow run](<{run_url}>)",
        "",
    ]
    if memory_skip_free_gib is not None:
        lines.append(
            "Videos not recorded: not enough host memory "
            f"(free commit {memory_skip_free_gib:.1f} GiB, needs {memory_needed_gib:.1f} GiB)."
        )
    elif not selection.get("seeds") and job_result in {"success", "skipped"}:
        reason = selection.get("reason")
        lines.append(reason if reason and "baseline" in reason.lower() else NOTHING_SELECTED)
    elif job_result != "success" or manifest is None:
        lines.append(UNFINISHED)
    else:
        lines += [
            "Recording results (the verdict is unaffected).",
            "",
            "| Seed | Kind | Video status |",
            "| --- | --- | --- |",
        ]
        entries = {entry["seed"]: entry for entry in manifest["seeds"]}
        for item in selection["seeds"]:
            entry = entries.get(item["seed"], {})
            status = entry.get("status")
            message = "recording missing; no video"
            if status == "diverged":
                message = "re-run diverged from the judged episode; no video"
            elif status == "matched" and entry.get("frames", 0) > 0 and artifact_url:
                message = "in artifact"
            lines.append(f"| {item['seed']} | {item['kind']} | {message} |")
        if artifact_url:
            lines += [
                "",
                f"Download: [so101-videos](<{artifact_url}>) (simulation only, kept 7 days)",
            ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--job-result", required=True)
    parser.add_argument("--artifact-url", default="")
    parser.add_argument("--memory-skip-free-gib", type=float)
    parser.add_argument("--memory-needed-gib", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.memory_skip_free_gib is None) != (args.memory_needed_gib is None):
        parser.error("both memory numbers are required")
    section = render_video_section(
        json.loads(args.selection.read_text(encoding="utf-8-sig")),
        json.loads(args.manifest.read_text(encoding="utf-8-sig")) if args.manifest else None,
        args.job_result,
        args.artifact_url,
        commit=args.commit,
        run_url=args.run_url,
        memory_skip_free_gib=args.memory_skip_free_gib,
        memory_needed_gib=args.memory_needed_gib,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(section, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
