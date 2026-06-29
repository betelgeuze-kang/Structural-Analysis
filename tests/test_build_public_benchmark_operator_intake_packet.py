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
    assert packet["source_of_truth_status"] == "seed_ready_materialization_blocked"
    assert packet["source_of_truth_blockers"] == [
        "casf_pdbbind_source_material_not_attached",
        "public_benchmark_real_pose_predictions_missing",
        "dud_e_lit_pcba_enrichment_rows_missing",
        "vina_gnina_comparison_rows_missing",
        "public_benchmark_external_receipts_missing",
    ]
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
        "complex_id",
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
        "ligand_atom_order_contract",
        "symmetry_permutation_contract",
        "source_license_or_accession",
        "source_checksum",
    ]
    assert subset["local_source_file_fields"] == [
        "protein_structure_path",
        "reference_ligand_path",
        "predicted_ligand_path_or_docking_run_id",
    ]
    assert "materialize_public_benchmark_subset_manifest.py" in subset["materialization_command"]

    pose = slots["pose_coordinate_intake"]
    assert pose["depends_on"] == [
        "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json"
    ]
    assert "reference_atoms" in pose["required_fields"]
    assert "materialize_public_benchmark_pose_validity_input.py" in pose["materialization_command"]

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

    comparison = slots["vina_gnina_comparison_intake"]
    assert comparison["depends_on"] == [
        "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json",
        "implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json",
    ]
    assert comparison["required_fields"] == [
        "case_id",
        "source_family",
        "complex_id",
        "reference_pose_id",
        "engine_runs",
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
    ]
    assert "materialize_public_benchmark_vina_gnina_comparison_adapter.py" in comparison[
        "materialization_command"
    ]
    assert packet["supported_comparison_engines"] == ["vina", "gnina"]
    assert "symmetry_aware_rmsd_angstrom" in packet["required_engine_run_fields"]
    assert packet["gate_unblock_plan_count"] == 4
    assert packet["minimum_subset_case_count"] == 12
    gate_plan = {row["slot_id"]: row for row in packet["gate_unblock_plan"]}
    assert gate_plan["casf_pdbbind_subset_intake"]["unblocks_tier_beta_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "case_count"
    ] == 12
    assert gate_plan["pose_coordinate_intake"]["unblocks_tier_beta_criteria"] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
    ]
    assert gate_plan["pose_coordinate_intake"]["materialization_steps"] == [
        "materialize_pose_validity_input",
        "materialize_posebusters_validity_packet",
        "materialize_symmetry_rmsd_scorecard",
    ]
    assert gate_plan["dud_e_lit_pcba_enrichment_intake"]["minimum_evidence"][
        "supported_families"
    ] == ["DUD-E", "LIT-PCBA"]
    assert gate_plan["vina_gnina_comparison_intake"]["minimum_evidence"][
        "required_engines"
    ] == ["vina", "gnina"]


def test_public_benchmark_operator_intake_packet_materialization_sequence_is_ordered() -> None:
    packet = module.build_public_benchmark_operator_intake_packet(repo_root=REPO_ROOT)
    steps = packet["materialization_sequence"]

    assert [step["step_id"] for step in steps] == [
        "materialize_subset_manifest",
        "materialize_pose_validity_input",
        "materialize_posebusters_validity_packet",
        "materialize_symmetry_rmsd_scorecard",
        "materialize_enrichment_scorecard",
        "materialize_vina_gnina_comparison_adapter",
        "refresh_public_benchmark_source_of_truth",
    ]
    assert packet["acceptance_criteria"][-1] == (
        "public_benchmark_source_of_truth.public_benchmark_ready == true"
    )
    assert packet["next_actions"][0] == "fill_public_benchmark_operator_intake_packet"
    assert packet["next_actions"][-1] == "regenerate_goal_bottleneck_roadmap_surface"
    assert packet["linked_artifacts"]["source_of_truth"] == (
        "implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json"
    )


def test_public_benchmark_operator_intake_packet_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "public_benchmark_operator_intake_packet.json"
    out_md = tmp_path / "public_benchmark_operator_intake_packet.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["input_checksums"][
        "scripts/build_public_benchmark_operator_intake_packet.py"
    ].startswith("sha256:")
    assert payload["packet_id"] == "public_benchmark_operator_intake_packet"
    assert "# Public Benchmark Operator Intake Packet" in markdown
    assert "materialize_subset_manifest" in markdown
