from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_release_gap_report_uses_smoke_history_for_time_saved_estimate(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
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

    _write(
        nightly,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "design_optimization_cost_reduction_smoke_history": {
                "history": [
                    {"baseline_runtime_s": 1.0, "trial_runtime_s": 0.05, "baseline_max_dcr": 0.93, "trial_max_dcr": 0.93, "contract_pass": True, "trial_feasible": True},
                    {"baseline_runtime_s": 1.2, "trial_runtime_s": 0.06, "baseline_max_dcr": 0.93, "trial_max_dcr": 0.93, "contract_pass": True, "trial_feasible": True},
                ],
                "summary": {"count": 2, "pass_rate": 1.0, "trial_feasible_rate": 1.0},
            },
            "design_optimization_cost_reduction_smoke": {"reason_code": "PASS", "contract_pass": True},
            "design_optimization_cost_reduction_smoke_strict_recommendation": {"strict_ready": False, "recommendation": "observe_more"},
        },
    )
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
    assert summary["estimated_time_saved_pct_range"] == [90, 95]
    assert summary["empirical_smoke_runtime_saved_pct_range"] == [95.0, 95.0]
    assert summary["empirical_smoke_runtime_saved_pct_mean"] == 95.0
    assert "Empirical estimate derived from nightly design-optimization smoke runtime reduction" in summary["estimated_time_saved_basis"]
