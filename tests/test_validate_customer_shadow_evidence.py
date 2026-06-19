from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "implementation/phase1/validate_customer_shadow_evidence.py"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "implementation/phase1/customer_shadow_evidence.schema.json"
SPEC = importlib.util.spec_from_file_location("validate_customer_shadow_evidence", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_payload() -> dict[str, object]:
    return {
        "case_id": "shadow-case-001",
        "project_status": "completed",
        "structure_family": "wall-frame",
        "reference_solver": "MIDAS",
        "reference_solver_version": "v1",
        "reference_output_checksum": "sha256:abcdef123456",
        "our_engine_commit": "7a40f599",
        "delta_metrics": {"max_relative_error_pct": 2.1},
        "residual_metrics": {"normalized_equilibrium_residual": 0.0004},
        "reviewer_decision": "REVIEW",
        "known_limitations": ["customer retains raw data"],
        "reproduce_bundle_id": "bundle-001",
        "raw_data_retained_by_customer": True,
        "redistribution_allowed": False,
    }


def test_customer_shadow_evidence_validator_accepts_valid_payload() -> None:
    payload = validator.validate_payload(_valid_payload(), _schema())

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["summary"]["raw_data_retained_by_customer"] is True
    assert payload["summary"]["redistribution_allowed"] is False


def test_customer_shadow_evidence_validator_rejects_raw_redistribution_and_placeholders() -> None:
    bad = _valid_payload()
    bad["case_id"] = "OWNER_INPUT_REQUIRED_CASE_ID"
    bad["redistribution_allowed"] = True
    bad["reference_output_checksum"] = "not-a-sha"

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "fixed_value_mismatch:redistribution_allowed" in payload["blockers"]
    assert "placeholder_marker_present" in payload["blockers"]
    assert "reference_output_checksum_not_sha256" in payload["blockers"]


def test_customer_shadow_evidence_validator_rejects_missing_metrics() -> None:
    bad = _valid_payload()
    bad["delta_metrics"] = {}
    bad.pop("residual_metrics")

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "missing_field:residual_metrics" in payload["blockers"]
    assert "empty_required_field:delta_metrics" in payload["blockers"]
    assert "delta_metrics_missing_or_empty" in payload["blockers"]
    assert "residual_metrics_missing_or_empty" in payload["blockers"]


def test_customer_shadow_evidence_validator_rejects_empty_required_fields() -> None:
    bad = _valid_payload()
    bad["reference_output_checksum"] = ""
    bad["known_limitations"] = []

    payload = validator.validate_payload(bad, _schema())

    assert payload["contract_pass"] is False
    assert "empty_required_field:reference_output_checksum" in payload["blockers"]
    assert "empty_required_field:known_limitations" in payload["blockers"]
