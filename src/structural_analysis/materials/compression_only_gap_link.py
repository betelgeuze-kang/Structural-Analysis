"""Frictionless compression-only elastic gap in force-deformation units."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Iterable, Literal


GAP_LINK_STATE_SCHEMA_VERSION = "compression-only-gap-link-state.v1"
GAP_LINK_ACTIVE_SET_ALGORITHM = "exact_piecewise_linear_compression_only_gap_active_set"
GAP_LINK_TANGENT_DEFINITION = (
    "one_sided_algorithmic_d_force_d_deformation_open_at_exact_closure"
)
GAP_LINK_CLOSURE_CONVENTION = (
    "contact_active_iff_deformation_plus_initial_gap_is_strictly_negative"
)
_STATE_HASH_DOMAIN = b"structural-analysis/compression-only-gap-link-state/v1\0"


def _require_finite(name: str, value: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class CompressionOnlyGapLinkState:
    """Committed active-set and bounded path metadata for one gap link."""

    contact_active: bool = False
    maximum_penetration_m: float = 0.0
    closure_event_count: int = 0
    opening_event_count: int = 0

    def __post_init__(self) -> None:
        if type(self.contact_active) is not bool:
            raise ValueError("contact_active must be a boolean")
        _require_finite("maximum_penetration_m", self.maximum_penetration_m)
        if self.maximum_penetration_m < 0.0:
            raise ValueError("maximum_penetration_m must be non-negative")
        for name in ("closure_event_count", "opening_event_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.opening_event_count > self.closure_event_count:
            raise ValueError("opening events cannot exceed closure events")
        expected_closures = self.opening_event_count + int(self.contact_active)
        if self.closure_event_count != expected_closures:
            raise ValueError("contact state and event counts are inconsistent")
        if self.closure_event_count == 0 and self.maximum_penetration_m != 0.0:
            raise ValueError("never-closed contact cannot have penetration history")
        if self.closure_event_count > 0 and self.maximum_penetration_m <= 0.0:
            raise ValueError("closed contact must retain positive penetration history")

    def canonical_bytes(self) -> bytes:
        return _STATE_HASH_DOMAIN + struct.pack(
            "<?dQQ",
            self.contact_active,
            self.maximum_penetration_m,
            self.closure_event_count,
            self.opening_event_count,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GAP_LINK_STATE_SCHEMA_VERSION,
            "contact_active": self.contact_active,
            "maximum_penetration_m": self.maximum_penetration_m,
            "closure_event_count": self.closure_event_count,
            "opening_event_count": self.opening_event_count,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class CompressionOnlyGapLinkResponse:
    deformation_m: float
    signed_clearance_m: float
    penetration_m: float
    force_kn: float
    consistent_tangent_kn_per_m: float
    contact_active: bool
    active_set_transition: Literal["unchanged", "closed", "opened"]
    recoverable_energy_kn_m: float
    committed_state_hash: str
    state: CompressionOnlyGapLinkState

    @property
    def yielded(self) -> bool:
        """Preserve the generic scalar-link metric without claiming plasticity."""

        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "deformation_m": self.deformation_m,
            "signed_clearance_m": self.signed_clearance_m,
            "penetration_m": self.penetration_m,
            "force_kn": self.force_kn,
            "consistent_tangent_kn_per_m": self.consistent_tangent_kn_per_m,
            "contact_active": self.contact_active,
            "active_set_transition": self.active_set_transition,
            "recoverable_energy_kn_m": self.recoverable_energy_kn_m,
            "yielded": False,
            "damage_evolved": False,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class CompressionOnlyGapLink:
    """One continuous unilateral spring with a strict open-at-closure rule."""

    contact_stiffness_kn_per_m: float = 10_000.0
    initial_gap_m: float = 0.0
    material_id: str = "compression_only_gap_link_1d"

    def __post_init__(self) -> None:
        _require_finite(
            "contact_stiffness_kn_per_m",
            self.contact_stiffness_kn_per_m,
        )
        _require_finite("initial_gap_m", self.initial_gap_m)
        if self.contact_stiffness_kn_per_m <= 0.0:
            raise ValueError("contact_stiffness_kn_per_m must be positive")
        if self.initial_gap_m < 0.0:
            raise ValueError("initial_gap_m must be non-negative")
        normalized_id = str(self.material_id).strip()
        if not normalized_id:
            raise ValueError("material_id must be non-empty")
        object.__setattr__(self, "material_id", normalized_id)

    def initial_state(self) -> CompressionOnlyGapLinkState:
        return CompressionOnlyGapLinkState()

    def integrate(
        self,
        deformation_m: float,
        committed_state: CompressionOnlyGapLinkState,
    ) -> CompressionOnlyGapLinkResponse:
        if type(committed_state) is not CompressionOnlyGapLinkState:
            raise ValueError("committed_state must be a CompressionOnlyGapLinkState")
        deformation = _require_finite("deformation_m", deformation_m)
        signed_clearance = deformation + self.initial_gap_m
        active = signed_clearance < 0.0
        penetration = -signed_clearance if active else 0.0
        force = -self.contact_stiffness_kn_per_m * penetration if active else 0.0
        tangent = self.contact_stiffness_kn_per_m if active else 0.0
        if active and not committed_state.contact_active:
            transition: Literal["unchanged", "closed", "opened"] = "closed"
            closure_events = committed_state.closure_event_count + 1
            opening_events = committed_state.opening_event_count
        elif not active and committed_state.contact_active:
            transition = "opened"
            closure_events = committed_state.closure_event_count
            opening_events = committed_state.opening_event_count + 1
        else:
            transition = "unchanged"
            closure_events = committed_state.closure_event_count
            opening_events = committed_state.opening_event_count
        next_state = CompressionOnlyGapLinkState(
            contact_active=active,
            maximum_penetration_m=max(
                committed_state.maximum_penetration_m,
                penetration,
            ),
            closure_event_count=closure_events,
            opening_event_count=opening_events,
        )
        return CompressionOnlyGapLinkResponse(
            deformation_m=deformation,
            signed_clearance_m=signed_clearance,
            penetration_m=penetration,
            force_kn=force,
            consistent_tangent_kn_per_m=tangent,
            contact_active=active,
            active_set_transition=transition,
            recoverable_energy_kn_m=(
                0.5 * self.contact_stiffness_kn_per_m * penetration**2
            ),
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


def finite_difference_gap_link_tangent_check(
    material: CompressionOnlyGapLink,
    committed_state: CompressionOnlyGapLinkState,
    *,
    deformation_m: float,
    epsilon_m: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    epsilon = _require_finite("epsilon_m", epsilon_m)
    tolerance = _require_finite("relative_tolerance", relative_tolerance)
    if epsilon <= 0.0:
        raise ValueError("epsilon_m must be positive")
    if tolerance <= 0.0:
        raise ValueError("relative_tolerance must be positive")
    center = material.integrate(deformation_m, committed_state)
    forward = material.integrate(deformation_m + epsilon, committed_state)
    backward = material.integrate(deformation_m - epsilon, committed_state)
    finite_difference = (forward.force_kn - backward.force_kn) / (2.0 * epsilon)
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
    active_set_stable = bool(
        forward.contact_active == center.contact_active == backward.contact_active
    )
    return {
        "active_set_algorithm": GAP_LINK_ACTIVE_SET_ALGORITHM,
        "closure_convention": GAP_LINK_CLOSURE_CONVENTION,
        "tangent_definition": GAP_LINK_TANGENT_DEFINITION,
        "deformation_m": float(deformation_m),
        "finite_difference_epsilon_m": epsilon,
        "contact_active": center.contact_active,
        "active_set_stable_across_perturbations": active_set_stable,
        "analytic_consistent_tangent_kn_per_m": (center.consistent_tangent_kn_per_m),
        "finite_difference_tangent_kn_per_m": finite_difference,
        "absolute_error_kn_per_m": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(relative_error <= tolerance and same_parent and active_set_stable),
    }


def integrate_gap_link_deformation_history(
    material: CompressionOnlyGapLink,
    deformations_m: Iterable[float],
    *,
    initial_state: CompressionOnlyGapLinkState | None = None,
) -> dict[str, Any]:
    path = tuple(_require_finite("deformation_m", value) for value in deformations_m)
    if not path:
        raise ValueError("deformations_m must be non-empty")
    state = initial_state or material.initial_state()
    if type(state) is not CompressionOnlyGapLinkState:
        raise ValueError("initial_state must be a CompressionOnlyGapLinkState")
    rows: list[dict[str, Any]] = []
    for step_index, deformation in enumerate(path, start=1):
        parent = state
        response = material.integrate(deformation, parent)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                **response.to_dict(),
            }
        )
        state = response.state
    return {
        "material_id": material.material_id,
        "active_set_algorithm": GAP_LINK_ACTIVE_SET_ALGORITHM,
        "closure_convention": GAP_LINK_CLOSURE_CONVENTION,
        "deformation_path_m": list(path),
        "step_count": len(rows),
        "active_step_count": sum(bool(row["contact_active"]) for row in rows),
        "closure_event_count": state.closure_event_count,
        "opening_event_count": state.opening_event_count,
        "maximum_penetration_m": state.maximum_penetration_m,
        "final_state": state.to_dict(),
        "history": rows,
    }


__all__ = [
    "GAP_LINK_ACTIVE_SET_ALGORITHM",
    "GAP_LINK_CLOSURE_CONVENTION",
    "GAP_LINK_STATE_SCHEMA_VERSION",
    "GAP_LINK_TANGENT_DEFINITION",
    "CompressionOnlyGapLink",
    "CompressionOnlyGapLinkResponse",
    "CompressionOnlyGapLinkState",
    "finite_difference_gap_link_tangent_check",
    "integrate_gap_link_deformation_history",
]
