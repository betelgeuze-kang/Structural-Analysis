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
from structural_analysis.solvers.equation_scaling import (
    EquationScaling6DOF,
    EquationScaling6DOFTransform,
    characteristic_length_from_coordinates,
    frame3d_dof_labels,
    make_equation_scaling_6dof,
    reference_force_from_mixed_load,
)


COROTATIONAL_FRAME3D_GLOBAL_PROFILE = (
    "dense_elastic_corotational_timoshenko_frame3d_load_control.v1"
)
COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION = "corotational-frame3d-global-solution.v1"
COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION = (
    "corotational-frame3d-global-checkpoint.v1"
)
COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY = (
    "Small dense elastic 3D frame verification path using the numerical-energy "
    "element tangent, explicit nodal loads and restraints, and exact checkpoint "
    "lineage. It has no stateful section, distributed load, release/offset, "
    "warping coupling, transient dynamics, external V&V, or release authority."
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
    increment_relative_tolerance: float = 1.0e-8
    increment_absolute_tolerance_m: float = 1.0e-10
    maximum_iterations: int = 20
    maximum_condition_number: float = 1.0e14
    maximum_line_search_iterations: int = 12
    line_search_reduction_factor: float = 0.5
    line_search_minimum_alpha: float = 2.0**-12
    line_search_sufficient_decrease: float = 1.0e-4
    reference_force_floor_kn: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "residual_relative_tolerance",
            "residual_absolute_tolerance_kn",
            "increment_relative_tolerance",
            "increment_absolute_tolerance_m",
            "maximum_condition_number",
            "reference_force_floor_kn",
        ):
            value = _positive_float(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be a positive integer")
        if (
            type(self.maximum_line_search_iterations) is not int
            or self.maximum_line_search_iterations < 1
        ):
            raise ValueError(
                "maximum_line_search_iterations must be a positive integer"
            )
        for name in (
            "line_search_reduction_factor",
            "line_search_minimum_alpha",
            "line_search_sufficient_decrease",
        ):
            object.__setattr__(
                self,
                name,
                _finite_float(getattr(self, name), name),
            )
        if not 0.0 < self.line_search_reduction_factor < 1.0:
            raise ValueError("line_search_reduction_factor must be in (0, 1)")
        if not 0.0 < self.line_search_minimum_alpha <= 1.0:
            raise ValueError("line_search_minimum_alpha must be in (0, 1]")
        if not 0.0 < self.line_search_sufficient_decrease < 1.0:
            raise ValueError("line_search_sufficient_decrease must be in (0, 1)")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
            "residual_relative_tolerance": self.residual_relative_tolerance,
            "residual_absolute_tolerance_kn": self.residual_absolute_tolerance_kn,
            "increment_relative_tolerance": self.increment_relative_tolerance,
            "increment_absolute_tolerance_m": (
                self.increment_absolute_tolerance_m
            ),
            "maximum_iterations": self.maximum_iterations,
            "maximum_condition_number": self.maximum_condition_number,
            "reference_force_floor_kn": self.reference_force_floor_kn,
            "linear_solver": "numpy_dense_solve",
            "load_control": "strictly_increasing_positive_factors",
            "equation_scaling": (
                "force_moment_translation_rotation_diagonal_6dof.v1"
            ),
            "line_search": {
                "algorithm": "backtracking_armijo_scaled_residual.v1",
                "maximum_iterations": self.maximum_line_search_iterations,
                "reduction_factor": self.line_search_reduction_factor,
                "minimum_alpha": self.line_search_minimum_alpha,
                "sufficient_decrease": self.line_search_sufficient_decrease,
                "invalid_geometry_trial": "reject_and_backtrack",
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
    equation_scaling: EquationScaling6DOF
    accepted_line_search_alphas: tuple[float, ...]
    convergence_checks: dict[str, bool]
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
    equation_scaling_hashes: tuple[str, ...]
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
    tangent = np.zeros((model.total_dofs, model.total_dofs), dtype=np.float64)
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
    scaling = _equation_scaling(model, config)
    residual_free = assembly.internal_force[list(model.free_dofs)]
    scaled_residual = float(
        np.linalg.norm(scaling.scale_residual(residual_free), ord=np.inf)
    )
    if scaled_residual > _scaled_residual_tolerance(config, scaling):
        raise CorotationalFrame3DGlobalError(
            "zero state does not satisfy the unloaded equilibrium contract"
        )
    residual = _translation_component_norm(residual_free, scaling.dof_labels)
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
    checkpoints = [checkpoint]
    steps: list[CorotationalFrame3DGlobalStep] = []
    displacement = np.asarray(checkpoint.displacement, dtype=np.float64)
    for factor in factors:
        step = _solve_step(
            model,
            config,
            factor,
            displacement,
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
        (step.equation_scaling.scaled_residual_norm for step in steps),
        default=0.0,
    )
    maximum_scaled_increment = max(
        (step.equation_scaling.scaled_increment_norm for step in steps),
        default=0.0,
    )
    scaling_hashes = tuple(
        dict.fromkeys(step.equation_scaling.scaling_hash for step in steps)
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
        "equation_scaling_hashes": list(scaling_hashes),
        "exact_checkpoint_resume_supported": True,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": True,
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
        equation_scaling_hashes=scaling_hashes,
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=True,
        regularization_used=False,
        fallback_used=False,
        contract_pass=True,
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
        scaling = _equation_scaling(model, config)
        residual_free = residual[list(model.free_dofs)]
        scaled_residual = float(
            np.linalg.norm(scaling.scale_residual(residual_free), ord=np.inf)
        )
        if scaled_residual > _scaled_residual_tolerance(config, scaling):
            raise CorotationalFrame3DGlobalError(
                "checkpoint free-equation equilibrium is invalid"
            )
        free_residual = _translation_component_norm(
            residual_free,
            scaling.dof_labels,
        )
        comparison_tolerance = max(
            config.residual_absolute_tolerance_kn,
            1.0e-12,
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
    parent_checkpoint: CorotationalFrame3DGlobalCheckpoint,
) -> CorotationalFrame3DGlobalStep:
    displacement = np.array(initial_displacement, dtype=np.float64, copy=True)
    free = np.asarray(model.free_dofs, dtype=np.int64)
    applied = factor * np.asarray(model.reference_load_kn, dtype=np.float64)
    scaling = _equation_scaling(model, config)
    residual_tolerance = _scaled_residual_tolerance(config, scaling)
    increment_tolerance = _scaled_increment_tolerance(config, scaling)
    accepted_alphas: list[float] = []
    for iteration in range(config.maximum_iterations + 1):
        try:
            assembly = assemble_corotational_frame3d_global(model, displacement)
        except (ValueError, FloatingPointError) as error:
            raise CorotationalFrame3DGlobalError(
                f"invalid geometry trial at iteration {iteration}"
            ) from error
        residual = assembly.internal_force - applied
        residual_free = residual[free]
        tangent_free = assembly.tangent[np.ix_(free, free)]
        scaled_tangent = scaling.scale_tangent(tangent_free)
        scaled_residual = scaling.scale_residual(residual_free)
        condition_number = float(np.linalg.cond(scaled_tangent, p=1))
        if (
            not math.isfinite(condition_number)
            or condition_number > config.maximum_condition_number
        ):
            raise CorotationalFrame3DGlobalError(
                "scaled free tangent is singular or exceeds the conditioning policy"
            )
        try:
            scaled_correction = np.linalg.solve(
                scaled_tangent,
                -scaled_residual,
            )
        except np.linalg.LinAlgError as error:
            raise CorotationalFrame3DGlobalError(
                "scaled free tangent factorization failed without fallback"
            ) from error
        if not np.all(np.isfinite(scaled_correction)):
            raise CorotationalFrame3DGlobalError(
                "scaled Newton correction is non-finite"
            )
        correction = scaling.unscale_increment(scaled_correction)
        observation = scaling.observe(
            residual=residual_free,
            increment=correction,
            scaled_tangent_condition=condition_number,
        )
        residual_gate = bool(
            observation.scaled_residual_norm <= residual_tolerance
        )
        increment_gate = bool(
            observation.scaled_increment_norm <= increment_tolerance
        )
        if residual_gate and increment_gate:
            final_assembly = assemble_corotational_frame3d_global(
                model,
                displacement,
            )
            final_residual = final_assembly.internal_force - applied
            final_residual_free = final_residual[free]
            final_scaled_residual = float(
                np.linalg.norm(
                    scaling.scale_residual(final_residual_free),
                    ord=np.inf,
                )
            )
            final_reassembled = bool(
                np.array_equal(
                    final_assembly.internal_force,
                    assembly.internal_force,
                )
                and np.array_equal(final_assembly.tangent, assembly.tangent)
                and final_scaled_residual <= residual_tolerance
            )
            checks = {
                "scaled_residual_gate": residual_gate,
                "scaled_increment_gate": increment_gate,
                "line_search_step_valid": all(
                    config.line_search_minimum_alpha <= alpha <= 1.0
                    for alpha in accepted_alphas
                ),
                "final_reassembled_equilibrium": final_reassembled,
                "scaled_condition_number_pass": bool(
                    condition_number <= config.maximum_condition_number
                ),
                "regularization_not_used": True,
                "fallback_not_used": True,
            }
            if not all(checks.values()):
                failed = ",".join(
                    name for name, passed in checks.items() if not passed
                )
                raise CorotationalFrame3DGlobalError(
                    f"dense Frame3D convergence commit contract failed: {failed}"
                )
            free_residual = _translation_component_norm(
                final_residual_free,
                scaling.dof_labels,
            )
            checkpoint = _make_checkpoint(
                model=model,
                config=config,
                load_factor=factor,
                displacement=displacement,
                converged_iterations=iteration,
                residual_inf_norm_kn=free_residual,
                parent_checkpoint_hash=parent_checkpoint.checkpoint_hash,
            )
            validate_corotational_frame3d_global_checkpoint(
                checkpoint,
                model=model,
                config=config,
                require_equilibrium=True,
            )
            reactions = tuple(
                (dof, float(final_residual[dof]))
                for dof in model.restrained_dofs
            )
            return CorotationalFrame3DGlobalStep(
                load_factor=factor,
                applied_load=tuple(float(value) for value in applied),
                reactions=reactions,
                free_residual_inf_norm_kn=free_residual,
                relative_residual=observation.scaled_residual_norm,
                condition_number=condition_number,
                equation_scaling=observation,
                accepted_line_search_alphas=tuple(accepted_alphas),
                convergence_checks=checks,
                checkpoint=checkpoint,
                members=_recover_members(model, final_assembly),
            )
        if iteration == config.maximum_iterations:
            break
        selected_alpha: float | None = None
        selected_displacement: np.ndarray | None = None
        alpha = 1.0
        for _ in range(config.maximum_line_search_iterations):
            if alpha + 1.0e-15 < config.line_search_minimum_alpha:
                break
            trial = np.array(displacement, dtype=np.float64, copy=True)
            trial[free] += alpha * correction
            try:
                candidate = assemble_corotational_frame3d_global(model, trial)
            except (ValueError, FloatingPointError):
                alpha *= config.line_search_reduction_factor
                continue
            candidate_residual = candidate.internal_force[free] - applied[free]
            candidate_scaled = float(
                np.linalg.norm(
                    scaling.scale_residual(candidate_residual),
                    ord=np.inf,
                )
            )
            required = (
                1.0 - config.line_search_sufficient_decrease * alpha
            ) * observation.scaled_residual_norm
            if candidate_scaled <= residual_tolerance or candidate_scaled <= required:
                selected_alpha = alpha
                selected_displacement = trial
                break
            alpha *= config.line_search_reduction_factor
        if selected_alpha is None or selected_displacement is None:
            raise CorotationalFrame3DGlobalError(
                "line_search_failed_to_reduce_scaled_residual_without_fallback"
            )
        accepted_alphas.append(selected_alpha)
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


def _equation_scaling(
    model: CorotationalFrame3DModel,
    config: CorotationalFrame3DGlobalConfig,
) -> EquationScaling6DOFTransform:
    free = model.free_dofs
    labels = frame3d_dof_labels(free)
    characteristic_length = characteristic_length_from_coordinates(
        model.node_coordinates_m
    )
    free_load = np.asarray(model.reference_load_kn, dtype=np.float64)[
        list(free)
    ]
    reference_force = reference_force_from_mixed_load(
        free_load,
        characteristic_length=characteristic_length,
        dof_labels=labels,
        minimum_reference_force=config.reference_force_floor_kn,
    )
    return make_equation_scaling_6dof(
        reference_force=reference_force,
        characteristic_length=characteristic_length,
        dof_labels=labels,
    )


def _scaled_residual_tolerance(
    config: CorotationalFrame3DGlobalConfig,
    scaling: EquationScaling6DOFTransform,
) -> float:
    return config.residual_relative_tolerance + (
        config.residual_absolute_tolerance_kn / scaling.reference_force
    )


def _scaled_increment_tolerance(
    config: CorotationalFrame3DGlobalConfig,
    scaling: EquationScaling6DOFTransform,
) -> float:
    return config.increment_relative_tolerance + (
        config.increment_absolute_tolerance_m / scaling.characteristic_length
    )


def _translation_component_norm(
    values: Any,
    labels: tuple[str, ...],
) -> float:
    vector = np.asarray(values, dtype=np.float64)
    mask = np.asarray(
        [label in {"UX", "UY", "UZ"} for label in labels],
        dtype=bool,
    )
    selected = vector[mask]
    return float(np.linalg.norm(selected, ord=np.inf)) if selected.size else 0.0


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
