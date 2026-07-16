"""Process-local high-load FGMRES model-case parity v2.

The legacy model-case v1 receipt is intentionally frozen.  This additive v2
contract binds the scale-aware componentwise/normwise terminal receipt to a
live native-HIP completion and supports exactly one populated restart row.
That row must be the terminal row, so its true-residual metrics are aliases of
the final vector-backed terminal metrics.  Estimated-residual and solution-
update scalars retain the legacy fixed diagnostic gate; no roundoff model is
claimed for them.

The current completion ABI exports only ``solution_x``, final
``true_residual``, and an opaque scalar ``solve_record``.  Consequently this
contract records, rather than hides, that general multi-restart history v2 is
unavailable until per-restart checkpoint vectors are exported.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    HipDeviceIdentityResultV1,
    validate_hip_device_identity_receipt_v1,
    validate_hip_device_identity_result_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceResultV1,
    validate_cpu_fgmres_reference_result_v1,
)

from .fgmres_completion_export_v1 import (
    _CompletionExportModelCaseParityAuthorityV1,
    HipFgmresCompletionExportExecutionContextV1,
    HipFgmresCompletionExportResultV1,
)
from .fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1,
    HipFgmresModelCaseParityVectorComparisonV1,
    _bytes_sha256,
    _detached_cpu_result,
    _detached_plan_lineage,
    _model_source_value_witness,
    _private_snapshot_token,
    _scalar_close,
    _validate_fixed_policy,
    _validate_vector_comparison,
)
from .fgmres_model_case_terminal_metric_parity_v2 import (
    HipFgmresTerminalMetricParityResultV2,
    replay_hip_fgmres_detached_terminal_metric_parity_v2,
    validate_hip_fgmres_terminal_metric_parity_result_v2,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeMetricsV1,
    HipFgmresTerminalOutcomeObservationResultV1,
    HipFgmresTerminalOutcomeRestartRowV1,
    HipFgmresTerminalOutcomeV1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)


HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-model-case-parity.v2"
)
HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2 = (
    "phase0_high_load_single_terminal_restart_cpu_hip_fgmres_parity_v2"
)
HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V2 = (
    "process_local_exact_one_terminal_restart_native_hip_normwise_parity_non_promoting"
)
HIP_FGMRES_MODEL_CASE_PARITY_REQUIRED_HISTORY_ABI_V2 = (
    "per_restart_checkpoint_solution_and_true_residual_vector_export_v2"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXECUTION_PLAN_ID_RE = re.compile(r"^SparsePlan:[0-9a-f]{24}$")
_FGMRES_PLAN_ID_RE = re.compile(r"^HipFgmresPlan:[0-9a-f]{24}$")
_RECURRENCE_PLAN_ID_RE = re.compile(r"^HipFgmresRecurrencePlan:[0-9a-f]{24}$")
_SCHEMA_RESOURCE = "hip_fgmres_model_case_parity_v2.schema.json"
_MISSING_HISTORY_EVIDENCE = (
    "intermediate_checkpoint_solution_vectors_not_exported",
    "intermediate_checkpoint_true_residual_vectors_not_exported",
    "estimated_residual_roundoff_model_not_available",
    "solution_update_roundoff_model_not_available",
)


class HipFgmresModelCaseParityV2Error(ValueError):
    """Stable fail-closed high-load model-case v2 error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityBindingsV2:
    model_ir_content_hash: str
    execution_plan_id: str
    execution_plan_hash: str
    operator_hash: str
    numeric_snapshot_hash: str
    symbolic_reuse_hash: str
    partition_hash: str
    load_pattern_id: str
    fgmres_plan_id: str
    fgmres_plan_hash: str
    recurrence_plan_id: str
    recurrence_plan_hash: str
    policy_hash: str
    terminal_observation_id: str
    terminal_observation_receipt_hash: str
    terminal_outcome_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    global_context_id: str
    global_receipt_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    compiled_architecture: str
    runtime_architecture_base: str
    device_ordinal: int
    device_identity_receipt_hash: str
    runtime_library_sha256: str
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    cpu_result_hash: str
    terminal_metric_parity_id: str
    terminal_metric_parity_receipt_hash: str
    cpu_candidate_componentwise_receipt_hash: str
    cpu_candidate_normwise_receipt_hash: str
    candidate_replay_componentwise_receipt_hash: str
    candidate_replay_normwise_receipt_hash: str
    terminal_metric_projection_hash: str
    retained_execution_plan_snapshot_identity_verified: Literal[True] = True
    process_local_runtime_identity_verified: Literal[True] = True
    process_local_identities_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityDimensionsV2:
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    populated_restart_row_count: Literal[1]
    prior_restart_row_count: Literal[0]
    exported_checkpoint_solution_vector_count: Literal[0]
    exported_checkpoint_true_residual_vector_count: Literal[0]
    solve_record_scalar_count_per_restart: Literal[5]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLegacyHistoryMetricComparisonV2:
    name: Literal["estimated_residual_l2", "solution_update_l2"]
    reference_record: float
    candidate_record: float
    absolute_difference: float
    legacy_fixed_tolerance: float
    maximum_tolerance_ratio: float
    legacy_fixed_gate_passed: Literal[True]
    roundoff_error_model_verified: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresSingleTerminalRestartHistoryV2:
    scope: Literal["exactly_one_populated_terminal_restart_row"]
    terminal_restart_index: int
    terminal_row_slot_index: Literal[1]
    cpu_terminal_true_residual_alias_verified: Literal[True]
    hip_terminal_true_residual_alias_verified: Literal[True]
    terminal_true_residual_metrics_delegated_to_normwise_v2: Literal[True]
    checkpoint_vector_roles_exported: Literal[False]
    general_history_status: Literal[
        "not_verified_missing_checkpoint_vectors_and_scalar_error_models"
    ]
    required_next_abi: Literal[
        "per_restart_checkpoint_solution_and_true_residual_vector_export_v2"
    ]
    missing_evidence: tuple[str, ...]
    estimated_residual: HipFgmresLegacyHistoryMetricComparisonV2
    solution_update: HipFgmresLegacyHistoryMetricComparisonV2
    general_restart_history_v2_verified: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "terminal_restart_index": self.terminal_restart_index,
            "terminal_row_slot_index": self.terminal_row_slot_index,
            "cpu_terminal_true_residual_alias_verified": (
                self.cpu_terminal_true_residual_alias_verified
            ),
            "hip_terminal_true_residual_alias_verified": (
                self.hip_terminal_true_residual_alias_verified
            ),
            "terminal_true_residual_metrics_delegated_to_normwise_v2": (
                self.terminal_true_residual_metrics_delegated_to_normwise_v2
            ),
            "checkpoint_vector_roles_exported": self.checkpoint_vector_roles_exported,
            "general_history_status": self.general_history_status,
            "required_next_abi": self.required_next_abi,
            "missing_evidence": list(self.missing_evidence),
            "estimated_residual": self.estimated_residual.to_dict(),
            "solution_update": self.solution_update.to_dict(),
            "general_restart_history_v2_verified": (
                self.general_restart_history_v2_verified
            ),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityDiscreteComparisonV2:
    terminal_status_match: Literal[True]
    termination_code_match: Literal[True]
    iteration_count_match: Literal[True]
    restart_count_match: Literal[True]
    operator_apply_count_match: Literal[True]
    preconditioner_apply_count_match: Literal[True]
    restart_history_shape_match: Literal[True]
    restart_history_discrete_fields_match: Literal[True]
    terminal_metrics_normwise_bound_verified: Literal[True]
    terminal_restart_true_residual_metrics_normwise_bound_verified: Literal[True]
    estimated_residual_legacy_fixed_gate_passed: Literal[True]
    solution_update_legacy_fixed_gate_passed: Literal[True]
    general_restart_history_metric_v2_verified: Literal[False]
    numerical_failure_absent: Literal[True]

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityCompatibilityV2:
    legacy_model_case_parity_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-case-parity.v1"
    ] = "structural-analysis-hip-fgmres-model-case-parity.v1"
    terminal_metric_parity_schema_version: Literal[
        "structural-analysis-hip-fgmres-terminal-metric-parity.v2"
    ] = "structural-analysis-hip-fgmres-terminal-metric-parity.v2"
    legacy_wire_receipt_mutated: Literal[False] = False
    legacy_solution_gate_relaxed: Literal[False] = False
    legacy_residual_gate_relaxed: Literal[False] = False
    legacy_terminal_or_history_gate_relaxed: Literal[False] = False
    legacy_v1_receipt_required: Literal[False] = False
    persisted_v1_migration_claimed: Literal[False] = False
    migration_action: Literal[
        "issue_additive_model_case_v2_without_mutating_or_requiring_v1"
    ] = "issue_additive_model_case_v2_without_mutating_or_requiring_v1"

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityTelemetryV2:
    cpu_reference_result_count: Literal[1] = 1
    hip_terminal_observation_result_count: Literal[1] = 1
    hip_device_identity_result_count: Literal[1] = 1
    terminal_metric_parity_result_count: Literal[1] = 1
    populated_restart_row_count: Literal[1] = 1
    fixed_solution_vector_comparison_count: Literal[1] = 1
    additional_d2h_operation_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    device_allocation_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    explicit_stream_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityClaimsV2:
    exact_retained_execution_plan_snapshot_bound: Literal[True] = True
    deterministic_cpu_reference_replayed: Literal[True] = True
    actual_hip_backend_verified: Literal[True] = True
    runtime_device_identity_verified: Literal[True] = True
    legacy_fixed_solution_vector_gate_verified: Literal[True] = True
    componentwise_residual_roundoff_bound_verified: Literal[True] = True
    independent_operator_residual_replay_verified: Literal[True] = True
    terminal_normwise_metric_v2_verified: Literal[True] = True
    single_terminal_restart_true_residual_metric_v2_verified: Literal[True] = True
    estimated_residual_roundoff_model_verified: Literal[False] = False
    solution_update_roundoff_model_verified: Literal[False] = False
    general_restart_history_metric_v2_verified: Literal[False] = False
    scoped_single_model_case_numerical_parity_verified: Literal[True] = True
    full_model_family_parity_verified: Literal[False] = False
    multi_architecture_parity_verified: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    signed_evidence: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityReceiptV2:
    schema_version: str
    capability_profile: str
    status: Literal["scoped_case_parity_verified"]
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    case_id: str
    bindings: HipFgmresModelCaseParityBindingsV2
    dimensions: HipFgmresModelCaseParityDimensionsV2
    discrete: HipFgmresModelCaseParityDiscreteComparisonV2
    solution: HipFgmresModelCaseParityVectorComparisonV1
    history: HipFgmresSingleTerminalRestartHistoryV2
    compatibility: HipFgmresModelCaseParityCompatibilityV2
    telemetry: HipFgmresModelCaseParityTelemetryV2
    claims: HipFgmresModelCaseParityClaimsV2
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_case_parity_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2:
    receipt: HipFgmresModelCaseParityReceiptV2
    source_execution_plan: ExecutionPlanV2
    cpu_result: CpuFgmresReferenceResultV1
    observation_result: HipFgmresTerminalOutcomeObservationResultV1
    device_identity_result: HipDeviceIdentityResultV1
    export_result: HipFgmresCompletionExportResultV1
    export_context: HipFgmresCompletionExportExecutionContextV1
    publication: _CompletionExportModelCaseParityAuthorityV1
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2
    snapshot: tuple[Any, ...]


class _WeakReferenceableModelCaseParityResultV2:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelCaseParityResultV2(_WeakReferenceableModelCaseParityResultV2):
    receipt: HipFgmresModelCaseParityReceiptV2
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2
    _cpu_result: CpuFgmresReferenceResultV1 = dataclass_field(repr=False, compare=False)
    _observation_result: HipFgmresTerminalOutcomeObservationResultV1 = dataclass_field(
        repr=False, compare=False
    )
    _device_identity_result: HipDeviceIdentityResultV1 = dataclass_field(
        repr=False, compare=False
    )
    _source_execution_plan: ExecutionPlanV2 = dataclass_field(repr=False, compare=False)
    _result_ir_downstream_authority_seal: (
        _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2 | None
    ) = dataclass_field(default=None, repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_case_parity_result_v2(self)
        return self.receipt.to_dict()

    def _result_ir_downstream_authority(
        self,
    ) -> _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2:
        seal = self._result_ir_downstream_authority_seal
        if type(seal) is not _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2:
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_authority_unavailable",
                "/result_ir_downstream_authority",
            )
        observation = self._observation_result
        try:
            export_result = observation._source_export_result
            export_context = observation._source_export_context
        except AttributeError as exc:
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_source_invalid",
                "/result_ir_downstream_authority/source",
                type(exc).__name__,
            )
        if (
            seal.receipt is not self.receipt
            or seal.source_execution_plan is not self._source_execution_plan
            or seal.cpu_result is not self._cpu_result
            or seal.observation_result is not observation
            or seal.device_identity_result is not self._device_identity_result
            or seal.export_result is not export_result
            or seal.export_context is not export_context
            or seal.terminal_metric_parity is not self.terminal_metric_parity
            or type(export_result) is not HipFgmresCompletionExportResultV1
            or type(export_context) is not HipFgmresCompletionExportExecutionContextV1
            or type(seal.publication) is not _CompletionExportModelCaseParityAuthorityV1
            or type(seal.snapshot) is not tuple
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_identity_changed",
                "/result_ir_downstream_authority/identity",
            )
        try:
            live = export_context._model_case_parity_authority(export_result)
        except Exception as exc:
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_live_authority_invalid",
                "/result_ir_downstream_authority/publication",
                type(exc).__name__,
            )
        publication = seal.publication
        if (
            type(live) is not _CompletionExportModelCaseParityAuthorityV1
            or live.publication is not publication.publication
            or live.source.source_execution_plan is not seal.source_execution_plan
            or live.publication.result is not seal.export_result
            or live.publication.receipt is not seal.export_result.receipt
            or live.publication.solution_x is not seal.export_result.solution_x
            or live.publication.true_residual is not seal.export_result.true_residual
            or live.publication.solve_record is not seal.export_result.solve_record
            or live.source_snapshot != publication.source_snapshot
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_live_authority_changed",
                "/result_ir_downstream_authority/publication",
            )
        validate_hip_fgmres_terminal_metric_parity_result_v2(
            self.terminal_metric_parity,
        )
        if (
            self.terminal_metric_parity.receipt.receipt_hash
            != self.receipt.bindings.terminal_metric_parity_receipt_hash
            or self.terminal_metric_parity.receipt.bindings.execution_plan_hash
            != self.receipt.bindings.execution_plan_hash
            or self.terminal_metric_parity.receipt.bindings.cpu_result_hash
            != self.receipt.bindings.cpu_result_hash
            or self.terminal_metric_parity.receipt.bindings.terminal_outcome_hash
            != self.receipt.bindings.terminal_outcome_hash
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_terminal_child_binding_changed",
                "/result_ir_downstream_authority/terminal",
            )
        snapshot = _result_ir_downstream_value_snapshot(
            receipt=self.receipt,
            source_execution_plan=self._source_execution_plan,
            cpu_result=self._cpu_result,
            observation_result=observation,
            device_identity_result=self._device_identity_result,
            export_result=export_result,
            publication=live,
            terminal_metric_parity=self.terminal_metric_parity,
        )
        if snapshot != seal.snapshot:
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_snapshot_changed",
                "/result_ir_downstream_authority/snapshot",
            )
        return seal

    def _result_ir_downstream_authority_binding(
        self,
    ) -> tuple[_HipFgmresModelCaseParityResultIrDownstreamAuthorityV2, object]:
        authority = self._result_ir_downstream_authority()
        with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
            token = _RESULT_IR_DOWNSTREAM_IDENTITIES.get(self)
        if type(token) is not object:
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_identity_unavailable",
                "/result_ir_downstream_authority/identity_token",
            )
        return authority, token


_RESULT_IR_DOWNSTREAM_IDENTITY_LOCK = threading.RLock()
_RESULT_IR_DOWNSTREAM_IDENTITIES: weakref.WeakKeyDictionary[
    HipFgmresModelCaseParityResultV2, object
] = weakref.WeakKeyDictionary()


def replay_hip_fgmres_single_terminal_restart_history_v2(
    *,
    cpu_result: CpuFgmresReferenceResultV1,
    outcome: HipFgmresTerminalOutcomeV1,
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2,
) -> HipFgmresSingleTerminalRestartHistoryV2:
    """Replay the exact one-terminal-row history scope and expose its gap."""

    if type(cpu_result) is not CpuFgmresReferenceResultV1:
        _fail("hip_fgmres_model_case_parity_v2_cpu_type_invalid", "/history/cpu")
    if type(outcome) is not HipFgmresTerminalOutcomeV1:
        _fail(
            "hip_fgmres_model_case_parity_v2_outcome_type_invalid",
            "/history/outcome",
        )
    validate_hip_fgmres_terminal_metric_parity_result_v2(
        terminal_metric_parity,
        expected_cpu_result=cpu_result,
        expected_outcome=outcome,
    )
    metrics = outcome.metrics
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    _validate_discrete_parity(cpu_result, outcome, populated)
    if (
        len(cpu_result.history) != 1
        or len(populated) != 1
        or type(metrics) is not HipFgmresTerminalOutcomeMetricsV1
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_history_scope_invalid",
            "/history",
            "Exactly one populated terminal restart row is required.",
        )
    cpu_row = cpu_result.history[0]
    hip_row = populated[0]
    if hip_row.slot_index != 1:
        _fail(
            "hip_fgmres_model_case_parity_v2_history_slot_invalid",
            "/history/terminal_row_slot_index",
        )
    if (
        cpu_row.true_residual_l2 != cpu_result.final_residual_l2
        or cpu_row.true_residual_linf != cpu_result.final_residual_linf
        or cpu_row.scaled_true_residual != cpu_result.scaled_true_residual
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_cpu_terminal_alias_invalid",
            "/history/cpu_terminal_alias",
        )
    if (
        hip_row.true_residual_l2 != metrics.final_residual_l2
        or hip_row.true_residual_linf != metrics.final_residual_linf
        or hip_row.scaled_true_residual != metrics.final_scaled_residual
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_hip_terminal_alias_invalid",
            "/history/hip_terminal_alias",
        )
    return HipFgmresSingleTerminalRestartHistoryV2(
        scope="exactly_one_populated_terminal_restart_row",
        terminal_restart_index=cpu_row.restart_index,
        terminal_row_slot_index=1,
        cpu_terminal_true_residual_alias_verified=True,
        hip_terminal_true_residual_alias_verified=True,
        terminal_true_residual_metrics_delegated_to_normwise_v2=True,
        checkpoint_vector_roles_exported=False,
        general_history_status=(
            "not_verified_missing_checkpoint_vectors_and_scalar_error_models"
        ),
        required_next_abi=HIP_FGMRES_MODEL_CASE_PARITY_REQUIRED_HISTORY_ABI_V2,
        missing_evidence=_MISSING_HISTORY_EVIDENCE,
        estimated_residual=_legacy_metric_comparison(
            "estimated_residual_l2",
            cpu_row.estimated_residual_l2,
            hip_row.estimated_residual_l2,
        ),
        solution_update=_legacy_metric_comparison(
            "solution_update_l2",
            cpu_row.solution_update_l2,
            hip_row.solution_update_l2,
        ),
        general_restart_history_v2_verified=False,
    )


def attest_hip_fgmres_model_case_parity_v2(
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
) -> HipFgmresModelCaseParityResultV2:
    """Attest one exact high-load native-HIP terminal-restart case."""

    receipt, plan, terminal = _evaluate_sources(
        cpu_result, observation_result, device_identity_result
    )
    result = HipFgmresModelCaseParityResultV2(
        receipt=receipt,
        terminal_metric_parity=terminal,
        _cpu_result=cpu_result,
        _observation_result=observation_result,
        _device_identity_result=device_identity_result,
        _source_execution_plan=plan,
    )
    validated = validate_hip_fgmres_model_case_parity_result_v2(
        result,
        expected_cpu_result=cpu_result,
        expected_observation_result=observation_result,
        expected_device_identity_result=device_identity_result,
    )
    sealed = replace(
        validated,
        _result_ir_downstream_authority_seal=(
            _seal_result_ir_downstream_authority(validated)
        ),
    )
    token = object()
    with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
        if sealed in _RESULT_IR_DOWNSTREAM_IDENTITIES:  # pragma: no cover
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_identity_duplicate",
                "/result_ir_downstream_authority/identity_token",
            )
        _RESULT_IR_DOWNSTREAM_IDENTITIES[sealed] = token
    try:
        _, recovered = sealed._result_ir_downstream_authority_binding()
        if recovered is not token:  # pragma: no cover
            _fail(
                "hip_fgmres_model_case_parity_v2_result_ir_identity_changed",
                "/result_ir_downstream_authority/identity_token",
            )
        return sealed
    except BaseException:
        with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
            if _RESULT_IR_DOWNSTREAM_IDENTITIES.get(sealed) is token:
                del _RESULT_IR_DOWNSTREAM_IDENTITIES[sealed]
        raise


def validate_hip_fgmres_model_case_parity_receipt_v2(
    receipt: HipFgmresModelCaseParityReceiptV2,
) -> HipFgmresModelCaseParityReceiptV2:
    """Validate strict serialized v2 semantics without live provenance."""

    if type(receipt) is not HipFgmresModelCaseParityReceiptV2:
        _fail("hip_fgmres_model_case_parity_v2_receipt_type_invalid", "/")
    nested = (
        (receipt.bindings, HipFgmresModelCaseParityBindingsV2, "/bindings"),
        (receipt.dimensions, HipFgmresModelCaseParityDimensionsV2, "/dimensions"),
        (receipt.discrete, HipFgmresModelCaseParityDiscreteComparisonV2, "/discrete"),
        (receipt.solution, HipFgmresModelCaseParityVectorComparisonV1, "/solution"),
        (receipt.history, HipFgmresSingleTerminalRestartHistoryV2, "/history"),
        (
            receipt.compatibility,
            HipFgmresModelCaseParityCompatibilityV2,
            "/compatibility",
        ),
        (receipt.telemetry, HipFgmresModelCaseParityTelemetryV2, "/telemetry"),
        (receipt.claims, HipFgmresModelCaseParityClaimsV2, "/claims"),
    )
    for value, expected, path in nested:
        if type(value) is not expected:
            _fail("hip_fgmres_model_case_parity_v2_nested_type_invalid", path)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_model_case_parity_v2_schema_invalid", path, error.message)
    if (
        receipt.schema_version != HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V2
        or receipt.capability_profile
        != HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2
        or receipt.status != "scoped_case_parity_verified"
        or receipt.evidence_scope != HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V2
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or receipt.discrete != _verified_discrete()
        or receipt.compatibility != HipFgmresModelCaseParityCompatibilityV2()
        or receipt.telemetry != HipFgmresModelCaseParityTelemetryV2()
        or receipt.claims != HipFgmresModelCaseParityClaimsV2()
        or receipt.solution.name != "solution_x"
    ):
        _fail("hip_fgmres_model_case_parity_v2_semantics_invalid", "/")
    _validate_bindings(receipt.bindings)
    _validate_dimensions(receipt.dimensions)
    _validate_vector_comparison(receipt.solution, "/solution")
    if receipt.solution.element_count != receipt.dimensions.free_dof_count:
        _fail(
            "hip_fgmres_model_case_parity_v2_solution_dimension_mismatch",
            "/solution/element_count",
        )
    _validate_history(receipt.history, receipt.bindings)
    if (
        receipt.history.terminal_restart_index
        > receipt.dimensions.maximum_restart_count
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_history_restart_index_invalid",
            "/history/terminal_restart_index",
        )
    expected_case_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2,
            "execution_plan_hash": receipt.bindings.execution_plan_hash,
            "policy_hash": receipt.bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                receipt.bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": (
                receipt.bindings.device_identity_receipt_hash
            ),
            "terminal_metric_parity_receipt_hash": (
                receipt.bindings.terminal_metric_parity_receipt_hash
            ),
        }
    )
    if receipt.case_id != expected_case_id:
        _fail("hip_fgmres_model_case_parity_v2_case_id_invalid", "/case_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if receipt.receipt_hash != expected_hash:
        _fail("hip_fgmres_model_case_parity_v2_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_model_case_parity_result_v2(
    result: HipFgmresModelCaseParityResultV2,
    *,
    expected_cpu_result: CpuFgmresReferenceResultV1 | None = None,
    expected_observation_result: HipFgmresTerminalOutcomeObservationResultV1
    | None = None,
    expected_device_identity_result: HipDeviceIdentityResultV1 | None = None,
) -> HipFgmresModelCaseParityResultV2:
    """Replay the exact retained live sources and every child value receipt."""

    if type(result) is not HipFgmresModelCaseParityResultV2:
        _fail("hip_fgmres_model_case_parity_v2_result_type_invalid", "/")
    validate_hip_fgmres_model_case_parity_receipt_v2(result.receipt)
    if (
        type(result.terminal_metric_parity) is not HipFgmresTerminalMetricParityResultV2
        or type(result._cpu_result) is not CpuFgmresReferenceResultV1
        or type(result._observation_result)
        is not HipFgmresTerminalOutcomeObservationResultV1
        or type(result._device_identity_result) is not HipDeviceIdentityResultV1
        or type(result._source_execution_plan) is not ExecutionPlanV2
    ):
        _fail("hip_fgmres_model_case_parity_v2_source_type_invalid", "/source")
    if (
        expected_cpu_result is not None
        and result._cpu_result is not expected_cpu_result
    ):
        _fail("hip_fgmres_model_case_parity_v2_cpu_source_mismatch", "/source/cpu")
    if (
        expected_observation_result is not None
        and result._observation_result is not expected_observation_result
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_observation_source_mismatch",
            "/source/observation",
        )
    if (
        expected_device_identity_result is not None
        and result._device_identity_result is not expected_device_identity_result
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_device_source_mismatch",
            "/source/device_identity",
        )
    replayed, plan, terminal = _evaluate_sources(
        result._cpu_result,
        result._observation_result,
        result._device_identity_result,
    )
    if plan is not result._source_execution_plan:
        _fail(
            "hip_fgmres_model_case_parity_v2_execution_plan_identity_changed",
            "/source/execution_plan",
        )
    if replayed != result.receipt:
        _fail("hip_fgmres_model_case_parity_v2_replay_mismatch", "/")
    if terminal.receipt != result.terminal_metric_parity.receipt:
        _fail("hip_fgmres_model_case_parity_v2_terminal_child_mismatch", "/terminal")
    validate_hip_fgmres_terminal_metric_parity_result_v2(
        result.terminal_metric_parity,
    )
    if result._result_ir_downstream_authority_seal is not None:
        result._result_ir_downstream_authority()
    return result


def _evaluate_sources(
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
) -> tuple[
    HipFgmresModelCaseParityReceiptV2,
    ExecutionPlanV2,
    HipFgmresTerminalMetricParityResultV2,
]:
    if type(cpu_result) is not CpuFgmresReferenceResultV1:
        _fail("hip_fgmres_model_case_parity_v2_cpu_result_type_invalid", "/cpu")
    if type(observation_result) is not HipFgmresTerminalOutcomeObservationResultV1:
        _fail(
            "hip_fgmres_model_case_parity_v2_observation_type_invalid",
            "/observation",
        )
    if type(device_identity_result) is not HipDeviceIdentityResultV1:
        _fail(
            "hip_fgmres_model_case_parity_v2_device_identity_type_invalid",
            "/device_identity",
        )
    export_result = observation_result._source_export_result
    export_context = observation_result._source_export_context
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        observation_result,
        expected_export_result=export_result,
        expected_export_context=export_context,
    )
    authority = export_context._model_case_parity_authority(export_result)
    if type(authority) is not _CompletionExportModelCaseParityAuthorityV1:
        _fail("hip_fgmres_model_case_parity_v2_authority_invalid", "/authority")
    source = authority.source
    source_witness = _model_source_value_witness(source)
    plan = source_witness.source_execution_plan
    fgmres_plan = source_witness.source_fgmres_plan
    recurrence_plan = source_witness.source_recurrence_plan
    validate_execution_plan_v2(plan)
    _validate_fixed_policy(fgmres_plan.policy)
    validate_cpu_fgmres_reference_result_v1(
        cpu_result,
        expected_plan=plan,
        expected_policy=fgmres_plan.policy,
        expected_initial_full_state=None,
    )
    validate_hip_device_identity_result_v1(
        device_identity_result,
        expected_loaded_runtime=source.loaded_runtime,
    )

    plan_witness, fgmres_witness, recurrence_witness = _detached_plan_lineage(
        plan, fgmres_plan, recurrence_plan
    )
    policy_witness = fgmres_witness.policy
    cpu_witness = _detached_cpu_result(cpu_result, policy_witness)
    observation_receipt = copy.deepcopy(observation_result.receipt)
    device_receipt = copy.deepcopy(device_identity_result.receipt)
    export_receipt = copy.deepcopy(authority.publication.receipt)
    solution_bytes = bytes(authority.publication.solution_x)
    residual_bytes = bytes(authority.publication.true_residual)
    publication_payload_hash = authority.publication.payload_hash
    validate_execution_plan_v2(plan_witness)
    validate_cpu_fgmres_reference_result_v1(
        cpu_witness,
        expected_plan=plan_witness,
        expected_policy=policy_witness,
        expected_initial_full_state=None,
    )
    observation_receipt.to_dict()
    validate_hip_device_identity_receipt_v1(device_receipt)
    if (
        _bytes_sha256(solution_bytes) != authority.publication.buffer_payload_hashes[0]
        or _bytes_sha256(residual_bytes)
        != authority.publication.buffer_payload_hashes[1]
        or export_receipt.receipt_hash != authority.publication.receipt_hash
        or export_receipt.payload_hash != publication_payload_hash
        or tuple(row.role for row in export_receipt.buffers)
        != ("solution_x", "true_residual", "solve_record")
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_publication_snapshot_invalid",
            "/authority/publication",
        )
    source_architecture = source_witness.architecture
    source_device_ordinal = source_witness.device_ordinal
    if (
        observation_receipt.actual_backend != "hip"
        or export_receipt.actual_backend != "hip"
        or device_receipt.actual_backend != "hip"
        or device_receipt.device.selected_ordinal != source_device_ordinal
        or device_receipt.architecture.expected_compiled.normalized
        != source_architecture.lower()
        or device_receipt.architecture.runtime.base
        != device_receipt.architecture.expected_compiled.base
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_native_binding_invalid",
            "/bindings/device",
        )
    outcome = observation_receipt.outcome
    if outcome.outcome_class == "numerical_failure" or cpu_witness.status == (
        "numerical_failure"
    ):
        _fail("hip_fgmres_model_case_parity_v2_numerical_failure", "/outcome")
    terminal = replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan_witness,
        cpu_result=cpu_witness,
        solution_x=solution_bytes,
        true_residual=residual_bytes,
        outcome=outcome,
    )
    history = replay_hip_fgmres_single_terminal_restart_history_v2(
        cpu_result=cpu_witness,
        outcome=outcome,
        terminal_metric_parity=terminal,
    )

    final_authority = export_context._model_case_parity_authority(export_result)
    if (
        type(final_authority) is not _CompletionExportModelCaseParityAuthorityV1
        or final_authority.source_snapshot != authority.source_snapshot
        or final_authority.publication.result is not authority.publication.result
        or final_authority.source.source_execution_plan is not plan
        or final_authority.source.source_fgmres_plan is not fgmres_plan
        or final_authority.source.source_recurrence_plan is not recurrence_plan
        or _model_source_value_witness(final_authority.source).value_snapshot
        != source_witness.value_snapshot
        or plan_witness.plan_hash
        != final_authority.source.source_execution_plan.plan_hash
        or fgmres_witness.plan_hash
        != final_authority.source.source_fgmres_plan.plan_hash
        or recurrence_witness.plan_hash
        != final_authority.source.source_recurrence_plan.plan_hash
        or policy_witness != final_authority.source.source_fgmres_plan.policy
        or _bytes_sha256(solution_bytes)
        != final_authority.publication.buffer_payload_hashes[0]
        or _bytes_sha256(residual_bytes)
        != final_authority.publication.buffer_payload_hashes[1]
        or publication_payload_hash != final_authority.publication.payload_hash
    ):
        _fail("hip_fgmres_model_case_parity_v2_authority_changed", "/authority")
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        observation_result,
        expected_export_result=export_result,
        expected_export_context=export_context,
    )
    validate_cpu_fgmres_reference_result_v1(
        cpu_result,
        expected_plan=plan,
        expected_policy=fgmres_plan.policy,
        expected_initial_full_state=None,
    )
    validate_hip_device_identity_result_v1(
        device_identity_result,
        expected_loaded_runtime=source_witness.loaded_runtime,
    )
    if (
        cpu_result.result_hash != cpu_witness.result_hash
        or observation_result.receipt != observation_receipt
        or device_identity_result.receipt != device_receipt
        or export_result.receipt != export_receipt
        or export_result.payload_hash != publication_payload_hash
    ):
        _fail("hip_fgmres_model_case_parity_v2_source_changed", "/source")

    child = terminal.receipt
    child_bindings = child.bindings
    bindings = HipFgmresModelCaseParityBindingsV2(
        model_ir_content_hash=plan_witness.model_ir_content_hash,
        execution_plan_id=plan_witness.plan_id,
        execution_plan_hash=plan_witness.plan_hash,
        operator_hash=plan_witness.operator_hash,
        numeric_snapshot_hash=plan_witness.numeric_snapshot_hash,
        symbolic_reuse_hash=plan_witness.symbolic_reuse_hash,
        partition_hash=plan_witness.partition_hash,
        load_pattern_id=plan_witness.load_pattern_id,
        fgmres_plan_id=fgmres_witness.plan_id,
        fgmres_plan_hash=fgmres_witness.plan_hash,
        recurrence_plan_id=recurrence_witness.plan_id,
        recurrence_plan_hash=recurrence_witness.plan_hash,
        policy_hash=policy_witness.policy_hash,
        terminal_observation_id=observation_receipt.observation_id,
        terminal_observation_receipt_hash=observation_receipt.receipt_hash,
        terminal_outcome_hash=observation_receipt.outcome_hash,
        completion_export_context_id=export_receipt.context_id,
        completion_export_receipt_hash=export_receipt.receipt_hash,
        completion_export_payload_hash=publication_payload_hash,
        global_context_id=export_receipt.bindings.global_context_id,
        global_receipt_hash=export_receipt.bindings.global_receipt_hash,
        kernel_identity_hash=export_receipt.bindings.kernel_identity_hash,
        kernel_source_sha256=export_receipt.bindings.kernel_source_sha256,
        compiled_architecture=source_architecture,
        runtime_architecture_base=device_receipt.architecture.runtime.base,
        device_ordinal=source_device_ordinal,
        device_identity_receipt_hash=device_receipt.receipt_hash,
        runtime_library_sha256=device_receipt.library.sha256,
        device_uuid_bytes_hex=device_receipt.device.uuid_bytes_hex,
        device_pci_bdf=device_receipt.device.pci_bdf,
        cpu_result_hash=cpu_witness.result_hash,
        terminal_metric_parity_id=child.parity_id,
        terminal_metric_parity_receipt_hash=child.receipt_hash,
        cpu_candidate_componentwise_receipt_hash=(
            child_bindings.cpu_candidate_componentwise_receipt_hash
        ),
        cpu_candidate_normwise_receipt_hash=(
            child_bindings.cpu_candidate_normwise_receipt_hash
        ),
        candidate_replay_componentwise_receipt_hash=(
            child_bindings.candidate_replay_componentwise_receipt_hash
        ),
        candidate_replay_normwise_receipt_hash=(
            child_bindings.candidate_replay_normwise_receipt_hash
        ),
        terminal_metric_projection_hash=child_bindings.terminal_metric_projection_hash,
    )
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    dimensions = HipFgmresModelCaseParityDimensionsV2(
        global_dof_count=fgmres_witness.global_dof_count,
        free_dof_count=fgmres_witness.free_dof_count,
        reduced_csr_nnz=fgmres_witness.reduced_csr_nnz,
        restart_dimension=policy_witness.restart_dimension,
        max_iterations=policy_witness.max_iterations,
        maximum_restart_count=recurrence_witness.maximum_restart_count,
        populated_restart_row_count=1,
        prior_restart_row_count=0,
        exported_checkpoint_solution_vector_count=0,
        exported_checkpoint_true_residual_vector_count=0,
        solve_record_scalar_count_per_restart=5,
    )
    if len(populated) != 1:
        _fail("hip_fgmres_model_case_parity_v2_history_scope_invalid", "/dimensions")
    case_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2,
            "execution_plan_hash": bindings.execution_plan_hash,
            "policy_hash": bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
            "terminal_metric_parity_receipt_hash": (
                bindings.terminal_metric_parity_receipt_hash
            ),
        }
    )
    draft = HipFgmresModelCaseParityReceiptV2(
        schema_version=HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V2,
        capability_profile=HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2,
        status="scoped_case_parity_verified",
        evidence_scope=HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V2,
        actual_backend="hip",
        promotion_eligible=False,
        case_id=case_id,
        bindings=bindings,
        dimensions=dimensions,
        discrete=_verified_discrete(),
        solution=terminal.roundoff_replay.solution_comparison,
        history=history,
        compatibility=HipFgmresModelCaseParityCompatibilityV2(),
        telemetry=HipFgmresModelCaseParityTelemetryV2(),
        claims=HipFgmresModelCaseParityClaimsV2(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_model_case_parity_receipt_v2(receipt), plan, terminal


def _validate_discrete_parity(
    cpu: CpuFgmresReferenceResultV1,
    outcome: HipFgmresTerminalOutcomeV1,
    populated: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...],
) -> None:
    counters = outcome.counters
    if (
        outcome.terminal_status != cpu.status
        or outcome.termination_code != cpu.termination_code
        or counters.effective_iterations != cpu.iteration_count
        or counters.effective_restarts != cpu.restart_count
        or counters.operator_apply_count != cpu.operator_apply_count
        or counters.preconditioner_apply_count != cpu.preconditioner_apply_count
        or len(populated) != len(cpu.history)
    ):
        _fail("hip_fgmres_model_case_parity_v2_discrete_mismatch", "/outcome")
    for index, (cpu_row, hip_row) in enumerate(
        zip(cpu.history, populated, strict=True)
    ):
        if not (
            hip_row.restart_index == cpu_row.restart_index
            and hip_row.start_iteration == cpu_row.start_iteration
            and hip_row.end_iteration == cpu_row.end_iteration
            and hip_row.arnoldi_step_count == cpu_row.arnoldi_step_count
            and hip_row.reorthogonalization_count == cpu_row.reorthogonalization_count
            and hip_row.termination_hint == cpu_row.termination_hint
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_history_discrete_mismatch",
                f"/outcome/history/{index}",
            )


def _legacy_metric_comparison(
    name: Literal["estimated_residual_l2", "solution_update_l2"],
    reference: float,
    candidate: float,
) -> HipFgmresLegacyHistoryMetricComparisonV2:
    if not _scalar_close(reference, candidate):
        _fail(
            "hip_fgmres_model_case_parity_v2_legacy_history_metric_mismatch",
            f"/history/{name}",
        )
    difference = abs(candidate - reference)
    tolerance = (
        HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        + HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 * abs(reference)
    )
    ratio = 0.0 if tolerance == 0.0 else difference / tolerance
    return HipFgmresLegacyHistoryMetricComparisonV2(
        name=name,
        reference_record=reference,
        candidate_record=candidate,
        absolute_difference=difference,
        legacy_fixed_tolerance=tolerance,
        maximum_tolerance_ratio=ratio,
        legacy_fixed_gate_passed=True,
        roundoff_error_model_verified=False,
    )


def _verified_discrete() -> HipFgmresModelCaseParityDiscreteComparisonV2:
    return HipFgmresModelCaseParityDiscreteComparisonV2(
        terminal_status_match=True,
        termination_code_match=True,
        iteration_count_match=True,
        restart_count_match=True,
        operator_apply_count_match=True,
        preconditioner_apply_count_match=True,
        restart_history_shape_match=True,
        restart_history_discrete_fields_match=True,
        terminal_metrics_normwise_bound_verified=True,
        terminal_restart_true_residual_metrics_normwise_bound_verified=True,
        estimated_residual_legacy_fixed_gate_passed=True,
        solution_update_legacy_fixed_gate_passed=True,
        general_restart_history_metric_v2_verified=False,
        numerical_failure_absent=True,
    )


def _seal_result_ir_downstream_authority(
    result: HipFgmresModelCaseParityResultV2,
) -> _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2:
    observation = result._observation_result
    export_result = observation._source_export_result
    export_context = observation._source_export_context
    if (
        type(export_result) is not HipFgmresCompletionExportResultV1
        or type(export_context) is not HipFgmresCompletionExportExecutionContextV1
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_result_ir_source_invalid",
            "/result_ir_downstream_authority/source",
        )
    publication = export_context._model_case_parity_authority(export_result)
    if (
        type(publication) is not _CompletionExportModelCaseParityAuthorityV1
        or publication.source.source_execution_plan is not result._source_execution_plan
        or publication.publication.result is not export_result
        or publication.publication.receipt is not export_result.receipt
        or publication.publication.solution_x is not export_result.solution_x
        or publication.publication.true_residual is not export_result.true_residual
        or publication.publication.solve_record is not export_result.solve_record
    ):
        _fail(
            "hip_fgmres_model_case_parity_v2_result_ir_live_authority_changed",
            "/result_ir_downstream_authority/publication",
        )
    snapshot = _result_ir_downstream_value_snapshot(
        receipt=result.receipt,
        source_execution_plan=result._source_execution_plan,
        cpu_result=result._cpu_result,
        observation_result=observation,
        device_identity_result=result._device_identity_result,
        export_result=export_result,
        publication=publication,
        terminal_metric_parity=result.terminal_metric_parity,
    )
    return _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2(
        receipt=result.receipt,
        source_execution_plan=result._source_execution_plan,
        cpu_result=result._cpu_result,
        observation_result=observation,
        device_identity_result=result._device_identity_result,
        export_result=export_result,
        export_context=export_context,
        publication=publication,
        terminal_metric_parity=result.terminal_metric_parity,
        snapshot=snapshot,
    )


def _result_ir_downstream_value_snapshot(
    *,
    receipt: HipFgmresModelCaseParityReceiptV2,
    source_execution_plan: ExecutionPlanV2,
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
    export_result: HipFgmresCompletionExportResultV1,
    publication: _CompletionExportModelCaseParityAuthorityV1,
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2,
) -> tuple[Any, ...]:
    plan_arrays = tuple(
        (
            row.name,
            type(source_execution_plan.array(row.name)),
            source_execution_plan.array(row.name).dtype.str,
            tuple(int(value) for value in source_execution_plan.array(row.name).shape),
            bool(source_execution_plan.array(row.name).flags.c_contiguous),
            bool(source_execution_plan.array(row.name).flags.writeable),
            _bytes_sha256(source_execution_plan.array(row.name).tobytes(order="C")),
        )
        for row in source_execution_plan.descriptors
    )
    cpu_arrays = tuple(
        (
            name,
            type(cpu_result.array(name)),
            cpu_result.array(name).dtype.str,
            tuple(int(value) for value in cpu_result.array(name).shape),
            bool(cpu_result.array(name).flags.c_contiguous),
            bool(cpu_result.array(name).flags.writeable),
            _bytes_sha256(cpu_result.array(name).tobytes(order="C")),
        )
        for name in ("reduced_solution", "true_residual")
    )
    source_witness = _model_source_value_witness(publication.source)
    published = publication.publication
    return (
        type(receipt),
        canonical_hash(_receipt_payload(receipt, include_hash=True)),
        type(source_execution_plan),
        canonical_hash(source_execution_plan.to_dict()),
        id(source_execution_plan._source_buffers),
        plan_arrays,
        type(cpu_result),
        canonical_hash(cpu_result.to_dict()),
        cpu_arrays,
        type(observation_result),
        canonical_hash(observation_result.receipt.to_dict()),
        type(device_identity_result),
        canonical_hash(device_identity_result.receipt.to_dict()),
        type(export_result),
        canonical_hash(export_result.receipt.to_dict()),
        export_result.payload_hash,
        (len(export_result.solution_x), _bytes_sha256(export_result.solution_x)),
        (len(export_result.true_residual), _bytes_sha256(export_result.true_residual)),
        (len(export_result.solve_record), _bytes_sha256(export_result.solve_record)),
        type(publication),
        _private_snapshot_token(publication.source_snapshot),
        _private_snapshot_token(source_witness.value_snapshot),
        type(published),
        published.receipt_hash,
        published.payload_hash,
        published.buffer_payload_hashes,
        type(terminal_metric_parity),
        terminal_metric_parity.receipt.receipt_hash,
        terminal_metric_parity.receipt.parity_id,
    )


def _validate_bindings(bindings: HipFgmresModelCaseParityBindingsV2) -> None:
    if type(bindings.device_ordinal) is not int or bindings.device_ordinal < 0:
        _fail(
            "hip_fgmres_model_case_parity_v2_binding_invalid",
            "/bindings/device_ordinal",
        )
    hash_fields = tuple(
        name
        for name in bindings.__dataclass_fields__
        if name.endswith("_hash")
        or name.endswith("_sha256")
        or name in {"terminal_observation_id", "completion_export_context_id"}
    )
    if any(_HASH_RE.fullmatch(getattr(bindings, name)) is None for name in hash_fields):
        _fail("hip_fgmres_model_case_parity_v2_binding_hash_invalid", "/bindings")
    if (
        _EXECUTION_PLAN_ID_RE.fullmatch(bindings.execution_plan_id) is None
        or _FGMRES_PLAN_ID_RE.fullmatch(bindings.fgmres_plan_id) is None
        or _RECURRENCE_PLAN_ID_RE.fullmatch(bindings.recurrence_plan_id) is None
    ):
        _fail("hip_fgmres_model_case_parity_v2_binding_id_invalid", "/bindings")


def _validate_dimensions(dimensions: HipFgmresModelCaseParityDimensionsV2) -> None:
    if any(
        type(getattr(dimensions, name)) is not int
        for name in dimensions.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_case_parity_v2_dimension_type_invalid", "/dimensions")
    if (
        dimensions.global_dof_count <= 0
        or dimensions.free_dof_count <= 0
        or dimensions.free_dof_count > dimensions.global_dof_count
        or dimensions.reduced_csr_nnz <= 0
        or dimensions.restart_dimension <= 0
        or dimensions.max_iterations <= 0
        or dimensions.maximum_restart_count
        != (dimensions.max_iterations + dimensions.restart_dimension - 1)
        // dimensions.restart_dimension
        or dimensions.populated_restart_row_count != 1
        or dimensions.prior_restart_row_count != 0
        or dimensions.exported_checkpoint_solution_vector_count != 0
        or dimensions.exported_checkpoint_true_residual_vector_count != 0
        or dimensions.solve_record_scalar_count_per_restart != 5
    ):
        _fail("hip_fgmres_model_case_parity_v2_dimension_invalid", "/dimensions")


def _validate_history(
    history: HipFgmresSingleTerminalRestartHistoryV2,
    bindings: HipFgmresModelCaseParityBindingsV2,
) -> None:
    if (
        history.scope != "exactly_one_populated_terminal_restart_row"
        or type(history.terminal_restart_index) is not int
        or history.terminal_restart_index <= 0
        or history.terminal_row_slot_index != 1
        or history.cpu_terminal_true_residual_alias_verified is not True
        or history.hip_terminal_true_residual_alias_verified is not True
        or history.terminal_true_residual_metrics_delegated_to_normwise_v2 is not True
        or history.checkpoint_vector_roles_exported is not False
        or history.general_history_status
        != "not_verified_missing_checkpoint_vectors_and_scalar_error_models"
        or history.required_next_abi
        != HIP_FGMRES_MODEL_CASE_PARITY_REQUIRED_HISTORY_ABI_V2
        or history.missing_evidence != _MISSING_HISTORY_EVIDENCE
        or history.general_restart_history_v2_verified is not False
    ):
        _fail("hip_fgmres_model_case_parity_v2_history_invalid", "/history")
    for comparison, name in (
        (history.estimated_residual, "estimated_residual_l2"),
        (history.solution_update, "solution_update_l2"),
    ):
        if (
            type(comparison) is not HipFgmresLegacyHistoryMetricComparisonV2
            or comparison.name != name
            or comparison.legacy_fixed_gate_passed is not True
            or comparison.roundoff_error_model_verified is not False
            or comparison.maximum_tolerance_ratio > 1.0
            or any(
                type(value) is not float
                or not math.isfinite(value)
                or value < 0.0
                or (value == 0.0 and math.copysign(1.0, value) < 0.0)
                for value in (
                    comparison.reference_record,
                    comparison.candidate_record,
                    comparison.absolute_difference,
                    comparison.legacy_fixed_tolerance,
                    comparison.maximum_tolerance_ratio,
                )
            )
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_history_metric_invalid",
                f"/history/{name}",
            )
        expected_difference = abs(
            comparison.candidate_record - comparison.reference_record
        )
        expected_tolerance = (
            HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
            + HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1
            * abs(comparison.reference_record)
        )
        expected_ratio = (
            0.0
            if expected_tolerance == 0.0
            else expected_difference / expected_tolerance
        )
        if (
            comparison.absolute_difference != expected_difference
            or comparison.legacy_fixed_tolerance != expected_tolerance
            or comparison.maximum_tolerance_ratio != expected_ratio
            or not _scalar_close(
                comparison.reference_record, comparison.candidate_record
            )
        ):
            _fail(
                "hip_fgmres_model_case_parity_v2_history_metric_replay_invalid",
                f"/history/{name}",
            )
    if bindings.terminal_metric_parity_receipt_hash == _ZERO_HASH:
        _fail(
            "hip_fgmres_model_case_parity_v2_history_terminal_binding_invalid",
            "/history",
        )


def _receipt_payload(
    receipt: HipFgmresModelCaseParityReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "case_id": receipt.case_id,
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "discrete": receipt.discrete.to_dict(),
        "solution": receipt.solution.to_dict(),
        "history": receipt.history.to_dict(),
        "compatibility": receipt.compatibility.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
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


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelCaseParityV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_MODEL_CASE_PARITY_REQUIRED_HISTORY_ABI_V2",
    "HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V2",
    "HipFgmresLegacyHistoryMetricComparisonV2",
    "HipFgmresModelCaseParityBindingsV2",
    "HipFgmresModelCaseParityClaimsV2",
    "HipFgmresModelCaseParityCompatibilityV2",
    "HipFgmresModelCaseParityDimensionsV2",
    "HipFgmresModelCaseParityDiscreteComparisonV2",
    "HipFgmresModelCaseParityReceiptV2",
    "HipFgmresModelCaseParityResultV2",
    "HipFgmresModelCaseParityTelemetryV2",
    "HipFgmresModelCaseParityV2Error",
    "HipFgmresSingleTerminalRestartHistoryV2",
    "attest_hip_fgmres_model_case_parity_v2",
    "replay_hip_fgmres_single_terminal_restart_history_v2",
    "validate_hip_fgmres_model_case_parity_receipt_v2",
    "validate_hip_fgmres_model_case_parity_result_v2",
]
