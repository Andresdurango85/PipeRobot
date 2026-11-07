"""Smoke-test fuzz targets without the Linux-only Atheris runtime."""

from __future__ import annotations

import importlib.util
import runpy
import sys
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parent.parent
FUZZ = ROOT / "fuzz"
SPEC = importlib.util.spec_from_file_location("fuzz_targets", FUZZ / "targets.py")
assert SPEC is not None
assert SPEC.loader is not None
TARGETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TARGETS)
NAMES = ("results", "history", "history_record", "bundle", "task_spec", "video_manifest")
HOSTILE = [
    b"[" * 5000 + b"]" * 5000,
    b"[" * 100_000 + b"]" * 100_000,
    b"\xff\xfe{",
    b"NaN",
    b"Infinity",
    b"null",
    b"[]",
    b"0",
    b'"text"',
    b"{",
    b"{}",
    b'{"episodes":[{"seed":0,"success":NaN}]}',
    b'{"episodes":[{"seed":3.7,"success":true}]}',
]


@pytest.mark.parametrize("name", NAMES)
def test_target_corpus_and_hostile_inputs(name: str) -> None:
    target = cast(Callable[[bytes], None], getattr(TARGETS, name))
    for path in sorted((FUZZ / "corpus" / name).iterdir()):
        target(path.read_bytes())
    for data in HOSTILE:
        target(data)


def test_harnesses_and_corpus() -> None:
    for path in FUZZ.glob("fuzz_*.py"):
        assert "import atheris" in path.read_text(encoding="utf-8").splitlines()
        corpus = FUZZ / "corpus" / path.stem.removeprefix("fuzz_")
        assert any(p.is_file() for p in corpus.iterdir())
    assert sum(p.stat().st_size for p in (FUZZ / "corpus").rglob("*") if p.is_file()) < 65536


@pytest.mark.parametrize(
    ("name", "entry", "error"),
    [
        ("results", "load_results", TARGETS.ResultsError),
        ("history", "load_history", TARGETS.HistoryError),
        ("bundle", "_bundle_types", TARGETS.CertificateInputError),
        ("task_spec", "read_object", TARGETS.ResultsError),
        ("history_record", "from_dict", TARGETS.HistoryError),
        ("video_manifest", "build_manifest", TARGETS.VideoInputError),
    ],
)
def test_target_exception_contract(
    name: str, entry: str, error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = cast(Callable[[bytes], None], getattr(TARGETS, name))
    owner = TARGETS.HistoryRecord if name == "history_record" else TARGETS
    payload = (FUZZ / "corpus" / name / "valid.json").read_bytes()

    def documented(*args: object, **kwargs: object) -> None:
        raise error("invalid input")

    def unexpected(*args: object, **kwargs: object) -> None:
        raise RuntimeError("real crash")

    monkeypatch.setattr(owner, entry, documented)
    target(payload)
    monkeypatch.setattr(owner, entry, unexpected)
    with pytest.raises(RuntimeError, match="real crash"):
        target(payload)


def test_history_fields_without_atheris(monkeypatch: pytest.MonkeyPatch) -> None:
    # Run the @given property on Windows; only import instrumentation needs a stand-in.
    stand_in = ModuleType("atheris")
    stand_in.instrument_imports = nullcontext  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "atheris", stand_in)
    # The harness adds the repo root for execution as a script; isolate that global change.
    monkeypatch.setattr(sys, "path", sys.path.copy())
    namespace = runpy.run_path(str(FUZZ / "fuzz_history_fields.py"))
    record = namespace["_RECORD"]
    assert TARGETS.HistoryRecord.from_dict(record).schema == 2
    check = cast(Callable[[], None], namespace["check"])
    check()
    assert callable(namespace["check"].hypothesis.fuzz_one_input)
