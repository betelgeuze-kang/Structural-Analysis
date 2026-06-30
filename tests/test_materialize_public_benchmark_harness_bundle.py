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


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


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


def _bundle(root: Path) -> dict[str, object]:
    case_id = "case_a"
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
    return {
        "target_subset_case_count": 1,
        "casf_pdbbind_subset_intake": {
            "target_subset_case_count": 1,
            "cases": [
                {
                    "case_id": case_id,
                    "source_family": "CASF/PDBBind",
                    "benchmark_split": "CASF-core",
                    "complex_id": f"{case_id}_complex",
                    **_write_case_files(root, case_id),
                    "ligand_atom_order_contract": ligand_contract,
                    "symmetry_permutation_contract": symmetry_contract,
                    "source_license_or_accession": "CASF/PDBBind:test-accession",
                    "provenance_ref": f"operator://casf-pdbbind/{case_id}",
                    "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                    "rmsd_threshold_angstrom": 2.0,
                }
            ],
        },
        "pose_coordinate_intake": {
            "cases": [
                {
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
                        "provenance_ref": f"operator://pose/{case_id}",
                    },
                }
            ]
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
                    "source_license_or_accession": "DUD-E:AA2AR",
                    "source_checksum": _checksum("DUD-E:AA2AR"),
                    "provenance_ref": "operator://dud-e/AA2AR",
                }
            ]
        },
        "vina_gnina_comparison_intake": {
            "cases": [
                {
                    "case_id": case_id,
                    "source_family": "CASF/PDBBind",
                    "benchmark_split": "CASF-core",
                    "complex_id": f"{case_id}_complex",
                    "reference_pose_id": f"{case_id}_reference",
                    "engine_runs": [
                        {
                            "engine_id": "vina",
                            "docking_run_id": f"{case_id}_vina",
                            "predicted_ligand_path_or_pose_ref": "operator://vina.sdf",
                            "symmetry_aware_rmsd_angstrom": 1.4,
                            "pose_success": True,
                            "score": -7.2,
                            "score_direction": "lower_is_better",
                        },
                        {
                            "engine_id": "gnina",
                            "docking_run_id": f"{case_id}_gnina",
                            "predicted_ligand_path_or_pose_ref": "operator://gnina.sdf",
                            "symmetry_aware_rmsd_angstrom": 1.6,
                            "pose_success": True,
                            "score": -7.8,
                            "score_direction": "lower_is_better",
                        },
                    ],
                    "source_license_or_accession": "CASF/PDBBind:test-accession",
                    "source_checksum": _checksum("vina-gnina-case-a"),
                    "provenance_ref": f"operator://vina-gnina/{case_id}",
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
    assert report["tier_beta_ready"] is True
    assert report["blockers"] == []
    assert report["target_subset_case_count"] == 1
    assert report["materialized_subset_case_count"] == 1
    assert report["real_pose_success_harness_case_count"] == 1
    assert report["real_enrichment_target_count"] == 1
    assert report["real_vina_gnina_comparison_case_count"] == 1
    assert report["tier_beta_gate"]["failed_criteria"] == []
    assert report["phase2_ready"] is True
    assert report["phase2_ready_component_count"] == report["phase2_exit_gate"][
        "required_component_count"
    ]
    assert report["phase2_blocked_component_count"] == 0
    assert report["phase2_exit_gate"]["failed_criteria"] == []
    assert report["ready_artifact_count"] == len(report["artifact_summaries"])
    for artifact in report["artifact_outputs"].values():
        assert (tmp_path / artifact).exists()


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
    assert report["phase2_exit_gate"]["failed_criterion_count"] > 0
    assert report["phase2_blocked_component_count"] > 0
    assert any("subset_manifest:" in blocker for blocker in report["blockers"])


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
    assert (out_dir / "public_benchmark_source_of_truth.json").exists()
