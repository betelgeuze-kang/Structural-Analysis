"""Bounded small-displacement global assembly for stateful 2D fiber beams."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.elements.stateful_fiber_beam2d import (
    StatefulFiberBeam2D,
    StatefulFiberBeam2DResponse,
    StatefulFiberBeam2DState,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
)


STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION = "stateful-fiber-frame2d-assembly.v1"
STATEFUL_FIBER_FRAME2D_TRANSFORMATION = (
    "u_local=T_initial_chord*u_global;f_global=T_transpose*f_local;"
    "K_global=T_transpose*K_local*T"
)


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _positive(value: Any, *, name: str) -> float:
    normalized = _finite(value, name=name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _readonly(array: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(array, dtype=np.float64)
    result.setflags(write=False)
    return result


def small_displacement_frame2d_transformation(
    node_coordinates_m: Any,
) -> np.ndarray:
    """Return the fixed initial-chord global-to-local ``6 x 6`` transform."""

    try:
        coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("node_coordinates_m must be a finite 2x2 array") from exc
    if coordinates.shape != (2, 2) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2x2 array")
    chord = coordinates[1] - coordinates[0]
    length = float(np.linalg.norm(chord))
    if length <= np.finfo(np.float64).eps:
        raise ValueError("frame member nodes must not coincide")
    cosine = float(chord[0] / length)
    sine = float(chord[1] / length)
    transformation = np.asarray(
        [
            [cosine, sine, 0.0, 0.0, 0.0, 0.0],
            [-sine, cosine, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, cosine, sine, 0.0],
            [0.0, 0.0, 0.0, -sine, cosine, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    transformation.setflags(write=False)
    return transformation


@dataclass(frozen=True)
class StatefulFiberFrame2DMember:
    member_id: str
    node_i: int
    node_j: int
    element: StatefulFiberBeam2D

    def __post_init__(self) -> None:
        normalized_id = str(self.member_id).strip()
        if not normalized_id:
            raise ValueError("member_id must be non-empty")
        object.__setattr__(self, "member_id", normalized_id)
        if (
            type(self.node_i) is not int
            or type(self.node_j) is not int
            or self.node_i < 0
            or self.node_j < 0
            or self.node_i == self.node_j
        ):
            raise ValueError("member node indices must be distinct and non-negative")
        if type(self.element) is not StatefulFiberBeam2D:
            raise ValueError("member element must be a StatefulFiberBeam2D")
        if self.element.element_id != normalized_id:
            raise ValueError("member_id must match element.element_id")


@dataclass(frozen=True)
class StatefulFiberFrame2DProblem:
    case_id: str
    node_coordinates_m: tuple[tuple[float, float], ...]
    members: tuple[StatefulFiberFrame2DMember, ...]
    fixed_global_dofs: tuple[int, ...]
    reference_external_loads: tuple[tuple[int, float], ...]
    rotation_coordinate_scale_m: float

    def __post_init__(self) -> None:
        normalized_case_id = str(self.case_id).strip()
        if not normalized_case_id:
            raise ValueError("case_id must be non-empty")
        object.__setattr__(self, "case_id", normalized_case_id)
        if (
            not isinstance(self.node_coordinates_m, tuple)
            or len(self.node_coordinates_m) < 2
        ):
            raise ValueError("node_coordinates_m must contain at least two nodes")
        coordinates: list[tuple[float, float]] = []
        for row in self.node_coordinates_m:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("each node coordinate must be an (x, y) tuple")
            coordinates.append(
                (
                    _finite(row[0], name="node x coordinate"),
                    _finite(row[1], name="node y coordinate"),
                )
            )
        object.__setattr__(self, "node_coordinates_m", tuple(coordinates))
        if not isinstance(self.members, tuple) or not self.members:
            raise ValueError("members must be a non-empty tuple")
        if not all(
            type(member) is StatefulFiberFrame2DMember for member in self.members
        ):
            raise ValueError("members contains an invalid member")
        member_ids: set[str] = set()
        node_count = len(coordinates)
        for member in self.members:
            if member.member_id in member_ids:
                raise ValueError("member_id values must be unique")
            member_ids.add(member.member_id)
            if member.node_i >= node_count or member.node_j >= node_count:
                raise ValueError("member node index is out of range")
            point_i = np.asarray(coordinates[member.node_i], dtype=np.float64)
            point_j = np.asarray(coordinates[member.node_j], dtype=np.float64)
            geometry_length = float(np.linalg.norm(point_j - point_i))
            if not math.isclose(
                geometry_length,
                member.element.length_m,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            ):
                raise ValueError("member element length does not match node geometry")
        global_dof_count = 3 * node_count
        if not isinstance(self.fixed_global_dofs, tuple) or not self.fixed_global_dofs:
            raise ValueError("fixed_global_dofs must be a non-empty tuple")
        if any(type(dof) is not int for dof in self.fixed_global_dofs):
            raise ValueError("fixed_global_dofs must contain integers")
        fixed = tuple(sorted(set(self.fixed_global_dofs)))
        if len(fixed) != len(self.fixed_global_dofs):
            raise ValueError("fixed_global_dofs must be unique")
        if fixed[0] < 0 or fixed[-1] >= global_dof_count:
            raise ValueError("fixed global DOF is out of range")
        object.__setattr__(self, "fixed_global_dofs", fixed)
        if not isinstance(self.reference_external_loads, tuple):
            raise ValueError("reference_external_loads must be a tuple")
        loads: list[tuple[int, float]] = []
        load_dofs: set[int] = set()
        for row in self.reference_external_loads:
            if not isinstance(row, tuple) or len(row) != 2 or type(row[0]) is not int:
                raise ValueError("each reference external load must be (dof, value)")
            dof = row[0]
            if dof < 0 or dof >= global_dof_count:
                raise ValueError("reference external load DOF is out of range")
            if dof in load_dofs:
                raise ValueError("reference external load DOFs must be unique")
            load_dofs.add(dof)
            loads.append((dof, _finite(row[1], name="reference external load")))
        if not loads or not any(value != 0.0 for _, value in loads):
            raise ValueError("reference_external_loads must include a nonzero load")
        object.__setattr__(
            self,
            "reference_external_loads",
            tuple(sorted(loads)),
        )
        object.__setattr__(
            self,
            "rotation_coordinate_scale_m",
            _positive(
                self.rotation_coordinate_scale_m,
                name="rotation_coordinate_scale_m",
            ),
        )

    @property
    def global_dof_count(self) -> int:
        return 3 * len(self.node_coordinates_m)

    @property
    def free_global_dofs(self) -> tuple[int, ...]:
        fixed = set(self.fixed_global_dofs)
        return tuple(dof for dof in range(self.global_dof_count) if dof not in fixed)

    @property
    def physical_coordinate_scale(self) -> np.ndarray:
        scale = np.ones(self.global_dof_count, dtype=np.float64)
        scale[2::3] = 1.0 / self.rotation_coordinate_scale_m
        scale.setflags(write=False)
        return scale

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            {
                "schema_version": STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION,
                "case_id": self.case_id,
                "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
                "members": [
                    {
                        "member_id": member.member_id,
                        "node_i": member.node_i,
                        "node_j": member.node_j,
                        "element_contract_hash": member.element.contract_hash,
                    }
                    for member in self.members
                ],
                "fixed_global_dofs": list(self.fixed_global_dofs),
                "reference_external_loads": [
                    [dof, value] for dof, value in self.reference_external_loads
                ],
                "rotation_coordinate_scale_m": self.rotation_coordinate_scale_m,
                "transformation": STATEFUL_FIBER_FRAME2D_TRANSFORMATION,
            }
        )

    def member_global_dofs(
        self,
        member: StatefulFiberFrame2DMember,
    ) -> tuple[int, ...]:
        return (
            3 * member.node_i,
            3 * member.node_i + 1,
            3 * member.node_i + 2,
            3 * member.node_j,
            3 * member.node_j + 1,
            3 * member.node_j + 2,
        )

    def member_transformation(
        self,
        member: StatefulFiberFrame2DMember,
    ) -> np.ndarray:
        return small_displacement_frame2d_transformation(
            (
                self.node_coordinates_m[member.node_i],
                self.node_coordinates_m[member.node_j],
            )
        )

    def reference_external_load_vector(self) -> np.ndarray:
        external = np.zeros(self.global_dof_count, dtype=np.float64)
        for dof, value in self.reference_external_loads:
            external[dof] = value
        external.setflags(write=False)
        return external

    def reference_force_scale(self) -> float:
        generalized = (
            self.physical_coordinate_scale * self.reference_external_load_vector()
        )
        return max(float(np.linalg.norm(generalized, ord=np.inf)), 1.0)


@dataclass(frozen=True)
class StatefulFiberFrame2DMemberAssembly:
    member_id: str
    global_dofs: tuple[int, ...]
    transformation_global_to_local: np.ndarray
    internal_load_global: np.ndarray
    consistent_tangent_global: np.ndarray
    response: StatefulFiberBeam2DResponse

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "global_dofs": list(self.global_dofs),
            "transformation_global_to_local": (
                self.transformation_global_to_local.tolist()
            ),
            "internal_load_global": self.internal_load_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "element_response": self.response.to_dict(),
        }


@dataclass(frozen=True)
class StatefulFiberFrame2DAssembly:
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    member_assemblies: tuple[StatefulFiberFrame2DMemberAssembly, ...]
    trial_element_states: tuple[StatefulFiberBeam2DState, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_formula": RESIDUAL_FORMULA,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "target_load_factor": self.target_load_factor,
            "free_global_dofs": list(self.free_global_dofs),
            "generalized_coordinates_m": self.generalized_coordinates_m.tolist(),
            "global_displacements": self.global_displacements.tolist(),
            "residual_kn": self.residual_kn.tolist(),
            "jacobian_kn_per_m": self.jacobian_kn_per_m.tolist(),
            "internal_loads_global": self.internal_loads_global.tolist(),
            "external_loads_global": self.external_loads_global.tolist(),
            "reactions_global": self.reactions_global.tolist(),
            "member_assemblies": [row.to_dict() for row in self.member_assemblies],
            "trial_element_state_hashes": [
                state.state_hash for state in self.trial_element_states
            ],
        }


def initial_stateful_fiber_frame2d_checkpoint(
    problem: StatefulFiberFrame2DProblem,
) -> StatefulFiberFrame2DCheckpoint:
    checkpoint = StatefulFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=0,
        step_index=0,
        load_factor=0.0,
        parent_state_hash=None,
        global_displacements=(0.0,) * problem.global_dof_count,
        element_states=tuple(
            member.element.initial_state() for member in problem.members
        ),
    )
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    return checkpoint


def validate_stateful_fiber_frame2d_checkpoint(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> None:
    if type(checkpoint) is not StatefulFiberFrame2DCheckpoint:
        raise ValueError("checkpoint type is invalid")
    if checkpoint.case_id != problem.case_id:
        raise ValueError("checkpoint case_id does not match problem")
    if checkpoint.problem_contract_hash != problem.contract_hash:
        raise ValueError("checkpoint problem_contract_hash does not match problem")
    if checkpoint.compute_state_hash() != checkpoint.state_hash:
        raise ValueError("checkpoint state hash validation failed")
    if len(checkpoint.global_displacements) != problem.global_dof_count:
        raise ValueError("checkpoint global displacement count does not match problem")
    if len(checkpoint.element_states) != len(problem.members):
        raise ValueError("checkpoint element-state count does not match problem")
    global_displacements = np.asarray(
        checkpoint.global_displacements,
        dtype=np.float64,
    )
    if not np.allclose(
        global_displacements[list(problem.fixed_global_dofs)],
        0.0,
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("checkpoint fixed global DOFs must be exactly zero")
    if checkpoint.epoch == 0 and (
        checkpoint.load_factor != 0.0
        or not np.array_equal(
            global_displacements,
            np.zeros(problem.global_dof_count, dtype=np.float64),
        )
    ):
        raise ValueError("epoch-zero checkpoint must be the zero state")
    for member, element_state in zip(
        problem.members,
        checkpoint.element_states,
        strict=True,
    ):
        member.element.validate_state(element_state)
        if element_state.step_index != checkpoint.step_index:
            raise ValueError("checkpoint and element step indices do not match")
        global_dofs = problem.member_global_dofs(member)
        expected_local = (
            problem.member_transformation(member)
            @ global_displacements[list(global_dofs)]
        )
        if not np.allclose(
            expected_local,
            element_state.local_displacements,
            rtol=0.0,
            atol=1.0e-13,
        ):
            raise ValueError(
                "element local displacement does not match checkpoint global state"
            )


def assemble_stateful_fiber_frame2d(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> StatefulFiberFrame2DAssembly:
    """Assemble one trial from the exact immutable committed checkpoint."""

    validate_stateful_fiber_frame2d_checkpoint(problem, accepted_checkpoint)
    load_factor = _finite(target_load_factor, name="target_load_factor")
    free_dofs = problem.free_global_dofs
    try:
        free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("trial_free_coordinates_m has invalid values") from exc
    if free.shape != (len(free_dofs),) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")
    scale = problem.physical_coordinate_scale
    generalized = np.zeros(problem.global_dof_count, dtype=np.float64)
    generalized[list(free_dofs)] = free
    global_displacements = scale * generalized
    internal = np.zeros(problem.global_dof_count, dtype=np.float64)
    tangent = np.zeros(
        (problem.global_dof_count, problem.global_dof_count),
        dtype=np.float64,
    )
    member_rows: list[StatefulFiberFrame2DMemberAssembly] = []
    trial_states: list[StatefulFiberBeam2DState] = []

    for member, parent in zip(
        problem.members,
        accepted_checkpoint.element_states,
        strict=True,
    ):
        global_dofs = problem.member_global_dofs(member)
        transformation = problem.member_transformation(member)
        member_global_displacements = global_displacements[list(global_dofs)]
        local_displacements = transformation @ member_global_displacements
        response = member.element.integrate(local_displacements, parent)
        if response.parent_state_hash != parent.state_hash:
            raise ValueError(
                "element response parent_state_hash does not match checkpoint parent"
            )
        internal_global = transformation.T @ response.internal_force_local
        tangent_global = (
            transformation.T @ response.consistent_tangent_local @ transformation
        )
        internal[list(global_dofs)] += internal_global
        tangent[np.ix_(global_dofs, global_dofs)] += tangent_global
        member_rows.append(
            StatefulFiberFrame2DMemberAssembly(
                member_id=member.member_id,
                global_dofs=global_dofs,
                transformation_global_to_local=_readonly(transformation),
                internal_load_global=_readonly(internal_global),
                consistent_tangent_global=_readonly(tangent_global),
                response=response,
            )
        )
        trial_states.append(response.state)

    external = load_factor * problem.reference_external_load_vector()
    physical_residual = internal - external
    free_scale = scale[list(free_dofs)]
    residual = free_scale * physical_residual[list(free_dofs)]
    jacobian = (
        free_scale[:, None]
        * tangent[np.ix_(free_dofs, free_dofs)]
        * free_scale[None, :]
    )
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    return StatefulFiberFrame2DAssembly(
        parent_checkpoint_hash=accepted_checkpoint.state_hash,
        target_load_factor=load_factor,
        free_global_dofs=free_dofs,
        generalized_coordinates_m=_readonly(generalized),
        global_displacements=_readonly(global_displacements),
        residual_kn=_readonly(residual),
        jacobian_kn_per_m=_readonly(jacobian),
        internal_loads_global=_readonly(internal),
        external_loads_global=_readonly(external),
        reactions_global=_readonly(reactions),
        member_assemblies=tuple(member_rows),
        trial_element_states=tuple(trial_states),
    )


__all__ = [
    "STATEFUL_FIBER_FRAME2D_SCHEMA_VERSION",
    "STATEFUL_FIBER_FRAME2D_TRANSFORMATION",
    "StatefulFiberFrame2DAssembly",
    "StatefulFiberFrame2DMember",
    "StatefulFiberFrame2DMemberAssembly",
    "StatefulFiberFrame2DProblem",
    "assemble_stateful_fiber_frame2d",
    "initial_stateful_fiber_frame2d_checkpoint",
    "small_displacement_frame2d_transformation",
    "validate_stateful_fiber_frame2d_checkpoint",
]
