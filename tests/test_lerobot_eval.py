from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from eval.lerobot_eval import convert_eval_info
from eval.lerobot_policy import PolicySpec, _coerce_tuple_fields
from eval.results import ResultsError

ROOT = Path(__file__).resolve().parent.parent
LINK = "https://github.com/o/r/actions/runs/1"


def _eval_info(successes: list[bool], n_videos: int = 10) -> dict[str, Any]:
    """Shape of LeRobot 0.6.1's eval_info.json for a single-task env."""
    return {
        "per_task": [
            {
                "task_group": "pusht",
                "task_id": 0,
                "metrics": {
                    "successes": successes,
                    "max_rewards": [1.0 if ok else 0.44 for ok in successes],
                    "video_paths": [f"videos/eval_episode_{i}.mp4" for i in range(n_videos)],
                },
            }
        ],
        "overall": {"pc_success": 100 * sum(successes) / len(successes)},
    }


def test_converts_episodes_with_seeds_from_start_seed() -> None:
    results = convert_eval_info(_eval_info([True, False, True]), "vqbet", start_seed=1000)

    assert [e.seed for e in results.episodes] == [1000, 1001, 1002]
    assert (results.successes, results.trials) == (2, 3)
    assert results.evaluator == "lerobot-eval"
    assert results.failed[0].failure == "not solved (max reward 0.44)"


def test_zero_reward_is_reported_not_dropped() -> None:
    info = _eval_info([False, False])
    info["per_task"][0]["metrics"]["max_rewards"] = [0.0, 0.5]

    results = convert_eval_info(info, "p", 0)

    assert [e.failure for e in results.failed] == [
        "not solved (max reward 0.00)",
        "not solved (max reward 0.50)",
    ]


def test_only_failed_episodes_with_a_recorded_video_get_a_link() -> None:
    successes = [False, True] + [False] * 10  # videos exist for the first 10 episodes only
    results = convert_eval_info(_eval_info(successes), "p", 0, videos_link=LINK)

    linked = {e.seed for e in results.episodes if e.video_url}
    assert linked == {0, *range(2, 10)}


def test_no_link_without_videos_link() -> None:
    results = convert_eval_info(_eval_info([False]), "p", 0)

    assert results.failed[0].video_url is None


@pytest.mark.parametrize(
    "info",
    [{}, {"per_task": []}, {"per_task": [{}, {}]}, {"per_task": [{"metrics": {}}]}],
)
def test_malformed_eval_info_is_rejected(info: dict[str, Any]) -> None:
    with pytest.raises(ResultsError):
        convert_eval_info(info, "p", 0)


def test_committed_policy_spec_is_pinned() -> None:
    spec = PolicySpec.load(ROOT / "policies" / "pusht-vqbet.json")

    assert len(spec.revision) == 40  # a full commit SHA, never a branch name
    assert spec.env == "pusht"


def test_invalid_policy_spec_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"name": "x"}), encoding="utf-8")

    with pytest.raises(ResultsError, match="invalid policy spec"):
        PolicySpec.load(path)


def test_list_values_become_tuples_for_tuple_fields() -> None:
    # Reproduces the LeRobot 0.6.1 migration bug: crop_shape arrives as a JSON list.
    @dataclasses.dataclass
    class FakeConfig:
        crop_shape: tuple[int, int] | None = None
        layers: list[int] = dataclasses.field(default_factory=list)

    config = _coerce_tuple_fields(FakeConfig(crop_shape=[84, 84], layers=[1, 2]))  # type: ignore[arg-type]

    assert config.crop_shape == (84, 84)
    assert config.layers == [1, 2]
