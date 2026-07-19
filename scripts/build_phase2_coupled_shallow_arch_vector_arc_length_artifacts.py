#!/usr/bin/env python3
"""Build coupled two-DOF vector arc-length evidence artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.benchmark.coupled_shallow_arch_arc_length import (  # noqa: E402
    COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    build_coupled_shallow_arch_vector_arc_length_benchmark_seed,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = (
    PRODUCTIZATION / "phase2_coupled_shallow_arch_vector_arc_length_result.json"
)
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "phase2_coupled_shallow_arch_vector_arc_length_summary.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "coupled_shallow_arch_vector_arc_length_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-coupled-shallow-arch-vector-arc-length-artifacts.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


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


def build_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    result_payload = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result_payload)

    solver_metrics = result_payload["solver_result"]["metrics"]
    verification = result_payload["verification"]
    reduction = result_payload["exact_reduction_errors"]
    limit_bracket = result_payload["computed_first_limit_bracket"]
    finite_difference_rows = result_payload["finite_difference_rows"]
    claims = result_payload["claims"]
    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/solvers/nonlinear/vector_arc_length.py"),
                Path(
                    "src/structural_analysis/benchmark/"
                    "coupled_shallow_arch_arc_length.py"
                ),
                Path("src/structural_analysis/benchmark/geometric_nonlinear.py"),
                SCHEMA_PATH,
                Path(
                    "scripts/"
                    "build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py"
                ),
                Path("tests/test_nonlinear_vector_arc_length.py"),
                Path("tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py"),
                Path(
                    "tests/"
                    "test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py"
                ),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": result_payload["contract_pass"],
        "case_id": result_payload["case_id"],
        "analysis_type": result_payload["analysis_type"],
        "truth_basis": result_payload["truth_basis"],
        "equation_count": solver_metrics["equation_count"],
        "accepted_step_count": solver_metrics["accepted_step_count"],
        "rejected_step_count": solver_metrics["rejected_step_count"],
        "rollback_exact": solver_metrics["rollback_exact"],
        "fallback_count": solver_metrics["fallback_count"],
        "regularization_count": solver_metrics["regularization_count"],
        "maximum_checkpoint_residual_inf_norm_kn": solver_metrics[
            "maximum_checkpoint_residual_inf_norm_kn"
        ],
        "maximum_accepted_constraint_residual_m2": solver_metrics[
            "maximum_accepted_constraint_residual_m2"
        ],
        "maximum_augmented_condition_number": solver_metrics[
            "maximum_augmented_condition_number"
        ],
        "maximum_coupling_relation_absolute_error_m": reduction[
            "maximum_coupling_relation_absolute_error_m"
        ],
        "maximum_reduced_equilibrium_absolute_error_kn": reduction[
            "maximum_reduced_equilibrium_absolute_error_kn"
        ],
        "first_limit_load_relative_error": limit_bracket[
            "first_limit_load_relative_error"
        ],
        "maximum_tangent_absolute_error_kn_per_m": max(
            row["maximum_tangent_absolute_error_kn_per_m"]
            for row in finite_difference_rows
        ),
        "maximum_energy_gradient_absolute_error_kn": max(
            row["maximum_energy_gradient_absolute_error_kn"]
            for row in finite_difference_rows
        ),
        "path_gate_passed": verification["path_gate_passed"],
        "exact_scalar_reduction_gate_passed": verification[
            "exact_scalar_reduction_gate_passed"
        ],
        "limit_point_gate_passed": verification["limit_point_gate_passed"],
        "tangent_energy_finite_difference_gate_passed": verification[
            "tangent_energy_finite_difference_gate_passed"
        ],
        "checkpoint_restart_exact": verification["checkpoint_restart_exact"],
        "deterministic_replay_exact": verification["deterministic_replay_exact"],
        "path_contract_hash": verification["path_contract_hash"],
        "dense_multi_dof_vector_arc_length_claim": claims[
            "dense_multi_dof_vector_arc_length"
        ],
        "general_frame_shell_arc_length_claim": False,
        "lee_frame_snapthrough_claim": False,
        "material_geometric_coupling_claim": False,
        "production_sparse_backend_claim": False,
        "production_rocm_hip_parity_claim": False,
        "g1_full_building_closure_claim": False,
        "blockers_remaining": result_payload["blockers_remaining"],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_coupled_vector_arc_length_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_coupled_vector_arc_length_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_coupled_vector_arc_length_mismatch:{key}"
    return True, "phase2_coupled_vector_arc_length_consistent"


def write_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
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
        ok, message = check_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | "
        f"vector_path={summary['path_gate_passed']} | "
        f"limit={summary['limit_point_gate_passed']} | "
        f"restart={summary['checkpoint_restart_exact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
