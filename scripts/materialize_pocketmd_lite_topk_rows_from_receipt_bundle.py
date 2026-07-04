#!/usr/bin/env python3
"""Materialize PocketMD Lite top-k rows from completed receipt bundle files."""

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
    DEFAULT_MAX_TOP_K,
    _normalize_row,
    _validate_topk_integrity,
)
from materialize_pocketmd_lite_topk_survival_report import (  # noqa: E402
    SOURCE_CHECKSUM_PATTERN,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RECEIPT_BUNDLE = PRODUCTIZATION / "pocketmd_lite_refinement_receipt_bundle.json"
DEFAULT_OUT_ROWS = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_from_receipt_bundle_report.json"
)
SCHEMA_VERSION = "pocketmd-lite-topk-rows-from-receipt-bundle.v1"
ROWS_SCHEMA_VERSION = "pocketmd-lite-topk-rows.v1"
COMPLETED_RECEIPT_STATUSES = {
    "complete",
    "completed",
    "operator_complete",
    "pass",
    "ready",
    "refinement_receipt_complete",
}
OPERATOR_INPUT_SOURCE_FIELDS = (
    "source_id",
    "source_url",
    "source_license",
    "source_artifact",
    "source_artifact_sha256",
)
TOPK_ROW_FIELDS = (
    "case_id",
    "source_family",
    "top_k_rank",
    "candidate_id",
    "upstream_top_k_provenance_ref",
    "upstream_top_k_source_checksum",
    "pre_refinement_energy_proxy",
    "post_refinement_energy_proxy",
    "local_min_survived",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_count_before",
    "clash_count_after",
    "uncertainty_low",
    "uncertainty_high",
    "uncertainty_unit",
    "provenance_ref",
    "source_checksum",
)
DEFAULT_OPERATOR_REQUIRED_FIELDS = (
    *TOPK_ROW_FIELDS,
    *(
        f"operator_input_source.{field}"
        for field in OPERATOR_INPUT_SOURCE_FIELDS
    ),
)
RECEIPT_METRIC_FAMILIES = (
    {
        "metric_family_id": "local_min_survival",
        "product_requirement": "local-min survival and energy proxy movement are recorded",
        "phase4_criterion_id": "local_min_survival_materialized",
        "required_receipt_fields": [
            "pre_refinement_energy_proxy",
            "post_refinement_energy_proxy",
            "local_min_survived",
        ],
    },
    {
        "metric_family_id": "contact_persistence",
        "product_requirement": "contact persistence is recorded",
        "phase4_criterion_id": "contact_persistence_materialized",
        "required_receipt_fields": ["contact_persistence_rate"],
    },
    {
        "metric_family_id": "h_bond_persistence",
        "product_requirement": "H-bond persistence is recorded",
        "phase4_criterion_id": "h_bond_persistence_materialized",
        "required_receipt_fields": ["h_bond_persistence_rate"],
    },
    {
        "metric_family_id": "clash_relief",
        "product_requirement": "clash relief before/after counts are recorded",
        "phase4_criterion_id": "clash_relief_materialized",
        "required_receipt_fields": ["clash_count_before", "clash_count_after"],
    },
    {
        "metric_family_id": "uncertainty",
        "product_requirement": "uncertainty interval bounds are recorded",
        "phase4_criterion_id": "uncertainty_summary_materialized",
        "required_receipt_fields": ["uncertainty_low", "uncertainty_high"],
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _operator_command_map(
    *,
    receipt_bundle: Path = DEFAULT_RECEIPT_BUNDLE,
    out_rows: Path = DEFAULT_OUT_ROWS,
    out_report: Path = DEFAULT_OUT_REPORT,
) -> dict[str, str]:
    return {
        "rerun_receipt_bundle": (
            "python3 scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py "
            "--fail-blocked"
        ),
        "rerun_rows_materialization": (
            "python3 scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py "
            f"--receipt-bundle {receipt_bundle} --out-rows {out_rows} "
            f"--out-report {out_report} --fail-blocked"
        ),
        "materialize_operator_intake": (
            "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
            f"--rows {out_rows} "
            f"--out {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license>"
        ),
        "materialize_survival_report": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            f"--intake {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
            f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
            f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_survival_report.json'} "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json --fail-blocked"
        ),
        "rerun_phase4_row_audit": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            f"--pocketmd-rows {out_rows} "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> --fail-blocked"
        ),
    }


def _nested_text(payload: dict[str, Any], field: str) -> str:
    current: Any = payload
    for part in field.split("."):
        if not isinstance(current, dict):
            return ""
        current = current.get(part)
    return _text(current)


def _receipt_completion_status(
    *,
    receipt: dict[str, Any],
    bundle_row: dict[str, Any],
) -> dict[str, Any]:
    required_fields = [
        _text(field)
        for field in _as_list(receipt.get("operator_required_fields"))
        if _text(field)
    ] or list(DEFAULT_OPERATOR_REQUIRED_FIELDS)
    row_payload = _receipt_row_payload(receipt) if receipt else {}
    completion_payload = {
        **_as_dict(row_payload),
        **{
            key: value
            for key, value in receipt.items()
            if key != "top_k_refinement_row"
        },
    }
    completion_payload.setdefault("case_id", bundle_row.get("case_id"))
    completion_payload.setdefault("source_family", bundle_row.get("source_family"))
    completion_payload.setdefault("top_k_rank", bundle_row.get("top_k_rank"))
    completion_payload.setdefault(
        "candidate_id",
        bundle_row.get("candidate_id_placeholder"),
    )
    missing_fields = [
        field
        for field in required_fields
        if not _nested_text(completion_payload, field)
    ]
    return {
        "completion_required_statuses": sorted(COMPLETED_RECEIPT_STATUSES),
        "completion_required_fields": required_fields,
        "completion_required_field_count": len(required_fields),
        "completion_filled_required_field_count": (
            len(required_fields) - len(missing_fields)
        ),
        "completion_missing_required_fields": missing_fields,
        "completion_missing_required_field_count": len(missing_fields),
        "operator_completion_action": (
            "fill_completion_missing_required_fields_and_set_status_complete"
            if missing_fields
            else "set_status_complete_after_operator_review"
        ),
    }


def _load_required_receipt(
    repo_root: Path,
    path_value: Any,
) -> tuple[dict[str, Any], str]:
    path_text = _text(path_value)
    if not path_text:
        return {}, "receipt_ref_missing"
    resolved = _resolve(repo_root, Path(path_text))
    if not resolved.is_file():
        return {}, "receipt_file_missing"
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"receipt_json_invalid:{exc.__class__.__name__}"
    return payload if isinstance(payload, dict) else {}, ""


def _receipt_row_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    nested_row = _as_dict(receipt.get("top_k_refinement_row"))
    return nested_row if nested_row else receipt


def _operator_input_source_status(
    receipt: dict[str, Any],
) -> tuple[dict[str, str], list[str]]:
    source = _as_dict(receipt.get("operator_input_source"))
    normalized = {field: _text(source.get(field)) for field in OPERATOR_INPUT_SOURCE_FIELDS}
    blockers = [
        f"operator_input_source.{field}_missing"
        for field, value in normalized.items()
        if not value
    ]
    artifact_checksum = normalized["source_artifact_sha256"]
    if artifact_checksum and not SOURCE_CHECKSUM_PATTERN.fullmatch(artifact_checksum):
        blockers.append("operator_input_source.source_artifact_sha256_invalid")
    return normalized, blockers


def _raw_row_from_receipt(
    *,
    receipt: dict[str, Any],
    bundle_row: dict[str, Any],
) -> dict[str, Any]:
    row_payload = _receipt_row_payload(receipt)
    raw_row = {field: row_payload.get(field, receipt.get(field)) for field in TOPK_ROW_FIELDS}
    raw_row["case_id"] = raw_row.get("case_id") or bundle_row.get("case_id")
    raw_row["source_family"] = raw_row.get("source_family") or bundle_row.get(
        "source_family"
    )
    raw_row["top_k_rank"] = raw_row.get("top_k_rank") or bundle_row.get("top_k_rank")
    raw_row["candidate_id"] = raw_row.get("candidate_id") or bundle_row.get(
        "candidate_id_placeholder"
    )
    return raw_row


def _row_from_bundle_receipt(
    *,
    repo_root: Path,
    bundle_row: dict[str, Any],
    max_top_k: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = _text(bundle_row.get("case_id"))
    rank_text = _text(bundle_row.get("top_k_rank"))
    run_key = f"{case_id}::rank_{rank_text}"
    blockers: list[str] = []
    receipt, receipt_blocker = _load_required_receipt(
        repo_root,
        bundle_row.get("receipt_ref"),
    )
    if receipt_blocker:
        blockers.append(receipt_blocker)
    receipt_status = _text(receipt.get("status")).lower()
    receipt_complete = bool(receipt) and receipt_status in COMPLETED_RECEIPT_STATUSES
    if receipt and not receipt_complete:
        blockers.append("receipt_not_complete")
    completion_status = _receipt_completion_status(
        receipt=receipt or _as_dict(bundle_row.get("receipt_template_payload")),
        bundle_row=bundle_row,
    )
    operator_input_source = {field: "" for field in OPERATOR_INPUT_SOURCE_FIELDS}
    if receipt_complete:
        operator_input_source, source_blockers = _operator_input_source_status(receipt)
        blockers.extend(source_blockers)
    normalized_row: dict[str, Any] = {}
    if receipt_complete:
        raw_row = _raw_row_from_receipt(receipt=receipt, bundle_row=bundle_row)
        try:
            normalized_row = _normalize_row(
                raw_row,
                row_index=1,
                max_top_k=max_top_k,
            )
        except Exception as exc:
            blockers.append(f"row_normalization_failed:{exc}")
        else:
            if case_id and normalized_row["case_id"] != case_id:
                blockers.append("case_id_mismatch")
            try:
                expected_rank = int(bundle_row.get("top_k_rank"))
            except (TypeError, ValueError):
                expected_rank = 0
            if expected_rank and normalized_row["top_k_rank"] != expected_rank:
                blockers.append("top_k_rank_mismatch")
    row_status = {
        "run_key": run_key,
        "case_id": case_id,
        "top_k_rank": bundle_row.get("top_k_rank"),
        "receipt_ref": _text(bundle_row.get("receipt_ref")),
        "receipt_status": receipt_status,
        "receipt_complete": receipt_complete,
        "status": "ready" if not blockers else "operator_completion_required",
        "operator_input_source": operator_input_source,
        **completion_status,
        "blockers": list(dict.fromkeys(blockers)),
    }
    return normalized_row, row_status


def _receipt_completion_action_plan(
    row_statuses: list[dict[str, Any]],
    *,
    commands: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    command_map = commands or {}
    command_key = "rerun_rows_materialization"
    for status in row_statuses:
        if status.get("status") == "ready":
            continue
        operator_action = str(status.get("operator_completion_action") or "")
        missing_fields = [
            str(field)
            for field in _as_list(status.get("completion_missing_required_fields"))
            if str(field)
        ]
        rows.append(
            {
                "run_key": str(status.get("run_key") or ""),
                "case_id": str(status.get("case_id") or ""),
                "top_k_rank": status.get("top_k_rank"),
                "receipt_ref": str(status.get("receipt_ref") or ""),
                "status": str(status.get("status") or ""),
                "receipt_status": str(status.get("receipt_status") or ""),
                "receipt_complete": bool(status.get("receipt_complete")),
                "operator_completion_action": operator_action,
                "next_action": operator_action,
                "command_key": command_key,
                "materialization_command": str(command_map.get(command_key) or ""),
                "completion_required_field_count": int(
                    status.get("completion_required_field_count") or 0
                ),
                "completion_filled_required_field_count": int(
                    status.get("completion_filled_required_field_count") or 0
                ),
                "completion_missing_required_field_count": len(missing_fields),
                "completion_missing_required_fields": missing_fields,
                "blockers": [
                    str(blocker)
                    for blocker in _as_list(status.get("blockers"))
                    if str(blocker)
                ],
            }
        )
    return rows


def _receipt_metric_family_completion_plan(
    receipt_completion_action_plan: list[dict[str, Any]],
    *,
    receipt_count: int,
    commands: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    command_map = commands or {}
    command_key = "rerun_rows_materialization"
    for family in RECEIPT_METRIC_FAMILIES:
        required_fields = [
            str(field)
            for field in _as_list(family.get("required_receipt_fields"))
            if str(field)
        ]
        blocked_receipts: list[dict[str, Any]] = []
        missing_field_occurrence_count = 0
        for receipt in receipt_completion_action_plan:
            missing_field_set = {
                str(field)
                for field in _as_list(
                    receipt.get("completion_missing_required_fields")
                )
            }
            missing_fields = [
                field for field in required_fields if field in missing_field_set
            ]
            if not missing_fields:
                continue
            missing_field_occurrence_count += len(missing_fields)
            blocked_receipts.append(
                {
                    "run_key": str(receipt.get("run_key") or ""),
                    "case_id": str(receipt.get("case_id") or ""),
                    "top_k_rank": int(receipt.get("top_k_rank") or 0),
                    "receipt_ref": str(receipt.get("receipt_ref") or ""),
                    "missing_receipt_fields": missing_fields,
                    "operator_completion_action": str(
                        receipt.get("operator_completion_action") or ""
                    ),
                }
            )
        blocked_count = len(blocked_receipts)
        operator_action = (
            "fill_metric_family_receipt_fields_for_"
            f"{family.get('metric_family_id')}"
            if blocked_count
            else "review_metric_family_receipts"
        )
        plan.append(
            {
                "metric_family_id": str(family.get("metric_family_id") or ""),
                "product_requirement": str(
                    family.get("product_requirement") or ""
                ),
                "phase4_criterion_id": str(
                    family.get("phase4_criterion_id") or ""
                ),
                "status": "blocked" if blocked_count else "ready",
                "required_receipt_fields": required_fields,
                "receipt_count": receipt_count,
                "complete_receipt_count": max(0, receipt_count - blocked_count),
                "blocked_receipt_count": blocked_count,
                "missing_field_occurrence_count": missing_field_occurrence_count,
                "first_blocked_receipt": (
                    blocked_receipts[0] if blocked_receipts else {}
                ),
                "blocked_receipts": blocked_receipts,
                "operator_completion_action": operator_action,
                "next_action": operator_action,
                "command_key": command_key,
                "materialization_command": str(command_map.get(command_key) or ""),
            }
        )
    return plan


def materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
    *,
    repo_root: Path = ROOT,
    receipt_bundle: Path = DEFAULT_RECEIPT_BUNDLE,
    out_rows: Path = DEFAULT_OUT_ROWS,
    out_report: Path = DEFAULT_OUT_REPORT,
    max_top_k: int = DEFAULT_MAX_TOP_K,
) -> dict[str, Any]:
    if max_top_k < 1:
        raise ValueError("max_top_k_must_be_positive")
    bundle = _load_json(repo_root, receipt_bundle)
    bundle_ready = bool(bundle.get("bundle_materialized"))
    raw_bundle_rows = [
        row for row in _as_list(bundle.get("bundle_rows")) if isinstance(row, dict)
    ]
    row_results = (
        [
            _row_from_bundle_receipt(
                repo_root=repo_root,
                bundle_row=row,
                max_top_k=max_top_k,
            )
            for row in raw_bundle_rows
        ]
        if bundle_ready
        else []
    )
    ready_rows = [
        row
        for row, status in row_results
        if row and status.get("status") == "ready"
    ]
    row_statuses = [status for _row, status in row_results]
    commands = _operator_command_map(
        receipt_bundle=receipt_bundle,
        out_rows=out_rows,
        out_report=out_report,
    )
    receipt_completion_action_plan = _receipt_completion_action_plan(
        row_statuses,
        commands=commands,
    )
    receipt_metric_family_completion_plan = (
        _receipt_metric_family_completion_plan(
            receipt_completion_action_plan,
            receipt_count=len(raw_bundle_rows),
            commands=commands,
        )
    )
    first_incomplete_receipt = (
        receipt_completion_action_plan[0] if receipt_completion_action_plan else {}
    )
    unique_missing_required_fields = sorted(
        {
            field
            for row in receipt_completion_action_plan
            for field in _as_list(row.get("completion_missing_required_fields"))
            if str(field)
        }
    )
    total_missing_required_field_count = sum(
        int(row.get("completion_missing_required_field_count") or 0)
        for row in receipt_completion_action_plan
    )
    row_blockers = [
        f"{status['run_key']}::{blocker}"
        for status in row_statuses
        for blocker in _as_list(status.get("blockers"))
    ]
    aggregate_error = ""
    if bundle_ready and not row_blockers and ready_rows:
        try:
            _validate_topk_integrity(ready_rows)
        except Exception as exc:
            aggregate_error = str(exc)
            row_blockers.append(f"topk_integrity_failed:{aggregate_error}")
    rows_written = False
    if bundle_ready and ready_rows and not row_blockers:
        rows_payload = {
            "schema_version": ROWS_SCHEMA_VERSION,
            **release_evidence_metadata(
                input_paths=[
                    Path(
                        "scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py"
                    ),
                    Path(
                        "scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py"
                    ),
                    Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                    receipt_bundle,
                ],
                reused_evidence=False,
                reuse_policy=(
                    "pocketmd_lite_topk_rows_materialized_from_completed_"
                    "refinement_receipt_bundle"
                ),
                repo_root=repo_root,
            ),
            "top_k_refinement_rows": ready_rows,
            "receipt_bundle_artifact": str(receipt_bundle),
            "row_count": len(ready_rows),
            "case_count": len({str(row["case_id"]) for row in ready_rows}),
            "operator_input_sources": [
                status["operator_input_source"] for status in row_statuses
            ],
            "claim_boundary": (
                "These rows are materialized from completed PocketMD Lite "
                "refinement receipts after row normalization and top-k integrity "
                "validation. They still require operator intake source arguments "
                "and downstream survival validation before Phase 4 closure."
            ),
        }
        _write_json(repo_root, out_rows, rows_payload)
        rows_written = True
    blockers: list[str] = []
    if not bundle_ready:
        blockers.append("pocketmd_lite_refinement_receipt_bundle_not_ready")
    if bundle_ready and not raw_bundle_rows:
        blockers.append("pocketmd_lite_refinement_receipt_bundle_rows_missing")
    if bundle_ready and raw_bundle_rows and not ready_rows:
        blockers.append("pocketmd_lite_refinement_receipts_not_completed")
    blockers.extend(row_blockers)
    blockers = list(dict.fromkeys(blockers))
    if rows_written:
        status = "rows_materialized"
    elif bundle_ready:
        status = "operator_receipts_completion_required"
    else:
        status = "receipt_bundle_not_ready"
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path(
                    "scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py"
                ),
                Path("scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py"),
                receipt_bundle,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_topk_rows_from_receipt_bundle_report",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": rows_written,
        "rows_materialized": rows_written,
        "bundle_ready": bundle_ready,
        "receipt_bundle_artifact": str(receipt_bundle),
        "out_rows_artifact": str(out_rows),
        "out_report_artifact": str(out_report),
        "receipt_count": len(raw_bundle_rows),
        "ready_receipt_count": sum(
            1 for row in row_statuses if row.get("status") == "ready"
        ),
        "incomplete_receipt_count": len(receipt_completion_action_plan),
        "first_incomplete_receipt": first_incomplete_receipt,
        "receipt_completion_action_plan": receipt_completion_action_plan,
        "receipt_metric_family_completion_plan": (
            receipt_metric_family_completion_plan
        ),
        "receipt_metric_family_count": len(
            receipt_metric_family_completion_plan
        ),
        "receipt_metric_family_blocked_count": sum(
            1
            for row in receipt_metric_family_completion_plan
            if row["status"] == "blocked"
        ),
        "receipt_metric_family_missing_field_occurrence_count": sum(
            int(row.get("missing_field_occurrence_count") or 0)
            for row in receipt_metric_family_completion_plan
        ),
        "unique_missing_required_fields": unique_missing_required_fields,
        "unique_missing_required_field_count": len(unique_missing_required_fields),
        "total_missing_required_field_count": total_missing_required_field_count,
        "row_count": len(ready_rows),
        "case_count": len({str(row["case_id"]) for row in ready_rows}),
        "aggregate_validation_error": aggregate_error,
        "row_statuses": row_statuses,
        "blockers": blockers,
        "commands": commands,
        "summary": {
            "bundle_ready": bundle_ready,
            "rows_materialized": rows_written,
            "receipt_count": len(raw_bundle_rows),
            "ready_receipt_count": sum(
                1 for row in row_statuses if row.get("status") == "ready"
            ),
            "incomplete_receipt_count": len(receipt_completion_action_plan),
            "receipt_metric_family_count": len(
                receipt_metric_family_completion_plan
            ),
            "receipt_metric_family_blocked_count": sum(
                1
                for row in receipt_metric_family_completion_plan
                if row["status"] == "blocked"
            ),
            "receipt_metric_family_missing_field_occurrence_count": sum(
                int(row.get("missing_field_occurrence_count") or 0)
                for row in receipt_metric_family_completion_plan
            ),
            "unique_missing_required_field_count": len(unique_missing_required_fields),
            "total_missing_required_field_count": (
                total_missing_required_field_count
            ),
            "row_count": len(ready_rows),
            "case_count": len({str(row["case_id"]) for row in ready_rows}),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This helper only promotes completed PocketMD Lite receipt-bundle "
            "files into top-k rows after normalization and integrity validation. "
            "It does not run refinement, invent metrics, bypass operator source "
            "receipts, or close Phase 4 by itself."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--receipt-bundle", type=Path, default=DEFAULT_RECEIPT_BUNDLE)
    parser.add_argument("--out-rows", type=Path, default=DEFAULT_OUT_ROWS)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--max-top-k", type=int, default=DEFAULT_MAX_TOP_K)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
        repo_root=args.repo_root,
        receipt_bundle=args.receipt_bundle,
        out_rows=args.out_rows,
        out_report=args.out_report,
        max_top_k=args.max_top_k,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-topk-rows-from-receipt-bundle: "
            f"{payload['status']} | receipts={payload['receipt_count']} | "
            f"written={payload['rows_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
