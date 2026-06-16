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
                    "redaction_self_test_pass": True,
                    "bundle_roundtrip_test_pass": True,
                    "missing_required_count": 0,
                },
                "optional_sections": {
                    "ci_streak_intake_packet": "release/support_bundle/redacted/ci_streak_intake_packet.json",
                    "license_status_intake_packet": "release/support_bundle/redacted/license_status_intake_packet.json",
                    "pm_release_blocker_action_register": "release/support_bundle/redacted/pm_release_blocker_action_register.json",
                    "frontend_dependency_audit_report": (
                        "release/support_bundle/redacted/frontend_dependency_audit_report.json"
                    ),
                },
            },
        ),
        "validation_manual": _text(tmp_path / "validation.md"),
        "limitation_manual": _text(tmp_path / "limitations.md"),
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
    }


def _base_kwargs(tmp_path: Path) -> dict[str, Path]:
    kwargs = {}
    kwargs.update(_runtime_inputs(tmp_path))
    kwargs.update(_packaging_inputs(tmp_path))
    kwargs.update(_release_area_inputs(tmp_path))
    return kwargs


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
    assert payload["limited_commercial_ready"] is True
    assert payload["contract_pass"] is True
    assert payload["release_area_gate_ready"] is True
    assert payload["full_release_gate_ready"] is True
    assert payload["implementation_orchestration"]["cursor_opencode_worker_preflight_pass"] is True
    basic_ci_area = next(row for row in payload["release_area_matrix"] if row["area"] == "basic_ci")
    assert basic_ci_area["summary"]["pr_missing_consecutive_pass_count"] == 0
    assert basic_ci_area["summary"]["pr_owner_action"].startswith("No release action required")
    assert "tracked PR CI evidence" in basic_ci_area["claim_boundary"]
    assert basic_ci_area["artifacts"]["ci_streak_intake_packet"].endswith("ci_streak_intake_packet.json")
    core_area = next(row for row in payload["release_area_matrix"] if row["area"] == "core_engine")
    assert core_area["summary"]["p95_evidence_source"] == "core_family_p95_accuracy_report"
    assert core_area["summary"]["max_family_p95_error_pct"] == 3.5
    ux_area = next(row for row in payload["release_area_matrix"] if row["area"] == "ux")
    assert ux_area["summary"]["ux_evidence_source"] == "ux_release_readiness_report"
    assert ux_area["summary"]["blocking_review_item_count"] == 0
    assert ux_area["summary"]["sample_completion_minutes"] == 2.0
    security_area = next(row for row in payload["release_area_matrix"] if row["area"] == "security")
    assert security_area["summary"]["license_status_template_path"] == "docs/templates/license_status.template.json"
    assert security_area["checks"]["frontend_dependency_audit_pass"] is True
    assert security_area["summary"]["frontend_dependency_vulnerability_total"] == 0
    support_area = next(row for row in payload["release_area_matrix"] if row["area"] == "support")
    assert support_area["checks"]["ci_streak_intake_packet_in_failure_bundle"] is True
    assert support_area["checks"]["license_status_intake_packet_in_failure_bundle"] is True
    assert support_area["checks"]["pm_blocker_action_register_in_failure_bundle"] is True
    assert support_area["checks"]["frontend_dependency_audit_in_failure_bundle"] is True
    assert support_area["summary"]["license_status_intake_packet"].endswith("license_status_intake_packet.json")
    assert support_area["summary"]["ci_streak_intake_packet"].endswith("ci_streak_intake_packet.json")
    assert support_area["summary"]["frontend_dependency_audit_report"].endswith("frontend_dependency_audit_report.json")
    assert support_area["summary"]["pm_release_blocker_action_register"].endswith(
        "pm_release_blocker_action_register.json"
    )
    assert payload["ga_enterprise_ready"] is False
    assert payload["release_tiers"]["ga_enterprise_evidence_gate_pass"] is False
    assert payload["release_tiers"]["ga_enterprise_readiness_report"].endswith("ga_enterprise_readiness.json")
    assert payload["release_tiers"]["ga_enterprise_signoff_intake_packet"].endswith(
        "ga_enterprise_signoff_intake.json"
    )
    assert "signoffs=0/3" in payload["release_tiers"]["ga_enterprise_signoff_intake_summary_line"]
    assert "independent_vv_missing" in payload["release_tiers"]["ga_enterprise_blockers"]
    assert payload["blockers"] == []
    assert payload["release_area_blockers"] == []

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
                    "missing_consecutive_pass_count": 28,
                    "threshold_pass": False,
                    "owner_action": "Collect 28 additional consecutive successful PR CI run(s); keep the pull_request CI lane green and refresh github_actions_ci_streak_evidence before release signoff.",
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
    assert ci_gap_area["summary"]["pr_missing_consecutive_pass_count"] == 28
    assert ci_gap_area["summary"]["pr_owner_action"].startswith("Collect 28 additional consecutive successful PR CI")
    assert "tracked PR CI evidence" in ci_gap_area["summary"]["pr_claim_boundary"]

    _write(base_kwargs["ci_require_hip"], {"reason_code": "ERR_HIP_KERNEL_SMOKE_FAIL"})
    payload_with_stale_strict_ci = report_pm_release_gate.build_report(
        ndtha_residual=ndtha,
        element_material_breadth=element,
        measured_benchmark_breadth=breadth,
        worst_case_report=worst,
        **base_kwargs,
    )

    assert payload_with_stale_strict_ci["limited_commercial_ready"] is True
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
