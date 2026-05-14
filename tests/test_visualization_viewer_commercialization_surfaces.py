from __future__ import annotations

from implementation.phase1.visualization_viewer.commercialization_surfaces import (
    build_commercialization_depth_surface,
    build_commercial_workflow_breadth_surface,
)


def test_commercialization_depth_surface_builds_bounded_p0_p1_rows() -> None:
    payload = {
        "summary": {
            "material_constitutive_summary_line": "PASS | concrete_damage=yes | matrix=expanded",
            "element_material_breadth_summary_line": "PASS | materials=8 | contact=yes",
            "load_combination_editor_commercialization_summary_line": "PASS | kds_match=ok | cases=42",
            "load_combination_editor_commercialization_pass": True,
            "reference_regression_summary_line": "PASS | cases=12 | metrics=4",
            "reference_regression_report_path": "release/reference_regression.json",
            "advanced_ssi_summary_line": "PASS | ssi=yes | links=4",
            "general_fe_contact_matrix_summary_line": "PASS | support_depth=3 | ssi=yes",
            "wind_tunnel_raw_mapping_ready": False,
        }
    }

    surface = build_commercialization_depth_surface(payload)

    assert surface["available"] is True
    assert surface["count"] == 5
    assert surface["ready_count"] == 4
    assert surface["open_count"] == 1
    assert surface["headline"] == "P0 3/3 | P1 1/2 | total 4/5"
    assert [row["id"] for row in surface["rows"]] == [
        "material_depth",
        "load_depth",
        "reference_regression",
        "advanced_ssi_depth",
        "wind_depth",
    ]
    assert surface["rows"][0]["status"] == "PASS"
    assert surface["rows"][-1]["status"] == "CHECK"


def test_commercial_workflow_breadth_surface_formats_ready_rows_and_artifact() -> None:
    payload = {
        "summary": {
            "construction_stage_ready": True,
            "construction_stage_history_snapshot_count": 7,
            "construction_stage_max_differential_shortening_mm": 12.34567,
            "rail_tunnel_ready": True,
            "rail_tunnel_serviceability_status": "ok",
            "rail_tunnel_maintenance_priority": "low",
            "rail_tunnel_recommended_action_count": 2,
            "design_redesign_loop_ready": True,
            "design_report_traceability_ratio": 0.875,
            "design_report_ng_member_count": 3,
            "section_optimizer_suggestion_count": 5,
            "section_optimizer_strengthen_count": 4,
            "section_optimizer_reduce_count": 1,
            "governing_clause_count": 9,
        },
        "checks": {"pass": True},
        "summary_line": "workflow breadth PASS",
    }

    surface = build_commercial_workflow_breadth_surface(
        payload,
        artifact_href="release/commercial_workflow_breadth_report.json",
        artifact_path="implementation/phase1/release/commercial_workflow_breadth_report.json",
    )

    assert surface["available"] is True
    assert surface["status_label"] == "commercial_workflow_breadth_ready"
    assert surface["ready_count"] == 3
    assert surface["open_count"] == 0
    assert surface["headline"] == "ready 3/3 | checks=PASS | clauses=9"
    assert surface["design_report_traceability_ratio_label"] == "87.5%"
    assert surface["construction_stage_max_differential_shortening_label"] == "12.346 mm"
    assert surface["artifact_name"] == "commercial_workflow_breadth_report.json"
    assert surface["rows"][2]["evidence_excerpt"] == (
        "optimizer suggestions=5 | strengthen=4 | reduce=1 | governing clauses=9"
    )
