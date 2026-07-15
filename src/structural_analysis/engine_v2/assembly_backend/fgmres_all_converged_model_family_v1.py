"""Exact ten-slot all-converged live FGMRES family authority.

The contract is intentionally narrow.  It classifies ten exact, still-live
model-case parity authorities against the package-owned all-converged registry
and binds them to one non-recycled process-local family token.  Its receipt is
detached and structurally replayable, but only the exact issued result carries
live provenance for downstream composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
)

from .fgmres_all_converged_fixture_registry_v1 import (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresAllConvergedFixtureRegistryResultV1,
    HipFgmresAllConvergedFixtureReplayV1,
    _FixedRegistryReplayTransactionV1,
    _fixed_registry_authority_snapshot_hash_v1,
    _issue_fixed_registry_replay_transaction_v1,
    _refresh_fixed_registry_replay_transaction_v1,
    _registry_from_fixed_replay_transaction_v1,
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from .fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityResultV1,
)
from .fgmres_model_family_parity_v1 import _derive_descriptor
from .fgmres_result_ir_v2 import (
    _capture_live_authority,
    _require_converged_native_source,
)


HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-all-converged-model-family.v1"
)
HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_package_gfx1030_all_converged_ten_slot_family"
)
HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_STATUS_V1 = (
    "exact_gfx1030_all_converged_ten_slot_family_verified"
)
HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_EVIDENCE_SCOPE_V1 = (
    "process_local_registry_bound_unsigned_nonpersistent_nonpromoting"
)
HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1 = (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
)

_SCHEMA_RESOURCE = "hip_fgmres_all_converged_model_family_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64


class HipFgmresAllConvergedModelFamilyV1Error(RuntimeError):
    """Stable fail-closed all-converged family error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = " ".join(str(message or code).split())[:512]
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedModelFamilyBindingsV1:
    registry_schema_version: str
    registry_capability_profile: str
    fixture_suite_id: str
    fixture_registry_evidence_scope: str
    registry_bytes_sha256: str
    registry_hash: str
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
class HipFgmresAllConvergedModelFamilyObservationV1:
    slot_id: str
    slot_registration_hash: str
    case_fingerprint: str
    case_id: str
    case_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    fgmres_plan_hash: str
    recurrence_plan_hash: str
    policy_hash: str
    cpu_result_hash: str
    descriptor_hash: str
    terminal_observation_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    runtime_library_sha256: str
    compiled_architecture: Literal["gfx1030"]
    runtime_architecture_base: Literal["gfx1030"]
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    cpu_status: Literal["converged"]
    cpu_termination_code: str
    solver_tolerance_passed: Literal[True]
    authoritative_plan_tolerance_passed: Literal[True]
    authority_snapshot_hash: str
    logical_case_key: str
    observation_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedModelFamilyTotalsV1:
    required_slot_count: Literal[10]
    validated_live_case_count: Literal[10]
    converged_case_count: Literal[10]
    solver_tolerance_passed_count: Literal[10]
    authoritative_plan_tolerance_passed_count: Literal[10]
    unique_model_ir_count: Literal[10]
    unique_execution_plan_count: Literal[10]
    unique_case_count: Literal[10]
    package_global_dof_count: int
    package_element_count: int
    package_free_dof_count: int
    package_csr_nnz: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedModelFamilyClaimsV1:
    fixed_all_converged_package_registry_replayed: Literal[True] = True
    exact_ten_registered_slots_verified: Literal[True] = True
    exact_ten_live_case_authorities_replayed: Literal[True] = True
    canonical_registry_order_verified: Literal[True] = True
    ten_unique_model_ir_verified: Literal[True] = True
    all_cpu_reference_converged: Literal[True] = True
    all_solver_tolerance_passed: Literal[True] = True
    all_authoritative_plan_tolerance_passed: Literal[True] = True
    exact_gfx1030_family_authority_issued: Literal[True] = True
    actual_hardware_execution_verified: Literal[False] = False
    hardware_gate_completed: Literal[False] = False
    serialized_receipt_grants_process_local_provenance: Literal[False] = False
    result_ir_verified: Literal[False] = False
    external_gfx1100_verified: Literal[False] = False
    multiarchitecture_parity_verified: Literal[False] = False
    signed_evidence: Literal[False] = False
    persistent_external_log_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedModelFamilyReceiptV1:
    status: Literal["exact_gfx1030_all_converged_ten_slot_family_verified"]
    attestation_id: str
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresAllConvergedModelFamilyBindingsV1
    observations: tuple[HipFgmresAllConvergedModelFamilyObservationV1, ...]
    totals: HipFgmresAllConvergedModelFamilyTotalsV1
    claims: HipFgmresAllConvergedModelFamilyClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_all_converged_model_family_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _CaseSourceCaptureV1:
    case_result: HipFgmresModelCaseParityResultV1
    source_case_identity_token: object
    receipt: HipFgmresModelCaseParityReceiptV1
    plan: Any
    cpu_result: Any
    authority_snapshot_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FamilyEvaluationV1:
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    canonical_cases: tuple[HipFgmresModelCaseParityResultV1, ...]
    case_captures: tuple[_CaseSourceCaptureV1, ...]
    source_token: tuple[Any, ...]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FamilyLiveBindingV1:
    family_result: HipFgmresAllConvergedModelFamilyResultV1
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    canonical_cases: tuple[HipFgmresModelCaseParityResultV1, ...]
    registry: HipFgmresAllConvergedFixtureRegistryResultV1
    registry_transaction: _FixedRegistryReplayTransactionV1
    family_identity_token: object
    source_token: tuple[Any, ...]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FamilyIssuanceV1:
    mint: object
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    cases: tuple[HipFgmresModelCaseParityResultV1, ...]
    registry: HipFgmresAllConvergedFixtureRegistryResultV1
    registry_snapshot_hash: str
    case_identity_tokens: tuple[object, ...]
    source_token: tuple[Any, ...]
    receipt_payload_hash: str


class _WeakReferenceableAllConvergedFamilyResultV1:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresAllConvergedModelFamilyResultV1(
    _WeakReferenceableAllConvergedFamilyResultV1
):
    """Exact live family authority; not a serializable provenance token."""

    receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    _case_results: tuple[HipFgmresModelCaseParityResultV1, ...] = field(
        repr=False,
        compare=False,
    )
    _registry_result: HipFgmresAllConvergedFixtureRegistryResultV1 = field(
        repr=False,
        compare=False,
    )

    @property
    def case_results(self) -> tuple[HipFgmresModelCaseParityResultV1, ...]:
        return self._case_results

    def to_manifest(self) -> dict[str, Any]:
        return self.receipt.to_dict()

    def _result_ir_downstream_authority_binding(
        self,
    ) -> tuple[_FamilyLiveBindingV1, object]:
        binding = _capture_hip_fgmres_all_converged_family_live_binding_v1(self)
        return binding, binding.family_identity_token


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresAllConvergedModelFamilyResultV1,
    _FamilyIssuanceV1,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_all_converged_model_family_v1(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
) -> HipFgmresAllConvergedModelFamilyResultV1:
    """Issue one canonical ten-case live family authority."""

    registry = load_hip_fgmres_all_converged_fixture_registry_v1()
    registry_transaction = _issue_fixed_registry_replay_transaction_v1(registry)
    first = _evaluate_cases(case_results, registry)
    second = _evaluate_cases(first.canonical_cases, registry)
    if first.source_token != second.source_token:
        _fail(
            "hip_fgmres_all_converged_family_source_changed",
            "/cases",
        )
    result = HipFgmresAllConvergedModelFamilyResultV1(
        receipt=second.receipt,
        _case_results=second.canonical_cases,
        _registry_result=registry,
    )
    issuance = _FamilyIssuanceV1(
        mint=object(),
        receipt=result.receipt,
        cases=result._case_results,
        registry=registry,
        registry_snapshot_hash=_registry_snapshot_hash(registry),
        case_identity_tokens=tuple(
            row.source_case_identity_token for row in second.case_captures
        ),
        source_token=second.source_token,
        receipt_payload_hash=canonical_hash(
            _receipt_payload(result.receipt, include_hash=True)
        ),
    )
    with _ISSUANCE_LOCK:
        _ISSUANCES[result] = issuance
    try:
        _capture_family_live_binding_with_exact_registry_transaction_v1(
            result,
            registry_transaction,
        )
        refreshed_registry = _refresh_family_registry_transaction_v1(
            registry_transaction
        )
        if refreshed_registry is not registry:
            _fail(
                "hip_fgmres_all_converged_family_registry_binding_mismatch",
                "/registry",
            )
        return result
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_all_converged_model_family_result_v1(
    result: HipFgmresAllConvergedModelFamilyResultV1,
) -> HipFgmresAllConvergedModelFamilyResultV1:
    """Replay an exact issued family while all source authorities are live."""

    _capture_hip_fgmres_all_converged_family_live_binding_v1(result)
    return result


def validate_hip_fgmres_all_converged_model_family_receipt_v1(
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
) -> HipFgmresAllConvergedModelFamilyReceiptV1:
    """Validate detached structure without granting process-local authority."""

    _validate_receipt_structure(receipt)
    registry = load_hip_fgmres_all_converged_fixture_registry_v1()
    _validate_receipt_semantics(receipt, registry)
    return receipt


def _validate_receipt_structure(
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
) -> None:
    _validate_exact_receipt_types(receipt)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: tuple(str(part) for part in row.absolute_path),
    )
    if errors:
        first = errors[0]
        _fail(
            "hip_fgmres_all_converged_family_schema_invalid",
            "/" + "/".join(str(part) for part in first.absolute_path),
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_all_converged_family_receipt_hash_invalid",
            "/receipt_hash",
        )


def _capture_hip_fgmres_all_converged_family_live_binding_v1(
    result: HipFgmresAllConvergedModelFamilyResultV1,
) -> _FamilyLiveBindingV1:
    try:
        fresh = load_hip_fgmres_all_converged_fixture_registry_v1()
        transaction = _issue_fixed_registry_replay_transaction_v1(fresh)
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_family_registry_invalid",
            "/registry",
            f"{type(exc).__name__}: {exc}",
        )
    return _capture_family_live_binding_against_registry_v1(
        result,
        fresh,
        transaction,
    )


def _capture_family_live_binding_with_exact_registry_transaction_v1(
    result: HipFgmresAllConvergedModelFamilyResultV1,
    transaction: _FixedRegistryReplayTransactionV1,
) -> _FamilyLiveBindingV1:
    try:
        registry = _registry_from_fixed_replay_transaction_v1(transaction)
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_family_registry_invalid",
            "/registry",
            f"{type(exc).__name__}: {exc}",
        )
    if (
        type(result) is not HipFgmresAllConvergedModelFamilyResultV1
        or registry is not result._registry_result
    ):
        _fail(
            "hip_fgmres_all_converged_family_registry_binding_mismatch",
            "/registry",
        )
    return _capture_family_live_binding_against_registry_v1(
        result,
        registry,
        transaction,
    )


def _recapture_family_live_binding_with_refreshed_registry_transaction_v1(
    result: HipFgmresAllConvergedModelFamilyResultV1,
    transaction: _FixedRegistryReplayTransactionV1,
) -> _FamilyLiveBindingV1:
    registry = _refresh_family_registry_transaction_v1(transaction)
    return _capture_family_live_binding_against_registry_v1(
        result,
        registry,
        transaction,
    )


def _refresh_family_registry_transaction_v1(
    transaction: _FixedRegistryReplayTransactionV1,
) -> HipFgmresAllConvergedFixtureRegistryResultV1:
    try:
        return _refresh_fixed_registry_replay_transaction_v1(transaction)
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_family_registry_invalid",
            "/registry",
            f"{type(exc).__name__}: {exc}",
        )


def _capture_family_live_binding_against_registry_v1(
    result: HipFgmresAllConvergedModelFamilyResultV1,
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
    transaction: _FixedRegistryReplayTransactionV1,
) -> _FamilyLiveBindingV1:
    if type(result) is not HipFgmresAllConvergedModelFamilyResultV1:
        _fail("hip_fgmres_all_converged_family_result_type_invalid", "/")
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _FamilyIssuanceV1:
        _fail(
            "hip_fgmres_all_converged_family_issuance_unavailable",
            "/issuance",
        )
    if (
        type(result._case_results) is not tuple
        or type(result._registry_result)
        is not HipFgmresAllConvergedFixtureRegistryResultV1
        or issuance.receipt is not result.receipt
        or issuance.cases is not result._case_results
        or issuance.registry is not result._registry_result
        or type(issuance.mint) is not object
        or type(transaction) is not _FixedRegistryReplayTransactionV1
        or transaction.registry is not registry
        or issuance.registry_snapshot_hash
        != _registry_snapshot_hash(result._registry_result)
        or issuance.receipt_payload_hash
        != canonical_hash(_receipt_payload(result.receipt, include_hash=True))
    ):
        _fail(
            "hip_fgmres_all_converged_family_issuance_binding_mismatch",
            "/issuance",
        )
    if (
        result._registry_result.registry_bytes_sha256 != registry.registry_bytes_sha256
        or result._registry_result.registry_hash != registry.registry_hash
        or result._registry_result.receipt_hash != registry.receipt_hash
        or _registry_snapshot_hash(result._registry_result)
        != _registry_snapshot_hash(registry)
    ):
        _fail(
            "hip_fgmres_all_converged_family_registry_binding_mismatch",
            "/registry",
        )
    replay = _evaluate_cases(result._case_results, registry)
    if (
        replay.receipt != result.receipt
        or any(
            left is not right
            for left, right in zip(
                replay.canonical_cases,
                result._case_results,
                strict=True,
            )
        )
        or tuple(row.source_case_identity_token for row in replay.case_captures)
        != issuance.case_identity_tokens
        or replay.source_token != issuance.source_token
    ):
        _fail(
            "hip_fgmres_all_converged_family_live_replay_mismatch",
            "/source",
        )
    return _FamilyLiveBindingV1(
        family_result=result,
        receipt=result.receipt,
        canonical_cases=result._case_results,
        registry=registry,
        registry_transaction=transaction,
        family_identity_token=issuance.mint,
        source_token=replay.source_token,
    )


def _capture_case_source(
    case: HipFgmresModelCaseParityResultV1,
) -> _CaseSourceCaptureV1:
    """Narrow seam around the model-case private live authority."""

    try:
        live = _capture_live_authority(case)
        _require_converged_native_source(live)
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_family_case_authority_invalid",
            "/cases",
            f"{type(exc).__name__}: {exc}",
        )
    return _CaseSourceCaptureV1(
        case_result=case,
        source_case_identity_token=live.source_case_identity_token,
        receipt=live.receipt,
        plan=live.plan,
        cpu_result=live.cpu_result,
        authority_snapshot_hash=live.authority_snapshot_hash,
    )


def _evaluate_cases(
    case_results: tuple[HipFgmresModelCaseParityResultV1, ...],
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> _FamilyEvaluationV1:
    if (
        type(case_results) is not tuple
        or len(case_results) != 10
        or any(
            type(row) is not HipFgmresModelCaseParityResultV1 for row in case_results
        )
        or len({id(row) for row in case_results}) != 10
    ):
        _fail("hip_fgmres_all_converged_family_case_set_invalid", "/cases")
    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_family_registry_type_invalid", "/registry")

    captures: list[_CaseSourceCaptureV1] = []
    by_slot: dict[str, _CaseSourceCaptureV1] = {}
    for index, case in enumerate(case_results):
        try:
            capture = _capture_case_source(case)
        except HipFgmresAllConvergedModelFamilyV1Error:
            raise
        except Exception as exc:
            _fail(
                "hip_fgmres_all_converged_family_case_authority_invalid",
                f"/cases/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        if (
            type(capture) is not _CaseSourceCaptureV1
            or capture.case_result is not case
            or type(capture.source_case_identity_token) is not object
            or capture.receipt is not case.receipt
            or capture.plan is not case._source_execution_plan
            or capture.cpu_result is not case._cpu_result
        ):
            _fail(
                "hip_fgmres_all_converged_family_case_capture_invalid",
                f"/cases/{index}",
            )
        descriptor_hash = _derive_descriptor(capture.plan).descriptor_hash
        matches = tuple(
            slot
            for slot in registry.slots
            if _slot_matches(slot, capture, descriptor_hash)
        )
        if len(matches) != 1:
            _fail(
                "hip_fgmres_all_converged_family_exact_slot_match_required",
                f"/cases/{index}/classification",
            )
        slot = matches[0]
        if slot.slot_id in by_slot:
            _fail(
                "hip_fgmres_all_converged_family_duplicate_slot",
                f"/cases/{index}",
            )
        by_slot[slot.slot_id] = capture
        captures.append(capture)
    if set(by_slot) != set(HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1):
        _fail("hip_fgmres_all_converged_family_slot_set_invalid", "/cases")

    canonical_captures = tuple(
        by_slot[slot_id]
        for slot_id in HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1
    )
    canonical_cases = tuple(row.case_result for row in canonical_captures)
    observations = tuple(
        _observation(slot, capture)
        for slot, capture in zip(
            registry.slots,
            canonical_captures,
            strict=True,
        )
    )
    if (
        len({row.case_id for row in observations}) != 10
        or len({row.case_receipt_hash for row in observations}) != 10
    ):
        _fail("hip_fgmres_all_converged_family_duplicate_case", "/cases")
    totals = _totals(registry, observations)
    bindings = HipFgmresAllConvergedModelFamilyBindingsV1(
        registry_schema_version=(
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        ),
        registry_capability_profile=(
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1
        ),
        fixture_suite_id=HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
        fixture_registry_evidence_scope=(
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1
        ),
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        required_architecture_base="gfx1030",
        required_slot_ids=(HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1),
    )
    claims = HipFgmresAllConvergedModelFamilyClaimsV1()
    attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1
            ),
            "registry_hash": registry.registry_hash,
            "observation_binding_hashes": [
                row.observation_binding_hash for row in observations
            ],
        }
    )
    draft = HipFgmresAllConvergedModelFamilyReceiptV1(
        status=HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        observations=observations,
        totals=totals,
        claims=claims,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    _validate_receipt_structure(receipt)
    _validate_receipt_semantics(receipt, registry)
    source_token = (
        tuple(id(row.case_result) for row in canonical_captures),
        tuple(row.source_case_identity_token for row in canonical_captures),
        tuple(id(row.receipt) for row in canonical_captures),
        tuple(row.receipt.receipt_hash for row in canonical_captures),
        tuple(id(row.plan) for row in canonical_captures),
        tuple(row.plan.plan_hash for row in canonical_captures),
        tuple(id(row.cpu_result) for row in canonical_captures),
        tuple(row.cpu_result.result_hash for row in canonical_captures),
        tuple(row.authority_snapshot_hash for row in canonical_captures),
    )
    return _FamilyEvaluationV1(
        receipt=receipt,
        canonical_cases=canonical_cases,
        case_captures=canonical_captures,
        source_token=source_token,
    )


def _slot_matches(
    slot: HipFgmresAllConvergedFixtureReplayV1,
    capture: _CaseSourceCaptureV1,
    descriptor_hash: str,
) -> bool:
    bindings = capture.receipt.bindings
    cpu = capture.cpu_result
    return (
        capture.plan.plan_hash == slot.execution_plan.plan_hash
        and bindings.execution_plan_hash == slot.execution_plan.plan_hash
        and bindings.model_ir_content_hash == slot.model.content_hash
        and bindings.fgmres_plan_hash == slot.fgmres_plan.plan_hash
        and bindings.recurrence_plan_hash == slot.recurrence_plan.plan_hash
        and bindings.policy_hash == slot.policy.policy_hash
        and bindings.cpu_result_hash == slot.cpu_result.result_hash
        and cpu.result_hash == slot.cpu_result.result_hash
        and cpu.status == "converged"
        and cpu.status == slot.cpu_result.status
        and cpu.termination_code == slot.cpu_result.termination_code
        and cpu.solver_tolerance_passed is True
        and cpu.authoritative_plan_tolerance_passed is True
        and slot.cpu_result.solver_tolerance_passed is True
        and slot.cpu_result.authoritative_plan_tolerance_passed is True
        and descriptor_hash == slot.descriptor.descriptor_hash
        and bindings.compiled_architecture == "gfx1030"
        and bindings.runtime_architecture_base == "gfx1030"
    )


def _observation(
    slot: HipFgmresAllConvergedFixtureReplayV1,
    capture: _CaseSourceCaptureV1,
) -> HipFgmresAllConvergedModelFamilyObservationV1:
    receipt = capture.receipt
    bindings = receipt.bindings
    cpu = capture.cpu_result
    logical_case_key = canonical_hash(
        {
            "registry_slot_registration_hash": slot.slot_registration_hash,
            "case_receipt_hash": receipt.receipt_hash,
            "source_case_identity_bound": True,
            "authority_snapshot_hash": capture.authority_snapshot_hash,
        }
    )
    draft = HipFgmresAllConvergedModelFamilyObservationV1(
        slot_id=slot.slot_id,
        slot_registration_hash=slot.slot_registration_hash,
        case_fingerprint=slot.case_fingerprint,
        case_id=receipt.case_id,
        case_receipt_hash=receipt.receipt_hash,
        model_ir_content_hash=bindings.model_ir_content_hash,
        execution_plan_hash=bindings.execution_plan_hash,
        fgmres_plan_hash=bindings.fgmres_plan_hash,
        recurrence_plan_hash=bindings.recurrence_plan_hash,
        policy_hash=bindings.policy_hash,
        cpu_result_hash=bindings.cpu_result_hash,
        descriptor_hash=slot.descriptor.descriptor_hash,
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        completion_export_context_id=bindings.completion_export_context_id,
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        kernel_identity_hash=bindings.kernel_identity_hash,
        kernel_source_sha256=bindings.kernel_source_sha256,
        runtime_library_sha256=bindings.runtime_library_sha256,
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=bindings.device_ordinal,
        device_uuid_bytes_hex=bindings.device_uuid_bytes_hex,
        device_pci_bdf=bindings.device_pci_bdf,
        cpu_status="converged",
        cpu_termination_code=cpu.termination_code,
        solver_tolerance_passed=True,
        authoritative_plan_tolerance_passed=True,
        authority_snapshot_hash=capture.authority_snapshot_hash,
        logical_case_key=logical_case_key,
        observation_binding_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        observation_binding_hash=canonical_hash(
            _observation_payload(draft, include_binding_hash=False)
        ),
    )


def _totals(
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
    observations: tuple[HipFgmresAllConvergedModelFamilyObservationV1, ...],
) -> HipFgmresAllConvergedModelFamilyTotalsV1:
    plans = tuple(row.execution_plan for row in registry.slots)
    return HipFgmresAllConvergedModelFamilyTotalsV1(
        required_slot_count=10,
        validated_live_case_count=len(observations),
        converged_case_count=sum(row.cpu_status == "converged" for row in observations),
        solver_tolerance_passed_count=sum(
            row.solver_tolerance_passed for row in observations
        ),
        authoritative_plan_tolerance_passed_count=sum(
            row.authoritative_plan_tolerance_passed for row in observations
        ),
        unique_model_ir_count=len({row.model.content_hash for row in registry.slots}),
        unique_execution_plan_count=len({row.plan_hash for row in plans}),
        unique_case_count=len({row.case_receipt_hash for row in observations}),
        package_global_dof_count=sum(row.dof_count for row in plans),
        package_element_count=sum(row.element_count for row in plans),
        package_free_dof_count=sum(len(row.free_dofs) for row in plans),
        package_csr_nnz=sum(row.nnz for row in plans),
    )


def _validate_receipt_semantics(
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> None:
    bindings = receipt.bindings
    if (
        receipt.status != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or bindings.registry_schema_version
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        or bindings.registry_capability_profile
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1
        or bindings.fixture_suite_id
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1
        or bindings.fixture_registry_evidence_scope
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1
        or bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.required_architecture_base != "gfx1030"
        or bindings.required_slot_ids
        != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1
    ):
        _fail("hip_fgmres_all_converged_family_semantics_invalid", "/")
    if (
        len({row.case_id for row in receipt.observations}) != 10
        or len({row.case_receipt_hash for row in receipt.observations}) != 10
    ):
        _fail("hip_fgmres_all_converged_family_duplicate_case", "/cases")
    for index, (row, slot) in enumerate(
        zip(receipt.observations, registry.slots, strict=True)
    ):
        expected_logical_case_key = canonical_hash(
            {
                "registry_slot_registration_hash": slot.slot_registration_hash,
                "case_receipt_hash": row.case_receipt_hash,
                "source_case_identity_bound": True,
                "authority_snapshot_hash": row.authority_snapshot_hash,
            }
        )
        if (
            row.slot_registration_hash != slot.slot_registration_hash
            or row.case_fingerprint != slot.case_fingerprint
            or row.model_ir_content_hash != slot.model.content_hash
            or row.execution_plan_hash != slot.execution_plan.plan_hash
            or row.fgmres_plan_hash != slot.fgmres_plan.plan_hash
            or row.recurrence_plan_hash != slot.recurrence_plan.plan_hash
            or row.policy_hash != slot.policy.policy_hash
            or row.cpu_result_hash != slot.cpu_result.result_hash
            or row.descriptor_hash != slot.descriptor.descriptor_hash
            or row.cpu_status != "converged"
            or row.cpu_termination_code != slot.cpu_result.termination_code
            or row.solver_tolerance_passed is not True
            or row.authoritative_plan_tolerance_passed is not True
            or row.compiled_architecture != "gfx1030"
            or row.runtime_architecture_base != "gfx1030"
            or row.logical_case_key != expected_logical_case_key
            or row.observation_binding_hash
            != canonical_hash(_observation_payload(row, include_binding_hash=False))
        ):
            _fail(
                "hip_fgmres_all_converged_family_observation_invalid",
                f"/observations/{index}",
            )
    expected_totals = _totals(registry, receipt.observations)
    if receipt.totals != expected_totals:
        _fail("hip_fgmres_all_converged_family_totals_invalid", "/totals")
    if receipt.claims != HipFgmresAllConvergedModelFamilyClaimsV1():
        _fail("hip_fgmres_all_converged_family_claims_invalid", "/claims")
    expected_attestation = canonical_hash(
        {
            "capability_profile": receipt.capability_profile,
            "registry_hash": bindings.registry_hash,
            "observation_binding_hashes": [
                row.observation_binding_hash for row in receipt.observations
            ],
        }
    )
    if receipt.attestation_id != expected_attestation:
        _fail(
            "hip_fgmres_all_converged_family_attestation_invalid",
            "/attestation_id",
        )


def _validate_exact_receipt_types(
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
) -> None:
    if type(receipt) is not HipFgmresAllConvergedModelFamilyReceiptV1:
        _fail("hip_fgmres_all_converged_family_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not HipFgmresAllConvergedModelFamilyBindingsV1
        or type(receipt.observations) is not tuple
        or len(receipt.observations) != 10
        or any(
            type(row) is not HipFgmresAllConvergedModelFamilyObservationV1
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresAllConvergedModelFamilyTotalsV1
        or type(receipt.claims) is not HipFgmresAllConvergedModelFamilyClaimsV1
    ):
        _fail("hip_fgmres_all_converged_family_receipt_container_invalid", "/")


def _observation_payload(
    row: HipFgmresAllConvergedModelFamilyObservationV1,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = row.to_dict()
    if not include_binding_hash:
        payload.pop("observation_binding_hash")
    return payload


def _receipt_payload(
    receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
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


def _registry_snapshot_hash(
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> str:
    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_family_registry_type_invalid", "/registry")
    return _fixed_registry_authority_snapshot_hash_v1(registry)


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


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresAllConvergedModelFamilyV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_STATUS_V1",
    "HipFgmresAllConvergedModelFamilyBindingsV1",
    "HipFgmresAllConvergedModelFamilyClaimsV1",
    "HipFgmresAllConvergedModelFamilyObservationV1",
    "HipFgmresAllConvergedModelFamilyReceiptV1",
    "HipFgmresAllConvergedModelFamilyResultV1",
    "HipFgmresAllConvergedModelFamilyTotalsV1",
    "HipFgmresAllConvergedModelFamilyV1Error",
    "attest_hip_fgmres_all_converged_model_family_v1",
    "validate_hip_fgmres_all_converged_model_family_receipt_v1",
    "validate_hip_fgmres_all_converged_model_family_result_v1",
]
