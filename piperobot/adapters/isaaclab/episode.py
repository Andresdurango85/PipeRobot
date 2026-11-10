"""Run one isolated task episode. Help works without Isaac or torch installed."""

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
from collections.abc import Callable, Sequence
from importlib import import_module
from pathlib import Path
from typing import cast

from piperobot.adapters.isaaclab.specs import Policy, PolicySpec, TaskSpec, load_module
from piperobot.platform_info import describe_platform

_exit = os._exit


def version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def gpu_driver_version() -> str | None:
    """The NVIDIA driver version from nvidia-smi; None when it is unavailable."""
    smi = shutil.which("nvidia-smi")
    if smi is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - resolved nvidia-smi and fixed arguments
            [smi, "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = result.stdout.strip().splitlines()
    return lines[0].strip() if result.returncode == 0 and lines else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--record", type=Path)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--device", default="cuda:0")
        parser.add_argument("--viz", default="none")
        parser.parse_args(argv)
        return 0
    started = time.perf_counter()
    output: Path | None = None
    try:
        early_args, _ = parser.parse_known_args(argv)
        output = Path(early_args.out)
        output.unlink(missing_ok=True)
        app = import_module("isaaclab.app")
        simulation = import_module("isaaclab.sim")
        physics = import_module("isaaclab_physx.physics")

        app.add_launcher_args(parser)
        args = parser.parse_args(argv)
        args.out.unlink(missing_ok=True)
        task = TaskSpec.load(args.task)
        spec = PolicySpec.load(args.policy)
        task_module = load_module("evaluation_task", task.module)
        # The task's simulation settings (e.g. the physics dt) must be in the config before
        # launch, not patched in afterwards.
        settings = getattr(task_module, "simulation_settings", None)
        extra = cast(dict[str, object], settings(task.options)) if settings is not None else {}
        sim_cfg = simulation.SimulationCfg(
            device=args.device,
            physics=physics.PhysxCfg(enable_enhanced_determinism=False),
            **extra,
        )
        if args.record is not None:
            args.enable_cameras = True
        with app.launch_simulation(sim_cfg, args):
            try:
                torch = import_module("torch")

                policy_module = load_module("evaluation_policy", spec.module)
                factory = cast(Callable[..., Policy], getattr(policy_module, spec.factory))
                policy = factory(**spec.options)
                policy.reset(args.seed)
                run = cast(Callable[..., dict[str, object]], task_module.run_episode)
                recording = {}
                if args.record is not None:
                    args.record.mkdir(parents=True, exist_ok=True)
                    recording["record_dir"] = args.record
                result = run(
                    seed=args.seed,
                    policy=policy,
                    layout=task.layout,
                    options=task.options,
                    sim_cfg=sim_cfg,
                    **recording,
                )
                metric_settings = getattr(task_module, "metric_spec", None)
                if metric_settings is not None:
                    # The declared layout takes precedence over any option with that name.
                    result["metric_spec"] = metric_settings({**task.options, "layout": task.layout})
                cuda = torch.cuda.is_available() and str(sim_cfg.device).startswith("cuda")
                result.update(
                    seed=args.seed,
                    wall_seconds=time.perf_counter() - started,
                    platform={
                        "cpu": describe_platform(),
                        "gpu": torch.cuda.get_device_name(sim_cfg.device) if cuda else None,
                        "cuda_version": torch.version.cuda,
                        "driver_version": gpu_driver_version() if cuda else None,
                        "torch_version": version("torch"),
                        "isaac_lab_version": version("isaaclab"),
                        "device": str(sim_cfg.device),
                        "options": task.options,
                    },
                )
                payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
                args.out.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.out.with_name(args.out.name + ".tmp")
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, args.out)
                saved = json.loads(args.out.read_text(encoding="utf-8"))
                if not isinstance(saved, dict) or saved.get("seed") != args.seed:
                    raise ValueError("Persisted worker result has a mismatched seed")
                # NVBug 5948099: Kit shutdown can deadlock. Fsync and re-read the result
                # before bypassing shutdown so a successful exit guarantees durable JSON.
                sys.stdout.flush()
                sys.stderr.flush()
                _exit(0)
            except Exception:
                args.out.unlink(missing_ok=True)
                traceback.print_exc()
                raise SystemExit(1) from None
            raise SystemExit(0)
    except Exception:
        if output is not None:
            output.unlink(missing_ok=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
