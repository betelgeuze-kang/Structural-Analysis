from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_support_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_support_bundle", SCRIPT_PATH)
assert SPEC is not None
build_support_bundle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_support_bundle)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _support_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "p0_status": _write_json(tmp_path / "p0.json", {"contract_pass": True}),
        "p1_status": _write_json(tmp_path / "p1.json", {"p1_inputs_ready": True}),
        "p1_strict_evidence_preflight": _write_json(
            tmp_path / "preflight.json",
            {
                "contract_pass": False,
                "blockers": ["external_receipt_or_closure_pending:hardest_external_10case"],
                "Authorization": "Bearer should-be-redacted",
            },
        ),
        "project_ops_snapshot": _write_json(tmp_path / "project-ops.json", {"summary": {"project_count": 1}}),
        "project_ops_deployment_drill": _write_json(
            tmp_path / "project-ops-drill.json",
            {"contract_pass": True, "drill_mode": "dry_run_contract"},
        ),
        "runtime_probe": _write_json(tmp_path / "runtime-probe.json", {"strict_rust_hip_pass": True}),
        "runtime_packaging_manifest": _write_json(tmp_path / "runtime-manifest.json", {"contract_pass": False}),
        "viewer_performance_budget_manifest": _write_json(
            tmp_path / "viewer-performance-budget.json",
            {"contract_pass": True, "budget_mode": "static_contract", "live_performance_claim": False},
        ),
        "viewer_browser_performance_probe": _write_json(
            tmp_path / "viewer-browser-performance.json",
            {"contract_pass": True, "probe_mode": "local_browser_probe", "live_performance_claim": False},
        ),
        "viewer_visual_regression_baseline": _write_json(
            tmp_path / "viewer-visual-regression.json",
            {"contract_pass": True, "visual_regression_mode": "local_canvas_signature_baseline"},
        ),
        "workstation_hardware_profile": _write_json(
            tmp_path / "workstation-hardware.json",
            {"contract_pass": True, "schema_version": "workstation-hardware-profile.v1"},
        ),
        "workstation_service_budget": _write_json(
            tmp_path / "workstation-budget.json",
            {"contract_pass": True, "schema_version": "workstation-service-budget.v1"},
        ),
        "workstation_delivery_package_manifest": _write_json(
            tmp_path / "workstation-package.json",
            {"contract_pass": True, "schema_version": "workstation-delivery-package-manifest.v1"},
        ),
        "workstation_delivery_readiness": _write_json(
            tmp_path / "workstation-readiness.json",
            {"contract_pass": True, "schema_version": "workstation-delivery-readiness.v1"},
        ),
        "workstation_delivery_viewer_smoke": _write_json(
            tmp_path / "workstation-delivery-viewer-smoke.json",
            {"contract_pass": True, "schema_version": "workstation-delivery-viewer-smoke.v1"},
        ),
        "client_input_validation_report": _write_json(
            tmp_path / "client-validation.json",
            {"status": "ready", "schema_version": "client-input-validation-report.v1"},
        ),
        "workstation_job_record": _write_json(
            tmp_path / "workstation-job.json",
            {"schema_version": "workstation-job-record.v1", "job_id": "J1"},
        ),
        "workstation_job_retention_policy": _write_json(
            tmp_path / "workstation-retention.json",
            {"schema_version": "workstation-job-retention-policy.v1", "contract_pass": True},
        ),
        "external_benchmark_updates": _write_json(tmp_path / "eb.json", {"receipt_status": "pending"}),
        "residual_holdout_updates": _write_json(tmp_path / "rh.json", {"status": "open"}),
        "pm_release_blocker_action_register": _write_json(
            tmp_path / "pm-release-blocker-action-register.json",
            {
                "schema_version": "pm-release-blocker-action-register.v1",
                "contract_pass": False,
                "summary": {"open_blocker_count": 2},
                "rows": [{"blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"}],
            },
        ),
        "pm_release_blocker_closure_board": _write_json(
            tmp_path / "pm-release-blocker-closure-board.json",
            {
                "schema_version": "pm-release-blocker-closure-board.v1",
                "contract_pass": False,
                "summary": {
                    "open_blocker_count": 2,
                    "handoff_not_ready_count": 0,
                    "all_open_blockers_have_handoff": True,
                },
                "rows": [
                    {
                        "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                        "closure_state": "external_owner_input_ready",
                    }
                ],
            },
        ),
        "pm_release_gate_completion_audit": _write_json(
            tmp_path / "pm-release-gate-completion-audit.json",
            {
                "schema_version": "pm-release-gate-completion-audit.v1",
                "contract_pass": False,
                "summary": {
                    "explicit_requirement_count": 45,
                    "blocked_requirement_count": 3,
                    "blocked_external_owner_input_ready_count": 3,
                },
                "rows": [
                    {
                        "requirement_id": "release_area.basic_ci",
                        "status": "blocked_external_owner_input_ready",
                    }
                ],
            },
        ),
        "pm_release_gate_reviewer_handoff": _write_json(
            tmp_path / "pm-release-gate-reviewer-handoff.json",
            {
                "schema_version": "pm-release-gate-reviewer-handoff.v1",
                "contract_pass": True,
                "summary": {"open_blocker_count": 2, "handoff_incomplete_count": 0},
                "rows": [
                    {
                        "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                        "verdict_change_conditions": ["`release_area.basic_ci` status is `pass`"],
                    }
                ],
            },
        ),
        "pm_owner_evidence_request_packet": _write_json(
            tmp_path / "pm-owner-evidence-request-packet.json",
            {
                "schema_version": "pm-owner-evidence-request-packet.v1",
                "contract_pass": True,
                "summary": {"owner_packet_count": 1, "open_blocker_count": 2},
                "owner_packets": [
                    {
                        "owner": "release_ci_owner",
                        "blocker_ids": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
                    }
                ],
            },
        ),
        "ci_streak_intake_packet": _write_json(
            tmp_path / "ci-streak-intake-packet.json",
            {
                "schema_version": "ci-streak-intake-packet.v1",
                "contract_pass": False,
                "current_blockers": ["pr:pr_ci_30_consecutive_pass_evidence_missing"],
            },
        ),
        "ci_streak_manifest": _write_json(
            tmp_path / "ci-streak-manifest.json",
            {
                "schema_version": "ci-consecutive-pass-manifest.v1",
                "contract_pass": False,
                "lanes": {
                    "pr": {"threshold_pass": False},
                    "nightly": {"threshold_pass": False},
                },
            },
        ),
        "github_actions_ci_streak_evidence": _write_json(
            tmp_path / "github-actions-ci-streak-evidence.json",
            {
                "schema_version": "github-actions-ci-streak-evidence.v1",
                "lanes": {
                    "pr": {"consecutive_pass_count": 0},
                    "nightly": {"consecutive_pass_count": 0},
                },
            },
        ),
        "license_status_intake_packet": _write_json(
            tmp_path / "license-status-intake-packet.json",
            {
                "schema_version": "license-status-intake-packet.v1",
                "contract_pass": False,
                "current_blockers": ["license_status_not_active"],
            },
        ),
        "license_status_closure_report": _write_json(
            tmp_path / "license-status-closure-report.json",
            {
                "schema_version": "license-status-closure-report.v1",
                "contract_pass": False,
                "blockers": ["license_status_not_active"],
            },
        ),
        "license_status_template": _write_json(
            tmp_path / "license-status-template.json",
            {
                "status": "active",
                "license_id": "LICENSE-ID",
                "template_only": True,
            },
        ),
        "frontend_dependency_audit_report": _write_json(
            tmp_path / "frontend-dependency-audit-report.json",
            {
                "schema_version": "frontend-dependency-audit-report.v1",
                "contract_pass": True,
                "summary": {"vulnerability_total": 0, "high_or_critical_vulnerability_count": 0},
            },
        ),
        "ga_enterprise_readiness_report": _write_json(
            tmp_path / "ga-enterprise-readiness-report.json",
            {
                "schema_version": "ga-enterprise-readiness-report.v1",
                "contract_pass": False,
                "blockers": [
                    "independent_vv_missing",
                    "family_validation_manual_signoff_missing",
                    "customer_audit_failure_bundle_sla_missing",
                ],
            },
        ),
        "ga_enterprise_signoff_intake_packet": _write_json(
            tmp_path / "ga-enterprise-signoff-intake-packet.json",
            {
                "schema_version": "ga-enterprise-signoff-intake-packet.v1",
                "contract_pass": False,
                "current_blockers": ["independent_vv_missing"],
            },
        ),
        "independent_vv_attestation_template": _write_json(
            tmp_path / "independent-vv-attestation-template.json",
            {
                "contract_pass": False,
                "template_only": True,
                "independent_reviewer": "OWNER_INPUT_REQUIRED",
            },
        ),
        "family_validation_manual_signoff_template": _write_json(
            tmp_path / "family-validation-manual-signoff-template.json",
            {
                "contract_pass": False,
                "template_only": True,
                "family_rows": [{"family": "OWNER_INPUT_REQUIRED"}],
            },
        ),
        "customer_audit_failure_bundle_sla_template": _write_json(
            tmp_path / "customer-audit-failure-bundle-sla-template.json",
            {
                "contract_pass": False,
                "template_only": True,
                "support_sla_ref": "OWNER_INPUT_REQUIRED",
            },
        ),
        "paid_pilot_scope_guard_report": _write_json(
            tmp_path / "paid-pilot-scope-guard-report.json",
            {
                "schema_version": "paid-pilot-scope-guard-report.v1",
                "contract_pass": True,
                "summary_line": "Paid pilot scope guard: PASS",
            },
        ),
        "release_validation_manual": _write_text(
            tmp_path / "release-validation-manual.md",
            "PM release gate validation family p95 error residual benchmark breadth interop reproduction commands\n",
        ),
        "release_limitation_manual": _write_text(
            tmp_path / "release-limitation-manual.md",
            "claim boundary paid pilot limited commercial ga/enterprise known issues support bundle rollback\n",
        ),
        "ux_new_user_observation_report": _write_json(
            tmp_path / "ux-new-user-observation-report.json",
            {
                "schema_version": "ux-new-user-observation-report.v1",
                "contract_pass": False,
                "blockers": ["observation_file_missing"],
            },
        ),
        "ux_new_user_observation_intake_packet": _write_json(
            tmp_path / "ux-new-user-observation-intake-packet.json",
            {
                "schema_version": "ux-new-user-observation-intake-packet.v1",
                "contract_pass": False,
                "current_blockers": ["observation_file_missing"],
            },
        ),
        "ux_new_user_observation_template": _write_json(
            tmp_path / "ux-new-user-observation-template.json",
            {
                "contract_pass": False,
                "template_only": True,
                "sample_project_id": "OWNER_INPUT_REQUIRED",
            },
        ),
        "package_json": _write_json(tmp_path / "package.json", {"name": "support-bundle-test"}),
        "pyproject": _write_text(tmp_path / "pyproject.toml", "[project]\nname='support-bundle-test'\n"),
    }


def test_support_bundle_builds_redacted_digest_and_roundtrip(tmp_path: Path) -> None:
    inputs = _support_inputs(tmp_path)
    audit_log = _write_text(
        tmp_path / "audit.jsonl",
        '{"tenant_id":"tenant-a","Authorization":"Bearer audit-token","status":200}\n',
    )

    payload = build_support_bundle.build_support_bundle(
        bundle_dir=tmp_path / "bundle",
        audit_log_path=audit_log,
        **inputs,
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["redaction_self_test_pass"] is True
    assert payload["checks"]["audit_event_digest_pass"] is True
    assert payload["checks"]["bundle_roundtrip_test_pass"] is True
    assert payload["checks"]["archive_roundtrip_test_pass"] is True
    assert payload["audit_digest"]["event_count"] == 1
    assert payload["blockers"] == []

    index_path = Path(payload["bundle_index"]["path"])
    assert index_path.exists()
    archive_path = Path(payload["export_archive"]["path"])
    assert archive_path.exists()
    assert payload["export_archive"]["member_count"] >= payload["bundle_index"]["artifact_count"]
    assert payload["archive_roundtrip"]["pass"] is True
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        assert "support_bundle_index.json" in members
        assert "audit_digest.json" in members
        assert "license_status.json" in members
        assert "redacted/ci_streak_manifest.json" in members
        assert "redacted/github_actions_ci_streak_evidence.json" in members
        assert "redacted/pm_release_blocker_closure_board.json" in members
        assert "redacted/pm_release_gate_completion_audit.json" in members
        assert "redacted/pm_release_gate_reviewer_handoff.json" in members
        assert "redacted/pm_owner_evidence_request_packet.json" in members
        assert "redacted/license_status_closure_report.json" in members
        assert "redacted/license_status_template.json" in members
        assert "redacted/independent_vv_attestation_template.json" in members
        assert "redacted/family_validation_manual_signoff_template.json" in members
        assert "redacted/customer_audit_failure_bundle_sla_template.json" in members
        assert "redacted/ux_new_user_observation_template.json" in members
        assert "license_status.template.json" not in members
    assert "project_ops_deployment_drill" in payload["required_sections"]
    assert "viewer_performance_budget_manifest" in payload["required_sections"]
    assert "viewer_browser_performance_probe" in payload["required_sections"]
    assert "viewer_visual_regression_baseline" in payload["required_sections"]
    assert "workstation_hardware_profile" in payload["required_sections"]
    assert "workstation_service_budget" in payload["required_sections"]
    assert "workstation_delivery_package_manifest" in payload["required_sections"]
    assert "workstation_delivery_readiness" in payload["required_sections"]
    assert "workstation_delivery_viewer_smoke" in payload["required_sections"]
    assert "client_input_validation_report" in payload["required_sections"]
    assert "workstation_job_record" in payload["required_sections"]
    assert "workstation_job_retention_policy" in payload["required_sections"]
    assert "pm_release_blocker_action_register" in payload["optional_sections"]
    assert "pm_release_blocker_closure_board" in payload["optional_sections"]
    assert "pm_release_gate_completion_audit" in payload["optional_sections"]
    assert "pm_release_gate_reviewer_handoff" in payload["optional_sections"]
    assert "pm_owner_evidence_request_packet" in payload["optional_sections"]
    assert "ci_streak_intake_packet" in payload["optional_sections"]
    assert "ci_streak_manifest" in payload["optional_sections"]
    assert "github_actions_ci_streak_evidence" in payload["optional_sections"]
    assert "license_status_intake_packet" in payload["optional_sections"]
    assert "license_status_closure_report" in payload["optional_sections"]
    assert "license_status_template" in payload["optional_sections"]
    assert "frontend_dependency_audit_report" in payload["optional_sections"]
    assert "ga_enterprise_readiness_report" in payload["optional_sections"]
    assert "ga_enterprise_signoff_intake_packet" in payload["optional_sections"]
    assert "independent_vv_attestation_template" in payload["optional_sections"]
    assert "family_validation_manual_signoff_template" in payload["optional_sections"]
    assert "customer_audit_failure_bundle_sla_template" in payload["optional_sections"]
    assert "paid_pilot_scope_guard_report" in payload["optional_sections"]
    assert "release_validation_manual" in payload["optional_sections"]
    assert "release_limitation_manual" in payload["optional_sections"]
    assert "ux_new_user_observation_report" in payload["optional_sections"]
    assert "ux_new_user_observation_intake_packet" in payload["optional_sections"]
    assert "ux_new_user_observation_template" in payload["optional_sections"]
    redacted_pm_blockers = Path(payload["optional_sections"]["pm_release_blocker_action_register"]).read_text(
        encoding="utf-8"
    )
    assert "basic_ci::pr_ci_30_consecutive_pass_evidence_missing" in redacted_pm_blockers
    redacted_closure_board = Path(payload["optional_sections"]["pm_release_blocker_closure_board"]).read_text(
        encoding="utf-8"
    )
    assert "pm-release-blocker-closure-board.v1" in redacted_closure_board
    assert "external_owner_input_ready" in redacted_closure_board
    redacted_completion_audit = Path(payload["optional_sections"]["pm_release_gate_completion_audit"]).read_text(
        encoding="utf-8"
    )
    assert "pm-release-gate-completion-audit.v1" in redacted_completion_audit
    assert "release_area.basic_ci" in redacted_completion_audit
    redacted_reviewer_handoff = Path(payload["optional_sections"]["pm_release_gate_reviewer_handoff"]).read_text(
        encoding="utf-8"
    )
    assert "pm-release-gate-reviewer-handoff.v1" in redacted_reviewer_handoff
    assert "verdict_change_conditions" in redacted_reviewer_handoff
    redacted_owner_packet = Path(payload["optional_sections"]["pm_owner_evidence_request_packet"]).read_text(
        encoding="utf-8"
    )
    assert "pm-owner-evidence-request-packet.v1" in redacted_owner_packet
    assert "release_ci_owner" in redacted_owner_packet
    redacted_ci_streak = Path(payload["optional_sections"]["ci_streak_intake_packet"]).read_text(
        encoding="utf-8"
    )
    assert "pr:pr_ci_30_consecutive_pass_evidence_missing" in redacted_ci_streak
    redacted_ci_manifest = Path(payload["optional_sections"]["ci_streak_manifest"]).read_text(encoding="utf-8")
    assert "ci-consecutive-pass-manifest.v1" in redacted_ci_manifest
    redacted_github_actions = Path(payload["optional_sections"]["github_actions_ci_streak_evidence"]).read_text(
        encoding="utf-8"
    )
    assert "github-actions-ci-streak-evidence.v1" in redacted_github_actions
    redacted_license_intake = Path(payload["optional_sections"]["license_status_intake_packet"]).read_text(
        encoding="utf-8"
    )
    assert "license_status_not_active" in redacted_license_intake
    redacted_license_closure = Path(payload["optional_sections"]["license_status_closure_report"]).read_text(
        encoding="utf-8"
    )
    assert "license_status_not_active" in redacted_license_closure
    redacted_license_template = Path(payload["optional_sections"]["license_status_template"]).read_text(
        encoding="utf-8"
    )
    assert "LICENSE-ID" in redacted_license_template
    redacted_frontend_audit = Path(payload["optional_sections"]["frontend_dependency_audit_report"]).read_text(
        encoding="utf-8"
    )
    assert '"vulnerability_total": 0' in redacted_frontend_audit
    redacted_ga_readiness = Path(payload["optional_sections"]["ga_enterprise_readiness_report"]).read_text(
        encoding="utf-8"
    )
    assert "independent_vv_missing" in redacted_ga_readiness
    redacted_ga_signoff = Path(payload["optional_sections"]["ga_enterprise_signoff_intake_packet"]).read_text(
        encoding="utf-8"
    )
    assert "independent_vv_missing" in redacted_ga_signoff
    redacted_independent_vv_template = Path(
        payload["optional_sections"]["independent_vv_attestation_template"]
    ).read_text(encoding="utf-8")
    assert "OWNER_INPUT_REQUIRED" in redacted_independent_vv_template
    redacted_family_signoff_template = Path(
        payload["optional_sections"]["family_validation_manual_signoff_template"]
    ).read_text(encoding="utf-8")
    assert "template_only" in redacted_family_signoff_template
    redacted_customer_sla_template = Path(
        payload["optional_sections"]["customer_audit_failure_bundle_sla_template"]
    ).read_text(encoding="utf-8")
    assert "support_sla_ref" in redacted_customer_sla_template
    redacted_scope_guard = Path(payload["optional_sections"]["paid_pilot_scope_guard_report"]).read_text(
        encoding="utf-8"
    )
    assert "Paid pilot scope guard: PASS" in redacted_scope_guard
    redacted_validation_manual = Path(payload["optional_sections"]["release_validation_manual"]).read_text(
        encoding="utf-8"
    )
    assert "PM release gate" in redacted_validation_manual
    redacted_limitation_manual = Path(payload["optional_sections"]["release_limitation_manual"]).read_text(
        encoding="utf-8"
    )
    assert "claim boundary" in redacted_limitation_manual
    redacted_ux_observation = Path(payload["optional_sections"]["ux_new_user_observation_report"]).read_text(
        encoding="utf-8"
    )
    assert "observation_file_missing" in redacted_ux_observation
    redacted_ux_intake = Path(payload["optional_sections"]["ux_new_user_observation_intake_packet"]).read_text(
        encoding="utf-8"
    )
    assert "ux-new-user-observation-intake-packet.v1" in redacted_ux_intake
    redacted_ux_template = Path(payload["optional_sections"]["ux_new_user_observation_template"]).read_text(
        encoding="utf-8"
    )
    assert "OWNER_INPUT_REQUIRED" in redacted_ux_template
    redacted_preflight = Path(payload["required_sections"]["p1_strict_evidence_preflight"]).read_text(
        encoding="utf-8"
    )
    assert "should-be-redacted" not in redacted_preflight
    assert build_support_bundle.REDACTED in redacted_preflight


def test_support_bundle_blocks_when_required_artifact_missing(tmp_path: Path) -> None:
    inputs = _support_inputs(tmp_path)
    inputs["runtime_probe"] = tmp_path / "missing-runtime-probe.json"

    payload = build_support_bundle.build_support_bundle(
        bundle_dir=tmp_path / "bundle",
        **inputs,
    )

    assert payload["contract_pass"] is False
    assert "required_artifact_missing:runtime_probe" in payload["blockers"]
