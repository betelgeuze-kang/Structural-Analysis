#!/usr/bin/env python3
"""Fill PocketMD Lite receipt slots from GPCR ChEMBL top-k ligand refinements."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402

try:  # noqa: E402
    from rdkit import Chem
    from rdkit import rdBase
    from rdkit.Chem import AllChem
except Exception as exc:  # pragma: no cover - import failure is environment-specific.
    raise SystemExit(f"RDKit is required for PocketMD Lite refinement receipts: {exc}")


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_GPCR_ROWS = PRODUCTIZATION / "gpcr_hard_decoy_rows.json"
DEFAULT_RECEIPT_BUNDLE = PRODUCTIZATION / "pocketmd_lite_refinement_receipt_bundle.json"
DEFAULT_SOURCE_OUT = (
    PRODUCTIZATION
    / "operator_attached"
    / "pocketmd_lite_refinement_sources"
    / "gpcr_chembl_topk_ligand_refinement_source.json"
)
DEFAULT_REPORT_OUT = PRODUCTIZATION / "pocketmd_lite_gpcr_chembl_refinement_receipts_report.json"

SCHEMA_VERSION = "pocketmd-lite-gpcr-chembl-refinement-receipts.v1"
SOURCE_SCHEMA_VERSION = "pocketmd-lite-gpcr-chembl-rdkit-refinement-source.v1"
DEFAULT_TARGET_ORDER = ("DRD2", "HTR2A", "OPRM1")
DEFAULT_CANDIDATES_PER_TARGET = 2
CHEMBL_MOLECULE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule"
SOURCE_ID = "pocketmd_lite_gpcr_chembl_rdkit_refinement_2026_07_05"
SOURCE_LICENSE = "ChEMBL public API data; use subject to EMBL-EBI and ChEMBL terms"
SOURCE_VERSION = "chembl_molecule_api_snapshot_rdkit_2022_09_5"
SOURCE_FAMILY = "ChEMBL GPCR hard-decoy top-k ligand refinement"
USER_AGENT = "pocketmd-lite-refinement-receipt-materializer/1.0"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected_object_json:{path}")
    return payload


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _round_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non_finite_metric")
    return round(float(value), 6)


def _fetch_chembl_molecule(molecule_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    url = f"{CHEMBL_MOLECULE_URL}/{molecule_id}.json"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"chembl_molecule_payload_not_object:{molecule_id}")
    return payload


def _canonical_smiles(payload: dict[str, Any], molecule_id: str) -> str:
    structures = payload.get("molecule_structures")
    smiles = ""
    if isinstance(structures, dict):
        smiles = str(structures.get("canonical_smiles") or "").strip()
    if not smiles:
        raise ValueError(f"canonical_smiles_missing:{molecule_id}")
    return smiles


def _force_field(mol: Chem.Mol, *, conf_id: int = 0) -> tuple[Any, str]:
    mmff_props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94s")
    if mmff_props is not None:
        ff = AllChem.MMFFGetMoleculeForceField(mol, mmff_props, confId=conf_id)
        if ff is not None:
            return ff, "MMFF94s"
    ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
    if ff is None:
        raise ValueError("force_field_unavailable")
    return ff, "UFF"


def _heavy_atom_indices(mol: Chem.Mol) -> list[int]:
    return [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1]


def _positions(mol: Chem.Mol) -> dict[int, tuple[float, float, float]]:
    conf = mol.GetConformer()
    return {
        index: (
            float(conf.GetAtomPosition(index).x),
            float(conf.GetAtomPosition(index).y),
            float(conf.GetAtomPosition(index).z),
        )
        for index in range(mol.GetNumAtoms())
    }


def _distance(
    positions: dict[int, tuple[float, float, float]],
    atom_i: int,
    atom_j: int,
) -> float:
    x1, y1, z1 = positions[atom_i]
    x2, y2, z2 = positions[atom_j]
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


def _topological_distances(mol: Chem.Mol) -> list[list[float]]:
    matrix = Chem.GetDistanceMatrix(mol)
    return [[float(matrix[i, j]) for j in range(mol.GetNumAtoms())] for i in range(mol.GetNumAtoms())]


def _contact_pairs(
    mol: Chem.Mol,
    positions: dict[int, tuple[float, float, float]],
    topo: list[list[float]],
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    heavy_atoms = _heavy_atom_indices(mol)
    for offset, atom_i in enumerate(heavy_atoms):
        for atom_j in heavy_atoms[offset + 1 :]:
            if topo[atom_i][atom_j] <= 3:
                continue
            if _distance(positions, atom_i, atom_j) <= 4.5:
                pairs.add((atom_i, atom_j))
    return pairs


def _h_bond_pairs(
    mol: Chem.Mol,
    positions: dict[int, tuple[float, float, float]],
    topo: list[list[float]],
) -> set[tuple[int, int]]:
    donor_atoms = {
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() in {7, 8, 16}
        and any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors())
    }
    acceptor_atoms = {
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() in {7, 8, 16} and atom.GetFormalCharge() <= 0
    }
    pairs: set[tuple[int, int]] = set()
    for donor_idx in donor_atoms:
        for acceptor_idx in acceptor_atoms:
            if donor_idx == acceptor_idx or topo[donor_idx][acceptor_idx] <= 2:
                continue
            if _distance(positions, donor_idx, acceptor_idx) <= 3.5:
                pairs.add(tuple(sorted((donor_idx, acceptor_idx))))
    return pairs


def _clash_count(
    mol: Chem.Mol,
    positions: dict[int, tuple[float, float, float]],
    topo: list[list[float]],
) -> int:
    periodic_table = Chem.GetPeriodicTable()
    count = 0
    heavy_atoms = _heavy_atom_indices(mol)
    for offset, atom_i in enumerate(heavy_atoms):
        for atom_j in heavy_atoms[offset + 1 :]:
            if topo[atom_i][atom_j] <= 2:
                continue
            radius_i = periodic_table.GetRcovalent(mol.GetAtomWithIdx(atom_i).GetAtomicNum())
            radius_j = periodic_table.GetRcovalent(mol.GetAtomWithIdx(atom_j).GetAtomicNum())
            if _distance(positions, atom_i, atom_j) < 0.75 * (radius_i + radius_j):
                count += 1
    return count


def _retention_rate(before: set[tuple[int, int]], after: set[tuple[int, int]]) -> float:
    if not before:
        return 1.0
    return len(before.intersection(after)) / len(before)


def _single_conformer_metrics(smiles: str, *, seed: int) -> dict[str, Any]:
    base_mol = Chem.MolFromSmiles(smiles)
    if base_mol is None:
        raise ValueError("smiles_parse_failed")
    mol = Chem.AddHs(base_mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    params.useRandomCoords = True
    embed_status = AllChem.EmbedMolecule(mol, params)
    if embed_status != 0:
        raise ValueError(f"embed_failed:{embed_status}")
    topo = _topological_distances(mol)
    before_positions = _positions(mol)
    ff, force_field = _force_field(mol)
    pre_energy = float(ff.CalcEnergy())
    minimize_status = int(ff.Minimize(maxIts=500))
    post_energy = float(ff.CalcEnergy())
    after_positions = _positions(mol)
    contacts_before = _contact_pairs(mol, before_positions, topo)
    contacts_after = _contact_pairs(mol, after_positions, topo)
    h_bonds_before = _h_bond_pairs(mol, before_positions, topo)
    h_bonds_after = _h_bond_pairs(mol, after_positions, topo)
    return {
        "pre_refinement_energy_proxy": pre_energy,
        "post_refinement_energy_proxy": post_energy,
        "energy_proxy_delta": post_energy - pre_energy,
        "local_min_survived": bool(post_energy <= pre_energy + 1e-6),
        "contact_persistence_rate": _retention_rate(contacts_before, contacts_after),
        "h_bond_persistence_rate": _retention_rate(h_bonds_before, h_bonds_after),
        "clash_count_before": _clash_count(mol, before_positions, topo),
        "clash_count_after": _clash_count(mol, after_positions, topo),
        "contact_pair_count_before": len(contacts_before),
        "contact_pair_count_after": len(contacts_after),
        "h_bond_pair_count_before": len(h_bonds_before),
        "h_bond_pair_count_after": len(h_bonds_after),
        "minimize_status": minimize_status,
        "force_field": force_field,
        "seed": seed,
    }


def _refinement_metrics(smiles: str, *, seed_base: int) -> dict[str, Any]:
    conformers = [
        _single_conformer_metrics(smiles, seed=seed_base + offset)
        for offset in range(3)
    ]
    primary = conformers[0]
    post_energies = [float(row["post_refinement_energy_proxy"]) for row in conformers]
    delta = float(primary["energy_proxy_delta"])
    uncertainty = statistics.pstdev(post_energies) if len(post_energies) > 1 else 0.0
    low = delta - uncertainty
    high = delta + uncertainty
    return {
        "pre_refinement_energy_proxy": _round_float(float(primary["pre_refinement_energy_proxy"])),
        "post_refinement_energy_proxy": _round_float(float(primary["post_refinement_energy_proxy"])),
        "energy_proxy_delta": _round_float(delta),
        "local_min_survived": bool(primary["local_min_survived"]),
        "contact_persistence_rate": _round_float(float(primary["contact_persistence_rate"])),
        "h_bond_persistence_rate": _round_float(float(primary["h_bond_persistence_rate"])),
        "clash_count_before": int(primary["clash_count_before"]),
        "clash_count_after": int(primary["clash_count_after"]),
        "uncertainty_low": _round_float(low),
        "uncertainty_high": _round_float(high),
        "uncertainty_unit": "energy_proxy_delta",
        "force_field": str(primary["force_field"]),
        "seed_base": seed_base,
        "conformer_replicates": [
            {
                "seed": int(row["seed"]),
                "force_field": str(row["force_field"]),
                "minimize_status": int(row["minimize_status"]),
                "pre_refinement_energy_proxy": _round_float(float(row["pre_refinement_energy_proxy"])),
                "post_refinement_energy_proxy": _round_float(float(row["post_refinement_energy_proxy"])),
                "energy_proxy_delta": _round_float(float(row["energy_proxy_delta"])),
                "contact_pair_count_before": int(row["contact_pair_count_before"]),
                "contact_pair_count_after": int(row["contact_pair_count_after"]),
                "h_bond_pair_count_before": int(row["h_bond_pair_count_before"]),
                "h_bond_pair_count_after": int(row["h_bond_pair_count_after"]),
                "clash_count_before": int(row["clash_count_before"]),
                "clash_count_after": int(row["clash_count_after"]),
            }
            for row in conformers
        ],
    }


def _gpcr_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("gpcr_rows_missing")
    return [row for row in rows if isinstance(row, dict)]


def _select_topk_candidates(
    gpcr_rows: list[dict[str, Any]],
    *,
    target_order: tuple[str, ...],
    candidates_per_target: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for target_index, target_id in enumerate(target_order, start=1):
        target_rows = [
            row
            for row in gpcr_rows
            if str(row.get("target_id") or "") == target_id
            and bool(row.get("is_positive")) is True
            and str(row.get("molecule_id") or "")
        ]
        target_rows = sorted(
            target_rows,
            key=lambda row: (
                -float(row.get("score") or 0.0),
                str(row.get("molecule_id") or ""),
                str(row.get("activity_id") or ""),
            ),
        )
        if len(target_rows) < candidates_per_target:
            raise ValueError(f"insufficient_positive_rows:{target_id}")
        case_id = f"pocketmd_lite_case_{target_index:03d}"
        for rank, row in enumerate(target_rows[:candidates_per_target], start=1):
            selected.append(
                {
                    "case_id": case_id,
                    "top_k_rank": rank,
                    "target_id": target_id,
                    "candidate_id": f"{target_id}_{row['molecule_id']}",
                    "gpcr_row": row,
                }
            )
    return selected


def _receipt_refs_by_slot(bundle_payload: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    rows = bundle_payload.get("bundle_rows")
    if not isinstance(rows, list):
        raise ValueError("receipt_bundle_rows_missing")
    refs: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "")
        rank = int(row.get("top_k_rank") or 0)
        if case_id and rank:
            refs[(case_id, rank)] = row
    return refs


def _row_and_source_entry(
    *,
    selected: dict[str, Any],
    molecule_payload: dict[str, Any],
    metrics: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    gpcr_row = selected["gpcr_row"]
    molecule_id = str(gpcr_row["molecule_id"])
    target_id = str(selected["target_id"])
    case_id = str(selected["case_id"])
    rank = int(selected["top_k_rank"])
    smiles = _canonical_smiles(molecule_payload, molecule_id)
    molecule_checksum = _json_digest(molecule_payload)
    provenance_ref = (
        f"{CHEMBL_MOLECULE_URL}/{molecule_id}.json"
        f"#pocketmd-lite-rdkit-refinement-{case_id}-rank-{rank:02d}"
    )
    row_evidence = {
        "case_id": case_id,
        "target_id": target_id,
        "top_k_rank": rank,
        "candidate_id": selected["candidate_id"],
        "upstream_gpcr_row": gpcr_row,
        "chembl_molecule_payload_checksum": molecule_checksum,
        "canonical_smiles": smiles,
        "metrics": metrics,
        "method": "rdkit_etkdg3_mmff94s_or_uff_ligand_only_minimization",
    }
    source_checksum = _json_digest(row_evidence)
    row = {
        "case_id": case_id,
        "source_family": SOURCE_FAMILY,
        "top_k_rank": rank,
        "candidate_id": selected["candidate_id"],
        "upstream_top_k_provenance_ref": str(gpcr_row["provenance_ref"]),
        "upstream_top_k_source_checksum": str(gpcr_row["source_checksum"]),
        "pre_refinement_energy_proxy": metrics["pre_refinement_energy_proxy"],
        "post_refinement_energy_proxy": metrics["post_refinement_energy_proxy"],
        "local_min_survived": metrics["local_min_survived"],
        "contact_persistence_rate": metrics["contact_persistence_rate"],
        "h_bond_persistence_rate": metrics["h_bond_persistence_rate"],
        "clash_count_before": metrics["clash_count_before"],
        "clash_count_after": metrics["clash_count_after"],
        "uncertainty_low": metrics["uncertainty_low"],
        "uncertainty_high": metrics["uncertainty_high"],
        "uncertainty_unit": metrics["uncertainty_unit"],
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
    }
    source_entry = {
        **row_evidence,
        "chembl_molecule_provenance_ref": f"{CHEMBL_MOLECULE_URL}/{molecule_id}.json",
        "chembl_molecule_payload": molecule_payload,
        "top_k_refinement_row": row,
    }
    return row, source_entry


def _update_receipt(
    *,
    repo_root: Path,
    bundle_row: dict[str, Any],
    row: dict[str, Any],
    source_artifact: Path,
    source_artifact_sha256: str,
    generated_at: str,
) -> str:
    receipt_ref = Path(str(bundle_row.get("receipt_ref") or ""))
    if not str(receipt_ref):
        raise ValueError("receipt_ref_missing")
    resolved = _resolve(repo_root, receipt_ref)
    if resolved.exists():
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
    else:
        payload = {}
    if not payload:
        payload = dict(bundle_row.get("receipt_template_payload") or {})
    payload.update(
        {
            "status": "complete",
            "completed_at": generated_at,
            "case_id": row["case_id"],
            "source_family": row["source_family"],
            "top_k_rank": row["top_k_rank"],
            "candidate_id": row["candidate_id"],
            "upstream_top_k_provenance_ref": row["upstream_top_k_provenance_ref"],
            "upstream_top_k_source_checksum": row["upstream_top_k_source_checksum"],
            "pre_refinement_energy_proxy": row["pre_refinement_energy_proxy"],
            "post_refinement_energy_proxy": row["post_refinement_energy_proxy"],
            "local_min_survived": row["local_min_survived"],
            "contact_persistence_rate": row["contact_persistence_rate"],
            "h_bond_persistence_rate": row["h_bond_persistence_rate"],
            "clash_count_before": row["clash_count_before"],
            "clash_count_after": row["clash_count_after"],
            "uncertainty_low": row["uncertainty_low"],
            "uncertainty_high": row["uncertainty_high"],
            "uncertainty_unit": row["uncertainty_unit"],
            "provenance_ref": row["provenance_ref"],
            "source_checksum": row["source_checksum"],
            "top_k_refinement_row": row,
            "operator_input_source": {
                "source_id": SOURCE_ID,
                "source_url": CHEMBL_MOLECULE_URL,
                "source_license": SOURCE_LICENSE,
                "source_artifact": str(source_artifact),
                "source_artifact_sha256": source_artifact_sha256,
            },
            "claim_boundary": (
                "Receipt records bounded PocketMD Lite ligand-only RDKit "
                "minimization metrics for upstream GPCR ChEMBL top-k candidates. "
                "It does not assert receptor-bound all-atom MD, FEP, or long "
                "timescale dynamics."
            ),
        }
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return str(receipt_ref)


def materialize_pocketmd_lite_gpcr_chembl_refinement_receipts(
    *,
    repo_root: Path = ROOT,
    gpcr_rows: Path = DEFAULT_GPCR_ROWS,
    receipt_bundle: Path = DEFAULT_RECEIPT_BUNDLE,
    source_out: Path = DEFAULT_SOURCE_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    target_order: tuple[str, ...] = DEFAULT_TARGET_ORDER,
    candidates_per_target: int = DEFAULT_CANDIDATES_PER_TARGET,
) -> dict[str, Any]:
    generated_at = _now_utc_iso()
    gpcr_payload = _load_json(repo_root, gpcr_rows)
    bundle_payload = _load_json(repo_root, receipt_bundle)
    selected_candidates = _select_topk_candidates(
        _gpcr_rows(gpcr_payload),
        target_order=target_order,
        candidates_per_target=candidates_per_target,
    )
    receipt_refs = _receipt_refs_by_slot(bundle_payload)
    molecule_payloads: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []
    blockers: list[str] = []

    for index, selected in enumerate(selected_candidates, start=1):
        gpcr_row = selected["gpcr_row"]
        molecule_id = str(gpcr_row["molecule_id"])
        try:
            molecule_payload = molecule_payloads.setdefault(
                molecule_id,
                _fetch_chembl_molecule(molecule_id),
            )
            smiles = _canonical_smiles(molecule_payload, molecule_id)
            metrics = _refinement_metrics(smiles, seed_base=7300 + index * 100)
            row, source_entry = _row_and_source_entry(
                selected=selected,
                molecule_payload=molecule_payload,
                metrics=metrics,
            )
        except Exception as exc:
            blockers.append(f"{selected['case_id']}:rank_{selected['top_k_rank']}:{exc}")
            continue
        rows.append(row)
        source_entries.append(source_entry)

    source_payload = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py"),
                gpcr_rows,
                receipt_bundle,
            ],
            reused_evidence=False,
            reuse_policy="gpcr_chembl_topk_ligand_rdkit_refinement_receipt_source",
            repo_root=repo_root,
        ),
        "generated_at": generated_at,
        "source_id": SOURCE_ID,
        "source_url": CHEMBL_MOLECULE_URL,
        "source_license": SOURCE_LICENSE,
        "source_version": SOURCE_VERSION,
        "rdkit_version": rdBase.rdkitVersion,
        "target_order": list(target_order),
        "candidates_per_target": candidates_per_target,
        "method": {
            "method_id": "rdkit_etkdg3_mmff94s_or_uff_ligand_only_minimization",
            "embedding": "ETKDGv3 deterministic seeds",
            "primary_metric_conformer": "first seeded conformer",
            "uncertainty_proxy": "population standard deviation across three post-minimization conformer energies around the primary energy delta",
            "contact_proxy": "intramolecular heavy-atom contact retention after minimization",
            "h_bond_proxy": "intramolecular donor-acceptor retention after minimization",
            "claim_boundary": (
                "Ligand-only refinement proxy for PocketMD Lite top-k survival; "
                "not a receptor-bound all-atom MD, FEP, or de novo binding mode claim."
            ),
        },
        "upstream_gpcr_rows_artifact": str(gpcr_rows),
        "upstream_gpcr_rows_sha256": file_sha256(_resolve(repo_root, gpcr_rows)),
        "top_k_refinement_rows": rows,
        "source_entries": source_entries,
    }
    _write_json(repo_root, source_out, source_payload)
    source_sha = file_sha256(_resolve(repo_root, source_out))

    completed_receipts: list[str] = []
    for row in rows:
        slot_key = (str(row["case_id"]), int(row["top_k_rank"]))
        bundle_row = receipt_refs.get(slot_key)
        if not bundle_row:
            blockers.append(f"{row['case_id']}:rank_{row['top_k_rank']}:receipt_slot_missing")
            continue
        completed_receipts.append(
            _update_receipt(
                repo_root=repo_root,
                bundle_row=bundle_row,
                row=row,
                source_artifact=source_out,
                source_artifact_sha256=source_sha,
                generated_at=generated_at,
            )
        )

    required_count = len(target_order) * candidates_per_target
    if len(rows) != required_count:
        blockers.append(
            f"top_k_refinement_row_count_mismatch:{len(rows)}_of_{required_count}"
        )
    if len(completed_receipts) != required_count:
        blockers.append(
            f"completed_receipt_count_mismatch:{len(completed_receipts)}_of_{required_count}"
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py"),
                gpcr_rows,
                receipt_bundle,
                source_out,
            ],
            reused_evidence=False,
            reuse_policy="gpcr_chembl_topk_ligand_rdkit_refinement_receipts",
            repo_root=repo_root,
        ),
        "status": "receipts_materialized" if not blockers else "blocked",
        "contract_pass": not blockers,
        "generated_at": generated_at,
        "source_id": SOURCE_ID,
        "source_url": CHEMBL_MOLECULE_URL,
        "source_license": SOURCE_LICENSE,
        "source_version": SOURCE_VERSION,
        "source_artifact": str(source_out),
        "source_artifact_sha256": source_sha,
        "target_order": list(target_order),
        "required_receipt_count": required_count,
        "top_k_refinement_row_count": len(rows),
        "completed_receipt_count": len(completed_receipts),
        "completed_receipts": completed_receipts,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "claim_boundary": source_payload["method"]["claim_boundary"],
        "next_commands": {
            "materialize_rows_from_receipt_bundle": (
                "python3 scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py "
                "--receipt-bundle implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_refinement_receipt_bundle.json "
                "--out-rows implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_topk_rows.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_topk_rows_from_receipt_bundle_report.json --fail-blocked"
            ),
        },
    }
    _write_json(repo_root, report_out, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--gpcr-rows", type=Path, default=DEFAULT_GPCR_ROWS)
    parser.add_argument("--receipt-bundle", type=Path, default=DEFAULT_RECEIPT_BUNDLE)
    parser.add_argument("--source-out", type=Path, default=DEFAULT_SOURCE_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--target-order", nargs="+", default=list(DEFAULT_TARGET_ORDER))
    parser.add_argument("--candidates-per-target", type=int, default=DEFAULT_CANDIDATES_PER_TARGET)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_pocketmd_lite_gpcr_chembl_refinement_receipts(
        repo_root=args.repo_root,
        gpcr_rows=args.gpcr_rows,
        receipt_bundle=args.receipt_bundle,
        source_out=args.source_out,
        report_out=args.report_out,
        target_order=tuple(args.target_order),
        candidates_per_target=args.candidates_per_target,
    )
    print(
        f"{payload['status']} | rows={payload['top_k_refinement_row_count']} | "
        f"receipts={payload['completed_receipt_count']} | blockers={payload['blocker_count']}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
