#!/usr/bin/env python3
"""Build PM-scoped strict CI evidence for NDTHA and HIP release promises."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_NDTHA_LONG_PROFILE = Path("implementation/phase1/ndtha_long_profile_report.json")
DEFAULT_SOLVER_HIP_E2E = Path("implementation/phase1/solver_hip_e2e_contract_report.json")
DEFAULT_RUNTIME_POLICY = Path("implementation/phase1/release_evidence/productization/solver_runtime_backend_policy.json")
DEFAULT_ZERO_COPY_STRICT = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_NDTHA_OUT = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_ndtha_report.json")
DEFAULT_HIP_OUT = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_hip_report.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _checks(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("checks")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("status", "")).strip().lower() == "ready"
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _host_copy_share(strict_probe: dict[str, Any]) -> float | None:
    for source in (strict_probe, _summary(strict_probe)):
        for key in ("host_copy_share", "host_copy_share_ratio"):
            if key in source:
                return _as_float(source[key], 1.0)
    host_bytes = _as_float(strict_probe.get("host_copy_bytes"), -1.0)
    tensor_bytes = _as_float(strict_probe.get("tensor_bytes"), 0.0)
    if host_bytes >= 0 and tensor_bytes > 0:
        return host_bytes / tensor_bytes
    return None


def _report(kind: str, *, checks: dict[str, bool], summary: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": "pm-strict-ci-report.v1",
        "kind": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "summary": summary,
        "artifacts": artifacts,
        "claim_boundary": (
            "This is a PM-scoped strict CI artifact. It verifies the release promise named by kind and does "
            "not replace broader monolithic CI gates."
        ),
    }


def build_reports(
    *,
    ndtha_long_profile_path: Path,
    solver_hip_e2e_path: Path,
    runtime_policy_path: Path,
    zero_copy_strict_path: Path,
    min_device_residency: float,
    max_host_copy_share: float,
    cpu_only_product_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ndtha = _load_json(ndtha_long_profile_path)
    ndtha_checks = _checks(ndtha)
    ndtha_summary = _summary(ndtha)
    ndtha_report = _report(
        "require_ndtha",
        checks={
            "ndtha_long_profile_contract_pass": _reason_pass(ndtha),
            "ndtha_all_runs_pass": bool(ndtha_checks.get("all_runs_pass", False)),
            "ndtha_rust_backend_all_runs_pass": bool(ndtha_checks.get("rust_backend_all_runs_pass", False)),
            "ndtha_elapsed_cov_pass": bool(ndtha_checks.get("elapsed_cov_pass", False)),
            "ndtha_peak_vram_cov_pass": bool(ndtha_checks.get("peak_vram_cov_pass", False)),
        },
        summary={
            "ndtha_long_profile_reason_code": str(ndtha.get("reason_code", "")),
            "elapsed_wall_s_mean": ndtha_summary.get("elapsed_wall_s_mean"),
            "peak_vram_mb_mean": ndtha_summary.get("peak_vram_mb_mean"),
        },
        artifacts={"ndtha_long_profile": str(ndtha_long_profile_path)},
    )

    hip = _load_json(solver_hip_e2e_path)
    policy = _load_json(runtime_policy_path)
    strict_probe = _load_json(zero_copy_strict_path)
    hip_checks = _checks(hip)
    hip_summary = _summary(hip)
    host_copy_share = _host_copy_share(strict_probe)
    device_residency = _as_float(hip_summary.get("device_residency_ratio_min"), 0.0)
    release_cpu_fallback_forbidden = bool(
        not policy.get("cpu_solver_fallback_detected", True)
        and not policy.get("cpu_fallback_allowed_for_official_solver_closure", True)
    )
    hip_report = _report(
        "require_hip" if not cpu_only_product_mode else "cpu_only_product_scope",
        checks={
            "solver_hip_e2e_contract_pass": bool(cpu_only_product_mode or _reason_pass(hip)),
            "all_main_loops_gpu_pass": bool(cpu_only_product_mode or hip_checks.get("all_main_loops_gpu_pass", False)),
            "no_cpu_backend_pass": bool(cpu_only_product_mode or hip_checks.get("no_cpu_backend_pass", False)),
            "no_cpu_required_pass": bool(cpu_only_product_mode or hip_checks.get("no_cpu_required_pass", False)),
            "no_cpu_fallback_pass": bool(cpu_only_product_mode or hip_checks.get("no_cpu_fallback_pass", False)),
            "runtime_backend_policy_ready": str(policy.get("status", "")).strip().lower() == "ready",
            "cpu_fallback_release_forbidden_pass": release_cpu_fallback_forbidden,
            "device_residency_target_pass": bool(cpu_only_product_mode or device_residency >= min_device_residency),
            "host_copy_share_pass": bool(host_copy_share is not None and host_copy_share <= max_host_copy_share),
        },
        summary={
            "solver_hip_e2e_reason_code": str(hip.get("reason_code", "")),
            "official_solver_backend": str(policy.get("official_solver_backend", "")),
            "cpu_only_product_mode": bool(cpu_only_product_mode),
            "device_residency_ratio_min": device_residency,
            "min_device_residency_ratio": min_device_residency,
            "host_copy_share": host_copy_share,
            "max_host_copy_share": max_host_copy_share,
        },
        artifacts={
            "solver_hip_e2e": str(solver_hip_e2e_path),
            "runtime_policy": str(runtime_policy_path),
            "zero_copy_strict": str(zero_copy_strict_path),
        },
    )
    return ndtha_report, hip_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndtha-long-profile", type=Path, default=DEFAULT_NDTHA_LONG_PROFILE)
    parser.add_argument("--solver-hip-e2e", type=Path, default=DEFAULT_SOLVER_HIP_E2E)
    parser.add_argument("--runtime-policy", type=Path, default=DEFAULT_RUNTIME_POLICY)
    parser.add_argument("--zero-copy-strict", type=Path, default=DEFAULT_ZERO_COPY_STRICT)
    parser.add_argument("--ndtha-out", type=Path, default=DEFAULT_NDTHA_OUT)
    parser.add_argument("--hip-out", type=Path, default=DEFAULT_HIP_OUT)
    parser.add_argument("--min-device-residency", type=float, default=0.99)
    parser.add_argument("--max-host-copy-share", type=float, default=0.05)
    parser.add_argument("--cpu-only-product-mode", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ndtha_report, hip_report = build_reports(
        ndtha_long_profile_path=args.ndtha_long_profile,
        solver_hip_e2e_path=args.solver_hip_e2e,
        runtime_policy_path=args.runtime_policy,
        zero_copy_strict_path=args.zero_copy_strict,
        min_device_residency=args.min_device_residency,
        max_host_copy_share=args.max_host_copy_share,
        cpu_only_product_mode=args.cpu_only_product_mode,
    )
    args.ndtha_out.parent.mkdir(parents=True, exist_ok=True)
    args.hip_out.parent.mkdir(parents=True, exist_ok=True)
    args.ndtha_out.write_text(json.dumps(ndtha_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.hip_out.write_text(json.dumps(hip_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {"require_ndtha": ndtha_report, "require_hip": hip_report}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else f"ndtha={ndtha_report['reason_code']} hip={hip_report['reason_code']}")
    return 0 if ndtha_report["contract_pass"] and hip_report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
