#!/usr/bin/env python3
"""Validate the read-only PR and branch hygiene inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("artifacts/manifests/repository_hygiene_inventory.json")


def build_report(
    repo_root: Path,
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
) -> dict[str, Any]:
    root = repo_root.resolve()
    path = inventory_path if inventory_path.is_absolute() else root / inventory_path
    inventory = json.loads(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if inventory.get("schema_version") != (
        "structural-analysis-repository-hygiene-inventory.v1"
    ):
        blockers.append("inventory_schema_version_invalid")
    if inventory.get("external_actions_performed"):
        blockers.append("read_only_inventory_records_external_mutation")
    if inventory.get("external_mutation_authorized") is not False:
        blockers.append("external_mutation_authority_must_not_be_inferred")
    pull_requests = inventory.get("open_pull_requests")
    if not isinstance(pull_requests, list):
        blockers.append("open_pull_requests_missing")
        pull_requests = []
    observed_count = inventory.get("observed_open_pull_request_count")
    if not isinstance(observed_count, int) or observed_count < 0:
        blockers.append("observed_open_pull_request_count_missing")
    elif observed_count != len(pull_requests):
        blockers.append("open_pull_request_inventory_incomplete")
    for row in pull_requests:
        if not isinstance(row, dict):
            blockers.append("invalid_pull_request_inventory_row")
            continue
        if row.get("state") != "open":
            blockers.append(f"non_open_pr_in_open_inventory:{row.get('number')}")
        if not row.get("recommended_disposition"):
            blockers.append(f"recommended_disposition_missing:{row.get('number')}")
        if row.get("disposition_authorized") is not False:
            blockers.append(
                f"disposition_authority_must_not_be_inferred:{row.get('number')}"
            )
        if not isinstance(row.get("blockers"), list) or not row.get("blockers"):
            blockers.append(f"open_pr_blockers_missing:{row.get('number')}")
    closure_blockers = inventory.get("closure_blockers")
    if not isinstance(closure_blockers, list):
        blockers.append("closure_blockers_missing")
        closure_blockers = []
    if bool(inventory.get("closure_pass")) != (not closure_blockers):
        blockers.append("closure_pass_inconsistent_with_closure_blockers")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "repository-hygiene-inventory-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "closure_pass": bool(inventory.get("closure_pass")) and not closure_blockers,
        "observed_at": inventory.get("observed_at"),
        "observed_default_branch_head": inventory.get("observed_default_branch_head"),
        "open_pull_request_count": len(pull_requests),
        "stale_remote_branch_count": int(
            inventory.get("remote_branch_inventory", {}).get(
                "observed_stale_remote_branch_count", 0
            )
        ),
        "external_actions_performed": inventory.get("external_actions_performed", []),
        "closure_blockers": closure_blockers,
        "blockers": blockers,
        "claim_boundary": inventory.get("claim_boundary", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--fail-open", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, inventory_path=args.inventory)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"repository hygiene inventory: {report['status']} | "
            f"closure={'pass' if report['closure_pass'] else 'open'}"
        )
    if not report["contract_pass"]:
        return 1
    if args.fail_open and not report["closure_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
