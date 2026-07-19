#!/usr/bin/env python3
"""Build the narrow adaptive consistent-Newton continuation evidence artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.nonlinear_static import (  # noqa: E402
    AxialChainLoadContinuationAdapter,
    assemble_axial_chain_state,
    finite_difference_assembled_jacobian_check,
    refined_strain_cubic_axial_chain_mesh_problem,
)
from structural_analysis.solvers.nonlinear.continuation import (  # noqa: E402
    AdaptiveContinuationConfig,
    adaptive_load_continuation,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    VECTOR_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_adaptive_newton_continuation_result.json"
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "phase2_adaptive_newton_continuation_summary.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/adaptive_newton_continuation_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-adaptive-newton-continuation-artifacts.v1"
CLAIM_BOUNDARY = (
    "This receipt reaches load factor 1.0 only for a two-element 1D strain-cubic "
    "analytic axial chain. It verifies accepted/trial state discipline, adaptive "
    "step reduction, exact rollback, checkpoint restart, a finite-difference "
    "consistent Jacobian check, local quadratic convergence, and zero fallback. "
    "Every committed step has active free equations and an iterative convergence "
    "claim; fully constrained no-solve state transitions are a separate contract. "
    "It does not close G1 full-building/full-mesh nonlinear equilibrium, frame-shell "
    "coupling, material-model breadth, arc-length snap-through, or ROCm/HIP parity."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _config(*, target: float, initial_step: float = 0.5) -> AdaptiveContinuationConfig:
    return AdaptiveContinuationConfig(
        target_load_factor=target,
        initial_step_size=initial_step,
        minimum_step_size=0.125,
        maximum_step_size=0.5,
        failed_step_reduction=0.5,
        fast_step_growth=1.0,
        fast_iteration_threshold=4,
        maximum_attempt_count=20,
    )


def build_phase2_adaptive_newton_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    base_problem = refined_strain_cubic_axial_chain_mesh_problem(element_count=2)
    problem = AxialChainLoadContinuationAdapter(base_problem)
    newton_config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=4,
        matrix_backend=VECTOR_MATRIX_BACKEND,
    )
    one_shot = adaptive_load_continuation(
        problem,
        config=_config(target=1.0),
        newton_config=newton_config,
    )
    first_half = adaptive_load_continuation(
        problem,
        config=_config(target=0.5),
        newton_config=newton_config,
    )
    resumed = adaptive_load_continuation(
        problem,
        config=_config(target=1.0, initial_step=0.25),
        newton_config=newton_config,
        resume_from=first_half.final_checkpoint,
    )

    final_free = np.asarray(one_shot.final_checkpoint.free_displacements_m, dtype=float)
    final_state = assemble_axial_chain_state(base_problem, final_free)
    final_residual_inf_norm = float(np.linalg.norm(final_state.residual_kn, ord=np.inf))
    tangent_check = finite_difference_assembled_jacobian_check(base_problem, final_free)
    committed_attempts = [
        row for row in one_shot.attempts if row.get("outcome") == "committed"
    ]
    final_attempt = committed_attempts[-1]
    quadratic_check = assess_quadratic_convergence(final_attempt["convergence_history"])
    restart_exact = bool(
        first_half.status == "ready"
        and resumed.status == "ready"
        and resumed.final_checkpoint.state_hash == one_shot.final_checkpoint.state_hash
        and resumed.final_checkpoint.free_displacements_m
        == one_shot.final_checkpoint.free_displacements_m
    )
    rollback_rows = [
        row for row in one_shot.attempts if row.get("outcome") == "rolled_back"
    ]
    rollback_gate = bool(
        rollback_rows
        and all(row.get("rollback_exact") is True for row in rollback_rows)
        and all(
            row.get("accepted_state_hash_before")
            == row.get("accepted_state_hash_after")
            for row in rollback_rows
        )
    )
    line_search_history_present = bool(
        committed_attempts
        and all(row.get("line_search_history") for row in committed_attempts)
    )
    contract_pass = bool(
        one_shot.status == "ready"
        and one_shot.metrics.get("contract_pass") is True
        and one_shot.final_checkpoint.load_factor == 1.0
        and rollback_gate
        and restart_exact
        and tangent_check["pass"] is True
        and quadratic_check["pass"] is True
        and line_search_history_present
        and final_residual_inf_norm <= newton_config.residual_tolerance
        and one_shot.metrics.get("fallback_count") == 0
        and one_shot.metrics.get("regularization_count") == 0
        and one_shot.metrics.get("no_solve_reaction_only_step_count") == 0
        and one_shot.metrics.get("iterative_solver_step_count")
        == len(committed_attempts)
        and one_shot.metrics.get("solver_executed_step_count")
        == len(committed_attempts)
        and one_shot.metrics.get("newton_convergence_claim_count")
        == len(committed_attempts)
        and one_shot.metrics.get("solver_executed") is True
        and one_shot.metrics.get("convergence_claim") is True
        and one_shot.metrics.get("reaction_observation_only") is False
        and one_shot.metrics.get("terminal_dispositions") == ["solve_free_equations"]
    )

    result_payload = one_shot.to_dict()
    result_payload.update(
        {
            "status": "ready" if contract_pass else "blocked",
            "contract_pass": contract_pass,
            "truth_class": "analytic_1d_material_mesh_truth",
            "analysis_type": "adaptive_consistent_newton_continuation_seed",
            "verification": {
                "full_load_factor_reached": one_shot.final_checkpoint.load_factor
                == 1.0,
                "final_residual_inf_norm_kn": final_residual_inf_norm,
                "finite_difference_jacobian": tangent_check,
                "quadratic_convergence": quadratic_check,
                "rollback_attempt_count": len(rollback_rows),
                "rollback_exact_gate_passed": rollback_gate,
                "line_search_history_present": line_search_history_present,
                "checkpoint_restart": {
                    "first_half_checkpoint": first_half.final_checkpoint.to_dict(),
                    "resumed_final_state_hash": resumed.final_checkpoint.state_hash,
                    "one_shot_final_state_hash": one_shot.final_checkpoint.state_hash,
                    "exact_final_state_match": restart_exact,
                },
            },
            "analytic_seed_full_load_pass": contract_pass,
            "g1_full_load_claim": False,
            "full_mesh_closure_claim": False,
            "production_nonlinear_closure_claim": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator(schema).validate(result_payload)

    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("src/structural_analysis/solvers/nonlinear/continuation.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                SCHEMA_PATH,
                Path("scripts/build_phase2_adaptive_newton_continuation_artifacts.py"),
                Path("tests/test_nonlinear_adaptive_continuation.py"),
                Path(
                    "tests/test_build_phase2_adaptive_newton_continuation_artifacts.py"
                ),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": result_payload["truth_class"],
        "analysis_type": result_payload["analysis_type"],
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "target_load_factor": 1.0,
        "final_load_factor": one_shot.final_checkpoint.load_factor,
        "attempt_count": one_shot.metrics["attempt_count"],
        "accepted_step_count": one_shot.metrics["accepted_step_count"],
        "rejected_attempt_count": one_shot.metrics["rejected_attempt_count"],
        "rollback_exact_gate_passed": rollback_gate,
        "checkpoint_restart_exact_gate_passed": restart_exact,
        "finite_difference_jacobian_gate_passed": tangent_check["pass"],
        "quadratic_convergence_gate_passed": quadratic_check["pass"],
        "line_search_history_present": line_search_history_present,
        "fallback_count": one_shot.metrics["fallback_count"],
        "regularization_count": one_shot.metrics["regularization_count"],
        "no_solve_reaction_only_step_count": one_shot.metrics[
            "no_solve_reaction_only_step_count"
        ],
        "iterative_solver_step_count": one_shot.metrics["iterative_solver_step_count"],
        "solver_executed_step_count": one_shot.metrics["solver_executed_step_count"],
        "newton_convergence_claim_count": one_shot.metrics[
            "newton_convergence_claim_count"
        ],
        "solver_executed": one_shot.metrics["solver_executed"],
        "convergence_claim": one_shot.metrics["convergence_claim"],
        "reaction_observation_only": one_shot.metrics["reaction_observation_only"],
        "terminal_dispositions": one_shot.metrics["terminal_dispositions"],
        "analytic_seed_full_load_pass": contract_pass,
        "g1_full_load_claim": False,
        "full_mesh_closure_claim": False,
        "production_nonlinear_closure_claim": False,
        "blockers_remaining": [
            "g1_full_building_load_factor_1_not_closed",
            "general_frame_shell_consistent_jacobian_not_closed",
            "state_updated_material_newton_breadth_not_closed",
            "arc_length_snap_through_not_closed",
            "production_sparse_rocm_hip_parity_not_closed",
        ],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_adaptive_newton_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_adaptive_newton_continuation_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_adaptive_newton_continuation_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_adaptive_newton_continuation_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_adaptive_newton_continuation_mismatch:{key}"
    return True, "phase2_adaptive_newton_continuation_consistent"


def write_phase2_adaptive_newton_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_adaptive_newton_continuation_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payloads[key]), encoding="utf-8")
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_phase2_adaptive_newton_continuation_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_adaptive_newton_continuation_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    print(
        f"{payloads['summary']['status']} | "
        f"final_load_factor={payloads['summary']['final_load_factor']} | "
        f"rollback_attempts={payloads['summary']['rejected_attempt_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
