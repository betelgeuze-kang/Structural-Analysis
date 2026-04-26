#!/usr/bin/env python3
"""Nonlinear Lennard-Jones mapping kernel for plastic hinge surrogate.

Maps structural yield targets to a scaled 12-6 LJ potential and verifies that:
- yield is reached near target strain
- post-yield softening occurs with bond damage
- dissipated energy is positive
"""

from __future__ import annotations

from dataclasses import dataclass
import math

EPS = 1e-12
LJ_FORCE_MAX_COEFF = 2.396429261243986  # max |F| = coeff * epsilon / sigma
NATURAL_LJ_YIELD_STRAIN = 0.10868341796872152  # at x=7/26 for 12-6 LJ tensile branch


@dataclass
class LJMappingConfig:
    elastic_modulus_pa: float = 210e9
    yield_stress_pa: float = 355e6
    area_m2: float = 0.015
    gauge_length_m: float = 6.0
    damage_beta: float = 1.2
    strain_max_factor: float = 8.0
    points: int = 240
    softening_ratio_threshold: float = 0.97


@dataclass
class LJMappedParams:
    sigma_lj: float
    epsilon_lj: float
    target_yield_strain: float
    natural_lj_yield_strain: float
    strain_scale: float
    yield_force_n: float


def map_structural_to_lj(cfg: LJMappingConfig) -> LJMappedParams:
    e = max(float(cfg.elastic_modulus_pa), EPS)
    sigma_y = max(float(cfg.yield_stress_pa), EPS)
    area = max(float(cfg.area_m2), EPS)
    l0 = max(float(cfg.gauge_length_m), EPS)

    target_yield_strain = sigma_y / e
    strain_scale = max(1.0, NATURAL_LJ_YIELD_STRAIN / max(target_yield_strain, EPS))

    sigma_lj = l0 / (2.0 ** (1.0 / 6.0))
    yield_force_n = sigma_y * area

    # Chain rule: F_phys = strain_scale * F_lj(r_eff).
    epsilon_lj = (yield_force_n * sigma_lj) / (LJ_FORCE_MAX_COEFF * strain_scale)

    return LJMappedParams(
        sigma_lj=sigma_lj,
        epsilon_lj=epsilon_lj,
        target_yield_strain=target_yield_strain,
        natural_lj_yield_strain=NATURAL_LJ_YIELD_STRAIN,
        strain_scale=strain_scale,
        yield_force_n=yield_force_n,
    )


def _lj_force_potential(r: float, sigma: float, epsilon: float) -> tuple[float, float]:
    rr = max(r, EPS)
    sr = sigma / rr
    sr6 = sr**6
    sr12 = sr6 * sr6
    potential = 4.0 * epsilon * (sr12 - sr6)
    force = 24.0 * epsilon / rr * (2.0 * sr12 - sr6)  # +: repulsive, -: tensile
    return force, potential


def simulate_lj_plastic_hinge(cfg: LJMappingConfig) -> dict:
    params = map_structural_to_lj(cfg)

    l0 = max(float(cfg.gauge_length_m), EPS)
    yield_force = params.yield_force_n
    points = max(20, int(cfg.points))
    strain_max = params.target_yield_strain * max(float(cfg.strain_max_factor), 1.5)

    rows = []
    yielded = False
    yield_index = None
    yield_strain_observed = None

    alive_prev = 1.0
    dissipated_energy = 0.0
    prev_r = l0
    peak_force_before_yield = 0.0

    for i in range(points + 1):
        strain_phys = strain_max * i / points
        strain_eff = strain_phys * params.strain_scale
        r_eff = l0 * (1.0 + strain_eff)

        force_eff, potential_eff = _lj_force_potential(r_eff, params.sigma_lj, params.epsilon_lj)

        # Tensile force magnitude in physical coordinate
        tension_eff = max(0.0, -force_eff)
        tension_phys_raw = params.strain_scale * tension_eff

        if not yielded and tension_phys_raw >= yield_force:
            yielded = True
            yield_index = i
            yield_strain_observed = strain_phys

        if yielded:
            plastic_ratio = max(0.0, (strain_phys / max(params.target_yield_strain, EPS)) - 1.0)
            damage = 1.0 - math.exp(-float(cfg.damage_beta) * plastic_ratio)
            alive = max(0.0, 1.0 - damage)
        else:
            damage = 0.0
            alive = 1.0
            peak_force_before_yield = max(peak_force_before_yield, tension_phys_raw)

        tension_phys = alive * tension_phys_raw
        stress_phys = tension_phys / max(float(cfg.area_m2), EPS)

        dr = max(0.0, l0 * strain_phys - (prev_r - l0))
        # Phenomenological dissipation from bond weakening.
        dissipated_energy += max(0.0, (alive_prev - alive) * tension_phys_raw * dr)
        alive_prev = alive
        prev_r = l0 * (1.0 + strain_phys)

        rows.append(
            {
                "step": i,
                "strain": strain_phys,
                "stress_pa": stress_phys,
                "force_n": tension_phys,
                "force_n_raw": tension_phys_raw,
                "yielded": yielded,
                "damage": damage,
                "bond_alive": alive,
                "potential": max(0.0, potential_eff),
            }
        )

    post_forces = [r["force_n"] for r in rows[(yield_index + 1 if yield_index is not None else len(rows)) :]]
    post_peak = max(post_forces) if post_forces else 0.0
    softening_pass = (peak_force_before_yield > 0.0) and (
        post_peak <= float(cfg.softening_ratio_threshold) * peak_force_before_yield
    )

    if yield_index is not None and yield_strain_observed is not None:
        yield_strain_error_abs = abs(yield_strain_observed - params.target_yield_strain)
        yield_strain_pass = yield_strain_error_abs <= max(2e-4, 0.25 * params.target_yield_strain)
    else:
        yield_strain_error_abs = float("inf")
        yield_strain_pass = False

    dissipation_pass = dissipated_energy > 0.0

    checks = {
        "yield_detected": yield_index is not None,
        "yield_strain_pass": yield_strain_pass,
        "post_yield_softening_pass": softening_pass,
        "energy_dissipation_pass": dissipation_pass,
    }

    return {
        "config": {
            "elastic_modulus_pa": float(cfg.elastic_modulus_pa),
            "yield_stress_pa": float(cfg.yield_stress_pa),
            "area_m2": float(cfg.area_m2),
            "gauge_length_m": float(cfg.gauge_length_m),
            "damage_beta": float(cfg.damage_beta),
            "strain_max_factor": float(cfg.strain_max_factor),
            "points": int(points),
            "softening_ratio_threshold": float(cfg.softening_ratio_threshold),
        },
        "mapped_params": {
            "sigma_lj": params.sigma_lj,
            "epsilon_lj": params.epsilon_lj,
            "target_yield_strain": params.target_yield_strain,
            "natural_lj_yield_strain": params.natural_lj_yield_strain,
            "strain_scale": params.strain_scale,
            "yield_force_n": params.yield_force_n,
        },
        "checks": checks,
        "metrics": {
            "yield_index": yield_index,
            "yield_strain_observed": yield_strain_observed,
            "yield_strain_error_abs": yield_strain_error_abs,
            "peak_force_before_yield_n": peak_force_before_yield,
            "post_yield_peak_force_n": post_peak,
            "dissipated_energy_j": dissipated_energy,
        },
        "curve": rows,
    }
