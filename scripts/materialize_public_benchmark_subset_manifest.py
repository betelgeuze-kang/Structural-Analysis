#!/usr/bin/env python3
"""Materialize a public benchmark subset manifest from local operator intake."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from validate_public_benchmark_subset_manifest import (  # noqa: E402
    LOCAL_SOURCE_FILE_FIELDS,
    REQUIRED_POSE_SUCCESS_METRIC,
    REQUIRED_CASE_FIELDS,
    SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS,
    source_material_coverage_summary,
    validate_subset_manifest,
)


SCHEMA_VERSION = "public-benchmark-subset-materialization.v1"
MANIFEST_SCHEMA_VERSION = "public-benchmark-subset-manifest.v1"
DEFAULT_TARGET_SUBSET_CASE_COUNT = 12


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _stable_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _path_key(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _resolve_local_path(value: Any, *, repo_root: Path, intake_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text or "://" in text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    repo_candidate = repo_root / path
    if repo_candidate.exists():
        return repo_candidate
    return intake_dir / path


def _case_row_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "complex_id": "",
        "protein_structure_path": "",
        "reference_ligand_path": "",
        "predicted_ligand_path_or_docking_run_id": "",
        "ligand_atom_order_contract": {
            "atom_count": 0,
            "atom_ids": [],
            "atom_id_basis": "reference_ligand_atom_order",
        },
        "symmetry_permutation_contract": {
            "permutations": [],
            "permutation_basis": "zero_based_indices_into_ligand_atom_order_contract.atom_ids",
        },
        "source_license_or_accession": "",
        "source_checksum": "",
        "provenance_ref": "",
        "pose_success_metric": REQUIRED_POSE_SUCCESS_METRIC,
        "rmsd_threshold_angstrom": 2.0,
    }


def _materialize_case(
    row: dict[str, Any],
    *,
    index: int,
    repo_root: Path,
    intake_dir: Path,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    case: dict[str, Any] = {field: row.get(field, "") for field in REQUIRED_CASE_FIELDS}
    case["source_family"] = row.get("source_family") or "CASF/PDBBind"
    case["ligand_atom_order_contract"] = _as_dict(row.get("ligand_atom_order_contract"))
    case["symmetry_permutation_contract"] = _as_dict(row.get("symmetry_permutation_contract"))

    blockers: list[str] = []
    source_file_checksums: dict[str, str] = {}
    for field in LOCAL_SOURCE_FILE_FIELDS:
        resolved = _resolve_local_path(row.get(field), repo_root=repo_root, intake_dir=intake_dir)
        if resolved is None or not resolved.exists() or not resolved.is_file():
            blockers.append(f"case_row_{index}:{field}_local_file_missing")
            continue
        source_file_checksums[_path_key(resolved, repo_root=repo_root)] = _sha256(resolved)

    declared_checksum = str(row.get("source_checksum") or "").strip()
    case["source_checksum"] = (
        declared_checksum if declared_checksum else _stable_sha256(source_file_checksums)
    )
    case["source_file_checksums"] = source_file_checksums
    case["materialization_blockers"] = blockers
    return case, blockers, source_file_checksums


def materialize_subset_manifest(
    intake_payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
    target_subset_case_count: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    intake_dir = (intake_path.parent if intake_path is not None else repo_root).resolve()
    raw_cases = [row for row in _as_list(intake_payload.get("cases")) if isinstance(row, dict)]
    target_count = int(
        target_subset_case_count
        or intake_payload.get("target_subset_case_count")
        or DEFAULT_TARGET_SUBSET_CASE_COUNT
    )

    rows: list[dict[str, Any]] = []
    materialization_blockers: list[str] = []
    checksum_map: dict[str, str] = {}
    for index, raw_case in enumerate(raw_cases):
        row, blockers, file_checksums = _materialize_case(
            raw_case,
            index=index,
            repo_root=repo_root,
            intake_dir=intake_dir,
        )
        rows.append(row)
        materialization_blockers.extend(blockers)
        checksum_map.update(file_checksums)

    validation = validate_subset_manifest(
        {
            "target_subset_case_count": target_count,
            "case_rows": rows,
        }
    )
    source_material_coverage = source_material_coverage_summary(
        rows,
        target_subset_case_count=target_count,
    )
    blockers = [*validation["blockers"], *materialization_blockers]
    ready = not blockers
    intake_paths = [
        Path("scripts/materialize_public_benchmark_subset_manifest.py"),
        Path("scripts/validate_public_benchmark_subset_manifest.py"),
    ]
    if intake_path is not None:
        intake_paths.append(intake_path)

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=intake_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_subset_manifest_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "source_material_required",
        "contract_pass": True,
        "public_benchmark_ready": ready,
        "target_subset_case_count": target_count,
        "materialized_case_count": len(rows),
        "source_families": ["CASF/PDBBind"],
        "source_material_coverage": source_material_coverage,
        "case_row_schema": {
            "required_fields": list(REQUIRED_CASE_FIELDS),
            "template": _case_row_template(),
            "supported_benchmark_splits": list(SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS),
            "validation_command": (
                "python3 scripts/validate_public_benchmark_subset_manifest.py "
                "--manifest <materialized-subset-manifest.json> --fail-blocked"
            ),
        },
        "case_rows": rows,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "intake_case_count": len(raw_cases),
            "materialized_case_count": len(rows),
            "source_file_checksum_count": len(checksum_map),
            "source_file_checksum_case_count": source_material_coverage[
                "source_file_checksum_case_count"
            ],
            "ligand_atom_order_contract_case_count": source_material_coverage[
                "ligand_atom_order_contract_case_count"
            ],
            "symmetry_permutation_contract_case_count": source_material_coverage[
                "symmetry_permutation_contract_case_count"
            ],
            "receipt_complete_case_count": source_material_coverage[
                "receipt_complete_case_count"
            ],
            "benchmark_split_counts": source_material_coverage[
                "benchmark_split_counts"
            ],
            "source_file_missing_count": len(materialization_blockers),
            "validation_blocker_count": int(validation["blocker_count"]),
            "materialization_blocker_count": len(materialization_blockers),
            "public_benchmark_ready": ready,
            "source_material_coverage": source_material_coverage,
            "source_file_checksums": dict(sorted(checksum_map.items())),
        },
        "claim_boundary": (
            "This manifest is materialized only from local operator-attached CASF/PDBBind "
            "case descriptors and files. The materializer computes checksums and validates "
            "the subset contract, but it does not download benchmark data, approve licenses, "
            "redistribute source files, or claim benchmark performance."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--target-subset-case-count", type=int)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intake_payload = json.loads(args.intake.read_text(encoding="utf-8"))
    manifest = materialize_subset_manifest(
        intake_payload,
        repo_root=args.repo_root,
        intake_path=args.intake,
        target_subset_case_count=args.target_subset_case_count,
    )
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(_json_text(manifest), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(manifest["materialization_report"]),
            encoding="utf-8",
        )
    report = manifest["materialization_report"]
    print(
        "public-benchmark-subset-materialization: "
        f"{manifest['status']} | cases={manifest['materialized_case_count']}/"
        f"{manifest['target_subset_case_count']} | "
        f"source_files={report['source_file_checksum_count']} | "
        f"blockers={len(manifest['blockers'])}"
    )
    return 1 if args.fail_blocked and not manifest["public_benchmark_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
