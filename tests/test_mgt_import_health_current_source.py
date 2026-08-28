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


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"a","schema_version":"b"}',
        '{"metric":NaN}',
        '{"metric":Infinity}',
        '{"metric":1e9999}',
    ],
)
def test_mgt_current_raw_json_rejects_duplicate_and_nonfinite_input(
    tmp_path: Path,
    raw: str,
) -> None:
    target = tmp_path / "attack.json"
    target.write_text(raw, encoding="utf-8")
    with pytest.raises(module.ReceiptError, match="duplicate|nonfinite"):
        module._load_json(tmp_path, Path("attack.json"))


@pytest.mark.parametrize("symlink_part", [".ci", "mgt-import-health-current-source"])
def test_mgt_current_evidence_path_rejects_symlink_ancestors(
    tmp_path: Path,
    symlink_part: str,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-{symlink_part}"
    outside.mkdir()
    if symlink_part == ".ci":
        (tmp_path / ".ci").symlink_to(outside, target_is_directory=True)
    else:
        (tmp_path / ".ci").mkdir()
        (tmp_path / ".ci" / symlink_part).symlink_to(
            outside,
            target_is_directory=True,
        )
    with pytest.raises(module.ReceiptError, match="symlink_forbidden"):
        module._validated_evidence_dir(tmp_path, module.DEFAULT_EVIDENCE_DIR)
    assert list(outside.iterdir()) == []


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


def test_model_identity_collapses_declared_derived_variants() -> None:
    foundation_paths = [
        ROOT / "tests/fixtures/foundation_realish/foundation_small.mgt",
        ROOT / "tests/fixtures/foundation_realish/foundation_generic_sections.mgt",
        ROOT / "tests/fixtures/foundation_realish/foundation_parser_drop_small.mgt",
    ]
    generator_paths = [
        ROOT / "implementation/phase1/open_data/midas/midas_generator_33.mgt",
        ROOT
        / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    ]

    assert len(
        {
            module._scan_source(path)["model_identity_sha256"]
            for path in foundation_paths
        }
    ) == 1
    assert len(
        {
            module._scan_source(path)["model_identity_sha256"]
            for path in generator_paths
        }
    ) == 1


def test_model_identity_is_invariant_to_node_and_element_row_order() -> None:
    first = {
        "NODE": ["2, 1, 0, 0", "1, 0, 0, 0"],
        "ELEMENT": ["20, BEAM, 1, 1, 2, 1", "10, BEAM, 1, 1, 1, 2"],
    }
    reordered = {
        "NODE": list(reversed(first["NODE"])),
        "ELEMENT": list(reversed(first["ELEMENT"])),
    }

    assert module._model_identity_sha256(first) == module._model_identity_sha256(
        reordered
    )


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
        negative = row["negative_silent_loss_gate"]
        assert negative["source_record_deletion_detected"] is True
        assert negative["accounting_record_deletion_detected"] is True
        assert negative["parser_replay_executed"] is True
        assert negative["parser_return_code_matches_contract"] is True
        assert negative["deleted_record_kind"] == "node"
        assert negative["raw_mutated_input_retained"] is False
        assert negative["source_mutation_reason"] == (
            "source_sha256_and_record_count_mismatch"
        )
        assert negative["accounting_mutation_reason"] == (
            "live_parser_replay_detected_deleted_node_identity"
        )
        negative_report = ROOT / negative["parser_report_path"]
        assert negative_report.is_file()
        negative_report_payload = json.loads(
            negative_report.read_text(encoding="utf-8")
        )
        assert module._stable_report_sha256(negative_report_payload) == negative[
            "parser_report_semantic_sha256"
        ]
        assert not list(
            (ROOT / module.DEFAULT_EVIDENCE_DIR / "negative-inputs").glob("*.mgt")
        )
        report_path = ROOT / row["parser"]["report_path"]
        assert report_path.is_file()
        assert module._sha256(report_path) == row["parser"]["report_sha256"]


def test_current_artifact_recalculation_accepts_untampered_receipt(
    receipt: dict,
) -> None:
    assert (
        module.validate_receipt_artifact_bindings(
            receipt,
            repo_root=ROOT,
            require_clean_source=False,
        )
        == []
    )


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


def test_case_contract_rejects_coherent_parser_return_code_mismatch(
    receipt: dict,
) -> None:
    tampered = deepcopy(receipt["cases"][0])
    tampered["parser"]["return_code"] = 7
    tampered["parser"]["return_code_matches_contract"] = False

    assert "parser_return_code_contract_invalid" in module._case_contract_errors(
        tampered
    )


def test_tenth_case_target_requires_attached_owned_rights_basis() -> None:
    unresolved = {
        "blocker_id": "mgt_import_health_independent_source_10_missing",
        "missing_independent_case_count": 0,
        "artifact_attached": False,
        "source_owner_identified": False,
        "rights_basis_recorded": False,
    }
    blockers = module._target_gap_blockers(case_count=10, target_gap=unresolved)

    assert "target_gap_blocker_not_cleared" in blockers
    assert "target_gap_condition_not_met:artifact_attached" in blockers
    assert "target_gap_condition_not_met:source_owner_identified" in blockers
    assert "target_gap_condition_not_met:rights_basis_recorded" in blockers
    resolved = {
        **unresolved,
        "blocker_id": None,
        "artifact_attached": True,
        "source_owner_identified": True,
        "rights_basis_recorded": True,
    }
    assert module._target_gap_blockers(case_count=10, target_gap=resolved) == []


@pytest.mark.parametrize(
    "unsafe",
    [Path("."), Path(".."), Path("../outside"), Path("custom/evidence")],
)
def test_evidence_directory_is_fixed_before_recursive_cleanup(
    tmp_path: Path, unsafe: Path
) -> None:
    with pytest.raises(module.ReceiptError):
        module._validated_evidence_dir(tmp_path.resolve(), unsafe)


def _artifact_errors(payload: dict) -> list[str]:
    return module.validate_receipt_artifact_bindings(
        payload,
        repo_root=ROOT,
        require_clean_source=False,
    )


def test_artifact_validator_rejects_forged_unique_lineage(receipt: dict) -> None:
    tampered = deepcopy(receipt)
    tampered["cases"][0]["lineage_id"] = "forged_unique_lineage"

    assert "case_manifest_projection_mismatch:midas_generator_33_public_source" in (
        _artifact_errors(tampered)
    )


def test_artifact_validator_rejects_owner_and_rights_rewrite(receipt: dict) -> None:
    tampered = deepcopy(receipt)
    rights = tampered["cases"][0]["provenance_and_rights"]
    rights["source_owner"] = "forged owner"
    rights["rights_status"] = "forged_reviewed_terms"
    rights["redistribution_reviewed"] = True
    tampered["summary"]["rights_reviewed_case_count"] = 1

    assert (
        "case_provenance_rights_binding_mismatch:midas_generator_33_public_source"
        in _artifact_errors(tampered)
    )


def test_artifact_validator_rejects_rebalanced_clean_dirty_rewrite(
    receipt: dict,
) -> None:
    tampered = deepcopy(receipt)
    row = tampered["cases"][4]
    row["corpus_class"] = "dirty"
    row["source"]["utf8_replacement_character_count"] = 1
    tampered["summary"]["clean_case_count"] -= 1
    tampered["summary"]["dirty_case_count"] += 1

    errors = _artifact_errors(tampered)
    assert "case_manifest_projection_mismatch:foundation_small_repository_fixture" in (
        errors
    )
    assert "case_source_binding_mismatch:foundation_small_repository_fixture" in errors


def test_artifact_validator_rejects_rebalanced_accounting_rewrite(
    receipt: dict,
) -> None:
    tampered = deepcopy(receipt)
    accounting = tampered["cases"][0]["record_accounting"]
    accounting["source_data_row_count"] += 1
    accounting["visible_unsupported_or_omitted_row_count"] += 1

    assert (
        "case_record_accounting_binding_mismatch:midas_generator_33_public_source"
        in _artifact_errors(tampered)
    )


def test_artifact_validator_rejects_silent_loss_gate_rewrite(receipt: dict) -> None:
    tampered = deepcopy(receipt)
    tampered["cases"][0]["negative_silent_loss_gate"][
        "source_record_deletion_detected"
    ] = False

    assert (
        "case_negative_gate_binding_mismatch:midas_generator_33_public_source"
        in _artifact_errors(tampered)
    )


def test_artifact_validator_rejects_rehashed_source_claim(receipt: dict) -> None:
    tampered = deepcopy(receipt)
    fake_hash = "f" * 64
    tampered["cases"][0]["source"]["expected_sha256"] = fake_hash
    tampered["cases"][0]["source"]["observed_sha256"] = fake_hash

    assert "case_source_binding_mismatch:midas_generator_33_public_source" in (
        _artifact_errors(tampered)
    )


def test_semantic_validator_rejects_forged_model_identity_after_raw_rehash(
    receipt: dict,
) -> None:
    tampered = deepcopy(receipt)
    first = tampered["cases"][0]["source"]
    second = tampered["cases"][1]["source"]
    second["observed_sha256"] = "e" * 64
    second["expected_sha256"] = "e" * 64
    second["record_fingerprint_sha256"] = "d" * 64
    second["model_identity_sha256"] = first["model_identity_sha256"]
    tampered["identity_gate"]["unique_model_identity_count"] = 8
    tampered["identity_gate"]["contract_pass"] = False
    tampered["identity_gate"]["blockers"] = ["duplicate_model_identity_credit"]
    tampered["technical_available_set_contract_pass"] = False
    tampered["status"] = "technical_blocked"
    tampered["technical_blockers"] = ["duplicate_model_identity_credit"]

    assert "duplicate_model_identity_credit" in module.validate_receipt_semantics(
        tampered
    )


def test_semantic_validator_rejects_removed_tenth_case_blocker(receipt: dict) -> None:
    tampered = deepcopy(receipt)
    tampered["target_blockers"] = []
    tampered["target_gap"]["blocker_id"] = ""
    tampered["target_gap"]["artifact_attached"] = True

    errors = module.validate_receipt_semantics(tampered)
    assert "target_blockers_mismatch" in errors
    assert "target_gap_blocker_id_mismatch" in errors
    assert "target_gap_not_false:artifact_attached" in errors
