from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_validation_dataset_split import validate_split


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas/validation-dataset-split.v1.schema.json").read_text(encoding="utf-8")
)
SAMPLE = json.loads(
    (ROOT / "examples/validation-dataset-split.sample.json").read_text(encoding="utf-8")
)


def test_example_split_is_leakage_free_and_contains_locked_validation() -> None:
    report = validate_split(SAMPLE, schema=SCHEMA)
    assert report["contract_pass"] is True
    assert report["locked_validation_present"] is True
    assert report["blind_prediction_present"] is True
    assert report["contract_errors"] == []


def test_sample_cannot_cross_roles() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["groups"][1]["sample_ids"] = ["calibration-cycle-set-01"]
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "duplicate_sample_id:calibration-cycle-set-01" in report["contract_errors"]
    assert any(
        error.startswith("sample_cross_role_leakage:calibration-cycle-set-01")
        for error in report["contract_errors"]
    )


def test_group_key_cannot_cross_roles() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["groups"][2]["group_key"] = "specimen-validation-01"
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "duplicate_group_key:specimen-validation-01" in report["contract_errors"]
    assert any(
        error.startswith("group_key_cross_role_leakage:specimen-validation-01")
        for error in report["contract_errors"]
    )


def test_duplicate_sample_in_same_role_cannot_double_count_credit() -> None:
    payload = copy.deepcopy(SAMPLE)
    duplicate = copy.deepcopy(payload["groups"][0])
    duplicate["group_key"] = "specimen-calibration-02"
    payload["groups"].append(duplicate)
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "duplicate_sample_id:calibration-cycle-set-01" in report["contract_errors"]


def test_training_role_requires_license_permission() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["license"]["training_allowed"] = False
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "training_role_not_permitted_by_license:0:calibration" in report[
        "contract_errors"
    ]


def test_locked_validation_requires_parameter_freeze() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["groups"][1]["parameters_frozen_at"] = None
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "locked_role_requires_parameters_frozen_at:1:locked_validation" in report[
        "contract_errors"
    ]


def test_locked_validation_requires_parameter_snapshot_hash() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["groups"][1]["parameter_snapshot_sha256"] = None
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "locked_role_requires_parameter_snapshot_sha256:1:locked_validation"
        in report["contract_errors"]
    )


def test_blind_results_must_remain_undisclosed() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["groups"][2]["results_disclosed"] = True
    report = validate_split(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert "blind_prediction_results_must_be_undisclosed:2" in report[
        "contract_errors"
    ]


def test_validation_report_never_grants_scientific_or_release_authority() -> None:
    report = validate_split(SAMPLE, schema=SCHEMA)
    boundary = report["claim_boundary"].lower()
    assert "no numerical" in boundary
    assert "experimental-validation" in boundary
    assert "no" in boundary
    assert "release authority" in boundary
