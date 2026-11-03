"""Opt-in verification of certificates published by the history workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from piperobot.reports.certificate import CertificateNotFound, verify
from piperobot.reports.history import HistoryRecord

SITE = "https://andresdurango85.github.io/PipeRobot"
pytestmark = pytest.mark.github


def _download(relative: str) -> bytes:
    # All URLs use our fixed HTTPS Pages origin and validated numeric run identities.
    with urlopen(f"{SITE}/{relative}", timeout=30) as response:  # noqa: S310
        contents: bytes = response.read()
        return contents


def test_published_certificate(tmp_path: Path) -> None:
    if shutil.which("gh") is None:
        pytest.skip("gh is not installed")
    records = [HistoryRecord.from_dict(item) for item in json.loads(_download("history.json"))]
    for record in reversed(records):
        identity = f"{record.run_id}.{record.run_attempt}"
        try:
            results_bytes = _download(f"results/{identity}.json")
            bundle_bytes = _download(f"bundles/{identity}.jsonl")
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        results, bundle = tmp_path / "results.json", tmp_path / "bundle.jsonl"
        results.write_bytes(results_bytes)
        bundle.write_bytes(bundle_bytes)
        assert verify(results, bundle=bundle).record == record
        altered = tmp_path / "altered.json"
        altered.write_bytes(results_bytes + b"\n ")
        with pytest.raises(CertificateNotFound):
            verify(altered, bundle=bundle)
        return
    pytest.skip("no signed history record has been published yet")
