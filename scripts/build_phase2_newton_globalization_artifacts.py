#!/usr/bin/env python3
"""Build Phase 2 Newton-Raphson/globalization seed artifacts for scalar nonlinear axial."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
    ScalarNonlinearAxialReference,
    expected_scalar_equilibrium_displacement,
    finite_difference_tangent_check,
    newton_raphson_scalar,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_newton_globalization_scalar_axial_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_newton_globalization_summary.json"
SCHEMA_VERSION = "phase2-newton-globalization-artifacts.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _problem_payload(problem: ScalarNonlinearAxialReference) -> dict[str, Any]:
    return {
        "case_id": problem.case_id,
        "truth_class": "analytic_truth",
        "model_kind": "scalar_nonlinear_axial_cubic_spring",
        "units": {"length": "m", "force": "kN"},
        "linear_stiffness_kn_per_m": problem.linear_stiffness_kn_per_m,
        "cubic_stiffness_kn_per_m3": problem.cubic_stiffness_kn_per_m3,
        "external_force_kn": problem.external_force_kn,
        "initial_displacement_m": problem.initial_displacement_m,
        "residual_contract": RESIDUAL_FORMULA,
        "claim_boundary": (
            "Deterministic scalar cubic-spring axial reference only. "
            "Not a full mesh, frame, shell, or production nonlinear solver."
        ),
    }


def _solution_payload(solution: Any) -> dict[str, Any]:
    return {
        "schema_version": "phase2-newton-globalization-scalar-result.v1",
        "status": solution.status,
        "contract_pass": bool(solution.metrics.get("contract_pass")),
        "case_id": solution.problem.case_id,
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": solution.metrics.get("tangent_definition"),
        "globalization": GLOBALIZATION,
        "matrix_backend": solution.metrics.get("matrix_backend"),
        "sparse_backend_used": solution.metrics.get("sparse_backend_used"),
        "metrics": solution.metrics,
        "convergence_history": solution.convergence_history,
        "line_search_history": solution.line_search_history,
        "unsupported_features": solution.unsupported_features,
        "warnings": solution.warnings,
        "regularization_used": solution.metrics.get("regularization_used"),
        "fallback_used": solution.metrics.get("fallback_used"),
        "g1_closure_claim": False,
        "nonlinear_newton_closure_claim": False,
        "claim_boundary": (
            "This records a scalar Newton-Raphson solve with explicit "
            "R=F_internal-F_external, consistent tangent, backtracking line search, "
            "and separate residual/increment gates for one cubic-spring axial case. "
            "It does not close general nonlinear equilibrium, frame/shell/material "
            "coupling, sparse production backends, full-mesh/full-load G1, or GPU/HIP parity."
        ),
    }


def build_newton_globalization_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    problem = ScalarNonlinearAxialReference()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    solution = newton_raphson_scalar(problem, config=config)
    expected_displacement_m = expected_scalar_equilibrium_displacement(problem)
    displacement_error = abs(solution.displacement_m - expected_displacement_m)
    tangent_check = finite_difference_tangent_check(problem, solution.displacement_m)
    equilibrium_residual = problem.residual(solution.displacement_m)
    metrics = solution.metrics

    residual_gate_passed = bool(metrics.get("residual_gate_passed"))
    increment_gate_passed = bool(metrics.get("increment_gate_passed"))
    line_search_used = bool(metrics.get("line_search_used"))
    line_search_step_count = int(metrics.get("line_search_step_count", 0))
    no_regularization_or_fallback = (
        metrics.get("regularization_used") is False and metrics.get("fallback_used") is False
    )
    tangent_gate_passed = bool(tangent_check["pass"])
    displacement_gate_passed = displacement_error <= 1.0e-10
    line_search_history_present = len(solution.line_search_history) > 0
    contract_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and residual_gate_passed
        and increment_gate_passed
        and line_search_used
        and line_search_history_present
        and line_search_step_count >= 1
        and no_regularization_or_fallback
        and tangent_gate_passed
        and displacement_gate_passed
        and metrics.get("residual_formula") == RESIDUAL_FORMULA
    )

    result_payload = _solution_payload(solution)
    result_payload["problem"] = _problem_payload(problem)
    result_payload["verification"] = {
        "expected_displacement_m": expected_displacement_m,
        "displacement_abs_error_m": displacement_error,
        "displacement_gate_passed": displacement_gate_passed,
        "equilibrium_residual_kn": equilibrium_residual,
        "tangent_finite_difference_check": tangent_check,
        "tangent_gate_passed": tangent_gate_passed,
    }

    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("src/structural_analysis/solvers/nonlinear/__init__.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "nonlinear_newton_closure_claim": False,
        "analysis_type": "nonlinear_static_scalar_seed",
        "truth_class": "analytic_truth",
        "case_id": problem.case_id,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": metrics.get("matrix_backend"),
        "sparse_backend_used": metrics.get("sparse_backend_used"),
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "line_search_used": line_search_used,
        "line_search_step_count": line_search_step_count,
        "tangent_gate_passed": tangent_gate_passed,
        "displacement_gate_passed": displacement_gate_passed,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "iteration_count": metrics.get("iteration_count"),
        "expected": {
            "displacement_m": expected_displacement_m,
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance": config.increment_tolerance,
        },
        "actual": {
            "displacement_m": solution.displacement_m,
            "relative_residual": metrics.get("relative_residual"),
            "final_increment_abs_m": metrics.get("final_increment_abs_m"),
            "residual_kn": metrics.get("residual_kn"),
        },
        "errors": {
            "displacement_abs_m": displacement_error,
        },
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_nonlinear_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "general_newton_jacobian_assembly_not_closed",
        ],
        "artifacts": {
            "scalar_axial_result": str(result_out),
            "summary": str(summary_out),
            "related_scalar_load_step_summary": str(
                PRODUCTIZATION / "phase2_nonlinear_load_step_summary.json"
            ),
        },
        "claim_boundary": (
            "This proves a deterministic scalar nonlinear axial reference can be solved "
            "with explicit Newton-Raphson residual R=F_internal-F_external, consistent "
            "tangent stiffness, backtracking line-search globalization, and separate "
            "residual/increment convergence gates without regularization or fallback "
            "false PASS. It does not close G1 full-mesh/full-load nonlinear equilibrium, "
            "general frame/shell/material coupling, sparse production matrix backends, "
            "or production GPU/HIP gates."
        ),
    }
    return {
        "result": result_payload,
        "summary": summary_payload,
    }


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


def check_newton_globalization_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_newton_globalization_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    targets = {
        "result": result_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_newton_globalization_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_newton_globalization_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_newton_globalization_mismatch:{key}"
    return True, "phase2_newton_globalization_consistent"


def write_newton_globalization_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_newton_globalization_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, path in {
        "result": result_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_newton_globalization_artifacts(
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 Newton globalization check: {message}")
        return 0 if ok else 1
    artifacts = write_newton_globalization_artifacts(
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 Newton globalization: "
        f"{summary['status']} | residual_gate={summary['residual_gate_passed']} | "
        f"increment_gate={summary['increment_gate_passed']} | "
        f"line_search={summary['line_search_used']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
