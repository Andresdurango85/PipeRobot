"""Mutation reporting without invoking mutmut or depending on a live run."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mutation_summary", ROOT / ".github/scripts/mutation_summary.py"
)
assert SPEC is not None
assert SPEC.loader is not None
summary_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary_script)

ACCEPTED = "piperobot.stats.gate.xǁSuccessCountǁparse__mutmut_3"
NEW = "piperobot.stats.gate.x_decide__mutmut_99"
STALE = "piperobot.stats.baseline.x_load_baseline__mutmut_5"


def test_parse_results() -> None:
    text = f"""Loading mutants...
    {ACCEPTED}: survived
    {NEW}: no tests
    piperobot.stats.paired.x_exact_mcnemar_p__mutmut_1: killed
"""
    assert summary_script.parse_results(text) == {
        ACCEPTED: "survived",
        NEW: "no tests",
        "piperobot.stats.paired.x_exact_mcnemar_p__mutmut_1": "killed",
    }


def test_real_equivalents() -> None:
    equivalents = summary_script.load_equivalents(ROOT / "tests/mutation_equivalents.txt")
    assert len(equivalents) == 10
    assert all(equivalents.values())
    assert ACCEPTED in equivalents


@pytest.mark.parametrize(
    "line",
    [
        "missing",
        "piperobot.foo",
        "piperobot.foo #",
        "other.foo # reason",
        "piperobot. # reason",
        "piperobot.two names # reason",
        "  #\nno name # reason",
    ],
)
def test_malformed_equivalents(tmp_path: Path, line: str) -> None:
    path = tmp_path / "equivalents.txt"
    path.write_text(line, encoding="utf-8")
    with pytest.raises(ValueError, match=r"expected.*reason"):
        summary_script.load_equivalents(path)


def test_duplicate_equivalent_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "equivalents.txt"
    line = "piperobot.stats.gate.x_decide__mutmut_26  # reason\n"
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match="listed twice"):
        summary_script.load_equivalents(path)


def test_comments_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "equivalents.txt"
    path.write_text(f"# header\n\n  # comment\n{ACCEPTED} # reason\n", encoding="utf-8")
    assert summary_script.load_equivalents(path) == {ACCEPTED: "reason"}


def test_classify() -> None:
    assert summary_script.classify([NEW, ACCEPTED], {ACCEPTED: "reason", STALE: "reason"}) == (
        [ACCEPTED],
        [NEW],
        [STALE],
    )
    assert summary_script.classify([], {}) == ([], [], [])


@pytest.mark.parametrize("case", ["new", "no tests", "accepted", "malformed"])
def test_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(output))
    (tmp_path / "mutants").mkdir()
    (tmp_path / "mutants/mutmut-cicd-stats.json").write_text(
        '{"killed": 90, "total": 100}', encoding="utf-8"
    )
    equivalents = tmp_path / "equivalents.txt"
    contents = f"{ACCEPTED} # equivalent reason\n"
    if case == "new":
        contents += f"{STALE} # old reason\n"
    equivalents.write_text("invalid" if case == "malformed" else contents, encoding="utf-8")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        text = f"    {ACCEPTED}: survived\n"
        if case in {"new", "no tests"}:
            text += f"    {NEW}: {'survived' if case == 'new' else 'no tests'}\n"
        if command[3] == "show":
            return subprocess.CompletedProcess(
                command, 0, f"-old {command[4]}\n+new", "diff stderr"
            )
        return subprocess.CompletedProcess(command, 0, text, "")

    code = summary_script.main([str(equivalents)], runner=runner)
    log = capsys.readouterr().out
    assert code == {"new": 0, "no tests": 1, "accepted": 0, "malformed": 2}[case]
    if case == "malformed":
        assert "::error::Invalid equivalent-mutant list" in log
        assert not commands
        return
    text = output.read_text(encoding="utf-8")
    assert "90 / 100 (90.0%)" in text
    assert f"| {ACCEPTED} | equivalent (accepted) | equivalent reason |" in text
    assert f"::group::{ACCEPTED}" in log
    assert "diff stderr" in text
    if case == "new":
        assert f"| {NEW} | NEW — review |" in text
        assert f"::warning::NEW surviving mutant — review: {NEW}" in log
        assert f"::notice::Stale equivalent (killed or renamed): {STALE}" in log
        assert f"{STALE}: stale" in text
        assert text.index(f"### {NEW}") < text.index(f"### {ACCEPTED}")
        assert [command[4] for command in commands[1:]] == [NEW, ACCEPTED]
    elif case == "no tests":
        assert "::error::1 mutants have no tests: piperobot.stats.gate" in log
        assert "1 mutants reached by no test" in text
    else:
        assert "::warning::" not in log
        assert "::notice::" not in log
