#!/usr/bin/env python3
"""Materialize a symmetry-aware RMSD scorecard from pose-validity input."""

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
from score_symmetry_aware_ligand_rmsd import (  # noqa: E402
    DEFAULT_THRESHOLD_ANGSTROM,
    score_symmetry_aware_rmsd,
)


SCHEMA_VERSION = "public-benchmark-rmsd-scorecard-materialization.v1"
SCORECARD_SCHEMA_VERSION = "public-benchmark-symmetry-rmsd-scorecard.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _case_source_family(row: dict[str, Any]) -> str:
    return str(row.get("source_family") or "").strip().lower()


def _score_case(row: dict[str, Any]) -> dict[str, Any]:
    threshold = float(row.get("rmsd_threshold_angstrom", DEFAULT_THRESHOLD_ANGSTROM))
    score = score_symmetry_aware_rmsd(
        reference_atoms=row.get("reference_atoms", []),
        predicted_atoms=row.get("predicted_atoms", []),
        symmetry_permutations=row.get("symmetry_permutation_contract", {}).get(
            "permutations"
        ),
        threshold_angstrom=threshold,
    )
    return {
        "case_id": str(row.get("case_id") or ""),
        "source_family": str(row.get("source_family") or ""),
        "benchmark_split": str(row.get("benchmark_split") or ""),
        "subset_manifest_case_checksum": str(row.get("subset_manifest_case_checksum") or ""),
        "score": score,
    }


def materialize_rmsd_scorecard(
    pose_validity_input: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    pose_validity_input_path: Path | None = None,
) -> dict[str, Any]:
    cases = [
        row for row in _as_list(pose_validity_input.get("cases")) if isinstance(row, dict)
    ]
    blockers: list[str] = []
    if not cases:
        blockers.append("pose_validity_input_cases_missing")
    if pose_validity_input and not bool(pose_validity_input.get("pose_validity_ready")):
        blockers.append("pose_validity_input_not_ready")

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(cases):
        try:
            rows.append(_score_case(row))
        except Exception as exc:
            case_id = str(row.get("case_id") or f"case_{index}")
            blockers.append(
                f"{case_id}:symmetry_aware_rmsd_score_failed:{exc.__class__.__name__}"
            )

    dry_run_case_count = sum(
        1 for row in cases if _case_source_family(row) in {"synthetic", "dry_run"}
    )
    real_benchmark_case_count = max(len(cases) - dry_run_case_count, 0)
    if cases and real_benchmark_case_count == 0:
        blockers.append("real_benchmark_rmsd_cases_missing")
    pose_success_count = sum(1 for row in rows if row["score"]["pose_success"])
    scorecard_ready = bool(rows and real_benchmark_case_count > 0 and not blockers)
    input_paths = [
        Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
        Path("scripts/score_symmetry_aware_ligand_rmsd.py"),
    ]
    if pose_validity_input_path is not None:
        input_paths.append(pose_validity_input_path)

    return {
        "schema_version": SCORECARD_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_rmsd_scorecard_materialized_from_pose_validity_input",
            repo_root=repo_root,
        ),
        "status": "ready" if scorecard_ready else "rmsd_materialization_required",
        "contract_pass": scorecard_ready,
        "scorecard_ready": scorecard_ready,
        "real_benchmark_case_count": real_benchmark_case_count,
        "dry_run_case_count": dry_run_case_count,
        "case_count": len(rows),
        "pose_success_count": pose_success_count,
        "pose_failure_count": max(len(rows) - pose_success_count, 0),
        "pose_success_rate": (pose_success_count / len(rows)) if rows else 0.0,
        "rows": rows,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "pose_validity_input_case_count": len(cases),
            "scored_case_count": len(rows),
            "real_benchmark_case_count": real_benchmark_case_count,
            "pose_success_count": pose_success_count,
            "pose_failure_count": max(len(rows) - pose_success_count, 0),
            "blocker_count": len(blockers),
            "scorecard_ready": scorecard_ready,
        },
        "claim_boundary": (
            "This scorecard computes symmetry-aware ligand RMSD from already materialized "
            "pose-validity input. It reports pose-success metrics but does not infer "
            "chemistry, license benchmark data, compare against Vina/GNINA, or claim Tier beta."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-validity-input", type=Path, required=True)
    parser.add_argument("--out-scorecard", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pose_validity_input = json.loads(args.pose_validity_input.read_text(encoding="utf-8"))
    scorecard = materialize_rmsd_scorecard(
        pose_validity_input,
        repo_root=args.repo_root,
        pose_validity_input_path=args.pose_validity_input,
    )
    args.out_scorecard.parent.mkdir(parents=True, exist_ok=True)
    args.out_scorecard.write_text(_json_text(scorecard), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(scorecard["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-rmsd-scorecard-materialization: "
        f"{scorecard['status']} | cases={scorecard['case_count']} | "
        f"real_cases={scorecard['real_benchmark_case_count']} | "
        f"pose_success={scorecard['pose_success_count']}/{scorecard['case_count']} | "
        f"blockers={len(scorecard['blockers'])}"
    )
    return 1 if args.fail_blocked and not scorecard["scorecard_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
