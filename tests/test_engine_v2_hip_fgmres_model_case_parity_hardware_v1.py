"""Actual-gfx1030 CPU/HIP parity for one completed FGMRES model case."""

from __future__ import annotations

import os

from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    open_hip_fgmres_completion_export_context_v1,
    validate_hip_fgmres_completion_export_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    attest_hip_fgmres_model_case_parity_v1,
    validate_hip_fgmres_model_case_parity_receipt_v1,
    validate_hip_fgmres_model_case_parity_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v1 import (
    attest_hip_fgmres_model_family_coverage_v1,
    validate_hip_fgmres_model_family_parity_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    build_hip_fgmres_result_ir_v2,
    validate_hip_fgmres_result_ir_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    observe_hip_fgmres_terminal_outcome_v1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    attest_hip_device_identity_v1,
    validate_hip_device_identity_result_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)

from tests.test_engine_v2_hip_fgmres_global_recurrence_context_hardware_v1 import (
    _serial_cantilever_model,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_CASE_PARITY_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_RESULT_IR_HARDWARE",
        )
    )


def test_native_gfx1030_later_column_convergence_attests_exact_model_case_parity() -> (
    None
):
    result_ir_bridge = None
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = _serial_cantilever_model(3)
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=2,
        absolute_tolerance=0.0,
        relative_tolerance=1.0e-15,
    )
    chain, predecessor_capability = _open_canonical_chain(
        model=model,
        architecture=architecture,
        required=required,
        policy=policy,
    )
    sealed = global_open = export_context = None
    try:
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        global_pending = global_open.context.enqueue_remaining_global_recurrence()
        completion = global_open.context.synchronize(global_pending)

        opened = open_hip_fgmres_completion_export_context_v1(
            global_open.context,
            completion,
        )
        assert opened.ready
        export_context = opened.context
        export_result = export_context.export_completion_buffers()
        validate_hip_fgmres_completion_export_result_v1(
            export_result,
            expected_context=export_context,
        )
        observation = observe_hip_fgmres_terminal_outcome_v1(
            export_result,
            expected_export_context=export_context,
        )
        validate_hip_fgmres_terminal_outcome_observation_result_v1(
            observation,
            expected_export_result=export_result,
            expected_export_context=export_context,
        )
        assert observation.receipt.status == "terminal_converged"
        assert observation.outcome.terminal_status == "converged"
        assert observation.outcome.termination_code == "converged_happy_breakdown"
        assert observation.outcome.counters.effective_iterations == 2
        assert observation.outcome.counters.effective_restarts == 1
        assert observation.outcome.restart_rows[0].arnoldi_step_count == 2

        source_fgmres_plan = chain.recurrence._source_fgmres_plan
        source_execution_plan = source_fgmres_plan._source_execution_plan
        cpu_result = solve_cpu_fgmres_reference_v1(
            source_execution_plan,
            source_fgmres_plan.policy,
        )
        assert cpu_result.status == "converged"
        assert cpu_result.termination_code == "converged_happy_breakdown"
        assert cpu_result.iteration_count == 2
        assert cpu_result.restart_count == 1
        assert cpu_result.history[0].arnoldi_step_count == 2

        loaded_runtime = chain.live._loaded_runtime
        assert loaded_runtime is not None
        device_identity = attest_hip_device_identity_v1(
            loaded_runtime,
            device_ordinal=0,
            expected_compiled_architecture=architecture,
        )
        validate_hip_device_identity_result_v1(
            device_identity,
            expected_loaded_runtime=loaded_runtime,
        )
        assert device_identity.receipt.actual_backend == "hip"
        assert device_identity.receipt.architecture.runtime.base == "gfx1030"

        parity = attest_hip_fgmres_model_case_parity_v1(
            cpu_result,
            observation,
            device_identity,
        )
        validate_hip_fgmres_model_case_parity_result_v1(
            parity,
            expected_cpu_result=cpu_result,
            expected_observation_result=observation,
            expected_device_identity_result=device_identity,
        )
        result_ir_bridge = build_hip_fgmres_result_ir_v2(parity)
        validate_hip_fgmres_result_ir_v2(result_ir_bridge)
        assert result_ir_bridge.source_execution_plan is source_execution_plan
        assert result_ir_bridge.receipt.source_provenance.actual_backend == "hip"
        assert result_ir_bridge.receipt.claims.result_ir_verified
        assert result_ir_bridge.receipt.claims.result_ir_ready
        assert not parity.receipt.claims.solution_ready
        assert not parity.receipt.claims.result_ir_ready
        receipt = parity.receipt
        validate_hip_fgmres_model_case_parity_receipt_v1(receipt)

        assert receipt.status == "case_parity_verified"
        assert receipt.actual_backend == "hip"
        assert not receipt.promotion_eligible
        assert receipt.bindings.execution_plan_hash == source_execution_plan.plan_hash
        assert receipt.bindings.policy_hash == source_fgmres_plan.policy.policy_hash
        assert receipt.bindings.terminal_observation_receipt_hash == (
            observation.receipt.receipt_hash
        )
        assert receipt.bindings.device_identity_receipt_hash == (
            device_identity.receipt.receipt_hash
        )
        assert receipt.bindings.compiled_architecture == architecture
        assert receipt.bindings.runtime_architecture_base == "gfx1030"
        assert receipt.bindings.device_ordinal == 0
        assert receipt.bindings.retained_execution_plan_snapshot_identity_verified
        assert receipt.bindings.process_local_runtime_identity_verified
        assert not receipt.bindings.process_local_identities_serialized

        assert receipt.dimensions.global_dof_count == 18
        assert receipt.dimensions.free_dof_count == 12
        assert receipt.dimensions.restart_dimension == 2
        assert receipt.dimensions.max_iterations == 2
        assert receipt.dimensions.maximum_restart_count == 1
        assert receipt.dimensions.populated_restart_row_count == 1
        assert all(receipt.discrete.to_dict().values())
        assert tuple(row.name for row in receipt.vectors) == (
            "solution_x",
            "true_residual",
            "true_residual_replay",
        )
        assert all(row.componentwise_tolerance_passed for row in receipt.vectors)
        assert all(row.maximum_tolerance_ratio <= 1.0 for row in receipt.vectors)
        assert receipt.telemetry.independent_true_residual_replay_count == 1
        assert receipt.telemetry.additional_d2h_operation_count == 0
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.device_allocation_count == 0
        assert receipt.telemetry.kernel_launch_count == 0
        assert receipt.telemetry.explicit_stream_sync_count == 0
        assert receipt.telemetry.fallback_count == 0

        assert receipt.claims.exact_retained_execution_plan_snapshot_bound
        assert receipt.claims.deterministic_cpu_reference_replayed
        assert receipt.claims.actual_hip_backend_verified
        assert receipt.claims.runtime_device_identity_verified
        assert receipt.claims.terminal_outcome_parity_verified
        assert receipt.claims.solution_vector_parity_verified
        assert receipt.claims.exported_residual_parity_verified
        assert receipt.claims.independent_operator_residual_replay_verified
        assert receipt.claims.single_model_case_numerical_parity_verified
        assert not receipt.claims.full_model_family_parity_verified
        assert not receipt.claims.multi_architecture_parity_verified
        assert not receipt.claims.iteration_host_copy_zero_proven
        assert not receipt.claims.solution_ready
        assert not receipt.claims.result_ir_ready
        assert not receipt.claims.performance_or_speedup_proven
        assert not receipt.claims.commercial_ready
        assert not receipt.claims.promotion_eligible

        family = attest_hip_fgmres_model_family_coverage_v1((parity,))
        validate_hip_fgmres_model_family_parity_result_v1(
            family,
            expected_case_results=(parity,),
        )
        family_receipt = family.receipt
        assert family_receipt.status == "pending_model_cases_and_external_architecture"
        assert family_receipt.coverage.validated_input_case_count == 1
        assert family_receipt.coverage.registered_input_case_count == 0
        assert family_receipt.coverage.unregistered_input_case_count == 1
        assert family_receipt.coverage.expected_matrix_cell_count == 20
        assert family_receipt.coverage.covered_matrix_cell_count == 0
        assert len(family_receipt.coverage.missing_cells) == 20
        assert family_receipt.coverage.observed_architecture_bases == ("gfx1030",)
        family_claims = family_receipt.claims
        assert family_claims.fixed_package_suite_manifest_bound
        assert family_claims.authoritative_execution_plan_metadata_classification
        assert family_claims.all_submitted_exact_case_results_replayed
        assert family_claims.architecture_key_is_normalized_runtime_base
        assert family_claims.duplicate_logical_slot_architecture_cells_rejected
        assert not family_claims.fixed_suite_slot_registration_complete
        assert not family_claims.fixed_suite_matrix_complete
        assert not family_claims.full_model_family_parity_verified
        assert not family_claims.multi_architecture_parity_verified
        assert not family_claims.same_process_actual_two_isa_verified
        assert not family_claims.result_ir_ready
        assert not family_claims.performance_or_speedup_proven
        assert not family_claims.signed_evidence
        assert not family_claims.commercial_ready
        assert not family_claims.promotion_eligible
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()

    assert result_ir_bridge is not None
    assert validate_hip_fgmres_result_ir_v2(result_ir_bridge) is result_ir_bridge
