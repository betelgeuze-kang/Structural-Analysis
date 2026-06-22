#!/usr/bin/env python3
"""Build Phase 2 narrow nonlinear mesh/load-step convergence suite artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.nonlinear_static import (  # noqa: E402
    finite_difference_assembled_jacobian_check,
    mesh_problem_with_scaled_external_load,
    mesh_series_force_equilibrium_check,
    refined_strain_cubic_axial_chain_mesh_problem,
    solve_axial_chain_mesh,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    VECTOR_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_mesh_load_step_convergence_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_mesh_load_step_convergence_summary.json"
SCHEMA_VERSION = "phase2-mesh-load-step-convergence-artifacts.v1"
ELEMENT_COUNTS = (1, 2, 4)
LOAD_PARTITION_COUNTS = (1, 2, 4)
TIP_DISPLACEMENT_TOLERANCE_M = 1.0e-10
RESIDUAL_TOLERANCE_KN = 1.0e-10


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _step_factors(partition_count: int) -> tuple[float, ...]:
    return tuple(index / partition_count for index in range(1, partition_count + 1))


def _tip_node(problem: Any) -> int:
    return max(node_index for node_index, _ in problem.external_forces_kn)


def _row_has_guarded_solver_usage(row: dict[str, Any]) -> bool:
    return bool(
        row.get("regularization_used") is True
        or row.get("fallback_used") is True
        or any(
            step.get("regularization_used") is True or step.get("fallback_used") is True
            for step in row.get("steps", [])
            if isinstance(step, dict)
        )
    )


def _solve_partition(
    *,
    element_count: int,
    partition_count: int,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    base_problem = refined_strain_cubic_axial_chain_mesh_problem(
        element_count=element_count,
    )
    displacements = tuple(base_problem.initial_displacements_m)
    steps: list[dict[str, Any]] = []
    final_solution = None
    final_state = None
    for step_index, load_factor in enumerate(_step_factors(partition_count), start=1):
        step_problem = mesh_problem_with_scaled_external_load(
            base_problem,
            load_factor=load_factor,
            initial_displacements_m=displacements,
        )
        solution, state = solve_axial_chain_mesh(step_problem, config=config)
        metrics = solution.metrics
        tip_displacement_m = float(state.displacements_m[_tip_node(base_problem)])
        steps.append(
            {
                "step_index": step_index,
                "load_factor": load_factor,
                "status": solution.status,
                "contract_pass": bool(metrics.get("contract_pass")),
                "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
                "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
                "iteration_count": int(metrics.get("iteration_count", 0)),
                "residual_norm_kn": float(metrics.get("residual_norm", 0.0)),
                "final_increment_abs_m": float(metrics.get("final_increment_abs_m", 0.0)),
                "tip_displacement_m": tip_displacement_m,
                "regularization_used": metrics.get("regularization_used"),
                "fallback_used": metrics.get("fallback_used"),
            }
        )
        displacements = tuple(state.displacements_m.tolist())
        final_solution = solution
        final_state = state
    assert final_solution is not None
    assert final_state is not None
    final_metrics = final_solution.metrics
    jacobian_check = finite_difference_assembled_jacobian_check(
        base_problem,
        final_solution.free_displacements_m,
    )
    series_check = mesh_series_force_equilibrium_check(final_state)
    final_residual_inf_norm = float(np.linalg.norm(final_state.residual_kn, ord=np.inf))
    row_regularization_used = bool(
        any(step["regularization_used"] is True for step in steps)
        or final_metrics.get("regularization_used") is True
    )
    row_fallback_used = bool(
        any(step["fallback_used"] is True for step in steps)
        or final_metrics.get("fallback_used") is True
    )
    row_pass = (
        all(step["contract_pass"] for step in steps)
        and bool(final_metrics.get("contract_pass"))
        and bool(jacobian_check["pass"])
        and bool(series_check["pass"])
        and not row_regularization_used
        and not row_fallback_used
        and final_residual_inf_norm <= RESIDUAL_TOLERANCE_KN
    )
    return {
        "case_id": base_problem.case_id,
        "element_count": element_count,
        "node_count": base_problem.node_count,
        "partition_count": partition_count,
        "step_factors": list(_step_factors(partition_count)),
        "status": "ready" if row_pass else "blocked",
        "contract_pass": row_pass,
        "steps": steps,
        "final_tip_displacement_m": float(final_state.displacements_m[_tip_node(base_problem)]),
        "final_residual_inf_norm_kn": final_residual_inf_norm,
        "final_iteration_count": int(final_metrics.get("iteration_count", 0)),
        "final_residual_gate_passed": bool(final_metrics.get("residual_gate_passed")),
        "final_increment_gate_passed": bool(final_metrics.get("increment_gate_passed")),
        "tangent_gate_passed": bool(jacobian_check["pass"]),
        "series_force_gate_passed": bool(series_check["pass"]),
        "series_force_spread_kn": float(series_check.get("force_spread_kn", 0.0)),
        "regularization_used": row_regularization_used,
        "fallback_used": row_fallback_used,
    }


def _grid_rows(config: NewtonRaphsonConfig) -> list[dict[str, Any]]:
    return [
        _solve_partition(
            element_count=element_count,
            partition_count=partition_count,
            config=config,
        )
        for element_count in ELEMENT_COUNTS
        for partition_count in LOAD_PARTITION_COUNTS
    ]


def build_phase2_mesh_load_step_convergence_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    config = NewtonRaphsonConfig(
        residual_tolerance=RESIDUAL_TOLERANCE_KN,
        increment_tolerance=1.0e-12,
        max_iterations=25,
        matrix_backend=VECTOR_MATRIX_BACKEND,
    )
    rows = _grid_rows(config)
    tip_values = [row["final_tip_displacement_m"] for row in rows]
    tip_spread = max(tip_values) - min(tip_values)
    partition_spreads: dict[str, float] = {}
    for element_count in ELEMENT_COUNTS:
        element_tip_values = [
            row["final_tip_displacement_m"]
            for row in rows
            if row["element_count"] == element_count
        ]
        partition_spreads[str(element_count)] = max(element_tip_values) - min(element_tip_values)
    regularization_used = any(row["regularization_used"] is True for row in rows)
    fallback_used = any(row["fallback_used"] is True for row in rows)
    guarded_solver_usage_present = any(_row_has_guarded_solver_usage(row) for row in rows)
    mesh_partition_contract_pass = (
        all(row["contract_pass"] for row in rows)
        and all(row["tangent_gate_passed"] for row in rows)
        and all(row["series_force_gate_passed"] for row in rows)
        and not regularization_used
        and not fallback_used
        and not guarded_solver_usage_present
        and tip_spread <= TIP_DISPLACEMENT_TOLERANCE_M
        and all(value <= TIP_DISPLACEMENT_TOLERANCE_M for value in partition_spreads.values())
    )
    result_payload = {
        "schema_version": "phase2-mesh-load-step-convergence-result.v1",
        "status": "ready" if mesh_partition_contract_pass else "blocked",
        "contract_pass": mesh_partition_contract_pass,
        "analysis_type": "nonlinear_static_mesh_load_step_convergence_seed",
        "truth_class": "analytic_1d_material_mesh_convergence_truth",
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": VECTOR_MATRIX_BACKEND,
        "element_counts": list(ELEMENT_COUNTS),
        "load_partition_counts": list(LOAD_PARTITION_COUNTS),
        "rows": rows,
        "tip_displacements_m": tip_values,
        "tip_displacement_spread_m": tip_spread,
        "partition_tip_spread_by_element_count_m": partition_spreads,
        "tip_displacement_tolerance_m": TIP_DISPLACEMENT_TOLERANCE_M,
        "residual_tolerance_kn": RESIDUAL_TOLERANCE_KN,
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "guarded_solver_usage_present": guarded_solver_usage_present,
        "g1_closure_claim": False,
        "mesh_load_step_convergence_closure_claim": False,
        "full_mesh_closure_claim": False,
        "claim_boundary": (
            "This is a narrow 1D strain-cubic axial material mesh/load-step convergence "
            "seed over a small element-count and load-partition grid. It does not close "
            "general frame/shell meshes, representative full-mesh/full-load nonlinear "
            "equilibrium, production sparse/GPU backends, or G1."
        ),
    }
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("scripts/build_phase2_mesh_load_step_convergence_artifacts.py"),
                Path("tests/test_build_phase2_mesh_load_step_convergence_artifacts.py"),
                Path("scripts/verify_quality_gate.py"),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": mesh_partition_contract_pass,
        "analysis_type": result_payload["analysis_type"],
        "truth_class": result_payload["truth_class"],
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": VECTOR_MATRIX_BACKEND,
        "element_counts": list(ELEMENT_COUNTS),
        "load_partition_counts": list(LOAD_PARTITION_COUNTS),
        "case_count": len(rows),
        "all_rows_contract_pass": all(row["contract_pass"] for row in rows),
        "all_tangent_gates_passed": all(row["tangent_gate_passed"] for row in rows),
        "all_series_force_gates_passed": all(row["series_force_gate_passed"] for row in rows),
        "tip_displacement_spread_m": tip_spread,
        "partition_tip_spread_by_element_count_m": partition_spreads,
        "tip_displacement_tolerance_m": TIP_DISPLACEMENT_TOLERANCE_M,
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "guarded_solver_usage_present": guarded_solver_usage_present,
        "g1_closure_claim": False,
        "mesh_load_step_convergence_closure_claim": False,
        "full_mesh_closure_claim": False,
        "blockers_remaining": [
            "general_frame_shell_mesh_load_step_convergence_not_closed",
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "general_sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "broad_material_newton_breadth_not_closed",
        ],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "related_material_mesh_newton_summary": str(
                PRODUCTIZATION / "phase2_material_mesh_newton_summary.json"
            ),
        },
        "claim_boundary": result_payload["claim_boundary"],
    }
    return {"result": result_payload, "summary": summary_payload}


def write_phase2_mesh_load_step_convergence_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, Path]:
    artifacts = build_phase2_mesh_load_step_convergence_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for path, payload in (
        (result_out, artifacts["result"]),
        (summary_out, artifacts["summary"]),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payload), encoding="utf-8")
    return {"result": result_out, "summary": summary_out}


def check_phase2_mesh_load_step_convergence_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_mesh_load_step_convergence_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, path in (("result", result_out), ("summary", summary_out)):
        if not path.exists():
            return False, f"phase2_mesh_load_step_convergence_missing:{path.as_posix()}"
        try:
            actual = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return False, f"phase2_mesh_load_step_convergence_unreadable:{path.as_posix()}:{exc}"
        if _strip_volatile(actual) != _strip_volatile(expected[key]):
            return False, f"phase2_mesh_load_step_convergence_mismatch:{key}"
    return True, "phase2_mesh_load_step_convergence_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase2_mesh_load_step_convergence_artifacts(
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 mesh/load-step convergence check: {message}")
        return 0 if ok else 1
    paths = write_phase2_mesh_load_step_convergence_artifacts(
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = _read_json(paths["summary"])
    print(
        "Phase 2 mesh/load-step convergence seed: "
        f"{summary['status']} | cases={summary['case_count']} | "
        f"spread={summary['tip_displacement_spread_m']:.3e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
