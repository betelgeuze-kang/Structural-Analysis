from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_pose_validity_input.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_pose_validity_input", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _subset_manifest() -> dict[str, object]:
    return {
        "target_subset_case_count": 1,
        "case_rows": [
            {
                "case_id": "case_a",
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "complex_id": "case_a_complex",
                "protein_structure_path": "benchmarks/case_a/protein.pdb",
                "reference_ligand_path": "benchmarks/case_a/ligand_ref.sdf",
                "predicted_ligand_path_or_docking_run_id": "benchmarks/case_a/pose_pred.sdf",
                "ligand_atom_order_contract": {
                    "atom_count": 4,
                    "atom_ids": ["C1", "O1", "O2", "N1"],
                },
                "symmetry_permutation_contract": {
                    "permutations": [[0, 1, 2, 3], [0, 2, 1, 3]],
                },
                "source_license_or_accession": "operator-attached-accession",
                "source_checksum": "sha256:case-a",
                "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                "rmsd_threshold_angstrom": 2.0,
            }
        ],
    }


def _pose_case(case_id: str = "case_a") -> dict[str, object]:
    return {
        "case_id": case_id,
        "receptor_context": {"binding_site_frame": "operator_attached_frame"},
        "reference_atoms": [
            {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
            {"element": "O", "x": 2.0, "y": 0.0, "z": 0.0},
            {"element": "O", "x": 0.0, "y": 1.0, "z": 0.0},
            {"element": "N", "x": 0.0, "y": 0.0, "z": 3.0},
        ],
        "predicted_atoms": [
            {"element": "C", "x": 5.0, "y": -2.0, "z": 1.0},
            {"element": "O", "x": 5.0, "y": -1.0, "z": 1.0},
            {"element": "O", "x": 7.0, "y": -2.0, "z": 1.0},
            {"element": "N", "x": 5.0, "y": -2.0, "z": 4.0},
        ],
        "rmsd_threshold_angstrom": 2.0,
    }


def test_pose_validity_input_materializer_builds_ready_real_case() -> None:
    payload = module.materialize_pose_validity_input(
        _subset_manifest(),
        {"cases": [_pose_case()]},
        repo_root=REPO_ROOT,
    )

    assert payload["schema_version"] == "public-benchmark-pose-validity-input.v1"
    assert payload["status"] == "ready"
    assert payload["pose_validity_ready"] is True
    assert payload["real_benchmark_case_count"] == 1
    assert payload["real_pose_case_count"] == 1
    assert payload["materialization_report"]["real_benchmark_case_count"] == 1
    assert payload["materialization_report"]["real_pose_case_count"] == 1
    assert payload["blockers"] == []
    case = payload["cases"][0]
    assert case["source_family"] == "CASF/PDBBind"
    assert case["benchmark_split"] == "CASF-core"
    assert case["protein_structure_path"] == "benchmarks/case_a/protein.pdb"
    assert case["pose_success_metric"] == "symmetry_aware_ligand_rmsd_angstrom"
    assert case["rmsd_threshold_angstrom"] == 2.0
    assert case["ligand_atom_order_contract"]["atom_count"] == 4
    assert case["subset_manifest_case_checksum"] == "sha256:case-a"
    assert payload["validation"]["pose_validity_ready"] is True
    assert payload["validation"]["rows"][0]["rmsd_score"]["best_permutation"] == [0, 2, 1, 3]


def test_pose_validity_input_materializer_blocks_unknown_case_id() -> None:
    payload = module.materialize_pose_validity_input(
        _subset_manifest(),
        {"cases": [_pose_case("unknown_case")]},
        repo_root=REPO_ROOT,
    )

    assert payload["pose_validity_ready"] is False
    assert "unknown_case:case_id_not_in_subset_manifest" in payload["blockers"]
    assert "unknown_case:protein_structure_path_missing" in payload["blockers"]


def test_pose_validity_input_materializer_blocks_placeholder_source_family() -> None:
    subset = _subset_manifest()
    subset["case_rows"][0]["source_family"] = "fixture benchmark source"

    payload = module.materialize_pose_validity_input(
        subset,
        {"cases": [_pose_case()]},
        repo_root=REPO_ROOT,
    )

    assert payload["pose_validity_ready"] is False
    assert payload["real_benchmark_case_count"] == 0
    assert payload["real_pose_case_count"] == 0
    assert "case_a:source_family_placeholder" in payload["blockers"]


def test_pose_validity_input_materializer_cli_writes_input_and_report(
    tmp_path: Path,
) -> None:
    subset = tmp_path / "subset.json"
    subset.write_text(json.dumps(_subset_manifest()), encoding="utf-8")
    pose_intake = tmp_path / "pose_intake.json"
    pose_intake.write_text(json.dumps({"cases": [_pose_case()]}), encoding="utf-8")
    out_input = tmp_path / "pose_validity_input.json"
    out_report = tmp_path / "pose_validity_report.json"

    assert (
        module.main(
            [
                "--subset-manifest",
                str(subset),
                "--pose-intake",
                str(pose_intake),
                "--out-input",
                str(out_input),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    payload = json.loads(out_input.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert payload["pose_validity_ready"] is True
    assert report["pose_validity_ready"] is True
