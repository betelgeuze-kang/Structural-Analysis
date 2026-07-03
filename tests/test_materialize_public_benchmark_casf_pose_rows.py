from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_casf_pose_rows.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_casf_pose_rows", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_fixture_sdf(path: Path) -> None:
    path.write_text(
        """fixture
  test

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )


def _mol2_block(name: str, coords: list[tuple[str, float, float, float]]) -> str:
    atom_lines = [
        f"{index:7d} {element}{index} {x:.4f} {y:.4f} {z:.4f} {element}.3 1 LIG 0.0"
        for index, (element, x, y, z) in enumerate(coords, start=1)
    ]
    return "\n".join(
        [
            "@<TRIPOS>MOLECULE",
            name,
            " 3 2 0 0 0",
            "SMALL",
            "USER_CHARGES",
            "",
            "@<TRIPOS>ATOM",
            *atom_lines,
            "@<TRIPOS>BOND",
            "     1    1    2 1",
            "     2    1    3 1",
            "",
        ]
    )


def _write_casf_fixture(root: Path) -> Path:
    casf_root = root / "CASF-2016"
    code = "1abc"
    case_dir = casf_root / "coreset" / code
    decoy_dir = casf_root / "decoys_docking"
    power_dir = casf_root / "power_screening"
    case_dir.mkdir(parents=True)
    decoy_dir.mkdir(parents=True)
    power_dir.mkdir(parents=True)
    (power_dir / "CoreSet.dat").write_text(
        "#code resolution year logKa Ka target\n"
        "1abc 1.50 2016 6.00 1.0e6 fixture_target\n",
        encoding="utf-8",
    )
    (case_dir / f"{code}_protein.pdb").write_text("HEADER fixture protein\n", encoding="utf-8")
    (case_dir / f"{code}_pocket.pdb").write_text("HEADER fixture pocket\n", encoding="utf-8")
    _write_fixture_sdf(case_dir / f"{code}_ligand.sdf")
    (decoy_dir / f"{code}_decoys.mol2").write_text(
        _mol2_block(
            "pose_bad",
            [
                ("C", 0.0, 0.0, 0.0),
                ("O", 3.0, 0.0, 0.0),
                ("N", 0.0, 3.0, 0.0),
            ],
        )
        + _mol2_block(
            "pose_good",
            [
                ("C", 0.01, 0.00, 0.00),
                ("O", 1.01, 0.01, 0.00),
                ("N", 0.00, 1.01, 0.01),
            ],
        ),
        encoding="utf-8",
    )
    return casf_root


def test_casf_pose_rows_select_lowest_rmsd_official_decoy_pose(
    tmp_path: Path,
) -> None:
    casf_root = _write_casf_fixture(tmp_path)

    payload = module.build_casf_pose_rows(
        casf_root=casf_root,
        case_count=1,
        rmsd_threshold_angstrom=0.2,
    )

    assert payload["schema_version"] == "public-benchmark-casf-pose-rows.v1"
    assert payload["source_url"] == module.CASF_2016_URL
    assert payload["source_archive_sha256"] == module.CASF_2016_SHA256
    assert payload["case_count"] == 1
    assert payload["pose_selection_policy"] == module.POSE_SELECTION_POLICY
    assert "do not claim prospective Vina/GNINA docking performance" in payload[
        "claim_boundary"
    ]
    subset_row = payload["subset_rows"]["rows"][0]
    pose_row = payload["pose_rows"]["cases"][0]

    assert subset_row["case_id"] == "casf2016_1abc"
    assert subset_row["protein_structure_path"] == (
        "CASF-2016/coreset/1abc/1abc_protein.pdb"
    )
    assert subset_row["reference_ligand_path"] == (
        "CASF-2016/coreset/1abc/1abc_ligand.sdf"
    )
    assert subset_row["predicted_ligand_path_or_docking_run_id"] == (
        "CASF-2016/decoys_docking/1abc_decoys.mol2#mol2_index=2"
    )
    assert set(subset_row["source_file_checksums"]) == {
        subset_row["protein_structure_path"],
        subset_row["reference_ligand_path"],
        subset_row["predicted_ligand_path_or_docking_run_id"],
    }
    assert all(
        checksum.startswith("sha256:")
        for checksum in subset_row["source_file_checksums"].values()
    )
    assert subset_row["ligand_atom_order_contract"]["atom_count"] == 3
    assert subset_row["symmetry_permutation_contract"]["permutations"] == [[0, 1, 2]]

    assert pose_row["case_id"] == "casf2016_1abc"
    assert len(pose_row["reference_atoms"]) == 3
    assert len(pose_row["predicted_atoms"]) == 3
    assert pose_row["selected_decoy_pose"] == {
        "decoy_pose_count": 2,
        "mol2_block_sha256": pose_row["selected_decoy_pose"]["mol2_block_sha256"],
        "mol2_index": 2,
        "pose_success": True,
        "rmsd_angstrom": pose_row["selected_decoy_pose"]["rmsd_angstrom"],
        "selection_policy": module.POSE_SELECTION_POLICY,
    }
    assert pose_row["selected_decoy_pose"]["rmsd_angstrom"] < 0.2
    assert pose_row["receptor_context"]["selected_decoy_pose_policy"] == (
        module.POSE_SELECTION_POLICY
    )


def test_casf_pose_rows_cli_writes_subset_and_pose_rows(tmp_path: Path) -> None:
    casf_root = _write_casf_fixture(tmp_path)
    subset_out = tmp_path / "subset_rows.json"
    pose_out = tmp_path / "pose_rows.json"

    assert (
        module.main(
            [
                "--casf-root",
                str(casf_root),
                "--case-count",
                "1",
                "--rmsd-threshold-angstrom",
                "0.2",
                "--subset-rows-out",
                str(subset_out),
                "--pose-rows-out",
                str(pose_out),
            ]
        )
        == 0
    )

    subset_payload = json.loads(subset_out.read_text(encoding="utf-8"))
    pose_payload = json.loads(pose_out.read_text(encoding="utf-8"))
    assert subset_payload["rows"][0]["case_id"] == "casf2016_1abc"
    assert pose_payload["cases"][0]["selected_decoy_pose"]["mol2_index"] == 2
