from __future__ import annotations

from implementation.phase1.section_optimizer import generate_section_suggestions


def _code_check_report_fixture() -> dict:
    return {
        "contract_pass": False,
        "summary": {
            "member_count": 5,
            "member_check_row_count": 10,
            "max_dcr": 1.24,
        },
        "rows": [
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "governing_component": "flexure",
                "governing_combination": "KDS_ULS_1",
                "max_dcr": 1.24,
            },
            {
                "member_id": "W1",
                "case_id": "CASE-W1",
                "member_type": "wall",
                "hazard_type": "seismic",
                "topology_type": "wall-frame",
                "governing_component": "boundary_element",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.12,
            },
            {
                "member_id": "S1",
                "case_id": "CASE-S1",
                "member_type": "slab",
                "hazard_type": "gravity",
                "topology_type": "wall-frame",
                "governing_component": "punching",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.18,
            },
            {
                "member_id": "C1",
                "case_id": "CASE-C1",
                "member_type": "column",
                "hazard_type": "wind",
                "topology_type": "outrigger",
                "governing_component": "axial_flexure",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 0.52,
            },
            {
                "member_id": "N1",
                "case_id": "CASE-N1",
                "member_type": "connection",
                "hazard_type": "seismic",
                "topology_type": "jointed-frame",
                "governing_component": "slip",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.08,
            },
        ],
        "member_check_rows": [
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "flexure",
                "clause": "KDS-RC-BEAM-FLEX-001",
                "dcr": 1.24,
            },
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "shear",
                "clause": "KDS-RC-BEAM-SHEAR-001",
                "dcr": 1.05,
            },
            {
                "member_id": "W1",
                "case_id": "CASE-W1",
                "member_type": "wall",
                "hazard_type": "seismic",
                "topology_type": "wall-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "boundary_element",
                "clause": "KDS-RC-WALL-BE-001",
                "dcr": 1.12,
            },
            {
                "member_id": "S1",
                "case_id": "CASE-S1",
                "member_type": "slab",
                "hazard_type": "gravity",
                "topology_type": "wall-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "punching",
                "clause": "KDS-RC-SLAB-PUNCH-001",
                "dcr": 1.18,
            },
            {
                "member_id": "C1",
                "case_id": "CASE-C1",
                "member_type": "column",
                "hazard_type": "wind",
                "topology_type": "outrigger",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "axial_flexure",
                "clause": "KDS-RC-COL-INT-001",
                "dcr": 0.52,
            },
            {
                "member_id": "N1",
                "case_id": "CASE-N1",
                "member_type": "connection",
                "hazard_type": "seismic",
                "topology_type": "jointed-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "slip",
                "clause": "KDS-RC-CONN-SLIP-001",
                "dcr": 1.08,
            },
        ],
    }


def test_section_optimizer_generates_strengthen_and_reduce_suggestions() -> None:
    payload = generate_section_suggestions(
        code_check_report=_code_check_report_fixture(),
        design_optimization_report={
            "accepted_head": [
                {"member_id": "C1", "action_name": "perimeter_frame_down", "viewer_row_url": "../viewer?member=C1"},
                {"member_id": "N1", "action_name": "connection_detailing_up", "viewer_row_url": "../viewer?member=N1"},
            ]
        },
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["governing_clause_traceability_pass"] is True
    assert payload["checks"]["action_family_supported_pass"] is True
    assert payload["summary"]["suggestion_count"] == 5
    assert payload["summary"]["strengthen_count"] == 4
    assert payload["summary"]["reduce_count"] == 1
    assert payload["summary"]["design_optimization_aligned_count"] == 2

    rows = payload["suggestion_rows"]
    assert rows[0]["member_id"] == "B1"
    assert rows[0]["action_name"] == "beam_section_up"
    assert rows[0]["action_family"] == "beam_section"
    assert rows[1]["member_id"] == "S1"
    assert rows[1]["action_name"] == "slab_thickness_up"

    reduce_row = next(row for row in rows if row["member_id"] == "C1")
    assert reduce_row["direction"] == "reduce"
    assert reduce_row["action_name"] == "perimeter_frame_down"
    assert reduce_row["design_optimization_aligned"] is True
    assert reduce_row["estimated_max_dcr_after"] > reduce_row["current_max_dcr"]

    conn_row = next(row for row in rows if row["member_id"] == "N1")
    assert conn_row["action_name"] == "connection_detailing_up"
    assert conn_row["design_optimization_aligned"] is True
    assert "families=" in payload["summary_line"]
