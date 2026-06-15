#!/usr/bin/env python3
"""Dedicated reduced-order steel constitutive helpers with cyclic Bauschinger effect."""

from __future__ import annotations

from dataclasses import dataclass
import math


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class MaterialSnapshot:
    strain: float
    stress_mpa: float
    tangent_mpa: float
    state_tag: str


@dataclass(frozen=True)
class SteelMaterial:
    fy_mpa: float = 420.0
    es_mpa: float = 200000.0
    hardening_ratio: float = 0.015
    fu_mpa: float = 620.0
    fracture_strain: float = 0.12
    local_buckling_strain: float = 0.0
    post_buckling_residual_ratio: float = 0.35
    kinematic_hardening_ratio: float = 0.50
    bauschinger_factor: float = 0.30

    @property
    def eps_y(self) -> float:
        return float(self.fy_mpa) / max(float(self.es_mpa), 1e-9)


@dataclass(frozen=True)
class SteelCyclicState:
    previous_strain: float = 0.0
    previous_stress_mpa: float = 0.0
    last_increment_sign: int = 0
    reversal_count: int = 0
    max_tension_strain: float = 0.0
    max_compression_strain: float = 0.0
    back_stress_mpa: float = 0.0
    plastic_strain: float = 0.0
    yielded: bool = False
    bar_buckled: bool = False
    history_tag: str = "monotonic"


@dataclass(frozen=True)
class SteelCyclicSnapshot:
    envelope: MaterialSnapshot
    restoring: MaterialSnapshot
    state: SteelCyclicState
    reversal_count: int
    back_stress_mpa: float
    plastic_strain: float
    bauschinger_active: bool
    bar_buckled: bool
    evidence_tags: tuple[str, ...]


def steel_response(strain: float, mat: SteelMaterial | None = None) -> MaterialSnapshot:
    if mat is None:
        mat = SteelMaterial()

    e = float(strain)
    sign = 1.0 if e >= 0.0 else -1.0
    ea = abs(e)
    ey = float(mat.eps_y)
    if ea <= ey:
        return MaterialSnapshot(strain=e, stress_mpa=mat.es_mpa * e, tangent_mpa=mat.es_mpa, state_tag="elastic")

    tangent = float(mat.es_mpa) * float(mat.hardening_ratio)
    plastic = ea - ey
    stress_abs = float(mat.fy_mpa) + tangent * plastic
    stress_abs = min(stress_abs, float(mat.fu_mpa))
    if (
        sign < 0.0
        and float(mat.local_buckling_strain) > ey
        and ea > float(mat.local_buckling_strain)
        and float(mat.fracture_strain) > float(mat.local_buckling_strain)
    ):
        buckling_start = float(mat.local_buckling_strain)
        start_plastic = max(buckling_start - ey, 0.0)
        start_stress_abs = min(float(mat.fy_mpa) + tangent * start_plastic, float(mat.fu_mpa))
        residual_abs = max(
            0.05 * float(mat.fy_mpa),
            start_stress_abs * _clamp(mat.post_buckling_residual_ratio, 0.05, 1.0),
        )
        softening_ratio = (ea - buckling_start) / max(float(mat.fracture_strain) - buckling_start, 1e-9)
        stress_abs = start_stress_abs + _clamp(softening_ratio, 0.0, 1.0) * (residual_abs - start_stress_abs)
        tangent = (residual_abs - start_stress_abs) / max(float(mat.fracture_strain) - buckling_start, 1e-9)
        if ea < float(mat.fracture_strain):
            return MaterialSnapshot(
                strain=e,
                stress_mpa=sign * stress_abs,
                tangent_mpa=tangent,
                state_tag="compression_local_buckling",
            )
    if ea >= float(mat.fracture_strain):
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * stress_abs,
            tangent_mpa=0.0,
            state_tag="fracture_limit",
        )
    capped = bool(stress_abs >= float(mat.fu_mpa))
    if capped:
        tangent = 0.0
    state_tag = "plastic_hardening" if not capped else "plastic_capped"
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=tangent, state_tag=state_tag)


def _sign_with_tol(value: float, tol: float = 1.0e-12) -> int:
    if value > tol:
        return 1
    if value < -tol:
        return -1
    return 0


def steel_cyclic_response(
    strain: float,
    state: SteelCyclicState | None = None,
    mat: SteelMaterial | None = None,
) -> SteelCyclicSnapshot:
    """Return steel response with Bauschinger effect, kinematic hardening, and bar buckling.

    The model implements:
    - Bauschinger effect: yield surface shift under reverse loading
    - Kinematic hardening: back stress evolution
    - Bar buckling: compression degradation after local buckling strain
    - Strength/stiffness degradation based on plastic strain history
    """

    if state is None:
        state = SteelCyclicState()
    if mat is None:
        mat = SteelMaterial()

    e = float(strain)
    envelope = steel_response(e, mat)
    increment = e - float(state.previous_strain)
    increment_sign = _sign_with_tol(increment)
    reversal = bool(state.last_increment_sign and increment_sign and increment_sign != state.last_increment_sign)
    reversal_count = int(state.reversal_count) + int(reversal)

    max_tension_strain = max(float(state.max_tension_strain), e)
    max_compression_strain = min(float(state.max_compression_strain), e)
    ey = float(mat.eps_y)
    ea = abs(e)
    yielded = bool(state.yielded or ea > ey)

    plastic_strain = max(float(state.plastic_strain), max(0.0, ea - ey))
    back_stress_mpa = float(state.back_stress_mpa)

    bauschinger_active = False
    if reversal and yielded:
        kinematic_ratio = _clamp(float(mat.kinematic_hardening_ratio), 0.0, 0.90)
        bauschinger_factor = _clamp(float(mat.bauschinger_factor), 0.05, 0.80)
        
        delta_back_stress = kinematic_ratio * float(mat.es_mpa) * abs(increment)
        if increment_sign > 0:
            back_stress_mpa = min(back_stress_mpa + delta_back_stress, float(mat.fy_mpa) * 0.80)
        else:
            back_stress_mpa = max(back_stress_mpa - delta_back_stress, -float(mat.fy_mpa) * 0.80)
        
        effective_yield = float(mat.fy_mpa) - bauschinger_factor * abs(back_stress_mpa)
        effective_yield = max(effective_yield, float(mat.fy_mpa) * 0.30)
        
        bauschinger_active = ea > effective_yield / max(float(mat.es_mpa), 1e-9)

    bar_buckled = bool(state.bar_buckled)
    if (
        not bar_buckled
        and e < 0.0
        and float(mat.local_buckling_strain) > ey
        and ea > float(mat.local_buckling_strain)
        and float(mat.fracture_strain) > float(mat.local_buckling_strain)
    ):
        bar_buckled = True

    stress_mpa = float(envelope.stress_mpa)
    tangent_mpa = float(envelope.tangent_mpa)

    if bauschinger_active:
        stress_mpa = stress_mpa - back_stress_mpa
        tangent_mpa = float(mat.es_mpa) * float(mat.hardening_ratio)

    if bar_buckled and e < 0.0:
        degradation = _clamp(plastic_strain / max(float(mat.fracture_strain), 1e-9), 0.0, 0.80)
        stress_mpa *= (1.0 - degradation * 0.50)
        tangent_mpa *= (1.0 - degradation * 0.70)

    evidence_tags: list[str] = []
    if reversal:
        evidence_tags.append("reversal")
    if yielded:
        evidence_tags.append("yielded")
    if bauschinger_active:
        evidence_tags.append("bauschinger")
    if bar_buckled:
        evidence_tags.append("bar_buckled")
    if plastic_strain > 0.0:
        evidence_tags.append("plastic")
    if not evidence_tags:
        evidence_tags.append("monotonic")

    history_tag_parts: list[str] = []
    if reversal_count > 0:
        history_tag_parts.append("cyclic")
    if yielded:
        history_tag_parts.append("yielded")
    if bauschinger_active:
        history_tag_parts.append("bauschinger")
    if bar_buckled:
        history_tag_parts.append("buckled")
    if plastic_strain > 0.0:
        history_tag_parts.append("plastic")
    history_tag = "-".join(history_tag_parts) if history_tag_parts else "monotonic"

    restoring_state_tag = "+".join([history_tag, envelope.state_tag])
    next_state = SteelCyclicState(
        previous_strain=e,
        previous_stress_mpa=stress_mpa,
        last_increment_sign=increment_sign or int(state.last_increment_sign),
        reversal_count=reversal_count,
        max_tension_strain=max_tension_strain,
        max_compression_strain=max_compression_strain,
        back_stress_mpa=back_stress_mpa,
        plastic_strain=plastic_strain,
        yielded=yielded,
        bar_buckled=bar_buckled,
        history_tag=history_tag,
    )
    restoring = MaterialSnapshot(
        strain=e,
        stress_mpa=stress_mpa,
        tangent_mpa=tangent_mpa,
        state_tag=restoring_state_tag,
    )
    return SteelCyclicSnapshot(
        envelope=envelope,
        restoring=restoring,
        state=next_state,
        reversal_count=reversal_count,
        back_stress_mpa=back_stress_mpa,
        plastic_strain=plastic_strain,
        bauschinger_active=bauschinger_active,
        bar_buckled=bar_buckled,
        evidence_tags=tuple(evidence_tags),
    )


def steel_cyclic_probe(
    *,
    strain_history: tuple[float, ...] = (0.005, -0.008, 0.003, -0.012, 0.006),
    mat: SteelMaterial | None = None,
    probe_id: str = "steel_cyclic_probe_v1",
) -> dict:
    """Run a deterministic cyclic steel sequence and summarize Bauschinger evidence."""

    if mat is None:
        mat = SteelMaterial(fy_mpa=400.0, es_mpa=200000.0, hardening_ratio=0.015, fu_mpa=550.0)

    state = SteelCyclicState()
    snapshots: list[SteelCyclicSnapshot] = []
    for strain in strain_history:
        snapshot = steel_cyclic_response(strain, state=state, mat=mat)
        snapshots.append(snapshot)
        state = snapshot.state

    evidence_tags = sorted({tag for snapshot in snapshots for tag in snapshot.evidence_tags})
    reversal_count = max((snapshot.reversal_count for snapshot in snapshots), default=0)
    bauschinger_observed = any(snapshot.bauschinger_active for snapshot in snapshots)
    bar_buckled_observed = any(snapshot.bar_buckled for snapshot in snapshots)
    max_back_stress = max((abs(snapshot.back_stress_mpa) for snapshot in snapshots), default=0.0)
    max_plastic_strain = max((snapshot.plastic_strain for snapshot in snapshots), default=0.0)

    return {
        "probe_id": probe_id,
        "strain_history": strain_history,
        "evidence_tags": evidence_tags,
        "reversal_count": reversal_count,
        "bauschinger_observed": bauschinger_observed,
        "bar_buckled_observed": bar_buckled_observed,
        "max_back_stress_mpa": max_back_stress,
        "max_plastic_strain": max_plastic_strain,
    }


__all__ = [
    "MaterialSnapshot",
    "SteelCyclicSnapshot",
    "SteelCyclicState",
    "SteelMaterial",
    "steel_cyclic_probe",
    "steel_cyclic_response",
    "steel_response",
]
