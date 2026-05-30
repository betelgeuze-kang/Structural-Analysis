"""Tests for optimization member alignment contract."""

from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.build_optimization_member_alignment import (
    build_member_alignment,
    enrich_changes_payload,
)


def _model_payload(*element_ids: str) -> dict:
    return {
        "model": {
            "elements": [{"id": element_id, "type": "BEAM", "node_ids": [1, 2]} for element_id in element_ids],
        }
    }


def test_build_member_alignment_detects_removed_and_merge() -> None:
    baseline = _model_payload("1", "2", "3")
    optimized = _model_payload("1", "3", "4")
    alignment = build_member_alignment(
        baseline_payload=baseline,
        optimized_payload=optimized,
        changes=[{"action_name": "group_merge", "group_id": "g1", "group_index": 0}],
    )
    assert alignment["removed_member_ids"] == ["2"]
    assert alignment["added_member_ids"] == ["4"]
    assert alignment["group_merge_count"] == 1


def test_enrich_changes_payload_writes_member_alignment(tmp_path: Path) -> None:
    changes_path = tmp_path / "changes.json"
    changes_path.write_text(
        json.dumps({"schema_version": "1.0", "changes": []}, indent=2),
        encoding="utf-8",
    )
    enriched = enrich_changes_payload(
        json.loads(changes_path.read_text(encoding="utf-8")),
        baseline_payload=_model_payload("a"),
        optimized_payload=_model_payload("b"),
    )
    assert enriched["contract_version"] == "1.1"
    assert enriched["member_alignment"]["removed_member_ids"] == ["a"]
    assert enriched["member_alignment"]["added_member_ids"] == ["b"]
