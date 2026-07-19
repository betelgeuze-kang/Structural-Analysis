"""State-updated RC fiber section with axial-curvature interaction.

This module is a bounded small-strain section reference.  Plane sections remain
plane, every fiber is evaluated from one immutable accepted material parent,
and the 2x2 axial-force/moment Jacobian is assembled from the same constituent
algorithmic tangents as the resultants.  It is not a frame element,
distributed-plasticity formulation, or production material backend.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import math
import struct
from typing import Any, Iterable, Literal

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)


STATEFUL_FIBER_SECTION_SCHEMA_VERSION = "phase2-stateful-rc-fiber-section.v1"
FIBER_SECTION_STATE_SCHEMA_VERSION = "stateful-rc-fiber-section-state.v1"
FIBER_SECTION_NEWTON_SCHEMA_VERSION = "stateful-rc-fiber-section-newton.v1"
FIBER_SECTION_STRAIN_RELATION = "epsilon_f=epsilon_0-kappa_z*y_f"
FIBER_SECTION_RESULTANT_DEFINITION = "N=sum(sigma_f*A_f);M_z=-sum(sigma_f*A_f*y_f)"
FIBER_SECTION_TANGENT_DEFINITION = "sum(A_f*E_alg_f*[[1,-y_f],[-y_f,y_f^2]])"
STATEFUL_FIBER_SECTION_CLAIM_BOUNDARY = (
    "This receipt verifies a bounded small-strain rectangular RC fiber section "
    "with plane-section axial-curvature kinematics, per-fiber combined-"
    "hardening steel and asymmetric concrete-damage states, a symmetric 2x2 "
    "algorithmic section tangent, cyclic state evolution, scaled Newton "
    "equilibrium, deterministic replay, and exact failed-step rollback. It "
    "does not validate a frame or shell element, hinge length, distributed "
    "plasticity, shear deformation, bond slip, confinement, multiaxial "
    "concrete, fracture-energy regularization or mesh objectivity, external "
    "benchmarks, production sparse/ROCm/HIP execution, full-building "
    "equilibrium, or G1 closure."
)

_STATE_HASH_DOMAIN = b"structural-analysis/stateful-rc-fiber-section-state/v1\0"
_MPA_M2_TO_KN = 1_000.0

FiberKind = Literal["steel", "concrete"]
FiberState = UniaxialPlasticityState | ConcreteDamageState
FiberResponse = UniaxialPlasticityResponse | ConcreteDamageResponse


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive(value: Any, *, name: str) -> float:
    result = _finite(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


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


def _generalized_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite two-vector") from exc
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite two-vector")
    return np.ascontiguousarray(result, dtype=np.float64)


@dataclass(frozen=True)
class StatefulSectionFiber:
    fiber_id: str
    y_m: float
    area_m2: float
    material_kind: FiberKind

    def __post_init__(self) -> None:
        normalized_id = str(self.fiber_id).strip()
        if not normalized_id:
            raise ValueError("fiber_id must be non-empty")
        object.__setattr__(self, "fiber_id", normalized_id)
        object.__setattr__(self, "y_m", _finite(self.y_m, name="y_m"))
        object.__setattr__(
            self,
            "area_m2",
            _positive(self.area_m2, name="area_m2"),
        )
        if self.material_kind not in ("steel", "concrete"):
            raise ValueError("material_kind must be steel or concrete")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StatefulFiberSectionState:
    section_id: str
    section_contract_hash: str
    step_index: int
    axial_strain: float
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
            _sha256_contract_hash(
                self.section_contract_hash,
                name="section_contract_hash",
            ),
        )
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        object.__setattr__(
            self,
            "axial_strain",
            _finite(self.axial_strain, name="axial_strain"),
        )
        object.__setattr__(
            self,
            "curvature_z_per_m",
            _finite(self.curvature_z_per_m, name="curvature_z_per_m"),
        )
        if not isinstance(self.fiber_states, tuple) or not self.fiber_states:
            raise ValueError("fiber_states must be a non-empty tuple")
        if not all(
            type(state) in (UniaxialPlasticityState, ConcreteDamageState)
            for state in self.fiber_states
        ):
            raise ValueError("fiber_states contains an unsupported state type")

    def canonical_bytes(self) -> bytes:
        section_id = self.section_id.encode("utf-8")
        section_contract_hash = self.section_contract_hash.encode("ascii")
        chunks = [
            _STATE_HASH_DOMAIN,
            struct.pack("<Q", len(section_id)),
            section_id,
            struct.pack("<Q", len(section_contract_hash)),
            section_contract_hash,
            struct.pack(
                "<Q2dQ",
                self.step_index,
                self.axial_strain,
                self.curvature_z_per_m,
                len(self.fiber_states),
            ),
        ]
        for state in self.fiber_states:
            tag = b"steel" if type(state) is UniaxialPlasticityState else b"concrete"
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
            "schema_version": FIBER_SECTION_STATE_SCHEMA_VERSION,
            "section_id": self.section_id,
            "section_contract_hash": self.section_contract_hash,
            "step_index": self.step_index,
            "axial_strain": self.axial_strain,
            "curvature_z_per_m": self.curvature_z_per_m,
            "fiber_states": [state.to_dict() for state in self.fiber_states],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulFiberSectionResponse:
    parent_state_hash: str
    axial_strain: float
    curvature_z_per_m: float
    axial_force_kn: float
    moment_z_kn_m: float
    consistent_tangent: np.ndarray
    fiber_strains: np.ndarray
    fiber_stresses_mpa: np.ndarray
    fiber_responses: tuple[FiberResponse, ...]
    yielded_steel_fiber_count: int
    damaged_concrete_fiber_count: int
    dissipated_energy_mj_per_m: float
    state: StatefulFiberSectionState

    @property
    def resultants(self) -> np.ndarray:
        result = np.asarray(
            [self.axial_force_kn, self.moment_z_kn_m],
            dtype=np.float64,
        )
        result.setflags(write=False)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_state_hash": self.parent_state_hash,
            "generalized_strain": {
                "axial_strain": self.axial_strain,
                "curvature_z_per_m": self.curvature_z_per_m,
            },
            "resultants": {
                "axial_force_kn": self.axial_force_kn,
                "moment_z_kn_m": self.moment_z_kn_m,
            },
            "strain_relation": FIBER_SECTION_STRAIN_RELATION,
            "resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
            "tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
            "consistent_tangent": self.consistent_tangent.tolist(),
            "fiber_strains": self.fiber_strains.tolist(),
            "fiber_stresses_mpa": self.fiber_stresses_mpa.tolist(),
            "fiber_responses": [row.to_dict() for row in self.fiber_responses],
            "yielded_steel_fiber_count": self.yielded_steel_fiber_count,
            "damaged_concrete_fiber_count": self.damaged_concrete_fiber_count,
            "dissipated_energy_mj_per_m": self.dissipated_energy_mj_per_m,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class StatefulRCFiberSection:
    fibers: tuple[StatefulSectionFiber, ...]
    steel: BilinearCombinedHardeningSteel = field(
        default_factory=BilinearCombinedHardeningSteel
    )
    concrete: AsymmetricConcreteDamageMaterial = field(
        default_factory=AsymmetricConcreteDamageMaterial
    )
    section_id: str = "rectangular_rc_stateful_fiber_section"

    def __post_init__(self) -> None:
        normalized_id = str(self.section_id).strip()
        if not normalized_id:
            raise ValueError("section_id must be non-empty")
        object.__setattr__(self, "section_id", normalized_id)
        if not isinstance(self.fibers, tuple) or not self.fibers:
            raise ValueError("fibers must be a non-empty tuple")
        ids = [fiber.fiber_id for fiber in self.fibers]
        if len(ids) != len(set(ids)):
            raise ValueError("fiber_id values must be unique")
        kinds = {fiber.material_kind for fiber in self.fibers}
        if kinds != {"steel", "concrete"}:
            raise ValueError("section must contain steel and concrete fibers")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            {
                "schema_version": STATEFUL_FIBER_SECTION_SCHEMA_VERSION,
                "section_id": self.section_id,
                "strain_relation": FIBER_SECTION_STRAIN_RELATION,
                "resultant_definition": FIBER_SECTION_RESULTANT_DEFINITION,
                "tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
                "fibers": [fiber.to_dict() for fiber in self.fibers],
                "steel": asdict(self.steel),
                "concrete": asdict(self.concrete),
            }
        )

    def initial_state(self) -> StatefulFiberSectionState:
        return StatefulFiberSectionState(
            section_id=self.section_id,
            section_contract_hash=self.contract_hash,
            step_index=0,
            axial_strain=0.0,
            curvature_z_per_m=0.0,
            fiber_states=tuple(
                self.steel.initial_state()
                if fiber.material_kind == "steel"
                else self.concrete.initial_state()
                for fiber in self.fibers
            ),
        )

    def validate_state(self, state: StatefulFiberSectionState) -> None:
        if type(state) is not StatefulFiberSectionState:
            raise ValueError("state type is invalid")
        if state.section_id != self.section_id:
            raise ValueError("state section_id does not match section")
        if state.section_contract_hash != self.contract_hash:
            raise ValueError("state section_contract_hash does not match section")
        if len(state.fiber_states) != len(self.fibers):
            raise ValueError("state fiber count does not match section")
        for fiber, fiber_state in zip(
            self.fibers,
            state.fiber_states,
            strict=True,
        ):
            expected = (
                UniaxialPlasticityState
                if fiber.material_kind == "steel"
                else ConcreteDamageState
            )
            if type(fiber_state) is not expected:
                raise ValueError("state fiber material type does not match section")

    def dissipated_energy_mj_per_m(
        self,
        state: StatefulFiberSectionState,
    ) -> float:
        self.validate_state(state)
        return math.fsum(
            fiber.area_m2 * float(fiber_state.dissipated_energy_density_mj_per_m3)
            for fiber, fiber_state in zip(
                self.fibers,
                state.fiber_states,
                strict=True,
            )
        )

    def integrate(
        self,
        generalized_strain: Any,
        committed_state: StatefulFiberSectionState,
    ) -> StatefulFiberSectionResponse:
        self.validate_state(committed_state)
        generalized = _generalized_vector(
            generalized_strain,
            name="generalized_strain",
        )
        axial_strain = float(generalized[0])
        curvature = float(generalized[1])
        fiber_strains: list[float] = []
        fiber_stresses: list[float] = []
        responses: list[FiberResponse] = []
        next_states: list[FiberState] = []
        axial_force = 0.0
        moment = 0.0
        tangent = np.zeros((2, 2), dtype=np.float64)
        yielded_count = 0
        damaged_count = 0

        for fiber, parent in zip(
            self.fibers,
            committed_state.fiber_states,
            strict=True,
        ):
            strain = axial_strain - curvature * fiber.y_m
            if fiber.material_kind == "steel":
                assert type(parent) is UniaxialPlasticityState
                response: FiberResponse = self.steel.integrate(strain, parent)
                yielded_count += int(response.yielded)
            else:
                assert type(parent) is ConcreteDamageState
                response = self.concrete.integrate(strain, parent)
                damaged_count += int(response.damage_evolved)
            stress = float(response.stress_mpa)
            algorithmic_tangent = float(response.consistent_tangent_mpa)
            force = stress * fiber.area_m2 * _MPA_M2_TO_KN
            stiffness = algorithmic_tangent * fiber.area_m2 * _MPA_M2_TO_KN
            axial_force += force
            moment -= force * fiber.y_m
            tangent[0, 0] += stiffness
            tangent[0, 1] -= stiffness * fiber.y_m
            tangent[1, 0] -= stiffness * fiber.y_m
            tangent[1, 1] += stiffness * fiber.y_m**2
            fiber_strains.append(strain)
            fiber_stresses.append(stress)
            responses.append(response)
            next_states.append(response.state)

        strain_array = np.asarray(fiber_strains, dtype=np.float64)
        stress_array = np.asarray(fiber_stresses, dtype=np.float64)
        for array in (tangent, strain_array, stress_array):
            array.setflags(write=False)
        next_state = StatefulFiberSectionState(
            section_id=self.section_id,
            section_contract_hash=self.contract_hash,
            step_index=committed_state.step_index + 1,
            axial_strain=axial_strain,
            curvature_z_per_m=curvature,
            fiber_states=tuple(next_states),
        )
        return StatefulFiberSectionResponse(
            parent_state_hash=committed_state.state_hash,
            axial_strain=axial_strain,
            curvature_z_per_m=curvature,
            axial_force_kn=float(axial_force),
            moment_z_kn_m=float(moment),
            consistent_tangent=tangent,
            fiber_strains=strain_array,
            fiber_stresses_mpa=stress_array,
            fiber_responses=tuple(responses),
            yielded_steel_fiber_count=yielded_count,
            damaged_concrete_fiber_count=damaged_count,
            dissipated_energy_mj_per_m=self.dissipated_energy_mj_per_m(next_state),
            state=next_state,
        )


def make_rectangular_stateful_rc_fiber_section(
    *,
    width_m: float = 0.4,
    depth_m: float = 0.6,
    cover_m: float = 0.05,
    concrete_layer_count: int = 12,
    top_bar_count: int = 4,
    bottom_bar_count: int = 4,
    bar_area_m2: float = 3.87e-4,
    section_id: str = "rectangular_rc_stateful_fiber_section",
    steel: BilinearCombinedHardeningSteel | None = None,
    concrete: AsymmetricConcreteDamageMaterial | None = None,
) -> StatefulRCFiberSection:
    width = _positive(width_m, name="width_m")
    depth = _positive(depth_m, name="depth_m")
    cover = _positive(cover_m, name="cover_m")
    if cover >= 0.5 * depth:
        raise ValueError("cover_m must be less than half the section depth")
    if type(concrete_layer_count) is not int or concrete_layer_count < 2:
        raise ValueError("concrete_layer_count must be an integer of at least 2")
    for name, count in (
        ("top_bar_count", top_bar_count),
        ("bottom_bar_count", bottom_bar_count),
    ):
        if type(count) is not int or count < 1:
            raise ValueError(f"{name} must be a positive integer")
    bar_area = _positive(bar_area_m2, name="bar_area_m2")
    layer_depth = depth / concrete_layer_count
    fibers = [
        StatefulSectionFiber(
            fiber_id=f"concrete-{index:02d}",
            y_m=-0.5 * depth + (index + 0.5) * layer_depth,
            area_m2=width * layer_depth,
            material_kind="concrete",
        )
        for index in range(concrete_layer_count)
    ]
    fibers.extend(
        (
            StatefulSectionFiber(
                fiber_id="steel-bottom-layer",
                y_m=-0.5 * depth + cover,
                area_m2=bottom_bar_count * bar_area,
                material_kind="steel",
            ),
            StatefulSectionFiber(
                fiber_id="steel-top-layer",
                y_m=0.5 * depth - cover,
                area_m2=top_bar_count * bar_area,
                material_kind="steel",
            ),
        )
    )
    return StatefulRCFiberSection(
        fibers=tuple(fibers),
        steel=steel or BilinearCombinedHardeningSteel(),
        concrete=concrete or AsymmetricConcreteDamageMaterial(),
        section_id=section_id,
    )


def finite_difference_stateful_fiber_section_tangent_check(
    section: StatefulRCFiberSection,
    committed_state: StatefulFiberSectionState,
    *,
    generalized_strain: Any = (-3.0e-4, 6.0e-3),
    axial_epsilon: float = 1.0e-9,
    curvature_epsilon_per_m: float = 1.0e-8,
    relative_tolerance: float = 2.0e-6,
) -> dict[str, Any]:
    generalized = _generalized_vector(
        generalized_strain,
        name="generalized_strain",
    )
    steps = np.asarray(
        [
            _positive(axial_epsilon, name="axial_epsilon"),
            _positive(
                curvature_epsilon_per_m,
                name="curvature_epsilon_per_m",
            ),
        ],
        dtype=np.float64,
    )
    tolerance = _positive(relative_tolerance, name="relative_tolerance")
    parent_bytes = committed_state.canonical_bytes()
    center = section.integrate(generalized, committed_state)
    finite_difference = np.empty((2, 2), dtype=np.float64)
    parent_hashes = [center.parent_state_hash]
    for column in range(2):
        direction = np.zeros(2, dtype=np.float64)
        direction[column] = steps[column]
        forward = section.integrate(generalized + direction, committed_state)
        backward = section.integrate(generalized - direction, committed_state)
        finite_difference[:, column] = (forward.resultants - backward.resultants) / (
            2.0 * steps[column]
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
    symmetry_error = float(
        np.linalg.norm(
            center.consistent_tangent - center.consistent_tangent.T,
            ord=np.inf,
        )
    )
    return {
        "generalized_strain": generalized.tolist(),
        "analytic_consistent_tangent": center.consistent_tangent.tolist(),
        "finite_difference_tangent": finite_difference.tolist(),
        "tangent_symmetry_error": symmetry_error,
        "absolute_inf_error": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(
            relative_error <= tolerance and symmetry_error <= 1.0e-12 and same_parent
        ),
    }


def integrate_stateful_fiber_section_history(
    section: StatefulRCFiberSection,
    generalized_strain_path: Iterable[tuple[float, float]],
    *,
    initial_state: StatefulFiberSectionState | None = None,
) -> dict[str, Any]:
    path = tuple(
        tuple(
            float(value)
            for value in _generalized_vector(row, name="generalized_strain_path row")
        )
        for row in generalized_strain_path
    )
    if not path:
        raise ValueError("generalized_strain_path must be non-empty")
    state = initial_state or section.initial_state()
    section.validate_state(state)
    previous_curvature = state.curvature_z_per_m
    previous_sign = 0
    reversal_count = 0
    rows: list[dict[str, Any]] = []
    energy_values = [section.dissipated_energy_mj_per_m(state)]
    for step_index, target in enumerate(path, start=1):
        parent = state
        response = section.integrate(target, parent)
        increment = target[1] - previous_curvature
        sign = 1 if increment > 0.0 else -1 if increment < 0.0 else 0
        if sign != 0 and previous_sign != 0 and sign != previous_sign:
            reversal_count += 1
        if sign != 0:
            previous_sign = sign
        state = response.state
        energy_values.append(response.dissipated_energy_mj_per_m)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "accepted_state_hash": state.state_hash,
                "curvature_increment_sign": sign,
                **response.to_dict(),
            }
        )
        previous_curvature = target[1]
    energy_monotonic = all(
        following + 1.0e-15 >= current
        for current, following in zip(energy_values, energy_values[1:])
    )
    return {
        "section_contract_hash": section.contract_hash,
        "step_count": len(rows),
        "curvature_reversal_count": reversal_count,
        "yielded_step_count": sum(
            int(row["yielded_steel_fiber_count"] > 0) for row in rows
        ),
        "concrete_damage_step_count": sum(
            int(row["damaged_concrete_fiber_count"] > 0) for row in rows
        ),
        "dissipated_energy_nonnegative_monotonic": energy_monotonic,
        "final_dissipated_energy_mj_per_m": energy_values[-1],
        "final_state": state.to_dict(),
        "history": rows,
    }


@dataclass(frozen=True)
class FiberSectionNewtonConfig:
    axial_force_scale_kn: float = 1_000.0
    moment_scale_kn_m: float = 100.0
    axial_strain_scale: float = 1.0e-3
    curvature_scale_per_m: float = 1.0e-2
    residual_tolerance: float = 1.0e-10
    increment_tolerance: float = 1.0e-10
    maximum_iterations: int = 20
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
            "axial_force_scale_kn",
            "moment_scale_kn_m",
            "axial_strain_scale",
            "curvature_scale_per_m",
            "residual_tolerance",
            "increment_tolerance",
        ):
            object.__setattr__(
                self,
                name,
                _positive(getattr(self, name), name=name),
            )
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 0:
            raise ValueError("maximum_iterations must be a non-negative integer")
        if not self.line_search_alphas:
            raise ValueError("line_search_alphas must be non-empty")
        previous = math.inf
        normalized: list[float] = []
        for value in self.line_search_alphas:
            alpha = _positive(value, name="line_search_alpha")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized.append(alpha)
            previous = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized))


@dataclass(frozen=True)
class FiberSectionNewtonResult:
    status: str
    terminal_reason: str
    target_resultants: tuple[float, float]
    parent_state: StatefulFiberSectionState
    accepted_state: StatefulFiberSectionState
    solution_generalized_strain: tuple[float, float]
    convergence_history: tuple[dict[str, Any], ...]
    line_search_history: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    @property
    def committed(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FIBER_SECTION_NEWTON_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "target_resultants": {
                "axial_force_kn": self.target_resultants[0],
                "moment_z_kn_m": self.target_resultants[1],
            },
            "parent_state_hash": self.parent_state.state_hash,
            "accepted_state": self.accepted_state.to_dict(),
            "solution_generalized_strain": {
                "axial_strain": self.solution_generalized_strain[0],
                "curvature_z_per_m": self.solution_generalized_strain[1],
            },
            "committed": self.committed,
            "convergence_history": list(self.convergence_history),
            "line_search_history": list(self.line_search_history),
            "metrics": dict(self.metrics),
        }


def _scaled_residual_norm(
    residual: np.ndarray,
    config: FiberSectionNewtonConfig,
) -> float:
    return float(
        np.linalg.norm(
            residual
            / np.asarray(
                [config.axial_force_scale_kn, config.moment_scale_kn_m],
                dtype=np.float64,
            ),
            ord=np.inf,
        )
    )


def _scaled_increment_norm(
    increment: np.ndarray,
    config: FiberSectionNewtonConfig,
) -> float:
    return float(
        np.linalg.norm(
            increment
            / np.asarray(
                [config.axial_strain_scale, config.curvature_scale_per_m],
                dtype=np.float64,
            ),
            ord=np.inf,
        )
    )


def solve_stateful_fiber_section_resultants(
    section: StatefulRCFiberSection,
    committed_state: StatefulFiberSectionState,
    *,
    target_resultants: Any,
    initial_generalized_strain: Any | None = None,
    config: FiberSectionNewtonConfig | None = None,
) -> FiberSectionNewtonResult:
    """Solve one section-resultant target and atomically commit or roll back."""

    section.validate_state(committed_state)
    cfg = config or FiberSectionNewtonConfig()
    target = _generalized_vector(target_resultants, name="target_resultants")
    generalized = _generalized_vector(
        (
            (
                committed_state.axial_strain,
                committed_state.curvature_z_per_m,
            )
            if initial_generalized_strain is None
            else initial_generalized_strain
        ),
        name="initial_generalized_strain",
    )
    parent_bytes = committed_state.canonical_bytes()
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    terminal_reason = "maximum_iterations_exhausted"
    accepted_response: StatefulFiberSectionResponse | None = None

    for iteration in range(cfg.maximum_iterations + 1):
        response = section.integrate(generalized, committed_state)
        residual = response.resultants - target
        residual_norm = _scaled_residual_norm(residual, cfg)
        try:
            newton_increment = np.linalg.solve(
                response.consistent_tangent,
                -residual,
            )
        except np.linalg.LinAlgError:
            terminal_reason = "singular_consistent_section_tangent"
            break
        increment_norm = _scaled_increment_norm(newton_increment, cfg)
        residual_gate = residual_norm <= cfg.residual_tolerance
        increment_gate = increment_norm <= cfg.increment_tolerance
        row: dict[str, Any] = {
            "iteration": iteration,
            "generalized_strain": generalized.tolist(),
            "resultants": response.resultants.tolist(),
            "residual": residual.tolist(),
            "scaled_residual_inf_norm": residual_norm,
            "newton_increment": newton_increment.tolist(),
            "scaled_increment_inf_norm": increment_norm,
            "residual_gate_passed": residual_gate,
            "increment_gate_passed": increment_gate,
        }
        if residual_gate and increment_gate:
            row.update(
                {
                    "selected_line_search_alpha": 1.0,
                    "line_search_attempt_count": 0,
                    "accepted": True,
                }
            )
            history.append(row)
            accepted_response = response
            terminal_reason = "residual_and_increment_converged"
            break

        attempts: list[dict[str, Any]] = []
        selected_alpha = 0.0
        selected_generalized = generalized
        for alpha in cfg.line_search_alphas:
            trial_generalized = generalized + alpha * newton_increment
            trial_response = section.integrate(
                trial_generalized,
                committed_state,
            )
            trial_residual = trial_response.resultants - target
            trial_norm = _scaled_residual_norm(trial_residual, cfg)
            accepted = trial_norm < residual_norm
            attempts.append(
                {
                    "alpha": alpha,
                    "trial_generalized_strain": trial_generalized.tolist(),
                    "trial_residual": trial_residual.tolist(),
                    "trial_scaled_residual_inf_norm": trial_norm,
                    "accepted": accepted,
                }
            )
            if accepted:
                selected_alpha = alpha
                selected_generalized = trial_generalized
                break
        line_search_history.append(
            {
                "iteration": iteration,
                "selected_alpha": selected_alpha,
                "attempts": attempts,
            }
        )
        row.update(
            {
                "selected_line_search_alpha": selected_alpha,
                "line_search_attempt_count": len(attempts),
                "accepted": selected_alpha > 0.0,
            }
        )
        history.append(row)
        if selected_alpha == 0.0:
            terminal_reason = "line_search_failed_to_reduce_residual"
            break
        generalized = np.ascontiguousarray(
            selected_generalized,
            dtype=np.float64,
        )
        if iteration == cfg.maximum_iterations:
            terminal_reason = "maximum_iterations_exhausted"
            break

    parent_unchanged = bool(
        committed_state.canonical_bytes() == parent_bytes
        and section.validate_state(committed_state) is None
    )
    if accepted_response is None:
        accepted_state = committed_state
        status = "blocked"
        final_response = section.integrate(generalized, committed_state)
        final_residual = final_response.resultants - target
        rollback_exact = bool(
            accepted_state is committed_state
            and accepted_state.canonical_bytes() == parent_bytes
            and parent_unchanged
        )
    else:
        accepted_state = accepted_response.state
        status = "ready"
        final_response = accepted_response
        final_residual = final_response.resultants - target
        rollback_exact = True
    final_scaled_residual = _scaled_residual_norm(final_residual, cfg)
    solver_contract_pass = bool(
        status == "ready"
        and final_scaled_residual <= cfg.residual_tolerance
        and parent_unchanged
        and rollback_exact
    )
    metrics = {
        "contract_pass": solver_contract_pass,
        "residual_formula": "section_resultants-target_resultants",
        "tangent_definition": FIBER_SECTION_TANGENT_DEFINITION,
        "final_scaled_residual_inf_norm": final_scaled_residual,
        "final_residual": final_residual.tolist(),
        "iteration_count": len(history),
        "linear_solve_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["selected_alpha"] < 1.0
            for row in line_search_history
            if row["selected_alpha"] > 0.0
        ),
        "parent_state_immutable": parent_unchanged,
        "rollback_exact": rollback_exact,
        "fallback_count": 0,
        "regularization_count": 0,
        "section_contract_hash": section.contract_hash,
    }
    return FiberSectionNewtonResult(
        status=status,
        terminal_reason=terminal_reason,
        target_resultants=(float(target[0]), float(target[1])),
        parent_state=committed_state,
        accepted_state=accepted_state,
        solution_generalized_strain=(
            float(generalized[0]),
            float(generalized[1]),
        ),
        convergence_history=tuple(history),
        line_search_history=tuple(line_search_history),
        metrics=metrics,
    )


def _manufactured_newton_path(
    section: StatefulRCFiberSection,
    target_generalized_strains: tuple[tuple[float, float], ...],
) -> dict[str, Any]:
    state = section.initial_state()
    rows: list[dict[str, Any]] = []
    maximum_truth_error = 0.0
    for step_index, target_generalized in enumerate(
        target_generalized_strains,
        start=1,
    ):
        truth = section.integrate(target_generalized, state)
        result = solve_stateful_fiber_section_resultants(
            section,
            state,
            target_resultants=truth.resultants,
        )
        error = float(
            np.linalg.norm(
                np.asarray(result.solution_generalized_strain)
                - np.asarray(target_generalized),
                ord=np.inf,
            )
        )
        maximum_truth_error = max(maximum_truth_error, error)
        rows.append(
            {
                "step_index": step_index,
                "manufactured_target_generalized_strain": list(target_generalized),
                "manufactured_target_resultants": truth.resultants.tolist(),
                "solution_error_inf_norm": error,
                "newton_result": result.to_dict(),
            }
        )
        if not result.committed:
            break
        state = result.accepted_state
    return {
        "status": (
            "ready"
            if len(rows) == len(target_generalized_strains)
            and all(row["newton_result"]["committed"] for row in rows)
            else "blocked"
        ),
        "step_count": len(rows),
        "maximum_solution_error_inf_norm": maximum_truth_error,
        "final_state": state.to_dict(),
        "steps": rows,
    }


def _quadratic_convergence_evidence(
    newton_step: dict[str, Any],
    *,
    local_residual_ceiling: float = 1.0e-1,
    minimum_observed_order: float = 1.8,
) -> dict[str, Any]:
    residuals = [
        float(row["scaled_residual_inf_norm"])
        for row in newton_step["newton_result"]["convergence_history"]
        if 0.0 < float(row["scaled_residual_inf_norm"]) <= local_residual_ceiling
    ]
    observed_orders: list[float] = []
    for previous, current, following in zip(
        residuals,
        residuals[1:],
        residuals[2:],
        strict=False,
    ):
        denominator = math.log(current / previous)
        if previous > current > following > 0.0 and denominator != 0.0:
            observed_orders.append(math.log(following / current) / denominator)
    return {
        "source_step_index": newton_step["step_index"],
        "local_residual_ceiling": local_residual_ceiling,
        "local_scaled_residual_inf_norms": residuals,
        "observed_orders": observed_orders,
        "minimum_observed_order_required": minimum_observed_order,
        "pass": bool(
            len(observed_orders) >= 2
            and min(observed_orders[-2:]) >= minimum_observed_order
        ),
    }


@lru_cache(maxsize=1)
def _build_stateful_rc_fiber_section_benchmark_cached() -> dict[str, Any]:
    section = make_rectangular_stateful_rc_fiber_section()
    tangent = finite_difference_stateful_fiber_section_tangent_check(
        section,
        section.initial_state(),
    )
    cyclic_path = (
        (-2.0e-4, 0.0),
        (-2.0e-4, 4.0e-3),
        (-2.0e-4, 9.0e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, -5.0e-3),
        (-2.0e-4, -9.0e-3),
        (-2.0e-4, 0.0),
    )
    cyclic = integrate_stateful_fiber_section_history(section, cyclic_path)
    manufactured_targets = (
        (-5.0e-5, 0.0),
        (-1.0e-4, 1.5e-3),
        (-1.5e-4, 3.0e-3),
        (-2.0e-4, 4.5e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, 0.0),
    )
    first = _manufactured_newton_path(section, manufactured_targets)
    repeated = _manufactured_newton_path(section, manufactured_targets)
    quadratic = _quadratic_convergence_evidence(
        max(
            first["steps"],
            key=lambda row: len(row["newton_result"]["convergence_history"]),
        )
    )
    damped_parent = section.initial_state()
    damped_target_generalized = (-1.0e-4, 1.5e-3)
    damped_truth = section.integrate(
        damped_target_generalized,
        damped_parent,
    )
    damped_initial_generalized = (1.0e-3, -2.0e-2)
    damped_result = solve_stateful_fiber_section_resultants(
        section,
        damped_parent,
        target_resultants=damped_truth.resultants,
        initial_generalized_strain=damped_initial_generalized,
    )
    damped_solution_error = float(
        np.linalg.norm(
            np.asarray(damped_result.solution_generalized_strain)
            - np.asarray(damped_target_generalized),
            ord=np.inf,
        )
    )
    selected_alphas = [
        float(row["selected_alpha"])
        for row in damped_result.line_search_history
        if float(row["selected_alpha"]) > 0.0
    ]
    damped_line_search_gate = bool(
        damped_result.committed
        and damped_solution_error <= 1.0e-10
        and damped_result.metrics["line_search_used"] is True
        and selected_alphas
        and min(selected_alphas) < 1.0
        and damped_result.metrics["parent_state_immutable"] is True
        and damped_result.metrics["fallback_count"] == 0
        and damped_result.metrics["regularization_count"] == 0
    )
    rollback_parent = section.initial_state()
    rollback_truth = section.integrate((-2.0e-4, 6.0e-3), rollback_parent)
    forced_failure = solve_stateful_fiber_section_resultants(
        section,
        rollback_parent,
        target_resultants=rollback_truth.resultants,
        config=FiberSectionNewtonConfig(maximum_iterations=0),
    )
    nonlinear_response = section.integrate(
        (-3.0e-4, 6.0e-3),
        section.initial_state(),
    )
    off_diagonal = abs(float(nonlinear_response.consistent_tangent[0, 1]))
    deterministic_replay_exact = first == repeated
    newton_gate = bool(
        first["status"] == "ready"
        and first["step_count"] == len(manufactured_targets)
        and first["maximum_solution_error_inf_norm"] <= 1.0e-10
        and all(
            row["newton_result"]["metrics"]["fallback_count"] == 0
            and row["newton_result"]["metrics"]["regularization_count"] == 0
            and row["newton_result"]["metrics"]["parent_state_immutable"] is True
            for row in first["steps"]
        )
    )
    rollback_gate = bool(
        forced_failure.status == "blocked"
        and forced_failure.accepted_state is rollback_parent
        and forced_failure.accepted_state.canonical_bytes()
        == rollback_parent.canonical_bytes()
        and forced_failure.metrics["rollback_exact"] is True
    )
    cyclic_gate = bool(
        cyclic["curvature_reversal_count"] >= 2
        and cyclic["yielded_step_count"] > 0
        and cyclic["concrete_damage_step_count"] > 0
        and cyclic["dissipated_energy_nonnegative_monotonic"] is True
        and cyclic["final_dissipated_energy_mj_per_m"] > 0.0
    )
    interaction_gate = bool(
        off_diagonal > 0.0
        and nonlinear_response.yielded_steel_fiber_count > 0
        and nonlinear_response.damaged_concrete_fiber_count > 0
    )
    contract_pass = bool(
        tangent["pass"] is True
        and tangent["tangent_symmetry_error"] <= 1.0e-12
        and cyclic_gate
        and newton_gate
        and quadratic["pass"] is True
        and damped_line_search_gate
        and rollback_gate
        and deterministic_replay_exact
        and interaction_gate
    )
    return {
        "schema_version": STATEFUL_FIBER_SECTION_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": section.section_id,
        "analysis_type": "stateful_rc_fiber_section_axial_curvature_newton",
        "section_contract_hash": section.contract_hash,
        "fiber_count": len(section.fibers),
        "steel_fiber_count": sum(
            int(fiber.material_kind == "steel") for fiber in section.fibers
        ),
        "concrete_fiber_count": sum(
            int(fiber.material_kind == "concrete") for fiber in section.fibers
        ),
        "tangent_finite_difference": tangent,
        "cyclic_history": cyclic,
        "manufactured_newton_path": first,
        "quadratic_convergence": quadratic,
        "damped_line_search": {
            "manufactured_target_generalized_strain": list(damped_target_generalized),
            "initial_generalized_strain": list(damped_initial_generalized),
            "solution_error_inf_norm": damped_solution_error,
            "minimum_selected_alpha": min(selected_alphas, default=0.0),
            "newton_result": damped_result.to_dict(),
            "gate_passed": damped_line_search_gate,
        },
        "forced_failure_rollback": forced_failure.to_dict(),
        "verification": {
            "consistent_tangent_finite_difference_passed": tangent["pass"],
            "consistent_tangent_relative_inf_error": tangent["relative_inf_error"],
            "tangent_symmetry_error": tangent["tangent_symmetry_error"],
            "axial_curvature_coupling_active": interaction_gate,
            "nonlinear_tangent_off_diagonal_abs": off_diagonal,
            "cyclic_state_and_energy_gate_passed": cyclic_gate,
            "manufactured_newton_path_gate_passed": newton_gate,
            "quadratic_convergence_gate_passed": quadratic["pass"],
            "minimum_tail_observed_convergence_order": min(
                quadratic["observed_orders"][-2:],
                default=0.0,
            ),
            "damped_line_search_gate_passed": damped_line_search_gate,
            "damped_line_search_minimum_alpha": min(
                selected_alphas,
                default=0.0,
            ),
            "damped_line_search_solution_error_inf_norm": (damped_solution_error),
            "manufactured_newton_step_count": first["step_count"],
            "maximum_manufactured_solution_error_inf_norm": first[
                "maximum_solution_error_inf_norm"
            ],
            "deterministic_replay_exact": deterministic_replay_exact,
            "forced_failure_rollback_exact": rollback_gate,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "verification_hierarchy": {
            "level_1_analytic_and_manufactured": contract_pass,
            "level_2_external_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_stateful_rc_fiber_section": contract_pass,
            "axial_curvature_interaction": interaction_gate,
            "per_fiber_path_dependent_material_state": cyclic_gate,
            "consistent_2x2_section_jacobian": tangent["pass"],
            "section_resultant_newton_commit_rollback": (
                newton_gate
                and quadratic["pass"] is True
                and damped_line_search_gate
                and rollback_gate
            ),
            "general_frame_or_shell_element": False,
            "plastic_hinge_length_or_distributed_plasticity": False,
            "shear_deformation_or_bond_slip": False,
            "confined_or_multiaxial_concrete": False,
            "fracture_energy_regularization_or_mesh_objectivity": False,
            "external_validation": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "frame_element_section_integration_not_connected",
            "plastic_hinge_length_and_distributed_plasticity_not_implemented",
            "shear_deformation_and_bond_slip_not_implemented",
            "confinement_and_multiaxial_concrete_not_implemented",
            "fracture_energy_regularization_and_mesh_objectivity_not_verified",
            "external_code_to_code_published_and_experimental_receipts_missing",
            "production_sparse_and_rocm_hip_paths_not_connected",
            "full_building_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": STATEFUL_FIBER_SECTION_CLAIM_BOUNDARY,
    }


def build_stateful_rc_fiber_section_benchmark() -> dict[str, Any]:
    """Return an isolated deterministic Level-1 section receipt."""

    return deepcopy(_build_stateful_rc_fiber_section_benchmark_cached())


__all__ = [
    "FIBER_SECTION_NEWTON_SCHEMA_VERSION",
    "FIBER_SECTION_RESULTANT_DEFINITION",
    "FIBER_SECTION_STATE_SCHEMA_VERSION",
    "FIBER_SECTION_STRAIN_RELATION",
    "FIBER_SECTION_TANGENT_DEFINITION",
    "STATEFUL_FIBER_SECTION_CLAIM_BOUNDARY",
    "STATEFUL_FIBER_SECTION_SCHEMA_VERSION",
    "FiberSectionNewtonConfig",
    "FiberSectionNewtonResult",
    "StatefulFiberSectionResponse",
    "StatefulFiberSectionState",
    "StatefulRCFiberSection",
    "StatefulSectionFiber",
    "build_stateful_rc_fiber_section_benchmark",
    "finite_difference_stateful_fiber_section_tangent_check",
    "integrate_stateful_fiber_section_history",
    "make_rectangular_stateful_rc_fiber_section",
    "solve_stateful_fiber_section_resultants",
]
