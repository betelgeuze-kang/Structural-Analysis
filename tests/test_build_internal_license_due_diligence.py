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


def _current_dataset_manifest(tmp_path: Path) -> Path:
    import build_developer_preview_readiness

    out = tmp_path / "developer_preview_dataset_license_manifest.json"
    out.write_text(
        json.dumps(
            build_developer_preview_readiness.build_dataset_license_manifest(
                repo_root=ROOT
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return out


def _current_external_receipt(source: Path, target: Path) -> Path:
    payload = json.loads((ROOT / source).read_text(encoding="utf-8"))
    payload["source_commit_sha"] = due_diligence.git_head(ROOT)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def test_internal_due_diligence_is_complete_without_promoting_legal_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        due_diligence,
        "DATASET_LICENSE_MANIFEST",
        _current_dataset_manifest(tmp_path),
    )
    external_code = _current_external_receipt(
        due_diligence.EXTERNAL_CODE_RECEIPT,
        tmp_path / "external_code.json",
    )
    external_modal = _current_external_receipt(
        due_diligence.EXTERNAL_MODAL_RECEIPT,
        tmp_path / "external_modal.json",
    )
    payload = due_diligence.build_internal_license_due_diligence(
        ROOT,
        external_code_receipt=external_code,
        external_modal_receipt=external_modal,
    )

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
    assert payload["claims"]["repo_generated_preview_seed_bundle_policy_ready"] is False
    assert payload["claims"]["formal_verification_level_2"] is False
    assert payload["claims"]["release_authority"] is False
    repo_generated = next(
        row
        for row in payload["inventory"]
        if row["inventory_id"] == "developer_preview_repo_generated_seed_corpus"
    )
    assert repo_generated["spdx_or_license_ref"] == (
        "LicenseRef-Repository-Default-No-License"
    )
    assert repo_generated["redistribution_allowed"] is False
    assert repo_generated["commercial_use_approved"] is False
    assert repo_generated["review_status"] == (
        "signed_rights_holder_decision_required"
    )
    assert (
        payload["components"]["redistribution_boundary"]
        ["bounded_preview_redistribution_allowed_count"]
        == 0
    )
    assert len(payload["external_actions"]) == 6
    assert "not legal advice" in payload["claim_boundary"]


def test_internal_due_diligence_schema_and_generated_manifest_are_current(
    tmp_path: Path,
) -> None:
    schema = json.loads(
        (ROOT / due_diligence.SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    out = tmp_path / "internal_license_due_diligence.current.v1.json"
    payload = due_diligence.write_internal_license_due_diligence(
        repo_root=ROOT,
        out_path=out,
    )
    Draft202012Validator(schema).validate(payload)
    due_diligence.validate_internal_license_due_diligence(
        payload,
        repo_root=ROOT,
    )
    ok, message = due_diligence.check_internal_license_due_diligence(
        repo_root=ROOT,
        out_path=out,
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


def test_internal_due_diligence_separates_receipt_age_from_replay_validity(
    tmp_path: Path,
) -> None:
    receipt_paths: list[Path] = []
    for source in (
        due_diligence.EXTERNAL_CODE_RECEIPT,
        due_diligence.EXTERNAL_MODAL_RECEIPT,
    ):
        payload = json.loads((ROOT / source).read_text(encoding="utf-8"))
        payload["source_commit_sha"] = "0" * 40
        target = tmp_path / source.name
        target.write_text(json.dumps(payload), encoding="utf-8")
        receipt_paths.append(target)

    payload = due_diligence.build_internal_license_due_diligence(
        ROOT,
        external_code_receipt=receipt_paths[0],
        external_modal_receipt=receipt_paths[1],
    )
    assert payload["status"] == "complete"
    assert payload["claims"]["release_authority"] is False

    stale_code = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    stale_code["replay_provenance"]["current_product_replay_pass"] = False
    receipt_paths[0].write_text(json.dumps(stale_code), encoding="utf-8")
    blocked = due_diligence.build_internal_license_due_diligence(
        ROOT,
        external_code_receipt=receipt_paths[0],
        external_modal_receipt=receipt_paths[1],
    )
    assert blocked["status"] == "blocked"
    assert "external_code_to_code_product_replay_not_passed" in blocked["blockers"]
