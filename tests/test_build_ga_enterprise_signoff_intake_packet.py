from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ga_enterprise_signoff_intake_packet.py"
SPEC = importlib.util.spec_from_file_location("build_ga_enterprise_signoff_intake_packet", SCRIPT_PATH)
assert SPEC is not None
build_ga_enterprise_signoff_intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ga_enterprise_signoff_intake_packet)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _readiness(path: Path) -> Path:
    return _write_json(
        path,
        {
            "contract_pass": False,
            "blockers": [
                "independent_vv_missing",
                "family_validation_manual_signoff_missing",
                "customer_audit_failure_bundle_sla_missing",
            ],
            "owner_handoff_rows": [
                {
                    "blocker": "independent_vv_missing",
                    "evidence_path": str(path.parent / "independent_vv_attestation.json"),
                    "owner_action": "Attach independent V&V.",
                    "acceptance": "`independent_vv_attestation.contract_pass == true`",
                },
                {
                    "blocker": "family_validation_manual_signoff_missing",
                    "evidence_path": str(path.parent / "family_validation_manual_signoff.json"),
                    "owner_action": "Attach family signoff.",
                    "acceptance": "`family_validation_manual_signoff.contract_pass == true`",
                },
                {
                    "blocker": "customer_audit_failure_bundle_sla_missing",
                    "evidence_path": str(path.parent / "customer_audit_failure_bundle_sla.json"),
                    "owner_action": "Attach customer SLA.",
                    "acceptance": "`customer_audit_failure_bundle_sla.contract_pass == true`",
                },
            ],
        },
    )


def _complete_payload(signoff: str) -> dict[str, object]:
    if signoff == "independent_vv_attestation":
        return {
            "contract_pass": True,
            "attestation_scope": "GA release V&V",
            "independent_reviewer": "third-party reviewer",
            "independence_basis": "separate reporting chain",
            "case_set_reference": "measured-breadth-304",
            "report_reference": "vv-report-001",
            "signed_at_utc": "2026-06-16T00:00:00+00:00",
            "approval_decision": "approved",
        }
    if signoff == "family_validation_manual_signoff":
        return {
            "contract_pass": True,
            "release_registry_ref": "release-registry-ed25519",
            "validation_manual_ref": "validation-manual",
            "family_rows": [{"family": "steel_frame", "decision": "approved"}],
            "signoff_owner": "validation-owner",
            "signed_at_utc": "2026-06-16T00:00:00+00:00",
            "approval_decision": "approved",
        }
    return {
        "contract_pass": True,
        "customer_or_ops_approver": "ops-owner",
        "audit_export_acceptance_ref": "audit-export-001",
        "failure_bundle_export_ref": "failure-bundle-001",
        "support_sla_ref": "sla-001",
        "rollback_policy_ref": "rollback-001",
        "signed_at_utc": "2026-06-16T00:00:00+00:00",
        "approval_decision": "approved",
    }


def test_ga_signoff_intake_surfaces_required_owner_fields(tmp_path: Path) -> None:
    payload = build_ga_enterprise_signoff_intake_packet.build_packet(
        ga_readiness_report=_readiness(tmp_path / "ga_readiness.json")
    )
    rows = {row["signoff"]: row for row in payload["signoff_rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_GA_ENTERPRISE_SIGNOFF_OWNER_INPUT_REQUIRED"
    assert payload["summary"]["open_signoff_count"] == 3
    assert payload["summary"]["external_input_required_count"] == 3
    assert "independent_vv_missing" in payload["current_blockers"]
    assert rows["independent_vv_attestation"]["owner"] == "independent_vv_owner"
    assert rows["independent_vv_attestation"]["external_input_required"] is True
    assert rows["independent_vv_attestation"]["resolution_type"] == "external_independent_vv_attestation_required"
    assert rows["independent_vv_attestation"]["evidence_status"]["state"] == "missing_external_signoff_evidence"
    assert "independence_basis" in rows["independent_vv_attestation"]["required_fields"]
    assert "attestation_scope" in rows["independent_vv_attestation"]["missing_fields"]
    assert rows["family_validation_manual_signoff"]["owner"] == "validation_manual_owner"
    assert rows["family_validation_manual_signoff"]["evidence_status"]["state"] == "missing_external_signoff_evidence"
    assert rows["customer_audit_failure_bundle_sla"]["owner"] == "customer_success_ops_owner"
    assert "support_sla_ref" in rows["customer_audit_failure_bundle_sla"]["required_fields"]
    assert any("build_ga_enterprise_signoff_intake_packet.py" in command for command in rows["independent_vv_attestation"]["verification_commands"])
    assert any("build_ga_enterprise_readiness_report.py" in command for command in payload["validation_commands"])


def test_ga_signoff_intake_passes_when_readiness_and_evidence_pass(tmp_path: Path) -> None:
    readiness = _readiness(tmp_path / "ga_readiness.json")
    payload = json.loads(readiness.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    payload["blockers"] = []
    readiness.write_text(json.dumps(payload), encoding="utf-8")
    for row in payload["owner_handoff_rows"]:
        _write_json(Path(row["evidence_path"]), _complete_payload(Path(row["evidence_path"]).stem))

    packet = build_ga_enterprise_signoff_intake_packet.build_packet(ga_readiness_report=readiness)

    assert packet["contract_pass"] is True
    assert packet["reason_code"] == "PASS"
    assert packet["current_blockers"] == []
    assert packet["summary"]["external_input_required_count"] == 0
    assert all(row["evidence_status"]["state"] == "ready_for_ga_readiness_regeneration" for row in packet["signoff_rows"])


def test_ga_signoff_intake_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = build_ga_enterprise_signoff_intake_packet.main(
        [
            "--ga-readiness-report",
            str(_readiness(tmp_path / "ga_readiness.json")),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "GA Enterprise Signoff Intake Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_signoff_count"] == 3
    markdown = out_md.read_text(encoding="utf-8")
    assert "Validation Commands" in markdown
    assert "independent_vv_owner" in markdown
