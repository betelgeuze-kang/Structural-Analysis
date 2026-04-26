#!/usr/bin/env python3
"""Minimal bond-slip interface helpers for steel/composite interaction checks."""

from __future__ import annotations

from dataclasses import dataclass

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

    @property
    def peak_force_kn(self) -> float:
        return float(self.k0_kn_per_mm) * float(self.slip_y_mm)


@dataclass(frozen=True)
class BondSlipInteractionSnapshot:
    slip: float
    interaction_ratio: float
    state_tag: str


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


__all__ = [
    "BondSlipInteractionSnapshot",
    "BondSlipMaterial",
    "bond_slip_interaction_response",
    "bond_slip_response",
]
