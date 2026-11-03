"""Object-free replay analysis. Holds use half-open frame intervals [start, end)."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

# Fixed on 2026-11-02 before the first replay run; changing them needs a new ADR.
HOLD_GAP = 5.0
HOLD_MIN_FRAMES = 15
ARM_P95_MAX = 5.0
ARM_ABS_MAX = 15.0
GRIPPER_P95_MAX = 5.0
GRIPPER_ABS_MAX = 15.0
RELEASE_SETTLE_FRAMES = 15
LIMIT_SHARE_MAX = 0.01
LIMIT_MARGIN_RAD = 0.0087
CLUSTER_MARGIN_M = 0.03
CLUSTER_SHARE_MIN = 0.90
MIN_EPISODES_WITH_EVENTS = 70
OFFSET_AGREEMENT_M = 0.02
OFFSET_MAX_M = 0.10
YAW_GRID = 201

RULES = [
    "GO: at least MIN_EPISODES_WITH_EVENTS episodes have both events; tracking passes (arm "
    "and gripper p95 and max); both limit shares <= LIMIT_SHARE_MAX; at least "
    "CLUSTER_SHARE_MIN of grasp points are within tube_radius + CLUSTER_MARGIN_M of the tube "
    "region and at least CLUSTER_SHARE_MIN of release points are within that distance of the "
    "rack-slot region.",
    "BASE_OFFSET: everything but the clusters passes; d_g = median grasp xy minus the nominal "
    "grasp centre (mean over tubes of origin + axis-span midpoint: (0.27125, -0.08)), d_p = median "
    "release xy minus the nominal place centre (rack origin + mean slot xy: (0.24025, 0.14)); if "
    "|d_g - d_p| <= OFFSET_AGREEMENT_M and |(d_g + d_p) / 2| <= OFFSET_MAX_M, shift every "
    "point by -(d_g + d_p) / 2 and re-run the cluster rule; if it now passes, the verdict is "
    "BASE_OFFSET and the report states the offset vector in metres.",
    "NO_GO: anything else. The report lists every rule that failed.",
    "Rate: the report gives pooled arm p95 and mean episode duration (frames / control_hz) for "
    "each substep count, and names the count with the lower pooled arm p95 as the measured rate. "
    "The final verdict is the verdict at the measured rate. z of grasp and release points is "
    "reported (median, p5, p95) but not judged.",
]


def control_hz(entry: Mapping[str, Any]) -> float:
    override = entry.get("control_hz")
    value = float(entry["metadata_fps"] if override is None else override)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Control rate must be positive and finite")
    return value


def substeps_per_frame(control_hz: float, physics_dt: float) -> int:
    if control_hz <= 0 or physics_dt <= 0:
        raise ValueError("Rate and dt must be positive")
    value = 1 / (control_hz * physics_dt)
    if (
        not math.isfinite(value)
        or round(value) < 1
        or not math.isclose(value, round(value), rel_tol=1e-9, abs_tol=0)
    ):
        raise ValueError("Non-integer physics substeps")
    return round(value)


def find_holds(
    state_gripper: Sequence[float], action_gripper: Sequence[float]
) -> list[tuple[int, int]]:
    if len(state_gripper) != len(action_gripper):
        raise ValueError("Unequal gripper series lengths")
    holds = []
    start = None
    gaps = [s - a for s, a in zip(state_gripper, action_gripper, strict=True)]
    for i, gap in enumerate([*gaps, -math.inf]):
        if gap >= HOLD_GAP:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= HOLD_MIN_FRAMES:
                holds.append((start, i))
            start = None
    return holds


def grasp_release_frames(
    state_gripper: Sequence[float], action_gripper: Sequence[float]
) -> tuple[int, int] | None:
    holds = find_holds(state_gripper, action_gripper)
    return (holds[0][0], min(holds[-1][1], len(state_gripper) - 1)) if holds else None


def yaw_to_quat_xyzw(yaw_deg: float) -> tuple[float, float, float, float]:
    half = math.radians(yaw_deg) / 2
    return (0.0, 0.0, math.sin(half), math.cos(half))


def quat_rotate_xyzw(q: Sequence[float], v: Sequence[float]) -> tuple[float, ...]:
    x, y, z, w = q
    norm = math.sqrt(sum(a * a for a in q))
    if norm == 0:
        raise ValueError("Zero quaternion")
    x, y, z, w = (a / norm for a in (x, y, z, w))
    ux, uy, uz = (2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0]))
    return (
        v[0] + w * ux + y * uz - z * uy,
        v[1] + w * uy + z * ux - x * uz,
        v[2] + w * uz + x * uy - y * ux,
    )


def tcp_point(
    body_pos: Sequence[float], body_quat_xyzw: Sequence[float], offset: Sequence[float]
) -> tuple[float, ...]:
    rotated = quat_rotate_xyzw(body_quat_xyzw, offset)
    return tuple(a + b for a, b in zip(body_pos, rotated, strict=True))


def _box_distance(point: Sequence[float], low: Sequence[float], high: Sequence[float]) -> float:
    distances = (max(lo - p, 0, p - hi) for p, lo, hi in zip(point[:2], low, high, strict=True))
    return math.hypot(*distances)


def grasp_distance(point_xy: Sequence[float], scene: Mapping[str, Any]) -> float:
    t = scene["tubes"]
    return min(
        _box_distance(
            point_xy,
            [o[0] + t["axis_span_m"][0] + t["x_range_m"][0], o[1] + t["y_range_m"][0]],
            [o[0] + t["axis_span_m"][1] + t["x_range_m"][1], o[1] + t["y_range_m"][1]],
        )
        for o in t["origins_m"]
    )


def place_distance(point_xy: Sequence[float], scene: Mapping[str, Any]) -> float:
    r = scene["rack"]
    distances = []
    for i in range(YAW_GRID):
        low, high = r["yaw_range_rad"]
        yaw = low + i * (high - low) / (YAW_GRID - 1)
        for x, y, _ in r["slots_m"]:
            centre = [
                r["origin_m"][0] + math.cos(yaw) * x - math.sin(yaw) * y,
                r["origin_m"][1] + math.sin(yaw) * x + math.cos(yaw) * y,
            ]
            distances.append(
                _box_distance(
                    point_xy,
                    [centre[0] + r["x_range_m"][0], centre[1] + r["y_range_m"][0]],
                    [centre[0] + r["x_range_m"][1], centre[1] + r["y_range_m"][1]],
                )
            )
    return min(distances)


def grasp_centre(scene: Mapping[str, Any]) -> tuple[float, float]:
    """Mean over tubes of origin + axis-span midpoint (xy)."""
    t = scene["tubes"]
    mid = sum(t["axis_span_m"]) / 2
    return (
        statistics.fmean(o[0] + mid for o in t["origins_m"]),
        statistics.fmean(o[1] for o in t["origins_m"]),
    )


def place_centre(scene: Mapping[str, Any]) -> tuple[float, float]:
    """Rack origin + mean slot (xy), at nominal yaw."""
    r = scene["rack"]
    return (
        r["origin_m"][0] + statistics.fmean(s[0] for s in r["slots_m"]),
        r["origin_m"][1] + statistics.fmean(s[1] for s in r["slots_m"]),
    )


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("Empty sample")
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lo = math.floor(index)
    hi = math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def judged_gripper(length: int, holds: Sequence[tuple[int, int]]) -> list[bool]:
    return [
        not any(start <= i < end + RELEASE_SETTLE_FRAMES for start, end in holds)
        for i in range(length)
    ]


def tracking_stats(
    recorded: Sequence[Sequence[float]],
    simulated: Sequence[Sequence[float]],
    joint_names: Sequence[str],
    gripper_mask: Sequence[bool],
) -> dict[str, Any]:
    result = {}
    pooled = []
    for j, name in enumerate(joint_names):
        errors = [
            abs(a[j] - b[j])
            for i, (a, b) in enumerate(zip(recorded, simulated, strict=True))
            if name != "gripper" or gripper_mask[i]
        ]
        if name != "gripper":
            pooled.extend(errors)
        result[name] = {
            "p95": percentile(errors, 0.95) if errors else None,
            "max": max(errors) if errors else None,
            "frames": len(errors),
        }
    return {"joints": result, "pooled_arm_p95": percentile(pooled, 0.95)}


def limit_shares(
    targets: Sequence[Sequence[float]],
    positions: Sequence[Sequence[float]],
    limits: Sequence[Sequence[float]],
    joint_names: Sequence[str],
    gripper_mask: Sequence[bool],
) -> dict[str, float]:
    outside = near = 0
    for i, (target, actual) in enumerate(zip(targets, positions, strict=True)):
        indices = [j for j, n in enumerate(joint_names) if n != "gripper" or gripper_mask[i]]
        outside += any(target[j] < limits[j][0] or target[j] > limits[j][1] for j in indices)
        near += any(
            min(actual[j] - limits[j][0], limits[j][1] - actual[j]) <= LIMIT_MARGIN_RAD
            for j in indices
        )
    count = len(targets)
    if not count:
        raise ValueError("No judged frames")
    return {"target_outside": outside / count, "simulated_near": near / count}


def _summary(points: Sequence[Sequence[float]]) -> dict[str, Any]:
    if not points:
        return {"median_xyz_m": None, "z_m": None}
    return {
        "median_xyz_m": [statistics.median([p[j] for p in points]) for j in range(3)],
        "z_m": {
            "median": statistics.median([p[2] for p in points]),
            "p5": percentile([p[2] for p in points], 0.05),
            "p95": percentile([p[2] for p in points], 0.95),
        },
    }


def verdict(
    tracking: Mapping[str, Any],
    limits: Mapping[str, float],
    grasps: Sequence[Sequence[float]],
    releases: Sequence[Sequence[float]],
    scene: Mapping[str, Any],
) -> dict[str, Any]:
    failed = []
    if len(grasps) != len(releases):
        raise ValueError("Events must be paired")
    if len(grasps) < MIN_EPISODES_WITH_EVENTS:
        failed.append("episodes_with_events")
    for name, stats in tracking["joints"].items():
        p95, maximum = (
            (GRIPPER_P95_MAX, GRIPPER_ABS_MAX) if name == "gripper" else (ARM_P95_MAX, ARM_ABS_MAX)
        )
        for key, threshold in (("p95", p95), ("max", maximum)):
            if stats[key] is None or stats[key] > threshold:
                failed.append(f"tracking.{name}.{key}")
    failed.extend(f"limits.{k}" for k, v in limits.items() if v > LIMIT_SHARE_MAX)
    radius = scene["tubes"]["radius_m"] + CLUSTER_MARGIN_M

    def clusters(g: Sequence[Sequence[float]], p: Sequence[Sequence[float]]) -> dict[str, float]:
        return {
            "grasp": sum(grasp_distance(x, scene) <= radius for x in g) / len(g) if g else 0,
            "release": sum(place_distance(x, scene) <= radius for x in p) / len(p) if p else 0,
        }

    shares = clusters(grasps, releases)
    cluster_failed = [f"clusters.{k}" for k, v in shares.items() if v < CLUSTER_SHARE_MIN]
    result = {
        "verdict": "NO_GO",
        "failed_rules": failed + cluster_failed,
        "episodes_with_events": len(grasps),
        "cluster_shares": shares,
        "grasp": _summary(grasps),
        "release": _summary(releases),
        "offset_m": None,
    }
    if not failed and not cluster_failed:
        result["verdict"] = "GO"
    elif not failed and grasps:
        dg = [
            statistics.median([p[j] for p in grasps]) - c for j, c in enumerate(grasp_centre(scene))
        ]
        dp = [
            statistics.median([p[j] for p in releases]) - c
            for j, c in enumerate(place_centre(scene))
        ]
        offset = [(a + b) / 2 for a, b in zip(dg, dp, strict=True)]
        if math.dist(dg, dp) <= OFFSET_AGREEMENT_M and math.hypot(*offset) <= OFFSET_MAX_M:
            shifted = clusters(
                [[p[0] - offset[0], p[1] - offset[1]] for p in grasps],
                [[p[0] - offset[0], p[1] - offset[1]] for p in releases],
            )
            result["shifted_cluster_shares"] = shifted
            if min(shifted.values()) >= CLUSTER_SHARE_MIN:
                result.update(verdict="BASE_OFFSET", offset_m=offset, failed_rules=[])
    return result
