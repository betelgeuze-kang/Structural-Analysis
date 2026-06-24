from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_gap_ledger_evidence_audit.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_gap_ledger_evidence_audit", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_gap_ledger_evidence_audit_verifies_closed_and_nonclosed_rows() -> None:
    payload = module.build_gap_ledger_evidence_audit(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "gap-ledger-evidence-audit.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["full_gap_ledger_ready"] is False
    assert payload["ledger_status"] == "open"
    assert payload["row_count"] == 20
    assert payload["closed_row_count"] == 17
    assert payload["nonclosed_row_count"] == 3
    closed = payload["closed_evidence_coverage"]
    assert closed["closed_rows_with_evidence_count"] == 17
    assert closed["closed_rows_without_blockers_count"] == 17
    assert closed["closed_missing_evidence_ids"] == []
    assert closed["closed_with_blockers_ids"] == []
    assert closed["closed_missing_claim_boundary_ids"] == []
    assert closed["closed_missing_boundary_or_next_gate_ids"] == []
    nonclosed = payload["nonclosed_visibility"]
    assert nonclosed["nonclosed_rows_with_blockers_count"] == 3
    assert nonclosed["nonclosed_rows_with_claim_boundary_count"] == 3
    assert nonclosed["nonclosed_rows_with_evidence_count"] == 3
    assert nonclosed["nonclosed_missing_blocker_ids"] == []
    assert nonclosed["nonclosed_missing_claim_boundary_ids"] == []
    source_paths = payload["source_receipt_path_coverage"]
    assert source_paths["source_receipt_path_count"] == 112
    assert source_paths["source_receipt_existing_path_count"] == 112
    assert source_paths["source_receipt_absent_row_count"] == 0
    assert source_paths["source_receipt_absent_row_ids"] == []
    assert source_paths["source_receipt_missing_path_count"] == 0
    assert source_paths["source_receipt_missing_row_ids"] == []
    assert payload["blockers"] == []
    outcomes = {row["id"]: row for row in payload["row_outcomes"]}
    assert outcomes["G1"]["closed"] is False
    assert outcomes["G1"]["claim_boundary_present"] is True
    assert outcomes["G1"]["source_receipt_path_count"] == 21
    assert outcomes["G1"]["source_receipt_missing_path_count"] == 0
    assert outcomes["G1"]["closure_requirement_count"] == 9
    assert outcomes["G1"]["closure_requirement_pass_count"] == 2
    assert outcomes["G1"]["closure_requirement_fail_count"] == 7
    assert outcomes["G1"]["closure_requirement_failed_ids"] == [
        "full_load_scale_1_0_reached",
        "strict_full_load_hip_newton_checkpoint_available",
        "full_line_mesh_nonlinear_equilibrium_closed",
        "full_frame_6dof_nonlinear_equilibrium_closed",
        "coupled_frame_surface_nonlinear_equilibrium_closed",
        "state_updated_material_newton_breadth_closed",
        "fallback_and_regularization_free_full_path",
    ]
    assert outcomes["G6"]["closure_requirement_count"] == 5
    assert outcomes["G6"]["closure_requirement_pass_count"] == 1
    assert outcomes["G6"]["closure_requirement_fail_count"] == 4
    assert outcomes["G6"]["closure_requirement_failed_ids"] == [
        "eb_receipt_hardest_external_10case",
        "eb_receipt_korean_public_structures",
        "eb_receipt_peer_spd_hinge",
        "eb_receipt_tpu_hffb",
    ]
    assert outcomes["G7"]["closure_requirement_count"] == 5
    assert outcomes["G7"]["closure_requirement_pass_count"] == 0
    assert outcomes["G7"]["closure_requirement_fail_count"] == 5
    assert outcomes["G7"]["closure_requirement_failed_ids"] == [
        "repo_benchmark_bridge_count_zero",
        "metadata_only_count_zero",
        "operator_attached_real_mgt_header_ok_minimum",
        "operator_manifest_source_mapping_clear",
        "operator_rights_boundary_clear",
    ]
    assert outcomes["G2"]["closed"] is True
    assert outcomes["G2"]["evidence_present"] is True
    assert outcomes["G2"]["claim_boundary_present"] is True
    assert outcomes["G2"]["next_gate_present"] is True
    assert outcomes["AI-G1"]["source_receipt_path_count"] == 8
    assert outcomes["AI-G1"]["source_receipt_missing_path_count"] == 0
    assert "does not create authoritative evidence" in payload["claim_boundary"]


def test_gap_ledger_evidence_audit_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_gap_ledger_evidence_audit(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("gap_ledger_evidence_audit_missing:")


def test_gap_ledger_evidence_audit_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "audit.json"
    module.write_gap_ledger_evidence_audit(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = False
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_gap_ledger_evidence_audit(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "gap_ledger_evidence_audit_mismatch"


def test_gap_ledger_evidence_audit_blocks_missing_source_receipt_path(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "commercial_gap_ledger_status.json"
    ledger.write_text(
        json.dumps(
            {
                "status": "open",
                "full_gap_ledger_ready": False,
                "rows": [
                    {
                        "id": "G1",
                        "ledger": "commercial_solver",
                        "status": "partial",
                        "blockers": ["still_open"],
                        "claim_boundary": "partial row boundary",
                        "evidence": {
                            "source_receipts": {
                                "missing": "missing-source-receipt.json"
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_gap_ledger_evidence_audit(
        repo_root=tmp_path,
        ledger_status_path=ledger,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["source_receipt_path_coverage"][
        "source_receipt_missing_path_count"
    ] == 1
    assert payload["source_receipt_path_coverage"][
        "source_receipt_missing_row_ids"
    ] == ["G1"]
    assert payload["blockers"] == ["source_receipt_path_missing:G1"]


def test_gap_ledger_evidence_audit_blocks_rows_without_source_receipts(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "commercial_gap_ledger_status.json"
    ledger.write_text(
        json.dumps(
            {
                "status": "open",
                "full_gap_ledger_ready": False,
                "rows": [
                    {
                        "id": "G2",
                        "ledger": "commercial_solver",
                        "status": "closed",
                        "blockers": [],
                        "claim_boundary": "closed row boundary",
                        "evidence": {"some_metric": True},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_gap_ledger_evidence_audit(
        repo_root=tmp_path,
        ledger_status_path=ledger,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["source_receipt_path_coverage"][
        "source_receipt_absent_row_count"
    ] == 1
    assert payload["source_receipt_path_coverage"][
        "source_receipt_absent_row_ids"
    ] == ["G2"]
    assert payload["blockers"] == ["source_receipts_absent:G2"]
