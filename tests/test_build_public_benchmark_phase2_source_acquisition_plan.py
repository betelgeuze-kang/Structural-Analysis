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
    assert receipt_plan["row_input_count"] == 4
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
    assert payload["vina_gnina_execution_plan"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_execution_plan.json"
    )
    assert payload["vina_gnina_execution_plan"]["status"] == (
        "engine_input_blocked"
    )
    assert payload["vina_gnina_execution_plan"]["execution_plan_ready"] is False
    assert payload["vina_gnina_execution_plan"]["operator_execution_ready"] is False
    assert payload["vina_gnina_execution_plan"]["adapter_rows_ready"] is False
    assert payload["vina_gnina_execution_plan"]["case_count"] == 12
    assert payload["vina_gnina_execution_plan"]["required_engine_run_count"] == 24
    assert payload["vina_gnina_execution_plan"]["missing_engine_ids"] == []
    assert payload["vina_gnina_runtime_readiness"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_runtime_readiness.json"
    )
    assert payload["vina_gnina_runtime_readiness"]["status"] == (
        "execution_plan_blocked"
    )
    assert payload["vina_gnina_runtime_readiness"][
        "runtime_ready_for_engine_execution"
    ] is False
    assert payload["vina_gnina_runtime_readiness"][
        "ready_engine_run_slot_count"
    ] == 0
    assert payload["vina_gnina_runtime_readiness"]["available_engine_count"] == 2
    assert payload["vina_gnina_runtime_readiness"]["missing_engine_count"] == 0
    assert payload["vina_gnina_runtime_readiness"][
        "detected_row_artifact_count"
    ] == 0
    assert payload["vina_gnina_runtime_readiness"]["missing_engine_ids"] == []
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
    assert container_statuses["gnina"]["status"] == "container_image_not_configured"
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
    assert vina_gnina["required_engines"] == ["vina", "gnina"]
    assert vina_gnina["row_validation_policies"]["engine_pair_policy"] == (
        module.ENGINE_PAIR_POLICY
    )

    assert payload["summary"] == {
        "actual_closure_ready": False,
        "blocker_count": 3,
        "minimum_enrichment_target_count": 1,
        "minimum_subset_case_count": 12,
        "minimum_vina_gnina_comparison_case_count": 1,
        "official_source_receipt_plan_status": "operator_receipts_required",
        "official_source_receipt_role_count": 4,
        "official_source_catalog_count": 6,
        "phase2_row_audit_blocker_count": 1,
        "phase2_row_audit_failed_criteria": [
            "vina_gnina_comparison_ready",
        ],
        "phase2_row_audit_missing_row_input_count": 1,
        "phase2_row_audit_missing_row_inputs": [
            "vina_gnina_rows",
        ],
        "phase2_row_audit_status": "operator_evidence_required",
        "vina_gnina_execution_plan_status": "engine_input_blocked",
        "vina_gnina_execution_plan_ready": False,
        "vina_gnina_required_engine_run_count": 24,
        "vina_gnina_missing_engine_count": 0,
        "vina_gnina_runtime_readiness_status": "execution_plan_blocked",
        "vina_gnina_runtime_ready_for_engine_execution": False,
        "vina_gnina_runtime_ready_engine_run_slot_count": 0,
        "vina_gnina_runtime_detected_row_artifact_count": 0,
        "vina_gnina_runtime_missing_engine_ids": [],
        "vina_gnina_runtime_container_daemon_available": True,
        "phase2_ready": False,
        "required_component_count": 5,
        "required_row_input_count": 4,
    }
    assert payload["blockers"] == [
        "public_benchmark_vina_gnina_rows_not_acquired",
        "public_benchmark_vina_gnina_engine_inputs_not_ready",
        "public_benchmark_external_receipts_not_attached",
    ]


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
    assert payload["vina_gnina_execution_plan"]["required_engine_run_count"] == 24
    assert payload["vina_gnina_runtime_readiness"]["status"] == (
        "execution_plan_blocked"
    )
    assert "# Public Benchmark Phase 2 Source Acquisition Plan" in markdown
    assert "public_benchmark_phase2_row_audit.json" in markdown
    assert "public_benchmark_vina_gnina_execution_plan.json" in markdown
    assert "public_benchmark_vina_gnina_runtime_readiness.json" in markdown
    assert "`vina_gnina_required_engine_run_count`: `24`" in markdown
    assert "`vina_gnina_runtime_ready_engine_run_slot_count`: `0`" in markdown
    assert "## Vina/GNINA Runtime" in markdown
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
    assert "materialize_public_benchmark_operator_bundle_from_rows.py" in markdown
