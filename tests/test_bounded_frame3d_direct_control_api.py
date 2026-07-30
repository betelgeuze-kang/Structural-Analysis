from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

import structural_analysis.api.frame3d_direct_control as frame3d_api_module
from structural_analysis.adapters.bounded_frame3d_direct_control_model_ir import (
    BoundedFrame3DDirectControlModelIRAdapterError,
    adapt_bounded_frame3d_direct_control_model_ir_v2,
    validate_bounded_frame3d_direct_control_model_ir_adapter,
)
from structural_analysis.api.frame3d_direct_control import (
    BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION,
    BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_VERSION,
    BoundedFrame3DDirectControlConfig,
    BoundedFrame3DDirectControlError,
    analyze_bounded_frame3d_direct_control_model_ir,
    validate_bounded_frame3d_direct_control_result,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    stateful_corotational_frame3d_equation_scaling_6dof,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir.loader import load_model_ir_v2, parse_model_ir_v2
from structural_analysis.model_ir.validation import (
    ModelIRValidationError,
    validate_model_ir_v2,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "examples/bounded_frame3d_direct_control.model-ir.v2.json"
AXIAL_YIELD_MODEL_PATH = (
    ROOT / "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
)


def _payload() -> dict:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _config(*targets: float) -> BoundedFrame3DDirectControlConfig:
    return BoundedFrame3DDirectControlConfig(
        control_node_id="N2",
        control_dof="UY",
        control_targets=targets,
    )


def _rehash_result(result, **changes):
    candidate = replace(result, **changes)
    payload = candidate.to_dict()
    payload.pop("result_hash")
    return replace(candidate, result_hash=canonical_hash(payload))


def _rehash_artifact(payload: dict) -> bytes:
    payload = deepcopy(payload)
    payload.pop("artifact_hash", None)
    payload["artifact_hash"] = canonical_hash(payload)
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def test_model_ir_candidate_api_returns_bound_results_without_promotion() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    result = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6, -1.6e-5),
    )
    payload = result.to_dict()

    assert result.schema_version == BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_VERSION
    assert result.status == "ready"
    assert result.contract_pass is True
    assert result.metrics["final_control_coordinate"] == pytest.approx(-1.6e-5)
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.metrics["scaled_residual_inf_norm"] <= (
        result.metrics["scaled_residual_tolerance"]
    )
    assert len(result.node_displacements) == 2
    assert len(result.support_reactions) == 6
    assert len(result.material_states) == 1
    assert result.checkpoint_artifact["available"] is True
    assert result.checkpoint_artifact["exact_resume_supported"] is True
    assert result.checkpoint_artifact_bytes().endswith(b"\n")
    assert payload["source_binding"]["model_ir_content_hash"] == document.content_hash
    assert payload["authority"] == {
        "candidate_api_exposed": True,
        "capability_registry_public": False,
        "workbench_execution": False,
        "numerical_authority": "bounded_candidate",
        "recovery_authority": "node_and_support_candidate",
        "external_vv_level": 0,
        "independent_operator_attached": False,
        "design_authority": False,
        "formal_verification_level_2": False,
        "release_eligible": False,
    }


def test_checkpoint_artifact_resumes_exact_suffix_and_rejects_tampering() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    one_shot = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6, -1.6e-5),
    )
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    resumed = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-1.6e-5),
        restart_checkpoint_artifact=prefix.checkpoint_artifact_bytes(),
    )

    assert resumed.status == "ready"
    assert resumed.checkpoint_artifact["checkpoint_hash"] == (
        one_shot.checkpoint_artifact["checkpoint_hash"]
    )
    assert resumed.node_displacements == one_shot.node_displacements
    assert resumed.support_reactions == one_shot.support_reactions
    assert resumed.material_states == one_shot.material_states
    assert resumed.metrics["final_load_factor"] == one_shot.metrics["final_load_factor"]

    tampered = json.loads(prefix.checkpoint_artifact_bytes())
    tampered["checkpoint"]["displacement"][7] *= 2.0
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_hash_mismatch",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            _config(-1.6e-5),
            restart_checkpoint_artifact=json.dumps(tampered).encode("utf-8"),
        )


def test_v1_checkpoint_requires_complete_recovery_identity_binding() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    original = json.loads(prefix.checkpoint_artifact_bytes())

    for field in (
        "entity_mapping_hash",
        "node_ids",
        "member_ids",
        "member_material_ids",
    ):
        forged = deepcopy(original)
        forged.pop(field)
        with pytest.raises(
            BoundedFrame3DDirectControlError,
            match="bounded_frame3d_checkpoint_artifact_schema_invalid",
        ):
            analyze_bounded_frame3d_direct_control_model_ir(
                document,
                _config(-1.6e-5),
                restart_checkpoint_artifact=_rehash_artifact(forged),
            )


def test_checkpoint_rejects_resume_binding_numeric_domain_alias() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    forged = json.loads(prefix.checkpoint_artifact_bytes())
    accepted_step = forged["resume_binding"]["accepted_step_index"]
    forged["resume_binding"]["accepted_step_index"] = float(accepted_step)

    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match=(
            "bounded_frame3d_checkpoint_resume_binding_numeric_domain_mismatch"
        ),
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            _config(-1.6e-5),
            restart_checkpoint_artifact=_rehash_artifact(forged),
        )


def test_checkpoint_rejects_top_level_integer_float_alias() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    forged = json.loads(prefix.checkpoint_artifact_bytes())
    forged["control_global_dof"] = float(forged["control_global_dof"])

    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_numeric_domain_mismatch",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            _config(-1.6e-5),
            restart_checkpoint_artifact=_rehash_artifact(forged),
        )


def test_checkpoint_artifact_rejects_rehashed_unreachable_material_state() -> None:
    document = load_model_ir_v2(AXIAL_YIELD_MODEL_PATH)
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        BoundedFrame3DDirectControlConfig("N2", "UX", (0.003,)),
    )
    forged = json.loads(prefix.checkpoint_artifact_bytes())
    state = forged["checkpoint"]["material_states"][0]
    state.update(
        {
            "plastic_strain": 0.0,
            "backstress_mpa": 249.0,
            "accumulated_plastic_strain": 0.0,
            "dissipated_energy_density_mj_per_m3": 0.0,
        }
    )
    state["state_hash"] = frame3d_api_module.UniaxialPlasticityState(
        plastic_strain=0.0,
        backstress_mpa=249.0,
        accumulated_plastic_strain=0.0,
        dissipated_energy_density_mj_per_m3=0.0,
    ).state_hash
    checkpoint = forged["checkpoint"]
    checkpoint.pop("checkpoint_hash")
    checkpoint["checkpoint_hash"] = canonical_hash(checkpoint)
    binding = forged["resume_binding"]
    binding["accepted_checkpoint_hash"] = checkpoint["checkpoint_hash"]
    binding.pop("binding_hash")
    binding["binding_hash"] = canonical_hash(binding)
    forged.pop("artifact_hash")
    forged["artifact_hash"] = canonical_hash(forged)
    forged_bytes = (
        json.dumps(
            forged,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match=(
            "bounded_frame3d_checkpoint_material_state_admissibility_failed"
        ),
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            BoundedFrame3DDirectControlConfig("N2", "UX", (0.004,)),
            restart_checkpoint_artifact=forged_bytes,
        )


@pytest.mark.parametrize(
    "payload",
    (
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"value":1e309}',
    ),
)
def test_checkpoint_json_rejects_nonfinite_numbers_with_stable_error(
    payload: bytes,
) -> None:
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_json_invalid",
    ):
        frame3d_api_module._strict_json_object(payload)


def test_cyclic_v2_artifact_resumes_to_identical_chain_and_material_state() -> None:
    document = load_model_ir_v2(AXIAL_YIELD_MODEL_PATH)
    solver_config = StatefulCorotationalFrame3DDisplacementControlConfig(
        allow_direction_reversal=True,
        maximum_direction_reversals=4,
    )
    targets = (0.003, 0.006, 0.001, -0.004, 0.002)

    def cyclic_config(*values: float) -> BoundedFrame3DDirectControlConfig:
        return BoundedFrame3DDirectControlConfig(
            control_node_id="N2",
            control_dof="UX",
            control_targets=values,
            solver_config=solver_config,
        )

    one_shot = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        cyclic_config(*targets),
    )
    prefix = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        cyclic_config(*targets[:2]),
    )
    resumed = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        cyclic_config(*targets[2:]),
        restart_checkpoint_artifact=prefix.checkpoint_artifact_bytes(),
    )

    assert one_shot.status == "ready"
    assert one_shot.metrics["path_mode"] == "cyclic_reversal"
    assert one_shot.metrics["requested_direction_reversal_count"] == 2
    assert one_shot.metrics["cumulative_direction_reversal_count"] == 2
    assert resumed.metrics["resumed_with_direction_reversal"] is True
    assert one_shot.metrics["accepted_target_chain_hash"] == (
        resumed.metrics["accepted_target_chain_hash"]
    )
    assert one_shot.material_states == resumed.material_states
    assert one_shot.node_displacements == resumed.node_displacements
    assert one_shot.checkpoint_artifact == resumed.checkpoint_artifact
    artifact = json.loads(one_shot.checkpoint_artifact_bytes())
    assert artifact["schema_version"] == (
        BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION
    )
    assert artifact["accepted_target_chain_hash"] == (
        one_shot.metrics["accepted_target_chain_hash"]
    )

    forged = json.loads(prefix.checkpoint_artifact_bytes())
    forged["accepted_target_chain_hash"] = "sha256:" + "0" * 64
    forged.pop("artifact_hash")
    forged["artifact_hash"] = canonical_hash(forged)
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_cyclic_binding_mismatch",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            cyclic_config(*targets[2:]),
            restart_checkpoint_artifact=(
                json.dumps(
                    forged,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            ),
        )

    impossible_count = json.loads(prefix.checkpoint_artifact_bytes())
    binding = impossible_count["resume_binding"]
    binding["cumulative_completed_target_count"] = (
        binding["accepted_step_index"] + 1
    )
    binding.pop("binding_hash")
    binding["binding_hash"] = canonical_hash(binding)
    impossible_count["cumulative_completed_target_count"] = binding[
        "cumulative_completed_target_count"
    ]
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_resume_binding_invalid",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            cyclic_config(*targets[2:]),
            restart_checkpoint_artifact=_rehash_artifact(impossible_count),
        )

    numeric_alias = json.loads(prefix.checkpoint_artifact_bytes())
    numeric_alias["cumulative_completed_target_count"] = float(
        numeric_alias["cumulative_completed_target_count"]
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_numeric_domain_mismatch",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            cyclic_config(*targets[2:]),
            restart_checkpoint_artifact=_rehash_artifact(numeric_alias),
        )


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    (
        (
            lambda payload: payload["materials"][0]["parameters"].pop(
                "shear_modulus_pa"
            ),
            "bounded_frame3d_shear_modulus_missing",
        ),
        (
            lambda payload: payload["elements"][0]["offsets"]["i_global_m"].__setitem__(
                0, 0.1
            ),
            "bounded_frame3d_rigid_offset_unsupported",
        ),
        (
            lambda payload: payload["constraints"][0].update(
                {
                    "dofs": ["UX", "UY", "UZ"],
                    "prescribed_values_si": {"UX": 0.0, "UY": 0.0, "UZ": 0.0},
                }
            ),
            "bounded_frame3d_rigid_body_restraint_rank_insufficient",
        ),
        (
            lambda payload: payload["load_patterns"][0]["nodal_loads"][0].update(
                {
                    "node_id": "N1",
                    "components_si": {
                        "FX": 100.0,
                        "FY": 0.0,
                        "FZ": 0.0,
                        "MX": 0.0,
                        "MY": 0.0,
                        "MZ": 0.0,
                    },
                }
            ),
            "bounded_frame3d_reference_load_on_restrained_dof",
        ),
        (
            lambda payload: payload["constraints"][0].update({"node_id": "NX"}),
            "dangling_reference",
        ),
        (
            lambda payload: payload["nodes"][0]["coordinates_m"].__setitem__(
                0, 10**400
            ),
            "non_finite_number",
        ),
        (
            lambda payload: (
                payload["nodes"][0].update(
                    {"coordinates_m": [9.0e307, 0.0, 0.0]}
                ),
                payload["nodes"][1].update(
                    {"coordinates_m": [1.0e308, 0.0, 0.0]}
                ),
            ),
            "bounded_frame3d_coordinate_magnitude_out_of_range",
        ),
        (
            lambda payload: payload["materials"][0]["parameters"].update(
                {"elastic_modulus_pa": 5.0e-324}
            ),
            "bounded_frame3d_material_conversion_out_of_range",
        ),
    ),
)
def test_model_ir_profile_blocks_unsupported_semantics_before_solver(
    mutate,
    reason_code: str,
) -> None:
    payload = deepcopy(_payload())
    mutate(payload)
    report = validate_model_ir_v2(payload)

    assert report.analysis_ready is False
    assert reason_code in {row.code for row in report.issues}
    with pytest.raises(ModelIRValidationError, match=reason_code):
        parse_model_ir_v2(payload)


def test_control_contract_rejects_restrained_and_nonmonotonic_coordinates() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_control_dof_restrained",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            BoundedFrame3DDirectControlConfig("N1", "UX", (1.0e-6,)),
        )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_control_targets_nonmonotonic",
    ):
        analyze_bounded_frame3d_direct_control_model_ir(
            document,
            _config(-8.0e-6, -4.0e-6),
        )


def test_result_validator_rejects_authority_promotion() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    result = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    forged_authority = dict(result.authority)
    forged_authority["release_eligible"] = True
    forged = replace(result, authority=forged_authority)

    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_result_schema_invalid",
    ):
        validate_bounded_frame3d_direct_control_result(forged)

    artifact = result.checkpoint_artifact_bytes()
    assert b'"accepted_control_target":-8e-06' in artifact
    tampered_artifact = artifact.replace(
        b'"accepted_control_target":-8e-06',
        b'"accepted_control_target":-9e-06',
        1,
    )
    forged_bytes = replace(
        result,
        _checkpoint_artifact_bytes=tampered_artifact,
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_hash_mismatch",
    ):
        validate_bounded_frame3d_direct_control_result(forged_bytes)


def test_result_validator_rejects_cross_field_and_artifact_forgery() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    result = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        _config(-8.0e-6),
    )
    incomplete_metrics = dict(result.metrics)
    incomplete_metrics["completed_requested_target_count"] = 0
    forged_ready = _rehash_result(result, metrics=incomplete_metrics)
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_result_ready_contract_invalid",
    ):
        validate_bounded_frame3d_direct_control_result(forged_ready)

    forged_blocked = _rehash_result(
        result,
        status="blocked",
        contract_pass=False,
        terminal_reason_code="forged_failure",
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_result_blocked_contract_invalid",
    ):
        validate_bounded_frame3d_direct_control_result(forged_blocked)

    changed_payload = deepcopy(_payload())
    changed_payload["model_id"] = "bounded-frame3d-direct-control-other"
    other = analyze_bounded_frame3d_direct_control_model_ir(
        parse_model_ir_v2(changed_payload),
        _config(-8.0e-6),
    )
    transplanted = _rehash_result(
        result,
        checkpoint_artifact=other.checkpoint_artifact,
        _checkpoint_artifact_bytes=other.checkpoint_artifact_bytes(),
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_artifact_result_binding_mismatch",
    ):
        validate_bounded_frame3d_direct_control_result(transplanted)

    artifact_payload = json.loads(result.checkpoint_artifact_bytes())
    artifact_payload["checkpoint"]["load_factor"] += 1.0e-6
    artifact_payload.pop("artifact_hash")
    artifact_payload["artifact_hash"] = canonical_hash(artifact_payload)
    forged_artifact_bytes = (
        json.dumps(
            artifact_payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    forged_descriptor = dict(result.checkpoint_artifact)
    forged_descriptor["artifact_hash"] = artifact_payload["artifact_hash"]
    forged_descriptor["byte_length"] = len(forged_artifact_bytes)
    forged_checkpoint = _rehash_result(
        result,
        checkpoint_artifact=forged_descriptor,
        _checkpoint_artifact_bytes=forged_artifact_bytes,
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_checkpoint_hash_mismatch",
    ):
        validate_bounded_frame3d_direct_control_result(forged_checkpoint)

    forged_state = dict(result.material_states[0])
    forged_state["plastic_strain"] += 1.0e-6
    forged_recovery = _rehash_result(
        result,
        material_states=(forged_state,),
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_result_checkpoint_material_state_mismatch",
    ):
        validate_bounded_frame3d_direct_control_result(forged_recovery)

    forged_node = dict(result.node_displacements[0])
    forged_node["node_id"] = "FORGED_NODE"
    forged_identity = _rehash_result(
        result,
        node_displacements=(forged_node, *result.node_displacements[1:]),
    )
    with pytest.raises(
        BoundedFrame3DDirectControlError,
        match="bounded_frame3d_result_checkpoint_material_state_mismatch",
    ):
        validate_bounded_frame3d_direct_control_result(forged_identity)


def test_result_is_deeply_immutable_and_to_dict_is_detached() -> None:
    result = analyze_bounded_frame3d_direct_control_model_ir(
        load_model_ir_v2(MODEL_PATH),
        _config(-8.0e-6),
    )
    detached = result.to_dict()
    detached["control"]["control_targets"][0] = -9.0e-6
    detached["control"]["solver_config"]["maximum_iterations"] = 1

    assert result.control["control_targets"] == (-8.0e-6,)
    assert result.control["solver_config"]["maximum_iterations"] != 1
    assert validate_bounded_frame3d_direct_control_result(result) is result


def test_rotational_control_reports_dimensionally_separated_residuals() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    config = BoundedFrame3DDirectControlConfig("N2", "RX", (1.0e-6,))
    result = analyze_bounded_frame3d_direct_control_model_ir(document, config)
    scaling = stateful_corotational_frame3d_equation_scaling_6dof(
        adapt_bounded_frame3d_direct_control_model_ir_v2(document).model,
        config=config.solver_config.frame_config,
    )
    metrics = result.metrics
    expected_scaled = max(
        metrics["raw_translational_residual_inf_norm_kn"]
        / scaling.residual_translation_scale_kn,
        metrics["raw_rotational_residual_inf_norm_kn_m"]
        / scaling.residual_rotation_scale_kn_m,
    )

    assert result.status == "ready"
    assert result.control["control_unit"] == "rad"
    assert "final_residual_inf_norm_kn" not in metrics
    assert metrics["scaled_residual_inf_norm"] == pytest.approx(expected_scaled)
    assert metrics["equation_scaling_hash"] == scaling.scaling_hash
    assert metrics["scaled_residual_inf_norm"] <= metrics["scaled_residual_tolerance"]


def test_translated_collinear_support_rank_deficiency_is_blocked() -> None:
    payload = deepcopy(_payload())
    payload["nodes"][0]["coordinates_m"] = [1.0e6, 1.0e6, 1.0e6]
    payload["nodes"][1]["coordinates_m"] = [1.0e6 + 2.0, 1.0e6, 1.0e6]
    node_3 = deepcopy(payload["nodes"][1])
    node_3.update(
        {
            "id": "N3",
            "index": 2,
            "coordinates_m": [1.0e6 + 4.0, 1.0e6, 1.0e6],
            "source_id": "generated:N3",
        }
    )
    payload["nodes"].append(node_3)
    element_2 = deepcopy(payload["elements"][0])
    element_2.update(
        {
            "id": "E2",
            "index": 1,
            "node_ids": ["N2", "N3"],
            "source_id": "generated:E2",
        }
    )
    payload["elements"].append(element_2)
    payload["constraints"] = []
    for index, node_id in enumerate(("N1", "N2", "N3")):
        payload["constraints"].append(
            {
                "id": f"BC{index + 1}",
                "index": index,
                "type": "fixed_dofs",
                "node_id": node_id,
                "dofs": ["UX", "UY", "UZ"],
                "prescribed_values_si": {"UX": 0, "UY": 0, "UZ": 0},
                "source_id": f"generated:BC{index + 1}",
                "extensions": {},
            }
        )
    load = payload["load_patterns"][0]["nodal_loads"][0]
    load["node_id"] = "N3"
    load["components_si"] = {
        "FX": 0,
        "FY": 0,
        "FZ": 0,
        "MX": 20,
        "MY": 0,
        "MZ": 0,
    }

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is True
    assert report.analysis_ready is False
    assert "bounded_frame3d_rigid_body_restraint_rank_insufficient" in {
        row.code for row in report.issues
    }


def test_adapter_validator_recompiles_document_projection() -> None:
    document = load_model_ir_v2(MODEL_PATH)
    changed_payload = deepcopy(_payload())
    changed_payload["nodes"][1]["coordinates_m"][0] = 3.0
    other_document = parse_model_ir_v2(changed_payload)
    adapter = adapt_bounded_frame3d_direct_control_model_ir_v2(document)
    other_adapter = adapt_bounded_frame3d_direct_control_model_ir_v2(other_document)
    forged = replace(
        adapter,
        model_hash=other_adapter.model_hash,
        _model=other_adapter.model,
    )
    forged_payload = forged.to_dict()
    forged_payload.pop("adapter_hash")
    forged = replace(forged, adapter_hash=canonical_hash(forged_payload))

    with pytest.raises(
        BoundedFrame3DDirectControlModelIRAdapterError,
        match="bounded_frame3d_model_ir_compiled_projection_mismatch",
    ):
        validate_bounded_frame3d_direct_control_model_ir_adapter(
            forged,
            document=document,
        )


def test_adapter_rejects_value_losing_binary64_source_projection() -> None:
    payload = _payload()
    payload["materials"][0]["parameters"]["yield_stress_pa"] = 2**53 + 1
    document = parse_model_ir_v2(payload)

    with pytest.raises(
        BoundedFrame3DDirectControlModelIRAdapterError,
        match=(
            "bounded_frame3d_model_ir_numeric_source_not_binary64"
            "@/materials/0/parameters/yield_stress_pa"
        ),
    ):
        adapt_bounded_frame3d_direct_control_model_ir_v2(document)
