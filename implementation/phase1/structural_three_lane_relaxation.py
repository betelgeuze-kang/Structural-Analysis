#!/usr/bin/env python3
"""Three-lane frame SoA structural relaxation helpers.

Goal:
- Replace time-burning mock loops with explicit force accumulation/integration
- Keep O(N) memory and compute characteristics for a three-lane frame proxy
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math

EPS = 1e-9


@dataclass
class ThreeLaneFrameSoA:
    node_count: int
    point_count: int
    x: array
    y: array
    z: array
    vx: array
    vy: array
    vz: array
    fx: array
    fy: array
    fz: array
    fixed: array
    center_idx: array
    positive_flange_idx: array
    negative_flange_idx: array
    spring_i: array
    spring_j: array
    spring_k: array
    spring_rest_length: array
    mass_per_point: float


def _fzeros(n: int) -> array:
    return array("f", [0.0]) * n


def _uzeros(n: int) -> array:
    return array("I", [0]) * n


def _bzeros(n: int) -> array:
    return array("B", [0]) * n


def build_three_lane_frame(
    node_count: int,
    story_pitch: float = 3.0,
    flange_offset: float = 0.18,
    mass_per_point: float = 2.0,
    k_web: float = 1_200.0,
    k_flange: float = 900.0,
    k_axial_ca: float = 1_500.0,
    k_axial_flange: float = 1_100.0,
    k_torsion_diag: float = 420.0,
) -> ThreeLaneFrameSoA:
    n = max(2, int(node_count))
    point_count = 3 * n

    x = _fzeros(point_count)
    y = _fzeros(point_count)
    z = _fzeros(point_count)
    vx = _fzeros(point_count)
    vy = _fzeros(point_count)
    vz = _fzeros(point_count)
    fx = _fzeros(point_count)
    fy = _fzeros(point_count)
    fz = _fzeros(point_count)
    fixed = _bzeros(point_count)

    center_idx = _uzeros(n)
    positive_flange_idx = _uzeros(n)
    negative_flange_idx = _uzeros(n)

    for i in range(n):
        ca = 3 * i
        sc = ca + 1
        cb = ca + 2
        center_idx[i] = ca
        positive_flange_idx[i] = sc
        negative_flange_idx[i] = cb

        height = i * story_pitch
        x[ca] = 0.0
        y[ca] = 0.0
        z[ca] = height

        x[sc] = 0.0
        y[sc] = flange_offset
        z[sc] = height

        x[cb] = 0.0
        y[cb] = -flange_offset
        z[cb] = height

    # Fixed support at base node (all three points).
    fixed[int(center_idx[0])] = 1
    fixed[int(positive_flange_idx[0])] = 1
    fixed[int(negative_flange_idx[0])] = 1

    spring_i = array("I")
    spring_j = array("I")
    spring_k = array("f")
    spring_rest_length = array("f")

    def add_spring(i: int, j: int, k: float, rest_length: float) -> None:
        spring_i.append(int(i))
        spring_j.append(int(j))
        spring_k.append(float(k))
        spring_rest_length.append(float(rest_length))

    web_len = flange_offset
    flange_len = 2.0 * flange_offset
    diag_len = math.sqrt(story_pitch * story_pitch + (2.0 * flange_offset) * (2.0 * flange_offset))

    for i in range(n):
        ca = int(center_idx[i])
        sc = int(positive_flange_idx[i])
        cb = int(negative_flange_idx[i])

        # Intra-node center-positive-negative flange coupling.
        add_spring(ca, sc, k_web, web_len)
        add_spring(ca, cb, k_web, web_len)
        add_spring(sc, cb, k_flange, flange_len)

        if i == 0:
            continue

        pca = int(center_idx[i - 1])
        psc = int(positive_flange_idx[i - 1])
        pcb = int(negative_flange_idx[i - 1])

        # Axial continuity per point lane.
        add_spring(pca, ca, k_axial_ca, story_pitch)
        add_spring(psc, sc, k_axial_flange, story_pitch)
        add_spring(pcb, cb, k_axial_flange, story_pitch)

        # Diagonal torsion-like constraints (warping surrogate).
        add_spring(psc, cb, k_torsion_diag, diag_len)
        add_spring(pcb, sc, k_torsion_diag, diag_len)

    return ThreeLaneFrameSoA(
        node_count=n,
        point_count=point_count,
        x=x,
        y=y,
        z=z,
        vx=vx,
        vy=vy,
        vz=vz,
        fx=fx,
        fy=fy,
        fz=fz,
        fixed=fixed,
        center_idx=center_idx,
        positive_flange_idx=positive_flange_idx,
        negative_flange_idx=negative_flange_idx,
        spring_i=spring_i,
        spring_j=spring_j,
        spring_k=spring_k,
        spring_rest_length=spring_rest_length,
        mass_per_point=float(mass_per_point),
    )


def _reset_forces(soa: ThreeLaneFrameSoA) -> None:
    for i in range(soa.point_count):
        soa.fx[i] = 0.0
        soa.fy[i] = 0.0
        soa.fz[i] = 0.0


def accumulate_internal_forces(soa: ThreeLaneFrameSoA) -> float:
    _reset_forces(soa)
    potential = 0.0

    for spring in range(len(soa.spring_i)):
        i = int(soa.spring_i[spring])
        j = int(soa.spring_j[spring])
        k = float(soa.spring_k[spring])
        rest_length = float(soa.spring_rest_length[spring])

        dx = float(soa.x[j] - soa.x[i])
        dy = float(soa.y[j] - soa.y[i])
        dz = float(soa.z[j] - soa.z[i])
        dist2 = dx * dx + dy * dy + dz * dz
        dist = math.sqrt(dist2 + EPS)

        stretch = dist - rest_length
        force_scale = k * stretch / dist

        fx = force_scale * dx
        fy = force_scale * dy
        fz = force_scale * dz

        soa.fx[i] += fx
        soa.fy[i] += fy
        soa.fz[i] += fz

        soa.fx[j] -= fx
        soa.fy[j] -= fy
        soa.fz[j] -= fz

        potential += 0.5 * k * stretch * stretch

    return potential


def apply_lateral_load(soa: ThreeLaneFrameSoA, base_force: float, ramp: float) -> float:
    force_total = 0.0
    denom = max(soa.node_count - 1, 1)
    scale = float(base_force) * float(max(0.0, min(1.0, ramp)))

    for node in range(soa.node_count):
        ca = int(soa.center_idx[node])
        h = node / denom
        # Top floors receive larger lateral demand.
        f = scale * (0.35 + 0.65 * h)
        soa.fx[ca] += f
        force_total += abs(f)

    return force_total


def max_unbalanced_force(soa: ThreeLaneFrameSoA) -> float:
    m = 0.0
    for i in range(soa.point_count):
        if int(soa.fixed[i]) == 1:
            continue
        fx = float(soa.fx[i])
        fy = float(soa.fy[i])
        fz = float(soa.fz[i])
        fn = math.sqrt(fx * fx + fy * fy + fz * fz)
        if fn > m:
            m = fn
    return m


def integrate_explicit_damped(soa: ThreeLaneFrameSoA, dt: float, damping: float) -> float:
    ke = 0.0
    inv_mass = 1.0 / max(float(soa.mass_per_point), EPS)
    damp = max(0.0, float(damping))

    for i in range(soa.point_count):
        if int(soa.fixed[i]) == 1:
            soa.vx[i] = 0.0
            soa.vy[i] = 0.0
            soa.vz[i] = 0.0
            continue

        ax = float(soa.fx[i]) * inv_mass - damp * float(soa.vx[i])
        ay = float(soa.fy[i]) * inv_mass - damp * float(soa.vy[i])
        az = float(soa.fz[i]) * inv_mass - damp * float(soa.vz[i])

        soa.vx[i] += dt * ax
        soa.vy[i] += dt * ay
        soa.vz[i] += dt * az

        soa.x[i] += dt * float(soa.vx[i])
        soa.y[i] += dt * float(soa.vy[i])
        soa.z[i] += dt * float(soa.vz[i])

        v2 = float(soa.vx[i]) ** 2 + float(soa.vy[i]) ** 2 + float(soa.vz[i]) ** 2
        ke += 0.5 * float(soa.mass_per_point) * v2

    return ke


def free_dof_count(soa: ThreeLaneFrameSoA) -> int:
    free_points = 0
    for i in range(soa.point_count):
        if int(soa.fixed[i]) == 0:
            free_points += 1
    return 3 * free_points


def run_relaxation_case(
    node_count: int,
    base_force: float,
    max_steps: int,
    tol: float,
    decay_hint: float,
    dt: float = 0.002,
) -> dict:
    soa = build_three_lane_frame(node_count=node_count)
    dof = max(free_dof_count(soa), 1)

    # decay_hint from legacy scaffold maps to damping here.
    damping = max(0.6, min(4.0, (1.0 - float(decay_hint)) * 45.0))

    converged = False
    steps = 0
    residual_norm = 1.0
    max_force = 0.0
    kinetic = 0.0
    potential = 0.0
    temperature = 0.0
    applied_load_l1 = 0.0

    for step in range(1, max_steps + 1):
        ramp = min(1.0, step / 20.0)
        potential = accumulate_internal_forces(soa)
        applied_load_l1 = apply_lateral_load(soa, base_force=float(base_force), ramp=ramp)

        max_force = max_unbalanced_force(soa)
        # Normalize by actually injected load magnitude (L1) for a scale-aware residual.
        residual_norm = max_force / max(applied_load_l1, EPS)

        kinetic = integrate_explicit_damped(soa, dt=float(dt), damping=damping)
        temperature = (2.0 * kinetic) / dof

        steps = step
        if step > 10 and residual_norm <= tol:
            converged = True
            break

    return {
        "steps": int(steps),
        "converged": bool(converged),
        "final_force_norm": float(residual_norm),
        "max_unbalanced_force": float(max_force),
        "kinetic_energy": float(kinetic),
        "potential_energy": float(potential),
        "system_temperature": float(temperature),
        "applied_load_l1": float(applied_load_l1),
        "node_count": int(node_count),
        "point_count": int(soa.point_count),
        "spring_count": int(len(soa.spring_i)),
        "model": "three_lane_frame_soa",
    }


def run_workload_pass(node_count: int, steps: int = 3) -> dict:
    soa = build_three_lane_frame(node_count=max(2, int(node_count)))
    acc = 0.0
    max_force = 0.0
    for i in range(max(1, int(steps))):
        ramp = min(1.0, (i + 1) / max(1, steps))
        p = accumulate_internal_forces(soa)
        apply_lateral_load(soa, base_force=140.0, ramp=ramp)
        max_force = max_unbalanced_force(soa)
        k = integrate_explicit_damped(soa, dt=0.0015, damping=1.8)
        acc += p + k + 0.01 * max_force

    return {
        "work_scalar": float(acc),
        "node_count": int(node_count),
        "point_count": int(soa.point_count),
        "spring_count": int(len(soa.spring_i)),
        "max_unbalanced_force": float(max_force),
        "model": "three_lane_frame_soa",
    }
