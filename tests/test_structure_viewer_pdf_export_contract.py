from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_pdf_export_smoke_is_wired_to_package_and_full_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (ROOT / "scripts" / "verify-frontend-build-contract.mjs").read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["verify:viewer-report-pdf"]
        == "node ./scripts/verify-structure-viewer-report-pdf.mjs"
    )
    assert "scripts/verify-structure-viewer-report-pdf.mjs" in frontend_contract
    assert "verify:viewer-report-pdf" in quality_gate
    assert quality_gate.index("verify:frontend-browser-smoke") < quality_gate.index("verify:viewer-report-pdf")
    assert quality_gate.index("verify:viewer-report-pdf") < quality_gate.index("report_commercialization_level.py")


def test_structure_viewer_pdf_export_smoke_has_dry_run_contract(tmp_path: Path) -> None:
    out = tmp_path / "viewer-report.pdf"
    result = subprocess.run(
        [
            "node",
            "scripts/verify-structure-viewer-report-pdf.mjs",
            "--dry-run",
            "--query",
            "project=midas33_release&drawing=midas33_optimized&variant=optimized",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "scripts/export-structure-viewer-report-pdf.mjs" in result.stdout
    assert "project=midas33_release&drawing=midas33_optimized&variant=optimized" in result.stdout
    assert str(out) in result.stdout
