from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from scripts import validate_third_party_material_inventory as validator
from scripts.validate_third_party_material_inventory import validate_inventory


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas/third-party-material-inventory.v1.schema.json").read_text(
        encoding="utf-8"
    )
)
SAMPLE = json.loads(
    (ROOT / "examples/third-party-material-inventory.sample.json").read_text(
        encoding="utf-8"
    )
)


def test_sample_inventory_is_contract_valid_without_granting_authority() -> None:
    report = validate_inventory(SAMPLE, schema=SCHEMA)
    assert report["schema_pass"] is True
    assert report["contract_pass"] is True
    assert report["approved_count"] == 1
    assert report["restricted_count"] == 1
    assert "grants no software-use" in report["claim_boundary"]
    assert "release authority" in report["claim_boundary"]


def test_permission_cannot_be_asserted_from_unreviewed_or_restricted_row() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["permissions"]["use"] = True
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.startswith(
            "permission_asserted_without_approved_review:example-restricted-dataset"
        )
        for error in report["contract_errors"]
    )


def test_approved_or_permissioned_row_requires_evidence() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["evidence_reference"] = None
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "permission_evidence_missing:example-reviewed-schema-source"
        in report["contract_errors"]
    )


def test_approved_row_requires_unambiguous_license_identifier() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["license_identifier"] = "unknown"
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "approved_license_identifier_missing_or_ambiguous:example-reviewed-schema-source"
        in report["contract_errors"]
    )


def test_redistribution_derivatives_and_training_require_use_permission() -> None:
    payload = copy.deepcopy(SAMPLE)
    approved = payload["entries"][1]
    approved["permissions"] = {
        "use": False,
        "redistribution": True,
        "derivative_works": True,
        "training": True,
    }
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "redistribution_requires_use:example-reviewed-schema-source"
        in report["contract_errors"]
    )
    assert (
        "derivative_works_requires_use:example-reviewed-schema-source"
        in report["contract_errors"]
    )
    assert (
        "training_requires_use:example-reviewed-schema-source"
        in report["contract_errors"]
    )


def test_duplicate_material_and_path_credit_is_rejected() -> None:
    payload = copy.deepcopy(SAMPLE)
    duplicate = copy.deepcopy(payload["entries"][0])
    duplicate["path_globs"] = payload["entries"][1]["path_globs"]
    payload["entries"].append(duplicate)
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "duplicate_material_id:example-restricted-dataset" in report["contract_errors"]
    )
    assert any(
        error.startswith(
            "duplicate_path_glob:examples/external/reviewed-schema-source.json"
        )
        for error in report["contract_errors"]
    )


def test_approved_row_must_assert_at_least_one_bounded_permission() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["permissions"] = {
        "use": False,
        "redistribution": False,
        "derivative_works": False,
        "training": False,
    }
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert (
        "approved_row_asserts_no_permission:example-reviewed-schema-source"
        in report["contract_errors"]
    )


@pytest.mark.parametrize(
    "path_glob",
    [
        "../outside/**",
        "/absolute/**",
        "examples\\external\\**",
        "**",
    ],
)
def test_path_glob_must_be_bounded_canonical_repo_relative(path_glob: str) -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["path_globs"] = [path_glob]
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.startswith(("repo_relative_path_invalid:", "path_glob_too_broad:"))
        for error in report["contract_errors"]
    )


@pytest.mark.parametrize(
    "reference",
    ["../outside.txt", "/absolute.txt", "docs\\licenses\\receipt.txt"],
)
def test_evidence_reference_must_be_canonical_repo_relative(reference: str) -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["evidence_reference"] = reference
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.startswith(
            "repo_relative_path_invalid:evidence_reference:"
            "example-reviewed-schema-source:"
        )
        for error in report["contract_errors"]
    )


def test_source_reference_can_remain_an_external_identifier() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["source_reference"] = (
        "https://example.invalid/datasets/reference?id=1"
    )
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is True


def test_nested_recursive_globs_cannot_double_count_inventory_scope() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][1]["path_globs"] = ["examples/external/example-only/nested/**"]
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.startswith("overlapping_path_glob:")
        for error in report["contract_errors"]
    )


@pytest.mark.parametrize(
    "path_glob",
    [
        "examples/external/*.json",
        "examples/external/file?.json",
        "examples/external/[ab].json",
        "examples/**/file.json",
        "examples/external/**/file.json",
    ],
)
def test_path_glob_rejects_every_nonterminal_recursive_pattern(
    path_glob: str,
) -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["path_globs"] = [path_glob]
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.endswith(":path_glob_grammar_invalid")
        for error in report["contract_errors"]
    )


def test_literal_path_under_recursive_prefix_is_overlap() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["path_globs"] = ["examples/external/**"]
    payload["entries"][1]["path_globs"] = [
        "examples/external/reviewed-schema-source.json"
    ]
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    assert any(
        error.startswith("overlapping_path_glob:")
        for error in report["contract_errors"]
    )


def test_path_glob_and_evidence_reference_reject_symlink_risk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "safe").mkdir()
    (repo / "outside").mkdir()
    (repo / "safe" / "linked").symlink_to(repo / "outside", target_is_directory=True)
    monkeypatch.setattr(validator, "ROOT", repo)

    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["path_globs"] = ["safe/linked/**"]
    payload["entries"][1]["evidence_reference"] = "safe/linked/receipt.json"
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["contract_pass"] is False
    symlink_errors = [
        error
        for error in report["contract_errors"]
        if error.startswith("repo_path_symlink_risk:")
    ]
    assert len(symlink_errors) >= 2


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"first","schema_version":"second"}',
        '{"entries":NaN}',
    ],
)
def test_inventory_loader_rejects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        validator._load_object(path)


def test_direct_nonfinite_inventory_value_is_rejected() -> None:
    payload = copy.deepcopy(SAMPLE)
    payload["entries"][0]["notes"] = [math.nan]
    report = validate_inventory(payload, schema=SCHEMA)
    assert report["schema_pass"] is False
    assert "non_finite_json_number:$.entries[0].notes[0]" in report["schema_errors"]
