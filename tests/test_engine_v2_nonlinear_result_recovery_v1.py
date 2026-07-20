from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan import create_execution_plan
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
    plan = _plan()
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
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version="stateful-nonlinear-path.v1",
        source_solver_receipt_hash=_hash("6"),
        state_hash=committed_state.state_hash,
        material_state_bundle_hash=committed_bundle.bundle_hash,
        path_history_hash=_hash("7"),
        terminal_reason="converged_residual_and_increment",
        converged=True,
        final_residual_linf=1.0e-11,
        residual_tolerance_linf=1.0e-9,
        final_increment_linf=1.0e-12,
        increment_tolerance_linf=1.0e-10,
        accepted_step_count=3,
        rejected_attempt_count=1,
        rollback_count=1,
    )
    return plan, initial_state, committed_state, committed_bundle, terminal


def _result(**overrides):
    plan, _initial, state, bundle, terminal = _fixture()
    values = {
        "result_id": "result.nonlinear.nl1",
        "execution_plan": plan,
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


def test_nonlinear_result_binds_state_material_history_and_terminal_gate() -> None:
    first = _result()
    second = _result()
    manifest = first.to_manifest()
    assert first.authority_profile == NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE
    assert first.result_hash == second.result_hash
    assert manifest["authority"]["material_state"] == "authoritative"
    assert manifest["authority"]["reaction"] == "not_evaluated"
    assert manifest["claim_boundary"]["reaction_authority"] is False
    assert first.displacement_global_si.flags.writeable is False
    assert validate_nonlinear_result_manifest(manifest) == manifest


def test_terminal_receipt_fails_closed_on_any_promotion_gate() -> None:
    _plan_value, _initial, state, bundle, _terminal = _fixture()
    base = {
        "source_solver_schema_version": "stateful-nonlinear-path.v1",
        "source_solver_receipt_hash": _hash("6"),
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


def test_result_rejects_valid_material_bundle_bound_to_different_state() -> None:
    plan, initial_state, state, _bundle, terminal = _fixture()
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
    assert candidate.free_residual_linf == pytest.approx(0.0)
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
