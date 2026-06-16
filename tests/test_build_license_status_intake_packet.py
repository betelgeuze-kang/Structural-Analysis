from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_license_status_intake_packet.py"
SPEC = importlib.util.spec_from_file_location("build_license_status_intake_packet", SCRIPT_PATH)
assert SPEC is not None
build_license_status_intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_license_status_intake_packet)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_license_status_intake_packet_surfaces_owner_fields(tmp_path: Path) -> None:
    license_status = _write_json(tmp_path / "license_status.json", {"status": "not_configured"})
    template = _write_json(
        tmp_path / "license_status.template.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LICENSE-ID",
            "issuer": "product-or-legal-owner",
            "approval_ref": "LEGAL-OR-PRODUCT-APPROVAL-ID",
            "product_scope": ["review-assist"],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )
    closure = _write_json(
        tmp_path / "license_status_closure_report.json",
        {
            "contract_pass": False,
            "blockers": ["license_status_not_active", "license_id_missing"],
            "checks": {
                "status_active_pass": False,
                "tier_present_pass": False,
                "license_id_present_pass": False,
                "issuer_or_approver_present_pass": False,
                "approval_reference_present_pass": False,
                "product_scope_present_pass": False,
                "expiry_valid_pass": False,
                "placeholder_values_absent_pass": True,
            },
            "summary": {
                "owner_action": "Populate license_status.json from an approved product/legal decision.",
            },
        },
    )

    payload = build_license_status_intake_packet.build_packet(
        license_status_path=license_status,
        template_path=template,
        closure_report_path=closure,
    )
    rows = {row["field"]: row for row in payload["field_rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_LICENSE_STATUS_OWNER_INPUT_REQUIRED"
    assert payload["summary"]["closure_blocker_count"] == 2
    assert payload["summary"]["placeholder_values_absent_pass"] is True
    assert rows["status"]["current_value"] == "not_configured"
    assert rows["license_id"]["template_value"] == "LICENSE-ID"
    assert rows["approval_ref"]["accepted_keys"] == [
        "approval_ref",
        "approval_ticket",
        "legal_ticket",
        "decision_ref",
    ]
    assert any("build_license_status_closure_report.py" in command for command in payload["validation_commands"])


def test_license_status_intake_packet_passes_through_closed_report(tmp_path: Path) -> None:
    license_status = _write_json(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-1",
            "issuer": "legal",
            "approval_ref": "LEGAL-1",
            "product_scope": ["review-assist"],
            "expires_at_utc": "2027-01-01T00:00:00+00:00",
        },
    )
    template = _write_json(tmp_path / "license_status.template.json", {})
    closure = _write_json(
        tmp_path / "license_status_closure_report.json",
        {
            "contract_pass": True,
            "blockers": [],
            "checks": {
                "status_active_pass": True,
                "tier_present_pass": True,
                "license_id_present_pass": True,
                "issuer_or_approver_present_pass": True,
                "approval_reference_present_pass": True,
                "product_scope_present_pass": True,
                "expiry_valid_pass": True,
                "placeholder_values_absent_pass": True,
            },
            "summary": {"owner_action": "No action required."},
        },
    )

    payload = build_license_status_intake_packet.build_packet(
        license_status_path=license_status,
        template_path=template,
        closure_report_path=closure,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["field_pass_count"] == 7
    assert payload["current_blockers"] == []


def test_license_status_intake_packet_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    license_status = _write_json(tmp_path / "license_status.json", {"status": "not_configured"})
    template = _write_json(tmp_path / "license_status.template.json", {"license_id": "LICENSE-ID"})
    closure = _write_json(
        tmp_path / "license_status_closure_report.json",
        {"contract_pass": False, "blockers": ["license_status_not_active"], "checks": {}, "summary": {}},
    )
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = build_license_status_intake_packet.main(
        [
            "--license-status",
            str(license_status),
            "--template",
            str(template),
            "--closure-report",
            str(closure),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "License Status Intake Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["closure_blocker_count"] == 1
    assert "Validation Commands" in out_md.read_text(encoding="utf-8")
