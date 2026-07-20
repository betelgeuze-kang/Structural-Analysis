from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import create_execution_plan
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (
    create_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.nonlinear_recovery import (
    NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE,
    NonlinearRecoveryError,
    create_nonlinear_recovery_candidate,
    validate_nonlinear_recovery_candidate,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE,
    NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE,
    NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE,
    NonlinearResultIRError,
    create_nonlinear_numerical_result_ir,
    create_nonlinear_terminal_receipt,
    validate_nonlinear_displacement_bytes,
    validate_nonlinear_numerical_result_ir,
    validate_nonlinear_result_manifest,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _plan():
    dof_count = 12
    return create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="nonlinear-solver-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="NL1",
        operator_id="nonlinear-state-operator",
        operator_version="nonlinear-state-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=np.asarray(
            [-1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5],
            dtype="<i4",
        ),
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=np.arange(6, dtype="<i4"),
        free_dofs=np.arange(6, dof_count, dtype="<i4"),
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )


def _fixture():
    base_plan = _plan()
    coordinates = np.asarray(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        dtype="<f8",
    )
    reference_load = np.zeros(12, dtype="<f8")
    reference_load[6] = 10.0
    reference_load[11] = 4.0
    scaling = create_equation_scaling(
        execution_plan=base_plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base_plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=_hash("d"),
    )
    initial_state = create_initial_state(plan)
    displacement = np.zeros(12, dtype="<f8")
    displacement[6:] = np.asarray([0.01, -0.02, 0.0, 0.0, 0.0, 0.003])
    trial_state = open_trial_state(
        initial_state,
        displacement,
        load_step=3,
        iteration=5,
        load_factor=0.75,
        expected_plan=plan,
    )
    committed_state = commit_trial_state(
        initial_state,
        trial_state,
        expected_plan=plan,
    )
    initial_bundle = create_initial_material_state_bundle(
        bundle_id="material.initial",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=initial_state.state_hash,
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"initial-steel-state",
            ),
        ),
    )
    trial_bundle = open_trial_material_state_bundle(
        initial_bundle,
        solver_state_hash=trial_state.state_hash,
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"yielded-steel-state",
            ),
        ),
    )
    committed_bundle = commit_trial_material_state_bundle(
        initial_bundle,
        trial_bundle,
        solver_state_hash=committed_state.state_hash,
    )
    source_solution = immutable_array(
        committed_state.displacement_si[plan.array("free_dofs")],
        dtype="<f8",
    )
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version="stateful-nonlinear-path.v1",
        source_solver_receipt_hash=_hash("6"),
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=array_data_hash(source_solution),
        solver_coordinate_scaling_receipt_hash=_hash("e"),
        state_hash=committed_state.state_hash,
        material_state_bundle_hash=committed_bundle.bundle_hash,
        path_history_hash=_hash("7"),
        terminal_reason="converged_residual_and_increment",
        converged=True,
        final_residual_linf=1.0e-11,
        residual_tolerance_linf=1.0e-9,
        final_increment_linf=1.0e-12,
        increment_tolerance_linf=1.0e-10,
        accepted_step_count=1,
        rejected_attempt_count=1,
        rollback_count=1,
    )
    return (
        plan,
        scaling,
        reduced,
        initial_state,
        committed_state,
        committed_bundle,
        terminal,
    )


def _result(**overrides):
    plan, scaling, reduced, _initial, state, bundle, terminal = _fixture()
    values = {
        "result_id": "result.nonlinear.nl1",
        "execution_plan": plan,
        "equation_scaling": scaling,
        "reduced_csr": reduced,
        "committed_state": state,
        "material_state_bundle": bundle,
        "terminal_receipt": terminal,
        "full_residual_receipt_hash": _hash("8"),
        "boundary_condition_receipt_hash": _hash("9"),
        "backend_role": "cpu_reference",
        "backend_receipt_hash": _hash("a"),
    }
    values.update(overrides)
    return create_nonlinear_numerical_result_ir(**values)


def test_nonlinear_result_binds_terminal_material_state_and_terminal_gate() -> None:
    first = _result()
    second = _result()
    manifest = first.to_manifest()
    assert first.authority_profile == NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE
    assert first.result_hash == second.result_hash
    assert manifest["authority"]["material_state"] == "authoritative"
    assert manifest["authority"]["reaction"] == "not_evaluated"
    assert manifest["claim_boundary"]["reaction_authority"] is False
    assert manifest["claim_boundary"]["equation_scaling_replay_bound"] is True
    assert manifest["claim_boundary"]["reduced_csr_identity_bound"] is True
    assert manifest["claim_boundary"]["material_state_history_replayed"] is False
    assert first.displacement_global_si.flags.writeable is False
    with pytest.raises(ValueError):
        first.displacement_global_si.setflags(write=True)
    assert validate_nonlinear_result_manifest(manifest) == manifest


def test_terminal_receipt_binds_scaled_equations_coordinates_and_solution_bytes() -> (
    None
):
    plan, scaling, reduced, _initial, state, bundle, terminal = _fixture()
    payload = terminal.to_dict()
    assert payload["equation_scaling_hash"] == scaling.scaling_hash
    assert payload["reduced_csr_identity_hash"] == reduced.identity_hash
    assert payload["residual_norm_profile"] == NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE
    assert (
        payload["increment_norm_profile"] == NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE
    )

    wrong_solution_terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version=terminal.source_solver_schema_version,
        source_solver_receipt_hash=terminal.source_solver_receipt_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=_hash("f"),
        solver_coordinate_scaling_receipt_hash=(
            terminal.solver_coordinate_scaling_receipt_hash
        ),
        state_hash=state.state_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        path_history_hash=terminal.path_history_hash,
        terminal_reason=terminal.terminal_reason,
        converged=True,
        final_residual_linf=terminal.final_residual_linf,
        residual_tolerance_linf=terminal.residual_tolerance_linf,
        final_increment_linf=terminal.final_increment_linf,
        increment_tolerance_linf=terminal.increment_tolerance_linf,
        accepted_step_count=terminal.accepted_step_count,
        rejected_attempt_count=terminal.rejected_attempt_count,
        rollback_count=terminal.rollback_count,
    )
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_source_solution_state_mismatch",
    ):
        create_nonlinear_numerical_result_ir(
            result_id="result.nonlinear.wrong-solution",
            execution_plan=plan,
            equation_scaling=scaling,
            reduced_csr=reduced,
            committed_state=state,
            material_state_bundle=bundle,
            terminal_receipt=wrong_solution_terminal,
            full_residual_receipt_hash=_hash("8"),
            boundary_condition_receipt_hash=_hash("9"),
            backend_role="cpu_reference",
            backend_receipt_hash=_hash("a"),
        )


def test_terminal_receipt_fails_closed_on_any_promotion_gate() -> None:
    plan, scaling, reduced, _initial, state, bundle, _terminal = _fixture()
    source_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")],
        dtype="<f8",
    )
    base = {
        "source_solver_schema_version": "stateful-nonlinear-path.v1",
        "source_solver_receipt_hash": _hash("6"),
        "equation_scaling_hash": scaling.scaling_hash,
        "reduced_csr_identity_hash": reduced.identity_hash,
        "source_solution_data_hash": array_data_hash(source_solution),
        "solver_coordinate_scaling_receipt_hash": _hash("e"),
        "state_hash": state.state_hash,
        "material_state_bundle_hash": bundle.bundle_hash,
        "path_history_hash": _hash("7"),
        "terminal_reason": "converged_residual_and_increment",
        "converged": True,
        "final_residual_linf": 1.0e-11,
        "residual_tolerance_linf": 1.0e-9,
        "final_increment_linf": 1.0e-12,
        "increment_tolerance_linf": 1.0e-10,
        "accepted_step_count": 3,
    }
    for override in (
        {"final_residual_linf": 1.0e-6},
        {"final_increment_linf": 1.0e-6},
        {"fallback_count": 1},
        {"regularization_count": 1},
        {"accepted_step_count": 0},
    ):
        with pytest.raises(
            NonlinearResultIRError,
            match="nonlinear_terminal_gate_failed",
        ):
            create_nonlinear_terminal_receipt(**{**base, **override})

    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_terminal_history_count_invalid",
    ):
        create_nonlinear_terminal_receipt(
            **{
                **base,
                "rejected_attempt_count": 0,
                "rollback_count": 1,
            }
        )


def test_result_rejects_valid_material_bundle_bound_to_different_state() -> None:
    plan, scaling, reduced, initial_state, state, _bundle, terminal = _fixture()
    wrong_initial = create_initial_material_state_bundle(
        bundle_id="material.wrong.initial",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=initial_state.state_hash,
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"initial-steel-state",
            ),
        ),
    )
    wrong_trial = open_trial_material_state_bundle(
        wrong_initial,
        solver_state_hash=_hash("e"),
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="steel.combined-hardening",
                material_schema_version="steel-state.v1",
                state_bytes=b"yielded-steel-state",
            ),
        ),
    )
    wrong_committed = commit_trial_material_state_bundle(
        wrong_initial,
        wrong_trial,
        solver_state_hash=_hash("f"),
    )
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_material_bundle_binding_mismatch",
    ):
        create_nonlinear_numerical_result_ir(
            result_id="result.nonlinear.stale",
            execution_plan=plan,
            equation_scaling=scaling,
            reduced_csr=reduced,
            committed_state=state,
            material_state_bundle=wrong_committed,
            terminal_receipt=terminal,
            full_residual_receipt_hash=_hash("8"),
            boundary_condition_receipt_hash=_hash("9"),
            backend_role="cpu_reference",
            backend_receipt_hash=_hash("a"),
        )


def test_displacement_artifact_and_manifest_authority_are_fail_closed() -> None:
    result = _result()
    payload = result.displacement_global_si.tobytes(order="C")
    restored = validate_nonlinear_displacement_bytes(result, payload)
    np.testing.assert_array_equal(restored, result.displacement_global_si)
    tampered = bytearray(payload)
    tampered[-1] ^= 1
    with pytest.raises(NonlinearResultIRError, match="artifact_bytes_invalid"):
        validate_nonlinear_displacement_bytes(result, tampered)
    with pytest.raises(NonlinearResultIRError, match="artifact_hash_mismatch"):
        validate_nonlinear_displacement_bytes(result, bytes(tampered))

    manifest = deepcopy(result.to_manifest())
    manifest["authority"]["reaction"] = "authoritative"
    manifest["claim_boundary"]["reaction_authority"] = True
    unsigned = dict(manifest)
    unsigned.pop("result_hash")
    manifest["result_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_manifest_schema_invalid",
    ):
        validate_nonlinear_result_manifest(manifest)

    incoherent = deepcopy(result.to_manifest())
    incoherent["dof_count"] = 18
    unsigned = dict(incoherent)
    unsigned.pop("result_hash")
    incoherent["result_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_displacement_shape_mismatch",
    ):
        validate_nonlinear_result_manifest(incoherent)

    wrong_uri = deepcopy(result.to_manifest())
    wrong_uri["displacement_artifact"]["artifact_uri"] = (
        "artifact://nonlinear-result/wrong/displacement_global.f64le"
    )
    descriptor = wrong_uri["displacement_artifact"]
    descriptor["content_hash"] = canonical_hash(
        {key: value for key, value in descriptor.items() if key != "content_hash"}
    )
    unsigned = dict(wrong_uri)
    unsigned.pop("result_hash")
    wrong_uri["result_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_displacement_uri_invalid",
    ):
        validate_nonlinear_result_manifest(wrong_uri)


def test_retained_displacement_requires_immutable_bytes_backing() -> None:
    result = _result()
    owned = result.displacement_global_si.copy()
    owned.setflags(write=False)
    tampered = replace(result, _displacement_global_si=owned)
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_displacement_mutable",
    ):
        validate_nonlinear_numerical_result_ir(tampered)


def test_recovery_candidate_partitions_reaction_but_remains_non_authoritative() -> None:
    result = _result()
    external = np.zeros(12, dtype="<f8")
    external[6] = 10.0
    external[11] = 4.0
    internal = external.copy()
    internal[0] = -10.0
    internal[5] = -4.0
    candidate = create_nonlinear_recovery_candidate(
        recovery_id="recovery.nonlinear.nl1",
        nonlinear_result=result,
        global_external_force_si=external,
        global_internal_force_si=internal,
        element_global_dofs=np.arange(12, dtype="<i8").reshape(1, 12),
        element_internal_force_si=internal.reshape(1, 12),
        member_axial_force_si=np.asarray([-10.0], dtype="<f8"),
        recovery_law_receipt_hash=_hash("b"),
    )
    manifest = candidate.to_manifest()
    assert candidate.authority_profile == NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE
    assert manifest["authority"]["reaction"] == "candidate_not_authoritative"
    assert manifest["claim_boundary"]["reaction_authority"] is False
    assert (
        manifest["claim_boundary"]["element_global_assembly_equation_scaling_bound"]
        is True
    )
    assert manifest["claim_boundary"]["free_equation_scaling_bound"] is True
    assert candidate.free_scaled_residual_linf == pytest.approx(0.0)
    assert candidate.reaction_global_si[0] == pytest.approx(-10.0)
    assert candidate.reaction_global_si[5] == pytest.approx(-4.0)
    validate_nonlinear_recovery_candidate(candidate)


def test_recovery_rejects_assembly_free_residual_and_authority_promotion() -> None:
    result = _result()
    zeros = np.zeros(12, dtype="<f8")
    dofs = np.arange(12, dtype="<i8").reshape(1, 12)
    mismatch = np.zeros((1, 12), dtype="<f8")
    mismatch[0, 0] = 1.0
    with pytest.raises(
        NonlinearRecoveryError,
        match="element_assembly_failed",
    ):
        create_nonlinear_recovery_candidate(
            recovery_id="recovery.mismatch",
            nonlinear_result=result,
            global_external_force_si=zeros,
            global_internal_force_si=zeros,
            element_global_dofs=dofs,
            element_internal_force_si=mismatch,
            member_axial_force_si=np.asarray([0.0]),
            recovery_law_receipt_hash=_hash("b"),
        )

    large_internal = zeros.copy()
    large_internal[0] = 1.0e12
    large_internal[5] = 1.0
    masked_moment_error = large_internal.reshape(1, 12).copy()
    masked_moment_error[0, 5] = 0.0
    with pytest.raises(
        NonlinearRecoveryError,
        match="element_assembly_failed",
    ):
        create_nonlinear_recovery_candidate(
            recovery_id="recovery.mixed-unit-mismatch",
            nonlinear_result=result,
            global_external_force_si=zeros,
            global_internal_force_si=large_internal,
            element_global_dofs=dofs,
            element_internal_force_si=masked_moment_error,
            member_axial_force_si=np.asarray([0.0]),
            recovery_law_receipt_hash=_hash("b"),
        )

    external = zeros.copy()
    internal = zeros.copy()
    external[6] = 1.0
    internal[6] = 2.0
    with pytest.raises(
        NonlinearRecoveryError,
        match="free_equilibrium_failed",
    ):
        create_nonlinear_recovery_candidate(
            recovery_id="recovery.residual",
            nonlinear_result=result,
            global_external_force_si=external,
            global_internal_force_si=internal,
            element_global_dofs=dofs,
            element_internal_force_si=internal.reshape(1, 12),
            member_axial_force_si=np.asarray([0.0]),
            recovery_law_receipt_hash=_hash("b"),
        )

    candidate = create_nonlinear_recovery_candidate(
        recovery_id="recovery.zero",
        nonlinear_result=result,
        global_external_force_si=zeros,
        global_internal_force_si=zeros,
        element_global_dofs=dofs,
        element_internal_force_si=np.zeros((1, 12), dtype="<f8"),
        member_axial_force_si=np.asarray([0.0]),
        recovery_law_receipt_hash=_hash("b"),
    )
    promoted = replace(candidate, authority_profile="authoritative_recovery")
    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_authority_profile_invalid",
    ):
        validate_nonlinear_recovery_candidate(promoted)


def test_nonlinear_result_authority_profile_cannot_be_promoted() -> None:
    result = _result()
    promoted = replace(
        result,
        authority_profile="authoritative_nonlinear_engineering_result",
    )
    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_authority_profile_invalid",
    ):
        validate_nonlinear_numerical_result_ir(promoted)
