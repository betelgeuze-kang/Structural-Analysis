#!/usr/bin/env python3
"""Build a non-mutating application plan for structural-scope owner decisions."""

from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_structural_scope_owner_review_packet as owner_review  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-owner-decision-application-plan.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "structural_scope_contamination_audit.json"
DEFAULT_QUARANTINE_MANIFEST = PRODUCTIZATION / "structural_scope_quarantine_manifest.json"
DEFAULT_OWNER_DECISIONS = PRODUCTIZATION / "structural_scope_owner_decisions.json"
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_owner_decision_application_plan.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_NEXT_BATCH_TEMPLATE = (
    PRODUCTIZATION / "structural_scope_owner_decisions.next_batch.template.json"
)
DEFAULT_NEXT_BATCH_TEMPLATE_MD = DEFAULT_NEXT_BATCH_TEMPLATE.with_suffix(".md")
DEFAULT_NEXT_BATCH_TEMPLATE_CSV = DEFAULT_NEXT_BATCH_TEMPLATE.with_suffix(".csv")
DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE = (
    PRODUCTIZATION
    / "structural_scope_owner_decisions.release_surface_first.template.json"
)
DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_MD = (
    DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE.with_suffix(".md")
)
DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_CSV = (
    DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE.with_suffix(".csv")
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _text(row.get(key))
        if value:
            _increment(counts, value)
    return dict(sorted(counts.items()))


def _deduped(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _csv_text(rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(owner_review.OWNER_DECISION_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                column: (
                    ";".join(str(item) for item in row[column])
                    if isinstance(row.get(column), list)
                    else str(row.get(column, ""))
                )
                for column in owner_review.OWNER_DECISION_COLUMNS
            }
        )
    return output.getvalue()


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for family in _as_list(row.get("families")):
            value = _text(family)
            if value:
                _increment(counts, value)
    return dict(sorted(counts.items()))


def _git_rm_args(paths: list[str]) -> list[str]:
    return ["git", "rm", "--", *paths] if paths else []


def _cleanup_owner_decision(decision: str) -> bool:
    return decision in {
        "delete_from_structural_repository",
        "extract_to_molecular_or_science_repository",
    }


def _action_for_decision(row: dict[str, Any]) -> dict[str, Any]:
    path = _text(row.get("path"))
    decision = _text(row.get("owner_decision"))
    if decision == "delete_from_structural_repository":
        return {
            "required_action": "remove_from_structural_repository",
            "safe_to_auto_apply": False,
            "manual_application_required": True,
            "suggested_git_rm_args": ["git", "rm", "--", path],
            "post_apply_verification": [
                "python3 scripts/check_structural_scope_contamination.py",
                "python3 scripts/build_structural_scope_owner_review_packet.py",
            ],
        }
    if decision == "extract_to_molecular_or_science_repository":
        return {
            "required_action": "extract_elsewhere_then_remove_from_structural_repository",
            "safe_to_auto_apply": False,
            "manual_application_required": True,
            "external_repository_or_archive_required": True,
            "post_extract_git_rm_args": ["git", "rm", "--", path],
            "post_apply_verification": [
                "python3 scripts/check_structural_scope_contamination.py",
                "python3 scripts/build_structural_scope_owner_review_packet.py",
            ],
        }
    if decision == "retain_quarantined_with_signed_owner_exception":
        return {
            "required_action": "retain_quarantined_signed_exception",
            "safe_to_auto_apply": False,
            "manual_application_required": False,
            "post_apply_verification": [
                "python3 scripts/build_structural_scope_owner_review_packet.py",
            ],
        }
    return {
        "required_action": "owner_decision_required",
        "safe_to_auto_apply": False,
        "manual_application_required": True,
        "post_apply_verification": [
            "fill structural_scope_owner_decisions.json from the owner decision template",
            "python3 scripts/build_structural_scope_owner_review_packet.py",
        ],
    }


def _plan_row(row: dict[str, Any]) -> dict[str, Any]:
    action = _action_for_decision(row)
    return {
        "path": _text(row.get("path")),
        "path_area": _text(row.get("path_area")),
        "families": [str(item) for item in _as_list(row.get("families"))],
        "matched_tokens": [str(item) for item in _as_list(row.get("matched_tokens"))],
        "owner_decision": _text(row.get("owner_decision")),
        "allowed_owner_decisions": [
            str(item) for item in _as_list(row.get("allowed_owner_decisions"))
        ],
        "owner_decision_valid": bool(row.get("owner_decision_valid")),
        "owner_review_state": _text(row.get("owner_review_state")),
        "post_decision_cleanup_pending": bool(row.get("post_decision_cleanup_pending")),
        "signed_owner_exception_reference": _text(
            row.get("signed_owner_exception_reference")
        ),
        "decision_evidence_reference": _text(row.get("decision_evidence_reference")),
        "external_archive_reference": _text(row.get("external_archive_reference")),
        "recommended_owner_decision": _text(row.get("recommended_owner_decision")),
        "recommended_owner_decision_primary": _text(
            row.get("recommended_owner_decision_primary")
        ),
        "recommended_owner_decision_alternate": _text(
            row.get("recommended_owner_decision_alternate")
        ),
        "current_release_action": _text(row.get("current_release_action")),
        **action,
    }


def _release_surface_first_batch_decision_intake(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    release_rows = sorted(
        [row for row in rows if _text(row.get("path_area")) == "release_surface"],
        key=lambda item: _text(item.get("path")),
    )
    submitted_rows = [
        row for row in release_rows if _text(row.get("owner_decision"))
    ]
    valid_rows = [
        row for row in release_rows if bool(row.get("owner_decision_valid"))
    ]
    valid_cleanup_rows = [
        row
        for row in valid_rows
        if _cleanup_owner_decision(_text(row.get("owner_decision")))
    ]
    pending_rows = [
        row for row in release_rows if not _text(row.get("owner_decision"))
    ]
    invalid_submitted_rows = [
        row
        for row in submitted_rows
        if not bool(row.get("owner_decision_valid"))
    ]
    retain_rows = [
        row
        for row in release_rows
        if _text(row.get("owner_decision"))
        == "retain_quarantined_with_signed_owner_exception"
    ]
    blockers: list[str] = []
    if pending_rows:
        blockers.append(
            f"pending_release_surface_owner_decision_count={len(pending_rows)}"
        )
    if invalid_submitted_rows:
        blockers.append(
            "invalid_release_surface_owner_decision_count="
            f"{len(invalid_submitted_rows)}"
        )
    if retain_rows:
        blockers.append(
            f"release_surface_retain_exception_count={len(retain_rows)}"
        )
    if release_rows and len(valid_cleanup_rows) < len(release_rows):
        blockers.append(
            "release_surface_cleanup_decision_count_below_expected="
            f"{len(valid_cleanup_rows)}/{len(release_rows)}"
        )
    ready = bool(release_rows and not blockers)
    if not release_rows:
        status = "no_release_surface_paths"
    elif invalid_submitted_rows or retain_rows:
        status = "invalid_owner_decisions"
    elif pending_rows:
        status = "pending_owner_decisions"
    elif ready:
        status = "ready_for_manual_cleanup_application"
    else:
        status = "blocked_release_surface_decision_intake"
    return {
        "schema_version": (
            "structural-scope-release-surface-first-batch-decision-intake.v1"
        ),
        "batch_id": "release_surface_first",
        "status": status,
        "ready_for_manual_cleanup_application": ready,
        "expected_path_count": len(release_rows),
        "expected_paths": [row["path"] for row in release_rows],
        "submitted_decision_count": len(submitted_rows),
        "valid_decision_count": len(valid_rows),
        "valid_cleanup_decision_count": len(valid_cleanup_rows),
        "pending_decision_count": len(pending_rows),
        "pending_decision_paths": [row["path"] for row in pending_rows],
        "invalid_submitted_decision_count": len(invalid_submitted_rows),
        "invalid_submitted_decision_paths": [
            row["path"] for row in invalid_submitted_rows
        ],
        "retain_exception_count": len(retain_rows),
        "delete_decision_count": sum(
            1
            for row in release_rows
            if _text(row.get("owner_decision"))
            == "delete_from_structural_repository"
        ),
        "extract_decision_count": sum(
            1
            for row in release_rows
            if _text(row.get("owner_decision"))
            == "extract_to_molecular_or_science_repository"
        ),
        "blockers": blockers,
        "decision_rows": [
            {
                "path": _text(row.get("path")),
                "owner_decision": _text(row.get("owner_decision")),
                "owner_decision_valid": bool(row.get("owner_decision_valid")),
                "owner_review_state": _text(row.get("owner_review_state")),
                "owner_decision_missing_requirements": [
                    str(item)
                    for item in _as_list(
                        row.get("owner_decision_missing_requirements")
                    )
                ],
                "required_action": _action_for_decision(row)["required_action"],
                "allowed_owner_decisions": [
                    str(item)
                    for item in _as_list(row.get("allowed_owner_decisions"))
                ],
            }
            for row in release_rows
        ],
        "claim_boundary": (
            "This release-surface-first intake is non-mutating. It only tracks "
            "whether every non-structural release-surface path has a valid "
            "owner delete/extract decision before a human applies cleanup."
        ),
    }


def _cleanup_command_manifest(cleanup_rows: list[dict[str, Any]]) -> dict[str, Any]:
    delete_paths = [
        row["path"]
        for row in cleanup_rows
        if row["owner_decision"] == "delete_from_structural_repository"
    ]
    extract_paths = [
        row["path"]
        for row in cleanup_rows
        if row["owner_decision"] == "extract_to_molecular_or_science_repository"
    ]
    release_surface_first_paths = [
        row["path"] for row in cleanup_rows if row["path_area"] == "release_surface"
    ]
    return {
        "safe_to_auto_apply": False,
        "manual_application_required": bool(cleanup_rows),
        "release_surface_first_paths": release_surface_first_paths,
        "delete_from_structural_repository": {
            "path_count": len(delete_paths),
            "paths": delete_paths,
            "batched_git_rm_args": _git_rm_args(delete_paths),
            "preconditions": [
                "owner_decision_validation_pass=true",
                "human confirms deletion scope",
            ],
            "post_apply_verification": [
                "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
                "python3 scripts/build_structural_scope_owner_review_packet.py",
                "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-blocked",
                "python3 scripts/build_product_readiness_snapshot.py --check",
            ],
        },
        "extract_to_molecular_or_science_repository": {
            "path_count": len(extract_paths),
            "paths": extract_paths,
            "post_extract_batched_git_rm_args": _git_rm_args(extract_paths),
            "preconditions": [
                "owner_decision_validation_pass=true",
                "external molecular/science repository or archive reference captured",
                "human confirms extracted copy/history is sufficient",
            ],
            "post_apply_verification": [
                "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
                "python3 scripts/build_structural_scope_owner_review_packet.py",
                "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-blocked",
                "python3 scripts/build_product_readiness_snapshot.py --check",
            ],
        },
    }


def _unsafe_cleanup_path_reasons(path: str) -> list[str]:
    normalized = Path(path)
    reasons: list[str] = []
    if not path:
        reasons.append("empty_path")
    if normalized.is_absolute():
        reasons.append("absolute_path")
    if ".." in normalized.parts:
        reasons.append("parent_traversal")
    if normalized.parts and normalized.parts[0] == ".git":
        reasons.append("git_metadata_path")
    return reasons


def _cleanup_application_preflight(cleanup_rows: list[dict[str, Any]]) -> dict[str, Any]:
    path_safety_rows: list[dict[str, Any]] = []
    unsafe_rows: list[dict[str, Any]] = []
    release_surface_policy_violations: list[dict[str, Any]] = []
    retain_cleanup_rows: list[dict[str, Any]] = []
    cleanup_decisions = {
        "delete_from_structural_repository",
        "extract_to_molecular_or_science_repository",
    }
    for row in cleanup_rows:
        path = _text(row.get("path"))
        reasons = _unsafe_cleanup_path_reasons(path)
        safety_row = {
            "path": path,
            "path_area": _text(row.get("path_area")),
            "owner_decision": _text(row.get("owner_decision")),
            "safe_path": not reasons,
            "unsafe_reasons": reasons,
        }
        path_safety_rows.append(safety_row)
        if reasons:
            unsafe_rows.append(safety_row)
        if (
            _text(row.get("path_area")) == "release_surface"
            and _text(row.get("owner_decision")) not in cleanup_decisions
        ):
            release_surface_policy_violations.append(safety_row)
        if _text(row.get("owner_decision")) == "retain_quarantined_with_signed_owner_exception":
            retain_cleanup_rows.append(safety_row)
    blockers = [
        *(
            [f"unsafe_cleanup_path_count={len(unsafe_rows)}"]
            if unsafe_rows
            else []
        ),
        *(
            [
                "release_surface_cleanup_policy_violation_count="
                f"{len(release_surface_policy_violations)}"
            ]
            if release_surface_policy_violations
            else []
        ),
        *(
            [f"retain_exception_cleanup_row_count={len(retain_cleanup_rows)}"]
            if retain_cleanup_rows
            else []
        ),
    ]
    delete_paths = [
        row["path"]
        for row in cleanup_rows
        if row["owner_decision"] == "delete_from_structural_repository"
    ]
    extract_paths = [
        row["path"]
        for row in cleanup_rows
        if row["owner_decision"] == "extract_to_molecular_or_science_repository"
    ]
    return {
        "schema_version": "structural-scope-cleanup-application-preflight.v1",
        "status": (
            "ready_for_manual_cleanup_application"
            if cleanup_rows and not blockers
            else "blocked_cleanup_application"
            if cleanup_rows
            else "no_cleanup_required"
        ),
        "ready": bool(cleanup_rows and not blockers),
        "blockers": blockers,
        "cleanup_path_count": len(cleanup_rows),
        "delete_path_count": len(delete_paths),
        "extract_path_count": len(extract_paths),
        "unsafe_cleanup_path_count": len(unsafe_rows),
        "release_surface_policy_violation_count": len(
            release_surface_policy_violations
        ),
        "retain_exception_cleanup_row_count": len(retain_cleanup_rows),
        "path_safety_rows": path_safety_rows,
        "unsafe_cleanup_path_rows": unsafe_rows,
        "release_surface_policy_violation_rows": (
            release_surface_policy_violations
        ),
        "destructive_commands_enabled": False,
        "safe_to_auto_apply": False,
        "manual_application_required": bool(cleanup_rows),
        "requires_human_confirmation": bool(cleanup_rows),
        "git_rm_command_preview_only": True,
        "claim_boundary": (
            "This preflight is non-mutating. It only checks owner-approved "
            "cleanup rows before a human manually applies git rm or external "
            "extract-then-remove actions."
        ),
    }


def _owner_review_priority_batches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority_order = [
        ("release_surface", "release_surface_first"),
        ("productization_evidence", "productization_evidence_second"),
        ("script", "script_cleanup_third"),
        ("test", "test_cleanup_fourth"),
        ("implementation_phase1", "implementation_phase1_cleanup_fifth"),
    ]
    known_areas = {area for area, _batch_id in priority_order}
    batches: list[dict[str, Any]] = []
    for priority, (area, batch_id) in enumerate(priority_order, start=1):
        batch_rows = [row for row in rows if row["path_area"] == area]
        if not batch_rows:
            continue
        batches.append(
            {
                "batch_id": batch_id,
                "priority": priority,
                "path_area": area,
                "path_count": len(batch_rows),
                "paths": sorted(row["path"] for row in batch_rows),
                "family_counts": _family_counts(batch_rows),
                "recommended_owner_decision_primary_counts": _counts_by_key(
                    batch_rows,
                    "recommended_owner_decision_primary",
                ),
                "review_goal": (
                    "record owner delete/extract/retain decisions without "
                    "mutating the repository"
                ),
            }
        )
    other_rows = [row for row in rows if row["path_area"] not in known_areas]
    if other_rows:
        batches.append(
            {
                "batch_id": "other_owner_review_last",
                "priority": len(priority_order) + 1,
                "path_area": "other",
                "path_count": len(other_rows),
                "paths": sorted(row["path"] for row in other_rows),
                "family_counts": _family_counts(other_rows),
                "recommended_owner_decision_primary_counts": _counts_by_key(
                    other_rows,
                    "recommended_owner_decision_primary",
                ),
                "review_goal": (
                    "record owner delete/extract/retain decisions without "
                    "mutating the repository"
                ),
            }
        )
    return batches


def _path_area_priority(path_area: str) -> tuple[int, str]:
    priority = {
        "release_surface": 1,
        "productization_evidence": 2,
        "script": 3,
        "test": 4,
        "implementation_phase1": 5,
    }
    return priority.get(path_area, 99), path_area


def _cleanup_priority_batches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["path_area"] or "unknown", []).append(row)
    batches: list[dict[str, Any]] = []
    for path_area in sorted(groups, key=_path_area_priority):
        batch_rows = sorted(groups[path_area], key=lambda item: item["path"])
        batches.append(
            {
                "batch_id": f"{path_area}_cleanup",
                "path_area": path_area,
                "path_count": len(batch_rows),
                "paths": [row["path"] for row in batch_rows],
                "owner_decision_counts": _counts_by_key(
                    batch_rows, "owner_decision"
                ),
                "family_counts": _family_counts(batch_rows),
                "manual_application_required": True,
                "safe_to_auto_apply": False,
                "delete_paths": [
                    row["path"]
                    for row in batch_rows
                    if row["owner_decision"] == "delete_from_structural_repository"
                ],
                "extract_paths": [
                    row["path"]
                    for row in batch_rows
                    if row["owner_decision"]
                    == "extract_to_molecular_or_science_repository"
                ],
                "post_apply_verification": [
                    "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
                    "python3 scripts/build_structural_scope_owner_review_packet.py --write-decision-template",
                    "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions",
                    "python3 scripts/build_product_readiness_snapshot.py --check",
                ],
            }
        )
    for batch in batches:
        batch["delete_git_rm_args"] = _git_rm_args(batch["delete_paths"])
        batch["extract_post_archive_git_rm_args"] = _git_rm_args(
            batch["extract_paths"]
        )
    return batches


def _decision_template_row(row: dict[str, Any], *, index: int, batch_id: str) -> dict[str, Any]:
    recommended = _text(row.get("recommended_owner_decision"))
    post_decision_required_action = (
        "delete_or_extract_path_then_rerun_scope_audit"
        if recommended.startswith(
            (
                "delete_from_structural_repository",
                "extract_to_molecular_or_science_repository",
            )
        )
        else "keep_quarantined_with_signed_owner_exception"
    )
    return {
        "row_id": f"{batch_id}-{index + 1:03d}",
        "path": _text(row.get("path")),
        "path_area": _text(row.get("path_area")),
        "families": [str(item) for item in _as_list(row.get("families"))],
        "matched_tokens": [str(item) for item in _as_list(row.get("matched_tokens"))],
        "current_release_action": _text(row.get("current_release_action")),
        "recommended_owner_decision": recommended,
        "recommended_owner_decision_primary": _text(
            row.get("recommended_owner_decision_primary")
        ),
        "recommended_owner_decision_alternate": _text(
            row.get("recommended_owner_decision_alternate")
        ),
        "allowed_owner_decisions": [
            str(item)
            for item in (
                _as_list(row.get("allowed_owner_decisions"))
                or list(owner_review.ALLOWED_OWNER_DECISIONS)
            )
        ],
        "owner_decision": "",
        "owner_identity": "",
        "owner_role": "",
        "decision_timestamp_utc": "",
        "evidence_reference": "",
        "signed_owner_exception_reference": "",
        "external_archive_reference": "",
        "post_decision_required_action": post_decision_required_action,
    }


def _next_batch_decision_template(
    *,
    pending_owner_decision_rows: list[dict[str, Any]],
    next_batch: dict[str, Any],
) -> dict[str, Any]:
    if not next_batch:
        return {}
    batch_paths = set(str(path) for path in _as_list(next_batch.get("paths")))
    batch_rows = [
        row
        for row in pending_owner_decision_rows
        if row.get("path") in batch_paths
    ]
    batch_id = _text(next_batch.get("batch_id")) or "next_owner_review_batch"
    decision_rows = [
        _decision_template_row(row, index=index, batch_id=batch_id)
        for index, row in enumerate(sorted(batch_rows, key=lambda item: item["path"]))
    ]
    primary_delete_paths = [
        row["path"]
        for row in decision_rows
        if row["recommended_owner_decision_primary"]
        == "delete_from_structural_repository"
    ]
    primary_extract_paths = [
        row["path"]
        for row in decision_rows
        if row["recommended_owner_decision_primary"]
        == "extract_to_molecular_or_science_repository"
    ]
    return {
        "schema_version": owner_review.DECISION_SCHEMA_VERSION,
        "batch_id": batch_id,
        "path_area": _text(next_batch.get("path_area")),
        "decision_pending_count": len(decision_rows),
        "decision_rows": decision_rows,
        "canonical_owner_decisions_path": DEFAULT_OWNER_DECISIONS.as_posix(),
        "generated_template_paths": {
            "json": DEFAULT_NEXT_BATCH_TEMPLATE.as_posix(),
            "csv": DEFAULT_NEXT_BATCH_TEMPLATE_CSV.as_posix(),
            "markdown": DEFAULT_NEXT_BATCH_TEMPLATE_MD.as_posix(),
        },
        "required_owner_fill_fields": [
            "owner_decision",
            "owner_identity",
            "owner_role",
            "decision_timestamp_utc",
            "evidence_reference",
        ],
        "conditional_required_fields": [
            "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository",
            "signed_owner_exception_reference when owner_decision=retain_quarantined_with_signed_owner_exception",
        ],
        "path_specific_restrictions": [
            "retain_quarantined_with_signed_owner_exception is not allowed when path_area=release_surface",
        ],
        "primary_cleanup_preview": {
            "safe_to_auto_apply": False,
            "owner_decision_required": True,
            "primary_delete_path_count": len(primary_delete_paths),
            "primary_delete_paths": primary_delete_paths,
            "primary_delete_git_rm_args": _git_rm_args(primary_delete_paths),
            "primary_extract_path_count": len(primary_extract_paths),
            "primary_extract_paths": primary_extract_paths,
            "primary_extract_post_archive_git_rm_args": _git_rm_args(
                primary_extract_paths
            ),
            "preconditions": [
                "owner fills matching decision rows in structural_scope_owner_decisions.json or CSV",
                "owner_decision_validation_pass=true for these rows",
                "human confirms the batch cleanup scope",
            ],
        },
        "post_batch_verification": [
            "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
            "python3 scripts/build_structural_scope_owner_review_packet.py --write-decision-template",
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions",
            "python3 scripts/build_product_readiness_snapshot.py --check",
        ],
        "claim_boundary": (
            "This is a batch fill-in template and cleanup preview only. It is not "
            "an owner decision, does not delete files, and does not close scope "
            "cleanup without recorded owner evidence and refreshed audits."
        ),
    }


def _release_surface_first_batch_decision_template(
    *,
    rows: list[dict[str, Any]],
    intake: dict[str, Any],
) -> dict[str, Any]:
    release_rows = sorted(
        [row for row in rows if _text(row.get("path_area")) == "release_surface"],
        key=lambda item: _text(item.get("path")),
    )
    if not release_rows:
        return {}
    decision_rows = [
        _decision_template_row(row, index=index, batch_id="release_surface_first")
        for index, row in enumerate(release_rows)
    ]
    primary_delete_paths = [
        row["path"]
        for row in decision_rows
        if row["recommended_owner_decision_primary"]
        == "delete_from_structural_repository"
    ]
    primary_extract_paths = [
        row["path"]
        for row in decision_rows
        if row["recommended_owner_decision_primary"]
        == "extract_to_molecular_or_science_repository"
    ]
    return {
        "schema_version": owner_review.DECISION_SCHEMA_VERSION,
        "batch_id": "release_surface_first",
        "path_area": "release_surface",
        "expected_path_count": len(release_rows),
        "decision_pending_count": int(intake.get("pending_decision_count", 0) or 0),
        "current_intake_status": _text(intake.get("status")),
        "current_intake_blockers": [
            str(item) for item in _as_list(intake.get("blockers"))
        ],
        "decision_rows": decision_rows,
        "canonical_owner_decisions_path": DEFAULT_OWNER_DECISIONS.as_posix(),
        "generated_template_paths": {
            "json": DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE.as_posix(),
            "csv": DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_CSV.as_posix(),
            "markdown": DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_MD.as_posix(),
        },
        "required_owner_fill_fields": [
            "owner_decision",
            "owner_identity",
            "owner_role",
            "decision_timestamp_utc",
            "evidence_reference",
        ],
        "conditional_required_fields": [
            "external_archive_reference when owner_decision=extract_to_molecular_or_science_repository",
        ],
        "path_specific_restrictions": [
            "retain_quarantined_with_signed_owner_exception is not allowed when path_area=release_surface",
        ],
        "primary_cleanup_preview": {
            "safe_to_auto_apply": False,
            "owner_decision_required": True,
            "primary_delete_path_count": len(primary_delete_paths),
            "primary_delete_paths": primary_delete_paths,
            "primary_delete_git_rm_args": _git_rm_args(primary_delete_paths),
            "primary_extract_path_count": len(primary_extract_paths),
            "primary_extract_paths": primary_extract_paths,
            "primary_extract_post_archive_git_rm_args": _git_rm_args(
                primary_extract_paths
            ),
            "preconditions": [
                "owner fills all release_surface_first rows in structural_scope_owner_decisions.json or CSV",
                "owner_decision_validation_pass=true for these release surface rows",
                "human confirms release-surface cleanup scope before any git rm",
            ],
        },
        "post_batch_verification": [
            "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
            "python3 scripts/build_structural_scope_owner_review_packet.py --write-decision-template",
            "python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions",
            "python3 scripts/build_product_readiness_snapshot.py --check",
        ],
        "claim_boundary": (
            "This is a fixed release_surface_first fill-in template and cleanup "
            "preview only. It is not an owner decision, does not delete files, "
            "and cannot close scope cleanup without recorded owner evidence and "
            "a refreshed post-decision structural scope audit."
        ),
    }


def _status_from_packet(packet: dict[str, Any]) -> str:
    if not packet.get("contract_pass"):
        return "blocked_scope_cleanup"
    if packet.get("evidence_closure_pass"):
        return "complete"
    owner_decisions = packet.get("owner_decisions")
    if isinstance(owner_decisions, dict) and owner_decisions.get("blockers"):
        return "owner_decision_evidence_invalid"
    if packet.get("owner_decision_pending_count"):
        return "pending_owner_decisions"
    if packet.get("post_decision_cleanup_pending_count"):
        return "ready_for_cleanup_application"
    return "pending_post_decision_scope_audit"


def _owner_decision_validation_blockers(
    *,
    packet: dict[str, Any],
    owner_decisions: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not packet.get("contract_pass"):
        blockers.append("structural_scope_owner_review_contract_not_pass")
    if not owner_decisions.get("present"):
        blockers.append("owner_decisions_missing")
    if packet.get("owner_decision_pending_count"):
        blockers.append(
            f"owner_decision_pending_count={packet.get('owner_decision_pending_count')}"
        )
    blockers.extend(
        f"owner_decisions::{item}"
        for item in _as_list(owner_decisions.get("blockers"))
    )
    return blockers


def build_application_plan(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    packet = owner_review.build_owner_review_packet(
        repo_root=repo_root,
        audit_path=audit_path,
        quarantine_manifest_path=quarantine_manifest_path,
        owner_decisions_path=owner_decisions_path,
    )
    review_rows = [
        row for row in _as_list(packet.get("review_rows")) if isinstance(row, dict)
    ]
    rows = [_plan_row(row) for row in review_rows]
    status = _status_from_packet(packet)
    owner_decisions = packet.get("owner_decisions") if isinstance(packet.get("owner_decisions"), dict) else {}
    release_surface_first_batch_decision_intake = (
        _release_surface_first_batch_decision_intake(review_rows)
    )
    delete_rows = [row for row in rows if row["owner_decision"] == "delete_from_structural_repository"]
    extract_rows = [row for row in rows if row["owner_decision"] == "extract_to_molecular_or_science_repository"]
    retain_rows = [
        row
        for row in rows
        if row["owner_decision"] == "retain_quarantined_with_signed_owner_exception"
    ]
    closure_blockers = [str(item) for item in _as_list(packet.get("closure_blockers"))]
    owner_decision_validation_blockers = _owner_decision_validation_blockers(
        packet=packet,
        owner_decisions=owner_decisions,
    )
    plan_blockers = [
        *([f"owner_decision_pending_count={packet.get('owner_decision_pending_count')}"] if packet.get("owner_decision_pending_count") else []),
        *([f"post_decision_cleanup_pending_count={packet.get('post_decision_cleanup_pending_count')}"] if packet.get("post_decision_cleanup_pending_count") else []),
        *[str(item) for item in _as_list(packet.get("blockers"))],
        *[f"owner_decisions::{item}" for item in _as_list(owner_decisions.get("blockers"))],
    ]
    cleanup_rows = [
        row for row in rows if row["post_decision_cleanup_pending"] is True
    ]
    cleanup_application_preflight = _cleanup_application_preflight(cleanup_rows)
    cleanup_priority_batches = _cleanup_priority_batches(cleanup_rows)
    next_cleanup_application_batch = (
        cleanup_priority_batches[0] if cleanup_priority_batches else {}
    )
    pending_owner_decision_rows = [
        row for row in rows if row["owner_decision_valid"] is False
    ]
    owner_review_priority_batches = _owner_review_priority_batches(
        pending_owner_decision_rows
    )
    next_owner_review_batch = (
        owner_review_priority_batches[0] if owner_review_priority_batches else {}
    )
    next_owner_review_batch_decision_template = _next_batch_decision_template(
        pending_owner_decision_rows=pending_owner_decision_rows,
        next_batch=next_owner_review_batch,
    )
    release_surface_first_batch_decision_template = (
        _release_surface_first_batch_decision_template(
            rows=rows,
            intake=release_surface_first_batch_decision_intake,
        )
    )
    application_blockers = _deduped(
        [
            *owner_decision_validation_blockers,
            *plan_blockers,
            *closure_blockers,
        ]
    )
    summary_line = (
        "Structural scope owner decision application plan: "
        f"{status.upper()} | recorded={int(packet.get('owner_decision_recorded_count', 0) or 0)} | "
        f"pending={int(packet.get('owner_decision_pending_count', 0) or 0)} | "
        f"cleanup_pending={int(packet.get('post_decision_cleanup_pending_count', 0) or 0)} | "
        f"delete={len(delete_rows)} | extract={len(extract_rows)} | "
        f"retain={len(retain_rows)} | "
        f"unquarantined={int(packet.get('unquarantined_non_structural_path_count', 0) or 0)}"
    )
    suggested_sequence = [
        "fill structural_scope_owner_decisions.json or a CSV owner-decisions file from the generated owner decision templates",
        "when using CSV, pass it with --owner-decisions <filled-owner-decisions.csv>",
        "rerun this application plan",
        "for delete decisions, remove paths from this structural repository after owner confirmation",
        "for extract decisions, preserve history/evidence externally before removing paths here",
        "rerun structural scope audit and owner review packet",
        "refresh product readiness snapshot",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_structural_scope_owner_decision_application_plan.py"),
                Path("scripts/build_structural_scope_owner_review_packet.py"),
                audit_path,
                quarantine_manifest_path,
                owner_decisions_path,
            ],
            reused_evidence=False,
            reuse_policy="structural_scope_owner_decision_application_plan_from_owner_review_packet",
            repo_root=repo_root,
        ),
        "status": status,
        "summary_line": summary_line,
        "contract_pass": bool(packet.get("contract_pass") and not _as_list(owner_decisions.get("blockers"))),
        "application_ready": status == "ready_for_cleanup_application",
        "evidence_closure_pass": bool(packet.get("evidence_closure_pass")),
        "owner_decision_validation_pass": not owner_decision_validation_blockers,
        "owner_decision_validation_blockers": owner_decision_validation_blockers,
        "owner_decisions_path": owner_decisions_path.as_posix(),
        "owner_decision_template_paths": {
            "json": owner_review.DEFAULT_OWNER_DECISION_TEMPLATE.as_posix(),
            "csv": owner_review.DEFAULT_OWNER_DECISION_TEMPLATE_CSV.as_posix(),
            "markdown": owner_review.DEFAULT_OWNER_DECISION_TEMPLATE_MD.as_posix(),
        },
        "owner_decisions_present": bool(owner_decisions.get("present")),
        "owner_decision_recorded_count": int(packet.get("owner_decision_recorded_count", 0) or 0),
        "owner_decision_pending_count": int(packet.get("owner_decision_pending_count", 0) or 0),
        "post_decision_cleanup_pending_count": int(
            packet.get("post_decision_cleanup_pending_count", 0) or 0
        ),
        "post_decision_cleanup_applied_count": int(
            packet.get("post_decision_cleanup_applied_count", 0) or 0
        ),
        "delete_decision_count": len(delete_rows),
        "extract_decision_count": len(extract_rows),
        "retain_quarantined_exception_count": len(retain_rows),
        "delete_path_count": len(delete_rows),
        "extract_path_count": len(extract_rows),
        "retain_quarantined_exception_path_count": len(retain_rows),
        "quarantined_path_count": int(packet.get("quarantined_path_count", 0) or 0),
        "release_surface_excluded_path_count": int(
            packet.get("release_surface_excluded_path_count", 0) or 0
        ),
        "unquarantined_non_structural_path_count": int(
            packet.get("unquarantined_non_structural_path_count", 0) or 0
        ),
        "closure_blockers": closure_blockers,
        "plan_blockers": plan_blockers,
        "application_blockers": application_blockers,
        "blockers": plan_blockers,
        "next_actions": [] if packet.get("evidence_closure_pass") else suggested_sequence,
        "pending_owner_decision_path_area_counts": _counts_by_key(
            pending_owner_decision_rows, "path_area"
        ),
        "pending_owner_decision_family_counts": _family_counts(
            pending_owner_decision_rows
        ),
        "pending_owner_decision_recommended_owner_decision_counts": _counts_by_key(
            pending_owner_decision_rows, "recommended_owner_decision"
        ),
        "pending_owner_decision_primary_counts": _counts_by_key(
            pending_owner_decision_rows, "recommended_owner_decision_primary"
        ),
        "owner_review_priority_batches": owner_review_priority_batches,
        "next_owner_review_batch": next_owner_review_batch,
        "next_owner_review_batch_decision_template": (
            next_owner_review_batch_decision_template
        ),
        "release_surface_owner_decision_required_count": sum(
            1 for row in pending_owner_decision_rows if row["path_area"] == "release_surface"
        ),
        "release_surface_owner_decision_required_paths": [
            row["path"]
            for row in pending_owner_decision_rows
            if row["path_area"] == "release_surface"
        ],
        "release_surface_first_batch_decision_intake": (
            release_surface_first_batch_decision_intake
        ),
        "release_surface_first_batch_ready": bool(
            release_surface_first_batch_decision_intake.get(
                "ready_for_manual_cleanup_application"
            )
        ),
        "release_surface_first_batch_blockers": [
            str(item)
            for item in _as_list(
                release_surface_first_batch_decision_intake.get("blockers")
            )
        ],
        "release_surface_first_batch_decision_template": (
            release_surface_first_batch_decision_template
        ),
        "release_surface_first_batch_template_paths": _as_dict(
            release_surface_first_batch_decision_template.get(
                "generated_template_paths"
            )
        ),
        "cleanup_required_count": len(cleanup_rows),
        "cleanup_application_preflight": cleanup_application_preflight,
        "cleanup_application_preflight_ready": bool(
            cleanup_application_preflight.get("ready")
        ),
        "cleanup_application_preflight_blockers": [
            str(item)
            for item in _as_list(cleanup_application_preflight.get("blockers"))
        ],
        "cleanup_path_area_counts": _counts_by_key(cleanup_rows, "path_area"),
        "cleanup_family_counts": _family_counts(cleanup_rows),
        "release_surface_cleanup_required_count": sum(
            1 for row in cleanup_rows if row["path_area"] == "release_surface"
        ),
        "release_surface_cleanup_paths": [
            row["path"] for row in cleanup_rows if row["path_area"] == "release_surface"
        ],
        "cleanup_command_manifest": _cleanup_command_manifest(cleanup_rows),
        "cleanup_priority_batches": cleanup_priority_batches,
        "next_cleanup_application_batch": next_cleanup_application_batch,
        "release_surface_batch_cleanup_ready": any(
            batch.get("path_area") == "release_surface"
            for batch in cleanup_priority_batches
        ),
        "partial_cleanup_ready": bool(cleanup_priority_batches),
        "cleanup_rows": cleanup_rows,
        "post_decision_cleanup_applied_rows": [
            row
            for row in _as_list(packet.get("post_decision_cleanup_applied_rows"))
            if isinstance(row, dict)
        ],
        "retain_exception_rows": retain_rows,
        "pending_owner_decision_rows": pending_owner_decision_rows,
        "suggested_sequence": suggested_sequence,
        "claim_boundary": (
            "This application plan is non-mutating. It never deletes or extracts "
            "files. It only classifies owner decisions into manual follow-up "
            "actions and keeps quarantined non-structural artifacts outside the "
            "building structural-analysis release surface until owner evidence "
            "and post-decision scope audit closure are present."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Owner Decision Application Plan",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `application_ready`: `{payload['application_ready']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `owner_decision_validation_pass`: `{payload['owner_decision_validation_pass']}`",
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        f"- `post_decision_cleanup_pending_count`: `{payload['post_decision_cleanup_pending_count']}`",
        f"- `post_decision_cleanup_applied_count`: `{payload['post_decision_cleanup_applied_count']}`",
        f"- `cleanup_required_count`: `{payload['cleanup_required_count']}`",
        f"- `release_surface_cleanup_required_count`: `{payload['release_surface_cleanup_required_count']}`",
        f"- `delete_decision_count`: `{payload['delete_decision_count']}`",
        f"- `extract_decision_count`: `{payload['extract_decision_count']}`",
        f"- `retain_quarantined_exception_count`: `{payload['retain_quarantined_exception_count']}`",
        f"- `release_surface_owner_decision_required_count`: `{payload['release_surface_owner_decision_required_count']}`",
        "",
    ]
    lines.extend(["## Pending Owner Decision Buckets", ""])
    lines.append(
        "- `pending_owner_decision_path_area_counts`: "
        f"`{payload['pending_owner_decision_path_area_counts']}`"
    )
    lines.append(
        "- `pending_owner_decision_family_counts`: "
        f"`{payload['pending_owner_decision_family_counts']}`"
    )
    lines.append(
        "- `pending_owner_decision_recommended_owner_decision_counts`: "
        f"`{payload['pending_owner_decision_recommended_owner_decision_counts']}`"
    )
    lines.append(
        "- `pending_owner_decision_primary_counts`: "
        f"`{payload['pending_owner_decision_primary_counts']}`"
    )
    next_batch = payload.get("next_owner_review_batch")
    next_batch = next_batch if isinstance(next_batch, dict) else {}
    if next_batch:
        lines.append(
            "- `next_owner_review_batch`: "
            f"`{next_batch.get('batch_id')}` "
            f"paths=`{next_batch.get('path_count')}` "
            f"area=`{next_batch.get('path_area')}`"
        )
    if payload.get("owner_review_priority_batches"):
        lines.append(
            "- `owner_review_priority_batches`: "
            f"`{len(payload['owner_review_priority_batches'])}`"
        )
    lines.append("")
    intake = payload.get("release_surface_first_batch_decision_intake")
    intake = intake if isinstance(intake, dict) else {}
    if intake:
        lines.extend(["## Release Surface First Batch Intake", ""])
        lines.append(f"- `status`: `{intake.get('status')}`")
        lines.append(
            "- `ready_for_manual_cleanup_application`: "
            f"`{intake.get('ready_for_manual_cleanup_application')}`"
        )
        lines.append(
            "- `expected_path_count`: "
            f"`{intake.get('expected_path_count', 0)}`"
        )
        lines.append(
            "- `valid_cleanup_decision_count`: "
            f"`{intake.get('valid_cleanup_decision_count', 0)}`"
        )
        lines.append(
            "- `pending_decision_count`: "
            f"`{intake.get('pending_decision_count', 0)}`"
        )
        if intake.get("blockers"):
            lines.extend(f"- `{item}`" for item in intake["blockers"])
        else:
            lines.append("- blockers: none")
        template_paths = payload.get("release_surface_first_batch_template_paths")
        template_paths = template_paths if isinstance(template_paths, dict) else {}
        if template_paths:
            lines.append(
                "- `release_surface_first_batch_template.csv`: "
                f"`{template_paths.get('csv')}`"
            )
        lines.append("")
    next_batch_template = payload.get("next_owner_review_batch_decision_template")
    next_batch_template = (
        next_batch_template if isinstance(next_batch_template, dict) else {}
    )
    if next_batch_template:
        lines.extend(["## Next Batch Decision Template", ""])
        lines.append(
            "- `batch_id`: "
            f"`{next_batch_template.get('batch_id')}`"
        )
        lines.append(
            "- `decision_pending_count`: "
            f"`{next_batch_template.get('decision_pending_count')}`"
        )
        preview = next_batch_template.get("primary_cleanup_preview")
        preview = preview if isinstance(preview, dict) else {}
        lines.append(
            "- `primary_delete_path_count`: "
            f"`{preview.get('primary_delete_path_count', 0)}`"
        )
        lines.extend(["", "| Row | Path | Primary Decision |", "|---|---|---|"])
        for row in next_batch_template.get("decision_rows", []):
            lines.append(
                "| "
                f"`{row['row_id']}` | "
                f"`{row['path']}` | "
                f"`{row['recommended_owner_decision_primary']}` |"
            )
        lines.append("")
    if payload["owner_decision_validation_blockers"]:
        lines.extend(["## Owner Decision Validation Blockers", ""])
        lines.extend(
            f"- `{item}`" for item in payload["owner_decision_validation_blockers"]
        )
        lines.append("")
    lines.extend(["## Plan Blockers", ""])
    if payload["plan_blockers"]:
        lines.extend(f"- `{item}`" for item in payload["plan_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Cleanup Rows", "", "| Path | Decision | Required Action |", "|---|---|---|"])
    for row in payload["cleanup_rows"]:
        lines.append(
            f"| `{row['path']}` | `{row['owner_decision']}` | `{row['required_action']}` |"
        )
    lines.extend(["", "## Cleanup Command Manifest", ""])
    manifest = payload["cleanup_command_manifest"]
    lines.append(f"- `safe_to_auto_apply`: `{manifest['safe_to_auto_apply']}`")
    lines.append(
        f"- `manual_application_required`: `{manifest['manual_application_required']}`"
    )
    lines.append(
        "- `delete_from_structural_repository.path_count`: "
        f"`{manifest['delete_from_structural_repository']['path_count']}`"
    )
    lines.append(
        "- `extract_to_molecular_or_science_repository.path_count`: "
        f"`{manifest['extract_to_molecular_or_science_repository']['path_count']}`"
    )
    preflight = payload.get("cleanup_application_preflight")
    preflight = preflight if isinstance(preflight, dict) else {}
    lines.extend(["", "## Cleanup Application Preflight", ""])
    lines.append(f"- `status`: `{preflight.get('status')}`")
    lines.append(f"- `ready`: `{preflight.get('ready')}`")
    lines.append(
        f"- `destructive_commands_enabled`: `{preflight.get('destructive_commands_enabled')}`"
    )
    lines.append(
        f"- `safe_to_auto_apply`: `{preflight.get('safe_to_auto_apply')}`"
    )
    if preflight.get("blockers"):
        lines.extend(f"- `{item}`" for item in preflight["blockers"])
    else:
        lines.append("- blockers: none")
    if payload.get("cleanup_priority_batches"):
        lines.extend(["", "## Cleanup Priority Batches", ""])
        lines.extend(
            [
                "| Batch | Area | Paths | Delete | Extract |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for batch in payload["cleanup_priority_batches"]:
            lines.append(
                "| "
                f"`{batch['batch_id']}` | "
                f"`{batch['path_area']}` | "
                f"{batch['path_count']} | "
                f"{len(batch['delete_paths'])} | "
                f"{len(batch['extract_paths'])} |"
            )
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def _next_batch_template_markdown(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    lines = [
        "# Structural Scope Next Batch Owner Decision Template",
        "",
        f"- `batch_id`: `{payload['batch_id']}`",
        f"- `path_area`: `{payload['path_area']}`",
        f"- `decision_pending_count`: `{payload['decision_pending_count']}`",
        (
            "- `external_archive_reference`: required when `owner_decision` is "
            "`extract_to_molecular_or_science_repository`"
        ),
        (
            "- `signed_owner_exception_reference`: required when `owner_decision` "
            "is `retain_quarantined_with_signed_owner_exception`"
        ),
        "",
        "## Path-Specific Restrictions",
        "",
    ]
    restrictions = [
        str(item) for item in _as_list(payload.get("path_specific_restrictions"))
    ]
    if restrictions:
        lines.extend(f"- `{item}`" for item in restrictions)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Decision Rows",
            "",
        ]
    )
    lines.extend(
        [
            "| Row | Path | Primary Decision | Alternate Decision |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["decision_rows"]:
        lines.append(
            "| "
            f"`{row['row_id']}` | "
            f"`{row['path']}` | "
            f"`{row['recommended_owner_decision_primary']}` | "
            f"`{row['recommended_owner_decision_alternate']}` |"
        )
    preview = payload.get("primary_cleanup_preview")
    preview = preview if isinstance(preview, dict) else {}
    lines.extend(
        [
            "",
            "## Primary Cleanup Preview",
            "",
            f"- `safe_to_auto_apply`: `{preview.get('safe_to_auto_apply')}`",
            f"- `primary_delete_path_count`: `{preview.get('primary_delete_path_count', 0)}`",
            f"- `primary_extract_path_count`: `{preview.get('primary_extract_path_count', 0)}`",
            "",
            "## Claim Boundary",
            "",
            str(payload["claim_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def _release_surface_first_batch_template_markdown(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    lines = [
        "# Structural Scope Release Surface First Batch Owner Decision Template",
        "",
        f"- `batch_id`: `{payload['batch_id']}`",
        f"- `path_area`: `{payload['path_area']}`",
        f"- `expected_path_count`: `{payload['expected_path_count']}`",
        f"- `decision_pending_count`: `{payload['decision_pending_count']}`",
        f"- `current_intake_status`: `{payload['current_intake_status']}`",
        (
            "- `external_archive_reference`: required when `owner_decision` is "
            "`extract_to_molecular_or_science_repository`"
        ),
        "",
        "## Path-Specific Restrictions",
        "",
    ]
    restrictions = [
        str(item) for item in _as_list(payload.get("path_specific_restrictions"))
    ]
    if restrictions:
        lines.extend(f"- `{item}`" for item in restrictions)
    else:
        lines.append("- none")
    blockers = [str(item) for item in _as_list(payload.get("current_intake_blockers"))]
    lines.extend(["", "## Current Intake Blockers", ""])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Decision Rows", ""])
    lines.extend(
        [
            "| Row | Path | Primary Decision | Alternate Decision |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["decision_rows"]:
        lines.append(
            "| "
            f"`{row['row_id']}` | "
            f"`{row['path']}` | "
            f"`{row['recommended_owner_decision_primary']}` | "
            f"`{row['recommended_owner_decision_alternate']}` |"
        )
    preview = payload.get("primary_cleanup_preview")
    preview = preview if isinstance(preview, dict) else {}
    lines.extend(
        [
            "",
            "## Primary Cleanup Preview",
            "",
            f"- `safe_to_auto_apply`: `{preview.get('safe_to_auto_apply')}`",
            f"- `primary_delete_path_count`: `{preview.get('primary_delete_path_count', 0)}`",
            f"- `primary_extract_path_count`: `{preview.get('primary_extract_path_count', 0)}`",
            "",
            "## Claim Boundary",
            "",
            str(payload["claim_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def write_application_plan(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    next_batch_template_out: Path = DEFAULT_NEXT_BATCH_TEMPLATE,
    next_batch_template_out_md: Path = DEFAULT_NEXT_BATCH_TEMPLATE_MD,
    next_batch_template_out_csv: Path = DEFAULT_NEXT_BATCH_TEMPLATE_CSV,
    release_surface_first_batch_template_out: Path = (
        DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE
    ),
    release_surface_first_batch_template_out_md: Path = (
        DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_MD
    ),
    release_surface_first_batch_template_out_csv: Path = (
        DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_CSV
    ),
) -> dict[str, Any]:
    payload = build_application_plan(
        repo_root=repo_root,
        audit_path=audit_path,
        quarantine_manifest_path=quarantine_manifest_path,
        owner_decisions_path=owner_decisions_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    next_batch_template = payload.get("next_owner_review_batch_decision_template")
    next_batch_template = (
        next_batch_template if isinstance(next_batch_template, dict) else {}
    )
    if next_batch_template:
        resolved_next = _resolve(repo_root, next_batch_template_out)
        resolved_next_md = _resolve(repo_root, next_batch_template_out_md)
        resolved_next_csv = _resolve(repo_root, next_batch_template_out_csv)
        resolved_next.parent.mkdir(parents=True, exist_ok=True)
        resolved_next.write_text(_json_text(next_batch_template), encoding="utf-8")
        resolved_next_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_next_md.write_text(
            _next_batch_template_markdown(next_batch_template),
            encoding="utf-8",
        )
        resolved_next_csv.parent.mkdir(parents=True, exist_ok=True)
        resolved_next_csv.write_text(
            _csv_text(next_batch_template["decision_rows"]),
            encoding="utf-8",
        )
    release_surface_first_template = payload.get(
        "release_surface_first_batch_decision_template"
    )
    release_surface_first_template = (
        release_surface_first_template
        if isinstance(release_surface_first_template, dict)
        else {}
    )
    if release_surface_first_template:
        resolved_release_surface = _resolve(
            repo_root,
            release_surface_first_batch_template_out,
        )
        resolved_release_surface_md = _resolve(
            repo_root,
            release_surface_first_batch_template_out_md,
        )
        resolved_release_surface_csv = _resolve(
            repo_root,
            release_surface_first_batch_template_out_csv,
        )
        resolved_release_surface.parent.mkdir(parents=True, exist_ok=True)
        resolved_release_surface.write_text(
            _json_text(release_surface_first_template),
            encoding="utf-8",
        )
        resolved_release_surface_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_release_surface_md.write_text(
            _release_surface_first_batch_template_markdown(
                release_surface_first_template
            ),
            encoding="utf-8",
        )
        resolved_release_surface_csv.parent.mkdir(parents=True, exist_ok=True)
        resolved_release_surface_csv.write_text(
            _csv_text(release_surface_first_template["decision_rows"]),
            encoding="utf-8",
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--quarantine-manifest", type=Path, default=DEFAULT_QUARANTINE_MANIFEST)
    parser.add_argument("--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument(
        "--next-batch-template-out",
        type=Path,
        default=DEFAULT_NEXT_BATCH_TEMPLATE,
    )
    parser.add_argument(
        "--next-batch-template-out-md",
        type=Path,
        default=DEFAULT_NEXT_BATCH_TEMPLATE_MD,
    )
    parser.add_argument(
        "--next-batch-template-out-csv",
        type=Path,
        default=DEFAULT_NEXT_BATCH_TEMPLATE_CSV,
    )
    parser.add_argument(
        "--release-surface-first-batch-template-out",
        type=Path,
        default=DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE,
    )
    parser.add_argument(
        "--release-surface-first-batch-template-out-md",
        type=Path,
        default=DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_MD,
    )
    parser.add_argument(
        "--release-surface-first-batch-template-out-csv",
        type=Path,
        default=DEFAULT_RELEASE_SURFACE_FIRST_BATCH_TEMPLATE_CSV,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--fail-invalid-owner-decisions",
        action="store_true",
        help=(
            "Exit non-zero when owner decisions are missing, incomplete, "
            "schema-invalid, duplicated, or reference paths outside quarantine. "
            "A valid delete/extract decision file may still leave cleanup pending."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_application_plan(
        repo_root=args.repo_root,
        audit_path=args.audit,
        quarantine_manifest_path=args.quarantine_manifest,
        owner_decisions_path=args.owner_decisions,
        out=args.out,
        out_md=args.out_md,
        next_batch_template_out=args.next_batch_template_out,
        next_batch_template_out_md=args.next_batch_template_out_md,
        next_batch_template_out_csv=args.next_batch_template_out_csv,
        release_surface_first_batch_template_out=(
            args.release_surface_first_batch_template_out
        ),
        release_surface_first_batch_template_out_md=(
            args.release_surface_first_batch_template_out_md
        ),
        release_surface_first_batch_template_out_csv=(
            args.release_surface_first_batch_template_out_csv
        ),
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Structural scope owner decision application plan: "
            f"{payload['status']} | pending={payload['owner_decision_pending_count']} | "
            f"cleanup_pending={payload['post_decision_cleanup_pending_count']}"
        )
    if args.fail_invalid_owner_decisions and not payload[
        "owner_decision_validation_pass"
    ]:
        return 1
    return 1 if args.fail_blocked and not payload["evidence_closure_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
