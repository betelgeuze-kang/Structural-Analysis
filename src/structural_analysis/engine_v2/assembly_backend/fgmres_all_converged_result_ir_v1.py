"""Detached aggregate of ten all-converged HIP FGMRES ``ResultIRV2`` bridges.

Issuance requires the exact live all-converged family authority and ten
already-issued bridges.  The factory does not build a bridge or perform an
additional native/device solve, export, allocation, launch, synchronization,
or transfer.  Registry validation may replay deterministic CPU-reference
solves.  The issued result retains only the detached family receipt and the
exact bridges, so validation remains available after HIP contexts close
without turning serialized data into process-local provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    RESULT_IR_V2_CAPABILITY_PROFILE,
    RESULT_IR_V2_SCHEMA_VERSION,
)

from .fgmres_all_converged_fixture_registry_v1 import (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresAllConvergedFixtureRegistryResultV1,
    HipFgmresAllConvergedFixtureReplayV1,
    _FixedRegistryReplayTransactionV1,
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from .fgmres_all_converged_model_family_v1 import (
    HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_SCHEMA_VERSION_V1,
    HipFgmresAllConvergedModelFamilyObservationV1,
    HipFgmresAllConvergedModelFamilyReceiptV1,
    HipFgmresAllConvergedModelFamilyResultV1,
    _FamilyLiveBindingV1,
    _recapture_family_live_binding_with_refreshed_registry_transaction_v1,
    _refresh_family_registry_transaction_v1,
    _receipt_payload as _family_receipt_payload,
    _validate_receipt_semantics as _validate_family_receipt_semantics,
    _validate_receipt_structure as _validate_family_receipt_structure,
)
from .fgmres_model_case_parity_v1 import HipFgmresModelCaseParityResultV1
from .fgmres_result_ir_v2 import (
    HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE,
    HipFgmresResultIRBridgeResultV2,
    _validate_hip_fgmres_result_ir_v2_against_live_case,
    validate_hip_fgmres_result_ir_v2,
)


HIP_FGMRES_ALL_CONVERGED_RESULT_IR_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-all-converged-result-ir.v1"
)
HIP_FGMRES_ALL_CONVERGED_RESULT_IR_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_package_gfx1030_all_converged_ten_slot_result_ir_v2"
)
HIP_FGMRES_ALL_CONVERGED_RESULT_IR_STATUS_V1 = (
    "exact_gfx1030_all_converged_ten_slot_result_ir_v2_verified"
)
HIP_FGMRES_ALL_CONVERGED_RESULT_IR_EVIDENCE_SCOPE_V1 = (
    "process_local_issuance_detached_validation_unsigned_nonpromoting"
)
HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_SLOT_IDS_V1 = (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
)

_SCHEMA_RESOURCE = "hip_fgmres_all_converged_result_ir_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64


class HipFgmresAllConvergedResultIRV1Error(RuntimeError):
    """Stable fail-closed all-converged ResultIR aggregate error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = " ".join(str(message or code).split())[:512]
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedResultIRBindingsV1:
    registry_schema_version: str
    fixture_suite_id: str
    registry_bytes_sha256: str
    registry_hash: str
    source_family_schema_version: str
    source_family_capability_profile: str
    source_family_attestation_id: str
    source_family_receipt_hash: str
    result_ir_schema_version: str
    result_ir_capability_profile: str
    result_ir_bridge_capability_profile: str
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
class HipFgmresAllConvergedResultIRObservationV1:
    slot_id: str
    slot_registration_hash: str
    case_fingerprint: str
    family_observation_binding_hash: str
    logical_case_key: str
    case_id: str
    case_receipt_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    cpu_result_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    compiled_architecture: Literal["gfx1030"]
    runtime_architecture_base: Literal["gfx1030"]
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    cpu_status: Literal["converged"]
    solver_tolerance_passed: Literal[True]
    authoritative_plan_tolerance_passed: Literal[True]
    disposition: Literal["ready_result_ir_v2"]
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
    aggregate_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedResultIRTotalsV1:
    required_slot_count: Literal[10]
    ready_result_ir_v2_count: Literal[10]
    solution_ready_count: Literal[10]
    not_issued_count: Literal[0]
    diagnostic_ir_count: Literal[0]
    unique_result_ir_bridge_count: Literal[10]
    committed_state_count: Literal[10]
    package_global_dof_count: int
    package_element_count: int
    package_free_dof_count: int
    package_csr_nnz: int
    result_array_count: Literal[60]
    result_array_byte_count: int
    detached_raw_payload_byte_count: int
    upstream_completion_export_blocking_d2h_attempt_count: Literal[30]
    upstream_completion_export_blocking_d2h_success_count: Literal[30]
    upstream_completion_export_blocking_d2h_failure_count: Literal[0]
    upstream_completion_export_byte_count: int
    aggregate_additional_device_operation_count: Literal[0]
    aggregate_additional_d2h_operation_count: Literal[0]
    aggregate_additional_solve_count: Literal[0]
    aggregate_additional_export_count: Literal[0]
    aggregate_fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedResultIRClaimsV1:
    fixed_all_converged_package_registry_replayed: Literal[True] = True
    all_converged_family_authority_replayed_at_issuance: Literal[True] = True
    exact_ten_converged_result_ir_v2_verified: Literal[True] = True
    exact_ten_result_ir_v2_ready: Literal[True] = True
    all_ten_solution_ready: Literal[True] = True
    retained_bridge_exact_identity_bound: Literal[True] = True
    case_plan_provenance_terminal_export_device_state_cross_bound: Literal[True] = True
    reaction_member_force_energy_and_state_lineage_verified: Literal[True] = True
    canonical_registry_order_verified: Literal[True] = True
    descriptor_only_family_manifest: Literal[True] = True
    post_close_detached_value_validation_supported: Literal[True] = True
    aggregate_additional_device_operation_zero: Literal[True] = True
    aggregate_additional_d2h_zero: Literal[True] = True
    aggregate_additional_solve_zero: Literal[True] = True
    aggregate_additional_export_zero: Literal[True] = True
    aggregate_fallback_zero: Literal[True] = True
    registry_validation_cpu_reference_replay_zero_proven: Literal[False] = False
    actual_hardware_execution_verified: Literal[False] = False
    hardware_gate_completed: Literal[False] = False
    serialized_receipt_grants_process_local_provenance: Literal[False] = False
    external_gfx1100_result_ir_verified: Literal[False] = False
    multiarchitecture_result_ir_verified: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    device_result_recovery_verified: Literal[False] = False
    hostile_same_process_mutation_resistance: Literal[False] = False
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
class HipFgmresAllConvergedResultIRReceiptV1:
    status: Literal["exact_gfx1030_all_converged_ten_slot_result_ir_v2_verified"]
    attestation_id: str
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresAllConvergedResultIRBindingsV1
    observations: tuple[HipFgmresAllConvergedResultIRObservationV1, ...]
    totals: HipFgmresAllConvergedResultIRTotalsV1
    claims: HipFgmresAllConvergedResultIRClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_ALL_CONVERGED_RESULT_IR_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_ALL_CONVERGED_RESULT_IR_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_all_converged_result_ir_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


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
class _AggregateIssuanceV1:
    mint: object
    family_identity_token: object
    family_receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    receipt: HipFgmresAllConvergedResultIRReceiptV1
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...]
    bridge_snapshots: tuple[_BridgeSnapshotV1, ...]
    receipt_payload_hash: str
    family_payload_hash: str


class _WeakReferenceableAllConvergedResultIRResultV1:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresAllConvergedResultIRResultV1(
    _WeakReferenceableAllConvergedResultIRResultV1
):
    """Issued aggregate retaining detached family data and exact bridges."""

    receipt: HipFgmresAllConvergedResultIRReceiptV1
    _source_family_receipt: HipFgmresAllConvergedModelFamilyReceiptV1
    _result_ir_bridges: tuple[HipFgmresResultIRBridgeResultV2, ...]

    @property
    def result_ir_bridges(self) -> tuple[HipFgmresResultIRBridgeResultV2, ...]:
        return self._result_ir_bridges

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_all_converged_result_ir_result_v1(self)
        return _receipt_payload(self.receipt, include_hash=True)


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresAllConvergedResultIRResultV1,
    _AggregateIssuanceV1,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_all_converged_result_ir_v1(
    family_result: HipFgmresAllConvergedModelFamilyResultV1,
    result_ir_bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
) -> HipFgmresAllConvergedResultIRResultV1:
    """Compose ten pre-issued bridges under one exact live family token."""

    first = _capture_family_source(family_result)
    registry_transaction = first.registry_transaction
    receipt, canonical = _evaluate(first, result_ir_bridges)
    second = _capture_family_source(family_result, registry_transaction)
    if not _same_family_source(first, second):
        _fail("hip_fgmres_all_converged_result_ir_family_changed", "/family")
    receipt, canonical = _evaluate(second, canonical)
    final = _capture_family_source(family_result, registry_transaction)
    if not _same_family_source(second, final):
        _fail("hip_fgmres_all_converged_result_ir_family_changed", "/family")
    receipt, canonical = _evaluate(final, canonical)
    try:
        refreshed_registry = _refresh_family_registry_transaction_v1(
            registry_transaction
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_result_ir_family_authority_invalid",
            "/family",
            f"{type(exc).__name__}: {exc}",
        )
    if refreshed_registry is not final.registry:
        _fail("hip_fgmres_all_converged_result_ir_family_changed", "/family")
    result = HipFgmresAllConvergedResultIRResultV1(
        receipt=receipt,
        _source_family_receipt=final.receipt,
        _result_ir_bridges=canonical,
    )
    issuance = _AggregateIssuanceV1(
        mint=object(),
        family_identity_token=final.family_identity_token,
        family_receipt=final.receipt,
        receipt=receipt,
        bridges=canonical,
        bridge_snapshots=tuple(_bridge_snapshot(row) for row in canonical),
        receipt_payload_hash=canonical_hash(
            _receipt_payload(receipt, include_hash=True)
        ),
        family_payload_hash=canonical_hash(
            _family_receipt_payload(final.receipt, include_hash=True)
        ),
    )
    with _ISSUANCE_LOCK:
        _ISSUANCES[result] = issuance
    try:
        _validate_result_source_v1(result)
        _validate_issued_result_against_registry_v1(result, final.registry)
        return result
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_all_converged_result_ir_result_v1(
    result: HipFgmresAllConvergedResultIRResultV1,
) -> HipFgmresAllConvergedResultIRResultV1:
    """Replay an issued aggregate without consulting any live HIP authority."""

    _validate_result_source_v1(result)
    registry = load_hip_fgmres_all_converged_fixture_registry_v1()
    _validate_issued_result_against_registry_v1(result, registry)
    return result


def _validate_result_source_v1(
    result: HipFgmresAllConvergedResultIRResultV1,
) -> None:
    if type(result) is not HipFgmresAllConvergedResultIRResultV1:
        _fail("hip_fgmres_all_converged_result_ir_result_type_invalid", "/")
    if (
        type(result._source_family_receipt)
        is not HipFgmresAllConvergedModelFamilyReceiptV1
        or type(result._result_ir_bridges) is not tuple
        or len(result._result_ir_bridges) != 10
        or any(
            type(row) is not HipFgmresResultIRBridgeResultV2
            for row in result._result_ir_bridges
        )
        or len({id(row) for row in result._result_ir_bridges}) != 10
    ):
        _fail("hip_fgmres_all_converged_result_ir_source_invalid", "/source")


def _validate_issued_result_against_registry_v1(
    result: HipFgmresAllConvergedResultIRResultV1,
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> None:
    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_result_ir_registry_type_invalid", "/registry")
    # One package replay supplies the complete detached validation authority
    # for this call.  All remaining checks are value/identity replays and must
    # not recursively invoke public validators that load the registry again.
    _validate_receipt_structure(result.receipt)
    _validate_receipt_semantics(result.receipt, registry)
    _validate_family_receipt_structure(result._source_family_receipt)
    _validate_family_receipt_semantics(result._source_family_receipt, registry)
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _AggregateIssuanceV1:
        _fail(
            "hip_fgmres_all_converged_result_ir_issuance_unavailable",
            "/issuance",
        )
    if (
        issuance.receipt is not result.receipt
        or issuance.family_receipt is not result._source_family_receipt
        or issuance.bridges is not result._result_ir_bridges
        or type(issuance.mint) is not object
        or type(issuance.family_identity_token) is not object
        or issuance.receipt_payload_hash
        != canonical_hash(_receipt_payload(result.receipt, include_hash=True))
        or issuance.family_payload_hash
        != canonical_hash(
            _family_receipt_payload(
                result._source_family_receipt,
                include_hash=True,
            )
        )
        or len(issuance.bridge_snapshots) != 10
    ):
        _fail(
            "hip_fgmres_all_converged_result_ir_issuance_binding_mismatch",
            "/issuance",
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
        result._source_family_receipt,
        result._result_ir_bridges,
        registry,
    )


def validate_hip_fgmres_all_converged_result_ir_receipt_v1(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
) -> HipFgmresAllConvergedResultIRReceiptV1:
    """Validate detached structure; this is not a live provenance gate."""

    _validate_receipt_structure(receipt)
    registry = load_hip_fgmres_all_converged_fixture_registry_v1()
    _validate_receipt_semantics(receipt, registry)
    return receipt


def _validate_receipt_structure(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
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
            "hip_fgmres_all_converged_result_ir_schema_invalid",
            "/" + "/".join(str(part) for part in first.absolute_path),
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_all_converged_result_ir_receipt_hash_invalid",
            "/receipt_hash",
        )


def _capture_family_source(
    result: HipFgmresAllConvergedModelFamilyResultV1,
    registry_transaction: _FixedRegistryReplayTransactionV1 | None = None,
) -> _FamilyLiveBindingV1:
    if type(result) is not HipFgmresAllConvergedModelFamilyResultV1:
        _fail("hip_fgmres_all_converged_result_ir_family_type_invalid", "/family")
    try:
        if registry_transaction is None:
            binding, token = result._result_ir_downstream_authority_binding()
        else:
            binding = (
                _recapture_family_live_binding_with_refreshed_registry_transaction_v1(
                    result,
                    registry_transaction,
                )
            )
            token = binding.family_identity_token
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_result_ir_family_authority_invalid",
            "/family",
            f"{type(exc).__name__}: {exc}",
        )
    if (
        type(binding) is not _FamilyLiveBindingV1
        or binding.family_result is not result
        or type(token) is not object
        or token is not binding.family_identity_token
        or type(binding.canonical_cases) is not tuple
        or len(binding.canonical_cases) != 10
        or any(
            type(row) is not HipFgmresModelCaseParityResultV1
            for row in binding.canonical_cases
        )
        or type(binding.registry) is not HipFgmresAllConvergedFixtureRegistryResultV1
        or type(binding.registry_transaction) is not _FixedRegistryReplayTransactionV1
        or (
            registry_transaction is not None
            and binding.registry_transaction is not registry_transaction
        )
    ):
        _fail(
            "hip_fgmres_all_converged_result_ir_family_binding_invalid",
            "/family",
        )
    return binding


def _same_family_source(
    left: _FamilyLiveBindingV1, right: _FamilyLiveBindingV1
) -> bool:
    return (
        left.family_result is right.family_result
        and left.receipt is right.receipt
        and left.canonical_cases is right.canonical_cases
        and left.family_identity_token is right.family_identity_token
        and left.source_token == right.source_token
        and left.registry is right.registry
        and left.registry_transaction is right.registry_transaction
        and left.registry.registry_bytes_sha256 == right.registry.registry_bytes_sha256
        and left.registry.registry_hash == right.registry.registry_hash
    )


def _evaluate(
    source: _FamilyLiveBindingV1,
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
) -> tuple[
    HipFgmresAllConvergedResultIRReceiptV1,
    tuple[HipFgmresResultIRBridgeResultV2, ...],
]:
    if (
        type(bridges) is not tuple
        or len(bridges) != 10
        or any(type(row) is not HipFgmresResultIRBridgeResultV2 for row in bridges)
        or len({id(row) for row in bridges}) != 10
    ):
        _fail("hip_fgmres_all_converged_result_ir_bridge_set_invalid", "/bridges")
    bridge_by_case: dict[str, HipFgmresResultIRBridgeResultV2] = {}
    for index, bridge in enumerate(bridges):
        try:
            validate_hip_fgmres_result_ir_v2(bridge)
        except Exception as exc:
            _fail(
                "hip_fgmres_all_converged_result_ir_bridge_invalid",
                f"/bridges/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        case_hash = bridge.receipt.source_provenance.case_parity_receipt_hash
        if case_hash in bridge_by_case:
            _fail(
                "hip_fgmres_all_converged_result_ir_duplicate_bridge_case",
                f"/bridges/{index}",
            )
        bridge_by_case[case_hash] = bridge

    canonical: list[HipFgmresResultIRBridgeResultV2] = []
    observations: list[HipFgmresAllConvergedResultIRObservationV1] = []
    for index, (slot, family_row, case) in enumerate(
        zip(
            source.registry.slots,
            source.receipt.observations,
            source.canonical_cases,
            strict=True,
        )
    ):
        if case.receipt.receipt_hash != family_row.case_receipt_hash:
            _fail(
                "hip_fgmres_all_converged_result_ir_family_case_join_invalid",
                f"/observations/{index}",
            )
        bridge = bridge_by_case.pop(family_row.case_receipt_hash, None)
        if bridge is None:
            _fail(
                "hip_fgmres_all_converged_result_ir_bridge_missing",
                f"/observations/{index}",
            )
        try:
            _validate_hip_fgmres_result_ir_v2_against_live_case(bridge, case)
        except Exception as exc:
            _fail(
                "hip_fgmres_all_converged_result_ir_bridge_live_case_invalid",
                f"/bridges/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        observations.append(_ready_observation(slot, family_row, bridge, index=index))
        # Rebind after reading every observation value.  A bridge/case authority
        # that changes during composition cannot be issued from the first view.
        try:
            _validate_hip_fgmres_result_ir_v2_against_live_case(bridge, case)
        except Exception as exc:
            _fail(
                "hip_fgmres_all_converged_result_ir_bridge_changed",
                f"/bridges/{index}",
                f"{type(exc).__name__}: {exc}",
            )
        canonical.append(bridge)
    if bridge_by_case:
        _fail("hip_fgmres_all_converged_result_ir_foreign_bridge", "/bridges")

    ordered = tuple(observations)
    canonical_bridges = tuple(canonical)
    totals = _totals(source.registry, ordered)
    bindings = HipFgmresAllConvergedResultIRBindingsV1(
        registry_schema_version=(
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        ),
        fixture_suite_id=HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
        registry_bytes_sha256=source.registry.registry_bytes_sha256,
        registry_hash=source.registry.registry_hash,
        source_family_schema_version=source.receipt.schema_version,
        source_family_capability_profile=source.receipt.capability_profile,
        source_family_attestation_id=source.receipt.attestation_id,
        source_family_receipt_hash=source.receipt.receipt_hash,
        result_ir_schema_version=RESULT_IR_V2_SCHEMA_VERSION,
        result_ir_capability_profile=RESULT_IR_V2_CAPABILITY_PROFILE,
        result_ir_bridge_capability_profile=(
            HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE
        ),
        required_architecture_base="gfx1030",
        required_slot_ids=HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_SLOT_IDS_V1,
    )
    claims = HipFgmresAllConvergedResultIRClaimsV1()
    attestation_id = canonical_hash(
        {
            "capability_profile": HIP_FGMRES_ALL_CONVERGED_RESULT_IR_CAPABILITY_PROFILE_V1,
            "registry_hash": source.registry.registry_hash,
            "source_family_receipt_hash": source.receipt.receipt_hash,
            "aggregate_binding_hashes": [row.aggregate_binding_hash for row in ordered],
        }
    )
    draft = HipFgmresAllConvergedResultIRReceiptV1(
        status=HIP_FGMRES_ALL_CONVERGED_RESULT_IR_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=HIP_FGMRES_ALL_CONVERGED_RESULT_IR_EVIDENCE_SCOPE_V1,
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
    _validate_receipt_structure(receipt)
    _validate_receipt_semantics(receipt, source.registry)
    return receipt, canonical_bridges


def _ready_observation(
    slot: HipFgmresAllConvergedFixtureReplayV1,
    family_row: HipFgmresAllConvergedModelFamilyObservationV1,
    bridge: HipFgmresResultIRBridgeResultV2,
    *,
    index: int,
) -> HipFgmresAllConvergedResultIRObservationV1:
    validate_hip_fgmres_result_ir_v2(bridge)
    result_ir = bridge.receipt
    plan = bridge.source_execution_plan
    provenance = result_ir.source_provenance
    arrays = result_ir.arrays.ordered()
    byte_count = sum(row.byte_length for row in arrays)
    expected_bytes = (
        24 * plan.dof_count + 104 * plan.element_count + 8 * len(plan.free_dofs)
    )
    if (
        family_row.slot_id != slot.slot_id
        or family_row.slot_registration_hash != slot.slot_registration_hash
        or plan.plan_hash != slot.execution_plan.plan_hash
        or result_ir.input_bindings.execution_plan_hash != plan.plan_hash
        or result_ir.input_bindings.model_ir_content_hash != slot.model.content_hash
        or provenance.case_id != family_row.case_id
        or provenance.case_parity_receipt_hash != family_row.case_receipt_hash
        or provenance.terminal_observation_receipt_hash
        != family_row.terminal_observation_receipt_hash
        or provenance.completion_export_receipt_hash
        != family_row.completion_export_receipt_hash
        or provenance.completion_export_payload_hash
        != family_row.completion_export_payload_hash
        or provenance.device_identity_receipt_hash
        != family_row.device_identity_receipt_hash
        or provenance.compiled_architecture != "gfx1030"
        or provenance.runtime_architecture_base != "gfx1030"
        or provenance.device_ordinal != family_row.device_ordinal
        or provenance.device_uuid_bytes_hex != family_row.device_uuid_bytes_hex
        or provenance.device_pci_bdf != family_row.device_pci_bdf
        or result_ir.input_bindings.evaluated_trial_state_hash
        != bridge.evaluated_trial_state.state_hash
        or result_ir.input_bindings.committed_state_hash
        != bridge.committed_state.state_hash
        or result_ir.claims.result_ir_verified is not True
        or result_ir.claims.result_ir_ready is not True
        or len(arrays) != 6
        or byte_count != expected_bytes
        or provenance.additional_device_operation_count != 0
        or provenance.additional_d2h_operation_count != 0
        or provenance.additional_solve_count != 0
        or provenance.additional_export_count != 0
        or provenance.fallback_count != 0
    ):
        _fail(
            "hip_fgmres_all_converged_result_ir_cross_binding_invalid",
            f"/observations/{index}",
        )
    draft = HipFgmresAllConvergedResultIRObservationV1(
        slot_id=slot.slot_id,
        slot_registration_hash=slot.slot_registration_hash,
        case_fingerprint=slot.case_fingerprint,
        family_observation_binding_hash=family_row.observation_binding_hash,
        logical_case_key=family_row.logical_case_key,
        case_id=family_row.case_id,
        case_receipt_hash=family_row.case_receipt_hash,
        model_ir_content_hash=family_row.model_ir_content_hash,
        execution_plan_hash=family_row.execution_plan_hash,
        cpu_result_hash=family_row.cpu_result_hash,
        terminal_observation_receipt_hash=(
            family_row.terminal_observation_receipt_hash
        ),
        completion_export_receipt_hash=family_row.completion_export_receipt_hash,
        completion_export_payload_hash=family_row.completion_export_payload_hash,
        device_identity_receipt_hash=family_row.device_identity_receipt_hash,
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=family_row.device_ordinal,
        device_uuid_bytes_hex=family_row.device_uuid_bytes_hex,
        device_pci_bdf=family_row.device_pci_bdf,
        cpu_status="converged",
        solver_tolerance_passed=True,
        authoritative_plan_tolerance_passed=True,
        disposition="ready_result_ir_v2",
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
        aggregate_binding_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        aggregate_binding_hash=canonical_hash(
            _observation_payload(draft, include_binding_hash=False)
        ),
    )


def _validate_detached_composition(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
    family_receipt: HipFgmresAllConvergedModelFamilyReceiptV1,
    bridges: tuple[HipFgmresResultIRBridgeResultV2, ...],
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> None:
    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail(
            "hip_fgmres_all_converged_result_ir_registry_type_invalid",
            "/registry",
        )
    bindings = receipt.bindings
    if (
        bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_family_schema_version != family_receipt.schema_version
        or bindings.source_family_capability_profile
        != family_receipt.capability_profile
        or bindings.source_family_attestation_id != family_receipt.attestation_id
        or bindings.source_family_receipt_hash != family_receipt.receipt_hash
    ):
        _fail(
            "hip_fgmres_all_converged_result_ir_detached_binding_mismatch",
            "/bindings",
        )
    bridge_by_case: dict[str, HipFgmresResultIRBridgeResultV2] = {}
    for index, bridge in enumerate(bridges):
        validate_hip_fgmres_result_ir_v2(bridge)
        key = bridge.receipt.source_provenance.case_parity_receipt_hash
        if key in bridge_by_case:
            _fail(
                "hip_fgmres_all_converged_result_ir_duplicate_bridge_case",
                f"/bridges/{index}",
            )
        bridge_by_case[key] = bridge
    canonical: list[HipFgmresResultIRBridgeResultV2] = []
    rebuilt: list[HipFgmresAllConvergedResultIRObservationV1] = []
    for index, (row, family_row, slot) in enumerate(
        zip(
            receipt.observations,
            family_receipt.observations,
            registry.slots,
            strict=True,
        )
    ):
        bridge = bridge_by_case.pop(family_row.case_receipt_hash, None)
        if bridge is None:
            _fail(
                "hip_fgmres_all_converged_result_ir_bridge_missing",
                f"/observations/{index}",
            )
        expected = _ready_observation(slot, family_row, bridge, index=index)
        if row != expected:
            _fail(
                "hip_fgmres_all_converged_result_ir_detached_row_mismatch",
                f"/observations/{index}",
            )
        rebuilt.append(expected)
        canonical.append(bridge)
    if bridge_by_case:
        _fail("hip_fgmres_all_converged_result_ir_foreign_bridge", "/bridges")
    if any(left is not right for left, right in zip(canonical, bridges, strict=True)):
        _fail(
            "hip_fgmres_all_converged_result_ir_bridge_order_invalid",
            "/bridges",
        )
    if receipt.totals != _totals(registry, tuple(rebuilt)):
        _fail("hip_fgmres_all_converged_result_ir_totals_invalid", "/totals")


def _totals(
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
    observations: tuple[HipFgmresAllConvergedResultIRObservationV1, ...],
) -> HipFgmresAllConvergedResultIRTotalsV1:
    plans = tuple(row.execution_plan for row in registry.slots)
    return HipFgmresAllConvergedResultIRTotalsV1(
        required_slot_count=10,
        ready_result_ir_v2_count=len(observations),
        solution_ready_count=len(observations),
        not_issued_count=0,
        diagnostic_ir_count=0,
        unique_result_ir_bridge_count=len({row.result_ir_hash for row in observations}),
        committed_state_count=len({row.committed_state_hash for row in observations}),
        package_global_dof_count=sum(row.dof_count for row in plans),
        package_element_count=sum(row.element_count for row in plans),
        package_free_dof_count=sum(len(row.free_dofs) for row in plans),
        package_csr_nnz=sum(row.nnz for row in plans),
        result_array_count=sum(row.result_array_count for row in observations),
        result_array_byte_count=sum(
            row.result_array_byte_count for row in observations
        ),
        detached_raw_payload_byte_count=sum(
            row.detached_raw_payload_byte_count for row in observations
        ),
        upstream_completion_export_blocking_d2h_attempt_count=30,
        upstream_completion_export_blocking_d2h_success_count=30,
        upstream_completion_export_blocking_d2h_failure_count=0,
        upstream_completion_export_byte_count=sum(
            16 * len(slot.execution_plan.free_dofs)
            + 192
            + 72 * slot.fgmres_plan.maximum_restart_count
            for slot in registry.slots
        ),
        aggregate_additional_device_operation_count=0,
        aggregate_additional_d2h_operation_count=0,
        aggregate_additional_solve_count=0,
        aggregate_additional_export_count=0,
        aggregate_fallback_count=0,
    )


def _validate_receipt_semantics(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> None:
    bindings = receipt.bindings
    if (
        receipt.status != HIP_FGMRES_ALL_CONVERGED_RESULT_IR_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_ALL_CONVERGED_RESULT_IR_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or bindings.registry_schema_version
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1
        or bindings.fixture_suite_id
        != HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1
        or bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.source_family_schema_version
        != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_SCHEMA_VERSION_V1
        or bindings.source_family_capability_profile
        != HIP_FGMRES_ALL_CONVERGED_MODEL_FAMILY_CAPABILITY_PROFILE_V1
        or bindings.result_ir_schema_version != RESULT_IR_V2_SCHEMA_VERSION
        or bindings.result_ir_capability_profile != RESULT_IR_V2_CAPABILITY_PROFILE
        or bindings.result_ir_bridge_capability_profile
        != HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE
        or bindings.required_architecture_base != "gfx1030"
        or bindings.required_slot_ids
        != HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_SLOT_IDS_V1
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_SLOT_IDS_V1
    ):
        _fail("hip_fgmres_all_converged_result_ir_semantics_invalid", "/")
    seen_case_ids: set[str] = set()
    seen_case_receipt_hashes: set[str] = set()
    for index, (row, slot) in enumerate(
        zip(receipt.observations, registry.slots, strict=True)
    ):
        if (
            row.case_id in seen_case_ids
            or row.case_receipt_hash in seen_case_receipt_hashes
        ):
            _fail(
                "hip_fgmres_all_converged_result_ir_duplicate_bridge_case",
                f"/bridges/{index}",
            )
        seen_case_ids.add(row.case_id)
        seen_case_receipt_hashes.add(row.case_receipt_hash)
        expected_bytes = (
            24 * slot.execution_plan.dof_count
            + 104 * slot.execution_plan.element_count
            + 8 * len(slot.execution_plan.free_dofs)
        )
        if (
            row.slot_registration_hash != slot.slot_registration_hash
            or row.case_fingerprint != slot.case_fingerprint
            or row.model_ir_content_hash != slot.model.content_hash
            or row.execution_plan_hash != slot.execution_plan.plan_hash
            or row.cpu_result_hash != slot.cpu_result.result_hash
            or row.compiled_architecture != "gfx1030"
            or row.runtime_architecture_base != "gfx1030"
            or row.cpu_status != "converged"
            or row.solver_tolerance_passed is not True
            or row.authoritative_plan_tolerance_passed is not True
            or row.disposition != "ready_result_ir_v2"
            or row.result_array_count != 6
            or row.result_array_byte_count != expected_bytes
            or row.detached_raw_payload_byte_count
            != 16 * len(slot.execution_plan.free_dofs)
            or row.additional_device_operation_count != 0
            or row.additional_d2h_operation_count != 0
            or row.additional_solve_count != 0
            or row.additional_export_count != 0
            or row.fallback_count != 0
            or row.aggregate_binding_hash
            != canonical_hash(_observation_payload(row, include_binding_hash=False))
        ):
            _fail(
                "hip_fgmres_all_converged_result_ir_observation_invalid",
                f"/observations/{index}",
            )
    if receipt.totals != _totals(registry, receipt.observations):
        _fail("hip_fgmres_all_converged_result_ir_totals_invalid", "/totals")
    if receipt.claims != HipFgmresAllConvergedResultIRClaimsV1():
        _fail("hip_fgmres_all_converged_result_ir_claims_invalid", "/claims")
    expected_attestation = canonical_hash(
        {
            "capability_profile": receipt.capability_profile,
            "registry_hash": bindings.registry_hash,
            "source_family_receipt_hash": bindings.source_family_receipt_hash,
            "aggregate_binding_hashes": [
                row.aggregate_binding_hash for row in receipt.observations
            ],
        }
    )
    if receipt.attestation_id != expected_attestation:
        _fail(
            "hip_fgmres_all_converged_result_ir_attestation_invalid",
            "/attestation_id",
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
        _fail("hip_fgmres_all_converged_result_ir_bridge_changed", path)


def _validate_exact_receipt_types(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
) -> None:
    if type(receipt) is not HipFgmresAllConvergedResultIRReceiptV1:
        _fail("hip_fgmres_all_converged_result_ir_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not HipFgmresAllConvergedResultIRBindingsV1
        or type(receipt.observations) is not tuple
        or len(receipt.observations) != 10
        or any(
            type(row) is not HipFgmresAllConvergedResultIRObservationV1
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresAllConvergedResultIRTotalsV1
        or type(receipt.claims) is not HipFgmresAllConvergedResultIRClaimsV1
    ):
        _fail("hip_fgmres_all_converged_result_ir_receipt_container_invalid", "/")


def _observation_payload(
    row: HipFgmresAllConvergedResultIRObservationV1,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = row.to_dict()
    if not include_binding_hash:
        payload.pop("aggregate_binding_hash")
    return payload


def _receipt_payload(
    receipt: HipFgmresAllConvergedResultIRReceiptV1,
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
    raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    schema = json.loads(raw.decode("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresAllConvergedResultIRV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_SCHEMA_VERSION_V1",
    "HIP_FGMRES_ALL_CONVERGED_RESULT_IR_STATUS_V1",
    "HipFgmresAllConvergedResultIRBindingsV1",
    "HipFgmresAllConvergedResultIRClaimsV1",
    "HipFgmresAllConvergedResultIRObservationV1",
    "HipFgmresAllConvergedResultIRReceiptV1",
    "HipFgmresAllConvergedResultIRResultV1",
    "HipFgmresAllConvergedResultIRTotalsV1",
    "HipFgmresAllConvergedResultIRV1Error",
    "attest_hip_fgmres_all_converged_result_ir_v1",
    "validate_hip_fgmres_all_converged_result_ir_receipt_v1",
    "validate_hip_fgmres_all_converged_result_ir_result_v1",
]
