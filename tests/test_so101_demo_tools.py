import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from so101_loader import load

R = load("demo_replay_report", "robots/so101/tools/demo_replay_report.py")
E = load("demo_extract", "robots/so101/tools/demo_extract.py")
ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "robots/so101/envs"


def test_rows_and_feature_validation() -> None:
    rows = [
        {
            "episode_index": e,
            "frame_index": f,
            "action": [float(f)] * 6,
            "observation.state": [float(e)] * 6,
        }
        for e, f in [(1, 0), (0, 1), (0, 0)]
    ]
    result = E.rows_to_episodes(rows, 1)
    assert result == [{"index": 0, "action": [[0.0] * 6, [1.0] * 6], "state": [[0.0] * 6] * 2}]
    with pytest.raises(ValueError, match="Duplicate"):
        E.rows_to_episodes([rows[0], rows[0]])
    with pytest.raises(ValueError, match="Non-contiguous"):
        E.rows_to_episodes([rows[1]])
    names = [n + ".pos" for n in R.UNITS.load_table()]
    info = {"features": {k: {"names": names} for k in ("action", "observation.state")}}
    assert E.feature_names(info) == names
    info["features"]["action"]["names"] = list(reversed(names))
    with pytest.raises(ValueError, match="differ"):
        E.feature_names(info)


@pytest.mark.parametrize("tool", ["isaac_demo_replay.py", "demo_extract.py"])
def test_help_without_optional_dependencies(tool: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-S", str(ROOT / "robots/so101/tools" / tool), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def fixture_payload(mode: str) -> tuple[dict[str, Any], dict[str, Any]]:
    table = R.UNITS.load_table()
    names = list(table)
    count = 69 if mode == "few" else 70
    episodes, simulated = [], []
    offset = 0.095 if mode == "offset" else 0
    for index in range(count):
        states = [[0.0, 0.0, 0.0, 0.0, 0.0, 23.0]] * 5 + [[0.0, 0.0, 0.0, 0.0, 0.0, 18.0]] * 15
        states += [[0.0, 0.0, 0.0, 0.0, 0.0, 27.0]] * 16
        actions = [row.copy() for row in states]
        for frame in range(5, 20):
            actions[frame][5] = 1.3
        positions = []
        for row in states:
            rad = R.UNITS.to_radians(dict(zip(names, row, strict=True)), table)
            if mode == "tracking":
                rad[names[0]] += 1
            positions.append([rad[n] for n in names])
        grasp = [0.27125 + offset, -0.08, 0.1]
        if mode == "offset":
            grasp[0] += 0.12 if index % 2 else -0.12
        release = [0.24025 + offset, 0.14, 0.2]
        if mode == "scatter":
            release = [2.0, float(index), 0.2]
        tcp = [grasp] * 20 + [release] * 16
        body = [[p[j] - [-0.0079, -0.000218121, -0.0981274][j] for j in range(3)] for p in tcp]
        episodes.append({"index": index, "action": actions, "state": states})
        simulated.append(
            {
                "index": index,
                "joint_pos_rad": positions,
                "body_pos_m": body,
                "body_quat_xyzw": [[0, 0, 0, 1]] * 36,
            }
        )
    limits = [[-4.0, 4.0]] * 6
    if mode == "limits":
        limits[0] = [-0.001, 0.001]
    return (
        {
            "repo_id": "synthetic/demo",
            "revision": "pinned",
            "metadata_fps": 30,
            "joint_names": names,
            "episodes": episodes,
        },
        {
            "metadata": {
                "joint_names": names,
                "joint_pos_limits": limits,
                "soft_joint_pos_limits": limits,
                "physics_dt": 1 / 120,
            },
            "runs": [{"substeps": s, "episodes": simulated} for s in (2, 4)],
        },
    )


@pytest.mark.parametrize(
    ("mode", "code", "verdict", "failure"),
    [
        ("go", 0, "GO", None),
        ("offset", 3, "BASE_OFFSET", None),
        ("tracking", 4, "NO_GO", "tracking.shoulder_pan.p95"),
        ("limits", 4, "NO_GO", "limits.simulated_near"),
        ("scatter", 4, "NO_GO", "clusters.release"),
        ("few", 4, "NO_GO", "episodes_with_events"),
    ],
)
def test_report_main(
    tmp_path: Path, mode: str, code: int, verdict: str, failure: str | None
) -> None:
    episodes, raw = fixture_payload(mode)
    for name, payload in (("episodes", episodes), ("raw", raw)):
        (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "out"
    result = R.main(
        [
            "--episodes-json",
            str(tmp_path / "episodes.json"),
            "--raw",
            str(tmp_path / "raw.json"),
            "--scene",
            str(ENV / "vials_to_rack.json"),
            "--units",
            str(ENV / "joint_units.json"),
            "--out-dir",
            str(out),
        ]
    )
    report = json.loads((out / "report.json").read_text())
    assert result == code
    assert report["final_verdict"] == verdict
    run = report["runs"]["2"]
    if failure:
        assert failure in run["failed_rules"]
    if mode == "offset":
        assert run["offset_m"] == pytest.approx([0.095, 0])
    assert run["mean_episode_duration_s"] == pytest.approx(0.6)
    assert report["runs"]["4"]["mean_episode_duration_s"] == pytest.approx(1.2)
    assert run["grasp"]["z_m"]["median"] == pytest.approx(0.1)
    markdown = (out / "report.md").read_text()
    assert all(rule in markdown for rule in R.CORE.RULES)


def test_measured_rate_uses_lower_error_and_rejects_nan() -> None:
    episodes, raw = fixture_payload("go")
    raw["runs"][0]["episodes"] = copy.deepcopy(raw["runs"][0]["episodes"])
    for episode in raw["runs"][0]["episodes"]:
        for row in episode["joint_pos_rad"]:
            row[0] += 0.01
    report = R.build_report(
        episodes, raw, R.read_json(ENV / "vials_to_rack.json"), R.UNITS.load_table()
    )
    assert report["measured_substeps"] == 4
    raw["runs"][0]["episodes"][0]["joint_pos_rad"][0][0] = float("nan")
    with pytest.raises(ValueError, match="Invalid raw"):
        R.build_report(episodes, raw, R.read_json(ENV / "vials_to_rack.json"), R.UNITS.load_table())


@pytest.mark.parametrize("mode", ["go", "tracking", "offset"])
def test_course_diagnostics_do_not_change_verdict(tmp_path: Path, mode: str) -> None:
    episodes, raw = fixture_payload(mode)
    scene = R.read_json(ENV / "vials_to_rack.json")
    table = R.UNITS.load_table()
    original = R.build_report(episodes, raw, scene, table)
    # A course run exactly reproduces the recorded state, independently of USD errors.
    course = copy.deepcopy(raw["runs"][0])
    course["actuators"] = "course"
    for source, simulated in zip(episodes["episodes"], course["episodes"], strict=True):
        simulated["joint_pos_rad"] = [
            list(R.UNITS.to_radians(dict(zip(table, row, strict=True)), table).values())
            for row in source["state"]
        ]
    slower = copy.deepcopy(course)
    slower["substeps"] = 4
    for simulated in slower["episodes"]:
        for row in simulated["joint_pos_rad"]:
            row[0] += 0.5
    raw["runs"].insert(0, slower)
    raw["runs"].insert(0, course)
    combined = R.build_report(episodes, raw, scene, table)
    for key in ("runs", "final_verdict", "measured_substeps", "thresholds", "rules"):
        assert combined[key] == original[key]
    assert R.write_report(combined, tmp_path / "combined") == R.write_report(
        original, tmp_path / "original"
    )
    diagnostic = combined["diagnostics"]["runs"]["course/2"]
    assert diagnostic["residual"]["pooled_arm_p95"] == pytest.approx(0, abs=1e-12)
    assert diagnostic["sim_vs_recorded_shift_frames"]["lag_frames"] == 0
    assert diagnostic["action_to_state_lag_frames"]["lag_frames"] == 0
    markdown = (tmp_path / "combined/report.md").read_text()
    assert "## Diagnostics (not part of the registered verdict)" in markdown
    assert "| course/2 | 60.0 |" in markdown
    assert "Dataset action->state lag (frames): 0.0" in markdown
    for joint in diagnostic["residual"]["joints"].values():
        for key in ("mean", "p95", "max", "signed_mean"):
            assert joint[key] == pytest.approx(0, abs=1e-12)


def test_course_only_and_recorded_gains(tmp_path: Path) -> None:
    episodes, raw = fixture_payload("go")
    raw["runs"] = [raw["runs"][0]]
    raw["runs"][0]["actuators"] = "course"
    names = raw["metadata"]["joint_names"]
    raw["metadata"]["actuators"] = {
        mode: {
            "joint_stiffness": dict.fromkeys(names, stiffness),
            "joint_damping": dict.fromkeys(names, damping),
            "joint_effort_limits": dict.fromkeys(names, 30),
        }
        for mode, stiffness, damping in (("usd", 9, 0.1), ("course", 55, 0.7))
    }
    report = R.build_report(
        episodes, raw, R.read_json(ENV / "vials_to_rack.json"), R.UNITS.load_table()
    )
    assert report["final_verdict"] is None
    assert report["measured_substeps"] is None
    assert report["runs"] == {}
    assert R.write_report(report, tmp_path) == 0
    markdown = (tmp_path / "report.md").read_text()
    assert "| shoulder_pan | 9/0.1 | 55/0.7 |" in markdown
    assert "diagnostics only" in markdown
