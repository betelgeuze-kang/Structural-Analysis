#!/usr/bin/env python3
"""Materialize PoseBusters-style pose-validity input from local benchmark intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from validate_public_benchmark_pose_validity import (  # noqa: E402
    REQUIRED_POSE_FIELDS,
    validate_pose_validity_payload,
)


SCHEMA_VERSION = "public-benchmark-pose-validity-input-materialization.v1"
POSE_INPUT_SCHEMA_VERSION = "public-benchmark-pose-validity-input.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _subset_rows_by_case_id(subset_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("case_id")): row
        for row in _as_list(subset_manifest.get("case_rows"))
        if isinstance(row, dict) and row.get("case_id")
    }


def _materialize_pose_case(
    pose_row: dict[str, Any],
    *,
    index: int,
    subset_by_case_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    case_id = str(pose_row.get("case_id") or f"pose_case_{index}")
    subset_row = subset_by_case_id.get(case_id)
    blockers: list[str] = []
    if subset_row is None:
        blockers.append(f"{case_id}:case_id_not_in_subset_manifest")
        subset_row = {}

    case = {
        "case_id": case_id,
        "source_family": subset_row.get("source_family") or pose_row.get("source_family") or "CASF/PDBBind",
        "protein_structure_path": (
            subset_row.get("protein_structure_path")
            or pose_row.get("protein_structure_path")
            or ""
        ),
        "pose_success_metric": (
            subset_row.get("pose_success_metric")
            or pose_row.get("pose_success_metric")
            or ""
        ),
        "receptor_context": _as_dict(pose_row.get("receptor_context")),
        "reference_atoms": _as_list(pose_row.get("reference_atoms")),
        "predicted_atoms": _as_list(pose_row.get("predicted_atoms")),
        "ligand_atom_order_contract": (
            _as_dict(subset_row.get("ligand_atom_order_contract"))
            or _as_dict(pose_row.get("ligand_atom_order_contract"))
        ),
        "symmetry_permutation_contract": (
            _as_dict(subset_row.get("symmetry_permutation_contract"))
            or _as_dict(pose_row.get("symmetry_permutation_contract"))
        ),
        "rmsd_threshold_angstrom": pose_row.get(
            "rmsd_threshold_angstrom",
            subset_row.get("rmsd_threshold_angstrom", 2.0),
        ),
        "subset_manifest_case_checksum": str(subset_row.get("source_checksum") or ""),
    }
    case["materialization_blockers"] = blockers
    return case, blockers


def materialize_pose_validity_input(
    subset_manifest: dict[str, Any],
    pose_intake_payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    subset_manifest_path: Path | None = None,
    pose_intake_path: Path | None = None,
) -> dict[str, Any]:
    subset_by_case_id = _subset_rows_by_case_id(subset_manifest)
    pose_rows = [
        row for row in _as_list(pose_intake_payload.get("cases")) if isinstance(row, dict)
    ]
    cases: list[dict[str, Any]] = []
    materialization_blockers: list[str] = []
    for index, pose_row in enumerate(pose_rows):
        case, blockers = _materialize_pose_case(
            pose_row,
            index=index,
            subset_by_case_id=subset_by_case_id,
        )
        cases.append(case)
        materialization_blockers.extend(blockers)

    validation = validate_pose_validity_payload({"cases": cases})
    blockers = [*materialization_blockers, *validation["blockers"]]
    ready = bool(cases and not blockers)
    input_paths = [
        Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
        Path("scripts/validate_public_benchmark_pose_validity.py"),
    ]
    if subset_manifest_path is not None:
        input_paths.append(subset_manifest_path)
    if pose_intake_path is not None:
        input_paths.append(pose_intake_path)

    return {
        "schema_version": POSE_INPUT_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_pose_validity_input_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "pose_materialization_required",
        "contract_pass": ready,
        "pose_validity_ready": ready,
        "required_pose_fields": list(REQUIRED_POSE_FIELDS),
        "case_count": len(cases),
        "real_benchmark_case_count": validation["real_benchmark_case_count"],
        "cases": cases,
        "validation": validation,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "subset_manifest_case_count": len(subset_by_case_id),
            "pose_intake_case_count": len(pose_rows),
            "materialized_pose_case_count": len(cases),
            "materialization_blocker_count": len(materialization_blockers),
            "validation_blocker_count": int(validation["blocker_count"]),
            "pose_validity_ready": ready,
        },
        "claim_boundary": (
            "This input is materialized from a local subset manifest and operator-attached "
            "pose-coordinate intake. It validates coordinates, atom-order contracts, "
            "symmetry permutations, receptor context, and RMSD through the local validator, "
            "but it does not infer chemistry, download benchmark data, or claim benchmark performance."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--pose-intake", type=Path, required=True)
    parser.add_argument("--out-input", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    subset_manifest = json.loads(args.subset_manifest.read_text(encoding="utf-8"))
    pose_intake = json.loads(args.pose_intake.read_text(encoding="utf-8"))
    payload = materialize_pose_validity_input(
        subset_manifest,
        pose_intake,
        repo_root=args.repo_root,
        subset_manifest_path=args.subset_manifest,
        pose_intake_path=args.pose_intake,
    )
    args.out_input.parent.mkdir(parents=True, exist_ok=True)
    args.out_input.write_text(_json_text(payload), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(payload["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-pose-validity-input-materialization: "
        f"{payload['status']} | cases={payload['case_count']} | "
        f"real_cases={payload['real_benchmark_case_count']} | "
        f"blockers={len(payload['blockers'])}"
    )
    return 1 if args.fail_blocked and not payload["pose_validity_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
