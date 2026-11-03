"""Plan reproducible daily seed ranges using only the standard library."""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path


def rotating_first_seed(
    day: date, episodes: int, base: int = 100000, epoch: date = date(2026, 1, 1)
) -> int:
    """Return the start of a daily, non-overlapping range for a fixed episode count."""
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    if day < epoch:
        raise ValueError("day must be on or after epoch")
    return base + episodes * (day - epoch).days


def main() -> int:
    """Validate environment inputs and print today's plan for GitHub Actions."""
    try:
        raw_episodes = os.environ.get("EPISODES", "") or "500"
        raw_seed = os.environ.get("FIRST_SEED", "")
        if not re.fullmatch(r"[0-9]+", raw_episodes):
            raise ValueError("episodes must be a positive integer <= 1000")
        episodes = int(raw_episodes)
        if not 1 <= episodes <= 1000:
            raise ValueError("episodes must be a positive integer <= 1000")
        if raw_seed and not re.fullmatch(r"[0-9]+", raw_seed):
            raise ValueError("first_seed must be a non-negative integer")
        seed = (
            int(raw_seed) if raw_seed else rotating_first_seed(datetime.now(UTC).date(), episodes)
        )
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"episodes={episodes}\nseed={seed}")
    summary = f"Nightly: {episodes} episodes, seeds {seed}-{seed + episodes - 1}"
    if output := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(summary + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
