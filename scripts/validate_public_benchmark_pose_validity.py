#!/usr/bin/env python3
"""Validate PoseBusters-style public benchmark pose sanity checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from score_symmetry_aware_ligand_rmsd import (  # noqa: E402
    DEFAULT_THRESHOLD_ANGSTROM,
    coordinates_array,
    score_symmetry_aware_rmsd,
)


SCHEMA_VERSION = "public-benchmark-pose-validity-validation.v1"
DEFAULT_MIN_INTERATOMIC_DISTANCE_ANGSTROM = 0.35
REQUIRED_POSE_SUCCESS_METRIC = "symmetry_aware_ligand_rmsd_angstrom"
REQUIRED_POSE_FIELDS = (
    "case_id",
    "pose_success_metric",
    "benchmark_split",
    "reference_atoms",
    "predicted_atoms",
    "ligand_atom_order_contract",
    "symmetry_permutation_contract",
    "protein_structure_path",
    "receptor_context",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _minimum_pairwise_distance(coords: np.ndarray) -> float:
    if coords.shape[0] < 2:
        return float("inf")
    deltas = coords[:, None, :] - coords[None, :, :]
    distances = np.sqrt(np.sum(deltas * deltas, axis=2))
    distances = distances + np.eye(coords.shape[0]) * 1.0e9
    return float(np.min(distances))


def _validate_atom_order_contract(
    row: dict[str, Any],
    *,
    atom_count: int,
    case_id: str,
) -> list[str]:
    blockers: list[str] = []
    contract = row.get("ligand_atom_order_contract")
    if not isinstance(contract, dict):
        return [f"{case_id}:ligand_atom_order_contract_missing"]
    declared_count = int(contract.get("atom_count") or 0)
    atom_ids = _as_list(contract.get("atom_ids"))
    if declared_count != atom_count:
        blockers.append(f"{case_id}:ligand_atom_order_atom_count_mismatch")
    if atom_ids and len(atom_ids) != atom_count:
        blockers.append(f"{case_id}:ligand_atom_order_atom_ids_count_mismatch")
    return blockers


def _validate_symmetry_contract(
    row: dict[str, Any],
    *,
    atom_count: int,
    case_id: str,
) -> list[str]:
    contract = row.get("symmetry_permutation_contract")
    if not isinstance(contract, dict):
        return [f"{case_id}:symmetry_permutation_contract_missing"]
    permutations = _as_list(contract.get("permutations"))
    if not permutations:
        return [f"{case_id}:symmetry_permutations_missing"]
    expected = list(range(atom_count))
    blockers: list[str] = []
    for index, permutation in enumerate(permutations):
        if not isinstance(permutation, list) or sorted(permutation) != expected:
            blockers.append(f"{case_id}:symmetry_permutation_{index}_invalid")
    return blockers


def validate_pose_case(
    row: dict[str, Any],
    *,
    min_interatomic_distance_angstrom: float = DEFAULT_MIN_INTERATOMIC_DISTANCE_ANGSTROM,
) -> dict[str, Any]:
    case_id = str(row.get("case_id") or "case_without_id")
    blockers: list[str] = []
    for field in REQUIRED_POSE_FIELDS:
        if row.get(field) in (None, "", [], {}):
            blockers.append(f"{case_id}:{field}_missing")
    if str(row.get("pose_success_metric") or "").strip() != REQUIRED_POSE_SUCCESS_METRIC:
        blockers.append(f"{case_id}:pose_success_metric_invalid")
    try:
        reference = coordinates_array(row.get("reference_atoms", []))
        predicted = coordinates_array(row.get("predicted_atoms", []))
    except Exception as exc:
        return {
            "case_id": case_id,
            "status": "blocked",
            "pass": False,
            "blockers": [*blockers, f"{case_id}:coordinate_finiteness_failed:{exc.__class__.__name__}"],
        }
    if reference.shape != predicted.shape:
        blockers.append(f"{case_id}:reference_predicted_atom_count_mismatch")
    atom_count = int(reference.shape[0])
    blockers.extend(_validate_atom_order_contract(row, atom_count=atom_count, case_id=case_id))
    blockers.extend(_validate_symmetry_contract(row, atom_count=atom_count, case_id=case_id))
    minimum_distance = _minimum_pairwise_distance(predicted)
    if minimum_distance < min_interatomic_distance_angstrom:
        blockers.append(f"{case_id}:minimum_interatomic_distance_guard_failed")
    rmsd_score: dict[str, Any] = {}
    if not any("symmetry" in blocker or "atom_count" in blocker for blocker in blockers):
        try:
            rmsd_score = score_symmetry_aware_rmsd(
                reference_atoms=row["reference_atoms"],
                predicted_atoms=row["predicted_atoms"],
                symmetry_permutations=row["symmetry_permutation_contract"]["permutations"],
                threshold_angstrom=float(
                    row.get("rmsd_threshold_angstrom", DEFAULT_THRESHOLD_ANGSTROM)
                ),
            )
        except Exception as exc:
            blockers.append(f"{case_id}:symmetry_aware_rmsd_failed:{exc.__class__.__name__}")
    if rmsd_score and not rmsd_score["pose_success"]:
        blockers.append(f"{case_id}:symmetry_aware_ligand_rmsd_above_threshold")
    return {
        "case_id": case_id,
        "status": "pass" if not blockers else "blocked",
        "pass": not blockers,
        "atom_count": atom_count,
        "minimum_interatomic_distance_angstrom": minimum_distance,
        "min_interatomic_distance_threshold_angstrom": float(min_interatomic_distance_angstrom),
        "rmsd_score": rmsd_score,
        "blockers": blockers,
    }


def validate_pose_validity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cases = payload.get("cases")
    if cases is None:
        cases = [payload]
    case_rows = [row for row in _as_list(cases) if isinstance(row, dict)]
    rows = [validate_pose_case(row) for row in case_rows]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    dry_run_case_count = sum(
        1 for row in case_rows if str(row.get("source_family", "")).lower() in {"synthetic", "dry_run"}
    )
    real_case_count = max(len(case_rows) - dry_run_case_count, 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pass" if rows and not blockers else "blocked",
        "contract_pass": bool(rows and not blockers),
        "pose_validity_ready": bool(rows and not blockers),
        "case_count": len(rows),
        "dry_run_case_count": dry_run_case_count,
        "real_benchmark_case_count": real_case_count,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "rows": rows,
        "claim_boundary": (
            "This validator performs local coordinate, atom-order, symmetry permutation, "
            "minimum-distance, receptor-context, and RMSD sanity checks. It does not infer "
            "bond orders, protonation, tautomer equivalence, docking protocol validity, or "
            "public benchmark performance."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = validate_pose_validity_payload(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_json_text(result), encoding="utf-8")
    print(
        "public-benchmark-pose-validity-validation: "
        f"{result['status']} | cases={result['case_count']} | blockers={result['blocker_count']}"
    )
    return 1 if args.fail_blocked and not result["pose_validity_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
