"""Privileged waypoint scaffold for tuning in Isaac; all lengths are metres."""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from piperobot.adapters.isaaclab.specs import load_module

ENV = Path(__file__).resolve().parents[1] / "envs"
UNITS = load_module("scripted_joint_units", ENV / "joint_units.py")
GEOMETRY = load_module("scripted_geometry", ENV / "vials_to_rack_success.py")

DEFAULTS: dict[str, float | int] = {
    # Gripper pitch = shoulder_lift + elbow_flex + wrist_flex (rad), medians of the 75 demos.
    "grasp_pitch": 1.025,
    "release_pitch": -0.172,
    "grasp_wrist_roll": -1.41,
    "release_wrist_roll": -1.59,
    "roll_per_pan": 0.0,
    "pan_ref": 0.31,
    "gripper_open": 41,
    "gripper_closed": 5,
    "approach_dz": 0.06,
    "carry_z": 0.15,
    "transfer_z": 0.19,
    "release_z": 0.17,
    "grasp_along_axis_m": 0.04,
    "min_along_axis_m": 0.015,
    "max_grasp_x_m": 0.295,
    "grasp_lateral_m": 0.02,
    "grasp_dz": -0.008,
    "slot_index": 0,
    "tolerance_m": 0.004,
    "dwell_steps": 20,
}
PHASES = (
    "approach",
    "descend",
    "close",
    "lift",
    "reorient",
    "transfer",
    "insert",
    "open",
    "retreat",
)


class ScriptedPickPlace:
    uses_object_state = True
    action_space = "tcp"

    def __init__(self, **params: float | int) -> None:
        unknown = params.keys() - DEFAULTS.keys()
        if unknown:
            raise ValueError(f"Unknown parameters: {sorted(unknown)}")
        self.params = DEFAULTS | params
        if not all(
            type(value) in (int, float) and math.isfinite(value) for value in self.params.values()
        ):
            raise ValueError("Parameters must be finite numbers")
        if self.params["tolerance_m"] <= 0:
            raise ValueError("tolerance_m must be positive")
        if type(self.params["slot_index"]) is not int or not 0 <= self.params["slot_index"] < 4:
            raise ValueError("slot_index must be an integer in 0..3")
        if type(self.params["dwell_steps"]) is not int or self.params["dwell_steps"] < 1:
            raise ValueError("dwell_steps must be a positive integer")
        self.table = UNITS.load_table()
        self.reset(0)

    def reset(self, seed: int) -> None:
        self.seed = seed
        self.phase = "approach"
        self.elapsed = 0
        self.grasp: list[float] | None = None
        self.place: list[float] | None = None

    def grasp_roll(self, pan: float) -> float:
        p = self.params
        return p["grasp_wrist_roll"] + p["roll_per_pan"] * (pan - p["pan_ref"])

    def act(self, observation: Mapping[str, object]) -> Sequence[float]:
        objects = cast(dict[str, object], observation["objects"])
        tubes = cast(list[dict[str, list[float]]], objects["tubes"])
        tcp = cast(dict[str, list[float]], objects["tcp"])["pos"]
        slots = cast(list[list[float]], objects["slots_w"])
        p = self.params
        if self.grasp is None:
            tube = tubes[0]
            axis = GEOMETRY.rotate_xyzw(tube["quat_xyzw"], (0.0, 0.0, 1.0))
            # Horizontal direction across the tube, for the jaw that does not sit on the TCP.
            across = (-axis[1], axis[0], 0.0)
            # Grasp nearer the robot when the tube is far, so the TCP stays within reach while the
            # gripper keeps its grasp pitch; never closer to the tube's end than min_along_axis_m.
            along = max(
                p["min_along_axis_m"],
                min(p["grasp_along_axis_m"], p["max_grasp_x_m"] - tube["pos"][0]),
            )
            self.grasp = [
                a + b * along + c * p["grasp_lateral_m"]
                for a, b, c in zip(tube["pos"], axis, across, strict=True)
            ]
            self.grasp[2] += p["grasp_dz"]
        target = self.grasp.copy()
        if self.phase == "approach":
            target[2] += p["approach_dz"]
        if self.phase in ("lift", "reorient"):
            target[2] = p["carry_z"]
        if self.phase in ("transfer", "insert"):
            # Steer the held tube, not the TCP, over the slot: the tube hangs off the TCP by
            # however far off-centre it was grasped.
            slot = slots[int(p["slot_index"])]
            held = tubes[0]["pos"]
            self.place = [tcp[0] + slot[0] - held[0], tcp[1] + slot[1] - held[1]]
        if self.phase in ("transfer", "insert", "open", "retreat"):
            if self.place is None:
                raise RuntimeError("No place target: transfer must run before later phases")
            heights = {
                "transfer": p["transfer_z"],
                "insert": p["release_z"],
                "open": p["release_z"],
            }
            target = [*self.place, heights.get(self.phase, p["transfer_z"])]
        released_pose = self.phase in ("reorient", "transfer", "insert", "open", "retreat")
        joints = cast(dict[str, float], observation["joint_pos"])
        pan = UNITS.to_radians(joints, self.table)["shoulder_pan"]
        pitch = p["release_pitch"] if released_pose else p["grasp_pitch"]
        roll = p["release_wrist_roll"] if released_pose else self.grasp_roll(pan)
        grip = (
            p["gripper_open"]
            if self.phase in ("approach", "descend", "open", "retreat")
            else p["gripper_closed"]
        )
        self.elapsed += 1
        reached = (
            self.elapsed >= p["dwell_steps"]
            if self.phase in ("close", "reorient", "open")
            else math.dist(tcp, target) <= p["tolerance_m"]
        )
        self.command_phase = self.phase
        if reached and self.phase != "retreat":
            self.phase = PHASES[PHASES.index(self.phase) + 1]
            self.elapsed = 0
        return [*target, pitch, roll, grip]
