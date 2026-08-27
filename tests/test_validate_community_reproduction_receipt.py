from __future__ import annotations

import copy
import json
from pathlib import Path

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


def test_signed_independent_receipt_can_receive_bounded_credit() -> None:
    receipt = copy.deepcopy(SAMPLE)
    receipt["attestation"] = {
        "operator": "independent-example",
        "independent_from_repository_author": True,
        "signed_at": "2026-08-17T00:00:00Z",
        "signature_reference": "sha256:" + "1" * 64,
    }
    report = validate_receipt(receipt, schema=SCHEMA)
    assert report["contract_pass"] is True
    assert report["eligible_for_community_reproduction_credit"] is True
    assert "grants no product" in report["claim_boundary"]
