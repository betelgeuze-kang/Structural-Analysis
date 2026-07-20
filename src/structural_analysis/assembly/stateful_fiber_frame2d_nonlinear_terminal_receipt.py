"""Bind a converged fiber-frame Newton path to the exact J4 state ancestry.

The receipt in this module is deliberately narrower than Engine v2
``NonlinearNumericalResultIR``.  It grants convergence authority only for one
bounded stateful 2D fiber-frame path.  It does not emit ``StateIR v1`` and does
not grant displacement, reaction, member-force, recovery, design, release, or
commercial authority.

Creation and full validation replay the exact load path, re-evaluate every
physical residual through the J2 ``EquationScaling`` binding, and audit every
accepted same-parent Jacobian by centered finite differences.  The manifest
retains scalar gates and canonical binary identities rather than JSON vectors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import re
from types import MappingProxyType
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    StatefulFiberFrame2DCheckpointChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FiberFrameNonlinearExecutionTopologyPlan,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
    FiberFrameNonlinearKinematicStateChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FiberFrameMaterialStateProjectionChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionStateBinding,
    validate_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
    FiberFramePhysicalEquationScalingBinding,
    trace_stateful_fiber_frame2d_physical_residual,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    StatefulFiberFrame2DLoadStepResult,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.benchmark.stateful_fiber_frame2d_diagnostics import (
    finite_difference_stateful_fiber_frame2d_tangent_check,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.solvers.nonlinear.newton import (
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    VECTOR_MATRIX_BACKENDS,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
)


FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-jacobian-audit.v1"
)
FIBER_FRAME_NONLINEAR_TERMINAL_STEP_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-terminal-step-receipt.v1"
)
FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-terminal-receipt.v1"
)
FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE = (
    "bounded_consistent_newton_convergence_only.v1"
)
FIBER_FRAME_NONLINEAR_RESIDUAL_GATE_PROFILE = (
    "equation_scaling_v1_active_scaled_linf.v1"
)
FIBER_FRAME_NONLINEAR_INCREMENT_GATE_PROFILE = "solver_generalized_length_linf_m.v1"
FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_PROFILE = (
    "same_parent_centered_difference_full_free_matrix.v1"
)
FIBER_FRAME_NONLINEAR_TANGENT_DEFINITION = "dF_internal_du_consistent"
FIBER_FRAME_NONLINEAR_TERMINAL_REASON = "converged_residual_and_increment"
FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE = 1.0e-10
FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M = 1.0e-12
FIBER_FRAME_NONLINEAR_JACOBIAN_EPSILON_M = 1.0e-8
FIBER_FRAME_NONLINEAR_JACOBIAN_RELATIVE_TOLERANCE = 5.0e-6
FIBER_FRAME_NONLINEAR_MAX_ITERATIONS_CAP = 100

FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY = MappingProxyType(
    {
        "exact_j4_execution_state_binding_bound": True,
        "physical_equation_scaling_replayed": True,
        "exact_scale_vector_bound": True,
        "deterministic_solver_path_replayed": True,
        "same_parent_consistent_jacobian_audited_each_step": True,
        "raw_force_norms_reported_in_n": True,
        "raw_moment_norms_reported_in_n_m": True,
        "dimensionless_scaled_residual_gate": True,
        "solver_coordinate_increment_gate": True,
        "fallback_count_zero": True,
        "regularization_count_zero": True,
        "bounded_path_convergence_authority": True,
        "manifest_only_source_replay_authority": False,
        "state_ir_v1_emitted": False,
        "nonlinear_numerical_result_authority": False,
        "displacement_result_authority": False,
        "reaction_member_force_or_fiber_recovery_authority": False,
        "general_frame_or_full_building_authority": False,
        "g1_closure": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_SOURCE_SCHEMA_VERSIONS = MappingProxyType(
    {
        "execution_state_binding": (
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION
        ),
        "physical_residual_trace": FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_SCHEMA_VERSION,
    }
)
_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_INDEX = 2**31 - 1


class FiberFrameNonlinearTerminalReceiptError(ValueError):
    """Fail-closed terminal-receipt error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameNonlinearJacobianAuditReceipt:
    schema_version: str
    audit_hash: str
    audit_profile: str
    problem_contract_hash: str
    execution_topology_plan_hash: str
    free_solver_dofs_content_hash: str
    parent_checkpoint_state_hash: str
    target_load_factor: float
    finite_difference_epsilon_m: float
    relative_tolerance: float
    free_coordinate_data_hash: str
    free_coordinate_content_hash: str
    analytic_jacobian_data_hash: str
    analytic_jacobian_content_hash: str
    finite_difference_jacobian_data_hash: str
    finite_difference_jacobian_content_hash: str
    absolute_inf_error_kn_per_m: float
    relative_inf_error: float
    tangent_symmetry_error_kn_per_m: float
    same_committed_parent_checkpoint: bool
    passed: bool
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_jacobian_audit_receipt(self)
        return _audit_payload(self, include_audit_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearTerminalStepReceipt:
    schema_version: str
    step_receipt_hash: str
    authority_profile: str
    execution_state_binding_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    problem_contract_hash: str
    case_id: str
    step_index: int
    epoch: int
    target_load_factor: float
    parent_checkpoint_state_hash: str
    accepted_checkpoint_state_hash: str
    committed_kinematic_state_hash: str
    committed_material_state_bundle_hash: str
    physical_residual_trace_hash: str
    solver_config_hash: str
    source_step_replay_hash: str
    source_solution_data_hash: str
    source_solution_content_hash: str
    source_physical_residual_data_hash: str
    source_physical_residual_content_hash: str
    convergence_history_hash: str
    line_search_history_hash: str
    residual_formula_hash: str
    tangent_definition: str
    globalization: str
    terminal_disposition: str
    terminal_reason: str
    matrix_backend: str
    iteration_count: int
    linear_solve_count: int
    line_search_step_count: int
    fallback_count: int
    regularization_count: int
    raw_translation_l2_n: float
    raw_translation_linf_n: float
    raw_rotation_l2_nm: float
    raw_rotation_linf_nm: float
    scaled_residual_l2: float
    scaled_residual_linf: float
    scaled_residual_tolerance: float
    solver_coordinate_increment_linf_m: float
    solver_coordinate_increment_tolerance_m: float
    dimensionless_increment_linf: float
    dimensionless_increment_tolerance: float
    governing_equation: int
    governing_node_id: str
    governing_dof: str
    residual_gate_passed: bool
    increment_gate_passed: bool
    convergence_gate_passed: bool
    jacobian_audit: FiberFrameNonlinearJacobianAuditReceipt
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_terminal_step_receipt(self)
        return _step_payload(self, include_step_receipt_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearTerminalReceipt:
    schema_version: str
    terminal_receipt_hash: str
    authority_profile: str
    state_ir_usage_profile: str
    problem_contract_hash: str
    model_ir_content_hash: str
    case_id: str
    execution_state_binding_hash: str
    execution_topology_plan_hash: str
    execution_operator_hash: str
    execution_numeric_buffer_hash: str
    solver_coordinate_scaling_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    engine_equation_scaling_source_commitment_hash: str
    physical_equation_order_hash: str
    physical_equation_free_dofs_content_hash: str
    physical_equation_scale_vector_content_hash: str
    checkpoint_chain_hash: str
    kinematic_state_chain_hash: str
    material_state_projection_chain_hash: str
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    terminal_kinematic_state_hash: str
    terminal_material_state_bundle_hash: str
    source_load_path_replay_hash: str
    solver_config_hash: str
    step_receipt_chain_hash: str
    jacobian_audit_chain_hash: str
    residual_formula: str
    residual_formula_hash: str
    tangent_definition: str
    globalization: str
    residual_gate_profile: str
    increment_gate_profile: str
    matrix_backend: str
    solver_residual_tolerance: float
    solver_increment_tolerance_m: float
    solver_max_iterations: int
    solver_line_search_alphas: tuple[float, ...]
    accepted_step_count: int
    terminal_epoch: int
    terminal_load_factor: float
    terminal_reason: str
    converged: bool
    total_iteration_count: int
    total_linear_solve_count: int
    total_line_search_step_count: int
    fallback_count: int
    regularization_count: int
    final_raw_translation_linf_n: float
    final_raw_rotation_linf_nm: float
    final_scaled_residual_linf: float
    final_solver_coordinate_increment_linf_m: float
    terminal_governing_node_id: str
    terminal_governing_dof: str
    step_receipts: tuple[FiberFrameNonlinearTerminalStepReceipt, ...]
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_terminal_receipt_shape(self)
        return _terminal_payload(self, include_terminal_receipt_hash=True)


def create_fiber_frame_nonlinear_terminal_receipt(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
) -> FiberFrameNonlinearTerminalReceipt:
    """Create a bounded convergence receipt after exact source replay."""

    config, source_replay_hash = _validate_and_replay_sources(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
    )
    receipt = _build_terminal_receipt(
        problem,
        topology_plan,
        physical_scaling,
        execution_state_binding,
        load_path,
        config,
        source_replay_hash,
    )
    return validate_fiber_frame_nonlinear_terminal_receipt_shape(receipt)


def validate_fiber_frame_nonlinear_jacobian_audit_receipt(
    receipt: FiberFrameNonlinearJacobianAuditReceipt,
) -> FiberFrameNonlinearJacobianAuditReceipt:
    if type(receipt) is not FiberFrameNonlinearJacobianAuditReceipt:
        _fail("jacobian_audit_type_invalid", "/", "Expected Jacobian audit receipt.")
    if receipt.schema_version != FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_SCHEMA_VERSION:
        _fail("jacobian_audit_schema_invalid", "/schema_version", "Unsupported schema.")
    if receipt.audit_profile != FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_PROFILE:
        _fail(
            "jacobian_audit_profile_invalid",
            "/audit_profile",
            "Unsupported audit profile.",
        )
    for path, value in (
        ("/audit_hash", receipt.audit_hash),
        ("/bindings/problem_contract_hash", receipt.problem_contract_hash),
        (
            "/bindings/execution_topology_plan_hash",
            receipt.execution_topology_plan_hash,
        ),
        (
            "/bindings/free_solver_dofs_content_hash",
            receipt.free_solver_dofs_content_hash,
        ),
        (
            "/bindings/parent_checkpoint_state_hash",
            receipt.parent_checkpoint_state_hash,
        ),
        (
            "/binary_identities/free_coordinate_data_hash",
            receipt.free_coordinate_data_hash,
        ),
        (
            "/binary_identities/free_coordinate_content_hash",
            receipt.free_coordinate_content_hash,
        ),
        (
            "/binary_identities/analytic_jacobian_data_hash",
            receipt.analytic_jacobian_data_hash,
        ),
        (
            "/binary_identities/analytic_jacobian_content_hash",
            receipt.analytic_jacobian_content_hash,
        ),
        (
            "/binary_identities/finite_difference_jacobian_data_hash",
            receipt.finite_difference_jacobian_data_hash,
        ),
        (
            "/binary_identities/finite_difference_jacobian_content_hash",
            receipt.finite_difference_jacobian_content_hash,
        ),
    ):
        _require_hash(value, path)
    _finite(receipt.target_load_factor, "/coordinates/target_load_factor")
    _positive(
        receipt.finite_difference_epsilon_m, "/controls/finite_difference_epsilon_m"
    )
    _positive(receipt.relative_tolerance, "/controls/relative_tolerance")
    _nonnegative(
        receipt.absolute_inf_error_kn_per_m, "/observations/absolute_inf_error_kn_per_m"
    )
    _nonnegative(receipt.relative_inf_error, "/observations/relative_inf_error")
    _nonnegative(
        receipt.tangent_symmetry_error_kn_per_m,
        "/observations/tangent_symmetry_error_kn_per_m",
    )
    if receipt.finite_difference_epsilon_m != FIBER_FRAME_NONLINEAR_JACOBIAN_EPSILON_M:
        _fail(
            "jacobian_audit_control_invalid",
            "/controls/finite_difference_epsilon_m",
            "v1 fixes the finite-difference epsilon.",
        )
    if receipt.relative_tolerance != FIBER_FRAME_NONLINEAR_JACOBIAN_RELATIVE_TOLERANCE:
        _fail(
            "jacobian_audit_control_invalid",
            "/controls/relative_tolerance",
            "v1 fixes the Jacobian tolerance.",
        )
    if (
        type(receipt.same_committed_parent_checkpoint) is not bool
        or not receipt.same_committed_parent_checkpoint
    ):
        _fail(
            "jacobian_audit_parent_gate_failed",
            "/gates/same_committed_parent_checkpoint",
            "The audit must retain one immutable parent.",
        )
    if type(receipt.passed) is not bool or not receipt.passed:
        _fail(
            "jacobian_audit_gate_failed",
            "/gates/passed",
            "The full free-equation Jacobian audit must pass.",
        )
    if receipt.relative_inf_error > receipt.relative_tolerance:
        _fail(
            "jacobian_audit_gate_failed",
            "/observations/relative_inf_error",
            "Jacobian error exceeds tolerance.",
        )
    if receipt.tangent_symmetry_error_kn_per_m > 1.0e-9:
        _fail(
            "jacobian_audit_gate_failed",
            "/observations/tangent_symmetry_error_kn_per_m",
            "Jacobian symmetry gate failed.",
        )
    _require_empty_extensions(receipt.extensions)
    expected = canonical_hash(_audit_payload(receipt, include_audit_hash=False))
    if receipt.audit_hash != expected:
        _fail(
            "jacobian_audit_hash_mismatch",
            "/audit_hash",
            "Audit hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_nonlinear_terminal_step_receipt(
    receipt: FiberFrameNonlinearTerminalStepReceipt,
) -> FiberFrameNonlinearTerminalStepReceipt:
    if type(receipt) is not FiberFrameNonlinearTerminalStepReceipt:
        _fail("terminal_step_type_invalid", "/", "Expected terminal step receipt.")
    if receipt.schema_version != FIBER_FRAME_NONLINEAR_TERMINAL_STEP_SCHEMA_VERSION:
        _fail("terminal_step_schema_invalid", "/schema_version", "Unsupported schema.")
    _require_authority_profile(receipt.authority_profile)
    for path, value in (
        ("/step_receipt_hash", receipt.step_receipt_hash),
        (
            "/bindings/execution_state_binding_hash",
            receipt.execution_state_binding_hash,
        ),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            receipt.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/engine_equation_scaling_hash",
            receipt.engine_equation_scaling_hash,
        ),
        ("/bindings/problem_contract_hash", receipt.problem_contract_hash),
        (
            "/bindings/parent_checkpoint_state_hash",
            receipt.parent_checkpoint_state_hash,
        ),
        (
            "/bindings/accepted_checkpoint_state_hash",
            receipt.accepted_checkpoint_state_hash,
        ),
        (
            "/bindings/committed_kinematic_state_hash",
            receipt.committed_kinematic_state_hash,
        ),
        (
            "/bindings/committed_material_state_bundle_hash",
            receipt.committed_material_state_bundle_hash,
        ),
        (
            "/bindings/physical_residual_trace_hash",
            receipt.physical_residual_trace_hash,
        ),
        ("/bindings/solver_config_hash", receipt.solver_config_hash),
        ("/bindings/source_step_replay_hash", receipt.source_step_replay_hash),
        (
            "/binary_identities/source_solution_data_hash",
            receipt.source_solution_data_hash,
        ),
        (
            "/binary_identities/source_solution_content_hash",
            receipt.source_solution_content_hash,
        ),
        (
            "/binary_identities/source_physical_residual_data_hash",
            receipt.source_physical_residual_data_hash,
        ),
        (
            "/binary_identities/source_physical_residual_content_hash",
            receipt.source_physical_residual_content_hash,
        ),
        ("/bindings/convergence_history_hash", receipt.convergence_history_hash),
        ("/bindings/line_search_history_hash", receipt.line_search_history_hash),
        ("/solver/residual_formula_hash", receipt.residual_formula_hash),
    ):
        _require_hash(value, path)
    _nonempty(receipt.case_id, "/bindings/case_id")
    _positive_index(receipt.step_index, "/coordinates/step_index")
    _positive_index(receipt.epoch, "/coordinates/epoch")
    if receipt.step_index != receipt.epoch:
        _fail(
            "terminal_step_epoch_mismatch",
            "/coordinates",
            "Step index must equal committed epoch.",
        )
    _finite(receipt.target_load_factor, "/coordinates/target_load_factor")
    if receipt.residual_formula_hash != RESIDUAL_FORMULA_HASH:
        _fail(
            "terminal_step_residual_formula_invalid",
            "/solver/residual_formula_hash",
            "Residual formula hash changed.",
        )
    if receipt.tangent_definition != FIBER_FRAME_NONLINEAR_TANGENT_DEFINITION:
        _fail(
            "terminal_step_tangent_invalid",
            "/solver/tangent_definition",
            "A consistent residual Jacobian is required.",
        )
    if receipt.globalization != GLOBALIZATION:
        _fail(
            "terminal_step_globalization_invalid",
            "/solver/globalization",
            "Unsupported globalization.",
        )
    if receipt.terminal_disposition != SOLVE_FREE_EQUATIONS_DISPOSITION:
        _fail(
            "terminal_step_disposition_invalid",
            "/solver/terminal_disposition",
            "J5 requires a solved free-equation space.",
        )
    if receipt.terminal_reason != "residual_and_increment_converged":
        _fail(
            "terminal_step_reason_invalid",
            "/solver/terminal_reason",
            "The source Newton step did not converge.",
        )
    if receipt.matrix_backend not in VECTOR_MATRIX_BACKENDS:
        _fail(
            "terminal_step_backend_invalid",
            "/solver/matrix_backend",
            "Unsupported deterministic CPU backend.",
        )
    for name in (
        "iteration_count",
        "linear_solve_count",
        "line_search_step_count",
        "fallback_count",
        "regularization_count",
    ):
        _index(getattr(receipt, name), f"/solver/{name}")
    if (
        receipt.iteration_count < 1
        or receipt.linear_solve_count != receipt.iteration_count
    ):
        _fail(
            "terminal_step_iteration_count_invalid",
            "/solver",
            "Each converged step requires one linear solve per Newton iteration.",
        )
    if receipt.fallback_count != 0 or receipt.regularization_count != 0:
        _fail(
            "terminal_step_fallback_invalid",
            "/solver",
            "Fallback and regularization counts must remain zero.",
        )
    for name in (
        "raw_translation_l2_n",
        "raw_translation_linf_n",
        "raw_rotation_l2_nm",
        "raw_rotation_linf_nm",
        "scaled_residual_l2",
        "scaled_residual_linf",
        "scaled_residual_tolerance",
        "solver_coordinate_increment_linf_m",
        "solver_coordinate_increment_tolerance_m",
        "dimensionless_increment_linf",
        "dimensionless_increment_tolerance",
    ):
        _nonnegative(getattr(receipt, name), f"/observations/{name}")
    if (
        receipt.scaled_residual_tolerance
        != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
    ):
        _fail(
            "terminal_step_residual_tolerance_invalid",
            "/observations/scaled_residual_tolerance",
            "v1 fixes the scaled residual tolerance.",
        )
    if (
        receipt.solver_coordinate_increment_tolerance_m
        != FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
    ):
        _fail(
            "terminal_step_increment_tolerance_invalid",
            "/observations/solver_coordinate_increment_tolerance_m",
            "v1 fixes the solver-coordinate increment tolerance.",
        )
    _index(receipt.governing_equation, "/observations/governing_equation")
    _nonempty(receipt.governing_node_id, "/observations/governing_node_id")
    _nonempty(receipt.governing_dof, "/observations/governing_dof")
    if any(
        type(value) is not bool or not value
        for value in (
            receipt.residual_gate_passed,
            receipt.increment_gate_passed,
            receipt.convergence_gate_passed,
        )
    ):
        _fail(
            "terminal_step_convergence_gate_failed",
            "/gates",
            "Residual and increment gates must both pass.",
        )
    if receipt.scaled_residual_linf > receipt.scaled_residual_tolerance:
        _fail(
            "terminal_step_convergence_gate_failed",
            "/observations/scaled_residual_linf",
            "Scaled residual exceeds tolerance.",
        )
    if (
        receipt.solver_coordinate_increment_linf_m
        > receipt.solver_coordinate_increment_tolerance_m
    ):
        _fail(
            "terminal_step_convergence_gate_failed",
            "/observations/solver_coordinate_increment_linf_m",
            "Solver-coordinate increment exceeds tolerance.",
        )
    validate_fiber_frame_nonlinear_jacobian_audit_receipt(receipt.jacobian_audit)
    if (
        receipt.jacobian_audit.parent_checkpoint_state_hash
        != receipt.parent_checkpoint_state_hash
        or receipt.jacobian_audit.target_load_factor != receipt.target_load_factor
    ):
        _fail(
            "terminal_step_jacobian_binding_mismatch",
            "/jacobian_audit",
            "Jacobian audit does not bind the step parent and load.",
        )
    _require_empty_extensions(receipt.extensions)
    expected = canonical_hash(_step_payload(receipt, include_step_receipt_hash=False))
    if receipt.step_receipt_hash != expected:
        _fail(
            "terminal_step_hash_mismatch",
            "/step_receipt_hash",
            "Step hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_nonlinear_terminal_receipt_shape(
    receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearTerminalReceipt:
    """Validate self-contained metadata; source replay requires the full validator."""

    if type(receipt) is not FiberFrameNonlinearTerminalReceipt:
        _fail("terminal_receipt_type_invalid", "/", "Expected terminal receipt.")
    if receipt.schema_version != FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION:
        _fail(
            "terminal_receipt_schema_invalid", "/schema_version", "Unsupported schema."
        )
    _require_authority_profile(receipt.authority_profile)
    if receipt.state_ir_usage_profile != FIBER_FRAME_STATE_IR_USAGE_PROFILE:
        _fail(
            "terminal_receipt_state_ir_profile_invalid",
            "/state_ir_usage_profile",
            "StateIR v1 cannot be promoted for this nonlinear state.",
        )
    hash_fields = (
        "terminal_receipt_hash",
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_state_binding_hash",
        "execution_topology_plan_hash",
        "execution_operator_hash",
        "execution_numeric_buffer_hash",
        "solver_coordinate_scaling_hash",
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "engine_equation_scaling_source_commitment_hash",
        "physical_equation_order_hash",
        "physical_equation_free_dofs_content_hash",
        "physical_equation_scale_vector_content_hash",
        "checkpoint_chain_hash",
        "kinematic_state_chain_hash",
        "material_state_projection_chain_hash",
        "root_checkpoint_state_hash",
        "terminal_checkpoint_state_hash",
        "terminal_kinematic_state_hash",
        "terminal_material_state_bundle_hash",
        "source_load_path_replay_hash",
        "solver_config_hash",
        "step_receipt_chain_hash",
        "jacobian_audit_chain_hash",
        "residual_formula_hash",
    )
    for name in hash_fields:
        _require_hash(getattr(receipt, name), f"/bindings/{name}")
    _nonempty(receipt.case_id, "/bindings/case_id")
    if (
        receipt.residual_formula != RESIDUAL_FORMULA
        or receipt.residual_formula_hash != RESIDUAL_FORMULA_HASH
    ):
        _fail(
            "terminal_receipt_residual_formula_invalid",
            "/solver/residual_formula",
            "Residual formula changed.",
        )
    if (
        receipt.tangent_definition != FIBER_FRAME_NONLINEAR_TANGENT_DEFINITION
        or receipt.globalization != GLOBALIZATION
    ):
        _fail(
            "terminal_receipt_solver_profile_invalid",
            "/solver",
            "Consistent Newton with the fixed globalization is required.",
        )
    if (
        receipt.residual_gate_profile != FIBER_FRAME_NONLINEAR_RESIDUAL_GATE_PROFILE
        or receipt.increment_gate_profile
        != FIBER_FRAME_NONLINEAR_INCREMENT_GATE_PROFILE
    ):
        _fail(
            "terminal_receipt_gate_profile_invalid",
            "/solver",
            "Unsupported convergence gate profile.",
        )
    if receipt.matrix_backend not in VECTOR_MATRIX_BACKENDS:
        _fail(
            "terminal_receipt_backend_invalid",
            "/solver/matrix_backend",
            "Unsupported deterministic CPU backend.",
        )
    if (
        receipt.solver_residual_tolerance
        != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
        or receipt.solver_increment_tolerance_m
        != FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
    ):
        _fail(
            "terminal_receipt_tolerance_invalid",
            "/solver",
            "v1 fixes residual and increment tolerances.",
        )
    max_iterations = _positive_index(
        receipt.solver_max_iterations, "/solver/max_iterations"
    )
    if max_iterations > FIBER_FRAME_NONLINEAR_MAX_ITERATIONS_CAP:
        _fail(
            "terminal_receipt_iteration_cap_exceeded",
            "/solver/max_iterations",
            "Solver iteration cap exceeds the v1 bound.",
        )
    _validate_line_search_alphas(receipt.solver_line_search_alphas)
    expected_config_hash = canonical_hash(_solver_config_payload(receipt))
    if receipt.solver_config_hash != expected_config_hash:
        _fail(
            "terminal_receipt_solver_config_hash_mismatch",
            "/bindings/solver_config_hash",
            "Solver config hash is stale.",
        )
    count = _positive_index(
        receipt.accepted_step_count, "/terminal/accepted_step_count"
    )
    if type(receipt.step_receipts) is not tuple or len(receipt.step_receipts) != count:
        _fail(
            "terminal_receipt_step_set_invalid",
            "/step_receipts",
            "Step receipt count is inconsistent.",
        )
    previous_hash = receipt.root_checkpoint_state_hash
    previous_load = 0.0
    for index, row in enumerate(receipt.step_receipts, start=1):
        validate_fiber_frame_nonlinear_terminal_step_receipt(row)
        if row.step_index != index or row.epoch != index:
            _fail(
                "terminal_receipt_step_position_invalid",
                f"/step_receipts/{index - 1}",
                "Steps must be contiguous from one.",
            )
        if row.parent_checkpoint_state_hash != previous_hash:
            _fail(
                "terminal_receipt_step_ancestry_invalid",
                f"/step_receipts/{index - 1}/bindings",
                "Step checkpoint ancestry is broken.",
            )
        if row.target_load_factor <= previous_load:
            _fail(
                "terminal_receipt_load_path_invalid",
                f"/step_receipts/{index - 1}/coordinates/target_load_factor",
                "Accepted load factors must increase strictly.",
            )
        for name, expected in (
            ("authority_profile", receipt.authority_profile),
            ("execution_state_binding_hash", receipt.execution_state_binding_hash),
            (
                "physical_equation_scaling_binding_hash",
                receipt.physical_equation_scaling_binding_hash,
            ),
            ("engine_equation_scaling_hash", receipt.engine_equation_scaling_hash),
            ("problem_contract_hash", receipt.problem_contract_hash),
            ("case_id", receipt.case_id),
            ("solver_config_hash", receipt.solver_config_hash),
            ("matrix_backend", receipt.matrix_backend),
        ):
            if getattr(row, name) != expected:
                _fail(
                    "terminal_receipt_step_source_mismatch",
                    f"/step_receipts/{index - 1}/{name}",
                    "Step source identity differs from the terminal receipt.",
                )
        previous_hash = row.accepted_checkpoint_state_hash
        previous_load = row.target_load_factor
    last = receipt.step_receipts[-1]
    if (
        receipt.terminal_epoch != count
        or receipt.terminal_checkpoint_state_hash != last.accepted_checkpoint_state_hash
        or receipt.terminal_kinematic_state_hash != last.committed_kinematic_state_hash
        or receipt.terminal_material_state_bundle_hash
        != last.committed_material_state_bundle_hash
    ):
        _fail(
            "terminal_receipt_terminal_binding_mismatch",
            "/terminal",
            "Terminal state does not equal the last accepted step.",
        )
    if receipt.terminal_load_factor != 1.0 or last.target_load_factor != 1.0:
        _fail(
            "terminal_receipt_full_load_required",
            "/terminal/terminal_load_factor",
            "The bounded v1 terminal requires exact load factor 1.0.",
        )
    if (
        receipt.terminal_reason != FIBER_FRAME_NONLINEAR_TERMINAL_REASON
        or type(receipt.converged) is not bool
        or not receipt.converged
    ):
        _fail(
            "terminal_receipt_convergence_invalid",
            "/terminal",
            "Only residual-and-increment convergence may mint this receipt.",
        )
    for name in (
        "total_iteration_count",
        "total_linear_solve_count",
        "total_line_search_step_count",
        "fallback_count",
        "regularization_count",
    ):
        _index(getattr(receipt, name), f"/terminal/{name}")
    if receipt.fallback_count != 0 or receipt.regularization_count != 0:
        _fail(
            "terminal_receipt_fallback_invalid",
            "/terminal",
            "Fallback and regularization counts must remain zero.",
        )
    expected_totals = (
        sum(row.iteration_count for row in receipt.step_receipts),
        sum(row.linear_solve_count for row in receipt.step_receipts),
        sum(row.line_search_step_count for row in receipt.step_receipts),
    )
    if (
        receipt.total_iteration_count,
        receipt.total_linear_solve_count,
        receipt.total_line_search_step_count,
    ) != expected_totals:
        _fail(
            "terminal_receipt_totals_invalid",
            "/terminal",
            "Aggregate solver counts are stale.",
        )
    for name in (
        "final_raw_translation_linf_n",
        "final_raw_rotation_linf_nm",
        "final_scaled_residual_linf",
        "final_solver_coordinate_increment_linf_m",
    ):
        _nonnegative(getattr(receipt, name), f"/terminal/{name}")
    if (
        receipt.final_raw_translation_linf_n != last.raw_translation_linf_n
        or receipt.final_raw_rotation_linf_nm != last.raw_rotation_linf_nm
        or receipt.final_scaled_residual_linf != last.scaled_residual_linf
        or receipt.final_solver_coordinate_increment_linf_m
        != last.solver_coordinate_increment_linf_m
        or receipt.terminal_governing_node_id != last.governing_node_id
        or receipt.terminal_governing_dof != last.governing_dof
    ):
        _fail(
            "terminal_receipt_final_observation_mismatch",
            "/terminal",
            "Final observations differ from the last step.",
        )
    expected_step_chain = canonical_hash(
        {
            "root_checkpoint_state_hash": receipt.root_checkpoint_state_hash,
            "step_receipt_hashes": [
                row.step_receipt_hash for row in receipt.step_receipts
            ],
        }
    )
    expected_audit_chain = canonical_hash(
        {
            "jacobian_audit_hashes": [
                row.jacobian_audit.audit_hash for row in receipt.step_receipts
            ]
        }
    )
    if (
        receipt.step_receipt_chain_hash != expected_step_chain
        or receipt.jacobian_audit_chain_hash != expected_audit_chain
    ):
        _fail(
            "terminal_receipt_chain_hash_mismatch",
            "/bindings",
            "Step or Jacobian audit chain hash is stale.",
        )
    _require_empty_extensions(receipt.extensions)
    expected_hash = canonical_hash(
        _terminal_payload(receipt, include_terminal_receipt_hash=False)
    )
    if receipt.terminal_receipt_hash != expected_hash:
        _fail(
            "terminal_receipt_hash_mismatch",
            "/terminal_receipt_hash",
            "Terminal receipt hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_nonlinear_terminal_receipt(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    receipt: FiberFrameNonlinearTerminalReceipt,
) -> FiberFrameNonlinearTerminalReceipt:
    """Replay every source and require byte-identical terminal metadata."""

    config, source_replay_hash = _validate_and_replay_sources(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
    )
    validate_fiber_frame_nonlinear_terminal_receipt_shape(receipt)
    expected = _build_terminal_receipt(
        problem,
        topology_plan,
        physical_scaling,
        execution_state_binding,
        load_path,
        config,
        source_replay_hash,
    )
    if receipt != expected:
        _fail(
            "terminal_receipt_source_replay_mismatch",
            "/",
            "Receipt differs from replayed J4/Newton sources.",
        )
    return receipt


def validate_fiber_frame_nonlinear_terminal_receipt_manifest(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate manifest integrity without granting source-replay authority."""

    manifest = _manifest_object(value, "/")
    receipt = _terminal_from_manifest(manifest)
    validate_fiber_frame_nonlinear_terminal_receipt_shape(receipt)
    return receipt.to_manifest()


def _validate_and_replay_sources(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
) -> tuple[NewtonRaphsonConfig, str]:
    validate_fiber_frame_nonlinear_execution_state_binding(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
    )
    if type(load_path) is not StatefulFiberFrame2DLoadPathResult:
        _fail(
            "terminal_source_path_type_invalid",
            "/load_path",
            "Expected exact load-path result.",
        )
    if load_path.status != "ready" or load_path.contract_pass is not True:
        _fail(
            "terminal_source_path_not_converged",
            "/load_path",
            "Only a fully committed path may mint a terminal receipt.",
        )
    if (
        len(load_path.steps) < 2
        or len(load_path.steps) + 1 != execution_state_binding.epoch_count
    ):
        _fail(
            "terminal_source_path_count_invalid",
            "/load_path/steps",
            "Path steps must cover every non-genesis J4 epoch.",
        )
    if (
        load_path.initial_checkpoint.state_hash
        != checkpoint_chain.root_checkpoint.state_hash
        or load_path.final_checkpoint.state_hash
        != checkpoint_chain.terminal_checkpoint.state_hash
    ):
        _fail(
            "terminal_source_path_checkpoint_mismatch",
            "/load_path",
            "Path endpoints differ from the J4 checkpoint chain.",
        )
    if (
        tuple(
            (
                load_path.initial_checkpoint,
                *(step.accepted_checkpoint for step in load_path.steps),
            )
        )
        != checkpoint_chain.checkpoints
    ):
        _fail(
            "terminal_source_path_checkpoint_mismatch",
            "/load_path/steps",
            "Accepted checkpoints differ from the J4 chain.",
        )
    factors = tuple(step.metrics.get("target_load_factor") for step in load_path.steps)
    if any(type(value) is not float or not math.isfinite(value) for value in factors):
        _fail(
            "terminal_source_path_load_invalid",
            "/load_path/steps",
            "Load factors must be finite floats.",
        )
    if factors[-1] != 1.0 or any(
        current <= previous
        for previous, current in zip((0.0, *factors[:-1]), factors, strict=True)
    ):
        _fail(
            "terminal_source_path_load_invalid",
            "/load_path/steps",
            "Path must increase strictly to exact load factor 1.0.",
        )
    first_solution = load_path.steps[0].trial_solution
    if (
        type(first_solution) is not NewtonRaphsonVectorSolution
        or type(first_solution.config) is not NewtonRaphsonConfig
    ):
        _fail(
            "terminal_source_solution_type_invalid",
            "/load_path/steps/0/trial_solution",
            "Expected exact vector Newton solution.",
        )
    config = first_solution.config
    _validate_source_config(config)
    for index, (step, checkpoint, binding_row) in enumerate(
        zip(
            load_path.steps,
            checkpoint_chain.checkpoints[1:],
            execution_state_binding.epoch_bindings[1:],
            strict=True,
        )
    ):
        if (
            type(step) is not StatefulFiberFrame2DLoadStepResult
            or type(step.trial_solution) is not NewtonRaphsonVectorSolution
        ):
            _fail(
                "terminal_source_step_type_invalid",
                f"/load_path/steps/{index}",
                "Expected exact load-step and vector-solution types.",
            )
        if step.trial_solution.config != config:
            _fail(
                "terminal_source_config_changed",
                f"/load_path/steps/{index}/trial_solution/config",
                "Every path step must share one solver config.",
            )
        if (
            step.accepted_checkpoint.state_hash != checkpoint.state_hash
            or step.accepted_checkpoint.state_hash != binding_row.checkpoint_state_hash
        ):
            _fail(
                "terminal_source_step_state_mismatch",
                f"/load_path/steps/{index}",
                "Accepted step does not match the J4 epoch.",
            )
    source_hash = canonical_hash(load_path.to_dict())
    replayed = run_stateful_fiber_frame2d_load_path(
        problem,
        factors,
        initial_checkpoint=load_path.initial_checkpoint,
        config=config,
    )
    replay_hash = canonical_hash(replayed.to_dict())
    if replay_hash != source_hash:
        _fail(
            "terminal_source_path_replay_mismatch",
            "/load_path",
            "Deterministic Newton replay differs from the supplied path.",
        )
    return config, source_hash


def _validate_source_config(config: NewtonRaphsonConfig) -> None:
    if config.residual_tolerance != FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE:
        _fail(
            "terminal_source_residual_tolerance_invalid",
            "/load_path/config/residual_tolerance",
            "J5 v1 requires the fixed residual tolerance.",
        )
    if config.increment_tolerance != FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M:
        _fail(
            "terminal_source_increment_tolerance_invalid",
            "/load_path/config/increment_tolerance",
            "J5 v1 requires the fixed increment tolerance.",
        )
    if (
        config.max_iterations < 1
        or config.max_iterations > FIBER_FRAME_NONLINEAR_MAX_ITERATIONS_CAP
    ):
        _fail(
            "terminal_source_iteration_cap_invalid",
            "/load_path/config/max_iterations",
            "Iteration cap is outside the bounded v1 policy.",
        )
    if config.matrix_backend not in VECTOR_MATRIX_BACKENDS:
        _fail(
            "terminal_source_backend_invalid",
            "/load_path/config/matrix_backend",
            "Unsupported deterministic CPU backend.",
        )
    _validate_line_search_alphas(config.line_search_alphas)


def _build_terminal_receipt(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    config: NewtonRaphsonConfig,
    source_replay_hash: str,
) -> FiberFrameNonlinearTerminalReceipt:
    config_hash = canonical_hash(_config_payload_from_config(config))
    rows = tuple(
        _build_step_receipt(
            problem,
            topology_plan,
            physical_scaling,
            execution_state_binding,
            step,
            index,
            config_hash,
        )
        for index, step in enumerate(load_path.steps, start=1)
    )
    last = rows[-1]
    step_chain_hash = canonical_hash(
        {
            "root_checkpoint_state_hash": execution_state_binding.root_checkpoint_state_hash,
            "step_receipt_hashes": [row.step_receipt_hash for row in rows],
        }
    )
    audit_chain_hash = canonical_hash(
        {"jacobian_audit_hashes": [row.jacobian_audit.audit_hash for row in rows]}
    )
    provisional = FiberFrameNonlinearTerminalReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION,
        terminal_receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE,
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        problem_contract_hash=execution_state_binding.problem_contract_hash,
        model_ir_content_hash=execution_state_binding.model_ir_content_hash,
        case_id=execution_state_binding.case_id,
        execution_state_binding_hash=execution_state_binding.binding_hash,
        execution_topology_plan_hash=execution_state_binding.execution_topology_plan_hash,
        execution_operator_hash=execution_state_binding.execution_operator_hash,
        execution_numeric_buffer_hash=execution_state_binding.execution_numeric_buffer_hash,
        solver_coordinate_scaling_hash=execution_state_binding.solver_coordinate_scaling_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=physical_scaling.engine_equation_scaling_hash,
        engine_equation_scaling_source_commitment_hash=physical_scaling.engine_source_commitment_hash,
        physical_equation_order_hash=physical_scaling.equation_order_hash,
        physical_equation_free_dofs_content_hash=execution_state_binding.physical_equation_free_dofs_content_hash,
        physical_equation_scale_vector_content_hash=execution_state_binding.physical_equation_scale_vector_content_hash,
        checkpoint_chain_hash=execution_state_binding.checkpoint_chain_hash,
        kinematic_state_chain_hash=execution_state_binding.kinematic_state_chain_hash,
        material_state_projection_chain_hash=execution_state_binding.material_state_projection_chain_hash,
        root_checkpoint_state_hash=execution_state_binding.root_checkpoint_state_hash,
        terminal_checkpoint_state_hash=execution_state_binding.terminal_checkpoint_state_hash,
        terminal_kinematic_state_hash=execution_state_binding.terminal_kinematic_state_hash,
        terminal_material_state_bundle_hash=execution_state_binding.terminal_material_state_bundle_hash,
        source_load_path_replay_hash=source_replay_hash,
        solver_config_hash=config_hash,
        step_receipt_chain_hash=step_chain_hash,
        jacobian_audit_chain_hash=audit_chain_hash,
        residual_formula=RESIDUAL_FORMULA,
        residual_formula_hash=RESIDUAL_FORMULA_HASH,
        tangent_definition=FIBER_FRAME_NONLINEAR_TANGENT_DEFINITION,
        globalization=GLOBALIZATION,
        residual_gate_profile=FIBER_FRAME_NONLINEAR_RESIDUAL_GATE_PROFILE,
        increment_gate_profile=FIBER_FRAME_NONLINEAR_INCREMENT_GATE_PROFILE,
        matrix_backend=config.matrix_backend,
        solver_residual_tolerance=config.residual_tolerance,
        solver_increment_tolerance_m=config.increment_tolerance,
        solver_max_iterations=config.max_iterations,
        solver_line_search_alphas=config.line_search_alphas,
        accepted_step_count=len(rows),
        terminal_epoch=last.epoch,
        terminal_load_factor=last.target_load_factor,
        terminal_reason=FIBER_FRAME_NONLINEAR_TERMINAL_REASON,
        converged=True,
        total_iteration_count=sum(row.iteration_count for row in rows),
        total_linear_solve_count=sum(row.linear_solve_count for row in rows),
        total_line_search_step_count=sum(row.line_search_step_count for row in rows),
        fallback_count=sum(row.fallback_count for row in rows),
        regularization_count=sum(row.regularization_count for row in rows),
        final_raw_translation_linf_n=last.raw_translation_linf_n,
        final_raw_rotation_linf_nm=last.raw_rotation_linf_nm,
        final_scaled_residual_linf=last.scaled_residual_linf,
        final_solver_coordinate_increment_linf_m=last.solver_coordinate_increment_linf_m,
        terminal_governing_node_id=last.governing_node_id,
        terminal_governing_dof=last.governing_dof,
        step_receipts=rows,
        extensions=MappingProxyType({}),
    )
    result = replace(
        provisional,
        terminal_receipt_hash=canonical_hash(
            _terminal_payload(provisional, include_terminal_receipt_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_terminal_receipt_shape(result)


def _build_step_receipt(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    step: StatefulFiberFrame2DLoadStepResult,
    step_index: int,
    config_hash: str,
) -> FiberFrameNonlinearTerminalStepReceipt:
    solution = step.trial_solution
    assembly = step.trial_assembly
    metrics = solution.metrics
    epoch_binding = execution_state_binding.epoch_bindings[step_index]
    if not _step_solver_contract_passes(step):
        _fail(
            "terminal_source_step_not_converged",
            f"/load_path/steps/{step_index - 1}",
            "Source Newton step does not satisfy the strict contract.",
        )
    if not np.array_equal(
        solution.free_displacements_m,
        assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
    ):
        _fail(
            "terminal_source_solution_assembly_mismatch",
            f"/load_path/steps/{step_index - 1}",
            "Solution coordinates differ from the final assembly.",
        )
    if not np.array_equal(
        np.asarray(step.accepted_checkpoint.global_displacements),
        assembly.global_displacements,
    ):
        _fail(
            "terminal_source_solution_checkpoint_mismatch",
            f"/load_path/steps/{step_index - 1}",
            "Final assembly differs from the committed checkpoint.",
        )
    if tuple(state.state_hash for state in assembly.trial_element_states) != tuple(
        state.state_hash for state in step.accepted_checkpoint.element_states
    ):
        _fail(
            "terminal_source_material_checkpoint_mismatch",
            f"/load_path/steps/{step_index - 1}",
            "Trial element states differ from the committed checkpoint.",
        )
    if epoch_binding.checkpoint_state_hash != step.accepted_checkpoint.state_hash:
        _fail(
            "terminal_source_j4_epoch_mismatch",
            f"/load_path/steps/{step_index - 1}",
            "Accepted checkpoint differs from J4.",
        )
    source_residual = immutable_array(
        assembly.internal_loads_global - assembly.external_loads_global,
        dtype="<f8",
    )
    trace = trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=topology_plan,
        scaling_binding=physical_scaling,
        raw_residual_source_3dof=source_residual,
    )
    increment = float(metrics["final_increment_abs_m"])
    scaled_increment = increment / physical_scaling.characteristic_length_m
    scaled_increment_tolerance = (
        FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
        / physical_scaling.characteristic_length_m
    )
    residual_gate = trace.scaled_linf <= FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE
    increment_gate = increment <= FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M
    if not residual_gate or not increment_gate:
        _fail(
            "terminal_physical_convergence_gate_failed",
            f"/load_path/steps/{step_index - 1}",
            "J2-scaled residual or solver-coordinate increment gate failed.",
        )
    solution_array = immutable_array(solution.free_displacements_m, dtype="<f8")
    free_order_hash = _descriptor_content_hash(topology_plan, "free_solver_dofs")
    solution_metadata = _array_metadata(solution_array, free_order_hash)
    residual_metadata = _array_metadata(
        source_residual, _solver_equation_order_hash(topology_plan)
    )
    audit = _build_jacobian_audit(
        problem,
        topology_plan,
        step,
        free_order_hash,
    )
    provisional = FiberFrameNonlinearTerminalStepReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_TERMINAL_STEP_SCHEMA_VERSION,
        step_receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE,
        execution_state_binding_hash=execution_state_binding.binding_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=physical_scaling.engine_equation_scaling_hash,
        problem_contract_hash=problem.contract_hash,
        case_id=problem.case_id,
        step_index=step_index,
        epoch=step.accepted_checkpoint.epoch,
        target_load_factor=step.accepted_checkpoint.load_factor,
        parent_checkpoint_state_hash=step.parent_checkpoint.state_hash,
        accepted_checkpoint_state_hash=step.accepted_checkpoint.state_hash,
        committed_kinematic_state_hash=epoch_binding.committed_kinematic_state_hash,
        committed_material_state_bundle_hash=epoch_binding.committed_material_state_bundle_hash,
        physical_residual_trace_hash=trace.trace_hash,
        solver_config_hash=config_hash,
        source_step_replay_hash=canonical_hash(step.to_dict()),
        source_solution_data_hash=array_data_hash(solution_array),
        source_solution_content_hash=array_content_hash(
            solution_metadata, solution_array
        ),
        source_physical_residual_data_hash=array_data_hash(source_residual),
        source_physical_residual_content_hash=array_content_hash(
            residual_metadata, source_residual
        ),
        convergence_history_hash=canonical_hash(
            {"convergence_history": solution.convergence_history}
        ),
        line_search_history_hash=canonical_hash(
            {"line_search_history": solution.line_search_history}
        ),
        residual_formula_hash=RESIDUAL_FORMULA_HASH,
        tangent_definition=metrics["tangent_definition"],
        globalization=metrics["globalization"],
        terminal_disposition=metrics["terminal_disposition"],
        terminal_reason=metrics["terminal_reason"],
        matrix_backend=metrics["matrix_backend"],
        iteration_count=int(metrics["iteration_count"]),
        linear_solve_count=int(metrics["linear_solve_count"]),
        line_search_step_count=int(metrics["line_search_step_count"]),
        fallback_count=int(bool(metrics["fallback_used"])),
        regularization_count=int(bool(metrics["regularization_used"])),
        raw_translation_l2_n=trace.raw_translation_l2_n,
        raw_translation_linf_n=trace.raw_translation_linf_n,
        raw_rotation_l2_nm=trace.raw_rotation_l2_nm,
        raw_rotation_linf_nm=trace.raw_rotation_linf_nm,
        scaled_residual_l2=trace.scaled_l2,
        scaled_residual_linf=trace.scaled_linf,
        scaled_residual_tolerance=FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE,
        solver_coordinate_increment_linf_m=increment,
        solver_coordinate_increment_tolerance_m=FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M,
        dimensionless_increment_linf=scaled_increment,
        dimensionless_increment_tolerance=scaled_increment_tolerance,
        governing_equation=trace.governing_equation,
        governing_node_id=trace.governing_node_id,
        governing_dof=trace.governing_dof,
        residual_gate_passed=residual_gate,
        increment_gate_passed=increment_gate,
        convergence_gate_passed=residual_gate and increment_gate and audit.passed,
        jacobian_audit=audit,
        extensions=MappingProxyType({}),
    )
    result = replace(
        provisional,
        step_receipt_hash=canonical_hash(
            _step_payload(provisional, include_step_receipt_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_terminal_step_receipt(result)


def _step_solver_contract_passes(step: StatefulFiberFrame2DLoadStepResult) -> bool:
    metrics = step.trial_solution.metrics
    return bool(
        step.status == "ready"
        and step.committed is True
        and step.metrics.get("solver_contract_pass") is True
        and step.metrics.get("iterative_solver_contract_pass") is True
        and metrics.get("contract_pass") is True
        and metrics.get("convergence_claim") is True
        and metrics.get("residual_formula") == RESIDUAL_FORMULA
        and metrics.get("residual_formula_hash") == RESIDUAL_FORMULA_HASH
        and metrics.get("tangent_definition")
        == FIBER_FRAME_NONLINEAR_TANGENT_DEFINITION
        and metrics.get("globalization") == GLOBALIZATION
        and metrics.get("terminal_disposition") == SOLVE_FREE_EQUATIONS_DISPOSITION
        and metrics.get("terminal_reason") == "residual_and_increment_converged"
        and metrics.get("solver_executed") is True
        and metrics.get("residual_gate_passed") is True
        and metrics.get("increment_gate_passed") is True
        and metrics.get("fallback_used") is False
        and metrics.get("regularization_used") is False
    )


def _build_jacobian_audit(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    step: StatefulFiberFrame2DLoadStepResult,
    free_order_hash: str,
) -> FiberFrameNonlinearJacobianAuditReceipt:
    diagnostic = finite_difference_stateful_fiber_frame2d_tangent_check(
        problem,
        step.parent_checkpoint,
        target_load_factor=step.accepted_checkpoint.load_factor,
        trial_free_coordinates_m=step.trial_solution.free_displacements_m,
        epsilon_m=FIBER_FRAME_NONLINEAR_JACOBIAN_EPSILON_M,
        relative_tolerance=FIBER_FRAME_NONLINEAR_JACOBIAN_RELATIVE_TOLERANCE,
    )
    if diagnostic["pass"] is not True:
        _fail(
            "terminal_jacobian_audit_failed",
            "/jacobian_audit",
            "Same-parent finite-difference Jacobian audit failed.",
        )
    free = immutable_array(step.trial_solution.free_displacements_m, dtype="<f8")
    analytic = immutable_array(diagnostic["analytic_jacobian_kn_per_m"], dtype="<f8")
    difference = immutable_array(
        diagnostic["finite_difference_jacobian_kn_per_m"], dtype="<f8"
    )
    free_metadata = _array_metadata(free, free_order_hash)
    matrix_metadata = _matrix_metadata(analytic, free_order_hash)
    difference_metadata = _matrix_metadata(difference, free_order_hash)
    provisional = FiberFrameNonlinearJacobianAuditReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_SCHEMA_VERSION,
        audit_hash=_HASH_ZERO,
        audit_profile=FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_PROFILE,
        problem_contract_hash=problem.contract_hash,
        execution_topology_plan_hash=topology_plan.plan_hash,
        free_solver_dofs_content_hash=free_order_hash,
        parent_checkpoint_state_hash=step.parent_checkpoint.state_hash,
        target_load_factor=step.accepted_checkpoint.load_factor,
        finite_difference_epsilon_m=diagnostic["finite_difference_epsilon_m"],
        relative_tolerance=diagnostic["relative_tolerance"],
        free_coordinate_data_hash=array_data_hash(free),
        free_coordinate_content_hash=array_content_hash(free_metadata, free),
        analytic_jacobian_data_hash=array_data_hash(analytic),
        analytic_jacobian_content_hash=array_content_hash(matrix_metadata, analytic),
        finite_difference_jacobian_data_hash=array_data_hash(difference),
        finite_difference_jacobian_content_hash=array_content_hash(
            difference_metadata, difference
        ),
        absolute_inf_error_kn_per_m=diagnostic["absolute_inf_error_kn_per_m"],
        relative_inf_error=diagnostic["relative_inf_error"],
        tangent_symmetry_error_kn_per_m=diagnostic["tangent_symmetry_error"],
        same_committed_parent_checkpoint=diagnostic["same_committed_parent_checkpoint"],
        passed=diagnostic["pass"],
        extensions=MappingProxyType({}),
    )
    result = replace(
        provisional,
        audit_hash=canonical_hash(
            _audit_payload(provisional, include_audit_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_jacobian_audit_receipt(result)


def _config_payload_from_config(config: NewtonRaphsonConfig) -> dict[str, Any]:
    return {
        "profile": "stateful_fiber_frame2d_dense_or_sparse_cpu_newton.v1",
        "residual_tolerance": config.residual_tolerance,
        "increment_tolerance_m": config.increment_tolerance,
        "max_iterations": config.max_iterations,
        "line_search_alphas": list(config.line_search_alphas),
        "matrix_backend": config.matrix_backend,
    }


def _solver_config_payload(
    receipt: FiberFrameNonlinearTerminalReceipt,
) -> dict[str, Any]:
    return {
        "profile": "stateful_fiber_frame2d_dense_or_sparse_cpu_newton.v1",
        "residual_tolerance": receipt.solver_residual_tolerance,
        "increment_tolerance_m": receipt.solver_increment_tolerance_m,
        "max_iterations": receipt.solver_max_iterations,
        "line_search_alphas": list(receipt.solver_line_search_alphas),
        "matrix_backend": receipt.matrix_backend,
    }


def _audit_payload(
    receipt: FiberFrameNonlinearJacobianAuditReceipt,
    *,
    include_audit_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "audit_hash": receipt.audit_hash,
        "audit_profile": receipt.audit_profile,
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "free_solver_dofs_content_hash": receipt.free_solver_dofs_content_hash,
            "parent_checkpoint_state_hash": receipt.parent_checkpoint_state_hash,
        },
        "coordinates": {"target_load_factor": receipt.target_load_factor},
        "controls": {
            "finite_difference_epsilon_m": receipt.finite_difference_epsilon_m,
            "relative_tolerance": receipt.relative_tolerance,
        },
        "binary_identities": {
            "storage_profile": "canonical_little_endian_float64_hash_only.v1",
            "free_coordinate_data_hash": receipt.free_coordinate_data_hash,
            "free_coordinate_content_hash": receipt.free_coordinate_content_hash,
            "analytic_jacobian_data_hash": receipt.analytic_jacobian_data_hash,
            "analytic_jacobian_content_hash": receipt.analytic_jacobian_content_hash,
            "finite_difference_jacobian_data_hash": receipt.finite_difference_jacobian_data_hash,
            "finite_difference_jacobian_content_hash": receipt.finite_difference_jacobian_content_hash,
        },
        "observations": {
            "absolute_inf_error_kn_per_m": receipt.absolute_inf_error_kn_per_m,
            "relative_inf_error": receipt.relative_inf_error,
            "tangent_symmetry_error_kn_per_m": receipt.tangent_symmetry_error_kn_per_m,
        },
        "gates": {
            "same_committed_parent_checkpoint": receipt.same_committed_parent_checkpoint,
            "passed": receipt.passed,
        },
        "extensions": dict(receipt.extensions),
    }
    if not include_audit_hash:
        payload.pop("audit_hash")
    return payload


def _step_payload(
    receipt: FiberFrameNonlinearTerminalStepReceipt,
    *,
    include_step_receipt_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "step_receipt_hash": receipt.step_receipt_hash,
        "authority_profile": receipt.authority_profile,
        "bindings": {
            "execution_state_binding_hash": receipt.execution_state_binding_hash,
            "physical_equation_scaling_binding_hash": receipt.physical_equation_scaling_binding_hash,
            "engine_equation_scaling_hash": receipt.engine_equation_scaling_hash,
            "problem_contract_hash": receipt.problem_contract_hash,
            "case_id": receipt.case_id,
            "parent_checkpoint_state_hash": receipt.parent_checkpoint_state_hash,
            "accepted_checkpoint_state_hash": receipt.accepted_checkpoint_state_hash,
            "committed_kinematic_state_hash": receipt.committed_kinematic_state_hash,
            "committed_material_state_bundle_hash": receipt.committed_material_state_bundle_hash,
            "physical_residual_trace_hash": receipt.physical_residual_trace_hash,
            "solver_config_hash": receipt.solver_config_hash,
            "source_step_replay_hash": receipt.source_step_replay_hash,
            "convergence_history_hash": receipt.convergence_history_hash,
            "line_search_history_hash": receipt.line_search_history_hash,
        },
        "coordinates": {
            "step_index": receipt.step_index,
            "epoch": receipt.epoch,
            "target_load_factor": receipt.target_load_factor,
        },
        "binary_identities": {
            "storage_profile": "canonical_little_endian_float64_hash_only.v1",
            "source_solution_data_hash": receipt.source_solution_data_hash,
            "source_solution_content_hash": receipt.source_solution_content_hash,
            "source_physical_residual_data_hash": receipt.source_physical_residual_data_hash,
            "source_physical_residual_content_hash": receipt.source_physical_residual_content_hash,
        },
        "solver": {
            "residual_formula_hash": receipt.residual_formula_hash,
            "tangent_definition": receipt.tangent_definition,
            "globalization": receipt.globalization,
            "terminal_disposition": receipt.terminal_disposition,
            "terminal_reason": receipt.terminal_reason,
            "matrix_backend": receipt.matrix_backend,
            "iteration_count": receipt.iteration_count,
            "linear_solve_count": receipt.linear_solve_count,
            "line_search_step_count": receipt.line_search_step_count,
            "fallback_count": receipt.fallback_count,
            "regularization_count": receipt.regularization_count,
        },
        "observations": {
            "raw_translation_l2_n": receipt.raw_translation_l2_n,
            "raw_translation_linf_n": receipt.raw_translation_linf_n,
            "raw_rotation_l2_nm": receipt.raw_rotation_l2_nm,
            "raw_rotation_linf_nm": receipt.raw_rotation_linf_nm,
            "scaled_residual_l2": receipt.scaled_residual_l2,
            "scaled_residual_linf": receipt.scaled_residual_linf,
            "scaled_residual_tolerance": receipt.scaled_residual_tolerance,
            "solver_coordinate_increment_linf_m": receipt.solver_coordinate_increment_linf_m,
            "solver_coordinate_increment_tolerance_m": receipt.solver_coordinate_increment_tolerance_m,
            "dimensionless_increment_linf": receipt.dimensionless_increment_linf,
            "dimensionless_increment_tolerance": receipt.dimensionless_increment_tolerance,
            "governing_equation": receipt.governing_equation,
            "governing_node_id": receipt.governing_node_id,
            "governing_dof": receipt.governing_dof,
        },
        "gates": {
            "residual_gate_passed": receipt.residual_gate_passed,
            "increment_gate_passed": receipt.increment_gate_passed,
            "convergence_gate_passed": receipt.convergence_gate_passed,
        },
        "jacobian_audit": receipt.jacobian_audit.to_manifest(),
        "extensions": dict(receipt.extensions),
    }
    if not include_step_receipt_hash:
        payload.pop("step_receipt_hash")
    return payload


def _terminal_payload(
    receipt: FiberFrameNonlinearTerminalReceipt,
    *,
    include_terminal_receipt_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "terminal_receipt_hash": receipt.terminal_receipt_hash,
        "authority_profile": receipt.authority_profile,
        "state_ir_usage_profile": receipt.state_ir_usage_profile,
        "source_schema_versions": dict(_SOURCE_SCHEMA_VERSIONS),
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "model_ir_content_hash": receipt.model_ir_content_hash,
            "case_id": receipt.case_id,
            "execution_state_binding_hash": receipt.execution_state_binding_hash,
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "execution_operator_hash": receipt.execution_operator_hash,
            "execution_numeric_buffer_hash": receipt.execution_numeric_buffer_hash,
            "solver_coordinate_scaling_hash": receipt.solver_coordinate_scaling_hash,
            "physical_equation_scaling_binding_hash": receipt.physical_equation_scaling_binding_hash,
            "engine_equation_scaling_hash": receipt.engine_equation_scaling_hash,
            "engine_equation_scaling_source_commitment_hash": receipt.engine_equation_scaling_source_commitment_hash,
            "physical_equation_order_hash": receipt.physical_equation_order_hash,
            "physical_equation_free_dofs_content_hash": receipt.physical_equation_free_dofs_content_hash,
            "physical_equation_scale_vector_content_hash": receipt.physical_equation_scale_vector_content_hash,
            "checkpoint_chain_hash": receipt.checkpoint_chain_hash,
            "kinematic_state_chain_hash": receipt.kinematic_state_chain_hash,
            "material_state_projection_chain_hash": receipt.material_state_projection_chain_hash,
            "root_checkpoint_state_hash": receipt.root_checkpoint_state_hash,
            "terminal_checkpoint_state_hash": receipt.terminal_checkpoint_state_hash,
            "terminal_kinematic_state_hash": receipt.terminal_kinematic_state_hash,
            "terminal_material_state_bundle_hash": receipt.terminal_material_state_bundle_hash,
            "source_load_path_replay_hash": receipt.source_load_path_replay_hash,
            "solver_config_hash": receipt.solver_config_hash,
            "step_receipt_chain_hash": receipt.step_receipt_chain_hash,
            "jacobian_audit_chain_hash": receipt.jacobian_audit_chain_hash,
        },
        "solver": {
            "residual_formula": receipt.residual_formula,
            "residual_formula_hash": receipt.residual_formula_hash,
            "tangent_definition": receipt.tangent_definition,
            "globalization": receipt.globalization,
            "residual_gate_profile": receipt.residual_gate_profile,
            "increment_gate_profile": receipt.increment_gate_profile,
            "matrix_backend": receipt.matrix_backend,
            "residual_tolerance": receipt.solver_residual_tolerance,
            "increment_tolerance_m": receipt.solver_increment_tolerance_m,
            "max_iterations": receipt.solver_max_iterations,
            "line_search_alphas": list(receipt.solver_line_search_alphas),
        },
        "terminal": {
            "accepted_step_count": receipt.accepted_step_count,
            "terminal_epoch": receipt.terminal_epoch,
            "terminal_load_factor": receipt.terminal_load_factor,
            "terminal_reason": receipt.terminal_reason,
            "converged": receipt.converged,
            "total_iteration_count": receipt.total_iteration_count,
            "total_linear_solve_count": receipt.total_linear_solve_count,
            "total_line_search_step_count": receipt.total_line_search_step_count,
            "fallback_count": receipt.fallback_count,
            "regularization_count": receipt.regularization_count,
            "final_raw_translation_linf_n": receipt.final_raw_translation_linf_n,
            "final_raw_rotation_linf_nm": receipt.final_raw_rotation_linf_nm,
            "final_scaled_residual_linf": receipt.final_scaled_residual_linf,
            "final_solver_coordinate_increment_linf_m": receipt.final_solver_coordinate_increment_linf_m,
            "terminal_governing_node_id": receipt.terminal_governing_node_id,
            "terminal_governing_dof": receipt.terminal_governing_dof,
        },
        "step_receipts": [row.to_manifest() for row in receipt.step_receipts],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_terminal_receipt_hash:
        payload.pop("terminal_receipt_hash")
    return payload


def _terminal_from_manifest(
    manifest: Mapping[str, Any],
) -> FiberFrameNonlinearTerminalReceipt:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "terminal_receipt_hash",
            "authority_profile",
            "state_ir_usage_profile",
            "source_schema_versions",
            "bindings",
            "solver",
            "terminal",
            "step_receipts",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    source_versions = _manifest_object(
        manifest["source_schema_versions"], "/source_schema_versions"
    )
    if source_versions != dict(_SOURCE_SCHEMA_VERSIONS):
        _fail(
            "terminal_manifest_source_schemas_invalid",
            "/source_schema_versions",
            "Source schema versions changed.",
        )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    binding_keys = {
        "problem_contract_hash",
        "model_ir_content_hash",
        "case_id",
        "execution_state_binding_hash",
        "execution_topology_plan_hash",
        "execution_operator_hash",
        "execution_numeric_buffer_hash",
        "solver_coordinate_scaling_hash",
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "engine_equation_scaling_source_commitment_hash",
        "physical_equation_order_hash",
        "physical_equation_free_dofs_content_hash",
        "physical_equation_scale_vector_content_hash",
        "checkpoint_chain_hash",
        "kinematic_state_chain_hash",
        "material_state_projection_chain_hash",
        "root_checkpoint_state_hash",
        "terminal_checkpoint_state_hash",
        "terminal_kinematic_state_hash",
        "terminal_material_state_bundle_hash",
        "source_load_path_replay_hash",
        "solver_config_hash",
        "step_receipt_chain_hash",
        "jacobian_audit_chain_hash",
    }
    _exact_keys(bindings, binding_keys, "/bindings")
    solver = _manifest_object(manifest["solver"], "/solver")
    _exact_keys(
        solver,
        {
            "residual_formula",
            "residual_formula_hash",
            "tangent_definition",
            "globalization",
            "residual_gate_profile",
            "increment_gate_profile",
            "matrix_backend",
            "residual_tolerance",
            "increment_tolerance_m",
            "max_iterations",
            "line_search_alphas",
        },
        "/solver",
    )
    terminal = _manifest_object(manifest["terminal"], "/terminal")
    _exact_keys(
        terminal,
        {
            "accepted_step_count",
            "terminal_epoch",
            "terminal_load_factor",
            "terminal_reason",
            "converged",
            "total_iteration_count",
            "total_linear_solve_count",
            "total_line_search_step_count",
            "fallback_count",
            "regularization_count",
            "final_raw_translation_linf_n",
            "final_raw_rotation_linf_nm",
            "final_scaled_residual_linf",
            "final_solver_coordinate_increment_linf_m",
            "terminal_governing_node_id",
            "terminal_governing_dof",
        },
        "/terminal",
    )
    raw_steps = manifest["step_receipts"]
    if type(raw_steps) is not list:
        _fail(
            "terminal_manifest_step_set_invalid",
            "/step_receipts",
            "Expected a JSON array.",
        )
    rows = tuple(
        _step_from_manifest(_manifest_object(value, f"/step_receipts/{index}"))
        for index, value in enumerate(raw_steps)
    )
    _require_claim_boundary(manifest["claim_boundary"])
    extensions = _manifest_extensions(manifest["extensions"])
    alphas = solver["line_search_alphas"]
    if type(alphas) is not list:
        _fail(
            "terminal_manifest_line_search_invalid",
            "/solver/line_search_alphas",
            "Expected a JSON array.",
        )
    return FiberFrameNonlinearTerminalReceipt(
        schema_version=manifest["schema_version"],
        terminal_receipt_hash=manifest["terminal_receipt_hash"],
        authority_profile=manifest["authority_profile"],
        state_ir_usage_profile=manifest["state_ir_usage_profile"],
        problem_contract_hash=bindings["problem_contract_hash"],
        model_ir_content_hash=bindings["model_ir_content_hash"],
        case_id=bindings["case_id"],
        execution_state_binding_hash=bindings["execution_state_binding_hash"],
        execution_topology_plan_hash=bindings["execution_topology_plan_hash"],
        execution_operator_hash=bindings["execution_operator_hash"],
        execution_numeric_buffer_hash=bindings["execution_numeric_buffer_hash"],
        solver_coordinate_scaling_hash=bindings["solver_coordinate_scaling_hash"],
        physical_equation_scaling_binding_hash=bindings[
            "physical_equation_scaling_binding_hash"
        ],
        engine_equation_scaling_hash=bindings["engine_equation_scaling_hash"],
        engine_equation_scaling_source_commitment_hash=bindings[
            "engine_equation_scaling_source_commitment_hash"
        ],
        physical_equation_order_hash=bindings["physical_equation_order_hash"],
        physical_equation_free_dofs_content_hash=bindings[
            "physical_equation_free_dofs_content_hash"
        ],
        physical_equation_scale_vector_content_hash=bindings[
            "physical_equation_scale_vector_content_hash"
        ],
        checkpoint_chain_hash=bindings["checkpoint_chain_hash"],
        kinematic_state_chain_hash=bindings["kinematic_state_chain_hash"],
        material_state_projection_chain_hash=bindings[
            "material_state_projection_chain_hash"
        ],
        root_checkpoint_state_hash=bindings["root_checkpoint_state_hash"],
        terminal_checkpoint_state_hash=bindings["terminal_checkpoint_state_hash"],
        terminal_kinematic_state_hash=bindings["terminal_kinematic_state_hash"],
        terminal_material_state_bundle_hash=bindings[
            "terminal_material_state_bundle_hash"
        ],
        source_load_path_replay_hash=bindings["source_load_path_replay_hash"],
        solver_config_hash=bindings["solver_config_hash"],
        step_receipt_chain_hash=bindings["step_receipt_chain_hash"],
        jacobian_audit_chain_hash=bindings["jacobian_audit_chain_hash"],
        residual_formula=solver["residual_formula"],
        residual_formula_hash=solver["residual_formula_hash"],
        tangent_definition=solver["tangent_definition"],
        globalization=solver["globalization"],
        residual_gate_profile=solver["residual_gate_profile"],
        increment_gate_profile=solver["increment_gate_profile"],
        matrix_backend=solver["matrix_backend"],
        solver_residual_tolerance=solver["residual_tolerance"],
        solver_increment_tolerance_m=solver["increment_tolerance_m"],
        solver_max_iterations=solver["max_iterations"],
        solver_line_search_alphas=tuple(alphas),
        accepted_step_count=terminal["accepted_step_count"],
        terminal_epoch=terminal["terminal_epoch"],
        terminal_load_factor=terminal["terminal_load_factor"],
        terminal_reason=terminal["terminal_reason"],
        converged=terminal["converged"],
        total_iteration_count=terminal["total_iteration_count"],
        total_linear_solve_count=terminal["total_linear_solve_count"],
        total_line_search_step_count=terminal["total_line_search_step_count"],
        fallback_count=terminal["fallback_count"],
        regularization_count=terminal["regularization_count"],
        final_raw_translation_linf_n=terminal["final_raw_translation_linf_n"],
        final_raw_rotation_linf_nm=terminal["final_raw_rotation_linf_nm"],
        final_scaled_residual_linf=terminal["final_scaled_residual_linf"],
        final_solver_coordinate_increment_linf_m=terminal[
            "final_solver_coordinate_increment_linf_m"
        ],
        terminal_governing_node_id=terminal["terminal_governing_node_id"],
        terminal_governing_dof=terminal["terminal_governing_dof"],
        step_receipts=rows,
        extensions=extensions,
    )


def _step_from_manifest(
    manifest: Mapping[str, Any],
) -> FiberFrameNonlinearTerminalStepReceipt:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "step_receipt_hash",
            "authority_profile",
            "bindings",
            "coordinates",
            "binary_identities",
            "solver",
            "observations",
            "gates",
            "jacobian_audit",
            "extensions",
        },
        "/",
    )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "execution_state_binding_hash",
            "physical_equation_scaling_binding_hash",
            "engine_equation_scaling_hash",
            "problem_contract_hash",
            "case_id",
            "parent_checkpoint_state_hash",
            "accepted_checkpoint_state_hash",
            "committed_kinematic_state_hash",
            "committed_material_state_bundle_hash",
            "physical_residual_trace_hash",
            "solver_config_hash",
            "source_step_replay_hash",
            "convergence_history_hash",
            "line_search_history_hash",
        },
        "/bindings",
    )
    coordinates = _manifest_object(manifest["coordinates"], "/coordinates")
    _exact_keys(
        coordinates, {"step_index", "epoch", "target_load_factor"}, "/coordinates"
    )
    binary = _manifest_object(manifest["binary_identities"], "/binary_identities")
    _exact_keys(
        binary,
        {
            "storage_profile",
            "source_solution_data_hash",
            "source_solution_content_hash",
            "source_physical_residual_data_hash",
            "source_physical_residual_content_hash",
        },
        "/binary_identities",
    )
    if binary["storage_profile"] != "canonical_little_endian_float64_hash_only.v1":
        _fail(
            "terminal_manifest_binary_profile_invalid",
            "/binary_identities/storage_profile",
            "Unsupported binary profile.",
        )
    solver = _manifest_object(manifest["solver"], "/solver")
    _exact_keys(
        solver,
        {
            "residual_formula_hash",
            "tangent_definition",
            "globalization",
            "terminal_disposition",
            "terminal_reason",
            "matrix_backend",
            "iteration_count",
            "linear_solve_count",
            "line_search_step_count",
            "fallback_count",
            "regularization_count",
        },
        "/solver",
    )
    obs = _manifest_object(manifest["observations"], "/observations")
    _exact_keys(
        obs,
        {
            "raw_translation_l2_n",
            "raw_translation_linf_n",
            "raw_rotation_l2_nm",
            "raw_rotation_linf_nm",
            "scaled_residual_l2",
            "scaled_residual_linf",
            "scaled_residual_tolerance",
            "solver_coordinate_increment_linf_m",
            "solver_coordinate_increment_tolerance_m",
            "dimensionless_increment_linf",
            "dimensionless_increment_tolerance",
            "governing_equation",
            "governing_node_id",
            "governing_dof",
        },
        "/observations",
    )
    gates = _manifest_object(manifest["gates"], "/gates")
    _exact_keys(
        gates,
        {"residual_gate_passed", "increment_gate_passed", "convergence_gate_passed"},
        "/gates",
    )
    audit = _audit_from_manifest(
        _manifest_object(manifest["jacobian_audit"], "/jacobian_audit")
    )
    return FiberFrameNonlinearTerminalStepReceipt(
        schema_version=manifest["schema_version"],
        step_receipt_hash=manifest["step_receipt_hash"],
        authority_profile=manifest["authority_profile"],
        execution_state_binding_hash=bindings["execution_state_binding_hash"],
        physical_equation_scaling_binding_hash=bindings[
            "physical_equation_scaling_binding_hash"
        ],
        engine_equation_scaling_hash=bindings["engine_equation_scaling_hash"],
        problem_contract_hash=bindings["problem_contract_hash"],
        case_id=bindings["case_id"],
        step_index=coordinates["step_index"],
        epoch=coordinates["epoch"],
        target_load_factor=coordinates["target_load_factor"],
        parent_checkpoint_state_hash=bindings["parent_checkpoint_state_hash"],
        accepted_checkpoint_state_hash=bindings["accepted_checkpoint_state_hash"],
        committed_kinematic_state_hash=bindings["committed_kinematic_state_hash"],
        committed_material_state_bundle_hash=bindings[
            "committed_material_state_bundle_hash"
        ],
        physical_residual_trace_hash=bindings["physical_residual_trace_hash"],
        solver_config_hash=bindings["solver_config_hash"],
        source_step_replay_hash=bindings["source_step_replay_hash"],
        source_solution_data_hash=binary["source_solution_data_hash"],
        source_solution_content_hash=binary["source_solution_content_hash"],
        source_physical_residual_data_hash=binary["source_physical_residual_data_hash"],
        source_physical_residual_content_hash=binary[
            "source_physical_residual_content_hash"
        ],
        convergence_history_hash=bindings["convergence_history_hash"],
        line_search_history_hash=bindings["line_search_history_hash"],
        residual_formula_hash=solver["residual_formula_hash"],
        tangent_definition=solver["tangent_definition"],
        globalization=solver["globalization"],
        terminal_disposition=solver["terminal_disposition"],
        terminal_reason=solver["terminal_reason"],
        matrix_backend=solver["matrix_backend"],
        iteration_count=solver["iteration_count"],
        linear_solve_count=solver["linear_solve_count"],
        line_search_step_count=solver["line_search_step_count"],
        fallback_count=solver["fallback_count"],
        regularization_count=solver["regularization_count"],
        raw_translation_l2_n=obs["raw_translation_l2_n"],
        raw_translation_linf_n=obs["raw_translation_linf_n"],
        raw_rotation_l2_nm=obs["raw_rotation_l2_nm"],
        raw_rotation_linf_nm=obs["raw_rotation_linf_nm"],
        scaled_residual_l2=obs["scaled_residual_l2"],
        scaled_residual_linf=obs["scaled_residual_linf"],
        scaled_residual_tolerance=obs["scaled_residual_tolerance"],
        solver_coordinate_increment_linf_m=obs["solver_coordinate_increment_linf_m"],
        solver_coordinate_increment_tolerance_m=obs[
            "solver_coordinate_increment_tolerance_m"
        ],
        dimensionless_increment_linf=obs["dimensionless_increment_linf"],
        dimensionless_increment_tolerance=obs["dimensionless_increment_tolerance"],
        governing_equation=obs["governing_equation"],
        governing_node_id=obs["governing_node_id"],
        governing_dof=obs["governing_dof"],
        residual_gate_passed=gates["residual_gate_passed"],
        increment_gate_passed=gates["increment_gate_passed"],
        convergence_gate_passed=gates["convergence_gate_passed"],
        jacobian_audit=audit,
        extensions=_manifest_extensions(manifest["extensions"]),
    )


def _audit_from_manifest(
    manifest: Mapping[str, Any],
) -> FiberFrameNonlinearJacobianAuditReceipt:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "audit_hash",
            "audit_profile",
            "bindings",
            "coordinates",
            "controls",
            "binary_identities",
            "observations",
            "gates",
            "extensions",
        },
        "/",
    )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "execution_topology_plan_hash",
            "free_solver_dofs_content_hash",
            "parent_checkpoint_state_hash",
        },
        "/bindings",
    )
    coordinates = _manifest_object(manifest["coordinates"], "/coordinates")
    _exact_keys(coordinates, {"target_load_factor"}, "/coordinates")
    controls = _manifest_object(manifest["controls"], "/controls")
    _exact_keys(
        controls, {"finite_difference_epsilon_m", "relative_tolerance"}, "/controls"
    )
    binary = _manifest_object(manifest["binary_identities"], "/binary_identities")
    _exact_keys(
        binary,
        {
            "storage_profile",
            "free_coordinate_data_hash",
            "free_coordinate_content_hash",
            "analytic_jacobian_data_hash",
            "analytic_jacobian_content_hash",
            "finite_difference_jacobian_data_hash",
            "finite_difference_jacobian_content_hash",
        },
        "/binary_identities",
    )
    if binary["storage_profile"] != "canonical_little_endian_float64_hash_only.v1":
        _fail(
            "terminal_manifest_binary_profile_invalid",
            "/binary_identities/storage_profile",
            "Unsupported binary profile.",
        )
    obs = _manifest_object(manifest["observations"], "/observations")
    _exact_keys(
        obs,
        {
            "absolute_inf_error_kn_per_m",
            "relative_inf_error",
            "tangent_symmetry_error_kn_per_m",
        },
        "/observations",
    )
    gates = _manifest_object(manifest["gates"], "/gates")
    _exact_keys(gates, {"same_committed_parent_checkpoint", "passed"}, "/gates")
    return FiberFrameNonlinearJacobianAuditReceipt(
        schema_version=manifest["schema_version"],
        audit_hash=manifest["audit_hash"],
        audit_profile=manifest["audit_profile"],
        problem_contract_hash=bindings["problem_contract_hash"],
        execution_topology_plan_hash=bindings["execution_topology_plan_hash"],
        free_solver_dofs_content_hash=bindings["free_solver_dofs_content_hash"],
        parent_checkpoint_state_hash=bindings["parent_checkpoint_state_hash"],
        target_load_factor=coordinates["target_load_factor"],
        finite_difference_epsilon_m=controls["finite_difference_epsilon_m"],
        relative_tolerance=controls["relative_tolerance"],
        free_coordinate_data_hash=binary["free_coordinate_data_hash"],
        free_coordinate_content_hash=binary["free_coordinate_content_hash"],
        analytic_jacobian_data_hash=binary["analytic_jacobian_data_hash"],
        analytic_jacobian_content_hash=binary["analytic_jacobian_content_hash"],
        finite_difference_jacobian_data_hash=binary[
            "finite_difference_jacobian_data_hash"
        ],
        finite_difference_jacobian_content_hash=binary[
            "finite_difference_jacobian_content_hash"
        ],
        absolute_inf_error_kn_per_m=obs["absolute_inf_error_kn_per_m"],
        relative_inf_error=obs["relative_inf_error"],
        tangent_symmetry_error_kn_per_m=obs["tangent_symmetry_error_kn_per_m"],
        same_committed_parent_checkpoint=gates["same_committed_parent_checkpoint"],
        passed=gates["passed"],
        extensions=_manifest_extensions(manifest["extensions"]),
    )


def _descriptor_content_hash(
    plan: FiberFrameNonlinearExecutionTopologyPlan, name: str
) -> str:
    for descriptor in plan.descriptors:
        if descriptor.name == name:
            return descriptor.content_hash
    _fail(
        "terminal_source_descriptor_missing",
        f"/topology_plan/descriptors/{name}",
        "Required topology descriptor is missing.",
    )


def _solver_equation_order_hash(plan: FiberFrameNonlinearExecutionTopologyPlan) -> str:
    return canonical_hash(
        {
            "profile": "stateful_fiber_frame2d_solver_3dof_order.v1",
            "node_ids": list(plan.node_ids),
            "components": ["UX", "UY", "RZ"],
        }
    )


def _array_metadata(array: np.ndarray, equation_order_hash: str) -> dict[str, Any]:
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
        "equation_order_hash": equation_order_hash,
    }


def _matrix_metadata(array: np.ndarray, equation_order_hash: str) -> dict[str, Any]:
    return {
        **_array_metadata(array, equation_order_hash),
        "row_equation_order_hash": equation_order_hash,
        "column_equation_order_hash": equation_order_hash,
    }


def _validate_line_search_alphas(value: Any) -> tuple[float, ...]:
    if type(value) is not tuple or not value:
        _fail(
            "terminal_line_search_invalid",
            "/solver/line_search_alphas",
            "Expected a non-empty tuple.",
        )
    previous = math.inf
    for index, alpha in enumerate(value):
        if (
            type(alpha) is not float
            or not math.isfinite(alpha)
            or alpha <= 0.0
            or alpha > 1.0
            or alpha >= previous
        ):
            _fail(
                "terminal_line_search_invalid",
                f"/solver/line_search_alphas/{index}",
                "Alphas must be finite, positive, and strictly decreasing.",
            )
        previous = alpha
    return value


def _require_authority_profile(value: Any) -> None:
    if value != FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE:
        _fail(
            "terminal_authority_profile_invalid",
            "/authority_profile",
            "Authority cannot be promoted beyond bounded convergence.",
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or not _HASH_PATTERN.fullmatch(value):
        _fail("terminal_hash_invalid", path, "Expected lowercase sha256:<hex>.")
    return value


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail("terminal_index_invalid", path, "Expected a non-negative 32-bit integer.")
    return value


def _positive_index(value: Any, path: str) -> int:
    result = _index(value, path)
    if result < 1:
        _fail("terminal_index_invalid", path, "Expected a positive integer.")
    return result


def _finite(value: Any, path: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        _fail("terminal_float_invalid", path, "Expected a finite JSON float.")
    return value


def _nonnegative(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result < 0.0:
        _fail("terminal_float_invalid", path, "Expected a non-negative float.")
    return result


def _positive(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result <= 0.0:
        _fail("terminal_float_invalid", path, "Expected a positive float.")
    return result


def _nonempty(value: Any, path: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail("terminal_string_invalid", path, "Expected a non-empty trimmed string.")
    return value


def _manifest_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("terminal_manifest_object_invalid", path, "Expected a JSON object.")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected or any(type(key) is not str for key in value):
        _fail(
            "terminal_manifest_keys_invalid",
            path,
            "Manifest keys do not match exactly.",
        )


def _require_claim_boundary(value: Any) -> None:
    payload = _manifest_object(value, "/claim_boundary")
    _exact_keys(
        payload, set(FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY), "/claim_boundary"
    )
    if any(
        type(payload[key]) is not bool or payload[key] is not expected
        for key, expected in FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY.items()
    ):
        _fail(
            "terminal_claim_boundary_invalid",
            "/claim_boundary",
            "Claim boundary cannot be promoted or weakened.",
        )


def _manifest_extensions(value: Any) -> Mapping[str, Any]:
    payload = _manifest_object(value, "/extensions")
    if payload:
        _fail(
            "terminal_extensions_invalid",
            "/extensions",
            "v1 requires empty extensions.",
        )
    return MappingProxyType({})


def _require_empty_extensions(value: Any) -> None:
    if not isinstance(value, MappingProxyType) or value:
        _fail(
            "terminal_extensions_invalid",
            "/extensions",
            "v1 requires immutable empty extensions.",
        )


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearTerminalReceiptError(
        f"fiber_frame_nonlinear_{code}", path, message
    )


__all__ = [
    "FIBER_FRAME_NONLINEAR_INCREMENT_GATE_PROFILE",
    "FIBER_FRAME_NONLINEAR_INCREMENT_TOLERANCE_M",
    "FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_PROFILE",
    "FIBER_FRAME_NONLINEAR_JACOBIAN_AUDIT_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RESIDUAL_GATE_PROFILE",
    "FIBER_FRAME_NONLINEAR_SCALED_RESIDUAL_TOLERANCE",
    "FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_TERMINAL_REASON",
    "FIBER_FRAME_NONLINEAR_TERMINAL_STEP_SCHEMA_VERSION",
    "FiberFrameNonlinearJacobianAuditReceipt",
    "FiberFrameNonlinearTerminalReceipt",
    "FiberFrameNonlinearTerminalReceiptError",
    "FiberFrameNonlinearTerminalStepReceipt",
    "create_fiber_frame_nonlinear_terminal_receipt",
    "validate_fiber_frame_nonlinear_jacobian_audit_receipt",
    "validate_fiber_frame_nonlinear_terminal_receipt",
    "validate_fiber_frame_nonlinear_terminal_receipt_manifest",
    "validate_fiber_frame_nonlinear_terminal_receipt_shape",
    "validate_fiber_frame_nonlinear_terminal_step_receipt",
]
