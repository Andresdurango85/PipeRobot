"""Load the stored baseline (`stats/baseline.json`): the counts the candidate is compared against.

The baseline is stored as counts, not as a rate, so its own uncertainty enters the comparison
(ADR 0003). Fields: ``successes`` and ``trials`` (required), plus free-form provenance such as
``policy``, ``evaluator``, ``updated`` and ``how``.
"""

from __future__ import annotations

import json
from pathlib import Path

from stats.gate import SuccessCount

DEFAULT_BASELINE = Path(__file__).with_name("baseline.json")


class BaselineError(ValueError):
    """The baseline file is missing or malformed."""


def load_baseline(path: Path = DEFAULT_BASELINE) -> SuccessCount:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SuccessCount(int(data["successes"]), int(data["trials"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BaselineError(f"invalid baseline {path}: {exc}") from exc
