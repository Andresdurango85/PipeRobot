"""Mock evaluator: a stand-in for Isaac Lab-Arena until the simulation runs (ADR 0014).

It "runs" a policy described by a JSON file (``{"name": ..., "success_rate": 0.8}``) for N
episodes. Each episode's outcome is derived from its seed only, so results are deterministic
(no flakiness), and lowering ``success_rate`` turns some successes into failures without changing
any other episode, like a real regression. The output follows the contract in `eval/results.py`,
so the rest of the gate does not know it is a mock.

Usage:
    uv run python -m eval.mock_eval --policy policies/mock-policy.json --output out/results.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path

from eval.results import EpisodeResult, EvalResults, ResultsError, save_results

DEFAULT_EPISODES = 50
# Scene variations the real evaluation will randomize (rack position, lighting, tube pose).
SCENES = ("rack_left", "rack_right", "dim_light", "tube_rotated")
FAILURES = ("tube dropped", "missed grasp", "timeout")


def load_success_rate(policy_path: Path) -> tuple[str, float]:
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        name, rate = str(policy["name"]), float(policy["success_rate"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ResultsError(f"invalid mock policy {policy_path}: {exc}") from exc
    if not 0 <= rate <= 1:
        raise ResultsError(f"success_rate must be in [0, 1], got {rate}")
    return name, rate


def run_episode(seed: int, success_rate: float) -> EpisodeResult:
    # Seeded per episode: not crypto, just reproducible simulated outcomes.
    rng = random.Random(seed)  # noqa: S311
    success = rng.random() < success_rate
    return EpisodeResult(
        seed=seed,
        success=success,
        scene=SCENES[seed % len(SCENES)],
        failure=None if success else rng.choice(FAILURES),
    )


def evaluate(name: str, success_rate: float, episodes: int = DEFAULT_EPISODES) -> EvalResults:
    return EvalResults(
        policy=name,
        evaluator="mock",
        episodes=tuple(run_episode(seed, success_rate) for seed in range(episodes)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", type=Path, required=True, help="Mock policy JSON file")
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--output", type=Path, required=True, help="Where to write results JSON")
    args = parser.parse_args(argv)

    try:
        name, rate = load_success_rate(args.policy)
        results = evaluate(name, rate, args.episodes)
    except ResultsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    save_results(results, args.output)
    print(f"{results.policy}: {results.successes}/{results.trials} episodes succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
