"""Evaluation results: the contract between an evaluator and the gate.

Any evaluator (the mock today, Isaac Lab-Arena later) writes one JSON file:

    {
      "policy": "mock-policy",
      "evaluator": "mock",
      "episodes": [
        {"seed": 0, "scene": "rack_left", "success": true},
        {"seed": 1, "scene": "dim_light", "success": false, "failure": "tube dropped",
         "video_url": "https://..."}
      ]
    }

``seed`` and ``success`` are required per episode; ``scene``, ``failure`` and ``video_url`` are
optional. Seeds must be unique: each one identifies a reproducible episode. On real hardware,
where nothing is seeded, the seed is the attempt number, a label only (ADR 0022).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ResultsError(ValueError):
    """The results file is missing, malformed or fails a sanity check."""


@dataclass(frozen=True)
class EpisodeResult:
    seed: int
    success: bool
    scene: str | None = None
    failure: str | None = None
    video_url: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EpisodeResult:
        if not isinstance(data, Mapping):
            raise ResultsError("episode must be an object")
        missing = {"seed", "success"} - data.keys()
        if missing:
            raise ResultsError(f"episode without {sorted(missing)}: {dict(data)}")
        if not isinstance(data["success"], bool):
            raise ResultsError(f"'success' must be true or false, got {data['success']!r}")
        value = data["seed"]
        if not isinstance(value, (int, float, str, bytes, bytearray)):
            raise ResultsError("'seed' must be convertible to an integer")
        try:
            seed = int(value)
        except (ValueError, OverflowError) as exc:
            raise ResultsError(f"invalid 'seed': {exc}") from exc
        return cls(
            seed=seed,
            success=data["success"],
            scene=data.get("scene"),
            failure=data.get("failure"),
            video_url=data.get("video_url"),
        )


@dataclass(frozen=True)
class EvalResults:
    policy: str
    evaluator: str
    episodes: tuple[EpisodeResult, ...]

    def __post_init__(self) -> None:
        if not self.episodes:
            raise ResultsError("results contain no episodes")
        seeds = [episode.seed for episode in self.episodes]
        duplicates = sorted({seed for seed in seeds if seeds.count(seed) > 1})
        if duplicates:
            raise ResultsError(f"duplicate seeds: {duplicates}")

    @property
    def trials(self) -> int:
        return len(self.episodes)

    @property
    def successes(self) -> int:
        return sum(episode.success for episode in self.episodes)

    @property
    def failed(self) -> list[EpisodeResult]:
        return [episode for episode in self.episodes if not episode.success]

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "evaluator": self.evaluator,
            "episodes": [
                {key: value for key, value in asdict(episode).items() if value is not None}
                for episode in self.episodes
            ],
        }


def parse_results(data: Mapping[str, Any]) -> EvalResults:
    if not isinstance(data, Mapping):
        raise ResultsError("expected a JSON object")
    episodes = data.get("episodes")
    if not isinstance(episodes, Sequence) or isinstance(episodes, str):
        raise ResultsError("'episodes' must be a list")
    return EvalResults(
        policy=str(data.get("policy", "unknown")),
        evaluator=str(data.get("evaluator", "unknown")),
        episodes=tuple(EpisodeResult.from_dict(item) for item in episodes),
    )


def load_results(path: Path) -> EvalResults:
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise ResultsError(f"cannot read results from {path}: {exc}") from exc
    try:
        data = json.loads(contents)
    except (ValueError, RecursionError) as exc:
        raise ResultsError(f"cannot read results from {path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ResultsError(f"{path}: expected a JSON object")
    try:
        return parse_results(data)
    except ResultsError as exc:
        raise ResultsError(f"{path}: {exc}") from exc


def save_results(results: EvalResults, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF on every OS: a certificate pins the exact bytes, and certified files are written on Linux.
    text = json.dumps(results.to_dict(), indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
