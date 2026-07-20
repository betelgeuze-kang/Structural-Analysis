"""Physical force/moment scaling for the bounded stateful fiber frame.

PR-J1 binds the solver-coordinate transform used to express rotations as
length-like generalized coordinates.  This module addresses a different
problem: physical equilibrium combines translational forces in kN and rotational
moments in kN m.  Those quantities must not be judged by one raw mixed-unit
norm.

The contracts below bind a geometry- and load-derived physical scaling receipt
and descriptor-only residual traces.  They do not establish convergence or
numerical/engineering result authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DAssembly,
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_PHYSICAL_DOF_COMPONENTS,
    FiberFrameNonlinearExecutionTopologyPlan,
    validate_fiber_frame_execution_topology_against_problem,
    validate_fiber_frame_execution_topology_plan,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-physical-equation-scaling.v1"
)
FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-physical-residual-trace.v1"
)
FIBER_FRAME_PHYSICAL_EQUATION_SCALING_PROFILE = (
    "bbox_diagonal_reference_load_force_moment.v1"
)
FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE = (
    "non_authoritative_physical_equation_scaling.v1"
)
FIBER_FRAME_PHYSICAL_SCALING_CLAIM_BOUNDARY = MappingProxyType(
    {
        "j1_topology_bound": True,
        "problem_contract_bound": True,
        "characteristic_length_bound": True,
        "force_and_moment_scales_separated": True,
        "raw_translation_norm_retained": True,
        "raw_rotation_norm_retained": True,
        "scaled_norms_retained": True,
        "governing_node_and_dof_retained": True,
        "solver_coordinate_transform_revalidated": True,
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
_MAX_INDEX = 2**31 - 1
_TRANSLATION_COMPONENTS = (0, 1)
_ROTATION_COMPONENT = 5
_SCALING_ARRAY_SPECS = (
    ("physical_equation_scale", "<f8"),
    ("solver_equation_scale", "<f8"),
    ("reference_load_physical_6dof", "<f8"),
    ("reference_load_scaled_6dof", "<f8"),
)
_TRACE_ARRAY_SPECS = (
    ("physical_residual_6dof", "<f8"),
    ("scaled_free_residual_6dof", "<f8"),
    ("physical_residual_solver_order", "<f8"),
    ("generalized_residual_solver_free", "<f8"),
)


class FiberFramePhysicalScalingError(ValueError):
    """Stable fail-closed physical scaling or trace error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFramePhysicalArrayDescriptor:
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
class FiberFramePhysicalEquationScalingReceipt:
    schema_version: str
    scaling_hash: str
    authority_profile: str
    scaling_profile: str
    topology_plan_hash: str
    problem_contract_hash: str
    characteristic_length_m: float
    characteristic_length_source_hash: str
    force_reference_kn: float
    moment_reference_kn_m: float
    physical_dof_count: int
    solver_dof_count: int
    descriptors: tuple[FiberFramePhysicalArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any] = field(repr=False, compare=False)

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown physical scaling array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_physical_equation_scaling(self)
        return _scaling_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFramePhysicalResidualTrace:
    schema_version: str
    trace_hash: str
    authority_profile: str
    topology_plan_hash: str
    physical_scaling_hash: str
    problem_contract_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    assembly_hash: str
    raw_translation_linf_kn: float
    raw_rotation_linf_kn_m: float
    scaled_linf: float
    scaled_l2: float
    governing_physical_dof: int
    governing_node_index: int
    governing_component: str
    descriptors: tuple[FiberFramePhysicalArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any] = field(repr=False, compare=False)

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown physical residual trace array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_physical_residual_trace(self)
        return _trace_payload(self, include_hash=True)


def create_fiber_frame_physical_equation_scaling(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    *,
    _skip_source_validation: bool = False,
) -> FiberFramePhysicalEquationScalingReceipt:
    """Create one geometry/load-derived kN and kN-m scaling receipt."""

    if _skip_source_validation:
        validate_fiber_frame_execution_topology_plan(topology_plan)
        if topology_plan.problem_contract_hash != problem.contract_hash:
            _fail(
                "fiber_frame_physical_scaling_problem_mismatch",
                "/problem_contract_hash",
                "Physical scaling belongs to another frame problem.",
            )
    else:
        validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    coordinates = np.asarray(problem.node_coordinates_m, dtype=np.float64)
    extents = np.max(coordinates, axis=0) - np.min(coordinates, axis=0)
    characteristic_length = float(np.linalg.norm(extents))
    if not math.isfinite(characteristic_length) or characteristic_length <= 0.0:
        _fail(
            "fiber_frame_physical_scaling_length_invalid",
            "/characteristic_length_m",
            "The node-coordinate bounding-box diagonal must be positive.",
        )

    reference_load = topology_plan.array("reference_external_load_physical_6dof")
    translation_indices = _component_indices(
        topology_plan.node_count,
        _TRANSLATION_COMPONENTS,
    )
    rotation_indices = _component_indices(
        topology_plan.node_count,
        (_ROTATION_COMPONENT,),
    )
    translation_reference = _linf(reference_load[translation_indices])
    rotation_reference = _linf(reference_load[rotation_indices])
    force_reference = max(
        translation_reference,
        rotation_reference / characteristic_length,
        1.0,
    )
    moment_reference = force_reference * characteristic_length

    physical_scale = np.zeros(topology_plan.physical_dof_count, dtype=np.float64)
    for node in range(topology_plan.node_count):
        physical_scale[6 * node] = 1.0 / force_reference
        physical_scale[6 * node + 1] = 1.0 / force_reference
        physical_scale[6 * node + 5] = 1.0 / moment_reference
    solver_scale = physical_scale[topology_plan.array("solver_to_physical_global_dofs")]
    reference_scaled = physical_scale * reference_load
    arrays = MappingProxyType(
        {
            "physical_equation_scale": immutable_array(physical_scale, dtype="<f8"),
            "solver_equation_scale": immutable_array(solver_scale, dtype="<f8"),
            "reference_load_physical_6dof": immutable_array(
                reference_load,
                dtype="<f8",
            ),
            "reference_load_scaled_6dof": immutable_array(
                reference_scaled,
                dtype="<f8",
            ),
        }
    )
    descriptors = tuple(
        _descriptor(name, arrays[name]) for name, _dtype in _SCALING_ARRAY_SPECS
    )
    length_source_hash = canonical_hash(
        {
            "profile": "node_coordinate_bbox_diagonal.v1",
            "node_coordinates_xy_m_data_hash": array_data_hash(
                topology_plan.array("node_coordinates_xy_m")
            ),
            "bbox_extent_x_m": float(extents[0]),
            "bbox_extent_y_m": float(extents[1]),
            "characteristic_length_m": characteristic_length,
        }
    )
    provisional = FiberFramePhysicalEquationScalingReceipt(
        schema_version=FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION,
        scaling_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE,
        scaling_profile=FIBER_FRAME_PHYSICAL_EQUATION_SCALING_PROFILE,
        topology_plan_hash=topology_plan.plan_hash,
        problem_contract_hash=problem.contract_hash,
        characteristic_length_m=characteristic_length,
        characteristic_length_source_hash=length_source_hash,
        force_reference_kn=force_reference,
        moment_reference_kn_m=moment_reference,
        physical_dof_count=topology_plan.physical_dof_count,
        solver_dof_count=topology_plan.solver_dof_count,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        scaling_hash=canonical_hash(_scaling_payload(provisional, include_hash=False)),
    )
    validate_fiber_frame_physical_equation_scaling(receipt)
    if not _skip_source_validation:
        validate_fiber_frame_physical_equation_scaling_against_problem(
            problem,
            topology_plan,
            receipt,
        )
    return receipt


def create_fiber_frame_physical_residual_trace(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    scaling: FiberFramePhysicalEquationScalingReceipt,
    assembly: StatefulFiberFrame2DAssembly,
    *,
    _skip_source_validation: bool = False,
) -> FiberFramePhysicalResidualTrace:
    """Record raw kN/kN-m residuals and their dimensionless scaled norms."""

    if _skip_source_validation:
        validate_fiber_frame_execution_topology_plan(topology_plan)
        validate_fiber_frame_physical_equation_scaling(scaling)
        if scaling.topology_plan_hash != topology_plan.plan_hash:
            _fail(
                "fiber_frame_physical_scaling_topology_mismatch",
                "/topology_plan_hash",
                "Physical scaling belongs to another J1 topology plan.",
            )
        if scaling.problem_contract_hash != problem.contract_hash:
            _fail(
                "fiber_frame_physical_scaling_problem_mismatch",
                "/problem_contract_hash",
                "Physical scaling belongs to another frame problem.",
            )
    else:
        validate_fiber_frame_physical_equation_scaling_against_problem(
            problem,
            topology_plan,
            scaling,
        )
    if type(assembly) is not StatefulFiberFrame2DAssembly:
        _fail(
            "fiber_frame_physical_trace_assembly_type_invalid",
            "/assembly",
            "Expected exact StatefulFiberFrame2DAssembly.",
        )
    expected_shape = (problem.global_dof_count,)
    for path, value in (
        ("/assembly/internal_loads_global", assembly.internal_loads_global),
        ("/assembly/external_loads_global", assembly.external_loads_global),
    ):
        if not isinstance(value, np.ndarray) or value.shape != expected_shape:
            _fail(
                "fiber_frame_physical_trace_assembly_shape_invalid",
                path,
                f"Expected shape {expected_shape}.",
            )
        if not np.all(np.isfinite(value)):
            _fail(
                "fiber_frame_physical_trace_assembly_nonfinite",
                path,
                "Assembly force/moment vectors must be finite.",
            )

    physical_solver_residual = immutable_array(
        assembly.internal_loads_global - assembly.external_loads_global,
        dtype="<f8",
    )
    free_solver = np.asarray(problem.free_global_dofs, dtype=np.int64)
    expected_generalized_free = (
        problem.physical_coordinate_scale[free_solver]
        * physical_solver_residual[free_solver]
    )
    if not np.allclose(
        assembly.residual_kn,
        expected_generalized_free,
        rtol=0.0,
        atol=1.0e-12,
    ):
        _fail(
            "fiber_frame_physical_trace_solver_transform_mismatch",
            "/assembly/residual_kn",
            "Assembly generalized residual does not match the J1 coordinate transform.",
        )

    physical_residual = np.zeros(topology_plan.physical_dof_count, dtype=np.float64)
    physical_residual[topology_plan.array("solver_to_physical_global_dofs")] = (
        physical_solver_residual
    )
    inactive = topology_plan.array("inactive_physical_dofs")
    if inactive.size and not np.array_equal(
        physical_residual[inactive],
        np.zeros(inactive.size, dtype=np.float64),
    ):
        _fail(
            "fiber_frame_physical_trace_inactive_residual_nonzero",
            "/physical_residual_6dof",
            "Inactive UZ/RX/RY equations must have exact zero residual.",
        )

    free_physical = topology_plan.array("free_physical_dofs").astype(
        np.int64,
        copy=False,
    )
    free_translation = np.asarray(
        [dof for dof in free_physical if int(dof) % 6 in _TRANSLATION_COMPONENTS],
        dtype=np.int64,
    )
    free_rotation = np.asarray(
        [dof for dof in free_physical if int(dof) % 6 == _ROTATION_COMPONENT],
        dtype=np.int64,
    )
    raw_translation = _linf(physical_residual[free_translation])
    raw_rotation = _linf(physical_residual[free_rotation])
    scaled = np.zeros(topology_plan.physical_dof_count, dtype=np.float64)
    scaled[free_physical] = (
        physical_residual[free_physical]
        * scaling.array("physical_equation_scale")[free_physical]
    )
    scaled_free = scaled[free_physical]
    scaled_linf = _linf(scaled_free)
    scaled_l2 = float(np.linalg.norm(scaled_free, ord=2)) if scaled_free.size else 0.0
    if not free_physical.size:
        _fail(
            "fiber_frame_physical_trace_free_equations_empty",
            "/free_physical_dofs",
            "Residual trace requires at least one free physical equation.",
        )
    governing_local = int(np.argmax(np.abs(scaled_free)))
    governing_dof = int(free_physical[governing_local])
    governing_node = governing_dof // 6
    governing_component = FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[governing_dof % 6]

    arrays = MappingProxyType(
        {
            "physical_residual_6dof": immutable_array(
                physical_residual,
                dtype="<f8",
            ),
            "scaled_free_residual_6dof": immutable_array(scaled, dtype="<f8"),
            "physical_residual_solver_order": physical_solver_residual,
            "generalized_residual_solver_free": immutable_array(
                assembly.residual_kn,
                dtype="<f8",
            ),
        }
    )
    descriptors = tuple(
        _descriptor(name, arrays[name]) for name, _dtype in _TRACE_ARRAY_SPECS
    )
    provisional = FiberFramePhysicalResidualTrace(
        schema_version=FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
        trace_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE,
        topology_plan_hash=topology_plan.plan_hash,
        physical_scaling_hash=scaling.scaling_hash,
        problem_contract_hash=problem.contract_hash,
        parent_checkpoint_hash=_require_hash(
            assembly.parent_checkpoint_hash,
            "/parent_checkpoint_hash",
        ),
        target_load_factor=_finite(
            assembly.target_load_factor,
            "/target_load_factor",
        ),
        assembly_hash=canonical_hash(assembly.to_dict()),
        raw_translation_linf_kn=raw_translation,
        raw_rotation_linf_kn_m=raw_rotation,
        scaled_linf=scaled_linf,
        scaled_l2=scaled_l2,
        governing_physical_dof=governing_dof,
        governing_node_index=governing_node,
        governing_component=governing_component,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    trace = replace(
        provisional,
        trace_hash=canonical_hash(_trace_payload(provisional, include_hash=False)),
    )
    validate_fiber_frame_physical_residual_trace(trace)
    if not _skip_source_validation:
        validate_fiber_frame_physical_residual_trace_against_assembly(
            problem,
            topology_plan,
            scaling,
            assembly,
            trace,
        )
    return trace


def validate_fiber_frame_physical_equation_scaling(
    receipt: FiberFramePhysicalEquationScalingReceipt,
) -> FiberFramePhysicalEquationScalingReceipt:
    if type(receipt) is not FiberFramePhysicalEquationScalingReceipt:
        _fail(
            "fiber_frame_physical_scaling_type_invalid",
            "/",
            "Expected FiberFramePhysicalEquationScalingReceipt.",
        )
    if receipt.schema_version != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_scaling_schema_invalid",
            "/schema_version",
            "Unsupported physical equation scaling schema.",
        )
    if receipt.authority_profile != FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_physical_scaling_authority_invalid",
            "/authority_profile",
            "Physical scaling cannot acquire result authority.",
        )
    if receipt.scaling_profile != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_PROFILE:
        _fail(
            "fiber_frame_physical_scaling_profile_invalid",
            "/scaling_profile",
            "Unsupported physical equation scaling profile.",
        )
    for path, value in (
        ("/scaling_hash", receipt.scaling_hash),
        ("/topology_plan_hash", receipt.topology_plan_hash),
        ("/problem_contract_hash", receipt.problem_contract_hash),
        (
            "/characteristic_length_source_hash",
            receipt.characteristic_length_source_hash,
        ),
    ):
        _require_hash(value, path)
    characteristic_length = _positive(
        receipt.characteristic_length_m,
        "/characteristic_length_m",
    )
    force_reference = _positive(receipt.force_reference_kn, "/force_reference_kn")
    moment_reference = _positive(
        receipt.moment_reference_kn_m,
        "/moment_reference_kn_m",
    )
    if not math.isclose(
        moment_reference,
        force_reference * characteristic_length,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        _fail(
            "fiber_frame_physical_scaling_force_moment_relation_invalid",
            "/moment_reference_kn_m",
            "Moment reference must equal force reference times characteristic length.",
        )
    if _index(receipt.physical_dof_count, "/physical_dof_count") % 6:
        _fail(
            "fiber_frame_physical_scaling_physical_dof_count_invalid",
            "/physical_dof_count",
            "Physical DOF count must be a multiple of six.",
        )
    if _index(receipt.solver_dof_count, "/solver_dof_count") % 3:
        _fail(
            "fiber_frame_physical_scaling_solver_dof_count_invalid",
            "/solver_dof_count",
            "Solver DOF count must be a multiple of three.",
        )
    _validate_array_map(
        receipt._arrays,
        receipt.descriptors,
        _SCALING_ARRAY_SPECS,
        "/arrays",
    )
    physical_scale = receipt.array("physical_equation_scale")
    if physical_scale.shape != (receipt.physical_dof_count,):
        _fail(
            "fiber_frame_physical_scaling_vector_shape_invalid",
            "/arrays/physical_equation_scale",
            "Physical scaling vector has the wrong shape.",
        )
    for node in range(receipt.physical_dof_count // 6):
        expected = np.asarray(
            [
                1.0 / force_reference,
                1.0 / force_reference,
                0.0,
                0.0,
                0.0,
                1.0 / moment_reference,
            ],
            dtype=np.float64,
        )
        if not np.array_equal(physical_scale[6 * node : 6 * node + 6], expected):
            _fail(
                "fiber_frame_physical_scaling_component_map_invalid",
                "/arrays/physical_equation_scale",
                "Physical scaling vector must separate forces and moments.",
            )
    if not isinstance(receipt.extensions, MappingProxyType) or receipt.extensions:
        _fail(
            "fiber_frame_physical_scaling_extensions_invalid",
            "/extensions",
            "Physical scaling v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_scaling_payload(receipt, include_hash=False))
    if receipt.scaling_hash != expected_hash:
        _fail(
            "fiber_frame_physical_scaling_hash_mismatch",
            "/scaling_hash",
            "Physical scaling hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_physical_equation_scaling_against_problem(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    receipt: FiberFramePhysicalEquationScalingReceipt,
) -> FiberFramePhysicalEquationScalingReceipt:
    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling(receipt)
    if receipt.topology_plan_hash != topology_plan.plan_hash:
        _fail(
            "fiber_frame_physical_scaling_topology_mismatch",
            "/topology_plan_hash",
            "Physical scaling belongs to another J1 topology plan.",
        )
    if receipt.problem_contract_hash != problem.contract_hash:
        _fail(
            "fiber_frame_physical_scaling_problem_mismatch",
            "/problem_contract_hash",
            "Physical scaling belongs to another frame problem.",
        )
    expected = create_fiber_frame_physical_equation_scaling(
        problem,
        topology_plan,
        _skip_source_validation=True,
    )
    if expected.to_manifest() != receipt.to_manifest():
        _fail(
            "fiber_frame_physical_scaling_source_replay_mismatch",
            "/",
            "Physical scaling does not replay from the source problem.",
        )
    return receipt


def validate_fiber_frame_physical_residual_trace(
    trace: FiberFramePhysicalResidualTrace,
) -> FiberFramePhysicalResidualTrace:
    if type(trace) is not FiberFramePhysicalResidualTrace:
        _fail(
            "fiber_frame_physical_trace_type_invalid",
            "/",
            "Expected FiberFramePhysicalResidualTrace.",
        )
    if trace.schema_version != FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_trace_schema_invalid",
            "/schema_version",
            "Unsupported physical residual trace schema.",
        )
    if trace.authority_profile != FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_physical_trace_authority_invalid",
            "/authority_profile",
            "Residual trace cannot acquire result authority.",
        )
    for path, value in (
        ("/trace_hash", trace.trace_hash),
        ("/topology_plan_hash", trace.topology_plan_hash),
        ("/physical_scaling_hash", trace.physical_scaling_hash),
        ("/problem_contract_hash", trace.problem_contract_hash),
        ("/parent_checkpoint_hash", trace.parent_checkpoint_hash),
        ("/assembly_hash", trace.assembly_hash),
    ):
        _require_hash(value, path)
    _finite(trace.target_load_factor, "/target_load_factor")
    for path, value in (
        ("/raw_translation_linf_kn", trace.raw_translation_linf_kn),
        ("/raw_rotation_linf_kn_m", trace.raw_rotation_linf_kn_m),
        ("/scaled_linf", trace.scaled_linf),
        ("/scaled_l2", trace.scaled_l2),
    ):
        _nonnegative(value, path)
    governing_dof = _index(
        trace.governing_physical_dof,
        "/governing_physical_dof",
    )
    governing_node = _index(trace.governing_node_index, "/governing_node_index")
    if governing_node != governing_dof // 6:
        _fail(
            "fiber_frame_physical_trace_governing_node_mismatch",
            "/governing_node_index",
            "Governing node does not match the governing physical DOF.",
        )
    if (
        trace.governing_component
        != FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[governing_dof % 6]
    ):
        _fail(
            "fiber_frame_physical_trace_governing_component_mismatch",
            "/governing_component",
            "Governing component does not match the governing physical DOF.",
        )
    _validate_array_map(
        trace._arrays,
        trace.descriptors,
        _TRACE_ARRAY_SPECS,
        "/arrays",
    )
    if not isinstance(trace.extensions, MappingProxyType) or trace.extensions:
        _fail(
            "fiber_frame_physical_trace_extensions_invalid",
            "/extensions",
            "Physical residual trace v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_trace_payload(trace, include_hash=False))
    if trace.trace_hash != expected_hash:
        _fail(
            "fiber_frame_physical_trace_hash_mismatch",
            "/trace_hash",
            "Physical residual trace hash does not match canonical content.",
        )
    return trace


def validate_fiber_frame_physical_residual_trace_against_assembly(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    scaling: FiberFramePhysicalEquationScalingReceipt,
    assembly: StatefulFiberFrame2DAssembly,
    trace: FiberFramePhysicalResidualTrace,
) -> FiberFramePhysicalResidualTrace:
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        scaling,
    )
    validate_fiber_frame_physical_residual_trace(trace)
    if trace.topology_plan_hash != topology_plan.plan_hash:
        _fail(
            "fiber_frame_physical_trace_topology_mismatch",
            "/topology_plan_hash",
            "Residual trace belongs to another topology plan.",
        )
    if trace.physical_scaling_hash != scaling.scaling_hash:
        _fail(
            "fiber_frame_physical_trace_scaling_mismatch",
            "/physical_scaling_hash",
            "Residual trace belongs to another physical scaling receipt.",
        )
    if trace.problem_contract_hash != problem.contract_hash:
        _fail(
            "fiber_frame_physical_trace_problem_mismatch",
            "/problem_contract_hash",
            "Residual trace belongs to another frame problem.",
        )
    expected = create_fiber_frame_physical_residual_trace(
        problem,
        topology_plan,
        scaling,
        assembly,
        _skip_source_validation=True,
    )
    if expected.to_manifest() != trace.to_manifest():
        _fail(
            "fiber_frame_physical_trace_source_replay_mismatch",
            "/",
            "Residual trace does not replay from the supplied assembly.",
        )
    return trace


def validate_fiber_frame_physical_array_bytes(
    descriptors: tuple[FiberFramePhysicalArrayDescriptor, ...],
    *,
    name: str,
    payload: bytes,
) -> np.ndarray:
    if type(payload) is not bytes:
        _fail(
            "fiber_frame_physical_array_bytes_invalid",
            f"/arrays/{name}",
            "External array artifact must be immutable bytes.",
        )
    descriptor = _descriptor_by_name(descriptors, name)
    if len(payload) != descriptor.byte_length:
        _fail(
            "fiber_frame_physical_array_length_mismatch",
            f"/arrays/{name}",
            "External array artifact length does not match descriptor.",
        )
    array = np.frombuffer(payload, dtype=descriptor.dtype).reshape(descriptor.shape)
    immutable = immutable_array(array, dtype=descriptor.dtype)
    if array_data_hash(immutable) != descriptor.data_hash:
        _fail(
            "fiber_frame_physical_array_hash_mismatch",
            f"/arrays/{name}",
            "External array artifact hash does not match descriptor.",
        )
    return immutable


def validate_fiber_frame_physical_scaling_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return _validate_manifest(payload, kind="scaling")


def validate_fiber_frame_physical_residual_trace_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return _validate_manifest(payload, kind="trace")


def _validate_manifest(payload: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail(
            "fiber_frame_physical_manifest_type_invalid",
            "/",
            "Physical scaling/trace manifest must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFramePhysicalScalingError(
            "fiber_frame_physical_manifest_json_invalid",
            "/",
            "Manifest must be finite strict JSON.",
        ) from exc
    hash_key = "scaling_hash" if kind == "scaling" else "trace_hash"
    schema = (
        FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION
        if kind == "scaling"
        else FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION
    )
    if normalized.get("schema_version") != schema:
        _fail(
            "fiber_frame_physical_manifest_schema_invalid",
            "/schema_version",
            "Manifest schema does not match its declared kind.",
        )
    if normalized.get("authority_profile") != (
        FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_physical_manifest_authority_invalid",
            "/authority_profile",
            "Manifest cannot acquire result authority.",
        )
    if normalized.get("claim_boundary") != dict(
        FIBER_FRAME_PHYSICAL_SCALING_CLAIM_BOUNDARY
    ):
        _fail(
            "fiber_frame_physical_manifest_claim_boundary_invalid",
            "/claim_boundary",
            "Manifest claim boundary changed.",
        )
    if normalized.get("extensions") != {}:
        _fail(
            "fiber_frame_physical_manifest_extensions_invalid",
            "/extensions",
            "Manifest requires empty extensions.",
        )
    claimed_hash = _require_hash(normalized.get(hash_key), f"/{hash_key}")
    unsigned = dict(normalized)
    unsigned.pop(hash_key)
    if claimed_hash != canonical_hash(unsigned):
        _fail(
            "fiber_frame_physical_manifest_hash_mismatch",
            f"/{hash_key}",
            "Manifest hash does not match canonical content.",
        )
    return normalized


def _scaling_payload(
    receipt: FiberFramePhysicalEquationScalingReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "authority_profile": receipt.authority_profile,
        "scaling_profile": receipt.scaling_profile,
        "bindings": {
            "topology_plan_hash": receipt.topology_plan_hash,
            "problem_contract_hash": receipt.problem_contract_hash,
            "characteristic_length_source_hash": (
                receipt.characteristic_length_source_hash
            ),
        },
        "characteristic_length_m": receipt.characteristic_length_m,
        "force_reference_kn": receipt.force_reference_kn,
        "moment_reference_kn_m": receipt.moment_reference_kn_m,
        "physical_dof_count": receipt.physical_dof_count,
        "solver_dof_count": receipt.solver_dof_count,
        "array_descriptors": [row.to_dict() for row in receipt.descriptors],
        "claim_boundary": dict(FIBER_FRAME_PHYSICAL_SCALING_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if include_hash:
        payload["scaling_hash"] = receipt.scaling_hash
    return payload


def _trace_payload(
    trace: FiberFramePhysicalResidualTrace,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": trace.schema_version,
        "authority_profile": trace.authority_profile,
        "bindings": {
            "topology_plan_hash": trace.topology_plan_hash,
            "physical_scaling_hash": trace.physical_scaling_hash,
            "problem_contract_hash": trace.problem_contract_hash,
            "parent_checkpoint_hash": trace.parent_checkpoint_hash,
            "assembly_hash": trace.assembly_hash,
        },
        "target_load_factor": trace.target_load_factor,
        "norms": {
            "raw_translation_linf_kn": trace.raw_translation_linf_kn,
            "raw_rotation_linf_kn_m": trace.raw_rotation_linf_kn_m,
            "scaled_linf": trace.scaled_linf,
            "scaled_l2": trace.scaled_l2,
        },
        "governing": {
            "physical_dof": trace.governing_physical_dof,
            "node_index": trace.governing_node_index,
            "component": trace.governing_component,
        },
        "array_descriptors": [row.to_dict() for row in trace.descriptors],
        "claim_boundary": dict(FIBER_FRAME_PHYSICAL_SCALING_CLAIM_BOUNDARY),
        "extensions": dict(trace.extensions),
    }
    if include_hash:
        payload["trace_hash"] = trace.trace_hash
    return payload


def _validate_array_map(
    arrays: Mapping[str, np.ndarray],
    descriptors: tuple[FiberFramePhysicalArrayDescriptor, ...],
    specs: tuple[tuple[str, str], ...],
    path: str,
) -> None:
    names = tuple(name for name, _dtype in specs)
    if not isinstance(arrays, MappingProxyType) or tuple(arrays) != names:
        _fail(
            "fiber_frame_physical_array_set_invalid",
            path,
            "Array map must be immutable and use the exact ordered set.",
        )
    if (
        type(descriptors) is not tuple
        or tuple(row.name for row in descriptors) != names
    ):
        _fail(
            "fiber_frame_physical_descriptor_set_invalid",
            path,
            "Descriptor tuple does not match the exact ordered array set.",
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
                "fiber_frame_physical_array_contract_invalid",
                f"{path}/{name}",
                f"Expected immutable C-contiguous {dtype} array.",
            )
        if by_name[name] != _descriptor(name, array):
            _fail(
                "fiber_frame_physical_descriptor_mismatch",
                f"{path}/{name}",
                "Descriptor does not match retained array bytes.",
            )


def _descriptor(name: str, array: np.ndarray) -> FiberFramePhysicalArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return FiberFramePhysicalArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _descriptor_by_name(
    descriptors: tuple[FiberFramePhysicalArrayDescriptor, ...],
    name: str,
) -> FiberFramePhysicalArrayDescriptor:
    for descriptor in descriptors:
        if descriptor.name == name:
            return descriptor
    _fail(
        "fiber_frame_physical_descriptor_missing",
        f"/array_descriptors/{name}",
        "Required array descriptor is missing.",
    )


def _component_indices(node_count: int, components: tuple[int, ...]) -> np.ndarray:
    return np.asarray(
        [
            6 * node + component
            for node in range(node_count)
            for component in components
        ],
        dtype=np.int64,
    )


def _linf(values: np.ndarray) -> float:
    return float(np.linalg.norm(values, ord=np.inf)) if values.size else 0.0


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "fiber_frame_physical_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_physical_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _positive(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized <= 0.0:
        _fail(
            "fiber_frame_physical_number_not_positive",
            path,
            "Expected a positive number.",
        )
    return normalized


def _nonnegative(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized < 0.0:
        _fail(
            "fiber_frame_physical_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_physical_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "fiber_frame_physical_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFramePhysicalScalingError(code, path, message)


__all__ = [
    "FIBER_FRAME_PHYSICAL_EQUATION_SCALING_PROFILE",
    "FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION",
    "FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION",
    "FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE",
    "FIBER_FRAME_PHYSICAL_SCALING_CLAIM_BOUNDARY",
    "FiberFramePhysicalArrayDescriptor",
    "FiberFramePhysicalEquationScalingReceipt",
    "FiberFramePhysicalResidualTrace",
    "FiberFramePhysicalScalingError",
    "create_fiber_frame_physical_equation_scaling",
    "create_fiber_frame_physical_residual_trace",
    "validate_fiber_frame_physical_array_bytes",
    "validate_fiber_frame_physical_equation_scaling",
    "validate_fiber_frame_physical_equation_scaling_against_problem",
    "validate_fiber_frame_physical_residual_trace",
    "validate_fiber_frame_physical_residual_trace_against_assembly",
    "validate_fiber_frame_physical_residual_trace_manifest",
    "validate_fiber_frame_physical_scaling_manifest",
]
