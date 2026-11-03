"""Portable layout, pinned scene data and Kit-free command checks."""

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from so101_loader import load

ROOT = Path(__file__).resolve().parents[1]
L = load("tube_layout_tests", "robots/so101/envs/vials_to_rack_layout.py")
S = load("tube_rotation_tests", "robots/so101/envs/vials_to_rack_success.py")
SCENE = json.loads((ROOT / "robots/so101/envs/vials_to_rack.json").read_text())


def test_tube_arithmetic_and_rotation() -> None:
    pose = L.tube_pose_for_grasp((0.3, 0.04, 0.2), SCENE)
    assert pose[:3] == pytest.approx((0.3 - (-0.017 + 0.0995) / 2, 0.04, 0.05))
    assert L.tube_pose_for_grasp((0.3, 0.04, 0.2), SCENE, 0.01)[0] == pytest.approx(0.29)
    assert S.rotate_xyzw(pose[3:], (0, 0, 1)) == pytest.approx((1, 0, 0))
    assert [p[:3] for p in L.park_poses(SCENE)] == [(-0.15, -0.25, 0.05), (-0.15, 0.25, 0.05)]


def test_nominal_slot_zero() -> None:
    rack = SCENE["rack"]
    release = [rack["origin_m"][i] + rack["slots_m"][0][i] for i in range(2)]
    pose = L.rack_pose_for_release(release, SCENE)
    assert pose.origin_xyz == pytest.approx(rack["origin_m"])
    assert pose.yaw == 0
    assert pose.slot_index == 0
    assert pose.offset == pytest.approx((0, 0))
    assert pose.inside_dr_box


def test_rotated_slot_alignment() -> None:
    rack = SCENE["rack"]
    x, y, _ = rack["slots_m"][0]
    yaw = 0.5
    release = (
        rack["origin_m"][0] + math.cos(yaw) * x - math.sin(yaw) * y,
        rack["origin_m"][1] + math.sin(yaw) * x + math.cos(yaw) * y,
    )
    pose = L.rack_pose_for_release(release, SCENE)
    assert pose.yaw == pytest.approx(yaw)
    assert pose.offset == pytest.approx((0, 0))
    assert pose.inside_dr_box


def test_unreachable_release_preserves_alignment_and_reports_outside() -> None:
    pose = L.rack_pose_for_release((10, 10), SCENE)
    assert not pose.inside_dr_box
    x, y, _ = SCENE["rack"]["slots_m"][pose.slot_index]
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    assert (
        pose.origin_xyz[0] + c * x - s * y,
        pose.origin_xyz[1] + s * x + c * y,
    ) == pytest.approx((10, 10))


def test_scene_additions() -> None:
    for group in ("light_box", "mat", "tubes", "rack", "contact_sensor", "control"):
        sources = SCENE[group]["source"]
        for source in sources if isinstance(sources, list) else [sources]:
            assert source["repo"].startswith("https://github.com/")
            assert source["commit"].startswith("ce807d9")
            assert source["path"].endswith(".py")
    assert SCENE["tubes"]["mass_kg"] > 0
    assert SCENE["rack"]["mass_kg"] > 0
    assert SCENE["tubes"]["angular_damping"] == 100
    assert SCENE["light_box"]["unloaded_payloads"] == ["LightBox/camera_mount/rsd455"]
    assert SCENE["contact_sensor"]["body"] == "moving_jaw_so101_v1"
    assert len(SCENE["contact_sensor"]["filtered_tubes"]) == 3
    assert SCENE["control"]["physics_dt"] * SCENE["control"]["substeps"] == pytest.approx(1 / 60)
    for group in ("light_box", "mat", "tubes", "rack"):
        assert SCENE[group]["usd"]


def test_success_geometry_matches_scene() -> None:
    assert S.SuccessParams().tube_axis_span_m == tuple(SCENE["tubes"]["axis_span_m"])


@pytest.mark.parametrize(
    ("origin_z", "depth"),
    [(0.073 + 0.017 + 0.003, False), (0.0158, True)],
    ids=["S7b-held-over-slot", "S2-measured-in-slot"],
)
def test_placement_subpredicates(
    origin_z: float, depth: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "robots/so101/tools"))
    tool = load("tube_subpredicates_tests", "robots/so101/tools/isaac_success_check.py")
    params = tool.SUCCESS.SuccessParams()
    slot = SCENE["rack"]["slots_m"][0]
    local = (slot[0], slot[1], origin_z)
    tracker = tool.SUCCESS.SuccessTracker(params)
    vial = tracker.step(
        0,
        [tool.SUCCESS.VialState(0.0, local, (0.0, 0.0, 0.0, 1.0))],
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ).vials[0]
    assert tool.placement_subpredicates(vial, params) == {
        "vertical": True,
        "xy_in_footprint": True,
        "origin_z_below_course_max": True,
        "bottom_below_rim_margin": depth,
        "in_box": depth,
        "placed": False,
        "bottom_local_z": pytest.approx(origin_z - 0.017),
        "rack_local_position": pytest.approx(local),
    }


def test_success_report_preserves_depth_and_episode_peaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "robots/so101/tools"))
    tool = load("tube_success_report_tests", "robots/so101/tools/isaac_success_check.py")
    report = {
        "checks": [
            {
                "name": "S7 upright on rack top",
                "expectation": "vertical True; in_box False; placed False",
                "measured": {"bottom_local_z": 0.073, "rack_local_position": [0.06, 0.06, 0.09]},
                "passed": True,
            }
        ],
        "diagnostic": {
            "episodes": [],
            "pooled": {"tube_1_episode_peak_force_n": [{"index": 7, "max_force_n": 19.0}]},
        },
    }
    tool.write_report(tmp_path, report)
    assert json.loads((tmp_path / "checks.json").read_text()) == report
    markdown = (tmp_path / "report.md").read_text()
    assert "bottom_local_z" in markdown
    assert '"max_force_n": 19.0' in markdown


@pytest.mark.parametrize("tool", ["isaac_mount_compare.py", "isaac_success_check.py"])
def test_help_without_isaac(tool: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "robots/so101/tools" / tool), "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--episodes-json" in result.stdout


def test_asset_check_missing_tampered_and_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "robots/so101/tools"))
    tool = load("tube_asset_check_tests", "robots/so101/tools/isaac_success_check.py")
    manifest = tmp_path / "manifest.json"
    data = b"pinned fixture"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "name": "scene.usda",
                        "use": "scene",
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                ]
            }
        )
    )
    assert "Missing" in tool.check_assets(tmp_path, manifest_path=manifest)[0]
    asset = tmp_path / "scene.usda"
    asset.write_bytes(b"wrong")
    assert "sha256" in tool.check_assets(tmp_path, manifest_path=manifest)[0]
    asset.write_bytes(data)
    assert tool.check_assets(tmp_path, manifest_path=manifest) == []
    asset.write_bytes(b"x" * len(data))
    assert "sha256" in tool.check_assets(tmp_path, manifest_path=manifest)[0]


def test_mount_refuses_bad_usd_before_kit(tmp_path: Path) -> None:
    asset = tmp_path / "renamed.usd"
    asset.write_bytes(b"tampered")
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "robots/so101/tools/isaac_mount_compare.py"),
            "--course-usd",
            str(asset),
            "--episodes-json",
            str(tmp_path / "episodes.json"),
            "--out",
            str(tmp_path / "comparison.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    assert "sha256" in result.stderr
    assert "No module named 'isaaclab'" not in result.stderr
