#!/usr/bin/env python3
"""Materialize a CASF/PDBBind pose-success harness from pose validity and RMSD rows."""

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
    is_non_actual_pose_case,
    pose_case_actuality_blockers,
)


SCHEMA_VERSION = "public-benchmark-pose-success-harness-materialization.v1"
HARNESS_SCHEMA_VERSION = "public-benchmark-pose-success-harness.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows_by_case_id(rows: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("case_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("case_id")
    }


def _harness_case_row(
    *,
    case_id: str,
    pose_row: dict[str, Any] | None,
    rmsd_row: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if pose_row is None:
        blockers.append(f"{case_id}:pose_validity_row_missing")
        pose_row = {}
    if rmsd_row is None:
        blockers.append(f"{case_id}:symmetry_rmsd_row_missing")
        rmsd_row = {}

    score = _as_dict(rmsd_row.get("score"))
    pose_validity_blockers = [
        str(blocker) for blocker in _as_list(pose_row.get("blockers"))
    ]
    if pose_validity_blockers:
        blockers.append(f"{case_id}:pose_validity_blocked")
    if rmsd_row and not score:
        blockers.append(f"{case_id}:symmetry_rmsd_score_missing")

    source_family = str(
        pose_row.get("source_family") or rmsd_row.get("source_family") or ""
    )
    benchmark_split = str(
        pose_row.get("benchmark_split") or rmsd_row.get("benchmark_split") or ""
    )
    actuality_row = {"case_id": case_id, "source_family": source_family}
    blockers.extend(pose_case_actuality_blockers(actuality_row))

    pose_validity_pass = bool(pose_row.get("pass"))
    pose_success = score.get("pose_success") if score else None
    if blockers:
        status = "blocked"
    elif pose_validity_pass and bool(pose_success):
        status = "pass"
    else:
        status = "pose_failed"

    return (
        {
            "case_id": case_id,
            "source_family": source_family,
            "benchmark_split": benchmark_split,
            "subset_manifest_case_checksum": str(
                pose_row.get("subset_manifest_case_checksum")
                or rmsd_row.get("subset_manifest_case_checksum")
                or ""
            ),
            "status": status,
            "pose_validity_pass": pose_validity_pass,
            "pose_validity_status": str(pose_row.get("status") or ""),
            "pose_success": bool(pose_success) if pose_success is not None else None,
            "symmetry_aware_ligand_rmsd_angstrom": (
                score.get("best_rmsd_angstrom") if score else None
            ),
            "rmsd_threshold_angstrom": score.get("threshold_angstrom") if score else None,
            "best_symmetry_permutation": score.get("best_permutation") if score else None,
            "pose_validity_check_results": [
                row
                for row in _as_list(pose_row.get("check_results"))
                if isinstance(row, dict)
            ],
            "pose_validity_blockers": pose_validity_blockers,
            "rmsd_blockers": [
                blocker for blocker in blockers if "rmsd" in blocker
            ],
            "blocker_count": len(blockers),
            "blockers": blockers,
        },
        blockers,
    )


def materialize_pose_success_harness(
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    pose_validity_packet_path: Path | None = None,
    rmsd_scorecard_path: Path | None = None,
) -> dict[str, Any]:
    pose_rows = [
        row
        for row in _as_list(pose_validity_packet.get("case_rows"))
        if isinstance(row, dict)
    ]
    rmsd_rows = [
        row for row in _as_list(rmsd_scorecard.get("rows")) if isinstance(row, dict)
    ]
    pose_by_case_id = _rows_by_case_id(pose_rows)
    rmsd_by_case_id = _rows_by_case_id(rmsd_rows)

    blockers: list[str] = []
    if not pose_rows:
        blockers.append("pose_validity_packet_case_rows_missing")
    if not rmsd_rows:
        blockers.append("symmetry_rmsd_scorecard_rows_missing")
    if pose_rows and not bool(pose_validity_packet.get("posebusters_validity_ready")):
        blockers.append("pose_validity_packet_not_ready")
    if rmsd_rows and not bool(rmsd_scorecard.get("scorecard_ready")):
        blockers.append("symmetry_rmsd_scorecard_not_ready")

    case_ids = sorted(set(pose_by_case_id) | set(rmsd_by_case_id))
    case_rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        row, row_blockers = _harness_case_row(
            case_id=case_id,
            pose_row=pose_by_case_id.get(case_id),
            rmsd_row=rmsd_by_case_id.get(case_id),
        )
        case_rows.append(row)
        blockers.extend(row_blockers)

    real_benchmark_case_count = sum(
        1 for row in case_rows if not is_non_actual_pose_case(row)
    )
    dry_run_case_count = max(len(case_rows) - real_benchmark_case_count, 0)
    if case_rows and real_benchmark_case_count == 0:
        blockers.append("real_benchmark_pose_success_cases_missing")

    blockers = list(dict.fromkeys(blockers))
    pose_success_count = sum(1 for row in case_rows if row["pose_success"] is True)
    pose_validity_pass_count = sum(1 for row in case_rows if row["pose_validity_pass"])
    harness_ready = bool(case_rows and real_benchmark_case_count > 0 and not blockers)
    input_paths = [Path("scripts/materialize_public_benchmark_pose_success_harness.py")]
    if pose_validity_packet_path is not None:
        input_paths.append(pose_validity_packet_path)
    if rmsd_scorecard_path is not None:
        input_paths.append(rmsd_scorecard_path)

    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_pose_success_harness_materialized_from_pose_packet_and_rmsd_scorecard",
            repo_root=repo_root,
        ),
        "status": "ready" if harness_ready else "pose_success_harness_materialization_required",
        "contract_pass": harness_ready,
        "pose_success_harness_ready": harness_ready,
        "real_benchmark_case_count": real_benchmark_case_count,
        "dry_run_case_count": dry_run_case_count,
        "case_count": len(case_rows),
        "pose_validity_pass_count": pose_validity_pass_count,
        "pose_validity_blocked_count": max(len(case_rows) - pose_validity_pass_count, 0),
        "pose_success_count": pose_success_count,
        "pose_failure_count": max(len(case_rows) - pose_success_count, 0),
        "pose_success_rate": (pose_success_count / len(case_rows)) if case_rows else 0.0,
        "case_rows": case_rows,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "pose_validity_packet_case_count": len(pose_rows),
            "rmsd_scorecard_case_count": len(rmsd_rows),
            "materialized_case_count": len(case_rows),
            "real_benchmark_case_count": real_benchmark_case_count,
            "dry_run_case_count": dry_run_case_count,
            "pose_validity_pass_count": pose_validity_pass_count,
            "pose_success_count": pose_success_count,
            "pose_failure_count": max(len(case_rows) - pose_success_count, 0),
            "blocker_count": len(blockers),
            "pose_success_harness_ready": harness_ready,
        },
        "claim_boundary": (
            "This harness joins an already materialized PoseBusters-style validity packet "
            "with a symmetry-aware ligand RMSD scorecard. It reports pose-success rows "
            "for operator-attached public benchmark cases, but it does not fetch CASF/"
            "PDBBind data, run docking engines, or claim Tier beta by itself."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-validity-packet", type=Path, required=True)
    parser.add_argument("--rmsd-scorecard", type=Path, required=True)
    parser.add_argument("--out-harness", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pose_validity_packet = json.loads(
        args.pose_validity_packet.read_text(encoding="utf-8")
    )
    rmsd_scorecard = json.loads(args.rmsd_scorecard.read_text(encoding="utf-8"))
    harness = materialize_pose_success_harness(
        pose_validity_packet,
        rmsd_scorecard,
        repo_root=args.repo_root,
        pose_validity_packet_path=args.pose_validity_packet,
        rmsd_scorecard_path=args.rmsd_scorecard,
    )
    args.out_harness.parent.mkdir(parents=True, exist_ok=True)
    args.out_harness.write_text(_json_text(harness), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(harness["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-pose-success-harness-materialization: "
        f"{harness['status']} | cases={harness['case_count']} | "
        f"real_cases={harness['real_benchmark_case_count']} | "
        f"pose_success={harness['pose_success_count']}/{harness['case_count']} | "
        f"blockers={len(harness['blockers'])}"
    )
    return 1 if args.fail_blocked and not harness["pose_success_harness_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
