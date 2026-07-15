"""Exact process-local CPU/HIP parity for one completed FGMRES model case.

The public receipt is deliberately non-promoting.  Authoritative validation
requires the retained CPU result, terminal observation, HIP device identity,
and the still-live completion-export context.  A serialized receipt alone
cannot prove process-local object identity or native execution provenance.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Literal, NamedTuple, NoReturn
import weakref

from jsonschema import Draft202012Validator
import numpy as np

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
    FgmresRestartRecord,
    validate_cpu_fgmres_reference_result_v1,
)

from .fgmres_completion_export_v1 import (
    _CompletionExportModelCaseParityAuthorityV1,
    HipFgmresCompletionExportExecutionContextV1,
    HipFgmresCompletionExportResultV1,
)
from .fgmres_plan import (
    HipFgmresPlanV1,
    _snapshot_execution_plan,
    validate_hip_fgmres_plan_v1,
)
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    _validated_source_snapshot,
    compile_hip_fgmres_recurrence_plan_v2,
    validate_hip_fgmres_recurrence_plan_v2,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeObservationResultV1,
    HipFgmresTerminalOutcomeRestartRowV1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)


HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-model-case-parity.v1"
)
HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_model_case_cpu_hip_fgmres_parity"
)
HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1 = (
    "process_local_exact_model_case_native_hip_cpu_parity_non_promoting"
)
HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 = 1.0e-8
HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1 = 1.0e-12

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXECUTION_PLAN_ID_RE = re.compile(r"^SparsePlan:[0-9a-f]{24}$")
_FGMRES_PLAN_ID_RE = re.compile(r"^HipFgmresPlan:[0-9a-f]{24}$")
_RECURRENCE_PLAN_ID_RE = re.compile(r"^HipFgmresRecurrencePlan:[0-9a-f]{24}$")
_SCHEMA_RESOURCE = "hip_fgmres_model_case_parity_v1.schema.json"
_VECTOR_NAMES = ("solution_x", "true_residual", "true_residual_replay")


class HipFgmresModelCaseParityV1Error(ValueError):
    """Stable fail-closed model-case parity error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


class _ModelSourceValueWitnessV1(NamedTuple):
    loaded_runtime: Any
    loaded_runtime_identity: int
    architecture: str
    device_ordinal: int
    source_fgmres_plan: Any
    source_fgmres_plan_identity: int
    fgmres_plan_id: str
    fgmres_plan_hash: str
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    source_recurrence_plan: Any
    source_recurrence_plan_identity: int
    recurrence_plan_id: str
    recurrence_plan_hash: str
    maximum_restart_count: int
    source_execution_plan: ExecutionPlanV2
    source_execution_plan_identity: int
    execution_plan_id: str
    execution_plan_hash: str
    policy_hash: str
    value_snapshot: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityBindingsV1:
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
    retained_execution_plan_snapshot_identity_verified: Literal[True] = True
    process_local_runtime_identity_verified: Literal[True] = True
    process_local_identities_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityDimensionsV1:
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    populated_restart_row_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityToleranceV1:
    relative_tolerance: float = HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1
    absolute_tolerance: float = HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
    comparison_rule: Literal["componentwise_abs_le_atol_plus_rtol_times_abs_cpu"] = (
        "componentwise_abs_le_atol_plus_rtol_times_abs_cpu"
    )
    caller_relaxation_allowed: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityVectorComparisonV1:
    name: Literal["solution_x", "true_residual", "true_residual_replay"]
    element_count: int
    cpu_or_reference_sha256: str
    hip_or_candidate_sha256: str
    maximum_absolute_error: float
    l2_absolute_error: float
    reference_l2: float
    relative_l2_error: float
    maximum_tolerance_ratio: float
    relative_l2_tolerance_passed: bool
    absolute_linf_tolerance_passed: bool
    componentwise_tolerance_passed: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityDiscreteComparisonV1:
    terminal_status_match: Literal[True]
    termination_code_match: Literal[True]
    iteration_count_match: Literal[True]
    restart_count_match: Literal[True]
    operator_apply_count_match: Literal[True]
    preconditioner_apply_count_match: Literal[True]
    restart_history_shape_match: Literal[True]
    restart_history_discrete_fields_match: Literal[True]
    restart_history_metrics_within_tolerance: Literal[True]
    terminal_metrics_within_tolerance: Literal[True]
    numerical_failure_absent: Literal[True]

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityTelemetryV1:
    cpu_reference_result_count: Literal[1] = 1
    hip_terminal_observation_result_count: Literal[1] = 1
    hip_device_identity_result_count: Literal[1] = 1
    independent_true_residual_replay_count: Literal[1] = 1
    compared_vector_count: Literal[3] = 3
    additional_d2h_operation_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    device_allocation_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    explicit_stream_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelCaseParityClaimsV1:
    exact_retained_execution_plan_snapshot_bound: Literal[True] = True
    deterministic_cpu_reference_replayed: Literal[True] = True
    actual_hip_backend_verified: Literal[True] = True
    runtime_device_identity_verified: Literal[True] = True
    terminal_outcome_parity_verified: Literal[True] = True
    solution_vector_parity_verified: Literal[True] = True
    exported_residual_parity_verified: Literal[True] = True
    independent_operator_residual_replay_verified: Literal[True] = True
    fp64_relative_tolerance_at_most_1e_8: Literal[True] = True
    single_model_case_numerical_parity_verified: Literal[True] = True
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
class HipFgmresModelCaseParityReceiptV1:
    schema_version: str
    capability_profile: str
    status: Literal["case_parity_verified"]
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    case_id: str
    bindings: HipFgmresModelCaseParityBindingsV1
    dimensions: HipFgmresModelCaseParityDimensionsV1
    tolerance: HipFgmresModelCaseParityToleranceV1
    discrete: HipFgmresModelCaseParityDiscreteComparisonV1
    vectors: tuple[HipFgmresModelCaseParityVectorComparisonV1, ...]
    telemetry: HipFgmresModelCaseParityTelemetryV1
    claims: HipFgmresModelCaseParityClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_case_parity_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1:
    """Private process-local seal for a ResultIR downstream consumer."""

    receipt: HipFgmresModelCaseParityReceiptV1
    source_execution_plan: ExecutionPlanV2
    cpu_result: CpuFgmresReferenceResultV1
    observation_result: HipFgmresTerminalOutcomeObservationResultV1
    device_identity_result: HipDeviceIdentityResultV1
    export_result: HipFgmresCompletionExportResultV1
    export_context: HipFgmresCompletionExportExecutionContextV1
    publication: _CompletionExportModelCaseParityAuthorityV1
    snapshot: tuple[Any, ...]


class _WeakReferenceableModelCaseParityResultV1:
    """Python 3.10-compatible weak-reference slot for issuance tracking."""

    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelCaseParityResultV1(_WeakReferenceableModelCaseParityResultV1):
    receipt: HipFgmresModelCaseParityReceiptV1
    _cpu_result: CpuFgmresReferenceResultV1 = dataclass_field(
        repr=False,
        compare=False,
    )
    _observation_result: HipFgmresTerminalOutcomeObservationResultV1 = dataclass_field(
        repr=False, compare=False
    )
    _device_identity_result: HipDeviceIdentityResultV1 = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_execution_plan: ExecutionPlanV2 = dataclass_field(
        repr=False,
        compare=False,
    )
    _result_ir_downstream_authority_seal: (
        _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1 | None
    ) = dataclass_field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_case_parity_result_v1(self)
        return self.receipt.to_dict()

    def _result_ir_downstream_authority(
        self,
    ) -> _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1:
        """Recover the sealed live authority without replaying the CPU solve."""

        seal = self._result_ir_downstream_authority_seal
        if type(seal) is not _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_authority_unavailable",
                "/result_ir_downstream_authority",
            )
        observation = self._observation_result
        try:
            export_result = observation._source_export_result
            export_context = observation._source_export_context
        except AttributeError as exc:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_source_invalid",
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
            or type(export_result) is not HipFgmresCompletionExportResultV1
            or type(export_context) is not HipFgmresCompletionExportExecutionContextV1
            or type(seal.publication) is not _CompletionExportModelCaseParityAuthorityV1
            or type(seal.snapshot) is not tuple
        ):
            _fail(
                "hip_fgmres_model_case_parity_result_ir_identity_changed",
                "/result_ir_downstream_authority/identity",
            )
        try:
            live = export_context._model_case_parity_authority(export_result)
        except Exception as exc:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_live_authority_invalid",
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
                "hip_fgmres_model_case_parity_result_ir_live_authority_changed",
                "/result_ir_downstream_authority/publication",
            )
        try:
            snapshot = _result_ir_downstream_value_snapshot(
                receipt=self.receipt,
                source_execution_plan=self._source_execution_plan,
                cpu_result=self._cpu_result,
                observation_result=observation,
                device_identity_result=self._device_identity_result,
                export_result=export_result,
                export_context=export_context,
                publication=live,
            )
        except HipFgmresModelCaseParityV1Error:
            raise
        except Exception as exc:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_snapshot_invalid",
                "/result_ir_downstream_authority/snapshot",
                type(exc).__name__,
            )
        if snapshot != seal.snapshot:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_snapshot_changed",
                "/result_ir_downstream_authority/snapshot",
            )
        return seal

    def _result_ir_downstream_authority_binding(
        self,
    ) -> tuple[_HipFgmresModelCaseParityResultIrDownstreamAuthorityV1, object]:
        """Return live authority plus a non-recycled exact-result token."""

        authority = self._result_ir_downstream_authority()
        with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
            token = _RESULT_IR_DOWNSTREAM_IDENTITIES.get(self)
        if type(token) is not object:
            _fail(
                "hip_fgmres_model_case_parity_result_ir_identity_unavailable",
                "/result_ir_downstream_authority/identity_token",
            )
        return authority, token


_RESULT_IR_DOWNSTREAM_IDENTITY_LOCK = threading.RLock()
_RESULT_IR_DOWNSTREAM_IDENTITIES: weakref.WeakKeyDictionary[
    HipFgmresModelCaseParityResultV1,
    object,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_model_case_parity_v1(
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
) -> HipFgmresModelCaseParityResultV1:
    """Attest one exact native-HIP case against the deterministic CPU oracle."""

    receipt, execution_plan = _evaluate_sources(
        cpu_result,
        observation_result,
        device_identity_result,
    )
    result = HipFgmresModelCaseParityResultV1(
        receipt=receipt,
        _cpu_result=cpu_result,
        _observation_result=observation_result,
        _device_identity_result=device_identity_result,
        _source_execution_plan=execution_plan,
    )
    validated = validate_hip_fgmres_model_case_parity_result_v1(
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
    identity_token = object()
    with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
        if sealed in _RESULT_IR_DOWNSTREAM_IDENTITIES:  # pragma: no cover
            _fail(
                "hip_fgmres_model_case_parity_result_ir_identity_duplicate",
                "/result_ir_downstream_authority/identity_token",
            )
        _RESULT_IR_DOWNSTREAM_IDENTITIES[sealed] = identity_token
    try:
        _, recovered_token = sealed._result_ir_downstream_authority_binding()
        if recovered_token is not identity_token:  # pragma: no cover
            _fail(
                "hip_fgmres_model_case_parity_result_ir_identity_changed",
                "/result_ir_downstream_authority/identity_token",
            )
        return sealed
    except BaseException:
        with _RESULT_IR_DOWNSTREAM_IDENTITY_LOCK:
            if _RESULT_IR_DOWNSTREAM_IDENTITIES.get(sealed) is identity_token:
                del _RESULT_IR_DOWNSTREAM_IDENTITIES[sealed]
        raise


def validate_hip_fgmres_model_case_parity_receipt_v1(
    receipt: HipFgmresModelCaseParityReceiptV1,
) -> HipFgmresModelCaseParityReceiptV1:
    """Validate serialized structure without asserting process-local provenance."""

    if type(receipt) is not HipFgmresModelCaseParityReceiptV1:
        _fail("hip_fgmres_model_case_parity_receipt_type_invalid", "/")
    nested = (
        (receipt.bindings, HipFgmresModelCaseParityBindingsV1, "/bindings"),
        (receipt.dimensions, HipFgmresModelCaseParityDimensionsV1, "/dimensions"),
        (receipt.tolerance, HipFgmresModelCaseParityToleranceV1, "/tolerance"),
        (receipt.discrete, HipFgmresModelCaseParityDiscreteComparisonV1, "/discrete"),
        (receipt.telemetry, HipFgmresModelCaseParityTelemetryV1, "/telemetry"),
        (receipt.claims, HipFgmresModelCaseParityClaimsV1, "/claims"),
    )
    for value, expected, path in nested:
        if type(value) is not expected:
            _fail("hip_fgmres_model_case_parity_nested_type_invalid", path)
    if (
        type(receipt.vectors) is not tuple
        or len(receipt.vectors) != 3
        or any(
            type(row) is not HipFgmresModelCaseParityVectorComparisonV1
            for row in receipt.vectors
        )
    ):
        _fail("hip_fgmres_model_case_parity_vectors_invalid", "/vectors")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_model_case_parity_schema_invalid", path, error.message)
    if (
        receipt.schema_version != HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1
        or receipt.status != "case_parity_verified"
        or receipt.evidence_scope != HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or receipt.tolerance != HipFgmresModelCaseParityToleranceV1()
        or receipt.discrete != _verified_discrete()
        or receipt.telemetry != HipFgmresModelCaseParityTelemetryV1()
        or receipt.claims != HipFgmresModelCaseParityClaimsV1()
        or tuple(row.name for row in receipt.vectors) != _VECTOR_NAMES
    ):
        _fail("hip_fgmres_model_case_parity_semantics_invalid", "/")
    _validate_exact_nested_scalar_types(receipt)
    _validate_bindings(receipt.bindings)
    _validate_dimensions(receipt.dimensions)
    for index, row in enumerate(receipt.vectors):
        _validate_vector_comparison(row, f"/vectors/{index}")
        if row.element_count != receipt.dimensions.free_dof_count:
            _fail(
                "hip_fgmres_model_case_parity_vector_dimension_mismatch",
                f"/vectors/{index}/element_count",
            )
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("hip_fgmres_model_case_parity_receipt_hash_invalid", "/receipt_hash")
    expected_case_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": receipt.bindings.execution_plan_hash,
            "policy_hash": receipt.bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                receipt.bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": (
                receipt.bindings.device_identity_receipt_hash
            ),
        }
    )
    if receipt.case_id != expected_case_id:
        _fail("hip_fgmres_model_case_parity_case_id_invalid", "/case_id")
    return receipt


def validate_hip_fgmres_model_case_parity_result_v1(
    result: HipFgmresModelCaseParityResultV1,
    *,
    expected_cpu_result: CpuFgmresReferenceResultV1 | None = None,
    expected_observation_result: (
        HipFgmresTerminalOutcomeObservationResultV1 | None
    ) = None,
    expected_device_identity_result: HipDeviceIdentityResultV1 | None = None,
) -> HipFgmresModelCaseParityResultV1:
    """Recompute the receipt through the exact retained source authorities."""

    if type(result) is not HipFgmresModelCaseParityResultV1:
        _fail("hip_fgmres_model_case_parity_result_type_invalid", "/")
    validate_hip_fgmres_model_case_parity_receipt_v1(result.receipt)
    if (
        type(result._cpu_result) is not CpuFgmresReferenceResultV1
        or type(result._observation_result)
        is not HipFgmresTerminalOutcomeObservationResultV1
        or type(result._device_identity_result) is not HipDeviceIdentityResultV1
        or type(result._source_execution_plan) is not ExecutionPlanV2
    ):
        _fail("hip_fgmres_model_case_parity_source_type_invalid", "/source")
    if (
        expected_cpu_result is not None
        and result._cpu_result is not expected_cpu_result
    ):
        _fail("hip_fgmres_model_case_parity_cpu_source_mismatch", "/source/cpu")
    if (
        expected_observation_result is not None
        and result._observation_result is not expected_observation_result
    ):
        _fail(
            "hip_fgmres_model_case_parity_observation_source_mismatch",
            "/source/observation",
        )
    if (
        expected_device_identity_result is not None
        and result._device_identity_result is not expected_device_identity_result
    ):
        _fail(
            "hip_fgmres_model_case_parity_device_source_mismatch",
            "/source/device_identity",
        )
    replayed, execution_plan = _evaluate_sources(
        result._cpu_result,
        result._observation_result,
        result._device_identity_result,
    )
    if execution_plan is not result._source_execution_plan:
        _fail(
            "hip_fgmres_model_case_parity_execution_plan_identity_changed",
            "/source/execution_plan",
        )
    if replayed != result.receipt:
        _fail("hip_fgmres_model_case_parity_replay_mismatch", "/")
    if result._result_ir_downstream_authority_seal is not None:
        result._result_ir_downstream_authority()
    return result


def replay_hip_fgmres_detached_model_case_numerics_v1(
    *,
    execution_plan: ExecutionPlanV2,
    cpu_result: CpuFgmresReferenceResultV1,
    solution_x: bytes,
    true_residual: bytes,
    outcome: Any,
) -> tuple[HipFgmresModelCaseParityVectorComparisonV1, ...]:
    """Replay detached numerical bytes without asserting HIP provenance."""

    validate_execution_plan_v2(execution_plan)
    validate_cpu_fgmres_reference_result_v1(
        cpu_result,
        expected_plan=execution_plan,
        expected_policy=cpu_result.policy,
        expected_initial_full_state=None,
    )
    free_dof_count = int(execution_plan.array("free_dofs").size)
    hip_solution = _f64_vector_from_bytes(solution_x, free_dof_count)
    hip_residual = _f64_vector_from_bytes(true_residual, free_dof_count)
    cpu_solution = _exact_f64_vector(cpu_result.reduced_solution, free_dof_count)
    cpu_residual = _exact_f64_vector(cpu_result.true_residual, free_dof_count)
    replayed_residual = _replay_true_residual(execution_plan, hip_solution)
    vectors = (
        _compare_vector("solution_x", cpu_solution, hip_solution),
        _compare_vector("true_residual", cpu_residual, hip_residual),
        _compare_vector("true_residual_replay", hip_residual, replayed_residual),
    )
    try:
        populated = tuple(row for row in outcome.restart_rows if row.populated)
    except (AttributeError, TypeError) as exc:
        _fail(
            "hip_fgmres_model_case_parity_detached_outcome_invalid",
            "/outcome",
            type(exc).__name__,
        )
    _validate_discrete_parity(cpu_result, outcome, populated)
    _validate_metric_parity(cpu_result, outcome, populated)
    return vectors


def _evaluate_sources(
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
) -> tuple[HipFgmresModelCaseParityReceiptV1, ExecutionPlanV2]:
    if type(cpu_result) is not CpuFgmresReferenceResultV1:
        _fail("hip_fgmres_model_case_parity_cpu_result_type_invalid", "/cpu")
    if type(observation_result) is not HipFgmresTerminalOutcomeObservationResultV1:
        _fail(
            "hip_fgmres_model_case_parity_observation_type_invalid",
            "/observation",
        )
    if type(device_identity_result) is not HipDeviceIdentityResultV1:
        _fail(
            "hip_fgmres_model_case_parity_device_identity_type_invalid",
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
        _fail("hip_fgmres_model_case_parity_authority_invalid", "/authority")
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

    # Every numerical and plan-metadata read below uses one coherent detached,
    # self-validating lineage.  In particular, receipt IDs/hashes must never be
    # reread from the live FGMRES/recurrence objects after the check that
    # authorizes their use.
    plan_witness, fgmres_witness, recurrence_witness = _detached_plan_lineage(
        plan,
        fgmres_plan,
        recurrence_plan,
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
    # A detached observation receipt can only be checked structurally.  The
    # public validator intentionally requires the live export result/context
    # provenance pair, which is validated above through ``observation_result``.
    observation_receipt.to_dict()
    validate_hip_device_identity_receipt_v1(device_receipt)
    if (
        _bytes_sha256(solution_bytes) != authority.publication.buffer_payload_hashes[0]
        or _bytes_sha256(residual_bytes)
        != authority.publication.buffer_payload_hashes[1]
        or export_receipt.receipt_hash != authority.publication.receipt_hash
        or export_receipt.payload_hash != publication_payload_hash
    ):
        _fail(
            "hip_fgmres_model_case_parity_publication_snapshot_invalid",
            "/authority/publication",
        )

    source_architecture = source_witness.architecture
    source_device_ordinal = source_witness.device_ordinal
    source_loaded_runtime = source_witness.loaded_runtime
    fgmres_plan_id = fgmres_witness.plan_id
    fgmres_plan_hash = fgmres_witness.plan_hash
    recurrence_plan_id = recurrence_witness.plan_id
    recurrence_plan_hash = recurrence_witness.plan_hash
    recurrence_maximum_restart_count = recurrence_witness.maximum_restart_count
    fgmres_global_dof_count = fgmres_witness.global_dof_count
    fgmres_free_dof_count = fgmres_witness.free_dof_count
    fgmres_reduced_csr_nnz = fgmres_witness.reduced_csr_nnz
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
            "hip_fgmres_model_case_parity_native_binding_invalid",
            "/bindings/device",
        )
    outcome = observation_receipt.outcome
    if (
        outcome.outcome_class == "numerical_failure"
        or cpu_witness.status == "numerical_failure"
    ):
        _fail(
            "hip_fgmres_model_case_parity_numerical_failure",
            "/outcome",
        )
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    _validate_discrete_parity(cpu_witness, outcome, populated)
    _validate_metric_parity(cpu_witness, outcome, populated)

    hip_solution = _f64_vector_from_bytes(solution_bytes, fgmres_free_dof_count)
    hip_residual = _f64_vector_from_bytes(residual_bytes, fgmres_free_dof_count)
    cpu_solution = _exact_f64_vector(
        cpu_witness.reduced_solution, fgmres_free_dof_count
    )
    cpu_residual = _exact_f64_vector(cpu_witness.true_residual, fgmres_free_dof_count)
    replayed_residual = _replay_true_residual(plan_witness, hip_solution)
    vectors = (
        _compare_vector("solution_x", cpu_solution, hip_solution),
        _compare_vector("true_residual", cpu_residual, hip_residual),
        _compare_vector("true_residual_replay", hip_residual, replayed_residual),
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
        or fgmres_witness.plan_id != final_authority.source.source_fgmres_plan.plan_id
        or fgmres_witness.plan_hash
        != final_authority.source.source_fgmres_plan.plan_hash
        or recurrence_witness.plan_id
        != final_authority.source.source_recurrence_plan.plan_id
        or recurrence_witness.plan_hash
        != final_authority.source.source_recurrence_plan.plan_hash
        or policy_witness != final_authority.source.source_fgmres_plan.policy
        or _bytes_sha256(solution_bytes)
        != final_authority.publication.buffer_payload_hashes[0]
        or _bytes_sha256(residual_bytes)
        != final_authority.publication.buffer_payload_hashes[1]
        or publication_payload_hash != final_authority.publication.payload_hash
    ):
        _fail(
            "hip_fgmres_model_case_parity_authority_changed",
            "/authority",
        )
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
        expected_loaded_runtime=source_loaded_runtime,
    )
    if (
        cpu_result.result_hash != cpu_witness.result_hash
        or observation_result.receipt != observation_receipt
        or device_identity_result.receipt != device_receipt
        or export_result.receipt != export_receipt
        or export_result.payload_hash != publication_payload_hash
    ):
        _fail(
            "hip_fgmres_model_case_parity_source_changed",
            "/source",
        )

    bindings = HipFgmresModelCaseParityBindingsV1(
        model_ir_content_hash=plan_witness.model_ir_content_hash,
        execution_plan_id=plan_witness.plan_id,
        execution_plan_hash=plan_witness.plan_hash,
        operator_hash=plan_witness.operator_hash,
        numeric_snapshot_hash=plan_witness.numeric_snapshot_hash,
        symbolic_reuse_hash=plan_witness.symbolic_reuse_hash,
        partition_hash=plan_witness.partition_hash,
        load_pattern_id=plan_witness.load_pattern_id,
        fgmres_plan_id=fgmres_plan_id,
        fgmres_plan_hash=fgmres_plan_hash,
        recurrence_plan_id=recurrence_plan_id,
        recurrence_plan_hash=recurrence_plan_hash,
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
    )
    dimensions = HipFgmresModelCaseParityDimensionsV1(
        global_dof_count=fgmres_global_dof_count,
        free_dof_count=fgmres_free_dof_count,
        reduced_csr_nnz=fgmres_reduced_csr_nnz,
        restart_dimension=policy_witness.restart_dimension,
        max_iterations=policy_witness.max_iterations,
        maximum_restart_count=recurrence_maximum_restart_count,
        populated_restart_row_count=len(populated),
    )
    case_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": bindings.execution_plan_hash,
            "policy_hash": bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
        }
    )
    draft = HipFgmresModelCaseParityReceiptV1(
        schema_version=HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
        status="case_parity_verified",
        evidence_scope=HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        case_id=case_id,
        bindings=bindings,
        dimensions=dimensions,
        tolerance=HipFgmresModelCaseParityToleranceV1(),
        discrete=_verified_discrete(),
        vectors=vectors,
        telemetry=HipFgmresModelCaseParityTelemetryV1(),
        claims=HipFgmresModelCaseParityClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_model_case_parity_receipt_v1(receipt), plan


def _validate_discrete_parity(
    cpu: CpuFgmresReferenceResultV1,
    outcome: Any,
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
        _fail("hip_fgmres_model_case_parity_discrete_mismatch", "/outcome")
    for index, (cpu_row, hip_row) in enumerate(
        zip(cpu.history, populated, strict=True)
    ):
        if not _restart_discrete_equal(cpu_row, hip_row):
            _fail(
                "hip_fgmres_model_case_parity_history_discrete_mismatch",
                f"/outcome/history/{index}",
            )


def _restart_discrete_equal(
    cpu: FgmresRestartRecord,
    hip: HipFgmresTerminalOutcomeRestartRowV1,
) -> bool:
    return (
        hip.restart_index == cpu.restart_index
        and hip.start_iteration == cpu.start_iteration
        and hip.end_iteration == cpu.end_iteration
        and hip.arnoldi_step_count == cpu.arnoldi_step_count
        and hip.reorthogonalization_count == cpu.reorthogonalization_count
        and hip.termination_hint == cpu.termination_hint
    )


def _validate_metric_parity(
    cpu: CpuFgmresReferenceResultV1,
    outcome: Any,
    populated: tuple[HipFgmresTerminalOutcomeRestartRowV1, ...],
) -> None:
    metrics = outcome.metrics
    if (
        outcome.record_metrics_authoritative is not True
        or metrics is None
        or outcome.true_residual_record_metrics_match is not True
        or not all(
            _scalar_close(cpu_value, hip_value)
            for cpu_value, hip_value in (
                (cpu.initial_residual_l2, metrics.initial_residual_l2),
                (cpu.solver_tolerance_l2, metrics.solver_tolerance_l2),
                (cpu.final_residual_l2, metrics.final_residual_l2),
                (cpu.final_residual_linf, metrics.final_residual_linf),
                (cpu.scaled_true_residual, metrics.final_scaled_residual),
            )
        )
    ):
        _fail(
            "hip_fgmres_model_case_parity_terminal_metric_mismatch", "/outcome/metrics"
        )
    for index, (cpu_row, hip_row) in enumerate(
        zip(cpu.history, populated, strict=True)
    ):
        if not all(
            _scalar_close(cpu_value, hip_value)
            for cpu_value, hip_value in (
                (cpu_row.estimated_residual_l2, hip_row.estimated_residual_l2),
                (cpu_row.true_residual_l2, hip_row.true_residual_l2),
                (cpu_row.true_residual_linf, hip_row.true_residual_linf),
                (cpu_row.scaled_true_residual, hip_row.scaled_true_residual),
                (cpu_row.solution_update_l2, hip_row.solution_update_l2),
            )
        ):
            _fail(
                "hip_fgmres_model_case_parity_history_metric_mismatch",
                f"/outcome/history/{index}",
            )


def _compare_vector(
    name: Literal["solution_x", "true_residual", "true_residual_replay"],
    reference: np.ndarray,
    candidate: np.ndarray,
) -> HipFgmresModelCaseParityVectorComparisonV1:
    if reference.shape != candidate.shape:
        _fail("hip_fgmres_model_case_parity_vector_shape_mismatch", f"/vectors/{name}")
    difference = np.abs(candidate - reference)
    tolerance = (
        HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        + HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 * np.abs(reference)
    )
    if not np.isfinite(difference).all() or np.any(difference > tolerance):
        _fail("hip_fgmres_model_case_parity_vector_mismatch", f"/vectors/{name}")
    maximum_absolute_error = float(np.max(difference, initial=0.0))
    l2_absolute_error = _stable_l2(difference)
    reference_l2 = _stable_l2(reference)
    if reference_l2 == 0.0:
        relative_l2_error = (
            0.0 if l2_absolute_error == 0.0 else float(np.finfo(float).max)
        )
    else:
        relative_l2_error = min(
            l2_absolute_error / reference_l2,
            float(np.finfo(float).max),
        )
    ratios = np.divide(
        difference,
        tolerance,
        out=np.zeros_like(difference),
        where=tolerance > 0.0,
    )
    maximum_tolerance_ratio = float(np.max(ratios, initial=0.0))
    return HipFgmresModelCaseParityVectorComparisonV1(
        name=name,
        element_count=reference.size,
        cpu_or_reference_sha256=_array_sha256(reference),
        hip_or_candidate_sha256=_array_sha256(candidate),
        maximum_absolute_error=maximum_absolute_error,
        l2_absolute_error=l2_absolute_error,
        reference_l2=reference_l2,
        relative_l2_error=relative_l2_error,
        maximum_tolerance_ratio=maximum_tolerance_ratio,
        relative_l2_tolerance_passed=(
            relative_l2_error <= HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1
        ),
        absolute_linf_tolerance_passed=(
            maximum_absolute_error <= HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        ),
        componentwise_tolerance_passed=True,
    )


def _replay_true_residual(plan: ExecutionPlanV2, solution: np.ndarray) -> np.ndarray:
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    residual = np.empty(free.size, dtype="<f8")
    try:
        for row in range(free.size):
            start = int(row_ptr[row])
            stop = int(row_ptr[row + 1])
            product = math.fsum(
                float(values[index]) * float(solution[int(columns[index])])
                for index in range(start, stop)
            )
            residual[row] = float(rhs[row]) - product
    except (IndexError, OverflowError, TypeError, ValueError) as exc:
        _fail(
            "hip_fgmres_model_case_parity_residual_replay_failed",
            "/vectors/true_residual_replay",
            type(exc).__name__,
        )
    if not np.isfinite(residual).all():
        _fail(
            "hip_fgmres_model_case_parity_residual_replay_nonfinite",
            "/vectors/true_residual_replay",
        )
    residual[residual == 0.0] = 0.0
    residual.setflags(write=False)
    return residual


def _exact_f64_vector(value: np.ndarray, expected_size: int) -> np.ndarray:
    if (
        type(value) is not np.ndarray
        or value.dtype.str != "<f8"
        or value.shape != (expected_size,)
        or not value.flags.c_contiguous
        or not np.isfinite(value).all()
        or np.any(np.signbit(value[value == 0.0]))
    ):
        _fail("hip_fgmres_model_case_parity_vector_invalid", "/vectors")
    return value


def _f64_vector_from_bytes(payload: bytes, expected_size: int) -> np.ndarray:
    if type(payload) is not bytes or len(payload) != 8 * expected_size:
        _fail("hip_fgmres_model_case_parity_payload_extent_invalid", "/vectors")
    value = np.frombuffer(payload, dtype="<f8")
    return _exact_f64_vector(value, expected_size)


def _detached_plan_lineage(
    execution_plan: ExecutionPlanV2,
    fgmres_plan: HipFgmresPlanV1,
    recurrence_plan: HipFgmresRecurrencePlanV2,
) -> tuple[ExecutionPlanV2, HipFgmresPlanV1, HipFgmresRecurrencePlanV2]:
    """Freeze one coherent, independently replayable plan lineage."""

    execution_witness = _snapshot_execution_plan(execution_plan)
    fgmres_witness = _validated_source_snapshot(fgmres_plan)
    if (
        fgmres_witness._source_execution_plan.plan_hash != execution_witness.plan_hash
        or fgmres_witness._source_execution_plan.plan_id != execution_witness.plan_id
    ):
        _fail(
            "hip_fgmres_model_case_parity_plan_lineage_mismatch",
            "/authority/model_source/execution_plan",
        )
    fgmres_witness = replace(
        fgmres_witness,
        _source_execution_plan=execution_witness,
    )
    validate_hip_fgmres_plan_v1(
        fgmres_witness,
        expected_execution_plan=execution_witness,
        expected_free_space_plan=fgmres_witness._source_free_space_plan,
    )
    recurrence_witness = compile_hip_fgmres_recurrence_plan_v2(fgmres_witness)
    validate_hip_fgmres_recurrence_plan_v2(
        recurrence_plan,
        expected_source_plan=fgmres_plan,
    )
    if recurrence_witness.to_dict() != recurrence_plan.to_dict():
        _fail(
            "hip_fgmres_model_case_parity_plan_lineage_mismatch",
            "/authority/model_source/recurrence_plan",
        )
    validate_hip_fgmres_recurrence_plan_v2(
        recurrence_witness,
        expected_source_plan=fgmres_witness,
    )
    return execution_witness, fgmres_witness, recurrence_witness


def _detached_cpu_result(
    source: CpuFgmresReferenceResultV1,
    policy: Any,
) -> CpuFgmresReferenceResultV1:
    solution = _f64_vector_from_bytes(
        bytes(source.reduced_solution.tobytes(order="C")),
        source.reduced_solution.size,
    )
    residual = _f64_vector_from_bytes(
        bytes(source.true_residual.tobytes(order="C")),
        source.true_residual.size,
    )
    return replace(
        source,
        policy=policy,
        history=tuple(replace(row) for row in source.history),
        descriptors=tuple(replace(row) for row in source.descriptors),
        reduced_solution=solution,
        true_residual=residual,
    )


def _model_source_value_witness(source: Any) -> _ModelSourceValueWitnessV1:
    runtime = source.runtime
    loaded_runtime = source.loaded_runtime
    stream = source.stream
    stream_pointer = source.stream_pointer
    device_ordinal = source.device_ordinal
    architecture = source.architecture
    fgmres = source.source_fgmres_plan
    recurrence = source.source_recurrence_plan
    execution = source.source_execution_plan
    policy = fgmres.policy
    fgmres_plan_id = fgmres.plan_id
    fgmres_plan_hash = fgmres.plan_hash
    global_dof_count = fgmres.global_dof_count
    free_dof_count = fgmres.free_dof_count
    reduced_csr_nnz = fgmres.reduced_csr_nnz
    recurrence_plan_id = recurrence.plan_id
    recurrence_plan_hash = recurrence.plan_hash
    maximum_restart_count = recurrence.maximum_restart_count
    execution_plan_id = execution.plan_id
    execution_plan_hash = execution.plan_hash
    policy_hash = policy.policy_hash
    value_snapshot = (
        type(source),
        id(runtime),
        id(loaded_runtime),
        id(stream),
        (type(stream_pointer), stream_pointer),
        (type(device_ordinal), device_ordinal),
        (type(architecture), architecture),
        id(fgmres),
        fgmres_plan_id,
        fgmres_plan_hash,
        fgmres.source_execution_plan_hash,
        id(recurrence),
        recurrence_plan_id,
        recurrence_plan_hash,
        recurrence.source_fgmres_plan_hash,
        recurrence.source_execution_plan_hash,
        id(execution),
        execution_plan_id,
        execution_plan_hash,
        execution.model_ir_content_hash,
        execution.operator_hash,
        execution.numeric_snapshot_hash,
        execution.symbolic_reuse_hash,
        execution.partition_hash,
        execution.load_pattern_id,
        policy_hash,
        (type(policy.restart_dimension), policy.restart_dimension),
        (type(policy.max_iterations), policy.max_iterations),
        (type(policy.absolute_tolerance), float.hex(policy.absolute_tolerance)),
        (type(policy.relative_tolerance), float.hex(policy.relative_tolerance)),
        (
            type(policy.stagnation_checkpoint_limit),
            policy.stagnation_checkpoint_limit,
        ),
        (
            type(policy.stagnation_relative_tolerance),
            float.hex(policy.stagnation_relative_tolerance),
        ),
        (type(policy.divergence_factor), float.hex(policy.divergence_factor)),
        (type(global_dof_count), global_dof_count),
        (type(free_dof_count), free_dof_count),
        (type(reduced_csr_nnz), reduced_csr_nnz),
        (
            type(maximum_restart_count),
            maximum_restart_count,
        ),
    )
    return _ModelSourceValueWitnessV1(
        loaded_runtime=loaded_runtime,
        loaded_runtime_identity=id(loaded_runtime),
        architecture=architecture,
        device_ordinal=device_ordinal,
        source_fgmres_plan=fgmres,
        source_fgmres_plan_identity=id(fgmres),
        fgmres_plan_id=fgmres_plan_id,
        fgmres_plan_hash=fgmres_plan_hash,
        global_dof_count=global_dof_count,
        free_dof_count=free_dof_count,
        reduced_csr_nnz=reduced_csr_nnz,
        source_recurrence_plan=recurrence,
        source_recurrence_plan_identity=id(recurrence),
        recurrence_plan_id=recurrence_plan_id,
        recurrence_plan_hash=recurrence_plan_hash,
        maximum_restart_count=maximum_restart_count,
        source_execution_plan=execution,
        source_execution_plan_identity=id(execution),
        execution_plan_id=execution_plan_id,
        execution_plan_hash=execution_plan_hash,
        policy_hash=policy_hash,
        value_snapshot=value_snapshot,
    )


def _seal_result_ir_downstream_authority(
    result: HipFgmresModelCaseParityResultV1,
) -> _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1:
    """Mint a non-serializable seal after the public result replay succeeds."""

    observation = result._observation_result
    export_result = observation._source_export_result
    export_context = observation._source_export_context
    if (
        type(export_result) is not HipFgmresCompletionExportResultV1
        or type(export_context) is not HipFgmresCompletionExportExecutionContextV1
    ):
        _fail(
            "hip_fgmres_model_case_parity_result_ir_source_invalid",
            "/result_ir_downstream_authority/source",
        )
    try:
        publication = export_context._model_case_parity_authority(export_result)
    except Exception as exc:
        _fail(
            "hip_fgmres_model_case_parity_result_ir_live_authority_invalid",
            "/result_ir_downstream_authority/publication",
            type(exc).__name__,
        )
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
            "hip_fgmres_model_case_parity_result_ir_live_authority_changed",
            "/result_ir_downstream_authority/publication",
        )
    snapshot = _result_ir_downstream_value_snapshot(
        receipt=result.receipt,
        source_execution_plan=result._source_execution_plan,
        cpu_result=result._cpu_result,
        observation_result=observation,
        device_identity_result=result._device_identity_result,
        export_result=export_result,
        export_context=export_context,
        publication=publication,
    )
    return _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1(
        receipt=result.receipt,
        source_execution_plan=result._source_execution_plan,
        cpu_result=result._cpu_result,
        observation_result=observation,
        device_identity_result=result._device_identity_result,
        export_result=export_result,
        export_context=export_context,
        publication=publication,
        snapshot=snapshot,
    )


def _result_ir_downstream_value_snapshot(
    *,
    receipt: HipFgmresModelCaseParityReceiptV1,
    source_execution_plan: ExecutionPlanV2,
    cpu_result: CpuFgmresReferenceResultV1,
    observation_result: HipFgmresTerminalOutcomeObservationResultV1,
    device_identity_result: HipDeviceIdentityResultV1,
    export_result: HipFgmresCompletionExportResultV1,
    export_context: HipFgmresCompletionExportExecutionContextV1,
    publication: _CompletionExportModelCaseParityAuthorityV1,
) -> tuple[Any, ...]:
    """Capture immutable values while retaining identities only in the seal."""

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
    published = publication.publication
    source_witness = _model_source_value_witness(publication.source)
    device_private = (
        id(device_identity_result._loaded_runtime),
        id(device_identity_result._loader_witness),
        id(device_identity_result._runtime_library_identity),
        _private_snapshot_token(device_identity_result._runtime_library_snapshot),
        id(device_identity_result._runtime_query_authority),
        _private_snapshot_token(device_identity_result._runtime_private_snapshot),
        _private_snapshot_token(device_identity_result._publication_authority_snapshot),
    )
    published_policy = tuple(
        (name, _private_snapshot_token(getattr(published.policy, name)))
        for name in published.policy.__dataclass_fields__
    )
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
        device_private,
        type(export_result),
        canonical_hash(export_result.receipt.to_dict()),
        export_result.payload_hash,
        (len(export_result.solution_x), _bytes_sha256(export_result.solution_x)),
        (len(export_result.true_residual), _bytes_sha256(export_result.true_residual)),
        (len(export_result.solve_record), _bytes_sha256(export_result.solve_record)),
        type(export_context),
        type(publication),
        _private_snapshot_token(publication.source_snapshot),
        _private_snapshot_token(source_witness.value_snapshot),
        type(published),
        published.receipt_hash,
        published.payload_hash,
        published.buffer_payload_hashes,
        (len(published.solution_x), _bytes_sha256(published.solution_x)),
        (len(published.true_residual), _bytes_sha256(published.true_residual)),
        (len(published.solve_record), _bytes_sha256(published.solve_record)),
        published_policy,
    )


def _private_snapshot_token(value: Any) -> tuple[Any, ...]:
    """Normalize private snapshot tuples without invoking arbitrary equality."""

    if value is None or type(value) in {bool, int, str, bytes}:
        return (type(value), value)
    if type(value) is float:
        return (float, float.hex(value))
    if type(value) is tuple:
        return (tuple, tuple(_private_snapshot_token(item) for item in value))
    if type(value) is type:
        return (type, value.__module__, value.__qualname__)
    return (type(value), id(value))


def _bytes_sha256(payload: bytes) -> str:
    if type(payload) is not bytes:
        _fail("hip_fgmres_model_case_parity_payload_type_invalid", "/payload")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_fixed_policy(policy: Any) -> None:
    if policy.max_iterations <= 0:
        _fail(
            "hip_fgmres_model_case_parity_zero_iteration_unavailable",
            "/policy/max_iterations",
        )
    for name in ("absolute_tolerance", "relative_tolerance"):
        value = getattr(policy, name)
        if value == 0.0 and math.copysign(1.0, value) < 0.0:
            _fail(
                "hip_fgmres_model_case_parity_negative_zero_policy", f"/policy/{name}"
            )


def _scalar_close(reference: float, candidate: float) -> bool:
    return (
        type(reference) is float
        and type(candidate) is float
        and math.isfinite(reference)
        and math.isfinite(candidate)
        and abs(candidate - reference)
        <= HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        + HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 * abs(reference)
    )


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


def _array_sha256(array: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _verified_discrete() -> HipFgmresModelCaseParityDiscreteComparisonV1:
    return HipFgmresModelCaseParityDiscreteComparisonV1(
        terminal_status_match=True,
        termination_code_match=True,
        iteration_count_match=True,
        restart_count_match=True,
        operator_apply_count_match=True,
        preconditioner_apply_count_match=True,
        restart_history_shape_match=True,
        restart_history_discrete_fields_match=True,
        restart_history_metrics_within_tolerance=True,
        terminal_metrics_within_tolerance=True,
        numerical_failure_absent=True,
    )


def _validate_exact_nested_scalar_types(
    receipt: HipFgmresModelCaseParityReceiptV1,
) -> None:
    binding_bool_fields = (
        "retained_execution_plan_snapshot_identity_verified",
        "process_local_runtime_identity_verified",
        "process_local_identities_serialized",
    )
    if any(
        type(getattr(receipt.bindings, name)) is not bool
        for name in binding_bool_fields
    ):
        _fail("hip_fgmres_model_case_parity_binding_type_invalid", "/bindings")
    if (
        type(receipt.tolerance.relative_tolerance) is not float
        or type(receipt.tolerance.absolute_tolerance) is not float
        or type(receipt.tolerance.comparison_rule) is not str
        or type(receipt.tolerance.caller_relaxation_allowed) is not bool
    ):
        _fail("hip_fgmres_model_case_parity_tolerance_type_invalid", "/tolerance")
    if any(
        type(getattr(receipt.discrete, name)) is not bool
        for name in receipt.discrete.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_case_parity_discrete_type_invalid", "/discrete")
    if any(
        type(getattr(receipt.telemetry, name)) is not int
        for name in receipt.telemetry.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_case_parity_telemetry_type_invalid", "/telemetry")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_case_parity_claim_type_invalid", "/claims")


def _validate_bindings(bindings: HipFgmresModelCaseParityBindingsV1) -> None:
    if type(bindings.device_ordinal) is not int or bindings.device_ordinal < 0:
        _fail(
            "hip_fgmres_model_case_parity_binding_invalid", "/bindings/device_ordinal"
        )
    hash_fields = (
        "model_ir_content_hash",
        "execution_plan_hash",
        "operator_hash",
        "numeric_snapshot_hash",
        "symbolic_reuse_hash",
        "partition_hash",
        "fgmres_plan_hash",
        "recurrence_plan_hash",
        "policy_hash",
        "terminal_observation_id",
        "terminal_observation_receipt_hash",
        "terminal_outcome_hash",
        "completion_export_context_id",
        "completion_export_receipt_hash",
        "completion_export_payload_hash",
        "global_context_id",
        "global_receipt_hash",
        "kernel_identity_hash",
        "kernel_source_sha256",
        "device_identity_receipt_hash",
        "runtime_library_sha256",
        "cpu_result_hash",
    )
    if any(_HASH_RE.fullmatch(getattr(bindings, name)) is None for name in hash_fields):
        _fail("hip_fgmres_model_case_parity_binding_hash_invalid", "/bindings")
    if (
        _EXECUTION_PLAN_ID_RE.fullmatch(bindings.execution_plan_id) is None
        or _FGMRES_PLAN_ID_RE.fullmatch(bindings.fgmres_plan_id) is None
        or _RECURRENCE_PLAN_ID_RE.fullmatch(bindings.recurrence_plan_id) is None
    ):
        _fail("hip_fgmres_model_case_parity_binding_id_invalid", "/bindings")


def _validate_dimensions(dimensions: HipFgmresModelCaseParityDimensionsV1) -> None:
    if any(
        type(getattr(dimensions, name)) is not int
        for name in dimensions.__dataclass_fields__
    ):
        _fail("hip_fgmres_model_case_parity_dimension_type_invalid", "/dimensions")
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
        or not 0
        <= dimensions.populated_restart_row_count
        <= dimensions.maximum_restart_count
    ):
        _fail("hip_fgmres_model_case_parity_dimension_invalid", "/dimensions")


def _validate_vector_comparison(
    row: HipFgmresModelCaseParityVectorComparisonV1,
    path: str,
) -> None:
    if (
        row.name not in _VECTOR_NAMES
        or type(row.element_count) is not int
        or row.element_count <= 0
        or _HASH_RE.fullmatch(row.cpu_or_reference_sha256) is None
        or _HASH_RE.fullmatch(row.hip_or_candidate_sha256) is None
    ):
        _fail("hip_fgmres_model_case_parity_vector_receipt_invalid", path)
    metrics = (
        row.maximum_absolute_error,
        row.l2_absolute_error,
        row.reference_l2,
        row.relative_l2_error,
        row.maximum_tolerance_ratio,
    )
    if any(
        type(value) is not float
        or not math.isfinite(value)
        or value < 0.0
        or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        for value in metrics
    ):
        _fail("hip_fgmres_model_case_parity_vector_metric_invalid", path)
    if (
        type(row.relative_l2_tolerance_passed) is not bool
        or type(row.absolute_linf_tolerance_passed) is not bool
        or row.componentwise_tolerance_passed is not True
        or row.maximum_tolerance_ratio > 1.0
        or not (row.relative_l2_tolerance_passed or row.absolute_linf_tolerance_passed)
    ):
        _fail("hip_fgmres_model_case_parity_vector_gate_invalid", path)


def _receipt_payload(
    receipt: HipFgmresModelCaseParityReceiptV1,
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
        "tolerance": receipt.tolerance.to_dict(),
        "discrete": receipt.discrete.to_dict(),
        "vectors": [row.to_dict() for row in receipt.vectors],
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
    raise HipFgmresModelCaseParityV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1",
    "HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1",
    "HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1",
    "HipFgmresModelCaseParityBindingsV1",
    "HipFgmresModelCaseParityClaimsV1",
    "HipFgmresModelCaseParityDimensionsV1",
    "HipFgmresModelCaseParityDiscreteComparisonV1",
    "HipFgmresModelCaseParityReceiptV1",
    "HipFgmresModelCaseParityResultV1",
    "HipFgmresModelCaseParityTelemetryV1",
    "HipFgmresModelCaseParityToleranceV1",
    "HipFgmresModelCaseParityV1Error",
    "HipFgmresModelCaseParityVectorComparisonV1",
    "attest_hip_fgmres_model_case_parity_v1",
    "replay_hip_fgmres_detached_model_case_numerics_v1",
    "validate_hip_fgmres_model_case_parity_receipt_v1",
    "validate_hip_fgmres_model_case_parity_result_v1",
]
