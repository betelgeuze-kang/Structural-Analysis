#!/usr/bin/env python3
"""RC/composite nonlinear material modifiers (cracking/creep/bond-slip).

This module provides lightweight constitutive modifiers that can be injected
into frame-level nonlinear runners without changing solver interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from rc_constitutive_library import (
    BondSlipMaterial,
    ConcreteMaterial,
    bond_slip_response,
    concrete_response,
    estimate_creep_shrinkage_multiplier,
)


@dataclass(frozen=True)
class RCCompositeMaterialConfig:
    cracking_strain: float = 2.2e-4
    cracking_stiffness_drop: float = 0.35
    creep_rate_per_hour: float = 0.008
    creep_stiffness_drop_cap: float = 0.25
    bond_slip_ratio_ref: float = 0.003
    bond_slip_strength_drop_cap: float = 0.30
    confinement_gain: float = 0.08


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.minimum(1.0, np.maximum(0.0, x))


def _safe_positive(x: np.ndarray, floor: float) -> np.ndarray:
    return np.maximum(float(floor), x)


def apply_rc_composite_profile(
    *,
    story_k_n_per_m: np.ndarray,
    story_yield_drift_m: np.ndarray,
    story_mass_kg: np.ndarray,
    story_h_m: np.ndarray,
    drift_ratio_proxy: np.ndarray,
    elapsed_hours: float,
    cycle_count: int,
    cfg: RCCompositeMaterialConfig | None = None,
) -> dict:
    """Apply RC/composite degradation modifiers to stiffness/yield profiles.

    Returns a dictionary with modified arrays and diagnostic indices.
    """
    if cfg is None:
        cfg = RCCompositeMaterialConfig()

    k = np.asarray(story_k_n_per_m, dtype=np.float64).copy()
    y = np.asarray(story_yield_drift_m, dtype=np.float64).copy()
    m = np.asarray(story_mass_kg, dtype=np.float64).copy()
    h = np.asarray(story_h_m, dtype=np.float64).copy()
    drift = np.asarray(drift_ratio_proxy, dtype=np.float64).copy()

    n = int(k.shape[0])
    if n == 0:
        return {
            "story_k_n_per_m": k,
            "story_yield_drift_m": y,
            "story_mass_kg": m,
            "indices": {
                "cracking_index_mean": 0.0,
                "creep_index_mean": 0.0,
                "bond_slip_index_mean": 0.0,
            },
        }

    strain_proxy = np.abs(drift) * np.maximum(h, 1e-9)
    tension_strain_proxy = np.abs(drift) * np.linspace(0.85, 1.15, num=n, dtype=np.float64)
    compression_strain_proxy = -0.60 * tension_strain_proxy

    concrete_mat = ConcreteMaterial(
        fc_mpa=30.0,
        eps_t_crack=float(cfg.cracking_strain),
        confinement_gain=1.0 + float(cfg.confinement_gain),
    )
    bond_mat = BondSlipMaterial(
        slip_y_mm=max(0.10, 0.30 * float(cfg.bond_slip_ratio_ref) * 1000.0),
        slip_u_mm=max(0.50, 1.60 * float(cfg.bond_slip_ratio_ref) * 1000.0),
        residual_ratio=max(0.10, 1.0 - float(cfg.bond_slip_strength_drop_cap)),
    )

    crack_samples = [concrete_response(float(eps), concrete_mat) for eps in tension_strain_proxy]
    comp_samples = [concrete_response(float(eps), concrete_mat) for eps in compression_strain_proxy]
    cracking_ratio = _clip01(strain_proxy / max(cfg.cracking_strain, 1e-9))
    cracking_drop = float(cfg.cracking_stiffness_drop) * np.power(cracking_ratio, 0.7)

    hours = max(0.0, float(elapsed_hours))
    creep_multiplier = estimate_creep_shrinkage_multiplier(
        age_days=max(1.0, hours / 24.0),
        relative_humidity=0.62,
        member_size_mm=650.0,
    )
    creep_index = _clip01((1.0 - math.exp(-float(cfg.creep_rate_per_hour) * hours)) * max(1.0, creep_multiplier))
    creep_drop = min(float(cfg.creep_stiffness_drop_cap), float(cfg.creep_stiffness_drop_cap) * float(creep_index))

    slip_mm = np.abs(drift) * np.maximum(h, 1e-9) * 1000.0 * 0.18
    cycle_gain = 1.0 - math.exp(-max(0, int(cycle_count)) / 80.0)
    bond_samples = [bond_slip_response(float(val), bond_mat) for val in slip_mm]
    slip_ratio = _clip01(np.abs(drift) / max(cfg.bond_slip_ratio_ref, 1e-9))
    bond_slip_index = _clip01(0.6 * slip_ratio + 0.4 * cycle_gain)
    bond_slip_drop = float(cfg.bond_slip_strength_drop_cap) * np.power(bond_slip_index, 0.8)

    comp_damage = np.asarray(
        [
            0.0
            if snap.state_tag == "compression_hardening"
            else _clip01(abs(float(eps)) / max(float(concrete_mat.eps_cu), 1e-9))
            for eps, snap in zip(compression_strain_proxy, comp_samples)
        ],
        dtype=np.float64,
    )

    confinement = float(cfg.confinement_gain) * np.linspace(1.0, 0.65, num=n, dtype=np.float64)
    stiffness_scale = _safe_positive(1.0 - cracking_drop - creep_drop + confinement, 0.10)
    yield_scale = _safe_positive(1.0 - 0.65 * bond_slip_drop + 0.5 * confinement, 0.12)

    k_mod = _safe_positive(k * stiffness_scale, 1e3)
    y_mod = _safe_positive(y * yield_scale, 1e-6)
    m_mod = _safe_positive(m, 1.0)

    return {
        "story_k_n_per_m": k_mod,
        "story_yield_drift_m": y_mod,
        "story_mass_kg": m_mod,
        "indices": {
            "cracking_index_mean": float(np.mean(cracking_ratio)),
            "creep_index_mean": float(np.mean(np.full(n, creep_index, dtype=np.float64))),
            "bond_slip_index_mean": float(np.mean(bond_slip_index)),
            "compression_damage_mean": float(np.mean(comp_damage)),
            "tension_softening_story_count": int(sum(1 for snap in crack_samples if snap.state_tag == "tension_softening")),
            "bond_softening_story_count": int(sum(1 for snap in bond_samples if snap.state_tag == "bond_softening")),
            "stiffness_scale_min": float(np.min(stiffness_scale)),
            "stiffness_scale_mean": float(np.mean(stiffness_scale)),
            "yield_scale_min": float(np.min(yield_scale)),
            "yield_scale_mean": float(np.mean(yield_scale)),
        },
    }
