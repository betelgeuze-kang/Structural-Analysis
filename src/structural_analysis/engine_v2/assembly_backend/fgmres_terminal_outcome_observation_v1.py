"""Host-side terminal-outcome observation for an exported HIP FGMRES solve.

This module is deliberately downstream of the completion-only exporter.  It
does not issue HIP operations or mutate the raw export receipt.  Instead it
decodes the immutable little-endian solve record, validates terminal semantics
and payload consistency, and publishes a separate non-promoting receipt.

The observer proves only that one context-bound device record reports a
well-formed terminal outcome.  It does not prove CPU/HIP numerical parity,
equilibrium closure, solution readiness, ResultIR readiness, iteration
host-copy zero, performance, or commercial readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import struct
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    FgmresGpuTreeReferenceV2Error,
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)

from .fgmres_completion_export_v1 import (
    HipFgmresCompletionExportExecutionContextV1,
    HipFgmresCompletionExportResultV1,
    _CompletionExportPolicySnapshotV1,
    validate_hip_fgmres_completion_export_result_v1,
)
from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_MAX_RESTART_DIMENSION,
)
from .fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)


HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-terminal-outcome-observation.v1"
)
HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_CAPABILITY_PROFILE_V1 = (
    "phase0_completion_export_bound_terminal_record_observer"
)
HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1 = (
    "context_bound_terminal_record_semantics_observed_non_promoting"
)

TerminalObservationStatusV1 = Literal[
    "terminal_converged",
    "terminal_not_converged",
    "terminal_numerical_failure",
]
TerminalOutcomeClassV1 = Literal[
    "converged",
    "not_converged",
    "numerical_failure",
]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCHEMA_RESOURCE = "hip_fgmres_terminal_outcome_observation_v1.schema.json"
_HEADER_BYTES = 192
_RESTART_BYTES = 72
_SQRT_EPSILON = float.fromhex("0x1p-26")
_BREAKDOWN_TAU = float.fromhex("0x1p-46")

_STATUS_TO_TERMINATION_CODES = {
    "converged": {
        "converged_initial_true_residual",
        "converged_happy_breakdown",
        "converged_true_residual",
        "converged_restart_true_residual",
    },
    "max_iterations": {"max_iterations_exhausted"},
    "stagnated": {"true_residual_stagnated"},
    "diverged": {"true_residual_diverged"},
    "arnoldi_breakdown": {
        "arnoldi_triangular_factor_breakdown",
        "arnoldi_invariant_subspace_breakdown",
    },
    "numerical_failure": {
        "invalid_input_or_control",
        "nonfinite_arithmetic",
        "operator_application_failed",
        "orthogonalization_failed",
        "givens_rotation_failed",
        "triangular_solve_failed",
        "true_residual_replay_failed",
        "restart_state_failed",
    },
}
_TERMINATION_TO_LAST_HINT = {
    "converged_happy_breakdown": "converged_happy_breakdown",
    "converged_true_residual": "converged_true_residual",
    "converged_restart_true_residual": "restart_completed",
    "max_iterations_exhausted": "restart_completed",
    "true_residual_stagnated": "restart_completed",
    "true_residual_diverged": "restart_completed",
    "arnoldi_triangular_factor_breakdown": ("arnoldi_triangular_factor_breakdown"),
    "arnoldi_invariant_subspace_breakdown": ("arnoldi_invariant_subspace_breakdown"),
}


class HipFgmresTerminalOutcomeObservationV1Error(ValueError):
    """Stable fail-closed observer error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationBindingsV1:
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    completion_export_source_binding_hash: str
    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    solve_record_abi_hash: str
    control_state_abi_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    continuation_schedule_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    architecture: str
    device_ordinal: int
    policy_hash: str
    solution_payload_sha256: str
    true_residual_payload_sha256: str
    solve_record_payload_sha256: str
    process_local_export_context_verified: Literal[True] = True
    process_local_result_identity_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationDimensionsV1:
    free_dof_count: int
    maximum_restart_count: int
    solve_record_header_bytes: Literal[192] = 192
    solve_record_restart_bytes: Literal[72] = 72
    solve_record_byte_count: int = 0
    inspected_host_payload_byte_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomePolicySnapshotV1:
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    stagnation_checkpoint_limit: int
    absolute_tolerance: float
    relative_tolerance: float
    authoritative_tolerance: float
    stagnation_relative_tolerance: float
    divergence_factor: float

    def to_dict(self) -> dict[str, int | float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeCountersV1:
    scheduled_iterations: int
    effective_iterations: int
    scheduled_restarts: int
    effective_restarts: int
    effective_arnoldi_dimension: int
    happy_breakdown_count: int
    stagnation_checkpoint_count: int
    false_convergence_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    restart_dimension: int

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeMetricsV1:
    rhs_l2: float
    rhs_linf: float
    solver_tolerance_l2: float
    authoritative_tolerance_scaled_linf: float
    initial_residual_l2: float
    final_residual_l2: float
    final_residual_linf: float
    final_scaled_residual: float
    previous_checkpoint_residual_l2: float
    solution_update_l2: float
    solution_scale_l2: float
    estimated_residual_l2: float
    arnoldi_work_l2: float
    arnoldi_breakdown_threshold: float
    triangular_scale: float

    def to_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeRestartRowV1:
    slot_index: int
    populated: bool
    restart_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    reorthogonalization_count: int
    termination_hint: str
    termination_hint_code: int
    flags: int
    flag_names: tuple[str, ...]
    estimated_residual_l2: float
    true_residual_l2: float
    true_residual_linf: float
    scaled_true_residual: float
    solution_update_l2: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "populated": self.populated,
            "restart_index": self.restart_index,
            "start_iteration": self.start_iteration,
            "end_iteration": self.end_iteration,
            "arnoldi_step_count": self.arnoldi_step_count,
            "reorthogonalization_count": self.reorthogonalization_count,
            "termination_hint": self.termination_hint,
            "termination_hint_code": self.termination_hint_code,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "estimated_residual_l2": self.estimated_residual_l2,
            "true_residual_l2": self.true_residual_l2,
            "true_residual_linf": self.true_residual_linf,
            "scaled_true_residual": self.scaled_true_residual,
            "solution_update_l2": self.solution_update_l2,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeV1:
    outcome_class: TerminalOutcomeClassV1
    active: Literal[0]
    terminal_status: str
    terminal_status_code: int
    termination_code: str
    termination_code_value: int
    device_error_bits: int
    device_error_names: tuple[str, ...]
    counters: HipFgmresTerminalOutcomeCountersV1
    record_metrics_authoritative: bool
    metrics: HipFgmresTerminalOutcomeMetricsV1 | None
    restart_rows: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...]
    solution_x_all_finite: bool
    true_residual_all_finite: bool
    observed_solution_x_l2: float | None
    observed_true_residual_l2: float | None
    observed_true_residual_linf: float | None
    observed_true_residual_scaled_linf: float | None
    true_residual_record_metrics_match: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_class": self.outcome_class,
            "active": self.active,
            "terminal_status": self.terminal_status,
            "terminal_status_code": self.terminal_status_code,
            "termination_code": self.termination_code,
            "termination_code_value": self.termination_code_value,
            "device_error_bits": self.device_error_bits,
            "device_error_names": list(self.device_error_names),
            "counters": self.counters.to_dict(),
            "record_metrics_authoritative": self.record_metrics_authoritative,
            "metrics": None if self.metrics is None else self.metrics.to_dict(),
            "restart_rows": [row.to_dict() for row in self.restart_rows],
            "solution_x_all_finite": self.solution_x_all_finite,
            "true_residual_all_finite": self.true_residual_all_finite,
            "observed_solution_x_l2": self.observed_solution_x_l2,
            "observed_true_residual_l2": self.observed_true_residual_l2,
            "observed_true_residual_linf": self.observed_true_residual_linf,
            "observed_true_residual_scaled_linf": (
                self.observed_true_residual_scaled_linf
            ),
            "true_residual_record_metrics_match": (
                self.true_residual_record_metrics_match
            ),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationTelemetryV1:
    completion_export_source_result_count: Literal[1] = 1
    solve_record_payload_count: Literal[1] = 1
    solve_record_header_field_count: Literal[32] = 32
    solve_record_restart_row_count: int = 0
    inspected_host_payload_byte_count: int = 0
    published_terminal_outcome_count: Literal[1] = 1
    additional_d2h_operation_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    device_allocation_count: Literal[0] = 0
    allocation_borrow_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    explicit_stream_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationClaimsV1:
    completion_export_result_bound: Literal[True] = True
    raw_export_receipt_preserved: Literal[True] = True
    solve_record_semantics_interpreted: Literal[True] = True
    actual_terminal_outcome_host_observed: Literal[True] = True
    terminal_record_invariants_verified: Literal[True] = True
    process_local_export_provenance_verified: bool = False
    authoritative_terminal_status_proven: bool = False
    no_additional_device_operation: Literal[True] = True
    authoritative_completion_or_solution_receipt: Literal[False] = False
    numerical_parity_verified: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationReceiptV1:
    status: TerminalObservationStatusV1
    observation_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresTerminalOutcomeObservationBindingsV1
    dimensions: HipFgmresTerminalOutcomeObservationDimensionsV1
    policy: HipFgmresTerminalOutcomePolicySnapshotV1
    outcome: HipFgmresTerminalOutcomeV1
    telemetry: HipFgmresTerminalOutcomeObservationTelemetryV1
    claims: HipFgmresTerminalOutcomeObservationClaimsV1
    outcome_hash: str
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        # A serialized receipt deliberately cannot carry process-local object
        # identity.  Structural validation is safe here; authoritative replay
        # requires the source result and context through the public validator.
        _validate_receipt_structure(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalOutcomeObservationResultV1:
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1
    _source_export_result: HipFgmresCompletionExportResultV1 = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_export_context: HipFgmresCompletionExportExecutionContextV1 = (
        dataclass_field(
            repr=False,
            compare=False,
        )
    )

    @property
    def outcome(self) -> HipFgmresTerminalOutcomeV1:
        return self.receipt.outcome

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_terminal_outcome_observation_result_v1(self)
        return self.receipt.to_dict()


def observe_hip_fgmres_terminal_outcome_v1(
    export_result: HipFgmresCompletionExportResultV1,
    *,
    expected_export_context: HipFgmresCompletionExportExecutionContextV1,
) -> HipFgmresTerminalOutcomeObservationResultV1:
    """Interpret one immutable completion export and publish atomically."""

    if type(export_result) is not HipFgmresCompletionExportResultV1:
        _fail("hip_fgmres_terminal_outcome_export_result_type_invalid", "/export")
    if type(expected_export_context) is not HipFgmresCompletionExportExecutionContextV1:
        _fail(
            "hip_fgmres_terminal_outcome_expected_context_invalid",
            "/expected_export_context",
        )

    publication_authority = (
        expected_export_context._terminal_outcome_observation_authority(export_result)
    )
    source_receipt = export_result.receipt
    source_receipt_identity = id(source_receipt)
    source_receipt_hash = source_receipt.receipt_hash
    source_manifest = source_receipt.to_dict()
    validate_hip_fgmres_completion_export_result_v1(
        export_result,
        expected_context=expected_export_context,
    )

    policy = _public_policy_snapshot(publication_authority.policy)
    outcome = _decode_and_validate_outcome(export_result, policy=policy)
    source = export_result.receipt
    abi_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
    control_hash = canonical_hash(hip_fgmres_control_state_abi_payload_v2())
    bindings = HipFgmresTerminalOutcomeObservationBindingsV1(
        completion_export_context_id=source.context_id,
        completion_export_receipt_hash=source.receipt_hash,
        completion_export_payload_hash=source.payload_hash,
        completion_export_source_binding_hash=source.bindings.source_binding_hash,
        global_context_id=source.bindings.global_context_id,
        global_receipt_hash=source.bindings.global_receipt_hash,
        completion_receipt_hash=source.bindings.completion_receipt_hash,
        solve_record_abi_hash=abi_hash,
        control_state_abi_hash=control_hash,
        recurrence_plan_hash=source.bindings.recurrence_plan_hash,
        recurrence_kernel_abi_hash=source.bindings.recurrence_kernel_abi_hash,
        combined_recurrence_abi_hash=source.bindings.combined_recurrence_abi_hash,
        continuation_schedule_hash=source.bindings.continuation_schedule_hash,
        kernel_identity_hash=source.bindings.kernel_identity_hash,
        kernel_source_sha256=source.bindings.kernel_source_sha256,
        architecture=source.bindings.architecture,
        device_ordinal=source.bindings.device_ordinal,
        policy_hash=canonical_hash(policy.to_dict()),
        solution_payload_sha256=source.buffers[0].payload_sha256,
        true_residual_payload_sha256=source.buffers[1].payload_sha256,
        solve_record_payload_sha256=source.buffers[2].payload_sha256,
    )
    dimensions = HipFgmresTerminalOutcomeObservationDimensionsV1(
        free_dof_count=source.dimensions.free_dof_count,
        maximum_restart_count=source.dimensions.maximum_restart_count,
        solve_record_byte_count=source.dimensions.solve_record_byte_count,
        inspected_host_payload_byte_count=source.dimensions.total_export_byte_count,
    )
    observation_id = canonical_hash(
        {
            "profile": HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_CAPABILITY_PROFILE_V1,
            "completion_export_receipt_hash": source.receipt_hash,
            "completion_export_payload_hash": source.payload_hash,
            "solve_record_abi_hash": abi_hash,
        }
    )
    status = _observation_status(outcome.outcome_class)
    telemetry = HipFgmresTerminalOutcomeObservationTelemetryV1(
        solve_record_restart_row_count=dimensions.maximum_restart_count,
        inspected_host_payload_byte_count=dimensions.inspected_host_payload_byte_count,
    )
    claims = HipFgmresTerminalOutcomeObservationClaimsV1(
        process_local_export_provenance_verified=True,
        authoritative_terminal_status_proven=True,
    )
    draft = HipFgmresTerminalOutcomeObservationReceiptV1(
        status=status,
        observation_id=observation_id,
        evidence_scope=(HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1),
        actual_backend=source.actual_backend,
        promotion_eligible=False,
        bindings=bindings,
        dimensions=dimensions,
        policy=policy,
        outcome=outcome,
        telemetry=telemetry,
        claims=claims,
        outcome_hash=canonical_hash(outcome.to_dict()),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )

    # Revalidate the immutable source immediately before publication.  This
    # keeps the raw export receipt identity and bytes outside observer control.
    validate_hip_fgmres_completion_export_result_v1(
        export_result,
        expected_context=expected_export_context,
    )
    if (
        id(export_result.receipt) != source_receipt_identity
        or export_result.receipt.receipt_hash != source_receipt_hash
        or export_result.receipt.to_dict() != source_manifest
    ):
        _fail(
            "hip_fgmres_terminal_outcome_export_receipt_changed",
            "/export/receipt",
        )
    if (
        expected_export_context._terminal_outcome_observation_authority(export_result)
        is not publication_authority
    ):
        _fail(
            "hip_fgmres_terminal_outcome_publication_authority_changed",
            "/export/publication",
        )

    result = HipFgmresTerminalOutcomeObservationResultV1(
        receipt=receipt,
        _source_export_result=export_result,
        _source_export_context=expected_export_context,
    )
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        result,
        expected_export_result=export_result,
        expected_export_context=expected_export_context,
    )
    return result


def validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1,
    *,
    expected_export_result: HipFgmresCompletionExportResultV1 | None = None,
    expected_export_context: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> HipFgmresTerminalOutcomeObservationReceiptV1:
    """Validate a receipt against exact process-local export provenance."""

    _validate_receipt_structure(receipt)
    if (
        type(expected_export_result) is not HipFgmresCompletionExportResultV1
        or type(expected_export_context)
        is not HipFgmresCompletionExportExecutionContextV1
    ):
        _fail(
            "hip_fgmres_terminal_outcome_provenance_required",
            "/provenance",
        )
    transient_result = HipFgmresTerminalOutcomeObservationResultV1(
        receipt=receipt,
        _source_export_result=expected_export_result,
        _source_export_context=expected_export_context,
    )
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        transient_result,
        expected_export_result=expected_export_result,
        expected_export_context=expected_export_context,
    )
    return receipt


def _validate_receipt_structure(
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1,
) -> HipFgmresTerminalOutcomeObservationReceiptV1:
    """Validate serialized structure without asserting object provenance."""

    if type(receipt) is not HipFgmresTerminalOutcomeObservationReceiptV1:
        _fail("hip_fgmres_terminal_outcome_receipt_type_invalid", "/")
    _validate_receipt_types(receipt)
    payload = _receipt_payload(receipt, include_hash=False)
    if _HASH_RE.fullmatch(
        receipt.receipt_hash
    ) is None or receipt.receipt_hash != canonical_hash(payload):
        _fail(
            "hip_fgmres_terminal_outcome_receipt_hash_invalid",
            "/receipt_hash",
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_terminal_outcome_receipt_schema_invalid",
            path,
            errors[0].message,
        )
    _validate_receipt_semantics(receipt)
    return receipt


def validate_hip_fgmres_terminal_outcome_observation_result_v1(
    result: HipFgmresTerminalOutcomeObservationResultV1,
    *,
    expected_export_result: HipFgmresCompletionExportResultV1 | None = None,
    expected_export_context: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> HipFgmresTerminalOutcomeObservationResultV1:
    """Replay an observation against its immutable raw export source."""

    if type(result) is not HipFgmresTerminalOutcomeObservationResultV1:
        _fail("hip_fgmres_terminal_outcome_result_type_invalid", "/")
    receipt = _validate_receipt_structure(result.receipt)
    source = result._source_export_result
    context = result._source_export_context
    if type(source) is not HipFgmresCompletionExportResultV1:
        _fail("hip_fgmres_terminal_outcome_source_type_invalid", "/source")
    if type(context) is not HipFgmresCompletionExportExecutionContextV1:
        _fail(
            "hip_fgmres_terminal_outcome_source_context_type_invalid",
            "/source/context",
        )
    if expected_export_result is not None and source is not expected_export_result:
        _fail("hip_fgmres_terminal_outcome_source_mismatch", "/source")
    if expected_export_context is not None and context is not expected_export_context:
        _fail(
            "hip_fgmres_terminal_outcome_source_context_mismatch",
            "/source/context",
        )
    validate_hip_fgmres_completion_export_result_v1(
        source,
        expected_context=context,
    )
    authority = context._terminal_outcome_observation_authority(source)
    if _public_policy_snapshot(authority.policy) != receipt.policy:
        _fail(
            "hip_fgmres_terminal_outcome_policy_provenance_invalid",
            "/policy",
        )
    source_receipt = source.receipt
    expected_bindings = receipt.bindings
    if (
        receipt.actual_backend != source_receipt.actual_backend
        or receipt.dimensions.free_dof_count != source_receipt.dimensions.free_dof_count
        or receipt.dimensions.maximum_restart_count
        != source_receipt.dimensions.maximum_restart_count
        or receipt.dimensions.solve_record_byte_count
        != source_receipt.dimensions.solve_record_byte_count
        or receipt.dimensions.inspected_host_payload_byte_count
        != source_receipt.dimensions.total_export_byte_count
        or expected_bindings.completion_export_context_id != source_receipt.context_id
        or expected_bindings.completion_export_receipt_hash
        != source_receipt.receipt_hash
        or expected_bindings.completion_export_payload_hash
        != source_receipt.payload_hash
        or expected_bindings.completion_export_source_binding_hash
        != source_receipt.bindings.source_binding_hash
        or expected_bindings.global_context_id
        != source_receipt.bindings.global_context_id
        or expected_bindings.global_receipt_hash
        != source_receipt.bindings.global_receipt_hash
        or expected_bindings.completion_receipt_hash
        != source_receipt.bindings.completion_receipt_hash
        or expected_bindings.solution_payload_sha256
        != source_receipt.buffers[0].payload_sha256
        or expected_bindings.true_residual_payload_sha256
        != source_receipt.buffers[1].payload_sha256
        or expected_bindings.solve_record_payload_sha256
        != source_receipt.buffers[2].payload_sha256
        or expected_bindings.recurrence_plan_hash
        != source_receipt.bindings.recurrence_plan_hash
        or expected_bindings.solve_record_abi_hash
        != source_receipt.bindings.solve_record_abi_hash
        or expected_bindings.recurrence_kernel_abi_hash
        != source_receipt.bindings.recurrence_kernel_abi_hash
        or expected_bindings.combined_recurrence_abi_hash
        != source_receipt.bindings.combined_recurrence_abi_hash
        or expected_bindings.continuation_schedule_hash
        != source_receipt.bindings.continuation_schedule_hash
        or expected_bindings.kernel_identity_hash
        != source_receipt.bindings.kernel_identity_hash
        or expected_bindings.kernel_source_sha256
        != source_receipt.bindings.kernel_source_sha256
        or expected_bindings.architecture != source_receipt.bindings.architecture
        or expected_bindings.device_ordinal != source_receipt.bindings.device_ordinal
        or expected_bindings.policy_hash != canonical_hash(receipt.policy.to_dict())
    ):
        _fail("hip_fgmres_terminal_outcome_source_binding_invalid", "/bindings")
    replayed = _decode_and_validate_outcome(source, policy=receipt.policy)
    if replayed != receipt.outcome:
        _fail("hip_fgmres_terminal_outcome_replay_mismatch", "/outcome")
    return result


def _decode_and_validate_outcome(
    export_result: HipFgmresCompletionExportResultV1,
    *,
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
) -> HipFgmresTerminalOutcomeV1:
    source = export_result.receipt
    abi_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
    if source.bindings.solve_record_abi_hash != abi_hash:
        _fail(
            "hip_fgmres_terminal_outcome_solve_record_abi_mismatch",
            "/bindings/solve_record_abi_hash",
        )
    if (
        source.dimensions.maximum_restart_count != policy.maximum_restart_count
        or source.dimensions.free_dof_count <= 0
        or source.dimensions.solve_record_byte_count
        != _HEADER_BYTES + _RESTART_BYTES * policy.maximum_restart_count
    ):
        _fail("hip_fgmres_terminal_outcome_record_extent_invalid", "/record")
    return decode_hip_fgmres_detached_completion_payload_v1(
        solution_x=export_result.solution_x,
        true_residual=export_result.true_residual,
        solve_record=export_result.solve_record,
        free_dof_count=source.dimensions.free_dof_count,
        maximum_restart_count=source.dimensions.maximum_restart_count,
        policy=policy,
    )


def decode_hip_fgmres_detached_completion_payload_v1(
    *,
    solution_x: bytes,
    true_residual: bytes,
    solve_record: bytes,
    free_dof_count: int,
    maximum_restart_count: int,
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
) -> HipFgmresTerminalOutcomeV1:
    """Decode current-ABI completion bytes without restoring live authority."""

    _validate_policy_snapshot(policy)
    if (
        type(solution_x) is not bytes
        or type(true_residual) is not bytes
        or type(solve_record) is not bytes
        or type(free_dof_count) is not int
        or free_dof_count <= 0
        or type(maximum_restart_count) is not int
        or maximum_restart_count <= 0
        or maximum_restart_count != policy.maximum_restart_count
        or len(solution_x) != 8 * free_dof_count
        or len(true_residual) != 8 * free_dof_count
    ):
        _fail("hip_fgmres_terminal_outcome_detached_payload_invalid", "/payload")
    abi = hip_fgmres_solve_record_abi_payload_v2()
    kernel_abi = hip_fgmres_recurrence_kernel_abi_payload_v2()
    if (
        abi["byte_order"] != "little_endian"
        or abi["header_bytes"] != _HEADER_BYTES
        or abi["restart_bytes"] != _RESTART_BYTES
        or abi["recurrence_abi_version"] != HIP_FGMRES_RECURRENCE_ABI_VERSION_V2
    ):
        _fail("hip_fgmres_terminal_outcome_abi_invalid", "/abi")

    maximum_restarts = maximum_restart_count
    expected_length = _HEADER_BYTES + _RESTART_BYTES * maximum_restarts
    payload = solve_record
    if len(payload) != expected_length:
        _fail("hip_fgmres_terminal_outcome_record_extent_invalid", "/record")

    header_fields = _parse_fields(payload, abi["header_fields"], base=0)
    if header_fields["recurrence_abi_version"] != (
        HIP_FGMRES_RECURRENCE_ABI_VERSION_V2
    ):
        _fail(
            "hip_fgmres_terminal_outcome_recurrence_abi_invalid",
            "/outcome/recurrence_abi_version",
        )
    if header_fields["active"] != 0:
        _fail(
            "hip_fgmres_terminal_outcome_not_terminal",
            "/outcome/active",
        )

    status_codes = _inverse_unique(abi["terminal_status_codes"], "/abi/status")
    termination_codes = _inverse_unique(abi["termination_codes"], "/abi/termination")
    hint_codes = _inverse_unique(abi["restart_hint_codes"], "/abi/restart_hint")
    status_code = header_fields["terminal_status"]
    termination_code_value = header_fields["termination_code"]
    if status_code not in status_codes or status_codes[status_code] == "not_terminal":
        _fail(
            "hip_fgmres_terminal_outcome_status_invalid",
            "/outcome/terminal_status",
        )
    if (
        termination_code_value not in termination_codes
        or termination_codes[termination_code_value] == "none"
    ):
        _fail(
            "hip_fgmres_terminal_outcome_termination_code_invalid",
            "/outcome/termination_code",
        )
    terminal_status = status_codes[status_code]
    termination_code = termination_codes[termination_code_value]
    if termination_code not in _STATUS_TO_TERMINATION_CODES[terminal_status]:
        _fail(
            "hip_fgmres_terminal_outcome_status_code_mismatch",
            "/outcome/termination_code",
        )

    device_error_map = kernel_abi["device_error_bits"]
    known_error_mask = sum(1 << int(bit) for bit in device_error_map.values())
    device_error_bits = header_fields["device_error_bits"]
    if (
        type(device_error_bits) is not int
        or device_error_bits < 0
        or device_error_bits & ~known_error_mask
    ):
        _fail(
            "hip_fgmres_terminal_outcome_device_error_bits_invalid",
            "/outcome/device_error_bits",
        )
    if (terminal_status == "numerical_failure") != (device_error_bits != 0):
        _fail(
            "hip_fgmres_terminal_outcome_device_error_status_mismatch",
            "/outcome/device_error_bits",
        )
    _validate_device_error_termination_compatibility(
        terminal_status=terminal_status,
        termination_code=termination_code,
        device_error_bits=device_error_bits,
        device_error_map=device_error_map,
    )
    device_error_names = tuple(
        name
        for name, bit in sorted(device_error_map.items(), key=lambda item: item[1])
        if device_error_bits & (1 << int(bit))
    )

    counters = HipFgmresTerminalOutcomeCountersV1(
        scheduled_iterations=header_fields["scheduled_iterations"],
        effective_iterations=header_fields["effective_iterations"],
        scheduled_restarts=header_fields["scheduled_restarts"],
        effective_restarts=header_fields["effective_restarts"],
        effective_arnoldi_dimension=header_fields["effective_arnoldi_dimension"],
        happy_breakdown_count=header_fields["happy_breakdown_count"],
        stagnation_checkpoint_count=header_fields["stagnation_checkpoint_count"],
        false_convergence_count=header_fields["false_convergence_count"],
        operator_apply_count=header_fields["operator_apply_count"],
        preconditioner_apply_count=header_fields["preconditioner_apply_count"],
        restart_dimension=header_fields["restart_dimension"],
    )
    metrics = HipFgmresTerminalOutcomeMetricsV1(
        rhs_l2=header_fields["rhs_l2"],
        rhs_linf=header_fields["rhs_linf"],
        solver_tolerance_l2=header_fields["solver_tolerance_l2"],
        authoritative_tolerance_scaled_linf=header_fields[
            "authoritative_tolerance_scaled_linf"
        ],
        initial_residual_l2=header_fields["initial_residual_l2"],
        final_residual_l2=header_fields["final_residual_l2"],
        final_residual_linf=header_fields["final_residual_linf"],
        final_scaled_residual=header_fields["final_scaled_residual"],
        previous_checkpoint_residual_l2=header_fields[
            "previous_checkpoint_residual_l2"
        ],
        solution_update_l2=header_fields["solution_update_l2"],
        solution_scale_l2=header_fields["solution_scale_l2"],
        estimated_residual_l2=header_fields["estimated_residual_l2"],
        arnoldi_work_l2=header_fields["arnoldi_work_l2"],
        arnoldi_breakdown_threshold=header_fields["arnoldi_breakdown_threshold"],
        triangular_scale=header_fields["triangular_scale"],
    )
    if not _positive_zero(header_fields["reserved_f64_0"]):
        _fail(
            "hip_fgmres_terminal_outcome_reserved_header_invalid",
            "/outcome/metrics/reserved_f64_0",
        )

    restart_rows = _parse_restart_rows(
        payload,
        abi,
        hint_codes,
        maximum_restarts,
    )
    _validate_outcome_semantics(
        terminal_status=terminal_status,
        termination_code=termination_code,
        counters=counters,
        metrics=metrics,
        restart_rows=restart_rows,
        maximum_restarts=maximum_restarts,
        restart_flag_bits=abi["restart_flag_bits"],
        policy=policy,
        raw_failure_metrics_available=True,
    )

    solution = np.frombuffer(solution_x, dtype="<f8")
    residual = np.frombuffer(true_residual, dtype="<f8")
    if solution.size != free_dof_count or residual.size != free_dof_count:
        _fail(
            "hip_fgmres_terminal_outcome_vector_extent_invalid",
            "/payload",
        )
    solution_finite = bool(np.isfinite(solution).all())
    residual_finite = bool(np.isfinite(residual).all())
    numerical_failure = terminal_status == "numerical_failure"
    observed_solution_l2: float | None = None
    observed_residual_l2: float | None = None
    observed_residual_linf: float | None = None
    observed_scaled: float | None = None
    residual_match: bool | None = None
    if not numerical_failure:
        if not solution_finite or not residual_finite:
            _fail(
                "hip_fgmres_terminal_outcome_payload_metrics_invalid",
                "/outcome/payload_metrics",
            )
        try:
            observed_residual_l2 = fgmres_gpu_tree_l2_v2(residual).value
            observed_residual_linf = fgmres_gpu_tree_linf_v2(residual).value
        except FgmresGpuTreeReferenceV2Error as exc:
            raise HipFgmresTerminalOutcomeObservationV1Error(
                "hip_fgmres_terminal_outcome_payload_metrics_invalid",
                "/outcome/payload_metrics",
                _detail(exc),
            ) from exc
        observed_scaled = observed_residual_linf / max(1.0, metrics.rhs_linf)
        residual_match = (
            observed_residual_l2 == metrics.final_residual_l2
            and observed_residual_linf == metrics.final_residual_linf
            and observed_scaled == metrics.final_scaled_residual
        )
        if not residual_match:
            _fail(
                "hip_fgmres_terminal_outcome_payload_metrics_invalid",
                "/outcome/payload_metrics",
            )

    outcome_class: TerminalOutcomeClassV1
    if terminal_status == "converged":
        outcome_class = "converged"
    elif numerical_failure:
        outcome_class = "numerical_failure"
    else:
        outcome_class = "not_converged"
    return HipFgmresTerminalOutcomeV1(
        outcome_class=outcome_class,
        active=0,
        terminal_status=terminal_status,
        terminal_status_code=status_code,
        termination_code=termination_code,
        termination_code_value=termination_code_value,
        device_error_bits=device_error_bits,
        device_error_names=device_error_names,
        counters=counters,
        record_metrics_authoritative=not numerical_failure,
        metrics=None if numerical_failure else metrics,
        restart_rows=restart_rows,
        solution_x_all_finite=solution_finite,
        true_residual_all_finite=residual_finite,
        observed_solution_x_l2=observed_solution_l2,
        observed_true_residual_l2=observed_residual_l2,
        observed_true_residual_linf=observed_residual_linf,
        observed_true_residual_scaled_linf=observed_scaled,
        true_residual_record_metrics_match=residual_match,
    )


def _parse_restart_rows(
    payload: bytes,
    abi: dict[str, Any],
    hint_codes: dict[int, str],
    maximum_restarts: int,
) -> tuple[HipFgmresTerminalOutcomeRestartRowV1, ...]:
    rows = []
    flag_bits = abi["restart_flag_bits"]
    for index in range(maximum_restarts):
        slot = index + 1
        base = _HEADER_BYTES + index * _RESTART_BYTES
        raw = payload[base : base + _RESTART_BYTES]
        fields = _parse_fields(payload, abi["restart_fields"], base=base)
        populated = any(raw)
        if not populated:
            if any(value != 0 for value in fields.values()):
                _fail(
                    "hip_fgmres_terminal_outcome_empty_restart_invalid",
                    f"/outcome/restart_rows/{index}",
                )
            hint = "none"
        else:
            if fields["restart_index"] != slot:
                _fail(
                    "hip_fgmres_terminal_outcome_restart_index_invalid",
                    f"/outcome/restart_rows/{index}/restart_index",
                )
            hint_value = fields["termination_hint"]
            if hint_value not in hint_codes or hint_codes[hint_value] == "none":
                _fail(
                    "hip_fgmres_terminal_outcome_restart_hint_invalid",
                    f"/outcome/restart_rows/{index}/termination_hint",
                )
            hint = hint_codes[hint_value]
        if fields["reserved_i32_0"] != 0:
            _fail(
                "hip_fgmres_terminal_outcome_restart_reserved_invalid",
                f"/outcome/restart_rows/{index}/reserved_i32_0",
            )
        flags = fields["flags"]
        if type(flags) is not int or not 0 <= flags <= 255:
            _fail(
                "hip_fgmres_terminal_outcome_restart_flags_invalid",
                f"/outcome/restart_rows/{index}/flags",
            )
        names = tuple(
            name
            for name, bit in sorted(flag_bits.items(), key=lambda item: item[1])
            if flags & (1 << int(bit))
        )
        rows.append(
            HipFgmresTerminalOutcomeRestartRowV1(
                slot_index=slot,
                populated=populated,
                restart_index=fields["restart_index"],
                start_iteration=fields["start_iteration"],
                end_iteration=fields["end_iteration"],
                arnoldi_step_count=fields["arnoldi_step_count"],
                reorthogonalization_count=fields["reorthogonalization_count"],
                termination_hint=hint,
                termination_hint_code=fields["termination_hint"],
                flags=flags,
                flag_names=names,
                estimated_residual_l2=fields["estimated_residual_l2"],
                true_residual_l2=fields["true_residual_l2"],
                true_residual_linf=fields["true_residual_linf"],
                scaled_true_residual=fields["scaled_true_residual"],
                solution_update_l2=fields["solution_update_l2"],
            )
        )
    return tuple(rows)


def _validate_outcome_semantics(
    *,
    terminal_status: str,
    termination_code: str,
    counters: HipFgmresTerminalOutcomeCountersV1,
    metrics: HipFgmresTerminalOutcomeMetricsV1,
    restart_rows: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...],
    maximum_restarts: int,
    restart_flag_bits: dict[str, int],
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
    raw_failure_metrics_available: bool,
) -> None:
    for name in counters.__dataclass_fields__:
        value = getattr(counters, name)
        if type(value) is not int or value < 0:
            _fail(
                "hip_fgmres_terminal_outcome_counter_invalid",
                f"/outcome/counters/{name}",
            )
    if not (
        counters.scheduled_iterations == policy.max_iterations
        and 1 <= counters.scheduled_iterations <= HIP_FGMRES_MAX_ITERATIONS
        and counters.restart_dimension == policy.restart_dimension
        and 1 <= counters.restart_dimension <= HIP_FGMRES_MAX_RESTART_DIMENSION
        and counters.scheduled_restarts == maximum_restarts
        and counters.scheduled_restarts == policy.maximum_restart_count
        and counters.scheduled_restarts
        == (counters.scheduled_iterations + counters.restart_dimension - 1)
        // counters.restart_dimension
        and 0 <= counters.effective_iterations <= counters.scheduled_iterations
        and 0 <= counters.effective_restarts <= counters.scheduled_restarts
        and 0 <= counters.effective_arnoldi_dimension <= counters.restart_dimension
        and counters.happy_breakdown_count <= 1
        and counters.stagnation_checkpoint_count <= policy.stagnation_checkpoint_limit
        and counters.false_convergence_count <= counters.effective_iterations
        and counters.preconditioner_apply_count <= counters.scheduled_iterations
        and counters.operator_apply_count
        <= (
            1
            + counters.scheduled_iterations
            + counters.scheduled_restarts
            + counters.false_convergence_count
        )
    ):
        _fail(
            "hip_fgmres_terminal_outcome_counter_relationship_invalid",
            "/outcome/counters",
        )

    if terminal_status != "numerical_failure":
        for name in metrics.__dataclass_fields__:
            value = getattr(metrics, name)
            if (
                type(value) is not float
                or not math.isfinite(value)
                or value < 0.0
                or (value == 0.0 and not _positive_zero(value))
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_metric_invalid",
                    f"/outcome/metrics/{name}",
                )
        if metrics.final_scaled_residual != (
            metrics.final_residual_linf / max(1.0, metrics.rhs_linf)
        ):
            _fail(
                "hip_fgmres_terminal_outcome_scaled_metric_invalid",
                "/outcome/metrics/final_scaled_residual",
            )
        expected_solver_tolerance = max(
            policy.absolute_tolerance,
            policy.relative_tolerance * metrics.rhs_l2,
        )
        if (
            not math.isfinite(expected_solver_tolerance)
            or metrics.solver_tolerance_l2 != expected_solver_tolerance
            or metrics.authoritative_tolerance_scaled_linf
            != policy.authoritative_tolerance
        ):
            _fail(
                "hip_fgmres_terminal_outcome_policy_metric_invalid",
                "/outcome/metrics/solver_tolerance_l2",
            )

    populated = tuple(row for row in restart_rows if row.populated)
    if populated != restart_rows[: len(populated)]:
        _fail(
            "hip_fgmres_terminal_outcome_restart_rows_not_contiguous",
            "/outcome/restart_rows",
        )
    for index, row in enumerate(restart_rows):
        if not row.populated:
            if (
                row.slot_index != index + 1
                or row.restart_index != 0
                or row.start_iteration != 0
                or row.end_iteration != 0
                or row.arnoldi_step_count != 0
                or row.reorthogonalization_count != 0
                or row.termination_hint != "none"
                or row.termination_hint_code != 0
                or row.flags != 0
                or row.flag_names
                or any(
                    not _positive_zero(getattr(row, name))
                    for name in (
                        "estimated_residual_l2",
                        "true_residual_l2",
                        "true_residual_linf",
                        "scaled_true_residual",
                        "solution_update_l2",
                    )
                )
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_empty_restart_invalid",
                    f"/outcome/restart_rows/{index}",
                )
            continue
        expected_start = index * counters.restart_dimension
        maximum_end = min(
            expected_start + counters.restart_dimension,
            counters.scheduled_iterations,
        )
        if (
            row.slot_index != index + 1
            or row.restart_index != index + 1
            or row.start_iteration != expected_start
            or not expected_start < row.end_iteration <= maximum_end
            or row.arnoldi_step_count != row.end_iteration - row.start_iteration
            or not 0 <= row.reorthogonalization_count <= row.arnoldi_step_count
            or row.termination_hint == "none"
        ):
            _fail(
                "hip_fgmres_terminal_outcome_restart_counter_invalid",
                f"/outcome/restart_rows/{index}",
            )
        if index < len(populated) - 1 and row.end_iteration != maximum_end:
            _fail(
                "hip_fgmres_terminal_outcome_prior_restart_extent_invalid",
                f"/outcome/restart_rows/{index}/end_iteration",
            )
        for metric_name in (
            "estimated_residual_l2",
            "true_residual_l2",
            "true_residual_linf",
            "scaled_true_residual",
            "solution_update_l2",
        ):
            value = getattr(row, metric_name)
            if (
                type(value) is not float
                or not math.isfinite(value)
                or value < 0.0
                or (value == 0.0 and not _positive_zero(value))
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_restart_metric_invalid",
                    f"/outcome/restart_rows/{index}/{metric_name}",
                )
        if terminal_status != "numerical_failure" and (
            row.scaled_true_residual
            != row.true_residual_linf / max(1.0, metrics.rhs_linf)
        ):
            _fail(
                "hip_fgmres_terminal_outcome_restart_scaled_metric_invalid",
                f"/outcome/restart_rows/{index}/scaled_true_residual",
            )
        if index < len(populated) - 1 and row.termination_hint != ("restart_completed"):
            _fail(
                "hip_fgmres_terminal_outcome_prior_restart_hint_invalid",
                f"/outcome/restart_rows/{index}/termination_hint",
            )

    if terminal_status == "numerical_failure":
        replay_bit = 1 << int(restart_flag_bits["true_residual_replayed"])
        forbidden_terminal_bits = sum(
            1 << int(restart_flag_bits[name])
            for name in (
                "happy_breakdown",
                "invariant_breakdown",
                "divergence",
            )
        )
        solver_bit = 1 << int(restart_flag_bits["solver_l2_passed"])
        authoritative_bit = 1 << int(restart_flag_bits["authoritative_linf_passed"])
        plateau_bit = 1 << int(restart_flag_bits["stagnation_plateau"])
        tiny_bit = 1 << int(restart_flag_bits["tiny_update"])
        observed_stagnation_count = 0
        for index, row in enumerate(populated):
            expected_end = min(
                row.start_iteration + counters.restart_dimension,
                counters.scheduled_iterations,
            )
            if (
                row.end_iteration != expected_end
                or row.termination_hint != "restart_completed"
                or not row.flags & replay_bit
                or row.flags & forbidden_terminal_bits
                or row.flags & solver_bit
                and row.flags & authoritative_bit
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_failure_restart_invalid",
                    f"/outcome/restart_rows/{index}",
                )
            observed_stagnation_count = (
                observed_stagnation_count + 1
                if row.flags & plateau_bit and row.flags & tiny_bit
                else 0
            )
        if not (
            len(populated)
            <= counters.effective_restarts
            <= min(maximum_restarts, len(populated) + 1)
        ):
            _fail(
                "hip_fgmres_terminal_outcome_failure_restart_count_invalid",
                "/outcome/counters/effective_restarts",
            )
        if counters.effective_restarts == len(populated):
            expected_iteration = populated[-1].end_iteration if populated else 0
            expected_dimension = populated[-1].arnoldi_step_count if populated else 0
            failure_progress_valid = (
                counters.effective_iterations == expected_iteration
                and counters.effective_arnoldi_dimension == expected_dimension
            )
        else:
            active_cycle_start = len(populated) * counters.restart_dimension
            active_cycle_end = min(
                active_cycle_start + counters.restart_dimension,
                counters.scheduled_iterations,
            )
            failure_progress_valid = (
                active_cycle_start <= counters.effective_iterations <= active_cycle_end
                and counters.effective_arnoldi_dimension
                == counters.effective_iterations - active_cycle_start
            )
        if not failure_progress_valid:
            _fail(
                "hip_fgmres_terminal_outcome_failure_progress_invalid",
                "/outcome/counters",
            )
        if populated and populated[-1].end_iteration > counters.effective_iterations:
            _fail(
                "hip_fgmres_terminal_outcome_failure_iteration_count_invalid",
                "/outcome/counters/effective_iterations",
            )
        replayed_restart_count = sum(bool(row.flags & replay_bit) for row in populated)
        operator_base = (
            1
            + counters.effective_iterations
            + replayed_restart_count
            + counters.false_convergence_count
        )
        active_cycle_started = counters.effective_restarts == len(populated) + 1
        pre_restart_failure = (
            not populated
            and counters.effective_restarts == 0
            and counters.effective_iterations == 0
        )
        preconditioner_count_valid = (
            counters.effective_iterations
            <= counters.preconditioner_apply_count
            <= min(
                counters.effective_iterations
                if counters.effective_iterations == active_cycle_end
                else counters.effective_iterations + 1,
                counters.scheduled_iterations,
            )
            if active_cycle_started
            else counters.preconditioner_apply_count == counters.effective_iterations
        )
        if pre_restart_failure:
            operator_count_valid = counters.operator_apply_count in {0, 1}
        elif active_cycle_started:
            operator_count_valid = (
                operator_base <= counters.operator_apply_count <= operator_base + 1
            )
        else:
            operator_count_valid = counters.operator_apply_count == operator_base
        in_flight_candidate_replay = (
            active_cycle_started
            and counters.operator_apply_count == operator_base + 1
            and counters.preconditioner_apply_count == counters.effective_iterations
        )
        if (
            counters.happy_breakdown_count != 0
            or counters.stagnation_checkpoint_count != observed_stagnation_count
            or observed_stagnation_count >= policy.stagnation_checkpoint_limit
            or counters.false_convergence_count
            + replayed_restart_count
            + int(in_flight_candidate_replay)
            > counters.effective_iterations
            or not preconditioner_count_valid
            or not operator_count_valid
        ):
            _fail(
                "hip_fgmres_terminal_outcome_failure_counter_invalid",
                "/outcome/counters",
            )
        if raw_failure_metrics_available and populated:
            _validate_failure_history_metrics(
                metrics=metrics,
                populated=populated,
                restart_flag_bits=restart_flag_bits,
                policy=policy,
            )
        return

    if counters.effective_restarts != len(populated):
        _fail(
            "hip_fgmres_terminal_outcome_effective_restart_count_invalid",
            "/outcome/counters/effective_restarts",
        )
    initial_terminal = termination_code == "converged_initial_true_residual"
    if initial_terminal:
        if (
            populated
            or counters.effective_iterations != 0
            or counters.effective_restarts != 0
            or counters.effective_arnoldi_dimension != 0
            or counters.preconditioner_apply_count != 0
            or counters.operator_apply_count != 1
        ):
            _fail(
                "hip_fgmres_terminal_outcome_initial_counter_invalid",
                "/outcome/counters",
            )
        if (
            metrics.initial_residual_l2 != metrics.final_residual_l2
            or metrics.estimated_residual_l2 != metrics.final_residual_l2
            or metrics.previous_checkpoint_residual_l2 != metrics.final_residual_l2
            or any(
                not _positive_zero(getattr(metrics, name))
                for name in (
                    "solution_update_l2",
                    "solution_scale_l2",
                    "arnoldi_work_l2",
                    "arnoldi_breakdown_threshold",
                    "triangular_scale",
                )
            )
        ):
            _fail(
                "hip_fgmres_terminal_outcome_initial_metric_invalid",
                "/outcome/metrics",
            )
    else:
        expected_breakdown_threshold = _BREAKDOWN_TAU * metrics.arnoldi_work_l2
        if (
            not populated
            or populated[-1].end_iteration != counters.effective_iterations
            or populated[-1].arnoldi_step_count != counters.effective_arnoldi_dimension
            or populated[-1].estimated_residual_l2 != metrics.estimated_residual_l2
            or populated[-1].true_residual_l2 != metrics.final_residual_l2
            or populated[-1].true_residual_linf != metrics.final_residual_linf
            or populated[-1].scaled_true_residual != metrics.final_scaled_residual
            or not math.isfinite(expected_breakdown_threshold)
            or metrics.arnoldi_breakdown_threshold != expected_breakdown_threshold
            or (
                termination_code != "arnoldi_triangular_factor_breakdown"
                and (metrics.arnoldi_work_l2 <= 0.0 or metrics.triangular_scale <= 0.0)
            )
            or (
                termination_code != "arnoldi_triangular_factor_breakdown"
                and populated[-1].solution_update_l2 != metrics.solution_update_l2
            )
        ):
            _fail(
                "hip_fgmres_terminal_outcome_terminal_restart_invalid",
                "/outcome/restart_rows",
            )
        if termination_code == "arnoldi_triangular_factor_breakdown":
            expected_committed_update = (
                populated[-2].solution_update_l2 if len(populated) > 1 else 0.0
            )
            if (
                populated[-1].solution_update_l2 != 0.0
                or metrics.solution_update_l2 != expected_committed_update
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_triangular_update_invalid",
                    f"/outcome/restart_rows/{len(populated) - 1}/solution_update_l2",
                )
            if len(populated) > 1:
                prior_committed = populated[-2]
                committed_residual_preserved = (
                    populated[-1].true_residual_l2 == prior_committed.true_residual_l2
                    and populated[-1].true_residual_linf
                    == prior_committed.true_residual_linf
                    and populated[-1].scaled_true_residual
                    == prior_committed.scaled_true_residual
                )
            else:
                committed_residual_preserved = (
                    populated[-1].true_residual_l2 == metrics.initial_residual_l2
                )
            if not committed_residual_preserved:
                _fail(
                    "hip_fgmres_terminal_outcome_triangular_residual_invalid",
                    f"/outcome/restart_rows/{len(populated) - 1}",
                )
        expected_hint = _TERMINATION_TO_LAST_HINT.get(termination_code)
        if expected_hint is None or populated[-1].termination_hint != expected_hint:
            _fail(
                "hip_fgmres_terminal_outcome_terminal_hint_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/termination_hint",
            )
        if termination_code in {
            "converged_restart_true_residual",
            "max_iterations_exhausted",
            "true_residual_stagnated",
            "true_residual_diverged",
        } and populated[-1].end_iteration != min(
            populated[-1].start_iteration + counters.restart_dimension,
            counters.scheduled_iterations,
        ):
            _fail(
                "hip_fgmres_terminal_outcome_terminal_restart_extent_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/end_iteration",
            )

    if counters.preconditioner_apply_count != counters.effective_iterations:
        _fail(
            "hip_fgmres_terminal_outcome_preconditioner_count_invalid",
            "/outcome/counters/preconditioner_apply_count",
        )
    replay_bit = 1 << int(restart_flag_bits["true_residual_replayed"])
    replayed_restart_count = sum(bool(row.flags & replay_bit) for row in populated)
    reserved_terminal_iteration_count = int(
        termination_code == "arnoldi_triangular_factor_breakdown"
    )
    if (
        counters.false_convergence_count
        + replayed_restart_count
        + reserved_terminal_iteration_count
        > counters.effective_iterations
    ):
        _fail(
            "hip_fgmres_terminal_outcome_replay_count_invalid",
            "/outcome/counters/false_convergence_count",
        )
    expected_operator_count = (
        1
        + counters.effective_iterations
        + replayed_restart_count
        + counters.false_convergence_count
    )
    if counters.operator_apply_count != expected_operator_count:
        _fail(
            "hip_fgmres_terminal_outcome_operator_count_invalid",
            "/outcome/counters/operator_apply_count",
        )

    dual_gate_passed = (
        metrics.final_residual_l2 <= metrics.solver_tolerance_l2
        and metrics.final_scaled_residual <= metrics.authoritative_tolerance_scaled_linf
    )
    if (terminal_status == "converged") != dual_gate_passed:
        _fail(
            "hip_fgmres_terminal_outcome_dual_gate_status_invalid",
            "/outcome/terminal_status",
        )
    if terminal_status == "max_iterations" and (
        counters.effective_iterations != counters.scheduled_iterations
    ):
        _fail(
            "hip_fgmres_terminal_outcome_max_iteration_count_invalid",
            "/outcome/counters/effective_iterations",
        )
    if terminal_status == "stagnated" and (
        counters.stagnation_checkpoint_count != policy.stagnation_checkpoint_limit
    ):
        _fail(
            "hip_fgmres_terminal_outcome_stagnation_count_invalid",
            "/outcome/counters/stagnation_checkpoint_count",
        )
    expected_happy_count = int(termination_code == "converged_happy_breakdown")
    if counters.happy_breakdown_count != expected_happy_count:
        _fail(
            "hip_fgmres_terminal_outcome_happy_count_invalid",
            "/outcome/counters/happy_breakdown_count",
        )

    _validate_nonfailure_restart_flags(
        terminal_status=terminal_status,
        termination_code=termination_code,
        counters=counters,
        metrics=metrics,
        populated=populated,
        restart_flag_bits=restart_flag_bits,
        policy=policy,
    )

    if populated:
        last = populated[-1]
        replay_bit = 1 << int(restart_flag_bits["true_residual_replayed"])
        happy_bit = 1 << int(restart_flag_bits["happy_breakdown"])
        invariant_bit = 1 << int(restart_flag_bits["invariant_breakdown"])
        solver_gate_bit = 1 << int(restart_flag_bits["solver_l2_passed"])
        authoritative_gate_bit = 1 << int(
            restart_flag_bits["authoritative_linf_passed"]
        )
        stagnation_plateau_bit = 1 << int(restart_flag_bits["stagnation_plateau"])
        tiny_update_bit = 1 << int(restart_flag_bits["tiny_update"])
        divergence_bit = 1 << int(restart_flag_bits["divergence"])
        if termination_code == "arnoldi_triangular_factor_breakdown":
            if last.flags != 0:
                _fail(
                    "hip_fgmres_terminal_outcome_triangular_flags_invalid",
                    f"/outcome/restart_rows/{len(populated) - 1}/flags",
                )
        elif not last.flags & replay_bit:
            _fail(
                "hip_fgmres_terminal_outcome_replay_flag_missing",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        if termination_code == "converged_happy_breakdown" and (
            not last.flags & happy_bit
            or last.flags & invariant_bit
            or not last.flags & solver_gate_bit
            or not last.flags & authoritative_gate_bit
        ):
            _fail(
                "hip_fgmres_terminal_outcome_happy_flags_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        if termination_code == "arnoldi_invariant_subspace_breakdown" and (
            not last.flags & invariant_bit or last.flags & happy_bit
        ):
            _fail(
                "hip_fgmres_terminal_outcome_invariant_flags_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        if termination_code in {
            "converged_true_residual",
            "converged_restart_true_residual",
        } and (
            not last.flags & solver_gate_bit or not last.flags & authoritative_gate_bit
        ):
            _fail(
                "hip_fgmres_terminal_outcome_convergence_flags_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        if terminal_status == "stagnated" and (
            not last.flags & stagnation_plateau_bit or not last.flags & tiny_update_bit
        ):
            _fail(
                "hip_fgmres_terminal_outcome_stagnation_flags_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        divergence_threshold = policy.divergence_factor * max(
            metrics.initial_residual_l2,
            float.fromhex("0x1.0000000000000p-1022"),
        )
        diverged_by_policy = (
            math.isfinite(divergence_threshold)
            and metrics.final_residual_l2 > divergence_threshold
        )
        if terminal_status == "diverged" and (
            not last.flags & divergence_bit or not diverged_by_policy
        ):
            _fail(
                "hip_fgmres_terminal_outcome_divergence_policy_invalid",
                f"/outcome/restart_rows/{len(populated) - 1}/flags",
            )
        if terminal_status in {"stagnated", "max_iterations"} and (diverged_by_policy):
            _fail(
                "hip_fgmres_terminal_outcome_priority_invalid",
                "/outcome/terminal_status",
            )


def _validate_failure_history_metrics(
    *,
    metrics: HipFgmresTerminalOutcomeMetricsV1,
    populated: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...],
    restart_flag_bits: dict[str, int],
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
) -> None:
    stable_metric_names = (
        "rhs_l2",
        "rhs_linf",
        "solver_tolerance_l2",
        "authoritative_tolerance_scaled_linf",
        "initial_residual_l2",
        "final_residual_l2",
        "final_residual_linf",
        "final_scaled_residual",
        "previous_checkpoint_residual_l2",
        "solution_update_l2",
        "solution_scale_l2",
    )
    for name in stable_metric_names:
        value = getattr(metrics, name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and not _positive_zero(value))
        ):
            _fail(
                "hip_fgmres_terminal_outcome_failure_history_metric_invalid",
                f"/outcome/metrics/{name}",
            )

    expected_solver_tolerance = max(
        policy.absolute_tolerance,
        policy.relative_tolerance * metrics.rhs_l2,
    )
    last = populated[-1]
    if (
        not math.isfinite(expected_solver_tolerance)
        or metrics.solver_tolerance_l2 != expected_solver_tolerance
        or metrics.authoritative_tolerance_scaled_linf != policy.authoritative_tolerance
        or metrics.final_residual_l2 != last.true_residual_l2
        or metrics.final_residual_linf != last.true_residual_linf
        or metrics.final_scaled_residual != last.scaled_true_residual
        or metrics.previous_checkpoint_residual_l2 != last.true_residual_l2
        or metrics.solution_update_l2 != last.solution_update_l2
    ):
        _fail(
            "hip_fgmres_terminal_outcome_failure_history_metric_invalid",
            "/outcome/metrics",
        )

    solver_bit = 1 << int(restart_flag_bits["solver_l2_passed"])
    authoritative_bit = 1 << int(restart_flag_bits["authoritative_linf_passed"])
    plateau_bit = 1 << int(restart_flag_bits["stagnation_plateau"])
    tiny_bit = 1 << int(restart_flag_bits["tiny_update"])
    previous_residual = metrics.initial_residual_l2
    for index, row in enumerate(populated):
        expected_scaled = row.true_residual_linf / max(1.0, metrics.rhs_linf)
        plateau_threshold = (
            1.0 - policy.stagnation_relative_tolerance
        ) * previous_residual
        if (
            not math.isfinite(expected_scaled)
            or not math.isfinite(plateau_threshold)
            or row.scaled_true_residual != expected_scaled
            or bool(row.flags & solver_bit)
            != (row.true_residual_l2 <= metrics.solver_tolerance_l2)
            or bool(row.flags & authoritative_bit)
            != (row.scaled_true_residual <= metrics.authoritative_tolerance_scaled_linf)
            or bool(row.flags & plateau_bit)
            != (row.true_residual_l2 >= plateau_threshold)
        ):
            _fail(
                "hip_fgmres_terminal_outcome_failure_history_flag_invalid",
                f"/outcome/restart_rows/{index}",
            )
        previous_residual = row.true_residual_l2

    tiny_threshold = _SQRT_EPSILON * metrics.solution_scale_l2
    if not math.isfinite(tiny_threshold) or bool(last.flags & tiny_bit) != (
        last.solution_update_l2 <= tiny_threshold
    ):
        _fail(
            "hip_fgmres_terminal_outcome_failure_history_flag_invalid",
            f"/outcome/restart_rows/{len(populated) - 1}/flags",
        )


def _validate_nonfailure_restart_flags(
    *,
    terminal_status: str,
    termination_code: str,
    counters: HipFgmresTerminalOutcomeCountersV1,
    metrics: HipFgmresTerminalOutcomeMetricsV1,
    populated: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...],
    restart_flag_bits: dict[str, int],
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
) -> None:
    replay_bit = 1 << int(restart_flag_bits["true_residual_replayed"])
    solver_bit = 1 << int(restart_flag_bits["solver_l2_passed"])
    authoritative_bit = 1 << int(restart_flag_bits["authoritative_linf_passed"])
    happy_bit = 1 << int(restart_flag_bits["happy_breakdown"])
    invariant_bit = 1 << int(restart_flag_bits["invariant_breakdown"])
    plateau_bit = 1 << int(restart_flag_bits["stagnation_plateau"])
    tiny_bit = 1 << int(restart_flag_bits["tiny_update"])
    divergence_bit = 1 << int(restart_flag_bits["divergence"])
    previous_checkpoint = metrics.initial_residual_l2
    expected_stagnation_count = 0

    for index, row in enumerate(populated):
        final = index == len(populated) - 1
        if final and termination_code == "arnoldi_triangular_factor_breakdown":
            expected_flags = 0
            scale_path = False
        else:
            expected_flags = replay_bit
            solver_passed = row.true_residual_l2 <= metrics.solver_tolerance_l2
            authoritative_passed = (
                row.scaled_true_residual <= metrics.authoritative_tolerance_scaled_linf
            )
            if solver_passed:
                expected_flags |= solver_bit
            if authoritative_passed:
                expected_flags |= authoritative_bit

            scale_path = not final
            divergence_threshold = policy.divergence_factor * max(
                metrics.initial_residual_l2,
                float.fromhex("0x1.0000000000000p-1022"),
            )
            if not final and (
                (solver_passed and authoritative_passed)
                or row.true_residual_l2 > divergence_threshold
            ):
                _fail(
                    "hip_fgmres_terminal_outcome_prior_restart_priority_invalid",
                    f"/outcome/restart_rows/{index}",
                )
            if final:
                if termination_code == "converged_happy_breakdown":
                    expected_flags |= happy_bit
                elif termination_code == "arnoldi_invariant_subspace_breakdown":
                    expected_flags |= invariant_bit
                elif termination_code == "true_residual_diverged":
                    expected_flags |= divergence_bit
                elif termination_code in {
                    "max_iterations_exhausted",
                    "true_residual_stagnated",
                }:
                    scale_path = True

            if scale_path:
                plateau = row.true_residual_l2 >= (
                    (1.0 - policy.stagnation_relative_tolerance) * previous_checkpoint
                )
                tiny = bool(row.flags & tiny_bit)
                if plateau:
                    expected_flags |= plateau_bit
                if final:
                    expected_tiny = row.solution_update_l2 <= (
                        float.fromhex("0x1p-26") * metrics.solution_scale_l2
                    )
                    if tiny != expected_tiny:
                        _fail(
                            "hip_fgmres_terminal_outcome_tiny_update_flag_invalid",
                            f"/outcome/restart_rows/{index}/flags",
                        )
                if tiny:
                    expected_flags |= tiny_bit
                expected_stagnation_count = (
                    expected_stagnation_count + 1 if plateau and tiny else 0
                )
                previous_checkpoint = row.true_residual_l2

        if row.flags != expected_flags:
            _fail(
                "hip_fgmres_terminal_outcome_restart_flags_invalid",
                f"/outcome/restart_rows/{index}/flags",
            )

    final_uses_retained_scale = termination_code in {
        "max_iterations_exhausted",
        "true_residual_stagnated",
    }
    if (
        len(populated) == 1
        and not final_uses_retained_scale
        and not _positive_zero(metrics.solution_scale_l2)
    ):
        _fail(
            "hip_fgmres_terminal_outcome_uncommitted_solution_scale_invalid",
            "/outcome/metrics/solution_scale_l2",
        )
    if len(populated) > 1 and not final_uses_retained_scale:
        latest_scale_row = populated[-2]
        expected_latest_tiny = latest_scale_row.solution_update_l2 <= (
            _SQRT_EPSILON * metrics.solution_scale_l2
        )
        if bool(latest_scale_row.flags & tiny_bit) != expected_latest_tiny:
            _fail(
                "hip_fgmres_terminal_outcome_tiny_update_flag_invalid",
                f"/outcome/restart_rows/{len(populated) - 2}/flags",
            )

    if (
        counters.stagnation_checkpoint_count != expected_stagnation_count
        or metrics.previous_checkpoint_residual_l2 != previous_checkpoint
        or (
            terminal_status != "stagnated"
            and expected_stagnation_count >= policy.stagnation_checkpoint_limit
        )
    ):
        _fail(
            "hip_fgmres_terminal_outcome_stagnation_history_invalid",
            "/outcome/counters/stagnation_checkpoint_count",
        )


def _validate_receipt_types(
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1,
) -> None:
    if (
        type(receipt.status) is not str
        or type(receipt.observation_id) is not str
        or type(receipt.evidence_scope) is not str
        or type(receipt.actual_backend) is not str
        or type(receipt.promotion_eligible) is not bool
        or type(receipt.bindings) is not HipFgmresTerminalOutcomeObservationBindingsV1
        or type(receipt.dimensions)
        is not HipFgmresTerminalOutcomeObservationDimensionsV1
        or type(receipt.policy) is not HipFgmresTerminalOutcomePolicySnapshotV1
        or type(receipt.outcome) is not HipFgmresTerminalOutcomeV1
        or type(receipt.telemetry) is not HipFgmresTerminalOutcomeObservationTelemetryV1
        or type(receipt.claims) is not HipFgmresTerminalOutcomeObservationClaimsV1
        or type(receipt.outcome_hash) is not str
        or type(receipt.receipt_hash) is not str
    ):
        _fail("hip_fgmres_terminal_outcome_receipt_type_invalid", "/")
    for name, value in receipt.bindings.to_dict().items():
        if name in {
            "process_local_export_context_verified",
            "process_local_result_identity_serialized",
        }:
            if type(value) is not bool:
                _fail(
                    "hip_fgmres_terminal_outcome_binding_type_invalid",
                    f"/bindings/{name}",
                )
        elif name == "device_ordinal":
            if type(value) is not int:
                _fail(
                    "hip_fgmres_terminal_outcome_binding_type_invalid",
                    f"/bindings/{name}",
                )
        elif type(value) is not str:
            _fail(
                "hip_fgmres_terminal_outcome_binding_type_invalid",
                f"/bindings/{name}",
            )
    for name in receipt.dimensions.__dataclass_fields__:
        value = getattr(receipt.dimensions, name)
        if type(value) is not int:
            _fail(
                "hip_fgmres_terminal_outcome_dimension_type_invalid",
                f"/dimensions/{name}",
            )
    for name in receipt.policy.__dataclass_fields__:
        value = getattr(receipt.policy, name)
        if name in {
            "restart_dimension",
            "max_iterations",
            "maximum_restart_count",
            "stagnation_checkpoint_limit",
        }:
            if type(value) is not int:
                _fail(
                    "hip_fgmres_terminal_outcome_policy_type_invalid",
                    f"/policy/{name}",
                )
        elif type(value) is not float:
            _fail(
                "hip_fgmres_terminal_outcome_policy_type_invalid",
                f"/policy/{name}",
            )
    _validate_outcome_types(receipt.outcome)
    for name in receipt.telemetry.__dataclass_fields__:
        value = getattr(receipt.telemetry, name)
        if type(value) is not int:
            _fail(
                "hip_fgmres_terminal_outcome_telemetry_type_invalid",
                f"/telemetry/{name}",
            )
    for name in receipt.claims.__dataclass_fields__:
        value = getattr(receipt.claims, name)
        if type(value) is not bool:
            _fail(
                "hip_fgmres_terminal_outcome_claim_type_invalid",
                f"/claims/{name}",
            )


def _validate_outcome_types(outcome: HipFgmresTerminalOutcomeV1) -> None:
    scalar_strings = (
        outcome.outcome_class,
        outcome.terminal_status,
        outcome.termination_code,
    )
    scalar_ints = (
        outcome.active,
        outcome.terminal_status_code,
        outcome.termination_code_value,
        outcome.device_error_bits,
    )
    if (
        any(type(value) is not str for value in scalar_strings)
        or any(type(value) is not int for value in scalar_ints)
        or type(outcome.device_error_names) is not tuple
        or any(type(value) is not str for value in outcome.device_error_names)
        or type(outcome.counters) is not HipFgmresTerminalOutcomeCountersV1
        or type(outcome.record_metrics_authoritative) is not bool
        or (
            outcome.metrics is not None
            and type(outcome.metrics) is not HipFgmresTerminalOutcomeMetricsV1
        )
        or type(outcome.restart_rows) is not tuple
        or any(
            type(row) is not HipFgmresTerminalOutcomeRestartRowV1
            for row in outcome.restart_rows
        )
        or type(outcome.solution_x_all_finite) is not bool
        or type(outcome.true_residual_all_finite) is not bool
        or (
            outcome.true_residual_record_metrics_match is not None
            and type(outcome.true_residual_record_metrics_match) is not bool
        )
    ):
        _fail("hip_fgmres_terminal_outcome_outcome_type_invalid", "/outcome")
    for name in outcome.counters.__dataclass_fields__:
        value = getattr(outcome.counters, name)
        if type(value) is not int:
            _fail(
                "hip_fgmres_terminal_outcome_counter_type_invalid",
                f"/outcome/counters/{name}",
            )
    if outcome.metrics is not None:
        for name in outcome.metrics.__dataclass_fields__:
            value = getattr(outcome.metrics, name)
            if type(value) is not float:
                _fail(
                    "hip_fgmres_terminal_outcome_metric_type_invalid",
                    f"/outcome/metrics/{name}",
                )
    for index, row in enumerate(outcome.restart_rows):
        for name in row.__dataclass_fields__:
            value = getattr(row, name)
            path = f"/outcome/restart_rows/{index}/{name}"
            if name == "populated":
                if type(value) is not bool:
                    _fail("hip_fgmres_terminal_outcome_row_type_invalid", path)
            elif name in {"termination_hint"}:
                if type(value) is not str:
                    _fail("hip_fgmres_terminal_outcome_row_type_invalid", path)
            elif name == "flag_names":
                if type(row.flag_names) is not tuple or any(
                    type(item) is not str for item in row.flag_names
                ):
                    _fail("hip_fgmres_terminal_outcome_row_type_invalid", path)
            elif name.endswith("_l2") or name in {
                "true_residual_linf",
                "scaled_true_residual",
            }:
                if type(value) is not float:
                    _fail("hip_fgmres_terminal_outcome_row_type_invalid", path)
            elif type(value) is not int:
                _fail("hip_fgmres_terminal_outcome_row_type_invalid", path)
    for name in (
        "observed_solution_x_l2",
        "observed_true_residual_l2",
        "observed_true_residual_linf",
        "observed_true_residual_scaled_linf",
    ):
        value = getattr(outcome, name)
        if value is not None and type(value) is not float:
            _fail(
                "hip_fgmres_terminal_outcome_observed_metric_type_invalid",
                f"/outcome/{name}",
            )


def _validate_receipt_semantics(
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1,
) -> None:
    bindings = receipt.bindings
    dimensions = receipt.dimensions
    outcome = receipt.outcome
    policy = receipt.policy
    telemetry = receipt.telemetry
    claims = receipt.claims
    for name, value in bindings.to_dict().items():
        if name in {
            "process_local_export_context_verified",
            "process_local_result_identity_serialized",
            "device_ordinal",
            "architecture",
        }:
            continue
        if _HASH_RE.fullmatch(value) is None:
            _fail(
                "hip_fgmres_terminal_outcome_binding_hash_invalid",
                f"/bindings/{name}",
            )
    current_abi_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
    current_control_hash = canonical_hash(hip_fgmres_control_state_abi_payload_v2())
    current_kernel_hash = canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
    if (
        bindings.solve_record_abi_hash != current_abi_hash
        or bindings.control_state_abi_hash != current_control_hash
        or bindings.recurrence_kernel_abi_hash != current_kernel_hash
    ):
        _fail(
            "hip_fgmres_terminal_outcome_current_abi_mismatch",
            "/bindings",
        )
    _validate_policy_snapshot(policy)
    if bindings.policy_hash != canonical_hash(policy.to_dict()):
        _fail(
            "hip_fgmres_terminal_outcome_policy_hash_invalid",
            "/bindings/policy_hash",
        )
    if (
        not bindings.architecture
        or bindings.device_ordinal < 0
        or policy.maximum_restart_count != dimensions.maximum_restart_count
        or policy.restart_dimension != outcome.counters.restart_dimension
        or policy.max_iterations != outcome.counters.scheduled_iterations
        or policy.maximum_restart_count != outcome.counters.scheduled_restarts
        or dimensions.free_dof_count <= 0
        or dimensions.maximum_restart_count <= 0
        or dimensions.solve_record_header_bytes != _HEADER_BYTES
        or dimensions.solve_record_restart_bytes != _RESTART_BYTES
        or dimensions.solve_record_byte_count
        != _HEADER_BYTES + _RESTART_BYTES * dimensions.maximum_restart_count
        or dimensions.inspected_host_payload_byte_count
        != 16 * dimensions.free_dof_count + dimensions.solve_record_byte_count
    ):
        _fail(
            "hip_fgmres_terminal_outcome_dimension_invalid",
            "/dimensions",
        )
    expected_id = canonical_hash(
        {
            "profile": HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_CAPABILITY_PROFILE_V1,
            "completion_export_receipt_hash": (bindings.completion_export_receipt_hash),
            "completion_export_payload_hash": (bindings.completion_export_payload_hash),
            "solve_record_abi_hash": bindings.solve_record_abi_hash,
        }
    )
    if receipt.observation_id != expected_id:
        _fail(
            "hip_fgmres_terminal_outcome_observation_id_invalid",
            "/observation_id",
        )
    if (
        receipt.evidence_scope
        != HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1
        or receipt.actual_backend not in {"hip", "test_double"}
        or receipt.promotion_eligible
        or receipt.status != _observation_status(outcome.outcome_class)
        or receipt.outcome_hash != canonical_hash(outcome.to_dict())
        or _HASH_RE.fullmatch(receipt.outcome_hash) is None
    ):
        _fail("hip_fgmres_terminal_outcome_receipt_semantics_invalid", "/")
    if (
        telemetry.completion_export_source_result_count != 1
        or telemetry.solve_record_payload_count != 1
        or telemetry.solve_record_header_field_count != 32
        or telemetry.solve_record_restart_row_count != dimensions.maximum_restart_count
        or telemetry.inspected_host_payload_byte_count
        != dimensions.inspected_host_payload_byte_count
        or telemetry.published_terminal_outcome_count != 1
        or any(
            getattr(telemetry, name) != 0
            for name in (
                "additional_d2h_operation_count",
                "h2d_operation_count",
                "device_allocation_count",
                "allocation_borrow_count",
                "kernel_launch_count",
                "explicit_stream_sync_count",
                "fallback_count",
            )
        )
    ):
        _fail(
            "hip_fgmres_terminal_outcome_telemetry_invalid",
            "/telemetry",
        )
    process_verified = bindings.process_local_export_context_verified
    if (
        process_verified is not True
        or bindings.process_local_result_identity_serialized is not False
        or claims.process_local_export_provenance_verified != process_verified
        or claims.authoritative_terminal_status_proven != process_verified
        or not claims.completion_export_result_bound
        or not claims.raw_export_receipt_preserved
        or not claims.solve_record_semantics_interpreted
        or not claims.actual_terminal_outcome_host_observed
        or not claims.terminal_record_invariants_verified
        or not claims.no_additional_device_operation
        or claims.authoritative_completion_or_solution_receipt
        or claims.numerical_parity_verified
        or claims.solution_ready
        or claims.result_ir_ready
        or claims.iteration_host_copy_zero_proven
        or claims.performance_or_speedup_proven
        or claims.commercial_ready
        or claims.promotion_eligible
    ):
        _fail("hip_fgmres_terminal_outcome_claims_invalid", "/claims")
    if len(outcome.restart_rows) != dimensions.maximum_restart_count:
        _fail(
            "hip_fgmres_terminal_outcome_restart_extent_invalid",
            "/outcome/restart_rows",
        )
    numerical_failure = outcome.outcome_class == "numerical_failure"
    if (
        outcome.record_metrics_authoritative is numerical_failure
        or (outcome.metrics is None) != numerical_failure
        or (outcome.true_residual_record_metrics_match is None) != numerical_failure
        or (
            numerical_failure
            and any(
                value is not None
                for value in (
                    outcome.observed_solution_x_l2,
                    outcome.observed_true_residual_l2,
                    outcome.observed_true_residual_linf,
                    outcome.observed_true_residual_scaled_linf,
                )
            )
        )
        or (
            not numerical_failure
            and (
                not outcome.solution_x_all_finite
                or not outcome.true_residual_all_finite
            )
        )
    ):
        _fail(
            "hip_fgmres_terminal_outcome_metric_availability_invalid",
            "/outcome/metrics",
        )

    kernel_abi = hip_fgmres_recurrence_kernel_abi_payload_v2()
    error_bits = kernel_abi["device_error_bits"]
    expected_error_names = tuple(
        name
        for name, bit in sorted(error_bits.items(), key=lambda item: item[1])
        if outcome.device_error_bits & (1 << int(bit))
    )
    if outcome.device_error_names != expected_error_names:
        _fail(
            "hip_fgmres_terminal_outcome_device_error_names_invalid",
            "/outcome/device_error_names",
        )
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    status_by_code = _inverse_unique(
        record_abi["terminal_status_codes"],
        "/outcome/terminal_status_code",
    )
    termination_by_code = _inverse_unique(
        record_abi["termination_codes"],
        "/outcome/termination_code_value",
    )
    expected_outcome_class = (
        "converged"
        if outcome.terminal_status == "converged"
        else (
            "numerical_failure"
            if outcome.terminal_status == "numerical_failure"
            else "not_converged"
        )
    )
    if (
        outcome.active != 0
        or status_by_code.get(outcome.terminal_status_code) != outcome.terminal_status
        or termination_by_code.get(outcome.termination_code_value)
        != outcome.termination_code
        or outcome.termination_code
        not in _STATUS_TO_TERMINATION_CODES.get(outcome.terminal_status, set())
        or outcome.outcome_class != expected_outcome_class
        or (numerical_failure != (outcome.device_error_bits != 0))
    ):
        _fail(
            "hip_fgmres_terminal_outcome_status_code_relationship_invalid",
            "/outcome",
        )
    known_error_mask = sum(1 << int(bit) for bit in error_bits.values())
    if outcome.device_error_bits < 0 or outcome.device_error_bits & ~known_error_mask:
        _fail(
            "hip_fgmres_terminal_outcome_device_error_bits_invalid",
            "/outcome/device_error_bits",
        )
    _validate_device_error_termination_compatibility(
        terminal_status=outcome.terminal_status,
        termination_code=outcome.termination_code,
        device_error_bits=outcome.device_error_bits,
        device_error_map=error_bits,
    )
    restart_flag_bits = record_abi["restart_flag_bits"]
    for index, row in enumerate(outcome.restart_rows):
        expected_flag_names = tuple(
            name
            for name, bit in sorted(restart_flag_bits.items(), key=lambda item: item[1])
            if row.flags & (1 << int(bit))
        )
        if row.slot_index != index + 1 or row.flag_names != expected_flag_names:
            _fail(
                "hip_fgmres_terminal_outcome_restart_flag_names_invalid",
                f"/outcome/restart_rows/{index}",
            )

    semantic_metrics = (
        _inert_failure_metrics() if numerical_failure else outcome.metrics
    )
    if semantic_metrics is None:
        _fail(
            "hip_fgmres_terminal_outcome_metric_availability_invalid",
            "/outcome/metrics",
        )
    _validate_outcome_semantics(
        terminal_status=outcome.terminal_status,
        termination_code=outcome.termination_code,
        counters=outcome.counters,
        metrics=semantic_metrics,
        restart_rows=outcome.restart_rows,
        maximum_restarts=dimensions.maximum_restart_count,
        restart_flag_bits=restart_flag_bits,
        policy=policy,
        raw_failure_metrics_available=False,
    )
    if not numerical_failure:
        observed = (
            outcome.observed_true_residual_l2,
            outcome.observed_true_residual_linf,
            outcome.observed_true_residual_scaled_linf,
        )
        if (
            outcome.observed_solution_x_l2 is not None
            or any(
                type(value) is not float
                or not math.isfinite(value)
                or value < 0.0
                or (value == 0.0 and not _positive_zero(value))
                for value in observed
            )
            or outcome.observed_true_residual_l2 != semantic_metrics.final_residual_l2
            or outcome.observed_true_residual_linf
            != semantic_metrics.final_residual_linf
            or outcome.observed_true_residual_scaled_linf
            != semantic_metrics.final_scaled_residual
            or outcome.true_residual_record_metrics_match is not True
        ):
            _fail(
                "hip_fgmres_terminal_outcome_observed_metrics_invalid",
                "/outcome",
            )


def _inert_failure_metrics() -> HipFgmresTerminalOutcomeMetricsV1:
    return HipFgmresTerminalOutcomeMetricsV1(
        rhs_l2=0.0,
        rhs_linf=0.0,
        solver_tolerance_l2=0.0,
        authoritative_tolerance_scaled_linf=0.0,
        initial_residual_l2=0.0,
        final_residual_l2=0.0,
        final_residual_linf=0.0,
        final_scaled_residual=0.0,
        previous_checkpoint_residual_l2=0.0,
        solution_update_l2=0.0,
        solution_scale_l2=0.0,
        estimated_residual_l2=0.0,
        arnoldi_work_l2=0.0,
        arnoldi_breakdown_threshold=0.0,
        triangular_scale=0.0,
    )


def _receipt_payload(
    receipt: HipFgmresTerminalOutcomeObservationReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": (HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_SCHEMA_VERSION_V1),
        "status": receipt.status,
        "observation_id": receipt.observation_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "policy": receipt.policy.to_dict(),
        "outcome": receipt.outcome.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "outcome_hash": receipt.outcome_hash,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _parse_fields(
    payload: bytes,
    fields: list[dict[str, Any]],
    *,
    base: int,
) -> dict[str, int | float]:
    parsed: dict[str, int | float] = {}
    for descriptor in fields:
        if (
            type(descriptor) is not dict
            or type(descriptor.get("name")) is not str
            or descriptor.get("dtype") not in {"i32", "f64"}
            or type(descriptor.get("offset_bytes")) is not int
        ):
            _fail("hip_fgmres_terminal_outcome_field_descriptor_invalid", "/abi")
        name = descriptor["name"]
        offset = base + descriptor["offset_bytes"]
        if name in parsed:
            _fail("hip_fgmres_terminal_outcome_field_duplicate", "/abi")
        try:
            if descriptor["dtype"] == "i32":
                parsed[name] = int(struct.unpack_from("<i", payload, offset)[0])
            else:
                parsed[name] = float(struct.unpack_from("<d", payload, offset)[0])
        except struct.error as exc:
            raise HipFgmresTerminalOutcomeObservationV1Error(
                "hip_fgmres_terminal_outcome_field_extent_invalid",
                f"/record/{name}",
                _detail(exc),
            ) from exc
    return parsed


def _inverse_unique(mapping: dict[str, int], path: str) -> dict[int, str]:
    if type(mapping) is not dict:
        _fail("hip_fgmres_terminal_outcome_code_map_invalid", path)
    inverse: dict[int, str] = {}
    for name, value in mapping.items():
        if type(name) is not str or type(value) is not int or value in inverse:
            _fail("hip_fgmres_terminal_outcome_code_map_invalid", path)
        inverse[value] = name
    return inverse


def _validate_device_error_termination_compatibility(
    *,
    terminal_status: str,
    termination_code: str,
    device_error_bits: int,
    device_error_map: dict[str, int],
) -> None:
    if terminal_status != "numerical_failure":
        if device_error_bits != 0:
            _fail(
                "hip_fgmres_terminal_outcome_device_error_termination_mismatch",
                "/outcome/device_error_bits",
            )
        return

    def error_mask(*names: str) -> int:
        try:
            return sum(1 << int(device_error_map[name]) for name in names)
        except (KeyError, TypeError, ValueError) as exc:
            raise HipFgmresTerminalOutcomeObservationV1Error(
                "hip_fgmres_terminal_outcome_device_error_map_invalid",
                "/abi/device_error_bits",
                _detail(exc),
            ) from exc

    invalid_control = error_mask("invalid_control_or_geometry")
    csr_structure = error_mask("csr_structure")
    nonfinite_input = error_mask("nonfinite_input")
    arithmetic_overflow = error_mask("arithmetic_overflow")
    record_abi = error_mask("record_abi")
    jacobi_inverse = error_mask("jacobi_inverse")
    invalid_reduction_pair = error_mask("invalid_reduction_pair")
    operator_data_errors = csr_structure | nonfinite_input | arithmetic_overflow
    orthogonalization_errors = nonfinite_input | arithmetic_overflow | jacobi_inverse

    def nonempty_subsets(mask: int) -> set[int]:
        return {candidate for candidate in range(1, mask + 1) if candidate & ~mask == 0}

    allowed_by_termination = {
        "invalid_input_or_control": {invalid_control, record_abi},
        "nonfinite_arithmetic": {
            nonfinite_input,
            arithmetic_overflow,
            nonfinite_input | arithmetic_overflow,
            invalid_reduction_pair,
            arithmetic_overflow | invalid_reduction_pair,
        },
        "operator_application_failed": {
            invalid_control,
            record_abi,
            *nonempty_subsets(operator_data_errors),
        },
        "orthogonalization_failed": nonempty_subsets(orthogonalization_errors),
        "givens_rotation_failed": {arithmetic_overflow},
        "triangular_solve_failed": {arithmetic_overflow},
        "true_residual_replay_failed": {
            nonfinite_input,
            arithmetic_overflow,
            nonfinite_input | arithmetic_overflow,
        },
        "restart_state_failed": {
            invalid_control,
            nonfinite_input,
            arithmetic_overflow,
            nonfinite_input | arithmetic_overflow,
        },
    }
    if device_error_bits not in allowed_by_termination.get(termination_code, set()):
        _fail(
            "hip_fgmres_terminal_outcome_device_error_termination_mismatch",
            "/outcome/device_error_bits",
        )


def _observation_status(
    outcome_class: TerminalOutcomeClassV1,
) -> TerminalObservationStatusV1:
    return {
        "converged": "terminal_converged",
        "not_converged": "terminal_not_converged",
        "numerical_failure": "terminal_numerical_failure",
    }[outcome_class]  # type: ignore[return-value]


def _public_policy_snapshot(
    source: _CompletionExportPolicySnapshotV1,
) -> HipFgmresTerminalOutcomePolicySnapshotV1:
    if type(source) is not _CompletionExportPolicySnapshotV1:
        _fail(
            "hip_fgmres_terminal_outcome_private_policy_type_invalid",
            "/policy",
        )
    policy = HipFgmresTerminalOutcomePolicySnapshotV1(
        restart_dimension=source.restart_dimension,
        max_iterations=source.max_iterations,
        maximum_restart_count=source.maximum_restart_count,
        stagnation_checkpoint_limit=source.stagnation_checkpoint_limit,
        absolute_tolerance=source.absolute_tolerance,
        relative_tolerance=source.relative_tolerance,
        authoritative_tolerance=source.authoritative_tolerance,
        stagnation_relative_tolerance=source.stagnation_relative_tolerance,
        divergence_factor=source.divergence_factor,
    )
    _validate_policy_snapshot(policy)
    return policy


def _validate_policy_snapshot(
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
) -> None:
    if type(policy) is not HipFgmresTerminalOutcomePolicySnapshotV1:
        _fail("hip_fgmres_terminal_outcome_policy_type_invalid", "/policy")
    if (
        type(policy.restart_dimension) is not int
        or not 1 <= policy.restart_dimension <= HIP_FGMRES_MAX_RESTART_DIMENSION
        or type(policy.max_iterations) is not int
        or not 1 <= policy.max_iterations <= HIP_FGMRES_MAX_ITERATIONS
        or type(policy.maximum_restart_count) is not int
        or policy.maximum_restart_count
        != (policy.max_iterations + policy.restart_dimension - 1)
        // policy.restart_dimension
        or type(policy.stagnation_checkpoint_limit) is not int
        or not 2 <= policy.stagnation_checkpoint_limit <= 16
        or any(
            type(value) is not float or not math.isfinite(value)
            for value in (
                policy.absolute_tolerance,
                policy.relative_tolerance,
                policy.authoritative_tolerance,
                policy.stagnation_relative_tolerance,
                policy.divergence_factor,
            )
        )
        or policy.absolute_tolerance < 0.0
        or policy.relative_tolerance < 0.0
        or (
            policy.absolute_tolerance == 0.0
            and not _positive_zero(policy.absolute_tolerance)
        )
        or (
            policy.relative_tolerance == 0.0
            and not _positive_zero(policy.relative_tolerance)
        )
        or (policy.absolute_tolerance == 0.0 and policy.relative_tolerance == 0.0)
        or policy.authoritative_tolerance < 0.0
        or (
            policy.authoritative_tolerance == 0.0
            and not _positive_zero(policy.authoritative_tolerance)
        )
        or not 0.0 < policy.stagnation_relative_tolerance < 1.0
        or policy.divergence_factor <= 1.0
    ):
        _fail("hip_fgmres_terminal_outcome_policy_invalid", "/policy")


def _positive_zero(value: float) -> bool:
    return type(value) is float and value == 0.0 and math.copysign(1.0, value) > 0.0


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HipFgmresTerminalOutcomeObservationV1Error(
            "hip_fgmres_terminal_outcome_schema_unavailable",
            "/schema",
            _detail(exc),
        ) from exc
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: object) -> str:
    text = str(value).strip()
    return text if text else "unspecified"


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresTerminalOutcomeObservationV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_SCHEMA_VERSION_V1",
    "HipFgmresTerminalOutcomeCountersV1",
    "HipFgmresTerminalOutcomeMetricsV1",
    "HipFgmresTerminalOutcomeObservationBindingsV1",
    "HipFgmresTerminalOutcomeObservationClaimsV1",
    "HipFgmresTerminalOutcomeObservationDimensionsV1",
    "HipFgmresTerminalOutcomePolicySnapshotV1",
    "HipFgmresTerminalOutcomeObservationReceiptV1",
    "HipFgmresTerminalOutcomeObservationResultV1",
    "HipFgmresTerminalOutcomeObservationTelemetryV1",
    "HipFgmresTerminalOutcomeObservationV1Error",
    "HipFgmresTerminalOutcomeRestartRowV1",
    "HipFgmresTerminalOutcomeV1",
    "decode_hip_fgmres_detached_completion_payload_v1",
    "observe_hip_fgmres_terminal_outcome_v1",
    "validate_hip_fgmres_terminal_outcome_observation_receipt_v1",
    "validate_hip_fgmres_terminal_outcome_observation_result_v1",
]
