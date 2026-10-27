from __future__ import annotations

from pathlib import Path

import pytest

from eval.mock_eval import evaluate, main
from eval.results import load_results
from stats.gate import SuccessCount, Verdict, decide

# Deliberately independent of policies/mock-policy.json and stats/baseline.json: judging the
# committed policy is pr-gate's job, so changing it must never break the unit tests.
REFERENCE_RATE = 0.8


def _verdict(candidate_rate: float) -> Verdict:
    candidate, baseline = evaluate("candidate", candidate_rate), evaluate("base", REFERENCE_RATE)
    return decide(
        SuccessCount(candidate.successes, candidate.trials),
        SuccessCount(baseline.successes, baseline.trials),
    ).verdict


def test_same_policy_gives_identical_results() -> None:
    assert evaluate("p", 0.8) == evaluate("p", 0.8)


def test_lower_success_rate_only_adds_failures() -> None:
    good = {episode.seed for episode in evaluate("p", 0.8).failed}
    worse = {episode.seed for episode in evaluate("p", 0.5).failed}

    assert good < worse


@pytest.mark.parametrize(("rate", "successes"), [(0.0, 0), (1.0, 50)])
def test_extreme_success_rates(rate: float, successes: int) -> None:
    assert evaluate("p", rate).successes == successes


def test_failed_episodes_carry_scene_and_failure() -> None:
    failed = evaluate("p", 0.5).failed

    assert failed
    assert all(episode.scene and episode.failure for episode in failed)


# Phase 0 acceptance criterion on the mock: an unchanged policy passes, a sabotaged one is blocked.
def test_unchanged_policy_passes() -> None:
    assert _verdict(REFERENCE_RATE) is Verdict.PASS


def test_sabotaged_policy_is_blocked() -> None:
    assert _verdict(0.5) is Verdict.BLOCK


def test_main_writes_results(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text('{"name": "p", "success_rate": 0.8}', encoding="utf-8")
    output = tmp_path / "out" / "results.json"

    assert main(["--policy", str(policy), "--episodes", "20", "--output", str(output)]) == 0
    assert load_results(output).trials == 20


@pytest.mark.parametrize(
    "policy", ['{"name": "p"}', '{"name": "p", "success_rate": 1.5}', "not json"]
)
def test_main_returns_2_on_invalid_policy(tmp_path: Path, policy: str) -> None:
    path = tmp_path / "policy.json"
    path.write_text(policy, encoding="utf-8")

    assert main(["--policy", str(path), "--output", str(tmp_path / "r.json")]) == 2
