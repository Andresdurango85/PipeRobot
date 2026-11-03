"""Execute explicitly marked README commands with timed, expected verdicts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Step:
    command: str
    expected_exit: int
    line: int


def extract(markdown: str) -> list[Step]:
    """Read marked fenced blocks, retaining one-based command line numbers."""
    lines = markdown.splitlines()
    steps: list[Step] = []
    index = 0
    while index < len(lines):
        text = lines[index].strip()
        marker_line = index + 1
        if not text.startswith("<!-- readme-test"):
            # Skip documentation fences, including marker examples inside them.
            fence = re.fullmatch(r"(`{3,}|~{3,}).*", text)
            if fence:
                opening = fence[1]
                index += 1
                while index < len(lines) and not re.fullmatch(
                    re.escape(opening[0]) + "{" + str(len(opening)) + r",}\s*",
                    lines[index].strip(),
                ):
                    index += 1
            index += 1
            continue
        marker = re.fullmatch(r"<!-- readme-test(?:: exit (-?\d+))? -->", text)
        if marker is None:
            raise ValueError(f"line {marker_line}: malformed readme-test marker")
        expected = int(marker[1] or 0)
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        fence = (
            re.fullmatch(r"(`{3,}|~{3,}).*", lines[index].strip()) if index < len(lines) else None
        )
        if fence is None:
            raise ValueError(f"line {marker_line}: marker must be followed by a fence")
        opening = fence[1]
        fence_line = index + 1
        index += 1
        block: list[Step] = []
        while index < len(lines):
            command = lines[index].strip()
            if re.fullmatch(re.escape(opening[0]) + "{" + str(len(opening)) + r",}\s*", command):
                break
            if command.endswith("\\"):
                raise ValueError(f"line {index + 1}: continuations are not portable")
            if command:
                block.append(Step(command, expected, index + 1))
            index += 1
        else:
            raise ValueError(f"line {fence_line}: unclosed fence")
        if expected != 0 and len(block) != 1:
            raise ValueError(f"line {marker_line}: non-zero exit requires exactly one command")
        steps.extend(block)
        index += 1
    return steps


def run(readme: Path, shell: str, summary: Path, budget_minutes: float) -> int:
    """Stream commands and append timings, including partial runs on failure."""
    steps = extract(readme.read_text(encoding="utf-8"))
    executable = shutil.which("bash" if shell == "bash" else "pwsh")
    if executable is None and shell == "powershell":
        executable = shutil.which("powershell")
    if executable is None:
        raise ValueError(f"shell not found: {shell}")
    flags = ["-c"] if shell == "bash" else ["-NoProfile", "-NonInteractive", "-Command"]
    rows = ["\n| Step | Expected exit | Actual exit | Seconds |", "| --- | --- | --- | --- |"]
    started = time.perf_counter()
    failed = False
    try:
        for number, step in enumerate(steps, 1):
            print(f"Step {number}, README line {step.line}: {step.command}", flush=True)
            before = time.perf_counter()
            result = subprocess.run(  # noqa: S603 -- explicitly marked repo commands, no shell=True.
                [executable, *flags, step.command], cwd=readme.resolve().parent, check=False
            )
            elapsed = time.perf_counter() - before
            rows.append(
                f"| {number} (line {step.line}) | {step.expected_exit} | "
                f"{result.returncode} | {elapsed:.2f} |"
            )
            if result.returncode != step.expected_exit:
                print(
                    f"Step {number}, README line {step.line}: "
                    f"expected exit {step.expected_exit}, got {result.returncode}",
                    file=sys.stderr,
                )
                failed = True
                break
    finally:
        total = time.perf_counter() - started
        with summary.open("a", encoding="utf-8") as output:
            output.write(
                "\n".join(rows)
                + f"\n\nTotal: {total:.2f} seconds (budget: {budget_minutes:g} minutes).\n"
            )
    if total > budget_minutes * 60:
        print("README execution exceeded its time budget", file=sys.stderr)
        failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    extraction = commands.add_parser("extract")
    extraction.add_argument("readme", type=Path)
    execution = commands.add_parser("run")
    execution.add_argument("readme", type=Path)
    execution.add_argument("--shell", choices=("bash", "powershell"), required=True)
    execution.add_argument("--summary", type=Path, required=True)
    execution.add_argument("--budget-minutes", type=float, default=30)
    args = parser.parse_args()
    try:
        if args.action == "extract":
            print(
                json.dumps(
                    [asdict(step) for step in extract(args.readme.read_text(encoding="utf-8"))]
                )
            )
            return 0
        return run(args.readme, args.shell, args.summary, args.budget_minutes)
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
