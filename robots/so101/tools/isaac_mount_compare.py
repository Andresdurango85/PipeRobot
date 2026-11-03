"""Compare course and Isaac Lab SO-101 geometry at recorded grasp/release poses."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from isaac_demo_replay import CORE, ENV, UNITS
from isaac_success_check import check_assets

COURSE_NAMES = {
    "shoulder_pan": "Rotation",
    "shoulder_lift": "Pitch",
    "elbow_flex": "Elbow",
    "wrist_flex": "Wrist_Pitch",
    "wrist_roll": "Wrist_Roll",
    "gripper": "Jaw",
}
COURSE_Y = 1.0
SCENE = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))


def run(args: argparse.Namespace, sim_cfg: object) -> int:
    import isaaclab.sim as sim_utils
    import numpy as np
    import torch
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import Articulation, ArticulationCfg
    from isaaclab.sim import SimulationContext
    from isaaclab.utils import clone
    from isaaclab_assets.robots.so101 import SO101_CFG
    from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    sim = SimulationContext(sim_cfg)
    # No ground plane, fixed course root, gravity off: an unfixed root plus a ground
    # plane through the course base previously sent positions to ~1e8.
    rot = CORE.yaw_to_quat_xyzw(SCENE["robot"]["yaw_deg"])
    base = list(SCENE["robot"]["position_m"])

    new_cfg = clone(SO101_CFG)
    new_cfg.prim_path = "/World/New"
    new_cfg.spawn.variants = {"Robot": "robot", "Sensor": "sensors", "Physics": "physx"}
    new_cfg.spawn.rigid_props.disable_gravity = True
    new_cfg.init_state.pos = tuple(base)
    new_cfg.init_state.rot = rot
    new = Articulation(cfg=new_cfg)

    course_cfg = ArticulationCfg(
        prim_path="/World/Course",
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(args.course_usd),
            activate_contact_sensors=False,
            fix_root_link=True,
            rigid_props=PhysxRigidBodyCfg(disable_gravity=True),
            articulation_props=[
                PhysxArticulationCfg(
                    enabled_self_collisions=False,
                    solver_position_iteration_count=32,
                    solver_velocity_iteration_count=1,
                )
            ],
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(base[0], base[1] + COURSE_Y, base[2]),
            rot=rot,
            joint_pos={v: 0.0 for v in COURSE_NAMES.values()},
        ),
        actuators={
            "all": ImplicitActuatorCfg(joint_names_expr=[".*"], stiffness=100.0, damping=1.0)
        },
    )
    course = Articulation(cfg=course_cfg)
    sim.reset()

    stage = sim.stage if hasattr(sim, "stage") else None
    if stage is None:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())

    def find_body(root: str, name: str) -> object:
        for p in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies()):
            if p.GetName() == name and p.HasAPI(UsdPhysics.RigidBodyAPI):
                return p
        raise RuntimeError(f"no body {name} under {root}")

    def collision_points(body: object) -> tuple[list[object], set[str]]:
        """World points of every collision mesh under the body, at the authored layout."""
        points, types = [], set()
        for p in Usd.PrimRange(body, Usd.TraverseInstanceProxies()):
            if p != body and p.HasAPI(UsdPhysics.RigidBodyAPI):
                continue
            if not p.HasAPI(UsdPhysics.CollisionAPI):
                continue
            for q in Usd.PrimRange(p, Usd.TraverseInstanceProxies()):
                types.add(q.GetTypeName())
                if q.IsA(UsdGeom.Mesh):
                    m = cache.GetLocalToWorldTransform(q)
                    pts = UsdGeom.Mesh(q).GetPointsAttr().Get() or []
                    points.extend(m.Transform(Gf.Vec3d(*v)) for v in pts)
        return points, types

    def local_points(root: str, name: str) -> tuple[object, list[str]]:
        body = find_body(root, name)
        inv = cache.GetLocalToWorldTransform(body).GetInverse()
        pts, types = collision_points(body)
        return np.array([list(inv.Transform(v)) for v in pts]), sorted(types)

    bodies = {
        "new": ("/World/New", {"base": "base", "gripper": "gripper", "jaw": "moving_jaw_so101_v1"}),
        "course": ("/World/Course", {"base": "base", "gripper": "gripper", "jaw": "jaw"}),
    }
    geometry, info = {}, {}
    for robot_name, (root, names) in bodies.items():
        geometry[robot_name] = {}
        for key, body in names.items():
            pts, types = local_points(root, body)
            geometry[robot_name][key] = pts
            info[f"{robot_name}.{key}"] = {"points": len(pts), "types": types}
    print("[MOUNT] geometry", json.dumps(info))

    def rotate(q: object, v: object) -> object:  # q XYZW, v (N, 3)
        x, y, z, w = q
        r = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        return v @ r.T

    robots = {"new": new, "course": course}
    ids = {
        "new": [new.joint_names.index(n) for n in COURSE_NAMES],
        "course": [course.joint_names.index(v) for v in COURSE_NAMES.values()],
    }
    body_ids = {
        r: {k: robots[r].body_names.index(b) for k, b in bodies[r][1].items()} for r in robots
    }
    meta = {
        "new_joints": new.joint_names,
        "course_joints": course.joint_names,
        "new_bodies": new.body_names,
        "course_bodies": course.body_names,
        "course_limits_deg": [
            [math.degrees(v) for v in p]
            for p in course.data.joint_pos_limits.torch[0].cpu().tolist()
        ],
    }
    print("[MOUNT] meta", json.dumps(meta))

    def pose(robot_name: str) -> dict[str, object]:
        r = robots[robot_name]
        out = {}
        for key, i in body_ids[robot_name].items():
            pos = np.array(r.data.body_pos_w.torch[0, i].cpu().tolist())
            quat = r.data.body_quat_w.torch[0, i].cpu().tolist()
            if robot_name == "course":
                pos[1] -= COURSE_Y
            pts = rotate(quat, geometry[robot_name][key]) + pos
            out[key] = {"origin": pos, "quat": quat, "lowest": pts[np.argmin(pts[:, 2])]}
        return out

    # Foot: base collision min z at spawn, before any joint motion.
    sim.step(render=False)
    for r in robots.values():
        r.update(sim.get_physics_dt())
    feet = {name: float(pose(name)["base"]["lowest"][2]) for name in robots}
    print("[MOUNT] feet", feet)

    table = UNITS.load_table()
    episodes = json.loads(Path(args.episodes_json).read_text(encoding="utf-8"))
    names = [n.removesuffix(".pos") for n in episodes["joint_names"]]
    g = names.index("gripper")
    rows = []
    tcp_offset = SCENE["tcp"]["offset_m"]
    with torch.inference_mode():
        for episode in episodes["episodes"]:
            events = CORE.grasp_release_frames(
                [s[g] for s in episode["state"]], [a[g] for a in episode["action"]]
            )
            if events is None:
                continue
            for label, frame in zip(("grasp", "release"), events, strict=True):
                rad = UNITS.to_radians(
                    dict(zip(names, episode["state"][frame], strict=True)), table
                )
                for robot_name, r in robots.items():
                    q = r.data.default_joint_pos.torch.clone()
                    q[0, ids[robot_name]] = torch.tensor(
                        [rad[n] for n in COURSE_NAMES], device=q.device
                    )
                    r.write_joint_position_to_sim_index(position=q)
                    r.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(q))
                    r.set_joint_position_target_index(target=q)
                    r.write_data_to_sim()
                sim.step(render=False)
                for r in robots.values():
                    r.update(sim.get_physics_dt())
                a, b = pose("new"), pose("course")
                tcp = np.array(
                    CORE.tcp_point(
                        a["gripper"]["origin"].tolist(), a["gripper"]["quat"], tcp_offset
                    )
                )
                rows.append(
                    {
                        "episode": episode["index"],
                        "event": label,
                        "frame": frame,
                        "body_delta": (a["gripper"]["origin"] - b["gripper"]["origin"]).tolist(),
                        "jaw_body_delta": (a["jaw"]["origin"] - b["jaw"]["origin"]).tolist(),
                        "fixed_jaw_lowest_delta": (
                            a["gripper"]["lowest"] - b["gripper"]["lowest"]
                        ).tolist(),
                        "moving_jaw_lowest_delta": (
                            a["jaw"]["lowest"] - b["jaw"]["lowest"]
                        ).tolist(),
                        "tcp_minus_course_ee": (tcp - b["gripper"]["origin"]).tolist(),
                        "new_fixed_jaw_lowest": a["gripper"]["lowest"].tolist(),
                        "course_fixed_jaw_lowest": b["gripper"]["lowest"].tolist(),
                        "new_tcp": tcp.tolist(),
                        "course_gripper_origin": b["gripper"]["origin"].tolist(),
                    }
                )
    Path(args.out).write_text(
        json.dumps({"feet_min_z": feet, "meta": meta, "geometry": info, "rows": rows}, indent=1),
        encoding="utf-8",
    )
    print(f"[MOUNT] wrote {len(rows)} rows")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-usd", type=Path, required=True)
    parser.add_argument("--episodes-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--viz")
        parser.add_argument("--device")
        parser.parse_args(argv)
        return 0
    # Parse and verify the reference USD before importing/starting Kit.
    preliminary, _ = parser.parse_known_args(argv)
    errors = check_assets(
        preliminary.course_usd.parent,
        names={preliminary.course_usd.name},
        reference_path=preliminary.course_usd,
    )
    if errors:
        parser.error("; ".join(errors))
    from isaaclab.app import add_launcher_args, launch_simulation
    from isaaclab.sim import SimulationCfg

    add_launcher_args(parser)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sim_cfg = SimulationCfg(dt=SCENE["control"]["physics_dt"], device=args.device)
    with launch_simulation(sim_cfg, args):
        try:
            code = run(args, sim_cfg)
        except Exception:
            args.out.write_text(json.dumps({"error": traceback.format_exc()}), encoding="utf-8")
            traceback.print_exc()
            code = 2
        if code:
            raise SystemExit(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
