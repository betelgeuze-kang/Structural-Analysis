from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_internal_license_due_diligence.py"
SPEC = importlib.util.spec_from_file_location(
    "build_internal_license_due_diligence",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
due_diligence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = due_diligence
SPEC.loader.exec_module(due_diligence)


def test_internal_due_diligence_is_complete_without_promoting_legal_authority() -> None:
    payload = due_diligence.build_internal_license_due_diligence(ROOT)

    assert payload["status"] == "complete"
    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert [row["inventory_id"] for row in payload["inventory"]] == list(
        due_diligence.REQUIRED_INVENTORY_IDS
    )
    assert payload["components"]["license_inventory"]["inventory_count"] == 7
    assert payload["components"]["spdx_notices"]["contract_pass"] is True
    assert (
        payload["components"]["redistribution_boundary"]["contract_pass"]
        is True
    )
    assert (
        payload["components"]["source_use_declarations"]["contract_pass"]
        is True
    )
    assert payload["claims"]["internal_due_diligence_complete"] is True
    assert payload["claims"]["third_party_material_clearance_complete"] is False
    assert payload["claims"]["product_legal_approval"] is False
    assert payload["claims"]["product_commercial_redistribution_approved"] is False
    assert payload["claims"]["formal_verification_level_2"] is False
    assert payload["claims"]["release_authority"] is False
    assert len(payload["external_actions"]) == 6
    assert "not legal advice" in payload["claim_boundary"]


def test_internal_due_diligence_schema_and_committed_manifest_are_current() -> None:
    schema = json.loads(
        (ROOT / due_diligence.SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    payload = json.loads(
        (ROOT / due_diligence.DEFAULT_OUT).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)
    due_diligence.validate_internal_license_due_diligence(
        payload,
        repo_root=ROOT,
    )
    ok, message = due_diligence.check_internal_license_due_diligence(
        repo_root=ROOT,
    )
    assert ok, message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_legal_approval", True),
        ("product_commercial_redistribution_approved", True),
        ("formal_verification_level_2", True),
        ("release_authority", True),
    ],
)
def test_internal_due_diligence_rejects_authority_promotion_tamper(
    field: str,
    value: bool,
) -> None:
    payload = due_diligence.build_internal_license_due_diligence(ROOT)
    payload["claims"][field] = value

    with pytest.raises(
        due_diligence.InternalLicenseDueDiligenceError,
        match="internal_license_due_diligence_mismatch",
    ):
        due_diligence.validate_internal_license_due_diligence(
            payload,
            repo_root=ROOT,
        )


def test_internal_due_diligence_rejects_inventory_and_hash_tamper() -> None:
    payload = due_diligence.build_internal_license_due_diligence(ROOT)
    payload["inventory"][2]["source_use_declaration"] = "tampered"

    with pytest.raises(
        due_diligence.InternalLicenseDueDiligenceError,
        match="internal_license_due_diligence_mismatch",
    ):
        due_diligence.validate_internal_license_due_diligence(
            payload,
            repo_root=ROOT,
        )
