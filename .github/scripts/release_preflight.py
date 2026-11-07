"""Fail-closed validation for annotated source releases and Sigstore envelopes."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Never


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def git(root: Path, *arguments: str) -> str:
    binary = shutil.which("git")
    if binary is None:
        raise ValueError("git not found")
    result = subprocess.run(  # noqa: S603 -- resolved git, explicit arguments, no shell.
        [binary, "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise ValueError(f"git {' '.join(arguments)} failed")
    return result.stdout


def check_tag(tag: str, main_ref: str, root: Path) -> None:
    if not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        raise ValueError("tag must match vX.Y.Z without leading zeros")
    ref = f"refs/tags/{tag}"
    if git(root, "cat-file", "-t", ref).strip() != "tag":
        raise ValueError("release tag must be annotated")
    commit = git(root, "rev-parse", f"{ref}^{{commit}}").strip()
    git(root, "merge-base", "--is-ancestor", commit, main_ref)
    project = tomllib.loads(git(root, "show", f"{commit}:pyproject.toml"))
    if project.get("project", {}).get("version") != tag[1:]:
        raise ValueError("tag and project version differ")
    if not git(root, "show", f"{commit}:docs/releases/{tag}.md").strip():
        raise ValueError("release notes are blank")


def reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_object(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if len(text.splitlines()) != 1:
        raise ValueError(f"{path}: expected exactly one JSON line")
    value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def envelope(bundle: Path) -> dict[str, Any]:
    value = read_object(bundle).get("dsseEnvelope")
    if not isinstance(value, dict):
        raise ValueError("bundle must contain a dsseEnvelope object")
    if not {"payload", "payloadType", "signatures"} <= value.keys():
        raise ValueError("envelope is missing required fields")
    if not isinstance(value["signatures"], list) or not value["signatures"]:
        raise ValueError("envelope signatures must be a non-empty list")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        tag = commands.add_parser("check-tag")
        tag.add_argument("--tag", required=True)
        tag.add_argument("--main-ref", default="origin/main")
        tag.add_argument("--repo-root", type=Path, default=Path("."))
        for name in ("envelope", "check-envelope"):
            command = commands.add_parser(name)
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument(
                "--output" if name == "envelope" else "--envelope", type=Path, required=True
            )
        args = parser.parse_args(argv)
        if args.command == "check-tag":
            check_tag(args.tag, args.main_ref, args.repo_root)
        else:
            value = envelope(args.bundle)
            if args.command == "envelope":
                args.output.write_text(
                    json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            elif read_object(args.envelope) != value:
                raise ValueError("envelope differs from bundle")
    except (OSError, ValueError, TypeError, AttributeError, RecursionError) as error:
        print("ERROR: " + " ".join(str(error).splitlines()), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
