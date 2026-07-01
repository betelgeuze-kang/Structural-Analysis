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
            "approver_role": "APPROVER-ROLE",
            "approval_ref": "LEGAL-OR-PRODUCT-APPROVAL-ID",
            "approved_at_utc": "APPROVED-AT-UTC",
            "evidence_ref": "EVIDENCE-REF",
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
                "tier_allowed_pass": False,
                "license_id_present_pass": False,
                "issuer_or_approver_present_pass": False,
                "approver_role_allowed_pass": False,
                "approval_reference_present_pass": False,
                "approved_at_not_future_pass": False,
                "evidence_ref_resolvable_pass": False,
                "evidence_ref_not_self_reference_pass": False,
                "evidence_ref_not_template_reference_pass": False,
                "evidence_ref_not_template_artifact_pass": False,
                "product_scope_boundary_pass": False,
                "expiry_valid_pass": False,
                "approval_timeline_pass": False,
                "approval_ref_distinct_pass": False,
                "provenance_complete_pass": False,
                "placeholder_values_absent_pass": True,
            },
            "summary": {
                "owner_action": "Populate license_status.json from an approved product/legal decision.",
                "license_id": "",
                "approval_ref": "",
                "approved_at_utc": "",
                "expires_at_utc": "",
                "approver_role": "",
                "evidence_ref": "",
                "evidence_ref_kind": "",
                "evidence_ref_resolved_path": "",
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
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_LICENSE_STATUS_OWNER_INPUT_REQUIRED"
    assert payload["summary_line"] == "License status intake: BLOCKED | fields=0/16 | blockers=2"
    assert payload["summary"]["closure_blocker_count"] == 2
    assert payload["summary"]["placeholder_values_absent_pass"] is True
    assert payload["gate_unblock_plan_count"] == 2
    assert payload["gate_unblock_plan"][0]["slot_id"] == "attach_license_status_record"
    assert "tier" in payload["gate_unblock_plan"][0]["failing_fields"]
    assert payload["next_actions"] == [
        "fill_license_status_record_from_template",
        "attach_product_or_legal_approval_evidence",
        "set_paid_pilot_or_limited_commercial_scope_boundary",
        "prove_future_expiry_or_perpetual_approval",
        "rerun_license_status_and_release_gates",
    ]
    assert rows["status"]["current_value"] == "not_configured"
    assert rows["license_id"]["template_value"] == "LICENSE-ID"
    assert rows["approver_role"]["template_value"] == "APPROVER-ROLE"
    assert rows["approved_at_utc"]["template_value"] == "APPROVED-AT-UTC"
    assert rows["evidence_ref"]["template_value"] == "EVIDENCE-REF"
    assert rows["approval_ref"]["accepted_keys"] == [
        "approval_ref",
        "approval_ticket",
        "legal_ticket",
        "decision_ref",
    ]
    assert rows["approval_timeline"]["closure_check"] == "approval_timeline_pass"
    assert rows["provenance_complete"]["closure_check_pass"] is False
    assert rows["evidence_ref_not_self_reference"]["closure_check"] == "evidence_ref_not_self_reference_pass"
    assert rows["evidence_ref_not_template_reference"]["closure_check"] == "evidence_ref_not_template_reference_pass"
    assert rows["evidence_ref_not_template_artifact"]["closure_check"] == "evidence_ref_not_template_artifact_pass"
    assert any("build_license_status_closure_report.py" in command for command in payload["validation_commands"])
    assert any("build_license_status_intake_packet.py" in command for command in payload["validation_commands"])


def test_license_status_intake_packet_passes_through_closed_report(tmp_path: Path) -> None:
    license_status = _write_json(
        tmp_path / "license_status.json",
        {
            "status": "active",
            "tier": "limited-commercial",
            "license_id": "LIC-1",
            "issuer": "legal",
            "approver_role": "legal_counsel",
            "approval_ref": "LEGAL-1",
            "approved_at_utc": "2026-06-01T00:00:00+00:00",
            "evidence_ref": "ticket:LEGAL-1",
            "product_scope": [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ],
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
                "tier_allowed_pass": True,
                "license_id_present_pass": True,
                "issuer_or_approver_present_pass": True,
                "approver_role_allowed_pass": True,
                "approval_reference_present_pass": True,
                "approved_at_not_future_pass": True,
                "evidence_ref_resolvable_pass": True,
                "evidence_ref_not_self_reference_pass": True,
                "evidence_ref_not_template_reference_pass": True,
                "evidence_ref_not_template_artifact_pass": True,
                "product_scope_boundary_pass": True,
                "expiry_valid_pass": True,
                "approval_timeline_pass": True,
                "approval_ref_distinct_pass": True,
                "provenance_complete_pass": True,
                "placeholder_values_absent_pass": True,
            },
            "summary": {
                "owner_action": "No action required.",
                "license_id": "LIC-1",
                "approval_ref": "LEGAL-1",
                "approved_at_utc": "2026-06-01T00:00:00+00:00",
                "expires_at_utc": "2027-01-01T00:00:00+00:00",
                "approver_role": "legal_counsel",
                "evidence_ref": "ticket:LEGAL-1",
                "evidence_ref_kind": "external_reference",
                "evidence_ref_resolved_path": "",
            },
        },
    )

    payload = build_license_status_intake_packet.build_packet(
        license_status_path=license_status,
        template_path=template,
        closure_report_path=closure,
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["field_pass_count"] == 16
    assert payload["summary"]["provenance_complete_pass"] is True
    assert payload["current_blockers"] == []
    assert payload["gate_unblock_plan"] == []
    assert payload["gate_unblock_plan_count"] == 0
    assert payload["next_actions"] == []


def test_license_status_intake_packet_reuses_closure_gate_unblock_plan(tmp_path: Path) -> None:
    license_status = _write_json(tmp_path / "license_status.json", {"status": "not_configured"})
    template = _write_json(tmp_path / "license_status.template.json", {})
    closure = _write_json(
        tmp_path / "license_status_closure_report.json",
        {
            "contract_pass": False,
            "blockers": ["license_status_not_active"],
            "checks": {},
            "summary": {},
            "gate_unblock_plan": [
                {
                    "slot_id": "custom_license_owner_slot",
                    "minimum_evidence": ["owner/license evidence"],
                }
            ],
        },
    )

    payload = build_license_status_intake_packet.build_packet(
        license_status_path=license_status,
        template_path=template,
        closure_report_path=closure,
    )

    assert payload["gate_unblock_plan"] == [
        {
            "slot_id": "custom_license_owner_slot",
            "minimum_evidence": ["owner/license evidence"],
        }
    ]
    assert payload["gate_unblock_plan_count"] == 1


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
    assert "Gate Unblock Plan" in out_md.read_text(encoding="utf-8")
