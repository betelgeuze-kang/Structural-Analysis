#!/usr/bin/env python3
"""Prepare Vina/GNINA receptor and ligand inputs from the CASF source manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_IN_MANIFEST = PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.csv"
DEFAULT_OUT_MANIFEST = DEFAULT_IN_MANIFEST
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_prepared_inputs_report.json"
)
DEFAULT_PREPARED_DIR = Path("tmp/public_benchmark_vina_gnina/prepared_inputs")
SCHEMA_VERSION = "public-benchmark-vina-gnina-prepared-inputs.v1"
CHECKSUM_CHUNK_SIZE = 1024 * 1024


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_manifest(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]
        header = [str(field) for field in reader.fieldnames or []]
    return header, rows


def _write_manifest(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=header, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "status": "ready" if completed.returncode == 0 else "failed",
    }


def _write_query_free_ligand_sdf(source: Path, destination: Path) -> dict[str, Any]:
    try:
        from rdkit import Chem
        from rdkit.Geometry import Point3D
        from rdkit import rdBase
    except Exception as exc:  # pragma: no cover - exercised only without RDKit.
        return {
            "status": "failed",
            "blocker": f"rdkit_import_failed:{exc.__class__.__name__}",
            "rdkit_version": "",
        }

    supplier = Chem.SDMolSupplier(str(source), sanitize=False, removeHs=False)
    mol = supplier[0] if len(supplier) else None
    if mol is None:
        return {
            "status": "failed",
            "blocker": "ligand_sdf_unreadable",
            "rdkit_version": rdBase.rdkitVersion,
        }
    conf = mol.GetConformer()
    rw_mol = Chem.RWMol()
    for atom in mol.GetAtoms():
        copied = Chem.Atom(atom.GetAtomicNum())
        copied.SetFormalCharge(atom.GetFormalCharge())
        copied.SetIsAromatic(atom.GetIsAromatic())
        rw_mol.AddAtom(copied)
    for bond in mol.GetBonds():
        begin = bond.GetBeginAtomIdx()
        end = bond.GetEndAtomIdx()
        rw_mol.AddBond(begin, end, bond.GetBondType())
        copied_bond = rw_mol.GetBondBetweenAtoms(begin, end)
        copied_bond.SetIsAromatic(bond.GetIsAromatic())
    carboxylate_charge_correction_count = 0
    for atom in rw_mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or atom.GetFormalCharge() != -1:
            continue
        double_oxygen_bonds = [
            (bond, bond.GetOtherAtom(atom))
            for bond in atom.GetBonds()
            if (
                bond.GetOtherAtom(atom).GetAtomicNum() == 8
                and bond.GetBondType() == Chem.BondType.DOUBLE
            )
        ]
        if len(double_oxygen_bonds) < 2:
            continue
        atom.SetFormalCharge(0)
        bond, oxygen = double_oxygen_bonds[-1]
        bond.SetBondType(Chem.BondType.SINGLE)
        oxygen.SetFormalCharge(-1)
        carboxylate_charge_correction_count += 1
    plain = rw_mol.GetMol()
    plain_conf = Chem.Conformer(plain.GetNumAtoms())
    for atom_index in range(plain.GetNumAtoms()):
        point = conf.GetAtomPosition(atom_index)
        plain_conf.SetAtomPosition(atom_index, Point3D(point.x, point.y, point.z))
    plain.AddConformer(plain_conf, assignId=True)
    try:
        Chem.SanitizeMol(plain)
    except Exception as exc:
        return {
            "status": "failed",
            "blocker": f"ligand_sanitize_failed:{exc.__class__.__name__}",
            "rdkit_version": rdBase.rdkitVersion,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(destination))
    writer.write(plain)
    writer.close()
    return {
        "status": "ready",
        "blocker": "",
        "rdkit_version": rdBase.rdkitVersion,
        "query_atom_count_before": sum(1 for atom in mol.GetAtoms() if atom.HasQuery()),
        "query_bond_count_before": sum(1 for bond in mol.GetBonds() if bond.HasQuery()),
        "carboxylate_charge_correction_count": carboxylate_charge_correction_count,
        "atom_count": plain.GetNumAtoms(),
        "heavy_atom_count": plain.GetNumHeavyAtoms(),
    }


def _materialize_case(
    *,
    repo_root: Path,
    row: dict[str, str],
    prepared_dir: Path,
    ligand_preparer: Path,
    receptor_preparer: Path,
    report_ref: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    case_id = str(row.get("case_id") or "")
    complex_id = str(row.get("complex_id") or "")
    case_dir = _resolve(repo_root, prepared_dir) / case_id
    ligand_plain = case_dir / f"{complex_id}_ligand_query_free.sdf"
    ligand_out = case_dir / f"{complex_id}_ligand.pdbqt"
    receptor_base = case_dir / f"{complex_id}_receptor"
    receptor_out = case_dir / f"{complex_id}_receptor.pdbqt"
    protein = _resolve(repo_root, Path(str(row.get("protein_structure_path") or "")))
    ligand = _resolve(repo_root, Path(str(row.get("reference_ligand_path") or "")))
    blockers: list[str] = []
    if not protein.is_file():
        blockers.append("protein_structure_file_missing")
    if not ligand.is_file():
        blockers.append("reference_ligand_file_missing")
    ligand_normalization: dict[str, Any] = {}
    ligand_command: dict[str, Any] = {}
    receptor_command: dict[str, Any] = {}
    if not blockers:
        ligand_normalization = _write_query_free_ligand_sdf(ligand, ligand_plain)
        if ligand_normalization.get("status") != "ready":
            blockers.append(str(ligand_normalization.get("blocker") or "ligand_normalization_failed"))
    if not blockers:
        ligand_command = _run_command(
            [
                str(_resolve(repo_root, ligand_preparer)),
                "-i",
                _display_path(repo_root, ligand_plain),
                "-o",
                _display_path(repo_root, ligand_out),
            ],
            cwd=repo_root,
        )
        if ligand_command["returncode"] != 0 or not ligand_out.is_file():
            blockers.append("prepared_ligand_materialization_failed")
    if not blockers:
        receptor_command = _run_command(
            [
                str(_resolve(repo_root, receptor_preparer)),
                "--read_pdb",
                _display_path(repo_root, protein),
                "-o",
                _display_path(repo_root, receptor_base),
                "-p",
                _display_path(repo_root, receptor_out),
                "-a",
            ],
            cwd=repo_root,
        )
        if receptor_command["returncode"] != 0 or not receptor_out.is_file():
            blockers.append("prepared_receptor_materialization_failed")
    updated = dict(row)
    receptor_checksum = _sha256_file(receptor_out) if receptor_out.is_file() else ""
    ligand_checksum = _sha256_file(ligand_out) if ligand_out.is_file() else ""
    if receptor_checksum and ligand_checksum and not blockers:
        updated["prepared_receptor_path"] = _display_path(repo_root, receptor_out)
        updated["prepared_receptor_checksum"] = receptor_checksum
        updated["prepared_ligand_path"] = _display_path(repo_root, ligand_out)
        updated["prepared_ligand_checksum"] = ligand_checksum
        updated["input_preparation_provenance_ref"] = str(report_ref)
    return (
        updated,
        {
            "case_id": case_id,
            "complex_id": complex_id,
            "status": "ready" if not blockers else "blocked",
            "blockers": blockers,
            "protein_structure_path": str(row.get("protein_structure_path") or ""),
            "reference_ligand_path": str(row.get("reference_ligand_path") or ""),
            "prepared_receptor_path": _display_path(repo_root, receptor_out),
            "prepared_receptor_checksum": receptor_checksum,
            "prepared_ligand_path": _display_path(repo_root, ligand_out),
            "prepared_ligand_checksum": ligand_checksum,
            "query_free_ligand_sdf": _display_path(repo_root, ligand_plain),
            "ligand_normalization": ligand_normalization,
            "ligand_preparation_command": ligand_command,
            "receptor_preparation_command": receptor_command,
        },
    )


def materialize_public_benchmark_vina_gnina_prepared_inputs(
    *,
    repo_root: Path = ROOT,
    in_manifest: Path = DEFAULT_IN_MANIFEST,
    out_manifest: Path = DEFAULT_OUT_MANIFEST,
    out_report: Path = DEFAULT_OUT_REPORT,
    prepared_dir: Path = DEFAULT_PREPARED_DIR,
    ligand_preparer: Path,
    receptor_preparer: Path,
) -> dict[str, Any]:
    manifest_path = _resolve(repo_root, in_manifest)
    header, rows = _read_manifest(manifest_path)
    report_ref = out_report
    updated_rows: list[dict[str, str]] = []
    case_rows: list[dict[str, Any]] = []
    for row in rows:
        updated, case_status = _materialize_case(
            repo_root=repo_root,
            row=row,
            prepared_dir=prepared_dir,
            ligand_preparer=ligand_preparer,
            receptor_preparer=receptor_preparer,
            report_ref=report_ref,
        )
        updated_rows.append(updated)
        case_rows.append(case_status)
    ready_case_count = sum(1 for row in case_rows if row["status"] == "ready")
    prepared_input_count = sum(
        2 for row in case_rows if row["prepared_receptor_checksum"] and row["prepared_ligand_checksum"]
    )
    blocker_count = sum(len(row["blockers"]) for row in case_rows)
    status = (
        "prepared_inputs_ready"
        if rows and ready_case_count == len(rows)
        else "prepared_input_materialization_blocked"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "contract_pass": status == "prepared_inputs_ready",
        "manifest_ready": status == "prepared_inputs_ready",
        "prepared_inputs_ready": status == "prepared_inputs_ready",
        "case_count": len(rows),
        "ready_case_count": ready_case_count,
        "prepared_input_count": prepared_input_count,
        "blocker_count": blocker_count,
        "prepared_dir": str(prepared_dir),
        "input_manifest": str(in_manifest),
        "output_manifest": str(out_manifest),
        "ligand_preparer": str(ligand_preparer),
        "receptor_preparer": str(receptor_preparer),
        "case_rows": case_rows,
        "summary": {
            "case_count": len(rows),
            "ready_case_count": ready_case_count,
            "blocked_case_count": len(rows) - ready_case_count,
            "prepared_input_count": prepared_input_count,
            "blocker_count": blocker_count,
        },
        "metadata": release_evidence_metadata(
            repo_root=repo_root,
            input_paths=[
                in_manifest,
                Path("scripts/materialize_public_benchmark_vina_gnina_prepared_inputs.py"),
            ],
            reused_evidence=False,
            reuse_policy="materialize_public_benchmark_vina_gnina_prepared_inputs",
        ),
        "claim_boundary": (
            "This materializes derived Vina/GNINA PDBQT inputs into the local "
            "operator workspace and records checksums in the manifest. It does "
            "not prove Vina or GNINA engines were run and does not commit the "
            "derived CASF payload files."
        ),
    }
    _write_manifest(_resolve(repo_root, out_manifest), header, updated_rows)
    _resolve(repo_root, out_report).parent.mkdir(parents=True, exist_ok=True)
    _resolve(repo_root, out_report).write_text(_json_text(payload), encoding="utf-8")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Vina/GNINA receptor and ligand inputs from a manifest."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--in-manifest", type=Path, default=DEFAULT_IN_MANIFEST)
    parser.add_argument("--out-manifest", type=Path, default=DEFAULT_OUT_MANIFEST)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--prepared-dir", type=Path, default=DEFAULT_PREPARED_DIR)
    parser.add_argument("--ligand-preparer", type=Path, required=True)
    parser.add_argument("--receptor-preparer", type=Path, required=True)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = materialize_public_benchmark_vina_gnina_prepared_inputs(
        repo_root=args.repo_root,
        in_manifest=args.in_manifest,
        out_manifest=args.out_manifest,
        out_report=args.out_report,
        prepared_dir=args.prepared_dir,
        ligand_preparer=args.ligand_preparer,
        receptor_preparer=args.receptor_preparer,
    )
    print(
        "public-benchmark-vina-gnina-prepared-inputs: "
        f"{payload['status']} | ready={payload['ready_case_count']}/"
        f"{payload['case_count']} | blockers={payload['blocker_count']}"
    )
    if args.fail_blocked and payload["status"] != "prepared_inputs_ready":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
