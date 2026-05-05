#!/usr/bin/env python3
"""Summarize P1 benchmark breadth readiness without bypassing the P0 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p1_readiness_status import build_status as build_p1_readiness_status  # noqa: E402


DEFAULT_COMMERCIAL_READINESS = Path("implementation/phase1/commercial_readiness_report.json")
DEFAULT_BENCHMARK_REPORTS = (
    Path("implementation/phase1/hf_benchmark_report.json"),
    Path("implementation/phase1/hf_benchmark_report.rwth_zenodo.json"),
    Path("implementation/phase1/hf_benchmark_report.from_csv.json"),
    Path("implementation/phase1/hf_benchmark_report.atwood_open.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_pr.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_nightly.json"),
    Path("implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json"),
    Path("implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"),
)
REQUIRED_COMMERCIAL_CHECKS = (
    "real_source_pass",
    "benchmark_breadth_pass",
    "measured_dynamic_targets_pass",
    "measured_source_family_pass",
    "measured_case_count_pass",
    "accuracy_pass",
    "noise_robustness_pass",
    "ood_safety_pass",
    "gpu_strict_pass",
)

RESIDUAL_HOLDOUT_QUEUE_DEFAULTS = {
    "licensed_engineer_review_required": {
        "work_item_id": "RH-001",
        "queue_name": "licensed_engineer_review_queue",
        "queue_status": "pending_review",
        "status": "open",
        "sla_hours": 72,
        "sla_label": "72h",
        "due_date": "assignment_plus_3_business_days",
        "closure_evidence_required": "signed_engineer_review_packet",
    },
    "legacy_tool_cross_validation_required": {
        "work_item_id": "RH-002",
        "queue_name": "legacy_tool_cross_validation_queue",
        "queue_status": "pending_cross_validation",
        "status": "open",
        "sla_hours": 120,
        "sla_label": "120h",
        "due_date": "assignment_plus_5_business_days",
        "closure_evidence_required": "legacy_tool_cross_validation_report",
    },
    "legal_authority_signoff_required": {
        "work_item_id": "RH-003",
        "queue_name": "legal_authority_signoff_queue",
        "queue_status": "pending_signoff",
        "status": "open",
        "sla_hours": 168,
        "sla_label": "168h",
        "due_date": "authority_submission_window",
        "closure_evidence_required": "authority_signoff_receipt_or_formal_hold",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _status(ok: bool) -> str:
    return "ready" if ok else "blocked"


def _report_pass(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("contract_pass"), bool):
        return bool(payload["contract_pass"])
    if isinstance(payload.get("all_pass"), bool):
        return bool(payload["all_pass"])
    if isinstance(payload.get("pass"), bool):
        return bool(payload["pass"])
    return False


def _summary_line(payload: dict[str, Any], path: Path) -> str:
    direct = str(payload.get("summary_line", "") or "").strip()
    if direct:
        return direct
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    nested = str(summary.get("summary_line", "") or "").strip()
    return nested or path.name


def _commercial_gate(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    grade = payload.get("grade") if isinstance(payload.get("grade"), dict) else {}
    deployment_model = payload.get("deployment_model") if isinstance(payload.get("deployment_model"), dict) else {}
    residual_holdouts = (
        payload.get("residual_holdout_categories")
        if isinstance(payload.get("residual_holdout_categories"), list)
        else []
    )
    residual_work_items = _residual_holdout_work_items(payload, residual_holdouts)
    missing_checks = [name for name in REQUIRED_COMMERCIAL_CHECKS if not bool(checks.get(name, False))]
    commercial_grade_pass = bool(grade.get("commercial_pass", False))
    engineer_in_loop_ready = bool(deployment_model.get("engineer_in_loop_accelerated_coverage_ready", False))
    full_replacement_ready = bool(deployment_model.get("full_commercial_replacement_ready", False))
    commercial_scope_ready = bool(commercial_grade_pass and (engineer_in_loop_ready or full_replacement_ready))
    exists = path.exists()
    ok = bool(exists and _report_pass(payload) and not missing_checks and commercial_scope_ready)
    return {
        "label": "Commercial readiness breadth",
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
        "missing_required_checks": missing_checks,
        "commercial_grade_label": str(grade.get("label", "") or ""),
        "commercial_grade_pass": commercial_grade_pass,
        "commercial_deployment_mode": str(deployment_model.get("mode", "") or ""),
        "engineer_in_loop_accelerated_coverage_ready": engineer_in_loop_ready,
        "full_commercial_replacement_ready": full_replacement_ready,
        "accelerated_coverage_target_pct_range": deployment_model.get("accelerated_coverage_target_pct_range", []),
        "residual_holdout_target_pct_range": deployment_model.get("residual_holdout_target_pct_range", []),
        "residual_holdout_category_count": len(residual_holdouts),
        "residual_holdout_work_item_count": len(residual_work_items),
        "residual_holdout_work_items": residual_work_items,
        "commercial_scope_ready": commercial_scope_ready,
    }


def _residual_holdout_work_items(
    payload: dict[str, Any],
    residual_holdouts: list[Any],
) -> list[dict[str, Any]]:
    explicit_items = payload.get("residual_holdout_work_items")
    if isinstance(explicit_items, list) and explicit_items:
        enriched: list[dict[str, Any]] = []
        for row in explicit_items:
            if not isinstance(row, dict):
                continue
            category_id = str(row.get("category_id", row.get("id", "")) or "")
            defaults = RESIDUAL_HOLDOUT_QUEUE_DEFAULTS.get(category_id, {})
            closure_evidence_path = str(row.get("closure_evidence_path", "") or "")
            enriched.append(
                {
                    **row,
                    "category_id": category_id,
                    "sla_hours": int(row.get("sla_hours", defaults.get("sla_hours", 120)) or defaults.get("sla_hours", 120)),
                    "sla_label": str(row.get("sla_label", "") or defaults.get("sla_label", "120h")),
                    "due_date": str(
                        row.get("due_date", "") or defaults.get("due_date", "assignment_plus_5_business_days")
                    ),
                    "closure_evidence_required": str(
                        row.get("closure_evidence_required", "")
                        or defaults.get("closure_evidence_required", "owner_approved_closure_evidence")
                    ),
                    "closure_evidence_path": closure_evidence_path,
                    "closure_evidence_status": str(
                        row.get("closure_evidence_status", "") or ("attached" if closure_evidence_path else "pending")
                    ),
                }
            )
        return enriched

    work_items: list[dict[str, Any]] = []
    for row in residual_holdouts:
        if not isinstance(row, dict):
            continue
        category_id = str(row.get("id", "") or "")
        defaults = RESIDUAL_HOLDOUT_QUEUE_DEFAULTS.get(category_id, {})
        work_items.append(
            {
                "work_item_id": str(row.get("work_item_id", "") or defaults.get("work_item_id", f"RH-{len(work_items) + 1:03d}")),
                "category_id": category_id,
                "owner": str(row.get("owner", "") or ""),
                "queue_name": str(row.get("queue_name", "") or defaults.get("queue_name", "residual_holdout_queue")),
                "queue_status": str(row.get("queue_status", "") or defaults.get("queue_status", "pending_review")),
                "status": str(row.get("status", "") or defaults.get("status", "open")),
                "sla_hours": int(row.get("sla_hours", defaults.get("sla_hours", 120)) or defaults.get("sla_hours", 120)),
                "sla_label": str(row.get("sla_label", "") or defaults.get("sla_label", "120h")),
                "due_date": str(row.get("due_date", "") or defaults.get("due_date", "assignment_plus_5_business_days")),
                "closure_evidence_required": str(
                    row.get("closure_evidence_required", "")
                    or defaults.get("closure_evidence_required", "owner_approved_closure_evidence")
                ),
                "closure_evidence_path": str(row.get("closure_evidence_path", "") or ""),
                "closure_evidence_status": str(
                    row.get("closure_evidence_status", "")
                    or ("attached" if str(row.get("closure_evidence_path", "") or "") else "pending")
                ),
            }
        )
    return work_items


def _benchmark_gate(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    exists = path.exists()
    ok = bool(exists and _report_pass(payload))
    return {
        "label": path.stem.replace("_", " "),
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
    }


def _read_or_build_p1(path: Path | None) -> dict[str, Any]:
    if path is not None:
        return _load_json(path)
    return build_p1_readiness_status()


def _p1_gate(payload: dict[str, Any]) -> dict[str, Any]:
    p1_execution_unblocked = bool(payload.get("p1_execution_unblocked", False))
    return {
        "label": "P1 execution prerequisite",
        "status": _status(p1_execution_unblocked),
        "ok": p1_execution_unblocked,
        "p1_inputs_ready": bool(payload.get("p1_inputs_ready", False)),
        "p1_execution_unblocked": p1_execution_unblocked,
        "p0_release_blocker": bool(payload.get("p0_release_blocker", True)),
    }


def build_status(
    *,
    p1_readiness_status: Path | None = None,
    commercial_readiness: Path = DEFAULT_COMMERCIAL_READINESS,
    benchmark_reports: list[Path] | tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    p1_gate = _p1_gate(_read_or_build_p1(p1_readiness_status))
    reports = list(benchmark_reports if benchmark_reports is not None else DEFAULT_BENCHMARK_REPORTS)
    commercial_gate = _commercial_gate(commercial_readiness)
    evidence_gates = [commercial_gate, *[_benchmark_gate(path) for path in reports]]
    benchmark_breadth_inputs_ready = all(bool(gate["ok"]) for gate in evidence_gates)
    p1_benchmark_execution_unblocked = bool(benchmark_breadth_inputs_ready and p1_gate["p1_execution_unblocked"])
    if not benchmark_breadth_inputs_ready:
        next_action = "fix blocked P1 benchmark breadth evidence"
    elif bool(p1_gate["p0_release_blocker"]):
        next_action = "close P0-1 release publication before running P1 benchmark breadth"
    elif not bool(p1_gate["p1_inputs_ready"]):
        next_action = "fix blocked P1 readiness gates"
    else:
        next_action = "run P1 quality/fallback/benchmark breadth execution"
    pass_count = sum(1 for gate in evidence_gates if bool(gate["ok"]))
    return {
        "schema_version": "p1-benchmark-breadth-status.v1",
        "status": "ready" if p1_benchmark_execution_unblocked else "blocked",
        "benchmark_breadth_inputs_ready": benchmark_breadth_inputs_ready,
        "p1_benchmark_execution_unblocked": p1_benchmark_execution_unblocked,
        "p1_execution_unblocked": bool(p1_gate["p1_execution_unblocked"]),
        "p0_release_blocker": bool(p1_gate["p0_release_blocker"]),
        "summary": {
            "evidence_gate_count": len(evidence_gates),
            "evidence_gate_pass_count": pass_count,
            "benchmark_report_count": len(reports),
            "commercialization_scope": {
                "commercial_grade_label": commercial_gate["commercial_grade_label"],
                "commercial_deployment_mode": commercial_gate["commercial_deployment_mode"],
                "engineer_in_loop_accelerated_coverage_ready": commercial_gate[
                    "engineer_in_loop_accelerated_coverage_ready"
                ],
                "full_commercial_replacement_ready": commercial_gate["full_commercial_replacement_ready"],
                "accelerated_coverage_target_pct_range": commercial_gate[
                    "accelerated_coverage_target_pct_range"
                ],
                "residual_holdout_target_pct_range": commercial_gate["residual_holdout_target_pct_range"],
                "residual_holdout_category_count": commercial_gate["residual_holdout_category_count"],
                "residual_holdout_work_item_count": commercial_gate["residual_holdout_work_item_count"],
                "commercial_scope_ready": commercial_gate["commercial_scope_ready"],
            },
        },
        "gates": [p1_gate, *evidence_gates],
        "next_action": next_action,
    }


def _markdown(status: dict[str, Any]) -> str:
    lines = [
        "# P1 Benchmark Breadth Status",
        "",
        f"- Benchmark inputs ready: `{bool(status['benchmark_breadth_inputs_ready'])}`",
        f"- P1 benchmark execution unblocked: `{bool(status['p1_benchmark_execution_unblocked'])}`",
        f"- P0 release blocker: `{bool(status['p0_release_blocker'])}`",
        "- P1 work slice: `quality/fallback/benchmark breadth`",
        f"- Next action: `{status['next_action']}`",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for gate in status["gates"]:
        evidence = str(gate.get("summary_line", "") or gate.get("path", ""))
        lines.append(f"| {gate['label']} | `{gate['status']}` | {evidence} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize P1 benchmark breadth readiness.")
    parser.add_argument("--p1-readiness-status", type=Path)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument(
        "--benchmark-report",
        action="append",
        type=Path,
        dest="benchmark_reports",
        help="Benchmark evidence report. Repeat to override the default report set.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = build_status(
            p1_readiness_status=args.p1_readiness_status,
            commercial_readiness=args.commercial_readiness,
            benchmark_reports=args.benchmark_reports,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P1 benchmark breadth status check failed: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(status), encoding="utf-8")
    print(payload if args.json else _markdown(status))
    return 1 if args.fail_blocked and not bool(status["p1_benchmark_execution_unblocked"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
