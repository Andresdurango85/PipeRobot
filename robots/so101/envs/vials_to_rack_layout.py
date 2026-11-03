"""Deterministic reconstruction of tube and rack poses; metres and XYZW throughout."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def pitch_quat_xyzw(degrees: float) -> tuple[float, float, float, float]:
    half = math.radians(degrees) / 2
    return (0.0, math.sin(half), 0.0, math.cos(half))


def tube_pose_for_grasp(
    grasp_tcp_xyz: Sequence[float], scene: Mapping[str, object], along_axis_m: float | None = None
) -> tuple[float, ...]:
    tubes = scene["tubes"]
    if along_axis_m is None:
        along_axis_m = sum(tubes["axis_span_m"]) / 2
    return (
        grasp_tcp_xyz[0] - along_axis_m,
        grasp_tcp_xyz[1],
        tubes["origins_m"][0][2],
        *pitch_quat_xyzw(tubes["pitch_deg"]),
    )


@dataclass(frozen=True)
class RackPose:
    origin_xyz: tuple[float, float, float]
    yaw: float
    slot_index: int
    offset: tuple[float, float]
    inside_dr_box: bool


def rack_pose_for_release(release_tcp_xy: Sequence[float], scene: Mapping[str, object]) -> RackPose:
    """Keep exact slot alignment, ranking box violation before nominal displacement.

    Clamp only for scoring: clamping the returned origin would destroy exact alignment.
    Ties prefer smaller nominal displacement, then smaller absolute yaw and slot index.
    """
    rack = scene["rack"]
    nominal = rack["origin_m"]
    candidates = []
    low, high = rack["yaw_range_rad"]
    for i in range(201):
        yaw = low + (high - low) * i / 200
        c, s = math.cos(yaw), math.sin(yaw)
        for slot_index, (x, y, _) in enumerate(rack["slots_m"]):
            origin = (
                release_tcp_xy[0] - c * x + s * y,
                release_tcp_xy[1] - s * x - c * y,
                nominal[2],
            )
            offset = (origin[0] - nominal[0], origin[1] - nominal[1])
            bounds = (rack["x_range_m"], rack["y_range_m"])
            clamped = tuple(max(a, min(b, d)) for d, (a, b) in zip(offset, bounds, strict=True))
            violation = math.dist(offset, clamped)
            inside = violation < 1e-12
            score = (0.0 if inside else violation, math.hypot(*offset), abs(yaw), slot_index)
            candidates.append((score, RackPose(origin, yaw, slot_index, offset, inside)))
    return min(candidates, key=lambda item: item[0])[1]


def park_poses(scene: Mapping[str, object]) -> tuple[tuple[float, ...], ...]:
    tubes = scene["tubes"]
    return tuple(
        (-0.15, y, tubes["origins_m"][0][2], *pitch_quat_xyzw(tubes["pitch_deg"]))
        for y in (-0.25, 0.25)
    )
