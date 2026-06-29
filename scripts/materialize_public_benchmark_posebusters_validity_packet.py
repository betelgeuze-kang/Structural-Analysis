#!/usr/bin/env python3
"""Materialize a PoseBusters-style validity packet from pose-validity input."""

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
    SCHEMA_VERSION as VALIDATOR_SCHEMA_VERSION,
    validate_pose_validity_payload,
)


SCHEMA_VERSION = "public-benchmark-posebusters-style-validity-packet-materialization.v1"
PACKET_SCHEMA_VERSION = "public-benchmark-pose-validity-packet.v1"

CHECK_DEFINITIONS = [
    {
        "check_id": "coordinate_finiteness",
        "required": True,
        "description": "reference and predicted ligand coordinates are finite 3D values",
    },
    {
        "check_id": "atom_count_and_order_contract",
        "required": True,
        "description": "reference/predicted ligand atoms share a declared atom-order contract",
    },
    {
        "check_id": "symmetry_permutation_contract",
        "required": True,
        "description": "allowed symmetry permutations are explicit zero-based atom-index maps",
    },
    {
        "check_id": "minimum_interatomic_distance_guard",
        "required": True,
        "description": "predicted ligand coordinates must not contain impossible self-clashes",
    },
    {
        "check_id": "receptor_ligand_context_present",
        "required": True,
        "description": "protein structure and binding-site context are present",
    },
    {
        "check_id": "symmetry_aware_ligand_rmsd_angstrom",
        "required": True,
        "description": "pose success uses the best rigid-aligned RMSD over allowed symmetry permutations",
    },
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _case_source_family(row: dict[str, Any]) -> str:
    return str(row.get("source_family") or "").strip().lower()


def _blocker_check_id(blocker: str) -> str:
    token = blocker.split(":", maxsplit=1)[-1]
    if "coordinate_finiteness" in token or token in {
        "reference_atoms_missing",
        "predicted_atoms_missing",
    }:
        return "coordinate_finiteness"
    if "ligand_atom_order" in token or "atom_count" in token:
        return "atom_count_and_order_contract"
    if "symmetry_permutation" in token:
        return "symmetry_permutation_contract"
    if "minimum_interatomic_distance" in token:
        return "minimum_interatomic_distance_guard"
    if token in {"protein_structure_path_missing", "receptor_context_missing"}:
        return "receptor_ligand_context_present"
    if "symmetry_aware_ligand_rmsd" in token or "symmetry_aware_rmsd" in token:
        return "symmetry_aware_ligand_rmsd_angstrom"
    return "input_contract_completeness"


def _status_for_check(
    *,
    check_id: str,
    row: dict[str, Any],
    check_blockers: list[str],
) -> str:
    if check_blockers:
        return "blocked"
    if check_id == "coordinate_finiteness":
        return "pass" if row.get("atom_count") else "not_evaluated"
    if check_id == "minimum_interatomic_distance_guard":
        return "pass" if "minimum_interatomic_distance_angstrom" in row else "not_evaluated"
    if check_id == "symmetry_aware_ligand_rmsd_angstrom":
        return "pass" if row.get("rmsd_score") else "not_evaluated"
    return "pass"


def _case_packet_row(
    *,
    pose_case: dict[str, Any],
    validation_row: dict[str, Any],
) -> dict[str, Any]:
    blockers = _as_list(validation_row.get("blockers"))
    blockers_by_check: dict[str, list[str]] = {}
    for blocker in blockers:
        blockers_by_check.setdefault(_blocker_check_id(str(blocker)), []).append(str(blocker))

    check_results: list[dict[str, Any]] = []
    for definition in CHECK_DEFINITIONS:
        check_id = str(definition["check_id"])
        check_blockers = blockers_by_check.get(check_id, [])
        check_results.append(
            {
                "check_id": check_id,
                "status": _status_for_check(
                    check_id=check_id,
                    row=validation_row,
                    check_blockers=check_blockers,
                ),
                "required": bool(definition["required"]),
                "blockers": check_blockers,
            }
        )

    rmsd_score = validation_row.get("rmsd_score") if isinstance(
        validation_row.get("rmsd_score"),
        dict,
    ) else {}
    return {
        "case_id": str(validation_row.get("case_id") or pose_case.get("case_id") or ""),
        "source_family": str(pose_case.get("source_family") or ""),
        "subset_manifest_case_checksum": str(pose_case.get("subset_manifest_case_checksum") or ""),
        "status": str(validation_row.get("status") or "blocked"),
        "pass": bool(validation_row.get("pass")),
        "pose_success": bool(rmsd_score.get("pose_success")) if rmsd_score else False,
        "minimum_interatomic_distance_angstrom": validation_row.get(
            "minimum_interatomic_distance_angstrom"
        ),
        "best_rmsd_angstrom": rmsd_score.get("best_rmsd_angstrom") if rmsd_score else None,
        "check_results": check_results,
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def _check_summary(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for definition in CHECK_DEFINITIONS:
        check_id = str(definition["check_id"])
        statuses = [
            str(result["status"])
            for case in case_rows
            for result in _as_list(case.get("check_results"))
            if isinstance(result, dict) and result.get("check_id") == check_id
        ]
        summary.append(
            {
                **definition,
                "case_count": len(statuses),
                "pass_count": sum(1 for status in statuses if status == "pass"),
                "blocked_count": sum(1 for status in statuses if status == "blocked"),
                "not_evaluated_count": sum(
                    1 for status in statuses if status == "not_evaluated"
                ),
            }
        )
    return summary


def materialize_posebusters_validity_packet(
    pose_validity_input: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    pose_validity_input_path: Path | None = None,
) -> dict[str, Any]:
    cases = [
        row for row in _as_list(pose_validity_input.get("cases")) if isinstance(row, dict)
    ]
    validation = validate_pose_validity_payload({"cases": cases})
    blockers: list[str] = []
    if not cases:
        blockers.append("pose_validity_input_cases_missing")
    if not bool(pose_validity_input.get("pose_validity_ready")):
        blockers.append("pose_validity_input_not_ready")
    blockers.extend(str(blocker) for blocker in _as_list(validation.get("blockers")))

    dry_run_case_count = sum(
        1 for row in cases if _case_source_family(row) in {"synthetic", "dry_run"}
    )
    real_benchmark_case_count = max(len(cases) - dry_run_case_count, 0)
    if cases and real_benchmark_case_count == 0:
        blockers.append("real_benchmark_pose_cases_missing")

    validation_rows = [
        row for row in _as_list(validation.get("rows")) if isinstance(row, dict)
    ]
    case_rows = [
        _case_packet_row(pose_case=pose_case, validation_row=validation_row)
        for pose_case, validation_row in zip(cases, validation_rows)
    ]
    packet_ready = bool(
        case_rows
        and real_benchmark_case_count > 0
        and bool(pose_validity_input.get("pose_validity_ready"))
        and bool(validation.get("pose_validity_ready"))
        and not blockers
    )

    input_paths = [
        Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
        Path("scripts/validate_public_benchmark_pose_validity.py"),
    ]
    if pose_validity_input_path is not None:
        input_paths.append(pose_validity_input_path)

    pose_success_count = sum(1 for row in case_rows if row["pose_success"])
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="posebusters_style_validity_packet_materialized_from_pose_validity_input",
            repo_root=repo_root,
        ),
        "status": "ready" if packet_ready else "posebusters_validity_materialization_required",
        "contract_pass": packet_ready,
        "posebusters_validity_ready": packet_ready,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "real_benchmark_case_count": real_benchmark_case_count,
        "dry_run_case_count": dry_run_case_count,
        "case_count": len(case_rows),
        "pose_success_count": pose_success_count,
        "pose_failure_count": max(len(case_rows) - pose_success_count, 0),
        "checks": CHECK_DEFINITIONS,
        "check_summary": _check_summary(case_rows),
        "case_rows": case_rows,
        "validation": validation,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "pose_validity_input_case_count": len(cases),
            "materialized_case_count": len(case_rows),
            "real_benchmark_case_count": real_benchmark_case_count,
            "dry_run_case_count": dry_run_case_count,
            "pose_success_count": pose_success_count,
            "pose_failure_count": max(len(case_rows) - pose_success_count, 0),
            "blocker_count": len(blockers),
            "posebusters_validity_ready": packet_ready,
        },
        "posebusters_style_boundary": (
            "This packet materializes local PoseBusters-style sanity results from "
            "operator-attached pose-validity input. It does not vendor PoseBusters, "
            "infer bond orders, redistribute public benchmark files, compare docking "
            "engines, or claim Tier beta."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-validity-input", type=Path, required=True)
    parser.add_argument("--out-packet", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pose_validity_input = json.loads(args.pose_validity_input.read_text(encoding="utf-8"))
    packet = materialize_posebusters_validity_packet(
        pose_validity_input,
        repo_root=args.repo_root,
        pose_validity_input_path=args.pose_validity_input,
    )
    args.out_packet.parent.mkdir(parents=True, exist_ok=True)
    args.out_packet.write_text(_json_text(packet), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(packet["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-posebusters-validity-packet-materialization: "
        f"{packet['status']} | cases={packet['case_count']} | "
        f"real_cases={packet['real_benchmark_case_count']} | "
        f"pose_success={packet['pose_success_count']}/{packet['case_count']} | "
        f"blockers={len(packet['blockers'])}"
    )
    return 1 if args.fail_blocked and not packet["posebusters_validity_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
