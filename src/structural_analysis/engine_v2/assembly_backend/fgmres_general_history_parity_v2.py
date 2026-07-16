"""General multi-restart CPU/HIP FGMRES checkpoint-history parity v2.

The contract consumes the additive five-buffer completion export, reconstructs
the CPU checkpoint vectors, binds every populated solve-record row to its
device-captured solution and true residual, and verifies scalar history through
vector-backed replay plus outward roundoff envelopes. No additional device
operation or host transfer is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.fp64_csr_residual_roundoff_v1 import (
    Fp64CsrResidualRoundoffResultV1,
    attest_fp64_csr_residual_roundoff_v1,
    validate_fp64_csr_residual_roundoff_result_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresCheckpointHistoryResultV2,
    FgmresRestartRecord,
    _initial_reduced_state,
    solve_cpu_fgmres_checkpoint_history_v2,
    validate_cpu_fgmres_checkpoint_history_result_v2,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)

from .fgmres_completion_export_v2 import (
    HipFgmresCompletionExportExecutionContextV2,
    HipFgmresCompletionExportResultV2,
    validate_hip_fgmres_completion_export_result_v2,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeObservationResultV1,
    HipFgmresTerminalOutcomeRestartRowV1,
    observe_hip_fgmres_terminal_outcome_v1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)


HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-general-history-parity.v2"
)
HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2 = (
    "phase0_general_multi_restart_vector_backed_history_parity_v2"
)
HIP_FGMRES_GENERAL_HISTORY_PARITY_EVIDENCE_SCOPE_V2 = (
    "process_local_exact_model_general_history_non_promoting"
)
HIP_FGMRES_GENERAL_HISTORY_SOLUTION_RELATIVE_TOLERANCE_V2 = 1.0e-8
HIP_FGMRES_GENERAL_HISTORY_SOLUTION_ABSOLUTE_TOLERANCE_V2 = 1.0e-12

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNIT_ROUNDOFF = 2.0**-53
_ETA = 2.0**-1074
_SCHEMA_RESOURCE = "hip_fgmres_general_history_parity_v2.schema.json"


class HipFgmresGeneralHistoryParityV2Error(RuntimeError):
    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresHistoryVectorComparisonV2:
    name: Literal["checkpoint_solution", "checkpoint_true_residual"]
    value_count: int
    reference_sha256: str
    candidate_sha256: str
    maximum_absolute_error: float
    difference_l2: float
    reference_l2: float
    relative_l2_error: float
    fixed_absolute_tolerance: float
    fixed_relative_tolerance: float
    fixed_componentwise_gate_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHistoryScalarEnvelopeV2:
    name: Literal[
        "true_residual_l2",
        "true_residual_linf",
        "scaled_true_residual",
        "estimated_residual_l2",
        "solution_update_l2",
    ]
    cpu_value: float
    hip_value: float
    absolute_difference: float
    vector_transport_bound: float
    cpu_estimator_or_replay_gap: float
    hip_estimator_or_replay_gap: float
    fp_roundoff_guard: float
    total_bound: float
    maximum_bound_ratio: float
    outward_rounding_used: Literal[True] = True
    bound_passed: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryRowV2:
    restart_index: int
    slot_index: int
    column_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    reorthogonalization_count: int
    termination_hint: str
    flags: int
    solution: HipFgmresHistoryVectorComparisonV2
    true_residual: HipFgmresHistoryVectorComparisonV2
    residual_roundoff_receipt_hash: str
    residual_roundoff_maximum_componentwise_ratio: float
    true_residual_l2: HipFgmresHistoryScalarEnvelopeV2
    true_residual_linf: HipFgmresHistoryScalarEnvelopeV2
    scaled_true_residual: HipFgmresHistoryScalarEnvelopeV2
    estimated_residual_l2: HipFgmresHistoryScalarEnvelopeV2
    solution_update_l2: HipFgmresHistoryScalarEnvelopeV2
    capture_metadata_matches_solve_record: Literal[True] = True
    gpu_true_residual_l2_tree_replayed: Literal[True] = True
    gpu_true_residual_linf_tree_replayed: Literal[True] = True
    gpu_scaled_true_residual_replayed: Literal[True] = True
    gpu_solution_update_l2_tree_replayed: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "restart_index": self.restart_index,
            "slot_index": self.slot_index,
            "column_index": self.column_index,
            "start_iteration": self.start_iteration,
            "end_iteration": self.end_iteration,
            "arnoldi_step_count": self.arnoldi_step_count,
            "reorthogonalization_count": self.reorthogonalization_count,
            "termination_hint": self.termination_hint,
            "flags": self.flags,
            "capture_metadata_matches_solve_record": True,
            "gpu_true_residual_l2_tree_replayed": True,
            "gpu_true_residual_linf_tree_replayed": True,
            "gpu_scaled_true_residual_replayed": True,
            "gpu_solution_update_l2_tree_replayed": True,
            "solution": self.solution.to_dict(),
            "true_residual": self.true_residual.to_dict(),
            "residual_roundoff_receipt_hash": self.residual_roundoff_receipt_hash,
            "residual_roundoff_maximum_componentwise_ratio": (
                self.residual_roundoff_maximum_componentwise_ratio
            ),
            "metrics": {
                "true_residual_l2": self.true_residual_l2.to_dict(),
                "true_residual_linf": self.true_residual_linf.to_dict(),
                "scaled_true_residual": self.scaled_true_residual.to_dict(),
                "estimated_residual_l2": self.estimated_residual_l2.to_dict(),
                "solution_update_l2": self.solution_update_l2.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityBindingsV2:
    execution_plan_hash: str
    operator_hash: str
    policy_hash: str
    cpu_checkpoint_history_result_hash: str
    cpu_base_result_hash: str
    completion_export_v2_context_id: str
    completion_export_v2_receipt_hash: str
    completion_export_v2_payload_hash: str
    retained_completion_export_v1_receipt_hash: str
    checkpoint_history_export_v1_receipt_hash: str
    terminal_observation_receipt_hash: str
    global_context_id: str
    history_plan_hash: str
    history_blob_abi_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_identity_hash: str
    architecture: str
    device_ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityDimensionsV2:
    free_dof_count: int
    maximum_restart_count: int
    populated_restart_count: int
    exported_checkpoint_solution_vector_count: int
    exported_checkpoint_true_residual_vector_count: int
    compared_scalar_count: int
    residual_roundoff_receipt_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityTelemetryV2:
    solve_record_restart_row_inspection_count: int
    checkpoint_vector_pair_comparison_count: int
    gpu_tree_metric_replay_count: int
    scalar_envelope_count: int
    residual_roundoff_receipt_count: int
    cpu_checkpoint_replay_count: Literal[1] = 1
    additional_d2h_operation_count: Literal[0] = 0
    device_allocation_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    explicit_stream_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityClaimsV2:
    exact_execution_plan_and_policy_bound: Literal[True] = True
    deterministic_cpu_checkpoint_history_replayed: Literal[True] = True
    actual_hip_backend_verified: Literal[True] = True
    solve_record_and_history_blob_rows_cross_bound: Literal[True] = True
    per_restart_checkpoint_solution_vectors_verified: Literal[True] = True
    per_restart_checkpoint_true_residual_vectors_verified: Literal[True] = True
    componentwise_sparse_residual_roundoff_verified: Literal[True] = True
    true_residual_scalar_vector_replay_verified: Literal[True] = True
    estimated_residual_roundoff_envelope_verified: Literal[True] = True
    solution_update_roundoff_envelope_verified: Literal[True] = True
    general_restart_history_metric_v2_verified: Literal[True] = True
    additional_device_or_transfer_work_zero: Literal[True] = True
    formal_machine_proof: Literal[False] = False
    multi_architecture_parity_verified: Literal[False] = False
    iteration_host_copy_zero_process_wide: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityReceiptV2:
    schema_version: str
    capability_profile: str
    status: Literal["general_multi_restart_history_v2_verified"]
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    parity_id: str
    bindings: HipFgmresGeneralHistoryParityBindingsV2
    dimensions: HipFgmresGeneralHistoryParityDimensionsV2
    rows: tuple[HipFgmresGeneralHistoryRowV2, ...]
    telemetry: HipFgmresGeneralHistoryParityTelemetryV2
    claims: HipFgmresGeneralHistoryParityClaimsV2
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_general_history_parity_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresGeneralHistoryParityResultV2:
    receipt: HipFgmresGeneralHistoryParityReceiptV2
    cpu_history: CpuFgmresCheckpointHistoryResultV2
    completion_export: HipFgmresCompletionExportResultV2
    terminal_observation: HipFgmresTerminalOutcomeObservationResultV1
    residual_roundoff_results: tuple[Fp64CsrResidualRoundoffResultV1, ...]

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_general_history_parity_result_v2(self)
        return self.receipt.to_dict()


def attest_hip_fgmres_general_history_parity_v2(
    cpu_history: CpuFgmresCheckpointHistoryResultV2,
    completion_export: HipFgmresCompletionExportResultV2,
    *,
    expected_export_context: HipFgmresCompletionExportExecutionContextV2,
) -> HipFgmresGeneralHistoryParityResultV2:
    """Verify every populated restart row without another device operation."""

    if type(expected_export_context) is not HipFgmresCompletionExportExecutionContextV2:
        _fail("hip_fgmres_general_history_context_invalid", "/context")
    validate_hip_fgmres_completion_export_result_v2(completion_export)
    if (
        expected_export_context.result is not completion_export
        or expected_export_context.closed
        or expected_export_context._base is None
    ):
        _fail("hip_fgmres_general_history_export_authority_invalid", "/export")
    authority = expected_export_context._base._model_case_parity_authority(
        completion_export.base_export
    )
    plan = authority.source.source_execution_plan
    policy = authority.source.source_fgmres_plan.policy
    validate_cpu_fgmres_checkpoint_history_result_v2(
        cpu_history,
        expected_plan=plan,
        expected_policy=policy,
    )
    replayed_cpu = solve_cpu_fgmres_checkpoint_history_v2(plan, policy)
    if replayed_cpu.result_hash != cpu_history.result_hash:
        _fail("hip_fgmres_general_history_cpu_replay_mismatch", "/cpu")
    observation = observe_hip_fgmres_terminal_outcome_v1(
        completion_export.base_export,
        expected_export_context=expected_export_context._base,
    )
    validate_hip_fgmres_terminal_outcome_observation_result_v1(observation)
    if observation.receipt.actual_backend != "hip":
        _fail("hip_fgmres_general_history_actual_backend_invalid", "/observation")
    outcome = observation.outcome
    base = cpu_history.base_result
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    captured = tuple(
        row
        for row in completion_export.history_export.solution.restart_rows
        if row.captured == 1
    )
    if (
        outcome.terminal_status != base.status
        or outcome.termination_code != base.termination_code
        or outcome.counters.effective_iterations != base.iteration_count
        or outcome.counters.effective_restarts != base.restart_count
        or outcome.counters.operator_apply_count != base.operator_apply_count
        or outcome.counters.preconditioner_apply_count
        != base.preconditioner_apply_count
        or len(populated) != len(base.history)
        or len(captured) != len(base.history)
        or completion_export.history_export.solution.populated_restart_count
        != len(base.history)
        or completion_export.history_export.true_residual.populated_restart_count
        != len(base.history)
    ):
        _fail("hip_fgmres_general_history_discrete_mismatch", "/history")
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    free_count = int(free.size)
    rhs = np.ascontiguousarray(plan.array("global_load")[free], dtype="<f8")
    rhs_linf = float(np.max(np.abs(rhs), initial=0.0))
    scale_denominator = max(1.0, rhs_linf)
    cpu_previous = _initial_reduced_state(plan, free, None)
    hip_previous = np.array(cpu_previous, dtype="<f8", copy=True)
    rows: list[HipFgmresGeneralHistoryRowV2] = []
    residual_roundoff: list[Fp64CsrResidualRoundoffResultV1] = []
    for index, (cpu_row, cpu_vectors, hip_row, capture_row) in enumerate(
        zip(
            base.history,
            cpu_history.checkpoints,
            populated,
            captured,
            strict=True,
        )
    ):
        hip_solution = np.ascontiguousarray(
            completion_export.checkpoint_solution_array[index], dtype="<f8"
        )
        hip_residual = np.ascontiguousarray(
            completion_export.checkpoint_true_residual_array[index], dtype="<f8"
        )
        row, roundoff = _attest_row(
            plan=plan,
            index=index,
            free_count=free_count,
            scale_denominator=scale_denominator,
            cpu_row=cpu_row,
            cpu_solution=cpu_vectors.solution,
            cpu_residual=cpu_vectors.true_residual,
            cpu_previous=cpu_previous,
            hip_row=hip_row,
            capture_row=capture_row,
            hip_solution=hip_solution,
            hip_residual=hip_residual,
            hip_previous=hip_previous,
        )
        rows.append(row)
        residual_roundoff.append(roundoff)
        cpu_previous = cpu_vectors.solution
        hip_previous = hip_solution
    row_tuple = tuple(rows)
    bindings = HipFgmresGeneralHistoryParityBindingsV2(
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        policy_hash=policy.policy_hash,
        cpu_checkpoint_history_result_hash=cpu_history.result_hash,
        cpu_base_result_hash=base.result_hash,
        completion_export_v2_context_id=completion_export.receipt.context_id,
        completion_export_v2_receipt_hash=completion_export.receipt.receipt_hash,
        completion_export_v2_payload_hash=completion_export.payload_hash,
        retained_completion_export_v1_receipt_hash=(
            completion_export.base_export.receipt.receipt_hash
        ),
        checkpoint_history_export_v1_receipt_hash=(
            completion_export.history_export.receipt.receipt_hash
        ),
        terminal_observation_receipt_hash=observation.receipt.receipt_hash,
        global_context_id=completion_export.receipt.bindings.global_context_id,
        history_plan_hash=completion_export.receipt.bindings.history_plan_hash,
        history_blob_abi_hash=completion_export.receipt.bindings.history_blob_abi_hash,
        recurrence_plan_hash=completion_export.receipt.bindings.recurrence_plan_hash,
        recurrence_kernel_identity_hash=(
            completion_export.receipt.bindings.recurrence_kernel_identity_hash
        ),
        architecture=completion_export.receipt.bindings.architecture,
        device_ordinal=completion_export.receipt.bindings.device_ordinal,
    )
    count = len(row_tuple)
    dimensions = HipFgmresGeneralHistoryParityDimensionsV2(
        free_dof_count=free_count,
        maximum_restart_count=completion_export.receipt.dimensions.maximum_restart_count,
        populated_restart_count=count,
        exported_checkpoint_solution_vector_count=count,
        exported_checkpoint_true_residual_vector_count=count,
        compared_scalar_count=5 * count,
        residual_roundoff_receipt_count=count,
    )
    telemetry = HipFgmresGeneralHistoryParityTelemetryV2(
        solve_record_restart_row_inspection_count=len(outcome.restart_rows),
        checkpoint_vector_pair_comparison_count=count,
        gpu_tree_metric_replay_count=4 * count,
        scalar_envelope_count=5 * count,
        residual_roundoff_receipt_count=count,
    )
    parity_id = canonical_hash(
        {
            "profile": HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2,
            "cpu_result_hash": cpu_history.result_hash,
            "completion_receipt_hash": completion_export.receipt.receipt_hash,
            "terminal_observation_receipt_hash": observation.receipt.receipt_hash,
            "rows": [row.to_dict() for row in row_tuple],
        }
    )
    draft = HipFgmresGeneralHistoryParityReceiptV2(
        schema_version=HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2,
        capability_profile=HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2,
        status="general_multi_restart_history_v2_verified",
        evidence_scope=HIP_FGMRES_GENERAL_HISTORY_PARITY_EVIDENCE_SCOPE_V2,
        actual_backend="hip",
        promotion_eligible=False,
        parity_id=parity_id,
        bindings=bindings,
        dimensions=dimensions,
        rows=row_tuple,
        telemetry=telemetry,
        claims=HipFgmresGeneralHistoryParityClaimsV2(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    result = HipFgmresGeneralHistoryParityResultV2(
        receipt=receipt,
        cpu_history=cpu_history,
        completion_export=completion_export,
        terminal_observation=observation,
        residual_roundoff_results=tuple(residual_roundoff),
    )
    return validate_hip_fgmres_general_history_parity_result_v2(result)


def _attest_row(
    *,
    plan: Any,
    index: int,
    free_count: int,
    scale_denominator: float,
    cpu_row: FgmresRestartRecord,
    cpu_solution: np.ndarray,
    cpu_residual: np.ndarray,
    cpu_previous: np.ndarray,
    hip_row: HipFgmresTerminalOutcomeRestartRowV1,
    capture_row: Any,
    hip_solution: np.ndarray,
    hip_residual: np.ndarray,
    hip_previous: np.ndarray,
) -> tuple[HipFgmresGeneralHistoryRowV2, Fp64CsrResidualRoundoffResultV1]:
    _validate_discrete_row(cpu_row, hip_row, capture_row, index)
    if hip_solution.shape != (free_count,) or hip_residual.shape != (free_count,):
        _fail("hip_fgmres_general_history_vector_shape_invalid", f"/rows/{index}")
    solution_comparison = _compare_vector(
        "checkpoint_solution",
        cpu_solution,
        hip_solution,
        require_fixed_gate=True,
    )
    residual_comparison = _compare_vector(
        "checkpoint_true_residual",
        cpu_residual,
        hip_residual,
        require_fixed_gate=False,
    )
    roundoff = attest_fp64_csr_residual_roundoff_v1(
        plan,
        cpu_solution,
        hip_solution,
        cpu_residual,
        hip_residual,
    )
    validate_fp64_csr_residual_roundoff_result_v1(
        roundoff,
        expected_execution_plan=plan,
    )
    summary = roundoff.receipt.summary
    hip_l2 = fgmres_gpu_tree_l2_v2(hip_residual).value
    hip_linf = fgmres_gpu_tree_linf_v2(hip_residual).value
    hip_scaled = hip_linf / scale_denominator
    cpu_update = np.ascontiguousarray(cpu_solution - cpu_previous, dtype="<f8")
    hip_update = np.ascontiguousarray(hip_solution - hip_previous, dtype="<f8")
    hip_update_l2 = fgmres_gpu_tree_l2_v2(hip_update).value
    if (
        hip_l2 != hip_row.true_residual_l2
        or hip_linf != hip_row.true_residual_linf
        or hip_scaled != hip_row.scaled_true_residual
        or hip_update_l2 != hip_row.solution_update_l2
    ):
        _fail(
            "hip_fgmres_general_history_gpu_tree_replay_mismatch",
            f"/rows/{index}/metrics",
        )
    l2_envelope = _scalar_envelope(
        "true_residual_l2",
        cpu_row.true_residual_l2,
        hip_row.true_residual_l2,
        vector_transport_bound=summary.difference_l2_upper_bound,
        cpu_gap=0.0,
        hip_gap=0.0,
        scale=max(cpu_row.true_residual_l2, hip_row.true_residual_l2),
        operation_count=8 * free_count + 32,
    )
    linf_transport = summary.maximum_absolute_difference_upper_bound
    linf_envelope = _scalar_envelope(
        "true_residual_linf",
        cpu_row.true_residual_linf,
        hip_row.true_residual_linf,
        vector_transport_bound=linf_transport,
        cpu_gap=0.0,
        hip_gap=0.0,
        scale=max(cpu_row.true_residual_linf, hip_row.true_residual_linf),
        operation_count=2 * free_count + 8,
    )
    scaled_envelope = _scalar_envelope(
        "scaled_true_residual",
        cpu_row.scaled_true_residual,
        hip_row.scaled_true_residual,
        vector_transport_bound=_div_up(linf_transport, scale_denominator),
        cpu_gap=0.0,
        hip_gap=0.0,
        scale=max(cpu_row.scaled_true_residual, hip_row.scaled_true_residual),
        operation_count=2 * free_count + 12,
    )
    estimated_envelope = _scalar_envelope(
        "estimated_residual_l2",
        cpu_row.estimated_residual_l2,
        hip_row.estimated_residual_l2,
        vector_transport_bound=l2_envelope.total_bound,
        cpu_gap=abs(cpu_row.estimated_residual_l2 - cpu_row.true_residual_l2),
        hip_gap=abs(hip_row.estimated_residual_l2 - hip_row.true_residual_l2),
        scale=max(
            cpu_row.estimated_residual_l2,
            hip_row.estimated_residual_l2,
            cpu_row.true_residual_l2,
            hip_row.true_residual_l2,
        ),
        operation_count=32 * cpu_row.arnoldi_step_count + 8 * free_count + 64,
    )
    update_envelope = _scalar_envelope(
        "solution_update_l2",
        cpu_row.solution_update_l2,
        hip_row.solution_update_l2,
        vector_transport_bound=_l2_difference_upper(cpu_update, hip_update),
        cpu_gap=0.0,
        hip_gap=0.0,
        scale=max(cpu_row.solution_update_l2, hip_row.solution_update_l2),
        operation_count=8 * free_count + 32,
    )
    row = HipFgmresGeneralHistoryRowV2(
        restart_index=cpu_row.restart_index,
        slot_index=hip_row.slot_index,
        column_index=capture_row.column_index,
        start_iteration=cpu_row.start_iteration,
        end_iteration=cpu_row.end_iteration,
        arnoldi_step_count=cpu_row.arnoldi_step_count,
        reorthogonalization_count=cpu_row.reorthogonalization_count,
        termination_hint=cpu_row.termination_hint,
        flags=hip_row.flags,
        solution=solution_comparison,
        true_residual=residual_comparison,
        residual_roundoff_receipt_hash=roundoff.receipt.receipt_hash,
        residual_roundoff_maximum_componentwise_ratio=(
            summary.maximum_componentwise_bound_ratio
        ),
        true_residual_l2=l2_envelope,
        true_residual_linf=linf_envelope,
        scaled_true_residual=scaled_envelope,
        estimated_residual_l2=estimated_envelope,
        solution_update_l2=update_envelope,
    )
    return row, roundoff


def _validate_discrete_row(
    cpu: FgmresRestartRecord,
    hip: HipFgmresTerminalOutcomeRestartRowV1,
    capture: Any,
    index: int,
) -> None:
    if (
        hip.restart_index != cpu.restart_index
        or hip.start_iteration != cpu.start_iteration
        or hip.end_iteration != cpu.end_iteration
        or hip.arnoldi_step_count != cpu.arnoldi_step_count
        or hip.reorthogonalization_count != cpu.reorthogonalization_count
        or hip.termination_hint != cpu.termination_hint
        or capture.restart_index != cpu.restart_index
        or capture.column_index != cpu.arnoldi_step_count - 1
        or capture.end_iteration != cpu.end_iteration
        or capture.source_restart_flags != hip.flags
    ):
        _fail("hip_fgmres_general_history_row_discrete_mismatch", f"/rows/{index}")


def _compare_vector(
    name: Literal["checkpoint_solution", "checkpoint_true_residual"],
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    require_fixed_gate: bool,
) -> HipFgmresHistoryVectorComparisonV2:
    if (
        reference.shape != candidate.shape
        or reference.dtype.str != "<f8"
        or candidate.dtype.str != "<f8"
        or not np.isfinite(reference).all()
        or not np.isfinite(candidate).all()
    ):
        _fail("hip_fgmres_general_history_vector_invalid", f"/vectors/{name}")
    difference = np.abs(candidate - reference)
    tolerance = (
        HIP_FGMRES_GENERAL_HISTORY_SOLUTION_ABSOLUTE_TOLERANCE_V2
        + HIP_FGMRES_GENERAL_HISTORY_SOLUTION_RELATIVE_TOLERANCE_V2 * np.abs(reference)
    )
    passed = bool(np.all(difference <= tolerance))
    if require_fixed_gate and not passed:
        _fail("hip_fgmres_general_history_solution_mismatch", f"/vectors/{name}")
    difference_l2 = _stable_l2(difference)
    reference_l2 = _stable_l2(reference)
    relative = difference_l2 / max(reference_l2, np.finfo(np.float64).tiny)
    return HipFgmresHistoryVectorComparisonV2(
        name=name,
        value_count=int(reference.size),
        reference_sha256=array_data_hash(reference),
        candidate_sha256=array_data_hash(candidate),
        maximum_absolute_error=float(np.max(difference, initial=0.0)),
        difference_l2=difference_l2,
        reference_l2=reference_l2,
        relative_l2_error=relative,
        fixed_absolute_tolerance=(
            HIP_FGMRES_GENERAL_HISTORY_SOLUTION_ABSOLUTE_TOLERANCE_V2
        ),
        fixed_relative_tolerance=(
            HIP_FGMRES_GENERAL_HISTORY_SOLUTION_RELATIVE_TOLERANCE_V2
        ),
        fixed_componentwise_gate_passed=passed,
    )


def _scalar_envelope(
    name: Literal[
        "true_residual_l2",
        "true_residual_linf",
        "scaled_true_residual",
        "estimated_residual_l2",
        "solution_update_l2",
    ],
    cpu_value: float,
    hip_value: float,
    *,
    vector_transport_bound: float,
    cpu_gap: float,
    hip_gap: float,
    scale: float,
    operation_count: int,
) -> HipFgmresHistoryScalarEnvelopeV2:
    values = (cpu_value, hip_value, vector_transport_bound, cpu_gap, hip_gap, scale)
    if any(
        type(value) is not float or not math.isfinite(value) or value < 0.0
        for value in values
    ):
        _fail("hip_fgmres_general_history_scalar_invalid", f"/metrics/{name}")
    guard = _roundoff_guard(scale, operation_count)
    total = _sum_up(vector_transport_bound, cpu_gap, hip_gap, guard)
    difference = abs(hip_value - cpu_value)
    if difference > total:
        _fail(
            "hip_fgmres_general_history_scalar_bound_failed",
            f"/metrics/{name}",
            f"difference={difference!r} bound={total!r}",
        )
    ratio = 0.0 if total == 0.0 else _div_up(difference, total)
    return HipFgmresHistoryScalarEnvelopeV2(
        name=name,
        cpu_value=cpu_value,
        hip_value=hip_value,
        absolute_difference=difference,
        vector_transport_bound=vector_transport_bound,
        cpu_estimator_or_replay_gap=cpu_gap,
        hip_estimator_or_replay_gap=hip_gap,
        fp_roundoff_guard=guard,
        total_bound=total,
        maximum_bound_ratio=ratio,
    )


def _valid_scalar_envelope(value: HipFgmresHistoryScalarEnvelopeV2) -> bool:
    numeric = (
        value.cpu_value,
        value.hip_value,
        value.absolute_difference,
        value.vector_transport_bound,
        value.cpu_estimator_or_replay_gap,
        value.hip_estimator_or_replay_gap,
        value.fp_roundoff_guard,
        value.total_bound,
        value.maximum_bound_ratio,
    )
    return (
        all(type(row) is float and math.isfinite(row) and row >= 0.0 for row in numeric)
        and value.absolute_difference <= value.total_bound
        and value.maximum_bound_ratio <= 1.0
        and value.outward_rounding_used is True
        and value.bound_passed is True
    )


def _l2_difference_upper(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        _fail("hip_fgmres_general_history_update_shape_invalid", "/metrics/update")
    sum_squares = 0.0
    for left_raw, right_raw in zip(left, right, strict=True):
        left_value = float(left_raw)
        right_value = float(right_raw)
        rounded_difference = abs(left_value - right_value)
        subtraction_error = _sum_up(
            _mul_up(_UNIT_ROUNDOFF, abs(left_value) + abs(right_value)),
            _ETA,
        )
        bound = _sum_up(rounded_difference, subtraction_error)
        sum_squares = _sum_up(sum_squares, _mul_up(bound, bound))
    return math.nextafter(math.sqrt(sum_squares), math.inf)


def _roundoff_guard(scale: float, operation_count: int) -> float:
    if operation_count <= 0 or operation_count * _UNIT_ROUNDOFF >= 1.0:
        _fail("hip_fgmres_general_history_roundoff_domain_invalid", "/roundoff")
    gamma = (operation_count * _UNIT_ROUNDOFF) / (
        1.0 - operation_count * _UNIT_ROUNDOFF
    )
    return _sum_up(_mul_up(gamma, scale), operation_count * _ETA)


def _sum_up(*values: float) -> float:
    result = 0.0
    for value in values:
        result = math.nextafter(result + value, math.inf)
    return result


def _mul_up(left: float, right: float) -> float:
    return math.nextafter(left * right, math.inf)


def _div_up(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        _fail("hip_fgmres_general_history_division_invalid", "/roundoff")
    return math.nextafter(numerator / denominator, math.inf)


def _stable_l2(vector: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for raw in vector:
        value = abs(float(raw))
        if value == 0.0:
            continue
        if scale < value:
            ratio = 0.0 if scale == 0.0 else scale / value
            sumsq = 1.0 + sumsq * ratio * ratio
            scale = value
        else:
            ratio = value / scale
            sumsq += ratio * ratio
    return 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)


def validate_hip_fgmres_general_history_parity_receipt_v2(
    receipt: HipFgmresGeneralHistoryParityReceiptV2,
) -> HipFgmresGeneralHistoryParityReceiptV2:
    if type(receipt) is not HipFgmresGeneralHistoryParityReceiptV2:
        _fail("hip_fgmres_general_history_receipt_type_invalid", "/")
    if (
        receipt.schema_version != HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2
        or receipt.capability_profile
        != HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2
        or receipt.status != "general_multi_restart_history_v2_verified"
        or receipt.evidence_scope != HIP_FGMRES_GENERAL_HISTORY_PARITY_EVIDENCE_SCOPE_V2
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or _HASH_RE.fullmatch(receipt.parity_id) is None
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash
        != canonical_hash(_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_general_history_receipt_invalid", "/")
    _validate_schema(_receipt_payload(receipt, include_hash=True))
    dimensions = receipt.dimensions
    count = len(receipt.rows)
    if (
        dimensions.free_dof_count <= 0
        or dimensions.maximum_restart_count <= 0
        or not 0 <= count <= dimensions.maximum_restart_count
        or dimensions.populated_restart_count != count
        or dimensions.exported_checkpoint_solution_vector_count != count
        or dimensions.exported_checkpoint_true_residual_vector_count != count
        or dimensions.compared_scalar_count != 5 * count
        or dimensions.residual_roundoff_receipt_count != count
        or receipt.telemetry.checkpoint_vector_pair_comparison_count != count
        or receipt.telemetry.gpu_tree_metric_replay_count != 4 * count
        or receipt.telemetry.scalar_envelope_count != 5 * count
        or receipt.telemetry.residual_roundoff_receipt_count != count
    ):
        _fail("hip_fgmres_general_history_dimensions_invalid", "/dimensions")
    for index, row in enumerate(receipt.rows):
        if (
            row.restart_index != index + 1
            or row.slot_index != index + 1
            or row.column_index != row.arnoldi_step_count - 1
            or row.capture_metadata_matches_solve_record is not True
            or row.gpu_true_residual_l2_tree_replayed is not True
            or row.gpu_true_residual_linf_tree_replayed is not True
            or row.gpu_scaled_true_residual_replayed is not True
            or row.gpu_solution_update_l2_tree_replayed is not True
            or not row.solution.fixed_componentwise_gate_passed
            or not _valid_scalar_envelope(row.true_residual_l2)
            or not _valid_scalar_envelope(row.true_residual_linf)
            or not _valid_scalar_envelope(row.scaled_true_residual)
            or not _valid_scalar_envelope(row.estimated_residual_l2)
            or not _valid_scalar_envelope(row.solution_update_l2)
            or _HASH_RE.fullmatch(row.residual_roundoff_receipt_hash) is None
            or not 0.0 <= row.residual_roundoff_maximum_componentwise_ratio <= 1.0
        ):
            _fail("hip_fgmres_general_history_row_invalid", f"/rows/{index}")
    if any(
        (
            receipt.telemetry.additional_d2h_operation_count,
            receipt.telemetry.device_allocation_count,
            receipt.telemetry.h2d_operation_count,
            receipt.telemetry.kernel_launch_count,
            receipt.telemetry.explicit_stream_sync_count,
            receipt.telemetry.fallback_count,
        )
    ):
        _fail("hip_fgmres_general_history_telemetry_invalid", "/telemetry")
    claims = receipt.claims
    required_true = (
        claims.exact_execution_plan_and_policy_bound,
        claims.deterministic_cpu_checkpoint_history_replayed,
        claims.actual_hip_backend_verified,
        claims.solve_record_and_history_blob_rows_cross_bound,
        claims.per_restart_checkpoint_solution_vectors_verified,
        claims.per_restart_checkpoint_true_residual_vectors_verified,
        claims.componentwise_sparse_residual_roundoff_verified,
        claims.true_residual_scalar_vector_replay_verified,
        claims.estimated_residual_roundoff_envelope_verified,
        claims.solution_update_roundoff_envelope_verified,
        claims.general_restart_history_metric_v2_verified,
        claims.additional_device_or_transfer_work_zero,
    )
    forbidden = (
        claims.formal_machine_proof,
        claims.multi_architecture_parity_verified,
        claims.iteration_host_copy_zero_process_wide,
        claims.performance_or_speedup_proven,
        claims.solution_ready,
        claims.result_ir_ready,
        claims.commercial_ready,
        claims.promotion_eligible,
    )
    if not all(required_true) or any(forbidden):
        _fail("hip_fgmres_general_history_claim_invalid", "/claims")
    return receipt


def validate_hip_fgmres_general_history_parity_result_v2(
    result: HipFgmresGeneralHistoryParityResultV2,
) -> HipFgmresGeneralHistoryParityResultV2:
    if type(result) is not HipFgmresGeneralHistoryParityResultV2:
        _fail("hip_fgmres_general_history_result_type_invalid", "/")
    receipt = validate_hip_fgmres_general_history_parity_receipt_v2(result.receipt)
    validate_hip_fgmres_completion_export_result_v2(result.completion_export)
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        result.terminal_observation
    )
    if (
        type(result.cpu_history) is not CpuFgmresCheckpointHistoryResultV2
        or len(result.residual_roundoff_results) != len(receipt.rows)
        or receipt.bindings.cpu_checkpoint_history_result_hash
        != result.cpu_history.result_hash
        or receipt.bindings.completion_export_v2_receipt_hash
        != result.completion_export.receipt.receipt_hash
        or receipt.bindings.terminal_observation_receipt_hash
        != result.terminal_observation.receipt.receipt_hash
    ):
        _fail("hip_fgmres_general_history_result_binding_invalid", "/")
    for row, roundoff in zip(
        receipt.rows,
        result.residual_roundoff_results,
        strict=True,
    ):
        validate_fp64_csr_residual_roundoff_result_v1(roundoff)
        if row.residual_roundoff_receipt_hash != roundoff.receipt.receipt_hash:
            _fail("hip_fgmres_general_history_roundoff_binding_invalid", "/rows")
    return result


def _receipt_payload(
    receipt: HipFgmresGeneralHistoryParityReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": False,
        "parity_id": receipt.parity_id,
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "rows": [row.to_dict() for row in receipt.rows],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("hip_fgmres_general_history_schema_invalid", path, error.message)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresGeneralHistoryParityV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_GENERAL_HISTORY_PARITY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2",
    "HIP_FGMRES_GENERAL_HISTORY_SOLUTION_ABSOLUTE_TOLERANCE_V2",
    "HIP_FGMRES_GENERAL_HISTORY_SOLUTION_RELATIVE_TOLERANCE_V2",
    "HipFgmresGeneralHistoryParityBindingsV2",
    "HipFgmresGeneralHistoryParityClaimsV2",
    "HipFgmresGeneralHistoryParityDimensionsV2",
    "HipFgmresGeneralHistoryParityReceiptV2",
    "HipFgmresGeneralHistoryParityResultV2",
    "HipFgmresGeneralHistoryParityTelemetryV2",
    "HipFgmresGeneralHistoryParityV2Error",
    "HipFgmresGeneralHistoryRowV2",
    "HipFgmresHistoryScalarEnvelopeV2",
    "HipFgmresHistoryVectorComparisonV2",
    "attest_hip_fgmres_general_history_parity_v2",
    "validate_hip_fgmres_general_history_parity_receipt_v2",
    "validate_hip_fgmres_general_history_parity_result_v2",
]
