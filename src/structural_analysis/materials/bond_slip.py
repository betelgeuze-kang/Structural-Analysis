"""SI-unit bond-slip envelope and immutable cyclic connector state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from numbers import Integral, Real
import struct
from typing import Any, Iterable


BOND_SLIP_PROFILE = "piecewise_softening_cyclic_connector.v1"
BOND_SLIP_CLAIM_BOUNDARY = (
    "One-dimensional local connector candidate only. It is not a calibrated "
    "reinforcing-bar anchorage law, a distributed interface element, a published "
    "cyclic validation, a member failure model, or design authority."
)
_STATE_DOMAIN = b"structural-analysis/bond-slip-state/v1\0"


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(
            f"{name} must be a finite, losslessly representable real binary64 value"
        )
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            f"{name} must be a finite, losslessly representable real binary64 value"
        ) from error
    if (
        not math.isfinite(result)
        or value != result
        or (
            isinstance(value, Integral)
            and int(result) != int(value)
        )
    ):
        raise ValueError(
            f"{name} must be a finite, losslessly representable real binary64 value"
        )
    return 0.0 if result == 0.0 else result


def _sign(value: float, tolerance: float = 1.0e-15) -> int:
    return 1 if value > tolerance else -1 if value < -tolerance else 0


@dataclass(frozen=True)
class BondSlipMaterial:
    initial_stiffness_n_per_m: float = 90.0e6
    yield_slip_m: float = 0.45e-3
    ultimate_slip_m: float = 3.5e-3
    residual_strength_ratio: float = 0.25
    reversal_stiffness_degradation: float = 0.08
    reversal_strength_degradation: float = 0.05
    minimum_stiffness_ratio: float = 0.15
    material_id: str = "bond_slip_softening_cyclic_1d"

    def __post_init__(self) -> None:
        for name in (
            "initial_stiffness_n_per_m",
            "yield_slip_m",
            "ultimate_slip_m",
            "residual_strength_ratio",
            "reversal_stiffness_degradation",
            "reversal_strength_degradation",
            "minimum_stiffness_ratio",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if self.initial_stiffness_n_per_m <= 0.0:
            raise ValueError("initial_stiffness_n_per_m must be positive")
        if self.yield_slip_m <= 0.0:
            raise ValueError("yield_slip_m must be positive")
        if self.ultimate_slip_m <= self.yield_slip_m:
            raise ValueError("ultimate_slip_m must exceed yield_slip_m")
        if not 0.0 <= self.residual_strength_ratio < 1.0:
            raise ValueError("residual_strength_ratio must be in [0, 1)")
        if not 0.0 <= self.reversal_stiffness_degradation < 1.0:
            raise ValueError("reversal_stiffness_degradation must be in [0, 1)")
        if not 0.0 <= self.reversal_strength_degradation < 1.0:
            raise ValueError("reversal_strength_degradation must be in [0, 1)")
        if not 0.0 < self.minimum_stiffness_ratio <= 1.0:
            raise ValueError("minimum_stiffness_ratio must be in (0, 1]")
        if not self.material_id.strip():
            raise ValueError("material_id must be non-empty")

    @property
    def peak_force_n(self) -> float:
        return self.initial_stiffness_n_per_m * self.yield_slip_m

    def validate_state_admissibility(
        self,
        state: BondSlipState,
    ) -> BondSlipState:
        """Reject algebraically impossible cyclic degradation states."""

        if type(state) is not BondSlipState:
            raise ValueError("state must be an exact BondSlipState")
        slip_tolerance = max(
            1.0e-15,
            1.0e-12
            * max(
                self.ultimate_slip_m,
                state.maximum_absolute_slip_m,
                abs(state.previous_slip_m),
            ),
        )
        if (
            state.maximum_absolute_slip_m + slip_tolerance
            < abs(state.previous_slip_m)
        ):
            raise ValueError("maximum slip is below the retained connector slip")
        energy_tolerance = max(
            1.0e-15,
            1.0e-12 * self.peak_force_n * self.ultimate_slip_m,
        )
        expected_stiffness = min(
            1.0 - self.minimum_stiffness_ratio,
            self.reversal_stiffness_degradation * state.reversal_count,
        )
        expected_strength = min(
            0.8,
            self.reversal_strength_degradation * state.reversal_count,
        )
        if not math.isclose(
            state.stiffness_degradation,
            expected_stiffness,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ) or not math.isclose(
            state.strength_degradation,
            expected_strength,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError("connector degradation is inconsistent with reversals")
        if state.reversal_count == 0:
            expected_sign = _sign(state.previous_slip_m)
            envelope_force = bond_slip_envelope(state.previous_slip_m, self)[0]
            if (
                state.last_increment_sign != expected_sign
                or not math.isclose(
                    state.maximum_absolute_slip_m,
                    abs(state.previous_slip_m),
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-15,
                )
                or not math.isclose(
                    state.previous_force_n,
                    envelope_force,
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-9,
                )
            ):
                raise ValueError("zero-reversal connector state is inconsistent")
            if (
                state.maximum_absolute_slip_m
                <= self.yield_slip_m + slip_tolerance
                and state.dissipated_energy_j > energy_tolerance
            ):
                raise ValueError(
                    "elastic zero-reversal connector state cannot retain dissipation"
                )
            monotonic_energy_bound = (
                self.peak_force_n * state.maximum_absolute_slip_m
            )
            if (
                state.dissipated_energy_j
                > monotonic_energy_bound + energy_tolerance
            ):
                raise ValueError(
                    "zero-reversal connector dissipation exceeds monotonic work"
                )
        elif (
            state.last_increment_sign == 0
            or state.maximum_absolute_slip_m <= 0.0
        ):
            raise ValueError("reversed connector state lacks path direction or slip")
        if state.reversal_count > 0:
            force_bound = self.peak_force_n + (
                2.0
                * self.initial_stiffness_n_per_m
                * state.maximum_absolute_slip_m
                * (state.reversal_count + 1)
            )
            if math.isfinite(force_bound):
                force_tolerance = max(1.0e-9, 1.0e-12 * force_bound)
                if abs(state.previous_force_n) > force_bound + force_tolerance:
                    raise ValueError(
                        "connector force exceeds the retained path reachability bound"
                    )
        if (
            state.maximum_absolute_slip_m == 0.0
            and state.dissipated_energy_j != 0.0
        ):
            raise ValueError("zero-slip connector state cannot retain dissipation")
        return state


@dataclass(frozen=True)
class BondSlipState:
    previous_slip_m: float = 0.0
    previous_force_n: float = 0.0
    last_increment_sign: int = 0
    reversal_count: int = 0
    maximum_absolute_slip_m: float = 0.0
    stiffness_degradation: float = 0.0
    strength_degradation: float = 0.0
    dissipated_energy_j: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "previous_slip_m",
            "previous_force_n",
            "maximum_absolute_slip_m",
            "stiffness_degradation",
            "strength_degradation",
            "dissipated_energy_j",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if (
            type(self.last_increment_sign) is not int
            or self.last_increment_sign not in {-1, 0, 1}
        ):
            raise ValueError("last_increment_sign must be -1, 0, or 1")
        if (
            type(self.reversal_count) is not int
            or self.reversal_count < 0
            or self.reversal_count > 2**63 - 1
        ):
            raise ValueError("reversal_count must be a non-negative integer")
        if self.maximum_absolute_slip_m < 0.0:
            raise ValueError("maximum_absolute_slip_m must be non-negative")
        if not 0.0 <= self.stiffness_degradation < 1.0:
            raise ValueError("stiffness_degradation must be in [0, 1)")
        if not 0.0 <= self.strength_degradation < 1.0:
            raise ValueError("strength_degradation must be in [0, 1)")
        if self.dissipated_energy_j < 0.0:
            raise ValueError("dissipated_energy_j must be non-negative")

    def canonical_bytes(self) -> bytes:
        return _STATE_DOMAIN + struct.pack(
            "<2diq4d",
            self.previous_slip_m,
            self.previous_force_n,
            self.last_increment_sign,
            self.reversal_count,
            self.maximum_absolute_slip_m,
            self.stiffness_degradation,
            self.strength_degradation,
            self.dissipated_energy_j,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "structural-analysis-bond-slip-state.v1",
            "previous_slip_m": self.previous_slip_m,
            "previous_force_n": self.previous_force_n,
            "last_increment_sign": self.last_increment_sign,
            "reversal_count": self.reversal_count,
            "maximum_absolute_slip_m": self.maximum_absolute_slip_m,
            "stiffness_degradation": self.stiffness_degradation,
            "strength_degradation": self.strength_degradation,
            "dissipated_energy_j": self.dissipated_energy_j,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class BondSlipResponse:
    slip_m: float
    force_n: float
    consistent_tangent_n_per_m: float
    branch: str
    reversal: bool
    unloading: bool
    interaction_ratio: float
    committed_state_hash: str
    state: BondSlipState

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": BOND_SLIP_PROFILE,
            "slip_m": self.slip_m,
            "force_n": self.force_n,
            "consistent_tangent_n_per_m": self.consistent_tangent_n_per_m,
            "branch": self.branch,
            "reversal": self.reversal,
            "unloading": self.unloading,
            "interaction_ratio": self.interaction_ratio,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
            "claim_boundary": BOND_SLIP_CLAIM_BOUNDARY,
        }


def bond_slip_envelope(
    slip_m: float,
    material: BondSlipMaterial | None = None,
) -> tuple[float, float, str]:
    selected = material or BondSlipMaterial()
    slip = _finite("slip_m", slip_m)
    magnitude = abs(slip)
    direction = 1.0 if slip >= 0.0 else -1.0
    peak = selected.peak_force_n
    if magnitude <= selected.yield_slip_m:
        return (
            selected.initial_stiffness_n_per_m * slip,
            selected.initial_stiffness_n_per_m,
            "elastic",
        )
    residual = peak * selected.residual_strength_ratio
    if magnitude <= selected.ultimate_slip_m:
        ratio = (magnitude - selected.yield_slip_m) / (
            selected.ultimate_slip_m - selected.yield_slip_m
        )
        force = peak + ratio * (residual - peak)
        tangent = (residual - peak) / (selected.ultimate_slip_m - selected.yield_slip_m)
        return direction * force, tangent, "softening"
    return direction * residual, 0.0, "residual"


def integrate_bond_slip(
    slip_m: float,
    committed_state: BondSlipState,
    material: BondSlipMaterial | None = None,
) -> BondSlipResponse:
    selected = material or BondSlipMaterial()
    selected.validate_state_admissibility(committed_state)
    slip = _finite("slip_m", slip_m)
    force, tangent, branch = bond_slip_envelope(slip, selected)
    increment = slip - committed_state.previous_slip_m
    increment_sign = _sign(increment)
    position_sign = _sign(slip)
    if (
        increment_sign == 0
        and position_sign != 0
        and committed_state.last_increment_sign == 0
    ):
        increment_sign = position_sign
    reversal = bool(
        committed_state.last_increment_sign
        and increment_sign
        and increment_sign != committed_state.last_increment_sign
    )
    reversal_count = committed_state.reversal_count + int(reversal)
    maximum_slip = max(
        committed_state.maximum_absolute_slip_m,
        abs(committed_state.previous_slip_m),
        abs(slip),
    )
    stiffness_degradation = min(
        1.0 - selected.minimum_stiffness_ratio,
        max(
            committed_state.stiffness_degradation,
            selected.reversal_stiffness_degradation * reversal_count,
        ),
    )
    strength_degradation = min(
        0.8,
        max(
            committed_state.strength_degradation,
            selected.reversal_strength_degradation * reversal_count,
        ),
    )
    unloading = bool(reversal_count > 0 and abs(slip) < maximum_slip)
    if unloading:
        tangent = selected.initial_stiffness_n_per_m * max(
            selected.minimum_stiffness_ratio,
            1.0 - stiffness_degradation,
        )
        force = committed_state.previous_force_n + tangent * increment
        branch = "cyclic_unloading_reloading"
    else:
        force *= 1.0 - strength_degradation
        tangent *= 1.0 - stiffness_degradation
    if abs(slip) >= selected.ultimate_slip_m:
        residual = (
            selected.peak_force_n
            * selected.residual_strength_ratio
            * max(0.2, 1.0 - strength_degradation)
        )
        force = math.copysign(residual, slip if slip != 0.0 else 1.0)
        tangent = 0.0
        branch = "degraded_residual"
    work_increment = 0.5 * (committed_state.previous_force_n + force) * increment
    recoverable_bound = 0.5 * abs(force * slip)
    dissipated_increment = max(abs(work_increment) - recoverable_bound, 0.0)
    state = BondSlipState(
        previous_slip_m=slip,
        previous_force_n=force,
        last_increment_sign=(increment_sign or committed_state.last_increment_sign),
        reversal_count=reversal_count,
        maximum_absolute_slip_m=maximum_slip,
        stiffness_degradation=stiffness_degradation,
        strength_degradation=strength_degradation,
        dissipated_energy_j=(
            committed_state.dissipated_energy_j + dissipated_increment
        ),
    )
    selected.validate_state_admissibility(state)
    return BondSlipResponse(
        slip_m=slip,
        force_n=force,
        consistent_tangent_n_per_m=tangent,
        branch=branch,
        reversal=reversal,
        unloading=unloading,
        interaction_ratio=bond_slip_interaction_ratio(slip, selected),
        committed_state_hash=committed_state.state_hash,
        state=state,
    )


def bond_slip_interaction_ratio(
    slip_m: float,
    material: BondSlipMaterial | None = None,
) -> float:
    selected = material or BondSlipMaterial()
    magnitude = abs(_finite("slip_m", slip_m))
    if magnitude <= selected.yield_slip_m:
        return 1.0
    if magnitude >= selected.ultimate_slip_m:
        return selected.residual_strength_ratio
    fraction = (magnitude - selected.yield_slip_m) / (
        selected.ultimate_slip_m - selected.yield_slip_m
    )
    return 1.0 + fraction * (selected.residual_strength_ratio - 1.0)


def integrate_bond_slip_history(
    slips_m: Iterable[float],
    *,
    material: BondSlipMaterial | None = None,
    initial_state: BondSlipState | None = None,
) -> tuple[BondSlipResponse, ...]:
    selected = material or BondSlipMaterial()
    state = initial_state or BondSlipState()
    rows: list[BondSlipResponse] = []
    for slip in slips_m:
        response = integrate_bond_slip(slip, state, selected)
        rows.append(response)
        state = response.state
    if not rows:
        raise ValueError("slips_m must be non-empty")
    return tuple(rows)


__all__ = [
    "BOND_SLIP_CLAIM_BOUNDARY",
    "BOND_SLIP_PROFILE",
    "BondSlipMaterial",
    "BondSlipResponse",
    "BondSlipState",
    "bond_slip_envelope",
    "bond_slip_interaction_ratio",
    "integrate_bond_slip",
    "integrate_bond_slip_history",
]
