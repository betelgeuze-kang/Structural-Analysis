"""J5-backed nonlinear numerical-result adapter for the bounded fiber frame.

The adapter replays the exact J1--J5 source chain, binds the terminal canonical
six-DOF displacement bytes, and supplies the remaining reduced-system,
full-residual, boundary-condition, and backend receipts required by
``NonlinearNumericalResultIR``.  It does not emit ``StateIR v1`` and grants no
reaction, member-force, integration-point engineering, design, release, or
commercial authority.
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
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
    StatefulFiberFrame2DCheckpointChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionTopologyPlan,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION,
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
    FiberFrameNonlinearKinematicStateChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION,
    FiberFrameMaterialStateProjectionChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionStateBinding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M,
    FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE,
    FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION,
    FiberFrameNonlinearTerminalReceipt,
    validate_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION,
    FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
    FiberFramePhysicalEquationScalingBinding,
    FiberFramePhysicalResidualTrace,
    trace_stateful_fiber_frame2d_physical_residual,
    validate_fiber_frame_physical_residual_trace,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateBundle,
    validate_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE,
    NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY,
    NonlinearNumericalResultIR,
    NonlinearNumericalResultSourceSnapshot,
    create_adapter_bound_nonlinear_numerical_result_ir,
    validate_nonlinear_numerical_result_ir,
    validate_nonlinear_result_manifest,
)
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)


FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-result-reduced-system-receipt.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_RESIDUAL_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-result-full-residual-receipt.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_BOUNDARY_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-result-boundary-condition-receipt.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_BACKEND_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-result-backend-receipt.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_SOURCE_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-result-source-binding.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_ADAPTER_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-numerical-result-adapter.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE = (
    "authoritative_bounded_converged_fiber_frame_numerical_state.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_TIME_PROFILE = "static_no_physical_time_zero.v1"
FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_PROFILE = (
    "canonical_free_physical_csr_with_terminal_dense_solver_jacobian.v1"
)
FIBER_FRAME_NONLINEAR_RESULT_STORAGE_PROFILE = (
    "canonical_little_endian_hash_bound_arrays.v1"
)

FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY = MappingProxyType(
    {
        "exact_j1_execution_topology_bound": True,
        "exact_j2_equation_scaling_bound": True,
        "exact_j3_kinematic_state_chain_bound": True,
        "exact_j4_execution_state_binding_bound": True,
        "exact_j5_terminal_receipt_bound": True,
        "load_path_and_checkpoint_chain_replayed": True,
        "reduced_system_identity_bound": True,
        "final_physical_and_scaled_residual_bound": True,
        "boundary_condition_receipt_bound": True,
        "backend_receipt_bound": True,
        "terminal_displacement_bytes_bound": True,
        "convergence_authority": True,
        "committed_displacement_authority": True,
        "committed_material_state_authority": True,
        "state_ir_v1_emitted": False,
        "constitutive_law_verified": False,
        "reaction_authority": False,
        "member_force_authority": False,
        "integration_point_engineering_output_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_REDUCED_SYSTEM_CLAIM_BOUNDARY = MappingProxyType(
    {
        "free_physical_equation_order_bound": True,
        "free_solver_equation_order_bound": True,
        "reduced_csr_topology_bound": True,
        "terminal_dense_solver_jacobian_bytes_bound": True,
        "numeric_csr_values_materialized": False,
        "solver_execution_authority": False,
        "result_authority": False,
    }
)
_RESIDUAL_CLAIM_BOUNDARY = MappingProxyType(
    {
        "full_source_residual_bytes_bound": True,
        "canonical_si_residual_bytes_bound": True,
        "dimensionless_scaled_residual_bytes_bound": True,
        "j5_terminal_step_bound": True,
        "residual_gate_passed": True,
        "independent_result_authority": False,
        "reaction_authority": False,
    }
)
_BOUNDARY_CLAIM_BOUNDARY = MappingProxyType(
    {
        "inactive_physical_constraints_bound": True,
        "authored_fixed_constraints_bound": True,
        "complete_free_constrained_partition_bound": True,
        "solver_to_physical_partition_bound": True,
        "arbitrary_boundary_entities_supported": False,
        "reaction_authority": False,
        "result_authority": False,
    }
)
_BACKEND_CLAIM_BOUNDARY = MappingProxyType(
    {
        "executed_cpu_backend_bound": True,
        "solver_config_bound": True,
        "terminal_linear_solve_count_bound": True,
        "fallback_or_regularization_used": False,
        "cpu_hip_parity_authority": False,
        "performance_authority": False,
        "result_authority": False,
    }
)

_SOURCE_SCHEMA_VERSIONS = MappingProxyType(
    {
        "execution_topology": FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
        "physical_equation_scaling": (
            FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION
        ),
        "checkpoint_chain": STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
        "kinematic_state_chain": (
            FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION
        ),
        "material_state_projection_chain": (
            FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION
        ),
        "execution_state_binding": (
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION
        ),
        "terminal_receipt": FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION,
        "physical_residual_trace": FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1
_REDUCED_ARRAY_NAMES = (
    "free_physical_dofs",
    "free_solver_dofs",
    "free_csr_row_ptr",
    "free_csr_column_indices",
)
_BACKEND_ROLE_BY_MATRIX_BACKEND: Mapping[
    str, Literal["cpu_reference", "cpu_optimized"]
] = MappingProxyType(
    {
        VECTOR_MATRIX_BACKEND: "cpu_reference",
        VECTOR_SPARSE_MATRIX_BACKEND: "cpu_optimized",
    }
)


class FiberFrameNonlinearResultAdapterError(ValueError):
    """Stable fail-closed error for the J5 result adapter."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameNonlinearResultArrayDescriptor:
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
class FiberFrameNonlinearReducedSystemReceipt:
    schema_version: str
    identity_hash: str
    authority_profile: str
    system_profile: str
    execution_topology_plan_hash: str
    execution_topology_hash: str
    execution_operator_hash: str
    solver_coordinate_scaling_hash: str
    terminal_step_receipt_hash: str
    final_analytic_jacobian_data_hash: str
    final_analytic_jacobian_content_hash: str
    physical_dof_count: int
    free_count: int
    reduced_nnz: int
    descriptors: tuple[FiberFrameNonlinearResultArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown reduced-system array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_reduced_system_receipt(self)
        return _reduced_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearFullResidualReceipt:
    schema_version: str
    receipt_hash: str
    authority_profile: str
    terminal_receipt_hash: str
    terminal_step_receipt_hash: str
    physical_residual_trace_hash: str
    source_residual_data_hash: str
    source_residual_content_hash: str
    canonical_si_residual_data_hash: str
    canonical_si_residual_content_hash: str
    scaled_residual_data_hash: str
    scaled_residual_content_hash: str
    raw_translation_linf_n: float
    raw_rotation_linf_nm: float
    scaled_residual_linf: float
    scaled_residual_tolerance: float
    residual_gate_passed: bool
    _trace: FiberFramePhysicalResidualTrace = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_full_residual_receipt(self)
        return _residual_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearBoundaryConditionReceipt:
    schema_version: str
    receipt_hash: str
    authority_profile: str
    problem_contract_hash: str
    execution_topology_plan_hash: str
    case_id: str
    node_order_hash: str
    physical_dof_count: int
    solver_dof_count: int
    inactive_physical_dofs_content_hash: str
    authored_fixed_physical_dofs_content_hash: str
    constrained_physical_dofs_content_hash: str
    free_physical_dofs_content_hash: str
    constrained_solver_dofs_content_hash: str
    free_solver_dofs_content_hash: str
    solver_to_physical_global_dofs_content_hash: str
    partition_hash: str
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_boundary_condition_receipt(self)
        return _boundary_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearBackendReceipt:
    schema_version: str
    receipt_hash: str
    authority_profile: str
    backend_role: Literal["cpu_reference", "cpu_optimized"]
    matrix_backend: str
    deterministic_execution: bool
    execution_topology_plan_hash: str
    execution_operator_hash: str
    execution_numeric_buffer_hash: str
    solver_config_hash: str
    terminal_receipt_hash: str
    terminal_step_receipt_hash: str
    final_analytic_jacobian_data_hash: str
    total_linear_solve_count: int
    fallback_count: int
    regularization_count: int
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_backend_receipt(self)
        return _backend_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearResultSourceBinding:
    schema_version: str
    binding_hash: str
    authority_profile: str
    state_ir_usage_profile: str
    time_profile: str
    problem_contract_hash: str
    model_ir_content_hash: str
    case_id: str
    execution_topology_plan_hash: str
    execution_topology_hash: str
    execution_operator_hash: str
    execution_numeric_buffer_hash: str
    solver_coordinate_scaling_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    execution_state_binding_hash: str
    checkpoint_chain_hash: str
    kinematic_state_chain_hash: str
    material_state_projection_chain_hash: str
    terminal_receipt_hash: str
    terminal_checkpoint_state_hash: str
    terminal_kinematic_state_hash: str
    terminal_material_state_bundle_hash: str
    path_history_hash: str
    terminal_displacement_data_hash: str
    terminal_displacement_content_hash: str
    terminal_displacement_coordinate_order_hash: str
    terminal_epoch: int
    terminal_load_factor: float
    accepted_step_count: int
    solver_residual_tolerance: float
    solver_increment_tolerance_m: float
    final_solver_coordinate_increment_linf_m: float
    residual_gate_passed: bool
    increment_gate_passed: bool
    convergence_gate_passed: bool
    physical_dof_count: int
    reduced_system_receipt: FiberFrameNonlinearReducedSystemReceipt
    full_residual_receipt: FiberFrameNonlinearFullResidualReceipt
    boundary_condition_receipt: FiberFrameNonlinearBoundaryConditionReceipt
    backend_receipt: FiberFrameNonlinearBackendReceipt
    extensions: Mapping[str, Any]
    _problem: StatefulFiberFrame2DProblem = field(repr=False, compare=False)
    _topology_plan: FiberFrameNonlinearExecutionTopologyPlan = field(
        repr=False,
        compare=False,
    )
    _physical_scaling: FiberFramePhysicalEquationScalingBinding = field(
        repr=False,
        compare=False,
    )
    _checkpoint_chain: StatefulFiberFrame2DCheckpointChain = field(
        repr=False,
        compare=False,
    )
    _kinematic_chain: FiberFrameNonlinearKinematicStateChain = field(
        repr=False,
        compare=False,
    )
    _material_chain: FiberFrameMaterialStateProjectionChain = field(
        repr=False,
        compare=False,
    )
    _execution_state_binding: FiberFrameNonlinearExecutionStateBinding = field(
        repr=False,
        compare=False,
    )
    _load_path: StatefulFiberFrame2DLoadPathResult = field(
        repr=False,
        compare=False,
    )
    _terminal_receipt: FiberFrameNonlinearTerminalReceipt = field(
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_result_source_binding_shape(self)
        return _source_binding_payload(self, include_hash=True)

    def validate_nonlinear_result_source(
        self,
    ) -> NonlinearNumericalResultSourceSnapshot:
        validate_fiber_frame_nonlinear_result_source_binding(self)
        return _source_snapshot(self)


@dataclass(frozen=True)
class FiberFrameNonlinearNumericalResultAdapter:
    schema_version: str
    adapter_hash: str
    authority_profile: str
    source_binding: FiberFrameNonlinearResultSourceBinding
    numerical_result: NonlinearNumericalResultIR
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_numerical_result_adapter(self)
        return _adapter_payload(self, include_hash=True)


def create_fiber_frame_nonlinear_numerical_result_adapter(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt,
    *,
    result_id: str = "result.fiber-frame.nonlinear.full-load",
) -> FiberFrameNonlinearNumericalResultAdapter:
    """Create one bounded authoritative numerical result from exact J1--J5."""

    source_binding = _build_source_binding(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
        terminal_receipt,
    )
    numerical_result = create_adapter_bound_nonlinear_numerical_result_ir(
        result_id=_stable_id(result_id, "/result_id"),
        source_adapter=source_binding,
    )
    provisional = FiberFrameNonlinearNumericalResultAdapter(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_ADAPTER_SCHEMA_VERSION,
        adapter_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        source_binding=source_binding,
        numerical_result=numerical_result,
        extensions=MappingProxyType({}),
    )
    adapter = replace(
        provisional,
        adapter_hash=canonical_hash(_adapter_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_numerical_result_adapter(adapter)


def _build_source_binding(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearResultSourceBinding:
    validate_fiber_frame_nonlinear_terminal_receipt(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
        terminal_receipt,
    )
    terminal_state = kinematic_chain.committed_states[-1]
    terminal_bundle = validate_material_state_bundle(
        material_chain.projections[-1].bundle
    )
    if terminal_bundle.solver_state_hash != terminal_state.state_hash:
        _fail(
            "fiber_frame_result_terminal_material_state_mismatch",
            "/bindings/terminal_material_state_bundle_hash",
            "Terminal material bundle does not bind the terminal kinematic state.",
        )
    displacement = terminal_state.array("canonical_displacement_si")
    displacement_descriptor = _descriptor_by_name(
        terminal_state.descriptors,
        "canonical_displacement_si",
    )
    final_step = terminal_receipt.step_receipts[-1]
    source_free_solution = immutable_array(
        terminal_state.array("solver_generalized_coordinates_m")[
            topology_plan.array("free_solver_dofs")
        ],
        dtype="<f8",
    )
    if (
        not np.array_equal(
            source_free_solution,
            load_path.steps[-1].trial_solution.free_displacements_m,
        )
        or array_data_hash(source_free_solution) != final_step.source_solution_data_hash
    ):
        _fail(
            "fiber_frame_result_terminal_solution_mismatch",
            "/terminal_displacement",
            "Terminal J3 displacement does not equal the J5 free solution bytes.",
        )

    reduced = _build_reduced_system_receipt(topology_plan, terminal_receipt)
    residual = _build_full_residual_receipt(
        topology_plan,
        physical_scaling,
        load_path,
        terminal_receipt,
    )
    boundary = _build_boundary_condition_receipt(problem, topology_plan)
    backend = _build_backend_receipt(topology_plan, terminal_receipt)
    path_history_hash = canonical_hash(
        {
            "checkpoint_chain_hash": checkpoint_chain.chain_hash,
            "source_load_path_replay_hash": terminal_receipt.source_load_path_replay_hash,
            "step_receipt_chain_hash": terminal_receipt.step_receipt_chain_hash,
        }
    )
    provisional = FiberFrameNonlinearResultSourceBinding(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_SOURCE_BINDING_SCHEMA_VERSION,
        binding_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        time_profile=FIBER_FRAME_NONLINEAR_RESULT_TIME_PROFILE,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=topology_plan.model_ir_content_hash,
        case_id=problem.case_id,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_topology_hash=topology_plan.topology_hash,
        execution_operator_hash=topology_plan.operator_hash,
        execution_numeric_buffer_hash=topology_plan.numeric_buffer_hash,
        solver_coordinate_scaling_hash=topology_plan.solver_coordinate_scaling_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=physical_scaling.engine_equation_scaling_hash,
        execution_state_binding_hash=execution_state_binding.binding_hash,
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        kinematic_state_chain_hash=kinematic_chain.chain_hash,
        material_state_projection_chain_hash=material_chain.chain_hash,
        terminal_receipt_hash=terminal_receipt.terminal_receipt_hash,
        terminal_checkpoint_state_hash=terminal_receipt.terminal_checkpoint_state_hash,
        terminal_kinematic_state_hash=terminal_state.state_hash,
        terminal_material_state_bundle_hash=terminal_bundle.bundle_hash,
        path_history_hash=path_history_hash,
        terminal_displacement_data_hash=array_data_hash(displacement),
        terminal_displacement_content_hash=displacement_descriptor.content_hash,
        terminal_displacement_coordinate_order_hash=(
            displacement_descriptor.coordinate_order_hash
        ),
        terminal_epoch=terminal_state.epoch,
        terminal_load_factor=terminal_state.load_factor,
        accepted_step_count=terminal_receipt.accepted_step_count,
        solver_residual_tolerance=terminal_receipt.solver_residual_tolerance,
        solver_increment_tolerance_m=terminal_receipt.solver_increment_tolerance_m,
        final_solver_coordinate_increment_linf_m=(
            terminal_receipt.final_solver_coordinate_increment_linf_m
        ),
        residual_gate_passed=final_step.residual_gate_passed,
        increment_gate_passed=final_step.increment_gate_passed,
        convergence_gate_passed=final_step.convergence_gate_passed,
        physical_dof_count=topology_plan.physical_dof_count,
        reduced_system_receipt=reduced,
        full_residual_receipt=residual,
        boundary_condition_receipt=boundary,
        backend_receipt=backend,
        extensions=MappingProxyType({}),
        _problem=problem,
        _topology_plan=topology_plan,
        _physical_scaling=physical_scaling,
        _checkpoint_chain=checkpoint_chain,
        _kinematic_chain=kinematic_chain,
        _material_chain=material_chain,
        _execution_state_binding=execution_state_binding,
        _load_path=load_path,
        _terminal_receipt=terminal_receipt,
    )
    binding = replace(
        provisional,
        binding_hash=canonical_hash(
            _source_binding_payload(provisional, include_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_result_source_binding_shape(binding)


def _build_reduced_system_receipt(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearReducedSystemReceipt:
    arrays = _reduced_system_arrays(topology_plan)
    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _REDUCED_ARRAY_NAMES
    )
    final_step = terminal_receipt.step_receipts[-1]
    audit = final_step.jacobian_audit
    provisional = FiberFrameNonlinearReducedSystemReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_SCHEMA_VERSION,
        identity_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        system_profile=FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_PROFILE,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_topology_hash=topology_plan.topology_hash,
        execution_operator_hash=topology_plan.operator_hash,
        solver_coordinate_scaling_hash=topology_plan.solver_coordinate_scaling_hash,
        terminal_step_receipt_hash=final_step.step_receipt_hash,
        final_analytic_jacobian_data_hash=audit.analytic_jacobian_data_hash,
        final_analytic_jacobian_content_hash=audit.analytic_jacobian_content_hash,
        physical_dof_count=topology_plan.physical_dof_count,
        free_count=len(arrays["free_physical_dofs"]),
        reduced_nnz=len(arrays["free_csr_column_indices"]),
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        identity_hash=canonical_hash(_reduced_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_reduced_system_receipt(receipt)


def _build_full_residual_receipt(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearFullResidualReceipt:
    source_residual = immutable_array(
        load_path.steps[-1].trial_assembly.internal_loads_global
        - load_path.steps[-1].trial_assembly.external_loads_global,
        dtype="<f8",
    )
    trace = trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=topology_plan,
        scaling_binding=physical_scaling,
        raw_residual_source_3dof=source_residual,
    )
    final_step = terminal_receipt.step_receipts[-1]
    if trace.trace_hash != final_step.physical_residual_trace_hash:
        _fail(
            "fiber_frame_result_residual_trace_mismatch",
            "/full_residual_receipt",
            "Replayed terminal residual trace does not equal J5.",
        )
    source_descriptor = _descriptor_by_name(
        trace.descriptors,
        "raw_residual_source_3dof",
    )
    si_descriptor = _descriptor_by_name(trace.descriptors, "raw_residual_si_6dof")
    scaled_descriptor = _descriptor_by_name(
        trace.descriptors,
        "scaled_residual_6dof",
    )
    provisional = FiberFrameNonlinearFullResidualReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_RESIDUAL_SCHEMA_VERSION,
        receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        terminal_receipt_hash=terminal_receipt.terminal_receipt_hash,
        terminal_step_receipt_hash=final_step.step_receipt_hash,
        physical_residual_trace_hash=trace.trace_hash,
        source_residual_data_hash=source_descriptor.data_hash,
        source_residual_content_hash=source_descriptor.content_hash,
        canonical_si_residual_data_hash=si_descriptor.data_hash,
        canonical_si_residual_content_hash=si_descriptor.content_hash,
        scaled_residual_data_hash=scaled_descriptor.data_hash,
        scaled_residual_content_hash=scaled_descriptor.content_hash,
        raw_translation_linf_n=trace.raw_translation_linf_n,
        raw_rotation_linf_nm=trace.raw_rotation_linf_nm,
        scaled_residual_linf=trace.scaled_linf,
        scaled_residual_tolerance=final_step.scaled_residual_tolerance,
        residual_gate_passed=bool(
            trace.scaled_linf <= final_step.scaled_residual_tolerance
            and final_step.residual_gate_passed
        ),
        _trace=trace,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        receipt_hash=canonical_hash(_residual_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_full_residual_receipt(receipt)


def _build_boundary_condition_receipt(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> FiberFrameNonlinearBoundaryConditionReceipt:
    content_hashes = {
        name: _descriptor_by_name(topology_plan.descriptors, name).content_hash
        for name in (
            "inactive_physical_dofs",
            "authored_fixed_physical_dofs",
            "constrained_physical_dofs",
            "free_physical_dofs",
            "constrained_solver_dofs",
            "free_solver_dofs",
            "solver_to_physical_global_dofs",
        )
    }
    partition_hash = canonical_hash(content_hashes)
    provisional = FiberFrameNonlinearBoundaryConditionReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_BOUNDARY_SCHEMA_VERSION,
        receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        problem_contract_hash=problem.contract_hash,
        execution_topology_plan_hash=topology_plan.plan_hash,
        case_id=problem.case_id,
        node_order_hash=canonical_hash({"node_ids": list(topology_plan.node_ids)}),
        physical_dof_count=topology_plan.physical_dof_count,
        solver_dof_count=topology_plan.solver_dof_count,
        inactive_physical_dofs_content_hash=content_hashes["inactive_physical_dofs"],
        authored_fixed_physical_dofs_content_hash=content_hashes[
            "authored_fixed_physical_dofs"
        ],
        constrained_physical_dofs_content_hash=content_hashes[
            "constrained_physical_dofs"
        ],
        free_physical_dofs_content_hash=content_hashes["free_physical_dofs"],
        constrained_solver_dofs_content_hash=content_hashes["constrained_solver_dofs"],
        free_solver_dofs_content_hash=content_hashes["free_solver_dofs"],
        solver_to_physical_global_dofs_content_hash=content_hashes[
            "solver_to_physical_global_dofs"
        ],
        partition_hash=partition_hash,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        receipt_hash=canonical_hash(_boundary_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_boundary_condition_receipt(receipt)


def _build_backend_receipt(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearBackendReceipt:
    try:
        backend_role = _BACKEND_ROLE_BY_MATRIX_BACKEND[terminal_receipt.matrix_backend]
    except KeyError as exc:
        raise FiberFrameNonlinearResultAdapterError(
            "fiber_frame_result_backend_unsupported",
            "/backend_receipt/matrix_backend",
            "J5 backend has no bounded NonlinearNumericalResultIR role mapping.",
        ) from exc
    final_step = terminal_receipt.step_receipts[-1]
    provisional = FiberFrameNonlinearBackendReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_BACKEND_SCHEMA_VERSION,
        receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE,
        backend_role=backend_role,
        matrix_backend=terminal_receipt.matrix_backend,
        deterministic_execution=True,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_operator_hash=topology_plan.operator_hash,
        execution_numeric_buffer_hash=topology_plan.numeric_buffer_hash,
        solver_config_hash=terminal_receipt.solver_config_hash,
        terminal_receipt_hash=terminal_receipt.terminal_receipt_hash,
        terminal_step_receipt_hash=final_step.step_receipt_hash,
        final_analytic_jacobian_data_hash=(
            final_step.jacobian_audit.analytic_jacobian_data_hash
        ),
        total_linear_solve_count=terminal_receipt.total_linear_solve_count,
        fallback_count=terminal_receipt.fallback_count,
        regularization_count=terminal_receipt.regularization_count,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        receipt_hash=canonical_hash(_backend_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_backend_receipt(receipt)


def _source_snapshot(
    binding: FiberFrameNonlinearResultSourceBinding,
) -> NonlinearNumericalResultSourceSnapshot:
    terminal_state = binding._kinematic_chain.committed_states[-1]
    terminal_bundle: MaterialStateBundle = binding._material_chain.projections[
        -1
    ].bundle
    return NonlinearNumericalResultSourceSnapshot(
        model_ir_content_hash=binding.model_ir_content_hash,
        execution_plan_hash=binding.execution_topology_plan_hash,
        equation_scaling_hash=binding.engine_equation_scaling_hash,
        reduced_csr_identity_hash=binding.reduced_system_receipt.identity_hash,
        operator_hash=binding.execution_operator_hash,
        state_hash=binding.terminal_kinematic_state_hash,
        state_epoch=binding.terminal_epoch,
        material_state_bundle_hash=binding.terminal_material_state_bundle_hash,
        integration_point_order_hash=terminal_bundle.integration_point_order_hash,
        path_history_hash=binding.path_history_hash,
        nonlinear_terminal_hash=binding.terminal_receipt_hash,
        full_residual_receipt_hash=binding.full_residual_receipt.receipt_hash,
        boundary_condition_receipt_hash=(
            binding.boundary_condition_receipt.receipt_hash
        ),
        backend_role=binding.backend_receipt.backend_role,
        backend_receipt_hash=binding.backend_receipt.receipt_hash,
        load_factor=binding.terminal_load_factor,
        time_s=0.0,
        dof_count=binding.physical_dof_count,
        displacement_global_si=terminal_state.array("canonical_displacement_si"),
    )


def validate_fiber_frame_nonlinear_reduced_system_receipt(
    receipt: FiberFrameNonlinearReducedSystemReceipt,
) -> FiberFrameNonlinearReducedSystemReceipt:
    if type(receipt) is not FiberFrameNonlinearReducedSystemReceipt:
        _fail("fiber_frame_result_reduced_type_invalid", "/", "Expected receipt.")
    if (
        receipt.schema_version
        != FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_SCHEMA_VERSION
        or receipt.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
        or receipt.system_profile != FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_PROFILE
    ):
        _fail(
            "fiber_frame_result_reduced_profile_invalid",
            "/",
            "Unsupported reduced-system receipt profile.",
        )
    for path, value in (
        ("/identity_hash", receipt.identity_hash),
        (
            "/bindings/execution_topology_plan_hash",
            receipt.execution_topology_plan_hash,
        ),
        ("/bindings/execution_topology_hash", receipt.execution_topology_hash),
        ("/bindings/execution_operator_hash", receipt.execution_operator_hash),
        (
            "/bindings/solver_coordinate_scaling_hash",
            receipt.solver_coordinate_scaling_hash,
        ),
        ("/bindings/terminal_step_receipt_hash", receipt.terminal_step_receipt_hash),
        (
            "/bindings/final_analytic_jacobian_data_hash",
            receipt.final_analytic_jacobian_data_hash,
        ),
        (
            "/bindings/final_analytic_jacobian_content_hash",
            receipt.final_analytic_jacobian_content_hash,
        ),
    ):
        _require_hash(value, path)
    physical_count = _positive_index(receipt.physical_dof_count, "/physical_dof_count")
    free_count = _positive_index(receipt.free_count, "/free_count")
    nnz = _positive_index(receipt.reduced_nnz, "/reduced_nnz")
    _validate_array_map(receipt._arrays, receipt.descriptors, _REDUCED_ARRAY_NAMES)
    if (
        receipt.array("free_physical_dofs").shape != (free_count,)
        or receipt.array("free_solver_dofs").shape != (free_count,)
        or receipt.array("free_csr_row_ptr").shape != (free_count + 1,)
        or receipt.array("free_csr_column_indices").shape != (nnz,)
        or np.any(receipt.array("free_physical_dofs") >= physical_count)
        or int(receipt.array("free_csr_row_ptr")[-1]) != nnz
        or np.any(receipt.array("free_csr_column_indices") >= free_count)
    ):
        _fail(
            "fiber_frame_result_reduced_array_semantics_invalid",
            "/array_descriptors",
            "Reduced-system array shape or index range is invalid.",
        )
    _require_empty_extensions(receipt.extensions)
    if receipt.identity_hash != canonical_hash(
        _reduced_payload(receipt, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_reduced_hash_mismatch",
            "/identity_hash",
            "Reduced-system identity hash is stale.",
        )
    return receipt


def validate_fiber_frame_nonlinear_full_residual_receipt(
    receipt: FiberFrameNonlinearFullResidualReceipt,
) -> FiberFrameNonlinearFullResidualReceipt:
    if type(receipt) is not FiberFrameNonlinearFullResidualReceipt:
        _fail("fiber_frame_result_residual_type_invalid", "/", "Expected receipt.")
    if (
        receipt.schema_version != FIBER_FRAME_NONLINEAR_RESULT_RESIDUAL_SCHEMA_VERSION
        or receipt.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_residual_profile_invalid",
            "/",
            "Unsupported full-residual receipt profile.",
        )
    for path, value in (
        ("/receipt_hash", receipt.receipt_hash),
        ("/bindings/terminal_receipt_hash", receipt.terminal_receipt_hash),
        ("/bindings/terminal_step_receipt_hash", receipt.terminal_step_receipt_hash),
        (
            "/bindings/physical_residual_trace_hash",
            receipt.physical_residual_trace_hash,
        ),
        ("/binary/source_residual_data_hash", receipt.source_residual_data_hash),
        (
            "/binary/source_residual_content_hash",
            receipt.source_residual_content_hash,
        ),
        (
            "/binary/canonical_si_residual_data_hash",
            receipt.canonical_si_residual_data_hash,
        ),
        (
            "/binary/canonical_si_residual_content_hash",
            receipt.canonical_si_residual_content_hash,
        ),
        ("/binary/scaled_residual_data_hash", receipt.scaled_residual_data_hash),
        (
            "/binary/scaled_residual_content_hash",
            receipt.scaled_residual_content_hash,
        ),
    ):
        _require_hash(value, path)
    trace = validate_fiber_frame_physical_residual_trace(receipt._trace)
    source = _descriptor_by_name(trace.descriptors, "raw_residual_source_3dof")
    raw_si = _descriptor_by_name(trace.descriptors, "raw_residual_si_6dof")
    scaled = _descriptor_by_name(trace.descriptors, "scaled_residual_6dof")
    expected = {
        "physical_residual_trace_hash": trace.trace_hash,
        "source_residual_data_hash": source.data_hash,
        "source_residual_content_hash": source.content_hash,
        "canonical_si_residual_data_hash": raw_si.data_hash,
        "canonical_si_residual_content_hash": raw_si.content_hash,
        "scaled_residual_data_hash": scaled.data_hash,
        "scaled_residual_content_hash": scaled.content_hash,
        "raw_translation_linf_n": trace.raw_translation_linf_n,
        "raw_rotation_linf_nm": trace.raw_rotation_linf_nm,
        "scaled_residual_linf": trace.scaled_linf,
    }
    if any(getattr(receipt, name) != value for name, value in expected.items()):
        _fail(
            "fiber_frame_result_residual_trace_binding_mismatch",
            "/bindings/physical_residual_trace_hash",
            "Full-residual receipt differs from its retained J2 trace.",
        )
    tolerance = _positive_float(
        receipt.scaled_residual_tolerance,
        "/observations/scaled_residual_tolerance",
    )
    if (
        tolerance != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
        or receipt.residual_gate_passed is not True
        or receipt.scaled_residual_linf > tolerance
    ):
        _fail(
            "fiber_frame_result_residual_gate_failed",
            "/gates/residual_gate_passed",
            "Final physical residual does not satisfy the fixed J5 gate.",
        )
    for name in (
        "raw_translation_linf_n",
        "raw_rotation_linf_nm",
        "scaled_residual_linf",
    ):
        _nonnegative_float(getattr(receipt, name), f"/observations/{name}")
    _require_empty_extensions(receipt.extensions)
    if receipt.receipt_hash != canonical_hash(
        _residual_payload(receipt, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_residual_hash_mismatch",
            "/receipt_hash",
            "Full-residual receipt hash is stale.",
        )
    return receipt


def validate_fiber_frame_nonlinear_boundary_condition_receipt(
    receipt: FiberFrameNonlinearBoundaryConditionReceipt,
) -> FiberFrameNonlinearBoundaryConditionReceipt:
    if type(receipt) is not FiberFrameNonlinearBoundaryConditionReceipt:
        _fail("fiber_frame_result_boundary_type_invalid", "/", "Expected receipt.")
    if (
        receipt.schema_version != FIBER_FRAME_NONLINEAR_RESULT_BOUNDARY_SCHEMA_VERSION
        or receipt.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_boundary_profile_invalid",
            "/",
            "Unsupported boundary-condition receipt profile.",
        )
    _stable_id(receipt.case_id, "/bindings/case_id")
    for path, value in (
        ("/receipt_hash", receipt.receipt_hash),
        ("/bindings/problem_contract_hash", receipt.problem_contract_hash),
        (
            "/bindings/execution_topology_plan_hash",
            receipt.execution_topology_plan_hash,
        ),
        ("/bindings/node_order_hash", receipt.node_order_hash),
        (
            "/partitions/inactive_physical_dofs_content_hash",
            receipt.inactive_physical_dofs_content_hash,
        ),
        (
            "/partitions/authored_fixed_physical_dofs_content_hash",
            receipt.authored_fixed_physical_dofs_content_hash,
        ),
        (
            "/partitions/constrained_physical_dofs_content_hash",
            receipt.constrained_physical_dofs_content_hash,
        ),
        (
            "/partitions/free_physical_dofs_content_hash",
            receipt.free_physical_dofs_content_hash,
        ),
        (
            "/partitions/constrained_solver_dofs_content_hash",
            receipt.constrained_solver_dofs_content_hash,
        ),
        (
            "/partitions/free_solver_dofs_content_hash",
            receipt.free_solver_dofs_content_hash,
        ),
        (
            "/partitions/solver_to_physical_global_dofs_content_hash",
            receipt.solver_to_physical_global_dofs_content_hash,
        ),
        ("/partitions/partition_hash", receipt.partition_hash),
    ):
        _require_hash(value, path)
    physical_count = _positive_index(receipt.physical_dof_count, "/physical_dof_count")
    solver_count = _positive_index(receipt.solver_dof_count, "/solver_dof_count")
    if physical_count % 6 != 0 or solver_count * 2 != physical_count:
        _fail(
            "fiber_frame_result_boundary_dof_count_invalid",
            "/physical_dof_count",
            "Boundary receipt must preserve six physical and three solver DOFs per node.",
        )
    expected_partition_hash = canonical_hash(
        {
            "inactive_physical_dofs": receipt.inactive_physical_dofs_content_hash,
            "authored_fixed_physical_dofs": (
                receipt.authored_fixed_physical_dofs_content_hash
            ),
            "constrained_physical_dofs": (
                receipt.constrained_physical_dofs_content_hash
            ),
            "free_physical_dofs": receipt.free_physical_dofs_content_hash,
            "constrained_solver_dofs": receipt.constrained_solver_dofs_content_hash,
            "free_solver_dofs": receipt.free_solver_dofs_content_hash,
            "solver_to_physical_global_dofs": (
                receipt.solver_to_physical_global_dofs_content_hash
            ),
        }
    )
    if receipt.partition_hash != expected_partition_hash:
        _fail(
            "fiber_frame_result_boundary_partition_hash_mismatch",
            "/partitions/partition_hash",
            "Boundary partition hash is stale.",
        )
    _require_empty_extensions(receipt.extensions)
    if receipt.receipt_hash != canonical_hash(
        _boundary_payload(receipt, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_boundary_hash_mismatch",
            "/receipt_hash",
            "Boundary-condition receipt hash is stale.",
        )
    return receipt


def validate_fiber_frame_nonlinear_backend_receipt(
    receipt: FiberFrameNonlinearBackendReceipt,
) -> FiberFrameNonlinearBackendReceipt:
    if type(receipt) is not FiberFrameNonlinearBackendReceipt:
        _fail("fiber_frame_result_backend_type_invalid", "/", "Expected receipt.")
    if (
        receipt.schema_version != FIBER_FRAME_NONLINEAR_RESULT_BACKEND_SCHEMA_VERSION
        or receipt.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_backend_profile_invalid",
            "/",
            "Unsupported backend receipt profile.",
        )
    if (
        receipt.matrix_backend not in _BACKEND_ROLE_BY_MATRIX_BACKEND
        or _BACKEND_ROLE_BY_MATRIX_BACKEND[receipt.matrix_backend]
        != receipt.backend_role
        or receipt.deterministic_execution is not True
    ):
        _fail(
            "fiber_frame_result_backend_mapping_invalid",
            "/backend",
            "Backend role does not match the executed deterministic CPU backend.",
        )
    for path, value in (
        ("/receipt_hash", receipt.receipt_hash),
        (
            "/bindings/execution_topology_plan_hash",
            receipt.execution_topology_plan_hash,
        ),
        ("/bindings/execution_operator_hash", receipt.execution_operator_hash),
        (
            "/bindings/execution_numeric_buffer_hash",
            receipt.execution_numeric_buffer_hash,
        ),
        ("/bindings/solver_config_hash", receipt.solver_config_hash),
        ("/bindings/terminal_receipt_hash", receipt.terminal_receipt_hash),
        ("/bindings/terminal_step_receipt_hash", receipt.terminal_step_receipt_hash),
        (
            "/bindings/final_analytic_jacobian_data_hash",
            receipt.final_analytic_jacobian_data_hash,
        ),
    ):
        _require_hash(value, path)
    _positive_index(
        receipt.total_linear_solve_count,
        "/observations/total_linear_solve_count",
    )
    if (
        type(receipt.fallback_count) is not int
        or type(receipt.regularization_count) is not int
        or receipt.fallback_count != 0
        or receipt.regularization_count != 0
    ):
        _fail(
            "fiber_frame_result_backend_fallback_forbidden",
            "/observations",
            "Fallback and regularization counts must remain exact zero.",
        )
    _require_empty_extensions(receipt.extensions)
    if receipt.receipt_hash != canonical_hash(
        _backend_payload(receipt, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_backend_hash_mismatch",
            "/receipt_hash",
            "Backend receipt hash is stale.",
        )
    return receipt


def validate_fiber_frame_nonlinear_result_source_binding_shape(
    binding: FiberFrameNonlinearResultSourceBinding,
) -> FiberFrameNonlinearResultSourceBinding:
    if type(binding) is not FiberFrameNonlinearResultSourceBinding:
        _fail("fiber_frame_result_source_type_invalid", "/", "Expected source binding.")
    if (
        binding.schema_version
        != FIBER_FRAME_NONLINEAR_RESULT_SOURCE_BINDING_SCHEMA_VERSION
        or binding.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
        or binding.state_ir_usage_profile != FIBER_FRAME_STATE_IR_USAGE_PROFILE
        or binding.time_profile != FIBER_FRAME_NONLINEAR_RESULT_TIME_PROFILE
    ):
        _fail(
            "fiber_frame_result_source_profile_invalid",
            "/",
            "Unsupported source-binding profile or StateIR usage decision.",
        )
    retained_sources = (
        (binding._problem, StatefulFiberFrame2DProblem),
        (binding._topology_plan, FiberFrameNonlinearExecutionTopologyPlan),
        (binding._physical_scaling, FiberFramePhysicalEquationScalingBinding),
        (binding._checkpoint_chain, StatefulFiberFrame2DCheckpointChain),
        (binding._kinematic_chain, FiberFrameNonlinearKinematicStateChain),
        (binding._material_chain, FiberFrameMaterialStateProjectionChain),
        (
            binding._execution_state_binding,
            FiberFrameNonlinearExecutionStateBinding,
        ),
        (binding._load_path, StatefulFiberFrame2DLoadPathResult),
        (binding._terminal_receipt, FiberFrameNonlinearTerminalReceipt),
    )
    if any(type(value) is not expected for value, expected in retained_sources):
        _fail(
            "fiber_frame_result_source_retained_type_invalid",
            "/source",
            "Retained J1--J5 source objects must use their exact contract types.",
        )
    _stable_id(binding.case_id, "/bindings/case_id")
    for name in (
        "binding_hash",
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_hash",
        "execution_topology_hash",
        "execution_operator_hash",
        "execution_numeric_buffer_hash",
        "solver_coordinate_scaling_hash",
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "execution_state_binding_hash",
        "checkpoint_chain_hash",
        "kinematic_state_chain_hash",
        "material_state_projection_chain_hash",
        "terminal_receipt_hash",
        "terminal_checkpoint_state_hash",
        "terminal_kinematic_state_hash",
        "terminal_material_state_bundle_hash",
        "path_history_hash",
        "terminal_displacement_data_hash",
        "terminal_displacement_content_hash",
        "terminal_displacement_coordinate_order_hash",
    ):
        _require_hash(getattr(binding, name), f"/bindings/{name}")
    epoch = _positive_index(binding.terminal_epoch, "/terminal/epoch")
    accepted_step_count = _positive_index(
        binding.accepted_step_count,
        "/terminal/accepted_step_count",
    )
    count = _positive_index(binding.physical_dof_count, "/terminal/dof_count")
    if count % 6 != 0:
        _fail(
            "fiber_frame_result_source_dof_count_invalid",
            "/terminal/dof_count",
            "Terminal displacement must use canonical six-DOF node order.",
        )
    load_factor = _finite_float(binding.terminal_load_factor, "/terminal/load_factor")
    residual_tolerance = _positive_float(
        binding.solver_residual_tolerance,
        "/terminal/solver_residual_tolerance",
    )
    increment_tolerance = _positive_float(
        binding.solver_increment_tolerance_m,
        "/terminal/solver_increment_tolerance_m",
    )
    final_increment = _nonnegative_float(
        binding.final_solver_coordinate_increment_linf_m,
        "/terminal/final_solver_coordinate_increment_linf_m",
    )
    if (
        load_factor != 1.0
        or epoch != accepted_step_count
        or residual_tolerance != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
        or increment_tolerance != FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
        or final_increment > increment_tolerance
        or binding.residual_gate_passed is not True
        or binding.increment_gate_passed is not True
        or binding.convergence_gate_passed is not True
    ):
        _fail(
            "fiber_frame_result_source_terminal_gate_invalid",
            "/terminal",
            "The adapter requires a full-load terminal state passing both exact gates.",
        )
    reduced = validate_fiber_frame_nonlinear_reduced_system_receipt(
        binding.reduced_system_receipt
    )
    residual = validate_fiber_frame_nonlinear_full_residual_receipt(
        binding.full_residual_receipt
    )
    boundary = validate_fiber_frame_nonlinear_boundary_condition_receipt(
        binding.boundary_condition_receipt
    )
    backend = validate_fiber_frame_nonlinear_backend_receipt(binding.backend_receipt)
    if (
        reduced.execution_topology_plan_hash != binding.execution_topology_plan_hash
        or reduced.execution_topology_hash != binding.execution_topology_hash
        or reduced.execution_operator_hash != binding.execution_operator_hash
        or reduced.solver_coordinate_scaling_hash
        != binding.solver_coordinate_scaling_hash
        or reduced.terminal_step_receipt_hash != residual.terminal_step_receipt_hash
        or residual.terminal_receipt_hash != binding.terminal_receipt_hash
        or boundary.problem_contract_hash != binding.problem_contract_hash
        or boundary.execution_topology_plan_hash != binding.execution_topology_plan_hash
        or boundary.case_id != binding.case_id
        or boundary.physical_dof_count != count
        or backend.execution_topology_plan_hash != binding.execution_topology_plan_hash
        or backend.execution_operator_hash != binding.execution_operator_hash
        or backend.execution_numeric_buffer_hash
        != binding.execution_numeric_buffer_hash
        or backend.terminal_receipt_hash != binding.terminal_receipt_hash
        or backend.terminal_step_receipt_hash != residual.terminal_step_receipt_hash
        or backend.final_analytic_jacobian_data_hash
        != reduced.final_analytic_jacobian_data_hash
        or residual.scaled_residual_tolerance != residual_tolerance
        or residual.residual_gate_passed != binding.residual_gate_passed
        or binding._terminal_receipt.solver_increment_tolerance_m != increment_tolerance
        or binding._terminal_receipt.final_solver_coordinate_increment_linf_m
        != final_increment
        or binding._terminal_receipt.step_receipts[-1].increment_gate_passed
        != binding.increment_gate_passed
        or binding._terminal_receipt.step_receipts[-1].convergence_gate_passed
        != binding.convergence_gate_passed
        or epoch != binding._terminal_receipt.terminal_epoch
    ):
        _fail(
            "fiber_frame_result_source_receipt_binding_mismatch",
            "/receipts",
            "Nested result receipts do not share one exact terminal source chain.",
        )
    _require_empty_extensions(binding.extensions)
    if binding.binding_hash != canonical_hash(
        _source_binding_payload(binding, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_source_hash_mismatch",
            "/binding_hash",
            "Source-binding hash is stale.",
        )
    return binding


def validate_fiber_frame_nonlinear_result_source_binding(
    binding: FiberFrameNonlinearResultSourceBinding,
) -> FiberFrameNonlinearResultSourceBinding:
    """Replay all retained J1--J5 inputs and compare the exact source binding."""

    validate_fiber_frame_nonlinear_result_source_binding_shape(binding)
    expected = _build_source_binding(
        binding._problem,
        binding._topology_plan,
        binding._physical_scaling,
        binding._checkpoint_chain,
        binding._kinematic_chain,
        binding._material_chain,
        binding._execution_state_binding,
        binding._load_path,
        binding._terminal_receipt,
    )
    if binding.to_manifest() != expected.to_manifest():
        _fail(
            "fiber_frame_result_source_replay_mismatch",
            "/",
            "Source binding does not replay exactly from retained J1--J5 inputs.",
        )
    return binding


def validate_fiber_frame_nonlinear_numerical_result_adapter(
    adapter: FiberFrameNonlinearNumericalResultAdapter,
) -> FiberFrameNonlinearNumericalResultAdapter:
    if type(adapter) is not FiberFrameNonlinearNumericalResultAdapter:
        _fail("fiber_frame_result_adapter_type_invalid", "/", "Expected adapter.")
    if (
        adapter.schema_version != FIBER_FRAME_NONLINEAR_RESULT_ADAPTER_SCHEMA_VERSION
        or adapter.authority_profile != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_adapter_profile_invalid",
            "/",
            "Unsupported fiber-frame result adapter profile.",
        )
    source = validate_fiber_frame_nonlinear_result_source_binding(
        adapter.source_binding
    )
    result = validate_nonlinear_numerical_result_ir(adapter.numerical_result)
    snapshot = _source_snapshot(source)
    expected = {
        "model_ir_content_hash": snapshot.model_ir_content_hash,
        "execution_plan_hash": snapshot.execution_plan_hash,
        "equation_scaling_hash": snapshot.equation_scaling_hash,
        "reduced_csr_identity_hash": snapshot.reduced_csr_identity_hash,
        "operator_hash": snapshot.operator_hash,
        "state_hash": snapshot.state_hash,
        "state_epoch": snapshot.state_epoch,
        "material_state_bundle_hash": snapshot.material_state_bundle_hash,
        "integration_point_order_hash": snapshot.integration_point_order_hash,
        "path_history_hash": snapshot.path_history_hash,
        "nonlinear_terminal_hash": snapshot.nonlinear_terminal_hash,
        "full_residual_receipt_hash": snapshot.full_residual_receipt_hash,
        "boundary_condition_receipt_hash": snapshot.boundary_condition_receipt_hash,
        "backend_role": snapshot.backend_role,
        "backend_receipt_hash": snapshot.backend_receipt_hash,
        "load_factor": snapshot.load_factor,
        "time_s": snapshot.time_s,
        "dof_count": snapshot.dof_count,
    }
    if (
        any(getattr(result, name) != value for name, value in expected.items())
        or result._source_adapter is not source
        or result.authority_profile != NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_adapter_result_binding_mismatch",
            "/numerical_result",
            "NumericalResultIR does not bind the exact retained fiber-frame source.",
        )
    result_manifest = result.to_manifest()
    if result_manifest["claim_boundary"] != dict(
        NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY
    ):
        _fail(
            "fiber_frame_result_adapter_claim_boundary_invalid",
            "/numerical_result/claim_boundary",
            "Nested result does not declare adapter-bound kinematic authority.",
        )
    _require_empty_extensions(adapter.extensions)
    _require_hash(adapter.adapter_hash, "/adapter_hash")
    if adapter.adapter_hash != canonical_hash(
        _adapter_payload(adapter, include_hash=False)
    ):
        _fail(
            "fiber_frame_result_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash is stale.",
        )
    return adapter


def validate_fiber_frame_nonlinear_result_adapter_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the strict descriptor-only adapter manifest."""

    normalized = _strict_json_object(payload, "/")
    _exact_keys(
        normalized,
        {
            "schema_version",
            "adapter_hash",
            "authority_profile",
            "source_binding",
            "numerical_result",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        normalized["schema_version"]
        != FIBER_FRAME_NONLINEAR_RESULT_ADAPTER_SCHEMA_VERSION
        or normalized["authority_profile"]
        != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_manifest_profile_invalid",
            "/",
            "Unsupported adapter manifest profile.",
        )
    _require_hash(normalized["adapter_hash"], "/adapter_hash")
    _require_claim_boundary(
        normalized["claim_boundary"],
        FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    _require_empty_manifest_extensions(normalized["extensions"], "/extensions")
    source = _validate_source_binding_manifest(
        _manifest_object(normalized["source_binding"], "/source_binding")
    )
    result = validate_nonlinear_result_manifest(
        _manifest_object(normalized["numerical_result"], "/numerical_result")
    )
    result_bindings = result["bindings"]
    source_bindings = source["result_bindings"]
    expected = {
        "model_ir_content_hash": source["bindings"]["model_ir_content_hash"],
        "execution_plan_hash": source["bindings"]["execution_topology_plan_hash"],
        "equation_scaling_hash": source["bindings"]["engine_equation_scaling_hash"],
        "reduced_csr_identity_hash": source["receipts"]["reduced_system"][
            "identity_hash"
        ],
        "operator_hash": source["bindings"]["execution_operator_hash"],
        "state_hash": source["bindings"]["terminal_kinematic_state_hash"],
        "state_epoch": source["terminal"]["epoch"],
        "material_state_bundle_hash": source["bindings"][
            "terminal_material_state_bundle_hash"
        ],
        "path_history_hash": source["bindings"]["path_history_hash"],
        "nonlinear_terminal_hash": source["bindings"]["terminal_receipt_hash"],
        "full_residual_receipt_hash": source["receipts"]["full_residual"][
            "receipt_hash"
        ],
        "boundary_condition_receipt_hash": source["receipts"]["boundary_condition"][
            "receipt_hash"
        ],
    }
    if (
        any(result_bindings[name] != value for name, value in expected.items())
        or result_bindings["integration_point_order_hash"]
        != source_bindings["integration_point_order_hash"]
        or result["backend"]["role"] != source["receipts"]["backend"]["backend"]["role"]
        or result["backend"]["receipt_hash"]
        != source["receipts"]["backend"]["receipt_hash"]
        or result["load_factor"] != source["terminal"]["load_factor"]
        or result["time_s"] != 0.0
        or result["dof_count"] != source["terminal"]["physical_dof_count"]
        or result["displacement_artifact"]["data_hash"]
        != source["terminal"]["displacement_data_hash"]
        or result["claim_boundary"] != dict(NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY)
    ):
        _fail(
            "fiber_frame_result_manifest_binding_mismatch",
            "/numerical_result",
            "Nested result manifest differs from the source-binding receipts.",
        )
    if normalized["adapter_hash"] != canonical_hash(
        {key: value for key, value in normalized.items() if key != "adapter_hash"}
    ):
        _fail(
            "fiber_frame_result_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter manifest hash is stale.",
        )
    return normalized


def _validate_source_binding_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "binding_hash",
            "authority_profile",
            "state_ir_usage_profile",
            "time_profile",
            "source_schema_versions",
            "bindings",
            "result_bindings",
            "terminal",
            "receipts",
            "claim_boundary",
            "extensions",
        },
        "/source_binding",
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_NONLINEAR_RESULT_SOURCE_BINDING_SCHEMA_VERSION
        or manifest["authority_profile"]
        != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
        or manifest["state_ir_usage_profile"] != FIBER_FRAME_STATE_IR_USAGE_PROFILE
        or manifest["time_profile"] != FIBER_FRAME_NONLINEAR_RESULT_TIME_PROFILE
        or manifest["source_schema_versions"] != dict(_SOURCE_SCHEMA_VERSIONS)
    ):
        _fail(
            "fiber_frame_result_source_manifest_profile_invalid",
            "/source_binding",
            "Unsupported source-binding manifest profile.",
        )
    _require_hash(manifest["binding_hash"], "/source_binding/binding_hash")
    bindings = _manifest_object(manifest["bindings"], "/source_binding/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "case_id",
            "execution_topology_plan_hash",
            "execution_topology_hash",
            "execution_operator_hash",
            "execution_numeric_buffer_hash",
            "solver_coordinate_scaling_hash",
            "physical_equation_scaling_binding_hash",
            "engine_equation_scaling_hash",
            "execution_state_binding_hash",
            "checkpoint_chain_hash",
            "kinematic_state_chain_hash",
            "material_state_projection_chain_hash",
            "terminal_receipt_hash",
            "terminal_checkpoint_state_hash",
            "terminal_kinematic_state_hash",
            "terminal_material_state_bundle_hash",
            "path_history_hash",
        },
        "/source_binding/bindings",
    )
    for name, value in bindings.items():
        if name == "case_id":
            _stable_id(value, f"/source_binding/bindings/{name}")
        else:
            _require_hash(value, f"/source_binding/bindings/{name}")
    result_bindings = _manifest_object(
        manifest["result_bindings"],
        "/source_binding/result_bindings",
    )
    _exact_keys(
        result_bindings,
        {"integration_point_order_hash"},
        "/source_binding/result_bindings",
    )
    _require_hash(
        result_bindings["integration_point_order_hash"],
        "/source_binding/result_bindings/integration_point_order_hash",
    )
    terminal = _manifest_object(manifest["terminal"], "/source_binding/terminal")
    _exact_keys(
        terminal,
        {
            "epoch",
            "load_factor",
            "accepted_step_count",
            "solver_residual_tolerance",
            "solver_increment_tolerance_m",
            "final_solver_coordinate_increment_linf_m",
            "residual_gate_passed",
            "increment_gate_passed",
            "convergence_gate_passed",
            "physical_dof_count",
            "displacement_data_hash",
            "displacement_content_hash",
            "displacement_coordinate_order_hash",
        },
        "/source_binding/terminal",
    )
    epoch = _positive_index(terminal["epoch"], "/source_binding/terminal/epoch")
    accepted_step_count = _positive_index(
        terminal["accepted_step_count"],
        "/source_binding/terminal/accepted_step_count",
    )
    count = _positive_index(
        terminal["physical_dof_count"],
        "/source_binding/terminal/physical_dof_count",
    )
    if count % 6 != 0:
        _fail(
            "fiber_frame_result_manifest_dof_count_invalid",
            "/source_binding/terminal/physical_dof_count",
            "Manifest displacement order must contain six DOFs per node.",
        )
    load_factor = _finite_float(
        terminal["load_factor"],
        "/source_binding/terminal/load_factor",
    )
    residual_tolerance = _positive_float(
        terminal["solver_residual_tolerance"],
        "/source_binding/terminal/solver_residual_tolerance",
    )
    increment_tolerance = _positive_float(
        terminal["solver_increment_tolerance_m"],
        "/source_binding/terminal/solver_increment_tolerance_m",
    )
    final_increment = _nonnegative_float(
        terminal["final_solver_coordinate_increment_linf_m"],
        "/source_binding/terminal/final_solver_coordinate_increment_linf_m",
    )
    if (
        load_factor != 1.0
        or epoch != accepted_step_count
        or residual_tolerance != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
        or increment_tolerance != FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
        or final_increment > increment_tolerance
        or terminal["residual_gate_passed"] is not True
        or terminal["increment_gate_passed"] is not True
        or terminal["convergence_gate_passed"] is not True
    ):
        _fail(
            "fiber_frame_result_manifest_terminal_gate_invalid",
            "/source_binding/terminal",
            "Manifest terminal must pass both exact full-load convergence gates.",
        )
    for name in (
        "displacement_data_hash",
        "displacement_content_hash",
        "displacement_coordinate_order_hash",
    ):
        _require_hash(terminal[name], f"/source_binding/terminal/{name}")
    receipts = _manifest_object(manifest["receipts"], "/source_binding/receipts")
    _exact_keys(
        receipts,
        {"reduced_system", "full_residual", "boundary_condition", "backend"},
        "/source_binding/receipts",
    )
    _validate_reduced_manifest(
        _manifest_object(
            receipts["reduced_system"], "/source_binding/receipts/reduced_system"
        )
    )
    _validate_residual_manifest(
        _manifest_object(
            receipts["full_residual"], "/source_binding/receipts/full_residual"
        )
    )
    _validate_boundary_manifest(
        _manifest_object(
            receipts["boundary_condition"],
            "/source_binding/receipts/boundary_condition",
        )
    )
    _validate_backend_manifest(
        _manifest_object(receipts["backend"], "/source_binding/receipts/backend")
    )
    reduced = receipts["reduced_system"]
    residual = receipts["full_residual"]
    boundary = receipts["boundary_condition"]
    backend = receipts["backend"]
    if (
        reduced["bindings"]["execution_topology_plan_hash"]
        != bindings["execution_topology_plan_hash"]
        or reduced["bindings"]["execution_topology_hash"]
        != bindings["execution_topology_hash"]
        or reduced["bindings"]["execution_operator_hash"]
        != bindings["execution_operator_hash"]
        or reduced["bindings"]["solver_coordinate_scaling_hash"]
        != bindings["solver_coordinate_scaling_hash"]
        or reduced["counts"]["physical_dof_count"] != terminal["physical_dof_count"]
        or residual["bindings"]["terminal_receipt_hash"]
        != bindings["terminal_receipt_hash"]
        or residual["bindings"]["terminal_step_receipt_hash"]
        != reduced["bindings"]["terminal_step_receipt_hash"]
        or residual["observations"]["scaled_residual_tolerance"] != residual_tolerance
        or residual["gates"]["residual_gate_passed"] != terminal["residual_gate_passed"]
        or boundary["bindings"]["problem_contract_hash"]
        != bindings["problem_contract_hash"]
        or boundary["bindings"]["execution_topology_plan_hash"]
        != bindings["execution_topology_plan_hash"]
        or boundary["bindings"]["case_id"] != bindings["case_id"]
        or boundary["counts"]["physical_dof_count"] != terminal["physical_dof_count"]
        or backend["bindings"]["execution_topology_plan_hash"]
        != bindings["execution_topology_plan_hash"]
        or backend["bindings"]["execution_operator_hash"]
        != bindings["execution_operator_hash"]
        or backend["bindings"]["execution_numeric_buffer_hash"]
        != bindings["execution_numeric_buffer_hash"]
        or backend["bindings"]["terminal_receipt_hash"]
        != bindings["terminal_receipt_hash"]
        or backend["bindings"]["terminal_step_receipt_hash"]
        != residual["bindings"]["terminal_step_receipt_hash"]
        or backend["bindings"]["final_analytic_jacobian_data_hash"]
        != reduced["bindings"]["final_analytic_jacobian_data_hash"]
    ):
        _fail(
            "fiber_frame_result_source_manifest_receipt_binding_mismatch",
            "/source_binding/receipts",
            "Nested manifest receipts do not share one exact source chain.",
        )
    _require_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY,
        "/source_binding/claim_boundary",
    )
    _require_empty_manifest_extensions(
        manifest["extensions"],
        "/source_binding/extensions",
    )
    if manifest["binding_hash"] != canonical_hash(
        {key: value for key, value in manifest.items() if key != "binding_hash"}
    ):
        _fail(
            "fiber_frame_result_source_hash_mismatch",
            "/source_binding/binding_hash",
            "Source-binding manifest hash is stale.",
        )
    return dict(manifest)


def _validate_reduced_manifest(manifest: Mapping[str, Any]) -> None:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "identity_hash",
            "authority_profile",
            "system_profile",
            "storage_profile",
            "bindings",
            "counts",
            "array_descriptors",
            "claim_boundary",
            "extensions",
        },
        "/source_binding/receipts/reduced_system",
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_SCHEMA_VERSION
        or manifest["authority_profile"]
        != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
        or manifest["system_profile"]
        != FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_PROFILE
        or manifest["storage_profile"] != FIBER_FRAME_NONLINEAR_RESULT_STORAGE_PROFILE
    ):
        _fail(
            "fiber_frame_result_reduced_manifest_profile_invalid",
            "/source_binding/receipts/reduced_system",
            "Unsupported reduced-system manifest profile.",
        )
    _require_hash(manifest["identity_hash"], "/reduced_system/identity_hash")
    _validate_exact_hash_object(
        manifest["bindings"],
        {
            "execution_topology_plan_hash",
            "execution_topology_hash",
            "execution_operator_hash",
            "solver_coordinate_scaling_hash",
            "terminal_step_receipt_hash",
            "final_analytic_jacobian_data_hash",
            "final_analytic_jacobian_content_hash",
        },
        "/reduced_system/bindings",
    )
    counts = _manifest_object(manifest["counts"], "/reduced_system/counts")
    _exact_keys(
        counts,
        {"physical_dof_count", "free_count", "reduced_nnz"},
        "/reduced_system/counts",
    )
    for name, value in counts.items():
        _positive_index(value, f"/reduced_system/counts/{name}")
    if (
        counts["physical_dof_count"] % 6 != 0
        or counts["free_count"] > counts["physical_dof_count"]
    ):
        _fail(
            "fiber_frame_result_reduced_manifest_counts_invalid",
            "/reduced_system/counts",
            "Reduced-system counts are inconsistent with canonical six-DOF space.",
        )
    descriptors = manifest["array_descriptors"]
    if type(descriptors) is not list or len(descriptors) != len(_REDUCED_ARRAY_NAMES):
        _fail(
            "fiber_frame_result_reduced_manifest_descriptors_invalid",
            "/reduced_system/array_descriptors",
            "Reduced-system descriptor set is incomplete.",
        )
    if [row.get("name") for row in descriptors if isinstance(row, dict)] != list(
        _REDUCED_ARRAY_NAMES
    ):
        _fail(
            "fiber_frame_result_reduced_manifest_descriptors_invalid",
            "/reduced_system/array_descriptors",
            "Reduced-system descriptor order changed.",
        )
    expected_dtypes = ("<i4", "<i4", "<i8", "<i4")
    expected_lengths = (
        counts["free_count"],
        counts["free_count"],
        counts["free_count"] + 1,
        counts["reduced_nnz"],
    )
    for index, row in enumerate(descriptors):
        descriptor = _manifest_object(row, f"/reduced_system/array_descriptors/{index}")
        _exact_keys(
            descriptor,
            {
                "name",
                "dtype",
                "shape",
                "layout",
                "byte_length",
                "data_hash",
                "content_hash",
            },
            f"/reduced_system/array_descriptors/{index}",
        )
        _require_hash(
            descriptor["data_hash"],
            f"/reduced_system/array_descriptors/{index}/data_hash",
        )
        _require_hash(
            descriptor["content_hash"],
            f"/reduced_system/array_descriptors/{index}/content_hash",
        )
        if (
            descriptor["name"] != _REDUCED_ARRAY_NAMES[index]
            or descriptor["dtype"] != expected_dtypes[index]
            or type(descriptor["shape"]) is not list
            or len(descriptor["shape"]) != 1
            or type(descriptor["shape"][0]) is not int
            or descriptor["shape"] != [expected_lengths[index]]
            or descriptor["layout"] != "C"
            or type(descriptor["byte_length"]) is not int
            or descriptor["byte_length"]
            != np.dtype(expected_dtypes[index]).itemsize * expected_lengths[index]
            or descriptor["content_hash"]
            != canonical_hash(
                {
                    key: value
                    for key, value in descriptor.items()
                    if key != "content_hash"
                }
            )
        ):
            _fail(
                "fiber_frame_result_reduced_manifest_descriptor_invalid",
                f"/reduced_system/array_descriptors/{index}",
                "Reduced-system descriptor metadata or content hash is invalid.",
            )
    _require_claim_boundary(
        manifest["claim_boundary"],
        _REDUCED_SYSTEM_CLAIM_BOUNDARY,
        "/reduced_system/claim_boundary",
    )
    _require_empty_manifest_extensions(
        manifest["extensions"], "/reduced_system/extensions"
    )
    _require_canonical_section_hash(
        manifest, "identity_hash", "/reduced_system/identity_hash"
    )


def _validate_residual_manifest(manifest: Mapping[str, Any]) -> None:
    _validate_simple_receipt_manifest(
        manifest,
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_RESIDUAL_SCHEMA_VERSION,
        hash_key="receipt_hash",
        claim_boundary=_RESIDUAL_CLAIM_BOUNDARY,
        required_sections={"bindings", "binary_identities", "observations", "gates"},
        path="/full_residual",
    )
    _validate_exact_hash_object(
        manifest["bindings"],
        {
            "terminal_receipt_hash",
            "terminal_step_receipt_hash",
            "physical_residual_trace_hash",
        },
        "/full_residual/bindings",
    )
    _validate_exact_hash_object(
        manifest["binary_identities"],
        {
            "source_residual_data_hash",
            "source_residual_content_hash",
            "canonical_si_residual_data_hash",
            "canonical_si_residual_content_hash",
            "scaled_residual_data_hash",
            "scaled_residual_content_hash",
        },
        "/full_residual/binary_identities",
    )
    observations = _manifest_object(
        manifest["observations"],
        "/full_residual/observations",
    )
    _exact_keys(
        observations,
        {
            "raw_translation_linf_n",
            "raw_rotation_linf_nm",
            "scaled_residual_linf",
            "scaled_residual_tolerance",
        },
        "/full_residual/observations",
    )
    for name in (
        "raw_translation_linf_n",
        "raw_rotation_linf_nm",
        "scaled_residual_linf",
    ):
        _nonnegative_float(observations[name], f"/full_residual/observations/{name}")
    tolerance = _positive_float(
        observations["scaled_residual_tolerance"],
        "/full_residual/observations/scaled_residual_tolerance",
    )
    gates = _manifest_object(manifest["gates"], "/full_residual/gates")
    if (
        gates != {"residual_gate_passed": True}
        or tolerance != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
        or observations["scaled_residual_linf"] > tolerance
    ):
        _fail(
            "fiber_frame_result_residual_manifest_gate_failed",
            "/full_residual/gates",
            "Residual manifest must retain the passed J5 gate.",
        )
    _require_canonical_section_hash(
        manifest,
        "receipt_hash",
        "/full_residual/receipt_hash",
    )


def _validate_boundary_manifest(manifest: Mapping[str, Any]) -> None:
    _validate_simple_receipt_manifest(
        manifest,
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_BOUNDARY_SCHEMA_VERSION,
        hash_key="receipt_hash",
        claim_boundary=_BOUNDARY_CLAIM_BOUNDARY,
        required_sections={"bindings", "counts", "partitions"},
        path="/boundary_condition",
    )
    bindings = _manifest_object(manifest["bindings"], "/boundary_condition/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "execution_topology_plan_hash",
            "case_id",
            "node_order_hash",
        },
        "/boundary_condition/bindings",
    )
    for name in (
        "problem_contract_hash",
        "execution_topology_plan_hash",
        "node_order_hash",
    ):
        _require_hash(bindings[name], f"/boundary_condition/bindings/{name}")
    _stable_id(bindings["case_id"], "/boundary_condition/bindings/case_id")
    counts = _manifest_object(manifest["counts"], "/boundary_condition/counts")
    _exact_keys(
        counts,
        {"physical_dof_count", "solver_dof_count"},
        "/boundary_condition/counts",
    )
    physical_count = _positive_index(
        counts["physical_dof_count"],
        "/boundary_condition/counts/physical_dof_count",
    )
    solver_count = _positive_index(
        counts["solver_dof_count"],
        "/boundary_condition/counts/solver_dof_count",
    )
    if physical_count % 6 != 0 or solver_count * 2 != physical_count:
        _fail(
            "fiber_frame_result_boundary_manifest_counts_invalid",
            "/boundary_condition/counts",
            "Boundary manifest must preserve the six-to-three DOF mapping.",
        )
    partitions = _manifest_object(
        manifest["partitions"],
        "/boundary_condition/partitions",
    )
    partition_names = (
        "inactive_physical_dofs",
        "authored_fixed_physical_dofs",
        "constrained_physical_dofs",
        "free_physical_dofs",
        "constrained_solver_dofs",
        "free_solver_dofs",
        "solver_to_physical_global_dofs",
    )
    _exact_keys(
        partitions,
        {*(f"{name}_content_hash" for name in partition_names), "partition_hash"},
        "/boundary_condition/partitions",
    )
    for name, value in partitions.items():
        _require_hash(value, f"/boundary_condition/partitions/{name}")
    if partitions["partition_hash"] != canonical_hash(
        {name: partitions[f"{name}_content_hash"] for name in partition_names}
    ):
        _fail(
            "fiber_frame_result_boundary_manifest_partition_hash_mismatch",
            "/boundary_condition/partitions/partition_hash",
            "Boundary manifest partition hash is stale.",
        )
    _require_canonical_section_hash(
        manifest,
        "receipt_hash",
        "/boundary_condition/receipt_hash",
    )


def _validate_backend_manifest(manifest: Mapping[str, Any]) -> None:
    _validate_simple_receipt_manifest(
        manifest,
        schema_version=FIBER_FRAME_NONLINEAR_RESULT_BACKEND_SCHEMA_VERSION,
        hash_key="receipt_hash",
        claim_boundary=_BACKEND_CLAIM_BOUNDARY,
        required_sections={"bindings", "backend", "observations"},
        path="/backend",
    )
    _validate_exact_hash_object(
        manifest["bindings"],
        {
            "execution_topology_plan_hash",
            "execution_operator_hash",
            "execution_numeric_buffer_hash",
            "solver_config_hash",
            "terminal_receipt_hash",
            "terminal_step_receipt_hash",
            "final_analytic_jacobian_data_hash",
        },
        "/backend/bindings",
    )
    backend = _manifest_object(manifest["backend"], "/backend/backend")
    _exact_keys(
        backend,
        {"role", "matrix_backend", "deterministic_execution"},
        "/backend/backend",
    )
    matrix_backend = backend.get("matrix_backend")
    if (
        matrix_backend not in _BACKEND_ROLE_BY_MATRIX_BACKEND
        or backend.get("role") != _BACKEND_ROLE_BY_MATRIX_BACKEND[matrix_backend]
        or backend.get("deterministic_execution") is not True
    ):
        _fail(
            "fiber_frame_result_backend_manifest_mapping_invalid",
            "/backend/backend",
            "Backend manifest role is inconsistent.",
        )
    observations = _manifest_object(manifest["observations"], "/backend/observations")
    _exact_keys(
        observations,
        {"total_linear_solve_count", "fallback_count", "regularization_count"},
        "/backend/observations",
    )
    _positive_index(
        observations["total_linear_solve_count"],
        "/backend/observations/total_linear_solve_count",
    )
    if (
        type(observations["fallback_count"]) is not int
        or type(observations["regularization_count"]) is not int
        or observations["fallback_count"] != 0
        or observations["regularization_count"] != 0
    ):
        _fail(
            "fiber_frame_result_backend_manifest_fallback_forbidden",
            "/backend/observations",
            "Backend manifest cannot promote fallback or regularized execution.",
        )
    _require_canonical_section_hash(
        manifest,
        "receipt_hash",
        "/backend/receipt_hash",
    )


def _validate_simple_receipt_manifest(
    manifest: Mapping[str, Any],
    *,
    schema_version: str,
    hash_key: str,
    claim_boundary: Mapping[str, bool],
    required_sections: set[str],
    path: str,
) -> None:
    expected_keys = {
        "schema_version",
        hash_key,
        "authority_profile",
        *required_sections,
        "claim_boundary",
        "extensions",
    }
    _exact_keys(manifest, expected_keys, path)
    if (
        manifest["schema_version"] != schema_version
        or manifest["authority_profile"]
        != FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_result_receipt_manifest_profile_invalid",
            path,
            "Unsupported receipt manifest profile.",
        )
    _require_hash(manifest[hash_key], f"{path}/{hash_key}")
    _require_claim_boundary(
        manifest["claim_boundary"], claim_boundary, f"{path}/claim_boundary"
    )
    _require_empty_manifest_extensions(manifest["extensions"], f"{path}/extensions")


def _reduced_payload(
    receipt: FiberFrameNonlinearReducedSystemReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "identity_hash": receipt.identity_hash,
        "authority_profile": receipt.authority_profile,
        "system_profile": receipt.system_profile,
        "storage_profile": FIBER_FRAME_NONLINEAR_RESULT_STORAGE_PROFILE,
        "bindings": {
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "execution_topology_hash": receipt.execution_topology_hash,
            "execution_operator_hash": receipt.execution_operator_hash,
            "solver_coordinate_scaling_hash": receipt.solver_coordinate_scaling_hash,
            "terminal_step_receipt_hash": receipt.terminal_step_receipt_hash,
            "final_analytic_jacobian_data_hash": (
                receipt.final_analytic_jacobian_data_hash
            ),
            "final_analytic_jacobian_content_hash": (
                receipt.final_analytic_jacobian_content_hash
            ),
        },
        "counts": {
            "physical_dof_count": receipt.physical_dof_count,
            "free_count": receipt.free_count,
            "reduced_nnz": receipt.reduced_nnz,
        },
        "array_descriptors": [row.to_dict() for row in receipt.descriptors],
        "claim_boundary": dict(_REDUCED_SYSTEM_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_hash:
        payload.pop("identity_hash")
    return payload


def _residual_payload(
    receipt: FiberFrameNonlinearFullResidualReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "receipt_hash": receipt.receipt_hash,
        "authority_profile": receipt.authority_profile,
        "bindings": {
            "terminal_receipt_hash": receipt.terminal_receipt_hash,
            "terminal_step_receipt_hash": receipt.terminal_step_receipt_hash,
            "physical_residual_trace_hash": receipt.physical_residual_trace_hash,
        },
        "binary_identities": {
            "source_residual_data_hash": receipt.source_residual_data_hash,
            "source_residual_content_hash": receipt.source_residual_content_hash,
            "canonical_si_residual_data_hash": (
                receipt.canonical_si_residual_data_hash
            ),
            "canonical_si_residual_content_hash": (
                receipt.canonical_si_residual_content_hash
            ),
            "scaled_residual_data_hash": receipt.scaled_residual_data_hash,
            "scaled_residual_content_hash": receipt.scaled_residual_content_hash,
        },
        "observations": {
            "raw_translation_linf_n": receipt.raw_translation_linf_n,
            "raw_rotation_linf_nm": receipt.raw_rotation_linf_nm,
            "scaled_residual_linf": receipt.scaled_residual_linf,
            "scaled_residual_tolerance": receipt.scaled_residual_tolerance,
        },
        "gates": {"residual_gate_passed": receipt.residual_gate_passed},
        "claim_boundary": dict(_RESIDUAL_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_hash:
        payload.pop("receipt_hash")
    return payload


def _boundary_payload(
    receipt: FiberFrameNonlinearBoundaryConditionReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "receipt_hash": receipt.receipt_hash,
        "authority_profile": receipt.authority_profile,
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "case_id": receipt.case_id,
            "node_order_hash": receipt.node_order_hash,
        },
        "counts": {
            "physical_dof_count": receipt.physical_dof_count,
            "solver_dof_count": receipt.solver_dof_count,
        },
        "partitions": {
            "inactive_physical_dofs_content_hash": (
                receipt.inactive_physical_dofs_content_hash
            ),
            "authored_fixed_physical_dofs_content_hash": (
                receipt.authored_fixed_physical_dofs_content_hash
            ),
            "constrained_physical_dofs_content_hash": (
                receipt.constrained_physical_dofs_content_hash
            ),
            "free_physical_dofs_content_hash": (
                receipt.free_physical_dofs_content_hash
            ),
            "constrained_solver_dofs_content_hash": (
                receipt.constrained_solver_dofs_content_hash
            ),
            "free_solver_dofs_content_hash": receipt.free_solver_dofs_content_hash,
            "solver_to_physical_global_dofs_content_hash": (
                receipt.solver_to_physical_global_dofs_content_hash
            ),
            "partition_hash": receipt.partition_hash,
        },
        "claim_boundary": dict(_BOUNDARY_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_hash:
        payload.pop("receipt_hash")
    return payload


def _backend_payload(
    receipt: FiberFrameNonlinearBackendReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "receipt_hash": receipt.receipt_hash,
        "authority_profile": receipt.authority_profile,
        "bindings": {
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "execution_operator_hash": receipt.execution_operator_hash,
            "execution_numeric_buffer_hash": receipt.execution_numeric_buffer_hash,
            "solver_config_hash": receipt.solver_config_hash,
            "terminal_receipt_hash": receipt.terminal_receipt_hash,
            "terminal_step_receipt_hash": receipt.terminal_step_receipt_hash,
            "final_analytic_jacobian_data_hash": (
                receipt.final_analytic_jacobian_data_hash
            ),
        },
        "backend": {
            "role": receipt.backend_role,
            "matrix_backend": receipt.matrix_backend,
            "deterministic_execution": receipt.deterministic_execution,
        },
        "observations": {
            "total_linear_solve_count": receipt.total_linear_solve_count,
            "fallback_count": receipt.fallback_count,
            "regularization_count": receipt.regularization_count,
        },
        "claim_boundary": dict(_BACKEND_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_hash:
        payload.pop("receipt_hash")
    return payload


def _source_binding_payload(
    binding: FiberFrameNonlinearResultSourceBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    terminal_bundle = binding._material_chain.projections[-1].bundle
    payload = {
        "schema_version": binding.schema_version,
        "binding_hash": binding.binding_hash,
        "authority_profile": binding.authority_profile,
        "state_ir_usage_profile": binding.state_ir_usage_profile,
        "time_profile": binding.time_profile,
        "source_schema_versions": dict(_SOURCE_SCHEMA_VERSIONS),
        "bindings": {
            "problem_contract_hash": binding.problem_contract_hash,
            "model_ir_content_hash": binding.model_ir_content_hash,
            "case_id": binding.case_id,
            "execution_topology_plan_hash": binding.execution_topology_plan_hash,
            "execution_topology_hash": binding.execution_topology_hash,
            "execution_operator_hash": binding.execution_operator_hash,
            "execution_numeric_buffer_hash": binding.execution_numeric_buffer_hash,
            "solver_coordinate_scaling_hash": binding.solver_coordinate_scaling_hash,
            "physical_equation_scaling_binding_hash": (
                binding.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": binding.engine_equation_scaling_hash,
            "execution_state_binding_hash": binding.execution_state_binding_hash,
            "checkpoint_chain_hash": binding.checkpoint_chain_hash,
            "kinematic_state_chain_hash": binding.kinematic_state_chain_hash,
            "material_state_projection_chain_hash": (
                binding.material_state_projection_chain_hash
            ),
            "terminal_receipt_hash": binding.terminal_receipt_hash,
            "terminal_checkpoint_state_hash": binding.terminal_checkpoint_state_hash,
            "terminal_kinematic_state_hash": binding.terminal_kinematic_state_hash,
            "terminal_material_state_bundle_hash": (
                binding.terminal_material_state_bundle_hash
            ),
            "path_history_hash": binding.path_history_hash,
        },
        "result_bindings": {
            "integration_point_order_hash": (
                terminal_bundle.integration_point_order_hash
            )
        },
        "terminal": {
            "epoch": binding.terminal_epoch,
            "load_factor": binding.terminal_load_factor,
            "accepted_step_count": binding.accepted_step_count,
            "solver_residual_tolerance": binding.solver_residual_tolerance,
            "solver_increment_tolerance_m": binding.solver_increment_tolerance_m,
            "final_solver_coordinate_increment_linf_m": (
                binding.final_solver_coordinate_increment_linf_m
            ),
            "residual_gate_passed": binding.residual_gate_passed,
            "increment_gate_passed": binding.increment_gate_passed,
            "convergence_gate_passed": binding.convergence_gate_passed,
            "physical_dof_count": binding.physical_dof_count,
            "displacement_data_hash": binding.terminal_displacement_data_hash,
            "displacement_content_hash": (binding.terminal_displacement_content_hash),
            "displacement_coordinate_order_hash": (
                binding.terminal_displacement_coordinate_order_hash
            ),
        },
        "receipts": {
            "reduced_system": binding.reduced_system_receipt.to_manifest(),
            "full_residual": binding.full_residual_receipt.to_manifest(),
            "boundary_condition": binding.boundary_condition_receipt.to_manifest(),
            "backend": binding.backend_receipt.to_manifest(),
        },
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY),
        "extensions": dict(binding.extensions),
    }
    if not include_hash:
        payload.pop("binding_hash")
    return payload


def _adapter_payload(
    adapter: FiberFrameNonlinearNumericalResultAdapter,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": adapter.schema_version,
        "adapter_hash": adapter.adapter_hash,
        "authority_profile": adapter.authority_profile,
        "source_binding": adapter.source_binding.to_manifest(),
        "numerical_result": adapter.numerical_result.to_manifest(),
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY),
        "extensions": dict(adapter.extensions),
    }
    if not include_hash:
        payload.pop("adapter_hash")
    return payload


def _reduced_system_arrays(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
) -> Mapping[str, np.ndarray]:
    free_physical = np.asarray(plan.array("free_physical_dofs"), dtype=np.int64)
    free_solver = np.asarray(plan.array("free_solver_dofs"), dtype=np.int64)
    if free_physical.size < 1 or free_physical.size != free_solver.size:
        _fail(
            "fiber_frame_result_free_equation_space_invalid",
            "/reduced_system",
            "A nonempty one-to-one physical/solver free-equation space is required.",
        )
    solver_to_physical = np.asarray(
        plan.array("solver_to_physical_global_dofs"),
        dtype=np.int64,
    )
    if not np.array_equal(solver_to_physical[free_solver], free_physical):
        _fail(
            "fiber_frame_result_free_equation_mapping_invalid",
            "/reduced_system",
            "Free solver and physical equation orders do not map exactly.",
        )
    full_row_ptr = np.asarray(plan.array("csr_row_ptr"), dtype=np.int64)
    full_columns = np.asarray(plan.array("csr_column_indices"), dtype=np.int64)
    global_to_reduced = np.full(plan.physical_dof_count, -1, dtype=np.int64)
    global_to_reduced[free_physical] = np.arange(free_physical.size, dtype=np.int64)
    reduced_row_ptr = [0]
    reduced_columns: list[int] = []
    for global_row in free_physical:
        start = int(full_row_ptr[global_row])
        stop = int(full_row_ptr[global_row + 1])
        for global_column in full_columns[start:stop]:
            local_column = int(global_to_reduced[global_column])
            if local_column >= 0:
                reduced_columns.append(local_column)
        reduced_row_ptr.append(len(reduced_columns))
    return MappingProxyType(
        {
            "free_physical_dofs": immutable_array(free_physical, dtype="<i4"),
            "free_solver_dofs": immutable_array(free_solver, dtype="<i4"),
            "free_csr_row_ptr": immutable_array(reduced_row_ptr, dtype="<i8"),
            "free_csr_column_indices": immutable_array(
                reduced_columns,
                dtype="<i4",
            ),
        }
    )


def _array_descriptor(
    name: str,
    array: np.ndarray,
) -> FiberFrameNonlinearResultArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
        "data_hash": array_data_hash(array),
    }
    return FiberFrameNonlinearResultArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=metadata["data_hash"],
        content_hash=canonical_hash(metadata),
    )


def _validate_array_map(
    arrays: Mapping[str, np.ndarray],
    descriptors: tuple[FiberFrameNonlinearResultArrayDescriptor, ...],
    expected_names: tuple[str, ...],
) -> None:
    if not isinstance(arrays, MappingProxyType) or tuple(arrays) != expected_names:
        _fail(
            "fiber_frame_result_array_map_invalid",
            "/array_descriptors",
            "Retained array map is mutable, incomplete, or reordered.",
        )
    if (
        type(descriptors) is not tuple
        or tuple(row.name for row in descriptors) != expected_names
    ):
        _fail(
            "fiber_frame_result_array_descriptor_set_invalid",
            "/array_descriptors",
            "Array descriptor set or order changed.",
        )
    for descriptor in descriptors:
        array = arrays[descriptor.name]
        if not has_immutable_bytes_backing(array):
            _fail(
                "fiber_frame_result_array_mutable",
                f"/array_descriptors/{descriptor.name}",
                "Retained arrays require immutable bytes backing.",
            )
        if descriptor != _array_descriptor(descriptor.name, array):
            _fail(
                "fiber_frame_result_array_descriptor_mismatch",
                f"/array_descriptors/{descriptor.name}",
                "Array descriptor does not match retained bytes.",
            )


def _descriptor_by_name(descriptors: Any, name: str) -> Any:
    for descriptor in descriptors:
        if descriptor.name == name:
            return descriptor
    _fail(
        "fiber_frame_result_source_descriptor_missing",
        f"/array_descriptors/{name}",
        "Required source descriptor is missing.",
    )


def _strict_json_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "fiber_frame_result_manifest_type_invalid",
            path,
            "Manifest value must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameNonlinearResultAdapterError(
            "fiber_frame_result_manifest_json_invalid",
            path,
            "Manifest must be finite strict JSON.",
        ) from exc
    if type(normalized) is not dict:
        _fail(
            "fiber_frame_result_manifest_type_invalid",
            path,
            "Manifest value must be an object.",
        )
    return normalized


def _manifest_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(
            "fiber_frame_result_manifest_object_invalid",
            path,
            "Expected a JSON object.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            "fiber_frame_result_manifest_keys_invalid",
            path,
            f"Expected exact keys {sorted(expected)}; got {sorted(actual)}.",
        )


def _validate_exact_hash_object(value: Any, expected: set[str], path: str) -> None:
    normalized = _manifest_object(value, path)
    _exact_keys(normalized, expected, path)
    for name, item in normalized.items():
        _require_hash(item, f"{path}/{name}")


def _require_canonical_section_hash(
    manifest: Mapping[str, Any],
    hash_key: str,
    path: str,
) -> None:
    expected = canonical_hash(
        {key: value for key, value in manifest.items() if key != hash_key}
    )
    if manifest[hash_key] != expected:
        _fail(
            "fiber_frame_result_receipt_manifest_hash_mismatch",
            path,
            "Receipt manifest hash is stale.",
        )


def _require_claim_boundary(
    value: Any,
    expected: Mapping[str, bool],
    path: str,
) -> None:
    if type(value) is not dict or value != dict(expected):
        _fail(
            "fiber_frame_result_claim_boundary_invalid",
            path,
            "Authority claim boundary changed.",
        )


def _require_empty_extensions(value: Any) -> None:
    if not isinstance(value, MappingProxyType) or value:
        _fail(
            "fiber_frame_result_extensions_invalid",
            "/extensions",
            "In-memory extensions must be immutable and empty.",
        )


def _require_empty_manifest_extensions(value: Any, path: str) -> None:
    if type(value) is not dict or value:
        _fail(
            "fiber_frame_result_manifest_extensions_invalid",
            path,
            "Manifest extensions must be empty.",
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_result_hash_invalid",
            path,
            "Expected lowercase sha256:<64 hex>.",
        )
    return value


def _stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_result_stable_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return value


def _positive_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 1 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_result_positive_index_invalid",
            path,
            "Expected a positive 32-bit integer.",
        )
    return value


def _finite_float(value: Any, path: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        _fail(
            "fiber_frame_result_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_result_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _positive_float(value: Any, path: str) -> float:
    normalized = _finite_float(value, path)
    if normalized <= 0.0:
        _fail(
            "fiber_frame_result_number_not_positive",
            path,
            "Expected a positive number.",
        )
    return normalized


def _nonnegative_float(value: Any, path: str) -> float:
    normalized = _finite_float(value, path)
    if normalized < 0.0:
        _fail(
            "fiber_frame_result_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearResultAdapterError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_RESULT_ADAPTER_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESULT_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_RESULT_BACKEND_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESULT_BOUNDARY_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESULT_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_RESULT_REDUCED_SYSTEM_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESULT_RESIDUAL_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESULT_SOURCE_BINDING_SCHEMA_VERSION",
    "FiberFrameNonlinearBackendReceipt",
    "FiberFrameNonlinearBoundaryConditionReceipt",
    "FiberFrameNonlinearFullResidualReceipt",
    "FiberFrameNonlinearNumericalResultAdapter",
    "FiberFrameNonlinearReducedSystemReceipt",
    "FiberFrameNonlinearResultAdapterError",
    "FiberFrameNonlinearResultArrayDescriptor",
    "FiberFrameNonlinearResultSourceBinding",
    "create_fiber_frame_nonlinear_numerical_result_adapter",
    "validate_fiber_frame_nonlinear_backend_receipt",
    "validate_fiber_frame_nonlinear_boundary_condition_receipt",
    "validate_fiber_frame_nonlinear_full_residual_receipt",
    "validate_fiber_frame_nonlinear_numerical_result_adapter",
    "validate_fiber_frame_nonlinear_reduced_system_receipt",
    "validate_fiber_frame_nonlinear_result_adapter_manifest",
    "validate_fiber_frame_nonlinear_result_source_binding",
    "validate_fiber_frame_nonlinear_result_source_binding_shape",
]
