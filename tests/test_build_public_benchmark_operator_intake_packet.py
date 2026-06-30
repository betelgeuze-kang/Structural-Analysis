from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_public_benchmark_operator_intake_packet.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_operator_intake_packet",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _slot_by_id(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    slots = packet["input_slots"]
    assert isinstance(slots, list)
    return {
        str(slot["slot_id"]): slot
        for slot in slots
        if isinstance(slot, dict) and "slot_id" in slot
    }


def test_public_benchmark_operator_intake_packet_exposes_all_required_slots() -> None:
    packet = module.build_public_benchmark_operator_intake_packet(repo_root=REPO_ROOT)
    slots = _slot_by_id(packet)

    assert packet["schema_version"] == "public-benchmark-operator-intake-packet.v1"
    assert packet["status"] == "ready_for_operator_input"
    assert packet["contract_pass"] is True
    assert packet["read_model_ready"] is True
    assert packet["route"] == "/product/public-benchmark/operator-intake"
    assert packet["read_model"] == {
        "route": "/product/public-benchmark/operator-intake",
        "alternate_routes": ["/product/public-benchmark", "/product/capabilities"],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_operator_intake_packet.json"
        ),
        "mutation_allowed": False,
    }
    assert packet["public_benchmark_ready"] is False
    assert packet["tier_beta_ready"] is False
    assert packet["owner_input_required"] is True
    assert packet["first_blocked_target"] == "casf_pdbbind_subset_intake"
    assert packet["root_cause_tags"] == [
        "operator_source_material_required",
        "operator_receipts_required",
    ]
    assert packet["operator_evidence_gap_count"] == 4
    assert packet["first_operator_evidence_gap"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert packet["source_of_truth_status"] == "seed_ready_materialization_blocked"
    assert packet["source_of_truth_blockers"] == [
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
    detail_register = {
        row["slot_id"]: row for row in packet["source_of_truth_blocker_detail_register"]
    }
    assert packet["source_of_truth_blocker_detail_count"] == 4
    assert packet["source_of_truth_first_blocker_detail"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert packet["summary"]["source_of_truth_blocker_detail_count"] == 4
    assert detail_register["dud_e_lit_pcba_enrichment_intake"]["blockers"] == [
        "dud_e_lit_pcba_enrichment_targets_missing",
        "dud_e_lit_pcba_scored_molecules_missing",
        "dud_e_lit_pcba_active_decoy_labels_missing",
        "public_benchmark_external_receipts_missing",
    ]
    assert detail_register["vina_gnina_comparison_intake"]["blockers"] == [
        "vina_gnina_comparison_cases_missing",
        "vina_gnina_engine_runs_missing",
        "vina_gnina_external_receipts_missing",
        "public_benchmark_external_receipts_missing",
    ]
    assert packet["manifest_contract_count"] == 1
    assert packet["first_manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert packet["first_manifest_contract"]["produces"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_manifest.json"
    )
    assert packet["first_manifest_contract"]["target_subset_case_count"] == 12
    assert (
        packet["first_manifest_contract"]["checksum_policy"]["required_manifest_field"]
        == "source_file_checksums"
    )
    assert set(slots) == {
        "casf_pdbbind_subset_intake",
        "pose_coordinate_intake",
        "dud_e_lit_pcba_enrichment_intake",
        "vina_gnina_comparison_intake",
    }

    subset = slots["casf_pdbbind_subset_intake"]
    assert subset["required"] is True
    assert subset["required_fields"] == [
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
        "ligand_atom_order_contract.atom_count",
        "ligand_atom_order_contract.atom_ids",
        "symmetry_permutation_contract.permutations",
    ]
    assert (
        subset["template"]["cases"][0]["pose_success_metric"]
        == "symmetry_aware_ligand_rmsd_angstrom"
    )
    assert subset["template"]["cases"][0]["benchmark_split"] == "CASF-core"
    assert subset["template"]["cases"][0]["rmsd_threshold_angstrom"] == 2.0
    assert subset["local_source_file_fields"] == [
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
    ]
    assert subset["manifest_contract"]["contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert subset["manifest_contract"]["nested_contracts"][0]["field"] == (
        "benchmark_split"
    )
    assert subset["manifest_contract"]["nested_contracts"][0][
        "supported_values"
    ] == ["CASF-core", "PDBBind-core", "PDBBind-refined", "PDBBind-general"]
    assert subset["manifest_contract"]["nested_contracts"][1]["field"] == (
        "ligand_atom_order_contract"
    )
    assert subset["manifest_contract"]["nested_contracts"][2]["field"] == (
        "symmetry_permutation_contract"
    )
    assert (
        "materialize_public_benchmark_subset_manifest.py"
        in subset["materialization_command"]
    )
    assert subset["validation_command"] == subset["manifest_contract"][
        "validation_command"
    ]

    pose = slots["pose_coordinate_intake"]
    assert pose["depends_on"] == [
        "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json"
    ]
    assert "pose_success_metric" in pose["required_fields"]
    assert "benchmark_split" in pose["required_fields"]
    assert "reference_atoms" in pose["required_fields"]
    assert pose["template"]["cases"][0]["benchmark_split"] == "CASF-core"
    assert (
        pose["template"]["cases"][0]["pose_success_metric"]
        == "symmetry_aware_ligand_rmsd_angstrom"
    )
    assert pose["minimum_evidence"]["benchmark_split_source"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_manifest.json"
    )
    assert (
        "materialize_public_benchmark_pose_validity_input.py"
        in pose["materialization_command"]
    )
    assert "validate_public_benchmark_pose_validity.py" in pose["validation_command"]

    enrichment = slots["dud_e_lit_pcba_enrichment_intake"]
    assert enrichment["required_fields"] == [
        "benchmark_family",
        "target_id",
        "score_direction",
        "scored_molecules",
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
    ]
    assert packet["supported_enrichment_families"] == ["DUD-E", "LIT-PCBA"]
    assert packet["required_molecule_fields"] == ["molecule_id", "is_active", "score"]
    assert enrichment["minimum_evidence"]["family_coverage_fields"] == [
        "benchmark_family_target_counts",
        "covered_supported_family_count",
        "missing_supported_families",
    ]
    assert enrichment["minimum_evidence"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert (
        "materialize_public_benchmark_enrichment_scorecard.py"
        in enrichment["validation_command"]
    )
    assert enrichment["validation_command"] == enrichment["materialization_command"]

    comparison = slots["vina_gnina_comparison_intake"]
    assert comparison["depends_on"] == [
        "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json",
        "implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json",
    ]
    assert comparison["required_fields"] == [
        "case_id",
        "source_family",
        "benchmark_split",
        "complex_id",
        "reference_pose_id",
        "engine_runs",
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
    ]
    assert (
        "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
        in comparison["materialization_command"]
    )
    assert (
        "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
        in comparison["validation_command"]
    )
    assert comparison["validation_command"] == comparison["materialization_command"]
    assert packet["supported_comparison_engines"] == ["vina", "gnina"]
    assert "symmetry_aware_rmsd_angstrom" in packet["required_engine_run_fields"]
    assert comparison["template"]["cases"][0]["benchmark_split"] == "CASF-core"
    assert comparison["minimum_evidence"]["benchmark_split_source"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_manifest.json"
    )
    assert comparison["minimum_evidence"]["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert comparison["minimum_evidence"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert packet["gate_unblock_plan_count"] == 4
    assert packet["minimum_subset_case_count"] == 12
    assert packet["execution_preflight_checklist_count"] == len(
        packet["materialization_sequence"]
    )
    assert packet["first_execution_preflight_blocker"]["step_id"] == (
        "materialize_subset_manifest"
    )
    assert packet["first_execution_preflight_blocker"]["operator_slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert packet["first_execution_preflight_blocker"]["first_blocker"] == (
        "casf_pdbbind_source_material_not_attached"
    )
    execution = {
        row["step_id"]: row for row in packet["execution_preflight_checklist"]
    }
    assert execution["materialize_subset_manifest"]["current_ready"] is False
    assert execution["materialize_subset_manifest"]["dependency_ready"] is True
    assert execution["materialize_subset_manifest"]["current_artifact"][
        "ready_values"
    ] == {
        "public_benchmark_ready": False,
        "materialized_case_count": 0,
        "target_subset_case_count": 12,
    }
    assert execution["materialize_pose_validity_input"]["dependency_states"] == [
        {
            "artifact": (
                "implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_manifest.json"
            ),
            "ready": False,
        }
    ]
    assert execution["materialize_pose_validity_input"]["current_artifact"][
        "artifact_exists"
    ] is False
    assert execution["validate_external_receipts"]["first_blocker"] == (
        "public_benchmark_external_receipts_missing"
    )
    assert execution["validate_external_receipts"]["current_artifact"][
        "ready_values"
    ]["public_benchmark_external_receipts_ready"] is False
    assert packet["summary"]["first_blocked_target"] == "casf_pdbbind_subset_intake"
    assert packet["summary"]["operator_evidence_gap_count"] == 4
    assert packet["summary"]["first_manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert packet["summary"]["execution_preflight_checklist_count"] == len(
        packet["materialization_sequence"]
    )
    assert packet["summary"]["first_execution_preflight_step_id"] == (
        "materialize_subset_manifest"
    )
    assert packet["summary"]["first_execution_preflight_blocker"] == (
        "casf_pdbbind_source_material_not_attached"
    )
    gate_plan = {row["slot_id"]: row for row in packet["gate_unblock_plan"]}
    assert gate_plan["casf_pdbbind_subset_intake"]["unblocks_tier_beta_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert gate_plan["casf_pdbbind_subset_intake"]["manifest_contract_id"] == (
        "casf_pdbbind_subset_manifest_contract"
    )
    assert (
        gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"]["case_count"] == 12
    )
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "supported_benchmark_splits"
    ] == ["CASF-core", "PDBBind-core", "PDBBind-refined", "PDBBind-general"]
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "ligand_atom_order_contract_fields"
    ] == ["atom_count", "atom_ids"]
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "symmetry_permutation_contract_fields"
    ] == ["permutations"]
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "materialized_manifest_fields"
    ] == ["source_file_checksums"]
    assert gate_plan["pose_coordinate_intake"]["unblocks_tier_beta_criteria"] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "casf_pdbbind_pose_success_harness_ready",
    ]
    assert gate_plan["pose_coordinate_intake"]["materialization_steps"] == [
        "materialize_pose_validity_input",
        "materialize_posebusters_validity_packet",
        "materialize_symmetry_rmsd_scorecard",
        "materialize_pose_success_harness",
    ]
    assert gate_plan["dud_e_lit_pcba_enrichment_intake"]["minimum_evidence"][
        "supported_families"
    ] == ["DUD-E", "LIT-PCBA"]
    assert gate_plan["dud_e_lit_pcba_enrichment_intake"]["minimum_evidence"][
        "source_checksum_policy"
    ] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert gate_plan["vina_gnina_comparison_intake"]["minimum_evidence"][
        "required_engines"
    ] == ["vina", "gnina"]
    assert gate_plan["vina_gnina_comparison_intake"]["minimum_evidence"][
        "source_checksum_policy"
    ] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }

    gap_register = {
        row["slot_id"]: row for row in packet["operator_evidence_gap_register"]
    }
    assert gap_register["dud_e_lit_pcba_enrichment_intake"][
        "validation_command"
    ] == enrichment["validation_command"]
    assert gap_register["vina_gnina_comparison_intake"][
        "validation_command"
    ] == comparison["validation_command"]
    assert gap_register["vina_gnina_comparison_intake"]["depends_on"] == comparison[
        "depends_on"
    ]


def test_public_benchmark_operator_intake_packet_materialization_sequence_is_ordered() -> (
    None
):
    packet = module.build_public_benchmark_operator_intake_packet(repo_root=REPO_ROOT)
    steps = packet["materialization_sequence"]

    assert [step["step_id"] for step in steps] == [
        "materialize_subset_manifest",
        "materialize_pose_validity_input",
        "materialize_posebusters_validity_packet",
        "materialize_symmetry_rmsd_scorecard",
        "materialize_pose_success_harness",
        "materialize_enrichment_scorecard",
        "materialize_vina_gnina_comparison_adapter",
        "validate_external_receipts",
        "refresh_public_benchmark_source_of_truth",
    ]
    assert packet["acceptance_criteria"][-2:] == [
        "public_benchmark_external_receipts_validation.public_benchmark_external_receipts_ready == true",
        "public_benchmark_source_of_truth.public_benchmark_ready == true"
    ]
    assert (
        "public_benchmark_pose_validity_input.real_benchmark_case_count >= 12"
        in packet["acceptance_criteria"]
    )
    assert (
        "public_benchmark_pose_validity_packet.posebusters_validity_ready == true"
        in packet["acceptance_criteria"]
    )
    assert (
        "public_benchmark_symmetry_rmsd_scorecard.scorecard_ready == true"
        in packet["acceptance_criteria"]
    )
    assert (
        "public_benchmark_pose_success_harness.pose_success_harness_ready == true"
        in packet["acceptance_criteria"]
    )
    assert packet["linked_artifacts"]["pose_success_harness"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_pose_success_harness.json"
    )
    assert packet["next_actions"][0] == "fill_public_benchmark_operator_intake_packet"
    assert packet["next_actions"][-1] == "regenerate_goal_bottleneck_roadmap_surface"
    assert packet["linked_artifacts"]["source_of_truth"] == (
        "implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json"
    )
    assert packet["linked_artifacts"]["external_receipts_validation"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_external_receipts_validation.json"
    )
    assert packet["linked_artifacts"]["harness_bundle_report"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_harness_bundle_materialization_report.json"
    )
    assert packet["operator_bundle_materialization"]["schema_version"] == (
        "public-benchmark-harness-bundle-materialization.v1"
    )
    assert "materialize_public_benchmark_harness_bundle.py" in packet[
        "operator_bundle_materialization"
    ]["command"]
    assert packet["operator_bundle_materialization"]["produces"]["source_of_truth"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_of_truth.json"
    )
    assert packet["next_actions"][1] == (
        "run_public_benchmark_harness_bundle_materializer"
    )
    assert packet["operator_template_schema_version"] == (
        "public-benchmark-operator-template.v1"
    )
    assert packet["operator_template_artifact_count"] == 4
    assert packet["operator_template_artifacts"][
        "casf_pdbbind_subset_intake"
    ].endswith("public_benchmark_casf_pdbbind_operator_template.json")


def test_public_benchmark_operator_intake_packet_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "public_benchmark_operator_intake_packet.json"
    out_md = tmp_path / "public_benchmark_operator_intake_packet.md"
    template_dir = tmp_path / "templates"

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--out",
                str(out),
                "--out-md",
                str(out_md),
                "--operator-template-dir",
                str(template_dir),
            ]
        )
        == 0
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    template_path = template_dir / "public_benchmark_casf_pdbbind_operator_template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    assert payload["input_checksums"][
        "scripts/build_public_benchmark_operator_intake_packet.py"
    ].startswith("sha256:")
    assert payload["packet_id"] == "public_benchmark_operator_intake_packet"
    assert template["schema_version"] == "public-benchmark-operator-template.v1"
    assert template["status"] == "operator_template_seed"
    assert template["operator_values_filled"] is False
    assert "# Public Benchmark Operator Intake Packet" in markdown
    assert "materialize_subset_manifest" in markdown


def test_public_benchmark_execution_preflight_uses_canonical_ready_fields(
    tmp_path: Path,
) -> None:
    productization = tmp_path / "implementation/phase1/release_evidence/productization"
    productization.mkdir(parents=True)

    artifacts = {
        module.DEFAULT_SUBSET_MANIFEST: {
            "schema_version": "public-benchmark-subset-manifest.v1",
            "status": "ready",
            "public_benchmark_ready": True,
            "materialized_case_count": 12,
            "target_subset_case_count": 12,
            "blockers": [],
        },
        module.DEFAULT_POSE_VALIDITY_INPUT: {
            "schema_version": "public-benchmark-pose-validity-input.v1",
            "status": "ready",
            "pose_validity_ready": True,
            "real_benchmark_case_count": 12,
            "blockers": [],
        },
        module.DEFAULT_POSE_VALIDITY_PACKET: {
            "schema_version": "public-benchmark-pose-validity-packet.v1",
            "status": "posebusters_validity_materialization_required",
            "posebusters_validity_ready": False,
            "real_benchmark_case_count": 12,
            "blockers": [],
        },
        module.DEFAULT_RMSD_SCORECARD: {
            "schema_version": "public-benchmark-symmetry-rmsd-scorecard.v1",
            "status": "rmsd_materialization_required",
            "scorecard_ready": False,
            "real_benchmark_case_count": 12,
            "dry_run_case_count": 0,
            "blockers": [],
        },
        module.DEFAULT_POSE_SUCCESS_HARNESS: {
            "schema_version": "public-benchmark-pose-success-harness.v1",
            "status": "pose_success_harness_materialization_required",
            "pose_success_harness_ready": False,
            "real_benchmark_case_count": 12,
            "pose_success_count": 0,
            "blockers": [],
        },
    }
    for raw_path, payload in artifacts.items():
        path = tmp_path / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    rows = module._execution_preflight_checklist(
        repo_root=tmp_path,
        materialization_sequence=[
            {
                "step_id": "materialize_subset_manifest",
                "produces": str(module.DEFAULT_SUBSET_MANIFEST),
            },
            {
                "step_id": "materialize_pose_validity_input",
                "produces": str(module.DEFAULT_POSE_VALIDITY_INPUT),
            },
            {
                "step_id": "materialize_posebusters_validity_packet",
                "produces": str(module.DEFAULT_POSE_VALIDITY_PACKET),
            },
            {
                "step_id": "materialize_symmetry_rmsd_scorecard",
                "produces": str(module.DEFAULT_RMSD_SCORECARD),
            },
            {
                "step_id": "materialize_pose_success_harness",
                "produces": str(module.DEFAULT_POSE_SUCCESS_HARNESS),
            },
        ],
        slots=[
            {"slot_id": "casf_pdbbind_subset_intake"},
            {"slot_id": "pose_coordinate_intake"},
        ],
        source_blocker_detail_register=[],
    )
    by_step = {row["step_id"]: row for row in rows}

    assert by_step["materialize_pose_validity_input"]["current_ready"] is True
    assert by_step["materialize_pose_validity_input"]["current_artifact"][
        "ready_values"
    ] == {
        "pose_validity_ready": True,
        "real_benchmark_case_count": 12,
    }
    assert by_step["materialize_posebusters_validity_packet"]["current_ready"] is False
    assert by_step["materialize_symmetry_rmsd_scorecard"]["current_ready"] is False
    assert by_step["materialize_pose_success_harness"]["current_ready"] is False

    packet = artifacts[module.DEFAULT_POSE_VALIDITY_PACKET]
    packet["posebusters_validity_ready"] = True
    packet["status"] = "ready"
    (tmp_path / module.DEFAULT_POSE_VALIDITY_PACKET).write_text(
        json.dumps(packet),
        encoding="utf-8",
    )
    scorecard = artifacts[module.DEFAULT_RMSD_SCORECARD]
    scorecard["scorecard_ready"] = True
    scorecard["status"] = "ready"
    (tmp_path / module.DEFAULT_RMSD_SCORECARD).write_text(
        json.dumps(scorecard),
        encoding="utf-8",
    )
    harness = artifacts[module.DEFAULT_POSE_SUCCESS_HARNESS]
    harness["pose_success_harness_ready"] = True
    harness["status"] = "ready"
    harness["pose_success_count"] = 12
    (tmp_path / module.DEFAULT_POSE_SUCCESS_HARNESS).write_text(
        json.dumps(harness),
        encoding="utf-8",
    )

    rows = module._execution_preflight_checklist(
        repo_root=tmp_path,
        materialization_sequence=[
            {
                "step_id": "materialize_subset_manifest",
                "produces": str(module.DEFAULT_SUBSET_MANIFEST),
            },
            {
                "step_id": "materialize_pose_validity_input",
                "produces": str(module.DEFAULT_POSE_VALIDITY_INPUT),
            },
            {
                "step_id": "materialize_posebusters_validity_packet",
                "produces": str(module.DEFAULT_POSE_VALIDITY_PACKET),
            },
            {
                "step_id": "materialize_symmetry_rmsd_scorecard",
                "produces": str(module.DEFAULT_RMSD_SCORECARD),
            },
            {
                "step_id": "materialize_pose_success_harness",
                "produces": str(module.DEFAULT_POSE_SUCCESS_HARNESS),
            },
        ],
        slots=[
            {"slot_id": "casf_pdbbind_subset_intake"},
            {"slot_id": "pose_coordinate_intake"},
        ],
        source_blocker_detail_register=[],
    )
    by_step = {row["step_id"]: row for row in rows}

    assert by_step["materialize_posebusters_validity_packet"]["current_ready"] is True
    assert by_step["materialize_symmetry_rmsd_scorecard"]["current_ready"] is True
    assert by_step["materialize_pose_success_harness"]["current_ready"] is True
