from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_science_actual_closure_operator_handoff.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_science_actual_closure_operator_handoff",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _slots_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    slots = payload["row_slot_handoffs"]
    assert isinstance(slots, list)
    return {
        str(slot["row_input_id"]): slot
        for slot in slots
        if isinstance(slot, dict) and "row_input_id" in slot
    }


def test_science_actual_closure_operator_handoff_exposes_all_row_slots() -> None:
    payload = module.build_science_actual_closure_operator_handoff(repo_root=REPO_ROOT)
    slots = _slots_by_id(payload)

    assert payload["schema_version"] == "science-actual-closure-operator-handoff.v1"
    assert payload["status"] == "operator_rows_required"
    assert payload["contract_pass"] is True
    assert payload["science_actual_closure_contract_pass"] is False
    assert payload["summary"] == {
        "actual_closure_blocked_component_count": 2,
        "actual_closure_blocked_requirement_count": 9,
        "actual_closure_complete_component_count": 1,
        "actual_closure_requirement_count": 19,
        "actual_closure_requirement_pass_count": 10,
        "blocker_count": 9,
        "blocked_component_operator_action_count": 2,
        "closes_actual_closure_criteria_count": 19,
        "component_count": 3,
        "expected_slot_count": 6,
        "missing_row_template_artifact_count": 0,
        "missing_slot_count": 2,
        "operator_rows_packet_missing_input_count": 2,
        "provided_slot_count": 4,
        "row_template_artifact_count": 6,
        "science_actual_closure_blocker_count": 2,
        "slot_count": 6,
        "upstream_source_blocker_count": 7,
        "upstream_source_context_count": 2,
    }
    assert payload["blocker_count"] == 9
    assert payload["science_actual_closure_blockers"] == [
        (
            "public_benchmark_phase2_actual_closure::"
            "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
        ),
        "pocketmd_lite_topk_actual_closure::pocketmd_lite_topk_rows_not_provided",
    ]
    assert payload["blockers"][:2] == [
        (
            "science_actual_closure::public_benchmark_phase2_actual_closure::"
            "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
        ),
        (
            "science_actual_closure::pocketmd_lite_topk_actual_closure::"
            "pocketmd_lite_topk_rows_not_provided"
        ),
    ]
    assert payload["blockers"][2:] == payload["upstream_source_blockers"]
    assert list(slots) == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
        "gpcr_rows",
        "pocketmd_rows",
    ]
    assert payload["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    assert payload["operator_rows_packet"]["status"] == "operator_rows_required"
    assert payload["operator_rows_packet"]["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    assert payload["operator_rows_packet"]["row_input_contract_count"] == 2
    assert payload["operator_rows_packet"]["first_missing_row_input"] == (
        "vina_gnina_rows"
    )
    completion_progress = payload["science_actual_closure_completion_progress"]
    assert completion_progress["status"] == "operator_evidence_required"
    assert completion_progress["actual_closure_ready"] is False
    assert completion_progress["requirement_count"] == 19
    assert completion_progress["requirement_pass_count"] == 10
    assert completion_progress["blocked_requirement_count"] == 9
    assert completion_progress["required_component_count"] == 3
    assert completion_progress["complete_component_ids"] == [
        "gpcr_hard_decoy_actual_closure"
    ]
    assert completion_progress["blocked_component_ids"] == [
        "public_benchmark_phase2_actual_closure",
        "pocketmd_lite_topk_actual_closure",
    ]
    assert completion_progress["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    component_progress = {
        row["component_id"]: row for row in completion_progress["component_progress"]
    }
    assert component_progress["gpcr_hard_decoy_actual_closure"]["status"] == (
        "complete"
    )
    assert component_progress["gpcr_hard_decoy_actual_closure"][
        "requirement_pass_count"
    ] == 5
    assert component_progress["public_benchmark_phase2_actual_closure"][
        "failed_criteria"
    ] == ["vina_gnina_comparison_ready"]
    assert component_progress["pocketmd_lite_topk_actual_closure"][
        "missing_row_inputs"
    ] == ["pocketmd_rows"]
    unblock_plan = {
        row["row_input_id"]: row for row in payload["blocking_input_unblock_plan"]
    }
    assert payload["blocking_input_unblock_plan_count"] == 2
    assert sorted(unblock_plan) == ["pocketmd_rows", "vina_gnina_rows"]
    assert unblock_plan["vina_gnina_rows"]["status"] == "engine_inputs_required"
    assert unblock_plan["vina_gnina_rows"]["first_operator_sequence_step"] == (
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight"
    )
    assert unblock_plan["vina_gnina_rows"]["expected_rows_artifact"].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert unblock_plan["vina_gnina_rows"]["artifact_refs"][
        "input_manifest_template_preflight_artifact"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template_preflight.json")
    assert unblock_plan["vina_gnina_rows"]["artifact_refs"][
        "rows_template_preflight_artifact"
    ].endswith("public_benchmark_vina_gnina_rows_template_preflight.json")
    assert unblock_plan["vina_gnina_rows"]["counts"][
        "blocked_engine_run_slot_count"
    ] == 24
    vina_runtime_action = unblock_plan["vina_gnina_rows"]["runtime_action_packet"]
    assert vina_runtime_action["runtime_readiness_blocker_count"] == 124
    assert vina_runtime_action["blocked_case_input_slot_count"] == 12
    assert vina_runtime_action["blocked_engine_run_slot_count"] == 24
    assert vina_runtime_action["missing_engine_ids"] == ["vina", "gnina"]
    assert vina_runtime_action["adapter_row_preflight_status"] == (
        "row_artifact_missing"
    )
    assert vina_runtime_action["engine_run_bundle_status"] == (
        "execution_plan_not_ready"
    )
    assert vina_runtime_action["engine_run_bundle_materialized"] is False
    assert vina_runtime_action["rows_from_engine_run_bundle_status"] == (
        "engine_run_bundle_not_ready"
    )
    assert vina_runtime_action["rows_from_engine_run_bundle_materialized"] is False
    assert vina_runtime_action["engine_run_bundle_summary"]["artifact"].endswith(
        "public_benchmark_vina_gnina_engine_run_bundle.json"
    )
    assert vina_runtime_action["rows_from_engine_run_bundle_report_summary"][
        "artifact"
    ].endswith("public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json")
    assert vina_runtime_action["input_manifest_template_preflight_status"] == (
        "operator_manifest_completion_required"
    )
    assert vina_runtime_action["input_manifest_template_manifest_ready"] is False
    manifest_preflight = vina_runtime_action[
        "input_manifest_template_preflight_summary"
    ]
    assert manifest_preflight["template_row_count"] == 12
    assert manifest_preflight["template_case_coverage_complete"] is True
    assert manifest_preflight["invalid_source_receipt_count"] == 0
    assert manifest_preflight["unsupported_benchmark_field_count"] == 0
    assert manifest_preflight["missing_local_file_count"] == 48
    assert manifest_preflight["missing_receipt_ref_count"] == 60
    assert vina_runtime_action["input_manifest_completion_action_case_count"] == 12
    assert vina_runtime_action["input_manifest_completion_blocked_case_count"] == 12
    first_manifest_action = vina_runtime_action[
        "input_manifest_completion_action_plan"
    ][0]
    assert first_manifest_action["case_id"] == "casf2016_4llx"
    assert first_manifest_action["operator_completion_action"] == (
        "complete_vina_gnina_input_manifest_row_for_casf2016_4llx"
    )
    assert vina_runtime_action["engine_runtime_actions"] == [
        {
            "binary_env_var": "PUBLIC_BENCHMARK_VINA_BIN",
            "container_image_env_var": "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE",
            "engine_id": "vina",
            "operator_action": "configure_vina_runtime",
        },
        {
            "binary_env_var": "PUBLIC_BENCHMARK_GNINA_BIN",
            "container_image_env_var": "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE",
            "engine_id": "gnina",
            "operator_action": "configure_gnina_runtime",
        },
    ]
    assert vina_runtime_action["first_blocked_case_input_slot"]["case_id"] == (
        "casf2016_4llx"
    )
    assert vina_runtime_action["first_blocked_case_input_slot"][
        "operator_action"
    ] == "fill_vina_gnina_input_manifest_row_for_casf2016_4llx"
    assert vina_runtime_action["first_blocked_engine_run_slot"]["case_id"] == (
        "casf2016_4llx"
    )
    assert vina_runtime_action["first_blocked_engine_run_slot"]["engine_id"] == (
        "vina"
    )
    assert vina_runtime_action["first_blocked_engine_run_slot"][
        "docking_run_id"
    ] == "casf2016_4llx_vina_run"
    assert unblock_plan["vina_gnina_rows"][
        "first_blocked_case_input_slot"
    ] == vina_runtime_action["first_blocked_case_input_slot"]
    assert unblock_plan["vina_gnina_rows"][
        "first_blocked_engine_run_slot"
    ] == vina_runtime_action["first_blocked_engine_run_slot"]
    assert unblock_plan["vina_gnina_rows"]["commands"][
        "build_rows_template_preflight"
    ].startswith("python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py")
    assert unblock_plan["pocketmd_rows"]["status"] == (
        "operator_refinement_rows_required"
    )
    assert unblock_plan["pocketmd_rows"]["first_operator_sequence_step"] == (
        "preflight_pocketmd_lite_topk_rows_template"
    )
    assert unblock_plan["pocketmd_rows"]["expected_rows_artifact"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert unblock_plan["pocketmd_rows"]["artifact_refs"][
        "row_template_preflight_artifact"
    ].endswith("pocketmd_lite_topk_rows_template_preflight.json")
    assert unblock_plan["pocketmd_rows"]["counts"][
        "missing_candidate_slot_count"
    ] == 6
    pocketmd_refinement_action = unblock_plan["pocketmd_rows"][
        "refinement_action_packet"
    ]
    assert pocketmd_refinement_action["missing_candidate_slot_count"] == 6
    assert pocketmd_refinement_action["first_missing_candidate_slot"] == {
        "case_id": "pocketmd_lite_case_001",
        "operator_action": (
            "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
        ),
        "slot_id": "pocketmd_lite_case_001_rank_01",
        "top_k_rank": 1,
    }
    assert pocketmd_refinement_action["first_blocked_role_receipt"][
        "role_id"
    ] == "upstream_top_k_candidate_scope_receipt"
    assert pocketmd_refinement_action["first_blocked_role_receipt"][
        "candidate_id"
    ] == "pocketmd_lite_case_001_rank_01"
    assert pocketmd_refinement_action[
        "first_blocked_operator_input_source_receipt"
    ]["field"] == "source_id"
    assert pocketmd_refinement_action["rows_from_receipt_bundle_status"] == (
        "operator_receipts_completion_required"
    )
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_receipt_count"
    ] == 6
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_ready_receipt_count"
    ] == 0
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_incomplete_receipt_count"
    ] == 6
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_missing_required_field_count"
    ] == 18
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_unique_missing_required_field_count"
    ] == 18
    assert pocketmd_refinement_action[
        "rows_from_receipt_bundle_total_missing_required_field_count"
    ] == 108
    receipt_bundle_report = pocketmd_refinement_action[
        "rows_from_receipt_bundle_report"
    ]
    assert receipt_bundle_report["artifact"].endswith(
        "pocketmd_lite_topk_rows_from_receipt_bundle_report.json"
    )
    assert receipt_bundle_report["ready_receipt_count"] == 0
    assert receipt_bundle_report["receipt_count"] == 6
    assert receipt_bundle_report["incomplete_receipt_count"] == 6
    assert len(receipt_bundle_report["receipt_completion_action_plan"]) == 6
    assert receipt_bundle_report["receipt_metric_family_count"] == 5
    assert receipt_bundle_report["receipt_metric_family_blocked_count"] == 5
    assert (
        receipt_bundle_report[
            "receipt_metric_family_missing_field_occurrence_count"
        ]
        == 54
    )
    assert receipt_bundle_report["receipt_metric_family_completion_plan"][0][
        "metric_family_id"
    ] == "local_min_survival"
    first_incomplete_receipt = pocketmd_refinement_action[
        "first_incomplete_receipt"
    ]
    assert first_incomplete_receipt["receipt_ref"].endswith(
        "pocketmd_lite_case_001/rank_01_refinement_receipt.json"
    )
    assert first_incomplete_receipt[
        "completion_missing_required_field_count"
    ] == 18
    assert first_incomplete_receipt["operator_completion_action"] == (
        "fill_completion_missing_required_fields_and_set_status_complete"
    )
    assert "upstream_top_k_provenance_ref" in first_incomplete_receipt[
        "completion_missing_required_fields"
    ]
    assert unblock_plan["pocketmd_rows"][
        "rows_from_receipt_bundle_report"
    ] == receipt_bundle_report
    assert unblock_plan["pocketmd_rows"][
        "first_incomplete_receipt"
    ] == first_incomplete_receipt
    survival_report = pocketmd_refinement_action["survival_report"]
    assert survival_report["status"] == "operator_evidence_required"
    assert survival_report["contract_pass"] is False
    assert survival_report["product_surface_ready"] is False
    assert survival_report["first_blocked_target"] == (
        "top_k_refinement_operator_intake"
    )
    assert survival_report["blocker_count"] == 6
    assert survival_report["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_persistence_rows_missing",
        "pocketmd_lite_h_bond_persistence_rows_missing",
        "pocketmd_lite_clash_relief_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
    ]
    assert survival_report["real_refinement_case_count"] == 0
    assert survival_report["top_k_candidate_count"] == 0
    assert unblock_plan["pocketmd_rows"][
        "first_missing_candidate_slot"
    ] == pocketmd_refinement_action["first_missing_candidate_slot"]
    assert unblock_plan["pocketmd_rows"][
        "first_blocked_role_receipt"
    ] == pocketmd_refinement_action["first_blocked_role_receipt"]
    assert unblock_plan["pocketmd_rows"][
        "survival_report"
    ] == pocketmd_refinement_action["survival_report"]
    assert unblock_plan["pocketmd_rows"]["commands"][
        "materialize_survival_report"
    ].startswith("python3 scripts/materialize_pocketmd_lite_topk_survival_report.py")
    row_contracts = payload["row_input_materialization_contracts"]
    assert sorted(row_contracts) == ["pocketmd_rows", "vina_gnina_rows"]
    assert row_contracts["vina_gnina_rows"]["operator_action"] == (
        "attach_vina_gnina_rows_at_"
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json"
    )
    vina_contract_detail = row_contracts["vina_gnina_rows"][
        "row_input_slot_detail"
    ]
    assert vina_contract_detail["status"] == "execution_plan_blocked"
    assert vina_contract_detail["required_engine_run_count"] == 24
    assert vina_contract_detail["ready_engine_run_slot_count"] == 0
    assert vina_contract_detail["blocked_engine_run_slot_count"] == 24
    assert vina_contract_detail["runtime_readiness_blocker_count"] == 124
    assert vina_contract_detail["missing_engine_ids"] == ["vina", "gnina"]
    assert vina_contract_detail["engine_run_status_summary"][
        "first_blocked_engine_run_slot"
    ]["case_id"] == "casf2016_4llx"
    assert row_contracts["pocketmd_rows"]["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    pocketmd_contract_detail = row_contracts["pocketmd_rows"][
        "row_input_slot_detail"
    ]
    assert pocketmd_contract_detail["missing_candidate_slot_count"] == 6
    assert pocketmd_contract_detail["provided_candidate_slot_count"] == 0
    assert pocketmd_contract_detail["first_missing_candidate_slot"] == {
        "case_id": "pocketmd_lite_case_001",
        "operator_action": (
            "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
        ),
        "slot_id": "pocketmd_lite_case_001_rank_01",
        "top_k_rank": 1,
    }
    blocked_actions = {
        row["component_id"]: row for row in payload["blocked_component_operator_actions"]
    }
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_ids"
    ] == ["vina_gnina_rows"]
    public_action = blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_actions"
    ][0]
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "missing_row_input_action_count"
    ] == 1
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "operator_action"
    ] == (
        "attach_vina_gnina_rows_at_"
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json"
    )
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "source_acquisition_operator_action"
    ] == "resolve_public_benchmark_phase2_source_acquisition_blockers"
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in blocked_actions[
        "public_benchmark_phase2_actual_closure"
    ]["upstream_source_blockers"]
    assert blocked_actions["public_benchmark_phase2_actual_closure"][
        "first_missing_row_input_action"
    ] == public_action
    assert public_action["row_input_id"] == "vina_gnina_rows"
    assert public_action["operator_action"] == (
        "attach_vina_gnina_rows_at_"
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json"
    )
    assert public_action["preferred_default_row_path"].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert public_action["row_template_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template.csv"
    )
    assert public_action["source_acquisition_operator_action"] == (
        "resolve_public_benchmark_phase2_source_acquisition_blockers"
    )
    assert public_action["source_acquisition_operator_next_actions"][:2] == [
        "review_official_source_receipt_plan",
        "attach_casf_pdbbind_subset_rows_with_local_file_checksums",
    ]
    assert public_action["source_acquisition_operator_next_actions"][-2:] == [
        "run_public_benchmark_harness_bundle_materializer",
        "refresh_public_benchmark_source_of_truth",
    ]
    assert public_action["source_acquisition_row_action"]["operator_action"] == (
        "attach_vina_gnina_rows_then_run_phase2_row_audit"
    )
    assert public_action["source_acquisition_row_action"][
        "closes_phase2_criteria"
    ] == ["vina_gnina_comparison_ready"]
    assert public_action["source_acquisition_row_action"][
        "runtime_readiness_command"
    ].startswith("python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py")
    assert "engine_config_checksum" in public_action["source_acquisition_row_action"][
        "receipt_fields"
    ]
    public_manifest_action = public_action["source_acquisition_row_action"][
        "engine_input_manifest_action_packet"
    ]
    assert public_manifest_action["expected_manifest_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert public_manifest_action["default_execution_plan_manifest_path"].endswith(
        "public_benchmark_vina_gnina_input_manifest.json"
    )
    assert public_manifest_action["recommended_template_dropzone"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert (
        public_manifest_action[
            "recommended_template_dropzone_is_supported_candidate_path"
        ]
        is True
    )
    assert public_manifest_action["supported_manifest_candidate_paths"][3].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert public_manifest_action["detected_manifest_artifact_count"] == 1
    assert public_manifest_action["input_manifest_load_errors"] == []
    assert public_manifest_action["source_archive_operator_artifact"] == (
        "<CASF-2016.tar.gz>"
    )
    assert public_manifest_action["source_archive_extraction_command"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
        "--archive <CASF-2016.tar.gz>"
    )
    assert public_manifest_action[
        "source_archive_extraction_report_artifact"
    ].endswith(
        "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json"
    )
    assert public_manifest_action["template_safety_policy"][
        "template_is_not_evidence"
    ] is True
    public_adapter_preflight_action = public_action["source_acquisition_row_action"][
        "adapter_row_preflight_action_packet"
    ]
    assert public_adapter_preflight_action["status"] == "row_artifact_missing"
    assert public_adapter_preflight_action["supported_candidate_paths"][3].endswith(
        "public_benchmark_vina_gnina_rows.csv"
    )
    assert public_adapter_preflight_action["row_template_preflight_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template_preflight.json"
    )
    assert public_adapter_preflight_action["role_receipt_plan_summary"][
        "role_receipt_blocked_count"
    ] == 72
    assert public_adapter_preflight_action["role_receipt_plan_summary"][
        "first_blocked_role_receipt"
    ]["role_id"] == "engine_run_artifact_receipt"
    assert public_adapter_preflight_action["role_receipt_plan_summary"][
        "first_blocked_role_receipt"
    ]["slot_id"] == "casf2016_4llx_vina_casf2016_4llx_vina_run"
    assert "build_public_benchmark_vina_gnina_rows_template_preflight.py" in public_adapter_preflight_action[
        "build_row_template_preflight_command"
    ]
    assert public_adapter_preflight_action["template_safety_policy"][
        "preflight_does_not_run_engines"
    ] is True
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in public_action[
        "upstream_source_blockers"
    ]
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_ids"
    ] == ["pocketmd_rows"]
    pocketmd_action = blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_actions"
    ][0]
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_action_count"
    ] == 1
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "operator_action"
    ] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "source_acquisition_operator_action"
    ] == "resolve_pocketmd_lite_source_acquisition_blockers"
    assert "pocketmd_lite_topk_rows_not_acquired" in blocked_actions[
        "pocketmd_lite_topk_actual_closure"
    ]["upstream_source_blockers"]
    assert blocked_actions["pocketmd_lite_topk_actual_closure"][
        "first_missing_row_input_action"
    ] == pocketmd_action
    assert pocketmd_action["row_input_id"] == "pocketmd_rows"
    assert pocketmd_action["operator_action"] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_action["preferred_default_row_path"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_action["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert pocketmd_action["source_acquisition_operator_action"] == (
        "resolve_pocketmd_lite_source_acquisition_blockers"
    )
    assert pocketmd_action["source_acquisition_operator_next_actions"][:2] == [
        "review_phase4_refinement_receipt_plan",
        "build_pocketmd_lite_refinement_execution_plan",
    ]
    assert pocketmd_action["source_acquisition_operator_next_actions"][-2:] == [
        "run_pocketmd_lite_raw_row_importer_and_survival_materializer",
        "refresh_science_actual_closure_from_rows",
    ]
    assert pocketmd_action["source_acquisition_row_action"]["operator_action"] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_action["source_acquisition_completion_audit"]["status"] == (
        "operator_topk_rows_required"
    )
    assert pocketmd_action["source_acquisition_completion_audit"][
        "ready_requirement_count"
    ] == 2
    assert pocketmd_action["source_acquisition_completion_audit"][
        "blocked_requirement_count"
    ] == 7
    assert "uncertainty_summary_materialized" in pocketmd_action[
        "source_acquisition_row_action"
    ]["closes_phase4_criteria"]
    assert "materialize_survival" in pocketmd_action["source_acquisition_row_action"][
        "commands"
    ]
    assert "uncertainty_interval_receipt" in pocketmd_action[
        "source_acquisition_row_action"
    ]["required_receipt_roles"]
    pocketmd_preflight_action = pocketmd_action["source_acquisition_row_action"][
        "row_preflight_action_packet"
    ]
    assert pocketmd_preflight_action["status"] == "row_artifact_missing"
    assert pocketmd_preflight_action["supported_candidate_paths"][4].endswith(
        "pocketmd_lite_topk_rows.tsv"
    )
    assert len(pocketmd_preflight_action["missing_required_slots"]) == 6
    assert pocketmd_preflight_action["template_preflight_summary"][
        "role_receipt_blocked_count"
    ] == 24
    assert pocketmd_preflight_action["template_preflight_summary"][
        "operator_input_source_receipt_blocked_count"
    ] == 5
    assert pocketmd_preflight_action["template_safety_policy"][
        "preflight_does_not_run_refinement"
    ] is True
    pocketmd_topk_action = pocketmd_action["source_acquisition_row_action"][
        "top_k_rows_action_packet"
    ]
    assert pocketmd_topk_action["expected_rows_artifact"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_topk_action["role_receipt_plan_summary"][
        "role_receipt_blocked_count"
    ] == 24
    assert pocketmd_topk_action["role_receipt_plan_summary"][
        "first_blocked_role_receipt"
    ]["role_id"] == "upstream_top_k_candidate_scope_receipt"
    assert pocketmd_topk_action["operator_input_source_receipt_plan_summary"][
        "blocked_count"
    ] == 5
    assert pocketmd_topk_action["operator_input_source_receipt_plan_summary"][
        "first_blocked_receipt"
    ]["field"] == "source_id"
    assert pocketmd_topk_action["phase4_metric_receipt_action_count"] == 8
    metric_receipt_actions = {
        row["criterion_id"]: row
        for row in pocketmd_topk_action["phase4_metric_receipt_actions"]
    }
    assert metric_receipt_actions["local_min_survival_materialized"][
        "receipt_roles"
    ] == ["lite_refinement_run_receipt"]
    assert metric_receipt_actions["uncertainty_summary_materialized"][
        "required_row_fields"
    ] == ["uncertainty_low", "uncertainty_high", "uncertainty_unit"]
    assert pocketmd_topk_action["template_safety_policy"][
        "placeholder_or_fixture_rows_do_not_promote"
    ] is True
    pocketmd_rows_arg = (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
    assert (
        pocketmd_rows_arg
        in pocketmd_topk_action["verify_science_actual_closure_command"]
    )
    assert "--source-url <source-url>" in pocketmd_topk_action[
        "verify_science_actual_closure_command"
    ]
    assert "pocketmd_lite_topk_rows_not_acquired" in pocketmd_action[
        "upstream_source_blockers"
    ]
    assert len(payload["upstream_source_blockers"]) == 7
    assert payload["upstream_source_acquisition"]["public_benchmark_phase2"][
        "present"
    ] is True
    assert payload["upstream_source_acquisition"]["pocketmd_lite"]["present"] is True
    assert payload["missing_row_template_artifacts"] == []
    assert payload["row_template_artifacts"] == {
        "enrichment_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_enrichment_rows_template.csv"
        ),
        "gpcr_rows": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_rows_template.csv"
        ),
        "pocketmd_rows": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_rows_template.csv"
        ),
        "pose_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_pose_rows_template.csv"
        ),
        "subset_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_rows_template.csv"
        ),
        "vina_gnina_rows": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_rows_template.csv"
        ),
    }
    assert payload["first_missing_slot"]["row_input_id"] == "vina_gnina_rows"

    subset = slots["subset_rows"]
    assert subset["status"] == "provided"
    assert subset["missing"] is False
    assert subset["row_template_present"] is True
    assert subset["row_template_artifact"].endswith(
        "public_benchmark_subset_rows_template.csv"
    )
    assert subset["preferred_default_row_path"].endswith(
        "public_benchmark_subset_rows.json"
    )
    assert subset["actual_closure_component_id"] == (
        "public_benchmark_phase2_actual_closure"
    )
    assert "casf_pdbbind_pose_success_harness_ready" in subset[
        "closes_actual_closure_criteria"
    ]
    assert "source_receipt_required_fields" in subset["contract_field_groups"]
    assert any(
        "materialize_public_benchmark" in step
        for step in subset["materialization_chain"]
    )

    pose = slots["pose_rows"]
    assert pose["status"] == "provided"
    assert {
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    }.issubset(set(pose["closes_actual_closure_criteria"]))
    assert "required_pose_fields" in pose["contract_field_groups"]

    enrichment = slots["enrichment_rows"]
    assert enrichment["status"] == "provided"

    vina_gnina = slots["vina_gnina_rows"]
    assert vina_gnina["status"] == "operator_input_required"
    assert vina_gnina["missing"] is True
    assert vina_gnina["upstream_source_id"] == "public_benchmark_phase2"
    assert vina_gnina["upstream_source_acquisition"][
        "phase2_row_closure_matrix_count"
    ] == 4
    assert vina_gnina["upstream_source_acquisition"][
        "phase2_exit_criterion_count"
    ] == 5
    assert vina_gnina["upstream_source_acquisition"][
        "source_access_preflight_count"
    ] == 6
    assert vina_gnina["upstream_source_acquisition"][
        "source_access_preflight_rows"
    ][0]["source_id"] == "pdbbind_plus_casf"
    assert vina_gnina["upstream_source_acquisition"][
        "source_access_preflight_receipt_artifact"
    ].endswith("public_benchmark_source_access_preflight_receipt.json")
    assert vina_gnina["upstream_source_acquisition"][
        "source_access_network_probe_command"
    ].endswith("--probe-network")
    receipt_summary = vina_gnina["upstream_source_acquisition"][
        "source_access_preflight_receipt_summary"
    ]
    assert receipt_summary["status"] == "reachable"
    assert receipt_summary["network_probe_performed"] is True
    assert receipt_summary["source_access_ready"] is True
    assert receipt_summary["reachable_count"] == 6
    assert receipt_summary["blocked_count"] == 0
    external_receipts = vina_gnina["upstream_source_acquisition"][
        "external_receipts_validation_summary"
    ]
    assert external_receipts["summary_source"] == "source_acquisition_plan"
    assert external_receipts["status"] == "operator_receipts_required"
    assert external_receipts["public_benchmark_external_receipts_ready"] is False
    assert external_receipts["materialized_row_count"] == 13
    assert external_receipts["receipt_complete_row_count"] == 13
    assert external_receipts["receipt_complete_artifact_role_count"] == 2
    assert external_receipts["expected_artifact_role_count"] == 3
    assert external_receipts["missing_expected_artifact_roles"] == [
        "vina_gnina_comparison_adapter",
    ]
    assert vina_gnina["upstream_source_acquisition"][
        "vina_gnina_case_input_slot_matrix_count"
    ] == 12
    assert vina_gnina["upstream_source_acquisition"][
        "vina_gnina_blocked_case_input_slot_count"
    ] == 12
    assert vina_gnina["upstream_source_acquisition"][
        "vina_gnina_engine_run_slot_matrix_count"
    ] == 24
    assert vina_gnina["upstream_source_acquisition"][
        "vina_gnina_blocked_engine_run_slot_count"
    ] == 24
    upstream_runtime = vina_gnina["upstream_source_acquisition"][
        "vina_gnina_runtime_readiness"
    ]
    assert upstream_runtime["status"] == "execution_plan_blocked"
    assert upstream_runtime["operator_unblock_packet"][
        "input_manifest_template_preflight_artifact"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template_preflight.json")
    assert upstream_runtime["operator_unblock_packet"]["operator_sequence"][0] == (
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight"
    )
    vina_gnina_actual = vina_gnina["upstream_source_acquisition"][
        "vina_gnina_actual_evidence_audit"
    ]
    assert vina_gnina_actual["status"] == "engine_input_manifest_required"
    assert vina_gnina_actual["blocked_component_count"] == 6
    assert vina_gnina_actual["components"][0]["component_id"] == (
        "engine_input_manifest"
    )
    assert vina_gnina["source_acquisition_operator_action"] == (
        "resolve_public_benchmark_phase2_source_acquisition_blockers"
    )
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in vina_gnina[
        "upstream_source_blockers"
    ]
    assert "public_benchmark_vina_gnina_input_manifest_not_detected" not in vina_gnina[
        "upstream_source_blockers"
    ]
    vina_detail = vina_gnina["row_input_slot_detail"]
    assert vina_detail["artifact"].endswith(
        "public_benchmark_vina_gnina_runtime_readiness.json"
    )
    assert vina_detail["engine_run_status_summary"] == {
        "blocked_engine_run_slot_count": 24,
        "first_blocked_engine_run_slot": vina_detail["engine_run_slots"][0],
        "first_ready_engine_run_slot": {},
        "ready_engine_run_slot_count": 0,
        "required_engine_run_count": 24,
    }
    assert vina_detail["engine_run_slots"][0]["operator_actions"] == [
        "resolve_vina_gnina_case_inputs_for_casf2016_4llx",
        "configure_vina_runtime",
        "attach_vina_gnina_adapter_row_for_casf2016_4llx_vina",
    ]
    assert vina_detail["operator_unblock_packet"]["status"] == (
        "engine_inputs_required"
    )
    assert vina_detail["operator_unblock_packet"][
        "input_manifest_template_artifact"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template.csv")
    assert vina_detail["operator_unblock_packet"][
        "input_manifest_template_preflight_artifact"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template_preflight.json")
    assert vina_detail["operator_unblock_packet"]["operator_sequence"][0] == (
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight"
    )
    assert vina_detail["operator_unblock_packet"][
        "blocked_engine_run_slot_count"
    ] == 24
    assert vina_detail["engine_run_slots"][0]["required_adapter_engine_run_fields"] == [
        "engine_id",
        "docking_run_id",
        "predicted_ligand_path_or_pose_ref",
        "predicted_ligand_checksum",
        "engine_version",
        "engine_config_checksum",
        "engine_run_provenance_ref",
        "symmetry_aware_rmsd_angstrom",
        "pose_success",
        "score",
        "score_direction",
    ]

    gpcr = slots["gpcr_rows"]
    assert gpcr["actual_closure_component_id"] == "gpcr_hard_decoy_actual_closure"
    assert gpcr["status"] == "provided"
    assert gpcr["missing"] is False
    assert gpcr["row_template_present"] is True
    assert gpcr["row_template_artifact"].endswith(
        "gpcr_hard_decoy_rows_template.csv"
    )
    assert "raw_hard_decoy_rows_actual_closure" in gpcr[
        "closes_actual_closure_criteria"
    ]
    assert gpcr["materialization_command"].startswith(
        "python3 scripts/materialize_science_actual_closure_from_rows.py --gpcr-rows"
    )
    assert gpcr["contract_field_groups"]["source_receipt_required_fields"] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact_sha256",
    ]
    gpcr_detail = gpcr["row_input_slot_detail"]
    assert gpcr_detail["artifact"].endswith("gpcr_hard_decoy_suite_report.json")
    assert gpcr_detail["status"] == "ready"
    assert gpcr_detail["actual_closure_ready"] is True
    assert gpcr_detail["phase3_exit_gate_status"] == "ready"
    assert gpcr_detail["phase3_failed_criteria"] == []
    assert gpcr_detail["target_count"] == 3
    assert gpcr_detail["target_pass_count"] == 3
    assert gpcr_detail["exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert gpcr_detail["observed_threshold_metrics"] == {
        "decoys_above_positive_count_max_observed": 0,
        "positive_out_anchored_target_count": 0,
        "ranking_pr_auc_ci_low_min_observed": 1,
        "top20_hit_rate_min_observed": 0.6,
    }
    assert gpcr_detail["target_rows"][0] == {
        "blockers": [],
        "contract_pass": True,
        "criteria": {
            "decoys_above_positive_count_max": 0,
            "positive_out_anchored_by_top_decoys_allowed": False,
            "ranking_pr_auc_ci_low_min": 0.45,
            "top20_hit_rate_min": 0.2,
        },
        "decoys_above_positive_count": 0,
        "positive_out_anchored_by_top_decoys": False,
        "ranking_pr_auc_ci_low": 1,
        "status": "pass",
        "target_id": "DRD2",
        "top20_hit_rate": 0.6,
    }

    pocketmd = slots["pocketmd_rows"]
    assert pocketmd["actual_closure_component_id"] == (
        "pocketmd_lite_topk_actual_closure"
    )
    assert pocketmd["status"] == "operator_input_required"
    assert pocketmd["missing"] is True
    assert pocketmd["row_template_present"] is True
    assert pocketmd["row_template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert pocketmd["upstream_source_id"] == "pocketmd_lite"
    assert pocketmd["upstream_source_acquisition"][
        "phase4_candidate_slot_matrix_count"
    ] == 6
    assert pocketmd["upstream_source_acquisition"][
        "phase4_missing_candidate_slot_count"
    ] == 6
    assert pocketmd["upstream_source_acquisition"][
        "phase4_metric_closure_matrix_count"
    ] == 8
    phase4_audit = pocketmd["upstream_source_acquisition"][
        "phase4_completion_audit"
    ]
    assert pocketmd["upstream_source_acquisition"][
        "phase4_completion_audit_status"
    ] == "operator_topk_rows_required"
    assert pocketmd["upstream_source_acquisition"][
        "phase4_completion_blocked_requirement_count"
    ] == 7
    assert phase4_audit["ready_requirement_count"] == 2
    assert phase4_audit["requirement_count"] == 9
    assert phase4_audit["remaining_row_inputs"] == ["pocketmd_rows"]
    assert phase4_audit["remaining_operator_action"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert phase4_audit["blocked_requirement_ids"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_reported",
        "contact_persistence_reported",
        "h_bond_persistence_reported",
        "clash_relief_reported",
        "uncertainty_reported",
    ]
    assert pocketmd["source_acquisition_operator_action"] == (
        "resolve_pocketmd_lite_source_acquisition_blockers"
    )
    pocketmd_actual = pocketmd["upstream_source_acquisition"][
        "phase4_actual_evidence_audit"
    ]
    assert pocketmd_actual["status"] == "operator_topk_rows_required"
    assert pocketmd_actual["blocked_component_count"] == 4
    assert pocketmd_actual["components"][0]["component_id"] == (
        "bounded_top_k_row_slots"
    )
    pocketmd_blocker_families = {
        row["family_id"]: row
        for row in pocketmd_actual["operator_blocker_family_plan"]
    }
    assert pocketmd_blocker_families["top_k_candidate_rows"]["next_action"] == (
        "attach_pocketmd_lite_topk_rows_at_default_dropzone"
    )
    assert pocketmd_blocker_families["top_k_candidate_rows"]["command_key"] == (
        "materialize_rows_from_receipt_bundle"
    )
    assert (
        "materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py"
        in pocketmd_blocker_families["top_k_candidate_rows"][
            "materialization_command"
        ]
    )
    assert "pocketmd_lite_topk_rows_not_acquired" in pocketmd[
        "upstream_source_blockers"
    ]
    assert "top_k_refinement_rows_present" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "broad_all_atom_fep_claims_locked" in pocketmd[
        "closes_actual_closure_criteria"
    ]
    assert "required_case_fields" in pocketmd["contract_field_groups"]
    assert "uncertainty_field_modes" in pocketmd["contract_field_groups"]
    assert pocketmd["row_input_slot_detail"]["artifact"].endswith(
        "pocketmd_lite_refinement_execution_plan.json"
    )
    assert pocketmd["row_input_slot_detail"]["top_k_slot_status_summary"][
        "missing_candidate_slot_count"
    ] == 6
    assert pocketmd["row_input_slot_detail"]["operator_unblock_packet"]["status"] == (
        "operator_refinement_rows_required"
    )
    assert pocketmd["row_input_slot_detail"]["operator_unblock_packet"][
        "row_template_artifact"
    ].endswith("pocketmd_lite_topk_rows_template.csv")
    assert pocketmd["row_input_slot_detail"]["operator_unblock_packet"][
        "row_template_preflight_artifact"
    ].endswith("pocketmd_lite_topk_rows_template_preflight.json")
    assert pocketmd["row_input_slot_detail"]["row_template_preflight"][
        "status"
    ] == "operator_rows_completion_required"
    assert pocketmd["row_input_slot_detail"]["row_template_preflight"][
        "missing_metric_value_count"
    ] > 0
    assert pocketmd["row_input_slot_detail"]["candidate_slot_statuses"][0] == {
        "case_id": "pocketmd_lite_case_001",
        "expected_rows_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_rows.json"
        ),
        "missing": True,
        "operator_action": (
            "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
        ),
        "provided": False,
        "required_metric_fields": [
            "local_min_survived",
            "contact_persistence_rate",
            "h_bond_persistence_rate",
            "clash_count_before",
            "clash_count_after",
            "uncertainty_low",
            "uncertainty_high",
            "uncertainty_unit",
        ],
        "required_receipt_fields": [
            "upstream_top_k_provenance_ref",
            "upstream_top_k_source_checksum",
            "provenance_ref",
            "source_checksum",
            "operator_input_source.source_artifact",
            "operator_input_source.source_artifact_sha256",
            "operator_input_source.source_id",
            "operator_input_source.source_url",
            "operator_input_source.source_license",
        ],
        "slot_id": "pocketmd_lite_case_001_rank_01",
        "status": "row_slot_missing",
        "top_k_rank": 1,
    }

    component_summaries = {
        row["component_id"]: row for row in payload["component_slot_summary"]
    }
    assert component_summaries["public_benchmark_phase2_actual_closure"][
        "missing_row_input_ids"
    ] == ["vina_gnina_rows"]
    assert component_summaries["gpcr_hard_decoy_actual_closure"][
        "missing_row_input_ids"
    ] == []
    assert component_summaries["pocketmd_lite_topk_actual_closure"][
        "missing_row_input_ids"
    ] == ["pocketmd_rows"]


def test_science_actual_closure_operator_handoff_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "handoff.json"
    out_md = tmp_path / "handoff.md"

    assert module.main(
        [
            "--repo-root",
            str(REPO_ROOT),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["row_slot_handoff_count"] == 6
    assert payload["summary"]["row_template_artifact_count"] == 6
    assert payload["summary"]["missing_slot_count"] == 2
    assert payload["input_checksums"][
        "scripts/build_science_actual_closure_operator_handoff.py"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_refinement_execution_plan.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows_template_preflight.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_survival_report.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_runtime_readiness.json"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_suite_report.json"
    ].startswith("sha256:")
    assert "| `subset_rows` | `provided` |" in markdown
    assert "| `vina_gnina_rows` | `operator_input_required` |" in markdown
    assert "| `pocketmd_rows` | `operator_input_required` |" in markdown
    assert "- `blocker_count`: `9`" in markdown
    assert "## Actual Closure Progress" in markdown
    assert "- `requirements`: `10/19`" in markdown
    assert "- `blocked_requirement_count`: `9`" in markdown
    assert "- `complete_components`: `1/3`" in markdown
    assert (
        "| `public_benchmark_phase2_actual_closure` | `operator_rows_required` | "
        "`4/5` | `vina_gnina_rows` | `vina_gnina_comparison_ready` |"
    ) in markdown
    assert (
        "| `gpcr_hard_decoy_actual_closure` | `complete` | `5/5` | `none` | "
        "`none` |"
    ) in markdown
    assert "## Missing Row Packet" in markdown
    assert "First Blocked Slot" in markdown
    assert (
        "case:casf2016_4llx/"
        "fill_vina_gnina_input_manifest_row_for_casf2016_4llx"
    ) in markdown
    assert "engine:casf2016_4llx/vina/casf2016_4llx_vina_run" in markdown
    assert "bundle:execution_plan_not_ready" in markdown
    assert "rows_bundle:engine_run_bundle_not_ready" in markdown
    assert (
        "candidate:pocketmd_lite_case_001_rank_01/"
        "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01"
    ) in markdown
    assert (
        "role:upstream_top_k_candidate_scope_receipt/"
        "pocketmd_lite_case_001_rank_01"
    ) in markdown
    assert "source:source_id/attach_operator_input_source_source_id" in markdown
    assert "report:top_k_refinement_operator_intake" in markdown
    assert "## Blocked Component Actions" in markdown
    assert "public_benchmark_phase2_actual_closure" in markdown
    assert "pocketmd_lite_topk_actual_closure" in markdown
    assert "Source Row Action" in markdown
    assert "Source Command" in markdown
    assert "Required Receipts" in markdown
    assert "Source Phase 2 Criteria" in markdown
    assert "Source Phase 4 Criteria" in markdown
    assert "### Source Acquisition Next Actions" in markdown
    assert "review_official_source_receipt_plan" in markdown
    assert "refresh_public_benchmark_source_of_truth" in markdown
    assert "review_phase4_refinement_receipt_plan" in markdown
    assert "refresh_science_actual_closure_from_rows" in markdown
    assert "attach_vina_gnina_rows_then_run_phase2_row_audit" in markdown
    assert "vina_gnina_comparison_ready" in markdown
    assert "build_public_benchmark_vina_gnina_runtime_readiness.py" in markdown
    assert "engine_config_checksum" in markdown
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in markdown
    assert "uncertainty_summary_materialized" in markdown
    assert "uncertainty_interval_receipt" in markdown
    assert "### Vina/GNINA Input Manifest Action" in markdown
    assert "public_benchmark_vina_gnina_input_manifest.json" in markdown
    assert "public_benchmark_vina_gnina_input_manifest.csv" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_template_preflight" in markdown
    assert (
        "manifest:casf2016_4llx/"
        "complete_vina_gnina_input_manifest_row_for_casf2016_4llx/"
        "missing_files=4"
    ) in markdown
    assert "`recommended_template_dropzone_is_supported_candidate_path`: `True`" in markdown
    assert "`input_manifest_load_errors`: `none`" in markdown
    assert "materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py" in markdown
    assert "`source_archive_operator_artifact`: `<CASF-2016.tar.gz>`" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json" in markdown
    assert "`do_not_treat_blank_prepared_checksums_as_ready`: `True`" in markdown
    assert "### Vina/GNINA Adapter Row Preflight Action" in markdown
    assert "public_benchmark_vina_gnina_rows_template_preflight.json" in markdown
    assert "build_public_benchmark_vina_gnina_rows_template_preflight.py" in markdown
    assert "`role_receipt_blocked_count`: `72`" in markdown
    assert (
        "`first_blocked_role_receipt`: `engine_run_artifact_receipt` / "
        "`casf2016_4llx_vina_casf2016_4llx_vina_run`"
    ) in markdown
    assert "public_benchmark_vina_gnina_rows.csv" in markdown
    assert "`operator_rows_must_be_real_engine_outputs`: `True`" in markdown
    assert "### Public Benchmark Vina/GNINA Actual Evidence Audit" in markdown
    assert "`engine_input_manifest`" in markdown
    assert "`per_engine_run_receipts`" in markdown
    assert "`public_benchmark_vina_gnina_case_inputs_incomplete`" in markdown
    assert "`public_benchmark_vina_gnina_engine_run_receipts_incomplete`" in (
        markdown
    )
    assert "### Public Benchmark Source Access Preflight" in markdown
    assert "`receipt_status`: `reachable`" in markdown
    assert "`receipt_reachable_count`: `6`" in markdown
    assert "`external_receipts_status`: `operator_receipts_required`" in markdown
    assert "`external_receipts_complete_roles`: `2/3`" in markdown
    assert "curl --head --location --max-time 20" in markdown
    assert "### PocketMD Top-k Rows Action" in markdown
    assert "materialize_rows_from_template_command" in markdown
    assert "materialize_rows_from_receipt_bundle_command" in markdown
    assert "materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py" in markdown
    assert "### PocketMD Actual Evidence Audit" in markdown
    assert "| Family | Status | Missing Items | Blocked Cases | Operator Action | Command Key |" in markdown
    assert "`operator_blocker_family_count`" in markdown
    assert "`bounded_top_k_row_slots`" in markdown
    assert "`materialize_rows_from_receipt_bundle`" in markdown
    assert "`survival_metric_summary`" in markdown
    assert "`pocketmd_lite_operator_input_source_receipt_incomplete`" in markdown
    assert "`role_receipt_blocked_count`: `24`" in markdown
    assert (
        "`first_blocked_role_receipt`: "
        "`upstream_top_k_candidate_scope_receipt` / "
        "`pocketmd_lite_case_001_rank_01`"
    ) in markdown
    assert "`operator_input_source_receipt_blocked_count`: `5`" in markdown
    assert "`first_blocked_operator_input_source_receipt`: `source_id`" in markdown
    assert "`phase4_metric_receipt_action_count`: `8`" in markdown
    assert "`receipt_metric_family_blocked_count`: `5`" in markdown
    assert "`first_receipt_metric_family_blocker`: `local_min_survival` / `6`" in (
        markdown
    )
    assert "#### PocketMD Phase 4 Receipt Closure Actions" in markdown
    assert "interaction_persistence_receipt" in markdown
    assert "### PocketMD Phase 4 Completion Audit" in markdown
    assert "`requirements_ready`: `2/9`" in markdown
    assert "`blocked_requirement_count`: `7`" in markdown
    assert "`remaining_row_inputs`: `pocketmd_rows`" in markdown
    assert "`top_k_refinement_case_coverage` | `blocked`" in markdown
    assert "`local_min_survival_reported` | `blocked`" in markdown
    assert "### PocketMD Row Preflight Action" in markdown
    assert "`template_preflight_role_receipt_blocked_count`: `24`" in markdown
    assert (
        "`template_preflight_operator_input_source_receipt_blocked_count`: `5`"
        in markdown
    )
    assert "pocketmd_lite_topk_rows.tsv" in markdown
    assert "`operator_rows_must_be_real_top_k_refinement_outputs`: `True`" in markdown
    assert "operator_input_source.source_artifact_sha256" in markdown
    assert "`placeholder_or_fixture_rows_do_not_promote`: `True`" in markdown
    assert "attach_pocketmd_rows_at_" in markdown
    assert "CSV Starter" in markdown
    assert "## Upstream Source Blockers" in markdown
    assert "public_benchmark_vina_gnina_engine_runtime_not_ready" in markdown
    assert (
        "public_benchmark_vina_gnina_engine_binaries_or_container_images_missing"
        in markdown
    )
    assert "public_benchmark_vina_gnina_input_manifest_not_detected" not in markdown
    assert "### Vina/GNINA Engine Run Slots" in markdown
    assert "`operator_unblock_status`: `engine_inputs_required`" in markdown
    assert "`missing_engine_ids`: `vina`, `gnina`" in markdown
    assert "`runtime_readiness_blocker_count`: `124`" in markdown
    assert "`adapter_row_preflight_status`: `row_artifact_missing`" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_template.csv" in markdown
    assert "PUBLIC_BENCHMARK_VINA_BIN" in markdown
    assert "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE" in markdown
    assert "configure_gnina_runtime" in markdown
    assert "casf2016_4llx_vina_casf2016_4llx_vina_run" in markdown
    assert "configure_vina_runtime" in markdown
    assert "## Provided Closure Evidence" in markdown
    assert "### GPCR Phase 3 Gate" in markdown
    assert "| `DRD2` | `1.0` | `0.6` | `0` | `False` | `pass` |" in markdown
    assert "pocketmd_lite_topk_rows_not_acquired" in markdown
    assert "### PocketMD Top-k Candidate Slots" in markdown
    assert "`operator_unblock_status`: `operator_refinement_rows_required`" in markdown
    assert "pocketmd_lite_topk_rows_template_preflight.json" in markdown
    assert "build_pocketmd_lite_topk_rows_template_preflight.py" in markdown
    assert "`survival_report_status`: `operator_evidence_required`" in markdown
    assert "`survival_report_first_blocked_target`: `top_k_refinement_operator_intake`" in markdown
    assert "`survival_report_blocker_count`: `6`" in markdown
    assert "pocketmd_lite_uncertainty_rows_missing" in markdown
    assert "`row_template_preflight_status`: `operator_rows_completion_required`" in markdown
    assert "`row_template_preflight_ready`: `False`" in markdown
    assert "pocketmd_lite_case_001_rank_01" in markdown
    assert "attach_pocketmd_topk_row_for_pocketmd_lite_case_001_rank_01" in markdown
    assert "public_benchmark_subset_rows_template.csv" in markdown
    assert "gpcr_hard_decoy_rows_template.csv" in markdown
    assert "pocketmd_lite_topk_rows_template.csv" in markdown
    assert (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    ) in markdown
    assert "--source-license <license>" in markdown
    assert "materialize_science_actual_closure_from_rows.py --fail-blocked" in markdown
