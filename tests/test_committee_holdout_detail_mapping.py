from __future__ import annotations

from implementation.phase1.generate_committee_review_package import _build_residual_holdout_detail_rows


def test_holdout_detail_rows_include_story_zone_and_submodel_family() -> None:
    holdout_buckets = [
        {"id": "licensed_engineer_review_required", "label": "Licensed Engineer Review", "owner": "기술사"},
        {"id": "legacy_tool_cross_validation_required", "label": "Legacy Tool Cross-Validation", "owner": "기존툴+기술사"},
        {"id": "legal_authority_signoff_required", "label": "Legal Sign-Off", "owner": "기술사/기존 승인 workflow"},
    ]
    design_change_rows = [
        {"story_band": 2, "zone_label": "perimeter"},
        {"story_band": 2, "zone_label": "perimeter"},
        {"story_band": 4, "zone_label": "intermediate"},
    ]
    accepted_candidate_rows = [
        {"member_type": "slab"},
        {"member_type": "beam"},
        {"member_type": "slab"},
    ]
    authority_rows = [
        {"track": "SAC"},
        {"track": "SAC"},
        {"track": "NHERI"},
    ]
    authority_catalog = {
        "tracks": {
            "sac": {
                "cases": [
                    {"case_id": "SAC20_LA_holdout_01", "real_source": True, "source_file_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"},
                ]
            },
            "opensees": {
                "models": [
                    {"id": "SCBF16B_shell_beam_mix", "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"},
                ]
            },
        }
    }

    rows = _build_residual_holdout_detail_rows(
        holdout_buckets,
        design_change_rows,
        accepted_candidate_rows,
        authority_rows,
        authority_catalog,
    )
    axes = {row["detail_axis"] for row in rows}
    assert "review_story_zone" in axes
    assert "submodel_family" in axes
    review_row = next(row for row in rows if row["detail_axis"] == "review_story_zone")
    assert "S02/perimeter" in review_row["detail_value"]
    assert review_row["work_item_id"] == "RH-001"
    assert review_row["status"] == "open"
    assert review_row["sla_label"] == "72h"
    assert review_row["due_date"] == "assignment_plus_3_business_days"
    assert review_row["closure_evidence_required"] == "signed_engineer_review_packet"
    assert review_row["closure_evidence_status"] == "pending"
    submodel_row = next(row for row in rows if row["detail_axis"] == "submodel_family")
    assert "SCBF16B" in submodel_row["detail_value"]
    assert submodel_row["work_item_id"] == "RH-002"
    assert submodel_row["queue_status"] == "pending_cross_validation"
    assert submodel_row["closure_evidence_required"] == "legacy_tool_cross_validation_report"
