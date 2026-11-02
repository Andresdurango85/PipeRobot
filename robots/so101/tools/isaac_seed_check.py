"""Check whether Isaac Lab reproduces an SO-101 episode from its seed.

Steps an Isaac Lab task with seeded random actions and saves every observation to a ``.npz``
file; ``--compare`` then tells whether two such files are identical, and from which step they
differ. Two runs with the same seed should match; a run with another seed should not
(docs/knowledge/isaac.md). Random actions only: no camera and no policy in the loop.

Runs in the Isaac Lab 3.0 environment of ADR 0021 (Isaac Lab ``release/3.0.0`` at commit
``44044b0963``, Isaac Sim 6.2.0.0), not in this repo's environment. The Omniverse EULA must have
been accepted by the owner; in an environment where Isaac Sim has not recorded it, set
``OMNI_KIT_ACCEPT_EULA=YES`` as the record of that acceptance. Run it from a scratch directory,
not from a repo checkout: Isaac Lab writes logs relative to the working directory.

Usage (``PY`` is the Isaac Lab environment's python)::

    PYTHONUNBUFFERED=1 $PY <repo>/robots/so101/tools/isaac_seed_check.py --viz none \
        --seed 1000 --out run1.npz
    PYTHONUNBUFFERED=1 $PY <repo>/robots/so101/tools/isaac_seed_check.py --viz none \
        --seed 1000 --out run2.npz
    $PY <repo>/robots/so101/tools/isaac_seed_check.py --compare run1.npz run2.npz

Exit codes: 0 OK (with ``--compare``: identical), 1 the runs differ.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

DEFAULT_TASK = "IsaacContrib-Stack-Cube-SO101-v0"


class Tensor(Protocol):
    """The part of ``torch.Tensor`` used here."""

    def detach(self) -> Tensor: ...
    def cpu(self) -> Tensor: ...
    def numpy(self) -> object: ...


def compare(first: Path, second: Path) -> int:
    """Print whether two saved runs are identical and where they first differ."""
    import numpy as np

    a = np.load(first)["obs"]
    b = np.load(second)["obs"]
    if a.shape != b.shape:
        print(f"different shapes: {a.shape} vs {b.shape}")
        return 1
    per_step = np.abs(a - b).reshape(a.shape[0], -1).max(axis=1)
    if not per_step.any():
        print(f"identical: {a.shape[0]} steps x {a.shape[1]} envs x {a.shape[2]} values")
        return 0
    first_step = int(np.argmax(per_step > 0))
    print(f"differ from step {first_step}; max |diff| {per_step.max():.3e}")
    return 1


def _flatten(obs: Tensor | Mapping[str, Any]) -> list[Any]:
    """Observation tensors in a fixed order, from a tensor or a nested dict of tensors."""
    if isinstance(obs, Mapping):
        return [tensor for value in obs.values() for tensor in _flatten(value)]
    return [obs.detach().cpu().numpy()]


def _make_torch_deterministic() -> None:
    import torch

    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def run(args: argparse.Namespace) -> int:
    """Step the task with seeded random actions and save the observations."""
    import gymnasium as gym
    import isaaclab_tasks  # noqa: F401  (registers the tasks)
    import numpy as np
    import torch
    from isaaclab.app import launch_simulation
    from isaaclab_tasks.utils import resolve_task_config

    sys.argv = sys.argv[:1]  # resolve_task_config re-parses sys.argv with Hydra
    env_cfg, _ = resolve_task_config(args.task, "")
    env_cfg.scene.num_envs = args.num_envs
    env_cfg.seed = args.seed
    args.device = env_cfg.sim.device
    if args.torch_deterministic and hasattr(env_cfg.sim.physics, "enable_enhanced_determinism"):
        env_cfg.sim.physics.enable_enhanced_determinism = True

    with launch_simulation(env_cfg, args):
        start = time.perf_counter()
        env = gym.make(args.task, cfg=env_cfg)
        obs, _ = env.reset(seed=args.seed)
        # The env's configure_seed() turns cudnn.benchmark back on, at construction and on reset.
        if args.torch_deterministic:
            _make_torch_deterministic()
        print(f"env ready in {time.perf_counter() - start:.1f} s, actions {env.action_space.shape}")
        device = env.unwrapped.device
        generator = torch.Generator(device=device).manual_seed(args.seed)
        steps = []
        start = time.perf_counter()
        with torch.inference_mode():
            for _ in range(args.steps):
                uniform = torch.rand(env.action_space.shape, device=device, generator=generator)
                obs, *_ = env.step(2 * uniform - 1)  # uniform in [-1, 1]
                parts = _flatten(obs)
                steps.append(np.concatenate([p.reshape(p.shape[0], -1) for p in parts], axis=1))
        elapsed = time.perf_counter() - start
        np.savez(args.out, obs=np.stack(steps))
        print(f"{args.steps} steps x {args.num_envs} envs in {elapsed:.2f} s -> {args.out}")
        env.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--compare"]:
        parser = argparse.ArgumentParser(description="Compare two saved runs.")
        parser.add_argument("--compare", nargs=2, type=Path, required=True, metavar="NPZ")
        return compare(*parser.parse_args(argv).compare)

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    from isaaclab.app import add_launcher_args

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--num_envs", type=int, default=4)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument(
        "--torch_deterministic",
        action="store_true",
        help="Deterministic torch algorithms and PhysX enhanced determinism",
    )
    parser.add_argument("--out", type=Path, required=True, help="Where to save the observations")
    add_launcher_args(parser)  # adds --viz, --device, --deterministic (reproducible rendering)...
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
