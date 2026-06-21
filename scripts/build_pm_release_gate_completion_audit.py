#!/usr/bin/env python3
"""Build a requirement-level completion audit for the PM release gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-gate-completion-audit.v1"
DEFAULT_PM_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_CLOSURE_BOARD = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SNAPSHOT_EXCLUDED_KEY_MARKERS = (
    "sha256",
    "generated_at",
)

RELEASE_AREA_REQUIREMENTS = [
    ("basic_ci", "Basic CI", "PR/nightly 30 consecutive PASS evidence"),
    ("strict_ci", "Strict CI", "require NDTHA and require HIP or explicit CPU product mode"),
    (
        "evidence_freshness",
        "Evidence Freshness",
        "release evidence generated_at/source commit/engine version/input checksum/reuse marker and producer recency",
    ),
    ("core_engine", "Core Engine", "family p95 error within Limited/GA budget"),
    ("ndtha", "NDTHA", "no collapse false-pass, all converged, long profile pass"),
    ("residual", "Residual", "hard and recommended residual pass with fallback limits"),
    ("benchmark_breadth", "Benchmark Breadth", "Paid Pilot/Limited/GA validation case breadth"),
    ("runtime", "Runtime", "p95 runtime budget exceed rate within budget"),
    ("memory", "Memory", "OOM zero and peak memory budget report"),
    ("gpu_device", "GPU / Device", "release mode CPU fallback forbidden or scoped CPU-only product mode"),
    ("interop", "Interop", "MIDAS/KDS/OpenSees roundtrip trace evidence"),
    ("report", "Report", "reviewer package and reproduction commands"),
    ("ux", "UX", "new user completes sample project within 30 minutes"),
    ("support", "Support", "known issues, failure bundle, and rollback evidence"),
    ("security", "Security", "secrets/license/SBOM/repro build pass"),
    ("github_sync", "GitHub Development Sync", "read-only GitHub sync preflight is clean or explicitly approved"),
]

MILESTONE_REQUIREMENTS = [
    ("M1", "m1_residual_report_fixed", "ndtha_residual_gate_report.json fixed in release evidence", "release_evidence_path_fixed"),
    ("M1", "m1_recommended_residual_hard_fail", "recommended residual hard-fails in strict mode", "strict_recommended_residual_hard_fail_enabled"),
    ("M1", "m1_strict_recommended_residual_pass", "strict recommended residual pass", "strict_recommended_residual_pass"),
    ("M1", "m1_fallback_rate_limited", "fallback rate <= 5%", "fallback_rate_pass"),
    ("M1", "m1_residual_source_solver_raw", "solver_raw residual source ratio is reported", "residual_source_solver_raw_ratio_present"),
    ("M1", "m1_normalized_residual", "normalized residual is present", "normalized_residual_rows_pass"),
    ("M1", "m1_corrected_state_recompute", "corrected-state recompute after GNN correction", "corrected_state_recompute_pass"),
    ("M2", "m2_contact_material_cases", "contact-material coupled case count >= 10", "contact_material_coupled_case_count_pass"),
    ("M2", "m2_rc_steel_composite_contact", "RC/steel/composite/contact appear in one report", "rc_material_present"),
    ("M2", "m2_steel_material_present", "steel material evidence present", "steel_material_present"),
    ("M2", "m2_composite_material_present", "composite material evidence present", "composite_material_present"),
    ("M2", "m2_structural_contact_present", "structural contact evidence present", "structural_contact_pass"),
    ("M2", "m2_ssi_foundation_link", "SSI/foundation link included in core summary", "ssi_foundation_link_pass"),
    ("M2", "m2_panel_contact_reason_code", "panel/contact failure mode reason_code separated", "panel_contact_failure_reason_code_pass"),
    ("M2", "m2_nonlinear_residual_same_case", "nonlinear and residual pass in the same case", "nonlinear_residual_same_case_pass"),
    ("M3", "m3_require_ndtha", "require_ndtha passes", "require_ndtha_pass"),
    ("M3", "m3_require_hip_or_cpu_scope", "require_hip passes or CPU-only product mode is declared", "require_hip_pass"),
    ("M3", "m3_cpu_fallback_forbidden", "release-mode CPU fallback is forbidden", "cpu_fallback_release_forbidden_pass"),
    ("M3", "m3_device_residency", "device residency target is explicit and met", "device_residency_target_pass"),
    ("M3", "m3_host_copy_share", "host copy share <= 5%", "host_copy_share_pass"),
    ("M4", "m4_validation_cases", "total validation cases >= 100", "validation_case_count_pass"),
    ("M4", "m4_structure_families", "structure families >= 5", "structure_family_count_pass"),
    ("M4", "m4_holdout_cases", "holdout cases exist per family", "holdout_cases_per_family_present"),
    ("M4", "m4_worst_case_report", "worst-case report generated", "worst_case_report_pass"),
    ("M4", "m4_measured_open_data_split", "measured/open data split from fixtures", "measured_open_data_split_pass"),
    ("M5", "m5_viewer_mode", "reviewer/customer viewer preset", "viewer_reviewer_customer_surface_pass"),
    ("M5", "m5_pdf_or_reviewer_package", "PDF/report or reviewer package generated", "pdf_report_or_reviewer_package_pass"),
    ("M5", "m5_audit_trail", "audit trail has action and source row trace", "audit_trail_action_source_trace_pass"),
    ("M5", "m5_signed_release_registry", "release registry is signed", "signed_release_registry_pass"),
    ("M5", "m5_support_bundle_export", "support bundle one-click export passes", "support_bundle_export_pass"),
    ("M5", "m5_validation_manual", "validation manual is present and complete", "validation_manual_content_pass"),
    ("M5", "m5_limitation_manual", "limitation manual is present and complete", "limitation_manual_content_pass"),
]

RELEASE_TIER_REQUIREMENTS = [
    (
        "technical_paid_pilot_candidate",
        "Technical Paid Pilot Candidate",
        "limited milestone evidence supports only a constrained paid pilot candidate",
    ),
    (
        "paid_pilot_scope_guard_pass",
        "Paid Pilot Scope Guard",
        "paid pilot use is constrained by the scope guard and evidence-package references",
    ),
    (
        "limited_commercial_full_gate_ready",
        "Limited Commercial Full Gate",
        "Limited Commercial release requires full release-area gate readiness",
    ),
    (
        "ga_enterprise_evidence_gate_pass",
        "GA / Enterprise Evidence Gate",
        "GA/Enterprise requires independent V&V, family signoff, customer audit/failure bundle, and SLA evidence",
    ),
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_snapshot(item)
            for key, item in value.items()
            if not any(marker in str(key).lower() for marker in SNAPSHOT_EXCLUDED_KEY_MARKERS)
        }
    if isinstance(value, list):
        return [_stable_snapshot(item) for item in value]
    return value


def _indexed(rows: list[Any], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get(key, "") or "")
        if row_key:
            indexed[row_key] = row
    return indexed


def _closure_by_blocker(closure_board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _indexed(_as_list(closure_board.get("rows")), "blocker_id")


def _blocker_ids(area_id: str, blockers: list[str]) -> list[str]:
    return [
        blocker if blocker.startswith(f"{area_id}::") else f"{area_id}::{blocker}"
        for blocker in blockers
    ]


def _blocked_status(blocker_ids: list[str], closure_rows: dict[str, dict[str, Any]]) -> str:
    if not blocker_ids:
        return "blocked"
    closure_states = [str(_as_dict(closure_rows.get(blocker)).get("closure_state", "")) for blocker in blocker_ids]
    if any(not state or state == "handoff_incomplete" for state in closure_states):
        return "blocked_handoff_incomplete"
    if all(state == "external_owner_input_ready" for state in closure_states):
        return "blocked_external_owner_input_ready"
    if all(state == "local_remediation_ready" for state in closure_states):
        return "blocked_local_remediation_ready"
    return "blocked_mixed_closure_ready"


def _blocker_next_actions(
    blocker_ids: list[str],
    closure_rows: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for blocker_id in blocker_ids:
        closure = _as_dict(closure_rows.get(blocker_id))
        actions.append(
            {
                "blocker_id": blocker_id,
                "owner": str(closure.get("owner", "")),
                "closure_state": str(closure.get("closure_state", "missing")),
                "evidence_state": str(closure.get("evidence_state", "")),
                "next_action": str(closure.get("next_action", "")),
            }
        )
    return actions


def _next_action_summary(actions: list[dict[str, str]]) -> str:
    grouped: dict[str, list[str]] = {}
    for action in actions:
        next_action = action.get("next_action")
        if not next_action:
            continue
        grouped.setdefault(next_action, []).append(action["blocker_id"])
    parts: list[str] = []
    for next_action, blocker_ids in grouped.items():
        if len(blocker_ids) == 1:
            parts.append(f"{blocker_ids[0]}: {next_action}")
        else:
            parts.append(f"{len(blocker_ids)} blockers: {next_action}")
    return "; ".join(parts)


def _release_area_audit_rows(
    *,
    pm_report: dict[str, Any],
    closure_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    area_rows = _indexed(_as_list(pm_report.get("release_area_matrix")), "area")
    rows: list[dict[str, Any]] = []
    for area_id, title, requirement in RELEASE_AREA_REQUIREMENTS:
        source = _as_dict(area_rows.get(area_id))
        checks = _as_dict(source.get("checks"))
        summary = _as_dict(source.get("summary"))
        blockers = [str(item) for item in _as_list(source.get("blockers"))]
        blocker_ids = _blocker_ids(area_id, blockers)
        source_present = bool(source)
        ok = bool(source.get("ok", False))
        if ok:
            status = "pass"
        elif not source_present:
            status = "missing_evidence"
        else:
            status = _blocked_status(blocker_ids, closure_rows)
        next_actions = _blocker_next_actions(blocker_ids, closure_rows)
        rows.append(
            {
                "requirement_id": f"release_area.{area_id}",
                "group": "release_area",
                "area": area_id,
                "title": title,
                "requirement": requirement,
                "status": status,
                "pass": status == "pass",
                "source_present": source_present,
                "blockers": blocker_ids,
                "closure_states": {
                    blocker: str(_as_dict(closure_rows.get(blocker)).get("closure_state", "missing"))
                    for blocker in blocker_ids
                },
                "next_action": _next_action_summary(next_actions),
                "next_actions": next_actions,
                "checks": checks,
                "summary_snapshot": _stable_snapshot(summary),
                "evidence_artifacts": {
                    str(key): str(value)
                    for key, value in _as_dict(source.get("artifacts")).items()
                    if str(value)
                },
                "claim_boundary": str(source.get("claim_boundary", "")),
            }
        )
    return rows


def _milestone_audit_rows(pm_report: dict[str, Any]) -> list[dict[str, Any]]:
    milestone_rows = _indexed(_as_list(pm_report.get("milestones")), "milestone")
    rows: list[dict[str, Any]] = []
    for milestone_id, requirement_id, requirement, check_key in MILESTONE_REQUIREMENTS:
        source = _as_dict(milestone_rows.get(milestone_id))
        checks = _as_dict(source.get("checks"))
        source_present = bool(source)
        check_value = bool(checks.get(check_key, False))
        status = "pass" if check_value else ("missing_evidence" if not source_present else "blocked")
        rows.append(
            {
                "requirement_id": requirement_id,
                "group": "milestone",
                "milestone": milestone_id,
                "title": str(source.get("title", milestone_id)),
                "requirement": requirement,
                "status": status,
                "pass": status == "pass",
                "source_present": source_present,
                "check_key": check_key,
                "check_value": check_value,
                "blockers": [str(item) for item in _as_list(source.get("blockers"))],
                "checks": {check_key: checks.get(check_key, False)},
                "summary_snapshot": _stable_snapshot(_as_dict(source.get("summary"))),
                "evidence_artifacts": {
                    str(key): str(value)
                    for key, value in _as_dict(source.get("artifacts")).items()
                    if str(value)
                },
                "claim_boundary": "",
            }
        )
    return rows


def _release_tier_audit_rows(pm_report: dict[str, Any]) -> list[dict[str, Any]]:
    release_tiers = _as_dict(pm_report.get("release_tiers"))
    release_area_blockers = [str(item) for item in _as_list(pm_report.get("release_area_blockers"))]
    ga_blockers = [str(item) for item in _as_list(release_tiers.get("ga_enterprise_blockers"))]
    rows: list[dict[str, Any]] = []
    for check_key, title, requirement in RELEASE_TIER_REQUIREMENTS:
        source_present = check_key in release_tiers
        check_value = bool(release_tiers.get(check_key, False))
        status = "pass" if check_value else ("missing_evidence" if not source_present else "blocked")
        if check_key == "limited_commercial_full_gate_ready":
            blockers = release_area_blockers
            claim_boundary = (
                "Limited Commercial cannot be promoted while release-area blockers remain open, even when "
                "milestone evidence is green."
            )
            next_action = (
                "Close all release-area blockers, regenerate the PM release gate, and verify "
                "`release_tiers.limited_commercial_full_gate_ready == true` before Limited Commercial promotion."
            )
        elif check_key == "ga_enterprise_evidence_gate_pass":
            blockers = ga_blockers
            claim_boundary = str(
                release_tiers.get(
                    "ga_enterprise_note",
                    "GA/Enterprise requires independent V&V, family signoff, customer audit/failure bundle, and SLA evidence.",
                )
            )
            next_action = str(
                release_tiers.get(
                    "ga_enterprise_owner_action",
                    "Attach independent V&V, family validation-manual signoff, customer audit/failure bundle, and support SLA evidence.",
                )
            )
        elif check_key == "paid_pilot_scope_guard_pass":
            blockers = ["paid_pilot_scope_guard_missing_or_failed"] if not check_value else []
            claim_boundary = (
                "Paid pilot status is a constrained customer PoC scope only; it does not imply Limited, GA, "
                "or engineer-of-record replacement readiness."
            )
            next_action = (
                "Regenerate the paid pilot scope guard and keep all customer-facing use constrained to the "
                "scope guard until release-area blockers close."
            )
        else:
            blockers = ["technical_paid_pilot_candidate_false"] if not check_value else []
            claim_boundary = (
                "Technical paid pilot candidate status depends on local milestone evidence and still requires "
                "the paid-pilot scope guard before customer use."
            )
            next_action = "Regenerate the PM release gate after milestone or scope-guard evidence changes."
        rows.append(
            {
                "requirement_id": f"release_tier.{check_key}",
                "group": "release_tier",
                "title": title,
                "requirement": requirement,
                "status": status,
                "pass": status == "pass",
                "source_present": source_present,
                "check_key": check_key,
                "check_value": check_value,
                "blockers": blockers,
                "next_action": "" if check_value else next_action,
                "next_actions": [
                    {
                        "blocker_id": blocker,
                        "owner": "release_owner",
                        "closure_state": "blocked",
                        "evidence_state": "release_tier_blocked",
                        "next_action": next_action,
                    }
                    for blocker in blockers
                ],
                "checks": {check_key: check_value},
                "summary_snapshot": _stable_snapshot(
                    {
                        "recommended_scope": pm_report.get("recommended_scope", ""),
                        "release_tiers": release_tiers,
                    }
                ),
                "evidence_artifacts": {
                    "paid_pilot_scope_guard_report": str(
                        release_tiers.get("paid_pilot_scope_guard_report", "")
                    ),
                    "ga_enterprise_readiness_report": str(
                        release_tiers.get("ga_enterprise_readiness_report", "")
                    ),
                    "ga_enterprise_signoff_intake_packet": str(
                        release_tiers.get("ga_enterprise_signoff_intake_packet", "")
                    ),
                },
                "claim_boundary": claim_boundary,
            }
        )
    return rows


def build_audit(
    *,
    pm_report: Path = DEFAULT_PM_REPORT,
    closure_board: Path = DEFAULT_CLOSURE_BOARD,
) -> dict[str, Any]:
    pm_payload = _load_json(pm_report)
    closure_payload = _load_json(closure_board)
    closure_rows = _closure_by_blocker(closure_payload)
    release_rows = _release_area_audit_rows(pm_report=pm_payload, closure_rows=closure_rows)
    milestone_rows = _milestone_audit_rows(pm_payload)
    release_tier_rows = _release_tier_audit_rows(pm_payload)
    rows = [*release_rows, *milestone_rows, *release_tier_rows]
    blocked_rows = [row for row in rows if not row["pass"]]
    blocked_release_rows = [row for row in release_rows if not row["pass"]]
    blocked_release_tier_rows = [row for row in release_tier_rows if not row["pass"]]
    blocked_release_area_claim_boundary_missing_ids = [
        str(row["requirement_id"]) for row in blocked_release_rows if not str(row.get("claim_boundary", ""))
    ]
    blocked_release_area_next_action_missing_ids = [
        str(row["requirement_id"]) for row in blocked_release_rows if not str(row.get("next_action", ""))
    ]
    blocked_release_tier_claim_boundary_missing_ids = [
        str(row["requirement_id"])
        for row in blocked_release_tier_rows
        if not str(row.get("claim_boundary", ""))
    ]
    blocked_release_tier_next_action_missing_ids = [
        str(row["requirement_id"]) for row in blocked_release_tier_rows if not str(row.get("next_action", ""))
    ]
    contract_pass = bool(pm_payload.get("full_release_gate_ready", False) and not blocked_rows)
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_REQUIREMENTS_BLOCKED",
        "pm_release_gate_report": str(pm_report),
        "pm_release_blocker_closure_board": str(closure_board),
        "pm_summary_line": str(pm_payload.get("summary_line", "")),
        "summary_line": (
            "PM release gate completion audit: "
            f"{'PASS' if contract_pass else 'BLOCKED'} | "
            f"requirements={len(rows)} | pass={len(rows) - len(blocked_rows)} | blocked={len(blocked_rows)}"
        ),
        "summary": {
            "explicit_requirement_count": len(rows),
            "pass_requirement_count": len(rows) - len(blocked_rows),
            "blocked_requirement_count": len(blocked_rows),
            "release_area_requirement_count": len(release_rows),
            "release_area_pass_count": sum(1 for row in release_rows if row["pass"]),
            "release_area_blocked_count": sum(1 for row in release_rows if not row["pass"]),
            "blocked_release_area_claim_boundary_missing_count": len(
                blocked_release_area_claim_boundary_missing_ids
            ),
            "blocked_release_area_next_action_missing_count": len(blocked_release_area_next_action_missing_ids),
            "blocked_release_area_claim_boundary_missing_ids": blocked_release_area_claim_boundary_missing_ids,
            "blocked_release_area_next_action_missing_ids": blocked_release_area_next_action_missing_ids,
            "milestone_subrequirement_count": len(milestone_rows),
            "milestone_subrequirement_pass_count": sum(1 for row in milestone_rows if row["pass"]),
            "milestone_subrequirement_blocked_count": sum(1 for row in milestone_rows if not row["pass"]),
            "release_tier_requirement_count": len(release_tier_rows),
            "release_tier_pass_count": sum(1 for row in release_tier_rows if row["pass"]),
            "release_tier_blocked_count": sum(1 for row in release_tier_rows if not row["pass"]),
            "blocked_release_tier_claim_boundary_missing_count": len(
                blocked_release_tier_claim_boundary_missing_ids
            ),
            "blocked_release_tier_next_action_missing_count": len(blocked_release_tier_next_action_missing_ids),
            "blocked_release_tier_claim_boundary_missing_ids": blocked_release_tier_claim_boundary_missing_ids,
            "blocked_release_tier_next_action_missing_ids": blocked_release_tier_next_action_missing_ids,
            "blocked_external_owner_input_ready_count": status_counts.get(
                "blocked_external_owner_input_ready", 0
            ),
            "blocked_local_remediation_ready_count": status_counts.get("blocked_local_remediation_ready", 0),
            "blocked_handoff_incomplete_count": status_counts.get("blocked_handoff_incomplete", 0),
            "missing_evidence_count": status_counts.get("missing_evidence", 0),
            "status_counts": status_counts,
            "full_release_gate_ready": bool(pm_payload.get("full_release_gate_ready", False)),
            "release_area_gate_ready": bool(pm_payload.get("release_area_gate_ready", False)),
            "limited_commercial_milestone_ready": bool(
                pm_payload.get("limited_commercial_milestone_ready", False)
            ),
            "limited_commercial_release_ready": bool(
                pm_payload.get("limited_commercial_release_ready", pm_payload.get("limited_commercial_ready", False))
            ),
            "limited_commercial_ready": bool(pm_payload.get("limited_commercial_ready", False)),
            "paid_pilot_candidate": bool(pm_payload.get("paid_pilot_candidate", False)),
        },
        "snapshot_policy": {
            "stable_summary_snapshot": True,
            "excluded_key_markers": list(SNAPSHOT_EXCLUDED_KEY_MARKERS),
            "reason": (
                "Completion audit snapshots exclude volatile timestamps and hashes. Support bundle manifests "
                "hash this audit as an output artifact, so the audit avoids embedding support-bundle archive "
                "hashes that would create circular freshness claims."
            ),
        },
        "rows": rows,
        "claim_boundary": (
            "This audit expands the PM release gate into explicit requirements. A blocked row with owner-handoff "
            "ready still remains blocked until the required evidence is attached and the PM release gate is regenerated."
        ),
    }


def _markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Gate Completion Audit",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `explicit_requirement_count`: `{payload['summary']['explicit_requirement_count']}`",
        f"- `blocked_requirement_count`: `{payload['summary']['blocked_requirement_count']}`",
        f"- `blocked_release_area_next_action_missing_count`: `{payload['summary']['blocked_release_area_next_action_missing_count']}`",
        "",
        "| Requirement | Group | Status | Blockers | Next Action |",
        "|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        blockers = ", ".join(f"`{item}`" for item in row.get("blockers", [])) or "none"
        next_action = _markdown_cell(row.get("next_action", "")) or "none"
        lines.append(
            f"| `{row['requirement_id']}` {row['requirement']} | `{row['group']}` | "
            f"`{row['status']}` | {blockers} | {next_action} |"
        )
    lines.extend(["", payload["claim_boundary"]])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--closure-board", type=Path, default=DEFAULT_CLOSURE_BOARD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_audit(pm_report=args.pm_report, closure_board=args.closure_board)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
