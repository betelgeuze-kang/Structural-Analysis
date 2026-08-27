from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_mgt_import_health_current_source_receipt.py"
MANIFEST = ROOT / "benchmarks/import_health/mgt_current_source.v1.json"
MANIFEST_SCHEMA = (
    ROOT / "canonical/mgt-import-health-current-source-manifest.v1.schema.json"
)
RECEIPT_SCHEMA = (
    ROOT
    / "canonical/mgt-import-health-current-source-technical-receipt.v1.schema.json"
)
RECEIPT = ROOT / ".ci/mgt-import-health-current-source/technical-receipt.json"

SPEC = importlib.util.spec_from_file_location("mgt_import_health", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


@pytest.fixture(scope="module")
def receipt() -> dict:
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-commit-sha",
            source_sha,
            "--allow-dirty-source",
            "--fail-available-blocked",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_manifest_is_strict_and_counts_only_nine_unique_lineages() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))

    assert module._schema_errors(manifest, schema) == []
    assert manifest["target_independent_case_count"] == 10
    assert manifest["available_independent_case_count"] == 9
    assert len(manifest["cases"]) == 9
    assert len({row["case_id"] for row in manifest["cases"]}) == 9
    assert len({row["lineage_id"] for row in manifest["cases"]}) == 9
    assert len({row["expected_sha256"] for row in manifest["cases"]}) == 9
    assert manifest["target_gap"]["missing_independent_case_count"] == 1
    assert manifest["target_gap"]["artifact_attached"] is False
    assert manifest["target_gap"]["source_owner_identified"] is False
    assert manifest["target_gap"]["rights_basis_recorded"] is False


def test_current_source_receipt_executes_all_available_cases_without_target_promotion(
    receipt: dict,
) -> None:
    assert receipt["technical_available_set_contract_pass"] is True
    assert receipt["target_10_case_contract_pass"] is False
    assert receipt["status"] == "available_set_pass_target_blocked"
    assert receipt["summary"] == {
        "available_independent_case_count": 9,
        "case_contract_pass_count": 9,
        "clean_case_count": 2,
        "dirty_case_count": 7,
        "executed_case_count": 9,
        "record_accounting_pass_count": 9,
        "rights_reviewed_case_count": 0,
        "silent_loss_negative_pass_count": 9,
        "target_independent_case_count": 10,
    }
    assert receipt["technical_blockers"] == []
    assert receipt["target_blockers"] == [
        "independent_source_model_identity_shortfall:9/10",
        "mgt_import_health_independent_source_10_missing",
    ]
    assert all(row["contract_pass"] is True for row in receipt["cases"])
    assert all(value is False for value in receipt["claims"].values())
    assert receipt["raw_mgt_files_uploaded"] is False


def test_each_case_records_provenance_visible_accounting_and_negative_mutation(
    receipt: dict,
) -> None:
    for row in receipt["cases"]:
        assert row["source"]["tracked"] is True
        assert row["source"]["expected_sha256"] == row["source"][
            "observed_sha256"
        ]
        assert row["source"]["expected_size_bytes"] == row["source"][
            "observed_size_bytes"
        ]
        assert row["provenance_and_rights"]["source_owner"]
        assert row["provenance_and_rights"]["provenance_status"]
        assert row["provenance_and_rights"]["rights_status"]
        assert row["provenance_and_rights"]["redistribution_reviewed"] is False
        assert row["provenance_and_rights"]["commercial_use_reviewed"] is False
        accounting = row["record_accounting"]
        assert accounting["unaccounted_row_count"] == 0
        assert accounting["source_data_row_count"] == (
            accounting["parser_recognized_row_count"]
            + accounting["visible_unsupported_or_omitted_row_count"]
        )
        assert row["negative_silent_loss_gate"] == {
            "accounting_mutation_reason": "node_parser_balance_mismatch",
            "accounting_record_deletion_detected": True,
            "source_mutation_reason": "source_sha256_and_record_count_mismatch",
            "source_record_deletion_detected": True,
        }
        report_path = ROOT / row["parser"]["report_path"]
        assert report_path.is_file()
        assert module._sha256(report_path) == row["parser"]["report_sha256"]


def test_strict_receipt_schema_rejects_unknown_property(receipt: dict) -> None:
    schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
    assert module._schema_errors(receipt, schema) == []

    tampered = deepcopy(receipt)
    tampered["unexpected"] = True
    assert any(
        "Additional properties are not allowed" in error
        for error in module._schema_errors(tampered, schema)
    )


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda payload: payload["cases"][1].__setitem__(
                "lineage_id", payload["cases"][0]["lineage_id"]
            ),
            "duplicate_lineage_credit",
        ),
        (
            lambda payload: payload["cases"][1]["source"].__setitem__(
                "observed_sha256",
                payload["cases"][0]["source"]["observed_sha256"],
            ),
            "duplicate_source_sha256_credit",
        ),
        (
            lambda payload: payload["summary"].__setitem__(
                "case_contract_pass_count", 10
            ),
            "summary_mismatch:case_contract_pass_count",
        ),
        (
            lambda payload: payload["claims"].__setitem__(
                "release_authority", True
            ),
            "authority_claim_not_false:release_authority",
        ),
        (
            lambda payload: payload.__setitem__(
                "target_10_case_contract_pass", True
            ),
            "target_10_case_contract_mismatch",
        ),
    ],
)
def test_semantic_validator_rejects_credit_or_authority_tamper(
    receipt: dict, mutator, expected_error: str
) -> None:
    tampered = deepcopy(receipt)
    mutator(tampered)
    assert expected_error in module.validate_receipt_semantics(tampered)


def test_semantic_validator_rejects_silent_entity_accounting_drop(
    receipt: dict,
) -> None:
    tampered = deepcopy(receipt)
    tampered["cases"][0]["entity_accounting"]["node"][
        "parser_reported_parsed_count"
    ] -= 1

    errors = module.validate_receipt_semantics(tampered)

    assert "summary_mismatch:record_accounting_pass_count" in errors
