"""Bounded global load-control path for elastic corotational 3D frames.

This module deliberately connects the existing energy-derived single-element
reference to a small dense global assembly.  It is an experimental verification
path, not a promoted production 3D solver.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Iterable

import numpy as np

from structural_analysis.elements.corotational_frame3d import (
    CorotationalFrame3DResponse,
    corotational_frame3d_response,
)
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.equation_scaling_6dof import (
    EquationScaling6DOF,
    create_equation_scaling_6dof,
    scale_linear_system_6dof,
    scaled_increment_metrics_6dof,
    scaled_residual_metrics_6dof,
)


COROTATIONAL_FRAME3D_GLOBAL_PROFILE = (
    "dense_elastic_corotational_timoshenko_frame3d_load_control.v2"
)
COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION = "corotational-frame3d-global-solution.v2"
COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION = (
    "corotational-frame3d-global-checkpoint.v1"
)
COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY = (
    "Small dense elastic 3D frame verification path using the numerical-energy "
    "element tangent, explicit nodal loads and restraints, residual-and-increment "
    "commit gates, deterministic backtracking, and exact checkpoint lineage. It "
    "has no stateful section, distributed load, release/offset, warping coupling, "
    "transient dynamics, external V&V, or release authority."
)
_ZERO_HASH = "sha256:" + "0" * 64
_MAX_NODES = 16
_MAX_MEMBERS = 32
_MAX_FREE_EQUATIONS = 60


class CorotationalFrame3DGlobalError(RuntimeError):
    """Fail-closed model, convergence, or checkpoint-contract error."""


@dataclass(frozen=True)
class CorotationalFrame3DMember:
    member_id: str
    node_i: int
    node_j: int
    section: TimoshenkoFrame3DSection
    local_axis_roll_deg: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.member_id, str) or not self.member_id.strip():
            raise ValueError("member_id must be a non-empty string")
        if type(self.node_i) is not int or type(self.node_j) is not int:
            raise ValueError("member node indices must be integers")
        if self.node_i == self.node_j:
            raise ValueError("member endpoints must be distinct")
        if type(self.section) is not TimoshenkoFrame3DSection:
            raise ValueError("section must be an exact TimoshenkoFrame3DSection")
        object.__setattr__(
            self,
            "local_axis_roll_deg",
            _finite_float(self.local_axis_roll_deg, "local_axis_roll_deg"),
        )

    def to_manifest(self) -> dict[str, Any]:
        props = self.section.frame
        return {
            "member_id": self.member_id,
            "node_i": self.node_i,
            "node_j": self.node_j,
            "local_axis_roll_deg": self.local_axis_roll_deg,
            "section": {
                "area_m2": props.area_m2,
                "elastic_modulus_kn_per_m2": props.e_n_per_m2,
                "shear_modulus_kn_per_m2": props.g_n_per_m2,
                "iy_m4": props.iy_m4,
                "iz_m4": props.iz_m4,
                "j_m4": props.j_m4,
                "effective_shear_area_y_m2": (self.section.effective_shear_area_y_m2),
                "effective_shear_area_z_m2": (self.section.effective_shear_area_z_m2),
            },
        }


@dataclass(frozen=True)
class CorotationalFrame3DModel:
    node_coordinates_m: tuple[tuple[float, float, float], ...]
    members: tuple[CorotationalFrame3DMember, ...]
    restrained_dofs: tuple[int, ...]
    reference_load_kn: tuple[float, ...]
    model_id: str = "bounded_global_corotational_frame3d"

    def __post_init__(self) -> None:
        coordinates = tuple(
            tuple(_finite_float(value, f"node_coordinates_m[{index}]") for value in row)
            for index, row in enumerate(self.node_coordinates_m)
        )
        if not 2 <= len(coordinates) <= _MAX_NODES:
            raise ValueError(f"node count must be in [2, {_MAX_NODES}]")
        if any(len(row) != 3 for row in coordinates):
            raise ValueError("every node coordinate must contain three values")
        object.__setattr__(self, "node_coordinates_m", coordinates)

        members = tuple(self.members)
        if not 1 <= len(members) <= _MAX_MEMBERS:
            raise ValueError(f"member count must be in [1, {_MAX_MEMBERS}]")
        if any(type(member) is not CorotationalFrame3DMember for member in members):
            raise ValueError(
                "members must contain exact CorotationalFrame3DMember rows"
            )
        identifiers = [member.member_id for member in members]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("member_id values must be unique")
        endpoint_pairs: set[tuple[int, int]] = set()
        for member in members:
            if min(member.node_i, member.node_j) < 0 or max(
                member.node_i, member.node_j
            ) >= len(coordinates):
                raise ValueError(f"member {member.member_id} endpoint is out of range")
            pair = (
                min(member.node_i, member.node_j),
                max(member.node_i, member.node_j),
            )
            if pair in endpoint_pairs:
                raise ValueError("parallel or duplicate members are outside v1")
            endpoint_pairs.add(pair)
            chord = np.subtract(coordinates[member.node_j], coordinates[member.node_i])
            if float(np.linalg.norm(chord)) <= 1.0e-12:
                raise ValueError(f"member {member.member_id} has zero length")
        _validate_connected_graph(len(coordinates), members)
        object.__setattr__(self, "members", members)

        total_dofs = 6 * len(coordinates)
        restrained = tuple(self.restrained_dofs)
        if any(type(value) is not int for value in restrained):
            raise ValueError("restrained_dofs must contain integers")
        if tuple(sorted(set(restrained))) != restrained:
            raise ValueError("restrained_dofs must be sorted and unique")
        if not restrained or min(restrained) < 0 or max(restrained) >= total_dofs:
            raise ValueError("restrained_dofs must reference at least one valid DOF")
        free_count = total_dofs - len(restrained)
        if not 1 <= free_count <= _MAX_FREE_EQUATIONS:
            raise ValueError(
                f"free equation count must be in [1, {_MAX_FREE_EQUATIONS}]"
            )
        object.__setattr__(self, "restrained_dofs", restrained)

        loads = tuple(
            _finite_float(value, f"reference_load_kn[{index}]")
            for index, value in enumerate(self.reference_load_kn)
        )
        if len(loads) != total_dofs:
            raise ValueError(f"reference_load_kn must contain {total_dofs} values")
        if not any(value != 0.0 for value in loads):
            raise ValueError("reference_load_kn must contain a nonzero load")
        object.__setattr__(self, "reference_load_kn", loads)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")

    @property
    def total_dofs(self) -> int:
        return 6 * len(self.node_coordinates_m)

    @property
    def free_dofs(self) -> tuple[int, ...]:
        restrained = set(self.restrained_dofs)
        return tuple(
            index for index in range(self.total_dofs) if index not in restrained
        )

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
            "model_id": self.model_id,
            "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
            "members": [member.to_manifest() for member in self.members],
            "restrained_dofs": list(self.restrained_dofs),
            "reference_load_kn": list(self.reference_load_kn),
        }


@dataclass(frozen=True)
class CorotationalFrame3DGlobalConfig:
    residual_relative_tolerance: float = 1.0e-8
    residual_absolute_tolerance_kn: float = 1.0e-7
    increment_relative_tolerance: float = 1.0e-10
    increment_absolute_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 20
    maximum_condition_number: float = 1.0e14
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    )

    def __post_init__(self) -> None:
        for name in (
            "residual_relative_tolerance",
            "residual_absolute_tolerance_kn",
            "increment_relative_tolerance",
            "increment_absolute_tolerance_m",
            "maximum_condition_number",
        ):
            value = _positive_float(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be a positive integer")
        if not isinstance(self.line_search_alphas, tuple) or not self.line_search_alphas:
            raise ValueError("line_search_alphas must be a non-empty tuple")
        normalized_alphas: list[float] = []
        previous = math.inf
        for index, value in enumerate(self.line_search_alphas):
            alpha = _positive_float(value, f"line_search_alphas[{index}]")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized_alphas.append(alpha)
            previous = alpha
        if normalized_alphas[0] != 1.0:
            raise ValueError("line_search_alphas must start with 1")
        object.__setattr__(self, "line_search_alphas", tuple(normalized_alphas))

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
            "residual_relative_tolerance": self.residual_relative_tolerance,
            "residual_absolute_tolerance_kn": self.residual_absolute_tolerance_kn,
            "increment_relative_tolerance": self.increment_relative_tolerance,
            "increment_absolute_tolerance_m": self.increment_absolute_tolerance_m,
            "maximum_iterations": self.maximum_iterations,
            "maximum_condition_number": self.maximum_condition_number,
            "linear_solver": "numpy_dense_solve",
            "equation_scaling": "centroid_diameter_force_moment_6dof.v1",
            "condition_number": "scaled_matrix_1_norm",
            "load_control": "strictly_increasing_positive_factors",
            "line_search": {
                "policy": "strict_scaled_residual_decrease.v1",
                "alphas": list(self.line_search_alphas),
            },
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


@dataclass(frozen=True)
class CorotationalFrame3DGlobalCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    load_factor: float
    displacement: tuple[float, ...]
    converged_iterations: int
    residual_inf_norm_kn: float
    parent_checkpoint_hash: str | None
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["displacement"] = list(self.displacement)
        return payload


@dataclass(frozen=True)
class CorotationalFrame3DMemberResult:
    member_id: str
    node_i: int
    node_j: int
    initial_length_m: float
    current_length_m: float
    strain_energy_kn_m: float
    basic_deformations: tuple[float, ...]
    basic_forces: tuple[float, ...]
    global_end_forces: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorotationalFrame3DGlobalAssembly:
    displacement: np.ndarray
    internal_force: np.ndarray
    tangent: np.ndarray
    strain_energy_kn_m: float
    member_responses: tuple[CorotationalFrame3DResponse, ...]

    def __post_init__(self) -> None:
        size = self.displacement.size
        object.__setattr__(self, "displacement", _immutable(self.displacement, (size,)))
        object.__setattr__(
            self, "internal_force", _immutable(self.internal_force, (size,))
        )
        object.__setattr__(self, "tangent", _immutable(self.tangent, (size, size)))


@dataclass(frozen=True)
class CorotationalFrame3DGlobalStep:
    load_factor: float
    applied_load: tuple[float, ...]
    reactions: tuple[tuple[int, float], ...]
    free_residual_inf_norm_kn: float
    relative_residual: float
    condition_number: float
    raw_translational_residual_inf_norm_kn: float
    raw_rotational_residual_inf_norm_kn_m: float
    scaled_residual_inf_norm: float
    raw_translation_increment_inf_norm_m: float
    raw_rotation_increment_inf_norm_rad: float
    scaled_increment_inf_norm: float
    scaled_residual_tolerance: float
    scaled_increment_tolerance: float
    residual_gate_passed: bool
    increment_gate_passed: bool
    line_search_required: bool
    selected_line_search_alpha: float | None
    line_search_valid: bool
    final_reassembled_equilibrium_passed: bool
    parent_state_immutable: bool
    scaled_condition_number_1: float
    equation_scaling_hash: str
    convergence_history: tuple[dict[str, Any], ...]
    line_search_history: tuple[dict[str, Any], ...]
    checkpoint: CorotationalFrame3DGlobalCheckpoint
    members: tuple[CorotationalFrame3DMemberResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorotationalFrame3DGlobalSolution:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    start_checkpoint_hash: str
    steps: tuple[CorotationalFrame3DGlobalStep, ...]
    checkpoints: tuple[CorotationalFrame3DGlobalCheckpoint, ...]
    maximum_free_residual_inf_norm_kn: float
    maximum_scaled_residual_inf_norm: float
    maximum_scaled_increment_inf_norm: float
    equation_scaling: dict[str, Any]
    result_hash: str
    exact_checkpoint_resume_supported: bool
    regularization_used: bool
    fallback_used: bool
    contract_pass: bool
    claim_boundary: str

    @property
    def final_checkpoint(self) -> CorotationalFrame3DGlobalCheckpoint:
        return self.checkpoints[-1]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assemble_corotational_frame3d_global(
    model: CorotationalFrame3DModel,
    displacement: Iterable[float],
) -> CorotationalFrame3DGlobalAssembly:
    """Assemble all element forces and tangents in the shared global DOF space."""

    if type(model) is not CorotationalFrame3DModel:
        raise ValueError("model must be an exact CorotationalFrame3DModel")
    values = np.asarray(tuple(displacement), dtype=np.float64)
    if values.shape != (model.total_dofs,) or not np.all(np.isfinite(values)):
        raise ValueError(f"displacement must be a finite {model.total_dofs}-vector")
    internal = np.zeros(model.total_dofs, dtype=np.float64)
    tangent: np.ndarray = np.zeros(
        (model.total_dofs, model.total_dofs), dtype=np.float64
    )
    responses: list[CorotationalFrame3DResponse] = []
    energy = 0.0
    coordinates = np.asarray(model.node_coordinates_m, dtype=np.float64)
    for member in model.members:
        dofs = _member_dofs(member)
        response = corotational_frame3d_response(
            node_coordinates_m=coordinates[[member.node_i, member.node_j]],
            element_displacements=values[list(dofs)],
            section=member.section,
            local_axis_roll_deg=member.local_axis_roll_deg,
        )
        internal[list(dofs)] += response.internal_force_global
        tangent[np.ix_(dofs, dofs)] += response.consistent_tangent_global
        energy += response.strain_energy_kn_m
        responses.append(response)
    tangent = 0.5 * (tangent + tangent.T)
    if not (
        np.all(np.isfinite(internal))
        and np.all(np.isfinite(tangent))
        and math.isfinite(energy)
    ):
        raise CorotationalFrame3DGlobalError("global assembly produced non-finite data")
    return CorotationalFrame3DGlobalAssembly(
        displacement=values,
        internal_force=internal,
        tangent=tangent,
        strain_energy_kn_m=energy,
        member_responses=tuple(responses),
    )


def initial_corotational_frame3d_global_checkpoint(
    model: CorotationalFrame3DModel,
    *,
    config: CorotationalFrame3DGlobalConfig,
) -> CorotationalFrame3DGlobalCheckpoint:
    assembly = assemble_corotational_frame3d_global(
        model,
        np.zeros(model.total_dofs, dtype=np.float64),
    )
    residual = float(
        np.linalg.norm(assembly.internal_force[list(model.free_dofs)], ord=np.inf)
    )
    scaling = _equation_scaling(model)
    residual_metrics = scaled_residual_metrics_6dof(
        assembly.internal_force[list(model.free_dofs)],
        model.free_dofs,
        scaling,
    )
    tolerance = _scaled_residual_tolerance(config, scaling)
    if residual_metrics["scaled"] > tolerance:
        raise CorotationalFrame3DGlobalError(
            "zero state does not satisfy the unloaded equilibrium contract"
        )
    return _make_checkpoint(
        model=model,
        config=config,
        load_factor=0.0,
        displacement=assembly.displacement,
        converged_iterations=0,
        residual_inf_norm_kn=residual,
        parent_checkpoint_hash=None,
    )


def solve_corotational_frame3d_global_load_path(
    model: CorotationalFrame3DModel,
    load_factors: Iterable[float],
    *,
    config: CorotationalFrame3DGlobalConfig,
    resume_from: CorotationalFrame3DGlobalCheckpoint | None = None,
) -> CorotationalFrame3DGlobalSolution:
    """Solve a deterministic sequence of increasing load factors without fallback."""

    if type(model) is not CorotationalFrame3DModel:
        raise ValueError("model must be an exact CorotationalFrame3DModel")
    if type(config) is not CorotationalFrame3DGlobalConfig:
        raise ValueError("config must be an exact CorotationalFrame3DGlobalConfig")
    checkpoint = (
        initial_corotational_frame3d_global_checkpoint(model, config=config)
        if resume_from is None
        else validate_corotational_frame3d_global_checkpoint(
            resume_from,
            model=model,
            config=config,
            require_equilibrium=True,
        )
    )
    factors = _load_factors(load_factors, after=checkpoint.load_factor)
    scaling = _equation_scaling(model)
    checkpoints = [checkpoint]
    steps: list[CorotationalFrame3DGlobalStep] = []
    displacement = np.asarray(checkpoint.displacement, dtype=np.float64)
    for factor in factors:
        step = _solve_step(
            model,
            config,
            factor,
            displacement,
            scaling=scaling,
            parent_checkpoint=checkpoints[-1],
        )
        steps.append(step)
        checkpoints.append(step.checkpoint)
        displacement = np.asarray(step.checkpoint.displacement, dtype=np.float64)
    maximum_residual = max(
        (step.free_residual_inf_norm_kn for step in steps),
        default=checkpoint.residual_inf_norm_kn,
    )
    maximum_scaled_residual = max(
        (step.scaled_residual_inf_norm for step in steps),
        default=0.0,
    )
    maximum_scaled_increment = max(
        (step.scaled_increment_inf_norm for step in steps),
        default=0.0,
    )
    contract_pass = bool(
        steps
        and all(
            step.residual_gate_passed
            and step.increment_gate_passed
            and step.line_search_valid
            and step.final_reassembled_equilibrium_passed
            and step.parent_state_immutable
            for step in steps
        )
    )
    payload = {
        "schema_version": COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION,
        "profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
        "model_hash": model.model_hash,
        "solver_contract_hash": config.contract_hash,
        "start_checkpoint_hash": checkpoint.checkpoint_hash,
        "steps": [step.to_dict() for step in steps],
        "maximum_free_residual_inf_norm_kn": maximum_residual,
        "maximum_scaled_residual_inf_norm": maximum_scaled_residual,
        "maximum_scaled_increment_inf_norm": maximum_scaled_increment,
        "equation_scaling": scaling.to_manifest(),
        "exact_checkpoint_resume_supported": True,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
        "claim_boundary": COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY,
    }
    return CorotationalFrame3DGlobalSolution(
        schema_version=COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION,
        profile=COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=config.contract_hash,
        start_checkpoint_hash=checkpoint.checkpoint_hash,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        maximum_free_residual_inf_norm_kn=maximum_residual,
        maximum_scaled_residual_inf_norm=maximum_scaled_residual,
        maximum_scaled_increment_inf_norm=maximum_scaled_increment,
        equation_scaling=scaling.to_manifest(),
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=True,
        regularization_used=False,
        fallback_used=False,
        contract_pass=contract_pass,
        claim_boundary=COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY,
    )


def validate_corotational_frame3d_global_checkpoint(
    checkpoint: CorotationalFrame3DGlobalCheckpoint,
    *,
    model: CorotationalFrame3DModel,
    config: CorotationalFrame3DGlobalConfig,
    require_equilibrium: bool = True,
) -> CorotationalFrame3DGlobalCheckpoint:
    if type(checkpoint) is not CorotationalFrame3DGlobalCheckpoint:
        raise CorotationalFrame3DGlobalError("checkpoint type is invalid")
    if (
        checkpoint.schema_version
        != COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.profile != COROTATIONAL_FRAME3D_GLOBAL_PROFILE
        or checkpoint.model_hash != model.model_hash
        or checkpoint.solver_contract_hash != config.contract_hash
    ):
        raise CorotationalFrame3DGlobalError("checkpoint contract binding is invalid")
    values = np.asarray(checkpoint.displacement, dtype=np.float64)
    if values.shape != (model.total_dofs,) or not np.all(np.isfinite(values)):
        raise CorotationalFrame3DGlobalError("checkpoint displacement is invalid")
    if (
        not math.isfinite(checkpoint.load_factor)
        or checkpoint.load_factor < 0.0
        or type(checkpoint.converged_iterations) is not int
        or checkpoint.converged_iterations < 0
        or not math.isfinite(checkpoint.residual_inf_norm_kn)
        or checkpoint.residual_inf_norm_kn < 0.0
        or not _optional_hash(checkpoint.parent_checkpoint_hash)
    ):
        raise CorotationalFrame3DGlobalError("checkpoint scalar metadata is invalid")
    expected_hash = canonical_hash(_checkpoint_payload(checkpoint, include_hash=False))
    if checkpoint.checkpoint_hash != expected_hash:
        raise CorotationalFrame3DGlobalError("checkpoint hash mismatch")
    if require_equilibrium:
        assembly = assemble_corotational_frame3d_global(model, values)
        external = checkpoint.load_factor * np.asarray(model.reference_load_kn)
        residual = assembly.internal_force - external
        free_values = residual[list(model.free_dofs)]
        free_residual = float(np.linalg.norm(free_values, ord=np.inf))
        scaling = _equation_scaling(model)
        residual_metrics = scaled_residual_metrics_6dof(
            free_values,
            model.free_dofs,
            scaling,
        )
        tolerance = _scaled_residual_tolerance(config, scaling)
        if residual_metrics["scaled"] > tolerance:
            raise CorotationalFrame3DGlobalError(
                "checkpoint free-equation equilibrium is invalid"
            )
        comparison_tolerance = max(
            1.0e-12,
            1.0e-12
            * max(
                abs(free_residual),
                abs(checkpoint.residual_inf_norm_kn),
                1.0,
            ),
        )
        if abs(free_residual - checkpoint.residual_inf_norm_kn) > comparison_tolerance:
            raise CorotationalFrame3DGlobalError(
                "checkpoint residual observation is inconsistent"
            )
    return checkpoint


def _solve_step(
    model: CorotationalFrame3DModel,
    config: CorotationalFrame3DGlobalConfig,
    factor: float,
    initial_displacement: np.ndarray,
    *,
    scaling: EquationScaling6DOF,
    parent_checkpoint: CorotationalFrame3DGlobalCheckpoint,
) -> CorotationalFrame3DGlobalStep:
    displacement = np.array(initial_displacement, dtype=np.float64, copy=True)
    free = np.asarray(model.free_dofs, dtype=np.int64)
    applied = factor * np.asarray(model.reference_load_kn, dtype=np.float64)
    residual_tolerance = _scaled_residual_tolerance(config, scaling)
    increment_tolerance = _scaled_increment_tolerance(config, scaling)
    convergence_history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    selected_line_search_alpha: float | None = None
    line_search_required = False
    parent_checkpoint_hash = parent_checkpoint.checkpoint_hash
    parent_displacement = parent_checkpoint.displacement
    for iteration in range(config.maximum_iterations + 1):
        assembly = assemble_corotational_frame3d_global(model, displacement)
        residual = assembly.internal_force - applied
        free_values = residual[free]
        free_residual = float(np.linalg.norm(free_values, ord=np.inf))
        residual_metrics = scaled_residual_metrics_6dof(
            free_values,
            model.free_dofs,
            scaling,
        )
        tangent_free = assembly.tangent[np.ix_(free, free)]
        scaled_tangent, scaled_rhs, recovery_scale = scale_linear_system_6dof(
            tangent_free,
            -free_values,
            model.free_dofs,
            scaling,
        )
        condition_number = float(np.linalg.cond(scaled_tangent, p=1))
        if (
            not math.isfinite(condition_number)
            or condition_number > config.maximum_condition_number
        ):
            raise CorotationalFrame3DGlobalError(
                "free tangent is singular or exceeds the conditioning policy"
            )
        try:
            correction = recovery_scale * np.linalg.solve(
                scaled_tangent,
                scaled_rhs,
            )
        except np.linalg.LinAlgError as error:
            raise CorotationalFrame3DGlobalError(
                "free tangent factorization failed without fallback"
            ) from error
        if not np.all(np.isfinite(correction)):
            raise CorotationalFrame3DGlobalError("Newton correction is non-finite")
        increment_metrics = scaled_increment_metrics_6dof(
            correction,
            model.free_dofs,
            scaling,
        )
        residual_gate = residual_metrics["scaled"] <= residual_tolerance
        increment_gate = increment_metrics["scaled"] <= increment_tolerance
        convergence_row: dict[str, Any] = {
            "iteration": iteration,
            "scaled_residual_inf_norm": residual_metrics["scaled"],
            "scaled_residual_tolerance": residual_tolerance,
            "scaled_increment_inf_norm": increment_metrics["scaled"],
            "scaled_increment_tolerance": increment_tolerance,
            "residual_gate_passed": residual_gate,
            "increment_gate_passed": increment_gate,
            "scaled_condition_number_1": condition_number,
        }
        if residual_gate and increment_gate:
            convergence_row["accepted"] = True
            convergence_row["selected_line_search_alpha"] = None
            convergence_history.append(convergence_row)
            final_assembly = assemble_corotational_frame3d_global(
                model,
                displacement,
            )
            final_residual = final_assembly.internal_force - applied
            final_free_values = final_residual[free]
            final_metrics = scaled_residual_metrics_6dof(
                final_free_values,
                model.free_dofs,
                scaling,
            )
            final_reassembled_equilibrium = bool(
                final_metrics["scaled"] <= residual_tolerance
                and np.array_equal(final_assembly.displacement, assembly.displacement)
                and np.array_equal(
                    final_assembly.internal_force,
                    assembly.internal_force,
                )
                and np.array_equal(final_assembly.tangent, assembly.tangent)
            )
            parent_immutable = bool(
                parent_checkpoint.checkpoint_hash == parent_checkpoint_hash
                and parent_checkpoint.displacement == parent_displacement
            )
            line_search_valid = bool(
                not line_search_required or selected_line_search_alpha is not None
            )
            if not (
                final_reassembled_equilibrium
                and parent_immutable
                and line_search_valid
            ):
                raise CorotationalFrame3DGlobalError(
                    "final Frame3D convergence contract failed before commit"
                )
            relative_residual = residual_metrics["scaled"]
            checkpoint = _make_checkpoint(
                model=model,
                config=config,
                load_factor=factor,
                displacement=displacement,
                converged_iterations=iteration,
                residual_inf_norm_kn=free_residual,
                parent_checkpoint_hash=parent_checkpoint.checkpoint_hash,
            )
            reactions = tuple(
                (dof, float(residual[dof])) for dof in model.restrained_dofs
            )
            return CorotationalFrame3DGlobalStep(
                load_factor=factor,
                applied_load=tuple(float(value) for value in applied),
                reactions=reactions,
                free_residual_inf_norm_kn=free_residual,
                relative_residual=relative_residual,
                condition_number=condition_number,
                raw_translational_residual_inf_norm_kn=residual_metrics[
                    "translation"
                ],
                raw_rotational_residual_inf_norm_kn_m=residual_metrics[
                    "rotation"
                ],
                scaled_residual_inf_norm=residual_metrics["scaled"],
                raw_translation_increment_inf_norm_m=increment_metrics[
                    "translation"
                ],
                raw_rotation_increment_inf_norm_rad=increment_metrics[
                    "rotation"
                ],
                scaled_increment_inf_norm=increment_metrics["scaled"],
                scaled_residual_tolerance=residual_tolerance,
                scaled_increment_tolerance=increment_tolerance,
                residual_gate_passed=True,
                increment_gate_passed=True,
                line_search_required=line_search_required,
                selected_line_search_alpha=selected_line_search_alpha,
                line_search_valid=line_search_valid,
                final_reassembled_equilibrium_passed=(
                    final_reassembled_equilibrium
                ),
                parent_state_immutable=parent_immutable,
                scaled_condition_number_1=condition_number,
                equation_scaling_hash=scaling.scaling_hash,
                convergence_history=tuple(convergence_history),
                line_search_history=tuple(line_search_history),
                checkpoint=checkpoint,
                members=_recover_members(model, final_assembly),
            )
        if iteration == config.maximum_iterations:
            convergence_row["accepted"] = False
            convergence_row["selected_line_search_alpha"] = None
            convergence_history.append(convergence_row)
            break
        line_search_required = True
        attempts: list[dict[str, Any]] = []
        selected_displacement: np.ndarray | None = None
        selected_line_search_alpha = None
        for alpha in config.line_search_alphas:
            candidate = displacement.copy()
            candidate[free] += alpha * correction
            try:
                trial = assemble_corotational_frame3d_global(model, candidate)
            except (
                CorotationalFrame3DGlobalError,
                ValueError,
                FloatingPointError,
            ) as error:
                attempts.append(
                    {
                        "alpha": alpha,
                        "accepted": False,
                        "admissible": False,
                        "reason": type(error).__name__,
                    }
                )
                continue
            trial_residual = trial.internal_force - applied
            trial_metrics = scaled_residual_metrics_6dof(
                trial_residual[free],
                model.free_dofs,
                scaling,
            )
            accepted = bool(
                math.isfinite(trial_metrics["scaled"])
                and trial_metrics["scaled"] < residual_metrics["scaled"]
            )
            attempts.append(
                {
                    "alpha": alpha,
                    "accepted": accepted,
                    "admissible": True,
                    "trial_scaled_residual_inf_norm": trial_metrics["scaled"],
                }
            )
            if accepted:
                selected_line_search_alpha = alpha
                selected_displacement = candidate
                break
        line_search_history.append(
            {
                "iteration": iteration,
                "selected_alpha": selected_line_search_alpha,
                "attempts": tuple(attempts),
            }
        )
        convergence_row["selected_line_search_alpha"] = selected_line_search_alpha
        convergence_row["accepted"] = selected_displacement is not None
        convergence_history.append(convergence_row)
        if selected_displacement is None:
            raise CorotationalFrame3DGlobalError(
                "line search failed to produce an admissible "
                "scaled-residual-decreasing trial"
            )
        displacement = selected_displacement
    raise CorotationalFrame3DGlobalError(
        f"load factor {factor} did not converge in {config.maximum_iterations} iterations"
    )


def _recover_members(
    model: CorotationalFrame3DModel,
    assembly: CorotationalFrame3DGlobalAssembly,
) -> tuple[CorotationalFrame3DMemberResult, ...]:
    rows: list[CorotationalFrame3DMemberResult] = []
    for member, response in zip(
        model.members,
        assembly.member_responses,
        strict=True,
    ):
        rows.append(
            CorotationalFrame3DMemberResult(
                member_id=member.member_id,
                node_i=member.node_i,
                node_j=member.node_j,
                initial_length_m=response.initial_length_m,
                current_length_m=response.current_length_m,
                strain_energy_kn_m=response.strain_energy_kn_m,
                basic_deformations=tuple(
                    float(value) for value in response.basic_deformations
                ),
                basic_forces=tuple(float(value) for value in response.basic_forces),
                global_end_forces=tuple(
                    float(value) for value in response.internal_force_global
                ),
            )
        )
    return tuple(rows)


def _make_checkpoint(
    *,
    model: CorotationalFrame3DModel,
    config: CorotationalFrame3DGlobalConfig,
    load_factor: float,
    displacement: np.ndarray,
    converged_iterations: int,
    residual_inf_norm_kn: float,
    parent_checkpoint_hash: str | None,
) -> CorotationalFrame3DGlobalCheckpoint:
    provisional = CorotationalFrame3DGlobalCheckpoint(
        schema_version=COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION,
        profile=COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=config.contract_hash,
        load_factor=float(load_factor),
        displacement=tuple(float(value) for value in displacement),
        converged_iterations=converged_iterations,
        residual_inf_norm_kn=float(residual_inf_norm_kn),
        parent_checkpoint_hash=parent_checkpoint_hash,
        checkpoint_hash=_ZERO_HASH,
    )
    checkpoint = replace(
        provisional,
        checkpoint_hash=canonical_hash(
            _checkpoint_payload(provisional, include_hash=False)
        ),
    )
    return validate_corotational_frame3d_global_checkpoint(
        checkpoint,
        model=model,
        config=config,
        require_equilibrium=False,
    )


def _checkpoint_payload(
    checkpoint: CorotationalFrame3DGlobalCheckpoint,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = checkpoint.to_dict()
    if not include_hash:
        payload.pop("checkpoint_hash")
    return payload


def _member_dofs(member: CorotationalFrame3DMember) -> tuple[int, ...]:
    start = 6 * member.node_i
    end = 6 * member.node_j
    return tuple(range(start, start + 6)) + tuple(range(end, end + 6))


def _load_factors(values: Iterable[float], *, after: float) -> tuple[float, ...]:
    factors = tuple(
        _finite_float(value, f"load_factors[{index}]")
        for index, value in enumerate(values)
    )
    if not factors:
        raise ValueError("load_factors must not be empty")
    previous = after
    for factor in factors:
        if factor <= previous:
            raise ValueError(
                "load_factors must be strictly increasing after checkpoint"
            )
        previous = factor
    return factors


def _scaled_residual_tolerance(
    config: CorotationalFrame3DGlobalConfig,
    scaling: EquationScaling6DOF,
) -> float:
    return (
        config.residual_absolute_tolerance_kn / scaling.reference_force
        + config.residual_relative_tolerance
    )


def _scaled_increment_tolerance(
    config: CorotationalFrame3DGlobalConfig,
    scaling: EquationScaling6DOF,
) -> float:
    return (
        config.increment_absolute_tolerance_m / scaling.characteristic_length_m
        + config.increment_relative_tolerance
    )


def _equation_scaling(model: CorotationalFrame3DModel) -> EquationScaling6DOF:
    return create_equation_scaling_6dof(
        source_identity_hash=model.model_hash,
        node_coordinates_m=model.node_coordinates_m,
        reference_equation_load=model.reference_load_kn,
        free_dofs=model.free_dofs,
    )


def _validate_connected_graph(
    node_count: int,
    members: tuple[CorotationalFrame3DMember, ...],
) -> None:
    adjacency: list[set[int]] = [set() for _ in range(node_count)]
    for member in members:
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
        raise ValueError("frame3d graph must be connected and include every node")


def _optional_hash(value: str | None) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _positive_float(value: Any, name: str) -> float:
    normalized = _finite_float(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _immutable(value: Any, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"array must be finite with shape {shape}")
    result = np.array(array, copy=True)
    result.setflags(write=False)
    return result


__all__ = [
    "COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION",
    "COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY",
    "COROTATIONAL_FRAME3D_GLOBAL_PROFILE",
    "COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION",
    "CorotationalFrame3DGlobalAssembly",
    "CorotationalFrame3DGlobalCheckpoint",
    "CorotationalFrame3DGlobalConfig",
    "CorotationalFrame3DGlobalError",
    "CorotationalFrame3DGlobalSolution",
    "CorotationalFrame3DGlobalStep",
    "CorotationalFrame3DMember",
    "CorotationalFrame3DMemberResult",
    "CorotationalFrame3DModel",
    "assemble_corotational_frame3d_global",
    "initial_corotational_frame3d_global_checkpoint",
    "solve_corotational_frame3d_global_load_path",
    "validate_corotational_frame3d_global_checkpoint",
]
