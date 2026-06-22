#!/usr/bin/env python3
"""Build Phase 2 narrow patch-test and rigid-body seed artifacts."""

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
from structural_analysis.assembly.patch_static import (  # noqa: E402
    assemble_axial_patch_state,
    default_axial_patch_rigidbody_problem,
    rigid_body_nullspace_check,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_patch_rigidbody_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_patch_rigidbody_summary.json"
SCHEMA_VERSION = "phase2-patch-rigidbody-artifacts.v1"
PATCH_TOLERANCE = 1.0e-10
RIGID_BODY_TOLERANCE = 1.0e-12


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


def _patch_payload() -> dict[str, Any]:
    problem = default_axial_patch_rigidbody_problem()
    state = assemble_axial_patch_state(problem)
    stiffness_work = float(state.displacement_m @ state.internal_forces_kn)
    external_work = float(state.displacement_m @ state.external_forces_kn)
    interior_residual = state.residual_kn[1:-1] if state.residual_kn.size > 2 else state.residual_kn
    strain_spread = float(np.max(state.element_strains) - np.min(state.element_strains))
    expected_force = (
        problem.elastic_modulus_kn_per_m2
        * problem.area_m2
        * problem.prescribed_strain
    )
    force_error = float(np.linalg.norm(state.element_forces_kn - expected_force, ord=np.inf))
    max_interior_residual = float(np.linalg.norm(interior_residual, ord=np.inf))
    max_total_residual = float(np.linalg.norm(state.residual_kn, ord=np.inf))
    stiffness_work_balance_error = abs(stiffness_work - external_work)
    patch_pass = (
        max_interior_residual <= PATCH_TOLERANCE
        and max_total_residual <= PATCH_TOLERANCE
        and strain_spread <= PATCH_TOLERANCE
        and force_error <= PATCH_TOLERANCE
        and stiffness_work_balance_error <= PATCH_TOLERANCE
    )
    return {
        "case_id": problem.case_id,
        "truth_class": "analytic_component_patch_truth",
        "node_coordinates_m": list(problem.node_coordinates_m),
        "element_count": len(problem.node_coordinates_m) - 1,
        "prescribed_strain": problem.prescribed_strain,
        "expected_element_force_kn": expected_force,
        "displacement_m": state.displacement_m.tolist(),
        "internal_forces_kn": state.internal_forces_kn.tolist(),
        "external_forces_kn": state.external_forces_kn.tolist(),
        "residual_kn": state.residual_kn.tolist(),
        "residual_formula": state.residual_formula,
        "element_strains": state.element_strains.tolist(),
        "element_forces_kn": state.element_forces_kn.tolist(),
        "max_total_residual_kn": max_total_residual,
        "max_interior_residual_kn": max_interior_residual,
        "strain_spread": strain_spread,
        "element_force_inf_norm_error_kn": force_error,
        "stiffness_work_kn_m": stiffness_work,
        "external_work_kn_m": external_work,
        "stiffness_work_balance_error_kn_m": stiffness_work_balance_error,
        "stiffness_symmetry_error": float(
            np.linalg.norm(state.stiffness_kn_per_m - state.stiffness_kn_per_m.T, ord=np.inf)
        ),
        "regularization_used": False,
        "fallback_used": False,
        "pass": patch_pass,
    }


def build_phase2_patch_rigidbody_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    patch = _patch_payload()
    rigid_body = rigid_body_nullspace_check(default_axial_patch_rigidbody_problem())
    contract_pass = bool(patch["pass"]) and bool(rigid_body["pass"])
    result_payload = {
        "schema_version": "phase2-patch-rigidbody-result.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "analysis_type": "linear_static_axial_patch_rigidbody_seed",
        "patch_test": patch,
        "rigid_body_test": rigid_body,
        "regularization_used": False,
        "fallback_used": False,
        "g1_closure_claim": False,
        "patch_rigidbody_closure_claim": False,
        "full_mesh_closure_claim": False,
        "claim_boundary": (
            "This artifact automates a narrow 1D axial constant-strain patch test "
            "and rigid-body translation nullspace check. It does not close general "
            "frame/shell patch tests, full-mesh/full-load nonlinear equilibrium, "
            "production sparse/GPU backends, or G1."
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
                Path("src/structural_analysis/assembly/patch_static.py"),
                Path("scripts/build_phase2_patch_rigidbody_artifacts.py"),
                Path("tests/test_build_phase2_patch_rigidbody_artifacts.py"),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": contract_pass,
        "analysis_type": result_payload["analysis_type"],
        "truth_class": patch["truth_class"],
        "patch_test_passed": bool(patch["pass"]),
        "rigid_body_test_passed": bool(rigid_body["pass"]),
        "max_patch_residual_kn": patch["max_total_residual_kn"],
        "patch_strain_spread": patch["strain_spread"],
        "rigid_body_dense_nullspace_norm_kn": rigid_body[
            "dense_stiffness_times_translation_inf_norm_kn"
        ],
        "rigid_body_sparse_nullspace_norm_kn": rigid_body[
            "sparse_stiffness_times_translation_inf_norm_kn"
        ],
        "regularization_used": False,
        "fallback_used": False,
        "g1_closure_claim": False,
        "patch_rigidbody_closure_claim": False,
        "full_mesh_closure_claim": False,
        "blockers_remaining": [
            "general_frame_shell_patch_tests_not_closed",
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
            "production_sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
        ],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
        },
        "claim_boundary": result_payload["claim_boundary"],
    }
    return {"result": result_payload, "summary": summary_payload}


def write_phase2_patch_rigidbody_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, Path]:
    artifacts = build_phase2_patch_rigidbody_artifacts(
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


def check_phase2_patch_rigidbody_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_patch_rigidbody_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, path in (("result", result_out), ("summary", summary_out)):
        if not path.exists():
            return False, f"phase2_patch_rigidbody_missing:{path.as_posix()}"
        try:
            actual = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return False, f"phase2_patch_rigidbody_unreadable:{path.as_posix()}:{exc}"
        if _strip_volatile(actual) != _strip_volatile(expected[key]):
            return False, f"phase2_patch_rigidbody_mismatch:{key}"
    return True, "phase2_patch_rigidbody_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase2_patch_rigidbody_artifacts(
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 patch/rigid-body check: {message}")
        return 0 if ok else 1
    paths = write_phase2_patch_rigidbody_artifacts(
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = _read_json(paths["summary"])
    print(
        "Phase 2 patch/rigid-body seed: "
        f"{summary['status']} | patch={summary['patch_test_passed']} | "
        f"rigid={summary['rigid_body_test_passed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
