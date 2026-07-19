#!/usr/bin/env python3
"""Build scalar shallow-arch arc-length path-following evidence artifacts."""

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
from structural_analysis.benchmark.shallow_arch_arc_length import (  # noqa: E402
    SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    build_shallow_arch_arc_length_benchmark_seed,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_shallow_arch_arc_length_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_shallow_arch_arc_length_summary.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/shallow_arch_arc_length_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-shallow-arch-arc-length-artifacts.v1"


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


def build_phase2_shallow_arch_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    result_payload = build_shallow_arch_arc_length_benchmark_seed()
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result_payload)

    solver_result = result_payload["solver_result"]
    solver_metrics = solver_result["metrics"]
    verification = result_payload["verification"]
    limit_bracket = result_payload["computed_first_limit_bracket"]
    tangent_rows = result_payload["consistent_tangent_finite_difference_rows"]
    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/solvers/nonlinear/arc_length.py"),
                Path("src/structural_analysis/benchmark/shallow_arch_arc_length.py"),
                Path("src/structural_analysis/benchmark/geometric_nonlinear.py"),
                SCHEMA_PATH,
                Path("scripts/build_phase2_shallow_arch_arc_length_artifacts.py"),
                Path("tests/test_nonlinear_arc_length.py"),
                Path("tests/test_shallow_arch_arc_length_benchmark.py"),
                Path("tests/test_build_phase2_shallow_arch_arc_length_artifacts.py"),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": result_payload["contract_pass"],
        "case_id": result_payload["case_id"],
        "analysis_type": result_payload["analysis_type"],
        "truth_basis": result_payload["truth_basis"],
        "accepted_step_count": solver_metrics["accepted_step_count"],
        "rejected_step_count": solver_metrics["rejected_step_count"],
        "rollback_exact": solver_metrics["rollback_exact"],
        "fallback_count": solver_metrics["fallback_count"],
        "regularization_count": solver_metrics["regularization_count"],
        "first_limit_load_relative_error": limit_bracket[
            "first_limit_load_relative_error"
        ],
        "maximum_tangent_finite_difference_error_kn_per_m": max(
            row["absolute_error_kn_per_m"] for row in tangent_rows
        ),
        "path_gate_passed": verification["path_gate_passed"],
        "limit_point_gate_passed": verification["limit_point_gate_passed"],
        "tangent_finite_difference_gate_passed": verification[
            "tangent_finite_difference_gate_passed"
        ],
        "checkpoint_restart_exact": verification["checkpoint_restart_exact"],
        "deterministic_replay_exact": verification["deterministic_replay_exact"],
        "scalar_arc_length_path_following_claim": result_payload["claims"][
            "scalar_arc_length_path_following"
        ],
        "shallow_arch_limit_point_crossing_claim": result_payload["claims"][
            "shallow_arch_limit_point_crossing"
        ],
        "multi_dof_frame_shell_arc_length_claim": False,
        "lee_frame_snapthrough_claim": False,
        "geometric_nonlinear_benchmark_breadth_claim": False,
        "production_rocm_hip_parity_claim": False,
        "blockers_remaining": result_payload["blockers_remaining"],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_shallow_arch_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_shallow_arch_arc_length_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_shallow_arch_arc_length_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_shallow_arch_arc_length_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_shallow_arch_arc_length_mismatch:{key}"
    return True, "phase2_shallow_arch_arc_length_consistent"


def write_phase2_shallow_arch_arc_length_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_shallow_arch_arc_length_artifacts(
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
        ok, message = check_phase2_shallow_arch_arc_length_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_shallow_arch_arc_length_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | "
        f"path={summary['path_gate_passed']} | "
        f"limit={summary['limit_point_gate_passed']} | "
        f"restart={summary['checkpoint_restart_exact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
