from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_subset_manifest.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_subset_manifest", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


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


def _case_descriptor(root: Path, case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
        "complex_id": f"{case_id}_complex",
        **_write_case_files(root, case_id),
        "ligand_atom_order_contract": {
            "atom_count": 3,
            "atom_ids": ["C1", "O1", "O2"],
        },
        "symmetry_permutation_contract": {
            "permutations": [[0, 1, 2], [0, 2, 1]],
        },
        "source_license_or_accession": "operator-attached-casf-pdbbind-accession",
        "provenance_ref": f"operator://casf-pdbbind/{case_id}",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "rmsd_threshold_angstrom": 2.0,
    }


def test_materializer_builds_ready_subset_manifest_from_local_intake(tmp_path: Path) -> None:
    manifest = module.materialize_subset_manifest(
        {
            "target_subset_case_count": 1,
            "cases": [_case_descriptor(tmp_path, "case_a")],
        },
        repo_root=tmp_path,
    )

    assert manifest["schema_version"] == "public-benchmark-subset-manifest.v1"
    assert manifest["status"] == "ready"
    assert manifest["public_benchmark_ready"] is True
    assert manifest["blockers"] == []
    assert manifest["materialized_case_count"] == 1
    row = manifest["case_rows"][0]
    assert row["source_checksum"].startswith("sha256:")
    assert row["pose_success_metric"] == "symmetry_aware_ligand_rmsd_angstrom"
    assert row["rmsd_threshold_angstrom"] == 2.0
    assert len(row["source_file_checksums"]) == 3
    assert all(value.startswith("sha256:") for value in row["source_file_checksums"].values())
    report = manifest["materialization_report"]
    assert report["source_file_checksum_count"] == 3
    assert report["materialization_blocker_count"] == 0


def test_materializer_blocks_missing_local_pose_prediction(tmp_path: Path) -> None:
    case = _case_descriptor(tmp_path, "case_a")
    (tmp_path / case["predicted_ligand_path_or_docking_run_id"]).unlink()

    manifest = module.materialize_subset_manifest(
        {"target_subset_case_count": 1, "cases": [case]},
        repo_root=tmp_path,
    )

    assert manifest["public_benchmark_ready"] is False
    assert manifest["materialization_report"]["source_file_missing_count"] == 1
    assert manifest["blockers"] == [
        "case_row_0:source_file_checksums_incomplete",
        "case_row_0:source_file_checksum_for_predicted_ligand_path_or_docking_run_id_missing",
        "case_row_0:predicted_ligand_path_or_docking_run_id_local_file_missing"
    ]
    assert manifest["case_rows"][0]["materialization_blockers"] == [
        "case_row_0:predicted_ligand_path_or_docking_run_id_local_file_missing"
    ]


def test_materializer_blocks_missing_ligand_atom_ids(tmp_path: Path) -> None:
    case = _case_descriptor(tmp_path, "case_a")
    case["ligand_atom_order_contract"] = {
        "atom_count": 3,
        "atom_ids": [],
    }

    manifest = module.materialize_subset_manifest(
        {"target_subset_case_count": 1, "cases": [case]},
        repo_root=tmp_path,
    )

    assert manifest["public_benchmark_ready"] is False
    assert manifest["blockers"] == ["case_row_0:atom_ids_missing"]
    assert manifest["materialization_report"]["validation_blocker_count"] == 1
    assert manifest["materialization_report"]["materialization_blocker_count"] == 0


def test_materializer_blocks_invalid_declared_source_checksum(tmp_path: Path) -> None:
    case = _case_descriptor(tmp_path, "case_a")
    case["source_checksum"] = "sha256:not-a-real-digest"

    manifest = module.materialize_subset_manifest(
        {"target_subset_case_count": 1, "cases": [case]},
        repo_root=tmp_path,
    )

    assert manifest["public_benchmark_ready"] is False
    assert manifest["blockers"] == ["case_row_0:source_checksum_invalid"]
    assert manifest["materialization_report"]["validation_blocker_count"] == 1
    assert manifest["materialization_report"]["materialization_blocker_count"] == 0
    assert len(manifest["case_rows"][0]["source_file_checksums"]) == 3


def test_materializer_cli_writes_manifest_and_report(tmp_path: Path) -> None:
    intake = tmp_path / "intake.json"
    intake.write_text(
        json.dumps(
            {
                "target_subset_case_count": 1,
                "cases": [_case_descriptor(tmp_path, "case_a")],
            }
        ),
        encoding="utf-8",
    )
    out_manifest = tmp_path / "manifest.json"
    out_report = tmp_path / "materialization_report.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-manifest",
                str(out_manifest),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(tmp_path),
                "--fail-blocked",
            ]
        )
        == 0
    )

    manifest = json.loads(out_manifest.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert manifest["public_benchmark_ready"] is True
    assert report["public_benchmark_ready"] is True
