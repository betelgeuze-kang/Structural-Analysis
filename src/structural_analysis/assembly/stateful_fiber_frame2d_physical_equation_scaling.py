"""Physical SI equation scaling for the bounded stateful fiber frame.

The frame source uses node-major ``[UX, UY, RZ]`` equations with forces in kN
and moments in kN*m.  This module adapts those source quantities into the
canonical six-DOF SI equation order owned by the nonlinear execution-topology
plan and embeds an unchanged Engine v2 ``EquationScaling v1`` artifact.

The binding and residual trace are preprocessing/observation contracts only.
They do not decide convergence, execute a backend, create a nonlinear state,
or grant numerical-result, engineering, design, release, or commercial
authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
    FIBER_FRAME_PHYSICAL_DOF_COMPONENTS,
    FIBER_FRAME_SOLVER_DOF_COMPONENTS,
    FiberFrame2DTopologyProblem,
    FiberFrameNonlinearExecutionTopologyPlan,
    physical_3dof_to_canonical_6dof,
    validate_fiber_frame_execution_topology_against_problem,
    validate_fiber_frame_execution_topology_plan,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    CHARACTERISTIC_LENGTH_POLICY,
    EQUATION_SCALING_SCHEMA_VERSION,
    REFERENCE_EQUATION_SCOPE,
    REFERENCE_FORCE_POLICY,
    EquationScaling,
    _scaling_payload as _engine_scaling_payload,
    _source_commitment_payload as _engine_source_commitment_payload,
    validate_equation_scaling,
    validate_equation_scaling_manifest,
)


FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-physical-equation-scaling-binding.v1"
)
FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-physical-residual-trace.v1"
)
FIBER_FRAME_PHYSICAL_EQUATION_SCALING_AUTHORITY_PROFILE = (
    "non_authoritative_physical_equation_scaling.v1"
)
FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_AUTHORITY_PROFILE = (
    "non_authoritative_physical_residual_observation.v1"
)
FIBER_FRAME_EQUATION_SCALING_SOURCE_PROFILE = (
    "structural-analysis-equation-scaling.v1/source_commitment"
)
FIBER_FRAME_SOURCE_UNIT_PROFILE = "stateful_fiber_frame2d_kn_kn_m_to_si.v1"
FIBER_FRAME_SOURCE_FORCE_UNIT = "kN"
FIBER_FRAME_SOURCE_MOMENT_UNIT = "kN*m"
FIBER_FRAME_TARGET_FORCE_UNIT = "N"
FIBER_FRAME_TARGET_MOMENT_UNIT = "N*m"
FIBER_FRAME_FORCE_TO_SI = 1000.0
FIBER_FRAME_MOMENT_TO_SI = 1000.0

FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY = MappingProxyType(
    {
        "topology_plan_bound": True,
        "engine_equation_scaling_v1_bound": True,
        "engine_source_commitment_replay_bound": True,
        "physical_force_moment_si_scaling_bound": True,
        "source_unit_conversion_bound": True,
        "residual_trace_bound": False,
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
FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY = MappingProxyType(
    {
        **dict(FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY),
        "residual_trace_bound": True,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1

_SCALING_ARRAY_NAMES = (
    "node_coordinates_m",
    "reference_equation_load_si",
    "scale_divisors_si",
)
_TRACE_ARRAY_NAMES = (
    "raw_residual_source_3dof",
    "raw_residual_si_6dof",
    "scaled_residual_6dof",
)


class FiberFramePhysicalEquationScalingError(ValueError):
    """Fail-closed physical-scaling error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFramePhysicalScalingArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    equation_order_hash: str
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "equation_order_hash": self.equation_order_hash,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class FiberFramePhysicalEquationScalingBinding:
    """Typed adapter from the nonlinear topology plan to EquationScaling v1."""

    schema_version: str
    binding_hash: str
    authority_profile: str
    topology_plan_hash: str
    problem_contract_hash: str
    topology_free_physical_dofs_content_hash: str
    source_unit_profile: str
    engine_scaling: EquationScaling = field(repr=False, compare=False)
    descriptors: tuple[FiberFramePhysicalScalingArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    @property
    def engine_equation_scaling_hash(self) -> str:
        return self.engine_scaling.scaling_hash

    @property
    def engine_source_commitment_hash(self) -> str:
        return self.engine_scaling.source_commitment_hash

    @property
    def equation_order_hash(self) -> str:
        return self.engine_scaling.equation_order_hash

    @property
    def characteristic_length_m(self) -> float:
        return self.engine_scaling.characteristic_length_m

    @property
    def reference_force_n(self) -> float:
        return self.engine_scaling.reference_force_n

    @property
    def scale_divisors_si(self) -> np.ndarray:
        return self.array("scale_divisors_si")

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown physical equation-scaling array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_physical_equation_scaling_binding(self)
        return _binding_payload(self, include_binding_hash=True)


@dataclass(frozen=True)
class FiberFramePhysicalResidualTrace:
    """Non-authoritative raw SI and dimensionless residual observation."""

    schema_version: str
    trace_hash: str
    authority_profile: str
    topology_plan_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    engine_source_commitment_hash: str
    problem_contract_hash: str
    equation_order_hash: str
    solver_physical_equation_order_hash: str
    node_ids: tuple[str, ...]
    residual_sign: str
    equation_scope: str
    source_unit_profile: str
    active_equations: tuple[int, ...]
    characteristic_length_m: float
    reference_force_n: float
    raw_translation_l2_n: float
    raw_translation_linf_n: float
    raw_rotation_l2_nm: float
    raw_rotation_linf_nm: float
    scaled_l2: float
    scaled_linf: float
    governing_equation: int
    governing_node_id: str
    governing_dof: str
    descriptors: tuple[FiberFramePhysicalScalingArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    @property
    def raw_residual_source_3dof(self) -> np.ndarray:
        return self.array("raw_residual_source_3dof")

    @property
    def raw_residual_si_6dof(self) -> np.ndarray:
        return self.array("raw_residual_si_6dof")

    @property
    def scaled_residual_6dof(self) -> np.ndarray:
        return self.array("scaled_residual_6dof")

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown physical residual-trace array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_physical_residual_trace(self)
        return _trace_payload(self, include_trace_hash=True)


def create_stateful_fiber_frame2d_physical_equation_scaling(
    problem: FiberFrame2DTopologyProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    *,
    minimum_characteristic_length_m: float = 1.0e-12,
    minimum_reference_force_n: float = 1.0,
) -> FiberFramePhysicalEquationScalingBinding:
    """Create a replayable physical N/N*m scaling binding for the J1 plan."""

    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    minimum_length = _positive_float(
        minimum_characteristic_length_m,
        "/minimum_characteristic_length_m",
    )
    minimum_force = _positive_float(
        minimum_reference_force_n,
        "/minimum_reference_force_n",
    )
    scaling, arrays, descriptors = _derive_engine_scaling(
        topology_plan,
        minimum_characteristic_length_m=minimum_length,
        minimum_reference_force_n=minimum_force,
    )
    topology_free_hash = _topology_descriptor(
        topology_plan, "free_physical_dofs"
    ).content_hash
    provisional = FiberFramePhysicalEquationScalingBinding(
        schema_version=FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION,
        binding_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_PHYSICAL_EQUATION_SCALING_AUTHORITY_PROFILE,
        topology_plan_hash=topology_plan.plan_hash,
        problem_contract_hash=problem.contract_hash,
        topology_free_physical_dofs_content_hash=topology_free_hash,
        source_unit_profile=FIBER_FRAME_SOURCE_UNIT_PROFILE,
        engine_scaling=scaling,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    binding = replace(
        provisional,
        binding_hash=canonical_hash(
            _binding_payload(provisional, include_binding_hash=False)
        ),
    )
    validate_fiber_frame_physical_equation_scaling_binding(binding)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        binding,
    )
    return binding


def trace_stateful_fiber_frame2d_physical_residual(
    *,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    scaling_binding: FiberFramePhysicalEquationScalingBinding,
    raw_residual_source_3dof: Any,
) -> FiberFramePhysicalResidualTrace:
    """Trace one source kN/kN*m residual in canonical SI equation order."""

    plan = validate_fiber_frame_execution_topology_plan(topology_plan)
    binding = validate_fiber_frame_physical_equation_scaling_binding(
        scaling_binding,
        topology_plan=plan,
    )
    source = _float_array(
        raw_residual_source_3dof,
        shape=(plan.solver_dof_count,),
        path="/raw_residual_source_3dof",
    )
    canonical_source = physical_3dof_to_canonical_6dof(plan, source)
    raw_si_values = np.asarray(canonical_source, dtype="<f8").reshape((-1, 6)).copy()
    raw_si_values[:, :3] *= FIBER_FRAME_FORCE_TO_SI
    raw_si_values[:, 3:] *= FIBER_FRAME_MOMENT_TO_SI
    raw_si = _immutable_float_array(
        raw_si_values.reshape(-1),
        "/raw_residual_si_6dof",
    )
    scaled = _immutable_float_array(
        raw_si / binding.scale_divisors_si,
        "/scaled_residual_6dof",
    )
    active = tuple(int(value) for value in plan.array("free_physical_dofs"))
    _require_nonempty_active_equations(active, plan.physical_dof_count)
    translation = tuple(index for index in active if index % 6 < 3)
    rotation = tuple(index for index in active if index % 6 >= 3)
    active_scaled = scaled[list(active)]
    governing = active[int(np.argmax(np.abs(active_scaled)))]
    governing_node = governing // 6
    governing_component = governing % 6
    solver_order_hash = _solver_physical_equation_order_hash(plan)
    arrays = _freeze_array_map(
        {
            "raw_residual_source_3dof": source,
            "raw_residual_si_6dof": raw_si,
            "scaled_residual_6dof": scaled,
        }
    )
    descriptors = tuple(
        _array_descriptor(
            name,
            arrays[name],
            solver_order_hash
            if name == "raw_residual_source_3dof"
            else binding.equation_order_hash,
        )
        for name in _TRACE_ARRAY_NAMES
    )
    provisional = FiberFramePhysicalResidualTrace(
        schema_version=FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
        trace_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_AUTHORITY_PROFILE,
        topology_plan_hash=plan.plan_hash,
        physical_equation_scaling_binding_hash=binding.binding_hash,
        engine_equation_scaling_hash=binding.engine_equation_scaling_hash,
        engine_source_commitment_hash=binding.engine_source_commitment_hash,
        problem_contract_hash=binding.problem_contract_hash,
        equation_order_hash=binding.equation_order_hash,
        solver_physical_equation_order_hash=solver_order_hash,
        node_ids=plan.node_ids,
        residual_sign="internal_minus_external",
        equation_scope=REFERENCE_EQUATION_SCOPE,
        source_unit_profile=FIBER_FRAME_SOURCE_UNIT_PROFILE,
        active_equations=active,
        characteristic_length_m=binding.characteristic_length_m,
        reference_force_n=binding.reference_force_n,
        raw_translation_l2_n=_stable_l2(raw_si[list(translation)]),
        raw_translation_linf_n=_linf(raw_si[list(translation)]),
        raw_rotation_l2_nm=_stable_l2(raw_si[list(rotation)]),
        raw_rotation_linf_nm=_linf(raw_si[list(rotation)]),
        scaled_l2=_stable_l2(active_scaled),
        scaled_linf=_linf(active_scaled),
        governing_equation=governing,
        governing_node_id=plan.node_ids[governing_node],
        governing_dof=FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[governing_component],
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    trace = replace(
        provisional,
        trace_hash=canonical_hash(
            _trace_payload(provisional, include_trace_hash=False)
        ),
    )
    return validate_fiber_frame_physical_residual_trace(
        trace,
        topology_plan=plan,
        scaling_binding=binding,
    )


def trace_stateful_fiber_frame2d_free_physical_residual(
    *,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    scaling_binding: FiberFramePhysicalEquationScalingBinding,
    raw_free_residual_source_3dof: Any,
) -> FiberFramePhysicalResidualTrace:
    """Trace an exact free-equation residual without inventing constrained values.

    The source vector is scattered through the topology plan's explicit free
    solver-equation map. Zeros outside that map are padding outside the trace's
    declared ``free_equations`` scope and carry no reaction authority.
    """

    plan = validate_fiber_frame_execution_topology_plan(topology_plan)
    free_solver_dofs = plan.array("free_solver_dofs")
    free = _float_array(
        raw_free_residual_source_3dof,
        shape=(free_solver_dofs.size,),
        path="/raw_free_residual_source_3dof",
    )
    global_source = np.zeros(plan.solver_dof_count, dtype="<f8")
    global_source[free_solver_dofs] = free
    return trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=plan,
        scaling_binding=scaling_binding,
        raw_residual_source_3dof=global_source,
    )


def validate_fiber_frame_physical_equation_scaling_binding(
    binding: FiberFramePhysicalEquationScalingBinding,
    *,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan | None = None,
) -> FiberFramePhysicalEquationScalingBinding:
    """Validate self-contained Engine v2 scaling and optional J1 plan binding."""

    if type(binding) is not FiberFramePhysicalEquationScalingBinding:
        _fail("fiber_frame_physical_scaling_type_invalid", "/", "Expected binding.")
    if binding.schema_version != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_scaling_schema_invalid",
            "/schema_version",
            "Unsupported physical equation-scaling binding schema.",
        )
    if (
        binding.authority_profile
        != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_physical_scaling_authority_invalid",
            "/authority_profile",
            "Physical scaling cannot acquire solver or result authority.",
        )
    if binding.source_unit_profile != FIBER_FRAME_SOURCE_UNIT_PROFILE:
        _fail(
            "fiber_frame_physical_scaling_unit_profile_invalid",
            "/source_units/profile",
            "Unsupported source-unit conversion profile.",
        )
    for path, value in (
        ("/binding_hash", binding.binding_hash),
        ("/bindings/topology_plan_hash", binding.topology_plan_hash),
        ("/bindings/problem_contract_hash", binding.problem_contract_hash),
        (
            "/bindings/topology_free_physical_dofs_content_hash",
            binding.topology_free_physical_dofs_content_hash,
        ),
    ):
        _require_hash(value, path)
    scaling = validate_equation_scaling(binding.engine_scaling)
    if scaling.schema_version != EQUATION_SCALING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_scaling_engine_schema_invalid",
            "/engine_v2_equation_scaling/schema_version",
            "The binding requires unchanged EquationScaling v1.",
        )
    if scaling.base_plan_hash != binding.topology_plan_hash:
        _fail(
            "fiber_frame_physical_scaling_base_plan_mismatch",
            "/engine_v2_equation_scaling/base_plan_hash",
            "Engine scaling must bind the exact nonlinear topology plan hash.",
        )
    if binding.problem_contract_hash == _HASH_ZERO:
        _fail(
            "fiber_frame_physical_scaling_problem_invalid",
            "/bindings/problem_contract_hash",
            "Problem identity cannot use the zero hash.",
        )
    _validate_array_map(binding._arrays, binding.descriptors, _SCALING_ARRAY_NAMES)
    source = _engine_source_commitment_payload(scaling, include_commitment_hash=True)
    engine_manifest = scaling.to_manifest()
    descriptor_map = {descriptor.name: descriptor for descriptor in binding.descriptors}
    if descriptor_map["node_coordinates_m"].to_dict() != source["node_coordinates"]:
        _fail(
            "fiber_frame_physical_scaling_source_descriptor_mismatch",
            "/array_descriptors/node_coordinates_m",
            "Coordinate descriptor differs from EquationScaling source commitment.",
        )
    if (
        descriptor_map["reference_equation_load_si"].to_dict()
        != source["reference_equation_load"]
    ):
        _fail(
            "fiber_frame_physical_scaling_source_descriptor_mismatch",
            "/array_descriptors/reference_equation_load_si",
            "Reference-load descriptor differs from the source commitment.",
        )
    if descriptor_map["scale_divisors_si"].to_dict() != _engine_scale_descriptor(
        engine_manifest
    ):
        _fail(
            "fiber_frame_physical_scaling_scale_descriptor_mismatch",
            "/array_descriptors/scale_divisors_si",
            "Scale descriptor differs from EquationScaling v1.",
        )
    if not np.array_equal(
        binding.array("scale_divisors_si"), scaling.scale_divisors_si
    ):
        _fail(
            "fiber_frame_physical_scaling_scale_array_mismatch",
            "/arrays/scale_divisors_si",
            "Retained scale bytes differ from EquationScaling v1.",
        )
    if not isinstance(binding.extensions, MappingProxyType) or binding.extensions:
        _fail(
            "fiber_frame_physical_scaling_extensions_invalid",
            "/extensions",
            "Binding v1 requires immutable empty extensions.",
        )
    validate_fiber_frame_physical_equation_scaling_manifest(
        _binding_payload(binding, include_binding_hash=True)
    )
    expected_hash = canonical_hash(
        _binding_payload(binding, include_binding_hash=False)
    )
    if binding.binding_hash != expected_hash:
        _fail(
            "fiber_frame_physical_scaling_binding_hash_mismatch",
            "/binding_hash",
            "Binding hash is stale.",
        )
    if topology_plan is not None:
        plan = validate_fiber_frame_execution_topology_plan(topology_plan)
        if binding.topology_plan_hash != plan.plan_hash:
            _fail(
                "fiber_frame_physical_scaling_topology_mismatch",
                "/bindings/topology_plan_hash",
                "Binding identifies another topology plan.",
            )
        if binding.problem_contract_hash != plan.problem_contract_hash:
            _fail(
                "fiber_frame_physical_scaling_problem_mismatch",
                "/bindings/problem_contract_hash",
                "Binding identifies another frame problem.",
            )
        if scaling.equation_order_hash != _physical_equation_order_hash(plan):
            _fail(
                "fiber_frame_physical_scaling_equation_order_mismatch",
                "/engine_v2_equation_scaling/equation_order_hash",
                "Equation order differs from the topology plan.",
            )
        topology_free_hash = _topology_descriptor(
            plan, "free_physical_dofs"
        ).content_hash
        if binding.topology_free_physical_dofs_content_hash != topology_free_hash:
            _fail(
                "fiber_frame_physical_scaling_free_partition_mismatch",
                "/bindings/topology_free_physical_dofs_content_hash",
                "Topology free-equation partition is stale.",
            )
        expected_engine_free_hash = _engine_free_dofs_content_hash(
            plan.array("free_physical_dofs")
        )
        if scaling.source_free_dofs_content_hash != expected_engine_free_hash:
            _fail(
                "fiber_frame_physical_scaling_engine_free_partition_mismatch",
                "/engine_v2_equation_scaling/source_commitment/free_dofs_content_hash",
                "Engine source commitment has another free-equation partition.",
            )
        if scaling.source_model_ir_content_hash != plan.model_ir_content_hash:
            _fail(
                "fiber_frame_physical_scaling_model_ir_mismatch",
                "/engine_v2_equation_scaling/source_commitment/model_ir_content_hash",
                "Engine source commitment identifies another ModelIR.",
            )
        if scaling.source_load_pattern_id != plan.case_id:
            _fail(
                "fiber_frame_physical_scaling_case_id_mismatch",
                "/engine_v2_equation_scaling/source_commitment/load_pattern_id",
                "Engine source commitment identifies another load case.",
            )
        if scaling.dof_count != plan.physical_dof_count:
            _fail(
                "fiber_frame_physical_scaling_dof_count_mismatch",
                "/engine_v2_equation_scaling/dof_count",
                "Engine scaling has another physical equation count.",
            )
        expected_scaling, expected_arrays, expected_descriptors = (
            _derive_engine_scaling(
                plan,
                minimum_characteristic_length_m=(
                    scaling.minimum_characteristic_length_m
                ),
                minimum_reference_force_n=scaling.minimum_reference_force_n,
            )
        )
        if scaling.to_manifest() != expected_scaling.to_manifest():
            _fail(
                "fiber_frame_physical_scaling_source_replay_mismatch",
                "/engine_v2_equation_scaling",
                "EquationScaling v1 does not replay from the topology sources.",
            )
        if binding.descriptors != expected_descriptors:
            _fail(
                "fiber_frame_physical_scaling_descriptor_replay_mismatch",
                "/array_descriptors",
                "Array descriptors do not replay from the topology sources.",
            )
        for name in _SCALING_ARRAY_NAMES:
            if not np.array_equal(binding.array(name), expected_arrays[name]):
                _fail(
                    "fiber_frame_physical_scaling_array_replay_mismatch",
                    f"/arrays/{name}",
                    "Retained array does not replay from the topology sources.",
                )
    return binding


def validate_fiber_frame_physical_equation_scaling_against_problem(
    problem: FiberFrame2DTopologyProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    binding: FiberFramePhysicalEquationScalingBinding,
) -> FiberFramePhysicalEquationScalingBinding:
    """Replay geometry, loads, units, free partition, policies, and scale bytes."""

    plan = validate_fiber_frame_execution_topology_plan(topology_plan)
    validated_binding = validate_fiber_frame_physical_equation_scaling_binding(binding)
    if (
        plan.problem_contract_hash != problem.contract_hash
        or validated_binding.problem_contract_hash != problem.contract_hash
    ):
        _fail(
            "fiber_frame_physical_scaling_problem_mismatch",
            "/bindings/problem_contract_hash",
            "Binding and topology plan must identify the supplied problem.",
        )
    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    return validate_fiber_frame_physical_equation_scaling_binding(
        validated_binding,
        topology_plan=plan,
    )


def validate_fiber_frame_physical_residual_trace(
    trace: FiberFramePhysicalResidualTrace,
    *,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan | None = None,
    scaling_binding: FiberFramePhysicalEquationScalingBinding | None = None,
) -> FiberFramePhysicalResidualTrace:
    """Validate trace arrays, SI conversion, norms, governing DOF, and bindings."""

    if type(trace) is not FiberFramePhysicalResidualTrace:
        _fail("fiber_frame_physical_trace_type_invalid", "/", "Expected trace.")
    if trace.schema_version != FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_trace_schema_invalid",
            "/schema_version",
            "Unsupported physical residual-trace schema.",
        )
    if trace.authority_profile != FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_physical_trace_authority_invalid",
            "/authority_profile",
            "Residual observation cannot acquire convergence or result authority.",
        )
    if trace.residual_sign != "internal_minus_external":
        _fail(
            "fiber_frame_physical_trace_sign_invalid",
            "/observation/residual_sign",
            "Unsupported residual sign.",
        )
    if trace.equation_scope != REFERENCE_EQUATION_SCOPE:
        _fail(
            "fiber_frame_physical_trace_scope_invalid",
            "/observation/equation_scope",
            "Only exact free-equation observation is supported.",
        )
    if trace.source_unit_profile != FIBER_FRAME_SOURCE_UNIT_PROFILE:
        _fail(
            "fiber_frame_physical_trace_unit_profile_invalid",
            "/source_units/profile",
            "Unsupported source-unit conversion profile.",
        )
    for path, value in (
        ("/trace_hash", trace.trace_hash),
        ("/bindings/topology_plan_hash", trace.topology_plan_hash),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            trace.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/engine_equation_scaling_hash",
            trace.engine_equation_scaling_hash,
        ),
        (
            "/bindings/engine_source_commitment_hash",
            trace.engine_source_commitment_hash,
        ),
        ("/bindings/problem_contract_hash", trace.problem_contract_hash),
        ("/bindings/equation_order_hash", trace.equation_order_hash),
        (
            "/bindings/solver_physical_equation_order_hash",
            trace.solver_physical_equation_order_hash,
        ),
    ):
        _require_hash(value, path)
    if type(trace.node_ids) is not tuple:
        _fail(
            "fiber_frame_physical_trace_node_order_invalid",
            "/entity_order/node_ids",
            "In-memory node IDs must be an immutable tuple.",
        )
    nodes = _stable_id_tuple(trace.node_ids, "/entity_order/node_ids")
    if len(set(nodes)) != len(nodes) or not nodes:
        _fail(
            "fiber_frame_physical_trace_node_order_invalid",
            "/entity_order/node_ids",
            "Node IDs must be nonempty and unique.",
        )
    physical_count = 6 * len(nodes)
    solver_count = 3 * len(nodes)
    if type(trace.active_equations) is not tuple:
        _fail(
            "fiber_frame_physical_trace_active_equations_invalid",
            "/observation/active_equations",
            "In-memory active equations must be an immutable tuple.",
        )
    active = _active_equations(trace.active_equations, physical_count)
    _validate_array_map(trace._arrays, trace.descriptors, _TRACE_ARRAY_NAMES)
    if trace.array("raw_residual_source_3dof").shape != (solver_count,):
        _fail(
            "fiber_frame_physical_trace_shape_invalid",
            "/arrays/raw_residual_source_3dof",
            "Source residual must have three equations per node.",
        )
    for name in ("raw_residual_si_6dof", "scaled_residual_6dof"):
        if trace.array(name).shape != (physical_count,):
            _fail(
                "fiber_frame_physical_trace_shape_invalid",
                f"/arrays/{name}",
                "Canonical residual must have six equations per node.",
            )
    expected_source_order_hash = canonical_hash(
        {
            "node_ids": list(nodes),
            "dof_components": list(FIBER_FRAME_SOLVER_DOF_COMPONENTS),
            "dof_count": solver_count,
        }
    )
    if trace.solver_physical_equation_order_hash != expected_source_order_hash:
        _fail(
            "fiber_frame_physical_trace_solver_order_mismatch",
            "/bindings/solver_physical_equation_order_hash",
            "Source residual order is stale.",
        )
    source = trace.raw_residual_source_3dof.reshape((-1, 3))
    expected_si = np.zeros((len(nodes), 6), dtype="<f8")
    expected_si[:, 0] = source[:, 0] * FIBER_FRAME_FORCE_TO_SI
    expected_si[:, 1] = source[:, 1] * FIBER_FRAME_FORCE_TO_SI
    expected_si[:, 5] = source[:, 2] * FIBER_FRAME_MOMENT_TO_SI
    if not np.array_equal(trace.raw_residual_si_6dof, expected_si.reshape(-1)):
        _fail(
            "fiber_frame_physical_trace_si_conversion_mismatch",
            "/arrays/raw_residual_si_6dof",
            "Canonical SI residual does not replay from source kN/kN*m values.",
        )
    for name, expected_order in (
        ("raw_residual_source_3dof", trace.solver_physical_equation_order_hash),
        ("raw_residual_si_6dof", trace.equation_order_hash),
        ("scaled_residual_6dof", trace.equation_order_hash),
    ):
        if (
            _descriptor_by_name(trace.descriptors, name).equation_order_hash
            != expected_order
        ):
            _fail(
                "fiber_frame_physical_trace_descriptor_order_mismatch",
                f"/array_descriptors/{name}/equation_order_hash",
                "Array descriptor uses another equation order.",
            )
    _positive_float(trace.characteristic_length_m, "/scales/characteristic_length_m")
    _positive_float(trace.reference_force_n, "/scales/reference_force_n")
    translation = tuple(index for index in active if index % 6 < 3)
    rotation = tuple(index for index in active if index % 6 >= 3)
    raw_si = trace.raw_residual_si_6dof
    scaled = trace.scaled_residual_6dof
    metrics = (
        _stable_l2(raw_si[list(translation)]),
        _linf(raw_si[list(translation)]),
        _stable_l2(raw_si[list(rotation)]),
        _linf(raw_si[list(rotation)]),
        _stable_l2(scaled[list(active)]),
        _linf(scaled[list(active)]),
    )
    claimed = (
        trace.raw_translation_l2_n,
        trace.raw_translation_linf_n,
        trace.raw_rotation_l2_nm,
        trace.raw_rotation_linf_nm,
        trace.scaled_l2,
        trace.scaled_linf,
    )
    if claimed != metrics:
        _fail(
            "fiber_frame_physical_trace_norm_mismatch",
            "/norms",
            "Dimensional or scaled residual norms are stale.",
        )
    governing = active[int(np.argmax(np.abs(scaled[list(active)])))]
    _index(trace.governing_equation, "/governing/equation")
    _stable_id(trace.governing_node_id, "/governing/node_id")
    _stable_id(trace.governing_dof, "/governing/dof")
    expected_governing = (
        governing,
        nodes[governing // 6],
        FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[governing % 6],
    )
    if (
        trace.governing_equation,
        trace.governing_node_id,
        trace.governing_dof,
    ) != expected_governing:
        _fail(
            "fiber_frame_physical_trace_governing_mismatch",
            "/governing",
            "Governing scaled equation is stale.",
        )
    if not isinstance(trace.extensions, MappingProxyType) or trace.extensions:
        _fail(
            "fiber_frame_physical_trace_extensions_invalid",
            "/extensions",
            "Residual-trace v1 requires immutable empty extensions.",
        )
    validate_fiber_frame_physical_residual_trace_manifest(
        _trace_payload(trace, include_trace_hash=True)
    )
    expected_hash = canonical_hash(_trace_payload(trace, include_trace_hash=False))
    if trace.trace_hash != expected_hash:
        _fail(
            "fiber_frame_physical_trace_hash_mismatch",
            "/trace_hash",
            "Residual trace hash is stale.",
        )
    if (topology_plan is None) != (scaling_binding is None):
        _fail(
            "fiber_frame_physical_trace_binding_inputs_incomplete",
            "/bindings",
            "Topology plan and scaling binding must be supplied together.",
        )
    if topology_plan is not None and scaling_binding is not None:
        plan = validate_fiber_frame_execution_topology_plan(topology_plan)
        binding = validate_fiber_frame_physical_equation_scaling_binding(
            scaling_binding,
            topology_plan=plan,
        )
        expected_bindings = (
            plan.plan_hash,
            binding.binding_hash,
            binding.engine_equation_scaling_hash,
            binding.engine_source_commitment_hash,
            binding.problem_contract_hash,
            binding.equation_order_hash,
            _solver_physical_equation_order_hash(plan),
            plan.node_ids,
        )
        claimed_bindings = (
            trace.topology_plan_hash,
            trace.physical_equation_scaling_binding_hash,
            trace.engine_equation_scaling_hash,
            trace.engine_source_commitment_hash,
            trace.problem_contract_hash,
            trace.equation_order_hash,
            trace.solver_physical_equation_order_hash,
            trace.node_ids,
        )
        if claimed_bindings != expected_bindings:
            _fail(
                "fiber_frame_physical_trace_binding_mismatch",
                "/bindings",
                "Trace binds different topology or scaling artifacts.",
            )
        expected_active = tuple(
            int(value) for value in plan.array("free_physical_dofs")
        )
        if active != expected_active:
            _fail(
                "fiber_frame_physical_trace_active_equations_mismatch",
                "/observation/active_equations",
                "Trace scope must exactly equal the topology free equations.",
            )
        if not np.array_equal(
            scaled,
            raw_si / binding.scale_divisors_si,
        ):
            _fail(
                "fiber_frame_physical_trace_scaled_residual_mismatch",
                "/arrays/scaled_residual_6dof",
                "Scaled residual does not match the bound SI divisors.",
            )
        if (
            trace.characteristic_length_m != binding.characteristic_length_m
            or trace.reference_force_n != binding.reference_force_n
        ):
            _fail(
                "fiber_frame_physical_trace_scale_summary_mismatch",
                "/scales",
                "Trace scale summary differs from the bound scaling artifact.",
            )
    return trace


def validate_fiber_frame_physical_equation_scaling_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate descriptor-only binding manifests without claiming source bytes."""

    manifest = _manifest_object(payload, "/")
    _exact_keys(
        manifest,
        {
            "schema_version",
            "binding_hash",
            "authority_profile",
            "bindings",
            "source_units",
            "engine_v2_equation_scaling",
            "array_descriptors",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_physical_scaling_manifest_schema_invalid",
            "/schema_version",
            "Unsupported binding manifest schema.",
        )
    if (
        manifest["authority_profile"]
        != FIBER_FRAME_PHYSICAL_EQUATION_SCALING_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_physical_scaling_manifest_authority_invalid",
            "/authority_profile",
            "Manifest cannot acquire solver or result authority.",
        )
    _require_hash(manifest["binding_hash"], "/binding_hash")
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "topology_schema_version",
            "topology_plan_hash",
            "problem_contract_hash",
            "topology_free_physical_dofs_content_hash",
            "engine_equation_scaling_schema_version",
            "engine_equation_scaling_hash",
            "engine_source_commitment_profile",
            "engine_source_commitment_hash",
        },
        "/bindings",
    )
    if (
        bindings["topology_schema_version"]
        != FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_physical_scaling_topology_schema_invalid",
            "/bindings/topology_schema_version",
            "Binding requires the J1 topology-plan schema.",
        )
    if (
        bindings["engine_equation_scaling_schema_version"]
        != EQUATION_SCALING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_physical_scaling_engine_schema_invalid",
            "/bindings/engine_equation_scaling_schema_version",
            "Binding requires unchanged EquationScaling v1.",
        )
    if (
        bindings["engine_source_commitment_profile"]
        != FIBER_FRAME_EQUATION_SCALING_SOURCE_PROFILE
    ):
        _fail(
            "fiber_frame_physical_scaling_source_profile_invalid",
            "/bindings/engine_source_commitment_profile",
            "Unsupported Engine v2 source-commitment profile.",
        )
    for key in (
        "topology_plan_hash",
        "problem_contract_hash",
        "topology_free_physical_dofs_content_hash",
        "engine_equation_scaling_hash",
        "engine_source_commitment_hash",
    ):
        _require_hash(bindings[key], f"/bindings/{key}")
    if bindings["problem_contract_hash"] == _HASH_ZERO:
        _fail(
            "fiber_frame_physical_scaling_problem_invalid",
            "/bindings/problem_contract_hash",
            "Problem identity cannot use the zero hash.",
        )
    _validate_source_units_manifest(manifest["source_units"])
    engine = _manifest_object(
        manifest["engine_v2_equation_scaling"],
        "/engine_v2_equation_scaling",
    )
    validate_equation_scaling_manifest(engine)
    if engine["base_plan_hash"] != bindings["topology_plan_hash"]:
        _fail(
            "fiber_frame_physical_scaling_base_plan_mismatch",
            "/engine_v2_equation_scaling/base_plan_hash",
            "Engine scaling identifies another topology plan.",
        )
    if engine["scaling_hash"] != bindings["engine_equation_scaling_hash"]:
        _fail(
            "fiber_frame_physical_scaling_engine_hash_mismatch",
            "/bindings/engine_equation_scaling_hash",
            "Engine scaling hash binding is stale.",
        )
    if (
        engine["source_commitment"]["commitment_hash"]
        != bindings["engine_source_commitment_hash"]
    ):
        _fail(
            "fiber_frame_physical_scaling_source_hash_mismatch",
            "/bindings/engine_source_commitment_hash",
            "Engine source-commitment binding is stale.",
        )
    descriptors = _manifest_object(manifest["array_descriptors"], "/array_descriptors")
    _exact_keys(descriptors, set(_SCALING_ARRAY_NAMES), "/array_descriptors")
    for name in _SCALING_ARRAY_NAMES:
        _validate_descriptor_manifest(descriptors[name], name=name)
    if (
        descriptors["node_coordinates_m"]
        != engine["source_commitment"]["node_coordinates"]
    ):
        _fail(
            "fiber_frame_physical_scaling_source_descriptor_mismatch",
            "/array_descriptors/node_coordinates_m",
            "Coordinate descriptor differs from the Engine source commitment.",
        )
    if (
        descriptors["reference_equation_load_si"]
        != engine["source_commitment"]["reference_equation_load"]
    ):
        _fail(
            "fiber_frame_physical_scaling_source_descriptor_mismatch",
            "/array_descriptors/reference_equation_load_si",
            "Load descriptor differs from the Engine source commitment.",
        )
    if descriptors["scale_divisors_si"] != _engine_scale_descriptor(engine):
        _fail(
            "fiber_frame_physical_scaling_scale_descriptor_mismatch",
            "/array_descriptors/scale_divisors_si",
            "Scale descriptor differs from EquationScaling v1.",
        )
    _validate_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    extensions = _manifest_object(manifest["extensions"], "/extensions")
    if extensions:
        _fail(
            "fiber_frame_physical_scaling_extensions_invalid",
            "/extensions",
            "Binding v1 requires empty extensions.",
        )
    without_hash = dict(manifest)
    claimed_hash = without_hash.pop("binding_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "fiber_frame_physical_scaling_binding_hash_mismatch",
            "/binding_hash",
            "Manifest binding hash is stale.",
        )
    return manifest


def validate_fiber_frame_physical_residual_trace_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate trace manifest vectors and all dimensional/scaled observations."""

    manifest = _manifest_object(payload, "/")
    _exact_keys(
        manifest,
        {
            "schema_version",
            "trace_hash",
            "authority_profile",
            "bindings",
            "entity_order",
            "source_units",
            "observation",
            "scales",
            "norms",
            "governing",
            "array_descriptors",
            "vectors",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if manifest["schema_version"] != FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION:
        _fail(
            "fiber_frame_physical_trace_manifest_schema_invalid",
            "/schema_version",
            "Unsupported residual-trace manifest schema.",
        )
    if (
        manifest["authority_profile"]
        != FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_physical_trace_manifest_authority_invalid",
            "/authority_profile",
            "Trace cannot acquire convergence or result authority.",
        )
    _require_hash(manifest["trace_hash"], "/trace_hash")
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "topology_plan_hash",
            "physical_equation_scaling_binding_hash",
            "engine_equation_scaling_hash",
            "engine_source_commitment_hash",
            "problem_contract_hash",
            "equation_order_hash",
            "solver_physical_equation_order_hash",
        },
        "/bindings",
    )
    for key, value in bindings.items():
        _require_hash(value, f"/bindings/{key}")
    entity_order = _manifest_object(manifest["entity_order"], "/entity_order")
    _exact_keys(entity_order, {"node_ids"}, "/entity_order")
    if type(entity_order["node_ids"]) is not list:
        _fail(
            "fiber_frame_physical_trace_node_order_invalid",
            "/entity_order/node_ids",
            "Manifest node IDs must be an array.",
        )
    nodes = _stable_id_tuple(entity_order["node_ids"], "/entity_order/node_ids")
    if not nodes or len(set(nodes)) != len(nodes):
        _fail(
            "fiber_frame_physical_trace_node_order_invalid",
            "/entity_order/node_ids",
            "Node IDs must be nonempty and unique.",
        )
    _validate_source_units_manifest(manifest["source_units"])
    observation = _manifest_object(manifest["observation"], "/observation")
    _exact_keys(
        observation,
        {"residual_sign", "equation_scope", "active_equations"},
        "/observation",
    )
    if observation["residual_sign"] != "internal_minus_external":
        _fail(
            "fiber_frame_physical_trace_sign_invalid",
            "/observation/residual_sign",
            "Unsupported residual sign.",
        )
    if observation["equation_scope"] != REFERENCE_EQUATION_SCOPE:
        _fail(
            "fiber_frame_physical_trace_scope_invalid",
            "/observation/equation_scope",
            "Only free-equation observation is supported.",
        )
    physical_count = 6 * len(nodes)
    solver_count = 3 * len(nodes)
    if type(observation["active_equations"]) is not list:
        _fail(
            "fiber_frame_physical_trace_active_equations_invalid",
            "/observation/active_equations",
            "Manifest active equations must be an array.",
        )
    active = _active_equations(observation["active_equations"], physical_count)
    if any(index % 6 not in (0, 1, 5) for index in active):
        _fail(
            "fiber_frame_physical_trace_active_equations_invalid",
            "/observation/active_equations",
            "Only mapped UX, UY, and RZ equations may be active.",
        )
    expected_solver_order_hash = canonical_hash(
        {
            "node_ids": list(nodes),
            "dof_components": list(FIBER_FRAME_SOLVER_DOF_COMPONENTS),
            "dof_count": solver_count,
        }
    )
    if bindings["solver_physical_equation_order_hash"] != expected_solver_order_hash:
        _fail(
            "fiber_frame_physical_trace_solver_order_mismatch",
            "/bindings/solver_physical_equation_order_hash",
            "Source residual order is stale.",
        )
    descriptors = _manifest_object(manifest["array_descriptors"], "/array_descriptors")
    vectors = _manifest_object(manifest["vectors"], "/vectors")
    _exact_keys(descriptors, set(_TRACE_ARRAY_NAMES), "/array_descriptors")
    _exact_keys(vectors, set(_TRACE_ARRAY_NAMES), "/vectors")
    arrays: dict[str, np.ndarray] = {}
    for name, shape, order_hash in (
        (
            "raw_residual_source_3dof",
            (solver_count,),
            bindings["solver_physical_equation_order_hash"],
        ),
        ("raw_residual_si_6dof", (physical_count,), bindings["equation_order_hash"]),
        ("scaled_residual_6dof", (physical_count,), bindings["equation_order_hash"]),
    ):
        array = _float_array(vectors[name], shape=shape, path=f"/vectors/{name}")
        arrays[name] = array
        _validate_descriptor_manifest(descriptors[name], name=name)
        if descriptors[name] != _array_descriptor(name, array, order_hash).to_dict():
            _fail(
                "fiber_frame_physical_trace_descriptor_mismatch",
                f"/array_descriptors/{name}",
                "Trace descriptor does not match embedded vector bytes.",
            )
    source = arrays["raw_residual_source_3dof"].reshape((-1, 3))
    expected_si = np.zeros((len(nodes), 6), dtype="<f8")
    expected_si[:, 0] = source[:, 0] * FIBER_FRAME_FORCE_TO_SI
    expected_si[:, 1] = source[:, 1] * FIBER_FRAME_FORCE_TO_SI
    expected_si[:, 5] = source[:, 2] * FIBER_FRAME_MOMENT_TO_SI
    raw_si = arrays["raw_residual_si_6dof"]
    if not np.array_equal(raw_si, expected_si.reshape(-1)):
        _fail(
            "fiber_frame_physical_trace_si_conversion_mismatch",
            "/vectors/raw_residual_si_6dof",
            "Canonical SI residual does not replay from source values.",
        )
    scales = _manifest_object(manifest["scales"], "/scales")
    _exact_keys(scales, {"characteristic_length_m", "reference_force_n"}, "/scales")
    _positive_float(
        scales["characteristic_length_m"], "/scales/characteristic_length_m"
    )
    _positive_float(scales["reference_force_n"], "/scales/reference_force_n")
    translation = tuple(index for index in active if index % 6 < 3)
    rotation = tuple(index for index in active if index % 6 >= 3)
    scaled = arrays["scaled_residual_6dof"]
    expected_norms = {
        "raw_translation_l2_n": _stable_l2(raw_si[list(translation)]),
        "raw_translation_linf_n": _linf(raw_si[list(translation)]),
        "raw_rotation_l2_nm": _stable_l2(raw_si[list(rotation)]),
        "raw_rotation_linf_nm": _linf(raw_si[list(rotation)]),
        "scaled_l2": _stable_l2(scaled[list(active)]),
        "scaled_linf": _linf(scaled[list(active)]),
    }
    norms = _manifest_object(manifest["norms"], "/norms")
    _exact_keys(norms, set(expected_norms), "/norms")
    for key, value in norms.items():
        _nonnegative_float(value, f"/norms/{key}")
    if norms != expected_norms:
        _fail(
            "fiber_frame_physical_trace_norm_mismatch",
            "/norms",
            "Dimensional or scaled residual norms are stale.",
        )
    governing_equation = active[int(np.argmax(np.abs(scaled[list(active)])))]
    governing = _manifest_object(manifest["governing"], "/governing")
    _exact_keys(governing, {"equation", "node_id", "dof"}, "/governing")
    _index(governing["equation"], "/governing/equation")
    _stable_id(governing["node_id"], "/governing/node_id")
    _stable_id(governing["dof"], "/governing/dof")
    if governing != {
        "equation": governing_equation,
        "node_id": nodes[governing_equation // 6],
        "dof": FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[governing_equation % 6],
    }:
        _fail(
            "fiber_frame_physical_trace_governing_mismatch",
            "/governing",
            "Governing scaled equation is stale.",
        )
    _validate_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    extensions = _manifest_object(manifest["extensions"], "/extensions")
    if extensions:
        _fail(
            "fiber_frame_physical_trace_extensions_invalid",
            "/extensions",
            "Residual-trace v1 requires empty extensions.",
        )
    without_hash = dict(manifest)
    claimed_hash = without_hash.pop("trace_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "fiber_frame_physical_trace_hash_mismatch",
            "/trace_hash",
            "Manifest trace hash is stale.",
        )
    return manifest


def validate_fiber_frame_physical_equation_scaling_array_bytes(
    binding: FiberFramePhysicalEquationScalingBinding,
    *,
    name: str,
    payload: bytes | bytearray | memoryview,
) -> np.ndarray:
    """Validate externally stored source/scale bytes against the binding."""

    validate_fiber_frame_physical_equation_scaling_binding(binding)
    return _validate_external_array_bytes(binding.descriptors, name, payload)


def validate_fiber_frame_physical_residual_trace_array_bytes(
    trace: FiberFramePhysicalResidualTrace,
    *,
    name: str,
    payload: bytes | bytearray | memoryview,
) -> np.ndarray:
    """Validate externally stored residual-vector bytes against the trace."""

    validate_fiber_frame_physical_residual_trace(trace)
    return _validate_external_array_bytes(trace.descriptors, name, payload)


def _derive_engine_scaling(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    *,
    minimum_characteristic_length_m: float,
    minimum_reference_force_n: float,
) -> tuple[
    EquationScaling,
    Mapping[str, np.ndarray],
    tuple[FiberFramePhysicalScalingArrayDescriptor, ...],
]:
    validate_fiber_frame_execution_topology_plan(plan)
    free = plan.array("free_physical_dofs")
    if free.size == 0:
        _fail(
            "fiber_frame_physical_scaling_free_equation_space_empty",
            "/topology_plan/arrays/free_physical_dofs",
            "Physical equation scaling requires at least one free equation.",
        )
    coordinates_xy = plan.array("node_coordinates_xy_m")
    coordinates = np.zeros((plan.node_count, 3), dtype="<f8")
    coordinates[:, :2] = coordinates_xy
    immutable_coordinates = _immutable_float_array(coordinates, "/node_coordinates_m")
    source_load = plan.array("reference_external_load_physical_6dof")
    load_si_values = np.asarray(source_load, dtype="<f8").reshape((-1, 6)).copy()
    load_si_values[:, :3] *= FIBER_FRAME_FORCE_TO_SI
    load_si_values[:, 3:] *= FIBER_FRAME_MOMENT_TO_SI
    load_si = _immutable_float_array(
        load_si_values.reshape(-1),
        "/reference_equation_load_si",
    )
    equation_order_hash = _physical_equation_order_hash(plan)
    characteristic_length = _characteristic_length(
        immutable_coordinates,
        minimum_characteristic_length_m,
    )
    reference_force = _reference_force(
        free_equations=free,
        reference_equation_load_si=load_si,
        characteristic_length_m=characteristic_length,
        minimum_reference_force_n=minimum_reference_force_n,
    )
    moment_scale = reference_force * characteristic_length
    if not math.isfinite(moment_scale):
        _fail(
            "fiber_frame_physical_scaling_nonfinite",
            "/scale_divisors_si",
            "Moment divisor overflowed fp64.",
        )
    divisors = np.empty(plan.physical_dof_count, dtype="<f8")
    divisors.reshape((-1, 6))[:, :3] = reference_force
    divisors.reshape((-1, 6))[:, 3:] = moment_scale
    immutable_divisors = _immutable_float_array(divisors, "/scale_divisors_si")
    descriptors = tuple(
        _array_descriptor(name, array, equation_order_hash)
        for name, array in (
            ("node_coordinates_m", immutable_coordinates),
            ("reference_equation_load_si", load_si),
            ("scale_divisors_si", immutable_divisors),
        )
    )
    descriptor_map = {descriptor.name: descriptor for descriptor in descriptors}
    provisional = EquationScaling(
        schema_version=EQUATION_SCALING_SCHEMA_VERSION,
        scaling_hash=_HASH_ZERO,
        base_plan_hash=plan.plan_hash,
        equation_order_hash=equation_order_hash,
        source_model_ir_content_hash=plan.model_ir_content_hash,
        source_load_pattern_id=plan.case_id,
        reference_equation_scope=REFERENCE_EQUATION_SCOPE,
        source_free_dofs_content_hash=_engine_free_dofs_content_hash(free),
        source_node_coordinates_data_hash=descriptor_map[
            "node_coordinates_m"
        ].data_hash,
        source_node_coordinates_content_hash=descriptor_map[
            "node_coordinates_m"
        ].content_hash,
        source_reference_load_data_hash=descriptor_map[
            "reference_equation_load_si"
        ].data_hash,
        source_reference_load_content_hash=descriptor_map[
            "reference_equation_load_si"
        ].content_hash,
        source_commitment_hash=_HASH_ZERO,
        characteristic_length_policy=CHARACTERISTIC_LENGTH_POLICY,
        reference_force_policy=REFERENCE_FORCE_POLICY,
        characteristic_length_m=characteristic_length,
        minimum_characteristic_length_m=minimum_characteristic_length_m,
        reference_force_n=reference_force,
        minimum_reference_force_n=minimum_reference_force_n,
        dof_count=plan.physical_dof_count,
        scale_vector_data_hash=descriptor_map["scale_divisors_si"].data_hash,
        scale_vector_content_hash=descriptor_map["scale_divisors_si"].content_hash,
        _scale_divisors_si=immutable_divisors,
    )
    with_source = replace(
        provisional,
        source_commitment_hash=canonical_hash(
            _engine_source_commitment_payload(
                provisional,
                include_commitment_hash=False,
            )
        ),
    )
    scaling = replace(
        with_source,
        scaling_hash=canonical_hash(
            _engine_scaling_payload(with_source, include_scaling_hash=False)
        ),
    )
    validate_equation_scaling(scaling)
    arrays = _freeze_array_map(
        {
            "node_coordinates_m": immutable_coordinates,
            "reference_equation_load_si": load_si,
            "scale_divisors_si": immutable_divisors,
        }
    )
    return scaling, arrays, descriptors


def _binding_payload(
    binding: FiberFramePhysicalEquationScalingBinding,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": binding.schema_version,
        "authority_profile": binding.authority_profile,
        "bindings": {
            "topology_schema_version": FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
            "topology_plan_hash": binding.topology_plan_hash,
            "problem_contract_hash": binding.problem_contract_hash,
            "topology_free_physical_dofs_content_hash": (
                binding.topology_free_physical_dofs_content_hash
            ),
            "engine_equation_scaling_schema_version": (
                binding.engine_scaling.schema_version
            ),
            "engine_equation_scaling_hash": binding.engine_equation_scaling_hash,
            "engine_source_commitment_profile": (
                FIBER_FRAME_EQUATION_SCALING_SOURCE_PROFILE
            ),
            "engine_source_commitment_hash": binding.engine_source_commitment_hash,
        },
        "source_units": _source_units_payload(),
        "engine_v2_equation_scaling": binding.engine_scaling.to_manifest(),
        "array_descriptors": {
            descriptor.name: descriptor.to_dict() for descriptor in binding.descriptors
        },
        "claim_boundary": dict(FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY),
        "extensions": dict(binding.extensions),
    }
    if include_binding_hash:
        payload["binding_hash"] = binding.binding_hash
    return payload


def _trace_payload(
    trace: FiberFramePhysicalResidualTrace,
    *,
    include_trace_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": trace.schema_version,
        "authority_profile": trace.authority_profile,
        "bindings": {
            "topology_plan_hash": trace.topology_plan_hash,
            "physical_equation_scaling_binding_hash": (
                trace.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": trace.engine_equation_scaling_hash,
            "engine_source_commitment_hash": trace.engine_source_commitment_hash,
            "problem_contract_hash": trace.problem_contract_hash,
            "equation_order_hash": trace.equation_order_hash,
            "solver_physical_equation_order_hash": (
                trace.solver_physical_equation_order_hash
            ),
        },
        "entity_order": {"node_ids": list(trace.node_ids)},
        "source_units": _source_units_payload(),
        "observation": {
            "residual_sign": trace.residual_sign,
            "equation_scope": trace.equation_scope,
            "active_equations": list(trace.active_equations),
        },
        "scales": {
            "characteristic_length_m": trace.characteristic_length_m,
            "reference_force_n": trace.reference_force_n,
        },
        "norms": {
            "raw_translation_l2_n": trace.raw_translation_l2_n,
            "raw_translation_linf_n": trace.raw_translation_linf_n,
            "raw_rotation_l2_nm": trace.raw_rotation_l2_nm,
            "raw_rotation_linf_nm": trace.raw_rotation_linf_nm,
            "scaled_l2": trace.scaled_l2,
            "scaled_linf": trace.scaled_linf,
        },
        "governing": {
            "equation": trace.governing_equation,
            "node_id": trace.governing_node_id,
            "dof": trace.governing_dof,
        },
        "array_descriptors": {
            descriptor.name: descriptor.to_dict() for descriptor in trace.descriptors
        },
        "vectors": {name: trace.array(name).tolist() for name in _TRACE_ARRAY_NAMES},
        "claim_boundary": dict(FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY),
        "extensions": dict(trace.extensions),
    }
    if include_trace_hash:
        payload["trace_hash"] = trace.trace_hash
    return payload


def _source_units_payload() -> dict[str, Any]:
    return {
        "profile": FIBER_FRAME_SOURCE_UNIT_PROFILE,
        "source_translation_force": FIBER_FRAME_SOURCE_FORCE_UNIT,
        "source_rotation_moment": FIBER_FRAME_SOURCE_MOMENT_UNIT,
        "target_translation_force": FIBER_FRAME_TARGET_FORCE_UNIT,
        "target_rotation_moment": FIBER_FRAME_TARGET_MOMENT_UNIT,
        "force_multiplier_to_si": FIBER_FRAME_FORCE_TO_SI,
        "moment_multiplier_to_si": FIBER_FRAME_MOMENT_TO_SI,
    }


def _validate_source_units_manifest(payload: Any) -> None:
    units = _manifest_object(payload, "/source_units")
    expected = _source_units_payload()
    _exact_keys(units, set(expected), "/source_units")
    for key in ("force_multiplier_to_si", "moment_multiplier_to_si"):
        _positive_float(units[key], f"/source_units/{key}")
    if units != expected:
        _fail(
            "fiber_frame_physical_scaling_source_units_invalid",
            "/source_units",
            "Source-to-SI unit profile changed.",
        )


def _physical_equation_order_hash(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> str:
    return canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "dof_components": list(FIBER_FRAME_PHYSICAL_DOF_COMPONENTS),
            "node_dof_indices_data_hash": array_data_hash(
                plan.array("node_dof_indices")
            ),
            "dof_count": plan.physical_dof_count,
        }
    )


def _solver_physical_equation_order_hash(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> str:
    return canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "dof_components": list(FIBER_FRAME_SOLVER_DOF_COMPONENTS),
            "dof_count": plan.solver_dof_count,
        }
    )


def _engine_free_dofs_content_hash(free_equations: np.ndarray) -> str:
    metadata = {
        "name": "free_dofs",
        "dtype": free_equations.dtype.str,
        "shape": list(free_equations.shape),
        "layout": "C",
        "byte_length": int(free_equations.nbytes),
    }
    return array_content_hash(metadata, free_equations)


def _characteristic_length(
    coordinates: np.ndarray,
    minimum_characteristic_length_m: float,
) -> float:
    node_count = coordinates.shape[0]
    try:
        centroid = np.asarray(
            [
                math.fsum(float(coordinates[row, column]) for row in range(node_count))
                / node_count
                for column in range(3)
            ],
            dtype="<f8",
        )
    except OverflowError:
        _fail(
            "fiber_frame_physical_scaling_characteristic_length_invalid",
            "/characteristic_length_m",
            "Coordinate accumulation overflowed fp64.",
        )
    max_radius = 0.0
    for row in range(node_count):
        delta = coordinates[row] - centroid
        max_radius = max(
            max_radius,
            math.hypot(float(delta[0]), float(delta[1]), float(delta[2])),
        )
    result = 2.0 * max_radius
    if not math.isfinite(result) or result < minimum_characteristic_length_m:
        _fail(
            "fiber_frame_physical_scaling_characteristic_length_invalid",
            "/characteristic_length_m",
            "Model extent is below the explicit characteristic-length minimum.",
        )
    return result


def _reference_force(
    *,
    free_equations: np.ndarray,
    reference_equation_load_si: np.ndarray,
    characteristic_length_m: float,
    minimum_reference_force_n: float,
) -> float:
    translation = free_equations[free_equations % 6 < 3]
    rotation = free_equations[free_equations % 6 >= 3]
    result = max(
        minimum_reference_force_n,
        _max_abs(reference_equation_load_si[translation]),
        _max_abs(reference_equation_load_si[rotation]) / characteristic_length_m,
    )
    if not math.isfinite(result):
        _fail(
            "fiber_frame_physical_scaling_reference_force_invalid",
            "/reference_force_n",
            "Reference-force scale overflowed fp64.",
        )
    return result


def _array_descriptor(
    name: str,
    array: np.ndarray,
    equation_order_hash: str,
) -> FiberFramePhysicalScalingArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
        "equation_order_hash": equation_order_hash,
    }
    return FiberFramePhysicalScalingArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        equation_order_hash=equation_order_hash,
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _engine_scale_descriptor(engine_manifest: Mapping[str, Any]) -> dict[str, Any]:
    vector = dict(engine_manifest["scale_vector"])
    vector.pop("values")
    return vector


def _validate_descriptor_manifest(payload: Any, *, name: str) -> None:
    descriptor = _manifest_object(payload, f"/array_descriptors/{name}")
    _exact_keys(
        descriptor,
        {
            "name",
            "dtype",
            "shape",
            "layout",
            "byte_length",
            "equation_order_hash",
            "data_hash",
            "content_hash",
        },
        f"/array_descriptors/{name}",
    )
    if descriptor["name"] != name or descriptor["dtype"] != "<f8":
        _fail(
            "fiber_frame_physical_scaling_descriptor_invalid",
            f"/array_descriptors/{name}",
            "Descriptor name or dtype is invalid.",
        )
    if descriptor["layout"] != "C":
        _fail(
            "fiber_frame_physical_scaling_descriptor_invalid",
            f"/array_descriptors/{name}/layout",
            "Only C-order arrays are supported.",
        )
    shape = descriptor["shape"]
    if (
        not isinstance(shape, list)
        or not shape
        or any(type(value) is not int or value < 1 for value in shape)
    ):
        _fail(
            "fiber_frame_physical_scaling_descriptor_invalid",
            f"/array_descriptors/{name}/shape",
            "Descriptor shape requires positive integer dimensions.",
        )
    byte_length = descriptor["byte_length"]
    if type(byte_length) is not int or byte_length != math.prod(shape) * 8:
        _fail(
            "fiber_frame_physical_scaling_descriptor_invalid",
            f"/array_descriptors/{name}/byte_length",
            "Descriptor byte length is inconsistent with shape and dtype.",
        )
    for key in ("equation_order_hash", "data_hash", "content_hash"):
        _require_hash(descriptor[key], f"/array_descriptors/{name}/{key}")


def _validate_array_map(
    arrays: Mapping[str, np.ndarray],
    descriptors: tuple[FiberFramePhysicalScalingArrayDescriptor, ...],
    expected_names: Sequence[str],
) -> None:
    if not isinstance(arrays, MappingProxyType):
        _fail(
            "fiber_frame_physical_scaling_array_map_invalid",
            "/arrays",
            "Array map must be immutable.",
        )
    if type(descriptors) is not tuple or any(
        type(row) is not FiberFramePhysicalScalingArrayDescriptor for row in descriptors
    ):
        _fail(
            "fiber_frame_physical_scaling_descriptor_type_invalid",
            "/array_descriptors",
            "Unexpected descriptor type.",
        )
    names = tuple(descriptor.name for descriptor in descriptors)
    if names != tuple(expected_names) or tuple(arrays) != tuple(expected_names):
        _fail(
            "fiber_frame_physical_scaling_array_order_invalid",
            "/arrays",
            "Array and descriptor names/order are invalid.",
        )
    for descriptor in descriptors:
        array = arrays[descriptor.name]
        _validate_contract_array(array, descriptor.shape, f"/arrays/{descriptor.name}")
        if descriptor != _array_descriptor(
            descriptor.name,
            array,
            descriptor.equation_order_hash,
        ):
            _fail(
                "fiber_frame_physical_scaling_descriptor_mismatch",
                f"/array_descriptors/{descriptor.name}",
                "Descriptor does not match retained array bytes.",
            )


def _validate_external_array_bytes(
    descriptors: tuple[FiberFramePhysicalScalingArrayDescriptor, ...],
    name: str,
    payload: bytes | bytearray | memoryview,
) -> np.ndarray:
    if type(name) is not str:
        _fail(
            "fiber_frame_physical_scaling_array_name_invalid",
            "/name",
            "Array name must be a string.",
        )
    try:
        descriptor = _descriptor_by_name(descriptors, name)
    except KeyError:
        _fail(
            "fiber_frame_physical_scaling_array_name_invalid",
            "/name",
            "Unknown external array name.",
        )
    if not isinstance(payload, bytes):
        _fail(
            "fiber_frame_physical_scaling_array_bytes_invalid",
            f"/arrays/{name}",
            "External array payload must be immutable bytes.",
        )
    if len(payload) != descriptor.byte_length:
        _fail(
            "fiber_frame_physical_scaling_array_bytes_invalid",
            f"/arrays/{name}",
            "External array byte length differs from its descriptor.",
        )
    try:
        array = np.frombuffer(payload, dtype=descriptor.dtype).reshape(descriptor.shape)
    except (TypeError, ValueError) as exc:
        _fail(
            "fiber_frame_physical_scaling_array_bytes_invalid",
            f"/arrays/{name}",
            f"External array bytes cannot be reshaped: {exc}",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "fiber_frame_physical_scaling_array_nonfinite",
            f"/arrays/{name}",
            "External array contains non-finite values.",
        )
    if array_data_hash(array) != descriptor.data_hash:
        _fail(
            "fiber_frame_physical_scaling_array_hash_mismatch",
            f"/arrays/{name}",
            "External array bytes do not match the descriptor hash.",
        )
    if _array_descriptor(name, array, descriptor.equation_order_hash) != descriptor:
        _fail(
            "fiber_frame_physical_scaling_array_hash_mismatch",
            f"/arrays/{name}",
            "External array content hash does not match the descriptor.",
        )
    return array


def _freeze_array_map(values: Mapping[str, np.ndarray]) -> Mapping[str, np.ndarray]:
    return MappingProxyType(dict(values))


def _immutable_float_array(value: Any, path: str) -> np.ndarray:
    try:
        object_view = np.asarray(value, dtype=object)
    except (TypeError, ValueError, OverflowError) as exc:
        _fail(
            "fiber_frame_physical_scaling_array_invalid",
            path,
            f"Value cannot be inspected: {exc}",
        )
    if any(isinstance(item, (bool, np.bool_)) for item in object_view.reshape(-1)):
        _fail(
            "fiber_frame_physical_scaling_array_invalid",
            path,
            "Boolean values are not physical numeric inputs.",
        )
    try:
        return immutable_array(value, dtype="<f8")
    except CanonicalContractError as exc:
        _fail("fiber_frame_physical_scaling_array_invalid", path, str(exc))


def _float_array(value: Any, *, shape: tuple[int, ...], path: str) -> np.ndarray:
    result = _immutable_float_array(value, path)
    if result.shape != shape:
        _fail(
            "fiber_frame_physical_scaling_array_shape_invalid",
            path,
            f"Expected shape {shape}.",
        )
    return result


def _validate_contract_array(
    value: Any,
    shape: tuple[int, ...],
    path: str,
) -> None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype.str != "<f8"
        or value.shape != shape
        or not value.flags.c_contiguous
        or not has_immutable_bytes_backing(value)
    ):
        _fail(
            "fiber_frame_physical_scaling_array_contract_invalid",
            path,
            "Expected immutable C-order canonical <f8 array and exact shape.",
        )
    if not np.all(np.isfinite(value)):
        _fail(
            "fiber_frame_physical_scaling_array_nonfinite",
            path,
            "Array values must be finite.",
        )


def _topology_descriptor(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    name: str,
) -> Any:
    for descriptor in plan.descriptors:
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)  # pragma: no cover - protected by topology validation


def _descriptor_by_name(
    descriptors: Sequence[FiberFramePhysicalScalingArrayDescriptor],
    name: str,
) -> FiberFramePhysicalScalingArrayDescriptor:
    for descriptor in descriptors:
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)


def _manifest_object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "fiber_frame_physical_scaling_manifest_object_invalid",
            path,
            "Expected an object.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        _fail(
            "fiber_frame_physical_scaling_manifest_keys_invalid",
            path,
            "Manifest object keys differ from the v1 contract.",
        )


def _validate_claim_boundary(
    payload: Any,
    expected: Mapping[str, bool],
    path: str,
) -> None:
    claims = _manifest_object(payload, path)
    _exact_keys(claims, set(expected), path)
    if any(type(value) is not bool for value in claims.values()) or dict(
        claims
    ) != dict(expected):
        _fail(
            "fiber_frame_physical_scaling_claim_boundary_invalid",
            path,
            "Claim boundary changed or contains non-boolean values.",
        )


def _active_equations(value: Any, dof_count: int) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(
            "fiber_frame_physical_trace_active_equations_invalid",
            "/observation/active_equations",
            "Expected an integer sequence.",
        )
    result = tuple(value)
    _require_nonempty_active_equations(result, dof_count)
    return result


def _require_nonempty_active_equations(
    value: tuple[Any, ...],
    dof_count: int,
) -> None:
    if (
        not value
        or any(type(item) is not int for item in value)
        or value != tuple(sorted(set(value)))
        or value[0] < 0
        or value[-1] >= dof_count
    ):
        _fail(
            "fiber_frame_physical_trace_active_equations_invalid",
            "/observation/active_equations",
            "Equations must be nonempty, sorted, unique integers in range.",
        )


def _stable_id_tuple(value: Any, path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(
            "fiber_frame_physical_scaling_id_invalid",
            path,
            "Expected an ID sequence.",
        )
    return tuple(
        _stable_id(item, f"{path}/{index}") for index, item in enumerate(value)
    )


def _stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_physical_scaling_id_invalid",
            path,
            "Expected a stable nonempty identifier.",
        )
    return value


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_physical_scaling_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_physical_scaling_hash_invalid",
            path,
            "Expected a canonical sha256 hash.",
        )
    return value


def _positive_float(value: Any, path: str) -> float:
    if type(value) not in (int, float):
        _fail(
            "fiber_frame_physical_scaling_number_invalid",
            path,
            "Expected a finite positive number.",
        )
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        _fail(
            "fiber_frame_physical_scaling_number_invalid",
            path,
            "Expected a finite positive number.",
        )
    return result


def _nonnegative_float(value: Any, path: str) -> float:
    if type(value) not in (int, float):
        _fail(
            "fiber_frame_physical_scaling_number_invalid",
            path,
            "Expected a finite nonnegative number.",
        )
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        _fail(
            "fiber_frame_physical_scaling_number_invalid",
            path,
            "Expected a finite nonnegative number.",
        )
    return result


def _max_abs(values: np.ndarray) -> float:
    return 0.0 if values.size == 0 else float(np.max(np.abs(values)))


def _linf(values: np.ndarray) -> float:
    return _max_abs(values)


def _stable_l2(values: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for item in values:
        absolute = abs(float(item))
        if absolute == 0.0:
            continue
        if scale < absolute:
            sumsq = 1.0 + sumsq * (scale / absolute) ** 2
            scale = absolute
        else:
            sumsq += (absolute / scale) ** 2
    result = 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)
    if not math.isfinite(result):
        _fail(
            "fiber_frame_physical_scaling_norm_nonfinite",
            "/norms",
            "Norm is not representable in fp64.",
        )
    return result


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFramePhysicalEquationScalingError(code, path, message)


__all__ = [
    "FIBER_FRAME_EQUATION_SCALING_SOURCE_PROFILE",
    "FIBER_FRAME_FORCE_TO_SI",
    "FIBER_FRAME_MOMENT_TO_SI",
    "FIBER_FRAME_PHYSICAL_EQUATION_SCALING_AUTHORITY_PROFILE",
    "FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY",
    "FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION",
    "FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_AUTHORITY_PROFILE",
    "FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY",
    "FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION",
    "FIBER_FRAME_SOURCE_UNIT_PROFILE",
    "FiberFramePhysicalEquationScalingBinding",
    "FiberFramePhysicalEquationScalingError",
    "FiberFramePhysicalResidualTrace",
    "FiberFramePhysicalScalingArrayDescriptor",
    "create_stateful_fiber_frame2d_physical_equation_scaling",
    "trace_stateful_fiber_frame2d_free_physical_residual",
    "trace_stateful_fiber_frame2d_physical_residual",
    "validate_fiber_frame_physical_equation_scaling_against_problem",
    "validate_fiber_frame_physical_equation_scaling_array_bytes",
    "validate_fiber_frame_physical_equation_scaling_binding",
    "validate_fiber_frame_physical_equation_scaling_manifest",
    "validate_fiber_frame_physical_residual_trace",
    "validate_fiber_frame_physical_residual_trace_array_bytes",
    "validate_fiber_frame_physical_residual_trace_manifest",
]
