from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_public_benchmark_source_of_truth.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_source_of_truth", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_public_benchmark_source_of_truth_keeps_beta_claim_blocked() -> None:
    artifacts = module.build_public_benchmark_artifacts(repo_root=REPO_ROOT)
    source = artifacts["source_of_truth"]
    subset = artifacts["subset_manifest"]
    pose_packet = artifacts["pose_validity_packet"]
    rmsd = artifacts["rmsd_scorecard"]
    pose_harness = artifacts["pose_success_harness"]
    enrichment = artifacts["enrichment_scorecard"]
    vina_gnina = artifacts["vina_gnina_comparison_adapter"]

    assert source["schema_version"] == "public-benchmark-source-of-truth.v1"
    assert source["contract_pass"] is True
    assert source["read_model_ready"] is True
    assert source["route"] == "/product/public-benchmark"
    assert source["read_model"] == {
        "route": "/product/public-benchmark",
        "alternate_routes": [
            "/product/public-benchmark/operator-intake",
            "/product/capabilities",
            "/goal/bottleneck",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_source_of_truth.json"
        ),
        "mutation_allowed": False,
    }
    assert source["tier_beta_ready"] is False
    assert source["public_benchmark_ready"] is False
    assert source["blocker_count"] == 10
    assert source["blockers"] == [
        "casf_pdbbind_source_material_not_attached",
        "casf_pdbbind_case_checksums_missing",
        "casf_pdbbind_ligand_symmetry_contracts_missing",
        "public_benchmark_real_pose_predictions_missing",
        "public_benchmark_real_pose_validity_rows_missing",
        "public_benchmark_real_rmsd_rows_missing",
        "public_benchmark_pose_success_harness_rows_missing",
        "dud_e_lit_pcba_enrichment_rows_missing",
        "vina_gnina_comparison_rows_missing",
        "public_benchmark_external_receipts_missing",
    ]
    assert source["first_blocker"] == "casf_pdbbind_source_material_not_attached"
    assert source["first_blocked_target"] == "casf_pdbbind_subset_intake"
    assert source["first_required_operator_slot"] == "casf_pdbbind_subset_intake"
    assert source["first_manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert (
        source["casf_pdbbind_subset_manifest_contract"]["target_subset_case_count"]
        == 12
    )
    assert (
        source["casf_pdbbind_subset_manifest_contract"]["checksum_policy"][
            "required_manifest_field"
        ]
        == "source_file_checksums"
    )
    assert source["required_slot_count"] == 4
    assert source["operator_template_artifact_count"] == 4
    assert source["operator_template_artifacts"][
        "casf_pdbbind_subset_intake"
    ].endswith("public_benchmark_casf_pdbbind_operator_template.json")
    assert source["harness_bundle_index"] == {
        "schema_version": "public-benchmark-harness-bundle.v1",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle.json"
        ),
        "status": "ready_for_local_artifact_index",
        "artifact_index_command": (
            "python3 scripts/materialize_public_benchmark_harness_bundle.py "
            "--out implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle.json"
        ),
        "materialization_report": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle_materialization_report.json"
        ),
        "claim_boundary": (
            "Indexes local public-benchmark harness artifacts only; it does not "
            "fetch, license, redistribute, or approve external benchmark data."
        ),
    }
    assert source["linked_artifacts"]["harness_bundle"].endswith(
        "public_benchmark_harness_bundle.json"
    )
    assert source["blocked_operator_slot_count"] == 4
    assert source["root_cause_tags"] == [
        "operator_source_material_required",
        "operator_receipts_required",
    ]
    assert source["summary_line"] == (
        "Public benchmark source-of-truth: BLOCKED | completed_slices=7 | "
        "blocked_slices=5 | first_blocker=casf_pdbbind_source_material_not_attached"
    )
    assert source["source_tracking"]["mode"] == "direct_builder_source_tracking"
    assert source["source_tracking"]["missing_source_artifact_count"] == 0
    assert (
        source["source_tracking"]["input_checksum_count"]
        == source["source_tracking"]["source_artifact_count"]
    )
    assert (
        "scripts/build_public_benchmark_source_of_truth.py"
        in source["source_tracking"]["source_artifacts"]
    )
    assert {
        row["slice_id"]: row["status"] for row in source["completed_slices"]
    } == {
        "public_benchmark_source_of_truth_spec": "contract_ready",
        "casf_pdbbind_subset_manifest_contract": "contract_ready",
        "symmetry_aware_rmsd_scorer_dry_run": "dry_run_ready",
        "posebusters_style_validity_packet_shape": "dry_run_ready",
        "casf_pdbbind_pose_success_harness_contract": "contract_ready",
        "operator_intake_handoff_packet": "ready_for_operator_input",
        "public_benchmark_external_receipt_contract": "contract_ready",
    }
    assert {
        row["slice_id"]: row["status"] for row in source["blocked_slices"]
    } == {
        "casf_pdbbind_subset_materialization": "operator_source_material_required",
        "real_pose_coordinate_materialization": "operator_pose_coordinates_required",
        "dud_e_lit_pcba_enrichment_materialization": "operator_enrichment_rows_required",
        "vina_gnina_comparison_materialization": "operator_engine_comparison_rows_required",
        "public_benchmark_external_receipts_validation": "operator_receipts_required",
    }
    blocked_slices_by_id = {
        row["slice_id"]: row for row in source["blocked_slices"]
    }
    assert blocked_slices_by_id["casf_pdbbind_subset_materialization"][
        "first_blocker"
    ] == "casf_pdbbind_source_material_not_attached"
    assert blocked_slices_by_id["casf_pdbbind_subset_materialization"][
        "first_blocked_target"
    ] == "casf_pdbbind_subset_intake"
    assert blocked_slices_by_id["casf_pdbbind_subset_materialization"][
        "operator_handoff_id"
    ] == "public_benchmark::casf_pdbbind_subset_intake"
    assert blocked_slices_by_id["casf_pdbbind_subset_materialization"][
        "root_cause_tags"
    ] == ["operator_source_material_required", "operator_receipts_required"]
    assert blocked_slices_by_id["casf_pdbbind_subset_materialization"][
        "blocked_tier_beta_criteria"
    ] == ["casf_pdbbind_subset_materialized", "external_receipts_attached"]
    assert blocked_slices_by_id["real_pose_coordinate_materialization"][
        "operator_slot_id"
    ] == "pose_coordinate_intake"
    assert blocked_slices_by_id["real_pose_coordinate_materialization"][
        "next_action"
    ] == "use case_id values from the materialized CASF/PDBBind subset manifest"
    assert blocked_slices_by_id["public_benchmark_external_receipts_validation"][
        "related_operator_slot_ids"
    ] == [
        "casf_pdbbind_subset_intake",
        "dud_e_lit_pcba_enrichment_intake",
        "vina_gnina_comparison_intake",
    ]
    assert blocked_slices_by_id["public_benchmark_external_receipts_validation"][
        "root_cause_tags"
    ] == ["operator_receipts_required"]
    assert blocked_slices_by_id["public_benchmark_external_receipts_validation"][
        "next_action"
    ].startswith("attach source_license_or_accession")
    assert source["materialization_progress"] == {
        "completed_slice_count": 7,
        "blocked_slice_count": 5,
        "target_subset_case_count": 12,
        "materialized_subset_case_count": 0,
        "real_pose_case_count": 0,
        "real_rmsd_case_count": 0,
        "real_pose_success_harness_case_count": 0,
        "real_enrichment_target_count": 0,
        "real_vina_gnina_comparison_case_count": 0,
        "external_receipt_complete_row_count": 0,
        "external_receipt_complete_artifact_role_count": 0,
        "external_receipt_missing_artifact_role_count": 3,
        "tier_beta_failed_criterion_count": 8,
        "next_unblock_slice_id": "casf_pdbbind_subset_materialization",
        "claim_boundary": (
            "Completed slices are repo-local contracts or synthetic dry-runs. "
            "Blocked slices require operator-attached public benchmark rows and "
            "external receipts before Tier beta can be claimed."
        ),
    }
    pose_blocked_slice = {
        row["slice_id"]: row for row in source["blocked_slices"]
    }["real_pose_coordinate_materialization"]
    assert pose_blocked_slice["current"] == {
        "real_pose_case_count": 0,
        "real_rmsd_case_count": 0,
        "real_pose_success_harness_case_count": 0,
    }
    receipt_blocked_slice = {
        row["slice_id"]: row for row in source["blocked_slices"]
    }["public_benchmark_external_receipts_validation"]
    assert receipt_blocked_slice["missing_artifact_roles"] == [
        "casf_pdbbind_subset_manifest",
        "dud_e_lit_pcba_enrichment_scorecard",
        "vina_gnina_comparison_adapter",
    ]
    assert receipt_blocked_slice["current"][
        "receipt_complete_artifact_role_count"
    ] == 0
    assert pose_blocked_slice["blockers"] == [
        "public_benchmark_real_pose_predictions_missing",
        "public_benchmark_real_pose_validity_rows_missing",
        "public_benchmark_real_rmsd_rows_missing",
        "public_benchmark_pose_success_harness_rows_missing",
    ]
    assert source["operator_handoff_queue_count"] == 4
    assert source["first_operator_handoff"]["handoff_id"] == (
        "public_benchmark::casf_pdbbind_subset_intake"
    )
    assert source["first_operator_handoff"]["template_artifact"].endswith(
        "public_benchmark_casf_pdbbind_operator_template.json"
    )
    assert {
        row["slot_id"]: row["route"] for row in source["operator_handoff_queue"]
    } == {
        "casf_pdbbind_subset_intake": "/product/public-benchmark/operator-intake",
        "pose_coordinate_intake": "/product/public-benchmark/operator-intake",
        "dud_e_lit_pcba_enrichment_intake": "/product/public-benchmark/operator-intake",
        "vina_gnina_comparison_intake": "/product/public-benchmark/operator-intake",
    }
    assert source["operator_handoff_summary"] == {
        "route": "/product/public-benchmark/operator-intake",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_operator_intake_packet.json"
        ),
        "operator_template_artifacts": {
            "casf_pdbbind_subset_intake": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_casf_pdbbind_operator_template.json"
            ),
            "dud_e_lit_pcba_enrichment_intake": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_enrichment_operator_template.json"
            ),
            "pose_coordinate_intake": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_coordinate_operator_template.json"
            ),
            "vina_gnina_comparison_intake": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_vina_gnina_operator_template.json"
            ),
        },
        "first_blocker": "casf_pdbbind_source_material_not_attached",
        "first_blocked_target": "casf_pdbbind_subset_intake",
        "manifest_contract_id": "casf_pdbbind_subset_manifest_contract",
        "first_next_action": "attach at least 12 local CASF/PDBBind case descriptors",
        "template_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_casf_pdbbind_operator_template.json"
        ),
        "required_slot_count": 4,
        "operator_template_schema_version": "public-benchmark-operator-template.v1",
        "operator_template_artifact_count": 4,
        "blocked_operator_slot_count": 4,
        "minimum_evidence": {
            "case_count": 12,
            "source_family": "CASF/PDBBind",
            "supported_benchmark_splits": [
                "CASF-core",
                "PDBBind-core",
                "PDBBind-refined",
                "PDBBind-general",
            ],
            "local_source_file_fields": [
                "protein_structure_path",
                "reference_ligand_path",
                "predicted_ligand_path_or_docking_run_id",
            ],
            "ligand_atom_order_contract_fields": ["atom_count", "atom_ids"],
            "symmetry_permutation_contract_fields": ["permutations"],
            "materialized_manifest_fields": ["source_file_checksums"],
            "receipt_fields": [
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
            ],
        },
        "materialization_command": (
            "python3 scripts/materialize_public_benchmark_subset_manifest.py "
            "--intake <operator-casf-pdbbind-intake.json> "
            "--out-manifest implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_manifest.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_materialization_report.json --fail-blocked"
        ),
        "validation_command": (
            "python3 scripts/validate_public_benchmark_subset_manifest.py "
            "--manifest implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_manifest.json --fail-blocked"
        ),
    }
    assert source["operator_handoff_queue_count"] == 4
    assert source["first_operator_handoff"] == source["operator_handoff_queue"][0]
    assert source["first_operator_handoff"]["handoff_id"] == (
        "public_benchmark::casf_pdbbind_subset_intake"
    )
    assert source["first_operator_handoff"]["route"] == (
        "/product/public-benchmark/operator-intake"
    )
    assert source["first_operator_handoff"]["blocked_tier_beta_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert source["first_operator_handoff"]["first_next_action"] == (
        "attach at least 12 local CASF/PDBBind case descriptors"
    )
    assert source["first_operator_handoff"]["template_artifact"].endswith(
        "public_benchmark_casf_pdbbind_operator_template.json"
    )
    assert (
        "materialize_public_benchmark_subset_manifest.py"
        in source["first_operator_handoff"]["materialization_command"]
    )
    assert (
        "validate_public_benchmark_subset_manifest.py"
        in source["first_operator_handoff"]["validation_command"]
    )
    assert source["tier_beta_gate"]["status"] == "blocked"
    assert source["tier_beta_gate"]["claim"] == "tier_beta_public_benchmark_harness"
    assert source["tier_beta_gate"]["minimum_subset_case_count"] == 12
    assert source["tier_beta_gate"]["failed_criterion_count"] == 8
    assert source["tier_beta_gate"]["failed_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "casf_pdbbind_pose_success_harness_ready",
        "dud_e_lit_pcba_enrichment_ready",
        "vina_gnina_comparison_ready",
        "external_receipts_attached",
    ]
    assert {
        row["criterion_id"]: row["pass"] for row in source["tier_beta_gate"]["criteria"]
    } == {
        "casf_pdbbind_subset_materialized": False,
        "real_pose_validity_packet_materialized": False,
        "symmetry_rmsd_scorecard_real_cases": False,
        "posebusters_style_validity_real_ligands": False,
        "casf_pdbbind_pose_success_harness_ready": False,
        "dud_e_lit_pcba_enrichment_ready": False,
        "vina_gnina_comparison_ready": False,
        "external_receipts_attached": False,
    }
    subset_summary = source["subset_manifest_summary"]
    assert subset_summary["target_subset_case_count"] == 12
    assert subset_summary["materialized_case_count"] == 0
    assert subset_summary["blockers"] == [
        "casf_pdbbind_source_material_not_attached",
        "casf_pdbbind_case_checksums_missing",
        "casf_pdbbind_ligand_symmetry_contracts_missing",
    ]
    subset_coverage = subset_summary["source_material_coverage"]
    assert subset_coverage["missing_case_count"] == 12
    assert subset_coverage["source_file_checksum_case_count"] == 0
    assert subset_coverage["ligand_atom_order_contract_case_count"] == 0
    assert subset_coverage["symmetry_permutation_contract_case_count"] == 0
    assert subset_coverage["receipt_complete_case_count"] == 0
    assert subset_coverage["benchmark_split_counts"] == {}
    assert source["symmetry_rmsd_summary"] == {
        "status": "ready",
        "dry_run_case_count": 1,
        "real_benchmark_case_count": 0,
        "dry_run_pose_success": True,
    }
    assert source["symmetry_rmsd_scorecard_summary"] == source["symmetry_rmsd_summary"]
    assert source["pose_success_harness_summary"] == {
        "status": "ready_for_real_benchmark_rows",
        "pose_success_harness_ready": False,
        "case_count": 1,
        "dry_run_case_count": 1,
        "real_benchmark_case_count": 0,
        "pose_success_count": 1,
        "pose_success_rate": 1.0,
        "blockers": ["public_benchmark_pose_success_harness_rows_missing"],
    }
    assert source["enrichment_scorecard_summary"] == {
        "status": "operator_evidence_required",
        "public_benchmark_enrichment_ready": False,
        "real_enrichment_target_count": 0,
        "blockers": [
            "dud_e_lit_pcba_enrichment_targets_missing",
            "dud_e_lit_pcba_scored_molecules_missing",
            "dud_e_lit_pcba_active_decoy_labels_missing",
        ],
    }
    assert source["vina_gnina_comparison_adapter_summary"] == {
        "status": "operator_evidence_required",
        "public_benchmark_engine_comparison_ready": False,
        "real_comparison_case_count": 0,
        "supported_engines": ["vina", "gnina"],
        "blockers": [
            "vina_gnina_comparison_cases_missing",
            "vina_gnina_engine_runs_missing",
            "vina_gnina_external_receipts_missing",
        ],
    }
    assert source["external_receipts_summary"]["receipt_coverage"][
        "missing_expected_artifact_roles"
    ] == [
        "casf_pdbbind_subset_manifest",
        "dud_e_lit_pcba_enrichment_scorecard",
        "vina_gnina_comparison_adapter",
    ]
    assert source["external_receipts_summary"]["receipt_coverage"][
        "receipt_complete_artifact_role_count"
    ] == 0
    assert source["pose_validity_packet_summary"] == {
        "status": "ready_for_dry_run",
        "check_count": 7,
        "required_check_count": 7,
        "validator_schema_version": "public-benchmark-pose-validity-validation.v1",
        "materializer_schema_version": (
            "public-benchmark-posebusters-style-validity-packet-materialization.v1"
        ),
        "dry_run_pose_validity_ready": True,
        "real_benchmark_case_count": 0,
    }
    assert source["subset_manifest_validation"]["status"] == "source_material_required"
    assert source["subset_manifest_validation"]["public_benchmark_ready"] is False
    assert source["subset_manifest_validation"]["blockers"] == [
        "materialized_case_count_below_target",
    ]
    assert source["subset_manifest_validation"]["source_material_coverage"][
        "missing_case_count"
    ] == 12
    assert source["subset_materializer"] == {
        "schema_version": "public-benchmark-subset-materialization.v1",
        "status": "ready_for_operator_intake",
        "intake_case_key": "cases",
        "required_case_fields": [
            "case_id",
            "source_family",
            "benchmark_split",
            "complex_id",
            "protein_structure_path",
            "reference_ligand_path",
            "predicted_ligand_path_or_docking_run_id",
            "ligand_atom_order_contract",
            "symmetry_permutation_contract",
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
            "pose_success_metric",
            "rmsd_threshold_angstrom",
        ],
        "supported_benchmark_splits": [
            "CASF-core",
            "PDBBind-core",
            "PDBBind-refined",
            "PDBBind-general",
        ],
        "local_source_file_fields": [
            "protein_structure_path",
            "reference_ligand_path",
            "predicted_ligand_path_or_docking_run_id",
        ],
        "materialization_command": subset["case_row_schema"]["materialization_command"],
        "claim_boundary": (
            "The materializer consumes operator-attached local CASF/PDBBind case "
            "descriptors and files, computes checksums, and validates the subset "
            "manifest. It does not fetch, redistribute, or license benchmark data."
        ),
    }
    assert source["pose_validity_materializer"] == {
        "schema_version": "public-benchmark-pose-validity-input-materialization.v1",
        "status": "ready_for_operator_intake",
        "required_pose_fields": [
            "case_id",
            "pose_success_metric",
            "benchmark_split",
            "reference_atoms",
            "predicted_atoms",
            "ligand_atom_order_contract",
            "symmetry_permutation_contract",
            "protein_structure_path",
            "receptor_context",
        ],
        "pose_intake_case_key": "cases",
        "materialization_command": pose_packet["validator"]["materialization_command"],
        "claim_boundary": (
            "The pose materializer joins a materialized subset manifest with "
            "operator-attached reference/predicted ligand coordinates and receptor "
            "context, then runs the local PoseBusters-style validator. It does not "
            "parse chemistry files or claim benchmark performance."
        ),
    }
    assert source["rmsd_scorecard_materializer"] == {
        "schema_version": "public-benchmark-rmsd-scorecard-materialization.v1",
        "status": "ready_for_pose_validity_input",
        "materialization_command": rmsd["materializer"]["materialization_command"],
        "claim_boundary": (
            "The RMSD scorecard materializer consumes validated pose-coordinate input "
            "and produces per-case symmetry-aware ligand RMSD rows plus pose-success "
            "counts. It does not compare docking engines or close Tier beta alone."
        ),
    }
    assert source["posebusters_validity_packet_materializer"] == {
        "schema_version": (
            "public-benchmark-posebusters-style-validity-packet-materialization.v1"
        ),
        "status": "ready_for_pose_validity_input",
        "materialization_command": pose_packet["materializer"][
            "materialization_command"
        ],
        "claim_boundary": (
            "The PoseBusters-style packet materializer consumes validated "
            "pose-coordinate input and emits per-case sanity-check rows for real "
            "benchmark ligands. It does not infer chemistry or close Tier beta."
        ),
    }
    assert source["pose_success_harness_materializer"] == {
        "schema_version": "public-benchmark-pose-success-harness-materialization.v1",
        "status": "ready_for_pose_validity_packet_and_rmsd_scorecard",
        "materialization_command": pose_harness["materializer"][
            "materialization_command"
        ],
        "claim_boundary": (
            "The pose-success harness materializer joins per-case "
            "PoseBusters-style validity rows with symmetry-aware RMSD rows. It "
            "does not fetch benchmark data, run docking engines, or close Tier "
            "beta alone."
        ),
    }
    assert source["enrichment_scorecard_materializer"] == {
        "schema_version": "public-benchmark-enrichment-materialization.v1",
        "status": "ready_for_operator_intake",
        "materialization_command": enrichment["materializer"][
            "materialization_command"
        ],
        "claim_boundary": (
            "The enrichment materializer consumes DUD-E/LIT-PCBA scored molecule "
            "rows and reports EF@1%, EF@5%, and ROC-AUC per target. It does not "
            "download benchmark data, validate chemistry, or close Tier beta alone."
        ),
    }
    assert source["vina_gnina_comparison_materializer"] == {
        "schema_version": "public-benchmark-vina-gnina-comparison-materialization.v1",
        "status": "ready_for_operator_intake",
        "materialization_command": vina_gnina["materializer"][
            "materialization_command"
        ],
        "claim_boundary": (
            "The Vina/GNINA adapter materializer consumes operator-attached engine "
            "comparison rows and reports per-engine pose-success summaries. It does "
            "not run docking engines, fetch benchmark data, or close Tier beta alone."
        ),
    }
    assert {
        row["family_id"]: row["materialization_status"]
        for row in source["source_families"]
    }["dud_e_lit_pcba"] == "operator_intake_required"
    assert {
        row["family_id"]: row["materialization_status"]
        for row in source["source_families"]
    }["vina_gnina"] == "operator_intake_required"
    assert source["harness_bundle_index"] == {
        "schema_version": "public-benchmark-harness-bundle.v1",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle.json"
        ),
        "status": "ready_for_local_artifact_index",
        "artifact_index_command": (
            "python3 scripts/materialize_public_benchmark_harness_bundle.py "
            "--out implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle.json"
        ),
        "materialization_report": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle_materialization_report.json"
        ),
        "claim_boundary": (
            "Indexes local public-benchmark harness artifacts only; it does not "
            "fetch, license, redistribute, or approve external benchmark data."
        ),
    }
    assert source["linked_artifacts"]["harness_bundle"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_harness_bundle.json"
    )
    assert source["operator_intake_packet"]["schema_version"] == (
        "public-benchmark-operator-intake-packet.v1"
    )
    assert source["operator_intake_packet"]["status"] == "ready_for_operator_input"
    assert source["operator_intake_packet"]["artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_operator_intake_packet.json"
    )
    assert source["operator_intake_packet"]["route"] == (
        "/product/public-benchmark/operator-intake"
    )
    assert source["operator_intake_packet"]["read_model"] == {
        "route": "/product/public-benchmark/operator-intake",
        "alternate_routes": ["/product/public-benchmark", "/product/capabilities"],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_operator_intake_packet.json"
        ),
        "mutation_allowed": False,
    }
    assert source["operator_intake_packet"]["required_slot_count"] == 4
    assert source["operator_intake_packet"]["gate_unblock_plan_count"] == 4
    assert source["operator_intake_packet"]["minimum_subset_case_count"] == 12
    assert source["operator_intake_packet"]["manifest_contract_count"] == 1
    assert source["operator_intake_packet"]["first_manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert source["operator_intake_packet"]["first_manifest_contract"]["produces"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_manifest.json"
    )
    assert source["operator_intake_packet"]["first_blocked_target"] == (
        "casf_pdbbind_subset_intake"
    )
    assert source["operator_intake_packet"]["root_cause_tags"] == [
        "operator_source_material_required",
        "operator_receipts_required",
    ]
    assert source["operator_intake_packet"]["operator_evidence_gap_count"] == 4
    assert (
        source["operator_intake_packet"]["first_operator_evidence_gap"]["slot_id"]
        == "casf_pdbbind_subset_intake"
    )
    assert source["operator_intake_packet"]["input_slot_ids"] == [
        "casf_pdbbind_subset_intake",
        "pose_coordinate_intake",
        "dud_e_lit_pcba_enrichment_intake",
        "vina_gnina_comparison_intake",
    ]
    gate_plan = {
        row["slot_id"]: row
        for row in source["operator_intake_packet"]["gate_unblock_plan"]
    }
    assert (
        source["operator_gate_unblock_plan"]
        == source["operator_intake_packet"]["gate_unblock_plan"]
    )
    assert source["operator_evidence_gap_count"] == 4
    assert source["first_operator_evidence_gap"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert source["first_operator_evidence_gap"]["manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert source["first_operator_evidence_gap"]["blocked_tier_beta_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert source["first_operator_evidence_gap"]["first_next_action"] == (
        "attach at least 12 local CASF/PDBBind case descriptors"
    )
    evidence_gap_register = {
        row["slot_id"]: row for row in source["operator_evidence_gap_register"]
    }
    blocker_detail_register = {
        row["slot_id"]: row for row in source["operator_blocker_detail_register"]
    }
    assert source["operator_blocker_detail_count"] == 4
    assert source["first_operator_blocker_detail"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert source["operator_intake_packet"][
        "source_of_truth_blocker_detail_count"
    ] == 4
    assert source["operator_intake_packet"][
        "source_of_truth_first_blocker_detail"
    ]["slot_id"] == "casf_pdbbind_subset_intake"
    assert (
        evidence_gap_register["casf_pdbbind_subset_intake"]["manifest_contract"][
            "nested_contracts"
        ][2]["field"]
        == "symmetry_permutation_contract"
    )
    assert evidence_gap_register["pose_coordinate_intake"][
        "blocked_tier_beta_criteria"
    ] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "casf_pdbbind_pose_success_harness_ready",
    ]
    assert evidence_gap_register["dud_e_lit_pcba_enrichment_intake"][
        "minimum_evidence"
    ]["supported_families"] == ["DUD-E", "LIT-PCBA"]
    assert blocker_detail_register["dud_e_lit_pcba_enrichment_intake"][
        "blockers"
    ] == [
        "dud_e_lit_pcba_enrichment_targets_missing",
        "dud_e_lit_pcba_scored_molecules_missing",
        "dud_e_lit_pcba_active_decoy_labels_missing",
        "public_benchmark_external_receipts_missing",
    ]
    assert blocker_detail_register["dud_e_lit_pcba_enrichment_intake"][
        "first_next_action"
    ] == "attach at least one DUD-E or LIT-PCBA target with active and decoy labels"
    assert (
        "materialize_public_benchmark_enrichment_scorecard.py"
        in evidence_gap_register["dud_e_lit_pcba_enrichment_intake"][
            "validation_command"
        ]
    )
    assert evidence_gap_register["vina_gnina_comparison_intake"][
        "materialization_steps"
    ] == ["materialize_vina_gnina_comparison_adapter"]
    assert blocker_detail_register["vina_gnina_comparison_intake"]["blockers"] == [
        "vina_gnina_comparison_cases_missing",
        "vina_gnina_engine_runs_missing",
        "vina_gnina_external_receipts_missing",
        "public_benchmark_external_receipts_missing",
    ]
    assert blocker_detail_register["vina_gnina_comparison_intake"][
        "minimum_evidence"
    ]["required_engines"] == ["vina", "gnina"]
    assert (
        "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
        in evidence_gap_register["vina_gnina_comparison_intake"][
            "validation_command"
        ]
    )
    assert evidence_gap_register["vina_gnina_comparison_intake"]["depends_on"] == [
        "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json",
        "implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json",
    ]
    assert (
        gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"]["case_count"] == 12
    )
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "supported_benchmark_splits"
    ] == ["CASF-core", "PDBBind-core", "PDBBind-refined", "PDBBind-general"]
    assert gate_plan["casf_pdbbind_subset_intake"]["manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert gate_plan["pose_coordinate_intake"]["unblocks_tier_beta_criteria"] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "casf_pdbbind_pose_success_harness_ready",
    ]
    assert gate_plan["vina_gnina_comparison_intake"]["materialization_steps"] == [
        "materialize_vina_gnina_comparison_adapter"
    ]
    assert source["operator_intake_packet"]["acceptance_criteria"][-1] == (
        "public_benchmark_source_of_truth.public_benchmark_ready == true"
    )
    assert source["next_actions"] == [
        "fill_public_benchmark_operator_intake_packet",
        "materialize_public_benchmark_operator_bundle_from_rows",
        "attach_checked_casf_pdbbind_subset_source_files",
        "run_public_benchmark_subset_materializer",
        "fill_ligand_atom_order_and_symmetry_permutation_contracts",
        "attach_public_benchmark_pose_coordinate_intake",
        "run_public_benchmark_pose_validity_materializer",
        "run_symmetry_aware_rmsd_on_real_subset",
        "run_public_benchmark_rmsd_scorecard_materializer",
        "materialize_posebusters_style_validity_packet_for_real_ligands",
        "materialize_casf_pdbbind_pose_success_harness",
        "attach_dud_e_lit_pcba_enrichment_intake",
        "run_public_benchmark_enrichment_materializer",
        "attach_vina_gnina_comparison_intake",
        "run_public_benchmark_vina_gnina_comparison_materializer",
    ]
    assert "Vina/GNINA comparison" in source["claim_boundary"]
    assert "DUD-E/LIT-PCBA enrichment results" in source["claim_boundary"]

    assert subset["schema_version"] == "public-benchmark-subset-manifest.v1"
    assert subset["source_families"] == ["CASF/PDBBind"]
    assert subset["target_subset_case_count"] == 12
    assert subset["materialized_case_count"] == 0
    assert subset["source_material_coverage"]["missing_case_count"] == 12
    assert subset["source_material_coverage"]["required_local_source_file_fields"] == [
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
    ]
    assert subset["case_rows"] == []
    assert subset["case_row_schema"]["required_fields"] == [
        "case_id",
        "source_family",
        "benchmark_split",
        "complex_id",
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
        "ligand_atom_order_contract",
        "symmetry_permutation_contract",
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
        "pose_success_metric",
        "rmsd_threshold_angstrom",
    ]
    assert subset["case_row_schema"]["template"]["source_family"] == "CASF/PDBBind"
    assert subset["case_row_schema"]["template"]["benchmark_split"] == "CASF-core"
    assert subset["case_row_schema"]["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert (
        "validate_public_benchmark_subset_manifest.py"
        in subset["case_row_schema"]["validation_command"]
    )
    assert (
        "materialize_public_benchmark_subset_manifest.py"
        in subset["case_row_schema"]["materialization_command"]
    )
    assert (
        "scripts/materialize_public_benchmark_subset_manifest.py"
        in subset["input_checksums"]
    )
    assert {row["slot_id"] for row in subset["slots"]} == {
        "casf_pdbbind_pose_success_seed",
        "casf_pdbbind_affinity_control_seed",
    }
    assert all(row["status"] == "source_material_required" for row in subset["slots"])
    assert all(
        "symmetry_permutation_contract" in row["required_fields"]
        for row in subset["slots"]
    )

    assert pose_packet["schema_version"] == "public-benchmark-pose-validity-packet.v1"
    check_ids = {row["check_id"] for row in pose_packet["checks"]}
    assert {
        "coordinate_finiteness",
        "atom_count_and_order_contract",
        "pose_success_metric_contract",
        "symmetry_permutation_contract",
        "symmetry_aware_ligand_rmsd_angstrom",
        "minimum_interatomic_distance_guard",
        "receptor_ligand_context_present",
    } <= check_ids
    assert pose_packet["real_benchmark_case_count"] == 0
    assert pose_packet["validator"]["required_pose_fields"] == [
        "case_id",
        "pose_success_metric",
        "benchmark_split",
        "reference_atoms",
        "predicted_atoms",
        "ligand_atom_order_contract",
        "symmetry_permutation_contract",
        "protein_structure_path",
        "receptor_context",
    ]
    assert (
        "materialize_public_benchmark_pose_validity_input.py"
        in pose_packet["validator"]["materialization_command"]
    )
    assert pose_packet["materializer"]["schema_version"] == (
        "public-benchmark-posebusters-style-validity-packet-materialization.v1"
    )
    assert (
        "materialize_public_benchmark_posebusters_validity_packet.py"
        in pose_packet["materializer"]["materialization_command"]
    )
    assert (
        "scripts/materialize_public_benchmark_pose_validity_input.py"
        in pose_packet["input_checksums"]
    )
    assert (
        "scripts/materialize_public_benchmark_posebusters_validity_packet.py"
        in pose_packet["input_checksums"]
    )
    assert pose_packet["dry_run_validation"]["pose_validity_ready"] is True
    assert pose_packet["dry_run_validation"]["dry_run_case_count"] == 1
    assert pose_packet["dry_run_validation"]["real_benchmark_case_count"] == 0
    assert pose_packet["dry_run_validation"]["blockers"] == []
    assert (
        pose_packet["dry_run_validation"]["rows"][0]["benchmark_split"]
        == "synthetic-dry-run"
    )

    assert rmsd["schema_version"] == "public-benchmark-symmetry-rmsd-scorecard.v1"
    assert rmsd["contract_pass"] is True
    assert rmsd["real_benchmark_case_count"] == 0
    assert rmsd["materializer"]["schema_version"] == (
        "public-benchmark-rmsd-scorecard-materialization.v1"
    )
    assert (
        "materialize_public_benchmark_rmsd_scorecard.py"
        in rmsd["materializer"]["materialization_command"]
    )
    assert (
        "scripts/materialize_public_benchmark_rmsd_scorecard.py"
        in rmsd["input_checksums"]
    )
    score = rmsd["rows"][0]["score"]
    assert rmsd["rows"][0]["benchmark_split"] == "synthetic-dry-run"
    assert score["best_permutation"] == [0, 2, 1, 3]
    assert score["pose_success"] is True
    assert score["best_rmsd_angstrom"] < 1.0e-12
    assert pose_harness["schema_version"] == "public-benchmark-pose-success-harness.v1"
    assert pose_harness["contract_pass"] is True
    assert pose_harness["pose_success_harness_ready"] is False
    assert pose_harness["real_benchmark_case_count"] == 0
    assert pose_harness["dry_run_case_count"] == 1
    assert pose_harness["pose_success_count"] == 1
    assert pose_harness["blockers"] == [
        "public_benchmark_pose_success_harness_rows_missing"
    ]
    assert pose_harness["materializer"]["schema_version"] == (
        "public-benchmark-pose-success-harness-materialization.v1"
    )
    assert (
        "materialize_public_benchmark_pose_success_harness.py"
        in pose_harness["materializer"]["materialization_command"]
    )

    assert enrichment["schema_version"] == "public-benchmark-enrichment-scorecard.v1"
    assert enrichment["status"] == "operator_evidence_required"
    assert enrichment["contract_pass"] is False
    assert enrichment["public_benchmark_enrichment_ready"] is False
    assert enrichment["real_enrichment_target_count"] == 0
    assert enrichment["benchmark_family_target_counts"] == {}
    assert enrichment["target_rows"] == []
    assert enrichment["summary"]["missing_supported_families"] == ["DUD-E", "LIT-PCBA"]
    assert enrichment["materializer"]["schema_version"] == (
        "public-benchmark-enrichment-materialization.v1"
    )
    assert enrichment["materializer"]["family_coverage_fields"] == [
        "benchmark_family_target_counts",
        "covered_supported_family_count",
        "missing_supported_families",
    ]
    assert enrichment["materializer"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert (
        "materialize_public_benchmark_enrichment_scorecard.py"
        in enrichment["materializer"]["materialization_command"]
    )
    assert (
        "scripts/materialize_public_benchmark_enrichment_scorecard.py"
        in enrichment["input_checksums"]
    )

    assert vina_gnina["schema_version"] == (
        "public-benchmark-vina-gnina-comparison-adapter.v1"
    )
    assert vina_gnina["status"] == "operator_evidence_required"
    assert vina_gnina["contract_pass"] is False
    assert vina_gnina["public_benchmark_engine_comparison_ready"] is False
    assert vina_gnina["real_comparison_case_count"] == 0
    assert vina_gnina["supported_engines"] == ["vina", "gnina"]
    assert vina_gnina["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert vina_gnina["benchmark_split_counts"] == {}
    assert vina_gnina["materializer"]["schema_version"] == (
        "public-benchmark-vina-gnina-comparison-materialization.v1"
    )
    assert "benchmark_split" in vina_gnina["materializer"]["required_case_fields"]
    assert vina_gnina["materializer"]["template"]["cases"][0]["benchmark_split"] == (
        "CASF-core"
    )
    assert vina_gnina["materializer"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert (
        "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
        in vina_gnina["materializer"]["materialization_command"]
    )
    assert (
        "scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"
        in vina_gnina["input_checksums"]
    )


def test_public_benchmark_source_of_truth_ready_is_derived_from_gate() -> None:
    artifacts = module.build_public_benchmark_artifacts(repo_root=REPO_ROOT)
    subset = copy.deepcopy(artifacts["subset_manifest"])
    pose_packet = copy.deepcopy(artifacts["pose_validity_packet"])
    rmsd = copy.deepcopy(artifacts["rmsd_scorecard"])
    pose_harness = copy.deepcopy(artifacts["pose_success_harness"])
    enrichment = copy.deepcopy(artifacts["enrichment_scorecard"])
    vina_gnina = copy.deepcopy(artifacts["vina_gnina_comparison_adapter"])
    external_receipts = copy.deepcopy(artifacts["external_receipts_validation"])

    checksum = "sha256:" + "a" * 64
    subset["target_subset_case_count"] = 1
    subset["materialized_case_count"] = 1
    subset["blockers"] = []
    subset["case_rows"] = [
        {
            "case_id": "case_a",
            "source_family": "CASF/PDBBind",
            "benchmark_split": "CASF-core",
            "complex_id": "1abc",
            "protein_structure_path": "benchmarks/case_a/protein.pdb",
            "reference_ligand_path": "benchmarks/case_a/ref.sdf",
            "predicted_ligand_path_or_docking_run_id": "benchmarks/case_a/pred.sdf",
            "ligand_atom_order_contract": {
                "atom_count": 2,
                "atom_ids": ["C1", "O1"],
            },
            "symmetry_permutation_contract": {"permutations": [[0, 1]]},
            "source_license_or_accession": "PDBBind:1abc",
            "source_checksum": checksum,
            "source_file_checksums": {
                "benchmarks/case_a/protein.pdb": checksum,
                "benchmarks/case_a/ref.sdf": checksum,
                "benchmarks/case_a/pred.sdf": checksum,
            },
            "provenance_ref": "operator://casf-pdbbind/case_a",
            "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
            "rmsd_threshold_angstrom": 2.0,
        }
    ]
    pose_packet["dry_run_validation"]["real_benchmark_case_count"] = 1
    rmsd["real_benchmark_case_count"] = 1
    rmsd["rows"][0]["source_family"] = "CASF/PDBBind"
    pose_harness.update(
        {
            "status": "ready",
            "pose_success_harness_ready": True,
            "contract_pass": True,
            "real_benchmark_case_count": 1,
            "dry_run_case_count": 0,
            "blockers": [],
        }
    )
    pose_harness["case_rows"][0]["source_family"] = "CASF/PDBBind"
    pose_harness["case_rows"][0]["benchmark_split"] = "CASF-core"
    enrichment.update(
        {
            "status": "ready",
            "contract_pass": True,
            "public_benchmark_enrichment_ready": True,
            "real_enrichment_target_count": 1,
            "blockers": [],
        }
    )
    vina_gnina.update(
        {
            "status": "ready",
            "contract_pass": True,
            "public_benchmark_engine_comparison_ready": True,
            "real_comparison_case_count": 1,
            "blockers": [],
        }
    )
    external_receipts.update(
        {
            "status": "ready",
            "public_benchmark_external_receipts_ready": True,
            "materialized_row_count": 3,
            "receipt_complete_row_count": 3,
            "receipt_blocked_row_count": 0,
            "receipt_coverage": {
                "expected_artifact_roles": [
                    "casf_pdbbind_subset_manifest",
                    "dud_e_lit_pcba_enrichment_scorecard",
                    "vina_gnina_comparison_adapter",
                ],
                "expected_artifact_role_count": 3,
                "materialized_artifact_role_count": 3,
                "receipt_complete_artifact_role_count": 3,
                "missing_expected_artifact_role_count": 0,
                "missing_expected_artifact_roles": [],
                "role_summaries": [],
            },
            "receipt_rows": [],
            "blockers": [],
        }
    )

    source = module.build_source_of_truth(
        subset_manifest=subset,
        pose_validity_packet=pose_packet,
        rmsd_scorecard=rmsd,
        pose_success_harness=pose_harness,
        enrichment_scorecard=enrichment,
        vina_gnina_comparison_adapter=vina_gnina,
        external_receipts_validation=external_receipts,
        operator_intake_packet=artifacts["operator_intake_packet"],
        repo_root=REPO_ROOT,
    )

    assert source["status"] == "ready"
    assert source["tier_beta_gate"]["status"] == "ready"
    assert source["tier_beta_gate"]["failed_criterion_count"] == 0
    assert source["tier_beta_gate"]["failed_criteria"] == []
    assert source["tier_beta_ready"] is True
    assert source["public_benchmark_ready"] is True
    assert source["blockers"] == []
    assert source["blocker_count"] == 0
    assert source["first_blocker"] == ""
    assert source["blocked_operator_slot_count"] == 0
    assert source["operator_handoff_queue_count"] == 0
    assert source["materialization_progress"]["blocked_slice_count"] == 0
    assert source["materialization_progress"]["next_unblock_slice_id"] == ""
    assert source["subset_manifest_validation"]["public_benchmark_ready"] is True
    assert source["subset_manifest_summary"]["source_material_coverage"][
        "source_file_checksum_case_count"
    ] == 1
    assert "READY" in source["summary_line"]


def test_public_benchmark_builder_writes_all_artifacts(tmp_path: Path) -> None:
    source_out = tmp_path / "public_benchmark_source_of_truth.json"
    subset_out = tmp_path / "public_benchmark_subset_manifest.json"
    pose_out = tmp_path / "public_benchmark_pose_validity_packet.json"
    rmsd_out = tmp_path / "public_benchmark_symmetry_rmsd_scorecard.json"
    pose_harness_out = tmp_path / "public_benchmark_pose_success_harness.json"
    enrichment_out = tmp_path / "public_benchmark_enrichment_scorecard.json"
    vina_gnina_out = tmp_path / "public_benchmark_vina_gnina_comparison_adapter.json"
    operator_out = tmp_path / "public_benchmark_operator_intake_packet.json"
    operator_md_out = tmp_path / "public_benchmark_operator_intake_packet.md"
    operator_template_dir = tmp_path / "templates"

    artifacts = module.write_public_benchmark_artifacts(
        repo_root=REPO_ROOT,
        source_of_truth_out=source_out,
        subset_manifest_out=subset_out,
        pose_validity_packet_out=pose_out,
        rmsd_scorecard_out=rmsd_out,
        pose_success_harness_out=pose_harness_out,
        enrichment_scorecard_out=enrichment_out,
        vina_gnina_comparison_adapter_out=vina_gnina_out,
        operator_intake_packet_out=operator_out,
        operator_intake_packet_md_out=operator_md_out,
        operator_template_dir=operator_template_dir,
    )

    assert source_out.exists()
    assert subset_out.exists()
    assert pose_out.exists()
    assert rmsd_out.exists()
    assert pose_harness_out.exists()
    assert enrichment_out.exists()
    assert vina_gnina_out.exists()
    assert operator_out.exists()
    assert operator_md_out.exists()
    assert (operator_template_dir / "public_benchmark_casf_pdbbind_operator_template.json").exists()
    assert (
        json.loads(source_out.read_text(encoding="utf-8"))
        == artifacts["source_of_truth"]
    )
    assert (
        json.loads(subset_out.read_text(encoding="utf-8"))
        == artifacts["subset_manifest"]
    )
    assert (
        json.loads(pose_out.read_text(encoding="utf-8"))
        == artifacts["pose_validity_packet"]
    )
    assert (
        json.loads(rmsd_out.read_text(encoding="utf-8")) == artifacts["rmsd_scorecard"]
    )
    assert (
        json.loads(pose_harness_out.read_text(encoding="utf-8"))
        == artifacts["pose_success_harness"]
    )
    assert (
        json.loads(enrichment_out.read_text(encoding="utf-8"))
        == artifacts["enrichment_scorecard"]
    )
    assert (
        json.loads(vina_gnina_out.read_text(encoding="utf-8"))
        == artifacts["vina_gnina_comparison_adapter"]
    )
    assert (
        json.loads(operator_out.read_text(encoding="utf-8"))
        == artifacts["operator_intake_packet"]
    )
    assert "# Public Benchmark Operator Intake Packet" in operator_md_out.read_text(
        encoding="utf-8"
    )
    operator_template = json.loads(
        (
            operator_template_dir
            / "public_benchmark_casf_pdbbind_operator_template.json"
        ).read_text(encoding="utf-8")
    )
    assert operator_template["schema_version"] == "public-benchmark-operator-template.v1"
    assert operator_template["operator_values_filled"] is False
