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
from build_pocketmd_lite_source_acquisition_plan import (  # noqa: E402
    _raw_row_candidate_status,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_ACQUISITION_PLAN = PRODUCTIZATION / "pocketmd_lite_source_acquisition_plan.json"
DEFAULT_SURVIVAL_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_ROWS_OUT = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_ROWS_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_topk_rows_template.csv"
DEFAULT_ROWS_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_template_preflight.json"
)
DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD = DEFAULT_ROWS_TEMPLATE_PREFLIGHT.with_suffix(".md")
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


def _required_flat_row_fields() -> list[str]:
    fields: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        if field == "uncertainty_interval":
            fields.extend(["uncertainty_low", "uncertainty_high", "uncertainty_unit"])
        else:
            fields.append(field)
    return fields


def _minimum_rows_from_source_plan(source_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source_plan.get("minimum_rows_by_case")
    if not isinstance(rows, list) or not rows:
        return _default_minimum_rows()
    return [row for row in rows if isinstance(row, dict)]


def _candidate_slots(minimum_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    required_flat_row_fields = _required_flat_row_fields()
    required_metric_fields = [
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
    ]
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
                    "required_row_fields": list(required_flat_row_fields),
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
                    "required_metric_fields": list(required_metric_fields),
                    "status": "operator_row_required",
                }
            )
    return slots


def _missing_slot_keys(raw_row_status: dict[str, Any]) -> set[tuple[str, int]]:
    missing_slots = raw_row_status.get("missing_required_slots")
    if not isinstance(missing_slots, list):
        return set()

    keys: set[tuple[str, int]] = set()
    for row in missing_slots:
        if not isinstance(row, dict):
            continue
        try:
            keys.add((str(row.get("case_id") or ""), int(row.get("top_k_rank"))))
        except (TypeError, ValueError):
            continue
    return keys


def _candidate_slot_statuses(
    candidate_slots: list[dict[str, Any]],
    raw_row_status: dict[str, Any],
    *,
    expected_rows_artifact: Path,
) -> list[dict[str, Any]]:
    missing_keys = _missing_slot_keys(raw_row_status)
    statuses: list[dict[str, Any]] = []
    for slot in candidate_slots:
        case_id = str(slot.get("case_id") or "")
        top_k_rank = int(slot.get("top_k_rank") or 0)
        missing = (case_id, top_k_rank) in missing_keys
        slot_id = f"{case_id}_rank_{top_k_rank:02d}"
        statuses.append(
            {
                "slot_id": slot_id,
                "case_id": case_id,
                "top_k_rank": top_k_rank,
                "candidate_id_placeholder": slot.get("candidate_id_placeholder"),
                "source_family": slot.get("source_family"),
                "status": "row_slot_missing" if missing else "row_slot_provided",
                "missing": missing,
                "provided": not missing,
                "expected_rows_artifact": str(expected_rows_artifact),
                "operator_action": (
                    f"attach_pocketmd_topk_row_for_{slot_id}"
                    if missing
                    else f"review_validated_pocketmd_topk_row_for_{slot_id}"
                ),
                "required_row_fields": list(slot.get("required_row_fields") or []),
                "required_metric_fields": list(
                    slot.get("required_metric_fields") or []
                ),
                "required_receipt_fields": list(
                    slot.get("required_receipt_fields") or []
                ),
            }
        )
    return statuses


def _slot_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": str(row.get("slot_id") or ""),
        "case_id": str(row.get("case_id") or ""),
        "top_k_rank": int(row.get("top_k_rank") or 0),
        "operator_action": str(row.get("operator_action") or ""),
    }


def _top_k_slot_status_summary(
    candidate_slot_statuses: list[dict[str, Any]],
    raw_row_status: dict[str, Any],
) -> dict[str, Any]:
    missing_slots = [
        _slot_ref(row)
        for row in candidate_slot_statuses
        if bool(row.get("missing"))
    ]
    provided_slots = [
        _slot_ref(row)
        for row in candidate_slot_statuses
        if bool(row.get("provided"))
    ]
    return {
        "raw_row_candidate_status": str(raw_row_status.get("status") or ""),
        "operator_rows_ready": bool(raw_row_status.get("coverage_ready")),
        "required_candidate_slot_count": len(candidate_slot_statuses),
        "provided_candidate_slot_count": len(provided_slots),
        "missing_candidate_slot_count": len(missing_slots),
        "covered_required_slot_count": int(
            raw_row_status.get("covered_required_slot_count") or 0
        ),
        "validated_row_count": int(raw_row_status.get("validated_row_count") or 0),
        "selected_path": str(raw_row_status.get("selected_path") or ""),
        "case_top_k_rank_prefixes": dict(
            raw_row_status.get("case_top_k_rank_prefixes") or {}
        ),
        "missing_candidate_slots": missing_slots,
        "provided_candidate_slots": provided_slots,
        "first_missing_candidate_slot": missing_slots[0] if missing_slots else {},
    }


def _operator_unblock_packet(
    *,
    top_k_slot_status_summary: dict[str, Any],
    rows_out: Path,
    operator_intake_out: Path,
    operator_commands: dict[str, str],
) -> dict[str, Any]:
    missing_candidate_slot_count = int(
        top_k_slot_status_summary.get("missing_candidate_slot_count") or 0
    )
    return {
        "status": (
            "operator_refinement_rows_required"
            if missing_candidate_slot_count
            else "operator_refinement_rows_ready"
        ),
        "row_template_artifact": str(DEFAULT_ROWS_TEMPLATE),
        "expected_rows_artifact": str(rows_out),
        "expected_operator_intake_artifact": str(operator_intake_out),
        "required_candidate_slot_count": int(
            top_k_slot_status_summary.get("required_candidate_slot_count") or 0
        ),
        "provided_candidate_slot_count": int(
            top_k_slot_status_summary.get("provided_candidate_slot_count") or 0
        ),
        "missing_candidate_slot_count": missing_candidate_slot_count,
        "first_missing_candidate_slot": dict(
            top_k_slot_status_summary.get("first_missing_candidate_slot") or {}
        ),
        "operator_sequence": [
            "preflight_pocketmd_lite_topk_rows_template",
            "fill_pocketmd_lite_topk_rows_from_template",
            "materialize_pocketmd_lite_topk_rows_from_template",
            "materialize_pocketmd_lite_operator_intake_from_rows",
            "materialize_pocketmd_lite_topk_survival_report",
            "refresh_pocketmd_lite_refinement_execution_plan",
            "rerun_science_actual_closure_row_audit",
        ],
        "row_template_preflight_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
        "row_template_preflight_markdown_artifact": str(
            DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD
        ),
        "commands": dict(operator_commands),
        "claim_boundary": (
            "This packet lists the bounded top-k refinement rows required by "
            "PocketMD Lite. It does not run refinement or synthesize local-min, "
            "contact, H-bond, clash, or uncertainty metrics."
        ),
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
    raw_row_status = _raw_row_candidate_status(
        repo_root,
        rows_out=rows_out,
        minimum_rows_by_case=minimum_rows,
    )
    candidate_slot_statuses = _candidate_slot_statuses(
        candidate_slots,
        raw_row_status,
        expected_rows_artifact=rows_out,
    )
    top_k_slot_status_summary = _top_k_slot_status_summary(
        candidate_slot_statuses,
        raw_row_status,
    )
    survival_blockers = [
        str(row)
        for row in survival_report.get("blockers", [])
        if str(row)
    ] if isinstance(survival_report.get("blockers"), list) else []
    operator_rows_ready = bool(raw_row_status["coverage_ready"])
    blockers = []
    row_blocker = str(raw_row_status.get("blocker") or "")
    if row_blocker:
        blockers.append(row_blocker)
    blockers.extend(survival_blockers)
    blockers = list(dict.fromkeys(blockers))
    operator_commands = {
        "build_row_template_preflight": (
            "python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py "
            f"--out {DEFAULT_ROWS_TEMPLATE_PREFLIGHT} "
            f"--out-md {DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD}"
        ),
        "materialize_rows_from_template": (
            "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py "
            f"--template {DEFAULT_ROWS_TEMPLATE} --out-rows {rows_out} "
            f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_rows_from_template_report.json'} "
            "--fail-blocked"
        ),
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
    }
    operator_unblock_packet = _operator_unblock_packet(
        top_k_slot_status_summary=top_k_slot_status_summary,
        rows_out=rows_out,
        operator_intake_out=operator_intake_out,
        operator_commands=operator_commands,
    )
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
        "operator_rows_ready": operator_rows_ready,
        "survival_report_ready": bool(survival_report.get("contract_pass")),
        "actual_closure_ready": False,
        "required_case_count": len(minimum_rows),
        "required_candidate_slot_count": len(candidate_slots),
        "candidate_slots": candidate_slots,
        "candidate_slot_statuses": candidate_slot_statuses,
        "top_k_slot_status_summary": top_k_slot_status_summary,
        "raw_row_candidate_status": raw_row_status,
        "expected_rows_artifact": str(rows_out),
        "expected_operator_intake_artifact": str(operator_intake_out),
        "operator_unblock_packet": operator_unblock_packet,
        "supported_row_formats": list(SUPPORTED_ROW_FORMATS),
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "required_flat_row_fields": _required_flat_row_fields(),
        "row_value_contract": row_value_contract(max_top_k=20),
        "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
        "operator_commands": operator_commands,
        "blockers": blockers,
        "summary": {
            "required_case_count": len(minimum_rows),
            "required_candidate_slot_count": len(candidate_slots),
            "operator_rows_ready": operator_rows_ready,
            "raw_row_candidate_status": raw_row_status["status"],
            "validated_row_count": raw_row_status["validated_row_count"],
            "covered_required_slot_count": raw_row_status[
                "covered_required_slot_count"
            ],
            "provided_candidate_slot_count": top_k_slot_status_summary[
                "provided_candidate_slot_count"
            ],
            "missing_candidate_slot_count": top_k_slot_status_summary[
                "missing_candidate_slot_count"
            ],
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
