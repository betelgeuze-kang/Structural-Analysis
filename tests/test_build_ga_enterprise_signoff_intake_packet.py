from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


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
            "artifacts": {
                "measured_benchmark_breadth": str(path.parent / "measured_benchmark_breadth_report.json"),
                "release_registry": str(path.parent / "release_registry.json"),
                "support_bundle": str(path.parent / "support_bundle_manifest.json"),
                "validation_manual": str(path.parent / "release-validation-manual.md"),
            },
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
    assert payload["summary"]["owner_packet_count"] == 3
    assert payload["summary"]["incomplete_owner_packet_count"] == 3
    assert payload["summary"]["template_count"] == 3
    assert payload["source_artifacts"]["ga_enterprise_readiness_report"].endswith("ga_readiness.json")
    assert payload["source_artifacts"]["release_registry"].endswith("release_registry.json")
    assert "independent_vv_missing" in payload["current_blockers"]
    assert rows["independent_vv_attestation"]["owner"] == "independent_vv_owner"
    assert rows["independent_vv_attestation"]["external_input_required"] is True
    assert rows["independent_vv_attestation"]["resolution_type"] == "external_independent_vv_attestation_required"
    assert rows["independent_vv_attestation"]["evidence_status"]["state"] == "missing_external_signoff_evidence"
    assert rows["independent_vv_attestation"]["template_path"].endswith(
        "docs/templates/independent_vv_attestation.template.json"
    )
    assert rows["independent_vv_attestation"]["template_present"] is True
    assert rows["independent_vv_attestation"]["source_artifacts"]["support_bundle"].endswith(
        "support_bundle_manifest.json"
    )
    assert "independence_basis" in rows["independent_vv_attestation"]["required_fields"]
    assert "attestation_scope" in rows["independent_vv_attestation"]["missing_fields"]
    assert rows["family_validation_manual_signoff"]["owner"] == "validation_manual_owner"
    assert rows["family_validation_manual_signoff"]["evidence_status"]["state"] == "missing_external_signoff_evidence"
    assert rows["customer_audit_failure_bundle_sla"]["owner"] == "customer_success_ops_owner"
    assert "support_sla_ref" in rows["customer_audit_failure_bundle_sla"]["required_fields"]
    assert any("build_ga_enterprise_signoff_intake_packet.py" in command for command in rows["independent_vv_attestation"]["verification_commands"])
    assert any("build_ga_enterprise_readiness_report.py" in command for command in payload["validation_commands"])
    owner_packets = {packet["owner"]: packet for packet in payload["owner_packets"]}
    assert owner_packets["independent_vv_owner"]["request_state"] == "owner_input_required"
    assert owner_packets["independent_vv_owner"]["signoffs"] == ["independent_vv_attestation"]
    assert owner_packets["independent_vv_owner"]["source_artifacts"]["validation_manual"].endswith(
        "release-validation-manual.md"
    )
    assert owner_packets["independent_vv_owner"]["template_paths"] == [
        "docs/templates/independent_vv_attestation.template.json"
    ]
    assert owner_packets["customer_success_ops_owner"]["acceptance_criteria"] == [
        "`customer_audit_failure_bundle_sla.contract_pass == true`"
    ]


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
    assert packet["summary"]["incomplete_owner_packet_count"] == 0
    assert all(row["evidence_status"]["state"] == "ready_for_ga_readiness_regeneration" for row in packet["signoff_rows"])
    assert all(packet["request_state"] == "ready_for_ga_readiness_regeneration" for packet in packet["owner_packets"])


def test_ga_signoff_intake_rejects_placeholder_and_incomplete_external_evidence(tmp_path: Path) -> None:
    readiness = _readiness(tmp_path / "ga_readiness.json")
    readiness_payload = json.loads(readiness.read_text(encoding="utf-8"))
    for row in readiness_payload["owner_handoff_rows"]:
        signoff = Path(row["evidence_path"]).stem
        payload = _complete_payload(signoff)
        if signoff == "independent_vv_attestation":
            payload["independence_basis"] = "TODO owner input required"
        elif signoff == "family_validation_manual_signoff":
            payload.pop("family_rows")
        else:
            payload["approval_decision"] = "pending"
        _write_json(Path(row["evidence_path"]), payload)

    packet = build_ga_enterprise_signoff_intake_packet.build_packet(ga_readiness_report=readiness)
    rows = {row["signoff"]: row for row in packet["signoff_rows"]}

    assert packet["contract_pass"] is False
    assert rows["independent_vv_attestation"]["evidence_status"]["state"] == "placeholder_external_signoff_evidence"
    assert rows["independent_vv_attestation"]["placeholder_fields"] == ["independence_basis"]
    assert rows["family_validation_manual_signoff"]["evidence_status"]["state"] == "incomplete_external_signoff_evidence"
    assert rows["family_validation_manual_signoff"]["missing_fields"] == ["family_rows"]
    assert rows["customer_audit_failure_bundle_sla"]["evidence_status"]["state"] == "incomplete_external_signoff_evidence"
    assert rows["customer_audit_failure_bundle_sla"]["approval_decision_pass"] is False
    assert packet["summary"]["open_signoff_count"] == 3


def test_ga_signoff_templates_do_not_pass_when_copied_to_evidence_paths(tmp_path: Path) -> None:
    readiness = _readiness(tmp_path / "ga_readiness.json")
    readiness_payload = json.loads(readiness.read_text(encoding="utf-8"))
    template_by_signoff = {
        str(spec["signoff"]): Path(str(spec["default_template_path"]))
        for spec in build_ga_enterprise_signoff_intake_packet.SIGNOFF_SPECS.values()
    }
    for row in readiness_payload["owner_handoff_rows"]:
        signoff = Path(row["evidence_path"]).stem
        template_payload = json.loads(template_by_signoff[signoff].read_text(encoding="utf-8"))
        _write_json(Path(row["evidence_path"]), template_payload)

    packet = build_ga_enterprise_signoff_intake_packet.build_packet(ga_readiness_report=readiness)

    assert packet["contract_pass"] is False
    assert packet["summary"]["open_signoff_count"] == 3
    assert all(row["evidence_contract_pass"] is False for row in packet["signoff_rows"])
    assert all(row["evidence_status"]["state"] == "template_only_external_signoff_evidence" for row in packet["signoff_rows"])
    assert all(row["template_only"] is True for row in packet["signoff_rows"])
    assert all(row["evidence_status"]["template_only"] is True for row in packet["signoff_rows"])
    assert all("approval_decision" in row["placeholder_fields"] for row in packet["signoff_rows"])


def test_ga_signoff_intake_keeps_required_rows_when_readiness_handoff_rows_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patched_specs = {
        blocker: {
            **spec,
            "default_evidence_path": tmp_path / f"{spec['signoff']}.json",
        }
        for blocker, spec in build_ga_enterprise_signoff_intake_packet.SIGNOFF_SPECS.items()
    }
    monkeypatch.setattr(build_ga_enterprise_signoff_intake_packet, "SIGNOFF_SPECS", patched_specs)
    readiness = _write_json(
        tmp_path / "ga_readiness.json",
        {"contract_pass": True, "blockers": [], "owner_handoff_rows": [], "artifacts": {}},
    )

    packet = build_ga_enterprise_signoff_intake_packet.build_packet(ga_readiness_report=readiness)

    assert packet["contract_pass"] is False
    assert packet["summary"]["signoff_count"] == 3
    assert packet["summary"]["open_signoff_count"] == 3
    assert set(packet["current_blockers"]) == set(patched_specs)
    assert "readiness_pass=True" in packet["summary_line"]


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
    assert "Owner Packets" in markdown
    assert ".template.json" in markdown
    assert "Validation Commands" in markdown
    assert "independent_vv_owner" in markdown


def test_ga_signoff_intake_cli_fail_blocked_returns_nonzero(tmp_path: Path, capsys) -> None:
    exit_code = build_ga_enterprise_signoff_intake_packet.main(
        [
            "--ga-readiness-report",
            str(_readiness(tmp_path / "ga_readiness.json")),
            "--out",
            str(tmp_path / "packet.json"),
            "--out-md",
            str(tmp_path / "packet.md"),
            "--fail-blocked",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "GA Enterprise Signoff Intake Packet" in captured.out
