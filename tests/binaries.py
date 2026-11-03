"""Require external test binaries in CI while allowing local skips."""

from collections.abc import Callable, Mapping

import pytest


def find_binary(*names: str, env: Mapping[str, str], which: Callable[[str], str | None]) -> str:
    for name in names:
        path = which(name)
        if path is not None:
            return path
    message = f"none of {', '.join(names)} found on PATH"
    if env.get("CI", "").lower() == "true":
        pytest.fail(f"{message}; CI must run these tests")
    pytest.skip(message)
