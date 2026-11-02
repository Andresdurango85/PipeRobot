"""The generic gate core must not depend on robot- or framework-specific code (ADR 0015, ADR 0019).

Modules are discovered from the packages, not from file globs, so a moved or empty package fails
the test instead of skipping it. Every module must be assigned to exactly one layer.
"""

from __future__ import annotations

import ast
import importlib.util
import pkgutil
import sys
from pathlib import Path

import pytest

PACKAGES = ("piperobot",)


def _modules() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for package in PACKAGES:
        spec = importlib.util.find_spec(package)
        if spec is None or spec.origin is None or spec.submodule_search_locations is None:
            raise RuntimeError(f"package {package!r} is missing: update PACKAGES")
        found[package] = Path(spec.origin)
        for info in pkgutil.walk_packages(spec.submodule_search_locations, prefix=f"{package}."):
            module_spec = importlib.util.find_spec(info.name)
            if module_spec is None or module_spec.origin is None:
                raise RuntimeError(f"cannot locate module {info.name!r}")
            found[info.name] = Path(module_spec.origin)
    return found


MODULES = _modules()


def _layer(name: str) -> str:
    if name == "piperobot.adapters" or name.startswith("piperobot.adapters."):
        return "adapter"
    if name == "piperobot" or name.startswith("piperobot."):
        return "core"
    return "unassigned"


def _imports(name: str, path: Path) -> set[str]:
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: resolve it against this module's package
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                modules.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                modules.add(node.module)
    return modules


def _allowed_in_core(module: str) -> bool:
    top = module.split(".")[0]
    return top in sys.stdlib_module_names or top == "__future__" or _layer(module) == "core"


def test_every_layer_has_modules() -> None:
    layers = {_layer(name) for name in MODULES}

    assert {"core", "adapter"} <= layers


@pytest.mark.parametrize("name", sorted(MODULES))
def test_module_is_assigned_to_a_layer(name: str) -> None:
    # Every discovered module must belong to a layer (ADR 0019).
    assert _layer(name) != "unassigned"


@pytest.mark.parametrize("name", sorted(n for n in MODULES if _layer(n) == "core"))
def test_core_imports_only_stdlib_and_core(name: str) -> None:
    bad = {module for module in _imports(name, MODULES[name]) if not _allowed_in_core(module)}

    assert bad == set()


def test_relative_imports_are_resolved(tmp_path: Path) -> None:
    source = tmp_path / "mod.py"
    source.write_text("from . import x\nfrom .y import z\nfrom ..w import v\n", encoding="utf-8")

    assert _imports("a.b.mod", source) == {"a.b", "a.b.y", "a.w"}


def test_manual_adapter_imports_only_stdlib_and_core() -> None:
    # Any robot uses it as is, with no extra installed (ADR 0022).
    names = [n for n in MODULES if n.startswith("piperobot.adapters.manual")]
    bad = {m for n in names for m in _imports(n, MODULES[n]) if not _allowed_in_core(m)}

    assert names
    assert bad == set()


@pytest.mark.parametrize("name", sorted(n for n in MODULES if _layer(n) == "adapter"))
def test_adapters_do_not_import_robots(name: str) -> None:
    bad = {module for module in _imports(name, MODULES[name]) if module.split(".")[0] == "robots"}

    assert bad == set()
