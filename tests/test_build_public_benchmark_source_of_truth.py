from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_public_benchmark_source_of_truth.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_public_benchmark_source_of_truth", SCRIPT_PATH)
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

    assert source["schema_version"] == "public-benchmark-source-of-truth.v1"
    assert source["contract_pass"] is True
    assert source["tier_beta_ready"] is False
    assert source["public_benchmark_ready"] is False
    assert source["subset_manifest_summary"] == {
        "target_subset_case_count": 12,
        "materialized_case_count": 0,
        "blockers": [
            "casf_pdbbind_source_material_not_attached",
            "casf_pdbbind_case_checksums_missing",
            "casf_pdbbind_ligand_symmetry_contracts_missing",
        ],
    }
    assert source["symmetry_rmsd_summary"] == {
        "status": "ready",
        "dry_run_case_count": 1,
        "real_benchmark_case_count": 0,
        "dry_run_pose_success": True,
    }
    assert source["pose_validity_packet_summary"] == {
        "status": "ready_for_dry_run",
        "check_count": 6,
        "required_check_count": 6,
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
    assert source["subset_materializer"] == {
        "schema_version": "public-benchmark-subset-materialization.v1",
        "status": "ready_for_operator_intake",
        "intake_case_key": "cases",
        "required_case_fields": [
            "case_id",
            "source_family",
            "complex_id",
            "protein_structure_path",
            "reference_ligand_path",
            "predicted_ligand_path_or_docking_run_id",
            "ligand_atom_order_contract",
            "symmetry_permutation_contract",
            "source_license_or_accession",
            "source_checksum",
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
        "materialization_command": pose_packet["materializer"]["materialization_command"],
        "claim_boundary": (
            "The PoseBusters-style packet materializer consumes validated "
            "pose-coordinate input and emits per-case sanity-check rows for real "
            "benchmark ligands. It does not infer chemistry or close Tier beta."
        ),
    }
    assert source["next_actions"] == [
        "attach_checked_casf_pdbbind_subset_source_files",
        "run_public_benchmark_subset_materializer",
        "fill_ligand_atom_order_and_symmetry_permutation_contracts",
        "attach_public_benchmark_pose_coordinate_intake",
        "run_public_benchmark_pose_validity_materializer",
        "run_symmetry_aware_rmsd_on_real_subset",
        "run_public_benchmark_rmsd_scorecard_materializer",
        "materialize_posebusters_style_validity_packet_for_real_ligands",
    ]
    assert "Vina/GNINA comparison" in source["claim_boundary"]
    assert "DUD-E/LIT-PCBA enrichment" in source["claim_boundary"]

    assert subset["schema_version"] == "public-benchmark-subset-manifest.v1"
    assert subset["source_families"] == ["CASF/PDBBind"]
    assert subset["target_subset_case_count"] == 12
    assert subset["materialized_case_count"] == 0
    assert subset["case_rows"] == []
    assert subset["case_row_schema"]["required_fields"] == [
        "case_id",
        "source_family",
        "complex_id",
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
        "ligand_atom_order_contract",
        "symmetry_permutation_contract",
        "source_license_or_accession",
        "source_checksum",
    ]
    assert subset["case_row_schema"]["template"]["source_family"] == "CASF/PDBBind"
    assert "validate_public_benchmark_subset_manifest.py" in subset["case_row_schema"][
        "validation_command"
    ]
    assert "materialize_public_benchmark_subset_manifest.py" in subset["case_row_schema"][
        "materialization_command"
    ]
    assert "scripts/materialize_public_benchmark_subset_manifest.py" in subset[
        "input_checksums"
    ]
    assert {row["slot_id"] for row in subset["slots"]} == {
        "casf_pdbbind_pose_success_seed",
        "casf_pdbbind_affinity_control_seed",
    }
    assert all(row["status"] == "source_material_required" for row in subset["slots"])
    assert all("symmetry_permutation_contract" in row["required_fields"] for row in subset["slots"])

    assert pose_packet["schema_version"] == "public-benchmark-pose-validity-packet.v1"
    check_ids = {row["check_id"] for row in pose_packet["checks"]}
    assert {
        "coordinate_finiteness",
        "atom_count_and_order_contract",
        "symmetry_permutation_contract",
        "symmetry_aware_ligand_rmsd_angstrom",
        "minimum_interatomic_distance_guard",
        "receptor_ligand_context_present",
    } <= check_ids
    assert pose_packet["real_benchmark_case_count"] == 0
    assert pose_packet["validator"]["required_pose_fields"] == [
        "case_id",
        "reference_atoms",
        "predicted_atoms",
        "ligand_atom_order_contract",
        "symmetry_permutation_contract",
        "protein_structure_path",
        "receptor_context",
    ]
    assert "materialize_public_benchmark_pose_validity_input.py" in pose_packet[
        "validator"
    ]["materialization_command"]
    assert pose_packet["materializer"]["schema_version"] == (
        "public-benchmark-posebusters-style-validity-packet-materialization.v1"
    )
    assert "materialize_public_benchmark_posebusters_validity_packet.py" in pose_packet[
        "materializer"
    ]["materialization_command"]
    assert "scripts/materialize_public_benchmark_pose_validity_input.py" in pose_packet[
        "input_checksums"
    ]
    assert "scripts/materialize_public_benchmark_posebusters_validity_packet.py" in pose_packet[
        "input_checksums"
    ]
    assert pose_packet["dry_run_validation"]["pose_validity_ready"] is True
    assert pose_packet["dry_run_validation"]["dry_run_case_count"] == 1
    assert pose_packet["dry_run_validation"]["real_benchmark_case_count"] == 0
    assert pose_packet["dry_run_validation"]["blockers"] == []

    assert rmsd["schema_version"] == "public-benchmark-symmetry-rmsd-scorecard.v1"
    assert rmsd["contract_pass"] is True
    assert rmsd["real_benchmark_case_count"] == 0
    assert rmsd["materializer"]["schema_version"] == (
        "public-benchmark-rmsd-scorecard-materialization.v1"
    )
    assert "materialize_public_benchmark_rmsd_scorecard.py" in rmsd["materializer"][
        "materialization_command"
    ]
    assert "scripts/materialize_public_benchmark_rmsd_scorecard.py" in rmsd[
        "input_checksums"
    ]
    score = rmsd["rows"][0]["score"]
    assert score["best_permutation"] == [0, 2, 1, 3]
    assert score["pose_success"] is True
    assert score["best_rmsd_angstrom"] < 1.0e-12


def test_public_benchmark_builder_writes_all_artifacts(tmp_path: Path) -> None:
    source_out = tmp_path / "public_benchmark_source_of_truth.json"
    subset_out = tmp_path / "public_benchmark_subset_manifest.json"
    pose_out = tmp_path / "public_benchmark_pose_validity_packet.json"
    rmsd_out = tmp_path / "public_benchmark_symmetry_rmsd_scorecard.json"

    artifacts = module.write_public_benchmark_artifacts(
        repo_root=REPO_ROOT,
        source_of_truth_out=source_out,
        subset_manifest_out=subset_out,
        pose_validity_packet_out=pose_out,
        rmsd_scorecard_out=rmsd_out,
    )

    assert source_out.exists()
    assert subset_out.exists()
    assert pose_out.exists()
    assert rmsd_out.exists()
    assert json.loads(source_out.read_text(encoding="utf-8")) == artifacts["source_of_truth"]
    assert json.loads(subset_out.read_text(encoding="utf-8")) == artifacts["subset_manifest"]
    assert json.loads(pose_out.read_text(encoding="utf-8")) == artifacts["pose_validity_packet"]
    assert json.loads(rmsd_out.read_text(encoding="utf-8")) == artifacts["rmsd_scorecard"]
