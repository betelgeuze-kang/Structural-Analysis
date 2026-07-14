"""Fail-closed package-owned replay for the fixed FGMRES fixture suite.

The registry is a local, unsigned, non-promoting validation authority.  It
does not establish full model-family coverage, multi-architecture parity,
performance, ResultIR, host-copy-zero, O(N), or commercial-readiness claims.
Every load reads fixed package resources, verifies the code-anchored registry
bytes, and replays ModelIR through the CPU and HIP planning contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
import math
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
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


HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-fixture-registry.v1"
)
HIP_FGMRES_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1 = (
    "phase0_package_owned_fgmres_fixed_suite_replay"
)
HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1 = (
    "phase0_execution_plan_v2_linear_frame_truss_fgmres_fixed_suite.v2"
)
HIP_FGMRES_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1 = (
    "package_local_unsigned_non_promoting"
)
HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1 = (
    "frame_single_axial",
    "frame_single_weak_axis_bending",
    "frame_single_strong_axis_bending",
    "frame_single_torsion",
    "frame_single_rotated_local_axis_bending",
    "frame_serial_later_column",
    "truss_single_axial",
    "recurrence_initial_or_early_terminal",
    "recurrence_later_restart_partial_final_cycle",
    "recurrence_exact_full_final_cycle_guard",
)

_RESOURCE_PACKAGE = (
    "structural_analysis.engine_v2.assembly_backend.fixtures.fgmres_family_v2"
)
_REGISTRY_RESOURCE = "registry.v1.json"
_REGISTRY_RESOURCE_BYTES_SHA256 = (
    "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
)
_SCHEMA_RESOURCE = "hip_fgmres_fixture_registry_v1.schema.json"
_COMPONENT_INDEX = {name: index for index, name in enumerate(
    ("FX", "FY", "FZ", "MX", "MY", "MZ")
)}


class HipFgmresFixtureRegistryV1Error(RuntimeError):
    """Stable fail-closed package fixture registry error."""

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
            "nonzero_local_axis_roll_count": (
                self.nonzero_local_axis_roll_count
            ),
            "zero_reduced_rhs": self.zero_reduced_rhs,
            "history_cycles": [list(row) for row in self.history_cycles],
            "analytic_free_solution_nonzero": [
                [index, value]
                for index, value in self.analytic_free_solution_nonzero
            ],
        }


@dataclass(frozen=True, slots=True)
class HipFgmresFixtureReplayV1:
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
    free_space_plan: HipFreeSpaceOperatorPlanV1 = field(
        repr=False, compare=False
    )
    fgmres_plan: HipFgmresPlanV1 = field(repr=False, compare=False)
    recurrence_plan: HipFgmresRecurrencePlanV2 = field(
        repr=False, compare=False
    )
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
            "cpu_history_hash": canonical_hash(
                [row.to_dict() for row in self.cpu_result.history]
            ),
            "direct_solution_data_hash": array_data_hash(
                self.direct_solution
            ),
            "direct_residual_data_hash": array_data_hash(
                self.direct_residual
            ),
            "case_fingerprint": self.case_fingerprint,
            "slot_registration_hash": self.slot_registration_hash,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresFixtureRegistryResultV1:
    registry_bytes_sha256: str
    registry_hash: str
    slots: tuple[HipFgmresFixtureReplayV1, ...]
    receipt_hash: str

    def slot(self, slot_id: str) -> HipFgmresFixtureReplayV1:
        matches = tuple(row for row in self.slots if row.slot_id == slot_id)
        if len(matches) != 1:
            raise KeyError(slot_id)
        return matches[0]

    def to_manifest(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)


class _DuplicateKeyError(ValueError):
    pass


def load_hip_fgmres_fixture_registry_v1() -> HipFgmresFixtureRegistryResultV1:
    """Read and replay the exact package registry; no path override exists."""

    # Every compiler used by the replay validates its own retained authority;
    # the explicit result validator below is reserved for caller-retained
    # results and intentionally performs a second, independent package replay.
    return _replay_package_registry()


def validate_hip_fgmres_fixture_registry_result_v1(
    result: HipFgmresFixtureRegistryResultV1,
) -> HipFgmresFixtureRegistryResultV1:
    """Revalidate retained authorities and compare with fresh package replay."""

    if type(result) is not HipFgmresFixtureRegistryResultV1:
        _fail("hip_fgmres_fixture_registry_result_type_invalid", "/")
    if (
        type(result.slots) is not tuple
        or len(result.slots) != len(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1)
        or any(type(row) is not HipFgmresFixtureReplayV1 for row in result.slots)
    ):
        _fail("hip_fgmres_fixture_registry_result_slots_invalid", "/slots")
    if result.registry_bytes_sha256 != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail(
            "hip_fgmres_fixture_registry_result_bytes_hash_mismatch",
            "/registry_bytes_sha256",
        )
    _validate_retained_authorities(result)
    expected = _replay_package_registry()
    if _result_payload(result, include_hash=False) != _result_payload(
        expected, include_hash=False
    ):
        _fail("hip_fgmres_fixture_registry_result_replay_mismatch", "/")
    expected_receipt_hash = canonical_hash(
        _result_payload(result, include_hash=False)
    )
    if result.receipt_hash != expected_receipt_hash:
        _fail(
            "hip_fgmres_fixture_registry_receipt_hash_mismatch",
            "/receipt_hash",
        )
    return result


def _replay_package_registry() -> HipFgmresFixtureRegistryResultV1:
    raw = _read_fixed_resource(_REGISTRY_RESOURCE)
    if sha256_prefixed(raw) != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail(
            "hip_fgmres_fixture_registry_resource_hash_mismatch",
            "/registry",
        )
    manifest = _parse_strict_object(raw, path="/registry")
    _validate_registry_schema(manifest)
    declared_hash = manifest["registry_hash"]
    hash_payload = dict(manifest)
    del hash_payload["registry_hash"]
    if declared_hash != canonical_hash(hash_payload):
        _fail(
            "hip_fgmres_fixture_registry_content_hash_mismatch",
            "/registry_hash",
        )
    if tuple(manifest["required_slot_ids"]) != (
        HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    ):
        _fail(
            "hip_fgmres_fixture_registry_required_slots_mismatch",
            "/required_slot_ids",
        )
    rows = manifest["slots"]
    if tuple(row["slot_id"] for row in rows) != (
        HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    ):
        _fail("hip_fgmres_fixture_registry_slot_order_mismatch", "/slots")
    registration_hashes = tuple(row["slot_registration_hash"] for row in rows)
    fingerprints = tuple(row["case_fingerprint"] for row in rows)
    if len(set(registration_hashes)) != len(rows):
        _fail(
            "hip_fgmres_fixture_registry_registration_hash_duplicate",
            "/slots",
        )
    if len(set(fingerprints)) != len(rows):
        _fail(
            "hip_fgmres_fixture_registry_case_fingerprint_duplicate",
            "/slots",
        )
    slots = tuple(_replay_slot(row, index) for index, row in enumerate(rows))
    draft = HipFgmresFixtureRegistryResultV1(
        registry_bytes_sha256=_REGISTRY_RESOURCE_BYTES_SHA256,
        registry_hash=declared_hash,
        slots=slots,
        receipt_hash="sha256:" + "0" * 64,
    )
    return HipFgmresFixtureRegistryResultV1(
        registry_bytes_sha256=draft.registry_bytes_sha256,
        registry_hash=draft.registry_hash,
        slots=draft.slots,
        receipt_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )


def _replay_slot(row: dict[str, Any], index: int) -> HipFgmresFixtureReplayV1:
    path = f"/slots/{index}"
    slot_id = row["slot_id"]
    rule = _semantic_rule(slot_id)
    expected_resource = f"{slot_id}.model.json"
    expected_group = (
        "recurrence_semantics"
        if slot_id.startswith("recurrence_")
        else "model_semantics"
    )
    if row["model_resource"] != expected_resource:
        _fail(
            "hip_fgmres_fixture_registry_model_resource_mismatch",
            f"{path}/model_resource",
        )
    if row["group"] != expected_group:
        _fail("hip_fgmres_fixture_registry_group_mismatch", f"{path}/group")
    if row["semantic_profile"] != f"{slot_id}.v1":
        _fail(
            "hip_fgmres_fixture_registry_semantic_profile_mismatch",
            f"{path}/semantic_profile",
        )
    if row["semantic_contract"] != rule.to_dict():
        _fail(
            "hip_fgmres_fixture_registry_semantic_contract_mismatch",
            f"{path}/semantic_contract",
        )
    policy_parameters = _policy_parameters(slot_id)
    if row["policy_parameters"] != policy_parameters:
        _fail(
            "hip_fgmres_fixture_registry_policy_parameters_mismatch",
            f"{path}/policy_parameters",
        )
    hash_payload = dict(row)
    declared_registration_hash = hash_payload.pop("slot_registration_hash")
    if declared_registration_hash != canonical_hash(hash_payload):
        _fail(
            "hip_fgmres_fixture_registry_slot_hash_mismatch",
            f"{path}/slot_registration_hash",
        )

    try:
        model_raw = _read_fixed_resource(expected_resource)
        if sha256_prefixed(model_raw) != row["model_bytes_sha256"]:
            _fail(
                "hip_fgmres_fixture_registry_model_bytes_hash_mismatch",
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
    except HipFgmresFixtureRegistryV1Error:
        raise
    except Exception as exc:
        _fail(
            "hip_fgmres_fixture_registry_slot_replay_failed",
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
            "hip_fgmres_fixture_registry_expected_replay_mismatch",
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
            "direct_solution_data_hash": actual_expected[
                "direct_solution_data_hash"
            ],
        }
    )
    if row["case_fingerprint"] != actual_fingerprint:
        _fail(
            "hip_fgmres_fixture_registry_case_fingerprint_mismatch",
            f"{path}/case_fingerprint",
        )
    return HipFgmresFixtureReplayV1(
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
            "hip_fgmres_fixture_registry_semantic_extent_mismatch",
            f"/slots/{slot_id}/semantics",
        )
    if len(patterns) != 1 or len(patterns[0]["nodal_loads"]) != 1:
        _fail(
            "hip_fgmres_fixture_registry_semantic_load_count_mismatch",
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
            "hip_fgmres_fixture_registry_semantic_load_mismatch",
            f"/slots/{slot_id}/semantics/load",
        )
    _validate_topology(slot_id, rule, payload, execution)
    rhs = execution.array("global_load")[execution.array("free_dofs")]
    rhs_nonzero = tuple(int(index) for index in np.flatnonzero(rhs))
    expected_rhs_nonzero = (
        ()
        if rule.zero_reduced_rhs
        else (_expected_free_rhs_index(rule),)
    )
    if rhs_nonzero != expected_rhs_nonzero:
        _fail(
            "hip_fgmres_fixture_registry_semantic_free_rhs_mismatch",
            f"/slots/{slot_id}/semantics/free_rhs",
        )
    cycles = tuple(
        (row.start_iteration, row.end_iteration, row.arnoldi_step_count)
        for row in cpu.history
    )
    if cycles != rule.history_cycles:
        _fail(
            "hip_fgmres_fixture_registry_semantic_history_mismatch",
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
            "hip_fgmres_fixture_registry_analytic_solution_mismatch",
            f"/slots/{slot_id}/semantics/direct_solution",
        )
    if cpu.status == "converged" and not np.allclose(
        cpu.reduced_solution,
        direct_solution,
        rtol=1.0e-10,
        atol=1.0e-12,
    ):
        _fail(
            "hip_fgmres_fixture_registry_cpu_direct_solution_mismatch",
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
        if slot_id == "frame_single_rotated_local_axis_bending"
        else [[float(2 * index), 0.0, 0.0] for index in range(rule.node_count)]
    )
    if [node["coordinates_m"] for node in nodes] != expected_coordinates:
        _fail(
            "hip_fgmres_fixture_registry_semantic_coordinates_mismatch",
            f"/slots/{slot_id}/semantics/nodes",
        )
    expected_connectivity = [
        [f"N{index + 1}", f"N{index + 2}"]
        for index in range(rule.element_count)
    ]
    if [element["node_ids"] for element in elements] != expected_connectivity:
        _fail(
            "hip_fgmres_fixture_registry_semantic_connectivity_mismatch",
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
                "hip_fgmres_fixture_registry_semantic_frame_mismatch",
                f"/slots/{slot_id}/semantics/elements",
            )
        rolls = [element["local_axis_rotation_rad"] for element in elements]
        expected_rolls = (
            [0.37]
            if slot_id == "frame_single_rotated_local_axis_bending"
            else [0.0] * rule.element_count
        )
        if rolls != expected_rolls:
            _fail(
                "hip_fgmres_fixture_registry_semantic_roll_mismatch",
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
                "hip_fgmres_fixture_registry_semantic_truss_mismatch",
                f"/slots/{slot_id}/semantics/truss",
            )
    support = execution._source_buffers.array("support_mask")
    expected_support = np.zeros((rule.node_count, 6), dtype=support.dtype)
    expected_support[0, :] = 1
    if rule.model_kind == "truss_3d":
        expected_support[1, 1:] = 1
    if not np.array_equal(support, expected_support):
        _fail(
            "hip_fgmres_fixture_registry_semantic_support_mismatch",
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
        "cpu_history_hash": canonical_hash(
            [row.to_dict() for row in cpu.history]
        ),
        "cpu_solution_data_hash": array_data_hash(cpu.reduced_solution),
        "cpu_true_residual_data_hash": array_data_hash(cpu.true_residual),
        "direct_solution_data_hash": array_data_hash(direct_solution),
        "direct_residual_data_hash": array_data_hash(direct_residual),
    }


def _deterministic_dense_oracle(
    plan: ExecutionPlanV2,
) -> tuple[np.ndarray, np.ndarray]:
    """Small-fixture Gaussian elimination independent of FGMRES and BLAS."""

    validate_execution_plan_v2(plan)
    size = int(plan.array("free_dofs").size)
    if not 1 <= size <= 64:
        _fail(
            "hip_fgmres_fixture_registry_direct_oracle_extent_invalid",
            "/direct_oracle",
        )
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    matrix = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for cursor in range(int(row_ptr[row]), int(row_ptr[row + 1])):
            matrix[row][int(columns[cursor])] = float(values[cursor])
    rhs_array = plan.array("global_load")[plan.array("free_dofs")]
    rhs = [float(value) for value in rhs_array]
    source_matrix = [row[:] for row in matrix]
    source_rhs = rhs[:]
    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(matrix[row][column]),
        )
        if matrix[pivot][column] == 0.0:
            _fail(
                "hip_fgmres_fixture_registry_direct_oracle_singular",
                "/direct_oracle",
            )
        if pivot != column:
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        for row in range(column + 1, size):
            factor = matrix[row][column] / matrix[column][column]
            matrix[row][column] = 0.0
            for cursor in range(column + 1, size):
                matrix[row][cursor] -= factor * matrix[column][cursor]
            rhs[row] -= factor * rhs[column]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        tail = sum(
            matrix[row][column] * solution[column]
            for column in range(row + 1, size)
        )
        solution[row] = (rhs[row] - tail) / matrix[row][row]
    residual = [
        source_rhs[row]
        - sum(
            source_matrix[row][column] * solution[column]
            for column in range(size)
        )
        for row in range(size)
    ]
    if not all(math.isfinite(value) for value in solution + residual):
        _fail(
            "hip_fgmres_fixture_registry_direct_oracle_nonfinite",
            "/direct_oracle",
        )
    return (
        immutable_array(solution, dtype="<f8"),
        immutable_array(residual, dtype="<f8"),
    )


def _validate_retained_authorities(
    result: HipFgmresFixtureRegistryResultV1,
) -> None:
    for index, row in enumerate(result.slots):
        path = f"/slots/{index}"
        try:
            if type(row.model) is not ModelIRDocument:
                _fail(
                    "hip_fgmres_fixture_registry_model_type_invalid",
                    f"{path}/model",
                )
            reparsed = parse_model_ir_v2(row.model.to_dict())
            if reparsed.content_hash != row.model.content_hash:
                _fail(
                    "hip_fgmres_fixture_registry_model_replay_mismatch",
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
                    "hip_fgmres_fixture_registry_descriptor_replay_mismatch",
                    f"{path}/descriptor",
                )
            direct_solution, direct_residual = _deterministic_dense_oracle(
                row.execution_plan
            )
            if (
                array_data_hash(direct_solution)
                != array_data_hash(row.direct_solution)
                or array_data_hash(direct_residual)
                != array_data_hash(row.direct_residual)
            ):
                _fail(
                    "hip_fgmres_fixture_registry_direct_replay_mismatch",
                    f"{path}/direct_oracle",
                )
        except HipFgmresFixtureRegistryV1Error:
            raise
        except Exception as exc:
            _fail(
                "hip_fgmres_fixture_registry_authority_invalid",
                path,
                f"{type(exc).__name__}: {exc}",
            )


def _result_payload(
    result: HipFgmresFixtureRegistryResultV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
        "capability_profile": (
            HIP_FGMRES_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1
        ),
        "suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        "evidence_scope": HIP_FGMRES_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1,
        "registry_bytes_sha256": result.registry_bytes_sha256,
        "registry_hash": result.registry_hash,
        "registered_slot_count": len(result.slots),
        "registered_slot_ids": [row.slot_id for row in result.slots],
        "slots": [row.to_manifest() for row in result.slots],
        "claims": {
            "package_fixture_registry_replayed": True,
            "fixed_suite_registration_complete": True,
            "signed_evidence": False,
            "promotion_eligible": False,
            "full_model_family_parity_verified": False,
            "multiarchitecture_parity_verified": False,
            "same_process_actual_two_isa_verified": False,
            "result_ir_verified": False,
            "iteration_host_copy_zero_verified": False,
            "speedup_verified": False,
            "end_to_end_o_n_verified": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["receipt_hash"] = result.receipt_hash
    return payload


def _read_fixed_resource(name: str) -> bytes:
    if (
        type(name) is not str
        or not name
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
    ):
        _fail("hip_fgmres_fixture_registry_resource_name_invalid", "/resource")
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(name)
    if not resource.is_file():
        _fail(
            "hip_fgmres_fixture_registry_resource_missing",
            f"/resources/{name}",
        )
    try:
        return resource.read_bytes()
    except OSError as exc:
        _fail(
            "hip_fgmres_fixture_registry_resource_read_failed",
            f"/resources/{name}",
            str(exc),
        )


def _parse_strict_object(raw: bytes, *, path: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_fixture_registry_json_bom_forbidden", path)

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKeyError(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        _reject_nonfinite(payload, path=path)
    except _DuplicateKeyError as exc:
        _fail(
            "hip_fgmres_fixture_registry_json_duplicate_key",
            path,
            str(exc),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(
            "hip_fgmres_fixture_registry_json_invalid",
            path,
            str(exc),
        )
    if type(payload) is not dict:
        _fail("hip_fgmres_fixture_registry_json_root_invalid", path)
    return payload


def _reject_nonfinite(value: Any, *, path: str) -> None:
    if type(value) is float and not math.isfinite(value):
        _fail("hip_fgmres_fixture_registry_json_nonfinite", path)
    if type(value) is dict:
        for key, item in value.items():
            _reject_nonfinite(item, path=f"{path}/{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_nonfinite(item, path=f"{path}/{index}")


def _validate_registry_schema(manifest: dict[str, Any]) -> None:
    schema_raw = resources.files("structural_analysis.schemas").joinpath(
        _SCHEMA_RESOURCE
    ).read_bytes()
    schema = _parse_strict_object(schema_raw, path="/schema")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        _fail(
            "hip_fgmres_fixture_registry_schema_invalid",
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
            "hip_fgmres_fixture_registry_schema_validation_failed",
            location,
            error.message,
        )


def _policy_parameters(slot_id: str) -> dict[str, Any]:
    restart_dimension, max_iterations, relative_tolerance = {
        "frame_single_rotated_local_axis_bending": (6, 5, 1.0e-30),
        "frame_serial_later_column": (2, 2, 1.0e-15),
        "truss_single_axial": (1, 1, 1.0e-12),
        "recurrence_later_restart_partial_final_cycle": (2, 5, 1.0e-30),
        "recurrence_exact_full_final_cycle_guard": (2, 4, 1.0e-30),
    }.get(slot_id, (2, 2, 1.0e-12))
    return {
        "restart_dimension": restart_dimension,
        "max_iterations": max_iterations,
        "absolute_tolerance": 0.0,
        "relative_tolerance": relative_tolerance,
        "stagnation_checkpoint_limit": 2,
        "stagnation_relative_tolerance": 1.4901161193847656e-08,
        "divergence_factor": 100000000.0,
    }


def _semantic_rule(slot_id: str) -> _SemanticRuleV1:
    rules = {
        "frame_single_axial": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "FX", 100000.0, "N2", 0,
            False, ((0, 1, 1),), ((0, 5.0e-5),),
        ),
        "frame_single_weak_axis_bending": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "FY", -10000.0, "N2", 0,
            False, ((0, 2, 2),), ((1, -0.0026666666666666666), (5, -0.002)),
        ),
        "frame_single_strong_axis_bending": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "FZ", -10000.0, "N2", 0,
            False, ((0, 2, 2),), ((2, -0.0016666666666666668), (4, 0.00125)),
        ),
        "frame_single_torsion": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "MX", 5000.0, "N2", 0,
            False, ((0, 1, 1),), ((3, 0.013),),
        ),
        "frame_single_rotated_local_axis_bending": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "FY", -10000.0, "N2", 1,
            False, ((0, 5, 5),),
            (
                (0, 0.002552171711639753),
                (1, -0.007960471927653038),
                (2, 0.004450021285577484),
                (3, 0.0035122991093693642),
                (4, 0.00034355291242947313),
                (5, -0.0013998016447427767),
            ),
        ),
        "frame_serial_later_column": _SemanticRuleV1(
            "frame_3d", 3, 2, 18, 12, 144, "FX", 100000.0, "N3", 0,
            False, ((0, 2, 2),), ((0, 5.0e-5), (6, 1.0e-4)),
        ),
        "truss_single_axial": _SemanticRuleV1(
            "truss_3d", 2, 1, 12, 1, 1, "FX", 100000.0, "N2", 0,
            False, ((0, 1, 1),), ((0, 5.0e-5),),
        ),
        "recurrence_initial_or_early_terminal": _SemanticRuleV1(
            "frame_3d", 2, 1, 12, 6, 36, "FX", 100000.0, "N1", 0,
            True, (), (),
        ),
        "recurrence_later_restart_partial_final_cycle": _SemanticRuleV1(
            "frame_3d", 5, 4, 30, 24, 360, "FX", 100000.0, "N5", 0,
            False, ((0, 2, 2), (2, 4, 2), (4, 5, 1)),
            ((0, 5.0e-5), (6, 1.0e-4), (12, 1.5e-4), (18, 2.0e-4)),
        ),
        "recurrence_exact_full_final_cycle_guard": _SemanticRuleV1(
            "frame_3d", 5, 4, 30, 24, 360, "FX", 100000.0, "N5", 0,
            False, ((0, 2, 2), (2, 4, 2)),
            ((0, 5.0e-5), (6, 1.0e-4), (12, 1.5e-4), (18, 2.0e-4)),
        ),
    }
    try:
        return rules[slot_id]
    except KeyError:
        _fail(
            "hip_fgmres_fixture_registry_slot_id_invalid",
            "/slot_id",
            slot_id,
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresFixtureRegistryV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_FIXTURE_REGISTRY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1",
    "HipFgmresFixtureRegistryResultV1",
    "HipFgmresFixtureRegistryV1Error",
    "HipFgmresFixtureReplayV1",
    "load_hip_fgmres_fixture_registry_v1",
    "validate_hip_fgmres_fixture_registry_result_v1",
]
