from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_product_readiness_snapshot.py"
SPEC = importlib.util.spec_from_file_location("build_product_readiness_snapshot", SCRIPT_PATH)
assert SPEC is not None
build_product_readiness_snapshot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = build_product_readiness_snapshot
SPEC.loader.exec_module(build_product_readiness_snapshot)


SnapshotInputPaths = build_product_readiness_snapshot.SnapshotInputPaths


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _g1_child_hip_refresh_evidence(*, ready: bool = True) -> dict:
    component = {
        "present": True,
        "ready": ready,
        "hip_required": True,
        "promoted_to_final_state": ready,
        "accepted_state_refresh_backend": "hip_full_residual",
        "accepted_state_refresh_hip_used": ready,
        "accepted_state_refresh_cpu_used": False,
    }
    return {
        "schema_version": "g1-child-hip-residual-refresh-evidence.v1",
        "ready": ready,
        "blockers": [] if ready else [
            "child_current_tangent_residual_row_not_promoted_to_final_state"
        ],
        "components": {
            "matrix_free_global_krylov": {
                **component,
                "accepted_state_refresh_backend": "hip_full_residual_resident",
            },
            "current_tangent_residual_row_correction": component,
        },
    }


def _g1_child_gate_evidence(*, ready: bool = True) -> dict:
    return {
        "schema_version": "g1-child-gate-evidence.v1",
        "ready": ready,
        "blockers": [] if ready else [
            "child_direct_residual_gate_not_proven",
            "child_relative_increment_gate_not_proven",
        ],
        "direct_residual_newton_ready": ready,
        "full_load_closure_passed": ready,
        "direct_residual_gate_passed": ready,
        "relative_increment_gate_passed": ready,
        "fallback_zero_passed": ready,
        "material_newton_breadth_passed": ready,
        "consistent_residual_jacobian_newton_passed": ready,
        "observed_load_scale": 1.0 if ready else 0.656,
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "load_scale_passed": ready,
    }


def _g1_hip_consistency_proof(
    *,
    ready: bool = True,
    source_commit_sha: str = "abc123",
) -> dict:
    return {
        "path": "implementation/phase1/release_evidence/productization/"
        "mgt_residual_jacobian_consistency_hip_required_probe.json",
        "present": True,
        "status": "ready" if ready else "partial",
        "source_commit_sha": source_commit_sha,
        "reused_evidence": False,
        "rocm_hip_required": True,
        "execution_mode": (
            "hip_required_production_residual_jacobian"
            if ready
            else "hip_required_runtime_unavailable_no_cpu_fallback"
        ),
        "cpu_diagnostic_assembler_used": False,
        "production_hip_residual_jacobian_path": ready,
        "consistent_residual_jacobian_newton_gate_passed": ready,
        "receipt_blockers": [] if ready else [
            "rocm_hip_runtime_unavailable",
            "hip_residual_jacobian_consistency_not_executed",
        ],
        "runtime_blockers": [] if ready else [
            "dev_kfd_missing",
            "dev_dri_missing",
        ],
    }


def _fresh_validation_rows(count: int = 8) -> list[dict]:
    return [
        {
            "lane_id": f"lane_{index + 1}",
            "pass": True,
            "fresh_validation_receipt_fresh": True,
            "fresh_validation_receipt_contract_pass": True,
            "fresh_validation_receipt_present": True,
            "fresh_validation_receipt_reused_evidence": False,
        }
        for index in range(count)
    ]


def _customer_shadow_rows(count: int = 3) -> list[dict]:
    return [
        {
            "path": f"implementation/phase1/customer_shadow_evidence/case_{index + 1}.json",
            "case_id": f"customer-shadow-case-{index + 1:03d}",
            "project_status": "completed",
            "structure_family": "commercial_building",
            "reference_solver": "customer_retained_reference",
            "reference_solver_version": "owner-retained",
            "reviewer_decision": "PASS",
            "raw_data_retained_by_customer": True,
            "redistribution_allowed": False,
            "contract_pass": True,
            "reason_code": "PASS",
            "blockers": [],
        }
        for index in range(count)
    ]


def _g1_detail_blockers(payload: dict) -> list[str]:
    return payload["components"]["g1"]["suppressed_detail_blockers"]


def _paths(tmp_path: Path) -> SnapshotInputPaths:
    return SnapshotInputPaths(
        readme=Path("README.md"),
        current_state=Path("docs/commercialization-gap-current-state.md"),
        pm_report=Path("pm_release_gate_report.json"),
        gap_closure_status=Path("gap_closure_status.json"),
        commercial_gap_ledger_status=Path("commercial_gap_ledger_status.json"),
        gap_ledger_evidence_audit=Path("gap_ledger_evidence_audit.json"),
        phase1_core_api_contract=Path("phase1_core_api_contract_summary.json"),
        developer_preview_readiness=Path("developer_preview_readiness.json"),
        developer_preview_rc_status=Path("developer_preview_rc_status.json"),
        fresh_full_validation=Path("fresh_full_validation_lane_status.json"),
        g1_terminal_gate=Path("mgt_g1_direct_residual_terminal_gate_report.json"),
        g1_full_load_hip_newton_lane=Path("g1_full_load_hip_newton_lane_report.json"),
        customer_shadow=Path("customer_shadow_evidence_status.json"),
        workstation_delivery=Path("workstation_delivery_readiness.json"),
        independent_product=Path("independent_product_readiness.json"),
        blocker_action_register=Path("pm_release_blocker_action_register.json"),
        github_actions_ci_streak=Path("github_actions_ci_streak_evidence.json"),
        ux_new_user_observation=Path("ux_new_user_observation_report.json"),
        license_status_closure=Path("license_status_closure_report.json"),
        paid_pilot_scope_guard=Path("paid_pilot_scope_guard_report.json"),
        external_benchmark_submission_readiness=Path("external_benchmark_submission_readiness.json"),
        external_benchmark_submission_updates=Path("external_benchmark_submission_updates.json"),
        phase3_release_control_cleanup_plan=Path("phase3_release_control_cleanup_plan.json"),
        self_hosted_runner_status=Path("github_actions_self_hosted_runner_status.json"),
        package_json=Path("package.json"),
        pyproject_toml=Path("pyproject.toml"),
        github_workflows=Path(".github/workflows"),
    )


def _write_common_metadata(tmp_path: Path, *, commit: str = "abc123") -> None:
    _write_json(tmp_path / "gap_closure_status.json", {
        "schema_version": "gap-closure-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"gaps.md": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
    })
    _write_json(tmp_path / "commercial_gap_ledger_status.json", {
        "schema_version": "commercial-gap-ledger-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "engine_version": "structural-analysis-workbench@test",
        "input_checksums": {
            "docs/commercial-structural-solver-product-gap-ledger.md": "sha256:abc123",
            "docs/structural-analysis-ai-engine-gap-ledger.md": "sha256:def456",
            "implementation/phase1/commercial_gap_ledger_status.py": "sha256:789abc",
        },
        "reused_evidence": True,
        "reuse_policy": (
            "summarizes_existing_gap_ledgers_and_productization_receipts; "
            "does_not_create_authoritative_closure_evidence"
        ),
        "status": "closed",
        "commercial_solver_gap_ready": True,
        "ai_engine_guardrail_rows_ready": True,
        "ai_engine_gap_ready": True,
        "autonomous_ai_engine_claim_ready": False,
        "autonomous_ai_engine_claim_blockers": [],
        "full_gap_ledger_ready": True,
        "summary": {
            "total_count": 20,
            "closed_count": 20,
            "partial_count": 0,
            "open_count": 0,
            "external_blocked_count": 0,
            "locally_closable_open_count": 0,
            "locally_closable_nonclosed_count": 0,
            "locally_closable_nonclosed_row_ids": [],
        },
        "blockers": [],
        "next_locally_closable_gaps": [],
        "rows": [
            {
                "id": f"G{index}",
                "ledger": "commercial_solver",
                "status": "closed",
                "closed": True,
                "locally_closable": False,
                "blockers": [],
            }
            for index in range(1, 11)
        ] + [
            {
                "id": f"AI-G{index}",
                "ledger": "ai_engine",
                "status": "closed",
                "closed": True,
                "locally_closable": False,
                "blockers": [],
            }
            for index in range(1, 11)
        ],
    })
    _write_json(tmp_path / "gap_ledger_evidence_audit.json", {
        "schema_version": "gap-ledger-evidence-audit.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"commercial_gap_ledger_status.json": "sha256:abc123"},
        "reused_evidence": True,
        "status": "ready",
        "contract_pass": True,
        "ledger_status": "closed",
        "full_gap_ledger_ready": True,
        "row_count": 20,
        "closed_row_count": 20,
        "nonclosed_row_count": 0,
        "row_outcomes": [
            {
                "id": f"G{index}",
                "ledger": "commercial_solver",
                "closed": True,
                "evidence_present": True,
                "blocker_count": 0,
                "claim_boundary_present": True,
            }
            for index in range(1, 11)
        ] + [
            {
                "id": f"AI-G{index}",
                "ledger": "ai_engine",
                "closed": True,
                "evidence_present": True,
                "blocker_count": 0,
                "claim_boundary_present": True,
            }
            for index in range(1, 11)
        ],
        "blockers": [],
        "claim_boundary": (
            "Fixture audit verifies row evidence visibility only; it does not "
            "create commercial release readiness."
        ),
    })
    _write_json(tmp_path / "phase1_core_api_contract_summary.json", {
        "schema_version": "phase1-core-api-contract-artifacts.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "engine_version": "structural-analysis-workbench@test",
        "input_checksums": {
            "src/structural_analysis/api/core.py": "sha256:abc123",
            "src/structural_analysis/api/cli.py": "sha256:def456",
        },
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "claim_boundary_version": "developer-preview-core-api-v1",
        "invocation_surfaces": ["python_api", "cli", "gui_json_consumption"],
        "supported_preview_analysis_types": [
            "model_health",
            "linear_static_axial_truss",
            "nonlinear_static_material_mesh_axial_chain",
        ],
        "schema_validation": {"contract_pass": True},
        "cli_contract": {
            "contract_pass": True,
            "same_result_schema_as_python_api": True,
            "same_validation_report_schema_as_python_api": True,
        },
        "reference_validation_contract": {
            "contract_pass": True,
            "python_api_blocks_reference_mismatch": True,
            "cli_blocks_reference_mismatch": True,
        },
        "unsupported_feature_count": 0,
        "developer_preview_blocked_field_count": 0,
        "claim_boundary": (
            "Fixture Phase 1 core API contract proves Python/CLI/GUI JSON "
            "schema compatibility only; it does not close commercial solver gaps."
        ),
    })
    _write_json(tmp_path / "developer_preview_readiness.json", {
        "schema_version": "developer-preview-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"developer_preview_inputs.json": "sha256:abc123"},
        "reused_evidence": False,
        "status": "ready",
        "developer_preview_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "future_commercial_blocker_count": 4,
        "future_commercial_blockers": [
            "customer_shadow::future_commercial_only",
            "license::future_commercial_only",
            "sla::future_commercial_only",
            "external_approval::future_commercial_only",
        ],
        "categories": {
            "numerical": {"blocked": False, "blocker_count": 0, "blockers": []},
            "benchmark": {"blocked": False, "blocker_count": 0, "blockers": []},
            "software product": {"blocked": False, "blocker_count": 0, "blockers": []},
            "future commercial": {
                "blocked": True,
                "blocker_count": 4,
                "blockers": [
                    "customer_shadow::future_commercial_only",
                    "license::future_commercial_only",
                    "sla::future_commercial_only",
                    "external_approval::future_commercial_only",
                ],
            },
        },
        "scope": {
            "freeze_policy": {
                "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
                "gpu_hip": "performance_track_after_cpu_reference_parity",
                "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
            },
        },
        "claim_boundary": (
            "Fixture Developer Preview receipt; future Commercial Release blockers "
            "remain visible but do not block the preview."
        ),
    })
    _write_json(tmp_path / "developer_preview_rc_status.json", {
        "schema_version": "developer-preview-rc-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"developer_preview_rc_inputs.json": "sha256:abc123"},
        "reused_evidence": False,
        "status": "ready",
        "contract_pass": True,
        "deliverable_count": 10,
        "deliverable_pass_count": 10,
        "final_gate_count": 9,
        "final_gate_pass_count": 9,
        "blockers": [],
        "claim_boundary": (
            "Fixture Developer Preview RC receipt; component status is informational "
            "inside the paid-pilot snapshot."
        ),
    })
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"workstation_inputs.md": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "claim_boundary": {
            "allowed": (
                "workstation-based structural analysis/optimization deliverable "
                "preparation with engineer review"
            ),
            "forbidden": [
                "independent commercial structural analysis product",
                "structural engineer replacement",
                "full autonomous replacement",
            ],
        },
        "gates": [
            {"label": "Workstation hardware profile", "ok": True},
            {"label": "Workstation service budget", "ok": True},
            {
                "label": "Delivery package manifest",
                "ok": True,
                "manifest_acceptance_reference_pass": True,
                "required_sections": {"ACCEPTANCE_PACKET.md": True},
            },
            {"label": "Customer-open delivery viewer smoke", "ok": True},
            {"label": "Viewer smoke and visual evidence", "ok": True},
            {"label": "Client input validation report", "ok": True},
            {"label": "Job reproducibility contract", "ok": True},
            {"label": "Job retention and cleanup policy", "ok": True},
        ],
        "blockers": [],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"independent_inputs.md": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": [],
    })
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", {
        "schema_version": "github-actions-ci-streak-evidence.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"workflow_runs.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "pr_threshold_pass": True,
            "nightly_threshold_pass": True,
            "pr_consecutive_pass_count": 30,
            "nightly_consecutive_pass_count": 30,
        },
        "lanes": {
            "pr": {"blockers": []},
            "nightly": {"blockers": []},
        },
    })
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"g1_probes.json": "sha256:abc123"},
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "full_load_input_pass": True,
        "hip_consistency_proof": _g1_hip_consistency_proof(source_commit_sha=commit),
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })
    _write_json(tmp_path / "ux_new_user_observation_report.json", {
        "schema_version": "ux-new-user-observation-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"ux_observation.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "completion_minutes": 24.0,
            "max_completion_minutes": 30.0,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "license_status_closure_report.json", {
        "schema_version": "license-status-closure-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"license_status.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"status": "active"},
        "blockers": [],
    })
    _write_json(tmp_path / "paid_pilot_scope_guard_report.json", {
        "schema_version": "paid-pilot-scope-guard-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"scope.md": "sha256:123"},
        "reused_evidence": True,
        "contract_pass": True,
        "reason_code": "PASS",
        "checks": {
            "all_required_scope_terms_present": True,
            "commercial_v1_separate_validation_exclusions_present": True,
            "commercial_v1_supported_scope_present": True,
            "evidence_package_artifacts_present": True,
            "no_prohibited_scope_claims_present": True,
            "required_evidence_package_artifacts_green": True,
            "scope_source_present": True,
            "support_bundle_required_sections_present": True,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"external_benchmark_queue.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 4,
            "submission_receipt_pending_count": 0,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"external_benchmark_updates.json": "sha256:abc123"},
        "reused_evidence": False,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_url": f"https://example.invalid/eb/{idx}",
                "receipt_status": "attached",
                "closure_evidence_status": "attached",
            }
            for idx in range(1, 5)
        },
    })
    _write_json(tmp_path / "phase3_release_control_cleanup_plan.json", {
        "schema_version": "phase3-release-control-cleanup-plan.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "status": "ready",
        "contract_pass": True,
        "candidate_set_source": "",
        "candidate_set_scope": "",
        "current_worktree_diagnostics_included": False,
        "current_worktree_diagnostic_source": "",
        "candidate_release_control_commit_set_count": 0,
        "path_role_counts": {},
        "recommended_action_counts": {},
        "human_git_action_required": False,
        "codex_commit_or_push_performed": False,
        "claim_boundary": "No Phase 3 release-control cleanup is required for this fixture.",
    })
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.0.0",
    })
    _write_json(tmp_path / "github_actions_self_hosted_runner_status.json", {
        "schema_version": "github-actions-self-hosted-runner-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "contract_pass": True,
        "status": "ready",
        "required_labels": ["self-hosted", "linux", "x64"],
        "ready_runner_count": 1,
        "blockers": [],
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.0.0"\n',
    )
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            "'[\"self-hosted\",\"linux\",\"x64\"]') }}\n"
        ),
    )


def _write_stable_non_receipt_inputs(tmp_path: Path) -> None:
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.0.0",
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.0.0"\n',
    )
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            "'[\"self-hosted\",\"linux\",\"x64\"]') }}\n"
        ),
    )


def _write_ready_snapshot_inputs(tmp_path: Path, *, commit: str) -> None:
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"pm_inputs.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
        "release_decision": {
            "release_allowed": True,
            "blocked_release_count": 0,
            "first_blocker": "",
            "operator_action_count": 0,
            "approval_token_count": 0,
            "stale_artifact_count": 0,
            "evidence_surface_count": 2,
            "locked_evidence_surface_count": 0,
            "public_benchmark_ready": True,
            "broad_gpcr_family_claim_safe": False,
        },
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"fresh_validation_inputs.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "rows": _fresh_validation_rows(),
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"customer_shadow_inputs.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "evidence_rows": _customer_shadow_rows(),
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"g1_terminal_inputs.json": "sha256:abc123"},
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": (
            "Full-mesh/full-load physical residual+increment/material Newton gate "
            "is closed with fallback_count=0."
        ),
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
    )
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=tmp_path)


def _commit_all(tmp_path: Path, message: str) -> str:
    subprocess.check_call(["git", "add", "."], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", message], cwd=tmp_path, stdout=subprocess.DEVNULL)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()


def test_snapshot_marks_doc_json_conflicts_stale_or_inconsistent(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `13/16` green. Current action register has `17` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `12/16` green. The open blocker total is `20`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": False,
        "full_release_gate_ready": False,
        "release_area_matrix": [{"ok": True} for _ in range(12)] + [{"ok": False} for _ in range(4)],
        "release_area_blockers": ["basic_ci::missing"],
        "full_release_blockers": ["basic_ci::missing"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 21},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 0, "fresh_validation_receipt_pass_count": 0},
        "blockers": ["commercial_benchmark_torch::fresh_validation_receipt_missing"],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"completed_shadow_case_count": 0, "min_completed_shadow_cases": 3},
        "blockers": ["completed_shadow_case_count_below_minimum"],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "This does not close full-mesh/full-load nonlinear equilibrium.",
    })
    _write_common_metadata(tmp_path, commit=commit)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert "stale_or_inconsistent:release_area_count_conflict" in payload["blockers"]
    assert "stale_or_inconsistent:open_blocker_count_conflict" in payload["blockers"]
    assert "g1::full_load_gate_not_closed" in payload["blockers"]
    assert "g1_full_mesh_full_load_not_closed" in _g1_detail_blockers(payload)
    assert payload["paid_pilot_ready"] is False


def test_snapshot_passes_happy_path_when_all_readiness_inputs_agree(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
        "release_decision": {
            "release_allowed": True,
            "blocked_release_count": 0,
            "first_blocker": "",
            "operator_action_count": 0,
            "approval_token_count": 0,
            "stale_artifact_count": 0,
            "evidence_surface_count": 2,
            "locked_evidence_surface_count": 0,
            "public_benchmark_ready": True,
            "broad_gpcr_family_claim_safe": False,
        },
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "rows": _fresh_validation_rows(),
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "evidence_rows": _customer_shadow_rows(),
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is True
    assert payload["reused_evidence"] is False
    assert (
        payload["reuse_policy"]
        == "product_readiness_snapshot_aggregates_release_readiness_inputs"
    )
    assert payload["aggregator_freshness_policy"]["mode"] == (
        "direct_aggregator_source_tracking"
    )
    assert payload["aggregator_freshness_policy"]["source_artifact_count"] == len(
        payload["input_checksums"]
    )
    assert "scripts/build_product_readiness_snapshot.py" in payload[
        "aggregator_freshness_policy"
    ]["source_artifacts"]
    assert "pm_release_gate_report.json" in payload[
        "aggregator_freshness_policy"
    ]["source_artifacts"]
    assert "fresh_full_validation_lane_status.json" in payload[
        "aggregator_freshness_policy"
    ]["source_artifacts"]
    assert "pm_release_blocker_action_register.json" in payload[
        "aggregator_freshness_policy"
    ]["source_artifacts"]
    assert payload["input_checksums"]["README.md"].startswith("sha256:")
    assert "pm_release_gate_report.json" in payload["input_checksums"]
    assert payload["evidence_fresh"] is True
    assert {
        "workstation_delivery_ready",
        "assisted_service_pilot_ready",
        "solver_product_pilot_ready",
        "limited_commercial_ready",
        "ga_enterprise_ready",
        "stale_or_inconsistent",
        "root_blockers",
    } <= set(payload)
    assert payload["workstation_delivery_ready"] is True
    assert payload["stale_or_inconsistent"] is False
    assert payload["paid_pilot_ready"] is True
    assert payload["assisted_service_pilot_ready"] is True
    assert payload["solver_product_pilot_ready"] is True
    assert payload["limited_commercial_ready"] is True
    assert payload["independent_product_ready"] is True
    assert payload["ga_enterprise_ready"] is True
    assert payload["release_ready"] is True
    assert payload["release_decision"]["release_allowed"] is True
    assert payload["release_decision"]["evidence_surface_count"] == 2
    assert payload["release_decision"]["broad_gpcr_family_claim_safe"] is False
    assert payload["components"]["pm_release"]["release_decision"] == payload["release_decision"]
    metadata_by_artifact = {
        row["artifact"]: row for row in payload["state_consistency"]["metadata_rows"]
    }
    assert metadata_by_artifact["commercial_gap_ledger_status"]["metadata_complete"] is True
    assert (
        metadata_by_artifact["commercial_gap_ledger_status"]["input_checksum_present"]
        is True
    )
    assert payload["components"]["commercial_gap_ledger_status"] == {
        "status": "closed",
        "commercial_solver_gap_ready": True,
        "ai_engine_guardrail_rows_ready": True,
        "ai_engine_gap_ready": True,
        "autonomous_ai_engine_claim_ready": False,
        "autonomous_ai_engine_claim_blockers": [],
        "full_gap_ledger_ready": True,
        "summary": {
            "total_count": 20,
            "closed_count": 20,
            "partial_count": 0,
            "open_count": 0,
            "external_blocked_count": 0,
            "locally_closable_open_count": 0,
            "locally_closable_nonclosed_count": 0,
            "locally_closable_nonclosed_row_ids": [],
        },
        "ledger_split_summary": {
            "ai_engine": {
                "row_count": 10,
                "status_counts": {"closed": 10},
                "nonclosed_row_ids": [],
                "locally_closable_nonclosed_row_ids": [],
            },
            "commercial_solver": {
                "row_count": 10,
                "status_counts": {"closed": 10},
                "nonclosed_row_ids": [],
                "locally_closable_nonclosed_row_ids": [],
            },
        },
        "blocker_count": 0,
        "blockers": [],
        "next_locally_closable_gaps": [],
        "ready": True,
    }
    assert payload["components"]["gap_ledger_evidence_audit"] == {
        "status": "ready",
        "contract_pass": True,
        "ledger_status": "closed",
        "full_gap_ledger_ready": True,
        "row_count": 20,
        "closed_row_count": 20,
        "nonclosed_row_count": 0,
        "ledger_split_summary": {
            "ai_engine": {
                "row_count": 10,
                "closed_row_count": 10,
                "nonclosed_row_count": 0,
                "evidence_present_count": 10,
                "claim_boundary_present_count": 10,
                "nonclosed_rows_with_blockers_count": 0,
                "closure_requirement_count": 0,
                "closure_requirement_pass_count": 0,
                "closure_requirement_fail_count": 0,
                "nonclosed_rows_with_failed_closure_requirements_count": 0,
                "missing_evidence_ids": [],
                "missing_claim_boundary_ids": [],
                "nonclosed_missing_blocker_ids": [],
                "nonclosed_failed_closure_requirement_ids": [],
            },
            "commercial_solver": {
                "row_count": 10,
                "closed_row_count": 10,
                "nonclosed_row_count": 0,
                "evidence_present_count": 10,
                "claim_boundary_present_count": 10,
                "nonclosed_rows_with_blockers_count": 0,
                "closure_requirement_count": 0,
                "closure_requirement_pass_count": 0,
                "closure_requirement_fail_count": 0,
                "nonclosed_rows_with_failed_closure_requirements_count": 0,
                "missing_evidence_ids": [],
                "missing_claim_boundary_ids": [],
                "nonclosed_missing_blocker_ids": [],
                "nonclosed_failed_closure_requirement_ids": [],
            },
        },
        "blocker_count": 0,
        "blockers": [],
        "claim_boundary": (
            "Fixture audit verifies row evidence visibility only; it does not "
            "create commercial release readiness."
        ),
        "ready": True,
    }
    assert payload["components"]["developer_preview_readiness"] == {
        "status": "ready",
        "developer_preview_ready": True,
        "blocker_count": 0,
        "future_commercial_blocker_count": 4,
        "category_counts": {
            "benchmark": 0,
            "future commercial": 4,
            "numerical": 0,
            "software product": 0,
        },
        "freeze_policy": {
            "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
            "gpu_hip": "performance_track_after_cpu_reference_parity",
            "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
        },
        "gap_ledger_closure_requirement_visibility": {
            "source_status": "missing",
            "source_contract_pass": False,
            "source_full_gap_ledger_ready": False,
            "ai_engine_guardrail_rows_ready": False,
            "autonomous_ai_engine_claim_ready": False,
            "autonomous_ai_engine_claim_blockers": [],
            "closure_requirement_count": 0,
            "closure_requirement_pass_count": 0,
            "closure_requirement_fail_count": 0,
            "nonclosed_rows_with_failed_closure_requirements_count": 0,
            "nonclosed_failed_closure_requirement_ids": [],
            "claim_boundary": "",
        },
        "scope_boundary_sync_summary": {
            "status": "missing",
            "contract_pass": False,
            "doc_surface_count": 0,
            "doc_surface_pass_count": 0,
            "report_surface_count": 0,
            "report_surface_pass_count": 0,
            "gui_contract_pass": False,
            "gui_consumes_scope_record": False,
            "gui_consumes_closure_visibility_record": False,
            "gui_consumes_failed_closure_requirement_ids": False,
            "gui_renders_closure_requirement_summary": False,
            "gui_renders_closure_visibility_boundary": False,
        },
        "claim_boundary": (
            "Fixture Developer Preview receipt; future Commercial Release blockers "
            "remain visible but do not block the preview."
        ),
        "ready": True,
    }
    assert payload["components"]["phase1_core_api_contract"] == {
        "status": "ready",
        "contract_pass": True,
        "claim_boundary_version": "developer-preview-core-api-v1",
        "invocation_surfaces": ["python_api", "cli", "gui_json_consumption"],
        "supported_preview_analysis_types": [
            "model_health",
            "linear_static_axial_truss",
            "nonlinear_static_material_mesh_axial_chain",
        ],
        "schema_validation_pass": True,
        "cli_contract_pass": True,
        "cli_same_result_schema_as_python_api": True,
        "cli_same_validation_report_schema_as_python_api": True,
        "reference_validation_contract_pass": True,
        "python_api_blocks_reference_mismatch": True,
        "cli_blocks_reference_mismatch": True,
        "unsupported_feature_count": 0,
        "developer_preview_blocked_field_count": 0,
        "claim_boundary": (
            "Fixture Phase 1 core API contract proves Python/CLI/GUI JSON "
            "schema compatibility only; it does not close commercial solver gaps."
        ),
        "ready": True,
    }
    assert payload["components"]["developer_preview_rc"] == {
        "status": "ready",
        "contract_pass": True,
        "deliverable_count": 10,
        "deliverable_pass_count": 10,
        "final_gate_count": 9,
        "final_gate_pass_count": 9,
        "blocker_count": 0,
        "blockers": [],
        "claim_boundary": (
            "Fixture Developer Preview RC receipt; component status is informational "
            "inside the paid-pilot snapshot."
        ),
        "ready": True,
    }
    assert payload["blocker_count"] == 0
    assert payload["blockers"] == []
    assert set(payload["root_blockers"]) == {
        "release freshness/sync",
        "CI runner/streak",
        "human UX",
        "license/legal",
        "customer shadow",
        "external benchmark",
        "fresh validation",
        "G1 solver",
    }
    assert set(payload["blocker_categories"]) == {
        "numerical",
        "benchmark",
        "software product",
        "future commercial",
    }
    assert all(
        row["blocked"] is False and row["blocker_count"] == 0
        for row in payload["blocker_categories"].values()
    )


def test_snapshot_attaches_open_gap_ledger_audit_without_release_promotion(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "commercial_gap_ledger_status.json", {
        "schema_version": "commercial-gap-ledger-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "engine_version": "structural-analysis-workbench@test",
        "input_checksums": {
            "docs/commercial-structural-solver-product-gap-ledger.md": "sha256:abc123",
            "docs/structural-analysis-ai-engine-gap-ledger.md": "sha256:def456",
            "implementation/phase1/commercial_gap_ledger_status.py": "sha256:789abc",
        },
        "reused_evidence": True,
        "reuse_policy": (
            "summarizes_existing_gap_ledgers_and_productization_receipts; "
            "does_not_create_authoritative_closure_evidence"
        ),
        "status": "open",
        "commercial_solver_gap_ready": False,
        "ai_engine_gap_ready": False,
        "full_gap_ledger_ready": False,
        "summary": {
            "total_count": 20,
            "closed_count": 17,
            "partial_count": 2,
            "open_count": 0,
            "external_blocked_count": 1,
            "locally_closable_open_count": 1,
            "locally_closable_nonclosed_count": 1,
            "locally_closable_nonclosed_row_ids": ["G1"],
        },
        "blockers": [
            "G1:full_mesh_nonlinear_equilibrium_not_closed",
            "G6:external_submission_receipts_pending",
        ],
        "next_locally_closable_gaps": ["G1"],
        "rows": [
            {
                "id": "G1",
                "ledger": "commercial_solver",
                "status": "partial",
                "closed": False,
                "locally_closable": True,
                "blockers": ["full_mesh_nonlinear_equilibrium_not_closed"],
            },
            {
                "id": "G6",
                "ledger": "commercial_solver",
                "status": "external_blocked",
                "closed": False,
                "locally_closable": False,
                "blockers": ["external_submission_receipts_pending"],
            },
            {
                "id": "G7",
                "ledger": "commercial_solver",
                "status": "partial",
                "closed": False,
                "locally_closable": False,
                "blockers": ["operator_attached_real_project_evidence_missing"],
            },
            *[
                {
                    "id": f"G{index}",
                    "ledger": "commercial_solver",
                    "status": "closed",
                    "closed": True,
                    "locally_closable": False,
                    "blockers": [],
                }
                for index in (2, 3, 4, 5, 8, 9, 10)
            ],
            *[
                {
                    "id": f"AI-G{index}",
                    "ledger": "ai_engine",
                    "status": "closed",
                    "closed": True,
                    "locally_closable": False,
                    "blockers": [],
                }
                for index in range(1, 11)
            ],
        ],
    })
    _write_json(tmp_path / "gap_ledger_evidence_audit.json", {
        "schema_version": "gap-ledger-evidence-audit.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"commercial_gap_ledger_status.json": "sha256:abc123"},
        "reused_evidence": True,
        "status": "ready",
        "contract_pass": True,
        "ledger_status": "open",
        "full_gap_ledger_ready": False,
        "row_count": 20,
        "closed_row_count": 17,
        "nonclosed_row_count": 3,
        "row_outcomes": [
            {
                "id": "G1",
                "ledger": "commercial_solver",
                "closed": False,
                "evidence_present": True,
                "blocker_count": 1,
                "claim_boundary_present": True,
                "closure_requirement_count": 9,
                "closure_requirement_pass_count": 2,
                "closure_requirement_fail_count": 7,
                "closure_requirement_failed_ids": [
                    "full_load_scale_1_0_reached",
                    "strict_full_load_hip_newton_checkpoint_available",
                    "full_line_mesh_nonlinear_equilibrium_closed",
                    "full_frame_6dof_nonlinear_equilibrium_closed",
                    "coupled_frame_surface_nonlinear_equilibrium_closed",
                    "state_updated_material_newton_breadth_closed",
                    "fallback_and_regularization_free_full_path",
                ],
            },
            {
                "id": "G6",
                "ledger": "commercial_solver",
                "closed": False,
                "evidence_present": True,
                "blocker_count": 1,
                "claim_boundary_present": True,
                "closure_requirement_count": 5,
                "closure_requirement_pass_count": 1,
                "closure_requirement_fail_count": 4,
                "closure_requirement_failed_ids": [
                    "eb_receipt_hardest_external_10case",
                    "eb_receipt_korean_public_structures",
                    "eb_receipt_peer_spd_hinge",
                    "eb_receipt_tpu_hffb",
                ],
            },
            {
                "id": "G7",
                "ledger": "commercial_solver",
                "closed": False,
                "evidence_present": True,
                "blocker_count": 1,
                "claim_boundary_present": True,
                "closure_requirement_count": 5,
                "closure_requirement_pass_count": 0,
                "closure_requirement_fail_count": 5,
                "closure_requirement_failed_ids": [
                    "repo_benchmark_bridge_count_zero",
                    "metadata_only_count_zero",
                    "operator_attached_real_mgt_header_ok_minimum",
                    "operator_manifest_source_mapping_clear",
                    "operator_rights_boundary_clear",
                ],
            },
            *[
                {
                    "id": f"G{index}",
                    "ledger": "commercial_solver",
                    "closed": True,
                    "evidence_present": True,
                    "blocker_count": 0,
                    "claim_boundary_present": True,
                }
                for index in (2, 3, 4, 5, 8, 9, 10)
            ],
            *[
                {
                    "id": f"AI-G{index}",
                    "ledger": "ai_engine",
                    "closed": True,
                    "evidence_present": True,
                    "blocker_count": 0,
                    "claim_boundary_present": True,
                }
                for index in range(1, 11)
            ],
        ],
        "blockers": [],
        "claim_boundary": (
            "Audit confirms visibility only and does not override source ledger status."
        ),
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    ledger = payload["components"]["commercial_gap_ledger_status"]
    audit = payload["components"]["gap_ledger_evidence_audit"]
    assert ledger["status"] == "open"
    assert ledger["full_gap_ledger_ready"] is False
    assert ledger["blocker_count"] == 2
    assert ledger["next_locally_closable_gaps"] == ["G1"]
    assert ledger["ledger_split_summary"] == {
        "ai_engine": {
            "row_count": 10,
            "status_counts": {"closed": 10},
            "nonclosed_row_ids": [],
            "locally_closable_nonclosed_row_ids": [],
        },
        "commercial_solver": {
            "row_count": 10,
            "status_counts": {"closed": 7, "external_blocked": 1, "partial": 2},
            "nonclosed_row_ids": ["G1", "G6", "G7"],
            "locally_closable_nonclosed_row_ids": ["G1"],
        },
    }
    assert ledger["ready"] is False
    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["ledger_status"] == "open"
    assert audit["full_gap_ledger_ready"] is False
    assert audit["nonclosed_row_count"] == 3
    assert audit["ledger_split_summary"] == {
        "ai_engine": {
            "row_count": 10,
            "closed_row_count": 10,
            "nonclosed_row_count": 0,
            "evidence_present_count": 10,
            "claim_boundary_present_count": 10,
            "nonclosed_rows_with_blockers_count": 0,
            "closure_requirement_count": 0,
            "closure_requirement_pass_count": 0,
            "closure_requirement_fail_count": 0,
            "nonclosed_rows_with_failed_closure_requirements_count": 0,
            "missing_evidence_ids": [],
            "missing_claim_boundary_ids": [],
            "nonclosed_missing_blocker_ids": [],
            "nonclosed_failed_closure_requirement_ids": [],
        },
        "commercial_solver": {
            "row_count": 10,
            "closed_row_count": 7,
            "nonclosed_row_count": 3,
            "evidence_present_count": 10,
            "claim_boundary_present_count": 10,
            "nonclosed_rows_with_blockers_count": 3,
            "closure_requirement_count": 19,
            "closure_requirement_pass_count": 3,
            "closure_requirement_fail_count": 16,
            "nonclosed_rows_with_failed_closure_requirements_count": 3,
            "missing_evidence_ids": [],
            "missing_claim_boundary_ids": [],
            "nonclosed_missing_blocker_ids": [],
            "nonclosed_failed_closure_requirement_ids": [
                "G1:coupled_frame_surface_nonlinear_equilibrium_closed",
                "G1:fallback_and_regularization_free_full_path",
                "G1:full_frame_6dof_nonlinear_equilibrium_closed",
                "G1:full_line_mesh_nonlinear_equilibrium_closed",
                "G1:full_load_scale_1_0_reached",
                "G1:state_updated_material_newton_breadth_closed",
                "G1:strict_full_load_hip_newton_checkpoint_available",
                "G6:eb_receipt_hardest_external_10case",
                "G6:eb_receipt_korean_public_structures",
                "G6:eb_receipt_peer_spd_hinge",
                "G6:eb_receipt_tpu_hffb",
                "G7:metadata_only_count_zero",
                "G7:operator_attached_real_mgt_header_ok_minimum",
                "G7:operator_manifest_source_mapping_clear",
                "G7:operator_rights_boundary_clear",
                "G7:repo_benchmark_bridge_count_zero",
            ],
        },
    }
    assert audit["ready"] is True
    assert payload["components"]["assisted_service_pilot"]["blockers"] == []
    assert payload["components"]["solver_product"]["blockers"] == []
    assert not any(str(blocker).startswith("gap_ledger") for blocker in payload["blockers"])


def test_snapshot_attaches_blocked_developer_preview_readiness_without_commercial_promotion(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "developer_preview_readiness.json", {
        "schema_version": "developer-preview-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"developer_preview_inputs.json": "sha256:abc123"},
        "reused_evidence": False,
        "status": "blocked",
        "developer_preview_ready": False,
        "blocker_count": 3,
        "blockers": [
            "g1::full_mesh_nonlinear_equilibrium_not_closed",
            "fresh_full_validation::row_fresh_receipt_count_below_lane_count",
            "phase5::task_based_ux_not_observed",
        ],
        "future_commercial_blocker_count": 2,
        "future_commercial_blockers": [
            "customer_shadow::future_commercial_only",
            "license::future_commercial_only",
        ],
        "categories": {
            "numerical": {"blocked": True, "blocker_count": 1, "blockers": []},
            "benchmark": {"blocked": True, "blocker_count": 1, "blockers": []},
            "software product": {"blocked": True, "blocker_count": 1, "blockers": []},
            "future commercial": {"blocked": True, "blocker_count": 2, "blockers": []},
        },
        "scope": {
            "freeze_policy": {
                "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
                "gpu_hip": "performance_track_after_cpu_reference_parity",
                "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
            },
        },
        "gap_ledger_closure_requirement_visibility": {
            "source_status": "ready",
            "source_contract_pass": True,
            "source_full_gap_ledger_ready": False,
            "closure_requirement_count": 19,
            "closure_requirement_pass_count": 3,
            "closure_requirement_fail_count": 16,
            "nonclosed_rows_with_failed_closure_requirements_count": 3,
            "nonclosed_failed_closure_requirement_ids": [
                "G1:full_load_scale_1_0_reached",
                "G6:eb_receipt_hardest_external_10case",
                "G7:operator_manifest_source_mapping_clear",
            ],
            "claim_boundary": (
                "This is a visibility summary only and does not add Developer "
                "Preview blockers."
            ),
        },
        "scope_boundary_sync": {
            "status": "ready",
            "contract_pass": True,
            "doc_surfaces": {
                "README.md": {"contract_pass": True},
                "docs/commercialization-gap-current-state.md": {"contract_pass": True},
            },
            "surface_groups": {
                "reports": {
                    "surface_count": 1,
                    "contract_pass_count": 1,
                },
            },
            "gui_surface": {
                "contract_pass": True,
                "consumes_scope_record": True,
                "consumes_closure_visibility_record": True,
                "consumes_failed_closure_requirement_ids": True,
                "renders_closure_requirement_summary": True,
                "renders_closure_visibility_boundary": True,
            },
        },
        "claim_boundary": (
            "Developer Preview is not a commercial structural solver beta."
        ),
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    component = payload["components"]["developer_preview_readiness"]
    assert component["status"] == "blocked"
    assert component["developer_preview_ready"] is False
    assert component["blocker_count"] == 3
    assert component["future_commercial_blocker_count"] == 2
    assert component["category_counts"] == {
        "benchmark": 1,
        "future commercial": 2,
        "numerical": 1,
        "software product": 1,
    }
    assert component["gap_ledger_closure_requirement_visibility"] == {
        "source_status": "ready",
        "source_contract_pass": True,
        "source_full_gap_ledger_ready": False,
        "ai_engine_guardrail_rows_ready": False,
        "autonomous_ai_engine_claim_ready": False,
        "autonomous_ai_engine_claim_blockers": [],
        "closure_requirement_count": 19,
        "closure_requirement_pass_count": 3,
        "closure_requirement_fail_count": 16,
        "nonclosed_rows_with_failed_closure_requirements_count": 3,
        "nonclosed_failed_closure_requirement_ids": [
            "G1:full_load_scale_1_0_reached",
            "G6:eb_receipt_hardest_external_10case",
            "G7:operator_manifest_source_mapping_clear",
        ],
        "claim_boundary": (
            "This is a visibility summary only and does not add Developer "
            "Preview blockers."
        ),
    }
    assert component["scope_boundary_sync_summary"] == {
        "status": "ready",
        "contract_pass": True,
        "doc_surface_count": 2,
        "doc_surface_pass_count": 2,
        "report_surface_count": 1,
        "report_surface_pass_count": 1,
        "gui_contract_pass": True,
        "gui_consumes_scope_record": True,
        "gui_consumes_closure_visibility_record": True,
        "gui_consumes_failed_closure_requirement_ids": True,
        "gui_renders_closure_requirement_summary": True,
        "gui_renders_closure_visibility_boundary": True,
    }
    assert component["ready"] is False
    assert "commercial structural solver beta" in component["claim_boundary"]
    assert payload["components"]["assisted_service_pilot"]["blockers"] == []
    assert payload["components"]["solver_product"]["blockers"] == []
    assert not any(
        str(blocker).startswith("developer_preview")
        for blocker in payload["blockers"]
    )


def test_snapshot_attaches_blocked_developer_preview_rc_without_solver_promotion(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "developer_preview_rc_status.json", {
        "schema_version": "developer-preview-rc-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "input_checksums": {"developer_preview_rc_inputs.json": "sha256:abc123"},
        "reused_evidence": False,
        "status": "blocked",
        "contract_pass": False,
        "deliverable_count": 10,
        "deliverable_pass_count": 10,
        "final_gate_count": 9,
        "final_gate_pass_count": 3,
        "blockers": [
            "final_gate_blocked:linux_windows_reproducibility_confirmed",
            "final_gate_blocked:new_user_core_workflow_observation_passed",
        ],
        "claim_boundary": (
            "Aggregates Developer Preview RC deliverables and final gates only; "
            "does not close Commercial Release."
        ),
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    component = payload["components"]["developer_preview_rc"]
    assert component["status"] == "blocked"
    assert component["contract_pass"] is False
    assert component["deliverable_pass_count"] == 10
    assert component["final_gate_pass_count"] == 3
    assert component["blocker_count"] == 2
    assert component["blockers"] == [
        "final_gate_blocked:linux_windows_reproducibility_confirmed",
        "final_gate_blocked:new_user_core_workflow_observation_passed",
    ]
    assert component["ready"] is False
    assert payload["components"]["assisted_service_pilot"]["blockers"] == []
    assert payload["components"]["solver_product"]["blockers"] == []
    assert not any(
        str(blocker).startswith("developer_preview_rc")
        for blocker in payload["blockers"]
    )


def test_snapshot_separates_assisted_service_from_solver_product_gate(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": False,
        "full_g1_closure_blockers": [
            "full_load_gate_not_closed",
            "full_mesh_nonlinear_equilibrium_not_closed",
            "material_newton_breadth_not_closed",
            "production_rocm_hip_residency_not_closed",
        ],
        "claim_boundary": "Terminal gate only; does not close full-mesh/full-load nonlinear equilibrium.",
        "blockers": [],
    })
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["status"] = "blocked"
    g1_lane["contract_pass"] = False
    g1_lane["checkpoint"] = {"load_scale": 0.656}
    g1_lane["full_load_input_pass"] = False
    g1_lane["child_gate_evidence"] = _g1_child_gate_evidence(ready=False)
    g1_lane["frontier_non_promoting_evidence"] = {
        "schema_version": "g1-frontier-non-promoting-context.v1",
        "present": True,
        "evidence_role": "non_promoting_partial_frontier_context",
        "latest_frontier_direct_residual_inf_n": 5.74426714604332,
        "direct_residual_gate_tolerance_n": 0.0005,
        "frontier_residual_above_tolerance": True,
        "non_promoting_launch_receipt_count": 1,
        "promotes_g1_closure": False,
        "promotes_lane_status": False,
    }
    g1_lane["blockers"] = ["checkpoint_load_scale_below_required_full_load"]
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["assisted_service_pilot"]["ready"] is True
    assert payload["components"]["assisted_service_pilot"]["blocker_count"] == 0
    assert payload["components"]["assisted_service_pilot"]["blockers"] == []
    assert payload["assisted_service_pilot_ready"] is True
    assert payload["solver_product_pilot_ready"] is False
    assert payload["components"]["solver_product"]["g1_full_mesh_full_load_ready"] is False
    assert payload["components"]["solver_product"]["g1_full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["solver_product"]["blocker_count"] == 2
    assert payload["components"]["solver_product"]["blockers"] == [
        "g1_full_mesh_full_load_not_ready",
        "g1_full_load_hip_newton_lane_not_ready",
    ]
    assert payload["root_blockers"]["G1 solver"]["blocked"] is True
    assert "g1::full_load_gate_not_closed" in payload["root_blockers"]["G1 solver"]["blockers"]
    assert "g1_full_mesh_full_load_not_closed" in _g1_detail_blockers(payload)
    g1_component = payload["components"]["g1"]
    grouping = g1_component["blocker_grouping_metadata"]
    boundary = g1_component["closure_boundary_metadata"]
    assert grouping["root_blocker_count"] == 4
    assert grouping["suppressed_detail_blocker_count"] == len(
        g1_component["suppressed_detail_blockers"]
    )
    assert grouping["grouping_promotes_status"] is False
    assert grouping["detail_blockers_remain_visible"] is True
    assert all(group["active"] is True for group in grouping["root_groups"])
    assert (
        grouping["detail_blocker_represented_by_root_group"][
            "g1_full_load_lane::checkpoint_load_scale_below_required_full_load"
        ]
        == "g1::full_load_gate_not_closed"
    )
    assert (
        grouping["detail_blocker_represented_by_root_group"][
            "g1_full_mesh_full_load_not_closed"
        ]
        == "g1::full_mesh_nonlinear_equilibrium_not_closed"
    )
    assert boundary["metadata_promotes_status"] is False
    assert boundary["gpu_hip_replaces_cpu_parity"] is False
    assert boundary["cpu_parity_required_before_gpu_performance_promotion"] is True
    assert boundary["current_gate_state"]["full_mesh_full_load_ready"] is False
    assert boundary["current_gate_state"]["full_load_hip_newton_lane_ready"] is False
    assert "full_load_1_0" in boundary["cpu_first_closure_scope"]
    assert "device_residency" in boundary["gpu_hip_followup_scope"]
    frontier_context = g1_component[
        "full_load_hip_newton_frontier_non_promoting_evidence"
    ]
    assert frontier_context["present"] is True
    assert frontier_context["promotes_g1_closure"] is False
    assert frontier_context["promotes_lane_status"] is False
    assert frontier_context["frontier_residual_above_tolerance"] is True
    assert frontier_context["non_promoting_launch_receipt_count"] == 1


def test_snapshot_classifies_residual_holdout_as_solver_evidence_gap(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    independent = json.loads(
        (tmp_path / "independent_product_readiness.json").read_text(
            encoding="utf-8"
        )
    )
    independent["status"] = "blocked"
    independent["contract_pass"] = False
    independent["independent_commercial_product_ready"] = False
    independent["blockers"] = [
        "Strict external and residual holdout evidence::residual_holdout_closure_pending"
    ]
    _write_json(tmp_path / "independent_product_readiness.json", independent)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    expected = (
        "independent_product::Strict external and residual holdout "
        "evidence::residual_holdout_closure_pending"
    )
    assert expected in payload["root_blockers"]["G1 solver"]["blockers"]
    assert expected in payload["blocker_categories"]["numerical"]["blockers"]
    assert expected not in payload["root_blockers"]["release freshness/sync"]["blockers"]
    assert expected not in payload["blocker_categories"]["software product"]["blockers"]


def test_snapshot_separates_assisted_service_blockers_from_solver_product_blockers(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    ux_payload = json.loads((tmp_path / "ux_new_user_observation_report.json").read_text(encoding="utf-8"))
    ux_payload["contract_pass"] = False
    ux_payload["summary"] = {"completion_minutes": None, "max_completion_minutes": 30.0}
    ux_payload["blockers"] = ["observation_file_missing"]
    _write_json(tmp_path / "ux_new_user_observation_report.json", ux_payload)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assisted = payload["components"]["assisted_service_pilot"]
    solver = payload["components"]["solver_product"]
    assert assisted["ready"] is False
    assert "human_ux_observation_not_ready" in assisted["blockers"]
    assert "human_ux_observation_not_ready" not in solver["blockers"]
    assert solver["ready"] is True
    assert solver["blockers"] == []


def test_snapshot_deduplicates_pm_release_ux_wrappers_when_human_ux_blocks(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    ux_payload = json.loads(
        (tmp_path / "ux_new_user_observation_report.json").read_text(encoding="utf-8")
    )
    ux_payload["contract_pass"] = False
    ux_payload["summary"] = {"completion_minutes": None, "max_completion_minutes": 30.0}
    ux_payload["blockers"] = ["observation_file_missing", "completion_minutes_missing"]
    _write_json(tmp_path / "ux_new_user_observation_report.json", ux_payload)
    pm_payload = json.loads(
        (tmp_path / "pm_release_gate_report.json").read_text(encoding="utf-8")
    )
    pm_payload["limited_commercial_release_ready"] = False
    pm_payload["release_area_gate_ready"] = False
    pm_payload["full_release_gate_ready"] = False
    pm_payload["full_release_blockers"] = [
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
    ]
    pm_payload["release_area_blockers"] = pm_payload["full_release_blockers"]
    _write_json(tmp_path / "pm_release_gate_report.json", pm_payload)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert "human_ux::observation_file_missing" in payload["blockers"]
    assert "human_ux::completion_minutes_missing" not in payload["blockers"]
    assert "pm_release::ux::human_new_user_observation_missing_or_failed" not in payload[
        "blockers"
    ]
    assert "pm_release::ux::human_new_user_30min_sample_evidence_missing" not in payload[
        "blockers"
    ]
    assert (
        "pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
        in payload["blockers"]
    )
    pm_component = payload["components"]["pm_release"]
    assert pm_component["suppressed_duplicate_blocker_count"] == 2
    assert pm_component["suppressed_duplicate_blockers"] == [
        "pm_release::ux::human_new_user_observation_missing_or_failed",
        "pm_release::ux::human_new_user_30min_sample_evidence_missing",
    ]
    assert pm_component["duplicate_blocker_represented_by"] == {
        "pm_release::ux::human_new_user_observation_missing_or_failed": "human_ux::*",
        "pm_release::ux::human_new_user_30min_sample_evidence_missing": "human_ux::*",
    }
    ux_component = payload["components"]["human_ux_observation"]
    assert ux_component["top_level_blockers"] == ["human_ux::observation_file_missing"]
    assert ux_component["suppressed_detail_blockers"] == [
        "human_ux::completion_minutes_missing"
    ]
    assert ux_component["detail_blocker_represented_by"] == {
        "human_ux::completion_minutes_missing": "human_ux::observation_file_missing"
    }


def test_snapshot_does_not_promote_pm_contract_pass_to_release_ready(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `15/16` green. Current action register has `1` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `15/16` green. The open blocker total is `1`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": False,
        "release_area_gate_ready": False,
        "full_release_gate_ready": False,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(15)] + [{"ok": False}],
        "release_area_blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
        "full_release_blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 1},
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "blocked"
    assert payload["components"]["pm_release"]["contract_pass"] is True
    assert payload["components"]["pm_release"]["full_release_gate_ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
        in payload["blockers"]
    )
    assert "contract_pass fields are component contract results" in (
        payload["claim_boundary"]["contract_pass_vs_release_ready"]
    )


def test_snapshot_reads_project_identity_from_structured_pyproject_toml(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "pyproject.toml",
        (
            "[tool.example]\n"
            'name = "not-the-product-name"\n'
            "\n"
            "[project]\n"
            'name = "structural-optimization-workbench" # canonical package name\n'
            'version = "1.0.0" # canonical package version\n'
        ),
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["product_identity"] == {
        "package_json": {
            "name": "structural-optimization-workbench",
            "version": "1.0.0",
        },
        "pyproject": {
            "name": "structural-optimization-workbench",
            "version": "1.0.0",
        },
        "name_matches": True,
        "version_matches": True,
        "matches": True,
    }
    assert "product_identity_name_mismatch:package_json_vs_pyproject" not in payload["blockers"]
    assert "product_identity_version_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_engine_version_tracks_canonical_product_identity(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.2.3",
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.2.3"\n',
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["engine_version"] == "structural-optimization-workbench@1.2.3"
    assert payload["components"]["product_identity"]["matches"] is True
    assert "product_identity_version_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_blocks_package_pyproject_name_mismatch(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench-ui",
        "version": "1.0.0",
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "blocked"
    assert payload["paid_pilot_ready"] is False
    assert payload["components"]["product_identity"]["name_matches"] is False
    assert payload["components"]["product_identity"]["version_matches"] is True
    assert "product_identity_name_mismatch:package_json_vs_pyproject" in payload["blockers"]
    assert "product_identity_version_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_blocks_package_pyproject_version_mismatch(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "0.1.0"\n',
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "blocked"
    assert payload["paid_pilot_ready"] is False
    assert payload["components"]["product_identity"]["name_matches"] is True
    assert payload["components"]["product_identity"]["version_matches"] is False
    assert "product_identity_version_mismatch:package_json_vs_pyproject" in payload["blockers"]
    assert "product_identity_name_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_accepts_receipt_only_commit_as_fresh(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    _write_json(tmp_path / "implementation/phase1/support_bundle_manifest.json", {
        "schema_version": "support-bundle-manifest.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "contract_pass": True,
    })
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_json(tmp_path / "implementation/phase1/support_bundle_manifest.json", {
        "schema_version": "support-bundle-manifest.v1",
        "generated_at": "2026-06-21T00:00:01+00:00",
        "contract_pass": True,
    })
    receipt_commit = _commit_all(tmp_path, "support bundle manifest")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == receipt_commit
    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_blocks_missing_input_checksum_on_head_generation(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    ci_payload = json.loads(
        (tmp_path / "github_actions_ci_streak_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    ci_payload.pop("input_checksums")
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", ci_payload)
    _commit_all(tmp_path, "evidence missing checksum")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert (
        "stale_or_inconsistent:input_checksum_missing:github_actions_ci_streak_evidence"
        in payload["blockers"]
    )
    row = next(
        row
        for row in payload["state_consistency"]["metadata_rows"]
        if row["artifact"] == "github_actions_ci_streak_evidence"
    )
    assert row["input_checksum_present"] is False


def test_snapshot_accepts_dispatch_prompt_commit_as_receipt_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "docs/ai/dispatch/g1_runtime_blocker_probe.md",
        "Goal: inspect runtime blocker propagation.\n",
    )
    dispatch_commit = _commit_all(tmp_path, "dispatch prompt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == dispatch_commit
    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert (
        "docs/ai/dispatch/g1_runtime_blocker_probe.md"
        in metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"]
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_blocks_non_receipt_changes_after_source_commit(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(tmp_path / "solver_core.py", "print('changed after evidence')\n")
    _commit_all(tmp_path, "solver code change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert payload["snapshot_source_state_consistent"] is False
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        in payload["blockers"]
    )
    assisted_blockers = payload["components"]["assisted_service_pilot"]["blockers"]
    solver_blockers = payload["components"]["solver_product"]["blockers"]
    assert "snapshot_source_state_not_consistent" in assisted_blockers
    assert "snapshot_source_state_not_consistent" in solver_blockers
    assert "evidence_not_fresh" not in assisted_blockers
    assert "evidence_not_fresh" not in solver_blockers
    assert (
        payload["components"]["assisted_service_pilot"]["snapshot_source_state_consistent"]
        is False
    )
    assert payload["components"]["solver_product"]["snapshot_source_state_consistent"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is False
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_receipt_paths_changed"
    )
    assert metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"] == [
        "solver_core.py",
    ]


def test_snapshot_accepts_generated_open_data_timestamp_only_commit(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    generated_open_data = (
        tmp_path
        / "implementation/phase1/open_data/midas/generated_roundtrip_receipt.json"
    )
    _write_json(
        generated_open_data,
        {
            "schema_version": "generated-open-data.v1",
            "generated_at": "2026-06-21T00:00:00+00:00",
            "case_count": 3,
        },
    )
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_json(
        generated_open_data,
        {
            "schema_version": "generated-open-data.v1",
            "generated_at": "2026-06-21T00:00:01+00:00",
            "case_count": 3,
        },
    )
    _commit_all(tmp_path, "open-data generated timestamp")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["status"] == "ready"
    assert payload["evidence_fresh"] is True
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "generated_open_data_timestamp_only_commit"
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_blocks_generated_open_data_semantic_commit(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    generated_open_data = (
        tmp_path
        / "implementation/phase1/open_data/midas/generated_roundtrip_receipt.json"
    )
    _write_json(
        generated_open_data,
        {
            "schema_version": "generated-open-data.v1",
            "generated_at": "2026-06-21T00:00:00+00:00",
            "case_count": 3,
        },
    )
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_json(
        generated_open_data,
        {
            "schema_version": "generated-open-data.v1",
            "generated_at": "2026-06-21T00:00:01+00:00",
            "case_count": 4,
        },
    )
    _commit_all(tmp_path, "open-data generated semantic change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is False
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_receipt_paths_changed"
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        in payload["blockers"]
    )


def test_snapshot_scoped_builder_change_only_stales_matching_artifact(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/run_g1_full_load_hip_newton_lane.py",
        "print('g1 lane wrapper policy changed')\n",
    )
    _commit_all(tmp_path, "g1 lane wrapper change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_artifact_source_paths_changed"
    )
    assert (
        metadata_rows["g1_full_load_hip_newton_lane_report"]["source_state_fresh"]
        is False
    )
    assert (
        metadata_rows["g1_full_load_hip_newton_lane_report"]["source_state_kind"]
        == "non_receipt_paths_changed"
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        not in payload["blockers"]
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:g1_full_load_hip_newton_lane_report"
        in payload["blockers"]
    )


def test_snapshot_public_benchmark_builder_change_does_not_stale_snapshot_leaf_receipts(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/materialize_public_benchmark_operator_bundle_from_rows.py",
        "print('public benchmark row importer changed')\n",
    )
    _commit_all(tmp_path, "public benchmark importer change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["license_status_closure_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["license_status_closure_report"]["source_state_kind"]
        == "non_artifact_source_paths_changed"
    )
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_g1_cause_narrowing_builder_change_does_not_stale_snapshot_leaf_receipts(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/build_g1_f2g_f2h_cause_narrowing_status.py",
        "print('g1 cause narrowing diagnostic changed')\n",
    )
    _commit_all(tmp_path, "g1 cause narrowing builder change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_artifact_source_paths_changed"
    )
    assert metadata_rows["g1_full_load_hip_newton_lane_report"]["source_state_fresh"] is True
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_license_builder_change_only_stales_license_receipt(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/build_license_status_closure_report.py",
        "print('license closure policy changed')\n",
    )
    _commit_all(tmp_path, "license closure builder change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert metadata_rows["license_status_closure_report"]["source_state_fresh"] is False
    assert (
        metadata_rows["license_status_closure_report"]["source_state_kind"]
        == "non_receipt_paths_changed"
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        not in payload["blockers"]
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:license_status_closure_report"
        in payload["blockers"]
    )


def test_snapshot_builder_change_does_not_stale_source_artifacts(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/build_product_readiness_snapshot.py",
        "print('snapshot aggregation policy changed')\n",
    )
    _commit_all(tmp_path, "snapshot builder change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_artifact_source_paths_changed"
    )
    assert payload["evidence_fresh"] is True
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_dp_rc_builder_change_only_stales_dp_rc_artifact(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "scripts/build_developer_preview_rc_status.py",
        "print('developer preview rc aggregation changed')\n",
    )
    _commit_all(tmp_path, "dp rc builder change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert metadata_rows["developer_preview_rc_status"]["source_state_fresh"] is False
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        not in payload["blockers"]
    )
    assert (
        "stale_or_inconsistent:source_commit_mismatch:developer_preview_rc_status"
        in payload["blockers"]
    )


def test_snapshot_blocks_dirty_worktree_even_when_committed_boundary_is_receipt_only(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(tmp_path / "solver_core.py", "print('uncommitted solver change')\n")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert "stale_or_inconsistent:worktree_dirty" in payload["blockers"]
    assert payload["state_consistency"]["worktree"]["dirty"] is True
    assert payload["state_consistency"]["worktree"]["status_rows"] == [
        "?? solver_core.py",
    ]
    assert payload["state_consistency"]["worktree"]["dirty_paths"] == [
        "solver_core.py",
    ]
    assert payload["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == [
        "solver_core.py",
    ]
    cleanup_plan = payload["state_consistency"]["worktree"]["phase3_release_control_cleanup_plan"]
    assert cleanup_plan == {
        "path": "phase3_release_control_cleanup_plan.json",
        "status": "ready",
        "contract_pass": True,
        "candidate_set_source": "",
        "candidate_set_scope": "",
        "current_worktree_diagnostics_included": False,
        "current_worktree_diagnostic_source": "",
        "candidate_release_control_commit_set_count": 0,
        "path_role_counts": {},
        "recommended_action_counts": {},
        "track_or_add_required_path_count": 0,
        "resolve_or_commit_dirty_tracked_path_count": 0,
        "human_git_action_required": False,
        "codex_commit_or_push_performed": False,
        "human_handoff_status": "",
        "human_handoff_next_action": "",
        "human_handoff_suggested_command_count": 0,
        "human_handoff_push_or_release_command_included": False,
        "claim_boundary": "No Phase 3 release-control cleanup is required for this fixture.",
    }
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )


def test_snapshot_attaches_phase3_release_control_cleanup_plan_summary(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _write_json(tmp_path / "phase3_release_control_cleanup_plan.json", {
        "schema_version": "phase3-release-control-cleanup-plan.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": source_commit,
        "status": "blocked",
        "contract_pass": False,
        "candidate_set_source": (
            "phase3_benchmark_factory_seed_git_clean_clone_reproduction."
            "release_control_cleanup_plan"
        ),
        "candidate_set_scope": (
            "Phase 3 seed git-clean-clone reproduction required-input set only; "
            "it is not an exhaustive current-worktree dirty-path inventory."
        ),
        "current_worktree_diagnostics_included": False,
        "current_worktree_diagnostic_source": (
            "product_readiness_snapshot.state_consistency.worktree"
        ),
        "candidate_release_control_commit_set_count": 23,
        "path_role_counts": {"generated_productization_evidence": 7},
        "recommended_action_counts": {"track_generated_productization_evidence": 7},
        "track_or_add_required_paths": ["phase3_seed_summary.json"],
        "resolve_or_commit_dirty_tracked_paths": ["pyproject.toml"],
        "human_git_action_required": True,
        "codex_commit_or_push_performed": False,
        "human_handoff": {
            "status": "blocked_until_human_git_action",
            "next_action": "owner_review_then_track_or_commit_required_inputs",
            "suggested_local_command_args": [
                ["git", "add", "--", "phase3_seed_summary.json"],
                ["git", "add", "--", "pyproject.toml"],
            ],
            "push_or_release_command_included": False,
        },
        "claim_boundary": "Codex did not commit, push, release, or promote readiness.",
    })
    _commit_all(tmp_path, "receipt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )

    cleanup_plan = payload["state_consistency"]["worktree"]["phase3_release_control_cleanup_plan"]
    assert cleanup_plan["status"] == "blocked"
    assert cleanup_plan["contract_pass"] is False
    assert (
        cleanup_plan["candidate_set_source"]
        == "phase3_benchmark_factory_seed_git_clean_clone_reproduction.release_control_cleanup_plan"
    )
    assert "not an exhaustive current-worktree" in cleanup_plan["candidate_set_scope"]
    assert cleanup_plan["current_worktree_diagnostics_included"] is False
    assert (
        cleanup_plan["current_worktree_diagnostic_source"]
        == "product_readiness_snapshot.state_consistency.worktree"
    )
    assert cleanup_plan["candidate_release_control_commit_set_count"] == 23
    assert cleanup_plan["path_role_counts"] == {"generated_productization_evidence": 7}
    assert cleanup_plan["recommended_action_counts"] == {
        "track_generated_productization_evidence": 7
    }
    assert cleanup_plan["track_or_add_required_path_count"] == 1
    assert cleanup_plan["resolve_or_commit_dirty_tracked_path_count"] == 1
    assert cleanup_plan["human_git_action_required"] is True
    assert cleanup_plan["codex_commit_or_push_performed"] is False
    assert cleanup_plan["human_handoff_status"] == "blocked_until_human_git_action"
    assert (
        cleanup_plan["human_handoff_next_action"]
        == "owner_review_then_track_or_commit_required_inputs"
    )
    assert cleanup_plan["human_handoff_suggested_command_count"] == 2
    assert cleanup_plan["human_handoff_push_or_release_command_included"] is False
    component = payload["components"]["release_control_cleanup"]
    assert component["local_worktree_dirty"] is False
    assert component["dirty_path_count"] == 0
    assert component["non_receipt_dirty_path_count"] == 0
    assert component["remote_github_sync_clean"] is True
    assert component["remote_github_sync_blocker_count"] == 0
    assert component["cleanup_plan_status"] == "blocked"
    assert component["cleanup_plan_contract_pass"] is False
    assert (
        component["cleanup_plan_candidate_set_source"]
        == "phase3_benchmark_factory_seed_git_clean_clone_reproduction.release_control_cleanup_plan"
    )
    assert "not an exhaustive current-worktree" in component["cleanup_plan_candidate_set_scope"]
    assert component["cleanup_plan_current_worktree_diagnostics_included"] is False
    assert (
        component["cleanup_plan_current_worktree_diagnostic_source"]
        == "product_readiness_snapshot.state_consistency.worktree"
    )
    assert component["cleanup_plan_candidate_path_count"] == 23
    assert component["cleanup_plan_track_or_add_required_path_count"] == 1
    assert component["cleanup_plan_resolve_or_commit_dirty_tracked_path_count"] == 1
    assert component["cleanup_plan_path_role_counts"] == {
        "generated_productization_evidence": 7
    }
    assert component["cleanup_plan_recommended_action_counts"] == {
        "track_generated_productization_evidence": 7
    }
    assert component["human_git_action_required"] is True
    assert component["codex_commit_or_push_performed"] is False
    assert component["human_handoff_status"] == "blocked_until_human_git_action"
    assert component["human_handoff_push_or_release_command_included"] is False
    assert "remote GitHub sync are separate blockers" in component["claim_boundary"]
    assert "Codex did not commit" in cleanup_plan["claim_boundary"]


def test_snapshot_separates_remote_github_sync_from_local_cleanup(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    pm_report = json.loads((tmp_path / "pm_release_gate_report.json").read_text(encoding="utf-8"))
    pm_report["limited_commercial_release_ready"] = False
    pm_report["release_area_gate_ready"] = False
    pm_report["full_release_gate_ready"] = False
    pm_report["release_area_blockers"] = [
        "github_sync::github_sync_preflight::remote_mutation_approval_required",
        "github_sync::github_sync_remote_sync_pending",
    ]
    pm_report["full_release_blockers"] = []
    _write_json(tmp_path / "pm_release_gate_report.json", pm_report)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    component = payload["components"]["release_control_cleanup"]
    assert component["local_worktree_dirty"] is False
    assert component["non_receipt_dirty_path_count"] == 0
    assert component["remote_github_sync_clean"] is False
    assert component["remote_github_sync_blocker_count"] == 2
    assert component["remote_github_sync_blockers"] == [
        "pm_release::github_sync::github_sync_preflight::remote_mutation_approval_required",
        "pm_release::github_sync::github_sync_remote_sync_pending",
    ]
    assert payload["root_blockers"]["release freshness/sync"]["blocked"] is True
    assert "stale_or_inconsistent:worktree_dirty" not in payload["blockers"]


def test_snapshot_allows_dirty_receipt_only_worktree_as_refresh_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    _write_json(tmp_path / "implementation/phase1/support_bundle_manifest.json", {
        "schema_version": "support-bundle-manifest.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "contract_pass": True,
    })
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    pm_report = json.loads((tmp_path / "pm_release_gate_report.json").read_text())
    pm_report["generated_at"] = "2026-06-21T00:00:01+00:00"
    _write_json(tmp_path / "pm_release_gate_report.json", pm_report)
    _write_json(tmp_path / "implementation/phase1/support_bundle_manifest.json", {
        "schema_version": "support-bundle-manifest.v1",
        "generated_at": "2026-06-21T00:00:01+00:00",
        "contract_pass": True,
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )

    assert "stale_or_inconsistent:worktree_dirty" not in payload["blockers"]
    assert payload["state_consistency"]["worktree"]["dirty"] is False
    assert sorted(payload["state_consistency"]["worktree"]["status_rows"]) == [
        " M implementation/phase1/support_bundle_manifest.json",
        " M pm_release_gate_report.json",
    ]
    assert sorted(payload["state_consistency"]["worktree"]["dirty_paths"]) == [
        "implementation/phase1/support_bundle_manifest.json",
        "pm_release_gate_report.json",
    ]
    assert payload["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == []
    assert payload["status"] == "ready"
    assert payload["evidence_fresh"] is True


def test_snapshot_allows_product_capabilities_surface_as_receipt_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_json(
        tmp_path / "implementation/phase1/release_evidence/surface/product_capabilities_surface.json",
        {
            "schema_version": "product-capabilities-surface.v1",
            "generated_at": "2026-06-21T00:00:01+00:00",
            "source_commit_sha": source_commit,
            "input_checksums": {"capability_input": "sha256:abc123"},
            "reused_evidence": False,
            "contract_pass": True,
            "status": "ready",
        },
    )
    surface_commit = _commit_all(tmp_path, "product capabilities surface")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == surface_commit
    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert (
        "implementation/phase1/release_evidence/surface/product_capabilities_surface.json"
        in metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"]
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_allows_release_surface_json_as_receipt_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_json(
        tmp_path
        / "implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json",
        {
            "schema_version": "pocketmd-lite-science-product-surface.v1",
            "generated_at": "2026-06-21T00:00:01+00:00",
            "source_commit_sha": source_commit,
            "input_checksums": {"surface_input": "sha256:abc123"},
            "reused_evidence": False,
            "contract_pass": True,
            "status": "ready",
        },
    )
    surface_commit = _commit_all(tmp_path, "science product surface")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == surface_commit
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert (
        "implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json"
        in metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"]
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_blocks_stale_workstation_and_independent_inputs(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": False,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": ["future_commercial_scope_not_ready"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": "old-workstation",
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "blockers": [],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": "old-independent",
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "stale_or_inconsistent"
    assert "stale_or_inconsistent:source_commit_mismatch:workstation_delivery_readiness" in payload["blockers"]
    assert "stale_or_inconsistent:source_commit_mismatch:independent_product_readiness" in payload["blockers"]
    assert payload["evidence_fresh"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["ga_enterprise_ready"] is False


def test_snapshot_does_not_promote_ready_status_with_component_blockers(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "blockers": ["delivery_blocker_still_present"],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": ["independent_blocker_still_present"],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["workstation_delivery_ready"] is False
    assert payload["independent_product_ready"] is False
    assert "workstation_delivery::delivery_blocker_still_present" in payload["blockers"]
    assert "independent_product::independent_blocker_still_present" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_blocks_github_hosted_actions_runner_policy(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        "name: CI\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_runner_policy"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert any(
        blocker.startswith("runner_policy::.github/workflows/ci.yml:4:github_hosted_runner_label")
        for blocker in payload["blockers"]
    )


def test_snapshot_blocks_missing_self_hosted_runner_status(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    (tmp_path / "github_actions_self_hosted_runner_status.json").unlink()

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_self_hosted_runner"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert "missing_artifact:github_actions_self_hosted_runner_status.json" in payload["blockers"]
    assert "self_hosted_runner:not_ready" in payload["blockers"]


def test_snapshot_surfaces_release_operation_evidence_blockers(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": False,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": ["future_commercial_scope_not_ready"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", {
        "schema_version": "github-actions-ci-streak-evidence.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {
            "pr_threshold_pass": False,
            "nightly_threshold_pass": False,
            "pr_consecutive_pass_count": 0,
            "nightly_consecutive_pass_count": 0,
        },
        "lanes": {
            "pr": {"blockers": ["pr_github_actions_30_consecutive_pass_evidence_missing"]},
            "nightly": {"blockers": ["nightly_github_actions_30_consecutive_pass_evidence_missing"]},
        },
    })
    _write_json(tmp_path / "ux_new_user_observation_report.json", {
        "schema_version": "ux-new-user-observation-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"completion_minutes": None, "max_completion_minutes": 30.0},
        "blockers": ["observation_file_missing"],
    })
    _write_json(tmp_path / "license_status_closure_report.json", {
        "schema_version": "license-status-closure-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"status": "not_configured"},
        "blockers": ["license_status_not_active"],
    })
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 0,
            "submission_receipt_pending_count": 4,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_status": "pending_external_submission_receipt",
                "closure_evidence_status": "pending",
            }
            for idx in range(1, 5)
        },
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_ci_streak"]["ready"] is False
    assert payload["components"]["human_ux_observation"]["ready"] is False
    assert payload["components"]["license_status"]["ready"] is False
    assert payload["components"]["external_benchmark_receipts"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "ci_streak::pr::pr_github_actions_30_consecutive_pass_evidence_missing"
        in payload["blockers"]
    )
    assert "human_ux::observation_file_missing" in payload["blockers"]
    assert "license::license_status_not_active" in payload["blockers"]
    assert "commercial_sla::production_support_commitment_missing" in payload["blockers"]
    assert "license_server::operation_readiness_missing" in payload["blockers"]
    assert "external_benchmark::submission_receipts_pending=4" in payload["blockers"]
    assert payload["blocker_categories"]["software product"]["blocked"] is True
    assert "CI runner/streak" in payload["blocker_categories"]["software product"][
        "root_streams"
    ]
    assert "human UX" in payload["blocker_categories"]["software product"][
        "root_streams"
    ]
    assert (
        "ci_streak::pr::pr_github_actions_30_consecutive_pass_evidence_missing"
        in payload["blocker_categories"]["software product"]["blockers"]
    )
    assert "human_ux::observation_file_missing" in payload["blocker_categories"][
        "software product"
    ]["blockers"]
    assert "external benchmark" in payload["blocker_categories"]["benchmark"][
        "root_streams"
    ]
    assert "external_benchmark::submission_receipts_pending=4" in payload[
        "blocker_categories"
    ]["benchmark"]["blockers"]
    assert "license/legal" in payload["blocker_categories"]["future commercial"][
        "root_streams"
    ]
    assert "license::license_status_not_active" in payload["blocker_categories"][
        "future commercial"
    ]["blockers"]
    assert "commercial_sla::production_support_commitment_missing" in payload[
        "blocker_categories"
    ]["future commercial"]["blockers"]
    assert "license_server::operation_readiness_missing" in payload[
        "blocker_categories"
    ]["future commercial"]["blockers"]
    assert payload["blocker_categories"]["numerical"]["blocked"] is False


def test_snapshot_rejects_reused_external_benchmark_receipt_sidecar(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": True,
        "full_g1_closure_blockers": [],
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 4,
            "submission_receipt_pending_count": 0,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_url": f"https://example.invalid/eb/{idx}",
                "receipt_status": "attached",
                "closure_evidence_status": "attached",
            }
            for idx in range(1, 5)
        },
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["external_benchmark_receipts"]["updates_fresh"] is False
    assert payload["components"]["external_benchmark_receipts"]["ready"] is False
    assert (
        "external_benchmark::submission_updates_reused_evidence_not_fresh"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_rejects_external_benchmark_summary_without_update_receipts(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 4,
            "submission_receipt_pending_count": 0,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "updates": {},
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["external_benchmark_receipts"]["attached_count"] == 4
    assert payload["components"]["external_benchmark_receipts"]["update_count"] == 0
    assert payload["components"]["external_benchmark_receipts"]["ready"] is False
    assert (
        "external_benchmark::submission_update_rows_below_queue_count"
        in payload["blockers"]
    )
    assert (
        "external_benchmark::submission_update_receipts_below_queue_count"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_rejects_fresh_validation_summary_when_row_receipt_reused(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "rows": [
            {
                "lane_id": f"lane_{index}",
                "pass": True,
                "fresh_validation_receipt_fresh": index != 0,
                "fresh_validation_receipt_contract_pass": True,
            }
            for index in range(8)
        ],
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["fresh_full_validation"]["row_count"] == 8
    assert payload["components"]["fresh_full_validation"]["row_pass_count"] == 8
    assert payload["components"]["fresh_full_validation"]["row_fresh_receipt_count"] == 7
    assert payload["components"]["fresh_full_validation"]["ready"] is False
    assert (
        "fresh_full_validation::row_fresh_receipt_count_below_lane_count"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_keeps_explicit_fresh_lane_blocker_without_duplicate_row_aggregates(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 7,
            "fresh_validation_receipt_pass_count": 7,
        },
        "rows": [
            *_fresh_validation_rows(count=7),
            {
                "lane_id": "gpu_hip_solver",
                "pass": False,
                "fresh_validation_receipt_fresh": False,
                "fresh_validation_receipt_contract_pass": False,
                "fresh_validation_receipt_present": False,
                "fresh_validation_receipt_reused_evidence": False,
            },
        ],
        "blockers": ["gpu_hip_solver::fresh_validation_receipt_missing"],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    fresh_component = payload["components"]["fresh_full_validation"]
    assert fresh_component["lane_count"] == 8
    assert fresh_component["row_count"] == 8
    assert fresh_component["row_pass_count"] == 7
    assert fresh_component["row_fresh_receipt_count"] == 7
    assert fresh_component["row_contract_pass_count"] == 7
    assert fresh_component["ready"] is False
    assert (
        "fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing"
        in payload["blockers"]
    )
    assert "fresh_full_validation::row_count_below_lane_count" not in payload["blockers"]
    assert "fresh_full_validation::row_pass_count_below_lane_count" not in payload["blockers"]
    assert (
        "fresh_full_validation::row_fresh_receipt_count_below_lane_count"
        not in payload["blockers"]
    )
    assert (
        "fresh_full_validation::row_contract_pass_count_below_lane_count"
        not in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_rejects_fresh_validation_summary_without_rows(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["fresh_full_validation"]["row_count"] == 0
    assert payload["components"]["fresh_full_validation"]["ready"] is False
    assert "fresh_full_validation::row_count_below_lane_count" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_rejects_customer_shadow_summary_without_evidence_rows(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["customer_shadow"]["completed_shadow_case_count"] == 3
    assert payload["components"]["customer_shadow"]["evidence_row_count"] == 0
    assert payload["components"]["customer_shadow"]["ready"] is False
    assert "customer_shadow::evidence_row_count_below_minimum" in payload["blockers"]
    assert (
        "customer_shadow::completed_evidence_row_count_below_minimum"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_requires_schema_versions_for_release_operation_inputs(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    ci_payload = json.loads((tmp_path / "github_actions_ci_streak_evidence.json").read_text(encoding="utf-8"))
    ci_payload.pop("schema_version")
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", ci_payload)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "schema_invalid:missing_schema_version:github_actions_ci_streak_evidence"
        in payload["blockers"]
    )


def test_snapshot_blocks_unexpected_g1_full_load_lane_schema(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["schema_version"] = "g1-full-load-hip-newton-lane.v0"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert (
        "schema_invalid:unexpected_schema_version:g1_full_load_hip_newton_lane_report"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_surfaces_g1_full_load_lane_blocker(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": False,
        "full_g1_closure_blockers": ["full_load_gate_not_closed"],
        "claim_boundary": "Terminal checkpoint only; does not close full-mesh/full-load.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": False,
        "status": "blocked",
        "checkpoint": {"load_scale": 0.656},
        "full_load_input_pass": False,
        "blockers": ["checkpoint_load_scale_below_required_full_load"],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"]["full_load_hip_newton_lane_status"] == "blocked"
    assert (
        "g1_full_load_lane::checkpoint_load_scale_below_required_full_load"
        in _g1_detail_blockers(payload)
    )
    assert "g1_full_load_lane::full_load_input_not_pass" in _g1_detail_blockers(payload)
    assert (
        "g1_full_load_lane::observed_load_scale_below_required_full_load"
        in _g1_detail_blockers(payload)
    )
    assert "g1::full_load_gate_not_closed" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_without_child_hip_refresh_evidence(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    g1_component = payload["components"]["g1"]
    assert g1_component["full_load_hip_newton_lane_ready"] is False
    assert (
        g1_component[
            "full_load_hip_newton_child_hip_residual_refresh_ready"
        ]
        is False
    )
    assert (
        "g1_full_load_lane::child_hip_residual_refresh_evidence_missing"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::matrix_free_global_krylov_child_hip_residual_refresh_not_ready"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::current_tangent_residual_row_correction_child_hip_residual_refresh_not_ready"
        in _g1_detail_blockers(payload)
    )
    assert "g1::full_load_gate_not_closed" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False


def test_snapshot_records_ready_g1_hip_consistency_proof_component(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof = payload["components"]["g1"]["full_load_hip_newton_hip_consistency_proof"]
    assert payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof_ready"
    ] is True
    assert proof["ready"] is True
    assert proof["rocm_hip_required"] is True
    assert proof["cpu_diagnostic_assembler_used"] is False
    assert proof["production_hip_residual_jacobian_path"] is True
    assert proof["consistent_residual_jacobian_newton_gate_passed"] is True
    assert proof["receipt_blockers"] == []
    assert proof["runtime_blockers"] == []


def test_snapshot_blocks_ready_g1_lane_with_blocked_hip_consistency_proof(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["hip_consistency_proof"] = _g1_hip_consistency_proof(ready=False)
    # Simulate a buggy lane report that forgot to mirror proof blockers at the
    # lane top level. The canonical snapshot must still block release.
    g1_lane["blockers"] = []
    g1_lane["contract_pass"] = True
    g1_lane["status"] = "ready"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof = payload["components"]["g1"]["full_load_hip_newton_hip_consistency_proof"]
    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof_ready"
    ] is False
    assert proof["ready"] is False
    assert proof["runtime_blockers"] == ["dev_kfd_missing", "dev_dri_missing"]
    assert "g1_full_load_lane::hip_consistency_proof_gate_not_passed" in _g1_detail_blockers(payload)
    assert "g1_full_load_lane::hip_consistency_proof_has_blockers" in _g1_detail_blockers(payload)
    assert (
        "g1_full_load_lane::hip_consistency_proof_runtime::dev_kfd_missing"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_runtime::dev_dri_missing"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_g1_lane_when_hip_path_wired_but_gate_not_closed(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    proof = _g1_hip_consistency_proof(ready=True)
    proof["status"] = "partial"
    proof["execution_mode"] = "hip_required_direct_probe_no_cpu_fallback"
    proof["production_hip_residual_jacobian_path"] = True
    proof["consistent_residual_jacobian_newton_gate_passed"] = False
    proof["receipt_blockers"] = ["consistent_residual_jacobian_not_closed"]
    proof["runtime_blockers"] = []
    g1_lane["hip_consistency_proof"] = proof
    g1_lane["blockers"] = []
    g1_lane["contract_pass"] = True
    g1_lane["status"] = "ready"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof_summary = payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof"
    ]
    assert proof_summary["production_hip_residual_jacobian_path"] is True
    assert proof_summary["consistent_residual_jacobian_newton_gate_passed"] is False
    assert proof_summary["ready"] is False
    assert (
        "g1_full_load_lane::hip_consistency_proof_gate_not_passed"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_has_blockers"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_when_hip_proof_no_cpu_contract_missing(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    proof = _g1_hip_consistency_proof(ready=True)
    proof.pop("cpu_diagnostic_assembler_used")
    proof.pop("production_hip_residual_jacobian_path")
    g1_lane["hip_consistency_proof"] = proof
    g1_lane["blockers"] = []
    g1_lane["contract_pass"] = True
    g1_lane["status"] = "ready"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof_summary = payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof"
    ]
    assert proof_summary["ready"] is False
    assert proof_summary["cpu_diagnostic_assembler_used"] is None
    assert proof_summary["production_hip_residual_jacobian_path"] is None
    assert (
        "g1_full_load_lane::hip_consistency_proof_cpu_diagnostic_assembler_not_explicitly_false"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_production_hip_path_not_proven"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_when_hip_proof_used_cpu_diagnostic(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["hip_consistency_proof"] = {
        **_g1_hip_consistency_proof(ready=True),
        "execution_mode": "cpu_diagnostic",
        "cpu_diagnostic_assembler_used": True,
        "production_hip_residual_jacobian_path": False,
    }
    g1_lane["blockers"] = []
    g1_lane["contract_pass"] = True
    g1_lane["status"] = "ready"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof_summary = payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof"
    ]
    assert proof_summary["ready"] is False
    assert proof_summary["cpu_diagnostic_assembler_used"] is True
    assert proof_summary["production_hip_residual_jacobian_path"] is False
    assert (
        "g1_full_load_lane::hip_consistency_proof_cpu_diagnostic_assembler_not_explicitly_false"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_production_hip_path_not_proven"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_with_stale_hip_consistency_proof_source(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["hip_consistency_proof"] = {
        **_g1_hip_consistency_proof(ready=True),
        "source_commit_sha": "old-hip-proof-source",
    }
    # Simulate a buggy lane report that forgot to mirror the source mismatch
    # at the lane top level. The canonical snapshot must still block release.
    g1_lane["blockers"] = []
    g1_lane["contract_pass"] = True
    g1_lane["status"] = "ready"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof = payload["components"]["g1"]["full_load_hip_newton_hip_consistency_proof"]
    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"][
        "full_load_hip_newton_hip_consistency_proof_ready"
    ] is False
    assert proof["ready"] is False
    assert proof["source_commit_sha"] == "old-hip-proof-source"
    assert (
        "g1_full_load_lane::hip_consistency_proof_source_commit_sha_mismatch"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_accepts_g1_hip_proof_receipt_only_source_state(
    tmp_path: Path,
) -> None:
    commit = "lane-source"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["hip_consistency_proof"] = {
        **_g1_hip_consistency_proof(ready=False),
        "source_commit_sha": "proof-source",
        "source_state_fresh": True,
        "source_state_kind": "receipt_only_commit",
        "changed_paths_since_source_commit": [
            "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
            "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
        ],
        "production_hip_residual_jacobian_path": True,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "receipt_blockers": ["consistent_residual_jacobian_not_closed"],
        "runtime_blockers": [],
    }
    g1_lane["blockers"] = [
        "hip_consistency_proof_gate_not_passed",
        "hip_consistency_proof_has_blockers",
    ]
    g1_lane["contract_pass"] = False
    g1_lane["status"] = "blocked"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    proof = payload["components"]["g1"]["full_load_hip_newton_hip_consistency_proof"]
    assert proof["ready"] is False
    assert proof["source_commit_sha"] == "proof-source"
    assert proof["source_state_fresh"] is True
    assert proof["source_state_kind"] == "receipt_only_commit"
    assert proof["changed_paths_since_source_commit"] == [
        "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
        "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
    ]
    assert (
        "g1_full_load_lane::hip_consistency_proof_source_commit_sha_mismatch"
        not in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_gate_not_passed"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::hip_consistency_proof_has_blockers"
        in _g1_detail_blockers(payload)
    )


def test_snapshot_blocks_ready_g1_lane_with_invalid_child_hip_refresh_schema(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_hip_refresh = _g1_child_hip_refresh_evidence()
    child_hip_refresh["schema_version"] = "wrong-schema.v1"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": child_hip_refresh,
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        payload["components"]["g1"][
            "full_load_hip_newton_child_hip_residual_refresh_ready"
        ]
        is False
    )
    assert (
        "g1_full_load_lane::child_hip_residual_refresh_evidence_schema_invalid"
        in _g1_detail_blockers(payload)
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_without_child_gate_evidence(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    g1_component = payload["components"]["g1"]
    assert g1_component["full_load_hip_newton_lane_ready"] is False
    assert g1_component["full_load_hip_newton_child_gate_ready"] is False
    assert "g1_full_load_lane::child_gate_evidence_missing" in _g1_detail_blockers(payload)
    assert "g1_full_load_lane::child_direct_residual_gate_not_proven" in _g1_detail_blockers(payload)
    assert "g1_full_load_lane::child_relative_increment_gate_not_proven" in _g1_detail_blockers(payload)
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_with_invalid_child_gate_schema(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_gate_evidence = _g1_child_gate_evidence()
    child_gate_evidence["schema_version"] = "wrong-schema.v1"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": child_gate_evidence,
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"]["full_load_hip_newton_child_gate_ready"] is False
    assert "g1_full_load_lane::child_gate_evidence_schema_invalid" in _g1_detail_blockers(payload)
    assert payload["paid_pilot_ready"] is False


def test_snapshot_surfaces_g1_child_contract_gate_conflict_blockers(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_gate_evidence = _g1_child_gate_evidence(ready=False)
    child_gate_evidence["blockers"].extend([
        "child_material_newton_contract_gate_conflict",
        "child_consistent_residual_jacobian_contract_gate_conflict",
    ])
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": False,
        "status": "blocked",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": child_gate_evidence,
        "blockers": [
            "child_direct_residual_gate_not_proven",
            "child_relative_increment_gate_not_proven",
            "child_material_newton_contract_gate_conflict",
            "child_consistent_residual_jacobian_contract_gate_conflict",
        ],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        "g1_full_load_lane::child_material_newton_contract_gate_conflict"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::child_direct_residual_gate_not_proven"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::child_relative_increment_gate_not_proven"
        in _g1_detail_blockers(payload)
    )
    assert (
        "g1_full_load_lane::child_consistent_residual_jacobian_contract_gate_conflict"
        in _g1_detail_blockers(payload)
    )
    child_gate = payload["components"]["g1"]["full_load_hip_newton_child_gate"]
    assert "child_material_newton_contract_gate_conflict" in child_gate["blockers"]
    assert (
        "child_consistent_residual_jacobian_contract_gate_conflict"
        in child_gate["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_requires_fresh_full_load_g1_lane_for_paid_pilot(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": True,
        "full_g1_closure_blockers": [],
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_mesh_full_load_ready"] is True
    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        payload["components"]["g1"]["full_load_hip_newton_lane_reused_evidence"]
        is True
    )
    assert "g1_full_load_lane::reused_evidence_not_false" in _g1_detail_blockers(payload)
    assert payload["paid_pilot_ready"] is False


def test_snapshot_check_passes_when_stored_snapshot_matches_current_inputs(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Simulate the volatile generated_at advancing on a subsequent regeneration.
    existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
    existing["generated_at"] = "2099-01-01T00:00:00+00:00"
    snapshot_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True, message
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["release_ready"] is True


def test_snapshot_check_fails_when_stored_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_missing:")
    assert "product_readiness_snapshot.json" in message
    assert generated is None
    assert snapshot_path.exists() is False


def test_snapshot_check_fails_when_stored_snapshot_is_unreadable(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text("{ this is not valid json", encoding="utf-8")

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_unreadable:")
    assert "product_readiness_snapshot.json" in message
    assert generated is None


def test_snapshot_check_fails_when_stored_snapshot_is_semantically_different(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    # Inject a stale semantic change that must be detected by --check.
    payload["status"] = "ready"
    payload["evidence_fresh"] = True
    payload["release_ready"] = True
    payload["blockers"] = []
    payload["blocker_count"] = 0
    payload["components"]["pm_release"]["release_area_green_count"] = 0
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "components.pm_release.release_area_green_count" in message
    assert generated is not None
    assert generated["status"] == "ready"
    assert generated["components"]["pm_release"]["release_area_green_count"] == 16


def test_snapshot_check_fails_when_stored_snapshot_blocks_count_drifts(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["blockers"] = []
    payload["blocker_count"] = 0
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Change an upstream input so the freshly generated snapshot accumulates a
    # new blocker. The stored snapshot must be reported as stale.
    ci_payload = json.loads(
        (tmp_path / "github_actions_ci_streak_evidence.json").read_text(encoding="utf-8")
    )
    ci_payload["contract_pass"] = False
    ci_payload["summary"]["pr_threshold_pass"] = False
    ci_payload["summary"]["nightly_threshold_pass"] = False
    ci_payload["lanes"] = {
        "pr": {"blockers": ["pr_github_actions_30_consecutive_pass_evidence_missing"]},
        "nightly": {"blockers": ["nightly_github_actions_30_consecutive_pass_evidence_missing"]},
    }
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", ci_payload)

    ok, message, _generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "blockers" in message
    assert "components.github_actions_ci_streak.ready" in message


def test_snapshot_check_ignores_volatile_generated_at_only(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
    # Top-level and nested generated_at must be ignored, every other field
    # must still match.
    existing["generated_at"] = "1900-01-01T00:00:00+00:00"
    for row in existing["state_consistency"]["metadata_rows"]:
        row["generated_at"] = "1900-01-01T00:00:00+00:00"
    snapshot_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, _generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True, message
    assert message == "snapshot_consistent"


def test_snapshot_check_ignores_top_level_snapshot_source_commit_only(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["source_commit_sha"] = "new-wrapper-commit-after-snapshot-was-checked-in"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["source_commit_sha"] == commit


def test_snapshot_check_accepts_receipt_only_commit_boundary_diagnostics(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    evidence_commit = _commit_all(tmp_path, "evidence")
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }
    assert payload["source_commit_sha"] == evidence_commit
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] = True
    metadata_rows["pm_release_gate_report"]["source_state_kind"] = "exact"
    metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"] = []
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    snapshot_commit = _commit_all(tmp_path, "snapshot")

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
    )

    assert ok is True, message
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["source_commit_sha"] == snapshot_commit
    generated_rows = {
        row["artifact"]: row
        for row in generated["state_consistency"]["metadata_rows"]
    }
    assert (
        generated_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert generated_rows["pm_release_gate_report"]["source_state_fresh"] is True


def test_snapshot_check_keeps_nested_source_commit_rows_semantic(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["state_consistency"]["metadata_rows"][0]["source_commit_sha"] = (
        "stale-upstream-evidence-commit"
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "state_consistency.metadata_rows" in message
    assert generated is not None


def test_snapshot_check_ignores_receipt_only_metadata_diagnostics(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    for row in payload["state_consistency"]["metadata_rows"]:
        row["changed_paths_since_source_commit"] = [
            "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
        ]
        row["source_commit_matches_head"] = False
        row["source_state_kind"] = "receipt_only_commit"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None


def test_snapshot_check_keeps_metadata_freshness_verdict_semantic(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["state_consistency"]["metadata_rows"][0]["source_state_fresh"] = False
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "state_consistency.metadata_rows" in message
    assert generated is not None


def test_snapshot_check_ignores_receipt_only_worktree_diagnostics(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )
    _write_json(snapshot_path, {"schema_version": "product-readiness-snapshot.v1"})
    _commit_all(tmp_path, "receipt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["state_consistency"]["worktree"]["dirty"] is False
    assert generated["state_consistency"]["worktree"]["status_rows"] == [
        " M implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
    ]
    assert generated["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == []


def test_snapshot_check_does_not_ignore_unrelated_status_rows(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["components"]["github_actions_runner_policy"]["status_rows"] = [
        "stale semantic row",
    ]
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "components.github_actions_runner_policy.status_rows" in message
    assert generated is not None


def test_main_check_returns_zero_on_match_and_writes_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.write_text('{"schema_version":"product-readiness-snapshot.v1"}\n', encoding="utf-8")

    monkeypatch.setattr(
        build_product_readiness_snapshot, "ROOT", tmp_path
    )

    def fake_check_snapshot_consistency(
        *,
        repo_root,
        out_path,
        paths=build_product_readiness_snapshot.SnapshotInputPaths(),
        source_commit_sha=None,
    ):
        assert repo_root == tmp_path
        assert out_path == snapshot_path
        return True, "snapshot_consistent", {"release_ready": True}

    monkeypatch.setattr(
        build_product_readiness_snapshot,
        "check_snapshot_consistency",
        fake_check_snapshot_consistency,
    )
    mtime_before = snapshot_path.stat().st_mtime_ns
    contents_before = snapshot_path.read_text(encoding="utf-8")

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--check",
        ]
    )

    assert exit_code == 0
    assert snapshot_path.stat().st_mtime_ns == mtime_before
    assert snapshot_path.read_text(encoding="utf-8") == contents_before


def test_main_no_write_prints_snapshot_without_touching_out(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.write_text(
        '{"schema_version":"existing-product-readiness-snapshot.v1"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(build_product_readiness_snapshot, "ROOT", tmp_path)

    def fake_build_snapshot():
        return {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "ready",
            "release_ready": True,
        }

    monkeypatch.setattr(
        build_product_readiness_snapshot,
        "build_snapshot",
        fake_build_snapshot,
    )
    mtime_before = snapshot_path.stat().st_mtime_ns
    contents_before = snapshot_path.read_text(encoding="utf-8")

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--json",
            "--no-write",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["schema_version"] == "product-readiness-snapshot.v1"
    assert snapshot_path.stat().st_mtime_ns == mtime_before
    assert snapshot_path.read_text(encoding="utf-8") == contents_before


def test_help_documents_non_mutating_snapshot_modes(capsys) -> None:
    try:
        build_product_readiness_snapshot.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    output = capsys.readouterr().out
    normalized = " ".join(output.split())
    assert "--no-write" in output
    assert "protected evidence files are not refreshed accidentally" in normalized
    assert "top-level source_commit_sha wrapper" in normalized


def test_main_check_returns_nonzero_on_missing_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    _write_ready_snapshot_inputs(tmp_path, commit="abc123")
    monkeypatch.setattr(build_product_readiness_snapshot, "ROOT", tmp_path)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    assert not snapshot_path.exists()

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--check",
        ]
    )

    assert exit_code == 2
    assert not snapshot_path.exists()
