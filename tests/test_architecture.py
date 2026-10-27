"""The generic gate core must not depend on robot- or task-specific code (ADR 0015)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = sorted([*ROOT.glob("stats/*.py"), *ROOT.glob("reports/*.py"), ROOT / "eval" / "results.py"])
FORBIDDEN = (
    "eval.mock_eval",
    "eval.dataset_stats",
    "envs",
    "policies",
    "lerobot",
    "isaaclab",
    "isaacsim",
    "omni",
    "torch",
)


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", CORE, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_core_module_has_no_specific_imports(path: Path) -> None:
    bad = {
        module
        for module in _imports(path)
        for forbidden in FORBIDDEN
        if module == forbidden or module.startswith(f"{forbidden}.")
    }

    assert bad == set()
