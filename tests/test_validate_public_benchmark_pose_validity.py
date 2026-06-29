from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_public_benchmark_pose_validity.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("validate_public_benchmark_pose_validity", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _valid_pose_case(case_id: str = "dry_run_pose") -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "synthetic",
        "protein_structure_path": "synthetic://protein.pdb",
        "receptor_context": {"binding_site_frame": "synthetic_identity_frame"},
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
        "ligand_atom_order_contract": {
            "atom_count": 4,
            "atom_ids": ["C1", "O1", "O2", "N1"],
        },
        "symmetry_permutation_contract": {
            "permutations": [[0, 1, 2, 3], [0, 2, 1, 3]],
        },
        "rmsd_threshold_angstrom": 2.0,
    }


def test_pose_validity_validator_passes_synthetic_dry_run() -> None:
    result = module.validate_pose_validity_payload({"cases": [_valid_pose_case()]})

    assert result["status"] == "pass"
    assert result["pose_validity_ready"] is True
    assert result["dry_run_case_count"] == 1
    assert result["real_benchmark_case_count"] == 0
    assert result["blockers"] == []
    row = result["rows"][0]
    assert row["pass"] is True
    assert row["rmsd_score"]["best_permutation"] == [0, 2, 1, 3]


def test_pose_validity_validator_blocks_self_clash() -> None:
    case = _valid_pose_case("self_clash_pose")
    case["predicted_atoms"] = [
        {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 0.1, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 2.0, "y": 0.0, "z": 0.0},
        {"element": "N", "x": 0.0, "y": 0.0, "z": 3.0},
    ]

    result = module.validate_pose_validity_payload({"cases": [case]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert "self_clash_pose:minimum_interatomic_distance_guard_failed" in result["blockers"]


def test_pose_validity_validator_cli_writes_result(tmp_path: Path) -> None:
    pose_input = tmp_path / "pose_validity_input.json"
    pose_input.write_text(json.dumps({"cases": [_valid_pose_case()]}), encoding="utf-8")
    out = tmp_path / "pose_validity_result.json"

    assert module.main(["--input", str(pose_input), "--out", str(out), "--fail-blocked"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["pose_validity_ready"] is True
    assert payload["blocker_count"] == 0
