#!/usr/bin/env python3
"""Run an operator-attached large-model input and write an execution receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import time
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.api.core import AnalysisConfig, analyze, load_model, validate  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 7200
DEFAULT_MEMORY_LIMIT_GB = 64.0
SCHEMA_VERSION = "phase3-large-model-execution-receipt.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _peak_memory_gb() -> float:
    # Linux reports KiB for ru_maxrss. The receipt is an approximate diagnostic,
    # not an enforcement primitive.
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / (1024.0 * 1024.0)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")


def build_large_model_execution_receipt(
    *,
    model_path: Path,
    source_id: str,
    case_id: str,
    out_path: Path,
    source_sha256: str | None = None,
    scorecard_or_review_path: Path | None = None,
    result_out: Path | None = None,
    report_out: Path | None = None,
    analysis_type: str = "model_health",
    solver: str = "phase3_large_model_operator_execution",
    tolerance: float = 1.0e-8,
    max_iterations: int = 0,
    matrix_backend: str = "numpy_linalg_solve_dense",
    reference: Path | None = None,
    memory_limit_gb: float = DEFAULT_MEMORY_LIMIT_GB,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner_command: str = "",
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    resolved_model = model_path.resolve()
    computed_sha = _sha256(resolved_model)
    expected_sha = source_sha256 or computed_sha
    source_sha256_match = computed_sha == expected_sha
    result_payload: dict[str, Any] | None = None
    report_payload: dict[str, Any] | None = None
    exception: str | None = None
    crashed = False
    oom = False
    exit_code = 1

    try:
        model = load_model(resolved_model)
        result = analyze(
            model,
            AnalysisConfig(
                analysis_type=analysis_type,
                solver=solver,
                tolerance=tolerance,
                max_iterations=max_iterations,
                matrix_backend=matrix_backend,
            ),
        )
        report = validate(result, reference)
        result_payload = result.to_dict()
        report_payload = report.to_dict()
        exit_code = 0 if report.contract_pass else 2
    except MemoryError as exc:
        oom = True
        crashed = True
        exception = f"{exc.__class__.__name__}: {exc}"
        exit_code = 137
    except Exception as exc:  # pragma: no cover - exercised through blocked CLI paths.
        crashed = True
        exception = f"{exc.__class__.__name__}: {exc}"
        exit_code = 1

    runtime_seconds = time.perf_counter() - started_perf
    if result_payload is not None and result_out is not None:
        _write_json(result_out, result_payload)
    if report_payload is not None and report_out is not None:
        _write_json(report_out, report_payload)

    blockers: list[str] = []
    if not source_sha256_match:
        blockers.append("source_sha256_mismatch")
    if scorecard_or_review_path is None:
        blockers.append("scorecard_or_review_missing")
    elif not scorecard_or_review_path.exists():
        blockers.append("scorecard_or_review_path_missing")
    if crashed:
        blockers.append("execution_crashed")
    if oom:
        blockers.append("execution_oom")
    if exit_code != 0:
        blockers.append("validation_contract_not_pass")

    peak_memory_gb = _peak_memory_gb()
    validation_contract_pass = bool(
        report_payload is not None and report_payload.get("contract_pass") is True
    )
    if runtime_seconds > timeout_seconds:
        blockers.append("runtime_seconds_above_declared_timeout")
    if peak_memory_gb > memory_limit_gb:
        blockers.append("peak_memory_above_declared_limit")
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = bool(
        not blockers
        and validation_contract_pass
        and not crashed
        and not oom
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started.isoformat(),
        "source_id": source_id,
        "case_id": case_id,
        "source_file": str(model_path),
        "source_sha256": computed_sha,
        "source_sha256_expected": expected_sha,
        "source_sha256_match": source_sha256_match,
        "runner_command": runner_command,
        "analysis_type": analysis_type,
        "solver": solver,
        "matrix_backend": matrix_backend,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "memory_limit_gb": memory_limit_gb,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "peak_memory_gb": peak_memory_gb,
        "crashed": crashed,
        "oom": oom,
        "exception": exception or "",
        "scorecard_or_review_path": str(scorecard_or_review_path or ""),
        "result_out": str(result_out or ""),
        "report_out": str(report_out or ""),
        "analysis_result_status": str((result_payload or {}).get("status", "")),
        "validation_report_status": str((report_payload or {}).get("status", "")),
        "validation_contract_pass": validation_contract_pass,
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "contract_pass": contract_pass,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "large_model_execution_receipt_claim": contract_pass,
        "blockers": blockers,
        "claim_boundary": (
            "This is a single operator-attached large-model execution receipt. It "
            "does not acquire sources, approve licenses, create reference outputs, "
            "satisfy the required 2/2 large-model quantity gate, or close Phase 3/"
            "Developer Preview RC by itself."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-sha256")
    parser.add_argument("--scorecard-or-review", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--result-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--analysis-type", default="model_health")
    parser.add_argument("--solver", default="phase3_large_model_operator_execution")
    parser.add_argument("--tolerance", type=float, default=1.0e-8)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument(
        "--matrix-backend",
        choices=["numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"],
        default="numpy_linalg_solve_dense",
    )
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--memory-limit-gb", type=float, default=DEFAULT_MEMORY_LIMIT_GB)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner_command = "python3 scripts/run_phase3_large_model_execution_receipt.py " + " ".join(
        sys.argv[1:] if argv is None else argv
    )
    payload = build_large_model_execution_receipt(
        model_path=args.model,
        source_id=args.source_id,
        case_id=args.case_id,
        out_path=args.out,
        source_sha256=args.source_sha256,
        scorecard_or_review_path=args.scorecard_or_review,
        result_out=args.result_out,
        report_out=args.report_out,
        analysis_type=args.analysis_type,
        solver=args.solver,
        tolerance=args.tolerance,
        max_iterations=args.max_iterations,
        matrix_backend=args.matrix_backend,
        reference=args.reference,
        memory_limit_gb=args.memory_limit_gb,
        timeout_seconds=args.timeout_seconds,
        runner_command=runner_command,
    )
    _write_json(args.out, payload)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 large-model execution receipt: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"runtime={payload['runtime_seconds']:.3f}s | blockers={len(payload['blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
