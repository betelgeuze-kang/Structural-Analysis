#!/usr/bin/env python3
"""Validate product license status evidence for the PM security release area."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

# The release command is documented and tested with ``python -I -B``.  Setting
# this before importing repository modules also prevents a clean invocation
# from creating untracked ``__pycache__`` files that would invalidate the exact
# source-worktree check.
sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import input_checksums  # noqa: E402
from verify_rights_holder_license_decision import (  # noqa: E402
    CANONICAL_LICENSE_STATUS,
    DEFAULT_TRUST_ROOT as DEFAULT_RIGHTS_HOLDER_TRUST_ROOT,
    _load_object_bytes,
    _read_repository_file,
    inspect_rights_holder_license_decision,
    sha256_bytes,
    source_commit_head,
)


SCHEMA_VERSION = "license-status-closure-report.v1"
from release_evidence_metadata import CANONICAL_ENGINE_VERSION  # noqa: E402

ENGINE_VERSION = CANONICAL_ENGINE_VERSION
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
DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET = Path(
    "implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json"
)
DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET_MD = DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET.with_suffix(".md")
DEFAULT_PRODUCT_READINESS_SNAPSHOT = Path(
    "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json"
)
GENERATED_GATE_EVIDENCE_REF_PATHS = {
    DEFAULT_OUT,
    DEFAULT_INTAKE_PACKET,
    DEFAULT_INTAKE_PACKET_MD,
    DEFAULT_PM_RELEASE_GATE_REPORT,
    DEFAULT_PM_RELEASE_GATE_REPORT_MD,
    DEFAULT_PM_BLOCKER_ACTION_REGISTER,
    DEFAULT_PM_BLOCKER_ACTION_REGISTER_MD,
    DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET,
    DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET_MD,
    DEFAULT_PRODUCT_READINESS_SNAPSHOT,
}
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


def _git_head(repo_root: Path = REPO_ROOT) -> str:
    return source_commit_head(repo_root)


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
    try:
        path = Path(text).expanduser()
        candidates = (
            [path]
            if path.is_absolute()
            else [repo_root / path, license_status_path.parent / path]
        )
    except (OSError, UnicodeError, ValueError):
        return {"kind": "invalid_local_path", "resolvable": False, "resolved_path": ""}
    for candidate in candidates:
        try:
            if candidate.exists():
                return {"kind": "local_path", "resolvable": True, "resolved_path": str(candidate)}
        except (OSError, UnicodeError, ValueError):
            continue
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


def _is_generated_gate_artifact_path(path: Path, *, repo_root: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for generated_path in GENERATED_GATE_EVIDENCE_REF_PATHS:
        if _same_resolved_path(resolved, repo_root / generated_path):
            return True
    return False


def _validation_commands() -> list[str]:
    return [
        f"/usr/bin/python3 -I -B scripts/build_license_status_closure_report.py --fail-blocked --out {DEFAULT_OUT}",
        f"/usr/bin/python3 -I -B scripts/build_license_status_intake_packet.py --out {DEFAULT_INTAKE_PACKET} "
        f"--out-md {DEFAULT_INTAKE_PACKET_MD}",
        f"/usr/bin/python3 -I -B scripts/report_pm_release_gate.py --out {DEFAULT_PM_RELEASE_GATE_REPORT} "
        f"--out-md {DEFAULT_PM_RELEASE_GATE_REPORT_MD}",
        f"/usr/bin/python3 -I -B scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_PM_BLOCKER_ACTION_REGISTER} "
        f"--out-md {DEFAULT_PM_BLOCKER_ACTION_REGISTER_MD}",
    ]


def _next_actions(contract_pass: bool) -> list[str]:
    if contract_pass:
        return []
    return [
        "fill_license_status_record_from_template",
        "attach_signed_rights_holder_decision",
        "set_paid_pilot_or_limited_commercial_scope_boundary",
        "prove_explicit_future_expiry",
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
                "decision is signed by one non-revoked repository trust-root signer",
                "signature verifies over the canonical decision payload with RSA-SHA256",
                "canonical tracked license-policy path, version, hash, and covered first-party paths are bound",
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
            "slot_id": "prove_explicit_validity_window",
            "minimum_evidence": [
                "signed decision is bound to the exact source commit and root LICENSE hash",
                "replay_policy is exact_subject_and_source_commit_until_expiry",
                "expires_at_utc is timezone-aware and in the future",
                "decision validity does not exceed 90 days",
                "approved_at_utc is not later than expires_at_utc when an expiry exists",
            ],
        },
        {
            "slot_id": "attach_distinct_retrievable_evidence_reference",
            "minimum_evidence": [
                "evidence_ref is an existing local signed rights-holder decision JSON",
                "evidence_ref is not license_status.json itself",
                "evidence_ref is not docs/templates or a .template artifact",
                "evidence_ref is not a generated PM/license/readiness gate artifact",
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
    rights_holder_trust_root_path: Path = DEFAULT_RIGHTS_HOLDER_TRUST_ROOT,
    allow_staged_canonical_status: bool = False,
) -> dict[str, Any]:
    evaluation_time_override_requested = now is not None
    now = _now_utc()
    repo_root = repo_root.resolve()
    declared_license_status_path = license_status_path
    resolved_license_status_path = (
        license_status_path
        if license_status_path.is_absolute()
        else repo_root / license_status_path
    )
    status_file, status_bytes, status_path_state = _read_repository_file(
        resolved_license_status_path,
        repo_root=repo_root,
    )
    payload = _load_object_bytes(status_bytes)
    status_json_object_pass = bool(payload)
    canonical_status_path = repo_root / CANONICAL_LICENSE_STATUS
    staged_status_path = bool(
        allow_staged_canonical_status
        and status_file is not None
        and status_file.parent == canonical_status_path.parent
        and status_file.name.startswith(f".{canonical_status_path.name}.")
        and status_file.name.endswith(".tmp")
    )
    canonical_status_path_pass = bool(status_file == canonical_status_path)
    captured_status_sha256 = sha256_bytes(status_bytes) if status_file else ""
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
        license_status_path=resolved_license_status_path,
        repo_root=repo_root,
    )
    resolved_evidence_path = str(evidence_ref_resolution.get("resolved_path", "") or "")
    evidence_ref_self_reference = bool(
        resolved_evidence_path
        and _same_resolved_path(
            Path(resolved_evidence_path), resolved_license_status_path
        )
    )
    evidence_ref_template_reference = bool(
        resolved_evidence_path and _same_resolved_path(Path(resolved_evidence_path), repo_root / template_path)
    )
    evidence_ref_template_artifact = bool(
        resolved_evidence_path and _is_template_like_path(Path(resolved_evidence_path), repo_root=repo_root)
    )
    evidence_ref_generated_gate_artifact = bool(
        resolved_evidence_path
        and _is_generated_gate_artifact_path(Path(resolved_evidence_path), repo_root=repo_root)
    )
    product_scope = payload.get("product_scope", payload.get("scope", payload.get("features")))
    expires_at = _text(payload, "expires_at_utc", "expires_at", "valid_until")
    perpetual = bool(payload.get("perpetual", False))
    parsed_expiry = _parse_datetime(expires_at)
    note = _text(payload, "note")
    source_commit_sha = _git_head(repo_root)

    normalized_product_scope = [
        item.strip()
        for item in (product_scope if isinstance(product_scope, list) else [])
        if isinstance(item, str) and item.strip()
    ]
    rights_holder_decision: dict[str, Any] = {
        "schema_version": "rights-holder-license-decision-inspection.v1",
        "contract_pass": False,
        "signature_verified": False,
        "decision_id_binding_pass": False,
        "subject_binding_pass": False,
        "repository_license_source_binding_pass": False,
        "trust_root_source_binding_pass": False,
        "public_key_source_binding_pass": False,
        "license_policy_source_binding_pass": False,
        "source_tree_coverage_pass": False,
        "canonical_trust_root_pass": False,
        "source_worktree_binding_pass": False,
        "timeline_and_expiry_pass": False,
        "replay_scope_pass": False,
        "grants_contract_pass": False,
        "signer_policy_authorized_pass": False,
        "commercial_use_approved": False,
        "redistribution_approved": False,
        "third_party_material_redistribution_approved": False,
        "release_authority": False,
        "blockers": ["rights_holder_decision_local_signed_artifact_required"],
        "claim_boundary": (
            "No cryptographically verified rights-holder decision was available. "
            "Commercial use, redistribution, third-party material rights, and overall "
            "release authority remain ungranted."
        ),
    }
    decision_reference_eligible = bool(
        resolved_evidence_path
        and not evidence_ref_self_reference
        and not evidence_ref_template_reference
        and not evidence_ref_template_artifact
        and not evidence_ref_generated_gate_artifact
    )
    if decision_reference_eligible:
        try:
            rights_holder_decision = inspect_rights_holder_license_decision(
                decision_path=Path(resolved_evidence_path),
                trust_root_path=rights_holder_trust_root_path,
                repo_root=repo_root,
                expected_source_commit_sha=source_commit_sha,
                expected_decision_id=approval_ref,
                expected_license_id=license_id,
                expected_tier=tier,
                expected_approver_role=normalized_approver_role,
                expected_product_scope=normalized_product_scope,
                expected_rights_holder_id=issuer,
                expected_approved_at_utc=approved_at,
                expected_expires_at_utc=expires_at,
                allowed_untracked_paths=[resolved_license_status_path],
            )
        except Exception as error:
            rights_holder_decision["blockers"] = [
                "rights_holder_decision_verification_exception:"
                f"{type(error).__name__}"
            ]

    blockers: list[str] = []
    if evaluation_time_override_requested:
        blockers.append("caller_supplied_evaluation_time_not_allowed")
    if status_file is None:
        blockers.append("license_status_file_missing")
        blockers.append(f"license_status_{status_path_state}")
    elif not status_json_object_pass:
        blockers.append("license_status_json_invalid_or_empty")
    if staged_status_path:
        # Staging may be inspected by the atomic fill helper, but it is never an
        # authoritative closure result and therefore can never set
        # ``contract_pass`` or any authority field true.
        blockers.append("license_status_staged_not_authoritative")
    elif not canonical_status_path_pass:
        blockers.append("license_status_path_not_canonical")
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
    elif evidence_ref_generated_gate_artifact:
        blockers.append("license_evidence_ref_generated_gate_artifact")
    if _scope_count(product_scope) == 0:
        blockers.append("license_product_scope_missing")
    else:
        scope_values = _scope_values(product_scope)
        if not REQUIRED_PRODUCT_SCOPE.issubset(scope_values):
            blockers.append("license_product_scope_boundary_incomplete")
        if (
            scope_values != REQUIRED_PRODUCT_SCOPE
            or _scope_count(product_scope) != len(REQUIRED_PRODUCT_SCOPE)
        ):
            blockers.append("license_product_scope_not_exact")
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
    blockers.extend(str(item) for item in rights_holder_decision["blockers"])
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
        and not perpetual
        and parsed_expiry is not None
        and parsed_approved_at <= parsed_expiry
        and parsed_expiry > now
    )
    placeholder_values_absent_pass = not any(
        blocker.endswith("_placeholder") or blocker == "license_status_template_only" for blocker in blockers
    )
    if perpetual:
        blockers.append("rights_holder_decision_explicit_expiry_required")
    checksum_inputs = [
        Path("LICENSE"),
        Path("scripts/build_license_status_closure_report.py"),
        Path("scripts/verify_rights_holder_license_decision.py"),
        Path("canonical/rights-holder-license-decision.v1.schema.json"),
        Path("canonical/rights-holder-license-trust-root.v1.schema.json"),
        resolved_license_status_path,
        template_path,
        rights_holder_trust_root_path,
    ]
    public_key_path = str(rights_holder_decision.get("public_key_path") or "")
    if public_key_path:
        checksum_inputs.append(Path(public_key_path))
    license_policy_path = str(
        rights_holder_decision.get("license_policy_path") or ""
    )
    if license_policy_path:
        checksum_inputs.append(Path(license_policy_path))
    if resolved_evidence_path:
        checksum_inputs.append(Path(resolved_evidence_path))
    try:
        checksums = input_checksums(checksum_inputs, repo_root=repo_root)
    except Exception as error:
        checksums = {}
        blockers.append(f"license_input_checksum_exception:{type(error).__name__}")
    captured_checksums = {
        "LICENSE": str(
            rights_holder_decision.get("repository_license_sha256") or ""
        ),
        str(rights_holder_trust_root_path): str(
            rights_holder_decision.get("trust_root_sha256") or ""
        ),
        public_key_path: str(
            rights_holder_decision.get("public_key_sha256") or ""
        ),
        license_policy_path: str(
            rights_holder_decision.get("license_policy_sha256") or ""
        ),
        resolved_evidence_path: str(
            rights_holder_decision.get("decision_sha256") or ""
        ),
        str(resolved_license_status_path): captured_status_sha256,
    }
    for path_key, captured_sha256 in captured_checksums.items():
        if path_key and captured_sha256:
            checksums[path_key] = captured_sha256
    # Re-read the status through the same no-follow boundary after all other
    # verification work.  A concurrent replacement or content change must not
    # leave a passing report for bytes that are no longer canonical on disk.
    final_status_file, final_status_bytes, final_status_state = (
        _read_repository_file(resolved_license_status_path, repo_root=repo_root)
    )
    status_stable_pass = bool(
        final_status_file == status_file
        and final_status_state == "ok"
        and final_status_bytes == status_bytes
    )
    if not status_stable_pass:
        blockers.append("license_status_changed_during_verification")
    checksums = dict(sorted(checksums.items()))
    blockers = list(dict.fromkeys(blockers))
    staged_validation_pass = bool(
        staged_status_path
        and blockers == ["license_status_staged_not_authoritative"]
    )
    contract_pass = not blockers
    validation_commands = _validation_commands()

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "source_commit_sha": source_commit_sha,
        "engine_version": ENGINE_VERSION,
        "input_checksums": checksums,
        "reused_evidence": False,
        "status": "ready" if contract_pass else "blocked",
        "license_status_path": str(declared_license_status_path),
        "template_path": str(template_path),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_LICENSE_STATUS_NOT_CLOSED",
        "blockers": blockers,
        "summary_line": (
            f"License status: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"status={status or 'missing'} | tier={tier or 'missing'} | blockers={len(blockers)}"
        ),
        "checks": {
            "license_status_file_present": status_file is not None,
            "license_status_json_object_pass": status_json_object_pass,
            "license_status_path_canonical_pass": canonical_status_path_pass,
            "license_status_staged_validation_pass": staged_validation_pass,
            "license_status_stable_pass": status_stable_pass,
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
            "evidence_ref_not_generated_gate_artifact_pass": bool(
                evidence_ref and evidence_ref_resolution["resolvable"] and not evidence_ref_generated_gate_artifact
            ),
            "product_scope_present_pass": _scope_count(product_scope) > 0,
            "product_scope_boundary_pass": bool(
                _scope_values(product_scope) == REQUIRED_PRODUCT_SCOPE
                and _scope_count(product_scope) == len(REQUIRED_PRODUCT_SCOPE)
            ),
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
                and not evidence_ref_generated_gate_artifact
                and approval_ref
                and license_id
                and approval_ref.lower() != license_id.lower()
                and rights_holder_decision["contract_pass"] is True
            ),
            "rights_holder_decision_contract_pass": bool(
                rights_holder_decision["contract_pass"] is True
            ),
            "rights_holder_signature_verified_pass": bool(
                rights_holder_decision["signature_verified"] is True
            ),
            "rights_holder_decision_id_binding_pass": bool(
                rights_holder_decision["decision_id_binding_pass"] is True
            ),
            "rights_holder_subject_binding_pass": bool(
                rights_holder_decision["subject_binding_pass"] is True
            ),
            "repository_license_source_binding_pass": bool(
                rights_holder_decision["repository_license_source_binding_pass"]
                is True
            ),
            "rights_holder_trust_root_source_binding_pass": bool(
                rights_holder_decision["trust_root_source_binding_pass"] is True
            ),
            "rights_holder_public_key_source_binding_pass": bool(
                rights_holder_decision["public_key_source_binding_pass"] is True
            ),
            "rights_holder_license_policy_source_binding_pass": bool(
                rights_holder_decision["license_policy_source_binding_pass"]
                is True
            ),
            "rights_holder_source_tree_coverage_pass": bool(
                rights_holder_decision["source_tree_coverage_pass"] is True
            ),
            "rights_holder_canonical_trust_root_pass": bool(
                rights_holder_decision["canonical_trust_root_pass"] is True
            ),
            "source_worktree_binding_pass": bool(
                rights_holder_decision["source_worktree_binding_pass"] is True
            ),
            "rights_holder_timeline_and_expiry_pass": bool(
                rights_holder_decision["timeline_and_expiry_pass"] is True
            ),
            "rights_holder_replay_scope_pass": bool(
                rights_holder_decision["replay_scope_pass"] is True
            ),
            "rights_holder_signer_policy_authorized_pass": bool(
                rights_holder_decision["signer_policy_authorized_pass"] is True
            ),
            "expiry_valid_pass": bool(
                not perpetual
                and parsed_expiry is not None
                and parsed_expiry > now
            ),
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
                "Populate license_status.json from a cryptographically signed rights-holder "
                "decision made by a repository-approved signer, including exact source, "
                "root-license hash, tier, scope, expiry, and no template placeholders before "
                "release-area security can pass."
            ),
        },
        "rights_holder_decision": rights_holder_decision,
        "authority": {
            "first_party_commercial_use_approved": bool(
                contract_pass
                and rights_holder_decision["commercial_use_approved"] is True
            ),
            "first_party_redistribution_approved": bool(
                contract_pass
                and rights_holder_decision["redistribution_approved"] is True
            ),
            "third_party_material_redistribution_approved": False,
            "overall_release_authority": False,
        },
        "claim_boundary": (
            "This report verifies that license status evidence is cryptographically signed "
            "by a repository-approved rights-holder signer and bound to the exact source, "
            "clean source worktree, root-license hash, signer policy, tier, exact bounded "
            "scope, tracked license-policy artifact, covered paths, complete source-tree "
            "path coverage, maximum 90-day "
            "expiry, revocation, and bounded replay policy. It does not create legal "
            "approval, third-party material rights, or overall product release authority."
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
    parser.add_argument(
        "--rights-holder-trust-root",
        type=Path,
        default=DEFAULT_RIGHTS_HOLDER_TRUST_ROOT,
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--require-release-authority",
        action="store_true",
        help=(
            "Fail unless the cryptographic rights-holder gate, first- and third-party "
            "redistribution gates, and overall release authority are all explicitly true."
        ),
    )
    return parser


def _release_authority_pass(payload: dict[str, Any]) -> bool:
    decision = payload.get("rights_holder_decision")
    decision = decision if isinstance(decision, dict) else {}
    authority = payload.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    return bool(
        payload.get("contract_pass") is True
        and decision.get("contract_pass") is True
        and decision.get("signature_verified") is True
        and decision.get("subject_binding_pass") is True
        and decision.get("source_worktree_binding_pass") is True
        and decision.get("signer_policy_authorized_pass") is True
        and authority.get("first_party_commercial_use_approved") is True
        and authority.get("first_party_redistribution_approved") is True
        and authority.get("third_party_material_redistribution_approved") is True
        and authority.get("overall_release_authority") is True
    )


def main(argv: list[str] | None = None) -> int:
    if not (sys.flags.isolated and sys.flags.dont_write_bytecode):
        print(
            "license-status closure: BLOCKED | invoke with /usr/bin/python3 -I -B",
            file=sys.stderr,
        )
        return 2
    args = build_parser().parse_args(argv)
    payload = build_report(
        license_status_path=args.license_status,
        template_path=args.template,
        rights_holder_trust_root_path=args.rights_holder_trust_root,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    if args.require_release_authority and not _release_authority_pass(payload):
        print(
            "license-status closure: BLOCKED | full release authority not established",
            file=sys.stderr,
        )
        return 1
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
