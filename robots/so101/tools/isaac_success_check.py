"""Registered scene/sensing checks and unregistered reconstructed-demo diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import traceback
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from isaac_demo_replay import CORE, ENV, UNITS, load_module

FETCH = load_module("scene_fetch", Path(__file__).with_name("fetch_course_assets.py"))
LAYOUT = load_module("scene_layout", ENV / "vials_to_rack_layout.py")
SUCCESS = load_module("scene_success", ENV / "vials_to_rack_success.py")

# Fixed on 2026-11-02 before the first run; changing them needs a new ADR.
# S7, S7b and the slot-depth rule added on 2026-11-02 before their first run.
# S7b setup corrected on 2026-11-02 after its first run (held pose
# from the settled rack, not the nominal origin); expectation unchanged.
SETTLE_STEPS = 120
RACK_Z = (0.03, 0.07)
TUBE_Z = (0.02, 0.07)
AXIS_X_MIN = 0.99
SLOT_YAWS = (0.0, 0.5)
SLOT_DROP_EXTRA_Z = 0.02
SLOT_LOCAL_Z_MAX = 0.1
RACK_TOP_Z = 0.073
BESIDE_XY = (-0.05, 0.06)
SENSOR_MAX_N = 0.01
UPRIGHT_TOP_XY = (0.06, 0.06)
UPRIGHT_BOTTOM_OFFSET_Z = 0.017
UPRIGHT_TOP_CLEARANCE_Z = 0.005
HELD_SLOT_CLEARANCE_Z = 0.003
INITIAL_JOINTS = {
    "shoulder_pan": -0.2736,
    "shoulder_lift": -0.6109,
    "elbow_flex": -0.0745,
    "wrist_flex": 1.5148,
    "wrist_roll": -1.6034,
    "gripper": -0.1465,
}


def placement_subpredicates(
    vial: SUCCESS.VialResult, params: SUCCESS.SuccessParams
) -> dict[str, object]:
    """Expose the independent placement conditions from one tracker sample."""
    x, y, z = vial.rack_local_position
    return {
        "vertical": vial.vertical,
        "xy_in_footprint": (
            params.rack_local_x_min <= x <= params.rack_local_x_max
            and params.rack_local_y_min <= y <= params.rack_local_y_max
        ),
        "origin_z_below_course_max": z < params.rack_local_z_max,
        "bottom_below_rim_margin": vial.bottom_local_z < params.rack_rim_z - params.rim_margin_m,
        "in_box": vial.in_box,
        "placed": vial.placed,
        "bottom_local_z": vial.bottom_local_z,
        "rack_local_position": vial.rack_local_position,
    }


def check_assets(
    assets_dir: Path,
    *,
    names: set[str] | None = None,
    reference_path: Path | None = None,
    manifest_path: Path = ENV / "course_assets.json",
) -> list[str]:
    """Read-only size/hash check; reference_path always uses the pinned robot entry."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for asset in manifest["assets"]:
        if reference_path is not None:
            if asset["name"] != "SO-ARM101-USD.usd":
                continue
            path = reference_path
        else:
            if names is None and asset["use"] != "scene":
                continue
            if names is not None and asset["name"] not in names:
                continue
            path = assets_dir / asset["name"]
        if not path.is_file():
            errors.append(f"Missing {path}; run fetch_course_assets.py")
        else:
            data = path.read_bytes()
            if len(data) != asset["size"] or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                errors.append(f"Invalid size/sha256: {path}; run fetch_course_assets.py")
    return errors


def distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "max": max(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p5": CORE.percentile(values, 0.05) if values else None,
        "p95": CORE.percentile(values, 0.95) if values else None,
    }


def write_report(out_dir: Path, report: dict[str, object]) -> None:
    (out_dir / "checks.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# Scene and sensing checks",
        "",
        "| Check | Expectation | Measured | Pass |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {check['expectation']} | "
            f"{json.dumps(check['measured'])} | {check['passed']} |"
        )
    lines += [
        "",
        "## Diagnostic (not part of the registered checks)",
        "",
        "| Episode | Success | Step | Release | Reason | Rack offset / inside | Forces |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    diagnostic = report["diagnostic"]
    for episode in diagnostic["episodes"]:
        lines.append(
            f"| {episode['index']} | {episode.get('success')} | "
            f"{episode.get('success_step')} | {episode.get('release_frame')} | "
            f"{episode.get('failure_reason')} | {episode.get('rack_pose')} | "
            f"{episode.get('forces')} |"
        )
    lines += [
        "",
        "Pooled results (forces in N):",
        "",
        "```json",
        json.dumps(diagnostic["pooled"], indent=2),
        "```",
        "",
    ]
    if "error" in diagnostic:
        lines += ["Diagnostic error:", "```", diagnostic["error"], "```", ""]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def episode_indices(value: str) -> set[int]:
    """Parse the optional comma-separated nonnegative episode indices."""
    try:
        indices = {int(part) for part in value.split(",")}
        if any(index < 0 for index in indices):
            raise ValueError("negative index")
        return indices
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated nonnegative indices") from exc


def write_episode_dump(
    out_dir: Path,
    index: int,
    grasp: int | None,
    release: int | None,
    rack_pose: object,
    params: SUCCESS.SuccessParams,
    steps: list[dict[str, object]],
) -> None:
    payload = {
        "episode_index": index,
        "grasp_frame": grasp,
        "release_frame": release,
        "rack_pose": rack_pose,
        "success_params": asdict(params),
        "steps": steps,
    }
    (out_dir / f"dump_episode_{index}.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def run(args: argparse.Namespace, sim_cfg: object) -> int:
    import torch
    from isaaclab.sim import SimulationContext
    from isaaclab.utils import instantiate

    scene_module = load_module("tube_scene", ENV / "vials_to_rack_scene.py")
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    sim = SimulationContext(sim_cfg)
    scene = instantiate(scene_module.build_scene_cfg(args.assets_dir, args.actuators))
    sim.reset()
    robot = scene["robot"]
    rack = scene["rack"]
    tubes = [scene[f"tube_{i}"] for i in range(1, 4)]
    sensor = scene["contact_grasp"]
    dt = data["control"]["physics_dt"]
    substeps = data["control"]["substeps"]
    lying = LAYOUT.pitch_quat_xyzw(data["tubes"]["pitch_deg"])
    identity = (0.0, 0.0, 0.0, 1.0)
    tracker = SUCCESS.SuccessTracker()

    def tensor(values: object) -> object:
        return torch.tensor(values, device=sim.device, dtype=torch.float32)

    def set_joints(values: dict[str, float]) -> None:
        q = robot.data.default_joint_pos.torch.clone()
        for name, value in values.items():
            q[0, robot.joint_names.index(name)] = value
        robot.write_joint_position_to_sim_index(position=q)
        robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(q))
        robot.set_joint_position_target_index(target=q)
        robot.reset()

    def write_pose(obj: object, pose: Sequence[float]) -> None:
        obj.write_root_pose_to_sim_index(root_pose=tensor([pose]))
        obj.write_root_velocity_to_sim_index(root_velocity=torch.zeros((1, 6), device=sim.device))

    def teleport(obj: object, pose: Sequence[float]) -> None:
        write_pose(obj, pose)
        obj.reset()

    def physics_step() -> None:
        scene.write_data_to_sim()
        sim.step(render=False)
        scene.update(dt)

    def forces() -> list[float]:
        matrix = sensor.data.force_matrix_w
        if matrix is None:
            raise RuntimeError("Jaw filtered force_matrix_w unavailable")
        values = matrix.torch
        if values.shape[2] != len(tubes):
            raise RuntimeError(f"Expected three tube filters, got {values.shape}")
        return values[0].norm(dim=-1).sum(dim=0).cpu().tolist()

    dump_steps: list[dict[str, object]] | None = None

    def sample(index: int) -> object:
        states = [
            SUCCESS.VialState(
                force,
                tuple(obj.data.root_pos_w.torch[0].cpu().tolist()),
                tuple(obj.data.root_quat_w.torch[0].cpu().tolist()),
            )
            for obj, force in zip(tubes, forces(), strict=True)
        ]
        rack_position = tuple(rack.data.root_pos_w.torch[0].cpu().tolist())
        rack_quaternion = tuple(rack.data.root_quat_w.torch[0].cpu().tolist())
        if dump_steps is not None:
            dump_steps.append(
                {
                    "step_index": index,
                    "vials": [asdict(state) for state in states],
                    "rack_position": rack_position,
                    "rack_quaternion_xyzw": rack_quaternion,
                }
            )
        return tracker.step(index, states, rack_position, rack_quaternion)

    def reset(yaw: float = 0.0, nominal: bool = False) -> None:
        set_joints(INITIAL_JOINTS)
        teleport(rack, (*data["rack"]["origin_m"], *CORE.yaw_to_quat_xyzw(math.degrees(yaw))))
        poses = (
            [(*pos, *lying) for pos in data["tubes"]["origins_m"]]
            if nominal
            else [(-0.15, 0.0, data["tubes"]["origins_m"][0][2], *lying), *LAYOUT.park_poses(data)]
        )
        for tube, pose in zip(tubes, poses, strict=True):
            teleport(tube, pose)
        sensor.reset()
        tracker.reset()

    def settle(hold: Callable[[], None] | None = None) -> tuple[object, list[float]]:
        peaks = [0.0] * len(tubes)
        result = None
        for index in range(SETTLE_STEPS // substeps):
            for _ in range(substeps):
                if hold is not None:
                    hold()
                physics_step()
                peaks = [max(a, b) for a, b in zip(peaks, forces(), strict=True)]
            result = sample(index)
        return result, peaks

    checks = []

    def record(name: str, expectation: str, measured: object, passed: bool) -> None:
        checks.append(
            {"name": name, "expectation": expectation, "measured": measured, "passed": bool(passed)}
        )

    def axis_x() -> list[float]:
        return [
            abs(
                SUCCESS.rotate_xyzw(
                    tuple(t.data.root_quat_w.torch[0].cpu().tolist()), (0.0, 0.0, 1.0)
                )[0]
            )
            for t in tubes
        ]

    with torch.inference_mode():
        reset(nominal=True)
        spawned_axis = axis_x()
        settle()
        rack_z = float(rack.data.root_pos_w.torch[0, 2])
        tube_z = [float(t.data.root_pos_w.torch[0, 2]) for t in tubes]
        record(
            "S0 settle",
            f"rack z in {RACK_Z}; tube z in {TUBE_Z}",
            {"rack_z": rack_z, "tube_z": tube_z},
            RACK_Z[0] <= rack_z <= RACK_Z[1] and all(TUBE_Z[0] <= z <= TUBE_Z[1] for z in tube_z),
        )
        settled_axis = axis_x()
        record(
            "S1 tube axis",
            f"abs(world local +z x) > {AXIS_X_MIN} at spawn and settled",
            {"spawn": spawned_axis, "settled": settled_axis},
            all(x > AXIS_X_MIN for x in spawned_axis + settled_axis),
        )
        for number, yaw in enumerate(SLOT_YAWS, 2):
            reset(yaw)
            slot = data["rack"]["slots_m"][0]
            local = (slot[0], slot[1], slot[2] + SLOT_DROP_EXTRA_Z)
            q = CORE.yaw_to_quat_xyzw(math.degrees(yaw))
            rotated = SUCCESS.rotate_xyzw(q, local)
            position = tuple(a + b for a, b in zip(data["rack"]["origin_m"], rotated, strict=True))
            teleport(tubes[0], (*position, *identity))
            result, _ = settle()
            vial = result.vials[0]
            record(
                f"S{number} slot, yaw {yaw}",
                "in_box and vertical; local z < 0.1; not placed; no_grasp",
                {**asdict(vial), "failure_reason": tracker.failure_reason()},
                vial.in_box
                and vial.vertical
                and not vial.placed
                and vial.rack_local_position[2] < SLOT_LOCAL_Z_MAX
                and tracker.failure_reason() == "no_grasp",
            )
        reset()
        origin = data["rack"]["origin_m"]
        footprint = data["rack"]["footprint_m"]
        centre = [sum(bounds) / 2 for bounds in footprint]
        teleport(
            tubes[0],
            (
                origin[0] + centre[0],
                origin[1] + centre[1],
                origin[2] + RACK_TOP_Z + SLOT_DROP_EXTRA_Z,
                *lying,
            ),
        )
        result, _ = settle()
        record(
            "S4 lying on rack top",
            "vertical False",
            asdict(result.vials[0]),
            not result.vials[0].vertical,
        )
        reset()
        teleport(
            tubes[0],
            (
                origin[0] + BESIDE_XY[0],
                origin[1] + BESIDE_XY[1],
                data["tubes"]["origins_m"][0][2],
                *identity,
            ),
        )
        result, _ = settle()
        record(
            "S5 beside the rack",
            "in_box False",
            asdict(result.vials[0]),
            not result.vials[0].in_box,
        )
        reset()
        # Three separate parked positions avoid overlapping the otherwise identical first two.
        for i, tube in enumerate(tubes):
            teleport(tube, (-0.15, -0.25 + i * 0.25, data["tubes"]["origins_m"][0][2], *lying))
        _, peaks = settle()
        record(
            "S6 jaw sensor sees only tubes",
            f"each filtered force < {SENSOR_MAX_N} N every step",
            {"peak_force_n": peaks},
            all(f < SENSOR_MAX_N for f in peaks),
        )

        reset()
        teleport(
            tubes[0],
            (
                origin[0] + UPRIGHT_TOP_XY[0],
                origin[1] + UPRIGHT_TOP_XY[1],
                origin[2] + RACK_TOP_Z + UPRIGHT_BOTTOM_OFFSET_Z + UPRIGHT_TOP_CLEARANCE_Z,
                *identity,
            ),
        )
        result, _ = settle()
        vial = result.vials[0]
        record(
            "S7 upright on rack top",
            "vertical True; in_box False; placed False",
            asdict(vial),
            vial.vertical and not vial.in_box and not vial.placed,
        )

        reset()
        slot = data["rack"]["slots_m"][0]
        teleport(tubes[0], (-0.15, 0.0, data["tubes"]["origins_m"][0][2], *lying))
        settle()
        settled_rack_pose = {
            "position": tuple(rack.data.root_pos_w.torch[0].cpu().tolist()),
            "quaternion_xyzw": tuple(rack.data.root_quat_w.torch[0].cpu().tolist()),
        }
        tracker.reset()

        def hold_over_slot() -> None:
            local = (
                slot[0],
                slot[1],
                RACK_TOP_Z + UPRIGHT_BOTTOM_OFFSET_Z + HELD_SLOT_CLEARANCE_Z,
            )
            rotated = SUCCESS.rotate_xyzw(
                tuple(rack.data.root_quat_w.torch[0].cpu().tolist()), local
            )
            position = tuple(
                a + b
                for a, b in zip(rack.data.root_pos_w.torch[0].cpu().tolist(), rotated, strict=True)
            )
            write_pose(tubes[0], (*position, *identity))

        # A free tube falls into the opening; restore pose/zero velocity before every step.
        result, _ = settle(hold=hold_over_slot)
        measured = placement_subpredicates(result.vials[0], tracker.params)
        measured["settled_rack_pose"] = settled_rack_pose
        expected = {
            "vertical": True,
            "xy_in_footprint": True,
            "origin_z_below_course_max": True,
            "bottom_below_rim_margin": False,
            "in_box": False,
            "placed": False,
        }
        record(
            "S7b upright held over slot 0",
            "; ".join(f"{key} {value}" for key, value in expected.items()),
            measured,
            all(measured[key] == value for key, value in expected.items()),
        )

        diagnostic: dict[str, object] = {"episodes": [], "pooled": {}}
        report = {"checks": checks, "diagnostic": diagnostic}
        # Preserve registered measurements even if the optional diagnostic fails.
        write_report(args.out_dir, report)
        try:
            episodes = json.loads(args.episodes_json.read_text(encoding="utf-8"))
            names = [name.removesuffix(".pos") for name in episodes["joint_names"]]
            gripper = names.index("gripper")
            table = UNITS.load_table()
            pooled = {"open_approach": [], "hold": []}
            delays = []
            successes = 0
            episode_peak_forces = []
            body = robot.body_names.index(data["tcp"]["body"])

            def converted(row: Sequence[float]) -> dict[str, float]:
                return UNITS.to_radians(dict(zip(names, row, strict=True)), table)

            def tcp(row: Sequence[float]) -> tuple[float, ...]:
                set_joints(converted(row))
                physics_step()
                return CORE.tcp_point(
                    robot.data.body_pos_w.torch[0, body].cpu().tolist(),
                    robot.data.body_quat_w.torch[0, body].cpu().tolist(),
                    data["tcp"]["offset_m"],
                )

            for episode in episodes["episodes"][: args.max_episodes]:
                state_g = [row[gripper] for row in episode["state"]]
                action_g = [row[gripper] for row in episode["action"]]
                events = CORE.grasp_release_frames(state_g, action_g)
                dump_steps = [] if episode["index"] in args.dump_episodes else None
                if events is None:
                    if dump_steps is not None:
                        write_episode_dump(
                            args.out_dir,
                            episode["index"],
                            None,
                            None,
                            None,
                            tracker.params,
                            dump_steps,
                        )
                    episode_peak_forces.append({"index": episode["index"], "max_force_n": None})
                    diagnostic["episodes"].append(
                        {
                            "index": episode["index"],
                            "success": False,
                            "failure_reason": "no_recorded_hold",
                            "success_step": None,
                            "release_frame": None,
                            "rack_pose": None,
                            "forces": {},
                        }
                    )
                    continue
                grasp, release = events
                grasp_tcp = tcp(episode["state"][grasp])
                release_tcp = tcp(episode["state"][release])
                placement = LAYOUT.rack_pose_for_release(release_tcp[:2], data)
                reset()
                teleport(
                    rack,
                    (*placement.origin_xyz, *CORE.yaw_to_quat_xyzw(math.degrees(placement.yaw))),
                )
                poses = [LAYOUT.tube_pose_for_grasp(grasp_tcp, data), *LAYOUT.park_poses(data)]
                for tube, pose in zip(tubes, poses, strict=True):
                    teleport(tube, pose)
                set_joints(converted(episode["state"][0]))
                tracker.reset()
                sensor.reset()
                windows = {"open_approach": [], "hold": []}
                holds = CORE.find_holds(state_g, action_g)
                peak_force = 0.0
                for index, action in enumerate(episode["action"]):
                    values = converted(action)
                    ids = [robot.joint_names.index(name) for name in names]
                    robot.set_joint_position_target_index(
                        target=tensor([[values[name] for name in names]]), joint_ids=ids
                    )
                    for _ in range(substeps):
                        physics_step()
                        peak_force = max(peak_force, forces()[0])
                    result = sample(index)
                    force = forces()[0]
                    # Open means wider than the recorded closing command by HOLD_GAP raw units.
                    if index < grasp and state_g[index] > action_g[grasp] + CORE.HOLD_GAP:
                        windows["open_approach"].append(force)
                    if any(start <= index < end for start, end in holds):
                        windows["hold"].append(force)
                if dump_steps is not None:
                    write_episode_dump(
                        args.out_dir,
                        episode["index"],
                        grasp,
                        release,
                        asdict(placement),
                        tracker.params,
                        dump_steps,
                    )
                dump_steps = None
                successes += int(result.success)
                episode_peak_forces.append({"index": episode["index"], "max_force_n": peak_force})
                if result.success_step is not None:
                    delays.append(result.success_step - release)
                for key, values in windows.items():
                    pooled[key].extend(values)
                diagnostic["episodes"].append(
                    {
                        "index": episode["index"],
                        "success": result.success,
                        "success_step": result.success_step,
                        "release_frame": release,
                        "failure_reason": tracker.failure_reason(),
                        "rack_pose": asdict(placement),
                        "forces": {key: distribution(values) for key, values in windows.items()},
                    }
                )
            diagnostic["pooled"] = {
                "success_count": successes,
                "tube_1_episode_peak_force_n": episode_peak_forces,
                "median_success_step_minus_release_frame": (
                    statistics.median(delays) if delays else None
                ),
                "forces": {key: distribution(values) for key, values in pooled.items()},
            }
        except Exception:
            diagnostic["error"] = traceback.format_exc()
        write_report(args.out_dir, report)
    return int(not all(check["passed"] for check in checks))


def main(argv: Sequence[str] | None = None) -> int:
    manifest = json.loads((ENV / "course_assets.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets-dir", type=Path, default=FETCH.default_cache_dir(manifest["source"]["commit"])
    )
    parser.add_argument("--episodes-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-episodes", type=int)
    parser.add_argument("--dump-episodes", type=episode_indices, default=set())
    parser.add_argument("--actuators", choices=("course", "usd"), default="course")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--viz")
        parser.add_argument("--device")
        parser.parse_args(argv)
        return 0
    preliminary, _ = parser.parse_known_args(argv)
    errors = check_assets(preliminary.assets_dir)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    if preliminary.max_episodes is not None and preliminary.max_episodes < 1:
        parser.error("--max-episodes must be positive")
    from isaaclab.app import add_launcher_args, launch_simulation
    from isaaclab.sim import SimulationCfg

    add_launcher_args(parser)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    sim_cfg = SimulationCfg(dt=data["control"]["physics_dt"], device=args.device)
    with launch_simulation(sim_cfg, args):
        try:
            code = run(args, sim_cfg)
        except Exception:
            error = traceback.format_exc()
            (args.out_dir / "error.txt").write_text(error, encoding="utf-8")
            if not (args.out_dir / "checks.json").exists():
                write_report(
                    args.out_dir,
                    {
                        "checks": [],
                        "diagnostic": {"episodes": [], "pooled": {}, "error": error},
                        "error": error,
                    },
                )
            traceback.print_exc()
            code = 2
        if code:
            raise SystemExit(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
