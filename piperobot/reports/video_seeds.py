"""Select reproducible failed episodes for optional video evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, TypedDict

from piperobot.results import EvalResults, load_results
from piperobot.stats.paired import PairedCounts


class VideoSeed(TypedDict):
    seed: int
    kind: Literal["lost", "failed"]


@dataclass(frozen=True)
class VideoSelection:
    seeds: list[VideoSeed]
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "seeds": self.seeds,
            "reason": self.reason,
            "seed_list": ",".join(str(item["seed"]) for item in self.seeds),
        }


def select_video_seeds(
    reference: EvalResults | None, candidate: EvalResults, cap: int = 5
) -> VideoSelection:
    if cap < 0:
        raise ValueError("cap must be non-negative")
    if reference is None:
        return VideoSelection([], "No baseline; nothing recorded.")
    # A baseline may cover more seeds than the gate runs (e.g. a larger pool); pair on the
    # candidate's seeds only, and record nothing if the baseline lacks some of them.
    wanted = {episode.seed for episode in candidate.episodes}
    if not wanted <= {episode.seed for episode in reference.episodes}:
        return VideoSelection([], "The baseline lacks some candidate seeds; nothing recorded.")
    reference = replace(
        reference, episodes=tuple(e for e in reference.episodes if e.seed in wanted)
    )
    counts = PairedCounts.from_results(reference, candidate)
    if counts.reference_only == 0:
        return VideoSelection([], "No lost episodes; nothing recorded.")
    successes = {episode.seed for episode in reference.episodes if episode.success}
    failures = sorted(episode.seed for episode in candidate.failed)
    kinds: tuple[Literal["lost", "failed"], ...] = ("lost", "failed")
    seeds: list[VideoSeed] = [
        {"seed": seed, "kind": kind}
        for kind in kinds
        for seed in failures
        if (seed in successes) == (kind == "lost")
    ]
    return VideoSelection(seeds[: min(cap, 5)])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    selection = select_video_seeds(
        load_results(args.reference) if args.reference else None, load_results(args.candidate)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selection.to_dict(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
