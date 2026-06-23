from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_developer_preview_readiness.py"
REPO_ROOT = SCRIPT_PATH.parent.parent
SPEC = importlib.util.spec_from_file_location("build_developer_preview_readiness", SCRIPT_PATH)
build_developer_preview_readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_developer_preview_readiness
assert SPEC.loader is not None
SPEC.loader.exec_module(build_developer_preview_readiness)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_developer_preview_excludes_future_commercial_blockers(tmp_path: Path) -> None:
    product_snapshot = _write_json(
        tmp_path / "product_readiness_snapshot.json",
        {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "blocked",
            "schema_valid": True,
            "evidence_fresh": True,
            "release_ready": False,
            "blockers": [
                "customer_shadow::completed_evidence_row_count_below_minimum",
                "license::license_status_not_active",
                "ci_streak::pr_github_actions_30_consecutive_pass_evidence_missing",
                "external_benchmark::submission_receipts_pending=4",
                "pm_release::security::license_status_not_configured",
                "pm_release::github_sync::github_sync_remote_sync_pending",
                (
                    "independent_product::Strict external and residual holdout evidence::"
                    "external_receipt_or_closure_pending:tpu_hffb"
                ),
            ],
        },
    )
    manifest = _write_json(
        tmp_path / "developer_preview_dataset_license_manifest.json",
        {
            "schema_version": "developer-preview-dataset-license-manifest.v1",
            "status": "ready",
            "contract_pass": True,
            "blockers": [],
            "dataset_count": 4,
        },
    )

    payload = build_developer_preview_readiness.build_developer_preview_readiness(
        repo_root=tmp_path,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )

    assert payload["developer_preview_ready"] is True
    assert payload["commercial_release_ready"] is False
    assert payload["reused_evidence"] is False
    assert "does_not_create_authoritative_closure_evidence" in payload["reuse_policy"]
    assert payload["input_checksum_policy"] == (
        "product_snapshot_readiness_semantic_subset_excludes_self_referential_"
        "developer_preview_metadata"
    )
    assert payload["input_artifacts"]["product_readiness_snapshot"]["present"] is True
    assert payload["input_artifacts"]["product_readiness_snapshot"]["schema_version"] == (
        "product-readiness-snapshot.v1"
    )
    assert payload["input_artifacts"]["product_readiness_snapshot"]["input_checksum"].startswith(
        "sha256:"
    )
    assert payload["input_artifacts"]["dataset_license_manifest"]["present"] is True
    assert payload["input_artifacts"]["dataset_license_manifest"]["schema_version"] == (
        "developer-preview-dataset-license-manifest.v1"
    )
    assert payload["input_artifacts"]["dataset_license_manifest"]["input_checksum"].startswith(
        "sha256:"
    )
    closure_visibility = payload["gap_ledger_closure_requirement_visibility"]
    assert closure_visibility["source_status"] == "missing"
    assert closure_visibility["closure_requirement_fail_count"] == 0
    assert closure_visibility["nonclosed_failed_closure_requirement_ids"] == []
    assert payload["blockers"] == []
    assert payload["scope"]["freeze_policy"] == {
        "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
        "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
        "gpu_hip": "performance_track_after_cpu_reference_parity",
    }
    assert payload["future_commercial_blocker_count"] == 9
    assert payload["categories"]["future commercial"]["blocker_count"] == 9
    assert "pm_release::security::license_status_not_configured" in payload[
        "future_commercial_blockers"
    ]
    assert "pm_release::github_sync::github_sync_remote_sync_pending" in payload[
        "future_commercial_blockers"
    ]
    assert (
        "independent_product::Strict external and residual holdout evidence::"
        "external_receipt_or_closure_pending:tpu_hffb"
    ) in payload["future_commercial_blockers"]
    assert "commercial_sla::production_support_commitment_missing" in payload[
        "future_commercial_blockers"
    ]
    assert "license_server::operation_readiness_missing" in payload[
        "future_commercial_blockers"
    ]
    assert "customer shadow" in payload["claim_boundary"].lower()
    assert "license-server operation" in payload["claim_boundary"].lower()


def test_developer_preview_keeps_numerical_benchmark_and_software_blockers(tmp_path: Path) -> None:
    product_snapshot = _write_json(
        tmp_path / "product_readiness_snapshot.json",
        {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "stale_or_inconsistent",
            "schema_valid": True,
            "evidence_fresh": False,
            "release_ready": False,
            "blockers": [
                "g1_full_load_lane::child_residual_gate_not_proven",
                "fresh_full_validation::row_count_below_lane_count",
                "stale_or_inconsistent:worktree_dirty",
            ],
            "root_blockers": {
                "release freshness/sync": {
                    "blocked": True,
                    "blocker_count": 1,
                    "blockers": ["stale_or_inconsistent:worktree_dirty"],
                },
            },
            "state_consistency": {
                "worktree": {
                    "phase3_release_control_cleanup_plan": {
                        "status": "blocked",
                        "contract_pass": False,
                        "candidate_release_control_commit_set_count": 23,
                        "human_git_action_required": True,
                        "codex_commit_or_push_performed": False,
                    },
                },
            },
            "components": {
                "gap_ledger_evidence_audit": {
                    "status": "ready",
                    "contract_pass": True,
                    "full_gap_ledger_ready": False,
                    "ledger_split_summary": {
                        "commercial_solver": {
                            "row_count": 10,
                            "nonclosed_row_count": 3,
                            "closure_requirement_count": 18,
                            "closure_requirement_pass_count": 3,
                            "closure_requirement_fail_count": 15,
                            "nonclosed_rows_with_failed_closure_requirements_count": 3,
                            "nonclosed_failed_closure_requirement_ids": [
                                "G1:full_load_scale_1_0_reached",
                                "G6:eb_receipt_hardest_external_10case",
                                "G7:operator_manifest_source_mapping_clear",
                            ],
                        },
                        "ai_engine": {
                            "row_count": 10,
                            "nonclosed_row_count": 0,
                            "closure_requirement_count": 0,
                            "closure_requirement_pass_count": 0,
                            "closure_requirement_fail_count": 0,
                            "nonclosed_rows_with_failed_closure_requirements_count": 0,
                            "nonclosed_failed_closure_requirement_ids": [],
                        },
                    },
                },
                "fresh_full_validation": {
                    "contract_pass": False,
                    "ready": False,
                    "blocker_grouping_metadata": {
                        "schema_version": "fresh-full-validation-blocker-groups.v1",
                        "groups": {
                            "fresh_receipt_presence": {
                                "scope": "fresh_validation_receipt_required",
                                "blocker_count": 1,
                                "blockers": [
                                    "gpu_hip_solver::fresh_validation_receipt_missing"
                                ],
                            },
                        },
                    },
                    "lane_boundary_metadata": {
                        "schema_version": "fresh-full-validation-lane-boundaries.v1",
                        "lanes": {
                            "gpu_hip_solver": {
                                "scope": "performance_track_after_cpu_reference_parity"
                            },
                        },
                    },
                },
                "g1": {
                    "contract_pass": True,
                    "full_mesh_full_load_ready": False,
                    "full_g1_closure_ready": False,
                    "top_level_blockers": [
                        "g1::full_load_gate_not_closed",
                        "g1::full_mesh_nonlinear_equilibrium_not_closed",
                        "g1::material_newton_breadth_not_closed",
                        "g1::production_rocm_hip_residency_not_closed",
                    ],
                    "suppressed_detail_blockers": [
                        "g1_full_mesh_full_load_not_closed",
                        "g1_full_load_lane::checkpoint_load_scale_below_required_full_load",
                    ],
                    "blocker_grouping_metadata": {
                        "grouping_promotes_status": False,
                        "detail_blockers_remain_visible": True,
                        "root_blocker_count": 4,
                        "suppressed_detail_blocker_count": 2,
                        "unmatched_detail_blockers": [],
                    },
                    "closure_boundary_metadata": {
                        "metadata_promotes_status": False,
                        "gpu_hip_replaces_cpu_parity": False,
                        "cpu_parity_required_before_gpu_performance_promotion": True,
                        "claim_boundary": (
                            "CPU full-load/full-mesh/material Newton closure is the "
                            "numerical priority gate; GPU/HIP does not replace CPU parity."
                        ),
                    },
                },
            },
        },
    )
    manifest = _write_json(
        tmp_path / "developer_preview_dataset_license_manifest.json",
        {
            "schema_version": "developer-preview-dataset-license-manifest.v1",
            "status": "blocked",
            "contract_pass": False,
            "blockers": ["dataset_license_manifest:authoritative_source_checksums_pending=4"],
            "dataset_count": 5,
        },
    )

    payload = build_developer_preview_readiness.build_developer_preview_readiness(
        repo_root=tmp_path,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )

    assert payload["developer_preview_ready"] is False
    assert payload["blocker_count"] == 4
    assert payload["categories"]["numerical"]["blocker_count"] == 1
    assert payload["categories"]["benchmark"]["blocker_count"] == 2
    assert payload["categories"]["software product"]["blocker_count"] == 1
    assert payload["categories"]["future commercial"]["blocker_count"] == 2
    assert "commercial_sla::production_support_commitment_missing" in payload[
        "future_commercial_blockers"
    ]
    assert "license_server::operation_readiness_missing" in payload[
        "future_commercial_blockers"
    ]
    release_sync = payload["root_blocker_evidence"]["product_snapshot_root_blockers"][
        "release freshness/sync"
    ]
    assert release_sync["blockers"] == ["stale_or_inconsistent:worktree_dirty"]
    cleanup_plan = payload["root_blocker_evidence"]["phase3_release_control_cleanup_plan"]
    assert cleanup_plan["status"] == "blocked"
    assert cleanup_plan["candidate_release_control_commit_set_count"] == 23
    assert cleanup_plan["human_git_action_required"] is True
    fresh_boundary = payload["root_blocker_evidence"]["fresh_full_validation"]
    assert fresh_boundary["blocker_grouping_metadata"]["schema_version"] == (
        "fresh-full-validation-blocker-groups.v1"
    )
    assert fresh_boundary["lane_boundary_metadata"]["lanes"]["gpu_hip_solver"]["scope"] == (
        "performance_track_after_cpu_reference_parity"
    )
    g1_boundary = payload["root_blocker_evidence"]["g1"]
    assert g1_boundary["blocker_grouping_metadata"]["grouping_promotes_status"] is False
    assert g1_boundary["blocker_grouping_metadata"]["detail_blockers_remain_visible"] is True
    assert g1_boundary["blocker_grouping_metadata"]["unmatched_detail_blockers"] == []
    assert g1_boundary["closure_boundary_metadata"]["metadata_promotes_status"] is False
    assert g1_boundary["closure_boundary_metadata"]["gpu_hip_replaces_cpu_parity"] is False
    assert (
        g1_boundary["closure_boundary_metadata"][
            "cpu_parity_required_before_gpu_performance_promotion"
        ]
        is True
    )
    closure_visibility = payload["gap_ledger_closure_requirement_visibility"]
    assert closure_visibility["source_status"] == "ready"
    assert closure_visibility["source_contract_pass"] is True
    assert closure_visibility["source_full_gap_ledger_ready"] is False
    assert closure_visibility["closure_requirement_count"] == 18
    assert closure_visibility["closure_requirement_pass_count"] == 3
    assert closure_visibility["closure_requirement_fail_count"] == 15
    assert closure_visibility["nonclosed_rows_with_failed_closure_requirements_count"] == 3
    assert closure_visibility["nonclosed_failed_closure_requirement_ids"] == [
        "G1:full_load_scale_1_0_reached",
        "G6:eb_receipt_hardest_external_10case",
        "G7:operator_manifest_source_mapping_clear",
    ]
    commercial_solver = closure_visibility["ledgers"]["commercial_solver"]
    assert commercial_solver["closure_requirement_fail_count"] == 15
    assert "does not add Developer Preview blockers" in closure_visibility["claim_boundary"]


def test_developer_preview_scope_boundary_sync_receipt_checks_docs_and_gui(
    tmp_path: Path,
) -> None:
    product_snapshot = _write_json(
        tmp_path / "product_readiness_snapshot.json",
        {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "blocked",
            "schema_valid": True,
            "evidence_fresh": True,
            "release_ready": False,
            "blockers": [],
        },
    )
    manifest = _write_json(
        tmp_path / "developer_preview_dataset_license_manifest.json",
        {
            "schema_version": "developer-preview-dataset-license-manifest.v1",
            "status": "ready",
            "contract_pass": True,
            "blockers": [],
            "dataset_count": 4,
        },
    )
    scope_text = (
        "Open Benchmark Developer Preview readiness: public/open benchmark import, "
        "deterministic analysis/reporting, benchmark scorecards, and local GUI review. "
        "It excludes permit automation, engineer replacement, SaaS/account/license server, "
        "commercial SLA, and AI/GNN truth claims. Customer shadow, license approval, "
        "30-run CI streak, and external approval receipts remain future Commercial Release blockers."
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(scope_text, encoding="utf-8")
    (tmp_path / "docs" / "commercialization-gap-current-state.md").write_text(
        scope_text,
        encoding="utf-8",
    )
    app_text = (
        "function buildDeveloperPreviewSnapshot() { "
        "getRecord(resource.data, 'scope'); getArray(scope, 'included'); "
        "getRecord(resource.data, 'gap_ledger_closure_requirement_visibility'); "
        "getArray(closureVisibility, 'nonclosed_failed_closure_requirement_ids'); "
        "getArray(scope, 'excluded'); `scope=${scopeSummary}`; "
        "`excludes=${exclusionSummary}`; "
        "`closure requirements=${closureRequirementSummary}`; "
        "visibility only; no G1/G6/G7 closure; customer shadow; license/legal approval; "
        "commercial SLA; 30-run CI streak; external approval receipts; }"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text(app_text, encoding="utf-8")

    payload = build_developer_preview_readiness.build_developer_preview_readiness(
        repo_root=tmp_path,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )

    sync = payload["scope_boundary_sync"]
    assert sync["status"] == "ready"
    assert sync["contract_pass"] is True
    assert sync["surface_groups"]["readme"]["path"] == "README.md"
    assert sync["surface_groups"]["readme"]["contract_pass"] is True
    assert sync["surface_groups"]["reports"]["surface_count"] == 1
    assert sync["surface_groups"]["reports"]["contract_pass_count"] == 1
    assert sync["surface_groups"]["reports"]["surfaces"][
        "docs/commercialization-gap-current-state.md"
    ]["contract_pass"] is True
    assert sync["surface_groups"]["gui"]["contract_pass"] is True
    assert sync["doc_surfaces"]["README.md"]["included_scope_anchor_count"] == 4
    assert sync["doc_surfaces"]["README.md"]["excluded_scope_anchor_count"] == 5
    assert sync["gui_surface"]["consumes_included_scope"] is True
    assert sync["gui_surface"]["consumes_excluded_scope"] is True
    assert sync["gui_surface"]["consumes_closure_visibility_record"] is True
    assert sync["gui_surface"]["consumes_failed_closure_requirement_ids"] is True
    assert sync["gui_surface"]["renders_closure_requirement_summary"] is True
    assert sync["gui_surface"]["renders_closure_visibility_boundary"] is True


def test_dataset_license_manifest_documents_non_bundled_sources() -> None:
    payload = build_developer_preview_readiness.build_dataset_license_manifest(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "developer-preview-dataset-license-manifest.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["dataset_count"] == 5
    assert "analytic_truth" in payload["truth_classes"]
    assert "dataset_license_manifest:source_checksums_pending" not in payload["blockers"]
    assert payload["blockers"] == []
    manifest_contract = payload["manifest_policy_contract"]
    assert manifest_contract["status"] == "ready"
    assert manifest_contract["contract_pass"] is True
    assert manifest_contract["policy_fixed"] is True
    assert manifest_contract["phase3_lane_coverage_contract_pass"] is True
    assert manifest_contract["developer_preview_seed_contract"] == {
        "status": "ready",
        "contract_pass": True,
        "bundle_eligible_source_ids": ["analytic-small"],
        "required_checks": [
            "repo_generated_license",
            "source_checksums",
            "per_case_seed_checksums",
            "expected_outputs_attached",
            "non_bundled_external_sources_visible",
        ],
    }
    assert manifest_contract["additional_repo_generated_seed_lanes"] == [
        "nonlinear-material-mesh"
    ]
    assert manifest_contract["repo_generated_bundle_source_ids"] == ["analytic-small"]
    assert manifest_contract["non_bundled_source_ids"] == [
        "opensees-megatall",
        "buildingsmart-ifc-samples",
        "ifc-query-and-gui-public-corpus",
        "commercial-cross-solver-imports",
    ]
    assert manifest_contract["authoritative_checksum_complete_source_ids"] == ["analytic-small"]
    assert manifest_contract["authoritative_checksum_pending_source_ids"] == [
        "opensees-megatall",
        "buildingsmart-ifc-samples",
        "ifc-query-and-gui-public-corpus",
        "commercial-cross-solver-imports",
    ]
    assert manifest_contract["expected_outputs_attached_source_ids"] == ["analytic-small"]
    assert manifest_contract["expected_outputs_pending_source_ids"] == [
        "opensees-megatall",
        "buildingsmart-ifc-samples",
        "ifc-query-and-gui-public-corpus",
        "commercial-cross-solver-imports",
    ]
    assert manifest_contract["redistribution_allowed_source_ids"] == ["analytic-small"]
    assert manifest_contract["redistribution_pending_source_ids"] == [
        "opensees-megatall",
        "buildingsmart-ifc-samples",
        "ifc-query-and-gui-public-corpus",
        "commercial-cross-solver-imports",
    ]
    assert manifest_contract["pending_counts"] == {
        "authoritative_source_checksums_pending": 4,
        "license_or_redistribution_pending": 4,
        "expected_outputs_pending": 4,
    }
    assert payload["phase3_external_corpus_readiness"] == {
        "status": "blocked",
        "contract_pass": False,
        "blockers": [
            "phase3_external_corpus:authoritative_source_checksums_pending=4",
            "phase3_external_corpus:license_or_redistribution_review_pending",
            "phase3_external_corpus:expected_outputs_pending",
        ],
        "authoritative_checksum_pending_source_ids": [
            "opensees-megatall",
            "buildingsmart-ifc-samples",
            "ifc-query-and-gui-public-corpus",
            "commercial-cross-solver-imports",
        ],
        "redistribution_pending_source_ids": [
            "opensees-megatall",
            "buildingsmart-ifc-samples",
            "ifc-query-and-gui-public-corpus",
            "commercial-cross-solver-imports",
        ],
        "expected_outputs_pending_source_ids": [
            "opensees-megatall",
            "buildingsmart-ifc-samples",
            "ifc-query-and-gui-public-corpus",
            "commercial-cross-solver-imports",
        ],
        "claim_boundary": (
            "These blockers prevent full Phase 3 corpus quantity credit and Developer "
            "Preview RC final-gate promotion, but they do not block the seed-only "
            "dataset/license manifest deliverable."
        ),
    }
    assert payload["phase3_lane_coverage"] == {
        "covered_lane_count": 10,
        "required_lane_count": 9,
        "covered_lanes": [
            "analytic-small",
            "buildingsmart-clean-ifc",
            "buildingsmart-dirty-ifc",
            "commercial-cross-solver",
            "element-patch",
            "ifc-query-and-gui",
            "large-model-performance",
            "nonlinear-material-mesh",
            "opensees-medium",
            "opensees-megatall",
        ],
        "missing_lanes": [],
        "additional_repo_generated_seed_lanes": ["nonlinear-material-mesh"],
        "contract_pass": True,
    }
    assert payload["phase3_acquisition_plan"]["status"] == "blocked"
    assert payload["phase3_acquisition_plan"]["ready_source_count"] == 0
    assert payload["phase3_acquisition_plan"]["all_non_seed_lanes_have_acquisition_policy"] is True
    assert (
        payload["phase3_acquisition_plan"][
            "all_non_seed_sources_have_license_checksum_and_expected_outputs"
        ]
        is False
    )
    sources = {row["source_id"]: row for row in payload["sources"]}

    analytic = sources["analytic-small"]
    assert analytic["developer_preview_bundle_policy"] == "repo_generated_cases_may_be_bundled"
    assert analytic["selected_benchmark_lanes"] == [
        "analytic-small",
        "element-patch",
        "nonlinear-material-mesh",
    ]
    assert analytic["checksum_status"] == "complete_repo_generated_seed_manifest_and_factory_sources"
    assert analytic["source_files"]
    assert all(row["checksum"].startswith("sha256:") for row in analytic["source_files"])

    opensees = sources["opensees-megatall"]
    assert opensees["developer_preview_bundle_policy"] == "not_bundled_user_acquisition_required"
    assert opensees["redistribution_allowed"] is False
    assert opensees["commercial_use_allowed"] is False
    assert opensees["checksum_status"] == "local_medium_candidate_checksums_attached_authoritative_source_pending"
    assert any(row["checksum"].startswith("sha256:") for row in opensees["source_files"])
    assert "authoritative upstream source" in opensees["source_checksum_policy"].lower()
    assert opensees["phase3_acquisition_policy"]["source_ids"] == [
        "opensees_scbf16b_medium_candidate",
        "opensees_megatall_model_2_large",
    ]
    assert opensees["phase3_acquisition_policy"]["ready_for_phase3_quantity_credit"] is False
    assert "license_review_pending" in opensees["phase3_acquisition_policy"]["blockers"]

    buildingsmart = sources["buildingsmart-ifc-samples"]
    assert buildingsmart["source_files"] == []
    assert buildingsmart["developer_preview_bundle_policy"] == "not_bundled_until_upstream_license_review"
    assert buildingsmart["supporting_receipt"].endswith("phase3_ifc_source_license_receipt.json")
    assert buildingsmart["acquisition_receipt"].endswith("phase3_buildingsmart_ifc_acquisition_receipt.json")
    assert buildingsmart["dirty_acquisition_receipt"].endswith(
        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
    )
    assert buildingsmart["import_health_execution_receipt"].endswith(
        "phase3_ifc_import_health_execution_receipt.json"
    )
    assert buildingsmart["expected_outputs_status"] == (
        "authored_import_health_and_negative_contracts_pending_execution"
    )
    assert buildingsmart["phase3_acquisition_policy"]["source_ids"] == [
        "buildingsmart_clean_ifc_samples",
        "buildingsmart_dirty_ifc_samples",
    ]
    assert "silent_import_loss_gate_not_executed" in buildingsmart["phase3_acquisition_policy"]["blockers"]
    assert (
        "silent_import_loss_gate_not_implemented"
        not in buildingsmart["phase3_acquisition_policy"]["blockers"]
    )
    assert "silent_import_loss_gate_not_implemented" not in json.dumps(payload, sort_keys=True)

    ifc_query = sources["ifc-query-and-gui-public-corpus"]
    assert ifc_query["source_files"] == []
    assert ifc_query["truth_class"] == "query_and_gui_task_truth"
    assert ifc_query["developer_preview_bundle_policy"] == "not_bundled_until_per_file_license_review"
    assert ifc_query["supporting_receipt"].endswith("phase3_ifc_source_license_receipt.json")
    assert ifc_query["phase3_acquisition_policy"]["source_ids"] == ["ifc_query_and_gui_public_corpus"]
    assert "query_expected_answers_missing" in ifc_query["phase3_acquisition_policy"]["blockers"]

    commercial = sources["commercial-cross-solver-imports"]
    assert commercial["source_files"] == []
    assert commercial["developer_preview_bundle_policy"] == "not_bundled_operator_attachment_required"
    assert commercial["import_template"].endswith("phase4_commercial_comparison_import_template.json")
    assert commercial["operator_reference_contract"].endswith(
        "phase4_commercial_operator_reference_contract.json"
    )
    assert commercial["operator_reference_ingest_validator"].endswith(
        "phase4_commercial_operator_reference_ingest_validator.json"
    )
    assert commercial["status"] == "template_and_contract_only"
    assert commercial["expected_outputs_status"] == (
        "authored_import_template_and_operator_contract_pending_reference_outputs"
    )
    assert commercial["phase3_acquisition_policy"]["source_ids"] == [
        "commercial_cross_solver_operator_imports"
    ]
    assert "operator_reference_outputs_missing" in commercial["phase3_acquisition_policy"]["blockers"]
    assert "operator_reference_package_missing" in commercial["phase3_acquisition_policy"]["blockers"]
    assert "operator_reference_ingest_validator_blocked" in commercial["phase3_acquisition_policy"]["blockers"]
    assert "cross_solver_mapping_expectations_missing" not in commercial["phase3_acquisition_policy"]["blockers"]
    assert "does not bundle" in payload["claim_boundary"]


def test_markdown_report_lists_scope_and_nonblocking_future_commercial(tmp_path: Path) -> None:
    product_snapshot = _write_json(
        tmp_path / "product_readiness_snapshot.json",
        {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "blocked",
            "schema_valid": True,
            "evidence_fresh": True,
            "release_ready": False,
            "blockers": ["license::license_status_not_active"],
            "components": {
                "gap_ledger_evidence_audit": {
                    "status": "ready",
                    "contract_pass": True,
                    "full_gap_ledger_ready": False,
                    "ledger_split_summary": {
                        "commercial_solver": {
                            "row_count": 10,
                            "nonclosed_row_count": 3,
                            "closure_requirement_count": 18,
                            "closure_requirement_pass_count": 3,
                            "closure_requirement_fail_count": 15,
                            "nonclosed_rows_with_failed_closure_requirements_count": 3,
                            "nonclosed_failed_closure_requirement_ids": [
                                "G1:full_load_scale_1_0_reached",
                            ],
                        },
                        "ai_engine": {
                            "row_count": 10,
                            "nonclosed_row_count": 0,
                            "closure_requirement_count": 0,
                            "closure_requirement_pass_count": 0,
                            "closure_requirement_fail_count": 0,
                            "nonclosed_rows_with_failed_closure_requirements_count": 0,
                            "nonclosed_failed_closure_requirement_ids": [],
                        },
                    },
                },
            },
        },
    )
    manifest = _write_json(
        tmp_path / "developer_preview_dataset_license_manifest.json",
        {
            "schema_version": "developer-preview-dataset-license-manifest.v1",
            "status": "ready",
            "contract_pass": True,
            "blockers": [],
            "dataset_count": 4,
        },
    )
    payload = build_developer_preview_readiness.build_developer_preview_readiness(
        repo_root=tmp_path,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )

    markdown = build_developer_preview_readiness._markdown(payload)

    assert "# Open Benchmark Developer Preview Readiness" in markdown
    assert "| future commercial | 3 | no, future commercial only |" in markdown
    assert "IFC/MGT/neutral JSON import" in markdown
    assert "customer shadow evidence as a Developer Preview blocker" in markdown
    assert "commercial license/legal approval" in markdown
    assert "does_not_create_authoritative_closure_evidence" in markdown
    assert "## Gap Ledger Closure Requirement Visibility" in markdown
    assert "`closure_requirements`: `3/18`" in markdown
    assert "`failed_closure_requirements`: `15`" in markdown
    assert "`G1:full_load_scale_1_0_reached`" in markdown
    assert "does not add Developer Preview blockers" in markdown
    assert (
        "product_snapshot_readiness_semantic_subset_excludes_self_referential_"
        "developer_preview_metadata"
    ) in markdown
    assert "## Freeze Policy" in markdown
    assert "`new_feature_development`: `frozen_until_developer_preview_baseline_is_clean`" in markdown
    assert (
        "`ai_training`: `frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed`"
        in markdown
    )
    assert "`gpu_hip`: `performance_track_after_cpu_reference_parity`" in markdown


def test_check_detects_json_and_markdown_drift(tmp_path: Path) -> None:
    product_snapshot = _write_json(
        tmp_path / "product_readiness_snapshot.json",
        {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "blocked",
            "schema_valid": True,
            "evidence_fresh": True,
            "release_ready": False,
            "blockers": [],
        },
    )
    manifest = _write_json(
        tmp_path / "developer_preview_dataset_license_manifest.json",
        {
            "schema_version": "developer-preview-dataset-license-manifest.v1",
            "status": "ready",
            "contract_pass": True,
            "blockers": [],
            "dataset_count": 4,
        },
    )
    payload = build_developer_preview_readiness.build_developer_preview_readiness(
        repo_root=tmp_path,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )
    out = _write_json(tmp_path / "developer_preview_readiness.json", payload)
    out_md = tmp_path / "developer_preview_readiness.md"
    out_md.write_text(build_developer_preview_readiness._markdown(payload), encoding="utf-8")

    ok, message = build_developer_preview_readiness.check_developer_preview_readiness(
        repo_root=tmp_path,
        out_path=out,
        out_md_path=out_md,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )
    assert ok is True
    assert message == "developer_preview_readiness_consistent"

    source_drifted = dict(payload)
    source_drifted["source_commit_sha"] = "previous-receipt-only-commit"
    _write_json(out, source_drifted)
    out_md.write_text(
        build_developer_preview_readiness._markdown(source_drifted),
        encoding="utf-8",
    )
    ok, message = build_developer_preview_readiness.check_developer_preview_readiness(
        repo_root=tmp_path,
        out_path=out,
        out_md_path=out_md,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )
    assert ok is True
    assert message == "developer_preview_readiness_consistent"

    drifted = dict(payload)
    drifted["blocker_count"] = 99
    _write_json(out, drifted)
    ok, message = build_developer_preview_readiness.check_developer_preview_readiness(
        repo_root=tmp_path,
        out_path=out,
        out_md_path=out_md,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )
    assert ok is False
    assert message == "developer_preview_readiness_semantic_mismatch"

    _write_json(out, payload)
    out_md.write_text("stale report\n", encoding="utf-8")
    ok, message = build_developer_preview_readiness.check_developer_preview_readiness(
        repo_root=tmp_path,
        out_path=out,
        out_md_path=out_md,
        product_snapshot_path=product_snapshot,
        dataset_license_manifest_path=manifest,
    )
    assert ok is False
    assert message == "developer_preview_readiness_report_mismatch"
