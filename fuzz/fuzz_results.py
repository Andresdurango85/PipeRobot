"""Coverage-guided fuzzing of results."""

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with atheris.instrument_imports():
    from targets import results

if __name__ == "__main__":
    atheris.Setup(sys.argv, results)
    atheris.Fuzz()
