from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_visual_regression_is_wired_to_package_and_full_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (ROOT / "scripts" / "verify-frontend-build-contract.mjs").read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    viewer_contracts = (ROOT / "scripts" / "verify_structure_viewer_contracts.py").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["verify:viewer-visual-regression"]
        == "playwright install chromium && node ./scripts/measure-structure-viewer-visual-regression.mjs --verify --fail-blocked"
    )
    assert "scripts/measure-structure-viewer-visual-regression.mjs" in frontend_contract
    assert "verify:viewer-visual-regression" in quality_gate
    assert quality_gate.index("verify:viewer-performance-probe") < quality_gate.index(
        "verify:viewer-visual-regression"
    )
    assert quality_gate.index("verify:viewer-visual-regression") < quality_gate.index(
        "report_commercialization_level.py"
    )
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
