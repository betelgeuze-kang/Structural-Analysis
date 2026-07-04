from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_public_benchmark_phase2_source_acquisition_plan.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_phase2_source_acquisition_plan",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_public_benchmark_phase2_source_plan_exposes_required_row_contracts() -> None:
    payload = module.build_public_benchmark_phase2_source_acquisition_plan(
        repo_root=REPO_ROOT,
    )
    row_contracts = {row["row_input_id"]: row for row in payload["row_input_contracts"]}
    receipt_plan = payload["official_source_receipt_plan"]
    receipt_roles = {
        row["row_input_id"]: row for row in receipt_plan["row_input_receipt_roles"]
    }
    source_catalog = {
        row["source_id"]: row for row in receipt_plan["official_source_catalog"]
    }

    assert payload["schema_version"] == (
        "public-benchmark-phase2-source-acquisition-plan.v1"
    )
    assert payload["status"] == "operator_acquisition_required"
    assert payload["contract_pass"] is True
    assert payload["phase2_ready"] is False
    assert payload["actual_closure_ready"] is False
    assert payload["required_components"] == [
        "casf_pdbbind_pose_success_harness",
        "symmetry_aware_ligand_rmsd",
        "posebusters_style_pose_validity",
        "vina_gnina_comparison_adapter",
        "dud_e_or_lit_pcba_enrichment",
    ]
    assert payload["required_row_inputs"] == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
    ]
    assert set(row_contracts) == set(payload["required_row_inputs"])
    assert payload["receipt_promotion_policy"] == {
        "external_source_receipts_required": True,
        "license_or_accession_reference_required": True,
        "operator_attached_rows_required": True,
        "per_source_bundle_checksum_required": True,
        "redistribution_of_restricted_benchmark_payloads": False,
        "summary_only_metrics_promote_to_phase2": False,
        "synthetic_fixture_rows_promote_to_phase2": False,
    }
    assert receipt_plan["plan_id"] == (
        "public_benchmark_phase2_official_source_receipt_plan"
    )
    assert receipt_plan["status"] == "operator_receipts_required"
    assert receipt_plan["receipt_role_count"] == 4
    assert receipt_plan["source_catalog_count"] == 6
    assert receipt_plan["source_access_preflight_count"] == 6
    assert receipt_plan["row_input_count"] == 4
    assert receipt_plan["source_access_preflight_policy"] == {
        "license_or_accession_review_required_before_payload_use": True,
        "network_probe_only": True,
        "raw_payload_committed_by_plan": False,
        "raw_payload_downloaded_by_plan": False,
        "source_checksum_required_after_operator_acquisition": True,
    }
    assert receipt_plan["source_access_preflight_receipt_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.json"
    )
    assert receipt_plan["source_access_preflight_receipt_markdown_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.md"
    )
    assert receipt_plan["source_access_preflight_receipt_command"] == (
        "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
        "--out implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.json "
        "--out-md implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.md"
    )
    assert receipt_plan["source_access_network_probe_command"].endswith(
        "--probe-network"
    )
    source_access_receipt = payload["source_access_preflight_receipt"]
    assert source_access_receipt["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.json"
    )
    assert source_access_receipt["markdown_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.md"
    )
    assert source_access_receipt["present"] is True
    assert source_access_receipt["status"] == "reachable"
    assert source_access_receipt["contract_pass"] is True
    assert source_access_receipt["network_probe_performed"] is True
    assert source_access_receipt["source_access_ready"] is True
    assert source_access_receipt["source_access_probe_row_count"] == 6
    assert source_access_receipt["reachable_count"] == 6
    assert source_access_receipt["blocked_count"] == 0
    assert source_access_receipt["not_run_count"] == 0
    assert source_access_receipt["blocked_source_ids"] == []
    source_access_rows = {
        row["source_id"]: row for row in source_access_receipt["row_statuses"]
    }
    assert set(source_access_rows) == {
        "autodock_vina",
        "dud_e",
        "gnina",
        "lit_pcba",
        "pdbbind_plus_casf",
        "posebusters",
    }
    assert source_access_rows["pdbbind_plus_casf"]["status"] == (
        "primary_reachable"
    )
    assert source_access_rows["gnina"]["source_family"] == "GNINA"
    assert source_access_rows["autodock_vina"]["primary_http_status"] == 200
    assert source_access_rows["posebusters"]["blockers"] == []
    external_validation = payload["external_receipts_validation"]
    assert external_validation["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_external_receipts_validation.json"
    )
    assert external_validation["present"] is True
    assert external_validation["computed_from_materialized_artifacts"] is True
    assert external_validation["persisted_artifact_status"] == (
        "operator_receipts_required"
    )
    assert external_validation["persisted_artifact_materialized_row_count"] == 0
    assert external_validation["materialized_artifact_inputs"] == [
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_manifest.json",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_enrichment_scorecard.json",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_comparison_adapter.json",
    ]
    assert external_validation["status"] == "operator_receipts_required"
    assert external_validation["public_benchmark_external_receipts_ready"] is False
    assert external_validation["materialized_row_count"] == 13
    assert external_validation["receipt_complete_row_count"] == 13
    assert external_validation["expected_artifact_role_count"] == 3
    assert external_validation["receipt_complete_artifact_role_count"] == 2
    assert external_validation["missing_expected_artifact_roles"] == [
        "vina_gnina_comparison_adapter"
    ]
    assert external_validation["blockers"] == [
        "public_benchmark_external_receipt_role_missing:"
        "vina_gnina_comparison_adapter"
    ]
    external_audit = payload["external_receipt_completion_audit"]
    assert external_audit["status"] == "blocked_pending_vina_gnina_receipts"
    assert external_audit["pass"] is False
    assert external_audit["source_access_ready"] is True
    assert external_audit["source_access_reachable_count"] == 6
    assert external_audit["external_receipts_validation_status"] == (
        "operator_receipts_required"
    )
    assert external_audit["all_expected_artifact_roles_complete"] is False
    assert external_audit["receipt_complete_artifact_role_count"] == 2
    assert external_audit["expected_artifact_role_count"] == 3
    assert external_audit["ready_official_receipt_role_count"] == 3
    assert external_audit["blocked_official_receipt_role_count"] == 1
    assert external_audit["blocked_receipt_role_ids"] == [
        "vina_gnina_engine_comparison_receipt"
    ]
    assert external_audit["remaining_row_inputs"] == ["vina_gnina_rows"]
    assert external_audit["operator_action"] == (
        "attach_vina_gnina_rows_and_receipts_then_refresh_external_receipts"
    )
    external_roles = {
        row["row_input_id"]: row for row in external_audit["receipt_roles"]
    }
    assert set(external_roles) == set(payload["required_row_inputs"])
    assert external_roles["subset_rows"]["status"] == "ready"
    assert external_roles["pose_rows"]["row_source_actuality_ready"] is True
    assert external_roles["enrichment_rows"]["artifact_receipts_complete"] is True
    assert external_roles["vina_gnina_rows"]["status"] == (
        "operator_receipt_required"
    )
    assert external_roles["vina_gnina_rows"]["source_access_ready"] is True
    assert external_roles["vina_gnina_rows"]["source_ids"] == [
        "pdbbind_plus_casf",
        "autodock_vina",
        "gnina",
    ]
    assert external_roles["vina_gnina_rows"]["blockers"] == [
        "vina_gnina_rows_not_provided",
        "public_benchmark_external_receipt_role_missing:"
        "vina_gnina_comparison_adapter",
    ]
    assert receipt_plan["operator_review_order"] == [
        "casf_pdbbind_subset_source_receipt",
        "casf_pdbbind_pose_coordinate_receipt",
        "dud_e_or_lit_pcba_enrichment_receipt",
        "vina_gnina_engine_comparison_receipt",
    ]
    assert receipt_plan["source_review_order"] == [
        "pdbbind_plus_casf",
        "dud_e",
        "lit_pcba",
        "autodock_vina",
        "gnina",
        "posebusters",
    ]
    assert set(source_catalog) == set(receipt_plan["source_review_order"])
    source_access_preflight = {
        row["source_id"]: row for row in receipt_plan["source_access_preflight_rows"]
    }
    assert source_access_preflight["pdbbind_plus_casf"][
        "primary_head_command"
    ] == "curl --head --location --max-time 20 'https://www.pdbbind-plus.org.cn/casf'"
    assert source_access_preflight["pdbbind_plus_casf"][
        "source_payload_policy"
    ]["raw_payload_downloaded_by_plan"] is False
    assert "license_or_accession_review_recorded_before_payload_use" in (
        source_access_preflight["pdbbind_plus_casf"]["operator_success_criteria"]
    )
    assert source_catalog["pdbbind_plus_casf"]["primary_url"] == (
        "https://www.pdbbind-plus.org.cn/casf"
    )
    assert source_catalog["pdbbind_plus_casf"]["feeds_row_inputs"] == [
        "subset_rows",
        "pose_rows",
        "vina_gnina_rows",
    ]
    assert source_catalog["dud_e"]["primary_url"] == (
        "https://dude.docking.org/targets/"
    )
    assert source_catalog["dud_e"]["feeds_row_inputs"] == ["enrichment_rows"]
    assert source_catalog["lit_pcba"]["primary_url"] == (
        "https://drugdesign.unistra.fr/LIT-PCBA/"
    )
    assert source_catalog["autodock_vina"]["feeds_row_inputs"] == [
        "vina_gnina_rows"
    ]
    assert source_catalog["gnina"]["primary_url"] == "https://github.com/gnina/gnina"
    assert source_catalog["posebusters"]["feeds_components"] == [
        "posebusters_style_pose_validity"
    ]
    assert set(receipt_roles) == set(payload["required_row_inputs"])
    assert receipt_roles["subset_rows"]["receipt_role_id"] == (
        "casf_pdbbind_subset_source_receipt"
    )
    assert receipt_roles["subset_rows"]["required_local_checksum_fields"] == [
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
    ]
    assert "source bundle checksum" in receipt_roles["subset_rows"][
        "operator_must_attach"
    ]
    assert receipt_roles["pose_rows"]["receipt_role_id"] == (
        "casf_pdbbind_pose_coordinate_receipt"
    )
    assert "pose_preparation_provenance_ref" in receipt_roles["pose_rows"][
        "required_receipt_fields"
    ]
    assert receipt_roles["enrichment_rows"]["supported_families"] == [
        "DUD-E",
        "LIT-PCBA",
    ]
    assert receipt_roles["vina_gnina_rows"]["required_engines"] == [
        "vina",
        "gnina",
    ]
    assert "engine_config_checksum" in receipt_roles["vina_gnina_rows"][
        "required_receipt_fields"
    ]
    assert payload["phase2_row_audit"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_phase2_row_audit.json"
    )
    assert payload["phase2_row_audit"]["status"] == "operator_evidence_required"
    assert payload["phase2_row_audit"]["phase2_ready"] is False
    assert payload["phase2_row_audit"]["missing_row_input_count"] == 1
    assert payload["phase2_row_audit"]["missing_row_inputs"] == [
        "vina_gnina_rows",
    ]
    assert payload["phase2_row_audit"]["component_ready_count"] == 4
    assert payload["phase2_row_audit"]["phase2_failed_criteria"] == [
        "vina_gnina_comparison_ready",
    ]
    assert payload["phase2_row_audit"]["phase2_completion_audit_status"] == (
        "blocked"
    )
    assert payload["phase2_row_audit"]["phase2_completion_requirement_count"] == 6
    assert (
        payload["phase2_row_audit"]["phase2_completion_requirement_pass_count"]
        == 4
    )
    assert payload["phase2_row_audit"]["phase2_completion_blocker_count"] == 2
    assert payload["phase2_exit_criterion_count"] == 5
    exit_criteria = {
        row["criterion_id"]: row for row in payload["phase2_exit_criteria"]
    }
    assert exit_criteria["casf_pdbbind_pose_success_harness_ready"]["pass"] is True
    assert exit_criteria["symmetry_aware_ligand_rmsd_ready"]["pass"] is True
    assert exit_criteria["posebusters_style_pose_validity_ready"]["pass"] is True
    assert exit_criteria["dud_e_or_lit_pcba_enrichment_ready"]["pass"] is True
    assert exit_criteria["vina_gnina_comparison_ready"]["pass"] is False
    assert exit_criteria["vina_gnina_comparison_ready"]["blockers"] == [
        "vina_gnina_rows_not_provided"
    ]
    harness_audit = payload["phase2_harness_completion_audit"]
    assert harness_audit["status"] == "ready_except_vina_gnina_actual_rows"
    assert harness_audit["pass"] is True
    assert harness_audit["phase2_ready"] is False
    assert harness_audit[
        "harness_contract_complete_except_vina_gnina_actual_rows"
    ] is True
    assert harness_audit["requirement_count"] == 5
    assert harness_audit["ready_requirement_count"] == 4
    assert harness_audit["blocked_requirement_count"] == 1
    assert harness_audit["blocked_requirement_ids"] == [
        "vina_gnina_comparison_adapter"
    ]
    assert harness_audit["remaining_row_inputs"] == ["vina_gnina_rows"]
    assert harness_audit["remaining_blockers"] == [
        "vina_gnina_rows_not_provided"
    ]
    assert harness_audit["remaining_operator_action"] == (
        "attach_vina_gnina_rows_then_run_phase2_row_audit"
    )
    assert harness_audit["vina_gnina_runtime_status"] == "ready_for_engine_execution"
    assert harness_audit["vina_gnina_input_manifest_status"] == "ready"
    assert harness_audit["vina_gnina_runtime_missing_engine_ids"] == []
    harness_requirements = {
        row["requirement_id"]: row for row in harness_audit["requirements"]
    }
    assert list(harness_requirements) == [
        "casf_pdbbind_pose_success_harness",
        "symmetry_aware_ligand_rmsd",
        "posebusters_style_pose_validity_checks",
        "vina_gnina_comparison_adapter",
        "dud_e_or_lit_pcba_enrichment",
    ]
    assert harness_requirements["casf_pdbbind_pose_success_harness"][
        "product_requirement"
    ] == "CASF/PDBBind pose-success harness"
    assert harness_requirements["casf_pdbbind_pose_success_harness"][
        "row_input_status"
    ] == {"pose_rows": "provided", "subset_rows": "provided"}
    assert harness_requirements["posebusters_style_pose_validity_checks"][
        "status"
    ] == "ready"
    assert harness_requirements["vina_gnina_comparison_adapter"]["status"] == (
        "blocked_pending_actual_vina_gnina_rows"
    )
    assert harness_requirements["vina_gnina_comparison_adapter"][
        "row_input_status"
    ] == {"vina_gnina_rows": "missing"}
    assert harness_requirements["vina_gnina_comparison_adapter"]["blockers"] == [
        "vina_gnina_rows_not_provided"
    ]
    source_extraction = payload["vina_gnina_source_extraction"]
    assert source_extraction["status"] == (
        "source_files_verified_prepared_inputs_required"
    )
    assert source_extraction["source_files_ready"] is True
    assert source_extraction["source_ready_case_count"] == 12
    assert source_extraction["source_file_count"] == 24
    assert source_extraction["verified_source_file_count"] == 24
    assert source_extraction["blocked_source_file_count"] == 0
    assert source_extraction["prepared_input_gap_count"] == 24
    assert payload["summary"]["vina_gnina_source_files_ready"] is True
    assert payload["summary"]["vina_gnina_source_ready_case_count"] == 12
    assert payload["summary"]["vina_gnina_source_file_count"] == 24
    assert payload["summary"]["vina_gnina_verified_source_file_count"] == 24
    assert payload["summary"]["vina_gnina_blocked_source_file_count"] == 0
    assert payload["summary"]["vina_gnina_prepared_input_gap_count"] == 0
    vina_gnina_actual_audit = payload["vina_gnina_actual_evidence_audit"]
    assert vina_gnina_actual_audit["status"] == "adapter_rows_required"
    assert vina_gnina_actual_audit["pass"] is False
    assert vina_gnina_actual_audit["actual_closure_ready"] is False
    assert vina_gnina_actual_audit["component_count"] == 6
    assert vina_gnina_actual_audit["ready_component_count"] == 3
    assert vina_gnina_actual_audit["blocked_component_count"] == 3
    assert vina_gnina_actual_audit["blocked_component_ids"] == [
        "adapter_rows",
        "per_engine_run_receipts",
        "external_receipts",
    ]
    assert vina_gnina_actual_audit["required_case_count"] == 12
    assert vina_gnina_actual_audit["required_engine_run_count"] == 24
    assert vina_gnina_actual_audit["operator_blocker_family_count"] == 7
    assert vina_gnina_actual_audit["operator_blocker_family_blocked_count"] == 1
    assert (
        vina_gnina_actual_audit["operator_blocker_family_missing_item_count"]
        == 12
    )
    assert vina_gnina_actual_audit["first_operator_blocker_family"][
        "family_id"
    ] == "adapter_rows"
    family_plan = {
        row["family_id"]: row
        for row in vina_gnina_actual_audit["operator_blocker_family_plan"]
    }
    assert family_plan["manifest_required_values"]["next_action"] == (
        "review_verified_vina_gnina_input_manifest"
    )
    assert family_plan["manifest_required_values"]["command_key"] == (
        "build_input_manifest_template_preflight"
    )
    assert (
        "build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"
        in family_plan["manifest_required_values"]["materialization_command"]
    )
    assert family_plan["official_source_files"]["status"] == "ready"
    assert family_plan["official_source_files"]["missing_item_count"] == 0
    assert family_plan["official_source_files"]["blocked_case_count"] == 0
    assert family_plan["official_source_files"]["first_missing_item"] == {}
    assert family_plan["official_source_files"]["next_action"] == (
        "review_verified_casf_source_file_receipt"
    )
    assert family_plan["official_source_files"]["source_extraction_summary"] == {
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json"
        ),
        "status": "source_files_verified_prepared_inputs_required",
        "source_ready_case_count": 12,
        "source_file_count": 24,
        "verified_source_file_count": 24,
        "blocked_source_file_count": 0,
    }
    assert (
        "materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py"
        in family_plan["official_source_files"]["materialization_command"]
    )
    assert family_plan["prepared_input_files"]["missing_item_count"] == 0
    assert family_plan["input_and_engine_receipt_refs"]["missing_item_count"] == 0
    assert family_plan["engine_runtime"]["missing_item_count"] == 0
    assert (
        "build_public_benchmark_vina_gnina_runtime_readiness.py"
        in family_plan["engine_runtime"]["materialization_command"]
    )
    assert family_plan["engine_run_slots"]["missing_item_count"] == 0
    assert family_plan["adapter_rows"]["missing_item_count"] == 12
    assert (
        "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
        in family_plan["adapter_rows"]["materialization_command"]
    )
    actual_components = {
        row["component_id"]: row
        for row in vina_gnina_actual_audit["components"]
    }
    assert actual_components["engine_input_manifest"]["current"] == {
        "blocked_case_input_slot_count": 0,
        "blocked_source_file_count": 0,
        "case_input_slot_count": 12,
        "input_manifest_detected": True,
        "input_manifest_row_count": 12,
        "input_manifest_syntax_ready": True,
        "input_manifest_status": "ready",
        "input_manifest_verification_status": "case_inputs_verified",
        "prepared_input_gap_count": 0,
        "prepared_input_ready_case_count": 12,
        "required_case_count": 12,
        "source_extraction_status": "source_files_verified_prepared_inputs_required",
        "source_file_count": 24,
        "source_files_ready": True,
        "source_ready_case_count": 12,
        "template_completion_blocked_case_count": 0,
        "template_manifest_ready": True,
        "template_missing_local_file_count": 0,
        "template_missing_receipt_ref_count": 0,
        "template_preflight_status": "operator_manifest_complete",
        "verified_case_input_count": 12,
        "verified_source_file_count": 24,
    }
    assert actual_components["engine_input_manifest"]["required"] == {
        "blocked_case_input_slot_count": 0,
        "input_manifest_detected": True,
        "input_manifest_row_count": ">=12",
        "input_manifest_syntax_ready": True,
        "template_manifest_ready": True,
        "verified_case_input_count": ">=12",
    }
    assert actual_components["engine_input_manifest"]["blockers"] == []
    assert actual_components["engine_runtime"]["blockers"] == []
    assert actual_components["adapter_rows"]["blockers"] == [
        "public_benchmark_vina_gnina_rows_not_detected",
        "vina_gnina_rows_not_provided",
    ]
    assert actual_components["per_engine_run_receipts"]["current"][
        "role_receipt_blocked_count"
    ] == 72
    assert actual_components["external_receipts"]["current"][
        "missing_expected_artifact_roles"
    ] == ["vina_gnina_comparison_adapter"]
    assert payload["phase2_row_closure_matrix_count"] == 4
    closure_matrix = {
        row["row_input_id"]: row for row in payload["phase2_row_closure_matrix"]
    }
    assert closure_matrix["subset_rows"]["closes_phase2_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready"
    ]
    assert closure_matrix["pose_rows"]["closes_phase2_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready",
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    ]
    assert closure_matrix["enrichment_rows"]["closes_phase2_criteria"] == [
        "dud_e_or_lit_pcba_enrichment_ready"
    ]
    assert closure_matrix["vina_gnina_rows"]["status"] == "missing"
    assert closure_matrix["vina_gnina_rows"]["closes_phase2_criteria"] == [
        "vina_gnina_comparison_ready"
    ]
    assert closure_matrix["vina_gnina_rows"]["required_by_components"] == [
        {
            "artifact_role": "vina_gnina_comparison_adapter",
            "component_id": "vina_gnina_comparison_adapter",
            "count_field": "real_comparison_case_count",
            "criterion_id": "vina_gnina_comparison_ready",
            "ready_field": "public_benchmark_engine_comparison_ready",
            "required_minimum_count": 1,
        }
    ]
    assert payload["phase2_row_audit"]["source_actuality_scope"] == (
        "provided_row_inputs_only"
    )
    assert payload["phase2_row_audit"]["source_actuality_contract_pass"] is True
    assert payload["phase2_row_audit"]["source_actuality_scope_complete"] is False
    assert payload["phase2_row_audit"]["source_actuality_blocker_count"] == 0
    assert payload["phase2_row_audit"]["source_actuality_provided_row_inputs"] == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
    ]
    assert payload["phase2_row_audit"]["source_actuality_missing_row_inputs"] == [
        "vina_gnina_rows",
    ]
    assert payload["vina_gnina_execution_plan"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_execution_plan.json"
    )
    assert payload["vina_gnina_execution_plan"]["status"] == (
        "ready_for_engine_execution"
    )
    assert payload["vina_gnina_execution_plan"]["execution_plan_ready"] is True
    assert payload["vina_gnina_execution_plan"]["operator_execution_ready"] is True
    assert payload["vina_gnina_execution_plan"]["adapter_rows_ready"] is False
    assert payload["vina_gnina_execution_plan"]["case_count"] == 12
    assert payload["vina_gnina_execution_plan"]["required_engine_run_count"] == 24
    assert payload["vina_gnina_execution_plan"]["missing_engine_ids"] == []
    assert payload["vina_gnina_execution_plan"]["input_manifest_status"] == "ready"
    assert payload["vina_gnina_execution_plan"]["input_manifest_detected"] is True
    assert payload["vina_gnina_execution_plan"]["input_manifest_row_count"] == 12
    assert payload["vina_gnina_execution_plan"]["input_manifest_blockers"] == []
    assert payload["vina_gnina_execution_plan"]["engine_input_manifest_template"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert payload["vina_gnina_execution_plan"]["required_engine_input_fields"] == [
        "case_id",
        "complex_id",
        "protein_structure_path",
        "protein_structure_checksum",
        "reference_ligand_path",
        "reference_ligand_checksum",
        "prepared_receptor_path",
        "prepared_receptor_checksum",
        "prepared_ligand_path",
        "prepared_ligand_checksum",
    ]
    assert payload["vina_gnina_runtime_readiness"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_runtime_readiness.json"
    )
    assert payload["vina_gnina_runtime_readiness"]["status"] == (
        "ready_for_engine_execution"
    )
    assert payload["vina_gnina_runtime_readiness"][
        "runtime_ready_for_engine_execution"
    ] is True
    assert payload["vina_gnina_runtime_readiness"][
        "ready_engine_run_slot_count"
    ] == 24
    assert payload["vina_gnina_runtime_readiness"]["available_engine_count"] == 2
    assert payload["vina_gnina_runtime_readiness"]["missing_engine_count"] == 0
    assert payload["vina_gnina_runtime_readiness"][
        "detected_row_artifact_count"
    ] == 0
    assert payload["vina_gnina_runtime_readiness"][
        "case_input_slot_matrix_count"
    ] == 12
    assert payload["vina_gnina_runtime_readiness"][
        "blocked_case_input_slot_count"
    ] == 0
    assert payload["vina_gnina_runtime_readiness"][
        "engine_run_slot_matrix_count"
    ] == 24
    assert payload["vina_gnina_runtime_readiness"][
        "blocked_engine_run_slot_count"
    ] == 0
    case_slots = {
        row["case_id"]: row
        for row in payload["vina_gnina_runtime_readiness"][
            "case_input_slot_matrix"
        ]
    }
    first_case_slot = case_slots["casf2016_4llx"]
    assert first_case_slot["slot_id"] == "casf2016_4llx_case_inputs"
    assert first_case_slot["status"] == "ready"
    assert "prepared_receptor_path" in first_case_slot[
        "required_engine_input_fields"
    ]
    first_engine_slot = payload["vina_gnina_runtime_readiness"][
        "engine_run_slot_matrix"
    ][0]
    assert first_engine_slot["slot_id"] == "casf2016_4llx_vina"
    assert first_engine_slot["engine_id"] == "vina"
    assert first_engine_slot["blockers"] == []
    assert first_engine_slot["operator_actions"] == [
        "resolve_vina_gnina_case_inputs_for_casf2016_4llx",
        "configure_vina_runtime",
        "attach_vina_gnina_adapter_row_for_casf2016_4llx_vina",
    ]
    assert payload["vina_gnina_runtime_readiness"]["missing_engine_ids"] == []
    runtime_unblock = payload["vina_gnina_runtime_readiness"][
        "operator_unblock_packet"
    ]
    assert runtime_unblock["status"] == "engine_run_rows_required"
    assert runtime_unblock["input_manifest_template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert runtime_unblock["input_manifest_template_preflight_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
    )
    assert runtime_unblock["commands"][
        "build_input_manifest_template_preflight"
    ].endswith("public_benchmark_vina_gnina_input_manifest_template_preflight.md")
    assert runtime_unblock["operator_sequence"][0] == (
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight"
    )
    assert runtime_unblock["blocked_case_input_slot_count"] == 0
    assert runtime_unblock["blocked_engine_run_slot_count"] == 0
    assert runtime_unblock["adapter_row_preflight_status"] == "row_artifact_missing"
    assert payload["vina_gnina_runtime_readiness"]["container_runtime_status"][
        "available"
    ] is True
    container_statuses = {
        row["engine_id"]: row
        for row in payload["vina_gnina_runtime_readiness"][
            "engine_container_statuses"
        ]
    }
    assert set(container_statuses) == {"vina", "gnina"}
    assert container_statuses["vina"]["status"] == "container_image_not_configured"
    assert container_statuses["vina"]["docker_daemon_available"] is True
    assert container_statuses["vina"]["image_env_var"] == (
        "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE"
    )
    assert container_statuses["gnina"]["status"] == "ready"
    assert container_statuses["gnina"]["image"] == "dkoes/gnina:latest"
    assert container_statuses["gnina"]["image_env_var"] == (
        "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE"
    )

    subset = row_contracts["subset_rows"]
    assert subset["source_family"] == "CASF/PDBBind"
    assert subset["minimum_rows_required"] == 12
    assert subset["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert subset["local_source_file_fields"] == [
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
    ]
    assert "ligand_atom_order_contract.atom_ids" in subset["required_fields"]
    assert "symmetry_permutation_contract.permutations" in subset["required_fields"]

    pose = row_contracts["pose_rows"]
    assert pose["minimum_rows_required"] == 12
    assert pose["depends_on_row_inputs"] == ["subset_rows"]
    assert pose["receipt_fields"] == [
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
        "pose_preparation_provenance_ref",
    ]
    assert pose["pose_success_metric"] == "symmetry_aware_ligand_rmsd_angstrom"
    assert pose["posebusters_style_check_contract"]["required_check_ids"] == [
        "coordinate_finiteness",
        "atom_count_and_order_contract",
        "pose_success_metric_contract",
        "symmetry_permutation_contract",
        "minimum_interatomic_distance_guard",
        "receptor_ligand_context_present",
        "symmetry_aware_ligand_rmsd_angstrom",
    ]
    assert pose["symmetry_rmsd_contract"] == {
        "requires_ligand_atom_order_contract": True,
        "requires_symmetry_permutation_contract": True,
        "success_threshold_angstrom": 2.0,
    }

    enrichment = row_contracts["enrichment_rows"]
    assert enrichment["source_family"] == "DUD-E/LIT-PCBA"
    assert enrichment["minimum_target_count_required"] == 1
    assert enrichment["supported_families"] == ["DUD-E", "LIT-PCBA"]
    assert enrichment["required_molecule_fields"] == [
        "molecule_id",
        "is_active",
        "score",
    ]
    assert enrichment["row_validation_policies"]["active_decoy_policy"] == (
        module.ACTIVE_DECOY_POLICY
    )

    vina_gnina = row_contracts["vina_gnina_rows"]
    assert vina_gnina["minimum_comparison_case_count_required"] == 1
    assert vina_gnina["depends_on_row_inputs"] == ["subset_rows", "pose_rows"]
    assert vina_gnina["engine_input_manifest_template"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert "prepared_receptor_checksum" in vina_gnina[
        "required_engine_input_fields"
    ]
    assert vina_gnina["required_engines"] == ["vina", "gnina"]
    assert vina_gnina["row_validation_policies"]["engine_pair_policy"] == (
        module.ENGINE_PAIR_POLICY
    )

    assert payload["summary"] == {
        "actual_closure_ready": False,
        "blocker_count": 2,
        "minimum_enrichment_target_count": 1,
        "minimum_subset_case_count": 12,
        "minimum_vina_gnina_comparison_case_count": 1,
        "official_source_receipt_plan_status": "operator_receipts_required",
        "official_source_receipt_role_count": 4,
        "official_source_catalog_count": 6,
        "official_source_access_preflight_count": 6,
        "source_access_preflight_receipt_status": "reachable",
        "source_access_preflight_receipt_ready": True,
        "source_access_preflight_reachable_count": 6,
        "source_access_preflight_blocked_count": 0,
        "source_access_preflight_network_probe_performed": True,
        "external_receipts_validation_status": "operator_receipts_required",
        "external_receipts_ready_for_materialized_rows": False,
        "external_receipts_expected_artifact_role_count": 3,
        "external_receipts_complete_artifact_role_count": 2,
        "external_receipts_missing_expected_artifact_roles": [
            "vina_gnina_comparison_adapter",
        ],
        "external_receipt_completion_audit_status": (
            "blocked_pending_vina_gnina_receipts"
        ),
        "external_receipt_ready_official_role_count": 3,
        "external_receipt_blocked_official_role_count": 1,
        "external_receipt_all_expected_artifact_roles_complete": False,
        "phase2_exit_criterion_count": 5,
        "phase2_passing_exit_criterion_count": 4,
        "phase2_blocked_exit_criterion_count": 1,
        "phase2_harness_completion_audit_status": (
            "ready_except_vina_gnina_actual_rows"
        ),
        "phase2_harness_requirement_count": 5,
        "phase2_harness_ready_requirement_count": 4,
        "phase2_harness_blocked_requirement_count": 1,
        "phase2_harness_complete_except_vina_gnina_actual_rows": True,
        "phase2_row_closure_matrix_count": 4,
        "phase2_row_audit_blocker_count": 1,
        "phase2_row_audit_failed_criteria": [
            "vina_gnina_comparison_ready",
        ],
        "phase2_row_audit_source_actuality_scope": "provided_row_inputs_only",
        "phase2_row_audit_source_actuality_contract_pass": True,
        "phase2_row_audit_source_actuality_scope_complete": False,
        "phase2_row_audit_source_actuality_blocker_count": 0,
        "missing_row_input_action_count": 1,
        "vina_gnina_actual_evidence_audit_status": "adapter_rows_required",
        "vina_gnina_actual_evidence_ready_component_count": 3,
        "vina_gnina_actual_evidence_blocked_component_count": 3,
        "vina_gnina_actual_evidence_required_engine_run_count": 24,
        "vina_gnina_actual_operator_blocker_family_count": 7,
        "vina_gnina_actual_operator_blocker_family_blocked_count": 1,
        "vina_gnina_actual_operator_blocker_family_missing_item_count": 12,
        "vina_gnina_source_extraction_status": (
            "source_files_verified_prepared_inputs_required"
        ),
        "vina_gnina_source_files_ready": True,
        "vina_gnina_source_ready_case_count": 12,
        "vina_gnina_source_file_count": 24,
        "vina_gnina_verified_source_file_count": 24,
        "vina_gnina_blocked_source_file_count": 0,
        "vina_gnina_prepared_input_gap_count": 0,
        "vina_gnina_prepared_input_ready_case_count": 12,
        "phase2_row_audit_missing_row_input_count": 1,
        "phase2_row_audit_missing_row_inputs": [
            "vina_gnina_rows",
        ],
        "phase2_row_audit_status": "operator_evidence_required",
        "phase2_row_audit_completion_audit_status": "blocked",
        "phase2_row_audit_completion_requirement_count": 6,
        "phase2_row_audit_completion_requirement_pass_count": 4,
        "phase2_row_audit_completion_blocker_count": 2,
        "vina_gnina_execution_plan_status": "ready_for_engine_execution",
        "vina_gnina_execution_plan_ready": True,
        "vina_gnina_required_engine_run_count": 24,
        "vina_gnina_input_manifest_status": "ready",
        "vina_gnina_input_manifest_detected": True,
        "vina_gnina_input_manifest_row_count": 12,
        "vina_gnina_input_manifest_syntax_ready": True,
        "vina_gnina_input_manifest_verification_status": "case_inputs_verified",
        "vina_gnina_input_manifest_verified_case_input_count": 12,
        "vina_gnina_input_manifest_template_manifest_ready": True,
        "vina_gnina_input_manifest_template_completion_blocked_case_count": 0,
        "vina_gnina_missing_engine_count": 0,
        "vina_gnina_runtime_readiness_status": "ready_for_engine_execution",
        "vina_gnina_runtime_ready_for_engine_execution": True,
        "vina_gnina_runtime_ready_engine_run_slot_count": 24,
        "vina_gnina_runtime_case_input_slot_count": 12,
        "vina_gnina_runtime_blocked_case_input_slot_count": 0,
        "vina_gnina_runtime_engine_run_slot_count": 24,
        "vina_gnina_runtime_blocked_engine_run_slot_count": 0,
        "vina_gnina_runtime_detected_row_artifact_count": 0,
        "vina_gnina_runtime_adapter_case_count": 0,
        "vina_gnina_runtime_adapter_row_preflight_status": "row_artifact_missing",
        "vina_gnina_engine_run_bundle_status": "engine_run_bundle_materialized",
        "vina_gnina_engine_run_bundle_materialized": True,
        "vina_gnina_rows_from_engine_run_bundle_status": (
            "operator_receipts_completion_required"
        ),
        "vina_gnina_rows_from_engine_run_bundle_materialized": False,
        "vina_gnina_rows_template_preflight_status": (
            "operator_rows_completion_required"
        ),
        "vina_gnina_rows_template_role_receipt_plan_count": 96,
        "vina_gnina_rows_template_role_receipt_blocked_count": 72,
        "vina_gnina_runtime_missing_engine_ids": [],
        "vina_gnina_runtime_container_daemon_available": True,
        "phase2_ready": False,
        "required_component_count": 5,
        "required_row_input_count": 4,
    }
    assert payload["blockers"] == [
        "public_benchmark_vina_gnina_rows_not_acquired",
        "public_benchmark_external_receipts_not_attached",
    ]
    assert payload["commands"]["build_source_access_preflight_receipt"] == (
        "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
        "--out implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.json "
        "--out-md implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_access_preflight_receipt.md"
    )
    assert payload["commands"]["probe_source_access_preflight"].endswith(
        "--probe-network"
    )
    assert "build_source_access_preflight_receipt" in (
        payload["operator_acquisition_checklist"]
    )
    assert payload["operator_next_actions"] == payload[
        "operator_acquisition_checklist"
    ]
    assert payload["operator_next_actions"][:3] == [
        "review_official_source_receipt_plan",
        "attach_casf_pdbbind_subset_rows_with_local_file_checksums",
        "attach_pose_coordinate_rows_with_symmetry_contracts",
    ]
    assert payload["operator_next_actions"][-2:] == [
        "run_public_benchmark_harness_bundle_materializer",
        "refresh_public_benchmark_source_of_truth",
    ]
    assert payload["vina_gnina_rows_template_preflight_summary"]["status"] == (
        "operator_rows_completion_required"
    )
    assert payload["vina_gnina_rows_template_preflight_summary"][
        "role_receipt_plan_count"
    ] == 96
    assert payload["vina_gnina_rows_template_preflight_summary"][
        "role_receipt_blocked_count"
    ] == 72
    assert payload["missing_row_input_action_count"] == 1
    missing_action = payload["missing_row_input_actions"][0]
    assert missing_action["row_input_id"] == "vina_gnina_rows"
    assert missing_action["status"] == "operator_input_required"
    assert missing_action["operator_action"] == (
        "attach_vina_gnina_rows_then_run_phase2_row_audit"
    )
    assert missing_action["next_action"] == (
        "attach_or_materialize_public_benchmark_vina_gnina_rows"
    )
    assert missing_action["command_key"] == "materialize_rows_from_engine_run_bundle"
    assert (
        "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
        in missing_action["materialization_command"]
    )
    assert missing_action["closes_phase2_criteria"] == [
        "vina_gnina_comparison_ready"
    ]
    assert missing_action["phase2_materialization_chain"] == [
        "materialize_public_benchmark_vina_gnina_comparison_adapter"
    ]
    assert missing_action["phase2_required_by_components"][0][
        "required_minimum_count"
    ] == 1
    assert missing_action["engine_input_manifest_template"].endswith(
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert missing_action["engine_input_manifest_expected_path"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert missing_action["engine_input_manifest_current_status"] == "ready"
    assert missing_action["engine_input_manifest_current_blockers"] == []
    runtime_action = missing_action["runtime_action_packet"]
    assert runtime_action["status"] == "engine_run_rows_required"
    assert runtime_action["expected_rows_artifact"].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert runtime_action["input_manifest_template_preflight_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
    )
    assert runtime_action["input_manifest_template_preflight_status"] == (
        "operator_manifest_complete"
    )
    assert runtime_action["input_manifest_template_manifest_ready"] is True
    manifest_preflight = runtime_action["input_manifest_template_preflight_summary"]
    assert manifest_preflight["template_row_count"] == 12
    assert manifest_preflight["template_case_coverage_complete"] is True
    assert manifest_preflight["invalid_source_receipt_count"] == 0
    assert manifest_preflight["unsupported_benchmark_field_count"] == 0
    assert manifest_preflight["missing_local_file_count"] == 0
    assert manifest_preflight["missing_receipt_ref_count"] == 0
    assert manifest_preflight["first_blocked_case_preflight"] == {}
    assert runtime_action["input_manifest_completion_action_case_count"] == 0
    assert runtime_action["input_manifest_completion_blocked_case_count"] == 0
    assert runtime_action["input_manifest_completion_action_plan"] == []
    assert runtime_action["rows_template_preflight_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template_preflight.json"
    )
    assert runtime_action["operator_sequence"][0] == (
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight"
    )
    assert runtime_action["case_input_slot_count"] == 12
    assert runtime_action["blocked_case_input_slot_count"] == 0
    assert runtime_action["first_blocked_case_input_slot"] == {}
    assert runtime_action["blocked_engine_run_slot_count"] == 0
    assert runtime_action["first_blocked_engine_run_slot"] == {}
    assert runtime_action["engine_run_bundle_status"] == "engine_run_bundle_materialized"
    assert runtime_action["engine_run_bundle_materialized"] is True
    assert runtime_action["rows_from_engine_run_bundle_status"] == (
        "operator_receipts_completion_required"
    )
    assert runtime_action["rows_from_engine_run_bundle_materialized"] is False
    assert runtime_action["commands"]["build_rows_template_preflight"].startswith(
        "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"
    )
    assert payload["commands"][
        "materialize_input_manifest_from_casf_archive"
    ].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
        "--archive <CASF-2016.tar.gz>"
    )
    manifest_action = missing_action["engine_input_manifest_action_packet"]
    assert manifest_action["template_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert manifest_action["expected_manifest_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert manifest_action["default_execution_plan_manifest_path"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert manifest_action["recommended_template_dropzone"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert (
        manifest_action["recommended_template_dropzone_is_supported_candidate_path"]
        is True
    )
    assert manifest_action["accepted_manifest_formats"] == [
        "json",
        "jsonl",
        "ndjson",
        "csv",
        "tsv",
    ]
    assert manifest_action["supported_manifest_candidate_paths"] == [
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest.json",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest.jsonl",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest.ndjson",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest.csv",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest.tsv",
    ]
    assert manifest_action["detected_manifest_artifact_count"] == 1
    assert manifest_action["selected_manifest_path"].endswith(
        "public_benchmark_vina_gnina_input_manifest.csv"
    )
    assert manifest_action["selected_manifest_format"] == "csv"
    assert manifest_action["input_manifest_row_count"] == 12
    assert manifest_action["input_manifest_load_errors"] == []
    assert manifest_action["template_to_manifest_command"].startswith(
        "cp implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert manifest_action["source_archive_operator_artifact"] == "<CASF-2016.tar.gz>"
    assert manifest_action["source_archive_extraction_command"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
        "--archive <CASF-2016.tar.gz>"
    )
    assert "--fail-blocked" in manifest_action["source_archive_extraction_command"]
    assert manifest_action["source_archive_extraction_report_artifact"].endswith(
        "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json"
    )
    assert "prepared_receptor_checksum" in manifest_action[
        "operator_must_fill_or_verify"
    ]
    assert manifest_action["template_safety_policy"] == {
        "do_not_treat_blank_prepared_checksums_as_ready": True,
        "expected_manifest_must_be_operator_reviewed": True,
        "no_engine_rows_are_synthesized_by_manifest": True,
        "template_is_not_evidence": True,
    }
    assert missing_action["required_engines"] == ["vina", "gnina"]
    assert missing_action["adapter_intake_formats"] == [
        "json",
        "jsonl",
        "ndjson",
        "csv",
    ]
    assert missing_action["direct_adapter_materialization_command"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
        "--intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson>"
    )
    preflight_action = missing_action["adapter_row_preflight_action_packet"]
    assert preflight_action["status"] == "row_artifact_missing"
    assert preflight_action["expected_rows_artifact"].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert preflight_action["row_template_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template.csv"
    )
    assert preflight_action["row_template_preflight_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template_preflight.json"
    )
    assert preflight_action["template_preflight_summary"][
        "role_receipt_blocked_count"
    ] == 72
    assert preflight_action["role_receipt_plan_summary"][
        "role_receipt_plan_count"
    ] == 96
    assert preflight_action["role_receipt_plan_summary"][
        "role_receipt_blocked_count"
    ] == 72
    assert preflight_action["role_receipt_plan_summary"][
        "first_blocked_role_receipt"
    ]["role_id"] == "engine_run_artifact_receipt"
    assert preflight_action["role_receipt_plan_summary"][
        "first_blocked_role_receipt"
    ]["slot_id"] == "casf2016_4llx_vina_casf2016_4llx_vina_run"
    assert "build_public_benchmark_vina_gnina_rows_template_preflight.py" in preflight_action[
        "build_row_template_preflight_command"
    ]
    assert preflight_action["supported_candidate_paths"] == [
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.json",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.jsonl",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.ndjson",
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows.csv",
    ]
    assert preflight_action["detected_row_artifact_count"] == 0
    assert preflight_action["adapter_preflight_status"] == "missing"
    assert preflight_action["adapter_preflight_blockers"] == []
    assert preflight_action["template_safety_policy"] == {
        "operator_rows_must_be_real_engine_outputs": True,
        "placeholder_or_fixture_rows_do_not_promote": True,
        "preflight_does_not_run_engines": True,
        "template_is_not_evidence": True,
    }
    assert "predicted_ligand_checksum" in missing_action[
        "required_engine_run_fields"
    ]
    assert missing_action["phase2_row_audit_command"] == (
        "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
        "--fail-blocked"
    )


def test_public_benchmark_phase2_source_plan_cli_writes_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "public_benchmark_phase2_source_acquisition_plan.json"
    out_md = tmp_path / "public_benchmark_phase2_source_acquisition_plan.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["required_row_input_count"] == 4
    assert payload["official_source_receipt_plan"]["receipt_role_count"] == 4
    assert payload["official_source_receipt_plan"]["source_catalog_count"] == 6
    assert payload["official_source_receipt_plan"][
        "source_access_preflight_count"
    ] == 6
    assert payload["source_access_preflight_receipt"]["status"] == "reachable"
    assert payload["source_access_preflight_receipt"]["reachable_count"] == 6
    assert payload["source_access_preflight_receipt"]["blocked_count"] == 0
    assert payload["external_receipts_validation"]["status"] == (
        "operator_receipts_required"
    )
    assert payload["external_receipts_validation"][
        "computed_from_materialized_artifacts"
    ] is True
    assert payload["external_receipts_validation"][
        "persisted_artifact_materialized_row_count"
    ] == 0
    assert payload["external_receipts_validation"][
        "receipt_complete_artifact_role_count"
    ] == 2
    assert payload["external_receipts_validation"][
        "missing_expected_artifact_roles"
    ] == ["vina_gnina_comparison_adapter"]
    assert payload["external_receipt_completion_audit"]["status"] == (
        "blocked_pending_vina_gnina_receipts"
    )
    assert payload["external_receipt_completion_audit"][
        "blocked_official_receipt_role_count"
    ] == 1
    assert payload["phase2_exit_criterion_count"] == 5
    assert payload["phase2_harness_completion_audit"]["status"] == (
        "ready_except_vina_gnina_actual_rows"
    )
    assert payload["phase2_harness_completion_audit"][
        "ready_requirement_count"
    ] == 4
    assert payload["phase2_harness_completion_audit"][
        "blocked_requirement_ids"
    ] == ["vina_gnina_comparison_adapter"]
    assert payload["phase2_row_closure_matrix_count"] == 4
    assert payload["vina_gnina_actual_evidence_audit"]["status"] == (
        "adapter_rows_required"
    )
    assert payload["vina_gnina_actual_evidence_audit"][
        "blocked_component_count"
    ] == 3
    assert payload["vina_gnina_execution_plan"]["required_engine_run_count"] == 24
    assert payload["vina_gnina_runtime_readiness"]["status"] == (
        "ready_for_engine_execution"
    )
    assert "# Public Benchmark Phase 2 Source Acquisition Plan" in markdown
    assert "public_benchmark_phase2_row_audit.json" in markdown
    assert "public_benchmark_vina_gnina_execution_plan.json" in markdown
    assert "public_benchmark_vina_gnina_runtime_readiness.json" in markdown
    assert "`vina_gnina_required_engine_run_count`: `24`" in markdown
    assert "`vina_gnina_input_manifest_status`: `ready`" in markdown
    assert "`vina_gnina_runtime_ready_engine_run_slot_count`: `24`" in markdown
    assert "`vina_gnina_runtime_case_input_slot_count`: `12`" in markdown
    assert "`vina_gnina_runtime_blocked_engine_run_slot_count`: `0`" in markdown
    assert "`vina_gnina_rows_template_role_receipt_blocked_count`: `72`" in markdown
    assert "## Source Access Preflight Receipt" in markdown
    assert "`source_access_preflight_receipt_status`: `reachable`" in markdown
    assert "`source_access_preflight_receipt_ready`: `True`" in markdown
    assert "`source_access_preflight_reachable_count`: `6`" in markdown
    assert "`source_access_preflight_blocked_count`: `0`" in markdown
    assert "| `pdbbind_plus_casf` | `CASF/PDBBind` | `primary_reachable` |" in markdown
    assert "| `gnina` | `GNINA` | `primary_reachable` |" in markdown
    assert "`external_receipts_validation_status`: `operator_receipts_required`" in markdown
    assert "`external_receipts_complete_artifact_roles`: `2/3`" in markdown
    assert (
        "`external_receipt_completion_audit_status`: "
        "`blocked_pending_vina_gnina_receipts`"
    ) in markdown
    assert "## External Receipt Completion Audit" in markdown
    assert "`external_receipts_ready_for_materialized_rows`: `False`" in markdown
    assert "`missing_expected_artifact_roles`: `vina_gnina_comparison_adapter`" in markdown
    assert (
        "attach_vina_gnina_rows_and_receipts_then_refresh_external_receipts"
        in markdown
    )
    assert "public_benchmark_external_receipt_role_missing:vina_gnina_comparison_adapter" in markdown
    assert "`phase2_exit_criterion_count`: `5`" in markdown
    assert "`phase2_row_audit_completion_audit_status`: `blocked`" in markdown
    assert "`phase2_row_audit_completion_requirement_pass_count`: `4/6`" in markdown
    assert "## Phase 2 Harness Completion Audit" in markdown
    assert (
        "`phase2_harness_completion_audit_status`: "
        "`ready_except_vina_gnina_actual_rows`"
    ) in markdown
    assert (
        "`phase2_harness_complete_except_vina_gnina_actual_rows`: `True`"
    ) in markdown
    assert "`phase2_harness_ready_requirement_count`: `4`" in markdown
    assert "`phase2_harness_blocked_requirement_count`: `1`" in markdown
    assert "## Vina/GNINA Actual Evidence Audit" in markdown
    assert (
        "`vina_gnina_actual_evidence_audit_status`: "
        "`adapter_rows_required`"
    ) in markdown
    assert "`engine_input_manifest`" in markdown
    assert "`engine_runtime`" in markdown
    assert "`engine_run_slots`" in markdown
    assert "`adapter_rows`" in markdown
    assert "`per_engine_run_receipts`" in markdown
    assert "`external_receipts`" in markdown
    assert "`operator_blocker_family_count`: `7`" in markdown
    assert "`operator_blocker_family_missing_item_count`: `12`" in markdown
    assert "### Vina/GNINA Operator Blocker Families" in markdown
    assert (
        "| Family | Status | Missing Items | Blocked Cases | Operator Action | "
        "Command Key | Materialization Command |"
    ) in markdown
    assert (
        "| `adapter_rows` | `blocked` | 12 | 12 | "
        "`attach_or_materialize_public_benchmark_vina_gnina_rows` |"
    ) in markdown
    assert "build_public_benchmark_vina_gnina_input_manifest_template_preflight.py" in (
        markdown
    )
    assert "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py" in (
        markdown
    )
    assert "`public_benchmark_vina_gnina_rows_not_detected`" in markdown
    assert "`public_benchmark_vina_gnina_engine_run_receipts_incomplete`" in (
        markdown
    )
    assert "`casf_pdbbind_pose_success_harness`" in markdown
    assert "CASF/PDBBind pose-success harness" in markdown
    assert "`posebusters_style_pose_validity_checks`" in markdown
    assert "`blocked_pending_actual_vina_gnina_rows`" in markdown
    assert "`vina_gnina_comparison_adapter`" in markdown
    assert "`phase2_row_closure_matrix_count`: `4`" in markdown
    assert "## Operator Next Actions" in markdown
    assert "| 1 | `review_official_source_receipt_plan` |" in markdown
    assert "| 14 | `refresh_public_benchmark_source_of_truth` |" in markdown
    assert "## Phase 2 Exit Criteria" in markdown
    assert "`posebusters_style_pose_validity_ready`" in markdown
    assert "`vina_gnina_rows_not_provided`" in markdown
    assert "## Phase 2 Row Closure Matrix" in markdown
    assert "`materialize_public_benchmark_vina_gnina_comparison_adapter`" in markdown
    assert "`operator_unblock_status`: `engine_run_rows_required`" in markdown
    assert "`blocked_case_input_slot_count`: `0`" in markdown
    assert "`blocked_engine_run_slot_count`: `0`" in markdown
    assert "## Missing Row Input Actions" in markdown
    assert "attach_vina_gnina_rows_then_run_phase2_row_audit" in markdown
    assert "`vina_gnina_comparison_ready`" in markdown
    assert "materialize_public_benchmark_vina_gnina_comparison_adapter.py" in markdown
    assert "<operator-vina-gnina-run-rows.csv|json|jsonl|ndjson>" in markdown
    assert "### Vina/GNINA Runtime Action Packet" in markdown
    assert "review_public_benchmark_vina_gnina_input_manifest_template_preflight" in (
        markdown
    )
    assert "`first_blocked_case_input_slot`: `` / ``" in markdown
    assert "`first_blocked_engine_run_slot`: `` / `` / ``" in markdown
    assert "`first_operator_sequence_step`: `review_public_benchmark_vina_gnina_input_manifest_template_preflight`" in markdown
    assert "`first_operator_blocker_family`: `adapter_rows` / `12`" in (
        markdown
    )
    assert "#### Vina/GNINA Runtime Blocker Families" in markdown
    assert (
        "| Family | Status | Missing Items | Blocked Cases | Command Key | "
        "Materialization Command |"
    ) in markdown
    assert "| `engine_runtime` | `ready` | 0 | 0 | `rerun_runtime_readiness` |" in (
        markdown
    )
    assert "### Vina/GNINA Adapter Row Preflight Action" in markdown
    assert "public_benchmark_vina_gnina_rows_template_preflight.json" in markdown
    assert "build_public_benchmark_vina_gnina_rows_template_preflight.py" in markdown
    assert "`role_receipt_blocked_count`: `72`" in markdown
    assert (
        "`first_blocked_role_receipt`: `engine_run_artifact_receipt` / "
        "`casf2016_4llx_vina_casf2016_4llx_vina_run`"
    ) in markdown
    assert "public_benchmark_vina_gnina_rows.ndjson" in markdown
    assert "`preflight_does_not_run_engines`: `True`" in markdown
    assert "### Vina/GNINA Input Manifest Action" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_template.csv" in markdown
    assert "public_benchmark_vina_gnina_input_manifest.json" in markdown
    assert "public_benchmark_vina_gnina_input_manifest.csv" in markdown
    assert "`recommended_template_dropzone_is_supported_candidate_path`: `True`" in markdown
    assert "`accepted_manifest_formats`: `json`, `jsonl`, `ndjson`, `csv`, `tsv`" in markdown
    assert "`input_manifest_load_errors`: `none`" in markdown
    assert "materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py" in markdown
    assert "`source_archive_operator_artifact`: `<CASF-2016.tar.gz>`" in markdown
    assert "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json" in markdown
    assert "`template_is_not_evidence`: `True`" in markdown
    assert "prepared_receptor_checksum" in markdown
    assert "## Vina/GNINA Runtime" in markdown
    assert "### Vina/GNINA Case Input Slots" in markdown
    assert "casf2016_4llx_case_inputs" in markdown
    assert "review_vina_gnina_case_inputs_for_casf2016_4llx" in markdown
    assert "### Vina/GNINA Engine Run Slots" in markdown
    assert "casf2016_4llx_vina" in markdown
    assert "attach_vina_gnina_adapter_row_for_casf2016_4llx_vina" in markdown
    assert "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE" in markdown
    assert "container_image_not_configured" in markdown
    assert "`subset_rows` | `CASF/PDBBind`" in markdown
    assert "`vina_gnina_rows` | `CASF/PDBBind + Vina/GNINA`" in markdown
    assert "## Source Receipt Roles" in markdown
    assert "casf_pdbbind_subset_source_receipt" in markdown
    assert "vina_gnina_engine_comparison_receipt" in markdown
    assert "## Official Source Catalog" in markdown
    assert "pdbbind_plus_casf" in markdown
    assert "https://dude.docking.org/targets/" in markdown
    assert "## Source Access Preflight" in markdown
    assert "curl --head --location --max-time 20" in markdown
    assert "https://www.pdbbind-plus.org.cn/casf" in markdown
    assert "materialize_public_benchmark_operator_bundle_from_rows.py" in markdown
