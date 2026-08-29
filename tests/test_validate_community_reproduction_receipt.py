from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from scripts import validate_community_reproduction_receipt as validator
from scripts.validate_community_reproduction_receipt import validate_receipt


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas/community-reproduction-receipt.v1.schema.json").read_text(
        encoding="utf-8"
    )
)
SAMPLE = json.loads(
    (ROOT / "examples/community-reproduction-receipt.sample.json").read_text(
        encoding="utf-8"
    )
)


def test_sample_receipt_is_valid_but_not_independent_credit() -> None:
    report = validate_receipt(SAMPLE, schema=SCHEMA)
    assert report["schema_pass"] is True
    assert report["contract_pass"] is True
    assert report["execution_pass"] is True
    assert report["eligible_for_community_reproduction_credit"] is False


def test_receipt_requires_engine_and_execution_plan_identity() -> None:
    receipt = copy.deepcopy(SAMPLE)
    del receipt["engine_artifact_sha256"]
    del receipt["execution_plan_sha256"]
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["schema_pass"] is False
    assert report["contract_pass"] is False
    assert any("engine_artifact_sha256" in error for error in report["schema_errors"])
    assert any("execution_plan_sha256" in error for error in report["schema_errors"])


def test_hip_receipt_requires_rocm_and_stable_gpu_identity() -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["execution"]["backend"] = "hip"
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert report["contract_errors"] == [
        "hip_backend_requires_gpu_architecture",
        "hip_backend_requires_gpu_device_uuid",
        "hip_backend_requires_rocm_version",
    ]


def test_independent_receipt_requires_signature_and_time() -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["attestation"]["independent_from_repository_author"] = True
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert report["contract_errors"] == [
        "independent_receipt_requires_signature_reference",
        "independent_receipt_requires_signed_at",
    ]


def test_self_declared_signed_independent_receipt_cannot_receive_credit() -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["attestation"] = {
        "operator": "independent-example",
        "independent_from_repository_author": True,
        "signed_at": "2026-08-17T00:00:00Z",
        "signature_reference": "sha256:" + "1" * 64,
    }
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["contract_pass"] is True
    assert report["independent_operator_claimed"] is True
    assert report["signature_claimed"] is True
    assert report["independent_operator_verified"] is False
    assert report["signature_verified"] is False
    assert report["eligible_for_community_reproduction_credit"] is False
    assert report["credit_blockers"] == [
        "independent_operator_identity_not_verified",
        "signature_not_cryptographically_verified",
    ]
    assert "no community reproduction credit" in report["claim_boundary"]


def test_caller_supplied_empty_schema_cannot_bypass_official_contract() -> None:
    receipt = copy.deepcopy(SAMPLE)
    del receipt["engine_artifact_sha256"]
    report = validate_receipt(receipt, schema={})
    assert report["schema_pass"] is False
    assert report["contract_pass"] is False
    assert "official_schema_sha256_mismatch" in report["schema_errors"]
    assert any("engine_artifact_sha256" in error for error in report["schema_errors"])


def test_require_independent_fails_closed_for_self_declared_signature(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["attestation"] = {
        "operator": "independent-example",
        "independent_from_repository_author": True,
        "signed_at": "2026-08-17T00:00:00Z",
        "signature_reference": "sha256:" + "1" * 64,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert validator.main([str(receipt_path), "--require-independent"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["eligible_for_community_reproduction_credit"] is False
    assert "signature_not_cryptographically_verified" in report["credit_blockers"]


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"first","schema_version":"second"}',
        '{"metrics":{"runtime_seconds":NaN}}',
    ],
)
def test_receipt_loader_rejects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        validator._load_object(path)


def test_direct_nonfinite_receipt_value_is_rejected() -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["metrics"]["runtime_seconds"] = math.nan
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["schema_pass"] is False
    assert "non_finite_json_number:$.metrics.runtime_seconds" in report["schema_errors"]
