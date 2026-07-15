"""Exact three-slot DiagnosticIR companion for the fixed FGMRES family.

The fixed package suite intentionally contains three ``max_iterations``
cases.  The ResultIR disposition keeps those cases explicitly unissued; this
additive companion binds the same three live model-case authorities to
already-issued :class:`HipFgmresDiagnosticIRBridgeResultV1` objects.  A
diagnostic is an evaluated partial iterate, never a successful solution or a
committed analysis state.

The factory replays the live audited authority and exact non-recycled bridge
tokens before issuance.  The issued result retains only detached receipts,
bridges, and a process-local issuance record, so validation remains possible
after the HIP contexts close.  The factory performs no solve, export, device
operation, copy, fallback, or state commit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.diagnostic_ir_v1 import (
    DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE,
    DIAGNOSTIC_IR_V1_SCHEMA_VERSION,
)

from .fgmres_diagnostic_ir_v1 import (
    HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE,
    HipFgmresDiagnosticIRBridgeResultV1,
    _validate_hip_fgmres_diagnostic_ir_v1_against_live_case,
    validate_hip_fgmres_diagnostic_ir_v1,
)
from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
    validate_hip_fgmres_fixture_registry_result_v1,
)
from .fgmres_model_family_audited_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2,
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2,
    HipFgmresModelFamilyAuditedParityReceiptV2,
    HipFgmresModelFamilyAuditedParityResultV2,
    validate_hip_fgmres_model_family_audited_parity_receipt_v2,
)
from .fgmres_model_family_result_ir_disposition_v1 import (
    HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1,
    HipFgmresModelFamilyResultIRDispositionResultV1,
    HipFgmresModelFamilyResultIRNotIssuedObservationV1,
    _capture_live_source,
    validate_hip_fgmres_model_family_result_ir_disposition_result_v1,
)


HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-model-family-diagnostic-ir.v1"
)
HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_package_gfx1030_three_nonconverged_diagnostic_ir_v1"
)
HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_STATUS_V1 = (
    "exact_gfx1030_three_nonconverged_diagnostic_ir_v1_verified"
)
HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_EVIDENCE_SCOPE_V1 = (
    "process_local_registry_bound_unsigned_nonpersistent_nonpromoting"
)
HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1 = (
    "frame_single_rotated_local_axis_bending",
    "recurrence_later_restart_partial_final_cycle",
    "recurrence_exact_full_final_cycle_guard",
)

_SCHEMA_RESOURCE = "hip_fgmres_model_family_diagnostic_ir_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class HipFgmresModelFamilyDiagnosticIRV1Error(RuntimeError):
    """Stable fail-closed family DiagnosticIR composition error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyDiagnosticIRBindingsV1:
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
    source_result_ir_disposition_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-family-result-ir-disposition.v1"
    ]
    source_result_ir_disposition_capability_profile: Literal[
        "phase0_exact_package_gfx1030_ten_slot_result_ir_v2_disposition"
    ]
    source_result_ir_disposition_attestation_id: str
    source_result_ir_disposition_receipt_hash: str
    diagnostic_ir_schema_version: Literal["structural-analysis-diagnostic-ir.v1"]
    diagnostic_ir_capability_profile: Literal[
        "hip_source_bound_fgmres_max_iterations_partial_iterate"
    ]
    diagnostic_ir_bridge_capability_profile: Literal[
        "hip_fgmres_retained_max_iterations_diagnostic_ir_v1"
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
class HipFgmresModelFamilyDiagnosticIRObservationV1:
    slot_id: str
    disposition: Literal["ready_diagnostic_ir_v1"]
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
    terminal_outcome_hash: str
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
    iteration_count: int
    restart_count: int
    solver_tolerance_passed: Literal[False]
    authoritative_plan_tolerance_passed: Literal[False]
    diagnostic_id: str
    diagnostic_ir_hash: str
    numerical_diagnostic_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: None
    rollback_state_hash: str
    source_solution_payload_sha256: str
    exported_free_residual_payload_sha256: str
    solve_record_payload_sha256: str
    diagnostic_termination_hash: str
    diagnostic_array_descriptor_hash: str
    diagnostic_array_count: Literal[3]
    diagnostic_array_byte_count: int
    detached_raw_export_payload_byte_count: int
    upstream_completion_export_blocking_d2h_attempt_count: Literal[3]
    upstream_completion_export_blocking_d2h_success_count: Literal[3]
    upstream_completion_export_blocking_d2h_failure_count: Literal[0]
    sparse_residual_replay_count: Literal[1]
    additional_device_operation_count: Literal[0]
    additional_d2h_operation_count: Literal[0]
    additional_solve_count: Literal[0]
    additional_export_count: Literal[0]
    fallback_count: Literal[0]
    state_commit_count: Literal[0]
    diagnostic_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyDiagnosticIRTotalsV1:
    required_diagnostic_slot_count: Literal[3]
    ready_result_ir_v2_count: Literal[7]
    ready_diagnostic_ir_v1_count: Literal[3]
    diagnostic_global_dof_count: Literal[72]
    diagnostic_element_count: Literal[9]
    diagnostic_free_dof_count: Literal[54]
    diagnostic_csr_nnz: Literal[1080]
    diagnostic_array_count: Literal[9]
    diagnostic_array_byte_count: Literal[1584]
    diagnostic_detached_raw_export_payload_byte_count: Literal[1872]
    upstream_completion_export_blocking_d2h_attempt_count: Literal[9]
    upstream_completion_export_blocking_d2h_success_count: Literal[9]
    upstream_completion_export_blocking_d2h_failure_count: Literal[0]
    upstream_completion_export_byte_count: Literal[1872]
    sparse_residual_replay_count: Literal[3]
    diagnostic_projection_additional_device_operation_count: Literal[0]
    diagnostic_projection_additional_d2h_operation_count: Literal[0]
    diagnostic_projection_additional_solve_count: Literal[0]
    diagnostic_projection_additional_export_count: Literal[0]
    diagnostic_projection_fallback_count: Literal[0]
    diagnostic_projection_state_commit_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyDiagnosticIRClaimsV1:
    fixed_package_registry_replayed: Literal[True] = True
    audited_ten_slot_authority_replayed_at_issuance: Literal[True] = True
    source_result_ir_disposition_replayed_unchanged: Literal[True] = True
    seven_converged_result_ir_v2_preserved: Literal[True] = True
    three_nonconverged_diagnostic_ir_v1_verified: Literal[True] = True
    exact_three_diagnostic_bridge_identity_bound: Literal[True] = True
    case_plan_terminal_export_device_cross_bound: Literal[True] = True
    partial_iterates_preserved: Literal[True] = True
    evaluated_trial_states_verified: Literal[True] = True
    nonconverged_state_commit_zero: Literal[True] = True
    sparse_residual_replayed_for_each_diagnostic: Literal[True] = True
    descriptor_only_family_manifest: Literal[True] = True
    post_close_detached_value_validation_supported: Literal[True] = True
    composition_factory_reuses_retained_authorities_only: Literal[True] = True
    diagnostic_projection_additional_device_operation_zero: Literal[True] = True
    diagnostic_projection_additional_d2h_zero: Literal[True] = True
    diagnostic_projection_additional_solve_zero: Literal[True] = True
    diagnostic_projection_additional_export_zero: Literal[True] = True
    diagnostic_projection_fallback_zero: Literal[True] = True
    registry_validation_cpu_reference_replay_zero_proven: Literal[False] = False
    exact_ten_slot_result_ir_v2_ready: Literal[False] = False
    all_ten_solution_ready: Literal[False] = False
    all_ten_converged: Literal[False] = False
    diagnostic_ir_is_solution_result: Literal[False] = False
    nonconverged_state_committed: Literal[False] = False
    external_gfx1100_diagnostic_ir_verified: Literal[False] = False
    full_model_family_diagnostic_ir_verified: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    hostile_same_process_mutation_or_interposition_resistance: Literal[False] = False
    signed_evidence: Literal[False] = False
    persistent_external_log_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    nonlinear_dynamic_shell_solid_contact_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresModelFamilyDiagnosticIRReceiptV1:
    status: Literal["exact_gfx1030_three_nonconverged_diagnostic_ir_v1_verified"]
    attestation_id: str
    evidence_scope: Literal[
        "process_local_registry_bound_unsigned_nonpersistent_nonpromoting"
    ]
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresModelFamilyDiagnosticIRBindingsV1
    observations: tuple[HipFgmresModelFamilyDiagnosticIRObservationV1, ...]
    totals: HipFgmresModelFamilyDiagnosticIRTotalsV1
    claims: HipFgmresModelFamilyDiagnosticIRClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _CompositionSourceV1:
    audited: Any
    disposition: HipFgmresModelFamilyResultIRDispositionResultV1
    disposition_token: tuple[Any, ...]
    token: tuple[Any, ...]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _DiagnosticBridgeSnapshotV1:
    bridge: HipFgmresDiagnosticIRBridgeResultV1
    receipt: Any
    plan: Any
    accepted_state: Any
    evaluated_trial_state: Any
    rollback_state: Any
    source_seal: Any
    source_provenance: Any
    diagnostic_ir_hash: str
    plan_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    rollback_state_hash: str
    provenance_hash: str
    capture_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FamilyDiagnosticIssuanceV1:
    mint: object
    audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    disposition: HipFgmresModelFamilyResultIRDispositionResultV1
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1
    bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...]
    bridge_snapshots: tuple[_DiagnosticBridgeSnapshotV1, ...]
    receipt_hash: str
    receipt_payload_hash: str
    audited_receipt_hash: str
    audited_payload_hash: str
    disposition_receipt_hash: str
    disposition_payload_hash: str


@dataclass(frozen=True, repr=False, eq=False)
class HipFgmresModelFamilyDiagnosticIRResultV1:
    """Issued three-slot diagnostic companion, valid after context close."""

    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1
    _source_audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2
    _source_result_ir_disposition: HipFgmresModelFamilyResultIRDispositionResultV1
    _diagnostic_bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...]

    @property
    def diagnostic_bridges(self) -> tuple[HipFgmresDiagnosticIRBridgeResultV1, ...]:
        return self._diagnostic_bridges

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_model_family_diagnostic_ir_result_v1(self)
        return self.receipt.to_dict()


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresModelFamilyDiagnosticIRResultV1,
    _FamilyDiagnosticIssuanceV1,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_model_family_diagnostic_ir_v1(
    audited_result: HipFgmresModelFamilyAuditedParityResultV2,
    result_ir_disposition_result: HipFgmresModelFamilyResultIRDispositionResultV1,
    diagnostic_bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...],
) -> HipFgmresModelFamilyDiagnosticIRResultV1:
    """Compose exact diagnostics for the three canonical max-iteration slots."""

    first = _capture_sources(
        audited_result,
        result_ir_disposition_result,
        validate_disposition=True,
    )
    receipt, canonical = _evaluate(first, diagnostic_bridges, require_live=True)
    try:
        second = _capture_sources(
            audited_result,
            result_ir_disposition_result,
            validate_disposition=False,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_source_changed",
            "/source",
            f"{type(exc).__name__}: {exc}",
        )
    if second.token != first.token:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_source_changed",
            "/source",
        )
    try:
        final = _capture_sources(
            audited_result,
            result_ir_disposition_result,
            validate_disposition=False,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_source_changed",
            "/source",
            f"{type(exc).__name__}: {exc}",
        )
    if final.token != second.token:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_source_changed",
            "/source",
        )
    final_receipt, final_canonical = _evaluate(
        final,
        canonical,
        require_live=True,
    )
    if final_receipt != receipt or final_canonical != canonical:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_composition_changed",
            "/source",
        )
    receipt = final_receipt
    canonical = final_canonical
    result = HipFgmresModelFamilyDiagnosticIRResultV1(
        receipt=receipt,
        _source_audited_receipt=final.audited.audited_receipt,
        _source_result_ir_disposition=result_ir_disposition_result,
        _diagnostic_bridges=canonical,
    )
    issuance = _FamilyDiagnosticIssuanceV1(
        mint=object(),
        audited_receipt=final.audited.audited_receipt,
        disposition=result_ir_disposition_result,
        receipt=receipt,
        bridges=canonical,
        bridge_snapshots=tuple(_bridge_snapshot(row) for row in canonical),
        receipt_hash=receipt.receipt_hash,
        receipt_payload_hash=canonical_hash(
            _receipt_payload(receipt, include_hash=True)
        ),
        audited_receipt_hash=final.audited.audited_receipt.receipt_hash,
        audited_payload_hash=canonical_hash(final.audited.audited_receipt.to_dict()),
        disposition_receipt_hash=result_ir_disposition_result.receipt.receipt_hash,
        disposition_payload_hash=canonical_hash(
            result_ir_disposition_result.receipt.to_dict()
        ),
    )
    with _ISSUANCE_LOCK:
        if result in _ISSUANCES:  # pragma: no cover
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_issuance_duplicate",
                "/issuance",
            )
        _ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_model_family_diagnostic_ir_result_v1(result)
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_model_family_diagnostic_ir_result_v1(
    result: HipFgmresModelFamilyDiagnosticIRResultV1,
) -> HipFgmresModelFamilyDiagnosticIRResultV1:
    """Replay an issued result without consulting live HIP/audit contexts."""

    if type(result) is not HipFgmresModelFamilyDiagnosticIRResultV1:
        _fail("hip_fgmres_family_diagnostic_ir_v1_result_type_invalid", "/")
    validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(result.receipt)
    if (
        type(result._source_audited_receipt)
        is not HipFgmresModelFamilyAuditedParityReceiptV2
        or type(result._source_result_ir_disposition)
        is not HipFgmresModelFamilyResultIRDispositionResultV1
        or type(result._diagnostic_bridges) is not tuple
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_source_type_invalid",
            "/source",
        )
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _FamilyDiagnosticIssuanceV1:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_issuance_unavailable",
            "/issuance",
        )
    if (
        issuance.receipt is not result.receipt
        or issuance.audited_receipt is not result._source_audited_receipt
        or issuance.disposition is not result._source_result_ir_disposition
        or issuance.bridges is not result._diagnostic_bridges
        or len(issuance.bridge_snapshots) != len(result._diagnostic_bridges)
        or issuance.receipt_hash != result.receipt.receipt_hash
        or issuance.receipt_payload_hash
        != canonical_hash(_receipt_payload(result.receipt, include_hash=True))
        or issuance.audited_receipt_hash != result._source_audited_receipt.receipt_hash
        or issuance.audited_payload_hash
        != canonical_hash(result._source_audited_receipt.to_dict())
        or issuance.disposition_receipt_hash
        != result._source_result_ir_disposition.receipt.receipt_hash
        or issuance.disposition_payload_hash
        != canonical_hash(result._source_result_ir_disposition.receipt.to_dict())
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_issuance_binding_mismatch",
            "/issuance",
        )
    for index, (bridge, snapshot) in enumerate(
        zip(
            result._diagnostic_bridges,
            issuance.bridge_snapshots,
            strict=True,
        )
    ):
        validate_hip_fgmres_diagnostic_ir_v1(bridge)
        _validate_bridge_snapshot(bridge, snapshot, path=f"/bridges/{index}")
    _validate_detached_composition(
        result.receipt,
        result._source_audited_receipt,
        result._source_result_ir_disposition,
        result._diagnostic_bridges,
        bridges_validated=True,
    )
    return result


def validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1,
) -> HipFgmresModelFamilyDiagnosticIRReceiptV1:
    """Validate detached structure without granting process-local provenance."""

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
            "hip_fgmres_family_diagnostic_ir_v1_schema_invalid",
            path or "/",
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_receipt_hash_invalid",
            "/receipt_hash",
        )
    _validate_receipt_semantics(receipt)
    return receipt


def _capture_sources(
    audited_result: HipFgmresModelFamilyAuditedParityResultV2,
    disposition: HipFgmresModelFamilyResultIRDispositionResultV1,
    *,
    validate_disposition: bool,
) -> _CompositionSourceV1:
    try:
        audited = _capture_live_source(audited_result)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_audited_source_invalid",
            "/source/audited",
            f"{type(exc).__name__}: {exc}",
        )
    if type(disposition) is not HipFgmresModelFamilyResultIRDispositionResultV1:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_disposition_type_invalid",
            "/source/result_ir_disposition",
        )
    if validate_disposition:
        try:
            validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
                disposition
            )
        except Exception as exc:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_disposition_invalid",
                "/source/result_ir_disposition",
                f"{type(exc).__name__}: {exc}",
            )
    receipt = disposition.receipt
    if (
        disposition._source_audited_receipt is not audited.audited_receipt
        or receipt.bindings.source_audited_attestation_id
        != audited.audited_receipt.attestation_id
        or receipt.bindings.source_audited_receipt_hash
        != audited.audited_receipt.receipt_hash
        or receipt.claims.seven_converged_result_ir_v2_verified is not True
        or receipt.claims.three_nonconverged_result_ir_v2_not_issued is not True
        or receipt.claims.exact_ten_slot_result_ir_v2_ready is not False
        or receipt.claims.all_ten_solution_ready is not False
        or len(receipt.observations) != 10
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_disposition_binding_invalid",
            "/source/result_ir_disposition",
        )
    nonconverged = tuple(
        row
        for row in receipt.observations
        if type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1
    )
    if tuple(
        row.slot_id for row in nonconverged
    ) != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1 or any(
        row.disposition != "not_issued_nonconverged"
        or row.result_ir_absence_reason != "source_not_converged"
        or row.result_ir_materialized is not False
        for row in nonconverged
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_disposition_truth_invalid",
            "/source/result_ir_disposition/observations",
        )
    disposition_token = (
        id(disposition),
        id(receipt),
        receipt.receipt_hash,
        canonical_hash(receipt.to_dict()),
        id(disposition._source_audited_receipt),
        disposition._source_audited_receipt.receipt_hash,
        id(disposition._result_ir_bridges),
        tuple(id(row) for row in disposition._result_ir_bridges),
        tuple(row.receipt.result_ir_hash for row in disposition._result_ir_bridges),
    )
    return _CompositionSourceV1(
        audited=audited,
        disposition=disposition,
        disposition_token=disposition_token,
        token=(audited.token, disposition_token),
    )


def _evaluate(
    source: _CompositionSourceV1,
    bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...],
    *,
    require_live: bool,
) -> tuple[
    HipFgmresModelFamilyDiagnosticIRReceiptV1,
    tuple[HipFgmresDiagnosticIRBridgeResultV1, ...],
]:
    if (
        type(bridges) is not tuple
        or len(bridges) != 3
        or any(type(row) is not HipFgmresDiagnosticIRBridgeResultV1 for row in bridges)
        or len({id(row) for row in bridges}) != 3
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_bridge_set_invalid",
            "/bridges",
        )
    audited_rows = {
        row.slot_id: row for row in source.audited.audited_receipt.observations
    }
    disposition_rows = {
        row.slot_id: row for row in source.disposition.receipt.observations
    }
    cases = {row.receipt.receipt_hash: row for row in source.audited.canonical_cases}
    bridge_by_case_hash: dict[str, HipFgmresDiagnosticIRBridgeResultV1] = {}
    for index, bridge in enumerate(bridges):
        try:
            validate_hip_fgmres_diagnostic_ir_v1(bridge)
            case_hash = bridge._source_seal.case_parity_receipt_hash
        except Exception as exc:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_bridge_invalid",
                f"/bridges/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        if case_hash in bridge_by_case_hash:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_bridge_case_duplicate",
                "/bridges",
            )
        bridge_by_case_hash[case_hash] = bridge

    observations: list[HipFgmresModelFamilyDiagnosticIRObservationV1] = []
    canonical: list[HipFgmresDiagnosticIRBridgeResultV1] = []
    slots: list[HipFgmresFixtureReplayV1] = []
    for index, slot_id in enumerate(
        HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1
    ):
        slot = source.audited.registry.slot(slot_id)
        audited_row = audited_rows.get(slot_id)
        disposition_row = disposition_rows.get(slot_id)
        if (
            audited_row is None
            or type(disposition_row)
            is not HipFgmresModelFamilyResultIRNotIssuedObservationV1
        ):
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_source_join_invalid",
                f"/observations/{index}",
            )
        case = cases.get(audited_row.case_receipt_hash)
        bridge = bridge_by_case_hash.pop(audited_row.case_receipt_hash, None)
        if case is None or bridge is None:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_bridge_join_invalid",
                f"/observations/{index}",
            )
        if require_live:
            try:
                _validate_hip_fgmres_diagnostic_ir_v1_against_live_case(
                    bridge,
                    case,
                )
            except Exception as exc:
                _fail(
                    "hip_fgmres_family_diagnostic_ir_v1_live_bridge_invalid",
                    f"/bridges/{index}",
                    f"{type(exc).__name__}: {exc}",
                )
        observation = _observation_from_bridge(
            slot,
            audited_row,
            disposition_row,
            bridge,
            index=index,
            bridge_validated=True,
        )
        if require_live:
            try:
                _validate_hip_fgmres_diagnostic_ir_v1_against_live_case(
                    bridge,
                    case,
                )
            except Exception as exc:
                _fail(
                    "hip_fgmres_family_diagnostic_ir_v1_live_bridge_changed",
                    f"/bridges/{index}",
                    f"{type(exc).__name__}: {exc}",
                )
        observations.append(observation)
        canonical.append(bridge)
        slots.append(slot)
    if bridge_by_case_hash:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_foreign_bridge",
            "/bridges",
        )
    ordered = tuple(observations)
    canonical_bridges = tuple(canonical)
    totals = _totals(ordered, tuple(slots), audited_rows)
    bindings = HipFgmresModelFamilyDiagnosticIRBindingsV1(
        registry_schema_version=HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
        fixture_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        registry_bytes_sha256=source.audited.registry.registry_bytes_sha256,
        registry_hash=source.audited.registry.registry_hash,
        source_audited_schema_version=(
            HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2
        ),
        source_audited_capability_profile=(
            HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
        ),
        source_audited_attestation_id=source.audited.audited_receipt.attestation_id,
        source_audited_receipt_hash=source.audited.audited_receipt.receipt_hash,
        source_result_ir_disposition_schema_version=(
            HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1
        ),
        source_result_ir_disposition_capability_profile=(
            HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1
        ),
        source_result_ir_disposition_attestation_id=(
            source.disposition.receipt.attestation_id
        ),
        source_result_ir_disposition_receipt_hash=(
            source.disposition.receipt.receipt_hash
        ),
        diagnostic_ir_schema_version=DIAGNOSTIC_IR_V1_SCHEMA_VERSION,
        diagnostic_ir_capability_profile=DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE,
        diagnostic_ir_bridge_capability_profile=(
            HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE
        ),
        required_architecture_base=(
            HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_ARCHITECTURE_V1
        ),
        required_slot_ids=HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1,
    )
    attestation_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1,
            "registry_hash": bindings.registry_hash,
            "source_audited_receipt_hash": bindings.source_audited_receipt_hash,
            "source_result_ir_disposition_receipt_hash": (
                bindings.source_result_ir_disposition_receipt_hash
            ),
            "observation_binding_hashes": [
                row.diagnostic_binding_hash for row in ordered
            ],
        }
    )
    draft = HipFgmresModelFamilyDiagnosticIRReceiptV1(
        status=HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        observations=ordered,
        totals=totals,
        claims=HipFgmresModelFamilyDiagnosticIRClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(receipt)
    return receipt, canonical_bridges


def _observation_from_bridge(
    slot: HipFgmresFixtureReplayV1,
    audited: Any,
    disposition: HipFgmresModelFamilyResultIRNotIssuedObservationV1,
    bridge: HipFgmresDiagnosticIRBridgeResultV1,
    *,
    index: int,
    bridge_validated: bool = False,
) -> HipFgmresModelFamilyDiagnosticIRObservationV1:
    if not bridge_validated:
        try:
            validate_hip_fgmres_diagnostic_ir_v1(bridge)
        except Exception as exc:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_bridge_invalid",
                f"/observations/{index}/diagnostic",
                f"{type(exc).__name__}: {exc}",
            )
    diagnostic = bridge.receipt
    plan = bridge.source_execution_plan
    seal = bridge._source_seal
    provenance = diagnostic.source_provenance
    termination = diagnostic.termination
    arrays = diagnostic.arrays.ordered()
    array_bytes = sum(row.byte_length for row in arrays)
    raw_export_bytes = (
        len(seal.solution_x) + len(seal.true_residual) + len(seal.solve_record)
    )
    expected_array_bytes = 16 * plan.dof_count + 8 * len(plan.free_dofs)
    expected_raw_bytes = audited.completion_export_byte_count
    cpu = slot.cpu_result
    if (
        slot.slot_id != audited.slot_id
        or slot.slot_id != disposition.slot_id
        or audited.case_receipt_hash != disposition.case_receipt_hash
        or seal.case_parity_receipt_hash != audited.case_receipt_hash
        or seal.case_id != disposition.case_id
        or plan.plan_hash != slot.execution_plan.plan_hash
        or plan.nnz != slot.execution_plan.nnz
        or diagnostic.input_bindings.model_ir_content_hash != slot.model.content_hash
        or diagnostic.input_bindings.execution_plan_hash != plan.plan_hash
        or seal.source_execution_plan_hash != plan.plan_hash
        or seal.cpu_result_hash != cpu.result_hash
        or disposition.cpu_result_hash != cpu.result_hash
        or termination.status != "max_iterations"
        or termination.termination_code != "max_iterations_exhausted"
        or cpu.status != "max_iterations"
        or cpu.termination_code != "max_iterations_exhausted"
        or termination.counters.iteration_count != cpu.iteration_count
        or termination.counters.restart_count != cpu.restart_count
        or termination.metrics.solver_tolerance_passed is not False
        or termination.metrics.authoritative_plan_tolerance_passed is not False
        or disposition.solver_tolerance_passed is not False
        or disposition.authoritative_plan_tolerance_passed is not False
        or seal.terminal_observation_receipt_hash
        != disposition.terminal_observation_receipt_hash
        or seal.completion_export_context_id != disposition.completion_export_context_id
        or seal.completion_export_receipt_hash != audited.completion_export_receipt_hash
        or seal.completion_export_receipt_hash
        != disposition.completion_export_receipt_hash
        or seal.completion_export_payload_hash != audited.completion_export_payload_hash
        or seal.completion_export_payload_hash
        != disposition.completion_export_payload_hash
        or seal.device_identity_receipt_hash != audited.device_identity_receipt_hash
        or seal.device_identity_receipt_hash != disposition.device_identity_receipt_hash
        or audited.compiled_architecture != "gfx1030"
        or audited.runtime_architecture_base != "gfx1030"
        or disposition.compiled_architecture != "gfx1030"
        or disposition.runtime_architecture_base != "gfx1030"
        or disposition.device_ordinal != audited.device_ordinal
        or disposition.device_uuid_bytes_hex != audited.device_uuid_bytes_hex
        or disposition.device_pci_bdf != audited.device_pci_bdf
        or diagnostic.input_bindings.accepted_state_hash
        != bridge.accepted_state.state_hash
        or diagnostic.input_bindings.evaluated_trial_state_hash
        != bridge.evaluated_trial_state.state_hash
        or diagnostic.input_bindings.committed_state_hash is not None
        or bridge.rollback_state is not bridge.accepted_state
        or bridge.rollback_state.state_hash != bridge.accepted_state.state_hash
        or diagnostic.claims.diagnostic_ready is not True
        or diagnostic.claims.diagnostic_ir_verified is not True
        or diagnostic.claims.partial_iterate_preserved is not True
        or diagnostic.claims.nonconverged_max_iterations_verified is not True
        or diagnostic.claims.evaluated_trial_state_verified is not True
        or diagnostic.claims.true_residual_replayed is not True
        or diagnostic.claims.restart_history_preserved is not True
        or diagnostic.claims.rollback_to_accepted_state_verified is not True
        or diagnostic.claims.committed_state_created is not False
        or diagnostic.claims.analysis_state_committed is not False
        or diagnostic.claims.solution_ready is not False
        or diagnostic.claims.result_ir_ready is not False
        or diagnostic.claims.restart_checkpoint_ready is not False
        or diagnostic.claims.code_check_ready is not False
        or diagnostic.claims.optimization_consumable is not False
        or provenance.additional_device_operation_count != 0
        or provenance.additional_d2h_operation_count != 0
        or provenance.additional_solve_count != 0
        or provenance.additional_export_count != 0
        or provenance.fallback_count != 0
        or len(arrays) != 3
        or array_bytes != expected_array_bytes
        or raw_export_bytes != expected_raw_bytes
        or audited.completion_export_blocking_d2h_attempt_count != 3
        or audited.completion_export_blocking_d2h_success_count != 3
        or audited.completion_export_blocking_d2h_failure_count != 0
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_cross_binding_invalid",
            f"/observations/{index}",
        )
    draft = HipFgmresModelFamilyDiagnosticIRObservationV1(
        slot_id=slot.slot_id,
        disposition="ready_diagnostic_ir_v1",
        slot_registration_hash=slot.slot_registration_hash,
        case_fingerprint=slot.case_fingerprint,
        logical_case_key=audited.logical_case_key,
        matrix_cell_id=audited.matrix_cell_id,
        audited_triple_binding_hash=audited.triple_binding_hash,
        case_id=seal.case_id,
        case_receipt_hash=seal.case_parity_receipt_hash,
        model_ir_content_hash=diagnostic.input_bindings.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        cpu_result_hash=seal.cpu_result_hash,
        terminal_observation_receipt_hash=(seal.terminal_observation_receipt_hash),
        terminal_outcome_hash=seal.terminal_outcome_hash,
        completion_export_context_id=disposition.completion_export_context_id,
        completion_export_receipt_hash=seal.completion_export_receipt_hash,
        completion_export_payload_hash=seal.completion_export_payload_hash,
        device_identity_receipt_hash=seal.device_identity_receipt_hash,
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=audited.device_ordinal,
        device_uuid_bytes_hex=audited.device_uuid_bytes_hex,
        device_pci_bdf=audited.device_pci_bdf,
        cpu_status="max_iterations",
        cpu_termination_code="max_iterations_exhausted",
        iteration_count=termination.counters.iteration_count,
        restart_count=termination.counters.restart_count,
        solver_tolerance_passed=False,
        authoritative_plan_tolerance_passed=False,
        diagnostic_id=diagnostic.diagnostic_id,
        diagnostic_ir_hash=diagnostic.diagnostic_ir_hash,
        numerical_diagnostic_hash=diagnostic.numerical_diagnostic_hash,
        accepted_state_hash=bridge.accepted_state.state_hash,
        evaluated_trial_state_hash=bridge.evaluated_trial_state.state_hash,
        committed_state_hash=None,
        rollback_state_hash=bridge.rollback_state.state_hash,
        source_solution_payload_sha256=(seal.solution_payload_sha256),
        exported_free_residual_payload_sha256=(seal.true_residual_payload_sha256),
        solve_record_payload_sha256=seal.solve_record_payload_sha256,
        diagnostic_termination_hash=canonical_hash(termination.to_dict()),
        diagnostic_array_descriptor_hash=canonical_hash(diagnostic.arrays.to_dict()),
        diagnostic_array_count=3,
        diagnostic_array_byte_count=array_bytes,
        detached_raw_export_payload_byte_count=raw_export_bytes,
        upstream_completion_export_blocking_d2h_attempt_count=3,
        upstream_completion_export_blocking_d2h_success_count=3,
        upstream_completion_export_blocking_d2h_failure_count=0,
        sparse_residual_replay_count=1,
        additional_device_operation_count=0,
        additional_d2h_operation_count=0,
        additional_solve_count=0,
        additional_export_count=0,
        fallback_count=0,
        state_commit_count=0,
        diagnostic_binding_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        diagnostic_binding_hash=canonical_hash(
            _observation_payload(draft, include_binding_hash=False)
        ),
    )


def _totals(
    observations: tuple[HipFgmresModelFamilyDiagnosticIRObservationV1, ...],
    slots: tuple[HipFgmresFixtureReplayV1, ...],
    audited_rows: dict[str, Any],
) -> HipFgmresModelFamilyDiagnosticIRTotalsV1:
    values = {
        "required_diagnostic_slot_count": len(observations),
        "ready_result_ir_v2_count": 7,
        "ready_diagnostic_ir_v1_count": len(observations),
        "diagnostic_global_dof_count": sum(
            row.execution_plan.dof_count for row in slots
        ),
        "diagnostic_element_count": sum(
            row.execution_plan.element_count for row in slots
        ),
        "diagnostic_free_dof_count": sum(
            len(row.execution_plan.free_dofs) for row in slots
        ),
        "diagnostic_csr_nnz": sum(row.execution_plan.nnz for row in slots),
        "diagnostic_array_count": sum(
            row.diagnostic_array_count for row in observations
        ),
        "diagnostic_array_byte_count": sum(
            row.diagnostic_array_byte_count for row in observations
        ),
        "diagnostic_detached_raw_export_payload_byte_count": sum(
            row.detached_raw_export_payload_byte_count for row in observations
        ),
        "upstream_completion_export_blocking_d2h_attempt_count": sum(
            audited_rows[row.slot_id].completion_export_blocking_d2h_attempt_count
            for row in observations
        ),
        "upstream_completion_export_blocking_d2h_success_count": sum(
            audited_rows[row.slot_id].completion_export_blocking_d2h_success_count
            for row in observations
        ),
        "upstream_completion_export_blocking_d2h_failure_count": sum(
            audited_rows[row.slot_id].completion_export_blocking_d2h_failure_count
            for row in observations
        ),
        "upstream_completion_export_byte_count": sum(
            audited_rows[row.slot_id].completion_export_byte_count
            for row in observations
        ),
        "sparse_residual_replay_count": sum(
            row.sparse_residual_replay_count for row in observations
        ),
        "diagnostic_projection_additional_device_operation_count": sum(
            row.additional_device_operation_count for row in observations
        ),
        "diagnostic_projection_additional_d2h_operation_count": sum(
            row.additional_d2h_operation_count for row in observations
        ),
        "diagnostic_projection_additional_solve_count": sum(
            row.additional_solve_count for row in observations
        ),
        "diagnostic_projection_additional_export_count": sum(
            row.additional_export_count for row in observations
        ),
        "diagnostic_projection_fallback_count": sum(
            row.fallback_count for row in observations
        ),
        "diagnostic_projection_state_commit_count": sum(
            row.state_commit_count for row in observations
        ),
    }
    expected = {
        "required_diagnostic_slot_count": 3,
        "ready_result_ir_v2_count": 7,
        "ready_diagnostic_ir_v1_count": 3,
        "diagnostic_global_dof_count": 72,
        "diagnostic_element_count": 9,
        "diagnostic_free_dof_count": 54,
        "diagnostic_csr_nnz": 1080,
        "diagnostic_array_count": 9,
        "diagnostic_array_byte_count": 1584,
        "diagnostic_detached_raw_export_payload_byte_count": 1872,
        "upstream_completion_export_blocking_d2h_attempt_count": 9,
        "upstream_completion_export_blocking_d2h_success_count": 9,
        "upstream_completion_export_blocking_d2h_failure_count": 0,
        "upstream_completion_export_byte_count": 1872,
        "sparse_residual_replay_count": 3,
        "diagnostic_projection_additional_device_operation_count": 0,
        "diagnostic_projection_additional_d2h_operation_count": 0,
        "diagnostic_projection_additional_solve_count": 0,
        "diagnostic_projection_additional_export_count": 0,
        "diagnostic_projection_fallback_count": 0,
        "diagnostic_projection_state_commit_count": 0,
    }
    if values != expected:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_totals_invalid",
            "/totals",
            f"expected={expected!r} actual={values!r}",
        )
    return HipFgmresModelFamilyDiagnosticIRTotalsV1(**values)


def _validate_detached_composition(
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1,
    audited_receipt: HipFgmresModelFamilyAuditedParityReceiptV2,
    disposition: HipFgmresModelFamilyResultIRDispositionResultV1,
    bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...],
    *,
    bridges_validated: bool,
) -> None:
    if (
        type(audited_receipt) is not HipFgmresModelFamilyAuditedParityReceiptV2
        or type(disposition) is not HipFgmresModelFamilyResultIRDispositionResultV1
        or type(bridges) is not tuple
        or len(bridges) != 3
        or any(type(row) is not HipFgmresDiagnosticIRBridgeResultV1 for row in bridges)
        or len({id(row) for row in bridges}) != 3
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_detached_source_invalid",
            "/source",
        )
    try:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(audited_receipt)
        validate_hip_fgmres_model_family_result_ir_disposition_result_v1(disposition)
        registry = load_hip_fgmres_fixture_registry_v1()
        validate_hip_fgmres_fixture_registry_result_v1(registry)
    except Exception as exc:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_detached_source_invalid",
            "/source",
            f"{type(exc).__name__}: {exc}",
        )
    if disposition._source_audited_receipt is not audited_receipt:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_detached_source_mismatch",
            "/source",
        )
    bindings = receipt.bindings
    if (
        bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_audited_attestation_id != audited_receipt.attestation_id
        or bindings.source_audited_receipt_hash != audited_receipt.receipt_hash
        or bindings.source_result_ir_disposition_attestation_id
        != disposition.receipt.attestation_id
        or bindings.source_result_ir_disposition_receipt_hash
        != disposition.receipt.receipt_hash
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_detached_binding_mismatch",
            "/bindings",
        )
    audited_rows = {row.slot_id: row for row in audited_receipt.observations}
    disposition_rows = {row.slot_id: row for row in disposition.receipt.observations}
    if tuple(row.slot_id for row in receipt.observations) != (
        HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_observation_order_invalid",
            "/observations",
        )
    for index, (row, bridge) in enumerate(
        zip(receipt.observations, bridges, strict=True)
    ):
        slot = registry.slot(row.slot_id)
        audited = audited_rows.get(row.slot_id)
        disposition_row = disposition_rows.get(row.slot_id)
        if (
            audited is None
            or type(disposition_row)
            is not HipFgmresModelFamilyResultIRNotIssuedObservationV1
        ):
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_detached_join_invalid",
                f"/observations/{index}",
            )
        expected = _observation_from_bridge(
            slot,
            audited,
            disposition_row,
            bridge,
            index=index,
            bridge_validated=bridges_validated,
        )
        if row != expected:
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_detached_observation_mismatch",
                f"/observations/{index}",
            )
    expected_totals = _totals(
        receipt.observations,
        tuple(registry.slot(row.slot_id) for row in receipt.observations),
        audited_rows,
    )
    if receipt.totals != expected_totals:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_detached_totals_mismatch",
            "/totals",
        )


def _bridge_snapshot(
    bridge: HipFgmresDiagnosticIRBridgeResultV1,
) -> _DiagnosticBridgeSnapshotV1:
    validate_hip_fgmres_diagnostic_ir_v1(bridge)
    return _DiagnosticBridgeSnapshotV1(
        bridge=bridge,
        receipt=bridge.receipt,
        plan=bridge.source_execution_plan,
        accepted_state=bridge.accepted_state,
        evaluated_trial_state=bridge.evaluated_trial_state,
        rollback_state=bridge.rollback_state,
        source_seal=bridge._source_seal,
        source_provenance=bridge.receipt.source_provenance,
        diagnostic_ir_hash=bridge.receipt.diagnostic_ir_hash,
        plan_hash=bridge.source_execution_plan.plan_hash,
        accepted_state_hash=bridge.accepted_state.state_hash,
        evaluated_trial_state_hash=bridge.evaluated_trial_state.state_hash,
        rollback_state_hash=bridge.rollback_state.state_hash,
        provenance_hash=canonical_hash(bridge.receipt.source_provenance.to_dict()),
        capture_hash=bridge._source_seal.capture_hash,
    )


def _validate_bridge_snapshot(
    bridge: HipFgmresDiagnosticIRBridgeResultV1,
    snapshot: _DiagnosticBridgeSnapshotV1,
    *,
    path: str,
) -> None:
    if (
        type(snapshot) is not _DiagnosticBridgeSnapshotV1
        or snapshot.bridge is not bridge
        or snapshot.receipt is not bridge.receipt
        or snapshot.plan is not bridge.source_execution_plan
        or snapshot.accepted_state is not bridge.accepted_state
        or snapshot.evaluated_trial_state is not bridge.evaluated_trial_state
        or snapshot.rollback_state is not bridge.rollback_state
        or snapshot.source_seal is not bridge._source_seal
        or snapshot.source_provenance is not bridge.receipt.source_provenance
        or snapshot.diagnostic_ir_hash != bridge.receipt.diagnostic_ir_hash
        or snapshot.plan_hash != bridge.source_execution_plan.plan_hash
        or snapshot.accepted_state_hash != bridge.accepted_state.state_hash
        or snapshot.evaluated_trial_state_hash
        != bridge.evaluated_trial_state.state_hash
        or snapshot.rollback_state_hash != bridge.rollback_state.state_hash
        or snapshot.provenance_hash
        != canonical_hash(bridge.receipt.source_provenance.to_dict())
        or snapshot.capture_hash != bridge._source_seal.capture_hash
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_bridge_snapshot_mismatch",
            path,
        )


def _validate_exact_receipt_types(
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1,
) -> None:
    if type(receipt) is not HipFgmresModelFamilyDiagnosticIRReceiptV1:
        _fail("hip_fgmres_family_diagnostic_ir_v1_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not HipFgmresModelFamilyDiagnosticIRBindingsV1
        or type(receipt.observations) is not tuple
        or len(receipt.observations) != 3
        or any(
            type(row) is not HipFgmresModelFamilyDiagnosticIRObservationV1
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresModelFamilyDiagnosticIRTotalsV1
        or type(receipt.claims) is not HipFgmresModelFamilyDiagnosticIRClaimsV1
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_receipt_container_invalid",
            "/",
        )


def _validate_receipt_semantics(
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1,
) -> None:
    if (
        receipt.schema_version
        != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1
        or receipt.status != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or receipt.claims != HipFgmresModelFamilyDiagnosticIRClaimsV1()
        or receipt.totals
        != HipFgmresModelFamilyDiagnosticIRTotalsV1(
            required_diagnostic_slot_count=3,
            ready_result_ir_v2_count=7,
            ready_diagnostic_ir_v1_count=3,
            diagnostic_global_dof_count=72,
            diagnostic_element_count=9,
            diagnostic_free_dof_count=54,
            diagnostic_csr_nnz=1080,
            diagnostic_array_count=9,
            diagnostic_array_byte_count=1584,
            diagnostic_detached_raw_export_payload_byte_count=1872,
            upstream_completion_export_blocking_d2h_attempt_count=9,
            upstream_completion_export_blocking_d2h_success_count=9,
            upstream_completion_export_blocking_d2h_failure_count=0,
            upstream_completion_export_byte_count=1872,
            sparse_residual_replay_count=3,
            diagnostic_projection_additional_device_operation_count=0,
            diagnostic_projection_additional_d2h_operation_count=0,
            diagnostic_projection_additional_solve_count=0,
            diagnostic_projection_additional_export_count=0,
            diagnostic_projection_fallback_count=0,
            diagnostic_projection_state_commit_count=0,
        )
        or receipt.bindings.required_slot_ids
        != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1
        or receipt.bindings.required_architecture_base != "gfx1030"
        or receipt.bindings.registry_schema_version
        != HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        or receipt.bindings.fixture_suite_id != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or receipt.bindings.source_audited_schema_version
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_SCHEMA_VERSION_V2
        or receipt.bindings.source_audited_capability_profile
        != HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
        or receipt.bindings.source_result_ir_disposition_schema_version
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_SCHEMA_VERSION_V1
        or receipt.bindings.source_result_ir_disposition_capability_profile
        != HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_CAPABILITY_PROFILE_V1
        or receipt.bindings.diagnostic_ir_schema_version
        != DIAGNOSTIC_IR_V1_SCHEMA_VERSION
        or receipt.bindings.diagnostic_ir_capability_profile
        != DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE
        or receipt.bindings.diagnostic_ir_bridge_capability_profile
        != HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_receipt_semantics_invalid",
            "/",
        )
    if (
        len({row.case_id for row in receipt.observations}) != 3
        or len({row.case_receipt_hash for row in receipt.observations}) != 3
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_duplicate_case",
            "/observations",
        )
    expected_attestation = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1,
            "registry_hash": receipt.bindings.registry_hash,
            "source_audited_receipt_hash": (
                receipt.bindings.source_audited_receipt_hash
            ),
            "source_result_ir_disposition_receipt_hash": (
                receipt.bindings.source_result_ir_disposition_receipt_hash
            ),
            "observation_binding_hashes": [
                row.diagnostic_binding_hash for row in receipt.observations
            ],
        }
    )
    if receipt.attestation_id != expected_attestation:
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_attestation_id_invalid",
            "/attestation_id",
        )
    expected_per_slot_bytes = (
        (240, 360),
        (672, 792),
        (672, 720),
    )
    if (
        sum(row.diagnostic_array_count for row in receipt.observations)
        != receipt.totals.diagnostic_array_count
        or sum(row.diagnostic_array_byte_count for row in receipt.observations)
        != receipt.totals.diagnostic_array_byte_count
        or sum(
            row.detached_raw_export_payload_byte_count for row in receipt.observations
        )
        != receipt.totals.diagnostic_detached_raw_export_payload_byte_count
        or sum(
            row.upstream_completion_export_blocking_d2h_attempt_count
            for row in receipt.observations
        )
        != receipt.totals.upstream_completion_export_blocking_d2h_attempt_count
        or sum(row.sparse_residual_replay_count for row in receipt.observations)
        != receipt.totals.sparse_residual_replay_count
    ):
        _fail(
            "hip_fgmres_family_diagnostic_ir_v1_observation_totals_invalid",
            "/observations",
        )
    for index, row in enumerate(receipt.observations):
        expected_array_bytes, expected_raw_bytes = expected_per_slot_bytes[index]
        if (
            row.disposition != "ready_diagnostic_ir_v1"
            or row.cpu_status != "max_iterations"
            or row.cpu_termination_code != "max_iterations_exhausted"
            or row.solver_tolerance_passed is not False
            or row.authoritative_plan_tolerance_passed is not False
            or row.committed_state_hash is not None
            or row.rollback_state_hash != row.accepted_state_hash
            or row.diagnostic_array_count != 3
            or row.diagnostic_array_byte_count != expected_array_bytes
            or row.detached_raw_export_payload_byte_count != expected_raw_bytes
            or row.upstream_completion_export_blocking_d2h_attempt_count != 3
            or row.upstream_completion_export_blocking_d2h_success_count != 3
            or row.upstream_completion_export_blocking_d2h_failure_count != 0
            or row.sparse_residual_replay_count != 1
            or row.additional_device_operation_count != 0
            or row.additional_d2h_operation_count != 0
            or row.additional_solve_count != 0
            or row.additional_export_count != 0
            or row.fallback_count != 0
            or row.state_commit_count != 0
            or row.diagnostic_binding_hash
            != canonical_hash(_observation_payload(row, include_binding_hash=False))
        ):
            _fail(
                "hip_fgmres_family_diagnostic_ir_v1_observation_invalid",
                f"/observations/{index}",
            )


def _receipt_payload(
    receipt: HipFgmresModelFamilyDiagnosticIRReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
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


def _observation_payload(
    row: HipFgmresModelFamilyDiagnosticIRObservationV1,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = row.to_dict()
    if not include_binding_hash:
        del payload["diagnostic_binding_hash"]
    return payload


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
    text = str(value).replace("\n", " ").replace("\r", " ")
    return "".join(character if character.isprintable() else "?" for character in text)[
        :240
    ]


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresModelFamilyDiagnosticIRV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_STATUS_V1",
    "HipFgmresModelFamilyDiagnosticIRBindingsV1",
    "HipFgmresModelFamilyDiagnosticIRClaimsV1",
    "HipFgmresModelFamilyDiagnosticIRObservationV1",
    "HipFgmresModelFamilyDiagnosticIRReceiptV1",
    "HipFgmresModelFamilyDiagnosticIRResultV1",
    "HipFgmresModelFamilyDiagnosticIRTotalsV1",
    "HipFgmresModelFamilyDiagnosticIRV1Error",
    "attest_hip_fgmres_model_family_diagnostic_ir_v1",
    "validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1",
    "validate_hip_fgmres_model_family_diagnostic_ir_result_v1",
]
