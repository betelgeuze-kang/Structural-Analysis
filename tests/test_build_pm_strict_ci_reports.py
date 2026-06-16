from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_strict_ci_reports.py"
SPEC = importlib.util.spec_from_file_location("build_pm_strict_ci_reports", SCRIPT_PATH)
assert SPEC is not None
build_pm_strict_ci_reports = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_pm_strict_ci_reports)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_pm_strict_ci_reports_pass_with_ndtha_and_hip_evidence(tmp_path: Path) -> None:
    ndtha = _write(
        tmp_path / "ndtha.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "checks": {
                "all_runs_pass": True,
                "rust_backend_all_runs_pass": True,
                "elapsed_cov_pass": True,
                "peak_vram_cov_pass": True,
            },
            "summary": {"elapsed_wall_s_mean": 10.0, "peak_vram_mb_mean": 128.0},
        },
    )
    hip = _write(
        tmp_path / "hip.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "checks": {
                "all_main_loops_gpu_pass": True,
                "no_cpu_backend_pass": True,
                "no_cpu_required_pass": True,
                "no_cpu_fallback_pass": True,
            },
            "summary": {"device_residency_ratio_min": 1.0},
        },
    )
    policy = _write(
        tmp_path / "policy.json",
        {
            "status": "ready",
            "official_solver_backend": "amd_rocm_hip",
            "cpu_solver_fallback_detected": False,
            "cpu_fallback_allowed_for_official_solver_closure": False,
        },
    )
    zero_copy = _write(tmp_path / "zero_copy.json", {"contract_pass": True, "host_copy_share": 0.01})

    ndtha_report, hip_report = build_pm_strict_ci_reports.build_reports(
        ndtha_long_profile_path=ndtha,
        solver_hip_e2e_path=hip,
        runtime_policy_path=policy,
        zero_copy_strict_path=zero_copy,
        min_device_residency=0.99,
        max_host_copy_share=0.05,
        cpu_only_product_mode=False,
    )

    assert ndtha_report["contract_pass"] is True
    assert hip_report["contract_pass"] is True
    assert hip_report["summary"]["host_copy_share"] == 0.01


def test_pm_strict_ci_hip_report_blocks_cpu_fallback(tmp_path: Path) -> None:
    ndtha = _write(tmp_path / "ndtha.json", {"contract_pass": True, "checks": {}})
    hip = _write(
        tmp_path / "hip.json",
        {
            "contract_pass": True,
            "checks": {
                "all_main_loops_gpu_pass": True,
                "no_cpu_backend_pass": True,
                "no_cpu_required_pass": True,
                "no_cpu_fallback_pass": True,
            },
            "summary": {"device_residency_ratio_min": 1.0},
        },
    )
    policy = _write(
        tmp_path / "policy.json",
        {
            "status": "ready",
            "cpu_solver_fallback_detected": True,
            "cpu_fallback_allowed_for_official_solver_closure": False,
        },
    )
    zero_copy = _write(tmp_path / "zero_copy.json", {"host_copy_share": 0.0})

    _, hip_report = build_pm_strict_ci_reports.build_reports(
        ndtha_long_profile_path=ndtha,
        solver_hip_e2e_path=hip,
        runtime_policy_path=policy,
        zero_copy_strict_path=zero_copy,
        min_device_residency=0.99,
        max_host_copy_share=0.05,
        cpu_only_product_mode=False,
    )

    assert hip_report["contract_pass"] is False
    assert "cpu_fallback_release_forbidden_pass" in hip_report["blockers"]
