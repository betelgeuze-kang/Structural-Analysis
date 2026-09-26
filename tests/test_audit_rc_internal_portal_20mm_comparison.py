from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_rc_internal_portal_20mm_comparison as audit
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.benchmark.rc_internal_portal_20mm_comparison import (
    prepare_case,
)


def _synthetic_response() -> dict:
    return {
        "epoch": 1,
        "step_index": 2,
        "material_point_count": 1,
        "checkpoint_hash": "sha256:checkpoint-reference",
        "parent_checkpoint_hash": "sha256:parent-reference",
        "load_factor": 2.0,
        "node_displacements": [{"node_id": "N4", "UX_m": -0.02}],
        "support_reactions": [{"node_id": "N1", "FX_N": 100.0}],
        "member_end_forces": [
            {
                "member_id": "left",
                "node_i": "N1",
                "node_j": "N3",
                "local_end_i": {"FX_N": 100.0},
            }
        ],
        "section_results": [
            {
                "member_id": "left",
                "axial_strain": 0.001,
                "section_state_hash": "sha256:section-reference",
            }
        ],
        "fiber_results": [
            {
                "fiber_id": "steel-top-layer",
                "stress_MPa": 100.0,
                "material_state": {
                    "plastic_strain": 0.001,
                    "state_hash": "sha256:fiber-reference",
                },
            }
        ],
        "accepted_section_states": [
            {
                "member_id": "left",
                "integration_point_states": [
                    {"axial_strain": 0.001, "state_hash": "sha256:section-reference"}
                ],
            }
        ],
    }


def test_existing_research_rule_reports_hash_differences_separately() -> None:
    reference = _synthetic_response()
    candidate = deepcopy(reference)
    candidate["checkpoint_hash"] = "sha256:checkpoint-candidate"
    candidate["parent_checkpoint_hash"] = "sha256:parent-candidate"
    candidate["fiber_results"][0]["material_state"]["state_hash"] = (
        "sha256:fiber-candidate"
    )
    candidate["section_results"][0]["section_state_hash"] = "sha256:section-candidate"
    candidate["node_displacements"][0]["UX_m"] += 1.0e-12
    result = audit._compare_projection(reference, candidate)
    assert result["diagnostic_response_match"] is True
    assert result["checkpoint_hash_exact"] is False
    assert result["parent_checkpoint_hash_exact"] is False
    assert result["nested_hash_identities"]["mismatched_fields"] >= 4
    assert (
        result["nested_hash_identities"]["excluded_from_numeric_tolerance_gate"] is True
    )


@pytest.mark.parametrize(
    ("group", "edit"),
    [
        ("support_reactions", lambda row: row[0].__setitem__("FX_N", 100.01)),
        (
            "member_end_forces",
            lambda row: row[0]["local_end_i"].__setitem__("FX_N", 100.01),
        ),
        (
            "fiber_results",
            lambda row: row[0]["material_state"].__setitem__("plastic_strain", 0.01),
        ),
        (
            "accepted_section_states",
            lambda row: row[0]["integration_point_states"][0].__setitem__(
                "axial_strain", 0.01
            ),
        ),
    ],
)
def test_physical_response_or_material_tamper_fails_diagnostic_group(
    group, edit
) -> None:
    reference = _synthetic_response()
    candidate = deepcopy(reference)
    edit(candidate[group])
    result = audit._compare_projection(reference, candidate)
    assert result["diagnostic_response_match"] is False
    assert result["groups"][group]["within_existing_research_tolerance"] is False


def test_missing_fiber_and_changed_member_identity_fail_closed() -> None:
    reference = _synthetic_response()
    candidate = deepcopy(reference)
    candidate["fiber_results"].clear()
    assert (
        audit._compare_projection(reference, candidate)["diagnostic_response_match"]
        is False
    )
    candidate = deepcopy(reference)
    candidate["member_end_forces"][0]["member_id"] = "other"
    comparison = audit._compare_projection(reference, candidate)
    assert comparison["diagnostic_response_match"] is False
    assert (
        comparison["groups"]["member_end_forces"][
            "structure_and_non_numeric_identity_match"
        ]
        is False
    )


def test_canonical_packet_byte_hash_rejects_tamper_and_duplicate_keys(tmp_path) -> None:
    path = tmp_path / "artifact.json"
    original = audit._canonical({"status": "complete", "work": 2})
    path.write_bytes(original)
    assert audit._read_verified(path, audit._sha(original))["work"] == 2
    path.write_bytes(original.replace(b"2", b"3"))
    with pytest.raises(audit.PortalResponseAuditError, match="byte hash"):
        audit._read_verified(path, audit._sha(original))
    duplicate = b'{"work":2,"work":3}'
    path.write_bytes(duplicate)
    with pytest.raises(audit.PortalResponseAuditError, match="duplicate JSON key"):
        audit._read_verified(path, audit._sha(duplicate))


def test_real_preload_projection_binds_member_section_and_fiber_states() -> None:
    case = prepare_case()
    genesis = initial_stateful_corotational_fiber_frame2d_checkpoint(case.problem)
    step = solve_stateful_corotational_fiber_frame2d_load_step(
        case.problem,
        genesis,
        target_load_factor=0.0,
        config=case.preload_config,
    )
    projection = audit._validated_projection(step.to_dict(), case)
    assert projection["material_point_count"] == 126
    assert len(projection["member_end_forces"]) == 3
    assert len(projection["section_results"]) == 9
    assert len(projection["fiber_results"]) == 126
    assert projection["member_end_forces"][0]["node_i"] == "N1"
    assert projection["member_end_forces"][0]["node_j"] == "N3"
    tampered = step.to_dict()
    tampered["trial_assembly"]["member_assemblies"][0]["element_response"][
        "fiber_beam_response"
    ]["section_responses"][0]["trial_state"]["fiber_states"][0]["tensile_damage"] = 0.5
    with pytest.raises(audit.PortalResponseAuditError, match="section trial state"):
        audit._validated_projection(tampered, case)
