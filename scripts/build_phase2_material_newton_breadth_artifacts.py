#!/usr/bin/env python3
"""Build Phase 2 material-Newton breadth seed artifacts for scalar constitutive laws."""

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
    ScalarAxialEquilibriumProblem,
    ScalarBilinearHardeningAxialReference,
    ScalarNonlinearAxialReference,
    expected_scalar_equilibrium_displacement,
    finite_difference_tangent_check,
    newton_raphson_scalar,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_LAWS_OUT = PRODUCTIZATION / "phase2_material_newton_breadth_scalar_axial_laws.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_material_newton_breadth_summary.json"
SCHEMA_VERSION = "phase2-material-newton-breadth-artifacts.v1"
DISPLACEMENT_TOLERANCE_M = 1.0e-10


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _problem_payload(problem: ScalarAxialEquilibriumProblem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": problem.case_id,
        "truth_class": "analytic_truth",
        "model_kind": problem.model_kind,
        "units": {"length": "m", "force": "kN"},
        "external_force_kn": problem.external_force_kn,
        "initial_displacement_m": problem.initial_displacement_m,
        "residual_contract": RESIDUAL_FORMULA,
        "claim_boundary": (
            "Deterministic scalar axial constitutive reference only. "
            "Not a full mesh, frame, shell, or production nonlinear solver."
        ),
    }
    if isinstance(problem, ScalarNonlinearAxialReference):
        payload.update(
            {
                "linear_stiffness_kn_per_m": problem.linear_stiffness_kn_per_m,
                "cubic_stiffness_kn_per_m3": problem.cubic_stiffness_kn_per_m3,
            }
        )
    elif isinstance(problem, ScalarBilinearHardeningAxialReference):
        payload.update(
            {
                "elastic_stiffness_kn_per_m": problem.elastic_stiffness_kn_per_m,
                "post_yield_stiffness_kn_per_m": problem.post_yield_stiffness_kn_per_m,
                "yield_force_kn": problem.yield_force_kn,
            }
        )
    return payload


def _solution_payload(solution: Any) -> dict[str, Any]:
    metrics = solution.metrics
    return {
        "schema_version": "phase2-material-newton-breadth-scalar-law-result.v1",
        "status": solution.status,
        "contract_pass": bool(metrics.get("contract_pass")),
        "case_id": solution.problem.case_id,
        "truth_class": "analytic_truth",
        "model_kind": solution.problem.model_kind,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": metrics.get("tangent_definition"),
        "globalization": GLOBALIZATION,
        "matrix_backend": metrics.get("matrix_backend"),
        "sparse_backend_used": metrics.get("sparse_backend_used"),
        "metrics": metrics,
        "convergence_history": solution.convergence_history,
        "line_search_history": solution.line_search_history,
        "unsupported_features": solution.unsupported_features,
        "warnings": solution.warnings,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "claim_boundary": (
            "This records one scalar material law solved with explicit "
            "R=F_internal-F_external, consistent tangent, backtracking line search, "
            "and separate residual/increment gates. It does not close general material "
            "Newton breadth on meshes, frame/shell/material coupling, sparse production "
            "backends, full-mesh/full-load G1, or GPU/HIP parity."
        ),
    }


def _evaluate_material_law(
    problem: ScalarAxialEquilibriumProblem,
    *,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    solution = newton_raphson_scalar(problem, config=config)
    expected_displacement_m = expected_scalar_equilibrium_displacement(problem)
    displacement_error = abs(solution.displacement_m - expected_displacement_m)
    tangent_check = finite_difference_tangent_check(problem, solution.displacement_m)
    equilibrium_residual = problem.residual(solution.displacement_m)
    metrics = solution.metrics

    residual_gate_passed = bool(metrics.get("residual_gate_passed"))
    increment_gate_passed = bool(metrics.get("increment_gate_passed"))
    no_regularization_or_fallback = (
        metrics.get("regularization_used") is False and metrics.get("fallback_used") is False
    )
    tangent_gate_passed = bool(tangent_check["pass"])
    displacement_gate_passed = displacement_error <= DISPLACEMENT_TOLERANCE_M
    law_contract_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and residual_gate_passed
        and increment_gate_passed
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
    return {
        "case_id": problem.case_id,
        "model_kind": problem.model_kind,
        "law_contract_pass": law_contract_pass,
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "tangent_gate_passed": tangent_gate_passed,
        "displacement_gate_passed": displacement_gate_passed,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "result": result_payload,
    }


def build_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    material_laws: tuple[ScalarAxialEquilibriumProblem, ...] = (
        ScalarNonlinearAxialReference(),
        ScalarBilinearHardeningAxialReference(),
    )
    law_results = [
        _evaluate_material_law(problem, config=config) for problem in material_laws
    ]
    contract_pass = all(row["law_contract_pass"] for row in law_results)
    model_kinds = [row["model_kind"] for row in law_results]

    laws_payload = {
        "schema_version": "phase2-material-newton-breadth-scalar-laws.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "material_law_count": len(law_results),
        "model_kinds": model_kinds,
        "solver_config": {
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance": config.increment_tolerance,
            "max_iterations": config.max_iterations,
        },
        "material_laws": law_results,
        "claim_boundary": (
            "Deterministic scalar material-Newton breadth seed across multiple "
            "constitutive laws using the same explicit F_internal_minus_F_external "
            "residual contract, consistent tangent, residual/increment gates, and "
            "backtracking line search without regularization or fallback false PASS. "
            "This does not close G1 full-mesh/full-load nonlinear equilibrium, general "
            "frame/shell/material coupling, sparse production matrix backends, or "
            "production GPU/HIP gates."
        ),
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
                Path("scripts/build_phase2_material_newton_breadth_artifacts.py"),
                Path("scripts/verify_quality_gate.py"),
                Path("tests/test_build_phase2_material_newton_breadth_artifacts.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "analysis_type": "nonlinear_static_scalar_material_breadth_seed",
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": law_results[0]["result"]["matrix_backend"],
        "sparse_backend_used": law_results[0]["result"]["sparse_backend_used"],
        "material_law_count": len(law_results),
        "model_kinds": model_kinds,
        "law_summaries": [
            {
                "case_id": row["case_id"],
                "model_kind": row["model_kind"],
                "law_contract_pass": row["law_contract_pass"],
                "residual_gate_passed": row["residual_gate_passed"],
                "increment_gate_passed": row["increment_gate_passed"],
                "tangent_gate_passed": row["tangent_gate_passed"],
                "displacement_gate_passed": row["displacement_gate_passed"],
                "regularization_used": row["regularization_used"],
                "fallback_used": row["fallback_used"],
                "displacement_m": row["result"]["metrics"]["displacement_m"],
                "relative_residual": row["result"]["metrics"]["relative_residual"],
                "final_increment_abs_m": row["result"]["metrics"]["final_increment_abs_m"],
            }
            for row in law_results
        ],
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_nonlinear_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "general_newton_jacobian_assembly_not_closed",
        ],
        "artifacts": {
            "scalar_axial_laws": str(laws_out),
            "summary": str(summary_out),
            "related_scalar_newton_globalization_summary": str(
                PRODUCTIZATION / "phase2_newton_globalization_summary.json"
            ),
        },
        "claim_boundary": laws_payload["claim_boundary"],
    }
    return {
        "laws": laws_payload,
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


def check_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_material_newton_breadth_artifacts(
        repo_root=repo_root,
        laws_out=laws_out,
        summary_out=summary_out,
    )
    targets = {
        "laws": laws_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_material_newton_breadth_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_material_newton_breadth_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_material_newton_breadth_mismatch:{key}"
    return True, "phase2_material_newton_breadth_consistent"


def write_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_material_newton_breadth_artifacts(
        repo_root=repo_root,
        laws_out=laws_out,
        summary_out=summary_out,
    )
    for key, path in {
        "laws": laws_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laws-out", type=Path, default=DEFAULT_LAWS_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_material_newton_breadth_artifacts(
            laws_out=args.laws_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 material Newton breadth check: {message}")
        return 0 if ok else 1
    artifacts = write_material_newton_breadth_artifacts(
        laws_out=args.laws_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 material Newton breadth: "
        f"{summary['status']} | laws={summary['material_law_count']} | "
        f"model_kinds={summary['model_kinds']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
