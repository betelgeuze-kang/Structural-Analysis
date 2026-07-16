"""Exact three-case aggregate for original-scale high-load ResultIR v3.

The package-owned high-load compatibility registry fixes the three original-
scale models and their CPU/plan replay.  This module composes exactly three
already-issued :class:`HipFgmresResultIRResultV3` objects in registry order.
It performs no native solve, allocation, launch, synchronization, export, or
host transfer.  Each child remains the process-local provenance authority;
the aggregate is a detached, unsigned, non-promoting cross-binding receipt.

Serialized aggregate bytes never recreate child issuance authority.  Public
validation therefore requires the exact in-process ResultIR v3 objects while
allowing their original HIP contexts to have been closed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)

from .fgmres_high_load_compatibility_registry_v1 import (
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1,
    HipFgmresHighLoadCompatibilityRegistryResultV1,
    HipFgmresHighLoadCompatibilityReplayV1,
    _issue_high_load_registry_transaction_v1,
    _refresh_high_load_registry_transaction_v1,
    load_hip_fgmres_high_load_compatibility_registry_v1,
)
from .fgmres_result_ir_v3 import (
    HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3,
    HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3,
    HipFgmresResultIRClaimsV3,
    HipFgmresResultIRResultV3,
    validate_hip_fgmres_result_ir_v3,
)


HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-high-load-result-ir-aggregate.v1"
)
HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_CAPABILITY_PROFILE_V1 = (
    "phase0_original_scale_high_load_three_case_result_ir_v3_aggregate"
)
HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_STATUS_V1 = (
    "exact_gfx1030_high_load_three_case_result_ir_v3_verified"
)
HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_EVIDENCE_SCOPE_V1 = (
    "process_local_exact_children_detached_aggregate_unsigned_nonpromoting"
)
HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_ARCHITECTURE_V1 = "gfx1030"
HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_SLOT_IDS_V1 = (
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
)

_SCHEMA_RESOURCE = "hip_fgmres_high_load_result_ir_aggregate_v1.schema.json"
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_HASH = "sha256:" + "0" * 64


class HipFgmresHighLoadResultIRAggregateV1Error(RuntimeError):
    """Stable fail-closed high-load aggregate error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = " ".join(str(message or code).split())[:512]
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadResultIRAggregateBindingsV1:
    registry_schema_version: str
    registry_capability_profile: str
    registry_suite_id: str
    registry_bytes_sha256: str
    registry_hash: str
    registry_receipt_hash: str
    result_ir_schema_version: str
    result_ir_capability_profile: str
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
class HipFgmresHighLoadResultIRAggregateObservationV1:
    slot_id: str
    base_slot_id: str
    slot_registration_hash: str
    model_bytes_sha256: str
    model_ir_content_hash: str
    execution_plan_hash: str
    cpu_result_hash: str
    load_component: str
    high_load_value_si: float
    load_scale_factor: float
    case_id: str
    case_parity_receipt_hash: str
    terminal_metric_parity_receipt_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    compiled_architecture: Literal["gfx1030"]
    runtime_architecture_base: Literal["gfx1030"]
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    result_id: str
    result_ir_v3_receipt_hash: str
    base_result_ir_v2_hash: str
    base_numerical_result_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    solution_payload_sha256: str
    exported_residual_payload_sha256: str
    independent_fsum_residual_sha256: str
    result_ir_plan_residual_sha256: str
    exported_to_fsum_componentwise_receipt_hash: str
    fsum_to_result_ir_plan_componentwise_receipt_hash: str
    fixed_physics_witness_result_ir_hash: str
    terminal_maximum_record_bound_ratio: float
    exported_to_fsum_maximum_componentwise_bound_ratio: float
    fsum_to_result_ir_plan_maximum_componentwise_bound_ratio: float
    result_array_descriptor_hash: str
    result_array_count: Literal[6]
    result_array_byte_count: int
    detached_completion_payload_byte_count: int
    additional_device_operation_count: Literal[0]
    additional_d2h_operation_count: Literal[0]
    additional_solve_count: Literal[0]
    additional_export_count: Literal[0]
    fallback_count: Literal[0]
    aggregate_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadResultIRAggregateTotalsV1:
    required_slot_count: Literal[3]
    result_ir_v3_ready_count: Literal[3]
    retained_base_result_ir_v2_ready_count: Literal[0]
    unique_result_ir_v3_count: Literal[3]
    committed_state_count: Literal[3]
    package_global_dof_count: Literal[78]
    package_element_count: Literal[10]
    package_free_dof_count: Literal[60]
    package_csr_nnz: Literal[1188]
    result_array_count: Literal[18]
    result_array_byte_count: Literal[3392]
    detached_completion_payload_count: Literal[6]
    detached_completion_payload_byte_count: Literal[960]
    aggregate_additional_device_operation_count: Literal[0]
    aggregate_additional_d2h_operation_count: Literal[0]
    aggregate_additional_solve_count: Literal[0]
    aggregate_additional_export_count: Literal[0]
    aggregate_fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadResultIRAggregateClaimsV1:
    package_high_load_registry_replayed: Literal[True] = True
    historical_unit_load_registry_preserved: Literal[True] = True
    exact_three_original_scale_result_ir_v3_verified: Literal[True] = True
    exact_three_result_ir_v3_ready: Literal[True] = True
    retained_base_result_ir_v2_ready_count_zero: Literal[True] = True
    canonical_registry_order_verified: Literal[True] = True
    exact_child_identity_bound: Literal[True] = True
    case_plan_cpu_terminal_export_device_state_cross_bound: Literal[True] = True
    reaction_member_force_energy_and_state_lineage_verified: Literal[True] = True
    roundoff_aware_residual_chain_verified: Literal[True] = True
    actual_hip_source_provenance_verified_at_child_factories: Literal[True] = True
    post_close_process_local_child_validation_supported: Literal[True] = True
    aggregate_additional_device_operation_zero: Literal[True] = True
    aggregate_additional_d2h_zero: Literal[True] = True
    aggregate_additional_solve_zero: Literal[True] = True
    aggregate_additional_export_zero: Literal[True] = True
    aggregate_fallback_zero: Literal[True] = True
    general_restart_history_v2_verified: Literal[False] = False
    dedicated_persistent_hardware_gate_receipt: Literal[False] = False
    external_gfx1100_result_ir_verified: Literal[False] = False
    multiarchitecture_result_ir_verified: Literal[False] = False
    process_wide_host_transfer_zero_proven: Literal[False] = False
    device_result_recovery_verified: Literal[False] = False
    standalone_serialized_provenance: Literal[False] = False
    signed_evidence: Literal[False] = False
    persistent_external_log_verified: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    nonlinear_dynamic_shell_solid_contact_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadResultIRAggregateReceiptV1:
    status: Literal["exact_gfx1030_high_load_three_case_result_ir_v3_verified"]
    attestation_id: str
    evidence_scope: str
    actual_backend: Literal["hip"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresHighLoadResultIRAggregateBindingsV1
    observations: tuple[HipFgmresHighLoadResultIRAggregateObservationV1, ...]
    totals: HipFgmresHighLoadResultIRAggregateTotalsV1
    claims: HipFgmresHighLoadResultIRAggregateClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_high_load_result_ir_aggregate_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _ResultIRV3SnapshotV1:
    result: HipFgmresResultIRResultV3
    receipt: Any
    base_result_ir_v2: Any
    accepted_state: Any
    evaluated_trial_state: Any
    committed_state: Any
    terminal_metric_parity: Any
    fsum_to_plan_roundoff: Any
    source_execution_plan: Any
    source_solution_x: bytes
    source_true_residual: bytes
    source_case_identity_token: object
    receipt_payload_hash: str
    base_result_ir_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _AggregateIssuanceV1:
    mint: object
    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1
    children: tuple[HipFgmresResultIRResultV3, ...]
    snapshots: tuple[_ResultIRV3SnapshotV1, ...]
    registry_receipt_hash: str
    receipt_payload_hash: str


class _WeakReferenceableHighLoadResultIRAggregateV1:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresHighLoadResultIRAggregateResultV1(
    _WeakReferenceableHighLoadResultIRAggregateV1
):
    """Issued aggregate retaining the exact three ResultIR v3 children."""

    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1
    _result_ir_v3_children: tuple[HipFgmresResultIRResultV3, ...]

    @property
    def result_ir_v3_children(self) -> tuple[HipFgmresResultIRResultV3, ...]:
        return self._result_ir_v3_children

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_high_load_result_ir_aggregate_result_v1(self)
        return _receipt_payload(self.receipt, include_hash=True)


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresHighLoadResultIRAggregateResultV1,
    _AggregateIssuanceV1,
] = weakref.WeakKeyDictionary()


def attest_hip_fgmres_high_load_result_ir_aggregate_v1(
    result_ir_v3_children: tuple[HipFgmresResultIRResultV3, ...],
) -> HipFgmresHighLoadResultIRAggregateResultV1:
    """Compose three pre-issued high-load ResultIR v3 objects."""

    registry = load_hip_fgmres_high_load_compatibility_registry_v1()
    transaction = _issue_high_load_registry_transaction_v1(registry)
    receipt, canonical = _evaluate(registry, result_ir_v3_children)
    refreshed = _refresh_high_load_registry_transaction_v1(transaction)
    if refreshed is not registry:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_registry_changed",
            "/registry",
        )
    receipt, canonical = _evaluate(refreshed, canonical)
    if _refresh_high_load_registry_transaction_v1(transaction) is not registry:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_registry_changed",
            "/registry",
        )
    result = HipFgmresHighLoadResultIRAggregateResultV1(
        receipt=receipt,
        _result_ir_v3_children=canonical,
    )
    issuance = _AggregateIssuanceV1(
        mint=object(),
        receipt=receipt,
        children=canonical,
        snapshots=tuple(_child_snapshot(row) for row in canonical),
        registry_receipt_hash=registry.receipt_hash,
        receipt_payload_hash=canonical_hash(
            _receipt_payload(receipt, include_hash=True)
        ),
    )
    with _ISSUANCE_LOCK:
        _ISSUANCES[result] = issuance
    try:
        _validate_issued_result_against_registry(result, registry)
        return result
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_high_load_result_ir_aggregate_result_v1(
    result: HipFgmresHighLoadResultIRAggregateResultV1,
) -> HipFgmresHighLoadResultIRAggregateResultV1:
    """Validate one exact issued aggregate against a fresh package replay."""

    registry = load_hip_fgmres_high_load_compatibility_registry_v1()
    _validate_issued_result_against_registry(result, registry)
    return result


def validate_hip_fgmres_high_load_result_ir_aggregate_receipt_v1(
    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1,
) -> HipFgmresHighLoadResultIRAggregateReceiptV1:
    """Validate the detached receipt without granting child provenance."""

    registry = load_hip_fgmres_high_load_compatibility_registry_v1()
    _validate_receipt_structure(receipt)
    _validate_receipt_semantics(receipt, registry)
    return receipt


def _validate_issued_result_against_registry(
    result: HipFgmresHighLoadResultIRAggregateResultV1,
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
) -> None:
    if type(result) is not HipFgmresHighLoadResultIRAggregateResultV1:
        _fail("hip_fgmres_high_load_result_ir_aggregate_result_type_invalid", "/")
    if (
        type(result._result_ir_v3_children) is not tuple
        or len(result._result_ir_v3_children) != 3
        or any(
            type(row) is not HipFgmresResultIRResultV3
            for row in result._result_ir_v3_children
        )
        or len({id(row) for row in result._result_ir_v3_children}) != 3
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_source_invalid",
            "/source",
        )
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _AggregateIssuanceV1:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_issuance_unavailable",
            "/source/issuance",
        )
    if (
        issuance.receipt is not result.receipt
        or issuance.children is not result._result_ir_v3_children
        or issuance.registry_receipt_hash != registry.receipt_hash
        or issuance.receipt_payload_hash
        != canonical_hash(_receipt_payload(result.receipt, include_hash=True))
        or len(issuance.snapshots) != 3
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_issuance_binding_mismatch",
            "/source/issuance",
        )
    for index, (child, snapshot) in enumerate(
        zip(result._result_ir_v3_children, issuance.snapshots, strict=True)
    ):
        _validate_child_snapshot(child, snapshot, path=f"/source/children/{index}")
    expected, canonical = _evaluate(registry, result._result_ir_v3_children)
    if expected != result.receipt or any(
        left is not right
        for left, right in zip(canonical, result._result_ir_v3_children, strict=True)
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_replay_mismatch",
            "/",
        )


def _evaluate(
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
    children: tuple[HipFgmresResultIRResultV3, ...],
) -> tuple[
    HipFgmresHighLoadResultIRAggregateReceiptV1,
    tuple[HipFgmresResultIRResultV3, ...],
]:
    if type(registry) is not HipFgmresHighLoadCompatibilityRegistryResultV1:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_registry_type_invalid",
            "/registry",
        )
    if (
        type(children) is not tuple
        or len(children) != 3
        or any(type(row) is not HipFgmresResultIRResultV3 for row in children)
        or len({id(row) for row in children}) != 3
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_children_invalid",
            "/children",
        )
    by_plan: dict[str, HipFgmresResultIRResultV3] = {}
    for index, child in enumerate(children):
        validate_hip_fgmres_result_ir_v3(child)
        plan_hash = child.source_execution_plan.plan_hash
        if plan_hash in by_plan:
            _fail(
                "hip_fgmres_high_load_result_ir_aggregate_duplicate_child",
                f"/children/{index}",
            )
        by_plan[plan_hash] = child
    canonical: list[HipFgmresResultIRResultV3] = []
    observations: list[HipFgmresHighLoadResultIRAggregateObservationV1] = []
    for index, slot in enumerate(registry.slots):
        child = by_plan.pop(slot.execution_plan.plan_hash, None)
        if child is None:
            _fail(
                "hip_fgmres_high_load_result_ir_aggregate_child_missing",
                f"/observations/{index}",
            )
        observations.append(_observation(slot, child, index=index))
        canonical.append(child)
    if by_plan:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_foreign_child",
            "/children",
        )
    bindings = HipFgmresHighLoadResultIRAggregateBindingsV1(
        registry_schema_version=(
            HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1
        ),
        registry_capability_profile=(
            HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1
        ),
        registry_suite_id=HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1,
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        registry_receipt_hash=registry.receipt_hash,
        result_ir_schema_version=HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3,
        result_ir_capability_profile=HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3,
        required_architecture_base="gfx1030",
        required_slot_ids=(
            HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_SLOT_IDS_V1
        ),
    )
    observation_tuple = tuple(observations)
    totals = _totals(registry, observation_tuple)
    attestation_id = canonical_hash(
        {
            "capability_profile": (
                HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_CAPABILITY_PROFILE_V1
            ),
            "registry_receipt_hash": registry.receipt_hash,
            "aggregate_binding_hashes": [
                row.aggregate_binding_hash for row in observation_tuple
            ],
        }
    )
    draft = HipFgmresHighLoadResultIRAggregateReceiptV1(
        status=HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_STATUS_V1,
        attestation_id=attestation_id,
        evidence_scope=HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        observations=observation_tuple,
        totals=totals,
        claims=HipFgmresHighLoadResultIRAggregateClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    _validate_receipt_structure(receipt)
    _validate_receipt_semantics(receipt, registry)
    return receipt, tuple(canonical)


def _observation(
    slot: HipFgmresHighLoadCompatibilityReplayV1,
    child: HipFgmresResultIRResultV3,
    *,
    index: int,
) -> HipFgmresHighLoadResultIRAggregateObservationV1:
    receipt = child.receipt
    bindings = receipt.bindings
    plan = child.source_execution_plan
    base = child.base_result_ir_v2
    provenance = base.source_provenance
    terminal_bindings = child.terminal_metric_parity.receipt.bindings
    arrays = base.arrays.ordered()
    array_bytes = sum(row.byte_length for row in arrays)
    expected_array_bytes = (
        24 * plan.dof_count + 104 * plan.element_count + 8 * len(plan.free_dofs)
    )
    ratios = (
        receipt.residual_validation.terminal_maximum_record_bound_ratio,
        receipt.residual_validation.exported_to_fsum_maximum_componentwise_bound_ratio,
        receipt.residual_validation.fsum_to_result_ir_plan_maximum_componentwise_bound_ratio,
    )
    if (
        receipt.schema_version != HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3
        or receipt.capability_profile != HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3
        or receipt.status != "result_ir_v3_ready"
        or receipt.claims != HipFgmresResultIRClaimsV3()
        or not receipt.claims.result_ir_v3_ready
        or receipt.claims.general_restart_history_v2_verified
        or receipt.claims.commercial_ready
        or receipt.claims.promotion_eligible
        or base.claims.result_ir_ready
        or plan.plan_hash != slot.execution_plan.plan_hash
        or base.input_bindings.execution_plan_hash != slot.execution_plan.plan_hash
        or base.input_bindings.model_ir_content_hash != slot.model.content_hash
        or bindings.execution_plan_hash != slot.execution_plan.plan_hash
        or terminal_bindings.execution_plan_hash != slot.execution_plan.plan_hash
        or terminal_bindings.cpu_result_hash != slot.cpu_result.result_hash
        or provenance.case_id != bindings.case_id
        or provenance.case_parity_receipt_hash != bindings.case_parity_receipt_hash
        or provenance.terminal_observation_receipt_hash
        != bindings.terminal_observation_receipt_hash
        or provenance.completion_export_receipt_hash
        != bindings.completion_export_receipt_hash
        or provenance.completion_export_payload_hash
        != bindings.completion_export_payload_hash
        or provenance.device_identity_receipt_hash
        != bindings.device_identity_receipt_hash
        or provenance.solution_payload_sha256 != bindings.solution_payload_sha256
        or provenance.exported_free_residual_payload_sha256
        != bindings.exported_residual_payload_sha256
        or provenance.actual_backend != "hip"
        or provenance.compiled_architecture != "gfx1030"
        or provenance.runtime_architecture_base != "gfx1030"
        or provenance.additional_device_operation_count != 0
        or provenance.additional_d2h_operation_count != 0
        or provenance.additional_solve_count != 0
        or provenance.additional_export_count != 0
        or provenance.fallback_count != 0
        or bindings.evaluated_trial_state_hash != child.evaluated_trial_state.state_hash
        or bindings.committed_state_hash != child.committed_state.state_hash
        or len(arrays) != 6
        or array_bytes != expected_array_bytes
        or len(child._source_solution_x) != 8 * len(plan.free_dofs)
        or len(child._source_true_residual) != 8 * len(plan.free_dofs)
        or sha256_prefixed(child._source_solution_x) != bindings.solution_payload_sha256
        or sha256_prefixed(child._source_true_residual)
        != bindings.exported_residual_payload_sha256
        or any(
            not math.isfinite(value) or value < 0.0 or value > 1.0 for value in ratios
        )
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_cross_binding_invalid",
            f"/observations/{index}",
        )
    draft = HipFgmresHighLoadResultIRAggregateObservationV1(
        slot_id=slot.slot_id,
        base_slot_id=slot.base_slot_id,
        slot_registration_hash=slot.slot_registration_hash,
        model_bytes_sha256=slot.model_bytes_sha256,
        model_ir_content_hash=slot.model.content_hash,
        execution_plan_hash=slot.execution_plan.plan_hash,
        cpu_result_hash=slot.cpu_result.result_hash,
        load_component=slot.load_component,
        high_load_value_si=slot.high_load_value_si,
        load_scale_factor=slot.load_scale_factor,
        case_id=bindings.case_id,
        case_parity_receipt_hash=bindings.case_parity_receipt_hash,
        terminal_metric_parity_receipt_hash=(
            bindings.terminal_metric_parity_receipt_hash
        ),
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=provenance.device_ordinal,
        device_uuid_bytes_hex=provenance.device_uuid_bytes_hex,
        device_pci_bdf=provenance.device_pci_bdf,
        result_id=receipt.result_id,
        result_ir_v3_receipt_hash=receipt.receipt_hash,
        base_result_ir_v2_hash=bindings.base_result_ir_v2_hash,
        base_numerical_result_hash=bindings.base_numerical_result_hash,
        accepted_state_hash=child.accepted_state.state_hash,
        evaluated_trial_state_hash=child.evaluated_trial_state.state_hash,
        committed_state_hash=child.committed_state.state_hash,
        solution_payload_sha256=bindings.solution_payload_sha256,
        exported_residual_payload_sha256=(bindings.exported_residual_payload_sha256),
        independent_fsum_residual_sha256=(bindings.independent_fsum_residual_sha256),
        result_ir_plan_residual_sha256=(
            bindings.result_ir_plan_residual_f_minus_ku_sha256
        ),
        exported_to_fsum_componentwise_receipt_hash=(
            bindings.exported_to_fsum_componentwise_receipt_hash
        ),
        fsum_to_result_ir_plan_componentwise_receipt_hash=(
            bindings.fsum_to_result_ir_plan_componentwise_receipt_hash
        ),
        fixed_physics_witness_result_ir_hash=(
            bindings.fixed_physics_witness_result_ir_hash
        ),
        terminal_maximum_record_bound_ratio=ratios[0],
        exported_to_fsum_maximum_componentwise_bound_ratio=ratios[1],
        fsum_to_result_ir_plan_maximum_componentwise_bound_ratio=ratios[2],
        result_array_descriptor_hash=canonical_hash(base.arrays.to_dict()),
        result_array_count=6,
        result_array_byte_count=array_bytes,
        detached_completion_payload_byte_count=(
            len(child._source_solution_x) + len(child._source_true_residual)
        ),
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


def _totals(
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
    observations: tuple[HipFgmresHighLoadResultIRAggregateObservationV1, ...],
) -> HipFgmresHighLoadResultIRAggregateTotalsV1:
    plans = tuple(row.execution_plan for row in registry.slots)
    return HipFgmresHighLoadResultIRAggregateTotalsV1(
        required_slot_count=3,
        result_ir_v3_ready_count=len(observations),
        retained_base_result_ir_v2_ready_count=0,
        unique_result_ir_v3_count=len(
            {row.result_ir_v3_receipt_hash for row in observations}
        ),
        committed_state_count=len({row.committed_state_hash for row in observations}),
        package_global_dof_count=sum(row.dof_count for row in plans),
        package_element_count=sum(row.element_count for row in plans),
        package_free_dof_count=sum(len(row.free_dofs) for row in plans),
        package_csr_nnz=sum(row.nnz for row in plans),
        result_array_count=sum(row.result_array_count for row in observations),
        result_array_byte_count=sum(
            row.result_array_byte_count for row in observations
        ),
        detached_completion_payload_count=2 * len(observations),
        detached_completion_payload_byte_count=sum(
            row.detached_completion_payload_byte_count for row in observations
        ),
        aggregate_additional_device_operation_count=0,
        aggregate_additional_d2h_operation_count=0,
        aggregate_additional_solve_count=0,
        aggregate_additional_export_count=0,
        aggregate_fallback_count=0,
    )


def _validate_receipt_structure(
    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1,
) -> None:
    if type(receipt) is not HipFgmresHighLoadResultIRAggregateReceiptV1:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_receipt_type_invalid",
            "/",
        )
    if (
        type(receipt.bindings) is not HipFgmresHighLoadResultIRAggregateBindingsV1
        or type(receipt.observations) is not tuple
        or len(receipt.observations) != 3
        or any(
            type(row) is not HipFgmresHighLoadResultIRAggregateObservationV1
            for row in receipt.observations
        )
        or type(receipt.totals) is not HipFgmresHighLoadResultIRAggregateTotalsV1
        or type(receipt.claims) is not HipFgmresHighLoadResultIRAggregateClaimsV1
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_container_invalid",
            "/",
        )
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: tuple(str(part) for part in row.absolute_path),
    )
    if errors:
        first = errors[0]
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_schema_invalid",
            "/" + "/".join(str(part) for part in first.absolute_path),
            first.message,
        )
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if receipt.receipt_hash != expected_hash:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_receipt_hash_invalid",
            "/receipt_hash",
        )


def _validate_receipt_semantics(
    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1,
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
) -> None:
    bindings = receipt.bindings
    if (
        receipt.status != HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_STATUS_V1
        or receipt.evidence_scope
        != HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
        or bindings.registry_schema_version
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1
        or bindings.registry_capability_profile
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1
        or bindings.registry_suite_id
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1
        or bindings.registry_bytes_sha256 != registry.registry_bytes_sha256
        or bindings.registry_hash != registry.registry_hash
        or bindings.registry_receipt_hash != registry.receipt_hash
        or bindings.result_ir_schema_version != HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3
        or bindings.result_ir_capability_profile
        != HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3
        or bindings.required_architecture_base != "gfx1030"
        or bindings.required_slot_ids
        != HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_SLOT_IDS_V1
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_SLOT_IDS_V1
        or receipt.claims != HipFgmresHighLoadResultIRAggregateClaimsV1()
    ):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_semantics_invalid",
            "/",
        )
    hash_fields = (
        bindings.registry_bytes_sha256,
        bindings.registry_hash,
        bindings.registry_receipt_hash,
        receipt.attestation_id,
        receipt.receipt_hash,
    )
    if any(_HASH_RE.fullmatch(value) is None for value in hash_fields):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_hash_invalid",
            "/bindings",
        )
    seen_cases: set[str] = set()
    seen_receipts: set[str] = set()
    for index, (row, slot) in enumerate(
        zip(receipt.observations, registry.slots, strict=True)
    ):
        expected_hash = canonical_hash(
            _observation_payload(row, include_binding_hash=False)
        )
        row_hashes = tuple(
            getattr(row, name)
            for name in row.__dataclass_fields__
            if name.endswith("_hash") or name.endswith("_sha256")
        )
        ratios = (
            row.terminal_maximum_record_bound_ratio,
            row.exported_to_fsum_maximum_componentwise_bound_ratio,
            row.fsum_to_result_ir_plan_maximum_componentwise_bound_ratio,
        )
        if (
            row.case_id in seen_cases
            or row.result_ir_v3_receipt_hash in seen_receipts
            or row.slot_id != slot.slot_id
            or row.base_slot_id != slot.base_slot_id
            or row.slot_registration_hash != slot.slot_registration_hash
            or row.model_bytes_sha256 != slot.model_bytes_sha256
            or row.model_ir_content_hash != slot.model.content_hash
            or row.execution_plan_hash != slot.execution_plan.plan_hash
            or row.cpu_result_hash != slot.cpu_result.result_hash
            or row.load_component != slot.load_component
            or row.high_load_value_si != slot.high_load_value_si
            or row.load_scale_factor != slot.load_scale_factor
            or row.compiled_architecture != "gfx1030"
            or row.runtime_architecture_base != "gfx1030"
            or row.result_array_count != 6
            or row.result_array_byte_count
            != 24 * slot.execution_plan.dof_count
            + 104 * slot.execution_plan.element_count
            + 8 * len(slot.execution_plan.free_dofs)
            or row.detached_completion_payload_byte_count
            != 16 * len(slot.execution_plan.free_dofs)
            or row.additional_device_operation_count != 0
            or row.additional_d2h_operation_count != 0
            or row.additional_solve_count != 0
            or row.additional_export_count != 0
            or row.fallback_count != 0
            or row.aggregate_binding_hash != expected_hash
            or any(_HASH_RE.fullmatch(value) is None for value in row_hashes)
            or any(
                not math.isfinite(value) or value < 0.0 or value > 1.0
                for value in ratios
            )
        ):
            _fail(
                "hip_fgmres_high_load_result_ir_aggregate_observation_invalid",
                f"/observations/{index}",
            )
        seen_cases.add(row.case_id)
        seen_receipts.add(row.result_ir_v3_receipt_hash)
    if receipt.totals != _totals(registry, receipt.observations):
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_totals_invalid",
            "/totals",
        )
    expected_attestation = canonical_hash(
        {
            "capability_profile": receipt.capability_profile,
            "registry_receipt_hash": registry.receipt_hash,
            "aggregate_binding_hashes": [
                row.aggregate_binding_hash for row in receipt.observations
            ],
        }
    )
    if receipt.attestation_id != expected_attestation:
        _fail(
            "hip_fgmres_high_load_result_ir_aggregate_attestation_invalid",
            "/attestation_id",
        )


def _child_snapshot(child: HipFgmresResultIRResultV3) -> _ResultIRV3SnapshotV1:
    return _ResultIRV3SnapshotV1(
        result=child,
        receipt=child.receipt,
        base_result_ir_v2=child.base_result_ir_v2,
        accepted_state=child.accepted_state,
        evaluated_trial_state=child.evaluated_trial_state,
        committed_state=child.committed_state,
        terminal_metric_parity=child.terminal_metric_parity,
        fsum_to_plan_roundoff=child.fsum_to_result_ir_plan_roundoff,
        source_execution_plan=child.source_execution_plan,
        source_solution_x=child._source_solution_x,
        source_true_residual=child._source_true_residual,
        source_case_identity_token=child._source_case_identity_token,
        receipt_payload_hash=canonical_hash(child.receipt.to_dict()),
        base_result_ir_hash=child.base_result_ir_v2.result_ir_hash,
        accepted_state_hash=child.accepted_state.state_hash,
        evaluated_trial_state_hash=child.evaluated_trial_state.state_hash,
        committed_state_hash=child.committed_state.state_hash,
    )


def _validate_child_snapshot(
    child: HipFgmresResultIRResultV3,
    snapshot: _ResultIRV3SnapshotV1,
    *,
    path: str,
) -> None:
    if (
        type(snapshot) is not _ResultIRV3SnapshotV1
        or snapshot.result is not child
        or snapshot.receipt is not child.receipt
        or snapshot.base_result_ir_v2 is not child.base_result_ir_v2
        or snapshot.accepted_state is not child.accepted_state
        or snapshot.evaluated_trial_state is not child.evaluated_trial_state
        or snapshot.committed_state is not child.committed_state
        or snapshot.terminal_metric_parity is not child.terminal_metric_parity
        or snapshot.fsum_to_plan_roundoff is not child.fsum_to_result_ir_plan_roundoff
        or snapshot.source_execution_plan is not child.source_execution_plan
        or snapshot.source_solution_x is not child._source_solution_x
        or snapshot.source_true_residual is not child._source_true_residual
        or snapshot.source_case_identity_token is not child._source_case_identity_token
        or snapshot.receipt_payload_hash != canonical_hash(child.receipt.to_dict())
        or snapshot.base_result_ir_hash != child.base_result_ir_v2.result_ir_hash
        or snapshot.accepted_state_hash != child.accepted_state.state_hash
        or snapshot.evaluated_trial_state_hash != child.evaluated_trial_state.state_hash
        or snapshot.committed_state_hash != child.committed_state.state_hash
    ):
        _fail("hip_fgmres_high_load_result_ir_aggregate_child_changed", path)


def _observation_payload(
    row: HipFgmresHighLoadResultIRAggregateObservationV1,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = row.to_dict()
    if not include_binding_hash:
        payload.pop("aggregate_binding_hash")
    return payload


def _receipt_payload(
    receipt: HipFgmresHighLoadResultIRAggregateReceiptV1,
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
    raise HipFgmresHighLoadResultIRAggregateV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_HIGH_LOAD_RESULT_IR_AGGREGATE_STATUS_V1",
    "HipFgmresHighLoadResultIRAggregateBindingsV1",
    "HipFgmresHighLoadResultIRAggregateClaimsV1",
    "HipFgmresHighLoadResultIRAggregateObservationV1",
    "HipFgmresHighLoadResultIRAggregateReceiptV1",
    "HipFgmresHighLoadResultIRAggregateResultV1",
    "HipFgmresHighLoadResultIRAggregateTotalsV1",
    "HipFgmresHighLoadResultIRAggregateV1Error",
    "attest_hip_fgmres_high_load_result_ir_aggregate_v1",
    "validate_hip_fgmres_high_load_result_ir_aggregate_receipt_v1",
    "validate_hip_fgmres_high_load_result_ir_aggregate_result_v1",
]
