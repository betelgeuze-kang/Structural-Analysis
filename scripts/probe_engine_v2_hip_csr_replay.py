#!/usr/bin/env python3
"""Run one strict native HIP CSR residual/JVP replay and CPU oracle check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    compile_execution_plan,
    create_initial_state,
    load_hip_csr_kernel_artifact,
    open_hip_operator_execution_context,
    parse_hip_csr_kernel_artifact_receipt,
    verify_hip_residual_jvp_parity,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load a prebuilt AOT kernel and run one native, no-fallback "
            "canonical-CSR residual/JVP verification replay."
        )
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--load-pattern", required=True)
    parser.add_argument("--device-ordinal", type=int, default=0)
    parser.add_argument("--runtime-library", type=Path)
    parser.add_argument(
        "--direction",
        choices=("ones", "zero", "ramp"),
        default="ones",
    )
    parser.add_argument("--out", type=Path)
    return parser


def _direction(mode: str, dof_count: int) -> np.ndarray:
    if mode == "zero":
        return np.zeros(dof_count, dtype="<f8")
    if mode == "ramp":
        return np.arange(1, dof_count + 1, dtype="<f8")
    return np.ones(dof_count, dtype="<f8")


def _emit(payload: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output is None:
        print(rendered)
    else:
        output.write_text(rendered + "\n", encoding="utf-8")


def _failure(exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-hip-csr-replay-probe.v1",
        "status": "unavailable",
        "status_code": str(getattr(exc, "code", type(exc).__name__)),
        "path": str(getattr(exc, "path", "/")),
        "message": str(getattr(exc, "message", str(exc)))[:512],
        "actual_backend": None,
        "fallback_used": False,
        "context_receipt": None,
        "result_receipt": None,
        "parity_receipt": None,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    context = None
    try:
        manifest = json.loads(args.artifact_receipt.read_text(encoding="utf-8"))
        artifact_receipt = parse_hip_csr_kernel_artifact_receipt(manifest)
        kernel = load_hip_csr_kernel_artifact(
            args.artifact,
            expected_sha256=args.expected_sha256 or artifact_receipt.library_hash,
            artifact_receipt=artifact_receipt,
        )
        model = load_model_ir_v2(args.model)
        buffers = pack_solver_model_buffers(
            model, load_pattern_id=args.load_pattern
        )
        plan = compile_execution_plan(buffers)
        state = create_initial_state(plan)
        opened = open_hip_operator_execution_context(
            buffers,
            plan,
            state,
            kernel=kernel,
            device_ordinal=args.device_ordinal,
            runtime_library=args.runtime_library,
        )
        if not opened.ready or opened.context is None:
            operator_cleanup_receipt = None
            if opened.context is not None:
                try:
                    opened.context.close()
                except Exception as cleanup_exc:
                    payload = _failure(cleanup_exc)
                    payload["context_receipt"] = opened.context.receipt().to_dict()
                    payload["operator_cleanup_receipt"] = (
                        opened.context.receipt().to_dict()
                    )
                    _emit(payload, args.out)
                    return 3
                operator_cleanup_receipt = opened.context.receipt().to_dict()
            foundation_cleanup_receipt = None
            if opened.cleanup_owner is not None:
                try:
                    opened.cleanup_owner.close()
                except Exception as cleanup_exc:
                    payload = _failure(cleanup_exc)
                    payload["context_receipt"] = opened.receipt.to_dict()
                    payload["foundation_cleanup_receipt"] = (
                        opened.cleanup_owner.receipt().to_dict()
                    )
                    _emit(payload, args.out)
                    return 3
                foundation_cleanup_receipt = (
                    opened.cleanup_owner.receipt().to_dict()
                )
            payload = {
                "schema_version": "structural-analysis-hip-csr-replay-probe.v1",
                "status": "unavailable",
                "status_code": (
                    opened.receipt.reason.code
                    if opened.receipt.reason is not None
                    else "hip_operator_context_unavailable"
                ),
                "actual_backend": None,
                "fallback_used": False,
                "artifact_receipt_hash": artifact_receipt.receipt_hash,
                "context_receipt": opened.receipt.to_dict(),
                "operator_cleanup_receipt": operator_cleanup_receipt,
                "foundation_cleanup_receipt": foundation_cleanup_receipt,
                "result_receipt": None,
                "parity_receipt": None,
            }
            _emit(payload, args.out)
            return 2
        context = opened.context
        result = context.evaluate_for_verification(
            _direction(args.direction, plan.dof_count)
        )
        parity = verify_hip_residual_jvp_parity(
            result, plan=plan, committed_state=state
        )
        status = "pass" if parity.status == "pass" else "parity_failed"
        live_context_receipt = context.receipt().to_dict()
        context.close()
        closed_context_receipt = context.receipt().to_dict()
        context = None
        payload = {
            "schema_version": "structural-analysis-hip-csr-replay-probe.v1",
            "status": status,
            "status_code": f"hip_native_csr_replay_{status}",
            "actual_backend": "hip_native",
            "fallback_used": False,
            "artifact_receipt_hash": artifact_receipt.receipt_hash,
            "context_receipt": live_context_receipt,
            "closed_context_receipt": closed_context_receipt,
            "result_receipt": result.to_dict(),
            "parity_receipt": parity.to_dict(),
        }
        _emit(payload, args.out)
        return 0 if parity.status == "pass" else 4
    except Exception as exc:
        error = exc
        if context is not None:
            try:
                context.close()
                context = None
            except Exception as cleanup_exc:
                error = cleanup_exc
        try:
            _emit(_failure(error), args.out)
        except OSError:
            print(json.dumps(_failure(error), sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
