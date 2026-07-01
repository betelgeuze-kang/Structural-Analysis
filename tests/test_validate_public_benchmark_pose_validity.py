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
        "benchmark_split": "synthetic-dry-run",
        "protein_structure_path": "synthetic://protein.pdb",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
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
    assert row["source_family"] == "synthetic"
    assert row["benchmark_split"] == "synthetic-dry-run"
    assert row["rmsd_score"]["best_permutation"] == [0, 2, 1, 3]


def test_pose_validity_validator_blocks_placeholder_source_family() -> None:
    case = _valid_pose_case("case_a")
    case["source_family"] = "fixture benchmark source"
    case["benchmark_split"] = "CASF-core"

    result = module.validate_pose_validity_payload({"cases": [case]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert result["dry_run_case_count"] == 1
    assert result["real_benchmark_case_count"] == 0
    assert "case_a:source_family_placeholder" in result["blockers"]


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


def test_pose_validity_validator_blocks_invalid_pose_success_metric() -> None:
    case = _valid_pose_case("wrong_metric_pose")
    case["pose_success_metric"] = "plain_ligand_rmsd_angstrom"

    result = module.validate_pose_validity_payload({"cases": [case]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert "wrong_metric_pose:pose_success_metric_invalid" in result["blockers"]


def test_pose_validity_validator_blocks_non_finite_rmsd_threshold() -> None:
    case = _valid_pose_case("bad_threshold_pose")
    case["rmsd_threshold_angstrom"] = float("nan")

    result = module.validate_pose_validity_payload({"cases": [case]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert "bad_threshold_pose:rmsd_threshold_angstrom_invalid" in result["blockers"]


def test_pose_validity_validator_blocks_duplicate_case_rows() -> None:
    case = _valid_pose_case("case_a")
    case["source_family"] = "CASF/PDBBind"
    case["benchmark_split"] = "CASF-core"

    result = module.validate_pose_validity_payload({"cases": [case, dict(case)]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert result["real_benchmark_case_count"] == 2
    assert result["unique_real_benchmark_case_count"] == 1
    assert result["row_integrity_policy"]["required_unique_row_keys"] == {
        "cases": ["case_id"]
    }
    assert "case_a:case_id_duplicate:row_1" in result["blockers"]


def test_pose_validity_validator_requires_benchmark_split() -> None:
    case = _valid_pose_case("missing_split_pose")
    case.pop("benchmark_split")

    result = module.validate_pose_validity_payload({"cases": [case]})

    assert result["status"] == "blocked"
    assert result["pose_validity_ready"] is False
    assert "missing_split_pose:benchmark_split_missing" in result["blockers"]


def test_pose_validity_validator_cli_writes_result(tmp_path: Path) -> None:
    pose_input = tmp_path / "pose_validity_input.json"
    pose_input.write_text(json.dumps({"cases": [_valid_pose_case()]}), encoding="utf-8")
    out = tmp_path / "pose_validity_result.json"

    assert module.main(["--input", str(pose_input), "--out", str(out), "--fail-blocked"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["pose_validity_ready"] is True
    assert payload["blocker_count"] == 0
