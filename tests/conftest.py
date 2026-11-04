"""Deterministic, database-free runs by default; opt into randomized local exploration."""

import os
import shutil
from tempfile import TemporaryDirectory

import pytest
from binaries import find_binary
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


@pytest.fixture
def powershell() -> str:
    return find_binary("pwsh", "powershell", env=os.environ, which=shutil.which)


@pytest.fixture
def git_binary() -> str:
    return find_binary("git", env=os.environ, which=shutil.which)


@pytest.fixture(autouse=True)
def _no_hook_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Inside a git hook (prek's pre-push runs pytest) git exports GIT_DIR for this checkout; a
    # test's git command that inherits it writes to the real repository (testing.md).
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX"):
        monkeypatch.delenv(key, raising=False)
