"""Optional video evidence remains independent of the gate verdict."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piperobot.reports.video_manifest import build_manifest
from piperobot.reports.video_manifest import main as manifest_main
from piperobot.reports.video_section import NOTHING_SELECTED, VIDEO_MARKER, render_video_section
from piperobot.reports.video_seeds import main as seeds_main
from piperobot.reports.video_seeds import select_video_seeds
from piperobot.results import EpisodeResult, EvalResults, save_results


def results(successes: set[int], count: int = 9) -> EvalResults:
    return EvalResults(
        "policy",
        "test",
        tuple(EpisodeResult(seed, seed in successes) for seed in reversed(range(count))),
    )


def test_no_lost_even_with_failures() -> None:
    assert select_video_seeds(results({1}), results({1})).seeds == []


def test_lost_then_failed_sorted_and_capped() -> None:
    selection = select_video_seeds(results({2, 4}), results(set()))
    assert selection.to_dict()["seed_list"] == "2,4,0,1,3"
    kinds = [item["kind"] for item in selection.seeds]
    assert kinds == ["lost", "lost", "failed", "failed", "failed"]
    assert len(select_video_seeds(results({2}), results(set()), cap=2).seeds) == 2


def test_more_than_five_lost() -> None:
    selection = select_video_seeds(results(set(range(9))), results(set()))
    assert selection.to_dict()["seed_list"] == "0,1,2,3,4"


def test_reference_with_more_seeds_pairs_on_candidate_seeds() -> None:
    selection = select_video_seeds(results({2, 4, 15}, count=20), results(set()))
    assert selection.to_dict()["seed_list"] == "2,4,0,1,3"


def test_reference_missing_candidate_seeds_records_nothing() -> None:
    selection = select_video_seeds(results({2}, count=5), results(set()))
    assert not selection.seeds
    assert "baseline lacks" in (selection.reason or "")


def test_no_reference() -> None:
    selection = select_video_seeds(None, results(set()))
    assert not selection.seeds
    assert "baseline" in (selection.reason or "").lower()


def test_selection_cli(tmp_path: Path) -> None:
    ref, cand, output = (tmp_path / name for name in ("ref.json", "cand.json", "selection.json"))
    save_results(results({3}), ref)
    save_results(results(set()), cand)
    args = ["--reference", str(ref), "--candidate", str(cand), "--output", str(output)]
    assert seeds_main(args) == 0
    assert json.loads(output.read_text())["seed_list"] == "3,0,1,2,4"


def test_manifest_and_cleanup(tmp_path: Path) -> None:
    selection = {"seeds": [{"seed": n, "kind": "lost"} for n in range(3)]}
    judged = [
        {"seed": n, "success": False, "failure": "dropped", "trajectory_sha256": "abc"}
        for n in range(3)
    ]
    recorded = [{**judged[0], "frames": 4}, {**judged[1], "trajectory_sha256": "other"}]
    manifest = build_manifest(selection, judged, recorded)
    assert [entry["status"] for entry in manifest["seeds"]] == ["matched", "diverged", "missing"]
    assert manifest["seeds"][0]["frames"] == 4
    for seed in range(3):
        (tmp_path / "frames" / str(seed)).mkdir(parents=True)
    for name, data in (("selection", selection), ("judged", judged), ("recorded", recorded)):
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    args = [
        value
        for name in ("selection", "judged", "recorded")
        for value in (f"--{name}", str(tmp_path / f"{name}.json"))
    ]
    args += ["--frames-dir", str(tmp_path / "frames")]
    args += ["--output", str(tmp_path / "manifest.json")]
    assert manifest_main(args) == 0
    assert (tmp_path / "frames/0").exists()
    assert not (tmp_path / "frames/1").exists()
    assert not (tmp_path / "frames/2").exists()


@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_unfinished_section(result: str) -> None:
    assert "did not finish" in render_video_section({"seeds": []}, job_result=result)


def test_section_cases() -> None:
    no_baseline = render_video_section({"seeds": [], "reason": "No baseline."})
    assert "\nNo baseline.\n" in no_baseline
    assert NOTHING_SELECTED not in no_baseline
    skip = {
        "short": "commit (host memory)",
        "free_mib": 12288,
        "needed_mib": 19456,
        "free_vram_mib": 10240,
        "needed_vram_mib": 5888,
    }
    memory = render_video_section({}, skip=skip)
    assert (
        "Videos not recorded: not enough free commit (host memory) (free commit 12.0 GiB, "
        "needs 19.0 GiB; free VRAM 10.0 GiB, needs 5.8 GiB)."
    ) in memory
    selection = {"seeds": [{"seed": n, "kind": "lost"} for n in range(3)]}
    manifest = {
        "seeds": [
            {"seed": 0, "status": "matched", "frames": 5},
            {"seed": 1, "status": "diverged"},
        ]
    }
    section = render_video_section(selection, manifest, artifact_url="https://example.org/artifact")
    assert "in artifact" in section
    assert "re-run diverged from the judged episode; no video" in section
    assert "recording missing; no video" in section
    assert "simulation only, kept 7 days" in section
    assert "did not finish" in render_video_section(selection)


def test_empty_selection_and_skipped_job() -> None:
    body = render_video_section({"seeds": []}, job_result="skipped")
    assert NOTHING_SELECTED in body
    assert "did not finish" not in body


def test_video_comment_provenance() -> None:
    sha = "0123456789abcdef"
    run_url = "https://github.com/owner/repo/actions/runs/123"
    body = render_video_section({"seeds": []}, commit=sha, run_url=run_url)
    assert body.startswith(VIDEO_MARKER + "\n## SO-101 failed-episode videos\n")
    assert f"[{sha[:7]}]" in body
    assert f"https://github.com/owner/repo/commit/{sha}" in body
    assert run_url in body


def test_section_cli(tmp_path: Path) -> None:
    from piperobot.reports.video_section import main

    selection = tmp_path / "selection.json"
    selection.write_text('{"seeds": [], "reason": "No baseline."}')
    output = tmp_path / "section.md"
    args = [
        "--selection",
        str(selection),
        "--job-result",
        "success",
        "--commit",
        "0123456789abcdef",
        "--run-url",
        "https://github.com/owner/repo/actions/runs/123",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert "No baseline." in output.read_text()
