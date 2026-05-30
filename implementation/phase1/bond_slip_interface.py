#!/usr/bin/env python3
"""Bond-slip interface helpers with spring/link element capability."""

from __future__ import annotations

from dataclasses import dataclass
import math

try:
    from implementation.phase1.steel_constitutive_library import MaterialSnapshot
except ImportError:  # pragma: no cover - script execution fallback
    from steel_constitutive_library import MaterialSnapshot


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class BondSlipMaterial:
    k0_kn_per_mm: float = 90.0
    slip_y_mm: float = 0.45
    slip_u_mm: float = 3.5
    residual_ratio: float = 0.25
    interaction_y: float = 8.0e-4
    interaction_u: float = 4.0e-3
    cyclic_degradation: float = 0.08

    @property
    def peak_force_kn(self) -> float:
        return float(self.k0_kn_per_mm) * float(self.slip_y_mm)


@dataclass(frozen=True)
class BondSlipInteractionSnapshot:
    slip: float
    interaction_ratio: float
    state_tag: str


@dataclass(frozen=True)
class BondSlipSpringState:
    previous_slip_mm: float = 0.0
    previous_force_kn: float = 0.0
    last_increment_sign: int = 0
    reversal_count: int = 0
    max_abs_slip_mm: float = 0.0
    stiffness_degradation: float = 0.0
    strength_degradation: float = 0.0
    history_tag: str = "monotonic"


@dataclass(frozen=True)
class BondSlipSpringSnapshot:
    force_kn: float
    stiffness_kn_per_mm: float
    state: BondSlipSpringState
    reversal_count: int
    stiffness_degradation: float
    strength_degradation: float
    evidence_tags: tuple[str, ...]


def bond_slip_response(slip_mm: float, mat: BondSlipMaterial | None = None) -> MaterialSnapshot:
    if mat is None:
        mat = BondSlipMaterial()

    s = abs(float(slip_mm))
    sign = 1.0 if float(slip_mm) >= 0.0 else -1.0
    peak = float(mat.peak_force_kn)
    if s <= mat.slip_y_mm:
        return MaterialSnapshot(
            strain=slip_mm,
            stress_mpa=sign * mat.k0_kn_per_mm * s,
            tangent_mpa=mat.k0_kn_per_mm,
            state_tag="bond_elastic",
        )
    if s <= mat.slip_u_mm:
        residual = peak * float(mat.residual_ratio)
        ratio = (s - mat.slip_y_mm) / max(mat.slip_u_mm - mat.slip_y_mm, 1e-9)
        force = peak + ratio * (residual - peak)
        tangent = (residual - peak) / max(mat.slip_u_mm - mat.slip_y_mm, 1e-9)
        return MaterialSnapshot(
            strain=slip_mm,
            stress_mpa=sign * force,
            tangent_mpa=tangent,
            state_tag="bond_softening",
        )
    return MaterialSnapshot(
        strain=slip_mm,
        stress_mpa=sign * peak * mat.residual_ratio,
        tangent_mpa=0.0,
        state_tag="bond_residual",
    )


def _sign_with_tol(value: float, tol: float = 1.0e-12) -> int:
    if value > tol:
        return 1
    if value < -tol:
        return -1
    return 0


def bond_slip_spring_response(
    slip_mm: float,
    state: BondSlipSpringState | None = None,
    mat: BondSlipMaterial | None = None,
) -> BondSlipSpringSnapshot:
    """Return bond-slip spring response with cyclic degradation.

    The model implements:
    - Monotonic envelope with elastic, softening, and residual branches
    - Unloading/reloading paths with stiffness degradation
    - Strength degradation based on reversal count and max slip
    - Spring/link element for FE coupling
    """

    if state is None:
        state = BondSlipSpringState()
    if mat is None:
        mat = BondSlipMaterial()

    slip = float(slip_mm)
    envelope = bond_slip_response(slip, mat)
    increment = slip - float(state.previous_slip_mm)
    increment_sign = _sign_with_tol(increment)
    reversal = bool(state.last_increment_sign and increment_sign and increment_sign != state.last_increment_sign)
    reversal_count = int(state.reversal_count) + int(reversal)

    max_abs_slip_mm = max(float(state.max_abs_slip_mm), abs(slip), abs(float(state.previous_slip_mm)))
    max_slip_ratio = max_abs_slip_mm / max(float(mat.slip_u_mm), 1.0e-9)

    stiffness_degradation = _clamp(
        max(
            float(state.stiffness_degradation),
            float(mat.cyclic_degradation) * reversal_count + 0.20 * _clamp(max_slip_ratio, 0.0, 1.0),
        ),
        0.0,
        0.85,
    )
    strength_degradation = _clamp(
        max(
            float(state.strength_degradation),
            0.05 * reversal_count + 0.15 * _clamp(max_slip_ratio, 0.0, 1.0),
        ),
        0.0,
        0.65,
    )

    unloading_active = bool(reversal_count > 0 and abs(slip) < max_abs_slip_mm)

    force_kn = float(envelope.stress_mpa) * (1.0 - strength_degradation)
    stiffness_kn_per_mm = float(envelope.tangent_mpa) * (1.0 - stiffness_degradation)

    if unloading_active:
        unloading_stiffness = float(mat.k0_kn_per_mm) * max(0.15, 1.0 - stiffness_degradation)
        delta_slip = slip - float(state.previous_slip_mm)
        force_kn = float(state.previous_force_kn) + unloading_stiffness * delta_slip
        stiffness_kn_per_mm = unloading_stiffness

    residual_floor = float(mat.peak_force_kn) * float(mat.residual_ratio) * max(0.30, 1.0 - 0.50 * strength_degradation)
    if abs(slip) >= float(mat.slip_u_mm):
        force_kn = math.copysign(residual_floor, slip if abs(slip) > 0.0 else 1.0)
        stiffness_kn_per_mm = 0.0

    evidence_tags: list[str] = []
    if reversal:
        evidence_tags.append("reversal")
    if unloading_active:
        evidence_tags.append("unloading")
    if stiffness_degradation > 0.0:
        evidence_tags.append("stiffness_degradation")
    if strength_degradation > 0.0:
        evidence_tags.append("strength_degradation")
    if not evidence_tags:
        evidence_tags.append("monotonic")

    history_tag_parts: list[str] = []
    if reversal_count > 0:
        history_tag_parts.append("cyclic")
    if unloading_active:
        history_tag_parts.append("unloading")
    if stiffness_degradation > 0.0 or strength_degradation > 0.0:
        history_tag_parts.append("degrading")
    history_tag = "-".join(history_tag_parts) if history_tag_parts else "monotonic"

    next_state = BondSlipSpringState(
        previous_slip_mm=slip,
        previous_force_kn=force_kn,
        last_increment_sign=increment_sign or int(state.last_increment_sign),
        reversal_count=reversal_count,
        max_abs_slip_mm=float(max_abs_slip_mm),
        stiffness_degradation=float(stiffness_degradation),
        strength_degradation=float(strength_degradation),
        history_tag=history_tag,
    )
    return BondSlipSpringSnapshot(
        force_kn=force_kn,
        stiffness_kn_per_mm=stiffness_kn_per_mm,
        state=next_state,
        reversal_count=reversal_count,
        stiffness_degradation=float(stiffness_degradation),
        strength_degradation=float(strength_degradation),
        evidence_tags=tuple(evidence_tags),
    )


def bond_slip_interaction_response(
    slip: float,
    mat: BondSlipMaterial | None = None,
    *,
    interaction_y: float | None = None,
    interaction_u: float | None = None,
    residual_ratio: float | None = None,
) -> BondSlipInteractionSnapshot:
    if mat is None:
        mat = BondSlipMaterial()

    slip_abs = abs(float(slip))
    slip_y = max(float(mat.interaction_y if interaction_y is None else interaction_y), 1e-9)
    slip_u = max(float(mat.interaction_u if interaction_u is None else interaction_u), slip_y)
    residual = _clamp(mat.residual_ratio if residual_ratio is None else residual_ratio, 0.05, 1.0)
    if slip_abs <= slip_y:
        return BondSlipInteractionSnapshot(slip=float(slip), interaction_ratio=1.0, state_tag="full_interaction")
    if slip_abs <= slip_u:
        ratio = 1.0 + (slip_abs - slip_y) * (residual - 1.0) / max(slip_u - slip_y, 1e-9)
        return BondSlipInteractionSnapshot(
            slip=float(slip),
            interaction_ratio=_clamp(ratio, residual, 1.0),
            state_tag="partial_interaction",
        )
    return BondSlipInteractionSnapshot(
        slip=float(slip),
        interaction_ratio=float(residual),
        state_tag="residual_interaction",
    )


def bond_slip_spring_probe(
    *,
    slip_history_mm: tuple[float, ...] = (0.30, 1.20, -0.25, 2.10, -0.80, 4.00),
    mat: BondSlipMaterial | None = None,
    probe_id: str = "bond_slip_spring_probe_v1",
) -> dict:
    """Run a deterministic cyclic bond-slip spring sequence and summarize deterioration evidence."""

    if mat is None:
        mat = BondSlipMaterial(k0_kn_per_mm=95.0, slip_y_mm=0.40, slip_u_mm=3.50, residual_ratio=0.25)

    state = BondSlipSpringState()
    snapshots: list[BondSlipSpringSnapshot] = []
    for slip in slip_history_mm:
        snapshot = bond_slip_spring_response(slip, state=state, mat=mat)
        snapshots.append(snapshot)
        state = snapshot.state

    evidence_tags = sorted({tag for snapshot in snapshots for tag in snapshot.evidence_tags})
    reversal_count = max((snapshot.reversal_count for snapshot in snapshots), default=0)
    max_stiffness_degradation = max((snapshot.stiffness_degradation for snapshot in snapshots), default=0.0)
    max_strength_degradation = max((snapshot.strength_degradation for snapshot in snapshots), default=0.0)

    return {
        "probe_id": probe_id,
        "slip_history_mm": slip_history_mm,
        "evidence_tags": evidence_tags,
        "reversal_count": reversal_count,
        "max_stiffness_degradation": max_stiffness_degradation,
        "max_strength_degradation": max_strength_degradation,
    }


__all__ = [
    "BondSlipInteractionSnapshot",
    "BondSlipMaterial",
    "BondSlipSpringSnapshot",
    "BondSlipSpringState",
    "bond_slip_interaction_response",
    "bond_slip_response",
    "bond_slip_spring_probe",
    "bond_slip_spring_response",
]
