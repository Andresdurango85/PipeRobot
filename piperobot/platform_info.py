"""Identify CPUs consistently for the gate workflow and history.

PushT outcomes depend on the CPU (ADR 0016), so both must label platforms
identically: the first cpuinfo model name and the affinity-aware CPU count.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from pathlib import Path


def _cpu_count() -> int | None:
    affinity = getattr(os, "sched_getaffinity", None)
    return len(affinity(0)) if affinity is not None else os.cpu_count()


def describe_platform(
    *, cpuinfo_path: Path = Path("/proc/cpuinfo"), count: Callable[[], int | None] = _cpu_count
) -> str:
    """Return the CPU model and available logical CPUs; inputs are injectable."""
    model = ""
    try:
        for line in cpuinfo_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() == "model name":
                model = value.strip()
                break
    except OSError:
        pass
    model = model or platform.processor() or platform.machine() or "unknown CPU"
    cpus = count()
    return f"{model}, {cpus if cpus is not None else 'unknown'} CPUs"


if __name__ == "__main__":
    print(describe_platform())
