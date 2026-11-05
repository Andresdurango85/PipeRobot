"""Mutate one field of a valid schema-2 history record."""

import contextlib
import json
import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with atheris.instrument_imports():
    from hypothesis import given
    from hypothesis import strategies as st

    from piperobot.reports.history import HistoryError, HistoryRecord

_RECORD = json.loads((Path(__file__).parent / "corpus/history_record/valid.json").read_bytes())
_JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=30,
)


@given(field=st.sampled_from(sorted(_RECORD)), value=_JSON)
def check(field: str, value: object) -> None:
    record = {**_RECORD, field: value}
    with contextlib.suppress(HistoryError):
        HistoryRecord.from_dict(record)


if __name__ == "__main__":
    # Hypothesis exposes this runtime bridge on @given functions.
    atheris.Setup(sys.argv, check.hypothesis.fuzz_one_input)  # type: ignore[attr-defined]
    atheris.Fuzz()
