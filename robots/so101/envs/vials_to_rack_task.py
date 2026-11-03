"""SO-101 tube-to-rack evaluation using the registered reconstructed runtime.

Observation: {"step": int, "joint_pos": {joint_units name: LeRobot value}}.
Actions contain six finite LeRobot values in the dataset's joint_names order
(the .pos suffix is removed for observation keys). Replay seeds are demo indices.
Randomized reactive rollouts default to 600 control steps, configurable via horizon_steps.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from piperobot.adapters.isaaclab.specs import Policy, ReferenceEpisodes, load_module

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
    seed: int, policy: Policy, layout: str, options: Mapping[str, object], sim_cfg: SimulationConfig
) -> dict[str, object]:
    validate_layout(policy, layout)
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
    env = runtime.ReconstructedEpisodes(
        assets_dir, str(options.get("actuators", "course")), sim_cfg, names
    )
    layout_source = None
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
        initial = runtime.UNITS.to_lerobot(runtime.INITIAL_JOINTS, env.table)
        row = [initial[name] for name in env.names]
        horizon = options.get("horizon_steps", 600)
        if type(horizon) is not int or horizon <= 0:
            raise ValueError("horizon_steps must be a positive integer")
        episode = {"index": seed, "state": [row] * horizon, "action": [row] * horizon}

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

        layout_source = apply_layout
    result = env.run_reconstructed_episode(
        episode,
        record_steps=False,
        action_source=lambda index, observation: policy.act(observation),
        layout_source=layout_source,
    )
    result["scene"] = scene_label(seed, layout)
    reason = result.pop("failure_reason")
    result["failure"] = None if result["success"] else reason
    if sampled is not None:
        result["rack_pose"] = {
            "origin_xyz": sampled.rack_position,
            "yaw": sampled.rack_yaw,
        }
        result["release_frame"] = None
    return result
