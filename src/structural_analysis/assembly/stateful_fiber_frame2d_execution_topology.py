"""Non-authoritative six-DOF topology for the bounded stateful fiber frame.

The current fiber-frame solver owns a three-DOF-per-node coordinate space
``[UX, UY, RZ]`` and uses a length scale to express rotations as generalized
length coordinates.  Engine v2 ``ExecutionPlan v1`` is intentionally not reused
here because its manifest is explicitly linear-static and binds StateIR v1's
``stateless_linear_elastic`` profile.

This module therefore introduces an additive nonlinear topology-plan candidate
and a solver-coordinate scaling receipt.  They freeze node/member ordering,
canonical six-DOF physical equations, active/inactive partitions, sparse
pattern, source identities, and the exact physical/generalized coordinate map.
They do not run a solver or grant convergence, numerical-result, engineering,
design, release, or commercial authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION,
    STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.corotational_frame2d_member_features import (
    consistent_uniform_load_element_global,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-execution-topology-plan.v1"
)
FIBER_FRAME_SOLVER_COORDINATE_SCALING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-solver-coordinate-scaling.v1"
)
FIBER_FRAME_EXECUTION_TOPOLOGY_CAPABILITY_PROFILE = (
    "stateful_fiber_frame2d_nonlinear_kinematics.v1"
)
FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE = (
    "non_authoritative_nonlinear_execution_topology.v1"
)
FIBER_FRAME_SOLVER_COORDINATE_SCALING_PROFILE = "ux_m_uy_m_rz_generalized_length.v1"
FIBER_FRAME_KINEMATIC_BINDING_DECISION = (
    "typed_external_constitutive_kinematic_binding.v1"
)
FIBER_FRAME_PHYSICAL_DOF_COMPONENTS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
FIBER_FRAME_SOLVER_DOF_COMPONENTS = ("UX", "UY", "RZ")
FIBER_FRAME_ACTIVE_PHYSICAL_COMPONENT_INDICES = (0, 1, 5)
FIBER_FRAME_INACTIVE_PHYSICAL_COMPONENT_INDICES = (2, 3, 4)
FIBER_FRAME_EXECUTION_TOPOLOGY_CLAIM_BOUNDARY = MappingProxyType(
    {
        "problem_contract_bound": True,
        "canonical_six_dof_topology_bound": True,
        "solver_three_dof_mapping_bound": True,
        "solver_coordinate_scaling_bound": True,
        "reference_load_mapping_bound": True,
        "physical_equation_scaling_bound": False,
        "nonlinear_state_history_bound": False,
        "material_state_projection_chain_bound": False,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "reaction_or_member_force_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1

FiberFrame2DTopologyProblem = (
    StatefulFiberFrame2DProblem | StatefulCorotationalFiberFrame2DProblem
)

_PLAN_ARRAY_SPECS = (
    ("node_coordinates_xy_m", "<f8"),
    ("node_dof_indices", "<i4"),
    ("member_physical_global_dofs", "<i4"),
    ("member_active_physical_dofs", "<i4"),
    ("member_solver_global_dofs", "<i4"),
    ("solver_to_physical_global_dofs", "<i4"),
    ("physical_to_solver_global_dofs", "<i4"),
    ("inactive_physical_dofs", "<i4"),
    ("authored_fixed_physical_dofs", "<i4"),
    ("constrained_physical_dofs", "<i4"),
    ("free_physical_dofs", "<i4"),
    ("constrained_solver_dofs", "<i4"),
    ("free_solver_dofs", "<i4"),
    ("reference_external_load_physical_6dof", "<f8"),
    ("csr_row_ptr", "<i8"),
    ("csr_column_indices", "<i4"),
)
_PLAN_ARRAY_NAMES = tuple(name for name, _dtype in _PLAN_ARRAY_SPECS)
_SCALING_ARRAY_SPECS = (
    ("physical_from_generalized_scale", "<f8"),
    ("generalized_from_physical_scale", "<f8"),
    ("reference_load_physical_solver_order", "<f8"),
    ("reference_load_generalized_solver_order", "<f8"),
)
_SCALING_ARRAY_NAMES = tuple(name for name, _dtype in _SCALING_ARRAY_SPECS)
_SCALING_MAPPING = MappingProxyType(
    {
        "generalized_to_physical": "physical_from_generalized_scale",
        "physical_to_generalized": "generalized_from_physical_scale",
        "physical_reference_load": "reference_load_physical_solver_order",
        "generalized_reference_load": "reference_load_generalized_solver_order",
        "residual_transform": (
            "r_generalized=physical_from_generalized_scale*r_physical"
        ),
        "jacobian_transform": "K_generalized=S*K_physical*S",
    }
)
_CONSTRAINT_PARTITION_MANIFEST = MappingProxyType(
    {
        "inactive_physical_dofs": "inactive_physical_dofs",
        "authored_fixed_physical_dofs": "authored_fixed_physical_dofs",
        "constrained_physical_dofs": "constrained_physical_dofs",
        "free_physical_dofs": "free_physical_dofs",
        "constrained_solver_dofs": "constrained_solver_dofs",
        "free_solver_dofs": "free_solver_dofs",
    }
)
_SPARSE_PATTERN_MANIFEST = MappingProxyType(
    {
        "format": "csr",
        "scope": "canonical_physical_equations",
        "row_ptr": "csr_row_ptr",
        "column_indices": "csr_column_indices",
        "inactive_rows": "diagonal_only",
    }
)


class FiberFrameExecutionTopologyError(ValueError):
    """Stable fail-closed compiler/topology error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameTopologyArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class FiberFrameSolverCoordinateScalingReceipt:
    schema_version: str
    scaling_hash: str
    authority_profile: str
    scaling_profile: str
    problem_contract_hash: str
    rotation_coordinate_scale_m: float
    solver_dof_count: int
    source_commitment_hash: str
    descriptors: tuple[FiberFrameTopologyArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown solver-coordinate scaling array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_solver_coordinate_scaling(self)
        return _scaling_payload(self, include_scaling_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearExecutionTopologyPlan:
    schema_version: str
    plan_id: str
    plan_hash: str
    authority_profile: str
    capability_profile: str
    kinematic_binding_decision: str
    problem_contract_hash: str
    model_ir_content_hash: str
    case_id: str
    node_ids: tuple[str, ...]
    member_ids: tuple[str, ...]
    node_count: int
    member_count: int
    physical_dof_count: int
    solver_dof_count: int
    source_identity_hash: str
    numeric_buffer_hash: str
    entity_mapping_hash: str
    operator_hash: str
    topology_hash: str
    solver_coordinate_scaling_hash: str
    descriptors: tuple[FiberFrameTopologyArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    solver_coordinate_scaling: FiberFrameSolverCoordinateScalingReceipt
    extensions: Mapping[str, Any]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown fiber-frame topology array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_execution_topology_plan(self)
        return _plan_payload(self, include_plan_hash=True)


def compile_stateful_fiber_frame2d_execution_topology(
    problem: FiberFrame2DTopologyProblem,
    *,
    model_ir_content_hash: str,
    node_ids: Sequence[str] | None = None,
    plan_id: str | None = None,
) -> FiberFrameNonlinearExecutionTopologyPlan:
    """Compile a bounded frame problem into canonical six-DOF topology.

    The returned plan is intentionally distinct from Engine v2 ExecutionPlan v1.
    It freezes nonlinear kinematic topology only and carries no result authority.
    """

    if not _is_supported_problem(problem):
        _fail(
            "fiber_frame_topology_problem_type_invalid",
            "/problem",
            "Expected an exact supported stateful planar fiber-frame problem.",
        )
    model_hash = _require_hash(model_ir_content_hash, "/model_ir_content_hash")
    nodes = _normalize_node_ids(node_ids, len(problem.node_coordinates_m))
    members = _stable_id_tuple(
        tuple(member.member_id for member in problem.members),
        "/entity_order/member_ids",
    )
    if len(set(members)) != len(members):
        _fail(
            "fiber_frame_topology_member_id_duplicate",
            "/entity_order/member_ids",
            "Member IDs must be unique.",
        )

    arrays = _compile_plan_arrays(problem)
    scaling = _create_solver_coordinate_scaling(problem)
    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _PLAN_ARRAY_NAMES
    )
    source_rows = [
        _member_source_row(index, member)
        for index, member in enumerate(problem.members)
    ]
    source_identity_hash = canonical_hash(
        {
            "problem_contract_hash": problem.contract_hash,
            "case_id": problem.case_id,
            "node_ids": list(nodes),
            "node_coordinates_xy_m_data_hash": array_data_hash(
                arrays["node_coordinates_xy_m"]
            ),
            "members": source_rows,
            "fixed_solver_dofs": list(problem.fixed_global_dofs),
            "reference_external_loads": _reference_external_load_source_rows(problem),
            "rotation_coordinate_scale_m": problem.rotation_coordinate_scale_m,
        }
    )
    numeric_buffer_hash = canonical_hash(
        {
            "node_coordinates_xy_m": _descriptor_payload(
                _descriptor_by_name(descriptors, "node_coordinates_xy_m")
            ),
            "reference_external_load_physical_6dof": _descriptor_payload(
                _descriptor_by_name(
                    descriptors,
                    "reference_external_load_physical_6dof",
                )
            ),
            "solver_coordinate_scaling_hash": scaling.scaling_hash,
        }
    )
    entity_mapping_hash = canonical_hash(
        {
            "node_ids": list(nodes),
            "member_ids": list(members),
            "member_rows": source_rows,
            "solver_to_physical_global_dofs": _descriptor_payload(
                _descriptor_by_name(
                    descriptors,
                    "solver_to_physical_global_dofs",
                )
            ),
            "member_active_physical_dofs": _descriptor_payload(
                _descriptor_by_name(
                    descriptors,
                    "member_active_physical_dofs",
                )
            ),
        }
    )
    operator_hash = canonical_hash(
        {
            "source_schema_version": _problem_schema_version(problem),
            "problem_contract_hash": problem.contract_hash,
            "transformation": _problem_transformation(problem),
            "member_element_contract_hashes": [
                member.element.contract_hash for member in problem.members
            ],
            **_member_feature_operator_binding(problem),
            "residual_sign": "internal_minus_external",
        }
    )
    topology_hash = canonical_hash(
        {
            descriptor.name: descriptor.content_hash
            for descriptor in descriptors
            if descriptor.name
            not in {
                "node_coordinates_xy_m",
                "reference_external_load_physical_6dof",
            }
        }
    )
    normalized_plan_id = _require_stable_id(
        plan_id or (f"fftopology.{problem.contract_hash.removeprefix('sha256:')[:16]}"),
        "/plan_id",
    )
    provisional = FiberFrameNonlinearExecutionTopologyPlan(
        schema_version=FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
        plan_id=normalized_plan_id,
        plan_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE,
        capability_profile=FIBER_FRAME_EXECUTION_TOPOLOGY_CAPABILITY_PROFILE,
        kinematic_binding_decision=FIBER_FRAME_KINEMATIC_BINDING_DECISION,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=model_hash,
        case_id=problem.case_id,
        node_ids=nodes,
        member_ids=members,
        node_count=len(nodes),
        member_count=len(members),
        physical_dof_count=6 * len(nodes),
        solver_dof_count=3 * len(nodes),
        source_identity_hash=source_identity_hash,
        numeric_buffer_hash=numeric_buffer_hash,
        entity_mapping_hash=entity_mapping_hash,
        operator_hash=operator_hash,
        topology_hash=topology_hash,
        solver_coordinate_scaling_hash=scaling.scaling_hash,
        descriptors=descriptors,
        _arrays=arrays,
        solver_coordinate_scaling=scaling,
        extensions=MappingProxyType({}),
    )
    plan = replace(
        provisional,
        plan_hash=canonical_hash(_plan_payload(provisional, include_plan_hash=False)),
    )
    validate_fiber_frame_execution_topology_plan(plan)
    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    return plan


def validate_fiber_frame_execution_topology_plan(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> FiberFrameNonlinearExecutionTopologyPlan:
    """Validate all self-contained topology, mapping, and hash invariants."""

    if type(plan) is not FiberFrameNonlinearExecutionTopologyPlan:
        _fail(
            "fiber_frame_topology_plan_type_invalid",
            "/",
            "Expected FiberFrameNonlinearExecutionTopologyPlan.",
        )
    if plan.schema_version != FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION:
        _fail(
            "fiber_frame_topology_schema_invalid",
            "/schema_version",
            "Unsupported fiber-frame execution-topology schema.",
        )
    if plan.authority_profile != FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_topology_authority_profile_invalid",
            "/authority_profile",
            "Execution topology cannot acquire result authority.",
        )
    if plan.capability_profile != FIBER_FRAME_EXECUTION_TOPOLOGY_CAPABILITY_PROFILE:
        _fail(
            "fiber_frame_topology_capability_profile_invalid",
            "/capability_profile",
            "Unsupported nonlinear topology capability profile.",
        )
    if plan.kinematic_binding_decision != FIBER_FRAME_KINEMATIC_BINDING_DECISION:
        _fail(
            "fiber_frame_topology_kinematic_decision_invalid",
            "/kinematic_binding_decision",
            "The StateIR/kinematic binding decision changed.",
        )
    _require_stable_id(plan.plan_id, "/plan_id")
    _require_nonempty_string(plan.case_id, "/case_id")
    for path, value in (
        ("/plan_hash", plan.plan_hash),
        ("/problem_contract_hash", plan.problem_contract_hash),
        ("/model_ir_content_hash", plan.model_ir_content_hash),
        ("/source_identity_hash", plan.source_identity_hash),
        ("/numeric_buffer_hash", plan.numeric_buffer_hash),
        ("/entity_mapping_hash", plan.entity_mapping_hash),
        ("/operator_hash", plan.operator_hash),
        ("/topology_hash", plan.topology_hash),
        (
            "/solver_coordinate_scaling_hash",
            plan.solver_coordinate_scaling_hash,
        ),
    ):
        _require_hash(value, path)
    nodes = _stable_id_tuple(plan.node_ids, "/entity_order/node_ids")
    members = _stable_id_tuple(plan.member_ids, "/entity_order/member_ids")
    if len(set(nodes)) != len(nodes) or len(set(members)) != len(members):
        _fail(
            "fiber_frame_topology_entity_order_duplicate",
            "/entity_order",
            "Node and member IDs must be unique.",
        )
    for path, value, expected in (
        ("/node_count", plan.node_count, len(nodes)),
        ("/member_count", plan.member_count, len(members)),
        ("/physical_dof_count", plan.physical_dof_count, 6 * len(nodes)),
        ("/solver_dof_count", plan.solver_dof_count, 3 * len(nodes)),
    ):
        normalized = _require_index(value, path)
        if normalized != expected:
            _fail(
                "fiber_frame_topology_count_mismatch",
                path,
                f"Expected {expected}.",
            )
    if plan.node_count < 2 or plan.member_count < 1:
        _fail(
            "fiber_frame_topology_entity_count_invalid",
            "/entity_order",
            "Topology requires at least two nodes and one member.",
        )
    _validate_array_map(
        plan._arrays,
        plan.descriptors,
        _PLAN_ARRAY_SPECS,
        "/arrays",
    )
    _validate_plan_array_semantics(plan)
    scaling = validate_fiber_frame_solver_coordinate_scaling(
        plan.solver_coordinate_scaling
    )
    if scaling.scaling_hash != plan.solver_coordinate_scaling_hash:
        _fail(
            "fiber_frame_topology_scaling_hash_mismatch",
            "/solver_coordinate_scaling_hash",
            "Plan does not bind the retained scaling receipt.",
        )
    if scaling.problem_contract_hash != plan.problem_contract_hash:
        _fail(
            "fiber_frame_topology_scaling_problem_mismatch",
            "/solver_coordinate_scaling/problem_contract_hash",
            "Scaling receipt belongs to another problem.",
        )
    if scaling.solver_dof_count != plan.solver_dof_count:
        _fail(
            "fiber_frame_topology_scaling_dof_count_mismatch",
            "/solver_coordinate_scaling/solver_dof_count",
            "Scaling receipt has a different solver equation count.",
        )
    expected_topology_hash = canonical_hash(
        {
            descriptor.name: descriptor.content_hash
            for descriptor in plan.descriptors
            if descriptor.name
            not in {
                "node_coordinates_xy_m",
                "reference_external_load_physical_6dof",
            }
        }
    )
    if plan.topology_hash != expected_topology_hash:
        _fail(
            "fiber_frame_topology_hash_mismatch",
            "/topology_hash",
            "Topology hash does not match retained index arrays.",
        )
    if not isinstance(plan.extensions, MappingProxyType) or plan.extensions:
        _fail(
            "fiber_frame_topology_extensions_invalid",
            "/extensions",
            "Topology-plan v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_plan_payload(plan, include_plan_hash=False))
    if plan.plan_hash != expected_hash:
        _fail(
            "fiber_frame_topology_plan_hash_mismatch",
            "/plan_hash",
            "Plan hash does not match canonical content.",
        )
    return plan


def validate_fiber_frame_execution_topology_against_problem(
    problem: FiberFrame2DTopologyProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> FiberFrameNonlinearExecutionTopologyPlan:
    """Recompile source-dependent identities and compare exact array bytes."""

    validate_fiber_frame_execution_topology_plan(plan)
    if not _is_supported_problem(problem):
        _fail(
            "fiber_frame_topology_problem_type_invalid",
            "/problem",
            "Expected an exact supported stateful planar fiber-frame problem.",
        )
    if plan.problem_contract_hash != problem.contract_hash:
        _fail(
            "fiber_frame_topology_problem_contract_mismatch",
            "/problem_contract_hash",
            "Plan does not bind the supplied frame problem.",
        )
    if plan.case_id != problem.case_id:
        _fail(
            "fiber_frame_topology_case_id_mismatch",
            "/entity_order/case_id",
            "Plan case identity does not match the supplied problem.",
        )
    expected_member_ids = tuple(member.member_id for member in problem.members)
    if plan.member_ids != expected_member_ids:
        _fail(
            "fiber_frame_topology_member_ids_mismatch",
            "/entity_order/member_ids",
            "Plan member identity/order does not match the supplied problem.",
        )
    expected_arrays = _compile_plan_arrays(problem)
    for name in _PLAN_ARRAY_NAMES:
        if not np.array_equal(plan.array(name), expected_arrays[name]):
            _fail(
                "fiber_frame_topology_source_array_mismatch",
                f"/arrays/{name}",
                "Retained plan array does not match the supplied problem.",
            )
    expected_scaling = _create_solver_coordinate_scaling(problem)
    if plan.solver_coordinate_scaling.to_manifest() != expected_scaling.to_manifest():
        _fail(
            "fiber_frame_topology_source_scaling_mismatch",
            "/solver_coordinate_scaling",
            "Scaling receipt does not replay from the supplied problem.",
        )

    expected_descriptors = tuple(
        _array_descriptor(name, expected_arrays[name]) for name in _PLAN_ARRAY_NAMES
    )
    source_rows = [
        _member_source_row(index, member)
        for index, member in enumerate(problem.members)
    ]
    expected_source_identity_hash = canonical_hash(
        {
            "problem_contract_hash": problem.contract_hash,
            "case_id": problem.case_id,
            "node_ids": list(plan.node_ids),
            "node_coordinates_xy_m_data_hash": array_data_hash(
                expected_arrays["node_coordinates_xy_m"]
            ),
            "members": source_rows,
            "fixed_solver_dofs": list(problem.fixed_global_dofs),
            "reference_external_loads": _reference_external_load_source_rows(problem),
            "rotation_coordinate_scale_m": problem.rotation_coordinate_scale_m,
        }
    )
    if plan.source_identity_hash != expected_source_identity_hash:
        _fail(
            "fiber_frame_topology_source_identity_mismatch",
            "/source_identity_hash",
            "Source identity does not replay from the supplied problem.",
        )

    expected_numeric_buffer_hash = canonical_hash(
        {
            "node_coordinates_xy_m": _descriptor_payload(
                _descriptor_by_name(expected_descriptors, "node_coordinates_xy_m")
            ),
            "reference_external_load_physical_6dof": _descriptor_payload(
                _descriptor_by_name(
                    expected_descriptors,
                    "reference_external_load_physical_6dof",
                )
            ),
            "solver_coordinate_scaling_hash": expected_scaling.scaling_hash,
        }
    )
    if plan.numeric_buffer_hash != expected_numeric_buffer_hash:
        _fail(
            "fiber_frame_topology_numeric_buffer_hash_mismatch",
            "/numeric_buffer_hash",
            "Numeric-buffer source commitment does not replay from the problem.",
        )

    expected_entity_mapping_hash = canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "member_ids": list(plan.member_ids),
            "member_rows": source_rows,
            "solver_to_physical_global_dofs": _descriptor_payload(
                _descriptor_by_name(
                    expected_descriptors,
                    "solver_to_physical_global_dofs",
                )
            ),
            "member_active_physical_dofs": _descriptor_payload(
                _descriptor_by_name(
                    expected_descriptors,
                    "member_active_physical_dofs",
                )
            ),
        }
    )
    if plan.entity_mapping_hash != expected_entity_mapping_hash:
        _fail(
            "fiber_frame_topology_entity_mapping_hash_mismatch",
            "/entity_mapping_hash",
            "Entity-mapping source commitment does not replay from the problem.",
        )

    expected_operator_hash = canonical_hash(
        {
            "source_schema_version": _problem_schema_version(problem),
            "problem_contract_hash": problem.contract_hash,
            "transformation": _problem_transformation(problem),
            "member_element_contract_hashes": [
                member.element.contract_hash for member in problem.members
            ],
            **_member_feature_operator_binding(problem),
            "residual_sign": "internal_minus_external",
        }
    )
    if plan.operator_hash != expected_operator_hash:
        _fail(
            "fiber_frame_topology_operator_hash_mismatch",
            "/operator_hash",
            "Operator source commitment does not match the supplied problem.",
        )
    return plan


def validate_fiber_frame_solver_coordinate_scaling(
    receipt: FiberFrameSolverCoordinateScalingReceipt,
) -> FiberFrameSolverCoordinateScalingReceipt:
    """Validate exact physical/generalized coordinate and load mappings."""

    if type(receipt) is not FiberFrameSolverCoordinateScalingReceipt:
        _fail(
            "fiber_frame_scaling_receipt_type_invalid",
            "/solver_coordinate_scaling",
            "Expected FiberFrameSolverCoordinateScalingReceipt.",
        )
    if receipt.schema_version != FIBER_FRAME_SOLVER_COORDINATE_SCALING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_scaling_schema_invalid",
            "/solver_coordinate_scaling/schema_version",
            "Unsupported solver-coordinate scaling schema.",
        )
    if receipt.authority_profile != FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_scaling_authority_profile_invalid",
            "/solver_coordinate_scaling/authority_profile",
            "Coordinate scaling cannot acquire result authority.",
        )
    if receipt.scaling_profile != FIBER_FRAME_SOLVER_COORDINATE_SCALING_PROFILE:
        _fail(
            "fiber_frame_scaling_profile_invalid",
            "/solver_coordinate_scaling/scaling_profile",
            "Unsupported solver-coordinate scaling profile.",
        )
    for path, value in (
        ("/solver_coordinate_scaling/scaling_hash", receipt.scaling_hash),
        (
            "/solver_coordinate_scaling/problem_contract_hash",
            receipt.problem_contract_hash,
        ),
        (
            "/solver_coordinate_scaling/source_commitment_hash",
            receipt.source_commitment_hash,
        ),
    ):
        _require_hash(value, path)
    scale_length = _require_positive_float(
        receipt.rotation_coordinate_scale_m,
        "/solver_coordinate_scaling/rotation_coordinate_scale_m",
    )
    solver_count = _require_index(
        receipt.solver_dof_count,
        "/solver_coordinate_scaling/solver_dof_count",
    )
    if solver_count < 3 or solver_count % 3:
        _fail(
            "fiber_frame_scaling_solver_dof_count_invalid",
            "/solver_coordinate_scaling/solver_dof_count",
            "Solver DOF count must be a positive multiple of three.",
        )
    _validate_array_map(
        receipt._arrays,
        receipt.descriptors,
        _SCALING_ARRAY_SPECS,
        "/solver_coordinate_scaling/arrays",
    )
    physical_from_generalized = receipt.array("physical_from_generalized_scale")
    generalized_from_physical = receipt.array("generalized_from_physical_scale")
    physical_load = receipt.array("reference_load_physical_solver_order")
    generalized_load = receipt.array("reference_load_generalized_solver_order")
    expected_shape = (solver_count,)
    if any(
        receipt.array(name).shape != expected_shape for name in _SCALING_ARRAY_NAMES
    ):
        _fail(
            "fiber_frame_scaling_array_shape_invalid",
            "/solver_coordinate_scaling/arrays",
            f"Every scaling vector must have shape {expected_shape}.",
        )
    expected_physical_from_generalized = np.ones(solver_count, dtype=np.float64)
    expected_physical_from_generalized[2::3] = 1.0 / scale_length
    expected_generalized_from_physical = np.ones(solver_count, dtype=np.float64)
    expected_generalized_from_physical[2::3] = scale_length
    if not np.array_equal(
        physical_from_generalized,
        expected_physical_from_generalized,
    ):
        _fail(
            "fiber_frame_scaling_physical_map_invalid",
            "/solver_coordinate_scaling/arrays/physical_from_generalized_scale",
            "Physical-from-generalized scale does not match rotation length.",
        )
    if not np.array_equal(
        generalized_from_physical,
        expected_generalized_from_physical,
    ):
        _fail(
            "fiber_frame_scaling_generalized_map_invalid",
            "/solver_coordinate_scaling/arrays/generalized_from_physical_scale",
            "Generalized-from-physical scale does not match rotation length.",
        )
    if not np.array_equal(
        generalized_load,
        physical_from_generalized * physical_load,
    ):
        _fail(
            "fiber_frame_scaling_reference_load_map_invalid",
            "/solver_coordinate_scaling/arrays/reference_load_generalized_solver_order",
            "Generalized reference load does not match the coordinate Jacobian.",
        )
    if not isinstance(receipt.extensions, MappingProxyType) or receipt.extensions:
        _fail(
            "fiber_frame_scaling_extensions_invalid",
            "/solver_coordinate_scaling/extensions",
            "Scaling receipt v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(
        _scaling_payload(receipt, include_scaling_hash=False)
    )
    if receipt.scaling_hash != expected_hash:
        _fail(
            "fiber_frame_scaling_hash_mismatch",
            "/solver_coordinate_scaling/scaling_hash",
            "Scaling hash does not match canonical content.",
        )
    return receipt


def solver_generalized_to_physical_3dof(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    generalized_coordinates_m: Any,
) -> np.ndarray:
    """Map generalized length coordinates to physical UX/UY/RZ values."""

    validate_fiber_frame_execution_topology_plan(plan)
    values = _immutable_float_vector(
        generalized_coordinates_m,
        plan.solver_dof_count,
        "/generalized_coordinates_m",
    )
    return immutable_array(
        plan.solver_coordinate_scaling.array("physical_from_generalized_scale")
        * values,
        dtype="<f8",
    )


def physical_3dof_to_solver_generalized(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_coordinates: Any,
) -> np.ndarray:
    """Map physical UX/UY/RZ values to solver generalized lengths."""

    validate_fiber_frame_execution_topology_plan(plan)
    values = _immutable_float_vector(
        physical_coordinates,
        plan.solver_dof_count,
        "/physical_coordinates",
    )
    return immutable_array(
        plan.solver_coordinate_scaling.array("generalized_from_physical_scale")
        * values,
        dtype="<f8",
    )


def physical_3dof_residual_to_solver_generalized(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_residual: Any,
) -> np.ndarray:
    """Map physical UX/UY/RZ residuals into energy-conjugate solver residuals."""

    validate_fiber_frame_execution_topology_plan(plan)
    values = _immutable_float_vector(
        physical_residual,
        plan.solver_dof_count,
        "/physical_residual",
    )
    scale = plan.solver_coordinate_scaling.array("physical_from_generalized_scale")
    return immutable_array(scale * values, dtype="<f8")


def physical_3dof_jacobian_to_solver_generalized(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_jacobian: Any,
) -> np.ndarray:
    """Map a physical UX/UY/RZ Jacobian into generalized solver coordinates."""

    validate_fiber_frame_execution_topology_plan(plan)
    matrix = _immutable_contract_array(
        physical_jacobian,
        "<f8",
        "/physical_jacobian",
    )
    expected_shape = (plan.solver_dof_count, plan.solver_dof_count)
    if matrix.shape != expected_shape:
        _fail(
            "fiber_frame_topology_jacobian_shape_invalid",
            "/physical_jacobian",
            f"Expected shape {expected_shape}.",
        )
    scale = plan.solver_coordinate_scaling.array("physical_from_generalized_scale")
    return immutable_array(
        scale[:, None] * matrix * scale[None, :],
        dtype="<f8",
    )


def physical_3dof_to_canonical_6dof(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_coordinates: Any,
) -> np.ndarray:
    """Scatter physical UX/UY/RZ values into canonical six-DOF node order."""

    validate_fiber_frame_execution_topology_plan(plan)
    values = _immutable_float_vector(
        physical_coordinates,
        plan.solver_dof_count,
        "/physical_coordinates",
    )
    result = np.zeros(plan.physical_dof_count, dtype=np.float64)
    result[plan.array("solver_to_physical_global_dofs")] = values
    return immutable_array(result, dtype="<f8")


def canonical_6dof_to_physical_3dof(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    canonical_coordinates: Any,
) -> np.ndarray:
    """Gather UX/UY/RZ after requiring inactive equations to be exact zero."""

    validate_fiber_frame_execution_topology_plan(plan)
    values = _immutable_float_vector(
        canonical_coordinates,
        plan.physical_dof_count,
        "/canonical_coordinates",
    )
    inactive = plan.array("inactive_physical_dofs")
    if inactive.size and not np.array_equal(
        values[inactive],
        np.zeros(inactive.size, dtype=np.float64),
    ):
        _fail(
            "fiber_frame_topology_inactive_coordinate_nonzero",
            "/canonical_coordinates",
            "UZ, RX, and RY coordinates must remain exact zero.",
        )
    return immutable_array(
        values[plan.array("solver_to_physical_global_dofs")],
        dtype="<f8",
    )


def validate_fiber_frame_execution_topology_array_bytes(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    *,
    name: str,
    payload: bytes,
) -> np.ndarray:
    """Validate one external plan-array artifact against its descriptor."""

    validate_fiber_frame_execution_topology_plan(plan)
    if type(payload) is not bytes:
        _fail(
            "fiber_frame_topology_array_bytes_invalid",
            f"/arrays/{name}",
            "Array artifact must be immutable bytes.",
        )
    return _validate_external_array_bytes(
        plan.descriptors,
        name=name,
        payload=payload,
        path=f"/arrays/{name}",
    )


def validate_fiber_frame_solver_coordinate_scaling_array_bytes(
    receipt: FiberFrameSolverCoordinateScalingReceipt,
    *,
    name: str,
    payload: bytes,
) -> np.ndarray:
    """Validate one external solver-coordinate scaling array artifact."""

    validate_fiber_frame_solver_coordinate_scaling(receipt)
    if type(payload) is not bytes:
        _fail(
            "fiber_frame_topology_array_bytes_invalid",
            f"/solver_coordinate_scaling/arrays/{name}",
            "Array artifact must be immutable bytes.",
        )
    return _validate_external_array_bytes(
        receipt.descriptors,
        name=name,
        payload=payload,
        path=f"/solver_coordinate_scaling/arrays/{name}",
    )


def validate_fiber_frame_execution_topology_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate strict descriptor-only imported topology metadata."""

    if not isinstance(payload, Mapping):
        _fail(
            "fiber_frame_topology_manifest_type_invalid",
            "/",
            "Topology manifest must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameExecutionTopologyError(
            "fiber_frame_topology_manifest_json_invalid",
            "/",
            "Topology manifest must be finite strict JSON.",
        ) from exc
    expected_keys = {
        "schema_version",
        "plan_id",
        "plan_hash",
        "authority_profile",
        "capability_profile",
        "kinematic_binding_decision",
        "bindings",
        "source_artifact_bindings",
        "entity_order",
        "dof_layout",
        "constraint_partition",
        "sparse_pattern",
        "array_descriptors",
        "solver_coordinate_scaling",
        "claim_boundary",
        "extensions",
    }
    if set(normalized) != expected_keys:
        _fail(
            "fiber_frame_topology_manifest_fields_invalid",
            "/",
            "Topology manifest has missing or unknown fields.",
        )
    if normalized["schema_version"] != FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION:
        _fail(
            "fiber_frame_topology_schema_invalid",
            "/schema_version",
            "Unsupported topology schema.",
        )
    if normalized["authority_profile"] != (
        FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_topology_authority_profile_invalid",
            "/authority_profile",
            "Topology manifest cannot acquire result authority.",
        )
    if normalized["capability_profile"] != (
        FIBER_FRAME_EXECUTION_TOPOLOGY_CAPABILITY_PROFILE
    ):
        _fail(
            "fiber_frame_topology_capability_profile_invalid",
            "/capability_profile",
            "Unsupported topology capability profile.",
        )
    if normalized["kinematic_binding_decision"] != (
        FIBER_FRAME_KINEMATIC_BINDING_DECISION
    ):
        _fail(
            "fiber_frame_topology_kinematic_decision_invalid",
            "/kinematic_binding_decision",
            "Kinematic binding decision changed.",
        )
    _require_stable_id(normalized["plan_id"], "/plan_id")
    _require_hash(normalized["plan_hash"], "/plan_hash")
    bindings = _require_manifest_object(
        normalized["bindings"],
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "source_identity_hash",
            "topology_hash",
            "solver_coordinate_scaling_hash",
        },
        "/bindings",
    )
    source_bindings = _require_manifest_object(
        normalized["source_artifact_bindings"],
        {"numeric_buffer_hash", "entity_mapping_hash", "operator_hash"},
        "/source_artifact_bindings",
    )
    for name, value in bindings.items():
        _require_hash(value, f"/bindings/{name}")
    for name, value in source_bindings.items():
        _require_hash(value, f"/source_artifact_bindings/{name}")

    entity_order = _require_manifest_object(
        normalized["entity_order"],
        {"case_id", "node_ids", "member_ids"},
        "/entity_order",
    )
    _require_nonempty_string(entity_order["case_id"], "/entity_order/case_id")
    node_ids = _stable_id_tuple(entity_order["node_ids"], "/entity_order/node_ids")
    member_ids = _stable_id_tuple(
        entity_order["member_ids"],
        "/entity_order/member_ids",
    )
    if len(set(node_ids)) != len(node_ids) or len(set(member_ids)) != len(member_ids):
        _fail(
            "fiber_frame_topology_entity_order_duplicate",
            "/entity_order",
            "Node and member IDs must be unique.",
        )

    dof_layout = _require_manifest_object(
        normalized["dof_layout"],
        set(_dof_layout_manifest(node_count=0, member_count=0)),
        "/dof_layout",
    )
    node_count = _require_index(dof_layout["node_count"], "/dof_layout/node_count")
    member_count = _require_index(
        dof_layout["member_count"],
        "/dof_layout/member_count",
    )
    _require_index(
        dof_layout["physical_dof_count"],
        "/dof_layout/physical_dof_count",
    )
    _require_index(
        dof_layout["solver_dof_count"],
        "/dof_layout/solver_dof_count",
    )
    if node_count < 2 or member_count < 1:
        _fail(
            "fiber_frame_topology_entity_count_invalid",
            "/dof_layout",
            "Topology requires at least two nodes and one member.",
        )
    if len(node_ids) != node_count or len(member_ids) != member_count:
        _fail(
            "fiber_frame_topology_entity_count_mismatch",
            "/entity_order",
            "Entity-order lengths do not match the DOF-layout counts.",
        )
    if dof_layout != _dof_layout_manifest(
        node_count=node_count,
        member_count=member_count,
    ):
        _fail(
            "fiber_frame_topology_dof_layout_invalid",
            "/dof_layout",
            "Canonical physical/solver DOF layout changed.",
        )
    if normalized["constraint_partition"] != dict(_CONSTRAINT_PARTITION_MANIFEST):
        _fail(
            "fiber_frame_topology_constraint_manifest_invalid",
            "/constraint_partition",
            "Constraint-partition descriptor mapping changed.",
        )
    if normalized["sparse_pattern"] != dict(_SPARSE_PATTERN_MANIFEST):
        _fail(
            "fiber_frame_topology_sparse_manifest_invalid",
            "/sparse_pattern",
            "Sparse-pattern profile or descriptor mapping changed.",
        )

    descriptors = normalized["array_descriptors"]
    if (
        not isinstance(descriptors, list)
        or not all(isinstance(row, Mapping) for row in descriptors)
        or [row["name"] if "name" in row else None for row in descriptors]
        != list(_PLAN_ARRAY_NAMES)
    ):
        _fail(
            "fiber_frame_topology_manifest_descriptor_set_invalid",
            "/array_descriptors",
            "Topology descriptor set or order is invalid.",
        )
    descriptor_shapes: dict[str, tuple[int, ...]] = {}
    for index, ((name, dtype), row) in enumerate(
        zip(_PLAN_ARRAY_SPECS, descriptors, strict=True)
    ):
        descriptor_shapes[name] = _validate_descriptor_manifest(
            row,
            name,
            dtype,
            f"/array_descriptors/{index}",
        )
    _validate_plan_manifest_descriptor_shapes(
        descriptor_shapes,
        node_count=node_count,
        member_count=member_count,
    )
    _validate_scaling_manifest(
        normalized["solver_coordinate_scaling"],
        expected_problem_contract_hash=bindings["problem_contract_hash"],
        expected_solver_dof_count=3 * node_count,
        expected_scaling_hash=bindings["solver_coordinate_scaling_hash"],
    )
    claim_boundary = _require_manifest_object(
        normalized["claim_boundary"],
        set(FIBER_FRAME_EXECUTION_TOPOLOGY_CLAIM_BOUNDARY),
        "/claim_boundary",
    )
    expected_claim_boundary = dict(FIBER_FRAME_EXECUTION_TOPOLOGY_CLAIM_BOUNDARY)
    if any(
        type(claim_boundary[name]) is not bool
        or claim_boundary[name] is not expected_value
        for name, expected_value in expected_claim_boundary.items()
    ):
        _fail(
            "fiber_frame_topology_claim_boundary_invalid",
            "/claim_boundary",
            "Topology claim boundary changed.",
        )
    if normalized["extensions"] != {}:
        _fail(
            "fiber_frame_topology_extensions_invalid",
            "/extensions",
            "Topology-plan v1 requires empty extensions.",
        )
    unsigned = dict(normalized)
    claimed_hash = unsigned.pop("plan_hash")
    if claimed_hash != canonical_hash(unsigned):
        _fail(
            "fiber_frame_topology_plan_hash_mismatch",
            "/plan_hash",
            "Topology manifest hash is stale.",
        )
    return normalized


def _is_supported_problem(problem: Any) -> bool:
    return type(problem) in (
        StatefulFiberFrame2DProblem,
        StatefulCorotationalFiberFrame2DProblem,
    )


def _problem_schema_version(problem: FiberFrame2DTopologyProblem) -> str:
    if type(problem) is StatefulFiberFrame2DProblem:
        return STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION
    return STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION


def _problem_transformation(problem: FiberFrame2DTopologyProblem) -> str:
    if type(problem) is StatefulFiberFrame2DProblem:
        return STATEFUL_FIBER_FRAME2D_TRANSFORMATION
    return (
        f"{STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY};"
        f"{STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING}"
    )


def _member_source_row(index: int, member: Any) -> dict[str, Any]:
    row = {
        "member_index": index,
        "member_id": member.member_id,
        "node_i": member.node_i,
        "node_j": member.node_j,
        "element_contract_hash": member.element.contract_hash,
    }
    if hasattr(member, "features"):
        row["feature_contract_hash"] = member.features.contract_hash
    return row


def _member_feature_operator_binding(
    problem: FiberFrame2DTopologyProblem,
) -> dict[str, Any]:
    if type(problem) is StatefulFiberFrame2DProblem:
        return {}
    return {
        "member_feature_contract_hashes": [
            member.features.contract_hash for member in problem.members
        ]
    }


def _reference_external_load_source_rows(
    problem: FiberFrame2DTopologyProblem,
) -> list[list[Any]]:
    return [[dof, value] for dof, value in problem.reference_external_loads]


def _complete_reference_external_load_vector(
    problem: FiberFrame2DTopologyProblem,
) -> np.ndarray:
    vector = np.array(
        problem.reference_external_load_vector(),
        dtype=np.float64,
        copy=True,
        order="C",
    )
    if type(problem) is StatefulCorotationalFiberFrame2DProblem:
        for member in problem.members:
            equivalent = consistent_uniform_load_element_global(
                member.element,
                member.features,
            )
            vector[list(problem.member_global_dofs(member))] += equivalent
    if not np.all(np.isfinite(vector)):
        _fail(
            "fiber_frame_topology_reference_load_nonfinite",
            "/arrays/reference_external_load_physical_6dof",
            "Complete nodal and member reference load must remain finite.",
        )
    vector.setflags(write=False)
    return vector


def _create_solver_coordinate_scaling(
    problem: FiberFrame2DTopologyProblem,
) -> FiberFrameSolverCoordinateScalingReceipt:
    scale_length = problem.rotation_coordinate_scale_m
    if scale_length < 1.0 / np.finfo(np.float64).max:
        _fail(
            "fiber_frame_scaling_rotation_scale_unrepresentable",
            "/solver_coordinate_scaling/rotation_coordinate_scale_m",
            "Rotation coordinate scale and its inverse must be finite positive fp64 values.",
        )
    inverse_scale_length = 1.0 / scale_length
    if not math.isfinite(inverse_scale_length) or inverse_scale_length <= 0.0:
        _fail(
            "fiber_frame_scaling_rotation_scale_unrepresentable",
            "/solver_coordinate_scaling/rotation_coordinate_scale_m",
            "Rotation coordinate scale and its inverse must be finite positive fp64 values.",
        )
    physical_from_generalized_values = np.ones(
        problem.global_dof_count,
        dtype=np.float64,
    )
    physical_from_generalized_values[2::3] = inverse_scale_length
    generalized_from_physical_values = np.ones(
        problem.global_dof_count,
        dtype=np.float64,
    )
    generalized_from_physical_values[2::3] = scale_length
    physical_from_generalized = _immutable_contract_array(
        physical_from_generalized_values,
        "<f8",
        "/solver_coordinate_scaling/arrays/physical_from_generalized_scale",
    )
    generalized_from_physical = _immutable_contract_array(
        generalized_from_physical_values,
        "<f8",
        "/solver_coordinate_scaling/arrays/generalized_from_physical_scale",
    )
    physical_load = _immutable_contract_array(
        _complete_reference_external_load_vector(problem),
        "<f8",
        "/solver_coordinate_scaling/arrays/reference_load_physical_solver_order",
    )
    generalized_load = _immutable_contract_array(
        physical_from_generalized * physical_load,
        "<f8",
        "/solver_coordinate_scaling/arrays/reference_load_generalized_solver_order",
    )
    arrays = MappingProxyType(
        {
            "physical_from_generalized_scale": physical_from_generalized,
            "generalized_from_physical_scale": generalized_from_physical,
            "reference_load_physical_solver_order": physical_load,
            "reference_load_generalized_solver_order": generalized_load,
        }
    )
    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _SCALING_ARRAY_NAMES
    )
    source_commitment_hash = canonical_hash(
        {
            "problem_contract_hash": problem.contract_hash,
            "rotation_coordinate_scale_m": problem.rotation_coordinate_scale_m,
            "fixed_solver_dofs": list(problem.fixed_global_dofs),
            "free_solver_dofs": list(problem.free_global_dofs),
            "reference_external_loads": _reference_external_load_source_rows(problem),
            **_member_feature_operator_binding(problem),
            "array_content_hashes": {
                descriptor.name: descriptor.content_hash for descriptor in descriptors
            },
        }
    )
    provisional = FiberFrameSolverCoordinateScalingReceipt(
        schema_version=FIBER_FRAME_SOLVER_COORDINATE_SCALING_SCHEMA_VERSION,
        scaling_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE,
        scaling_profile=FIBER_FRAME_SOLVER_COORDINATE_SCALING_PROFILE,
        problem_contract_hash=problem.contract_hash,
        rotation_coordinate_scale_m=problem.rotation_coordinate_scale_m,
        solver_dof_count=problem.global_dof_count,
        source_commitment_hash=source_commitment_hash,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        scaling_hash=canonical_hash(
            _scaling_payload(provisional, include_scaling_hash=False)
        ),
    )
    return validate_fiber_frame_solver_coordinate_scaling(receipt)


def _compile_plan_arrays(
    problem: FiberFrame2DTopologyProblem,
) -> Mapping[str, np.ndarray]:
    node_count = len(problem.node_coordinates_m)
    physical_dof_count = 6 * node_count
    solver_dof_count = 3 * node_count
    node_dofs = np.arange(physical_dof_count, dtype=np.int32).reshape(
        node_count,
        6,
    )
    solver_to_physical = np.asarray(
        [
            6 * node + component
            for node in range(node_count)
            for component in FIBER_FRAME_ACTIVE_PHYSICAL_COMPONENT_INDICES
        ],
        dtype=np.int32,
    )
    physical_to_solver = np.full(physical_dof_count, -1, dtype=np.int32)
    physical_to_solver[solver_to_physical] = np.arange(
        solver_dof_count,
        dtype=np.int32,
    )
    inactive = np.asarray(
        [
            6 * node + component
            for node in range(node_count)
            for component in FIBER_FRAME_INACTIVE_PHYSICAL_COMPONENT_INDICES
        ],
        dtype=np.int32,
    )
    authored_fixed = np.asarray(
        [solver_to_physical[dof] for dof in problem.fixed_global_dofs],
        dtype=np.int32,
    )
    constrained = np.asarray(
        sorted(
            set(int(value) for value in inactive)
            | set(int(value) for value in authored_fixed)
        ),
        dtype=np.int32,
    )
    constrained_set = set(int(value) for value in constrained)
    free_physical = np.asarray(
        [dof for dof in range(physical_dof_count) if dof not in constrained_set],
        dtype=np.int32,
    )
    member_physical_rows: list[np.ndarray] = []
    member_active_rows: list[np.ndarray] = []
    member_solver_rows: list[np.ndarray] = []
    for member in problem.members:
        physical_row = np.concatenate(
            (node_dofs[member.node_i], node_dofs[member.node_j])
        ).astype(np.int32, copy=False)
        solver_row = np.asarray(problem.member_global_dofs(member), dtype=np.int32)
        active_row = solver_to_physical[solver_row]
        member_physical_rows.append(physical_row)
        member_active_rows.append(active_row)
        member_solver_rows.append(solver_row)
    member_physical = np.vstack(member_physical_rows).astype(np.int32, copy=False)
    member_active = np.vstack(member_active_rows).astype(np.int32, copy=False)
    member_solver = np.vstack(member_solver_rows).astype(np.int32, copy=False)
    row_ptr, columns = _csr_pattern(physical_dof_count, member_active)
    physical_load = np.zeros(physical_dof_count, dtype=np.float64)
    physical_load[solver_to_physical] = _complete_reference_external_load_vector(
        problem
    )
    values: dict[str, tuple[Any, str]] = {
        "node_coordinates_xy_m": (problem.node_coordinates_m, "<f8"),
        "node_dof_indices": (node_dofs, "<i4"),
        "member_physical_global_dofs": (member_physical, "<i4"),
        "member_active_physical_dofs": (member_active, "<i4"),
        "member_solver_global_dofs": (member_solver, "<i4"),
        "solver_to_physical_global_dofs": (solver_to_physical, "<i4"),
        "physical_to_solver_global_dofs": (physical_to_solver, "<i4"),
        "inactive_physical_dofs": (inactive, "<i4"),
        "authored_fixed_physical_dofs": (authored_fixed, "<i4"),
        "constrained_physical_dofs": (constrained, "<i4"),
        "free_physical_dofs": (free_physical, "<i4"),
        "constrained_solver_dofs": (problem.fixed_global_dofs, "<i4"),
        "free_solver_dofs": (problem.free_global_dofs, "<i4"),
        "reference_external_load_physical_6dof": (physical_load, "<f8"),
        "csr_row_ptr": (row_ptr, "<i8"),
        "csr_column_indices": (columns, "<i4"),
    }
    return MappingProxyType(
        {
            name: _immutable_contract_array(
                values[name][0], values[name][1], f"/arrays/{name}"
            )
            for name in _PLAN_ARRAY_NAMES
        }
    )


def _validate_plan_array_semantics(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> None:
    exact_shapes = {
        "node_coordinates_xy_m": (plan.node_count, 2),
        "node_dof_indices": (plan.node_count, 6),
        "member_physical_global_dofs": (plan.member_count, 12),
        "member_active_physical_dofs": (plan.member_count, 6),
        "member_solver_global_dofs": (plan.member_count, 6),
        "solver_to_physical_global_dofs": (plan.solver_dof_count,),
        "physical_to_solver_global_dofs": (plan.physical_dof_count,),
        "inactive_physical_dofs": (3 * plan.node_count,),
        "reference_external_load_physical_6dof": (plan.physical_dof_count,),
        "csr_row_ptr": (plan.physical_dof_count + 1,),
    }
    for name, expected_shape in exact_shapes.items():
        if plan.array(name).shape != expected_shape:
            _fail(
                "fiber_frame_topology_array_shape_invalid",
                f"/arrays/{name}",
                f"Expected shape {expected_shape}.",
            )
    for name in (
        "authored_fixed_physical_dofs",
        "constrained_physical_dofs",
        "free_physical_dofs",
        "constrained_solver_dofs",
        "free_solver_dofs",
        "csr_column_indices",
    ):
        if plan.array(name).ndim != 1:
            _fail(
                "fiber_frame_topology_array_shape_invalid",
                f"/arrays/{name}",
                "Expected a one-dimensional vector.",
            )

    fixed_solver = plan.array("constrained_solver_dofs")
    if (
        fixed_solver.size < 1
        or np.any(fixed_solver < 0)
        or np.any(fixed_solver >= plan.solver_dof_count)
        or np.any(fixed_solver[1:] <= fixed_solver[:-1])
    ):
        _fail(
            "fiber_frame_topology_constrained_solver_partition_invalid",
            "/arrays/constrained_solver_dofs",
            "Authored solver constraints must be sorted, unique, and in range.",
        )
    fixed_set = set(int(value) for value in fixed_solver)
    expected_free_solver = np.asarray(
        [dof for dof in range(plan.solver_dof_count) if dof not in fixed_set],
        dtype=np.int32,
    )
    if not np.array_equal(plan.array("free_solver_dofs"), expected_free_solver):
        _fail(
            "fiber_frame_topology_free_solver_partition_invalid",
            "/arrays/free_solver_dofs",
            "Free solver equations must exactly complement authored constraints.",
        )

    node_dofs = plan.array("node_dof_indices")
    expected_node_dofs = np.arange(plan.physical_dof_count, dtype=np.int32).reshape(
        plan.node_count,
        6,
    )
    if not np.array_equal(node_dofs, expected_node_dofs):
        _fail(
            "fiber_frame_topology_node_dof_order_invalid",
            "/arrays/node_dof_indices",
            "Canonical node-major six-DOF order is required.",
        )
    solver_to_physical = plan.array("solver_to_physical_global_dofs")
    expected_solver_to_physical = np.asarray(
        [
            6 * node + component
            for node in range(plan.node_count)
            for component in FIBER_FRAME_ACTIVE_PHYSICAL_COMPONENT_INDICES
        ],
        dtype=np.int32,
    )
    if not np.array_equal(solver_to_physical, expected_solver_to_physical):
        _fail(
            "fiber_frame_topology_solver_physical_map_invalid",
            "/arrays/solver_to_physical_global_dofs",
            "Solver UX/UY/RZ mapping is invalid.",
        )
    physical_to_solver = plan.array("physical_to_solver_global_dofs")
    expected_physical_to_solver = np.full(
        plan.physical_dof_count,
        -1,
        dtype=np.int32,
    )
    expected_physical_to_solver[solver_to_physical] = np.arange(
        plan.solver_dof_count,
        dtype=np.int32,
    )
    if not np.array_equal(physical_to_solver, expected_physical_to_solver):
        _fail(
            "fiber_frame_topology_physical_solver_map_invalid",
            "/arrays/physical_to_solver_global_dofs",
            "Physical-to-solver inverse mapping is invalid.",
        )
    expected_inactive = np.asarray(
        [
            6 * node + component
            for node in range(plan.node_count)
            for component in FIBER_FRAME_INACTIVE_PHYSICAL_COMPONENT_INDICES
        ],
        dtype=np.int32,
    )
    if not np.array_equal(plan.array("inactive_physical_dofs"), expected_inactive):
        _fail(
            "fiber_frame_topology_inactive_dofs_invalid",
            "/arrays/inactive_physical_dofs",
            "UZ, RX, and RY must be explicit inactive equations.",
        )
    fixed_solver = plan.array("constrained_solver_dofs")
    expected_fixed_physical = solver_to_physical[fixed_solver]
    if not np.array_equal(
        plan.array("authored_fixed_physical_dofs"),
        expected_fixed_physical,
    ):
        _fail(
            "fiber_frame_topology_authored_fixed_map_invalid",
            "/arrays/authored_fixed_physical_dofs",
            "Authored frame constraints do not map to physical equations.",
        )
    expected_constrained = np.asarray(
        sorted(
            set(int(value) for value in expected_inactive)
            | set(int(value) for value in expected_fixed_physical)
        ),
        dtype=np.int32,
    )
    if not np.array_equal(
        plan.array("constrained_physical_dofs"),
        expected_constrained,
    ):
        _fail(
            "fiber_frame_topology_constrained_partition_invalid",
            "/arrays/constrained_physical_dofs",
            "Physical constrained partition is invalid.",
        )
    expected_free_physical = solver_to_physical[plan.array("free_solver_dofs")]
    if not np.array_equal(plan.array("free_physical_dofs"), expected_free_physical):
        _fail(
            "fiber_frame_topology_free_partition_invalid",
            "/arrays/free_physical_dofs",
            "Physical free equations do not match solver free equations.",
        )
    member_physical = plan.array("member_physical_global_dofs")
    member_active = plan.array("member_active_physical_dofs")
    member_solver = plan.array("member_solver_global_dofs")
    if member_physical.shape != (plan.member_count, 12):
        _fail(
            "fiber_frame_topology_member_physical_shape_invalid",
            "/arrays/member_physical_global_dofs",
            "Member physical rows must have 12 equations.",
        )
    if member_active.shape != (plan.member_count, 6) or member_solver.shape != (
        plan.member_count,
        6,
    ):
        _fail(
            "fiber_frame_topology_member_active_shape_invalid",
            "/arrays/member_active_physical_dofs",
            "Member active/solver rows must have six equations.",
        )
    if np.any(member_solver < 0) or np.any(member_solver >= plan.solver_dof_count):
        _fail(
            "fiber_frame_topology_member_solver_dof_invalid",
            "/arrays/member_solver_global_dofs",
            "Member solver equations are out of range.",
        )
    expected_member_physical_rows: list[np.ndarray] = []
    for index, row in enumerate(member_solver):
        node_indices: list[int] = []
        for offset in (0, 3):
            node_index = int(row[offset]) // 3
            expected_solver_triplet = np.arange(
                3 * node_index,
                3 * node_index + 3,
                dtype=np.int32,
            )
            if not np.array_equal(row[offset : offset + 3], expected_solver_triplet):
                _fail(
                    "fiber_frame_topology_member_solver_row_invalid",
                    f"/arrays/member_solver_global_dofs/{index}",
                    "Each member end must retain canonical UX/UY/RZ solver order.",
                )
            node_indices.append(node_index)
        if node_indices[0] == node_indices[1]:
            _fail(
                "fiber_frame_topology_member_connectivity_invalid",
                f"/arrays/member_solver_global_dofs/{index}",
                "Member end nodes must be distinct.",
            )
        expected_member_physical_rows.append(
            np.concatenate(
                (
                    node_dofs[node_indices[0]],
                    node_dofs[node_indices[1]],
                )
            )
        )
    expected_member_physical = np.vstack(expected_member_physical_rows).astype(
        np.int32,
        copy=False,
    )
    if not np.array_equal(member_physical, expected_member_physical):
        _fail(
            "fiber_frame_topology_member_physical_mapping_invalid",
            "/arrays/member_physical_global_dofs",
            "Twelve-DOF member rows do not match solver member connectivity.",
        )
    if not np.array_equal(member_active, solver_to_physical[member_solver]):
        _fail(
            "fiber_frame_topology_member_mapping_invalid",
            "/arrays/member_active_physical_dofs",
            "Member active physical rows do not map from solver rows.",
        )
    load = plan.array("reference_external_load_physical_6dof")
    if load.shape != (plan.physical_dof_count,):
        _fail(
            "fiber_frame_topology_reference_load_shape_invalid",
            "/arrays/reference_external_load_physical_6dof",
            "Reference load must use the full physical equation space.",
        )
    if not np.array_equal(
        load[plan.array("inactive_physical_dofs")],
        np.zeros(plan.array("inactive_physical_dofs").size, dtype=np.float64),
    ):
        _fail(
            "fiber_frame_topology_inactive_load_nonzero",
            "/arrays/reference_external_load_physical_6dof",
            "Inactive equations cannot carry reference loads.",
        )
    expected_row_ptr, expected_columns = _csr_pattern(
        plan.physical_dof_count,
        member_active,
    )
    if not np.array_equal(
        plan.array("csr_row_ptr"), expected_row_ptr
    ) or not np.array_equal(
        plan.array("csr_column_indices"),
        expected_columns,
    ):
        _fail(
            "fiber_frame_topology_csr_pattern_invalid",
            "/sparse_pattern",
            "CSR pattern does not match active member connectivity.",
        )


def _csr_pattern(
    dof_count: int,
    member_active_dofs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    adjacency = [{row} for row in range(dof_count)]
    for element_row in member_active_dofs:
        coupled = tuple(int(value) for value in element_row)
        for row in coupled:
            adjacency[row].update(coupled)
    row_ptr = [0]
    columns: list[int] = []
    for row in adjacency:
        columns.extend(sorted(row))
        row_ptr.append(len(columns))
    return (
        np.asarray(row_ptr, dtype=np.int64),
        np.asarray(columns, dtype=np.int32),
    )


def _dof_layout_manifest(*, node_count: int, member_count: int) -> dict[str, Any]:
    return {
        "physical_components": list(FIBER_FRAME_PHYSICAL_DOF_COMPONENTS),
        "solver_components": list(FIBER_FRAME_SOLVER_DOF_COMPONENTS),
        "node_count": node_count,
        "member_count": member_count,
        "physical_dof_count": 6 * node_count,
        "solver_dof_count": 3 * node_count,
        "node_dof_indices": "node_dof_indices",
        "member_physical_global_dofs": "member_physical_global_dofs",
        "member_active_physical_dofs": "member_active_physical_dofs",
        "member_solver_global_dofs": "member_solver_global_dofs",
        "solver_to_physical_global_dofs": "solver_to_physical_global_dofs",
        "physical_to_solver_global_dofs": "physical_to_solver_global_dofs",
    }


def _plan_payload(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    *,
    include_plan_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "authority_profile": plan.authority_profile,
        "capability_profile": plan.capability_profile,
        "kinematic_binding_decision": plan.kinematic_binding_decision,
        "bindings": {
            "problem_contract_hash": plan.problem_contract_hash,
            "model_ir_content_hash": plan.model_ir_content_hash,
            "source_identity_hash": plan.source_identity_hash,
            "topology_hash": plan.topology_hash,
            "solver_coordinate_scaling_hash": (plan.solver_coordinate_scaling_hash),
        },
        "source_artifact_bindings": {
            "numeric_buffer_hash": plan.numeric_buffer_hash,
            "entity_mapping_hash": plan.entity_mapping_hash,
            "operator_hash": plan.operator_hash,
        },
        "entity_order": {
            "case_id": plan.case_id,
            "node_ids": list(plan.node_ids),
            "member_ids": list(plan.member_ids),
        },
        "dof_layout": _dof_layout_manifest(
            node_count=plan.node_count,
            member_count=plan.member_count,
        ),
        "constraint_partition": dict(_CONSTRAINT_PARTITION_MANIFEST),
        "sparse_pattern": dict(_SPARSE_PATTERN_MANIFEST),
        "array_descriptors": [row.to_dict() for row in plan.descriptors],
        "solver_coordinate_scaling": plan.solver_coordinate_scaling.to_manifest(),
        "claim_boundary": dict(FIBER_FRAME_EXECUTION_TOPOLOGY_CLAIM_BOUNDARY),
        "extensions": dict(plan.extensions),
    }
    if include_plan_hash:
        payload["plan_hash"] = plan.plan_hash
    return payload


def _scaling_payload(
    receipt: FiberFrameSolverCoordinateScalingReceipt,
    *,
    include_scaling_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "authority_profile": receipt.authority_profile,
        "scaling_profile": receipt.scaling_profile,
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "source_commitment_hash": receipt.source_commitment_hash,
        },
        "rotation_coordinate_scale_m": receipt.rotation_coordinate_scale_m,
        "solver_dof_count": receipt.solver_dof_count,
        "array_descriptors": [row.to_dict() for row in receipt.descriptors],
        "mapping": dict(_SCALING_MAPPING),
        "extensions": dict(receipt.extensions),
    }
    if include_scaling_hash:
        payload["scaling_hash"] = receipt.scaling_hash
    return payload


def _require_manifest_object(
    value: Any,
    expected_keys: set[str],
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        _fail(
            "fiber_frame_topology_manifest_object_invalid",
            path,
            "Manifest object has missing or unknown fields.",
        )
    return value


def _validate_plan_manifest_descriptor_shapes(
    shapes: Mapping[str, tuple[int, ...]],
    *,
    node_count: int,
    member_count: int,
) -> None:
    physical_dof_count = 6 * node_count
    solver_dof_count = 3 * node_count
    exact_shapes = {
        "node_coordinates_xy_m": (node_count, 2),
        "node_dof_indices": (node_count, 6),
        "member_physical_global_dofs": (member_count, 12),
        "member_active_physical_dofs": (member_count, 6),
        "member_solver_global_dofs": (member_count, 6),
        "solver_to_physical_global_dofs": (solver_dof_count,),
        "physical_to_solver_global_dofs": (physical_dof_count,),
        "inactive_physical_dofs": (3 * node_count,),
        "reference_external_load_physical_6dof": (physical_dof_count,),
        "csr_row_ptr": (physical_dof_count + 1,),
    }
    for name, expected in exact_shapes.items():
        if shapes[name] != expected:
            _fail(
                "fiber_frame_topology_descriptor_shape_invalid",
                f"/array_descriptors/{name}/shape",
                f"Expected descriptor shape {expected}.",
            )
    variable_vectors = (
        "authored_fixed_physical_dofs",
        "constrained_physical_dofs",
        "free_physical_dofs",
        "constrained_solver_dofs",
        "free_solver_dofs",
        "csr_column_indices",
    )
    if any(len(shapes[name]) != 1 for name in variable_vectors):
        _fail(
            "fiber_frame_topology_descriptor_shape_invalid",
            "/array_descriptors",
            "Constraint and CSR column descriptors must be vectors.",
        )
    fixed_count = shapes["constrained_solver_dofs"][0]
    if fixed_count < 1 or fixed_count > solver_dof_count:
        _fail(
            "fiber_frame_topology_descriptor_partition_invalid",
            "/array_descriptors/constrained_solver_dofs/shape",
            "Authored constrained solver count is out of range.",
        )
    expected_partition_lengths = {
        "authored_fixed_physical_dofs": fixed_count,
        "constrained_physical_dofs": 3 * node_count + fixed_count,
        "free_physical_dofs": solver_dof_count - fixed_count,
        "free_solver_dofs": solver_dof_count - fixed_count,
    }
    for name, expected_length in expected_partition_lengths.items():
        if shapes[name] != (expected_length,):
            _fail(
                "fiber_frame_topology_descriptor_partition_invalid",
                f"/array_descriptors/{name}/shape",
                "Descriptor length is inconsistent with the DOF partition.",
            )
    column_count = shapes["csr_column_indices"][0]
    if column_count < physical_dof_count:
        _fail(
            "fiber_frame_topology_descriptor_csr_invalid",
            "/array_descriptors/csr_column_indices/shape",
            "CSR pattern must retain at least one diagonal entry per physical row.",
        )


def _validate_scaling_manifest(
    payload: Any,
    *,
    expected_problem_contract_hash: str,
    expected_solver_dof_count: int,
    expected_scaling_hash: str,
) -> None:
    if not isinstance(payload, Mapping):
        _fail(
            "fiber_frame_scaling_manifest_type_invalid",
            "/solver_coordinate_scaling",
            "Scaling manifest must be an object.",
        )
    expected_keys = {
        "schema_version",
        "scaling_hash",
        "authority_profile",
        "scaling_profile",
        "bindings",
        "rotation_coordinate_scale_m",
        "solver_dof_count",
        "array_descriptors",
        "mapping",
        "extensions",
    }
    if set(payload) != expected_keys:
        _fail(
            "fiber_frame_scaling_manifest_fields_invalid",
            "/solver_coordinate_scaling",
            "Scaling manifest has missing or unknown fields.",
        )
    if payload["schema_version"] != (
        FIBER_FRAME_SOLVER_COORDINATE_SCALING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_scaling_schema_invalid",
            "/solver_coordinate_scaling/schema_version",
            "Unsupported scaling schema.",
        )
    if payload["authority_profile"] != (
        FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_scaling_authority_profile_invalid",
            "/solver_coordinate_scaling/authority_profile",
            "Scaling manifest cannot acquire result authority.",
        )
    if payload["scaling_profile"] != FIBER_FRAME_SOLVER_COORDINATE_SCALING_PROFILE:
        _fail(
            "fiber_frame_scaling_profile_invalid",
            "/solver_coordinate_scaling/scaling_profile",
            "Unsupported scaling profile.",
        )
    scaling_hash = _require_hash(
        payload["scaling_hash"],
        "/solver_coordinate_scaling/scaling_hash",
    )
    bindings = _require_manifest_object(
        payload["bindings"],
        {"problem_contract_hash", "source_commitment_hash"},
        "/solver_coordinate_scaling/bindings",
    )
    for name, value in bindings.items():
        _require_hash(value, f"/solver_coordinate_scaling/bindings/{name}")
    if bindings["problem_contract_hash"] != expected_problem_contract_hash:
        _fail(
            "fiber_frame_scaling_problem_binding_mismatch",
            "/solver_coordinate_scaling/bindings/problem_contract_hash",
            "Scaling manifest belongs to another problem contract.",
        )
    _require_positive_float(
        payload["rotation_coordinate_scale_m"],
        "/solver_coordinate_scaling/rotation_coordinate_scale_m",
    )
    solver_dof_count = _require_index(
        payload["solver_dof_count"],
        "/solver_coordinate_scaling/solver_dof_count",
    )
    if (
        solver_dof_count < 3
        or solver_dof_count % 3
        or solver_dof_count != expected_solver_dof_count
    ):
        _fail(
            "fiber_frame_scaling_solver_dof_count_invalid",
            "/solver_coordinate_scaling/solver_dof_count",
            "Scaling solver count must match the topology and be a multiple of three.",
        )
    descriptors = payload["array_descriptors"]
    if (
        not isinstance(descriptors, list)
        or not all(isinstance(row, Mapping) for row in descriptors)
        or [row["name"] if "name" in row else None for row in descriptors]
        != list(_SCALING_ARRAY_NAMES)
    ):
        _fail(
            "fiber_frame_scaling_manifest_descriptor_set_invalid",
            "/solver_coordinate_scaling/array_descriptors",
            "Scaling descriptor set or order is invalid.",
        )
    for index, ((name, dtype), row) in enumerate(
        zip(_SCALING_ARRAY_SPECS, descriptors, strict=True)
    ):
        shape = _validate_descriptor_manifest(
            row,
            name,
            dtype,
            f"/solver_coordinate_scaling/array_descriptors/{index}",
        )
        if shape != (solver_dof_count,):
            _fail(
                "fiber_frame_scaling_descriptor_shape_invalid",
                f"/solver_coordinate_scaling/array_descriptors/{index}/shape",
                "Every solver-coordinate scaling array must use full solver order.",
            )
    if payload["mapping"] != dict(_SCALING_MAPPING):
        _fail(
            "fiber_frame_scaling_mapping_invalid",
            "/solver_coordinate_scaling/mapping",
            "Residual/Jacobian coordinate-transform mapping changed.",
        )
    if payload["extensions"] != {}:
        _fail(
            "fiber_frame_scaling_extensions_invalid",
            "/solver_coordinate_scaling/extensions",
            "Scaling manifest v1 requires empty extensions.",
        )
    unsigned = dict(payload)
    claimed_hash = unsigned.pop("scaling_hash")
    if claimed_hash != canonical_hash(unsigned):
        _fail(
            "fiber_frame_scaling_hash_mismatch",
            "/solver_coordinate_scaling/scaling_hash",
            "Scaling manifest hash is stale.",
        )
    if scaling_hash != expected_scaling_hash:
        _fail(
            "fiber_frame_topology_scaling_hash_mismatch",
            "/bindings/solver_coordinate_scaling_hash",
            "Topology binding does not match the nested scaling manifest.",
        )


def _validate_descriptor_manifest(
    payload: Any,
    expected_name: str,
    expected_dtype: str,
    path: str,
) -> tuple[int, ...]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "name",
        "dtype",
        "shape",
        "layout",
        "byte_length",
        "data_hash",
        "content_hash",
    }:
        _fail(
            "fiber_frame_topology_descriptor_fields_invalid",
            path,
            "Array descriptor has missing or unknown fields.",
        )
    if payload["name"] != expected_name or payload["dtype"] != expected_dtype:
        _fail(
            "fiber_frame_topology_descriptor_identity_invalid",
            path,
            "Array descriptor name or dtype changed.",
        )
    if payload["layout"] != "C":
        _fail(
            "fiber_frame_topology_descriptor_layout_invalid",
            path,
            "Array descriptor requires C layout.",
        )
    if not isinstance(payload["shape"], list) or not payload["shape"]:
        _fail(
            "fiber_frame_topology_descriptor_shape_invalid",
            path,
            "Array descriptor shape must be a non-empty list.",
        )
    shape = tuple(
        _require_index(value, f"{path}/shape/{index}")
        for index, value in enumerate(payload["shape"])
    )
    byte_length = _require_index(payload["byte_length"], f"{path}/byte_length")
    expected_byte_length = math.prod(shape) * np.dtype(expected_dtype).itemsize
    if byte_length != expected_byte_length:
        _fail(
            "fiber_frame_topology_descriptor_byte_length_invalid",
            f"{path}/byte_length",
            "Descriptor byte length does not match dtype and shape.",
        )
    _require_hash(payload["data_hash"], f"{path}/data_hash")
    _require_hash(payload["content_hash"], f"{path}/content_hash")
    return shape


def _validate_array_map(
    arrays: Mapping[str, np.ndarray],
    descriptors: tuple[FiberFrameTopologyArrayDescriptor, ...],
    specs: tuple[tuple[str, str], ...],
    path: str,
) -> None:
    names = tuple(name for name, _dtype in specs)
    if not isinstance(arrays, MappingProxyType) or tuple(arrays) != names:
        _fail(
            "fiber_frame_topology_array_set_invalid",
            path,
            "Array map must be immutable and use the exact ordered set.",
        )
    if (
        type(descriptors) is not tuple
        or not all(
            type(row) is FiberFrameTopologyArrayDescriptor for row in descriptors
        )
        or tuple(row.name for row in descriptors) != names
    ):
        _fail(
            "fiber_frame_topology_descriptor_set_invalid",
            path,
            "Array descriptor set or order is invalid.",
        )
    by_name = {row.name: row for row in descriptors}
    for name, dtype in specs:
        array = arrays[name]
        if (
            not isinstance(array, np.ndarray)
            or array.dtype.str != dtype
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
        ):
            _fail(
                "fiber_frame_topology_array_contract_invalid",
                f"{path}/{name}",
                f"Expected immutable C-contiguous {dtype} array.",
            )
        if by_name[name] != _array_descriptor(name, array):
            _fail(
                "fiber_frame_topology_descriptor_mismatch",
                f"{path}/{name}",
                "Array descriptor does not match retained bytes.",
            )


def _array_descriptor(
    name: str,
    array: np.ndarray,
) -> FiberFrameTopologyArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return FiberFrameTopologyArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _descriptor_by_name(
    descriptors: tuple[FiberFrameTopologyArrayDescriptor, ...],
    name: str,
) -> FiberFrameTopologyArrayDescriptor:
    for descriptor in descriptors:
        if descriptor.name == name:
            return descriptor
    _fail(
        "fiber_frame_topology_descriptor_missing",
        f"/array_descriptors/{name}",
        "Required array descriptor is missing.",
    )


def _validate_external_array_bytes(
    descriptors: tuple[FiberFrameTopologyArrayDescriptor, ...],
    *,
    name: str,
    payload: bytes,
    path: str,
) -> np.ndarray:
    descriptor = _descriptor_by_name(descriptors, name)
    if len(payload) != descriptor.byte_length:
        _fail(
            "fiber_frame_topology_array_length_mismatch",
            path,
            "Array artifact byte length does not match descriptor.",
        )
    try:
        array = np.frombuffer(payload, dtype=descriptor.dtype).reshape(descriptor.shape)
    except (TypeError, ValueError) as exc:
        raise FiberFrameExecutionTopologyError(
            "fiber_frame_topology_array_shape_mismatch",
            path,
            "Array artifact bytes cannot be reshaped to the descriptor shape.",
        ) from exc
    immutable = immutable_array(array, dtype=descriptor.dtype)
    if array_data_hash(immutable) != descriptor.data_hash:
        _fail(
            "fiber_frame_topology_array_hash_mismatch",
            path,
            "Array artifact bytes do not match descriptor.",
        )
    return immutable


def _descriptor_payload(
    descriptor: FiberFrameTopologyArrayDescriptor,
) -> dict[str, Any]:
    return descriptor.to_dict()


def _immutable_contract_array(
    value: Any,
    dtype: str,
    path: str,
) -> np.ndarray:
    try:
        return immutable_array(value, dtype=dtype)
    except CanonicalContractError as exc:
        raise FiberFrameExecutionTopologyError(
            "fiber_frame_topology_array_invalid",
            path,
            str(exc),
        ) from exc


def _immutable_float_vector(value: Any, size: int, path: str) -> np.ndarray:
    array = _immutable_contract_array(value, "<f8", path)
    if array.shape != (size,):
        _fail(
            "fiber_frame_topology_vector_shape_invalid",
            path,
            f"Expected shape {(size,)}.",
        )
    return array


def _normalize_node_ids(
    node_ids: Sequence[str] | None,
    node_count: int,
) -> tuple[str, ...]:
    values = (
        tuple(f"node.{index:04d}" for index in range(node_count))
        if node_ids is None
        else _stable_id_tuple(node_ids, "/entity_order/node_ids")
    )
    if len(values) != node_count:
        _fail(
            "fiber_frame_topology_node_id_count_mismatch",
            "/entity_order/node_ids",
            "Exactly one node ID is required per problem node.",
        )
    if len(set(values)) != len(values):
        _fail(
            "fiber_frame_topology_node_id_duplicate",
            "/entity_order/node_ids",
            "Node IDs must be unique.",
        )
    return values


def _stable_id_tuple(value: Sequence[str], path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail(
            "fiber_frame_topology_id_sequence_invalid",
            path,
            "Expected a non-string identifier sequence.",
        )
    return tuple(
        _require_stable_id(item, f"{path}/{index}") for index, item in enumerate(value)
    )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or not _HASH_PATTERN.fullmatch(value):
        _fail(
            "fiber_frame_topology_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if type(value) is not str or not _STABLE_ID_PATTERN.fullmatch(value):
        _fail(
            "fiber_frame_topology_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return value


def _require_nonempty_string(value: Any, path: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail(
            "fiber_frame_topology_string_invalid",
            path,
            "Expected a normalized non-empty string.",
        )
    return value


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_topology_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _require_positive_float(value: Any, path: str) -> float:
    if type(value) is not float:
        _fail(
            "fiber_frame_topology_number_invalid",
            path,
            "Expected a finite positive number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        _fail(
            "fiber_frame_topology_number_invalid",
            path,
            "Expected a finite positive number.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameExecutionTopologyError(code, path, message)


__all__ = [
    "FIBER_FRAME_ACTIVE_PHYSICAL_COMPONENT_INDICES",
    "FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE",
    "FIBER_FRAME_EXECUTION_TOPOLOGY_CAPABILITY_PROFILE",
    "FIBER_FRAME_EXECUTION_TOPOLOGY_CLAIM_BOUNDARY",
    "FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION",
    "FIBER_FRAME_INACTIVE_PHYSICAL_COMPONENT_INDICES",
    "FIBER_FRAME_KINEMATIC_BINDING_DECISION",
    "FIBER_FRAME_PHYSICAL_DOF_COMPONENTS",
    "FIBER_FRAME_SOLVER_COORDINATE_SCALING_PROFILE",
    "FIBER_FRAME_SOLVER_COORDINATE_SCALING_SCHEMA_VERSION",
    "FIBER_FRAME_SOLVER_DOF_COMPONENTS",
    "FiberFrameExecutionTopologyError",
    "FiberFrame2DTopologyProblem",
    "FiberFrameNonlinearExecutionTopologyPlan",
    "FiberFrameSolverCoordinateScalingReceipt",
    "FiberFrameTopologyArrayDescriptor",
    "canonical_6dof_to_physical_3dof",
    "compile_stateful_fiber_frame2d_execution_topology",
    "physical_3dof_to_canonical_6dof",
    "physical_3dof_jacobian_to_solver_generalized",
    "physical_3dof_residual_to_solver_generalized",
    "physical_3dof_to_solver_generalized",
    "solver_generalized_to_physical_3dof",
    "validate_fiber_frame_execution_topology_against_problem",
    "validate_fiber_frame_execution_topology_array_bytes",
    "validate_fiber_frame_execution_topology_manifest",
    "validate_fiber_frame_execution_topology_plan",
    "validate_fiber_frame_solver_coordinate_scaling",
    "validate_fiber_frame_solver_coordinate_scaling_array_bytes",
]
