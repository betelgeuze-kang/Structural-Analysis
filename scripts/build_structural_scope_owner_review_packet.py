#!/usr/bin/env python3
"""Build owner-review handoff for quarantined non-structural scope paths."""

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

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-owner-review-packet.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "structural_scope_contamination_audit.json"
DEFAULT_QUARANTINE_MANIFEST = PRODUCTIZATION / "structural_scope_quarantine_manifest.json"
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def build_owner_review_packet(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit = _load_json(repo_root, audit_path)
    manifest = _load_json(repo_root, quarantine_manifest_path)
    manifest_paths = _manifest_paths(manifest)
    rows = [
        row
        for row in _as_list(audit.get("quarantined_non_structural_rows"))
        if isinstance(row, dict)
    ]
    review_rows = [_review_row(row, manifest_paths=manifest_paths) for row in rows]
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
    packet_complete = bool(audit and manifest and not blockers)
    evidence_closure_pass = bool(packet_complete and pending_count == 0)
    status = (
        "complete"
        if evidence_closure_pass
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
            f"{status.upper()} | pending={pending_count} | "
            f"excluded={release_excluded_count}/{pending_count} | "
            f"unquarantined={len(unquarantined_rows)}"
        ),
        "owner_review_required": pending_count > 0,
        "owner_decision_pending_count": pending_count,
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
        "review_rows": review_rows,
        "unquarantined_rows": unquarantined_rows,
        "artifacts": {
            "structural_scope_contamination_audit": audit_path.as_posix(),
            "structural_scope_quarantine_manifest": quarantine_manifest_path.as_posix(),
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
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        f"- `release_surface_excluded_path_count`: `{payload['release_surface_excluded_path_count']}`",
        f"- `unquarantined_non_structural_path_count`: `{payload['unquarantined_non_structural_path_count']}`",
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
            "| Path | Area | Families | Release Surface | Recommended Decision |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["review_rows"]:
        lines.append(
            "| "
            f"`{row['path']}` | "
            f"`{row['path_area']}` | "
            f"`{', '.join(row['families'])}` | "
            f"`{row['structural_release_surface_status']}` | "
            f"`{row['recommended_owner_decision']}` |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_owner_review_packet(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
    quarantine_manifest_path: Path = DEFAULT_QUARANTINE_MANIFEST,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_owner_review_packet(
        repo_root=repo_root,
        audit_path=audit_path,
        quarantine_manifest_path=quarantine_manifest_path,
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
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_owner_review_packet(
        repo_root=args.repo_root,
        audit_path=args.audit,
        quarantine_manifest_path=args.quarantine_manifest,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["evidence_closure_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
