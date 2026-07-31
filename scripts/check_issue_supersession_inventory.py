#!/usr/bin/env python3
"""Validate issue resolution, supersession, and orphan classification inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("artifacts/manifests/issue_supersession_inventory.json")
ALLOWED_OPEN_CLASSIFICATIONS = {"active_pull_request", "source_quarry_backlog"}


def _rows(payload: dict[str, Any], key: str, blockers: list[str]) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        blockers.append(f"{key}_missing")
        return []
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            blockers.append(f"{key}[{index}]_invalid")
            continue
        rows.append(row)
    return rows


def build_report(
    repo_root: Path = ROOT,
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
) -> dict[str, Any]:
    path = (
        inventory_path
        if inventory_path.is_absolute()
        else repo_root.resolve() / inventory_path
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if payload.get("schema_version") != (
        "structural-analysis-issue-supersession-inventory.v1"
    ):
        blockers.append("inventory_schema_version_invalid")

    open_issues = _rows(payload, "open_issues", blockers)
    implemented_open = _rows(payload, "implemented_but_open_issues", blockers)
    orphan_issues = _rows(payload, "orphan_issues", blockers)
    resolved_issues = _rows(payload, "resolved_issues", blockers)
    superseded_prs = _rows(payload, "superseded_pull_requests", blockers)

    observed_count = payload.get("observed_open_issue_count")
    if not isinstance(observed_count, int) or observed_count < 0:
        blockers.append("observed_open_issue_count_invalid")
    elif observed_count != len(open_issues):
        blockers.append("open_issue_inventory_incomplete")

    derived_implemented_open: list[int] = []
    derived_orphans: list[int] = []
    seen_issue_numbers: set[int] = set()
    for row in open_issues:
        number = row.get("number")
        if not isinstance(number, int) or number <= 0 or number in seen_issue_numbers:
            blockers.append(f"open_issue_number_invalid_or_duplicate:{number}")
            continue
        seen_issue_numbers.add(number)
        if row.get("state") != "open":
            blockers.append(f"non_open_issue_in_open_inventory:{number}")
        classification = row.get("classification")
        if classification not in ALLOWED_OPEN_CLASSIFICATIONS:
            blockers.append(f"open_issue_classification_invalid:{number}")
        linked = row.get("linked_pull_requests")
        if not isinstance(linked, list) or not linked:
            derived_orphans.append(number)
        if not str(row.get("disposition") or "").strip():
            derived_orphans.append(number)
        merged = row.get("merged_implementation_pull_requests")
        if not isinstance(merged, list):
            blockers.append(f"merged_implementation_links_missing:{number}")
        elif merged:
            derived_implemented_open.append(number)

    recorded_implemented_open = sorted(
        row.get("number")
        for row in implemented_open
        if isinstance(row.get("number"), int)
    )
    recorded_orphans = sorted(
        row.get("number")
        for row in orphan_issues
        if isinstance(row.get("number"), int)
    )
    if sorted(set(derived_implemented_open)) != recorded_implemented_open:
        blockers.append("implemented_but_open_issue_inventory_inconsistent")
    if sorted(set(derived_orphans)) != recorded_orphans:
        blockers.append("orphan_issue_inventory_inconsistent")

    seen_resolved: set[int] = set()
    for row in resolved_issues:
        number = row.get("number")
        if not isinstance(number, int) or number <= 0 or number in seen_resolved:
            blockers.append(f"resolved_issue_number_invalid_or_duplicate:{number}")
            continue
        seen_resolved.add(number)
        if row.get("state") != "closed" or row.get("state_reason") != "completed":
            blockers.append(f"resolved_issue_not_completed:{number}")
        if row.get("resolution") != "resolved_by":
            blockers.append(f"resolved_issue_disposition_missing:{number}")
        if not isinstance(row.get("resolved_by_pull_request"), int):
            blockers.append(f"resolved_issue_pull_request_missing:{number}")
        merge_sha = str(row.get("merge_commit_sha") or "")
        if len(merge_sha) != 40 or any(char not in "0123456789abcdef" for char in merge_sha):
            blockers.append(f"resolved_issue_merge_sha_invalid:{number}")
        if not isinstance(row.get("normalization_comment_id"), int):
            blockers.append(f"resolved_issue_comment_missing:{number}")

    seen_prs: set[int] = set()
    for row in superseded_prs:
        number = row.get("number")
        if not isinstance(number, int) or number <= 0 or number in seen_prs:
            blockers.append(f"superseded_pr_number_invalid_or_duplicate:{number}")
            continue
        seen_prs.add(number)
        if row.get("state") != "closed" or row.get("merged") is not False:
            blockers.append(f"superseded_pr_state_invalid:{number}")
        if row.get("disposition") != "superseded":
            blockers.append(f"superseded_pr_disposition_missing:{number}")
        if not isinstance(row.get("superseded_by_pull_request"), int):
            blockers.append(f"superseding_pr_missing:{number}")
        if not isinstance(row.get("normalization_comment_id"), int):
            blockers.append(f"supersession_comment_missing:{number}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "issue-supersession-inventory-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "open_issue_count": len(open_issues),
        "implemented_but_open_issue_count": len(implemented_open),
        "orphan_issue_count": len(orphan_issues),
        "resolved_issue_count": len(resolved_issues),
        "superseded_pull_request_count": len(superseded_prs),
        "blockers": blockers,
        "claim_boundary": payload.get("claim_boundary", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, inventory_path=args.inventory)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "issue supersession inventory: "
            f"{report['status']} | open={report['open_issue_count']} | "
            f"implemented_open={report['implemented_but_open_issue_count']} | "
            f"orphan={report['orphan_issue_count']} | "
            f"superseded_pr={report['superseded_pull_request_count']}"
        )
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
