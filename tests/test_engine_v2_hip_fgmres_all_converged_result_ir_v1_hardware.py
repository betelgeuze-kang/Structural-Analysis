"""Actual-gfx1030 all-converged 10/10 ResultIR v1 hardware gate."""

from __future__ import annotations

import ast
import inspect
import os
import sys
from pathlib import Path
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_model_family_v1 import (
    attest_hip_fgmres_all_converged_model_family_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_result_ir_v1 import (
    attest_hip_fgmres_all_converged_result_ir_v1,
    validate_hip_fgmres_all_converged_result_ir_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    build_hip_fgmres_result_ir_v2,
    validate_hip_fgmres_result_ir_v2,
)

from tests.test_engine_v2_hip_fgmres_model_family_parity_v2_hardware import (
    _attach_cleanup_failures,
    _execute_live_case,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
)


_REQUIRED_ENV = "ENGINE_V2_REQUIRE_HIP_FGMRES_ALL_CONVERGED_RESULT_IR_V1_HARDWARE"
_LINUX_PROCESS_STATUS = Path("/proc/self/status")


def _hardware_required() -> bool:
    return (
        os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
        or os.environ.get(_REQUIRED_ENV) == "1"
    )


def _linux_process_rss_kib() -> tuple[int, int]:
    """Return current and high-water resident memory for this Linux process."""
    fields: dict[str, int] = {}
    for line in _LINUX_PROCESS_STATUS.read_text(encoding="ascii").splitlines():
        name, separator, value = line.partition(":")
        if not separator or name not in {"VmRSS", "VmHWM"}:
            continue
        parts = value.split()
        assert len(parts) == 2
        assert parts[1] == "kB"
        fields[name] = int(parts[0])
    assert set(fields) == {"VmRSS", "VmHWM"}
    assert 0 < fields["VmRSS"] <= fields["VmHWM"]
    return fields["VmRSS"], fields["VmHWM"]


def _emit_rss_checkpoint(
    *,
    phase: str,
    previous_peak_rss_kib: int | None,
) -> int:
    current_rss_kib, peak_rss_kib = _linux_process_rss_kib()
    peak_delta_kib = (
        0 if previous_peak_rss_kib is None else peak_rss_kib - previous_peak_rss_kib
    )
    assert peak_delta_kib >= 0
    print(
        "actual-gfx1030 all-converged rss: "
        f"phase={phase} current_rss_kib={current_rss_kib} "
        f"cumulative_peak_rss_kib={peak_rss_kib} "
        f"peak_delta_kib={peak_delta_kib}",
        flush=True,
    )
    return peak_rss_kib


def _assert_converged_case_and_single_export(
    *,
    slot: Any,
    case: Any,
    audit_context: Any,
) -> int:
    cpu = case._cpu_result
    observation = case._observation_result
    receipt = case.receipt

    assert cpu.result_hash == slot.cpu_result.result_hash
    assert cpu.status == "converged"
    assert cpu.solver_tolerance_passed is True
    assert cpu.authoritative_plan_tolerance_passed is True
    assert observation.receipt.status == "terminal_converged"
    assert observation.outcome.terminal_status == "converged"
    assert receipt.actual_backend == "hip"
    assert all(receipt.discrete.to_dict().values())
    assert all(row.componentwise_tolerance_passed for row in receipt.vectors)
    assert receipt.telemetry.cpu_reference_result_count == 1
    assert receipt.telemetry.hip_terminal_observation_result_count == 1
    assert receipt.telemetry.fallback_count == 0

    audit_result = audit_context.result
    assert audit_result is not None
    audit_receipt = audit_result.receipt
    assert audit_receipt.claims.recurrence_program_bound_runtime_copy_attempt_zero
    assert audit_receipt.claims.post_fence_exact_three_blocking_d2h
    recurrence = audit_receipt.window.recurrence_program
    assert recurrence.h2d_async.attempt_count == 0
    assert recurrence.d2h_async.attempt_count == 0
    assert recurrence.d2h_blocking.attempt_count == 0
    export_phase = audit_receipt.window.completion_export
    assert export_phase.h2d_async.attempt_count == 0
    assert export_phase.d2h_async.attempt_count == 0
    assert export_phase.d2h_blocking.attempt_count == 3
    assert export_phase.d2h_blocking.success_count == 3
    assert export_phase.d2h_blocking.failure_count == 0
    assert (
        export_phase.d2h_blocking.bytes_attempted,
        export_phase.d2h_blocking.bytes_succeeded,
    ) == (
        audit_receipt.dimensions.total_export_byte_count,
        audit_receipt.dimensions.total_export_byte_count,
    )
    export = audit_result.completion_export_result.receipt
    assert export.telemetry.completion_capability_consume_count == 1
    assert export.telemetry.d2h_operation_attempt_count == 3
    assert export.telemetry.d2h_operation_success_count == 3
    assert export.telemetry.fallback_count == 0
    assert (
        audit_receipt.dimensions.total_export_byte_count
        == export.dimensions.total_export_byte_count
    )
    return audit_receipt.dimensions.total_export_byte_count


def test_hardware_flow_has_exact_four_full_registry_replay_bound() -> None:
    tree = ast.parse(
        inspect.getsource(
            test_native_gfx1030_all_converged_ten_result_ir_in_one_live_aggregate
        )
    )
    replaying_calls = {
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        "attest_hip_fgmres_all_converged_model_family_v1",
        "attest_hip_fgmres_all_converged_result_ir_v1",
        "validate_hip_fgmres_all_converged_result_ir_result_v1",
    }
    observed = tuple(
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in replaying_calls
    )
    assert len(observed) == 4
    assert set(observed) == replaying_calls


def test_native_gfx1030_all_converged_ten_result_ir_in_one_live_aggregate() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    registry = load_hip_fgmres_all_converged_fixture_registry_v1()

    resources: list[Any] = []
    cases: list[Any] = []
    bridges: list[Any] = []
    family = None
    aggregate = None
    observed_upstream_export_byte_count = 0
    peak_rss_kib = _emit_rss_checkpoint(
        phase="baseline_after_registry_replay",
        previous_peak_rss_kib=None,
    )
    try:
        for slot_id in HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1:
            print(f"actual-gfx1030 all-converged cell: {slot_id}", flush=True)
            slot = registry.slot(slot_id)
            assert slot.cpu_result.status == "converged"
            assert slot.cpu_result.solver_tolerance_passed is True
            assert slot.cpu_result.authoritative_plan_tolerance_passed is True

            opened, case, audit_context, _ordinal_context = _execute_live_case(
                slot,
                architecture,
                required,
            )
            resources.append(opened)
            cases.append(case)
            observed_upstream_export_byte_count += (
                _assert_converged_case_and_single_export(
                    slot=slot,
                    case=case,
                    audit_context=audit_context,
                )
            )

            bridge = build_hip_fgmres_result_ir_v2(
                case,
                result_id=f"Result.hip-fgmres-all-converged.{slot_id}.v2",
            )
            assert validate_hip_fgmres_result_ir_v2(bridge) is bridge
            assert bridge.receipt.claims.result_ir_verified
            assert bridge.receipt.claims.result_ir_ready
            assert bridge.receipt.source_provenance.actual_backend == "hip"
            assert (
                bridge.receipt.source_provenance.runtime_architecture_base == "gfx1030"
            )
            assert (
                bridge.receipt.source_provenance.additional_device_operation_count == 0
            )
            assert bridge.receipt.source_provenance.additional_d2h_operation_count == 0
            assert bridge.receipt.source_provenance.additional_solve_count == 0
            assert bridge.receipt.source_provenance.additional_export_count == 0
            assert bridge.receipt.source_provenance.fallback_count == 0
            bridges.append(bridge)
            peak_rss_kib = _emit_rss_checkpoint(
                phase=f"case_complete:{slot_id}",
                previous_peak_rss_kib=peak_rss_kib,
            )

        assert len(cases) == 10
        assert len(bridges) == 10
        family = attest_hip_fgmres_all_converged_model_family_v1(tuple(cases))
        family_receipt = family.receipt
        assert family_receipt.status == (
            "exact_gfx1030_all_converged_ten_slot_family_verified"
        )
        assert tuple(row.slot_id for row in family_receipt.observations) == (
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        )
        family_totals = family_receipt.totals
        assert family_totals.required_slot_count == 10
        assert family_totals.validated_live_case_count == 10
        assert family_totals.converged_case_count == 10
        assert family_totals.solver_tolerance_passed_count == 10
        assert family_totals.authoritative_plan_tolerance_passed_count == 10
        assert family_totals.unique_model_ir_count == 10
        assert family_totals.unique_execution_plan_count == 10
        assert family_totals.unique_case_count == 10
        plans = tuple(
            registry.slot(slot_id).execution_plan
            for slot_id in HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        )
        assert family_totals.package_global_dof_count == sum(
            plan.dof_count for plan in plans
        )
        assert family_totals.package_element_count == sum(
            plan.element_count for plan in plans
        )
        assert family_totals.package_free_dof_count == sum(
            len(plan.free_dofs) for plan in plans
        )
        assert family_totals.package_csr_nnz == sum(plan.nnz for plan in plans)
        assert (
            family_totals.package_global_dof_count,
            family_totals.package_element_count,
            family_totals.package_free_dof_count,
            family_totals.package_csr_nnz,
        ) == (168, 18, 103, 2304)
        family_claims = family_receipt.claims
        assert family_claims.fixed_all_converged_package_registry_replayed
        assert family_claims.exact_ten_registered_slots_verified
        assert family_claims.exact_ten_live_case_authorities_replayed
        assert family_claims.canonical_registry_order_verified
        assert family_claims.ten_unique_model_ir_verified
        assert family_claims.all_cpu_reference_converged
        assert family_claims.all_solver_tolerance_passed
        assert family_claims.all_authoritative_plan_tolerance_passed
        assert family_claims.exact_gfx1030_family_authority_issued
        assert not family_claims.result_ir_verified
        assert not family_claims.external_gfx1100_verified
        assert not family_claims.signed_evidence
        assert not family_claims.performance_or_speedup_proven
        assert not family_claims.end_to_end_o_n_verified
        assert not family_claims.commercial_ready
        assert not family_receipt.promotion_eligible
        peak_rss_kib = _emit_rss_checkpoint(
            phase="family_complete",
            previous_peak_rss_kib=peak_rss_kib,
        )
        aggregate = attest_hip_fgmres_all_converged_result_ir_v1(
            family,
            tuple(reversed(bridges)),
        )
        aggregate_receipt = aggregate.receipt
        assert aggregate_receipt.status == (
            "exact_gfx1030_all_converged_ten_slot_result_ir_v2_verified"
        )
        assert aggregate_receipt.actual_backend == "hip"
        assert not aggregate_receipt.promotion_eligible
        observations = aggregate_receipt.observations
        assert tuple(row.slot_id for row in observations) == (
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        )
        assert aggregate.result_ir_bridges == tuple(bridges)
        assert all(
            row.cpu_status == "converged"
            and row.solver_tolerance_passed is True
            and row.authoritative_plan_tolerance_passed is True
            and row.disposition == "ready_result_ir_v2"
            and row.compiled_architecture == "gfx1030"
            and row.runtime_architecture_base == "gfx1030"
            and row.result_array_count == 6
            and row.additional_device_operation_count == 0
            and row.additional_d2h_operation_count == 0
            and row.additional_solve_count == 0
            and row.additional_export_count == 0
            and row.fallback_count == 0
            for row in observations
        )
        aggregate_totals = aggregate_receipt.totals
        assert (
            aggregate_totals.required_slot_count,
            aggregate_totals.ready_result_ir_v2_count,
            aggregate_totals.solution_ready_count,
            aggregate_totals.not_issued_count,
            aggregate_totals.diagnostic_ir_count,
            aggregate_totals.unique_result_ir_bridge_count,
            aggregate_totals.committed_state_count,
        ) == (10, 10, 10, 0, 0, 10, 10)
        assert (
            aggregate_totals.package_global_dof_count
            == family_totals.package_global_dof_count
        )
        assert (
            aggregate_totals.package_element_count
            == family_totals.package_element_count
        )
        assert (
            aggregate_totals.package_free_dof_count
            == family_totals.package_free_dof_count
        )
        assert aggregate_totals.package_csr_nnz == family_totals.package_csr_nnz
        assert aggregate_totals.result_array_count == sum(
            row.result_array_count for row in observations
        )
        assert aggregate_totals.result_array_count == 60
        assert aggregate_totals.result_array_byte_count == sum(
            row.result_array_byte_count for row in observations
        )
        assert aggregate_totals.result_array_byte_count == 6728
        assert aggregate_totals.detached_raw_payload_byte_count == sum(
            row.detached_raw_payload_byte_count for row in observations
        )
        assert aggregate_totals.detached_raw_payload_byte_count == 1648
        assert (
            aggregate_totals.upstream_completion_export_blocking_d2h_attempt_count,
            aggregate_totals.upstream_completion_export_blocking_d2h_success_count,
            aggregate_totals.upstream_completion_export_blocking_d2h_failure_count,
            aggregate_totals.upstream_completion_export_byte_count,
        ) == (30, 30, 0, 4288)
        assert observed_upstream_export_byte_count == 4288
        assert (
            aggregate_totals.upstream_completion_export_byte_count
            == observed_upstream_export_byte_count
        )
        assert aggregate_totals.aggregate_additional_device_operation_count == 0
        assert aggregate_totals.aggregate_additional_d2h_operation_count == 0
        assert aggregate_totals.aggregate_additional_solve_count == 0
        assert aggregate_totals.aggregate_additional_export_count == 0
        assert aggregate_totals.aggregate_fallback_count == 0
        aggregate_claims = aggregate_receipt.claims
        assert aggregate_claims.fixed_all_converged_package_registry_replayed
        assert aggregate_claims.all_converged_family_authority_replayed_at_issuance
        assert aggregate_claims.exact_ten_converged_result_ir_v2_verified
        assert aggregate_claims.exact_ten_result_ir_v2_ready
        assert aggregate_claims.all_ten_solution_ready
        assert aggregate_claims.retained_bridge_exact_identity_bound
        assert aggregate_claims.case_plan_provenance_terminal_export_device_state_cross_bound
        assert aggregate_claims.reaction_member_force_energy_and_state_lineage_verified
        assert aggregate_claims.canonical_registry_order_verified
        assert aggregate_claims.descriptor_only_family_manifest
        assert aggregate_claims.post_close_detached_value_validation_supported
        assert aggregate_claims.aggregate_additional_device_operation_zero
        assert aggregate_claims.aggregate_additional_d2h_zero
        assert aggregate_claims.aggregate_additional_solve_zero
        assert aggregate_claims.aggregate_additional_export_zero
        assert aggregate_claims.aggregate_fallback_zero
        assert not aggregate_claims.registry_validation_cpu_reference_replay_zero_proven
        assert not aggregate_claims.serialized_receipt_grants_process_local_provenance
        assert not aggregate_claims.external_gfx1100_result_ir_verified
        assert not aggregate_claims.multiarchitecture_result_ir_verified
        assert not aggregate_claims.process_wide_host_transfer_zero_proven
        assert not aggregate_claims.device_result_recovery_verified
        assert not aggregate_claims.hostile_same_process_mutation_resistance
        assert not aggregate_claims.signed_evidence
        assert not aggregate_claims.persistent_external_log_verified
        assert not aggregate_claims.performance_or_speedup_proven
        assert not aggregate_claims.end_to_end_o_n_verified
        assert not aggregate_claims.nonlinear_dynamic_shell_solid_contact_verified
        assert not aggregate_claims.commercial_ready
        assert not aggregate_claims.promotion_eligible
        peak_rss_kib = _emit_rss_checkpoint(
            phase="aggregate_complete",
            previous_peak_rss_kib=peak_rss_kib,
        )
    finally:
        cleanup_errors: list[BaseException] = []
        for opened in reversed(resources):
            try:
                opened.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            active_error = sys.exc_info()[1]
            if active_error is not None:
                _attach_cleanup_failures(active_error, cleanup_errors)
            else:
                first = cleanup_errors[0]
                _attach_cleanup_failures(first, cleanup_errors[1:])
                raise first

    assert family is not None
    assert aggregate is not None
    for bridge in bridges:
        assert validate_hip_fgmres_result_ir_v2(bridge) is bridge
    assert validate_hip_fgmres_all_converged_result_ir_result_v1(aggregate) is aggregate
    _emit_rss_checkpoint(
        phase="post_close_validation_complete",
        previous_peak_rss_kib=peak_rss_kib,
    )
