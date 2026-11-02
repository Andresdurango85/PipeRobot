from __future__ import annotations

import json
from pathlib import Path

import pytest

from piperobot.adapters.manual.evaluate import load_attempts, main
from piperobot.results import ResultsError, load_results
from piperobot.stats.gate import main as gate_main


def test_main_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "attempts.csv"
    path.write_text(
        "scene,attempt,success,failure,video_url\n"
        "dim light,2,no,missed grasp,https://example.com/failure.mp4\n"
        "bright,1,yes,,\n",
        encoding="utf-8",
    )
    output = tmp_path / "out" / "results.json"

    assert main(["--attempts", str(path), "--policy", "p", "--output", str(output)]) == 0
    assert capsys.readouterr().out == "p: 1/2 attempts succeeded\n"
    results = load_results(output)
    assert results.policy == "p"
    assert results.evaluator == "manual"
    assert (results.successes, results.trials) == (1, 2)
    assert [episode.seed for episode in results.episodes] == [1, 2]
    assert [episode.scene for episode in results.episodes] == ["bright", "dim light"]
    assert results.failed[0].failure == "missed grasp"
    assert results.failed[0].video_url == "https://example.com/failure.mp4"
    assert json.loads(output.read_text(encoding="utf-8"))["episodes"][0] == {
        "seed": 1,
        "success": True,
        "scene": "bright",
    }
    assert gate_main(["--results", str(output), "--baseline", "15/20"]) in (0, 1)


@pytest.mark.parametrize(
    ("spelling", "success"),
    [
        (" TrUe ", True),
        (" YES ", True),
        (" 1 ", True),
        (" FaLsE ", False),
        (" No ", False),
        (" 0 ", False),
    ],
)
def test_success_spellings(tmp_path: Path, spelling: str, success: bool) -> None:
    path = tmp_path / "attempts.csv"
    path.write_text(f"attempt,success\n1,{spelling}\n", encoding="utf-8")

    assert load_attempts(path, "p").episodes[0].success is success


@pytest.mark.parametrize("optional", ["", ",failure,scene,video_url"])
def test_empty_optional_fields_are_omitted(tmp_path: Path, optional: str) -> None:
    path = tmp_path / "attempts.csv"
    cells = ",,," if optional else ""
    path.write_text(f"attempt,success{optional}\n1,true{cells}\n", encoding="utf-8")

    assert load_attempts(path, "p").to_dict()["episodes"] == [{"seed": 1, "success": True}]


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_excel_csv(tmp_path: Path, delimiter: str) -> None:
    path = tmp_path / "attempts.csv"
    path.write_bytes(
        f"\ufeffattempt{delimiter}success{delimiter}scene\r\n\r\n"
        f"1{delimiter}yes{delimiter}iluminación\r\n"
        f"{delimiter}{delimiter}\r\n".encode()
    )

    assert load_attempts(path, "p").episodes[0].scene == "iluminación"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("attempt,success\n1,true\n3,false\n", "missing attempts: [2]"),
        ("attempt,success\n1,true\n1,false\n", "duplicated attempts: [1]"),
        (
            "attempt,success\n1,true\n3,false\n3,false\n",
            "missing attempts: [2]; duplicated attempts: [3]",
        ),
        ("attempt,success\n0,true\n", "attempt must be positive"),
        ("attempt,success\nabc,true\n", "attempt must be a positive integer"),
        ("attempt\n1\n", "missing ['success']"),
        ("attempt,success,faliure\n1,false,note\n", "allowed columns:"),
        ("attempt,success,failure\n1,true,note\n", "attempt 1: successful attempt"),
        ("attempt,success\n", "no attempts"),
        ("", "invalid header"),
        ("attempt,success\n1,maybe\n", "attempt 1: invalid success"),
        ("attempt,success\n1,\n", "attempt 1: invalid success"),
        ("attempt,success\n1\n", "line 2: expected"),
        ("attempt,success\n1,true,extra\n", "line 2: expected"),
        ('attempt,success\n1,"true\n', "cannot read attempts"),
        ("attempt,success,success\n1,true,false\n", "column names must be unique"),
    ],
)
def test_invalid_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, message: str
) -> None:
    path = tmp_path / "attempts.csv"
    path.write_text(content, encoding="utf-8")
    output = tmp_path / "results.json"

    with pytest.raises(ResultsError):
        load_attempts(path, "p")
    assert main(["--attempts", str(path), "--policy", "p", "--output", str(output)]) == 2
    error = capsys.readouterr().err
    assert error.startswith("ERROR: ")
    assert str(path) in error
    assert message in error
    assert not output.exists()


@pytest.mark.parametrize("invalid_bytes", [None, b"attempt,success\n1,\xff\n"])
def test_unreadable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid_bytes: bytes | None
) -> None:
    path = tmp_path / "attempts.csv"
    if invalid_bytes is not None:
        path.write_bytes(invalid_bytes)
    output = tmp_path / "results.json"

    assert main(["--attempts", str(path), "--policy", "p", "--output", str(output)]) == 2
    error = capsys.readouterr().err
    assert error.startswith("ERROR: ")
    assert str(path) in error
    assert "cannot read attempts" in error
    if invalid_bytes is not None:
        assert "save as 'CSV UTF-8'" in error
    assert not output.exists()
