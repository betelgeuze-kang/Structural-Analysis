from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_large_model_runner_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_large_model_runner_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_minimal_large_readiness_inputs(repo_root: Path) -> None:
    runner = repo_root / module.RUNNER_SCRIPT
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


def test_large_model_runner_readiness_receipt_blocks_without_execution_evidence(
    tmp_path: Path,
) -> None:
    _write_minimal_large_readiness_inputs(tmp_path)
    payload = module.build_phase3_large_model_runner_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["schema_version"] == "phase3-large-model-runner-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["large_model_execution_claim"] is False
    assert payload["required_large_model_count"] == 2
    assert payload["current_large_model_execution_receipt_count"] == 0
    assert payload["crash_oom_free_execution_count"] == 0
    assert payload["scorecard_or_review_count"] == 0
    assert payload["source_url_verified_count"] == 0
    assert payload["source_checksum_count"] == 0
    assert payload["source_identity_inventory"]["source_url_candidate_count"] == 0
    assert payload["source_identity_inventory"]["source_checksum_count"] == 0
    assert payload["execution_receipt_inventory"]["receipt_file_count"] == 0
    assert payload["execution_receipt_inventory"]["execution_receipt_case_count"] == 0
    assert payload["required_evidence_pass_count"] == 2
    assert payload["required_evidence_count"] == len(payload["required_evidence"])
    assert payload["runner_command_ready"] is True
    assert "run_phase3_large_model_execution_receipt.py" in payload["runner_command_template"]
    assert payload["resource_envelope"]["default_timeout_seconds"] == 7200
    assert "source_url_verification_pending" in payload["blockers"]
    assert "checksum_missing" in payload["blockers"]
    assert "large_model_runner_not_implemented" not in payload["blockers"]
    assert "nightly_lane_not_configured" not in payload["blockers"]
    assert "large_model_execution_receipt_missing" in payload["blockers"]
    assert "large_model_scorecard_or_review_missing" in payload["blockers"]
    assert payload["runner_receipt_template"]["schema_version"] == "phase3-large-model-execution-receipt.v1"
    assert payload["runner_receipt_template"]["crashed"] is False
    assert payload["runner_receipt_template"]["oom"] is False
    assert payload["runner_receipt_template"]["contract_pass"] is False
    assert "runner command and resource envelope are implemented" in payload["claim_boundary"]
    assert "does not acquire sources" in payload["claim_boundary"]


def test_large_model_runner_readiness_counts_crash_oom_free_receipts_separately(
    tmp_path: Path,
) -> None:
    _write_minimal_large_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.LARGE_RECEIPT_DIR
    for index in range(2):
        _write_json(
            receipt_dir / f"large-{index}.execution_receipt.json",
            {
                "schema_version": "phase3-large-model-execution-receipt.v1",
                "case_id": f"large-{index}",
                "contract_pass": False,
                "validation_contract_pass": False,
                "exit_code": 2,
                "crashed": False,
                "oom": False,
                "source_sha256": f"sha256:{index:064x}",
                "source_sha256_match": True,
                "scorecard_or_review_path": "",
                "blockers": [
                    "scorecard_or_review_missing",
                    "validation_contract_not_pass",
                ],
            },
        )

    payload = module.build_phase3_large_model_runner_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["current_large_model_execution_receipt_count"] == 2
    assert payload["crash_oom_free_execution_count"] == 2
    assert payload["scorecard_or_review_count"] == 0
    assert payload["execution_receipt_inventory"]["execution_receipt_case_count"] == 2
    assert payload["execution_receipt_inventory"]["valid_execution_case_count"] == 0
    assert payload["required_evidence_pass_count"] == 4
    assert "large_model_execution_receipt_missing" not in payload["blockers"]
    assert "large_model_scorecard_or_review_missing" in payload["blockers"]
    assert "source_url_verification_pending" in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False


def test_large_model_runner_readiness_counts_operator_execution_receipts(tmp_path: Path) -> None:
    _write_minimal_large_readiness_inputs(tmp_path)
    receipt_dir = tmp_path / module.LARGE_RECEIPT_DIR
    for index in range(2):
        _write_json(
            receipt_dir / f"large-{index}.execution_receipt.json",
            {
                "schema_version": "phase3-large-model-execution-receipt.v1",
                "case_id": f"large-{index}",
                "contract_pass": True,
                "validation_contract_pass": True,
                "exit_code": 0,
                "crashed": False,
                "oom": False,
                "source_sha256": f"sha256:{index:064x}",
                "source_sha256_match": True,
                "scorecard_or_review_path": f"approved-review-{index}.json",
                "blockers": [],
            },
        )

    payload = module.build_phase3_large_model_runner_readiness_receipt(
        repo_root=tmp_path,
        source_commit_sha="test-sha",
    )

    assert payload["current_large_model_execution_receipt_count"] == 2
    assert payload["crash_oom_free_execution_count"] == 2
    assert payload["scorecard_or_review_count"] == 2
    assert payload["source_url_verified_count"] == 0
    assert payload["source_checksum_count"] == 2
    assert payload["execution_receipt_inventory"]["execution_receipt_case_count"] == 2
    assert payload["execution_receipt_inventory"]["valid_execution_case_count"] == 2
    assert payload["required_evidence_pass_count"] == 5
    assert "checksum_missing" not in payload["blockers"]
    assert "large_model_execution_receipt_missing" not in payload["blockers"]
    assert "large_model_scorecard_or_review_missing" not in payload["blockers"]
    assert "source_url_verification_pending" in payload["blockers"]
    assert "license_review_pending" in payload["blockers"]
    assert "reference_outputs_missing" in payload["blockers"]
    assert "normalization_not_implemented" in payload["blockers"]
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False


def test_large_model_runner_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_large_model_runner_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_large_model_runner_readiness_missing:")


def test_large_model_runner_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "large-runner.json"
    module.write_phase3_large_model_runner_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_large_model_runner_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_large_model_runner_readiness_mismatch"
