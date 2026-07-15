"""Compose the exact gfx1030 fixed suite with exported transfer-audit authority.

This contract is additive.  It does not change the historical family-v2 or
per-case transfer-audit receipts.  The authoritative result exists only while
the retained process-local family, audit contexts, audit results, and shared
completion-export objects can all be replayed.  Its serialized receipt is a
structural projection, not standalone provenance authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib import resources
import json
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from .fgmres_iteration_host_transfer_audit_v1 import (
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1,
    HipFgmresIterationHostTransferAuditExecutionContextV1,
    HipFgmresIterationHostTransferAuditResultV1,
    validate_hip_fgmres_iteration_host_transfer_audit_result_v1,
)
from .fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2,
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
    HipFgmresModelFamilyParityResultV2,
    validate_hip_fgmres_model_family_parity_result_v2,
)


HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-model-family-host-transfer-audit.v1"
)
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1 = (
    "phase0_registry_gfx1030_fixed_suite_live_transfer_audit_composition"
)
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1 = (
    "process_local_registry_bound_gfx1030_fixed_suite_parity_and_per_case_"
    "bound_runtime_copy_audit_unsigned_non_promoting"
)
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_STATUS_V1 = (
    "primary_gfx1030_fixed_suite_audited_external_gfx1100_pending"
)
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1 = (
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
)
HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_TOTAL_EXPORT_BYTES_V1 = 4408

_SCHEMA_RESOURCE = "hip_fgmres_model_family_host_transfer_audit_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class HipFgmresModelFamilyHostTransferAuditV1Error(RuntimeError):
    """Stable fail-closed composition error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyHostTransferAuditBindingsV1:
    registry_bytes_sha256: str
    registry_hash: str
    source_family_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-family-parity.v2"
    ]
    source_family_receipt_hash: str
    required_architecture_base: Literal["gfx1030"]
    required_slot_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_bytes_sha256": self.registry_bytes_sha256,
            "registry_hash": self.registry_hash,
            "source_family_schema_version": self.source_family_schema_version,
            "source_family_receipt_hash": self.source_family_receipt_hash,
            "required_architecture_base": self.required_architecture_base,
            "required_slot_ids": list(self.required_slot_ids),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyHostTransferAuditObservationV1:
    slot_id: str
    logical_case_key: str
    matrix_cell_id: str
    family_observation_hash: str
    case_id: str
    case_receipt_hash: str
    audit_context_id: str
    audit_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    global_context_id: str
    global_receipt_hash: str
    recurrence_plan_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    runtime_architecture_base: Literal["gfx1030"]
    compiled_architecture: str
    device_ordinal: int
    device_identity_receipt_hash: str
    runtime_library_sha256: str
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    runtime_scope: Literal["exact_engine_v2_bound_context_runtime_only"]
    native_loader_bound_runtime: Literal[True]
    free_dof_count: int
    maximum_restart_count: int
    recurrence_program_sequence_delta: Literal[0]
    recurrence_program_copy_attempt_count: Literal[0]
    completion_export_sequence_delta: Literal[6]
    completion_export_blocking_d2h_attempt_count: Literal[3]
    completion_export_blocking_d2h_success_count: Literal[3]
    completion_export_blocking_d2h_failure_count: Literal[0]
    completion_export_byte_count: int
    pair_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyHostTransferAuditTotalsV1:
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

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyHostTransferAuditClaimsV1:
    fixed_package_registry_and_source_family_receipt_bound: Literal[True]
    exact_gfx1030_registered_ten_slot_coverage_bound: Literal[True]
    ten_same_process_audit_authorities_captured_while_exported: Literal[True]
    case_parity_and_audit_same_export_identity_bound: Literal[True]
    case_and_audit_lineage_hashes_cross_bound: Literal[True]
    per_slot_bound_runtime_recurrence_copy_attempt_zero: Literal[True]
    per_slot_post_fence_exact_three_blocking_d2h: Literal[True]
    composition_factory_reuses_retained_export_identity_only: Literal[True]
    external_gfx1100_fixed_suite_audited: Literal[False] = False
    unsigned_two_architecture_fixed_suite_audited: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    pre_window_async_copy_completion_or_device_dma_activity_zero_proven: Literal[
        False
    ] = False
    raw_cdll_fresh_binding_or_third_party_transfer_zero_proven: Literal[False] = False
    full_solver_setup_or_between_case_transfer_zero_proven: Literal[False] = False
    same_runtime_or_stream_shared_across_all_cases_proven: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    full_model_family_parity_verified: Literal[False] = False
    multiarchitecture_parity_verified: Literal[False] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    signed_evidence: Literal[False] = False
    result_ir_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    whole_process_additional_device_solve_or_export_absence_proven: Literal[False] = (
        False
    )
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyHostTransferAuditReceiptV1:
    status: Literal["primary_gfx1030_fixed_suite_audited_external_gfx1100_pending"]
    attestation_id: str
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresModelFamilyHostTransferAuditBindingsV1
    observations: tuple[HipFgmresModelFamilyHostTransferAuditObservationV1, ...]
    totals: HipFgmresModelFamilyHostTransferAuditTotalsV1
    claims: HipFgmresModelFamilyHostTransferAuditClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresModelFamilyHostTransferAuditAuthorityV1:
    context: HipFgmresIterationHostTransferAuditExecutionContextV1
    result: HipFgmresIterationHostTransferAuditResultV1


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresModelFamilyHostTransferAuditResultV1:
    receipt: HipFgmresModelFamilyHostTransferAuditReceiptV1
    _family_result: HipFgmresModelFamilyParityResultV2 = field(
        repr=False,
        compare=False,
    )
    _audit_authorities: tuple[
        _HipFgmresModelFamilyHostTransferAuditAuthorityV1, ...
    ] = field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(self)
        return self.receipt.to_dict()


def attest_hip_fgmres_model_family_host_transfer_audit_v1(
    family_result: HipFgmresModelFamilyParityResultV2,
    audit_contexts: tuple[HipFgmresIterationHostTransferAuditExecutionContextV1, ...],
) -> HipFgmresModelFamilyHostTransferAuditResultV1:
    """Capture ten exported audits and bind the exact live gfx1030 family."""

    _validate_family_result(family_result)
    authorities = _capture_audit_authorities(audit_contexts)
    receipt = _evaluate(family_result, authorities)
    result = HipFgmresModelFamilyHostTransferAuditResultV1(
        receipt=receipt,
        _family_result=family_result,
        _audit_authorities=authorities,
    )
    return validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
        result,
        expected_family_result=family_result,
        expected_audit_contexts=audit_contexts,
    )


def validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
    result: HipFgmresModelFamilyHostTransferAuditResultV1,
    *,
    expected_family_result: HipFgmresModelFamilyParityResultV2 | None = None,
    expected_audit_contexts: tuple[
        HipFgmresIterationHostTransferAuditExecutionContextV1, ...
    ]
    | None = None,
) -> HipFgmresModelFamilyHostTransferAuditResultV1:
    """Replay the retained family and every expected-context audit authority."""

    if type(result) is not HipFgmresModelFamilyHostTransferAuditResultV1:
        _fail("hip_fgmres_family_transfer_audit_result_type_invalid", "/result")
    if type(result._family_result) is not HipFgmresModelFamilyParityResultV2:
        _fail("hip_fgmres_family_transfer_audit_family_type_invalid", "/family")
    if expected_family_result is not None and result._family_result is not (
        expected_family_result
    ):
        _fail("hip_fgmres_family_transfer_audit_family_changed", "/family")
    if type(result._audit_authorities) is not tuple or any(
        type(row) is not _HipFgmresModelFamilyHostTransferAuditAuthorityV1
        for row in result._audit_authorities
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_authority_container_invalid",
            "/audits",
        )
    if expected_audit_contexts is not None:
        if type(expected_audit_contexts) is not tuple or len(
            expected_audit_contexts
        ) != len(result._audit_authorities):
            _fail(
                "hip_fgmres_family_transfer_audit_expected_contexts_changed",
                "/audits",
            )
        if any(
            authority.context is not context
            for authority, context in zip(
                result._audit_authorities,
                expected_audit_contexts,
                strict=True,
            )
        ):
            _fail(
                "hip_fgmres_family_transfer_audit_expected_contexts_changed",
                "/audits",
            )
    _validate_family_result(result._family_result)
    for index, authority in enumerate(result._audit_authorities):
        _validate_audit_authority(authority, path=f"/audits/{index}")
    expected = _evaluate(result._family_result, result._audit_authorities)
    if result.receipt != expected:
        _fail(
            "hip_fgmres_family_transfer_audit_result_replay_mismatch",
            "/receipt",
        )
    validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(result.receipt)
    return result


def validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
    receipt: HipFgmresModelFamilyHostTransferAuditReceiptV1,
) -> HipFgmresModelFamilyHostTransferAuditReceiptV1:
    """Validate structural consistency without granting live provenance."""

    _validate_exact_types(receipt)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: list(row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail(
            "hip_fgmres_family_transfer_audit_schema_invalid",
            path or "/",
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_receipt_hash_invalid",
            "/receipt_hash",
        )
    _validate_receipt_semantics(receipt)
    return receipt


def _capture_audit_authorities(
    audit_contexts: tuple[HipFgmresIterationHostTransferAuditExecutionContextV1, ...],
) -> tuple[_HipFgmresModelFamilyHostTransferAuditAuthorityV1, ...]:
    if type(audit_contexts) is not tuple:
        _fail(
            "hip_fgmres_family_transfer_audit_context_container_invalid",
            "/audits",
        )
    if len(audit_contexts) != len(
        HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_context_count_invalid",
            "/audits",
        )
    if len({id(context) for context in audit_contexts}) != len(audit_contexts):
        _fail(
            "hip_fgmres_family_transfer_audit_duplicate_context",
            "/audits",
        )
    authorities: list[_HipFgmresModelFamilyHostTransferAuditAuthorityV1] = []
    for index, context in enumerate(audit_contexts):
        if type(context) is not HipFgmresIterationHostTransferAuditExecutionContextV1:
            _fail(
                "hip_fgmres_family_transfer_audit_context_type_invalid",
                f"/audits/{index}",
            )
        audit_result = context.result
        if audit_result is None:
            _fail(
                "hip_fgmres_family_transfer_audit_context_not_exported",
                f"/audits/{index}",
            )
        authority = _HipFgmresModelFamilyHostTransferAuditAuthorityV1(
            context=context,
            result=audit_result,
        )
        _validate_audit_authority(authority, path=f"/audits/{index}")
        authorities.append(authority)
    return tuple(authorities)


def _validate_family_result(result: HipFgmresModelFamilyParityResultV2) -> None:
    if type(result) is not HipFgmresModelFamilyParityResultV2:
        _fail("hip_fgmres_family_transfer_audit_family_type_invalid", "/family")
    try:
        validate_hip_fgmres_model_family_parity_result_v2(result)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_transfer_audit_family_invalid",
            "/family",
            f"{type(exc).__name__}: {exc}",
        )


def _validate_audit_authority(
    authority: _HipFgmresModelFamilyHostTransferAuditAuthorityV1,
    *,
    path: str,
) -> None:
    if type(authority.result) is not HipFgmresIterationHostTransferAuditResultV1:
        _fail(
            "hip_fgmres_family_transfer_audit_result_source_type_invalid",
            path,
        )
    try:
        validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
            authority.result,
            expected_context=authority.context,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_family_transfer_audit_authority_invalid",
            path,
            f"{type(exc).__name__}: {exc}",
        )


def _evaluate(
    family_result: HipFgmresModelFamilyParityResultV2,
    authorities: tuple[_HipFgmresModelFamilyHostTransferAuditAuthorityV1, ...],
) -> HipFgmresModelFamilyHostTransferAuditReceiptV1:
    family_receipt = family_result.receipt
    retained_registry = family_result._registry_result
    registry = load_hip_fgmres_fixture_registry_v1()
    coverage = family_receipt.coverage
    if (
        family_receipt.schema_version
        != HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2
        or family_receipt.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
        or coverage.validated_input_case_count != 10
        or coverage.covered_matrix_cell_count != 10
        or coverage.missing_matrix_cell_count != 10
        or coverage.completed_architecture_bases != ("gfx1030",)
        or coverage.observed_architecture_bases != ("gfx1030",)
        or family_receipt.claims.primary_gfx1030_fixed_suite_complete is not True
        or family_receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
        is not False
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_source_family_scope_invalid",
            "/family/receipt",
        )
    if (
        family_receipt.registry_bytes_sha256 != registry.registry_bytes_sha256
        or family_receipt.registry_hash != registry.registry_hash
        or retained_registry.registry_bytes_sha256 != registry.registry_bytes_sha256
        or retained_registry.registry_hash != registry.registry_hash
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_source_registry_identity_mismatch",
            "/family/registry",
        )
    if len(family_result._case_results) != 10 or len(authorities) != 10:
        _fail(
            "hip_fgmres_family_transfer_audit_source_count_invalid",
            "/sources",
        )

    family_observations = {
        row.case_receipt_hash: row for row in family_receipt.observations
    }
    cases_by_export_hash: dict[str, Any] = {}
    for case in family_result._case_results:
        bindings = case.receipt.bindings
        export_hash = bindings.completion_export_receipt_hash
        if export_hash in cases_by_export_hash:
            _fail(
                "hip_fgmres_family_transfer_audit_duplicate_case_export",
                "/family/cases",
            )
        cases_by_export_hash[export_hash] = case

    observations_by_case: dict[
        str, HipFgmresModelFamilyHostTransferAuditObservationV1
    ] = {}
    audit_receipt_hashes: set[str] = set()
    audit_context_ids: set[str] = set()
    export_context_ids: set[str] = set()
    global_context_ids: set[str] = set()
    for index, authority in enumerate(authorities):
        _validate_audit_authority(authority, path=f"/audits/{index}")
        audit_result = authority.result
        audit_receipt = audit_result.receipt
        audit_bindings = audit_receipt.bindings
        export_hash = audit_bindings.completion_export_receipt_hash
        case = cases_by_export_hash.pop(export_hash, None)
        if case is None:
            _fail(
                "hip_fgmres_family_transfer_audit_case_join_invalid",
                f"/audits/{index}",
            )
        case_receipt = case.receipt
        case_bindings = case_receipt.bindings
        family_observation = family_observations.get(case_receipt.receipt_hash)
        if family_observation is None:
            _fail(
                "hip_fgmres_family_transfer_audit_family_observation_missing",
                f"/audits/{index}",
            )
        source_observation = case._observation_result
        if (
            source_observation._source_export_context
            is not audit_result.completion_export_context
            or source_observation._source_export_result
            is not audit_result.completion_export_result
        ):
            _fail(
                "hip_fgmres_family_transfer_audit_export_identity_mismatch",
                f"/audits/{index}/completion_export",
            )
        case_dimensions = case_receipt.dimensions
        audit_dimensions = audit_receipt.dimensions
        if (
            audit_receipt.actual_backend != "hip"
            or audit_bindings.native_loader_bound_runtime is not True
            or audit_bindings.runtime_scope
            != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1
            or audit_bindings.completion_export_context_id
            != case_bindings.completion_export_context_id
            or audit_bindings.completion_export_receipt_hash
            != case_bindings.completion_export_receipt_hash
            or audit_bindings.completion_export_payload_hash
            != case_bindings.completion_export_payload_hash
            or audit_bindings.global_context_id != case_bindings.global_context_id
            or audit_bindings.global_receipt_hash != case_bindings.global_receipt_hash
            or audit_bindings.recurrence_plan_hash != case_bindings.recurrence_plan_hash
            or audit_bindings.kernel_identity_hash != case_bindings.kernel_identity_hash
            or audit_bindings.kernel_source_sha256 != case_bindings.kernel_source_sha256
            or audit_bindings.architecture != case_bindings.compiled_architecture
            or audit_bindings.device_ordinal != case_bindings.device_ordinal
            or audit_dimensions.free_dof_count != case_dimensions.free_dof_count
            or audit_dimensions.maximum_restart_count
            != case_dimensions.maximum_restart_count
            or family_observation.runtime_architecture_base != "gfx1030"
            or family_observation.compiled_architecture
            != case_bindings.compiled_architecture
            or family_observation.device_ordinal != case_bindings.device_ordinal
        ):
            _fail(
                "hip_fgmres_family_transfer_audit_lineage_binding_mismatch",
                f"/audits/{index}",
            )
        if (
            audit_receipt.receipt_hash in audit_receipt_hashes
            or audit_receipt.context_id in audit_context_ids
            or audit_bindings.completion_export_context_id in export_context_ids
            or audit_bindings.global_context_id in global_context_ids
            or case_receipt.receipt_hash in observations_by_case
        ):
            _fail(
                "hip_fgmres_family_transfer_audit_duplicate_authority",
                f"/audits/{index}",
            )
        audit_receipt_hashes.add(audit_receipt.receipt_hash)
        audit_context_ids.add(audit_receipt.context_id)
        export_context_ids.add(audit_bindings.completion_export_context_id)
        global_context_ids.add(audit_bindings.global_context_id)

        recurrence = audit_receipt.window.recurrence_program
        export = audit_receipt.window.completion_export
        recurrence_attempts = sum(
            row.attempt_count
            for row in (
                recurrence.h2d_async,
                recurrence.d2h_async,
                recurrence.d2h_blocking,
            )
        )
        blocking = export.d2h_blocking
        draft = HipFgmresModelFamilyHostTransferAuditObservationV1(
            slot_id=family_observation.slot_id,
            logical_case_key=family_observation.logical_case_key,
            matrix_cell_id=family_observation.matrix_cell_id,
            family_observation_hash=canonical_hash(family_observation.to_dict()),
            case_id=family_observation.case_id,
            case_receipt_hash=case_receipt.receipt_hash,
            audit_context_id=audit_receipt.context_id,
            audit_receipt_hash=audit_receipt.receipt_hash,
            completion_export_context_id=(audit_bindings.completion_export_context_id),
            completion_export_receipt_hash=(
                audit_bindings.completion_export_receipt_hash
            ),
            completion_export_payload_hash=(
                audit_bindings.completion_export_payload_hash
            ),
            global_context_id=audit_bindings.global_context_id,
            global_receipt_hash=audit_bindings.global_receipt_hash,
            recurrence_plan_hash=audit_bindings.recurrence_plan_hash,
            kernel_identity_hash=audit_bindings.kernel_identity_hash,
            kernel_source_sha256=audit_bindings.kernel_source_sha256,
            runtime_architecture_base=family_observation.runtime_architecture_base,
            compiled_architecture=family_observation.compiled_architecture,
            device_ordinal=family_observation.device_ordinal,
            device_identity_receipt_hash=(
                family_observation.device_identity_receipt_hash
            ),
            runtime_library_sha256=family_observation.runtime_library_sha256,
            device_uuid_bytes_hex=family_observation.device_uuid_bytes_hex,
            device_pci_bdf=family_observation.device_pci_bdf,
            runtime_scope=audit_bindings.runtime_scope,
            native_loader_bound_runtime=(audit_bindings.native_loader_bound_runtime),
            free_dof_count=audit_dimensions.free_dof_count,
            maximum_restart_count=audit_dimensions.maximum_restart_count,
            recurrence_program_sequence_delta=recurrence.sequence_delta,
            recurrence_program_copy_attempt_count=recurrence_attempts,
            completion_export_sequence_delta=export.sequence_delta,
            completion_export_blocking_d2h_attempt_count=(blocking.attempt_count),
            completion_export_blocking_d2h_success_count=(blocking.success_count),
            completion_export_blocking_d2h_failure_count=(blocking.failure_count),
            completion_export_byte_count=audit_dimensions.total_export_byte_count,
            pair_binding_hash=_ZERO_HASH,
        )
        observation = replace(
            draft,
            pair_binding_hash=canonical_hash(
                _observation_payload(draft, include_pair_hash=False)
            ),
        )
        observations_by_case[case_receipt.receipt_hash] = observation

    if cases_by_export_hash or len(observations_by_case) != 10:
        _fail(
            "hip_fgmres_family_transfer_audit_case_set_mismatch",
            "/sources",
        )
    ordered = tuple(
        observations_by_case[row.case_receipt_hash]
        for row in family_receipt.observations
    )
    if tuple(row.slot_id for row in ordered) != (
        HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_slot_order_invalid",
            "/observations",
        )

    bindings = HipFgmresModelFamilyHostTransferAuditBindingsV1(
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        source_family_schema_version=family_receipt.schema_version,
        source_family_receipt_hash=family_receipt.receipt_hash,
        required_architecture_base=(
            HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_ARCHITECTURE_V1
        ),
        required_slot_ids=(
            HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
        ),
    )
    totals = HipFgmresModelFamilyHostTransferAuditTotalsV1(
        required_slot_count=10,
        paired_slot_count=10,
        source_family_expected_matrix_cell_count=(coverage.expected_matrix_cell_count),
        source_family_covered_matrix_cell_count=(coverage.covered_matrix_cell_count),
        source_family_missing_matrix_cell_count=(coverage.missing_matrix_cell_count),
        audited_gfx1030_slot_count=10,
        audited_gfx1100_slot_count=0,
        recurrence_program_copy_attempt_count=sum(
            row.recurrence_program_copy_attempt_count for row in ordered
        ),
        completion_export_blocking_d2h_attempt_count=sum(
            row.completion_export_blocking_d2h_attempt_count for row in ordered
        ),
        completion_export_blocking_d2h_success_count=sum(
            row.completion_export_blocking_d2h_success_count for row in ordered
        ),
        completion_export_blocking_d2h_failure_count=sum(
            row.completion_export_blocking_d2h_failure_count for row in ordered
        ),
        completion_export_byte_count=sum(
            row.completion_export_byte_count for row in ordered
        ),
    )
    claims = HipFgmresModelFamilyHostTransferAuditClaimsV1(
        fixed_package_registry_and_source_family_receipt_bound=True,
        exact_gfx1030_registered_ten_slot_coverage_bound=True,
        ten_same_process_audit_authorities_captured_while_exported=True,
        case_parity_and_audit_same_export_identity_bound=True,
        case_and_audit_lineage_hashes_cross_bound=True,
        per_slot_bound_runtime_recurrence_copy_attempt_zero=True,
        per_slot_post_fence_exact_three_blocking_d2h=True,
        composition_factory_reuses_retained_export_identity_only=True,
    )
    attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1
            ),
            "registry_hash": registry.registry_hash,
            "source_family_receipt_hash": family_receipt.receipt_hash,
            "pair_binding_hashes": [row.pair_binding_hash for row in ordered],
        }
    )
    draft_receipt = HipFgmresModelFamilyHostTransferAuditReceiptV1(
        status=HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=(HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1),
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
    return validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(receipt)


def _validate_exact_types(
    receipt: HipFgmresModelFamilyHostTransferAuditReceiptV1,
) -> None:
    if (
        type(receipt) is not HipFgmresModelFamilyHostTransferAuditReceiptV1
        or type(receipt.bindings) is not HipFgmresModelFamilyHostTransferAuditBindingsV1
        or type(receipt.observations) is not tuple
        or any(
            type(row) is not HipFgmresModelFamilyHostTransferAuditObservationV1
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresModelFamilyHostTransferAuditTotalsV1
        or type(receipt.claims) is not HipFgmresModelFamilyHostTransferAuditClaimsV1
    ):
        _fail("hip_fgmres_family_transfer_audit_type_invalid", "/receipt")
    strings = (
        receipt.status,
        receipt.attestation_id,
        receipt.evidence_scope,
        receipt.actual_backend,
        receipt.receipt_hash,
        receipt.bindings.registry_bytes_sha256,
        receipt.bindings.registry_hash,
        receipt.bindings.source_family_schema_version,
        receipt.bindings.source_family_receipt_hash,
        receipt.bindings.required_architecture_base,
        *receipt.bindings.required_slot_ids,
        *(
            value
            for row in receipt.observations
            for name, value in row.to_dict().items()
            if name
            not in {
                "device_ordinal",
                "native_loader_bound_runtime",
                "free_dof_count",
                "maximum_restart_count",
                "recurrence_program_sequence_delta",
                "recurrence_program_copy_attempt_count",
                "completion_export_sequence_delta",
                "completion_export_blocking_d2h_attempt_count",
                "completion_export_blocking_d2h_success_count",
                "completion_export_blocking_d2h_failure_count",
                "completion_export_byte_count",
            }
        ),
    )
    if any(type(value) is not str for value in strings):
        _fail("hip_fgmres_family_transfer_audit_type_invalid", "/string")
    integers = (
        *(value for value in receipt.totals.to_dict().values()),
        *(
            value
            for row in receipt.observations
            for name, value in row.to_dict().items()
            if name
            in {
                "device_ordinal",
                "free_dof_count",
                "maximum_restart_count",
                "recurrence_program_sequence_delta",
                "recurrence_program_copy_attempt_count",
                "completion_export_sequence_delta",
                "completion_export_blocking_d2h_attempt_count",
                "completion_export_blocking_d2h_success_count",
                "completion_export_blocking_d2h_failure_count",
                "completion_export_byte_count",
            }
        ),
    )
    if any(type(value) is not int or value < 0 for value in integers):
        _fail("hip_fgmres_family_transfer_audit_type_invalid", "/integer")
    booleans = (
        receipt.promotion_eligible,
        *(
            getattr(receipt.claims, name)
            for name in receipt.claims.__dataclass_fields__
        ),
        *(row.native_loader_bound_runtime for row in receipt.observations),
    )
    if any(type(value) is not bool for value in booleans):
        _fail("hip_fgmres_family_transfer_audit_type_invalid", "/boolean")


def _validate_receipt_semantics(
    receipt: HipFgmresModelFamilyHostTransferAuditReceiptV1,
) -> None:
    registry = load_hip_fgmres_fixture_registry_v1()
    bindings = receipt.bindings
    if (
        receipt.status != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_family_schema_version
        != HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2
        or bindings.required_architecture_base != "gfx1030"
        or bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
        or len(receipt.observations) != 10
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_semantics_invalid",
            "/receipt",
        )
    hash_fields = (
        receipt.attestation_id,
        receipt.receipt_hash,
        bindings.registry_bytes_sha256,
        bindings.registry_hash,
        bindings.source_family_receipt_hash,
        *(
            value
            for row in receipt.observations
            for name, value in row.to_dict().items()
            if name.endswith("_hash") or name.endswith("_sha256")
        ),
    )
    if any(_HASH_RE.fullmatch(value) is None for value in hash_fields):
        _fail(
            "hip_fgmres_family_transfer_audit_hash_field_invalid",
            "/receipt",
        )
    unique_identity_fields = (
        "case_id",
        "case_receipt_hash",
        "family_observation_hash",
        "logical_case_key",
        "matrix_cell_id",
        "audit_context_id",
        "audit_receipt_hash",
        "completion_export_context_id",
        "completion_export_receipt_hash",
        "global_context_id",
        "global_receipt_hash",
    )
    if any(
        len({getattr(row, name) for row in receipt.observations}) != 10
        for name in unique_identity_fields
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_duplicate_observation",
            "/observations",
        )
    architecture_device_kernel_rows = {
        (
            row.device_ordinal,
            row.device_uuid_bytes_hex,
            row.device_pci_bdf,
            row.runtime_library_sha256,
            row.kernel_identity_hash,
            row.kernel_source_sha256,
            row.compiled_architecture,
        )
        for row in receipt.observations
    }
    if len(architecture_device_kernel_rows) != 1:
        _fail(
            "hip_fgmres_family_transfer_audit_architecture_device_inconsistent",
            "/observations",
        )
    for index, row in enumerate(receipt.observations):
        slot = registry.slot(row.slot_id)
        expected_bytes = (
            16 * slot.recurrence_plan.free_dof_count
            + 192
            + 72 * slot.recurrence_plan.maximum_restart_count
        )
        if (
            row.runtime_architecture_base != "gfx1030"
            or row.compiled_architecture != "gfx1030"
            or row.runtime_scope
            != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1
            or row.native_loader_bound_runtime is not True
            or row.free_dof_count != slot.recurrence_plan.free_dof_count
            or row.maximum_restart_count != slot.recurrence_plan.maximum_restart_count
            or row.recurrence_program_sequence_delta != 0
            or row.recurrence_program_copy_attempt_count != 0
            or row.completion_export_sequence_delta != 6
            or row.completion_export_blocking_d2h_attempt_count != 3
            or row.completion_export_blocking_d2h_success_count != 3
            or row.completion_export_blocking_d2h_failure_count != 0
            or row.completion_export_byte_count != expected_bytes
            or row.pair_binding_hash
            != canonical_hash(_observation_payload(row, include_pair_hash=False))
        ):
            _fail(
                "hip_fgmres_family_transfer_audit_observation_invalid",
                f"/observations/{index}",
            )
    expected_totals = HipFgmresModelFamilyHostTransferAuditTotalsV1(
        required_slot_count=10,
        paired_slot_count=10,
        source_family_expected_matrix_cell_count=20,
        source_family_covered_matrix_cell_count=10,
        source_family_missing_matrix_cell_count=10,
        audited_gfx1030_slot_count=10,
        audited_gfx1100_slot_count=0,
        recurrence_program_copy_attempt_count=sum(
            row.recurrence_program_copy_attempt_count for row in receipt.observations
        ),
        completion_export_blocking_d2h_attempt_count=sum(
            row.completion_export_blocking_d2h_attempt_count
            for row in receipt.observations
        ),
        completion_export_blocking_d2h_success_count=sum(
            row.completion_export_blocking_d2h_success_count
            for row in receipt.observations
        ),
        completion_export_blocking_d2h_failure_count=sum(
            row.completion_export_blocking_d2h_failure_count
            for row in receipt.observations
        ),
        completion_export_byte_count=sum(
            row.completion_export_byte_count for row in receipt.observations
        ),
    )
    expected_claims = HipFgmresModelFamilyHostTransferAuditClaimsV1(
        fixed_package_registry_and_source_family_receipt_bound=True,
        exact_gfx1030_registered_ten_slot_coverage_bound=True,
        ten_same_process_audit_authorities_captured_while_exported=True,
        case_parity_and_audit_same_export_identity_bound=True,
        case_and_audit_lineage_hashes_cross_bound=True,
        per_slot_bound_runtime_recurrence_copy_attempt_zero=True,
        per_slot_post_fence_exact_three_blocking_d2h=True,
        composition_factory_reuses_retained_export_identity_only=True,
    )
    expected_attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1
            ),
            "registry_hash": bindings.registry_hash,
            "source_family_receipt_hash": bindings.source_family_receipt_hash,
            "pair_binding_hashes": [
                row.pair_binding_hash for row in receipt.observations
            ],
        }
    )
    if (
        receipt.totals != expected_totals
        or receipt.totals.completion_export_byte_count
        != HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_TOTAL_EXPORT_BYTES_V1
        or receipt.claims != expected_claims
        or receipt.attestation_id != expected_attestation_id
    ):
        _fail(
            "hip_fgmres_family_transfer_audit_summary_invalid",
            "/receipt",
        )


def _observation_payload(
    observation: HipFgmresModelFamilyHostTransferAuditObservationV1,
    *,
    include_pair_hash: bool,
) -> dict[str, Any]:
    payload = {
        name: getattr(observation, name)
        for name in observation.__dataclass_fields__
        if name != "pair_binding_hash"
    }
    if include_pair_hash:
        payload["pair_binding_hash"] = observation.pair_binding_hash
    return payload


def _receipt_payload(
    receipt: HipFgmresModelFamilyHostTransferAuditReceiptV1,
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
    raise HipFgmresModelFamilyHostTransferAuditV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_STATUS_V1",
    "HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_TOTAL_EXPORT_BYTES_V1",
    "HipFgmresModelFamilyHostTransferAuditBindingsV1",
    "HipFgmresModelFamilyHostTransferAuditClaimsV1",
    "HipFgmresModelFamilyHostTransferAuditObservationV1",
    "HipFgmresModelFamilyHostTransferAuditReceiptV1",
    "HipFgmresModelFamilyHostTransferAuditResultV1",
    "HipFgmresModelFamilyHostTransferAuditTotalsV1",
    "HipFgmresModelFamilyHostTransferAuditV1Error",
    "attest_hip_fgmres_model_family_host_transfer_audit_v1",
    "validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1",
    "validate_hip_fgmres_model_family_host_transfer_audit_result_v1",
]
