#!/usr/bin/env python3
"""Run the Engine v2 HIPRTC canonical-CSR residual/JVP hardware probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    pack_solver_model_buffers,
    run_linear_static_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.rtc_backend import (  # noqa: E402
    open_hip_rtc_csr_execution_context,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

DEFAULT_FIXTURE = (
    REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
)
_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_REPORT_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-residual-jvp-probe.v1"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile the package-owned HIPRTC CSR kernel and verify fused "
            "R=Ku-F/Jv=Kv against the Engine v2 CPU reference."
        )
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--load-pattern", default="LC_STRONG")
    parser.add_argument("--device-ordinal", type=int, default=0)
    parser.add_argument("--agent-enumerator", type=Path)
    parser.add_argument("--runtime-library", type=Path)
    parser.add_argument("--hiprtc-library", type=Path)
    parser.add_argument("--out", type=Path)
    return parser


def _resolve_enumerator(explicit: Path | None) -> str | None:
    if explicit is not None:
        return str(explicit) if explicit.is_file() else None
    discovered = shutil.which("rocm_agent_enumerator")
    if discovered is not None:
        return discovered
    for candidate in (
        Path("/opt/rocm/bin/rocm_agent_enumerator"),
        Path("/opt/rocm-6.0.2/bin/rocm_agent_enumerator"),
    ):
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate)
    return None


def _detect_architectures(executable: str | None) -> tuple[str, ...]:
    if executable is None:
        return ()
    try:
        completed = subprocess.run(
            [executable],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0:
        return ()
    return tuple(
        target
        for target in (
            token.strip().lower() for token in completed.stdout.split()
        )
        if target != "gfx000" and _ARCH_PATTERN.fullmatch(target)
    )


def _direction(dof_count: int) -> np.ndarray:
    indices = np.arange(1, dof_count + 1, dtype=np.float64)
    signs = np.where(indices.astype(np.int64) % 2 == 0, 1.0, -1.0)
    return np.ascontiguousarray(signs * indices * 1.0e-7, dtype="<f8")


def _metric(actual: np.ndarray, expected: np.ndarray) -> dict[str, Any]:
    error = np.asarray(actual, dtype=np.float64) - np.asarray(
        expected, dtype=np.float64
    )
    denominator = max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
    max_abs = float(np.max(np.abs(error))) if error.size else 0.0
    relative_l2 = float(np.linalg.norm(error) / denominator)
    return {
        "count": int(error.size),
        "max_abs_error": max_abs,
        "relative_l2_error": relative_l2,
        "passed": bool(max_abs <= 1.0e-8 or relative_l2 <= 1.0e-8),
    }


def _external_parity(
    actual: np.ndarray,
    expected: np.ndarray,
    free: np.ndarray,
    constrained: np.ndarray,
) -> dict[str, Any]:
    metrics = {
        "full": _metric(actual, expected),
        "free": _metric(actual[free], expected[free]),
        "constrained": _metric(
            actual[constrained], expected[constrained]
        ),
    }
    return {
        **metrics,
        "passed": all(value["passed"] for value in metrics.values()),
    }


def _base_report(
    *,
    status: str,
    reason_code: str | None,
    reason_detail: str | None,
    architecture: str | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "status": status,
        "requested_backend": "hip",
        "actual_backend": None,
        "evidence_scope": "native_hiprtc",
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": (
            None
            if reason_code is None
            else {"code": reason_code, "detail": reason_detail}
        ),
        "device_ordinal": args.device_ordinal,
        "architecture": architecture,
        "fixture": str(args.fixture),
        "load_pattern_id": args.load_pattern,
        "execution_environment": {
            "hip_launch_blocking": os.environ.get("HIP_LAUNCH_BLOCKING"),
            "timing_measured": False,
            "speedup_claim": False,
            "complexity_slope_claim": False,
        },
    }


def _emit(payload: dict[str, Any], out: Path | None) -> None:
    rendered = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    )
    if out is None:
        print(rendered)
    else:
        out.write_text(rendered + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    enumerator = _resolve_enumerator(args.agent_enumerator)
    architectures = _detect_architectures(enumerator)
    if (
        args.device_ordinal < 0
        or args.device_ordinal >= len(architectures)
    ):
        report = _base_report(
            status="unavailable",
            reason_code="hip_rtc_gfx_agent_unavailable",
            reason_detail=(
                "rocm_agent_enumerator did not report a real gfx* target "
                "for the requested device ordinal; no CPU fallback ran."
            ),
            architecture=None,
            args=args,
        )
        report["agent_enumerator"] = enumerator
        report["detected_architectures"] = list(architectures)
        _emit(report, args.out)
        return 2

    architecture = architectures[args.device_ordinal]
    report = _base_report(
        status="running",
        reason_code=None,
        reason_detail=None,
        architecture=architecture,
        args=args,
    )
    report["agent_enumerator"] = enumerator
    report["detected_architectures"] = list(architectures)

    context = None
    try:
        capability = probe_hip_capability(
            runtime_library=args.runtime_library,
            device_ordinal=args.device_ordinal,
        )
        report["capability_receipt"] = capability.to_dict()
        if capability.status != "ready":
            report.update(
                status="unavailable",
                reason={
                    "code": capability.status_code,
                    "detail": capability.message,
                },
            )
            _emit(report, args.out)
            return 2
        buffers = pack_solver_model_buffers(
            load_model_ir_v2(args.fixture),
            load_pattern_id=args.load_pattern,
        )
        authoritative = run_linear_static_v1(
            buffers, matrix_backend="dense"
        )
        plan = authoritative.execution_plan
        committed = authoritative.committed_state
        opened = open_hip_rtc_csr_execution_context(
            buffers,
            plan,
            committed,
            device_ordinal=args.device_ordinal,
            architecture=architecture,
            runtime_library=args.runtime_library,
            hiprtc_library=args.hiprtc_library,
        )
        context = opened.context
        report["context_open_receipt"] = opened.receipt.to_dict()
        if not opened.ready or opened.context is None:
            report.update(
                status="unavailable",
                reason=(
                    None
                    if opened.receipt.reason is None
                    else opened.receipt.reason.to_dict()
                ),
            )
            _emit(report, args.out)
            return 2

        direction = _direction(plan.dof_count)
        first = context.evaluate_residual_jvp(direction)
        repeat = context.evaluate_residual_jvp(direction)
        zero = context.evaluate_residual_jvp(
            np.zeros(plan.dof_count, dtype="<f8")
        )
        if (
            first.residual is None
            or first.jvp is None
            or repeat.residual is None
            or repeat.jvp is None
            or zero.residual is None
            or zero.jvp is None
        ):
            raise RuntimeError("A HIPRTC evaluation returned no output arrays.")

        free = plan.array("free_dofs").astype(np.int64, copy=False)
        constrained = plan.array("constrained_dofs").astype(
            np.int64, copy=False
        )
        cpu_residual = plan.operator.residual(committed.displacement_si)
        cpu_jvp = plan.operator.jvp(direction)
        external_residual = _external_parity(
            first.residual, cpu_residual, free, constrained
        )
        external_jvp = _external_parity(
            first.jvp, cpu_jvp, free, constrained
        )
        repeat_identical = bool(
            np.array_equal(first.residual, repeat.residual)
            and np.array_equal(first.jvp, repeat.jvp)
            and first.receipt.residual == repeat.receipt.residual
            and first.receipt.jvp == repeat.receipt.jvp
            and first.receipt.receipt_hash == repeat.receipt.receipt_hash
        )
        zero_exact = bool(
            zero.receipt.parity is not None
            and zero.receipt.parity.zero_direction_exact is True
            and np.array_equal(
                zero.jvp, np.zeros(plan.dof_count, dtype="<f8")
            )
        )
        delta = first.receipt.telemetry_delta
        exact_evaluation_counters = bool(
            delta.h2d_operation_count == 1
            and delta.d2h_operation_count == 2
            and delta.explicit_sync_count == 1
            and delta.kernel_launch_attempt_count == 1
            and delta.kernel_launch_count == 1
            and delta.allocation_count == 0
            and delta.blocking_copy_count == 0
            and delta.fallback_count == 0
        )
        open_telemetry = opened.receipt.telemetry
        exact_open_counters = bool(
            open_telemetry.child_allocation_attempt_count == 8
            and open_telemetry.child_allocation_success_count == 8
            and open_telemetry.child_initial_h2d_attempt_count == 5
            and open_telemetry.child_initial_h2d_success_count == 5
            and open_telemetry.fallback_count == 0
        )
        parity_verified = bool(
            first.receipt.status == "verified"
            and first.receipt.parity is not None
            and first.receipt.parity.passed
            and external_residual["passed"]
            and external_jvp["passed"]
        )
        verified = bool(
            opened.receipt.evidence_scope == "native_hiprtc"
            and first.receipt.evidence_scope == "native_hiprtc"
            and first.receipt.actual_backend == "hip"
            and first.receipt.promotion_eligible is False
            and parity_verified
            and repeat_identical
            and zero_exact
            and exact_open_counters
            and exact_evaluation_counters
        )
        report.update(
            status="verified" if verified else "failed",
            actual_backend="hip",
            reason=(
                None
                if verified
                else {
                    "code": "hip_rtc_probe_verification_failed",
                    "detail": "One or more parity/residency checks failed.",
                }
            ),
            committed_state={
                "state_hash": committed.state_hash,
                "epoch": committed.epoch,
                "role": committed.role,
            },
            execution_plan={
                "plan_hash": plan.plan_hash,
                "operator_hash": plan.operator_hash,
                "pattern_hash": plan.pattern_hash,
                "global_dof_count": plan.dof_count,
                "csr_nnz": int(
                    plan.array("csr_column_indices").size
                ),
            },
            first_evaluation=first.receipt.to_dict(),
            repeat_evaluation=repeat.receipt.to_dict(),
            zero_direction_evaluation=zero.receipt.to_dict(),
            verification={
                "external_cpu_oracle_role": (
                    "verification_only_never_fallback"
                ),
                "residual": external_residual,
                "jvp": external_jvp,
                "repeat_output_and_receipt_hashes_identical": (
                    repeat_identical
                ),
                "zero_direction_jvp_exact": zero_exact,
                "open_allocation_and_upload_counters_exact": (
                    exact_open_counters
                ),
                "evaluation_transfer_and_kernel_counters_exact": (
                    exact_evaluation_counters
                ),
                "fallback_count": context.receipt().telemetry.fallback_count,
            },
            structural_work_receipt=first.receipt.work.to_dict(),
            context_after_evaluations=context.receipt().to_dict(),
            claim_boundary={
                "cpu_compiled_csr_replay_only": True,
                "unsigned_v1_non_promoting": True,
                "signed_evidence_v2_required_for_promotion": True,
                "hip_element_assembly_proven": False,
                "solver_ready": False,
                "end_to_end_o_n_proven": False,
                "speedup_proven": False,
                "commercial_readiness": False,
            },
        )
        exit_code = 0 if verified else 3
    except Exception as exc:
        report.update(
            status="unavailable",
            actual_backend=None,
            reason={
                "code": getattr(exc, "code", "hip_rtc_probe_failed"),
                "detail": " ".join(str(exc).split())[:512],
            },
        )
        exit_code = 2
    finally:
        if context is not None:
            try:
                context.close()
                report["closed_context_receipt"] = context.receipt().to_dict()
            except Exception as exc:
                report["status"] = "failed"
                report["reason"] = {
                    "code": getattr(
                        exc, "code", "hip_rtc_probe_cleanup_failed"
                    ),
                    "detail": " ".join(str(exc).split())[:512],
                }
                exit_code = 3

    _emit(report, args.out)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
