from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_kds_clause_member_extraction_receipt.py"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/kds_clause_member_extraction_receipt.json"
)


def test_kds_clause_member_extraction_default_pass(tmp_path: Path) -> None:
    out = tmp_path / "kds_clause_receipt.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--hf-csv",
        "implementation/phase1/commercial_hf_export_sample.csv",
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "kds-clause-member-extraction-receipt.v1"
    assert payload["status"] in {"ready", "partial"}
    assert payload["summary"]["member_count"] >= 3
    assert payload["summary"]["case_count"] >= 3
    assert payload["summary"]["clause_expected_count"] == 23
    assert payload["summary"]["family_expected_count"] == 6
    assert payload["summary"]["family_coverage_ready"] is True
    assert len(payload["per_clause_summary"]) >= 16
    assert all("clause_id" in row and "max_dcr" in row for row in payload["per_clause_summary"])
    assert all(
        row["family"] in {
            "beam", "column", "wall", "slab", "foundation",
            "connection", "axial", "shear", "moment",
            "interaction", "serviceability", "stability", "general",
        }
        for row in payload["per_clause_summary"]
    )
    assert isinstance(payload["checks"]["code_check_contract_pass"], bool)
    assert "rule_family_max_dcr" in payload["summary"]
    assert "rule_family_dcr_count" in payload["summary"]
    assert "claim_boundary" in payload
    assert "drift" in payload["claim_boundary"].lower() or "rule family" in payload["claim_boundary"].lower()


def test_kds_clause_member_extraction_auto_fit_capacity(tmp_path: Path) -> None:
    out = tmp_path / "kds_clause_receipt_auto_fit.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--hf-csv",
        "implementation/phase1/commercial_hf_export_sample.csv",
        "--auto-fit-capacity",
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs"]["capacity_source"] == "auto_fit_safety_factor_1.2"
    assert float(payload["inputs"]["axial_capacity_kN"]) > 1500.0
    assert float(payload["inputs"]["moment_capacity_kNm"]) > 2000.0
    assert payload["summary"]["member_count"] >= 3
    assert payload["summary"]["clause_expected_count"] == 23


def test_kds_clause_member_extraction_uses_solver_provenance(tmp_path: Path) -> None:
    out = tmp_path / "kds_clause_receipt_solver.json"
    solver_eq = (
        REPO_ROOT
        / "implementation/phase1/release_evidence/productization/mgt_full_frame_6dof_sparse_equilibrium.json"
    )
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--hf-csv",
        "implementation/phase1/commercial_hf_export_sample.csv",
        "--solver-equilibrium-json",
        str(solver_eq),
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"]["solver_equilibrium_json"] == str(solver_eq)
    assert payload["source"]["solver_equilibrium_sha256"] != ""
    assert payload["source"]["midas_model_name"] != ""


def test_kds_clause_member_extraction_writes_productization_receipt() -> None:
    """Sanity-check: the CLI default writes the canonical productization receipt path."""
    out = DEFAULT_OUT
    before = out.read_text(encoding="utf-8") if out.is_file() else ""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--hf-csv", "implementation/phase1/commercial_hf_export_sample.csv"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "kds-clause-member-extraction-receipt.v1"
    after = out.read_text(encoding="utf-8")
    assert after != before or before == ""
