"""State-updated bilinear hysteretic link in moment-rotation units."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Iterable


ROTATIONAL_LINK_STATE_SCHEMA_VERSION = (
    "bilinear-combined-hardening-rotational-link-state.v1"
)
ROTATIONAL_LINK_RETURN_MAPPING_ALGORITHM = (
    "backward_euler_1d_rotational_link_return_mapping"
)
ROTATIONAL_LINK_TANGENT_DEFINITION = "algorithmic_consistent_d_moment_d_rotation"
_STATE_HASH_DOMAIN = b"structural-analysis/bilinear-rotational-link-state/v1\0"


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class BilinearRotationalLinkState:
    """Immutable internal variables for one scalar rotational link."""

    plastic_rotation_rad: float = 0.0
    backmoment_kn_m: float = 0.0
    accumulated_plastic_rotation_rad: float = 0.0
    dissipated_energy_kn_m: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "plastic_rotation_rad",
            "backmoment_kn_m",
            "accumulated_plastic_rotation_rad",
            "dissipated_energy_kn_m",
        ):
            _require_finite(name, getattr(self, name))
        if self.accumulated_plastic_rotation_rad < 0.0:
            raise ValueError("accumulated_plastic_rotation_rad must be non-negative")
        if self.dissipated_energy_kn_m < 0.0:
            raise ValueError("dissipated_energy_kn_m must be non-negative")

    def canonical_bytes(self) -> bytes:
        return _STATE_HASH_DOMAIN + struct.pack(
            "<4d",
            self.plastic_rotation_rad,
            self.backmoment_kn_m,
            self.accumulated_plastic_rotation_rad,
            self.dissipated_energy_kn_m,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROTATIONAL_LINK_STATE_SCHEMA_VERSION,
            "plastic_rotation_rad": self.plastic_rotation_rad,
            "backmoment_kn_m": self.backmoment_kn_m,
            "accumulated_plastic_rotation_rad": (self.accumulated_plastic_rotation_rad),
            "dissipated_energy_kn_m": self.dissipated_energy_kn_m,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class BilinearRotationalLinkResponse:
    rotation_rad: float
    moment_kn_m: float
    consistent_tangent_kn_m_per_rad: float
    yielded: bool
    plastic_multiplier_increment_rad: float
    trial_yield_function_kn_m: float
    final_yield_function_kn_m: float
    committed_state_hash: str
    state: BilinearRotationalLinkState

    def to_dict(self) -> dict[str, Any]:
        return {
            "rotation_rad": self.rotation_rad,
            "moment_kn_m": self.moment_kn_m,
            "consistent_tangent_kn_m_per_rad": (self.consistent_tangent_kn_m_per_rad),
            "yielded": self.yielded,
            "damage_evolved": False,
            "plastic_multiplier_increment_rad": (self.plastic_multiplier_increment_rad),
            "trial_yield_function_kn_m": self.trial_yield_function_kn_m,
            "final_yield_function_kn_m": self.final_yield_function_kn_m,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class BilinearCombinedHardeningRotationalLink:
    """One-dimensional bilinear return mapping in kN-m and radians."""

    initial_stiffness_kn_m_per_rad: float = 10_000.0
    yield_moment_kn_m: float = 100.0
    isotropic_hardening_kn_m_per_rad: float = 200.0
    kinematic_hardening_kn_m_per_rad: float = 300.0
    yield_tolerance_kn_m: float = 1.0e-10
    material_id: str = "bilinear_combined_hardening_rotational_link_1d"

    def __post_init__(self) -> None:
        for name in (
            "initial_stiffness_kn_m_per_rad",
            "yield_moment_kn_m",
            "isotropic_hardening_kn_m_per_rad",
            "kinematic_hardening_kn_m_per_rad",
            "yield_tolerance_kn_m",
        ):
            _require_finite(name, getattr(self, name))
        if self.initial_stiffness_kn_m_per_rad <= 0.0:
            raise ValueError("initial_stiffness_kn_m_per_rad must be positive")
        if self.yield_moment_kn_m <= 0.0:
            raise ValueError("yield_moment_kn_m must be positive")
        if self.isotropic_hardening_kn_m_per_rad < 0.0:
            raise ValueError("isotropic_hardening_kn_m_per_rad must be non-negative")
        if self.kinematic_hardening_kn_m_per_rad < 0.0:
            raise ValueError("kinematic_hardening_kn_m_per_rad must be non-negative")
        if self.yield_tolerance_kn_m < 0.0:
            raise ValueError("yield_tolerance_kn_m must be non-negative")
        normalized_id = str(self.material_id).strip()
        if not normalized_id:
            raise ValueError("material_id must be non-empty")
        object.__setattr__(self, "material_id", normalized_id)

    @property
    def hardening_stiffness_kn_m_per_rad(self) -> float:
        return (
            self.isotropic_hardening_kn_m_per_rad
            + self.kinematic_hardening_kn_m_per_rad
        )

    @property
    def plastic_consistent_tangent_kn_m_per_rad(self) -> float:
        hardening = self.hardening_stiffness_kn_m_per_rad
        return (
            self.initial_stiffness_kn_m_per_rad
            * hardening
            / (self.initial_stiffness_kn_m_per_rad + hardening)
        )

    def initial_state(self) -> BilinearRotationalLinkState:
        return BilinearRotationalLinkState()

    def integrate(
        self,
        rotation_rad: float,
        committed_state: BilinearRotationalLinkState,
    ) -> BilinearRotationalLinkResponse:
        if type(committed_state) is not BilinearRotationalLinkState:
            raise ValueError("committed_state must be a BilinearRotationalLinkState")
        rotation = _require_finite("rotation_rad", rotation_rad)
        elastic_trial = rotation - committed_state.plastic_rotation_rad
        trial_moment = self.initial_stiffness_kn_m_per_rad * elastic_trial
        relative_trial = trial_moment - committed_state.backmoment_kn_m
        yield_radius = self.yield_moment_kn_m + (
            self.isotropic_hardening_kn_m_per_rad
            * committed_state.accumulated_plastic_rotation_rad
        )
        trial_yield = abs(relative_trial) - yield_radius
        if trial_yield <= self.yield_tolerance_kn_m:
            moment = trial_moment
            tangent = self.initial_stiffness_kn_m_per_rad
            plastic_increment = 0.0
            next_state = committed_state
            yielded = False
        else:
            flow_direction = 1.0 if relative_trial >= 0.0 else -1.0
            denominator = (
                self.initial_stiffness_kn_m_per_rad
                + self.hardening_stiffness_kn_m_per_rad
            )
            plastic_increment = trial_yield / denominator
            next_state = BilinearRotationalLinkState(
                plastic_rotation_rad=(
                    committed_state.plastic_rotation_rad
                    + plastic_increment * flow_direction
                ),
                backmoment_kn_m=(
                    committed_state.backmoment_kn_m
                    + self.kinematic_hardening_kn_m_per_rad
                    * plastic_increment
                    * flow_direction
                ),
                accumulated_plastic_rotation_rad=(
                    committed_state.accumulated_plastic_rotation_rad + plastic_increment
                ),
                dissipated_energy_kn_m=(
                    committed_state.dissipated_energy_kn_m
                    + self.yield_moment_kn_m * plastic_increment
                ),
            )
            moment = trial_moment - (
                self.initial_stiffness_kn_m_per_rad * plastic_increment * flow_direction
            )
            tangent = self.plastic_consistent_tangent_kn_m_per_rad
            yielded = True
        final_yield = abs(moment - next_state.backmoment_kn_m) - (
            self.yield_moment_kn_m
            + self.isotropic_hardening_kn_m_per_rad
            * next_state.accumulated_plastic_rotation_rad
        )
        return BilinearRotationalLinkResponse(
            rotation_rad=rotation,
            moment_kn_m=moment,
            consistent_tangent_kn_m_per_rad=tangent,
            yielded=yielded,
            plastic_multiplier_increment_rad=plastic_increment,
            trial_yield_function_kn_m=trial_yield,
            final_yield_function_kn_m=final_yield,
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


def finite_difference_rotational_link_tangent_check(
    material: BilinearCombinedHardeningRotationalLink,
    committed_state: BilinearRotationalLinkState,
    *,
    rotation_rad: float,
    epsilon_rad: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    if epsilon_rad <= 0.0 or not math.isfinite(epsilon_rad):
        raise ValueError("epsilon_rad must be finite and positive")
    tolerance = _require_finite("relative_tolerance", relative_tolerance)
    if tolerance <= 0.0:
        raise ValueError("relative_tolerance must be positive")
    center = material.integrate(rotation_rad, committed_state)
    forward = material.integrate(rotation_rad + epsilon_rad, committed_state)
    backward = material.integrate(rotation_rad - epsilon_rad, committed_state)
    finite_difference = (forward.moment_kn_m - backward.moment_kn_m) / (
        2.0 * epsilon_rad
    )
    absolute_error = abs(finite_difference - center.consistent_tangent_kn_m_per_rad)
    scale = max(
        abs(finite_difference),
        abs(center.consistent_tangent_kn_m_per_rad),
        1.0,
    )
    relative_error = absolute_error / scale
    same_parent = bool(
        forward.committed_state_hash
        == center.committed_state_hash
        == backward.committed_state_hash
    )
    return {
        "return_mapping_algorithm": ROTATIONAL_LINK_RETURN_MAPPING_ALGORITHM,
        "tangent_definition": ROTATIONAL_LINK_TANGENT_DEFINITION,
        "rotation_rad": float(rotation_rad),
        "finite_difference_epsilon_rad": epsilon_rad,
        "analytic_consistent_tangent_kn_m_per_rad": (
            center.consistent_tangent_kn_m_per_rad
        ),
        "finite_difference_tangent_kn_m_per_rad": finite_difference,
        "absolute_error_kn_m_per_rad": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(relative_error <= tolerance and same_parent),
    }


def integrate_rotational_link_history(
    material: BilinearCombinedHardeningRotationalLink,
    rotations_rad: Iterable[float],
    *,
    initial_state: BilinearRotationalLinkState | None = None,
) -> dict[str, Any]:
    path = tuple(float(value) for value in rotations_rad)
    if not path or not all(math.isfinite(value) for value in path):
        raise ValueError("rotations_rad must contain finite values")
    state = initial_state or material.initial_state()
    previous_rotation = 0.0
    previous_moment = material.integrate(0.0, state).moment_kn_m
    previous_flow_direction = 0
    reversal_count = 0
    work_kn_m = 0.0
    dissipation_values = [state.dissipated_energy_kn_m]
    rows: list[dict[str, Any]] = []

    for step_index, rotation in enumerate(path, start=1):
        parent = state
        response = material.integrate(rotation, parent)
        work_kn_m += (
            0.5
            * (previous_moment + response.moment_kn_m)
            * (rotation - previous_rotation)
        )
        plastic_increment = (
            response.state.plastic_rotation_rad - parent.plastic_rotation_rad
        )
        flow_direction = (
            1 if plastic_increment > 0.0 else -1 if plastic_increment < 0.0 else 0
        )
        if (
            flow_direction != 0
            and previous_flow_direction != 0
            and flow_direction != previous_flow_direction
        ):
            reversal_count += 1
        if flow_direction != 0:
            previous_flow_direction = flow_direction
        state = response.state
        dissipation_values.append(state.dissipated_energy_kn_m)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "plastic_flow_direction": flow_direction,
                **response.to_dict(),
            }
        )
        previous_rotation = rotation
        previous_moment = response.moment_kn_m

    dissipation_monotonic = all(
        current + 1.0e-15 >= previous
        for previous, current in zip(dissipation_values, dissipation_values[1:])
    )
    return {
        "material_id": material.material_id,
        "return_mapping_algorithm": ROTATIONAL_LINK_RETURN_MAPPING_ALGORITHM,
        "rotation_path_rad": list(path),
        "step_count": len(rows),
        "yielded_step_count": sum(bool(row["yielded"]) for row in rows),
        "plastic_flow_reversal_count": reversal_count,
        "moment_rotation_work_kn_m": work_kn_m,
        "cumulative_dissipated_energy_kn_m": state.dissipated_energy_kn_m,
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "energy_gate_passed": bool(
            dissipation_monotonic and state.dissipated_energy_kn_m > 0.0
        ),
        "final_state": state.to_dict(),
        "history": rows,
    }


__all__ = [
    "ROTATIONAL_LINK_RETURN_MAPPING_ALGORITHM",
    "ROTATIONAL_LINK_STATE_SCHEMA_VERSION",
    "ROTATIONAL_LINK_TANGENT_DEFINITION",
    "BilinearCombinedHardeningRotationalLink",
    "BilinearRotationalLinkResponse",
    "BilinearRotationalLinkState",
    "finite_difference_rotational_link_tangent_check",
    "integrate_rotational_link_history",
]
