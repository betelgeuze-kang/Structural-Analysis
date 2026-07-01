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
        **action,
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
    plan_blockers = [
        *([f"owner_decision_pending_count={packet.get('owner_decision_pending_count')}"] if packet.get("owner_decision_pending_count") else []),
        *([f"post_decision_cleanup_pending_count={packet.get('post_decision_cleanup_pending_count')}"] if packet.get("post_decision_cleanup_pending_count") else []),
        *[str(item) for item in _as_list(packet.get("blockers"))],
        *[f"owner_decisions::{item}" for item in _as_list(owner_decisions.get("blockers"))],
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
        "contract_pass": bool(packet.get("contract_pass") and not _as_list(owner_decisions.get("blockers"))),
        "application_ready": status == "ready_for_cleanup_application",
        "evidence_closure_pass": bool(packet.get("evidence_closure_pass")),
        "owner_decisions_path": owner_decisions_path.as_posix(),
        "owner_decisions_present": bool(owner_decisions.get("present")),
        "owner_decision_recorded_count": int(packet.get("owner_decision_recorded_count", 0) or 0),
        "owner_decision_pending_count": int(packet.get("owner_decision_pending_count", 0) or 0),
        "post_decision_cleanup_pending_count": int(
            packet.get("post_decision_cleanup_pending_count", 0) or 0
        ),
        "delete_decision_count": len(delete_rows),
        "extract_decision_count": len(extract_rows),
        "retain_quarantined_exception_count": len(retain_rows),
        "quarantined_path_count": int(packet.get("quarantined_path_count", 0) or 0),
        "release_surface_excluded_path_count": int(
            packet.get("release_surface_excluded_path_count", 0) or 0
        ),
        "unquarantined_non_structural_path_count": int(
            packet.get("unquarantined_non_structural_path_count", 0) or 0
        ),
        "closure_blockers": closure_blockers,
        "plan_blockers": plan_blockers,
        "cleanup_rows": [
            row for row in rows if row["post_decision_cleanup_pending"] is True
        ],
        "retain_exception_rows": retain_rows,
        "pending_owner_decision_rows": [
            row for row in rows if row["owner_decision_valid"] is False
        ],
        "suggested_sequence": [
            "fill structural_scope_owner_decisions.json from structural_scope_owner_decisions.template.json",
            "rerun this application plan",
            "for delete decisions, remove paths from this structural repository after owner confirmation",
            "for extract decisions, preserve history/evidence externally before removing paths here",
            "rerun structural scope audit and owner review packet",
            "refresh product readiness snapshot",
        ],
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
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `application_ready`: `{payload['application_ready']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        f"- `post_decision_cleanup_pending_count`: `{payload['post_decision_cleanup_pending_count']}`",
        f"- `delete_decision_count`: `{payload['delete_decision_count']}`",
        f"- `extract_decision_count`: `{payload['extract_decision_count']}`",
        f"- `retain_quarantined_exception_count`: `{payload['retain_quarantined_exception_count']}`",
        "",
        "## Plan Blockers",
        "",
    ]
    if payload["plan_blockers"]:
        lines.extend(f"- `{item}`" for item in payload["plan_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Cleanup Rows", "", "| Path | Decision | Required Action |", "|---|---|---|"])
    for row in payload["cleanup_rows"]:
        lines.append(
            f"| `{row['path']}` | `{row['owner_decision']}` | `{row['required_action']}` |"
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
    return 1 if args.fail_blocked and not payload["evidence_closure_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
