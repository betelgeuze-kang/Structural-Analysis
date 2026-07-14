"""Actual-gfx1030 replay of all package FGMRES fixed-suite v2 cells."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    open_hip_fgmres_completion_export_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    attest_hip_fgmres_model_case_parity_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
    attest_hip_fgmres_model_family_coverage_v2,
    validate_hip_fgmres_model_family_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    observe_hip_fgmres_terminal_outcome_v1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    attest_hip_device_identity_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    solve_cpu_fgmres_reference_v1,
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
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_PARITY_V2_HARDWARE",
        )
    )


@dataclass(slots=True)
class _LiveCaseResources:
    chain: Any
    sealed: Any
    global_open: Any
    export_context: Any

    def close(self) -> None:
        if self.export_context is not None and not self.export_context.closed:
            self.export_context.close()
        if self.global_open is not None and not self.global_open.context.closed:
            self.global_open.context.close()
        if self.sealed is not None and not self.sealed.context.closed:
            self.sealed.context.close()
        self.chain.close()


def _execute_live_case(slot: Any, architecture: str, required: bool) -> tuple[Any, Any]:
    chain = sealed = global_open = export_context = None
    try:
        chain, predecessor_capability = _open_canonical_chain(
            model=slot.model,
            architecture=architecture,
            required=required,
            policy=slot.policy,
            load_pattern_id=slot.execution_plan.load_pattern_id,
        )
        source_fgmres_plan = chain.recurrence._source_fgmres_plan
        source_execution_plan = source_fgmres_plan._source_execution_plan
        assert source_execution_plan.plan_hash == slot.execution_plan.plan_hash
        assert source_fgmres_plan.plan_hash == slot.fgmres_plan.plan_hash
        assert chain.recurrence.plan_hash == slot.recurrence_plan.plan_hash

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
        observation = observe_hip_fgmres_terminal_outcome_v1(
            export_result,
            expected_export_context=export_context,
        )
        cpu_result = solve_cpu_fgmres_reference_v1(
            source_execution_plan,
            source_fgmres_plan.policy,
        )
        assert cpu_result.result_hash == slot.cpu_result.result_hash
        loaded_runtime = chain.live._loaded_runtime
        assert loaded_runtime is not None
        device_identity = attest_hip_device_identity_v1(
            loaded_runtime,
            device_ordinal=0,
            expected_compiled_architecture=architecture,
        )
        parity = attest_hip_fgmres_model_case_parity_v1(
            cpu_result,
            observation,
            device_identity,
        )
        resources = _LiveCaseResources(
            chain=chain,
            sealed=sealed,
            global_open=global_open,
            export_context=export_context,
        )
        return resources, parity
    except BaseException:
        if export_context is not None and not export_context.closed:
            export_context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if chain is not None:
            chain.close()
        raise


def test_native_gfx1030_replays_all_ten_registry_cells_in_one_live_aggregate() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    registry = load_hip_fgmres_fixture_registry_v1()
    resources: list[_LiveCaseResources] = []
    cases: list[Any] = []
    try:
        for slot_id in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2:
            print(f"actual-gfx1030 fixed-suite cell: {slot_id}", flush=True)
            opened, case = _execute_live_case(
                registry.slot(slot_id),
                architecture,
                required,
            )
            resources.append(opened)
            cases.append(case)

        family = attest_hip_fgmres_model_family_coverage_v2(tuple(cases))
        validate_hip_fgmres_model_family_parity_result_v2(
            family,
            expected_case_results=tuple(cases),
        )
        receipt = family.receipt
        assert receipt.status == (
            "primary_gfx1030_fixed_suite_complete_external_gfx1100_pending"
        )
        assert receipt.coverage.validated_input_case_count == 10
        assert receipt.coverage.covered_matrix_cell_count == 10
        assert receipt.coverage.completed_architecture_bases == ("gfx1030",)
        assert receipt.coverage.incomplete_architecture_bases == ("gfx1100",)
        assert receipt.claims.primary_gfx1030_fixed_suite_complete
        assert not receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
        assert not receipt.claims.full_model_family_parity_verified
        assert not receipt.claims.multiarchitecture_parity_verified
        assert not receipt.claims.signed_evidence
        assert not receipt.claims.result_ir_verified
        assert not receipt.claims.iteration_host_copy_zero_verified
        assert not receipt.claims.speedup_verified
        assert not receipt.claims.end_to_end_o_n_verified
        assert not receipt.claims.commercial_ready
        assert not receipt.promotion_eligible
    finally:
        for opened in reversed(resources):
            opened.close()
