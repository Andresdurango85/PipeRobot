"""Offline scripted policy geometry and runtime control flow."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import time
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from piperobot.adapters.isaaclab.specs import UsesObjectState, load_module

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "robots/so101/envs"
P = load_module("test_scripted_policy", ENV.parent / "policies/scripted_pick_place.py")
IK = load_module("test_tcp_helper", ENV / "tcp_ik.py")
TASK = load_module("test_scripted_task", ENV / "vials_to_rack_task.py")


def observation(tcp: list[float] | None = None) -> dict:
    return {
        "step": 0,
        "joint_pos": {name: 0.0 for name in P.UNITS.load_table()},
        "objects": {
            "tubes": [{"pos": [0.2, 0.0, 0.05], "quat_xyzw": [0.0, 0.0, 0.0, 1.0]}],
            "tcp": {"pos": tcp or [0.0, 0.0, 0.0]},
            "slots_w": [[0.3, 0.1, 0.16]] * 4,
        },
    }


def test_protocol_and_action_space() -> None:
    policy = P.ScriptedPickPlace()
    assert isinstance(policy, UsesObjectState)
    assert not isinstance(object(), UsesObjectState)
    TASK.validate_action_space(policy, "tcp")
    with pytest.raises(ValueError, match="differs"):
        TASK.validate_action_space(policy, "joint")
    with pytest.raises(ValueError, match="joint or tcp"):
        TASK.validate_action_space(policy, "invalid")


def test_all_waypoints_and_dwells() -> None:
    policy = P.ScriptedPickPlace(dwell_steps=2)
    obs = observation()
    seen = []
    for _ in range(50):
        before = policy.phase
        action = policy.act(obs)
        if not seen or seen[-1] != before:
            seen.append(before)
        obs["objects"]["tcp"]["pos"] = action[:3]
        if before in ("lift", "reorient", "transfer", "insert"):
            # A held tube moves with the TCP.
            obs["objects"]["tubes"][0]["pos"] = list(action[:3])
    assert seen == list(P.PHASES)
    assert policy.phase == "retreat"
    assert action == pytest.approx([0.3, 0.1, 0.19, -0.172, -1.59, 41])
    policy.reset(123)
    assert policy.phase == "approach"
    assert policy.grasp is None


def test_grasp_geometry_and_roll() -> None:
    policy = P.ScriptedPickPlace(roll_per_pan=2.0, pan_ref=0.1)
    obs = observation()
    obs["objects"]["tubes"][0]["quat_xyzw"] = [0, math.sqrt(0.5), 0, math.sqrt(0.5)]
    action = policy.act(obs)
    # 4 cm along the tube (+x), 2 cm across it (+y), 8 mm below its axis, 6 cm above for approach.
    assert action[:3] == pytest.approx([0.24, 0.02, 0.102])
    pan = P.UNITS.to_radians(obs["joint_pos"], policy.table)["shoulder_pan"]
    assert action[4] == pytest.approx(-1.41 + 2 * (pan - 0.1))
    assert policy.grasp_roll(0.6) == pytest.approx(-0.41)
    obs["objects"]["tubes"][0]["pos"] = [9, 9, 9]
    assert policy.act(obs)[:3] == pytest.approx(action[:3])


def test_fixed_dwell() -> None:
    policy = P.ScriptedPickPlace(dwell_steps=3)
    policy.phase = "close"
    obs = observation()
    for _ in range(2):
        assert policy.act(obs)[5] == 5
        assert policy.phase == "close"
    policy.act(obs)
    assert policy.phase == "lift"


def test_tcp_math() -> None:
    assert IK.skew([1, 2, 3]) == [[0, -3, 2], [3, 0, -1], [-2, 1, 0]]
    # Rotation about z at the body origin creates +y linear velocity at TCP x=2.
    jacobian = [[0], [0], [0], [0], [0], [1]]
    assert IK.shift_jacobian(jacobian, [2, 0, 0]) == [[0], [2], [0]]
    assert IK.clamp(-3, -1, 1) == -1
    assert IK.clamp(3, -1, 1) == 1
    assert IK.clamp(0, -1, 1) == 0
    assert IK.split_action([1, 2, 3, 4, 5, 6]) == ([1, 2, 3], 4, 5, 6)


@pytest.mark.parametrize("action", [[0], [0, 0, 0, 0, 0, math.nan], [0, 0, 0, 0, 0, 101]])
def test_bad_tcp_action(action: list[float]) -> None:
    with pytest.raises(ValueError, match=r"finite|0..100"):
        IK.split_action(action)


def runtime_class() -> type:
    source = ENV / "vials_to_rack_episodes.py"
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    cls.body = [
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("run_policy_episode", "object_state", "state_digest")
    ]
    namespace = {
        "torch": SimpleNamespace(inference_mode=nullcontext),
        "time": time,
        "json": json,
        "hashlib": hashlib,
        "math": math,
        "asdict": asdict,
        "INITIAL_JOINTS": {"wrist_flex": 0},
        "DIGEST": SimpleNamespace(state_digest=lambda values: list(values)),
        "CORE": P.GEOMETRY,
        "UNITS": SimpleNamespace(to_lerobot=lambda radians, table: radians),
    }
    namespace["CORE"] = SimpleNamespace(
        tcp_point=lambda pos, quat, offset: [
            a + b for a, b in zip(pos, P.GEOMETRY.rotate_xyzw(quat, offset), strict=True)
        ]
    )
    exec(  # noqa: S102 - local runtime methods with explicit offline dependencies
        compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace
    )
    return namespace["ReconstructedEpisodes"]


class Array:
    def __init__(self, value: object) -> None:
        self.value = value
        self.torch = self

    def __getitem__(self, index: object) -> Array:
        return self

    def cpu(self) -> Array:
        return self

    def tolist(self) -> object:
        return self.value

    def item(self) -> object:
        return self.value


@pytest.mark.parametrize("measured", [-1.64, 0.0, 1.64])
@pytest.mark.parametrize("record_steps", [False, True])
@pytest.mark.parametrize("success_at", [1, None])
@pytest.mark.parametrize("privileged", [False, True])
def test_policy_loop(
    success_at: int | None, privileged: bool, record_steps: bool, measured: float
) -> None:
    env = runtime_class()()
    trace = []
    env.full_reset = False
    env.seed = 200000
    env.action_space = "joint"
    env.uses_object_state = privileged
    env.policy = SimpleNamespace(command_phase="approach")
    digest_calls = []

    def digest() -> str:
        digest_calls.append(len(trace))
        return f"{len(digest_calls):064x}"

    env.state_digest = digest
    env.forces = lambda: [0.0]
    env.names = ["wrist_flex"]
    env.table = {}
    env.substeps = 2
    env.robot = SimpleNamespace(
        joint_names=env.names,
        data=SimpleNamespace(joint_pos=Array(measured), joint_pos_limits=Array([-1.66, 1.66])),
    )
    env.rack = SimpleNamespace(
        data=SimpleNamespace(root_pos_w=Array([1, 2, 3]), root_quat_w=Array([0, 0, 0, 1]))
    )
    env.reset_layout = lambda **kwargs: trace.append(("reset", kwargs))
    env.set_joints = lambda values: trace.append("joints")
    env.tracker = SimpleNamespace(
        reset=lambda: trace.append("tracker"),
        failure_reason=lambda: None if success_at is not None else "no_grasp",
    )
    env.sensor = SimpleNamespace(reset=lambda: trace.append("sensor"))
    env.physics_step = lambda: trace.append("physics")
    env.apply_policy_action = lambda action: trace.append("action")
    env.object_state = lambda: {"tubes": [], "rack": {}, "slots_w": [], "tcp": {"pos": [0, 0, 0]}}

    def sample(index: int) -> object:
        trace.append(("sample", index))
        env.dump_steps.append({"step_index": index})
        return P.GEOMETRY.StepResult(
            index == success_at,
            (P.GEOMETRY.VialResult(False, False, True, True, False, (0, 0, 0), 0, -0.01),),
            0,
            success_at,
        )

    def action(index: int, obs: dict) -> list[float]:
        assert set(obs) == (
            {"step", "joint_pos", "objects"} if privileged else {"step", "joint_pos"}
        )
        assert obs["step"] == index
        return [0]

    env.sample = sample
    result = env.run_policy_episode(lambda: trace.append("layout"), action, 4, record_steps)
    assert result["initial_state_sha256"] == f"{1:064x}"
    assert result["final_state_sha256"] == f"{2:064x}"
    assert result["metric"] == -0.01
    assert digest_calls == [5, len(trace)]
    count = 2 if success_at == 1 else 4
    assert result["steps_run"] == count
    assert result["success"] is (success_at is not None)
    assert result["wrist_flex_limit_steps"] == (count if measured != 0 else 0)
    assert result["release_frame"] is None
    assert result["forces"] is None
    if record_steps:
        assert len(result["steps"]) == count
        assert result["steps"][0]["phase"] == "approach"
        assert result["steps"][0]["tracker"]["success_step"] == success_at
    assert trace[:5] == [("reset", {"nominal": True}), "layout", "joints", "tracker", "sensor"]
    assert trace[5:] == [
        event for i in range(count) for event in ("action", "physics", "physics", ("sample", i))
    ]
    expected = json.dumps(env.dump_steps, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert result["trajectory_sha256"] == hashlib.sha256(expected.encode()).hexdigest()
    with pytest.raises(RuntimeError, match="Initial rack position is stale"):
        env.run_policy_episode(lambda: None, action, 4, False, expected_rack_position=(0, 0, 0))
    # The failed freshness check must happen before any further digest or action.
    assert len(digest_calls) == 2


def test_object_world_geometry() -> None:
    env = runtime_class()()
    q = [0, 0, math.sqrt(0.5), math.sqrt(0.5)]
    env.rack = SimpleNamespace(
        data=SimpleNamespace(root_pos_w=Array([1.0, 2.0, 3.0]), root_quat_w=Array(q))
    )
    env.tubes = [env.rack]
    env.data = {
        "tcp": {"body": "gripper", "offset_m": [1, 0, 0]},
        "rack": {"slots_m": [[1, 0, 0]] * 4},
    }
    env.robot = SimpleNamespace(
        body_names=["gripper"],
        data=SimpleNamespace(body_pos_w=Array([0, 0, 0]), body_quat_w=Array(q)),
    )
    objects = env.object_state()
    assert objects["slots_w"][0] == pytest.approx([1, 3, 3])
    assert objects["tcp"]["pos"] == pytest.approx([0, 1, 0])
    assert objects["tubes"][0]["quat_xyzw"] == q


def test_task_dispatches_randomized_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    policy = P.ScriptedPickPlace()
    original_load = TASK.load_module

    class Runtime:
        def __init__(self, *args: object) -> None:
            self.rack = "rack"
            self.tubes = ["tube1", "tube2", "tube3"]
            self.lying = [0, 0, 0, 1]

        def teleport(self, obj: object, pose: object) -> None:
            calls.append(obj)

        def run_policy_episode(
            self,
            layout_source: object,
            action_source: object,
            horizon: int,
            record_steps: bool,
            expected_rack_position: tuple[float, float, float],
        ) -> dict:
            assert len(expected_rack_position) == 3
            layout_source()
            assert self.seed == 200000
            assert self.uses_object_state
            assert self.action_space == "tcp"
            assert horizon == 17
            assert record_steps
            assert len(action_source(0, observation())) == 6
            return {"success": False, "failure_reason": "no_grasp"}

    runtime = SimpleNamespace(
        ReconstructedEpisodes=Runtime,
        UNITS=P.UNITS,
        CORE=SimpleNamespace(yaw_to_quat_xyzw=lambda yaw: [0, 0, 0, 1]),
    )

    def load(name: str, path: Path) -> object:
        return runtime if path.name == "vials_to_rack_episodes.py" else original_load(name, path)

    monkeypatch.setattr(TASK, "load_module", load)
    # The production task inserts its sibling tool directory into sys.path.
    import sys

    monkeypatch.setattr(sys, "path", sys.path.copy())
    result = TASK.run_episode(
        200000,
        policy,
        "randomized",
        {
            "action_space": "tcp",
            "assets_dir": ".",
            "horizon_steps": 17,
            "record_steps": True,
        },
        SimpleNamespace(dt=1 / 120),
    )
    assert calls == ["rack", "tube1", "tube2", "tube3"]
    assert result == {"success": False, "failure": "no_grasp", "scene": "randomized"}


def test_spike_help() -> None:
    import subprocess
    import sys

    result = subprocess.run(  # noqa: S603 - current interpreter, local tool help only
        [sys.executable, str(ENV.parent / "tools/isaac_scripted_spike.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--param" in result.stdout
    assert "--dump-steps" in result.stdout


@pytest.mark.parametrize("horizon", [0, -1, True, 1.5])
def test_policy_loop_rejects_horizon(horizon: object) -> None:
    env = runtime_class()()
    with pytest.raises(ValueError, match="positive integer"):
        env.run_policy_episode(lambda: None, lambda index, obs: [], horizon, False)


def test_policy_spec_defaults() -> None:
    from piperobot.adapters.isaaclab.specs import PolicySpec

    spec = PolicySpec.load(ENV.parent / "policies/scripted_pick_place.json")
    assert spec.name == "scripted-pick-place"
    assert spec.files == ()
    assert spec.options == P.DEFAULTS


def test_integrate_gain_and_lead() -> None:
    ik = IK
    # A fraction of the step from the previous target.
    assert ik.integrate([0.0], [1.0], [0.0], 0.2, 1.0) == pytest.approx([0.2])
    # Never further than max_lead from the measured joint.
    assert ik.integrate([0.5], [2.0], [0.0], 1.0, 0.25) == pytest.approx([0.25])
    with pytest.raises(ValueError, match="gain"):
        ik.integrate([0.0], [1.0], [0.0], 0.0, 0.25)


def test_grasp_moves_in_when_the_tube_is_far() -> None:
    policy = P.ScriptedPickPlace(max_grasp_x_m=0.27)
    obs = observation()
    obs["objects"]["tubes"][0]["quat_xyzw"] = [0, math.sqrt(0.5), 0, math.sqrt(0.5)]
    obs["objects"]["tubes"][0]["pos"][0] = 0.26
    # Only 1 cm of reach left, but never closer to the tube's end than 1.5 cm.
    assert policy.act(obs)[0] == pytest.approx(0.26 + 0.015)


def test_state_vector_order() -> None:
    env = runtime_class()()

    def body(start: int) -> object:
        return SimpleNamespace(
            data=SimpleNamespace(
                root_pos_w=Array(list(range(start, start + 3))),
                root_quat_w=Array(list(range(start + 3, start + 7))),
            )
        )

    env.tubes = [body(0), body(7), body(14)]
    env.rack = body(21)
    env.robot = SimpleNamespace(data=SimpleNamespace(joint_pos=Array(list(range(28, 34)))))
    assert env.state_digest() == list(range(34))
