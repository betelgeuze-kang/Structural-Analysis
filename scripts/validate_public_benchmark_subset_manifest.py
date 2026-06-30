#!/usr/bin/env python3
"""Validate the Phase 2 public benchmark subset manifest contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "public-benchmark-subset-manifest-validation.v1"
REQUIRED_POSE_SUCCESS_METRIC = "symmetry_aware_ligand_rmsd_angstrom"
SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS = (
    "CASF-core",
    "PDBBind-core",
    "PDBBind-refined",
    "PDBBind-general",
)
LOCAL_SOURCE_FILE_FIELDS = (
    "protein_structure_path",
    "reference_ligand_path",
    "predicted_ligand_path_or_docking_run_id",
)
REQUIRED_CASE_FIELDS = (
    "case_id",
    "source_family",
    "benchmark_split",
    "complex_id",
    "protein_structure_path",
    "reference_ligand_path",
    "predicted_ligand_path_or_docking_run_id",
    "ligand_atom_order_contract",
    "symmetry_permutation_contract",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
    "pose_success_metric",
    "rmsd_threshold_angstrom",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_sha256_ref(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "").strip()))


def _path_key(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").lstrip("./")


def _counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _complete_source_file_checksums(row: dict[str, Any]) -> bool:
    source_file_checksums = row.get("source_file_checksums")
    if not isinstance(source_file_checksums, dict) or not source_file_checksums:
        return False
    checksum_path_keys = {_path_key(path_key) for path_key in source_file_checksums}
    for field in LOCAL_SOURCE_FILE_FIELDS:
        declared_path = _path_key(row.get(field))
        if not declared_path or declared_path not in checksum_path_keys:
            return False
        checksum = source_file_checksums.get(declared_path)
        if checksum is None:
            checksum = next(
                (
                    value
                    for path_key, value in source_file_checksums.items()
                    if _path_key(path_key) == declared_path
                ),
                "",
            )
        if not _is_sha256_ref(checksum):
            return False
    return True


def _complete_ligand_atom_order_contract(row: dict[str, Any]) -> bool:
    atom_order = row.get("ligand_atom_order_contract")
    if not isinstance(atom_order, dict):
        return False
    atom_count = int(atom_order.get("atom_count") or 0)
    atom_ids = _as_list(atom_order.get("atom_ids"))
    return bool(
        atom_count > 0
        and atom_ids
        and len(atom_ids) == atom_count
        and len({str(atom_id) for atom_id in atom_ids}) == len(atom_ids)
    )


def _complete_symmetry_permutation_contract(row: dict[str, Any]) -> bool:
    if not _complete_ligand_atom_order_contract(row):
        return False
    atom_order = row["ligand_atom_order_contract"]
    atom_count = int(atom_order.get("atom_count") or 0)
    expected = list(range(atom_count))
    symmetry = row.get("symmetry_permutation_contract")
    if not isinstance(symmetry, dict):
        return False
    permutations = _as_list(symmetry.get("permutations"))
    if not permutations or expected not in permutations:
        return False
    return all(
        isinstance(permutation, list) and sorted(permutation) == expected
        for permutation in permutations
    )


def _complete_receipt_fields(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("source_license_or_accession") or "").strip()
        and _is_sha256_ref(row.get("source_checksum"))
        and str(row.get("provenance_ref") or "").strip()
    )


def source_material_coverage_summary(
    case_rows: list[dict[str, Any]],
    *,
    target_subset_case_count: int,
) -> dict[str, Any]:
    materialized_count = len(case_rows)
    source_file_checksum_entry_count = sum(
        len(row.get("source_file_checksums"))
        for row in case_rows
        if isinstance(row.get("source_file_checksums"), dict)
    )
    valid_source_file_checksum_entry_count = sum(
        1
        for row in case_rows
        if isinstance(row.get("source_file_checksums"), dict)
        for checksum in row["source_file_checksums"].values()
        if _is_sha256_ref(checksum)
    )
    return {
        "target_subset_case_count": int(target_subset_case_count),
        "materialized_case_count": materialized_count,
        "missing_case_count": max(int(target_subset_case_count) - materialized_count, 0),
        "required_local_source_file_fields": list(LOCAL_SOURCE_FILE_FIELDS),
        "required_local_source_file_field_count": len(LOCAL_SOURCE_FILE_FIELDS),
        "expected_source_file_checksum_count": (
            materialized_count * len(LOCAL_SOURCE_FILE_FIELDS)
        ),
        "source_file_checksum_entry_count": source_file_checksum_entry_count,
        "valid_source_file_checksum_entry_count": (
            valid_source_file_checksum_entry_count
        ),
        "source_file_checksum_case_count": sum(
            1 for row in case_rows if _complete_source_file_checksums(row)
        ),
        "ligand_atom_order_contract_case_count": sum(
            1 for row in case_rows if _complete_ligand_atom_order_contract(row)
        ),
        "symmetry_permutation_contract_case_count": sum(
            1 for row in case_rows if _complete_symmetry_permutation_contract(row)
        ),
        "receipt_complete_case_count": sum(
            1 for row in case_rows if _complete_receipt_fields(row)
        ),
        "benchmark_split_counts": _counts(
            [str(row.get("benchmark_split") or "").strip() for row in case_rows]
        ),
        "claim_boundary": (
            "Coverage counts summarize local operator-attached CASF/PDBBind case rows. "
            "They prove manifest completeness only for declared rows and do not fetch, "
            "license, redistribute, or benchmark external source material."
        ),
    }


def _validate_case_row(row: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        value = row.get(field)
        if value in (None, "", [], {}):
            blockers.append(f"case_row_{index}:{field}_missing")
    source_checksum = str(row.get("source_checksum") or "").strip()
    if source_checksum and not _is_sha256_ref(source_checksum):
        blockers.append(f"case_row_{index}:source_checksum_invalid")
    if str(row.get("pose_success_metric") or "").strip() != REQUIRED_POSE_SUCCESS_METRIC:
        blockers.append(f"case_row_{index}:pose_success_metric_invalid")
    try:
        rmsd_threshold = float(row.get("rmsd_threshold_angstrom"))
    except (TypeError, ValueError):
        blockers.append(f"case_row_{index}:rmsd_threshold_angstrom_invalid")
    else:
        if rmsd_threshold <= 0:
            blockers.append(f"case_row_{index}:rmsd_threshold_angstrom_invalid")
    source_file_checksums = row.get("source_file_checksums")
    if not isinstance(source_file_checksums, dict) or not source_file_checksums:
        blockers.append(f"case_row_{index}:source_file_checksums_missing")
    else:
        if len(source_file_checksums) < len(LOCAL_SOURCE_FILE_FIELDS):
            blockers.append(f"case_row_{index}:source_file_checksums_incomplete")
        checksum_path_keys = {_path_key(path_key) for path_key in source_file_checksums}
        for field in LOCAL_SOURCE_FILE_FIELDS:
            declared_path = _path_key(row.get(field))
            if declared_path and declared_path not in checksum_path_keys:
                blockers.append(
                    f"case_row_{index}:source_file_checksum_for_{field}_missing"
                )
        for checksum_index, (path_key, checksum) in enumerate(source_file_checksums.items()):
            if not str(path_key).strip():
                blockers.append(
                    f"case_row_{index}:source_file_checksum_{checksum_index}_path_missing"
                )
            if not _is_sha256_ref(checksum):
                blockers.append(
                    f"case_row_{index}:source_file_checksum_{checksum_index}_invalid"
                )
    if row.get("source_family") not in {"CASF/PDBBind"}:
        blockers.append(f"case_row_{index}:unsupported_source_family")
    benchmark_split = str(row.get("benchmark_split") or "").strip()
    if benchmark_split and benchmark_split not in SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS:
        blockers.append(f"case_row_{index}:unsupported_benchmark_split")
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
            if atom_count > 0 and expected not in permutations:
                blockers.append(f"case_row_{index}:symmetry_identity_permutation_missing")
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
    coverage = source_material_coverage_summary(
        case_rows,
        target_subset_case_count=target_count,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if ready else "source_material_required",
        "contract_pass": True,
        "public_benchmark_ready": ready,
        "target_subset_case_count": target_count,
        "materialized_case_count": materialized_count,
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "source_material_coverage": coverage,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "claim_boundary": (
            "This validator checks the local subset manifest structure, required case-row "
            "fields, atom-order contracts, explicit symmetry permutations, and identity "
            "permutation coverage. It also requires a declared CASF/PDBBind benchmark "
            "split so subset rows remain traceable to their benchmark role. It does not "
            "download public benchmark files, verify redistribution rights beyond "
            "declared fields, or claim benchmark performance."
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
