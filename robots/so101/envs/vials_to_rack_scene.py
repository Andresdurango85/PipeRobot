# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Ported from isaac-sim/Sim-to-Real-SO-101-Workshop @ ce807d9,
# source/sim_to_real_so101/tasks/{task_env_cfg,vials_to_rack_env_cfg}.py.
# Modified for PipeRobot: Isaac Lab 3.0 API, XYZW quaternions, the
# Isaac Lab 3.0 SO-101 asset and optional external recording camera.
"""Build the nominal tube-to-rack scene after the Isaac runtime has launched."""

import json
import math
from collections.abc import Mapping
from pathlib import Path


def build_scene_cfg(
    assets_dir: Path,
    actuators: str = "course",
    num_envs: int = 1,
    camera: Mapping | None = None,
) -> object:
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.sensors import ContactSensorCfg
    from isaaclab.utils import clone
    from isaaclab_assets.robots.so101 import SO101_CFG
    from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg
    from pxr import Sdf, Usd

    if actuators not in {"course", "usd"} or num_envs < 1:
        raise ValueError("Expected course/usd actuators and positive num_envs")
    directory = Path(__file__).resolve().parent
    data = json.loads((directory / "vials_to_rack.json").read_text(encoding="utf-8"))
    cfg = InteractiveSceneCfg(num_envs=num_envs, env_spacing=2.0)
    robot = clone(SO101_CFG)
    robot.prim_path = "{ENV_REGEX_NS}/Robot"
    robot.spawn.variants = {"Robot": "robot", "Sensor": "sensors", "Physics": "physx"}
    robot.spawn.activate_contact_sensors = True
    robot.init_state.pos = tuple(data["robot"]["position_m"])
    half = math.radians(data["robot"]["yaw_deg"]) / 2
    robot.init_state.rot = (0.0, 0.0, math.sin(half), math.cos(half))
    if actuators == "course":
        course = json.loads((directory / "course_actuators.json").read_text(encoding="utf-8"))
        robot.actuators = {
            name: ImplicitActuatorCfg(joint_names_expr=[name], **values)
            for name, values in course["joints"].items()
        }
        robot.spawn.articulation_props = [PhysxArticulationCfg(**course["articulation"])]
    cfg.robot = robot

    # Install NoneRule BEFORE spawning: the unavailable Nucleus camera payload never loads.
    from isaaclab.sim import SimulationContext

    stage = SimulationContext.instance().stage
    rules = stage.GetLoadRules()
    for env_index in range(num_envs):
        for payload in data["light_box"]["unloaded_payloads"]:
            path = f"/World/envs/env_{env_index}/LightStudio/{payload}"
            rules.AddRule(Sdf.Path(path), Usd.StageLoadRules.NoneRule)
    stage.SetLoadRules(rules)
    for name, prim in (("light_box", "LightStudio"), ("mat", "Mat")):
        item = data[name]
        half = math.radians(item.get("yaw_deg", 0)) / 2
        setattr(
            cfg,
            name,
            AssetBaseCfg(
                prim_path="{ENV_REGEX_NS}/" + prim,
                spawn=sim_utils.UsdFileCfg(usd_path=str(assets_dir / item["usd"])),
                init_state=AssetBaseCfg.InitialStateCfg(
                    pos=tuple(item["position_m"]), rot=(0.0, 0.0, math.sin(half), math.cos(half))
                ),
            ),
        )
    for name, prim, item, position in [
        ("rack", "Rack_Left", data["rack"], data["rack"]["origin_m"]),
        *(
            (f"tube_{i}", f"Vial_{i}", data["tubes"], pos)
            for i, pos in enumerate(data["tubes"]["origins_m"], 1)
        ),
    ]:
        half = math.radians(item.get("pitch_deg", 0)) / 2
        setattr(
            cfg,
            name,
            RigidObjectCfg(
                prim_path="{ENV_REGEX_NS}/" + prim,
                spawn=sim_utils.UsdFileCfg(
                    usd_path=str(assets_dir / item["usd"]),
                    mass_props=sim_utils.MassPropertiesCfg(mass=item["mass_kg"]),
                    rigid_props=(
                        PhysxRigidBodyCfg(angular_damping=item["angular_damping"])
                        if "angular_damping" in item
                        else None
                    ),
                ),
                init_state=RigidObjectCfg.InitialStateCfg(
                    pos=tuple(position), rot=(0.0, math.sin(half), 0.0, math.cos(half))
                ),
            ),
        )
    sensor = data["contact_sensor"]
    cfg.contact_grasp = ContactSensorCfg(
        prim_path="{ENV_REGEX_NS}/Robot/" + sensor["body"],
        update_period=sensor["update_period"],
        history_length=sensor["history_length"],
        filter_prim_paths_expr=["{ENV_REGEX_NS}/" + name for name in sensor["filtered_tubes"]],
    )
    if camera is not None:
        from isaaclab.sensors import CameraCfg

        cfg.video_camera = CameraCfg(
            prim_path="{ENV_REGEX_NS}/VideoCamera",
            data_types=["rgb"],
            width=camera["width"],
            height=camera["height"],
            update_period=0,
            spawn=sim_utils.PinholeCameraCfg(focal_length=camera["focal_length"]),
        )
    return cfg
