"""Exact-package ResultIR-v2 disposition for the retained FGMRES family.

The package fixture suite deliberately contains both converged numerical
cases and recurrence/lifecycle cases that terminate at ``max_iterations``.
This additive contract therefore accounts for all ten canonical slots while
issuing no successful ``ResultIRV2`` for a non-converged source.  Seven
already-issued :class:`HipFgmresResultIRBridgeResultV2` objects are retained
by exact identity; the other three slots carry an explicit fail-closed
``not_issued_nonconverged`` disposition.

The attestation factory composes retained authorities only.  It does not call
the ResultIR builder, a HIP/native/device solver, an exporter, a native entry
point, or a device operation.  Package-registry validation may replay its
deterministic CPU reference fixtures; those validation replays are explicitly
outside the ResultIR-projection counters.  Live audited-family authority is
replayed before and after the composition.  Once issued, validation is
deliberately detached: it replays
the audited receipt, the fixed package registry, every retained ResultIR
bridge, and a process-local exact-object issuance seal without consulting the
closed HIP/audit contexts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import re
import threading
from typing import Any, Literal, NoReturn, TypeAlias
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    RESULT_IR_V2_CAPABILITY_PROFILE,
    RESULT_IR_V2_SCHEMA_VERSION,
)

from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresFixtureRegistryResultV1,
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
    validate_hip_fgmres_fixture_registry_result_v1,
)
from .fgmres_model_case_parity_v1 import HipFgmresModelCaseParityResultV1
from .fgmres_model_family_audited_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2,
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2,
    HipFgmresModelFamilyAuditedParityReceiptV2,
    HipFgmresModelFamilyAuditedParityResultV2,
    validate_hip_fgmres_model_family_audited_parity_receipt_v2,
    validate_hip_fgmres_model_family_audited_parity_result_v2,
)
from .fgmres_model_family_host_transfer_audit_v1 import (
    HipFgmresModelFamilyHostTransferAuditResultV1,
)
from .fgmres_model_family_parity_v2 import HipFgmresModelFamilyParityResultV2
from .fgmres_result_ir_v2 import (
    HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE,
    HipFgmresResultIRBridgeResultV2,
    _validate_hip_fgmres_result_ir_v2_against_live_case,
    validate_hip_fgmres_result_ir_v2,
)


HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-model-family-result-ir-disposition.v1"
)
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_package_gfx1030_ten_slot_result_ir_v2_disposition"
)
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_STATUS_V1 = (
    "exact_gfx1030_ten_slot_result_ir_v2_disposition_verified"
)
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_EVIDENCE_SCOPE_V1 = (
    "process_local_registry_bound_unsigned_nonpersistent_nonpromoting"
)
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1 = (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
)
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_READY_COUNT_V1 = 7
HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_NOT_ISSUED_COUNT_V1 = 3

_SCHEMA_RESOURCE = "hip_fgmres_model_family_result_ir_disposition_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class HipFgmresModelFamilyResultIRDispositionV1Error(RuntimeError):
    """Stable fail-closed family ResultIR-disposition error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyResultIRDispositionBindingsV1:
    registry_schema_version: Literal[
        "structural-analysis-hip-fgmres-fixture-registry.v1"
    ]
    fixture_suite_id: Literal[
        "phase0_execution_plan_v2_linear_frame_truss_fgmres_fixed_suite.v2"
    ]
    registry_bytes_sha256: str
    registry_hash: str
    source_audited_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-family-audited-parity.v2"
    ]
    source_audited_capability_profile: Literal[
        "phase0_exact_gfx1030_family_parity_transfer_and_launch_fence_audit_composition"
    ]
    source_audited_attestation_id: str
    source_audited_receipt_hash: str
    source_transfer_audit_receipt_hash: str
    source_family_receipt_hash: str
    result_ir_schema_version: Literal["structural-analysis-result-ir.v2"]
    result_ir_capability_profile: Literal[
        "hip_fgmres_sparse_plan_recovery_linear_static"
    ]
    result_ir_bridge_capability_profile: Literal[
        "hip_fgmres_retained_completion_sparse_result_ir_v2"
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
class HipFgmresModelFamilyResultIRReadyObservationV1:
    slot_id: str
    disposition: Literal["ready_result_ir_v2"]
    slot_registration_hash: str
    case_fingerprint: str
    logical_case_key: str
    matrix_cell_id: str
    audited_triple_binding_hash: str
    case_id: str
    case_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    cpu_result_hash: str
    terminal_observation_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    compiled_architecture: Literal["gfx1030"]
    runtime_architecture_base: Literal["gfx1030"]
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    cpu_status: Literal["converged"]
    cpu_termination_code: str
    solver_tolerance_passed: Literal[True]
    authoritative_plan_tolerance_passed: Literal[True]
    result_id: str
    result_ir_hash: str
    numerical_result_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    solution_payload_sha256: str
    exported_free_residual_payload_sha256: str
    result_array_descriptor_hash: str
    result_array_count: Literal[6]
    result_array_byte_count: int
    detached_raw_payload_byte_count: int
    additional_device_operation_count: Literal[0]
    additional_d2h_operation_count: Literal[0]
    additional_solve_count: Literal[0]
    additional_export_count: Literal[0]
    fallback_count: Literal[0]
    disposition_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyResultIRNotIssuedObservationV1:
    slot_id: str
    disposition: Literal["not_issued_nonconverged"]
    slot_registration_hash: str
    case_fingerprint: str
    logical_case_key: str
    matrix_cell_id: str
    audited_triple_binding_hash: str
    case_id: str
    case_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    cpu_result_hash: str
    terminal_observation_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    compiled_architecture: Literal["gfx1030"]
    runtime_architecture_base: Literal["gfx1030"]
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    cpu_status: Literal["max_iterations"]
    cpu_termination_code: Literal["max_iterations_exhausted"]
    solver_tolerance_passed: Literal[False]
    authoritative_plan_tolerance_passed: Literal[False]
    result_ir_absence_reason: Literal["source_not_converged"]
    result_ir_materialized: Literal[False]
    disposition_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


HipFgmresModelFamilyResultIRDispositionObservationV1: TypeAlias = (
    HipFgmresModelFamilyResultIRReadyObservationV1
    | HipFgmresModelFamilyResultIRNotIssuedObservationV1
)


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyResultIRDispositionTotalsV1:
    required_slot_count: Literal[10]
    ready_result_ir_v2_count: Literal[7]
    not_issued_nonconverged_count: Literal[3]
    package_global_dof_count: Literal[162]
    package_element_count: Literal[17]
    package_free_dof_count: Literal[97]
    package_csr_nnz: Literal[2196]
    ready_global_dof_count: Literal[90]
    ready_element_count: Literal[8]
    ready_free_dof_count: Literal[43]
    ready_csr_nnz: Literal[1116]
    ready_result_array_count: Literal[42]
    ready_result_array_byte_count: Literal[3336]
    ready_detached_raw_payload_byte_count: Literal[688]
    upstream_completion_export_blocking_d2h_attempt_count: Literal[30]
    upstream_completion_export_blocking_d2h_success_count: Literal[30]
    upstream_completion_export_blocking_d2h_failure_count: Literal[0]
    upstream_completion_export_byte_count: Literal[4408]
    result_ir_projection_additional_device_operation_count: Literal[0]
    result_ir_projection_additional_d2h_operation_count: Literal[0]
    result_ir_projection_additional_solve_count: Literal[0]
    result_ir_projection_additional_export_count: Literal[0]
    result_ir_projection_fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyResultIRDispositionClaimsV1:
    fixed_package_registry_replayed: Literal[True] = True
    audited_ten_slot_authority_replayed_at_issuance: Literal[True] = True
    canonical_ten_slot_disposition_verified: Literal[True] = True
    seven_converged_result_ir_v2_verified: Literal[True] = True
    three_nonconverged_result_ir_v2_not_issued: Literal[True] = True
    retained_bridge_exact_identity_bound: Literal[True] = True
    case_plan_provenance_observation_device_export_cross_bound: Literal[True] = True
    descriptor_only_family_manifest: Literal[True] = True
    post_close_detached_value_validation_supported: Literal[True] = True
    composition_factory_reuses_retained_authorities_only: Literal[True] = True
    result_ir_projection_additional_device_operation_zero: Literal[True] = True
    result_ir_projection_additional_d2h_zero: Literal[True] = True
    result_ir_projection_additional_solve_zero: Literal[True] = True
    result_ir_projection_additional_export_zero: Literal[True] = True
    result_ir_projection_fallback_zero: Literal[True] = True
    registry_validation_cpu_reference_replay_zero_proven: Literal[False] = False
    exact_ten_slot_result_ir_v2_ready: Literal[False] = False
    all_ten_solution_ready: Literal[False] = False
    nonconverged_state_committed: Literal[False] = False
    external_gfx1100_result_ir_verified: Literal[False] = False
    unsigned_two_architecture_result_ir_verified: Literal[False] = False
    full_model_family_result_ir_verified: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    device_recovery_verified: Literal[False] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    hostile_same_process_mutation_or_interposition_resistance: Literal[False] = False
    signed_evidence: Literal[False] = False
    persistent_external_log_verified: Literal[False] = False
    peak_rss_measured: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    nonlinear_dynamic_shell_solid_contact_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyResultIRDispositionReceiptV1:
    status: Literal["exact_gfx1030_ten_slot_result_ir_v2_disposition_verified"]
    attestation_id: str
    evidence_scope: Literal[
        "process_local_registry_bound_unsigned_nonpersistent_nonpromoting"
    ]
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresModelFamilyResultIRDispositionBindingsV1
    observations: tuple[HipFgmresModelFamilyResultIRDispositionObservationV1, ...]
    totals: HipFgmresModelFamilyResultIRDispositionTotalsV1
    claims: HipFgmresModelFamilyResultIRDispositionClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _SourceSnapshotV1:
    audited_result: HipFgmresModelFamilyAuditedParityResultV2
    audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    transfer_result: HipFgmresModelFamilyHostTransferAuditResultV1
    family_result: HipFgmresModelFamilyParityResultV2
    source_cases: tuple[HipFgmresModelCaseParityResultV1, ...]
    canonical_cases: tuple[HipFgmresModelCaseParityResultV1, ...]
    registry: HipFgmresFixtureRegistryResultV1
    token: tuple[Any, ...]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _BridgeSnapshotV1:
    bridge: HipFgmresResultIRBridgeResultV2
    receipt: Any
    plan: Any
    accepted_state: Any
    evaluated_trial_state: Any
    committed_state: Any
    source_provenance: Any
    result_ir_hash: str
    plan_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    provenance_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FamilyDispositionIssuanceV1:
    mint: object
    audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...]
    bridge_snapshots: tuple[_BridgeSnapshotV1, ...]
    receipt_hash: str
    receipt_payload_hash: str
    audited_receipt_hash: str
    audited_payload_hash: str


@dataclass(frozen=True, repr=False, eq=False)
class HipFgmresModelFamilyResultIRDispositionResultV1:
    """Exact issued family disposition, valid after HIP contexts close."""

    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1
    _source_audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    _result_ir_bridges: tuple[HipFgmresResultIRBridgeResultV2, ...]

    @property
    def result_ir_bridges(self) -> tuple[HipFgmresResultIRBridgeResultV2, ...]:
        return self._result_ir_bridges

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_result_ir_disposition_result_v1(self)
        return self.receipt.to_dict()


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresModelFamilyResultIRDispositionResultV1,
    _FamilyDispositionIssuanceV1,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_model_family_result_ir_disposition_v1(
    audited_result: HipFgmresModelFamilyAuditedParityResultV2,
    result_ir_bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
) -> HipFgmresModelFamilyResultIRDispositionResultV1:
    """Compose ten dispositions from audited authority and seven bridges."""

    first = _capture_live_source(audited_result)
    receipt, canonical_bridges = _evaluate(first, result_ir_bridges)
    second = _capture_live_source(audited_result)
    if second.token != first.token:
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_changed",
            "/source/audited",
        )
    # Re-evaluate after the second live replay so no receipt is issued from a
    # source/bridge view that changed during the first composition pass.
    receipt, canonical_bridges = _evaluate(second, canonical_bridges)
    final = _capture_live_source(audited_result)
    if final.token != second.token:
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_changed",
            "/source/audited",
        )
    result = HipFgmresModelFamilyResultIRDispositionResultV1(
        receipt=receipt,
        _source_audited_receipt=final.audited_receipt,
        _result_ir_bridges=canonical_bridges,
    )
    issuance = _FamilyDispositionIssuanceV1(
        mint=object(),
        audited_receipt=final.audited_receipt,
        receipt=receipt,
        bridges=canonical_bridges,
        bridge_snapshots=tuple(_bridge_snapshot(row) for row in canonical_bridges),
        receipt_hash=receipt.receipt_hash,
        receipt_payload_hash=canonical_hash(
            _receipt_payload(receipt, include_hash=True)
        ),
        audited_receipt_hash=final.audited_receipt.receipt_hash,
        audited_payload_hash=canonical_hash(final.audited_receipt.to_dict()),
    )
    with _ISSUANCE_LOCK:
        if result in _ISSUANCES:  # pragma: no cover - fresh identity
            _fail(
                "hip_fgmres_family_result_ir_disposition_issuance_duplicate",
                "/issuance",
            )
        _ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_model_family_result_ir_disposition_result_v1(result)
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
    result: HipFgmresModelFamilyResultIRDispositionResultV1,
) -> HipFgmresModelFamilyResultIRDispositionResultV1:
    """Replay an issued result without consulting live HIP/audit contexts."""

    if type(result) is not HipFgmresModelFamilyResultIRDispositionResultV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_result_type_invalid",
            "/",
        )
    validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(result.receipt)
    if type(result._source_audited_receipt) is not (
        HipFgmresModelFamilyAuditedParityReceiptV2
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_type_invalid",
            "/source/audited_receipt",
        )
    if type(result._result_ir_bridges) is not tuple:
        _fail(
            "hip_fgmres_family_result_ir_disposition_bridge_container_invalid",
            "/bridges",
        )
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _FamilyDispositionIssuanceV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_issuance_unavailable",
            "/issuance",
        )
    if (
        issuance.receipt is not result.receipt
        or issuance.audited_receipt is not result._source_audited_receipt
        or issuance.bridges is not result._result_ir_bridges
        or len(issuance.bridge_snapshots) != len(result._result_ir_bridges)
        or issuance.receipt_hash != result.receipt.receipt_hash
        or issuance.receipt_payload_hash
        != canonical_hash(_receipt_payload(result.receipt, include_hash=True))
        or issuance.audited_receipt_hash != result._source_audited_receipt.receipt_hash
        or issuance.audited_payload_hash
        != canonical_hash(result._source_audited_receipt.to_dict())
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_issuance_binding_mismatch",
            "/issuance",
        )
    try:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            result._source_audited_receipt
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_detached_source_invalid",
            "/source/audited_receipt",
            f"{type(exc).__name__}: {exc}",
        )
    for index, (bridge, snapshot) in enumerate(
        zip(
            result._result_ir_bridges,
            issuance.bridge_snapshots,
            strict=True,
        )
    ):
        validate_hip_fgmres_result_ir_v2(bridge)
        _validate_bridge_snapshot(bridge, snapshot, path=f"/bridges/{index}")
    _validate_detached_composition(
        result.receipt,
        result._source_audited_receipt,
        result._result_ir_bridges,
    )
    return result


def validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1,
) -> HipFgmresModelFamilyResultIRDispositionReceiptV1:
    """Validate detached structure; this does not grant live provenance."""

    _validate_exact_receipt_types(receipt)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: tuple(str(part) for part in row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail(
            "hip_fgmres_family_result_ir_disposition_schema_invalid",
            path or "/",
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_receipt_hash_invalid",
            "/receipt_hash",
        )
    _validate_receipt_semantics(receipt)
    return receipt


def _capture_live_source(
    result: HipFgmresModelFamilyAuditedParityResultV2,
) -> _SourceSnapshotV1:
    if type(result) is not HipFgmresModelFamilyAuditedParityResultV2:
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_type_invalid",
            "/source/audited",
        )
    try:
        validate_hip_fgmres_model_family_audited_parity_result_v2(result)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_invalid",
            "/source/audited",
            f"{type(exc).__name__}: {exc}",
        )
    transfer = result._transfer_composition_result
    if type(transfer) is not HipFgmresModelFamilyHostTransferAuditResultV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_transfer_type_invalid",
            "/source/transfer",
        )
    family = transfer._family_result
    if type(family) is not HipFgmresModelFamilyParityResultV2:
        _fail(
            "hip_fgmres_family_result_ir_disposition_family_type_invalid",
            "/source/family",
        )
    cases = family._case_results
    if (
        type(cases) is not tuple
        or len(cases) != 10
        or any(type(case) is not HipFgmresModelCaseParityResultV1 for case in cases)
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_set_invalid",
            "/source/cases",
        )
    retained_registry = family._registry_result
    if type(retained_registry) is not HipFgmresFixtureRegistryResultV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_registry_type_invalid",
            "/source/registry",
        )
    try:
        validate_hip_fgmres_fixture_registry_result_v1(retained_registry)
        registry = load_hip_fgmres_fixture_registry_v1()
        validate_hip_fgmres_fixture_registry_result_v1(registry)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_registry_invalid",
            "/source/registry",
            f"{type(exc).__name__}: {exc}",
        )
    if (
        retained_registry.registry_bytes_sha256 != registry.registry_bytes_sha256
        or retained_registry.registry_hash != registry.registry_hash
        or result.receipt.bindings.registry_bytes_sha256
        != registry.registry_bytes_sha256
        or result.receipt.bindings.registry_hash != registry.registry_hash
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_registry_binding_mismatch",
            "/source/registry",
        )
    if (
        result.receipt.schema_version
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2
        or result.receipt.capability_profile
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
        or result.receipt.actual_backend != "hip"
        or result.receipt.promotion_eligible is not False
        or result.receipt.claims.result_ir_verified is not False
        or result.receipt.bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1
        or len(result.receipt.observations) != 10
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_source_scope_invalid",
            "/source/audited/receipt",
        )
    cases_by_hash = {case.receipt.receipt_hash: case for case in cases}
    if len(cases_by_hash) != 10:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_duplicate",
            "/source/cases",
        )
    canonical: list[HipFgmresModelCaseParityResultV1] = []
    for index, observation in enumerate(result.receipt.observations):
        expected_slot = registry.slots[index]
        if observation.slot_id != expected_slot.slot_id:
            _fail(
                "hip_fgmres_family_result_ir_disposition_source_order_invalid",
                f"/source/audited/observations/{index}",
            )
        case = cases_by_hash.pop(observation.case_receipt_hash, None)
        if case is None:
            _fail(
                "hip_fgmres_family_result_ir_disposition_case_join_invalid",
                f"/source/audited/observations/{index}",
            )
        _validate_case_against_slot(case, expected_slot, observation, index=index)
        canonical.append(case)
    if cases_by_hash:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_set_invalid",
            "/source/cases",
        )
    canonical_cases = tuple(canonical)
    token = _source_token(
        result,
        transfer,
        family,
        cases,
        canonical_cases,
        retained_registry,
    )
    return _SourceSnapshotV1(
        audited_result=result,
        audited_receipt=result.receipt,
        transfer_result=transfer,
        family_result=family,
        source_cases=cases,
        canonical_cases=canonical_cases,
        registry=registry,
        token=token,
    )


def _validate_detached_composition(
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1,
    audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
) -> None:
    """Replay values only; no live audited result/context is retained or used."""

    if (
        type(audited_receipt) is not HipFgmresModelFamilyAuditedParityReceiptV2
        or type(bridges) is not tuple
        or len(bridges) != 7
        or any(type(row) is not HipFgmresResultIRBridgeResultV2 for row in bridges)
        or len({id(row) for row in bridges}) != 7
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_detached_source_invalid",
            "/source",
        )
    try:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(audited_receipt)
        registry = load_hip_fgmres_fixture_registry_v1()
        validate_hip_fgmres_fixture_registry_result_v1(registry)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_detached_source_invalid",
            "/source",
            f"{type(exc).__name__}: {exc}",
        )
    bindings = receipt.bindings
    if (
        bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_audited_schema_version != audited_receipt.schema_version
        or bindings.source_audited_capability_profile
        != audited_receipt.capability_profile
        or bindings.source_audited_attestation_id != audited_receipt.attestation_id
        or bindings.source_audited_receipt_hash != audited_receipt.receipt_hash
        or bindings.source_transfer_audit_receipt_hash
        != audited_receipt.bindings.source_transfer_audit_receipt_hash
        or bindings.source_family_receipt_hash
        != audited_receipt.bindings.source_family_receipt_hash
        or len(audited_receipt.observations) != 10
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_detached_binding_mismatch",
            "/bindings",
        )
    bridge_by_case: dict[str, HipFgmresResultIRBridgeResultV2] = {}
    for index, bridge in enumerate(bridges):
        validate_hip_fgmres_result_ir_v2(bridge)
        key = bridge.receipt.source_provenance.case_parity_receipt_hash
        if key in bridge_by_case:
            _fail(
                "hip_fgmres_family_result_ir_disposition_bridge_duplicate_case",
                f"/bridges/{index}",
            )
        bridge_by_case[key] = bridge
    canonical: list[HipFgmresResultIRBridgeResultV2] = []
    for index, (row, audited, slot) in enumerate(
        zip(
            receipt.observations,
            audited_receipt.observations,
            registry.slots,
            strict=True,
        )
    ):
        if (
            row.slot_id != slot.slot_id
            or row.slot_id != audited.slot_id
            or row.slot_registration_hash != slot.slot_registration_hash
            or row.case_fingerprint != slot.case_fingerprint
            or row.logical_case_key != audited.logical_case_key
            or row.matrix_cell_id != audited.matrix_cell_id
            or row.audited_triple_binding_hash != audited.triple_binding_hash
            or row.case_receipt_hash != audited.case_receipt_hash
            or row.model_ir_content_hash != slot.model.content_hash
            or row.execution_plan_hash != slot.execution_plan.plan_hash
            or row.cpu_result_hash != slot.cpu_result.result_hash
            or row.completion_export_context_id != audited.completion_export_context_id
            or row.completion_export_receipt_hash
            != audited.completion_export_receipt_hash
            or row.completion_export_payload_hash
            != audited.completion_export_payload_hash
            or row.device_identity_receipt_hash != audited.device_identity_receipt_hash
            or row.compiled_architecture != audited.compiled_architecture
            or row.runtime_architecture_base != audited.runtime_architecture_base
            or row.device_ordinal != audited.device_ordinal
            or row.device_uuid_bytes_hex != audited.device_uuid_bytes_hex
            or row.device_pci_bdf != audited.device_pci_bdf
            or row.cpu_status != slot.cpu_result.status
            or row.cpu_termination_code != slot.cpu_result.termination_code
            or row.solver_tolerance_passed
            is not slot.cpu_result.solver_tolerance_passed
            or row.authoritative_plan_tolerance_passed
            is not slot.cpu_result.authoritative_plan_tolerance_passed
        ):
            _fail(
                "hip_fgmres_family_result_ir_disposition_detached_row_mismatch",
                f"/observations/{index}",
            )
        bridge = bridge_by_case.pop(row.case_receipt_hash, None)
        if type(row) is HipFgmresModelFamilyResultIRReadyObservationV1:
            if bridge is None:
                _fail(
                    "hip_fgmres_family_result_ir_disposition_ready_bridge_missing",
                    f"/observations/{index}",
                )
            _validate_ready_row_against_bridge(row, bridge, slot, audited, index=index)
            canonical.append(bridge)
        elif type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1:
            if bridge is not None:
                _fail(
                    "hip_fgmres_family_result_ir_disposition_nonconverged_bridge_forbidden",
                    f"/observations/{index}",
                )
        else:  # protected by exact receipt validation
            _fail(
                "hip_fgmres_family_result_ir_disposition_observation_type_invalid",
                f"/observations/{index}",
            )
    if bridge_by_case:
        _fail(
            "hip_fgmres_family_result_ir_disposition_foreign_bridge",
            "/bridges",
        )
    if len(canonical) != len(bridges) or any(
        left is not right for left, right in zip(canonical, bridges, strict=True)
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_bridge_order_invalid",
            "/bridges",
        )


def _evaluate(
    source: _SourceSnapshotV1,
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
) -> tuple[
    HipFgmresModelFamilyResultIRDispositionReceiptV1,
    tuple[HipFgmresResultIRBridgeResultV2, ...],
]:
    if (
        type(bridges) is not tuple
        or not (1 <= len(bridges) <= 10)
        or any(type(row) is not HipFgmresResultIRBridgeResultV2 for row in bridges)
        or len({id(row) for row in bridges}) != len(bridges)
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_bridge_set_invalid",
            "/bridges",
        )
    bridge_by_case: dict[str, HipFgmresResultIRBridgeResultV2] = {}
    for index, bridge in enumerate(bridges):
        try:
            validate_hip_fgmres_result_ir_v2(bridge)
        except Exception as exc:
            _fail(
                "hip_fgmres_family_result_ir_disposition_bridge_invalid",
                f"/bridges/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        key = bridge.receipt.source_provenance.case_parity_receipt_hash
        if key in bridge_by_case:
            _fail(
                "hip_fgmres_family_result_ir_disposition_bridge_duplicate_case",
                f"/bridges/{index}",
            )
        bridge_by_case[key] = bridge

    source_case_by_hash = {
        case.receipt.receipt_hash: case for case in source.canonical_cases
    }
    for key in bridge_by_case:
        case = source_case_by_hash.get(key)
        if case is None:
            _fail(
                "hip_fgmres_family_result_ir_disposition_foreign_bridge",
                "/bridges",
            )
        if case._cpu_result.status != "converged":
            _fail(
                "hip_fgmres_family_result_ir_disposition_nonconverged_bridge_forbidden",
                "/bridges",
            )
        try:
            _validate_hip_fgmres_result_ir_v2_against_live_case(
                bridge_by_case[key],
                case,
            )
        except Exception as exc:
            _fail(
                "hip_fgmres_family_result_ir_disposition_bridge_live_case_invalid",
                "/bridges",
                f"{type(exc).__name__}: {exc}",
            )
    if len(bridges) != (HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_READY_COUNT_V1):
        _fail(
            "hip_fgmres_family_result_ir_disposition_bridge_set_invalid",
            "/bridges",
        )

    observations: list[HipFgmresModelFamilyResultIRDispositionObservationV1] = []
    canonical_bridges: list[HipFgmresResultIRBridgeResultV2] = []
    ready_plans: list[Any] = []
    all_plans: list[Any] = []
    audited_rows = source.audited_receipt.observations
    for index, (slot, case, audited) in enumerate(
        zip(
            source.registry.slots,
            source.canonical_cases,
            audited_rows,
            strict=True,
        )
    ):
        _validate_case_against_slot(case, slot, audited, index=index)
        plan = case._source_execution_plan
        cpu = case._cpu_result
        all_plans.append(plan)
        bridge = bridge_by_case.pop(case.receipt.receipt_hash, None)
        if cpu.status == "converged":
            if bridge is None:
                _fail(
                    "hip_fgmres_family_result_ir_disposition_ready_bridge_missing",
                    f"/observations/{index}",
                )
            observations.append(
                _ready_observation(slot, case, audited, bridge, index=index)
            )
            canonical_bridges.append(bridge)
            ready_plans.append(plan)
        elif cpu.status == "max_iterations":
            if bridge is not None:
                _fail(
                    "hip_fgmres_family_result_ir_disposition_nonconverged_bridge_forbidden",
                    f"/observations/{index}",
                )
            observations.append(
                _not_issued_observation(slot, case, audited, index=index)
            )
        else:
            _fail(
                "hip_fgmres_family_result_ir_disposition_terminal_status_unsupported",
                f"/observations/{index}/cpu_status",
            )
    if bridge_by_case:
        _fail(
            "hip_fgmres_family_result_ir_disposition_foreign_bridge",
            "/bridges",
        )
    ordered = tuple(observations)
    canonical_bridge_tuple = tuple(canonical_bridges)
    totals = _totals(ordered, tuple(all_plans), tuple(ready_plans), source)
    bindings = HipFgmresModelFamilyResultIRDispositionBindingsV1(
        registry_schema_version=HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
        fixture_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        registry_bytes_sha256=source.registry.registry_bytes_sha256,
        registry_hash=source.registry.registry_hash,
        source_audited_schema_version=source.audited_receipt.schema_version,
        source_audited_capability_profile=(source.audited_receipt.capability_profile),
        source_audited_attestation_id=source.audited_receipt.attestation_id,
        source_audited_receipt_hash=source.audited_receipt.receipt_hash,
        source_transfer_audit_receipt_hash=(
            source.audited_receipt.bindings.source_transfer_audit_receipt_hash
        ),
        source_family_receipt_hash=(
            source.audited_receipt.bindings.source_family_receipt_hash
        ),
        result_ir_schema_version=RESULT_IR_V2_SCHEMA_VERSION,
        result_ir_capability_profile=RESULT_IR_V2_CAPABILITY_PROFILE,
        result_ir_bridge_capability_profile=(
            HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE
        ),
        required_architecture_base=(
            HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_ARCHITECTURE_V1
        ),
        required_slot_ids=(
            HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1
        ),
    )
    claims = HipFgmresModelFamilyResultIRDispositionClaimsV1()
    attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1
            ),
            "registry_hash": source.registry.registry_hash,
            "source_audited_receipt_hash": source.audited_receipt.receipt_hash,
            "disposition_binding_hashes": [
                row.disposition_binding_hash for row in ordered
            ],
        }
    )
    draft = HipFgmresModelFamilyResultIRDispositionReceiptV1(
        status=HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=(
            HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_EVIDENCE_SCOPE_V1
        ),
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        observations=ordered,
        totals=totals,
        claims=claims,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(receipt)
    return receipt, canonical_bridge_tuple


def _ready_observation(
    slot: HipFgmresFixtureReplayV1,
    case: HipFgmresModelCaseParityResultV1,
    audited: Any,
    bridge: HipFgmresResultIRBridgeResultV2,
    *,
    index: int,
) -> HipFgmresModelFamilyResultIRReadyObservationV1:
    validate_hip_fgmres_result_ir_v2(bridge)
    case_receipt = case.receipt
    case_bindings = case_receipt.bindings
    cpu = case._cpu_result
    plan = case._source_execution_plan
    result_ir = bridge.receipt
    provenance = result_ir.source_provenance
    observation_result = case._observation_result
    device_result = case._device_identity_result
    try:
        observation_receipt = observation_result.receipt
        export_result = observation_result._source_export_result
        export_receipt = export_result.receipt
        device_receipt = device_result.receipt
    except AttributeError as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_authority_invalid",
            f"/observations/{index}/source",
            type(exc).__name__,
        )
    vector_by_name = {row.name: row for row in case_receipt.vectors}
    if set(vector_by_name) != {
        "solution_x",
        "true_residual",
        "true_residual_replay",
    }:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_vectors_invalid",
            f"/observations/{index}/source/vectors",
        )
    if (
        cpu.status != "converged"
        or cpu.solver_tolerance_passed is not True
        or cpu.authoritative_plan_tolerance_passed is not True
        or bridge.source_execution_plan is not plan
        or result_ir.input_bindings.execution_plan_hash != plan.plan_hash
        or result_ir.input_bindings.model_ir_content_hash
        != case_bindings.model_ir_content_hash
        or result_ir.input_bindings.evaluated_trial_state_hash
        != bridge.evaluated_trial_state.state_hash
        or result_ir.input_bindings.committed_state_hash
        != bridge.committed_state.state_hash
        or provenance.case_id != case_receipt.case_id
        or provenance.case_parity_receipt_hash != case_receipt.receipt_hash
        or provenance.terminal_observation_receipt_hash
        != case_bindings.terminal_observation_receipt_hash
        or provenance.completion_export_receipt_hash
        != case_bindings.completion_export_receipt_hash
        or provenance.completion_export_payload_hash
        != case_bindings.completion_export_payload_hash
        or provenance.device_identity_receipt_hash
        != case_bindings.device_identity_receipt_hash
        or provenance.solution_payload_sha256
        != vector_by_name["solution_x"].hip_or_candidate_sha256
        or provenance.exported_free_residual_payload_sha256
        != vector_by_name["true_residual"].hip_or_candidate_sha256
        or provenance.compiled_architecture != case_bindings.compiled_architecture
        or provenance.runtime_architecture_base
        != case_bindings.runtime_architecture_base
        or provenance.device_ordinal != case_bindings.device_ordinal
        or provenance.device_uuid_bytes_hex != case_bindings.device_uuid_bytes_hex
        or provenance.device_pci_bdf != case_bindings.device_pci_bdf
        or observation_receipt.receipt_hash
        != case_bindings.terminal_observation_receipt_hash
        or export_receipt.receipt_hash != case_bindings.completion_export_receipt_hash
        or export_receipt.payload_hash != case_bindings.completion_export_payload_hash
        or device_receipt.receipt_hash != case_bindings.device_identity_receipt_hash
        or audited.case_receipt_hash != case_receipt.receipt_hash
        or audited.completion_export_receipt_hash
        != case_bindings.completion_export_receipt_hash
        or audited.completion_export_payload_hash
        != case_bindings.completion_export_payload_hash
        or audited.device_identity_receipt_hash
        != case_bindings.device_identity_receipt_hash
        or audited.compiled_architecture != provenance.compiled_architecture
        or audited.runtime_architecture_base != provenance.runtime_architecture_base
        or audited.device_ordinal != provenance.device_ordinal
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_ready_cross_binding_invalid",
            f"/observations/{index}",
        )
    if (
        result_ir.claims.result_ir_verified is not True
        or result_ir.claims.result_ir_ready is not True
        or provenance.additional_device_operation_count != 0
        or provenance.additional_d2h_operation_count != 0
        or provenance.additional_solve_count != 0
        or provenance.additional_export_count != 0
        or provenance.fallback_count != 0
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_ready_claim_invalid",
            f"/observations/{index}/result_ir",
        )
    arrays = result_ir.arrays.ordered()
    byte_count = sum(row.byte_length for row in arrays)
    expected_bytes = (
        24 * plan.dof_count + 104 * plan.element_count + 8 * len(plan.free_dofs)
    )
    if len(arrays) != 6 or byte_count != expected_bytes:
        _fail(
            "hip_fgmres_family_result_ir_disposition_result_bytes_invalid",
            f"/observations/{index}/result_ir/arrays",
        )
    draft = HipFgmresModelFamilyResultIRReadyObservationV1(
        **_common_observation_fields(slot, case, audited),
        disposition="ready_result_ir_v2",
        cpu_status="converged",
        cpu_termination_code=cpu.termination_code,
        solver_tolerance_passed=True,
        authoritative_plan_tolerance_passed=True,
        result_id=result_ir.result_id,
        result_ir_hash=result_ir.result_ir_hash,
        numerical_result_hash=result_ir.numerical_result_hash,
        accepted_state_hash=bridge.accepted_state.state_hash,
        evaluated_trial_state_hash=bridge.evaluated_trial_state.state_hash,
        committed_state_hash=bridge.committed_state.state_hash,
        solution_payload_sha256=provenance.solution_payload_sha256,
        exported_free_residual_payload_sha256=(
            provenance.exported_free_residual_payload_sha256
        ),
        result_array_descriptor_hash=canonical_hash(result_ir.arrays.to_dict()),
        result_array_count=6,
        result_array_byte_count=byte_count,
        detached_raw_payload_byte_count=16 * len(plan.free_dofs),
        additional_device_operation_count=0,
        additional_d2h_operation_count=0,
        additional_solve_count=0,
        additional_export_count=0,
        fallback_count=0,
        disposition_binding_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        disposition_binding_hash=canonical_hash(
            _observation_payload(draft, include_binding_hash=False)
        ),
    )


def _validate_ready_row_against_bridge(
    row: HipFgmresModelFamilyResultIRReadyObservationV1,
    bridge: HipFgmresResultIRBridgeResultV2,
    slot: HipFgmresFixtureReplayV1,
    audited: Any,
    *,
    index: int,
) -> None:
    validate_hip_fgmres_result_ir_v2(bridge)
    result_ir = bridge.receipt
    provenance = result_ir.source_provenance
    plan = bridge.source_execution_plan
    arrays = result_ir.arrays.ordered()
    byte_count = sum(value.byte_length for value in arrays)
    if (
        plan.plan_hash != slot.execution_plan.plan_hash
        or result_ir.input_bindings.model_ir_content_hash != slot.model.content_hash
        or result_ir.input_bindings.execution_plan_hash != plan.plan_hash
        or provenance.case_id != row.case_id
        or provenance.case_parity_receipt_hash != row.case_receipt_hash
        or provenance.terminal_observation_receipt_hash
        != row.terminal_observation_receipt_hash
        or provenance.completion_export_receipt_hash
        != audited.completion_export_receipt_hash
        or provenance.completion_export_payload_hash
        != audited.completion_export_payload_hash
        or provenance.device_identity_receipt_hash
        != audited.device_identity_receipt_hash
        or provenance.compiled_architecture != audited.compiled_architecture
        or provenance.runtime_architecture_base != audited.runtime_architecture_base
        or provenance.device_ordinal != audited.device_ordinal
        or provenance.device_uuid_bytes_hex != audited.device_uuid_bytes_hex
        or provenance.device_pci_bdf != audited.device_pci_bdf
        or row.result_id != result_ir.result_id
        or row.result_ir_hash != result_ir.result_ir_hash
        or row.numerical_result_hash != result_ir.numerical_result_hash
        or row.accepted_state_hash != bridge.accepted_state.state_hash
        or row.evaluated_trial_state_hash != bridge.evaluated_trial_state.state_hash
        or row.committed_state_hash != bridge.committed_state.state_hash
        or row.solution_payload_sha256 != provenance.solution_payload_sha256
        or row.exported_free_residual_payload_sha256
        != provenance.exported_free_residual_payload_sha256
        or row.result_array_descriptor_hash
        != canonical_hash(result_ir.arrays.to_dict())
        or row.result_array_count != len(arrays)
        or row.result_array_byte_count != byte_count
        or row.detached_raw_payload_byte_count != 16 * len(plan.free_dofs)
        or row.additional_device_operation_count
        != provenance.additional_device_operation_count
        or row.additional_d2h_operation_count
        != provenance.additional_d2h_operation_count
        or row.additional_solve_count != provenance.additional_solve_count
        or row.additional_export_count != provenance.additional_export_count
        or row.fallback_count != provenance.fallback_count
        or result_ir.claims.result_ir_verified is not True
        or result_ir.claims.result_ir_ready is not True
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_detached_bridge_mismatch",
            f"/observations/{index}",
        )


def _not_issued_observation(
    slot: HipFgmresFixtureReplayV1,
    case: HipFgmresModelCaseParityResultV1,
    audited: Any,
    *,
    index: int,
) -> HipFgmresModelFamilyResultIRNotIssuedObservationV1:
    cpu = case._cpu_result
    if (
        cpu.status != "max_iterations"
        or cpu.termination_code != "max_iterations_exhausted"
        or cpu.solver_tolerance_passed is not False
        or cpu.authoritative_plan_tolerance_passed is not False
        or slot.cpu_result.status != cpu.status
        or slot.cpu_result.termination_code != cpu.termination_code
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_nonconverged_source_invalid",
            f"/observations/{index}",
        )
    draft = HipFgmresModelFamilyResultIRNotIssuedObservationV1(
        **_common_observation_fields(slot, case, audited),
        disposition="not_issued_nonconverged",
        cpu_status="max_iterations",
        cpu_termination_code="max_iterations_exhausted",
        solver_tolerance_passed=False,
        authoritative_plan_tolerance_passed=False,
        result_ir_absence_reason="source_not_converged",
        result_ir_materialized=False,
        disposition_binding_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        disposition_binding_hash=canonical_hash(
            _observation_payload(draft, include_binding_hash=False)
        ),
    )


def _common_observation_fields(
    slot: HipFgmresFixtureReplayV1,
    case: HipFgmresModelCaseParityResultV1,
    audited: Any,
) -> dict[str, Any]:
    bindings = case.receipt.bindings
    return {
        "slot_id": slot.slot_id,
        "slot_registration_hash": slot.slot_registration_hash,
        "case_fingerprint": slot.case_fingerprint,
        "logical_case_key": audited.logical_case_key,
        "matrix_cell_id": audited.matrix_cell_id,
        "audited_triple_binding_hash": audited.triple_binding_hash,
        "case_id": case.receipt.case_id,
        "case_receipt_hash": case.receipt.receipt_hash,
        "model_ir_content_hash": bindings.model_ir_content_hash,
        "execution_plan_hash": bindings.execution_plan_hash,
        "cpu_result_hash": bindings.cpu_result_hash,
        "terminal_observation_receipt_hash": (
            bindings.terminal_observation_receipt_hash
        ),
        "completion_export_context_id": bindings.completion_export_context_id,
        "completion_export_receipt_hash": (bindings.completion_export_receipt_hash),
        "completion_export_payload_hash": (bindings.completion_export_payload_hash),
        "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
        "compiled_architecture": bindings.compiled_architecture,
        "runtime_architecture_base": bindings.runtime_architecture_base,
        "device_ordinal": bindings.device_ordinal,
        "device_uuid_bytes_hex": bindings.device_uuid_bytes_hex,
        "device_pci_bdf": bindings.device_pci_bdf,
    }


def _validate_case_against_slot(
    case: HipFgmresModelCaseParityResultV1,
    slot: HipFgmresFixtureReplayV1,
    audited: Any,
    *,
    index: int,
) -> None:
    if type(case) is not HipFgmresModelCaseParityResultV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_type_invalid",
            f"/source/cases/{index}",
        )
    plan = case._source_execution_plan
    cpu = case._cpu_result
    bindings = case.receipt.bindings
    observation = case._observation_result
    device = case._device_identity_result
    try:
        observation_receipt = observation.receipt
        export_receipt = observation._source_export_result.receipt
        device_receipt = device.receipt
    except AttributeError as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_authority_invalid",
            f"/source/cases/{index}",
            type(exc).__name__,
        )
    if (
        slot.slot_id != audited.slot_id
        or case.receipt.receipt_hash != audited.case_receipt_hash
        or plan.plan_hash != slot.execution_plan.plan_hash
        or bindings.execution_plan_hash != plan.plan_hash
        or bindings.model_ir_content_hash != slot.model.content_hash
        or bindings.cpu_result_hash != cpu.result_hash
        or cpu.result_hash != slot.cpu_result.result_hash
        or cpu.status != slot.cpu_result.status
        or cpu.termination_code != slot.cpu_result.termination_code
        or bindings.terminal_observation_receipt_hash
        != observation_receipt.receipt_hash
        or bindings.completion_export_context_id != audited.completion_export_context_id
        or bindings.completion_export_receipt_hash != export_receipt.receipt_hash
        or bindings.completion_export_receipt_hash
        != audited.completion_export_receipt_hash
        or bindings.completion_export_payload_hash != export_receipt.payload_hash
        or bindings.completion_export_payload_hash
        != audited.completion_export_payload_hash
        or bindings.device_identity_receipt_hash != device_receipt.receipt_hash
        or bindings.device_identity_receipt_hash != audited.device_identity_receipt_hash
        or bindings.compiled_architecture != "gfx1030"
        or bindings.runtime_architecture_base != "gfx1030"
        or audited.compiled_architecture != "gfx1030"
        or audited.runtime_architecture_base != "gfx1030"
        or bindings.device_ordinal != audited.device_ordinal
        or bindings.device_uuid_bytes_hex != audited.device_uuid_bytes_hex
        or bindings.device_pci_bdf != audited.device_pci_bdf
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_case_cross_binding_invalid",
            f"/source/cases/{index}",
        )


def _totals(
    observations: tuple[HipFgmresModelFamilyResultIRDispositionObservationV1, ...],
    all_plans: tuple[Any, ...],
    ready_plans: tuple[Any, ...],
    source: _SourceSnapshotV1,
) -> HipFgmresModelFamilyResultIRDispositionTotalsV1:
    ready_rows = tuple(
        row
        for row in observations
        if type(row) is HipFgmresModelFamilyResultIRReadyObservationV1
    )
    not_issued = tuple(
        row
        for row in observations
        if type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1
    )
    values = {
        "required_slot_count": len(observations),
        "ready_result_ir_v2_count": len(ready_rows),
        "not_issued_nonconverged_count": len(not_issued),
        "package_global_dof_count": sum(row.dof_count for row in all_plans),
        "package_element_count": sum(row.element_count for row in all_plans),
        "package_free_dof_count": sum(len(row.free_dofs) for row in all_plans),
        "package_csr_nnz": sum(row.nnz for row in all_plans),
        "ready_global_dof_count": sum(row.dof_count for row in ready_plans),
        "ready_element_count": sum(row.element_count for row in ready_plans),
        "ready_free_dof_count": sum(len(row.free_dofs) for row in ready_plans),
        "ready_csr_nnz": sum(row.nnz for row in ready_plans),
        "ready_result_array_count": sum(row.result_array_count for row in ready_rows),
        "ready_result_array_byte_count": sum(
            row.result_array_byte_count for row in ready_rows
        ),
        "ready_detached_raw_payload_byte_count": sum(
            row.detached_raw_payload_byte_count for row in ready_rows
        ),
    }
    expected = {
        "required_slot_count": 10,
        "ready_result_ir_v2_count": 7,
        "not_issued_nonconverged_count": 3,
        "package_global_dof_count": 162,
        "package_element_count": 17,
        "package_free_dof_count": 97,
        "package_csr_nnz": 2196,
        "ready_global_dof_count": 90,
        "ready_element_count": 8,
        "ready_free_dof_count": 43,
        "ready_csr_nnz": 1116,
        "ready_result_array_count": 42,
        "ready_result_array_byte_count": 3336,
        "ready_detached_raw_payload_byte_count": 688,
    }
    if values != expected:
        _fail(
            "hip_fgmres_family_result_ir_disposition_totals_invalid",
            "/totals",
            f"expected={expected!r} actual={values!r}",
        )
    upstream = source.audited_receipt.totals
    if (
        upstream.completion_export_blocking_d2h_attempt_count != 30
        or upstream.completion_export_blocking_d2h_success_count != 30
        or upstream.completion_export_blocking_d2h_failure_count != 0
        or upstream.completion_export_byte_count != 4408
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_upstream_totals_invalid",
            "/source/audited/totals",
        )
    return HipFgmresModelFamilyResultIRDispositionTotalsV1(
        **values,
        upstream_completion_export_blocking_d2h_attempt_count=30,
        upstream_completion_export_blocking_d2h_success_count=30,
        upstream_completion_export_blocking_d2h_failure_count=0,
        upstream_completion_export_byte_count=4408,
        result_ir_projection_additional_device_operation_count=0,
        result_ir_projection_additional_d2h_operation_count=0,
        result_ir_projection_additional_solve_count=0,
        result_ir_projection_additional_export_count=0,
        result_ir_projection_fallback_count=0,
    )


def _source_token(
    audited: HipFgmresModelFamilyAuditedParityResultV2,
    transfer: HipFgmresModelFamilyHostTransferAuditResultV1,
    family: HipFgmresModelFamilyParityResultV2,
    source_cases: tuple[HipFgmresModelCaseParityResultV1, ...],
    canonical_cases: tuple[HipFgmresModelCaseParityResultV1, ...],
    retained_registry: HipFgmresFixtureRegistryResultV1,
) -> tuple[Any, ...]:
    return (
        id(audited),
        id(audited.receipt),
        audited.receipt.receipt_hash,
        id(transfer),
        id(transfer.receipt),
        transfer.receipt.receipt_hash,
        id(family),
        id(family.receipt),
        family.receipt.receipt_hash,
        id(source_cases),
        tuple(id(row) for row in source_cases),
        tuple(id(row) for row in canonical_cases),
        tuple(id(row.receipt) for row in canonical_cases),
        tuple(row.receipt.receipt_hash for row in canonical_cases),
        tuple(id(row._source_execution_plan) for row in canonical_cases),
        tuple(row._source_execution_plan.plan_hash for row in canonical_cases),
        tuple(id(row._cpu_result) for row in canonical_cases),
        tuple(row._cpu_result.result_hash for row in canonical_cases),
        id(retained_registry),
        retained_registry.registry_bytes_sha256,
        retained_registry.registry_hash,
    )


def _bridge_snapshot(bridge: HipFgmresResultIRBridgeResultV2) -> _BridgeSnapshotV1:
    validate_hip_fgmres_result_ir_v2(bridge)
    return _BridgeSnapshotV1(
        bridge=bridge,
        receipt=bridge.receipt,
        plan=bridge.source_execution_plan,
        accepted_state=bridge.accepted_state,
        evaluated_trial_state=bridge.evaluated_trial_state,
        committed_state=bridge.committed_state,
        source_provenance=bridge.receipt.source_provenance,
        result_ir_hash=bridge.receipt.result_ir_hash,
        plan_hash=bridge.source_execution_plan.plan_hash,
        accepted_state_hash=bridge.accepted_state.state_hash,
        evaluated_trial_state_hash=bridge.evaluated_trial_state.state_hash,
        committed_state_hash=bridge.committed_state.state_hash,
        provenance_hash=canonical_hash(bridge.receipt.source_provenance.to_dict()),
    )


def _validate_bridge_snapshot(
    bridge: HipFgmresResultIRBridgeResultV2,
    snapshot: _BridgeSnapshotV1,
    *,
    path: str,
) -> None:
    if (
        type(snapshot) is not _BridgeSnapshotV1
        or snapshot.bridge is not bridge
        or snapshot.receipt is not bridge.receipt
        or snapshot.plan is not bridge.source_execution_plan
        or snapshot.accepted_state is not bridge.accepted_state
        or snapshot.evaluated_trial_state is not bridge.evaluated_trial_state
        or snapshot.committed_state is not bridge.committed_state
        or snapshot.source_provenance is not bridge.receipt.source_provenance
        or snapshot.result_ir_hash != bridge.receipt.result_ir_hash
        or snapshot.plan_hash != bridge.source_execution_plan.plan_hash
        or snapshot.accepted_state_hash != bridge.accepted_state.state_hash
        or snapshot.evaluated_trial_state_hash
        != bridge.evaluated_trial_state.state_hash
        or snapshot.committed_state_hash != bridge.committed_state.state_hash
        or snapshot.provenance_hash
        != canonical_hash(bridge.receipt.source_provenance.to_dict())
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_bridge_identity_changed",
            path,
        )


def _validate_exact_receipt_types(
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1,
) -> None:
    if type(receipt) is not HipFgmresModelFamilyResultIRDispositionReceiptV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_receipt_type_invalid",
            "/",
        )
    if type(receipt.bindings) is not (
        HipFgmresModelFamilyResultIRDispositionBindingsV1
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_bindings_type_invalid",
            "/bindings",
        )
    if (
        type(receipt.observations) is not tuple
        or len(receipt.observations) != 10
        or any(
            type(row)
            not in (
                HipFgmresModelFamilyResultIRReadyObservationV1,
                HipFgmresModelFamilyResultIRNotIssuedObservationV1,
            )
            for row in receipt.observations
        )
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_observation_type_invalid",
            "/observations",
        )
    if type(receipt.totals) is not HipFgmresModelFamilyResultIRDispositionTotalsV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_totals_type_invalid",
            "/totals",
        )
    if type(receipt.claims) is not HipFgmresModelFamilyResultIRDispositionClaimsV1:
        _fail(
            "hip_fgmres_family_result_ir_disposition_claims_type_invalid",
            "/claims",
        )
    _require_exact_json_scalars(_receipt_payload(receipt, include_hash=True), "/")


def _validate_receipt_semantics(
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1,
) -> None:
    try:
        registry = load_hip_fgmres_fixture_registry_v1()
        validate_hip_fgmres_fixture_registry_result_v1(registry)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_result_ir_disposition_registry_invalid",
            "/bindings/registry_hash",
            f"{type(exc).__name__}: {exc}",
        )
    if (
        receipt.status != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or receipt.bindings.registry_schema_version
        != HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        or receipt.bindings.fixture_suite_id != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or receipt.bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or receipt.bindings.registry_hash != registry.registry_hash
        or receipt.bindings.source_audited_schema_version
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2
        or receipt.bindings.source_audited_capability_profile
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
        or receipt.bindings.result_ir_schema_version != RESULT_IR_V2_SCHEMA_VERSION
        or receipt.bindings.result_ir_capability_profile
        != RESULT_IR_V2_CAPABILITY_PROFILE
        or receipt.bindings.result_ir_bridge_capability_profile
        != HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE
        or receipt.bindings.required_architecture_base
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_ARCHITECTURE_V1
        or receipt.bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_result_ir_disposition_receipt_semantics_invalid",
            "/",
        )
    ready = tuple(
        row
        for row in receipt.observations
        if type(row) is HipFgmresModelFamilyResultIRReadyObservationV1
    )
    absent = tuple(
        row
        for row in receipt.observations
        if type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1
    )
    if len(ready) != 7 or len(absent) != 3:
        _fail(
            "hip_fgmres_family_result_ir_disposition_count_invalid",
            "/observations",
        )
    for index, (row, slot) in enumerate(
        zip(receipt.observations, registry.slots, strict=True)
    ):
        if (
            row.slot_registration_hash != slot.slot_registration_hash
            or row.case_fingerprint != slot.case_fingerprint
            or row.compiled_architecture != "gfx1030"
            or row.runtime_architecture_base != "gfx1030"
            or row.disposition_binding_hash
            != canonical_hash(_observation_payload(row, include_binding_hash=False))
        ):
            _fail(
                "hip_fgmres_family_result_ir_disposition_observation_invalid",
                f"/observations/{index}",
            )
        expected_disposition = (
            "ready_result_ir_v2"
            if slot.cpu_result.status == "converged"
            else "not_issued_nonconverged"
        )
        if row.disposition != expected_disposition:
            _fail(
                "hip_fgmres_family_result_ir_disposition_classification_invalid",
                f"/observations/{index}/disposition",
            )
    expected_totals = HipFgmresModelFamilyResultIRDispositionTotalsV1(
        required_slot_count=10,
        ready_result_ir_v2_count=7,
        not_issued_nonconverged_count=3,
        package_global_dof_count=162,
        package_element_count=17,
        package_free_dof_count=97,
        package_csr_nnz=2196,
        ready_global_dof_count=90,
        ready_element_count=8,
        ready_free_dof_count=43,
        ready_csr_nnz=1116,
        ready_result_array_count=42,
        ready_result_array_byte_count=3336,
        ready_detached_raw_payload_byte_count=688,
        upstream_completion_export_blocking_d2h_attempt_count=30,
        upstream_completion_export_blocking_d2h_success_count=30,
        upstream_completion_export_blocking_d2h_failure_count=0,
        upstream_completion_export_byte_count=4408,
        result_ir_projection_additional_device_operation_count=0,
        result_ir_projection_additional_d2h_operation_count=0,
        result_ir_projection_additional_solve_count=0,
        result_ir_projection_additional_export_count=0,
        result_ir_projection_fallback_count=0,
    )
    if receipt.totals != expected_totals:
        _fail(
            "hip_fgmres_family_result_ir_disposition_totals_invalid",
            "/totals",
        )
    if receipt.claims != HipFgmresModelFamilyResultIRDispositionClaimsV1():
        _fail(
            "hip_fgmres_family_result_ir_disposition_claims_invalid",
            "/claims",
        )
    expected_attestation = canonical_hash(
        {
            "capability_profile": receipt.capability_profile,
            "registry_hash": receipt.bindings.registry_hash,
            "source_audited_receipt_hash": (
                receipt.bindings.source_audited_receipt_hash
            ),
            "disposition_binding_hashes": [
                row.disposition_binding_hash for row in receipt.observations
            ],
        }
    )
    if receipt.attestation_id != expected_attestation:
        _fail(
            "hip_fgmres_family_result_ir_disposition_attestation_invalid",
            "/attestation_id",
        )


def _observation_payload(
    row: HipFgmresModelFamilyResultIRDispositionObservationV1,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = row.to_dict()
    if not include_binding_hash:
        payload.pop("disposition_binding_hash")
    return payload


def _receipt_payload(
    receipt: HipFgmresModelFamilyResultIRDispositionReceiptV1,
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


def _require_exact_json_scalars(value: Any, path: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _require_exact_json_scalars(item, f"{path.rstrip('/')}/{index}")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail(
                    "hip_fgmres_family_result_ir_disposition_json_type_invalid",
                    path,
                )
            _require_exact_json_scalars(item, f"{path.rstrip('/')}/{key}")
        return
    _fail(
        "hip_fgmres_family_result_ir_disposition_json_type_invalid",
        path,
        type(value).__name__,
    )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    schema = json.loads(raw.decode("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: Any) -> str:
    return " ".join(str(value).split())[:512]


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelFamilyResultIRDispositionV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_NOT_ISSUED_COUNT_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_READY_COUNT_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_STATUS_V1",
    "HipFgmresModelFamilyResultIRDispositionBindingsV1",
    "HipFgmresModelFamilyResultIRDispositionClaimsV1",
    "HipFgmresModelFamilyResultIRDispositionObservationV1",
    "HipFgmresModelFamilyResultIRDispositionReceiptV1",
    "HipFgmresModelFamilyResultIRDispositionResultV1",
    "HipFgmresModelFamilyResultIRDispositionTotalsV1",
    "HipFgmresModelFamilyResultIRDispositionV1Error",
    "HipFgmresModelFamilyResultIRNotIssuedObservationV1",
    "HipFgmresModelFamilyResultIRReadyObservationV1",
    "attest_hip_fgmres_model_family_result_ir_disposition_v1",
    "validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1",
    "validate_hip_fgmres_model_family_result_ir_disposition_result_v1",
]
