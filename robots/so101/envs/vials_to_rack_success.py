# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Ported from isaac-sim/Sim-to-Real-SO-101-Workshop @ ce807d99724cb65671abec01f908a2fcb4a6eab7,
# source/sim_to_real_so101/mdp/terms.py (vial_placed_on_rack, vial_placed_on_rack_termination).
# Modified for PipeRobot: per-instance state, one history advance per step, one environment,
# stdlib only, failure reasons.
"""Pure success tracking, with per-instance state instead of course function attributes.

The course shares placement/history state between environments and tasks, and its Eval
observation and termination both advance history. Here each step advances it exactly once;
reset() clears all episode state. All quaternions are XYZW; the course used WXYZ.

Deliberate judgement changes: use 5 N to separate pushes from genuine grasps, and require
the lowest tube end below the rack rim by a margin. The course's origin z < 0.1 box
alone admits an upright tube standing on top of the rack.
"""

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]


@dataclass(frozen=True)
class SuccessParams:
    warmup_steps: int = 30
    grasp_history_window: int = 20
    # The course uses 2 N; 5 N sits in the measured gap: pushes <= 1.98 N,
    # genuine grasp medians 10-19 N, about 2.5x margin on each side.
    # See ADR 0028.
    force_threshold_n: float = 5.0
    tube_axis_span_m: tuple[float, float] = (-0.017, 0.0995)  # Vial_opaque.usda
    rack_rim_z: float = 0.073  # Vial_rack_simple.usda, rack-local top surface
    rim_margin_m: float = 0.02
    rack_local_x_min: float = 0.0
    rack_local_x_max: float = 0.12
    rack_local_y_min: float = 0.0
    rack_local_y_max: float = 0.12
    rack_local_z_max: float = 0.1
    vertical_threshold: float = 0.7
    confirm_steps: int = 25

    def __post_init__(self) -> None:
        if self.warmup_steps < 0 or min(self.grasp_history_window, self.confirm_steps) < 1:
            raise ValueError("Invalid step window")


@dataclass(frozen=True)
class VialState:
    """Force is the sum of contact force norms over the jaw bodies, in newtons."""

    force_n: float
    position: Vec3
    quaternion_xyzw: Quat


@dataclass(frozen=True)
class VialResult:
    grasped_now: bool
    recently_grasped: bool
    vertical: bool
    in_box: bool
    placed: bool
    rack_local_position: Vec3
    bottom_local_z: float


@dataclass(frozen=True)
class StepResult:
    success: bool
    vials: tuple[VialResult, ...]
    confirmation_count: int
    success_step: int | None


def rotate_xyzw(q: Quat, v: Vec3) -> Vec3:
    """Rotate by a normalized XYZW quaternion (the course instead used WXYZ)."""
    norm = math.sqrt(sum(a * a for a in q))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Expected finite nonzero quaternion")
    x, y, z, w = (a / norm for a in q)
    ux = 2 * (y * v[2] - z * v[1])
    uy = 2 * (z * v[0] - x * v[2])
    uz = 2 * (x * v[1] - y * v[0])
    return (
        v[0] + w * ux + y * uz - z * uy,
        v[1] + w * uy + z * ux - x * uz,
        v[2] + w * uz + x * uy - y * ux,
    )


class SuccessTracker:
    def __init__(self, params: SuccessParams | None = None) -> None:
        self.params = params if params is not None else SuccessParams()
        self.reset()

    def reset(self) -> None:
        self._history: list[deque[bool]] = []
        self._placed: list[bool] = []
        self._last_step: int | None = None
        self._ever_grasped = False
        self._count = 0
        self.success_step: int | None = None

    def step(
        self,
        step_index: int,
        vials: Sequence[VialState],
        rack_position: Vec3,
        rack_quaternion_xyzw: Quat,
    ) -> StepResult:
        """Consume one step, starting at 0, with consecutive indices within an episode.

        Index counts env.step calls before this sample. Warmup ends at index warmup_steps.
        The release sample itself counts as the first confirmation step.
        """
        expected = 0 if self._last_step is None else self._last_step + 1
        if step_index != expected:
            raise ValueError(f"Expected step index {expected}, got {step_index}")
        if not vials or (self._history and len(vials) != len(self._history)):
            raise ValueError("Expected a stable nonzero vial count")
        p = self.params
        inverse = tuple(-a if i < 3 else a for i, a in enumerate(rack_quaternion_xyzw))
        # Compute geometry before mutating episode state.
        local_positions = [
            rotate_xyzw(
                inverse, tuple(a - b for a, b in zip(v.position, rack_position, strict=True))
            )
            for v in vials
        ]
        axes = [rotate_xyzw(v.quaternion_xyzw, (0.0, 0.0, 1.0)) for v in vials]
        verticals = [abs(axis[2]) > p.vertical_threshold for axis in axes]
        local_axes = [rotate_xyzw(inverse, axis) for axis in axes]
        if not self._history:
            self._history = [deque(maxlen=p.grasp_history_window) for _ in vials]
            self._placed = [False] * len(vials)
        results = []
        for i, vial in enumerate(vials):
            grasped = vial.force_n > p.force_threshold_n
            self._history[i].append(grasped)
            recent = any(self._history[i])
            x, y, z = local_positions[i]
            bottom_local_z = z + min(end * local_axes[i][2] for end in p.tube_axis_span_m)
            in_box = (
                p.rack_local_x_min <= x <= p.rack_local_x_max
                and p.rack_local_y_min <= y <= p.rack_local_y_max
                and z < p.rack_local_z_max
                and bottom_local_z < p.rack_rim_z - p.rim_margin_m
            )
            if step_index >= p.warmup_steps:
                self._ever_grasped |= grasped
                self._placed[i] |= verticals[i] and in_box and recent and not grasped
            results.append(
                VialResult(
                    grasped,
                    recent,
                    verticals[i],
                    in_box,
                    self._placed[i],
                    local_positions[i],
                    bottom_local_z,
                )
            )
        valid = any(v.placed and v.vertical and v.in_box and not v.grasped_now for v in results)
        self._count = self._count + 1 if valid else 0
        if self.success_step is None and self._count >= p.confirm_steps:
            self.success_step = step_index
        self._last_step = step_index
        return StepResult(
            self.success_step is not None, tuple(results), self._count, self.success_step
        )

    def failure_reason(self) -> str | None:
        if self.success_step is not None:
            return None
        if not self._ever_grasped:
            return "no_grasp"
        return "placement_not_held" if any(self._placed) else "not_placed"
