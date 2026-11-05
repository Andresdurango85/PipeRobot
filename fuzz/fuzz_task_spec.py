"""Coverage-guided fuzzing of task_spec."""

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with atheris.instrument_imports():
    from targets import task_spec

if __name__ == "__main__":
    atheris.Setup(sys.argv, task_spec)
    atheris.Fuzz()
