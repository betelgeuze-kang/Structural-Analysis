"""Bounded axial steel-concrete partial-interaction material point."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any

from structural_analysis.materials.bond_slip import (
    BondSlipMaterial,
    BondSlipResponse,
    BondSlipState,
    integrate_bond_slip,
)


PARTIAL_COMPOSITE_PROFILE = "axial_two_layer_discrete_connector.v1"
CONDENSED_PARTIAL_COMPOSITE_AXIAL_PROFILE = (
    "axial_two_layer_single_slip_mode_static_condensation.v1"
)
CONDENSED_PARTIAL_COMPOSITE_AXIAL_STATE_SCHEMA_VERSION = (
    "condensed-partial-composite-axial-state.v1"
)
PARTIAL_COMPOSITE_CLAIM_BOUNDARY = (
    "One axial steel layer, one axial concrete layer, and one local connector "
    "material point. It is not a distributed beam formulation, shear-lag model, "
    "uplift/contact model, published composite-member validation, or design authority."
)
CONDENSED_PARTIAL_COMPOSITE_AXIAL_CLAIM_BOUNDARY = (
    "One two-layer axial member mode with a single internal interface-slip "
    "coordinate statically condensed from exact same-parent connector tangents. "
    "It verifies member-level bond-slip, partial-interaction, cyclic state, and "
    "checkpoint coupling only. It is not a distributed connector field, composite "
    "beam bending/shear-lag/uplift model, published validation, production-scale "
    "3D authority, or design authority."
)
_CONDENSED_STATE_DOMAIN = (
    b"structural-analysis/condensed-partial-composite-axial-state/v1\0"
)


def _positive(name: str, value: Any) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


@dataclass(frozen=True)
class PartialCompositeMaterial:
    steel_axial_rigidity_n: float = 4.0e8
    concrete_axial_rigidity_n: float = 6.0e8
    connector: BondSlipMaterial = field(default_factory=BondSlipMaterial)
    material_id: str = "partial_composite_axial_connector_point"

    def __post_init__(self) -> None:
        for name in (
            "steel_axial_rigidity_n",
            "concrete_axial_rigidity_n",
        ):
            object.__setattr__(self, name, _positive(name, getattr(self, name)))
        if type(self.connector) is not BondSlipMaterial:
            raise ValueError("connector must be an exact BondSlipMaterial")
        if not self.material_id.strip():
            raise ValueError("material_id must be non-empty")


@dataclass(frozen=True)
class PartialCompositeState:
    connector_state: BondSlipState = field(default_factory=BondSlipState)

    def canonical_bytes(self) -> bytes:
        encoded = self.connector_state.canonical_bytes()
        return struct.pack("<Q", len(encoded)) + encoded

    @property
    def state_hash(self) -> str:
        return self.connector_state.state_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "partial-composite-state.v1",
            "connector_state": self.connector_state.to_dict(),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class PartialCompositeResponse:
    steel_strain: float
    concrete_strain: float
    interface_slip_m: float
    steel_axial_force_n: float
    concrete_axial_force_n: float
    connector_force_n: float
    combined_axial_force_n: float
    generalized_tangent: tuple[tuple[float, float, float], ...]
    interaction_ratio: float
    committed_state_hash: str
    connector_response: BondSlipResponse
    state: PartialCompositeState

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": PARTIAL_COMPOSITE_PROFILE,
            "steel_strain": self.steel_strain,
            "concrete_strain": self.concrete_strain,
            "interface_slip_m": self.interface_slip_m,
            "steel_axial_force_n": self.steel_axial_force_n,
            "concrete_axial_force_n": self.concrete_axial_force_n,
            "connector_force_n": self.connector_force_n,
            "combined_axial_force_n": self.combined_axial_force_n,
            "generalized_tangent": [list(row) for row in self.generalized_tangent],
            "interaction_ratio": self.interaction_ratio,
            "committed_state_hash": self.committed_state_hash,
            "connector_response": self.connector_response.to_dict(),
            "trial_state_hash": self.state.state_hash,
            "claim_boundary": PARTIAL_COMPOSITE_CLAIM_BOUNDARY,
        }


@dataclass(frozen=True)
class CondensedPartialCompositeAxialState:
    total_strain: float = 0.0
    interface_slip_m: float = 0.0
    component_state: PartialCompositeState = field(
        default_factory=PartialCompositeState
    )

    def __post_init__(self) -> None:
        for name in ("total_strain", "interface_slip_m"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if type(self.component_state) is not PartialCompositeState:
            raise ValueError("component_state must be an exact PartialCompositeState")

    def canonical_bytes(self) -> bytes:
        component = self.component_state.canonical_bytes()
        return b"".join(
            (
                _CONDENSED_STATE_DOMAIN,
                struct.pack(
                    "<2dQ",
                    self.total_strain,
                    self.interface_slip_m,
                    len(component),
                ),
                component,
            )
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONDENSED_PARTIAL_COMPOSITE_AXIAL_STATE_SCHEMA_VERSION,
            "total_strain": self.total_strain,
            "interface_slip_m": self.interface_slip_m,
            "component_state": self.component_state.to_dict(),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class CondensedPartialCompositeAxialResponse:
    total_strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    combined_axial_force_n: float
    interface_slip_m: float
    internal_equilibrium_residual_n: float
    local_iterations: int
    committed_state_hash: str
    partial_composite_response: PartialCompositeResponse
    state: CondensedPartialCompositeAxialState
    profile: str = CONDENSED_PARTIAL_COMPOSITE_AXIAL_PROFILE
    claim_boundary: str = CONDENSED_PARTIAL_COMPOSITE_AXIAL_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "total_strain": self.total_strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "combined_axial_force_n": self.combined_axial_force_n,
            "interface_slip_m": self.interface_slip_m,
            "internal_equilibrium_residual_n": (self.internal_equilibrium_residual_n),
            "local_iterations": self.local_iterations,
            "committed_state_hash": self.committed_state_hash,
            "partial_composite_response": self.partial_composite_response.to_dict(),
            "trial_state": self.state.to_dict(),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class CondensedPartialCompositeAxialMaterial:
    """Two elastic layers with one connector-slip mode condensed per member.

    The frame supplies one total axial strain. The internal coordinate ``s`` uses
    ``epsilon_s = epsilon + s/L`` and ``epsilon_c = epsilon - s/L``. Local
    equilibrium is ``N_s - N_c + F_connector = 0``. Its exact scalar Schur
    complement supplies the member's algorithmic axial tangent.
    """

    partial_composite: PartialCompositeMaterial = field(
        default_factory=PartialCompositeMaterial
    )
    member_length_m: float = 3.0
    reference_area_m2: float = 0.01
    local_equilibrium_absolute_tolerance_n: float = 1.0e-6
    local_increment_tolerance_m: float = 1.0e-13
    maximum_local_iterations: int = 30
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
    )
    material_id: str = "condensed_partial_composite_axial_member"

    def __post_init__(self) -> None:
        if type(self.partial_composite) is not PartialCompositeMaterial:
            raise ValueError(
                "partial_composite must be an exact PartialCompositeMaterial"
            )
        for name in (
            "member_length_m",
            "reference_area_m2",
            "local_equilibrium_absolute_tolerance_n",
            "local_increment_tolerance_m",
        ):
            object.__setattr__(self, name, _positive(name, getattr(self, name)))
        if (
            type(self.maximum_local_iterations) is not int
            or self.maximum_local_iterations < 1
        ):
            raise ValueError("maximum_local_iterations must be a positive integer")
        if (
            not isinstance(self.line_search_alphas, tuple)
            or not self.line_search_alphas
        ):
            raise ValueError("line_search_alphas must be a non-empty tuple")
        normalized: list[float] = []
        previous = math.inf
        for value in self.line_search_alphas:
            alpha = _positive("line_search_alpha", value)
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized.append(alpha)
            previous = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized))
        if not self.material_id.strip():
            raise ValueError("material_id must be non-empty")

    @property
    def initial_effective_modulus_mpa(self) -> float:
        steel = self.partial_composite.steel_axial_rigidity_n
        concrete = self.partial_composite.concrete_axial_rigidity_n
        connector = self.partial_composite.connector.initial_stiffness_n_per_m
        denominator = steel + concrete + connector * self.member_length_m
        condensed_rigidity = steel + concrete - (steel - concrete) ** 2 / denominator
        return condensed_rigidity / (self.reference_area_m2 * 1.0e6)

    def initial_state(self) -> CondensedPartialCompositeAxialState:
        return CondensedPartialCompositeAxialState()

    def integrate(
        self,
        total_strain: float,
        committed_state: CondensedPartialCompositeAxialState,
    ) -> CondensedPartialCompositeAxialResponse:
        strain = float(total_strain)
        if not math.isfinite(strain):
            raise ValueError("total_strain must be finite")
        if type(committed_state) is not CondensedPartialCompositeAxialState:
            raise ValueError(
                "committed_state must be an exact CondensedPartialCompositeAxialState"
            )
        slip = committed_state.interface_slip_m
        tolerance = self.local_equilibrium_absolute_tolerance_n
        response: PartialCompositeResponse | None = None
        residual = math.inf
        iteration = 0
        for iteration in range(self.maximum_local_iterations + 1):
            response, residual, jacobian = self._local_response(
                strain,
                slip,
                committed_state.component_state,
            )
            if abs(residual) <= tolerance:
                break
            if iteration == self.maximum_local_iterations:
                raise RuntimeError(
                    "partial-composite local equilibrium did not converge"
                )
            if not math.isfinite(jacobian) or abs(jacobian) <= 1.0e-12:
                raise RuntimeError("partial-composite local tangent is singular")
            correction = -residual / jacobian
            if not math.isfinite(correction):
                raise RuntimeError("partial-composite local correction is non-finite")
            accepted = False
            for alpha in self.line_search_alphas:
                candidate = slip + alpha * correction
                _, candidate_residual, _ = self._local_response(
                    strain,
                    candidate,
                    committed_state.component_state,
                )
                if abs(candidate_residual) < abs(residual):
                    slip = candidate
                    accepted = True
                    break
            if not accepted:
                raise RuntimeError(
                    "partial-composite local line search failed without fallback"
                )
            if abs(alpha * correction) <= self.local_increment_tolerance_m:
                response, residual, _ = self._local_response(
                    strain,
                    slip,
                    committed_state.component_state,
                )
                if abs(residual) <= tolerance:
                    break
        assert response is not None
        response, residual, jacobian = self._local_response(
            strain,
            slip,
            committed_state.component_state,
        )
        if abs(residual) > tolerance:
            raise RuntimeError("partial-composite accepted local residual is invalid")
        steel = self.partial_composite.steel_axial_rigidity_n
        concrete = self.partial_composite.concrete_axial_rigidity_n
        slip_derivative = -(steel - concrete) / jacobian
        force_tangent_n = (
            steel
            + concrete
            + (steel - concrete) * slip_derivative / self.member_length_m
        )
        stress = response.combined_axial_force_n / (self.reference_area_m2 * 1.0e6)
        tangent = force_tangent_n / (self.reference_area_m2 * 1.0e6)
        if not all(math.isfinite(value) for value in (stress, tangent)):
            raise RuntimeError("partial-composite condensed response is non-finite")
        state = CondensedPartialCompositeAxialState(
            total_strain=strain,
            interface_slip_m=slip,
            component_state=response.state,
        )
        return CondensedPartialCompositeAxialResponse(
            total_strain=strain,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            combined_axial_force_n=response.combined_axial_force_n,
            interface_slip_m=slip,
            internal_equilibrium_residual_n=residual,
            local_iterations=iteration,
            committed_state_hash=committed_state.state_hash,
            partial_composite_response=response,
            state=state,
        )

    def _local_response(
        self,
        strain: float,
        slip_m: float,
        committed_state: PartialCompositeState,
    ) -> tuple[PartialCompositeResponse, float, float]:
        length = self.member_length_m
        response = integrate_partial_composite(
            steel_strain=strain + slip_m / length,
            concrete_strain=strain - slip_m / length,
            interface_slip_m=slip_m,
            committed_state=committed_state,
            material=self.partial_composite,
        )
        residual = (
            response.steel_axial_force_n
            - response.concrete_axial_force_n
            + response.connector_force_n
        )
        jacobian = (
            self.partial_composite.steel_axial_rigidity_n
            + self.partial_composite.concrete_axial_rigidity_n
        ) / length + response.connector_response.consistent_tangent_n_per_m
        return response, residual, jacobian


def integrate_partial_composite(
    *,
    steel_strain: float,
    concrete_strain: float,
    interface_slip_m: float,
    committed_state: PartialCompositeState,
    material: PartialCompositeMaterial | None = None,
) -> PartialCompositeResponse:
    selected = material or PartialCompositeMaterial()
    steel = float(steel_strain)
    concrete = float(concrete_strain)
    if not math.isfinite(steel) or not math.isfinite(concrete):
        raise ValueError("constituent strains must be finite")
    connector = integrate_bond_slip(
        interface_slip_m,
        committed_state.connector_state,
        selected.connector,
    )
    steel_force = selected.steel_axial_rigidity_n * steel
    concrete_force = selected.concrete_axial_rigidity_n * concrete
    state = PartialCompositeState(connector_state=connector.state)
    return PartialCompositeResponse(
        steel_strain=steel,
        concrete_strain=concrete,
        interface_slip_m=connector.slip_m,
        steel_axial_force_n=steel_force,
        concrete_axial_force_n=concrete_force,
        connector_force_n=connector.force_n,
        combined_axial_force_n=steel_force + concrete_force,
        generalized_tangent=(
            (selected.steel_axial_rigidity_n, 0.0, 0.0),
            (0.0, selected.concrete_axial_rigidity_n, 0.0),
            (0.0, 0.0, connector.consistent_tangent_n_per_m),
        ),
        interaction_ratio=connector.interaction_ratio,
        committed_state_hash=committed_state.state_hash,
        connector_response=connector,
        state=state,
    )


__all__ = [
    "CONDENSED_PARTIAL_COMPOSITE_AXIAL_CLAIM_BOUNDARY",
    "CONDENSED_PARTIAL_COMPOSITE_AXIAL_PROFILE",
    "CONDENSED_PARTIAL_COMPOSITE_AXIAL_STATE_SCHEMA_VERSION",
    "PARTIAL_COMPOSITE_CLAIM_BOUNDARY",
    "PARTIAL_COMPOSITE_PROFILE",
    "CondensedPartialCompositeAxialMaterial",
    "CondensedPartialCompositeAxialResponse",
    "CondensedPartialCompositeAxialState",
    "PartialCompositeMaterial",
    "PartialCompositeResponse",
    "PartialCompositeState",
    "integrate_partial_composite",
]
