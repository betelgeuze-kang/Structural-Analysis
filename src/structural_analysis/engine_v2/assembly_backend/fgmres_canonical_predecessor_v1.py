"""Live first-column FGMRES producer with a device-only validation seal.

This non-promoting walking slice consumes one ready live checkpoint resource
context.  It zero-initializes the exact owned eight allocations with the
sealed runtime, submits the fixed initial-to-column-zero prefix, submits the
non-advancing device validator, observes one exact-runtime fence, and mints a
process-local conditional predecessor capability.  It never copies the mask
or validation verdict to the host.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointExecutionContextV1,
    validate_hip_fgmres_live_checkpoint_context_receipt_v1,
)
from .fgmres_recurrence_plan_v2 import (
    _VECTOR_MODE_CODES,
    hip_fgmres_first_column_predecessor_validation_schedule_payload_v2,
)
from .fgmres_rtc_v2 import (
    FgmresV2CanonicalPredecessorLaunch,
    HipRtcFgmresV2Kernel,
    canonical_first_column_predecessor_launches_v2,
    reduction_stage_output_counts_v2,
    _runtime_pointer,
)
from .fgmres_rtc_launch_fence_ledger_v1 import (
    _launch_descriptor_hash_v1,
    _memset_descriptor_hash_v1,
)


HIP_FGMRES_CANONICAL_PREDECESSOR_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-canonical-predecessor.v1"
)
HIP_FGMRES_CANONICAL_PREDECESSOR_CAPABILITY_PROFILE_V1 = (
    "phase0_live_first_column_device_sealed_predecessor"
)
HIP_FGMRES_CANONICAL_PREDECESSOR_EVIDENCE_SCOPE_V1 = (
    "device_sealed_predecessor_outcome_unobserved_non_promoting"
)

CanonicalPredecessorStatusV1 = Literal[
    "context_ready",
    "predecessor_pending",
    "fence_observed_ack_pending",
    "predecessor_fenced",
    "poisoned_no_work",
    "poisoned_pending_fence",
    "poisoned_fence_observed_ack_pending",
    "poisoned_fenced",
    "context_closed",
    "cleanup_failed",
]

_DIRECT_ROLES = (
    "reduced_state",
    "reduced_load",
    "jacobi_inverse",
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_OWNED_ROLES = _DIRECT_ROLES[3:]
_DELEGATED_OPERATOR_ROLES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
)
_DELEGATED_WORKSPACE_ROLES = ("reduction_ping", "reduction_pong")
_MASK_DOMAIN = (0, 1792, 7936)
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HEX_ADDRESS_RE = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_DECIMAL_HANDLE_RE = re.compile(
    r"(?i)\b(?:pointer|ptr|handle|stream|module|function|device_address)"
    r"\s*[=:]\s*\d+\b"
)
_SCHEMA_RESOURCE = "hip_fgmres_canonical_predecessor_v1.schema.json"


class HipFgmresCanonicalPredecessorV1Error(RuntimeError):
    """Stable producer error retaining retryable fence/cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        pending: HipFgmresCanonicalPredecessorPendingV1 | None = None,
        cleanup_owner: HipFgmresCanonicalPredecessorExecutionContextV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.pending = pending
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


class _ImmutableCapability:
    __slots__ = ("__weakref__",)

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")


class HipFgmresCanonicalPredecessorPendingV1(_ImmutableCapability):
    """Nonconstructible single-context fence authority."""

    __slots__ = (
        "context_id",
        "attempted_operation_count",
        "accepted_operation_lower_bound",
        "accepted_operation_upper_bound",
        "_issuer",
        "_nonce",
        "_snapshot",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("Pending predecessor capabilities are context-issued only.")


class HipFgmresCanonicalPredecessorCapabilityV1(_ImmutableCapability):
    """Device-conditional, nonserializable predecessor capability."""

    __slots__ = (
        "context_id",
        "receipt_hash",
        "mask_domain",
        "_issuer",
        "_nonce",
        "_snapshot",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("Canonical predecessor capabilities are context-issued only.")


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorBindingsV1:
    live_context_id: str
    live_opening_receipt_hash: str
    primitive_context_id: str
    primitive_opening_receipt_hash: str
    primitive_evidence_scope: str
    primitive_actual_backend: Literal["hip", "test_double"]
    source_apply_receipt_hash: str
    source_state_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    kernel_origin: Literal["internally_compiled", "caller_supplied"]
    runtime_library_discovery_source: str
    hiprtc_library_discovery_source: str
    canonical_schedule_hash: str
    validator_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    primitive_parent_lease_epoch: int
    solver_child_lease_epoch: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorDimensionsV1:
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    reduction_stage_count: int
    persistent_capability_count: Literal[11] = 11
    delegated_operator_capability_count: Literal[3] = 3
    delegated_workspace_capability_count: Literal[2] = 2
    physical_capability_count: Literal[16] = 16

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorProjectionV1:
    persistent_roles: tuple[str, ...]
    delegated_operator_roles: tuple[str, ...]
    delegated_workspace_roles: tuple[str, ...]
    runtime_device_bound: bool
    same_stream_bound: bool
    pointer_values_serialized: Literal[False] = False
    additional_allocation_count: Literal[0] = 0
    additional_device_bytes: Literal[0] = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "persistent_roles": list(self.persistent_roles),
            "delegated_operator_roles": list(self.delegated_operator_roles),
            "delegated_workspace_roles": list(self.delegated_workspace_roles),
            "runtime_device_bound": self.runtime_device_bound,
            "same_stream_bound": self.same_stream_bound,
            "pointer_values_serialized": False,
            "additional_allocation_count": 0,
            "additional_device_bytes": 0,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorTelemetryV1:
    memset_attempt_count: int = 0
    memset_accept_lower_bound: int = 0
    memset_accept_upper_bound: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_accept_lower_bound: int = 0
    kernel_launch_accept_upper_bound: int = 0
    async_operation_attempt_count: int = 0
    async_operation_accept_lower_bound: int = 0
    async_operation_accept_upper_bound: int = 0
    fence_attempt_count: int = 0
    fence_success_count: int = 0
    pending_consume_attempt_count: int = 0
    consumed_operation_count: int = 0
    h2d_operation_count: Literal[0] = 0
    d2h_operation_count: Literal[0] = 0
    intermediate_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorClaimsV1:
    source_apply_completion_bound: bool
    positive_jacobi_completion_bound: bool
    persistent_parent3_owned8_bound: bool
    delegated_operator_workspace_bound: bool
    same_runtime_device_stream_bound: bool
    owned_content_initialized: bool
    canonical_producer_prefix_fenced: bool
    device_mask_domain_gate_bound: bool
    device_validation_outcome_host_observed: Literal[False] = False
    actual_mask_host_observed: Literal[False] = False
    authoritative_predecessor_proven: Literal[False] = False
    checkpoint_transaction_ready: Literal[False] = False
    invalid_source_destination_atomicity_proven: Literal[False] = False
    live_solver_ready: Literal[False] = False
    solution_ready: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    asymptotic_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorReceiptV1:
    status: CanonicalPredecessorStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresCanonicalPredecessorReasonV1 | None
    bindings: HipFgmresCanonicalPredecessorBindingsV1
    dimensions: HipFgmresCanonicalPredecessorDimensionsV1
    projection: HipFgmresCanonicalPredecessorProjectionV1
    admitted_mask_domain: tuple[int, int, int]
    telemetry: HipFgmresCanonicalPredecessorTelemetryV1
    claims: HipFgmresCanonicalPredecessorClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_CANONICAL_PREDECESSOR_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_canonical_predecessor_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresCanonicalPredecessorOpenResultV1:
    context: HipFgmresCanonicalPredecessorExecutionContextV1
    receipt: HipFgmresCanonicalPredecessorReceiptV1

    @property
    def ready(self) -> bool:
        return self.receipt.status == "context_ready" and not self.context.closed


_CONTEXT_MINT = object()


class HipFgmresCanonicalPredecessorExecutionContextV1:
    """Single-use child that owns prefix enqueue, fence, and acknowledgement."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Canonical predecessor contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._live: HipFgmresLiveCheckpointExecutionContextV1 | None = None
        self._token = object()
        self._projection: Any | None = None
        self._pointers: dict[str, int] = {}
        self._owned_byte_lengths: dict[str, int] = {}
        self._schedule: tuple[FgmresV2CanonicalPredecessorLaunch, ...] = ()
        self._bindings: HipFgmresCanonicalPredecessorBindingsV1 | None = None
        self._dimensions: HipFgmresCanonicalPredecessorDimensionsV1 | None = None
        self._context_id = _ZERO_HASH
        self._telemetry = HipFgmresCanonicalPredecessorTelemetryV1()
        self._state: CanonicalPredecessorStatusV1 = "context_ready"
        self._reason: HipFgmresCanonicalPredecessorReasonV1 | None = None
        self._pending: HipFgmresCanonicalPredecessorPendingV1 | None = None
        self._capability: HipFgmresCanonicalPredecessorCapabilityV1 | None = None
        self._pending_nonce = object()
        self._capability_nonce = object()
        self._consume_started = False
        self._sealed_checkpoint_transaction_child_token: object | None = None
        self._sealed_checkpoint_transaction_child_terminal = False
        self._capability_consumed = False
        self._child_released = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def capability(self) -> HipFgmresCanonicalPredecessorCapabilityV1 | None:
        return self._capability

    def receipt(self) -> HipFgmresCanonicalPredecessorReceiptV1:
        with self._lock:
            return self._build_receipt(self._state)

    def enqueue_canonical_predecessor(
        self,
    ) -> HipFgmresCanonicalPredecessorPendingV1:
        with self._lock:
            if self._state != "context_ready" or self._pending is not None:
                _fail(
                    "hip_fgmres_canonical_predecessor_state_invalid",
                    "/enqueue",
                    cleanup_owner=self,
                )
            self._validate_authority(require_idle_kernel=True)
            self._state = "predecessor_pending"
            try:
                for role in _OWNED_ROLES:
                    self._attempt(
                        "memset",
                        lambda role=role: self._memset_owned(role),
                    )
                scratch_stage: dict[str, int] = {}
                for row in self._schedule:
                    self._attempt(
                        "kernel",
                        lambda row=row: self._dispatch(row, scratch_stage),
                    )
                    if (
                        row.submission_kind == "vector"
                        and row.mode == _VECTOR_MODE_CODES["APPLY_JACOBI_INDEXED"]
                    ):
                        self._require_live()._enqueue_fixed_rank_coarse_overlay_after_jacobi(
                            phase="canonical_prefix",
                            owner=self,
                            expected_restart=row.expected_restart,
                            expected_column=row.expected_column,
                            logical_index=row.logical_index,
                        )
            except BaseException as exc:
                self._poison_after_enqueue_failure(exc)
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresCanonicalPredecessorV1Error(
                    "hip_fgmres_canonical_predecessor_enqueue_failed",
                    "/enqueue",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            expected = 8 + len(self._schedule)
            if (
                self._telemetry.async_operation_attempt_count != expected
                or self._telemetry.async_operation_accept_lower_bound != expected
                or self._telemetry.async_operation_accept_upper_bound != expected
                or self._kernel()._checkpoint_pending_stream_count(
                    self._live_checkpoint_token()
                )
                != 1
            ):
                self._poison_after_enqueue_failure(
                    RuntimeError("canonical operation accounting mismatch")
                )
                _fail(
                    "hip_fgmres_canonical_predecessor_pending_invalid",
                    "/enqueue/pending",
                    cleanup_owner=self,
                )
            self._pending = self._mint_pending()
            return self._pending

    def synchronize_canonical_predecessor(
        self,
        pending: HipFgmresCanonicalPredecessorPendingV1,
    ) -> HipFgmresCanonicalPredecessorCapabilityV1:
        with self._lock:
            self._validate_pending(pending)
            if self._state == "predecessor_fenced" and self._capability is not None:
                return self._capability
            if self._state not in {
                "predecessor_pending",
                "poisoned_pending_fence",
                "fence_observed_ack_pending",
                "poisoned_fence_observed_ack_pending",
            }:
                _fail(
                    "hip_fgmres_canonical_predecessor_state_invalid",
                    "/fence",
                    cleanup_owner=self,
                )
            self._observe_fence_and_consume()
            if self._state == "poisoned_fenced":
                _fail(
                    "hip_fgmres_canonical_predecessor_poisoned",
                    "/fence",
                    cleanup_owner=self,
                )
            self._state = "predecessor_fenced"
            receipt = self._build_receipt(self._state)
            self._capability = _issue_capability(
                HipFgmresCanonicalPredecessorCapabilityV1,
                {
                    "context_id": self._context_id,
                    "receipt_hash": receipt.receipt_hash,
                    "mask_domain": _MASK_DOMAIN,
                    "_issuer": self,
                    "_nonce": self._capability_nonce,
                },
            )
            object.__setattr__(
                self._capability,
                "_snapshot",
                _capability_snapshot(self._capability),
            )
            return self._capability

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._sealed_checkpoint_transaction_child_token is not None:
                _fail(
                    "hip_fgmres_canonical_predecessor_sealed_child_active",
                    "/lifetime/sealed_checkpoint_transaction_child",
                    cleanup_owner=self,
                )
            try:
                if self._state in {
                    "predecessor_pending",
                    "poisoned_pending_fence",
                    "fence_observed_ack_pending",
                    "poisoned_fence_observed_ack_pending",
                }:
                    self._observe_fence_and_consume()
                self._release_child()
            except Exception as exc:
                self._state = "cleanup_failed"
                self._reason = HipFgmresCanonicalPredecessorReasonV1(
                    "hip_fgmres_canonical_predecessor_cleanup_failed",
                    _detail(exc),
                )
                raise HipFgmresCanonicalPredecessorV1Error(
                    self._reason.code,
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"

    def _attempt(self, kind: Literal["memset", "kernel"], operation: Any) -> None:
        before = self._telemetry
        self._telemetry = replace(
            before,
            async_operation_attempt_count=before.async_operation_attempt_count + 1,
            memset_attempt_count=before.memset_attempt_count + (kind == "memset"),
            kernel_launch_attempt_count=(
                before.kernel_launch_attempt_count + (kind == "kernel")
            ),
        )
        try:
            operation()
        except BaseException as exc:
            disposition = getattr(exc, "launch_disposition", None)
            if disposition == "ambiguous" or disposition not in {
                "rejected",
                "not_attempted",
            }:
                self._increment_accept(kind, lower=0, upper=1)
            raise
        self._increment_accept(kind, lower=1, upper=1)

    def _increment_accept(self, kind: str, *, lower: int, upper: int) -> None:
        row = self._telemetry
        self._telemetry = replace(
            row,
            async_operation_accept_lower_bound=(
                row.async_operation_accept_lower_bound + lower
            ),
            async_operation_accept_upper_bound=(
                row.async_operation_accept_upper_bound + upper
            ),
            memset_accept_lower_bound=(
                row.memset_accept_lower_bound + (lower if kind == "memset" else 0)
            ),
            memset_accept_upper_bound=(
                row.memset_accept_upper_bound + (upper if kind == "memset" else 0)
            ),
            kernel_launch_accept_lower_bound=(
                row.kernel_launch_accept_lower_bound
                + (lower if kind == "kernel" else 0)
            ),
            kernel_launch_accept_upper_bound=(
                row.kernel_launch_accept_upper_bound
                + (upper if kind == "kernel" else 0)
            ),
        )

    def _memset_owned(self, role: str) -> None:
        self._kernel()._checkpoint_memset_zero(
            self._live_checkpoint_token(),
            self._stream(),
            self._pointers[role],
            self._owned_byte_lengths[role],
            _checkpoint_audit_descriptor_hash=_memset_descriptor_hash_v1(
                role,
                self._owned_byte_lengths[role],
            ),
        )

    def _dispatch(
        self,
        row: FgmresV2CanonicalPredecessorLaunch,
        scratch_stage: dict[str, int],
    ) -> None:
        live = self._require_live()
        plan = live._source_plan
        if plan is None:
            _fail("hip_fgmres_canonical_predecessor_plan_missing", "/enqueue")
        policy = plan.policy
        kernel = self._kernel()
        token = self._live_checkpoint_token()
        stream = self._stream()
        audit_descriptor_hash = _launch_descriptor_hash_v1(row)
        common_control = (
            live._recurrence_plan.free_dof_count,  # type: ignore[union-attr]
            live._recurrence_plan.restart_dimension,  # type: ignore[union-attr]
            live._recurrence_plan.max_iterations,  # type: ignore[union-attr]
            live._recurrence_plan.maximum_restart_count,  # type: ignore[union-attr]
            policy.stagnation_checkpoint_limit,
            policy.absolute_tolerance,
            policy.relative_tolerance,
            plan.source_residual_tolerance,
            policy.stagnation_relative_tolerance,
            policy.divergence_factor,
        )
        if row.submission_kind == "control":
            kernel.launch_control(
                stream,
                row.mode,
                row.expected_schedule_epoch,
                row.expected_restart,
                row.expected_column,
                row.row_index,
                row.pass_index,
                *common_control,
                self._pointers["packed_dense_state"],
                self._pointers["fgmres_control_state_v2"],
                self._pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
            )
            return
        n = live._recurrence_plan.free_dof_count  # type: ignore[union-attr]
        if row.submission_kind == "vector":
            kernel.launch_vector(
                stream,
                row.mode,
                row.vector_gate,
                row.expected_schedule_epoch,
                row.expected_restart,
                row.expected_column,
                n,
                row.logical_index,
                self._pointers["reduced_state"],
                self._pointers["reduced_load"],
                self._pointers["jacobi_inverse"],
                self._pointers["solution_x"],
                self._pointers["true_residual"],
                self._pointers["work_w"],
                self._pointers["basis_v"],
                self._pointers["preconditioned_basis_z"],
                self._pointers["packed_dense_state"],
                self._pointers["fgmres_control_state_v2"],
                self._pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
            )
            return
        if row.submission_kind == "spmv":
            kernel.launch_csr_spmv_indexed(
                stream,
                row.mode,
                row.expected_schedule_epoch,
                row.expected_restart,
                row.expected_column,
                n,
                live._recurrence_plan.reduced_csr_nnz,  # type: ignore[union-attr]
                row.logical_index,
                self._pointers["reduced_csr_row_ptr"],
                self._pointers["reduced_csr_column_indices"],
                self._pointers["reduced_csr_values"],
                self._pointers["solution_x"],
                self._pointers["work_w"],
                self._pointers["basis_v"],
                self._pointers["preconditioned_basis_z"],
                self._pointers["fgmres_control_state_v2"],
                self._pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
            )
            return
        if row.submission_kind != "reduction":
            _fail(
                "hip_fgmres_canonical_predecessor_schedule_invalid",
                "/enqueue/schedule",
            )
        tree_id = row.reduction_tree_id
        if type(tree_id) is not str or not tree_id:
            _fail(
                "hip_fgmres_canonical_predecessor_schedule_invalid",
                "/enqueue/schedule/reduction_tree_id",
            )
        stage = scratch_stage.get(tree_id, 0)
        reduction_input = self._pointers[
            "reduction_ping" if stage % 2 == 0 else "reduction_pong"
        ]
        reduction_output = self._pointers[
            "reduction_pong" if stage % 2 == 0 else "reduction_ping"
        ]
        kernel.launch_reduction(
            stream,
            row.mode,
            row.reduction_target,
            row.expected_schedule_epoch,
            row.expected_restart,
            row.expected_column,
            row.expected_reduction_epoch,
            row.value_count,
            row.logical_index,
            self._pointers["reduced_load"],
            self._pointers["solution_x"],
            self._pointers["true_residual"],
            self._pointers["work_w"],
            self._pointers["basis_v"],
            reduction_input,
            reduction_output,
            self._pointers["fgmres_control_state_v2"],
            self._pointers["solve_record"],
            _checkpoint_owner_token=token,
            _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
        )
        scratch_stage[tree_id] = stage + 1

    def _poison_after_enqueue_failure(self, error: BaseException) -> None:
        kernel = self._kernel()
        token = self._live_checkpoint_token()
        try:
            kernel._poison_checkpoint_transaction_owner(token)
        except BaseException:
            pass
        try:
            pending = kernel._checkpoint_pending_stream_count(token) != 0
        except BaseException:
            # Failure to prove the exact leased stream empty must retain fence
            # authority.  This never consults unrelated raw-kernel work.
            pending = True
        self._state = "poisoned_pending_fence" if pending else "poisoned_no_work"
        self._reason = HipFgmresCanonicalPredecessorReasonV1(
            "hip_fgmres_canonical_predecessor_enqueue_failed",
            _detail(error),
        )
        self._pending = self._mint_pending()

    def _observe_fence_and_consume(self) -> None:
        kernel = self._kernel()
        token = self._live_checkpoint_token()
        if self._state not in {
            "fence_observed_ack_pending",
            "poisoned_fence_observed_ack_pending",
        }:
            row = self._telemetry
            self._telemetry = replace(
                row, fence_attempt_count=row.fence_attempt_count + 1
            )
            try:
                kernel._synchronize_checkpoint_stream(token, self._stream())
            except Exception as exc:
                raise HipFgmresCanonicalPredecessorV1Error(
                    "hip_fgmres_canonical_predecessor_fence_failed",
                    "/fence/synchronize",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            row = self._telemetry
            self._telemetry = replace(
                row, fence_success_count=row.fence_success_count + 1
            )
            self._state = (
                "poisoned_fence_observed_ack_pending"
                if self._state == "poisoned_pending_fence"
                else "fence_observed_ack_pending"
            )
        was_started = self._consume_started
        self._consume_started = True
        row = self._telemetry
        self._telemetry = replace(
            row,
            pending_consume_attempt_count=row.pending_consume_attempt_count + 1,
        )
        try:
            consumed = kernel._consume_checkpoint_pending_after_fence(
                token, self._stream()
            )
        except Exception as exc:
            raise HipFgmresCanonicalPredecessorV1Error(
                "hip_fgmres_canonical_predecessor_pending_consume_failed",
                "/fence/consume",
                _detail(exc),
                pending=self._pending,
                cleanup_owner=self,
            ) from exc
        lower = self._telemetry.async_operation_accept_lower_bound
        upper = self._telemetry.async_operation_accept_upper_bound
        if consumed == 0 and was_started:
            consumed = upper if lower == upper else lower
        if not lower <= consumed <= upper or (lower == upper and consumed != lower):
            self._state = "poisoned_fenced"
            _fail(
                "hip_fgmres_canonical_predecessor_pending_consume_mismatch",
                "/fence/consume",
                cleanup_owner=self,
            )
        self._telemetry = replace(self._telemetry, consumed_operation_count=consumed)
        self._require_live()._acknowledge_fixed_rank_coarse_overlay_fence(
            phase="canonical_prefix",
            owner=self,
        )
        if self._state == "poisoned_fence_observed_ack_pending":
            self._state = "poisoned_fenced"

    def _validate_authority(self, *, require_idle_kernel: bool) -> None:
        live = self._require_live()
        live._require_canonical_predecessor_child(self._token)
        if require_idle_kernel:
            live._validate_authority()
        parent = live._parent
        source_apply = live._source_apply
        if parent is None or source_apply is None or self._projection is None:
            _fail("hip_fgmres_canonical_predecessor_authority_invalid", "/authority")
        parent._validate_fgmres_producer_resource_projection(
            live._token, source_apply, self._projection
        )

    def _validate_pending(
        self, pending: HipFgmresCanonicalPredecessorPendingV1
    ) -> None:
        if (
            type(pending) is not HipFgmresCanonicalPredecessorPendingV1
            or pending._issuer is not self
            or pending._nonce is not self._pending_nonce
            or pending._snapshot != _pending_snapshot(pending)
            or pending is not self._pending
        ):
            _fail("hip_fgmres_canonical_predecessor_pending_invalid", "/pending")

    def _reserve_sealed_checkpoint_transaction_child(
        self,
        token: object,
        capability: HipFgmresCanonicalPredecessorCapabilityV1,
    ) -> object:
        """Reserve the sole non-owning transaction child without consuming it."""

        if type(token) is not object:
            _fail(
                "hip_fgmres_canonical_predecessor_sealed_child_token_invalid",
                "/lifetime/sealed_checkpoint_transaction_child",
            )
        with self._lock:
            if (
                self._closed
                or self._sealed_checkpoint_transaction_child_terminal
                or self._sealed_checkpoint_transaction_child_token is not None
                or self._capability_consumed
            ):
                _fail(
                    "hip_fgmres_canonical_predecessor_sealed_child_unavailable",
                    "/lifetime/sealed_checkpoint_transaction_child",
                )
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability,
                expected_context=self,
            )
            self._validate_authority(require_idle_kernel=True)
            self._sealed_checkpoint_transaction_child_token = token
            return token

    def _require_sealed_checkpoint_transaction_child(
        self,
        token: object,
        *,
        capability_consumed: bool | None = None,
    ) -> None:
        with self._lock:
            if token is not self._sealed_checkpoint_transaction_child_token:
                _fail(
                    "hip_fgmres_canonical_predecessor_sealed_child_token_invalid",
                    "/lifetime/sealed_checkpoint_transaction_child",
                )
            if self._closed:
                _fail(
                    "hip_fgmres_canonical_predecessor_sealed_child_unavailable",
                    "/lifetime/sealed_checkpoint_transaction_child",
                )
            if (
                capability_consumed is not None
                and self._capability_consumed is not capability_consumed
            ):
                _fail(
                    "hip_fgmres_canonical_predecessor_capability_state_invalid",
                    "/capability/consumed",
                )

    def _consume_sealed_checkpoint_transaction_capability(
        self,
        token: object,
        capability: HipFgmresCanonicalPredecessorCapabilityV1,
    ) -> None:
        """Atomically consume the reserved canonical capability exactly once."""

        with self._lock:
            self._require_sealed_checkpoint_transaction_child(
                token,
                capability_consumed=False,
            )
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability,
                expected_context=self,
            )
            self._validate_authority(require_idle_kernel=True)
            self._capability_consumed = True

    def _sealed_checkpoint_transaction_capability_consumed(
        self,
        token: object,
    ) -> bool:
        """Report the exact shared consume bit for caller-side reconciliation."""

        with self._lock:
            self._require_sealed_checkpoint_transaction_child(token)
            return self._capability_consumed

    def _validate_sealed_checkpoint_transaction_authority(
        self,
        token: object,
        *,
        expected_pending_operation_bounds: tuple[int, int],
    ) -> None:
        """Validate lineage plus the exact live stream reservation interval."""

        if (
            type(expected_pending_operation_bounds) is not tuple
            or len(expected_pending_operation_bounds) != 2
            or any(
                type(value) is not int for value in expected_pending_operation_bounds
            )
            or not 0
            <= expected_pending_operation_bounds[0]
            <= expected_pending_operation_bounds[1]
        ):
            _fail(
                "hip_fgmres_canonical_predecessor_pending_expectation_invalid",
                "/kernel/pending_operation_bounds",
            )
        with self._lock:
            self._require_sealed_checkpoint_transaction_child(
                token,
                capability_consumed=True,
            )
            self._validate_authority(require_idle_kernel=False)
            live = self._require_live()
            live._validate_authority_for_canonical_child(
                self._token,
                pending_operation_bounds=expected_pending_operation_bounds,
            )
            kernel = self._kernel()
            checkpoint_token = self._live_checkpoint_token()
            try:
                runtime_owner = kernel._checkpoint_runtime_owner(checkpoint_token)
                binding_snapshot = kernel._checkpoint_binding_snapshot(checkpoint_token)
            except Exception as exc:
                raise HipFgmresCanonicalPredecessorV1Error(
                    "hip_fgmres_canonical_predecessor_sealed_authority_invalid",
                    "/kernel/authority",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            if (
                runtime_owner is not live._loaded_runtime
                or binding_snapshot != live._kernel_binding_snapshot
            ):
                _fail(
                    "hip_fgmres_canonical_predecessor_sealed_authority_invalid",
                    "/kernel/authority",
                    cleanup_owner=self,
                )

    def _release_sealed_checkpoint_transaction_child(self, token: object) -> None:
        """Release the child only after its exact stream reservation is empty."""

        with self._lock:
            self._require_sealed_checkpoint_transaction_child(token)
            self._validate_authority(require_idle_kernel=False)
            self._require_live()._validate_authority_for_canonical_child(
                self._token,
                pending_operation_bounds=(0, 0),
            )
            if self._capability_consumed:
                self._sealed_checkpoint_transaction_child_terminal = True
            self._sealed_checkpoint_transaction_child_token = None

    def _mint_pending(self) -> HipFgmresCanonicalPredecessorPendingV1:
        if self._pending is not None:
            return self._pending
        pending = _issue_capability(
            HipFgmresCanonicalPredecessorPendingV1,
            {
                "context_id": self._context_id,
                "attempted_operation_count": (
                    self._telemetry.async_operation_attempt_count
                ),
                "accepted_operation_lower_bound": (
                    self._telemetry.async_operation_accept_lower_bound
                ),
                "accepted_operation_upper_bound": (
                    self._telemetry.async_operation_accept_upper_bound
                ),
                "_issuer": self,
                "_nonce": self._pending_nonce,
            },
        )
        object.__setattr__(pending, "_snapshot", _pending_snapshot(pending))
        return pending

    def _release_child(self) -> None:
        if self._child_released:
            return
        live = self._require_live()
        live._release_canonical_predecessor_child(self._token)
        self._child_released = True

    def _kernel(self) -> HipRtcFgmresV2Kernel:
        live = self._require_live()
        if type(live._kernel) is not HipRtcFgmresV2Kernel:
            _fail("hip_fgmres_canonical_predecessor_kernel_invalid", "/kernel")
        return live._kernel

    def _stream(self) -> Any:
        live = self._require_live()
        if live._stream is None or live._stream_pointer_snapshot is None:
            _fail("hip_fgmres_canonical_predecessor_stream_invalid", "/stream")
        return live._stream_pointer_snapshot

    def _live_checkpoint_token(self) -> object:
        return self._require_live()._checkpoint_token

    def _require_live(self) -> HipFgmresLiveCheckpointExecutionContextV1:
        if type(self._live) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail("hip_fgmres_canonical_predecessor_live_invalid", "/live_context")
        return self._live

    def _build_receipt(
        self, status: CanonicalPredecessorStatusV1
    ) -> HipFgmresCanonicalPredecessorReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail("hip_fgmres_canonical_predecessor_receipt_unavailable", "/receipt")
        fenced = status in {"predecessor_fenced", "context_closed"} and (
            self._capability is not None or status == "predecessor_fenced"
        )
        live_bound = status not in {"cleanup_failed"}
        claims = HipFgmresCanonicalPredecessorClaimsV1(
            source_apply_completion_bound=live_bound,
            positive_jacobi_completion_bound=live_bound,
            persistent_parent3_owned8_bound=live_bound,
            delegated_operator_workspace_bound=live_bound,
            same_runtime_device_stream_bound=live_bound,
            owned_content_initialized=fenced,
            canonical_producer_prefix_fenced=fenced,
            device_mask_domain_gate_bound=fenced,
        )
        draft = HipFgmresCanonicalPredecessorReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_CANONICAL_PREDECESSOR_EVIDENCE_SCOPE_V1,
            actual_backend=self._require_live().opening_receipt.actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            projection=HipFgmresCanonicalPredecessorProjectionV1(
                _DIRECT_ROLES,
                _DELEGATED_OPERATOR_ROLES,
                _DELEGATED_WORKSPACE_ROLES,
                live_bound,
                live_bound,
            ),
            admitted_mask_domain=_MASK_DOMAIN,
            telemetry=self._telemetry,
            claims=claims,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


def open_hip_fgmres_canonical_predecessor_context_v1(
    live_context: HipFgmresLiveCheckpointExecutionContextV1,
) -> HipFgmresCanonicalPredecessorOpenResultV1:
    """Reserve a single canonical producer child over a ready live context."""

    context = HipFgmresCanonicalPredecessorExecutionContextV1(_mint=_CONTEXT_MINT)
    reserved = False
    try:
        if type(live_context) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail("hip_fgmres_canonical_predecessor_live_invalid", "/live_context")
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            live_context.opening_receipt, expected_context=live_context
        )
        acquired = live_context._reserve_canonical_predecessor_child(context._token)
        if acquired is not context._token:
            _fail("hip_fgmres_canonical_predecessor_child_changed", "/lifetime")
        reserved = True
        context._live = live_context
        parent = live_context._parent
        source_apply = live_context._source_apply
        plan = live_context._recurrence_plan
        kernel = live_context._kernel
        if (
            parent is None
            or source_apply is None
            or plan is None
            or type(kernel) is not HipRtcFgmresV2Kernel
        ):
            _fail("hip_fgmres_canonical_predecessor_authority_invalid", "/authority")
        projection = parent._issue_fgmres_producer_resource_projection(
            live_context._token, source_apply
        )
        parent._validate_fgmres_producer_resource_projection(
            live_context._token, source_apply, projection
        )
        context._projection = projection
        direct = {row.role: row for row in live_context._group_capabilities}
        if tuple(direct) != _DIRECT_ROLES:
            _fail(
                "hip_fgmres_canonical_predecessor_direct_group_invalid", "/projection"
            )
        context._pointers = {
            role: int(direct[role].pointer_snapshot) for role in _DIRECT_ROLES
        }
        context._pointers.update(
            {
                role: _runtime_pointer(projection.pointer(role), role)
                for role in (*_DELEGATED_OPERATOR_ROLES, *_DELEGATED_WORKSPACE_ROLES)
            }
        )
        context._owned_byte_lengths = {
            role: int(direct[role].nbytes) for role in _OWNED_ROLES
        }
        context._schedule = canonical_first_column_predecessor_launches_v2(
            plan.free_dof_count, plan.restart_dimension
        )
        schedule_payload = [asdict(row) for row in context._schedule]
        validator_schedule = (
            hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
        )
        direct_hash = canonical_hash(
            {
                "roles": list(_DIRECT_ROLES),
                "generations": [direct[role].generation for role in _DIRECT_ROLES],
                "byte_lengths": [direct[role].nbytes for role in _DIRECT_ROLES],
                "pointer_values_serialized": False,
            }
        )
        resources = projection.ordered_resources
        physical_hash = canonical_hash(
            {
                "roles": [row.role for row in resources],
                "delegation_kinds": [row.delegation_kind for row in resources],
                "element_types": [row.element_type for row in resources],
                "byte_lengths": [row.nbytes for row in resources],
                "generations": [row.generation for row in resources],
                "primitive_parent_lease_epoch": projection.primitive_parent_lease_epoch,
                "solver_child_lease_epoch": projection.solver_child_lease_epoch,
                "pointer_values_serialized": False,
            }
        )
        live_receipt = live_context.opening_receipt
        if live_receipt.kernel is None:
            _fail("hip_fgmres_canonical_predecessor_kernel_invalid", "/kernel")
        identity = kernel.identity
        context._context_id = canonical_hash(
            {
                "profile": HIP_FGMRES_CANONICAL_PREDECESSOR_CAPABILITY_PROFILE_V1,
                "live_context_id": live_receipt.context_id,
                "live_opening_receipt_hash": live_receipt.context_receipt_hash,
                "canonical_schedule_hash": canonical_hash(schedule_payload),
                "physical_projection_hash": physical_hash,
            }
        )
        context._bindings = HipFgmresCanonicalPredecessorBindingsV1(
            live_receipt.context_id,
            live_receipt.context_receipt_hash,
            live_receipt.bindings.primitive_context_id,
            live_receipt.bindings.primitive_opening_receipt_hash,
            live_receipt.bindings.primitive_evidence_scope,
            live_receipt.bindings.primitive_actual_backend,
            live_receipt.bindings.source_apply_receipt_hash,
            live_receipt.bindings.source_state_hash,
            live_receipt.bindings.recurrence_plan_hash,
            live_receipt.bindings.recurrence_kernel_abi_hash,
            identity.identity_hash,
            identity.source_sha256,
            live_receipt.kernel.kernel_origin,
            live_receipt.kernel.runtime_library_discovery_source,
            live_receipt.kernel.hiprtc_library_discovery_source,
            canonical_hash(schedule_payload),
            canonical_hash(validator_schedule),
            direct_hash,
            physical_hash,
            projection.primitive_parent_lease_epoch,
            projection.solver_child_lease_epoch,
        )
        context._dimensions = HipFgmresCanonicalPredecessorDimensionsV1(
            plan.free_dof_count,
            plan.reduced_csr_nnz,
            plan.restart_dimension,
            len(reduction_stage_output_counts_v2(plan.free_dof_count)),
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_canonical_predecessor_receipt_v1(
            receipt, expected_context=context
        )
        return HipFgmresCanonicalPredecessorOpenResultV1(context, receipt)
    except BaseException:
        if reserved:
            try:
                live_context._release_canonical_predecessor_child(context._token)
            except BaseException:
                pass
        raise


def validate_hip_fgmres_canonical_predecessor_receipt_v1(
    receipt: HipFgmresCanonicalPredecessorReceiptV1,
    *,
    expected_context: HipFgmresCanonicalPredecessorExecutionContextV1 | None = None,
) -> HipFgmresCanonicalPredecessorReceiptV1:
    if type(receipt) is not HipFgmresCanonicalPredecessorReceiptV1:
        _fail("hip_fgmres_canonical_predecessor_receipt_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=False)
    if (
        type(receipt.receipt_hash) is not str
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != canonical_hash(payload)
    ):
        _fail("hip_fgmres_canonical_predecessor_receipt_hash_invalid", "/receipt_hash")
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_canonical_predecessor_schema_invalid",
            path or "/",
            errors[0].message,
        )
    forbidden = (
        receipt.promotion_eligible,
        receipt.claims.device_validation_outcome_host_observed,
        receipt.claims.actual_mask_host_observed,
        receipt.claims.authoritative_predecessor_proven,
        receipt.claims.checkpoint_transaction_ready,
        receipt.claims.invalid_source_destination_atomicity_proven,
        receipt.claims.live_solver_ready,
        receipt.claims.solution_ready,
        receipt.claims.iteration_host_copy_zero_proven,
        receipt.claims.asymptotic_o_n_proven,
        receipt.claims.speedup_proven,
        receipt.claims.commercial_ready,
        receipt.claims.promotion_eligible,
    )
    if any(forbidden) or receipt.admitted_mask_domain != _MASK_DOMAIN:
        _fail("hip_fgmres_canonical_predecessor_claim_invalid", "/claims")
    native_parent = (
        receipt.bindings.primitive_evidence_scope
        == "native_hiprtc_krylov_primitives_composite"
        and receipt.bindings.primitive_actual_backend == "hip"
    )
    native_kernel = (
        receipt.bindings.kernel_origin == "internally_compiled"
        and receipt.bindings.runtime_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
        and receipt.bindings.hiprtc_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
    )
    expected_backend = "hip" if native_parent and native_kernel else "test_double"
    if receipt.actual_backend != expected_backend:
        _fail("hip_fgmres_canonical_predecessor_backend_invalid", "/actual_backend")
    _validate_receipt_semantics(receipt)
    fenced_claims = (
        receipt.claims.owned_content_initialized,
        receipt.claims.canonical_producer_prefix_fenced,
        receipt.claims.device_mask_domain_gate_bound,
    )
    if len(set(fenced_claims)) != 1:
        _fail("hip_fgmres_canonical_predecessor_claim_invalid", "/claims")
    fenced = receipt.status == "predecessor_fenced"
    if any(value is not fenced for value in fenced_claims):
        if receipt.status != "context_closed":
            _fail("hip_fgmres_canonical_predecessor_claim_invalid", "/claims")
    if expected_context is not None:
        if (
            type(expected_context)
            is not HipFgmresCanonicalPredecessorExecutionContextV1
        ):
            _fail("hip_fgmres_canonical_predecessor_context_invalid", "/")
        if (
            receipt.receipt_hash
            != expected_context._build_receipt(expected_context._state).receipt_hash
        ):
            _fail("hip_fgmres_canonical_predecessor_context_mismatch", "/")
    return receipt


def _validate_receipt_semantics(
    receipt: HipFgmresCanonicalPredecessorReceiptV1,
) -> None:
    dimensions = receipt.dimensions
    try:
        expected_stages = len(
            reduction_stage_output_counts_v2(dimensions.free_dof_count)
        )
        schedule = canonical_first_column_predecessor_launches_v2(
            dimensions.free_dof_count,
            dimensions.restart_dimension,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_canonical_predecessor_dimensions_invalid",
            "/dimensions",
            _detail(exc),
        )
    if dimensions.reduction_stage_count != expected_stages:
        _fail(
            "hip_fgmres_canonical_predecessor_dimensions_invalid",
            "/dimensions/reduction_stage_count",
        )
    expected_schedule_hash = canonical_hash([asdict(row) for row in schedule])
    expected_validator_hash = canonical_hash(
        hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    )
    if receipt.bindings.canonical_schedule_hash != expected_schedule_hash:
        _fail(
            "hip_fgmres_canonical_predecessor_schedule_hash_invalid",
            "/bindings/canonical_schedule_hash",
        )
    if receipt.bindings.validator_schedule_hash != expected_validator_hash:
        _fail(
            "hip_fgmres_canonical_predecessor_validator_hash_invalid",
            "/bindings/validator_schedule_hash",
        )
    expected_context_id = canonical_hash(
        {
            "profile": HIP_FGMRES_CANONICAL_PREDECESSOR_CAPABILITY_PROFILE_V1,
            "live_context_id": receipt.bindings.live_context_id,
            "live_opening_receipt_hash": (receipt.bindings.live_opening_receipt_hash),
            "canonical_schedule_hash": expected_schedule_hash,
            "physical_projection_hash": receipt.bindings.physical_projection_hash,
        }
    )
    if receipt.context_id != expected_context_id:
        _fail(
            "hip_fgmres_canonical_predecessor_context_id_invalid",
            "/context_id",
        )
    projection = receipt.projection
    if (
        projection.persistent_roles != _DIRECT_ROLES
        or projection.delegated_operator_roles != _DELEGATED_OPERATOR_ROLES
        or projection.delegated_workspace_roles != _DELEGATED_WORKSPACE_ROLES
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_projection_invalid",
            "/projection",
        )

    live_bound = receipt.status != "cleanup_failed"
    bound_claims = (
        receipt.claims.source_apply_completion_bound,
        receipt.claims.positive_jacobi_completion_bound,
        receipt.claims.persistent_parent3_owned8_bound,
        receipt.claims.delegated_operator_workspace_bound,
        receipt.claims.same_runtime_device_stream_bound,
        projection.runtime_device_bound,
        projection.same_stream_bound,
    )
    if any(value is not live_bound for value in bound_claims):
        _fail(
            "hip_fgmres_canonical_predecessor_claim_invalid",
            "/claims",
        )

    telemetry = receipt.telemetry
    component_rows = (
        (
            telemetry.memset_attempt_count,
            telemetry.memset_accept_lower_bound,
            telemetry.memset_accept_upper_bound,
        ),
        (
            telemetry.kernel_launch_attempt_count,
            telemetry.kernel_launch_accept_lower_bound,
            telemetry.kernel_launch_accept_upper_bound,
        ),
    )
    if any(
        not 0 <= lower <= upper <= attempts for attempts, lower, upper in component_rows
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if (
        telemetry.async_operation_attempt_count
        != telemetry.memset_attempt_count + telemetry.kernel_launch_attempt_count
        or telemetry.async_operation_accept_lower_bound
        != telemetry.memset_accept_lower_bound
        + telemetry.kernel_launch_accept_lower_bound
        or telemetry.async_operation_accept_upper_bound
        != telemetry.memset_accept_upper_bound
        + telemetry.kernel_launch_accept_upper_bound
        or telemetry.memset_attempt_count > 8
        or telemetry.kernel_launch_attempt_count > len(schedule)
        or (
            telemetry.kernel_launch_attempt_count > 0
            and telemetry.memset_attempt_count != 8
        )
        or telemetry.fence_success_count > 1
        or telemetry.fence_success_count > telemetry.fence_attempt_count
        or telemetry.consumed_operation_count
        > telemetry.async_operation_accept_upper_bound
        or (
            telemetry.pending_consume_attempt_count > 0
            and telemetry.fence_success_count != 1
        )
        or (
            telemetry.consumed_operation_count > 0
            and telemetry.pending_consume_attempt_count == 0
        )
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )

    expected_operations = 8 + len(schedule)
    complete_submission_statuses = {
        "predecessor_pending",
        "fence_observed_ack_pending",
        "predecessor_fenced",
    }
    if receipt.status in complete_submission_statuses and (
        telemetry.async_operation_attempt_count != expected_operations
        or telemetry.async_operation_accept_lower_bound != expected_operations
        or telemetry.async_operation_accept_upper_bound != expected_operations
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry/async_operation_attempt_count",
        )
    if receipt.status == "context_ready" and any(telemetry.to_dict().values()):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status == "predecessor_pending" and (
        telemetry.fence_attempt_count != 0
        or telemetry.pending_consume_attempt_count != 0
        or telemetry.consumed_operation_count != 0
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status in {
        "fence_observed_ack_pending",
        "poisoned_fence_observed_ack_pending",
    } and (
        telemetry.fence_success_count != 1
        or telemetry.pending_consume_attempt_count < 1
        or telemetry.consumed_operation_count != 0
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status == "poisoned_no_work" and (
        telemetry.async_operation_accept_upper_bound != 0
        or telemetry.fence_success_count != 0
        or telemetry.consumed_operation_count != 0
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if (
        receipt.status == "poisoned_pending_fence"
        and telemetry.fence_success_count != 0
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status.startswith("poisoned_") and receipt.reason is None:
        _fail(
            "hip_fgmres_canonical_predecessor_reason_invalid",
            "/reason",
        )
    if receipt.status in complete_submission_statuses | {"context_ready"} and (
        receipt.reason is not None
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_reason_invalid",
            "/reason",
        )

    fenced_claim = receipt.claims.canonical_producer_prefix_fenced
    if fenced_claim and (
        receipt.status not in {"predecessor_fenced", "context_closed"}
        or telemetry.async_operation_accept_lower_bound != expected_operations
        or telemetry.async_operation_accept_upper_bound != expected_operations
        or telemetry.fence_success_count != 1
        or telemetry.consumed_operation_count != expected_operations
    ):
        _fail(
            "hip_fgmres_canonical_predecessor_claim_invalid",
            "/claims/canonical_producer_prefix_fenced",
        )
    if receipt.status == "predecessor_fenced" and not fenced_claim:
        _fail(
            "hip_fgmres_canonical_predecessor_claim_invalid",
            "/claims/canonical_producer_prefix_fenced",
        )


def validate_hip_fgmres_canonical_predecessor_capability_v1(
    capability: HipFgmresCanonicalPredecessorCapabilityV1,
    *,
    expected_context: HipFgmresCanonicalPredecessorExecutionContextV1,
) -> HipFgmresCanonicalPredecessorCapabilityV1:
    """Validate one live, exact-context conditional device capability."""

    if type(expected_context) is not HipFgmresCanonicalPredecessorExecutionContextV1:
        _fail(
            "hip_fgmres_canonical_predecessor_capability_invalid",
            "/capability",
        )
    with expected_context._lock:
        if (
            type(capability) is not HipFgmresCanonicalPredecessorCapabilityV1
            or capability._issuer is not expected_context
            or capability._nonce is not expected_context._capability_nonce
            or capability._snapshot != _capability_snapshot(capability)
            or capability is not expected_context._capability
            or capability.context_id != expected_context._context_id
            or capability.mask_domain != _MASK_DOMAIN
            or expected_context._state != "predecessor_fenced"
            or expected_context._capability_consumed
            or expected_context.closed
        ):
            _fail(
                "hip_fgmres_canonical_predecessor_capability_invalid",
                "/capability",
            )
        receipt = expected_context.receipt()
        if capability.receipt_hash != receipt.receipt_hash:
            _fail(
                "hip_fgmres_canonical_predecessor_capability_invalid",
                "/capability/receipt_hash",
            )
        return capability


def _receipt_payload(
    receipt: HipFgmresCanonicalPredecessorReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_CANONICAL_PREDECESSOR_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_CANONICAL_PREDECESSOR_CAPABILITY_PROFILE_V1,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "projection": receipt.projection.to_dict(),
        "admitted_mask_domain": list(receipt.admitted_mask_domain),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _pending_snapshot(
    pending: HipFgmresCanonicalPredecessorPendingV1,
) -> tuple[Any, ...]:
    return (
        pending.context_id,
        pending.attempted_operation_count,
        pending.accepted_operation_lower_bound,
        pending.accepted_operation_upper_bound,
        id(pending._issuer),
        id(pending._nonce),
    )


def _capability_snapshot(
    capability: HipFgmresCanonicalPredecessorCapabilityV1,
) -> tuple[Any, ...]:
    return (
        capability.context_id,
        capability.receipt_hash,
        capability.mask_domain,
        id(capability._issuer),
        id(capability._nonce),
    )


def _issue_capability(type_: type[Any], fields: dict[str, Any]) -> Any:
    value = object.__new__(type_)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: object) -> str:
    text = _HEX_ADDRESS_RE.sub("<redacted-address>", str(value))
    text = _DECIMAL_HANDLE_RE.sub("<redacted-handle>", text)
    return (" ".join(text.split())[:512]) or "unspecified"


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresCanonicalPredecessorExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresCanonicalPredecessorV1Error(
        code,
        path,
        message or code,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_CANONICAL_PREDECESSOR_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_CANONICAL_PREDECESSOR_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_CANONICAL_PREDECESSOR_SCHEMA_VERSION_V1",
    "HipFgmresCanonicalPredecessorBindingsV1",
    "HipFgmresCanonicalPredecessorCapabilityV1",
    "HipFgmresCanonicalPredecessorClaimsV1",
    "HipFgmresCanonicalPredecessorDimensionsV1",
    "HipFgmresCanonicalPredecessorExecutionContextV1",
    "HipFgmresCanonicalPredecessorOpenResultV1",
    "HipFgmresCanonicalPredecessorPendingV1",
    "HipFgmresCanonicalPredecessorProjectionV1",
    "HipFgmresCanonicalPredecessorReasonV1",
    "HipFgmresCanonicalPredecessorReceiptV1",
    "HipFgmresCanonicalPredecessorTelemetryV1",
    "HipFgmresCanonicalPredecessorV1Error",
    "open_hip_fgmres_canonical_predecessor_context_v1",
    "validate_hip_fgmres_canonical_predecessor_receipt_v1",
    "validate_hip_fgmres_canonical_predecessor_capability_v1",
]
