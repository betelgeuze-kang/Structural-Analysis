#!/usr/bin/env python3
"""Execute deterministic M1–M5/L1–L2 planar corpus cases.

The runner emits internal execution, checkpoint, recovery, timing, and memory
receipts. It does not create external scientific reference or release authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import tempfile
import time
from typing import Any, Mapping, Sequence

from structural_analysis.api.planar_frame import (
    PlanarFrameConfig,
    analyze_planar_frame,
    validate_planar_frame_result,
)
from structural_analysis.model_ir import parse_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/materialize_planar_verification_corpus.py"
spec = importlib.util.spec_from_file_location(
    "materialize_planar_verification_corpus",
    GENERATOR,
)
if spec is None or spec.loader is None:
    raise RuntimeError("planar corpus generator is unavailable")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PlanarCorpusExecutionError(RuntimeError):
    """Raised when a corpus execution cannot produce its bounded receipt."""


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if os.uname().sysname == "Darwin" else value * 1024)


def _terminal_reason_code(result_ir: Mapping[str, Any]) -> str | None:
    unsupported = result_ir.get("unsupported_features")
    if not isinstance(unsupported, list):
        return None
    for row in unsupported:
        if not isinstance(row, Mapping):
            continue
        detail = row.get("detail")
        if isinstance(detail, str) and "terminal_reason=" in detail:
            reason = detail.split("terminal_reason=", 1)[1]
            reason = reason.split(".", 1)[0].split(",", 1)[0].strip()
            if reason:
                return reason
        reason_code = row.get("reason_code")
        if isinstance(reason_code, str) and reason_code:
            return reason_code
    return None


def _classify_execution(
    result_status: object,
    result_ir: Mapping[str, Any],
) -> tuple[str, str, str | None]:
    """Separate execution state from numerical convergence semantics."""

    public_status = str(result_status)
    internal_status = str(result_ir.get("status", ""))
    reason_code = _terminal_reason_code(result_ir)
    if internal_status == "blocked":
        return (
            "blocked",
            "not_applicable",
            reason_code or "solver_execution_blocked",
        )
    if public_status == "converged":
        return "completed", "converged", None
    if public_status == "not_converged":
        return "completed", "not_converged", reason_code
    if public_status == "not_run":
        return "not_run", "not_applicable", reason_code
    return "failed", "not_applicable", reason_code or "solver_execution_failed"


def execute_case(
    case_id: str,
    *,
    output_root: Path,
    matrix_backend: str,
    load_steps: int,
) -> dict[str, Any]:
    payload = generator.build_case(case_id)
    model_bytes = _serialized(payload).encode("utf-8")
    model_path = output_root / f"{case_id}.model-ir.v2.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(model_bytes)
    document = parse_model_ir_v2(payload, require_analysis_ready=True)
    before_rss = _peak_rss_bytes()
    started = time.perf_counter()
    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(
            load_steps=load_steps,
            maximum_iterations=40,
            residual_tolerance=1.0e-8,
            increment_tolerance_m=1.0e-10,
            matrix_backend=matrix_backend,
        ),
    )
    elapsed = time.perf_counter() - started
    after_rss = _peak_rss_bytes()
    report = validate_planar_frame_result(result)
    if report.artifact_contract_pass is not True:
        raise PlanarCorpusExecutionError(f"artifact_contract_blocked:{case_id}")
    result_path = output_root / f"{case_id}.result.json"
    report_path = output_root / f"{case_id}.report.json"
    checkpoint_path = output_root / f"{case_id}.checkpoint.json"
    _write_json(result_path, result.to_dict())
    _write_json(report_path, report.to_dict())
    checkpoint_available = False
    try:
        checkpoint = result.checkpoint_artifact()
    except ValueError:
        checkpoint = b""
    else:
        checkpoint_path.write_bytes(checkpoint)
        checkpoint_available = True

    result_ir = result.result_ir if isinstance(result.result_ir, Mapping) else {}
    engineering = result_ir.get("engineering_result_ir")
    engineering_hash = (
        engineering.get("engineering_result_hash")
        if isinstance(engineering, Mapping)
        else None
    )
    execution_status, numerical_status, reason_code = _classify_execution(
        result.status,
        result_ir,
    )
    row = {
        "schema_version": "planar-corpus-execution-case.v1",
        "case_id": case_id,
        "profile": generator.PROFILE,
        "contract_pass": report.contract_pass,
        "status": result.status,
        "internal_status": result_ir.get("status"),
        "execution_status": execution_status,
        "numerical_status": numerical_status,
        "reason_code": reason_code,
        "converged": result.converged,
        "artifact_contract_pass": report.artifact_contract_pass,
        "execution_contract_pass": report.execution_contract_pass,
        "diagnostic_authority": report.diagnostic_authority,
        "numerical_result_authority": report.numerical_result_authority,
        "engineering_result_authority": report.engineering_result_authority,
        "node_count": len(payload["nodes"]),
        "member_count": len(payload["elements"]),
        "matrix_backend": matrix_backend,
        "load_steps": load_steps,
        "elapsed_seconds": elapsed,
        "peak_rss_bytes": max(before_rss, after_rss),
        "model_sha256": _sha256_file(model_path),
        "result_sha256": _sha256_file(result_path),
        "report_sha256": _sha256_file(report_path),
        "result_hash": result.result_hash,
        "engineering_result_hash": engineering_hash,
        "checkpoint_available": checkpoint_available,
        "checkpoint_sha256": (
            _sha256_file(checkpoint_path) if checkpoint_available else None
        ),
        "claim_boundary": (
            "This is deterministic internal execution evidence for the declared "
            "bounded planar corpus case. It does not provide an independent reference, "
            "external V&V, performance guarantee, design authority, or release eligibility."
        ),
    }
    _write_json(output_root / f"{case_id}.execution-receipt.json", row)
    return row


def _required_convergence_error(rows: Sequence[Mapping[str, Any]]) -> str | None:
    groups = (
        (
            "corpus_cases_blocked",
            [row["case_id"] for row in rows if row["execution_status"] == "blocked"],
        ),
        (
            "corpus_cases_failed",
            [row["case_id"] for row in rows if row["execution_status"] == "failed"],
        ),
        (
            "corpus_cases_not_run",
            [row["case_id"] for row in rows if row["execution_status"] == "not_run"],
        ),
        (
            "corpus_cases_not_converged",
            [
                row["case_id"]
                for row in rows
                if row["numerical_status"] == "not_converged"
            ],
        ),
    )
    failures = [f"{label}:{','.join(case_ids)}" for label, case_ids in groups if case_ids]
    return ";".join(failures) if failures else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(generator.CASE_SIZES), action="append")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--matrix-backend",
        choices=("numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"),
        default="scipy_sparse_spsolve_cpu",
    )
    parser.add_argument("--load-steps", type=int, default=1)
    parser.add_argument("--require-converged", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    selected = args.case or list(generator.CASE_SIZES)
    rows = [
        execute_case(
            case_id,
            output_root=args.out_dir,
            matrix_backend=args.matrix_backend,
            load_steps=args.load_steps,
        )
        for case_id in selected
    ]
    if args.require_converged:
        failure = _required_convergence_error(rows)
        if failure:
            raise PlanarCorpusExecutionError(failure)
    receipt = {
        "schema_version": "planar-corpus-execution-matrix.v1",
        "contract_pass": all(row["artifact_contract_pass"] is True for row in rows),
        "profile": generator.PROFILE,
        "case_count": len(rows),
        "completed_case_count": sum(
            row["execution_status"] == "completed" for row in rows
        ),
        "blocked_case_count": sum(row["execution_status"] == "blocked" for row in rows),
        "failed_case_count": sum(row["execution_status"] == "failed" for row in rows),
        "not_run_case_count": sum(row["execution_status"] == "not_run" for row in rows),
        "converged_case_count": sum(row["numerical_status"] == "converged" for row in rows),
        "not_converged_case_count": sum(
            row["numerical_status"] == "not_converged" for row in rows
        ),
        "cases": rows,
        "claim_boundary": (
            "This matrix records internal deterministic execution and resource evidence. "
            "Scientific acceptance and external solver credit remain separate gates."
        ),
    }
    _write_json(args.out_dir / "execution-matrix.json", receipt)
    if args.json:
        print(_serialized(receipt), end="")
    else:
        print(
            "planar corpus execution: "
            f"{receipt['converged_case_count']}/{receipt['case_count']} converged"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
