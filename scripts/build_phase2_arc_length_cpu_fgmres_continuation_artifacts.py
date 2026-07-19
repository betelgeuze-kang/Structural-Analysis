#!/usr/bin/env python3
"""Build complete short-path CPU FGMRES arc-length integration artifacts."""

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
from structural_analysis.benchmark.arc_length_fgmres_continuation import (  # noqa: E402
    ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY,
    build_arc_length_cpu_fgmres_continuation_seed,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = (
    PRODUCTIZATION / "phase2_arc_length_cpu_fgmres_continuation_result.json"
)
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "phase2_arc_length_cpu_fgmres_continuation_summary.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "arc_length_cpu_fgmres_continuation_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = (
    "phase2-arc-length-cpu-fgmres-continuation-artifacts.v1"
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def build_phase2_arc_length_cpu_fgmres_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    result_payload = build_arc_length_cpu_fgmres_continuation_seed()
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result_payload)

    solver_result = result_payload["solver_result"]
    solver_metrics = solver_result["metrics"]
    verification = result_payload["verification"]
    claims = result_payload["claims"]
    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path(
                    "src/structural_analysis/solvers/nonlinear/"
                    "vector_arc_length.py"
                ),
                Path(
                    "src/structural_analysis/engine_v2/cpu_fgmres_tangent.py"
                ),
                Path("src/structural_analysis/engine_v2/cpu_fgmres.py"),
                Path(
                    "src/structural_analysis/benchmark/"
                    "coupled_shallow_arch_arc_length.py"
                ),
                Path(
                    "src/structural_analysis/benchmark/"
                    "arc_length_fgmres_bridge.py"
                ),
                Path(
                    "src/structural_analysis/benchmark/"
                    "arc_length_fgmres_continuation.py"
                ),
                SCHEMA_PATH,
                Path(
                    "scripts/"
                    "build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py"
                ),
                Path("tests/test_nonlinear_vector_arc_length.py"),
                Path("tests/test_engine_v2_cpu_fgmres_tangent.py"),
                Path("tests/test_arc_length_cpu_fgmres_continuation.py"),
                Path(
                    "tests/"
                    "test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py"
                ),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": result_payload["contract_pass"],
        "case_id": result_payload["case_id"],
        "analysis_type": result_payload["analysis_type"],
        "tangent_solver_profile": result_payload["tangent_solver_profile"],
        "tangent_solver_mode": result_payload["tangent_solver_mode"],
        "tangent_solver_contract_hash": result_payload[
            "tangent_solver_contract_hash"
        ],
        "path_contract_hash": solver_result["path_contract_hash"],
        "accepted_step_count": solver_metrics["accepted_step_count"],
        "rejected_step_count": solver_metrics["rejected_step_count"],
        "rollback_exact": solver_metrics["rollback_exact"],
        "final_primary_displacement_m": solver_metrics[
            "final_free_displacements_m"
        ][0],
        "final_load_factor": solver_metrics["final_load_factor"],
        "maximum_checkpoint_residual_inf_norm_kn": solver_metrics[
            "maximum_checkpoint_residual_inf_norm_kn"
        ],
        "maximum_accepted_constraint_residual_m2": solver_metrics[
            "maximum_accepted_constraint_residual_m2"
        ],
        "tangent_solve_count": verification["tangent_solve_count"],
        "maximum_tangent_solve_iteration_count": verification[
            "maximum_tangent_solve_iteration_count"
        ],
        "maximum_tangent_solve_explicit_residual_inf_norm_kn": verification[
            "maximum_tangent_solve_explicit_residual_inf_norm_kn"
        ],
        "path_gate_passed": verification["path_gate_passed"],
        "limit_point_crossed": verification["limit_point_crossed"],
        "negative_load_branch_reached": verification[
            "negative_load_branch_reached"
        ],
        "external_tangent_integration_gate_passed": verification[
            "external_tangent_integration_gate_passed"
        ],
        "all_tangent_solves_ready": verification[
            "all_tangent_solves_ready"
        ],
        "rollback_evidence_passed": verification[
            "rollback_evidence_passed"
        ],
        "checkpoint_restart_exact": verification["checkpoint_restart_exact"],
        "deterministic_replay_exact": verification[
            "deterministic_replay_exact"
        ],
        "dense_augmented_reference_gate_passed": verification[
            "dense_augmented_reference_gate_passed"
        ],
        "maximum_dense_reference_displacement_absolute_error_m": verification[
            "maximum_dense_reference_displacement_absolute_error_m"
        ],
        "maximum_dense_reference_load_factor_absolute_error": verification[
            "maximum_dense_reference_load_factor_absolute_error"
        ],
        "maximum_coupling_relation_absolute_error_m": verification[
            "maximum_coupling_relation_absolute_error_m"
        ],
        "maximum_reduced_equilibrium_absolute_error_kn": verification[
            "maximum_reduced_equilibrium_absolute_error_kn"
        ],
        "fallback_count": verification["fallback_count"],
        "regularization_count": verification["regularization_count"],
        "tangent_solve_hashes": verification["tangent_solve_hashes"],
        "complete_short_path_cpu_fgmres_arc_length_integration_claim": claims[
            "complete_short_path_cpu_fgmres_arc_length_integration"
        ],
        "engine_v2_cpu_fgmres_every_tangent_solve_claim": claims[
            "engine_v2_cpu_fgmres_every_tangent_solve"
        ],
        "general_frame_shell_arc_length_claim": False,
        "lee_frame_snapthrough_claim": False,
        "production_scale_sparse_preconditioner_claim": False,
        "production_rocm_hip_nonlinear_parity_claim": False,
        "g1_full_building_closure_claim": False,
        "blockers_remaining": result_payload["blockers_remaining"],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_arc_length_cpu_fgmres_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_arc_length_cpu_fgmres_continuation_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_arc_length_fgmres_continuation_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_arc_length_fgmres_continuation_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_arc_length_fgmres_continuation_mismatch:{key}"
    return True, "phase2_arc_length_fgmres_continuation_consistent"


def write_phase2_arc_length_cpu_fgmres_continuation_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_arc_length_cpu_fgmres_continuation_artifacts(
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
        ok, message = check_phase2_arc_length_cpu_fgmres_continuation_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_arc_length_cpu_fgmres_continuation_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | "
        f"steps={summary['accepted_step_count']} | "
        f"tangent_solves={summary['tangent_solve_count']} | "
        f"negative_load={summary['negative_load_branch_reached']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
