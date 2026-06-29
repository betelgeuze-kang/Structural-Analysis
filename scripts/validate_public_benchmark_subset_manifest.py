#!/usr/bin/env python3
"""Validate the Phase 2 public benchmark subset manifest contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "public-benchmark-subset-manifest-validation.v1"
REQUIRED_CASE_FIELDS = (
    "case_id",
    "source_family",
    "complex_id",
    "protein_structure_path",
    "reference_ligand_path",
    "predicted_ligand_path_or_docking_run_id",
    "ligand_atom_order_contract",
    "symmetry_permutation_contract",
    "source_license_or_accession",
    "source_checksum",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _validate_case_row(row: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        value = row.get(field)
        if value in (None, "", [], {}):
            blockers.append(f"case_row_{index}:{field}_missing")
    if row.get("source_family") not in {"CASF/PDBBind"}:
        blockers.append(f"case_row_{index}:unsupported_source_family")
    atom_order = row.get("ligand_atom_order_contract")
    if isinstance(atom_order, dict):
        atom_count = int(atom_order.get("atom_count") or 0)
        atom_ids = _as_list(atom_order.get("atom_ids"))
        if atom_count <= 0:
            blockers.append(f"case_row_{index}:atom_count_missing")
        if not atom_ids:
            blockers.append(f"case_row_{index}:atom_ids_missing")
        if atom_ids and atom_count and len(atom_ids) != atom_count:
            blockers.append(f"case_row_{index}:atom_ids_count_mismatch")
        if atom_ids and len({str(atom_id) for atom_id in atom_ids}) != len(atom_ids):
            blockers.append(f"case_row_{index}:atom_ids_not_unique")
    symmetry = row.get("symmetry_permutation_contract")
    if isinstance(symmetry, dict):
        permutations = _as_list(symmetry.get("permutations"))
        if not permutations:
            blockers.append(f"case_row_{index}:symmetry_permutations_missing")
        elif atom_order and isinstance(atom_order, dict):
            atom_count = int(atom_order.get("atom_count") or 0)
            expected = list(range(atom_count))
            for permutation_index, permutation in enumerate(permutations):
                if not isinstance(permutation, list) or sorted(permutation) != expected:
                    blockers.append(
                        f"case_row_{index}:symmetry_permutation_{permutation_index}_invalid"
                    )
    return blockers


def validate_subset_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    target_count = int(payload.get("target_subset_case_count") or 0)
    case_rows = [row for row in _as_list(payload.get("case_rows")) if isinstance(row, dict)]
    row_blockers = [
        blocker
        for index, row in enumerate(case_rows)
        for blocker in _validate_case_row(row, index=index)
    ]
    materialized_count = len(case_rows)
    count_blockers: list[str] = []
    if target_count <= 0:
        count_blockers.append("target_subset_case_count_missing")
    if materialized_count < target_count:
        count_blockers.append("materialized_case_count_below_target")
    if len({str(row.get("case_id")) for row in case_rows}) != materialized_count:
        count_blockers.append("case_id_not_unique")
    blockers = [*count_blockers, *row_blockers]
    ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if ready else "source_material_required",
        "contract_pass": True,
        "public_benchmark_ready": ready,
        "target_subset_case_count": target_count,
        "materialized_case_count": materialized_count,
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "claim_boundary": (
            "This validator checks the local subset manifest structure, required case-row "
            "fields, atom-order contracts, and explicit symmetry permutations. It does not "
            "download public benchmark files, verify redistribution rights beyond declared "
            "fields, or claim benchmark performance."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = validate_subset_manifest(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_json_text(result), encoding="utf-8")
    print(
        "public-benchmark-subset-manifest-validation: "
        f"{result['status']} | cases={result['materialized_case_count']}/"
        f"{result['target_subset_case_count']} | blockers={result['blocker_count']}"
    )
    return 1 if args.fail_blocked and not result["public_benchmark_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
