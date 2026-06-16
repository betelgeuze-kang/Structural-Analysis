#!/usr/bin/env python3
"""Validate product license status evidence for the PM security release area."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "license-status-closure-report.v1"
DEFAULT_LICENSE_STATUS = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/license_status_closure_report.json")
DEFAULT_TEMPLATE = Path("docs/templates/license_status.template.json")
PASS_STATUSES = {"active", "approved", "valid"}
PLACEHOLDER_TOKENS = {
    "LICENSE-ID",
    "LEGAL-OR-PRODUCT-APPROVAL-ID",
    "PRODUCT-OR-LEGAL-OWNER",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _looks_placeholder(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    upper = text.upper()
    return bool(
        upper in PLACEHOLDER_TOKENS
        or upper.startswith("TODO")
        or "PLACEHOLDER" in upper
        or "TEMPLATE ONLY" in upper
    )


def _scope_placeholders(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    return [item for item in values if _looks_placeholder(item)]


def _scope_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if value.strip() else 0
    if isinstance(value, list):
        return sum(1 for item in value if isinstance(item, str) and item.strip())
    return 0


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_report(
    *,
    license_status_path: Path,
    now: datetime | None = None,
    template_path: Path = DEFAULT_TEMPLATE,
) -> dict[str, Any]:
    now = now or _now_utc()
    payload = _load_json(license_status_path)
    status = _text(payload, "status").lower()
    tier = _text(payload, "tier", "edition")
    license_id = _text(payload, "license_id", "id")
    issuer = _text(payload, "issuer", "approved_by", "approver")
    approval_ref = _text(payload, "approval_ref", "approval_ticket", "legal_ticket", "decision_ref")
    product_scope = payload.get("product_scope", payload.get("scope", payload.get("features")))
    expires_at = _text(payload, "expires_at_utc", "expires_at", "valid_until")
    perpetual = bool(payload.get("perpetual", False))
    parsed_expiry = _parse_datetime(expires_at)
    note = _text(payload, "note")

    blockers: list[str] = []
    if not license_status_path.exists():
        blockers.append("license_status_file_missing")
    if status not in PASS_STATUSES:
        blockers.append("license_status_not_active")
    if not tier:
        blockers.append("license_tier_missing")
    if not license_id:
        blockers.append("license_id_missing")
    if not issuer:
        blockers.append("license_issuer_or_approver_missing")
    if not approval_ref:
        blockers.append("license_approval_reference_missing")
    if _scope_count(product_scope) == 0:
        blockers.append("license_product_scope_missing")
    if _looks_placeholder(license_id):
        blockers.append("license_id_placeholder")
    if _looks_placeholder(issuer):
        blockers.append("license_issuer_or_approver_placeholder")
    if _looks_placeholder(approval_ref):
        blockers.append("license_approval_reference_placeholder")
    if _scope_placeholders(product_scope):
        blockers.append("license_product_scope_placeholder")
    if bool(payload.get("template_only", False)) or _looks_placeholder(note):
        blockers.append("license_status_template_only")
    if not perpetual:
        if parsed_expiry is None:
            blockers.append("license_expiry_missing_or_invalid")
        elif parsed_expiry <= now:
            blockers.append("license_expired")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc().isoformat(),
        "license_status_path": str(license_status_path),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_LICENSE_STATUS_NOT_CLOSED",
        "blockers": blockers,
        "checks": {
            "license_status_file_present": license_status_path.exists(),
            "status_active_pass": status in PASS_STATUSES,
            "tier_present_pass": bool(tier),
            "license_id_present_pass": bool(license_id),
            "issuer_or_approver_present_pass": bool(issuer),
            "approval_reference_present_pass": bool(approval_ref),
            "product_scope_present_pass": _scope_count(product_scope) > 0,
            "placeholder_values_absent_pass": not any(
                blocker.endswith("_placeholder") or blocker == "license_status_template_only"
                for blocker in blockers
            ),
            "expiry_valid_pass": bool(perpetual or (parsed_expiry is not None and parsed_expiry > now)),
            "perpetual": perpetual,
        },
        "summary": {
            "status": status or "missing",
            "tier": tier,
            "license_id": license_id,
            "issuer_or_approver": issuer,
            "approval_ref": approval_ref,
            "product_scope_count": _scope_count(product_scope),
            "expires_at_utc": parsed_expiry.isoformat() if parsed_expiry else "",
            "template_path": str(template_path),
            "owner_action": (
                "Populate license_status.json from an approved product/legal decision, replacing all "
                "template placeholders with real approval evidence before release-area security can pass."
            ),
        },
        "claim_boundary": (
            "This report verifies that license status evidence is populated and current; it does not "
            "create legal approval or substitute for counsel/product-owner signoff."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--license-status", type=Path, default=DEFAULT_LICENSE_STATUS)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(license_status_path=args.license_status, template_path=args.template)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
