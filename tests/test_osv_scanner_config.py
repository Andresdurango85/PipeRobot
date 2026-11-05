"""Keep OSV-Scanner ignores valid and in sync with the accepted advisories in ADR 0012."""

from __future__ import annotations

import re
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_PATH = "docs/decisions/0012-dependency-vulnerability-triage.md"


def test_osv_scanner_config_schema() -> None:
    with (ROOT / "osv-scanner.toml").open("rb") as file:
        config = tomllib.load(file)

    assert set(config) == {"IgnoredVulns"}
    entries = config["IgnoredVulns"]
    assert isinstance(entries, list)
    for entry in entries:
        assert set(entry) == {"id", "ignoreUntil", "reason"}
        assert type(entry["ignoreUntil"]) is date
        assert ADR_PATH in entry["reason"]


def test_osv_scanner_ids_match_adr() -> None:
    with (ROOT / "osv-scanner.toml").open("rb") as file:
        config = tomllib.load(file)

    ids = [entry["id"] for entry in config["IgnoredVulns"]]
    adr_text = (ROOT / ADR_PATH).read_text(encoding="utf-8")
    accepted_ids = set(re.findall(r"GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}", adr_text))

    assert set(ids) == accepted_ids
    assert len(ids) == len(set(ids))
