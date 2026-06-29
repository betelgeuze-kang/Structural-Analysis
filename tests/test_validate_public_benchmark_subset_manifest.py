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
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
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
        "source_checksum": "sha256:abc123",
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
