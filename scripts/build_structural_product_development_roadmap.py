#!/usr/bin/env python3
"""Build a structural-solver product progress and roadmap surface."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import engine_version, git_head, input_checksums  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT_JSON = PRODUCTIZATION / "structural_product_development_roadmap.json"
DEFAULT_OUT_MD = PRODUCTIZATION / "structural_product_development_roadmap.md"

PRODUCT_READINESS = PRODUCTIZATION / "product_readiness_snapshot.json"
PM_RELEASE_GATE = PRODUCTIZATION / "pm_release_gate_report.json"
DEVELOPER_PREVIEW_RC = PRODUCTIZATION / "developer_preview_rc_status.json"
RELEASE_FRESHNESS = PRODUCTIZATION / "release_evidence_freshness_report.json"
G1_DIRECT_RESIDUAL = PRODUCTIZATION / "mgt_g1_direct_residual_terminal_gate_report.json"
G1_FULL_LOAD_HIP = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
CUSTOMER_SHADOW = Path("implementation/phase1/customer_shadow_evidence_status.json")
EXTERNAL_BENCHMARK_SUBMISSION = Path(
    "implementation/phase1/release/external_benchmark_submission_readiness.json"
)

SCHEMA_VERSION = "structural-product-development-roadmap.v1"
REUSE_POLICY = "roadmap_aggregates_existing_release_dp_g1_paid_pilot_evidence"


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def _status_from_progress(numerator: int, denominator: int, *, blocked: bool) -> str:
    if denominator > 0 and numerator >= denominator and not blocked:
        return "ready"
    if numerator > 0:
        return "partial"
    return "blocked"


def _first_blockers(blockers: list[str], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for blocker in blockers:
        if not blocker or blocker in seen:
            continue
        seen.add(blocker)
        rows.append(blocker)
        if len(rows) >= limit:
            break
    return rows


def _count_pm_milestones(pm_report: dict[str, Any]) -> tuple[int, int]:
    rows = [row for row in _as_list(pm_report.get("milestones")) if isinstance(row, dict)]
    return (
        sum(
            1
            for row in rows
            if row.get("ok") is True or str(row.get("status") or "").lower() == "pass"
        ),
        len(rows),
    )


def _count_pm_release_areas(pm_report: dict[str, Any]) -> tuple[int, int]:
    rows = [row for row in _as_list(pm_report.get("release_area_matrix")) if isinstance(row, dict)]
    return (
        sum(
            1
            for row in rows
            if row.get("ok") is True or str(row.get("status") or "").lower() == "pass"
        ),
        len(rows),
    )


def _pm_release_area_blockers(pm_report: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for area in _as_list(pm_report.get("release_area_matrix")):
        if not isinstance(area, dict):
            continue
        area_id = str(area.get("area") or "release_area")
        for blocker in _as_list(area.get("blockers")):
            rows.append(f"{area_id}::{blocker}")
    return _first_blockers(rows)


def _dp_gate_blockers(dp_report: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for gate in _as_list(dp_report.get("final_gates")):
        if not isinstance(gate, dict) or gate.get("contract_pass") is True:
            continue
        item = str(gate.get("item") or "final_gate")
        first = str(_as_list(gate.get("blockers"))[0]) if _as_list(gate.get("blockers")) else "blocked"
        rows.append(f"{item}::{first}")
    return _first_blockers(rows)


def _source_paths() -> list[Path]:
    return [
        Path("scripts/build_structural_product_development_roadmap.py"),
        PRODUCT_READINESS,
        PM_RELEASE_GATE,
        DEVELOPER_PREVIEW_RC,
        RELEASE_FRESHNESS,
        G1_DIRECT_RESIDUAL,
        G1_FULL_LOAD_HIP,
        CUSTOMER_SHADOW,
        EXTERNAL_BENCHMARK_SUBMISSION,
    ]


def _stage_row(
    *,
    stage_id: str,
    label: str,
    numerator: int,
    denominator: int,
    blockers: list[str],
    next_actions: list[str],
    evidence_artifacts: list[Path],
    claim_boundary: str,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocked = bool(blockers) or numerator < denominator
    return {
        "stage_id": stage_id,
        "label": label,
        "status": _status_from_progress(numerator, denominator, blocked=blocked),
        "progress_percent": _pct(numerator, denominator),
        "passed_count": numerator,
        "required_count": denominator,
        "blockers": _first_blockers(blockers),
        "next_actions": next_actions,
        "evidence_artifacts": [str(path) for path in evidence_artifacts],
        "claim_boundary": claim_boundary,
        "summary": summary or {},
    }


def build_structural_product_development_roadmap(
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    snapshot = _load_json(repo_root, PRODUCT_READINESS)
    pm_report = _load_json(repo_root, PM_RELEASE_GATE)
    dp_report = _load_json(repo_root, DEVELOPER_PREVIEW_RC)
    freshness = _load_json(repo_root, RELEASE_FRESHNESS)
    g1_direct = _load_json(repo_root, G1_DIRECT_RESIDUAL)
    g1_full_load = _load_json(repo_root, G1_FULL_LOAD_HIP)
    customer_shadow = _load_json(repo_root, CUSTOMER_SHADOW)
    external_submission = _load_json(repo_root, EXTERNAL_BENCHMARK_SUBMISSION)

    components = _as_dict(snapshot.get("components"))
    solver_product = _as_dict(components.get("solver_product"))
    ci_streak = _as_dict(components.get("github_actions_ci_streak"))
    human_ux = _as_dict(components.get("human_ux_observation"))
    license_status = _as_dict(components.get("license_status"))
    external_receipts = _as_dict(components.get("external_benchmark_receipts"))

    freshness_summary = _as_dict(freshness.get("summary"))
    freshness_pass = _as_int(freshness_summary.get("pass_count"))
    freshness_total = _as_int(freshness_summary.get("artifact_count"))
    source_state_points = [
        freshness.get("contract_pass") is True,
        snapshot.get("evidence_fresh") is True,
        snapshot.get("snapshot_source_state_consistent") is True,
    ]

    milestone_pass, milestone_total = _count_pm_milestones(pm_report)
    release_area_pass, release_area_total = _count_pm_release_areas(pm_report)
    pm_numerator = milestone_pass + release_area_pass
    pm_denominator = milestone_total + release_area_total

    dp_pass = _as_int(dp_report.get("final_gate_pass_count"))
    dp_total = _as_int(dp_report.get("final_gate_count"))

    g1_direct_ready = g1_direct.get("contract_pass") is True
    g1_full_ready = g1_full_load.get("contract_pass") is True
    g1_numerator = int(g1_direct_ready) + int(g1_full_ready)
    g1_blockers = [str(row) for row in _as_list(g1_full_load.get("blockers"))]

    shadow_summary = _as_dict(customer_shadow.get("summary"))
    completed_shadow = _as_int(shadow_summary.get("completed_shadow_case_count"))
    required_shadow = _as_int(shadow_summary.get("min_completed_shadow_cases"), 3)
    external_summary = _as_dict(external_submission.get("summary"))
    paid_pilot_checks = [
        pm_report.get("paid_pilot_candidate") is True,
        completed_shadow >= required_shadow,
        external_receipts.get("ready") is True,
        snapshot.get("paid_pilot_ready") is True,
    ]
    paid_pilot_blockers = []
    if completed_shadow < required_shadow:
        paid_pilot_blockers.append(f"customer_shadow_below_required:{completed_shadow}/{required_shadow}")
    if external_receipts.get("ready") is not True:
        attached = _as_int(external_receipts.get("attached_count"))
        queue = _as_int(external_receipts.get("queue_count"))
        paid_pilot_blockers.append(f"external_benchmark_receipts_pending:{attached}/{queue}")
    if snapshot.get("paid_pilot_ready") is not True:
        paid_pilot_blockers.append("product_snapshot_paid_pilot_ready_false")

    commercial_checks = [
        pm_report.get("limited_commercial_milestone_ready") is True,
        external_summary.get("ready_to_start_full_submission_now") is True,
        external_receipts.get("ready") is True,
        snapshot.get("limited_commercial_ready") is True,
        solver_product.get("ready") is True,
    ]
    commercial_blockers = [
        str(row)
        for row in _as_list(solver_product.get("blockers"))
        if str(row)
    ]
    if snapshot.get("limited_commercial_ready") is not True:
        commercial_blockers.append("limited_commercial_ready_false")

    enterprise_checks = [
        snapshot.get("workstation_delivery_ready") is True,
        snapshot.get("independent_product_ready") is True,
        snapshot.get("assisted_service_pilot_ready") is True,
        snapshot.get("ga_enterprise_ready") is True,
    ]
    enterprise_blockers = []
    if snapshot.get("independent_product_ready") is not True:
        enterprise_blockers.append("independent_product_ready_false")
    if snapshot.get("assisted_service_pilot_ready") is not True:
        enterprise_blockers.append("assisted_service_pilot_ready_false")
    if snapshot.get("ga_enterprise_ready") is not True:
        enterprise_blockers.append("ga_enterprise_ready_false")

    stages = [
        _stage_row(
            stage_id="evidence_freshness_and_snapshot_integrity",
            label="Evidence freshness and snapshot integrity",
            numerator=sum(1 for item in source_state_points if item),
            denominator=len(source_state_points),
            blockers=[] if all(source_state_points) else ["freshness_or_snapshot_integrity_not_closed"],
            next_actions=["keep_release_evidence_freshness_report_green"],
            evidence_artifacts=[RELEASE_FRESHNESS, PRODUCT_READINESS],
            claim_boundary="Fresh metadata does not replace heavy validation or external release evidence.",
            summary={
                "fresh_artifact_pass_count": freshness_pass,
                "fresh_artifact_count": freshness_total,
                "snapshot_blocker_count": _as_int(snapshot.get("blocker_count")),
                "stale_or_inconsistent": _as_bool(snapshot.get("stale_or_inconsistent")),
            },
        ),
        _stage_row(
            stage_id="pm_release_gate",
            label="PM release gate",
            numerator=pm_numerator,
            denominator=pm_denominator,
            blockers=_pm_release_area_blockers(pm_report),
            next_actions=[
                "collect_30_pr_ci_and_nightly_ci_streak_evidence",
                "attach_product_license_status_approval",
                "attach_passing_human_new_user_observation",
            ],
            evidence_artifacts=[PM_RELEASE_GATE],
            claim_boundary="Milestone readiness is not full release readiness until all release areas pass.",
            summary={
                "milestone_pass_count": milestone_pass,
                "milestone_count": milestone_total,
                "release_area_green_count": release_area_pass,
                "release_area_count": release_area_total,
                "paid_pilot_candidate": _as_bool(pm_report.get("paid_pilot_candidate")),
                "ci_pr_consecutive_pass_count": _as_int(ci_streak.get("pr_consecutive_pass_count")),
                "ci_nightly_consecutive_pass_count": _as_int(
                    ci_streak.get("nightly_consecutive_pass_count")
                ),
                "license_status": str(license_status.get("status") or ""),
                "human_ux_blocker_count": _as_int(human_ux.get("blocker_count")),
            },
        ),
        _stage_row(
            stage_id="developer_preview_rc",
            label="Developer Preview release candidate",
            numerator=dp_pass,
            denominator=dp_total,
            blockers=_dp_gate_blockers(dp_report),
            next_actions=[
                "close_medium_model_pass_or_approved_review_gate",
                "close_large_model_crash_oom_free_gate",
                "attach_linux_windows_parity_receipts",
                "attach_human_new_user_workflow_observation",
            ],
            evidence_artifacts=[DEVELOPER_PREVIEW_RC],
            claim_boundary="Ready gates cannot be counted as a Developer Preview RC while any final gate remains blocked.",
            summary={
                "status": str(dp_report.get("status") or ""),
                "final_gate_pass_count": dp_pass,
                "final_gate_count": dp_total,
            },
        ),
        _stage_row(
            stage_id="g1_solver_closure",
            label="G1 solver closure",
            numerator=g1_numerator,
            denominator=2,
            blockers=g1_blockers,
            next_actions=[
                "continue_from_global_connectivity_and_consistent_newton_path",
                "prove_full_load_1_0_checkpoint",
                "prove_production_rocm_hip_residual_jacobian_lane",
            ],
            evidence_artifacts=[G1_DIRECT_RESIDUAL, G1_FULL_LOAD_HIP],
            claim_boundary="Direct residual closure is only one G1 axis; full-load HIP/Newton closure remains required.",
            summary={
                "direct_residual_terminal_gate_ready": g1_direct_ready,
                "full_load_hip_newton_lane_ready": g1_full_ready,
                "full_load_hip_observed_load_scale": _as_dict(components.get("g1")).get(
                    "full_load_hip_newton_lane_observed_load_scale"
                ),
            },
        ),
        _stage_row(
            stage_id="paid_pilot_readiness",
            label="Paid pilot readiness",
            numerator=sum(1 for item in paid_pilot_checks if item),
            denominator=len(paid_pilot_checks),
            blockers=paid_pilot_blockers,
            next_actions=[
                "complete_3_customer_shadow_cases",
                "attach_4_external_benchmark_terminal_receipts",
                "refresh_paid_pilot_scope_guard_after_receipts",
            ],
            evidence_artifacts=[CUSTOMER_SHADOW, EXTERNAL_BENCHMARK_SUBMISSION, PRODUCT_READINESS],
            claim_boundary="Paid-pilot candidate status is not paid-pilot readiness without customer shadow and receipt closure.",
            summary={
                "completed_shadow_case_count": completed_shadow,
                "required_shadow_case_count": required_shadow,
                "external_submission_package_ready": _as_bool(
                    external_summary.get("ready_to_start_full_submission_now")
                ),
                "external_receipt_attached_count": _as_int(external_receipts.get("attached_count")),
                "external_receipt_queue_count": _as_int(external_receipts.get("queue_count")),
                "paid_pilot_ready": _as_bool(snapshot.get("paid_pilot_ready")),
            },
        ),
        _stage_row(
            stage_id="commercial_solver_claim_upgrade",
            label="Commercial solver claim upgrade",
            numerator=sum(1 for item in commercial_checks if item),
            denominator=len(commercial_checks),
            blockers=commercial_blockers,
            next_actions=[
                "close_external_benchmark_receipts",
                "close_customer_shadow_reviews",
                "promote_limited_commercial_claim_only_after_solver_product_ready",
            ],
            evidence_artifacts=[PRODUCT_READINESS, EXTERNAL_BENCHMARK_SUBMISSION],
            claim_boundary="Commercial benchmark breadth and submission readiness do not authorize limited commercial claims while solver-product blockers remain.",
            summary={
                "limited_commercial_milestone_ready": _as_bool(
                    pm_report.get("limited_commercial_milestone_ready")
                ),
                "limited_commercial_ready": _as_bool(snapshot.get("limited_commercial_ready")),
                "solver_product_ready": _as_bool(solver_product.get("ready")),
                "solver_product_blocker_count": _as_int(solver_product.get("blocker_count")),
            },
        ),
        _stage_row(
            stage_id="enterprise_productization",
            label="Enterprise productization",
            numerator=sum(1 for item in enterprise_checks if item),
            denominator=len(enterprise_checks),
            blockers=enterprise_blockers,
            next_actions=[
                "add_durable_queue_postgres_and_object_storage_receipts",
                "add_oidc_rbac_tenant_isolation_receipts",
                "run_hosted_smoke_recovery_drill",
                "publish_slo_support_playbook_evidence",
            ],
            evidence_artifacts=[PRODUCT_READINESS],
            claim_boundary="Workstation delivery readiness is not hosted enterprise readiness.",
            summary={
                "workstation_delivery_ready": _as_bool(snapshot.get("workstation_delivery_ready")),
                "independent_product_ready": _as_bool(snapshot.get("independent_product_ready")),
                "assisted_service_pilot_ready": _as_bool(snapshot.get("assisted_service_pilot_ready")),
                "ga_enterprise_ready": _as_bool(snapshot.get("ga_enterprise_ready")),
            },
        ),
    ]

    total_passed = sum(_as_int(row.get("passed_count")) for row in stages)
    total_required = sum(_as_int(row.get("required_count")) for row in stages)
    stage_average = round(
        sum(float(row["progress_percent"]) for row in stages) / max(len(stages), 1),
        1,
    )
    blocked_stages = [row for row in stages if row["status"] != "ready"]
    primary_blocker = ""
    for row in stages:
        if row["blockers"]:
            primary_blocker = str(row["blockers"][0])
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "surface_id": "structural_product_development_roadmap",
        "surface_scope": "structural_solver_product_completion",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "input_checksums": input_checksums(_source_paths(), repo_root=repo_root),
        "reused_evidence": True,
        "reuse_policy": REUSE_POLICY,
        "status": "blocked" if blocked_stages else "ready",
        "contract_pass": not blocked_stages,
        "product_completion_claim": False if blocked_stages else True,
        "evidence_requirement_progress_percent": _pct(total_passed, total_required),
        "stage_average_progress_percent": stage_average,
        "passed_evidence_requirement_count": total_passed,
        "required_evidence_requirement_count": total_required,
        "ready_stage_count": len(stages) - len(blocked_stages),
        "stage_count": len(stages),
        "blocked_stage_count": len(blocked_stages),
        "primary_blocker": primary_blocker,
        "roadmap_stages": stages,
        "current_position": {
            "snapshot_status": str(snapshot.get("status") or ""),
            "snapshot_blocker_count": _as_int(snapshot.get("blocker_count")),
            "release_ready": _as_bool(snapshot.get("release_ready")),
            "paid_pilot_ready": _as_bool(snapshot.get("paid_pilot_ready")),
            "limited_commercial_ready": _as_bool(snapshot.get("limited_commercial_ready")),
            "workstation_delivery_ready": _as_bool(snapshot.get("workstation_delivery_ready")),
            "developer_preview_final_gates": f"{dp_pass}/{dp_total}",
            "pm_release_areas": f"{release_area_pass}/{release_area_total}",
            "pm_milestones": f"{milestone_pass}/{milestone_total}",
            "g1_direct_residual_terminal_gate_ready": g1_direct_ready,
            "g1_full_load_hip_newton_lane_ready": g1_full_ready,
        },
        "recommended_next_slice": [
            "land_ci_license_ux_release_area_evidence",
            "close_developer_preview_medium_large_and_parity_gates",
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path",
            "collect_customer_shadow_and_external_benchmark_terminal_receipts",
        ],
        "summary_line": (
            "Structural product roadmap: BLOCKED | "
            f"evidence_progress={_pct(total_passed, total_required)}% | "
            f"stage_average={stage_average}% | "
            f"ready_stages={len(stages) - len(blocked_stages)}/{len(stages)} | "
            f"primary_blocker={primary_blocker or 'none'}"
        ),
        "claim_boundary": (
            "This surface summarizes current evidence-readiness progress for the structural "
            "solver product. It is not a product-complete, paid-pilot, limited-commercial, "
            "or GA/enterprise claim while any stage remains blocked."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Product Development Roadmap",
        "",
        payload["summary_line"],
        "",
        "## Current Position",
        "",
    ]
    current = _as_dict(payload.get("current_position"))
    for key in sorted(current):
        lines.append(f"- `{key}`: `{current[key]}`")
    lines.extend(["", "## Roadmap Stages", ""])
    for row in _as_list(payload.get("roadmap_stages")):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row['stage_id']}`: {row['status']} "
            f"({row['passed_count']}/{row['required_count']}, "
            f"{row['progress_percent']}%)"
        )
        blockers = _as_list(row.get("blockers"))
        if blockers:
            lines.append(f"  - first blocker: `{blockers[0]}`")
        next_actions = _as_list(row.get("next_actions"))
        if next_actions:
            lines.append(f"  - next action: `{next_actions[0]}`")
    lines.extend(["", "## Claim Boundary", "", str(payload.get("claim_boundary") or ""), ""])
    return "\n".join(lines)


def write_structural_product_development_roadmap(
    *,
    repo_root: Path = ROOT,
    out_json: Path = DEFAULT_OUT_JSON,
    out_md: Path | None = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_structural_product_development_roadmap(repo_root=repo_root)
    resolved_json = out_json if out_json.is_absolute() else repo_root / out_json
    resolved_json.parent.mkdir(parents=True, exist_ok=True)
    resolved_json.write_text(_json_text(payload), encoding="utf-8")
    if out_md is not None:
        resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
        resolved_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--no-md", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_structural_product_development_roadmap(
        out_json=args.out_json,
        out_md=None if args.no_md else args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
