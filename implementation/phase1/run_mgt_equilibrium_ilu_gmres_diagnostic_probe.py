#!/usr/bin/env python3
"""Diagnose ILU-GMRES breakdown on the equilibrium Newton tangent at lambda=0.05."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

import numpy as np
from scipy.sparse.linalg import LinearOperator, gmres, spilu

_PHASE1 = Path(__file__).resolve().parent
if str(_PHASE1) not in sys.path:
    sys.path.insert(0, str(_PHASE1))

from mgt_equilibrium_step_assembly import build_equilibrium_step_assembler
from mgt_sparse_linear_solver import (
    build_node_block_jacobi_preconditioner,
    solve_block_jacobi_gmres,
    solve_cpu_ilu_gmres,
    solve_host_ilu_device_gmres,
    solve_sparse_with_iterative_refinement,
)
from mgt_sparse_matrix_equilibration import symmetric_sqrt_diagonal_scaling
from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import _select_frame_elements
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _element_angle_array_from_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (
    DEFAULT_MGT,
    PRODUCTIZATION,
    _assemble_elastic_link_springs,
    _authored_support_restraints,
    _run_uncoarsened_parser,
)
from run_mgt_uncoarsened_boundary_pdelta_probe import _linear_tangent_warm_start_u


SCHEMA_VERSION = "mgt-equilibrium-ilu-gmres-diagnostic-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_equilibrium_ilu_gmres_diagnostic_probe.json"


def _json_float(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not np.isfinite(number):
        return None
    return number


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return _json_float(value)
    if isinstance(value, (int, np.integer, str, bool)) or value is None:
        return value
    if isinstance(value, np.ndarray):
        return _sanitize_for_json(value.tolist())
    return value


def _classify_gmres_info(info: int) -> str:
    if int(info) == 0:
        return "gmres_exit_success"
    if int(info) > 0:
        return "gmres_maxiter_not_converged"
    return "gmres_illegal_input_or_breakdown"


def _classify_attempt(
    *,
    ilu_factorization_ok: bool,
    gmres_info: int | None,
    residual_inf: float | None,
    threshold: float,
    error_excerpt: str | None = None,
) -> str:
    if not ilu_factorization_ok:
        return "ilu_factorization_failed"
    if gmres_info is None:
        return "gmres_exception"
    if int(gmres_info) < 0:
        return "gmres_breakdown"
    if int(gmres_info) > 0:
        return "gmres_maxiter_exceeded"
    if residual_inf is None or not np.isfinite(residual_inf):
        return "gmres_nonfinite_residual"
    if float(residual_inf) > float(threshold):
        return "gmres_residual_above_threshold"
    return "converged"


def _matrix_diagnostics(k_ff: Any) -> dict[str, Any]:
    csr = k_ff.tocsr()
    diag = np.asarray(csr.diagonal(), dtype=np.float64)
    abs_diag = np.abs(diag)
    zero_diag_count = int(np.sum(abs_diag <= 1.0e-15))
    return {
        "shape": [int(csr.shape[0]), int(csr.shape[1])],
        "nnz": int(csr.nnz),
        "diag_abs_min": float(np.min(abs_diag)) if abs_diag.size else 0.0,
        "diag_abs_max": float(np.max(abs_diag)) if abs_diag.size else 0.0,
        "diag_abs_mean": float(np.mean(abs_diag)) if abs_diag.size else 0.0,
        "zero_diag_count": zero_diag_count,
        "symmetry_max_abs_diff": float(
            np.max(np.abs((csr - csr.T).data))
        )
        if csr.nnz
        else 0.0,
    }


def _run_explicit_attempt(
    *,
    label: str,
    k_ff: Any,
    rhs: np.ndarray,
    free_global_dofs: np.ndarray,
    drop_tol: float,
    fill_factor: float,
    restart: int,
    max_iterations: int,
    tolerance_abs: float,
    tolerance_rel: float,
    use_block_jacobi: bool,
    equilibrate: bool = False,
) -> dict[str, Any]:
    from mgt_sparse_matrix_equilibration import unscale_solution

    started = time.perf_counter()
    k_orig = k_ff.tocsr()
    n = int(k_orig.shape[0])
    rhs_np = np.asarray(rhs, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    rhs_l2 = float(np.linalg.norm(rhs_np)) if rhs_np.size else 0.0
    threshold = max(float(tolerance_abs), float(tolerance_rel) * max(rhs_inf, 1.0))
    k_work = k_orig
    rhs_work = rhs_np
    scale = np.ones(n, dtype=np.float64)
    equilibration_meta: dict[str, Any] = {"applied": False}
    if equilibrate:
        k_work, rhs_work, scale, equilibration_meta = symmetric_sqrt_diagonal_scaling(k_orig, rhs_np)
    row: dict[str, Any] = {
        "label": label,
        "drop_tol": float(drop_tol),
        "fill_factor": float(fill_factor),
        "restart": int(restart),
        "max_iterations": int(max_iterations),
        "tolerance_abs": float(tolerance_abs),
        "tolerance_rel": float(tolerance_rel),
        "threshold_n": threshold,
        "rhs_inf_n": rhs_inf,
        "rhs_l2_n": rhs_l2,
        "use_block_jacobi": bool(use_block_jacobi),
        "equilibrate": bool(equilibrate),
        "equilibration": equilibration_meta,
        "ilu_factorization_ok": False,
        "ilu_factorization_seconds": None,
        "gmres_info": None,
        "gmres_info_class": None,
        "residual_inf_n": None,
        "residual_rel_inf": None,
        "residual_rel_l2": None,
        "converged": False,
        "breakdown_category": "pending",
        "solve_seconds": None,
    }
    factor_started = time.perf_counter()
    try:
        ilu = spilu(k_work.tocsc(), drop_tol=float(drop_tol), fill_factor=float(fill_factor))
    except Exception as exc:
        row["ilu_factorization_seconds"] = time.perf_counter() - factor_started
        row["error_excerpt"] = repr(exc)[:600]
        row["breakdown_category"] = _classify_attempt(
            ilu_factorization_ok=False,
            gmres_info=None,
            residual_inf=None,
            threshold=threshold,
        )
        row["solve_seconds"] = time.perf_counter() - started
        return row
    row["ilu_factorization_ok"] = True
    row["ilu_factorization_seconds"] = time.perf_counter() - factor_started

    def ilu_precondition(vector: np.ndarray) -> np.ndarray:
        return np.asarray(ilu.solve(np.asarray(vector, dtype=np.float64)), dtype=np.float64)

    if use_block_jacobi and int(free_global_dofs.size) == n:
        free = np.asarray(free_global_dofs, dtype=np.int64)
        block_inverse, block_meta = build_node_block_jacobi_preconditioner(
            k_work,
            free_global_dofs=free,
        )
        row["block_jacobi_build_seconds"] = block_meta.get("build_seconds")
        row["block_jacobi_singular_block_count"] = block_meta.get("singular_block_count")

        def precondition(vector: np.ndarray) -> np.ndarray:
            return np.asarray(block_inverse @ ilu_precondition(vector), dtype=np.float64)
    else:
        precondition = ilu_precondition

    m_op = LinearOperator((n, n), matvec=precondition, dtype=np.float64)
    gmres_started = time.perf_counter()
    try:
        solution_scaled, info = gmres(
            k_work,
            rhs_work,
            M=m_op,
            rtol=float(tolerance_rel),
            atol=float(tolerance_abs),
            maxiter=int(max_iterations),
            restart=int(restart),
        )
    except Exception as exc:
        row["gmres_seconds"] = time.perf_counter() - gmres_started
        row["error_excerpt"] = repr(exc)[:600]
        row["breakdown_category"] = "gmres_exception"
        row["solve_seconds"] = time.perf_counter() - started
        return row
    row["gmres_seconds"] = time.perf_counter() - gmres_started
    row["gmres_info"] = int(info)
    row["gmres_info_class"] = _classify_gmres_info(int(info))
    solution = unscale_solution(np.asarray(solution_scaled, dtype=np.float64), scale)
    residual = np.asarray(k_orig @ solution - rhs_np, dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else float("inf")
    row["residual_inf_n"] = _json_float(residual_inf)
    row["residual_rel_inf"] = _json_float(residual_inf / max(rhs_inf, 1.0))
    row["residual_rel_l2"] = _json_float(
        float(np.linalg.norm(residual)) / max(rhs_l2, 1.0) if residual.size else float("inf")
    )
    row["converged"] = bool(np.isfinite(residual_inf) and residual_inf <= threshold)
    row["breakdown_category"] = _classify_attempt(
        ilu_factorization_ok=True,
        gmres_info=int(info),
        residual_inf=residual_inf,
        threshold=threshold,
    )
    row["solve_seconds"] = time.perf_counter() - started
    return row


def run_mgt_equilibrium_ilu_gmres_diagnostic_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    load_scale: float = 0.05,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    if not mgt_path.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    with tempfile.TemporaryDirectory(prefix="mgt-ilu-gmres-diagnostic-") as temp_name:
        work_dir = Path(temp_name)
        _roundtrip_json, roundtrip_npz, parser_report, parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=work_dir,
        )
        props = load_mgt_section_material_properties(mgt_path)
        section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
        material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
        plate_thickness_props = (
            props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
        )
        beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
        with np.load(roundtrip_npz, allow_pickle=False) as archive:
            node_id = np.asarray(archive["node_id"], dtype=np.int64)
            node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
            edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
            elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
            elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
            elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
            elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
            elem_angle_deg = (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(props, elem_id)
            )
            conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
            conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

        frame_elements, frame_select_meta = _select_frame_elements(
            node_xyz=node_xyz,
            edge_index=edge_index,
            elem_id=elem_id,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )
        node_index = {int(raw_node_id): int(index) for index, raw_node_id in enumerate(node_id.tolist())}
        restrained, support_meta = _authored_support_restraints(
            constraints=constraints,
            node_index=node_index,
        )
        spring_stiffness, spring_meta = _assemble_elastic_link_springs(
            links=elastic_links,
            node_index=node_index,
            dof_count=int(node_xyz.shape[0]) * DOF_PER_NODE,
            stiffness_scale_to_si=stiffness_scale_to_si,
        )
        base_axial_forces = _component_gravity_axial_forces(
            elements=frame_elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
        )
        warm_start_u, warm_start_meta = _linear_tangent_warm_start_u(
            load_scale=float(load_scale),
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            restrained=restrained,
            base_axial_forces=base_axial_forces,
            base_frame_gravity_scale=frame_gravity_load_scale,
        )
        assemble_residual, step_meta = build_equilibrium_step_assembler(
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=float(load_scale),
            restrained=restrained,
        )
        stiffness, _f_ext, free, residual, _rhs, tangent_meta = assemble_residual(warm_start_u)
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        k_ff = stiffness[free, :][:, free].tocsc()
        rhs = -np.asarray(residual, dtype=np.float64)
        free_global = np.asarray(free, dtype=np.int64)
        matrix_meta = _matrix_diagnostics(k_ff)

        explicit_attempts = [
            _run_explicit_attempt(
                label="equilibrated_block_jacobi",
                k_ff=k_ff,
                rhs=rhs,
                free_global_dofs=free_global,
                drop_tol=1.0e-4,
                fill_factor=40.0,
                restart=80,
                max_iterations=200,
                tolerance_abs=1.0e-6,
                tolerance_rel=1.0e-4,
                use_block_jacobi=True,
                equilibrate=True,
            ),
            _run_explicit_attempt(
                label="equilibrated_ilu_only",
                k_ff=k_ff,
                rhs=rhs,
                free_global_dofs=free_global,
                drop_tol=1.0e-4,
                fill_factor=60.0,
                restart=80,
                max_iterations=200,
                tolerance_abs=1.0e-6,
                tolerance_rel=1.0e-4,
                use_block_jacobi=False,
                equilibrate=True,
            ),
        ]

        wrapper_attempts: list[dict[str, Any]] = []
        block_row = solve_block_jacobi_gmres(
            k_ff,
            rhs,
            free_global_dofs=free_global,
            tolerance_abs=1.0e-6,
            tolerance_rel=1.0e-4,
            max_iterations=800,
            restart=80,
            equilibrate=True,
        )
        wrapper_attempts.append(
            {
                "label": "solve_block_jacobi_gmres_wrapper",
                **{
                    key: block_row.get(key)
                    for key in (
                        "backend",
                        "preconditioner",
                        "converged",
                        "gmres_info",
                        "residual_inf_n",
                        "breakdown",
                        "error_excerpt",
                        "solve_seconds",
                        "equilibration",
                    )
                },
                "breakdown_category": block_row.get("breakdown")
                or ("converged" if bool(block_row.get("converged")) else "gmres_residual_above_threshold"),
            }
        )
        cpu_row = solve_cpu_ilu_gmres(
            k_ff,
            rhs,
            tolerance_abs=1.0e-6,
            tolerance_rel=1.0e-4,
            max_iterations=800,
            restart=80,
            drop_tol=1.0e-5,
            fill_factor=40.0,
            free_global_dofs=free_global,
        )
        wrapper_attempts.append(
            {
                "label": "solve_cpu_ilu_gmres_wrapper",
                **{
                    key: cpu_row.get(key)
                    for key in (
                        "backend",
                        "preconditioner",
                        "converged",
                        "gmres_info",
                        "residual_inf_n",
                        "breakdown",
                        "error_excerpt",
                        "solve_seconds",
                    )
                },
                "breakdown_category": cpu_row.get("breakdown")
                or (
                    "converged"
                    if bool(cpu_row.get("converged"))
                    else _classify_attempt(
                        ilu_factorization_ok="solution" in cpu_row,
                        gmres_info=cpu_row.get("gmres_info"),
                        residual_inf=cpu_row.get("residual_inf_n"),
                        threshold=max(1.0e-6, 1.0e-4 * max(float(np.max(np.abs(rhs))), 1.0)),
                    )
                ),
            }
        )
        try:
            host_row = solve_host_ilu_device_gmres(
                k_ff,
                rhs,
                tolerance_abs=1.0e-6,
                tolerance_rel=1.0e-4,
                max_iterations=800,
                restart=80,
                drop_tol=1.0e-6,
                fill_factor=40.0,
                require_convergence=False,
            )
            wrapper_attempts.append(
                {
                    "label": "solve_host_ilu_device_gmres_wrapper",
                    **{
                        key: host_row.get(key)
                        for key in (
                            "backend",
                            "preconditioner",
                            "converged",
                            "gmres_info",
                            "residual_inf_n",
                            "breakdown",
                            "error_excerpt",
                            "solve_seconds",
                            "device",
                        )
                    },
                    "breakdown_category": host_row.get("breakdown")
                    or (
                        "converged"
                        if bool(host_row.get("converged"))
                        else "gmres_residual_above_threshold"
                    ),
                }
            )
        except Exception as exc:
            wrapper_attempts.append(
                {
                    "label": "solve_host_ilu_device_gmres_wrapper",
                    "breakdown_category": "host_wrapper_exception",
                    "error_excerpt": repr(exc)[:600],
                }
            )

        reg_solution, reg_value, reg_residual = solve_sparse_with_iterative_refinement(
            k_ff,
            rhs,
            regularization_factor=1.0e-12,
        )
        reg_rhs_inf = float(np.max(np.abs(rhs))) if rhs.size else 0.0
        fallback_row = {
            "label": "regularized_spsolve_refined",
            "regularization": float(reg_value),
            "residual_inf_n": float(reg_residual),
            "residual_rel_inf": float(reg_residual) / max(reg_rhs_inf, 1.0),
            "breakdown_category": "fallback_not_ilu_gmres",
        }

        category_counts: dict[str, int] = {}
        for attempt in explicit_attempts:
            category = str(attempt.get("breakdown_category") or "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1

        best_explicit = min(
            explicit_attempts,
            key=lambda row: float(row.get("residual_inf_n") or float("inf")),
        )
        ilu_factorization_failures = sum(
            1 for row in explicit_attempts if row.get("breakdown_category") == "ilu_factorization_failed"
        )
        gmres_maxiter_failures = sum(
            1
            for row in explicit_attempts
            if row.get("breakdown_category") == "gmres_maxiter_exceeded"
        )
        gmres_threshold_failures = sum(
            1
            for row in explicit_attempts
            if row.get("breakdown_category") == "gmres_residual_above_threshold"
        )
        any_converged = any(bool(row.get("converged")) for row in explicit_attempts)

        if ilu_factorization_failures == len(explicit_attempts):
            primary_breakdown = "ilu_factorization_failed"
        elif any_converged:
            primary_breakdown = "some_configurations_converged"
        elif gmres_maxiter_failures > 0 and gmres_threshold_failures == 0:
            primary_breakdown = "gmres_maxiter_exceeded"
        elif gmres_threshold_failures > 0:
            primary_breakdown = "gmres_residual_above_threshold"
        else:
            primary_breakdown = "mixed_or_unknown"

        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "ready",
            "load_scale": float(load_scale),
            "warm_start_meta": warm_start_meta,
            "equilibrium_state": {
                "residual_inf_n": residual_inf,
                "free_dof_count": int(free.size),
                "tangent_meta": tangent_meta,
                "stiffness_unit_audit": tangent_meta.get("stiffness_unit_audit"),
            },
            "matrix_diagnostics": matrix_meta,
            "explicit_attempts": explicit_attempts,
            "wrapper_attempts": wrapper_attempts,
            "fallback_solver": fallback_row,
            "summary": {
                "primary_breakdown": primary_breakdown,
                "ilu_factorization_failure_count": ilu_factorization_failures,
                "gmres_maxiter_failure_count": gmres_maxiter_failures,
                "gmres_threshold_failure_count": gmres_threshold_failures,
                "explicit_converged_count": sum(1 for row in explicit_attempts if row.get("converged")),
                "breakdown_category_counts": category_counts,
                "best_explicit_label": best_explicit.get("label"),
                "best_explicit_residual_inf_n": best_explicit.get("residual_inf_n"),
                "best_explicit_breakdown_category": best_explicit.get("breakdown_category"),
                "fallback_residual_inf_n": fallback_row["residual_inf_n"],
                "newton_rhs_inf_n": float(np.max(np.abs(rhs))) if rhs.size else 0.0,
            },
            "frame_select_meta": frame_select_meta,
            "support_meta": support_meta,
            "spring_meta": spring_meta,
            "equilibrium_step_meta": step_meta,
            "parser_report_contract_pass": bool(parser_report.get("contract_pass")),
            "parser_run": parser_run,
            "runtime_metrics": {"total_seconds": time.perf_counter() - started},
            "claim_boundary": (
                "Diagnostic-only receipt for equilibrium tangent ILU-GMRES at lambda=0.05 warm-start. "
                "Classifies ILU factorization failure vs GMRES maxiter vs residual-above-threshold."
            ),
        }

    payload = _sanitize_for_json(payload)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--load-scale", type=float, default=0.05)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = run_mgt_equilibrium_ilu_gmres_diagnostic_probe(
        mgt_path=args.mgt_path,
        load_scale=float(args.load_scale),
        output_json=args.output_json,
    )
    summary = payload.get("summary") or {}
    print(
        "equilibrium-ilu-gmres-diagnostic:",
        payload.get("status"),
        f"primary={summary.get('primary_breakdown')}",
        f"best_residual={summary.get('best_explicit_residual_inf_n')}",
        "->",
        args.output_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
