from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from strict_json import StrictJSONError, strict_json_loads  # noqa: E402


@pytest.mark.parametrize(
    ("payload", "marker"),
    [
        ('{"case_id":"a","case_id":"b"}', "duplicate_json_key:case_id"),
        ('{"value":NaN}', "non_finite_json_number:NaN"),
        ('{"value":Infinity}', "non_finite_json_number:Infinity"),
        ('{"value":-Infinity}', "non_finite_json_number:-Infinity"),
        ('{"value":1e9999}', "non_finite_json_number:1e9999"),
    ],
)
def test_strict_json_rejects_ambiguous_or_nonfinite_first_boundary(
    payload: str, marker: str
) -> None:
    with pytest.raises(StrictJSONError, match=marker):
        strict_json_loads(payload)


def test_strict_json_accepts_finite_unique_json() -> None:
    assert strict_json_loads('{"case_id":"a","value":1.25}') == {
        "case_id": "a",
        "value": 1.25,
    }
