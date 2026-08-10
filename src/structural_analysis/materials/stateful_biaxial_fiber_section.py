"""Stateful small-strain axial-biaxial fiber-section candidate.

Plane sections remain plane and every fiber is evaluated from one immutable
accepted material parent. The section supplies conjugate ``[N, My, Mz]``
resultants and the exact symmetric ``3 x 3`` algorithmic tangent assembled from
the same constituent responses. Member integration and corotational geometry
belong to the element/assembly layers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import struct
from typing import Any, TypeAlias, TypeGuard

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.confined_concrete import (
    ConfinedConcreteMaterial,
    ConfinedConcreteState,
    StatefulConfinedConcreteResponse,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)


STATEFUL_BIAXIAL_FIBER_SECTION_PROFILE = (
    "plane_section_axial_biaxial_discrete_fibers.v1"
)
STATEFUL_BIAXIAL_FIBER_SECTION_STATE_SCHEMA_VERSION = (
    "stateful-biaxial-fiber-section-state.v1"
)
STATEFUL_BIAXIAL_FIBER_SECTION_CLAIM_BOUNDARY = (
    "Bounded small-strain axial-biaxial plane-section integration with exact "
    "same-parent uniaxial material tangents. It is not a shear/torsion section, "
    "multiaxial material law, localization/mesh-objectivity proof, distributed "
    "member by itself, published validation, or design authority."
)
_STATE_DOMAIN = b"structural-analysis/stateful-biaxial-fiber-section-state/v1\0"
_MPA_M2_TO_KN = 1000.0

FiberMaterial: TypeAlias = (
    BilinearCombinedHardeningSteel
    | AsymmetricConcreteDamageMaterial
    | FractureEnergyConcreteDamageMaterial
    | ConfinedConcreteMaterial
)
FiberState: TypeAlias = (
    UniaxialPlasticityState | ConcreteDamageState | ConfinedConcreteState
)
FiberResponse: TypeAlias = (
    UniaxialPlasticityResponse
    | ConcreteDamageResponse
    | StatefulConfinedConcreteResponse
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


def _generalized_strain(values: Any) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("generalized_strain must be a finite three-vector") from exc
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("generalized_strain must be a finite three-vector")
    return np.array(vector, dtype=np.float64, copy=True)


@dataclass(frozen=True)
class StatefulBiaxialSectionFiber:
    fiber_id: str
    y_m: float
    z_m: float
    area_m2: float
    material: FiberMaterial

    def __post_init__(self) -> None:
        normalized_id = str(self.fiber_id).strip()
        if not normalized_id:
            raise ValueError("fiber_id must be non-empty")
        object.__setattr__(self, "fiber_id", normalized_id)
        object.__setattr__(self, "y_m", _finite(self.y_m, name="y_m"))
        object.__setattr__(self, "z_m", _finite(self.z_m, name="z_m"))
        object.__setattr__(self, "area_m2", _positive(self.area_m2, name="area_m2"))
        if not _supported_material(self.material):
            raise ValueError("material must be a supported exact uniaxial material")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "fiber_id": self.fiber_id,
            "y_m": self.y_m,
            "z_m": self.z_m,
            "area_m2": self.area_m2,
            "material": _material_manifest(self.material),
        }


@dataclass(frozen=True)
class StatefulBiaxialFiberSectionState:
    section_id: str
    section_contract_hash: str
    axial_strain: float
    curvature_y_per_m: float
    curvature_z_per_m: float
    fiber_states: tuple[FiberState, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.section_id).strip()
        if not normalized_id:
            raise ValueError("section_id must be non-empty")
        object.__setattr__(self, "section_id", normalized_id)
        object.__setattr__(
            self,
            "section_contract_hash",
            _hash(self.section_contract_hash, name="section_contract_hash"),
        )
        for name in (
            "axial_strain",
            "curvature_y_per_m",
            "curvature_z_per_m",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if not isinstance(self.fiber_states, tuple) or not self.fiber_states:
            raise ValueError("fiber_states must be a non-empty tuple")
        if not all(
            type(state)
            in (UniaxialPlasticityState, ConcreteDamageState, ConfinedConcreteState)
            for state in self.fiber_states
        ):
            raise ValueError("fiber_states contains an unsupported state type")

    def canonical_bytes(self) -> bytes:
        section_id = self.section_id.encode("utf-8")
        contract_hash = self.section_contract_hash.encode("ascii")
        chunks = [
            _STATE_DOMAIN,
            struct.pack("<Q", len(section_id)),
            section_id,
            struct.pack("<Q", len(contract_hash)),
            contract_hash,
            struct.pack(
                "<3dQ",
                self.axial_strain,
                self.curvature_y_per_m,
                self.curvature_z_per_m,
                len(self.fiber_states),
            ),
        ]
        for state in self.fiber_states:
            if type(state) is UniaxialPlasticityState:
                tag = b"steel"
            elif type(state) is ConcreteDamageState:
                tag = b"concrete"
            else:
                tag = b"confined-concrete"
            encoded = state.canonical_bytes()
            chunks.extend(
                (
                    struct.pack("<Q", len(tag)),
                    tag,
                    struct.pack("<Q", len(encoded)),
                    encoded,
                )
            )
        return b"".join(chunks)

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_BIAXIAL_FIBER_SECTION_STATE_SCHEMA_VERSION,
            "section_id": self.section_id,
            "section_contract_hash": self.section_contract_hash,
            "axial_strain": self.axial_strain,
            "curvature_y_per_m": self.curvature_y_per_m,
            "curvature_z_per_m": self.curvature_z_per_m,
            "fiber_states": [state.to_dict() for state in self.fiber_states],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulBiaxialFiberSectionResponse:
    parent_state_hash: str
    generalized_strain: np.ndarray
    resultants: np.ndarray
    consistent_tangent: np.ndarray
    fiber_strains: np.ndarray
    fiber_stresses_mpa: np.ndarray
    fiber_responses: tuple[FiberResponse, ...]
    yielded_steel_fiber_count: int
    damaged_concrete_fiber_count: int
    dissipated_energy_mj_per_m: float
    state: StatefulBiaxialFiberSectionState
    profile: str = STATEFUL_BIAXIAL_FIBER_SECTION_PROFILE
    claim_boundary: str = STATEFUL_BIAXIAL_FIBER_SECTION_CLAIM_BOUNDARY

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "generalized_strain",
            immutable_array(self.generalized_strain, dtype="<f8"),
        )
        object.__setattr__(
            self,
            "resultants",
            immutable_array(self.resultants, dtype="<f8"),
        )
        object.__setattr__(
            self,
            "consistent_tangent",
            immutable_array(self.consistent_tangent, dtype="<f8"),
        )
        object.__setattr__(
            self,
            "fiber_strains",
            immutable_array(self.fiber_strains, dtype="<f8"),
        )
        object.__setattr__(
            self,
            "fiber_stresses_mpa",
            immutable_array(self.fiber_stresses_mpa, dtype="<f8"),
        )
        if self.generalized_strain.shape != (3,) or self.resultants.shape != (3,):
            raise ValueError("generalized strain and resultants must be three-vectors")
        if self.consistent_tangent.shape != (3, 3):
            raise ValueError("consistent_tangent must be 3 by 3")
        if self.fiber_strains.shape != self.fiber_stresses_mpa.shape:
            raise ValueError("fiber strain/stress shapes must match")

    @property
    def axial_force_kn(self) -> float:
        return float(self.resultants[0])

    @property
    def moment_y_kn_m(self) -> float:
        return float(self.resultants[1])

    @property
    def moment_z_kn_m(self) -> float:
        return float(self.resultants[2])

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "parent_state_hash": self.parent_state_hash,
            "generalized_strain": {
                "axial_strain": float(self.generalized_strain[0]),
                "curvature_y_per_m": float(self.generalized_strain[1]),
                "curvature_z_per_m": float(self.generalized_strain[2]),
            },
            "resultants": {
                "axial_force_kn": self.axial_force_kn,
                "moment_y_kn_m": self.moment_y_kn_m,
                "moment_z_kn_m": self.moment_z_kn_m,
            },
            "consistent_tangent": self.consistent_tangent.tolist(),
            "fiber_strains": self.fiber_strains.tolist(),
            "fiber_stresses_mpa": self.fiber_stresses_mpa.tolist(),
            "fiber_responses": [row.to_dict() for row in self.fiber_responses],
            "yielded_steel_fiber_count": self.yielded_steel_fiber_count,
            "damaged_concrete_fiber_count": self.damaged_concrete_fiber_count,
            "dissipated_energy_mj_per_m": self.dissipated_energy_mj_per_m,
            "trial_state": self.state.to_dict(),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class StatefulBiaxialFiberSection:
    fibers: tuple[StatefulBiaxialSectionFiber, ...]
    section_id: str = "stateful_biaxial_fiber_section"

    def __post_init__(self) -> None:
        normalized_id = str(self.section_id).strip()
        if not normalized_id:
            raise ValueError("section_id must be non-empty")
        object.__setattr__(self, "section_id", normalized_id)
        if not isinstance(self.fibers, tuple) or not self.fibers:
            raise ValueError("fibers must be a non-empty tuple")
        if not all(type(fiber) is StatefulBiaxialSectionFiber for fiber in self.fibers):
            raise ValueError(
                "fibers must contain exact StatefulBiaxialSectionFiber rows"
            )
        ids = tuple(fiber.fiber_id for fiber in self.fibers)
        if len(set(ids)) != len(ids):
            raise ValueError("fiber_id values must be unique")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            {
                "profile": STATEFUL_BIAXIAL_FIBER_SECTION_PROFILE,
                "section_id": self.section_id,
                "strain_relation": "epsilon=epsilon0+curvature_y*z-curvature_z*y",
                "resultants": "N=sum(F);My=sum(F*z);Mz=-sum(F*y)",
                "fibers": [fiber.to_manifest() for fiber in self.fibers],
            }
        )

    def initial_state(self) -> StatefulBiaxialFiberSectionState:
        return StatefulBiaxialFiberSectionState(
            section_id=self.section_id,
            section_contract_hash=self.contract_hash,
            axial_strain=0.0,
            curvature_y_per_m=0.0,
            curvature_z_per_m=0.0,
            fiber_states=tuple(
                _initial_material_state(fiber.material) for fiber in self.fibers
            ),
        )

    def validate_state(self, state: StatefulBiaxialFiberSectionState) -> None:
        if type(state) is not StatefulBiaxialFiberSectionState:
            raise ValueError("state type is invalid")
        if state.section_id != self.section_id:
            raise ValueError("state section_id does not match section")
        if state.section_contract_hash != self.contract_hash:
            raise ValueError("state section_contract_hash does not match section")
        if len(state.fiber_states) != len(self.fibers):
            raise ValueError("state fiber count does not match section")
        if any(
            not _material_state_matches(fiber.material, material_state)
            for fiber, material_state in zip(
                self.fibers,
                state.fiber_states,
                strict=True,
            )
        ):
            raise ValueError("state fiber material type does not match section")

    def dissipated_energy_mj_per_m(
        self,
        state: StatefulBiaxialFiberSectionState,
    ) -> float:
        self.validate_state(state)
        return math.fsum(
            fiber.area_m2
            * float(
                getattr(
                    material_state,
                    "dissipated_energy_density_mj_per_m3",
                    0.0,
                )
            )
            for fiber, material_state in zip(
                self.fibers,
                state.fiber_states,
                strict=True,
            )
        )

    def initial_consistent_tangent(self) -> np.ndarray:
        response = self.integrate(np.zeros(3), self.initial_state())
        return response.consistent_tangent

    def integrate(
        self,
        generalized_strain: Any,
        committed_state: StatefulBiaxialFiberSectionState,
    ) -> StatefulBiaxialFiberSectionResponse:
        self.validate_state(committed_state)
        generalized = _generalized_strain(generalized_strain)
        axial, curvature_y, curvature_z = map(float, generalized)
        resultants = np.zeros(3, dtype=np.float64)
        tangent = np.zeros((3, 3), dtype=np.float64)
        strains: list[float] = []
        stresses: list[float] = []
        responses: list[FiberResponse] = []
        states: list[FiberState] = []
        yielded = 0
        damaged = 0
        for fiber, parent in zip(
            self.fibers,
            committed_state.fiber_states,
            strict=True,
        ):
            strain = axial + curvature_y * fiber.z_m - curvature_z * fiber.y_m
            response = _integrate_material(fiber.material, strain, parent)
            stress = float(response.stress_mpa)
            modulus = float(response.consistent_tangent_mpa)
            force = stress * fiber.area_m2 * _MPA_M2_TO_KN
            stiffness = modulus * fiber.area_m2 * _MPA_M2_TO_KN
            strain_vector = np.asarray(
                [1.0, fiber.z_m, -fiber.y_m],
                dtype=np.float64,
            )
            resultants += force * strain_vector
            tangent += stiffness * np.outer(strain_vector, strain_vector)
            strains.append(strain)
            stresses.append(stress)
            responses.append(response)
            states.append(response.state)
            yielded += int(
                isinstance(response, UniaxialPlasticityResponse) and response.yielded
            )
            damaged += int(
                isinstance(response, ConcreteDamageResponse) and response.damage_evolved
            )
        tangent[...] = 0.5 * (tangent + tangent.T)
        next_state = StatefulBiaxialFiberSectionState(
            section_id=self.section_id,
            section_contract_hash=self.contract_hash,
            axial_strain=axial,
            curvature_y_per_m=curvature_y,
            curvature_z_per_m=curvature_z,
            fiber_states=tuple(states),
        )
        return StatefulBiaxialFiberSectionResponse(
            parent_state_hash=committed_state.state_hash,
            generalized_strain=generalized,
            resultants=resultants,
            consistent_tangent=tangent,
            fiber_strains=np.asarray(strains, dtype=np.float64),
            fiber_stresses_mpa=np.asarray(stresses, dtype=np.float64),
            fiber_responses=tuple(responses),
            yielded_steel_fiber_count=yielded,
            damaged_concrete_fiber_count=damaged,
            dissipated_energy_mj_per_m=self.dissipated_energy_mj_per_m(next_state),
            state=next_state,
        )


def finite_difference_biaxial_fiber_section_tangent_check(
    section: StatefulBiaxialFiberSection,
    committed_state: StatefulBiaxialFiberSectionState,
    *,
    generalized_strain: Any,
    steps: tuple[float, float, float] = (1.0e-9, 1.0e-8, 1.0e-8),
    relative_tolerance: float = 3.0e-6,
) -> dict[str, Any]:
    generalized = _generalized_strain(generalized_strain)
    increments = np.asarray(
        [_positive(value, name=f"steps[{index}]") for index, value in enumerate(steps)],
        dtype=np.float64,
    )
    center = section.integrate(generalized, committed_state)
    finite_difference = np.empty((3, 3), dtype=np.float64)
    parent_hashes = [center.parent_state_hash]
    parent_bytes = committed_state.canonical_bytes()
    for column in range(3):
        direction = np.zeros(3, dtype=np.float64)
        direction[column] = increments[column]
        forward = section.integrate(generalized + direction, committed_state)
        backward = section.integrate(generalized - direction, committed_state)
        finite_difference[:, column] = (forward.resultants - backward.resultants) / (
            2.0 * increments[column]
        )
        parent_hashes.extend((forward.parent_state_hash, backward.parent_state_hash))
    error = finite_difference - center.consistent_tangent
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(center.consistent_tangent, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error / scale
    same_parent = bool(
        all(value == committed_state.state_hash for value in parent_hashes)
        and committed_state.canonical_bytes() == parent_bytes
    )
    return {
        "generalized_strain": generalized.tolist(),
        "analytic_consistent_tangent": center.consistent_tangent.tolist(),
        "finite_difference_tangent": finite_difference.tolist(),
        "absolute_inf_error": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(relative_error <= relative_tolerance and same_parent),
    }


def _supported_material(value: object) -> TypeGuard[FiberMaterial]:
    return type(value) in (
        BilinearCombinedHardeningSteel,
        AsymmetricConcreteDamageMaterial,
        FractureEnergyConcreteDamageMaterial,
        ConfinedConcreteMaterial,
    )


def _material_state_matches(material: FiberMaterial, state: object) -> bool:
    if type(material) is BilinearCombinedHardeningSteel:
        return type(state) is UniaxialPlasticityState
    if type(material) in (
        AsymmetricConcreteDamageMaterial,
        FractureEnergyConcreteDamageMaterial,
    ):
        return type(state) is ConcreteDamageState
    if type(material) is ConfinedConcreteMaterial:
        return type(state) is ConfinedConcreteState
    return False


def _initial_material_state(material: FiberMaterial) -> FiberState:
    if isinstance(material, BilinearCombinedHardeningSteel):
        return material.initial_state()
    if isinstance(material, AsymmetricConcreteDamageMaterial):
        return material.initial_state()
    if isinstance(material, ConfinedConcreteMaterial):
        return material.initial_state()
    raise TypeError("unsupported fiber material")


def _integrate_material(
    material: FiberMaterial,
    strain: float,
    state: FiberState,
) -> FiberResponse:
    if isinstance(material, BilinearCombinedHardeningSteel) and isinstance(
        state,
        UniaxialPlasticityState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, AsymmetricConcreteDamageMaterial) and isinstance(
        state,
        ConcreteDamageState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, ConfinedConcreteMaterial) and isinstance(
        state,
        ConfinedConcreteState,
    ):
        return material.integrate(strain, state)
    raise ValueError("fiber material and committed state types do not match")


def _material_manifest(material: FiberMaterial) -> dict[str, Any]:
    if isinstance(material, BilinearCombinedHardeningSteel):
        return {"material_type": "steel", **asdict(material)}
    if isinstance(material, FractureEnergyConcreteDamageMaterial):
        return {"material_type": "fracture_energy_concrete", **asdict(material)}
    if isinstance(material, AsymmetricConcreteDamageMaterial):
        return {"material_type": "concrete_damage", **asdict(material)}
    if isinstance(material, ConfinedConcreteMaterial):
        return {"material_type": "confined_concrete", **asdict(material)}
    raise TypeError("unsupported fiber material")


__all__ = [
    "STATEFUL_BIAXIAL_FIBER_SECTION_CLAIM_BOUNDARY",
    "STATEFUL_BIAXIAL_FIBER_SECTION_PROFILE",
    "STATEFUL_BIAXIAL_FIBER_SECTION_STATE_SCHEMA_VERSION",
    "FiberMaterial",
    "FiberResponse",
    "FiberState",
    "StatefulBiaxialFiberSection",
    "StatefulBiaxialFiberSectionResponse",
    "StatefulBiaxialFiberSectionState",
    "StatefulBiaxialSectionFiber",
    "finite_difference_biaxial_fiber_section_tangent_check",
]
