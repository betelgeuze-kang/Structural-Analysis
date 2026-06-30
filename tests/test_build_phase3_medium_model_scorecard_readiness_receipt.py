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
    assert "source_url_verification_pending" not in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "reference_outputs_missing" in payload["blockers"]
    assert "normalization_not_implemented" in payload["blockers"]
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
    assert "operator scorecard runner command" in payload["claim_boundary"]


def test_medium_model_scorecard_readiness_counts_operator_scorecard_receipts(tmp_path: Path) -> None:
    _write_minimal_medium_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.MEDIUM_RECEIPT_DIR
    for index in range(5):
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
    assert "opensees_medium_scorecard_execution_missing" not in payload["blockers"]
    assert "medium_model_pass_or_review_missing" not in payload["blockers"]
    assert "source_url_verification_pending" in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "reference_outputs_missing" in payload["blockers"]
    assert "normalization_not_implemented" in payload["blockers"]
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False


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
