"""Evaluate a pinned LeRobot policy in a LeRobot simulator and write the results contract.

Runs `lerobot-eval` (LeRobot 0.6.1) in a subprocess, then converts its ``eval_info.json`` into
`eval/results.py`'s format, so `stats.gate` and `reports.pr_comment` work unchanged (ADR 0016).
Episode ``i`` uses seed ``start_seed + i``, as `lerobot-eval` assigns them. `lerobot-eval` records
videos of the first 10 episodes only; failed episodes among them get a video link.
The gate runs on CPU: ``--device cuda`` is for exploring speed only, because `lerobot-eval`'s CUDA
runs are not reproducible on the same seeds.

Usage:
    uv run python -m eval.lerobot_eval --policy policies/pusht-vqbet.json --output out/results.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from eval.lerobot_policy import PolicySpec, prepare_policy
from eval.results import EpisodeResult, EvalResults, ResultsError, save_results

DEFAULT_EPISODES = 50
DEFAULT_BATCH_SIZE = 10
DEFAULT_START_SEED = 1000


def convert_eval_info(
    info: Mapping[str, Any], policy: str, start_seed: int, videos_link: str | None = None
) -> EvalResults:
    """Turn `lerobot-eval`'s single-task ``eval_info.json`` into the results contract."""
    tasks = info.get("per_task")
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        raise ResultsError(f"expected exactly one task in eval_info, got {tasks!r:.200}")
    metrics = tasks[0].get("metrics", {})
    if not isinstance(metrics, Mapping):
        raise ResultsError(f"eval_info 'metrics' is not an object: {metrics!r:.200}")
    successes = metrics.get("successes")
    if not isinstance(successes, list):
        raise ResultsError("eval_info has no per-episode 'successes'")
    max_rewards = metrics.get("max_rewards") or [None] * len(successes)
    if not isinstance(max_rewards, list) or len(max_rewards) != len(successes):
        raise ResultsError(
            f"eval_info has {len(successes)} 'successes' but 'max_rewards' is {max_rewards!r:.200}"
        )
    n_videos = len(metrics.get("video_paths") or [])

    episodes = []
    for index, (success, max_reward) in enumerate(zip(successes, max_rewards, strict=True)):
        failure = None
        if not success:
            reward = "" if max_reward is None else f" (max reward {max_reward:.2f})"
            failure = "not solved" + reward
        has_video = not success and index < n_videos and videos_link
        episodes.append(
            EpisodeResult(
                seed=start_seed + index,
                success=bool(success),
                failure=failure,
                video_url=videos_link if has_video else None,
            )
        )
    return EvalResults(policy=policy, evaluator="lerobot-eval", episodes=tuple(episodes))


def run_lerobot_eval(
    policy_dir: Path,
    env: str,
    episodes: int,
    batch_size: int,
    start_seed: int,
    output_dir: Path,
    device: str = "cpu",
) -> Path:
    shutil.rmtree(output_dir, ignore_errors=True)  # never mix with a previous run's videos
    command = [
        sys.executable,
        "-m",
        "lerobot.scripts.lerobot_eval",
        f"--policy.path={policy_dir}",
        f"--env.type={env}",
        f"--eval.n_episodes={episodes}",
        f"--eval.batch_size={min(batch_size, episodes)}",
        "--eval.use_async_envs=false",
        f"--policy.device={device}",
        "--policy.use_amp=false",
        f"--seed={start_seed}",
        f"--output_dir={output_dir}",
    ]
    # Our own interpreter and arguments, no shell: nothing untrusted reaches the command line.
    completed = subprocess.run(command, check=False)  # noqa: S603
    eval_info = output_dir / "eval_info.json"
    if completed.returncode != 0 or not eval_info.exists():
        raise ResultsError(f"lerobot-eval failed with exit code {completed.returncode}")
    return eval_info


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", type=Path, required=True, help="Policy spec JSON")
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_START_SEED, help="First episode seed")
    parser.add_argument(
        "--device", default="cpu", help="Torch device for the policy, e.g. cpu or cuda"
    )
    parser.add_argument("--work-dir", type=Path, default=Path("out/lerobot"))
    parser.add_argument("--output", type=Path, required=True, help="Where to write results JSON")
    parser.add_argument("--videos-link", help="URL where failed-episode videos can be found")
    args = parser.parse_args(argv)

    try:
        spec = PolicySpec.load(args.policy)
        policy_dir = prepare_policy(spec, args.work_dir / "policies")
        eval_info = run_lerobot_eval(
            policy_dir,
            spec.env,
            args.episodes,
            args.batch_size,
            args.seed,
            args.work_dir / "eval",
            args.device,
        )
        try:
            info = json.loads(eval_info.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ResultsError(f"cannot read {eval_info}: {exc}") from exc
        if not isinstance(info, Mapping):
            raise ResultsError(f"{eval_info} is not a JSON object")
        results = convert_eval_info(info, spec.name, args.seed, args.videos_link)
    except ResultsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    save_results(results, args.output)
    print(f"{results.policy}: {results.successes}/{results.trials} episodes succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
