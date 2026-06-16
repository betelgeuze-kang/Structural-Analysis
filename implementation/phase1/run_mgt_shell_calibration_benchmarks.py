#!/usr/bin/env python3
"""Run calibrated shell benchmark receipts for the MGT shell formulation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, eye
from scipy.sparse.linalg import spsolve

from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE, _node_dofs
from run_mgt_surface_membrane_tangent import _triangle_membrane_stiffness
from run_mgt_surface_shell_bending_tangent import _triangle_shell_bending_stiffness


SCHEMA_VERSION = "mgt-shell-calibration-benchmarks.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _relative_error(actual: float, expected: float) -> float:
    return abs(float(actual) - float(expected)) / max(abs(float(expected)), 1.0e-30)


def _membrane_patch_benchmark() -> dict[str, Any]:
    e = 30.0e9
    nu = 0.20
    thickness = 0.20
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    result = _triangle_membrane_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=thickness,
    )
    if result is None:
        return {"case_id": "membrane_constant_strain_patch", "ready": False, "error": "degenerate_triangle"}
    stiffness, area = result
    eps_x = 1.0e-4
    eps_y = 2.0e-5
    gamma_xy = 3.0e-5
    displacement: list[float] = []
    for x, y, _z in points:
        u = eps_x * x + 0.5 * gamma_xy * y
        v = eps_y * y + 0.5 * gamma_xy * x
        displacement.extend([u, v, 0.0])
    u_vec = np.asarray(displacement, dtype=np.float64)
    energy = 0.5 * float(u_vec @ stiffness @ u_vec)
    dmat = e * thickness / (1.0 - nu**2) * np.asarray(
        [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]],
        dtype=np.float64,
    )
    strain = np.asarray([eps_x, eps_y, gamma_xy], dtype=np.float64)
    expected = 0.5 * float(area) * float(strain @ dmat @ strain)
    rel = _relative_error(energy, expected)
    return {
        "case_id": "membrane_constant_strain_patch",
        "ready": bool(rel <= 1.0e-10),
        "formulation": "constant_strain_triangle_membrane",
        "reference": "closed_form_plane_stress_constant_strain_energy",
        "energy_j": energy,
        "expected_energy_j": expected,
        "relative_error": rel,
        "threshold": 1.0e-10,
        "area_m2": float(area),
    }


def _membrane_rigid_body_benchmark() -> dict[str, Any]:
    e = 30.0e9
    nu = 0.20
    thickness = 0.20
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    result = _triangle_membrane_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=thickness,
    )
    if result is None:
        return {"case_id": "membrane_rigid_body_modes", "ready": False, "error": "degenerate_triangle"}
    stiffness, _area = result
    modes: list[np.ndarray] = []
    for axis in range(3):
        vec = np.zeros(9, dtype=np.float64)
        vec[axis::3] = 1.0
        modes.append(vec)
    omega = 1.0e-4
    rot = np.zeros(9, dtype=np.float64)
    for idx, (x, y, _z) in enumerate(points):
        rot[3 * idx] = -omega * y
        rot[3 * idx + 1] = omega * x
    modes.append(rot)
    residuals = [float(np.max(np.abs(stiffness @ mode))) for mode in modes]
    scale = max(float(np.max(np.abs(stiffness.diagonal()))), 1.0)
    normalized = [value / scale for value in residuals]
    max_normalized = max(normalized)
    return {
        "case_id": "membrane_rigid_body_modes",
        "ready": bool(max_normalized <= 1.0e-12),
        "formulation": "constant_strain_triangle_membrane",
        "reference": "zero_internal_force_for_translation_and_in_plane_rotation",
        "mode_count": len(modes),
        "max_residual": max(residuals),
        "max_normalized_residual": max_normalized,
        "threshold": 1.0e-12,
    }


def _shell_transverse_shear_patch_benchmark() -> dict[str, Any]:
    e = 30.0e9
    nu = 0.20
    thickness = 0.20
    gamma_xz = 1.0e-4
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    result = _triangle_shell_bending_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=thickness,
    )
    if result is None:
        return {"case_id": "shell_transverse_shear_patch", "ready": False, "error": "degenerate_triangle"}
    stiffness, area = result
    displacement: list[float] = []
    for x, _y, _z in points:
        displacement.extend([0.0, 0.0, gamma_xz * x, 0.0, 0.0, 0.0])
    u_vec = np.asarray(displacement, dtype=np.float64)
    energy = 0.5 * float(u_vec @ stiffness @ u_vec)
    shear_modulus = e / (2.0 * (1.0 + nu))
    expected = 0.5 * float(area) * (5.0 / 6.0) * shear_modulus * thickness * gamma_xz**2
    rel = _relative_error(energy, expected)
    return {
        "case_id": "shell_transverse_shear_patch",
        "ready": bool(rel <= 1.0e-10),
        "formulation": "mindlin_cst_transverse_shear",
        "reference": "closed_form_constant_transverse_shear_energy",
        "energy_j": energy,
        "expected_energy_j": expected,
        "relative_error": rel,
        "threshold": 1.0e-10,
        "area_m2": float(area),
    }


def _shell_zero_shear_rotation_benchmark() -> dict[str, Any]:
    e = 30.0e9
    nu = 0.20
    thickness = 0.20
    slope = 1.0e-4
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    result = _triangle_shell_bending_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=thickness,
    )
    if result is None:
        return {"case_id": "shell_zero_shear_rigid_slope", "ready": False, "error": "degenerate_triangle"}
    stiffness, _area = result
    displacement: list[float] = []
    for x, _y, _z in points:
        displacement.extend([0.0, 0.0, slope * x, 0.0, slope, 0.0])
    u_vec = np.asarray(displacement, dtype=np.float64)
    energy = abs(0.5 * float(u_vec @ stiffness @ u_vec))
    scale = max(float(np.max(np.abs(stiffness.diagonal()))), 1.0) * max(float(np.max(np.abs(u_vec))) ** 2, 1.0e-30)
    normalized = energy / scale
    return {
        "case_id": "shell_zero_shear_rigid_slope",
        "ready": bool(normalized <= 1.0e-12),
        "formulation": "mindlin_cst_bending_shear",
        "reference": "zero_energy_for_linear_w_with_matching_rotation",
        "energy_j_abs": energy,
        "normalized_energy": normalized,
        "threshold": 1.0e-12,
    }


def _clamped_square_plate_benchmark(mesh_divisions: int = 24) -> dict[str, Any]:
    started = time.perf_counter()
    n = int(mesh_divisions)
    side = 4.0
    e = 30.0e9
    nu = 0.20
    thickness = 0.20
    pressure = 10_000.0
    node_xyz = np.asarray(
        [(side * i / n, side * j / n, 0.0) for j in range(n + 1) for i in range(n + 1)],
        dtype=np.float64,
    )
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)

    def node(i: int, j: int) -> int:
        return j * (n + 1) + i

    tri_count = 0
    for j in range(n):
        for i in range(n):
            for tri in (
                (node(i, j), node(i + 1, j), node(i + 1, j + 1)),
                (node(i, j), node(i + 1, j + 1), node(i, j + 1)),
            ):
                result = _triangle_shell_bending_stiffness(
                    points=node_xyz[list(tri)],
                    e_n_per_m2=e,
                    poisson=nu,
                    thickness_m=thickness,
                )
                if result is None:
                    continue
                ke, area = result
                tri_count += 1
                dofs = tuple(dof for nd in tri for dof in _node_dofs(nd))
                for nd in tri:
                    f_ext[_node_dofs(nd)[2]] += pressure * area / 3.0
                for a, gi in enumerate(dofs):
                    for b, gj in enumerate(dofs):
                        rows.append(gi)
                        cols.append(gj)
                        vals.append(float(ke[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(f_ext.size, f_ext.size)).tocsc()
    restrained: set[int] = set()
    for j in range(n + 1):
        for i in range(n + 1):
            if i in {0, n} or j in {0, n}:
                restrained.update(_node_dofs(node(i, j)))
    active = np.asarray(np.where(np.abs(stiffness.diagonal()) > 1.0e-9)[0], dtype=np.int64)
    free = np.asarray([idx for idx in active.tolist() if idx not in restrained], dtype=np.int64)
    k_free = stiffness[free, :][:, free].tocsc()
    diag = np.asarray(k_free.diagonal(), dtype=np.float64)
    regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
    k_reg = k_free + eye(k_free.shape[0], format="csc") * regularization
    solve_started = time.perf_counter()
    u_free = np.asarray(spsolve(k_reg, f_ext[free]), dtype=np.float64)
    solve_s = time.perf_counter() - solve_started
    residual = np.asarray(k_reg @ u_free - f_ext[free], dtype=np.float64)
    u = np.zeros_like(f_ext)
    u[free] = u_free
    center_node = node(n // 2, n // 2)
    center_w = float(u[_node_dofs(center_node)[2]])
    flexural_rigidity = e * thickness**3 / (12.0 * (1.0 - nu**2))
    expected_w = 0.00126 * pressure * side**4 / flexural_rigidity
    rel = _relative_error(center_w, expected_w)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    rhs_inf = float(np.max(np.abs(f_ext[free]))) if free.size else 0.0
    return {
        "case_id": "clamped_square_plate_uniform_pressure",
        "ready": bool(rel <= 0.15 and residual_inf <= 1.0e-6),
        "formulation": "assembled_mindlin_cst_shell_plate",
        "reference": "classical_clamped_square_plate_center_deflection_alpha_0p00126",
        "mesh_divisions": n,
        "node_count": int(node_xyz.shape[0]),
        "triangle_count": tri_count,
        "free_dof_count": int(free.size),
        "center_deflection_m": center_w,
        "expected_center_deflection_m": expected_w,
        "relative_error": rel,
        "threshold": 0.15,
        "residual_inf_n": residual_inf,
        "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "regularization": regularization,
        "assembly_plus_solve_seconds": time.perf_counter() - started,
        "solve_seconds": solve_s,
    }


def run_mgt_shell_calibration_benchmarks(
    *,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    cases = [
        _membrane_patch_benchmark(),
        _membrane_rigid_body_benchmark(),
        _shell_transverse_shear_patch_benchmark(),
        _shell_zero_shear_rotation_benchmark(),
        _clamped_square_plate_benchmark(),
    ]
    ready_cases = sum(1 for row in cases if bool(row.get("ready")))
    ready = ready_cases == len(cases)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "shell_calibration_benchmarks_ready": ready,
        "membrane_patch_benchmark_ready": all(
            bool(row.get("ready")) for row in cases if str(row.get("case_id")).startswith("membrane_")
        ),
        "shell_patch_benchmark_ready": all(
            bool(row.get("ready")) for row in cases if str(row.get("case_id")).startswith("shell_")
        ),
        "plate_deflection_benchmark_ready": bool(cases[-1].get("ready")),
        "case_count": len(cases),
        "ready_case_count": ready_cases,
        "cases": cases,
        "claim_boundary": (
            "Calibrates the current CST membrane plus Mindlin-type shell bending/shear implementation "
            "against constant-strain, rigid-mode, transverse-shear, and clamped square plate analytical "
            "benchmarks. This is a shell formulation calibration receipt, not opening/local-axis handling, "
            "higher-order shell breadth, material nonlinear shell behavior, or full-load nonlinear closure."
        ),
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_shell_calibration",
            "total_seconds": time.perf_counter() - started,
        },
        "blockers": [] if ready else [str(row.get("case_id")) for row in cases if not row.get("ready")],
    }
    out = output_json or PRODUCTIZATION / "mgt_shell_calibration_benchmarks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_shell_calibration_benchmarks.json")
    args = parser.parse_args()
    payload = run_mgt_shell_calibration_benchmarks(output_json=args.output_json)
    plate_case = next(
        (row for row in payload.get("cases", []) if row.get("case_id") == "clamped_square_plate_uniform_pressure"),
        {},
    )
    print(
        "mgt-shell-calibration-benchmarks: "
        f"status={payload['status']} ready={payload.get('ready_case_count')}/{payload.get('case_count')} "
        f"plate_rel_error={plate_case.get('relative_error')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
