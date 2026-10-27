"""Print basic statistics for a LeRobot dataset hosted on the Hugging Face Hub.

Only the dataset metadata (``meta/`` folder: info.json, episodes, tasks, stats) is
downloaded, never the videos, so this is cheap to run.

Usage:
    uv run python -m eval.dataset_stats
    uv run python -m eval.dataset_stats --repo-id lerobot/svla_so101_pickplace --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

DEFAULT_REPO_ID = "lerobot/svla_so101_pickplace"
ACTION_KEY = "action"
STATE_KEY = "observation.state"
CAMERA_DTYPES = ("video", "image")


class EpisodeTable(Protocol):
    """Column access as on a HF ``datasets.Dataset``: ``episodes["length"]``."""

    def __getitem__(self, column: str, /) -> Iterable[Any]: ...


class DatasetMeta(Protocol):
    """Subset of ``lerobot.datasets.LeRobotDatasetMetadata`` (LeRobot 0.6.x) used here."""

    repo_id: str
    # One row per episode; the "length" column is the number of frames of each episode.
    episodes: EpisodeTable | None

    @property
    def total_episodes(self) -> int: ...

    @property
    def total_frames(self) -> int: ...

    @property
    def fps(self) -> int: ...

    @property
    def robot_type(self) -> str | None: ...

    @property
    def features(self) -> Mapping[str, Mapping[str, Any]]: ...


@dataclass(frozen=True)
class DatasetSummary:
    repo_id: str
    robot_type: str | None
    fps: int
    num_episodes: int
    num_frames: int
    min_episode_s: float
    mean_episode_s: float
    max_episode_s: float
    total_duration_s: float
    action_dim: int | None
    action_names: list[str]
    state_dim: int | None
    camera_keys: list[str]
    warnings: list[str] = field(default_factory=list)


def _feature_dim(features: Mapping[str, Mapping[str, Any]], key: str) -> int | None:
    feature = features.get(key)
    if feature is None:
        return None
    shape = feature.get("shape") or ()
    return int(shape[0]) if len(shape) == 1 else None


def _feature_names(features: Mapping[str, Mapping[str, Any]], key: str) -> list[str]:
    names = (features.get(key) or {}).get("names")
    # Older datasets nest names under an axis label, e.g. {"motors": [...]}.
    if isinstance(names, Mapping):
        names = next(iter(names.values()), None)
    return [str(n) for n in names] if isinstance(names, Sequence) else []


def _episode_lengths(episodes: EpisodeTable | None) -> list[int]:
    if episodes is None:
        return []
    return [int(length) for length in episodes["length"]]


def summarize(meta: DatasetMeta) -> DatasetSummary:
    """Compute summary statistics and sanity checks from dataset metadata."""
    fps = int(meta.fps)
    if fps <= 0:
        raise ValueError(f"Invalid fps {fps} for dataset {meta.repo_id}")

    lengths = _episode_lengths(meta.episodes)
    durations = [n / fps for n in lengths] or [0.0]
    warnings: list[str] = []
    if len(lengths) != meta.total_episodes:
        warnings.append(
            f"info.json reports {meta.total_episodes} episodes "
            f"but episode metadata has {len(lengths)}"
        )
    if sum(lengths) != meta.total_frames:
        warnings.append(
            f"info.json reports {meta.total_frames} frames "
            f"but episode lengths add up to {sum(lengths)}"
        )

    features = meta.features
    return DatasetSummary(
        repo_id=meta.repo_id,
        robot_type=meta.robot_type,
        fps=fps,
        num_episodes=int(meta.total_episodes),
        num_frames=int(meta.total_frames),
        min_episode_s=round(min(durations), 2),
        mean_episode_s=round(statistics.fmean(durations), 2),
        max_episode_s=round(max(durations), 2),
        total_duration_s=round(sum(lengths) / fps, 2),
        action_dim=_feature_dim(features, ACTION_KEY),
        action_names=_feature_names(features, ACTION_KEY),
        state_dim=_feature_dim(features, STATE_KEY),
        camera_keys=sorted(k for k, ft in features.items() if ft.get("dtype") in CAMERA_DTYPES),
        warnings=warnings,
    )


def format_summary(summary: DatasetSummary) -> str:
    lines = [
        f"Dataset:        {summary.repo_id}",
        f"Robot type:     {summary.robot_type or 'unknown'}",
        f"FPS:            {summary.fps}",
        f"Episodes:       {summary.num_episodes}",
        f"Frames:         {summary.num_frames}",
        f"Total duration: {summary.total_duration_s / 60:.1f} min",
        "Episode length: "
        f"min {summary.min_episode_s:.1f} s / mean {summary.mean_episode_s:.1f} s"
        f" / max {summary.max_episode_s:.1f} s",
        f"Action dim:     {summary.action_dim if summary.action_dim is not None else 'n/a'}",
    ]
    if summary.action_names:
        lines.append(f"Action names:   {', '.join(summary.action_names)}")
    lines += [
        f"State dim:      {summary.state_dim if summary.state_dim is not None else 'n/a'}",
        f"Cameras:        {', '.join(summary.camera_keys) or 'none'}",
    ]
    lines += [f"WARNING: {w}" for w in summary.warnings]
    return "\n".join(lines)


def load_metadata(repo_id: str, revision: str | None = None) -> DatasetMeta:
    """Download (or reuse the cached) ``meta/`` folder of a Hub dataset."""
    try:
        from lerobot.datasets import LeRobotDatasetMetadata
    except ImportError as exc:
        raise SystemExit(
            "LeRobot is not installed. Install it with: uv sync --extra lerobot"
        ) from exc
    return LeRobotDatasetMetadata(repo_id, revision=revision)


def main(
    argv: Sequence[str] | None = None,
    loader: Callable[[str, str | None], DatasetMeta] = load_metadata,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Hub dataset id")
    parser.add_argument("--revision", default=None, help="Branch, tag or commit of the dataset")
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON")
    args = parser.parse_args(argv)

    summary = summarize(loader(args.repo_id, args.revision))
    print(json.dumps(asdict(summary), indent=2) if args.json else format_summary(summary))
    return 1 if summary.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
