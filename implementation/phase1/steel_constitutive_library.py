#!/usr/bin/env python3
"""Dedicated reduced-order steel constitutive helpers."""

from __future__ import annotations

from dataclasses import dataclass


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

    @property
    def eps_y(self) -> float:
        return float(self.fy_mpa) / max(float(self.es_mpa), 1e-9)


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
    state_tag = "plastic_hardening" if stress_abs < float(mat.fu_mpa) else "plastic_capped"
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=tangent, state_tag=state_tag)


__all__ = [
    "MaterialSnapshot",
    "SteelMaterial",
    "steel_response",
]
