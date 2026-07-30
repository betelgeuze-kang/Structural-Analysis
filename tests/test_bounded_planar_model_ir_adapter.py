from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_manifest,
    validate_nonlinear_frame_result,
)
from structural_analysis.api import nonlinear_frame_cli
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.adapters import (
    BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE,
    BoundedPlanarModelIRAdapterError,
    adapt_bounded_planar_model_ir_v2,
    validate_bounded_planar_model_ir_adapter,
    validate_bounded_planar_execution_plan_manifest,
)
from structural_analysis.model_ir import (
    ModelIRValidationError,
    load_model_ir_v2,
    parse_model_ir_v2,
    validate_model_ir_v2,
)

SETTLEMENT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "bounded_planar_settlement.model-ir.v2.json"
)


def _payload() -> dict:
    return {
        "schema_version": "structural-analysis-model-ir.v2",
        "model_id": "bounded-planar-member-features",
        "capability_profile": BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE,
        "provenance": {
            "source_format": "generated",
            "source_ref": "generated:bounded-planar-member-features",
            "source_sha256": "sha256:" + "1" * 64,
            "normalizer_id": "bounded-planar-model-ir-test-builder",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad",
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0,
            },
            "extensions": {},
        },
        "units": {
            "length": "m",
            "force": "N",
            "mass": "kg",
            "time": "s",
            "rotation": "rad",
        },
        "coordinate_system": {
            "frame_id": "global",
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
            "handedness": "right",
            "origin_m": [0.0, 0.0, 0.0],
        },
        "dof_components": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "nodes": [
            {
                "id": "N1",
                "index": 0,
                "coordinates_m": [0.0, 0.0, 0.0],
                "source_id": "generated:N1",
                "extensions": {},
            },
            {
                "id": "N2",
                "index": 1,
                "coordinates_m": [4.0, 0.0, 0.0],
                "source_id": "generated:N2",
                "extensions": {},
            },
        ],
        "materials": [
            {
                "id": "steel",
                "index": 0,
                "law_id": "bilinear_combined_hardening_steel",
                "parameter_set_version": "1",
                "parameters": {
                    "elastic_modulus_pa": 200.0e9,
                    "yield_stress_pa": 250.0e6,
                    "isotropic_hardening_modulus_pa": 3.0e9,
                    "kinematic_hardening_modulus_pa": 5.0e9,
                    "yield_tolerance_pa": 1.0e-4,
                },
                "state_schema": {
                    "stateful": True,
                    "state_update_epoch": "accepted_step",
                    "supports_trial_commit_rollback": True,
                },
                "source_id": "generated:steel",
                "extensions": {},
            },
            {
                "id": "concrete",
                "index": 1,
                "law_id": "asymmetric_concrete_damage",
                "parameter_set_version": "1",
                "parameters": {
                    "elastic_modulus_pa": 30.0e9,
                    "tensile_strength_pa": 3.0e6,
                    "compressive_strength_pa": 30.0e6,
                    "tensile_softening_rate": 3000.0,
                    "compressive_softening_rate": 400.0,
                    "history_tolerance": 1.0e-14,
                },
                "state_schema": {
                    "stateful": True,
                    "state_update_epoch": "accepted_step",
                    "supports_trial_commit_rollback": True,
                },
                "source_id": "generated:concrete",
                "extensions": {},
            },
        ],
        "sections": [
            {
                "id": "RC1",
                "index": 0,
                "family_id": "rectangular_rc_fiber_2d",
                "parameter_set_version": "1",
                "parameters": {
                    "width_m": 0.4,
                    "depth_m": 0.6,
                    "cover_m": 0.05,
                    "concrete_layer_count": 2,
                    "top_bar_count": 4,
                    "bottom_bar_count": 4,
                    "bar_area_m2": 0.000387,
                },
                "steel_material_id": "steel",
                "concrete_material_id": "concrete",
                "source_id": "generated:RC1",
                "extensions": {},
            }
        ],
        "elements": [
            {
                "id": "E1",
                "index": 0,
                "type": "frame_2d",
                "formulation": "stateful_corotational_rc_fiber_frame2d",
                "node_ids": ["N1", "N2"],
                "section_id": "RC1",
                "integration_order": 3,
                "offsets": {
                    "i_global_m": [0.2, 0.0, 0.0],
                    "j_global_m": [-0.2, 0.0, 0.0],
                },
                "releases": {"i": [], "j": ["RZ"]},
                "uniform_distributed_load_local": {
                    "basis": "initial_member_local",
                    "behavior": "dead",
                    "qx_n_per_m": 0.0,
                    "qy_n_per_m": -2000.0,
                },
                "source_id": "generated:E1",
                "extensions": {},
            }
        ],
        "constraints": [
            {
                "id": "BC1",
                "index": 0,
                "type": "fixed_dofs",
                "node_id": "N1",
                "dofs": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
                "prescribed_values_si": {
                    "UX": 0.0,
                    "UY": 0.0,
                    "UZ": 0.0,
                    "RX": 0.0,
                    "RY": 0.0,
                    "RZ": 0.0,
                },
                "source_id": "generated:BC1",
                "extensions": {},
            },
            {
                "id": "BC2",
                "index": 1,
                "type": "fixed_dofs",
                "node_id": "N2",
                "dofs": ["UZ", "RX", "RY", "RZ"],
                "prescribed_values_si": {
                    "UZ": 0.0,
                    "RX": 0.0,
                    "RY": 0.0,
                    "RZ": 0.0,
                },
                "source_id": "generated:BC2",
                "extensions": {},
            },
        ],
        "load_patterns": [
            {
                "id": "LP1",
                "index": 0,
                "analysis_type": "nonlinear_static_load_control",
                "self_weight": [0.0, 0.0, 0.0],
                "nodal_loads": [],
                "source_id": "generated:LP1",
                "extensions": {},
            }
        ],
        "load_combinations": [],
        "time_functions": [],
        "construction_stages": [],
        "roundtrip_map": [],
        "unsupported_features": [],
        "extensions": {},
    }


def _codes(payload: dict) -> set[str]:
    return {issue.code for issue in validate_model_ir_v2(payload).issues}


def test_bounded_planar_model_ir_adapts_and_runs_exact_engineering_result() -> None:
    document = parse_model_ir_v2(_payload())
    adapter = adapt_bounded_planar_model_ir_v2(document)
    canonical = adapter.canonical_model

    assert adapter.model_ir_content_hash == document.content_hash
    assert adapter.model_ir_semantic_hash == document.semantic_hash
    assert adapter.model_ir_provenance_hash == document.provenance_hash
    assert adapter.canonical_model_checksum == canonical.canonical_model_checksum
    assert canonical.input_checksum == document.content_hash
    assert canonical.materials[0]["elastic_modulus_mpa"] == 200000.0
    assert (
        canonical.elements[0]["uniform_distributed_load_local"]["qy_kN_per_m"] == -2.0
    )
    assert canonical.supports == [
        {
            "node": "N1",
            "dofs": ["UX", "UY", "RZ"],
            "prescribed_values": {"UX": 0.0, "UY": 0.0, "RZ": 0.0},
        },
        {
            "node": "N2",
            "dofs": ["RZ"],
            "prescribed_values": {"RZ": 0.0},
        },
    ]
    validate_bounded_planar_model_ir_adapter(adapter, document=document)

    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            maximum_iterations=60,
        ),
    )
    report = validate_nonlinear_frame_result(result)
    assert result.status == "ready"
    assert result.engineering_result_ir is not None
    assert report.contract_pass is True
    assert report.exact_checkpoint_chain_replay is True
    assert report.exact_engineering_recovery is True
    source_binding = result.contract_bindings["source_model_ir_adapter"]
    assert source_binding["model_ir_content_hash"] == document.content_hash
    assert (
        source_binding["canonical_model_checksum"] == canonical.canonical_model_checksum
    )
    execution_plan = validate_bounded_planar_execution_plan_manifest(
        result.contract_bindings["bounded_planar_execution_plan"]
    )
    assert execution_plan["model_ir_content_hash"] == document.content_hash
    assert (
        execution_plan["topology_plan_hash"]
        == result.contract_bindings["nonlinear_execution_topology_plan_hash"]
    )
    assert execution_plan["physical_dof_components"] == [
        "UX",
        "UY",
        "UZ",
        "RX",
        "RY",
        "RZ",
    ]
    assert execution_plan["solver_dof_components"] == ["UX", "UY", "RZ"]
    assert execution_plan["equation_scaling_status"] == "available"
    assert execution_plan["authority_axes"]["numerical_result"] == ("not_authoritative")


def test_source_unit_provenance_preserves_si_semantics_and_engineering_result() -> None:
    canonical_payload = _payload()
    alternate_source_units = deepcopy(canonical_payload)
    alternate_source_units["provenance"].update(
        {
            "source_ref": "generated:bounded-planar-member-features-mm-kN",
            "source_sha256": "sha256:" + "2" * 64,
        }
    )
    alternate_source_units["provenance"]["source_units"].update(
        {"length": "mm", "force": "kN"}
    )
    alternate_source_units["provenance"]["unit_scales_to_si"].update(
        {"length_to_m": 1.0e-3, "force_to_n": 1.0e3}
    )

    canonical_document = parse_model_ir_v2(canonical_payload)
    alternate_document = parse_model_ir_v2(alternate_source_units)
    canonical_adapter = adapt_bounded_planar_model_ir_v2(canonical_document)
    alternate_adapter = adapt_bounded_planar_model_ir_v2(alternate_document)

    assert canonical_document.semantic_hash == alternate_document.semantic_hash
    assert canonical_document.content_hash != alternate_document.content_hash
    assert canonical_document.provenance_hash != alternate_document.provenance_hash
    assert (
        canonical_adapter.canonical_model_checksum
        == alternate_adapter.canonical_model_checksum
    )
    assert canonical_adapter.unit_conversion_hash == alternate_adapter.unit_conversion_hash
    assert canonical_adapter.adapter_hash != alternate_adapter.adapter_hash

    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=2,
        residual_tolerance=1.0e-9,
        maximum_iterations=60,
    )
    canonical_result = analyze_nonlinear_frame_model_ir(
        canonical_document,
        config,
    )
    alternate_result = analyze_nonlinear_frame_model_ir(
        alternate_document,
        config,
    )
    assert canonical_result.status == alternate_result.status == "ready"
    assert canonical_result.node_displacements == alternate_result.node_displacements
    assert canonical_result.support_reactions == alternate_result.support_reactions
    assert canonical_result.member_end_forces == alternate_result.member_end_forces
    assert canonical_result.engineering_result_ir == alternate_result.engineering_result_ir


def test_bounded_planar_settlement_fixture_uses_scaled_exact_recovery() -> None:
    document = load_model_ir_v2(SETTLEMENT_FIXTURE)
    adapter = adapt_bounded_planar_model_ir_v2(document)
    canonical = adapter.canonical_model

    assert canonical.supports == [
        {
            "node": "N1",
            "dofs": ["UX", "UY", "RZ"],
            "prescribed_values": {"UX": 0.0, "UY": 0.0, "RZ": 0.0},
        },
        {
            "node": "N2",
            "dofs": ["UY", "RZ"],
            "prescribed_values": {"UY": -1.0e-4, "RZ": 0.0},
        },
    ]
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-9,
            maximum_iterations=80,
        ),
    )
    report = validate_nonlinear_frame_result(result)

    assert result.status == "ready"
    assert report.contract_pass is True
    assert report.exact_checkpoint_chain_replay is True
    assert report.exact_engineering_recovery is True
    assert result.metrics["solver_executed"] is True
    assert result.metrics["no_solve_contract_pass"] is False
    assert result.configuration["equation_scaling"]["status"] == "available"
    assert result.configuration["equation_scaling"]["reference_force_n"] == 1000.0
    assert result.metrics["terminal_physical_residual_trace_status"] == "available"
    assert result.convergence_history
    assert result.node_displacements[1]["UY_m"] == -1.0e-4
    assert result.node_displacements[1]["UX_m"] > 0.0
    assert {
        (row["node_id"], row["dof"]) for row in result.support_reactions
    } == {
        ("N1", "UX"),
        ("N1", "UY"),
        ("N1", "RZ"),
        ("N2", "UY"),
        ("N2", "RZ"),
    }

    replayed = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-9,
            maximum_iterations=80,
        ),
        restart_checkpoint_chain=result.checkpoint_artifact(),
    )
    assert replayed.node_displacements == result.node_displacements
    assert replayed.support_reactions == result.support_reactions
    assert replayed.member_end_forces == result.member_end_forces
    assert replayed.checkpoint_artifact() == result.checkpoint_artifact()


def test_detached_unified_result_rejects_rehashed_model_ir_target_tamper() -> None:
    document = parse_model_ir_v2(_payload())
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            maximum_iterations=60,
        ),
    )
    manifest = result.to_dict()
    receipt = manifest["contract_bindings"]["source_model_ir_adapter"]
    receipt["canonical_model_checksum"] = "sha256:" + "a" * 64
    receipt_body = dict(receipt)
    receipt_body.pop("adapter_hash")
    receipt["adapter_hash"] = canonical_hash(receipt_body)
    result_body = dict(manifest)
    result_body.pop("result_hash")
    manifest["result_hash"] = canonical_hash(result_body)

    with pytest.raises(ValueError, match="canonical model differs"):
        validate_nonlinear_frame_manifest(manifest)


def test_detached_unified_result_rejects_rehashed_execution_plan_tamper() -> None:
    document = parse_model_ir_v2(_payload())
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            maximum_iterations=60,
        ),
    )
    manifest = result.to_dict()
    plan = manifest["contract_bindings"]["bounded_planar_execution_plan"]
    plan["entity_mapping_hash"] = "sha256:" + "b" * 64
    plan_body = dict(plan)
    plan_body.pop("binding_hash")
    plan["binding_hash"] = canonical_hash(plan_body)
    result_body = dict(manifest)
    result_body.pop("result_hash")
    manifest["result_hash"] = canonical_hash(result_body)

    with pytest.raises(ValueError, match="dof_ordering_hash differs"):
        validate_nonlinear_frame_manifest(manifest)


def test_adapter_returns_detached_canonical_snapshots() -> None:
    adapter = adapt_bounded_planar_model_ir_v2(parse_model_ir_v2(_payload()))
    first = adapter.canonical_model
    first.nodes[0]["coordinates"][0] = 99.0

    second = adapter.canonical_model
    assert second.nodes[0]["coordinates"] == [0.0, 0.0, 0.0]
    assert second.canonical_model_checksum == adapter.canonical_model_checksum


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda payload: payload["nodes"][1]["coordinates_m"].__setitem__(2, 1.0),
            "bounded_planar_node_out_of_plane",
        ),
        (
            lambda payload: payload["constraints"][1]["dofs"].remove("RY"),
            "bounded_planar_inactive_dof_unrestrained",
        ),
        (
            lambda payload: payload["elements"][0]["releases"]["j"].append("RY"),
            "bounded_planar_release_unsupported",
        ),
        (
            lambda payload: payload["sections"][0].update(
                {"steel_material_id": "concrete"}
            ),
            "bounded_planar_section_steel_material_invalid",
        ),
        (
            lambda payload: payload["elements"][0][
                "uniform_distributed_load_local"
            ].update({"qy_n_per_m": 0.0}),
            "bounded_planar_load_missing",
        ),
    ],
)
def test_bounded_planar_semantics_fail_closed(mutate, expected_code: str) -> None:
    payload = _payload()
    mutate(payload)
    report = validate_model_ir_v2(payload)

    assert report.schema_valid is True
    assert report.analysis_ready is False
    assert expected_code in _codes(payload)
    with pytest.raises(ModelIRValidationError):
        parse_model_ir_v2(payload)


def test_capability_profile_condition_rejects_cross_profile_entities() -> None:
    payload = _payload()
    payload["capability_profile"] = "engine_v2_phase0_linear_3d"
    report = validate_model_ir_v2(payload)

    assert report.schema_valid is False
    assert report.analysis_ready is False


def test_linear_model_ir_cannot_be_misrepresented_as_bounded_planar() -> None:
    payload = _payload()
    bounded = parse_model_ir_v2(payload)
    linear_payload = deepcopy(payload)
    linear_payload["capability_profile"] = "engine_v2_phase0_linear_3d"

    assert bounded.capability_profile == BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE
    with pytest.raises(ModelIRValidationError):
        parse_model_ir_v2(linear_payload)
    with pytest.raises(BoundedPlanarModelIRAdapterError):
        adapt_bounded_planar_model_ir_v2(object())  # type: ignore[arg-type]


def test_bounded_planar_model_ir_sample_runs_through_cli(tmp_path: Path) -> None:
    sample = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "bounded_planar_frame_alpha.model-ir.v2.json"
    )
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"

    exit_code = nonlinear_frame_cli.main(
        [
            str(sample),
            "--profile",
            COROTATIONAL_GENERAL_PROFILE,
            "--load-steps",
            "2",
            "--residual-tolerance",
            "1e-9",
            "--max-iterations",
            "60",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["contract_pass"] is True
    assert (
        result["contract_bindings"]["source_model_ir_adapter"]["model_ir_content_hash"]
        == result["input_checksum"]
    )
    assert checkpoint_path.read_bytes()
