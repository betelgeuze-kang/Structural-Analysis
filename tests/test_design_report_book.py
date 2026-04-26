from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.design_report_book import (
    build_design_report_book,
    write_design_report_book_artifacts,
)
from implementation.phase1.section_optimizer import generate_section_suggestions
from tests.test_section_optimizer import _code_check_report_fixture


def test_design_report_book_assembles_clause_table_ng_grouping_and_suggestions(tmp_path: Path) -> None:
    code_check_report = _code_check_report_fixture()
    design_optimization_report = {
        "summary": {
            "accepted_count": 2,
            "cost_reduction_proxy": 184.25,
            "final_max_dcr": 0.98,
        },
        "accepted_head": [
            {
                "member_id": "C1",
                "member_type": "column",
                "action_name": "perimeter_frame_down",
                "action_family": "perimeter_frame",
                "governing_clause_label": "KDS-RC-COL-INT-001",
                "projected_cost_delta": -42.0,
                "max_dcr": 0.52,
                "viewer_row_url": "../viewer?member=C1",
            },
            {
                "member_id": "N1",
                "member_type": "connection",
                "action_name": "connection_detailing_up",
                "action_family": "connection_detailing",
                "governing_clause_label": "KDS-RC-CONN-SLIP-001",
                "projected_cost_delta": 15.0,
                "max_dcr": 1.08,
                "viewer_row_url": "../viewer?member=N1",
            },
        ],
    }
    optimizer_payload = generate_section_suggestions(
        code_check_report=code_check_report,
        design_optimization_report=design_optimization_report,
    )
    payload = build_design_report_book(
        code_check_report=code_check_report,
        design_optimization_report=design_optimization_report,
        design_change_rows=[
            {
                "group_id": "C1-group",
                "member_type": "column",
                "action_name": "perimeter_frame_down",
                "action_family": "perimeter_frame",
                "governing_clause": "KDS-RC-COL-INT-001",
                "cost_proxy_delta": -42.0,
                "max_dcr_after": 0.52,
            }
        ],
        section_optimizer_report=optimizer_payload,
        external_design_sheet_diff_report={
            "summary": {
                "changed_row_count": 2,
                "added_row_count": 1,
                "removed_row_count": 0,
                "key_field": "member_id",
                "max_numeric_delta": 0.18,
                "shared_column_count": 4,
            },
            "changed_rows": [
                {
                    "row_key": "B1",
                    "changed_columns": ["dcr", "remark"],
                    "max_numeric_delta": 0.18,
                }
            ],
        },
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["governing_clause_traceability_pass"] is True
    assert payload["summary"]["member_count"] == 5
    assert payload["summary"]["ng_member_count"] == 4
    assert payload["summary"]["governing_clause_traceability_ratio"] == 1.0
    assert payload["summary"]["suggestion_count"] == 5
    assert payload["summary"]["optimization_change_row_count"] == 2
    assert payload["summary"]["optimization_accepted_count"] == 2
    assert payload["summary"]["external_sheet_diff_changed_row_count"] == 2
    assert payload["governing_clause_rows"][0]["clause"] == "KDS-RC-BEAM-FLEX-001"
    assert payload["ng_group_rows"][0]["ng_count"] >= 1
    assert payload["member_family_rows"][0]["member_type"] == "beam"
    assert payload["section_suggestion_rows"][0]["member_id"] == "B1"
    assert payload["optimization_change_rows"][0]["member_id"] == "C1"
    assert payload["external_sheet_diff_rows"][0]["row_key"] == "B1"
    assert payload["summary_line"].startswith("Design report book: PASS")

    out_json = tmp_path / "design_report_book.json"
    out_md = tmp_path / "design_report_book.md"
    write_design_report_book_artifacts(payload, out_json=out_json, out_md=out_md)

    persisted = json.loads(out_json.read_text(encoding="utf-8"))
    assert persisted["summary"]["suggestion_count"] == 5
    markdown = out_md.read_text(encoding="utf-8")
    assert "## Governing Clause Table" in markdown
    assert "## Section Suggestions" in markdown
    assert "## External Sheet Diff" in markdown
    assert "KDS-RC-BEAM-FLEX-001" in markdown
