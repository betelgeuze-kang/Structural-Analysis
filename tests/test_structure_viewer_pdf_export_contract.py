from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_pdf_export_smoke_is_wired_to_package_and_full_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_contract = (
        ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
    ).read_text(encoding="utf-8")
    quality_gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["export:viewer-report-pdf"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-export --root ."
    )
    assert (
        package_json["scripts"]["verify:viewer-report-pdf"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-smoke --root ."
    )
    assert "scripts/verify-structure-viewer-report-pdf.mjs" not in frontend_contract
    assert "native/crates/structural-frontend-contract/src/viewer_report_pdf_export.rs" in frontend_contract
    assert "native/crates/structural-frontend-contract/src/viewer_report_pdf_smoke.rs" in frontend_contract
    assert "scripts/export-structure-viewer-report-pdf.mjs" in frontend_contract
    assert "verify:viewer-report-pdf" in quality_gate
    assert quality_gate.index("verify:frontend-browser-smoke") < quality_gate.index("verify:viewer-report-pdf")
    assert quality_gate.index("verify:viewer-report-pdf") < quality_gate.index("report_commercialization_level.py")


def test_structure_viewer_pdf_export_smoke_has_dry_run_contract(tmp_path: Path) -> None:
    out = tmp_path / "viewer-report.pdf"
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--manifest-path",
            "native/Cargo.toml",
            "-p",
            "structural-frontend-contract",
            "--",
            "viewer-report-pdf-smoke",
            "--root",
            ".",
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
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-viewer-report-pdf-smoke-receipt.v1"
    assert payload["execution_mode"] == "dry_run"
    assert payload["query"] == "project=midas33_release&drawing=midas33_optimized&variant=optimized"
    assert payload["requested_output"] == str(out)
    assert payload["direct_processes_spawned"] == 0
    assert payload["pdf_sha256"] is None
    assert payload["html_sha256"] is None
    assert payload["logical_command_template"][1] == "scripts/export-structure-viewer-report-pdf.mjs"


def test_structure_viewer_pdf_product_export_has_native_dry_run_contract(tmp_path: Path) -> None:
    out = tmp_path / "viewer-product-report.pdf"
    html_out = tmp_path / "viewer-product-report.html"
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--manifest-path",
            "native/Cargo.toml",
            "-p",
            "structural-frontend-contract",
            "--",
            "viewer-report-pdf-export",
            "--root",
            ".",
            "--out",
            str(out),
            "--html-out",
            str(html_out),
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-viewer-report-pdf-export-receipt.v1"
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["requested_pdf_output"] == str(out)
    assert payload["requested_html_output"] == str(html_out)
    assert payload["published_pdf_path"] is None
    assert payload["published_html_path"] is None
    assert payload["output_disposition"] == "not_created"
    assert payload["direct_processes_spawned"] == 0
    assert payload["verification_receipt_hash"].startswith("sha256:")
    assert not out.exists()
    assert not html_out.exists()
