from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "report_pm_release_gate.py"
SPEC = importlib.util.spec_from_file_location("report_pm_release_gate", SCRIPT_PATH)
assert SPEC is not None
report_pm_release_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_pm_release_gate)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _text(path: Path, content: str = "manual\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _science_action_hints(family: str) -> dict[str, object]:
    return {
        "h_bond": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "h_bond_backmap_operator_intake_packet.json"
            ),
            "operator_intake_route": "/product/capabilities",
            "next_actions": [
                "fill_h_bond_backmap_operator_intake_packet",
                "attach_h_bond_backmap_operator_receipts",
                "materialize_h_bond_backmap_evidence_rows",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
                "regenerate_pm_release_gate_report",
            ],
        },
        "gpcr": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_operator_intake_packet.json"
            ),
            "operator_intake_route": (
                "/product/gpcr-hard-decoy-suite-report/operator-intake"
            ),
            "next_actions": [
                "fill_gpcr_hard_decoy_operator_intake_packet",
                "fill_drd2_htr2a_oprm1_operator_template_values",
                "run_gpcr_hard_decoy_materializer",
                "refresh_gpcr_hard_decoy_product_report",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
            ],
        },
        "pocketmd_lite": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_operator_intake_packet.json"
            ),
            "operator_intake_route": "/product/pocketmd-lite/operator-intake",
            "next_actions": [
                "fill_pocketmd_lite_operator_intake_packet",
                "attach_top_k_candidate_refinement_rows",
                "run_pocketmd_lite_topk_survival_materializer",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
            ],
        },
    }[family]


def _runtime_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "ndtha_long_profile": _write(
            tmp_path / "ndtha_long_profile.json",
            {"contract_pass": True, "checks": {"all_runs_pass": True}, "summary": {"peak_vram_mb_mean": 128.0}},
        ),
        "solver_hip_e2e": _write(
            tmp_path / "solver_hip.json",
            {
                "contract_pass": True,
                "checks": {
                    "all_main_loops_gpu_pass": True,
                    "no_cpu_backend_pass": True,
                    "no_cpu_required_pass": True,
                    "no_cpu_fallback_pass": True,
                },
                "summary": {"device_residency_ratio_min": 1.0},
            },
        ),
        "runtime_policy": _write(
            tmp_path / "policy.json",
            {
                "status": "ready",
                "official_solver_backend": "amd_rocm_hip",
                "official_solver_backend_family": "rocm_hip",
                "cpu_solver_fallback_detected": False,
                "cpu_fallback_allowed_for_official_solver_closure": False,
            },
        ),
        "ci_require_ndtha": _write(tmp_path / "ci.json", {"reason_code": "PASS", "host_copy_share": 0.03}),
        "ci_require_hip": _write(tmp_path / "ci_require_hip.json", {"reason_code": "PASS"}),
        "zero_copy_strict": _write(tmp_path / "probe.json", {"contract_pass": True, "host_copy_bytes": 0, "tensor_bytes": 100}),
    }


def _packaging_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "workflow_productization": _write(
            tmp_path / "workflow.json",
            {
                "contract_pass": True,
                "summary_line": "Workflow: PASS | viewer=yes(results+review)",
                "summary": {
                    "viewer_mode": "static_release_artifact_viewer",
                    "results_explorer_traceability_pass": True,
                    "zero_touch_no_open_decision_items_pass": True,
                    "repro_command": "python3 scripts/report_pm_release_gate.py",
                },
            },
        ),
        "release_registry": _write(
            tmp_path / "release_registry.json",
            {"contract_pass": True, "summary": {"signing_algorithm": "ed25519", "artifact_count": 12}},
        ),
        "support_bundle": _write(
            tmp_path / "support.json",
            {
                "contract_pass": True,
                "checks": {
                    "archive_roundtrip_test_pass": True,
                    "redaction_self_test_pass": True,
                    "bundle_roundtrip_test_pass": True,
                    "missing_required_count": 0,
                    "pm_failure_bundle_coverage_pass": True,
                },
                "pm_failure_bundle_coverage": {
                    "coverage_pass": True,
                    "bundle_path": "release/support_bundle/pm_failure_bundle_coverage.json",
                    "sha256": "pm-failure-bundle-coverage-sha256",
                },
                "export_archive": {
                    "available": True,
                    "path": "release/support_bundle_export.zip",
                    "sha256": "support-bundle-sha256",
                    "member_count": 12,
                },
                "optional_sections": {
                    "ci_streak_intake_packet": "release/support_bundle/redacted/ci_streak_intake_packet.json",
                    "ci_streak_manifest": "release/support_bundle/redacted/ci_streak_manifest.json",
                    "github_actions_ci_streak_evidence": (
                        "release/support_bundle/redacted/github_actions_ci_streak_evidence.json"
                    ),
                    "license_status_intake_packet": "release/support_bundle/redacted/license_status_intake_packet.json",
                    "license_status_closure_report": (
                        "release/support_bundle/redacted/license_status_closure_report.json"
                    ),
                    "license_status_template": "release/support_bundle/redacted/license_status_template.json",
                    "pm_release_blocker_action_register": "release/support_bundle/redacted/pm_release_blocker_action_register.json",
                    "pm_release_blocker_closure_board": "release/support_bundle/redacted/pm_release_blocker_closure_board.json",
                    "pm_release_gate_completion_audit": "release/support_bundle/redacted/pm_release_gate_completion_audit.json",
                    "pm_release_gate_reviewer_handoff": "release/support_bundle/redacted/pm_release_gate_reviewer_handoff.json",
                    "pm_owner_evidence_request_packet": (
                        "release/support_bundle/redacted/pm_owner_evidence_request_packet.json"
                    ),
                    "frontend_dependency_audit_report": (
                        "release/support_bundle/redacted/frontend_dependency_audit_report.json"
                    ),
                    "release_validation_manual": "release/support_bundle/redacted/release_validation_manual.md",
                    "release_limitation_manual": "release/support_bundle/redacted/release_limitation_manual.md",
                    "ux_new_user_observation_report": (
                        "release/support_bundle/redacted/ux_new_user_observation_report.json"
                    ),
                    "ux_new_user_observation_intake_packet": (
                        "release/support_bundle/redacted/ux_new_user_observation_intake_packet.json"
                    ),
                    "template_evidence_safety_report": (
                        "release/support_bundle/redacted/template_evidence_safety_report.json"
                    ),
                    "pm_release_reproduction_command_audit": (
                        "release/support_bundle/redacted/pm_release_reproduction_command_audit.json"
                    ),
                    "commercial_gap_ledger_status": "release/support_bundle/redacted/commercial_gap_ledger_status.json",
                    "gap_closure_status": "release/support_bundle/redacted/gap_closure_status.json",
                },
            },
        ),
        "pm_release_blocker_action_register": _write(
            tmp_path / "pm-release-blocker-action-register.json",
            {
                "contract_pass": True,
                "summary": {
                    "open_blocker_count": 0,
                    "handoff_ready_count": 0,
                    "handoff_not_ready_count": 0,
                    "external_owner_input_ready_count": 0,
                    "all_open_blockers_have_handoff": True,
                },
                "rows": [],
            },
        ),
        "pm_release_blocker_closure_board": _write(
            tmp_path / "pm-release-blocker-closure-board.json",
            {
                "contract_pass": True,
                "summary": {
                    "open_blocker_count": 0,
                    "handoff_ready_count": 0,
                    "handoff_not_ready_count": 0,
                    "external_owner_input_ready_count": 0,
                    "all_open_blockers_have_handoff": True,
                },
                "rows": [],
            },
        ),
        "validation_manual": _text(
            tmp_path / "validation.md",
            "PM release gate validation family p95 error residual benchmark breadth interop reproduction commands\n",
        ),
        "limitation_manual": _text(
            tmp_path / "limitations.md",
            "claim boundary paid pilot limited commercial ga/enterprise known issues support bundle rollback\n",
        ),
        "pm_release_reproduction_command_audit": _write(
            tmp_path / "pm_release_reproduction_command_audit.json",
            {
                "schema_version": "pm-release-reproduction-command-audit.v1",
                "contract_pass": True,
                "reason_code": "PASS",
                "summary_line": "PM reproduction command audit: PASS | artifacts=7/7 | commands=42 | violations=0",
                "summary": {"artifact_count": 7, "command_count": 42, "violation_count": 0},
            },
        ),
    }


def _release_area_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "ci_pr": _write(tmp_path / "ci_pr.json", {"reason_code": "PASS", "summary": {"pass_streak_count": 30}}),
        "ci_nightly": _write(
            tmp_path / "ci_nightly.json",
            {"reason_code": "PASS", "summary": {"pass_streak_count": 30}},
        ),
        "ci_streak_manifest": _write(
            tmp_path / "ci_streak_manifest.json",
            {
                "schema_version": "ci-consecutive-pass-manifest.v1",
                "threshold": 30,
                "contract_pass": True,
                "evidence_sources": {
                    "github_actions_evidence_path": "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json",
                },
                "lanes": {
                    "pr": {
                        "consecutive_pass_count": 30,
                        "local_consecutive_pass_count": 30,
                        "github_actions_consecutive_pass_count": 30,
                        "pull_request_run_source_present": True,
                        "missing_consecutive_pass_count": 0,
                        "threshold_pass": True,
                        "streak_source": "github_actions",
                        "owner_action": "No release action required; consecutive pass threshold is satisfied.",
                        "claim_boundary": "Local PR gate reports prove command-level readiness; release streak credit requires tracked PR CI evidence for the consecutive-pass window.",
                    },
                    "nightly": {
                        "consecutive_pass_count": 30,
                        "local_consecutive_pass_count": 30,
                        "github_actions_consecutive_pass_count": 30,
                        "missing_consecutive_pass_count": 0,
                        "threshold_pass": True,
                        "streak_source": "github_actions",
                        "owner_action": "No release action required; consecutive pass threshold is satisfied.",
                        "claim_boundary": "Local nightly artifacts prove command-level readiness; release streak credit requires tracked nightly CI evidence for the consecutive-pass window.",
                    },
                },
            },
        ),
        "ci_streak_intake_packet": _write(
            tmp_path / "ci_streak_intake_packet.json",
            {
                "schema_version": "ci-streak-intake-packet.v1",
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {
                    "threshold": 30,
                    "lane_pass_count": 2,
                    "source_evidence_pass": True,
                    "source_evidence_generated_at": "2026-06-16T00:00:00+00:00",
                    "source_evidence_age_hours": 1.0,
                    "source_evidence_freshness_pass": True,
                    "pr_missing_consecutive_pass_count": 0,
                    "nightly_missing_consecutive_pass_count": 0,
                    "pr_pull_request_run_source_present": True,
                },
                "source_evidence": {
                    "contract_pass": True,
                    "generated_at": "2026-06-16T00:00:00+00:00",
                    "age_hours": 1.0,
                    "freshness_pass": True,
                    "lanes": {
                        "pr": {
                            "source_release_credit_pass": True,
                            "workflow_state": "active",
                            "local_workflow_trigger_events": ["pull_request", "push"],
                            "local_required_trigger_present": True,
                        },
                        "nightly": {
                            "source_release_credit_pass": True,
                            "workflow_state": "active",
                            "local_workflow_trigger_events": ["schedule", "workflow_dispatch"],
                            "local_required_trigger_present": True,
                        },
                    },
                },
                "lane_rows": [
                    {
                        "lane": "pr",
                        "threshold": 30,
                        "threshold_pass": True,
                        "consecutive_pass_count": 30,
                    },
                    {
                        "lane": "nightly",
                        "threshold": 30,
                        "threshold_pass": True,
                        "consecutive_pass_count": 30,
                    },
                ],
            },
        ),
        "commercial_readiness": _write(
            tmp_path / "commercial_readiness.json",
            {
                "contract_pass": True,
                "checks": {"accuracy_pass": True},
                "model_rows": [
                    {
                        "model_id": "family_a",
                        "metrics": {
                            "drift_error_pct_p95": 3.5,
                            "base_shear_error_pct_p95": 2.0,
                            "high_noise_drift_error_pct_p95": 8.0,
                        },
                    }
                ],
            },
        ),
        "core_family_p95_report": _write(
            tmp_path / "core_family_p95.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {"max_family_p95_error_pct": 3.5, "metric_row_count": 2},
                "rows": [
                    {
                        "model_id": "family_a",
                        "family": "family_a",
                        "metric": "drift_error_pct",
                        "p95_error_pct": 3.5,
                    },
                    {
                        "model_id": "family_a",
                        "family": "family_a",
                        "metric": "base_shear_error_pct",
                        "p95_error_pct": 2.0,
                    },
                ],
            },
        ),
        "residual_level3_status": _write(
            tmp_path / "residual_level3_status.json",
            {
                "contract_pass": True,
                "status": "ready",
                "reason_code": "PASS",
                "blockers": [],
                "summary": {
                    "case_count": 3,
                    "hard_pass_rate": 1.0,
                    "recommended_pass_rate": 1.0,
                    "fallback_rate": 0.0,
                    "solver_raw_ratio": 1.0,
                },
            },
        ),
        "runtime_packaging": _write(
            tmp_path / "runtime_packaging.json",
            {"contract_pass": True, "checks": {"rollback_runbook_present": True}},
        ),
        "runtime_memory_budget": _write(
            tmp_path / "runtime_memory_budget.json",
            {
                "contract_pass": True,
                "summary": {
                    "p95_runtime_budget_exceed_rate": 0.0,
                    "oom_count": 0,
                },
            },
        ),
        "runtime_sbom": _write(tmp_path / "runtime_sbom.json", {"component_count": 3}),
        "frontend_dependency_audit": _write(
            tmp_path / "frontend_dependency_audit.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "checks": {
                    "dependency_vulnerability_total_zero_pass": True,
                    "dependency_high_or_critical_zero_pass": True,
                },
                "summary": {"vulnerability_total": 0, "high_or_critical_vulnerability_count": 0},
            },
        ),
        "repro_lock": _write(tmp_path / "repro_lock.json", {"contract_pass": True, "reason_code": "PASS"}),
        "workstation_budget": _write(
            tmp_path / "workstation_budget.json",
            {
                "contract_pass": True,
                "p95_runtime_budget_exceed_rate": 0.02,
                "oom_count": 0,
                "performance_budget": {"memory_budget_gib": {"minimum_required_gib": 16}},
            },
        ),
        "viewer_performance_budget": _write(tmp_path / "viewer_performance_budget.json", {"contract_pass": True}),
        "midas_interop": _write(tmp_path / "midas_interop.json", {"contract_pass": True, "reason_code": "PASS"}),
        "midas_native_roundtrip": _write(
            tmp_path / "midas_native_roundtrip.json",
            {"contract_pass": True, "reason_code": "PASS"},
        ),
        "midas_exact_roundtrip": _write(
            tmp_path / "midas_exact_roundtrip.json",
            {"contract_pass": True, "reason_code": "PASS", "summary": {"exact_case_ratio": 1.0}},
        ),
        "midas_kds_geometry": _write(
            tmp_path / "midas_kds_geometry.json",
            {"contract_pass": True, "reason_code": "PASS", "checks": {"full_crosswalk_pass": True}},
        ),
        "opensees_topology": _write(
            tmp_path / "opensees_topology.json",
            {"contract_pass": True, "reason_code": "PASS", "checks": {"roundtrip_trace_pass": True}},
        ),
        "opensees_roundtrip_trace": _write(
            tmp_path / "opensees_roundtrip_trace.json",
            {"contract_pass": True, "reason_code": "PASS"},
        ),
        "viewer_quality": _write(
            tmp_path / "viewer_quality.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {"review_item_count": 7},
            },
        ),
        "ux_release_readiness": _write(
            tmp_path / "ux_release_readiness.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {
                    "sample_completion_minutes": 2.0,
                    "viewer_review_item_count": 7,
                    "claim_scoped_review_item_count": 7,
                    "blocking_review_item_count": 0,
                },
            },
        ),
        "ux_new_user_observation": _write(
            tmp_path / "ux_new_user_observation.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {
                    "completion_minutes": 24.0,
                    "owner_action": "human UX observation complete",
                },
            },
        ),
        "security_runbook": _text(
            tmp_path / "security.md",
            "no production default secret\nnegative start test\n",
        ),
        "license_status": _write(tmp_path / "license_status.json", {"status": "active"}),
        "license_status_closure": _write(
            tmp_path / "license_status_closure.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary": {
                    "status": "active",
                    "tier": "limited-commercial",
                    "owner_action": "license evidence populated",
                    "template_path": "docs/templates/license_status.template.json",
                },
                "blockers": [],
            },
        ),
        "ai_orchestration_preflight": _write(
            tmp_path / "ai_orchestration.json",
            {
                "contract_pass": True,
                "summary": {
                    "cursor_worker_cli": "cursor-agent",
                    "opencode_worker_cli": "opencode",
                    "opencode_version": "1.17.7",
                    "opencode_configured_model": "opencode-go/deepseek-v4-pro",
                    "opencode_configured_model_available": True,
                    "opencode_assignment_routed_to_cursor": True,
                    "opencode_assignment_cursor_model": "composer-2.5",
                },
            },
        ),
        "ga_enterprise_readiness": _write(
            tmp_path / "ga_enterprise_readiness.json",
            {
                "contract_pass": False,
                "reason_code": "ERR_GA_ENTERPRISE_EVIDENCE_PENDING",
                "summary_line": "GA enterprise readiness: BLOCKED | independent_vv=False",
                "summary": {
                    "owner_action": (
                        "Attach independent V&V attestation, family validation-manual signoff, "
                        "and customer audit/failure-bundle/SLA approval evidence before GA/Enterprise release."
                    )
                },
                "blockers": [
                    "independent_vv_missing",
                    "family_validation_manual_signoff_missing",
                    "customer_audit_failure_bundle_sla_missing",
                ],
            },
        ),
        "ga_enterprise_signoff_intake": _write(
            tmp_path / "ga_enterprise_signoff_intake.json",
            {
                "contract_pass": False,
                "reason_code": "ERR_GA_ENTERPRISE_SIGNOFF_OWNER_INPUT_REQUIRED",
                "summary_line": "GA enterprise signoff intake: BLOCKED | signoffs=0/3",
            },
        ),
        "paid_pilot_scope_guard": _write(
            tmp_path / "paid_pilot_scope_guard.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary_line": "Paid pilot scope guard: PASS",
            },
        ),
        "template_evidence_safety": _write(
            tmp_path / "template_evidence_safety_report.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "summary_line": "Template evidence safety: PASS | templates=5 | validator_probes=5 | blockers=0",
            },
        ),
        "release_evidence_freshness": _write(
            tmp_path / "release_evidence_freshness_report.json",
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "current_source_commit_sha": "abcdef123456",
                "max_age_days": 30,
                "summary": {
                    "artifact_count": 3,
                    "pass_count": 3,
                    "blocker_count": 0,
                    "source_commit_match_count": 3,
                    "engine_version_present_count": 3,
                    "input_checksum_present_count": 3,
                    "reuse_marker_present_count": 3,
                    "dependency_mtime_pass_count": 3,
                },
                "blockers": [],
            },
        ),
        "fresh_full_validation_lane_status": _write(
            tmp_path / "fresh_full_validation_lane_status.json",
            {
                "contract_pass": False,
                "reason_code": "ERR_FRESH_FULL_VALIDATION_LANES_INCOMPLETE",
                "summary": {
                    "lane_count": 8,
                    "lane_contract_pass_count": 8,
                    "fresh_validation_receipt_pass_count": 0,
                    "fresh_validation_receipt_present_count": 0,
                    "blocker_count": 8,
                },
                "blockers": ["gpu_hip_solver::fresh_validation_receipt_missing"],
            },
        ),
        "customer_shadow_evidence_status": _write(
            tmp_path / "customer_shadow_evidence_status.json",
            {
                "contract_pass": False,
                "reason_code": "ERR_CUSTOMER_SHADOW_EVIDENCE_INCOMPLETE",
                "summary": {
                    "completed_shadow_case_count": 0,
                    "min_completed_shadow_cases": 3,
                    "target_completed_shadow_cases": 5,
                    "evidence_file_count": 0,
                    "valid_evidence_file_count": 0,
                },
                "blockers": ["completed_shadow_case_count_below_minimum"],
            },
        ),
        "commercial_gap_ledger_status": _write(
            tmp_path / "commercial_gap_ledger_status.json",
            {
                "schema_version": "commercial-gap-ledger-status.v1",
                "status": "open",
                "full_gap_ledger_ready": False,
                "commercial_solver_gap_ready": False,
                "ai_engine_gap_ready": True,
                "summary": {
                    "total_count": 20,
                    "closed_count": 17,
                    "partial_count": 2,
                    "open_count": 0,
                    "external_blocked_count": 1,
                },
                "next_locally_closable_gaps": ["G1"],
                "blockers": ["G1:direct_residual_newton_not_closed"],
            },
        ),
        "gap_closure_status": _write(
            tmp_path / "gap_closure_status.json",
            {
                "schema_version": "gap-closure-status.v1",
                "full_gap_ledger_status": "open",
                "full_gap_ledger_ready": False,
                "full_gap_ledger_summary": {
                    "total_count": 20,
                    "closed_count": 17,
                    "partial_count": 2,
                    "open_count": 0,
                    "external_blocked_count": 1,
                },
                "next_locally_closable_gaps": ["G1"],
            },
        ),
        "github_sync_preflight": _write(
            tmp_path / "github_development_sync_preflight_report.json",
            {
                "schema_version": "github-development-sync-preflight.v1",
                "status": "synced",
                "contract_pass": True,
                "preflight_pass": True,
                "remote_mutation_approved": False,
                "remote_sync_needed": False,
                "reason_code": "PASS",
                "blockers": [],
                "state": {
                    "feature_ahead_count": 0,
                    "main_ahead_count": 0,
                    "feature_fast_forward_possible": True,
                    "main_fast_forward_possible": True,
                },
                "checks": {
                    "worktree_clean": True,
                    "remote_safety_ok": True,
                    "remote_fetch_ok": None,
                    "feature_fast_forward_possible": True,
                    "main_fast_forward_possible": True,
                    "feature_synced_to_head": True,
                    "main_synced_to_head": True,
                    "explicit_remote_mutation_approval": False,
                },
                "pending_remote_updates": [],
                "r4_disclosure": {
                    "target": [],
                    "action": "no remote mutation required",
                    "impact": "No GitHub ref update is needed; feature and main already match local HEAD.",
                    "risk": "No remote mutation remains.",
                    "rollback": "no rollback needed",
                    "verification": "fetch origin and compare remote feature/main refs with local HEAD after push",
                },
                "claim_boundary": (
                    "This preflight is read-only. It does not push, merge, publish, or mutate GitHub. "
                    "A remote update still requires explicit human R4 approval."
                ),
            },
        ),
    }


def _release_decision_inputs(tmp_path: Path) -> dict[str, Path]:
    evidence_surface_dir = tmp_path / "evidence_surfaces"
    _write(
        evidence_surface_dir / "structural_contact_surface.json",
        {
            "contract_pass": True,
            "status": "ready",
            "reason_code": "PASS",
            "summary_line": "Structural contact surface: PASS",
            "blockers": [],
        },
    )
    _write(
        evidence_surface_dir / "gpcr_hard_decoy_surface.json",
        {
            "contract_pass": False,
            "status": "locked",
            "reason_code": "ERR_BROAD_GPCR_CLAIM_LOCKED",
            "summary_line": "GPCR hard decoy surface: LOCKED",
            "blockers": ["broad_gpcr_family_claim_locked"],
            "first_blocked_target": "DRD2",
            "root_cause_tags": ["operator_values_required"],
            "phase3_exit_gate": {
                "failed_criteria": [
                    "ranking_pr_auc_ci_low_min",
                    "top20_hit_rate_min",
                    "decoys_above_positive_count_max",
                    "no_positive_out_anchored_by_top_decoys",
                ]
            },
        },
    )
    return {
        "external_benchmark_submission_readiness": _write(
            tmp_path / "external_benchmark_submission_readiness.json",
            {
                "contract_pass": True,
                "reason_code": "PASS_START_NOW_FULL",
                "summary": {
                    "ready_to_start_now": True,
                    "ready_to_start_full_submission_now": True,
                    "submission_queue_ready_count": 4,
                    "submission_queue_blocked_count": 0,
                },
                "blockers": [],
            },
        ),
        "public_benchmark_source_of_truth": _write(
            tmp_path / "public_benchmark_source_of_truth.json",
            {
                "contract_pass": True,
                "public_benchmark_ready": True,
                "status": "ready",
                "blockers": [],
            },
        ),
        "evidence_surface_dir": evidence_surface_dir,
    }


def _base_kwargs(tmp_path: Path) -> dict[str, Path]:
    kwargs = {}
    kwargs.update(_runtime_inputs(tmp_path))
    kwargs.update(_packaging_inputs(tmp_path))
    kwargs.update(_release_area_inputs(tmp_path))
    kwargs.update(_release_decision_inputs(tmp_path))
    return kwargs


def test_public_benchmark_ready_requires_source_of_truth_ready() -> None:
    measured = {"contract_pass": True}
    external = {
        "contract_pass": True,
        "summary": {"ready_to_start_full_submission_now": True},
    }

    assert (
        report_pm_release_gate._public_benchmark_ready(
            measured,
            external,
            {"contract_pass": True, "public_benchmark_ready": True},
        )
        is True
    )
    assert (
        report_pm_release_gate._public_benchmark_ready(
            measured,
            external,
            {"contract_pass": True, "public_benchmark_ready": False},
        )
        is False
    )


def test_public_benchmark_source_of_truth_blocker_becomes_operator_action() -> None:
    actions = report_pm_release_gate._public_benchmark_operator_actions(
        {
            "status": "seed_ready_materialization_blocked",
            "public_benchmark_ready": False,
            "blockers": [
                "casf_pdbbind_source_material_not_attached",
                "public_benchmark_real_pose_predictions_missing",
            ],
            "first_blocked_target": "casf_pdbbind_subset_intake",
            "root_cause_tags": [
                "operator_source_material_required",
                "operator_receipts_required",
            ],
            "next_actions": [
                "attach_checked_casf_pdbbind_subset_source_files",
                "run_public_benchmark_subset_materializer",
            ],
            "tier_beta_gate": {
                "failed_criteria": [
                    "casf_pdbbind_subset_materialized",
                    "symmetry_rmsd_scorecard_real_cases",
                ]
            },
            "operator_intake_packet": {
                "route": "/product/public-benchmark/operator-intake",
                "artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.json"
                ),
                "markdown_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.md"
                ),
            },
            "operator_handoff_summary": {
                "route": "/product/public-benchmark/operator-intake",
                "artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.json"
                ),
                "required_slot_count": 4,
                "blocked_operator_slot_count": 4,
                "template_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_casf_pdbbind_operator_template.json"
                ),
                "minimum_evidence": {
                    "case_count": 12,
                    "source_family": "CASF/PDBBind",
                },
                "materialization_command": (
                    "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                    "--intake <operator-casf-pdbbind-intake.json>"
                ),
                "validation_command": (
                    "python3 scripts/validate_public_benchmark_subset_manifest.py "
                    "--manifest implementation/phase1/release_evidence/productization/"
                    "public_benchmark_subset_manifest.json --fail-blocked"
                ),
            },
            "operator_handoff_queue_count": 1,
            "first_operator_handoff": {
                "handoff_id": "public_benchmark::casf_pdbbind_subset_intake",
                "route": "/product/public-benchmark/operator-intake",
                "operator_intake_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.json"
                ),
                "operator_intake_markdown_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.md"
                ),
                "slot_id": "casf_pdbbind_subset_intake",
                "template_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_casf_pdbbind_operator_template.json"
                ),
                "minimum_evidence": {
                    "case_count": 12,
                    "source_family": "CASF/PDBBind",
                },
                "materialization_command": (
                    "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                    "--intake <operator-casf-pdbbind-intake.json>"
                ),
                "validation_command": (
                    "python3 scripts/validate_public_benchmark_subset_manifest.py "
                    "--manifest implementation/phase1/release_evidence/productization/"
                    "public_benchmark_subset_manifest.json --fail-blocked"
                ),
            },
        }
    )

    assert actions == [
        {
            "action_id": "materialize_public_benchmark_source_of_truth",
            "status": "public_benchmark_evidence_required",
            "bottleneck": "public_benchmark_source_of_truth_not_ready",
            "first_blocker": "casf_pdbbind_source_material_not_attached",
            "first_blocked_target": "casf_pdbbind_subset_intake",
            "root_cause_tags": [
                "operator_source_material_required",
                "operator_receipts_required",
            ],
            "blocked_criteria": [
                "casf_pdbbind_subset_materialized",
                "symmetry_rmsd_scorecard_real_cases",
            ],
            "blocked_criteria_count": 2,
            "blockers": [
                "casf_pdbbind_source_material_not_attached",
                "public_benchmark_real_pose_predictions_missing",
            ],
            "next_actions": [
                "attach_checked_casf_pdbbind_subset_source_files",
                "run_public_benchmark_subset_materializer",
            ],
            "reason": (
                "public benchmark source-of-truth is seed_ready_materialization_blocked; "
                "first_blocker=casf_pdbbind_source_material_not_attached; "
                "first_blocked_target=casf_pdbbind_subset_intake; "
                "root_cause_tags=operator_source_material_required,operator_receipts_required; "
                "next_action=attach_checked_casf_pdbbind_subset_source_files"
            ),
            "artifact": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_source_of_truth.json"
            ),
            "operator_intake_route": "/product/public-benchmark/operator-intake",
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_operator_intake_packet.json"
            ),
            "operator_intake_markdown_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_operator_intake_packet.md"
            ),
            "operator_template_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_casf_pdbbind_operator_template.json"
            ),
            "first_operator_handoff": {
                "handoff_id": "public_benchmark::casf_pdbbind_subset_intake",
                "route": "/product/public-benchmark/operator-intake",
                "operator_intake_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.json"
                ),
                "operator_intake_markdown_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.md"
                ),
                "slot_id": "casf_pdbbind_subset_intake",
                "template_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_casf_pdbbind_operator_template.json"
                ),
                "minimum_evidence": {
                    "case_count": 12,
                    "source_family": "CASF/PDBBind",
                },
                "materialization_command": (
                    "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                    "--intake <operator-casf-pdbbind-intake.json>"
                ),
                "validation_command": (
                    "python3 scripts/validate_public_benchmark_subset_manifest.py "
                    "--manifest implementation/phase1/release_evidence/productization/"
                    "public_benchmark_subset_manifest.json --fail-blocked"
                ),
            },
            "operator_handoff_queue_count": 1,
            "blocked_operator_slot_count": 4,
            "required_slot_count": 4,
            "minimum_evidence": {
                "case_count": 12,
                "source_family": "CASF/PDBBind",
            },
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                "--intake <operator-casf-pdbbind-intake.json>"
            ),
            "validation_command": (
                "python3 scripts/validate_public_benchmark_subset_manifest.py "
                "--manifest implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_manifest.json --fail-blocked"
            ),
        }
    ]

    assert report_pm_release_gate._public_benchmark_operator_actions(
        {"contract_pass": True, "public_benchmark_ready": True}
    ) == []


def test_pm_release_gate_keeps_paid_pilot_scope_when_limited_blockers_remain(tmp_path: Path) -> None:
    ndtha = _write(
        tmp_path / "release_evidence" / "productization" / "ndtha_residual_gate_report.json",
        {
            "contract_pass": True,
            "checks": {
                "ndtha_no_collapse_pass": True,
                "residual_top_hard_pass": True,
                "residual_drift_hard_pass": True,
                "recommended_residual_pass": True,
                "strict_recommended_residual_hard_fail_enabled": True,
                "strict_recommended_residual_pass": True,
                "corrected_state_recompute_pass": True,
                "solver_control_rollup_pass": True,
            },
            "summary": {
                "case_count": 3,
                "fallback_rate": 0.0,
                "solver_raw_ratio": 1.0,
                "corrected_state_recompute_required": False,
                "solver_control_nonconverged_step_total": 0,
            },
            "rows": [{"normalized_residual": {"recommended_max_ratio": 0.1}}],
        },
    )
    element = _write(
        tmp_path / "element.json",
        {
            "contract_pass": True,
            "checks": {
                "structural_contact_direct_contract_pass": True,
                "foundation_soil_link_direct_contract_pass": True,
            },
            "summary": {
                "beam_shell_contact_coupling_signal_count": 21,
                "material_model_types": ["rc_composite", "steel_elastic_plastic"],
            },
        },
    )
    breadth = _write(
        tmp_path / "breadth.json",
        {
            "contract_pass": True,
            "summary": {
                "measured_case_count": 294,
                "measured_family_count": 21,
                "baseline_measured_case_count": 51,
                "external_incremental_case_count": 10,
            },
        },
    )

    payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=tmp_path / "missing_worst.json",
        **_base_kwargs(tmp_path),
    )

    assert payload["paid_pilot_candidate"] is True
    assert payload["limited_commercial_milestone_ready"] is False
    assert payload["limited_commercial_release_ready"] is False
    assert payload["limited_commercial_ready"] is False
    assert payload["ga_enterprise_ready"] is False
    assert "M1::corrected_state_recompute_missing_or_failed" in payload["blockers"]
    assert "M2::contact_material_coupled_case_count_lt_10_or_missing" in payload["blockers"]
    assert "M4::holdout_cases_per_family_missing" in payload["blockers"]
    assert payload["release_area_gate_ready"] is False
    assert "Paid pilot / constrained customer PoC only" in payload["recommended_scope"]


def test_pm_release_gate_passes_limited_when_all_milestone_evidence_is_explicit(tmp_path: Path) -> None:
    ndtha = _write(
        tmp_path / "release_evidence" / "productization" / "ndtha_residual_gate_report.json",
        {
            "contract_pass": True,
            "checks": {
                "ndtha_no_collapse_pass": True,
                "residual_top_hard_pass": True,
                "residual_drift_hard_pass": True,
                "recommended_residual_pass": True,
                "strict_recommended_residual_hard_fail_enabled": True,
                "strict_recommended_residual_pass": True,
                "corrected_state_recompute_pass": True,
                "solver_control_rollup_pass": True,
            },
            "summary": {
                "case_count": 12,
                "fallback_rate": 0.01,
                "solver_raw_ratio": 0.99,
                "corrected_state_recompute_required": True,
                "corrected_state_recompute_present_count": 12,
                "corrected_state_recompute_pass_count": 12,
                "solver_control_nonconverged_step_total": 0,
            },
            "rows": [{"normalized_residual": {"recommended_max_ratio": 0.1}}],
        },
    )
    element = _write(
        tmp_path / "element.json",
        {
            "contract_pass": True,
            "checks": {
                "structural_contact_direct_contract_pass": True,
                "foundation_soil_link_direct_contract_pass": True,
                "panel_contact_failure_mode_reason_code_pass": True,
            },
            "summary": {
                "contact_material_coupled_case_count": 10,
                "nonlinear_residual_integrated_case_count": 2,
                "material_model_types": ["rc_composite", "steel_elastic_plastic", "composite_steel_rc"],
            },
        },
    )
    breadth = _write(
        tmp_path / "breadth.json",
        {
            "contract_pass": True,
            "summary": {
                "measured_case_count": 150,
                "measured_family_count": 6,
                "holdout_family_count": 6,
                "baseline_measured_case_count": 50,
                "opensees_incremental_case_count": 20,
            },
        },
    )
    worst = _write(tmp_path / "worst.json", {"contract_pass": True})
    base_kwargs = _base_kwargs(tmp_path)
    _write(
        base_kwargs["pm_release_blocker_action_register"],
        {
            "contract_pass": True,
            "summary": {
                "open_blocker_count": 16,
                "release_area_blocker_count": 5,
                "ga_enterprise_blocker_count": 16,
                "handoff_ready_count": 16,
                "handoff_not_ready_count": 0,
                "external_owner_input_ready_count": 8,
                "all_open_blockers_have_handoff": True,
            },
            "rows": [],
        },
    )
    _write(
        base_kwargs["pm_release_blocker_closure_board"],
        {
            "contract_pass": True,
            "summary": {
                "open_blocker_count": 16,
                "handoff_ready_count": 16,
                "handoff_not_ready_count": 0,
                "external_owner_input_ready_count": 8,
                "all_open_blockers_have_handoff": True,
            },
            "rows": [],
        },
    )

    payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **base_kwargs,
    )

    assert payload["paid_pilot_candidate"] is True
    assert payload["release_tiers"]["technical_paid_pilot_candidate"] is True
    assert payload["release_tiers"]["paid_pilot_scope_guard_pass"] is True
    assert payload["release_tiers"]["paid_pilot_scope_guard_report"].endswith("paid_pilot_scope_guard.json")
    assert payload["limited_commercial_milestone_ready"] is True
    assert payload["limited_commercial_release_ready"] is True
    assert payload["limited_commercial_ready"] is True
    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is True
    assert payload["reuse_policy"] == "status_rebuilt_from_pm_release_gate_input_receipts"
    assert payload["input_checksums"][str(ndtha)].startswith("sha256:")
    assert payload["input_checksums"][str(base_kwargs["release_evidence_freshness"])].startswith(
        "sha256:"
    )
    assert payload["input_checksums"][str(base_kwargs["external_benchmark_submission_readiness"])].startswith(
        "sha256:"
    )
    assert payload["input_checksums"][str(base_kwargs["public_benchmark_source_of_truth"])].startswith(
        "sha256:"
    )
    assert payload["release_area_gate_ready"] is True
    assert payload["full_release_gate_ready"] is True
    decision = payload["release_decision"]
    assert decision["release_allowed"] is True
    assert decision["blocked_release_count"] == 0
    assert decision["first_blocker"] == ""
    assert decision["operator_action_count"] == 19
    assert decision["approval_token_count"] == 0
    assert decision["stale_artifact_count"] == 0
    assert decision["stale_artifact_refresh_required"] is False
    assert decision["evidence_surface_count"] == 2
    assert decision["missing_evidence_surface_count"] == 0
    assert decision["locked_evidence_surface_count"] == 1
    assert decision["public_benchmark_ready"] is True
    assert decision["public_benchmark_source_of_truth_ready"] is True
    assert decision["public_benchmark_source_of_truth_status"] == "ready"
    assert decision["public_benchmark_source_of_truth_blockers"] == []
    assert decision["h_bond_evidence_surface_present"] is False
    assert decision["gpcr_evidence_surface_present"] is True
    assert decision["pocketmd_lite_science_product_surface_present"] is False
    assert decision["broad_gpcr_family_claim_safe"] is False
    assert decision["pocketmd_lite_product_surface_ready"] is False
    assert decision["science_evidence_surface_bottlenecks"] == [
        "h_bond_evidence_surface_missing",
        "broad_gpcr_family_claim_locked",
        "pocketmd_lite_science_product_surface_missing",
    ]
    science_surface_status = decision["science_evidence_surface_status"]
    assert science_surface_status["h_bond"] == {
        "surface_family": "h_bond",
        "present": False,
        "status": "missing",
        "surface_count": 0,
        "contract_pass_count": 0,
        "locked_count": 0,
        "surface_ids": [],
        "first_blocked_target": "",
        "root_cause_tags": [],
        "blocked_criteria": [],
        "bottleneck": "h_bond_evidence_surface_missing",
    }
    assert science_surface_status["gpcr"] == {
        "surface_family": "gpcr",
        "present": True,
        "status": "locked",
        "surface_count": 1,
        "contract_pass_count": 0,
        "locked_count": 1,
        "surface_ids": ["gpcr_hard_decoy_surface"],
        "first_blocked_target": "DRD2",
        "root_cause_tags": ["operator_values_required"],
        "blocked_criteria": [
            "ranking_pr_auc_ci_low_min",
            "top20_hit_rate_min",
            "decoys_above_positive_count_max",
            "no_positive_out_anchored_by_top_decoys",
        ],
        "bottleneck": "broad_gpcr_family_claim_locked",
        "broad_family_claim_safe": False,
    }
    assert science_surface_status["pocketmd_lite"] == {
        "surface_family": "pocketmd_lite",
        "present": False,
        "status": "missing",
        "surface_count": 0,
        "contract_pass_count": 0,
        "locked_count": 0,
        "surface_ids": [],
        "first_blocked_target": "",
        "root_cause_tags": [],
        "blocked_criteria": [],
        "bottleneck": "pocketmd_lite_science_product_surface_missing",
        "product_surface_ready": False,
    }
    assert decision["operator_actions"] == [
        {
            "action_id": "resolve_h_bond_evidence_surface",
            "status": "science_evidence_required",
            "surface_family": "h_bond",
            "bottleneck": "h_bond_evidence_surface_missing",
            "first_blocked_target": "",
            "root_cause_tags": [],
            "blocked_criteria": [],
            "blocked_criteria_count": 0,
            "reason": "h_bond evidence surface is missing; bottleneck=h_bond_evidence_surface_missing",
            "artifact": str(base_kwargs["evidence_surface_dir"]),
            **_science_action_hints("h_bond"),
        },
        {
            "action_id": "resolve_gpcr_evidence_surface",
            "status": "science_evidence_required",
            "surface_family": "gpcr",
            "bottleneck": "broad_gpcr_family_claim_locked",
            "first_blocked_target": "DRD2",
            "root_cause_tags": ["operator_values_required"],
            "blocked_criteria": [
                "ranking_pr_auc_ci_low_min",
                "top20_hit_rate_min",
                "decoys_above_positive_count_max",
                "no_positive_out_anchored_by_top_decoys",
            ],
            "blocked_criteria_count": 4,
            "reason": (
                "gpcr evidence surface is locked; bottleneck=broad_gpcr_family_claim_locked; "
                "first_blocked_target=DRD2; root_cause_tags=operator_values_required"
            ),
            "artifact": "gpcr_hard_decoy_surface",
            **_science_action_hints("gpcr"),
        },
        {
            "action_id": "resolve_pocketmd_lite_science_product_surface",
            "status": "science_product_surface_required",
            "surface_family": "pocketmd_lite",
            "bottleneck": "pocketmd_lite_science_product_surface_missing",
            "first_blocked_target": "",
            "root_cause_tags": [],
            "blocked_criteria": [],
            "blocked_criteria_count": 0,
            "reason": (
                "pocketmd_lite science product surface is missing; "
                "bottleneck=pocketmd_lite_science_product_surface_missing"
            ),
            "artifact": str(base_kwargs["evidence_surface_dir"]),
            **_science_action_hints("pocketmd_lite"),
        },
    ]
    surface_paths = {row["surface_id"]: row for row in decision["evidence_surfaces"]}
    assert surface_paths["structural_contact_surface"]["contract_pass"] is True
    assert surface_paths["gpcr_hard_decoy_surface"]["locked"] is True
    assert surface_paths["gpcr_hard_decoy_surface"]["first_blocked_target"] == "DRD2"
    assert surface_paths["gpcr_hard_decoy_surface"]["root_cause_tags"] == [
        "operator_values_required"
    ]
    assert payload["implementation_orchestration"]["cursor_opencode_worker_preflight_pass"] is True
    assert (
        payload["implementation_orchestration"]["summary"]["opencode_configured_model"]
        == "opencode-go/deepseek-v4-pro"
    )
    assert payload["implementation_orchestration"]["summary"]["opencode_configured_model_available"] is True
    assert payload["implementation_orchestration"]["summary"]["opencode_assignment_routed_to_cursor"] is True
    assert payload["implementation_orchestration"]["summary"]["opencode_assignment_cursor_model"] == "composer-2.5"
    assert payload["gap_ledger_status"]["full_gap_ledger_status"] == "open"
    assert payload["gap_ledger_status"]["commercial_gap_status"] == "open"
    assert payload["gap_ledger_status"]["commercial_solver_gap_ready"] is False
    assert payload["gap_ledger_status"]["ai_engine_gap_ready"] is True
    assert payload["gap_ledger_status"]["next_locally_closable_gaps"] == ["G1"]
    assert "G1:direct_residual_newton_not_closed" in payload["gap_ledger_status"]["blockers"]
    basic_ci_area = next(row for row in payload["release_area_matrix"] if row["area"] == "basic_ci")
    assert basic_ci_area["summary"]["pr_missing_consecutive_pass_count"] == 0
    assert basic_ci_area["summary"]["pr_pull_request_run_source_present"] is True
    assert basic_ci_area["checks"]["ci_streak_intake_contract_pass"] is True
    assert basic_ci_area["checks"]["ci_streak_source_evidence_pass"] is True
    assert basic_ci_area["summary"]["pr_source_evidence_release_credit_pass"] is True
    assert basic_ci_area["summary"]["nightly_source_evidence_release_credit_pass"] is True
    assert basic_ci_area["summary"]["pr_local_required_trigger_present"] is True
    assert basic_ci_area["summary"]["nightly_local_required_trigger_present"] is True
    assert basic_ci_area["summary"]["pr_local_workflow_trigger_events"] == ["pull_request", "push"]
    assert basic_ci_area["summary"]["nightly_local_workflow_trigger_events"] == [
        "schedule",
        "workflow_dispatch",
    ]
    assert basic_ci_area["summary"]["pr_github_actions_workflow_state"] == "active"
    assert basic_ci_area["summary"]["pr_owner_action"].startswith("No release action required")
    assert "tracked PR CI evidence" in basic_ci_area["claim_boundary"]
    assert basic_ci_area["artifacts"]["ci_streak_intake_packet"].endswith("ci_streak_intake_packet.json")
    freshness_area = next(row for row in payload["release_area_matrix"] if row["area"] == "evidence_freshness")
    assert freshness_area["ok"] is True
    assert freshness_area["checks"]["release_evidence_freshness_contract_pass"] is True
    assert freshness_area["summary"]["artifact_count"] == 3
    core_area = next(row for row in payload["release_area_matrix"] if row["area"] == "core_engine")
    assert core_area["summary"]["p95_evidence_source"] == "core_family_p95_accuracy_report"
    assert core_area["summary"]["max_family_p95_error_pct"] == 3.5
    ux_area = next(row for row in payload["release_area_matrix"] if row["area"] == "ux")
    assert ux_area["summary"]["ux_evidence_source"] == "ux_release_readiness_report"
    assert ux_area["summary"]["blocking_review_item_count"] == 0
    assert ux_area["summary"]["automated_sample_completion_minutes"] == 2.0
    assert ux_area["summary"]["sample_completion_minutes"] == 24.0
    assert ux_area["checks"]["human_new_user_observation_pass"] is True
    assert ux_area["checks"]["human_new_user_sample_30min_pass"] is True
    security_area = next(row for row in payload["release_area_matrix"] if row["area"] == "security")
    assert security_area["summary"]["license_status_template_path"] == "docs/templates/license_status.template.json"
    assert security_area["checks"]["frontend_dependency_audit_pass"] is True
    assert security_area["summary"]["frontend_dependency_vulnerability_total"] == 0
    support_area = next(row for row in payload["release_area_matrix"] if row["area"] == "support")
    assert support_area["checks"]["ci_streak_intake_packet_in_failure_bundle"] is True
    assert support_area["checks"]["ci_streak_manifest_in_failure_bundle"] is True
    assert support_area["checks"]["github_actions_ci_streak_evidence_in_failure_bundle"] is True
    assert support_area["checks"]["license_status_intake_packet_in_failure_bundle"] is True
    assert support_area["checks"]["license_status_closure_report_in_failure_bundle"] is True
    assert support_area["checks"]["license_status_template_in_failure_bundle"] is True
    assert support_area["checks"]["pm_blocker_action_register_in_failure_bundle"] is True
    assert support_area["checks"]["pm_blocker_closure_board_in_failure_bundle"] is True
    assert support_area["checks"]["pm_release_gate_completion_audit_in_failure_bundle"] is True
    assert support_area["checks"]["pm_release_gate_reviewer_handoff_in_failure_bundle"] is True
    assert support_area["checks"]["pm_owner_evidence_request_packet_in_failure_bundle"] is True
    assert support_area["checks"]["pm_failure_bundle_coverage_index_pass"] is True
    assert support_area["checks"]["pm_blocker_action_register_handoff_ready_pass"] is True
    assert support_area["checks"]["pm_blocker_closure_board_handoff_ready_pass"] is True
    assert support_area["checks"]["pm_blocker_closure_board_register_count_match"] is True
    assert support_area["checks"]["frontend_dependency_audit_in_failure_bundle"] is True
    assert support_area["checks"]["validation_manual_in_failure_bundle"] is True
    assert support_area["checks"]["limitation_manual_in_failure_bundle"] is True
    assert support_area["checks"]["ux_new_user_observation_report_in_failure_bundle"] is True
    assert support_area["checks"]["ux_new_user_observation_intake_packet_in_failure_bundle"] is True
    assert support_area["checks"]["template_evidence_safety_report_present"] is True
    assert support_area["checks"]["template_evidence_safety_pass"] is True
    assert support_area["checks"]["template_evidence_safety_report_in_failure_bundle"] is True
    assert support_area["checks"]["pm_release_reproduction_command_audit_present"] is True
    assert support_area["checks"]["pm_release_reproduction_command_audit_pass"] is True
    assert support_area["checks"]["pm_release_reproduction_command_audit_in_failure_bundle"] is True
    assert support_area["checks"]["one_click_failure_bundle_archive_present"] is True
    assert support_area["checks"]["failure_bundle_archive_roundtrip_pass"] is True
    assert support_area["checks"]["known_issue_or_limitation_register_content_pass"] is True
    assert support_area["summary"]["license_status_intake_packet"].endswith("license_status_intake_packet.json")
    assert support_area["summary"]["ci_streak_intake_packet"].endswith("ci_streak_intake_packet.json")
    assert support_area["summary"]["ci_streak_manifest"].endswith("ci_streak_manifest.json")
    assert support_area["summary"]["github_actions_ci_streak_evidence"].endswith(
        "github_actions_ci_streak_evidence.json"
    )
    assert support_area["summary"]["license_status_closure_report"].endswith("license_status_closure_report.json")
    assert support_area["summary"]["license_status_template"].endswith("license_status_template.json")
    assert support_area["summary"]["frontend_dependency_audit_report"].endswith("frontend_dependency_audit_report.json")
    assert support_area["summary"]["pm_release_blocker_action_register"].endswith(
        "pm_release_blocker_action_register.json"
    )
    assert support_area["summary"]["pm_release_blocker_closure_board"].endswith(
        "pm_release_blocker_closure_board.json"
    )
    assert support_area["summary"]["pm_release_gate_completion_audit"].endswith(
        "pm_release_gate_completion_audit.json"
    )
    assert support_area["summary"]["pm_release_gate_reviewer_handoff"].endswith(
        "pm_release_gate_reviewer_handoff.json"
    )
    assert support_area["summary"]["pm_owner_evidence_request_packet"].endswith(
        "pm_owner_evidence_request_packet.json"
    )
    assert support_area["summary"]["pm_failure_bundle_coverage_index"].endswith(
        "pm_failure_bundle_coverage.json"
    )
    assert support_area["summary"]["pm_failure_bundle_coverage_index_sha256"] == "pm-failure-bundle-coverage-sha256"
    assert support_area["summary"]["pm_blocker_register_handoff_not_ready_count"] == 0
    assert support_area["summary"]["pm_blocker_closure_board_handoff_not_ready_count"] == 0
    assert support_area["summary"]["release_validation_manual"].endswith("release_validation_manual.md")
    assert support_area["summary"]["release_limitation_manual"].endswith("release_limitation_manual.md")
    assert support_area["summary"]["ux_new_user_observation_report"].endswith(
        "ux_new_user_observation_report.json"
    )
    assert support_area["summary"]["ux_new_user_observation_intake_packet"].endswith(
        "ux_new_user_observation_intake_packet.json"
    )
    assert support_area["summary"]["template_evidence_safety_report"].endswith(
        "template_evidence_safety_report.json"
    )
    assert support_area["summary"]["template_evidence_safety_report_bundle_path"].endswith(
        "template_evidence_safety_report.json"
    )
    assert support_area["summary"]["pm_release_reproduction_command_audit"].endswith(
        "pm_release_reproduction_command_audit.json"
    )
    assert support_area["summary"]["pm_release_reproduction_command_audit_command_count"] == 42
    assert support_area["summary"]["pm_release_reproduction_command_audit_violation_count"] == 0
    assert support_area["summary"]["pm_release_reproduction_command_audit_bundle_path"].endswith(
        "pm_release_reproduction_command_audit.json"
    )
    assert support_area["summary"]["one_click_failure_bundle_archive"].endswith("support_bundle_export.zip")
    assert support_area["summary"]["one_click_failure_bundle_archive_sha256"] == "support-bundle-sha256"
    assert support_area["summary"]["pm_blocker_register_open_blocker_count"] == 16
    assert support_area["summary"]["pm_blocker_register_release_area_blocker_count"] == 5
    assert support_area["summary"]["pm_blocker_closure_board_open_blocker_count"] == 16
    m5 = next(row for row in payload["milestones"] if row["milestone"] == "M5")
    assert m5["checks"]["validation_manual_content_pass"] is True
    assert m5["checks"]["limitation_manual_content_pass"] is True
    assert m5["checks"]["support_bundle_ci_streak_manifest_present"] is True
    assert m5["checks"]["support_bundle_github_actions_ci_streak_evidence_present"] is True
    assert m5["checks"]["support_bundle_license_status_closure_present"] is True
    assert m5["checks"]["support_bundle_license_status_template_present"] is True
    assert m5["checks"]["pm_blocker_register_handoff_ready_pass"] is True
    assert m5["checks"]["support_bundle_pm_blocker_closure_board_present"] is True
    assert m5["checks"]["support_bundle_pm_release_gate_completion_audit_present"] is True
    assert m5["checks"]["support_bundle_pm_release_gate_reviewer_handoff_present"] is True
    assert m5["checks"]["support_bundle_pm_owner_evidence_request_packet_present"] is True
    assert m5["checks"]["support_bundle_pm_failure_bundle_coverage_pass"] is True
    assert m5["checks"]["pm_blocker_closure_board_handoff_ready_pass"] is True
    assert m5["checks"]["pm_blocker_closure_board_register_count_match"] is True
    assert m5["summary"]["support_bundle_pm_failure_bundle_coverage"].endswith(
        "pm_failure_bundle_coverage.json"
    )
    assert m5["summary"]["pm_blocker_register_handoff_not_ready_count"] == 0
    assert m5["summary"]["pm_blocker_closure_board_handoff_not_ready_count"] == 0
    assert m5["checks"]["support_bundle_validation_manual_present"] is True
    assert m5["checks"]["support_bundle_limitation_manual_present"] is True
    assert m5["checks"]["support_bundle_ux_new_user_observation_present"] is True
    assert m5["checks"]["support_bundle_ux_new_user_observation_intake_present"] is True
    assert m5["checks"]["template_evidence_safety_report_present"] is True
    assert m5["checks"]["template_evidence_safety_pass"] is True
    assert m5["checks"]["support_bundle_template_evidence_safety_report_present"] is True
    assert m5["checks"]["pm_release_reproduction_command_audit_present"] is True
    assert m5["checks"]["pm_release_reproduction_command_audit_pass"] is True
    assert m5["checks"]["support_bundle_pm_release_reproduction_command_audit_present"] is True
    assert m5["checks"]["support_bundle_commercial_gap_ledger_status_present"] is True
    assert m5["checks"]["support_bundle_gap_closure_status_present"] is True
    assert m5["summary"]["support_bundle_commercial_gap_ledger_status"].endswith(
        "commercial_gap_ledger_status.json"
    )
    assert m5["summary"]["support_bundle_gap_closure_status"].endswith("gap_closure_status.json")
    assert m5["summary"]["pm_release_reproduction_command_audit_command_count"] == 42
    assert m5["summary"]["pm_release_reproduction_command_audit_violation_count"] == 0
    assert m5["summary"]["release_evidence_freshness"].endswith("release_evidence_freshness_report.json")
    assert m5["summary"]["release_evidence_freshness_contract_pass"] is True
    assert m5["summary"]["release_evidence_freshness_blocker_count"] == 0
    assert m5["summary"]["pm_blocker_register_open_blocker_count"] == 16
    assert m5["summary"]["pm_blocker_register_release_area_blocker_count"] == 5
    assert m5["summary"]["pm_blocker_closure_board_open_blocker_count"] == 16
    assert m5["artifacts"]["release_evidence_freshness"].endswith("release_evidence_freshness_report.json")
    assert m5["checks"]["support_bundle_one_click_archive_present"] is True
    assert payload["ga_enterprise_ready"] is False
    assert payload["release_tiers"]["ga_enterprise_evidence_gate_pass"] is False
    assert payload["release_tiers"]["ga_enterprise_readiness_report"].endswith("ga_enterprise_readiness.json")
    assert payload["release_tiers"]["ga_enterprise_signoff_intake_packet"].endswith(
        "ga_enterprise_signoff_intake.json"
    )
    assert "signoffs=0/3" in payload["release_tiers"]["ga_enterprise_signoff_intake_summary_line"]
    assert payload["release_tiers"]["fresh_full_validation_ready"] is False
    assert payload["release_tiers"]["fresh_full_validation_lane_status"].endswith(
        "fresh_full_validation_lane_status.json"
    )
    assert payload["release_tiers"]["fresh_full_validation_summary"]["lane_contract_pass_count"] == 8
    assert payload["release_tiers"]["fresh_full_validation_summary"]["fresh_validation_receipt_pass_count"] == 0
    assert payload["release_tiers"]["customer_shadow_completed_project_ready"] is False
    assert payload["release_tiers"]["customer_shadow_evidence_status"].endswith(
        "customer_shadow_evidence_status.json"
    )
    assert payload["release_tiers"]["customer_shadow_summary"]["completed_shadow_case_count"] == 0
    assert payload["release_tiers"]["customer_shadow_summary"]["min_completed_shadow_cases"] == 3
    assert "independent_vv_missing" in payload["release_tiers"]["ga_enterprise_blockers"]
    assert (
        "customer_shadow::completed_shadow_case_count_below_minimum"
        in payload["release_tiers"]["ga_enterprise_blockers"]
    )
    assert (
        "fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing"
        in payload["release_tiers"]["ga_enterprise_blockers"]
    )
    assert payload["blockers"] == []
    assert payload["release_area_blockers"] == []

    missing_freshness_kwargs = dict(base_kwargs)
    missing_freshness_kwargs["release_evidence_freshness"] = tmp_path / "missing_freshness.json"
    payload_missing_freshness = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **missing_freshness_kwargs,
    )
    freshness_area = next(
        row for row in payload_missing_freshness["release_area_matrix"] if row["area"] == "evidence_freshness"
    )
    assert freshness_area["ok"] is False
    assert freshness_area["blockers"] == ["release_evidence_freshness_report_missing"]
    assert (
        "evidence_freshness::release_evidence_freshness_report_missing"
        in payload_missing_freshness["release_area_blockers"]
    )
    assert payload_missing_freshness["release_area_gate_ready"] is False

    stale_freshness_kwargs = dict(base_kwargs)
    stale_freshness_kwargs["release_evidence_freshness"] = _write(
        tmp_path / "stale_release_evidence_freshness_report.json",
        {
            "contract_pass": False,
            "reason_code": "ERR_STALE_SOURCE_OF_TRUTH",
            "summary": {"artifact_count": 3, "pass_count": 1, "blocker_count": 2},
            "blockers": ["accuracy_parity_scorecard_stale", "goal_readiness_rollup_missing_source_tracking"],
        },
    )
    payload_stale_freshness = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **stale_freshness_kwargs,
    )
    stale_decision = payload_stale_freshness["release_decision"]
    assert stale_decision["release_allowed"] is False
    assert stale_decision["stale_artifact_count"] == 2
    assert stale_decision["stale_artifact_refresh_required"] is True
    assert stale_decision["operator_actions"] == [
        {
            "action_id": "refresh_release_evidence_freshness",
            "status": "refresh_required",
            "reason": "release_evidence_freshness_report has stale or incomplete source-of-truth blockers",
            "artifact": "release_evidence_freshness_report",
        },
        {
            "action_id": "resolve_h_bond_evidence_surface",
            "status": "science_evidence_required",
            "surface_family": "h_bond",
            "bottleneck": "h_bond_evidence_surface_missing",
            "first_blocked_target": "",
            "root_cause_tags": [],
            "blocked_criteria": [],
            "blocked_criteria_count": 0,
            "reason": "h_bond evidence surface is missing; bottleneck=h_bond_evidence_surface_missing",
            "artifact": str(base_kwargs["evidence_surface_dir"]),
            **_science_action_hints("h_bond"),
        },
        {
            "action_id": "resolve_gpcr_evidence_surface",
            "status": "science_evidence_required",
            "surface_family": "gpcr",
            "bottleneck": "broad_gpcr_family_claim_locked",
            "first_blocked_target": "DRD2",
            "root_cause_tags": ["operator_values_required"],
            "blocked_criteria": [
                "ranking_pr_auc_ci_low_min",
                "top20_hit_rate_min",
                "decoys_above_positive_count_max",
                "no_positive_out_anchored_by_top_decoys",
            ],
            "blocked_criteria_count": 4,
            "reason": (
                "gpcr evidence surface is locked; bottleneck=broad_gpcr_family_claim_locked; "
                "first_blocked_target=DRD2; root_cause_tags=operator_values_required"
            ),
            "artifact": "gpcr_hard_decoy_surface",
            **_science_action_hints("gpcr"),
        },
        {
            "action_id": "resolve_pocketmd_lite_science_product_surface",
            "status": "science_product_surface_required",
            "surface_family": "pocketmd_lite",
            "bottleneck": "pocketmd_lite_science_product_surface_missing",
            "first_blocked_target": "",
            "root_cause_tags": [],
            "blocked_criteria": [],
            "blocked_criteria_count": 0,
            "reason": (
                "pocketmd_lite science product surface is missing; "
                "bottleneck=pocketmd_lite_science_product_surface_missing"
            ),
            "artifact": str(base_kwargs["evidence_surface_dir"]),
            **_science_action_hints("pocketmd_lite"),
        },
    ]

    ci_gap_kwargs = dict(base_kwargs)
    ci_gap_kwargs["ci_pr"] = _write(
        tmp_path / "ci_gap" / "ci_pr.json",
        {"reason_code": "PASS", "summary": {"pass_streak_count": 2}},
    )
    ci_gap_kwargs["ci_streak_manifest"] = _write(
        tmp_path / "ci_gap" / "ci_streak_manifest.json",
        {
            "schema_version": "ci-consecutive-pass-manifest.v1",
            "threshold": 30,
            "contract_pass": False,
            "evidence_sources": {"github_actions_evidence_path": "github_actions_ci_streak_evidence.json"},
            "lanes": {
                "pr": {
                    "consecutive_pass_count": 2,
                    "local_consecutive_pass_count": 2,
                    "github_actions_consecutive_pass_count": 0,
                    "pull_request_run_source_present": False,
                    "missing_consecutive_pass_count": 28,
                    "threshold_pass": False,
                    "owner_action": "No pull_request-triggered CI runs have been observed.",
                    "claim_boundary": "Local PR gate reports prove command-level readiness; release streak credit requires tracked PR CI evidence for the consecutive-pass window.",
                },
                "nightly": {
                    "consecutive_pass_count": 30,
                    "local_consecutive_pass_count": 30,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 0,
                    "threshold_pass": True,
                    "owner_action": "No release action required; consecutive pass threshold is satisfied.",
                    "claim_boundary": "Local nightly artifacts prove command-level readiness; release streak credit requires tracked nightly CI evidence for the consecutive-pass window.",
                },
            },
        },
    )
    ci_gap_kwargs["ci_streak_intake_packet"] = _write(
        tmp_path / "ci_gap" / "ci_streak_intake_packet.json",
        {
            "schema_version": "ci-streak-intake-packet.v1",
            "contract_pass": False,
            "reason_code": "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE",
            "summary": {
                "threshold": 30,
                "lane_pass_count": 1,
                "source_evidence_pass": False,
                "source_evidence_freshness_pass": True,
                "pr_missing_consecutive_pass_count": 30,
                "nightly_missing_consecutive_pass_count": 0,
                "pr_pull_request_run_source_present": False,
            },
            "source_evidence": {
                "contract_pass": False,
                "generated_at": "2026-06-16T00:00:00+00:00",
                "age_hours": 1.0,
                "freshness_pass": True,
                "lanes": {
                    "pr": {
                        "source_release_credit_pass": False,
                        "workflow_state": "active",
                    },
                    "nightly": {
                        "source_release_credit_pass": True,
                        "workflow_state": "active",
                    },
                },
            },
            "lane_rows": [
                {
                    "lane": "pr",
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "pull_request_run_source_present": False,
                },
                {
                    "lane": "nightly",
                    "threshold": 30,
                    "threshold_pass": True,
                    "consecutive_pass_count": 30,
                },
            ],
        },
    )
    payload_with_ci_gap = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **ci_gap_kwargs,
    )
    ci_gap_area = next(row for row in payload_with_ci_gap["release_area_matrix"] if row["area"] == "basic_ci")

    assert payload_with_ci_gap["release_area_gate_ready"] is False
    assert "basic_ci::pr_ci_30_consecutive_pass_evidence_missing" in payload_with_ci_gap["release_area_blockers"]
    assert ci_gap_area["summary"]["pr_missing_consecutive_pass_count"] == 30
    assert ci_gap_area["summary"]["pr_pull_request_run_source_present"] is False
    assert ci_gap_area["checks"]["ci_streak_source_evidence_pass"] is False
    assert ci_gap_area["summary"]["pr_source_evidence_release_credit_pass"] is False
    assert ci_gap_area["summary"]["pr_owner_action"].startswith("No pull_request-triggered CI runs")
    assert "tracked PR CI evidence" in ci_gap_area["summary"]["pr_claim_boundary"]

    _write(base_kwargs["ci_require_hip"], {"reason_code": "ERR_HIP_KERNEL_SMOKE_FAIL"})
    payload_with_stale_strict_ci = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **base_kwargs,
    )

    assert payload_with_stale_strict_ci["limited_commercial_milestone_ready"] is True
    assert payload_with_stale_strict_ci["limited_commercial_release_ready"] is False
    assert payload_with_stale_strict_ci["limited_commercial_ready"] is False
    assert payload_with_stale_strict_ci["release_area_gate_ready"] is False
    assert (
        "strict_ci::strict_ci_require_hip_artifact_failed_or_stale"
        in payload_with_stale_strict_ci["release_area_blockers"]
    )


def test_pm_release_gate_cli_writes_default_markdown_next_to_json(tmp_path: Path) -> None:
    ndtha = _write(
        tmp_path / "release_evidence" / "productization" / "ndtha_residual_gate_report.json",
        {
            "contract_pass": True,
            "checks": {
                "ndtha_no_collapse_pass": True,
                "residual_top_hard_pass": True,
                "residual_drift_hard_pass": True,
                "recommended_residual_pass": True,
                "strict_recommended_residual_hard_fail_enabled": True,
                "strict_recommended_residual_pass": True,
                "corrected_state_recompute_pass": True,
                "solver_control_rollup_pass": True,
            },
            "summary": {
                "case_count": 12,
                "fallback_rate": 0.01,
                "solver_raw_ratio": 0.99,
                "corrected_state_recompute_required": True,
                "corrected_state_recompute_present_count": 12,
                "corrected_state_recompute_pass_count": 12,
                "solver_control_nonconverged_step_total": 0,
            },
            "rows": [{"normalized_residual": {"recommended_max_ratio": 0.1}}],
        },
    )
    element = _write(
        tmp_path / "element.json",
        {
            "contract_pass": True,
            "checks": {
                "structural_contact_direct_contract_pass": True,
                "foundation_soil_link_direct_contract_pass": True,
                "panel_contact_failure_mode_reason_code_pass": True,
            },
            "summary": {
                "contact_material_coupled_case_count": 10,
                "nonlinear_residual_integrated_case_count": 2,
                "material_model_types": ["rc_composite", "steel_elastic_plastic", "composite_steel_rc"],
            },
        },
    )
    breadth = _write(
        tmp_path / "breadth.json",
        {
            "contract_pass": True,
            "summary": {
                "measured_case_count": 150,
                "measured_family_count": 6,
                "holdout_family_count": 6,
                "baseline_measured_case_count": 50,
                "opensees_incremental_case_count": 20,
            },
        },
    )
    worst = _write(tmp_path / "worst.json", {"contract_pass": True})
    out = tmp_path / "evidence" / "pm_release_gate_report.json"
    argv = [
        "--ndtha-residual",
        str(ndtha),
        "--element-material-breadth",
        str(element),
        "--measured-benchmark-breadth",
        str(breadth),
        "--worst-case-report",
        str(worst),
        "--out",
        str(out),
    ]
    for key, value in _base_kwargs(tmp_path).items():
        argv.extend([f"--{key.replace('_', '-')}", str(value)])

    assert report_pm_release_gate.main(argv) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out.with_suffix(".md").read_text(encoding="utf-8")

    assert f"- `summary_line`: `{payload['summary_line']}`" in markdown
    assert "release_areas=READY" in markdown
    assert "- `full_gap_ledger_status`: `open`" in markdown


def test_pm_release_gate_residual_area_consumes_residual_level3_status(tmp_path: Path) -> None:
    ndtha = _write(
        tmp_path / "release_evidence" / "productization" / "ndtha_residual_gate_report.json",
        {
            "contract_pass": True,
            "checks": {
                "ndtha_no_collapse_pass": True,
                "residual_top_hard_pass": True,
                "residual_drift_hard_pass": True,
                "recommended_residual_pass": True,
                "strict_recommended_residual_hard_fail_enabled": True,
                "strict_recommended_residual_pass": True,
                "corrected_state_recompute_pass": True,
                "solver_control_rollup_pass": True,
            },
            "summary": {
                "case_count": 12,
                "fallback_rate": 0.0,
                "solver_raw_ratio": 1.0,
                "corrected_state_recompute_required": True,
                "corrected_state_recompute_present_count": 12,
                "corrected_state_recompute_pass_count": 12,
                "solver_control_nonconverged_step_total": 0,
            },
            "rows": [{"normalized_residual": {"recommended_max_ratio": 0.1}}],
        },
    )
    element = _write(
        tmp_path / "element.json",
        {
            "contract_pass": True,
            "checks": {
                "structural_contact_direct_contract_pass": True,
                "foundation_soil_link_direct_contract_pass": True,
                "panel_contact_failure_mode_reason_code_pass": True,
            },
            "summary": {
                "contact_material_coupled_case_count": 12,
                "nonlinear_residual_integrated_case_count": 2,
                "material_model_types": ["rc_composite", "steel_elastic_plastic", "composite_steel_rc"],
            },
        },
    )
    breadth = _write(
        tmp_path / "breadth.json",
        {
            "contract_pass": True,
            "summary": {
                "measured_case_count": 150,
                "measured_family_count": 6,
                "holdout_family_count": 6,
                "baseline_measured_case_count": 50,
                "opensees_incremental_case_count": 20,
            },
        },
    )
    worst = _write(tmp_path / "worst.json", {"contract_pass": True})

    green_kwargs = dict(_base_kwargs(tmp_path))
    green_kwargs["residual_level3_status"] = _write(
        tmp_path / "green_residual_level3.json",
        {
            "contract_pass": True,
            "status": "ready",
            "reason_code": "PASS",
            "blockers": [],
            "summary": {
                "case_count": 3,
                "hard_pass_rate": 1.0,
                "recommended_pass_rate": 1.0,
                "fallback_rate": 0.0,
                "solver_raw_ratio": 1.0,
            },
        },
    )
    green_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **green_kwargs,
    )
    residual_area = next(row for row in green_payload["release_area_matrix"] if row["area"] == "residual")
    assert residual_area["ok"] is True
    assert residual_area["checks"]["residual_level3_status_present"] is True
    assert residual_area["checks"]["residual_level3_status_green"] is True
    assert residual_area["summary"]["residual_level3_status"] == "ready"
    assert residual_area["summary"]["residual_level3_reason_code"] == "PASS"
    assert residual_area["artifacts"]["residual_level3_status"].endswith("green_residual_level3.json")
    assert residual_area["artifacts"]["ndtha_residual"].endswith("ndtha_residual_gate_report.json")
    assert "residual::residual_level3_status_not_green" not in green_payload["release_area_blockers"]

    blocked_kwargs = dict(_base_kwargs(tmp_path))
    blocked_kwargs["residual_level3_status"] = _write(
        tmp_path / "blocked_residual_level3.json",
        {
            "contract_pass": False,
            "status": "blocked",
            "reason_code": "ERR_RESIDUAL_LEVEL3_INCOMPLETE",
            "blockers": ["fallback_rate_gt_5pct", "normalized_residual_missing"],
        },
    )
    blocked_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **blocked_kwargs,
    )
    blocked_residual_area = next(
        row for row in blocked_payload["release_area_matrix"] if row["area"] == "residual"
    )
    assert blocked_residual_area["ok"] is False
    assert blocked_residual_area["checks"]["residual_level3_status_green"] is False
    assert "residual::residual_level3_status_not_green" in blocked_payload["release_area_blockers"]
    assert "residual::fallback_rate_gt_5pct" in blocked_payload["release_area_blockers"]
    assert "residual::normalized_residual_missing" in blocked_payload["release_area_blockers"]
    assert blocked_residual_area["artifacts"]["residual_level3_status"].endswith(
        "blocked_residual_level3.json"
    )
    assert blocked_payload["release_area_gate_ready"] is False
    assert blocked_payload["full_release_gate_ready"] is False

    missing_kwargs = dict(_base_kwargs(tmp_path))
    missing_kwargs["residual_level3_status"] = tmp_path / "missing_residual_level3.json"
    missing_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **missing_kwargs,
    )
    missing_residual_area = next(
        row for row in missing_payload["release_area_matrix"] if row["area"] == "residual"
    )
    assert missing_residual_area["ok"] is False
    assert missing_residual_area["checks"]["residual_level3_status_present"] is False
    assert "residual::residual_level3_status_missing" in missing_payload["release_area_blockers"]
    assert missing_payload["release_area_gate_ready"] is False


def test_pm_release_gate_github_sync_area_passes_when_preflight_is_synced(
    tmp_path: Path,
) -> None:
    ndtha = _write(
        tmp_path / "release_evidence" / "productization" / "ndtha_residual_gate_report.json",
        {
            "contract_pass": True,
            "checks": {
                "ndtha_no_collapse_pass": True,
                "residual_top_hard_pass": True,
                "residual_drift_hard_pass": True,
                "recommended_residual_pass": True,
                "strict_recommended_residual_hard_fail_enabled": True,
                "strict_recommended_residual_pass": True,
                "corrected_state_recompute_pass": True,
                "solver_control_rollup_pass": True,
            },
            "summary": {
                "case_count": 12,
                "fallback_rate": 0.0,
                "solver_raw_ratio": 1.0,
                "corrected_state_recompute_required": True,
                "corrected_state_recompute_present_count": 12,
                "corrected_state_recompute_pass_count": 12,
                "solver_control_nonconverged_step_total": 0,
            },
            "rows": [{"normalized_residual": {"recommended_max_ratio": 0.1}}],
        },
    )
    element = _write(
        tmp_path / "element.json",
        {
            "contract_pass": True,
            "checks": {
                "structural_contact_direct_contract_pass": True,
                "foundation_soil_link_direct_contract_pass": True,
                "panel_contact_failure_mode_reason_code_pass": True,
            },
            "summary": {
                "contact_material_coupled_case_count": 12,
                "nonlinear_residual_integrated_case_count": 2,
                "material_model_types": ["rc_composite", "steel_elastic_plastic", "composite_steel_rc"],
            },
        },
    )
    breadth = _write(
        tmp_path / "breadth.json",
        {
            "contract_pass": True,
            "summary": {
                "measured_case_count": 150,
                "measured_family_count": 6,
                "holdout_family_count": 6,
                "baseline_measured_case_count": 50,
                "opensees_incremental_case_count": 20,
            },
        },
    )
    worst = _write(tmp_path / "worst.json", {"contract_pass": True})
    base_kwargs = _base_kwargs(tmp_path)

    synced_kwargs = dict(base_kwargs)
    synced_kwargs["github_sync_preflight"] = _write(
        tmp_path / "synced_preflight.json",
        {
            "schema_version": "github-development-sync-preflight.v1",
            "status": "synced",
            "contract_pass": True,
            "preflight_pass": True,
            "remote_mutation_approved": False,
            "remote_sync_needed": False,
            "reason_code": "PASS",
            "blockers": [],
            "state": {
                "feature_ahead_count": 0,
                "main_ahead_count": 0,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": True,
            },
            "checks": {
                "worktree_clean": True,
                "remote_safety_ok": True,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": True,
                "feature_synced_to_head": True,
                "main_synced_to_head": True,
                "explicit_remote_mutation_approval": False,
            },
            "pending_remote_updates": [],
            "r4_disclosure": {
                "target": [],
                "action": "no remote mutation required",
                "risk": "No remote mutation remains.",
            },
            "claim_boundary": "read-only",
        },
    )
    synced_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **synced_kwargs,
    )
    synced_area = next(
        row for row in synced_payload["release_area_matrix"] if row["area"] == "github_sync"
    )
    assert synced_area["ok"] is True
    assert synced_area["status"] == "pass"
    assert synced_area["checks"]["github_sync_preflight_artifact_present"] is True
    assert synced_area["checks"]["github_sync_preflight_clean"] is True
    assert synced_area["checks"]["github_sync_preflight_status"] == "synced"
    assert synced_area["summary"]["pending_remote_update_count"] == 0
    assert synced_area["summary"]["status"] == "synced"
    assert "read-only" in synced_area["claim_boundary"]
    assert synced_area["artifacts"]["github_development_sync_preflight"].endswith(
        "synced_preflight.json"
    )

    approval_kwargs = dict(base_kwargs)
    approval_kwargs["github_sync_preflight"] = _write(
        tmp_path / "approval_required_preflight.json",
        {
            "schema_version": "github-development-sync-preflight.v1",
            "status": "approval_required",
            "contract_pass": False,
            "preflight_pass": True,
            "remote_mutation_approved": False,
            "remote_sync_needed": True,
            "reason_code": "ERR_GITHUB_SYNC_NOT_COMPLETE",
            "blockers": ["remote_mutation_approval_required"],
            "state": {
                "feature_ahead_count": 2,
                "main_ahead_count": 4,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": True,
            },
            "checks": {
                "worktree_clean": True,
                "remote_safety_ok": True,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": True,
                "feature_synced_to_head": False,
                "main_synced_to_head": False,
                "explicit_remote_mutation_approval": False,
            },
            "pending_remote_updates": [
                {"target": "origin/main", "action": "fast-forward push current HEAD to main"}
            ],
            "r4_disclosure": {
                "target": ["origin/main"],
                "action": "fast-forward push current HEAD to main",
                "risk": "Main CI and external reviewers immediately see the current commits.",
            },
            "claim_boundary": "read-only",
        },
    )
    approval_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **approval_kwargs,
    )
    approval_area = next(
        row for row in approval_payload["release_area_matrix"] if row["area"] == "github_sync"
    )
    assert approval_area["ok"] is False
    assert approval_area["status"] == "blocked"
    assert approval_area["checks"]["github_sync_preflight_clean"] is False
    assert approval_area["checks"]["github_sync_remote_mutation_approval_pending"] is True
    assert approval_area["summary"]["remote_mutation_approval_pending"] is True
    assert approval_area["summary"]["pending_remote_update_count"] == 1
    assert approval_area["summary"]["main_ahead_count"] == 4
    assert approval_area["artifacts"]["github_development_sync_preflight"].endswith(
        "approval_required_preflight.json"
    )
    assert (
        "github_sync::github_sync_preflight::remote_mutation_approval_required"
        in approval_payload["release_area_blockers"]
    )
    assert "github_sync::github_sync_remote_sync_pending" in approval_payload["release_area_blockers"]
    assert "github_sync::github_sync_preflight_not_synced" in approval_payload["release_area_blockers"]
    assert approval_payload["release_area_gate_ready"] is False

    missing_kwargs = dict(base_kwargs)
    missing_kwargs["github_sync_preflight"] = tmp_path / "missing_github_sync_preflight.json"
    missing_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **missing_kwargs,
    )
    missing_area = next(
        row for row in missing_payload["release_area_matrix"] if row["area"] == "github_sync"
    )
    assert missing_area["ok"] is False
    assert missing_area["status"] == "blocked"
    assert missing_area["checks"]["github_sync_preflight_artifact_present"] is False
    assert missing_area["checks"]["github_sync_preflight_clean"] is False
    assert missing_area["summary"]["status"] == "missing"
    assert "github_sync::github_sync_preflight_report_missing" in missing_payload["release_area_blockers"]
    assert missing_payload["release_area_gate_ready"] is False

    blocked_kwargs = dict(base_kwargs)
    blocked_kwargs["github_sync_preflight"] = _write(
        tmp_path / "blocked_preflight.json",
        {
            "schema_version": "github-development-sync-preflight.v1",
            "status": "blocked",
            "contract_pass": False,
            "preflight_pass": False,
            "remote_mutation_approved": False,
            "remote_sync_needed": False,
            "reason_code": "ERR_GITHUB_SYNC_NOT_COMPLETE",
            "blockers": [
                "worktree_not_clean",
                "main_remote_not_ancestor_of_head",
                "remote_safety_failed",
            ],
            "state": {
                "feature_ahead_count": 0,
                "main_ahead_count": 0,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": False,
            },
            "checks": {
                "worktree_clean": False,
                "remote_safety_ok": False,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": False,
            },
            "pending_remote_updates": [],
            "r4_disclosure": {"target": [], "action": "no remote mutation required", "risk": ""},
            "claim_boundary": "read-only",
        },
    )
    blocked_payload = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **blocked_kwargs,
    )
    blocked_area = next(
        row for row in blocked_payload["release_area_matrix"] if row["area"] == "github_sync"
    )
    assert blocked_area["ok"] is False
    assert blocked_area["status"] == "blocked"
    assert blocked_area["checks"]["github_sync_preflight_artifact_present"] is True
    assert blocked_area["checks"]["github_sync_preflight_clean"] is False
    assert blocked_area["checks"]["github_sync_worktree_clean"] is False
    assert blocked_area["checks"]["github_sync_remote_safety_ok"] is False
    assert blocked_area["checks"]["github_sync_main_fast_forward_possible"] is False
    assert (
        "github_sync::github_sync_preflight::worktree_not_clean"
        in blocked_payload["release_area_blockers"]
    )
    assert (
        "github_sync::github_sync_preflight::main_remote_not_ancestor_of_head"
        in blocked_payload["release_area_blockers"]
    )
    assert (
        "github_sync::github_sync_preflight::remote_safety_failed"
        in blocked_payload["release_area_blockers"]
    )
    assert blocked_payload["release_area_gate_ready"] is False
    assert blocked_payload["full_release_gate_ready"] is False


def test_pm_release_gate_cli_defaults_to_tracked_github_sync_preflight() -> None:
    args = report_pm_release_gate.build_parser().parse_args([])

    assert (
        args.github_sync_preflight
        == report_pm_release_gate.DEFAULT_GITHUB_DEVELOPMENT_SYNC_PREFLIGHT
    )
    assert args.github_sync_live_state is False


def test_pm_release_gate_github_sync_blocks_stale_preflight_head(
    tmp_path: Path,
) -> None:
    stale_preflight = _write(
        tmp_path / "stale_preflight.json",
        {
            "schema_version": "github-development-sync-preflight.v1",
            "status": "synced",
            "contract_pass": True,
            "preflight_pass": True,
            "remote_mutation_approved": False,
            "remote_sync_needed": False,
            "reason_code": "PASS",
            "blockers": [],
            "state": {
                "local_head_sha": "not-the-current-head",
                "remote_feature_ref": "origin/feature",
                "remote_main_ref": "origin/main",
                "feature_ahead_count": 0,
                "main_ahead_count": 0,
            },
            "checks": {
                "worktree_clean": True,
                "remote_safety_ok": True,
                "feature_fast_forward_possible": True,
                "main_fast_forward_possible": True,
                "feature_synced_to_head": True,
                "main_synced_to_head": True,
                "explicit_remote_mutation_approval": False,
            },
            "pending_remote_updates": [],
            "r4_disclosure": {"risk": "No remote mutation remains."},
            "claim_boundary": "read-only",
        },
    )

    area = report_pm_release_gate._github_sync_area(stale_preflight)

    assert area["ok"] is False
    assert area["status"] == "blocked"
    assert area["checks"]["github_sync_preflight_head_matches_current"] is False
    assert area["checks"]["github_sync_preflight_source_state_fresh"] is False
    assert "github_sync_preflight::local_head_mismatch" in area["blockers"]
    assert area["summary"]["preflight_local_head_sha"] == "not-the-current-head"
    assert area["summary"]["current_head_sha"] == report_pm_release_gate._git_head()
    assert area["summary"]["preflight_source_state_kind"] == "unresolved_preflight_head"


def test_github_sync_preflight_source_state_allows_evidence_only_delta(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        report_pm_release_gate,
        "_git_rev_parse",
        lambda value: {"old": "old-sha", "new": "new-sha"}.get(value, ""),
    )
    monkeypatch.setattr(
        report_pm_release_gate,
        "_git_diff_name_only",
        lambda source, current: [
            "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
            "implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        ],
    )

    fresh, kind, changed_paths = report_pm_release_gate._github_sync_preflight_source_state(
        "old", "new"
    )

    assert fresh is True
    assert kind == "evidence_only_delta"
    assert changed_paths == [
        "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
        "implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
    ]


def test_github_sync_preflight_source_state_blocks_source_delta(monkeypatch) -> None:
    monkeypatch.setattr(
        report_pm_release_gate,
        "_git_rev_parse",
        lambda value: {"old": "old-sha", "new": "new-sha"}.get(value, ""),
    )
    monkeypatch.setattr(
        report_pm_release_gate,
        "_git_diff_name_only",
        lambda source, current: [
            "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
            "scripts/report_pm_release_gate.py",
        ],
    )

    fresh, kind, changed_paths = report_pm_release_gate._github_sync_preflight_source_state(
        "old", "new"
    )

    assert fresh is False
    assert kind == "source_delta"
    assert changed_paths == ["scripts/report_pm_release_gate.py"]
