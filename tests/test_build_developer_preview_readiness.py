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
    assert payload["blockers"] == []
    assert payload["scope"]["freeze_policy"] == {
        "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
        "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
        "gpu_hip": "performance_track_after_cpu_reference_parity",
    }
    assert payload["future_commercial_blocker_count"] == 4
    assert payload["categories"]["future commercial"]["blocker_count"] == 4
    assert "customer shadow" in payload["claim_boundary"].lower()


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
    assert payload["categories"]["future commercial"]["blocker_count"] == 0
    release_sync = payload["root_blocker_evidence"]["product_snapshot_root_blockers"][
        "release freshness/sync"
    ]
    assert release_sync["blockers"] == ["stale_or_inconsistent:worktree_dirty"]
    cleanup_plan = payload["root_blocker_evidence"]["phase3_release_control_cleanup_plan"]
    assert cleanup_plan["status"] == "blocked"
    assert cleanup_plan["candidate_release_control_commit_set_count"] == 23
    assert cleanup_plan["human_git_action_required"] is True


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
        "getArray(scope, 'excluded'); `scope=${scopeSummary}`; "
        "`excludes=${exclusionSummary}`; customer shadow; license/legal approval; "
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
    assert sync["doc_surfaces"]["README.md"]["included_scope_anchor_count"] == 4
    assert sync["doc_surfaces"]["README.md"]["excluded_scope_anchor_count"] == 5
    assert sync["gui_surface"]["consumes_included_scope"] is True
    assert sync["gui_surface"]["consumes_excluded_scope"] is True


def test_dataset_license_manifest_documents_non_bundled_sources() -> None:
    payload = build_developer_preview_readiness.build_dataset_license_manifest(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "developer-preview-dataset-license-manifest.v1"
    assert payload["contract_pass"] is False
    assert payload["dataset_count"] == 5
    assert "analytic_truth" in payload["truth_classes"]
    assert "dataset_license_manifest:source_checksums_pending" not in payload["blockers"]
    assert "dataset_license_manifest:authoritative_source_checksums_pending=4" in payload["blockers"]
    assert payload["phase3_lane_coverage"] == {
        "covered_lane_count": 9,
        "required_lane_count": 9,
        "covered_lanes": [
            "analytic-small",
            "buildingsmart-clean-ifc",
            "buildingsmart-dirty-ifc",
            "commercial-cross-solver",
            "element-patch",
            "ifc-query-and-gui",
            "large-model-performance",
            "opensees-medium",
            "opensees-megatall",
        ],
        "missing_lanes": [],
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
    assert "| future commercial | 1 | no, future commercial only |" in markdown
    assert "IFC/MGT/neutral JSON import" in markdown
    assert "customer shadow evidence as a Developer Preview blocker" in markdown
    assert "commercial license/legal approval" in markdown
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
