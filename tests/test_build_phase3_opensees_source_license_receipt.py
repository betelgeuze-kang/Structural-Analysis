from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_opensees_source_license_receipt.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_opensees_source_license_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_opensees_source_license_receipt_identifies_source_but_keeps_license_blocked() -> None:
    payload = module.build_phase3_opensees_source_license_receipt(repo_root=REPO_ROOT)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["source_id"] == "opensees_scbf16b_medium_candidate"
    assert payload["lanes"] == ["opensees-medium"]
    assert payload["source_url_verified"] is True
    assert payload["license_review_status"] == "identified_gpl_3_0_product_legal_review_required"
    assert payload["redistribution_allowed"] is False
    assert payload["commercial_use_allowed"] is False
    assert payload["local_candidate_checksum_attached"] is True
    assert {row["case_id"] for row in payload["local_candidate_artifacts"]} == {
        "SCBF16B",
        "SCBF16B_shell_beam_mix",
    }
    assert payload["topology_receipt"]["contract_pass"] is True
    assert payload["topology_receipt"]["source_is_opensees_text"] is True
    assert payload["topology_receipt"]["real_topology_pass"] is True
    assert "authoritative_source_url_missing" not in payload["blockers"]
    assert "upstream_license_text_missing" not in payload["blockers"]
    assert "authoritative_download_or_acquisition_script_blocked_source_url_missing" not in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "product_legal_license_review_pending" in payload["blockers"]
    assert "redistribution_rights_unverified" in payload["blockers"]
    assert "commercial_use_rights_unverified" in payload["blockers"]
    assert "download_or_acquisition_script_not_attached" not in payload["blockers"]
    assert "opensees_medium_scorecard_execution_missing" in payload["blockers"]
    assert "phase3_scorecard_runner_not_implemented" not in payload["blockers"]
    acquisition = payload["authoritative_acquisition"]
    assert acquisition["status"] == "source_url_and_license_identified_product_review_required"
    assert acquisition["source_url_verified"] is True
    assert acquisition["download_command"][:2] == ["curl", "-L"]
    assert "authoritative_download_or_acquisition_script_blocked_source_url_missing" not in acquisition["blockers"]
    assert "product_legal_license_review_pending" in acquisition["blockers"]
    assert "upstream SCBF16B source only" in acquisition["claim_boundary"]
    source_candidate = payload["source_url_candidates"][0]
    assert source_candidate["repository"] == "amaelkady/OpenSEES_Models_CBF"
    assert source_candidate["path"] == "Models and Tcl Files/SCBF16B.tcl"
    assert source_candidate["local_matches_upstream_raw_sha256"] is True
    assert source_candidate["upstream_raw_sha256"] == "309234fd42a58369a6d41198290527c6a86fee7da38c38a2fcbf625318720b80"
    assert source_candidate["local_candidate_sha256"] == source_candidate["upstream_raw_sha256"]
    license_evidence = payload["license_evidence"]
    assert license_evidence["spdx"] == "GPL-3.0"
    assert license_evidence["review_status"] == "identified_product_legal_review_required"
    verification = payload["local_candidate_verification"]
    assert verification["status"] == "ready_for_local_parser_work_only"
    assert verification["contract_pass"] is True
    assert verification["topology_verification_command"] == [
        "python3",
        "scripts/build_phase3_opensees_source_license_receipt.py",
        "--check",
    ]
    assert {row["case_id"] for row in verification["checksum_verification_rows"]} == {
        "SCBF16B",
        "SCBF16B_shell_beam_mix",
    }
    for row in verification["checksum_verification_rows"]:
        assert row["verification_command"][:2] == ["python3", "-c"]
        assert "hashlib.sha256" in row["verification_command"][2]
        assert row["verification_command"][3] == row["path"]
        assert row["verification_command"][4] == row["expected_sha256"]
    assert "committed/local candidate checksums" in verification["claim_boundary"]
    assert "local OpenSees medium candidate checksum/topology evidence" in payload["claim_boundary"]
    assert "GPL-3.0 license text" in payload["claim_boundary"]
    assert "scorecard execution for OpenSees medium blocked" in payload["claim_boundary"]


def test_phase3_opensees_source_license_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_opensees_source_license_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_opensees_source_license_missing:")


def test_phase3_opensees_source_license_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    module.write_phase3_opensees_source_license_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["source_url_verified"] = False
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_opensees_source_license_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_opensees_source_license_mismatch"
