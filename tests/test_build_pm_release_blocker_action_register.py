from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_blocker_action_register.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_blocker_action_register", SCRIPT_PATH)
assert SPEC is not None
build_register_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_register_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pm_report(path: Path, *, blockers: list[str] | None = None) -> Path:
    if blockers is None:
        blockers = [
            "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
            "security::license_status_not_configured",
        ]
    return _write_json(
        path,
        {
            "schema_version": "pm-release-gate.v1",
            "summary_line": "PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_milestone_ready": True,
            "limited_commercial_release_ready": False,
            "limited_commercial_ready": False,
            "release_area_gate_ready": False,
            "full_release_gate_ready": False,
            "blockers": [],
            "release_area_blockers": blockers,
            "full_release_blockers": blockers,
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "basic_ci",
                    "title": "Basic CI",
                    "status": "blocked",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                    "claim_boundary": "CI claim boundary",
                    "summary": {
                        "required_consecutive_pass_count": 30,
                        "pr_pass_streak_count": 2,
                        "pr_missing_consecutive_pass_count": 28,
                        "pr_pull_request_run_source_present": False,
                        "pr_owner_action": "No pull_request-triggered CI runs have been observed.",
                        "pr_claim_boundary": "Tracked PR CI evidence is required.",
                    },
                    "artifacts": {
                        "ci_streak_intake_packet": "ci_streak_intake_packet.json",
                        "ci_streak_manifest": "ci_consecutive_pass_manifest.json",
                    },
                },
                {
                    "area": "security",
                    "title": "Security",
                    "status": "blocked",
                    "blockers": ["license_status_not_configured"],
                    "summary": {
                        "license_status": "not_configured",
                        "license_status_owner_action": "Populate license status from approved legal evidence.",
                        "license_status_template_path": "docs/templates/license_status.template.json",
                    },
                    "artifacts": {
                        "license_status_closure": "license_status_closure_report.json",
                    },
                },
            ],
        },
    )


def test_build_register_surfaces_owner_actions_and_acceptance(tmp_path: Path) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json")

    payload = build_register_module.build_register(pm_report=report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_RELEASE_BLOCKERS_OPEN"
    assert payload["summary"]["open_blocker_count"] == 2
    assert payload["summary"]["owner_input_required_count"] == 2
    assert payload["summary"]["external_input_required_count"] == 2
    assert payload["summary"]["handoff_ready_count"] == 2
    assert payload["summary"]["handoff_not_ready_count"] == 0
    assert payload["summary"]["external_owner_input_ready_count"] == 2
    assert payload["summary"]["local_remediation_ready_count"] == 0
    assert payload["summary"]["all_open_blockers_have_handoff"] is True
    assert payload["summary"]["limited_commercial_milestone_ready"] is True
    assert payload["summary"]["limited_commercial_release_ready"] is False
    assert payload["summary"]["limited_commercial_ready"] is False

    ci_row = rows["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"]
    assert ci_row["owner"] == "release_ci_owner"
    assert ci_row["next_action"] == ci_row["owner_action"]
    assert ci_row["external_input_required"] is True
    assert ci_row["resolution_type"] == "external_tracked_ci_evidence_required"
    assert ci_row["owner_action"] == "No pull_request-triggered CI runs have been observed."
    assert ci_row["claim_boundary"] == "Tracked PR CI evidence is required."
    assert any("build_ci_consecutive_pass_manifest.py" in command for command in ci_row["reproduction_commands"])
    assert any("build_ci_streak_intake_packet.py" in command for command in ci_row["reproduction_commands"])
    assert any("build_ci_streak_intake_packet.py" in command for command in ci_row["verification_commands"])
    assert any("pr_pass_streak_count >= 30" in item for item in ci_row["acceptance_criteria"])
    assert any("ci_streak_intake_packet.json.contract_pass" in item for item in ci_row["acceptance_criteria"])
    assert "ci_streak_intake_packet" in ci_row["evidence_artifacts"]
    assert ci_row["handoff_ready"] is True
    assert ci_row["handoff_state"] == "external_owner_input_ready"
    assert ci_row["handoff"]["expected_intake_artifact"] == "ci_streak_intake_packet"
    assert ci_row["handoff"]["checks"]["expected_intake_artifact_present"] is True
    assert ci_row["evidence_status"]["state"] == "no_pull_request_run_source"
    assert ci_row["evidence_status"]["lane"] == "pr"
    assert ci_row["evidence_status"]["missing_consecutive_pass_count"] == 28
    assert ci_row["evidence_status"]["pull_request_run_source_present"] is False
    assert ci_row["evidence_snapshot"]["pr_missing_consecutive_pass_count"] == 28

    security_row = rows["security::license_status_not_configured"]
    assert security_row["owner"] == "product_legal_owner"
    assert security_row["external_input_required"] is True
    assert security_row["resolution_type"] == "product_legal_decision_required"
    assert security_row["owner_action"] == "Populate license status from approved legal evidence."
    assert any("build_license_status_intake_packet.py" in command for command in security_row["reproduction_commands"])
    assert any("build_license_status_closure_report.py" in command for command in security_row["reproduction_commands"])
    assert any("build_license_status_closure_report.py" in command for command in security_row["verification_commands"])
    assert any("license_status_closure_report.json.contract_pass" in item for item in security_row["acceptance_criteria"])
    assert "license_status_intake_packet" in security_row["evidence_artifacts"]
    assert security_row["handoff_ready"] is True
    assert security_row["handoff_state"] == "external_owner_input_ready"
    assert security_row["handoff"]["expected_intake_artifact"] == "license_status_intake_packet"
    assert security_row["evidence_status"]["state"] == "not_configured"


def test_build_register_passes_when_pm_report_has_no_blockers(tmp_path: Path) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json", blockers=[])
    payload = build_register_module.build_register(pm_report=report)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["rows"] == []
    assert payload["next_actions"] == []


def test_build_register_surfaces_ga_enterprise_blockers(tmp_path: Path) -> None:
    fresh_status = _write_json(
        tmp_path / "fresh_full_validation_lane_status.json",
        {
            "rows": [
                {
                    "lane_id": "gpu_hip_solver",
                    "runner": "gpu_capable_rocm_hip_validation",
                    "fresh_validation_receipt": "implementation/phase1/release_evidence/full_validation/gpu_hip_solver.fresh_validation_receipt.json",
                    "fresh_validation_receipt_present": False,
                    "fresh_validation_receipt_fresh": False,
                    "fresh_validation_receipt_lane_matches": False,
                    "fresh_validation_receipt_runner_matches": False,
                    "fresh_validation_receipt_contract_pass": False,
                    "fresh_validation_receipt_blockers": ["fresh_validation_receipt_missing"],
                }
            ]
        },
    )
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | ga=BLOCKED",
            "full_release_blockers": [],
            "release_area_blockers": [],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [],
            "release_tiers": {
                "ga_enterprise_blockers": [
                    "independent_vv_missing",
                    "customer_shadow::completed_shadow_case_count_below_minimum",
                    "fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing",
                ],
                "fresh_full_validation_lane_status": str(fresh_status),
                "customer_shadow_evidence_status": "implementation/phase1/customer_shadow_evidence_status.json",
                "customer_shadow_summary": {
                    "completed_shadow_case_count": 0,
                    "min_completed_shadow_cases": 3,
                    "target_completed_shadow_cases": 5,
                    "evidence_file_count": 0,
                    "valid_evidence_file_count": 0,
                },
            },
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["summary"]["open_blocker_count"] == 3
    assert payload["summary"]["ga_enterprise_blocker_count"] == 3

    vv_row = rows["independent_vv_missing"]
    assert vv_row["scope"] == "ga_enterprise"
    assert vv_row["owner"] == "independent_vv_owner"
    assert vv_row["owner_input_required"] is True
    assert vv_row["handoff_state"] == "external_owner_input_ready"
    assert vv_row["resolution_type"] == "external_ga_enterprise_signoff_required"
    assert "ga_enterprise_signoff_intake_packet" in vv_row["evidence_artifacts"]
    assert vv_row["evidence_status"]["state"] == "missing_external_ga_enterprise_signoff_evidence"

    customer_shadow_row = rows["customer_shadow::completed_shadow_case_count_below_minimum"]
    assert customer_shadow_row["scope"] == "ga_enterprise"
    assert customer_shadow_row["owner"] == "customer_success_ops_owner"
    assert customer_shadow_row["owner_input_required"] is True
    assert customer_shadow_row["handoff_state"] == "external_owner_input_ready"
    assert customer_shadow_row["resolution_type"] == "external_customer_shadow_evidence_required"
    assert customer_shadow_row["evidence_status"]["state"] == "completed_shadow_case_count_below_minimum"
    assert customer_shadow_row["evidence_status"]["completed_shadow_case_count"] == 0
    assert customer_shadow_row["evidence_status"]["min_completed_shadow_cases"] == 3
    assert "customer_shadow_evidence_intake_packet" in customer_shadow_row["evidence_artifacts"]
    assert customer_shadow_row["handoff"]["expected_intake_artifact"] == "customer_shadow_evidence_intake_packet"
    assert any("check_customer_shadow_evidence_status.py" in command for command in customer_shadow_row["reproduction_commands"])
    assert any("completed_shadow_case_count >= 3" in item for item in customer_shadow_row["acceptance_criteria"])

    fresh_row = rows["fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing"]
    assert fresh_row["scope"] == "ga_enterprise"
    assert fresh_row["owner"] == "validation_lane_owner"
    assert fresh_row["owner_input_required"] is False
    assert fresh_row["handoff_state"] == "local_remediation_ready"
    assert fresh_row["resolution_type"] == "fresh_validation_receipt_required"
    assert fresh_row["evidence_status"]["state"] == "fresh_validation_receipt_missing"
    assert fresh_row["evidence_status"]["lane_id"] == "gpu_hip_solver"
    assert fresh_row["evidence_status"]["fresh_validation_receipt_lane_matches"] is False
    assert fresh_row["evidence_status"]["fresh_validation_receipt_runner_matches"] is False
    assert fresh_row["evidence_status"]["receipt_validator"] == "implementation/phase1/validate_fresh_validation_receipt.py"
    assert any("build_fresh_full_validation_lane_status.py" in command for command in fresh_row["reproduction_commands"])
    assert any("fresh_validation_receipt_lane_matches == true" in item for item in fresh_row["acceptance_criteria"])
    assert any("validate_fresh_validation_receipt.py" in item for item in fresh_row["acceptance_criteria"])


def test_build_register_prioritizes_ci_job_start_blocker_state(tmp_path: Path) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    basic_ci = payload["release_area_matrix"][0]
    basic_ci["summary"]["pr_streak_source"] = "github_actions_job_start_blocked"
    basic_ci["summary"]["pr_github_actions_job_start_blocker_count"] = 2
    basic_ci["summary"]["pr_owner_action"] = (
        "Resolve the pr GitHub Actions job-start blocker shown in "
        "github_actions_ci_streak_evidence.json."
    )
    report.write_text(json.dumps(payload), encoding="utf-8")

    register = build_register_module.build_register(pm_report=report)
    row = register["rows"][0]

    assert row["blocker_id"] == "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    assert row["evidence_status"]["state"] == "github_actions_job_start_blocked"
    assert row["evidence_status"]["streak_source"] == "github_actions_job_start_blocked"
    assert row["evidence_status"]["github_actions_job_start_blocker_count"] == 2
    assert row["owner_action"].startswith("Resolve the pr GitHub Actions job-start blocker")


def test_build_register_guides_frontend_dependency_audit_blocker(tmp_path: Path) -> None:
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": ["security::frontend_dependency_audit_missing_or_failed"],
            "release_area_blockers": ["security::frontend_dependency_audit_missing_or_failed"],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "security",
                    "title": "Security",
                    "status": "blocked",
                    "blockers": ["frontend_dependency_audit_missing_or_failed"],
                    "summary": {
                        "frontend_dependency_vulnerability_total": 1,
                        "frontend_dependency_high_or_critical_vulnerability_count": 1,
                    },
                    "artifacts": {
                        "frontend_dependency_audit": "frontend_dependency_audit_report.json",
                    },
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == "security::frontend_dependency_audit_missing_or_failed"
    assert row["owner"] == "frontend_security_owner"
    assert row["external_input_required"] is False
    assert row["resolution_type"] == "local_dependency_remediation_required"
    assert row["handoff_ready"] is True
    assert row["handoff_state"] == "local_remediation_ready"
    assert row["handoff"]["expected_intake_artifact"] == ""
    assert "npm audit --audit-level high" in row["reproduction_commands"]
    assert any("build_frontend_dependency_audit_report.py" in command for command in row["reproduction_commands"])
    assert any("build_frontend_dependency_audit_report.py" in command for command in row["verification_commands"])
    assert any("high_or_critical_vulnerability_count == 0" in item for item in row["acceptance_criteria"])
    assert "frontend_dependency_audit_report" in row["evidence_artifacts"]


def test_build_register_guides_release_evidence_freshness_blocker(tmp_path: Path) -> None:
    blocker_id = "evidence_freshness::p0_closure_status::source_commit_missing"
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": [blocker_id],
            "release_area_blockers": [blocker_id],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "evidence_freshness",
                    "title": "Evidence Freshness",
                    "status": "blocked",
                    "blockers": ["p0_closure_status::source_commit_missing"],
                    "checks": {
                        "source_commit_rows_match": False,
                        "engine_version_rows_present": False,
                        "input_checksum_rows_present": False,
                        "reuse_marker_rows_present": False,
                        "dependency_mtime_rows_pass": True,
                    },
                    "summary": {"artifact_count": 3, "pass_count": 0, "blocker_count": 15},
                    "artifacts": {
                        "release_evidence_freshness": "release_evidence_freshness_report.json",
                    },
                    "claim_boundary": "Freshness audit only; it does not rerun heavy validation.",
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == blocker_id
    assert row["owner"] == "release_owner"
    assert row["owner_input_required"] is False
    assert row["resolution_type"] == "release_evidence_metadata_required"
    assert "source commit" in row["owner_action"]
    assert any("report_release_evidence_freshness.py" in command for command in row["reproduction_commands"])
    assert any("report_release_evidence_freshness.py" in command for command in row["verification_commands"])
    assert any("release_evidence_freshness_report.json.contract_pass" in item for item in row["acceptance_criteria"])
    assert "release_evidence_freshness_report" in row["evidence_artifacts"]
    assert row["claim_boundary"] == "Freshness audit only; it does not rerun heavy validation."
    assert row["evidence_status"]["state"] == "release_evidence_metadata_missing"
    assert row["evidence_status"]["source_commit_rows_match"] is False
    assert row["evidence_status"]["dependency_mtime_rows_pass"] is True
    assert row["handoff_ready"] is True
    assert row["handoff_state"] == "local_remediation_ready"


def test_build_register_guides_github_sync_r4_blocker(tmp_path: Path) -> None:
    blocker_id = "github_sync::github_sync_preflight::remote_mutation_approval_required"
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": [blocker_id],
            "release_area_blockers": [blocker_id],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "github_sync",
                    "title": "GitHub Development Sync",
                    "status": "blocked",
                    "blockers": ["github_sync_preflight::remote_mutation_approval_required"],
                    "checks": {
                        "github_sync_feature_fast_forward_possible": True,
                        "github_sync_main_fast_forward_possible": True,
                        "github_sync_remote_safety_ok": True,
                    },
                    "summary": {
                        "status": "approval_required",
                        "reason_code": "ERR_GITHUB_SYNC_NOT_COMPLETE",
                        "remote_sync_needed": True,
                        "remote_mutation_approval_pending": True,
                        "remote_mutation_approved": False,
                        "feature_ahead_count": 11,
                        "main_ahead_count": 59,
                        "pending_remote_update_count": 2,
                    },
                    "artifacts": {
                        "github_development_sync_preflight": "<live-git-state>",
                    },
                    "claim_boundary": "The GitHub development sync preflight is read-only.",
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == blocker_id
    assert row["namespace"] == "github_sync"
    assert row["scope"] == "release_area"
    assert row["owner"] == "release_owner"
    assert row["owner_input_required"] is True
    assert row["external_input_required"] is True
    assert row["resolution_type"] == "r4_remote_mutation_approval_required"
    assert row["handoff_state"] == "external_owner_input_ready"
    assert "feature push + main fast-forward 승인" in row["owner_action"]
    assert any("check_github_development_sync_preflight.py --fetch --json" in command for command in row["reproduction_commands"])
    assert any("remote_sync_needed == false" in item for item in row["acceptance_criteria"])
    assert any("origin/main" in item for item in row["acceptance_criteria"])
    assert row["claim_boundary"] == "The GitHub development sync preflight is read-only."
    assert row["evidence_status"]["state"] == "approval_required"
    assert row["evidence_status"]["remote_sync_needed"] is True
    assert row["evidence_status"]["remote_mutation_approval_pending"] is True
    assert row["evidence_status"]["feature_ahead_count"] == 11
    assert row["evidence_status"]["main_ahead_count"] == 59
    assert row["evidence_status"]["approval_phrase"] == "feature push + main fast-forward 승인"


def test_build_register_guides_human_new_user_ux_blocker(tmp_path: Path) -> None:
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": ["ux::human_new_user_observation_missing_or_failed"],
            "release_area_blockers": ["ux::human_new_user_observation_missing_or_failed"],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "ux",
                    "title": "UX",
                    "status": "blocked",
                    "blockers": ["human_new_user_observation_missing_or_failed"],
                    "claim_boundary": "Human new-user observation is required for PM UX pass.",
                    "checks": {
                        "human_new_user_observation_pass": False,
                        "human_new_user_sample_30min_pass": False,
                    },
                    "summary": {
                        "automated_sample_completion_minutes": 0.27,
                        "human_sample_completion_minutes": None,
                        "human_observation_reason_code": "ERR_UX_NEW_USER_OBSERVATION_REQUIRED",
                        "human_observation_owner_action": "Schedule and attach one observed new-user sample run.",
                    },
                    "artifacts": {
                        "ux_new_user_observation": "ux_new_user_observation_report.json",
                    },
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == "ux::human_new_user_observation_missing_or_failed"
    assert row["owner"] == "ux_research_owner"
    assert row["owner_input_required"] is True
    assert row["external_input_required"] is True
    assert row["resolution_type"] == "external_human_new_user_observation_required"
    assert row["owner_action"] == "Schedule and attach one observed new-user sample run."
    assert any("build_ux_new_user_observation_report.py" in command for command in row["reproduction_commands"])
    assert any("build_ux_new_user_observation_intake_packet.py" in command for command in row["reproduction_commands"])
    assert any("build_ux_new_user_observation_report.py" in command for command in row["verification_commands"])
    assert any("build_ux_new_user_observation_intake_packet.py" in command for command in row["verification_commands"])
    assert any("ux_new_user_observation_report.json.contract_pass" in item for item in row["acceptance_criteria"])
    assert "ux_new_user_observation_report" in row["evidence_artifacts"]
    assert "ux_new_user_observation_intake_packet" in row["evidence_artifacts"]
    assert row["handoff_ready"] is True
    assert row["handoff_state"] == "external_owner_input_ready"
    assert row["handoff"]["expected_intake_artifact"] == "ux_new_user_observation_intake_packet"
    assert row["evidence_status"]["state"] == "missing_human_new_user_observation"
    assert row["evidence_status"]["source_policy"] == "human_new_user_observation_required"
    assert row["evidence_status"]["human_observation_reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"


def test_build_register_distinguishes_ux_observation_and_30min_evidence_blockers(tmp_path: Path) -> None:
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": [
                "ux::human_new_user_observation_missing_or_failed",
                "ux::human_new_user_30min_sample_evidence_missing",
            ],
            "release_area_blockers": [
                "ux::human_new_user_observation_missing_or_failed",
                "ux::human_new_user_30min_sample_evidence_missing",
            ],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "ux",
                    "title": "UX",
                    "status": "blocked",
                    "blockers": [
                        "human_new_user_observation_missing_or_failed",
                        "human_new_user_30min_sample_evidence_missing",
                    ],
                    "claim_boundary": "Human new-user observation is required for PM UX pass.",
                    "checks": {
                        "human_new_user_observation_pass": False,
                        "human_new_user_sample_30min_evidence_present": False,
                        "human_new_user_sample_30min_pass": False,
                    },
                    "summary": {
                        "automated_sample_completion_minutes": 0.27,
                        "human_sample_completion_minutes": None,
                        "human_observation_reason_code": "ERR_UX_NEW_USER_OBSERVATION_REQUIRED",
                        "human_observation_owner_action": "Schedule and attach one observed new-user sample run.",
                    },
                    "artifacts": {
                        "ux_new_user_observation": "ux_new_user_observation_report.json",
                    },
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    observation_row = rows["ux::human_new_user_observation_missing_or_failed"]
    completion_row = rows["ux::human_new_user_30min_sample_evidence_missing"]

    assert observation_row["evidence_status"]["state"] == "missing_human_new_user_observation"
    assert completion_row["evidence_status"]["state"] == "missing_human_new_user_completion_evidence"
    assert completion_row["evidence_status"]["human_new_user_sample_30min_evidence_present"] is False
    assert any(
        "ux::human_new_user_observation_missing_or_failed" in item
        for item in observation_row["acceptance_criteria"]
    )
    assert any(
        "ux::human_new_user_30min_sample_evidence_missing" in item
        for item in completion_row["acceptance_criteria"]
    )
    assert not any(
        "ux::human_new_user_observation_missing_or_failed" in item
        for item in completion_row["acceptance_criteria"]
    )


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json")
    out = tmp_path / "register.json"
    out_md = tmp_path / "register.md"

    exit_code = build_register_module.main(
        [
            "--pm-report",
            str(report),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Blocker Action Register" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 2
    assert "basic_ci::pr_ci_30_consecutive_pass_evidence_missing" in out_md.read_text(encoding="utf-8")
    assert "release_ci_owner" in out_md.read_text(encoding="utf-8")
    assert "external_owner_input_ready" in out_md.read_text(encoding="utf-8")
