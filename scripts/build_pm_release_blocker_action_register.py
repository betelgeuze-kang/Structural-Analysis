#!/usr/bin/env python3
"""Build an actionable register for open PM release blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA_VERSION = "pm-release-blocker-action-register.v1"
ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
AGGREGATOR_REUSE_POLICY = "pm_release_blocker_action_register_aggregates_pm_report_and_freshness_actions"
DEFAULT_PM_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md")
DEFAULT_PM_REPORT_MD = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.md")
DEFAULT_CI_STREAK_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json"
)
DEFAULT_CI_STREAK_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
)
DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)
DEFAULT_LICENSE_STATUS_CLOSURE = Path(
    "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_LICENSE_STATUS_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/license_status_intake_packet.json"
)
DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT = Path(
    "implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json"
)
DEFAULT_UX_NEW_USER_OBSERVATION_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json"
)
DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json"
)
DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_owner_decision_application_plan.json"
)
DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_owner_review_packet.json"
)
DEFAULT_STRUCTURAL_SCOPE_CONTAMINATION_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_contamination_audit.json"
)
DEFAULT_STRUCTURAL_SCOPE_QUARANTINE_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_quarantine_manifest.json"
)
DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISIONS = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.json"
)
DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT = Path(
    "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json"
)
DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS = Path("implementation/phase1/customer_shadow_evidence_status.json")
DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/customer_shadow_evidence_intake_packet.json"
)
DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS = Path(
    "implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json"
)
DEFAULT_GA_ENTERPRISE_READINESS_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json"
)
DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.json"
)
GITHUB_SYNC_APPROVAL_PHRASE = "feature push + main fast-forward 승인"
STRUCTURAL_SCOPE_CLEANUP_BLOCKER_ID = "structural_scope_cleanup::owner_review_decisions_pending"


def _is_ux_human_new_user_blocker(*, namespace: str, code: str) -> bool:
    return namespace == "ux" and "human_new_user" in code


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _path_key(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_or_missing(path: Path) -> str:
    resolved = path if path.is_absolute() else ROOT / path
    if not resolved.exists() or not resolved.is_file():
        return "missing"
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _source_tracking_metadata(source_paths: list[Path]) -> dict[str, Any]:
    return {
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": {_path_key(path): _sha256_or_missing(path) for path in source_paths},
        "reused_evidence": True,
        "reuse_policy": AGGREGATOR_REUSE_POLICY,
        "aggregator_freshness_policy": {
            "mode": "direct_aggregator_source_tracking",
            "source_artifacts": [_path_key(path) for path in source_paths],
            "claim_boundary": (
                "This operator action aggregator does not close blockers. It exposes source commit "
                "and input checksums for its direct upstream PM/freshness artifacts so stale action "
                "boards can be detected."
            ),
        },
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _deduped(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _release_area_green_total(report: dict[str, Any]) -> tuple[int, int]:
    rows = [row for row in _as_list(report.get("release_area_matrix")) if isinstance(row, dict)]
    if rows:
        return sum(1 for row in rows if row.get("ok") is True), len(rows)
    match = re.search(r"release_areas_green=(\d+)/(\d+)", str(report.get("summary_line", "")))
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _structural_scope_cleanup_open(plan: dict[str, Any]) -> bool:
    if not plan:
        return False
    if bool(plan.get("evidence_closure_pass", False)):
        return False
    return bool(
        _as_int(plan.get("owner_decision_pending_count"), 0)
        or _as_int(plan.get("release_surface_owner_decision_required_count"), 0)
        or _as_int(plan.get("post_decision_cleanup_pending_count"), 0)
        or _as_int(plan.get("retain_quarantined_exception_count"), 0)
        or _as_list(plan.get("application_blockers"))
        or _as_list(plan.get("blockers"))
    )


def _structural_scope_source_row(
    *,
    plan: dict[str, Any],
    plan_path: Path,
) -> dict[str, Any]:
    owner_decision_recorded = _as_int(plan.get("owner_decision_recorded_count"), 0)
    owner_decision_pending = _as_int(plan.get("owner_decision_pending_count"), 0)
    owner_decision_total = _as_int(
        plan.get("owner_decision_total_count"),
        owner_decision_recorded + owner_decision_pending,
    )
    return {
        "title": "Structural Scope Cleanup",
        "summary": {
            "status": str(plan.get("status", "") or ""),
            "summary_line": str(plan.get("summary_line", "") or ""),
            "owner_decision_recorded_count": owner_decision_recorded,
            "owner_decision_pending_count": owner_decision_pending,
            "owner_decision_total_count": owner_decision_total,
            "release_surface_owner_decision_required_count": _as_int(
                plan.get("release_surface_owner_decision_required_count"), 0
            ),
            "release_surface_owner_decision_required_paths": [
                str(path)
                for path in _as_list(plan.get("release_surface_owner_decision_required_paths"))
                if str(path)
            ],
            "release_surface_first_batch_ready": bool(
                plan.get("release_surface_first_batch_ready", False)
            ),
            "release_surface_first_batch_application_ready": bool(
                plan.get("release_surface_first_batch_application_ready", False)
            ),
            "release_surface_first_batch_blockers": [
                str(item)
                for item in _as_list(plan.get("release_surface_first_batch_blockers"))
                if str(item)
            ],
            "release_surface_first_batch_application_blockers": [
                str(item)
                for item in _as_list(
                    plan.get("release_surface_first_batch_application_blockers")
                )
                if str(item)
            ],
            "release_surface_first_batch_cleanup_application_preflight": _as_dict(
                plan.get("release_surface_first_batch_cleanup_application_preflight")
            ),
            "release_surface_first_batch_template_paths": _as_dict(
                plan.get("release_surface_first_batch_template_paths")
            ),
            "post_decision_cleanup_pending_count": _as_int(
                plan.get("post_decision_cleanup_pending_count"), 0
            ),
            "retain_quarantined_exception_count": _as_int(
                plan.get("retain_quarantined_exception_count"), 0
            ),
            "pending_owner_decision_family_counts": _as_dict(
                plan.get("pending_owner_decision_family_counts")
            ),
            "pending_owner_decision_path_area_counts": _as_dict(
                plan.get("pending_owner_decision_path_area_counts")
            ),
            "next_owner_review_batch": _as_dict(plan.get("next_owner_review_batch")),
            "owner_decision_template_paths": _as_dict(
                plan.get("owner_decision_template_paths")
            ),
            "owner_decision_validation_pass": bool(
                plan.get("owner_decision_validation_pass", False)
            ),
            "owner_decision_validation_blockers": [
                str(item)
                for item in _as_list(plan.get("owner_decision_validation_blockers"))
                if str(item)
            ],
            "evidence_closure_pass": bool(plan.get("evidence_closure_pass", False)),
            "application_ready": bool(plan.get("application_ready", False)),
        },
        "artifacts": {
            "structural_scope_owner_decision_application_plan": str(plan_path),
            "structural_scope_owner_review_packet": str(
                DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET
            ),
            "structural_scope_contamination_audit": str(
                DEFAULT_STRUCTURAL_SCOPE_CONTAMINATION_AUDIT
            ),
            "structural_scope_quarantine_manifest": str(
                DEFAULT_STRUCTURAL_SCOPE_QUARANTINE_MANIFEST
            ),
            "structural_scope_owner_decisions": str(DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISIONS),
            "product_readiness_snapshot": str(
                Path("implementation/phase1/release_evidence/productization/product_readiness_snapshot.json")
            ),
        },
        "claim_boundary": str(
            plan.get("claim_boundary")
            or "Structural release-surface cleanup requires explicit owner delete/extract decisions before non-structural molecular artifacts can leave quarantine."
        ),
    }


def _split_blocker(blocker_id: str) -> tuple[str, str]:
    if "::" not in blocker_id:
        return "", blocker_id
    namespace, code = blocker_id.split("::", 1)
    return namespace, code


def _indexed_rows(rows: list[Any], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get(key, "") or "")
        if row_key:
            indexed[row_key] = row
    return indexed


def _owner_action(*, namespace: str, code: str, row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("summary"))
    if namespace == "structural_scope_cleanup":
        pending = _as_int(summary.get("owner_decision_pending_count"), 0)
        total = _as_int(summary.get("owner_decision_total_count"), pending)
        release_surface_pending = _as_int(
            summary.get("release_surface_owner_decision_required_count"), 0
        )
        release_paths = [
            str(path)
            for path in _as_list(summary.get("release_surface_owner_decision_required_paths"))
            if str(path)
        ]
        first_paths = ", ".join(release_paths[:3])
        path_clause = f" First release-surface paths: {first_paths}." if first_paths else ""
        return (
            "Complete structural scope cleanup before feature expansion: record owner "
            "`delete_from_structural_repository` or "
            "`extract_to_molecular_or_science_repository` decisions for the "
            f"{release_surface_pending} release-surface-first path(s) and the "
            f"{pending}/{total} pending quarantined PocketMD/GPCR/MD3Bead-family path(s), "
            "then rerun the structural scope application plan and contamination audit."
            f"{path_clause}"
        )
    if namespace == "fresh_full_validation":
        lane_id = code.split("::", 1)[0]
        runner = str(row.get("runner", "") or summary.get("runner", "") or lane_id)
        receipt = str(row.get("fresh_validation_receipt", "") or "")
        return (
            f"Run the `{runner}` fresh validation lane, attach `{receipt}` with "
            "`reused_evidence=false`, required provenance metadata, and a green contract result, "
            "then regenerate fresh full-validation and PM release evidence."
        )
    if namespace == "ga_enterprise":
        return str(row.get("owner_action", "") or "")
    if not namespace and code == "independent_vv_missing":
        return "Attach an approved independent V&V attestation and regenerate GA/Enterprise readiness evidence."
    if not namespace and code == "family_validation_manual_signoff_missing":
        return "Attach family validation manual signoff evidence and regenerate GA/Enterprise readiness evidence."
    if not namespace and code == "customer_audit_failure_bundle_sla_missing":
        return "Attach customer audit/failure-bundle and support SLA approval evidence before GA/Enterprise release."
    if namespace == "basic_ci":
        if code.startswith("pr_ci"):
            return str(summary.get("pr_owner_action", "") or "")
        if code.startswith("nightly_ci"):
            return str(summary.get("nightly_owner_action", "") or "")
    if namespace == "security" and "license" in code:
        return str(summary.get("license_status_owner_action", "") or "")
    if namespace == "security" and "frontend_dependency" in code:
        return (
            "Patch or replace vulnerable frontend dependencies, rerun `npm audit --audit-level high`, "
            "and regenerate frontend dependency audit evidence before security release signoff."
        )
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        direct = str(summary.get("human_observation_owner_action", "") or "")
        if direct:
            return direct
        return (
            "Attach a human new-user observation record for the sample project workflow, rerun "
            "`build_ux_new_user_observation_report.py`, and regenerate the PM release gate evidence."
        )
    if namespace == "evidence_freshness":
        return (
            "Regenerate the referenced P0/P1 release evidence with generated_at, source commit, engine version, "
            "input checksum, and reuse marker metadata, then rerun the freshness and PM release reports."
        )
    if namespace == "github_sync":
        github_sync_checks = _as_dict(row.get("checks"))
        preflight_fresh = bool(github_sync_checks.get("github_sync_preflight_source_state_fresh", True))
        preflight_kind = str(summary.get("preflight_source_state_kind", "") or "")
        if not preflight_fresh:
            return (
                "Tracked GitHub sync preflight is stale for the current release HEAD "
                f"(`{preflight_kind or 'source_delta'}`). Regenerate it with "
                "`python3 scripts/check_github_development_sync_preflight.py --json`, "
                f"obtain explicit R4 approval phrase `{GITHUB_SYNC_APPROVAL_PHRASE}` for "
                "the pending feature push and main fast-forward, then rerun the PM release gate."
            )
        feature_synced = bool(summary.get("feature_synced_to_head", False))
        main_synced = bool(summary.get("main_synced_to_head", False))
        if feature_synced and not main_synced:
            return (
                "Feature branch is synced to the release HEAD. Obtain explicit R4 "
                f"approval phrase `{GITHUB_SYNC_APPROVAL_PHRASE}` for the remaining "
                "main fast-forward, then run the pending main remote-update command "
                "from `check_github_development_sync_preflight.py --fetch --json`."
            )
        return (
            f"Obtain explicit R4 approval phrase `{GITHUB_SYNC_APPROVAL_PHRASE}`, then run the pending "
            "remote-update commands from `check_github_development_sync_preflight.py --fetch --json`."
        )
    if namespace == "customer_shadow":
        return (
            "Attach validated completed-project customer shadow metadata files under "
            "`implementation/phase1/customer_shadow_evidence/`, keep raw customer data retained by the customer, "
            "then regenerate customer shadow status and PM release evidence."
        )
    direct = str(summary.get("owner_action", "") or row.get("owner_action", "") or "")
    if direct:
        return direct
    title = str(row.get("title", namespace or "PM release gate") or namespace or "PM release gate")
    return f"Resolve `{code}` in {title} evidence, regenerate PM release reports, and attach the updated evidence."


def _owner(*, namespace: str, code: str) -> str:
    if namespace == "structural_scope_cleanup":
        return "release_scope_owner"
    if namespace == "fresh_full_validation":
        return "validation_lane_owner"
    if namespace == "customer_shadow":
        return "customer_success_ops_owner"
    if not namespace and code == "independent_vv_missing":
        return "independent_vv_owner"
    if not namespace and code == "family_validation_manual_signoff_missing":
        return "validation_manual_owner"
    if not namespace and code == "customer_audit_failure_bundle_sla_missing":
        return "customer_success_ops_owner"
    if namespace == "basic_ci":
        return "release_ci_owner"
    if namespace == "security" and "license" in code:
        return "product_legal_owner"
    if namespace == "security" and "frontend_dependency" in code:
        return "frontend_security_owner"
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return "ux_research_owner"
    return "release_owner"


def _resolution_type(*, namespace: str, code: str) -> str:
    if namespace == "structural_scope_cleanup":
        return "owner_review_scope_cleanup_required"
    if namespace == "fresh_full_validation":
        return "fresh_validation_receipt_required"
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        return "external_ga_enterprise_signoff_required"
    if namespace == "basic_ci" and "consecutive_pass" in code:
        return "external_tracked_ci_evidence_required"
    if namespace == "security" and "license" in code:
        return "product_legal_decision_required"
    if namespace == "security" and "frontend_dependency" in code:
        return "local_dependency_remediation_required"
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return "external_human_new_user_observation_required"
    if namespace == "evidence_freshness":
        return "release_evidence_metadata_required"
    if namespace == "github_sync":
        return "r4_remote_mutation_approval_required"
    if namespace == "customer_shadow":
        return "external_customer_shadow_evidence_required"
    return "release_evidence_remediation_required"


def _claim_boundary(*, namespace: str, code: str, row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("summary"))
    if namespace == "structural_scope_cleanup":
        direct = str(row.get("claim_boundary", "") or "")
        if direct:
            return direct
        return (
            "Non-structural molecular artifacts remain outside the building structural-analysis "
            "release surface until every quarantined path has an owner delete/extract decision, "
            "manual cleanup is applied, and the post-decision scope audit is green."
        )
    if namespace == "fresh_full_validation":
        return (
            "Fresh validation lane blockers require new lane execution receipts. Existing hydrated, "
            "publication, local-only, or reused evidence must not be counted as GA/Enterprise fresh validation."
        )
    if namespace == "customer_shadow":
        return (
            "Customer shadow blockers require real completed-project derived metadata. Templates, placeholder "
            "rows, synthetic cases, or customer raw data committed to Git must not close this blocker."
        )
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        return (
            "GA/Enterprise signoff blockers require approved external or owner-signed evidence; local "
            "test artifacts and templates do not close these approvals."
        )
    if namespace == "basic_ci":
        if code.startswith("pr_ci"):
            direct = str(summary.get("pr_claim_boundary", "") or "")
            if direct:
                return direct
        if code.startswith("nightly_ci"):
            direct = str(summary.get("nightly_claim_boundary", "") or "")
            if direct:
                return direct
    direct = str(row.get("claim_boundary", "") or summary.get("claim_boundary", "") or "")
    if direct:
        return direct
    return "This register is a blocker handoff artifact; it does not convert missing evidence into a release pass."


def _acceptance_criteria(*, namespace: str, code: str, row: dict[str, Any]) -> list[str]:
    summary = _as_dict(row.get("summary"))
    if namespace == "structural_scope_cleanup":
        return [
            "`structural_scope_owner_decision_application_plan.json.release_surface_first_batch_application_ready == true` before applying the first release-surface cleanup batch",
            "`structural_scope_owner_decision_application_plan.json.owner_decision_pending_count == 0`",
            "`structural_scope_owner_decision_application_plan.json.release_surface_owner_decision_required_count == 0`",
            "`structural_scope_owner_decision_application_plan.json.retain_quarantined_exception_count == 0`",
            "`structural_scope_owner_decision_application_plan.json.evidence_closure_pass == true` after manual delete/extract cleanup",
            "`check_structural_scope_contamination.py --fail-blocked` exits 0 after cleanup and release evidence regeneration",
        ]
    if namespace == "fresh_full_validation":
        lane_id = code.split("::", 1)[0]
        return [
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_present == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_fresh == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_lane_matches == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_runner_matches == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_contract_pass == true`",
            "`implementation/phase1/validate_fresh_validation_receipt.py --receipt <lane receipt> --fail-blocked` exits 0",
            f"`fresh_full_validation::{code}` absent from `ga_enterprise_blockers`",
        ]
    if not namespace and code == "independent_vv_missing":
        return [
            "`ga_enterprise_readiness_report.json.contract_pass == true` or no `independent_vv_missing` blocker",
            "`ga_enterprise_signoff_intake_packet.json` shows independent V&V evidence accepted",
            "`independent_vv_missing` absent from `ga_enterprise_blockers`",
        ]
    if not namespace and code == "family_validation_manual_signoff_missing":
        return [
            "`ga_enterprise_readiness_report.json.contract_pass == true` or no `family_validation_manual_signoff_missing` blocker",
            "`ga_enterprise_signoff_intake_packet.json` shows family validation manual signoff accepted",
            "`family_validation_manual_signoff_missing` absent from `ga_enterprise_blockers`",
        ]
    if not namespace and code == "customer_audit_failure_bundle_sla_missing":
        return [
            "`ga_enterprise_readiness_report.json.contract_pass == true` or no `customer_audit_failure_bundle_sla_missing` blocker",
            "`ga_enterprise_signoff_intake_packet.json` shows customer audit/failure-bundle/SLA evidence accepted",
            "`customer_audit_failure_bundle_sla_missing` absent from `ga_enterprise_blockers`",
        ]
    if namespace == "basic_ci" and code.startswith("pr_ci"):
        required = int(summary.get("required_consecutive_pass_count", 30) or 30)
        return [
            f"`pr_pass_streak_count >= {required}` in `pm_release_gate_report.json`",
            "`ci_streak_intake_packet.json.contract_pass == true`",
            "`basic_ci::pr_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`",
            "`github_actions_ci_streak_evidence.json` refreshed for the release signoff window",
        ]
    if namespace == "basic_ci" and code.startswith("nightly_ci"):
        required = int(summary.get("required_consecutive_pass_count", 30) or 30)
        return [
            f"`nightly_pass_streak_count >= {required}` in `pm_release_gate_report.json`",
            "`ci_streak_intake_packet.json.contract_pass == true`",
            "`basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`",
            "`github_actions_ci_streak_evidence.json` refreshed for the release signoff window",
        ]
    if namespace == "security" and "license" in code:
        return [
            "`license_status_closure_report.json.contract_pass == true`",
            "`license_status` is active and populated from approved product/legal evidence",
            "`security::license_status_not_configured` absent from `release_area_blockers`",
        ]
    if namespace == "security" and "frontend_dependency" in code:
        return [
            "`frontend_dependency_audit_report.json.contract_pass == true`",
            "`frontend_dependency_audit_report.json.summary.high_or_critical_vulnerability_count == 0`",
            "`security::frontend_dependency_audit_missing_or_failed` absent from `release_area_blockers`",
        ]
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        blocker_id = f"{namespace}::{code}"
        blocker_absence_criterion = f"`{blocker_id}` absent from `release_area_blockers`"
        return [
            "`ux_new_user_observation_report.json.contract_pass == true`",
            "`human_new_user_sample_30min_pass == true` in `pm_release_gate_report.json`",
            blocker_absence_criterion,
        ]
    if namespace == "evidence_freshness":
        blocker_id = f"{namespace}::{code}"
        return [
            "`release_evidence_freshness_report.json.contract_pass == true`",
            "`source_commit_rows_match`, `engine_version_rows_present`, `input_checksum_rows_present`, "
            "`reuse_marker_rows_present`, and `dependency_mtime_rows_pass` are true in `pm_release_gate_report.json`",
            f"`{blocker_id}` absent from `release_area_blockers`",
        ]
    if namespace == "github_sync":
        feature_ref = str(summary.get("remote_feature_ref", "") or "remote feature ref")
        main_ref = str(summary.get("remote_main_ref", "") or "origin/main")
        return [
            f"Explicit R4 approval phrase received: `{GITHUB_SYNC_APPROVAL_PHRASE}`",
            "`check_github_development_sync_preflight.py --fetch --json` reports `remote_sync_needed == false`",
            "`github_sync` absent from `release_area_blockers` after PM release gate regeneration",
            f"`{feature_ref}` and `{main_ref}` match local release HEAD",
        ]
    if namespace == "customer_shadow":
        return [
            "`customer_shadow_evidence_status.json.contract_pass == true`",
            "`customer_shadow_evidence_status.json.summary.completed_shadow_case_count >= 3`",
            "Every attached customer shadow JSON passes `validate_customer_shadow_evidence.py --fail-blocked`",
            "`customer_shadow::completed_shadow_case_count_below_minimum` absent from `ga_enterprise_blockers`",
        ]
    return [
        f"`{namespace}::{code}` absent from `full_release_blockers`",
        "`full_release_gate_ready == true` after PM report regeneration",
    ]


def _reproduction_commands(*, namespace: str, code: str) -> list[str]:
    pm_report_command = (
        "python3 scripts/report_pm_release_gate.py "
        f"--out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}"
    )
    if namespace == "structural_scope_cleanup":
        return [
            f"python3 scripts/check_structural_scope_contamination.py --out {DEFAULT_STRUCTURAL_SCOPE_CONTAMINATION_AUDIT} --out-md {DEFAULT_STRUCTURAL_SCOPE_CONTAMINATION_AUDIT.with_suffix('.md')}",
            f"python3 scripts/build_structural_scope_owner_review_packet.py --out {DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET} --out-md {DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET.with_suffix('.md')} --write-decision-template",
            f"python3 scripts/build_structural_scope_owner_decision_application_plan.py --out {DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN} --out-md {DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN.with_suffix('.md')}",
            "python3 scripts/build_product_readiness_snapshot.py",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "fresh_full_validation":
        return [
            f"python3 scripts/build_fresh_full_validation_lane_status.py --out {DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS} --out-md {DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS.with_suffix('.md')}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        return [
            f"python3 scripts/build_ga_enterprise_readiness_report.py --out {DEFAULT_GA_ENTERPRISE_READINESS_REPORT}",
            f"python3 scripts/build_ga_enterprise_signoff_intake_packet.py --out {DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET} --out-md {DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET.with_suffix('.md')}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "basic_ci":
        return [
            f"python3 scripts/build_github_actions_ci_streak_evidence.py --out {DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE}",
            f"python3 scripts/build_ci_consecutive_pass_manifest.py --out {DEFAULT_CI_STREAK_MANIFEST}",
            f"python3 scripts/build_ci_streak_intake_packet.py --out {DEFAULT_CI_STREAK_INTAKE_PACKET}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "security" and "license" in code:
        return [
            f"python3 scripts/build_license_status_intake_packet.py --out {DEFAULT_LICENSE_STATUS_INTAKE_PACKET}",
            f"python3 scripts/build_license_status_closure_report.py --out {DEFAULT_LICENSE_STATUS_CLOSURE}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "security" and "frontend_dependency" in code:
        return [
            "npm audit --audit-level high",
            f"python3 scripts/build_frontend_dependency_audit_report.py --out {DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return [
            f"python3 scripts/build_ux_new_user_observation_report.py --out {DEFAULT_UX_NEW_USER_OBSERVATION_REPORT}",
            f"python3 scripts/build_ux_new_user_observation_intake_packet.py --out {DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "evidence_freshness":
        return [
            f"python3 scripts/report_release_evidence_freshness.py --out {DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT} --out-md {DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT.with_suffix('.md')}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "github_sync":
        return [
            "python3 scripts/check_github_development_sync_preflight.py --fetch --json",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "customer_shadow":
        return [
            f"python3 scripts/check_customer_shadow_evidence_status.py --out {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS} --json",
            f"python3 scripts/build_customer_shadow_evidence_intake_packet.py --out {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET} --out-md {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET.with_suffix('.md')}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    return [
        pm_report_command,
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
    ]


def _verification_commands(*, namespace: str, code: str) -> list[str]:
    if namespace == "structural_scope_cleanup":
        return [
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-release-surface-first-blocked",
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions",
            "python3 scripts/check_structural_scope_contamination.py --fail-blocked",
            "python3 scripts/build_product_readiness_snapshot.py --check",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "fresh_full_validation":
        return [
            f"python3 scripts/build_fresh_full_validation_lane_status.py --out {DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS} --out-md {DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS.with_suffix('.md')} --fail-blocked",
            f"python3 scripts/report_pm_release_gate.py --out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        return [
            f"python3 scripts/build_ga_enterprise_readiness_report.py --out {DEFAULT_GA_ENTERPRISE_READINESS_REPORT} --fail-blocked",
            f"python3 scripts/build_ga_enterprise_signoff_intake_packet.py --out {DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET} --out-md {DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET.with_suffix('.md')} --fail-blocked",
        ]
    if namespace == "basic_ci":
        return [
            f"python3 scripts/build_ci_streak_intake_packet.py --out {DEFAULT_CI_STREAK_INTAKE_PACKET} --fail-blocked",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "security" and "license" in code:
        return [
            f"python3 scripts/build_license_status_closure_report.py --out {DEFAULT_LICENSE_STATUS_CLOSURE} --fail-blocked",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "security" and "frontend_dependency" in code:
        return [
            "npm audit --audit-level high",
            f"python3 scripts/build_frontend_dependency_audit_report.py --out {DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT} --fail-blocked",
        ]
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return [
            f"python3 scripts/build_ux_new_user_observation_report.py --out {DEFAULT_UX_NEW_USER_OBSERVATION_REPORT} --fail-blocked",
            f"python3 scripts/build_ux_new_user_observation_intake_packet.py --out {DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET} --fail-blocked",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "evidence_freshness":
        return [
            f"python3 scripts/report_release_evidence_freshness.py --out {DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT} --out-md {DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT.with_suffix('.md')} --fail-blocked",
            f"python3 scripts/report_pm_release_gate.py --out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "github_sync":
        return [
            "python3 scripts/check_github_development_sync_preflight.py --fetch --json",
            f"python3 scripts/report_pm_release_gate.py --out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}",
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
        ]
    if namespace == "customer_shadow":
        return [
            f"python3 scripts/check_customer_shadow_evidence_status.py --out {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS} --json --fail-blocked",
            f"python3 scripts/build_customer_shadow_evidence_intake_packet.py --out {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET} --out-md {DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET.with_suffix('.md')}",
            f"python3 scripts/report_pm_release_gate.py --out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}",
        ]
    return [
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
    ]


def _owner_input_required(*, namespace: str, code: str) -> bool:
    return bool(
        namespace == "structural_scope_cleanup"
        or (namespace == "basic_ci" and "consecutive_pass" in code)
        or (namespace == "security" and "license" in code)
        or _is_ux_human_new_user_blocker(namespace=namespace, code=code)
        or namespace == "github_sync"
        or namespace == "customer_shadow"
        or (
            not namespace
            and code
            in {
                "independent_vv_missing",
                "family_validation_manual_signoff_missing",
                "customer_audit_failure_bundle_sla_missing",
            }
        )
    )


def _evidence_artifacts(row: dict[str, Any]) -> dict[str, str]:
    artifacts = {
        str(key): str(value)
        for key, value in _as_dict(row.get("artifacts")).items()
        if str(value)
    }
    artifacts["pm_release_gate_report"] = str(DEFAULT_PM_REPORT)
    return artifacts


def _augment_evidence_artifacts(*, namespace: str, code: str, artifacts: dict[str, str]) -> dict[str, str]:
    augmented = dict(artifacts)
    if namespace == "structural_scope_cleanup":
        augmented["structural_scope_owner_decision_application_plan"] = str(
            DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN
        )
        augmented["structural_scope_owner_review_packet"] = str(
            DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET
        )
        augmented["structural_scope_contamination_audit"] = str(
            DEFAULT_STRUCTURAL_SCOPE_CONTAMINATION_AUDIT
        )
        augmented["structural_scope_quarantine_manifest"] = str(
            DEFAULT_STRUCTURAL_SCOPE_QUARANTINE_MANIFEST
        )
        augmented["structural_scope_owner_decisions"] = str(
            DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISIONS
        )
    if namespace == "fresh_full_validation":
        augmented["fresh_full_validation_lane_status"] = str(DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS)
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        augmented["ga_enterprise_readiness_report"] = str(DEFAULT_GA_ENTERPRISE_READINESS_REPORT)
        augmented["ga_enterprise_signoff_intake_packet"] = str(DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET)
    if namespace == "basic_ci" and "consecutive_pass" in code:
        augmented["ci_streak_intake_packet"] = str(DEFAULT_CI_STREAK_INTAKE_PACKET)
    if namespace == "security" and "license" in code:
        augmented["license_status_intake_packet"] = str(DEFAULT_LICENSE_STATUS_INTAKE_PACKET)
    if namespace == "security" and "frontend_dependency" in code:
        augmented["frontend_dependency_audit_report"] = str(DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT)
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        augmented["ux_new_user_observation_report"] = str(DEFAULT_UX_NEW_USER_OBSERVATION_REPORT)
        augmented["ux_new_user_observation_intake_packet"] = str(DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET)
    if namespace == "evidence_freshness":
        augmented["release_evidence_freshness_report"] = str(DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT)
    if namespace == "customer_shadow":
        augmented["customer_shadow_evidence_status"] = str(DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS)
        augmented["customer_shadow_evidence_intake_packet"] = str(DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET)
    return augmented


def _expected_intake_artifact(*, namespace: str, code: str) -> str:
    if namespace == "structural_scope_cleanup":
        return "structural_scope_owner_decision_application_plan"
    if namespace == "basic_ci" and "consecutive_pass" in code:
        return "ci_streak_intake_packet"
    if namespace == "security" and "license" in code:
        return "license_status_intake_packet"
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return "ux_new_user_observation_intake_packet"
    if namespace == "customer_shadow":
        return "customer_shadow_evidence_intake_packet"
    return ""


def _path_within_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    except Exception:
        return False
    return True


def _resolve_artifact_json_path(*, pm_report: Path, artifact_ref: str) -> Path | None:
    if not artifact_ref:
        return None
    artifact = Path(artifact_ref)
    candidates: list[Path] = []
    if artifact.is_absolute():
        candidates.append(artifact)
    else:
        candidates.extend(
            [
                pm_report.parent / artifact,
                pm_report.parent / artifact.name,
                artifact,
            ]
        )
        if _path_within_root(pm_report):
            candidates.append(ROOT / artifact)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _source_intake_packet(
    *,
    pm_report: Path,
    expected_intake_artifact: str,
    evidence_artifacts: dict[str, str],
) -> tuple[dict[str, Any], str]:
    if not expected_intake_artifact:
        return {}, ""
    artifact_ref = str(evidence_artifacts.get(expected_intake_artifact, "") or "")
    resolved = _resolve_artifact_json_path(pm_report=pm_report, artifact_ref=artifact_ref)
    if not resolved:
        return {}, artifact_ref
    return _load_json(resolved), _path_key(resolved)


def _evidence_status(*, namespace: str, code: str, row: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(row.get("summary"))
    if namespace == "structural_scope_cleanup":
        owner_pending = _as_int(summary.get("owner_decision_pending_count"), 0)
        owner_total = _as_int(summary.get("owner_decision_total_count"), owner_pending)
        release_surface_pending = _as_int(
            summary.get("release_surface_owner_decision_required_count"), 0
        )
        cleanup_pending = _as_int(summary.get("post_decision_cleanup_pending_count"), 0)
        retain_exceptions = _as_int(summary.get("retain_quarantined_exception_count"), 0)
        if release_surface_pending:
            state = "release_surface_owner_decisions_pending"
        elif owner_pending:
            state = "owner_decisions_pending"
        elif retain_exceptions:
            state = "retain_quarantined_exception_review_required"
        elif cleanup_pending:
            state = "manual_cleanup_application_pending"
        elif bool(summary.get("evidence_closure_pass", False)):
            state = "ready_for_pm_regeneration"
        else:
            state = "structural_scope_cleanup_blocked"
        return {
            "state": state,
            "status": str(summary.get("status", "") or ""),
            "owner_decision_recorded_count": _as_int(
                summary.get("owner_decision_recorded_count"), 0
            ),
            "owner_decision_pending_count": owner_pending,
            "owner_decision_total_count": owner_total,
            "release_surface_owner_decision_required_count": release_surface_pending,
            "release_surface_owner_decision_required_paths": _as_list(
                summary.get("release_surface_owner_decision_required_paths")
            ),
            "release_surface_first_batch_ready": bool(
                summary.get("release_surface_first_batch_ready", False)
            ),
            "release_surface_first_batch_application_ready": bool(
                summary.get("release_surface_first_batch_application_ready", False)
            ),
            "release_surface_first_batch_blockers": _as_list(
                summary.get("release_surface_first_batch_blockers")
            ),
            "release_surface_first_batch_application_blockers": _as_list(
                summary.get("release_surface_first_batch_application_blockers")
            ),
            "release_surface_first_batch_cleanup_application_preflight": _as_dict(
                summary.get("release_surface_first_batch_cleanup_application_preflight")
            ),
            "release_surface_first_batch_template_paths": _as_dict(
                summary.get("release_surface_first_batch_template_paths")
            ),
            "post_decision_cleanup_pending_count": cleanup_pending,
            "retain_quarantined_exception_count": retain_exceptions,
            "owner_decision_validation_pass": bool(
                summary.get("owner_decision_validation_pass", False)
            ),
            "owner_decision_validation_blockers": _as_list(
                summary.get("owner_decision_validation_blockers")
            ),
            "pending_owner_decision_family_counts": _as_dict(
                summary.get("pending_owner_decision_family_counts")
            ),
            "pending_owner_decision_path_area_counts": _as_dict(
                summary.get("pending_owner_decision_path_area_counts")
            ),
            "next_owner_review_batch": _as_dict(summary.get("next_owner_review_batch")),
            "source_policy": "owner_delete_or_extract_decisions_required_before_release_surface_cleanup",
        }
    if namespace == "fresh_full_validation":
        lane_id = code.split("::", 1)[0]
        present = bool(row.get("fresh_validation_receipt_present", False))
        fresh = bool(row.get("fresh_validation_receipt_fresh", False))
        lane_matches = bool(row.get("fresh_validation_receipt_lane_matches", False))
        runner_matches = bool(row.get("fresh_validation_receipt_runner_matches", False))
        contract_pass = bool(row.get("fresh_validation_receipt_contract_pass", False))
        validator_blockers = list(row.get("fresh_validation_receipt_blockers", []))
        if not present:
            state = "fresh_validation_receipt_missing"
        elif not fresh:
            state = "fresh_validation_receipt_reuses_evidence"
        elif not lane_matches:
            state = "fresh_validation_receipt_lane_mismatch"
        elif not runner_matches:
            state = "fresh_validation_receipt_runner_mismatch"
        elif not contract_pass:
            state = "fresh_validation_receipt_invalid"
        else:
            state = "ready_for_pm_regeneration"
        return {
            "state": state,
            "lane_id": lane_id,
            "runner": str(row.get("runner", "") or ""),
            "fresh_validation_receipt": str(row.get("fresh_validation_receipt", "") or ""),
            "fresh_validation_receipt_present": present,
            "fresh_validation_receipt_fresh": fresh,
            "fresh_validation_receipt_lane_matches": lane_matches,
            "fresh_validation_receipt_runner_matches": runner_matches,
            "fresh_validation_receipt_contract_pass": contract_pass,
            "fresh_validation_receipt_blockers": validator_blockers,
            "receipt_validator": "implementation/phase1/validate_fresh_validation_receipt.py",
            "source_policy": "fresh_lane_execution_required",
        }
    if namespace == "customer_shadow":
        completed = _as_int(summary.get("completed_shadow_case_count"), 0)
        minimum = _as_int(summary.get("min_completed_shadow_cases"), 3)
        return {
            "state": "completed_shadow_case_count_below_minimum"
            if completed < minimum
            else "ready_for_pm_regeneration",
            "completed_shadow_case_count": completed,
            "min_completed_shadow_cases": minimum,
            "target_completed_shadow_cases": _as_int(summary.get("target_completed_shadow_cases"), 5),
            "evidence_file_count": _as_int(summary.get("evidence_file_count"), 0),
            "valid_evidence_file_count": _as_int(summary.get("valid_evidence_file_count"), 0),
            "source_policy": "real_customer_retained_metadata_required",
        }
    if not namespace and code in {
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    }:
        return {
            "state": "missing_external_ga_enterprise_signoff_evidence",
            "ga_enterprise_blocker": code,
            "source_policy": "external_or_owner_signed_ga_evidence_required",
        }
    if namespace == "basic_ci":
        lane = "nightly" if code.startswith("nightly_ci") else "pr"
        required = int(summary.get("required_consecutive_pass_count", 30) or 30)
        release_count = int(summary.get(f"{lane}_pass_streak_count", 0) or 0)
        local_count = int(summary.get(f"{lane}_local_pass_streak_count", 0) or 0)
        github_count = int(summary.get(f"{lane}_github_actions_pass_streak_count", 0) or 0)
        missing = int(summary.get(f"{lane}_missing_consecutive_pass_count", max(0, required - release_count)) or 0)
        pull_request_source_present = summary.get("pr_pull_request_run_source_present")
        job_start_blocker_count = int(summary.get(f"{lane}_github_actions_job_start_blocker_count", 0) or 0)
        streak_source = str(summary.get(f"{lane}_streak_source", "") or "")
        runner_precondition_evaluated = bool(
            summary.get("ci_runner_precondition_evaluated", False)
        )
        runner_precondition_pass = bool(
            summary.get("ci_runner_precondition_pass", True)
        )
        state = "ready_for_pm_regeneration" if release_count >= required else "missing_tracked_ci_streak_evidence"
        if lane == "pr" and pull_request_source_present is False and release_count < required:
            state = "no_pull_request_run_source"
        if job_start_blocker_count > 0 or streak_source == "github_actions_job_start_blocked":
            state = "github_actions_job_start_blocked"
        if runner_precondition_evaluated and not runner_precondition_pass:
            state = "self_hosted_runner_offline"
        return {
            "state": state,
            "lane": lane,
            "streak_source": streak_source,
            "required_consecutive_pass_count": required,
            "release_consecutive_pass_count": release_count,
            "github_actions_consecutive_pass_count": github_count,
            "github_actions_job_start_blocker_count": job_start_blocker_count,
            "local_consecutive_pass_count": local_count,
            "missing_consecutive_pass_count": missing,
            "pull_request_run_source_present": pull_request_source_present,
            "runner_precondition_evaluated": runner_precondition_evaluated,
            "runner_precondition_pass": runner_precondition_pass,
            "runner_status": str(summary.get("ci_runner_status", "") or ""),
            "runner_required_labels": [
                str(item)
                for item in _as_list(summary.get("ci_runner_required_labels"))
                if str(item)
            ],
            "runner_matching_runner_count": _as_int(
                summary.get("ci_runner_matching_runner_count"), 0
            ),
            "runner_online_matching_runner_count": _as_int(
                summary.get("ci_runner_online_matching_runner_count"), 0
            ),
            "runner_ready_runner_count": _as_int(
                summary.get("ci_runner_ready_runner_count"), 0
            ),
            "source_policy": "github_actions_required",
        }
    if namespace == "security" and "license" in code:
        blockers = [str(item) for item in _as_list(summary.get("license_status_closure_blockers"))]
        status = str(summary.get("license_status", "") or "missing")
        return {
            "state": status,
            "license_status": status,
            "closure_blocker_count": len(blockers),
            "closure_blockers": blockers,
            "template_path": str(summary.get("license_status_template_path", "")),
        }
    if namespace == "security" and "frontend_dependency" in code:
        high_or_critical = int(summary.get("frontend_dependency_high_or_critical_vulnerability_count", 0) or 0)
        total = int(summary.get("frontend_dependency_vulnerability_total", high_or_critical) or 0)
        return {
            "state": "dependency_vulnerabilities_present" if high_or_critical else "ready_for_pm_regeneration",
            "vulnerability_total": total,
            "high_or_critical_vulnerability_count": high_or_critical,
        }
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        checks = _as_dict(row.get("checks"))
        human_pass = bool(checks.get("human_new_user_observation_pass", False))
        human_30min_evidence_present = bool(checks.get("human_new_user_sample_30min_evidence_present", False))
        human_30min_pass = bool(checks.get("human_new_user_sample_30min_pass", False))
        completion_minutes = summary.get("human_sample_completion_minutes")
        state = "ready_for_pm_regeneration"
        if "30min_sample_evidence" in code and not human_30min_evidence_present:
            state = "missing_human_new_user_completion_evidence"
        elif "30min" in code and completion_minutes is None:
            state = "missing_human_new_user_completion_evidence"
        elif "30min" in code and not human_30min_pass:
            state = "human_new_user_completion_gt_30min"
        elif not human_pass:
            state = "missing_human_new_user_observation"
        elif completion_minutes is None:
            state = "missing_human_new_user_completion_evidence"
        elif not human_30min_pass:
            state = "human_new_user_completion_gt_30min"
        return {
            "state": state,
            "human_new_user_observation_pass": human_pass,
            "human_new_user_sample_30min_evidence_present": human_30min_evidence_present,
            "human_new_user_sample_30min_pass": human_30min_pass,
            "human_sample_completion_minutes": completion_minutes,
            "automated_sample_completion_minutes": summary.get("automated_sample_completion_minutes"),
            "human_observation_reason_code": str(summary.get("human_observation_reason_code", "")),
            "source_policy": "human_new_user_observation_required",
        }
    if namespace == "evidence_freshness":
        summary = _as_dict(row.get("summary"))
        checks = _as_dict(row.get("checks"))
        return {
            "state": "release_evidence_metadata_missing",
            "artifact_count": summary.get("artifact_count"),
            "pass_count": summary.get("pass_count"),
            "blocker_count": summary.get("blocker_count"),
            "source_commit_rows_match": checks.get("source_commit_rows_match"),
            "engine_version_rows_present": checks.get("engine_version_rows_present"),
            "input_checksum_rows_present": checks.get("input_checksum_rows_present"),
            "reuse_marker_rows_present": checks.get("reuse_marker_rows_present"),
            "dependency_mtime_rows_pass": checks.get("dependency_mtime_rows_pass"),
        }
    if namespace == "github_sync":
        summary = _as_dict(row.get("summary"))
        checks = _as_dict(row.get("checks"))
        return {
            "state": str(summary.get("status", "") or "approval_required"),
            "reason_code": str(summary.get("reason_code", "") or ""),
            "preflight_source_state_fresh": checks.get("github_sync_preflight_source_state_fresh"),
            "preflight_source_state_kind": str(summary.get("preflight_source_state_kind", "") or ""),
            "preflight_local_head_sha": str(summary.get("preflight_local_head_sha", "") or ""),
            "current_head_sha": str(summary.get("current_head_sha", "") or ""),
            "changed_paths_since_preflight_head": _as_list(
                summary.get("changed_paths_since_preflight_head")
            ),
            "remote_sync_needed": bool(summary.get("remote_sync_needed", False)),
            "remote_mutation_approval_pending": bool(
                summary.get("remote_mutation_approval_pending", False)
            ),
            "remote_mutation_approved": bool(summary.get("remote_mutation_approved", False)),
            "remote_feature_ref": str(summary.get("remote_feature_ref", "") or ""),
            "remote_main_ref": str(summary.get("remote_main_ref", "") or ""),
            "feature_synced_to_head": bool(summary.get("feature_synced_to_head", False)),
            "main_synced_to_head": bool(summary.get("main_synced_to_head", False)),
            "feature_ahead_count": summary.get("feature_ahead_count"),
            "main_ahead_count": summary.get("main_ahead_count"),
            "pending_remote_update_count": summary.get("pending_remote_update_count"),
            "pending_remote_update_targets": _as_list(
                summary.get("pending_remote_update_targets")
            ),
            "pending_remote_update_actions": _as_list(
                summary.get("pending_remote_update_actions")
            ),
            "feature_fast_forward_possible": checks.get("github_sync_feature_fast_forward_possible"),
            "main_fast_forward_possible": checks.get("github_sync_main_fast_forward_possible"),
            "remote_safety_ok": checks.get("github_sync_remote_safety_ok"),
            "source_policy": "explicit_r4_approval_required_before_remote_mutation",
            "approval_phrase": GITHUB_SYNC_APPROVAL_PHRASE,
        }
    return {"state": "open_release_evidence_blocker"}


def _handoff_payload(
    *,
    owner: str,
    owner_action: str,
    owner_input_required: bool,
    acceptance_criteria: list[str],
    reproduction_commands: list[str],
    verification_commands: list[str],
    evidence_artifacts: dict[str, str],
    expected_intake_artifact: str,
) -> dict[str, Any]:
    checks = {
        "owner_assigned": bool(owner),
        "owner_action_present": bool(owner_action),
        "acceptance_criteria_present": bool(acceptance_criteria),
        "reproduction_commands_present": bool(reproduction_commands),
        "verification_commands_present": bool(verification_commands),
        "evidence_artifacts_present": bool(evidence_artifacts),
        "expected_intake_artifact_present": (
            not expected_intake_artifact or bool(evidence_artifacts.get(expected_intake_artifact))
        ),
    }
    handoff_ready = all(checks.values())
    if handoff_ready and owner_input_required:
        state = "external_owner_input_ready"
    elif handoff_ready:
        state = "local_remediation_ready"
    else:
        state = "handoff_incomplete"
    return {
        "handoff_ready": handoff_ready,
        "handoff_state": state,
        "expected_intake_artifact": expected_intake_artifact,
        "checks": checks,
    }


def build_register(
    pm_report: Path = DEFAULT_PM_REPORT,
    structural_scope_plan: Path | None = None,
) -> dict[str, Any]:
    report = _load_json(pm_report)
    structural_scope_plan_payload = (
        _load_json(structural_scope_plan) if structural_scope_plan is not None else {}
    )
    structural_scope_source_row = _structural_scope_source_row(
        plan=structural_scope_plan_payload,
        plan_path=structural_scope_plan,
    ) if structural_scope_plan is not None and structural_scope_plan_payload else {}
    structural_scope_blockers = (
        [STRUCTURAL_SCOPE_CLEANUP_BLOCKER_ID]
        if _structural_scope_cleanup_open(structural_scope_plan_payload)
        else []
    )
    release_decision = _as_dict(report.get("release_decision"))
    release_decision_operator_actions = [
        row for row in _as_list(release_decision.get("operator_actions")) if isinstance(row, dict)
    ]
    release_area_rows = _indexed_rows(_as_list(report.get("release_area_matrix")), "area")
    milestone_rows = _indexed_rows(_as_list(report.get("milestones")), "milestone")
    release_tiers = _as_dict(report.get("release_tiers"))
    customer_shadow_summary = _as_dict(release_tiers.get("customer_shadow_summary"))
    customer_shadow_source_row = {
        "title": "Customer Shadow Evidence",
        "summary": customer_shadow_summary,
        "claim_boundary": (
            "Customer shadow release-tier blockers require real completed-project derived metadata. "
            "Templates, synthetic cases, and raw customer data committed to Git do not close the blocker."
        ),
        "artifacts": {
            "customer_shadow_evidence_status": str(
                release_tiers.get("customer_shadow_evidence_status") or DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS
            ),
            "customer_shadow_evidence_intake_packet": str(DEFAULT_CUSTOMER_SHADOW_EVIDENCE_INTAKE_PACKET),
        },
    }
    fresh_status_path = Path(
        str(release_tiers.get("fresh_full_validation_lane_status", "") or DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS)
    )
    fresh_lane_rows = _indexed_rows(_as_list(_load_json(fresh_status_path).get("rows")), "lane_id")
    full_blockers = [str(row) for row in _as_list(report.get("full_release_blockers"))]
    if not full_blockers:
        full_blockers = [
            *[str(row) for row in _as_list(report.get("blockers"))],
            *[str(row) for row in _as_list(report.get("release_area_blockers"))],
        ]
    ga_enterprise_blockers = [str(row) for row in _as_list(release_tiers.get("ga_enterprise_blockers"))]
    all_blockers = list(
        dict.fromkeys([*structural_scope_blockers, *full_blockers, *ga_enterprise_blockers])
    )

    rows: list[dict[str, Any]] = []
    for blocker_id in all_blockers:
        namespace, code = _split_blocker(blocker_id)
        if namespace == "structural_scope_cleanup":
            scope = "release_surface_scope"
            source_row = structural_scope_source_row
        elif namespace in release_area_rows:
            scope = "release_area"
            source_row = release_area_rows[namespace]
        elif namespace in milestone_rows:
            scope = "milestone"
            source_row = milestone_rows[namespace]
        elif blocker_id in ga_enterprise_blockers:
            scope = "ga_enterprise"
            if namespace == "fresh_full_validation":
                lane_id = code.split("::", 1)[0]
                source_row = fresh_lane_rows.get(lane_id, {})
            elif namespace == "customer_shadow":
                source_row = customer_shadow_source_row
            else:
                source_row = {}
        else:
            scope = "unknown"
            source_row = {}
        title = str(source_row.get("title", namespace) or namespace)
        owner = _owner(namespace=namespace, code=code)
        owner_action = _owner_action(namespace=namespace, code=code, row=source_row)
        owner_input_required = _owner_input_required(namespace=namespace, code=code)
        acceptance_criteria = _acceptance_criteria(namespace=namespace, code=code, row=source_row)
        reproduction_commands = _reproduction_commands(namespace=namespace, code=code)
        verification_commands = _verification_commands(namespace=namespace, code=code)
        evidence_artifacts = _augment_evidence_artifacts(
            namespace=namespace,
            code=code,
            artifacts=_evidence_artifacts(source_row),
        )
        expected_intake_artifact = _expected_intake_artifact(namespace=namespace, code=code)
        source_intake_packet, source_intake_path = _source_intake_packet(
            pm_report=pm_report,
            expected_intake_artifact=expected_intake_artifact,
            evidence_artifacts=evidence_artifacts,
        )
        source_intake_blocker_ids = _deduped(
            [str(item) for item in _as_list(source_intake_packet.get("blocker_ids"))]
        )
        source_intake_release_area_blocker_ids = _deduped(
            [str(item) for item in _as_list(source_intake_packet.get("release_area_blocker_ids"))]
        )
        source_intake_evidence_artifacts = _deduped(
            [str(item) for item in _as_list(source_intake_packet.get("evidence_intake_artifacts"))]
        )
        row_blocker_ids = _deduped(
            [
                blocker_id,
                *source_intake_release_area_blocker_ids,
                *source_intake_blocker_ids,
            ]
        )
        handoff = _handoff_payload(
            owner=owner,
            owner_action=owner_action,
            owner_input_required=owner_input_required,
            acceptance_criteria=acceptance_criteria,
            reproduction_commands=reproduction_commands,
            verification_commands=verification_commands,
            evidence_artifacts=evidence_artifacts,
            expected_intake_artifact=expected_intake_artifact,
        )
        row = {
            "blocker_id": blocker_id,
            "blocker_code": code,
            "namespace": namespace,
            "scope": scope,
            "title": title,
            "status": "open",
            "owner": owner,
            "owner_input_required": owner_input_required,
            "external_input_required": owner_input_required,
            "resolution_type": _resolution_type(namespace=namespace, code=code),
            "blocker_ids": row_blocker_ids,
            "source_intake_artifact": expected_intake_artifact,
            "source_intake_path": source_intake_path,
            "source_intake_status": str(source_intake_packet.get("status", "")),
            "source_intake_contract_pass": bool(source_intake_packet.get("contract_pass") is True),
            "source_intake_blocker_ids": source_intake_blocker_ids,
            "source_intake_blocker_id_count": len(source_intake_blocker_ids),
            "source_intake_release_area_blocker_ids": source_intake_release_area_blocker_ids,
            "source_intake_evidence_intake_artifacts": source_intake_evidence_artifacts,
            "source_intake_evidence_intake_artifact_count": len(source_intake_evidence_artifacts),
            "owner_action": owner_action,
            "next_action": owner_action,
            "claim_boundary": _claim_boundary(namespace=namespace, code=code, row=source_row),
            "acceptance_criteria": acceptance_criteria,
            "reproduction_commands": reproduction_commands,
            "verification_commands": verification_commands,
            "evidence_artifacts": evidence_artifacts,
            "evidence_status": _evidence_status(namespace=namespace, code=code, row=source_row),
            "evidence_snapshot": _as_dict(source_row.get("summary")),
            "handoff": handoff,
            "handoff_ready": bool(handoff["handoff_ready"]),
            "handoff_state": str(handoff["handoff_state"]),
        }
        rows.append(row)

    release_area_blockers = [str(row) for row in _as_list(report.get("release_area_blockers"))]
    milestone_blockers = [str(row) for row in _as_list(report.get("blockers"))]
    release_area_green_count, release_area_total_count = _release_area_green_total(report)
    canonical_release_area_evidence = {
        "release_area_green_count": release_area_green_count,
        "release_area_total_count": release_area_total_count,
        "release_area_summary": (
            f"{release_area_green_count}/{release_area_total_count}"
            if release_area_total_count
            else ""
        ),
        "release_area_blocker_count": len(release_area_blockers),
        "release_area_blocker_ids": release_area_blockers,
        "claim_boundary": (
            "Release-area blockers are sourced from "
            "pm_release_gate_report.json.release_area_blockers and are distinct "
            "from release-tier/open blocker lists used for owner handoff."
        ),
    }
    contract_pass = not rows
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        **_source_tracking_metadata(
            [
                Path("scripts/build_pm_release_blocker_action_register.py"),
                pm_report,
                DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT,
                DEFAULT_CI_STREAK_INTAKE_PACKET,
                DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
                DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET,
                *([structural_scope_plan] if structural_scope_plan is not None else []),
            ]
        ),
        "pm_release_gate_report": str(pm_report),
        "pm_summary_line": str(report.get("summary_line", "")),
        "canonical_release_area_evidence": canonical_release_area_evidence,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_RELEASE_BLOCKERS_OPEN",
        "summary": {
            "open_blocker_count": len(rows),
            "release_area_blocker_count": len(release_area_blockers),
            "release_area_green_count": release_area_green_count,
            "release_area_total_count": release_area_total_count,
            "milestone_blocker_count": len(milestone_blockers),
            "ga_enterprise_blocker_count": len(ga_enterprise_blockers),
            "structural_scope_cleanup_blocker_count": len(structural_scope_blockers),
            "release_decision_operator_action_count": len(release_decision_operator_actions),
            "owner_input_required_count": sum(1 for row in rows if row["owner_input_required"]),
            "full_release_gate_ready": bool(report.get("full_release_gate_ready", False)),
            "release_area_gate_ready": bool(report.get("release_area_gate_ready", False)),
            "limited_commercial_milestone_ready": bool(
                report.get("limited_commercial_milestone_ready", False)
            ),
            "limited_commercial_release_ready": bool(
                report.get("limited_commercial_release_ready", report.get("limited_commercial_ready", False))
            ),
            "limited_commercial_ready": bool(report.get("limited_commercial_ready", False)),
            "paid_pilot_candidate": bool(report.get("paid_pilot_candidate", False)),
            "external_input_required_count": sum(1 for row in rows if row["external_input_required"]),
            "handoff_ready_count": sum(1 for row in rows if row["handoff_ready"]),
            "handoff_not_ready_count": sum(1 for row in rows if not row["handoff_ready"]),
            "external_owner_input_ready_count": sum(
                1 for row in rows if row["handoff_state"] == "external_owner_input_ready"
            ),
            "local_remediation_ready_count": sum(
                1 for row in rows if row["handoff_state"] == "local_remediation_ready"
            ),
            "all_open_blockers_have_handoff": all(row["handoff_ready"] for row in rows),
        },
        "rows": rows,
        "release_decision_operator_actions": release_decision_operator_actions,
        "next_actions": [row["next_action"] for row in rows],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Blocker Action Register",
        "",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `open_blocker_count`: `{payload['summary']['open_blocker_count']}`",
        f"- `release_area_summary`: `{payload['canonical_release_area_evidence']['release_area_summary']}`",
        f"- `release_area_blocker_count`: `{payload['canonical_release_area_evidence']['release_area_blocker_count']}`",
        "",
        "| Blocker | Scope | Owner | Evidence Status | Next Action | Acceptance |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        acceptance = "<br>".join(str(item) for item in row.get("acceptance_criteria", []))
        evidence_status = _as_dict(row.get("evidence_status"))
        lines.append(
            f"| `{row['blocker_id']}` | {row['scope']} | `{row['owner']}` | "
            f"`{evidence_status.get('state', 'open')}` / `{row.get('handoff_state', 'handoff_incomplete')}` | "
            f"{row['next_action']} | {acceptance} |"
        )
    if not payload["rows"]:
        lines.append("| none | release | `release_owner` | `closed` | No open PM release blockers. | PM release gate is ready. |")
    intake_rows = [
        row
        for row in payload["rows"]
        if row.get("source_intake_blocker_ids") or row.get("source_intake_evidence_intake_artifacts")
    ]
    if intake_rows:
        lines.extend(["", "## Source Intake Links", ""])
        for row in intake_rows:
            lines.append(f"### `{row['blocker_id']}`")
            if row.get("source_intake_path"):
                lines.append(f"- `source_intake_path`: `{row['source_intake_path']}`")
            for blocker_id in row.get("source_intake_blocker_ids", []):
                lines.append(f"- `blocker_id`: `{blocker_id}`")
            for artifact in row.get("source_intake_evidence_intake_artifacts", []):
                lines.append(f"- `evidence_artifact`: `{artifact}`")
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument(
        "--structural-scope-plan",
        type=Path,
        default=DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN,
        help=(
            "Optional structural scope owner-decision application plan. When present "
            "and not closed, the register surfaces it as the first release-surface "
            "scope cleanup action."
        ),
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_register(
        pm_report=args.pm_report,
        structural_scope_plan=args.structural_scope_plan,
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
