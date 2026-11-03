"""Tune scripted randomized rollouts in one Isaac process (not registered evaluation)."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from isaac_demo_replay import ENV, load_module

from piperobot.adapters.isaaclab.evaluate import parse_seeds
from piperobot.adapters.isaaclab.specs import PolicySpec, UsesObjectState


def run(args: argparse.Namespace, sim_cfg: object) -> dict[str, object]:
    spec = PolicySpec.load(args.policy)
    params = spec.options.copy()
    for override in args.param:
        key, separator, value = override.partition("=")
        if not separator or key not in params:
            raise ValueError(f"Unknown or malformed --param: {override}")
        params[key] = json.loads(value)
    module = load_module("spike_policy", spec.module)
    policy = getattr(module, spec.factory)(**params)
    task = load_module("spike_task", ENV / "vials_to_rack_task.py")
    task.validate_action_space(policy, "tcp")
    runtime = load_module("spike_episodes", ENV / "vials_to_rack_episodes.py")
    randomization = load_module("spike_randomization", ENV / "vials_to_rack_randomization.py")
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    env = runtime.ReconstructedEpisodes(
        args.assets_dir, "course", sim_cfg, list(runtime.UNITS.load_table())
    )
    env.policy = policy
    env.action_space = "tcp"
    env.uses_object_state = isinstance(policy, UsesObjectState) and policy.uses_object_state
    env.ik_gain = args.ik_gain
    env.ik_max_lead = args.ik_max_lead
    episodes = []
    for seed in parse_seeds(args.seeds):
        policy.reset(seed)
        env.seed = seed
        sampled = randomization.sample_layout(seed, data)

        def apply_layout(sampled: object = sampled) -> None:
            env.teleport(
                env.rack,
                (
                    *sampled.rack_position,
                    *runtime.CORE.yaw_to_quat_xyzw(math.degrees(sampled.rack_yaw)),
                ),
            )
            for tube, position in zip(env.tubes, sampled.tubes, strict=True):
                env.teleport(tube, (*position, *env.lying))

        result = env.run_policy_episode(
            apply_layout, lambda index, observation: policy.act(observation), args.horizon, True
        )
        steps = result["steps"]
        phase = steps[-1]["phase"]
        errors = []
        for step in reversed(steps):
            if step["phase"] != phase:
                break
            errors.append(step["tcp_error"])
        result.update(final_phase=phase, max_tcp_error_last_phase=max(errors))
        print(
            seed,
            result["success"],
            result["failure_reason"],
            result["steps_run"],
            phase,
            max(errors),
            result["wrist_flex_limit_steps"],
            flush=True,
        )
        if not args.dump_steps:
            result.pop("steps")
        episodes.append(result)
    return {"policy": spec.name, "params": params, "episodes": episodes}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="200000-200009")
    parser.add_argument(
        "--policy", type=Path, default=ENV.parent / "policies/scripted_pick_place.json"
    )
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--horizon", type=int, default=600)
    parser.add_argument("--ik-gain", type=float, default=0.2)
    parser.add_argument("--ik-max-lead", type=float, default=0.25)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dump-steps", action="store_true")
    parser.add_argument("--assets-dir", type=Path)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        parser.add_argument("--device", default="cuda:0")
        parser.add_argument("--viz", choices=("none",), default="none")
        parser.parse_args(argv)
        return 0
    from isaaclab.app import add_launcher_args, launch_simulation
    from isaaclab.sim import SimulationCfg

    add_launcher_args(parser)
    args = parser.parse_args(argv)
    if args.assets_dir is None:
        fetch = load_module("spike_fetch", Path(__file__).with_name("fetch_course_assets.py"))
        manifest = json.loads((ENV / "course_assets.json").read_text(encoding="utf-8"))
        args.assets_dir = fetch.default_cache_dir(manifest["source"]["commit"])
    data = json.loads((ENV / "vials_to_rack.json").read_text(encoding="utf-8"))
    sim_cfg = SimulationCfg(dt=data["control"]["physics_dt"], device=args.device)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with launch_simulation(sim_cfg, args):
        code = 0
        try:
            report = run(args, sim_cfg)
        except Exception:
            report = {"episodes": [], "error": traceback.format_exc()}
            traceback.print_exc()
            code = 2
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        if code:
            raise SystemExit(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
