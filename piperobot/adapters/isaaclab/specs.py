"""Portable task/policy specifications; no simulation dependencies."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast, runtime_checkable

from piperobot.cache import cache_root
from piperobot.results import ResultsError


def reject_constant(value: str) -> object:
    raise ValueError(f"Non-finite JSON number: {value}")


def read_object(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except (OSError, ValueError) as exc:
        raise ResultsError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResultsError(f"{path}: expected a JSON object")
    return cast(dict[str, object], data)


def object_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ResultsError(f"{label}: expected an object")
    return cast(dict[str, object], value)


def required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ResultsError(f"{key}: expected a nonempty string")
    return value


def expand_variables(value: str) -> str:
    environ = dict(os.environ)
    environ["PIPEROBOT_CACHE"] = str(cache_root())
    pattern = r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z_0-9]*)"
    if os.name == "nt":
        pattern += r"|%([^%]+)%"
    return re.sub(
        pattern,
        lambda match: environ.get(next(g for g in match.groups() if g is not None), match[0]),
        value,
    )


def resolve_path(value: str, parent: Path) -> Path:
    path = Path(expand_variables(value))
    return (parent / path).resolve() if not path.is_absolute() else path.resolve()


@dataclass(frozen=True)
class TaskSpec:
    name: str
    module: Path
    layout: str
    options: dict[str, object]
    timeout_s: float = 300

    @classmethod
    def load(cls, path: Path) -> TaskSpec:
        data = read_object(path)
        timeout = data.get("timeout_s", 300)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ResultsError("timeout_s must be finite and positive")
        return cls(
            required_string(data, "name"),
            resolve_path(required_string(data, "module"), path.resolve().parent),
            required_string(data, "layout"),
            object_dict(data.get("options", {}), "options"),
            float(timeout),
        )


@dataclass(frozen=True)
class PolicySpec:
    name: str
    module: Path
    factory: str
    options: dict[str, object]
    files: tuple[dict[str, str], ...] = ()
    prepare: str = ""
    repo_id: str | None = None
    revision: str | None = None

    @classmethod
    def load(cls, path: Path) -> PolicySpec:
        data = read_object(path)
        prepare = str(data.get("prepare", "Create the pinned file before evaluation."))
        entries = data.get("files", [])
        if not isinstance(entries, list):
            raise ResultsError("files must be a list")
        files = []
        for entry in entries:
            item = object_dict(entry, "file")
            file = resolve_path(required_string(item, "path"), path.resolve().parent)
            sha256 = required_string(item, "sha256")
            try:
                with file.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
            except OSError as exc:
                raise ResultsError(f"Missing policy file {file}. Prepare it: {prepare}") from exc
            if actual != sha256:
                raise ResultsError(f"SHA256 mismatch for {file}. Recreate it: {prepare}")
            files.append({"path": str(file), "sha256": sha256})
        options = object_dict(data.get("options", {}), "options").copy()
        # Expand path variables in factory options as well as integrity-checked files.
        options = {k: expand_variables(v) if isinstance(v, str) else v for k, v in options.items()}
        return cls(
            required_string(data, "name"),
            resolve_path(required_string(data, "module"), path.resolve().parent),
            required_string(data, "factory"),
            options,
            tuple(files),
            prepare,
            str(data["repo_id"]) if "repo_id" in data else None,
            str(data["revision"]) if "revision" in data else None,
        )


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ResultsError(f"Cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


class Policy(Protocol):
    def reset(self, seed: int) -> None: ...

    def act(self, observation: Mapping[str, object]) -> Sequence[float]: ...


@runtime_checkable
class ReferenceEpisodes(Protocol):
    def reference_episode(self, seed: int) -> Mapping[str, object] | None: ...


@runtime_checkable
class UsesObjectState(Protocol):
    """Optional opt-in to privileged task object observations."""

    uses_object_state: bool
