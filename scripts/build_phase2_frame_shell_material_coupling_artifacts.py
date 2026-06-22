#!/usr/bin/env python3
"""Build Phase 2 frame-shell-material coupling seed artifacts."""

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
from structural_analysis.assembly.coupled_static import (  # noqa: E402
    default_frame_shell_material_coupled_problem,
    finite_difference_coupled_jacobian_check,
    solve_frame_shell_material_coupled,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_frame_shell_material_coupling_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_frame_shell_material_coupling_summary.json"
SCHEMA_VERSION = "phase2-frame-shell-material-coupling-artifacts.v1"
COUPLING_TOLERANCE = 1.0e-10


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


def _state_payload(state: Any) -> dict[str, Any]:
    return {
        "residual_formula": state.residual_formula,
        "free_dof_labels": list(state.free_dof_labels),
        "free_displacements_m": state.free_displacements_m.tolist(),
        "residual_kn": state.residual_kn.tolist(),
        "jacobian_kn_per_m": state.jacobian_kn_per_m.tolist(),
        "internal_forces_kn": state.internal_forces_kn.tolist(),
        "external_forces_kn": state.external_forces_kn.tolist(),
        "component_forces_kn": list(state.component_forces_kn),
    }


def _solution_payload(solution: Any, state: Any) -> dict[str, Any]:
    return {
        "status": solution.status,
        "contract_pass": bool(solution.metrics.get("contract_pass")),
        "matrix_backend": solution.metrics.get("matrix_backend"),
        "sparse_backend_used": solution.metrics.get("sparse_backend_used"),
        "stiffness_storage": solution.metrics.get("stiffness_storage"),
        "metrics": solution.metrics,
        "state": _state_payload(state),
        "convergence_history": solution.convergence_history,
        "line_search_history": solution.line_search_history,
        "unsupported_features": solution.unsupported_features,
        "warnings": solution.warnings,
    }


def build_phase2_frame_shell_material_coupling_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    problem = default_frame_shell_material_coupled_problem()
    dense_config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
        matrix_backend=VECTOR_MATRIX_BACKEND,
    )
    sparse_config = NewtonRaphsonConfig(
        residual_tolerance=dense_config.residual_tolerance,
        increment_tolerance=dense_config.increment_tolerance,
        max_iterations=dense_config.max_iterations,
        line_search_alphas=dense_config.line_search_alphas,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
    )
    dense_solution, dense_state = solve_frame_shell_material_coupled(
        problem,
        config=dense_config,
    )
    sparse_solution, sparse_state = solve_frame_shell_material_coupled(
        problem,
        config=sparse_config,
    )
    fd_check = finite_difference_coupled_jacobian_check(
        problem,
        dense_solution.free_displacements_m,
    )
    displacement_deltas = [
        abs(float(a) - float(b))
        for a, b in zip(
            dense_state.free_displacements_m.tolist(),
            sparse_state.free_displacements_m.tolist(),
            strict=True,
        )
    ]
    residual_deltas = [
        abs(float(a) - float(b))
        for a, b in zip(
            dense_state.residual_kn.tolist(),
            sparse_state.residual_kn.tolist(),
            strict=True,
        )
    ]
    max_displacement_delta = max(displacement_deltas)
    max_residual_delta = max(residual_deltas)
    off_diagonal_coupling_visible = (
        abs(float(dense_state.jacobian_kn_per_m[0, 1])) > 0.0
        and float(dense_state.jacobian_kn_per_m[0, 1])
        == float(dense_state.jacobian_kn_per_m[1, 0])
    )
    no_regularization_or_fallback = (
        dense_solution.metrics.get("regularization_used") is False
        and dense_solution.metrics.get("fallback_used") is False
        and sparse_solution.metrics.get("regularization_used") is False
        and sparse_solution.metrics.get("fallback_used") is False
    )
    coupling_contract_pass = (
        dense_solution.status == "ready"
        and sparse_solution.status == "ready"
        and bool(dense_solution.metrics.get("contract_pass"))
        and bool(sparse_solution.metrics.get("contract_pass"))
        and bool(fd_check["pass"])
        and off_diagonal_coupling_visible
        and no_regularization_or_fallback
        and max_displacement_delta <= COUPLING_TOLERANCE
        and max_residual_delta <= COUPLING_TOLERANCE
    )

    result_payload = {
        "schema_version": "phase2-frame-shell-material-coupling-result.v1",
        "status": "ready" if coupling_contract_pass else "blocked",
        "contract_pass": coupling_contract_pass,
        "case_id": problem.case_id,
        "truth_class": "assembled_coupling_truth",
        "analysis_type": "nonlinear_static_frame_shell_material_coupling_seed",
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "dense_solution": _solution_payload(dense_solution, dense_state),
        "sparse_solution": _solution_payload(sparse_solution, sparse_state),
        "finite_difference_jacobian_check": fd_check,
        "off_diagonal_coupling_visible": off_diagonal_coupling_visible,
        "dense_sparse_equivalence": {
            "max_displacement_delta_m": max_displacement_delta,
            "max_residual_delta_kn": max_residual_delta,
            "pass": max_displacement_delta <= COUPLING_TOLERANCE
            and max_residual_delta <= COUPLING_TOLERANCE,
        },
        "regularization_used": False,
        "fallback_used": False,
        "g1_closure_claim": False,
        "frame_shell_material_coupling_closure_claim": False,
        "full_mesh_closure_claim": False,
        "claim_boundary": (
            "This is a two-free-DOF deterministic seed that assembles a frame axial "
            "component, a shell diaphragm shear component, and an off-diagonal material "
            "coupling tangent into one residual/Jacobian system. It does not close "
            "general frame-shell finite elements, production full-mesh/full-load G1, "
            "or design-code adequacy."
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
                Path("src/structural_analysis/assembly/__init__.py"),
                Path("src/structural_analysis/assembly/coupled_static.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("scripts/build_phase2_frame_shell_material_coupling_artifacts.py"),
                Path("tests/test_build_phase2_frame_shell_material_coupling_artifacts.py"),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": coupling_contract_pass,
        "analysis_type": result_payload["analysis_type"],
        "truth_class": result_payload["truth_class"],
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "dense_matrix_backend": VECTOR_MATRIX_BACKEND,
        "sparse_matrix_backend": VECTOR_SPARSE_MATRIX_BACKEND,
        "finite_difference_jacobian_gate_passed": bool(fd_check["pass"]),
        "off_diagonal_coupling_visible": off_diagonal_coupling_visible,
        "dense_sparse_equivalence_gate_passed": result_payload["dense_sparse_equivalence"]["pass"],
        "regularization_used": False,
        "fallback_used": False,
        "g1_closure_claim": False,
        "frame_shell_material_coupling_closure_claim": False,
        "full_mesh_closure_claim": False,
        "blockers_remaining": [
            "general_frame_shell_material_coupling_not_closed",
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
            "production_rocm_hip_parity_not_closed",
            "design_code_adequacy_not_closed",
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


def check_phase2_frame_shell_material_coupling_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_frame_shell_material_coupling_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, path in {"result": result_out, "summary": summary_out}.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_frame_shell_material_coupling_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_frame_shell_material_coupling_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_frame_shell_material_coupling_mismatch:{key}"
    return True, "phase2_frame_shell_material_coupling_consistent"


def write_phase2_frame_shell_material_coupling_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_phase2_frame_shell_material_coupling_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, path in {"result": result_out, "summary": summary_out}.items():
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
        ok, message = check_phase2_frame_shell_material_coupling_artifacts(
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 frame-shell-material coupling check: {message}")
        return 0 if ok else 1
    artifacts = write_phase2_frame_shell_material_coupling_artifacts(
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 frame-shell-material coupling: "
        f"{summary['status']} | fd={summary['finite_difference_jacobian_gate_passed']} | "
        f"dense_sparse={summary['dense_sparse_equivalence_gate_passed']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
