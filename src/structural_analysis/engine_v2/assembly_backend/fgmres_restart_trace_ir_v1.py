"""Diagnostic restart-trace IR derived from general FGMRES history parity v2.

The general-history parity receipt proves restart-by-restart CPU/HIP numerical
agreement.  It is not a result payload.  This module projects that receipt into
an explicitly diagnostic trace whose vector data are referenced by hash only.
The trace cannot commit solver state, authorize a final solution, or issue a
ResultIR.  Projection performs no device operation, transfer, solve, or export.
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

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_general_history_parity_v2 import (
    HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2,
    HipFgmresGeneralHistoryParityReceiptV2,
    HipFgmresGeneralHistoryParityResultV2,
    HipFgmresGeneralHistoryRowV2,
    HipFgmresHistoryScalarEnvelopeV2,
    HipFgmresHistoryVectorComparisonV2,
    validate_hip_fgmres_general_history_parity_receipt_v2,
    validate_hip_fgmres_general_history_parity_result_v2,
)


HIP_FGMRES_RESTART_TRACE_IR_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-restart-trace-ir.v1"
)
HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1 = (
    "phase0_general_history_diagnostic_restart_trace_ir_v1"
)
HIP_FGMRES_RESTART_TRACE_IR_EVIDENCE_SCOPE_V1 = (
    "derived_from_process_local_general_history_parity_v2_non_promoting"
)
HIP_FGMRES_RESTART_TRACE_IR_ARTIFACT_KIND_V1 = "solver_restart_diagnostic_trace"

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARCHITECTURE_RE = re.compile(r"^gfx[0-9a-f]+$")
_SCHEMA_RESOURCE = "hip_fgmres_restart_trace_ir_v1.schema.json"


class HipFgmresRestartTraceIRV1Error(RuntimeError):
    """Stable fail-closed restart-trace contract error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceVectorReferenceV1:
    role: Literal["checkpoint_solution", "checkpoint_true_residual"]
    value_count: int
    cpu_reference_sha256: str
    hip_candidate_sha256: str
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
class HipFgmresRestartTraceMetricV1:
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
class HipFgmresRestartTraceRowV1:
    sequence_index: int
    semantic_role: Literal["restart_checkpoint_diagnostic"]
    terminal_row_in_trace: bool
    source_history_row_hash: str
    restart_index: int
    slot_index: int
    column_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    reorthogonalization_count: int
    termination_hint: str
    flags: int
    solution: HipFgmresRestartTraceVectorReferenceV1
    true_residual: HipFgmresRestartTraceVectorReferenceV1
    residual_roundoff_receipt_hash: str
    residual_roundoff_maximum_componentwise_ratio: float
    true_residual_l2: HipFgmresRestartTraceMetricV1
    true_residual_linf: HipFgmresRestartTraceMetricV1
    scaled_true_residual: HipFgmresRestartTraceMetricV1
    estimated_residual_l2: HipFgmresRestartTraceMetricV1
    solution_update_l2: HipFgmresRestartTraceMetricV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_index": self.sequence_index,
            "semantic_role": self.semantic_role,
            "terminal_row_in_trace": self.terminal_row_in_trace,
            "source_history_row_hash": self.source_history_row_hash,
            "restart_index": self.restart_index,
            "slot_index": self.slot_index,
            "column_index": self.column_index,
            "start_iteration": self.start_iteration,
            "end_iteration": self.end_iteration,
            "arnoldi_step_count": self.arnoldi_step_count,
            "reorthogonalization_count": self.reorthogonalization_count,
            "termination_hint": self.termination_hint,
            "flags": self.flags,
            "solution": self.solution.to_dict(),
            "true_residual": self.true_residual.to_dict(),
            "residual_roundoff_receipt_hash": (self.residual_roundoff_receipt_hash),
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
class HipFgmresRestartTraceBindingsV1:
    source_general_history_schema_version: str
    source_parity_id: str
    source_parity_receipt_hash: str
    source_general_history_bindings_hash: str
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
class HipFgmresRestartTraceDimensionsV1:
    free_dof_count: int
    maximum_restart_count: int
    trace_row_count: int
    referenced_vector_count: int
    referenced_scalar_metric_count: int
    embedded_numeric_vector_byte_count: Literal[0] = 0
    result_array_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceSummaryV1:
    first_restart_index: int | None
    last_restart_index: int | None
    first_start_iteration: int | None
    last_end_iteration: int | None
    terminal_trace_row_count: int
    monotonic_restart_and_iteration_order_verified: Literal[True] = True
    all_solution_vector_gates_passed: Literal[True] = True
    all_metric_bounds_passed: Literal[True] = True
    result_ir_binding_count: Literal[0] = 0

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceTelemetryV1:
    source_general_history_receipt_validation_count: Literal[1] = 1
    source_row_projection_count: int = 0
    source_row_hash_count: int = 0
    vector_reference_projection_count: int = 0
    scalar_envelope_projection_count: int = 0
    numeric_vector_payload_copy_count: Literal[0] = 0
    state_commit_count: Literal[0] = 0
    result_ir_build_count: Literal[0] = 0
    additional_device_operation_count: Literal[0] = 0
    additional_d2h_operation_count: Literal[0] = 0
    additional_solve_count: Literal[0] = 0
    additional_export_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceClaimsV1:
    diagnostic_restart_trace_ir_v1_ready: Literal[True] = True
    source_general_history_parity_v2_bound: Literal[True] = True
    ordered_restart_rows_preserved: Literal[True] = True
    source_row_hashes_preserved: Literal[True] = True
    vector_payloads_referenced_by_hash_only: Literal[True] = True
    scalar_roundoff_envelopes_preserved: Literal[True] = True
    result_ir_semantics_separated: Literal[True] = True
    final_solution_authority_absent: Literal[True] = True
    state_commit_authority_absent: Literal[True] = True
    additional_device_transfer_solve_or_export_zero: Literal[True] = True
    raw_checkpoint_vectors_embedded: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    result_ir_issuance_authorized: Literal[False] = False
    standalone_provenance: Literal[False] = False
    signed_evidence: Literal[False] = False
    multi_architecture_parity_verified: Literal[False] = False
    iteration_host_copy_zero_process_wide: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceIRReceiptV1:
    schema_version: str
    capability_profile: str
    status: Literal["diagnostic_restart_trace_ir_v1_ready"]
    evidence_scope: str
    artifact_kind: str
    promotion_eligible: Literal[False]
    trace_id: str
    bindings: HipFgmresRestartTraceBindingsV1
    dimensions: HipFgmresRestartTraceDimensionsV1
    summary: HipFgmresRestartTraceSummaryV1
    rows: tuple[HipFgmresRestartTraceRowV1, ...]
    telemetry: HipFgmresRestartTraceTelemetryV1
    claims: HipFgmresRestartTraceClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_restart_trace_ir_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresRestartTraceIRResultV1:
    receipt: HipFgmresRestartTraceIRReceiptV1
    source_general_history: HipFgmresGeneralHistoryParityResultV2

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_restart_trace_ir_result_v1(self)
        return self.receipt.to_dict()


def build_hip_fgmres_restart_trace_ir_receipt_v1(
    source: HipFgmresGeneralHistoryParityReceiptV2,
) -> HipFgmresRestartTraceIRReceiptV1:
    """Project one validated detached parity receipt into diagnostic trace wire."""

    if type(source) is not HipFgmresGeneralHistoryParityReceiptV2:
        _fail("hip_fgmres_restart_trace_source_receipt_type_invalid", "/source")
    validate_hip_fgmres_general_history_parity_receipt_v2(source)
    count = len(source.rows)
    rows = tuple(
        _project_row(
            row,
            sequence_index=index,
            row_count=count,
            terminal=index == count - 1,
        )
        for index, row in enumerate(source.rows)
    )
    source_bindings = source.bindings
    bindings = HipFgmresRestartTraceBindingsV1(
        source_general_history_schema_version=source.schema_version,
        source_parity_id=source.parity_id,
        source_parity_receipt_hash=source.receipt_hash,
        source_general_history_bindings_hash=canonical_hash(source_bindings.to_dict()),
        execution_plan_hash=source_bindings.execution_plan_hash,
        operator_hash=source_bindings.operator_hash,
        policy_hash=source_bindings.policy_hash,
        cpu_checkpoint_history_result_hash=(
            source_bindings.cpu_checkpoint_history_result_hash
        ),
        cpu_base_result_hash=source_bindings.cpu_base_result_hash,
        completion_export_v2_context_id=(
            source_bindings.completion_export_v2_context_id
        ),
        completion_export_v2_receipt_hash=(
            source_bindings.completion_export_v2_receipt_hash
        ),
        completion_export_v2_payload_hash=(
            source_bindings.completion_export_v2_payload_hash
        ),
        retained_completion_export_v1_receipt_hash=(
            source_bindings.retained_completion_export_v1_receipt_hash
        ),
        checkpoint_history_export_v1_receipt_hash=(
            source_bindings.checkpoint_history_export_v1_receipt_hash
        ),
        terminal_observation_receipt_hash=(
            source_bindings.terminal_observation_receipt_hash
        ),
        global_context_id=source_bindings.global_context_id,
        history_plan_hash=source_bindings.history_plan_hash,
        history_blob_abi_hash=source_bindings.history_blob_abi_hash,
        recurrence_plan_hash=source_bindings.recurrence_plan_hash,
        recurrence_kernel_identity_hash=(
            source_bindings.recurrence_kernel_identity_hash
        ),
        architecture=source_bindings.architecture,
        device_ordinal=source_bindings.device_ordinal,
    )
    dimensions = HipFgmresRestartTraceDimensionsV1(
        free_dof_count=source.dimensions.free_dof_count,
        maximum_restart_count=source.dimensions.maximum_restart_count,
        trace_row_count=count,
        referenced_vector_count=2 * count,
        referenced_scalar_metric_count=5 * count,
    )
    summary = HipFgmresRestartTraceSummaryV1(
        first_restart_index=None if not rows else rows[0].restart_index,
        last_restart_index=None if not rows else rows[-1].restart_index,
        first_start_iteration=None if not rows else rows[0].start_iteration,
        last_end_iteration=None if not rows else rows[-1].end_iteration,
        terminal_trace_row_count=0 if not rows else 1,
    )
    telemetry = HipFgmresRestartTraceTelemetryV1(
        source_row_projection_count=count,
        source_row_hash_count=count,
        vector_reference_projection_count=2 * count,
        scalar_envelope_projection_count=5 * count,
    )
    trace_id = canonical_hash(
        {
            "profile": HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1,
            "source_parity_id": source.parity_id,
            "source_parity_receipt_hash": source.receipt_hash,
            "source_bindings_hash": bindings.source_general_history_bindings_hash,
            "source_row_hashes": [row.source_history_row_hash for row in rows],
        }
    )
    draft = HipFgmresRestartTraceIRReceiptV1(
        schema_version=HIP_FGMRES_RESTART_TRACE_IR_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1,
        status="diagnostic_restart_trace_ir_v1_ready",
        evidence_scope=HIP_FGMRES_RESTART_TRACE_IR_EVIDENCE_SCOPE_V1,
        artifact_kind=HIP_FGMRES_RESTART_TRACE_IR_ARTIFACT_KIND_V1,
        promotion_eligible=False,
        trace_id=trace_id,
        bindings=bindings,
        dimensions=dimensions,
        summary=summary,
        rows=rows,
        telemetry=telemetry,
        claims=HipFgmresRestartTraceClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_restart_trace_ir_receipt_v1(receipt)


def build_hip_fgmres_restart_trace_ir_v1(
    source: HipFgmresGeneralHistoryParityResultV2,
) -> HipFgmresRestartTraceIRResultV1:
    """Build an attached trace after replaying the complete parity result."""

    if type(source) is not HipFgmresGeneralHistoryParityResultV2:
        _fail("hip_fgmres_restart_trace_source_result_type_invalid", "/source")
    validate_hip_fgmres_general_history_parity_result_v2(source)
    result = HipFgmresRestartTraceIRResultV1(
        receipt=build_hip_fgmres_restart_trace_ir_receipt_v1(source.receipt),
        source_general_history=source,
    )
    return validate_hip_fgmres_restart_trace_ir_result_v1(result)


def validate_hip_fgmres_restart_trace_ir_receipt_v1(
    receipt: HipFgmresRestartTraceIRReceiptV1,
) -> HipFgmresRestartTraceIRReceiptV1:
    """Validate the strict detached trace without granting source provenance."""

    if type(receipt) is not HipFgmresRestartTraceIRReceiptV1:
        _fail("hip_fgmres_restart_trace_receipt_type_invalid", "/")
    nested = (
        (receipt.bindings, HipFgmresRestartTraceBindingsV1, "/bindings"),
        (receipt.dimensions, HipFgmresRestartTraceDimensionsV1, "/dimensions"),
        (receipt.summary, HipFgmresRestartTraceSummaryV1, "/summary"),
        (receipt.telemetry, HipFgmresRestartTraceTelemetryV1, "/telemetry"),
        (receipt.claims, HipFgmresRestartTraceClaimsV1, "/claims"),
    )
    for value, expected, path in nested:
        if type(value) is not expected:
            _fail("hip_fgmres_restart_trace_nested_type_invalid", path)
    if type(receipt.rows) is not tuple:
        _fail("hip_fgmres_restart_trace_rows_type_invalid", "/rows")
    for index, row in enumerate(receipt.rows):
        _validate_row(row, index=index, row_count=len(receipt.rows))
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_restart_trace_schema_invalid", path, error.message)
    if (
        receipt.schema_version != HIP_FGMRES_RESTART_TRACE_IR_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1
        or receipt.status != "diagnostic_restart_trace_ir_v1_ready"
        or receipt.evidence_scope != HIP_FGMRES_RESTART_TRACE_IR_EVIDENCE_SCOPE_V1
        or receipt.artifact_kind != HIP_FGMRES_RESTART_TRACE_IR_ARTIFACT_KIND_V1
        or receipt.promotion_eligible is not False
        or receipt.claims != HipFgmresRestartTraceClaimsV1()
    ):
        _fail("hip_fgmres_restart_trace_semantics_invalid", "/")
    _validate_bindings(receipt.bindings)
    _validate_dimensions_and_summary(receipt)
    _validate_telemetry(receipt)
    expected_trace_id = canonical_hash(
        {
            "profile": HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1,
            "source_parity_id": receipt.bindings.source_parity_id,
            "source_parity_receipt_hash": (receipt.bindings.source_parity_receipt_hash),
            "source_bindings_hash": (
                receipt.bindings.source_general_history_bindings_hash
            ),
            "source_row_hashes": [row.source_history_row_hash for row in receipt.rows],
        }
    )
    if receipt.trace_id != expected_trace_id:
        _fail("hip_fgmres_restart_trace_id_invalid", "/trace_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if receipt.receipt_hash != expected_hash:
        _fail("hip_fgmres_restart_trace_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_restart_trace_ir_result_v1(
    result: HipFgmresRestartTraceIRResultV1,
) -> HipFgmresRestartTraceIRResultV1:
    """Replay the full source and require an exact deterministic projection."""

    if type(result) is not HipFgmresRestartTraceIRResultV1:
        _fail("hip_fgmres_restart_trace_result_type_invalid", "/")
    validate_hip_fgmres_restart_trace_ir_receipt_v1(result.receipt)
    if type(result.source_general_history) is not HipFgmresGeneralHistoryParityResultV2:
        _fail("hip_fgmres_restart_trace_source_result_type_invalid", "/source")
    validate_hip_fgmres_general_history_parity_result_v2(result.source_general_history)
    expected = build_hip_fgmres_restart_trace_ir_receipt_v1(
        result.source_general_history.receipt
    )
    if result.receipt != expected:
        _fail("hip_fgmres_restart_trace_source_binding_invalid", "/source")
    return result


def _project_row(
    source: HipFgmresGeneralHistoryRowV2,
    *,
    sequence_index: int,
    row_count: int,
    terminal: bool,
) -> HipFgmresRestartTraceRowV1:
    if type(source) is not HipFgmresGeneralHistoryRowV2:
        _fail("hip_fgmres_restart_trace_source_row_type_invalid", "/source/rows")
    solution = _project_vector(source.solution)
    residual = _project_vector(source.true_residual)
    metrics = tuple(
        _project_metric(value)
        for value in (
            source.true_residual_l2,
            source.true_residual_linf,
            source.scaled_true_residual,
            source.estimated_residual_l2,
            source.solution_update_l2,
        )
    )
    row = HipFgmresRestartTraceRowV1(
        sequence_index=sequence_index,
        semantic_role="restart_checkpoint_diagnostic",
        terminal_row_in_trace=terminal,
        source_history_row_hash=canonical_hash(source.to_dict()),
        restart_index=source.restart_index,
        slot_index=source.slot_index,
        column_index=source.column_index,
        start_iteration=source.start_iteration,
        end_iteration=source.end_iteration,
        arnoldi_step_count=source.arnoldi_step_count,
        reorthogonalization_count=source.reorthogonalization_count,
        termination_hint=source.termination_hint,
        flags=source.flags,
        solution=solution,
        true_residual=residual,
        residual_roundoff_receipt_hash=source.residual_roundoff_receipt_hash,
        residual_roundoff_maximum_componentwise_ratio=(
            source.residual_roundoff_maximum_componentwise_ratio
        ),
        true_residual_l2=metrics[0],
        true_residual_linf=metrics[1],
        scaled_true_residual=metrics[2],
        estimated_residual_l2=metrics[3],
        solution_update_l2=metrics[4],
    )
    _validate_row(row, index=sequence_index, row_count=row_count)
    return row


def _project_vector(
    source: HipFgmresHistoryVectorComparisonV2,
) -> HipFgmresRestartTraceVectorReferenceV1:
    if type(source) is not HipFgmresHistoryVectorComparisonV2:
        _fail("hip_fgmres_restart_trace_source_vector_type_invalid", "/source/rows")
    return HipFgmresRestartTraceVectorReferenceV1(
        role=source.name,
        value_count=source.value_count,
        cpu_reference_sha256=source.reference_sha256,
        hip_candidate_sha256=source.candidate_sha256,
        maximum_absolute_error=source.maximum_absolute_error,
        difference_l2=source.difference_l2,
        reference_l2=source.reference_l2,
        relative_l2_error=source.relative_l2_error,
        fixed_absolute_tolerance=source.fixed_absolute_tolerance,
        fixed_relative_tolerance=source.fixed_relative_tolerance,
        fixed_componentwise_gate_passed=source.fixed_componentwise_gate_passed,
    )


def _project_metric(
    source: HipFgmresHistoryScalarEnvelopeV2,
) -> HipFgmresRestartTraceMetricV1:
    if type(source) is not HipFgmresHistoryScalarEnvelopeV2:
        _fail("hip_fgmres_restart_trace_source_metric_type_invalid", "/source/rows")
    return HipFgmresRestartTraceMetricV1(
        name=source.name,
        cpu_value=source.cpu_value,
        hip_value=source.hip_value,
        absolute_difference=source.absolute_difference,
        vector_transport_bound=source.vector_transport_bound,
        cpu_estimator_or_replay_gap=source.cpu_estimator_or_replay_gap,
        hip_estimator_or_replay_gap=source.hip_estimator_or_replay_gap,
        fp_roundoff_guard=source.fp_roundoff_guard,
        total_bound=source.total_bound,
        maximum_bound_ratio=source.maximum_bound_ratio,
        outward_rounding_used=source.outward_rounding_used,
        bound_passed=source.bound_passed,
    )


def _validate_row(
    row: HipFgmresRestartTraceRowV1,
    *,
    index: int,
    row_count: int,
) -> None:
    path = f"/rows/{index}"
    if type(row) is not HipFgmresRestartTraceRowV1:
        _fail("hip_fgmres_restart_trace_row_type_invalid", path)
    if (
        type(row.solution) is not HipFgmresRestartTraceVectorReferenceV1
        or type(row.true_residual) is not HipFgmresRestartTraceVectorReferenceV1
    ):
        _fail("hip_fgmres_restart_trace_vector_type_invalid", path)
    metrics = (
        row.true_residual_l2,
        row.true_residual_linf,
        row.scaled_true_residual,
        row.estimated_residual_l2,
        row.solution_update_l2,
    )
    if any(type(metric) is not HipFgmresRestartTraceMetricV1 for metric in metrics):
        _fail("hip_fgmres_restart_trace_metric_type_invalid", path)
    if (
        type(row.sequence_index) is not int
        or row.sequence_index != index
        or row.semantic_role != "restart_checkpoint_diagnostic"
        or type(row.terminal_row_in_trace) is not bool
        or row.terminal_row_in_trace is not (index == row_count - 1)
        or row.restart_index != index + 1
        or row.slot_index != index + 1
        or row.column_index != row.arnoldi_step_count - 1
        or row.start_iteration < 0
        or row.end_iteration <= row.start_iteration
        or row.arnoldi_step_count <= 0
        or row.reorthogonalization_count < 0
        or not row.termination_hint
        or row.flags < 0
        or _HASH_RE.fullmatch(row.residual_roundoff_receipt_hash) is None
        or not _finite_ratio(row.residual_roundoff_maximum_componentwise_ratio)
    ):
        _fail("hip_fgmres_restart_trace_row_invalid", path)
    _validate_vector(row.solution, expected_role="checkpoint_solution", path=path)
    _validate_vector(
        row.true_residual,
        expected_role="checkpoint_true_residual",
        path=path,
    )
    expected_metric_names = (
        "true_residual_l2",
        "true_residual_linf",
        "scaled_true_residual",
        "estimated_residual_l2",
        "solution_update_l2",
    )
    for metric, expected_name in zip(metrics, expected_metric_names, strict=True):
        _validate_metric(metric, expected_name=expected_name, path=path)
    if row.source_history_row_hash != canonical_hash(_source_row_payload(row)):
        _fail("hip_fgmres_restart_trace_source_row_hash_invalid", path)


def _validate_vector(
    vector: HipFgmresRestartTraceVectorReferenceV1,
    *,
    expected_role: str,
    path: str,
) -> None:
    numeric = (
        vector.maximum_absolute_error,
        vector.difference_l2,
        vector.reference_l2,
        vector.relative_l2_error,
        vector.fixed_absolute_tolerance,
        vector.fixed_relative_tolerance,
    )
    if (
        vector.role != expected_role
        or type(vector.value_count) is not int
        or vector.value_count <= 0
        or _HASH_RE.fullmatch(vector.cpu_reference_sha256) is None
        or _HASH_RE.fullmatch(vector.hip_candidate_sha256) is None
        or any(not _finite_nonnegative(value) for value in numeric)
        or vector.fixed_absolute_tolerance != 1.0e-12
        or vector.fixed_relative_tolerance != 1.0e-8
        or type(vector.fixed_componentwise_gate_passed) is not bool
        or (
            expected_role == "checkpoint_solution"
            and vector.fixed_componentwise_gate_passed is not True
        )
    ):
        _fail("hip_fgmres_restart_trace_vector_invalid", path)


def _validate_metric(
    metric: HipFgmresRestartTraceMetricV1,
    *,
    expected_name: str,
    path: str,
) -> None:
    numeric = (
        metric.cpu_value,
        metric.hip_value,
        metric.absolute_difference,
        metric.vector_transport_bound,
        metric.cpu_estimator_or_replay_gap,
        metric.hip_estimator_or_replay_gap,
        metric.fp_roundoff_guard,
        metric.total_bound,
    )
    if (
        metric.name != expected_name
        or any(not _finite_nonnegative(value) for value in numeric)
        or not _finite_ratio(metric.maximum_bound_ratio)
        or metric.absolute_difference > metric.total_bound
        or metric.outward_rounding_used is not True
        or metric.bound_passed is not True
    ):
        _fail("hip_fgmres_restart_trace_metric_invalid", path)


def _validate_bindings(bindings: HipFgmresRestartTraceBindingsV1) -> None:
    if (
        bindings.source_general_history_schema_version
        != HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2
        or any(
            _HASH_RE.fullmatch(getattr(bindings, name)) is None
            for name in bindings.__dataclass_fields__
            if name
            not in {
                "source_general_history_schema_version",
                "architecture",
                "device_ordinal",
            }
        )
        or _ARCHITECTURE_RE.fullmatch(bindings.architecture) is None
        or type(bindings.device_ordinal) is not int
        or bindings.device_ordinal < 0
        or bindings.source_general_history_bindings_hash
        != canonical_hash(_source_bindings_payload(bindings))
    ):
        _fail("hip_fgmres_restart_trace_bindings_invalid", "/bindings")


def _validate_dimensions_and_summary(
    receipt: HipFgmresRestartTraceIRReceiptV1,
) -> None:
    dimensions = receipt.dimensions
    count = len(receipt.rows)
    if (
        any(
            type(getattr(dimensions, name)) is not int
            for name in dimensions.__dataclass_fields__
        )
        or dimensions.free_dof_count <= 0
        or dimensions.maximum_restart_count <= 0
        or count > dimensions.maximum_restart_count
        or dimensions.trace_row_count != count
        or dimensions.referenced_vector_count != 2 * count
        or dimensions.referenced_scalar_metric_count != 5 * count
        or dimensions.embedded_numeric_vector_byte_count != 0
        or dimensions.result_array_count != 0
        or any(
            row.solution.value_count != dimensions.free_dof_count
            or row.true_residual.value_count != dimensions.free_dof_count
            for row in receipt.rows
        )
    ):
        _fail("hip_fgmres_restart_trace_dimensions_invalid", "/dimensions")
    summary = receipt.summary
    expected = HipFgmresRestartTraceSummaryV1(
        first_restart_index=None if not receipt.rows else receipt.rows[0].restart_index,
        last_restart_index=None if not receipt.rows else receipt.rows[-1].restart_index,
        first_start_iteration=None
        if not receipt.rows
        else receipt.rows[0].start_iteration,
        last_end_iteration=None if not receipt.rows else receipt.rows[-1].end_iteration,
        terminal_trace_row_count=0 if not receipt.rows else 1,
    )
    if summary != expected:
        _fail("hip_fgmres_restart_trace_summary_invalid", "/summary")
    previous_end = -1
    for row in receipt.rows:
        if row.start_iteration < previous_end or row.end_iteration <= previous_end:
            _fail("hip_fgmres_restart_trace_order_invalid", "/rows")
        previous_end = row.end_iteration


def _validate_telemetry(receipt: HipFgmresRestartTraceIRReceiptV1) -> None:
    count = len(receipt.rows)
    expected = HipFgmresRestartTraceTelemetryV1(
        source_row_projection_count=count,
        source_row_hash_count=count,
        vector_reference_projection_count=2 * count,
        scalar_envelope_projection_count=5 * count,
    )
    if receipt.telemetry != expected:
        _fail("hip_fgmres_restart_trace_telemetry_invalid", "/telemetry")


def _source_bindings_payload(
    bindings: HipFgmresRestartTraceBindingsV1,
) -> dict[str, Any]:
    excluded = {
        "source_general_history_schema_version",
        "source_parity_id",
        "source_parity_receipt_hash",
        "source_general_history_bindings_hash",
    }
    return {
        name: getattr(bindings, name)
        for name in bindings.__dataclass_fields__
        if name not in excluded
    }


def _source_row_payload(row: HipFgmresRestartTraceRowV1) -> dict[str, Any]:
    return {
        "restart_index": row.restart_index,
        "slot_index": row.slot_index,
        "column_index": row.column_index,
        "start_iteration": row.start_iteration,
        "end_iteration": row.end_iteration,
        "arnoldi_step_count": row.arnoldi_step_count,
        "reorthogonalization_count": row.reorthogonalization_count,
        "termination_hint": row.termination_hint,
        "flags": row.flags,
        "capture_metadata_matches_solve_record": True,
        "gpu_true_residual_l2_tree_replayed": True,
        "gpu_true_residual_linf_tree_replayed": True,
        "gpu_scaled_true_residual_replayed": True,
        "gpu_solution_update_l2_tree_replayed": True,
        "solution": _source_vector_payload(row.solution),
        "true_residual": _source_vector_payload(row.true_residual),
        "residual_roundoff_receipt_hash": row.residual_roundoff_receipt_hash,
        "residual_roundoff_maximum_componentwise_ratio": (
            row.residual_roundoff_maximum_componentwise_ratio
        ),
        "metrics": {
            "true_residual_l2": row.true_residual_l2.to_dict(),
            "true_residual_linf": row.true_residual_linf.to_dict(),
            "scaled_true_residual": row.scaled_true_residual.to_dict(),
            "estimated_residual_l2": row.estimated_residual_l2.to_dict(),
            "solution_update_l2": row.solution_update_l2.to_dict(),
        },
    }


def _source_vector_payload(
    vector: HipFgmresRestartTraceVectorReferenceV1,
) -> dict[str, Any]:
    return {
        "name": vector.role,
        "value_count": vector.value_count,
        "reference_sha256": vector.cpu_reference_sha256,
        "candidate_sha256": vector.hip_candidate_sha256,
        "maximum_absolute_error": vector.maximum_absolute_error,
        "difference_l2": vector.difference_l2,
        "reference_l2": vector.reference_l2,
        "relative_l2_error": vector.relative_l2_error,
        "fixed_absolute_tolerance": vector.fixed_absolute_tolerance,
        "fixed_relative_tolerance": vector.fixed_relative_tolerance,
        "fixed_componentwise_gate_passed": vector.fixed_componentwise_gate_passed,
    }


def _receipt_payload(
    receipt: HipFgmresRestartTraceIRReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "artifact_kind": receipt.artifact_kind,
        "promotion_eligible": receipt.promotion_eligible,
        "trace_id": receipt.trace_id,
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "summary": receipt.summary.to_dict(),
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
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _finite_nonnegative(value: Any) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


def _finite_ratio(value: Any) -> bool:
    return _finite_nonnegative(value) and value <= 1.0


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresRestartTraceIRV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_RESTART_TRACE_IR_ARTIFACT_KIND_V1",
    "HIP_FGMRES_RESTART_TRACE_IR_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_RESTART_TRACE_IR_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_RESTART_TRACE_IR_SCHEMA_VERSION_V1",
    "HipFgmresRestartTraceBindingsV1",
    "HipFgmresRestartTraceClaimsV1",
    "HipFgmresRestartTraceDimensionsV1",
    "HipFgmresRestartTraceIRReceiptV1",
    "HipFgmresRestartTraceIRResultV1",
    "HipFgmresRestartTraceIRV1Error",
    "HipFgmresRestartTraceMetricV1",
    "HipFgmresRestartTraceRowV1",
    "HipFgmresRestartTraceSummaryV1",
    "HipFgmresRestartTraceTelemetryV1",
    "HipFgmresRestartTraceVectorReferenceV1",
    "build_hip_fgmres_restart_trace_ir_receipt_v1",
    "build_hip_fgmres_restart_trace_ir_v1",
    "validate_hip_fgmres_restart_trace_ir_receipt_v1",
    "validate_hip_fgmres_restart_trace_ir_result_v1",
]
