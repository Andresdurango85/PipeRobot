"""Workflow and runner trust boundaries (ADR 0020, ADR 0027)."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
HOOK = ROOT / ".github" / "runner" / "job-started.ps1"
REPOSITORY = "Andresdurango85/PipeRobot"
REF = f"{REPOSITORY}/.github/workflows/"

SPEC = importlib.util.spec_from_file_location("so101_gate", ROOT / ".github/scripts/so101_gate.py")
assert SPEC is not None
assert SPEC.loader is not None
gate_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate_script)


def _load(path: Path) -> dict[str | bool, Any]:
    data: dict[str | bool, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def test_dependabot_ignores_torch_minor_and_major_updates() -> None:
    data = _load(ROOT / ".github" / "dependabot.yml")
    uv = next(update for update in data["updates"] if update["package-ecosystem"] == "uv")
    for dependency in ("torch", "torchvision"):
        rules = [rule for rule in uv["ignore"] if rule["dependency-name"] == dependency]
        assert len(rules) == 1
        assert sorted(rules[0]["update-types"]) == [
            "version-update:semver-major",
            "version-update:semver-minor",
        ]


def test_dependabot_torch_ignores_still_have_minor_caps() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra: list[str] = data["project"]["optional-dependencies"]["lerobot"]
    for dependency in ("torch", "torchvision"):
        pins = [pin for pin in extra if re.match(rf"^{dependency}(?=[<>=!~;\s]|$)", pin)]
        assert len(pins) == 1, f"Revisit the Dependabot ignore rule for {dependency}: missing pin"
        assert re.search(r"(?:^|,)\s*<\d+\.\d+\s*(?:,|$)", pins[0]), (
            f"Revisit the Dependabot ignore rule for {dependency}: missing <X.Y minor cap"
        )


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
        if uses.startswith(("./", "$/")):  # same-repo references run at the caller's commit
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
    event: str | None,
    workflow_ref: str | None,
    repository: str | None,
    expected: int,
    powershell: str,
) -> None:
    """Refusals leave the Python parent alive and print only the refusal line."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GITHUB_")}
    for key, value in {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_WORKFLOW_REF": workflow_ref,
        "GITHUB_REPOSITORY": repository,
    }.items():
        if value is not None:
            env[key] = value
    result = subprocess.run(  # noqa: S603 -- resolved PowerShell executable and fixed script, no shell.
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(HOOK)],
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
    workspace: Path | None, runner: Path | None, powershell: str
) -> subprocess.CompletedProcess[str]:
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
            powershell,
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


def test_completed_hook_wipes_workspace(tmp_path: Path, powershell: str) -> None:
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
    result = _run_completed_hook(workspace, runner, powershell)
    assert result.returncode == 0, result.stdout + result.stderr
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []
    assert keep.read_text(encoding="utf-8") == "keep"
    assert result.stdout.strip() == f"Wiped job workspace: {workspace} (5 entries)."


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junctions require Windows")
def test_completed_hook_does_not_follow_junctions(tmp_path: Path, powershell: str) -> None:
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
    result = _run_completed_hook(workspace, runner, powershell)
    assert result.returncode == 0, result.stdout + result.stderr
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []
    assert precious.read_text(encoding="utf-8") == "keep"
    assert keep.read_text(encoding="utf-8") == "keep"
    assert result.stdout.strip() == f"Wiped job workspace: {workspace} (3 entries)."


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
def test_completed_hook_refuses_unsafe_paths(tmp_path: Path, case: str, powershell: str) -> None:
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
    result = _run_completed_hook(workspace_env, runner_env, powershell)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("Refused workspace wipe:")
    assert len(result.stdout.strip().splitlines()) == 1
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_history_signing_boundary() -> None:
    jobs = _load(ROOT / ".github/workflows/history.yml")["jobs"]
    assert jobs["evaluate"]["permissions"] == {"contents": "read"}
    caller = jobs["certify"]
    assert caller["uses"] == "$/.github/workflows/certify.yml"
    assert caller["needs"] == "evaluate"
    assert caller["if"] == "github.ref == 'refs/heads/main'"
    assert caller["with"] == {"series": "main", "artifact": "history-evaluation"}
    assert caller["permissions"] == {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
        "pages": "write",
    }
    data = _load(ROOT / ".github/workflows/certify.yml")
    assert data.get("on", data.get(True)) == {
        "workflow_call": {
            "inputs": {
                "series": {"type": "string", "required": True},
                "artifact": {"type": "string", "required": True},
            }
        }
    }
    assert data["permissions"] == {}
    permissions = {
        "attest": {"contents": "read", "id-token": "write", "attestations": "write"},
        "append": {"contents": "write"},
        "deploy": {"contents": "read", "pages": "write", "id-token": "write"},
    }
    assert set(data["jobs"]) == set(permissions)
    for name, job in data["jobs"].items():
        assert job["permissions"] == permissions[name]
        assert job["runs-on"] == "ubuntu-24.04"
        assert job["if"] == "github.ref == 'refs/heads/main'"
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")
            assert "artifact-metadata" not in step.get("with", {})
    attest = data["jobs"]["attest"]
    record_script = next(
        step["run"] for step in attest["steps"] if step.get("name") == "Write the record"
    )
    assert "evidence=(out/reference_commit.txt)" in record_script
    assert any(
        '"${evidence[@]}"' in line
        for line in record_script.splitlines()
        if line.startswith("for file in ")
    )
    verdict = next(step for step in attest["steps"] if step.get("id") == "verdict")
    assert verdict["with"] == {
        "subject-path": "${{ steps.record.outputs.subjects }}",
        "predicate-type": "${{ steps.record.outputs.type }}",
        "predicate-path": "out/record.json",
    }
    provenance = next(step for step in attest["steps"] if step.get("id") == "provenance")
    assert provenance["with"]["subject-path"].splitlines() == [
        "${{ steps.record.outputs.subjects }}",
        "out/record.json",
    ]
    append = data["jobs"]["append"]
    assert append["needs"] == "attest"
    assert "concurrency" not in append
    downloads = [
        step["with"]["name"]
        for step in append["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert downloads == ["history-certified"]
    script = next(
        step["run"]
        for step in append["steps"]
        if step.get("name") == "Append evaluation to history"
    )
    assert "--record out/record.json" in script
    for destination in (
        "results/$GITHUB_RUN_ID.$GITHUB_RUN_ATTEMPT.json",
        "results/$GITHUB_RUN_ID.$GITHUB_RUN_ATTEMPT.reference.json",
        "bundles/$GITHUB_RUN_ID.$GITHUB_RUN_ATTEMPT.jsonl",
    ):
        assert destination in script
    assert data["jobs"]["deploy"]["needs"] == "append"
    assert data["jobs"]["deploy"]["concurrency"] == {"group": "pages", "cancel-in-progress": False}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_certify_callers_use_relative_path(path: Path) -> None:
    for uses in _uses(_load(path)):
        if "certify.yml" in uses:
            assert uses == "$/.github/workflows/certify.yml"


def test_nightly_hosted_read_only_jobs() -> None:
    path = ROOT / ".github/workflows/nightly.yml"
    assert path.is_file()
    data = _load(path)
    assert data["permissions"] == {}
    assert set(data["jobs"]) == {"evaluate", "verdict", "certify"}
    assert "runs-on" not in data["jobs"]["certify"]
    assert "steps" not in data["jobs"]["certify"]
    for job in data["jobs"].values():
        if "steps" not in job:
            continue
        assert job["runs-on"] == "ubuntu-24.04"
        assert job["permissions"] == {"contents": "read"}
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")


def test_nightly_signing_boundary() -> None:
    jobs = _load(ROOT / ".github/workflows/nightly.yml")["jobs"]
    for name in ("evaluate", "verdict"):
        assert jobs[name]["permissions"] == {"contents": "read"}
    caller = jobs["certify"]
    assert caller["uses"] == "$/.github/workflows/certify.yml"
    assert caller["needs"] == "evaluate"
    assert caller["if"] == "github.ref == 'refs/heads/main'"
    assert caller["with"] == {"series": "nightly", "artifact": "nightly-evaluation"}
    assert caller["permissions"] == {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
        "pages": "write",
    }


def test_nightly_artifact_contract() -> None:
    jobs = _load(ROOT / ".github/workflows/nightly.yml")["jobs"]
    uploads = [
        step["with"]
        for step in jobs["evaluate"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    assert uploads[0]["name"] == "nightly-evaluation"
    assert uploads[0]["retention-days"] == 30
    assert uploads[0]["path"].splitlines() == [
        "out/reference.json",
        "out/candidate.json",
        "out/reference_commit.txt",
        "out/candidate_commit.txt",
        "out/platform.txt",
        "out/evaluated_at.txt",
        "out/cpu_flags.txt",
        "out/runner_image.txt",
    ]
    downloads = [
        step["with"]
        for step in jobs["verdict"]["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert downloads == [{"name": "nightly-evaluation", "path": "out/"}]


# Workflows whose torch results are compared across runs (with the committed baseline). They pin
# the hosted image: a new OS brings new system libraries (libm) that can flip near-miss episodes.
PINNED_IMAGE = "ubuntu-24.04"
NUMERIC_WORKFLOWS = ("pr-gate.yml", "baseline.yml", "nightly.yml")


@pytest.mark.parametrize("name", NUMERIC_WORKFLOWS)
def test_numeric_workflows_pin_the_runner_image(name: str) -> None:
    for job in _load(ROOT / ".github" / "workflows" / name)["jobs"].values():
        if "uses" in job:
            continue
        assert job["runs-on"] == PINNED_IMAGE, (
            f"{name} must run on {PINNED_IMAGE}; move images only with a baseline comparison"
        )


def test_history_evaluate_job_pins_the_runner_image() -> None:
    job = _load(ROOT / ".github" / "workflows" / "history.yml")["jobs"]["evaluate"]
    assert job["runs-on"] == PINNED_IMAGE


def test_readme_workflow() -> None:
    data = _load(ROOT / ".github/workflows/readme.yml")
    assert data["permissions"] == {}
    assert set(data["jobs"]) == {"linux", "windows"}
    assert data["jobs"]["linux"]["runs-on"] == PINNED_IMAGE
    assert data["jobs"]["windows"]["runs-on"] == "windows-2025"
    for job in data["jobs"].values():
        assert job["permissions"] == {"contents": "read"}
        setup = [
            step for step in job["steps"] if step.get("uses", "").startswith("astral-sh/setup-uv@")
        ]
        assert len(setup) == 1
        assert setup[0]["with"]["enable-cache"] is False
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")


def test_degraded_policy_is_demo_only() -> None:
    import json

    name = "demo-degraded.json"
    policy = json.loads((ROOT / "robots/pusht/policies" / name).read_text(encoding="utf-8"))
    assert "DEMO ONLY" in policy["note"]
    for path in WORKFLOWS:
        assert name not in path.read_text(encoding="utf-8"), str(path)
    for path in (ROOT / "piperobot").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            assert name not in path.read_text(encoding="utf-8"), str(path)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_runner_context_is_not_used_in_workflow_or_job_env(path: Path) -> None:
    """`runner.*` exists only inside steps; at job level it makes the workflow file invalid."""
    data = _load(path)
    scopes = [data.get("env", {}), *(job.get("env", {}) for job in data["jobs"].values())]
    for env in scopes:
        for value in env.values():
            assert "runner." not in str(value), f"{path.name}: runner context in an env block"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_write_permissions_never_on_self_hosted(path: Path) -> None:
    data = _load(path)
    for job in data["jobs"].values():
        permissions = job.get("permissions", data.get("permissions", {}))
        writes = permissions == "write-all" or (
            isinstance(permissions, dict) and "write" in permissions.values()
        )
        if writes:
            assert "self-hosted" not in _labels(job)


def test_so101_gate_trust_boundary() -> None:
    """The report write token is safe only while this workflow stays push/dispatch-only."""
    data = _load(ROOT / ".github/workflows/so101-gate.yml")
    triggers = data.get("on", data.get(True))
    assert isinstance(triggers, dict)
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert not {"pull_request", "pull_request_target", "workflow_run", "issue_comment"} & set(
        triggers
    )
    assert data["permissions"] == {}
    jobs = data["jobs"]
    assert jobs["evaluate"]["permissions"] == {"contents": "read"}
    assert jobs["report"]["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert jobs["report"]["runs-on"] == "ubuntu-24.04"
    assert jobs["report"]["needs"] == "evaluate"
    uploads = [
        s["with"]["name"]
        for s in jobs["evaluate"]["steps"]
        if s.get("uses", "").startswith("actions/upload-artifact@")
    ]
    downloads = [
        s["with"]["name"]
        for s in jobs["report"]["steps"]
        if s.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert uploads == downloads == ["so101-gate"]
    for job in jobs.values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")


def test_gpu_smoke_excludes_isaaclab() -> None:
    data = _load(ROOT / ".github/workflows/gpu-smoke.yml")
    triggers = data.get("on", data.get(True))
    assert isinstance(triggers, dict)
    paths = triggers["push"]["paths"]
    assert paths.index("!piperobot/adapters/isaaclab/**") > paths.index("piperobot/**")


def test_so101_platform_guard_and_baseline_artifact() -> None:
    report = _load(ROOT / ".github/workflows/so101-gate.yml")["jobs"]["report"]
    script = next(
        step["run"] for step in report["steps"] if step.get("name") == "Verdict and PR comments"
    )
    assert script.index("piperobot.adapters.isaaclab.baseline check") < script.index(
        "piperobot.reports.paired_comment"
    )
    upload = next(
        step for step in report["steps"] if step.get("with", {}).get("name") == "so101-baseline"
    )
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["retention-days"] == 30
    assert "inputs.mode == 'baseline'" in upload["if"]


def test_so101_missing_baseline_fails_closed_once_main_has_one() -> None:
    """A branch that drops the baseline must not get a green 'no baseline yet'."""
    report = _load(ROOT / ".github/workflows/so101-gate.yml")["jobs"]["report"]
    script = next(
        step["run"] for step in report["steps"] if step.get("name") == "Verdict and PR comments"
    )
    lookup = script.index("contents/$file?ref=main")
    green = script.index("no baseline committed yet")
    assert lookup < green
    missing_here = script.index("exists on main but is missing here; restore it")
    lookup_failed = script.index("::error::could not check main for a baseline")
    assert lookup < missing_here < green
    assert lookup < lookup_failed < green
    assert "HTTP 404" in script[lookup:green]


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("piperobot/results.py", "piperobot/**/*.py", True),
        ("piperobot/stats/paired.py", "piperobot/*.py", False),
    ],
)
def test_push_path_matching(path: str, pattern: str, expected: bool) -> None:
    assert gate_script.matches(path, pattern) is expected


def _in_repo_imports(entry_points: set[Path]) -> set[Path]:
    pending = list(entry_points)
    visited: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        relative = path.relative_to(ROOT)
        package = ".".join(relative.parts[:-1])
        modules: list[str] = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = importlib.util.resolve_name("." * node.level + module, package)
                modules.append(module)
                modules.extend(f"{module}.{alias.name}" for alias in node.names)
        for module in modules:
            parts = module.split(".")
            if parts[0] != "piperobot":
                continue
            for index in range(1, len(parts) + 1):
                base = ROOT.joinpath(*parts[:index])
                for candidate in (base.with_suffix(".py"), base / "__init__.py"):
                    if candidate.is_file() and candidate not in visited:
                        pending.append(candidate)
    return visited


def test_so101_push_paths_cover_dependencies() -> None:
    data = _load(ROOT / ".github/workflows/so101-gate.yml")
    triggers = data.get("on", data.get(True))
    assert isinstance(triggers, dict)
    patterns = gate_script.PATHS
    dependencies = _in_repo_imports(
        {
            ROOT / path
            for path in (
                "piperobot/adapters/isaaclab/evaluate.py",
                "piperobot/adapters/isaaclab/baseline.py",
                "piperobot/reports/paired_comment.py",
                "piperobot/reports/sticky_comment.py",
                "robots/so101/tools/prepare_caches.py",
            )
        }
    )
    env = data["jobs"]["evaluate"]["env"]
    dependencies.update(ROOT / env[key] for key in ("TASK", "POLICY"))
    import json

    for key in ("TASK", "POLICY"):
        manifest = ROOT / env[key]
        module = json.loads(manifest.read_text(encoding="utf-8"))["module"]
        dependencies.add(manifest.parent / module)
    dependencies.update(
        ROOT / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            ".github/workflows/so101-gate.yml",
            ".github/scripts/so101_gate.py",
        )
    )
    for path in dependencies:
        name = path.relative_to(ROOT).as_posix()
        assert any(gate_script.matches(name, pattern) for pattern in patterns), name
    assert {"pyproject.toml", "uv.lock"} <= set(patterns)


def test_so101_concurrency_and_shared_seeds() -> None:
    path = ROOT / ".github/workflows/so101-gate.yml"
    data = _load(path)
    assert "inputs.mode" in data["concurrency"]["group"]
    assert data["concurrency"]["cancel-in-progress"] == (
        "${{ inputs.mode != 'baseline' && github.ref != 'refs/heads/main' }}"
    )
    assert data["env"]["SEEDS"] == "100000-100099"
    assert path.read_text(encoding="utf-8").count("100000-100099") == 1


def test_so101_scripted_gate_configuration() -> None:
    path = ROOT / ".github/workflows/so101-gate.yml"
    assert "demo-replay" not in path.read_text(encoding="utf-8")
    data = _load(path)
    assert data["env"]["BASELINE"] == "robots/so101/baselines/scripted-pick-place"
    evaluate = data["jobs"]["evaluate"]
    env = evaluate["env"]
    assert env["TASK"] == "robots/so101/envs/vials_to_rack_task_randomized.json"
    assert env["POLICY"] == "robots/so101/policies/scripted_pick_place.json"
    assert env["MAX_WORKERS"] == "2"
    assert env["VRAM_PER_WORKER_MB"] == "4352"
    assert env["COMMIT_PER_WORKER_MB"] == "8448"
    assert "MIN_FREE_VRAM_MB" not in env
    assert evaluate["timeout-minutes"] == 130
    step = next(s for s in evaluate["steps"] if s.get("name", "").startswith("Evaluate ("))
    assert step["timeout-minutes"] == 120
    assert "--workers $env:WORKERS" in step["run"]
    preflight = next(s["run"] for s in evaluate["steps"] if s.get("name") == "GPU preflight")
    assert (
        "(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).FreeVirtualMemory / 1024"
    ) in preflight
    assert '"Free commit MiB: $freeCommit"' in preflight
    assert "$freeCommit -ge ($n * [int]$env:COMMIT_PER_WORKER_MB)" in preflight
    assert '"WORKERS=$workers" | Out-File -Append -Encoding utf8 $env:GITHUB_ENV' in preflight
    report = next(
        s for s in data["jobs"]["report"]["steps"] if s.get("name") == "Verdict and PR comments"
    )
    script = report["run"]
    # A failed or timed-out evaluate skips the report: a red check, never a verdict.
    assert data["jobs"]["report"]["needs"] == "evaluate"
    assert "if" not in data["jobs"]["report"]
    assert '--baseline "$BASELINE.json"' in script
    assert '--reference "$BASELINE-episodes.json"' in script
    assert 'for file in "$BASELINE.json" "$BASELINE-episodes.json";' in script
    assert "contents/$file?ref=main" in script
    assert '--note "$NOTE"' in script
    assert report["env"]["NOTE"] == (
        "Privileged-state scripted policy: measures the simulated pipeline and regressions, "
        "not a deployable policy (ADR 0034)."
    )


@pytest.mark.parametrize(
    ("free", "commit", "workers", "resource"),
    [
        (3583, 20000, 0, "VRAM"),
        (12000, 8447, 0, "commit (host memory)"),
        (3583, 8447, 0, "VRAM and commit"),
        (3584, 20000, 1, "VRAM"),
        (7167, 20000, 1, "VRAM"),
        (12000, 8448, 1, "commit (host memory)"),
        (12000, 16895, 1, "commit (host memory)"),
        (7167, 16895, 1, "VRAM and commit"),
        (7168, 16896, 2, ""),
        (12000, 20000, 2, ""),
    ],
)
def test_so101_worker_selection(
    tmp_path: Path, free: int, commit: int, workers: int, resource: str, powershell: str
) -> None:
    evaluate = _load(ROOT / ".github/workflows/so101-gate.yml")["jobs"]["evaluate"]
    script = next(s["run"] for s in evaluate["steps"] if s.get("name") == "GPU preflight")
    script = script[script.index("$workers = 0") :]
    environment = os.environ.copy()
    environment.update(
        MAX_WORKERS="2",
        VRAM_PER_WORKER_MB="3584",
        COMMIT_PER_WORKER_MB="8448",
        GITHUB_ENV=str(tmp_path / "env"),
        GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
    )
    result = subprocess.run(  # noqa: S603 - repository script and fixed test inputs
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$free = {free}\n$freeCommit = {commit}\n{script}",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if workers else 1), result.stdout + result.stderr
    if workers:
        assert (tmp_path / "env").read_text(encoding="utf-8-sig").strip() == f"WORKERS={workers}"
        assert (tmp_path / "summary").read_text(
            encoding="utf-8-sig"
        ).strip() == f"Workers: {workers}"
        assert ("::warning::" in result.stdout) == (workers == 1)
        if workers == 1:
            assert (
                f"::warning::running 1 worker(s), not enough free {resource} for 2: "
                "~50 min at the baseline rate, longer if episodes fail"
            ) in result.stdout
    else:
        assert "::error::" in result.stdout
        assert f"::error::not enough free {resource} for 1 worker;" in result.stdout
        assert not (tmp_path / "env").exists()


def test_so101_required_verdict_job() -> None:
    data = _load(ROOT / ".github/workflows/so101-gate.yml")
    triggers = data.get("on", data.get(True))
    assert isinstance(triggers, dict)
    assert triggers["push"] == {"branches": ["**"]}
    jobs = data["jobs"]
    final = jobs["so101-gate-verdict"]
    assert "name" not in final
    assert final["if"] == "always()"
    assert final["needs"] == ["changes", "evaluate", "report"]
    for job, action in ((final, "verdict"), (jobs["changes"], "changes")):
        assert job["runs-on"] == "ubuntu-24.04"
        assert job["permissions"] == {"contents": "read"}
        assert job["timeout-minutes"] == 5
        assert any(
            f".github/scripts/so101_gate.py {action}" in step.get("run", "")
            for step in job["steps"]
        )
    assert jobs["changes"]["steps"][0]["with"]["fetch-depth"] == 0
    assert jobs["evaluate"]["needs"] == "changes"
    for guard in (
        "github.repository == 'Andresdurango85/PipeRobot'",
        "github.actor != 'dependabot[bot]'",
        "needs.changes.outputs.relevant == 'true'",
        "needs.changes.outputs.dependabot != 'true'",
    ):
        assert guard in jobs["evaluate"]["if"]
    assert jobs["report"]["needs"] == "evaluate"
    assert "if" not in jobs["report"]
    assert {name for name, job in jobs.items() if "self-hosted" in _labels(job)} == {
        "evaluate",
        "video",
    }


def test_so101_optional_video_jobs() -> None:
    jobs = _load(ROOT / ".github/workflows/so101-gate.yml")["jobs"]
    assert not {"video-select", "video", "video-report"} & set(jobs["so101-gate-verdict"]["needs"])
    selection, video, report = jobs["video-select"], jobs["video"], jobs["video-report"]
    assert selection["runs-on"] == "ubuntu-24.04"
    assert selection["needs"] == ["changes", "evaluate"]
    assert selection["timeout-minutes"] == 5
    assert selection["permissions"] == {"contents": "read"}
    assert "secrets" not in selection
    assert "video-select" in video["needs"]
    assert "needs.video-select.outputs.seed_list != ''" in video["if"]
    assert "needs.video-select.result == 'success'" in video["if"]
    assert report["needs"] == ["changes", "evaluate", "report", "video-select", "video"]
    assert "needs.video-select.result == 'success'" in report["if"]
    for job in (selection, video):
        for guard in (
            "github.repository == 'Andresdurango85/PipeRobot'",
            "github.actor != 'dependabot[bot]'",
            "needs.changes.outputs.relevant == 'true'",
            "needs.changes.outputs.dependabot != 'true'",
        ):
            assert guard in job["if"]
    for job in (selection, video, report):
        assert "github.ref != 'refs/heads/main'" in job["if"]
        assert "inputs.mode == 'gate'" in job["if"]
        assert "github.event_name == 'push'" in job["if"]
    assert not {"GH_TOKEN", "GITHUB_TOKEN"} & set(selection.get("env", {}))
    for step in selection["steps"]:
        assert not {"GH_TOKEN", "GITHUB_TOKEN"} & set(step.get("env", {}))
        assert "secrets." not in str(step)
    assert {
        name
        for name in ("video-select", "video", "video-report")
        if jobs[name]["permissions"].get("pull-requests") == "write"
    } == {"video-report"}
    select_run = next(s["run"] for s in selection["steps"] if s.get("id") == "selection")
    record = next(s for s in video["steps"] if s.get("name") == "Record judged seeds")
    assert "^[0-9]+(,[0-9]+)*$" in select_run
    assert "^[0-9]+(,[0-9]+)*$" in record["run"]
    assert record["env"]["SEEDS_TO_RECORD"] == "${{ needs.video-select.outputs.seed_list }}"
    assert not any(s.get("name") == "Select video seeds" for s in video["steps"])
    for name in ("FFmpeg version", "Encode verified frames"):
        step = next(s for s in report["steps"] if s.get("name") == name)
        assert step["if"] == "needs.video-select.outputs.seed_list != ''"
    assert video["continue-on-error"] is True
    assert video["timeout-minutes"] == 15
    assert "inputs.mode == 'gate'" in video["if"]
    assert "github.event_name == 'push'" in video["if"]
    assert report["if"].startswith("always() && needs.evaluate.result == 'success'")
    assert video["env"]["COMMIT_FOR_VIDEO_MB"] == "19456"
    assert video["env"]["VRAM_FOR_VIDEO_MB"] == "5888"
    # The camera re-run must record the same policy and task the gate judged.
    evaluate = jobs["evaluate"]
    for key in ("TASK", "POLICY", "ISAACLAB_COMMIT", "OMNI_KIT_ACCEPT_EULA"):
        assert video["env"][key] == evaluate["env"][key]
    for job, retention in ((selection, 1), (video, 1), (report, 7)):
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")
            if step.get("uses", "").startswith("actions/upload-artifact@"):
                assert step["with"]["retention-days"] == retention
                assert "github.run_id" in step["with"]["name"]
                assert "github.run_attempt" in step["with"]["name"]
