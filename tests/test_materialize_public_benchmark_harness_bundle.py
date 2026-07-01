from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_harness_bundle.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_harness_bundle",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

PHASE2_COMPONENT_IDS = {
    "casf_pdbbind_pose_success_harness",
    "symmetry_aware_ligand_rmsd",
    "posebusters_style_pose_validity",
    "vina_gnina_comparison_adapter",
    "dud_e_or_lit_pcba_enrichment",
}


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(*parts: str) -> str:
    return "https://zenodo.org/records/9753102/files/" + "/".join(parts)


def _write_case_files(root: Path, case_id: str) -> dict[str, str]:
    case_dir = root / "benchmarks" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "protein_structure_path": case_dir / "protein.pdb",
        "reference_ligand_path": case_dir / "ligand_ref.sdf",
        "predicted_ligand_path_or_docking_run_id": case_dir / "pose_pred.sdf",
    }
    for path in files.values():
        path.write_text(f"{case_id}:{path.name}\n", encoding="utf-8")
    return {key: path.relative_to(root).as_posix() for key, path in files.items()}


def _case_payload(root: Path, case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    ligand_contract = {
        "atom_count": 2,
        "atom_ids": ["C1", "O1"],
    }
    symmetry_contract = {"permutations": [[0, 1]]}
    reference_atoms = [
        {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.2, "y": 0.0, "z": 0.0},
    ]
    predicted_atoms = [
        {"element": "C", "x": 0.1, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.3, "y": 0.0, "z": 0.0},
    ]
    subset_case = {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "complex_id": f"{case_id}_complex",
        **_write_case_files(root, case_id),
        "ligand_atom_order_contract": ligand_contract,
        "symmetry_permutation_contract": symmetry_contract,
        "source_license_or_accession": f"PDBBind-CASF-2016-core:{case_id}",
        "source_checksum": _checksum(f"PDBBind-CASF-2016-core:{case_id}"),
        "provenance_ref": _provenance_ref(
            "public-benchmark",
            "casf-pdbbind",
            case_id,
        ),
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "rmsd_threshold_angstrom": 2.0,
    }
    pose_case = {
        "case_id": case_id,
        "benchmark_split": "CASF-core",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "reference_atoms": reference_atoms,
        "predicted_atoms": predicted_atoms,
        "ligand_atom_order_contract": ligand_contract,
        "symmetry_permutation_contract": symmetry_contract,
        "protein_structure_path": f"benchmarks/{case_id}/protein.pdb",
        "receptor_context": {
            "binding_site_frame": "operator_supplied_receptor_frame",
            "provenance_ref": _provenance_ref("public-benchmark", "pose", case_id),
        },
    }
    return subset_case, pose_case


def _bundle(root: Path, *, case_count: int = 12) -> dict[str, object]:
    case_ids = [f"case_{index:02d}" for index in range(1, case_count + 1)]
    case_payloads = [_case_payload(root, case_id) for case_id in case_ids]
    subset_cases = [subset_case for subset_case, _pose_case in case_payloads]
    pose_cases = [pose_case for _subset_case, pose_case in case_payloads]
    first_case_id = case_ids[0]
    return {
        "target_subset_case_count": case_count,
        "casf_pdbbind_subset_intake": {
            "target_subset_case_count": case_count,
            "cases": subset_cases,
        },
        "pose_coordinate_intake": {
            "cases": pose_cases
        },
        "dud_e_lit_pcba_enrichment_intake": {
            "targets": [
                {
                    "benchmark_family": "DUD-E",
                    "target_id": "AA2AR",
                    "score_direction": "higher_is_better",
                    "scored_molecules": [
                        {"molecule_id": "active_1", "is_active": True, "score": 0.9},
                        {"molecule_id": "decoy_1", "is_active": False, "score": 0.1},
                    ],
                    "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                    "source_checksum": _checksum("DUD-E:AA2AR:release-2015"),
                    "provenance_ref": _provenance_ref(
                        "public-benchmark",
                        "dud-e",
                        "AA2AR",
                    ),
                }
            ]
        },
        "vina_gnina_comparison_intake": {
            "cases": [
                {
                    "case_id": first_case_id,
                    "source_family": "CASF/PDBBind",
                    "benchmark_split": "CASF-core",
                    "complex_id": f"{first_case_id}_complex",
                    "reference_pose_id": f"{first_case_id}_reference",
                    "engine_runs": [
                        {
                            "engine_id": "vina",
                            "docking_run_id": f"{first_case_id}_vina",
                            "predicted_ligand_path_or_pose_ref": _provenance_ref(
                                "public-benchmark",
                                "vina-gnina",
                                first_case_id,
                                "vina.sdf",
                            ),
                            "symmetry_aware_rmsd_angstrom": 1.4,
                            "pose_success": True,
                            "score": -7.2,
                            "score_direction": "lower_is_better",
                        },
                        {
                            "engine_id": "gnina",
                            "docking_run_id": f"{first_case_id}_gnina",
                            "predicted_ligand_path_or_pose_ref": _provenance_ref(
                                "public-benchmark",
                                "vina-gnina",
                                first_case_id,
                                "gnina.sdf",
                            ),
                            "symmetry_aware_rmsd_angstrom": 1.6,
                            "pose_success": True,
                            "score": -7.8,
                            "score_direction": "lower_is_better",
                        },
                    ],
                    "source_license_or_accession": (
                        f"PDBBind-CASF-2016-core:{first_case_id}"
                    ),
                    "source_checksum": _checksum("vina-gnina-case-a"),
                    "provenance_ref": _provenance_ref(
                        "public-benchmark",
                        "vina-gnina",
                        first_case_id,
                    ),
                }
            ]
        },
    }


def test_public_benchmark_harness_bundle_materializes_tier_beta_ready_artifacts(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    payload = _bundle(tmp_path)
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    report = module.materialize_public_benchmark_harness_bundle(
        payload,
        repo_root=tmp_path,
        bundle_path=bundle_path,
        out_dir=tmp_path / "out",
    )

    assert report["schema_version"] == (
        "public-benchmark-harness-bundle-materialization.v1"
    )
    assert report["status"] == "ready"
    assert report["contract_pass"] is True
    assert report["public_benchmark_ready"] is True
    assert report["source_of_truth_public_benchmark_ready"] is True
    assert report["tier_beta_ready"] is True
    assert report["blockers"] == []
    assert (
        report["target_subset_case_count"]
        == module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
    )
    assert (
        report["materialized_subset_case_count"]
        == module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
    )
    assert (
        report["real_pose_success_harness_case_count"]
        == module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
    )
    assert report["real_enrichment_target_count"] == 1
    assert report["real_vina_gnina_comparison_case_count"] == 1
    assert report["tier_beta_gate"]["failed_criteria"] == []
    assert report["phase2_ready"] is True
    assert report["phase2_ready_component_count"] == report["phase2_exit_gate"][
        "required_component_count"
    ]
    assert report["phase2_blocked_component_count"] == 0
    assert report["phase2_exit_gate"]["failed_criteria"] == []
    assert report["phase2_exit_gate"]["status"] == "ready"
    assert module.build_phase2_exit_gate(report["phase2_requirements"])["status"] == (
        "ready"
    )
    assert {row["component_id"] for row in report["required_components"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert {row["component_id"] for row in report["components"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert {row["component_id"] for row in report["phase2_requirements"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert report["phase2_requirement_summary"] == {
        "required_component_count": 5,
        "ready_component_count": 5,
        "blocked_component_count": 0,
        "materialized_component_count": 5,
        "operator_evidence_required_count": 0,
        "missing_row_input_count": 0,
        "missing_row_inputs": [],
        "phase2_ready": True,
        "blocked_component_ids": [],
    }
    assert all(row["ready"] for row in report["components"])
    assert all(row["ready"] for row in report["phase2_requirements"])
    assert report["ready_artifact_count"] == len(report["artifact_summaries"])
    for artifact in report["artifact_outputs"].values():
        assert (tmp_path / artifact).exists()


def test_public_benchmark_harness_bundle_blocks_duplicate_manual_bundle_rows(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    payload = _bundle(tmp_path)
    enrichment_targets = payload["dud_e_lit_pcba_enrichment_intake"]["targets"]
    assert isinstance(enrichment_targets, list)
    first_target = enrichment_targets[0]
    assert isinstance(first_target, dict)
    scored_molecules = first_target["scored_molecules"]
    assert isinstance(scored_molecules, list)
    scored_molecules[1]["molecule_id"] = scored_molecules[0]["molecule_id"]
    comparison_cases = payload["vina_gnina_comparison_intake"]["cases"]
    assert isinstance(comparison_cases, list)
    comparison_case = comparison_cases[0]
    assert isinstance(comparison_case, dict)
    engine_runs = comparison_case["engine_runs"]
    assert isinstance(engine_runs, list)
    engine_runs[1]["engine_id"] = engine_runs[0]["engine_id"]
    engine_runs[1]["docking_run_id"] = engine_runs[0]["docking_run_id"]
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    report = module.materialize_public_benchmark_harness_bundle(
        payload,
        repo_root=tmp_path,
        bundle_path=bundle_path,
        out_dir=tmp_path / "out",
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["public_benchmark_ready"] is False
    assert "enrichment_scorecard:AA2AR:molecule_1:molecule_id_duplicate:active_1" in report[
        "blockers"
    ]
    assert (
        "vina_gnina_comparison_adapter:case_01:engine_run_1:"
        "engine_id_duplicate:vina"
    ) in report["blockers"]
    assert (
        "vina_gnina_comparison_adapter:case_01:engine_run_1:"
        "docking_run_id_duplicate:case_01_vina"
    ) in report["blockers"]
    components = {row["component_id"]: row for row in report["components"]}
    assert components["dud_e_or_lit_pcba_enrichment"]["ready"] is False
    assert components["vina_gnina_comparison_adapter"]["ready"] is False


def test_public_benchmark_harness_bundle_blocks_duplicate_pose_case_rows(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    payload = _bundle(tmp_path)
    pose_cases = payload["pose_coordinate_intake"]["cases"]
    assert isinstance(pose_cases, list)
    pose_cases[1]["case_id"] = pose_cases[0]["case_id"]
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    report = module.materialize_public_benchmark_harness_bundle(
        payload,
        repo_root=tmp_path,
        bundle_path=bundle_path,
        out_dir=tmp_path / "out",
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["public_benchmark_ready"] is False
    assert "pose_validity_input:case_01:case_id_duplicate:row_1" in report[
        "blockers"
    ]
    components = {row["component_id"]: row for row in report["components"]}
    assert components["casf_pdbbind_pose_success_harness"]["ready"] is False
    assert components["symmetry_aware_ligand_rmsd"]["ready"] is False
    assert components["posebusters_style_pose_validity"]["ready"] is False


def test_public_benchmark_harness_bundle_blocks_one_case_smoke_as_phase2_ready(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    payload = _bundle(tmp_path, case_count=1)
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    report = module.materialize_public_benchmark_harness_bundle(
        payload,
        repo_root=tmp_path,
        bundle_path=bundle_path,
        out_dir=tmp_path / "out",
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["public_benchmark_ready"] is False
    assert report["source_of_truth_public_benchmark_ready"] is True
    assert report["tier_beta_ready"] is False
    assert report["target_subset_case_count"] == 1
    assert report["materialized_subset_case_count"] == 1
    assert report["real_pose_success_harness_case_count"] == 1
    assert report["phase2_ready"] is False
    assert report["phase2_blocked_component_count"] == 3
    assert report["phase2_requirement_summary"]["ready_component_count"] == 2
    assert report["phase2_requirement_summary"]["blocked_component_count"] == 3
    assert report["phase2_requirement_summary"]["blocked_component_ids"] == [
        "casf_pdbbind_pose_success_harness",
        "symmetry_aware_ligand_rmsd",
        "posebusters_style_pose_validity",
    ]
    assert report["phase2_exit_gate"]["failed_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready",
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    ]
    blocked_by_component = {
        row["component_id"]: row
        for row in report["components"]
        if not row["ready"]
    }
    assert {
        component_id: row["contract_pass"]
        for component_id, row in blocked_by_component.items()
    } == {
        "casf_pdbbind_pose_success_harness": False,
        "symmetry_aware_ligand_rmsd": False,
        "posebusters_style_pose_validity": False,
    }
    assert {
        component_id: row["source_artifact_contract_pass"]
        for component_id, row in blocked_by_component.items()
    } == {
        "casf_pdbbind_pose_success_harness": True,
        "symmetry_aware_ligand_rmsd": True,
        "posebusters_style_pose_validity": True,
    }
    assert {
        component_id: row["status"]
        for component_id, row in blocked_by_component.items()
    } == {
        "casf_pdbbind_pose_success_harness": "phase2_count_incomplete",
        "symmetry_aware_ligand_rmsd": "phase2_count_incomplete",
        "posebusters_style_pose_validity": "phase2_count_incomplete",
    }
    assert {
        row["component_id"]: row["required_minimum_count"]
        for row in report["components"]
    } == {
        "casf_pdbbind_pose_success_harness": (
            module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
        ),
        "symmetry_aware_ligand_rmsd": (
            module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
        ),
        "posebusters_style_pose_validity": (
            module.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
        ),
        "vina_gnina_comparison_adapter": 1,
        "dud_e_or_lit_pcba_enrichment": 1,
    }
    assert any(
        "real_benchmark_case_count_below_required:1<12" in blocker
        for blocker in report["blockers"]
    )


def test_public_benchmark_harness_bundle_blocks_empty_bundle(tmp_path: Path) -> None:
    report = module.materialize_public_benchmark_harness_bundle(
        {},
        repo_root=tmp_path,
        out_dir=tmp_path / "out",
        target_subset_case_count=1,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["tier_beta_ready"] is False
    assert report["blocked_artifact_count"] > 0
    assert report["blocker_count"] > 0
    assert report["phase2_ready"] is False
    assert report["phase2_exit_gate"]["status"] == "blocked"
    assert report["phase2_exit_gate"]["failed_criterion_count"] > 0
    assert report["phase2_blocked_component_count"] > 0
    assert {row["component_id"] for row in report["phase2_requirements"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert report["phase2_requirement_summary"]["required_component_count"] == 5
    assert report["phase2_requirement_summary"]["phase2_ready"] is False
    assert any("subset_manifest:" in blocker for blocker in report["blockers"])


def test_public_benchmark_harness_artifact_bundle_indexes_phase2_gate(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    payload = _bundle(tmp_path)
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    out_dir = tmp_path / "out"

    module.materialize_public_benchmark_harness_bundle(
        payload,
        repo_root=tmp_path,
        bundle_path=bundle_path,
        out_dir=out_dir,
    )
    artifact_paths = [
        out_dir / "public_benchmark_subset_manifest.json",
        out_dir / "public_benchmark_pose_validity_packet.json",
        out_dir / "public_benchmark_symmetry_rmsd_scorecard.json",
        out_dir / "public_benchmark_pose_success_harness.json",
        out_dir / "public_benchmark_enrichment_scorecard.json",
        out_dir / "public_benchmark_vina_gnina_comparison_adapter.json",
        out_dir / "public_benchmark_external_receipts_validation.json",
    ]

    bundle = module.materialize_public_benchmark_artifact_bundle(
        artifact_paths,
        repo_root=tmp_path,
    )

    assert bundle["schema_version"] == "public-benchmark-harness-bundle.v1"
    assert bundle["status"] == "ready"
    assert bundle["contract_pass"] is True
    assert bundle["phase2_ready"] is True
    assert bundle["phase2_exit_gate"]["status"] == "ready"
    assert bundle["phase2_exit_gate"]["failed_criteria"] == []
    assert {row["component_id"] for row in bundle["required_components"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert {row["component_id"] for row in bundle["components"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert {row["component_id"] for row in bundle["phase2_requirements"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert bundle["phase2_requirement_summary"]["ready_component_count"] == 5
    assert bundle["phase2_requirement_summary"]["blocked_component_count"] == 0
    assert all(row["ready"] for row in bundle["components"])


def test_public_benchmark_harness_bundle_cli_writes_report(tmp_path: Path) -> None:
    bundle_path = tmp_path / "operator_bundle.json"
    bundle_path.write_text(json.dumps(_bundle(tmp_path)), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_report = tmp_path / "bundle_report.json"

    assert (
        module.main(
            [
                "--bundle",
                str(bundle_path),
                "--repo-root",
                str(tmp_path),
                "--out-dir",
                str(out_dir),
                "--out-report",
                str(out_report),
                "--fail-blocked",
            ]
        )
        == 0
    )
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["tier_beta_ready"] is True
    assert report["phase2_ready"] is True
    assert report["phase2_exit_gate"]["status"] == "ready"
    assert (out_dir / "public_benchmark_source_of_truth.json").exists()
