"""Fail-closed package replay for the all-converged FGMRES fixture suite.

This registry is intentionally separate from the termination-semantics
registry.  It owns ten unique ModelIR resources and realistic solver
tolerances, but remains an unsigned, non-promoting CPU reference authority.
It does not prove a HIP execution, ResultIR issuance, multi-architecture
parity, performance, or commercial readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import threading
from typing import Any, NoReturn
import weakref

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
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
    validate_fgmres_policy_v1,
)
from structural_analysis.model_ir import ModelIRDocument, parse_model_ir_v2

from . import fgmres_fixture_registry_v1 as _termination_registry
from .fgmres_fixture_registry_v1 import HipFgmresFixtureRegistryV1Error
from .fgmres_model_family_parity_v1 import (
    HipFgmresModelFamilyCaseDescriptorV1,
    _derive_descriptor,
)
from .fgmres_plan import (
    HipFgmresPlanV1,
    compile_hip_fgmres_plan_v1,
    validate_hip_fgmres_plan_v1,
)
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    compile_hip_fgmres_recurrence_plan_v2,
    validate_hip_fgmres_recurrence_plan_v2,
)
from .free_space_plan import (
    HipFreeSpaceOperatorPlanV1,
    compile_hip_free_space_operator_plan_v1,
    validate_hip_free_space_operator_plan_v1,
)


HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-all-converged-fixture-registry.v1"
)
HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1 = (
    "phase0_package_owned_fgmres_all_converged_fixed_suite_replay"
)
HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1 = (
    "phase0_execution_plan_v2_linear_frame_truss_fgmres_all_converged_suite.v1"
)
HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1 = (
    "package_local_unsigned_non_promoting"
)
HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1 = (
    "solution_frame_single_axial",
    "solution_frame_single_weak_axis_bending",
    "solution_frame_single_strong_axis_bending",
    "solution_frame_single_torsion",
    "solution_frame_single_rotated_axis_bending",
    "solution_frame_serial_two_span_axial",
    "solution_truss_single_axial",
    "solution_frame_zero_free_rhs_edge",
    "solution_frame_serial_four_span_axial",
    "solution_frame_serial_five_span_axial",
)

_SUITE_SCOPE = (
    "execution_plan_v2_linear_frame_truss_zero_offset_release_prescribed_"
    "fgmres_all_converged_cases_only"
)
_RESOURCE_PACKAGE = (
    "structural_analysis.engine_v2.assembly_backend.fixtures.fgmres_all_converged_v1"
)
_REGISTRY_RESOURCE = "registry.v1.json"
_REGISTRY_RESOURCE_BYTES_SHA256 = (
    "sha256:e3414a08530703a9cc4405393157c9c88f6a721b2dbf5717e77c6a5dee7f31f1"
)
_SCHEMA_RESOURCE = "hip_fgmres_all_converged_fixture_registry_v1.schema.json"
_COMPONENT_INDEX = {
    name: index for index, name in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ"))
}


class HipFgmresAllConvergedFixtureRegistryV1Error(RuntimeError):
    """Stable fail-closed all-converged fixture-registry error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class _SemanticRuleV1:
    model_kind: str
    node_count: int
    element_count: int
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    load_component: str
    load_value_si: float
    load_node_id: str
    nonzero_local_axis_roll_count: int
    zero_reduced_rhs: bool
    history_cycles: tuple[tuple[int, int, int], ...]
    analytic_free_solution_nonzero: tuple[tuple[int, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_kind": self.model_kind,
            "node_count": self.node_count,
            "element_count": self.element_count,
            "global_dof_count": self.global_dof_count,
            "free_dof_count": self.free_dof_count,
            "reduced_csr_nnz": self.reduced_csr_nnz,
            "load_component": self.load_component,
            "load_value_si": self.load_value_si,
            "load_node_id": self.load_node_id,
            "nonzero_local_axis_roll_count": self.nonzero_local_axis_roll_count,
            "zero_reduced_rhs": self.zero_reduced_rhs,
            "history_cycles": [list(row) for row in self.history_cycles],
            "analytic_free_solution_nonzero": [
                [index, value] for index, value in self.analytic_free_solution_nonzero
            ],
        }


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedFixtureReplayV1:
    slot_id: str
    group: str
    description: str
    model_resource: str
    model_bytes_sha256: str
    semantic_profile: str
    case_fingerprint: str
    slot_registration_hash: str
    descriptor: HipFgmresModelFamilyCaseDescriptorV1
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
            "group": self.group,
            "description": self.description,
            "model_resource": self.model_resource,
            "model_bytes_sha256": self.model_bytes_sha256,
            "semantic_profile": self.semantic_profile,
            "model_ir_content_hash": self.model.content_hash,
            "execution_plan_hash": self.execution_plan.plan_hash,
            "descriptor_hash": self.descriptor.descriptor_hash,
            "policy_hash": self.policy.policy_hash,
            "cpu_result_hash": self.cpu_result.result_hash,
            "cpu_status": self.cpu_result.status,
            "cpu_termination_code": self.cpu_result.termination_code,
            "solver_tolerance_passed": self.cpu_result.solver_tolerance_passed,
            "authoritative_plan_tolerance_passed": (
                self.cpu_result.authoritative_plan_tolerance_passed
            ),
            "cpu_history_hash": canonical_hash(
                [row.to_dict() for row in self.cpu_result.history]
            ),
            "direct_solution_data_hash": array_data_hash(self.direct_solution),
            "direct_residual_data_hash": array_data_hash(self.direct_residual),
            "case_fingerprint": self.case_fingerprint,
            "slot_registration_hash": self.slot_registration_hash,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresAllConvergedFixtureRegistryResultV1:
    registry_bytes_sha256: str
    registry_hash: str
    slots: tuple[HipFgmresAllConvergedFixtureReplayV1, ...]
    receipt_hash: str

    def slot(self, slot_id: str) -> HipFgmresAllConvergedFixtureReplayV1:
        matches = tuple(row for row in self.slots if row.slot_id == slot_id)
        if len(matches) != 1:
            raise KeyError(slot_id)
        return matches[0]

    def to_manifest(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)


class _WeakReferenceableFixedRegistryReplayTransactionV1:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FixedRegistryReplayTransactionV1(
    _WeakReferenceableFixedRegistryReplayTransactionV1
):
    registry: HipFgmresAllConvergedFixtureRegistryResultV1
    registry_snapshot_hash: str
    resource_bindings: tuple[tuple[str, str], ...]
    mint: object


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _FixedRegistryReplayTransactionIssuanceV1:
    transaction_ref: weakref.ReferenceType[_FixedRegistryReplayTransactionV1]
    registry: HipFgmresAllConvergedFixtureRegistryResultV1
    registry_snapshot_hash: str
    resource_bindings: tuple[tuple[str, str], ...]
    mint: object


_TRANSACTION_LOCK = threading.RLock()
_TRANSACTION_ISSUANCES: weakref.WeakKeyDictionary[
    _FixedRegistryReplayTransactionV1,
    _FixedRegistryReplayTransactionIssuanceV1,
] = weakref.WeakKeyDictionary()


def load_hip_fgmres_all_converged_fixture_registry_v1() -> (
    HipFgmresAllConvergedFixtureRegistryResultV1
):
    """Read and replay the exact package registry; no override is accepted."""

    return _replay_package_registry()


def _issue_fixed_registry_replay_transaction_v1(
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> _FixedRegistryReplayTransactionV1:
    """Retain one exact full replay for private same-call composition."""

    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_registry_transaction_type_invalid", "/")
    snapshot_hash = _fixed_registry_authority_snapshot_hash_v1(registry)
    resource_bindings = (
        (_REGISTRY_RESOURCE, _REGISTRY_RESOURCE_BYTES_SHA256),
        *((slot.model_resource, slot.model_bytes_sha256) for slot in registry.slots),
    )
    transaction = _FixedRegistryReplayTransactionV1(
        registry=registry,
        registry_snapshot_hash=snapshot_hash,
        resource_bindings=resource_bindings,
        mint=object(),
    )
    issuance = _FixedRegistryReplayTransactionIssuanceV1(
        transaction_ref=weakref.ref(transaction),
        registry=registry,
        registry_snapshot_hash=snapshot_hash,
        resource_bindings=resource_bindings,
        mint=transaction.mint,
    )
    with _TRANSACTION_LOCK:
        _TRANSACTION_ISSUANCES[transaction] = issuance
    return transaction


def _registry_from_fixed_replay_transaction_v1(
    transaction: _FixedRegistryReplayTransactionV1,
) -> HipFgmresAllConvergedFixtureRegistryResultV1:
    """Require an exact issued transaction and unchanged retained authority."""

    if type(transaction) is not _FixedRegistryReplayTransactionV1:
        _fail("hip_fgmres_all_converged_registry_transaction_type_invalid", "/")
    with _TRANSACTION_LOCK:
        issuance = _TRANSACTION_ISSUANCES.get(transaction)
    if type(issuance) is not _FixedRegistryReplayTransactionIssuanceV1:
        _fail(
            "hip_fgmres_all_converged_registry_transaction_issuance_unavailable",
            "/issuance",
        )
    if (
        issuance.transaction_ref() is not transaction
        or issuance.registry is not transaction.registry
        or issuance.registry_snapshot_hash != transaction.registry_snapshot_hash
        or issuance.resource_bindings is not transaction.resource_bindings
        or issuance.mint is not transaction.mint
        or type(transaction.mint) is not object
        or _fixed_registry_authority_snapshot_hash_v1(transaction.registry)
        != issuance.registry_snapshot_hash
    ):
        _fail(
            "hip_fgmres_all_converged_registry_transaction_binding_mismatch",
            "/issuance",
        )
    return transaction.registry


def _refresh_fixed_registry_replay_transaction_v1(
    transaction: _FixedRegistryReplayTransactionV1,
) -> HipFgmresAllConvergedFixtureRegistryResultV1:
    """Rehash all fixed raw resources without repeating CPU/dense replay."""

    registry = _registry_from_fixed_replay_transaction_v1(transaction)
    for name, expected_hash in transaction.resource_bindings:
        if sha256_prefixed(_read_fixed_resource(name)) != expected_hash:
            _fail(
                "hip_fgmres_all_converged_registry_transaction_resource_hash_mismatch",
                f"/resources/{name}",
            )
    return registry


def validate_hip_fgmres_all_converged_fixture_registry_result_v1(
    result: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> HipFgmresAllConvergedFixtureRegistryResultV1:
    """Revalidate retained authorities and compare with a fresh replay."""

    if type(result) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_registry_result_type_invalid", "/")
    if (
        type(result.slots) is not tuple
        or len(result.slots)
        != len(HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1)
        or any(
            type(row) is not HipFgmresAllConvergedFixtureReplayV1
            for row in result.slots
        )
    ):
        _fail("hip_fgmres_all_converged_registry_result_slots_invalid", "/slots")
    if result.registry_bytes_sha256 != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail(
            "hip_fgmres_all_converged_registry_result_bytes_hash_mismatch",
            "/registry_bytes_sha256",
        )
    _validate_retained_authorities(result)
    expected = _replay_package_registry()
    if _result_payload(result, include_hash=False) != _result_payload(
        expected, include_hash=False
    ):
        _fail("hip_fgmres_all_converged_registry_result_replay_mismatch", "/")
    expected_receipt_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.receipt_hash != expected_receipt_hash:
        _fail(
            "hip_fgmres_all_converged_registry_receipt_hash_mismatch",
            "/receipt_hash",
        )
    return result


def _replay_package_registry() -> HipFgmresAllConvergedFixtureRegistryResultV1:
    raw = _read_fixed_resource(_REGISTRY_RESOURCE)
    if sha256_prefixed(raw) != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail(
            "hip_fgmres_all_converged_registry_resource_hash_mismatch",
            "/registry",
        )
    manifest = _parse_strict_object(raw, path="/registry")
    _validate_registry_schema(manifest)
    declared_hash = manifest["registry_hash"]
    hash_payload = dict(manifest)
    del hash_payload["registry_hash"]
    if declared_hash != canonical_hash(hash_payload):
        _fail(
            "hip_fgmres_all_converged_registry_content_hash_mismatch",
            "/registry_hash",
        )
    required = HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    if tuple(manifest["required_slot_ids"]) != required:
        _fail(
            "hip_fgmres_all_converged_registry_required_slots_mismatch",
            "/required_slot_ids",
        )
    rows = manifest["slots"]
    if tuple(row["slot_id"] for row in rows) != required:
        _fail("hip_fgmres_all_converged_registry_slot_order_mismatch", "/slots")
    _require_unique_manifest_values(
        rows,
        key="slot_registration_hash",
        code="hip_fgmres_all_converged_registry_registration_hash_duplicate",
    )
    _require_unique_manifest_values(
        rows,
        key="case_fingerprint",
        code="hip_fgmres_all_converged_registry_case_fingerprint_duplicate",
    )
    _require_unique_manifest_values(
        rows,
        key="model_bytes_sha256",
        code="hip_fgmres_all_converged_registry_model_bytes_hash_duplicate",
    )
    _require_unique_manifest_values(
        rows,
        key="model_ir_content_hash",
        nested="expected",
        code="hip_fgmres_all_converged_registry_model_content_hash_duplicate",
    )
    _require_unique_manifest_values(
        rows,
        key="execution_plan_hash",
        nested="expected",
        code="hip_fgmres_all_converged_registry_execution_plan_hash_duplicate",
    )
    slots = tuple(_replay_slot(row, index) for index, row in enumerate(rows))
    if len({row.model.content_hash for row in slots}) != len(slots) or len(
        {row.execution_plan.plan_hash for row in slots}
    ) != len(slots):
        _fail("hip_fgmres_all_converged_registry_actual_uniqueness_mismatch", "/slots")
    if any(
        row.cpu_result.status != "converged"
        or not row.cpu_result.solver_tolerance_passed
        or not row.cpu_result.authoritative_plan_tolerance_passed
        for row in slots
    ):
        _fail("hip_fgmres_all_converged_registry_convergence_mismatch", "/slots")
    draft = HipFgmresAllConvergedFixtureRegistryResultV1(
        registry_bytes_sha256=_REGISTRY_RESOURCE_BYTES_SHA256,
        registry_hash=declared_hash,
        slots=slots,
        receipt_hash="sha256:" + "0" * 64,
    )
    return HipFgmresAllConvergedFixtureRegistryResultV1(
        registry_bytes_sha256=draft.registry_bytes_sha256,
        registry_hash=draft.registry_hash,
        slots=draft.slots,
        receipt_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )


def _require_unique_manifest_values(
    rows: list[dict[str, Any]],
    *,
    key: str,
    code: str,
    nested: str | None = None,
) -> None:
    values = tuple(row[key] if nested is None else row[nested][key] for row in rows)
    if len(set(values)) != len(rows):
        _fail(code, "/slots")


def _replay_slot(
    row: dict[str, Any], index: int
) -> HipFgmresAllConvergedFixtureReplayV1:
    path = f"/slots/{index}"
    slot_id = row["slot_id"]
    rule = _semantic_rule(slot_id)
    expected_resource = f"{slot_id}.model.json"
    expected_group = _group(slot_id)
    expected_description = _description(slot_id)
    expected_load_pattern = _load_pattern_id(slot_id)
    if row["model_resource"] != expected_resource:
        _fail(
            "hip_fgmres_all_converged_registry_model_resource_mismatch",
            f"{path}/model_resource",
        )
    if row["group"] != expected_group:
        _fail(
            "hip_fgmres_all_converged_registry_group_mismatch",
            f"{path}/group",
        )
    if row["description"] != expected_description:
        _fail(
            "hip_fgmres_all_converged_registry_description_mismatch",
            f"{path}/description",
        )
    if row["load_pattern_id"] != expected_load_pattern:
        _fail(
            "hip_fgmres_all_converged_registry_load_pattern_mismatch",
            f"{path}/load_pattern_id",
        )
    if row["semantic_profile"] != f"{slot_id}.v1":
        _fail(
            "hip_fgmres_all_converged_registry_semantic_profile_mismatch",
            f"{path}/semantic_profile",
        )
    if row["semantic_contract"] != rule.to_dict():
        _fail(
            "hip_fgmres_all_converged_registry_semantic_contract_mismatch",
            f"{path}/semantic_contract",
        )
    policy_parameters = _policy_parameters(slot_id)
    if row["policy_parameters"] != policy_parameters:
        _fail(
            "hip_fgmres_all_converged_registry_policy_parameters_mismatch",
            f"{path}/policy_parameters",
        )
    hash_payload = dict(row)
    declared_registration_hash = hash_payload.pop("slot_registration_hash")
    if declared_registration_hash != canonical_hash(hash_payload):
        _fail(
            "hip_fgmres_all_converged_registry_slot_hash_mismatch",
            f"{path}/slot_registration_hash",
        )

    try:
        model_raw = _read_fixed_resource(expected_resource)
        if sha256_prefixed(model_raw) != row["model_bytes_sha256"]:
            _fail(
                "hip_fgmres_all_converged_registry_model_bytes_hash_mismatch",
                f"{path}/model_bytes_sha256",
            )
        payload = _parse_strict_object(model_raw, path=f"{path}/model")
        model = parse_model_ir_v2(payload, require_analysis_ready=True)
        execution = compile_execution_plan_v2(
            pack_solver_model_buffers(
                model,
                load_pattern_id=row["load_pattern_id"],
            ),
            residual_tolerance=float(row["execution_residual_tolerance"]),
        )
        policy = compile_fgmres_policy_v1(
            restart_dimension=policy_parameters["restart_dimension"],
            max_iterations=policy_parameters["max_iterations"],
            absolute_tolerance=float(policy_parameters["absolute_tolerance"]),
            relative_tolerance=float(policy_parameters["relative_tolerance"]),
            stagnation_checkpoint_limit=policy_parameters[
                "stagnation_checkpoint_limit"
            ],
            stagnation_relative_tolerance=float(
                policy_parameters["stagnation_relative_tolerance"]
            ),
            divergence_factor=float(policy_parameters["divergence_factor"]),
        )
        cpu = solve_cpu_fgmres_reference_v1(execution, policy)
        free_space = compile_hip_free_space_operator_plan_v1(execution)
        fgmres = compile_hip_fgmres_plan_v1(execution, free_space, policy)
        recurrence = compile_hip_fgmres_recurrence_plan_v2(fgmres)
        descriptor = _derive_descriptor(execution)
        direct_solution, direct_residual = _deterministic_dense_oracle(execution)
        _validate_semantics(
            slot_id=slot_id,
            rule=rule,
            model=model,
            execution=execution,
            descriptor=descriptor,
            cpu=cpu,
            direct_solution=direct_solution,
        )
    except HipFgmresAllConvergedFixtureRegistryV1Error:
        raise
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_registry_slot_replay_failed",
            path,
            f"{type(exc).__name__}: {exc}",
        )

    actual_expected = _expected_snapshot(
        model=model,
        execution=execution,
        descriptor=descriptor,
        policy=policy,
        cpu=cpu,
        free_space=free_space,
        fgmres=fgmres,
        recurrence=recurrence,
        direct_solution=direct_solution,
        direct_residual=direct_residual,
    )
    if row["expected"] != actual_expected:
        _fail(
            "hip_fgmres_all_converged_registry_expected_replay_mismatch",
            f"{path}/expected",
        )
    actual_fingerprint = canonical_hash(
        {
            "slot_id": slot_id,
            "semantic_profile": row["semantic_profile"],
            "model_ir_content_hash": model.content_hash,
            "execution_plan_hash": execution.plan_hash,
            "descriptor_hash": descriptor.descriptor_hash,
            "policy_hash": policy.policy_hash,
            "cpu_result_hash": cpu.result_hash,
            "cpu_history_hash": actual_expected["cpu_history_hash"],
            "direct_solution_data_hash": actual_expected["direct_solution_data_hash"],
        }
    )
    if row["case_fingerprint"] != actual_fingerprint:
        _fail(
            "hip_fgmres_all_converged_registry_case_fingerprint_mismatch",
            f"{path}/case_fingerprint",
        )
    return HipFgmresAllConvergedFixtureReplayV1(
        slot_id=slot_id,
        group=row["group"],
        description=row["description"],
        model_resource=expected_resource,
        model_bytes_sha256=row["model_bytes_sha256"],
        semantic_profile=row["semantic_profile"],
        case_fingerprint=actual_fingerprint,
        slot_registration_hash=declared_registration_hash,
        descriptor=descriptor,
        model=model,
        execution_plan=execution,
        policy=policy,
        cpu_result=cpu,
        free_space_plan=free_space,
        fgmres_plan=fgmres,
        recurrence_plan=recurrence,
        direct_solution=direct_solution,
        direct_residual=direct_residual,
    )


def _validate_semantics(
    *,
    slot_id: str,
    rule: _SemanticRuleV1,
    model: ModelIRDocument,
    execution: ExecutionPlanV2,
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    cpu: CpuFgmresReferenceResultV1,
    direct_solution: np.ndarray,
) -> None:
    payload = model.to_dict()
    nodes = payload["nodes"]
    elements = payload["elements"]
    patterns = payload["load_patterns"]
    if (
        len(nodes) != rule.node_count
        or len(elements) != rule.element_count
        or execution.dof_count != rule.global_dof_count
        or int(execution.array("free_dofs").size) != rule.free_dof_count
        or execution.reduced_nnz != rule.reduced_csr_nnz
        or descriptor.node_count != rule.node_count
        or descriptor.element_count != rule.element_count
        or descriptor.nonzero_local_axis_roll_count
        != rule.nonzero_local_axis_roll_count
        or descriptor.nonzero_offset_component_count != 0
        or descriptor.released_dof_count != 0
    ):
        _fail(
            "hip_fgmres_all_converged_registry_semantic_extent_mismatch",
            f"/slots/{slot_id}/semantics",
        )
    if len(patterns) != 1 or len(patterns[0]["nodal_loads"]) != 1:
        _fail(
            "hip_fgmres_all_converged_registry_semantic_load_count_mismatch",
            f"/slots/{slot_id}/semantics/load",
        )
    load = patterns[0]["nodal_loads"][0]
    components = load["components_si"]
    expected_components = {
        name: rule.load_value_si if name == rule.load_component else 0.0
        for name in _COMPONENT_INDEX
    }
    if (
        load["node_id"] != rule.load_node_id
        or components != expected_components
        or any(value != 0.0 for value in patterns[0]["self_weight"])
    ):
        _fail(
            "hip_fgmres_all_converged_registry_semantic_load_mismatch",
            f"/slots/{slot_id}/semantics/load",
        )
    _validate_topology(slot_id, rule, payload, execution)
    rhs = execution.array("global_load")[execution.array("free_dofs")]
    rhs_nonzero = tuple(int(index) for index in np.flatnonzero(rhs))
    expected_rhs_nonzero = (
        () if rule.zero_reduced_rhs else (_expected_free_rhs_index(rule),)
    )
    if rhs_nonzero != expected_rhs_nonzero:
        _fail(
            "hip_fgmres_all_converged_registry_semantic_free_rhs_mismatch",
            f"/slots/{slot_id}/semantics/free_rhs",
        )
    cycles = tuple(
        (row.start_iteration, row.end_iteration, row.arnoldi_step_count)
        for row in cpu.history
    )
    if cycles != rule.history_cycles:
        _fail(
            "hip_fgmres_all_converged_registry_semantic_history_mismatch",
            f"/slots/{slot_id}/semantics/history",
        )
    expected_solution = np.zeros(rule.free_dof_count, dtype=np.float64)
    for index, value in rule.analytic_free_solution_nonzero:
        expected_solution[index] = value
    if not np.allclose(
        direct_solution,
        expected_solution,
        rtol=1.0e-12,
        atol=1.0e-12,
    ):
        _fail(
            "hip_fgmres_all_converged_registry_analytic_solution_mismatch",
            f"/slots/{slot_id}/semantics/direct_solution",
        )
    if (
        cpu.status != "converged"
        or not cpu.solver_tolerance_passed
        or not cpu.authoritative_plan_tolerance_passed
        or not np.allclose(
            cpu.reduced_solution,
            direct_solution,
            rtol=1.0e-10,
            atol=1.0e-12,
        )
    ):
        _fail(
            "hip_fgmres_all_converged_registry_cpu_solution_mismatch",
            f"/slots/{slot_id}/semantics/cpu_solution",
        )


def _validate_topology(
    slot_id: str,
    rule: _SemanticRuleV1,
    payload: dict[str, Any],
    execution: ExecutionPlanV2,
) -> None:
    nodes = payload["nodes"]
    elements = payload["elements"]
    expected_coordinates = (
        [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
        if slot_id == "solution_frame_single_rotated_axis_bending"
        else [[float(2 * index), 0.0, 0.0] for index in range(rule.node_count)]
    )
    if [node["coordinates_m"] for node in nodes] != expected_coordinates:
        _fail(
            "hip_fgmres_all_converged_registry_semantic_coordinates_mismatch",
            f"/slots/{slot_id}/semantics/nodes",
        )
    expected_connectivity = [
        [f"N{index + 1}", f"N{index + 2}"] for index in range(rule.element_count)
    ]
    if [element["node_ids"] for element in elements] != expected_connectivity:
        _fail(
            "hip_fgmres_all_converged_registry_semantic_connectivity_mismatch",
            f"/slots/{slot_id}/semantics/elements",
        )
    if rule.model_kind == "frame_3d":
        if any(
            element["type"] != "frame_3d"
            or element["formulation"] != "euler_bernoulli_3d"
            or any(
                value != 0.0
                for values in element["offsets"].values()
                for value in values
            )
            or element["releases"] != {"i": [], "j": []}
            for element in elements
        ):
            _fail(
                "hip_fgmres_all_converged_registry_semantic_frame_mismatch",
                f"/slots/{slot_id}/semantics/elements",
            )
        rolls = [element["local_axis_rotation_rad"] for element in elements]
        expected_rolls = (
            [0.37]
            if slot_id == "solution_frame_single_rotated_axis_bending"
            else [0.0] * rule.element_count
        )
        if rolls != expected_rolls:
            _fail(
                "hip_fgmres_all_converged_registry_semantic_roll_mismatch",
                f"/slots/{slot_id}/semantics/elements/roll",
            )
    else:
        element = elements[0]
        section = payload["sections"][0]
        if (
            element["type"] != "truss_3d"
            or element["formulation"] != "linear_truss_3d"
            or "local_axis_rotation_rad" in element
            or "releases" in element
            or section["family_id"] != "truss_3d"
            or section["parameters"] != {"area_m2": 0.02}
        ):
            _fail(
                "hip_fgmres_all_converged_registry_semantic_truss_mismatch",
                f"/slots/{slot_id}/semantics/truss",
            )
    support = execution._source_buffers.array("support_mask")
    expected_support = np.zeros((rule.node_count, 6), dtype=support.dtype)
    expected_support[0, :] = 1
    if rule.model_kind == "truss_3d":
        expected_support[1, 1:] = 1
    if not np.array_equal(support, expected_support):
        _fail(
            "hip_fgmres_all_converged_registry_semantic_support_mismatch",
            f"/slots/{slot_id}/semantics/support",
        )


def _expected_free_rhs_index(rule: _SemanticRuleV1) -> int:
    node_index = int(rule.load_node_id[1:]) - 2
    return node_index * 6 + _COMPONENT_INDEX[rule.load_component]


def _expected_snapshot(
    *,
    model: ModelIRDocument,
    execution: ExecutionPlanV2,
    descriptor: HipFgmresModelFamilyCaseDescriptorV1,
    policy: FgmresPolicyV1,
    cpu: CpuFgmresReferenceResultV1,
    free_space: HipFreeSpaceOperatorPlanV1,
    fgmres: HipFgmresPlanV1,
    recurrence: HipFgmresRecurrencePlanV2,
    direct_solution: np.ndarray,
    direct_residual: np.ndarray,
) -> dict[str, Any]:
    return {
        "model_ir_content_hash": model.content_hash,
        "execution_plan_hash": execution.plan_hash,
        "descriptor_hash": descriptor.descriptor_hash,
        "free_space_plan_hash": free_space.plan_hash,
        "fgmres_plan_hash": fgmres.plan_hash,
        "recurrence_plan_hash": recurrence.plan_hash,
        "policy_hash": policy.policy_hash,
        "cpu_result_hash": cpu.result_hash,
        "cpu_status": cpu.status,
        "cpu_termination_code": cpu.termination_code,
        "cpu_iteration_count": cpu.iteration_count,
        "cpu_restart_count": cpu.restart_count,
        "cpu_operator_apply_count": cpu.operator_apply_count,
        "cpu_preconditioner_apply_count": cpu.preconditioner_apply_count,
        "solver_tolerance_passed": cpu.solver_tolerance_passed,
        "authoritative_plan_tolerance_passed": (
            cpu.authoritative_plan_tolerance_passed
        ),
        "cpu_history_hash": canonical_hash([row.to_dict() for row in cpu.history]),
        "cpu_solution_data_hash": array_data_hash(cpu.reduced_solution),
        "cpu_true_residual_data_hash": array_data_hash(cpu.true_residual),
        "direct_solution_data_hash": array_data_hash(direct_solution),
        "direct_residual_data_hash": array_data_hash(direct_residual),
    }


def _deterministic_dense_oracle(
    plan: ExecutionPlanV2,
) -> tuple[np.ndarray, np.ndarray]:
    """Reuse the independent dense oracle behind a distinct error boundary."""

    try:
        return _termination_registry._deterministic_dense_oracle(plan)
    except HipFgmresFixtureRegistryV1Error as exc:
        code = exc.code.replace(
            "hip_fgmres_fixture_registry_",
            "hip_fgmres_all_converged_registry_",
            1,
        )
        _fail(code, exc.path, exc.message)


def _validate_retained_authorities(
    result: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> None:
    for index, row in enumerate(result.slots):
        path = f"/slots/{index}"
        try:
            if type(row.model) is not ModelIRDocument:
                _fail(
                    "hip_fgmres_all_converged_registry_model_type_invalid",
                    f"{path}/model",
                )
            reparsed = parse_model_ir_v2(row.model.to_dict())
            if reparsed.content_hash != row.model.content_hash:
                _fail(
                    "hip_fgmres_all_converged_registry_model_replay_mismatch",
                    f"{path}/model",
                )
            validate_execution_plan_v2(row.execution_plan)
            validate_fgmres_policy_v1(row.policy)
            validate_cpu_fgmres_reference_result_v1(
                row.cpu_result,
                expected_plan=row.execution_plan,
                expected_policy=row.policy,
            )
            validate_hip_free_space_operator_plan_v1(
                row.free_space_plan,
                expected_execution_plan=row.execution_plan,
            )
            validate_hip_fgmres_plan_v1(
                row.fgmres_plan,
                expected_execution_plan=row.execution_plan,
                expected_free_space_plan=row.free_space_plan,
            )
            validate_hip_fgmres_recurrence_plan_v2(
                row.recurrence_plan,
                expected_source_plan=row.fgmres_plan,
            )
            if _derive_descriptor(row.execution_plan) != row.descriptor:
                _fail(
                    "hip_fgmres_all_converged_registry_descriptor_replay_mismatch",
                    f"{path}/descriptor",
                )
            direct_solution, direct_residual = _deterministic_dense_oracle(
                row.execution_plan
            )
            if array_data_hash(direct_solution) != array_data_hash(
                row.direct_solution
            ) or array_data_hash(direct_residual) != array_data_hash(
                row.direct_residual
            ):
                _fail(
                    "hip_fgmres_all_converged_registry_direct_replay_mismatch",
                    f"{path}/direct_oracle",
                )
            if (
                row.cpu_result.status != "converged"
                or not row.cpu_result.solver_tolerance_passed
                or not row.cpu_result.authoritative_plan_tolerance_passed
            ):
                _fail(
                    "hip_fgmres_all_converged_registry_retained_convergence_invalid",
                    f"{path}/cpu_result",
                )
        except HipFgmresAllConvergedFixtureRegistryV1Error:
            raise
        except Exception as exc:
            _fail(
                "hip_fgmres_all_converged_registry_authority_invalid",
                path,
                f"{type(exc).__name__}: {exc}",
            )


def _result_payload(
    result: HipFgmresAllConvergedFixtureRegistryResultV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": (HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1),
        "capability_profile": (
            HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1
        ),
        "suite_id": HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
        "evidence_scope": (HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1),
        "registry_bytes_sha256": result.registry_bytes_sha256,
        "registry_hash": result.registry_hash,
        "registered_slot_count": len(result.slots),
        "registered_slot_ids": [row.slot_id for row in result.slots],
        "unique_model_bytes_hash_count": len(
            {row.model_bytes_sha256 for row in result.slots}
        ),
        "unique_model_ir_content_hash_count": len(
            {row.model.content_hash for row in result.slots}
        ),
        "unique_execution_plan_hash_count": len(
            {row.execution_plan.plan_hash for row in result.slots}
        ),
        "nontrivial_solution_case_count": sum(
            not _semantic_rule(row.slot_id).zero_reduced_rhs for row in result.slots
        ),
        "zero_free_rhs_edge_count": sum(
            _semantic_rule(row.slot_id).zero_reduced_rhs for row in result.slots
        ),
        "slots": [row.to_manifest() for row in result.slots],
        "claims": {
            "package_all_converged_fixture_registry_replayed": True,
            "fixed_suite_registration_complete": True,
            "ten_unique_model_ir_verified": True,
            "all_cpu_reference_converged": True,
            "all_solver_tolerance_passed": True,
            "all_authoritative_plan_tolerance_passed": True,
            "actual_hip_execution_verified": False,
            "result_ir_verified": False,
            "signed_evidence": False,
            "promotion_eligible": False,
            "full_model_family_parity_verified": False,
            "multiarchitecture_parity_verified": False,
            "same_process_actual_two_isa_verified": False,
            "iteration_host_copy_zero_verified": False,
            "speedup_verified": False,
            "end_to_end_o_n_verified": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["receipt_hash"] = result.receipt_hash
    return payload


def _fixed_registry_authority_snapshot_hash_v1(
    registry: HipFgmresAllConvergedFixtureRegistryResultV1,
) -> str:
    if type(registry) is not HipFgmresAllConvergedFixtureRegistryResultV1:
        _fail("hip_fgmres_all_converged_registry_transaction_type_invalid", "/")
    return canonical_hash(
        {
            "registry_bytes_sha256": registry.registry_bytes_sha256,
            "registry_hash": registry.registry_hash,
            "receipt_hash": registry.receipt_hash,
            "slots": [
                {
                    "manifest": row.to_manifest(),
                    "free_space_plan_hash": row.free_space_plan.plan_hash,
                    "fgmres_plan_hash": row.fgmres_plan.plan_hash,
                    "recurrence_plan_hash": row.recurrence_plan.plan_hash,
                    "direct_solution_data_hash": array_data_hash(row.direct_solution),
                    "direct_residual_data_hash": array_data_hash(row.direct_residual),
                }
                for row in registry.slots
            ],
        }
    )


def _read_fixed_resource(name: str) -> bytes:
    if (
        type(name) is not str
        or not name
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
    ):
        _fail("hip_fgmres_all_converged_registry_resource_name_invalid", "/resource")
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(name)
    if not resource.is_file():
        _fail(
            "hip_fgmres_all_converged_registry_resource_missing",
            f"/resources/{name}",
        )
    try:
        return resource.read_bytes()
    except OSError as exc:
        _fail(
            "hip_fgmres_all_converged_registry_resource_read_failed",
            f"/resources/{name}",
            str(exc),
        )


def _parse_strict_object(raw: bytes, *, path: str) -> dict[str, Any]:
    """Reuse the strict JSON parser while translating its error namespace."""

    try:
        return _termination_registry._parse_strict_object(raw, path=path)
    except HipFgmresFixtureRegistryV1Error as exc:
        code = exc.code.replace(
            "hip_fgmres_fixture_registry_",
            "hip_fgmres_all_converged_registry_",
            1,
        )
        _fail(code, exc.path, exc.message)


def _validate_registry_schema(manifest: dict[str, Any]) -> None:
    schema_raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    schema = _parse_strict_object(schema_raw, path="/schema")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        _fail(
            "hip_fgmres_all_converged_registry_schema_invalid",
            "/schema",
            str(exc),
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(
            "hip_fgmres_all_converged_registry_schema_validation_failed",
            location,
            error.message,
        )


def _policy_parameters(slot_id: str) -> dict[str, Any]:
    restart_dimension, max_iterations = {
        "solution_frame_single_axial": (2, 2),
        "solution_frame_single_weak_axis_bending": (2, 2),
        "solution_frame_single_strong_axis_bending": (2, 2),
        "solution_frame_single_torsion": (2, 2),
        "solution_frame_single_rotated_axis_bending": (6, 6),
        "solution_frame_serial_two_span_axial": (2, 2),
        "solution_truss_single_axial": (1, 1),
        "solution_frame_zero_free_rhs_edge": (2, 2),
        "solution_frame_serial_four_span_axial": (4, 4),
        "solution_frame_serial_five_span_axial": (5, 5),
    }.get(slot_id, (0, 0))
    if restart_dimension == 0:
        _fail(
            "hip_fgmres_all_converged_registry_slot_id_invalid",
            "/slot_id",
            slot_id,
        )
    return {
        "restart_dimension": restart_dimension,
        "max_iterations": max_iterations,
        "absolute_tolerance": 0.0,
        "relative_tolerance": 1.0e-12,
        "stagnation_checkpoint_limit": 2,
        "stagnation_relative_tolerance": 1.4901161193847656e-08,
        "divergence_factor": 100000000.0,
    }


def _semantic_rule(slot_id: str) -> _SemanticRuleV1:
    rules = {
        "solution_frame_single_axial": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "FX",
            100000.0,
            "N2",
            0,
            False,
            ((0, 1, 1),),
            ((0, 5.0e-5),),
        ),
        "solution_frame_single_weak_axis_bending": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "FY",
            -10000.0,
            "N2",
            0,
            False,
            ((0, 2, 2),),
            ((1, -0.0026666666666666666), (5, -0.002)),
        ),
        "solution_frame_single_strong_axis_bending": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "FZ",
            -10000.0,
            "N2",
            0,
            False,
            ((0, 2, 2),),
            ((2, -0.0016666666666666668), (4, 0.00125)),
        ),
        "solution_frame_single_torsion": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "MX",
            5000.0,
            "N2",
            0,
            False,
            ((0, 1, 1),),
            ((3, 0.013),),
        ),
        "solution_frame_single_rotated_axis_bending": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "FY",
            -1.0,
            "N2",
            1,
            False,
            ((0, 6, 6),),
            (
                (0, 2.552171711639753e-07),
                (1, -7.960471927653038e-07),
                (2, 4.450021285577484e-07),
                (3, 3.512299109369364e-07),
                (4, 3.4355291242947314e-08),
                (5, -1.3998016447427768e-07),
            ),
        ),
        "solution_frame_serial_two_span_axial": _SemanticRuleV1(
            "frame_3d",
            3,
            2,
            18,
            12,
            144,
            "FX",
            100000.0,
            "N3",
            0,
            False,
            ((0, 2, 2),),
            ((0, 5.0e-5), (6, 1.0e-4)),
        ),
        "solution_truss_single_axial": _SemanticRuleV1(
            "truss_3d",
            2,
            1,
            12,
            1,
            1,
            "FX",
            100000.0,
            "N2",
            0,
            False,
            ((0, 1, 1),),
            ((0, 5.0e-5),),
        ),
        "solution_frame_zero_free_rhs_edge": _SemanticRuleV1(
            "frame_3d",
            2,
            1,
            12,
            6,
            36,
            "FX",
            100000.0,
            "N1",
            0,
            True,
            (),
            (),
        ),
        "solution_frame_serial_four_span_axial": _SemanticRuleV1(
            "frame_3d",
            5,
            4,
            30,
            24,
            360,
            "FX",
            1.0,
            "N5",
            0,
            False,
            ((0, 4, 4),),
            ((0, 5.0e-10), (6, 1.0e-9), (12, 1.5e-9), (18, 2.0e-9)),
        ),
        "solution_frame_serial_five_span_axial": _SemanticRuleV1(
            "frame_3d",
            6,
            5,
            36,
            30,
            468,
            "FX",
            1.0,
            "N6",
            0,
            False,
            ((0, 5, 5),),
            (
                (0, 5.0e-10),
                (6, 1.0e-9),
                (12, 1.5e-9),
                (18, 2.0e-9),
                (24, 2.5e-9),
            ),
        ),
    }
    try:
        return rules[slot_id]
    except KeyError:
        _fail(
            "hip_fgmres_all_converged_registry_slot_id_invalid",
            "/slot_id",
            slot_id,
        )


def _group(slot_id: str) -> str:
    _semantic_rule(slot_id)
    return (
        "solution_edge_semantics"
        if slot_id == "solution_frame_zero_free_rhs_edge"
        else "solution_semantics"
    )


def _description(slot_id: str) -> str:
    descriptions = {
        "solution_frame_single_axial": ("single straight frame under axial excitation"),
        "solution_frame_single_weak_axis_bending": (
            "single straight frame under weak-axis bending excitation"
        ),
        "solution_frame_single_strong_axis_bending": (
            "single straight frame under strong-axis bending excitation"
        ),
        "solution_frame_single_torsion": (
            "single straight frame under torsional excitation"
        ),
        "solution_frame_single_rotated_axis_bending": (
            "single skew frame with nonzero local-axis roll under normalized unit "
            "bending excitation"
        ),
        "solution_frame_serial_two_span_axial": (
            "three-node two-span serial frame under axial excitation"
        ),
        "solution_truss_single_axial": ("single truss element under axial excitation"),
        "solution_frame_zero_free_rhs_edge": (
            "single frame with a load entirely on the constrained partition"
        ),
        "solution_frame_serial_four_span_axial": (
            "five-node four-span serial frame under normalized unit axial excitation"
        ),
        "solution_frame_serial_five_span_axial": (
            "six-node five-span serial frame under normalized unit axial excitation"
        ),
    }
    try:
        return descriptions[slot_id]
    except KeyError:
        _fail(
            "hip_fgmres_all_converged_registry_slot_id_invalid",
            "/slot_id",
            slot_id,
        )


def _load_pattern_id(slot_id: str) -> str:
    identifiers = {
        "solution_frame_single_axial": "LC_AXIAL",
        "solution_frame_single_weak_axis_bending": "LC_WEAK",
        "solution_frame_single_strong_axis_bending": "LC_STRONG",
        "solution_frame_single_torsion": "LC_TORSION",
        "solution_frame_single_rotated_axis_bending": "LC_WEAK",
        "solution_frame_serial_two_span_axial": "LC_AXIAL",
        "solution_truss_single_axial": "LC_AXIAL",
        "solution_frame_zero_free_rhs_edge": "LC_AXIAL",
        "solution_frame_serial_four_span_axial": "LC_AXIAL",
        "solution_frame_serial_five_span_axial": "LC_AXIAL",
    }
    try:
        return identifiers[slot_id]
    except KeyError:
        _fail(
            "hip_fgmres_all_converged_registry_slot_id_invalid",
            "/slot_id",
            slot_id,
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresAllConvergedFixtureRegistryV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1",
    "HipFgmresAllConvergedFixtureRegistryResultV1",
    "HipFgmresAllConvergedFixtureRegistryV1Error",
    "HipFgmresAllConvergedFixtureReplayV1",
    "load_hip_fgmres_all_converged_fixture_registry_v1",
    "validate_hip_fgmres_all_converged_fixture_registry_result_v1",
]
