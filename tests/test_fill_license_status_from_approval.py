from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from tests.license_decision_test_support import (
    DECISION_ID,
    EXPIRES_AT_UTC,
    ISSUED_AT_UTC,
    build_signed_decision_repository,
)


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "fill_license_status_from_approval.py"
)
SPEC = importlib.util.spec_from_file_location("fill_license_status_from_approval", SCRIPT_PATH)
assert SPEC is not None
fill_license_status_from_approval = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fill_license_status_from_approval)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fill_license_status_from_explicit_approval_passes_closure(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    license_status = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json"
    )
    template_path = tmp_path / "license_status.template.json"

    payload = fill_license_status_from_approval.fill_license_status(
        repo_root=tmp_path,
        out=license_status,
        template_path=template_path,
        status="active",
        tier="limited-commercial",
        license_id="LIC-001",
        issuer="product-owner",
        approver_role="product_owner",
        approval_ref=DECISION_ID,
        approved_at_utc=ISSUED_AT_UTC,
        evidence_ref=str(fixture["decision_path"]),
        expires_at_utc=EXPIRES_AT_UTC,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    written = _read_json(license_status)
    assert payload["contract_pass"] is True
    assert payload["status"] == "filled"
    assert payload["validation_blockers"] == []
    assert written["template_only"] is False
    assert written["product_scope"] == [
        "review-assist",
        "specified-structure-families",
        "specified-workflows",
        "engine-and-reviewer-evidence-package",
    ]
    assert any(
        "build_license_status_closure_report.py" in command
        for command in payload["validation_commands"]
    )


def test_fill_license_status_blocks_placeholder_or_missing_expiry(
    tmp_path: Path,
) -> None:
    license_status = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json"
    )
    template_path = tmp_path / "license_status.template.json"

    payload = fill_license_status_from_approval.fill_license_status(
        repo_root=tmp_path,
        out=license_status,
        template_path=template_path,
        status="active",
        tier="limited-commercial",
        license_id="LICENSE-ID",
        issuer="product-owner",
        approver_role="product_owner",
        approval_ref="LEGAL-123",
        approved_at_utc="2026-06-01T00:00:00+00:00",
        evidence_ref="legal:LIC-APPROVAL-001",
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert "license_id_placeholder" in payload["validation_blockers"]
    assert "license_expiry_missing_or_invalid" in payload["validation_blockers"]
    written = _read_json(license_status)
    assert written["license_id"] == "LICENSE-ID"
    assert written["status"] == "not_configured"
    assert written["requested_status"] == "active"


def test_fill_cli_returns_nonzero_when_approval_cannot_be_verified(
    tmp_path: Path,
) -> None:
    exit_code = fill_license_status_from_approval.main(
        [
            "--out",
            str(tmp_path / "license_status.json"),
            "--report-out",
            str(tmp_path / "fill_report.json"),
            "--license-id",
            "LIC-001",
            "--issuer",
            "product-owner",
            "--approver-role",
            "product_owner",
            "--approval-ref",
            "RH-LICENSE-DECISION-001",
            "--approved-at-utc",
            "2020-06-01T00:00:00+00:00",
            "--evidence-ref",
            "legal:RH-LICENSE-DECISION-001",
            "--expires-at-utc",
            "2099-01-01T00:00:00+00:00",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "license_status.json").exists()
    assert not (tmp_path / "fill_report.json").exists()


def test_fill_converts_validation_exception_before_atomic_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    license_status = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json"
    )
    license_status.parent.mkdir(parents=True, exist_ok=True)
    license_status.write_text('{"status":"active"}\n', encoding="utf-8")

    def fail_validation(**_kwargs):
        raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogate")

    monkeypatch.setattr(
        fill_license_status_from_approval.closure_report,
        "build_report",
        fail_validation,
    )
    payload = fill_license_status_from_approval.fill_license_status(
        repo_root=tmp_path,
        out=license_status,
        status="active",
        tier="limited-commercial",
        license_id="LIC-001",
        issuer="product-owner",
        approver_role="product_owner",
        approval_ref=DECISION_ID,
        approved_at_utc=ISSUED_AT_UTC,
        evidence_ref="implementation/phase1/release/license_decisions/bad.json",
        expires_at_utc=EXPIRES_AT_UTC,
    )

    assert payload["contract_pass"] is False
    assert payload["validation_blockers"] == [
        "license_status_validation_exception:UnicodeEncodeError"
    ]
    written = _read_json(license_status)
    assert written["status"] == "not_configured"
    assert written["requested_status"] == "active"


def test_fill_requires_final_canonical_revalidation_after_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    license_status = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "support_bundle"
        / "license_status.json"
    )
    original = fill_license_status_from_approval.closure_report.build_report
    calls = 0

    def reject_final_canonical(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(**kwargs)
        return {
            "status": "blocked",
            "reason_code": "ERR_FINAL_CANONICAL_RECHECK",
            "contract_pass": False,
            "blockers": ["final_canonical_recheck_failed"],
            "summary_line": "License status: BLOCKED | final canonical recheck",
        }

    monkeypatch.setattr(
        fill_license_status_from_approval.closure_report,
        "build_report",
        reject_final_canonical,
    )
    payload = fill_license_status_from_approval.fill_license_status(
        repo_root=tmp_path,
        out=license_status,
        status="active",
        tier="limited-commercial",
        license_id="LIC-001",
        issuer="product-owner",
        approver_role="product_owner",
        approval_ref=DECISION_ID,
        approved_at_utc=ISSUED_AT_UTC,
        evidence_ref=str(fixture["decision_path"]),
        expires_at_utc=EXPIRES_AT_UTC,
        rights_holder_trust_root_path=fixture["trust_root_path"],
    )

    assert calls == 2
    assert payload["contract_pass"] is False
    assert payload["validation_blockers"] == ["final_canonical_recheck_failed"]
    written = _read_json(license_status)
    assert written["status"] == "not_configured"
    assert written["requested_status"] == "active"
