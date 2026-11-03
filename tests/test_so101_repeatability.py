"""Portable study tests: no Isaac imports or simulator execution."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
from so101_loader import load

R = load("study_rules_tests", "robots/so101/envs/repeatability.py")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robots/so101/tools"))
try:
    T = load("study_tool_tests", "robots/so101/tools/isaac_repeatability.py")
    D = load("study_driver_tests", "robots/so101/tools/repeatability_driver.py")
    P = load("study_report_tests", "robots/so101/tools/repeatability_report.py")
finally:
    sys.path.pop(0)


def episode(index: int = 0, step: int = 10, sha: str = "abc", wall: float = 1.0) -> dict:
    return {
        "index": index,
        "success": True,
        "failure_reason": None,
        "success_step": step,
        "trajectory_sha256": sha,
        "wall_seconds": wall,
        "forces": {"hold": {"count": 2, "max": 8.0, "median": 6.0}},
    }


def run(*eps: dict, label: str = "a") -> dict:
    return {"metadata": {"config_label": label}, "episodes": list(eps or [episode()])}


def test_compare_agreement() -> None:
    summary = R.compare_runs([run(), run(), run()])
    assert R.repeatable(summary)
    assert summary["bit_identical"] == 1
    assert summary["mean_wall_seconds_per_episode"] == 1.0
    assert summary["per_episode"][0]["force_deltas"]["hold"]["max"] == 0


def test_compare_flip_spread_and_forces() -> None:
    changed = episode(step=14)
    changed["forces"]["hold"]["max"] = 9.5
    summary = R.compare_runs([run(), run(changed)])
    assert summary["outcome_flips"] == 1
    assert summary["flip_rate"] == 1.0
    assert summary["max_success_step_spread"] == 4
    assert summary["per_episode"][0]["distinct_outcomes"] == 2
    assert summary["per_episode"][0]["force_deltas"]["hold"]["max"] == 1.5


def test_hash_disagreement_same_outcome() -> None:
    summary = R.compare_runs([run(), run(episode(sha="different"))])
    assert summary["outcome_flips"] == 0
    assert summary["bit_identical"] == 0


@pytest.mark.parametrize(
    ("forward", "reverse", "expected", "k_rev", "k_fwd"),
    [
        ([run(), run(), run()], run(episode(step=11)), "supported", 1, 0),
        ([run(), run(), run()], run(), "not supported", 0, 0),
        (
            [
                run(episode(), episode(1), episode(2)),
                run(episode(step=11), episode(1), episode(2)),
                run(episode(), episode(1), episode(2)),
            ],
            run(episode(), episode(1, step=11), episode(2, step=11)),
            "supported",
            2,
            1,
        ),
        ([run(), run(episode(step=11)), run()], run(), "inconclusive", 0, 1),
    ],
)
def test_order_branches(
    forward: list[dict], reverse: dict, expected: str, k_rev: int, k_fwd: int
) -> None:
    result = R.order_test(forward, reverse)["outcome"]
    assert result["verdict"] == expected
    assert result["k_rev"] == k_rev
    assert result["k_fwd"] == k_fwd
    hashed_forward = json.loads(json.dumps(forward))
    hashed_reverse = json.loads(json.dumps(reverse))
    for item in [*hashed_forward, hashed_reverse]:
        for ep in item["episodes"]:
            ep["trajectory_sha256"] = str(ep["success_step"])
    assert R.order_test(hashed_forward, hashed_reverse)["trajectory"] == result


def test_order_hashes_separate() -> None:
    result = R.order_test([run(), run(), run()], run(episode(sha="new")))
    assert result["outcome"]["verdict"] == "not supported"
    assert result["trajectory"]["verdict"] == "supported"


def test_shift_and_decision() -> None:
    failed = episode()
    failed.update(success=False, failure_reason="no_grasp", success_step=None)
    a = [run(failed), run(failed), run()]
    b = [run(), run(), run()]
    assert R.shift_vs_a(b, a)["success_count_difference"] == 1
    assert R.shift_vs_a(b, a)["episodes"] == [0]
    assert R.decide({"a": a, "b": b})["chosen"] == "b"
    assert R.decide({"a": a})["residual_flip_rates"] == {"a": 1.0}


def test_c_requires_confirmation() -> None:
    c = [run(*(episode(i, wall=0.1) for i in R.SUBSET_C)) for _ in range(3)]
    result = R.decide({"a": [run(), run(), run()], "c": c})
    assert result["action"] == "confirm c on all 75 episodes"
    assert result["chosen"] is None


def test_tie_favors_bit_identity() -> None:
    a = [run(), run(episode(sha="other")), run()]
    assert R.decide({"a": a, "b": [run(), run(), run()]})["chosen"] == "b"


def test_incomplete_cannot_qualify() -> None:
    assert not R.repeatable(R.compare_runs([run(), run(), run({"index": 0, "exit_code": 2})]))
    assert not R.repeatable(R.compare_runs([run(), run(), {"episodes": []}]))
    with pytest.raises(ValueError, match="matching episode coverage"):
        R.order_test([run()], run(episode(1)))
    with pytest.raises(ValueError, match="repeatable"):
        R.shift_vs_a([run()], [run()])


def test_report(tmp_path: Path) -> None:
    paths = []
    for i in range(3):
        path = tmp_path / f"a-{i}.json"
        data = run()
        data["metadata"]["runner_worker_start"] = i == 0
        path.write_text(json.dumps(data), encoding="utf-8")
        paths.append(path)
    reverse = tmp_path / "reverse.json"
    reverse.write_text(json.dumps(run(episode(step=11), label="a_rev")), encoding="utf-8")
    result = P.report([*paths, reverse], tmp_path / "out")
    assert result["order_test"]["outcome"]["verdict"] == "supported"
    assert result["decision"]["chosen"] == "a"
    markdown = (tmp_path / "out/report.md").read_text(encoding="utf-8")
    assert R.DECISION_RULES in markdown
    assert "Runner.Worker.exe" in markdown
    assert json.loads((tmp_path / "out/report.json").read_text())["configs"]["a"]["runs"] == 3


def test_driver_fake_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "episodes.json"
    dataset.write_text(json.dumps({"episodes": [{"index": 0}, {"index": 1}]}))
    args = argparse.Namespace(
        episodes_json=dataset,
        episodes="all",
        order="reverse",
        isaac_python=Path("fake-python"),
        workdir=tmp_path,
        config_label="c",
        determinism="enhanced",
        actuators="course",
        device="cpu",
        viz="none",
        full_reset=True,
        assets_dir=tmp_path,
    )
    calls = []
    monkeypatch.setattr(D, "runner_worker_running", lambda: False)

    def fake(
        command: list[str], *, cwd: Path, env: dict, check: bool
    ) -> subprocess.CompletedProcess:
        assert cwd == tmp_path
        assert env["PYTHONUNBUFFERED"] == "1"
        assert not check
        assert "--full-reset" in command
        index = int(command[command.index("--episodes") + 1])
        calls.append(index)
        output = Path(command[command.index("--out") + 1])
        child = run(episode(index), label="c")
        child["metadata"]["wall_seconds"] = 2.0
        output.write_text(json.dumps(child))
        return subprocess.CompletedProcess(command, 2 if index == 1 else 0)

    result = D.drive(args, runner=fake)
    assert calls == [1, 0]
    assert result["episodes"][0]["exit_code"] == 2
    assert result["episodes"][1]["success"]
    assert result["metadata"]["process_per_episode"]
    assert result["metadata"]["wall_seconds"] == 4.0
    assert result["metadata"]["end_to_end_wall_seconds"] >= 0


def test_isaac_help_without_isaac() -> None:
    result = subprocess.run(
        [sys.executable, "robots/so101/tools/isaac_repeatability.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--determinism" in result.stdout
    assert "--full-reset" in result.stdout


def test_selection() -> None:
    assert T.select_episodes("all", [0, 1]) == [0, 1]
    with pytest.raises(ValueError, match="unique and present"):
        T.select_episodes("0,0", [0, 1])
    with pytest.raises(ValueError, match="Expected all"):
        T.select_episodes("x", [0])
