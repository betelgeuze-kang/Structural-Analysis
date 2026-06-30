from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_developer_preview_rc_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_developer_preview_rc_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_developer_preview_rc_status_aggregates_deliverables_without_promotion() -> None:
    payload = module.build_developer_preview_rc_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "developer-preview-rc-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_ready"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["developer_preview_ready"] is False
    assert payload["deliverable_count"] == 10
    assert payload["final_gate_count"] == 9
    assert payload["deliverable_pass_count"] == 10
    assert payload["final_gate_pass_count"] == 5

    deliverables = {row["item"]: row for row in payload["deliverables"]}
    assert deliverables["installable_python_package"]["contract_pass"] is True
    assert deliverables["structural_analysis_cli"]["contract_pass"] is True
    assert deliverables["local_web_gui_surface"]["contract_pass"] is True
    assert deliverables["benchmark_runner"]["contract_pass"] is True
    assert deliverables["benchmark_scorecard"]["contract_pass"] is True
    assert deliverables["known_limitations"]["contract_pass"] is True
    assert deliverables["reproducibility_bundle"]["contract_pass"] is True
    assert deliverables["commercial_comparison_import_template"]["contract_pass"] is True
    assert deliverables["sample_acquisition_command"]["contract_pass"] is True
    assert deliverables["dataset_license_manifest"]["contract_pass"] is True
    assert deliverables["dataset_license_manifest"]["blockers"] == []
    assert deliverables["sample_acquisition_command"]["blockers"] == []

    final_gates = {row["item"]: row for row in payload["final_gates"]}
    assert final_gates["analytic_component_benchmark_all_pass"]["contract_pass"] is True
    assert final_gates["unsupported_features_explicitly_blocked"]["contract_pass"] is True
    assert final_gates["selected_medium_models_pass_or_approved_review"]["contract_pass"] is False
    assert final_gates["large_models_crash_oom_free"]["contract_pass"] is False
    medium_blockers = final_gates["selected_medium_models_pass_or_approved_review"]["blockers"]
    assert "medium_structural_models_current_below_required:0/5" in medium_blockers
    assert "opensees_medium_runner_command_missing" not in medium_blockers
    assert "opensees_medium_scorecard_execution_missing" in medium_blockers
    assert "medium_model_pass_or_review_missing" in medium_blockers
    assert "reference_outputs_missing" in medium_blockers
    assert "medium_model_pass_or_review_below_required:0/5" in medium_blockers
    assert final_gates["selected_medium_models_pass_or_approved_review"]["evidence"].endswith(
        "phase6_benchmark_scale_status.json"
    )
    medium_gate_grouping = final_gates["selected_medium_models_pass_or_approved_review"][
        "blocker_grouping_metadata"
    ]
    assert medium_gate_grouping["schema_version"] == "phase6-benchmark-scale-blocker-groups.v1"
    assert medium_gate_grouping["blocker_count"] == len(medium_blockers)
    assert medium_gate_grouping["unassigned_blockers"] == []
    assert "medium_model_pass_or_review_below_required:0/5" in medium_gate_grouping[
        "groups"
    ]["medium_quantity_shortfall"]["blockers"]
    assert "topology/parser evidence does not count" in " ".join(
        final_gates["selected_medium_models_pass_or_approved_review"]["notes"]
    )
    large_blockers = final_gates["large_models_crash_oom_free"]["blockers"]
    assert "large_structural_models_current_below_required:0/2" not in large_blockers
    assert not any(blocker.startswith("large_structural_models_current_below_required") for blocker in large_blockers)
    assert "large_model_runner_not_implemented" not in large_blockers
    assert "nightly_lane_not_configured" not in large_blockers
    assert "large_model_execution_receipt_missing" in large_blockers
    assert "large_model_scorecard_or_review_missing" in large_blockers
    assert "large_model_execution_count_below_required:0/2" in large_blockers
    assert "large_model_crash_oom_free_count_below_required:0/2" in large_blockers
    assert final_gates["large_models_crash_oom_free"]["evidence"].endswith(
        "phase6_benchmark_scale_status.json"
    )
    large_gate_grouping = final_gates["large_models_crash_oom_free"][
        "blocker_grouping_metadata"
    ]
    assert large_gate_grouping["schema_version"] == "phase6-benchmark-scale-blocker-groups.v1"
    assert large_gate_grouping["blocker_count"] == len(large_blockers)
    assert large_gate_grouping["unassigned_blockers"] == []
    assert "large_model_execution_receipt_missing" in large_gate_grouping["groups"][
        "large_runner_execution"
    ]["blockers"]
    assert "Policy-only acquisition rows" in " ".join(
        final_gates["large_models_crash_oom_free"]["notes"]
    )
    assert final_gates["silent_import_loss_zero"]["contract_pass"] is True
    assert final_gates["silent_import_loss_zero"]["evidence"] == (
        "implementation/phase1/release_evidence/productization/"
        "phase3_ifc_import_health_execution_receipt.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_buildingsmart_ifc_acquisition_receipt.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_ifc_source_license_receipt.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase6_silent_import_loss_status.json"
    )
    silent_blockers = final_gates["silent_import_loss_zero"]["blockers"]
    assert silent_blockers == []
    assert "import_health_execution_missing" not in silent_blockers
    assert "dirty_import_execution_missing" not in silent_blockers
    assert "source_file_not_acquired" not in silent_blockers
    assert "source_sha256_missing" not in silent_blockers
    assert "ifc_import_health_execution_count_below_required:0/10" not in silent_blockers
    assert "silent_data_loss_negative_gate_not_executed" not in silent_blockers
    assert "product_legal_license_review_pending" not in silent_blockers
    assert "per_file_license_review_pending" not in silent_blockers
    assert "phase3_ifc_import_case_quantity_credit_missing" not in silent_blockers
    assert "phase3_ifc_import_case_quantity_credit_blocked_pending_license_review" not in silent_blockers
    assert "gui_task_runner_not_implemented" not in silent_blockers
    assert "query_expected_answers_missing" not in silent_blockers
    assert "query_task_file_checksums_missing" not in silent_blockers
    assert "dataset_repository_url_missing" not in silent_blockers
    assert "Product/legal license review" in " ".join(
        final_gates["silent_import_loss_zero"]["notes"]
    )
    assert final_gates["residual_and_convergence_history_present"]["contract_pass"] is True
    assert final_gates["linux_windows_reproducibility_confirmed"]["contract_pass"] is False
    assert final_gates["linux_windows_reproducibility_confirmed"]["evidence"] == (
        "implementation/phase1/release_evidence/productization/"
        "phase3_benchmark_factory_seed_reproducibility_bundle.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase6_linux_windows_parity_status.json"
    )
    assert final_gates["new_user_core_workflow_observation_passed"]["contract_pass"] is False
    assert final_gates["new_user_core_workflow_observation_passed"]["evidence"] == (
        "implementation/phase1/release_evidence/productization/"
        "ux_new_user_observation_report.json; "
        "implementation/phase1/release_evidence/productization/"
        "ux_new_user_observation_intake_packet.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase6_ux_observation_status.json"
    )
    ux_gate_blockers = final_gates["new_user_core_workflow_observation_passed"]["blockers"]
    assert "human_new_user_observation_not_passed" in ux_gate_blockers
    assert "human_observation_workflow_step_pass_count_below_required:0/5" in ux_gate_blockers
    assert "phase5_workflow_execution_not_proven:0/5" not in ux_gate_blockers
    assert "task_based_ux_browser_execution_not_passed" not in ux_gate_blockers
    assert not any(
        blocker.startswith("task_based_ux_browser_execution_environment_blocked")
        for blocker in ux_gate_blockers
    )
    assert "automated browser/task evidence does not replace" in " ".join(
        final_gates["new_user_core_workflow_observation_passed"]["notes"]
    )
    ux_gate_grouping = final_gates["new_user_core_workflow_observation_passed"][
        "blocker_grouping_metadata"
    ]
    assert ux_gate_grouping["schema_version"] == "phase6-ux-observation-blocker-groups.v1"
    assert ux_gate_grouping["groups"]["human_observation_root"]["scope"] == (
        "direct_rc_ux_gate"
    )
    assert ux_gate_grouping["unassigned_blockers"] == []
    assert "observation_report:observation_file_missing" in ux_gate_grouping["groups"][
        "human_observation_report_detail"
    ]["blockers"]
    assert ux_gate_grouping["groups"]["phase5_execution_detail"]["blockers"] == []
    assert ux_gate_grouping["groups"]["environment_spillover"]["blockers"] == []
    assert final_gates["benchmark_results_clean_checkout_regenerated"]["contract_pass"] is True
    assert final_gates["benchmark_results_clean_checkout_regenerated"]["status"] == "ready"
    assert final_gates["benchmark_results_clean_checkout_regenerated"]["evidence"] == (
        "implementation/phase1/release_evidence/productization/"
        "phase3_benchmark_factory_seed_clean_checkout_reproduction.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase3_release_control_cleanup_plan.json; "
        "implementation/phase1/release_evidence/productization/"
        "phase6_clean_checkout_status.json"
    )
    assert final_gates["residual_and_convergence_history_present"]["blockers"] == []
    assert final_gates["linux_windows_reproducibility_confirmed"]["blockers"] == [
        "platform_replay_receipt_missing:windows",
    ]
    parity_gate_grouping = final_gates["linux_windows_reproducibility_confirmed"][
        "blocker_grouping_metadata"
    ]
    assert parity_gate_grouping["schema_version"] == (
        "phase6-linux-windows-parity-blocker-groups.v1"
    )
    assert parity_gate_grouping["blocker_count"] == len(
        final_gates["linux_windows_reproducibility_confirmed"]["blockers"]
    )
    assert parity_gate_grouping["unassigned_blockers"] == []
    assert "platform_replay_receipt_missing:windows" in parity_gate_grouping["groups"][
        "platform_receipt_presence"
    ]["blockers"]
    assert parity_gate_grouping["groups"]["git_clean_clone_spillover"]["blockers"] == []
    assert (
        "git_clean_clone_reproduction_not_passed"
        not in final_gates["linux_windows_reproducibility_confirmed"]["blockers"]
    )
    assert "stable output checksums" in " ".join(
        final_gates["linux_windows_reproducibility_confirmed"]["notes"]
    )
    assert "clean-clone blockers" in " ".join(
        final_gates["linux_windows_reproducibility_confirmed"]["notes"]
    )
    clean_checkout_blockers = final_gates[
        "benchmark_results_clean_checkout_regenerated"
    ]["blockers"]
    assert clean_checkout_blockers == []
    clean_gate_grouping = final_gates["benchmark_results_clean_checkout_regenerated"][
        "blocker_grouping_metadata"
    ]
    assert clean_gate_grouping["schema_version"] == "phase6-clean-checkout-blocker-groups.v1"
    assert clean_gate_grouping["unassigned_blockers"] == []
    assert clean_gate_grouping["blocker_count"] == 0
    assert clean_gate_grouping["groups"]["dirty_tracked_required_inputs"]["blocker_count"] == 0
    assert clean_gate_grouping["groups"]["untracked_required_inputs"]["blocker_count"] == 0
    assert clean_gate_grouping["groups"]["release_control_human_handoff"]["blockers"] == []
    assert "tracked and committed" in " ".join(
        final_gates["benchmark_results_clean_checkout_regenerated"]["notes"]
    )
    assert "Phase 6 status receipt" in " ".join(
        final_gates["benchmark_results_clean_checkout_regenerated"]["notes"]
    )

    preview_readiness = json.loads(
        (REPO_ROOT / module.DEVELOPER_PREVIEW_READINESS).read_text(encoding="utf-8")
    )
    assert (
        payload["known_limitations"]["developer_preview_blocker_count"]
        == preview_readiness["blocker_count"]
    )
    assert payload["known_limitations"]["developer_preview_blockers"] == preview_readiness[
        "blockers"
    ][:20]
    assert payload["known_limitations"]["dataset_license_blockers"] == []
    assert payload["known_limitations"]["dataset_license_external_corpus_blockers"] == [
        "phase3_external_corpus:authoritative_source_checksums_pending=4",
        "phase3_external_corpus:license_or_redistribution_review_pending",
        "phase3_external_corpus:expected_outputs_pending",
    ]
    gap_visibility = payload["known_limitations"]["gap_ledger_closure_requirement_visibility"]
    assert gap_visibility["source_status"] == "ready"
    assert gap_visibility["source_contract_pass"] is True
    assert gap_visibility["source_full_gap_ledger_ready"] is False
    assert gap_visibility["closure_requirement_count"] == 19
    assert gap_visibility["closure_requirement_pass_count"] == 3
    assert gap_visibility["closure_requirement_fail_count"] == 16
    assert gap_visibility["nonclosed_rows_with_failed_closure_requirements_count"] == 3
    assert "G1:full_load_scale_1_0_reached" in gap_visibility[
        "nonclosed_failed_closure_requirement_ids"
    ]
    assert "G6:eb_receipt_hardest_external_10case" in gap_visibility[
        "nonclosed_failed_closure_requirement_ids"
    ]
    assert "G7:operator_manifest_source_mapping_clear" in gap_visibility[
        "nonclosed_failed_closure_requirement_ids"
    ]
    ux_handoff = payload["known_limitations"]["ux_new_user_observation_handoff"]
    assert ux_handoff["ux_observation_status_receipt"].endswith(
        "phase6_ux_observation_status.json"
    )
    assert ux_handoff["ux_observation_status"] == "blocked"
    assert ux_handoff["ux_observation_contract_pass"] is False
    assert ux_handoff["observation_report"].endswith("ux_new_user_observation_report.json")
    assert ux_handoff["intake_packet"].endswith("ux_new_user_observation_intake_packet.json")
    assert ux_handoff["human_observation_gate"]["status"] == "blocked"
    assert ux_handoff["human_observation_gate"]["workflow_step_pass_count"] == 0
    assert ux_handoff["intake_packet_gate"]["status"] == "blocked"
    assert ux_handoff["intake_packet_gate"]["field_pass_count"] == 0
    assert ux_handoff["phase5_workflow_gate"]["status"] == "blocked"
    assert ux_handoff["phase5_workflow_gate"]["workflow_shell_step_pass_count"] == 5
    assert ux_handoff["phase5_workflow_gate"]["execution_workflow_step_pass_count"] == 5
    assert ux_handoff["phase5_workflow_gate"]["task_based_ux_browser_execution_passed"] is True
    assert "phase5_workflow_execution_not_proven:0/5" not in ux_handoff["phase6_ux_status_blockers"]
    assert not any(
        blocker.startswith("task_based_ux_browser_execution_environment_blocked")
        for blocker in ux_handoff["phase6_ux_status_blockers"]
    )
    assert ux_handoff["phase6_ux_blocker_grouping"]["schema_version"] == (
        "phase6-ux-observation-blocker-groups.v1"
    )
    assert ux_handoff["phase6_ux_blocker_grouping"]["groups"][
        "intake_packet_handoff"
    ]["scope"] == "owner_handoff_not_gate_closure"
    assert ux_handoff["phase6_ux_blocker_grouping"]["groups"][
        "environment_spillover"
    ]["scope"] == "local_environment_blocker"
    assert ux_handoff["intake_field_pass_count"] == 0
    assert ux_handoff["intake_field_count"] == 21
    assert ux_handoff["report_blockers"] == [
        "observation_file_missing",
        "contract_signal_not_pass",
        "required_fields_missing",
        "participant_not_new_user",
        "new_to_product_not_confirmed",
        "completion_minutes_missing",
        "workflow_steps_missing",
        "required_workflow_steps_missing",
        "required_workflow_step_not_passed",
        "blocking_usability_issue_present",
        "evidence_ref_missing",
        "approval_decision_not_accepted",
    ]
    assert ux_handoff["workflow_step_pass_count"] == 0
    assert ux_handoff["required_workflow_step_count"] == 5
    assert ux_handoff["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert ux_handoff["not_passed_workflow_steps"] == []
    assert ux_handoff["required_workflow_steps"] == [
        {"id": "import", "label": "Import"},
        {"id": "model_health", "label": "Model Health"},
        {"id": "analysis_setup", "label": "Analysis Setup"},
        {"id": "run_monitor", "label": "Run & Monitor"},
        {"id": "compare_report", "label": "Compare & Report"},
    ]
    assert "Attach a human new-user observation record" in ux_handoff["owner_action"]
    assert any("build_ux_new_user_observation_report.py" in command for command in ux_handoff["validation_commands"])
    assert any("build_ux_new_user_observation_intake_packet.py" in command for command in ux_handoff["validation_commands"])
    assert "automated browser/task tests do not replace" in ux_handoff["claim_boundary"]
    assert "cannot close the RC UX final gate" in ux_handoff["claim_boundary"]
    quantity_handoff = payload["known_limitations"]["benchmark_quantity_handoff"]
    assert quantity_handoff["source"].endswith("phase3_benchmark_factory_seed_summary.json")
    assert quantity_handoff["acquisition_plan"].endswith("phase3_benchmark_acquisition_plan.json")
    assert quantity_handoff["benchmark_scale_status_receipt"].endswith(
        "phase6_benchmark_scale_status.json"
    )
    assert quantity_handoff["benchmark_scale_status"] == "blocked"
    assert quantity_handoff["benchmark_scale_contract_pass"] is False
    assert quantity_handoff["benchmark_scale_blocker_grouping"]["schema_version"] == (
        "phase6-benchmark-scale-blocker-groups.v1"
    )
    assert quantity_handoff["targets"]["analytic_component"] == {
        "current": 30,
        "required": 20,
        "remaining": 0,
        "contract_pass": True,
    }
    assert quantity_handoff["targets"]["medium_structural_models"]["current"] == 0
    assert quantity_handoff["targets"]["medium_structural_models"]["required"] == 5
    assert quantity_handoff["targets"]["medium_structural_models"]["remaining"] == 5
    assert quantity_handoff["targets"]["medium_structural_models"]["contract_pass"] is False
    assert (
        "opensees_medium_scorecard_execution_missing"
        in quantity_handoff["targets"]["medium_structural_models"]["acquisition_blockers"]
    )
    assert quantity_handoff["targets"]["medium_structural_models"]["scorecard_readiness_receipt"].endswith(
        "phase3_medium_model_scorecard_readiness_receipt.json"
    )
    assert (
        "medium_model_pass_or_review_missing"
        in quantity_handoff["targets"]["medium_structural_models"]["scorecard_blockers"]
    )
    medium_scale_gate = quantity_handoff["targets"]["medium_structural_models"]["benchmark_scale_gate"]
    assert medium_scale_gate["status"] == "blocked"
    assert medium_scale_gate["contract_pass"] is False
    assert "medium_model_pass_or_review_below_required:0/5" in medium_scale_gate["blockers"]
    assert quantity_handoff["targets"]["large_structural_models"]["current"] == 2
    assert quantity_handoff["targets"]["large_structural_models"]["required"] == 2
    assert quantity_handoff["targets"]["large_structural_models"]["remaining"] == 0
    assert quantity_handoff["targets"]["large_structural_models"]["contract_pass"] is False
    assert (
        "large_model_runner_not_implemented"
        not in quantity_handoff["targets"]["large_structural_models"]["acquisition_blockers"]
    )
    assert (
        "nightly_lane_not_configured"
        not in quantity_handoff["targets"]["large_structural_models"]["acquisition_blockers"]
    )
    assert quantity_handoff["targets"]["large_structural_models"]["runner_readiness_receipt"].endswith(
        "phase3_large_model_runner_readiness_receipt.json"
    )
    assert (
        "large_model_execution_receipt_missing"
        in quantity_handoff["targets"]["large_structural_models"]["runner_blockers"]
    )
    large_scale_gate = quantity_handoff["targets"]["large_structural_models"]["benchmark_scale_gate"]
    assert large_scale_gate["status"] == "blocked"
    assert large_scale_gate["contract_pass"] is False
    assert "large_model_crash_oom_free_count_below_required:0/2" in large_scale_gate["blockers"]
    assert quantity_handoff["targets"]["ifc_clean_dirty_import_cases"]["remaining"] == 10
    assert "does not create medium/large benchmark evidence" in quantity_handoff["claim_boundary"]
    medium_scorecard_handoff = payload["known_limitations"]["medium_model_scorecard_handoff"]
    assert medium_scorecard_handoff["scorecard_readiness_receipt"].endswith(
        "phase3_medium_model_scorecard_readiness_receipt.json"
    )
    assert medium_scorecard_handoff["benchmark_scale_status_receipt"].endswith(
        "phase6_benchmark_scale_status.json"
    )
    assert medium_scorecard_handoff["benchmark_scale_status"] == "blocked"
    assert medium_scorecard_handoff["benchmark_scale_contract_pass"] is False
    assert medium_scorecard_handoff["benchmark_scale_gate"]["contract_pass"] is False
    assert medium_scorecard_handoff["benchmark_scale_blocker_grouping"]["groups"][
        "medium_scorecard_execution"
    ]["scope"] == "medium_model_scorecard_execution"
    assert medium_scorecard_handoff["required_medium_model_count"] == 5
    assert medium_scorecard_handoff["current_medium_model_scorecard_count"] == 0
    assert medium_scorecard_handoff["pass_or_approved_review_count"] == 0
    assert medium_scorecard_handoff["local_candidate_artifact_count"] == 2
    assert medium_scorecard_handoff["local_topology_contract_pass"] is True
    assert medium_scorecard_handoff["required_evidence_pass_count"] == 4
    assert "source_url_verification_pending" not in medium_scorecard_handoff["blockers"]
    assert "license_review_pending" in medium_scorecard_handoff["blockers"]
    assert "opensees_medium_scorecard_execution_missing" in medium_scorecard_handoff["blockers"]
    assert "opensees_medium_runner_command_missing" not in medium_scorecard_handoff["blockers"]
    assert medium_scorecard_handoff["runner_command_ready"] is True
    assert "run_phase3_medium_model_scorecard_receipt.py" in medium_scorecard_handoff[
        "runner_command_template"
    ]
    assert medium_scorecard_handoff["local_parser_boundary"]["topology_contract_pass"] is True
    assert medium_scorecard_handoff["scorecard_receipt_template"]["schema_version"] == (
        "phase3-medium-model-scorecard-receipt.v1"
    )
    assert "Attach product legal license approval" in medium_scorecard_handoff["owner_action"]
    assert "parser-only" in medium_scorecard_handoff["claim_boundary"]
    large_runner_handoff = payload["known_limitations"]["large_model_runner_handoff"]
    assert large_runner_handoff["runner_readiness_receipt"].endswith(
        "phase3_large_model_runner_readiness_receipt.json"
    )
    assert large_runner_handoff["benchmark_scale_status_receipt"].endswith(
        "phase6_benchmark_scale_status.json"
    )
    assert large_runner_handoff["benchmark_scale_status"] == "blocked"
    assert large_runner_handoff["benchmark_scale_contract_pass"] is False
    assert large_runner_handoff["benchmark_scale_gate"]["contract_pass"] is False
    assert large_runner_handoff["benchmark_scale_blocker_grouping"]["groups"][
        "large_quantity_shortfall"
    ]["scope"] == "large_model_quantity_gate"
    assert large_runner_handoff["required_large_model_count"] == 2
    assert large_runner_handoff["current_large_model_execution_receipt_count"] == 0
    assert large_runner_handoff["crash_oom_free_execution_count"] == 0
    assert large_runner_handoff["scorecard_or_review_count"] == 0
    assert large_runner_handoff["required_evidence_pass_count"] == 4
    assert large_runner_handoff["runner_command_ready"] is True
    assert "run_phase3_large_model_execution_receipt.py" in large_runner_handoff[
        "runner_command_template"
    ]
    assert large_runner_handoff["resource_envelope"]["default_memory_limit_gb"] == 64.0
    assert "large_model_runner_not_implemented" not in large_runner_handoff["blockers"]
    assert "large_model_execution_receipt_missing" in large_runner_handoff["blockers"]
    assert large_runner_handoff["runner_receipt_template"]["schema_version"] == (
        "phase3-large-model-execution-receipt.v1"
    )
    assert "Complete license review" in large_runner_handoff["owner_action"]
    assert "does not acquire sources" in large_runner_handoff["claim_boundary"]
    ifc_handoff = payload["known_limitations"]["ifc_import_handoff"]
    assert ifc_handoff["silent_import_loss_status_receipt"].endswith(
        "phase6_silent_import_loss_status.json"
    )
    assert ifc_handoff["silent_import_loss_status"] == "blocked"
    assert ifc_handoff["silent_import_loss_contract_pass"] is False
    assert ifc_handoff["technical_silent_import_loss_zero"] is True
    assert ifc_handoff["product_release_credit_ready"] is False
    assert ifc_handoff["import_health_receipt"].endswith(
        "phase3_ifc_import_health_execution_receipt.json"
    )
    assert ifc_handoff["clean_acquisition_receipt"].endswith(
        "phase3_buildingsmart_ifc_acquisition_receipt.json"
    )
    assert ifc_handoff["dirty_acquisition_receipt"].endswith(
        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
    )
    assert ifc_handoff["source_license_receipt"].endswith(
        "phase3_ifc_source_license_receipt.json"
    )
    assert ifc_handoff["clean_selected_file_count"] == 2
    assert ifc_handoff["clean_expected_contract_count"] == 2
    assert ifc_handoff["clean_execution_count"] == 0
    assert ifc_handoff["dirty_selected_file_count"] == 8
    assert ifc_handoff["dirty_expected_contract_count"] == 8
    assert ifc_handoff["dirty_execution_count"] == 0
    assert ifc_handoff["import_health_execution_count"] == 10
    assert ifc_handoff["import_health_contract_pass_count"] == 10
    assert ifc_handoff["selected_import_case_count"] == 10
    assert ifc_handoff["required_ifc_import_case_count"] == 10
    assert ifc_handoff["evidence_requirements"]["clean_dirty_import_case_count"] == {
        "current": 10,
        "required": 10,
        "contract_pass": True,
    }
    assert ifc_handoff["evidence_requirements"]["source_files_acquired"] is True
    assert ifc_handoff["evidence_requirements"]["selected_file_checksums_ready"] is True
    assert ifc_handoff["evidence_requirements"]["import_health_execution_ready"] is True
    assert ifc_handoff["evidence_requirements"]["silent_data_loss_negative_gate_executed"] is True
    assert ifc_handoff["evidence_requirements"]["product_license_review_ready"] is False
    assert ifc_handoff["evidence_requirements"]["technical_silent_import_loss_zero"] is True
    assert ifc_handoff["evidence_requirements"]["product_release_credit_ready"] is False
    assert "source_file_not_acquired" not in ifc_handoff["import_health_blockers"]
    assert "phase3_ifc_import_case_quantity_credit_blocked_pending_license_review" in ifc_handoff[
        "import_health_blockers"
    ]
    assert "selected_file_checksums_missing" not in ifc_handoff["source_license_blockers"]
    assert "product_legal_license_review_pending" in ifc_handoff["source_license_blockers"]
    assert "ifc_import_health_execution_count_below_required:0/10" not in ifc_handoff[
        "silent_import_loss_blockers"
    ]
    assert "phase3_ifc_import_case_quantity_credit_missing" in ifc_handoff[
        "silent_import_loss_blockers"
    ]
    assert ifc_handoff["silent_import_loss_direct_blockers"] == ifc_handoff[
        "silent_import_loss_blockers"
    ]
    assert ifc_handoff["silent_import_loss_technical_direct_blockers"] == []
    assert ifc_handoff["silent_import_loss_product_release_credit_blockers"] == [
        "per_file_license_review_pending",
        "phase3_ifc_import_case_quantity_credit_blocked_pending_license_review",
        "phase3_ifc_import_case_quantity_credit_missing",
        "product_legal_license_review_pending",
    ]
    assert "gui_task_runner_not_implemented" not in ifc_handoff[
        "silent_import_loss_direct_blockers"
    ]
    assert "gui_task_runner_not_implemented" in ifc_handoff[
        "silent_import_loss_spillover_blockers"
    ]
    assert "gui_task_runner_not_implemented" in ifc_handoff[
        "silent_import_loss_all_blockers"
    ]
    grouping = ifc_handoff["silent_import_loss_blocker_grouping"]
    assert grouping["schema_version"] == "phase6-silent-import-loss-blocker-groups.v1"
    assert grouping["groups"]["source_acquisition"]["scope"] == "direct_silent_import_loss"
    assert grouping["groups"]["source_acquisition"]["blockers"] == []
    assert "phase3_ifc_import_case_quantity_credit_missing" in grouping["groups"][
        "quantity_credit"
    ]["blockers"]
    assert grouping["groups"]["query_gui_spillover"]["scope"] == (
        "spillover_not_direct_silent_import_loss"
    )
    assert "gui_task_runner_not_implemented" in grouping["groups"][
        "query_gui_spillover"
    ]["blockers"]
    assert "complete product/legal and per-file license review" in ifc_handoff["owner_action"]
    assert "close or explicitly defer the ifc-bench query/GUI spillover blockers" in ifc_handoff[
        "owner_action"
    ]
    assert "does not download or bundle IFC files" in ifc_handoff["claim_boundary"]
    ifc_query_handoff = payload["known_limitations"]["ifc_query_gui_handoff"]
    assert ifc_query_handoff["query_gui_readiness_receipt"].endswith(
        "phase3_ifc_query_gui_readiness_receipt.json"
    )
    assert ifc_query_handoff["required_task_source_count"] == 1
    assert ifc_query_handoff["current_task_source_count"] == 0
    assert ifc_query_handoff["task_manifest_count"] == 0
    assert ifc_query_handoff["expected_answer_count"] == 0
    assert ifc_query_handoff["gui_task_execution_count"] == 0
    assert ifc_query_handoff["workflow_step_count"] == 5
    assert ifc_query_handoff["workflow_step_pass_count"] == 0
    assert ifc_query_handoff["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert ifc_query_handoff["required_evidence_pass_count"] == 0
    assert "query_task_manifest_missing" in ifc_query_handoff["blockers"]
    assert "gui_workflow_coverage_missing" in ifc_query_handoff["blockers"]
    assert ifc_query_handoff["task_execution_receipt_template"]["schema_version"] == (
        "phase3-ifc-query-gui-task-execution-receipt.v1"
    )
    assert "Attach the IFC query/GUI dataset" in ifc_query_handoff["owner_action"]
    assert "not FEM numerical accuracy evidence" in ifc_query_handoff["claim_boundary"]
    phase5_handoff = payload["known_limitations"]["phase5_gui_workflow_handoff"]
    assert phase5_handoff["gui_workflow_readiness_receipt"].endswith(
        "phase5_gui_workflow_readiness_receipt.json"
    )
    assert phase5_handoff["required_workflow_step_count"] == 5
    assert phase5_handoff["workflow_shell_step_pass_count"] == 5
    assert phase5_handoff["actual_gui_workflow_step_pass_count"] == 5
    assert phase5_handoff["actual_gui_workflow_step_partial_count"] == 0
    assert phase5_handoff["execution_workflow_step_pass_count"] == 5
    assert phase5_handoff["partial_actual_gui_workflow_steps"] == []
    assert phase5_handoff["missing_actual_gui_workflow_steps"] == []
    assert phase5_handoff["missing_execution_workflow_steps"] == []
    assert phase5_handoff["handoff_surface"]["observation_required_workflow_step_count"] == 5
    assert phase5_handoff["handoff_surface"]["intake_required_workflow_step_count"] == 5
    assert phase5_handoff["task_based_ux_test"]["status"] == "ready"
    assert phase5_handoff["task_based_ux_test"]["contract_pass"] is True
    assert phase5_handoff["task_based_ux_test"]["browser_execution_receipt_attached"] is True
    assert phase5_handoff["task_based_ux_test"]["browser_execution_status"] == "ready"
    assert phase5_handoff["task_based_ux_test"]["browser_execution_passed"] is True
    assert phase5_handoff["task_based_ux_test"]["browser_execution_blocker"] is None
    assert phase5_handoff["task_based_ux_test"]["browser_execution_environment_blocker"] is False
    assert phase5_handoff["task_based_ux_test"]["browser_execution_blocker_reason_code"] == ""
    assert phase5_handoff["task_based_ux_test"]["execution_environment_blocker"] is None
    assert phase5_handoff["task_based_ux_browser_execution_receipt"]["failed_phase"] is None
    assert phase5_handoff["task_based_ux_test"]["path"].endswith(
        "tests/frontend/developer-preview-workflow.spec.ts"
    )
    assert phase5_handoff["route_case_run_state_model"]["status"] == "ready"
    assert phase5_handoff["route_case_run_state_model"]["route_id"] == (
        "developer-preview-local-workflow"
    )
    assert phase5_handoff["route_case_run_state_model"]["case_id"] == (
        "open-benchmark-seed-corpus"
    )
    assert phase5_handoff["route_case_run_state_model"]["run_id"] == (
        "execution-receipt-pending"
    )
    assert "workflow_execution_step_not_proven:model_health" not in phase5_handoff["blockers"]
    assert "task_based_ux_browser_execution_receipt_missing" not in phase5_handoff["blockers"]
    assert "task_based_ux_browser_execution_not_passed" not in phase5_handoff["blockers"]
    assert not any(
        blocker.startswith("task_based_ux_browser_execution_environment_blocked")
        for blocker in phase5_handoff["blockers"]
    )
    assert "human_new_user_observation_not_passed" in phase5_handoff["blockers"]
    assert "Attach execution receipts" in phase5_handoff["owner_action"]
    assert "visible GUI workflow shell coverage" in phase5_handoff["claim_boundary"]
    commercial_handoff = payload["known_limitations"]["commercial_cross_solver_handoff"]
    assert commercial_handoff["cross_solver_readiness_receipt"].endswith(
        "phase4_commercial_cross_solver_readiness_receipt.json"
    )
    assert commercial_handoff["required_reference_solver_count"] == 2
    assert commercial_handoff["current_reference_solver_count"] == 0
    assert commercial_handoff["operator_package_attached"] is False
    assert commercial_handoff["operator_permission_attached"] is False
    assert commercial_handoff["operator_checksum_count"] == 0
    assert commercial_handoff["operator_trace_rows_available"] is False
    assert commercial_handoff["required_evidence_pass_count"] == 1
    assert "operator_reference_package_missing" in commercial_handoff["blockers"]
    assert "two_reference_solver_comparison_not_available" in commercial_handoff["blockers"]
    assert "operator_comparison_trace_rows_missing" in commercial_handoff["blockers"]
    assert commercial_handoff["readiness_inputs"]["import_template"].endswith(
        "phase4_commercial_comparison_import_template.json"
    )
    assert "Attach an operator-approved comparison package" in commercial_handoff["owner_action"]
    assert "does not include operator files" in commercial_handoff["claim_boundary"]
    parity_handoff = payload["known_limitations"]["linux_windows_reproducibility_handoff"]
    assert parity_handoff["parity_status_receipt"].endswith(
        "phase6_linux_windows_parity_status.json"
    )
    assert parity_handoff["parity_status"] == "blocked"
    assert parity_handoff["parity_contract_pass"] is False
    assert parity_handoff["reproducibility_bundle"].endswith(
        "phase3_benchmark_factory_seed_reproducibility_bundle.json"
    )
    assert parity_handoff["git_clean_clone_receipt"].endswith(
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
    )
    assert parity_handoff["required_platforms"] == ["linux", "windows"]
    assert parity_handoff["current_platform_receipts"] == ["linux"]
    assert parity_handoff["missing_platform_receipts"] == ["windows"]
    assert (
        parity_handoff["platform_receipt_schema"]
        == "phase6-linux-windows-platform-replay-receipt.v1"
    )
    receipt_template = parity_handoff["platform_receipt_template"]
    assert receipt_template["schema_version"] == "phase6-linux-windows-platform-replay-receipt.v1"
    assert receipt_template["platform"] == "linux|windows"
    assert receipt_template["working_tree_clean"] is True
    assert receipt_template["local_dirty_inputs"] == []
    assert receipt_template["contract_pass"] is False
    assert receipt_template["stable_artifact_checksums"] == parity_handoff[
        "expected_stable_artifact_checksums"
    ]
    assert receipt_template["expected_scorecard"] == parity_handoff["expected_scorecard"]
    missing_platform_handoff = parity_handoff["missing_platform_receipt_handoff"]
    assert len(missing_platform_handoff) == 1
    assert missing_platform_handoff[0]["platform"] == "windows"
    assert missing_platform_handoff[0]["receipt_path"].endswith(
        "phase6_windows_platform_replay_receipt.json"
    )
    assert (
        "do_not_copy_linux_receipt_as_windows_receipt"
        in missing_platform_handoff[0]["forbidden_shortcuts"]
    )
    assert (
        "python3 scripts/build_developer_preview_rc_status.py --check"
        in missing_platform_handoff[0]["validation_commands_after_attachment"]
    )
    parity_contract = parity_handoff["parity_comparison_contract"]
    assert parity_contract["required_platform_receipt_count"] == 2
    assert parity_contract["current_platform_receipt_count"] == 1
    assert parity_contract["required_platforms"] == ["linux", "windows"]
    assert parity_contract["local_dirty_inputs_allowed"] is False
    assert parity_contract["contract_pass"] is False
    assert "manifest" in parity_contract["checksum_keys"]
    assert "scorecard" in parity_contract["checksum_keys"]
    assert "case_count" in parity_contract["scorecard_identity_fields"]
    assert parity_handoff["blocked_by"] == ["platform_replay_receipt_missing:windows"]
    assert parity_handoff["parity_blocker_grouping"]["schema_version"] == (
        "phase6-linux-windows-parity-blocker-groups.v1"
    )
    assert parity_handoff["parity_blocker_grouping"]["groups"][
        "git_clean_clone_spillover"
    ]["blockers"] == []
    assert parity_handoff["parity_gate_blocker_grouping"]["blocker_count"] == 1
    assert parity_handoff["parity_gate_blocker_grouping"]["groups"][
        "git_clean_clone_spillover"
    ]["blockers"] == []
    assert any(
        "structural_analysis.benchmark.cli" in command
        for command in parity_handoff["required_commands"]
    )
    assert any(
        "run_phase3_benchmark_factory_git_clean_clone_reproduction.py" in command
        for command in parity_handoff["required_commands"]
    )
    assert "stable manifest and scorecard SHA256 values" in parity_handoff[
        "comparison_requirements"
    ]
    assert "working_tree_clean=true and local_dirty_inputs=[]" in parity_handoff[
        "comparison_requirements"
    ]
    assert parity_handoff["clean_clone_blockers_tracked_elsewhere"] == []
    assert "does not prove parity" in parity_handoff["claim_boundary"]
    clean_handoff = payload["known_limitations"]["clean_checkout_reproduction_handoff"]
    assert clean_handoff["clean_checkout_status_receipt"].endswith(
        "phase6_clean_checkout_status.json"
    )
    assert clean_handoff["clean_checkout_status"] == "ready"
    assert clean_handoff["clean_checkout_status_contract_pass"] is True
    assert clean_handoff["local_clean_checkout_gate"]["status"] == "ready"
    assert clean_handoff["local_clean_checkout_gate"]["contract_pass"] is True
    assert clean_handoff["git_clean_clone_gate"]["status"] == "ready"
    assert clean_handoff["git_clean_clone_gate"]["contract_pass"] is True
    assert clean_handoff["git_clean_clone_gate"]["git_clean_clone_executed"] is True
    assert clean_handoff["release_control_cleanup_gate"]["status"] == "ready"
    assert clean_handoff["release_control_cleanup_gate"]["human_git_action_required"] is False
    assert clean_handoff["phase6_clean_checkout_blockers"] == []
    assert clean_handoff["phase6_clean_checkout_blocker_grouping"]["schema_version"] == (
        "phase6-clean-checkout-blocker-groups.v1"
    )
    assert clean_handoff["phase6_clean_checkout_blocker_grouping"]["groups"][
        "release_control_human_handoff"
    ]["scope"] == "owner_git_action_handoff"
    assert clean_handoff["clean_checkout_receipt"].endswith(
        "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
    )
    assert clean_handoff["git_clean_clone_receipt"].endswith(
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
    )
    assert clean_handoff["release_control_cleanup_plan"].endswith(
        "phase3_release_control_cleanup_plan.json"
    )
    assert clean_handoff["reproducibility_bundle"].endswith(
        "phase3_benchmark_factory_seed_reproducibility_bundle.json"
    )
    assert clean_handoff["local_clean_checkout"]["status"] == "pass"
    assert clean_handoff["local_clean_checkout"]["contract_pass"] is True
    assert clean_handoff["local_clean_checkout"]["executed"] is True
    assert clean_handoff["git_clean_clone"]["status"] == "pass"
    assert clean_handoff["git_clean_clone"]["contract_pass"] is True
    assert clean_handoff["git_clean_clone"]["executed"] is True
    git_clean_clone = clean_handoff["git_clean_clone"]
    assert git_clean_clone["required_input_count"] >= git_clean_clone["blocker_count"]
    assert sum(git_clean_clone["blocker_counts"].values()) == git_clean_clone["blocker_count"]
    assert git_clean_clone["blocker_counts"] == {}
    cleanup = clean_handoff["release_control_cleanup"]
    assert cleanup["status"] == "ready"
    assert cleanup["contract_pass"] is True
    assert cleanup["human_git_action_required"] is False
    assert cleanup["candidate_release_control_commit_set_count"] == 0
    assert cleanup["recommended_action_counts"] == {}
    assert cleanup["human_handoff_next_action"] == "rerun_git_clean_clone_reproduction"
    assert any(
        "run_phase3_benchmark_factory_git_clean_clone_reproduction.py" in command
        for command in cleanup["next_verification_commands"]
    )
    assert "does not commit" in cleanup["claim_boundary"]
    assert git_clean_clone["blocker_count"] == 0
    assert git_clean_clone["blockers"] == []
    assert any(
        "run_phase3_benchmark_factory_git_clean_clone_reproduction.py" in command
        for command in clean_handoff["required_commands"]
    )
    assert "does not commit changes" in clean_handoff["claim_boundary"]
    assert payload["future_commercial_gates"] == [
        "30_run_ci_streak",
        "customer_shadow",
        "product_license",
        "license_server_operation",
        "commercial_sla",
        "external_approval_receipts",
        "remote_github_sync",
    ]
    assert "full Phase 3 corpus" in payload["claim_boundary"]
    assert "G1 full nonlinear full-mesh" in payload["claim_boundary"]
    markdown = module._markdown(payload)
    assert "## Known Limitation Closure Requirements" in markdown
    assert "`closure_requirements`: `3/19`" in markdown
    assert "`failed_closure_requirements`: `16`" in markdown
    assert "`G1:full_load_scale_1_0_reached`" in markdown
    assert "does not add Developer Preview blockers" in markdown
    assert "deliverable_blocked:sample_acquisition_command" not in payload["blockers"]
    assert "deliverable_blocked:dataset_license_manifest" not in payload["blockers"]
    assert any(
        item == "final_gate_blocked:linux_windows_reproducibility_confirmed"
        for item in payload["blockers"]
    )


def test_developer_preview_rc_status_check_detects_missing_outputs(tmp_path: Path) -> None:
    ok, message = module.check_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
        out_md_path=tmp_path / "missing.md",
    )

    assert ok is False
    assert message.startswith("developer_preview_rc_status_missing:")


def test_developer_preview_rc_status_check_detects_json_drift(tmp_path: Path) -> None:
    out = tmp_path / "developer_preview_rc_status.json"
    out_md = tmp_path / "developer_preview_rc_status.md"
    module.write_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )

    assert ok is False
    assert message == "developer_preview_rc_status_mismatch"


def test_developer_preview_rc_status_check_allows_source_commit_wrapper_drift(
    tmp_path: Path,
) -> None:
    out = tmp_path / "developer_preview_rc_status.json"
    out_md = tmp_path / "developer_preview_rc_status.md"
    module.write_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["source_commit_sha"] = "previous-receipt-only-commit"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )

    assert ok is True
    assert message == "developer_preview_rc_status_consistent"


def test_developer_preview_rc_status_check_allows_readiness_checksum_cycle(
    tmp_path: Path,
) -> None:
    out = tmp_path / "developer_preview_rc_status.json"
    out_md = tmp_path / "developer_preview_rc_status.md"
    module.write_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/developer_preview_readiness.json"
    ] = "sha256:receipt-cycle-refresh"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_developer_preview_rc_status(
        repo_root=REPO_ROOT,
        out_path=out,
        out_md_path=out_md,
    )

    assert ok is True
    assert message == "developer_preview_rc_status_consistent"
