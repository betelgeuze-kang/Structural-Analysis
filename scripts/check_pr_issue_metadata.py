#!/usr/bin/env python3
"""Validate issue links, scoped snapshot maintenance, and factual PR metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)([1-9][0-9]*)\b"
)
ANY_ISSUE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#([1-9][0-9]*)\b"
)
EXACT_FILE_CLAIM = re.compile(r"(?i)\bexactly\s+([1-9][0-9]*)\s+changed\s+files?\b")
NUMERIC_COMMIT_CLAIM = re.compile(
    r"(?ix)"
    r"(?:"
    r"\bexactly\s+"
    r"|"
    r"\b(?:this|the)\s+(?:change|pull\s+request|pr)\s+"
    r"(?:contains?|has)\s+(?:exactly\s+)?"
    r")"
    r"([1-9][0-9]*)\s+commits?\b"
    r"(?!\s+(?:ahead|behind|between|from|since)\b)"
)
ONE_COMMIT_CLAIM = re.compile(
    r"(?ix)"
    r"\b(?:"
    r"(?:this|the)\s+(?:change|pull\s+request|pr)\s+"
    r"(?:contains?|has|is)"
    r"|this\s+is"
    r")\s+(?:a|one)\s+commit\b"
    r"(?!\s+(?:ahead|behind|between|from|since)\b)"
)
PLACEHOLDER_TOKENS = ("OWNER_INPUT_REQUIRED", "TBD", "TODO:")
SNAPSHOT_PURPOSE = "Purpose: issue-state snapshot maintenance"
SNAPSHOT_GOVERNANCE = "Refs #493"
SNAPSHOT_REPOSITORY = "betelgeuze-kang/Structural-Analysis"
SNAPSHOT_REPOSITORY_ID = 1136685613
SNAPSHOT_INVENTORY_PATH = "artifacts/manifests/issue_supersession_inventory.json"
SNAPSHOT_ALLOWED_PATHS = frozenset(
    {SNAPSHOT_INVENTORY_PATH, "tests/test_check_issue_supersession_inventory.py"}
)
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SNAPSHOT_CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)[\s:]+"
    r"(?:(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#|https?://)"
)
_GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)\b"
)


def _snapshot_requested(body: str) -> bool:
    return SNAPSHOT_PURPOSE in {line.strip() for line in body.splitlines()}


def _snapshot_pr_identity(pr: Any) -> dict[str, Any]:
    if not isinstance(pr, dict):
        raise ValueError("snapshot_pr_identity_invalid")
    number = pr.get("number")
    count = pr.get("changed_files")
    if (
        type(number) is not int
        or number <= 0
        or type(count) is not int
        or not 0 < count <= 3000
        or pr.get("state") != "open"
        or not isinstance(pr.get("body"), str)
        or not isinstance(pr.get("title"), str)
    ):
        raise ValueError("snapshot_pr_identity_invalid")
    identity: dict[str, Any] = {
        "number": number,
        "changed_files": count,
        "state": pr["state"],
        "body": pr["body"],
        "title": pr["title"],
    }
    for side in ("base", "head"):
        branch = pr.get(side)
        if not isinstance(branch, dict):
            raise ValueError("snapshot_pr_identity_invalid")
        repo = branch.get("repo")
        if (
            not isinstance(repo, dict)
            or type(repo.get("id")) is not int
            or repo.get("id") != SNAPSHOT_REPOSITORY_ID
            or repo.get("full_name") != SNAPSHOT_REPOSITORY
        ):
            raise ValueError("snapshot_repository_identity_invalid")
        sha = branch.get("sha")
        ref = branch.get("ref")
        if (
            not isinstance(sha, str)
            or _COMMIT_SHA.fullmatch(sha) is None
            or not isinstance(ref, str)
            or not ref
            or (side == "base" and ref != "main")
        ):
            raise ValueError("snapshot_branch_identity_invalid")
        identity[f"{side}_sha"] = sha
        identity[f"{side}_ref"] = ref
    if identity["base_ref"] == identity["head_ref"]:
        raise ValueError("snapshot_branch_identity_invalid")
    return identity


def _snapshot_event_identity(payload: dict[str, Any]) -> dict[str, Any]:
    repo = payload.get("repository")
    if (
        not isinstance(repo, dict)
        or type(repo.get("id")) is not int
        or repo.get("id") != SNAPSHOT_REPOSITORY_ID
        or repo.get("full_name") != SNAPSHOT_REPOSITORY
    ):
        raise ValueError("snapshot_repository_identity_invalid")
    identity = _snapshot_pr_identity(payload.get("pull_request"))
    if payload.get("number", identity["number"]) != identity["number"]:
        raise ValueError("snapshot_pr_number_mismatch")
    return identity


def _github_json(
    endpoint: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Any:
    result = runner(
        [
            "gh",
            "api",
            endpoint,
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ValueError("snapshot_github_read_failed")
    try:
        return json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("snapshot_github_json_invalid") from exc


def _fetch_snapshot_files(
    endpoint: str, fetcher: Callable[[str], Any]
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for page in range(1, 32):
        rows = fetcher(f"{endpoint}/files?per_page=100&page={page}")
        if (
            not isinstance(rows, list)
            or len(rows) > 100
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise ValueError("snapshot_file_page_invalid")
        files.extend(rows)
        if len(files) > 3000:
            raise ValueError("snapshot_file_limit_exceeded")
        if len(rows) < 100:
            return files
    raise ValueError("snapshot_file_pagination_incomplete")


def _require_open_governing_issue(issue: Any) -> None:
    if (
        not isinstance(issue, dict)
        or type(issue.get("number")) is not int
        or issue.get("number") != 493
        or issue.get("state") != "open"
        or "pull_request" in issue
    ):
        raise ValueError("snapshot_governing_issue_not_open")


def collect_snapshot_observation(
    payload: dict[str, Any],
    *,
    fetcher: Callable[[str], Any] = _github_json,
) -> dict[str, Any]:
    """Read GitHub only; bind complete file enumeration to an unchanged PR."""
    expected = _snapshot_event_identity(payload)
    endpoint = f"repos/{SNAPSHOT_REPOSITORY}/pulls/{expected['number']}"
    before = _snapshot_pr_identity(fetcher(endpoint))
    if before != expected:
        raise ValueError("snapshot_pr_changed_before_collection")
    issue_endpoint = f"repos/{SNAPSHOT_REPOSITORY}/issues/493"
    _require_open_governing_issue(fetcher(issue_endpoint))
    files = _fetch_snapshot_files(endpoint, fetcher)
    _require_open_governing_issue(fetcher(issue_endpoint))
    after = _snapshot_pr_identity(fetcher(endpoint))
    if after != before:
        raise ValueError("snapshot_pr_changed_during_collection")
    if len(files) != expected["changed_files"]:
        raise ValueError("snapshot_file_count_mismatch")
    return {
        "repository": SNAPSHOT_REPOSITORY,
        "repository_id": SNAPSHOT_REPOSITORY_ID,
        "before": before,
        "after": after,
        "governing_issue_number": 493,
        "governing_issue_state": "open",
        "complete": True,
        "files": files,
    }


def _snapshot_scope_blockers(payload: dict[str, Any], observation: Any) -> list[str]:
    pr = payload["pull_request"]
    body = str(pr.get("body") or "")
    blockers: list[str] = []
    if SNAPSHOT_GOVERNANCE not in {line.strip() for line in body.splitlines()}:
        blockers.append("snapshot_governing_reference_missing")
    if _SNAPSHOT_CLOSING_REFERENCE.search(body):
        blockers.append("snapshot_closing_reference_forbidden")
    if any(match.group(0) != "#493" for match in ANY_ISSUE_REFERENCE.finditer(body)):
        blockers.append("snapshot_other_issue_reference_forbidden")
    if any(
        match.group(1) != SNAPSHOT_REPOSITORY or match.group(2) != "493"
        for match in _GITHUB_ISSUE_URL.finditer(body)
    ):
        blockers.append("snapshot_other_issue_reference_forbidden")
    try:
        expected = _snapshot_event_identity(payload)
    except ValueError as exc:
        blockers.append(str(exc))
        return blockers
    if not isinstance(observation, dict):
        blockers.append("snapshot_authenticated_observation_missing")
        return blockers
    if (
        observation.get("repository") != SNAPSHOT_REPOSITORY
        or type(observation.get("repository_id")) is not int
        or observation.get("repository_id") != SNAPSHOT_REPOSITORY_ID
        or observation.get("before") != expected
        or observation.get("after") != expected
        or observation.get("complete") is not True
        or type(observation.get("governing_issue_number")) is not int
        or observation.get("governing_issue_number") != 493
        or observation.get("governing_issue_state") != "open"
    ):
        blockers.append("snapshot_observation_identity_mismatch")
    files = observation.get("files")
    if not isinstance(files, list) or len(files) != expected["changed_files"]:
        blockers.append("snapshot_file_count_mismatch")
        return blockers
    paths: list[str] = []
    for row in files:
        if not isinstance(row, dict):
            blockers.append("snapshot_file_record_invalid")
            continue
        path = row.get("filename")
        if not isinstance(path, str):
            blockers.append("snapshot_file_record_invalid")
            continue
        paths.append(path)
        if (
            row.get("status") != "modified"
            or "previous_filename" in row
            or path not in SNAPSHOT_ALLOWED_PATHS
        ):
            blockers.append("snapshot_file_scope_invalid")
    if len(paths) != len(set(paths)) or SNAPSHOT_INVENTORY_PATH not in paths:
        blockers.append("snapshot_inventory_change_required")
    return blockers


def _event_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub event payload must be an object")
    return payload


def build_report(
    payload: dict[str, Any],
    *,
    require_closing_issue: bool = True,
    snapshot_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        raise ValueError("payload.pull_request must be an object")
    body = str(pr.get("body") or "")
    title = str(pr.get("title") or "").strip()
    number = int(pr.get("number") or payload.get("number") or 0)
    commits = int(pr.get("commits") or 0)
    changed_files = int(pr.get("changed_files") or 0)
    base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    blockers: list[str] = []

    closing_issue_numbers = sorted(
        {int(match.group(1)) for match in CLOSING_REFERENCE.finditer(body)}
    )
    referenced_issue_numbers = sorted(
        {int(match.group(1)) for match in ANY_ISSUE_REFERENCE.finditer(body)}
    )
    snapshot_requested = _snapshot_requested(body)
    snapshot_blockers = (
        _snapshot_scope_blockers(payload, snapshot_observation)
        if snapshot_requested
        else []
    )
    snapshot_verified = snapshot_requested and not snapshot_blockers
    blockers.extend(snapshot_blockers)
    if require_closing_issue and not closing_issue_numbers and not snapshot_verified:
        blockers.append("recognized_closing_issue_reference_missing")
    ambiguous = sorted(set(referenced_issue_numbers) - set(closing_issue_numbers))
    if ambiguous and not closing_issue_numbers and not snapshot_verified:
        blockers.append("issue_referenced_without_github_closing_keyword")
    if number and number in closing_issue_numbers:
        blockers.append("pull_request_cannot_close_itself")
    if not title:
        blockers.append("pull_request_title_missing")
    if not body.strip():
        blockers.append("pull_request_body_missing")
    for token in PLACEHOLDER_TOKENS:
        if token.lower() in body.lower():
            blockers.append(f"pull_request_body_placeholder:{token}")

    claimed_commit_counts = {
        int(match.group(1)) for match in NUMERIC_COMMIT_CLAIM.finditer(body)
    }
    if ONE_COMMIT_CLAIM.search(body):
        claimed_commit_counts.add(1)
    for claimed in sorted(claimed_commit_counts):
        if commits and claimed != commits:
            blockers.append(
                f"commit_count_claim_mismatch:claimed={claimed}:actual={commits}"
            )
    for match in EXACT_FILE_CLAIM.finditer(body):
        claimed = int(match.group(1))
        if changed_files and claimed != changed_files:
            blockers.append(
                f"changed_file_count_claim_mismatch:claimed={claimed}:actual={changed_files}"
            )

    base_ref = str(base.get("ref") or "")
    head_ref = str(head.get("ref") or "")
    if base_ref and head_ref and base_ref == head_ref:
        blockers.append("pull_request_head_matches_base")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "pr-issue-metadata-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "pull_request_number": number,
        "title": title,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "actual_commit_count": commits,
        "actual_changed_file_count": changed_files,
        "closing_issue_numbers": closing_issue_numbers,
        "referenced_issue_numbers": referenced_issue_numbers,
        "require_closing_issue": require_closing_issue,
        "snapshot_maintenance_requested": snapshot_requested,
        "snapshot_maintenance_verified": snapshot_verified,
        "snapshot_scope": (
            {
                "governing_issue": 493,
                "repository": SNAPSHOT_REPOSITORY,
                "base_sha": snapshot_observation["before"]["base_sha"],
                "head_sha": snapshot_observation["before"]["head_sha"],
                "changed_paths": sorted(
                    row["filename"] for row in snapshot_observation["files"]
                ),
            }
            if snapshot_verified and snapshot_observation is not None
            else None
        ),
        "blockers": blockers,
        "claim_boundary": (
            "This check validates issue-link syntax, narrow snapshot-maintenance "
            "scope, and PR event metadata consistency. It does not prove that "
            "the issue inventory is current, that an issue is correctly "
            "scoped, that acceptance criteria pass, or that merge is authorized."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event-json",
        type=Path,
        default=Path(os.environ.get("GITHUB_EVENT_PATH", "")),
    )
    parser.add_argument("--allow-unlinked", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not str(args.event_json) or not args.event_json.is_file():
        parser.error("--event-json or GITHUB_EVENT_PATH must identify a readable file")
    payload = _event_payload(args.event_json)
    observation = None
    observation_error = None
    pr = payload.get("pull_request")
    if isinstance(pr, dict) and _snapshot_requested(str(pr.get("body") or "")):
        try:
            if not os.environ.get("GH_TOKEN"):
                raise ValueError("snapshot_github_authentication_missing")
            observation = collect_snapshot_observation(payload)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            observation_error = (
                str(exc)
                if isinstance(exc, ValueError)
                else "snapshot_github_read_failed"
            )
    report = build_report(
        payload,
        require_closing_issue=not args.allow_unlinked,
        snapshot_observation=observation,
    )
    if observation_error:
        report["blockers"] = sorted(set(report["blockers"]) | {observation_error})
        report["contract_pass"] = False
        report["status"] = "blocked"
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if args.json or args.out is None:
        print(text, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
