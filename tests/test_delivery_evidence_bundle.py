"""Smoke tests for delivery evidence bundle artifacts and orchestration contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_delivery_evidence_bundle import _run, build_productization_status_command  # noqa: E402


def test_delivery_evidence_bundle_summary_contract_is_present() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json"
    bundle = json.loads(out.read_text(encoding="utf-8"))

    assert bundle["schema_version"] == "delivery-evidence-bundle.v1"
    assert bundle["status"] in {"ready", "review_required"}
    assert bundle["summary"]["cross_validation_status"] in {
        "pass",
        "partial",
        "fail",
        "pass_with_marginal_metrics",
    }
    assert "holdout_evidence_hints" in bundle
    assert bundle["artifacts"]["commercial_gap_ledger_status"].endswith(
        "commercial_gap_ledger_status.json"
    )
    assert bundle["artifacts"]["gap_closure_status"].endswith("gap_closure_status.json")
    assert bundle["artifacts"]["productization_delivery_evidence_validation"].endswith(
        "productization_delivery_evidence_validation.json"
    )
    assert bundle["artifacts"]["solver_runtime_backend_policy"].endswith(
        "solver_runtime_backend_policy.json"
    )
    assert bundle["summary"]["official_solver_compute_backend"] == "amd_rocm_hip"
    assert bundle["summary"]["official_solver_backend"] == "amd_rocm_hip"
    assert bundle["summary"]["official_solver_backend_family"] == "rocm_hip"
    assert bundle["summary"]["gpu_required_for_commercial_solver_closure"] is True
    assert bundle["summary"]["torch_device_label_is_pytorch_rocm_compat_alias"] is True
    assert bundle["summary"]["cpu_diagnostic_promotes_solver_closure"] is False
    assert bundle["summary"]["cpu_solver_fallback_detected"] is False
    assert bundle["summary"]["cpu_fallback_allowed_for_official_solver_closure"] is False


def test_delivery_evidence_orchestrator_documents_status_snapshot_reruns() -> None:
    source = (REPO_ROOT / "scripts/run_delivery_evidence_bundle.py").read_text(encoding="utf-8")

    assert "Run ledger/governance snapshots twice on purpose" in source
    assert "Validation writes a new artifact and may alter final blocker state" in source
    assert '--residual-holdout-json' in source
    assert 'out_dir / "residual_holdout_closure_updates.json"' in source
    assert 'out_dir / "rh_signed_closure_packets"' in source
    assert '"--packet-dir"' in source
    assert "--rerun-heavy-rocm-probe" in source
    assert "--rerun-heavy-probes" in source
    assert "reuse_existing_receipt" in source
    assert "mgt_pdelta_continuation_probe" in source
    assert "mgt_coarsened_authored_support_pdelta_probe" in source
    assert "mgt_uncoarsened_boundary_pdelta_probe" in source
    assert "heavy_probe_reuse_policy" in source
    assert "delivery_step_timeout_after=" in source
    assert source.count("build_productization_status_command(") >= 6


def test_delivery_evidence_status_snapshot_command_is_fully_scoped(tmp_path: Path) -> None:
    output = tmp_path / "gap_closure_status.json"
    cmd = build_productization_status_command(
        "report_gap_closure_status.py",
        productization_dir=tmp_path,
        output_json=output,
    )

    assert cmd == [
        sys.executable,
        str(REPO_ROOT / "scripts/report_gap_closure_status.py"),
        "--productization-dir",
        str(tmp_path),
        "--output-json",
        str(output),
    ]


def test_delivery_evidence_step_timeout_is_recorded(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):  # noqa: ANN001
        raise subprocess.TimeoutExpired(cmd=["fake"], timeout=3, output="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_run)

    code, log = _run(["fake"], timeout_seconds=3)

    assert code == 124
    assert "delivery_step_timeout_after=3s" in log
    assert "cmd=fake" in log
    assert "out" in log
    assert "err" in log


def test_delivery_evidence_heavy_receipt_reuse_skips_subprocess(
    monkeypatch, tmp_path: Path
) -> None:
    output = tmp_path / "mgt_rocm_sparse_solver_probe.json"
    output.write_text("{}", encoding="utf-8")

    def fail_run(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("heavy receipt reuse should not spawn subprocess")

    monkeypatch.setattr(subprocess, "run", fail_run)

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_rocm_sparse_solver_probe.py"),
            "--output-json",
            str(output),
        ]
    )

    assert code == 0
    assert "reused_existing_heavy_receipt=" in log
    assert "run_mgt_rocm_sparse_solver_probe.py" in log
