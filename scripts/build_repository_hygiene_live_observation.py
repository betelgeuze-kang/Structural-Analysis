#!/usr/bin/env python3
"""Build a normalized read-only GitHub observation for the hygiene gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_rows(path: Path, *, label: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array: {path}")
    if payload and all(isinstance(page, list) for page in payload):
        payload = [row for page in payload for row in page]
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"expected {label} objects: {path}")
    return payload


def _normalize_issue_rows(
    rows: list[dict[str, Any]],
    *,
    require_open: bool,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if "pull_request" in row:
            continue
        number = row.get("number")
        state = row.get("state")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("issue number invalid")
        if state not in {"open", "closed"}:
            raise ValueError(f"issue state invalid: {number}")
        if require_open and state != "open":
            raise ValueError(f"non-open issue returned by open query: {number}")
        normalized.append(
            {
                "number": number,
                "state": state,
                "state_reason": row.get("state_reason"),
                "updated_at": row.get("updated_at"),
                "closed_at": row.get("closed_at"),
            }
        )
    normalized.sort(key=lambda row: row["number"])
    numbers = [row["number"] for row in normalized]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate issue number")
    return normalized


def _normalize_superseded_pull_requests(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        number = row.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("superseded pull request number invalid")
        normalized.append(
            {
                "number": number,
                "state": row.get("state"),
                "merged": bool(row.get("merged")),
                "updated_at": row.get("updated_at"),
                "closed_at": row.get("closed_at"),
            }
        )
    normalized.sort(key=lambda row: row["number"])
    numbers = [row["number"] for row in normalized]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate superseded pull request number")
    return normalized


def build_observation(
    *,
    repository: str,
    repository_payload: dict[str, Any],
    default_branch_commit: dict[str, Any],
    pull_requests: list[dict[str, Any]],
    open_issues: list[dict[str, Any]],
    tracked_issues: list[dict[str, Any]],
    superseded_pull_requests: list[dict[str, Any]],
    observed_at: str,
    candidate_pull_request: dict[str, Any] | None = None,
    candidate_compare: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if repository_payload.get("full_name") != repository:
        raise ValueError("repository identity mismatch")
    default_branch = repository_payload.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise ValueError("default branch missing")
    default_branch_head = default_branch_commit.get("sha")
    if not isinstance(default_branch_head, str) or not GIT_SHA_PATTERN.fullmatch(
        default_branch_head
    ):
        raise ValueError("default branch head invalid")

    normalized_rows: list[dict[str, Any]] = []
    for row in pull_requests:
        number = row.get("number")
        state = row.get("state")
        head = row.get("head")
        head_sha = head.get("sha") if isinstance(head, dict) else None
        if not isinstance(number, int) or number <= 0:
            raise ValueError("pull request number invalid")
        if state != "open":
            raise ValueError(f"non-open pull request returned by open query: {number}")
        if not isinstance(head_sha, str) or not GIT_SHA_PATTERN.fullmatch(head_sha):
            raise ValueError(f"pull request head invalid: {number}")
        normalized_rows.append(
            {
                "number": number,
                "state": state,
                "head_sha": head_sha,
                "updated_at": row.get("updated_at"),
                "draft": bool(row.get("draft")),
            }
        )
    normalized_rows.sort(key=lambda row: row["number"])
    numbers = [row["number"] for row in normalized_rows]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate pull request number")

    normalized_candidate: dict[str, Any] | None = None
    if candidate_pull_request is not None or candidate_compare is not None:
        if not isinstance(candidate_pull_request, dict) or not isinstance(
            candidate_compare, dict
        ):
            raise ValueError("candidate pull request and comparison are both required")
        number = candidate_pull_request.get("number")
        state = candidate_pull_request.get("state")
        head = candidate_pull_request.get("head")
        base = candidate_pull_request.get("base")
        head_sha = head.get("sha") if isinstance(head, dict) else None
        base_sha = base.get("sha") if isinstance(base, dict) else None
        merge_base = candidate_compare.get("merge_base_commit")
        merge_base_sha = merge_base.get("sha") if isinstance(merge_base, dict) else None
        commit_count = candidate_pull_request.get("commits")
        changed_file_count = candidate_pull_request.get("changed_files")
        ahead_by = candidate_compare.get("ahead_by")
        behind_by = candidate_compare.get("behind_by")
        comparison_files = candidate_compare.get("files")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("candidate pull request number invalid")
        if state != "open":
            raise ValueError("candidate pull request is not open")
        for label, value in (
            ("head", head_sha),
            ("base", base_sha),
            ("merge base", merge_base_sha),
        ):
            if not isinstance(value, str) or not GIT_SHA_PATTERN.fullmatch(value):
                raise ValueError(f"candidate pull request {label} invalid")
        for label, value in (
            ("commit count", commit_count),
            ("changed file count", changed_file_count),
            ("ahead count", ahead_by),
            ("behind count", behind_by),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"candidate pull request {label} invalid")
        if not isinstance(comparison_files, list):
            raise ValueError("candidate comparison files missing")
        comparison_changed_path_count = len(comparison_files)
        comparison_files_complete = bool(
            changed_file_count <= 300
            and comparison_changed_path_count == changed_file_count
        )
        normalized_candidate = {
            "number": number,
            "state": state,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "merge_base_sha": merge_base_sha,
            "commit_count": commit_count,
            "changed_file_count": changed_file_count,
            "ahead_by": ahead_by,
            "behind_by": behind_by,
            "comparison_changed_path_count": comparison_changed_path_count,
            "comparison_files_complete": comparison_files_complete,
        }

    normalized_open_issues = _normalize_issue_rows(open_issues, require_open=True)
    normalized_tracked_issues = _normalize_issue_rows(
        tracked_issues,
        require_open=False,
    )
    normalized_superseded = _normalize_superseded_pull_requests(
        superseded_pull_requests
    )

    return {
        "schema_version": "repository-hygiene-live-observation.v2",
        "repository": repository,
        "observed_at": observed_at,
        "default_branch": default_branch,
        "default_branch_head": default_branch_head,
        "open_pull_requests": normalized_rows,
        "candidate_pull_request": normalized_candidate,
        "open_issues": normalized_open_issues,
        "tracked_issues": normalized_tracked_issues,
        "superseded_pull_requests": normalized_superseded,
        "claim_boundary": (
            "Read-only GitHub API observation of pull requests, issues, and declared "
            "supersession rows. This artifact performs no mutation and carries no "
            "disposition or repository-hygiene closure authority."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-json", type=Path, required=True)
    parser.add_argument("--default-branch-commit-json", type=Path, required=True)
    parser.add_argument("--open-pull-requests-json", type=Path, required=True)
    parser.add_argument("--open-issues-json", type=Path, required=True)
    parser.add_argument("--tracked-issues-json", type=Path, required=True)
    parser.add_argument("--superseded-pull-requests-json", type=Path, required=True)
    parser.add_argument("--candidate-pull-request-json", type=Path)
    parser.add_argument("--candidate-compare-json", type=Path)
    parser.add_argument("--observed-at")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    observed_at = args.observed_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    payload = build_observation(
        repository=args.repository,
        repository_payload=_read_object(args.repository_json),
        default_branch_commit=_read_object(args.default_branch_commit_json),
        pull_requests=_read_rows(
            args.open_pull_requests_json,
            label="pull-request",
        ),
        open_issues=_read_rows(args.open_issues_json, label="issue"),
        tracked_issues=_read_rows(args.tracked_issues_json, label="issue"),
        superseded_pull_requests=_read_rows(
            args.superseded_pull_requests_json,
            label="pull-request",
        ),
        observed_at=observed_at,
        candidate_pull_request=(
            _read_object(args.candidate_pull_request_json)
            if args.candidate_pull_request_json
            else None
        ),
        candidate_compare=(
            _read_object(args.candidate_compare_json)
            if args.candidate_compare_json
            else None
        ),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
