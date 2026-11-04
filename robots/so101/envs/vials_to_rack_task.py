"""SO-101 tube-to-rack evaluation using the registered reconstructed runtime.

Observation: {"step": int, "joint_pos": {joint_units name: LeRobot value}}.
Actions contain six finite LeRobot values in the dataset's joint_names order
(the .pos suffix is removed for observation keys). Replay seeds are demo indices.
Policies opting into UsesObjectState receive objects: tubes (scene order), rack and tcp
poses as pos and quat_xyzw float lists, plus four rack-local slot centres transformed
into world slots_w. TCP is the gripper body plus tcp.offset_m.
The tcp action space is [world x, y, z metres, gripper pitch radians (shoulder_lift + elbow_flex +
wrist_flex), wrist_roll radians,
gripper LeRobot 0..100]; joint is the default action space.
Randomized reactive rollouts default to 600 control steps, configurable via horizon_steps.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from piperobot.adapters.isaaclab.specs import (
    Policy,
    ReferenceEpisodes,
    UsesObjectState,
    load_module,
)

ENV = Path(__file__).resolve().parent
TOOLS = ENV.parent / "tools"


def scene_label(seed: int, layout: str) -> str:
    if layout == "reconstructed_demo":
        return f"demo_{seed}"
    if layout == "randomized":
        return "randomized"
    raise ValueError(f"Unknown layout: {layout}")


def validate_layout(policy: Policy, layout: str) -> None:
    scene_label(0, layout)
    if layout == "randomized" and isinstance(policy, ReferenceEpisodes):
        raise ValueError("Open-loop replay ignores randomized layout; use a reactive policy")
    if layout == "reconstructed_demo" and not isinstance(policy, ReferenceEpisodes):
        raise ValueError("reconstructed_demo requires a policy implementing ReferenceEpisodes")


class SimulationConfig(Protocol):
    dt: float


def simulation_settings(options: Mapping[str, object]) -> dict[str, object]:
    """SimulationCfg fields the worker sets before launch."""
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    return {"dt": data["control"]["physics_dt"]}


def run_episode(
    seed: int,
    policy: Policy,
    layout: str,
    options: Mapping[str, object],
    sim_cfg: SimulationConfig,
    record_dir: Path | None = None,
) -> dict[str, object]:
    if record_dir is not None and layout == "reconstructed_demo":
        raise ValueError("recording supports the randomized layout only")
    validate_layout(policy, layout)
    validate_action_space(policy, options.get("action_space", "joint"))
    # Existing study modules import siblings by name; keep that convention local to this task.
    sys.path.insert(0, str(TOOLS))
    runtime = load_module("task_reconstructed_episodes", ENV / "vials_to_rack_episodes.py")
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    if sim_cfg.dt != data["control"]["physics_dt"]:
        raise ValueError(
            f"SimulationCfg dt {sim_cfg.dt} is not the scene's; see simulation_settings"
        )
    assets = options.get("assets_dir")
    if assets is None:
        fetch = load_module("task_asset_cache", TOOLS / "fetch_course_assets.py")
        manifest = json.loads((ENV / "course_assets.json").read_text(encoding="utf-8"))
        assets_dir = fetch.default_cache_dir(manifest["source"]["commit"])
    else:
        assets_dir = Path(str(assets)).resolve()
    names = getattr(policy, "joint_names", list(runtime.UNITS.load_table()))
    recording = {}
    if record_dir is not None:
        recording["record"] = json.loads((ENV / "video_camera.json").read_text(encoding="utf-8"))
    env = runtime.ReconstructedEpisodes(
        assets_dir, str(options.get("actuators", "course")), sim_cfg, names, **recording
    )
    env.seed = seed
    env.policy = policy
    env.action_space = options.get("action_space", "joint")
    env.uses_object_state = isinstance(policy, UsesObjectState) and policy.uses_object_state
    # Optional controller settings for the TCP action space; the runtime has the defaults.
    if "ik_gain" in options:
        env.ik_gain = float(options["ik_gain"])
    if "ik_max_lead_rad" in options:
        env.ik_max_lead = float(options["ik_max_lead_rad"])
    sampled = None
    if layout == "reconstructed_demo":
        if not isinstance(policy, ReferenceEpisodes):
            raise ValueError("ReferenceEpisodes required")
        reference = policy.reference_episode(seed)
        if reference is None:
            raise ValueError(f"No reference episode for seed {seed}")
        episode = dict(reference)
    else:
        randomization = load_module("task_randomization", ENV / "vials_to_rack_randomization.py")
        sampled = randomization.sample_layout(seed, data)
        horizon = options.get("horizon_steps", 600)
        if type(horizon) is not int or horizon <= 0:
            raise ValueError("horizon_steps must be a positive integer")

        def apply_layout() -> None:
            env.teleport(
                env.rack,
                (
                    *sampled.rack_position,
                    *runtime.CORE.yaw_to_quat_xyzw(math.degrees(sampled.rack_yaw)),
                ),
            )
            for tube, position in zip(env.tubes, sampled.tubes, strict=True):
                env.teleport(tube, (*position, *env.lying))

        result = env.run_policy_episode(
            apply_layout,
            lambda index, observation: policy.act(observation),
            horizon,
            record_steps=bool(options.get("record_steps", False)),
            **({"record_dir": record_dir} if record_dir is not None else {}),
        )
    if layout == "reconstructed_demo":
        result = env.run_reconstructed_episode(
            episode,
            record_steps=False,
            action_source=lambda index, observation: policy.act(observation),
        )
    result["scene"] = scene_label(seed, layout)
    reason = result.pop("failure_reason")
    result["failure"] = None if result["success"] else reason
    return result


def validate_action_space(policy: Policy, action_space: object) -> None:
    if action_space not in ("joint", "tcp"):
        raise ValueError("action_space must be joint or tcp")
    if getattr(policy, "action_space", "joint") != action_space:
        raise ValueError("Policy action_space differs from task action_space")
