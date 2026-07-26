"""Replay-bound compiler/adapter for connected branching 2D frame graphs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, validators

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
    StatefulCorotationalFiberFrame2DProblem,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    CorotationalFiberFrameJStageReceipt,
    JStageName,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
)


COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-general-j1-j5-adapter.v1"
)
COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE = (
    "planar_connected_branching_frame_explicit_fiber_section.v1"
)
COROTATIONAL_FIBER_FRAME_GENERAL_AUTHORITY_PROFILE = (
    "non_promoting_general_corotational_convergence_candidate.v1"
)
COROTATIONAL_FIBER_FRAME_GENERAL_PRESCRIBED_PROFILE = (
    "terminal_value_scaled_by_load_factor.v1"
)

_HASH_ZERO = "sha256:" + "0" * 64
_EXPECTED_STAGES: tuple[JStageName, ...] = ("J1", "J2", "J3", "J4", "J5")
_STAGE_PROFILES = MappingProxyType(
    {
        "J1": "corotational_connected_branching_topology_operator_binding.v1",
        "J2": "corotational_scaling_and_proportional_prescribed_displacement.v1",
        "J3": "corotational_committed_checkpoint_chain.v1",
        "J4": "corotational_solver_assembly_state_binding.v1",
        "J5": "corotational_full_load_terminal_contract.v1",
    }
)
_STAGE_CHECK_NAMES = MappingProxyType(
    {
        "J1": (
            "connected_graph_passed",
            "multiple_support_semantics_bound",
            "operator_bound",
            "unsupported_member_features_absent",
        ),
        "J2": (
            "coordinate_scaling_bound",
            "reference_load_bound",
            "prescribed_displacement_bound",
        ),
        "J3": ("checkpoint_chain_complete", "rollback_ancestry_bound"),
        "J4": (
            "solver_assembly_binding_passed",
            "iterative_or_no_solve_contract_passed",
            "no_fallback_or_regularization",
        ),
        "J5": ("full_load_terminal_passed", "solver_terminal_contract_passed"),
    }
)
_AUTHORITY_AXES = MappingProxyType(
    {
        "topology": "connected_graph_candidate_bound",
        "member_features": "not_supported",
        "multiple_support": "candidate_bound",
        "prescribed_displacement": "proportional_candidate_bound",
        "equation_scaling": "candidate_bound",
        "state_ancestry": "candidate_bound",
        "solver_state_binding": "candidate_bound",
        "convergence": "bounded_candidate",
        "numerical_result": "not_created",
        "reaction": "not_created",
        "member_force": "not_created",
        "section_resultant": "not_created",
        "fiber_result": "not_created",
        "release_readiness": "not_authoritative",
    }
)
_LIMITATIONS = (
    "connected_planar_frame_graph_only",
    "proportional_nodal_load_only",
    "prescribed_displacement_scaled_by_load_factor",
    "load_control_cpu_dense_or_native_sparse_newton_only",
    "parallel_members_not_supported",
    "disconnected_graphs_not_supported",
    "member_end_releases_not_supported",
    "rigid_offsets_not_supported",
    "distributed_member_loads_not_supported",
    "direct_displacement_control_not_supported",
    "external_level2_not_attached",
    "standalone_manifest_source_authenticity_not_established",
    "public_capability_not_promoted",
)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class CorotationalFiberFrameGeneralError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class CorotationalFiberFrameGeneralCompilation:
    schema_version: str
    compiler_profile: str
    compiler_hash: str
    model_content_hash: str
    problem_contract_hash: str
    case_id: str
    node_count: int
    member_count: int
    support_node_indices: tuple[int, ...]
    branching_node_indices: tuple[int, ...]
    maximum_node_degree: int
    prescribed_displacements: tuple[tuple[int, float], ...]
    _problem: StatefulCorotationalFiberFrame2DProblem = field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_corotational_general_compilation(self)
        return _compilation_payload(self, include_hash=True)


@dataclass(frozen=True)
class CorotationalFiberFrameGeneralJ1J5Adapter:
    schema_version: str
    adapter_hash: str
    compiler_profile: str
    compiler_hash: str
    authority_profile: str
    model_content_hash: str
    problem_contract_hash: str
    case_id: str
    terminal_checkpoint_hash: str
    terminal_load_factor: float
    stage_receipts: tuple[CorotationalFiberFrameJStageReceipt, ...]
    authority_axes: Mapping[str, str]
    limitations: tuple[str, ...]
    _compilation: CorotationalFiberFrameGeneralCompilation = field(
        repr=False, compare=False
    )
    _path: StatefulCorotationalFiberFrame2DLoadPathResult = field(
        repr=False, compare=False
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_corotational_fiber_frame_general_j1_j5_adapter(self)
        return _adapter_payload(self, include_hash=True)


def compile_corotational_fiber_frame_general_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
    *,
    model_content_hash: str,
) -> CorotationalFiberFrameGeneralCompilation:
    if type(problem) is not StatefulCorotationalFiberFrame2DProblem:
        _fail(
            "corotational_general_problem_type_invalid",
            "/problem",
            "Expected exact StatefulCorotationalFiberFrame2DProblem.",
        )
    model_hash = _require_hash(model_content_hash, "/model_content_hash")
    graph = _validate_general_profile(problem)
    provisional = CorotationalFiberFrameGeneralCompilation(
        schema_version=COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION,
        compiler_profile=COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE,
        compiler_hash=_HASH_ZERO,
        model_content_hash=model_hash,
        problem_contract_hash=problem.contract_hash,
        case_id=problem.case_id,
        node_count=len(problem.node_coordinates_m),
        member_count=len(problem.members),
        support_node_indices=graph["support_nodes"],
        branching_node_indices=graph["branching_nodes"],
        maximum_node_degree=graph["maximum_degree"],
        prescribed_displacements=problem.prescribed_displacements,
        _problem=problem,
    )
    compiled = replace(
        provisional,
        compiler_hash=canonical_hash(
            _compilation_payload(provisional, include_hash=False)
        ),
    )
    return validate_corotational_general_compilation(compiled)


def create_corotational_fiber_frame_general_j1_j5_adapter(
    compilation: CorotationalFiberFrameGeneralCompilation,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> CorotationalFiberFrameGeneralJ1J5Adapter:
    validate_corotational_general_compilation(compilation)
    receipts = _build_stage_receipts(compilation, path)
    provisional = CorotationalFiberFrameGeneralJ1J5Adapter(
        schema_version=COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION,
        adapter_hash=_HASH_ZERO,
        compiler_profile=compilation.compiler_profile,
        compiler_hash=compilation.compiler_hash,
        authority_profile=COROTATIONAL_FIBER_FRAME_GENERAL_AUTHORITY_PROFILE,
        model_content_hash=compilation.model_content_hash,
        problem_contract_hash=compilation.problem_contract_hash,
        case_id=compilation.case_id,
        terminal_checkpoint_hash=path.final_checkpoint.state_hash,
        terminal_load_factor=path.final_checkpoint.load_factor,
        stage_receipts=receipts,
        authority_axes=_AUTHORITY_AXES,
        limitations=_LIMITATIONS,
        _compilation=compilation,
        _path=path,
    )
    adapter = replace(
        provisional,
        adapter_hash=canonical_hash(_adapter_payload(provisional, include_hash=False)),
    )
    return validate_corotational_fiber_frame_general_j1_j5_adapter(adapter)


def validate_corotational_general_compilation(
    compilation: CorotationalFiberFrameGeneralCompilation,
) -> CorotationalFiberFrameGeneralCompilation:
    if type(compilation) is not CorotationalFiberFrameGeneralCompilation:
        _fail(
            "corotational_general_compilation_type_invalid",
            "/",
            "Expected exact general compilation type.",
        )
    if (
        compilation.schema_version != COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION
        or compilation.compiler_profile
        != COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE
    ):
        _fail(
            "corotational_general_compiler_profile_invalid",
            "/compiler_profile",
            "Compiler schema/profile is fixed by v1.",
        )
    _require_hash(compilation.compiler_hash, "/compiler_hash")
    _require_hash(compilation.model_content_hash, "/model_content_hash")
    _require_hash(compilation.problem_contract_hash, "/problem_contract_hash")
    problem = compilation._problem
    if type(problem) is not StatefulCorotationalFiberFrame2DProblem:
        _fail(
            "corotational_general_problem_type_invalid",
            "/problem",
            "Retained problem has the wrong type.",
        )
    graph = _validate_general_profile(problem)
    if (
        compilation.problem_contract_hash != problem.contract_hash
        or compilation.case_id != problem.case_id
        or compilation.node_count != len(problem.node_coordinates_m)
        or compilation.member_count != len(problem.members)
        or compilation.support_node_indices != graph["support_nodes"]
        or compilation.branching_node_indices != graph["branching_nodes"]
        or compilation.maximum_node_degree != graph["maximum_degree"]
        or compilation.prescribed_displacements != problem.prescribed_displacements
    ):
        _fail(
            "corotational_general_compilation_binding_invalid",
            "/",
            "Compilation metadata differs from the retained frame graph.",
        )
    if compilation.compiler_hash != canonical_hash(
        _compilation_payload(compilation, include_hash=False)
    ):
        _fail(
            "corotational_general_compiler_hash_mismatch",
            "/compiler_hash",
            "Compiler hash differs from canonical content.",
        )
    return compilation


def validate_corotational_fiber_frame_general_j1_j5_adapter(
    adapter: CorotationalFiberFrameGeneralJ1J5Adapter,
) -> CorotationalFiberFrameGeneralJ1J5Adapter:
    if type(adapter) is not CorotationalFiberFrameGeneralJ1J5Adapter:
        _fail(
            "corotational_general_adapter_type_invalid",
            "/",
            "Expected exact general J1-J5 adapter type.",
        )
    compilation = validate_corotational_general_compilation(adapter._compilation)
    try:
        authority_axes = dict(adapter.authority_axes)
    except (TypeError, ValueError):
        _fail(
            "corotational_general_adapter_binding_invalid",
            "/authority_axes",
            "Authority axes must be the fixed v1 mapping.",
        )
    if (
        adapter.schema_version != COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION
        or adapter.compiler_profile != compilation.compiler_profile
        or adapter.compiler_hash != compilation.compiler_hash
        or adapter.authority_profile
        != COROTATIONAL_FIBER_FRAME_GENERAL_AUTHORITY_PROFILE
        or adapter.model_content_hash != compilation.model_content_hash
        or adapter.problem_contract_hash != compilation.problem_contract_hash
        or adapter.case_id != compilation.case_id
        or authority_axes != dict(_AUTHORITY_AXES)
        or adapter.limitations != _LIMITATIONS
    ):
        _fail(
            "corotational_general_adapter_binding_invalid",
            "/",
            "Adapter metadata or claim boundary differs from v1.",
        )
    if adapter.stage_receipts != _build_stage_receipts(compilation, adapter._path):
        _fail(
            "corotational_general_adapter_replay_mismatch",
            "/stage_receipts",
            "J1-J5 receipts differ from replayed retained sources.",
        )
    if tuple(row.stage for row in adapter.stage_receipts) != _EXPECTED_STAGES:
        _fail(
            "corotational_general_stage_order_invalid",
            "/stage_receipts",
            "Adapter must contain J1 through J5 exactly once and in order.",
        )
    if (
        adapter.terminal_checkpoint_hash != adapter._path.final_checkpoint.state_hash
        or adapter.terminal_load_factor != adapter._path.final_checkpoint.load_factor
        or not _terminal_path_target_passed(adapter._path)
    ):
        _fail(
            "corotational_general_terminal_binding_invalid",
            "/terminal_checkpoint_hash",
            "J5 requires the exact full-load terminal checkpoint.",
        )
    if adapter.adapter_hash != canonical_hash(
        _adapter_payload(adapter, include_hash=False)
    ):
        _fail(
            "corotational_general_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash differs from canonical content.",
        )
    _validate_schema(_adapter_payload(adapter, include_hash=True))
    return adapter


def validate_corotational_fiber_frame_general_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError, OverflowError):
        _fail(
            "corotational_general_manifest_invalid",
            "/",
            "Adapter manifest must be a finite JSON object.",
        )
    _validate_schema(normalized)
    compilation = dict(normalized["compilation"])
    compiler_hash = compilation.pop("compiler_hash")
    if compiler_hash != canonical_hash(compilation):
        _fail(
            "corotational_general_compiler_hash_mismatch",
            "/compilation/compiler_hash",
            "Embedded compilation hash differs from canonical content.",
        )
    embedded = normalized["compilation"]
    if not (
        2 <= embedded["node_count"] <= 128
        and 1 <= embedded["member_count"] <= 256
        and embedded["support_node_indices"]
        and len(set(embedded["support_node_indices"]))
        == len(embedded["support_node_indices"])
        and all(
            0 <= node < embedded["node_count"]
            for node in embedded["support_node_indices"]
        )
        and all(
            0 <= node < embedded["node_count"]
            for node in embedded["branching_node_indices"]
        )
        and embedded["maximum_node_degree"] >= 1
    ):
        _fail(
            "corotational_general_compilation_semantics_invalid",
            "/compilation",
            "Embedded bounded graph metadata is invalid.",
        )
    stage_rows = normalized["stage_receipts"]
    j1_body = stage_rows[0]["body"]
    free_global_dofs = j1_body.get("free_global_dofs")
    global_dof_count = 3 * embedded["node_count"]
    if (
        not isinstance(free_global_dofs, list)
        or len(set(free_global_dofs)) != len(free_global_dofs)
        or any(
            type(dof) is not int or not 0 <= dof < global_dof_count
            for dof in free_global_dofs
        )
        or j1_body.get("support_nodes") != embedded["support_node_indices"]
        or j1_body.get("branching_nodes") != embedded["branching_node_indices"]
        or j1_body.get("maximum_degree") != embedded["maximum_node_degree"]
    ):
        _fail(
            "corotational_general_stage_body_binding_invalid",
            "/stage_receipts/0/body",
            "J1 graph and equation metadata differ from the embedded compilation.",
        )
    support_nodes = set(embedded["support_node_indices"])
    prescribed_displacements = embedded["prescribed_displacements"]
    if any(
        type(row[0]) is not int
        or not 0 <= row[0] < global_dof_count
        or row[0] in free_global_dofs
        or row[0] // 3 not in support_nodes
        for row in prescribed_displacements
    ):
        _fail(
            "corotational_general_prescribed_displacement_semantics_invalid",
            "/compilation/prescribed_displacements",
            "Prescribed DOFs must be in range and constrained on declared support nodes.",
        )
    if (
        stage_rows[1]["body"].get("prescribed_displacements")
        != prescribed_displacements
    ):
        _fail(
            "corotational_general_stage_body_binding_invalid",
            "/stage_receipts/1/body/prescribed_displacements",
            "J2 prescribed displacements differ from the embedded compilation.",
        )

    for key in (
        "schema_version",
        "compiler_profile",
        "model_content_hash",
        "problem_contract_hash",
        "case_id",
    ):
        if normalized[key] != embedded[key]:
            _fail(
                "corotational_general_compilation_binding_invalid",
                f"/{key}",
                "Adapter metadata differs from the embedded compilation.",
            )
    if normalized["compiler_hash"] != embedded["compiler_hash"]:
        _fail(
            "corotational_general_compilation_binding_invalid",
            "/compiler_hash",
            "Adapter compiler hash differs from the embedded compilation.",
        )
    if (
        normalized["authority_profile"]
        != COROTATIONAL_FIBER_FRAME_GENERAL_AUTHORITY_PROFILE
        or normalized["authority_axes"] != dict(_AUTHORITY_AXES)
        or normalized["limitations"] != list(_LIMITATIONS)
        or normalized["terminal_load_factor"] != 1.0
    ):
        _fail(
            "corotational_general_manifest_semantics_invalid",
            "/",
            "Authority boundary or terminal target differs from v1.",
        )
    for index, (stage_name, row) in enumerate(
        zip(_EXPECTED_STAGES, normalized["stage_receipts"], strict=True)
    ):
        expected_checks = {name: True for name in _STAGE_CHECK_NAMES[stage_name]}
        if (
            row["stage"] != stage_name
            or row["contract_profile"] != _STAGE_PROFILES[stage_name]
            or row["checks"] != expected_checks
        ):
            _fail(
                "corotational_general_stage_semantics_invalid",
                f"/stage_receipts/{index}",
                "Stage order, profile, and checks are fixed by v1.",
            )
        expected_stage_hash = canonical_hash(
            _stage_hash_payload(
                stage=stage_name,
                contract_profile=row["contract_profile"],
                source_hashes=tuple(row["source_hashes"]),
                checks=row["checks"],
                body=row["body"],
            )
        )
        if row["stage_hash"] != expected_stage_hash:
            _fail(
                "corotational_general_stage_hash_mismatch",
                f"/stage_receipts/{index}/stage_hash",
                "Stage hash differs from canonical receipt content.",
            )

    j1, j2, j3, j4, j5 = stage_rows
    if j1["source_hashes"] != [
        normalized["problem_contract_hash"],
        normalized["compiler_hash"],
    ] or j2["source_hashes"] != [normalized["problem_contract_hash"]]:
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts",
            "J1/J2 sources differ from the advertised problem or compiler hashes.",
        )
    checkpoint_hashes = j3["source_hashes"]
    checkpoint_body = j3["body"]
    if (
        len(checkpoint_hashes) < 2
        or checkpoint_hashes[-1] != normalized["terminal_checkpoint_hash"]
        or len(checkpoint_body.get("epochs", ())) != len(checkpoint_hashes)
        or len(checkpoint_body.get("load_factors", ())) != len(checkpoint_hashes)
        or len(checkpoint_body.get("parents", ())) != len(checkpoint_hashes)
        or checkpoint_body["load_factors"][-1] != normalized["terminal_load_factor"]
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/2",
            "J3 checkpoint sources do not bind the advertised terminal state.",
        )
    expected_accepted_hashes = checkpoint_hashes[1:]
    step_bindings = j4["body"].get("step_bindings")
    if (
        j4["source_hashes"] != expected_accepted_hashes
        or not isinstance(step_bindings, list)
        or len(step_bindings) != len(expected_accepted_hashes)
        or any(
            row.get("parent") != checkpoint_hashes[index]
            or row.get("assembly_parent") != checkpoint_hashes[index]
            or row.get("accepted") != expected_accepted_hashes[index]
            for index, row in enumerate(step_bindings)
        )
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/3",
            "J4 step sources do not match the J3 checkpoint ancestry.",
        )
    if (
        j5["source_hashes"] != [normalized["terminal_checkpoint_hash"]]
        or j5["body"].get("terminal_load_factor") != normalized["terminal_load_factor"]
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/4",
            "J5 source or terminal load differs from the advertised terminal fields.",
        )

    claimed = normalized["adapter_hash"]
    body = dict(normalized)
    body.pop("adapter_hash")
    if claimed != canonical_hash(body):
        _fail(
            "corotational_general_adapter_hash_mismatch",
            "/adapter_hash",
            "Manifest hash differs from canonical content.",
        )
    return normalized


def _validate_general_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> dict[str, Any]:
    node_count = len(problem.node_coordinates_m)
    if not 2 <= node_count <= 128 or not 1 <= len(problem.members) <= 256:
        _fail(
            "corotational_general_topology_count_invalid",
            "/problem",
            "The bounded profile accepts 2-128 nodes and 1-256 members.",
        )
    adjacency: list[set[int]] = [set() for _ in range(node_count)]
    edges: set[frozenset[int]] = set()
    for index, member in enumerate(problem.members):
        edge = frozenset((member.node_i, member.node_j))
        if edge in edges:
            _fail(
                "corotational_general_duplicate_edge",
                f"/members/{index}",
                "Parallel members between the same two nodes are not supported in v1.",
            )
        edges.add(edge)
        adjacency[member.node_i].add(member.node_j)
        adjacency[member.node_j].add(member.node_i)
    visited = {0}
    frontier = [0]
    while frontier:
        node = frontier.pop()
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    if len(visited) != node_count:
        _fail(
            "corotational_general_graph_disconnected",
            "/members",
            "Every node must belong to one connected member graph.",
        )
    support_nodes = tuple(sorted({dof // 3 for dof in problem.fixed_global_dofs}))
    if not support_nodes:
        _fail(
            "corotational_general_support_missing",
            "/fixed_global_dofs",
            "At least one constrained support node is required.",
        )
    degrees = tuple(len(neighbors) for neighbors in adjacency)
    return {
        "support_nodes": support_nodes,
        "branching_nodes": tuple(
            index for index, degree in enumerate(degrees) if degree >= 3
        ),
        "maximum_degree": max(degrees),
    }


def _build_stage_receipts(
    compilation: CorotationalFiberFrameGeneralCompilation,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> tuple[CorotationalFiberFrameJStageReceipt, ...]:
    if type(path) is not StatefulCorotationalFiberFrame2DLoadPathResult:
        _fail(
            "corotational_general_path_type_invalid",
            "/path",
            "Expected exact corotational load-path result.",
        )
    problem = compilation._problem
    checkpoints = (path.initial_checkpoint,) + tuple(
        step.accepted_checkpoint for step in path.steps if step.committed
    )
    for index, checkpoint in enumerate(checkpoints):
        try:
            validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
        except (TypeError, ValueError):
            _fail(
                "corotational_general_j3_checkpoint_invalid",
                f"/checkpoints/{index}",
                "Checkpoint is invalid for the retained problem.",
            )
    chain_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) >= 1
        and len(checkpoints) == len(path.steps) + 1
        and path.initial_checkpoint.epoch == 0
        and path.initial_checkpoint.load_factor == 0.0
        and path.final_checkpoint.state_hash == checkpoints[-1].state_hash
        and all(
            child.epoch == parent.epoch + 1
            and child.parent_state_hash == parent.state_hash
            and child.load_factor > parent.load_factor
            for parent, child in zip(checkpoints[:-1], checkpoints[1:], strict=True)
        )
    )

    def iterative_contract(step: Any) -> bool:
        return bool(
            step.metrics.get("iterative_solver_contract_pass") is True
            and step.trial_solution.metrics.get("solver_executed") is True
            and step.trial_solution.metrics.get("contract_pass") is True
        )

    def no_solve_contract(step: Any) -> bool:
        return bool(
            step.metrics.get("no_solve_contract_pass") is True
            and step.trial_solution.metrics.get("terminal_disposition")
            == NO_SOLVE_REACTION_ONLY_DISPOSITION
            and step.trial_solution.metrics.get("solver_executed") is False
            and step.trial_solution.metrics.get("convergence_claim") is False
            and step.trial_solution.metrics.get("active_equation_count") == 0
            and step.trial_solution.metrics.get("residual_gate_passed") is None
            and step.trial_solution.metrics.get("increment_gate_passed") is None
        )

    step_binding_pass = bool(
        chain_pass
        and all(
            step.metrics.get("solver_contract_pass") is True
            and step.metrics.get("section_and_element_parent_binding_passed") is True
            and step.metrics.get("solver_assembly_coordinate_residual_binding_passed")
            is True
            and step.metrics.get("parent_checkpoint_immutable") is True
            and step.metrics.get("regularization_used") is False
            and step.metrics.get("fallback_used") is False
            and (iterative_contract(step) or no_solve_contract(step))
            and step.parent_checkpoint.state_hash == checkpoints[index].state_hash
            and step.accepted_checkpoint.state_hash == checkpoints[index + 1].state_hash
            for index, step in enumerate(path.steps)
        )
    )
    last = path.steps[-1] if path.steps else None
    iterative_terminal_pass = bool(
        last is not None
        and iterative_contract(last)
        and last.metrics.get("residual_gate_passed") is True
        and last.metrics.get("increment_gate_passed") is True
        and _metric_float(last.trial_solution.metrics.get("relative_residual"))
        <= last.trial_solution.config.residual_tolerance
        and _metric_float(last.trial_solution.metrics.get("final_increment_abs_m"))
        <= last.trial_solution.config.increment_tolerance
    )
    no_solve_terminal_pass = bool(last is not None and no_solve_contract(last))
    j5_pass = bool(
        step_binding_pass
        and last is not None
        and _terminal_path_target_passed(path)
        and last.accepted_checkpoint.state_hash == path.final_checkpoint.state_hash
        and (iterative_terminal_pass or no_solve_terminal_pass)
    )
    graph = _validate_general_profile(problem)
    stages: tuple[
        tuple[JStageName, str, tuple[str, ...], Mapping[str, bool], Mapping[str, Any]],
        ...,
    ] = (
        (
            "J1",
            _STAGE_PROFILES["J1"],
            (problem.contract_hash, compilation.compiler_hash),
            MappingProxyType(
                {
                    "connected_graph_passed": True,
                    "multiple_support_semantics_bound": True,
                    "operator_bound": True,
                    "unsupported_member_features_absent": True,
                }
            ),
            {
                "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
                "support_nodes": list(graph["support_nodes"]),
                "branching_nodes": list(graph["branching_nodes"]),
                "maximum_degree": graph["maximum_degree"],
                "free_global_dofs": list(problem.free_global_dofs),
                "member_contract_hashes": [
                    row.element.contract_hash for row in problem.members
                ],
            },
        ),
        (
            "J2",
            _STAGE_PROFILES["J2"],
            (problem.contract_hash,),
            MappingProxyType(
                {
                    "coordinate_scaling_bound": True,
                    "reference_load_bound": True,
                    "prescribed_displacement_bound": True,
                }
            ),
            {
                "coordinate_scaling": STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
                "prescribed_profile": COROTATIONAL_FIBER_FRAME_GENERAL_PRESCRIBED_PROFILE,
                "prescribed_displacements": [
                    list(row) for row in problem.prescribed_displacements
                ],
                "reference_force_scale": problem.reference_force_scale(),
                "reference_external_loads": [
                    list(row) for row in problem.reference_external_loads
                ],
                "residual_formula": RESIDUAL_FORMULA,
            },
        ),
        (
            "J3",
            _STAGE_PROFILES["J3"],
            tuple(row.state_hash for row in checkpoints),
            MappingProxyType(
                {
                    "checkpoint_chain_complete": chain_pass,
                    "rollback_ancestry_bound": chain_pass,
                }
            ),
            {
                "epochs": [row.epoch for row in checkpoints],
                "load_factors": [row.load_factor for row in checkpoints],
                "parents": [row.parent_state_hash for row in checkpoints],
            },
        ),
        (
            "J4",
            _STAGE_PROFILES["J4"],
            tuple(step.accepted_checkpoint.state_hash for step in path.steps),
            MappingProxyType(
                {
                    "solver_assembly_binding_passed": step_binding_pass,
                    "iterative_or_no_solve_contract_passed": step_binding_pass,
                    "no_fallback_or_regularization": step_binding_pass,
                }
            ),
            {
                "step_bindings": [
                    {
                        "parent": step.parent_checkpoint.state_hash,
                        "accepted": step.accepted_checkpoint.state_hash,
                        "assembly_parent": step.trial_assembly.parent_checkpoint_hash,
                        "solver_contract_pass": step.metrics.get(
                            "solver_contract_pass"
                        ),
                        "terminal_disposition": step.metrics.get(
                            "terminal_disposition"
                        ),
                        "solver_executed": step.trial_solution.metrics.get(
                            "solver_executed"
                        ),
                    }
                    for step in path.steps
                ]
            },
        ),
        (
            "J5",
            _STAGE_PROFILES["J5"],
            ((path.final_checkpoint.state_hash,) if path.steps else ()),
            MappingProxyType(
                {
                    "full_load_terminal_passed": j5_pass,
                    "solver_terminal_contract_passed": j5_pass,
                }
            ),
            {
                "terminal_load_factor": path.final_checkpoint.load_factor,
                "control_mode": "load_control",
                "terminal_mode": (
                    "reaction_only_no_solve"
                    if no_solve_terminal_pass
                    else "iterative_newton"
                ),
                "solver_executed": (
                    last.trial_solution.metrics.get("solver_executed")
                    if last is not None
                    else None
                ),
                "convergence_claim": (
                    last.trial_solution.metrics.get("convergence_claim")
                    if last is not None
                    else None
                ),
                "terminal_relative_residual": (
                    last.trial_solution.metrics.get("relative_residual")
                    if last is not None
                    else None
                ),
                "terminal_increment_abs_m": (
                    last.trial_solution.metrics.get("final_increment_abs_m")
                    if last is not None
                    else None
                ),
            },
        ),
    )
    receipts: list[CorotationalFiberFrameJStageReceipt] = []
    for stage, profile, sources, checks, body in stages:
        if not checks or not all(checks.values()):
            _fail(
                f"corotational_general_{stage.lower()}_gate_failed",
                f"/stage_receipts/{stage}",
                f"{stage} source gate did not pass.",
            )
        frozen_body = _freeze_json(
            body,
            path=f"/stage_receipts/{stage}/body",
        )
        if not isinstance(frozen_body, Mapping):
            _fail(
                "corotational_general_stage_body_invalid",
                f"/stage_receipts/{stage}/body",
                "Stage body must be a JSON object.",
            )
        receipts.append(
            CorotationalFiberFrameJStageReceipt(
                stage=stage,
                stage_hash=canonical_hash(
                    _stage_hash_payload(
                        stage=stage,
                        contract_profile=profile,
                        source_hashes=sources,
                        checks=checks,
                        body=frozen_body,
                    )
                ),
                contract_profile=profile,
                source_hashes=sources,
                checks=checks,
                body=frozen_body,
            )
        )
    return tuple(receipts)


def _terminal_path_target_passed(
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    return bool(path.steps and path.final_checkpoint.load_factor == 1.0)


def _stage_hash_payload(
    *,
    stage: JStageName,
    contract_profile: str,
    source_hashes: tuple[str, ...],
    checks: Mapping[str, bool],
    body: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "contract_profile": contract_profile,
        "source_hashes": list(source_hashes),
        "checks": dict(checks),
        "body": _json_value(body),
    }


def _freeze_json(value: Any, *, path: str) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail(
                "corotational_general_stage_body_invalid",
                path,
                "Stage body numbers must be finite.",
            )
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                _fail(
                    "corotational_general_stage_body_invalid",
                    path,
                    "Stage body object keys must be strings.",
                )
            frozen[key] = _freeze_json(item, path=f"{path}/{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, path=f"{path}/{index}")
            for index, item in enumerate(value)
        )
    _fail(
        "corotational_general_stage_body_invalid",
        path,
        "Stage body must contain only finite JSON values.",
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _metric_float(value: Any) -> float:
    if isinstance(value, bool):
        return math.inf
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        return math.inf
    return normalized if math.isfinite(normalized) else math.inf


def _compilation_payload(
    compilation: CorotationalFiberFrameGeneralCompilation,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": compilation.schema_version,
        "compiler_profile": compilation.compiler_profile,
        "model_content_hash": compilation.model_content_hash,
        "problem_contract_hash": compilation.problem_contract_hash,
        "case_id": compilation.case_id,
        "node_count": compilation.node_count,
        "member_count": compilation.member_count,
        "support_node_indices": list(compilation.support_node_indices),
        "branching_node_indices": list(compilation.branching_node_indices),
        "maximum_node_degree": compilation.maximum_node_degree,
        "prescribed_displacements": [
            list(row) for row in compilation.prescribed_displacements
        ],
    }
    if include_hash:
        payload["compiler_hash"] = compilation.compiler_hash
    return payload


def _adapter_payload(
    adapter: CorotationalFiberFrameGeneralJ1J5Adapter,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": adapter.schema_version,
        "compiler_profile": adapter.compiler_profile,
        "compiler_hash": adapter.compiler_hash,
        "authority_profile": adapter.authority_profile,
        "model_content_hash": adapter.model_content_hash,
        "problem_contract_hash": adapter.problem_contract_hash,
        "case_id": adapter.case_id,
        "compilation": adapter._compilation.to_manifest(),
        "terminal_checkpoint_hash": adapter.terminal_checkpoint_hash,
        "terminal_load_factor": adapter.terminal_load_factor,
        "stage_receipts": [row.to_dict() for row in adapter.stage_receipts],
        "authority_axes": dict(adapter.authority_axes),
        "limitations": list(adapter.limitations),
    }
    if include_hash:
        payload["adapter_hash"] = adapter.adapter_hash
    return payload


def _validate_schema(payload: Mapping[str, Any]) -> None:
    errors = sorted(
        _schema_validator().iter_errors(dict(payload)), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("corotational_general_schema_invalid", path, first.message)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("corotational_fiber_frame_general_j1_j5_v1.schema.json")
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError("packaged general corotational schema must be an object")
    return _StrictDraft202012Validator(schema)


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str:
        _fail(
            "corotational_general_hash_invalid",
            path,
            "Expected sha256 digest.",
        )
    text = value.strip()
    digest = text.removeprefix("sha256:")
    if (
        not text.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        _fail("corotational_general_hash_invalid", path, "Expected sha256 digest.")
    return text


def _fail(code: str, path: str, message: str) -> NoReturn:
    raise CorotationalFiberFrameGeneralError(code, path, message)


__all__ = [
    "COROTATIONAL_FIBER_FRAME_GENERAL_AUTHORITY_PROFILE",
    "COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE",
    "COROTATIONAL_FIBER_FRAME_GENERAL_PRESCRIBED_PROFILE",
    "COROTATIONAL_FIBER_FRAME_GENERAL_SCHEMA_VERSION",
    "CorotationalFiberFrameGeneralCompilation",
    "CorotationalFiberFrameGeneralError",
    "CorotationalFiberFrameGeneralJ1J5Adapter",
    "compile_corotational_fiber_frame_general_profile",
    "create_corotational_fiber_frame_general_j1_j5_adapter",
    "validate_corotational_fiber_frame_general_j1_j5_adapter",
    "validate_corotational_fiber_frame_general_manifest",
    "validate_corotational_general_compilation",
]
