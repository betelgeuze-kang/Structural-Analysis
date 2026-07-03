#!/usr/bin/env python3
"""Build a PocketMD Lite bounded top-k refinement execution plan."""

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

from materialize_pocketmd_lite_operator_intake_from_rows import (  # noqa: E402
    SUPPORTED_ROW_FORMATS,
    SOURCE_RECEIPT_REQUIREMENTS,
    row_value_contract,
)
from materialize_pocketmd_lite_topk_survival_report import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    TOPK_ROW_QUALITY_CRITERIA,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_ACQUISITION_PLAN = PRODUCTIZATION / "pocketmd_lite_source_acquisition_plan.json"
DEFAULT_SURVIVAL_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_ROWS_OUT = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_OPERATOR_INTAKE = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
DEFAULT_OUT = PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
SCHEMA_VERSION = "pocketmd-lite-refinement-execution-plan.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_minimum_rows() -> list[dict[str, Any]]:
    min_case_count = int(TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"])
    min_candidates = int(TOPK_ROW_QUALITY_CRITERIA["min_candidate_count_per_case"])
    min_rank_coverage = int(TOPK_ROW_QUALITY_CRITERIA["min_top_k_rank_coverage_per_case"])
    return [
        {
            "case_id": f"pocketmd_lite_case_{case_index:03d}",
            "minimum_candidate_rows": min_candidates,
            "required_top_k_rank_prefix": list(range(1, min_rank_coverage + 1)),
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
        }
        for case_index in range(1, min_case_count + 1)
    ]


def _minimum_rows_from_source_plan(source_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source_plan.get("minimum_rows_by_case")
    if not isinstance(rows, list) or not rows:
        return _default_minimum_rows()
    return [row for row in rows if isinstance(row, dict)]


def _candidate_slots(minimum_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for case_row in minimum_rows:
        case_id = str(case_row.get("case_id") or "")
        ranks = case_row.get("required_top_k_rank_prefix")
        if not isinstance(ranks, list) or not ranks:
            ranks = [1, 2]
        for rank in ranks:
            slots.append(
                {
                    "case_id": case_id,
                    "top_k_rank": int(rank),
                    "candidate_id_placeholder": f"{case_id}_rank_{int(rank):02d}",
                    "source_family": "upstream_ranked_top_k_candidate_set",
                    "required_row_fields": list(REQUIRED_CASE_FIELDS),
                    "required_receipt_fields": [
                        "upstream_top_k_provenance_ref",
                        "upstream_top_k_source_checksum",
                        "provenance_ref",
                        "source_checksum",
                        "operator_input_source.source_artifact",
                        "operator_input_source.source_artifact_sha256",
                        "operator_input_source.source_id",
                        "operator_input_source.source_url",
                        "operator_input_source.source_license",
                    ],
                    "required_metric_fields": [
                        "local_min_survived",
                        "contact_persistence_rate",
                        "h_bond_persistence_rate",
                        "clash_count_before",
                        "clash_count_after",
                        "uncertainty_interval",
                    ],
                    "status": "operator_row_required",
                }
            )
    return slots


def _raw_row_candidate_status(repo_root: Path, rows_out: Path) -> dict[str, Any]:
    candidates = [
        PRODUCTIZATION / f"pocketmd_lite_topk_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv", "tsv")
    ]
    if rows_out not in candidates:
        candidates.insert(0, rows_out)
    rows = []
    for path in candidates:
        resolved = path if path.is_absolute() else repo_root / path
        rows.append(
            {
                "path": str(path),
                "exists": resolved.exists(),
                "is_file": resolved.is_file(),
            }
        )
    return {
        "default_rows_out": str(rows_out),
        "candidate_paths": rows,
        "detected_row_artifact_count": sum(1 for row in rows if row["is_file"]),
    }


def build_pocketmd_lite_refinement_execution_plan(
    *,
    repo_root: Path = ROOT,
    source_acquisition_plan_path: Path = DEFAULT_SOURCE_ACQUISITION_PLAN,
    survival_report_path: Path = DEFAULT_SURVIVAL_REPORT,
    rows_out: Path = DEFAULT_ROWS_OUT,
    operator_intake_out: Path = DEFAULT_OPERATOR_INTAKE,
) -> dict[str, Any]:
    source_plan = _load_json(repo_root, source_acquisition_plan_path)
    survival_report = _load_json(repo_root, survival_report_path)
    minimum_rows = _minimum_rows_from_source_plan(source_plan)
    candidate_slots = _candidate_slots(minimum_rows)
    raw_row_status = _raw_row_candidate_status(repo_root, rows_out)
    survival_blockers = [
        str(row)
        for row in survival_report.get("blockers", [])
        if str(row)
    ] if isinstance(survival_report.get("blockers"), list) else []
    row_artifact_present = raw_row_status["detected_row_artifact_count"] > 0
    blockers = []
    if not row_artifact_present:
        blockers.append("pocketmd_lite_topk_rows_not_detected")
    blockers.extend(survival_blockers)
    blockers = list(dict.fromkeys(blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_pocketmd_lite_refinement_execution_plan.py"),
                source_acquisition_plan_path,
                survival_report_path,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_refinement_execution_plan_from_current_contracts",
            repo_root=repo_root,
        ),
        "status": "operator_refinement_rows_required",
        "contract_pass": True,
        "execution_plan_ready": True,
        "operator_rows_ready": row_artifact_present,
        "survival_report_ready": bool(survival_report.get("contract_pass")),
        "actual_closure_ready": False,
        "required_case_count": len(minimum_rows),
        "required_candidate_slot_count": len(candidate_slots),
        "candidate_slots": candidate_slots,
        "raw_row_candidate_status": raw_row_status,
        "expected_rows_artifact": str(rows_out),
        "expected_operator_intake_artifact": str(operator_intake_out),
        "supported_row_formats": list(SUPPORTED_ROW_FORMATS),
        "row_value_contract": row_value_contract(max_top_k=20),
        "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
        "operator_commands": {
            "import_rows": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                f"--rows {rows_out} --out {operator_intake_out} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_survival_report": (
                "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
                f"--intake {operator_intake_out} "
                f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
                f"--out-report {DEFAULT_SURVIVAL_REPORT} "
                "--out-surface implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json --fail-blocked"
            ),
        },
        "blockers": blockers,
        "summary": {
            "required_case_count": len(minimum_rows),
            "required_candidate_slot_count": len(candidate_slots),
            "operator_rows_ready": row_artifact_present,
            "survival_report_ready": bool(survival_report.get("contract_pass")),
            "survival_report_blocker_count": len(survival_blockers),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This execution plan enumerates the bounded PocketMD Lite top-k refinement "
            "row slots required by the current contract. It does not run refinement, "
            "does not synthesize metric rows, and does not unlock all-atom MD/FEP "
            "claims before real operator rows pass the survival materializer."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-acquisition-plan", type=Path, default=DEFAULT_SOURCE_ACQUISITION_PLAN)
    parser.add_argument("--survival-report", type=Path, default=DEFAULT_SURVIVAL_REPORT)
    parser.add_argument("--rows-out", type=Path, default=DEFAULT_ROWS_OUT)
    parser.add_argument("--operator-intake-out", type=Path, default=DEFAULT_OPERATOR_INTAKE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_pocketmd_lite_refinement_execution_plan(
        repo_root=args.repo_root,
        source_acquisition_plan_path=args.source_acquisition_plan,
        survival_report_path=args.survival_report,
        rows_out=args.rows_out,
        operator_intake_out=args.operator_intake_out,
    )
    resolved_out = args.out if args.out.is_absolute() else args.repo_root / args.out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-refinement-execution-plan: "
            f"{payload['status']} | cases={payload['required_case_count']} | "
            f"candidate_slots={payload['required_candidate_slot_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
