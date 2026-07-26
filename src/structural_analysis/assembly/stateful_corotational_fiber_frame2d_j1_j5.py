"""Replay-bound J1-J5 adapter for the corotational one-bay portal candidate.

The adapter establishes topology, scaling, state ancestry, solver binding, and
bounded terminal convergence.  It deliberately does not create numerical or
engineering ResultIR authority; exact recovery and external V&V remain later
promotion gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
    StatefulCorotationalFiberFrame2DProblem,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA


COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-j1-j5-adapter.v1"
)
COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE = (
    "planar_one_bay_one_story_portal_explicit_fiber_section.v1"
)
COROTATIONAL_FIBER_FRAME_J1_J5_AUTHORITY_PROFILE = (
    "non_promoting_bounded_corotational_convergence_candidate.v1"
)

JStageName = Literal["J1", "J2", "J3", "J4", "J5"]
_EXPECTED_STAGES: tuple[JStageName, ...] = ("J1", "J2", "J3", "J4", "J5")
_AUTHORITY_AXES = MappingProxyType(
    {
        "topology": "candidate_bound",
        "member_features": "candidate_bound",
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
    "one_bay_one_story_portal_only",
    "load_or_direct_displacement_control_cpu_dense_or_native_sparse_newton",
    "zero_prescribed_displacement_only",
    "rz_end_release_only",
    "rigid_offsets_in_global_xy_only",
    "uniform_initial_local_axis_dead_member_load_only",
    "exact_engineering_recovery_not_created",
    "external_level2_not_attached",
    "public_capability_not_promoted",
)


class CorotationalFiberFrameJ1J5Error(ValueError):
    """Stable fail-closed adapter/compiler error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class CorotationalFiberFramePortalCompilation:
    schema_version: str
    compiler_profile: str
    compiler_hash: str
    model_content_hash: str
    problem_contract_hash: str
    case_id: str
    node_count: int
    member_count: int
    base_node_indices: tuple[int, int]
    top_node_indices: tuple[int, int]
    _problem: StatefulCorotationalFiberFrame2DProblem = field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_corotational_portal_compilation(self)
        return _compilation_payload(self, include_hash=True)


@dataclass(frozen=True)
class CorotationalFiberFrameJStageReceipt:
    stage: JStageName
    stage_hash: str
    contract_profile: str
    source_hashes: tuple[str, ...]
    checks: Mapping[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_hash": self.stage_hash,
            "contract_profile": self.contract_profile,
            "source_hashes": list(self.source_hashes),
            "checks": dict(self.checks),
        }


@dataclass(frozen=True)
class CorotationalFiberFrameJ1J5Adapter:
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
    _compilation: CorotationalFiberFramePortalCompilation = field(
        repr=False, compare=False
    )
    _path: StatefulCorotationalFiberFrame2DLoadPathResult = field(
        repr=False, compare=False
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_corotational_fiber_frame_j1_j5_adapter(self)
        return _adapter_payload(self, include_hash=True)


def compile_corotational_fiber_frame_portal_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
    *,
    model_content_hash: str,
) -> CorotationalFiberFramePortalCompilation:
    if type(problem) is not StatefulCorotationalFiberFrame2DProblem:
        _fail(
            "corotational_portal_problem_type_invalid",
            "/problem",
            "Expected exact StatefulCorotationalFiberFrame2DProblem.",
        )
    model_hash = _require_hash(model_content_hash, "/model_content_hash")
    base_nodes, top_nodes = _validate_portal_profile(problem)
    provisional = CorotationalFiberFramePortalCompilation(
        schema_version=COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION,
        compiler_profile=COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE,
        compiler_hash="sha256:" + "0" * 64,
        model_content_hash=model_hash,
        problem_contract_hash=problem.contract_hash,
        case_id=problem.case_id,
        node_count=len(problem.node_coordinates_m),
        member_count=len(problem.members),
        base_node_indices=base_nodes,
        top_node_indices=top_nodes,
        _problem=problem,
    )
    compiled = replace(
        provisional,
        compiler_hash=canonical_hash(
            _compilation_payload(provisional, include_hash=False)
        ),
    )
    return validate_corotational_portal_compilation(compiled)


def create_corotational_fiber_frame_j1_j5_adapter(
    compilation: CorotationalFiberFramePortalCompilation,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> CorotationalFiberFrameJ1J5Adapter:
    validate_corotational_portal_compilation(compilation)
    receipts = _build_stage_receipts(compilation, path)
    provisional = CorotationalFiberFrameJ1J5Adapter(
        schema_version=COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION,
        adapter_hash="sha256:" + "0" * 64,
        compiler_profile=compilation.compiler_profile,
        compiler_hash=compilation.compiler_hash,
        authority_profile=COROTATIONAL_FIBER_FRAME_J1_J5_AUTHORITY_PROFILE,
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
    return validate_corotational_fiber_frame_j1_j5_adapter(adapter)


def validate_corotational_portal_compilation(
    compilation: CorotationalFiberFramePortalCompilation,
) -> CorotationalFiberFramePortalCompilation:
    if type(compilation) is not CorotationalFiberFramePortalCompilation:
        _fail(
            "corotational_portal_compilation_type_invalid",
            "/",
            "Expected exact portal compilation type.",
        )
    if (
        compilation.schema_version != COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION
        or compilation.compiler_profile
        != COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE
    ):
        _fail(
            "corotational_portal_compiler_profile_invalid",
            "/compiler_profile",
            "Compiler schema/profile is fixed by v1.",
        )
    problem = compilation._problem
    if problem.contract_hash != compilation.problem_contract_hash:
        _fail(
            "corotational_portal_problem_hash_mismatch",
            "/problem_contract_hash",
            "Compiled problem hash differs from retained source.",
        )
    base_nodes, top_nodes = _validate_portal_profile(problem)
    if (
        compilation.case_id != problem.case_id
        or compilation.node_count != len(problem.node_coordinates_m)
        or compilation.member_count != len(problem.members)
        or compilation.base_node_indices != base_nodes
        or compilation.top_node_indices != top_nodes
    ):
        _fail(
            "corotational_portal_compilation_binding_invalid",
            "/",
            "Compilation metadata differs from the retained portal problem.",
        )
    expected_hash = canonical_hash(
        _compilation_payload(compilation, include_hash=False)
    )
    if compilation.compiler_hash != expected_hash:
        _fail(
            "corotational_portal_compiler_hash_mismatch",
            "/compiler_hash",
            "Compiler hash differs from canonical content.",
        )
    return compilation


def validate_corotational_fiber_frame_j1_j5_adapter(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> CorotationalFiberFrameJ1J5Adapter:
    if type(adapter) is not CorotationalFiberFrameJ1J5Adapter:
        _fail(
            "corotational_j1_j5_adapter_type_invalid",
            "/",
            "Expected exact adapter type.",
        )
    compilation = validate_corotational_portal_compilation(adapter._compilation)
    if (
        adapter.schema_version != COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION
        or adapter.compiler_profile != compilation.compiler_profile
        or adapter.compiler_hash != compilation.compiler_hash
        or adapter.authority_profile != COROTATIONAL_FIBER_FRAME_J1_J5_AUTHORITY_PROFILE
        or adapter.model_content_hash != compilation.model_content_hash
        or adapter.problem_contract_hash != compilation.problem_contract_hash
        or adapter.case_id != compilation.case_id
        or dict(adapter.authority_axes) != dict(_AUTHORITY_AXES)
        or adapter.limitations != _LIMITATIONS
    ):
        _fail(
            "corotational_j1_j5_adapter_binding_invalid",
            "/",
            "Adapter metadata or claim boundary differs from v1.",
        )
    replayed = _build_stage_receipts(compilation, adapter._path)
    if adapter.stage_receipts != replayed:
        _fail(
            "corotational_j1_j5_replay_mismatch",
            "/stage_receipts",
            "J1-J5 receipts differ from replayed retained sources.",
        )
    if tuple(row.stage for row in adapter.stage_receipts) != _EXPECTED_STAGES:
        _fail(
            "corotational_j1_j5_stage_order_invalid",
            "/stage_receipts",
            "Adapter must contain J1 through J5 exactly once and in order.",
        )
    if (
        adapter.terminal_checkpoint_hash != adapter._path.final_checkpoint.state_hash
        or adapter.terminal_load_factor != adapter._path.final_checkpoint.load_factor
        or not _terminal_path_target_passed(adapter._path)
    ):
        _fail(
            "corotational_j5_terminal_binding_invalid",
            "/terminal_checkpoint_hash",
            "J5 requires the exact full-load or displacement-control terminal checkpoint.",
        )
    expected_hash = canonical_hash(_adapter_payload(adapter, include_hash=False))
    if adapter.adapter_hash != expected_hash:
        _fail(
            "corotational_j1_j5_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash differs from canonical content.",
        )
    payload = _adapter_payload(adapter, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("corotational_j1_j5_schema_invalid", path, first.message)
    return adapter


def validate_corotational_fiber_frame_j1_j5_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    errors = sorted(
        _schema_validator().iter_errors(normalized), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("corotational_j1_j5_schema_invalid", path, first.message)
    claimed = str(normalized["adapter_hash"])
    body = dict(normalized)
    body.pop("adapter_hash")
    if claimed != canonical_hash(body):
        _fail(
            "corotational_j1_j5_adapter_hash_mismatch",
            "/adapter_hash",
            "Manifest hash differs from canonical content.",
        )
    return normalized


def _validate_portal_profile(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> tuple[tuple[int, int], tuple[int, int]]:
    coordinates = problem.node_coordinates_m
    if len(coordinates) != 4 or len(problem.members) != 3:
        _fail(
            "corotational_portal_topology_count_invalid",
            "/problem",
            "The v1 profile requires four nodes and three members.",
        )
    ys = sorted({row[1] for row in coordinates})
    xs = sorted({row[0] for row in coordinates})
    if len(xs) != 2 or len(ys) != 2 or xs[0] == xs[1] or ys[0] == ys[1]:
        _fail(
            "corotational_portal_geometry_invalid",
            "/node_coordinates_m",
            "Nodes must form a non-degenerate axis-aligned one-bay rectangle.",
        )
    expected_coordinates = {(x, y) for x in xs for y in ys}
    if set(coordinates) != expected_coordinates:
        _fail(
            "corotational_portal_geometry_invalid",
            "/node_coordinates_m",
            "Nodes must occupy all four portal rectangle corners.",
        )
    base = tuple(index for index, row in enumerate(coordinates) if row[1] == ys[0])
    top = tuple(index for index, row in enumerate(coordinates) if row[1] == ys[1])
    if len(base) != 2 or len(top) != 2:
        _fail(
            "corotational_portal_geometry_invalid",
            "/node_coordinates_m",
            "Invalid portal levels.",
        )
    expected_fixed = tuple(sorted(3 * node + dof for node in base for dof in range(3)))
    if problem.fixed_global_dofs != expected_fixed:
        _fail(
            "corotational_portal_support_invalid",
            "/fixed_global_dofs",
            "Both base nodes must restrain UX, UY and RZ exactly.",
        )
    if any(value != 0.0 for _dof, value in problem.prescribed_displacements):
        _fail(
            "corotational_portal_prescribed_displacement_invalid",
            "/prescribed_displacements",
            "The portal v1 profile requires zero prescribed displacement.",
        )
    by_coordinate = {row: index for index, row in enumerate(coordinates)}
    expected_edges = {
        frozenset((by_coordinate[(xs[0], ys[0])], by_coordinate[(xs[0], ys[1])])),
        frozenset((by_coordinate[(xs[1], ys[0])], by_coordinate[(xs[1], ys[1])])),
        frozenset((by_coordinate[(xs[0], ys[1])], by_coordinate[(xs[1], ys[1])])),
    }
    actual_edges = {frozenset((row.node_i, row.node_j)) for row in problem.members}
    if actual_edges != expected_edges:
        _fail(
            "corotational_portal_connectivity_invalid",
            "/members",
            "Members must be the two columns and one top beam.",
        )
    top_set = set(top)
    if any(dof // 3 not in top_set for dof, _value in problem.reference_external_loads):
        _fail(
            "corotational_portal_load_location_invalid",
            "/reference_external_loads",
            "The v1 profile accepts proportional nodal loads at top nodes only.",
        )
    return (base[0], base[1]), (top[0], top[1])


def _build_stage_receipts(
    compilation: CorotationalFiberFramePortalCompilation,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> tuple[CorotationalFiberFrameJStageReceipt, ...]:
    if type(path) is not StatefulCorotationalFiberFrame2DLoadPathResult:
        _fail(
            "corotational_j1_j5_path_type_invalid",
            "/path",
            "Expected exact corotational load-path result.",
        )
    problem = compilation._problem
    displacement_control = _is_displacement_control_path(path)
    checkpoints = (path.initial_checkpoint,) + tuple(
        step.accepted_checkpoint for step in path.steps if step.committed
    )
    for checkpoint in checkpoints:
        validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
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
            and (displacement_control or child.load_factor > parent.load_factor)
            for parent, child in zip(checkpoints[:-1], checkpoints[1:], strict=True)
        )
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
            and step.parent_checkpoint.state_hash == checkpoints[index].state_hash
            and step.accepted_checkpoint.state_hash == checkpoints[index + 1].state_hash
            for index, step in enumerate(path.steps)
        )
    )
    member_feature_binding_pass = bool(
        step_binding_pass
        and all(
            len(step.metrics.get("member_feature_response_hashes", ()))
            == len(problem.members)
            and float(step.metrics.get("release_equilibrium_max_abs_kn_m", math.inf))
            <= 1.0e-10 * problem.reference_force_scale()
            for step in path.steps
        )
    )
    last = path.steps[-1] if path.steps else None
    j5_pass = bool(
        step_binding_pass
        and last is not None
        and _terminal_path_target_passed(path)
        and last.accepted_checkpoint.state_hash == path.final_checkpoint.state_hash
        and last.metrics.get("residual_gate_passed") is True
        and last.metrics.get("increment_gate_passed") is True
        and last.trial_solution.metrics.get("contract_pass") is True
        and float(last.trial_solution.metrics.get("relative_residual", math.inf))
        <= last.trial_solution.config.residual_tolerance
        and float(last.trial_solution.metrics.get("final_increment_abs_m", math.inf))
        <= last.trial_solution.config.increment_tolerance
    )
    stage_inputs: tuple[
        tuple[JStageName, str, tuple[str, ...], Mapping[str, bool], Mapping[str, Any]],
        ...,
    ] = (
        (
            "J1",
            "corotational_portal_topology_and_operator_binding.v1",
            (problem.contract_hash, compilation.compiler_hash),
            MappingProxyType(
                {
                    "portal_profile_passed": True,
                    "operator_bound": True,
                    "member_feature_contracts_bound": True,
                }
            ),
            {
                "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
                "member_contract_hashes": [
                    row.element.contract_hash for row in problem.members
                ],
                "member_feature_contract_hashes": [
                    row.features.contract_hash for row in problem.members
                ],
                "free_global_dofs": list(problem.free_global_dofs),
            },
        ),
        (
            "J2",
            "corotational_physical_equation_and_coordinate_scaling.v1",
            (problem.contract_hash,),
            MappingProxyType(
                {
                    "coordinate_scaling_bound": True,
                    "reference_load_bound": True,
                    "member_load_semantics_bound": True,
                }
            ),
            {
                "coordinate_scaling": STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
                "rotation_coordinate_scale_m": problem.rotation_coordinate_scale_m,
                "reference_force_scale": problem.reference_force_scale(),
                "member_feature_contracts": [
                    row.features.to_dict() for row in problem.members
                ],
                "residual_formula": RESIDUAL_FORMULA,
            },
        ),
        (
            "J3",
            "corotational_committed_checkpoint_chain.v1",
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
            "corotational_solver_assembly_state_binding.v1",
            tuple(step.accepted_checkpoint.state_hash for step in path.steps),
            MappingProxyType(
                {
                    "solver_assembly_binding_passed": step_binding_pass,
                    "no_fallback_or_regularization": step_binding_pass,
                    "member_feature_equilibrium_bound": member_feature_binding_pass,
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
                        "member_feature_response_hashes": step.metrics.get(
                            "member_feature_response_hashes"
                        ),
                        "release_equilibrium_max_abs_kn_m": step.metrics.get(
                            "release_equilibrium_max_abs_kn_m"
                        ),
                    }
                    for step in path.steps
                ]
            },
        ),
        (
            "J5",
            (
                "corotational_terminal_displacement_control_convergence.v1"
                if displacement_control
                else "corotational_full_load_terminal_convergence.v1"
            ),
            ((path.final_checkpoint.state_hash,) if path.steps else ()),
            MappingProxyType(
                (
                    {
                        "displacement_control_terminal_passed": j5_pass,
                        "residual_and_increment_gates_passed": j5_pass,
                    }
                    if displacement_control
                    else {
                        "full_load_terminal_passed": j5_pass,
                        "residual_and_increment_gates_passed": j5_pass,
                    }
                )
            ),
            {
                "terminal_load_factor": path.final_checkpoint.load_factor,
                "control_mode": (
                    "displacement_control" if displacement_control else "load_control"
                ),
                "controlled_global_dof": (
                    last.metrics.get("controlled_global_dof")
                    if displacement_control and last is not None
                    else None
                ),
                "target_control_displacement": (
                    last.metrics.get("target_control_displacement")
                    if displacement_control and last is not None
                    else None
                ),
                "terminal_control_displacement": (
                    last.metrics.get("terminal_control_displacement")
                    if displacement_control and last is not None
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
                "residual_tolerance": (
                    last.trial_solution.config.residual_tolerance
                    if last is not None
                    else None
                ),
                "increment_tolerance_m": (
                    last.trial_solution.config.increment_tolerance
                    if last is not None
                    else None
                ),
            },
        ),
    )
    receipts: list[CorotationalFiberFrameJStageReceipt] = []
    for stage, profile, sources, checks, body in stage_inputs:
        if not checks or not all(checks.values()):
            _fail(
                f"corotational_{stage.lower()}_gate_failed",
                f"/stage_receipts/{stage}",
                f"{stage} source gate did not pass.",
            )
        stage_hash = canonical_hash(
            {
                "stage": stage,
                "contract_profile": profile,
                "source_hashes": list(sources),
                "checks": dict(checks),
                "body": body,
            }
        )
        receipts.append(
            CorotationalFiberFrameJStageReceipt(
                stage=stage,
                stage_hash=stage_hash,
                contract_profile=profile,
                source_hashes=sources,
                checks=checks,
            )
        )
    return tuple(receipts)


def _is_displacement_control_path(
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    return bool(
        path.steps
        and all(
            step.metrics.get("control_mode") == "displacement_control"
            for step in path.steps
        )
    )


def _terminal_path_target_passed(
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    if not path.steps:
        return False
    if not _is_displacement_control_path(path):
        return path.final_checkpoint.load_factor == 1.0
    last = path.steps[-1]
    dof = last.metrics.get("controlled_global_dof")
    target = last.metrics.get("target_control_displacement")
    terminal_target = last.metrics.get("terminal_control_displacement")
    return bool(
        type(dof) is int
        and isinstance(target, (int, float))
        and isinstance(terminal_target, (int, float))
        and float(target) == float(terminal_target)
        and last.metrics.get("control_target_reached") is True
        and path.final_checkpoint.global_displacements[dof] == float(target)
    )


def _compilation_payload(
    compilation: CorotationalFiberFramePortalCompilation,
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
        "base_node_indices": list(compilation.base_node_indices),
        "top_node_indices": list(compilation.top_node_indices),
    }
    if include_hash:
        payload["compiler_hash"] = compilation.compiler_hash
    return payload


def _adapter_payload(
    adapter: CorotationalFiberFrameJ1J5Adapter,
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
        "terminal_checkpoint_hash": adapter.terminal_checkpoint_hash,
        "terminal_load_factor": adapter.terminal_load_factor,
        "stage_receipts": [row.to_dict() for row in adapter.stage_receipts],
        "authority_axes": dict(adapter.authority_axes),
        "limitations": list(adapter.limitations),
    }
    if include_hash:
        payload["adapter_hash"] = adapter.adapter_hash
    return payload


def _require_hash(value: Any, path: str) -> str:
    text = str(value or "").strip()
    digest = text.removeprefix("sha256:")
    if (
        not text.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        _fail("corotational_hash_invalid", path, "Expected lowercase sha256 digest.")
    return text


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("corotational_fiber_frame_j1_j5_adapter_v1.schema.json")
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Packaged corotational J1-J5 schema must be an object.")
    return Draft202012Validator(payload)


def _fail(code: str, path: str, message: str) -> NoReturn:
    raise CorotationalFiberFrameJ1J5Error(code, path, message)


__all__ = [
    "COROTATIONAL_FIBER_FRAME_J1_J5_AUTHORITY_PROFILE",
    "COROTATIONAL_FIBER_FRAME_J1_J5_SCHEMA_VERSION",
    "COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE",
    "CorotationalFiberFrameJ1J5Adapter",
    "CorotationalFiberFrameJ1J5Error",
    "CorotationalFiberFrameJStageReceipt",
    "CorotationalFiberFramePortalCompilation",
    "compile_corotational_fiber_frame_portal_profile",
    "create_corotational_fiber_frame_j1_j5_adapter",
    "validate_corotational_fiber_frame_j1_j5_adapter",
    "validate_corotational_fiber_frame_j1_j5_manifest",
    "validate_corotational_portal_compilation",
]
