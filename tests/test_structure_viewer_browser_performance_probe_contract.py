from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_browser_performance_probe_is_wired_to_package_and_full_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (ROOT / "scripts" / "verify-frontend-build-contract.mjs").read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    viewer_contracts = (ROOT / "scripts" / "verify_structure_viewer_contracts.py").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["verify:viewer-performance-probe"]
        == "playwright install chromium && node ./scripts/measure-structure-viewer-performance.mjs --verify --fail-blocked"
    )
    assert "scripts/measure-structure-viewer-performance.mjs" in frontend_contract
    assert "verify:viewer-performance-probe" in quality_gate
    assert quality_gate.index("verify:viewer-report-pdf") < quality_gate.index("verify:viewer-performance-probe")
    assert quality_gate.index("verify:viewer-performance-probe") < quality_gate.index("report_commercialization_level.py")
    assert "tests/test_structure_viewer_browser_performance_probe_contract.py" in viewer_contracts


def test_structure_viewer_browser_performance_probe_has_dry_run_and_claim_boundary(tmp_path: Path) -> None:
    script_text = (ROOT / "scripts" / "measure-structure-viewer-performance.mjs").read_text(encoding="utf-8")
    out = tmp_path / "viewer-performance.json"
    result = subprocess.run(
        [
            "node",
            "scripts/measure-structure-viewer-performance.mjs",
            "--dry-run",
            "--query",
            "project=midas33_release&drawing=midas33_optimized&variant=optimized",
            "--out",
            str(out),
            "--sample-ms",
            "100",
            "--min-fps",
            "1",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "scripts/measure-structure-viewer-performance.mjs" in result.stdout
    assert "project=midas33_release&drawing=midas33_optimized&variant=optimized" in result.stdout
    assert str(out) in result.stdout
    assert "structure-viewer-browser-performance-probe.v1" in script_text
    assert "local_browser_probe" in script_text
    assert "live_performance_claim: false" in script_text
    assert "independent_product_claim: false" in script_text
    assert "waitForCanvasNonBlank" in script_text
    assert "assertCanvasWellFramed" in script_text
    assert "sampleRaf" in script_text
