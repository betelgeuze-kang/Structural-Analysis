#!/usr/bin/env python3
"""Validate pull-request issue auto-close syntax and factual metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any


CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)([1-9][0-9]*)\b"
)
ANY_ISSUE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#([1-9][0-9]*)\b"
)
EXACT_FILE_CLAIM = re.compile(r"(?i)\bexactly\s+([1-9][0-9]*)\s+changed\s+files?\b")
NUMERIC_COMMIT_CLAIM = re.compile(
    r"(?i)\b(?:exactly\s+)?([1-9][0-9]*)\s+commits?\b"
)
ONE_COMMIT_CLAIM = re.compile(r"(?i)\b(?:a|one)\s+commit\b")
PLACEHOLDER_TOKENS = ("OWNER_INPUT_REQUIRED", "TBD", "TODO:")


def _event_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub event payload must be an object")
    return payload


def build_report(
    payload: dict[str, Any],
    *,
    require_closing_issue: bool = True,
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
    if require_closing_issue and not closing_issue_numbers:
        blockers.append("recognized_closing_issue_reference_missing")
    ambiguous = sorted(set(referenced_issue_numbers) - set(closing_issue_numbers))
    if ambiguous and not closing_issue_numbers:
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
        "blockers": blockers,
        "claim_boundary": (
            "This check validates GitHub-recognized closing syntax and PR event "
            "metadata consistency. It does not prove that an issue is correctly "
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
    report = build_report(
        _event_payload(args.event_json),
        require_closing_issue=not args.allow_unlinked,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if args.json or args.out is None:
        print(text, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
