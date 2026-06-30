from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_public_benchmark_subset_manifest.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("validate_public_benchmark_subset_manifest", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _complete_row(case_id: str) -> dict[str, object]:
    source_checksum = "sha256:" + "a" * 64
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "complex_id": f"{case_id}_complex",
        "protein_structure_path": f"benchmarks/{case_id}/protein.pdb",
        "reference_ligand_path": f"benchmarks/{case_id}/ligand_ref.sdf",
        "predicted_ligand_path_or_docking_run_id": f"benchmarks/{case_id}/pose_pred.sdf",
        "ligand_atom_order_contract": {
            "atom_count": 3,
            "atom_ids": ["C1", "O1", "O2"],
        },
        "symmetry_permutation_contract": {
            "permutations": [[0, 1, 2], [0, 2, 1]],
        },
        "source_license_or_accession": "operator-attached-accession",
        "source_checksum": source_checksum,
        "provenance_ref": "operator://casf-pdbbind/case",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "rmsd_threshold_angstrom": 2.0,
        "source_file_checksums": {
            f"benchmarks/{case_id}/protein.pdb": "sha256:" + "b" * 64,
            f"benchmarks/{case_id}/ligand_ref.sdf": "sha256:" + "c" * 64,
            f"benchmarks/{case_id}/pose_pred.sdf": "sha256:" + "d" * 64,
        },
    }


def test_validate_empty_seed_manifest_stays_structurally_valid_but_not_ready() -> None:
    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 12,
            "case_rows": [],
        }
    )

    assert result["contract_pass"] is True
    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["materialized_case_count_below_target"]
    assert result["materialized_case_count"] == 0


def test_validate_complete_manifest_ready() -> None:
    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 2,
            "case_rows": [_complete_row("case_a"), _complete_row("case_b")],
        }
    )

    assert result["status"] == "ready"
    assert result["public_benchmark_ready"] is True
    assert result["blockers"] == []
    assert result["materialized_case_count"] == 2


def test_validate_manifest_requires_explicit_ligand_atom_ids() -> None:
    row = _complete_row("case_a")
    row["ligand_atom_order_contract"] = {
        "atom_count": 3,
        "atom_ids": [],
    }

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:atom_ids_missing"]


def test_validate_manifest_rejects_duplicate_ligand_atom_ids() -> None:
    row = _complete_row("case_a")
    row["ligand_atom_order_contract"] = {
        "atom_count": 3,
        "atom_ids": ["C1", "O1", "O1"],
    }

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:atom_ids_not_unique"]


def test_validate_manifest_rejects_invalid_source_checksum() -> None:
    row = _complete_row("case_a")
    row["source_checksum"] = "sha256:not-a-real-digest"

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:source_checksum_invalid"]


def test_validate_manifest_rejects_unsupported_benchmark_split() -> None:
    row = _complete_row("case_a")
    row["benchmark_split"] = "private_test_split"

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:unsupported_benchmark_split"]


def test_validate_manifest_requires_symmetry_aware_pose_success_metric() -> None:
    row = _complete_row("case_a")
    row["pose_success_metric"] = "raw_ligand_rmsd_angstrom"

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:pose_success_metric_invalid"]


def test_validate_manifest_rejects_nonpositive_rmsd_threshold() -> None:
    row = _complete_row("case_a")
    row["rmsd_threshold_angstrom"] = 0.0

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:rmsd_threshold_angstrom_invalid"]


def test_validate_manifest_requires_source_file_checksums() -> None:
    row = _complete_row("case_a")
    row["source_file_checksums"] = {}

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:source_file_checksums_missing"]


def test_validate_manifest_requires_checksum_for_each_declared_source_file() -> None:
    row = _complete_row("case_a")
    row["source_file_checksums"] = {
        "benchmarks/case_a/protein.pdb": "sha256:" + "b" * 64,
        "benchmarks/case_a/unrelated_pose.sdf": "sha256:" + "d" * 64,
        "benchmarks/case_a/ligand_ref.sdf": "sha256:" + "c" * 64,
    }

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == [
        "case_row_0:source_file_checksum_for_predicted_ligand_path_or_docking_run_id_missing"
    ]


def test_validate_manifest_requires_identity_symmetry_permutation() -> None:
    row = _complete_row("case_a")
    row["symmetry_permutation_contract"] = {
        "permutations": [[0, 2, 1]],
    }

    result = module.validate_subset_manifest(
        {
            "target_subset_case_count": 1,
            "case_rows": [row],
        }
    )

    assert result["public_benchmark_ready"] is False
    assert result["blockers"] == ["case_row_0:symmetry_identity_permutation_missing"]


def test_validate_manifest_cli_writes_result(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"target_subset_case_count": 1, "case_rows": [_complete_row("case_a")]}),
        encoding="utf-8",
    )
    out = tmp_path / "validation.json"

    assert module.main(["--manifest", str(manifest), "--out", str(out), "--fail-blocked"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["public_benchmark_ready"] is True
    assert payload["blocker_count"] == 0
