from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "implementation" / "phase1" / "validate_fresh_validation_receipt.py"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "implementation" / "phase1" / "fresh_validation_receipt.schema.json"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "docs" / "templates" / "fresh_validation_receipt.template.json"
SPEC = importlib.util.spec_from_file_location("validate_fresh_validation_receipt", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": "fresh-validation-receipt.v1",
        "lane_id": "gpu_hip_solver",
        "runner": "gpu_capable_rocm_hip_validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": "abcdef1234567890",
        "engine_version": "engine@1.0.0",
        "input_checksums": {
            "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json": (
                "sha256:" + "a" * 64
            )
        },
        "reused_evidence": False,
        "contract_pass": True,
        "reason_code": "PASS",
        "validation_command": "python3 -m implementation.phase1.run_gpu_solver_hip_validation",
        "receipt_artifacts": [
            {
                "path": "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json",
                "sha256": "sha256:" + "a" * 64,
                "kind": "contract_report",
            }
        ],
        "summary": {"case_count": 10, "passed_case_count": 10, "duration_seconds": 12.5},
        "claim_boundary": (
            "Receipt attests the named lane produced real fresh evidence; "
            "Level 3 promotion remains with the human owner."
        ),
    }


def test_fresh_validation_receipt_validator_accepts_valid_payload() -> None:
    payload = validator.validate_payload(_valid_payload(), _schema())

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["blockers"] == []
    assert payload["summary"]["reused_evidence"] is False
    assert payload["summary"]["contract_pass_field"] is True
    assert payload["summary"]["reason_code_field"] == "PASS"
    assert payload["summary"]["source_commit_sha_pass"] is True


def test_fresh_validation_receipt_validator_rejects_reused_evidence() -> None:
    bad = _valid_payload()
    bad["reused_evidence"] = True

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "fixed_value_mismatch:reused_evidence" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_wrong_contract_pass_and_reason() -> None:
    bad = _valid_payload()
    bad["contract_pass"] = False
    bad["reason_code"] = "WARN"

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "fixed_value_mismatch:contract_pass" in payload["blockers"]
    assert "fixed_value_mismatch:reason_code" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_missing_required_fields() -> None:
    bad = _valid_payload()
    bad.pop("lane_id")
    bad.pop("validation_command")
    bad.pop("claim_boundary")

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert any(b.startswith("missing_field:lane_id") for b in payload["blockers"])
    assert any(b.startswith("missing_field:validation_command") for b in payload["blockers"])
    assert any(b.startswith("missing_field:claim_boundary") for b in payload["blockers"])


def test_fresh_validation_receipt_validator_rejects_empty_required_fields() -> None:
    bad = _valid_payload()
    bad["lane_id"] = ""
    bad["input_checksums"] = {}
    bad["receipt_artifacts"] = []
    bad["summary"] = {}

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "empty_required_field:lane_id" in payload["blockers"]
    assert "empty_required_field:input_checksums" in payload["blockers"]
    assert "empty_required_field:summary" in payload["blockers"]
    assert "receipt_artifacts_missing_or_empty" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_bad_source_commit_sha() -> None:
    bad = _valid_payload()
    bad["source_commit_sha"] = "not-a-commit"

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "source_commit_sha_not_commit_sha" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_bad_timestamp_and_input_checksum() -> None:
    bad = _valid_payload()
    bad["generated_at"] = "not-a-timestamp"
    bad["input_checksums"] = {"report.json": "sha256:not-a-digest"}

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "generated_at_not_iso_datetime" in payload["blockers"]
    assert "input_checksums.report.json:not_sha256" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_bad_artifact_checksums() -> None:
    bad = _valid_payload()
    bad["receipt_artifacts"] = [
        {"path": "report.json", "sha256": "not-a-sha"},
        {"path": "report2.json", "sha256": "sha256:" + "b" * 64},
    ]

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert any(b.startswith("receipt_artifacts[0].sha256") for b in payload["blockers"])


def test_fresh_validation_receipt_validator_rejects_summary_inconsistencies() -> None:
    bad = _valid_payload()
    bad["summary"] = {"case_count": "five", "passed_case_count": 9}

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "summary.case_count:not_non_negative_integer" in payload["blockers"]

    bad2 = _valid_payload()
    bad2["summary"] = {"case_count": 2, "passed_case_count": 5}

    payload2 = validator.validate_payload(bad2, _schema())

    assert payload2["contract_pass"] is False
    assert "summary.passed_case_count_exceeds_case_count" in payload2["blockers"]


def test_fresh_validation_receipt_validator_rejects_placeholders() -> None:
    bad = _valid_payload()
    bad["lane_id"] = "OWNER_INPUT_REQUIRED_LANE_ID"

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "placeholder_marker_present" in payload["blockers"]


def test_fresh_validation_receipt_validator_rejects_wrong_schema_version() -> None:
    bad = _valid_payload()
    bad["schema_version"] = "fresh-validation-receipt.v0"

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert any(b.startswith("fixed_value_mismatch:schema_version") for b in payload["blockers"])
    assert any(b.startswith("schema_violation:") for b in payload["blockers"])


def test_fresh_validation_receipt_template_is_validated_as_placeholder() -> None:
    template_payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    payload = validator.validate_payload(template_payload, _schema())

    assert payload["contract_pass"] is False
    assert "placeholder_marker_present" in payload["blockers"]


def test_fresh_validation_receipt_cli_returns_nonzero_when_blocked(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_valid_payload()), encoding="utf-8")
    out = tmp_path / "result.json"

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--receipt",
            str(receipt),
            "--schema",
            str(SCHEMA_PATH),
            "--out",
            str(out),
            "--fail-blocked",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert out.exists()
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["contract_pass"] is True
