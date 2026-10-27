from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from eval.dataset_stats import DatasetMeta, format_summary, main, summarize

SO101_JOINTS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


def _features() -> dict[str, dict[str, Any]]:
    return {
        "action": {"dtype": "float32", "shape": [6], "names": SO101_JOINTS},
        "observation.state": {"dtype": "float32", "shape": [6], "names": SO101_JOINTS},
        "observation.images.front": {"dtype": "video", "shape": [480, 640, 3]},
        "observation.images.wrist": {"dtype": "video", "shape": [480, 640, 3]},
        "timestamp": {"dtype": "float32", "shape": [1], "names": None},
    }


@dataclass
class FakeMeta:
    lengths: list[int] = field(default_factory=lambda: [300, 450, 600])
    repo_id: str = "someone/so101_fake"
    fps: int = 30
    robot_type: str | None = "so101_follower"
    features: dict[str, dict[str, Any]] = field(default_factory=_features)
    total_episodes: int | None = None
    total_frames: int | None = None

    def __post_init__(self) -> None:
        if self.total_episodes is None:
            self.total_episodes = len(self.lengths)
        if self.total_frames is None:
            self.total_frames = sum(self.lengths)

    @property
    def episodes(self) -> dict[str, list[int]]:
        # Same column access as a HF datasets.Dataset: episodes["length"].
        return {"length": self.lengths}


def test_summarize_counts_and_durations() -> None:
    summary = summarize(FakeMeta())

    assert summary.num_episodes == 3
    assert summary.num_frames == 1350
    assert summary.min_episode_s == 10.0
    assert summary.mean_episode_s == 15.0
    assert summary.max_episode_s == 20.0
    assert summary.total_duration_s == 45.0
    assert summary.warnings == []


def test_summarize_feature_dimensions() -> None:
    summary = summarize(FakeMeta())

    assert summary.action_dim == 6
    assert summary.state_dim == 6
    assert summary.action_names == SO101_JOINTS
    assert summary.camera_keys == ["observation.images.front", "observation.images.wrist"]


def test_summarize_accepts_names_nested_by_axis() -> None:
    features = _features()
    features["action"]["names"] = {"motors": SO101_JOINTS}

    assert summarize(FakeMeta(features=features)).action_names == SO101_JOINTS


def test_summarize_handles_missing_action_feature() -> None:
    features = _features()
    del features["action"]

    summary = summarize(FakeMeta(features=features))

    assert summary.action_dim is None
    assert summary.action_names == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"total_episodes": 4}, "4 episodes"),
        ({"total_frames": 999}, "999 frames"),
    ],
)
def test_summarize_flags_inconsistent_metadata(overrides: dict[str, int], expected: str) -> None:
    summary = summarize(FakeMeta(**overrides))

    assert len(summary.warnings) == 1
    assert expected in summary.warnings[0]


def test_summarize_rejects_invalid_fps() -> None:
    with pytest.raises(ValueError, match="Invalid fps"):
        summarize(FakeMeta(fps=0))


def test_format_summary_is_human_readable() -> None:
    text = format_summary(summarize(FakeMeta()))

    assert "Episodes:       3" in text
    assert "Action dim:     6" in text
    assert "mean 15.0 s" in text
    assert "WARNING" not in text


def test_main_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    def loader(repo_id: str, revision: str | None) -> DatasetMeta:
        return FakeMeta(repo_id=repo_id)

    exit_code = main(["--repo-id", "me/data", "--json"], loader=loader)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["repo_id"] == "me/data"
    assert payload["action_dim"] == 6


def test_main_fails_when_metadata_is_inconsistent(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([], loader=lambda repo_id, revision: FakeMeta(total_frames=1))

    assert exit_code == 1
    assert "WARNING" in capsys.readouterr().out


@pytest.mark.hub
def test_real_so101_dataset_from_hub() -> None:
    pytest.importorskip("lerobot")
    from eval.dataset_stats import DEFAULT_REPO_ID, load_metadata

    summary = summarize(load_metadata(DEFAULT_REPO_ID))

    assert summary.num_episodes > 0
    assert summary.action_dim == 6  # SO-101: 5 arm joints + gripper
    assert summary.warnings == []
