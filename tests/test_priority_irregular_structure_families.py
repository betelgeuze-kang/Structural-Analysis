from __future__ import annotations

import json
from pathlib import Path


def test_priority_irregular_structure_families_are_complete_and_ordered() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "open_data"
        / "irregular"
        / "priority_irregular_structure_families.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    families = payload["families"]

    assert len(families) == 20
    assert [family["priority"] for family in families] == list(range(1, 21))
    assert len({family["id"] for family in families}) == 20
