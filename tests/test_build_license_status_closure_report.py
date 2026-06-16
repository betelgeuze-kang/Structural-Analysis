from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_license_status_closure_report.py"
SPEC = importlib.util.spec_from_file_location("build_license_status_closure_report", SCRIPT_PATH)
assert SPEC is not None
build_license_status_closure_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_license_status_closure_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_license_status_closure_blocks_not_configured_status(tmp_path: Path) -> None:
    license_status = _write(tmp_path / "license_status.json", {"status": "not_configured"})

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_status_not_active" in payload["blockers"]
    assert "license_tier_missing" in payload["blockers"]
    assert payload["summary"]["owner_action"].startswith("Populate license_status.json")


def test_license_status_closure_passes_populated_future_license(tmp_path: Path) -> None:
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-001",
            "issuer": "product-owner",
            "approval_ref": "LEGAL-123",
            "product_scope": ["review-assist", "specified-workflows"],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["summary"]["product_scope_count"] == 2


def test_license_status_closure_rejects_template_placeholders(tmp_path: Path) -> None:
    license_status = _write(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LICENSE-ID",
            "issuer": "product-or-legal-owner",
            "approval_ref": "LEGAL-OR-PRODUCT-APPROVAL-ID",
            "product_scope": ["review-assist"],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
            "template_only": True,
            "note": "Template only. Do not use as release evidence.",
        },
    )

    payload = build_license_status_closure_report.build_report(
        license_status_path=license_status,
        now=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )

    assert payload["contract_pass"] is False
    assert "license_id_placeholder" in payload["blockers"]
    assert "license_issuer_or_approver_placeholder" in payload["blockers"]
    assert "license_approval_reference_placeholder" in payload["blockers"]
    assert "license_status_template_only" in payload["blockers"]
    assert payload["checks"]["placeholder_values_absent_pass"] is False
