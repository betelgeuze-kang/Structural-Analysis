"""Bind exact gfx1030 family parity, transfer, and RTC ordinal authorities.

This additive contract does not run a solver, export a completion buffer, or
invoke a native API.  It replays the retained model-family host-transfer
composition and ten retained launch/fence audit contexts, then binds their
common lineage into one process-local receipt.  The serialized receipt remains
unsigned, non-promoting, and is not standalone provenance authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_canonical_predecessor_v1 import _OWNED_ROLES
from .fgmres_context_v2 import (
    HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2,
    HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from .fgmres_fixture_registry_v1 import load_hip_fgmres_fixture_registry_v1
from .fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from .fgmres_iteration_host_transfer_audit_v1 import (
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1,
)
from .fgmres_model_family_host_transfer_audit_v1 import (
    HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1,
    HipFgmresModelFamilyHostTransferAuditResultV1,
    validate_hip_fgmres_model_family_host_transfer_audit_result_v1,
)
from .fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2,
)
from .fgmres_recurrence_launch_fence_audit_v1 import (
    HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1,
    HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1,
    HipFgmresRecurrenceLaunchFenceAuditResultV1,
    validate_hip_fgmres_recurrence_launch_fence_audit_result_v1,
)
from .fgmres_recurrence_plan_v2 import hip_fgmres_recurrence_kernel_abi_payload_v2
from .fgmres_rtc_launch_fence_ledger_v1 import (
    _fence_descriptor_hash_v1,
    _launch_descriptor_hash_v1,
    _memset_descriptor_hash_v1,
)
from .fgmres_rtc_v2 import (
    canonical_first_column_predecessor_launches_v2,
    first_column_checkpoint_transaction_launches_v2,
)


HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-model-family-audited-parity.v2"
)
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2 = (
    "phase0_exact_gfx1030_family_parity_transfer_and_launch_fence_audit_composition"
)
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_EVIDENCE_SCOPE_V2 = (
    "process_local_registry_bound_gfx1030_fixed_suite_retained_parity_"
    "transfer_and_launch_fence_authorities_unsigned_non_promoting"
)
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_STATUS_V2 = (
    "exact_gfx1030_ten_slot_parity_transfer_and_launch_fence_audits_composed"
)
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_ARCHITECTURE_V2 = "gfx1030"
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2 = (
    HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
)
HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_TOTAL_EXPORT_BYTES_V2 = 4408

_SCHEMA_RESOURCE = "hip_fgmres_model_family_audited_parity_v2.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class HipFgmresModelFamilyAuditedParityV2Error(RuntimeError):
    """Stable fail-closed retained-authority composition error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyAuditedParityBindingsV2:
    registry_bytes_sha256: str
    registry_hash: str
    source_transfer_audit_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-family-host-transfer-audit.v1"
    ]
    source_transfer_audit_receipt_hash: str
    source_family_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-family-parity.v2"
    ]
    source_family_receipt_hash: str
    ordinal_audit_schema_version: Literal[
        "structural-analysis-hip-fgmres-recurrence-launch-fence-audit.v1"
    ]
    required_architecture_base: Literal["gfx1030"]
    required_slot_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name != "required_slot_ids"
            },
            "required_slot_ids": list(self.required_slot_ids),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyAuditedParityObservationV2:
    slot_id: str
    logical_case_key: str
    matrix_cell_id: str
    source_pair_binding_hash: str
    case_receipt_hash: str
    transfer_context_id: str
    transfer_receipt_hash: str
    ordinal_context_id: str
    ordinal_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    canonical_context_id: str
    canonical_open_receipt_hash: str
    canonical_fenced_receipt_hash: str
    sealed_checkpoint_context_id: str
    sealed_checkpoint_receipt_hash: str
    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    canonical_schedule_hash: str
    checkpoint_schedule_hash: str
    global_full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    program_descriptor_hash: str
    runtime_architecture_base: Literal["gfx1030"]
    compiled_architecture: Literal["gfx1030"]
    device_ordinal: int
    device_identity_receipt_hash: str
    runtime_library_sha256: str
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    runtime_scope: Literal["exact_engine_v2_bound_context_runtime_only"]
    native_loader_bound_runtime: Literal[True]
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_stage_count: int
    recurrence_program_copy_attempt_count: Literal[0]
    completion_export_blocking_d2h_attempt_count: Literal[3]
    completion_export_blocking_d2h_success_count: Literal[3]
    completion_export_blocking_d2h_failure_count: Literal[0]
    completion_export_byte_count: int
    ordinal_memset_attempt_count: Literal[8]
    ordinal_memset_success_count: Literal[8]
    ordinal_memset_rejected_count: Literal[0]
    ordinal_memset_ambiguous_count: Literal[0]
    ordinal_memset_in_flight_count: Literal[0]
    ordinal_launch_attempt_count: int
    ordinal_launch_success_count: int
    ordinal_launch_rejected_count: Literal[0]
    ordinal_launch_ambiguous_count: Literal[0]
    ordinal_launch_in_flight_count: Literal[0]
    ordinal_fence_attempt_count: Literal[3]
    ordinal_fence_success_count: Literal[3]
    ordinal_fence_rejected_count: Literal[0]
    ordinal_fence_ambiguous_count: Literal[0]
    ordinal_fence_in_flight_count: Literal[0]
    ordinal_operation_delta: int
    ordinal_event_delta: int
    ordinal_total_native_call_count: int
    triple_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyAuditedParityTotalsV2:
    required_slot_count: Literal[10]
    paired_slot_count: Literal[10]
    source_family_expected_matrix_cell_count: Literal[20]
    source_family_covered_matrix_cell_count: Literal[10]
    source_family_missing_matrix_cell_count: Literal[10]
    audited_gfx1030_slot_count: Literal[10]
    audited_gfx1100_slot_count: Literal[0]
    recurrence_program_copy_attempt_count: Literal[0]
    completion_export_blocking_d2h_attempt_count: Literal[30]
    completion_export_blocking_d2h_success_count: Literal[30]
    completion_export_blocking_d2h_failure_count: Literal[0]
    completion_export_byte_count: Literal[4408]
    ordinal_memset_attempt_count: Literal[80]
    ordinal_memset_success_count: Literal[80]
    ordinal_memset_rejected_count: Literal[0]
    ordinal_memset_ambiguous_count: Literal[0]
    ordinal_memset_in_flight_count: Literal[0]
    ordinal_launch_attempt_count: int
    ordinal_launch_success_count: int
    ordinal_launch_rejected_count: Literal[0]
    ordinal_launch_ambiguous_count: Literal[0]
    ordinal_launch_in_flight_count: Literal[0]
    ordinal_fence_attempt_count: Literal[30]
    ordinal_fence_success_count: Literal[30]
    ordinal_fence_rejected_count: Literal[0]
    ordinal_fence_ambiguous_count: Literal[0]
    ordinal_fence_in_flight_count: Literal[0]
    ordinal_operation_delta: int
    ordinal_event_delta: int
    ordinal_total_native_call_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyAuditedParityClaimsV2:
    three_retained_authority_families_replayed: Literal[True]
    fixed_package_registry_and_source_receipts_bound: Literal[True]
    exact_gfx1030_registered_ten_slot_coverage_bound: Literal[True]
    case_transfer_export_identity_replayed: Literal[True]
    transfer_and_ordinal_lineage_cross_bound: Literal[True]
    per_slot_bound_runtime_recurrence_copy_attempt_zero: Literal[True]
    per_slot_post_fence_exact_three_blocking_d2h: Literal[True]
    per_slot_fixed_recurrence_descriptor_order_replayed: Literal[True]
    composition_factory_reuses_retained_authorities_only: Literal[True]
    external_gfx1100_fixed_suite_audited: Literal[False] = False
    unsigned_two_architecture_fixed_suite_audited: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    pre_window_dma_or_setup_teardown_transfer_zero_proven: Literal[False] = False
    raw_fresh_or_third_party_native_calls_observed: Literal[False] = False
    whole_process_additional_solve_or_export_absence_proven: Literal[False] = False
    same_runtime_or_stream_shared_across_all_cases_proven: Literal[False] = False
    device_kernel_semantic_execution_proven: Literal[False] = False
    device_content_or_numerical_outcome_proven_by_ordinal: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    full_model_family_parity_verified: Literal[False] = False
    multiarchitecture_parity_verified: Literal[False] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    hostile_same_process_mutation_or_interposition_resistance: Literal[False] = False
    signed_evidence: Literal[False] = False
    persistent_external_log_verified: Literal[False] = False
    result_ir_verified: Literal[False] = False
    reaction_recovery_or_energy_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyAuditedParityReceiptV2:
    status: Literal[
        "exact_gfx1030_ten_slot_parity_transfer_and_launch_fence_audits_composed"
    ]
    attestation_id: str
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresModelFamilyAuditedParityBindingsV2
    observations: tuple[HipFgmresModelFamilyAuditedParityObservationV2, ...]
    totals: HipFgmresModelFamilyAuditedParityTotalsV2
    claims: HipFgmresModelFamilyAuditedParityClaimsV2
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresModelFamilyOrdinalAuthorityV2:
    context: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1
    result: HipFgmresRecurrenceLaunchFenceAuditResultV1


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelFamilyAuditedParityResultV2:
    receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    _transfer_composition_result: HipFgmresModelFamilyHostTransferAuditResultV1 = field(
        repr=False, compare=False
    )
    _ordinal_authorities: tuple[_HipFgmresModelFamilyOrdinalAuthorityV2, ...] = field(
        repr=False, compare=False
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_audited_parity_result_v2(self)
        return self.receipt.to_dict()


def attest_hip_fgmres_model_family_audited_parity_v2(
    transfer_composition_result: HipFgmresModelFamilyHostTransferAuditResultV1,
    ordinal_contexts: tuple[HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1, ...],
) -> HipFgmresModelFamilyAuditedParityResultV2:
    """Compose retained authorities without solving, exporting, or native calls."""

    _validate_transfer_composition(transfer_composition_result)
    authorities = _capture_ordinal_authorities(ordinal_contexts)
    receipt = _evaluate(transfer_composition_result, authorities)
    result = HipFgmresModelFamilyAuditedParityResultV2(
        receipt=receipt,
        _transfer_composition_result=transfer_composition_result,
        _ordinal_authorities=authorities,
    )
    return validate_hip_fgmres_model_family_audited_parity_result_v2(
        result,
        expected_transfer_composition_result=transfer_composition_result,
        expected_ordinal_contexts=ordinal_contexts,
    )


def validate_hip_fgmres_model_family_audited_parity_result_v2(
    result: HipFgmresModelFamilyAuditedParityResultV2,
    *,
    expected_transfer_composition_result: (
        HipFgmresModelFamilyHostTransferAuditResultV1 | None
    ) = None,
    expected_ordinal_contexts: tuple[
        HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1, ...
    ]
    | None = None,
) -> HipFgmresModelFamilyAuditedParityResultV2:
    """Replay the retained transfer composition and every ordinal context."""

    if type(result) is not HipFgmresModelFamilyAuditedParityResultV2:
        _fail("hip_fgmres_family_audited_parity_result_type_invalid", "/result")
    if (
        type(result._transfer_composition_result)
        is not HipFgmresModelFamilyHostTransferAuditResultV1
    ):
        _fail("hip_fgmres_family_audited_parity_source_type_invalid", "/source")
    if (
        expected_transfer_composition_result is not None
        and result._transfer_composition_result
        is not expected_transfer_composition_result
    ):
        _fail("hip_fgmres_family_audited_parity_source_changed", "/source")
    if type(result._ordinal_authorities) is not tuple or any(
        type(row) is not _HipFgmresModelFamilyOrdinalAuthorityV2
        for row in result._ordinal_authorities
    ):
        _fail(
            "hip_fgmres_family_audited_parity_authority_container_invalid",
            "/ordinals",
        )
    if expected_ordinal_contexts is not None:
        if type(expected_ordinal_contexts) is not tuple or len(
            expected_ordinal_contexts
        ) != len(result._ordinal_authorities):
            _fail(
                "hip_fgmres_family_audited_parity_expected_contexts_changed",
                "/ordinals",
            )
        if any(
            authority.context is not context
            for authority, context in zip(
                result._ordinal_authorities,
                expected_ordinal_contexts,
                strict=True,
            )
        ):
            _fail(
                "hip_fgmres_family_audited_parity_expected_contexts_changed",
                "/ordinals",
            )
    _validate_transfer_composition(result._transfer_composition_result)
    for index, authority in enumerate(result._ordinal_authorities):
        _validate_ordinal_authority(authority, path=f"/ordinals/{index}")
    expected = _evaluate(
        result._transfer_composition_result,
        result._ordinal_authorities,
    )
    if result.receipt != expected:
        _fail(
            "hip_fgmres_family_audited_parity_result_replay_mismatch",
            "/receipt",
        )
    validate_hip_fgmres_model_family_audited_parity_receipt_v2(result.receipt)
    return result


def validate_hip_fgmres_model_family_audited_parity_receipt_v2(
    receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
) -> HipFgmresModelFamilyAuditedParityReceiptV2:
    """Validate detached structure without granting retained authority."""

    _validate_exact_types(receipt)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: tuple(str(part) for part in row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail(
            "hip_fgmres_family_audited_parity_schema_invalid",
            path or "/",
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_family_audited_parity_receipt_hash_invalid",
            "/receipt_hash",
        )
    _validate_receipt_semantics(receipt)
    return receipt


def _capture_ordinal_authorities(
    contexts: tuple[HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1, ...],
) -> tuple[_HipFgmresModelFamilyOrdinalAuthorityV2, ...]:
    if type(contexts) is not tuple:
        _fail(
            "hip_fgmres_family_audited_parity_context_container_invalid",
            "/ordinals",
        )
    if len(contexts) != len(
        HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    ):
        _fail(
            "hip_fgmres_family_audited_parity_context_count_invalid",
            "/ordinals",
        )
    if len({id(context) for context in contexts}) != len(contexts):
        _fail(
            "hip_fgmres_family_audited_parity_duplicate_context",
            "/ordinals",
        )
    authorities: list[_HipFgmresModelFamilyOrdinalAuthorityV2] = []
    for index, context in enumerate(contexts):
        if type(context) is not HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1:
            _fail(
                "hip_fgmres_family_audited_parity_context_type_invalid",
                f"/ordinals/{index}",
            )
        result = context.result
        if result is None:
            _fail(
                "hip_fgmres_family_audited_parity_context_not_sealed",
                f"/ordinals/{index}",
            )
        authority = _HipFgmresModelFamilyOrdinalAuthorityV2(context, result)
        _validate_ordinal_authority(authority, path=f"/ordinals/{index}")
        authorities.append(authority)
    return tuple(authorities)


def _validate_transfer_composition(
    result: HipFgmresModelFamilyHostTransferAuditResultV1,
) -> None:
    if type(result) is not HipFgmresModelFamilyHostTransferAuditResultV1:
        _fail("hip_fgmres_family_audited_parity_source_type_invalid", "/source")
    try:
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(result)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_audited_parity_source_invalid",
            "/source",
            f"{type(exc).__name__}: {exc}",
        )


def _validate_ordinal_authority(
    authority: _HipFgmresModelFamilyOrdinalAuthorityV2,
    *,
    path: str,
) -> None:
    if type(authority.result) is not HipFgmresRecurrenceLaunchFenceAuditResultV1:
        _fail(
            "hip_fgmres_family_audited_parity_ordinal_result_type_invalid",
            path,
        )
    try:
        validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
            authority.result,
            expected_context=authority.context,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_family_audited_parity_ordinal_authority_invalid",
            path,
            f"{type(exc).__name__}: {exc}",
        )


def _evaluate(
    source: HipFgmresModelFamilyHostTransferAuditResultV1,
    ordinal_authorities: tuple[_HipFgmresModelFamilyOrdinalAuthorityV2, ...],
) -> HipFgmresModelFamilyAuditedParityReceiptV2:
    source_receipt = source.receipt
    family_receipt = source._family_result.receipt
    registry = load_hip_fgmres_fixture_registry_v1()
    if (
        source_receipt.schema_version
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1
        or family_receipt.schema_version
        != HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2
        or source_receipt.bindings.source_family_receipt_hash
        != family_receipt.receipt_hash
        or source_receipt.bindings.registry_bytes_sha256
        != registry.registry_bytes_sha256
        or source_receipt.bindings.registry_hash != registry.registry_hash
        or source_receipt.bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
        or len(source_receipt.observations) != 10
        or len(source._audit_authorities) != 10
        or len(ordinal_authorities) != 10
    ):
        _fail(
            "hip_fgmres_family_audited_parity_source_scope_invalid",
            "/source",
        )

    source_by_global = {
        row.global_context_id: row for row in source_receipt.observations
    }
    if len(source_by_global) != 10:
        _fail(
            "hip_fgmres_family_audited_parity_source_duplicate_global",
            "/source/observations",
        )
    transfer_by_hash = {
        row.result.receipt.receipt_hash: row for row in source._audit_authorities
    }
    if len(transfer_by_hash) != 10:
        _fail(
            "hip_fgmres_family_audited_parity_source_duplicate_transfer",
            "/source/audits",
        )

    observations_by_slot: dict[str, HipFgmresModelFamilyAuditedParityObservationV2] = {}
    ordinal_context_ids: set[str] = set()
    ordinal_receipt_hashes: set[str] = set()
    for index, authority in enumerate(ordinal_authorities):
        _validate_ordinal_authority(authority, path=f"/ordinals/{index}")
        ordinal = authority.result.receipt
        ordinal_bindings = ordinal.bindings
        source_row = source_by_global.pop(ordinal_bindings.global_context_id, None)
        if source_row is None:
            _fail(
                "hip_fgmres_family_audited_parity_global_join_invalid",
                f"/ordinals/{index}",
            )
        transfer_authority = transfer_by_hash.pop(
            source_row.audit_receipt_hash,
            None,
        )
        if transfer_authority is None:
            _fail(
                "hip_fgmres_family_audited_parity_transfer_join_invalid",
                f"/ordinals/{index}",
            )
        transfer = transfer_authority.result.receipt
        transfer_bindings = transfer.bindings
        transfer_dimensions = transfer.dimensions
        ordinal_dimensions = ordinal.dimensions
        common_binding_names = (
            "canonical_context_id",
            "canonical_open_receipt_hash",
            "canonical_fenced_receipt_hash",
            "sealed_checkpoint_context_id",
            "sealed_checkpoint_receipt_hash",
            "global_context_id",
            "global_receipt_hash",
            "completion_receipt_hash",
            "recurrence_plan_hash",
            "recurrence_kernel_abi_hash",
            "combined_recurrence_abi_hash",
            "kernel_identity_hash",
            "kernel_source_sha256",
            "global_full_schedule_hash",
            "sealed_prefix_schedule_hash",
            "continuation_schedule_hash",
            "direct_generation_binding_hash",
            "physical_projection_hash",
            "architecture",
            "device_ordinal",
        )
        if (
            ordinal.actual_backend != "hip"
            or transfer_authority.context._canonical is not authority.context._canonical
            or transfer_authority.context._global_context
            is not authority.context._global_context
            or transfer_authority.context._completion_capability
            is not authority.context._completion_capability
            or any(
                getattr(transfer_bindings, name) != getattr(ordinal_bindings, name)
                for name in common_binding_names
            )
            or transfer_bindings.completion_export_context_id
            != source_row.completion_export_context_id
            or transfer_bindings.completion_export_receipt_hash
            != source_row.completion_export_receipt_hash
            or transfer_bindings.completion_export_payload_hash
            != source_row.completion_export_payload_hash
            or transfer_dimensions.free_dof_count != ordinal_dimensions.free_dof_count
            or transfer_dimensions.maximum_restart_count
            != ordinal_dimensions.maximum_restart_count
            or transfer_dimensions.full_program_launch_count
            != ordinal_dimensions.full_program_launch_count
            or source_row.recurrence_plan_hash != ordinal_bindings.recurrence_plan_hash
            or source_row.kernel_identity_hash != ordinal_bindings.kernel_identity_hash
            or source_row.kernel_source_sha256 != ordinal_bindings.kernel_source_sha256
            or source_row.compiled_architecture != ordinal_bindings.architecture
            or source_row.device_ordinal != ordinal_bindings.device_ordinal
            or source_row.free_dof_count != ordinal_dimensions.free_dof_count
            or source_row.maximum_restart_count
            != ordinal_dimensions.maximum_restart_count
        ):
            _fail(
                "hip_fgmres_family_audited_parity_lineage_binding_mismatch",
                f"/ordinals/{index}",
            )
        if (
            ordinal.context_id in ordinal_context_ids
            or ordinal.receipt_hash in ordinal_receipt_hashes
            or source_row.slot_id in observations_by_slot
        ):
            _fail(
                "hip_fgmres_family_audited_parity_duplicate_authority",
                f"/ordinals/{index}",
            )
        ordinal_context_ids.add(ordinal.context_id)
        ordinal_receipt_hashes.add(ordinal.receipt_hash)

        recurrence = transfer.window.recurrence_program
        recurrence_attempts = sum(
            row.attempt_count
            for row in (
                recurrence.h2d_async,
                recurrence.d2h_async,
                recurrence.d2h_blocking,
            )
        )
        export = transfer.window.completion_export.d2h_blocking
        telemetry = ordinal.telemetry
        draft = HipFgmresModelFamilyAuditedParityObservationV2(
            slot_id=source_row.slot_id,
            logical_case_key=source_row.logical_case_key,
            matrix_cell_id=source_row.matrix_cell_id,
            source_pair_binding_hash=source_row.pair_binding_hash,
            case_receipt_hash=source_row.case_receipt_hash,
            transfer_context_id=transfer.context_id,
            transfer_receipt_hash=transfer.receipt_hash,
            ordinal_context_id=ordinal.context_id,
            ordinal_receipt_hash=ordinal.receipt_hash,
            completion_export_context_id=(
                transfer_bindings.completion_export_context_id
            ),
            completion_export_receipt_hash=(
                transfer_bindings.completion_export_receipt_hash
            ),
            completion_export_payload_hash=(
                transfer_bindings.completion_export_payload_hash
            ),
            canonical_context_id=ordinal_bindings.canonical_context_id,
            canonical_open_receipt_hash=(ordinal_bindings.canonical_open_receipt_hash),
            canonical_fenced_receipt_hash=(
                ordinal_bindings.canonical_fenced_receipt_hash
            ),
            sealed_checkpoint_context_id=(
                ordinal_bindings.sealed_checkpoint_context_id
            ),
            sealed_checkpoint_receipt_hash=(
                ordinal_bindings.sealed_checkpoint_receipt_hash
            ),
            global_context_id=ordinal_bindings.global_context_id,
            global_receipt_hash=ordinal_bindings.global_receipt_hash,
            completion_receipt_hash=ordinal_bindings.completion_receipt_hash,
            recurrence_plan_hash=ordinal_bindings.recurrence_plan_hash,
            recurrence_kernel_abi_hash=(ordinal_bindings.recurrence_kernel_abi_hash),
            combined_recurrence_abi_hash=(
                ordinal_bindings.combined_recurrence_abi_hash
            ),
            kernel_identity_hash=ordinal_bindings.kernel_identity_hash,
            kernel_source_sha256=ordinal_bindings.kernel_source_sha256,
            canonical_schedule_hash=ordinal_bindings.canonical_schedule_hash,
            checkpoint_schedule_hash=ordinal_bindings.checkpoint_schedule_hash,
            global_full_schedule_hash=(ordinal_bindings.global_full_schedule_hash),
            sealed_prefix_schedule_hash=(ordinal_bindings.sealed_prefix_schedule_hash),
            continuation_schedule_hash=(ordinal_bindings.continuation_schedule_hash),
            direct_generation_binding_hash=(
                ordinal_bindings.direct_generation_binding_hash
            ),
            physical_projection_hash=(ordinal_bindings.physical_projection_hash),
            program_descriptor_hash=ordinal_bindings.program_descriptor_hash,
            runtime_architecture_base=source_row.runtime_architecture_base,
            compiled_architecture=source_row.compiled_architecture,
            device_ordinal=source_row.device_ordinal,
            device_identity_receipt_hash=(source_row.device_identity_receipt_hash),
            runtime_library_sha256=source_row.runtime_library_sha256,
            device_uuid_bytes_hex=source_row.device_uuid_bytes_hex,
            device_pci_bdf=source_row.device_pci_bdf,
            runtime_scope=source_row.runtime_scope,
            native_loader_bound_runtime=source_row.native_loader_bound_runtime,
            free_dof_count=ordinal_dimensions.free_dof_count,
            restart_dimension=ordinal_dimensions.restart_dimension,
            max_iterations=ordinal_dimensions.max_iterations,
            maximum_restart_count=ordinal_dimensions.maximum_restart_count,
            reduction_stage_count=ordinal_dimensions.reduction_stage_count,
            recurrence_program_copy_attempt_count=recurrence_attempts,
            completion_export_blocking_d2h_attempt_count=export.attempt_count,
            completion_export_blocking_d2h_success_count=export.success_count,
            completion_export_blocking_d2h_failure_count=export.failure_count,
            completion_export_byte_count=transfer_dimensions.total_export_byte_count,
            ordinal_memset_attempt_count=telemetry.memset.attempt_count,
            ordinal_memset_success_count=telemetry.memset.success_count,
            ordinal_memset_rejected_count=telemetry.memset.rejected_count,
            ordinal_memset_ambiguous_count=telemetry.memset.ambiguous_count,
            ordinal_memset_in_flight_count=telemetry.memset.in_flight_count,
            ordinal_launch_attempt_count=telemetry.launch.attempt_count,
            ordinal_launch_success_count=telemetry.launch.success_count,
            ordinal_launch_rejected_count=telemetry.launch.rejected_count,
            ordinal_launch_ambiguous_count=telemetry.launch.ambiguous_count,
            ordinal_launch_in_flight_count=telemetry.launch.in_flight_count,
            ordinal_fence_attempt_count=telemetry.fence.attempt_count,
            ordinal_fence_success_count=telemetry.fence.success_count,
            ordinal_fence_rejected_count=telemetry.fence.rejected_count,
            ordinal_fence_ambiguous_count=telemetry.fence.ambiguous_count,
            ordinal_fence_in_flight_count=telemetry.fence.in_flight_count,
            ordinal_operation_delta=telemetry.operation_ordinal_delta,
            ordinal_event_delta=telemetry.event_sequence_delta,
            ordinal_total_native_call_count=(
                ordinal_dimensions.total_native_call_count
            ),
            triple_binding_hash=_ZERO_HASH,
        )
        observation = replace(
            draft,
            triple_binding_hash=canonical_hash(
                _observation_payload(draft, include_triple_hash=False)
            ),
        )
        observations_by_slot[source_row.slot_id] = observation

    if source_by_global or transfer_by_hash or len(observations_by_slot) != 10:
        _fail(
            "hip_fgmres_family_audited_parity_authority_set_mismatch",
            "/sources",
        )
    ordered = tuple(
        observations_by_slot[slot_id]
        for slot_id in HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    )
    source_totals = source_receipt.totals
    bindings = HipFgmresModelFamilyAuditedParityBindingsV2(
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        source_transfer_audit_schema_version=source_receipt.schema_version,
        source_transfer_audit_receipt_hash=source_receipt.receipt_hash,
        source_family_schema_version=family_receipt.schema_version,
        source_family_receipt_hash=family_receipt.receipt_hash,
        ordinal_audit_schema_version=(
            HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1
        ),
        required_architecture_base=(
            HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_ARCHITECTURE_V2
        ),
        required_slot_ids=(HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2),
    )
    totals = _totals_from_observations(ordered, source_totals)
    claims = _expected_claims()
    attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
            ),
            "registry_hash": registry.registry_hash,
            "source_transfer_audit_receipt_hash": source_receipt.receipt_hash,
            "source_family_receipt_hash": family_receipt.receipt_hash,
            "triple_binding_hashes": [row.triple_binding_hash for row in ordered],
        }
    )
    draft_receipt = HipFgmresModelFamilyAuditedParityReceiptV2(
        status=HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_STATUS_V2,
        attestation_id=attestation_id,
        evidence_scope=HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_EVIDENCE_SCOPE_V2,
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        observations=ordered,
        totals=totals,
        claims=claims,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft_receipt,
        receipt_hash=canonical_hash(
            _receipt_payload(draft_receipt, include_hash=False)
        ),
    )
    return validate_hip_fgmres_model_family_audited_parity_receipt_v2(receipt)


def _totals_from_observations(
    rows: tuple[HipFgmresModelFamilyAuditedParityObservationV2, ...],
    source_totals: Any,
) -> HipFgmresModelFamilyAuditedParityTotalsV2:
    return HipFgmresModelFamilyAuditedParityTotalsV2(
        required_slot_count=10,
        paired_slot_count=10,
        source_family_expected_matrix_cell_count=(
            source_totals.source_family_expected_matrix_cell_count
        ),
        source_family_covered_matrix_cell_count=(
            source_totals.source_family_covered_matrix_cell_count
        ),
        source_family_missing_matrix_cell_count=(
            source_totals.source_family_missing_matrix_cell_count
        ),
        audited_gfx1030_slot_count=10,
        audited_gfx1100_slot_count=0,
        recurrence_program_copy_attempt_count=sum(
            row.recurrence_program_copy_attempt_count for row in rows
        ),
        completion_export_blocking_d2h_attempt_count=sum(
            row.completion_export_blocking_d2h_attempt_count for row in rows
        ),
        completion_export_blocking_d2h_success_count=sum(
            row.completion_export_blocking_d2h_success_count for row in rows
        ),
        completion_export_blocking_d2h_failure_count=sum(
            row.completion_export_blocking_d2h_failure_count for row in rows
        ),
        completion_export_byte_count=sum(
            row.completion_export_byte_count for row in rows
        ),
        ordinal_memset_attempt_count=sum(
            row.ordinal_memset_attempt_count for row in rows
        ),
        ordinal_memset_success_count=sum(
            row.ordinal_memset_success_count for row in rows
        ),
        ordinal_memset_rejected_count=sum(
            row.ordinal_memset_rejected_count for row in rows
        ),
        ordinal_memset_ambiguous_count=sum(
            row.ordinal_memset_ambiguous_count for row in rows
        ),
        ordinal_memset_in_flight_count=sum(
            row.ordinal_memset_in_flight_count for row in rows
        ),
        ordinal_launch_attempt_count=sum(
            row.ordinal_launch_attempt_count for row in rows
        ),
        ordinal_launch_success_count=sum(
            row.ordinal_launch_success_count for row in rows
        ),
        ordinal_launch_rejected_count=sum(
            row.ordinal_launch_rejected_count for row in rows
        ),
        ordinal_launch_ambiguous_count=sum(
            row.ordinal_launch_ambiguous_count for row in rows
        ),
        ordinal_launch_in_flight_count=sum(
            row.ordinal_launch_in_flight_count for row in rows
        ),
        ordinal_fence_attempt_count=sum(
            row.ordinal_fence_attempt_count for row in rows
        ),
        ordinal_fence_success_count=sum(
            row.ordinal_fence_success_count for row in rows
        ),
        ordinal_fence_rejected_count=sum(
            row.ordinal_fence_rejected_count for row in rows
        ),
        ordinal_fence_ambiguous_count=sum(
            row.ordinal_fence_ambiguous_count for row in rows
        ),
        ordinal_fence_in_flight_count=sum(
            row.ordinal_fence_in_flight_count for row in rows
        ),
        ordinal_operation_delta=sum(row.ordinal_operation_delta for row in rows),
        ordinal_event_delta=sum(row.ordinal_event_delta for row in rows),
        ordinal_total_native_call_count=sum(
            row.ordinal_total_native_call_count for row in rows
        ),
    )


def _expected_claims() -> HipFgmresModelFamilyAuditedParityClaimsV2:
    return HipFgmresModelFamilyAuditedParityClaimsV2(
        three_retained_authority_families_replayed=True,
        fixed_package_registry_and_source_receipts_bound=True,
        exact_gfx1030_registered_ten_slot_coverage_bound=True,
        case_transfer_export_identity_replayed=True,
        transfer_and_ordinal_lineage_cross_bound=True,
        per_slot_bound_runtime_recurrence_copy_attempt_zero=True,
        per_slot_post_fence_exact_three_blocking_d2h=True,
        per_slot_fixed_recurrence_descriptor_order_replayed=True,
        composition_factory_reuses_retained_authorities_only=True,
    )


def _validate_exact_types(
    receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
) -> None:
    if (
        type(receipt) is not HipFgmresModelFamilyAuditedParityReceiptV2
        or type(receipt.bindings) is not HipFgmresModelFamilyAuditedParityBindingsV2
        or type(receipt.observations) is not tuple
        or any(
            type(row) is not HipFgmresModelFamilyAuditedParityObservationV2
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresModelFamilyAuditedParityTotalsV2
        or type(receipt.claims) is not HipFgmresModelFamilyAuditedParityClaimsV2
    ):
        _fail("hip_fgmres_family_audited_parity_type_invalid", "/receipt")
    _require_exact_json_types(_receipt_payload(receipt, include_hash=True), "/")


def _require_exact_json_types(value: Any, path: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail("hip_fgmres_family_audited_parity_type_invalid", path)
            _require_exact_json_types(item, f"{path}/{key}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _require_exact_json_types(item, f"{path}/{index}")
        return
    if type(value) not in {str, int, bool, type(None)}:
        _fail("hip_fgmres_family_audited_parity_type_invalid", path)


def _fixed_package_slot_semantics(
    slot: Any,
    schedule: Any,
) -> dict[str, str]:
    plan = slot.recurrence_plan
    canonical_rows = canonical_first_column_predecessor_launches_v2(
        plan.free_dof_count,
        plan.restart_dimension,
    )
    checkpoint_rows = first_column_checkpoint_transaction_launches_v2(
        plan.free_dof_count,
        plan.restart_dimension,
    )
    canonical_descriptors = tuple(
        _launch_descriptor_hash_v1(row) for row in canonical_rows
    )
    checkpoint_descriptors = tuple(
        _launch_descriptor_hash_v1(row) for row in checkpoint_rows
    )
    continuation_descriptors = tuple(
        _launch_descriptor_hash_v1(row) for row in schedule.continuation.launches
    )
    full_descriptors = tuple(
        _launch_descriptor_hash_v1(row) for row in schedule.full.launches
    )
    if (
        canonical_descriptors + checkpoint_descriptors + continuation_descriptors
        != full_descriptors
    ):
        _fail(
            "hip_fgmres_family_audited_parity_package_schedule_invalid",
            f"/registry/{slot.slot_id}",
        )
    memset_descriptors = tuple(
        _memset_descriptor_hash_v1(role, plan.buffer(role).byte_length)
        for role in _OWNED_ROLES
    )
    fence = _fence_descriptor_hash_v1()
    operations = (
        tuple(("memset", value) for value in memset_descriptors)
        + tuple(("launch", value) for value in canonical_descriptors)
        + (("fence", fence),)
        + tuple(("launch", value) for value in checkpoint_descriptors)
        + (("fence", fence),)
        + tuple(("launch", value) for value in continuation_descriptors)
        + (("fence", fence),)
    )
    return {
        "recurrence_kernel_abi_hash": canonical_hash(
            hip_fgmres_recurrence_kernel_abi_payload_v2()
        ),
        "combined_recurrence_abi_hash": (HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2),
        "kernel_source_sha256": HIP_FGMRES_RTC_SOURCE_SHA256_V2,
        "canonical_schedule_hash": canonical_hash(
            [asdict(row) for row in canonical_rows]
        ),
        "checkpoint_schedule_hash": (
            HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
        ),
        "program_descriptor_hash": canonical_hash(
            [
                {"kind": kind, "descriptor_hash": descriptor_hash}
                for kind, descriptor_hash in operations
            ]
        ),
    }


def _validate_receipt_semantics(
    receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
) -> None:
    registry = load_hip_fgmres_fixture_registry_v1()
    bindings = receipt.bindings
    rows = receipt.observations
    if (
        receipt.status != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_STATUS_V2
        or receipt.evidence_scope
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_EVIDENCE_SCOPE_V2
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_transfer_audit_schema_version
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1
        or bindings.source_family_schema_version
        != HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2
        or bindings.ordinal_audit_schema_version
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1
        or bindings.required_architecture_base != "gfx1030"
        or bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
        or len(rows) != 10
        or tuple(row.slot_id for row in rows)
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    ):
        _fail("hip_fgmres_family_audited_parity_semantics_invalid", "/receipt")
    payload = _receipt_payload(receipt, include_hash=True)
    hashes = _collect_named_values(payload, suffixes=("_hash", "_sha256")) + (
        receipt.attestation_id,
        receipt.receipt_hash,
    )
    if any(
        type(value) is not str or _HASH_RE.fullmatch(value) is None for value in hashes
    ):
        _fail("hip_fgmres_family_audited_parity_hash_field_invalid", "/receipt")
    unique_names = (
        "slot_id",
        "logical_case_key",
        "matrix_cell_id",
        "case_receipt_hash",
        "transfer_context_id",
        "transfer_receipt_hash",
        "ordinal_context_id",
        "ordinal_receipt_hash",
        "completion_export_context_id",
        "completion_export_receipt_hash",
        "canonical_context_id",
        "sealed_checkpoint_context_id",
        "global_context_id",
        "global_receipt_hash",
    )
    if any(len({getattr(row, name) for row in rows}) != 10 for name in unique_names):
        _fail(
            "hip_fgmres_family_audited_parity_duplicate_observation",
            "/observations",
        )
    device_rows = {
        (
            row.device_ordinal,
            row.runtime_library_sha256,
            row.device_uuid_bytes_hex,
            row.device_pci_bdf,
            row.kernel_identity_hash,
            row.kernel_source_sha256,
            row.compiled_architecture,
        )
        for row in rows
    }
    if len(device_rows) != 1:
        _fail(
            "hip_fgmres_family_audited_parity_device_inconsistent",
            "/observations",
        )
    for index, row in enumerate(rows):
        slot = registry.slot(row.slot_id)
        schedule = compile_hip_fgmres_global_sealed_continuation_v1(
            slot.recurrence_plan.free_dof_count,
            slot.recurrence_plan.restart_dimension,
            slot.recurrence_plan.max_iterations,
        )
        package = _fixed_package_slot_semantics(slot, schedule)
        logical_case_key = canonical_hash(
            {
                "registry_hash": registry.registry_hash,
                "slot_registration_hash": slot.slot_registration_hash,
                "slot_id": slot.slot_id,
                "descriptor_hash": slot.descriptor.descriptor_hash,
                "execution_plan_hash": slot.execution_plan.plan_hash,
                "fgmres_plan_hash": slot.fgmres_plan.plan_hash,
                "recurrence_plan_hash": slot.recurrence_plan.plan_hash,
                "policy_hash": slot.policy.policy_hash,
                "cpu_result_hash": slot.cpu_result.result_hash,
            }
        )
        matrix_cell_id = canonical_hash(
            {
                "logical_case_key": logical_case_key,
                "runtime_architecture_base": row.runtime_architecture_base,
                "device_identity_receipt_hash": row.device_identity_receipt_hash,
                "case_receipt_hash": row.case_receipt_hash,
            }
        )
        expected_bytes = (
            16 * slot.recurrence_plan.free_dof_count
            + 192
            + 72 * slot.recurrence_plan.maximum_restart_count
        )
        if (
            row.runtime_architecture_base != "gfx1030"
            or row.compiled_architecture != "gfx1030"
            or row.logical_case_key != logical_case_key
            or row.matrix_cell_id != matrix_cell_id
            or row.runtime_scope
            != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1
            or row.native_loader_bound_runtime is not True
            or row.free_dof_count != slot.recurrence_plan.free_dof_count
            or row.restart_dimension != slot.recurrence_plan.restart_dimension
            or row.max_iterations != slot.recurrence_plan.max_iterations
            or row.maximum_restart_count != slot.recurrence_plan.maximum_restart_count
            or row.recurrence_plan_hash != slot.recurrence_plan.plan_hash
            or row.recurrence_kernel_abi_hash != package["recurrence_kernel_abi_hash"]
            or row.combined_recurrence_abi_hash
            != package["combined_recurrence_abi_hash"]
            or row.kernel_source_sha256 != package["kernel_source_sha256"]
            or row.canonical_schedule_hash != package["canonical_schedule_hash"]
            or row.checkpoint_schedule_hash != package["checkpoint_schedule_hash"]
            or row.program_descriptor_hash != package["program_descriptor_hash"]
            or row.completion_receipt_hash != row.global_receipt_hash
            or row.reduction_stage_count != schedule.plan.reduction_stage_count
            or row.global_full_schedule_hash != schedule.full.canonical_sha256
            or row.sealed_prefix_schedule_hash
            != schedule.sealed_prefix.canonical_sha256
            or row.continuation_schedule_hash != schedule.continuation.canonical_sha256
            or row.recurrence_program_copy_attempt_count != 0
            or row.completion_export_blocking_d2h_attempt_count != 3
            or row.completion_export_blocking_d2h_success_count != 3
            or row.completion_export_blocking_d2h_failure_count != 0
            or row.completion_export_byte_count != expected_bytes
            or row.ordinal_memset_attempt_count != 8
            or row.ordinal_memset_success_count != 8
            or row.ordinal_memset_rejected_count != 0
            or row.ordinal_memset_ambiguous_count != 0
            or row.ordinal_memset_in_flight_count != 0
            or row.ordinal_launch_attempt_count <= 0
            or row.ordinal_launch_attempt_count != schedule.full.launch_count
            or row.ordinal_launch_success_count != schedule.full.launch_count
            or row.ordinal_launch_rejected_count != 0
            or row.ordinal_launch_ambiguous_count != 0
            or row.ordinal_launch_in_flight_count != 0
            or row.ordinal_fence_attempt_count != 3
            or row.ordinal_fence_success_count != 3
            or row.ordinal_fence_rejected_count != 0
            or row.ordinal_fence_ambiguous_count != 0
            or row.ordinal_fence_in_flight_count != 0
            or row.ordinal_total_native_call_count
            != 8 + row.ordinal_launch_attempt_count + 3
            or row.ordinal_operation_delta != row.ordinal_total_native_call_count
            or row.ordinal_event_delta != 2 * row.ordinal_total_native_call_count
            or row.triple_binding_hash
            != canonical_hash(_observation_payload(row, include_triple_hash=False))
        ):
            _fail(
                "hip_fgmres_family_audited_parity_observation_invalid",
                f"/observations/{index}",
            )
    expected_totals = _totals_from_observations(rows, receipt.totals)
    expected_claims = _expected_claims()
    expected_attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
            ),
            "registry_hash": bindings.registry_hash,
            "source_transfer_audit_receipt_hash": (
                bindings.source_transfer_audit_receipt_hash
            ),
            "source_family_receipt_hash": bindings.source_family_receipt_hash,
            "triple_binding_hashes": [row.triple_binding_hash for row in rows],
        }
    )
    if (
        receipt.totals != expected_totals
        or receipt.totals.completion_export_byte_count
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_TOTAL_EXPORT_BYTES_V2
        or receipt.claims != expected_claims
        or receipt.attestation_id != expected_attestation_id
    ):
        _fail("hip_fgmres_family_audited_parity_summary_invalid", "/receipt")


def _collect_named_values(
    value: Any,
    *,
    suffixes: tuple[str, ...],
) -> tuple[Any, ...]:
    found: list[Any] = []
    if type(value) is dict:
        for name, item in value.items():
            if any(name.endswith(suffix) for suffix in suffixes):
                found.append(item)
            else:
                found.extend(_collect_named_values(item, suffixes=suffixes))
    elif type(value) is list:
        for item in value:
            found.extend(_collect_named_values(item, suffixes=suffixes))
    return tuple(found)


def _observation_payload(
    observation: HipFgmresModelFamilyAuditedParityObservationV2,
    *,
    include_triple_hash: bool,
) -> dict[str, Any]:
    payload = {
        name: getattr(observation, name)
        for name in observation.__dataclass_fields__
        if name != "triple_binding_hash"
    }
    if include_triple_hash:
        payload["triple_binding_hash"] = observation.triple_binding_hash
    return payload


def _receipt_payload(
    receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "attestation_id": receipt.attestation_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "bindings": receipt.bindings.to_dict(),
        "observations": [row.to_dict() for row in receipt.observations],
        "totals": receipt.totals.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    schema = json.loads(schema_raw.decode("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: Any) -> str:
    return " ".join(str(value).split())[:512]


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelFamilyAuditedParityV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_ARCHITECTURE_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_STATUS_V2",
    "HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_TOTAL_EXPORT_BYTES_V2",
    "HipFgmresModelFamilyAuditedParityBindingsV2",
    "HipFgmresModelFamilyAuditedParityClaimsV2",
    "HipFgmresModelFamilyAuditedParityObservationV2",
    "HipFgmresModelFamilyAuditedParityReceiptV2",
    "HipFgmresModelFamilyAuditedParityResultV2",
    "HipFgmresModelFamilyAuditedParityTotalsV2",
    "HipFgmresModelFamilyAuditedParityV2Error",
    "attest_hip_fgmres_model_family_audited_parity_v2",
    "validate_hip_fgmres_model_family_audited_parity_receipt_v2",
    "validate_hip_fgmres_model_family_audited_parity_result_v2",
]
