"""Report surviving mutants against the reviewed equivalent-mutant list."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def parse_results(text: str) -> dict[str, str]:
    """Extract mutant names and statuses from mutmut's human-readable results."""
    return dict(re.findall(r"^\s*(piperobot\.\S+):\s*([^\r\n]+?)\s*$", text, re.MULTILINE))


def load_equivalents(path: Path) -> dict[str, str]:
    """Read exact mutmut names, requiring a reason for every accepted equivalent."""
    equivalents: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, reason = line.partition("#")
        name, reason = name.strip(), reason.strip()
        if not re.fullmatch(r"piperobot\.\S+", name) or not separator or not reason:
            raise ValueError(f"{path}:{number}: expected 'piperobot.<exact name> # reason'")
        if name in equivalents:
            raise ValueError(f"{path}:{number}: {name} is listed twice")
        equivalents[name] = reason
    return equivalents


def classify(
    survivors: Iterable[str], equivalents: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Return accepted survivors, new survivors, and stale accepted names."""
    names = set(survivors)
    return (
        sorted(names & equivalents.keys()),
        sorted(names - equivalents.keys()),
        sorted(equivalents.keys() - names),
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed mutmut commands, no shell.
        command, capture_output=True, text=True, encoding="utf-8", check=False
    )


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def main(argv: Sequence[str] | None = None, *, runner: Runner = _run) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "equivalents", nargs="?", type=Path, default=Path("tests/mutation_equivalents.txt")
    )
    args = parser.parse_args(argv)
    try:
        equivalents = load_equivalents(args.equivalents)
    except (OSError, ValueError) as error:
        print(f"::error::Invalid equivalent-mutant list: {error}")
        return 2

    stats_path = Path("mutants/mutmut-cicd-stats.json")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write("## Mutation testing\n\n")
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            killed, total = stats["killed"], stats["total"]
            score = f"{killed / total:.1%}" if total else "N/A"
            summary.write(f"Killed / total: **{killed} / {total} ({score})**\n\n")
        else:
            summary.write("Statistics unavailable; inspect the mutation run logs.\n\n")
        result = runner(["uv", "run", "mutmut", "results"])
        if result.returncode:
            summary.write("Could not list survivors; inspect the results step.\n")
        results = parse_results(result.stdout)
        accepted, new, stale = classify(
            [name for name, status in results.items() if status == "survived"], equivalents
        )
        summary.write("| Survivor | Status | Reason |\n| --- | --- | --- |\n")
        for name in new:
            summary.write(f"| {name} | NEW — review | |\n")
            print(f"::warning::NEW surviving mutant — review: {name}")
        for name in accepted:
            summary.write(f"| {name} | equivalent (accepted) | {_cell(equivalents[name])} |\n")
        summary.write("\n")
        if stale:
            summary.write("### Stale equivalents (killed or renamed)\n\n")
            for name in stale:
                summary.write(f"- {name}: stale (killed or renamed)\n")
                print(f"::notice::Stale equivalent (killed or renamed): {name}")
            summary.write("\n")
        # NEW and stale are non-blocking for now; see docs/knowledge/testing.md.
        for name in new + accepted:
            diff = runner(["uv", "run", "mutmut", "show", name])
            summary.write(f"### {name}\n\n```diff\n{diff.stdout}{diff.stderr}\n```\n\n")
            # Also in the log: step summaries cannot be read through the API.
            print(f"::group::{name}\n{diff.stdout}{diff.stderr}\n::endgroup::")
        untested = [name for name, status in results.items() if status == "no tests"]
        if untested:
            modules = sorted({name.split(".x")[0] for name in untested})
            summary.write(f"**{len(untested)} mutants reached by no test** in {modules}.\n")
            print(f"::error::{len(untested)} mutants have no tests: {', '.join(modules)}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
