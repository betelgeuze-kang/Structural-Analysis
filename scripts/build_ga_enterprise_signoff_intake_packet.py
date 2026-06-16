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
ACCEPTED_SIGNOFF_DECISIONS = {"approved", "accepted", "pass", "signed", "approved_for_ga"}
PLACEHOLDER_MARKERS = ("TODO", "TBD", "PLACEHOLDER", "TEMPLATE", "REPLACE_ME", "OWNER_INPUT_REQUIRED")


SIGNOFF_SPECS = {
    "independent_vv_missing": {
        "signoff": "independent_vv_attestation",
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
    },
    "family_validation_manual_signoff_missing": {
        "signoff": "family_validation_manual_signoff",
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
    },
    "customer_audit_failure_bundle_sla_missing": {
        "signoff": "customer_audit_failure_bundle_sla",
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


def build_packet(*, ga_readiness_report: Path = DEFAULT_GA_READINESS) -> dict[str, Any]:
    readiness = _load_json(ga_readiness_report)
    blockers = [str(item) for item in _as_list(readiness.get("blockers"))]
    owner_rows = [row for row in _as_list(readiness.get("owner_handoff_rows")) if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for owner_row in owner_rows:
        blocker = str(owner_row.get("blocker", ""))
        spec = SIGNOFF_SPECS.get(blocker, {})
        evidence_path = Path(str(owner_row.get("evidence_path", "")))
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
        rows.append(
            {
                "blocker": blocker,
                "signoff": str(spec.get("signoff", blocker)),
                "evidence_path": str(evidence_path),
                "evidence_present": evidence_path.exists(),
                "evidence_contract_pass": evidence_contract_pass,
                "required_fields": required_fields,
                "missing_fields": field_status["missing_fields"],
                "placeholder_fields": field_status["placeholder_fields"],
                "approval_decision": field_status["approval_decision"],
                "approval_decision_pass": field_status["approval_decision_pass"],
                "owner_action": str(owner_row.get("owner_action", "")),
                "owner_note": str(spec.get("owner_note", "")),
                "acceptance": str(owner_row.get("acceptance", "")),
            }
        )

    current_open = [row["blocker"] for row in rows if not row["evidence_contract_pass"]]
    contract_pass = bool(_reason_pass(readiness) and not current_open)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_GA_ENTERPRISE_SIGNOFF_OWNER_INPUT_REQUIRED",
        "ga_enterprise_readiness_report": str(ga_readiness_report),
        "summary_line": (
            f"GA enterprise signoff intake: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"signoffs={len(rows) - len(current_open)}/{len(rows)} | "
            f"readiness_pass={_reason_pass(readiness)}"
        ),
        "summary": {
            "signoff_count": len(rows),
            "signoff_pass_count": len(rows) - len(current_open),
            "open_signoff_count": len(current_open),
            "readiness_blocker_count": len(blockers),
            "owner_action": (
                "Populate the referenced GA/Enterprise signoff evidence files from independent V&V, "
                "family validation manual signoff, and customer audit/failure-bundle/SLA approval records."
            ),
        },
        "signoff_rows": rows,
        "current_blockers": current_open,
        "validation_commands": [
            f"python3 scripts/build_ga_enterprise_readiness_report.py --out {DEFAULT_GA_READINESS}",
            f"python3 scripts/build_ga_enterprise_signoff_intake_packet.py --out {DEFAULT_OUT}",
            "python3 scripts/report_pm_release_gate.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        ],
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
        "| Signoff | Evidence | Pass | Required Fields |",
        "|---|---|---|---|",
    ]
    for row in payload["signoff_rows"]:
        lines.append(
            f"| `{row['signoff']}` | `{row['evidence_path']}` | `{row['evidence_contract_pass']}` | "
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
