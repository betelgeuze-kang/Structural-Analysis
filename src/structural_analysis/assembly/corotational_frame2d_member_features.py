"""Exact bounded member-feature operators for the corotational frame path.

The operator keeps analysis-node degrees of freedom separate from physical
element-end degrees of freedom.  Rigid offsets use the finite-rotation rigid
arm map, released end rotations are solved as internal coordinates, and a
uniform dead load is represented by its consistent element-end load vector in
the initial member axes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

import numpy as np

from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
    StatefulCorotationalFiberBeam2DResponse,
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


COROTATIONAL_FRAME2D_MEMBER_FEATURE_SCHEMA_VERSION = (
    "corotational-frame2d-member-features.v1"
)
COROTATIONAL_FRAME2D_RIGID_OFFSET_OPERATOR = (
    "x_end=x_node+u_node+(R(theta_node)-I)*offset_global;"
    "f_node=B_transpose*f_end;"
    "K_node=B_transpose*K_end*B+sum(f_end_i*H_i)"
)
COROTATIONAL_FRAME2D_RELEASE_OPERATOR = (
    "released_end_rotation_is_internal_coordinate;"
    "C_transpose*(f_internal-lambda*p_dead)=0;"
    "K_condensed=K_qq-K_qr*inverse(K_rr)*K_rq"
)
COROTATIONAL_FRAME2D_DISTRIBUTED_LOAD_OPERATOR = (
    "uniform_qx_qy_dead_in_initial_element_local_axes;"
    "p_local=[qxL/2,qyL/2,qyL2/12,qxL/2,qyL/2,-qyL2/12];"
    "residual=f_internal-lambda*p_dead"
)

_HASH_ZERO = "sha256:" + "0" * 64
_RELEASE_MAXIMUM_ITERATIONS = 40
_RELEASE_MAXIMUM_LINE_SEARCHES = 16
_RELEASE_RELATIVE_TOLERANCE = 1.0e-12


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


def _pair(values: Any, *, name: str) -> tuple[float, float]:
    if not isinstance(values, tuple) or len(values) != 2:
        raise ValueError(f"{name} must be a two-value tuple")
    return (
        _finite(values[0], name=f"{name}[0]"),
        _finite(values[1], name=f"{name}[1]"),
    )


def _vector6(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite six-vector")
    return np.array(vector, dtype=np.float64, copy=True, order="C")


def _readonly(values: Any, *, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite array with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True, order="C")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class CorotationalFrame2DMemberFeatures:
    """Immutable v1 feature contract for one analysis member."""

    offset_i_global_m: tuple[float, float] = (0.0, 0.0)
    offset_j_global_m: tuple[float, float] = (0.0, 0.0)
    release_i_rz: bool = False
    release_j_rz: bool = False
    uniform_load_local_kn_per_m: tuple[float, float] = (0.0, 0.0)
    local_x_axis_global: tuple[float, float] | None = None
    local_y_axis_global: tuple[float, float] | None = None
    local_axis_explicit: bool = False
    self_weight_local_kn_per_m: tuple[float, float] = (0.0, 0.0)
    self_weight_mass_per_length_kg_per_m: float | None = None
    self_weight_gravity_global_m_per_s2: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "offset_i_global_m",
            _pair(self.offset_i_global_m, name="offset_i_global_m"),
        )
        object.__setattr__(
            self,
            "offset_j_global_m",
            _pair(self.offset_j_global_m, name="offset_j_global_m"),
        )
        if type(self.release_i_rz) is not bool or type(self.release_j_rz) is not bool:
            raise ValueError("release_i_rz and release_j_rz must be booleans")
        object.__setattr__(
            self,
            "uniform_load_local_kn_per_m",
            _pair(
                self.uniform_load_local_kn_per_m,
                name="uniform_load_local_kn_per_m",
            ),
        )
        object.__setattr__(
            self,
            "self_weight_local_kn_per_m",
            _pair(
                self.self_weight_local_kn_per_m,
                name="self_weight_local_kn_per_m",
            ),
        )
        if type(self.local_axis_explicit) is not bool:
            raise ValueError("local_axis_explicit must be a boolean")
        if (self.local_x_axis_global is None) != (self.local_y_axis_global is None):
            raise ValueError("local x and y axes must be provided together")
        if self.local_x_axis_global is None:
            if self.local_axis_explicit:
                raise ValueError("explicit local axis requires x and y vectors")
        else:
            x_axis = _pair(self.local_x_axis_global, name="local_x_axis_global")
            y_axis = _pair(self.local_y_axis_global, name="local_y_axis_global")
            x = np.asarray(x_axis, dtype=np.float64)
            y = np.asarray(y_axis, dtype=np.float64)
            if not np.isclose(np.linalg.norm(x), 1.0, rtol=0.0, atol=1.0e-12):
                raise ValueError("local_x_axis_global must be a unit vector")
            if not np.isclose(np.linalg.norm(y), 1.0, rtol=0.0, atol=1.0e-12):
                raise ValueError("local_y_axis_global must be a unit vector")
            if not np.isclose(float(x @ y), 0.0, rtol=0.0, atol=1.0e-12):
                raise ValueError("local axes must be orthogonal")
            determinant = float(x[0] * y[1] - x[1] * y[0])
            if not np.isclose(determinant, 1.0, rtol=0.0, atol=1.0e-12):
                raise ValueError("local axes must form a right-handed basis")
            object.__setattr__(self, "local_x_axis_global", x_axis)
            object.__setattr__(self, "local_y_axis_global", y_axis)
        mass = self.self_weight_mass_per_length_kg_per_m
        gravity = self.self_weight_gravity_global_m_per_s2
        if mass is None:
            if gravity is not None or self.self_weight_local_kn_per_m != (0.0, 0.0):
                raise ValueError(
                    "self-weight provenance and local load must be provided together"
                )
        else:
            normalized_mass = _finite(mass, name="self_weight_mass_per_length_kg_per_m")
            if normalized_mass <= 0.0 or gravity is None:
                raise ValueError(
                    "self-weight mass must be positive and include gravity"
                )
            normalized_gravity = _pair(
                gravity,
                name="self_weight_gravity_global_m_per_s2",
            )
            if normalized_gravity == (0.0, 0.0):
                raise ValueError("self-weight gravity vector must be nonzero")
            object.__setattr__(
                self,
                "self_weight_mass_per_length_kg_per_m",
                normalized_mass,
            )
            object.__setattr__(
                self,
                "self_weight_gravity_global_m_per_s2",
                normalized_gravity,
            )

    @property
    def released_element_dofs(self) -> tuple[int, ...]:
        return tuple(
            dof
            for dof, released in ((2, self.release_i_rz), (5, self.release_j_rz))
            if released
        )

    @property
    def has_rigid_offset(self) -> bool:
        return any(
            value != 0.0 for value in self.offset_i_global_m + self.offset_j_global_m
        )

    @property
    def has_distributed_load(self) -> bool:
        return any(value != 0.0 for value in self.combined_uniform_load_local_kn_per_m)

    @property
    def has_self_weight(self) -> bool:
        return self.self_weight_mass_per_length_kg_per_m is not None

    @property
    def combined_uniform_load_local_kn_per_m(self) -> tuple[float, float]:
        return tuple(
            explicit + self_weight
            for explicit, self_weight in zip(
                self.uniform_load_local_kn_per_m,
                self.self_weight_local_kn_per_m,
                strict=True,
            )
        )

    @property
    def has_release(self) -> bool:
        return self.release_i_rz or self.release_j_rz

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COROTATIONAL_FRAME2D_MEMBER_FEATURE_SCHEMA_VERSION,
            "offset_i_global_m": list(self.offset_i_global_m),
            "offset_j_global_m": list(self.offset_j_global_m),
            "release_i_rz": self.release_i_rz,
            "release_j_rz": self.release_j_rz,
            "uniform_load_local_kn_per_m": list(self.uniform_load_local_kn_per_m),
            "self_weight_local_kn_per_m": list(self.self_weight_local_kn_per_m),
            "combined_uniform_load_local_kn_per_m": list(
                self.combined_uniform_load_local_kn_per_m
            ),
            "self_weight_mass_per_length_kg_per_m": (
                self.self_weight_mass_per_length_kg_per_m
            ),
            "self_weight_gravity_global_m_per_s2": (
                None
                if self.self_weight_gravity_global_m_per_s2 is None
                else list(self.self_weight_gravity_global_m_per_s2)
            ),
            "local_axis_explicit": self.local_axis_explicit,
            "local_x_axis_global": (
                None
                if self.local_x_axis_global is None
                else list(self.local_x_axis_global)
            ),
            "local_y_axis_global": (
                None
                if self.local_y_axis_global is None
                else list(self.local_y_axis_global)
            ),
            "rigid_offset_operator": COROTATIONAL_FRAME2D_RIGID_OFFSET_OPERATOR,
            "release_operator": COROTATIONAL_FRAME2D_RELEASE_OPERATOR,
            "distributed_load_operator": (
                COROTATIONAL_FRAME2D_DISTRIBUTED_LOAD_OPERATOR
            ),
        }


@dataclass(frozen=True)
class CorotationalFrame2DMemberFeatureResponse:
    """One feature-resolved trial response in analysis-node coordinates."""

    response_hash: str
    feature_contract_hash: str
    target_load_factor: float
    element_displacements: np.ndarray
    node_to_element_jacobian: np.ndarray
    element_internal_load_global: np.ndarray
    element_equivalent_external_load_global: np.ndarray
    element_net_end_force_global: np.ndarray
    nodal_internal_load_global: np.ndarray
    nodal_equivalent_external_load_global: np.ndarray
    load_factor_residual_derivative_global: np.ndarray
    material_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray
    release_residual_kn_m: np.ndarray
    release_iterations: int
    element_response: StatefulCorotationalFiberBeam2DResponse

    def __post_init__(self) -> None:
        for name in ("response_hash", "feature_contract_hash"):
            value = str(getattr(self, name)).strip()
            digest = value.removeprefix("sha256:")
            if (
                not value.startswith("sha256:")
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError(f"{name} must be a lowercase sha256 digest")
        object.__setattr__(
            self,
            "target_load_factor",
            _finite(self.target_load_factor, name="target_load_factor"),
        )
        if type(self.release_iterations) is not int or self.release_iterations < 0:
            raise ValueError("release_iterations must be a non-negative integer")
        for name, shape in (
            ("element_displacements", (6,)),
            ("node_to_element_jacobian", (6, 6)),
            ("element_internal_load_global", (6,)),
            ("element_equivalent_external_load_global", (6,)),
            ("element_net_end_force_global", (6,)),
            ("nodal_internal_load_global", (6,)),
            ("nodal_equivalent_external_load_global", (6,)),
            ("load_factor_residual_derivative_global", (6,)),
            ("material_tangent_global", (6, 6)),
            ("geometric_tangent_global", (6, 6)),
            ("consistent_tangent_global", (6, 6)),
        ):
            object.__setattr__(
                self,
                name,
                _readonly(getattr(self, name), shape=shape, name=name),
            )
        residual = np.asarray(self.release_residual_kn_m, dtype=np.float64)
        if residual.ndim != 1 or residual.size > 2 or not np.all(np.isfinite(residual)):
            raise ValueError("release_residual_kn_m must contain zero to two values")
        frozen_residual = np.array(residual, dtype=np.float64, copy=True, order="C")
        frozen_residual.setflags(write=False)
        object.__setattr__(self, "release_residual_kn_m", frozen_residual)
        if type(self.element_response) is not StatefulCorotationalFiberBeam2DResponse:
            raise ValueError("element_response type is invalid")
        if not np.array_equal(
            self.element_displacements,
            np.asarray(self.element_response.state.element_displacements),
        ):
            raise ValueError("element displacement does not match element trial state")
        if not np.array_equal(
            self.consistent_tangent_global,
            self.material_tangent_global + self.geometric_tangent_global,
        ):
            raise ValueError("consistent tangent split is not exact")
        expected_hash = canonical_hash(_response_payload(self, include_hash=False))
        if self.response_hash not in {_HASH_ZERO, expected_hash}:
            raise ValueError("member feature response hash is stale")

    def to_dict(self) -> dict[str, Any]:
        return _response_payload(self, include_hash=True)


def element_end_coordinates_m(
    node_i_coordinates_m: tuple[float, float],
    node_j_coordinates_m: tuple[float, float],
    features: CorotationalFrame2DMemberFeatures,
) -> tuple[tuple[float, float], tuple[float, float]]:
    if type(features) is not CorotationalFrame2DMemberFeatures:
        raise ValueError("features type is invalid")
    node_i = _pair(node_i_coordinates_m, name="node_i_coordinates_m")
    node_j = _pair(node_j_coordinates_m, name="node_j_coordinates_m")
    return (
        (
            node_i[0] + features.offset_i_global_m[0],
            node_i[1] + features.offset_i_global_m[1],
        ),
        (
            node_j[0] + features.offset_j_global_m[0],
            node_j[1] + features.offset_j_global_m[1],
        ),
    )


def consistent_uniform_load_element_global(
    element: StatefulCorotationalFiberBeam2D,
    features: CorotationalFrame2DMemberFeatures,
) -> np.ndarray:
    """Return the full-load dead-load vector in element global coordinates."""

    if type(element) is not StatefulCorotationalFiberBeam2D:
        raise ValueError("element type is invalid")
    if type(features) is not CorotationalFrame2DMemberFeatures:
        raise ValueError("features type is invalid")
    qx, qy = features.combined_uniform_load_local_kn_per_m
    length = element.initial_length_m
    local = np.asarray(
        [
            qx * length / 2.0,
            qy * length / 2.0,
            qy * length * length / 12.0,
            qx * length / 2.0,
            qy * length / 2.0,
            -qy * length * length / 12.0,
        ],
        dtype=np.float64,
    )
    coordinates = np.asarray(element.node_coordinates_m, dtype=np.float64)
    delta = coordinates[1] - coordinates[0]
    cosine = float(delta[0] / length)
    sine = float(delta[1] / length)
    if features.local_x_axis_global is None:
        x_axis = (cosine, sine)
        y_axis = (-sine, cosine)
    else:
        x_axis = features.local_x_axis_global
        y_axis = features.local_y_axis_global
        assert y_axis is not None
        if not np.allclose(
            x_axis, (cosine, sine), rtol=0.0, atol=1.0e-12
        ) or not np.allclose(
            y_axis,
            (-sine, cosine),
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError("explicit local axes must match the initial member chord")
    local_from_global = np.asarray(
        [
            [x_axis[0], x_axis[1], 0.0, 0.0, 0.0, 0.0],
            [y_axis[0], y_axis[1], 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, x_axis[0], x_axis[1], 0.0],
            [0.0, 0.0, 0.0, y_axis[0], y_axis[1], 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    result = local_from_global.T @ local
    result.setflags(write=False)
    return result


def expected_element_displacements(
    nodal_displacements: Any,
    features: CorotationalFrame2DMemberFeatures,
    *,
    released_rotations_rad: tuple[float, ...] = (),
) -> np.ndarray:
    """Map analysis-node coordinates to element ends with explicit releases."""

    q = _vector6(nodal_displacements, name="nodal_displacements")
    release_dofs = features.released_element_dofs
    if len(released_rotations_rad) != len(release_dofs):
        raise ValueError("released_rotations_rad does not match released ends")
    alpha = np.asarray(released_rotations_rad, dtype=np.float64)
    if not np.all(np.isfinite(alpha)):
        raise ValueError("released_rotations_rad must be finite")
    element_displacements, _jacobian, _second = _kinematic_map(q, features, alpha)
    element_displacements.setflags(write=False)
    return element_displacements


def integrate_corotational_frame2d_member_features(
    element: StatefulCorotationalFiberBeam2D,
    features: CorotationalFrame2DMemberFeatures,
    nodal_displacements: Any,
    committed_state: StatefulCorotationalFiberBeam2DState,
    *,
    target_load_factor: float,
) -> CorotationalFrame2DMemberFeatureResponse:
    """Resolve releases and return an exact analysis-node residual tangent."""

    if type(element) is not StatefulCorotationalFiberBeam2D:
        raise ValueError("element type is invalid")
    if type(features) is not CorotationalFrame2DMemberFeatures:
        raise ValueError("features type is invalid")
    element.validate_state(committed_state)
    q = _vector6(nodal_displacements, name="nodal_displacements")
    load_factor = _finite(target_load_factor, name="target_load_factor")
    release_dofs = features.released_element_dofs
    selector = np.zeros((6, len(release_dofs)), dtype=np.float64)
    for column, dof in enumerate(release_dofs):
        selector[dof, column] = 1.0
    alpha = np.asarray(
        [committed_state.element_displacements[dof] for dof in release_dofs],
        dtype=np.float64,
    )
    full_dead_load = consistent_uniform_load_element_global(element, features)
    applied_dead_load = load_factor * full_dead_load

    response: StatefulCorotationalFiberBeam2DResponse | None = None
    element_displacements = np.zeros(6, dtype=np.float64)
    jacobian = np.zeros((6, 6), dtype=np.float64)
    second_derivatives = np.zeros((2, 2), dtype=np.float64)
    release_residual = np.zeros(len(release_dofs), dtype=np.float64)
    release_iterations = 0

    for iteration in range(_RELEASE_MAXIMUM_ITERATIONS + 1):
        element_displacements, jacobian, second_derivatives = _kinematic_map(
            q, features, alpha
        )
        response = element.integrate(element_displacements, committed_state)
        net_end_force = response.internal_force_global - applied_dead_load
        release_residual = selector.T @ net_end_force
        scale = max(
            1.0,
            float(np.linalg.norm(response.internal_force_global, ord=np.inf)),
            float(np.linalg.norm(applied_dead_load, ord=np.inf)),
        )
        tolerance = _RELEASE_RELATIVE_TOLERANCE * scale
        if (
            not release_dofs
            or float(np.linalg.norm(release_residual, ord=np.inf)) <= tolerance
        ):
            release_iterations = iteration
            break
        if iteration == _RELEASE_MAXIMUM_ITERATIONS:
            raise ValueError("member end-release local equilibrium did not converge")
        tangent = np.asarray(response.consistent_tangent_global, dtype=np.float64)
        release_tangent = selector.T @ tangent @ selector
        try:
            increment = np.linalg.solve(release_tangent, -release_residual)
        except np.linalg.LinAlgError as exc:
            raise ValueError("member end-release tangent is singular") from exc
        current_norm = float(np.linalg.norm(release_residual, ord=np.inf))
        accepted = False
        step = 1.0
        for _line_search in range(_RELEASE_MAXIMUM_LINE_SEARCHES + 1):
            candidate_alpha = alpha + step * increment
            candidate_u, _candidate_b, _candidate_second = _kinematic_map(
                q, features, candidate_alpha
            )
            candidate_response = element.integrate(candidate_u, committed_state)
            candidate_residual = selector.T @ (
                candidate_response.internal_force_global - applied_dead_load
            )
            candidate_norm = float(np.linalg.norm(candidate_residual, ord=np.inf))
            if candidate_norm <= tolerance or candidate_norm < current_norm:
                alpha = candidate_alpha
                accepted = True
                break
            step *= 0.5
        if not accepted:
            raise ValueError("member end-release line search did not reduce residual")
    assert response is not None

    internal_end = np.asarray(response.internal_force_global, dtype=np.float64)
    net_end = internal_end - applied_dead_load
    nodal_internal = jacobian.T @ internal_end
    nodal_external = jacobian.T @ applied_dead_load
    tangent_end = np.asarray(response.consistent_tangent_global, dtype=np.float64)
    tangent_qq = jacobian.T @ tangent_end @ jacobian
    for end, rotation_dof in enumerate((2, 5)):
        tangent_qq[rotation_dof, rotation_dof] += float(
            net_end[3 * end] * second_derivatives[end, 0]
            + net_end[3 * end + 1] * second_derivatives[end, 1]
        )
    if release_dofs:
        tangent_qr = jacobian.T @ tangent_end @ selector
        tangent_rq = selector.T @ tangent_end @ jacobian
        tangent_rr = selector.T @ tangent_end @ selector
        try:
            consistent = tangent_qq - tangent_qr @ np.linalg.solve(
                tangent_rr, tangent_rq
            )
            release_load_derivative = np.linalg.solve(
                tangent_rr,
                selector.T @ full_dead_load,
            )
        except np.linalg.LinAlgError as exc:
            raise ValueError("member end-release condensation is singular") from exc
        load_factor_derivative = (
            -jacobian.T @ full_dead_load + tangent_qr @ release_load_derivative
        )
    else:
        consistent = tangent_qq
        load_factor_derivative = -jacobian.T @ full_dead_load
    material = (
        jacobian.T
        @ np.asarray(response.material_tangent_global, dtype=np.float64)
        @ jacobian
    )
    geometric = consistent - material

    provisional = CorotationalFrame2DMemberFeatureResponse(
        response_hash=_HASH_ZERO,
        feature_contract_hash=features.contract_hash,
        target_load_factor=load_factor,
        element_displacements=element_displacements,
        node_to_element_jacobian=jacobian,
        element_internal_load_global=internal_end,
        element_equivalent_external_load_global=applied_dead_load,
        element_net_end_force_global=net_end,
        nodal_internal_load_global=nodal_internal,
        nodal_equivalent_external_load_global=nodal_external,
        load_factor_residual_derivative_global=load_factor_derivative,
        material_tangent_global=material,
        geometric_tangent_global=geometric,
        consistent_tangent_global=consistent,
        release_residual_kn_m=release_residual,
        release_iterations=release_iterations,
        element_response=response,
    )
    return replace(
        provisional,
        response_hash=canonical_hash(
            _response_payload(provisional, include_hash=False)
        ),
    )


def _kinematic_map(
    nodal_displacements: np.ndarray,
    features: CorotationalFrame2DMemberFeatures,
    released_rotations_rad: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    element = np.array(nodal_displacements, dtype=np.float64, copy=True, order="C")
    jacobian = np.eye(6, dtype=np.float64)
    second = np.zeros((2, 2), dtype=np.float64)
    alpha_index = 0
    for end, (base, offset, released) in enumerate(
        (
            (0, features.offset_i_global_m, features.release_i_rz),
            (3, features.offset_j_global_m, features.release_j_rz),
        )
    ):
        theta = float(nodal_displacements[base + 2])
        cosine = math.cos(theta)
        sine = math.sin(theta)
        rx, ry = offset
        if rx != 0.0 or ry != 0.0:
            element[base] += (cosine - 1.0) * rx - sine * ry
            element[base + 1] += sine * rx + (cosine - 1.0) * ry
            jacobian[base, base + 2] = -sine * rx - cosine * ry
            jacobian[base + 1, base + 2] = cosine * rx - sine * ry
            second[end, 0] = -cosine * rx + sine * ry
            second[end, 1] = -sine * rx - cosine * ry
        if released:
            element[base + 2] = released_rotations_rad[alpha_index]
            jacobian[base + 2, :] = 0.0
            alpha_index += 1
    return element, jacobian, second


def _response_payload(
    response: CorotationalFrame2DMemberFeatureResponse,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": COROTATIONAL_FRAME2D_MEMBER_FEATURE_SCHEMA_VERSION,
        "feature_contract_hash": response.feature_contract_hash,
        "target_load_factor": response.target_load_factor,
        "element_displacements": response.element_displacements.tolist(),
        "node_to_element_jacobian": response.node_to_element_jacobian.tolist(),
        "element_internal_load_global": response.element_internal_load_global.tolist(),
        "element_equivalent_external_load_global": (
            response.element_equivalent_external_load_global.tolist()
        ),
        "element_net_end_force_global": response.element_net_end_force_global.tolist(),
        "nodal_internal_load_global": response.nodal_internal_load_global.tolist(),
        "nodal_equivalent_external_load_global": (
            response.nodal_equivalent_external_load_global.tolist()
        ),
        "load_factor_residual_derivative_global": (
            response.load_factor_residual_derivative_global.tolist()
        ),
        "material_tangent_global": response.material_tangent_global.tolist(),
        "geometric_tangent_global": response.geometric_tangent_global.tolist(),
        "consistent_tangent_global": response.consistent_tangent_global.tolist(),
        "release_residual_kn_m": response.release_residual_kn_m.tolist(),
        "release_iterations": response.release_iterations,
        "element_response": response.element_response.to_dict(),
    }
    if include_hash:
        payload["response_hash"] = response.response_hash
    return payload


__all__ = [
    "COROTATIONAL_FRAME2D_DISTRIBUTED_LOAD_OPERATOR",
    "COROTATIONAL_FRAME2D_MEMBER_FEATURE_SCHEMA_VERSION",
    "COROTATIONAL_FRAME2D_RELEASE_OPERATOR",
    "COROTATIONAL_FRAME2D_RIGID_OFFSET_OPERATOR",
    "CorotationalFrame2DMemberFeatureResponse",
    "CorotationalFrame2DMemberFeatures",
    "consistent_uniform_load_element_global",
    "element_end_coordinates_m",
    "expected_element_displacements",
    "integrate_corotational_frame2d_member_features",
]
