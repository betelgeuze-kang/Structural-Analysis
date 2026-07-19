"""State-updated bilinear hysteretic link in force-deformation units."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Iterable


STATE_SCHEMA_VERSION = "bilinear-combined-hardening-link-state.v1"
RETURN_MAPPING_ALGORITHM = "backward_euler_1d_link_return_mapping"
TANGENT_DEFINITION = "algorithmic_consistent_d_force_d_deformation"
_STATE_HASH_DOMAIN = b"structural-analysis/bilinear-link-state/v1\0"


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class BilinearLinkState:
    plastic_deformation_m: float = 0.0
    backforce_kn: float = 0.0
    accumulated_plastic_deformation_m: float = 0.0
    dissipated_energy_kn_m: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "plastic_deformation_m",
            "backforce_kn",
            "accumulated_plastic_deformation_m",
            "dissipated_energy_kn_m",
        ):
            _require_finite(name, getattr(self, name))
        if self.accumulated_plastic_deformation_m < 0.0:
            raise ValueError(
                "accumulated_plastic_deformation_m must be non-negative"
            )
        if self.dissipated_energy_kn_m < 0.0:
            raise ValueError("dissipated_energy_kn_m must be non-negative")

    def canonical_bytes(self) -> bytes:
        return _STATE_HASH_DOMAIN + struct.pack(
            "<4d",
            self.plastic_deformation_m,
            self.backforce_kn,
            self.accumulated_plastic_deformation_m,
            self.dissipated_energy_kn_m,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "plastic_deformation_m": self.plastic_deformation_m,
            "backforce_kn": self.backforce_kn,
            "accumulated_plastic_deformation_m": (
                self.accumulated_plastic_deformation_m
            ),
            "dissipated_energy_kn_m": self.dissipated_energy_kn_m,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class BilinearLinkResponse:
    deformation_m: float
    force_kn: float
    consistent_tangent_kn_per_m: float
    yielded: bool
    plastic_multiplier_increment_m: float
    trial_yield_function_kn: float
    final_yield_function_kn: float
    committed_state_hash: str
    state: BilinearLinkState

    def to_dict(self) -> dict[str, Any]:
        return {
            "deformation_m": self.deformation_m,
            "force_kn": self.force_kn,
            "consistent_tangent_kn_per_m": self.consistent_tangent_kn_per_m,
            "yielded": self.yielded,
            "damage_evolved": False,
            "plastic_multiplier_increment_m": (
                self.plastic_multiplier_increment_m
            ),
            "trial_yield_function_kn": self.trial_yield_function_kn,
            "final_yield_function_kn": self.final_yield_function_kn,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class BilinearCombinedHardeningLink:
    initial_stiffness_kn_per_m: float = 10_000.0
    yield_force_kn: float = 100.0
    isotropic_hardening_kn_per_m: float = 200.0
    kinematic_hardening_kn_per_m: float = 300.0
    yield_tolerance_kn: float = 1.0e-10
    material_id: str = "bilinear_combined_hardening_link_1d"

    def __post_init__(self) -> None:
        for name in (
            "initial_stiffness_kn_per_m",
            "yield_force_kn",
            "isotropic_hardening_kn_per_m",
            "kinematic_hardening_kn_per_m",
            "yield_tolerance_kn",
        ):
            _require_finite(name, getattr(self, name))
        if self.initial_stiffness_kn_per_m <= 0.0:
            raise ValueError("initial_stiffness_kn_per_m must be positive")
        if self.yield_force_kn <= 0.0:
            raise ValueError("yield_force_kn must be positive")
        if self.isotropic_hardening_kn_per_m < 0.0:
            raise ValueError("isotropic_hardening_kn_per_m must be non-negative")
        if self.kinematic_hardening_kn_per_m < 0.0:
            raise ValueError("kinematic_hardening_kn_per_m must be non-negative")
        if self.yield_tolerance_kn < 0.0:
            raise ValueError("yield_tolerance_kn must be non-negative")
        if not self.material_id:
            raise ValueError("material_id must be non-empty")

    @property
    def hardening_stiffness_kn_per_m(self) -> float:
        return (
            self.isotropic_hardening_kn_per_m
            + self.kinematic_hardening_kn_per_m
        )

    @property
    def plastic_consistent_tangent_kn_per_m(self) -> float:
        hardening = self.hardening_stiffness_kn_per_m
        return self.initial_stiffness_kn_per_m * hardening / (
            self.initial_stiffness_kn_per_m + hardening
        )

    def initial_state(self) -> BilinearLinkState:
        return BilinearLinkState()

    def integrate(
        self,
        deformation_m: float,
        committed_state: BilinearLinkState,
    ) -> BilinearLinkResponse:
        deformation = _require_finite("deformation_m", deformation_m)
        elastic_trial = deformation - committed_state.plastic_deformation_m
        trial_force = self.initial_stiffness_kn_per_m * elastic_trial
        relative_trial = trial_force - committed_state.backforce_kn
        yield_radius = self.yield_force_kn + (
            self.isotropic_hardening_kn_per_m
            * committed_state.accumulated_plastic_deformation_m
        )
        trial_yield = abs(relative_trial) - yield_radius
        if trial_yield <= self.yield_tolerance_kn:
            force = trial_force
            tangent = self.initial_stiffness_kn_per_m
            plastic_increment = 0.0
            next_state = committed_state
            yielded = False
        else:
            flow_direction = 1.0 if relative_trial >= 0.0 else -1.0
            denominator = (
                self.initial_stiffness_kn_per_m
                + self.hardening_stiffness_kn_per_m
            )
            plastic_increment = trial_yield / denominator
            next_state = BilinearLinkState(
                plastic_deformation_m=(
                    committed_state.plastic_deformation_m
                    + plastic_increment * flow_direction
                ),
                backforce_kn=(
                    committed_state.backforce_kn
                    + self.kinematic_hardening_kn_per_m
                    * plastic_increment
                    * flow_direction
                ),
                accumulated_plastic_deformation_m=(
                    committed_state.accumulated_plastic_deformation_m
                    + plastic_increment
                ),
                dissipated_energy_kn_m=(
                    committed_state.dissipated_energy_kn_m
                    + self.yield_force_kn * plastic_increment
                ),
            )
            force = trial_force - (
                self.initial_stiffness_kn_per_m
                * plastic_increment
                * flow_direction
            )
            tangent = self.plastic_consistent_tangent_kn_per_m
            yielded = True
        final_yield = abs(force - next_state.backforce_kn) - (
            self.yield_force_kn
            + self.isotropic_hardening_kn_per_m
            * next_state.accumulated_plastic_deformation_m
        )
        return BilinearLinkResponse(
            deformation_m=deformation,
            force_kn=force,
            consistent_tangent_kn_per_m=tangent,
            yielded=yielded,
            plastic_multiplier_increment_m=plastic_increment,
            trial_yield_function_kn=trial_yield,
            final_yield_function_kn=final_yield,
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


def finite_difference_link_tangent_check(
    material: BilinearCombinedHardeningLink,
    committed_state: BilinearLinkState,
    *,
    deformation_m: float,
    epsilon_m: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    if epsilon_m <= 0.0 or not math.isfinite(epsilon_m):
        raise ValueError("epsilon_m must be finite and positive")
    center = material.integrate(deformation_m, committed_state)
    forward = material.integrate(deformation_m + epsilon_m, committed_state)
    backward = material.integrate(deformation_m - epsilon_m, committed_state)
    finite_difference = (forward.force_kn - backward.force_kn) / (2.0 * epsilon_m)
    absolute_error = abs(finite_difference - center.consistent_tangent_kn_per_m)
    scale = max(
        abs(finite_difference),
        abs(center.consistent_tangent_kn_per_m),
        1.0,
    )
    relative_error = absolute_error / scale
    same_parent = bool(
        forward.committed_state_hash
        == center.committed_state_hash
        == backward.committed_state_hash
    )
    return {
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "tangent_definition": TANGENT_DEFINITION,
        "deformation_m": float(deformation_m),
        "finite_difference_epsilon_m": epsilon_m,
        "analytic_consistent_tangent_kn_per_m": (
            center.consistent_tangent_kn_per_m
        ),
        "finite_difference_tangent_kn_per_m": finite_difference,
        "absolute_error_kn_per_m": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(relative_error <= relative_tolerance and same_parent),
    }


def integrate_link_deformation_history(
    material: BilinearCombinedHardeningLink,
    deformations_m: Iterable[float],
    *,
    initial_state: BilinearLinkState | None = None,
) -> dict[str, Any]:
    path = tuple(float(value) for value in deformations_m)
    if not path or not all(math.isfinite(value) for value in path):
        raise ValueError("deformations_m must contain finite values")
    state = initial_state or material.initial_state()
    previous_deformation = 0.0
    previous_force = material.integrate(0.0, state).force_kn
    previous_flow_direction = 0
    reversal_count = 0
    work_kn_m = 0.0
    dissipation_values = [state.dissipated_energy_kn_m]
    rows: list[dict[str, Any]] = []

    for step_index, deformation in enumerate(path, start=1):
        parent = state
        response = material.integrate(deformation, parent)
        work_kn_m += 0.5 * (previous_force + response.force_kn) * (
            deformation - previous_deformation
        )
        plastic_increment = (
            response.state.plastic_deformation_m - parent.plastic_deformation_m
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
        previous_deformation = deformation
        previous_force = response.force_kn

    dissipation_monotonic = all(
        current + 1.0e-15 >= previous
        for previous, current in zip(dissipation_values, dissipation_values[1:])
    )
    return {
        "material_id": material.material_id,
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "deformation_path_m": list(path),
        "step_count": len(rows),
        "yielded_step_count": sum(bool(row["yielded"]) for row in rows),
        "plastic_flow_reversal_count": reversal_count,
        "force_deformation_work_kn_m": work_kn_m,
        "cumulative_dissipated_energy_kn_m": state.dissipated_energy_kn_m,
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "energy_gate_passed": bool(
            dissipation_monotonic and state.dissipated_energy_kn_m > 0.0
        ),
        "final_state": state.to_dict(),
        "history": rows,
    }
