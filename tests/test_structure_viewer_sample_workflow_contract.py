from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_sample_workflow_is_rust_owned_and_full_gated() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (
        ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
    ).read_text(encoding="utf-8")
    rust_verifier = (
        ROOT
        / "native/crates/structural-frontend-contract/src/viewer_sample_workflow.rs"
    ).read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts/verify_quality_gate.py").read_text(
        encoding="utf-8"
    )
    viewer_contracts = (ROOT / "scripts/verify_structure_viewer_contracts.py").read_text(
        encoding="utf-8"
    )

    assert package_json["scripts"]["verify:viewer-sample-workflow"] == (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-sample-workflow --root ."
    )
    assert '"viewer_sample_workflow_contract"' in frontend_contract
    assert "scripts/verify-structure-viewer-sample-workflow.mjs" in frontend_contract
    assert "pub fn run_viewer_sample_workflow" in rust_verifier
    assert "decode_json_strict" in rust_verifier
    assert "viewer_sample_workflow_contract_changed" in rust_verifier
    assert "viewer_sample_workflow_aggregate_mismatch" in rust_verifier
    assert "viewer_sample_workflow_step_failed" in rust_verifier
    assert "temporary_removed_after_verification" in rust_verifier
    assert "direct_processes_spawned" in rust_verifier
    assert "not human new-user observation" in rust_verifier
    assert "verify:viewer-sample-workflow" in quality_gate
    assert quality_gate.index("verify:frontend-browser-smoke") < quality_gate.index(
        "verify:viewer-sample-workflow"
    )
    assert quality_gate.index("verify:viewer-sample-workflow") < quality_gate.index(
        "verify:viewer-report-pdf"
    )
    assert "tests/test_structure_viewer_sample_workflow_contract.py" in viewer_contracts


def test_retained_sample_workflow_probe_keeps_exact_automated_rehearsal() -> None:
    script = (
        ROOT / "scripts/verify-structure-viewer-sample-workflow.mjs"
    ).read_text(encoding="utf-8")

    assert "structure-viewer-sample-workflow-smoke.v1" in script
    assert "midas33 optimized sample project" in script
    assert "midas33 search and selection input" in script
    assert "real drawing sample project" in script
    assert "real drawing search input" in script
    assert "project=midas33_release&drawing=midas33_optimized&variant=optimized" in script
    assert "preset=real_drawing_private_3d&member=RD-001&drawing_asset=RD-001" in script
    assert "waitForCanvasNonBlank" in script
    assert "assertCanvasWellFramed" in script
    assert "max_sample_completion_minutes" in script
    assert "ERR_STRUCTURE_VIEWER_SAMPLE_WORKFLOW_FAIL" in script


def test_native_sample_workflow_dry_run_is_process_and_listener_free() -> None:
    result = subprocess.run(
        [
            "npm",
            "run",
            "verify:viewer-sample-workflow",
            "--silent",
            "--",
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == (
        "structural-native-viewer-sample-workflow-receipt.v1"
    )
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["max_sample_completion_minutes"] == 30
    assert len(payload["tracked_sources"]) == 3
    assert payload["verified_step_count"] == 0
    assert payload["artifact_sha256"] is None
    assert payload["output_disposition"] == "not_created"
    assert payload["rust_owned_listener_count"] == 0
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_code"] is None
    assert payload["runtime_requirements"] == {
        "node_required": True,
        "browser_required": True,
        "retained_node_internal_listener": True,
    }
    assert payload["receipt_hash"].startswith("sha256:")


def test_tracked_sample_workflow_artifact_remains_honest_automated_smoke() -> None:
    artifact = json.loads(
        (
            ROOT
            / "implementation/phase1/structure_viewer_sample_workflow_smoke.json"
        ).read_text(encoding="utf-8")
    )

    assert artifact["schema_version"] == "structure-viewer-sample-workflow-smoke.v1"
    assert artifact["contract_pass"] is True
    assert artifact["reason_code"] == "PASS"
    assert len(artifact["steps"]) == 4
    assert artifact["browser_error_count"] == 0
    assert artifact["sample_completion_minutes"] <= artifact[
        "max_sample_completion_minutes"
    ]
