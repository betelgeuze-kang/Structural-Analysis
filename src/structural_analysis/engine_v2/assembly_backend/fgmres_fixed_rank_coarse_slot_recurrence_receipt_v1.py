"""Strict pointer-free receipt for the live typed coarse-slot recurrence.

The receipt records one logical recurrence row backed by four typed-slot
launches and one same-stream device terminal guard.  It deliberately exposes
no pointer, stream, module, function, owner, lease, or process token.  A
detached validation proves schema and semantic self-consistency; passing the
live context to the validator additionally proves process-local provenance
and freshness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any, Literal, NoReturn, TYPE_CHECKING

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

if TYPE_CHECKING:
    from .fgmres_fixed_rank_coarse_slot_recurrence_v1 import (
        HipFgmresFixedRankCoarseSlotRecurrenceV1,
    )


HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-slot-recurrence.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_CAPABILITY_PROFILE = (
    "phase0_live_typed_fixed_rank_coarse_recurrence_with_device_terminal_guard"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_EVIDENCE_SCOPE = (
    "pointer_free_live_typed_slot_plus_device_terminal_guard_contract_non_promoting"
)

HipFgmresFixedRankCoarseSlotRecurrencePhaseV1 = Literal[
    "canonical_prefix",
    "global_suffix",
]
HipFgmresFixedRankCoarseSlotRecurrenceStatusV1 = Literal[
    "context_ready",
    "canonical_slot_pending",
    "canonical_fenced",
    "global_slot_pending",
    "global_fenced",
    "global_receipt_bound",
    "poisoned",
    "context_closed",
    "cleanup_failed",
]

_SCHEMA_RESOURCE = "hip_fgmres_fixed_rank_coarse_slot_recurrence_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_RESTART_DIMENSION = 16
_MAX_ITERATIONS = 4096
_MAX_PADDED_APPLICATION_COUNT = max(
    ((_MAX_ITERATIONS + width - 1) // width) * width
    for width in range(1, _MAX_RESTART_DIMENSION + 1)
)


class HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error(RuntimeError):
    """Stable strict-receipt validation failure."""

    def __init__(self, code: str, path: str, detail: str = "") -> None:
        self.code = code
        self.path = path
        self.detail = _redact(detail)
        super().__init__(f"{code}@{path}" + (f": {self.detail}" if detail else ""))


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1:
    live_checkpoint_context_id: str
    live_checkpoint_opening_receipt_hash: str
    coarse_context_id: str
    coarse_context_opening_receipt_hash: str
    source_fgmres_plan_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_identity_hash: str
    recurrence_kernel_source_sha256: str
    coarse_plan_hash: str
    coarse_space_hash: str
    coarse_kernel_identity_hash: str
    coarse_kernel_source_sha256: str
    slot_kernel_identity_hash: str
    slot_kernel_abi_hash: str
    slot_combined_source_sha256: str
    terminal_guard_identity_hash: str
    terminal_guard_abi_hash: str
    terminal_guard_combined_source_sha256: str
    full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str
    schedule_coordinates_hash: str
    schedule_epochs_hash: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    retained_rank: int
    expected_application_count: int
    canonical_prefix_application_count: Literal[1] = 1
    global_suffix_application_count: int = 0
    logical_recurrence_launches_per_application: Literal[1] = 1
    legacy_jacobi_launches_per_application: Literal[0] = 0
    physical_slot_launches_per_application: Literal[4] = 4
    physical_terminal_guard_launches_per_application: Literal[1] = 1
    total_physical_launches_per_application: Literal[5] = 5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1:
    sequence: int
    phase: HipFgmresFixedRankCoarseSlotRecurrencePhaseV1
    schedule_epoch: int
    restart_index: int
    column_index: int
    logical_index: int
    recurrence_descriptor_hash: str
    logical_recurrence_launch_count: Literal[1] = 1
    legacy_jacobi_launch_count: Literal[0] = 0
    physical_slot_launch_count: Literal[4] = 4
    physical_terminal_guard_launch_count: Literal[1] = 1
    physical_launch_count: Literal[5] = 5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1:
    application_attempt_count: int = 0
    application_success_count: int = 0
    logical_recurrence_launch_count: int = 0
    retained_jacobi_launch_count: Literal[0] = 0
    physical_slot_launch_accept_count: int = 0
    physical_terminal_guard_launch_accept_count: int = 0
    canonical_application_count: int = 0
    global_application_count: int = 0
    parent_fence_ack_count: int = 0
    physical_slot_launch_ack_count: int = 0
    physical_terminal_guard_launch_ack_count: int = 0
    additional_h2d_copy_count: Literal[0] = 0
    additional_d2h_copy_count: Literal[0] = 0
    additional_allocation_count: Literal[0] = 0
    additional_synchronization_count: Literal[0] = 0
    additional_csr_apply_count: Literal[0] = 0
    host_status_branch_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1:
    exact_live_and_coarse_contexts_bound: bool
    exact_slot_and_terminal_guard_kernel_identities_bound: bool
    immutable_schedule_hashes_bound: bool
    global_recurrence_receipt_bound: bool
    all_scheduled_jacobi_rows_replaced: bool
    one_logical_row_per_five_physical_launches: bool
    same_stream_slot_then_terminal_guard_order_bound: bool
    both_physical_owners_parent_fenced: bool
    device_terminal_status_binding_contract: bool
    application_window_host_copy_zero_contract: bool
    no_additional_intermediate_synchronization_contract: bool
    legacy_jacobi_launch_zero_observed: bool
    pointer_values_serialized: Literal[False] = False
    actual_integrated_device_execution_proven: Literal[False] = False
    authoritative_numerical_parity_proven: Literal[False] = False
    full_iteration_host_copy_zero_proven: Literal[False] = False
    end_to_end_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
    status: HipFgmresFixedRankCoarseSlotRecurrenceStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresFixedRankCoarseSlotRecurrenceReasonV1 | None
    bindings: HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1
    dimensions: HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1
    applications: tuple[HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1, ...]
    application_sequence_hash: str
    global_context_id: str
    global_receipt_hash: str
    telemetry: HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1
    claims: HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


def validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
    receipt: HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1,
    *,
    expected_context: HipFgmresFixedRankCoarseSlotRecurrenceV1 | None = None,
) -> HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
    """Validate strict detached semantics and optional live provenance."""

    if type(receipt) is not HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
        _fail("hip_fgmres_coarse_slot_receipt_type_invalid", "/receipt")
    if (
        type(receipt.bindings) is not HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1
        or type(receipt.dimensions)
        is not HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1
        or type(receipt.telemetry)
        is not HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1
        or type(receipt.claims) is not HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1
        or (
            receipt.reason is not None
            and type(receipt.reason)
            is not HipFgmresFixedRankCoarseSlotRecurrenceReasonV1
        )
        or type(receipt.applications) is not tuple
        or any(
            type(row) is not HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1
            for row in receipt.applications
        )
    ):
        _fail("hip_fgmres_coarse_slot_receipt_nested_type_invalid", "/receipt")
    if (
        type(receipt.status) is not str
        or type(receipt.evidence_scope) is not str
        or type(receipt.actual_backend) is not str
        or any(type(value) is not str for value in receipt.bindings.to_dict().values())
        or any(
            type(value) is not int for value in receipt.dimensions.to_dict().values()
        )
        or any(type(value) is not int for value in receipt.telemetry.to_dict().values())
        or any(type(value) is not bool for value in receipt.claims.to_dict().values())
        or (
            receipt.reason is not None
            and (
                type(receipt.reason.code) is not str
                or type(receipt.reason.detail) is not str
            )
        )
        or any(
            type(row.phase) is not str
            or type(row.recurrence_descriptor_hash) is not str
            or any(
                type(getattr(row, name)) is not int
                for name in (
                    "sequence",
                    "schedule_epoch",
                    "restart_index",
                    "column_index",
                    "logical_index",
                    "logical_recurrence_launch_count",
                    "legacy_jacobi_launch_count",
                    "physical_slot_launch_count",
                    "physical_terminal_guard_launch_count",
                    "physical_launch_count",
                )
            )
            for row in receipt.applications
        )
    ):
        _fail("hip_fgmres_coarse_slot_receipt_nested_type_invalid", "/receipt")

    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_coarse_slot_receipt_schema_invalid",
            path or "/",
            errors[0].message,
        )

    dimensions = receipt.dimensions
    telemetry = receipt.telemetry
    applications = receipt.applications
    expected_count = dimensions.expected_application_count
    expected_full_count = (
        dimensions.restart_dimension * dimensions.maximum_restart_count
    )
    expected_coordinates = tuple(
        (restart, column)
        for restart in range(1, dimensions.maximum_restart_count + 1)
        for column in range(dimensions.restart_dimension)
    )[:expected_count]
    actual_coordinates = tuple(
        (row.restart_index, row.column_index) for row in applications
    )
    epochs = tuple(row.schedule_epoch for row in applications)
    global_bound = (
        receipt.global_context_id != _ZERO_HASH
        and receipt.global_receipt_hash != _ZERO_HASH
    )
    all_rows_fenced = (
        len(applications) == expected_count
        and telemetry.application_attempt_count == expected_count
        and telemetry.application_success_count == expected_count
        and telemetry.logical_recurrence_launch_count == expected_count
        and telemetry.physical_slot_launch_accept_count == 4 * expected_count
        and telemetry.physical_terminal_guard_launch_accept_count == expected_count
        and telemetry.physical_slot_launch_ack_count == 4 * expected_count
        and telemetry.physical_terminal_guard_launch_ack_count == expected_count
        and telemetry.parent_fence_ack_count == 2
    )
    integrated = all_rows_fenced and global_bound
    all_accepted_launches_acknowledged = (
        telemetry.physical_slot_launch_ack_count
        == telemetry.physical_slot_launch_accept_count
        and telemetry.physical_terminal_guard_launch_ack_count
        == telemetry.physical_terminal_guard_launch_accept_count
    )
    healthy_state_valid = {
        "context_ready": (
            len(applications) == 0
            and telemetry.application_attempt_count == 0
            and telemetry.physical_slot_launch_accept_count == 0
            and telemetry.physical_terminal_guard_launch_accept_count == 0
            and telemetry.parent_fence_ack_count == 0
            and not global_bound
        ),
        "canonical_slot_pending": (
            len(applications) == 1
            and telemetry.application_attempt_count == 1
            and telemetry.physical_slot_launch_accept_count == 4
            and telemetry.physical_terminal_guard_launch_accept_count == 1
            and telemetry.parent_fence_ack_count == 0
            and telemetry.physical_slot_launch_ack_count == 0
            and telemetry.physical_terminal_guard_launch_ack_count == 0
            and not global_bound
        ),
        "canonical_fenced": (
            len(applications) == 1
            and telemetry.application_attempt_count == 1
            and telemetry.physical_slot_launch_accept_count == 4
            and telemetry.physical_terminal_guard_launch_accept_count == 1
            and telemetry.parent_fence_ack_count == 1
            and telemetry.physical_slot_launch_ack_count == 4
            and telemetry.physical_terminal_guard_launch_ack_count == 1
            and not global_bound
        ),
        "global_slot_pending": (
            2 <= len(applications) <= expected_count
            and telemetry.application_attempt_count == len(applications)
            and telemetry.physical_slot_launch_accept_count == 4 * len(applications)
            and telemetry.physical_terminal_guard_launch_accept_count
            == len(applications)
            and telemetry.parent_fence_ack_count == 1
            and telemetry.physical_slot_launch_ack_count == 4
            and telemetry.physical_terminal_guard_launch_ack_count == 1
            and not global_bound
        ),
        "global_fenced": all_rows_fenced and not global_bound,
        "global_receipt_bound": integrated,
    }
    reason_valid = (
        receipt.reason is not None
        if receipt.status in {"poisoned", "cleanup_failed"}
        else receipt.reason is None
        if receipt.status != "context_closed"
        else True
    )
    reason_code_valid = (
        receipt.reason is None
        or (
            receipt.status == "poisoned"
            and receipt.reason.code == "hip_fgmres_coarse_slot_recurrence_poisoned"
        )
        or (
            receipt.status == "cleanup_failed"
            and receipt.reason.code
            == "hip_fgmres_coarse_slot_recurrence_cleanup_failed"
        )
        or (
            receipt.status == "context_closed"
            and receipt.reason.code
            in {
                "hip_fgmres_coarse_slot_recurrence_poisoned",
                "hip_fgmres_coarse_slot_recurrence_cleanup_failed",
            }
        )
    )
    expected_claims = {
        "exact_live_and_coarse_contexts_bound": True,
        "exact_slot_and_terminal_guard_kernel_identities_bound": True,
        "immutable_schedule_hashes_bound": True,
        "global_recurrence_receipt_bound": global_bound,
        "all_scheduled_jacobi_rows_replaced": all_rows_fenced,
        "one_logical_row_per_five_physical_launches": all_rows_fenced,
        "same_stream_slot_then_terminal_guard_order_bound": all_rows_fenced,
        "both_physical_owners_parent_fenced": all_rows_fenced,
        "device_terminal_status_binding_contract": all_rows_fenced,
        "application_window_host_copy_zero_contract": all_rows_fenced,
        "no_additional_intermediate_synchronization_contract": all_rows_fenced,
        "legacy_jacobi_launch_zero_observed": all_rows_fenced,
    }

    if (
        receipt.schema_version
        != HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION
        or receipt.evidence_scope
        != HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_EVIDENCE_SCOPE
        or receipt.promotion_eligible is not False
        or not _valid_hash(receipt.context_id)
        or receipt.context_id
        != _context_id_for(receipt.bindings, dimensions, receipt.actual_backend)
        or not _valid_hash(receipt.receipt_hash)
        or not _valid_hash(receipt.application_sequence_hash)
        or dimensions.free_dof_count <= 0
        or dimensions.restart_dimension <= 0
        or dimensions.restart_dimension > _MAX_RESTART_DIMENSION
        or dimensions.max_iterations <= 0
        or dimensions.max_iterations > _MAX_ITERATIONS
        or dimensions.maximum_restart_count <= 0
        or dimensions.maximum_restart_count > _MAX_ITERATIONS
        or dimensions.retained_rank <= 0
        or dimensions.retained_rank > _MAX_RESTART_DIMENSION
        or dimensions.retained_rank > dimensions.free_dof_count
        or expected_count <= 0
        or expected_count > _MAX_PADDED_APPLICATION_COUNT
        or dimensions.maximum_restart_count
        != (dimensions.max_iterations + dimensions.restart_dimension - 1)
        // dimensions.restart_dimension
        or expected_count != expected_full_count
        or dimensions.global_suffix_application_count != expected_count - 1
        or len(applications) > expected_count
        or actual_coordinates != expected_coordinates[: len(applications)]
        or epochs != tuple(sorted(set(epochs)))
        or any(
            not _valid_hash(value) or value == _ZERO_HASH
            for value in receipt.bindings.to_dict().values()
        )
        or (
            receipt.reason is not None
            and re.search(r"(?i)0x[0-9a-f]+", receipt.reason.detail) is not None
        )
        or any(
            row.sequence != index + 1
            or row.phase != ("canonical_prefix" if index == 0 else "global_suffix")
            or row.logical_index != row.column_index
            or row.schedule_epoch < 0
            or not _valid_hash(row.recurrence_descriptor_hash)
            or row.recurrence_descriptor_hash == _ZERO_HASH
            or row.logical_recurrence_launch_count != 1
            or row.legacy_jacobi_launch_count != 0
            or row.physical_slot_launch_count != 4
            or row.physical_terminal_guard_launch_count != 1
            or row.physical_launch_count != 5
            for index, row in enumerate(applications)
        )
        or receipt.application_sequence_hash
        != canonical_hash([row.to_dict() for row in applications])
        or not reason_valid
        or not reason_code_valid
        or (
            receipt.reason is not None
            and receipt.reason.code == "hip_fgmres_coarse_slot_recurrence_poisoned"
            and telemetry.application_attempt_count == 0
        )
        or (
            receipt.status in healthy_state_valid
            and not healthy_state_valid[receipt.status]
        )
        or not len(applications)
        <= telemetry.application_attempt_count
        <= expected_count
        or telemetry.application_attempt_count > len(applications) + 1
        or telemetry.application_success_count != len(applications)
        or telemetry.logical_recurrence_launch_count != len(applications)
        or telemetry.retained_jacobi_launch_count != 0
        or telemetry.canonical_application_count != min(1, len(applications))
        or telemetry.global_application_count != max(0, len(applications) - 1)
        or not 4 * len(applications)
        <= telemetry.physical_slot_launch_accept_count
        <= 4 * telemetry.application_attempt_count
        or not len(applications)
        <= telemetry.physical_terminal_guard_launch_accept_count
        <= telemetry.application_attempt_count
        or not 0
        <= telemetry.physical_slot_launch_ack_count
        <= telemetry.physical_slot_launch_accept_count
        or not 0
        <= telemetry.physical_terminal_guard_launch_ack_count
        <= telemetry.physical_terminal_guard_launch_accept_count
        or not 0 <= telemetry.parent_fence_ack_count <= 2
        or (
            telemetry.parent_fence_ack_count == 0
            and (
                telemetry.physical_slot_launch_ack_count != 0
                or telemetry.physical_terminal_guard_launch_ack_count != 0
            )
        )
        or (
            telemetry.parent_fence_ack_count == 2
            and (
                telemetry.physical_slot_launch_ack_count
                != telemetry.physical_slot_launch_accept_count
                or telemetry.physical_terminal_guard_launch_ack_count
                != telemetry.physical_terminal_guard_launch_accept_count
            )
        )
        or (
            telemetry.parent_fence_ack_count == 1
            and (
                telemetry.physical_slot_launch_ack_count
                != min(4, telemetry.physical_slot_launch_accept_count)
                or telemetry.physical_terminal_guard_launch_ack_count
                != min(
                    1,
                    telemetry.physical_terminal_guard_launch_accept_count,
                )
            )
        )
        or any(
            getattr(telemetry, name) != 0
            for name in (
                "additional_h2d_copy_count",
                "additional_d2h_copy_count",
                "additional_allocation_count",
                "additional_synchronization_count",
                "additional_csr_apply_count",
                "host_status_branch_count",
                "fallback_count",
            )
        )
        or any(
            getattr(receipt.claims, name) is not value
            for name, value in expected_claims.items()
        )
        or receipt.claims.pointer_values_serialized is not False
        or receipt.claims.actual_integrated_device_execution_proven is not False
        or receipt.claims.authoritative_numerical_parity_proven is not False
        or receipt.claims.full_iteration_host_copy_zero_proven is not False
        or receipt.claims.end_to_end_o_n_proven is not False
        or receipt.claims.speedup_proven is not False
        or receipt.claims.commercial_ready is not False
        or receipt.claims.promotion_eligible is not False
        or not _valid_hash(receipt.global_context_id)
        or not _valid_hash(receipt.global_receipt_hash)
        or (receipt.global_context_id != _ZERO_HASH) is not global_bound
        or (receipt.global_receipt_hash != _ZERO_HASH) is not global_bound
        or (global_bound and not all_rows_fenced)
        or (receipt.status == "global_receipt_bound" and not integrated)
        or (
            receipt.status in {"context_closed", "cleanup_failed"}
            and not all_accepted_launches_acknowledged
        )
        or (
            receipt.status == "context_closed"
            and receipt.reason is None
            and not (healthy_state_valid["context_ready"] or integrated)
        )
        or (
            receipt.status
            not in {"global_receipt_bound", "context_closed", "cleanup_failed"}
            and global_bound
        )
    ):
        _fail("hip_fgmres_coarse_slot_receipt_invalid", "/receipt")

    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail("hip_fgmres_coarse_slot_receipt_hash_invalid", "/receipt/hash")

    if expected_context is not None:
        from .fgmres_fixed_rank_coarse_slot_recurrence_v1 import (
            HipFgmresFixedRankCoarseSlotRecurrenceV1,
        )

        if type(expected_context) is not HipFgmresFixedRankCoarseSlotRecurrenceV1:
            _fail("hip_fgmres_coarse_slot_receipt_context_invalid", "/receipt")
        with expected_context._lock:
            if (
                receipt.context_id != expected_context._context_id
                or receipt.status != expected_context._state
                or receipt.actual_backend != expected_context._actual_backend
                or receipt.bindings is not expected_context._bindings
                or receipt.dimensions is not expected_context._dimensions
                or receipt.applications != tuple(expected_context._applications)
                or receipt.receipt_hash
                != expected_context._build_receipt(expected_context._state).receipt_hash
                or telemetry.physical_slot_launch_accept_count
                != sum(expected_context._accepted_by_phase.values())
                or telemetry.physical_slot_launch_ack_count
                != sum(expected_context._acknowledged_by_phase.values())
                or telemetry.physical_terminal_guard_launch_accept_count
                != sum(expected_context._guard_accepted_by_phase.values())
                or telemetry.physical_terminal_guard_launch_ack_count
                != sum(expected_context._guard_acknowledged_by_phase.values())
                or (
                    telemetry.physical_slot_launch_accept_count
                    > telemetry.physical_slot_launch_ack_count
                    and not expected_context._require_slot_kernel().pending
                )
                or (
                    telemetry.physical_terminal_guard_launch_accept_count
                    > telemetry.physical_terminal_guard_launch_ack_count
                    and not expected_context._require_terminal_guard_kernel().pending
                )
            ):
                _fail("hip_fgmres_coarse_slot_receipt_context_invalid", "/receipt")
    return receipt


def _context_id_for(
    bindings: HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1,
    dimensions: HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1,
    actual_backend: Literal["hip", "test_double"],
) -> str:
    return canonical_hash(
        {
            "profile": (
                HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_CAPABILITY_PROFILE
            ),
            "actual_backend": actual_backend,
            "bindings": bindings.to_dict(),
            "dimensions": dimensions.to_dict(),
        }
    )


def _receipt_payload(
    receipt: HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "applications": [row.to_dict() for row in receipt.applications],
        "application_sequence_hash": receipt.application_sequence_hash,
        "global_context_id": receipt.global_context_id,
        "global_receipt_hash": receipt.global_receipt_hash,
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(raw)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_hash(value: object) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _redact(value: object) -> str:
    text = str(value).strip().replace("\n", " ")
    return re.sub(r"(?i)0x[0-9a-f]+", "<redacted>", text)[:512]


def _fail(code: str, path: str, detail: str = "") -> NoReturn:
    raise HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error(code, path, detail)


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_CAPABILITY_PROFILE",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_EVIDENCE_SCOPE",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION",
    "HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1",
    "HipFgmresFixedRankCoarseSlotRecurrencePhaseV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceReasonV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error",
    "HipFgmresFixedRankCoarseSlotRecurrenceStatusV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1",
    "validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1",
]
