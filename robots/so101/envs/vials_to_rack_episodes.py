"""Isaac-only reconstructed demo runtime; no reference source is imported."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import torch
from isaac_demo_replay import CORE, ENV, UNITS, load_module
from isaac_success_check import INITIAL_JOINTS, distribution
from isaaclab.sim import SimulationContext
from isaaclab.utils import instantiate

LAYOUT = load_module("episode_layout", ENV / "vials_to_rack_layout.py")
DIGEST = load_module("episode_state_digest", ENV / "state_digest.py")
SUCCESS = load_module("episode_success", ENV / "vials_to_rack_success.py")


class ReconstructedEpisodes:
    """Own one scene and preserve the diagnostic's write/step ordering."""

    def __init__(
        self,
        assets_dir: Path,
        actuators: str,
        sim_cfg: object,
        joint_names: Sequence[str],
        full_reset: bool = False,
        record: Mapping | None = None,
    ) -> None:
        self.full_reset = full_reset
        self.names = [name.removesuffix(".pos") for name in joint_names]
        self.gripper = self.names.index("gripper")
        self.table = UNITS.load_table()
        scene_module = load_module("tube_scene", ENV / "vials_to_rack_scene.py")
        self.data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
        self.sim = SimulationContext(sim_cfg)
        self.scene = instantiate(scene_module.build_scene_cfg(assets_dir, actuators, camera=record))
        self.sim.reset()
        if record is not None:
            self.record = record
            self.camera = self.scene["video_camera"]
            # Isaac Lab look-at helper uses world-space eyes/targets and the stage up axis.
            self.camera.set_world_poses_from_view(
                self.tensor([record["eye"]]), self.tensor([record["target"]])
            )
        self.robot = self.scene["robot"]
        self.rack = self.scene["rack"]
        self.tubes = [self.scene[f"tube_{i}"] for i in range(1, 4)]
        self.sensor = self.scene["contact_grasp"]
        self.dt = self.data["control"]["physics_dt"]
        self.substeps = self.data["control"]["substeps"]
        self.lying = LAYOUT.pitch_quat_xyzw(self.data["tubes"]["pitch_deg"])
        self.identity = (0.0, 0.0, 0.0, 1.0)
        self.tracker = SUCCESS.SuccessTracker()

        self.dump_steps: list[dict[str, object]] = []
        self.seed = 0
        self.action_space = "joint"
        self.uses_object_state = False
        self.policy: object = None
        # TCP action space: fraction of each IK step applied, and the furthest a joint target may
        # lead the measured joint (rad).
        self.ik_gain = 0.2
        self.ik_max_lead = 0.25

    def tensor(self, values: object) -> object:
        return torch.tensor(values, device=self.sim.device, dtype=torch.float32)

    def set_joints(self, values: dict[str, float]) -> None:
        q = self.robot.data.default_joint_pos.torch.clone()
        for name, value in values.items():
            q[0, self.robot.joint_names.index(name)] = value
        self.robot.write_joint_position_to_sim_index(position=q)
        self.robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(q))
        self.robot.set_joint_position_target_index(target=q)
        self.robot.reset()

    def write_pose(self, obj: object, pose: Sequence[float]) -> None:
        obj.write_root_pose_to_sim_index(root_pose=self.tensor([pose]))
        obj.write_root_velocity_to_sim_index(
            root_velocity=torch.zeros((1, 6), device=self.sim.device)
        )

    def teleport(self, obj: object, pose: Sequence[float]) -> None:
        self.write_pose(obj, pose)
        obj.reset()

    def physics_step(self) -> None:
        self.scene.write_data_to_sim()
        self.sim.step(render=False)
        self.scene.update(self.dt)

    def forces(self) -> list[float]:
        matrix = self.sensor.data.force_matrix_w
        if matrix is None:
            raise RuntimeError("Jaw filtered force_matrix_w unavailable")
        values = matrix.torch
        if values.shape[2] != len(self.tubes):
            raise RuntimeError(f"Expected three tube filters, got {values.shape}")
        return values[0].norm(dim=-1).sum(dim=0).cpu().tolist()

    def sample(self, index: int) -> object:
        states = [
            SUCCESS.VialState(
                force,
                tuple(obj.data.root_pos_w.torch[0].cpu().tolist()),
                tuple(obj.data.root_quat_w.torch[0].cpu().tolist()),
            )
            for obj, force in zip(self.tubes, self.forces(), strict=True)
        ]
        rack_position = tuple(self.rack.data.root_pos_w.torch[0].cpu().tolist())
        rack_quaternion = tuple(self.rack.data.root_quat_w.torch[0].cpu().tolist())
        if self.dump_steps is not None:
            self.dump_steps.append(
                {
                    "step_index": index,
                    "vials": [asdict(state) for state in states],
                    "rack_position": rack_position,
                    "rack_quaternion_xyzw": rack_quaternion,
                }
            )
        return self.tracker.step(index, states, rack_position, rack_quaternion)

    def _full_reset(self) -> None:
        # Isaac Lab 3.0: simulation_context.py resets physics and invokes reset callbacks.
        # interactive_scene.py resets entities in place; fetch their handles afterward.
        self.sim.reset(soft=False)
        self.scene.reset()
        self._handles()

    def reset_layout(self, yaw: float = 0.0, nominal: bool = False) -> None:
        self.set_joints(INITIAL_JOINTS)
        self.teleport(
            self.rack,
            (*self.data["rack"]["origin_m"], *CORE.yaw_to_quat_xyzw(math.degrees(yaw))),
        )
        poses = (
            [(*pos, *self.lying) for pos in self.data["tubes"]["origins_m"]]
            if nominal
            else [
                (-0.15, 0.0, self.data["tubes"]["origins_m"][0][2], *self.lying),
                *LAYOUT.park_poses(self.data),
            ]
        )
        for tube, pose in zip(self.tubes, poses, strict=True):
            self.teleport(tube, pose)
        self.sensor.reset()
        self.tracker.reset()

    def _handles(self) -> None:
        self.robot = self.scene["robot"]
        self.rack = self.scene["rack"]
        self.tubes = [self.scene[f"tube_{i}"] for i in range(1, 4)]
        self.sensor = self.scene["contact_grasp"]

    def converted(self, row: Sequence[float]) -> dict[str, float]:
        return UNITS.to_radians(dict(zip(self.names, row, strict=True)), self.table)

    def grasp_release_tcps(self, episode: dict) -> tuple | None:
        state_g = [row[self.gripper] for row in episode["state"]]
        action_g = [row[self.gripper] for row in episode["action"]]
        events = CORE.grasp_release_frames(state_g, action_g)
        if events is None:
            return None
        points = []
        body = self.robot.body_names.index(self.data["tcp"]["body"])
        for frame in events:
            self.set_joints(self.converted(episode["state"][frame]))
            self.physics_step()
            points.append(
                CORE.tcp_point(
                    self.robot.data.body_pos_w.torch[0, body].cpu().tolist(),
                    self.robot.data.body_quat_w.torch[0, body].cpu().tolist(),
                    self.data["tcp"]["offset_m"],
                )
            )
        return (*events, *points)

    def run_reconstructed_episode(
        self,
        episode: dict,
        record_steps: bool,
        action_source: Callable[[int, Mapping[str, object]], Sequence[float]] | None = None,
    ) -> dict:
        started = time.perf_counter()
        self.dump_steps = []
        with torch.inference_mode():
            if self.full_reset:
                # Before the TCP probe too, so nothing from the previous episode reaches it.
                self._full_reset()
            events = self.grasp_release_tcps(episode)
            result_dict = {
                "index": episode["index"],
                "success": False,
                "success_step": None,
                "failure_reason": "no_recorded_hold",
                "release_frame": None,
                "rack_pose": None,
                "forces": {},
            }
            if events is not None:
                grasp, release, grasp_tcp, release_tcp = events
                placement = LAYOUT.rack_pose_for_release(release_tcp[:2], self.data)
                self.reset_layout()
                self.teleport(
                    self.rack,
                    (
                        *placement.origin_xyz,
                        *CORE.yaw_to_quat_xyzw(math.degrees(placement.yaw)),
                    ),
                )
                poses = [
                    LAYOUT.tube_pose_for_grasp(grasp_tcp, self.data),
                    *LAYOUT.park_poses(self.data),
                ]
                for tube, pose in zip(self.tubes, poses, strict=True):
                    self.teleport(tube, pose)
                self.set_joints(self.converted(episode["state"][0]))
                self.tracker.reset()
                self.sensor.reset()
                windows = {"open_approach": [], "hold": []}
                state_g = [row[self.gripper] for row in episode["state"]]
                action_g = [row[self.gripper] for row in episode["action"]]
                holds = CORE.find_holds(state_g, action_g)
                peak_force = 0.0
                for index, action in enumerate(episode["action"]):
                    if action_source is not None:
                        radians = {
                            name: float(
                                self.robot.data.joint_pos.torch[
                                    0, self.robot.joint_names.index(name)
                                ].item()
                            )
                            for name in self.names
                        }
                        observation = {
                            "step": index,
                            "joint_pos": UNITS.to_lerobot(radians, self.table),
                        }
                        action = action_source(index, observation)
                    values = self.converted(action)
                    ids = [self.robot.joint_names.index(name) for name in self.names]
                    self.robot.set_joint_position_target_index(
                        target=self.tensor([[values[name] for name in self.names]]), joint_ids=ids
                    )
                    for _ in range(self.substeps):
                        self.physics_step()
                        peak_force = max(peak_force, self.forces()[0])
                    result = self.sample(index)
                    force = self.forces()[0]
                    if index < grasp and state_g[index] > action_g[grasp] + CORE.HOLD_GAP:
                        windows["open_approach"].append(force)
                    if any(start <= index < end for start, end in holds):
                        windows["hold"].append(force)
                result_dict.update(
                    success=result.success,
                    success_step=result.success_step,
                    failure_reason=self.tracker.failure_reason(),
                    release_frame=release,
                    rack_pose=asdict(placement),
                    forces={key: distribution(values) for key, values in windows.items()},
                )
        canonical = json.dumps(
            self.dump_steps, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        result_dict["trajectory_sha256"] = hashlib.sha256(canonical).hexdigest()
        result_dict["wall_seconds"] = time.perf_counter() - started
        if record_steps:
            result_dict["steps"] = self.dump_steps
        return result_dict

    def object_state(self) -> dict[str, object]:
        def pose(obj: object) -> dict[str, list[float]]:
            return {
                "pos": obj.data.root_pos_w.torch[0].cpu().tolist(),
                "quat_xyzw": obj.data.root_quat_w.torch[0].cpu().tolist(),
            }

        rack = pose(self.rack)
        body = self.robot.body_names.index(self.data["tcp"]["body"])
        position = self.robot.data.body_pos_w.torch[0, body].cpu().tolist()
        quaternion = self.robot.data.body_quat_w.torch[0, body].cpu().tolist()
        return {
            "tubes": [pose(tube) for tube in self.tubes],
            "rack": rack,
            "slots_w": [
                list(CORE.tcp_point(rack["pos"], rack["quat_xyzw"], slot))
                for slot in self.data["rack"]["slots_m"]
            ],
            "tcp": {
                "pos": list(CORE.tcp_point(position, quaternion, self.data["tcp"]["offset_m"])),
                "quat_xyzw": quaternion,
            },
        }

    def apply_policy_action(self, action: Sequence[float]) -> None:
        if self.action_space == "joint":
            values = self.converted(action)
        else:
            from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg

            helper = load_module("task_tcp_ik", ENV / "tcp_ik.py")
            target, pitch, roll, grip = helper.split_action(action)
            if self.ik is None:
                # Isaac Lab 3.0 cfg defaults: ik_params={"lambda_val": 0.01} for DLS.
                self.ik = DifferentialIKController(
                    DifferentialIKControllerCfg(
                        command_type="position", use_relative_mode=False, ik_method="dls"
                    ),
                    num_envs=1,
                    device=self.sim.device,
                )
            arm = [
                self.robot.joint_names.index(n)
                for n in ("shoulder_pan", "shoulder_lift", "elbow_flex")
            ]
            body = self.robot.body_names.index(self.data["tcp"]["body"])
            objects = self.object_state()
            tcp = objects["tcp"]["pos"]
            position = self.robot.data.body_pos_w.torch[0, body].cpu().tolist()
            quaternion = self.robot.data.body_quat_w.torch[:, body]
            jacobian = self.robot.data.body_link_jacobian_w.torch[0, body - 1][:, arm]
            shifted = helper.shift_jacobian(
                jacobian.cpu().tolist(), [a - b for a, b in zip(tcp, position, strict=True)]
            )
            self.ik.set_command(self.tensor([target]), ee_quat=quaternion)
            solved = (
                self.ik.compute(
                    self.tensor([tcp]),
                    quaternion,
                    self.tensor([shifted]),
                    # Integrate on the previous target, not the measured position: the course's
                    # low gains let gravity hold the arm short of its target, and q + dq from the
                    # measured q would stall at that offset forever.
                    self.robot.data.joint_pos_target.torch[:, arm],
                )[0]
                .cpu()
                .tolist()
            )
            solved = helper.integrate(
                self.robot.data.joint_pos_target.torch[0, arm].cpu().tolist(),
                solved,
                self.robot.data.joint_pos.torch[0, arm].cpu().tolist(),
                self.ik_gain,
                self.ik_max_lead,
            )
            raw = {name: 0.0 for name in self.names}
            raw["gripper"] = grip
            values = UNITS.to_radians(raw, self.table)
            values.update(zip(("shoulder_pan", "shoulder_lift", "elbow_flex"), solved, strict=True))
            # The three pitch joints have parallel axes: the gripper's pitch is their sum, which is
            # what the course demos hold steady (wrist_flex alone varies twice as much).
            values.update(wrist_flex=pitch - solved[1] - solved[2], wrist_roll=roll)
            limits = self.robot.data.joint_pos_limits.torch[0]
            values = {
                name: helper.clamp(
                    value, *limits[self.robot.joint_names.index(name)].cpu().tolist()
                )
                for name, value in values.items()
            }
        ids = [self.robot.joint_names.index(name) for name in self.names]
        self.robot.set_joint_position_target_index(
            target=self.tensor([[values[name] for name in self.names]]), joint_ids=ids
        )

    def state_digest(self) -> str:
        values = []
        for obj in [*self.tubes, self.rack]:
            values.extend(obj.data.root_pos_w.torch[0].cpu().tolist())
            values.extend(obj.data.root_quat_w.torch[0].cpu().tolist())
        values.extend(self.robot.data.joint_pos.torch[0].cpu().tolist())
        return DIGEST.state_digest(values)

    def run_policy_episode(
        self,
        layout_source: Callable[[], None],
        action_source: Callable[[int, Mapping[str, object]], Sequence[float]],
        horizon: int,
        record_steps: bool,
        record_dir: Path | None = None,
        expected_rack_position: Sequence[float] | None = None,
    ) -> dict[str, object]:
        if type(horizon) is not int or horizon <= 0:
            raise ValueError("horizon must be a positive integer")
        frames = 0
        if record_dir is not None:
            import cv2

            record_dir.mkdir(parents=True, exist_ok=True)
            every_n_steps = self.record["every_n_steps"]
        started = time.perf_counter()
        self.dump_steps = []
        limit_steps = 0
        diagnostics = []
        with torch.inference_mode():
            if self.full_reset:
                self._full_reset()
            self.reset_layout(nominal=True)
            layout_source()
            self.set_joints(INITIAL_JOINTS)
            self.tracker.reset()
            self.sensor.reset()
            self.ik = None
            rack_pose = {
                "pos": self.rack.data.root_pos_w.torch[0].cpu().tolist(),
                "quat_xyzw": self.rack.data.root_quat_w.torch[0].cpu().tolist(),
            }
            if expected_rack_position is not None and any(
                not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)
                for actual, expected in zip(rack_pose["pos"], expected_rack_position, strict=True)
            ):
                raise RuntimeError("Initial rack position is stale: differs from sampled layout")
            initial_state_sha256 = self.state_digest()
            for index in range(horizon):
                radians = {
                    name: float(
                        self.robot.data.joint_pos.torch[
                            0, self.robot.joint_names.index(name)
                        ].item()
                    )
                    for name in self.names
                }
                observation = {"step": index, "joint_pos": UNITS.to_lerobot(radians, self.table)}
                if self.uses_object_state:
                    observation["objects"] = self.object_state()
                action = action_source(index, observation)
                self.apply_policy_action(action)
                for _ in range(self.substeps):
                    self.physics_step()
                result = self.sample(index)
                if record_dir is not None and index % every_n_steps == every_n_steps - 1:
                    self.sim.render()
                    self.camera.update(0.0, force_recompute=True)
                    rgb = self.camera.data.output["rgb"].torch[0, ..., :3].cpu().numpy()
                    path = record_dir / f"frame_{frames:04d}.jpg"
                    if not cv2.imwrite(
                        str(path),
                        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, self.record["jpeg_quality"]],
                    ):
                        raise OSError(f"Could not write frame: {path}")
                    frames += 1
                wrist = self.robot.joint_names.index("wrist_flex")
                measured = float(self.robot.data.joint_pos.torch[0, wrist].item())
                limits = self.robot.data.joint_pos_limits.torch[0, wrist].cpu().tolist()
                limit_steps += int(min(abs(measured - bound) for bound in limits) <= 0.05)
                if record_steps:
                    tcp = self.object_state()["tcp"]["pos"]
                    target = list(action[:3]) if self.action_space == "tcp" else None
                    diagnostics.append(
                        {
                            **self.dump_steps[-1],
                            "phase": getattr(
                                self.policy, "command_phase", getattr(self.policy, "phase", None)
                            ),
                            "tcp_target": target,
                            "tcp_measured": tcp,
                            "tcp_error": math.dist(target, tcp) if target is not None else None,
                            "joint_pos": self.robot.data.joint_pos.torch[0].cpu().tolist(),
                            "gripper_force": self.forces(),
                            "tracker": asdict(result),
                        }
                    )
                if result.success:
                    break
        canonical = json.dumps(
            self.dump_steps, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        report = {
            "index": self.seed,
            "success": result.success,
            "success_step": result.success_step,
            "failure_reason": self.tracker.failure_reason(),
            "steps_run": index + 1,
            "trajectory_sha256": hashlib.sha256(canonical).hexdigest(),
            "wall_seconds": time.perf_counter() - started,
            "rack_pose": rack_pose,
            "release_frame": None,
            "forces": None,
            "wrist_flex_limit_steps": limit_steps,
            "initial_state_sha256": initial_state_sha256,
            "final_state_sha256": self.state_digest(),
            "metric": min(vial.box_signed_distance for vial in result.vials),
        }
        if record_steps:
            report["steps"] = diagnostics
        if record_dir is not None:
            report["frames"] = frames
        return report
