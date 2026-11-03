"""Generate the object-free SO-101 replay decision from portable JSON files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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


CORE = load_module("demo_replay", ENV / "demo_replay.py")
UNITS = load_module("joint_units", ENV / "joint_units.py")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_report(
    episodes: dict[str, Any],
    raw: dict[str, Any],
    scene: dict[str, Any],
    table: dict[str, dict[str, list[float]]],
) -> dict[str, Any]:
    names = [n.removesuffix(".pos") for n in episodes["joint_names"]]
    if set(names) != set(table) or len(names) != len(table):
        raise ValueError("Dataset joint names do not match unit table")
    sources = {e["index"]: e for e in episodes["episodes"]}
    meta = raw["metadata"]
    if meta.get("recorded_joint_order", names) != names:
        raise ValueError("Raw recorded joint order differs from dataset")
    indices = [meta["joint_names"].index(n) for n in names]
    limits = [meta["joint_pos_limits"][j] for j in indices]
    if not math.isfinite(meta["physics_dt"]) or meta["physics_dt"] <= 0:
        raise ValueError("Invalid physics dt")
    if any(
        len(pair) != 2 or not all(math.isfinite(v) for v in pair) or pair[0] >= pair[1]
        for pair in limits
    ):
        raise ValueError("Invalid joint limits")
    reports = {}
    compared_episodes = None
    for run in raw["runs"]:
        if run["substeps"] < 1 or int(run["substeps"]) != run["substeps"]:
            raise ValueError("Invalid substeps")
        if str(run["substeps"]) in reports:
            raise ValueError("Duplicate substep count")
        recorded, simulated, targets, positions, masks = [], [], [], [], []
        grasps, releases, durations = [], [], []
        seen = set()
        hz = 1 / (run["substeps"] * meta["physics_dt"])
        for episode in run["episodes"]:
            index = episode["index"]
            if index in seen:
                raise ValueError("Duplicate episode in replay")
            seen.add(index)
            source = sources[index]
            count = len(source["action"])
            if (
                not count
                or len(source["state"]) != count
                or any(
                    len(episode[k]) != count
                    for k in ("joint_pos_rad", "body_pos_m", "body_quat_xyzw")
                )
            ):
                raise ValueError("Empty or mismatched episode series")
            for key, width in (("joint_pos_rad", 6), ("body_pos_m", 3), ("body_quat_xyzw", 4)):
                if any(
                    len(row) != width or not all(math.isfinite(v) for v in row)
                    for row in episode[key]
                ):
                    raise ValueError("Invalid raw frame values")
            g = names.index("gripper")
            sg = [row[g] for row in source["state"]]
            ag = [row[g] for row in source["action"]]
            masks.extend(CORE.judged_gripper(count, CORE.find_holds(sg, ag)))
            for state, action, rad in zip(
                source["state"], source["action"], episode["joint_pos_rad"], strict=True
            ):
                if len(state) != len(names) or len(action) != len(names):
                    raise ValueError("Incorrect frame width")
                converted = UNITS.to_lerobot(dict(zip(names, rad, strict=True)), table)
                target = UNITS.to_radians(dict(zip(names, action, strict=True)), table)
                if not all(math.isfinite(v) for v in state):
                    raise ValueError("Invalid recorded state")
                recorded.append(state)
                simulated.append([converted[n] for n in names])
                targets.append([target[n] for n in names])
                positions.append(rad)
            events = CORE.grasp_release_frames(sg, ag)
            if events is not None:
                points = [
                    CORE.tcp_point(
                        episode["body_pos_m"][i],
                        episode["body_quat_xyzw"][i],
                        scene["tcp"]["offset_m"],
                    )
                    for i in events
                ]
                grasps.append(points[0])
                releases.append(points[1])
            durations.append(count / hz)
        if compared_episodes is not None and seen != compared_episodes:
            raise ValueError("Rate comparison requires the same episodes")
        compared_episodes = seen
        tracking = CORE.tracking_stats(recorded, simulated, names, masks)
        shares = CORE.limit_shares(targets, positions, limits, names, masks)
        decision = CORE.verdict(tracking, shares, grasps, releases, scene)
        reports[str(run["substeps"])] = {
            **decision,
            "tracking": tracking,
            "limit_shares": shares,
            "control_hz": hz,
            "mean_episode_duration_s": sum(durations) / len(durations),
            "wall_seconds": run.get("wall_seconds"),
        }
    if not reports:
        raise ValueError("No replay runs")
    measured = min(reports, key=lambda k: reports[k]["tracking"]["pooled_arm_p95"])
    return {
        "repo_id": episodes["repo_id"],
        "revision": episodes["revision"],
        "metadata": meta,
        "dataset_rate": {
            "metadata_fps": episodes["metadata_fps"],
            "control_hz": episodes.get("control_hz"),
            "control_hz_provenance": episodes.get("control_hz_provenance"),
        },
        "rules": CORE.RULES,
        "thresholds": {k: v for k, v in vars(CORE).items() if k.isupper() and k != "RULES"},
        "runs": reports,
        "measured_substeps": int(measured),
        "rate_selection": "Lowest pooled arm p95; ties choose the first supplied run.",
        "final_verdict": reports[measured]["verdict"],
    }


def write_report(report: dict[str, Any], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        f"# SO-101 demo replay: {report['final_verdict']}",
        "",
        *report["rules"],
        "",
        "| Substeps | Hz | Arm pooled p95 | Mean episode seconds | Verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for count, run in report["runs"].items():
        lines.append(
            f"| {count} | {run['control_hz']} | {run['tracking']['pooled_arm_p95']} | "
            f"{run['mean_episode_duration_s']} | {run['verdict']} |"
        )
    lines.extend(["", f"Measured rate: substeps {report['measured_substeps']}."])
    for count, run in report["runs"].items():
        lines.extend(
            [
                "",
                f"## Substeps {count}",
                "",
                "| Joint | p95 | Max | Judged frames |",
                "| --- | --- | --- | --- |",
            ]
        )
        for name, stats in run["tracking"]["joints"].items():
            lines.append(f"| {name} | {stats['p95']} | {stats['max']} | {stats['frames']} |")
        for key in (
            "limit_shares",
            "cluster_shares",
            "grasp",
            "release",
            "offset_m",
            "shifted_cluster_shares",
            "failed_rules",
        ):
            lines.extend(["", f"{key}: {json.dumps(run.get(key))}"])
    lines.extend(["", "Thresholds: " + json.dumps(report["thresholds"], sort_keys=True)])
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"GO": 0, "BASE_OFFSET": 3, "NO_GO": 4}[report["final_verdict"]]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("episodes-json", "raw", "scene", "units", "out-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_report(
        read_json(args.episodes_json),
        read_json(args.raw),
        read_json(args.scene),
        UNITS.load_table(args.units),
    )
    return write_report(report, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
