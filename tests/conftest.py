"""Deterministic, database-free runs by default; opt into randomized local exploration."""

import os
from tempfile import TemporaryDirectory

from hypothesis import settings

# Hypothesis also caches constants and Unicode data independently of its example database.
_storage = TemporaryDirectory(prefix="piperobot-hypothesis-")
os.environ.setdefault("HYPOTHESIS_STORAGE_DIRECTORY", _storage.name)

settings.register_profile(
    "default", derandomize=True, database=None, deadline=None, print_blob=True
)
settings.register_profile(
    "explore", derandomize=False, max_examples=5000, database=None, deadline=None
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
