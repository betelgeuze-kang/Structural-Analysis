"""Distributed two-layer fiber frame with condensed bond-slip field.

The two axial-biaxial fiber sections share the objective corotational frame
kinematics.  A linear two-node interface-slip field adds compatible axial
strain increments to the two layers and is statically condensed from the five
selected frame basic modes.  Connector and fiber trials are always evaluated
from one immutable accepted parent.

This is a bounded verification kernel.  It does not claim a general shear-lag,
uplift, contact, headed-stud, slab-width, or design-code formulation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any

import numpy as np

from structural_analysis.elements.corotational_frame3d import (
    CorotationalFrame3DResponse,
    corotational_frame3d_basic_kinematics,
    corotational_frame3d_response,
)
from structural_analysis.elements.timoshenko_frame3d import TimoshenkoFrame3DSection
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.materials.bond_slip import (
    BondSlipMaterial,
    BondSlipResponse,
    BondSlipState,
    integrate_bond_slip,
)
from structural_analysis.materials.stateful_biaxial_fiber_section import (
    StatefulBiaxialFiberSection,
    StatefulBiaxialFiberSectionResponse,
    StatefulBiaxialFiberSectionState,
)


STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_PROFILE = (
    "corotational_timoshenko_distributed_two_layer_fiber_bond_slip_condensed.v1"
)
STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_STATE_SCHEMA_VERSION = (
    "stateful-corotational-partial-composite-frame3d-state.v1"
)
STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_CLAIM_BOUNDARY = (
    "Bounded 2/3-point two-layer axial-biaxial fiber member with a linear "
    "two-node interface-slip field and cyclic bond-slip points repeated at an "
    "explicit connector spacing. The two internal slip coordinates are solved "
    "from same-parent local equilibrium and statically condensed. It is not a "
    "general shear-lag, uplift/contact, slab-effective-width, connector-group, "
    "local-buckling, published composite-member validation, production-scale, "
    "design-code, or release-authoritative formulation."
)
_STATE_DOMAIN = (
    b"structural-analysis/stateful-corotational-partial-composite-frame3d-state/v1\0"
)
_SELECTED_BASIC_INDICES = (0, 2, 3, 5, 6)
_N_TO_KN = 1.0e-3
_J_TO_MJ = 1000.0


def _coordinates(values: Any) -> tuple[tuple[float, float, float], ...]:
    try:
        coordinates = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("node_coordinates_m must be a finite 2 by 3 array") from exc
    if coordinates.shape != (2, 3) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2 by 3 array")
    return tuple(
        (float(row[0]), float(row[1]), float(row[2])) for row in coordinates
    )


def _displacement(values: Any) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("element_displacements must be a finite 12-vector") from exc
    if vector.shape != (12,) or not np.all(np.isfinite(vector)):
        raise ValueError("element_displacements must be a finite 12-vector")
    return np.array(vector, dtype=np.float64, copy=True)


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


def _hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


@dataclass(frozen=True)
class StatefulCorotationalPartialCompositeFrame3DState:
    element_id: str
    element_contract_hash: str
    element_displacements: tuple[float, ...]
    interface_slip_nodes_m: tuple[float, float]
    steel_section_states: tuple[StatefulBiaxialFiberSectionState, ...]
    concrete_section_states: tuple[StatefulBiaxialFiberSectionState, ...]
    connector_states: tuple[BondSlipState, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        object.__setattr__(
            self,
            "element_contract_hash",
            _hash(self.element_contract_hash, name="element_contract_hash"),
        )
        object.__setattr__(
            self,
            "element_displacements",
            tuple(float(value) for value in _displacement(self.element_displacements)),
        )
        if (
            not isinstance(self.interface_slip_nodes_m, tuple)
            or len(self.interface_slip_nodes_m) != 2
        ):
            raise ValueError("interface_slip_nodes_m must contain two values")
        object.__setattr__(
            self,
            "interface_slip_nodes_m",
            tuple(
                _finite(value, name=f"interface_slip_nodes_m[{index}]")
                for index, value in enumerate(self.interface_slip_nodes_m)
            ),
        )
        if not all(
            isinstance(rows, tuple) and bool(rows)
            for rows in (
                self.steel_section_states,
                self.concrete_section_states,
                self.connector_states,
            )
        ):
            raise ValueError("integration-point state tuples must be non-empty")
        if not all(
            type(state) is StatefulBiaxialFiberSectionState
            for state in self.steel_section_states
        ):
            raise ValueError("steel_section_states contains an invalid state")
        if not all(
            type(state) is StatefulBiaxialFiberSectionState
            for state in self.concrete_section_states
        ):
            raise ValueError("concrete_section_states contains an invalid state")
        if not all(type(state) is BondSlipState for state in self.connector_states):
            raise ValueError("connector_states contains an invalid state")
        counts = {
            len(self.steel_section_states),
            len(self.concrete_section_states),
            len(self.connector_states),
        }
        if len(counts) != 1:
            raise ValueError("integration-point state counts must match")

    def canonical_bytes(self) -> bytes:
        element_id = self.element_id.encode("utf-8")
        contract_hash = self.element_contract_hash.encode("ascii")
        chunks = [
            _STATE_DOMAIN,
            struct.pack("<Q", len(element_id)),
            element_id,
            struct.pack("<Q", len(contract_hash)),
            contract_hash,
            struct.pack(
                "<12d2dQ",
                *self.element_displacements,
                *self.interface_slip_nodes_m,
                len(self.connector_states),
            ),
        ]
        for steel, concrete, connector in zip(
            self.steel_section_states,
            self.concrete_section_states,
            self.connector_states,
            strict=True,
        ):
            for state in (steel, concrete, connector):
                encoded = state.canonical_bytes()
                chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_STATE_SCHEMA_VERSION
            ),
            "element_id": self.element_id,
            "element_contract_hash": self.element_contract_hash,
            "element_displacements": list(self.element_displacements),
            "interface_slip_nodes_m": list(self.interface_slip_nodes_m),
            "steel_section_states": [
                state.to_dict() for state in self.steel_section_states
            ],
            "concrete_section_states": [
                state.to_dict() for state in self.concrete_section_states
            ],
            "connector_states": [state.to_dict() for state in self.connector_states],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalPartialCompositeFrame3DResponse:
    parent_state_hash: str
    elastic_reference: CorotationalFrame3DResponse
    selected_basic_deformations: np.ndarray
    partial_composite_basic_forces: np.ndarray
    partial_composite_basic_tangent: np.ndarray
    elastic_reference_basic_tangent: np.ndarray
    correction_basic_forces: np.ndarray
    interface_slip_nodes_m: np.ndarray
    local_equilibrium_residual_kn: np.ndarray
    local_iterations: int
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray
    basic_jacobian: np.ndarray
    steel_section_responses: tuple[StatefulBiaxialFiberSectionResponse, ...]
    concrete_section_responses: tuple[StatefulBiaxialFiberSectionResponse, ...]
    connector_responses: tuple[BondSlipResponse, ...]
    dissipated_energy_mj: float
    state: StatefulCorotationalPartialCompositeFrame3DState
    profile: str = STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_PROFILE
    claim_boundary: str = (
        STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_CLAIM_BOUNDARY
    )

    def __post_init__(self) -> None:
        arrays = (
            ("selected_basic_deformations", (5,)),
            ("partial_composite_basic_forces", (5,)),
            ("partial_composite_basic_tangent", (5, 5)),
            ("elastic_reference_basic_tangent", (5, 5)),
            ("correction_basic_forces", (5,)),
            ("interface_slip_nodes_m", (2,)),
            ("local_equilibrium_residual_kn", (2,)),
            ("internal_force_global", (12,)),
            ("consistent_tangent_global", (12, 12)),
            ("basic_jacobian", (5, 12)),
        )
        for name, shape in arrays:
            values = immutable_array(getattr(self, name), dtype="<f8")
            if values.shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
            object.__setattr__(self, name, values)
        if type(self.local_iterations) is not int or self.local_iterations < 0:
            raise ValueError("local_iterations must be a non-negative integer")
        object.__setattr__(
            self,
            "dissipated_energy_mj",
            _finite(self.dissipated_energy_mj, name="dissipated_energy_mj"),
        )

    @property
    def axial_strain(self) -> float:
        return float(
            self.selected_basic_deformations[0]
            / self.elastic_reference.initial_length_m
        )

    @property
    def axial_force_kn(self) -> float:
        return float(self.partial_composite_basic_forces[0])

    @property
    def axial_tangent_kn_per_m(self) -> float:
        return float(self.partial_composite_basic_tangent[0, 0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "parent_state_hash": self.parent_state_hash,
            "selected_basic_order": [
                "axial_extension_m",
                "bending_y_i_rad",
                "bending_z_i_rad",
                "bending_y_j_rad",
                "bending_z_j_rad",
            ],
            "selected_basic_deformations": self.selected_basic_deformations.tolist(),
            "partial_composite_basic_forces": (
                self.partial_composite_basic_forces.tolist()
            ),
            "partial_composite_basic_tangent": (
                self.partial_composite_basic_tangent.tolist()
            ),
            "elastic_reference_basic_tangent": (
                self.elastic_reference_basic_tangent.tolist()
            ),
            "correction_basic_forces": self.correction_basic_forces.tolist(),
            "interface_slip_nodes_m": self.interface_slip_nodes_m.tolist(),
            "local_equilibrium_residual_kn": (
                self.local_equilibrium_residual_kn.tolist()
            ),
            "local_iterations": self.local_iterations,
            "global_end_forces": self.internal_force_global.tolist(),
            "steel_section_responses": [
                response.to_dict() for response in self.steel_section_responses
            ],
            "concrete_section_responses": [
                response.to_dict() for response in self.concrete_section_responses
            ],
            "connector_responses": [
                response.to_dict() for response in self.connector_responses
            ],
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "trial_state": self.state.to_dict(),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _LocalResponse:
    basic_force: np.ndarray
    condensed_tangent: np.ndarray
    residual: np.ndarray
    local_tangent: np.ndarray
    steel_responses: tuple[StatefulBiaxialFiberSectionResponse, ...]
    concrete_responses: tuple[StatefulBiaxialFiberSectionResponse, ...]
    connector_responses: tuple[BondSlipResponse, ...]


@dataclass(frozen=True)
class StatefulCorotationalPartialCompositeFrame3D:
    node_coordinates_m: tuple[tuple[float, float, float], ...]
    steel_section: StatefulBiaxialFiberSection
    concrete_section: StatefulBiaxialFiberSection
    connector: BondSlipMaterial
    connector_spacing_m: float
    integration_order: int = 3
    local_axis_roll_deg: float = 0.0
    local_equilibrium_absolute_tolerance_kn: float = 1.0e-9
    local_increment_tolerance_m: float = 1.0e-13
    maximum_local_iterations: int = 30
    maximum_local_condition_number: float = 1.0e14
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
    )
    element_id: str = "stateful_corotational_partial_composite_frame3d"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "node_coordinates_m",
            _coordinates(self.node_coordinates_m),
        )
        if type(self.steel_section) is not StatefulBiaxialFiberSection:
            raise ValueError("steel_section must be an exact biaxial fiber section")
        if type(self.concrete_section) is not StatefulBiaxialFiberSection:
            raise ValueError("concrete_section must be an exact biaxial fiber section")
        if self.steel_section.section_id == self.concrete_section.section_id:
            raise ValueError("steel and concrete section_id values must differ")
        if type(self.connector) is not BondSlipMaterial:
            raise ValueError("connector must be an exact BondSlipMaterial")
        object.__setattr__(
            self,
            "connector_spacing_m",
            _positive(self.connector_spacing_m, name="connector_spacing_m"),
        )
        _gauss_rule(self.integration_order)
        object.__setattr__(
            self,
            "local_axis_roll_deg",
            _finite(self.local_axis_roll_deg, name="local_axis_roll_deg"),
        )
        for name in (
            "local_equilibrium_absolute_tolerance_kn",
            "local_increment_tolerance_m",
            "maximum_local_condition_number",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name=name))
        if (
            type(self.maximum_local_iterations) is not int
            or self.maximum_local_iterations < 1
        ):
            raise ValueError("maximum_local_iterations must be a positive integer")
        if not isinstance(self.line_search_alphas, tuple) or not self.line_search_alphas:
            raise ValueError("line_search_alphas must be a non-empty tuple")
        previous = math.inf
        normalized: list[float] = []
        for index, value in enumerate(self.line_search_alphas):
            alpha = _positive(value, name=f"line_search_alphas[{index}]")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized.append(alpha)
            previous = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized))
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        if self.initial_length_m <= 1.0e-12:
            raise ValueError("initial member length must be positive")

    @property
    def initial_length_m(self) -> float:
        coordinates = np.asarray(self.node_coordinates_m, dtype=np.float64)
        return float(np.linalg.norm(coordinates[1] - coordinates[0]))

    @property
    def quadrature(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return _gauss_rule(self.integration_order)

    @property
    def slip_partition(self) -> tuple[float, float]:
        steel = float(self.steel_section.initial_consistent_tangent()[0, 0])
        concrete = float(self.concrete_section.initial_consistent_tangent()[0, 0])
        total = steel + concrete
        if not math.isfinite(total) or steel <= 0.0 or concrete <= 0.0:
            raise ValueError("layer initial axial tangents must be positive")
        return concrete / total, steel / total

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        points, weights = self.quadrature
        steel_partition, concrete_partition = self.slip_partition
        return {
            "profile": STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_PROFILE,
            "element_id": self.element_id,
            "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
            "local_axis_roll_deg": self.local_axis_roll_deg,
            "integration_order": self.integration_order,
            "integration_point_xi": list(points),
            "integration_point_weights": list(weights),
            "steel_section_contract_hash": self.steel_section.contract_hash,
            "concrete_section_contract_hash": self.concrete_section.contract_hash,
            "connector": {
                "material_id": self.connector.material_id,
                "initial_stiffness_n_per_m": (
                    self.connector.initial_stiffness_n_per_m
                ),
                "yield_slip_m": self.connector.yield_slip_m,
                "ultimate_slip_m": self.connector.ultimate_slip_m,
                "residual_strength_ratio": self.connector.residual_strength_ratio,
                "reversal_stiffness_degradation": (
                    self.connector.reversal_stiffness_degradation
                ),
                "reversal_strength_degradation": (
                    self.connector.reversal_strength_degradation
                ),
                "minimum_stiffness_ratio": self.connector.minimum_stiffness_ratio,
                "connector_spacing_m": self.connector_spacing_m,
            },
            "slip_field": {
                "interpolation": "linear_two_node",
                "steel_axial_partition": steel_partition,
                "concrete_axial_partition": concrete_partition,
                "partition_policy": "initial_axial_rigidity_weighted_mean_strain",
                "end_slip_tractions": "zero_natural_boundary",
            },
            "local_solver": {
                "absolute_tolerance_kn": (
                    self.local_equilibrium_absolute_tolerance_kn
                ),
                "increment_tolerance_m": self.local_increment_tolerance_m,
                "maximum_iterations": self.maximum_local_iterations,
                "maximum_condition_number": self.maximum_local_condition_number,
                "line_search_alphas": list(self.line_search_alphas),
                "fallback_allowed": False,
                "regularization_allowed": False,
            },
            "basic_modes": list(_SELECTED_BASIC_INDICES),
            "derivative_profile": (
                "five_point_basic_jacobian_and_symmetric_basic_hessian.v1"
            ),
            "reference_policy": (
                "elastic_timoshenko_plus_condensed_partial_composite_minus_"
                "uncondensed_initial_layers"
            ),
            "claim_boundary": (
                STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_CLAIM_BOUNDARY
            ),
        }

    def initial_state(self) -> StatefulCorotationalPartialCompositeFrame3DState:
        state = StatefulCorotationalPartialCompositeFrame3DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            element_displacements=(0.0,) * 12,
            interface_slip_nodes_m=(0.0, 0.0),
            steel_section_states=tuple(
                self.steel_section.initial_state()
                for _ in range(self.integration_order)
            ),
            concrete_section_states=tuple(
                self.concrete_section.initial_state()
                for _ in range(self.integration_order)
            ),
            connector_states=tuple(
                BondSlipState() for _ in range(self.integration_order)
            ),
        )
        self.validate_state(state)
        return state

    def validate_reference_section(
        self,
        reference: TimoshenkoFrame3DSection,
        *,
        relative_tolerance: float = 1.0e-10,
    ) -> None:
        if type(reference) is not TimoshenkoFrame3DSection:
            raise ValueError("reference must be an exact TimoshenkoFrame3DSection")
        tangent = (
            np.asarray(self.steel_section.initial_consistent_tangent())
            + np.asarray(self.concrete_section.initial_consistent_tangent())
        )
        props = reference.frame
        expected = np.diag(
            (
                props.e_n_per_m2 * props.area_m2,
                props.e_n_per_m2 * props.iy_m4,
                props.e_n_per_m2 * props.iz_m4,
            )
        )
        scale = max(
            float(np.linalg.norm(tangent, ord=np.inf)),
            float(np.linalg.norm(expected, ord=np.inf)),
            1.0,
        )
        if float(np.linalg.norm(tangent - expected, ord=np.inf)) > (
            relative_tolerance * scale
        ):
            raise ValueError(
                "partial-composite layer initial tangent does not match frame reference"
            )

    def validate_state(
        self,
        state: StatefulCorotationalPartialCompositeFrame3DState,
    ) -> None:
        if type(state) is not StatefulCorotationalPartialCompositeFrame3DState:
            raise ValueError("state type is invalid")
        if state.element_id != self.element_id:
            raise ValueError("state element_id does not match element")
        if state.element_contract_hash != self.contract_hash:
            raise ValueError("state element_contract_hash does not match element")
        if len(state.connector_states) != self.integration_order:
            raise ValueError("state integration-point count does not match element")
        selected = self._selected_basic(_displacement(state.element_displacements))
        slip_nodes = np.asarray(state.interface_slip_nodes_m, dtype=np.float64)
        steel_partition, concrete_partition = self.slip_partition
        slip_gradient = self._slip_gradient() @ slip_nodes
        for xi, steel, concrete, connector in zip(
            self.quadrature[0],
            state.steel_section_states,
            state.concrete_section_states,
            state.connector_states,
            strict=True,
        ):
            self.steel_section.validate_state(steel)
            self.concrete_section.validate_state(concrete)
            base = self._strain_matrix(xi) @ selected
            expected_steel = base + np.asarray(
                (steel_partition * slip_gradient, 0.0, 0.0)
            )
            expected_concrete = base - np.asarray(
                (concrete_partition * slip_gradient, 0.0, 0.0)
            )
            actual_steel = np.asarray(
                (steel.axial_strain, steel.curvature_y_per_m, steel.curvature_z_per_m)
            )
            actual_concrete = np.asarray(
                (
                    concrete.axial_strain,
                    concrete.curvature_y_per_m,
                    concrete.curvature_z_per_m,
                )
            )
            slip = float(self._slip_shape(xi) @ slip_nodes)
            if not np.allclose(expected_steel, actual_steel, atol=3.0e-12, rtol=0.0):
                raise ValueError("steel section strain does not match element state")
            if not np.allclose(
                expected_concrete,
                actual_concrete,
                atol=3.0e-12,
                rtol=0.0,
            ):
                raise ValueError("concrete section strain does not match element state")
            if not math.isclose(
                connector.previous_slip_m,
                slip,
                rel_tol=0.0,
                abs_tol=3.0e-12,
            ):
                raise ValueError("connector slip does not match element state")

    def dissipated_energy_mj(
        self,
        state: StatefulCorotationalPartialCompositeFrame3DState,
    ) -> float:
        self.validate_state(state)
        _, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
        return math.fsum(
            weight
            * jacobian
            * (
                self.steel_section.dissipated_energy_mj_per_m(steel)
                + self.concrete_section.dissipated_energy_mj_per_m(concrete)
                + connector.dissipated_energy_j
                * _J_TO_MJ
                / self.connector_spacing_m
            )
            for weight, steel, concrete, connector in zip(
                weights,
                state.steel_section_states,
                state.concrete_section_states,
                state.connector_states,
                strict=True,
            )
        )

    def integrate(
        self,
        element_displacements: Any,
        committed_state: StatefulCorotationalPartialCompositeFrame3DState,
        *,
        reference_section: TimoshenkoFrame3DSection,
    ) -> StatefulCorotationalPartialCompositeFrame3DResponse:
        self.validate_reference_section(reference_section)
        self.validate_state(committed_state)
        displacement = _displacement(element_displacements)
        elastic = corotational_frame3d_response(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacement,
            section=reference_section,
            local_axis_roll_deg=self.local_axis_roll_deg,
        )
        selected, jacobian, hessians = self._selected_basic_derivatives(displacement)
        local, slip_nodes, local_iterations = self._solve_local(
            selected,
            committed_state,
        )
        reference_tangent = self._elastic_reference_basic_tangent()
        correction_force = local.basic_force - reference_tangent @ selected
        correction_tangent = local.condensed_tangent - reference_tangent
        global_correction = jacobian.T @ correction_force
        global_tangent_correction = jacobian.T @ correction_tangent @ jacobian
        for index in range(5):
            global_tangent_correction += correction_force[index] * hessians[index]
        internal = np.asarray(elastic.internal_force_global) + global_correction
        tangent = (
            np.asarray(elastic.consistent_tangent_global)
            + global_tangent_correction
        )
        tangent = 0.5 * (tangent + tangent.T)
        if not np.all(np.isfinite(internal)) or not np.all(np.isfinite(tangent)):
            raise ValueError("partial-composite member response is non-finite")
        state = StatefulCorotationalPartialCompositeFrame3DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            element_displacements=tuple(float(value) for value in displacement),
            interface_slip_nodes_m=(
                float(slip_nodes[0]),
                float(slip_nodes[1]),
            ),
            steel_section_states=tuple(
                response.state for response in local.steel_responses
            ),
            concrete_section_states=tuple(
                response.state for response in local.concrete_responses
            ),
            connector_states=tuple(
                response.state for response in local.connector_responses
            ),
        )
        self.validate_state(state)
        return StatefulCorotationalPartialCompositeFrame3DResponse(
            parent_state_hash=committed_state.state_hash,
            elastic_reference=elastic,
            selected_basic_deformations=selected,
            partial_composite_basic_forces=local.basic_force,
            partial_composite_basic_tangent=local.condensed_tangent,
            elastic_reference_basic_tangent=reference_tangent,
            correction_basic_forces=correction_force,
            interface_slip_nodes_m=slip_nodes,
            local_equilibrium_residual_kn=local.residual,
            local_iterations=local_iterations,
            internal_force_global=internal,
            consistent_tangent_global=tangent,
            basic_jacobian=jacobian,
            steel_section_responses=local.steel_responses,
            concrete_section_responses=local.concrete_responses,
            connector_responses=local.connector_responses,
            dissipated_energy_mj=self.dissipated_energy_mj(state),
            state=state,
        )

    def initial_condensed_basic_tangent(self) -> np.ndarray:
        parent = self.initial_state()
        local = self._local_response(
            np.zeros(5, dtype=np.float64),
            np.zeros(2, dtype=np.float64),
            parent,
        )
        if float(np.linalg.norm(local.residual, ord=np.inf)) > (
            self.local_equilibrium_absolute_tolerance_kn
        ):
            raise ValueError("initial partial-composite local equilibrium is invalid")
        return immutable_array(local.condensed_tangent, dtype="<f8")

    def _solve_local(
        self,
        selected: np.ndarray,
        parent: StatefulCorotationalPartialCompositeFrame3DState,
    ) -> tuple[_LocalResponse, np.ndarray, int]:
        slip = np.asarray(parent.interface_slip_nodes_m, dtype=np.float64).copy()
        tolerance = self.local_equilibrium_absolute_tolerance_kn
        response: _LocalResponse | None = None
        residual_norm = math.inf
        iteration = 0
        for iteration in range(self.maximum_local_iterations + 1):
            response = self._local_response(selected, slip, parent)
            residual_norm = float(np.linalg.norm(response.residual, ord=np.inf))
            if residual_norm <= tolerance:
                break
            if iteration == self.maximum_local_iterations:
                raise RuntimeError(
                    "distributed partial-composite local equilibrium did not converge"
                )
            condition = float(np.linalg.cond(response.local_tangent, p=1))
            if (
                not math.isfinite(condition)
                or condition > self.maximum_local_condition_number
            ):
                raise RuntimeError(
                    "distributed partial-composite local tangent is ill-conditioned"
                )
            try:
                correction = np.linalg.solve(
                    response.local_tangent,
                    -response.residual,
                )
            except np.linalg.LinAlgError as exc:
                raise RuntimeError(
                    "distributed partial-composite local tangent is singular"
                ) from exc
            if correction.shape != (2,) or not np.all(np.isfinite(correction)):
                raise RuntimeError(
                    "distributed partial-composite local correction is invalid"
                )
            accepted = False
            accepted_increment = math.inf
            for alpha in self.line_search_alphas:
                candidate = slip + alpha * correction
                candidate_response = self._local_response(selected, candidate, parent)
                candidate_norm = float(
                    np.linalg.norm(candidate_response.residual, ord=np.inf)
                )
                if candidate_norm < residual_norm or candidate_norm <= tolerance:
                    slip = candidate
                    accepted_increment = float(
                        np.linalg.norm(alpha * correction, ord=np.inf)
                    )
                    accepted = True
                    break
            if not accepted:
                raise RuntimeError(
                    "distributed partial-composite local line search failed without fallback"
                )
            if accepted_increment <= self.local_increment_tolerance_m:
                response = self._local_response(selected, slip, parent)
                if float(np.linalg.norm(response.residual, ord=np.inf)) <= tolerance:
                    break
        assert response is not None
        response = self._local_response(selected, slip, parent)
        if float(np.linalg.norm(response.residual, ord=np.inf)) > tolerance:
            raise RuntimeError(
                "distributed partial-composite accepted local residual is invalid"
            )
        return response, slip, iteration

    def _local_response(
        self,
        selected: np.ndarray,
        slip_nodes: np.ndarray,
        parent: StatefulCorotationalPartialCompositeFrame3DState,
    ) -> _LocalResponse:
        points, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
        steel_partition, concrete_partition = self.slip_partition
        slip_gradient = self._slip_gradient()
        steel_slip = np.zeros((3, 2), dtype=np.float64)
        concrete_slip = np.zeros((3, 2), dtype=np.float64)
        steel_slip[0, :] = steel_partition * slip_gradient
        concrete_slip[0, :] = -concrete_partition * slip_gradient
        basic_force = np.zeros(5, dtype=np.float64)
        basic_tangent = np.zeros((5, 5), dtype=np.float64)
        coupling = np.zeros((5, 2), dtype=np.float64)
        residual = np.zeros(2, dtype=np.float64)
        local_tangent = np.zeros((2, 2), dtype=np.float64)
        steel_responses: list[StatefulBiaxialFiberSectionResponse] = []
        concrete_responses: list[StatefulBiaxialFiberSectionResponse] = []
        connector_responses: list[BondSlipResponse] = []
        for xi, weight, steel_parent, concrete_parent, connector_parent in zip(
            points,
            weights,
            parent.steel_section_states,
            parent.concrete_section_states,
            parent.connector_states,
            strict=True,
        ):
            frame_strain = self._strain_matrix(xi)
            steel_strain = frame_strain @ selected + steel_slip @ slip_nodes
            concrete_strain = frame_strain @ selected + concrete_slip @ slip_nodes
            steel = self.steel_section.integrate(steel_strain, steel_parent)
            concrete = self.concrete_section.integrate(
                concrete_strain,
                concrete_parent,
            )
            shape = self._slip_shape(xi)
            connector = integrate_bond_slip(
                float(shape @ slip_nodes),
                connector_parent,
                self.connector,
            )
            factor = weight * jacobian
            steel_tangent = np.asarray(steel.consistent_tangent)
            concrete_tangent = np.asarray(concrete.consistent_tangent)
            basic_force += (
                frame_strain.T @ (steel.resultants + concrete.resultants) * factor
            )
            basic_tangent += (
                frame_strain.T
                @ (steel_tangent + concrete_tangent)
                @ frame_strain
                * factor
            )
            coupling += (
                frame_strain.T
                @ (
                    steel_tangent @ steel_slip
                    + concrete_tangent @ concrete_slip
                )
                * factor
            )
            connector_force_kn_per_m = (
                connector.force_n * _N_TO_KN / self.connector_spacing_m
            )
            connector_tangent_kn_per_m2 = (
                connector.consistent_tangent_n_per_m
                * _N_TO_KN
                / self.connector_spacing_m
            )
            residual += (
                steel_slip.T @ steel.resultants
                + concrete_slip.T @ concrete.resultants
                + shape * connector_force_kn_per_m
            ) * factor
            local_tangent += (
                steel_slip.T @ steel_tangent @ steel_slip
                + concrete_slip.T @ concrete_tangent @ concrete_slip
                + np.outer(shape, shape) * connector_tangent_kn_per_m2
            ) * factor
            steel_responses.append(steel)
            concrete_responses.append(concrete)
            connector_responses.append(connector)
        basic_tangent = 0.5 * (basic_tangent + basic_tangent.T)
        local_tangent = 0.5 * (local_tangent + local_tangent.T)
        try:
            condensed = basic_tangent - coupling @ np.linalg.solve(
                local_tangent,
                coupling.T,
            )
        except np.linalg.LinAlgError as exc:
            raise RuntimeError(
                "distributed partial-composite local tangent is singular"
            ) from exc
        condensed = 0.5 * (condensed + condensed.T)
        if not all(
            np.all(np.isfinite(values))
            for values in (
                basic_force,
                condensed,
                residual,
                local_tangent,
            )
        ):
            raise RuntimeError("distributed partial-composite local response is invalid")
        return _LocalResponse(
            basic_force=basic_force,
            condensed_tangent=condensed,
            residual=residual,
            local_tangent=local_tangent,
            steel_responses=tuple(steel_responses),
            concrete_responses=tuple(concrete_responses),
            connector_responses=tuple(connector_responses),
        )

    def _selected_basic(self, displacement: np.ndarray) -> np.ndarray:
        kinematics = corotational_frame3d_basic_kinematics(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacement,
            local_axis_roll_deg=self.local_axis_roll_deg,
        )
        return np.asarray(
            kinematics.basic_deformations[list(_SELECTED_BASIC_INDICES)],
            dtype=np.float64,
        )

    def _strain_matrix(self, xi: float) -> np.ndarray:
        coordinate = _finite(xi, name="xi")
        if not -1.0 <= coordinate <= 1.0:
            raise ValueError("xi must be in [-1, 1]")
        length = self.initial_length_m
        first = (3.0 * coordinate - 1.0) / length
        second = (3.0 * coordinate + 1.0) / length
        return np.asarray(
            (
                (1.0 / length, 0.0, 0.0, 0.0, 0.0),
                (0.0, first, 0.0, second, 0.0),
                (0.0, 0.0, first, 0.0, second),
            ),
            dtype=np.float64,
        )

    def _slip_shape(self, xi: float) -> np.ndarray:
        coordinate = _finite(xi, name="xi")
        if not -1.0 <= coordinate <= 1.0:
            raise ValueError("xi must be in [-1, 1]")
        return np.asarray(
            (0.5 * (1.0 - coordinate), 0.5 * (1.0 + coordinate)),
            dtype=np.float64,
        )

    def _slip_gradient(self) -> np.ndarray:
        return np.asarray(
            (-1.0 / self.initial_length_m, 1.0 / self.initial_length_m),
            dtype=np.float64,
        )

    def _elastic_reference_basic_tangent(self) -> np.ndarray:
        points, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
        section_tangent = (
            np.asarray(self.steel_section.initial_consistent_tangent())
            + np.asarray(self.concrete_section.initial_consistent_tangent())
        )
        tangent = np.zeros((5, 5), dtype=np.float64)
        for xi, weight in zip(points, weights, strict=True):
            strain_matrix = self._strain_matrix(xi)
            tangent += (
                strain_matrix.T @ section_tangent @ strain_matrix * weight * jacobian
            )
        return 0.5 * (tangent + tangent.T)

    def _selected_basic_derivatives(
        self,
        displacement: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        center = self._selected_basic(displacement)
        length = self.initial_length_m
        jacobian_steps = np.asarray(
            [1.0e-6 * max(length, 1.0)] * 3
            + [1.0e-6] * 3
            + [1.0e-6 * max(length, 1.0)] * 3
            + [1.0e-6] * 3,
            dtype=np.float64,
        )
        hessian_steps = np.asarray(
            [2.0e-4 * max(length, 1.0)] * 3
            + [2.0e-4] * 3
            + [2.0e-4 * max(length, 1.0)] * 3
            + [2.0e-4] * 3,
            dtype=np.float64,
        )
        jacobian = np.empty((5, 12), dtype=np.float64)
        hessians = np.empty((5, 12, 12), dtype=np.float64)
        for first in range(12):
            step = jacobian_steps[first]
            plus_one = displacement.copy()
            minus_one = displacement.copy()
            plus_two = displacement.copy()
            minus_two = displacement.copy()
            plus_one[first] += step
            minus_one[first] -= step
            plus_two[first] += 2.0 * step
            minus_two[first] -= 2.0 * step
            jacobian[:, first] = (
                -self._selected_basic(plus_two)
                + 8.0 * self._selected_basic(plus_one)
                - 8.0 * self._selected_basic(minus_one)
                + self._selected_basic(minus_two)
            ) / (12.0 * step)

            second_step = hessian_steps[first]
            plus_one = displacement.copy()
            minus_one = displacement.copy()
            plus_two = displacement.copy()
            minus_two = displacement.copy()
            plus_one[first] += second_step
            minus_one[first] -= second_step
            plus_two[first] += 2.0 * second_step
            minus_two[first] -= 2.0 * second_step
            hessians[:, first, first] = (
                -self._selected_basic(plus_two)
                + 16.0 * self._selected_basic(plus_one)
                - 30.0 * center
                + 16.0 * self._selected_basic(minus_one)
                - self._selected_basic(minus_two)
            ) / (12.0 * second_step**2)
            for second in range(first + 1, 12):
                other_step = hessian_steps[second]
                plus_plus = displacement.copy()
                plus_minus = displacement.copy()
                minus_plus = displacement.copy()
                minus_minus = displacement.copy()
                plus_plus[first] += second_step
                plus_plus[second] += other_step
                plus_minus[first] += second_step
                plus_minus[second] -= other_step
                minus_plus[first] -= second_step
                minus_plus[second] += other_step
                minus_minus[first] -= second_step
                minus_minus[second] -= other_step
                values = (
                    self._selected_basic(plus_plus)
                    - self._selected_basic(plus_minus)
                    - self._selected_basic(minus_plus)
                    + self._selected_basic(minus_minus)
                ) / (4.0 * second_step * other_step)
                hessians[:, first, second] = values
                hessians[:, second, first] = values
        return center, jacobian, hessians


__all__ = [
    "STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_PROFILE",
    "STATEFUL_COROTATIONAL_PARTIAL_COMPOSITE_FRAME3D_STATE_SCHEMA_VERSION",
    "StatefulCorotationalPartialCompositeFrame3D",
    "StatefulCorotationalPartialCompositeFrame3DResponse",
    "StatefulCorotationalPartialCompositeFrame3DState",
]
