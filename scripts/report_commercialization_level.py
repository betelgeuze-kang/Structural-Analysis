#!/usr/bin/env python3
"""Report the current commercialization level from release-facing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p1_benchmark_breadth_status import (  # noqa: E402
    DEFAULT_COMMERCIAL_READINESS,
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    build_status as build_p1_benchmark_breadth_status,
    _commercial_gate,
    _external_submission_queue_gate,
    _load_json,
    _load_submission_updates,
)


DEFAULT_P1_BENCHMARK_BREADTH_STATUS = Path("implementation/phase1/release/p1_benchmark_breadth_status.json")
DEFAULT_P1_OPERATIONAL_QUEUES = Path("implementation/phase1/release/p1_operational_queues/p1_operational_queues.json")
CONDITIONAL_CLOSURE_MODE = "conditional"
STRICT_CLOSURE_MODE = "strict"


def _conditional_external_closed(external_gate: dict[str, Any]) -> bool:
    queue_count = int(external_gate.get("submission_queue_count", 0) or 0)
    return bool(
        external_gate.get("ok")
        and queue_count
        and int(external_gate.get("submission_queue_ready_count", 0) or 0) >= queue_count
        and int(external_gate.get("external_benchmark_submission_updates_applied_count", 0) or 0) >= queue_count
        and int(external_gate.get("submission_last_checked_count", 0) or 0) >= queue_count
        and bool(external_gate.get("required_lifecycle_fields_present", False))
    )


def _conditional_residual_closed(
    *,
    commercial_gate: dict[str, Any],
    p1_operational_queues: dict[str, Any],
) -> bool:
    ops_summary = p1_operational_queues.get("summary") if isinstance(p1_operational_queues.get("summary"), dict) else {}
    residual_count = int(
        ops_summary.get(
            "residual_holdout_work_item_count",
            commercial_gate.get("residual_holdout_work_item_count", 0),
        )
        or 0
    )
    last_checked = int(
        ops_summary.get(
            "residual_holdout_last_checked_count",
            commercial_gate.get("residual_holdout_last_checked_count", 0),
        )
        or 0
    )
    work_items = commercial_gate.get("residual_holdout_work_items")
    rows = work_items if isinstance(work_items, list) else []
    rows_have_contract = bool(rows) and all(
        bool(str(row.get("owner", "") or "").strip())
        and int(row.get("sla_hours", 0) or 0) > 0
        and bool(str(row.get("closure_evidence_required", "") or "").strip())
        and bool(str(row.get("queue_status", "") or "").strip())
        for row in rows
        if isinstance(row, dict)
    )
    return bool(
        commercial_gate.get("commercial_scope_ready")
        and residual_count
        and last_checked >= residual_count
        and rows_have_contract
    )


def _score_from_gates(
    *,
    commercial_gate: dict[str, Any],
    external_gate: dict[str, Any],
    p1_benchmark_status: dict[str, Any],
    p1_operational_queues: dict[str, Any],
    closure_mode: str = STRICT_CLOSURE_MODE,
) -> tuple[float, list[str], list[str]]:
    blockers: list[str] = []
    accelerators: list[str] = []
    score = 0.0

    if commercial_gate.get("ok"):
        score += 3.0
        accelerators.append("commercial_readiness_contract_pass")
    else:
        blockers.append("commercial_readiness_not_green")

    if commercial_gate.get("commercial_grade_label") == "Commercial":
        score += 1.0
        accelerators.append("commercial_grade_label")
    else:
        blockers.append("commercial_grade_not_commercial")

    if commercial_gate.get("engineer_in_loop_accelerated_coverage_ready"):
        score += 1.0
        accelerators.append("engineer_in_loop_95_99_ready")
    else:
        blockers.append("engineer_in_loop_accelerated_coverage_not_ready")

    if external_gate.get("ok"):
        score += 1.0
        accelerators.append("external_submission_queue_operational")
    else:
        blockers.append("external_submission_queue_not_operational")

    queue_count = int(external_gate.get("submission_queue_count", 0) or 0)
    receipt_attached = int(external_gate.get("submission_receipt_attached_count", 0) or 0)
    updates_applied = int(external_gate.get("external_benchmark_submission_updates_applied_count", 0) or 0)
    last_checked = int(external_gate.get("submission_last_checked_count", 0) or 0)
    if queue_count and updates_applied >= queue_count and last_checked >= queue_count:
        accelerators.append("external_submission_update_sidecar_applied")
    elif updates_applied:
        accelerators.append("external_submission_update_sidecar_partially_applied")
    external_conditionally_closed = _conditional_external_closed(external_gate)
    if queue_count and receipt_attached >= queue_count:
        score += 1.0
        accelerators.append("external_submission_receipts_closed")
    elif closure_mode == CONDITIONAL_CLOSURE_MODE and external_conditionally_closed:
        score += 1.0
        accelerators.append("external_submission_conditional_productization_closed")
    else:
        blockers.append(f"external_submission_receipts_pending={max(queue_count - receipt_attached, 0)}")

    if p1_benchmark_status.get("p1_benchmark_execution_unblocked"):
        score += 1.0
        accelerators.append("p1_benchmark_execution_unblocked")
    elif p1_benchmark_status.get("benchmark_breadth_inputs_ready"):
        score += 0.5
        accelerators.append("p1_benchmark_breadth_inputs_ready")
        blockers.append("p1_benchmark_execution_blocked_by_p0_or_execution_gate")
    else:
        blockers.append("p1_benchmark_execution_blocked_or_not_materialized")

    ops_summary = p1_operational_queues.get("summary") if isinstance(p1_operational_queues.get("summary"), dict) else {}
    residual_count = int(
        ops_summary.get(
            "residual_holdout_work_item_count",
            commercial_gate.get("residual_holdout_work_item_count", 0),
        )
        or 0
    )
    residual_open = int(
        ops_summary.get(
            "residual_holdout_open_count",
            commercial_gate.get("residual_holdout_open_count", residual_count),
        )
        or 0
    )
    residual_pending = int(
        ops_summary.get(
            "residual_holdout_closure_evidence_pending_count",
            commercial_gate.get("residual_holdout_closure_evidence_pending_count", residual_open),
        )
        or 0
    )
    residual_conditionally_closed = _conditional_residual_closed(
        commercial_gate=commercial_gate,
        p1_operational_queues=p1_operational_queues,
    )
    if residual_count and residual_open == 0 and residual_pending == 0:
        score += 1.0
        accelerators.append("residual_holdout_closure_evidence_closed")
    elif closure_mode == CONDITIONAL_CLOSURE_MODE and residual_conditionally_closed:
        score += 1.0
        accelerators.append("residual_holdout_conditional_productization_closed")
    elif residual_count:
        score += 0.5
        accelerators.append("residual_holdout_operational_queue_present")
        blockers.append(f"residual_holdout_closure_pending={max(residual_pending, residual_open, 0)}")
    else:
        blockers.append(f"residual_holdout_closure_pending={max(residual_pending, residual_open, 0)}")

    if commercial_gate.get("full_commercial_replacement_ready"):
        score += 1.0
        accelerators.append("full_commercial_replacement_ready")
    else:
        blockers.append("full_commercial_replacement_ready=false")

    return min(score, 10.0), blockers, accelerators


def _level(score: float, *, full_replacement_ready: bool) -> tuple[str, str]:
    if score >= 9.0 and full_replacement_ready:
        return "L5", "full_commercial_replacement_candidate"
    if score >= 8.0:
        return "L4", "commercial_operations_ready_with_evidence_closure"
    if score >= 7.0:
        return "L3", "engineer_in_loop_commercial_assist_ready"
    if score >= 5.0:
        return "L2", "pilot_commercial_ready"
    return "L1", "pre_commercial"


def build_report(
    *,
    commercial_readiness: Path = DEFAULT_COMMERCIAL_READINESS,
    external_benchmark_submission_readiness: Path = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    external_benchmark_submission_updates: Path | None = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    residual_holdout_closure_updates: Path | None = DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    p1_benchmark_breadth_status: Path = DEFAULT_P1_BENCHMARK_BREADTH_STATUS,
    p1_operational_queues: Path = DEFAULT_P1_OPERATIONAL_QUEUES,
    closure_mode: str = STRICT_CLOSURE_MODE,
) -> dict[str, Any]:
    if closure_mode not in {STRICT_CLOSURE_MODE, CONDITIONAL_CLOSURE_MODE}:
        raise ValueError(f"unsupported closure mode: {closure_mode}")
    commercial_gate = _commercial_gate(
        commercial_readiness,
        residual_holdout_closure_updates=residual_holdout_closure_updates,
    )
    external_submission_updates = _load_submission_updates(external_benchmark_submission_updates)
    external_gate = _external_submission_queue_gate(
        external_benchmark_submission_readiness,
        submission_updates=external_submission_updates,
    )
    p1_benchmark_payload = (
        _load_json(p1_benchmark_breadth_status)
        if p1_benchmark_breadth_status.exists()
        else build_p1_benchmark_breadth_status(
            commercial_readiness=commercial_readiness,
            external_benchmark_submission_readiness=external_benchmark_submission_readiness,
            external_benchmark_submission_updates=external_benchmark_submission_updates,
            residual_holdout_closure_updates=residual_holdout_closure_updates,
        )
    )
    operational_payload = _load_json(p1_operational_queues) if p1_operational_queues.exists() else {}

    score, blockers, accelerators = _score_from_gates(
        commercial_gate=commercial_gate,
        external_gate=external_gate,
        p1_benchmark_status=p1_benchmark_payload,
        p1_operational_queues=operational_payload,
        closure_mode=closure_mode,
    )
    external_pending = int(external_gate.get("submission_receipt_pending_count", 0) or 0)
    ops_summary = operational_payload.get("summary") if isinstance(operational_payload.get("summary"), dict) else {}
    residual_pending = int(
        ops_summary.get(
            "residual_holdout_closure_evidence_pending_count",
            commercial_gate.get("residual_holdout_closure_evidence_pending_count", 0),
        )
        or 0
    )
    residual_open = int(
        ops_summary.get(
            "residual_holdout_open_count",
            commercial_gate.get("residual_holdout_open_count", 0),
        )
        or 0
    )
    strict_evidence_closed = bool(external_pending == 0 and residual_pending == 0 and residual_open == 0)
    external_conditionally_closed = _conditional_external_closed(external_gate)
    residual_conditionally_closed = _conditional_residual_closed(
        commercial_gate=commercial_gate,
        p1_operational_queues=operational_payload,
    )
    conditional_productization_closed = bool(
        external_conditionally_closed
        and residual_conditionally_closed
        and p1_benchmark_payload.get("p1_benchmark_execution_unblocked")
        and commercial_gate.get("ok")
    )
    level_id, level_label = _level(
        score,
        full_replacement_ready=bool(commercial_gate.get("full_commercial_replacement_ready", False)),
    )
    deployment_mode = str(commercial_gate.get("commercial_deployment_mode", "") or "")
    summary_line = (
        f"Commercialization level: {level_id} {level_label} | score={score:.1f}/10 | "
        f"grade={commercial_gate.get('commercial_grade_label', 'unknown')} | mode={deployment_mode or 'unknown'} | "
        f"full_commercial_replacement_ready={bool(commercial_gate.get('full_commercial_replacement_ready', False))}"
    )
    return {
        "schema_version": "commercialization-level-report.v1",
        "contract_pass": score >= 7.0 and bool(commercial_gate.get("ok", False)),
        "closure_mode": closure_mode,
        "strict_evidence_closed": strict_evidence_closed,
        "conditional_productization_closed": conditional_productization_closed,
        "strict_evidence_blockers": [
            *(["external_submission_receipts_pending"] if external_pending else []),
            *(["residual_holdout_closure_pending"] if residual_pending or residual_open else []),
        ],
        "commercialization_score": score,
        "commercialization_level": level_id,
        "commercialization_level_label": level_label,
        "summary_line": summary_line,
        "recommended_claim": (
            "engineer-in-loop commercial assist only; strict external/RH evidence remains pending."
            if closure_mode == CONDITIONAL_CLOSURE_MODE and conditional_productization_closed and not strict_evidence_closed
            else (
                "Commercial engineer-in-loop acceleration for 95-99% repeated workflows; "
                "not a full autonomous commercial replacement."
            )
        ),
        "commercial_scope": {
            "commercial_grade_label": commercial_gate.get("commercial_grade_label", ""),
            "commercial_deployment_mode": deployment_mode,
            "engineer_in_loop_accelerated_coverage_ready": bool(
                commercial_gate.get("engineer_in_loop_accelerated_coverage_ready", False)
            ),
            "full_commercial_replacement_ready": bool(commercial_gate.get("full_commercial_replacement_ready", False)),
            "accelerated_coverage_target_pct_range": commercial_gate.get(
                "accelerated_coverage_target_pct_range",
                [],
            ),
            "residual_holdout_target_pct_range": commercial_gate.get("residual_holdout_target_pct_range", []),
            "residual_holdout_work_item_count": int(commercial_gate.get("residual_holdout_work_item_count", 0) or 0),
        },
        "external_benchmark_submission": {
            "submission_queue_count": int(external_gate.get("submission_queue_count", 0) or 0),
            "submission_receipt_attached_count": int(external_gate.get("submission_receipt_attached_count", 0) or 0),
            "submission_receipt_pending_count": int(external_gate.get("submission_receipt_pending_count", 0) or 0),
            "submission_last_checked_count": int(external_gate.get("submission_last_checked_count", 0) or 0),
            "closure_evidence_attached_count": int(external_gate.get("closure_evidence_attached_count", 0) or 0),
            "external_benchmark_submission_updates_path": str(external_benchmark_submission_updates or ""),
            "external_benchmark_submission_updates_present": bool(
                external_benchmark_submission_updates and external_benchmark_submission_updates.exists()
            ),
            "external_benchmark_submission_updates_applied_count": int(
                external_gate.get("external_benchmark_submission_updates_applied_count", 0) or 0
            ),
        },
        "p1_benchmark_execution_unblocked": bool(
            p1_benchmark_payload.get("p1_benchmark_execution_unblocked", False)
        ),
        "p1_operational_queues_present": bool(p1_operational_queues.exists()),
        "blockers": blockers,
        "accelerators": accelerators,
        "artifacts": {
            "commercial_readiness": str(commercial_readiness),
            "external_benchmark_submission_readiness": str(external_benchmark_submission_readiness),
            "external_benchmark_submission_updates": str(external_benchmark_submission_updates or ""),
            "residual_holdout_closure_updates": str(residual_holdout_closure_updates or ""),
            "p1_benchmark_breadth_status": str(p1_benchmark_breadth_status),
            "p1_operational_queues": str(p1_operational_queues),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Commercialization Level",
            "",
            f"- `summary_line`: `{payload['summary_line']}`",
            f"- `recommended_claim`: `{payload['recommended_claim']}`",
            f"- `contract_pass`: `{bool(payload['contract_pass'])}`",
            f"- `closure_mode`: `{payload.get('closure_mode', 'strict')}`",
            f"- `strict_evidence_closed`: `{bool(payload.get('strict_evidence_closed', False))}`",
            f"- `conditional_productization_closed`: `{bool(payload.get('conditional_productization_closed', False))}`",
            "- `external_benchmark_submission_updates`: "
            f"`present={bool(payload['external_benchmark_submission']['external_benchmark_submission_updates_present'])}, "
            f"applied={int(payload['external_benchmark_submission']['external_benchmark_submission_updates_applied_count'])}, "
            f"last_checked={int(payload['external_benchmark_submission']['submission_last_checked_count'])}`",
            f"- `blockers`: `{', '.join(payload['blockers']) or 'none'}`",
            f"- `accelerators`: `{', '.join(payload['accelerators']) or 'none'}`",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument(
        "--external-benchmark-submission-readiness",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    )
    parser.add_argument(
        "--external-benchmark-submission-updates",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    )
    parser.add_argument(
        "--residual-holdout-closure-updates",
        type=Path,
        default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    )
    parser.add_argument("--p1-benchmark-breadth-status", type=Path, default=DEFAULT_P1_BENCHMARK_BREADTH_STATUS)
    parser.add_argument("--p1-operational-queues", type=Path, default=DEFAULT_P1_OPERATIONAL_QUEUES)
    parser.add_argument(
        "--closure-mode",
        choices=(STRICT_CLOSURE_MODE, CONDITIONAL_CLOSURE_MODE),
        default=STRICT_CLOSURE_MODE,
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-below", type=float, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        commercial_readiness=args.commercial_readiness,
        external_benchmark_submission_readiness=args.external_benchmark_submission_readiness,
        external_benchmark_submission_updates=args.external_benchmark_submission_updates,
        residual_holdout_closure_updates=args.residual_holdout_closure_updates,
        p1_benchmark_breadth_status=args.p1_benchmark_breadth_status,
        p1_operational_queues=args.p1_operational_queues,
        closure_mode=args.closure_mode,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(text if args.json else _markdown(payload))
    if args.fail_below is not None and float(payload["commercialization_score"]) < args.fail_below:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
