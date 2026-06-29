from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "score_symmetry_aware_ligand_rmsd.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("score_symmetry_aware_ligand_rmsd", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_symmetry_aware_rmsd_selects_lowest_permutation() -> None:
    reference = [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"x": 2.0, "y": 0.0, "z": 0.0},
        {"x": 0.0, "y": 1.0, "z": 0.0},
        {"x": 0.0, "y": 0.0, "z": 3.0},
    ]
    predicted = [
        {"x": 5.0, "y": -2.0, "z": 1.0},
        {"x": 5.0, "y": -1.0, "z": 1.0},
        {"x": 7.0, "y": -2.0, "z": 1.0},
        {"x": 5.0, "y": -2.0, "z": 4.0},
    ]

    score = module.score_symmetry_aware_rmsd(
        reference_atoms=reference,
        predicted_atoms=predicted,
        symmetry_permutations=[[0, 1, 2, 3], [0, 2, 1, 3]],
        threshold_angstrom=0.05,
    )

    identity = score["permutation_rows"][0]
    assert identity["permutation"] == [0, 1, 2, 3]
    assert identity["rmsd_angstrom"] > 0.5
    assert score["best_permutation"] == [0, 2, 1, 3]
    assert score["best_rmsd_angstrom"] < 1.0e-12
    assert score["pose_success"] is True


def test_symmetry_aware_rmsd_cli_writes_scorecard(tmp_path: Path) -> None:
    pose_input = tmp_path / "pose.json"
    pose_input.write_text(
        json.dumps(
            {
                "case_id": "symmetry_cli_fixture",
                "reference_atoms": [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                "predicted_atoms": [[9.0, 1.0, 0.0], [9.0, 2.0, 0.0], [11.0, 1.0, 0.0]],
                "symmetry_permutations": [[0, 1, 2], [0, 2, 1]],
                "rmsd_threshold_angstrom": 0.05,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "score.json"

    assert module.main(["--input", str(pose_input), "--out", str(out), "--fail-blocked"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["case_id"] == "symmetry_cli_fixture"
    assert payload["pose_success"] is True
    assert payload["source_commit_sha"]
    assert payload["input_checksums"][str(pose_input)].startswith("sha256:")
