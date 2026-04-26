from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_release_gap_report import _rolling_measured_chain_summary


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_release_gap_report_emits_rolling_measured_chain_summary(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    history_root = tmp_path / "nightly_history"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    def nightly_payload(seconds: float) -> dict:
        return {
            "contract_pass": True,
            "reason_code": "PASS",
            "generated_at": "2026-03-15T00:00:00Z",
            "steps": [
                {"step": "midas_mgt_conversion_gate", "seconds": 12.0},
                {"step": "nonlinear_engine_gate", "seconds": 18.0},
                {"step": "wind_benchmark_gate", "seconds": seconds},
                {"step": "global_authority_gate", "seconds": 6.0},
                {"step": "release_registry_gate", "seconds": 4.0},
            ],
        }

    _write(nightly, nightly_payload(120.0))
    _write(history_root / "20260315T000000Z" / "artifacts" / "nightly_release_gate_report.json", nightly_payload(60.0))
    _write(history_root / "20260315T010000Z" / "artifacts" / "nightly_release_gate_report.json", nightly_payload(90.0))

    for path in [ci, freeze, promotion, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
                "recommended_use": "Automate repeated analysis while preserving residual holdout.",
            },
            "residual_holdout_categories": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--nightly-release",
            str(nightly),
            "--nightly-history-root",
            str(history_root),
            "--nightly-history-limit",
            "3",
            "--ci-gate",
            str(ci),
            "--static-validation",
            str(static),
            "--freeze-report",
            str(freeze),
            "--promotion-report",
            str(promotion),
            "--commercial-readiness",
            str(commercial),
            "--global-authority",
            str(authority),
            "--hip-kernel-smoke",
            str(hip),
            "--midas-conversion",
            str(midas),
            "--construction-sequence",
            str(construction),
            "--flexible-diaphragm",
            str(diaphragm),
            "--repro-version-lock",
            str(repro),
            "--release-registry",
            str(registry),
            "--kds-compliance",
            str(kds),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc),
            "--quality-mgt-corpus",
            str(quality),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["measured_chain_rolling_sample_count"] == 3
    assert summary["measured_chain_rolling_total_minutes_range"] == [1.667, 2.667]
    assert summary["measured_chain_rolling_total_minutes_mean"] == 2.167
    assert summary["measured_chain_rolling_category_minutes_mean"]["nonseismic_construction"] == 1.5
    assert len(payload["measured_chain_rolling_rows"]) == 3

    markdown = out_md.read_text(encoding="utf-8")
    assert "Measured accelerated chain wall-clock (comparable rolling N=3)" in markdown


def test_release_gap_report_ignores_zero_minute_full_chain_rows(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    history_root = tmp_path / "nightly_history"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    def nightly_payload(*, selected_nonzero: bool) -> dict:
        base_seconds = 12.0 if selected_nonzero else 0.0
        steps = [
            {"step": "midas_mgt_conversion_gate", "seconds": base_seconds},
            {"step": "nonlinear_engine_gate", "seconds": 18.0 if selected_nonzero else 0.0},
            {"step": "global_authority_gate", "seconds": 6.0 if selected_nonzero else 0.0},
            {"step": "release_registry_gate", "seconds": 4.0 if selected_nonzero else 0.0},
        ]
        steps.extend(
            {"step": "wind_benchmark_gate", "seconds": 10.0 if selected_nonzero else 0.0}
            for _ in range(8)
        )
        steps.extend(
            {"step": "construction_sequence_gate", "seconds": 12.0 if selected_nonzero else 0.0}
            for _ in range(4)
        )
        steps.extend({"step": f"filler_{idx:02d}", "seconds": 1.0} for idx in range(20))
        return {
            "contract_pass": True,
            "reason_code": "PASS",
            "generated_at": "2026-03-15T00:00:00Z",
            "steps": steps,
        }

    _write(nightly, nightly_payload(selected_nonzero=True))
    _write(history_root / "20260315T000000Z" / "artifacts" / "nightly_release_gate_report.json", nightly_payload(selected_nonzero=False))
    _write(history_root / "20260315T010000Z" / "artifacts" / "nightly_release_gate_report.json", nightly_payload(selected_nonzero=True))

    for path in [ci, freeze, promotion, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
                "recommended_use": "Automate repeated analysis while preserving residual holdout.",
            },
            "residual_holdout_categories": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--nightly-release",
            str(nightly),
            "--nightly-history-root",
            str(history_root),
            "--nightly-history-limit",
            "3",
            "--ci-gate",
            str(ci),
            "--static-validation",
            str(static),
            "--freeze-report",
            str(freeze),
            "--promotion-report",
            str(promotion),
            "--commercial-readiness",
            str(commercial),
            "--global-authority",
            str(authority),
            "--hip-kernel-smoke",
            str(hip),
            "--midas-conversion",
            str(midas),
            "--construction-sequence",
            str(construction),
            "--flexible-diaphragm",
            str(diaphragm),
            "--repro-version-lock",
            str(repro),
            "--release-registry",
            str(registry),
            "--kds-compliance",
            str(kds),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc),
            "--quality-mgt-corpus",
            str(quality),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["measured_chain_rolling_sample_count"] == 2
    assert summary["measured_chain_rolling_total_minutes_range"][0] > 0.0


def test_release_gap_report_prefers_current_pipeline_comparable_rows(tmp_path: Path) -> None:
    current_path = tmp_path / "nightly.json"
    history_root = tmp_path / "history"

    current_steps = [
        "commercial_csv_gate",
        "midas_mgt_conversion_gate",
        "real_source_multi_gate",
        "nonlinear_engine_gate",
        "pushover_stress_gate",
        "ndtha_stress_gate",
        "ndtha_residual_gate",
        "wind_benchmark_gate",
        "ssi_boundary_gate",
        "damper_validation_gate",
        "kds_compliance_gate",
        "construction_sequence_gate",
        "flexible_diaphragm_gate",
        "reproducibility_version_lock_gate",
        "release_registry_gate",
        "rc_benchmark_lock_gate",
        "commercial_readiness_gate",
        "global_authority_gate",
        "design_optimization_cost_reduction_smoke",
    ]
    older_steps = current_steps[:-2]

    def payload(step_names: list[str], seconds: float) -> dict:
        return {
            "contract_pass": True,
            "reason_code": "PASS",
            "generated_at": "2026-03-15T00:00:00Z",
            "steps": [{"step": name, "seconds": seconds} for name in step_names] + [{"step": f"filler_{idx:02d}", "seconds": 1.0} for idx in range(10)],
        }

    current_payload = payload(current_steps, 5.0)
    _write(current_path, current_payload)
    _write(history_root / "20260315T000000Z" / "artifacts" / "nightly_release_gate_report.json", payload(older_steps, 5.0))
    _write(history_root / "20260315T010000Z" / "artifacts" / "nightly_release_gate_report.json", payload(current_steps[:-1], 5.0))

    summary = _rolling_measured_chain_summary(
        current_path,
        current_payload,
        history_root=history_root,
        limit=10,
    )
    assert summary["measured_chain_rolling_selection_mode"] == "current_pipeline_comparable_full_chain_pass"
    assert summary["measured_chain_full_chain_sample_count"] == 3
    assert summary["measured_chain_comparable_sample_count"] == 2
    assert summary["measured_chain_rolling_sample_count"] == 2


def test_release_gap_report_comparable_rows_require_same_deployment_and_strict_smoke(tmp_path: Path) -> None:
    current_path = tmp_path / "nightly.json"
    history_root = tmp_path / "history"
    current_commercial = tmp_path / "commercial.json"

    current_steps = [
        "commercial_csv_gate",
        "midas_mgt_conversion_gate",
        "real_source_multi_gate",
        "nonlinear_engine_gate",
        "pushover_stress_gate",
        "ndtha_stress_gate",
        "ndtha_residual_gate",
        "wind_benchmark_gate",
        "ssi_boundary_gate",
        "damper_validation_gate",
        "kds_compliance_gate",
        "construction_sequence_gate",
        "flexible_diaphragm_gate",
        "reproducibility_version_lock_gate",
        "release_registry_gate",
        "rc_benchmark_lock_gate",
        "commercial_readiness_gate",
        "global_authority_gate",
        "design_optimization_cost_reduction_smoke",
    ]

    def payload(*, strict: bool) -> dict:
        return {
            "contract_pass": True,
            "reason_code": "PASS",
            "generated_at": "2026-03-15T00:00:00Z",
            "inputs": {"strict_design_opt_cost_smoke": strict},
            "steps": [{"step": name, "seconds": 5.0} for name in current_steps] + [{"step": f"filler_{idx:02d}", "seconds": 1.0} for idx in range(10)],
        }

    def commercial_payload(mode: str) -> dict:
        return {"deployment_model": {"mode": mode}}

    _write(current_path, payload(strict=True))
    _write(current_commercial, commercial_payload("engineer_in_the_loop_accelerated_coverage"))
    same_dir = history_root / "20260315T000000Z" / "artifacts"
    strict_mismatch_dir = history_root / "20260315T010000Z" / "artifacts"
    deployment_mismatch_dir = history_root / "20260315T020000Z" / "artifacts"

    _write(same_dir / "nightly_release_gate_report.json", payload(strict=True))
    _write(same_dir / "commercial_readiness_report.json", commercial_payload("engineer_in_the_loop_accelerated_coverage"))

    _write(strict_mismatch_dir / "nightly_release_gate_report.json", payload(strict=False))
    _write(strict_mismatch_dir / "commercial_readiness_report.json", commercial_payload("engineer_in_the_loop_accelerated_coverage"))

    _write(deployment_mismatch_dir / "nightly_release_gate_report.json", payload(strict=True))
    _write(deployment_mismatch_dir / "commercial_readiness_report.json", commercial_payload("full_replacement"))

    current_payload = json.loads(current_path.read_text(encoding="utf-8"))
    summary = _rolling_measured_chain_summary(
        current_path,
        current_payload,
        history_root=history_root,
        limit=10,
        current_deployment_model="engineer_in_the_loop_accelerated_coverage",
        current_strict_design_opt_cost_smoke=True,
        fallback_commercial_readiness_path=current_commercial,
    )
    assert summary["measured_chain_rolling_selection_mode"] == "current_pipeline_comparable_full_chain_pass"
    assert summary["measured_chain_full_chain_sample_count"] == 4
    assert summary["measured_chain_comparable_sample_count"] == 2
    assert summary["measured_chain_rolling_sample_count"] == 2
    assert summary["measured_chain_comparable_reference_deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert summary["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
