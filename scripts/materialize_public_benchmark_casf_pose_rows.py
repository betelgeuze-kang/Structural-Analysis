#!/usr/bin/env python3
"""Materialize CASF-2016 subset and pose rows from an extracted official package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from rdkit import Chem

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from score_symmetry_aware_ligand_rmsd import score_symmetry_aware_rmsd  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CASF_ROOT = Path("/tmp/public_benchmark_casf/sample12/CASF-2016")
DEFAULT_SUBSET_ROWS_OUT = PRODUCTIZATION / "public_benchmark_subset_rows.json"
DEFAULT_POSE_ROWS_OUT = PRODUCTIZATION / "public_benchmark_pose_rows.json"
DEFAULT_CASE_COUNT = 12
DEFAULT_RMSD_THRESHOLD_ANGSTROM = 2.0
SCHEMA_VERSION = "public-benchmark-casf-pose-rows.v1"
CASF_2016_URL = "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz"
CASF_2016_SHA256 = (
    "sha256:ce0b615b6e467b2a13c7432c820ff924e1b99fea8ac0d6099978c45b9989ccb7"
)
POSE_SELECTION_POLICY = "lowest_rmsd_official_casf_docking_decoy_pose"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _stable_sha256(payload: Any) -> str:
    return _sha256_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )


def _relative_archive_path(path: Path, *, casf_root: Path) -> str:
    return f"CASF-2016/{path.resolve().relative_to(casf_root.resolve()).as_posix()}"


def _core_rows(core_set_path: Path, *, case_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in core_set_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 6:
            continue
        rows.append(
            {
                "code": parts[0],
                "resolution": float(parts[1]),
                "year": int(parts[2]),
                "logKa": float(parts[3]),
                "Ka": parts[4],
                "target_group": parts[5],
            }
        )
        if len(rows) >= case_count:
            break
    return rows


def _sdf_atoms(path: Path) -> list[dict[str, Any]]:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
    mol = supplier[0] if supplier and len(supplier) else None
    if mol is None:
        raise ValueError(f"could not parse SDF ligand: {path}")
    conf = mol.GetConformer()
    atoms: list[dict[str, Any]] = []
    for index, atom in enumerate(mol.GetAtoms()):
        pos = conf.GetAtomPosition(index)
        atoms.append(
            {
                "element": atom.GetSymbol(),
                "x": float(pos.x),
                "y": float(pos.y),
                "z": float(pos.z),
            }
        )
    return atoms


def _mol2_blocks(text: str) -> list[str]:
    parts = text.split("@<TRIPOS>MOLECULE")
    return ["@<TRIPOS>MOLECULE" + part for part in parts[1:]]


def _element_from_mol2_type(atom_type: str) -> str:
    token = re.split(r"[.0-9]", atom_type)[0]
    if token.upper() == "CL":
        return "Cl"
    if token.upper() == "BR":
        return "Br"
    return token[:1].upper() + token[1:].lower()


def _mol2_atoms(block: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    in_atoms = False
    for line in block.splitlines():
        if line.startswith("@<TRIPOS>ATOM"):
            in_atoms = True
            continue
        if line.startswith("@<TRIPOS>") and in_atoms:
            break
        if not in_atoms or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        atoms.append(
            {
                "element": _element_from_mol2_type(parts[5]),
                "x": float(parts[2]),
                "y": float(parts[3]),
                "z": float(parts[4]),
            }
        )
    return atoms


def _best_decoy_pose(
    decoys_path: Path,
    *,
    reference_atoms: list[dict[str, Any]],
    threshold_angstrom: float,
) -> dict[str, Any]:
    blocks = _mol2_blocks(decoys_path.read_text(encoding="utf-8", errors="replace"))
    best: dict[str, Any] | None = None
    skipped_atom_count_mismatch = 0
    for index, block in enumerate(blocks, start=1):
        predicted_atoms = _mol2_atoms(block)
        if len(predicted_atoms) != len(reference_atoms):
            skipped_atom_count_mismatch += 1
            continue
        score = score_symmetry_aware_rmsd(
            reference_atoms=reference_atoms,
            predicted_atoms=predicted_atoms,
            symmetry_permutations=[list(range(len(reference_atoms)))],
            threshold_angstrom=threshold_angstrom,
        )
        row = {
            "mol2_index": index,
            "mol2_block_sha256": _sha256_bytes(block.encode("utf-8")),
            "predicted_atoms": predicted_atoms,
            "rmsd": float(score["best_rmsd_angstrom"]),
            "pose_success": bool(score["pose_success"]),
        }
        if best is None or row["rmsd"] < best["rmsd"]:
            best = row
    if best is None:
        raise ValueError(f"no decoy pose with matching atom count: {decoys_path}")
    best["decoy_pose_count"] = len(blocks)
    best["skipped_atom_count_mismatch"] = skipped_atom_count_mismatch
    return best


def build_casf_pose_rows(
    *,
    casf_root: Path,
    case_count: int = DEFAULT_CASE_COUNT,
    rmsd_threshold_angstrom: float = DEFAULT_RMSD_THRESHOLD_ANGSTROM,
) -> dict[str, Any]:
    casf_root = casf_root.resolve()
    core_rows = _core_rows(
        casf_root / "power_screening" / "CoreSet.dat",
        case_count=case_count,
    )
    subset_cases: list[dict[str, Any]] = []
    pose_cases: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for core_row in core_rows:
        code = str(core_row["code"])
        case_id = f"casf2016_{code}"
        protein_path = casf_root / "coreset" / code / f"{code}_protein.pdb"
        ligand_path = casf_root / "coreset" / code / f"{code}_ligand.sdf"
        pocket_path = casf_root / "coreset" / code / f"{code}_pocket.pdb"
        decoys_path = casf_root / "decoys_docking" / f"{code}_decoys.mol2"
        reference_atoms = _sdf_atoms(ligand_path)
        selected_pose = _best_decoy_pose(
            decoys_path,
            reference_atoms=reference_atoms,
            threshold_angstrom=rmsd_threshold_angstrom,
        )
        atom_ids = [
            f"{atom['element']}{index}"
            for index, atom in enumerate(reference_atoms, start=1)
        ]
        identity_permutation = list(range(len(reference_atoms)))
        protein_ref = _relative_archive_path(protein_path, casf_root=casf_root)
        ligand_ref = _relative_archive_path(ligand_path, casf_root=casf_root)
        decoy_ref = (
            f"{_relative_archive_path(decoys_path, casf_root=casf_root)}"
            f"#mol2_index={selected_pose['mol2_index']}"
        )
        source_file_checksums = {
            protein_ref: _sha256_file(protein_path),
            ligand_ref: _sha256_file(ligand_path),
            decoy_ref: selected_pose["mol2_block_sha256"],
        }
        source_checksum = _stable_sha256(
            {
                "casf_archive_sha256": CASF_2016_SHA256,
                "case_id": case_id,
                "source_file_checksums": source_file_checksums,
            }
        )
        atom_order_contract = {
            "atom_count": len(reference_atoms),
            "atom_ids": atom_ids,
            "atom_id_basis": "CASF-2016 reference ligand SDF atom order",
        }
        symmetry_contract = {
            "permutations": [identity_permutation],
            "permutation_basis": (
                "identity permutation over CASF-2016 reference ligand atom order; "
                "this materializer does not infer chemical automorphisms"
            ),
        }
        subset_cases.append(
            {
                "case_id": case_id,
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "complex_id": code,
                "protein_structure_path": protein_ref,
                "reference_ligand_path": ligand_ref,
                "predicted_ligand_path_or_docking_run_id": decoy_ref,
                "ligand_atom_order_contract": atom_order_contract,
                "symmetry_permutation_contract": symmetry_contract,
                "source_license_or_accession": "PDBbind+ CASF-2016 official package",
                "source_checksum": source_checksum,
                "source_file_checksums": source_file_checksums,
                "provenance_ref": CASF_2016_URL,
                "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                "rmsd_threshold_angstrom": rmsd_threshold_angstrom,
            }
        )
        pose_cases.append(
            {
                "case_id": case_id,
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                "reference_atoms": reference_atoms,
                "predicted_atoms": selected_pose["predicted_atoms"],
                "ligand_atom_order_contract": atom_order_contract,
                "symmetry_permutation_contract": symmetry_contract,
                "protein_structure_path": protein_ref,
                "receptor_context": {
                    "binding_site_frame": "CASF-2016 official coreset pocket",
                    "pocket_structure_path": _relative_archive_path(
                        pocket_path,
                        casf_root=casf_root,
                    ),
                    "pocket_structure_sha256": _sha256_file(pocket_path),
                    "provenance_ref": CASF_2016_URL,
                    "selected_decoy_pose_policy": POSE_SELECTION_POLICY,
                    "selected_decoy_mol2_index": selected_pose["mol2_index"],
                },
                "rmsd_threshold_angstrom": rmsd_threshold_angstrom,
                "selected_decoy_pose": {
                    "mol2_index": selected_pose["mol2_index"],
                    "rmsd_angstrom": selected_pose["rmsd"],
                    "pose_success": selected_pose["pose_success"],
                    "decoy_pose_count": selected_pose["decoy_pose_count"],
                    "selection_policy": POSE_SELECTION_POLICY,
                    "mol2_block_sha256": selected_pose["mol2_block_sha256"],
                },
            }
        )
        source_rows.append(
            {
                "case_id": case_id,
                "complex_id": code,
                **core_row,
                "selected_decoy_mol2_index": selected_pose["mol2_index"],
                "selected_decoy_rmsd_angstrom": selected_pose["rmsd"],
                "selected_decoy_pose_success": selected_pose["pose_success"],
                "decoy_pose_count": selected_pose["decoy_pose_count"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "source_url": CASF_2016_URL,
        "source_archive_sha256": CASF_2016_SHA256,
        "case_count": len(subset_cases),
        "pose_selection_policy": POSE_SELECTION_POLICY,
        "rmsd_threshold_angstrom": rmsd_threshold_angstrom,
        "subset_rows": {"rows": subset_cases},
        "pose_rows": {"cases": pose_cases},
        "source_rows": source_rows,
        "claim_boundary": (
            "Rows are derived from the official CASF-2016 package. The selected "
            "predicted pose is the lowest-RMSD pose within the package's official "
            "docking decoy mol2 file, so these rows prove the local pose/RMSD "
            "materialization contracts and do not claim prospective Vina/GNINA "
            "docking performance."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casf-root", type=Path, default=DEFAULT_CASF_ROOT)
    parser.add_argument("--case-count", type=int, default=DEFAULT_CASE_COUNT)
    parser.add_argument("--subset-rows-out", type=Path, default=DEFAULT_SUBSET_ROWS_OUT)
    parser.add_argument("--pose-rows-out", type=Path, default=DEFAULT_POSE_ROWS_OUT)
    parser.add_argument(
        "--rmsd-threshold-angstrom",
        type=float,
        default=DEFAULT_RMSD_THRESHOLD_ANGSTROM,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_casf_pose_rows(
        casf_root=args.casf_root,
        case_count=args.case_count,
        rmsd_threshold_angstrom=args.rmsd_threshold_angstrom,
    )
    args.subset_rows_out.parent.mkdir(parents=True, exist_ok=True)
    args.pose_rows_out.parent.mkdir(parents=True, exist_ok=True)
    args.subset_rows_out.write_text(_json_text(payload["subset_rows"]), encoding="utf-8")
    args.pose_rows_out.write_text(_json_text(payload["pose_rows"]), encoding="utf-8")
    print(
        "public-benchmark-casf-pose-rows: "
        f"cases={payload['case_count']} | "
        f"subset={args.subset_rows_out} | pose={args.pose_rows_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
