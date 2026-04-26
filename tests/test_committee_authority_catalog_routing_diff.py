from implementation.phase1.generate_committee_review_package import (
    _authority_catalog_snapshot_payload,
    _build_authority_catalog_routing_diff,
)


def test_authority_catalog_routing_diff_detects_added_pairs() -> None:
    previous_catalog = {
        "tracks": {
            "sac": {
                "cases": [
                    {"case_id": "case_a", "real_source": True, "source_file_path": "a/SCBF16B.tcl"},
                ]
            }
        }
    }
    current_catalog = {
        "tracks": {
            "sac": {
                "cases": [
                    {"case_id": "case_a", "real_source": True, "source_file_path": "a/SCBF16B.tcl"},
                ]
            },
            "opensees": {
                "models": [
                    {"id": "SCBF16B_shell_beam_mix", "real_source": True, "model_path": "b/SCBF16B_shell_beam_mix.tcl"},
                ]
            },
        }
    }
    previous_snapshot = _authority_catalog_snapshot_payload(previous_catalog, [
        {
            "authority_track": "sac",
            "submodel_family": "SCBF16B",
            "review_story_zone": "S02/perimeter",
            "member_family": "slab",
            "owner": "legacy",
            "why": "old",
        }
    ])
    current_snapshot = _authority_catalog_snapshot_payload(current_catalog, [
        {
            "authority_track": "sac",
            "submodel_family": "SCBF16B",
            "review_story_zone": "S02/perimeter",
            "member_family": "slab",
            "owner": "legacy",
            "why": "old",
        },
        {
            "authority_track": "opensees",
            "submodel_family": "SCBF16B_shell_beam_mix",
            "review_story_zone": "S03/intermediate",
            "member_family": "beam",
            "owner": "legacy",
            "why": "new",
        },
    ])

    diff = _build_authority_catalog_routing_diff(previous_snapshot, current_snapshot)
    assert diff["baseline_seeded"] is False
    assert diff["change_count"] == 1
    assert diff["added_count"] == 1
    assert diff["removed_count"] == 0
    assert diff["diff_rows"][0]["change_type"] == "added"
    assert diff["diff_rows"][0]["authority_track"] == "opensees"
