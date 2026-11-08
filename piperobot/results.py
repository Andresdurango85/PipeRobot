"""Evaluation results: the contract between an evaluator and the gate.

Every evaluator (mock, LeRobot, Isaac Lab, manual outcomes) writes one JSON file:

    {
      "policy": "mock-policy",
      "evaluator": "mock",
      "episodes": [
        {"seed": 0, "scene": "rack_left", "success": true, "metric": 0.01,
         "initial_state_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
         "final_state_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},
        {"seed": 1, "scene": "dim_light", "success": false, "failure": "tube dropped",
         "video_url": "https://...", "metric": 0.03,
         "initial_state_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
         "final_state_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}
      ],
      "metric_spec": {"name": "distance", "unit": "m", "threshold": 0.02,
                      "success_when": "below"}
    }

``seed`` and ``success`` are required per episode; ``scene``, ``failure`` and ``video_url`` are
optional. Seeds must be unique: each one identifies a reproducible episode. On real hardware,
where nothing is seeded, the seed is the attempt number, a label only (ADR 0022).
Optional episode fields also include ``initial_state_sha256``, ``final_state_sha256``
and ``metric`` (a finite number stored as float). Digests are 64 lowercase hex characters.
Each new episode field must be present on all episodes or none. Initial digests must differ
between seeds. That rule assumes the initial digest covers all randomized state: an evaluator
whose scenes come from a small discrete set, with no continuous perturbation, must not emit
initial digests, because two seeds could legitimately share a scene.
Optional ``metric_spec`` contains exactly ``name``, ``unit``, ``threshold`` (finite number)
and ``success_when`` (below or above), and requires episode metrics.
Success is not cross-checked against the threshold: other conditions may determine the outcome.
Metrics without a spec are allowed and reported without a threshold.
``seed`` must be a JSON integer, not a float such as ``3.0``, a bool or a string.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ResultsError(ValueError):
    """The results file is missing, malformed or fails a sanity check."""


@dataclass(frozen=True)
class MetricSpec:
    """A metric threshold is descriptive: success may depend on additional conditions."""

    name: str
    unit: str
    threshold: float
    success_when: str

    @classmethod
    def from_dict(cls, data: object) -> MetricSpec:
        if not isinstance(data, Mapping) or set(data) != {
            "name",
            "unit",
            "threshold",
            "success_when",
        }:
            raise ResultsError(
                "metric_spec must contain exactly name, unit, threshold, success_when"
            )
        if not isinstance(data["name"], str) or not data["name"].strip():
            raise ResultsError("metric_spec name must be a non-empty string")
        if not isinstance(data["unit"], str):
            raise ResultsError("metric_spec unit must be a string")
        if data["success_when"] not in ("below", "above"):
            raise ResultsError("metric_spec success_when must be below or above")
        return cls(
            data["name"],
            data["unit"],
            _number(data["threshold"], "threshold"),
            data["success_when"],
        )


def _number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ResultsError(f"{field} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ResultsError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ResultsError(f"{field} must be a finite number")
    return number


@dataclass(frozen=True)
class EpisodeResult:
    seed: int
    success: bool
    scene: str | None = None
    failure: str | None = None
    video_url: str | None = None

    initial_state_sha256: str | None = None
    final_state_sha256: str | None = None
    metric: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EpisodeResult:
        if not isinstance(data, Mapping):
            raise ResultsError("episode must be an object")
        missing = {"seed", "success"} - data.keys()
        if missing:
            raise ResultsError(
                f"episode without {sorted(missing)} (keys: {sorted(str(k) for k in data)})"
            )
        if not isinstance(data["success"], bool):
            raise ResultsError(
                f"'success' must be true or false, got {type(data['success']).__name__}"
            )
        value = data["seed"]
        if type(value) is not int:
            raise ResultsError(f"'seed' must be an integer, got {type(value).__name__}")
        for field in ("initial_state_sha256", "final_state_sha256"):
            if field in data and (
                not isinstance(data[field], str)
                or re.fullmatch(r"[0-9a-f]{64}", data[field]) is None
            ):
                raise ResultsError(f"{field} must be 64 lowercase hex characters")
        metric = _number(data["metric"], "metric") if "metric" in data else None
        return cls(
            seed=value,
            success=data["success"],
            scene=data.get("scene"),
            failure=data.get("failure"),
            video_url=data.get("video_url"),
            initial_state_sha256=data.get("initial_state_sha256"),
            final_state_sha256=data.get("final_state_sha256"),
            metric=metric,
        )


@dataclass(frozen=True)
class EvalResults:
    policy: str
    evaluator: str
    episodes: tuple[EpisodeResult, ...]

    metric_spec: MetricSpec | None = None

    def __post_init__(self) -> None:
        if not self.episodes:
            raise ResultsError("results contain no episodes")
        seeds = [episode.seed for episode in self.episodes]
        duplicates = sorted({seed for seed in seeds if seeds.count(seed) > 1})
        if duplicates:
            raise ResultsError(f"duplicate seeds: {duplicates}")

        for field in ("initial_state_sha256", "final_state_sha256", "metric"):
            present = [getattr(episode, field) is not None for episode in self.episodes]
            if any(present) and not all(present):
                raise ResultsError(f"{field} must be present on all episodes or none")
        if self.metric_spec is not None and self.episodes[0].metric is None:
            raise ResultsError("metric_spec requires per-episode metric")
        digests: dict[str, list[int]] = {}
        for episode in self.episodes:
            if episode.initial_state_sha256 is not None:
                digests.setdefault(episode.initial_state_sha256, []).append(episode.seed)
        for digest, group in digests.items():
            if len(group) > 1:
                raise ResultsError(
                    f"seeds do not vary the scene: seeds {group[:5]}, digest {digest[:12]}"
                )

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
        data: dict[str, Any] = {
            "policy": self.policy,
            "evaluator": self.evaluator,
            "episodes": [
                {key: value for key, value in asdict(episode).items() if value is not None}
                for episode in self.episodes
            ],
        }
        if self.metric_spec is not None:
            data["metric_spec"] = asdict(self.metric_spec)
        return data


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
        metric_spec=MetricSpec.from_dict(data["metric_spec"]) if "metric_spec" in data else None,
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
