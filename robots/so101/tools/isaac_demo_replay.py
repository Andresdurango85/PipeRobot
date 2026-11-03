"""Replay object-free SO-101 demos in Isaac Lab 3.0; --help needs only Python."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ENV = Path(__file__).resolve().parents[1] / "envs"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UNITS = load_module("joint_units", ENV / "joint_units.py")
CORE = load_module("demo_replay", ENV / "demo_replay.py")
REPORT = load_module("demo_replay_report", Path(__file__).with_name("demo_replay_report.py"))


def replay(args: argparse.Namespace, sim_cfg: object) -> int:
    import isaaclab.sim as sim_utils
    import torch
    from isaaclab.assets import Articulation
    from isaaclab.sim import SimulationContext
    from isaaclab.utils import clone
    from isaaclab_assets.robots.so101 import SO101_CFG

    scene = REPORT.read_json(ENV / "vials_to_rack.json")
    episodes = REPORT.read_json(args.episodes_json)
    if args.max_episodes is not None:
        episodes["episodes"] = episodes["episodes"][: args.max_episodes]
    table = UNITS.load_table()
    names = [n.removesuffix(".pos") for n in episodes["joint_names"]]
    sim = SimulationContext(sim_cfg)
    ground = sim_utils.GroundPlaneCfg()
    ground.func("/World/Ground", ground)
    light = sim_utils.DomeLightCfg(intensity=3000.0)
    light.func("/World/Light", light)
    cfg = clone(SO101_CFG)
    cfg.prim_path = "/World/Robot"
    cfg.spawn.variants = {"Robot": "robot", "Sensor": "sensors", "Physics": "physx"}
    cfg.init_state.pos = tuple(scene["robot"]["position_m"])
    cfg.init_state.rot = CORE.yaw_to_quat_xyzw(scene["robot"]["yaw_deg"])
    robot = Articulation(cfg=cfg)
    sim.reset()
    joint_ids = [robot.joint_names.index(n) for n in names]
    body_id = robot.body_names.index(scene["tcp"]["body"])
    dt = sim.get_physics_dt()
    try:
        version = importlib.metadata.version("isaaclab")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    raw: dict[str, Any] = {
        "metadata": {
            "isaaclab_version": version,
            "asset_usd": cfg.spawn.usd_path,
            "asset_variants": cfg.spawn.variants,
            "joint_names": list(robot.joint_names),
            "body_names": list(robot.body_names),
            "joint_pos_limits": robot.data.joint_pos_limits.torch[0].cpu().tolist(),
            "soft_joint_pos_limits": robot.data.soft_joint_pos_limits.torch[0].cpu().tolist(),
            "default_joint_pos_rad": robot.data.default_joint_pos.torch[0].cpu().tolist(),
            "physics_dt": dt,
            "recorded_joint_order": names,
        },
        "runs": [],
    }

    def converted(row: list[float]) -> object:
        values = UNITS.to_radians(dict(zip(names, row, strict=True)), table)
        return torch.tensor([[values[n] for n in names]], device=sim.device)

    with torch.inference_mode():
        for substeps in args.substeps:
            start = time.perf_counter()
            run: dict[str, Any] = {"substeps": substeps, "episodes": []}
            for episode in episodes["episodes"]:
                initial = robot.data.default_joint_pos.torch.clone()
                initial[:, joint_ids] = converted(episode["state"][0])
                robot.write_joint_position_to_sim_index(position=initial)
                robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(initial))
                robot.set_joint_position_target_index(target=initial)
                robot.reset()
                recorded: dict[str, Any] = {
                    "index": episode["index"],
                    "joint_pos_rad": [],
                    "body_pos_m": [],
                    "body_quat_xyzw": [],
                }
                episode_start = time.perf_counter()
                for action in episode["action"]:
                    robot.set_joint_position_target_index(
                        target=converted(action), joint_ids=joint_ids
                    )
                    for _ in range(substeps):
                        robot.write_data_to_sim()
                        sim.step(render=False)
                        robot.update(dt)
                    recorded["joint_pos_rad"].append(
                        robot.data.joint_pos.torch[0, joint_ids].cpu().tolist()
                    )
                    recorded["body_pos_m"].append(
                        robot.data.body_pos_w.torch[0, body_id].cpu().tolist()
                    )
                    recorded["body_quat_xyzw"].append(
                        robot.data.body_quat_w.torch[0, body_id].cpu().tolist()
                    )
                recorded["wall_seconds"] = time.perf_counter() - episode_start
                run["episodes"].append(recorded)
            run["wall_seconds"] = time.perf_counter() - start
            raw["runs"].append(run)
    (args.out_dir / "replay_raw.json").write_text(
        json.dumps(raw, allow_nan=False) + "\n", encoding="utf-8"
    )
    return REPORT.write_report(REPORT.build_report(episodes, raw, scene, table), args.out_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--substeps", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--max-episodes", type=int)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--viz", help="Isaac launcher visualizer; use none")
        parser.add_argument("--device", help="Isaac launcher device")
        parser.parse_args(argv)
        return 0
    from isaaclab.app import add_launcher_args, launch_simulation
    from isaaclab.sim import SimulationCfg

    add_launcher_args(parser)
    args = parser.parse_args(argv)
    if min(args.substeps) < 1 or (args.max_episodes is not None and args.max_episodes < 1):
        parser.error("Counts must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    sim_cfg = SimulationCfg(dt=1 / 120, device=args.device)
    with launch_simulation(sim_cfg, args):
        try:
            code = replay(args, sim_cfg)
        except Exception:
            error = traceback.format_exc()
            (args.out_dir / "error.txt").write_text(error, encoding="utf-8")
            traceback.print_exc()
            code = 2
        if code:
            raise SystemExit(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
