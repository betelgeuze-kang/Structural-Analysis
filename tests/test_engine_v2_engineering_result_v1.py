from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import (
    AXIAL_LOCAL_END_FORCE_PROFILE,
    ENGINEERING_RESULT_AUTHORITY_PROFILE,
    ENGINEERING_RESULT_IR_SCHEMA_VERSION,
    FRAME_LOCAL_END_FORCE_PROFILE,
    LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION,
    EngineeringRecoveryError,
    EngineeringResultIR,
    LinearStaticRecoveryOperator,
    bind_equation_scaling_to_execution_plan,
    commit_trial_state,
    create_engineering_result_ir,
    create_equation_scaling,
    create_execution_plan,
    create_execution_plan_reduced_csr,
    create_initial_state,
    create_linear_static_recovery_operator,
    create_numerical_result_ir,
    open_trial_state,
    validate_engineering_result_artifact_bytes,
    validate_engineering_result_ir_manifest,
    validate_linear_static_recovery_operator_manifest,
    write_engineering_result_artifacts,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)


ROOT = Path(__file__).resolve().parents[1]


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _rehash(payload: dict, field: str) -> None:
    without_hash = dict(payload)
    without_hash.pop(field)
    payload[field] = canonical_hash(without_hash)


def _fixture(
    *,
    element_profile: str = FRAME_LOCAL_END_FORCE_PROFILE,
    displacement_scale: float = 1.0,
    constrained_displacement: float = 0.0,
    model_hash_character: str = "1",
):
    dof_count = 12
    row_ptr = np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8")
    columns = np.tile(np.arange(dof_count, dtype="<i4"), dof_count)
    kinematic = np.eye(dof_count, dtype="<f8").reshape(1, 12, 12)
    if element_profile == AXIAL_LOCAL_END_FORCE_PROFILE:
        diagonal = np.zeros(dof_count, dtype="<f8")
        diagonal[0] = 100.0
        diagonal[6] = 200.0
    else:
        diagonal = np.arange(100.0, 220.0, 10.0, dtype="<f8")
    local_stiffness = np.diag(diagonal).reshape(1, 12, 12)
    global_matrix = np.diag(diagonal)
    global_values = immutable_array(global_matrix.reshape(-1), dtype="<f8")
    base = create_execution_plan(
        model_ir_content_hash=_hash(model_hash_character),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=np.asarray(
            [-1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5], dtype="<i4"
        ),
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=np.arange(6, dtype="<i4"),
        free_dofs=np.arange(6, dof_count, dtype="<i4"),
        csr_row_ptr=row_ptr,
        csr_column_indices=columns,
    )
    target_displacement = np.zeros(dof_count, dtype="<f8")
    if element_profile == AXIAL_LOCAL_END_FORCE_PROFILE:
        target_displacement[6] = 0.01
    else:
        target_displacement[6:] = np.asarray(
            [0.01, 0.02, 0.03, 0.04, 0.05, 0.06], dtype="<f8"
        )
    reference_load = global_matrix @ target_displacement
    reference_load[0] = 7.0
    coordinates = np.asarray(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8"
    )
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=array_data_hash(global_values),
    )
    initial = create_initial_state(plan)
    displacement = target_displacement * displacement_scale
    displacement[0] = constrained_displacement
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=3,
        load_factor=1.0,
        time_s=0.0,
        expected_plan=plan,
    )
    state = commit_trial_state(initial, trial, expected_plan=plan)
    free_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")], dtype="<f8"
    )
    numerical = create_numerical_result_ir(
        result_id="result.linear.lc1",
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        committed_state=state,
        source_run_schema_version="structural-analysis-cpu-fgmres-run.v1",
        source_run_hash=_hash("7"),
        source_terminal_reason="converged_scaled_residual",
        source_solution_data_hash=array_data_hash(free_solution),
        convergence_receipt_hash=_hash("8"),
        full_residual_receipt_hash=_hash("9"),
        boundary_condition_receipt_hash=_hash("a"),
        backend_role="cpu_reference",
        backend_receipt_hash=_hash("b"),
    )
    operator = create_linear_static_recovery_operator(
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        global_csr_values_si=global_values,
        reference_external_load_global_si=reference_load,
        element_kinematic_matrices=kinematic,
        element_local_stiffness_matrices_si=local_stiffness,
        element_result_profiles=(element_profile,),
        recovery_law_receipt_hash=_hash("c"),
    )
    return {
        "plan": plan,
        "scaling": scaling,
        "reduced": reduced,
        "numerical": numerical,
        "operator": operator,
        "global_values": global_values,
        "reference_load": reference_load,
        "kinematic": kinematic,
        "local_stiffness": local_stiffness,
        "target_displacement": target_displacement,
    }


def test_engineering_result_is_deterministic_bound_and_schema_valid() -> None:
    import structural_analysis.engine_v2 as engine_v2

    fixture = _fixture()
    first = create_engineering_result_ir(
        engineering_result_id="engineering.linear.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )
    second = create_engineering_result_ir(
        engineering_result_id="engineering.linear.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )
    operator_manifest = fixture["operator"].to_manifest()
    result_manifest = first.to_manifest()
    operator_schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/linear_static_recovery_operator_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    result_schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/engineering_result_ir_v1.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(operator_schema)
    Draft202012Validator(operator_schema).validate(operator_manifest)
    Draft202012Validator.check_schema(result_schema)
    Draft202012Validator(result_schema).validate(result_manifest)
    assert isinstance(fixture["operator"], LinearStaticRecoveryOperator)
    assert isinstance(first, EngineeringResultIR)
    assert engine_v2.EngineeringResultIR is EngineeringResultIR
    assert (
        fixture["operator"].schema_version
        == LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION
    )
    assert first.schema_version == ENGINEERING_RESULT_IR_SCHEMA_VERSION
    assert first.authority_profile == ENGINEERING_RESULT_AUTHORITY_PROFILE
    assert first.engineering_result_hash == second.engineering_result_hash
    assert result_manifest["authority"]["reaction"] == "authoritative"
    assert result_manifest["authority"]["member_force"] == "authoritative"
    assert result_manifest["claim_boundary"]["engineering_design"] is False
    assert result_manifest["claim_boundary"]["commercial_claim"] is False
    assert operator_manifest["claim_boundary"]["result_authority"] is False
    assert "arrays" not in operator_manifest
    assert "vectors" not in result_manifest

    expected_reaction = np.zeros(12, dtype="<f8")
    expected_reaction[0] = -7.0
    np.testing.assert_array_equal(first.reaction_global_si, expected_reaction)
    np.testing.assert_array_equal(
        first.equilibrium_residual_global_si, np.zeros(12, dtype="<f8")
    )
    np.testing.assert_array_equal(
        first.member_local_end_force_si[0, 6:], fixture["reference_load"][6:]
    )
    assert first.free_residual_scaled_linf == 0.0
    assert first.element_balance_scaled_linf == 0.0
    assert first.reaction_global_si.flags.writeable is False
    with pytest.raises(ValueError):
        first.reaction_global_si.setflags(write=True)


def test_recovery_operator_rejects_numeric_load_and_element_law_mismatches() -> None:
    fixture = _fixture()
    values = np.array(fixture["global_values"], copy=True)
    values[0] += 1.0
    with pytest.raises(EngineeringRecoveryError) as numeric_error:
        create_linear_static_recovery_operator(
            execution_plan=fixture["plan"],
            equation_scaling=fixture["scaling"],
            reduced_csr=fixture["reduced"],
            global_csr_values_si=values,
            reference_external_load_global_si=fixture["reference_load"],
            element_kinematic_matrices=fixture["kinematic"],
            element_local_stiffness_matrices_si=fixture["local_stiffness"],
            element_result_profiles=(FRAME_LOCAL_END_FORCE_PROFILE,),
            recovery_law_receipt_hash=_hash("c"),
        )
    assert numeric_error.value.code == "recovery_operator_binding_mismatch"

    load = np.array(fixture["reference_load"], copy=True)
    load[6] += 1.0
    with pytest.raises(EngineeringRecoveryError) as load_error:
        create_linear_static_recovery_operator(
            execution_plan=fixture["plan"],
            equation_scaling=fixture["scaling"],
            reduced_csr=fixture["reduced"],
            global_csr_values_si=fixture["global_values"],
            reference_external_load_global_si=load,
            element_kinematic_matrices=fixture["kinematic"],
            element_local_stiffness_matrices_si=fixture["local_stiffness"],
            element_result_profiles=(FRAME_LOCAL_END_FORCE_PROFILE,),
            recovery_law_receipt_hash=_hash("c"),
        )
    assert load_error.value.code == "recovery_operator_binding_mismatch"

    local = np.array(fixture["local_stiffness"], copy=True)
    local[0, 6, 6] += 1.0
    with pytest.raises(EngineeringRecoveryError) as assembly_error:
        create_linear_static_recovery_operator(
            execution_plan=fixture["plan"],
            equation_scaling=fixture["scaling"],
            reduced_csr=fixture["reduced"],
            global_csr_values_si=fixture["global_values"],
            reference_external_load_global_si=fixture["reference_load"],
            element_kinematic_matrices=fixture["kinematic"],
            element_local_stiffness_matrices_si=local,
            element_result_profiles=(FRAME_LOCAL_END_FORCE_PROFILE,),
            recovery_law_receipt_hash=_hash("c"),
        )
    assert assembly_error.value.code == "recovery_operator_assembly_replay_failed"


def test_engineering_result_fails_closed_on_equilibrium_and_boundary_conditions() -> None:
    residual_fixture = _fixture(displacement_scale=0.9)
    with pytest.raises(EngineeringRecoveryError) as residual_error:
        create_engineering_result_ir(
            engineering_result_id="engineering.residual.invalid",
            numerical_result=residual_fixture["numerical"],
            recovery_operator=residual_fixture["operator"],
        )
    assert residual_error.value.code == "engineering_result_free_equilibrium_gate_failed"

    boundary_fixture = _fixture(constrained_displacement=0.01)
    with pytest.raises(EngineeringRecoveryError) as boundary_error:
        create_engineering_result_ir(
            engineering_result_id="engineering.boundary.invalid",
            numerical_result=boundary_fixture["numerical"],
            recovery_operator=boundary_fixture["operator"],
        )
    assert (
        boundary_error.value.code
        == "engineering_result_nonzero_prescribed_displacement_unsupported"
    )


def test_axial_profile_exposes_only_evaluated_local_force_components() -> None:
    fixture = _fixture(element_profile=AXIAL_LOCAL_END_FORCE_PROFILE)
    result = create_engineering_result_ir(
        engineering_result_id="engineering.axial.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )

    assert result.evaluated_member_force_value_count == 2
    assert result.member_local_end_force_si[0, 6] == pytest.approx(2.0)
    inactive = [index for index in range(12) if index not in (0, 6)]
    np.testing.assert_array_equal(
        result.member_local_end_force_si[0, inactive],
        np.zeros(10, dtype="<f8"),
    )

    invalid_local = np.array(fixture["local_stiffness"], copy=True)
    invalid_local[0, 1, 1] = 1.0
    with pytest.raises(EngineeringRecoveryError) as profile_error:
        create_linear_static_recovery_operator(
            execution_plan=fixture["plan"],
            equation_scaling=fixture["scaling"],
            reduced_csr=fixture["reduced"],
            global_csr_values_si=fixture["global_values"],
            reference_external_load_global_si=fixture["reference_load"],
            element_kinematic_matrices=fixture["kinematic"],
            element_local_stiffness_matrices_si=invalid_local,
            element_result_profiles=(AXIAL_LOCAL_END_FORCE_PROFILE,),
            recovery_law_receipt_hash=_hash("c"),
        )
    assert profile_error.value.code == "recovery_operator_axial_component_law_invalid"


def test_manifests_cannot_rehash_themselves_into_broader_authority() -> None:
    fixture = _fixture()
    result = create_engineering_result_ir(
        engineering_result_id="engineering.linear.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )
    operator_manifest = deepcopy(fixture["operator"].to_manifest())
    operator_manifest["claim_boundary"]["result_authority"] = True
    _rehash(operator_manifest, "recovery_operator_hash")
    with pytest.raises(EngineeringRecoveryError) as operator_error:
        validate_linear_static_recovery_operator_manifest(operator_manifest)
    assert operator_error.value.code == "recovery_operator_schema_invalid"

    result_manifest = deepcopy(result.to_manifest())
    result_manifest["authority"]["engineering_design"] = "authoritative"
    result_manifest["claim_boundary"]["engineering_design"] = True
    _rehash(result_manifest, "engineering_result_hash")
    with pytest.raises(EngineeringRecoveryError) as result_error:
        validate_engineering_result_ir_manifest(result_manifest)
    assert result_error.value.code == "engineering_result_schema_invalid"

    gate_manifest = deepcopy(result.to_manifest())
    gate_manifest["gates"]["free_residual_scaled_linf"] = 1.0
    _rehash(gate_manifest, "engineering_result_hash")
    with pytest.raises(EngineeringRecoveryError) as gate_error:
        validate_engineering_result_ir_manifest(gate_manifest)
    assert gate_error.value.code == "engineering_result_manifest_gate_failed"

    foreign_artifact_manifest = deepcopy(result.to_manifest())
    foreign_artifact_manifest["outputs"]["artifacts"][0]["artifact_uri"] = (
        "artifact://engine-v2/engineering-results/engineering.other/"
        "reaction_global.f64le"
    )
    _rehash(foreign_artifact_manifest, "engineering_result_hash")
    with pytest.raises(EngineeringRecoveryError) as artifact_uri_error:
        validate_engineering_result_ir_manifest(foreign_artifact_manifest)
    assert (
        artifact_uri_error.value.code
        == "engineering_result_descriptor_semantics_invalid"
    )


def test_engineering_result_artifacts_are_hash_bound_and_no_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()
    result = create_engineering_result_ir(
        engineering_result_id="engineering.linear.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )
    output = tmp_path / "artifacts"
    write_engineering_result_artifacts(result, output)
    for name, filename in (
        ("reaction_global_si", "reaction_global.f64le"),
        (
            "equilibrium_residual_global_si",
            "equilibrium_residual_global.f64le",
        ),
        ("member_local_end_force_si", "member_local_end_force.f64le"),
    ):
        restored = validate_engineering_result_artifact_bytes(
            result, name=name, data=(output / filename).read_bytes()
        )
        np.testing.assert_array_equal(restored, result.vector(name))

    tampered = bytearray((output / "reaction_global.f64le").read_bytes())
    tampered[-1] ^= 1
    with pytest.raises(EngineeringRecoveryError) as tamper_error:
        validate_engineering_result_artifact_bytes(
            result, name="reaction_global_si", data=tampered
        )
    assert tamper_error.value.code == "engineering_result_artifact_hash_mismatch"

    with pytest.raises(EngineeringRecoveryError) as overwrite_error:
        write_engineering_result_artifacts(result, output)
    assert overwrite_error.value.code == "engineering_result_artifact_target_exists"

    race_output = tmp_path / "race"
    race_target = race_output / "equilibrium_residual_global.f64le"
    first_target = race_output / "reaction_global.f64le"
    original_open = Path.open

    def racing_open(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path == race_target and mode == "xb" and not path.exists():
            with original_open(path, "wb") as winner:
                winner.write(b"concurrent-winner")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    with pytest.raises(EngineeringRecoveryError) as race_error:
        write_engineering_result_artifacts(result, race_output)
    assert race_error.value.code == "engineering_result_artifact_target_exists"
    assert not first_target.exists()
    assert race_target.read_bytes() == b"concurrent-winner"


def test_engineering_result_rejects_a_recovery_operator_from_another_plan() -> None:
    first = _fixture()
    second = _fixture(model_hash_character="d")
    with pytest.raises(EngineeringRecoveryError) as mismatch_error:
        create_engineering_result_ir(
            engineering_result_id="engineering.cross.binding.invalid",
            numerical_result=first["numerical"],
            recovery_operator=second["operator"],
        )
    assert mismatch_error.value.code == "engineering_result_recovery_source_mismatch"


def test_result_object_rejects_stale_gate_metrics() -> None:
    fixture = _fixture()
    result = create_engineering_result_ir(
        engineering_result_id="engineering.linear.lc1",
        numerical_result=fixture["numerical"],
        recovery_operator=fixture["operator"],
    )
    stale = replace(result, free_residual_scaled_linf=1.0)
    with pytest.raises(EngineeringRecoveryError) as error:
        stale.to_manifest()
    assert error.value.code == "engineering_result_gate_metric_mismatch"
