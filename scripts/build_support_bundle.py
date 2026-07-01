#!/usr/bin/env python3
"""Build a redacted support bundle manifest for product ops handoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import zipfile


SCHEMA_VERSION = "support-bundle-manifest.v1"
DEFAULT_BUNDLE_DIR = Path("implementation/phase1/release/support_bundle")
DEFAULT_ARCHIVE_OUT = Path("implementation/phase1/release/support_bundle_export.zip")
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_P0_STATUS = Path("implementation/phase1/release/publication_evidence/current/p0-status.json")
DEFAULT_P1_STATUS = Path("implementation/phase1/release/publication_evidence/current/p1-readiness-status.json")
DEFAULT_P1_STRICT_PREFLIGHT = Path("implementation/phase1/commercialization_status/p1_evidence_sidecar_preflight.json")
DEFAULT_PROJECT_OPS_SNAPSHOT = Path("implementation/phase1/release/project_ops_service_snapshot.json")
DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL = Path("implementation/phase1/project_ops_deployment_drill_manifest.json")
DEFAULT_RUNTIME_PROBE = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_RUNTIME_PACKAGING_MANIFEST = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST = Path(
    "implementation/phase1/structure_viewer_performance_budget_manifest.json"
)
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path(
    "implementation/phase1/structure_viewer_visual_regression_baseline.json"
)
DEFAULT_WORKSTATION_HARDWARE_PROFILE = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_WORKSTATION_SERVICE_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST = Path(
    "implementation/phase1/workstation_delivery_package_manifest.json"
)
DEFAULT_WORKSTATION_DELIVERY_READINESS = Path("implementation/phase1/workstation_delivery_readiness.json")
DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE = Path("implementation/phase1/workstation_delivery_viewer_smoke.json")
DEFAULT_CLIENT_INPUT_VALIDATION_REPORT = Path("implementation/phase1/client_input_validation_report.json")
DEFAULT_WORKSTATION_JOB_RECORD = Path("implementation/phase1/workstation_job_record.json")
DEFAULT_WORKSTATION_JOB_RETENTION_POLICY = Path("implementation/phase1/workstation_job_retention_policy.json")
DEFAULT_EXTERNAL_BENCHMARK_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
)
DEFAULT_RESIDUAL_HOLDOUT_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
)
DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json"
)
DEFAULT_PM_RELEASE_GATE_COMPLETION_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json"
)
DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json"
)
DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET = Path(
    "implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json"
)
DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET = Path(
    "implementation/phase1/release_evidence/productization/structural_scope_owner_review_packet.json"
)
DEFAULT_CI_STREAK_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
)
DEFAULT_CI_STREAK_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json"
)
DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)
DEFAULT_LICENSE_STATUS_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/license_status_intake_packet.json"
)
DEFAULT_LICENSE_STATUS_CLOSURE_REPORT = Path(
    "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_LICENSE_STATUS_TEMPLATE = Path("docs/templates/license_status.template.json")
DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT = Path(
    "implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json"
)
DEFAULT_GA_ENTERPRISE_READINESS_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json"
)
DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.json"
)
DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS = Path(
    "implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json"
)
DEFAULT_INDEPENDENT_VV_ATTESTATION_TEMPLATE = Path("docs/templates/independent_vv_attestation.template.json")
DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF_TEMPLATE = Path(
    "docs/templates/family_validation_manual_signoff.template.json"
)
DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA_TEMPLATE = Path(
    "docs/templates/customer_audit_failure_bundle_sla.template.json"
)
DEFAULT_PAID_PILOT_SCOPE_GUARD_REPORT = Path(
    "implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.json"
)
DEFAULT_RELEASE_VALIDATION_MANUAL = Path("docs/release-validation-manual.md")
DEFAULT_RELEASE_LIMITATION_MANUAL = Path("docs/release-limitation-manual.md")
DEFAULT_UX_NEW_USER_OBSERVATION_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json"
)
DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json"
)
DEFAULT_UX_NEW_USER_OBSERVATION_TEMPLATE = Path("docs/templates/ux_new_user_observation.template.json")
DEFAULT_TEMPLATE_EVIDENCE_SAFETY_REPORT = Path(
    "implementation/phase1/release_evidence/productization/template_evidence_safety_report.json"
)
DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_reproduction_command_audit.json"
)
DEFAULT_AI_ORCHESTRATION_PREFLIGHT_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json"
)
DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS = Path(
    "implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json"
)
DEFAULT_GAP_CLOSURE_STATUS = Path("implementation/phase1/release_evidence/productization/gap_closure_status.json")
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PYPROJECT = Path("pyproject.toml")
PM_FAILURE_BUNDLE_REQUIRED_SECTION_LABELS = (
    "pm_release_blocker_action_register",
    "pm_release_blocker_closure_board",
    "pm_release_gate_completion_audit",
    "pm_release_gate_reviewer_handoff",
    "pm_owner_evidence_request_packet",
    "pm_release_reproduction_command_audit",
    "ci_streak_intake_packet",
    "ci_streak_manifest",
    "github_actions_ci_streak_evidence",
    "license_status_intake_packet",
    "license_status_closure_report",
    "license_status_template",
    "frontend_dependency_audit_report",
    "ux_new_user_observation_report",
    "ux_new_user_observation_intake_packet",
    "ux_new_user_observation_template",
    "template_evidence_safety_report",
    "ga_enterprise_readiness_report",
    "ga_enterprise_signoff_intake_packet",
    "fresh_full_validation_lane_status",
    "commercial_gap_ledger_status",
    "gap_closure_status",
    "independent_vv_attestation_template",
    "family_validation_manual_signoff_template",
    "customer_audit_failure_bundle_sla_template",
    "paid_pilot_scope_guard_report",
    "release_validation_manual",
    "release_limitation_manual",
    "ai_orchestration_preflight_report",
)

SENSITIVE_KEY_MARKERS = (
    "authorization",
    "secret",
    "token",
    "password",
    "private_key",
    "apikey",
    "api_key",
    "credential",
)
TEXT_REDACTIONS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(secret|token|password|api[_-]?key)\s*[:=]\s*[^,\s\"']+"),
)
REDACTED = "[REDACTED]"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _load_json_dict(path: Path | None) -> dict[str, Any]:
    loaded = _load_json(path) if path else None
    return loaded if isinstance(loaded, dict) else {}


def _load_optional_section_json(optional_sections: dict[str, str], label: str) -> dict[str, Any]:
    path_text = str(optional_sections.get(label, "") or "")
    if not path_text or path_text == "missing":
        return {}
    return _load_json_dict(Path(path_text))


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in TEXT_REDACTIONS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _safe_bundle_name(label: str, source: Path) -> str:
    suffix = source.suffix if source.suffix in {".json", ".md", ".txt", ".toml", ".jsonl"} else ".txt"
    return f"{label.replace('/', '_')}{suffix}"


def _write_redacted_copy(*, label: str, source: Path, bundle_dir: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "source_path": str(source),
        "available": source.exists(),
        "bytes": 0,
        "sha256": "",
        "redacted_bundle_path": "",
        "redacted_sha256": "",
    }
    if not source.exists():
        return row

    raw_bytes = source.read_bytes()
    row["bytes"] = len(raw_bytes)
    row["sha256"] = _sha256_bytes(raw_bytes)
    destination = bundle_dir / "redacted" / _safe_bundle_name(label, source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    json_payload = _load_json(source)
    if json_payload is not None:
        redacted_bytes = (
            json.dumps(redact_payload(json_payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    else:
        redacted_bytes = (_redact_text(source.read_text(encoding="utf-8", errors="replace")) + "\n").encode("utf-8")
    destination.write_bytes(redacted_bytes)
    row["redacted_bundle_path"] = str(destination)
    row["redacted_sha256"] = _sha256_bytes(redacted_bytes)
    return row


def _build_audit_digest(audit_log_path: Path | None, bundle_dir: Path) -> dict[str, Any]:
    lines: list[str] = []
    if audit_log_path and audit_log_path.exists():
        lines = audit_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    canonical = "\n".join(_redact_text(line) for line in lines).encode("utf-8")
    payload = {
        "schema_version": "support-bundle-audit-digest.v1",
        "generated_at": _now_utc_iso(),
        "audit_log_path": str(audit_log_path or ""),
        "audit_log_available": bool(audit_log_path and audit_log_path.exists()),
        "event_count": len([line for line in lines if line.strip()]),
        "sha256": _sha256_bytes(canonical),
    }
    destination = bundle_dir / "audit_digest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["bundle_path"] = str(destination)
    return payload


def _build_license_snapshot(license_status: Path | None, bundle_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any]
    loaded = _load_json(license_status) if license_status else None
    if isinstance(loaded, dict):
        payload = loaded
    else:
        payload = {
            "status": "not_configured",
            "tier": "",
            "expires_at": "",
            "note": "No license status file was provided for this support bundle.",
        }
    redacted = redact_payload(payload)
    destination = bundle_dir / "license_status.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(license_status or ""),
        "available": bool(license_status and license_status.exists()),
        "bundle_path": str(destination),
        "sha256": _sha256_path(destination),
    }


def _redaction_self_test() -> dict[str, Any]:
    fixture = {
        "Authorization": "Bearer eyJexample.secret.token",
        "nested": {"api_key": "sample-api-key", "safe": "kept"},
        "line": "token=sample-token",
    }
    redacted = json.dumps(redact_payload(fixture), ensure_ascii=False, sort_keys=True)
    forbidden = ("eyJexample", "sample-api-key", "sample-token")
    return {
        "pass": not any(token in redacted for token in forbidden),
        "redacted_fixture": redacted,
    }


def _build_index(*, bundle_dir: Path, artifact_rows: list[dict[str, Any]], audit_digest: dict[str, Any]) -> dict[str, Any]:
    index = {
        "schema_version": "support-bundle-index.v1",
        "generated_at": _now_utc_iso(),
        "artifact_count": len(artifact_rows),
        "available_artifact_count": sum(1 for row in artifact_rows if row.get("available")),
        "artifact_rows": artifact_rows,
        "audit_digest": audit_digest,
    }
    index_path = bundle_dir / "support_bundle_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index["bundle_index_path"] = str(index_path)
    index["bundle_index_sha256"] = _sha256_path(index_path)
    return index


def _roundtrip_self_test(index: dict[str, Any]) -> dict[str, Any]:
    index_path = Path(str(index.get("bundle_index_path", "")))
    if not index_path.exists():
        return {"pass": False, "reason": "bundle_index_missing"}
    loaded = json.loads(index_path.read_text(encoding="utf-8"))
    expected_count = int(index.get("artifact_count", 0))
    actual_count = len(loaded.get("artifact_rows", [])) if isinstance(loaded.get("artifact_rows"), list) else -1
    return {
        "pass": actual_count == expected_count,
        "reason": "PASS" if actual_count == expected_count else "artifact_count_mismatch",
        "expected_artifact_count": expected_count,
        "actual_artifact_count": actual_count,
    }


def _build_export_archive(*, bundle_dir: Path, archive_out: Path, source_paths: list[Path]) -> dict[str, Any]:
    if archive_out.exists():
        archive_out.unlink()
    archive_out.parent.mkdir(parents=True, exist_ok=True)
    files = [path for path in source_paths if path.exists() and path.is_file()]
    members = [path.relative_to(bundle_dir).as_posix() for path in files]
    try:
        with zipfile.ZipFile(archive_out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, member in sorted(zip(files, members), key=lambda item: item[1]):
                info = zipfile.ZipInfo(member)
                info.date_time = (2026, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    except Exception as exc:
        return {
            "path": str(archive_out),
            "available": False,
            "bytes": 0,
            "sha256": "",
            "member_count": 0,
            "members": [],
            "error": str(exc),
        }
    return {
        "path": str(archive_out),
        "available": archive_out.exists(),
        "bytes": archive_out.stat().st_size if archive_out.exists() else 0,
        "sha256": _sha256_path(archive_out) if archive_out.exists() else "",
        "member_count": len(members),
        "members": sorted(members),
        "error": "",
    }


def _archive_roundtrip_self_test(archive_payload: dict[str, Any]) -> dict[str, Any]:
    archive_path = Path(str(archive_payload.get("path", "")))
    if not archive_path.exists():
        return {"pass": False, "reason": "archive_missing", "member_count": 0}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            index_bytes = archive.read("support_bundle_index.json")
            index = json.loads(index_bytes.decode("utf-8"))
    except Exception as exc:
        return {"pass": False, "reason": f"archive_roundtrip_failed:{exc}", "member_count": 0}
    artifact_count = int(index.get("artifact_count", -1))
    artifact_rows = index.get("artifact_rows")
    actual_artifact_count = len(artifact_rows) if isinstance(artifact_rows, list) else -1
    required_members = {"support_bundle_index.json", "audit_digest.json", "license_status.json"}
    missing_members = sorted(required_members.difference(names))
    pass_roundtrip = bool(
        not missing_members
        and artifact_count == actual_artifact_count
        and int(archive_payload.get("member_count", 0) or 0) == len(names)
    )
    return {
        "pass": pass_roundtrip,
        "reason": "PASS" if pass_roundtrip else "archive_member_or_index_mismatch",
        "member_count": len(names),
        "artifact_count": artifact_count,
        "actual_artifact_count": actual_artifact_count,
        "missing_members": missing_members,
    }


def _rows(payload: dict[str, Any], key: str = "rows") -> list[dict[str, Any]]:
    rows = payload.get(key)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def _blocker_ids_from_rows(payload: dict[str, Any]) -> list[str]:
    return _unique_sorted([str(row.get("blocker_id", "")) for row in _rows(payload)])


def _blocker_ids_from_owner_packet(payload: dict[str, Any]) -> list[str]:
    blocker_ids: list[str] = []
    for packet in _rows(payload, "owner_packets"):
        ids = packet.get("blocker_ids")
        if isinstance(ids, list):
            blocker_ids.extend(str(item) for item in ids if item)
    return _unique_sorted(blocker_ids)


def _release_tier_blocker_ids(payload: dict[str, Any]) -> list[str]:
    blocker_ids: list[str] = []
    for row in _rows(payload, "release_tier_rows"):
        blockers = row.get("blockers")
        if isinstance(blockers, list):
            blocker_ids.extend(str(item) for item in blockers if item)
    return _unique_sorted(blocker_ids)


def _blocker_ids_from_key(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    return _unique_sorted([str(item) for item in values if item]) if isinstance(values, list) else []


def _fresh_full_validation_blocker_ids(payload: dict[str, Any]) -> list[str]:
    return _unique_sorted(
        [
            f"fresh_full_validation::{blocker}"
            for blocker in _blocker_ids_from_key(payload, "blockers")
            if not blocker.startswith("fresh_full_validation::")
        ]
        + [
            blocker
            for blocker in _blocker_ids_from_key(payload, "blockers")
            if blocker.startswith("fresh_full_validation::")
        ]
    )


def _int_from_summary(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    return int(value) if isinstance(value, int | float | str) and str(value).isdigit() else 0


def _blocked_requirement_ids(payload: dict[str, Any]) -> list[str]:
    return _unique_sorted(
        [
            str(row.get("requirement_id", ""))
            for row in _rows(payload)
            if str(row.get("status", "")).startswith("blocked")
        ]
    )


def _section_rows(optional_sections: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label in PM_FAILURE_BUNDLE_REQUIRED_SECTION_LABELS:
        bundle_path = str(optional_sections.get(label, ""))
        rows.append(
            {
                "label": label,
                "present": bool(bundle_path and bundle_path != "missing"),
                "redacted_bundle_path": bundle_path if bundle_path else "missing",
            }
        )
    return rows


def _build_pm_failure_bundle_coverage(
    *,
    bundle_dir: Path,
    optional_sections: dict[str, str],
    pm_release_blocker_action_register: Path | None,
    pm_release_blocker_closure_board: Path | None,
    pm_release_gate_completion_audit: Path | None,
    pm_release_gate_reviewer_handoff: Path | None,
    pm_owner_evidence_request_packet: Path | None,
) -> dict[str, Any]:
    action_register = _load_json_dict(pm_release_blocker_action_register)
    closure_board = _load_json_dict(pm_release_blocker_closure_board)
    completion_audit = _load_json_dict(pm_release_gate_completion_audit)
    reviewer_handoff = _load_json_dict(pm_release_gate_reviewer_handoff)
    owner_packet = _load_json_dict(pm_owner_evidence_request_packet)
    ga_enterprise_readiness = _load_optional_section_json(optional_sections, "ga_enterprise_readiness_report")
    ga_enterprise_signoff = _load_optional_section_json(optional_sections, "ga_enterprise_signoff_intake_packet")
    fresh_full_validation = _load_optional_section_json(optional_sections, "fresh_full_validation_lane_status")
    action_blocker_ids = _blocker_ids_from_rows(action_register)
    closure_blocker_ids = _blocker_ids_from_rows(closure_board)
    handoff_blocker_ids = _blocker_ids_from_rows(reviewer_handoff)
    owner_packet_blocker_ids = _blocker_ids_from_owner_packet(owner_packet)
    release_tier_blocker_ids = _release_tier_blocker_ids(reviewer_handoff)
    canonical_release_area_evidence = (
        action_register.get("canonical_release_area_evidence")
        if isinstance(action_register.get("canonical_release_area_evidence"), dict)
        else {}
    )
    release_area_blocker_ids = _unique_sorted(
        [
            str(item)
            for item in (
                canonical_release_area_evidence.get("release_area_blocker_ids", [])
                if isinstance(canonical_release_area_evidence, dict)
                else []
            )
            if str(item)
        ]
        or [
            str(row.get("blocker_id", ""))
            for row in _rows(action_register)
            if str(row.get("scope", "")) == "release_area"
        ]
    )
    if not canonical_release_area_evidence:
        canonical_release_area_evidence = {
            "release_area_green_count": 0,
            "release_area_total_count": 0,
            "release_area_summary": "",
            "release_area_blocker_count": len(release_area_blocker_ids),
            "release_area_blocker_ids": release_area_blocker_ids,
            "claim_boundary": (
                "Release-area blockers are distinct from release-tier/open blocker lists "
                "used for owner handoff."
            ),
        }
    ga_covered_blocker_ids = _unique_sorted(
        [
            *release_tier_blocker_ids,
            *_blocker_ids_from_key(ga_enterprise_readiness, "blockers"),
            *_blocker_ids_from_key(ga_enterprise_signoff, "current_blockers"),
            *_fresh_full_validation_blocker_ids(fresh_full_validation),
        ]
    )
    core_blocker_ids = owner_packet_blocker_ids
    action_extra_blocker_ids = _unique_sorted(
        [blocker for blocker in action_blocker_ids if blocker not in set(core_blocker_ids)]
    )
    core_blocker_id_sources_match = bool(
        core_blocker_ids
        and core_blocker_ids == closure_blocker_ids
        and core_blocker_ids == handoff_blocker_ids
        and set(core_blocker_ids).issubset(set(action_blocker_ids))
    )
    action_extra_blocker_ids_covered = set(action_extra_blocker_ids).issubset(set(ga_covered_blocker_ids))
    section_rows = _section_rows(optional_sections)
    missing_section_labels = [row["label"] for row in section_rows if not row["present"]]
    blocker_id_sources_match = bool(core_blocker_id_sources_match and action_extra_blocker_ids_covered)
    release_tier_rows_present = bool(_rows(reviewer_handoff, "release_tier_rows"))
    owner_packets_present = bool(_rows(owner_packet, "owner_packets"))
    release_tier_owner_packets_present = bool(_rows(owner_packet, "release_tier_owner_packets"))
    owner_packet_summary = owner_packet.get("summary") if isinstance(owner_packet.get("summary"), dict) else {}
    owner_packet_tier_impact_contract_pass = owner_packet_summary.get("release_tier_impact_contract_pass") is True
    owner_packet_missing_release_tier_impact_count = _int_from_summary(
        owner_packet_summary,
        "missing_release_tier_impact_count",
    )
    owner_packet_blocked_release_tier_impact_count = _int_from_summary(
        owner_packet_summary,
        "blocked_release_tier_impact_count",
    )
    owner_packet_tier_impact_complete = bool(
        owner_packet_tier_impact_contract_pass
        and owner_packet_missing_release_tier_impact_count == 0
        and owner_packet_blocked_release_tier_impact_count > 0
    )
    coverage_pass = bool(
        not missing_section_labels
        and blocker_id_sources_match
        and release_tier_rows_present
        and owner_packets_present
        and release_tier_owner_packets_present
        and owner_packet_tier_impact_complete
    )
    payload = {
        "schema_version": "pm-failure-bundle-coverage.v1",
        "generated_at": _now_utc_iso(),
        "coverage_pass": coverage_pass,
        "reason_code": "PASS" if coverage_pass else "ERR_PM_FAILURE_BUNDLE_COVERAGE_INCOMPLETE",
        "claim_boundary": (
            "This index proves support-bundle coverage for open PM blocker handoff artifacts only. "
            "It does not close tracked CI streak, human UX observation, license, Limited Commercial, "
            "GA/Enterprise, or other external release evidence blockers."
        ),
        "summary": {
            "open_blocker_count": len(action_blocker_ids),
            "release_area_blocker_count": len(release_area_blocker_ids),
            "release_area_green_count": int(
                canonical_release_area_evidence.get("release_area_green_count", 0) or 0
            ),
            "release_area_total_count": int(
                canonical_release_area_evidence.get("release_area_total_count", 0) or 0
            ),
            "release_tier_blocker_count": len(release_tier_blocker_ids),
            "required_section_count": len(section_rows),
            "missing_required_section_count": len(missing_section_labels),
            "blocker_id_sources_match": blocker_id_sources_match,
            "core_blocker_id_sources_match": core_blocker_id_sources_match,
            "action_extra_blocker_count": len(action_extra_blocker_ids),
            "action_extra_blocker_ids_covered": action_extra_blocker_ids_covered,
            "release_tier_rows_present": release_tier_rows_present,
            "owner_packets_present": owner_packets_present,
            "release_tier_owner_packets_present": release_tier_owner_packets_present,
            "owner_packet_tier_impact_contract_pass": owner_packet_tier_impact_contract_pass,
            "owner_packet_missing_release_tier_impact_count": owner_packet_missing_release_tier_impact_count,
            "owner_packet_blocked_release_tier_impact_count": owner_packet_blocked_release_tier_impact_count,
            "owner_packet_tier_impact_complete": owner_packet_tier_impact_complete,
        },
        "open_blocker_ids": action_blocker_ids,
        "release_area_blocker_ids": release_area_blocker_ids,
        "canonical_release_area_evidence": canonical_release_area_evidence,
        "release_tier_blocker_ids": release_tier_blocker_ids,
        "ga_covered_blocker_ids": ga_covered_blocker_ids,
        "action_extra_blocker_ids": action_extra_blocker_ids,
        "blocked_requirement_ids": _blocked_requirement_ids(completion_audit),
        "source_blocker_ids": {
            "pm_release_blocker_action_register": action_blocker_ids,
            "pm_release_blocker_closure_board": closure_blocker_ids,
            "pm_release_gate_reviewer_handoff": handoff_blocker_ids,
            "pm_owner_evidence_request_packet": owner_packet_blocker_ids,
        },
        "required_section_rows": section_rows,
        "missing_required_section_labels": missing_section_labels,
        "source_artifacts": {
            "pm_release_blocker_action_register": str(pm_release_blocker_action_register or ""),
            "pm_release_blocker_closure_board": str(pm_release_blocker_closure_board or ""),
            "pm_release_gate_completion_audit": str(pm_release_gate_completion_audit or ""),
            "pm_release_gate_reviewer_handoff": str(pm_release_gate_reviewer_handoff or ""),
            "pm_owner_evidence_request_packet": str(pm_owner_evidence_request_packet or ""),
        },
    }
    destination = bundle_dir / "pm_failure_bundle_coverage.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["bundle_path"] = str(destination)
    payload["sha256"] = _sha256_path(destination)
    return payload


def build_support_bundle(
    *,
    bundle_dir: Path = DEFAULT_BUNDLE_DIR,
    archive_out: Path = DEFAULT_ARCHIVE_OUT,
    audit_log_path: Path | None = None,
    license_status: Path | None = None,
    p0_status: Path = DEFAULT_P0_STATUS,
    p1_status: Path = DEFAULT_P1_STATUS,
    p1_strict_evidence_preflight: Path = DEFAULT_P1_STRICT_PREFLIGHT,
    project_ops_snapshot: Path = DEFAULT_PROJECT_OPS_SNAPSHOT,
    project_ops_deployment_drill: Path = DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL,
    runtime_probe: Path = DEFAULT_RUNTIME_PROBE,
    runtime_packaging_manifest: Path = DEFAULT_RUNTIME_PACKAGING_MANIFEST,
    viewer_performance_budget_manifest: Path = DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    workstation_hardware_profile: Path = DEFAULT_WORKSTATION_HARDWARE_PROFILE,
    workstation_service_budget: Path = DEFAULT_WORKSTATION_SERVICE_BUDGET,
    workstation_delivery_package_manifest: Path = DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST,
    workstation_delivery_readiness: Path = DEFAULT_WORKSTATION_DELIVERY_READINESS,
    workstation_delivery_viewer_smoke: Path = DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE,
    client_input_validation_report: Path = DEFAULT_CLIENT_INPUT_VALIDATION_REPORT,
    workstation_job_record: Path = DEFAULT_WORKSTATION_JOB_RECORD,
    workstation_job_retention_policy: Path = DEFAULT_WORKSTATION_JOB_RETENTION_POLICY,
    external_benchmark_updates: Path = DEFAULT_EXTERNAL_BENCHMARK_UPDATES,
    residual_holdout_updates: Path = DEFAULT_RESIDUAL_HOLDOUT_UPDATES,
    pm_release_blocker_action_register: Path | None = DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    pm_release_blocker_closure_board: Path | None = DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD,
    pm_release_gate_completion_audit: Path | None = DEFAULT_PM_RELEASE_GATE_COMPLETION_AUDIT,
    pm_release_gate_reviewer_handoff: Path | None = DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF,
    pm_owner_evidence_request_packet: Path | None = DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET,
    structural_scope_owner_review_packet: Path | None = DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET,
    ci_streak_intake_packet: Path | None = DEFAULT_CI_STREAK_INTAKE_PACKET,
    ci_streak_manifest: Path | None = DEFAULT_CI_STREAK_MANIFEST,
    github_actions_ci_streak_evidence: Path | None = DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE,
    license_status_intake_packet: Path | None = DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
    license_status_closure_report: Path | None = DEFAULT_LICENSE_STATUS_CLOSURE_REPORT,
    license_status_template: Path | None = DEFAULT_LICENSE_STATUS_TEMPLATE,
    frontend_dependency_audit_report: Path | None = DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT,
    ga_enterprise_readiness_report: Path | None = DEFAULT_GA_ENTERPRISE_READINESS_REPORT,
    ga_enterprise_signoff_intake_packet: Path | None = DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET,
    fresh_full_validation_lane_status: Path | None = DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS,
    independent_vv_attestation_template: Path | None = DEFAULT_INDEPENDENT_VV_ATTESTATION_TEMPLATE,
    family_validation_manual_signoff_template: Path | None = DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF_TEMPLATE,
    customer_audit_failure_bundle_sla_template: Path | None = DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA_TEMPLATE,
    paid_pilot_scope_guard_report: Path | None = DEFAULT_PAID_PILOT_SCOPE_GUARD_REPORT,
    release_validation_manual: Path | None = DEFAULT_RELEASE_VALIDATION_MANUAL,
    release_limitation_manual: Path | None = DEFAULT_RELEASE_LIMITATION_MANUAL,
    ux_new_user_observation_report: Path | None = DEFAULT_UX_NEW_USER_OBSERVATION_REPORT,
    ux_new_user_observation_intake_packet: Path | None = DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET,
    ux_new_user_observation_template: Path | None = DEFAULT_UX_NEW_USER_OBSERVATION_TEMPLATE,
    template_evidence_safety_report: Path | None = DEFAULT_TEMPLATE_EVIDENCE_SAFETY_REPORT,
    pm_release_reproduction_command_audit: Path | None = DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
    ai_orchestration_preflight_report: Path | None = DEFAULT_AI_ORCHESTRATION_PREFLIGHT_REPORT,
    commercial_gap_ledger_status: Path | None = DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS,
    gap_closure_status: Path | None = DEFAULT_GAP_CLOSURE_STATUS,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    pyproject: Path = DEFAULT_PYPROJECT,
    viewer_report: Path | None = None,
) -> dict[str, Any]:
    required_specs = [
        ("p0_status", p0_status),
        ("p1_status", p1_status),
        ("p1_strict_evidence_preflight", p1_strict_evidence_preflight),
        ("project_ops_snapshot", project_ops_snapshot),
        ("project_ops_deployment_drill", project_ops_deployment_drill),
        ("runtime_probe", runtime_probe),
        ("runtime_packaging_manifest", runtime_packaging_manifest),
        ("viewer_performance_budget_manifest", viewer_performance_budget_manifest),
        ("viewer_browser_performance_probe", viewer_browser_performance_probe),
        ("viewer_visual_regression_baseline", viewer_visual_regression_baseline),
        ("workstation_hardware_profile", workstation_hardware_profile),
        ("workstation_service_budget", workstation_service_budget),
        ("workstation_delivery_package_manifest", workstation_delivery_package_manifest),
        ("workstation_delivery_readiness", workstation_delivery_readiness),
        ("workstation_delivery_viewer_smoke", workstation_delivery_viewer_smoke),
        ("client_input_validation_report", client_input_validation_report),
        ("workstation_job_record", workstation_job_record),
        ("workstation_job_retention_policy", workstation_job_retention_policy),
        ("external_benchmark_updates", external_benchmark_updates),
        ("residual_holdout_updates", residual_holdout_updates),
        ("package_json", package_json),
        ("pyproject", pyproject),
    ]
    optional_specs = [
        ("pm_release_blocker_action_register", pm_release_blocker_action_register),
        ("pm_release_blocker_closure_board", pm_release_blocker_closure_board),
        ("pm_release_gate_completion_audit", pm_release_gate_completion_audit),
        ("pm_release_gate_reviewer_handoff", pm_release_gate_reviewer_handoff),
        ("pm_owner_evidence_request_packet", pm_owner_evidence_request_packet),
        ("structural_scope_owner_review_packet", structural_scope_owner_review_packet),
        ("ci_streak_intake_packet", ci_streak_intake_packet),
        ("ci_streak_manifest", ci_streak_manifest),
        ("github_actions_ci_streak_evidence", github_actions_ci_streak_evidence),
        ("license_status_intake_packet", license_status_intake_packet),
        ("license_status_closure_report", license_status_closure_report),
        ("license_status_template", license_status_template),
        ("frontend_dependency_audit_report", frontend_dependency_audit_report),
        ("ga_enterprise_readiness_report", ga_enterprise_readiness_report),
        ("ga_enterprise_signoff_intake_packet", ga_enterprise_signoff_intake_packet),
        ("fresh_full_validation_lane_status", fresh_full_validation_lane_status),
        ("independent_vv_attestation_template", independent_vv_attestation_template),
        ("family_validation_manual_signoff_template", family_validation_manual_signoff_template),
        ("customer_audit_failure_bundle_sla_template", customer_audit_failure_bundle_sla_template),
        ("paid_pilot_scope_guard_report", paid_pilot_scope_guard_report),
        ("release_validation_manual", release_validation_manual),
        ("release_limitation_manual", release_limitation_manual),
        ("ux_new_user_observation_report", ux_new_user_observation_report),
        ("ux_new_user_observation_intake_packet", ux_new_user_observation_intake_packet),
        ("ux_new_user_observation_template", ux_new_user_observation_template),
        ("template_evidence_safety_report", template_evidence_safety_report),
        ("pm_release_reproduction_command_audit", pm_release_reproduction_command_audit),
        ("ai_orchestration_preflight_report", ai_orchestration_preflight_report),
        ("commercial_gap_ledger_status", commercial_gap_ledger_status),
        ("gap_closure_status", gap_closure_status),
        ("viewer_report", viewer_report),
    ]
    artifact_rows = [_write_redacted_copy(label=label, source=path, bundle_dir=bundle_dir) for label, path in required_specs]
    for label, path in optional_specs:
        if path is not None:
            artifact_rows.append(_write_redacted_copy(label=label, source=path, bundle_dir=bundle_dir))

    audit_digest = _build_audit_digest(audit_log_path, bundle_dir)
    license_snapshot = _build_license_snapshot(license_status, bundle_dir)
    redaction = _redaction_self_test()
    index = _build_index(bundle_dir=bundle_dir, artifact_rows=artifact_rows, audit_digest=audit_digest)
    roundtrip = _roundtrip_self_test(index)
    optional_section_map = {
        row["label"]: row["redacted_bundle_path"] if row.get("available") else "missing"
        for row in artifact_rows[len(required_specs) :]
    }
    pm_failure_bundle_coverage = _build_pm_failure_bundle_coverage(
        bundle_dir=bundle_dir,
        optional_sections=optional_section_map,
        pm_release_blocker_action_register=pm_release_blocker_action_register,
        pm_release_blocker_closure_board=pm_release_blocker_closure_board,
        pm_release_gate_completion_audit=pm_release_gate_completion_audit,
        pm_release_gate_reviewer_handoff=pm_release_gate_reviewer_handoff,
        pm_owner_evidence_request_packet=pm_owner_evidence_request_packet,
    )
    archive_source_paths = [
        *[
            Path(str(row.get("redacted_bundle_path", "")))
            for row in artifact_rows
            if row.get("available") and row.get("redacted_bundle_path")
        ],
        Path(str(audit_digest.get("bundle_path", ""))),
        Path(str(license_snapshot.get("bundle_path", ""))),
        Path(str(index.get("bundle_index_path", ""))),
        Path(str(pm_failure_bundle_coverage.get("bundle_path", ""))),
    ]
    export_archive = _build_export_archive(
        bundle_dir=bundle_dir,
        archive_out=archive_out,
        source_paths=archive_source_paths,
    )
    archive_roundtrip = _archive_roundtrip_self_test(export_archive)

    missing_required = [row["label"] for row in artifact_rows[: len(required_specs)] if not row.get("available")]
    blockers = [
        *(f"required_artifact_missing:{label}" for label in missing_required),
        *(["redaction_self_test_failed"] if not redaction["pass"] else []),
        *(["audit_event_digest_missing"] if not audit_digest.get("sha256") else []),
        *(["bundle_roundtrip_test_failed"] if not roundtrip["pass"] else []),
        *(["archive_export_failed"] if not export_archive.get("available") else []),
        *(["archive_roundtrip_test_failed"] if not archive_roundtrip["pass"] else []),
        *(["pm_failure_bundle_coverage_incomplete"] if not pm_failure_bundle_coverage["coverage_pass"] else []),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_SUPPORT_BUNDLE_EVIDENCE_PENDING",
        "summary_line": (
            f"Support bundle: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"artifacts={index['available_artifact_count']}/{index['artifact_count']} | "
            f"redaction={redaction['pass']} | roundtrip={roundtrip['pass']} | "
            f"archive={archive_roundtrip['pass']}"
        ),
        "bundle_policy": {
            "redact_secrets": True,
            "include_private_keys": False,
            "include_tokens": False,
            "tenant_scoped": True,
            "copy_mode": "redacted_evidence_plus_digest",
            "one_click_export": True,
            "export_format": "zip",
        },
        "required_sections": {
            row["label"]: row["redacted_bundle_path"] if row.get("available") else "missing"
            for row in artifact_rows[: len(required_specs)]
        },
        "optional_sections": {
            row["label"]: row["redacted_bundle_path"] if row.get("available") else "missing"
            for row in artifact_rows[len(required_specs) :]
        },
        "checks": {
            "redaction_self_test_pass": redaction["pass"],
            "audit_event_digest_pass": bool(audit_digest.get("sha256")),
            "bundle_roundtrip_test_pass": roundtrip["pass"],
            "archive_roundtrip_test_pass": archive_roundtrip["pass"],
            "missing_required_count": len(missing_required),
            "pm_failure_bundle_coverage_pass": pm_failure_bundle_coverage["coverage_pass"],
        },
        "audit_digest": audit_digest,
        "license_status": license_snapshot,
        "pm_failure_bundle_coverage": pm_failure_bundle_coverage,
        "bundle_index": {
            "path": index["bundle_index_path"],
            "sha256": index["bundle_index_sha256"],
            "artifact_count": index["artifact_count"],
            "available_artifact_count": index["available_artifact_count"],
        },
        "export_archive": export_archive,
        "archive_roundtrip": archive_roundtrip,
        "artifact_rows": artifact_rows,
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--archive-out", type=Path, default=DEFAULT_ARCHIVE_OUT)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--audit-log-path", type=Path)
    parser.add_argument("--license-status-json", type=Path)
    parser.add_argument("--p0-status", type=Path, default=DEFAULT_P0_STATUS)
    parser.add_argument("--p1-status", type=Path, default=DEFAULT_P1_STATUS)
    parser.add_argument("--p1-strict-evidence-preflight", type=Path, default=DEFAULT_P1_STRICT_PREFLIGHT)
    parser.add_argument("--project-ops-snapshot", type=Path, default=DEFAULT_PROJECT_OPS_SNAPSHOT)
    parser.add_argument("--project-ops-deployment-drill", type=Path, default=DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL)
    parser.add_argument("--runtime-probe", type=Path, default=DEFAULT_RUNTIME_PROBE)
    parser.add_argument("--runtime-packaging-manifest", type=Path, default=DEFAULT_RUNTIME_PACKAGING_MANIFEST)
    parser.add_argument(
        "--viewer-performance-budget-manifest",
        type=Path,
        default=DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    )
    parser.add_argument(
        "--viewer-browser-performance-probe",
        type=Path,
        default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    )
    parser.add_argument(
        "--viewer-visual-regression-baseline",
        type=Path,
        default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    )
    parser.add_argument("--workstation-hardware-profile", type=Path, default=DEFAULT_WORKSTATION_HARDWARE_PROFILE)
    parser.add_argument("--workstation-service-budget", type=Path, default=DEFAULT_WORKSTATION_SERVICE_BUDGET)
    parser.add_argument(
        "--workstation-delivery-package-manifest",
        type=Path,
        default=DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST,
    )
    parser.add_argument("--workstation-delivery-readiness", type=Path, default=DEFAULT_WORKSTATION_DELIVERY_READINESS)
    parser.add_argument(
        "--workstation-delivery-viewer-smoke",
        type=Path,
        default=DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE,
    )
    parser.add_argument("--client-input-validation-report", type=Path, default=DEFAULT_CLIENT_INPUT_VALIDATION_REPORT)
    parser.add_argument("--workstation-job-record", type=Path, default=DEFAULT_WORKSTATION_JOB_RECORD)
    parser.add_argument(
        "--workstation-job-retention-policy",
        type=Path,
        default=DEFAULT_WORKSTATION_JOB_RETENTION_POLICY,
    )
    parser.add_argument("--external-benchmark-updates", type=Path, default=DEFAULT_EXTERNAL_BENCHMARK_UPDATES)
    parser.add_argument("--residual-holdout-updates", type=Path, default=DEFAULT_RESIDUAL_HOLDOUT_UPDATES)
    parser.add_argument(
        "--pm-release-blocker-action-register",
        type=Path,
        default=DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    )
    parser.add_argument(
        "--pm-release-blocker-closure-board",
        type=Path,
        default=DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD,
    )
    parser.add_argument(
        "--pm-release-gate-completion-audit",
        type=Path,
        default=DEFAULT_PM_RELEASE_GATE_COMPLETION_AUDIT,
    )
    parser.add_argument(
        "--pm-release-gate-reviewer-handoff",
        type=Path,
        default=DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF,
    )
    parser.add_argument(
        "--pm-owner-evidence-request-packet",
        type=Path,
        default=DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET,
    )
    parser.add_argument(
        "--structural-scope-owner-review-packet",
        type=Path,
        default=DEFAULT_STRUCTURAL_SCOPE_OWNER_REVIEW_PACKET,
    )
    parser.add_argument(
        "--ci-streak-intake-packet",
        type=Path,
        default=DEFAULT_CI_STREAK_INTAKE_PACKET,
    )
    parser.add_argument(
        "--ci-streak-manifest",
        type=Path,
        default=DEFAULT_CI_STREAK_MANIFEST,
    )
    parser.add_argument(
        "--github-actions-ci-streak-evidence",
        type=Path,
        default=DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE,
    )
    parser.add_argument(
        "--license-status-intake-packet",
        type=Path,
        default=DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
    )
    parser.add_argument(
        "--license-status-closure-report",
        type=Path,
        default=DEFAULT_LICENSE_STATUS_CLOSURE_REPORT,
    )
    parser.add_argument(
        "--license-status-template",
        type=Path,
        default=DEFAULT_LICENSE_STATUS_TEMPLATE,
    )
    parser.add_argument(
        "--frontend-dependency-audit-report",
        type=Path,
        default=DEFAULT_FRONTEND_DEPENDENCY_AUDIT_REPORT,
    )
    parser.add_argument(
        "--ga-enterprise-readiness-report",
        type=Path,
        default=DEFAULT_GA_ENTERPRISE_READINESS_REPORT,
    )
    parser.add_argument(
        "--ga-enterprise-signoff-intake-packet",
        type=Path,
        default=DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE_PACKET,
    )
    parser.add_argument(
        "--independent-vv-attestation-template",
        type=Path,
        default=DEFAULT_INDEPENDENT_VV_ATTESTATION_TEMPLATE,
    )
    parser.add_argument(
        "--family-validation-manual-signoff-template",
        type=Path,
        default=DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF_TEMPLATE,
    )
    parser.add_argument(
        "--customer-audit-failure-bundle-sla-template",
        type=Path,
        default=DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA_TEMPLATE,
    )
    parser.add_argument(
        "--paid-pilot-scope-guard-report",
        type=Path,
        default=DEFAULT_PAID_PILOT_SCOPE_GUARD_REPORT,
    )
    parser.add_argument(
        "--release-validation-manual",
        type=Path,
        default=DEFAULT_RELEASE_VALIDATION_MANUAL,
    )
    parser.add_argument(
        "--release-limitation-manual",
        type=Path,
        default=DEFAULT_RELEASE_LIMITATION_MANUAL,
    )
    parser.add_argument(
        "--ux-new-user-observation-report",
        type=Path,
        default=DEFAULT_UX_NEW_USER_OBSERVATION_REPORT,
    )
    parser.add_argument(
        "--ux-new-user-observation-intake-packet",
        type=Path,
        default=DEFAULT_UX_NEW_USER_OBSERVATION_INTAKE_PACKET,
    )
    parser.add_argument(
        "--ux-new-user-observation-template",
        type=Path,
        default=DEFAULT_UX_NEW_USER_OBSERVATION_TEMPLATE,
    )
    parser.add_argument(
        "--template-evidence-safety-report",
        type=Path,
        default=DEFAULT_TEMPLATE_EVIDENCE_SAFETY_REPORT,
    )
    parser.add_argument(
        "--pm-release-reproduction-command-audit",
        type=Path,
        default=DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
    )
    parser.add_argument(
        "--ai-orchestration-preflight-report",
        type=Path,
        default=DEFAULT_AI_ORCHESTRATION_PREFLIGHT_REPORT,
    )
    parser.add_argument(
        "--commercial-gap-ledger-status",
        type=Path,
        default=DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS,
    )
    parser.add_argument(
        "--gap-closure-status",
        type=Path,
        default=DEFAULT_GAP_CLOSURE_STATUS,
    )
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--viewer-report", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_support_bundle(
        bundle_dir=args.bundle_dir,
        archive_out=args.archive_out,
        audit_log_path=args.audit_log_path,
        license_status=args.license_status_json,
        p0_status=args.p0_status,
        p1_status=args.p1_status,
        p1_strict_evidence_preflight=args.p1_strict_evidence_preflight,
        project_ops_snapshot=args.project_ops_snapshot,
        project_ops_deployment_drill=args.project_ops_deployment_drill,
        runtime_probe=args.runtime_probe,
        runtime_packaging_manifest=args.runtime_packaging_manifest,
        viewer_performance_budget_manifest=args.viewer_performance_budget_manifest,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
        workstation_hardware_profile=args.workstation_hardware_profile,
        workstation_service_budget=args.workstation_service_budget,
        workstation_delivery_package_manifest=args.workstation_delivery_package_manifest,
        workstation_delivery_readiness=args.workstation_delivery_readiness,
        workstation_delivery_viewer_smoke=args.workstation_delivery_viewer_smoke,
        client_input_validation_report=args.client_input_validation_report,
        workstation_job_record=args.workstation_job_record,
        workstation_job_retention_policy=args.workstation_job_retention_policy,
        external_benchmark_updates=args.external_benchmark_updates,
        residual_holdout_updates=args.residual_holdout_updates,
        pm_release_blocker_action_register=args.pm_release_blocker_action_register,
        pm_release_blocker_closure_board=args.pm_release_blocker_closure_board,
        pm_release_gate_completion_audit=args.pm_release_gate_completion_audit,
        pm_release_gate_reviewer_handoff=args.pm_release_gate_reviewer_handoff,
        pm_owner_evidence_request_packet=args.pm_owner_evidence_request_packet,
        structural_scope_owner_review_packet=args.structural_scope_owner_review_packet,
        ci_streak_intake_packet=args.ci_streak_intake_packet,
        ci_streak_manifest=args.ci_streak_manifest,
        github_actions_ci_streak_evidence=args.github_actions_ci_streak_evidence,
        license_status_intake_packet=args.license_status_intake_packet,
        license_status_closure_report=args.license_status_closure_report,
        license_status_template=args.license_status_template,
        frontend_dependency_audit_report=args.frontend_dependency_audit_report,
        ga_enterprise_readiness_report=args.ga_enterprise_readiness_report,
        ga_enterprise_signoff_intake_packet=args.ga_enterprise_signoff_intake_packet,
        independent_vv_attestation_template=args.independent_vv_attestation_template,
        family_validation_manual_signoff_template=args.family_validation_manual_signoff_template,
        customer_audit_failure_bundle_sla_template=args.customer_audit_failure_bundle_sla_template,
        paid_pilot_scope_guard_report=args.paid_pilot_scope_guard_report,
        release_validation_manual=args.release_validation_manual,
        release_limitation_manual=args.release_limitation_manual,
        ux_new_user_observation_report=args.ux_new_user_observation_report,
        ux_new_user_observation_intake_packet=args.ux_new_user_observation_intake_packet,
        ux_new_user_observation_template=args.ux_new_user_observation_template,
        template_evidence_safety_report=args.template_evidence_safety_report,
        pm_release_reproduction_command_audit=args.pm_release_reproduction_command_audit,
        ai_orchestration_preflight_report=args.ai_orchestration_preflight_report,
        commercial_gap_ledger_status=args.commercial_gap_ledger_status,
        gap_closure_status=args.gap_closure_status,
        package_json=args.package_json,
        pyproject=args.pyproject,
        viewer_report=args.viewer_report,
    )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
