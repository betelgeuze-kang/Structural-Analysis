#!/usr/bin/env python3
"""Build a non-mutating application plan for structural-scope owner decisions."""

from __future__ import annotations

import argparse
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


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        "owner_decision": _text(row.get("owner_decision")),
        "owner_decision_valid": bool(row.get("owner_decision_valid")),
        "owner_review_state": _text(row.get("owner_review_state")),
        "post_decision_cleanup_pending": bool(row.get("post_decision_cleanup_pending")),
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


def _status_from_packet(packet: dict[str, Any]) -> str:
    if not packet.get("contract_pass"):
        return "blocked_scope_cleanup"
    if packet.get("evidence_closure_pass"):
        return "complete"
    if packet.get("owner_decision_pending_count"):
        return "pending_owner_decisions"
    owner_decisions = packet.get("owner_decisions")
    if isinstance(owner_decisions, dict) and owner_decisions.get("blockers"):
        return "owner_decision_evidence_invalid"
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
    rows = [_plan_row(row) for row in _as_list(packet.get("review_rows")) if isinstance(row, dict)]
    status = _status_from_packet(packet)
    owner_decisions = packet.get("owner_decisions") if isinstance(packet.get("owner_decisions"), dict) else {}
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
    pending_owner_decision_rows = [
        row for row in rows if row["owner_decision_valid"] is False
    ]
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
        "release_surface_owner_decision_required_count": sum(
            1 for row in pending_owner_decision_rows if row["path_area"] == "release_surface"
        ),
        "release_surface_owner_decision_required_paths": [
            row["path"]
            for row in pending_owner_decision_rows
            if row["path_area"] == "release_surface"
        ],
        "cleanup_required_count": len(cleanup_rows),
        "cleanup_path_area_counts": _counts_by_key(cleanup_rows, "path_area"),
        "cleanup_family_counts": _family_counts(cleanup_rows),
        "release_surface_cleanup_required_count": sum(
            1 for row in cleanup_rows if row["path_area"] == "release_surface"
        ),
        "release_surface_cleanup_paths": [
            row["path"] for row in cleanup_rows if row["path_area"] == "release_surface"
        ],
        "cleanup_command_manifest": _cleanup_command_manifest(cleanup_rows),
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
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_application_plan(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
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
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--quarantine-manifest", type=Path, default=DEFAULT_QUARANTINE_MANIFEST)
    parser.add_argument("--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
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
