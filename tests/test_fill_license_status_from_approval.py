from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
    evidence = tmp_path / "legal-approval.json"
    evidence.write_text(json.dumps({"approved": True}), encoding="utf-8")
    license_status = tmp_path / "license_status.json"
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
        approval_ref="LEGAL-123",
        approved_at_utc="2026-06-01T00:00:00+00:00",
        evidence_ref=str(evidence),
        expires_at_utc="2027-01-01T00:00:00+00:00",
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
    license_status = tmp_path / "license_status.json"
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
    assert _read_json(license_status)["license_id"] == "LICENSE-ID"
