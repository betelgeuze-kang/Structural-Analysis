#!/usr/bin/env python3
"""Build Phase 2 scalar nonlinear load-step partition convergence seed artifacts."""

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
    newton_raphson_scalar,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_PARTITIONS_OUT = PRODUCTIZATION / "phase2_nonlinear_load_step_scalar_axial_partitions.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_nonlinear_load_step_summary.json"
SCHEMA_VERSION = "phase2-nonlinear-load-step-artifacts.v1"
PARTITION_STEP_COUNTS = (1, 2, 4, 8)
TARGET_LOAD_FACTOR = 1.0
DISPLACEMENT_TOLERANCE_M = 1.0e-10


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


def _step_record(
    *,
    step_index: int,
    partition_step_count: int,
    load_factor: float,
    initial_displacement_m: float,
    solution: Any,
    expected_displacement_m: float,
) -> dict[str, Any]:
    metrics = solution.metrics
    displacement_m = solution.displacement_m
    displacement_error = abs(displacement_m - expected_displacement_m)
    return {
        "step_index": step_index,
        "partition_step_count": partition_step_count,
        "load_factor": load_factor,
        "initial_displacement_m": initial_displacement_m,
        "final_displacement_m": displacement_m,
        "expected_displacement_m": expected_displacement_m,
        "displacement_abs_error_m": displacement_error,
        "displacement_gate_passed": displacement_error <= DISPLACEMENT_TOLERANCE_M,
        "status": solution.status,
        "contract_pass": bool(metrics.get("contract_pass")),
        "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
        "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
        "iteration_count": int(metrics.get("iteration_count", 0)),
        "line_search_used": bool(metrics.get("line_search_used")),
        "line_search_step_count": int(metrics.get("line_search_step_count", 0)),
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": metrics.get("tangent_definition"),
        "globalization": GLOBALIZATION,
        "relative_residual": metrics.get("relative_residual"),
        "final_increment_abs_m": metrics.get("final_increment_abs_m"),
        "residual_kn": metrics.get("residual_kn"),
    }


def run_load_step_partition(
    base_problem: ScalarNonlinearAxialReference,
    *,
    partition_step_count: int,
    config: NewtonRaphsonConfig,
    target_load_factor: float = TARGET_LOAD_FACTOR,
) -> dict[str, Any]:
    total_force_kn = base_problem.external_force_kn
    displacement_m = float(base_problem.initial_displacement_m)
    steps: list[dict[str, Any]] = []

    for step_index in range(1, partition_step_count + 1):
        load_factor = (step_index / partition_step_count) * target_load_factor
        initial_displacement_m = displacement_m
        step_problem = ScalarNonlinearAxialReference(
            linear_stiffness_kn_per_m=base_problem.linear_stiffness_kn_per_m,
            cubic_stiffness_kn_per_m3=base_problem.cubic_stiffness_kn_per_m3,
            external_force_kn=total_force_kn * load_factor,
            initial_displacement_m=initial_displacement_m,
            case_id=base_problem.case_id,
        )
        solution = newton_raphson_scalar(step_problem, config=config)
        expected_displacement_m = expected_scalar_equilibrium_displacement(step_problem)
        step_payload = _step_record(
            step_index=step_index,
            partition_step_count=partition_step_count,
            load_factor=load_factor,
            initial_displacement_m=initial_displacement_m,
            solution=solution,
            expected_displacement_m=expected_displacement_m,
        )
        step_payload["problem"] = _problem_payload(step_problem)
        steps.append(step_payload)
        displacement_m = solution.displacement_m

    final_step = steps[-1]
    no_regularization_or_fallback = all(
        step["regularization_used"] is False and step["fallback_used"] is False for step in steps
    )
    partition_contract_pass = (
        all(step["contract_pass"] for step in steps)
        and all(step["residual_gate_passed"] for step in steps)
        and all(step["increment_gate_passed"] for step in steps)
        and all(step["displacement_gate_passed"] for step in steps)
        and no_regularization_or_fallback
        and final_step["status"] == "ready"
    )

    return {
        "partition_step_count": partition_step_count,
        "target_load_factor": target_load_factor,
        "final_load_factor": final_step["load_factor"],
        "final_displacement_m": final_step["final_displacement_m"],
        "expected_final_displacement_m": final_step["expected_displacement_m"],
        "final_displacement_abs_error_m": final_step["displacement_abs_error_m"],
        "total_iteration_count": sum(step["iteration_count"] for step in steps),
        "partition_contract_pass": partition_contract_pass,
        "regularization_used": any(step["regularization_used"] for step in steps),
        "fallback_used": any(step["fallback_used"] for step in steps),
        "steps": steps,
    }


def build_nonlinear_load_step_artifacts(
    *,
    repo_root: Path = ROOT,
    partitions_out: Path = DEFAULT_PARTITIONS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    partition_step_counts: tuple[int, ...] = PARTITION_STEP_COUNTS,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    base_problem = ScalarNonlinearAxialReference()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    expected_full_load_displacement_m = expected_scalar_equilibrium_displacement(base_problem)

    partitions = [
        run_load_step_partition(
            base_problem,
            partition_step_count=partition_step_count,
            config=config,
        )
        for partition_step_count in partition_step_counts
    ]

    final_displacements = [row["final_displacement_m"] for row in partitions]
    max_partition_spread_m = max(final_displacements) - min(final_displacements)
    partition_spread_gate_passed = max_partition_spread_m <= DISPLACEMENT_TOLERANCE_M
    full_load_errors = [
        abs(row["final_displacement_m"] - expected_full_load_displacement_m) for row in partitions
    ]
    full_load_gate_passed = all(error <= DISPLACEMENT_TOLERANCE_M for error in full_load_errors)
    contract_pass = (
        partition_spread_gate_passed
        and full_load_gate_passed
        and all(row["partition_contract_pass"] for row in partitions)
    )

    partitions_payload = {
        "schema_version": "phase2-nonlinear-load-step-scalar-partitions.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": base_problem.case_id,
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "nonlinear_newton_closure_claim": False,
        "target_load_factor": TARGET_LOAD_FACTOR,
        "partition_step_counts": list(partition_step_counts),
        "base_problem": _problem_payload(base_problem),
        "solver_config": {
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance": config.increment_tolerance,
            "max_iterations": config.max_iterations,
        },
        "verification": {
            "expected_full_load_displacement_m": expected_full_load_displacement_m,
            "max_partition_final_displacement_spread_m": max_partition_spread_m,
            "partition_spread_gate_passed": partition_spread_gate_passed,
            "full_load_gate_passed": full_load_gate_passed,
            "full_load_displacement_abs_errors_m": {
                str(row["partition_step_count"]): error
                for row, error in zip(partitions, full_load_errors, strict=True)
            },
        },
        "partitions": partitions,
        "claim_boundary": (
            "Deterministic scalar cubic-spring load-step partition convergence only. "
            "Each partition applies proportional load factors to the same reference case, "
            "continues from the previous accepted step displacement, and uses "
            "newton_raphson_scalar with F_internal_minus_F_external, consistent tangent, "
            "residual/increment gates, and backtracking line search. "
            "This does not close G1 full-mesh/full-load nonlinear equilibrium, general "
            "frame/shell/material coupling, or production mesh load-step suites."
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
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "nonlinear_newton_closure_claim": False,
        "analysis_type": "nonlinear_static_scalar_load_step_seed",
        "truth_class": "analytic_truth",
        "case_id": base_problem.case_id,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "target_load_factor": TARGET_LOAD_FACTOR,
        "partition_step_counts": list(partition_step_counts),
        "partition_spread_gate_passed": partition_spread_gate_passed,
        "full_load_gate_passed": full_load_gate_passed,
        "max_partition_final_displacement_spread_m": max_partition_spread_m,
        "expected_full_load_displacement_m": expected_full_load_displacement_m,
        "partition_summaries": [
            {
                "partition_step_count": row["partition_step_count"],
                "partition_contract_pass": row["partition_contract_pass"],
                "final_displacement_m": row["final_displacement_m"],
                "final_displacement_abs_error_m": row["final_displacement_abs_error_m"],
                "total_iteration_count": row["total_iteration_count"],
                "regularization_used": row["regularization_used"],
                "fallback_used": row["fallback_used"],
            }
            for row in partitions
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
            "scalar_axial_partitions": str(partitions_out),
            "summary": str(summary_out),
            "related_scalar_newton_globalization_summary": str(
                PRODUCTIZATION / "phase2_newton_globalization_summary.json"
            ),
        },
        "claim_boundary": partitions_payload["claim_boundary"],
    }
    return {
        "partitions": partitions_payload,
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


def check_nonlinear_load_step_artifacts(
    *,
    repo_root: Path = ROOT,
    partitions_out: Path = DEFAULT_PARTITIONS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_nonlinear_load_step_artifacts(
        repo_root=repo_root,
        partitions_out=partitions_out,
        summary_out=summary_out,
    )
    targets = {
        "partitions": partitions_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_nonlinear_load_step_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_nonlinear_load_step_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_nonlinear_load_step_mismatch:{key}"
    return True, "phase2_nonlinear_load_step_consistent"


def write_nonlinear_load_step_artifacts(
    *,
    repo_root: Path = ROOT,
    partitions_out: Path = DEFAULT_PARTITIONS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_nonlinear_load_step_artifacts(
        repo_root=repo_root,
        partitions_out=partitions_out,
        summary_out=summary_out,
    )
    for key, path in {
        "partitions": partitions_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partitions-out", type=Path, default=DEFAULT_PARTITIONS_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_nonlinear_load_step_artifacts(
            partitions_out=args.partitions_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 nonlinear load-step check: {message}")
        return 0 if ok else 1
    artifacts = write_nonlinear_load_step_artifacts(
        partitions_out=args.partitions_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 nonlinear load-step: "
        f"{summary['status']} | partitions={summary['partition_step_counts']} | "
        f"spread_gate={summary['partition_spread_gate_passed']} | "
        f"full_load_gate={summary['full_load_gate_passed']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
