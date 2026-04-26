#!/usr/bin/env python3
"""Utilities for spatio-temporal structural dataset generation and loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Iterable


G = 9.80665
EPS = 1e-12

TOPOLOGIES = ["rahmen", "truss", "outrigger", "wall-frame"]
MATERIALS = ["steel", "rc", "composite"]
OOD_TAGS = ["in_distribution", "ood_topology", "ood_hazard", "ood_combined"]


@dataclass(frozen=True)
class CaseConfig:
    seq_len: int
    dt: float
    coupling_k: float


def _choose_split(rng: random.Random) -> str:
    p = rng.random()
    if p < 0.7:
        return "train"
    if p < 0.85:
        return "val"
    return "test"


def _choose_ood(topology: str, amp_scale: float, rng: random.Random) -> str:
    if topology in {"outrigger", "wall-frame"} and amp_scale > 1.2:
        return "ood_combined"
    if topology in {"outrigger", "wall-frame"}:
        return "ood_topology"
    if amp_scale > 1.15:
        return "ood_hazard"
    return "in_distribution"


def _build_edges(node_count: int, topology: str, rng: random.Random) -> list[list[int]]:
    edges: set[tuple[int, int]] = set()
    for i in range(node_count - 1):
        edges.add((i, i + 1))
    if topology in {"rahmen", "wall-frame", "outrigger"}:
        for i in range(node_count - 2):
            if rng.random() < 0.45:
                edges.add((i, i + 2))
    if topology in {"truss", "outrigger"}:
        for i in range(node_count - 3):
            if rng.random() < 0.35:
                edges.add((i, i + 3))
    out = [[u, v] for u, v in sorted(edges)]
    return out


def _build_faces(node_count: int, topology: str, rng: random.Random) -> list[list[int]]:
    faces: list[list[int]] = []
    for i in range(node_count - 2):
        if topology in {"wall-frame", "outrigger"}:
            if rng.random() < 0.7:
                faces.append([i, i + 1, i + 2])
        elif rng.random() < 0.35:
            faces.append([i, i + 1, i + 2])
    return faces


def generate_ground_motion(seq_len: int, dt: float, amp_scale: float, rng: random.Random) -> list[float]:
    phi1 = rng.uniform(0.0, 2.0 * math.pi)
    phi2 = rng.uniform(0.0, 2.0 * math.pi)
    phi3 = rng.uniform(0.0, 2.0 * math.pi)
    f1 = rng.uniform(0.6, 2.2)
    f2 = rng.uniform(2.8, 6.0)
    f3 = rng.uniform(7.5, 10.5)
    gm: list[float] = []
    for i in range(seq_len):
        t = i * dt
        v = (
            0.34 * math.exp(-0.028 * t) * math.sin(2.0 * math.pi * f1 * t + phi1)
            + 0.22 * math.exp(-0.036 * t) * math.sin(2.0 * math.pi * f2 * t + phi2)
            + 0.08 * math.exp(-0.14 * max(0.0, t - 7.0)) * math.sin(2.0 * math.pi * f3 * t + phi3)
        )
        gm.append(max(-0.95, min(0.95, amp_scale * v)))
    return gm


def _neighbors(node_count: int, edges: list[list[int]]) -> list[list[int]]:
    out = [[] for _ in range(node_count)]
    for u, v in edges:
        if u == v:
            continue
        out[u].append(v)
        out[v].append(u)
    return out


def simulate_dynamic_response(
    node_features: list[list[float]],
    edges: list[list[int]],
    ground_motion_g: list[float],
    cfg: CaseConfig,
) -> tuple[list[list[float]], dict]:
    n = len(node_features)
    t_len = len(ground_motion_g)
    nbr = _neighbors(n, edges)

    m = [max(100.0, float(f[0])) for f in node_features]
    k = [max(1e4, float(f[1])) for f in node_features]
    c = [max(10.0, float(f[2])) for f in node_features]
    h = [float(f[3]) for f in node_features]

    u = [0.0 for _ in range(n)]
    v = [0.0 for _ in range(n)]
    a = [0.0 for _ in range(n)]
    response: list[list[float]] = []

    peak_disp = 0.0
    peak_shear = 0.0
    max_residual = 0.0
    input_force_scale = 0.0

    for t in range(t_len):
        ag = float(ground_motion_g[t]) * G
        force_l1 = 0.0

        # Explicit damped integration with neighbor coupling.
        for i in range(n):
            ext = -m[i] * ag * (0.9 + 0.35 * h[i])
            coupling = 0.0
            if nbr[i]:
                ui = u[i]
                coupling = float(cfg.coupling_k) * sum(ui - u[j] for j in nbr[i])
            int_force = c[i] * v[i] + k[i] * u[i] + coupling
            a[i] = (ext - int_force) / m[i]
            v[i] += float(cfg.dt) * a[i]
            u[i] += float(cfg.dt) * v[i]

            residual = m[i] * a[i] + int_force - ext
            max_residual = max(max_residual, abs(residual))
            force_l1 += abs(ext)
            peak_disp = max(peak_disp, abs(u[i]))

        response.append(u[:])
        shear = sum(abs(k[i] * u[i]) for i in range(n)) / 1000.0
        peak_shear = max(peak_shear, shear)
        input_force_scale = max(input_force_scale, force_l1)

    eq_residual = max_residual / max(input_force_scale, 1.0)
    metrics = {
        "max_disp_m": float(peak_disp),
        "peak_base_shear_kN": float(peak_shear),
        "equilibrium_residual": float(eq_residual),
    }
    return response, metrics


def build_random_case(case_id: str, cfg: CaseConfig, rng: random.Random, hard_bias: float = 0.0) -> dict:
    topology = rng.choice(TOPOLOGIES)
    material = rng.choice(MATERIALS)
    node_count = rng.randint(18, 72)
    amp_scale = rng.uniform(0.75, 1.45 + hard_bias)
    split = _choose_split(rng)
    edges = _build_edges(node_count, topology, rng)
    faces = _build_faces(node_count, topology, rng)

    material_scales = {
        "steel": (1.0, 1.0, 1.0),
        "rc": (1.15, 0.82, 1.2),
        "composite": (1.08, 1.12, 1.05),
    }[material]
    torsion_base = 1.22 if topology in {"outrigger", "wall-frame"} else 1.0

    node_features: list[list[float]] = []
    for i in range(node_count):
        h = i / max(1, node_count - 1)
        mass = (800.0 + 250.0 * rng.random()) * material_scales[0]
        stiff = (6.0e4 + 5.0e4 * rng.random()) * material_scales[1]
        damp = (240.0 + 160.0 * rng.random()) * material_scales[2]
        torsion = torsion_base * (0.8 + 0.5 * rng.random())
        node_features.append([mass, stiff, damp, h, torsion])

    gm = generate_ground_motion(cfg.seq_len, cfg.dt, amp_scale=amp_scale, rng=rng)
    response, metrics = simulate_dynamic_response(
        node_features=node_features,
        edges=edges,
        ground_motion_g=gm,
        cfg=cfg,
    )

    eq_res = float(metrics["equilibrium_residual"])
    max_disp = float(metrics["max_disp_m"])
    peak_shear = float(metrics["peak_base_shear_kN"])
    diff_score = 0.55 * eq_res + 0.30 * max_disp + 0.15 * (peak_shear / 1000.0)

    dead = 0.55 * peak_shear
    live = 0.25 * peak_shear
    wind = 0.42 * peak_shear * amp_scale
    seismic = 0.60 * peak_shear * amp_scale
    cap_margin = rng.uniform(1.18, 1.45)
    capacity = cap_margin * max(
        1.2 * dead + 1.6 * live,
        1.2 * dead + wind + live,
        0.9 * dead + wind,
        1.2 * dead + seismic + live,
    )

    return {
        "case_id": case_id,
        "split": split,
        "topology_type": topology,
        "material_type": material,
        "ood_tag": _choose_ood(topology, amp_scale, rng),
        "torsion_sensitive": bool(topology in {"outrigger", "wall-frame"} and sum(f[4] for f in node_features) / node_count > 1.15),
        "seq_len": int(cfg.seq_len),
        "dt": float(cfg.dt),
        "node_count": int(node_count),
        "node_features": node_features,
        "edges": edges,
        "faces": faces,
        "ground_motion_g": gm,
        "response_u": response,
        "physics_params": {
            "coupling_k": float(cfg.coupling_k),
            "simulator": "building_explicit_v1",
        },
        "metrics": metrics,
        "difficulty_score": float(diff_score),
        "demand_capacity": {
            "dead_kN": float(dead),
            "live_kN": float(live),
            "wind_kN": float(wind),
            "seismic_kN": float(seismic),
            "capacity_kN": float(capacity),
        },
    }


def mutate_hard_case(source: dict, cfg: CaseConfig, new_case_id: str, rng: random.Random) -> dict:
    topology = source["topology_type"]
    material = source["material_type"]
    node_count = int(source["node_count"])
    node_features = [[float(v) for v in row] for row in source["node_features"]]

    for row in node_features:
        row[1] *= rng.uniform(0.87, 1.06)  # stiffness perturbation
        row[2] *= rng.uniform(0.92, 1.15)  # damping perturbation
        row[4] *= rng.uniform(1.02, 1.28)  # torsion gain

    gm_src = [float(v) for v in source["ground_motion_g"]]
    amp = rng.uniform(1.10, 1.35)
    gm = [max(-0.98, min(0.98, amp * v + rng.uniform(-0.015, 0.015))) for v in gm_src]
    edges = [[int(u), int(v)] for u, v in source["edges"]]
    faces = [[int(i), int(j), int(k)] for i, j, k in source["faces"]]

    if rng.random() < 0.45 and node_count > 6:
        u = rng.randint(0, node_count - 4)
        v = min(node_count - 1, u + rng.randint(2, 5))
        if u != v:
            edges.append([u, v])
    if rng.random() < 0.35 and node_count > 8:
        i = rng.randint(0, node_count - 4)
        faces.append([i, i + 1, i + 3])

    response, metrics = simulate_dynamic_response(
        node_features=node_features,
        edges=edges,
        ground_motion_g=gm,
        cfg=cfg,
    )
    eq_res = float(metrics["equilibrium_residual"])
    max_disp = float(metrics["max_disp_m"])
    peak_shear = float(metrics["peak_base_shear_kN"])
    diff_score = 0.6 * eq_res + 0.25 * max_disp + 0.15 * (peak_shear / 1000.0)

    dead = 0.55 * peak_shear
    live = 0.25 * peak_shear
    wind = 0.46 * peak_shear * amp
    seismic = 0.66 * peak_shear * amp
    capacity = float(source["demand_capacity"]["capacity_kN"]) * rng.uniform(0.95, 1.05)

    return {
        "case_id": new_case_id,
        "split": source["split"],
        "topology_type": topology,
        "material_type": material,
        "ood_tag": "ood_combined",
        "torsion_sensitive": True,
        "seq_len": int(cfg.seq_len),
        "dt": float(cfg.dt),
        "node_count": int(node_count),
        "node_features": node_features,
        "edges": edges,
        "faces": faces,
        "ground_motion_g": gm,
        "response_u": response,
        "physics_params": {
            "coupling_k": float(cfg.coupling_k),
            "simulator": "building_explicit_v1",
        },
        "metrics": metrics,
        "difficulty_score": float(diff_score),
        "demand_capacity": {
            "dead_kN": float(dead),
            "live_kN": float(live),
            "wind_kN": float(wind),
            "seismic_kN": float(seismic),
            "capacity_kN": float(capacity),
        },
    }


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True))
            f.write("\n")


def load_jsonl(path: Path, max_cases: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if max_cases is not None and len(rows) >= max_cases:
                break
    return rows
