from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from piperobot import platform_info


def test_cpuinfo(tmp_path: Path) -> None:
    path = tmp_path / "cpuinfo"
    path.write_text("model name : AMD EPYC 7763\nmodel name : ignored\n", encoding="utf-8")
    assert (
        platform_info.describe_platform(cpuinfo_path=path, count=lambda: 4)
        == "AMD EPYC 7763, 4 CPUs"
    )


@pytest.mark.parametrize(
    ("processor", "machine", "expected"),
    [("processor", "machine", "processor"), ("", "machine", "machine"), ("", "", "unknown CPU")],
)
def test_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, processor: str, machine: str, expected: str
) -> None:
    monkeypatch.setattr(platform, "processor", lambda: processor)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert (
        platform_info.describe_platform(cpuinfo_path=tmp_path / "missing", count=lambda: 2)
        == f"{expected}, 2 CPUs"
    )


def test_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {1, 3}, raising=False)
    assert platform_info._cpu_count() == 2
    monkeypatch.delattr(os, "sched_getaffinity")
    monkeypatch.setattr(os, "cpu_count", lambda: 6)
    assert platform_info._cpu_count() == 6


def test_module() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "piperobot.platform_info"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(result.stdout.splitlines()) == 1
    assert result.stdout.strip().endswith(" CPUs")


def test_unknown_count(tmp_path: Path) -> None:
    path = tmp_path / "cpuinfo"
    path.write_text("model name : CPU model\n", encoding="utf-8")
    assert (
        platform_info.describe_platform(cpuinfo_path=path, count=lambda: None)
        == "CPU model, unknown CPUs"
    )
