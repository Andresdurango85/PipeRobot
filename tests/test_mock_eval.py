from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mock_eval import evaluate, main
from eval.results import load_results
from stats.baseline import load_baseline
from stats.gate import SuccessCount, Verdict, decide

ROOT = Path(__file__).resolve().parent.parent
MOCK_POLICY = ROOT / "policies" / "mock-policy.json"


def _verdict_against_committed_baseline(success_rate: float) -> Verdict:
    results = evaluate("candidate", success_rate)
    candidate = SuccessCount(results.successes, results.trials)
    return decide(candidate, load_baseline()).verdict


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


# Phase 0 acceptance criterion, end to end on the mock: a deliberately worse policy is blocked,
# the current one passes.
def test_current_mock_policy_passes_the_gate() -> None:
    rate = json.loads(MOCK_POLICY.read_text(encoding="utf-8"))["success_rate"]

    assert _verdict_against_committed_baseline(rate) is Verdict.PASS


def test_sabotaged_policy_is_blocked() -> None:
    assert _verdict_against_committed_baseline(0.5) is Verdict.BLOCK


def test_main_writes_results(tmp_path: Path) -> None:
    output = tmp_path / "out" / "results.json"

    assert main(["--policy", str(MOCK_POLICY), "--episodes", "20", "--output", str(output)]) == 0
    assert load_results(output).trials == 20


@pytest.mark.parametrize(
    "policy", ['{"name": "p"}', '{"name": "p", "success_rate": 1.5}', "not json"]
)
def test_main_returns_2_on_invalid_policy(tmp_path: Path, policy: str) -> None:
    path = tmp_path / "policy.json"
    path.write_text(policy, encoding="utf-8")

    assert main(["--policy", str(path), "--output", str(tmp_path / "r.json")]) == 2
