#!/usr/bin/env python3
"""Build an actionable register for open PM release blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-blocker-action-register.v1"
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
DEFAULT_RELEASE_EVIDENCE_FRESHNESS_REPORT = Path(
    "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json"
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


def _is_ux_human_new_user_blocker(*, namespace: str, code: str) -> bool:
    return namespace == "ux" and "human_new_user" in code


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
    direct = str(summary.get("owner_action", "") or row.get("owner_action", "") or "")
    if direct:
        return direct
    title = str(row.get("title", namespace or "PM release gate") or namespace or "PM release gate")
    return f"Resolve `{code}` in {title} evidence, regenerate PM release reports, and attach the updated evidence."


def _owner(*, namespace: str, code: str) -> str:
    if namespace == "fresh_full_validation":
        return "validation_lane_owner"
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
    return "release_evidence_remediation_required"


def _claim_boundary(*, namespace: str, code: str, row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("summary"))
    if namespace == "fresh_full_validation":
        return (
            "Fresh validation lane blockers require new lane execution receipts. Existing hydrated, "
            "publication, local-only, or reused evidence must not be counted as GA/Enterprise fresh validation."
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
    if namespace == "fresh_full_validation":
        lane_id = code.split("::", 1)[0]
        return [
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_present == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_fresh == true`",
            f"`fresh_full_validation_lane_status.json.rows[{lane_id}].fresh_validation_receipt_contract_pass == true`",
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
    return [
        f"`{namespace}::{code}` absent from `full_release_blockers`",
        "`full_release_gate_ready == true` after PM report regeneration",
    ]


def _reproduction_commands(*, namespace: str, code: str) -> list[str]:
    pm_report_command = (
        "python3 scripts/report_pm_release_gate.py "
        f"--out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}"
    )
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
    return [
        pm_report_command,
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
    ]


def _verification_commands(*, namespace: str, code: str) -> list[str]:
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
    return [
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --fail-blocked",
    ]


def _owner_input_required(*, namespace: str, code: str) -> bool:
    return bool(
        (namespace == "basic_ci" and "consecutive_pass" in code)
        or (namespace == "security" and "license" in code)
        or _is_ux_human_new_user_blocker(namespace=namespace, code=code)
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
    return augmented


def _expected_intake_artifact(*, namespace: str, code: str) -> str:
    if namespace == "basic_ci" and "consecutive_pass" in code:
        return "ci_streak_intake_packet"
    if namespace == "security" and "license" in code:
        return "license_status_intake_packet"
    if _is_ux_human_new_user_blocker(namespace=namespace, code=code):
        return "ux_new_user_observation_intake_packet"
    return ""


def _evidence_status(*, namespace: str, code: str, row: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(row.get("summary"))
    if namespace == "fresh_full_validation":
        lane_id = code.split("::", 1)[0]
        present = bool(row.get("fresh_validation_receipt_present", False))
        fresh = bool(row.get("fresh_validation_receipt_fresh", False))
        contract_pass = bool(row.get("fresh_validation_receipt_contract_pass", False))
        if not present:
            state = "fresh_validation_receipt_missing"
        elif not fresh:
            state = "fresh_validation_receipt_reuses_evidence"
        elif not contract_pass:
            state = "fresh_validation_receipt_not_green"
        else:
            state = "ready_for_pm_regeneration"
        return {
            "state": state,
            "lane_id": lane_id,
            "runner": str(row.get("runner", "") or ""),
            "fresh_validation_receipt": str(row.get("fresh_validation_receipt", "") or ""),
            "fresh_validation_receipt_present": present,
            "fresh_validation_receipt_fresh": fresh,
            "fresh_validation_receipt_contract_pass": contract_pass,
            "source_policy": "fresh_lane_execution_required",
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
        state = "ready_for_pm_regeneration" if release_count >= required else "missing_tracked_ci_streak_evidence"
        if lane == "pr" and pull_request_source_present is False and release_count < required:
            state = "no_pull_request_run_source"
        if job_start_blocker_count > 0 or streak_source == "github_actions_job_start_blocked":
            state = "github_actions_job_start_blocked"
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


def build_register(pm_report: Path = DEFAULT_PM_REPORT) -> dict[str, Any]:
    report = _load_json(pm_report)
    release_area_rows = _indexed_rows(_as_list(report.get("release_area_matrix")), "area")
    milestone_rows = _indexed_rows(_as_list(report.get("milestones")), "milestone")
    release_tiers = _as_dict(report.get("release_tiers"))
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
    all_blockers = list(dict.fromkeys([*full_blockers, *ga_enterprise_blockers]))

    rows: list[dict[str, Any]] = []
    for blocker_id in all_blockers:
        namespace, code = _split_blocker(blocker_id)
        if namespace in release_area_rows:
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
    contract_pass = not rows
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "pm_release_gate_report": str(pm_report),
        "pm_summary_line": str(report.get("summary_line", "")),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_RELEASE_BLOCKERS_OPEN",
        "summary": {
            "open_blocker_count": len(rows),
            "release_area_blocker_count": len(release_area_blockers),
            "milestone_blocker_count": len(milestone_blockers),
            "ga_enterprise_blocker_count": len(ga_enterprise_blockers),
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
        "next_actions": [row["next_action"] for row in rows],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Blocker Action Register",
        "",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `open_blocker_count`: `{payload['summary']['open_blocker_count']}`",
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
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_register(pm_report=args.pm_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
