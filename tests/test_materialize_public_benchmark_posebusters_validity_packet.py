from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_public_benchmark_posebusters_validity_packet.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_posebusters_validity_packet", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _pose_case(case_id: str = "case_a", source_family: str = "CASF/PDBBind") -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": source_family,
        "protein_structure_path": "benchmarks/case_a/protein.pdb",
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
        "ligand_atom_order_contract": {
            "atom_count": 4,
            "atom_ids": ["C1", "O1", "O2", "N1"],
        },
        "symmetry_permutation_contract": {
            "permutations": [[0, 1, 2, 3], [0, 2, 1, 3]],
        },
        "rmsd_threshold_angstrom": 2.0,
        "subset_manifest_case_checksum": "sha256:case-a",
    }


def test_posebusters_packet_materializer_builds_ready_real_case() -> None:
    packet = module.materialize_posebusters_validity_packet(
        {"pose_validity_ready": True, "cases": [_pose_case()]},
        repo_root=REPO_ROOT,
    )

    assert packet["schema_version"] == "public-benchmark-pose-validity-packet.v1"
    assert packet["status"] == "ready"
    assert packet["posebusters_validity_ready"] is True
    assert packet["real_benchmark_case_count"] == 1
    assert packet["dry_run_case_count"] == 0
    assert packet["pose_success_count"] == 1
    assert packet["blockers"] == []
    row = packet["case_rows"][0]
    assert row["case_id"] == "case_a"
    assert row["pose_success"] is True
    assert {check["status"] for check in row["check_results"]} == {"pass"}
    assert {
        "coordinate_finiteness",
        "atom_count_and_order_contract",
        "symmetry_permutation_contract",
        "minimum_interatomic_distance_guard",
        "receptor_ligand_context_present",
        "symmetry_aware_ligand_rmsd_angstrom",
    } == {check["check_id"] for check in packet["checks"]}


def test_posebusters_packet_materializer_blocks_dry_run_only_input() -> None:
    packet = module.materialize_posebusters_validity_packet(
        {"pose_validity_ready": True, "cases": [_pose_case(source_family="synthetic")]},
        repo_root=REPO_ROOT,
    )

    assert packet["posebusters_validity_ready"] is False
    assert packet["real_benchmark_case_count"] == 0
    assert packet["dry_run_case_count"] == 1
    assert packet["blockers"] == ["real_benchmark_pose_cases_missing"]


def test_posebusters_packet_materializer_blocks_invalid_pose_input() -> None:
    packet = module.materialize_posebusters_validity_packet(
        {"pose_validity_ready": False, "cases": []},
        repo_root=REPO_ROOT,
    )

    assert packet["posebusters_validity_ready"] is False
    assert packet["status"] == "posebusters_validity_materialization_required"
    assert packet["blockers"] == [
        "pose_validity_input_cases_missing",
        "pose_validity_input_not_ready",
    ]


def test_posebusters_packet_materializer_cli_writes_packet_and_report(
    tmp_path: Path,
) -> None:
    pose_input = tmp_path / "pose_validity_input.json"
    pose_input.write_text(
        json.dumps({"pose_validity_ready": True, "cases": [_pose_case()]}),
        encoding="utf-8",
    )
    out_packet = tmp_path / "posebusters_packet.json"
    out_report = tmp_path / "posebusters_report.json"

    assert (
        module.main(
            [
                "--pose-validity-input",
                str(pose_input),
                "--out-packet",
                str(out_packet),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    packet = json.loads(out_packet.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert packet["posebusters_validity_ready"] is True
    assert report["posebusters_validity_ready"] is True
