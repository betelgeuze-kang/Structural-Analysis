#!/usr/bin/env python3
"""Audit current-tree or all-history Git blobs against the 25 MiB policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("artifacts/manifests/large_blob_policy.json")
POLICY_SCHEMA_VERSION = "structural-analysis-large-blob-policy.v1"


def _run(repo_root: Path, command: list[str], *, stdin: str | None = None) -> str:
    return subprocess.run(
        command,
        cwd=repo_root,
        input=stdin,
        text=True,
        check=True,
        capture_output=True,
    ).stdout


def _current_tree_blobs(repo_root: Path) -> list[dict[str, Any]]:
    output = _run(repo_root, ["git", "ls-tree", "-r", "-l", "HEAD"])
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        parts = metadata.split()
        if len(parts) != 4 or parts[1] != "blob":
            continue
        rows.append({"oid": parts[2], "size": int(parts[3]), "path": path})
    return rows


def _history_blobs(repo_root: Path) -> list[dict[str, Any]]:
    objects = _run(repo_root, ["git", "rev-list", "--objects", "--all"])
    paths: dict[str, str] = {}
    ordered_oids: list[str] = []
    for line in objects.splitlines():
        oid, _, path = line.partition(" ")
        if oid not in paths:
            ordered_oids.append(oid)
            paths[oid] = path
    query = "".join(f"{oid}\n" for oid in ordered_oids)
    metadata = _run(
        repo_root,
        [
            "git",
            "cat-file",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ],
        stdin=query,
    )
    rows: list[dict[str, Any]] = []
    for line in metadata.splitlines():
        oid, object_type, size = line.split()
        if object_type == "blob":
            rows.append({"oid": oid, "size": int(size), "path": paths.get(oid, "")})
    return rows


def _is_shallow_repository(repo_root: Path) -> bool:
    return _run(repo_root, ["git", "rev-parse", "--is-shallow-repository"]).strip() == "true"


def _load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("large blob policy must be a JSON object")
    if payload.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported large blob policy schema_version")
    if int(payload.get("threshold_bytes") or 0) <= 0:
        raise ValueError("large blob policy threshold_bytes must be positive")
    if not isinstance(payload.get("approved_blobs"), list):
        raise ValueError("large blob policy approved_blobs must be a list")
    return payload


def build_report(
    repo_root: Path,
    *,
    policy_path: Path = DEFAULT_POLICY,
    scope: str = "current",
    max_report_rows: int = 200,
) -> dict[str, Any]:
    if scope not in {"current", "history"}:
        raise ValueError(f"unsupported blob audit scope: {scope}")
    if max_report_rows <= 0:
        raise ValueError("max_report_rows must be positive")
    root = repo_root.resolve()
    resolved_policy = policy_path if policy_path.is_absolute() else root / policy_path
    policy = _load_policy(resolved_policy)
    threshold = int(policy["threshold_bytes"])
    approved = {
        str(row.get("oid")): row
        for row in policy.get("approved_blobs", [])
        if isinstance(row, dict) and row.get("oid")
    }
    repository_is_shallow = _is_shallow_repository(root)
    rows = _current_tree_blobs(root) if scope == "current" else _history_blobs(root)
    oversized = sorted(
        (row for row in rows if int(row["size"]) > threshold),
        key=lambda row: (-int(row["size"]), str(row["path"]), str(row["oid"])),
    )
    unapproved = [row for row in oversized if row["oid"] not in approved]
    approved_rows = [row for row in oversized if row["oid"] in approved]
    blockers = [
        f"unapproved_large_blob:{row['oid']}:{row['size']}:{row['path']}"
        for row in unapproved
    ]
    if scope == "history" and repository_is_shallow:
        blockers.append("all_history_audit_requires_complete_clone")
    if scope == "history" and unapproved and not policy.get("history_rewrite_authorized"):
        blockers.append("history_rewrite_not_authorized")
    return {
        "schema_version": "large-git-blob-audit.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "scope": scope,
        "threshold_bytes": threshold,
        "repository_is_shallow": repository_is_shallow,
        "scanned_blob_count": len(rows),
        "oversized_blob_count": len(oversized),
        "approved_oversized_blob_count": len(approved_rows),
        "unapproved_oversized_blob_count": len(unapproved),
        "oversized_blobs": oversized[:max_report_rows],
        "reported_row_limit": max_report_rows,
        "reported_rows_truncated": len(oversized) > max_report_rows,
        "history_rewrite_authorized": bool(policy.get("history_rewrite_authorized")),
        "p0_required_scope": str(policy.get("p0_required_scope", "")),
        "blockers": blockers[:max_report_rows],
        "blocker_count": len(blockers),
        "claim_boundary": str(policy.get("claim_boundary", "")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--scope", choices=("current", "history"), default="current")
    parser.add_argument("--max-report-rows", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        args.repo_root,
        policy_path=args.policy,
        scope=args.scope,
        max_report_rows=args.max_report_rows,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"large Git blobs ({report['scope']}): {report['status']} | "
            f"oversized={report['oversized_blob_count']} | "
            f"unapproved={report['unapproved_oversized_blob_count']}"
        )
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
