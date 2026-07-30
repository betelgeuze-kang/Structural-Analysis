from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api import nonlinear_frame as nonlinear_frame_api
from structural_analysis.api import nonlinear_frame_cli
from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    COROTATIONAL_PORTAL_PROFILE,
    FIXED_CHORD_SERIAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    validate_nonlinear_frame_manifest,
    validate_nonlinear_frame_result,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_corotational_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)


def _materials_and_sections() -> tuple[list[dict], list[dict]]:
    return (
        [
            {
                "id": "steel",
                "type": "bilinear_combined_hardening_steel",
                "elastic_modulus_mpa": 200_000.0,
                "yield_stress_mpa": 250.0,
                "isotropic_hardening_modulus_mpa": 3_000.0,
                "kinematic_hardening_modulus_mpa": 5_000.0,
                "yield_tolerance_mpa": 1.0e-10,
            },
            {
                "id": "concrete",
                "type": "asymmetric_concrete_damage",
                "elastic_modulus_mpa": 30_000.0,
                "tensile_strength_mpa": 3.0,
                "compressive_strength_mpa": 30.0,
                "tensile_softening_rate": 3_000.0,
                "compressive_softening_rate": 400.0,
                "history_tolerance": 1.0e-14,
            },
        ],
        [
            {
                "id": "RC1",
                "type": "rectangular_rc_fiber_section",
                "width_m": 0.4,
                "depth_m": 0.6,
                "cover_m": 0.05,
                "concrete_layer_count": 2,
                "top_bar_count": 4,
                "bottom_bar_count": 4,
                "bar_area_m2": 3.87e-4,
                "steel_material": "steel",
                "concrete_material": "concrete",
            }
        ],
    )


def _base_payload() -> dict:
    materials, sections = _materials_and_sections()
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [],
        "elements": [],
        "materials": materials,
        "sections": sections,
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"case_id": "unified-nonlinear-frame"},
    }


def _member_feature_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
            ],
            "elements": [
                {
                    "id": "released-beam",
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": ["N1", "N2"],
                    "section": "RC1",
                    "integration_order": 3,
                    "rigid_offsets_global_m": {
                        "i": [0.2, 0.0],
                        "j": [-0.2, 0.0],
                    },
                    "end_releases": {"i": [], "j": ["RZ"]},
                    "uniform_distributed_load_local": {
                        "basis": "initial_member_local",
                        "behavior": "dead",
                        "qx_kN_per_m": 0.0,
                        "qy_kN_per_m": -2.0,
                    },
                }
            ],
            "loads": [],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {"node": "N2", "dofs": ["RZ"]},
            ],
        }
    )
    return payload


def _fixed_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [3.0, 0.0, 0.0]},
            ],
            "elements": [
                {
                    "id": "M1",
                    "type": "stateful_rc_fiber_frame2d",
                    "nodes": ["N1", "N2"],
                    "section": "RC1",
                    "integration_order": 2,
                }
            ],
            "loads": [
                {
                    "node": "N2",
                    "components": {
                        "FX": 0.0,
                        "FY": -10.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [{"node": "N1", "dofs": ["UX", "UY", "RZ"]}],
        }
    )
    return payload


def _portal_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
                {"id": "N3", "coordinates": [0.0, 3.0, 0.0]},
                {"id": "N4", "coordinates": [4.0, 3.0, 0.0]},
            ],
            "elements": [
                {
                    "id": member_id,
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": list(nodes),
                    "section": "RC1",
                    "integration_order": 3,
                }
                for member_id, nodes in (
                    ("column-left", ("N1", "N3")),
                    ("column-right", ("N2", "N4")),
                    ("beam-top", ("N3", "N4")),
                )
            ],
            "loads": [
                {
                    "node": "N4",
                    "components": {
                        "FX": 20.0,
                        "FY": -50.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {"node": "N2", "dofs": ["UX", "UY", "RZ"]},
            ],
        }
    )
    return payload


def _branching_payload() -> dict:
    payload = _base_payload()
    payload.update(
        {
            "nodes": [
                {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                {"id": "N2", "coordinates": [4.0, 0.0, 0.0]},
                {"id": "N3", "coordinates": [0.0, 3.0, 0.0]},
                {"id": "N4", "coordinates": [4.0, 3.0, 0.0]},
                {"id": "N5", "coordinates": [2.0, 3.0, 0.0]},
                {"id": "N6", "coordinates": [2.0, 5.0, 0.0]},
            ],
            "elements": [
                {
                    "id": member_id,
                    "type": "stateful_corotational_rc_fiber_frame2d",
                    "nodes": list(nodes),
                    "section": "RC1",
                    "integration_order": 3,
                }
                for member_id, nodes in (
                    ("column-left", ("N1", "N3")),
                    ("column-right", ("N2", "N4")),
                    ("beam-left", ("N3", "N5")),
                    ("beam-right", ("N5", "N4")),
                    ("branch", ("N5", "N6")),
                )
            ],
            "loads": [
                {
                    "node": "N6",
                    "components": {
                        "FX": 5.0,
                        "FY": -10.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ],
            "supports": [
                {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
                {
                    "node": "N2",
                    "dofs": ["UX", "UY", "RZ"],
                    "prescribed_values": {"UX": 2.0e-4},
                },
            ],
        }
    )
    return payload


def _model(tmp_path: Path, payload: dict, name: str = "model.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return load_neutral_json(path)


def _assert_normalized_rows_close(left, right) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        assert left.keys() == right.keys()
        for key in left:
            _assert_normalized_rows_close(left[key], right[key])
        return
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        assert len(left) == len(right)
        for left_value, right_value in zip(left, right, strict=True):
            _assert_normalized_rows_close(left_value, right_value)
        return
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        np.testing.assert_allclose(left, right, rtol=1.0e-9, atol=1.0e-9)
        return
    assert left == right


def test_unified_api_preserves_fixed_chord_profile_and_normalizes_stress_to_pa(
    tmp_path: Path,
) -> None:
    result = analyze_nonlinear_frame(
        _model(tmp_path, _fixed_payload()),
        NonlinearFrameConfig(profile=FIXED_CHORD_SERIAL_PROFILE, load_steps=2),
    )
    report = validate_nonlinear_frame_result(result)

    assert report.contract_pass is True
    assert result.profile == FIXED_CHORD_SERIAL_PROFILE
    assert result.authority["reaction"] == "authoritative"
    assert result.fiber_results
    assert "stress_Pa" in result.fiber_results[0]
    assert "stress_MPa" not in result.fiber_results[0]
    assert result.checkpoint_artifact()


@pytest.fixture(scope="module")
def portal_result(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("unified-corotational-portal")
    model = _model(root, _portal_payload())
    result = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
    )
    return model, result


def test_corotational_profile_exposes_exact_normalized_engineering_results(
    portal_result,
) -> None:
    _, result = portal_result
    report = validate_nonlinear_frame_result(result)

    assert result.status == "ready"
    assert report.contract_pass is True
    assert report.exact_engineering_recovery is True
    assert report.exact_checkpoint_chain_replay is True
    assert report.external_level2_attached is False
    assert result.authority["reaction"] == "exact_bounded_candidate"
    assert result.authority["public_api"] == "developer_preview_candidate"
    assert len(result.node_displacements) == 4
    assert len(result.support_reactions) == 6
    assert len(result.member_end_forces) == 3
    assert len(result.section_results) == 9
    assert result.fiber_results
    assert all("stress_Pa" in row for row in result.fiber_results)
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.engineering_result_ir is not None
    assert result.engineering_result_ir["schema_version"] == (
        "corotational-fiber-frame2d-engineering-result-ir.v1"
    )
    assert result.engineering_result_ir["engineering_result_hash"] == (
        result.source_result_hash
    )
    assert (
        result.engineering_result_ir["engineering_result_hash"]
        == (result.contract_bindings["engineering_result_hash"])
    )
    chain = json.loads(result.checkpoint_artifact())
    assert chain["checkpoint_count"] == 5
    assert [row["epoch"] for row in chain["checkpoints"]] == [0, 1, 2, 3, 4]
    assert chain["root_state_hash"] == chain["checkpoints"][0]["state_hash"]
    assert chain["terminal_state_hash"] == chain["checkpoints"][-1]["state_hash"]
    assert result.checkpoint["complete_ancestry_included"] is True
    assert result.checkpoint["prefix_replay_required"] is True
    assert validate_nonlinear_frame_manifest(result.to_dict()) == result.to_dict()


def test_corotational_public_api_exposes_native_sparse_full_si_parity(
    portal_result,
) -> None:
    model, dense = portal_result
    sparse_config = NonlinearFrameConfig(
        profile=COROTATIONAL_PORTAL_PROFILE,
        load_steps=4,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
    )
    sparse = analyze_nonlinear_frame(model, sparse_config)

    assert dense.configuration["matrix_backend"] == VECTOR_MATRIX_BACKEND
    assert sparse.status == "ready"
    assert validate_nonlinear_frame_result(sparse).contract_pass is True
    assert sparse.configuration["matrix_backend"] == VECTOR_SPARSE_MATRIX_BACKEND
    assert sparse.configuration["stiffness_storage"] == "scipy_sparse_csr"
    assert sparse.metrics["sparse_backend_used"] is True
    assert sparse.metrics["native_sparse_assembly_used"] is True
    assert sparse.metrics["sparse_factorization_count"] > 0
    assert sparse.metrics["sparse_factorization_diagnostics_passed"] is True
    assert sparse.metrics["sparse_factorization_max_condition_number_1"] < 1.0e12
    assert sparse.metrics["sparse_factorization_max_backward_error"] <= 1.0e-12
    assert (
        len(sparse.metrics["sparse_factorization_diagnostic_hashes"])
        == sparse.metrics["sparse_factorization_count"]
    )
    assert str(sparse.metrics["sparse_factorization_policy_hash"]).startswith("sha256:")
    assert sparse.metrics["fallback_count"] == 0
    assert sparse.metrics["regularization_count"] == 0

    tampered = replace(
        sparse,
        metrics={
            **dict(sparse.metrics),
            "sparse_factorization_diagnostics_passed": False,
        },
        result_hash="sha256:" + "0" * 64,
    )
    tampered = replace(
        tampered,
        result_hash=nonlinear_frame_api.canonical_hash(
            nonlinear_frame_api._result_payload(tampered, include_hash=False)
        ),
    )
    with pytest.raises(ValueError, match="contract_pass differs"):
        validate_nonlinear_frame_result(tampered)

    _assert_normalized_rows_close(sparse.node_displacements, dense.node_displacements)
    _assert_normalized_rows_close(sparse.support_reactions, dense.support_reactions)
    _assert_normalized_rows_close(sparse.member_end_forces, dense.member_end_forces)
    _assert_normalized_rows_close(sparse.section_results, dense.section_results)
    _assert_normalized_rows_close(sparse.fiber_results, dense.fiber_results)

    replayed = analyze_nonlinear_frame(
        model,
        sparse_config,
        restart_checkpoint_chain=sparse.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.metrics["replayed_prefix_step_count"] == 4
    assert replayed.metrics["native_sparse_assembly_used"] is True
    assert replayed.node_displacements == sparse.node_displacements
    assert replayed.support_reactions == sparse.support_reactions
    assert replayed.member_end_forces == sparse.member_end_forces
    assert replayed.section_results == sparse.section_results
    assert replayed.fiber_results == sparse.fiber_results
    assert replayed.checkpoint_artifact() == sparse.checkpoint_artifact()


def test_rehashed_outer_result_cannot_hide_engineering_result_ir_tampering(
    portal_result,
) -> None:
    _, result = portal_result
    payload = result.to_dict()
    assert payload["engineering_result_ir"] is not None
    payload["engineering_result_ir"]["counts"]["member"] += 1
    body = dict(payload)
    body.pop("result_hash")
    payload["result_hash"] = nonlinear_frame_api.canonical_hash(body)

    with pytest.raises(
        ValueError,
        match="corotational_engineering_result_(schema_invalid|hash_mismatch)",
    ):
        validate_nonlinear_frame_manifest(payload)


def test_fixed_chord_profile_rejects_sparse_backend() -> None:
    with pytest.raises(ValueError, match="fixed-chord"):
        NonlinearFrameConfig(
            profile=FIXED_CHORD_SERIAL_PROFILE,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        )


def test_connected_frame_profile_supports_branching_prescribed_and_restart(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path, _branching_payload(), "branching.json")
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
    )
    result = analyze_nonlinear_frame(model, config)

    assert validate_nonlinear_frame_result(result).contract_pass is True
    assert result.compiler_profile == (
        "planar_connected_branching_frame_explicit_fiber_section.v1"
    )
    assert len(result.node_displacements) == 6
    assert len(result.member_end_forces) == 5
    assert len(result.support_reactions) == 6
    assert result.node_displacements[1]["UX_m"] == 2.0e-4
    assert result.metrics["solver_executed"] is True
    assert result.metrics["native_sparse_assembly_used"] is True
    assert result.metrics["sparse_factorization_diagnostics_passed"] is True
    assert result.configuration["equation_scaling"]["status"] == "available"
    assert result.metrics["terminal_physical_residual_trace_status"] == "available"
    assert (
        result.metrics["terminal_physical_residual_trace_hash"]
        == (result.contract_bindings["terminal_physical_residual_trace_hash"])
    )
    for key in (
        "model_ir_adapter_hash",
        "nonlinear_execution_topology_plan_hash",
        "dof_ordering_hash",
        "solver_coordinate_scaling_hash",
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "equation_order_hash",
    ):
        assert result.contract_bindings[key].startswith("sha256:")
    assert result.metrics["raw_translational_residual_linf_n"] >= 0.0
    assert result.metrics["raw_rotational_residual_linf_nm"] >= 0.0
    assert result.metrics["dimensionless_scaled_residual_linf"] >= 0.0

    replayed = analyze_nonlinear_frame(
        model,
        config,
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.metrics["replayed_prefix_step_count"] == 4
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions
    assert replayed.checkpoint_artifact() == result.checkpoint_artifact()
    assert replayed.contract_bindings == result.contract_bindings


def test_general_public_profile_executes_release_offset_and_distributed_load(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path, _member_feature_payload(), "member-features.json")
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        maximum_iterations=60,
    )
    result = analyze_nonlinear_frame(model, config)

    assert result.status == "ready"
    assert validate_nonlinear_frame_result(result).contract_pass is True
    assert result.unsupported_features == ()
    assert result.member_end_forces[0]["member_features"]["release_j_rz"] is True
    assert result.member_end_forces[0]["member_features"][
        "uniform_load_local_kn_per_m"
    ] == [0.0, -2.0]
    assert result.authority["member_features"] == "exact_bounded_candidate"
    assert result.engineering_result_ir is not None
    assert result.engineering_result_ir["authority_axes"]["member_features"] == (
        "exact_bounded_candidate"
    )
    assert abs(result.member_end_forces[0]["local_end_j"]["MZ_Nm"]) < 1.0e-8
    reaction_by_dof = {
        (row["node_id"], row["dof"]): row["value_si"]
        for row in result.support_reactions
    }
    assert abs(reaction_by_dof[("N1", "UY")] - 7200.0) < 2.0e-6

    replayed = analyze_nonlinear_frame(
        model,
        config,
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert validate_nonlinear_frame_result(replayed).contract_pass is True
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions
    assert replayed.member_end_forces == result.member_end_forces


def test_connected_frame_profile_supports_partial_dofs_across_support_nodes(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["supports"] = [
        {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
        {
            "node": "N2",
            "dofs": ["UX", "UY"],
            "prescribed_values": {"UX": 2.0e-4},
        },
        {"node": "N4", "dofs": ["RZ"]},
    ]

    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "partial-supports.json"),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )

    assert validate_nonlinear_frame_result(result).contract_pass is True
    assert result.node_displacements[1]["UX_m"] == 2.0e-4
    assert {(row["node_id"], row["dof"]) for row in result.support_reactions} == {
        ("N1", "UX"),
        ("N1", "UY"),
        ("N1", "RZ"),
        ("N2", "UX"),
        ("N2", "UY"),
        ("N4", "RZ"),
    }


def test_connected_frame_prescribed_only_commits_without_newton(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["loads"] = []
    payload["supports"] = [
        {
            "node": row["id"],
            "dofs": ["UX", "UY", "RZ"],
            **({"prescribed_values": {"UX": 1.0e-4}} if row["id"] == "N6" else {}),
        }
        for row in payload["nodes"]
    ]
    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "prescribed-only.json"),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )

    assert validate_nonlinear_frame_result(result).contract_pass is True
    assert result.metrics["solver_executed"] is False
    assert result.metrics["no_solve_contract_pass"] is True
    assert result.metrics["sparse_factorization_count"] == 0
    assert result.metrics["sparse_factorization_diagnostics_passed"] is False
    assert result.configuration["equation_scaling"] == {
        "status": "unavailable",
        "reason": "no_free_reference_load",
    }
    assert result.metrics["terminal_physical_residual_trace_status"] == "unavailable"
    assert result.metrics["terminal_physical_residual_trace_reason"] == (
        "no_free_equations_no_convergence_claim"
    )
    assert "nonlinear_execution_topology_plan_hash" in result.contract_bindings
    assert "physical_equation_scaling_binding_hash" not in result.contract_bindings
    assert "terminal_physical_residual_trace_hash" not in result.contract_bindings
    assert result.convergence_history == ()
    assert result.node_displacements[-1]["UX_m"] == 1.0e-4
    assert result.support_reactions


def test_connected_frame_prescribed_only_with_free_equations_fails_closed(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["loads"] = []
    payload["supports"] = [
        {"node": "N1", "dofs": ["UX", "UY", "RZ"]},
        {
            "node": "N2",
            "dofs": ["UX", "UY"],
            "prescribed_values": {"UX": 2.0e-4},
        },
        {"node": "N4", "dofs": ["RZ"]},
    ]

    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "prescribed-only-free-equations.json"),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )

    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.configuration["equation_scaling"] == {
        "status": "unavailable",
        "reason": "no_free_reference_load",
    }
    assert result.unsupported_features == (
        {
            "reason_code": "equation_scaling_unavailable",
            "kind": "corotational_equation_scaling_unavailable",
            "path": "/solver/equation_scaling",
            "detail": (
                "corotational_equation_scaling_unavailable@"
                "/solver/equation_scaling: An iterative path with free equations "
                "requires a source-bound reference force; prescribed motion alone "
                "does not create one."
            ),
        },
    )
    assert "nonlinear_execution_topology_plan_hash" in result.contract_bindings
    assert "physical_equation_scaling_binding_hash" not in result.contract_bindings
    assert result.convergence_history == ()
    assert result.checkpoint == {"available": False}


def test_blocked_result_normalizes_source_diagnostics_to_stable_reason_codes(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["unsupported_features"] = [
        {
            "kind": "vendor_constraint_unsupported",
            "detail": "The source constraint family has no bounded adapter.",
            "vendor_code": 91,
        }
    ]

    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "source-unsupported.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )

    assert result.status == "blocked"
    assert result.unsupported_features == (
        {
            "reason_code": "source_model_unsupported",
            "kind": "vendor_constraint_unsupported",
            "path": "/unsupported_features/0",
            "detail": "The source constraint family has no bounded adapter.",
            "source_context": {"vendor_code": 91},
        },
    )
    assert validate_nonlinear_frame_result(result).contract_pass is False


def test_connected_frame_distinguishes_released_mechanism_from_singular_system(
    tmp_path: Path,
) -> None:
    mechanism = _portal_payload()
    for element in mechanism["elements"]:
        element["end_releases"] = {"i": ["RZ"], "j": ["RZ"]}
    mechanism_result = analyze_nonlinear_frame(
        _model(tmp_path, mechanism, "released-mechanism.json"),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            maximum_iterations=20,
        ),
    )

    assert mechanism_result.status == "blocked"
    assert mechanism_result.unsupported_features[0]["reason_code"] == (
        "mechanism_detected"
    )
    assert mechanism_result.unsupported_features[0]["kind"] == (
        "corotational_released_mechanism_detected"
    )
    assert mechanism_result.unsupported_features[0]["path"] == "/solver/tangent"
    assert mechanism_result.metrics["fallback_count"] == 0
    assert mechanism_result.metrics["regularization_count"] == 0

    singular = _portal_payload()
    singular["supports"] = [{"node": "N1", "dofs": ["UX", "UY"]}]
    singular_result = analyze_nonlinear_frame(
        _model(tmp_path, singular, "singular-system.json"),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            maximum_iterations=20,
        ),
    )

    assert singular_result.status == "blocked"
    assert singular_result.unsupported_features[0]["reason_code"] == (
        "singular_system_detected"
    )
    assert singular_result.unsupported_features[0]["kind"] == (
        "corotational_rigid_body_constraint_rank_deficient"
    )
    assert singular_result.unsupported_features[0]["path"] == "/supports"
    assert singular_result.metrics["solver_executed"] is False
    assert singular_result.metrics["fallback_count"] == 0
    assert singular_result.metrics["regularization_count"] == 0


def test_result_schema_rejects_unknown_unsupported_reason_code(
    tmp_path: Path,
) -> None:
    payload = _branching_payload()
    payload["elements"] = payload["elements"][:-1]
    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "unknown-reason-code.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )
    manifest = result.to_dict()
    manifest["unsupported_features"][0]["reason_code"] = "unstable_typo"

    with pytest.raises(ValueError, match="unsupported_features"):
        validate_nonlinear_frame_manifest(manifest)


def test_unsupported_reason_code_catalog_matches_packaged_schema() -> None:
    schema = nonlinear_frame_api._result_schema_validator().schema
    schema_codes = tuple(
        schema["$defs"]["unsupportedFeature"]["properties"]["reason_code"]["enum"]
    )

    assert schema_codes == (
        nonlinear_frame_api.UNIFIED_NONLINEAR_FRAME_UNSUPPORTED_REASON_CODES
    )


def test_connected_frame_profile_rejects_disconnected_graph(tmp_path: Path) -> None:
    payload = _branching_payload()
    payload["elements"] = payload["elements"][:-1]
    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, "disconnected.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )

    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.unsupported_features[0]["kind"] == (
        "corotational_general_graph_disconnected"
    )


@pytest.mark.parametrize(
    ("mutate", "expected_kind"),
    [
        (
            lambda payload: payload["supports"][1].update({"dofs": []}),
            "corotational_portal_support_invalid",
        ),
        (
            lambda payload: payload["supports"][1].update(
                {"dofs": ["UY"], "prescribed_values": {"UX": 2.0e-4}}
            ),
            "corotational_general_prescribed_displacement_invalid",
        ),
    ],
)
def test_connected_frame_profile_rejects_invalid_support_or_prescribed_values(
    tmp_path: Path,
    mutate,
    expected_kind: str,
) -> None:
    payload = _branching_payload()
    mutate(payload)
    result = analyze_nonlinear_frame(
        _model(tmp_path, payload, f"{expected_kind}.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == expected_kind


def test_connected_frame_profile_enforces_node_and_member_bounds(
    tmp_path: Path,
) -> None:
    too_many_nodes = _branching_payload()
    too_many_nodes["nodes"].extend(
        {
            "id": f"EXTRA{index}",
            "coordinates": [1000.0 + index, 0.0, 0.0],
        }
        for index in range(123)
    )
    node_result = analyze_nonlinear_frame(
        _model(tmp_path, too_many_nodes, "too-many-nodes.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )
    assert node_result.unsupported_features[0]["kind"] == (
        "corotational_portal_node_count_invalid"
    )

    too_many_members = _branching_payload()
    too_many_members["elements"] = too_many_members["elements"] * 52
    member_result = analyze_nonlinear_frame(
        _model(tmp_path, too_many_members, "too-many-members.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE),
    )
    assert member_result.unsupported_features[0]["kind"] == (
        "corotational_portal_member_count_invalid"
    )


def test_terminal_checkpoint_chain_replays_to_identical_corotational_result(
    portal_result,
) -> None:
    model, first = portal_result
    resumed = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
        restart_checkpoint_chain=first.checkpoint_artifact(),
    )

    assert validate_nonlinear_frame_result(resumed).contract_pass is True
    assert resumed.metrics["replayed_prefix_step_count"] == 4
    assert resumed.metrics["newly_solved_step_count"] == 0
    assert (
        resumed.contract_bindings["engineering_result_hash"]
        == (first.contract_bindings["engineering_result_hash"])
    )
    assert resumed.node_displacements == first.node_displacements
    assert resumed.support_reactions == first.support_reactions
    assert resumed.member_end_forces == first.member_end_forces
    assert resumed.section_results == first.section_results
    assert resumed.fiber_results == first.fiber_results
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()


def test_partial_checkpoint_chain_replays_prefix_before_solving_suffix(
    portal_result,
) -> None:
    model, first = portal_result
    compiled = nonlinear_frame_api._compile_portal(model.detached_analysis_snapshot())
    terminal_chain = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        first.checkpoint_artifact(),
        compiled.problem,
    )
    prefix_chain = make_stateful_corotational_fiber_frame2d_checkpoint_chain(
        compiled.problem,
        terminal_chain.checkpoints[:3],
    )
    prefix_bytes = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        compiled.problem,
        prefix_chain,
    )

    resumed = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
        restart_checkpoint_chain=prefix_bytes,
    )

    assert validate_nonlinear_frame_result(resumed).contract_pass is True
    assert resumed.metrics["replayed_prefix_step_count"] == 2
    assert resumed.metrics["newly_solved_step_count"] == 2
    assert resumed.contract_bindings == first.contract_bindings
    assert resumed.node_displacements == first.node_displacements
    assert resumed.support_reactions == first.support_reactions
    assert resumed.member_end_forces == first.member_end_forces
    assert resumed.section_results == first.section_results
    assert resumed.fiber_results == first.fiber_results
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()


def test_tampered_corotational_checkpoint_chain_fails_closed(portal_result) -> None:
    model, first = portal_result
    raw = bytearray(first.checkpoint_artifact())
    raw[-2] = ord("0") if raw[-2] != ord("0") else ord("1")
    blocked = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE, load_steps=4),
        restart_checkpoint_chain=raw,
    )

    assert blocked.status == "blocked"
    assert blocked.contract_pass is False
    assert blocked.metrics["exact_checkpoint_chain_replay"] is False
    assert blocked.checkpoint["available"] is False
    assert blocked.unsupported_features
    assert blocked.unsupported_features[0]["path"] == "/restart_checkpoint_chain"


def test_unified_cli_writes_result_report_and_checkpoint_atomically(
    tmp_path: Path,
    portal_result,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, result = portal_result
    captured: list[NonlinearFrameConfig] = []
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"

    def _capture_config(_model, config, **_kwargs):
        captured.append(config)
        return result

    monkeypatch.setattr(nonlinear_frame_cli, "analyze_nonlinear_frame", _capture_config)

    exit_code = nonlinear_frame_cli.main(
        [
            model.source_path,
            "--profile",
            COROTATIONAL_PORTAL_PROFILE,
            "--matrix-backend",
            VECTOR_SPARSE_MATRIX_BACKEND,
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    assert exit_code == 0
    assert captured[0].matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND
    assert json.loads(result_path.read_text(encoding="utf-8"))["contract_pass"] is True
    assert (
        json.loads(report_path.read_text(encoding="utf-8"))[
            "exact_checkpoint_chain_replay"
        ]
        is True
    )
    assert checkpoint_path.read_bytes() == result.checkpoint_artifact()


def test_unified_cli_runs_connected_frame_profile(tmp_path: Path) -> None:
    model = _model(tmp_path, _branching_payload(), "cli-branching.json")
    result_path = tmp_path / "general-result.json"
    report_path = tmp_path / "general-report.json"
    checkpoint_path = tmp_path / "general-checkpoint.json"

    exit_code = nonlinear_frame_cli.main(
        [
            model.source_path,
            "--profile",
            COROTATIONAL_GENERAL_PROFILE,
            "--load-steps",
            "2",
            "--residual-tolerance",
            "1e-9",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["profile"] == (
        COROTATIONAL_GENERAL_PROFILE
    )
    assert json.loads(report_path.read_text(encoding="utf-8"))["contract_pass"] is True
    assert checkpoint_path.read_bytes()


def test_profile_mismatch_and_result_hash_tampering_fail_closed(tmp_path: Path) -> None:
    blocked = analyze_nonlinear_frame(
        _model(tmp_path, _fixed_payload(), "wrong-profile.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE),
    )
    assert blocked.status == "blocked"
    assert blocked.unsupported_features[0]["kind"] == (
        "corotational_portal_node_count_invalid"
    )

    with pytest.raises(ValueError, match="result_hash"):
        validate_nonlinear_frame_result(
            replace(blocked, result_hash="sha256:" + "0" * 64)
        )


def test_portal_profile_rejects_later_member_feature_surface(tmp_path: Path) -> None:
    payload = _portal_payload()
    payload["elements"][0]["end_releases"] = {"i": [], "j": ["RZ"]}

    blocked = analyze_nonlinear_frame(
        _model(tmp_path, payload, "member-feature.json"),
        NonlinearFrameConfig(profile=COROTATIONAL_PORTAL_PROFILE),
    )

    assert blocked.status == "blocked"
    assert blocked.contract_pass is False
    assert blocked.unsupported_features[0]["kind"] == (
        "corotational_portal_row_keys_invalid"
    )
    assert blocked.unsupported_features[0]["path"] == "/elements/0"
