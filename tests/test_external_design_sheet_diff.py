from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.external_design_sheet_diff import build_external_design_sheet_diff


def _write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_external_design_sheet_diff_surfaces_changed_added_and_removed_rows(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    revised = tmp_path / "revised.csv"
    _write_csv(
        baseline,
        "member_id,axial_kN,remark\n"
        "B1,100,baseline\n"
        "C1,200,baseline\n"
        "W1,300,baseline\n",
    )
    _write_csv(
        revised,
        "member_id,axial_kN,remark\n"
        "B1,125,revised\n"
        "C1,200,baseline\n"
        "N1,90,new\n",
    )

    payload = build_external_design_sheet_diff(
        baseline_path=baseline,
        revised_path=revised,
        key_fields=("member_id",),
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["changed_row_count"] == 1
    assert payload["summary"]["added_row_count"] == 1
    assert payload["summary"]["removed_row_count"] == 1
    assert payload["summary"]["key_field"] == "member_id"
    assert payload["summary"]["max_numeric_delta"] == 25.0
    assert payload["changed_rows"][0]["row_key"] == "B1"
    assert payload["changed_rows"][0]["numeric_delta_columns"] == ["axial_kN"]
    assert "External design sheet diff: PASS" in payload["summary_line"]


def test_external_design_sheet_diff_reads_json_row_payloads(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    revised = tmp_path / "revised.json"
    baseline.write_text(json.dumps({"rows": [{"member_id": "B1", "dcr": 1.2}]}), encoding="utf-8")
    revised.write_text(json.dumps({"rows": [{"member_id": "B1", "dcr": 0.95}]}), encoding="utf-8")

    payload = build_external_design_sheet_diff(
        baseline_path=baseline,
        revised_path=revised,
        key_fields=("member_id",),
    )

    assert payload["summary"]["changed_row_count"] == 1
    assert payload["changed_rows"][0]["row_key"] == "B1"
    assert payload["summary"]["max_numeric_delta"] == 0.25
