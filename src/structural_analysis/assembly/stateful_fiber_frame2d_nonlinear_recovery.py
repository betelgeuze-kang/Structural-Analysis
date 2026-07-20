"""Exact terminal engineering recovery for the bounded stateful fiber frame.

The operator starts from the last accepted parent checkpoint and the terminal
J3 kinematic state, then independently replays the terminal constitutive,
section, element, transformation, and global-assembly path.  No force or stress
array returned by the source Newton solve is accepted as an engineering result.
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
    STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FiberFrameNonlinearExecutionTopologyPlan,
    physical_3dof_to_canonical_6dof,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    FiberFrameNonlinearNumericalResultAdapter,
    validate_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_FORCE_TO_SI,
    FIBER_FRAME_MOMENT_TO_SI,
)
from structural_analysis.elements.stateful_fiber_beam2d_contract import (
    STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_FIBER_BEAM2D_KINEMATICS,
    STATEFUL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    validate_material_state_bundle,
)
from structural_analysis.materials.concrete_damage import (
    STATE_SCHEMA_VERSION as CONCRETE_DAMAGE_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.stateful_fiber_section import (
    FIBER_SECTION_RESULTANT_DEFINITION,
    FIBER_SECTION_STRAIN_RELATION,
    FIBER_SECTION_TANGENT_DEFINITION,
    StatefulFiberSectionResponse,
    StatefulRCFiberSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    STATE_SCHEMA_VERSION as STEEL_PLASTICITY_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.uniaxial_plasticity import (
    UniaxialPlasticityState,
)
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA


FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-engineering-recovery-operator.v1"
)
FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-engineering-result.v1"
)
FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE = (
    "exact_terminal_parent_constitutive_section_element_global_replay.v1"
)
FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_AUTHORITY_PROFILE = (
    "non_authoritative_exact_fiber_frame_recovery_operator.v1"
)
FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_AUTHORITY_PROFILE = (
    "authoritative_bounded_fiber_frame_engineering_recovery.v1"
)
FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_KIND = (
    "nonlinear_fiber_frame_reaction_member_section_fiber"
)
FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE = (
    "canonical_little_endian_hash_bound_arrays.v1"
)
FIBER_FRAME_NONLINEAR_MEMBER_FORCE_ORDER = (
    "member_order_fx_i_fy_i_mz_i_fx_j_fy_j_mz_j.v1"
)
FIBER_FRAME_NONLINEAR_SECTION_RESULTANT_ORDER = (
    "member_then_gauss_ip_axial_force_n_moment_z_nm.v1"
)
FIBER_FRAME_NONLINEAR_FIBER_OUTPUT_ORDER = "member_then_gauss_ip_then_section_fiber.v1"
FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE = 1.0e-12
FIBER_FRAME_NONLINEAR_RECOVERY_FIBER_STRAIN_TOLERANCE = 1.0e-15

FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "inherited_authoritative",
        "convergence": "inherited_authoritative",
        "displacement": "inherited_authoritative",
        "material_state": "inherited_authoritative",
        "reaction": "authoritative",
        "member_force": "authoritative",
        "section_resultant": "authoritative",
        "fiber_strain_stress": "authoritative",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)
FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY = MappingProxyType(
    {
        "exact_j1_j5_source_replayed": True,
        "terminal_parent_checkpoint_bound": True,
        "terminal_constitutive_transition_replayed": True,
        "section_integration_replayed": True,
        "member_local_end_force_replayed": True,
        "local_global_transformation_replayed": True,
        "element_to_global_scatter_replayed": True,
        "free_equation_equilibrium_checked": True,
        "constrained_reaction_partition_checked": True,
        "constituent_state_bytes_checked": True,
        "energy_and_work_consistency_checked": True,
        "solver_returned_force_arrays_trusted": False,
        "result_authority": False,
        "constitutive_law_independently_verified": False,
        "cpu_hip_parity_established": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)
FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY = MappingProxyType(
    {
        "bounded_stateful_rc_fiber_frame_only": True,
        "small_displacement_fixed_chord_only": True,
        "zero_prescribed_displacement_only": True,
        "proportional_nodal_load_only": True,
        "reaction_authority": True,
        "member_local_end_force_authority": True,
        "section_resultant_authority": True,
        "fiber_strain_stress_authority": True,
        "dissipated_energy_observation_authority": True,
        "geometric_nonlinearity": False,
        "distributed_load_recovery": False,
        "member_release_or_offset_recovery": False,
        "general_topology_authority": False,
        "engineering_design": False,
        "code_compliance": False,
        "viewer_projection": False,
        "cpu_hip_parity_established": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1

_ARRAY_SPECS = (
    (
        "member_global_dofs_source_3dof",
        "<i4",
        2,
        "source_ux_uy_rz_global_dof_indices.v1",
        "member_order",
        "mapping_evidence",
    ),
    (
        "member_transformation_global_to_local",
        "<f8",
        3,
        "dimensionless_fixed_chord_transform.v1",
        "member_order",
        "replay_evidence",
    ),
    (
        "member_local_displacement",
        "<f8",
        2,
        "ux_uy_m_rz_rad_i_then_j.v1",
        "member_order",
        "replay_evidence",
    ),
    (
        "member_local_end_force_si",
        "<f8",
        2,
        "fx_fy_n_mz_nm_i_then_j.v1",
        "member_order",
        "authoritative_output",
    ),
    (
        "member_global_end_force_si",
        "<f8",
        2,
        "global_fx_fy_n_mz_nm_i_then_j.v1",
        "member_order",
        "replay_evidence",
    ),
    (
        "internal_load_global_si",
        "<f8",
        1,
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
        "physical_equation_order",
        "replay_evidence",
    ),
    (
        "external_load_global_si",
        "<f8",
        1,
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
        "physical_equation_order",
        "replay_evidence",
    ),
    (
        "equilibrium_residual_global_si",
        "<f8",
        1,
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
        "physical_equation_order",
        "authoritative_output",
    ),
    (
        "reaction_global_si",
        "<f8",
        1,
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
        "physical_equation_order",
        "authoritative_output",
    ),
    (
        "integration_point_offsets",
        "<i8",
        1,
        "member_to_flat_integration_point_offsets.v1",
        "integration_point_order",
        "mapping_evidence",
    ),
    (
        "integration_point_xi",
        "<f8",
        1,
        "gauss_parent_coordinate.v1",
        "integration_point_order",
        "mapping_evidence",
    ),
    (
        "integration_point_weights",
        "<f8",
        1,
        "gauss_weight.v1",
        "integration_point_order",
        "mapping_evidence",
    ),
    (
        "section_generalized_strain",
        "<f8",
        2,
        "axial_strain_curvature_z_per_m.v1",
        "integration_point_order",
        "authoritative_output",
    ),
    (
        "section_resultant_si",
        "<f8",
        2,
        "axial_force_n_moment_z_nm.v1",
        "integration_point_order",
        "authoritative_output",
    ),
    (
        "section_dissipated_energy_mj_per_m",
        "<f8",
        1,
        "mj_per_m.v1",
        "integration_point_order",
        "authoritative_output",
    ),
    (
        "fiber_offsets",
        "<i8",
        1,
        "integration_point_to_flat_fiber_offsets.v1",
        "fiber_output_order",
        "mapping_evidence",
    ),
    (
        "fiber_y_m",
        "<f8",
        1,
        "section_local_y_m.v1",
        "fiber_output_order",
        "mapping_evidence",
    ),
    (
        "fiber_area_m2",
        "<f8",
        1,
        "area_m2.v1",
        "fiber_output_order",
        "mapping_evidence",
    ),
    (
        "fiber_strain",
        "<f8",
        1,
        "dimensionless_total_strain.v1",
        "fiber_output_order",
        "authoritative_output",
    ),
    (
        "fiber_stress_mpa",
        "<f8",
        1,
        "stress_mpa.v1",
        "fiber_output_order",
        "authoritative_output",
    ),
    (
        "fiber_dissipated_energy_density_mj_per_m3",
        "<f8",
        1,
        "dissipated_energy_density_mj_per_m3.v1",
        "fiber_output_order",
        "authoritative_output",
    ),
)
_ARRAY_NAMES = tuple(row[0] for row in _ARRAY_SPECS)
_ARRAY_SPEC_BY_NAME = MappingProxyType({row[0]: row for row in _ARRAY_SPECS})


class FiberFrameNonlinearRecoveryError(ValueError):
    """Stable fail-closed error for exact nonlinear engineering recovery."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameNonlinearRecoveryArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    byte_length: int
    unit_profile: str
    equation_scope: str
    authority_role: Literal[
        "authoritative_output",
        "mapping_evidence",
        "replay_evidence",
    ]
    order_hash: str
    data_hash: str
    content_hash: str
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_order": self.byte_order,
            "byte_length": self.byte_length,
            "unit_profile": self.unit_profile,
            "equation_scope": self.equation_scope,
            "authority_role": self.authority_role,
            "order_hash": self.order_hash,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "artifact_uri": self.artifact_uri,
        }


@dataclass(frozen=True)
class FiberFrameNonlinearRecoveryOperator:
    schema_version: str
    recovery_operator_hash: str
    profile: str
    authority_profile: str
    problem_contract_hash: str
    model_ir_content_hash: str
    case_id: str
    source_result_adapter_hash: str
    source_binding_hash: str
    source_numerical_result_hash: str
    execution_topology_plan_hash: str
    physical_equation_scaling_binding_hash: str
    execution_state_binding_hash: str
    checkpoint_chain_hash: str
    terminal_checkpoint_state_hash: str
    terminal_kinematic_state_hash: str
    terminal_material_state_bundle_hash: str
    terminal_receipt_hash: str
    geometry_hash: str
    member_order_hash: str
    integration_point_output_order_hash: str
    fiber_output_order_hash: str
    constituent_state_replay_hash: str
    recovery_law_hash: str
    terminal_epoch: int
    terminal_load_factor: float
    physical_dof_count: int
    member_count: int
    integration_point_count: int
    fiber_output_count: int
    authored_reaction_count: int
    free_residual_scaled_linf: float
    element_scatter_scaled_linf: float
    local_global_force_scaled_linf: float
    section_integration_scaled_linf: float
    section_resultant_scaled_linf: float
    fiber_strain_linf: float
    local_global_work_scaled_abs: float
    section_element_work_scaled_abs: float
    dissipated_energy_balance_scaled_abs: float
    total_dissipated_energy_mj: float
    transformation_orthogonality_linf: float
    state_bytes_exact: bool
    array_bundle_hash: str
    descriptors: tuple[FiberFrameNonlinearRecoveryArrayDescriptor, ...]
    extensions: Mapping[str, Any]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    _source_adapter: FiberFrameNonlinearNumericalResultAdapter = field(
        repr=False,
        compare=False,
    )

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown fiber-frame recovery array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_recovery_operator(self)
        return _operator_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearEngineeringResultIR:
    schema_version: str
    engineering_result_id: str
    engineering_result_hash: str
    result_kind: str
    authority_profile: str
    source_numerical_result_schema_version: str
    source_numerical_result_hash: str
    source_result_adapter_hash: str
    recovery_operator_hash: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_hash: str
    terminal_kinematic_state_hash: str
    terminal_material_state_bundle_hash: str
    terminal_epoch: int
    load_factor: float
    physical_dof_count: int
    member_count: int
    integration_point_count: int
    fiber_output_count: int
    authored_reaction_count: int
    free_residual_scaled_linf: float
    total_dissipated_energy_mj: float
    array_bundle_hash: str
    descriptors: tuple[FiberFrameNonlinearRecoveryArrayDescriptor, ...]
    extensions: Mapping[str, Any]
    _source_adapter: FiberFrameNonlinearNumericalResultAdapter = field(
        repr=False,
        compare=False,
    )
    _recovery_operator: FiberFrameNonlinearRecoveryOperator = field(
        repr=False,
        compare=False,
    )

    def artifact(self, name: str) -> np.ndarray:
        return self._recovery_operator.array(name)

    @property
    def reaction_global_si(self) -> np.ndarray:
        return self.artifact("reaction_global_si")

    @property
    def equilibrium_residual_global_si(self) -> np.ndarray:
        return self.artifact("equilibrium_residual_global_si")

    @property
    def member_local_end_force_si(self) -> np.ndarray:
        return self.artifact("member_local_end_force_si")

    @property
    def section_resultant_si(self) -> np.ndarray:
        return self.artifact("section_resultant_si")

    @property
    def fiber_strain(self) -> np.ndarray:
        return self.artifact("fiber_strain")

    @property
    def fiber_stress_mpa(self) -> np.ndarray:
        return self.artifact("fiber_stress_mpa")

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_engineering_result_ir(self)
        return _result_payload(self, include_hash=True)


@dataclass(frozen=True)
class _RecoveryReplay:
    bindings: Mapping[str, Any]
    orders: Mapping[str, str]
    counts: Mapping[str, int]
    metrics: Mapping[str, float | bool]
    arrays: Mapping[str, np.ndarray]
    descriptors: tuple[FiberFrameNonlinearRecoveryArrayDescriptor, ...]
    array_bundle_hash: str


def create_fiber_frame_nonlinear_recovery_operator(
    source_adapter: FiberFrameNonlinearNumericalResultAdapter,
) -> FiberFrameNonlinearRecoveryOperator:
    """Replay the exact terminal transition and freeze engineering artifacts."""

    adapter = validate_fiber_frame_nonlinear_numerical_result_adapter(source_adapter)
    operator = _build_recovery_operator(adapter)
    return validate_fiber_frame_nonlinear_recovery_operator(operator)


def create_fiber_frame_nonlinear_engineering_result_ir(
    *,
    engineering_result_id: str,
    source_adapter: FiberFrameNonlinearNumericalResultAdapter,
    recovery_operator: FiberFrameNonlinearRecoveryOperator | None = None,
) -> FiberFrameNonlinearEngineeringResultIR:
    """Promote exact bounded reaction/member/section/fiber recovery authority."""

    adapter = validate_fiber_frame_nonlinear_numerical_result_adapter(source_adapter)
    operator = (
        create_fiber_frame_nonlinear_recovery_operator(adapter)
        if recovery_operator is None
        else validate_fiber_frame_nonlinear_recovery_operator(recovery_operator)
    )
    if operator._source_adapter is not adapter:
        _fail(
            "fiber_frame_engineering_result_source_identity_mismatch",
            "/source",
            "Recovery operator and engineering result must retain one source adapter.",
        )
    source = adapter.source_binding
    result = adapter.numerical_result
    provisional = FiberFrameNonlinearEngineeringResultIR(
        schema_version=FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_SCHEMA_VERSION,
        engineering_result_id=_stable_id(
            engineering_result_id,
            "/engineering_result_id",
        ),
        engineering_result_hash=_HASH_ZERO,
        result_kind=FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_KIND,
        authority_profile=(FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_AUTHORITY_PROFILE),
        source_numerical_result_schema_version=result.schema_version,
        source_numerical_result_hash=result.result_hash,
        source_result_adapter_hash=adapter.adapter_hash,
        recovery_operator_hash=operator.recovery_operator_hash,
        problem_contract_hash=source.problem_contract_hash,
        model_ir_content_hash=source.model_ir_content_hash,
        execution_topology_plan_hash=source.execution_topology_plan_hash,
        terminal_kinematic_state_hash=source.terminal_kinematic_state_hash,
        terminal_material_state_bundle_hash=(
            source.terminal_material_state_bundle_hash
        ),
        terminal_epoch=source.terminal_epoch,
        load_factor=source.terminal_load_factor,
        physical_dof_count=source.physical_dof_count,
        member_count=operator.member_count,
        integration_point_count=operator.integration_point_count,
        fiber_output_count=operator.fiber_output_count,
        authored_reaction_count=operator.authored_reaction_count,
        free_residual_scaled_linf=operator.free_residual_scaled_linf,
        total_dissipated_energy_mj=operator.total_dissipated_energy_mj,
        array_bundle_hash=operator.array_bundle_hash,
        descriptors=operator.descriptors,
        extensions=MappingProxyType({}),
        _source_adapter=adapter,
        _recovery_operator=operator,
    )
    result_ir = replace(
        provisional,
        engineering_result_hash=canonical_hash(
            _result_payload(provisional, include_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_engineering_result_ir(result_ir)


def _build_recovery_operator(
    adapter: FiberFrameNonlinearNumericalResultAdapter,
) -> FiberFrameNonlinearRecoveryOperator:
    replay = _replay_terminal_engineering_outputs(adapter)
    bindings = replay.bindings
    orders = replay.orders
    counts = replay.counts
    metrics = replay.metrics
    provisional = FiberFrameNonlinearRecoveryOperator(
        schema_version=FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_SCHEMA_VERSION,
        recovery_operator_hash=_HASH_ZERO,
        profile=FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE,
        authority_profile=FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_AUTHORITY_PROFILE,
        problem_contract_hash=bindings["problem_contract_hash"],
        model_ir_content_hash=bindings["model_ir_content_hash"],
        case_id=bindings["case_id"],
        source_result_adapter_hash=bindings["source_result_adapter_hash"],
        source_binding_hash=bindings["source_binding_hash"],
        source_numerical_result_hash=bindings["source_numerical_result_hash"],
        execution_topology_plan_hash=bindings["execution_topology_plan_hash"],
        physical_equation_scaling_binding_hash=bindings[
            "physical_equation_scaling_binding_hash"
        ],
        execution_state_binding_hash=bindings["execution_state_binding_hash"],
        checkpoint_chain_hash=bindings["checkpoint_chain_hash"],
        terminal_checkpoint_state_hash=bindings["terminal_checkpoint_state_hash"],
        terminal_kinematic_state_hash=bindings["terminal_kinematic_state_hash"],
        terminal_material_state_bundle_hash=bindings[
            "terminal_material_state_bundle_hash"
        ],
        terminal_receipt_hash=bindings["terminal_receipt_hash"],
        geometry_hash=orders["geometry_hash"],
        member_order_hash=orders["member_order_hash"],
        integration_point_output_order_hash=orders[
            "integration_point_output_order_hash"
        ],
        fiber_output_order_hash=orders["fiber_output_order_hash"],
        constituent_state_replay_hash=orders["constituent_state_replay_hash"],
        recovery_law_hash=orders["recovery_law_hash"],
        terminal_epoch=counts["terminal_epoch"],
        terminal_load_factor=float(bindings["terminal_load_factor"]),
        physical_dof_count=counts["physical_dof_count"],
        member_count=counts["member_count"],
        integration_point_count=counts["integration_point_count"],
        fiber_output_count=counts["fiber_output_count"],
        authored_reaction_count=counts["authored_reaction_count"],
        free_residual_scaled_linf=float(metrics["free_residual_scaled_linf"]),
        element_scatter_scaled_linf=float(metrics["element_scatter_scaled_linf"]),
        local_global_force_scaled_linf=float(metrics["local_global_force_scaled_linf"]),
        section_integration_scaled_linf=float(
            metrics["section_integration_scaled_linf"]
        ),
        section_resultant_scaled_linf=float(metrics["section_resultant_scaled_linf"]),
        fiber_strain_linf=float(metrics["fiber_strain_linf"]),
        local_global_work_scaled_abs=float(metrics["local_global_work_scaled_abs"]),
        section_element_work_scaled_abs=float(
            metrics["section_element_work_scaled_abs"]
        ),
        dissipated_energy_balance_scaled_abs=float(
            metrics["dissipated_energy_balance_scaled_abs"]
        ),
        total_dissipated_energy_mj=float(metrics["total_dissipated_energy_mj"]),
        transformation_orthogonality_linf=float(
            metrics["transformation_orthogonality_linf"]
        ),
        state_bytes_exact=bool(metrics["state_bytes_exact"]),
        array_bundle_hash=replay.array_bundle_hash,
        descriptors=replay.descriptors,
        extensions=MappingProxyType({}),
        _arrays=replay.arrays,
        _source_adapter=adapter,
    )
    operator = replace(
        provisional,
        recovery_operator_hash=canonical_hash(
            _operator_payload(provisional, include_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_recovery_operator_shape(operator)


def _replay_terminal_engineering_outputs(
    adapter: FiberFrameNonlinearNumericalResultAdapter,
) -> _RecoveryReplay:
    source = adapter.source_binding
    problem: StatefulFiberFrame2DProblem = source._problem
    plan: FiberFrameNonlinearExecutionTopologyPlan = source._topology_plan
    checkpoint_chain = source._checkpoint_chain
    kinematic_chain = source._kinematic_chain
    terminal_projection = source._material_chain.projections[-1]
    terminal_bundle = validate_material_state_bundle(terminal_projection.bundle)

    if len(checkpoint_chain.checkpoints) < 2:
        _fail(
            "fiber_frame_recovery_terminal_parent_missing",
            "/source/checkpoint_chain",
            "Exact recovery requires a positive-epoch terminal checkpoint.",
        )
    parent_checkpoint = checkpoint_chain.checkpoints[-2]
    terminal_checkpoint = checkpoint_chain.checkpoints[-1]
    terminal_state = kinematic_chain.committed_states[-1]
    free_solver_dofs = np.asarray(plan.array("free_solver_dofs"), dtype=np.int64)
    problem_free_dofs = np.asarray(problem.free_global_dofs, dtype=np.int64)
    if not np.array_equal(free_solver_dofs, problem_free_dofs):
        _fail(
            "fiber_frame_recovery_free_order_mismatch",
            "/source/execution_topology/free_solver_dofs",
            "J1 free solver order differs from the source frame free order.",
        )
    solver_generalized = terminal_state.array("solver_generalized_coordinates_m")
    replay = assemble_stateful_fiber_frame2d(
        problem,
        parent_checkpoint,
        target_load_factor=source.terminal_load_factor,
        trial_free_coordinates_m=solver_generalized[free_solver_dofs],
    )
    _require_exact_array(
        replay.generalized_coordinates_m,
        solver_generalized,
        "/replay/generalized_coordinates_m",
    )
    _require_exact_array(
        replay.global_displacements,
        np.asarray(terminal_checkpoint.global_displacements, dtype=np.float64),
        "/replay/global_displacements",
    )
    if (
        replay.parent_checkpoint_hash != parent_checkpoint.state_hash
        or terminal_checkpoint.parent_state_hash != parent_checkpoint.state_hash
        or replay.target_load_factor != terminal_checkpoint.load_factor
    ):
        _fail(
            "fiber_frame_recovery_terminal_transition_mismatch",
            "/replay",
            "Replayed transition does not retain the exact terminal parent/load.",
        )

    member_dofs: list[tuple[int, ...]] = []
    transformations: list[np.ndarray] = []
    local_displacements: list[np.ndarray] = []
    local_end_forces_si: list[np.ndarray] = []
    global_end_forces_si: list[np.ndarray] = []
    integration_point_offsets = [0]
    integration_point_xi: list[float] = []
    integration_point_weights: list[float] = []
    generalized_strains: list[np.ndarray] = []
    section_resultants_si: list[np.ndarray] = []
    section_dissipated_energy: list[float] = []
    fiber_offsets = [0]
    fiber_y_m: list[float] = []
    fiber_area_m2: list[float] = []
    fiber_strain: list[float] = []
    fiber_stress_mpa: list[float] = []
    fiber_dissipated_energy: list[float] = []
    member_order_rows: list[dict[str, Any]] = []
    integration_point_order_rows: list[dict[str, Any]] = []
    fiber_order_rows: list[dict[str, Any]] = []
    constituent_rows: list[dict[str, Any]] = []

    manual_internal_source = np.zeros(problem.global_dof_count, dtype=np.float64)
    element_scatter_reference = np.zeros(
        problem.global_dof_count,
        dtype=np.float64,
    )
    section_integration_error = 0.0
    section_integration_scale = 1.0
    section_resultant_error = 0.0
    section_resultant_scale = 1.0
    local_global_force_error = 0.0
    local_global_force_scale = 1.0
    fiber_strain_error = 0.0
    local_global_work_error = 0.0
    local_global_work_scale = 1.0
    section_element_work_error = 0.0
    section_element_work_scale = 1.0
    energy_error = 0.0
    energy_scale = 1.0
    transformation_error = 0.0
    total_dissipated_energy_mj = 0.0
    bundle_index = 0

    for member_index, (member, member_assembly, terminal_element_state) in enumerate(
        zip(
            problem.members,
            replay.member_assemblies,
            terminal_checkpoint.element_states,
            strict=True,
        )
    ):
        response = member_assembly.response
        if (
            response.state.state_hash != terminal_element_state.state_hash
            or response.state.canonical_bytes()
            != terminal_element_state.canonical_bytes()
        ):
            _fail(
                "fiber_frame_recovery_terminal_element_state_mismatch",
                f"/replay/members/{member_index}/state",
                "Replayed element state bytes differ from the terminal checkpoint.",
            )
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            _fail(
                "fiber_frame_recovery_section_type_unsupported",
                f"/source/problem/members/{member_index}/section",
                "Recovery v1 supports exact StatefulRCFiberSection only.",
            )
        global_dofs = tuple(int(value) for value in member_assembly.global_dofs)
        transformation = np.asarray(
            member_assembly.transformation_global_to_local,
            dtype=np.float64,
        )
        global_member_displacement = replay.global_displacements[list(global_dofs)]
        local_displacement = transformation @ global_member_displacement
        _require_exact_array(
            local_displacement,
            response.local_displacements,
            f"/replay/members/{member_index}/local_displacement",
        )
        transformation_error = max(
            transformation_error,
            _linf(transformation @ transformation.T - np.eye(6)),
        )
        member_order_rows.append(
            {
                "member_index": member_index,
                "member_id": member.member_id,
                "node_i": member.node_i,
                "node_j": member.node_j,
                "element_contract_hash": member.element.contract_hash,
                "global_dofs_source_3dof": list(global_dofs),
            }
        )
        member_dofs.append(global_dofs)
        transformations.append(transformation)
        local_displacements.append(local_displacement)

        manual_local_force = np.zeros(6, dtype=np.float64)
        member_section_work = 0.0
        member_fiber_energy = 0.0
        points, weights = member.element.quadrature
        jacobian = 0.5 * member.element.length_m
        if len(points) != len(response.section_responses) or len(points) != len(
            terminal_element_state.integration_point_states
        ):
            _fail(
                "fiber_frame_recovery_integration_point_count_mismatch",
                f"/replay/members/{member_index}/integration_points",
                "Quadrature, response, and committed-state orders differ.",
            )

        for integration_point_index, (
            xi,
            weight,
            section_response,
            terminal_section_state,
        ) in enumerate(
            zip(
                points,
                weights,
                response.section_responses,
                terminal_element_state.integration_point_states,
                strict=True,
            )
        ):
            if type(section_response) is not StatefulFiberSectionResponse:
                _fail(
                    "fiber_frame_recovery_section_response_type_unsupported",
                    (
                        f"/replay/members/{member_index}/integration_points/"
                        f"{integration_point_index}"
                    ),
                    "Recovery v1 requires exact StatefulFiberSectionResponse.",
                )
            if (
                section_response.state.state_hash != terminal_section_state.state_hash
                or section_response.state.canonical_bytes()
                != terminal_section_state.canonical_bytes()
            ):
                _fail(
                    "fiber_frame_recovery_terminal_section_state_mismatch",
                    (
                        f"/replay/members/{member_index}/integration_points/"
                        f"{integration_point_index}/state"
                    ),
                    "Replayed section state bytes differ from the checkpoint.",
                )
            strain_displacement = member.element.strain_displacement_matrix(xi)
            manual_generalized = strain_displacement @ local_displacement
            response_generalized = np.asarray(
                [
                    section_response.axial_strain,
                    section_response.curvature_z_per_m,
                ],
                dtype=np.float64,
            )
            _require_exact_array(
                manual_generalized,
                response_generalized,
                (
                    f"/replay/members/{member_index}/integration_points/"
                    f"{integration_point_index}/generalized_strain"
                ),
            )

            areas = np.asarray(
                [fiber.area_m2 for fiber in section.fibers],
                dtype=np.float64,
            )
            y_values = np.asarray(
                [fiber.y_m for fiber in section.fibers],
                dtype=np.float64,
            )
            response_fiber_strains = np.asarray(
                [row.total_strain for row in section_response.fiber_responses],
                dtype=np.float64,
            )
            stresses = np.asarray(
                [row.stress_mpa for row in section_response.fiber_responses],
                dtype=np.float64,
            )
            _require_exact_array(
                response_fiber_strains,
                section_response.fiber_strains,
                (
                    f"/replay/members/{member_index}/integration_points/"
                    f"{integration_point_index}/fiber_strains"
                ),
            )
            _require_exact_array(
                stresses,
                section_response.fiber_stresses_mpa,
                (
                    f"/replay/members/{member_index}/integration_points/"
                    f"{integration_point_index}/fiber_stresses_mpa"
                ),
            )
            manual_fiber_strains = (
                manual_generalized[0] - manual_generalized[1] * y_values
            )
            fiber_strain_error = max(
                fiber_strain_error,
                _linf(manual_fiber_strains - response_fiber_strains),
            )
            forces_kn = stresses * areas * FIBER_FRAME_FORCE_TO_SI
            manual_resultant_kn = np.asarray(
                [
                    math.fsum(float(value) for value in forces_kn),
                    -math.fsum(
                        float(force * y)
                        for force, y in zip(forces_kn, y_values, strict=True)
                    ),
                ],
                dtype=np.float64,
            )
            response_resultant_kn = np.asarray(
                section_response.resultants,
                dtype=np.float64,
            )
            section_integration_error = max(
                section_integration_error,
                _linf(manual_resultant_kn - response_resultant_kn),
            )
            section_integration_scale = max(
                section_integration_scale,
                _linf(manual_resultant_kn),
                _linf(response_resultant_kn),
            )
            factor = float(weight) * jacobian
            manual_local_force += (strain_displacement.T @ manual_resultant_kn) * factor
            member_section_work += (
                float(np.dot(manual_generalized, manual_resultant_kn)) * factor
            )

            integration_point_order_rows.append(
                {
                    "member_index": member_index,
                    "member_id": member.member_id,
                    "integration_point_index": integration_point_index,
                    "integration_point_xi": float(xi),
                    "integration_point_weight": float(weight),
                    "section_id": section.section_id,
                    "section_contract_hash": section.contract_hash,
                }
            )
            integration_point_xi.append(float(xi))
            integration_point_weights.append(float(weight))
            generalized_strains.append(manual_generalized)
            section_resultants_si.append(manual_resultant_kn * 1000.0)

            section_energy = 0.0
            for fiber_index, (
                fiber,
                fiber_response,
                replayed_fiber_state,
                terminal_fiber_state,
                strain,
                stress,
            ) in enumerate(
                zip(
                    section.fibers,
                    section_response.fiber_responses,
                    section_response.state.fiber_states,
                    terminal_section_state.fiber_states,
                    manual_fiber_strains,
                    stresses,
                    strict=True,
                )
            ):
                if fiber.material_kind == "steel":
                    expected_type = UniaxialPlasticityState
                    material_type_id = section.steel.material_id
                    material_schema_version = STEEL_PLASTICITY_STATE_SCHEMA_VERSION
                else:
                    expected_type = ConcreteDamageState
                    material_type_id = section.concrete.material_id
                    material_schema_version = CONCRETE_DAMAGE_STATE_SCHEMA_VERSION
                if (
                    type(replayed_fiber_state) is not expected_type
                    or type(terminal_fiber_state) is not expected_type
                ):
                    _fail(
                        "fiber_frame_recovery_constituent_type_mismatch",
                        (
                            f"/replay/members/{member_index}/integration_points/"
                            f"{integration_point_index}/fibers/{fiber_index}"
                        ),
                        "Replayed and committed constituent types must be exact.",
                    )
                state_bytes = replayed_fiber_state.canonical_bytes()
                if (
                    fiber_response.state.canonical_bytes() != state_bytes
                    or fiber_response.state.state_hash
                    != replayed_fiber_state.state_hash
                    or state_bytes != terminal_fiber_state.canonical_bytes()
                    or replayed_fiber_state.state_hash
                    != terminal_fiber_state.state_hash
                ):
                    _fail(
                        "fiber_frame_recovery_constituent_state_bytes_mismatch",
                        (
                            f"/replay/members/{member_index}/integration_points/"
                            f"{integration_point_index}/fibers/{fiber_index}"
                        ),
                        "Replayed constituent bytes differ from the checkpoint.",
                    )
                if bundle_index >= terminal_bundle.entry_count:
                    _fail(
                        "fiber_frame_recovery_material_bundle_count_mismatch",
                        "/source/material_state_bundle/entries",
                        "Terminal material bundle ended before replayed fibers.",
                    )
                descriptor = terminal_bundle.entries[bundle_index]
                expected_entity_id = f"member.{member_index:04d}"
                expected_ip_id = (
                    f"ip.{integration_point_index:04d}.fiber.{fiber_index:04d}"
                )
                if (
                    descriptor.index != bundle_index
                    or descriptor.entity_id != expected_entity_id
                    or descriptor.integration_point_id != expected_ip_id
                    or descriptor.material_type_id != material_type_id
                    or descriptor.material_schema_version != material_schema_version
                    or descriptor.data_hash != replayed_fiber_state.state_hash
                    or terminal_bundle.state_bytes(bundle_index) != state_bytes
                ):
                    _fail(
                        "fiber_frame_recovery_material_bundle_entry_mismatch",
                        f"/source/material_state_bundle/entries/{bundle_index}",
                        "Terminal bundle identity or bytes differ from replay.",
                    )
                energy_density = float(
                    replayed_fiber_state.dissipated_energy_density_mj_per_m3
                )
                section_energy += fiber.area_m2 * energy_density
                fiber_y_m.append(float(fiber.y_m))
                fiber_area_m2.append(float(fiber.area_m2))
                fiber_strain.append(float(strain))
                fiber_stress_mpa.append(float(stress))
                fiber_dissipated_energy.append(energy_density)
                fiber_order_rows.append(
                    {
                        "member_index": member_index,
                        "member_id": member.member_id,
                        "element_contract_hash": member.element.contract_hash,
                        "integration_point_index": integration_point_index,
                        "integration_point_xi": float(xi),
                        "section_id": section.section_id,
                        "section_contract_hash": section.contract_hash,
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "fiber_y_m": fiber.y_m,
                        "fiber_area_m2": fiber.area_m2,
                        "material_kind": fiber.material_kind,
                        "material_type_id": material_type_id,
                        "material_schema_version": material_schema_version,
                    }
                )
                constituent_rows.append(
                    {
                        "index": bundle_index,
                        "data_hash": descriptor.data_hash,
                        "content_hash": descriptor.content_hash,
                        "state_hash": replayed_fiber_state.state_hash,
                    }
                )
                bundle_index += 1
            fiber_offsets.append(len(fiber_y_m))
            section_dissipated_energy.append(section_energy)
            member_fiber_energy += section_energy * factor
            energy_error = max(
                energy_error,
                abs(section_energy - section_response.dissipated_energy_mj_per_m),
            )
            energy_scale = max(
                energy_scale,
                abs(section_energy),
                abs(section_response.dissipated_energy_mj_per_m),
            )

        integration_point_offsets.append(len(integration_point_xi))
        response_local = np.asarray(response.internal_force_local, dtype=np.float64)
        section_resultant_error = max(
            section_resultant_error,
            _linf(manual_local_force - response_local),
        )
        section_resultant_scale = max(
            section_resultant_scale,
            _linf(manual_local_force),
            _linf(response_local),
        )
        manual_global_force = transformation.T @ manual_local_force
        response_global_force = np.asarray(
            member_assembly.internal_load_global,
            dtype=np.float64,
        )
        local_global_force_error = max(
            local_global_force_error,
            _linf(manual_global_force - response_global_force),
        )
        local_global_force_scale = max(
            local_global_force_scale,
            _linf(manual_global_force),
            _linf(response_global_force),
        )
        manual_internal_source[list(global_dofs)] += manual_global_force
        element_scatter_reference[list(global_dofs)] += response_global_force
        local_work = float(np.dot(local_displacement, manual_local_force))
        global_work = float(np.dot(global_member_displacement, manual_global_force))
        local_global_work_error = max(
            local_global_work_error,
            abs(local_work - global_work),
        )
        local_global_work_scale = max(
            local_global_work_scale,
            abs(local_work),
            abs(global_work),
        )
        section_element_work_error = max(
            section_element_work_error,
            abs(member_section_work - local_work),
        )
        section_element_work_scale = max(
            section_element_work_scale,
            abs(member_section_work),
            abs(local_work),
        )
        energy_error = max(
            energy_error,
            abs(member_fiber_energy - response.dissipated_energy_mj),
        )
        energy_scale = max(
            energy_scale,
            abs(member_fiber_energy),
            abs(response.dissipated_energy_mj),
        )
        total_dissipated_energy_mj += member_fiber_energy
        local_end_forces_si.append(manual_local_force * 1000.0)
        global_end_forces_si.append(manual_global_force * 1000.0)

    if bundle_index != terminal_bundle.entry_count:
        _fail(
            "fiber_frame_recovery_material_bundle_count_mismatch",
            "/source/material_state_bundle/entries",
            "Replayed fiber count differs from the terminal material bundle.",
        )
    fiber_output_order_hash = canonical_hash(fiber_order_rows)
    if fiber_output_order_hash != terminal_projection.receipt.source_identity_hash:
        _fail(
            "fiber_frame_recovery_fiber_output_order_mismatch",
            "/orders/fiber_output_order_hash",
            "Replayed fiber order differs from the J4 material projection.",
        )

    element_scatter_error = _linf(
        manual_internal_source
        - np.asarray(replay.internal_loads_global, dtype=np.float64)
    )
    element_scatter_error = max(
        element_scatter_error,
        _linf(
            element_scatter_reference
            - np.asarray(replay.internal_loads_global, dtype=np.float64)
        ),
    )
    element_scatter_scale = max(
        1.0,
        _linf(manual_internal_source),
        _linf(replay.internal_loads_global),
    )
    internal_si = _source_force_to_canonical_si(plan, manual_internal_source)
    external_si = _source_force_to_canonical_si(plan, replay.external_loads_global)
    residual_si = immutable_array(internal_si - external_si, dtype="<f8")
    reaction_si_values = np.zeros(plan.physical_dof_count, dtype=np.float64)
    authored_fixed = np.asarray(
        plan.array("authored_fixed_physical_dofs"),
        dtype=np.int64,
    )
    reaction_si_values[authored_fixed] = residual_si[authored_fixed]
    reaction_si = immutable_array(reaction_si_values, dtype="<f8")
    free_physical = np.asarray(plan.array("free_physical_dofs"), dtype=np.int64)
    scaled_residual = residual_si / source._physical_scaling.scale_divisors_si
    free_residual_scaled_linf = _linf(scaled_residual[free_physical])
    if not math.isclose(
        free_residual_scaled_linf,
        source.full_residual_receipt.scaled_residual_linf,
        rel_tol=0.0,
        abs_tol=FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
    ):
        _fail(
            "fiber_frame_recovery_j5_residual_mismatch",
            "/metrics/free_residual_scaled_linf",
            "Independent terminal residual differs from the J5 receipt.",
        )

    arrays = _freeze_arrays(
        {
            "member_global_dofs_source_3dof": member_dofs,
            "member_transformation_global_to_local": transformations,
            "member_local_displacement": local_displacements,
            "member_local_end_force_si": local_end_forces_si,
            "member_global_end_force_si": global_end_forces_si,
            "internal_load_global_si": internal_si,
            "external_load_global_si": external_si,
            "equilibrium_residual_global_si": residual_si,
            "reaction_global_si": reaction_si,
            "integration_point_offsets": integration_point_offsets,
            "integration_point_xi": integration_point_xi,
            "integration_point_weights": integration_point_weights,
            "section_generalized_strain": generalized_strains,
            "section_resultant_si": section_resultants_si,
            "section_dissipated_energy_mj_per_m": (section_dissipated_energy),
            "fiber_offsets": fiber_offsets,
            "fiber_y_m": fiber_y_m,
            "fiber_area_m2": fiber_area_m2,
            "fiber_strain": fiber_strain,
            "fiber_stress_mpa": fiber_stress_mpa,
            "fiber_dissipated_energy_density_mj_per_m3": (fiber_dissipated_energy),
        }
    )
    member_order_hash = canonical_hash(member_order_rows)
    integration_point_output_order_hash = canonical_hash(integration_point_order_rows)
    geometry_hash = _geometry_hash(problem)
    constituent_state_replay_hash = canonical_hash(
        {
            "terminal_material_state_bundle_hash": terminal_bundle.bundle_hash,
            "integration_point_order_hash": (
                terminal_bundle.integration_point_order_hash
            ),
            "fiber_output_order_hash": fiber_output_order_hash,
            "entries": constituent_rows,
        }
    )
    recovery_law_hash = _recovery_law_hash()
    order_hashes = {
        "member_order": member_order_hash,
        "physical_equation_order": source._physical_scaling.equation_order_hash,
        "integration_point_order": integration_point_output_order_hash,
        "fiber_output_order": fiber_output_order_hash,
    }
    descriptors = tuple(
        _recovery_array_descriptor(
            name,
            arrays[name],
            order_hash=order_hashes[_ARRAY_SPEC_BY_NAME[name][4]],
            source_numerical_result_hash=adapter.numerical_result.result_hash,
        )
        for name in _ARRAY_NAMES
    )
    array_bundle_hash = _array_bundle_hash(
        descriptors,
        adapter.numerical_result.result_hash,
    )
    metrics: dict[str, float | bool] = {
        "free_residual_scaled_linf": free_residual_scaled_linf,
        "element_scatter_scaled_linf": (element_scatter_error / element_scatter_scale),
        "local_global_force_scaled_linf": (
            local_global_force_error / local_global_force_scale
        ),
        "section_integration_scaled_linf": (
            section_integration_error / section_integration_scale
        ),
        "section_resultant_scaled_linf": (
            section_resultant_error / section_resultant_scale
        ),
        "fiber_strain_linf": fiber_strain_error,
        "local_global_work_scaled_abs": (
            local_global_work_error / local_global_work_scale
        ),
        "section_element_work_scaled_abs": (
            section_element_work_error / section_element_work_scale
        ),
        "dissipated_energy_balance_scaled_abs": energy_error / energy_scale,
        "total_dissipated_energy_mj": total_dissipated_energy_mj,
        "transformation_orthogonality_linf": transformation_error,
        "state_bytes_exact": True,
    }
    _require_recovery_gates(metrics, source.solver_residual_tolerance)
    return _RecoveryReplay(
        bindings=MappingProxyType(
            {
                "problem_contract_hash": source.problem_contract_hash,
                "model_ir_content_hash": source.model_ir_content_hash,
                "case_id": source.case_id,
                "source_result_adapter_hash": adapter.adapter_hash,
                "source_binding_hash": source.binding_hash,
                "source_numerical_result_hash": (adapter.numerical_result.result_hash),
                "execution_topology_plan_hash": (source.execution_topology_plan_hash),
                "physical_equation_scaling_binding_hash": (
                    source.physical_equation_scaling_binding_hash
                ),
                "execution_state_binding_hash": (source.execution_state_binding_hash),
                "checkpoint_chain_hash": source.checkpoint_chain_hash,
                "terminal_checkpoint_state_hash": (
                    source.terminal_checkpoint_state_hash
                ),
                "terminal_kinematic_state_hash": (source.terminal_kinematic_state_hash),
                "terminal_material_state_bundle_hash": (
                    source.terminal_material_state_bundle_hash
                ),
                "terminal_receipt_hash": source.terminal_receipt_hash,
                "terminal_load_factor": source.terminal_load_factor,
            }
        ),
        orders=MappingProxyType(
            {
                "geometry_hash": geometry_hash,
                "member_order_hash": member_order_hash,
                "integration_point_output_order_hash": (
                    integration_point_output_order_hash
                ),
                "fiber_output_order_hash": fiber_output_order_hash,
                "constituent_state_replay_hash": (constituent_state_replay_hash),
                "recovery_law_hash": recovery_law_hash,
            }
        ),
        counts=MappingProxyType(
            {
                "terminal_epoch": source.terminal_epoch,
                "physical_dof_count": plan.physical_dof_count,
                "member_count": len(problem.members),
                "integration_point_count": len(integration_point_xi),
                "fiber_output_count": len(fiber_y_m),
                "authored_reaction_count": int(authored_fixed.size),
            }
        ),
        metrics=MappingProxyType(metrics),
        arrays=arrays,
        descriptors=descriptors,
        array_bundle_hash=array_bundle_hash,
    )


def _geometry_hash(problem: StatefulFiberFrame2DProblem) -> str:
    return canonical_hash(
        {
            "problem_contract_hash": problem.contract_hash,
            "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
            "node_coordinates_m": [list(row) for row in problem.node_coordinates_m],
            "members": [
                {
                    "member_index": index,
                    "member_id": member.member_id,
                    "node_i": member.node_i,
                    "node_j": member.node_j,
                    "length_m": member.element.length_m,
                    "element_contract_hash": member.element.contract_hash,
                }
                for index, member in enumerate(problem.members)
            ],
        }
    )


def _recovery_law_hash() -> str:
    return canonical_hash(
        {
            "profile": FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE,
            "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
            "beam_kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
            "beam_internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
            "beam_tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
            "section_strain_relation": FIBER_SECTION_STRAIN_RELATION,
            "section_resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
            "section_tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
            "residual_formula": RESIDUAL_FORMULA,
            "force_to_si": FIBER_FRAME_FORCE_TO_SI,
            "moment_to_si": FIBER_FRAME_MOMENT_TO_SI,
            "member_force_order": FIBER_FRAME_NONLINEAR_MEMBER_FORCE_ORDER,
            "section_resultant_order": (FIBER_FRAME_NONLINEAR_SECTION_RESULTANT_ORDER),
            "fiber_output_order": FIBER_FRAME_NONLINEAR_FIBER_OUTPUT_ORDER,
        }
    )


def _source_force_to_canonical_si(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    source_force: Any,
) -> np.ndarray:
    canonical = physical_3dof_to_canonical_6dof(plan, source_force)
    values = np.asarray(canonical, dtype=np.float64).reshape((-1, 6)).copy()
    values[:, :3] *= FIBER_FRAME_FORCE_TO_SI
    values[:, 3:] *= FIBER_FRAME_MOMENT_TO_SI
    return immutable_array(values.reshape(-1), dtype="<f8")


def _freeze_arrays(values: Mapping[str, Any]) -> Mapping[str, np.ndarray]:
    if set(values) != set(_ARRAY_NAMES):
        _fail(
            "fiber_frame_recovery_array_set_invalid",
            "/arrays",
            "Recovery array set is incomplete or contains unknown names.",
        )
    arrays: dict[str, np.ndarray] = {}
    for name, dtype, rank, *_ in _ARRAY_SPECS:
        try:
            array = immutable_array(values[name], dtype=dtype)
        except (TypeError, ValueError, OverflowError) as exc:
            raise FiberFrameNonlinearRecoveryError(
                "fiber_frame_recovery_array_invalid",
                f"/arrays/{name}",
                "Recovery array cannot be represented canonically.",
            ) from exc
        if array.ndim != rank:
            _fail(
                "fiber_frame_recovery_array_rank_invalid",
                f"/arrays/{name}",
                f"Expected rank {rank}.",
            )
        arrays[name] = array
    return MappingProxyType(arrays)


def _recovery_array_descriptor(
    name: str,
    array: np.ndarray,
    *,
    order_hash: str,
    source_numerical_result_hash: str,
) -> FiberFrameNonlinearRecoveryArrayDescriptor:
    spec = _ARRAY_SPEC_BY_NAME[name]
    digest = source_numerical_result_hash.split(":", 1)[1]
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_order": "little",
        "byte_length": int(array.nbytes),
        "unit_profile": spec[3],
        "equation_scope": spec[4],
        "authority_role": spec[5],
        "order_hash": order_hash,
        "data_hash": array_data_hash(array),
        "artifact_uri": (
            f"artifact://stateful-fiber-frame2d-nonlinear-recovery/{digest}/{name}.bin"
        ),
    }
    return FiberFrameNonlinearRecoveryArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_order="little",
        byte_length=int(array.nbytes),
        unit_profile=spec[3],
        equation_scope=spec[4],
        authority_role=spec[5],
        order_hash=order_hash,
        data_hash=metadata["data_hash"],
        content_hash=canonical_hash(metadata),
        artifact_uri=metadata["artifact_uri"],
    )


def _array_bundle_hash(
    descriptors: tuple[FiberFrameNonlinearRecoveryArrayDescriptor, ...],
    source_numerical_result_hash: str,
) -> str:
    return canonical_hash(
        {
            "storage_profile": FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE,
            "source_numerical_result_hash": source_numerical_result_hash,
            "array_descriptors": [row.to_dict() for row in descriptors],
        }
    )


def _require_recovery_gates(
    metrics: Mapping[str, float | bool],
    source_residual_tolerance: float,
) -> None:
    checks = (
        (
            "free_residual_scaled_linf",
            source_residual_tolerance,
        ),
        (
            "element_scatter_scaled_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "local_global_force_scaled_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "section_integration_scaled_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "section_resultant_scaled_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "fiber_strain_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_FIBER_STRAIN_TOLERANCE,
        ),
        (
            "local_global_work_scaled_abs",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "section_element_work_scaled_abs",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "dissipated_energy_balance_scaled_abs",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
        (
            "transformation_orthogonality_linf",
            FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
        ),
    )
    for name, tolerance in checks:
        value = _nonnegative_float(metrics[name], f"/metrics/{name}")
        if value > tolerance:
            _fail(
                "fiber_frame_recovery_consistency_gate_failed",
                f"/metrics/{name}",
                f"Recovery metric exceeds fixed tolerance {tolerance}.",
            )
    _nonnegative_float(
        metrics["total_dissipated_energy_mj"],
        "/metrics/total_dissipated_energy_mj",
    )
    if metrics["state_bytes_exact"] is not True:
        _fail(
            "fiber_frame_recovery_state_bytes_gate_failed",
            "/metrics/state_bytes_exact",
            "All terminal constituent state bytes must replay exactly.",
        )


def _require_exact_array(actual: Any, expected: Any, path: str) -> None:
    if not np.array_equal(
        np.asarray(actual, dtype=np.float64),
        np.asarray(expected, dtype=np.float64),
    ):
        _fail(
            "fiber_frame_recovery_exact_array_mismatch",
            path,
            "Replayed canonical values differ at the binary float level.",
        )


def _linf(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    return 0.0 if array.size == 0 else float(np.linalg.norm(array, ord=np.inf))


def _operator_payload(
    operator: FiberFrameNonlinearRecoveryOperator,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    source_tolerance = operator._source_adapter.source_binding.solver_residual_tolerance
    payload = {
        "schema_version": operator.schema_version,
        "recovery_operator_hash": operator.recovery_operator_hash,
        "profile": operator.profile,
        "authority_profile": operator.authority_profile,
        "storage_profile": FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE,
        "bindings": {
            "problem_contract_hash": operator.problem_contract_hash,
            "model_ir_content_hash": operator.model_ir_content_hash,
            "case_id": operator.case_id,
            "source_result_adapter_hash": operator.source_result_adapter_hash,
            "source_binding_hash": operator.source_binding_hash,
            "source_numerical_result_hash": operator.source_numerical_result_hash,
            "execution_topology_plan_hash": (operator.execution_topology_plan_hash),
            "physical_equation_scaling_binding_hash": (
                operator.physical_equation_scaling_binding_hash
            ),
            "execution_state_binding_hash": operator.execution_state_binding_hash,
            "checkpoint_chain_hash": operator.checkpoint_chain_hash,
            "terminal_checkpoint_state_hash": (operator.terminal_checkpoint_state_hash),
            "terminal_kinematic_state_hash": operator.terminal_kinematic_state_hash,
            "terminal_material_state_bundle_hash": (
                operator.terminal_material_state_bundle_hash
            ),
            "terminal_receipt_hash": operator.terminal_receipt_hash,
            "terminal_load_factor": operator.terminal_load_factor,
        },
        "formulations": {
            "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
            "beam_kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
            "beam_internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
            "beam_tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
            "section_strain_relation": FIBER_SECTION_STRAIN_RELATION,
            "section_resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
            "section_tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
            "residual_formula": RESIDUAL_FORMULA,
            "source_force_to_si": FIBER_FRAME_FORCE_TO_SI,
            "source_moment_to_si": FIBER_FRAME_MOMENT_TO_SI,
        },
        "orders": {
            "member_force_order": FIBER_FRAME_NONLINEAR_MEMBER_FORCE_ORDER,
            "section_resultant_order": (FIBER_FRAME_NONLINEAR_SECTION_RESULTANT_ORDER),
            "fiber_output_order": FIBER_FRAME_NONLINEAR_FIBER_OUTPUT_ORDER,
            "geometry_hash": operator.geometry_hash,
            "member_order_hash": operator.member_order_hash,
            "physical_equation_order_hash": (
                operator._source_adapter.source_binding._physical_scaling.equation_order_hash
            ),
            "integration_point_output_order_hash": (
                operator.integration_point_output_order_hash
            ),
            "fiber_output_order_hash": operator.fiber_output_order_hash,
            "constituent_state_replay_hash": (operator.constituent_state_replay_hash),
            "recovery_law_hash": operator.recovery_law_hash,
        },
        "counts": {
            "terminal_epoch": operator.terminal_epoch,
            "physical_dof_count": operator.physical_dof_count,
            "member_count": operator.member_count,
            "integration_point_count": operator.integration_point_count,
            "fiber_output_count": operator.fiber_output_count,
            "authored_reaction_count": operator.authored_reaction_count,
        },
        "metrics": {
            "free_residual_scaled_linf": operator.free_residual_scaled_linf,
            "free_residual_scaled_tolerance": source_tolerance,
            "element_scatter_scaled_linf": operator.element_scatter_scaled_linf,
            "local_global_force_scaled_linf": (operator.local_global_force_scaled_linf),
            "section_integration_scaled_linf": (
                operator.section_integration_scaled_linf
            ),
            "section_resultant_scaled_linf": (operator.section_resultant_scaled_linf),
            "fiber_strain_linf": operator.fiber_strain_linf,
            "local_global_work_scaled_abs": (operator.local_global_work_scaled_abs),
            "section_element_work_scaled_abs": (
                operator.section_element_work_scaled_abs
            ),
            "dissipated_energy_balance_scaled_abs": (
                operator.dissipated_energy_balance_scaled_abs
            ),
            "total_dissipated_energy_mj": operator.total_dissipated_energy_mj,
            "transformation_orthogonality_linf": (
                operator.transformation_orthogonality_linf
            ),
            "consistency_tolerance": (
                FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE
            ),
            "fiber_strain_tolerance": (
                FIBER_FRAME_NONLINEAR_RECOVERY_FIBER_STRAIN_TOLERANCE
            ),
            "state_bytes_exact": operator.state_bytes_exact,
            "all_recovery_gates_passed": True,
        },
        "array_bundle_hash": operator.array_bundle_hash,
        "array_descriptors": [row.to_dict() for row in operator.descriptors],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY),
        "extensions": dict(operator.extensions),
    }
    if not include_hash:
        payload.pop("recovery_operator_hash")
    return payload


def _result_payload(
    result: FiberFrameNonlinearEngineeringResultIR,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version,
        "engineering_result_id": result.engineering_result_id,
        "engineering_result_hash": result.engineering_result_hash,
        "result_kind": result.result_kind,
        "authority_profile": result.authority_profile,
        "authority": dict(FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES),
        "source": {
            "numerical_result_schema_version": (
                result.source_numerical_result_schema_version
            ),
            "numerical_result_hash": result.source_numerical_result_hash,
            "result_adapter_hash": result.source_result_adapter_hash,
            "recovery_operator_hash": result.recovery_operator_hash,
        },
        "bindings": {
            "problem_contract_hash": result.problem_contract_hash,
            "model_ir_content_hash": result.model_ir_content_hash,
            "execution_topology_plan_hash": (result.execution_topology_plan_hash),
            "terminal_kinematic_state_hash": (result.terminal_kinematic_state_hash),
            "terminal_material_state_bundle_hash": (
                result.terminal_material_state_bundle_hash
            ),
        },
        "counts": {
            "terminal_epoch": result.terminal_epoch,
            "physical_dof_count": result.physical_dof_count,
            "member_count": result.member_count,
            "integration_point_count": result.integration_point_count,
            "fiber_output_count": result.fiber_output_count,
            "authored_reaction_count": result.authored_reaction_count,
        },
        "observations": {
            "load_factor": result.load_factor,
            "free_residual_scaled_linf": result.free_residual_scaled_linf,
            "total_dissipated_energy_mj": result.total_dissipated_energy_mj,
        },
        "array_bundle_hash": result.array_bundle_hash,
        "artifact_descriptors": [row.to_dict() for row in result.descriptors],
        "recovery_operator": _operator_payload(
            result._recovery_operator,
            include_hash=True,
        ),
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY),
        "extensions": dict(result.extensions),
    }
    if not include_hash:
        payload.pop("engineering_result_hash")
    return payload


def validate_fiber_frame_nonlinear_recovery_operator_shape(
    operator: FiberFrameNonlinearRecoveryOperator,
) -> FiberFrameNonlinearRecoveryOperator:
    """Validate immutable recovery storage, bindings, gates, and self-hash."""

    if type(operator) is not FiberFrameNonlinearRecoveryOperator:
        _fail(
            "fiber_frame_recovery_operator_type_invalid",
            "/",
            "Expected FiberFrameNonlinearRecoveryOperator.",
        )
    if (
        operator.schema_version
        != FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_SCHEMA_VERSION
        or operator.profile != FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE
        or operator.authority_profile
        != FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_recovery_operator_profile_invalid",
            "/",
            "Unsupported recovery operator schema or authority profile.",
        )
    if type(operator._source_adapter) is not FiberFrameNonlinearNumericalResultAdapter:
        _fail(
            "fiber_frame_recovery_source_type_invalid",
            "/source",
            "Recovery operator must retain its exact numerical-result adapter.",
        )
    source_adapter = operator._source_adapter
    source = source_adapter.source_binding
    numerical_result = source_adapter.numerical_result
    _stable_id(operator.case_id, "/bindings/case_id")
    hash_fields = (
        "recovery_operator_hash",
        "problem_contract_hash",
        "model_ir_content_hash",
        "source_result_adapter_hash",
        "source_binding_hash",
        "source_numerical_result_hash",
        "execution_topology_plan_hash",
        "physical_equation_scaling_binding_hash",
        "execution_state_binding_hash",
        "checkpoint_chain_hash",
        "terminal_checkpoint_state_hash",
        "terminal_kinematic_state_hash",
        "terminal_material_state_bundle_hash",
        "terminal_receipt_hash",
        "geometry_hash",
        "member_order_hash",
        "integration_point_output_order_hash",
        "fiber_output_order_hash",
        "constituent_state_replay_hash",
        "recovery_law_hash",
        "array_bundle_hash",
    )
    for name in hash_fields:
        _require_hash(getattr(operator, name), f"/{name}")
    expected_bindings = {
        "problem_contract_hash": source.problem_contract_hash,
        "model_ir_content_hash": source.model_ir_content_hash,
        "case_id": source.case_id,
        "source_result_adapter_hash": source_adapter.adapter_hash,
        "source_binding_hash": source.binding_hash,
        "source_numerical_result_hash": numerical_result.result_hash,
        "execution_topology_plan_hash": source.execution_topology_plan_hash,
        "physical_equation_scaling_binding_hash": (
            source.physical_equation_scaling_binding_hash
        ),
        "execution_state_binding_hash": source.execution_state_binding_hash,
        "checkpoint_chain_hash": source.checkpoint_chain_hash,
        "terminal_checkpoint_state_hash": source.terminal_checkpoint_state_hash,
        "terminal_kinematic_state_hash": source.terminal_kinematic_state_hash,
        "terminal_material_state_bundle_hash": (
            source.terminal_material_state_bundle_hash
        ),
        "terminal_receipt_hash": source.terminal_receipt_hash,
        "terminal_epoch": source.terminal_epoch,
        "terminal_load_factor": source.terminal_load_factor,
        "physical_dof_count": source.physical_dof_count,
    }
    if any(
        getattr(operator, name) != value for name, value in expected_bindings.items()
    ):
        _fail(
            "fiber_frame_recovery_source_binding_mismatch",
            "/bindings",
            "Recovery operator differs from its retained J1--J5 source.",
        )
    _positive_index(operator.terminal_epoch, "/counts/terminal_epoch")
    _positive_float(operator.terminal_load_factor, "/bindings/terminal_load_factor")
    for name in (
        "physical_dof_count",
        "member_count",
        "integration_point_count",
        "fiber_output_count",
        "authored_reaction_count",
    ):
        _positive_index(getattr(operator, name), f"/counts/{name}")
    if operator.physical_dof_count % 6 != 0:
        _fail(
            "fiber_frame_recovery_physical_dof_count_invalid",
            "/counts/physical_dof_count",
            "Canonical physical equations require six DOFs per node.",
        )
    metrics = {
        "free_residual_scaled_linf": operator.free_residual_scaled_linf,
        "element_scatter_scaled_linf": operator.element_scatter_scaled_linf,
        "local_global_force_scaled_linf": (operator.local_global_force_scaled_linf),
        "section_integration_scaled_linf": (operator.section_integration_scaled_linf),
        "section_resultant_scaled_linf": operator.section_resultant_scaled_linf,
        "fiber_strain_linf": operator.fiber_strain_linf,
        "local_global_work_scaled_abs": operator.local_global_work_scaled_abs,
        "section_element_work_scaled_abs": (operator.section_element_work_scaled_abs),
        "dissipated_energy_balance_scaled_abs": (
            operator.dissipated_energy_balance_scaled_abs
        ),
        "total_dissipated_energy_mj": operator.total_dissipated_energy_mj,
        "transformation_orthogonality_linf": (
            operator.transformation_orthogonality_linf
        ),
        "state_bytes_exact": operator.state_bytes_exact,
    }
    _require_recovery_gates(metrics, source.solver_residual_tolerance)
    _validate_recovery_array_map(operator)
    _validate_recovery_array_semantics(operator)
    if not isinstance(operator.extensions, MappingProxyType) or operator.extensions:
        _fail(
            "fiber_frame_recovery_extensions_invalid",
            "/extensions",
            "Recovery operator v1 requires immutable empty extensions.",
        )
    expected_bundle_hash = _array_bundle_hash(
        operator.descriptors,
        operator.source_numerical_result_hash,
    )
    if operator.array_bundle_hash != expected_bundle_hash:
        _fail(
            "fiber_frame_recovery_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Recovery array bundle hash is stale.",
        )
    expected_hash = canonical_hash(_operator_payload(operator, include_hash=False))
    if operator.recovery_operator_hash != expected_hash:
        _fail(
            "fiber_frame_recovery_operator_hash_mismatch",
            "/recovery_operator_hash",
            "Recovery operator hash is stale.",
        )
    return operator


def _validate_recovery_array_map(
    operator: FiberFrameNonlinearRecoveryOperator,
) -> None:
    arrays = operator._arrays
    if not isinstance(arrays, MappingProxyType) or tuple(arrays) != _ARRAY_NAMES:
        _fail(
            "fiber_frame_recovery_array_map_invalid",
            "/array_descriptors",
            "Retained array map is mutable, incomplete, or reordered.",
        )
    if (
        type(operator.descriptors) is not tuple
        or tuple(row.name for row in operator.descriptors) != _ARRAY_NAMES
    ):
        _fail(
            "fiber_frame_recovery_descriptor_set_invalid",
            "/array_descriptors",
            "Recovery descriptors are incomplete or reordered.",
        )
    order_hashes = {
        "member_order": operator.member_order_hash,
        "physical_equation_order": (
            operator._source_adapter.source_binding._physical_scaling.equation_order_hash
        ),
        "integration_point_order": operator.integration_point_output_order_hash,
        "fiber_output_order": operator.fiber_output_order_hash,
    }
    for descriptor in operator.descriptors:
        array = arrays[descriptor.name]
        spec = _ARRAY_SPEC_BY_NAME[descriptor.name]
        if (
            not has_immutable_bytes_backing(array)
            or array.dtype.str != spec[1]
            or array.ndim != spec[2]
            or not array.flags.c_contiguous
        ):
            _fail(
                "fiber_frame_recovery_array_storage_invalid",
                f"/array_descriptors/{descriptor.name}",
                "Recovery array storage is not canonical immutable little-endian data.",
            )
        expected = _recovery_array_descriptor(
            descriptor.name,
            array,
            order_hash=order_hashes[spec[4]],
            source_numerical_result_hash=operator.source_numerical_result_hash,
        )
        if descriptor != expected:
            _fail(
                "fiber_frame_recovery_array_descriptor_mismatch",
                f"/array_descriptors/{descriptor.name}",
                "Descriptor metadata differs from retained array bytes.",
            )


def _validate_recovery_array_semantics(
    operator: FiberFrameNonlinearRecoveryOperator,
) -> None:
    member_count = operator.member_count
    point_count = operator.integration_point_count
    fiber_count = operator.fiber_output_count
    physical_count = operator.physical_dof_count
    expected_shapes = {
        "member_global_dofs_source_3dof": (member_count, 6),
        "member_transformation_global_to_local": (member_count, 6, 6),
        "member_local_displacement": (member_count, 6),
        "member_local_end_force_si": (member_count, 6),
        "member_global_end_force_si": (member_count, 6),
        "internal_load_global_si": (physical_count,),
        "external_load_global_si": (physical_count,),
        "equilibrium_residual_global_si": (physical_count,),
        "reaction_global_si": (physical_count,),
        "integration_point_offsets": (member_count + 1,),
        "integration_point_xi": (point_count,),
        "integration_point_weights": (point_count,),
        "section_generalized_strain": (point_count, 2),
        "section_resultant_si": (point_count, 2),
        "section_dissipated_energy_mj_per_m": (point_count,),
        "fiber_offsets": (point_count + 1,),
        "fiber_y_m": (fiber_count,),
        "fiber_area_m2": (fiber_count,),
        "fiber_strain": (fiber_count,),
        "fiber_stress_mpa": (fiber_count,),
        "fiber_dissipated_energy_density_mj_per_m3": (fiber_count,),
    }
    for name, shape in expected_shapes.items():
        if operator.array(name).shape != shape:
            _fail(
                "fiber_frame_recovery_array_shape_invalid",
                f"/arrays/{name}",
                f"Expected shape {shape}.",
            )
    solver_count = physical_count // 2
    member_dofs = operator.array("member_global_dofs_source_3dof")
    if np.any(member_dofs < 0) or np.any(member_dofs >= solver_count):
        _fail(
            "fiber_frame_recovery_member_dof_invalid",
            "/arrays/member_global_dofs_source_3dof",
            "Member source DOF indices are outside the solver equation space.",
        )
    point_offsets = operator.array("integration_point_offsets")
    fiber_offsets = operator.array("fiber_offsets")
    if (
        int(point_offsets[0]) != 0
        or int(point_offsets[-1]) != point_count
        or np.any(np.diff(point_offsets) <= 0)
        or int(fiber_offsets[0]) != 0
        or int(fiber_offsets[-1]) != fiber_count
        or np.any(np.diff(fiber_offsets) <= 0)
        or np.any(np.abs(operator.array("integration_point_xi")) > 1.0)
        or np.any(operator.array("integration_point_weights") <= 0.0)
        or np.any(operator.array("fiber_area_m2") <= 0.0)
        or np.any(operator.array("section_dissipated_energy_mj_per_m") < 0.0)
        or np.any(operator.array("fiber_dissipated_energy_density_mj_per_m3") < 0.0)
    ):
        _fail(
            "fiber_frame_recovery_array_semantics_invalid",
            "/arrays",
            "Recovery offsets, quadrature, area, or energy semantics are invalid.",
        )
    plan = operator._source_adapter.source_binding._topology_plan
    authored_fixed = np.asarray(
        plan.array("authored_fixed_physical_dofs"),
        dtype=np.int64,
    )
    if authored_fixed.size != operator.authored_reaction_count:
        _fail(
            "fiber_frame_recovery_reaction_count_mismatch",
            "/counts/authored_reaction_count",
            "Authored reaction count differs from the J1 partition.",
        )
    residual = operator.array("equilibrium_residual_global_si")
    reaction = operator.array("reaction_global_si")
    expected_reaction = np.zeros(physical_count, dtype=np.float64)
    expected_reaction[authored_fixed] = residual[authored_fixed]
    if not np.array_equal(reaction, expected_reaction):
        _fail(
            "fiber_frame_recovery_reaction_partition_mismatch",
            "/arrays/reaction_global_si",
            "Reaction values must be the residual on authored fixed equations only.",
        )
    if not np.array_equal(
        residual,
        operator.array("internal_load_global_si")
        - operator.array("external_load_global_si"),
    ):
        _fail(
            "fiber_frame_recovery_residual_identity_mismatch",
            "/arrays/equilibrium_residual_global_si",
            "Equilibrium residual must equal internal minus external load.",
        )


def validate_fiber_frame_nonlinear_recovery_operator(
    operator: FiberFrameNonlinearRecoveryOperator,
) -> FiberFrameNonlinearRecoveryOperator:
    """Replay the terminal path and compare every retained artifact."""

    checked = validate_fiber_frame_nonlinear_recovery_operator_shape(operator)
    adapter = validate_fiber_frame_nonlinear_numerical_result_adapter(
        checked._source_adapter
    )
    expected = _build_recovery_operator(adapter)
    if _operator_payload(checked, include_hash=True) != _operator_payload(
        expected,
        include_hash=True,
    ):
        _fail(
            "fiber_frame_recovery_operator_replay_mismatch",
            "/",
            "Recovery operator metadata does not replay from its exact source.",
        )
    for name in _ARRAY_NAMES:
        if not np.array_equal(checked.array(name), expected.array(name)):
            _fail(
                "fiber_frame_recovery_array_replay_mismatch",
                f"/arrays/{name}",
                "Retained engineering artifact differs from independent replay.",
            )
    return checked


def validate_fiber_frame_nonlinear_engineering_result_ir(
    result: FiberFrameNonlinearEngineeringResultIR,
) -> FiberFrameNonlinearEngineeringResultIR:
    """Validate one bounded authoritative engineering result and its operator."""

    if type(result) is not FiberFrameNonlinearEngineeringResultIR:
        _fail(
            "fiber_frame_engineering_result_type_invalid",
            "/",
            "Expected FiberFrameNonlinearEngineeringResultIR.",
        )
    if (
        result.schema_version != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_SCHEMA_VERSION
        or result.result_kind != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_KIND
        or result.authority_profile
        != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_engineering_result_profile_invalid",
            "/",
            "Unsupported engineering-result schema, kind, or authority profile.",
        )
    _stable_id(result.engineering_result_id, "/engineering_result_id")
    _require_hash(result.engineering_result_hash, "/engineering_result_hash")
    if (
        type(result._source_adapter) is not FiberFrameNonlinearNumericalResultAdapter
        or type(result._recovery_operator) is not FiberFrameNonlinearRecoveryOperator
    ):
        _fail(
            "fiber_frame_engineering_result_retained_source_invalid",
            "/source",
            "Engineering result must retain its exact adapter and recovery operator.",
        )
    adapter = validate_fiber_frame_nonlinear_numerical_result_adapter(
        result._source_adapter
    )
    operator = validate_fiber_frame_nonlinear_recovery_operator(
        result._recovery_operator
    )
    if operator._source_adapter is not adapter:
        _fail(
            "fiber_frame_engineering_result_source_identity_mismatch",
            "/source",
            "Engineering result and recovery operator retain different sources.",
        )
    source = adapter.source_binding
    numerical_result = adapter.numerical_result
    expected = {
        "source_numerical_result_schema_version": numerical_result.schema_version,
        "source_numerical_result_hash": numerical_result.result_hash,
        "source_result_adapter_hash": adapter.adapter_hash,
        "recovery_operator_hash": operator.recovery_operator_hash,
        "problem_contract_hash": source.problem_contract_hash,
        "model_ir_content_hash": source.model_ir_content_hash,
        "execution_topology_plan_hash": source.execution_topology_plan_hash,
        "terminal_kinematic_state_hash": source.terminal_kinematic_state_hash,
        "terminal_material_state_bundle_hash": (
            source.terminal_material_state_bundle_hash
        ),
        "terminal_epoch": source.terminal_epoch,
        "load_factor": source.terminal_load_factor,
        "physical_dof_count": operator.physical_dof_count,
        "member_count": operator.member_count,
        "integration_point_count": operator.integration_point_count,
        "fiber_output_count": operator.fiber_output_count,
        "authored_reaction_count": operator.authored_reaction_count,
        "free_residual_scaled_linf": operator.free_residual_scaled_linf,
        "total_dissipated_energy_mj": operator.total_dissipated_energy_mj,
        "array_bundle_hash": operator.array_bundle_hash,
        "descriptors": operator.descriptors,
    }
    if any(getattr(result, name) != value for name, value in expected.items()):
        _fail(
            "fiber_frame_engineering_result_binding_mismatch",
            "/",
            "Engineering result differs from its source or recovery operator.",
        )
    if (
        result.source_numerical_result_schema_version
        != NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_engineering_result_source_schema_invalid",
            "/source/numerical_result_schema_version",
            "Engineering result requires NonlinearNumericalResultIR v1.",
        )
    if not isinstance(result.extensions, MappingProxyType) or result.extensions:
        _fail(
            "fiber_frame_engineering_result_extensions_invalid",
            "/extensions",
            "Engineering result v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.engineering_result_hash != expected_hash:
        _fail(
            "fiber_frame_engineering_result_hash_mismatch",
            "/engineering_result_hash",
            "Engineering result hash is stale.",
        )
    return result


def validate_fiber_frame_nonlinear_recovery_operator_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a descriptor-only recovery manifest as strict finite JSON."""

    normalized = _strict_json_object(manifest, "/")
    _exact_keys(
        normalized,
        {
            "schema_version",
            "recovery_operator_hash",
            "profile",
            "authority_profile",
            "storage_profile",
            "bindings",
            "formulations",
            "orders",
            "counts",
            "metrics",
            "array_bundle_hash",
            "array_descriptors",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        normalized["schema_version"]
        != FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_SCHEMA_VERSION
        or normalized["profile"] != FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE
        or normalized["authority_profile"]
        != FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_AUTHORITY_PROFILE
        or normalized["storage_profile"]
        != FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE
    ):
        _fail(
            "fiber_frame_recovery_manifest_profile_invalid",
            "/",
            "Unsupported recovery manifest schema or profile.",
        )
    _require_hash(
        normalized["recovery_operator_hash"],
        "/recovery_operator_hash",
    )
    _require_hash(normalized["array_bundle_hash"], "/array_bundle_hash")

    bindings = _manifest_object(normalized["bindings"], "/bindings")
    binding_keys = {
        "problem_contract_hash",
        "model_ir_content_hash",
        "case_id",
        "source_result_adapter_hash",
        "source_binding_hash",
        "source_numerical_result_hash",
        "execution_topology_plan_hash",
        "physical_equation_scaling_binding_hash",
        "execution_state_binding_hash",
        "checkpoint_chain_hash",
        "terminal_checkpoint_state_hash",
        "terminal_kinematic_state_hash",
        "terminal_material_state_bundle_hash",
        "terminal_receipt_hash",
        "terminal_load_factor",
    }
    _exact_keys(bindings, binding_keys, "/bindings")
    _stable_id(bindings["case_id"], "/bindings/case_id")
    _positive_float(
        bindings["terminal_load_factor"],
        "/bindings/terminal_load_factor",
    )
    for name in binding_keys - {"case_id", "terminal_load_factor"}:
        _require_hash(bindings[name], f"/bindings/{name}")

    formulations = _manifest_object(
        normalized["formulations"],
        "/formulations",
    )
    if formulations != _expected_formulations():
        _fail(
            "fiber_frame_recovery_manifest_formulation_invalid",
            "/formulations",
            "Recovery formulation identities changed.",
        )
    orders = _manifest_object(normalized["orders"], "/orders")
    _exact_keys(
        orders,
        {
            "member_force_order",
            "section_resultant_order",
            "fiber_output_order",
            "geometry_hash",
            "member_order_hash",
            "physical_equation_order_hash",
            "integration_point_output_order_hash",
            "fiber_output_order_hash",
            "constituent_state_replay_hash",
            "recovery_law_hash",
        },
        "/orders",
    )
    if (
        orders["member_force_order"] != FIBER_FRAME_NONLINEAR_MEMBER_FORCE_ORDER
        or orders["section_resultant_order"]
        != FIBER_FRAME_NONLINEAR_SECTION_RESULTANT_ORDER
        or orders["fiber_output_order"] != FIBER_FRAME_NONLINEAR_FIBER_OUTPUT_ORDER
    ):
        _fail(
            "fiber_frame_recovery_manifest_order_profile_invalid",
            "/orders",
            "Recovery output-order profile changed.",
        )
    for name in (
        "geometry_hash",
        "member_order_hash",
        "physical_equation_order_hash",
        "integration_point_output_order_hash",
        "fiber_output_order_hash",
        "constituent_state_replay_hash",
        "recovery_law_hash",
    ):
        _require_hash(orders[name], f"/orders/{name}")
    if orders["recovery_law_hash"] != _recovery_law_hash():
        _fail(
            "fiber_frame_recovery_manifest_law_hash_invalid",
            "/orders/recovery_law_hash",
            "Recovery law hash does not match the v1 formulation.",
        )

    counts = _manifest_object(normalized["counts"], "/counts")
    _exact_keys(
        counts,
        {
            "terminal_epoch",
            "physical_dof_count",
            "member_count",
            "integration_point_count",
            "fiber_output_count",
            "authored_reaction_count",
        },
        "/counts",
    )
    for name, value in counts.items():
        _positive_index(value, f"/counts/{name}")
    if counts["physical_dof_count"] % 6 != 0:
        _fail(
            "fiber_frame_recovery_manifest_dof_count_invalid",
            "/counts/physical_dof_count",
            "Canonical physical equation count must be divisible by six.",
        )

    metrics = _manifest_object(normalized["metrics"], "/metrics")
    metric_names = {
        "free_residual_scaled_linf",
        "free_residual_scaled_tolerance",
        "element_scatter_scaled_linf",
        "local_global_force_scaled_linf",
        "section_integration_scaled_linf",
        "section_resultant_scaled_linf",
        "fiber_strain_linf",
        "local_global_work_scaled_abs",
        "section_element_work_scaled_abs",
        "dissipated_energy_balance_scaled_abs",
        "total_dissipated_energy_mj",
        "transformation_orthogonality_linf",
        "consistency_tolerance",
        "fiber_strain_tolerance",
        "state_bytes_exact",
        "all_recovery_gates_passed",
    }
    _exact_keys(metrics, metric_names, "/metrics")
    source_tolerance = _positive_float(
        metrics["free_residual_scaled_tolerance"],
        "/metrics/free_residual_scaled_tolerance",
    )
    if (
        metrics["consistency_tolerance"]
        != FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE
        or metrics["fiber_strain_tolerance"]
        != FIBER_FRAME_NONLINEAR_RECOVERY_FIBER_STRAIN_TOLERANCE
        or metrics["all_recovery_gates_passed"] is not True
    ):
        _fail(
            "fiber_frame_recovery_manifest_gate_profile_invalid",
            "/metrics",
            "Recovery tolerances or aggregate gate changed.",
        )
    _require_recovery_gates(metrics, source_tolerance)

    descriptors = normalized["array_descriptors"]
    if type(descriptors) is not list or len(descriptors) != len(_ARRAY_NAMES):
        _fail(
            "fiber_frame_recovery_manifest_descriptors_invalid",
            "/array_descriptors",
            "Recovery manifest requires the exact descriptor set.",
        )
    expected_shapes = _manifest_array_shapes(counts)
    order_hashes = {
        "member_order": orders["member_order_hash"],
        "physical_equation_order": orders["physical_equation_order_hash"],
        "integration_point_order": orders["integration_point_output_order_hash"],
        "fiber_output_order": orders["fiber_output_order_hash"],
    }
    digest = bindings["source_numerical_result_hash"].split(":", 1)[1]
    for index, (descriptor_value, spec) in enumerate(
        zip(descriptors, _ARRAY_SPECS, strict=True)
    ):
        descriptor = _manifest_object(
            descriptor_value,
            f"/array_descriptors/{index}",
        )
        _exact_keys(
            descriptor,
            {
                "name",
                "dtype",
                "shape",
                "layout",
                "byte_order",
                "byte_length",
                "unit_profile",
                "equation_scope",
                "authority_role",
                "order_hash",
                "data_hash",
                "content_hash",
                "artifact_uri",
            },
            f"/array_descriptors/{index}",
        )
        name, dtype, rank, unit, scope, role = spec
        shape = expected_shapes[name]
        expected_uri = (
            f"artifact://stateful-fiber-frame2d-nonlinear-recovery/{digest}/{name}.bin"
        )
        if (
            descriptor["name"] != name
            or descriptor["dtype"] != dtype
            or descriptor["shape"] != list(shape)
            or len(descriptor["shape"]) != rank
            or descriptor["layout"] != "C"
            or descriptor["byte_order"] != "little"
            or descriptor["byte_length"]
            != int(np.prod(shape, dtype=np.int64)) * np.dtype(dtype).itemsize
            or descriptor["unit_profile"] != unit
            or descriptor["equation_scope"] != scope
            or descriptor["authority_role"] != role
            or descriptor["order_hash"] != order_hashes[scope]
            or descriptor["artifact_uri"] != expected_uri
        ):
            _fail(
                "fiber_frame_recovery_manifest_descriptor_invalid",
                f"/array_descriptors/{index}",
                "Recovery descriptor metadata is inconsistent.",
            )
        _require_hash(
            descriptor["data_hash"],
            f"/array_descriptors/{index}/data_hash",
        )
        _require_hash(
            descriptor["content_hash"],
            f"/array_descriptors/{index}/content_hash",
        )
        if descriptor["content_hash"] != canonical_hash(
            {key: value for key, value in descriptor.items() if key != "content_hash"}
        ):
            _fail(
                "fiber_frame_recovery_manifest_descriptor_hash_mismatch",
                f"/array_descriptors/{index}/content_hash",
                "Recovery descriptor content hash is stale.",
            )
    expected_bundle_hash = canonical_hash(
        {
            "storage_profile": FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE,
            "source_numerical_result_hash": bindings["source_numerical_result_hash"],
            "array_descriptors": descriptors,
        }
    )
    if normalized["array_bundle_hash"] != expected_bundle_hash:
        _fail(
            "fiber_frame_recovery_manifest_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Recovery manifest array-bundle hash is stale.",
        )
    _require_claim_boundary(
        normalized["claim_boundary"],
        FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    _require_empty_manifest_extensions(normalized["extensions"], "/extensions")
    if normalized["recovery_operator_hash"] != canonical_hash(
        {
            key: value
            for key, value in normalized.items()
            if key != "recovery_operator_hash"
        }
    ):
        _fail(
            "fiber_frame_recovery_manifest_hash_mismatch",
            "/recovery_operator_hash",
            "Recovery manifest hash is stale.",
        )
    return normalized


def validate_fiber_frame_nonlinear_engineering_result_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate strict JSON plus all cross-bindings to the nested operator."""

    normalized = _strict_json_object(manifest, "/")
    _exact_keys(
        normalized,
        {
            "schema_version",
            "engineering_result_id",
            "engineering_result_hash",
            "result_kind",
            "authority_profile",
            "authority",
            "source",
            "bindings",
            "counts",
            "observations",
            "array_bundle_hash",
            "artifact_descriptors",
            "recovery_operator",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        normalized["schema_version"]
        != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_SCHEMA_VERSION
        or normalized["result_kind"] != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_KIND
        or normalized["authority_profile"]
        != FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_profile_invalid",
            "/",
            "Unsupported engineering-result manifest profile.",
        )
    _stable_id(normalized["engineering_result_id"], "/engineering_result_id")
    _require_hash(
        normalized["engineering_result_hash"],
        "/engineering_result_hash",
    )
    if normalized["authority"] != dict(
        FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_authority_invalid",
            "/authority",
            "Engineering authority axes changed.",
        )
    nested = validate_fiber_frame_nonlinear_recovery_operator_manifest(
        _manifest_object(normalized["recovery_operator"], "/recovery_operator")
    )

    source = _manifest_object(normalized["source"], "/source")
    _exact_keys(
        source,
        {
            "numerical_result_schema_version",
            "numerical_result_hash",
            "result_adapter_hash",
            "recovery_operator_hash",
        },
        "/source",
    )
    if source["numerical_result_schema_version"] != (
        NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_source_schema_invalid",
            "/source/numerical_result_schema_version",
            "Engineering result requires NonlinearNumericalResultIR v1.",
        )
    for name in (
        "numerical_result_hash",
        "result_adapter_hash",
        "recovery_operator_hash",
    ):
        _require_hash(source[name], f"/source/{name}")
    nested_bindings = nested["bindings"]
    if (
        source["numerical_result_hash"]
        != nested_bindings["source_numerical_result_hash"]
        or source["result_adapter_hash"]
        != nested_bindings["source_result_adapter_hash"]
        or source["recovery_operator_hash"] != nested["recovery_operator_hash"]
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_source_mismatch",
            "/source",
            "Engineering source differs from the nested recovery operator.",
        )

    bindings = _manifest_object(normalized["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_hash",
            "terminal_kinematic_state_hash",
            "terminal_material_state_bundle_hash",
        },
        "/bindings",
    )
    for name, value in bindings.items():
        _require_hash(value, f"/bindings/{name}")
        if value != nested_bindings[name]:
            _fail(
                "fiber_frame_engineering_result_manifest_binding_mismatch",
                f"/bindings/{name}",
                "Engineering binding differs from the recovery operator.",
            )

    counts = _manifest_object(normalized["counts"], "/counts")
    _exact_keys(
        counts,
        {
            "terminal_epoch",
            "physical_dof_count",
            "member_count",
            "integration_point_count",
            "fiber_output_count",
            "authored_reaction_count",
        },
        "/counts",
    )
    if counts != nested["counts"]:
        _fail(
            "fiber_frame_engineering_result_manifest_count_mismatch",
            "/counts",
            "Engineering counts differ from the recovery operator.",
        )
    observations = _manifest_object(
        normalized["observations"],
        "/observations",
    )
    _exact_keys(
        observations,
        {
            "load_factor",
            "free_residual_scaled_linf",
            "total_dissipated_energy_mj",
        },
        "/observations",
    )
    for name, value in observations.items():
        _nonnegative_float(value, f"/observations/{name}")
    if (
        observations["load_factor"] != nested_bindings["terminal_load_factor"]
        or observations["free_residual_scaled_linf"]
        != nested["metrics"]["free_residual_scaled_linf"]
        or observations["total_dissipated_energy_mj"]
        != nested["metrics"]["total_dissipated_energy_mj"]
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_observation_mismatch",
            "/observations",
            "Engineering observations differ from the recovery operator.",
        )
    _require_hash(normalized["array_bundle_hash"], "/array_bundle_hash")
    if (
        normalized["array_bundle_hash"] != nested["array_bundle_hash"]
        or normalized["artifact_descriptors"] != nested["array_descriptors"]
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_artifact_mismatch",
            "/artifact_descriptors",
            "Engineering artifact identities differ from the recovery operator.",
        )
    _require_claim_boundary(
        normalized["claim_boundary"],
        FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    _require_empty_manifest_extensions(normalized["extensions"], "/extensions")
    if normalized["engineering_result_hash"] != canonical_hash(
        {
            key: value
            for key, value in normalized.items()
            if key != "engineering_result_hash"
        }
    ):
        _fail(
            "fiber_frame_engineering_result_manifest_hash_mismatch",
            "/engineering_result_hash",
            "Engineering-result manifest hash is stale.",
        )
    return normalized


def _expected_formulations() -> dict[str, Any]:
    return {
        "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
        "beam_kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
        "beam_internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
        "beam_tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
        "section_strain_relation": FIBER_SECTION_STRAIN_RELATION,
        "section_resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
        "section_tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
        "residual_formula": RESIDUAL_FORMULA,
        "source_force_to_si": FIBER_FRAME_FORCE_TO_SI,
        "source_moment_to_si": FIBER_FRAME_MOMENT_TO_SI,
    }


def _manifest_array_shapes(counts: Mapping[str, Any]) -> dict[str, tuple[int, ...]]:
    member_count = counts["member_count"]
    point_count = counts["integration_point_count"]
    fiber_count = counts["fiber_output_count"]
    physical_count = counts["physical_dof_count"]
    return {
        "member_global_dofs_source_3dof": (member_count, 6),
        "member_transformation_global_to_local": (member_count, 6, 6),
        "member_local_displacement": (member_count, 6),
        "member_local_end_force_si": (member_count, 6),
        "member_global_end_force_si": (member_count, 6),
        "internal_load_global_si": (physical_count,),
        "external_load_global_si": (physical_count,),
        "equilibrium_residual_global_si": (physical_count,),
        "reaction_global_si": (physical_count,),
        "integration_point_offsets": (member_count + 1,),
        "integration_point_xi": (point_count,),
        "integration_point_weights": (point_count,),
        "section_generalized_strain": (point_count, 2),
        "section_resultant_si": (point_count, 2),
        "section_dissipated_energy_mj_per_m": (point_count,),
        "fiber_offsets": (point_count + 1,),
        "fiber_y_m": (fiber_count,),
        "fiber_area_m2": (fiber_count,),
        "fiber_strain": (fiber_count,),
        "fiber_stress_mpa": (fiber_count,),
        "fiber_dissipated_energy_density_mj_per_m3": (fiber_count,),
    }


def _strict_json_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "fiber_frame_recovery_manifest_type_invalid",
            path,
            "Manifest value must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameNonlinearRecoveryError(
            "fiber_frame_recovery_manifest_json_invalid",
            path,
            "Manifest must be finite strict JSON.",
        ) from exc
    if type(normalized) is not dict:
        _fail(
            "fiber_frame_recovery_manifest_type_invalid",
            path,
            "Manifest value must be an object.",
        )
    return normalized


def _manifest_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(
            "fiber_frame_recovery_manifest_object_invalid",
            path,
            "Expected a JSON object.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            "fiber_frame_recovery_manifest_keys_invalid",
            path,
            f"Expected exact keys {sorted(expected)}; got {sorted(actual)}.",
        )


def _require_claim_boundary(
    value: Any,
    expected: Mapping[str, bool],
    path: str,
) -> None:
    if type(value) is not dict or value != dict(expected):
        _fail(
            "fiber_frame_recovery_claim_boundary_invalid",
            path,
            "Authority claim boundary changed.",
        )


def _require_empty_manifest_extensions(value: Any, path: str) -> None:
    if type(value) is not dict or value:
        _fail(
            "fiber_frame_recovery_manifest_extensions_invalid",
            path,
            "Manifest extensions must be empty.",
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_recovery_hash_invalid",
            path,
            "Expected lowercase sha256:<64 hex>.",
        )
    return value


def _stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_recovery_stable_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return value


def _positive_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 1 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_recovery_positive_index_invalid",
            path,
            "Expected a positive 32-bit integer.",
        )
    return value


def _finite_float(value: Any, path: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        _fail(
            "fiber_frame_recovery_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_recovery_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _positive_float(value: Any, path: str) -> float:
    normalized = _finite_float(value, path)
    if normalized <= 0.0:
        _fail(
            "fiber_frame_recovery_number_not_positive",
            path,
            "Expected a positive number.",
        )
    return normalized


def _nonnegative_float(value: Any, path: str) -> float:
    normalized = _finite_float(value, path)
    if normalized < 0.0:
        _fail(
            "fiber_frame_recovery_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearRecoveryError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES",
    "FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_KIND",
    "FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_FIBER_OUTPUT_ORDER",
    "FIBER_FRAME_NONLINEAR_MEMBER_FORCE_ORDER",
    "FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE",
    "FIBER_FRAME_NONLINEAR_RECOVERY_FIBER_STRAIN_TOLERANCE",
    "FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_RECOVERY_PROFILE",
    "FIBER_FRAME_NONLINEAR_RECOVERY_STORAGE_PROFILE",
    "FIBER_FRAME_NONLINEAR_SECTION_RESULTANT_ORDER",
    "FiberFrameNonlinearEngineeringResultIR",
    "FiberFrameNonlinearRecoveryArrayDescriptor",
    "FiberFrameNonlinearRecoveryError",
    "FiberFrameNonlinearRecoveryOperator",
    "create_fiber_frame_nonlinear_engineering_result_ir",
    "create_fiber_frame_nonlinear_recovery_operator",
    "validate_fiber_frame_nonlinear_engineering_result_ir",
    "validate_fiber_frame_nonlinear_engineering_result_manifest",
    "validate_fiber_frame_nonlinear_recovery_operator",
    "validate_fiber_frame_nonlinear_recovery_operator_manifest",
    "validate_fiber_frame_nonlinear_recovery_operator_shape",
]
