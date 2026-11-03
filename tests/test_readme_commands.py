"""The README marker contract and the committed reproduction path."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


class ReadmeStep(Protocol):
    command: str
    expected_exit: int
    line: int


class ReadmeCommands(Protocol):
    def extract(self, markdown: str) -> list[ReadmeStep]: ...

    def run(self, readme: Path, shell: str, summary: Path, budget_minutes: float) -> int: ...


spec = importlib.util.spec_from_file_location(
    "readme_commands", ROOT / ".github/scripts/readme_commands.py"
)
assert spec is not None
assert spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
commands = cast(ReadmeCommands, module)


def test_marked_blocks() -> None:
    steps = commands.extract(
        "```bash\nignored\n```\n<!-- readme-test -->\n\n```bash\nuv sync\n\nuv run pytest\n```\n"
        "<!-- readme-test: exit 1 -->\n~~~powershell\nuv run gate\n~~~\n"
    )
    assert [(step.command, step.expected_exit, step.line) for step in steps] == [
        ("uv sync", 0, 7),
        ("uv run pytest", 0, 9),
        ("uv run gate", 1, 13),
    ]


@pytest.mark.parametrize(
    ("markdown", "line", "message"),
    [
        ("\n<!-- readme-test -->\ntext", 2, "followed by a fence"),
        ("\n<!-- readme-test -->\n\n", 2, "followed by a fence"),
        ("\n<!-- readme-test: nope -->", 2, "malformed"),
        ("\n<!-- readme-test: exit one -->", 2, "malformed"),
        ("\n<!-- readme-test: exit 1 extra -->", 2, "malformed"),
        ("<!-- readme-test: exit 1 -->\n```\na\nb\n```", 1, "exactly one"),
        ("<!-- readme-test: exit 1 -->\n```\n```", 1, "exactly one"),
        ("<!-- readme-test -->\n```bash\na", 2, "unclosed fence"),
        ("<!-- readme-test -->\n```\na \\\n```", 3, "continuations"),
    ],
)
def test_invalid_blocks(markdown: str, line: int, message: str) -> None:
    with pytest.raises(ValueError, match=rf"line {line}: .*{message}"):
        commands.extract(markdown)


def test_other_expected_exit() -> None:
    assert commands.extract("<!-- readme-test: exit 7 -->\n```\na\n```")[0].expected_exit == 7


def test_unmarked_marker_example_is_ignored() -> None:
    assert commands.extract("```markdown\n<!-- readme-test -->\n```") == []


def test_real_readme() -> None:
    steps = commands.extract((ROOT / "README.md").read_text(encoding="utf-8"))
    assert len(steps) >= 6
    blocked = [step for step in steps if step.expected_exit == 1]
    assert len(blocked) == 1
    assert "piperobot.stats.gate" in blocked[0].command
    assert "--results out/block/results.json" in blocked[0].command
    assert all(step.command.startswith("uv ") for step in steps)
    assert all("\\" not in step.command for step in steps)


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize(
    ("actual", "budget", "expected", "count"),
    [(1, 30.0, 0, 2), (0, 30.0, 1, 1), (1, 0.0, 1, 2)],
)
def test_run_verdicts_and_timing(
    tmp_path: Path, shell: str, actual: int, budget: float, expected: int, count: int
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "<!-- readme-test: exit 1 -->\n```\nfirst\n```\n<!-- readme-test -->\n```\nsecond\n```\n",
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    summary.write_text("Existing summary\n", encoding="utf-8")
    with (
        patch.object(
            module.shutil, "which", side_effect=lambda name: None if name == "pwsh" else name
        ),
        patch.object(module.time, "perf_counter", side_effect=range(10)),
        patch.object(
            module.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], actual),
                subprocess.CompletedProcess([], 0),
            ],
        ) as execute,
    ):
        assert commands.run(readme, shell, summary, budget) == expected
    assert execute.call_count == count
    flags = ["-c"] if shell == "bash" else ["-NoProfile", "-NonInteractive", "-Command"]
    execute.assert_any_call([shell, *flags, "first"], cwd=tmp_path, check=False)
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("Existing summary\n")
    assert f"| 1 (line 3) | 1 | {actual} | 1.00 |" in text
    assert "Total:" in text
