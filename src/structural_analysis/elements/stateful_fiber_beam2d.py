"""State-updated small-displacement 2D fiber beam element.

The element is a bounded local-coordinate Euler-Bernoulli reference.  It maps
six nodal degrees of freedom to axial strain and curvature at Gauss points,
evaluates one immutable RC fiber-section parent at every point, and integrates
the matching internal force and algorithmic tangent.  It intentionally omits
coordinate transformation, shear deformation, geometric nonlinearity, and a
multi-element assembler.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Iterable

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionResponse,
    StatefulFiberSectionState,
    StatefulRCFiberSection,
)


STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION = "stateful-fiber-beam2d.v1"
STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION = "stateful-fiber-beam2d-state.v1"
STATEFUL_FIBER_BEAM2D_KINEMATICS = (
    "epsilon_0=(-u_i+u_j)/L;kappa_z=d2(Hermite(v_i,theta_i,v_j,theta_j))/dx2"
)
STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE = "f_local=integral(B_transpose*[N_kN,M_z_kN_m]dx)"
STATEFUL_FIBER_BEAM2D_TANGENT = (
    "K_local=integral(B_transpose*K_section_algorithmic*B dx)"
)

_STATE_HASH_DOMAIN = b"structural-analysis/stateful-fiber-beam2d-state/v1\0"


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


def _sha256_contract_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    prefix = "sha256:"
    digest = normalized.removeprefix(prefix)
    if (
        not normalized.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _local_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite six-vector")
    return np.array(vector, dtype=np.float64, copy=True, order="C")


def _gauss_rule(order: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if type(order) is not int or order not in (2, 3):
        raise ValueError("integration_order must be 2 or 3")
    if order == 2:
        abscissa = 0.5773502691896257
        return (-abscissa, abscissa), (1.0, 1.0)
    abscissa = 0.7745966692414834
    return (
        (-abscissa, 0.0, abscissa),
        (0.5555555555555556, 0.8888888888888888, 0.5555555555555556),
    )


@dataclass(frozen=True)
class StatefulFiberBeam2DState:
    element_id: str
    element_contract_hash: str
    step_index: int
    local_displacements: tuple[float, ...]
    integration_point_states: tuple[StatefulFiberSectionState, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        object.__setattr__(
            self,
            "element_contract_hash",
            _sha256_contract_hash(
                self.element_contract_hash,
                name="element_contract_hash",
            ),
        )
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        displacements = _local_vector(
            self.local_displacements,
            name="local_displacements",
        )
        object.__setattr__(
            self,
            "local_displacements",
            tuple(float(value) for value in displacements),
        )
        if (
            not isinstance(self.integration_point_states, tuple)
            or not self.integration_point_states
            or not all(
                type(state) is StatefulFiberSectionState
                for state in self.integration_point_states
            )
        ):
            raise ValueError(
                "integration_point_states must be a non-empty tuple of "
                "StatefulFiberSectionState values"
            )

    def canonical_bytes(self) -> bytes:
        element_id = self.element_id.encode("utf-8")
        contract_hash = self.element_contract_hash.encode("ascii")
        chunks = [
            _STATE_HASH_DOMAIN,
            struct.pack("<Q", len(element_id)),
            element_id,
            struct.pack("<Q", len(contract_hash)),
            contract_hash,
            struct.pack(
                "<Q6dQ",
                self.step_index,
                *self.local_displacements,
                len(self.integration_point_states),
            ),
        ]
        for state in self.integration_point_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
            "element_id": self.element_id,
            "element_contract_hash": self.element_contract_hash,
            "step_index": self.step_index,
            "local_displacements": list(self.local_displacements),
            "integration_point_states": [
                state.to_dict() for state in self.integration_point_states
            ],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulFiberBeam2DResponse:
    parent_state_hash: str
    local_displacements: np.ndarray
    internal_force_local: np.ndarray
    consistent_tangent_local: np.ndarray
    integration_point_xi: np.ndarray
    integration_point_weights: np.ndarray
    generalized_strains: np.ndarray
    section_responses: tuple[StatefulFiberSectionResponse, ...]
    yielded_integration_point_count: int
    damaged_integration_point_count: int
    dissipated_energy_mj: float
    state: StatefulFiberBeam2DState

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "parent_state_hash": self.parent_state_hash,
            "local_displacements": self.local_displacements.tolist(),
            "internal_force_local": self.internal_force_local.tolist(),
            "generalized_strains": self.generalized_strains.tolist(),
            "integration_point_state_hashes": [
                response.state.state_hash for response in self.section_responses
            ],
            "yielded_integration_point_count": (self.yielded_integration_point_count),
            "damaged_integration_point_count": (self.damaged_integration_point_count),
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "trial_state_hash": self.state.state_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_state_hash": self.parent_state_hash,
            "local_displacements": self.local_displacements.tolist(),
            "internal_force_local": self.internal_force_local.tolist(),
            "consistent_tangent_local": self.consistent_tangent_local.tolist(),
            "integration_point_xi": self.integration_point_xi.tolist(),
            "integration_point_weights": self.integration_point_weights.tolist(),
            "generalized_strains": self.generalized_strains.tolist(),
            "section_responses": [
                response.to_dict() for response in self.section_responses
            ],
            "yielded_integration_point_count": (self.yielded_integration_point_count),
            "damaged_integration_point_count": (self.damaged_integration_point_count),
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
            "internal_force_definition": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
            "tangent_definition": STATEFUL_FIBER_BEAM2D_TANGENT,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class StatefulFiberBeam2D:
    section: StatefulRCFiberSection
    length_m: float = 3.0
    integration_order: int = 3
    element_id: str = "stateful_rc_fiber_beam2d"

    def __post_init__(self) -> None:
        if type(self.section) is not StatefulRCFiberSection:
            raise ValueError("section must be a StatefulRCFiberSection")
        object.__setattr__(
            self,
            "length_m",
            _positive(self.length_m, name="length_m"),
        )
        _gauss_rule(self.integration_order)
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)

    @property
    def quadrature(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return _gauss_rule(self.integration_order)

    @property
    def contract_hash(self) -> str:
        points, weights = self.quadrature
        return canonical_hash(
            {
                "schema_version": STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION,
                "element_id": self.element_id,
                "length_m": self.length_m,
                "integration_order": self.integration_order,
                "integration_point_xi": list(points),
                "integration_point_weights": list(weights),
                "section_contract_hash": self.section.contract_hash,
                "kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
                "internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
                "tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
            }
        )

    def strain_displacement_matrix(self, xi: float) -> np.ndarray:
        coordinate = _finite(xi, name="xi")
        if coordinate < -1.0 or coordinate > 1.0:
            raise ValueError("xi must be in [-1, 1]")
        ratio = 0.5 * (coordinate + 1.0)
        length = self.length_m
        matrix = np.asarray(
            [
                [-1.0 / length, 0.0, 0.0, 1.0 / length, 0.0, 0.0],
                [
                    0.0,
                    (-6.0 + 12.0 * ratio) / length**2,
                    (-4.0 + 6.0 * ratio) / length,
                    0.0,
                    (6.0 - 12.0 * ratio) / length**2,
                    (-2.0 + 6.0 * ratio) / length,
                ],
            ],
            dtype=np.float64,
        )
        matrix.setflags(write=False)
        return matrix

    def uniform_generalized_strain_displacements(
        self,
        axial_strain: float,
        curvature_z_per_m: float,
    ) -> np.ndarray:
        axial = _finite(axial_strain, name="axial_strain")
        curvature = _finite(
            curvature_z_per_m,
            name="curvature_z_per_m",
        )
        length = self.length_m
        displacement = np.asarray(
            [
                0.0,
                0.0,
                0.0,
                axial * length,
                0.5 * curvature * length**2,
                curvature * length,
            ],
            dtype=np.float64,
        )
        displacement.setflags(write=False)
        return displacement

    def initial_state(self) -> StatefulFiberBeam2DState:
        return StatefulFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=0,
            local_displacements=(0.0,) * 6,
            integration_point_states=tuple(
                self.section.initial_state() for _ in range(self.integration_order)
            ),
        )

    def validate_state(self, state: StatefulFiberBeam2DState) -> None:
        if type(state) is not StatefulFiberBeam2DState:
            raise ValueError("state type is invalid")
        if state.element_id != self.element_id:
            raise ValueError("state element_id does not match element")
        if state.element_contract_hash != self.contract_hash:
            raise ValueError("state element_contract_hash does not match element")
        if len(state.integration_point_states) != self.integration_order:
            raise ValueError("state integration-point count does not match element")
        local = np.asarray(state.local_displacements, dtype=np.float64)
        for xi, section_state in zip(
            self.quadrature[0],
            state.integration_point_states,
            strict=True,
        ):
            self.section.validate_state(section_state)
            if section_state.step_index != state.step_index:
                raise ValueError("section and element step indices do not match")
            expected = self.strain_displacement_matrix(xi) @ local
            actual = np.asarray(
                [
                    section_state.axial_strain,
                    section_state.curvature_z_per_m,
                ],
                dtype=np.float64,
            )
            if not np.allclose(expected, actual, rtol=0.0, atol=1.0e-14):
                raise ValueError(
                    "section generalized strain does not match element state"
                )

    def dissipated_energy_mj(self, state: StatefulFiberBeam2DState) -> float:
        self.validate_state(state)
        _, weights = self.quadrature
        jacobian = 0.5 * self.length_m
        return math.fsum(
            weight * jacobian * self.section.dissipated_energy_mj_per_m(section_state)
            for weight, section_state in zip(
                weights,
                state.integration_point_states,
                strict=True,
            )
        )

    def integrate(
        self,
        local_displacements: Any,
        committed_state: StatefulFiberBeam2DState,
    ) -> StatefulFiberBeam2DResponse:
        self.validate_state(committed_state)
        local = _local_vector(
            local_displacements,
            name="local_displacements",
        )
        points, weights = self.quadrature
        jacobian = 0.5 * self.length_m
        internal_force = np.zeros(6, dtype=np.float64)
        tangent = np.zeros((6, 6), dtype=np.float64)
        generalized_strains: list[np.ndarray] = []
        section_responses: list[StatefulFiberSectionResponse] = []
        next_states: list[StatefulFiberSectionState] = []

        for xi, weight, parent in zip(
            points,
            weights,
            committed_state.integration_point_states,
            strict=True,
        ):
            strain_displacement = self.strain_displacement_matrix(xi)
            generalized = strain_displacement @ local
            response = self.section.integrate(generalized, parent)
            factor = weight * jacobian
            internal_force += (strain_displacement.T @ response.resultants) * factor
            tangent += (
                strain_displacement.T
                @ response.consistent_tangent
                @ strain_displacement
            ) * factor
            generalized_strains.append(generalized)
            section_responses.append(response)
            next_states.append(response.state)

        next_state = StatefulFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=committed_state.step_index + 1,
            local_displacements=tuple(float(value) for value in local),
            integration_point_states=tuple(next_states),
        )
        generalized_array = np.asarray(
            generalized_strains,
            dtype=np.float64,
        )
        point_array = np.asarray(points, dtype=np.float64)
        weight_array = np.asarray(weights, dtype=np.float64)
        for array in (
            local,
            internal_force,
            tangent,
            generalized_array,
            point_array,
            weight_array,
        ):
            array.setflags(write=False)
        return StatefulFiberBeam2DResponse(
            parent_state_hash=committed_state.state_hash,
            local_displacements=local,
            internal_force_local=internal_force,
            consistent_tangent_local=tangent,
            integration_point_xi=point_array,
            integration_point_weights=weight_array,
            generalized_strains=generalized_array,
            section_responses=tuple(section_responses),
            yielded_integration_point_count=sum(
                int(response.yielded_steel_fiber_count > 0)
                for response in section_responses
            ),
            damaged_integration_point_count=sum(
                int(response.damaged_concrete_fiber_count > 0)
                for response in section_responses
            ),
            dissipated_energy_mj=self.dissipated_energy_mj(next_state),
            state=next_state,
        )


def finite_difference_stateful_fiber_beam2d_tangent_check(
    element: StatefulFiberBeam2D,
    committed_state: StatefulFiberBeam2DState,
    *,
    local_displacements: Any | None = None,
    displacement_epsilon_m: float = 1.0e-8,
    rotation_epsilon_rad: float = 1.0e-8,
    relative_tolerance: float = 3.0e-6,
) -> dict[str, Any]:
    local = _local_vector(
        (
            element.uniform_generalized_strain_displacements(-3.0e-4, 6.0e-3)
            if local_displacements is None
            else local_displacements
        ),
        name="local_displacements",
    )
    displacement_step = _positive(
        displacement_epsilon_m,
        name="displacement_epsilon_m",
    )
    rotation_step = _positive(
        rotation_epsilon_rad,
        name="rotation_epsilon_rad",
    )
    tolerance = _positive(relative_tolerance, name="relative_tolerance")
    steps = np.asarray(
        [
            displacement_step,
            displacement_step,
            rotation_step,
            displacement_step,
            displacement_step,
            rotation_step,
        ],
        dtype=np.float64,
    )
    parent_bytes = committed_state.canonical_bytes()
    center = element.integrate(local, committed_state)
    difference = np.empty((6, 6), dtype=np.float64)
    parent_hashes = [center.parent_state_hash]
    for column, step in enumerate(steps):
        direction = np.zeros(6, dtype=np.float64)
        direction[column] = step
        forward = element.integrate(local + direction, committed_state)
        backward = element.integrate(local - direction, committed_state)
        difference[:, column] = (
            forward.internal_force_local - backward.internal_force_local
        ) / (2.0 * step)
        parent_hashes.extend((forward.parent_state_hash, backward.parent_state_hash))
    error = difference - center.consistent_tangent_local
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(
        float(np.linalg.norm(difference, ord=np.inf)),
        float(np.linalg.norm(center.consistent_tangent_local, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error / scale
    symmetry_error = float(
        np.linalg.norm(
            center.consistent_tangent_local - center.consistent_tangent_local.T,
            ord=np.inf,
        )
    )
    same_parent = bool(
        all(value == committed_state.state_hash for value in parent_hashes)
        and committed_state.canonical_bytes() == parent_bytes
    )
    return {
        "local_displacements": local.tolist(),
        "analytic_consistent_tangent": (center.consistent_tangent_local.tolist()),
        "finite_difference_tangent": difference.tolist(),
        "absolute_inf_error": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "tangent_symmetry_error": symmetry_error,
        "same_committed_parent_state": same_parent,
        "pass": bool(
            relative_error <= tolerance and symmetry_error <= 1.0e-10 and same_parent
        ),
    }


def integrate_stateful_fiber_beam2d_history(
    element: StatefulFiberBeam2D,
    local_displacement_path: Iterable[Any],
    *,
    initial_state: StatefulFiberBeam2DState | None = None,
) -> dict[str, Any]:
    path = tuple(
        _local_vector(row, name="local_displacement_path row")
        for row in local_displacement_path
    )
    if not path:
        raise ValueError("local_displacement_path must be non-empty")
    state = initial_state or element.initial_state()
    element.validate_state(state)
    previous_curvature = float(
        np.mean(
            [
                section_state.curvature_z_per_m
                for section_state in state.integration_point_states
            ]
        )
    )
    previous_sign = 0
    reversal_count = 0
    rows: list[dict[str, Any]] = []
    energy_values = [element.dissipated_energy_mj(state)]
    for step_index, local in enumerate(path, start=1):
        parent = state
        response = element.integrate(local, parent)
        curvature = float(np.mean(response.generalized_strains[:, 1]))
        increment = curvature - previous_curvature
        sign = 1 if increment > 0.0 else -1 if increment < 0.0 else 0
        if sign != 0 and previous_sign != 0 and sign != previous_sign:
            reversal_count += 1
        if sign != 0:
            previous_sign = sign
        state = response.state
        energy_values.append(response.dissipated_energy_mj)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "accepted_state_hash": state.state_hash,
                "mean_curvature_z_per_m": curvature,
                "curvature_increment_sign": sign,
                **response.to_summary_dict(),
            }
        )
        previous_curvature = curvature
    energy_monotonic = all(
        following + 1.0e-15 >= current
        for current, following in zip(energy_values, energy_values[1:])
    )
    return {
        "element_contract_hash": element.contract_hash,
        "step_count": len(rows),
        "curvature_reversal_count": reversal_count,
        "yielded_step_count": sum(
            int(row["yielded_integration_point_count"] > 0) for row in rows
        ),
        "concrete_damage_step_count": sum(
            int(row["damaged_integration_point_count"] > 0) for row in rows
        ),
        "dissipated_energy_nonnegative_monotonic": energy_monotonic,
        "final_dissipated_energy_mj": energy_values[-1],
        "final_state": state.to_dict(),
        "history": rows,
    }


__all__ = [
    "STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE",
    "STATEFUL_FIBER_BEAM2D_KINEMATICS",
    "STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_TANGENT",
    "StatefulFiberBeam2D",
    "StatefulFiberBeam2DResponse",
    "StatefulFiberBeam2DState",
    "finite_difference_stateful_fiber_beam2d_tangent_check",
    "integrate_stateful_fiber_beam2d_history",
]
