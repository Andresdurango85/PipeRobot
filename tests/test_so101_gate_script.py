"""SO-101 change detection and required verdict without simulation."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("so101_gate", ROOT / ".github/scripts/so101_gate.py")
assert SPEC is not None
assert SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("piperobot/results.py", "piperobot/**/*.py", True),
        ("piperobot/stats/paired.py", "piperobot/*.py", False),
        ("piperobot/a/b.py", "piperobot/**", True),
        ("piperobotx/a.py", "piperobot/**", False),
        ("uv.lock", "uv.lock", True),
        ("uv.lock.bak", "uv.lock", False),
    ],
)
def test_matches(path: str, pattern: str, expected: bool) -> None:
    assert gate.matches(path, pattern) is expected


def test_is_relevant() -> None:
    assert not gate.is_relevant(["docs/x.md"])
    assert gate.is_relevant(["docs/x.md", "robots/so101/policies/p.json"])


@pytest.mark.parametrize(
    ("event", "mode", "changes", "relevant", "bot", "evaluate", "report", "passed", "phrase"),
    [
        ("push", "gate", "failure", "false", "false", "skipped", "skipped", False, "no verdict"),
        ("push", "gate", "cancelled", "true", "false", "skipped", "skipped", False, "cancelled"),
        (
            "workflow_dispatch",
            "baseline",
            "success",
            "true",
            "true",
            "failure",
            "skipped",
            True,
            "baseline mode",
        ),
        (
            "push",
            "gate",
            "success",
            "false",
            "true",
            "skipped",
            "skipped",
            True,
            "no gate-relevant change",
        ),
        ("push", "gate", "success", "true", "true", "skipped", "skipped", False, "Dependabot"),
        ("push", "gate", "success", "true", "false", "success", "success", True, "ran and passed"),
        ("push", "gate", "success", "true", "false", "failure", "skipped", False, "did not pass"),
        ("push", "gate", "success", "true", "false", "success", "failure", False, "did not pass"),
        ("push", "gate", "success", "true", "false", "cancelled", "skipped", False, "did not pass"),
        ("push", "gate", "success", "true", "false", "skipped", "skipped", False, "did not pass"),
        (
            "workflow_dispatch",
            "gate",
            "success",
            "true",
            "false",
            "success",
            "success",
            True,
            "ran and passed",
        ),
        (
            "workflow_dispatch",
            "gate",
            "success",
            "true",
            "false",
            "failure",
            "skipped",
            False,
            "did not pass",
        ),
        (
            "workflow_dispatch",
            "baseline",
            "failure",
            "true",
            "false",
            "success",
            "success",
            False,
            "no verdict",
        ),
    ],
)
def test_verdict(
    event: str,
    mode: str,
    changes: str,
    relevant: str,
    bot: str,
    evaluate: str,
    report: str,
    passed: bool,
    phrase: str,
) -> None:
    result, message = gate.verdict(
        event=event,
        mode=mode,
        changes=changes,
        relevant=relevant,
        dependabot=bot,
        evaluate=evaluate,
        report=report,
    )
    assert result is passed
    assert phrase in message


def test_changed_files(tmp_path: Path, git_binary: str) -> None:
    def git(arguments: list[str]) -> str:
        return subprocess.run(  # noqa: S603 -- fixture git, local temporary repository.
            [git_binary, *arguments], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git(["init", "-b", "main"])
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
    ):
        git(["config", key, value])

    def commit(path: str) -> str:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path, encoding="utf-8")
        git(["add", path])
        git(["commit", "-m", "test"])
        return git(["rev-parse", "HEAD"])

    base = commit("initial.txt")
    git(["update-ref", "refs/remotes/origin/main", base])
    git(["checkout", "-b", "feature"])
    policy = commit("robots/so101/policies/p.json")
    head = commit("docs/x.md")
    files = gate.changed_files(ref="refs/heads/feature", sha=head, before=policy, git=git)
    assert "robots/so101/policies/p.json" in files
    assert gate.is_relevant(files)
    git(["checkout", "main"])
    head = commit("docs/main.md")
    files = gate.changed_files(ref="refs/heads/main", sha=head, before=base, git=git)
    assert files == ["docs/main.md"]
    assert not gate.is_relevant(files)
    for before in ("", "0" * 40, "a" * 40):
        assert gate.changed_files(ref="refs/heads/main", sha=head, before=before, git=git) is None
    assert gate.changed_files(ref="refs/heads/feature", sha="unknown", before=base, git=git) is None


@pytest.mark.parametrize("bot", ["owner", "dependabot[bot]"])
def test_changes_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bot: str) -> None:
    output, summary = tmp_path / "output", tmp_path / "summary"
    for key, value in {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "head",
        "BEFORE": "",
        "ACTOR": bot,
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }.items():
        monkeypatch.setenv(key, value)
    assert gate.main(["changes"]) == 0
    assert (
        output.read_text() == f"relevant=true\ndependabot={str(bot == 'dependabot[bot]').lower()}\n"
    )
    assert "gate-relevant" in summary.read_text()


@pytest.mark.parametrize("passed", [True, False])
def test_verdict_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passed: bool,
) -> None:
    summary = tmp_path / "summary"
    for key, value in {
        "EVENT": "push",
        "MODE": "gate",
        "CHANGES": "success",
        "RELEVANT": "true",
        "DEPENDABOT": "false",
        "EVALUATE": "success" if passed else "failure",
        "REPORT": "success" if passed else "skipped",
        "GITHUB_STEP_SUMMARY": str(summary),
    }.items():
        monkeypatch.setenv(key, value)
    assert gate.main(["verdict"]) == (0 if passed else 1)
    log = capsys.readouterr().out
    assert ("::error::" in log) is not passed
    assert ("ran and passed" if passed else "did not pass") in summary.read_text()


@pytest.mark.parametrize("action", ["changes", "verdict"])
def test_missing_environment(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert gate.main([action]) == 2


@pytest.mark.parametrize(
    ("diff", "relevant", "phrase"),
    [
        ("docs/x.md\n", "false", "no gate-relevant change"),
        ("docs/x.md\nuv.lock\n", "true", "gate-relevant changes: uv.lock"),
        (None, "true", "changes unknown"),
    ],
)
def test_changes_cli_on_a_branch_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diff: str | None, relevant: str, phrase: str
) -> None:
    calls: list[list[str]] = []

    def git(arguments: list[str]) -> str:
        calls.append(arguments)
        if diff is None:
            raise subprocess.CalledProcessError(128, ["git", *arguments])
        return "base\n" if arguments[0] == "merge-base" else diff

    output, summary = tmp_path / "output", tmp_path / "summary"
    for key, value in {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/feature",
        "GITHUB_SHA": "head",
        "BEFORE": "previous",
        "ACTOR": "owner",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(gate, "_git", git)
    assert gate.main(["changes"]) == 0
    assert output.read_text() == f"relevant={relevant}\ndependabot=false\n"
    assert phrase in summary.read_text()
    assert calls[0] == ["fetch", "--no-tags", "origin", "main"]
    if diff is not None:
        assert calls[1:] == [
            ["merge-base", "origin/main", "head"],
            ["diff", "--name-only", "base", "head"],
        ]
