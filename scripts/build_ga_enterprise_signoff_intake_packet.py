#!/usr/bin/env python3
"""Build an owner intake packet for GA/Enterprise external signoff evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ga-enterprise-signoff-intake-packet.v1"
DEFAULT_GA_READINESS = Path("implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_INDEPENDENT_VV_ATTESTATION = Path(
    "implementation/phase1/release_evidence/productization/independent_vv_attestation.json"
)
DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF = Path(
    "implementation/phase1/release_evidence/productization/family_validation_manual_signoff.json"
)
DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA = Path(
    "implementation/phase1/release_evidence/productization/customer_audit_failure_bundle_sla.json"
)
DEFAULT_INDEPENDENT_VV_ATTESTATION_TEMPLATE = Path("docs/templates/independent_vv_attestation.template.json")
DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF_TEMPLATE = Path(
    "docs/templates/family_validation_manual_signoff.template.json"
)
DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA_TEMPLATE = Path(
    "docs/templates/customer_audit_failure_bundle_sla.template.json"
)
ACCEPTED_SIGNOFF_DECISIONS = {"approved", "accepted", "pass", "signed", "approved_for_ga"}
PLACEHOLDER_MARKERS = ("TODO", "TBD", "PLACEHOLDER", "TEMPLATE", "REPLACE_ME", "OWNER_INPUT_REQUIRED")
OWNER_ORDER = ("independent_vv_owner", "validation_manual_owner", "customer_success_ops_owner", "ga_release_owner")


SIGNOFF_SPECS = {
    "independent_vv_missing": {
        "signoff": "independent_vv_attestation",
        "owner": "independent_vv_owner",
        "resolution_type": "external_independent_vv_attestation_required",
        "required_fields": [
            "contract_pass",
            "attestation_scope",
            "independent_reviewer",
            "independence_basis",
            "case_set_reference",
            "report_reference",
            "signed_at_utc",
            "approval_decision",
        ],
        "owner_note": "Attach independent V&V scope, reviewer identity, case set, report reference, and signed decision.",
        "default_evidence_path": DEFAULT_INDEPENDENT_VV_ATTESTATION,
        "default_template_path": DEFAULT_INDEPENDENT_VV_ATTESTATION_TEMPLATE,
        "default_acceptance": "`independent_vv_attestation.contract_pass == true`",
        "default_owner_action": "Attach third-party or independent V&V attestation with scope, case set, date, and approver.",
    },
    "family_validation_manual_signoff_missing": {
        "signoff": "family_validation_manual_signoff",
        "owner": "validation_manual_owner",
        "resolution_type": "external_family_validation_manual_signoff_required",
        "required_fields": [
            "contract_pass",
            "release_registry_ref",
            "validation_manual_ref",
            "family_rows",
            "signoff_owner",
            "signed_at_utc",
            "approval_decision",
        ],
        "owner_note": "Attach family-by-family validation manual signoff tied to the signed release registry.",
        "default_evidence_path": DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF,
        "default_template_path": DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF_TEMPLATE,
        "default_acceptance": "`family_validation_manual_signoff.contract_pass == true`",
        "default_owner_action": "Attach family-by-family validation manual signoff tied to the release registry.",
    },
    "customer_audit_failure_bundle_sla_missing": {
        "signoff": "customer_audit_failure_bundle_sla",
        "owner": "customer_success_ops_owner",
        "resolution_type": "external_customer_audit_failure_bundle_sla_required",
        "required_fields": [
            "contract_pass",
            "customer_or_ops_approver",
            "audit_export_acceptance_ref",
            "failure_bundle_export_ref",
            "support_sla_ref",
            "rollback_policy_ref",
            "signed_at_utc",
            "approval_decision",
        ],
        "owner_note": "Attach customer/ops acceptance for audit export, failure bundle, support SLA, and rollback path.",
        "default_evidence_path": DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA,
        "default_template_path": DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA_TEMPLATE,
        "default_acceptance": "`customer_audit_failure_bundle_sla.contract_pass == true`",
        "default_owner_action": "Attach customer audit/failure-bundle export acceptance and support SLA evidence.",
    },
}


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _owner_sort_key(owner: str) -> tuple[int, str]:
    try:
        return (OWNER_ORDER.index(owner), owner)
    except ValueError:
        return (len(OWNER_ORDER), owner)


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _looks_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    upper = value.strip().upper()
    return bool(not upper or any(marker in upper for marker in PLACEHOLDER_MARKERS))


def _field_present(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _evidence_field_status(payload: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
    missing_fields = [field for field in required_fields if not _field_present(payload, field)]
    placeholder_fields = [
        field for field in required_fields if _looks_placeholder(payload.get(field))
    ]
    decision = str(payload.get("approval_decision", "")).strip().lower()
    approval_decision_pass = decision in ACCEPTED_SIGNOFF_DECISIONS
    return {
        "missing_fields": missing_fields,
        "placeholder_fields": placeholder_fields,
        "approval_decision": decision,
        "approval_decision_pass": approval_decision_pass,
    }


def _evidence_state(*, evidence_present: bool, evidence_contract_pass: bool, field_status: dict[str, Any]) -> str:
    if evidence_contract_pass:
        return "ready_for_ga_readiness_regeneration"
    if not evidence_present:
        return "missing_external_signoff_evidence"
    if field_status["placeholder_fields"]:
        return "placeholder_external_signoff_evidence"
    if field_status["missing_fields"] or not field_status["approval_decision_pass"]:
        return "incomplete_external_signoff_evidence"
    return "external_signoff_contract_signal_missing"


def _verification_commands() -> list[str]:
    return [
        f"python3 scripts/build_ga_enterprise_readiness_report.py --out {DEFAULT_GA_READINESS} --fail-blocked",
        f"python3 scripts/build_ga_enterprise_signoff_intake_packet.py --out {DEFAULT_OUT} --fail-blocked",
        "python3 scripts/report_pm_release_gate.py "
        " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
        " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
    ]


def _source_artifacts(readiness: dict[str, Any], ga_readiness_report: Path) -> dict[str, str]:
    source_artifacts = {"ga_enterprise_readiness_report": str(ga_readiness_report)}
    source_artifacts.update(
        {
            str(key): str(value)
            for key, value in _as_dict(readiness.get("artifacts")).items()
            if str(value)
        }
    )
    return source_artifacts


def _owner_row_by_blocker(owner_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("blocker", "")): row
        for row in owner_rows
        if str(row.get("blocker", ""))
    }


def _evidence_path(owner_row: dict[str, Any], spec: dict[str, Any]) -> Path:
    path = owner_row.get("evidence_path") or spec.get("default_evidence_path") or ""
    return Path(str(path))


def _template_path(spec: dict[str, Any]) -> Path:
    return Path(str(spec.get("default_template_path", "")))


def _owner_packet(owner: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [row["signoff"] for row in rows if not row["evidence_contract_pass"]]
    source_artifacts: dict[str, str] = {}
    for row in rows:
        source_artifacts.update({str(key): str(value) for key, value in _as_dict(row.get("source_artifacts")).items()})
    return {
        "owner": owner,
        "request_state": "ready_for_ga_readiness_regeneration" if not incomplete else "owner_input_required",
        "signoff_count": len(rows),
        "signoff_pass_count": len(rows) - len(incomplete),
        "blockers": [row["blocker"] for row in rows],
        "signoffs": [row["signoff"] for row in rows],
        "evidence_paths": [row["evidence_path"] for row in rows],
        "template_paths": [row["template_path"] for row in rows],
        "evidence_states": _dedupe([str(_as_dict(row.get("evidence_status")).get("state", "")) for row in rows]),
        "source_artifacts": source_artifacts,
        "acceptance_criteria": _dedupe([row["acceptance"] for row in rows]),
        "required_fields": _dedupe([field for row in rows for field in _as_list(row.get("required_fields"))]),
        "missing_fields": _dedupe([field for row in rows for field in _as_list(row.get("missing_fields"))]),
        "placeholder_fields": _dedupe([field for row in rows for field in _as_list(row.get("placeholder_fields"))]),
        "verification_commands": _dedupe(
            [command for row in rows for command in _as_list(row.get("verification_commands"))]
        ),
        "external_input_required": any(row["external_input_required"] for row in rows),
        "owner_input_required": any(row["owner_input_required"] for row in rows),
        "incomplete_signoffs": incomplete,
        "request_rows": rows,
    }


def build_packet(*, ga_readiness_report: Path = DEFAULT_GA_READINESS) -> dict[str, Any]:
    readiness = _load_json(ga_readiness_report)
    blockers = [str(item) for item in _as_list(readiness.get("blockers"))]
    owner_rows = [row for row in _as_list(readiness.get("owner_handoff_rows")) if isinstance(row, dict)]
    owner_rows_by_blocker = _owner_row_by_blocker(owner_rows)
    source_artifacts = _source_artifacts(readiness, ga_readiness_report)
    rows: list[dict[str, Any]] = []
    for blocker, spec in SIGNOFF_SPECS.items():
        owner_row = owner_rows_by_blocker.get(blocker, {})
        evidence_path = _evidence_path(owner_row, spec)
        template_path = _template_path(spec)
        evidence = _load_json(evidence_path)
        required_fields = [str(field) for field in spec.get("required_fields", [])]
        field_status = _evidence_field_status(evidence, required_fields)
        evidence_contract_pass = bool(
            evidence_path.exists()
            and _reason_pass(evidence)
            and not field_status["missing_fields"]
            and not field_status["placeholder_fields"]
            and field_status["approval_decision_pass"]
        )
        evidence_state = _evidence_state(
            evidence_present=evidence_path.exists(),
            evidence_contract_pass=evidence_contract_pass,
            field_status=field_status,
        )
        owner_action = str(owner_row.get("owner_action", "") or spec.get("default_owner_action", ""))
        acceptance = str(owner_row.get("acceptance", "") or spec.get("default_acceptance", ""))
        rows.append(
            {
                "blocker": blocker,
                "signoff": str(spec.get("signoff", blocker)),
                "owner": str(spec.get("owner", "ga_release_owner")),
                "owner_input_required": not evidence_contract_pass,
                "external_input_required": not evidence_contract_pass,
                "resolution_type": str(spec.get("resolution_type", "external_ga_signoff_required")),
                "evidence_path": str(evidence_path),
                "evidence_present": evidence_path.exists(),
                "template_path": str(template_path),
                "template_present": template_path.exists(),
                "evidence_contract_pass": evidence_contract_pass,
                "evidence_status": {
                    "state": evidence_state,
                    "missing_field_count": len(field_status["missing_fields"]),
                    "placeholder_field_count": len(field_status["placeholder_fields"]),
                    "approval_decision": field_status["approval_decision"],
                    "approval_decision_pass": field_status["approval_decision_pass"],
                },
                "required_fields": required_fields,
                "missing_fields": field_status["missing_fields"],
                "placeholder_fields": field_status["placeholder_fields"],
                "approval_decision": field_status["approval_decision"],
                "approval_decision_pass": field_status["approval_decision_pass"],
                "owner_action": owner_action,
                "next_action": owner_action,
                "owner_note": str(spec.get("owner_note", "")),
                "acceptance": acceptance,
                "source_artifacts": source_artifacts,
                "verification_commands": _verification_commands(),
            }
        )

    current_open = [row["blocker"] for row in rows if not row["evidence_contract_pass"]]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["owner"], []).append(row)
    owner_packets = [
        _owner_packet(owner, grouped[owner])
        for owner in sorted(grouped, key=_owner_sort_key)
    ]
    current_blockers = _dedupe([*current_open, *blockers])
    readiness_pass = bool(_reason_pass(readiness) and not blockers)
    contract_pass = bool(readiness_pass and not current_open)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_GA_ENTERPRISE_SIGNOFF_OWNER_INPUT_REQUIRED",
        "ga_enterprise_readiness_report": str(ga_readiness_report),
        "summary_line": (
            f"GA enterprise signoff intake: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"signoffs={len(rows) - len(current_open)}/{len(rows)} | "
            f"readiness_pass={readiness_pass}"
        ),
        "summary": {
            "signoff_count": len(rows),
            "signoff_pass_count": len(rows) - len(current_open),
            "open_signoff_count": len(current_open),
            "owner_packet_count": len(owner_packets),
            "incomplete_owner_packet_count": sum(1 for packet in owner_packets if packet["incomplete_signoffs"]),
            "readiness_blocker_count": len(blockers),
            "external_input_required_count": sum(1 for row in rows if row["external_input_required"]),
            "source_artifact_count": len(source_artifacts),
            "template_count": sum(1 for row in rows if row["template_present"]),
            "owner_action": (
                "Populate the referenced GA/Enterprise signoff evidence files from independent V&V, "
                "family validation manual signoff, and customer audit/failure-bundle/SLA approval records."
            ),
        },
        "source_artifacts": source_artifacts,
        "owner_packets": owner_packets,
        "signoff_rows": rows,
        "current_blockers": current_blockers,
        "validation_commands": _verification_commands(),
        "claim_boundary": (
            "This packet is an owner handoff checklist. It does not create independent V&V, customer "
            "acceptance, legal approval, or support SLA commitments."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GA Enterprise Signoff Intake Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "## Owner Packets",
        "",
        "| Owner | State | Signoffs | Evidence | Template | Acceptance |",
        "|---|---|---|---|---|---|",
    ]
    for packet in payload["owner_packets"]:
        signoffs = "<br>".join(f"`{item}`" for item in packet["signoffs"])
        evidence = "<br>".join(f"`{item}`" for item in packet["evidence_paths"])
        templates = "<br>".join(f"`{item}`" for item in packet["template_paths"])
        acceptance = "<br>".join(str(item) for item in packet["acceptance_criteria"])
        lines.append(
            f"| `{packet['owner']}` | `{packet['request_state']}` | {signoffs} | {evidence} | {templates} | "
            f"{acceptance} |"
        )
    lines.extend(
        [
            "",
            "## Signoff Rows",
            "",
        "| Signoff | Owner | Evidence Status | Evidence | Template | Pass | Next Action | Required Fields |",
        "|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in payload["signoff_rows"]:
        evidence_status = row.get("evidence_status", {})
        status = evidence_status.get("state", "open") if isinstance(evidence_status, dict) else "open"
        lines.append(
            f"| `{row['signoff']}` | `{row['owner']}` | `{status}` | `{row['evidence_path']}` | "
            f"`{row['template_path']}` | `{row['evidence_contract_pass']}` | {row['next_action']} | "
            f"{', '.join(f'`{field}`' for field in row['required_fields'])} |"
        )
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ga-readiness-report", type=Path, default=DEFAULT_GA_READINESS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(ga_readiness_report=args.ga_readiness_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
