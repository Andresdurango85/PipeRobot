"""Load robot scripts without making the robots tree a package."""

import importlib.util
from pathlib import Path
from types import ModuleType


def load(name: str, relative: str) -> ModuleType:
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
