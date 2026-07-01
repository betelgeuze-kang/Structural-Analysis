#!/usr/bin/env python3
"""Validate product license status evidence for the PM security release area."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import input_checksums  # noqa: E402


SCHEMA_VERSION = "license-status-closure-report.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_LICENSE_STATUS = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/license_status_closure_report.json")
DEFAULT_TEMPLATE = Path("docs/templates/license_status.template.json")
DEFAULT_INTAKE_PACKET = Path("implementation/phase1/release_evidence/productization/license_status_intake_packet.json")
DEFAULT_INTAKE_PACKET_MD = DEFAULT_INTAKE_PACKET.with_suffix(".md")
DEFAULT_PM_RELEASE_GATE_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_PM_RELEASE_GATE_REPORT_MD = DEFAULT_PM_RELEASE_GATE_REPORT.with_suffix(".md")
DEFAULT_PM_BLOCKER_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_PM_BLOCKER_ACTION_REGISTER_MD = DEFAULT_PM_BLOCKER_ACTION_REGISTER.with_suffix(".md")
PASS_STATUSES = {"active", "approved", "valid"}
ALLOWED_TIERS = {"paid-pilot", "limited-commercial"}
ALLOWED_APPROVER_ROLES = {"product_owner", "legal_counsel", "product_and_legal", "delegated_product_owner"}
REQUIRED_PRODUCT_SCOPE = {
    "review-assist",
    "specified-structure-families",
    "specified-workflows",
    "engine-and-reviewer-evidence-package",
}
EXTERNAL_REFERENCE_PREFIXES = ("ticket:", "jira:", "legal:", "docusign:")
PLACEHOLDER_TOKENS = {
    "APPROVED-AT-UTC",
    "APPROVER-ROLE",
    "EVIDENCE-REF",
    "LICENSE-ID",
    "LEGAL-OR-PRODUCT-APPROVAL-ID",
    "OWNER_INPUT_REQUIRED",
    "PRODUCT-OR-LEGAL-OWNER",
}
PLACEHOLDER_MARKERS = ("TODO", "TBD", "PLACEHOLDER", "TEMPLATE", "REPLACE_ME", "PENDING", "UNKNOWN", "N/A")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


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


def _looks_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    upper = text.upper()
    return bool(upper in PLACEHOLDER_TOKENS or any(marker in upper for marker in PLACEHOLDER_MARKERS))


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


def _scope_values(value: Any) -> set[str]:
    values: list[str] = []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    return {item.strip().lower() for item in values if item.strip()}


def _normalize_role(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _evidence_ref_resolution(reference: str, *, license_status_path: Path, repo_root: Path) -> dict[str, Any]:
    text = reference.strip()
    if not text:
        return {"kind": "missing", "resolvable": False, "resolved_path": ""}
    if text.lower().startswith(EXTERNAL_REFERENCE_PREFIXES):
        suffix = text.split(":", 1)[1].strip()
        return {"kind": "external_reference", "resolvable": bool(suffix), "resolved_path": ""}
    parsed = urlparse(text)
    if parsed.scheme:
        if parsed.scheme == "https" and bool(parsed.netloc):
            return {"kind": "https_url", "resolvable": True, "resolved_path": ""}
        return {"kind": "unsupported_url", "resolvable": False, "resolved_path": ""}
    path = Path(text).expanduser()
    candidates = [path] if path.is_absolute() else [repo_root / path, license_status_path.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return {"kind": "local_path", "resolvable": True, "resolved_path": str(candidate)}
    return {"kind": "local_path_missing", "resolvable": False, "resolved_path": ""}


def _same_resolved_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except Exception:
        return False


def _is_template_like_path(path: Path, *, repo_root: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    try:
        templates_dir = (repo_root / "docs" / "templates").resolve()
        if resolved.is_relative_to(templates_dir):
            return True
    except Exception:
        pass
    name = resolved.name.lower()
    return bool(".template." in name or name.endswith(".template"))


def _validation_commands() -> list[str]:
    return [
        f"python3 scripts/build_license_status_closure_report.py --out {DEFAULT_OUT}",
        f"python3 scripts/build_license_status_intake_packet.py --out {DEFAULT_INTAKE_PACKET} "
        f"--out-md {DEFAULT_INTAKE_PACKET_MD}",
        f"python3 scripts/report_pm_release_gate.py --out {DEFAULT_PM_RELEASE_GATE_REPORT} "
        f"--out-md {DEFAULT_PM_RELEASE_GATE_REPORT_MD}",
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_PM_BLOCKER_ACTION_REGISTER} "
        f"--out-md {DEFAULT_PM_BLOCKER_ACTION_REGISTER_MD}",
    ]


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
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    return [
        {
            "slot_id": "attach_license_status_record",
            "required_artifact": str(license_status_path),
            "template_artifact": str(template_path),
            "minimum_evidence": [
                "status is active, approved, or valid",
                "tier is paid-pilot or limited-commercial",
                "license_id, issuer_or_approver, approver_role, approval_ref, and approved_at_utc are populated",
                "template placeholders such as LICENSE-ID or OWNER_INPUT_REQUIRED are absent",
            ],
        },
        {
            "slot_id": "prove_product_legal_approval",
            "allowed_approver_roles": sorted(ALLOWED_APPROVER_ROLES),
            "minimum_evidence": [
                "approver_role is product_owner, legal_counsel, product_and_legal, or delegated_product_owner",
                "approved_at_utc is timezone-aware and not in the future",
                "approval_ref names the product/legal decision record",
                "approval_ref differs from license_id",
            ],
        },
        {
            "slot_id": "prove_scope_and_tier_boundary",
            "allowed_tiers": sorted(ALLOWED_TIERS),
            "required_product_scope": sorted(REQUIRED_PRODUCT_SCOPE),
            "minimum_evidence": [
                "product_scope includes review-assist",
                "product_scope includes specified-structure-families",
                "product_scope includes specified-workflows",
                "product_scope includes engine-and-reviewer-evidence-package",
            ],
        },
        {
            "slot_id": "prove_validity_window_or_perpetual_approval",
            "minimum_evidence": [
                "expires_at_utc is timezone-aware and in the future",
                "or perpetual=true is explicitly approved",
                "approved_at_utc is not later than expires_at_utc when an expiry exists",
            ],
        },
        {
            "slot_id": "attach_distinct_retrievable_evidence_reference",
            "minimum_evidence": [
                "evidence_ref is a ticket/jira/legal/docusign reference, https URL, or existing local evidence path",
                "evidence_ref is not license_status.json itself",
                "evidence_ref is not docs/templates or a .template artifact",
            ],
        },
        {
            "slot_id": "regenerate_release_gate_evidence",
            "validation_commands": validation_commands,
            "minimum_evidence": [
                "license_status_closure_report.json contract_pass=true",
                "license_status_intake_packet.json contract_pass=true",
                "PM release security area no longer blocks license_status_not_configured",
            ],
        },
    ]


def build_report(
    *,
    license_status_path: Path,
    now: datetime | None = None,
    template_path: Path = DEFAULT_TEMPLATE,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    now = now or _now_utc()
    repo_root = repo_root.resolve()
    payload = _load_json(license_status_path)
    status = _text(payload, "status").lower()
    tier = _text(payload, "tier", "edition").lower()
    license_id = _text(payload, "license_id", "id")
    issuer = _text(payload, "issuer", "approved_by", "approver")
    approver_role = _text(payload, "approver_role", "approval_role")
    normalized_approver_role = _normalize_role(approver_role)
    approval_ref = _text(payload, "approval_ref", "approval_ticket", "legal_ticket", "decision_ref")
    approved_at = _text(payload, "approved_at_utc", "approved_at", "decision_at_utc")
    parsed_approved_at = _parse_datetime(approved_at)
    evidence_ref = _text(payload, "evidence_ref", "approval_artifact_ref", "evidence_path")
    evidence_ref_resolution = _evidence_ref_resolution(
        evidence_ref,
        license_status_path=license_status_path,
        repo_root=repo_root,
    )
    resolved_evidence_path = str(evidence_ref_resolution.get("resolved_path", "") or "")
    evidence_ref_self_reference = bool(
        resolved_evidence_path and _same_resolved_path(Path(resolved_evidence_path), license_status_path)
    )
    evidence_ref_template_reference = bool(
        resolved_evidence_path and _same_resolved_path(Path(resolved_evidence_path), repo_root / template_path)
    )
    evidence_ref_template_artifact = bool(
        resolved_evidence_path and _is_template_like_path(Path(resolved_evidence_path), repo_root=repo_root)
    )
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
    elif tier not in ALLOWED_TIERS:
        blockers.append("license_tier_not_allowed")
    if not license_id:
        blockers.append("license_id_missing")
    if not issuer:
        blockers.append("license_issuer_or_approver_missing")
    if not approver_role:
        blockers.append("license_approver_role_missing")
    elif normalized_approver_role not in ALLOWED_APPROVER_ROLES:
        blockers.append("license_approver_role_invalid")
    if not approval_ref:
        blockers.append("license_approval_reference_missing")
    if approval_ref and license_id and approval_ref.lower() == license_id.lower():
        blockers.append("license_approval_ref_not_distinct")
    if not approved_at:
        blockers.append("license_approved_at_missing")
    elif parsed_approved_at is None:
        blockers.append("license_approved_at_invalid")
    elif parsed_approved_at > now:
        blockers.append("license_approved_at_future")
    if not evidence_ref:
        blockers.append("license_evidence_ref_missing")
    elif not bool(evidence_ref_resolution["resolvable"]):
        blockers.append("license_evidence_ref_unresolvable")
    elif evidence_ref_self_reference:
        blockers.append("license_evidence_ref_self_reference")
    elif evidence_ref_template_reference:
        blockers.append("license_evidence_ref_template_reference")
    elif evidence_ref_template_artifact:
        blockers.append("license_evidence_ref_template_artifact")
    if _scope_count(product_scope) == 0:
        blockers.append("license_product_scope_missing")
    elif not REQUIRED_PRODUCT_SCOPE.issubset(_scope_values(product_scope)):
        blockers.append("license_product_scope_boundary_incomplete")
    if _looks_placeholder(license_id):
        blockers.append("license_id_placeholder")
    if _looks_placeholder(issuer):
        blockers.append("license_issuer_or_approver_placeholder")
    if _looks_placeholder(approver_role):
        blockers.append("license_approver_role_placeholder")
    if _looks_placeholder(approval_ref):
        blockers.append("license_approval_reference_placeholder")
    if _looks_placeholder(approved_at):
        blockers.append("license_approved_at_placeholder")
    if _looks_placeholder(evidence_ref):
        blockers.append("license_evidence_ref_placeholder")
    if _scope_placeholders(product_scope):
        blockers.append("license_product_scope_placeholder")
    if bool(payload.get("template_only", False)) or _looks_placeholder(note):
        blockers.append("license_status_template_only")
    if not perpetual:
        if parsed_expiry is None:
            blockers.append("license_expiry_missing_or_invalid")
        elif parsed_expiry <= now:
            blockers.append("license_expired")
        if parsed_approved_at is not None and parsed_expiry is not None and parsed_approved_at > parsed_expiry:
            blockers.append("license_approval_after_expiry")

    approval_timeline_pass = bool(
        parsed_approved_at is not None
        and parsed_approved_at <= now
        and (perpetual or (parsed_expiry is not None and parsed_approved_at <= parsed_expiry))
    )
    placeholder_values_absent_pass = not any(
        blocker.endswith("_placeholder") or blocker == "license_status_template_only" for blocker in blockers
    )
    checksum_inputs = [license_status_path, template_path]
    if resolved_evidence_path:
        checksum_inputs.append(Path(resolved_evidence_path))
    contract_pass = not blockers
    validation_commands = _validation_commands()

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc().isoformat(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": input_checksums(checksum_inputs, repo_root=repo_root),
        "reused_evidence": False,
        "status": "ready" if contract_pass else "blocked",
        "license_status_path": str(license_status_path),
        "template_path": str(template_path),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_LICENSE_STATUS_NOT_CLOSED",
        "blockers": blockers,
        "summary_line": (
            f"License status: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"status={status or 'missing'} | tier={tier or 'missing'} | blockers={len(blockers)}"
        ),
        "checks": {
            "license_status_file_present": license_status_path.exists(),
            "status_active_pass": status in PASS_STATUSES,
            "tier_present_pass": bool(tier),
            "tier_allowed_pass": bool(tier in ALLOWED_TIERS),
            "license_id_present_pass": bool(license_id),
            "issuer_or_approver_present_pass": bool(issuer),
            "approver_role_present_pass": bool(approver_role),
            "approver_role_allowed_pass": bool(normalized_approver_role in ALLOWED_APPROVER_ROLES),
            "approval_reference_present_pass": bool(approval_ref),
            "approval_ref_distinct_pass": bool(approval_ref and license_id and approval_ref.lower() != license_id.lower()),
            "approved_at_present_pass": bool(approved_at),
            "approved_at_valid_pass": bool(parsed_approved_at is not None),
            "approved_at_not_future_pass": bool(parsed_approved_at is not None and parsed_approved_at <= now),
            "approval_timeline_pass": approval_timeline_pass,
            "evidence_ref_present_pass": bool(evidence_ref),
            "evidence_ref_resolvable_pass": bool(evidence_ref_resolution["resolvable"]),
            "evidence_ref_not_self_reference_pass": bool(
                evidence_ref and evidence_ref_resolution["resolvable"] and not evidence_ref_self_reference
            ),
            "evidence_ref_not_template_reference_pass": bool(
                evidence_ref and evidence_ref_resolution["resolvable"] and not evidence_ref_template_reference
            ),
            "evidence_ref_not_template_artifact_pass": bool(
                evidence_ref and evidence_ref_resolution["resolvable"] and not evidence_ref_template_artifact
            ),
            "product_scope_present_pass": _scope_count(product_scope) > 0,
            "product_scope_boundary_pass": bool(REQUIRED_PRODUCT_SCOPE.issubset(_scope_values(product_scope))),
            "placeholder_values_absent_pass": placeholder_values_absent_pass,
            "provenance_complete_pass": bool(
                normalized_approver_role in ALLOWED_APPROVER_ROLES
                and approval_ref
                and parsed_approved_at is not None
                and parsed_approved_at <= now
                and evidence_ref_resolution["resolvable"]
                and not evidence_ref_self_reference
                and not evidence_ref_template_reference
                and not evidence_ref_template_artifact
                and approval_ref
                and license_id
                and approval_ref.lower() != license_id.lower()
            ),
            "expiry_valid_pass": bool(perpetual or (parsed_expiry is not None and parsed_expiry > now)),
            "perpetual": perpetual,
        },
        "summary": {
            "status": status or "missing",
            "tier": tier,
            "license_id": license_id,
            "issuer_or_approver": issuer,
            "approver_role": normalized_approver_role,
            "allowed_tiers": sorted(ALLOWED_TIERS),
            "allowed_approver_roles": sorted(ALLOWED_APPROVER_ROLES),
            "approval_ref": approval_ref,
            "approved_at_utc": parsed_approved_at.isoformat() if parsed_approved_at else "",
            "evidence_ref": evidence_ref,
            "evidence_ref_kind": str(evidence_ref_resolution["kind"]),
            "evidence_ref_resolved_path": str(evidence_ref_resolution["resolved_path"]),
            "product_scope_count": _scope_count(product_scope),
            "required_product_scope": sorted(REQUIRED_PRODUCT_SCOPE),
            "product_scope_boundary_missing": sorted(REQUIRED_PRODUCT_SCOPE - _scope_values(product_scope)),
            "expires_at_utc": parsed_expiry.isoformat() if parsed_expiry else "",
            "template_path": str(template_path),
            "owner_action": (
                "Populate license_status.json from an approved product/legal decision, including approver "
                "role, approval timestamp, retrievable evidence reference, scoped product boundary, and no "
                "template placeholders before release-area security can pass."
            ),
        },
        "claim_boundary": (
            "This report verifies that license status evidence is populated and current; it does not "
            "create legal approval or substitute for counsel/product-owner signoff."
        ),
        "gate_unblock_plan": _gate_unblock_plan(
            license_status_path=license_status_path,
            template_path=template_path,
            validation_commands=validation_commands,
            contract_pass=contract_pass,
        ),
        "gate_unblock_plan_count": 0 if contract_pass else 6,
        "next_actions": _next_actions(contract_pass),
        "validation_commands": validation_commands,
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
