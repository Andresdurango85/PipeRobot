"""Render the registered repeatability study from portable JSON runs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from isaac_demo_replay import ENV, load_module

RULES = load_module("repeatability_rules", ENV / "repeatability.py")


def report(paths: Sequence[Path], out_dir: Path) -> dict:
    groups = defaultdict(list)
    worker = False
    for path in paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        groups[run["metadata"]["config_label"]].append(run)
        metadata = run["metadata"]
        worker |= any(
            item.get("runner_worker_start") or item.get("runner_worker_end")
            for item in [metadata, *metadata.get("child_metadata", [])]
        )
    summaries = {label: RULES.compare_runs(runs) for label, runs in groups.items()}
    order = None
    if "a" in groups and "a_rev" in groups:
        if len(groups["a_rev"]) != 1:
            raise ValueError("Expected exactly one reverse run")
        order = RULES.order_test(groups["a"], groups["a_rev"][0])
    shifts = {
        label: RULES.shift_vs_a(runs, groups["a"])
        for label, runs in groups.items()
        if "a" in groups and RULES.repeatable(summaries[label])
    }
    payload = {
        "configs": summaries,
        "order_test": order,
        "decision": RULES.decide(groups),
        "shifts_vs_a": shifts,
        "rules": RULES.DECISION_RULES,
        "runner_worker_observed": worker,
    }
    lines = [
        "# Same-seed repeatability study",
        "",
        "| Config | Runs | Episodes | Outcome flips | Flip rate | Bit-identical | "
        "Max step spread | Mean wall s/episode |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, summary in summaries.items():
        keys = (
            "runs",
            "episodes",
            "outcome_flips",
            "flip_rate",
            "bit_identical",
            "max_success_step_spread",
            "mean_wall_seconds_per_episode",
        )
        lines.append(f"| {label} | " + " | ".join(str(summary[k]) for k in keys) + " |")
    lines.extend(
        [
            "",
            "## Order test",
            "",
            RULES.H1,
            "",
            "```json",
            json.dumps(order, indent=2),
            "```",
            "",
            "## Decision",
            "",
            "```json",
            json.dumps(payload["decision"], indent=2),
            "```",
            "",
            "## Shifts vs a",
            "",
            "```json",
            json.dumps(shifts, indent=2),
            "```",
            "",
            "## Registered rules",
            "",
            RULES.DECISION_RULES,
            "",
        ]
    )
    if worker:
        lines.extend(["Runner.Worker.exe was running during at least one run boundary.", ""])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report(args.runs, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
