"""Registered same-seed repeatability rules, independent of Isaac."""

from __future__ import annotations

import statistics
from collections import Counter
from itertools import combinations

# Fixed on 2026-11-03 before the first run; changing them needs a new ADR.
REPEATS = 3
SUBSET_C = (0, 7, 12, 17, 18, 19, 21, 25, 27, 35, 46, 51, 55, 67, 72)
_BASE = {
    "device": "cuda:0",
    "determinism": "off",
    "full_reset": False,
    "order": "forward",
    "episodes": "all",
    "actuators": "course",
    "runs": REPEATS,
}
CONFIGS = {
    "a": dict(_BASE),
    "a_rev": {**_BASE, "order": "reverse", "runs": 1},
    "b": {**_BASE, "determinism": "enhanced"},
    "d": {**_BASE, "full_reset": True},
    "e": {**_BASE, "device": "cpu"},
    "c": {**_BASE, "episodes": SUBSET_C, "process_per_episode": True},
}
H1 = (
    "State carries over across resets within one process: the outcome of "
    "an episode depends on which episodes ran before it in the same process."
)
DECISION_RULES = """A config is repeatable after at least 3 complete runs with zero outcome flips.
An outcome is (success, failure_reason, success_step). Hash agreement is reported separately.
Compare only identical episode coverage; failed or incomplete processes cannot qualify.
For order: with unanimous forward runs, support H1 iff k_rev >= 1; otherwise not supported.
With forward flips, support H1 iff k_rev > k_fwd; otherwise inconclusive.
Apply the same order rule separately to trajectory hashes.
Choose the repeatable config with the lowest mean episode wall time; ties favor bit identity.
Compare repeatable configs against a's majority outcome; majority ties are unresolved.
Config c counts only on its registered subset. If cheapest, confirm c on all 75 episodes.
If none is repeatable, report every config's residual flip rate."""


def outcome(ep: dict) -> tuple:
    return ep["success"], ep["failure_reason"], ep["success_step"]


def _indexed(run: dict) -> dict:
    episodes = run["episodes"]
    indexed = {ep["index"]: ep for ep in episodes}
    if len(indexed) != len(episodes):
        raise ValueError("Duplicate episode indices")
    return indexed


def compare_runs(runs: list[dict]) -> dict:
    indexed = [_indexed(run) for run in runs]
    indices = sorted(set().union(*(set(run) for run in indexed)))
    details = []
    times = []
    for index in indices:
        eps = [run[index] for run in indexed if index in run]
        valid = [ep for ep in eps if "success" in ep and not ep.get("exit_code", 0)]
        complete = len(valid) == len(runs)
        outcomes = {outcome(ep) for ep in valid}
        steps = [ep["success_step"] for ep in valid if ep["success_step"] is not None]
        hashes = [ep.get("trajectory_sha256") for ep in valid]
        deltas = {}
        for window in ("open_approach", "hold"):
            keys = set().union(*(ep.get("forces", {}).get(window, {}) for ep in valid))
            deltas[window] = {}
            for key in sorted(keys):
                values = [ep.get("forces", {}).get(window, {}).get(key) for ep in valid]
                numeric = [value for value in values if isinstance(value, (int, float))]
                deltas[window][key] = max(numeric) - min(numeric) if numeric else None
        times.extend(ep["wall_seconds"] for ep in valid)
        details.append(
            {
                "index": index,
                "all_agree": complete and len(outcomes) == 1,
                "distinct_outcomes": len(outcomes),
                "complete": complete,
                "success_step_spread": max(steps) - min(steps) if steps else 0,
                "hashes_equal": complete
                and bool(hashes)
                and None not in hashes
                and len(set(hashes)) == 1,
                "force_deltas": deltas,
            }
        )
    flips = sum(not ep["all_agree"] for ep in details)
    return {
        "runs": len(runs),
        "episodes": len(indices),
        "per_episode": details,
        "outcome_flips": flips,
        "flip_rate": flips / len(indices) if indices else None,
        "bit_identical": sum(ep["hashes_equal"] for ep in details),
        "max_success_step_spread": max((ep["success_step_spread"] for ep in details), default=0),
        "complete": bool(indices) and all(ep["complete"] for ep in details),
        "mean_wall_seconds_per_episode": statistics.mean(times) if times else None,
    }


def repeatable(config: dict) -> bool:
    return config["runs"] >= REPEATS and config["outcome_flips"] == 0 and config["complete"]


def order_test(forward_runs: list[dict], reverse_run: dict) -> dict:
    forward = [_indexed(run) for run in forward_runs]
    reverse = _indexed(reverse_run)
    if not forward or any(set(run) != set(reverse) for run in forward):
        raise ValueError("Order test requires matching episode coverage")
    if any("success" not in ep for run in [*forward, reverse] for ep in run.values()):
        raise ValueError("Order test requires successful episode processes")

    def evaluate(hashes: bool) -> dict:
        def value(ep: dict) -> object:
            return ep["trajectory_sha256"] if hashes else outcome(ep)

        unanimous = [i for i in reverse if len({value(run[i]) for run in forward}) == 1]
        changed = [i for i in unanimous if value(forward[0][i]) != value(reverse[i])]
        k_fwd = max(
            (sum(value(a[i]) != value(b[i]) for i in reverse) for a, b in combinations(forward, 2)),
            default=0,
        )
        verdict = (
            ("supported" if changed else "not supported")
            if k_fwd == 0
            else ("supported" if len(changed) > k_fwd else "inconclusive")
        )
        return {"k_rev": len(changed), "episodes": changed, "k_fwd": k_fwd, "verdict": verdict}

    return {"hypothesis": H1, "outcome": evaluate(False), "trajectory": evaluate(True)}


def shift_vs_a(config_runs: list[dict], a_runs: list[dict]) -> dict:
    if not repeatable(compare_runs(config_runs)):
        raise ValueError("Shift requires a repeatable config")
    config = _indexed(config_runs[0])
    baseline = [_indexed(run) for run in a_runs]
    changed, unresolved = [], []
    difference = 0
    for index, ep in config.items():
        votes = Counter(
            outcome(run[index]) for run in baseline if index in run and "success" in run[index]
        )
        ranked = votes.most_common()
        if not ranked or ranked[0][1] <= len(baseline) / 2:
            unresolved.append(index)
            continue
        majority = ranked[0][0]
        if outcome(ep) != majority:
            changed.append(index)
        difference += int(ep["success"]) - int(majority[0])
    return {
        "episodes": sorted(changed),
        "success_count_difference": difference,
        "unresolved_majority": sorted(unresolved),
    }


def decide(results: dict[str, list[dict]]) -> dict:
    summaries = {label: compare_runs(runs) for label, runs in results.items()}
    eligible = [
        label
        for label, summary in summaries.items()
        if label != "a_rev"
        and repeatable(summary)
        and (label != "c" or {ep["index"] for ep in summary["per_episode"]} == set(SUBSET_C))
    ]
    decision = {
        "repeatable_configs": sorted(eligible),
        "chosen": None,
        "action": "no repeatable config",
        "shift_vs_a": None,
    }
    if eligible:
        cheapest = min(
            eligible,
            key=lambda label: (
                summaries[label]["mean_wall_seconds_per_episode"],
                summaries[label]["bit_identical"] != summaries[label]["episodes"],
                label,
            ),
        )
        decision["cheapest"] = cheapest
        decision["action"] = "confirm c on all 75 episodes" if cheapest == "c" else "choose"
        decision["chosen"] = None if cheapest == "c" else cheapest
        if "a" in results:
            decision["shift_vs_a"] = shift_vs_a(results[cheapest], results["a"])
    else:
        decision["residual_flip_rates"] = {
            k: v["flip_rate"] for k, v in summaries.items() if k != "a_rev"
        }
    return decision
