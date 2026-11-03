"""Exercise the history appender against local repositories only."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from piperobot.results import EpisodeResult, EvalResults, save_results

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
GIT = shutil.which("git")
if BASH is None or GIT is None:
    pytest.skip("bash and git must be on PATH", allow_module_level=True)


def _run(
    args: list[str], env: dict[str, str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed executables, local test repositories, no shell.
        args, env=env, text=True, capture_output=True, check=check, timeout=30
    )


@pytest.fixture
def local_repo(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    assert BASH is not None
    assert GIT is not None
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("GIT_", "GITHUB_", "HISTORY_")):
            del env[key]
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="History test",
        GIT_AUTHOR_EMAIL="history@example.org",
        GIT_COMMITTER_NAME="History test",
        GIT_COMMITTER_EMAIL="history@example.org",
        PROJECT_DIR=ROOT.as_posix(),
        HISTORY_PYTHON=shlex.quote(Path(sys.executable).as_posix()),
    )
    # Windows may expose only the WSL launcher, without a usable bash installation.
    try:
        probe = _run([BASH, "-c", 'command -v git && test -d "$PROJECT_DIR"'], env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"bash cannot run in this sandbox: {exc}")
    if probe.returncode:
        pytest.skip(f"bash/git cannot access the workspace: {probe.stderr.strip()}")
    remote = tmp_path / "remote.git"
    env["HISTORY_REMOTE"] = remote.as_posix()
    _run([GIT, "init", "--bare", str(remote)], env)
    seed = tmp_path / "seed"
    _run([GIT, "init", str(seed)], env)
    (seed / "history.json").write_text("[]\n", encoding="utf-8")
    _run([GIT, "-C", str(seed), "add", "history.json"], env)
    _run([GIT, "-C", str(seed), "-c", "commit.gpgsign=false", "commit", "-m", "Seed history"], env)
    _run([GIT, "-C", str(seed), "push", str(remote), "HEAD:refs/heads/history"], env)
    results = tmp_path / "results.json"
    save_results(EvalResults("mock", "mock", (EpisodeResult(1, True),)), results)
    return remote, env, results


def _append(
    env: dict[str, str], results: Path, run_id: int = 1
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return _run(
        [
            BASH,
            (ROOT / ".github/scripts/append_history.sh").as_posix(),
            "--results",
            results.as_posix(),
            "--baseline-file",
            "robots/mock/baseline.json",
            "--commit",
            "a" * 40,
            "--commit-date",
            "2026-11-03T10:00:00Z",
            "--run-url",
            f"https://example.org/runs/{run_id}",
            "--run-id",
            str(run_id),
            "--run-attempt",
            "1",
            "--platform",
            "Test CPU, 2 CPUs",
            "--evaluated-at",
            "2026-11-03T10:01:00Z",
        ],
        env,
        check=False,
    )


def _git(remote: Path, env: dict[str, str], *args: str) -> str:
    assert GIT is not None
    return _run([GIT, "--git-dir", str(remote), *args], env).stdout.strip()


def test_append_and_duplicate(local_repo: tuple[Path, dict[str, str], Path]) -> None:
    remote, env, results = local_repo
    first = _append(env, results)
    assert first.returncode == 0, first.stdout + first.stderr
    records = json.loads(_git(remote, env, "show", "history:history.json"))
    assert len(records) == 1
    assert records[0]["run_id"] == 1
    head = _git(remote, env, "rev-parse", "history")
    assert _git(remote, env, "log", "-1", "--format=%s", "history") == (
        f"History: {'a' * 40} (run 1.1)"
    )
    second = _append(env, results)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "already present" in second.stdout
    assert _git(remote, env, "rev-parse", "history") == head


def test_two_runs_preserve_prefix(local_repo: tuple[Path, dict[str, str], Path]) -> None:
    remote, env, results = local_repo
    assert _append(env, results).returncode == 0
    first = json.loads(_git(remote, env, "show", "history:history.json"))
    assert _append(env, results, 2).returncode == 0
    second = json.loads(_git(remote, env, "show", "history:history.json"))
    assert len(second) == 2
    assert second[:1] == first
    assert [record["run_id"] for record in second] == [1, 2]


def test_rejected_push_retries(local_repo: tuple[Path, dict[str, str], Path]) -> None:
    remote, env, results = local_repo
    hook = remote / "hooks/pre-receive"
    hook.write_text(
        "#!/bin/sh\nif [ ! -f rejected-once ]; then\n  touch rejected-once\n  exit 1\nfi\nexit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    result = _append(env, results)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (remote / "rejected-once").exists()
    assert len(json.loads(_git(remote, env, "show", "history:history.json"))) == 1
    assert _git(remote, env, "rev-list", "--count", "history") == "2"


def test_missing_branch(local_repo: tuple[Path, dict[str, str], Path]) -> None:
    remote, env, results = local_repo
    _git(remote, env, "update-ref", "-d", "refs/heads/history")
    result = _append(env, results)
    assert result.returncode == 1
    assert "branch must be created first" in result.stderr
    assert _git(remote, env, "for-each-ref", "--format=%(refname)") == ""


def test_bad_results_stops_without_push(local_repo: tuple[Path, dict[str, str], Path]) -> None:
    remote, env, results = local_repo
    head = _git(remote, env, "rev-parse", "history")
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\ntouch push-attempted\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    results.write_text("{", encoding="utf-8")
    result = _append(env, results)
    assert result.returncode == 2, result.stdout + result.stderr
    assert _git(remote, env, "rev-parse", "history") == head
    assert not (remote / "push-attempted").exists()
