#!/usr/bin/env python3
"""Build owner-review handoff for quarantined non-structural scope paths."""

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

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-owner-review-packet.v1"
DECISION_SCHEMA_VERSION = "structural-scope-owner-decisions.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "structural_scope_contamination_audit.json"
DEFAULT_QUARANTINE_MANIFEST = PRODUCTIZATION / "structural_scope_quarantine_manifest.json"
DEFAULT_OWNER_DECISIONS = PRODUCTIZATION / "structural_scope_owner_decisions.json"
DEFAULT_OWNER_DECISION_TEMPLATE = (
    PRODUCTIZATION / "structural_scope_owner_decisions.template.json"
)
DEFAULT_OWNER_DECISION_TEMPLATE_MD = DEFAULT_OWNER_DECISION_TEMPLATE.with_suffix(".md")
DEFAULT_OWNER_DECISION_TEMPLATE_CSV = DEFAULT_OWNER_DECISION_TEMPLATE.with_suffix(".csv")
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_owner_review_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
ALLOWED_OWNER_DECISIONS = (
    "delete_from_structural_repository",
    "extract_to_molecular_or_science_repository",
    "retain_quarantined_with_signed_owner_exception",
)
REQUIRED_CLOSURE_EVIDENCE = (
    "owner_identity_and_role",
    "decision_timestamp_utc",
    "per_path_decision",
    "evidence_reference",
    "post_decision_structural_scope_audit",
)
OWNER_DECISION_COLUMNS = (
    "row_id",
    "path",
    "path_area",
    "families",
    "matched_tokens",
    "recommended_owner_decision",
    "recommended_owner_decision_primary",
    "recommended_owner_decision_alternate",
    "owner_decision",
    "owner_identity",
    "owner_role",
    "decision_timestamp_utc",
    "evidence_reference",
)
OWNER_DECISION_REQUIRED_COLUMNS = (
    "path",
    "owner_decision",
    "owner_identity",
    "owner_role",
    "decision_timestamp_utc",
    "evidence_reference",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_owner_decisions(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    if resolved.suffix.lower() != ".csv":
        return _load_json(repo_root, path)

    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    blockers = [
        f"owner_decisions_csv_column_missing:{column}"
        for column in OWNER_DECISION_REQUIRED_COLUMNS
        if column not in columns
    ]
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "decision_format": "csv",
        "decision_columns": columns,
        "decision_rows": rows,
        "blockers": blockers,
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        families = [str(item) for item in _as_list(row.get("families")) if str(item)]
        if not families:
            families = ["unknown"]
        for family in families:
            counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _recommended_decision(row: dict[str, Any]) -> str:
    area = str(row.get("path_area", ""))
    if area in {"release_surface", "productization_evidence"}:
        return "delete_from_structural_repository_or_extract_only_if_owner_requires_history"
    if area in {"script", "test", "implementation_phase1"}:
        return "extract_to_molecular_or_science_repository_or_delete_if_obsolete"
    return "owner_decision_required"


def _recommended_owner_decision_primary(row: dict[str, Any]) -> str:
    area = str(row.get("path_area", ""))
    if area in {"release_surface", "productization_evidence"}:
        return "delete_from_structural_repository"
    if area in {"script", "test", "implementation_phase1"}:
        return "extract_to_molecular_or_science_repository"
    return ""


def _recommended_owner_decision_alternate(row: dict[str, Any]) -> str:
    area = str(row.get("path_area", ""))
    if area in {"release_surface", "productization_evidence"}:
        return "extract_to_molecular_or_science_repository"
    if area in {"script", "test", "implementation_phase1"}:
        return "delete_from_structural_repository"
    return "retain_quarantined_with_signed_owner_exception"


def _review_row(row: dict[str, Any], *, manifest_paths: set[str]) -> dict[str, Any]:
    path = str(row.get("path", ""))
    quarantined = str(row.get("quarantine_status", "")) == "quarantined"
    release_excluded = bool(row.get("excluded_from_structural_release_surface")) and path in manifest_paths
    return {
        "path": path,
        "git_state": str(row.get("git_state", "")),
        "path_area": str(row.get("path_area", "")),
        "families": [str(item) for item in _as_list(row.get("families"))],
        "matched_tokens": [str(item) for item in _as_list(row.get("matched_tokens"))],
        "quarantine_status": str(row.get("quarantine_status", "")),
        "manifest_path_present": path in manifest_paths,
        "excluded_from_structural_release_surface": release_excluded,
        "structural_release_surface_status": (
            "excluded_quarantined_legacy_artifact"
            if quarantined and release_excluded
            else "not_excluded_from_structural_release_surface"
        ),
        "structural_release_claim_eligible": False,
        "owner_review_state": "pending_owner_decision",
        "owner_decision_required": True,
        "allowed_owner_decisions": list(ALLOWED_OWNER_DECISIONS),
        "recommended_owner_decision": _recommended_decision(row),
        "recommended_owner_decision_primary": _recommended_owner_decision_primary(row),
        "recommended_owner_decision_alternate": _recommended_owner_decision_alternate(row),
        "current_release_action": "keep_quarantined_until_owner_delete_or_extract_decision",
        "closure_evidence_required": list(REQUIRED_CLOSURE_EVIDENCE),
    }


def _manifest_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for row in _as_list(manifest.get("paths")):
        if isinstance(row, dict) and str(row.get("path", "")).strip():
            paths.add(str(row["path"]))
    return paths


def _group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        families = [str(item) for item in _as_list(row.get("families")) if str(item)]
        family = "+".join(families) if families else "unknown"
        area = str(row.get("path_area", "") or "unknown")
        key = (family, area)
        group = groups.setdefault(
            key,
            {
                "family": family,
                "path_area": area,
                "path_count": 0,
                "paths": [],
                "recommended_owner_decision": _recommended_decision(row),
            },
        )
        group["path_count"] += 1
        group["paths"].append(str(row.get("path", "")))
    return [groups[key] for key in sorted(groups)]


def _decision_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("decision_rows")
    if not isinstance(rows, list):
        rows = payload.get("owner_decision_rows")
    return [row for row in _as_list(rows) if isinstance(row, dict)]


def _decision_row_by_path(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows_by_path: dict[str, dict[str, Any]] = {}
    for row in _decision_rows(payload):
        path = _text(row.get("path"))
        if path and path not in rows_by_path:
            rows_by_path[path] = row
    return rows_by_path


def _duplicate_decision_paths(payload: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in _decision_rows(payload):
        path = _text(row.get("path"))
        if not path:
            continue
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    return sorted(duplicates)


def _csv_text(rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(OWNER_DECISION_COLUMNS),
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
                for column in OWNER_DECISION_COLUMNS
            }
        )
    return output.getvalue()


def _owner_decision_overlay(
    review_row: dict[str, Any],
    decision_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not decision_row:
        return {
            "owner_decision": "",
            "owner_decision_valid": False,
            "owner_review_state": "pending_owner_decision",
            "owner_decision_required": True,
            "owner_decision_missing_requirements": list(REQUIRED_CLOSURE_EVIDENCE),
            "decision_evidence_reference": "",
            "post_decision_cleanup_required": False,
            "post_decision_cleanup_pending": False,
        }

    owner_decision = _text(decision_row.get("owner_decision"))
    owner_identity = _text(decision_row.get("owner_identity"))
    owner_role = _text(decision_row.get("owner_role"))
    decision_timestamp_utc = _text(decision_row.get("decision_timestamp_utc"))
    evidence_reference = _text(decision_row.get("evidence_reference"))
    missing: list[str] = []
    if owner_decision not in ALLOWED_OWNER_DECISIONS:
        missing.append("per_path_decision")
    if not owner_identity:
        missing.append("owner_identity")
    if not owner_role:
        missing.append("owner_role")
    if not decision_timestamp_utc:
        missing.append("decision_timestamp_utc")
    if not evidence_reference:
        missing.append("evidence_reference")
    valid = not missing
    cleanup_required = owner_decision in {
        "delete_from_structural_repository",
        "extract_to_molecular_or_science_repository",
    }
    cleanup_pending = bool(valid and cleanup_required)
    if not valid:
        state = "owner_decision_incomplete"
    elif cleanup_pending:
        state = "owner_decision_recorded_post_decision_cleanup_pending"
    else:
        state = "owner_decision_recorded_retained_quarantined_signed_exception"
    return {
        "owner_decision": owner_decision,
        "owner_decision_valid": valid,
        "owner_review_state": state,
        "owner_decision_required": not valid,
        "owner_decision_missing_requirements": missing,
        "owner_identity": owner_identity,
        "owner_role": owner_role,
        "decision_timestamp_utc": decision_timestamp_utc,
        "decision_evidence_reference": evidence_reference,
        "post_decision_cleanup_required": cleanup_required,
        "post_decision_cleanup_pending": cleanup_pending,
    }


def build_owner_decision_template(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    packet = _load_json(repo_root, owner_review_packet_path)
    review_rows = [
        row for row in _as_list(packet.get("review_rows")) if isinstance(row, dict)
    ]
    blockers: list[str] = []
    if not packet:
        blockers.append("structural_scope_owner_review_packet_missing")
    if packet and not packet.get("contract_pass"):
        blockers.append("structural_scope_owner_review_packet_not_contract_pass")
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_structural_scope_owner_review_packet.py"),
                owner_review_packet_path,
            ],
            reused_evidence=False,
            reuse_policy="structural_scope_owner_decision_template_from_review_packet",
            repo_root=repo_root,
        ),
        "status": "pending_owner_decisions" if review_rows else "complete_no_paths",
        "contract_pass": bool(packet and packet.get("contract_pass") and not blockers),
        "evidence_closure_pass": False,
        "owner_decision_required_count": len(review_rows),
        "decision_recorded_count": 0,
        "decision_pending_count": len(review_rows),
        "allowed_owner_decisions": list(ALLOWED_OWNER_DECISIONS),
        "required_closure_evidence": list(REQUIRED_CLOSURE_EVIDENCE),
        "blockers": blockers,
        "decision_rows": [
            {
                "row_id": f"structural-scope-owner-{index + 1:03d}",
                "path": _text(row.get("path")),
                "path_area": _text(row.get("path_area")),
                "families": [str(item) for item in _as_list(row.get("families"))],
                "matched_tokens": [
                    str(item) for item in _as_list(row.get("matched_tokens"))
                ],
                "current_release_action": _text(row.get("current_release_action")),
                "recommended_owner_decision": _text(
                    row.get("recommended_owner_decision")
                ),
                "recommended_owner_decision_primary": _text(
                    row.get("recommended_owner_decision_primary")
                ),
                "recommended_owner_decision_alternate": _text(
                    row.get("recommended_owner_decision_alternate")
                ),
                "allowed_owner_decisions": list(ALLOWED_OWNER_DECISIONS),
                "owner_decision": "",
                "owner_identity": "",
                "owner_role": "",
                "decision_timestamp_utc": "",
                "evidence_reference": "",
                "post_decision_required_action": (
                    "delete_or_extract_path_then_rerun_scope_audit"
                    if _text(row.get("recommended_owner_decision")).startswith(
                        (
                            "delete_from_structural_repository",
                            "extract_to_molecular_or_science_repository",
                        )
                    )
                    else "keep_quarantined_with_signed_owner_exception"
                ),
            }
            for index, row in enumerate(review_rows)
        ],
        "claim_boundary": (
            "This is a fill-in owner decision template. It is not approval, "
            "does not delete files, and does not close structural scope cleanup "
            "until every row has an allowed owner_decision, owner identity/role, "
            "decision timestamp, evidence reference, and any delete/extract "
            "decision has been applied and followed by a refreshed structural "
            "scope audit."
        ),
    }


def build_owner_review_packet(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit = _load_json(repo_root, audit_path)
    manifest = _load_json(repo_root, quarantine_manifest_path)
    owner_decisions_resolved = _resolve(repo_root, owner_decisions_path)
    owner_decisions = _load_owner_decisions(repo_root, owner_decisions_path)
    owner_decisions_present = owner_decisions_resolved.exists()
    owner_decision_by_path = _decision_row_by_path(owner_decisions)
    duplicate_decision_paths = _duplicate_decision_paths(owner_decisions)
    manifest_paths = _manifest_paths(manifest)
    rows = [
        row
        for row in _as_list(audit.get("quarantined_non_structural_rows"))
        if isinstance(row, dict)
    ]
    review_rows = []
    for row in rows:
        review_row = _review_row(row, manifest_paths=manifest_paths)
        review_row.update(
            _owner_decision_overlay(
                review_row,
                owner_decision_by_path.get(review_row["path"]),
            )
        )
        review_rows.append(review_row)
    unquarantined_rows = [
        row
        for row in _as_list(audit.get("unquarantined_non_structural_rows"))
        if isinstance(row, dict)
    ]
    release_excluded_count = sum(
        1 for row in review_rows if row["excluded_from_structural_release_surface"]
    )
    pending_count = len(review_rows)
    blockers = [str(item) for item in _as_list(audit.get("blockers")) if str(item)]
    if not audit:
        blockers.append("structural_scope_contamination_audit_missing")
    if not manifest:
        blockers.append("structural_scope_quarantine_manifest_missing")
    if unquarantined_rows:
        blockers.append(f"unquarantined_non_structural_path_count={len(unquarantined_rows)}")
    if release_excluded_count != pending_count:
        blockers.append(
            "owner_review_rows_not_fully_excluded_from_structural_release_surface"
        )
    decision_schema_valid = (
        not owner_decisions_present
        or owner_decisions.get("schema_version") == DECISION_SCHEMA_VERSION
    )
    decision_blockers: list[str] = [
        str(item) for item in _as_list(owner_decisions.get("blockers")) if str(item)
    ]
    if owner_decisions_present and not decision_schema_valid:
        decision_blockers.append("owner_decisions_schema_version_mismatch")
    if owner_decisions_present and "decision_rows" not in owner_decisions:
        decision_blockers.append("owner_decisions_decision_rows_missing")
    decision_extra_path_count = len(
        set(owner_decision_by_path) - {row["path"] for row in review_rows}
    )
    if decision_extra_path_count:
        decision_blockers.append(
            f"owner_decisions_extra_path_count={decision_extra_path_count}"
        )
    if duplicate_decision_paths:
        decision_blockers.append(
            f"owner_decisions_duplicate_path_count={len(duplicate_decision_paths)}"
        )
    owner_decision_recorded_count = sum(
        1 for row in review_rows if row.get("owner_decision_valid") is True
    )
    owner_decision_pending_count = pending_count - owner_decision_recorded_count
    post_decision_cleanup_pending_count = sum(
        1 for row in review_rows if row.get("post_decision_cleanup_pending") is True
    )
    packet_complete = bool(audit and manifest and not blockers)
    evidence_closure_pass = bool(
        packet_complete
        and not decision_blockers
        and owner_decision_pending_count == 0
        and post_decision_cleanup_pending_count == 0
    )
    status = (
        "complete"
        if evidence_closure_pass
        else "owner_decision_evidence_invalid"
        if packet_complete and decision_blockers
        else "ready_for_post_decision_cleanup"
        if packet_complete
        and owner_decision_pending_count == 0
        and post_decision_cleanup_pending_count
        else "ready_for_owner_review"
        if packet_complete
        else "blocked_scope_cleanup"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_structural_scope_owner_review_packet.py"),
                audit_path,
                quarantine_manifest_path,
                owner_decisions_path,
            ],
            reused_evidence=False,
            reuse_policy=(
                "structural_scope_owner_review_packet_from_quarantine_audit"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": packet_complete,
        "evidence_closure_pass": evidence_closure_pass,
        "summary_line": (
            "Structural scope owner review: "
            f"{status.upper()} | pending={owner_decision_pending_count} | "
            f"cleanup_pending={post_decision_cleanup_pending_count} | "
            f"excluded={release_excluded_count}/{pending_count} | "
            f"unquarantined={len(unquarantined_rows)}"
        ),
        "owner_review_required": pending_count > 0,
        "owner_decisions": {
            "path": owner_decisions_path.as_posix(),
            "present": owner_decisions_present,
            "schema_version": str(owner_decisions.get("schema_version", "")),
            "decision_format": str(owner_decisions.get("decision_format", "json")),
            "schema_valid": decision_schema_valid,
            "decision_row_count": len(_decision_rows(owner_decisions)),
            "decision_extra_path_count": decision_extra_path_count,
            "decision_duplicate_path_count": len(duplicate_decision_paths),
            "decision_duplicate_paths": duplicate_decision_paths,
            "decision_recorded_count": owner_decision_recorded_count,
            "decision_pending_count": owner_decision_pending_count,
            "post_decision_cleanup_pending_count": post_decision_cleanup_pending_count,
            "blockers": decision_blockers,
        },
        "owner_decision_recorded_count": owner_decision_recorded_count,
        "owner_decision_pending_count": owner_decision_pending_count,
        "post_decision_cleanup_pending_count": post_decision_cleanup_pending_count,
        "quarantined_path_count": pending_count,
        "release_surface_excluded_path_count": release_excluded_count,
        "unquarantined_non_structural_path_count": len(unquarantined_rows),
        "path_area_counts": _counts_by_key(review_rows, "path_area"),
        "family_counts": _family_counts(review_rows),
        "review_group_count": len(_group_rows(review_rows)),
        "review_groups": _group_rows(review_rows),
        "allowed_owner_decisions": list(ALLOWED_OWNER_DECISIONS),
        "required_closure_evidence": list(REQUIRED_CLOSURE_EVIDENCE),
        "blockers": blockers,
        "closure_blockers": [
            *decision_blockers,
            *(
                [f"owner_decision_pending_count={owner_decision_pending_count}"]
                if owner_decision_pending_count
                else []
            ),
            *(
                [
                    "post_decision_cleanup_pending_count="
                    f"{post_decision_cleanup_pending_count}"
                ]
                if post_decision_cleanup_pending_count
                else []
            ),
        ],
        "review_rows": review_rows,
        "unquarantined_rows": unquarantined_rows,
        "artifacts": {
            "structural_scope_contamination_audit": audit_path.as_posix(),
            "structural_scope_quarantine_manifest": quarantine_manifest_path.as_posix(),
            "structural_scope_owner_decisions": owner_decisions_path.as_posix(),
        },
        "claim_boundary": (
            "This packet is an owner handoff for quarantined non-structural "
            "molecular/GPCR/PocketMD/MD artifacts. It does not delete files, "
            "promote molecular evidence, or make quarantined rows eligible for "
            "building structural-analysis release claims. Closure requires a "
            "recorded owner decision per path followed by a refreshed structural "
            "scope contamination audit."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Owner Review Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `owner_decision_recorded_count`: `{payload['owner_decision_recorded_count']}`",
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        f"- `post_decision_cleanup_pending_count`: `{payload['post_decision_cleanup_pending_count']}`",
        f"- `release_surface_excluded_path_count`: `{payload['release_surface_excluded_path_count']}`",
        f"- `unquarantined_non_structural_path_count`: `{payload['unquarantined_non_structural_path_count']}`",
        f"- `owner_decisions_path`: `{payload['owner_decisions']['path']}`",
        "",
        "## Review Groups",
        "",
        "| Family | Area | Paths | Recommended Decision |",
        "|---|---|---:|---|",
    ]
    for group in payload["review_groups"]:
        lines.append(
            "| "
            f"`{group['family']}` | "
            f"`{group['path_area']}` | "
            f"{group['path_count']} | "
            f"`{group['recommended_owner_decision']}` |"
        )
    lines.extend(
        [
            "",
            "## Owner Decision Rows",
            "",
            "| Path | Area | Families | State | Release Surface | Recommended Decision |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in payload["review_rows"]:
        lines.append(
            "| "
            f"`{row['path']}` | "
            f"`{row['path_area']}` | "
            f"`{', '.join(row['families'])}` | "
            f"`{row['owner_review_state']}` | "
            f"`{row['structural_release_surface_status']}` | "
            f"`{row['recommended_owner_decision']}` |"
        )
    if payload["closure_blockers"]:
        lines.extend(["", "## Closure Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["closure_blockers"])
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def _decision_template_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Owner Decision Template",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `decision_pending_count`: `{payload['decision_pending_count']}`",
        "",
        "| Row | Path | Recommended Decision |",
        "|---|---|---|",
    ]
    for row in payload["decision_rows"]:
        lines.append(
            "| "
            f"`{row['row_id']}` | "
            f"`{row['path']}` | "
            f"`{row['recommended_owner_decision']}` |"
        )
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_owner_review_packet(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_owner_review_packet(
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
    return payload


def write_owner_decision_template(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OUT,
    out: Path = DEFAULT_OWNER_DECISION_TEMPLATE,
    out_md: Path = DEFAULT_OWNER_DECISION_TEMPLATE_MD,
    out_csv: Path = DEFAULT_OWNER_DECISION_TEMPLATE_CSV,
) -> dict[str, Any]:
    payload = build_owner_decision_template(
        repo_root=repo_root,
        owner_review_packet_path=owner_review_packet_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out_csv = _resolve(repo_root, out_csv)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_decision_template_markdown(payload), encoding="utf-8")
    resolved_out_csv.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_csv.write_text(_csv_text(payload["decision_rows"]), encoding="utf-8")
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
        "--write-decision-template",
        action="store_true",
        help="Also write a fill-in owner decision template from the generated packet.",
    )
    parser.add_argument(
        "--decision-template-out",
        type=Path,
        default=DEFAULT_OWNER_DECISION_TEMPLATE,
    )
    parser.add_argument(
        "--decision-template-out-md",
        type=Path,
        default=DEFAULT_OWNER_DECISION_TEMPLATE_MD,
    )
    parser.add_argument(
        "--decision-template-out-csv",
        type=Path,
        default=DEFAULT_OWNER_DECISION_TEMPLATE_CSV,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_owner_review_packet(
        repo_root=args.repo_root,
        audit_path=args.audit,
        quarantine_manifest_path=args.quarantine_manifest,
        owner_decisions_path=args.owner_decisions,
        out=args.out,
        out_md=args.out_md,
    )
    template_payload = None
    if args.write_decision_template:
        template_payload = write_owner_decision_template(
            repo_root=args.repo_root,
            owner_review_packet_path=args.out,
            out=args.decision_template_out,
            out_md=args.decision_template_out_md,
            out_csv=args.decision_template_out_csv,
        )
    if args.json:
        output_payload = dict(payload)
        if template_payload is not None:
            output_payload["owner_decision_template"] = {
                "path": args.decision_template_out.as_posix(),
                "csv_path": args.decision_template_out_csv.as_posix(),
                "decision_pending_count": template_payload["decision_pending_count"],
                "contract_pass": template_payload["contract_pass"],
            }
        print(_json_text(output_payload), end="")
    else:
        print(payload["summary_line"])
        if template_payload is not None:
            print(
                "Owner decision template: "
                f"{args.decision_template_out.as_posix()} "
                f"and {args.decision_template_out_csv.as_posix()} "
                f"(pending={template_payload['decision_pending_count']})"
            )
    return 1 if args.fail_blocked and not payload["evidence_closure_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
