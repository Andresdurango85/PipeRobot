"""Detect gate-relevant changes and produce the required SO-101 verdict."""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

PATHS: tuple[str, ...] = (
    "robots/so101/policies/**",
    "robots/so101/envs/**",
    "robots/so101/baselines/**",
    "robots/so101/tools/prepare_caches.py",
    "piperobot/**",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/so101-gate.yml",
    ".github/scripts/so101_gate.py",
)


def matches(path: str, pattern: str) -> bool:
    """Match path components with ** spanning zero or more directories."""
    parts, patterns = path.split("/"), pattern.split("/")
    if patterns[0] == "**":
        return len(patterns) == 1 or any(
            matches("/".join(parts[index:]), "/".join(patterns[1:]))
            for index in range(len(parts) + 1)
        )
    return fnmatch.fnmatchcase(parts[0], patterns[0]) and (
        len(parts) == len(patterns) == 1
        or (
            len(parts) > 1
            and len(patterns) > 1
            and matches("/".join(parts[1:]), "/".join(patterns[1:]))
        )
    )


def is_relevant(files: Iterable[str]) -> bool:
    return any(matches(path, pattern) for path in files for pattern in PATHS)


def changed_files(
    *, ref: str, sha: str, before: str, git: Callable[[list[str]], str]
) -> list[str] | None:
    """Diff the whole branch, or the pushed range on main; fail closed."""
    try:
        if ref == "refs/heads/main":
            if not before or set(before) == {"0"}:
                return None
            base = before
        else:
            base = git(["merge-base", "origin/main", sha]).strip()
        return git(["diff", "--name-only", base, sha]).splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None


def verdict(
    *,
    event: str,
    mode: str,
    changes: str,
    relevant: str,
    dependabot: str,
    evaluate: str,
    report: str,
) -> tuple[bool, str]:
    if changes != "success":
        return False, f"the changes job did not succeed ({changes}); no verdict"
    if event == "workflow_dispatch" and mode == "baseline":
        return True, "baseline mode: measures a baseline, not a PR check"
    if relevant != "true":
        return True, "no gate-relevant change; the SO-101 gate did not need to run"
    if dependabot == "true":
        return False, (
            "Dependabot changed gate-relevant files; the runner never runs untrusted code. "
            "Andrés reviews it and pushes a commit to the branch to trigger the gate, or bypasses."
        )
    if evaluate == "success" and report == "success":
        return True, "the SO-101 gate ran and passed"
    return False, f"the SO-101 gate did not pass (evaluate: {evaluate}, report: {report})"


def _git(arguments: list[str]) -> str:
    # Fixed git commands from PATH on a hosted runner, no shell.
    command = ["git", *arguments]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout  # noqa: S603


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("changes", "verdict"))
    args = parser.parse_args(argv)
    keys = (
        ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_SHA", "BEFORE", "ACTOR", "GITHUB_OUTPUT")
        if args.action == "changes"
        else ("EVENT", "MODE", "CHANGES", "RELEVANT", "DEPENDABOT", "EVALUATE", "REPORT")
    )
    try:
        env = {key: os.environ[key] for key in (*keys, "GITHUB_STEP_SUMMARY")}
    except KeyError as error:
        print(f"Missing environment variable: {error.args[0]}", file=sys.stderr)
        return 2
    if args.action == "changes":
        files = None
        if env["GITHUB_EVENT_NAME"] != "workflow_dispatch":
            try:
                if env["GITHUB_REF"] != "refs/heads/main":
                    _git(["fetch", "--no-tags", "origin", "main"])
                files = changed_files(
                    ref=env["GITHUB_REF"], sha=env["GITHUB_SHA"], before=env["BEFORE"], git=_git
                )
            except (OSError, subprocess.CalledProcessError):
                files = None
        relevant = files is None or is_relevant(files)
        with Path(env["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"relevant={str(relevant).lower()}\n")
            output.write(f"dependabot={str(env['ACTOR'] == 'dependabot[bot]').lower()}\n")
        matching = [path for path in files or [] if is_relevant([path])]
        message = (
            "gate-relevant changes: " + ", ".join(matching[:20])
            if matching
            else (
                "manual run or changes unknown; treating as gate-relevant"
                if relevant
                else "no gate-relevant change"
            )
        )
        passed = True
    else:
        passed, message = verdict(**{key.lower(): env[key] for key in keys})
    with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(message + "\n")
    if not passed:
        print(f"::error::{message}")
    return int(not passed)


if __name__ == "__main__":
    sys.exit(main())
