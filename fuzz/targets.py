"""Portable untrusted-input targets; unexpected exceptions must escape."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from piperobot.adapters.isaaclab.specs import read_object
from piperobot.reports.certificate import CertificateInputError, _bundle_types
from piperobot.reports.history import HistoryError, HistoryRecord, load_history
from piperobot.reports.video_manifest import VideoInputError, build_manifest
from piperobot.results import ResultsError, load_results

# Close each write before loaders open the reusable file, including on Windows.
_DIRECTORY = TemporaryDirectory(prefix="piperobot-fuzz-")
_PATH = Path(_DIRECTORY.name) / "input.json"


def results(data: bytes) -> None:
    _PATH.write_bytes(data)
    with contextlib.suppress(ResultsError):
        load_results(_PATH)


def history(data: bytes) -> None:
    _PATH.write_bytes(data)
    with contextlib.suppress(HistoryError):
        load_history(_PATH)


def bundle(data: bytes) -> None:
    _PATH.write_bytes(data)
    with contextlib.suppress(CertificateInputError):
        _bundle_types(_PATH)


def task_spec(data: bytes) -> None:
    _PATH.write_bytes(data)
    with contextlib.suppress(ResultsError):
        read_object(_PATH)


def history_record(data: bytes) -> None:
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return
    if isinstance(value, dict):
        with contextlib.suppress(HistoryError):
            HistoryRecord.from_dict(value)


def video_manifest(data: bytes) -> None:
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return
    if not isinstance(value, dict) or not {"selection", "judged", "recorded"} <= value.keys():
        return
    with contextlib.suppress(VideoInputError):
        build_manifest(value["selection"], value["judged"], value["recorded"])
