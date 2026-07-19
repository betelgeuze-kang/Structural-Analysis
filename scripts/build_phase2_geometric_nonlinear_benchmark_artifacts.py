#!/usr/bin/env python3
"""Build narrow Euler, modal P-Delta, and shallow-arch evidence artifacts."""

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
from structural_analysis.benchmark.geometric_nonlinear import (  # noqa: E402
    build_geometric_nonlinear_benchmark_seed,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_geometric_nonlinear_benchmark_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_geometric_nonlinear_benchmark_summary.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/geometric_nonlinear_benchmark_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-geometric-nonlinear-benchmark-artifacts.v1"
BLOCKERS_REMAINING = [
    "general_2d_3d_pdelta_frame_not_implemented",
    "lee_frame_snapthrough_not_implemented",
    "arc_length_path_following_not_implemented",
    "continuum_cantilever_large_rotation_not_implemented",
    "general_corotational_frame_shell_elements_not_implemented",
    "material_geometric_nonlinear_coupling_not_verified",
    "published_or_experimental_geometric_validation_not_attached",
    "production_sparse_rocm_hip_geometric_parity_not_verified",
]
CLAIM_BOUNDARY = (
    "This receipt verifies a pinned Euler-Bernoulli column against the closed-form "
    "critical load and sine mode, first-mode P-Delta amplification using the same "
    "finite-element K/Kg eigenpair, and the exact displacement-controlled path of "
    "a symmetric two-bar shallow arch through its first limit point. It is not a "
    "general frame solver and does not claim a P-Delta frame, Lee frame, arc-length "
    "path following, continuum cantilever large rotation, general corotational "
    "frame/shell kinematics, material-geometric coupling, or CPU/HIP parity."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def build_phase2_geometric_nonlinear_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    first = build_geometric_nonlinear_benchmark_seed()
    second = build_geometric_nonlinear_benchmark_seed()
    deterministic_replay = first == second
    benchmark_rows = first["benchmarks"]
    implemented_contract_pass = bool(
        first["contract_pass"]
        and deterministic_replay
        and all(row["contract_pass"] for row in benchmark_rows.values())
    )
    result_payload = {
        **first,
        "status": "partial" if implemented_contract_pass else "blocked",
        "contract_pass": implemented_contract_pass,
        "verification": {
            "euler_column_gate_passed": benchmark_rows["euler_column"][
                "contract_pass"
            ],
            "modal_pdelta_column_gate_passed": benchmark_rows[
                "modal_pdelta_column"
            ]["contract_pass"],
            "two_bar_shallow_arch_gate_passed": benchmark_rows[
                "two_bar_shallow_arch"
            ]["contract_pass"],
            "deterministic_replay_exact": deterministic_replay,
        },
        "implemented_benchmarks_contract_pass": implemented_contract_pass,
        "blockers_remaining": BLOCKERS_REMAINING,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result_payload)

    euler = benchmark_rows["euler_column"]
    pdelta = benchmark_rows["modal_pdelta_column"]
    arch = benchmark_rows["two_bar_shallow_arch"]
    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/benchmark/geometric_nonlinear.py"),
                SCHEMA_PATH,
                Path(
                    "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py"
                ),
                Path("tests/test_geometric_nonlinear_benchmarks.py"),
                Path(
                    "tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py"
                ),
            ],
            repo_root=repo_root,
        ),
        "status": result_payload["status"],
        "contract_pass": implemented_contract_pass,
        "truth_class": result_payload["truth_class"],
        "analysis_type": result_payload["analysis_type"],
        "euler_column_gate_passed": euler["contract_pass"],
        "euler_finest_relative_error": euler["finest_relative_error"],
        "euler_minimum_convergence_order": min(
            euler["observed_convergence_orders"]
        ),
        "modal_pdelta_column_gate_passed": pdelta["contract_pass"],
        "modal_pdelta_maximum_relative_error": max(
            row["relative_error"] for row in pdelta["load_rows"]
        ),
        "two_bar_shallow_arch_gate_passed": arch["contract_pass"],
        "shallow_arch_first_limit_load_kn": arch["first_limit_point"][
            "equilibrium_load_kn"
        ],
        "deterministic_replay_exact": deterministic_replay,
        "implemented_benchmarks_contract_pass": implemented_contract_pass,
        "geometric_nonlinear_benchmark_breadth_claim": False,
        "general_frame_pdelta_claim": False,
        "lee_frame_snapthrough_claim": False,
        "arc_length_path_following_claim": False,
        "continuum_cantilever_large_rotation_claim": False,
        "general_2d_3d_geometric_stiffness_claim": False,
        "blockers_remaining": BLOCKERS_REMAINING,
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_geometric_nonlinear_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_geometric_nonlinear_benchmark_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_geometric_nonlinear_benchmark_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_geometric_nonlinear_benchmark_mismatch:{key}"
    return True, "phase2_geometric_nonlinear_benchmark_consistent"


def write_phase2_geometric_nonlinear_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_geometric_nonlinear_benchmark_artifacts(
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
        ok, message = check_phase2_geometric_nonlinear_benchmark_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | "
        f"implemented={summary['implemented_benchmarks_contract_pass']} | "
        f"breadth={summary['geometric_nonlinear_benchmark_breadth_claim']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
