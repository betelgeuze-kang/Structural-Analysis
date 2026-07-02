from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_medium_model_scorecard_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_review(path: Path, *, index: int) -> None:
    _write_json(
        path,
        {
            "decision": "APPROVED_REVIEW",
            "evidence_ref": f"operator-review://medium-{index}",
            "reviewer": "release_owner",
        },
    )


def _write_minimal_medium_readiness_inputs(repo_root: Path) -> None:
    _write_json(
        repo_root / "implementation/phase1/opensees_topology_report.json",
        {
            "contract_pass": True,
            "metrics": {
                "beam_element_count": 3,
                "node_count": 4,
                "shell_element_count": 1,
            },
            "source_provenance": {
                "source_path": "operator-attached-medium.json",
                "source_sha256": "sha256:medium",
            },
        },
    )
    _write_json(
        repo_root
        / "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
        {
            "rows": [
                {"case_id": "SCBF16B"},
                {"case_id": "SCBF16B_shell_beam_mix"},
            ]
        },
    )
    runner = repo_root / module.RUNNER_SCRIPT
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


def test_medium_model_scorecard_readiness_blocks_without_scorecard_evidence() -> None:
    payload = module.build_phase3_medium_model_scorecard_readiness_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-medium-model-scorecard-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["medium_model_benchmark_pass_claim"] is False
    assert payload["required_medium_model_count"] == 5
    assert payload["current_medium_model_scorecard_count"] == 0
    assert payload["pass_or_approved_review_count"] == 0
    assert payload["scorecard_receipt_inventory"]["receipt_file_count"] == 0
    assert payload["local_candidate_artifact_count"] == 2
    assert payload["local_topology_contract_pass"] is True
    assert payload["source_url_verified"] is True
    assert payload["license_review_status"] == "identified_gpl_3_0_product_legal_review_required"
    assert payload["required_evidence_pass_count"] == 4
    assert payload["required_evidence_count"] == len(payload["required_evidence"])
    assert payload["summary"] == {
        "required_medium_model_count": 5,
        "local_candidate_case_count": 2,
        "missing_candidate_case_count": 3,
        "current_medium_model_scorecard_count": 0,
        "normalization_receipt_count": 0,
        "pass_or_approved_review_count": 0,
        "remaining_scorecard_case_count": 5,
        "remaining_pass_or_review_case_count": 5,
        "required_evidence_pass_count": 4,
        "required_evidence_count": len(payload["required_evidence"]),
        "runner_command_ready": True,
        "source_url_verified": True,
        "license_review_status": "identified_gpl_3_0_product_legal_review_required",
    }
    assert payload["case_selection_summary"] == {
        "claim_boundary": (
            "Candidate selection counts parser/topology-ready local source rows only. "
            "Scorecard credit remains zero until reference outputs, normalization "
            "receipts, scorecard execution, and PASS/REVIEW decisions pass."
        ),
        "current_scorecard_credit_count": 0,
        "local_candidate_case_count": 2,
        "missing_candidate_case_count": 3,
        "required_candidate_case_count": 5,
    }
    assert "source_url_verification_pending" not in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "reference_outputs_missing" in payload["blockers"]
    assert "normalization_receipts_missing" in payload["blockers"]
    assert "opensees_medium_runner_command_missing" not in payload["blockers"]
    assert "opensees_medium_scorecard_execution_missing" in payload["blockers"]
    assert "medium_model_pass_or_review_missing" in payload["blockers"]
    assert payload["runner_command_ready"] is True
    assert "run_phase3_medium_model_scorecard_receipt.py" in payload["runner_command_template"]
    assert payload["resource_envelope"]["default_timeout_seconds"] == 3600
    assert payload["local_parser_boundary"]["topology_contract_pass"] is True
    assert "parser input evidence" in payload["local_parser_boundary"]["claim_boundary"]
    assert payload["scorecard_receipt_template"]["schema_version"] == "phase3-medium-model-scorecard-receipt.v1"
    assert payload["scorecard_receipt_template"]["crashed"] is False
    assert payload["scorecard_receipt_template"]["oom"] is False
    assert payload["scorecard_receipt_template"]["contract_pass"] is False
    assert [row["id"] for row in payload["missing_evidence_breakdown"]] == [
        "license_approval",
        "reference_outputs",
        "canonical_normalization",
        "scorecard_execution",
        "pass_or_approved_review",
    ]
    scorecard_gap = {
        row["id"]: row for row in payload["missing_evidence_breakdown"]
    }["scorecard_execution"]
    assert scorecard_gap["remaining_case_count"] == 5
    assert scorecard_gap["receipt_directory"].endswith("medium_model_scorecard_receipts")
    assert [row["id"] for row in payload["operator_next_actions"]] == [
        "select_additional_medium_model_cases",
        "complete_product_legal_license_review",
        "attach_medium_reference_outputs",
        "record_medium_canonical_normalization",
        "run_medium_scorecard_receipts",
        "attach_medium_pass_or_approved_review_decisions",
    ]
    assert payload["recommended_next_actions"] == payload["operator_next_actions"]
    assert payload["gate_unblock_plan_count"] == 7
    gate_plan = {row["slot_id"]: row for row in payload["gate_unblock_plan"]}
    assert "select_additional_medium_model_cases" in gate_plan
    assert "rerun_medium_model_and_dp_rc_checks" in gate_plan
    assert gate_plan["run_medium_scorecard_receipts"]["remaining_case_count"] == 5
    assert any(
        "convergence history" in item
        for item in gate_plan["run_medium_scorecard_receipts"]["minimum_evidence"]
    )
    assert payload["validation_commands"] == [
        "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
        "python3 scripts/build_phase6_benchmark_scale_status.py --check",
        "python3 scripts/build_developer_preview_rc_status.py --check",
        "python3 scripts/build_product_readiness_snapshot.py --check",
    ]
    assert payload["next_actions"] == [
        "select_additional_medium_model_cases",
        "complete_product_legal_license_review",
        "attach_medium_reference_outputs",
        "record_medium_canonical_normalization",
        "run_medium_scorecard_receipts",
        "attach_medium_pass_or_approved_review_decisions",
    ]
    case_ledger = payload["case_readiness_ledger"]
    assert case_ledger["schema_version"] == "phase3-medium-model-case-readiness-ledger.v1"
    assert case_ledger["required_case_count"] == 5
    assert case_ledger["local_candidate_case_count"] == 2
    assert case_ledger["missing_candidate_case_count"] == 3
    assert case_ledger["case_ready_count"] == 0
    assert case_ledger["selection_gate"] == {
        "blockers": ["medium_structural_models_current_below_required:2/5"],
        "contract_pass": False,
        "current_candidate_case_count": 2,
        "required_candidate_case_count": 5,
    }
    case_rows = {row["case_id"]: row for row in case_ledger["case_rows"]}
    assert set(case_rows) == {"SCBF16B", "SCBF16B_shell_beam_mix"}
    assert case_rows["SCBF16B"]["parser_contract_pass"] is True
    assert case_rows["SCBF16B"]["authoritative_source_pass"] is True
    assert "reference_outputs_missing" in case_rows["SCBF16B"]["blockers"]
    queue = payload["medium_model_case_execution_queue"]
    assert queue["schema_version"] == "phase3-medium-model-case-execution-queue.v1"
    assert queue["required_case_count"] == 5
    assert queue["selected_case_count"] == 2
    assert queue["missing_case_count"] == 3
    assert queue["case_ready_count"] == 0
    assert len(queue["queue_rows"]) == 5
    assert queue["next_case_slot"]["slot"] == 1
    assert queue["next_case_slot"]["case_id"] == "SCBF16B"
    selected_slots = queue["queue_rows"][:2]
    missing_slots = queue["queue_rows"][2:]
    assert [row["slot_status"] for row in selected_slots] == [
        "selected_blocked",
        "selected_blocked",
    ]
    assert [row["slot_status"] for row in missing_slots] == [
        "operator_selection_required",
        "operator_selection_required",
        "operator_selection_required",
    ]
    assert "PASS or APPROVED_REVIEW decision with non-generated evidence_ref" in (
        selected_slots[0]["next_required_inputs"]
    )
    assert missing_slots[0]["case_id"] == "OPERATOR_ATTACHED_MEDIUM_CASE_3"
    assert "run_phase3_medium_model_scorecard_receipt.py" in (
        missing_slots[0]["runner_command_template"]
    )
    assert payload["case_input_requirements"]["remaining_case_count"] == 5
    assert "case_id" in {
        row["field"] for row in payload["case_input_requirements"]["case_fields"]
    }
    assert any(
        "build_developer_preview_rc_status.py --check" in command
        for command in payload["case_input_requirements"]["validation_commands"]
    )
    assert "operator scorecard runner command" in payload["claim_boundary"]


def test_medium_model_scorecard_readiness_counts_operator_scorecard_receipts(tmp_path: Path) -> None:
    _write_minimal_medium_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.MEDIUM_RECEIPT_DIR
    for index in range(5):
        _write_review(tmp_path / f"approved-review-{index}.json", index=index)
        _write_json(
            receipt_dir / f"medium-{index}.scorecard_receipt.json",
            {
                "schema_version": "phase3-medium-model-scorecard-receipt.v1",
                "case_id": f"medium-{index}",
                "contract_pass": True,
                "validation_contract_pass": True,
                "crashed": False,
                "oom": False,
                "scorecard_or_review_path": f"approved-review-{index}.json",
                "blockers": [],
            },
        )

    payload = module.build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["current_medium_model_scorecard_count"] == 5
    assert payload["pass_or_approved_review_count"] == 5
    assert payload["scorecard_receipt_inventory"]["valid_scorecard_case_count"] == 5
    assert payload["required_evidence_pass_count"] == 5
    assert "scorecard_execution" not in {
        row["id"] for row in payload["missing_evidence_breakdown"]
    }
    assert payload["case_input_requirements"]["remaining_case_count"] == 0
    assert payload["summary"]["remaining_scorecard_case_count"] == 0
    assert payload["summary"]["remaining_pass_or_review_case_count"] == 0
    assert "opensees_medium_scorecard_execution_missing" not in payload["blockers"]
    assert "medium_model_pass_or_review_missing" not in payload["blockers"]
    assert "source_url_verification_pending" in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "reference_outputs_missing" in payload["blockers"]
    assert "normalization_receipts_missing" in payload["blockers"]
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False


def test_medium_model_scorecard_readiness_validates_normalization_receipts(tmp_path: Path) -> None:
    _write_minimal_medium_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.MEDIUM_RECEIPT_DIR
    for index in range(5):
        _write_review(tmp_path / f"approved-review-{index}.json", index=index)
        normalization_receipt = (
            module.MEDIUM_RECEIPT_DIR
            / f"medium-{index}.normalization_receipt.json"
        )
        _write_json(
            tmp_path / normalization_receipt,
            {
                "schema_version": "phase3-medium-normalization-receipt.v1",
                "case_id": f"medium-{index}",
                "contract_pass": True,
                "units": {"force": "kN", "length": "m"},
                "coordinate_transform": "identity",
                "mapping_coverage": {"member": 1.0, "node": 1.0},
            },
        )
        _write_json(
            receipt_dir / f"medium-{index}.scorecard_receipt.json",
            {
                "schema_version": "phase3-medium-model-scorecard-receipt.v1",
                "case_id": f"medium-{index}",
                "contract_pass": True,
                "validation_contract_pass": True,
                "crashed": False,
                "oom": False,
                "scorecard_or_review_path": f"approved-review-{index}.json",
                "normalization_receipt": normalization_receipt.as_posix(),
                "blockers": [],
            },
        )

    payload = module.build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["scorecard_receipt_inventory"]["valid_normalization_case_count"] == 5
    assert payload["summary"]["normalization_receipt_count"] == 5
    assert "normalization_receipts_missing" not in payload["blockers"]
    canonical_normalization = {
        row["id"]: row for row in payload["required_evidence"]
    }["canonical_normalization"]
    assert canonical_normalization["contract_pass"] is True
    assert all(
        row["normalization_receipt_contract_pass"] is True
        for row in payload["scorecard_receipt_inventory"]["receipts"]
    )


def test_medium_model_scorecard_readiness_rejects_invalid_review_payloads(
    tmp_path: Path,
) -> None:
    _write_minimal_medium_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.MEDIUM_RECEIPT_DIR
    for index in range(5):
        _write_json(tmp_path / f"invalid-review-{index}.json", {})
        _write_json(
            receipt_dir / f"medium-{index}.scorecard_receipt.json",
            {
                "schema_version": "phase3-medium-model-scorecard-receipt.v1",
                "case_id": f"medium-{index}",
                "contract_pass": True,
                "validation_contract_pass": True,
                "crashed": False,
                "oom": False,
                "scorecard_or_review_path": f"invalid-review-{index}.json",
                "blockers": [],
            },
        )

    payload = module.build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["current_medium_model_scorecard_count"] == 5
    assert payload["pass_or_approved_review_count"] == 0
    assert "medium_model_pass_or_review_missing" in payload["blockers"]
    assert all(
        row["scorecard_or_review_contract_pass"] is False
        for row in payload["scorecard_receipt_inventory"]["receipts"]
    )
    first = payload["scorecard_receipt_inventory"]["receipts"][0]
    assert "scorecard_or_review_decision_not_accepted" in first[
        "scorecard_or_review_status"
    ]["blockers"]


def test_medium_model_scorecard_readiness_rejects_review_generated_evidence_refs(
    tmp_path: Path,
) -> None:
    _write_minimal_medium_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.MEDIUM_RECEIPT_DIR
    generated_gate_artifact = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "phase3_medium_model_scorecard_readiness_receipt.json"
    )
    _write_json(generated_gate_artifact, {"status": "blocked"})
    self_ref_review = tmp_path / "self-ref-review.json"
    generated_ref_review = tmp_path / "generated-ref-review.json"
    _write_json(
        self_ref_review,
        {
            "decision": "APPROVED_REVIEW",
            "evidence_ref": str(self_ref_review),
            "reviewer": "release_owner",
        },
    )
    _write_json(
        generated_ref_review,
        {
            "decision": "APPROVED_REVIEW",
            "evidence_ref": str(generated_gate_artifact),
            "reviewer": "release_owner",
        },
    )
    for index, review in enumerate([self_ref_review, generated_ref_review]):
        _write_json(
            receipt_dir / f"medium-{index}.scorecard_receipt.json",
            {
                "schema_version": "phase3-medium-model-scorecard-receipt.v1",
                "case_id": f"medium-{index}",
                "contract_pass": True,
                "validation_contract_pass": True,
                "crashed": False,
                "oom": False,
                "scorecard_or_review_path": str(review),
                "blockers": [],
            },
        )

    payload = module.build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["pass_or_approved_review_count"] == 0
    statuses = [
        row["scorecard_or_review_status"]
        for row in payload["scorecard_receipt_inventory"]["receipts"]
    ]
    blockers = [blocker for status in statuses for blocker in status["blockers"]]
    assert "scorecard_or_review_evidence_ref_self_reference" in blockers
    assert "scorecard_or_review_evidence_ref_generated_gate_artifact" in blockers
    assert all(status["contract_pass"] is False for status in statuses)


def test_medium_model_scorecard_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_medium_model_scorecard_readiness_missing:")


def test_medium_model_scorecard_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "medium-scorecard.json"
    module.write_phase3_medium_model_scorecard_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_medium_model_scorecard_readiness_mismatch"


def test_medium_model_scorecard_readiness_check_ignores_wrapper_metadata(tmp_path: Path) -> None:
    out = tmp_path / "medium-scorecard.json"
    module.write_phase3_medium_model_scorecard_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["generated_at"] = "2026-06-30T00:00:00+00:00"
    payload["source_commit_sha"] = "receipt-only-refresh"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is True
    assert message == "phase3_medium_model_scorecard_readiness_consistent"
