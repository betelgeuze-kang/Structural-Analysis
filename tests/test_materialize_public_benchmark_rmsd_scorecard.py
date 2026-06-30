from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_rmsd_scorecard.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_rmsd_scorecard", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _pose_case(case_id: str = "case_a", threshold: float = 2.0) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "protein_structure_path": "benchmarks/case_a/protein.pdb",
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
        "rmsd_threshold_angstrom": threshold,
        "subset_manifest_case_checksum": "sha256:case-a",
    }


def test_rmsd_scorecard_materializer_scores_real_pose_input() -> None:
    scorecard = module.materialize_rmsd_scorecard(
        {"pose_validity_ready": True, "cases": [_pose_case()]},
        repo_root=REPO_ROOT,
    )

    assert scorecard["schema_version"] == "public-benchmark-symmetry-rmsd-scorecard.v1"
    assert scorecard["status"] == "ready"
    assert scorecard["scorecard_ready"] is True
    assert scorecard["real_benchmark_case_count"] == 1
    assert scorecard["dry_run_case_count"] == 0
    assert scorecard["pose_success_count"] == 1
    assert scorecard["pose_failure_count"] == 0
    assert scorecard["pose_success_rate"] == 1.0
    row = scorecard["rows"][0]
    assert row["case_id"] == "case_a"
    assert row["benchmark_split"] == "CASF-core"
    assert row["score"]["best_permutation"] == [0, 2, 1, 3]
    assert row["score"]["pose_success"] is True


def test_rmsd_scorecard_materializer_records_pose_failure_without_blocking() -> None:
    scorecard = module.materialize_rmsd_scorecard(
        {"pose_validity_ready": True, "cases": [_pose_case(threshold=0.0)]},
        repo_root=REPO_ROOT,
    )

    assert scorecard["scorecard_ready"] is True
    assert scorecard["pose_success_count"] == 0
    assert scorecard["pose_failure_count"] == 1
    assert scorecard["blockers"] == []


def test_rmsd_scorecard_materializer_blocks_invalid_pose_validity_input() -> None:
    scorecard = module.materialize_rmsd_scorecard(
        {"pose_validity_ready": False, "cases": []},
        repo_root=REPO_ROOT,
    )

    assert scorecard["scorecard_ready"] is False
    assert scorecard["status"] == "rmsd_materialization_required"
    assert scorecard["blockers"] == [
        "pose_validity_input_cases_missing",
        "pose_validity_input_not_ready",
    ]


def test_rmsd_scorecard_materializer_blocks_dry_run_only_input() -> None:
    dry_run_case = _pose_case("dry_run_case")
    dry_run_case["source_family"] = "synthetic"

    scorecard = module.materialize_rmsd_scorecard(
        {"pose_validity_ready": True, "cases": [dry_run_case]},
        repo_root=REPO_ROOT,
    )

    assert scorecard["scorecard_ready"] is False
    assert scorecard["status"] == "rmsd_materialization_required"
    assert scorecard["real_benchmark_case_count"] == 0
    assert scorecard["dry_run_case_count"] == 1
    assert scorecard["blockers"] == ["real_benchmark_rmsd_cases_missing"]
    assert scorecard["materialization_report"]["scorecard_ready"] is False


def test_rmsd_scorecard_materializer_cli_writes_scorecard_and_report(
    tmp_path: Path,
) -> None:
    pose_input = tmp_path / "pose_validity_input.json"
    pose_input.write_text(
        json.dumps({"pose_validity_ready": True, "cases": [_pose_case()]}),
        encoding="utf-8",
    )
    out_scorecard = tmp_path / "rmsd_scorecard.json"
    out_report = tmp_path / "rmsd_report.json"

    assert (
        module.main(
            [
                "--pose-validity-input",
                str(pose_input),
                "--out-scorecard",
                str(out_scorecard),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    scorecard = json.loads(out_scorecard.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert scorecard["scorecard_ready"] is True
    assert report["scorecard_ready"] is True
