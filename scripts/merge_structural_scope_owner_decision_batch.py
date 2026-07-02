#!/usr/bin/env python3
"""Merge a filled owner-review batch into a non-mutating decision candidate."""

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

import build_structural_scope_owner_decision_application_plan as application_plan  # noqa: E402
import build_structural_scope_owner_review_packet as owner_review  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-owner-decision-batch-merge.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "structural_scope_contamination_audit.json"
DEFAULT_QUARANTINE_MANIFEST = PRODUCTIZATION / "structural_scope_quarantine_manifest.json"
DEFAULT_BASE_OWNER_DECISIONS = PRODUCTIZATION / "structural_scope_owner_decisions.json"

LIST_FIELDS = {
    "families",
    "matched_tokens",
    "allowed_owner_decisions",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _same_path(repo_root: Path, left: Path, right: Path) -> bool:
    return _resolve(repo_root, left).resolve() == _resolve(repo_root, right).resolve()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(",", ";").split(";")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _normalized_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key in LIST_FIELDS:
            normalized[key] = _split_list_field(value)
        else:
            normalized[key] = _text(value)
    return normalized


def _load_decision_payload(repo_root: Path, path: Path) -> tuple[dict[str, Any], bool]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}, False
    return owner_review._load_owner_decisions(repo_root, path), True


def _decision_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _normalized_decision_row(row)
        for row in owner_review._decision_rows(payload)
        if isinstance(row, dict)
    ]


def _duplicate_paths(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        path = _text(row.get("path"))
        if not path:
            continue
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    return sorted(duplicates)


def _empty_path_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if not _text(row.get("path")))


def _schema_blockers(
    *,
    label: str,
    payload: dict[str, Any],
    present: bool,
    required: bool,
) -> list[str]:
    blockers: list[str] = []
    if required and not present:
        blockers.append(f"{label}_missing")
        return blockers
    if not present:
        return blockers
    if payload.get("schema_version") != owner_review.DECISION_SCHEMA_VERSION:
        blockers.append(f"{label}_schema_version_mismatch")
    if "decision_rows" not in payload and "owner_decision_rows" not in payload:
        blockers.append(f"{label}_decision_rows_missing")
    blockers.extend(f"{label}::{item}" for item in _as_list(payload.get("blockers")))
    return blockers


def build_merge_candidate(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    base_owner_decisions_path: Path = DEFAULT_BASE_OWNER_DECISIONS,
    batch_owner_decisions_path: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    base_payload, base_present = _load_decision_payload(
        repo_root,
        base_owner_decisions_path,
    )
    batch_payload, batch_present = _load_decision_payload(
        repo_root,
        batch_owner_decisions_path,
    )
    base_rows = _decision_rows(base_payload)
    batch_rows = _decision_rows(batch_payload)

    blockers = [
        *_schema_blockers(
            label="batch_owner_decisions",
            payload=batch_payload,
            present=batch_present,
            required=True,
        ),
        *_schema_blockers(
            label="base_owner_decisions",
            payload=base_payload,
            present=base_present,
            required=False,
        ),
    ]
    base_duplicate_paths = _duplicate_paths(base_rows)
    batch_duplicate_paths = _duplicate_paths(batch_rows)
    base_empty_path_count = _empty_path_count(base_rows)
    batch_empty_path_count = _empty_path_count(batch_rows)
    if base_duplicate_paths:
        blockers.append(f"base_duplicate_path_count={len(base_duplicate_paths)}")
    if batch_duplicate_paths:
        blockers.append(f"batch_duplicate_path_count={len(batch_duplicate_paths)}")
    if base_empty_path_count:
        blockers.append(f"base_empty_path_row_count={base_empty_path_count}")
    if batch_empty_path_count:
        blockers.append(f"batch_empty_path_row_count={batch_empty_path_count}")

    rows_by_path: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    overwritten_paths: list[str] = []
    appended_paths: list[str] = []
    for row in base_rows:
        path = _text(row.get("path"))
        if not path:
            continue
        if path not in rows_by_path:
            order.append(path)
        rows_by_path[path] = row
    for row in batch_rows:
        path = _text(row.get("path"))
        if not path:
            continue
        if path in rows_by_path:
            overwritten_paths.append(path)
        else:
            order.append(path)
            appended_paths.append(path)
        rows_by_path[path] = row

    merged_rows = [rows_by_path[path] for path in order]
    blockers = sorted(set(blockers))
    merge_report = {
        "base_owner_decisions_path": base_owner_decisions_path.as_posix(),
        "batch_owner_decisions_path": batch_owner_decisions_path.as_posix(),
        "base_owner_decisions_present": base_present,
        "batch_owner_decisions_present": batch_present,
        "base_decision_row_count": len(base_rows),
        "batch_decision_row_count": len(batch_rows),
        "merged_decision_row_count": len(merged_rows),
        "overwritten_path_count": len(set(overwritten_paths)),
        "overwritten_paths": sorted(set(overwritten_paths)),
        "appended_path_count": len(appended_paths),
        "appended_paths": appended_paths,
        "base_duplicate_path_count": len(base_duplicate_paths),
        "base_duplicate_paths": base_duplicate_paths,
        "batch_duplicate_path_count": len(batch_duplicate_paths),
        "batch_duplicate_paths": batch_duplicate_paths,
        "base_empty_path_row_count": base_empty_path_count,
        "batch_empty_path_row_count": batch_empty_path_count,
        "merge_blockers": blockers,
        "merge_contract_pass": not blockers,
    }
    return {
        "schema_version": owner_review.DECISION_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/merge_structural_scope_owner_decision_batch.py"),
                Path("scripts/build_structural_scope_owner_review_packet.py"),
                Path("scripts/build_structural_scope_owner_decision_application_plan.py"),
                audit_path,
                quarantine_manifest_path,
                base_owner_decisions_path,
                batch_owner_decisions_path,
            ],
            reused_evidence=False,
            reuse_policy="structural_scope_owner_decision_batch_merge_candidate_only",
            repo_root=repo_root,
        ),
        "decision_rows": merged_rows,
        "blockers": blockers,
        "merge_report": merge_report,
        "claim_boundary": (
            "This file is a non-mutating owner-decision candidate generated "
            "from a filled batch. It does not delete, extract, or close scope "
            "cleanup without owner evidence, manual cleanup application, and a "
            "refreshed structural scope audit."
        ),
    }


def _application_plan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _text(payload.get("status")),
        "contract_pass": bool(payload.get("contract_pass")),
        "application_ready": bool(payload.get("application_ready")),
        "evidence_closure_pass": bool(payload.get("evidence_closure_pass")),
        "owner_decision_validation_pass": bool(
            payload.get("owner_decision_validation_pass")
        ),
        "owner_decision_validation_blockers": [
            str(item) for item in _as_list(payload.get("owner_decision_validation_blockers"))
        ],
        "owner_decision_recorded_count": int(
            payload.get("owner_decision_recorded_count", 0) or 0
        ),
        "owner_decision_pending_count": int(
            payload.get("owner_decision_pending_count", 0) or 0
        ),
        "post_decision_cleanup_pending_count": int(
            payload.get("post_decision_cleanup_pending_count", 0) or 0
        ),
        "cleanup_required_count": int(payload.get("cleanup_required_count", 0) or 0),
        "release_surface_owner_decision_required_count": int(
            payload.get("release_surface_owner_decision_required_count", 0) or 0
        ),
        "release_surface_first_batch_ready": bool(
            payload.get("release_surface_first_batch_ready")
        ),
        "release_surface_first_batch_application_ready": bool(
            payload.get("release_surface_first_batch_application_ready")
        ),
        "release_surface_first_batch_blockers": [
            str(item) for item in _as_list(payload.get("release_surface_first_batch_blockers"))
        ],
        "release_surface_first_batch_application_blockers": [
            str(item)
            for item in _as_list(
                payload.get("release_surface_first_batch_application_blockers")
            )
        ],
        "cleanup_command_manifest": _as_dict(payload.get("cleanup_command_manifest")),
    }


def write_merge_candidate(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    base_owner_decisions_path: Path = DEFAULT_BASE_OWNER_DECISIONS,
    batch_owner_decisions_path: Path,
    out: Path,
    out_md: Path | None = None,
    allow_overwrite_base: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if _same_path(repo_root, out, batch_owner_decisions_path):
        raise ValueError("candidate_out_must_not_overwrite_batch_owner_decisions")
    if (
        _same_path(repo_root, out, base_owner_decisions_path)
        and not allow_overwrite_base
    ):
        raise ValueError(
            "candidate_out_matches_base_owner_decisions_without_allow_overwrite_base"
        )
    candidate = build_merge_candidate(
        repo_root=repo_root,
        audit_path=audit_path,
        quarantine_manifest_path=quarantine_manifest_path,
        base_owner_decisions_path=base_owner_decisions_path,
        batch_owner_decisions_path=batch_owner_decisions_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(candidate), encoding="utf-8")
    plan = application_plan.build_application_plan(
        repo_root=repo_root,
        audit_path=audit_path,
        quarantine_manifest_path=quarantine_manifest_path,
        owner_decisions_path=out,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "candidate_owner_decisions_path": out.as_posix(),
        "candidate_owner_decisions": candidate,
        "merge_report": candidate["merge_report"],
        "application_plan_summary": _application_plan_summary(plan),
        "application_plan_summary_line": _text(plan.get("summary_line")),
        "safe_to_auto_apply": False,
        "destructive_commands_enabled": False,
        "manual_cleanup_application_required": bool(
            plan.get("cleanup_required_count")
        ),
        "claim_boundary": (
            "This merge report is non-mutating. It validates a candidate owner "
            "decision file and surfaces manual cleanup previews only."
        ),
    }
    if out_md is not None:
        resolved_md = _resolve(repo_root, out_md)
        resolved_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    report = _as_dict(payload.get("merge_report"))
    summary = _as_dict(payload.get("application_plan_summary"))
    lines = [
        "# Structural Scope Owner Decision Batch Merge",
        "",
        f"- `candidate_owner_decisions_path`: `{payload['candidate_owner_decisions_path']}`",
        f"- `merge_contract_pass`: `{report.get('merge_contract_pass')}`",
        f"- `base_decision_row_count`: `{report.get('base_decision_row_count', 0)}`",
        f"- `batch_decision_row_count`: `{report.get('batch_decision_row_count', 0)}`",
        f"- `merged_decision_row_count`: `{report.get('merged_decision_row_count', 0)}`",
        f"- `overwritten_path_count`: `{report.get('overwritten_path_count', 0)}`",
        f"- `appended_path_count`: `{report.get('appended_path_count', 0)}`",
        "",
        "## Application Plan Validation",
        "",
        f"- `status`: `{summary.get('status')}`",
        f"- `owner_decision_validation_pass`: `{summary.get('owner_decision_validation_pass')}`",
        f"- `owner_decision_pending_count`: `{summary.get('owner_decision_pending_count')}`",
        f"- `post_decision_cleanup_pending_count`: `{summary.get('post_decision_cleanup_pending_count')}`",
        f"- `release_surface_first_batch_application_ready`: `{summary.get('release_surface_first_batch_application_ready')}`",
    ]
    blockers = [str(item) for item in _as_list(report.get("merge_blockers"))]
    lines.extend(["", "## Merge Blockers", ""])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    validation_blockers = [
        str(item) for item in _as_list(summary.get("owner_decision_validation_blockers"))
    ]
    lines.extend(["", "## Owner Decision Validation Blockers", ""])
    if validation_blockers:
        lines.extend(f"- `{item}`" for item in validation_blockers)
    else:
        lines.append("- none")
    release_blockers = [
        str(item)
        for item in _as_list(
            summary.get("release_surface_first_batch_application_blockers")
        )
    ]
    lines.extend(["", "## Release Surface First Batch Blockers", ""])
    if release_blockers:
        lines.extend(f"- `{item}`" for item in release_blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument(
        "--quarantine-manifest",
        type=Path,
        default=DEFAULT_QUARANTINE_MANIFEST,
    )
    parser.add_argument(
        "--base-owner-decisions",
        type=Path,
        default=DEFAULT_BASE_OWNER_DECISIONS,
    )
    parser.add_argument("--batch-owner-decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument(
        "--allow-overwrite-base",
        action="store_true",
        help="Allow --out to overwrite --base-owner-decisions when explicitly intended.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--fail-merge-blocked",
        action="store_true",
        help="Exit non-zero if the merge input itself has blockers.",
    )
    parser.add_argument(
        "--fail-invalid-owner-decisions",
        action="store_true",
        help="Exit non-zero if the merged candidate fails owner-decision validation.",
    )
    parser.add_argument(
        "--fail-release-surface-first-blocked",
        action="store_true",
        help="Exit non-zero unless release-surface-first is ready for manual cleanup.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = write_merge_candidate(
            repo_root=args.repo_root,
            audit_path=args.audit,
            quarantine_manifest_path=args.quarantine_manifest,
            base_owner_decisions_path=args.base_owner_decisions,
            batch_owner_decisions_path=args.batch_owner_decisions,
            out=args.out,
            out_md=args.out_md,
            allow_overwrite_base=args.allow_overwrite_base,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(_json_text(payload), end="")
    else:
        summary = payload["application_plan_summary"]
        report = payload["merge_report"]
        print(
            "Structural scope owner decision batch merge: "
            f"merge_contract_pass={report['merge_contract_pass']} | "
            f"candidate={payload['candidate_owner_decisions_path']} | "
            f"validation={summary['owner_decision_validation_pass']} | "
            "release_surface_first_batch_application_ready="
            f"{summary['release_surface_first_batch_application_ready']}"
        )
    report = payload["merge_report"]
    summary = payload["application_plan_summary"]
    if args.fail_merge_blocked and not report["merge_contract_pass"]:
        return 1
    if (
        args.fail_invalid_owner_decisions
        and not summary["owner_decision_validation_pass"]
    ):
        return 1
    if (
        args.fail_release_surface_first_blocked
        and not summary["release_surface_first_batch_application_ready"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
