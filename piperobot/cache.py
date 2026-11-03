"""The one cache root for evaluator inputs; CI sets it explicitly."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def cache_root(
    environ: Mapping[str, str] | None = None,
    os_name: str | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else home
    configured = env.get("PIPEROBOT_CACHE", "")
    if configured:
        # A literal path (CI sets it explicitly); only a leading ~ is expanded.
        if configured == "~" or configured.startswith(("~/", "~\\")):
            configured = str(user_home) + configured[1:]
        return Path(configured).resolve()
    if (os.name if os_name is None else os_name) == "nt":
        base = Path(env.get("LOCALAPPDATA") or user_home / "AppData" / "Local")
    else:
        base = Path(env.get("XDG_CACHE_HOME") or user_home / ".cache")
    return (base / "piperobot").expanduser().resolve()
