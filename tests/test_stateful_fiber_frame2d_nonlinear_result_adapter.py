from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY,
    FiberFrameNonlinearResultAdapterError,
    create_fiber_frame_nonlinear_numerical_result_adapter,
    validate_fiber_frame_nonlinear_numerical_result_adapter,
    validate_fiber_frame_nonlinear_result_adapter_manifest,
    validate_fiber_frame_nonlinear_result_source_binding,
    validate_fiber_frame_nonlinear_result_source_binding_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.nonlinear_recovery import (
    NonlinearRecoveryError,
    create_nonlinear_recovery_candidate,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY,
    NonlinearResultIRError,
    validate_nonlinear_numerical_result_ir,
)
from tests.test_stateful_fiber_frame2d_nonlinear_terminal_receipt import _artifacts


def _hash(character: str) -> str:
    return "sha256:" + character * 64


@pytest.fixture(scope="module")
def artifacts():
    (
        problem,
        path,
        checkpoints,
        plan,
        scaling,
        kinematic,
        material,
        execution_state,
        terminal,
    ) = _artifacts()
    adapter = create_fiber_frame_nonlinear_numerical_result_adapter(
        problem,
        plan,
        scaling,
        checkpoints,
        kinematic,
        material,
        execution_state,
        path,
        terminal,
    )
    return (
        problem,
        path,
        checkpoints,
        plan,
        scaling,
        kinematic,
        material,
        execution_state,
        terminal,
        adapter,
    )


@pytest.fixture(scope="module")
def manifest(artifacts):
    return artifacts[-1].to_manifest()


def test_adapter_issues_exact_bounded_numerical_result(artifacts) -> None:
    (
        problem,
        path,
        checkpoints,
        plan,
        scaling,
        kinematic,
        material,
        execution_state,
        terminal,
        adapter,
    ) = artifacts
    source = adapter.source_binding
    result = adapter.numerical_result
    final_state = kinematic.committed_states[-1]

    assert source.problem_contract_hash == problem.contract_hash
    assert source.execution_topology_plan_hash == plan.plan_hash
    assert source.physical_equation_scaling_binding_hash == scaling.binding_hash
    assert source.checkpoint_chain_hash == checkpoints.chain_hash
    assert source.execution_state_binding_hash == execution_state.binding_hash
    assert source.terminal_receipt_hash == terminal.terminal_receipt_hash
    assert source.terminal_epoch == source.accepted_step_count == len(path.steps) == 4
    assert source.terminal_load_factor == 1.0
    assert source.residual_gate_passed is True
    assert source.increment_gate_passed is True
    assert source.convergence_gate_passed is True
    assert source.backend_receipt.fallback_count == 0
    assert source.backend_receipt.regularization_count == 0
    assert result._source_adapter is source
    assert result._execution_plan is None
    assert result._committed_state is None
    assert result.state_hash == final_state.state_hash
    assert (
        result.material_state_bundle_hash == material.projections[-1].bundle.bundle_hash
    )
    assert result.nonlinear_terminal_hash == terminal.terminal_receipt_hash
    assert result.load_factor == 1.0
    np.testing.assert_array_equal(
        result.displacement_global_si,
        final_state.array("canonical_displacement_si"),
    )
    assert result.displacement_global_si.flags.writeable is False
    with pytest.raises(ValueError):
        result.displacement_global_si.setflags(write=True)


def test_adapter_manifest_is_strict_descriptor_only_and_exactly_bound(
    manifest,
) -> None:
    normalized = validate_fiber_frame_nonlinear_result_adapter_manifest(manifest)
    source = normalized["source_binding"]
    result = normalized["numerical_result"]

    assert normalized["claim_boundary"] == dict(
        FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY
    )
    assert result["claim_boundary"] == dict(NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY)
    assert source["state_ir_usage_profile"] == FIBER_FRAME_STATE_IR_USAGE_PROFILE
    assert source["terminal"]["solver_residual_tolerance"] == 1.0e-10
    assert source["terminal"]["solver_increment_tolerance_m"] == 1.0e-12
    assert (
        result["bindings"]["state_hash"]
        == source["bindings"]["terminal_kinematic_state_hash"]
    )
    assert (
        result["displacement_artifact"]["data_hash"]
        == source["terminal"]["displacement_data_hash"]
    )
    encoded = json.dumps(normalized, sort_keys=True)
    assert "canonical_displacement_si" not in encoded
    assert "constituent_state_bytes" not in encoded
    assert "raw_customer_payload" not in encoded


def test_same_source_replays_to_same_adapter_and_result_hash(artifacts) -> None:
    *sources, first = artifacts
    problem, path, checkpoints, plan, scaling, kinematic, material, state, terminal = (
        sources
    )
    second = create_fiber_frame_nonlinear_numerical_result_adapter(
        problem,
        plan,
        scaling,
        checkpoints,
        kinematic,
        material,
        state,
        path,
        terminal,
    )

    assert second.adapter_hash == first.adapter_hash
    assert second.source_binding.binding_hash == first.source_binding.binding_hash
    assert second.numerical_result.result_hash == first.numerical_result.result_hash


def test_in_memory_source_and_result_tampering_fail_closed(artifacts) -> None:
    adapter = artifacts[-1]
    source = adapter.source_binding
    bad_backend = replace(source.backend_receipt, fallback_count=1)
    with pytest.raises(
        FiberFrameNonlinearResultAdapterError,
        match="fiber_frame_result_backend_fallback_forbidden",
    ):
        validate_fiber_frame_nonlinear_result_source_binding_shape(
            replace(source, backend_receipt=bad_backend)
        )

    with pytest.raises(
        NonlinearResultIRError,
        match="nonlinear_result_binding_mismatch",
    ):
        validate_nonlinear_numerical_result_ir(
            replace(adapter.numerical_result, state_hash=_hash("e"))
        )


def test_manifest_rejects_nested_extension_and_rehashed_cross_binding_tamper(
    manifest,
) -> None:
    extra = deepcopy(manifest)
    extra["source_binding"]["receipts"]["backend"]["backend"]["unexpected"] = True
    with pytest.raises(
        FiberFrameNonlinearResultAdapterError,
        match="fiber_frame_result_manifest_keys_invalid",
    ):
        validate_fiber_frame_nonlinear_result_adapter_manifest(extra)

    changed = deepcopy(manifest)
    backend = changed["source_binding"]["receipts"]["backend"]
    backend["bindings"]["execution_operator_hash"] = _hash("f")
    backend["receipt_hash"] = canonical_hash(
        {key: value for key, value in backend.items() if key != "receipt_hash"}
    )
    source = changed["source_binding"]
    source["binding_hash"] = canonical_hash(
        {key: value for key, value in source.items() if key != "binding_hash"}
    )
    changed["adapter_hash"] = canonical_hash(
        {key: value for key, value in changed.items() if key != "adapter_hash"}
    )
    with pytest.raises(
        FiberFrameNonlinearResultAdapterError,
        match="fiber_frame_result_source_manifest_receipt_binding_mismatch",
    ):
        validate_fiber_frame_nonlinear_result_adapter_manifest(changed)


def test_source_replay_and_adapter_validation_are_authoritative(artifacts) -> None:
    adapter = artifacts[-1]

    assert (
        validate_fiber_frame_nonlinear_result_source_binding(adapter.source_binding)
        is adapter.source_binding
    )
    assert validate_fiber_frame_nonlinear_numerical_result_adapter(adapter) is adapter


def test_generic_recovery_rejects_adapter_bound_result_until_exact_recovery(
    artifacts,
) -> None:
    result = artifacts[-1].numerical_result
    zeros = np.zeros(result.dof_count, dtype="<f8")
    dofs = np.arange(result.dof_count, dtype="<i8").reshape(1, -1)

    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_source_profile_unsupported",
    ):
        create_nonlinear_recovery_candidate(
            recovery_id="recovery.fiber-frame.blocked",
            nonlinear_result=result,
            global_external_force_si=zeros,
            global_internal_force_si=zeros,
            element_global_dofs=dofs,
            element_internal_force_si=zeros.reshape(1, -1),
            member_axial_force_si=np.zeros(1, dtype="<f8"),
            recovery_law_receipt_hash=_hash("a"),
        )
