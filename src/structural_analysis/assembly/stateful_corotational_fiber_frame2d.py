"""Bounded global assembly for stateful corotational 2D fiber beams.

This module scatters exact member-global forces and material/geometric
tangents into one dense planar frame system.  It owns neither nonlinear
solution control nor acceptance of trial checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
    StatefulCorotationalFiberBeam2DResponse,
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA


STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-assembly.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY = (
    "f_global=sum(scatter_e(f_e));"
    "K_material=sum(scatter_e(K_material_e));"
    "K_geometric=sum(scatter_e(K_geometric_e));"
    "K_consistent=K_material+K_geometric"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING = (
    "u_physical=S*q_generalized;"
    "r_generalized=S_transpose*r_physical;"
    "K_generalized=S_transpose*K_physical*S"
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


def _sha256_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _readonly(
    values: Any,
    *,
    shape: tuple[int, ...],
    name: str,
) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite array with shape {shape}") from exc
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite array with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True, order="C")
    result.setflags(write=False)
    return result


def _exact_float64_equal(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left, dtype="<f8")
    right_array = np.ascontiguousarray(right, dtype="<f8")
    return left_array.shape == right_array.shape and (
        left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DMember:
    member_id: str
    node_i: int
    node_j: int
    element: StatefulCorotationalFiberBeam2D

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
        if type(self.element) is not StatefulCorotationalFiberBeam2D:
            raise ValueError("member element must be a StatefulCorotationalFiberBeam2D")
        if self.element.element_id != normalized_id:
            raise ValueError("member_id must match element.element_id")


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DProblem:
    case_id: str
    node_coordinates_m: tuple[tuple[float, float], ...]
    members: tuple[StatefulCorotationalFiberFrame2DMember, ...]
    fixed_global_dofs: tuple[int, ...]
    reference_external_loads: tuple[tuple[int, float], ...]
    rotation_coordinate_scale_m: float
    prescribed_displacements: tuple[tuple[int, float], ...] = ()

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
        normalized_coordinates = tuple(coordinates)
        object.__setattr__(self, "node_coordinates_m", normalized_coordinates)
        if not isinstance(self.members, tuple) or not self.members:
            raise ValueError("members must be a non-empty tuple")
        if not all(
            type(member) is StatefulCorotationalFiberFrame2DMember
            for member in self.members
        ):
            raise ValueError("members contains an invalid member")
        member_ids: set[str] = set()
        node_count = len(normalized_coordinates)
        for member in self.members:
            if member.member_id in member_ids:
                raise ValueError("member_id values must be unique")
            member_ids.add(member.member_id)
            if member.node_i >= node_count or member.node_j >= node_count:
                raise ValueError("member node index is out of range")
            expected_coordinates = (
                normalized_coordinates[member.node_i],
                normalized_coordinates[member.node_j],
            )
            if member.element.node_coordinates_m != expected_coordinates:
                raise ValueError(
                    "member element coordinates do not match problem connectivity"
                )
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
        object.__setattr__(self, "reference_external_loads", tuple(sorted(loads)))
        if not isinstance(self.prescribed_displacements, tuple):
            raise ValueError("prescribed_displacements must be a tuple")
        prescribed: list[tuple[int, float]] = []
        prescribed_dofs: set[int] = set()
        fixed_dofs = set(fixed)
        for row in self.prescribed_displacements:
            if not isinstance(row, tuple) or len(row) != 2 or type(row[0]) is not int:
                raise ValueError("each prescribed displacement must be (dof, value)")
            dof = row[0]
            if dof < 0 or dof >= global_dof_count:
                raise ValueError("prescribed displacement DOF is out of range")
            if dof not in fixed_dofs:
                raise ValueError("prescribed displacement DOF must be constrained")
            if dof in prescribed_dofs:
                raise ValueError("prescribed displacement DOFs must be unique")
            prescribed_dofs.add(dof)
            prescribed.append((dof, _finite(row[1], name="prescribed displacement")))
        normalized_prescribed = tuple(sorted(prescribed))
        object.__setattr__(self, "prescribed_displacements", normalized_prescribed)
        if not any(value != 0.0 for _, value in loads) and not any(
            value != 0.0 for _, value in normalized_prescribed
        ):
            raise ValueError(
                "problem must include a nonzero reference load or prescribed displacement"
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
                "schema_version": (STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION),
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
                "prescribed_displacements": [
                    [dof, value] for dof, value in self.prescribed_displacements
                ],
                "rotation_coordinate_scale_m": self.rotation_coordinate_scale_m,
                "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
                "coordinate_scaling": (
                    STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING
                ),
                "residual_formula": RESIDUAL_FORMULA,
            }
        )

    def member_global_dofs(
        self,
        member: StatefulCorotationalFiberFrame2DMember,
    ) -> tuple[int, ...]:
        return (
            3 * member.node_i,
            3 * member.node_i + 1,
            3 * member.node_i + 2,
            3 * member.node_j,
            3 * member.node_j + 1,
            3 * member.node_j + 2,
        )

    def reference_external_load_vector(self) -> np.ndarray:
        external = np.zeros(self.global_dof_count, dtype=np.float64)
        for dof, value in self.reference_external_loads:
            external[dof] = value
        external.setflags(write=False)
        return external

    def prescribed_displacement_vector(self, load_factor: float) -> np.ndarray:
        factor = _finite(load_factor, name="load_factor")
        prescribed = np.zeros(self.global_dof_count, dtype=np.float64)
        for dof, terminal_value in self.prescribed_displacements:
            prescribed[dof] = (
                0.0
                if factor == 0.0 or terminal_value == 0.0
                else factor * terminal_value
            )
        prescribed.setflags(write=False)
        return prescribed

    def reference_force_scale(self) -> float:
        generalized = (
            self.physical_coordinate_scale * self.reference_external_load_vector()
        )
        return max(float(np.linalg.norm(generalized, ord=np.inf)), 1.0)


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DMemberAssembly:
    member_id: str
    global_dofs: tuple[int, ...]
    internal_load_global: np.ndarray
    material_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray
    response: StatefulCorotationalFiberBeam2DResponse

    def __post_init__(self) -> None:
        normalized_id = str(self.member_id).strip()
        if not normalized_id:
            raise ValueError("member_id must be non-empty")
        object.__setattr__(self, "member_id", normalized_id)
        if (
            not isinstance(self.global_dofs, tuple)
            or len(self.global_dofs) != 6
            or len(set(self.global_dofs)) != 6
            or any(type(dof) is not int or dof < 0 for dof in self.global_dofs)
        ):
            raise ValueError("global_dofs must be six distinct non-negative integers")
        if type(self.response) is not StatefulCorotationalFiberBeam2DResponse:
            raise ValueError("response type is invalid")
        array_fields = (
            ("internal_load_global", (6,)),
            ("material_tangent_global", (6, 6)),
            ("geometric_tangent_global", (6, 6)),
            ("consistent_tangent_global", (6, 6)),
        )
        for name, shape in array_fields:
            object.__setattr__(
                self,
                name,
                _readonly(getattr(self, name), shape=shape, name=name),
            )
        if not _exact_float64_equal(
            self.internal_load_global,
            self.response.internal_force_global,
        ):
            raise ValueError("member internal load does not match element response")
        for name, response_values in (
            ("material_tangent_global", self.response.material_tangent_global),
            ("geometric_tangent_global", self.response.geometric_tangent_global),
            ("consistent_tangent_global", self.response.consistent_tangent_global),
        ):
            if not _exact_float64_equal(getattr(self, name), response_values):
                raise ValueError(f"member {name} does not match element response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "global_dofs": list(self.global_dofs),
            "internal_load_global": self.internal_load_global.tolist(),
            "material_tangent_global": self.material_tangent_global.tolist(),
            "geometric_tangent_global": self.geometric_tangent_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "element_response": self.response.to_dict(),
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DAssembly:
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
    material_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray
    member_assemblies: tuple[StatefulCorotationalFiberFrame2DMemberAssembly, ...]
    trial_element_states: tuple[StatefulCorotationalFiberBeam2DState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_checkpoint_hash",
            _sha256_hash(
                self.parent_checkpoint_hash,
                name="parent_checkpoint_hash",
            ),
        )
        object.__setattr__(
            self,
            "target_load_factor",
            _finite(self.target_load_factor, name="target_load_factor"),
        )
        if (
            not isinstance(self.free_global_dofs, tuple)
            or len(set(self.free_global_dofs)) != len(self.free_global_dofs)
            or any(type(dof) is not int or dof < 0 for dof in self.free_global_dofs)
            or self.free_global_dofs != tuple(sorted(self.free_global_dofs))
        ):
            raise ValueError(
                "free_global_dofs must be sorted distinct non-negative integers"
            )
        try:
            global_count = int(np.asarray(self.global_displacements).shape[0])
        except (IndexError, TypeError) as exc:
            raise ValueError("global_displacements must be a finite vector") from exc
        if global_count == 0 or global_count % 3 != 0:
            raise ValueError("global_displacements must contain complete 3-DOF nodes")
        free_count = len(self.free_global_dofs)
        if self.free_global_dofs and max(self.free_global_dofs) >= global_count:
            raise ValueError("free global DOF is out of range")
        array_fields = (
            ("generalized_coordinates_m", (global_count,)),
            ("global_displacements", (global_count,)),
            ("residual_kn", (free_count,)),
            ("jacobian_kn_per_m", (free_count, free_count)),
            ("internal_loads_global", (global_count,)),
            ("external_loads_global", (global_count,)),
            ("reactions_global", (global_count,)),
            ("material_tangent_global", (global_count, global_count)),
            ("geometric_tangent_global", (global_count, global_count)),
            ("consistent_tangent_global", (global_count, global_count)),
        )
        for name, shape in array_fields:
            object.__setattr__(
                self,
                name,
                _readonly(getattr(self, name), shape=shape, name=name),
            )
        if not np.allclose(
            self.consistent_tangent_global,
            self.material_tangent_global + self.geometric_tangent_global,
            rtol=1.0e-13,
            atol=1.0e-10,
        ):
            raise ValueError("consistent tangent must equal material plus geometric")
        if (
            not isinstance(self.member_assemblies, tuple)
            or not self.member_assemblies
            or not all(
                type(row) is StatefulCorotationalFiberFrame2DMemberAssembly
                for row in self.member_assemblies
            )
        ):
            raise ValueError("member_assemblies contains an invalid row")
        if (
            not isinstance(self.trial_element_states, tuple)
            or len(self.trial_element_states) != len(self.member_assemblies)
            or not all(
                type(state) is StatefulCorotationalFiberBeam2DState
                for state in self.trial_element_states
            )
        ):
            raise ValueError("trial_element_states does not match member assemblies")
        if len({row.member_id for row in self.member_assemblies}) != len(
            self.member_assemblies
        ):
            raise ValueError("member_assemblies must have unique member_id values")
        for row, state in zip(
            self.member_assemblies,
            self.trial_element_states,
            strict=True,
        ):
            if row.response.state.canonical_bytes() != state.canonical_bytes():
                raise ValueError(
                    "trial element state does not match member response state"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION,
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
            "material_tangent_global": self.material_tangent_global.tolist(),
            "geometric_tangent_global": self.geometric_tangent_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "member_assemblies": [row.to_dict() for row in self.member_assemblies],
            "trial_element_state_hashes": [
                state.state_hash for state in self.trial_element_states
            ],
        }


def initial_stateful_corotational_fiber_frame2d_checkpoint(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> StatefulCorotationalFiberFrame2DCheckpoint:
    checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
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
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
    return checkpoint


def validate_stateful_corotational_fiber_frame2d_checkpoint(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> None:
    if type(checkpoint) is not StatefulCorotationalFiberFrame2DCheckpoint:
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
    expected_prescribed = problem.prescribed_displacement_vector(checkpoint.load_factor)
    if not _exact_float64_equal(
        global_displacements[list(problem.fixed_global_dofs)],
        expected_prescribed[list(problem.fixed_global_dofs)],
    ):
        raise ValueError(
            "checkpoint constrained global DOFs do not match prescribed values"
        )
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
        expected_element_displacements = global_displacements[list(global_dofs)]
        if not _exact_float64_equal(
            expected_element_displacements,
            element_state.element_displacements,
        ):
            raise ValueError(
                "element displacement does not match checkpoint global state"
            )


def assemble_stateful_corotational_fiber_frame2d(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> StatefulCorotationalFiberFrame2DAssembly:
    """Assemble one trial from the exact immutable accepted checkpoint."""

    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        accepted_checkpoint,
    )
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
    prescribed = problem.prescribed_displacement_vector(load_factor)
    generalized[list(problem.fixed_global_dofs)] = (
        prescribed[list(problem.fixed_global_dofs)]
        / scale[list(problem.fixed_global_dofs)]
    )
    generalized[list(free_dofs)] = free
    global_displacements = scale * generalized
    global_displacements[list(problem.fixed_global_dofs)] = prescribed[
        list(problem.fixed_global_dofs)
    ]
    internal = np.zeros(problem.global_dof_count, dtype=np.float64)
    material_tangent = np.zeros(
        (problem.global_dof_count, problem.global_dof_count),
        dtype=np.float64,
    )
    geometric_tangent = np.zeros_like(material_tangent)
    member_rows: list[StatefulCorotationalFiberFrame2DMemberAssembly] = []
    trial_states: list[StatefulCorotationalFiberBeam2DState] = []

    for member, parent in zip(
        problem.members,
        accepted_checkpoint.element_states,
        strict=True,
    ):
        global_dofs = problem.member_global_dofs(member)
        member_displacements = global_displacements[list(global_dofs)]
        response = member.element.integrate(member_displacements, parent)
        if response.parent_state_hash != parent.state_hash:
            raise ValueError(
                "element response parent_state_hash does not match checkpoint parent"
            )
        internal[list(global_dofs)] += response.internal_force_global
        material_tangent[np.ix_(global_dofs, global_dofs)] += (
            response.material_tangent_global
        )
        geometric_tangent[np.ix_(global_dofs, global_dofs)] += (
            response.geometric_tangent_global
        )
        member_rows.append(
            StatefulCorotationalFiberFrame2DMemberAssembly(
                member_id=member.member_id,
                global_dofs=global_dofs,
                internal_load_global=response.internal_force_global,
                material_tangent_global=response.material_tangent_global,
                geometric_tangent_global=response.geometric_tangent_global,
                consistent_tangent_global=response.consistent_tangent_global,
                response=response,
            )
        )
        trial_states.append(response.state)

    consistent_tangent = material_tangent + geometric_tangent
    external = load_factor * problem.reference_external_load_vector()
    physical_residual = internal - external
    free_scale = scale[list(free_dofs)]
    residual = free_scale * physical_residual[list(free_dofs)]
    jacobian = (
        free_scale[:, None]
        * consistent_tangent[np.ix_(free_dofs, free_dofs)]
        * free_scale[None, :]
    )
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    return StatefulCorotationalFiberFrame2DAssembly(
        parent_checkpoint_hash=accepted_checkpoint.state_hash,
        target_load_factor=load_factor,
        free_global_dofs=free_dofs,
        generalized_coordinates_m=generalized,
        global_displacements=global_displacements,
        residual_kn=residual,
        jacobian_kn_per_m=jacobian,
        internal_loads_global=internal,
        external_loads_global=external,
        reactions_global=reactions,
        material_tangent_global=material_tangent,
        geometric_tangent_global=geometric_tangent,
        consistent_tangent_global=consistent_tangent,
        member_assemblies=tuple(member_rows),
        trial_element_states=tuple(trial_states),
    )


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DAssembly",
    "StatefulCorotationalFiberFrame2DMember",
    "StatefulCorotationalFiberFrame2DMemberAssembly",
    "StatefulCorotationalFiberFrame2DProblem",
    "assemble_stateful_corotational_fiber_frame2d",
    "initial_stateful_corotational_fiber_frame2d_checkpoint",
    "validate_stateful_corotational_fiber_frame2d_checkpoint",
]
