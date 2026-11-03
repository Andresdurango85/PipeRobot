"""Measure reconstructed SO-101 demo repeatability in one Isaac process."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from isaac_demo_replay import ENV, load_module


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def runner_worker_running() -> bool | None:
    if os.name != "nt":
        return None
    tasklist = shutil.which("tasklist")
    if tasklist is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments, resolved executable
            [tasklist, "/FI", "IMAGENAME eq Runner.Worker.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return "runner.worker.exe" in result.stdout.lower() if result.returncode == 0 else None


def git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments, resolved executable
            [git, "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def select_episodes(value: str, available: list[int]) -> list[int]:
    if value == "all":
        return available.copy()
    try:
        selected = [int(part) for part in value.split(",")]
    except ValueError as exc:
        raise ValueError("Expected all or comma-separated episode indices") from exc
    if (
        len(selected) != len(set(selected))
        or not selected
        or any(i not in available for i in selected)
    ):
        raise ValueError("Episode indices must be unique and present in the dataset")
    return selected


def parser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--episodes-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-label", required=True)
    parser.add_argument("--episodes", default="all")
    parser.add_argument("--order", choices=("forward", "reverse"), default="forward")
    parser.add_argument("--determinism", choices=("off", "enhanced"), default="off")
    parser.add_argument("--full-reset", action="store_true")
    parser.add_argument("--actuators", choices=("course", "usd"), default="course")
    parser.add_argument("--assets-dir", type=Path)


def run(args: argparse.Namespace, sim_cfg: object) -> dict:
    started = time.perf_counter()
    start_timestamp = timestamp()
    worker_start = runner_worker_running()
    episodes = json.loads(args.episodes_json.read_text(encoding="utf-8"))
    selected = select_episodes(args.episodes, [ep["index"] for ep in episodes["episodes"]])
    selected.sort(reverse=args.order == "reverse")
    by_index = {ep["index"]: ep for ep in episodes["episodes"]}
    runtime = load_module("reconstructed_episodes", ENV / "vials_to_rack_episodes.py")
    metadata = {
        "config_label": args.config_label,
        "options": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "start_timestamp": start_timestamp,
        "runner_worker_start": worker_start,
        "git_commit": git_commit(),
        "physics_dt": sim_cfg.dt,
        "isaac_lab_version": importlib.metadata.version("isaaclab"),
    }
    env = runtime.ReconstructedEpisodes(
        args.assets_dir, args.actuators, sim_cfg, episodes["joint_names"], args.full_reset
    )
    metadata["resolved_device"] = str(env.sim.device)
    results = [env.run_reconstructed_episode(by_index[i], record_steps=False) for i in selected]
    metadata.update(
        end_timestamp=timestamp(),
        wall_seconds=time.perf_counter() - started,
        runner_worker_end=runner_worker_running(),
    )
    return {"metadata": metadata, "episodes": results}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser_options(parser)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--device", choices=("cuda:0", "cpu"), default="cuda:0")
        parser.add_argument("--viz", choices=("none",), default="none")
        parser.parse_args(argv)
        return 0
    from isaaclab.app import add_launcher_args, launch_simulation
    from isaaclab.sim import SimulationCfg
    from isaaclab_physx.physics import PhysxCfg

    add_launcher_args(parser)
    args = parser.parse_args(argv)
    if args.assets_dir is None:
        fetch = load_module(
            "repeatability_fetch", Path(__file__).with_name("fetch_course_assets.py")
        )
        manifest = json.loads((ENV / "course_assets.json").read_text(encoding="utf-8"))
        args.assets_dir = fetch.default_cache_dir(manifest["source"]["commit"])
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    sim_cfg = SimulationCfg(
        dt=data["control"]["physics_dt"],
        device=args.device,
        physics=PhysxCfg(enable_enhanced_determinism=args.determinism == "enhanced"),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with launch_simulation(sim_cfg, args):
        code = 0
        try:
            report = run(args, sim_cfg)
        except Exception:
            report = {
                "metadata": {"config_label": args.config_label},
                "episodes": [],
                "error": traceback.format_exc(),
            }
            traceback.print_exc()
            code = 2
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        if code:
            raise SystemExit(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
