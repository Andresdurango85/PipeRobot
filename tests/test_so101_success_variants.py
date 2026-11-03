"""Synthetic attribution and dump round-trip tests; no simulator required."""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import pytest
from so101_loader import load

V = load("success_variants_tests", "robots/so101/tools/success_variants.py")


def synthetic_dump(height: float, residual: float) -> dict:
    params = V.S.SuccessParams(warmup_steps=0, confirm_steps=2, grasp_history_window=4)
    return {
        "episode_index": 46,
        "grasp_frame": 0,
        "release_frame": 1,
        "rack_pose": {"position": [0, 0, 0.041]},
        "success_params": asdict(params),
        "steps": [
            {
                "step_index": index,
                "vials": [
                    {
                        "force_n": force,
                        "position": [0.06, 0.06, height + 0.041],
                        "quaternion_xyzw": [0, math.sin(0.1), 0, math.cos(0.1)],
                    }
                ],
                "rack_position": [0, 0, 0.041],
                "rack_quaternion_xyzw": [0, 0, 0, 1],
            }
            for index, force in enumerate([10.0, residual, residual, residual])
        ],
    }


@pytest.mark.parametrize(
    ("height", "residual", "expected"),
    [
        (0.09, 0.0, [False, True, False, True]),
        (0.04, 3.0, [False, False, True, True]),
        (0.04, 0.0, [True, True, True, True]),
    ],
    ids=["depth-only", "force-only", "all-pass"],
)
def test_rule_attribution(height: float, residual: float, expected: list[bool]) -> None:
    result = V.replay_dump(synthetic_dump(height, residual))
    assert [item["success"] for item in result["variants"].values()] == expected
    for variant, success in zip(result["variants"].values(), expected, strict=True):
        assert variant["success_step"] == (2 if success else None)
        assert variant["failure_reason"] == (None if success else "not_placed")
    depth = result["depth"]
    assert depth["count"] == 3
    bottom = height - 0.017 * math.cos(0.2)
    for name in ("minimum", "median"):
        assert depth[name]["bottom_local_z"] == pytest.approx(bottom)
        assert depth[name]["margin_above_bound_m"] == pytest.approx(bottom - 0.053)
        assert depth[name]["tilt_deg"] == pytest.approx(math.degrees(0.2))


def test_cli_multiple_files_and_empty_depth(tmp_path: Path) -> None:
    paths = []
    for index, height in enumerate((0.04, 0.2)):
        dump = synthetic_dump(height, 0.0)
        dump["episode_index"] = index
        path = tmp_path / f"dump_{index}.json"
        path.write_text(json.dumps(dump), encoding="utf-8")
        paths.append(str(path))
    out = tmp_path / "out"
    assert V.main(["--dumps", *paths, "--out", str(out)]) == 0
    episodes = json.loads((out / "success_variants.json").read_text())["episodes"]
    assert episodes[1]["depth"] == {"count": 0, "minimum": None, "median": None}
    markdown = (out / "success_variants.md").read_text()
    assert "force_2n_depth_on" in markdown
    assert "not_placed" in markdown
    assert "n/a" in markdown


def test_dump_exact_inputs_and_indices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "robots/so101/tools"))
    tool = load("success_dump_tests", "robots/so101/tools/isaac_success_check.py")
    dump = synthetic_dump(0.04, 0.0)
    tool.write_episode_dump(
        tmp_path,
        46,
        0,
        1,
        dump["rack_pose"],
        tool.SUCCESS.SuccessParams(**dump["success_params"]),
        dump["steps"],
    )
    assert json.loads((tmp_path / "dump_episode_46.json").read_text()) == json.loads(
        json.dumps(dump)
    )
    assert tool.episode_indices("0,46,51,55") == {0, 46, 51, 55}
    for invalid in ("-1", "a", "1,", ""):
        with pytest.raises(argparse.ArgumentTypeError, match="comma-separated nonnegative"):
            tool.episode_indices(invalid)
