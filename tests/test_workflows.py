"""Workflow and runner trust boundaries (ADR 0020, ADR 0027)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
HOOK = ROOT / ".github" / "runner" / "job-started.ps1"
REPOSITORY = "Andresdurango85/PipeRobot"
REF = f"{REPOSITORY}/.github/workflows/"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _load(path: Path) -> dict[str | bool, Any]:
    data: dict[str | bool, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _self_hosted_jobs(data: dict[str | bool, Any]) -> list[dict[str, Any]]:
    return [job for job in data["jobs"].values() if "self-hosted" in _labels(job)]


def _labels(job: dict[str, Any]) -> list[str]:
    labels = job.get("runs-on", [])
    return [labels] if isinstance(labels, str) else labels


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_self_hosted_events(path: Path) -> None:
    """Check our workflows for regressions; only the runner hook stops fork additions (ADR 0027)."""
    data = _load(path)
    if _self_hosted_jobs(data):
        # PyYAML follows YAML 1.1, where the bare key `on` loads as the boolean True.
        triggers = data.get("on", data.get(True))
        assert isinstance(triggers, (str, list, dict)), "missing or invalid workflow triggers"
        events = {triggers} if isinstance(triggers, str) else set(triggers)
        assert events
        assert events <= {"push", "workflow_dispatch", "schedule"}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_self_hosted_gpu_label(path: Path) -> None:
    """Target GPU runners explicitly instead of any available machine (ADR 0020)."""
    for job in _self_hosted_jobs(_load(path)):
        assert "gpu" in _labels(job)


def test_runner_allowlist_matches_workflows() -> None:
    text = HOOK.read_text(encoding="utf-8")
    match = re.search(r"^\$AllowedWorkflows = @\(([^\n]+)\)$", text, re.M)
    assert match, "missing runner allowlist"
    allowed = set(re.findall(r"'([^']+)'", match[1]))
    assert allowed == {path.name for path in WORKFLOWS if _self_hosted_jobs(_load(path))}


def _uses(data: dict[str | bool, Any]) -> list[str]:
    uses: list[str] = []
    for job in data["jobs"].values():
        if "uses" in job:
            uses.append(job["uses"])
        uses.extend(step["uses"] for step in job.get("steps", []) if "uses" in step)
    return uses


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_with_version_comments(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for uses in _uses(_load(path)):
        if uses.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-fA-F]{40}", uses)
        assert re.search(
            rf"^\s*(?:-\s+)?uses:\s*['\"]?{re.escape(uses)}['\"]?\s+# v\S+.*$",
            text,
            re.M,
        ), f"missing version comment: {uses}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_checkout_does_not_persist_credentials(path: Path) -> None:
    for job in _load(path)["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
@pytest.mark.parametrize(
    ("event", "workflow_ref", "repository", "expected"),
    [
        ("push", REF + "gpu-smoke.yml@refs/heads/feature/test", REPOSITORY, 0),
        ("workflow_dispatch", REF + "isaac-render.yml@refs/heads/main", REPOSITORY, 0),
        ("schedule", REF + "gpu-smoke.yml@refs/heads/main", REPOSITORY, 0),
        ("pull_request", REF + "gpu-smoke.yml@refs/heads/main", REPOSITORY, 1),
        ("pull_request_target", REF + "gpu-smoke.yml@refs/heads/main", REPOSITORY, 1),
        ("push", REF + "gpu-smoke.yml@refs/pull/7/merge", REPOSITORY, 1),
        ("push", REF + "gpu-smoke.yml@refs/tags/v1", REPOSITORY, 1),
        ("push", REF + "untrusted.yml@refs/heads/main", REPOSITORY, 1),
        ("push", REF + "gpu-smoke.yml@refs/heads/main", "someone/fork", 1),
        ("push", None, REPOSITORY, 1),
        (None, REF + "gpu-smoke.yml@refs/heads/main", REPOSITORY, 1),
        ("push", REF + "gpu-smoke.yml@refs/heads/main", None, 1),
    ],
)
def test_runner_hook(
    event: str | None, workflow_ref: str | None, repository: str | None, expected: int
) -> None:
    """Refusals leave the Python parent alive and print only the refusal line."""
    assert POWERSHELL is not None
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GITHUB_")}
    for key, value in {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_WORKFLOW_REF": workflow_ref,
        "GITHUB_REPOSITORY": repository,
    }.items():
        if value is not None:
            env[key] = value
    result = subprocess.run(  # noqa: S603 -- resolved PowerShell executable and fixed script, no shell.
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(HOOK)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert len(result.stdout.strip().splitlines()) == 1
    assert result.stdout.startswith("Allowed job:" if expected == 0 else "Refused job:")


def _run_completed_hook(
    workspace: Path | None, runner: Path | None
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"GITHUB_WORKSPACE", "RUNNER_WORKSPACE"}
    }
    for key, path in {"GITHUB_WORKSPACE": workspace, "RUNNER_WORKSPACE": runner}.items():
        if path is not None:
            env[key] = str(path)
    return subprocess.run(  # noqa: S603 -- resolved PowerShell and fixed script, no shell.
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(HOOK.with_name("job-completed.ps1")),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
def test_completed_hook_wipes_workspace(tmp_path: Path) -> None:
    runner = tmp_path / "_work" / "PipeRobot"
    workspace = runner / "PipeRobot"
    workspace.mkdir(parents=True)
    for name in (
        "nested/deeper/file.txt",
        ".hidden",
        "readonly.txt",
        "out/failure.mp4",
        "work/data",
    ):
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("leftover", encoding="utf-8")
    (workspace / "readonly.txt").chmod(0o444)
    if sys.platform == "win32":  # mypy understands this guard for ctypes.windll, not os.name
        import ctypes

        assert ctypes.windll.kernel32.SetFileAttributesW(str(workspace / ".hidden"), 2)
    keep = tmp_path / "_work" / "_tool" / "keep.txt"
    keep.parent.mkdir()
    keep.write_text("keep", encoding="utf-8")
    result = _run_completed_hook(workspace, runner)
    assert result.returncode == 0, result.stdout + result.stderr
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []
    assert keep.read_text(encoding="utf-8") == "keep"
    assert result.stdout.strip() == f"Wiped job workspace: {workspace} (5 entries)."


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junctions require Windows")
@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
def test_completed_hook_does_not_follow_junctions(tmp_path: Path) -> None:
    runner = tmp_path / "_work" / "PipeRobot"
    workspace = runner / "PipeRobot"
    (workspace / "sub").mkdir(parents=True)
    precious = tmp_path / "outside" / "precious.txt"
    keep = tmp_path / "_work" / "_tool" / "keep.txt"
    for sentinel in (precious, keep):
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("keep", encoding="utf-8")
    for link, target in (
        (workspace / "outside-link", precious.parent),
        (workspace / "tool-link", keep.parent),
        (workspace / "sub" / "link", precious.parent),
    ):
        result = subprocess.run(  # noqa: S603 -- Windows mklink, tmp paths, no shell=True.
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607 -- Windows builtin.
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    result = _run_completed_hook(workspace, runner)
    assert result.returncode == 0, result.stdout + result.stderr
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []
    assert precious.read_text(encoding="utf-8") == "keep"
    assert keep.read_text(encoding="utf-8") == "keep"
    assert result.stdout.strip() == f"Wiped job workspace: {workspace} (3 entries)."


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
@pytest.mark.parametrize(
    "case",
    [
        "not-direct-child",
        "wrong-parent",
        "runner-tool",
        "protected-leaf",
        "missing-workspace",
        "missing-runner",
        "missing-both",
        "nonexistent-workspace",
        "nonexistent-runner",
    ],
)
def test_completed_hook_refuses_unsafe_paths(tmp_path: Path, case: str) -> None:
    runner = tmp_path / "_work" / "PipeRobot"
    workspace = runner / "PipeRobot"
    if case == "not-direct-child":
        workspace = workspace / "nested"
    elif case == "wrong-parent":
        runner = tmp_path / "other" / "PipeRobot"
        workspace = runner / "PipeRobot"
    elif case == "runner-tool":
        runner = tmp_path / "_work"
        workspace = runner / "_tool"
    elif case == "protected-leaf":
        workspace = runner / "_tool"
    workspace.mkdir(parents=True)
    sentinel = workspace / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    workspace_env: Path | None = workspace
    runner_env: Path | None = runner
    if case in {"missing-workspace", "missing-both"}:
        workspace_env = None
    if case in {"missing-runner", "missing-both"}:
        runner_env = None
    if case == "nonexistent-workspace":
        workspace_env = sentinel.parent / "absent"
    if case == "nonexistent-runner":
        runner_env = tmp_path / "_work" / "absent"
    result = _run_completed_hook(workspace_env, runner_env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("Refused workspace wipe:")
    assert len(result.stdout.strip().splitlines()) == 1
    assert sentinel.read_text(encoding="utf-8") == "keep"
