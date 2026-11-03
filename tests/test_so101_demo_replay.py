import json
from pathlib import Path

import pytest
from so101_loader import load

C = load("demo_replay", "robots/so101/envs/demo_replay.py")
SCENE_PATH = Path(__file__).resolve().parents[1] / "robots/so101/envs/vials_to_rack.json"
SCENE = json.loads(SCENE_PATH.read_text())


def test_rates() -> None:
    assert C.control_hz({"metadata_fps": 30, "control_hz": None}) == 30
    assert C.control_hz({"metadata_fps": 30, "control_hz": 60}) == 60
    assert C.substeps_per_frame(60, 1 / 120) == 2
    assert C.substeps_per_frame(30, 1 / 120) == 4
    with pytest.raises(ValueError, match="Non-integer"):
        C.substeps_per_frame(50, 1 / 120)


def test_holds() -> None:
    state = [23] * 10 + [18] * 60 + [27] * 20
    action = [23] * 10 + [1.3] * 60 + [27] * 20
    assert C.find_holds(state, action) == [(10, 70)]
    assert C.grasp_release_frames(state, action) == (10, 70)
    assert C.find_holds([18] * 14, [1.3] * 14) == []
    assert C.grasp_release_frames([23], [23]) is None
    assert C.find_holds(state + state, action + action) == [(10, 70), (100, 160)]
    assert C.grasp_release_frames(state + state, action + action) == (10, 160)
    assert C.grasp_release_frames([18] * 15, [1] * 15) == (0, 14)
    mask = C.judged_gripper(90, [(10, 70)])
    assert not any(mask[10:85])
    assert mask[85]


def test_geometry() -> None:
    q = C.yaw_to_quat_xyzw(90)
    assert C.quat_rotate_xyzw(q, [1, 0, 0]) == pytest.approx([0, 1, 0])
    assert C.tcp_point([1, 2, 3], q, [1, 0, 0]) == pytest.approx([1, 3, 3])
    assert C.grasp_distance([0.23, -0.08], SCENE) == 0
    assert C.place_distance([0.2098, 0.1099], SCENE) == pytest.approx(0)
    assert C.place_distance([0.24, -0.14], SCENE) > 0.1


def test_stats_and_limits() -> None:
    stats = C.tracking_stats(
        [[0, 0], [0, 10]], [[1, 99], [3, 12]], ["arm", "gripper"], [False, True]
    )
    assert stats["joints"]["gripper"]["p95"] == 2
    assert stats["pooled_arm_p95"] == pytest.approx(2.9)
    assert C.limit_shares(
        [[0, 3], [2, 0]], [[0, 1], [1, 0]], [[-1, 1], [-1, 1]], ["arm", "gripper"], [False, True]
    ) == {"target_outside": 0.5, "simulated_near": 0.5}


@pytest.mark.parametrize("lag", [-3, 0, 2, 0.5, -0.5, 8, -8])
def test_best_lag(lag: float) -> None:
    reference = [[[float(t)] * 5 for t in range(40)]]
    follower = [[[t - lag] * 5 for t in range(40)]]
    result = C.best_lag(reference, follower, 8)
    assert result["lag_frames"] == pytest.approx(lag, abs=0.15)
    assert len(result["curve"]) == 17


def test_lag_boundaries_and_episode_pooling() -> None:
    # Each episode contributes only its own valid pairs, weighted by pair count.
    result = C.best_lag([[[0.0] * 5], [[100.0] * 5]], [[[0.0] * 5], [[100.0] * 5]], 8)
    assert result == {"lag_frames": 0.0, "curve": {"0": 0.0}}
    assert C.best_lag([[[1.0] * 5]], [[[2.0] * 5]], 0)["lag_frames"] == 0
    with pytest.raises(ValueError, match="Invalid lag inputs"):
        C.best_lag([], [], 8)


def test_course_actuators() -> None:
    data = json.loads((SCENE_PATH.parent / "course_actuators.json").read_text())
    expected = {
        "shoulder_pan": (55, 0.7),
        "shoulder_lift": (30, 0.8),
        "elbow_flex": (25, 0.7),
        "wrist_flex": (12, 0.5),
        "wrist_roll": (7, 0.5),
        "gripper": (4, 0.3),
    }
    assert set(data["joints"]) == set(expected)
    for name, (stiffness, damping) in expected.items():
        assert data["joints"][name] == {
            "stiffness": stiffness,
            "damping": damping,
            "joint_effort_limit": 30,
        }
        assert all(v > 0 for v in data["joints"][name].values())
    assert data["articulation"] == {
        "enabled_self_collisions": False,
        "solver_position_iteration_count": 32,
        "solver_velocity_iteration_count": 1,
    }


def test_signed_residual_and_hold_mask() -> None:
    result = C.residual_stats(
        [[1, 20], [3, 20]], [[3, 99], [1, 17]], ["arm", "gripper"], [False, True]
    )
    assert result["joints"]["arm"]["mean"] == 2
    assert result["joints"]["arm"]["signed_mean"] == 0
    assert result["joints"]["gripper"]["mean"] == 3
    assert result["joints"]["gripper"]["signed_mean"] == -3
