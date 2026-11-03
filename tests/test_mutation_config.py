"""Mutation testing must reach every test of piperobot.stats.

mutmut runs only the test files listed in ``[tool.mutmut]``: a stats module whose tests are
missing from that list has all its mutants reported as "no tests", and the job still looked green
until mutation.yml started failing on them. mutation.yml's pull_request paths must list the same
files, or editing those tests would not run mutation testing.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
IMPORTS_STATS = re.compile(r"^\s*(?:from|import)\s+piperobot\.stats\b", re.MULTILINE)


def _selection() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return set(data["tool"]["mutmut"]["pytest_add_cli_args_test_selection"])


def _stats_test_files() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").glob("test_*.py")
        if IMPORTS_STATS.search(path.read_text(encoding="utf-8"))
    }


def test_every_stats_test_file_is_in_the_mutmut_selection() -> None:
    missing = sorted(_stats_test_files() - _selection())
    assert not missing, (
        f"{missing} import piperobot.stats but are missing from [tool.mutmut] "
        "pytest_add_cli_args_test_selection in pyproject.toml; add them, or their mutants "
        "report 'no tests'."
    )


def test_mutation_workflow_runs_when_selected_tests_change() -> None:
    data: dict[str | bool, Any] = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "mutation.yml").read_text(encoding="utf-8")
    )
    # PyYAML follows YAML 1.1, where the bare key `on` loads as the boolean True.
    triggers: dict[str, Any] = data.get("on", data.get(True)) or {}
    paths = set(triggers["pull_request"]["paths"])
    missing = sorted(_selection() - paths)
    assert not missing, f"{missing} are mutation-tested but missing from mutation.yml's paths."


def test_equivalent_mutant_modules_exist() -> None:
    lines = (ROOT / "tests/mutation_equivalents.txt").read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name = line.partition("#")[0].strip()
        module, separator, _ = name.rpartition(".")
        assert separator, name
        assert module.startswith("piperobot.stats."), name
        path = ROOT.joinpath(*module.split(".")).with_suffix(".py")
        assert path.is_file(), f"Equivalent mutant {name} refers to a missing stats module: {path}"
