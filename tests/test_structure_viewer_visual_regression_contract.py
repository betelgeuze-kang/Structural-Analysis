from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_visual_regression_is_wired_to_package_and_full_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (
        ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
    ).read_text(encoding="utf-8")
    rust_verifier = (
        ROOT
        / "native/crates/structural-frontend-contract/src/viewer_visual_regression.rs"
    ).read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    viewer_contracts = (ROOT / "scripts" / "verify_structure_viewer_contracts.py").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["verify:viewer-visual-regression"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-visual-regression --root ."
    )
    assert "scripts/measure-structure-viewer-visual-regression.mjs" in frontend_contract
    assert '"viewer_visual_regression_contract"' in frontend_contract
    assert "pub fn run_viewer_visual_regression" in rust_verifier
    assert "decode_json_strict" in rust_verifier
    assert "viewer_visual_regression_contract_changed" in rust_verifier
    assert "viewer_visual_regression_source_identity_mismatch" in rust_verifier
    assert "viewer_visual_regression_measurement_failed" in rust_verifier
    assert "temporary_removed_after_verification" in rust_verifier
    assert "direct_processes_spawned" in rust_verifier
    assert "verify:viewer-visual-regression" in quality_gate
    performance_index = quality_gate.index("verify:viewer-performance-probe")
    visual_index = quality_gate.index("verify:viewer-visual-regression")
    full_commercialization_index = quality_gate.index(
        "report_commercialization_level.py",
        visual_index,
    )
    assert performance_index < visual_index < full_commercialization_index
    assert "tests/test_structure_viewer_visual_regression_contract.py" in viewer_contracts


def test_structure_viewer_visual_regression_has_dry_run_and_claim_boundary(tmp_path: Path) -> None:
    script_text = (ROOT / "scripts" / "measure-structure-viewer-visual-regression.mjs").read_text(encoding="utf-8")
    out = tmp_path / "visual-regression.json"
    result = subprocess.run(
        [
            "node",
            "scripts/measure-structure-viewer-visual-regression.mjs",
            "--dry-run",
            "--verify",
            "--baseline",
            "implementation/phase1/structure_viewer_visual_regression_baseline.json",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "scripts/measure-structure-viewer-visual-regression.mjs" in result.stdout
    assert "--verify" in result.stdout
    assert str(out) in result.stdout
    assert "structure-viewer-visual-regression-baseline.v1" in script_text
    assert "local_canvas_signature_baseline" in script_text
    assert "live_visual_claim: false" in script_text
    assert "independent_product_claim: false" in script_text
    assert "desktop_midas33_solid" in script_text
    assert "desktop_midas33_contour" in script_text
    assert "desktop_midas33_plan_wireframe" in script_text
    assert "desktop_midas33_review_member" in script_text
    assert "desktop_midas33_compare_risk_overlay" in script_text
    assert "desktop_midas33_evidence_ingest_csv" in script_text
    assert "desktop_midas33_renderable_json_ingest" in script_text
    assert "desktop_midas33_section_edit_apply" in script_text
    assert "desktop_midas33_loadcomb_draft" in script_text
    assert "expected_render_mode" in script_text
    assert "render_mode_mismatch" in script_text
    assert "expected_workflow_state" in script_text
    assert "view_preset_mismatch" in script_text
    assert "comparison_filter_mismatch" in script_text
    assert "evidence_ingest_missing" in script_text
    assert "renderable_payload_missing" in script_text
    assert "section_edit_missing" in script_text
    assert "Applied staged draft" in script_text
    assert "loadcomb_draft_missing" in script_text
    assert "visual_case_scope" in script_text
    assert "compareSignatures" in script_text
    assert "viewport_screenshot_sha256" in script_text
    assert "activateRenderMode" in script_text
    assert 'data-viewport-tool-render-mode="${normalizedMode}"' in script_text
    assert "activateViewPreset" in script_text
    assert 'data-viewport-view-preset="${normalizedPreset}"' in script_text
    assert "ensureWorkspaceChrome" in script_text
    assert "data-si-shell" in script_text
    assert "aria-pressed" in script_text


def test_native_visual_regression_dry_run_validates_baseline_without_process() -> None:
    result = subprocess.run(
        [
            "npm",
            "run",
            "verify:viewer-visual-regression",
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
        "structural-native-viewer-visual-regression-receipt.v1"
    )
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["baseline_sha256"] == (
        "sha256:85d5150e46dc859042a824e9b98948a0e3476a781a3315b4903e8d9df7dd75be"
    )
    assert len(payload["selected_case_ids"]) == 11
    assert len(payload["tracked_sources"]) == 4
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
