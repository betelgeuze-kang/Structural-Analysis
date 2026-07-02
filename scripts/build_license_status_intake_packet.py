#!/usr/bin/env python3
"""Build a product/legal intake packet for license status release evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "license-status-intake-packet.v1"
DEFAULT_LICENSE_STATUS = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_TEMPLATE = Path("docs/templates/license_status.template.json")
DEFAULT_CLOSURE_REPORT = Path("implementation/phase1/release_evidence/productization/license_status_closure_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/license_status_intake_packet.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/license_status_intake_packet.md")


FIELD_SPECS = (
    {
        "field": "status",
        "accepted_keys": ["status"],
        "required_value": "active | approved | valid",
        "closure_check": "status_active_pass",
        "owner_note": "Must reflect an approved product/legal decision, not a draft state.",
    },
    {
        "field": "tier",
        "accepted_keys": ["tier", "edition"],
        "required_value": "paid-pilot | limited-commercial",
        "closure_check": "tier_allowed_pass",
        "owner_note": "Must stay inside the PM-approved paid-pilot or limited-commercial boundary.",
    },
    {
        "field": "license_id",
        "accepted_keys": ["license_id", "id"],
        "required_value": "non-placeholder license or approval identifier",
        "closure_check": "license_id_present_pass",
        "owner_note": "Template values such as LICENSE-ID are rejected.",
    },
    {
        "field": "issuer_or_approver",
        "accepted_keys": ["issuer", "approved_by", "approver"],
        "required_value": "product/legal owner or approval authority",
        "closure_check": "issuer_or_approver_present_pass",
        "owner_note": "Template values such as product-or-legal-owner are rejected.",
    },
    {
        "field": "approver_role",
        "accepted_keys": ["approver_role", "approval_role"],
        "required_value": "product_owner | legal_counsel | product_and_legal | delegated_product_owner",
        "closure_check": "approver_role_allowed_pass",
        "owner_note": "Role is separate from the human approver identity and must be one of the allowed release roles.",
    },
    {
        "field": "approval_ref",
        "accepted_keys": ["approval_ref", "approval_ticket", "legal_ticket", "decision_ref"],
        "required_value": "legal/product approval reference",
        "closure_check": "approval_reference_present_pass",
        "owner_note": "Template values such as LEGAL-OR-PRODUCT-APPROVAL-ID are rejected.",
    },
    {
        "field": "approved_at_utc",
        "accepted_keys": ["approved_at_utc", "approved_at", "decision_at_utc"],
        "required_value": "timezone-aware approval timestamp, not future",
        "closure_check": "approved_at_not_future_pass",
        "owner_note": "Approval timestamp must be timezone-aware and no later than the report generation time.",
    },
    {
        "field": "evidence_ref",
        "accepted_keys": ["evidence_ref", "approval_artifact_ref", "evidence_path"],
        "required_value": "https URL, supported external ref, or existing local evidence path",
        "closure_check": "evidence_ref_resolvable_pass",
        "owner_note": "Approval reference identifies the decision; evidence_ref points to the retrievable artifact.",
    },
    {
        "field": "product_scope",
        "accepted_keys": ["product_scope", "scope", "features"],
        "required_value": (
            "review-assist, specified-structure-families, specified-workflows, "
            "engine-and-reviewer-evidence-package"
        ),
        "closure_check": "product_scope_boundary_pass",
        "owner_note": "Scope should preserve the PM claim boundary: review assist, specified families/workflows, evidence package.",
    },
    {
        "field": "expiry_or_perpetual",
        "accepted_keys": ["expires_at_utc", "expires_at", "valid_until", "perpetual"],
        "required_value": "future expiry timestamp or perpetual=true",
        "closure_check": "expiry_valid_pass",
        "owner_note": "Expired or missing validity evidence keeps the release-area security gate blocked.",
    },
)
DERIVED_CHECK_SPECS = (
    {
        "field": "approval_timeline",
        "required_value": "approved_at_utc <= now and approved_at_utc <= expiry when not perpetual",
        "closure_check": "approval_timeline_pass",
        "owner_note": "Approval date must be internally consistent with current validity.",
    },
    {
        "field": "approval_ref_distinct",
        "required_value": "approval_ref differs from license_id",
        "closure_check": "approval_ref_distinct_pass",
        "owner_note": "A license identifier cannot also serve as the approval decision evidence reference.",
    },
    {
        "field": "provenance_complete",
        "required_value": "approver role, approval time, evidence ref, and distinct approval ref all pass",
        "closure_check": "provenance_complete_pass",
        "owner_note": "Derived check for complete legal/product approval provenance.",
    },
    {
        "field": "evidence_ref_not_self_reference",
        "required_value": "evidence_ref must not point back to license_status.json",
        "closure_check": "evidence_ref_not_self_reference_pass",
        "owner_note": "The license status record cannot serve as its own approval evidence artifact.",
    },
    {
        "field": "evidence_ref_not_template_reference",
        "required_value": "evidence_ref must not point to the license status template",
        "closure_check": "evidence_ref_not_template_reference_pass",
        "owner_note": "Templates are owner input aids, not product/legal approval evidence.",
    },
    {
        "field": "evidence_ref_not_template_artifact",
        "required_value": "evidence_ref must not point to docs/templates or a .template.* artifact",
        "closure_check": "evidence_ref_not_template_artifact_pass",
        "owner_note": "Any template-like file is rejected as product/legal approval evidence.",
    },
    {
        "field": "evidence_ref_not_generated_gate_artifact",
        "required_value": "evidence_ref must not point to generated PM/license/readiness gate artifacts",
        "closure_check": "evidence_ref_not_generated_gate_artifact_pass",
        "owner_note": "Generated gate reports and intake packets verify approval evidence; they cannot be that evidence.",
    },
)


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


def _first_value(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return ""


def _display_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "")


def _derived_current_value(field: str, closure_summary: dict[str, Any]) -> str:
    if field == "approval_timeline":
        return (
            f"approved_at={closure_summary.get('approved_at_utc', '')}; "
            f"expires_at={closure_summary.get('expires_at_utc', '')}"
        )
    if field == "approval_ref_distinct":
        return (
            f"license_id={closure_summary.get('license_id', '')}; "
            f"approval_ref={closure_summary.get('approval_ref', '')}"
        )
    if field == "provenance_complete":
        return (
            f"role={closure_summary.get('approver_role', '')}; "
            f"evidence_ref={closure_summary.get('evidence_ref', '')}; "
            f"evidence_kind={closure_summary.get('evidence_ref_kind', '')}"
        )
    if field in {
        "evidence_ref_not_self_reference",
        "evidence_ref_not_template_reference",
        "evidence_ref_not_template_artifact",
        "evidence_ref_not_generated_gate_artifact",
    }:
        return str(closure_summary.get("evidence_ref_resolved_path", ""))
    return ""


def _next_actions(contract_pass: bool) -> list[str]:
    if contract_pass:
        return []
    return [
        "fill_license_status_record_from_template",
        "attach_product_or_legal_approval_evidence",
        "set_paid_pilot_or_limited_commercial_scope_boundary",
        "prove_future_expiry_or_perpetual_approval",
        "rerun_license_status_and_release_gates",
    ]


def _gate_unblock_plan(
    *,
    license_status_path: Path,
    template_path: Path,
    closure_report_path: Path,
    closure: dict[str, Any],
    field_rows: list[dict[str, Any]],
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    closure_plan = closure.get("gate_unblock_plan")
    if isinstance(closure_plan, list) and closure_plan:
        return [row for row in closure_plan if isinstance(row, dict)]
    failing_fields = [
        str(row["field"])
        for row in field_rows
        if row.get("closure_check_pass") is not True
    ]
    return [
        {
            "slot_id": "attach_license_status_record",
            "required_artifact": str(license_status_path),
            "template_artifact": str(template_path),
            "closure_report": str(closure_report_path),
            "failing_fields": failing_fields,
            "minimum_evidence": [
                "license_status.json populated from an approved product/legal decision",
                "all required fields populated without template placeholders",
                "contract_pass=true only after closure report validation passes",
            ],
        },
        {
            "slot_id": "rerun_validation_chain",
            "validation_commands": validation_commands,
            "minimum_evidence": [
                "license_status_closure_report.json contract_pass=true",
                "license_status_intake_packet.json contract_pass=true",
                "PM release security gate refreshed",
            ],
        },
    ]


def build_packet(
    *,
    license_status_path: Path = DEFAULT_LICENSE_STATUS,
    template_path: Path = DEFAULT_TEMPLATE,
    closure_report_path: Path = DEFAULT_CLOSURE_REPORT,
) -> dict[str, Any]:
    license_status = _load_json(license_status_path)
    template = _load_json(template_path)
    closure = _load_json(closure_report_path)
    closure_checks = _as_dict(closure.get("checks"))
    closure_summary = _as_dict(closure.get("summary"))
    closure_blockers = _as_list(closure.get("blockers"))

    rows: list[dict[str, Any]] = []
    for spec in (*FIELD_SPECS, *DERIVED_CHECK_SPECS):
        accepted_keys = [str(key) for key in spec.get("accepted_keys", [])]
        current_value = _first_value(license_status, accepted_keys) if accepted_keys else _derived_current_value(
            str(spec["field"]),
            closure_summary,
        )
        template_value = _first_value(template, accepted_keys) if accepted_keys else "derived from closure report"
        check_name = str(spec["closure_check"])
        rows.append(
            {
                "field": spec["field"],
                "accepted_keys": accepted_keys,
                "required_value": spec["required_value"],
                "current_value": _display_value(current_value),
                "template_value": _display_value(template_value),
                "closure_check": check_name,
                "closure_check_pass": bool(closure_checks.get(check_name, False)),
                "owner_note": spec["owner_note"],
            }
        )

    placeholder_absent = bool(closure_checks.get("placeholder_values_absent_pass", False))
    contract_pass = bool(closure.get("contract_pass", False))
    validation_commands = [
        f"python3 scripts/build_license_status_closure_report.py --out {DEFAULT_CLOSURE_REPORT}",
        f"python3 scripts/build_license_status_intake_packet.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        "python3 scripts/report_pm_release_gate.py "
        " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
        " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        "python3 scripts/build_pm_release_blocker_action_register.py "
        " --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
        " --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
    ]
    gate_unblock_plan = _gate_unblock_plan(
        license_status_path=license_status_path,
        template_path=template_path,
        closure_report_path=closure_report_path,
        closure=closure,
        field_rows=rows,
        validation_commands=validation_commands,
        contract_pass=contract_pass,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_LICENSE_STATUS_OWNER_INPUT_REQUIRED",
        "license_status_path": str(license_status_path),
        "template_path": str(template_path),
        "closure_report_path": str(closure_report_path),
        "summary_line": (
            f"License status intake: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"fields={sum(1 for row in rows if row['closure_check_pass'])}/{len(rows)} | "
            f"blockers={len(closure_blockers)}"
        ),
        "summary": {
            "owner_action": str(
                closure_summary.get(
                    "owner_action",
                    "Populate license_status.json from approved product/legal evidence.",
                )
            ),
            "closure_contract_pass": contract_pass,
            "closure_blocker_count": len(closure_blockers),
            "placeholder_values_absent_pass": placeholder_absent,
            "field_count": len(rows),
            "field_pass_count": sum(1 for row in rows if row["closure_check_pass"]),
            "provenance_complete_pass": bool(closure_checks.get("provenance_complete_pass", False)),
        },
        "claim_boundary": (
            "This intake packet is an owner handoff checklist. It does not create legal approval and "
            "does not make the PM security release area pass until the closure report passes."
        ),
        "field_rows": rows,
        "current_blockers": [str(blocker) for blocker in closure_blockers],
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "next_actions": _next_actions(contract_pass),
        "validation_commands": validation_commands,
    }


def _markdown(payload: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# License Status Intake Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `gate_unblock_plan_count`: `{payload['gate_unblock_plan_count']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `license_status_path`: `{payload['license_status_path']}`",
        f"- `template_path`: `{payload['template_path']}`",
        f"- `owner_action`: {payload['summary']['owner_action']}",
        "",
        "| Field | Current | Required | Closure Check |",
        "|---|---|---|---|",
    ]
    for row in payload["field_rows"]:
        lines.append(
            f"| `{cell(row['field'])}` | `{cell(row['current_value'])}` | {cell(row['required_value'])} | "
            f"`{cell(row['closure_check'])}` = `{row['closure_check_pass']}` |"
        )
    if payload["gate_unblock_plan"]:
        lines.extend(["", "## Gate Unblock Plan", ""])
        for row in payload["gate_unblock_plan"]:
            lines.append(f"- `{cell(row.get('slot_id', ''))}`")
            for item in row.get("minimum_evidence", []):
                lines.append(f"  - {cell(item)}")
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--license-status", type=Path, default=DEFAULT_LICENSE_STATUS)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--closure-report", type=Path, default=DEFAULT_CLOSURE_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(
        license_status_path=args.license_status,
        template_path=args.template,
        closure_report_path=args.closure_report,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
