"""Package-owned original-scale FGMRES high-load compatibility registry.

The v0.2.47 all-converged registry intentionally keeps three cancellation-
sensitive models normalized to unit load.  This additive registry does not
rewrite that historical package.  It pins three deterministic original-scale
derivatives and proves, by full CPU/plan replay, that only the load and
provenance change while the sparse stiffness, symbolic partition, recovery
operator, policy, and convergence-cycle semantics remain compatible.

The registry is a package-local, unsigned, non-promoting CPU replay contract.
Actual HIP and ResultIR authority are composed separately from exact live v2
model-case results.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
import json
import math
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    compile_execution_plan_v2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceResultV1,
    FgmresPolicyV1,
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
    validate_cpu_fgmres_reference_result_v1,
)
from structural_analysis.model_ir import ModelIRDocument, parse_model_ir_v2

from .fgmres_all_converged_fixture_registry_v1 import (
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
    HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresAllConvergedFixtureRegistryResultV1,
    HipFgmresAllConvergedFixtureReplayV1,
    _derive_descriptor,
    _deterministic_dense_oracle,
    _expected_snapshot,
    _policy_parameters,
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from .fgmres_plan import HipFgmresPlanV1, compile_hip_fgmres_plan_v1
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    compile_hip_fgmres_recurrence_plan_v2,
)
from .free_space_plan import (
    HipFreeSpaceOperatorPlanV1,
    compile_hip_free_space_operator_plan_v1,
)


HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-high-load-compatibility-registry.v1"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1 = (
    "phase0_package_owned_original_scale_high_load_three_case_compatibility"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1 = (
    "EngineV2.HipFgmres.HighLoadCompatibility.gfx1030.v1"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_EVIDENCE_SCOPE_V1 = (
    "package_local_cpu_replay_linear_load_scaling_unsigned_nonpromoting"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1 = (
    "high_load_frame_single_rotated_axis_bending_10kn",
    "high_load_frame_serial_four_span_axial_100kn",
    "high_load_frame_serial_five_span_axial_100kn",
)

HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1 = (
    "sha256:e3414a08530703a9cc4405393157c9c88f6a721b2dbf5717e77c6a5dee7f31f1"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1 = (
    "sha256:85611ec01af14b375be09f91ee67e9eb2ee89734f110ff9899239465d5793a19"
)
HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1 = (
    "sha256:cfe3a37ab6d9db1adbe5d26a6b1a0549eae8591d0adc5a00fbc5865d07dc00ab"
)

_FIXTURE_PACKAGE = (
    "structural_analysis.engine_v2.assembly_backend.fixtures."
    "fgmres_high_load_compatibility_v1"
)
_REGISTRY_RESOURCE = "registry.v1.json"
_SCHEMA_RESOURCE = "hip_fgmres_high_load_compatibility_registry_v1.schema.json"
_REGISTRY_RESOURCE_BYTES_SHA256 = (
    "sha256:7411b02b72500b7448ed97dd3470d27e8fb129a7d98ee600b2ff06374a1b113d"
)
_SCHEMA_RESOURCE_BYTES_SHA256 = (
    "sha256:5883c16075f8ebabdc7e8a6dfdb2b300e3c89973cc14ea6e955bbd1d16f9ac75"
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_HASH = "sha256:" + "0" * 64
_UNCHANGED_PLAN_ARRAYS = (
    "node_dof_indices",
    "global_to_free",
    "element_global_dofs",
    "constrained_dofs",
    "free_dofs",
    "csr_row_ptr",
    "csr_column_indices",
    "csr_diagonal_positions",
    "csr_element_scatter_indices",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
    "global_stiffness_csr_values",
    "reduced_stiffness_csr_values",
    "recovery_transform_global_to_local",
    "recovery_stiffness_local",
)


@dataclass(frozen=True, slots=True)
class _HighLoadSpecV1:
    slot_id: str
    base_slot_id: str
    model_resource: str
    load_component: Literal["FX", "FY"]
    base_load_value_si: float
    high_load_value_si: float
    load_scale_factor: float
    description: str

    @property
    def source_ref(self) -> str:
        return (
            "actual-gfx1030:fp64-csr-roundoff:"
            f"{self.base_slot_id}:{float.hex(self.high_load_value_si)}"
        )


_SPECS = (
    _HighLoadSpecV1(
        slot_id=HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1[0],
        base_slot_id="solution_frame_single_rotated_axis_bending",
        model_resource="high_load_frame_single_rotated_axis_bending_10kn.model.json",
        load_component="FY",
        base_load_value_si=-1.0,
        high_load_value_si=-10000.0,
        load_scale_factor=10000.0,
        description="rotated-axis frame bending at original -10 kN load",
    ),
    _HighLoadSpecV1(
        slot_id=HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1[1],
        base_slot_id="solution_frame_serial_four_span_axial",
        model_resource="high_load_frame_serial_four_span_axial_100kn.model.json",
        load_component="FX",
        base_load_value_si=1.0,
        high_load_value_si=100000.0,
        load_scale_factor=100000.0,
        description="four-span serial frame axial response at original 100 kN load",
    ),
    _HighLoadSpecV1(
        slot_id=HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1[2],
        base_slot_id="solution_frame_serial_five_span_axial",
        model_resource="high_load_frame_serial_five_span_axial_100kn.model.json",
        load_component="FX",
        base_load_value_si=1.0,
        high_load_value_si=100000.0,
        load_scale_factor=100000.0,
        description="five-span serial frame axial response at original 100 kN load",
    ),
)


class HipFgmresHighLoadCompatibilityRegistryV1Error(RuntimeError):
    """Stable fail-closed package registry error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = " ".join(str(message or code).split())[:512]
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadCompatibilitySnapshotV1:
    load_only_model_derivative_verified: Literal[True]
    exact_global_load_scaling_verified: Literal[True]
    unchanged_sparse_plan_array_count: Literal[16]
    unchanged_sparse_plan_arrays_byte_equal: Literal[True]
    symbolic_reuse_hash_equal: Literal[True]
    partition_hash_equal: Literal[True]
    ordering_hash_equal: Literal[True]
    recovery_operator_hash_equal: Literal[True]
    policy_hash_equal: Literal[True]
    cpu_history_cycles_equal: Literal[True]
    direct_solution_linear_scaling_verified: Literal[True]
    cpu_solution_linear_scaling_verified: Literal[True]
    maximum_direct_solution_scaling_absolute_error: float
    maximum_cpu_solution_scaling_absolute_error: float

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadCompatibilityReplayV1:
    slot_id: str
    base_slot_id: str
    model_resource: str
    model_bytes_sha256: str
    slot_registration_hash: str
    base_slot_registration_hash: str
    base_model_bytes_sha256: str
    base_case_fingerprint: str
    load_component: str
    base_load_value_si: float
    high_load_value_si: float
    load_scale_factor: float
    source_ref: str
    expected: dict[str, Any]
    compatibility: HipFgmresHighLoadCompatibilitySnapshotV1
    base_slot: HipFgmresAllConvergedFixtureReplayV1 = field(
        repr=False,
        compare=False,
    )
    model: ModelIRDocument = field(repr=False, compare=False)
    execution_plan: ExecutionPlanV2 = field(repr=False, compare=False)
    policy: FgmresPolicyV1 = field(repr=False, compare=False)
    cpu_result: CpuFgmresReferenceResultV1 = field(repr=False, compare=False)
    free_space_plan: HipFreeSpaceOperatorPlanV1 = field(repr=False, compare=False)
    fgmres_plan: HipFgmresPlanV1 = field(repr=False, compare=False)
    recurrence_plan: HipFgmresRecurrencePlanV2 = field(repr=False, compare=False)
    direct_solution: np.ndarray = field(repr=False, compare=False)
    direct_residual: np.ndarray = field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "base_slot_id": self.base_slot_id,
            "model_resource": self.model_resource,
            "model_bytes_sha256": self.model_bytes_sha256,
            "slot_registration_hash": self.slot_registration_hash,
            "base_slot_registration_hash": self.base_slot_registration_hash,
            "base_model_bytes_sha256": self.base_model_bytes_sha256,
            "base_case_fingerprint": self.base_case_fingerprint,
            "load_component": self.load_component,
            "base_load_value_si": self.base_load_value_si,
            "high_load_value_si": self.high_load_value_si,
            "load_scale_factor": self.load_scale_factor,
            "source_ref": self.source_ref,
            "model_ir_content_hash": self.model.content_hash,
            "execution_plan_hash": self.execution_plan.plan_hash,
            "cpu_result_hash": self.cpu_result.result_hash,
            "expected": copy.deepcopy(self.expected),
            "compatibility": self.compatibility.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresHighLoadCompatibilityRegistryResultV1:
    registry_bytes_sha256: str
    registry_hash: str
    parent_registry_bytes_sha256: str
    parent_registry_hash: str
    parent_schema_bytes_sha256: str
    slots: tuple[HipFgmresHighLoadCompatibilityReplayV1, ...]
    receipt_hash: str

    def slot(self, slot_id: str) -> HipFgmresHighLoadCompatibilityReplayV1:
        matches = tuple(row for row in self.slots if row.slot_id == slot_id)
        if len(matches) != 1:
            raise KeyError(slot_id)
        return matches[0]

    def to_manifest(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)


class _WeakReferenceableRegistryTransactionV1:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HighLoadRegistryTransactionV1(_WeakReferenceableRegistryTransactionV1):
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1
    registry_snapshot_hash: str
    resource_bindings: tuple[tuple[str, str], ...]
    mint: object


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HighLoadRegistryTransactionIssuanceV1:
    transaction_ref: weakref.ReferenceType[_HighLoadRegistryTransactionV1]
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1
    registry_snapshot_hash: str
    resource_bindings: tuple[tuple[str, str], ...]
    mint: object


_TRANSACTION_LOCK = threading.RLock()
_TRANSACTION_ISSUANCES: weakref.WeakKeyDictionary[
    _HighLoadRegistryTransactionV1,
    _HighLoadRegistryTransactionIssuanceV1,
] = weakref.WeakKeyDictionary()


def load_hip_fgmres_high_load_compatibility_registry_v1() -> (
    HipFgmresHighLoadCompatibilityRegistryResultV1
):
    """Replay the exact package registry; caller paths and overrides are absent."""

    return _replay_package_registry()


def validate_hip_fgmres_high_load_compatibility_registry_result_v1(
    result: HipFgmresHighLoadCompatibilityRegistryResultV1,
) -> HipFgmresHighLoadCompatibilityRegistryResultV1:
    """Replay all fixed package inputs and compare the complete value receipt."""

    if type(result) is not HipFgmresHighLoadCompatibilityRegistryResultV1:
        _fail("hip_fgmres_high_load_registry_result_type_invalid", "/")
    fresh = _replay_package_registry()
    if fresh.to_manifest() != result.to_manifest():
        _fail("hip_fgmres_high_load_registry_result_replay_mismatch", "/")
    return result


def _issue_high_load_registry_transaction_v1(
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
) -> _HighLoadRegistryTransactionV1:
    if type(registry) is not HipFgmresHighLoadCompatibilityRegistryResultV1:
        _fail("hip_fgmres_high_load_registry_transaction_type_invalid", "/")
    bindings = _resource_bindings(registry)
    snapshot = _registry_snapshot_hash(registry)
    transaction = _HighLoadRegistryTransactionV1(
        registry=registry,
        registry_snapshot_hash=snapshot,
        resource_bindings=bindings,
        mint=object(),
    )
    issuance = _HighLoadRegistryTransactionIssuanceV1(
        transaction_ref=weakref.ref(transaction),
        registry=registry,
        registry_snapshot_hash=snapshot,
        resource_bindings=bindings,
        mint=transaction.mint,
    )
    with _TRANSACTION_LOCK:
        _TRANSACTION_ISSUANCES[transaction] = issuance
    return transaction


def _registry_from_high_load_transaction_v1(
    transaction: _HighLoadRegistryTransactionV1,
) -> HipFgmresHighLoadCompatibilityRegistryResultV1:
    if type(transaction) is not _HighLoadRegistryTransactionV1:
        _fail("hip_fgmres_high_load_registry_transaction_type_invalid", "/")
    with _TRANSACTION_LOCK:
        issuance = _TRANSACTION_ISSUANCES.get(transaction)
    if type(issuance) is not _HighLoadRegistryTransactionIssuanceV1:
        _fail(
            "hip_fgmres_high_load_registry_transaction_issuance_unavailable",
            "/issuance",
        )
    if (
        issuance.transaction_ref() is not transaction
        or issuance.registry is not transaction.registry
        or issuance.registry_snapshot_hash != transaction.registry_snapshot_hash
        or issuance.resource_bindings != transaction.resource_bindings
        or issuance.mint is not transaction.mint
        or _registry_snapshot_hash(transaction.registry)
        != transaction.registry_snapshot_hash
    ):
        _fail(
            "hip_fgmres_high_load_registry_transaction_binding_mismatch",
            "/issuance",
        )
    return issuance.registry


def _refresh_high_load_registry_transaction_v1(
    transaction: _HighLoadRegistryTransactionV1,
) -> HipFgmresHighLoadCompatibilityRegistryResultV1:
    registry = _registry_from_high_load_transaction_v1(transaction)
    if _resource_bindings(registry, refresh=True) != transaction.resource_bindings:
        _fail(
            "hip_fgmres_high_load_registry_transaction_resource_changed",
            "/resources",
        )
    return registry


def _replay_package_registry() -> HipFgmresHighLoadCompatibilityRegistryResultV1:
    raw = _read_fixed_resource(_REGISTRY_RESOURCE)
    if sha256_prefixed(raw) != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail("hip_fgmres_high_load_registry_resource_hash_mismatch", "/")
    payload = _parse_strict_object(raw, path="/")
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda row: tuple(str(part) for part in row.absolute_path),
    )
    if errors:
        first = errors[0]
        _fail(
            "hip_fgmres_high_load_registry_schema_validation_failed",
            "/" + "/".join(str(part) for part in first.absolute_path),
            first.message,
        )
    _validate_registry_header(payload)
    parent = load_hip_fgmres_all_converged_fixture_registry_v1()
    _validate_parent(parent, payload)
    slots = tuple(
        _replay_slot(row, spec, parent, index=index)
        for index, (row, spec) in enumerate(zip(payload["slots"], _SPECS, strict=True))
    )
    if (
        tuple(row.slot_id for row in slots)
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
        or len({row.model_bytes_sha256 for row in slots}) != 3
        or len({row.model.content_hash for row in slots}) != 3
        or len({row.execution_plan.plan_hash for row in slots}) != 3
        or len({row.cpu_result.result_hash for row in slots}) != 3
        or len({row.slot_registration_hash for row in slots}) != 3
    ):
        _fail("hip_fgmres_high_load_registry_uniqueness_invalid", "/slots")
    registry_hash = _manifest_hash(payload)
    if payload["registry_hash"] != registry_hash:
        _fail("hip_fgmres_high_load_registry_hash_invalid", "/registry_hash")
    draft = HipFgmresHighLoadCompatibilityRegistryResultV1(
        registry_bytes_sha256=sha256_prefixed(raw),
        registry_hash=registry_hash,
        parent_registry_bytes_sha256=parent.registry_bytes_sha256,
        parent_registry_hash=parent.registry_hash,
        parent_schema_bytes_sha256=(
            HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1
        ),
        slots=slots,
        receipt_hash=_ZERO_HASH,
    )
    return HipFgmresHighLoadCompatibilityRegistryResultV1(
        **{
            **{
                name: getattr(draft, name)
                for name in draft.__dataclass_fields__
                if name != "receipt_hash"
            },
            "receipt_hash": canonical_hash(_result_payload(draft, include_hash=False)),
        }
    )


def _replay_slot(
    row: dict[str, Any],
    spec: _HighLoadSpecV1,
    parent: HipFgmresAllConvergedFixtureRegistryResultV1,
    *,
    index: int,
) -> HipFgmresHighLoadCompatibilityReplayV1:
    path = f"/slots/{index}"
    if (
        row["slot_id"] != spec.slot_id
        or row["base_slot_id"] != spec.base_slot_id
        or row["model_resource"] != spec.model_resource
        or row["description"] != spec.description
        or row["load_component"] != spec.load_component
        or row["base_load_value_si"] != spec.base_load_value_si
        or row["high_load_value_si"] != spec.high_load_value_si
        or row["load_scale_factor"] != spec.load_scale_factor
        or row["source_ref"] != spec.source_ref
    ):
        _fail("hip_fgmres_high_load_registry_slot_metadata_invalid", path)
    registration = dict(row)
    declared_registration = registration.pop("slot_registration_hash")
    if declared_registration != canonical_hash(registration):
        _fail(
            "hip_fgmres_high_load_registry_slot_registration_hash_invalid",
            f"{path}/slot_registration_hash",
        )
    try:
        base = parent.slot(spec.base_slot_id)
    except KeyError:
        _fail("hip_fgmres_high_load_registry_parent_slot_missing", path)
    if (
        row["base_slot_registration_hash"] != base.slot_registration_hash
        or row["base_model_bytes_sha256"] != base.model_bytes_sha256
        or row["base_case_fingerprint"] != base.case_fingerprint
        or row["base_model_ir_content_hash"] != base.model.content_hash
        or row["base_execution_plan_hash"] != base.execution_plan.plan_hash
    ):
        _fail("hip_fgmres_high_load_registry_parent_binding_invalid", path)
    raw = _read_fixed_resource(spec.model_resource)
    if sha256_prefixed(raw) != row["model_bytes_sha256"]:
        _fail(
            "hip_fgmres_high_load_registry_model_bytes_hash_mismatch",
            f"{path}/model_bytes_sha256",
        )
    payload = _parse_strict_object(raw, path=f"{path}/model")
    expected_payload = _derived_high_load_payload(base, spec)
    if payload != expected_payload:
        _fail("hip_fgmres_high_load_registry_model_derivative_invalid", f"{path}/model")
    material = _compile_high_load_material(base, spec, payload)
    expected = _expected_snapshot(
        model=material[0],
        execution=material[1],
        descriptor=_derive_descriptor(material[1]),
        policy=material[2],
        cpu=material[3],
        free_space=material[4],
        fgmres=material[5],
        recurrence=material[6],
        direct_solution=material[7],
        direct_residual=material[8],
    )
    compatibility = _compatibility_snapshot(
        base,
        material[1],
        material[2],
        material[3],
        material[7],
        spec,
    )
    if row["expected"] != expected or row["compatibility"] != compatibility.to_dict():
        _fail("hip_fgmres_high_load_registry_expected_replay_mismatch", path)
    return HipFgmresHighLoadCompatibilityReplayV1(
        slot_id=spec.slot_id,
        base_slot_id=spec.base_slot_id,
        model_resource=spec.model_resource,
        model_bytes_sha256=row["model_bytes_sha256"],
        slot_registration_hash=declared_registration,
        base_slot_registration_hash=base.slot_registration_hash,
        base_model_bytes_sha256=base.model_bytes_sha256,
        base_case_fingerprint=base.case_fingerprint,
        load_component=spec.load_component,
        base_load_value_si=spec.base_load_value_si,
        high_load_value_si=spec.high_load_value_si,
        load_scale_factor=spec.load_scale_factor,
        source_ref=spec.source_ref,
        expected=copy.deepcopy(expected),
        compatibility=compatibility,
        base_slot=base,
        model=material[0],
        execution_plan=material[1],
        policy=material[2],
        cpu_result=material[3],
        free_space_plan=material[4],
        fgmres_plan=material[5],
        recurrence_plan=material[6],
        direct_solution=material[7],
        direct_residual=material[8],
    )


def _derived_high_load_payload(
    base: HipFgmresAllConvergedFixtureReplayV1,
    spec: _HighLoadSpecV1,
) -> dict[str, Any]:
    payload = copy.deepcopy(base.model.to_dict())
    components = payload["load_patterns"][0]["nodal_loads"][0]["components_si"]
    if components[spec.load_component] != spec.base_load_value_si:
        _fail(
            "hip_fgmres_high_load_registry_parent_load_invalid",
            f"/parent/{spec.base_slot_id}/load",
        )
    components[spec.load_component] = spec.high_load_value_si
    payload["provenance"]["source_ref"] = spec.source_ref
    payload["provenance"]["source_sha256"] = sha256_prefixed(
        spec.source_ref.encode("utf-8")
    )
    return payload


def _compile_high_load_material(
    base: HipFgmresAllConvergedFixtureReplayV1,
    spec: _HighLoadSpecV1,
    payload: dict[str, Any],
) -> tuple[
    ModelIRDocument,
    ExecutionPlanV2,
    FgmresPolicyV1,
    CpuFgmresReferenceResultV1,
    HipFreeSpaceOperatorPlanV1,
    HipFgmresPlanV1,
    HipFgmresRecurrencePlanV2,
    np.ndarray,
    np.ndarray,
]:
    model = parse_model_ir_v2(payload, require_analysis_ready=True)
    plan = compile_execution_plan_v2(
        pack_solver_model_buffers(
            model, load_pattern_id=base.execution_plan.load_pattern_id
        ),
        residual_tolerance=base.execution_plan.residual_tolerance,
    )
    parameters = _policy_parameters(spec.base_slot_id)
    policy = compile_fgmres_policy_v1(**parameters)
    cpu = solve_cpu_fgmres_reference_v1(plan, policy)
    free_space = compile_hip_free_space_operator_plan_v1(plan)
    fgmres = compile_hip_fgmres_plan_v1(plan, free_space, policy)
    recurrence = compile_hip_fgmres_recurrence_plan_v2(fgmres)
    direct_solution, direct_residual = _deterministic_dense_oracle(plan)
    validate_execution_plan_v2(plan)
    validate_cpu_fgmres_reference_result_v1(
        cpu,
        expected_plan=plan,
        expected_policy=policy,
    )
    if (
        cpu.status != "converged"
        or not cpu.solver_tolerance_passed
        or not cpu.authoritative_plan_tolerance_passed
        or len(cpu.history) != 1
        or not np.allclose(
            cpu.reduced_solution,
            direct_solution,
            rtol=1.0e-10,
            atol=1.0e-12,
        )
    ):
        _fail(
            "hip_fgmres_high_load_registry_cpu_replay_invalid",
            f"/slots/{spec.slot_id}/cpu",
        )
    return (
        model,
        plan,
        policy,
        cpu,
        free_space,
        fgmres,
        recurrence,
        direct_solution,
        direct_residual,
    )


def _compatibility_snapshot(
    base: HipFgmresAllConvergedFixtureReplayV1,
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    cpu: CpuFgmresReferenceResultV1,
    direct_solution: np.ndarray,
    spec: _HighLoadSpecV1,
) -> HipFgmresHighLoadCompatibilitySnapshotV1:
    if any(
        not np.array_equal(plan.array(name), base.execution_plan.array(name))
        for name in _UNCHANGED_PLAN_ARRAYS
    ):
        _fail(
            "hip_fgmres_high_load_registry_sparse_operator_changed",
            f"/slots/{spec.slot_id}/compatibility",
        )
    scaled_load = base.execution_plan.array("global_load") * spec.load_scale_factor
    if not np.array_equal(plan.array("global_load"), scaled_load):
        _fail(
            "hip_fgmres_high_load_registry_load_scaling_invalid",
            f"/slots/{spec.slot_id}/compatibility/global_load",
        )
    direct_expected = base.direct_solution * spec.load_scale_factor
    cpu_expected = base.cpu_result.reduced_solution * spec.load_scale_factor
    direct_error = float(np.max(np.abs(direct_solution - direct_expected), initial=0.0))
    cpu_error = float(np.max(np.abs(cpu.reduced_solution - cpu_expected), initial=0.0))
    if not np.allclose(
        direct_solution, direct_expected, rtol=1.0e-12, atol=1.0e-12
    ) or not np.allclose(
        cpu.reduced_solution,
        cpu_expected,
        rtol=1.0e-12,
        atol=1.0e-12,
    ):
        _fail(
            "hip_fgmres_high_load_registry_solution_scaling_invalid",
            f"/slots/{spec.slot_id}/compatibility/solution",
        )
    base_cycles = tuple(
        (row.start_iteration, row.end_iteration, row.arnoldi_step_count)
        for row in base.cpu_result.history
    )
    high_cycles = tuple(
        (row.start_iteration, row.end_iteration, row.arnoldi_step_count)
        for row in cpu.history
    )
    if base_cycles != high_cycles:
        _fail(
            "hip_fgmres_high_load_registry_history_compatibility_invalid",
            f"/slots/{spec.slot_id}/compatibility/history",
        )
    if (
        plan.symbolic_reuse_hash != base.execution_plan.symbolic_reuse_hash
        or plan.partition_hash != base.execution_plan.partition_hash
        or plan.ordering_hash != base.execution_plan.ordering_hash
        or plan.recovery_operator_hash != base.execution_plan.recovery_operator_hash
        or policy.policy_hash != base.policy.policy_hash
    ):
        _fail(
            "hip_fgmres_high_load_registry_hash_compatibility_invalid",
            f"/slots/{spec.slot_id}/compatibility/hashes",
        )
    return HipFgmresHighLoadCompatibilitySnapshotV1(
        load_only_model_derivative_verified=True,
        exact_global_load_scaling_verified=True,
        unchanged_sparse_plan_array_count=len(_UNCHANGED_PLAN_ARRAYS),
        unchanged_sparse_plan_arrays_byte_equal=True,
        symbolic_reuse_hash_equal=True,
        partition_hash_equal=True,
        ordering_hash_equal=True,
        recovery_operator_hash_equal=True,
        policy_hash_equal=True,
        cpu_history_cycles_equal=True,
        direct_solution_linear_scaling_verified=True,
        cpu_solution_linear_scaling_verified=True,
        maximum_direct_solution_scaling_absolute_error=direct_error,
        maximum_cpu_solution_scaling_absolute_error=cpu_error,
    )


def _validate_registry_header(payload: dict[str, Any]) -> None:
    claims = payload["claims"]
    if (
        payload["schema_version"]
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1
        or payload["capability_profile"]
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1
        or payload["fixture_suite_id"]
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1
        or payload["evidence_scope"]
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_EVIDENCE_SCOPE_V1
        or tuple(payload["required_slot_ids"])
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
        or payload["registered_slot_count"] != 3
        or claims != _registry_claims()
    ):
        _fail("hip_fgmres_high_load_registry_header_invalid", "/")


def _validate_parent(
    parent: HipFgmresAllConvergedFixtureRegistryResultV1,
    payload: dict[str, Any],
) -> None:
    binding = payload["parent_registry"]
    if (
        type(parent) is not HipFgmresAllConvergedFixtureRegistryResultV1
        or parent.registry_bytes_sha256
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1
        or parent.registry_hash
        != HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1
        or binding
        != {
            "schema_version": HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
            "capability_profile": HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1,
            "fixture_suite_id": HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
            "registry_bytes_sha256": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1,
            "registry_hash": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1,
            "schema_bytes_sha256": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1,
            "source_registry_mutated": False,
        }
    ):
        _fail("hip_fgmres_high_load_registry_parent_invalid", "/parent_registry")


def _registry_claims() -> dict[str, bool]:
    return {
        "package_high_load_registry_replayed": True,
        "historical_unit_load_registry_bytes_preserved": True,
        "exact_three_original_scale_derivatives_verified": True,
        "sparse_operator_compatibility_verified": True,
        "linear_load_solution_scaling_verified": True,
        "all_cpu_reference_converged": True,
        "actual_hip_execution_verified": False,
        "result_ir_v3_aggregate_verified": False,
        "general_restart_history_v2_verified": False,
        "external_gfx1100_verified": False,
        "signed_evidence": False,
        "promotion_eligible": False,
        "commercial_ready": False,
    }


def _result_payload(
    result: HipFgmresHighLoadCompatibilityRegistryResultV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1,
        "fixture_suite_id": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1,
        "evidence_scope": HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_EVIDENCE_SCOPE_V1,
        "registry_bytes_sha256": result.registry_bytes_sha256,
        "registry_hash": result.registry_hash,
        "parent_registry_bytes_sha256": result.parent_registry_bytes_sha256,
        "parent_registry_hash": result.parent_registry_hash,
        "parent_schema_bytes_sha256": result.parent_schema_bytes_sha256,
        "registered_slot_count": len(result.slots),
        "required_slot_ids": [row.slot_id for row in result.slots],
        "package_global_dof_count": sum(
            row.execution_plan.dof_count for row in result.slots
        ),
        "package_element_count": sum(
            row.execution_plan.element_count for row in result.slots
        ),
        "package_free_dof_count": sum(
            len(row.execution_plan.free_dofs) for row in result.slots
        ),
        "package_csr_nnz": sum(row.execution_plan.nnz for row in result.slots),
        "claims": _registry_claims(),
        "slots": [row.to_manifest() for row in result.slots],
    }
    if include_hash:
        payload["receipt_hash"] = result.receipt_hash
    return payload


def _registry_snapshot_hash(
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
) -> str:
    return canonical_hash(_result_payload(registry, include_hash=True))


def _resource_bindings(
    registry: HipFgmresHighLoadCompatibilityRegistryResultV1,
    *,
    refresh: bool = False,
) -> tuple[tuple[str, str], ...]:
    if refresh:
        raw_registry = _read_fixed_resource(_REGISTRY_RESOURCE)
        raw_schema = (
            resources.files("structural_analysis.schemas")
            .joinpath(_SCHEMA_RESOURCE)
            .read_bytes()
        )
        actual = (
            (_REGISTRY_RESOURCE, sha256_prefixed(raw_registry)),
            (_SCHEMA_RESOURCE, sha256_prefixed(raw_schema)),
            *(
                (
                    row.model_resource,
                    sha256_prefixed(_read_fixed_resource(row.model_resource)),
                )
                for row in registry.slots
            ),
        )
    else:
        actual = (
            (_REGISTRY_RESOURCE, registry.registry_bytes_sha256),
            (_SCHEMA_RESOURCE, _SCHEMA_RESOURCE_BYTES_SHA256),
            *((row.model_resource, row.model_bytes_sha256) for row in registry.slots),
        )
    return tuple(actual)


def _manifest_hash(payload: dict[str, Any]) -> str:
    candidate = copy.deepcopy(payload)
    candidate.pop("registry_hash", None)
    return canonical_hash(candidate)


def _read_fixed_resource(name: str) -> bytes:
    return resources.files(_FIXTURE_PACKAGE).joinpath(name).read_bytes()


def _parse_strict_object(raw: bytes, *, path: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_high_load_registry_json_bom_forbidden", path)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail("hip_fgmres_high_load_registry_json_utf8_invalid", path, str(exc))

    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite constant: {token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        code = (
            "hip_fgmres_high_load_registry_json_duplicate_key"
            if "duplicate key" in str(exc)
            else "hip_fgmres_high_load_registry_json_invalid"
        )
        _fail(code, path, str(exc))
    if type(value) is not dict or not _all_finite_json(value):
        _fail("hip_fgmres_high_load_registry_json_object_invalid", path)
    return value


def _all_finite_json(value: Any) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    if type(value) in (str, int, bool) or value is None:
        return True
    if type(value) is list:
        return all(_all_finite_json(row) for row in value)
    if type(value) is dict:
        return all(
            type(key) is str and _all_finite_json(row) for key, row in value.items()
        )
    return False


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    if sha256_prefixed(raw) != _SCHEMA_RESOURCE_BYTES_SHA256:
        _fail("hip_fgmres_high_load_registry_schema_hash_mismatch", "/schema")
    schema = _parse_strict_object(raw, path="/schema")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresHighLoadCompatibilityRegistryV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1",
    "HipFgmresHighLoadCompatibilityRegistryResultV1",
    "HipFgmresHighLoadCompatibilityRegistryV1Error",
    "HipFgmresHighLoadCompatibilityReplayV1",
    "HipFgmresHighLoadCompatibilitySnapshotV1",
    "load_hip_fgmres_high_load_compatibility_registry_v1",
    "validate_hip_fgmres_high_load_compatibility_registry_result_v1",
]
