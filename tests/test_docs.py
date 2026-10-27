"""Checks on the project memory (ADR 0001): links resolve, ADRs are well formed and indexed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "docs" / "decisions"
KNOWLEDGE = ROOT / "docs" / "knowledge"
SKIP_DIRS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "node_modules"}
# Machine-specific and untracked by design.
SKIP_FILES = {"CLAUDE.local.md"}

ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_STATUS = re.compile(r"^- Status: (Proposed|Accepted|Deprecated|Superseded by \d{4})$", re.M)
ADR_DATE = re.compile(r"^- Date: \d{4}-\d{2}-\d{2}$", re.M)
ADR_SECTIONS = ["## Context", "## Decision", "## Alternatives considered", "## Consequences"]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCED_BLOCK = re.compile(r"^```.*?^```", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts) and path.name not in SKIP_FILES
    )


def _local_links(path: Path) -> list[str]:
    text = INLINE_CODE.sub("", FENCED_BLOCK.sub("", path.read_text(encoding="utf-8")))
    targets = (match.group(1) for match in LINK.finditer(text))
    return [t for t in targets if not t.startswith(("http://", "https://", "mailto:", "#"))]


def _adr_files() -> list[Path]:
    return sorted(p for p in DECISIONS.glob("*.md") if p.name != "README.md")


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(path: Path) -> None:
    broken = [
        target
        for target in _local_links(path)
        if not (path.parent / target.split("#", 1)[0]).exists()
    ]

    assert broken == [], f"broken links in {path.relative_to(ROOT)}"


def test_adr_numbers_are_unique_and_consecutive() -> None:
    names = [p.name for p in _adr_files()]
    bad_names = [name for name in names if not ADR_NAME.match(name)]
    numbers = [int(name[:4]) for name in names if ADR_NAME.match(name)]

    assert bad_names == [], "ADR files must be named NNNN-kebab-title.md"
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.name)
def test_adr_is_well_formed(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    assert text.splitlines()[0].startswith(f"# {path.name[:4]}. ")
    assert ADR_STATUS.search(text), "missing or invalid '- Status:' line"
    assert ADR_DATE.search(text), "missing or invalid '- Date: YYYY-MM-DD' line"
    positions = [text.find(f"\n{section}\n") for section in ADR_SECTIONS]
    assert -1 not in positions, f"ADRs need these sections: {ADR_SECTIONS}"
    assert positions == sorted(positions), "ADR sections are out of order"


def test_every_adr_is_in_the_index() -> None:
    indexed = set(_local_links(DECISIONS / "README.md"))

    assert {p.name for p in _adr_files()} - indexed == set()


def test_every_knowledge_file_is_in_the_index() -> None:
    indexed = set(_local_links(KNOWLEDGE / "README.md"))
    topics = {p.name for p in KNOWLEDGE.glob("*.md") if p.name != "README.md"}

    assert topics - indexed == set()


def test_status_has_last_updated_date() -> None:
    text = (ROOT / "docs" / "STATUS.md").read_text(encoding="utf-8")

    assert re.search(r"^Last updated: \d{4}-\d{2}-\d{2}", text, re.M)


def test_claude_md_imports_agents_md() -> None:
    first_line = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0]

    assert first_line == "@AGENTS.md"


def test_machine_specific_files_are_gitignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "CLAUDE.local.md" in ignored
