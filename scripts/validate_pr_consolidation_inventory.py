#!/usr/bin/env python3
"""Validate the bounded open-PR consolidation inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "docs/open-pr-consolidation-inventory.v2.json"
SUPPORTED_SCHEMA_VERSIONS = {
    "open-pr-consolidation-inventory.v1",
    "open-pr-consolidation-inventory.v2",
}
REQUIRED_ENTRY_FIELDS = {
    "pr_number",
    "integration_line",
    "base_class",
    "disposition",
    "replacement_destination",
    "unique_scope",
    "close_condition",
}
SAFE_DISPOSITIONS = {
    "preserve-until-replacement",
    "retain-as-historical-evidence-source",
    "extract-unique-code",
    "extract-after-linear-slice",
    "merge-when-required-checks-pass",
}


def load_inventory(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("inventory root must be an object")
    return payload


def validate_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append("invalid_schema_version")
    source_commit = payload.get("source_commit")
    if not isinstance(source_commit, str) or len(source_commit) != 40:
        errors.append("invalid_source_commit")
    if payload.get("active_implementation_pr_target") != 4:
        errors.append("active_implementation_pr_target_must_equal_4")

    snapshot_numbers = payload.get("snapshot_open_pr_numbers")
    entries = payload.get("entries")
    if not isinstance(snapshot_numbers, list) or not all(
        isinstance(number, int) and number > 0 for number in snapshot_numbers
    ):
        errors.append("invalid_snapshot_open_pr_numbers")
        snapshot_numbers = []
    if len(snapshot_numbers) != len(set(snapshot_numbers)):
        errors.append("duplicate_snapshot_open_pr_number")

    entry_numbers: list[int] = []
    integration_lines: set[str] = set()
    if not isinstance(entries, list):
        errors.append("entries_must_be_array")
        entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry_not_object:{index}")
            continue
        missing = sorted(REQUIRED_ENTRY_FIELDS - entry.keys())
        if missing:
            errors.append(f"entry_missing_fields:{index}:{','.join(missing)}")
        pr_number = entry.get("pr_number")
        if not isinstance(pr_number, int) or pr_number <= 0:
            errors.append(f"invalid_pr_number:{index}")
        else:
            entry_numbers.append(pr_number)
        integration_line = entry.get("integration_line")
        if not isinstance(integration_line, str) or not integration_line.strip():
            errors.append(f"invalid_integration_line:{index}")
        else:
            integration_lines.add(integration_line)
        if entry.get("base_class") not in {"current-main", "legacy-stack"}:
            errors.append(f"invalid_base_class:{index}")
        if entry.get("disposition") not in SAFE_DISPOSITIONS:
            errors.append(f"unsafe_or_unknown_disposition:{index}")
        unique_scope = entry.get("unique_scope")
        if (
            not isinstance(unique_scope, list)
            or not unique_scope
            or not all(isinstance(item, str) and item.strip() for item in unique_scope)
        ):
            errors.append(f"invalid_unique_scope:{index}")
        close_condition = entry.get("close_condition")
        if not isinstance(close_condition, str) or not close_condition.strip():
            errors.append(f"missing_close_condition:{index}")
        replacement = entry.get("replacement_destination")
        if not isinstance(replacement, str) or not replacement.strip():
            errors.append(f"missing_replacement_destination:{index}")

    if len(entry_numbers) != len(set(entry_numbers)):
        errors.append("duplicate_entry_pr_number")
    if set(entry_numbers) != set(snapshot_numbers):
        missing_entries = sorted(set(snapshot_numbers) - set(entry_numbers))
        unexpected_entries = sorted(set(entry_numbers) - set(snapshot_numbers))
        if missing_entries:
            errors.append(
                "snapshot_prs_missing_entries:" + ",".join(map(str, missing_entries))
            )
        if unexpected_entries:
            errors.append(
                "entries_not_in_snapshot:" + ",".join(map(str, unexpected_entries))
            )

    if schema_version == "open-pr-consolidation-inventory.v2":
        previous_snapshot = payload.get("previous_snapshot")
        previous_numbers: list[int] = []
        if not isinstance(previous_snapshot, dict):
            errors.append("previous_snapshot_missing")
        else:
            if (
                previous_snapshot.get("schema_version")
                != "open-pr-consolidation-inventory.v1"
            ):
                errors.append("previous_snapshot_schema_invalid")
            if (
                previous_snapshot.get("path")
                != "docs/open-pr-consolidation-inventory.v1.json"
            ):
                errors.append("previous_snapshot_path_invalid")
            raw_previous_numbers = previous_snapshot.get("snapshot_open_pr_numbers")
            if not isinstance(raw_previous_numbers, list) or not all(
                isinstance(number, int) and number > 0
                for number in raw_previous_numbers
            ):
                errors.append("previous_snapshot_numbers_invalid")
            else:
                previous_numbers = raw_previous_numbers
                if len(previous_numbers) != len(set(previous_numbers)):
                    errors.append("previous_snapshot_numbers_duplicate")

        added_numbers = payload.get("added_since_previous")
        if not isinstance(added_numbers, list) or not all(
            isinstance(number, int) and number > 0 for number in added_numbers
        ):
            errors.append("added_since_previous_invalid")
            added_numbers = []
        elif len(added_numbers) != len(set(added_numbers)):
            errors.append("added_since_previous_duplicate")

        closed_rows = payload.get("closed_since_previous")
        closed_numbers: list[int] = []
        if not isinstance(closed_rows, list):
            errors.append("closed_since_previous_invalid")
            closed_rows = []
        for index, row in enumerate(closed_rows):
            if not isinstance(row, dict):
                errors.append(f"closed_since_previous_entry_invalid:{index}")
                continue
            number = row.get("pr_number")
            if not isinstance(number, int) or number <= 0:
                errors.append(f"closed_since_previous_number_invalid:{index}")
                continue
            closed_numbers.append(number)
            if row.get("state") != "closed":
                errors.append(f"closed_since_previous_state_invalid:{number}")
            if row.get("merged") is not True:
                errors.append(f"closed_since_previous_merge_invalid:{number}")
            merged_at = row.get("merged_at")
            if not isinstance(merged_at, str) or not merged_at.endswith("Z"):
                errors.append(f"closed_since_previous_merged_at_invalid:{number}")
        if len(closed_numbers) != len(set(closed_numbers)):
            errors.append("closed_since_previous_duplicate")

        previous_set = set(previous_numbers)
        added_set = set(added_numbers)
        closed_set = set(closed_numbers)
        if previous_set & added_set:
            errors.append("added_since_previous_already_in_previous")
        if not closed_set <= previous_set:
            errors.append("closed_since_previous_not_in_previous")
        reconciled_numbers = (previous_set | added_set) - closed_set
        if reconciled_numbers != set(snapshot_numbers):
            errors.append("snapshot_delta_reconciliation_failed")

    claim_boundary = payload.get("claim_boundary")
    if (
        not isinstance(claim_boundary, str)
        or "does not merge code" not in claim_boundary
    ):
        errors.append("claim_boundary_missing_or_unsafe")

    return {
        "schema_version": "open-pr-consolidation-inventory-validation.v2",
        "contract_pass": not errors,
        "entry_count": len(entry_numbers),
        "snapshot_count": len(snapshot_numbers),
        "integration_lines": sorted(integration_lines),
        "errors": sorted(set(errors)),
        "claim_boundary": (
            "Validation confirms planning inventory consistency only and creates no "
            "numerical, external-V&V, hardware, licensing, merge, or release authority."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_inventory(load_inventory(args.inventory))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
