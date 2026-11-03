"""Record a baseline and guard paired comparisons against platform changes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from piperobot.results import EvalResults, load_results

GUARDED_KEYS = (
    "gpu",
    "cuda_version",
    "driver_version",
    "torch_version",
    "isaac_lab_version",
    "device",
    "options",
)


def baseline_record(
    results: EvalResults, metadata: Mapping[str, Any], *, seeds: str, run_url: str | None
) -> dict[str, Any]:
    platform = metadata.get("platform")
    if not isinstance(platform, Mapping):
        raise ValueError("run platform is missing")
    if metadata.get("platform_differences"):
        raise ValueError("run platform_differences is non-empty")
    return {
        "policy": results.policy,
        "evaluator": "isaaclab",
        "successes": results.successes,
        "trials": results.trials,
        "seeds": seeds,
        "commit": metadata.get("git_commit"),
        "platform": {key: platform.get(key) for key in GUARDED_KEYS},
        "updated": datetime.now(UTC).date().isoformat(),
        "how": "Recorded from Isaac Lab evaluation" + (f": {run_url}" if run_url else "."),
    }


def platform_mismatches(baseline: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[str]:
    reference = baseline.get("platform")
    if not isinstance(reference, Mapping):
        raise ValueError("baseline platform is missing")
    lines = []
    if metadata.get("platform_differences"):
        lines.append("run platform_differences is non-empty")
    platform = metadata.get("platform")
    if not isinstance(platform, Mapping):
        lines.append("run platform is missing")
        return lines
    for key in GUARDED_KEYS:
        if reference.get(key) != platform.get(key):
            lines.append(f"{key}: baseline {reference.get(key)}, run {platform.get(key)}")
    return lines


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--results", type=Path, required=True)
    record.add_argument("--seeds", required=True)
    record.add_argument("--run-url")
    record.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--baseline", type=Path, required=True)
    for command in (record, check):
        command.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        metadata = _read(args.metadata)
        if args.command == "record":
            data = baseline_record(
                load_results(args.results), metadata, seeds=args.seeds, run_url=args.run_url
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            lines = platform_mismatches(_read(args.baseline), metadata)
            if lines:
                print("baseline platform mismatch: re-measure the baseline", file=sys.stderr)
                print("\n".join(lines), file=sys.stderr)
                return 3
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
