#!/usr/bin/env python3
"""Validate the read-only PR, issue, supersession, and branch hygiene inventory."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("artifacts/manifests/repository_hygiene_inventory.json")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc)


def _pull_request_numbers(rows: Sequence[object]) -> list[int]:
    numbers: list[int] = []
    for row in rows:
        if isinstance(row, dict):
            number = row.get("number")
            if isinstance(number, int) and number > 0:
                numbers.append(number)
    return numbers


def _validate_numbered_rows(
    rows: object,
    *,
    missing_blocker: str,
    duplicate_blocker: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    if not isinstance(rows, list):
        return [], [missing_blocker]
    typed_rows: list[dict[str, Any]] = []
    numbers: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            blockers.append("invalid_numbered_inventory_row")
            continue
        number = row.get("number")
        if not isinstance(number, int) or number <= 0:
            blockers.append("numbered_inventory_row_number_invalid")
            continue
        typed_rows.append(row)
        numbers.append(number)
    if len(numbers) != len(set(numbers)):
        blockers.append(duplicate_blocker)
    return typed_rows, blockers


def build_report(
    repo_root: Path,
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
    live_observation_path: Path | None = None,
    checked_at: datetime | None = None,
    require_live_freshness: bool = False,
    expected_candidate_number: int | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    path = inventory_path if inventory_path.is_absolute() else root / inventory_path
    inventory = _load_json(path)
    blockers: list[str] = []
    if expected_candidate_number is not None and (
        isinstance(expected_candidate_number, bool)
        or expected_candidate_number <= 0
    ):
        blockers.append("expected_candidate_pull_request_number_invalid")
    if inventory.get("schema_version") != (
        "structural-analysis-repository-hygiene-inventory.v3"
    ):
        blockers.append("inventory_schema_version_invalid")
    observed_at = _parse_utc(inventory.get("observed_at"))
    if observed_at is None:
        blockers.append("inventory_observed_at_invalid")
    if not GIT_SHA_PATTERN.fullmatch(
        str(inventory.get("observed_default_branch_head", ""))
    ):
        blockers.append("observed_default_branch_head_invalid")
    external_actions = inventory.get("external_actions_performed")
    if not isinstance(external_actions, list) or external_actions != []:
        blockers.append("external_actions_performed_must_be_explicit_empty_list")
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
    pull_request_numbers = _pull_request_numbers(pull_requests)
    if len(pull_request_numbers) != len(set(pull_request_numbers)):
        blockers.append("open_pull_request_inventory_contains_duplicates")
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

    issue_scope = inventory.get("issue_hygiene_scope")
    open_issue_rows: list[dict[str, Any]] = []
    tracked_issue_rows: list[dict[str, Any]] = []
    superseded_rows: list[dict[str, Any]] = []
    if not isinstance(issue_scope, dict):
        blockers.append("issue_hygiene_scope_missing")
        issue_scope = {}
    else:
        if issue_scope.get("selection_rule") != (
            "all_open_issues_plus_declared_resolved_watchlist"
        ):
            blockers.append("issue_hygiene_scope_selection_rule_invalid")
        open_issue_rows, row_blockers = _validate_numbered_rows(
            issue_scope.get("open_issues"),
            missing_blocker="open_issue_inventory_missing",
            duplicate_blocker="open_issue_inventory_contains_duplicates",
        )
        blockers.extend(row_blockers)
        observed_open_issue_count = issue_scope.get("observed_open_issue_count")
        if (
            not isinstance(observed_open_issue_count, int)
            or observed_open_issue_count < 0
        ):
            blockers.append("observed_open_issue_count_invalid")
        elif observed_open_issue_count != len(open_issue_rows):
            blockers.append("open_issue_inventory_incomplete")
        allowed_classifications = {
            "active_source_extraction",
            "active_pull_request",
            "candidate_self",
            "implemented_but_open",
            "orphan",
        }
        for row in open_issue_rows:
            number = row["number"]
            if row.get("state") != "open":
                blockers.append(f"non_open_issue_in_open_inventory:{number}")
            if row.get("classification") not in allowed_classifications:
                blockers.append(f"open_issue_classification_invalid:{number}")
            if row.get("disposition_authorized") is not False:
                blockers.append(
                    f"issue_disposition_authority_must_not_be_inferred:{number}"
                )
            if not isinstance(row.get("blockers"), list):
                blockers.append(f"open_issue_blockers_missing:{number}")

        implemented_rows, row_blockers = _validate_numbered_rows(
            issue_scope.get("implemented_but_open_issues"),
            missing_blocker="implemented_but_open_issue_inventory_missing",
            duplicate_blocker="implemented_but_open_issue_inventory_duplicates",
        )
        blockers.extend(row_blockers)
        orphan_rows, row_blockers = _validate_numbered_rows(
            issue_scope.get("orphan_issues"),
            missing_blocker="orphan_issue_inventory_missing",
            duplicate_blocker="orphan_issue_inventory_duplicates",
        )
        blockers.extend(row_blockers)
        open_by_number = {row["number"]: row for row in open_issue_rows}
        expected_implemented = sorted(
            number
            for number, row in open_by_number.items()
            if row.get("classification") == "implemented_but_open"
        )
        expected_orphans = sorted(
            number
            for number, row in open_by_number.items()
            if row.get("classification") == "orphan"
        )
        if sorted(row["number"] for row in implemented_rows) != expected_implemented:
            blockers.append("implemented_but_open_issue_inventory_inconsistent")
        if sorted(row["number"] for row in orphan_rows) != expected_orphans:
            blockers.append("orphan_issue_inventory_inconsistent")
        if issue_scope.get("observed_implemented_but_open_issue_count") != len(
            implemented_rows
        ):
            blockers.append("implemented_but_open_issue_count_inconsistent")
        if issue_scope.get("observed_orphan_issue_count") != len(orphan_rows):
            blockers.append("orphan_issue_count_inconsistent")

        tracked_issue_rows, row_blockers = _validate_numbered_rows(
            issue_scope.get("resolved_issue_watchlist"),
            missing_blocker="resolved_issue_watchlist_missing",
            duplicate_blocker="resolved_issue_watchlist_duplicates",
        )
        blockers.extend(row_blockers)
        for row in tracked_issue_rows:
            number = row["number"]
            if row.get("state") != "closed":
                blockers.append(f"resolved_issue_not_closed:{number}")
            if row.get("state_reason") != "completed":
                blockers.append(f"resolved_issue_state_reason_invalid:{number}")
            if row.get("resolution") not in {
                "resolved_by_pull_request",
                "partially_resolved",
                "superseded",
            }:
                blockers.append(f"resolved_issue_disposition_invalid:{number}")
            if row.get("resolution") == "resolved_by_pull_request":
                resolved_by = row.get("resolved_by_pull_request")
                if not isinstance(resolved_by, int) or resolved_by <= 0:
                    blockers.append(f"resolved_issue_pull_request_invalid:{number}")

        superseded_rows, row_blockers = _validate_numbered_rows(
            inventory.get("superseded_pull_requests"),
            missing_blocker="superseded_pull_request_inventory_missing",
            duplicate_blocker="superseded_pull_request_inventory_duplicates",
        )
        blockers.extend(row_blockers)
        for row in superseded_rows:
            number = row["number"]
            if row.get("state") != "closed" or row.get("merged") is not False:
                blockers.append(f"superseded_pull_request_state_invalid:{number}")
            superseded_by_pr = row.get("superseded_by_pull_request")
            superseded_by_issue = row.get("superseded_by_issue")
            if (isinstance(superseded_by_pr, int) and superseded_by_pr > 0) == (
                isinstance(superseded_by_issue, int) and superseded_by_issue > 0
            ):
                blockers.append(f"superseded_pull_request_target_invalid:{number}")

    scope = inventory.get("open_pull_request_scope")
    candidate_number: int | None = None
    candidate_metadata_check_status: str | None = None
    if not isinstance(scope, dict):
        blockers.append("open_pull_request_scope_missing")
        scope = {}
    else:
        if scope.get("selection_rule") != (
            "all_open_pull_requests_except_declared_candidate_self"
        ):
            blockers.append("open_pull_request_scope_selection_rule_invalid")
        candidate = scope.get("candidate_pull_request")
        if not isinstance(candidate, dict):
            blockers.append("candidate_pull_request_exclusion_missing")
        else:
            raw_candidate_number = candidate.get("number")
            if isinstance(raw_candidate_number, int) and raw_candidate_number > 0:
                candidate_number = raw_candidate_number
            else:
                blockers.append("candidate_pull_request_number_invalid")
            if candidate.get("included_in_open_pull_requests") is not False:
                blockers.append("candidate_pull_request_must_be_excluded")
            if candidate.get("reason") != "inventory_candidate_self_observation":
                blockers.append("candidate_pull_request_exclusion_reason_invalid")
            if not GIT_SHA_PATTERN.fullmatch(str(candidate.get("head_sha", ""))):
                blockers.append("candidate_pull_request_head_sha_invalid")
            if not GIT_SHA_PATTERN.fullmatch(str(candidate.get("base_sha", ""))):
                blockers.append("candidate_pull_request_base_sha_invalid")
            if not GIT_SHA_PATTERN.fullmatch(str(candidate.get("merge_base_sha", ""))):
                blockers.append("candidate_pull_request_merge_base_sha_invalid")
            for key in (
                "commit_count",
                "changed_file_count",
                "ahead_by",
                "behind_by",
            ):
                value = candidate.get(key)
                if not isinstance(value, int) or value < 0:
                    blockers.append(f"candidate_pull_request_{key}_invalid")
            metadata = candidate.get("metadata_check_observation")
            if not isinstance(metadata, dict):
                blockers.append("candidate_metadata_check_observation_missing")
            else:
                candidate_metadata_check_status = str(metadata.get("status") or "")
                run_id = metadata.get("workflow_run_id")
                if not isinstance(run_id, int) or run_id <= 0:
                    blockers.append("candidate_metadata_check_run_id_invalid")
                if metadata.get("workflow_run_conclusion") != "failure":
                    blockers.append("candidate_metadata_check_conclusion_invalid")
                if metadata.get("candidate_head_validator_contract_pass") is not False:
                    blockers.append("candidate_metadata_head_validator_state_invalid")
                head_validator_blockers = metadata.get(
                    "candidate_head_validator_blockers"
                )
                if (
                    not isinstance(head_validator_blockers, list)
                    or not head_validator_blockers
                    or not all(
                        isinstance(item, str) and item
                        for item in head_validator_blockers
                    )
                ):
                    blockers.append("candidate_metadata_head_blockers_invalid")
                if metadata.get("current_worktree_validator_contract_pass") is not True:
                    blockers.append("candidate_metadata_current_validator_not_passing")
                closing_issue_numbers = metadata.get("closing_issue_numbers")
                if not isinstance(closing_issue_numbers, list) or not all(
                    isinstance(number, int) and number > 0
                    for number in closing_issue_numbers
                ):
                    blockers.append("candidate_metadata_closing_issue_numbers_invalid")
                if metadata.get("rerun_after_body_update_observed") is not False:
                    blockers.append("candidate_metadata_rerun_observation_invalid")
                if candidate_metadata_check_status != (
                    "validator_fix_not_on_candidate_head"
                ):
                    blockers.append("candidate_metadata_check_status_invalid")
                run_started_at = _parse_utc(metadata.get("workflow_run_started_at"))
                body_updated_at = _parse_utc(
                    metadata.get("pull_request_body_updated_at")
                )
                if run_started_at is None:
                    blockers.append("candidate_metadata_check_run_timestamp_invalid")
                if body_updated_at is None:
                    blockers.append("candidate_metadata_body_timestamp_invalid")
                if (
                    run_started_at is not None
                    and body_updated_at is not None
                    and run_started_at >= body_updated_at
                ):
                    blockers.append("candidate_metadata_failure_not_stale")
        if candidate_number in pull_request_numbers:
            blockers.append("candidate_pull_request_present_in_authoritative_rows")
        unfiltered_count = scope.get("observed_unfiltered_open_pull_request_count")
        if not isinstance(unfiltered_count, int) or unfiltered_count < 0:
            blockers.append("unfiltered_open_pull_request_count_invalid")
        elif (
            candidate_number is not None and unfiltered_count != len(pull_requests) + 1
        ):
            blockers.append("candidate_exclusion_count_inconsistent")

    freshness_contract = inventory.get("freshness_contract")
    max_age_seconds: int | None = None
    if not isinstance(freshness_contract, dict):
        blockers.append("freshness_contract_missing")
    else:
        max_age = freshness_contract.get("maximum_live_observation_age_seconds")
        if isinstance(max_age, int) and max_age > 0:
            max_age_seconds = max_age
        else:
            blockers.append("freshness_maximum_age_invalid")
        if (
            freshness_contract.get("live_observation_required_for_freshness")
            is not True
        ):
            blockers.append("live_observation_requirement_missing")
        if freshness_contract.get("offline_inventory_can_claim_freshness") is not False:
            blockers.append("offline_inventory_must_not_claim_freshness")
        required_live_fields = freshness_contract.get("required_live_fields")
        required_candidate_fields = {
            "candidate_pull_request.base_sha",
            "candidate_pull_request.head_sha",
            "candidate_pull_request.commit_count",
            "candidate_pull_request.changed_file_count",
            "candidate_pull_request.behind_by",
            "open_issues.number",
            "open_issues.state",
            "tracked_issues.number",
            "tracked_issues.state",
            "superseded_pull_requests.number",
            "superseded_pull_requests.state",
        }
        if not isinstance(
            required_live_fields, list
        ) or not required_candidate_fields.issubset(
            {str(item) for item in required_live_fields}
        ):
            blockers.append("candidate_live_freshness_fields_missing")

    freshness_blockers: list[str] = []
    live_observed_at: str | None = None
    if live_observation_path is None:
        if require_live_freshness:
            freshness_blockers.append("live_observation_missing")
    else:
        live_path = (
            live_observation_path
            if live_observation_path.is_absolute()
            else root / live_observation_path
        )
        live = _load_json(live_path)
        if live.get("schema_version") != "repository-hygiene-live-observation.v2":
            freshness_blockers.append("live_observation_schema_version_invalid")
        if live.get("repository") != inventory.get("repository"):
            freshness_blockers.append("live_observation_repository_mismatch")
        live_observed_at = live.get("observed_at")
        live_timestamp = _parse_utc(live_observed_at)
        if live_timestamp is None:
            freshness_blockers.append("live_observation_timestamp_invalid")
        elif max_age_seconds is not None:
            comparison_time = checked_at or datetime.now(timezone.utc)
            if comparison_time.tzinfo is None:
                comparison_time = comparison_time.replace(tzinfo=timezone.utc)
            age_seconds = (comparison_time - live_timestamp).total_seconds()
            if age_seconds < 0:
                freshness_blockers.append("live_observation_from_future")
            elif age_seconds > max_age_seconds:
                freshness_blockers.append("live_observation_stale")
        live_head = str(live.get("default_branch_head", ""))
        if not GIT_SHA_PATTERN.fullmatch(live_head):
            freshness_blockers.append("live_default_branch_head_invalid")
        elif live_head != inventory.get("observed_default_branch_head"):
            freshness_blockers.append("default_branch_head_drift")
        live_rows = live.get("open_pull_requests")
        if not isinstance(live_rows, list):
            freshness_blockers.append("live_open_pull_requests_missing")
            live_rows = []
        live_numbers = _pull_request_numbers(live_rows)
        if len(live_numbers) != len(set(live_numbers)):
            freshness_blockers.append("live_open_pull_requests_contain_duplicates")
        live_candidate = live.get("candidate_pull_request")
        live_candidate_number: int | None = None
        if not isinstance(live_candidate, dict):
            freshness_blockers.append("live_candidate_pull_request_missing")
        else:
            raw_live_candidate_number = live_candidate.get("number")
            if (
                isinstance(raw_live_candidate_number, int)
                and not isinstance(raw_live_candidate_number, bool)
                and raw_live_candidate_number > 0
            ):
                live_candidate_number = raw_live_candidate_number
            else:
                freshness_blockers.append(
                    "live_candidate_pull_request_number_invalid"
                )
            if (
                expected_candidate_number is not None
                and live_candidate_number != expected_candidate_number
            ):
                freshness_blockers.append(
                    "live_candidate_pull_request_number_mismatch"
                )
            if live_candidate.get("state") != "open":
                freshness_blockers.append("live_candidate_pull_request_not_open")
            if (
                live_candidate_number is not None
                and live_candidate_number not in live_numbers
            ):
                freshness_blockers.append(
                    "live_candidate_pull_request_missing_from_open_scope"
                )
            for key in ("head_sha", "base_sha", "merge_base_sha"):
                if not GIT_SHA_PATTERN.fullmatch(
                    str(live_candidate.get(key, ""))
                ):
                    freshness_blockers.append(
                        f"live_candidate_pull_request_{key}_invalid"
                    )
            for key in (
                "commit_count",
                "changed_file_count",
                "ahead_by",
                "behind_by",
                "comparison_changed_path_count",
            ):
                value = live_candidate.get(key)
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                ):
                    freshness_blockers.append(
                        f"live_candidate_pull_request_{key}_invalid"
                    )
            if live_candidate.get("comparison_files_complete") is not True:
                freshness_blockers.append(
                    "candidate_pull_request_comparison_files_incomplete"
                )
            if (
                isinstance(live_candidate.get("comparison_changed_path_count"), int)
                and isinstance(live_candidate.get("changed_file_count"), int)
                and live_candidate.get("comparison_changed_path_count")
                != live_candidate.get("changed_file_count")
            ):
                freshness_blockers.append(
                    "candidate_pull_request_comparison_path_count_drift"
                )
        excluded_candidate_numbers = {
            number
            for number in (candidate_number, live_candidate_number)
            if isinstance(number, int) and number > 0
        }
        scoped_live_rows = [
            row
            for row in live_rows
            if isinstance(row, dict)
            and row.get("number") not in excluded_candidate_numbers
        ]
        scoped_live_numbers = sorted(_pull_request_numbers(scoped_live_rows))
        if scoped_live_numbers != sorted(pull_request_numbers):
            freshness_blockers.append("open_pull_request_scope_drift")
        inventory_by_number = {
            row.get("number"): row for row in pull_requests if isinstance(row, dict)
        }
        for live_row in scoped_live_rows:
            number = live_row.get("number")
            recorded = inventory_by_number.get(number)
            if recorded is None:
                continue
            if live_row.get("state") != "open":
                freshness_blockers.append(f"live_pull_request_not_open:{number}")
            if live_row.get("head_sha") != recorded.get("head_sha"):
                freshness_blockers.append(f"open_pull_request_head_drift:{number}")
        live_open_issues = live.get("open_issues")
        if not isinstance(live_open_issues, list):
            freshness_blockers.append("live_open_issues_missing")
            live_open_issues = []
        candidate_issue_numbers = {
            row["number"]
            for row in open_issue_rows
            if row.get("classification") == "candidate_self"
        }
        live_open_issue_numbers = sorted(
            number
            for number in _pull_request_numbers(live_open_issues)
            if number not in candidate_issue_numbers
        )
        recorded_open_issue_numbers = sorted(
            row["number"]
            for row in open_issue_rows
            if row["number"] not in candidate_issue_numbers
        )
        if live_open_issue_numbers != recorded_open_issue_numbers:
            freshness_blockers.append("open_issue_scope_drift")
        recorded_open_issue_by_number = {row["number"]: row for row in open_issue_rows}
        for live_row in live_open_issues:
            if not isinstance(live_row, dict):
                freshness_blockers.append("invalid_live_open_issue_row")
                continue
            number = live_row.get("number")
            if number in candidate_issue_numbers:
                continue
            recorded = recorded_open_issue_by_number.get(number)
            if recorded is None:
                continue
            if live_row.get("state") != recorded.get("state"):
                freshness_blockers.append(f"open_issue_state_drift:{number}")

        live_tracked_issues = live.get("tracked_issues")
        if not isinstance(live_tracked_issues, list):
            freshness_blockers.append("live_tracked_issues_missing")
            live_tracked_issues = []
        live_tracked_by_number: dict[int, dict[str, Any]] = {
            number: row
            for row in live_tracked_issues
            if isinstance(row, dict)
            and isinstance((number := row.get("number")), int)
            and number > 0
        }
        recorded_tracked_by_number = {row["number"]: row for row in tracked_issue_rows}
        if sorted(live_tracked_by_number) != sorted(recorded_tracked_by_number):
            freshness_blockers.append("resolved_issue_watchlist_scope_drift")
        for number, recorded in recorded_tracked_by_number.items():
            matched_live_row = live_tracked_by_number.get(number)
            if matched_live_row is None:
                continue
            for key in ("state", "state_reason"):
                if matched_live_row.get(key) != recorded.get(key):
                    freshness_blockers.append(f"resolved_issue_{key}_drift:{number}")

        live_superseded = live.get("superseded_pull_requests")
        if not isinstance(live_superseded, list):
            freshness_blockers.append("live_superseded_pull_requests_missing")
            live_superseded = []
        live_superseded_by_number: dict[int, dict[str, Any]] = {
            number: row
            for row in live_superseded
            if isinstance(row, dict)
            and isinstance((number := row.get("number")), int)
            and number > 0
        }
        recorded_superseded_by_number = {row["number"]: row for row in superseded_rows}
        if sorted(live_superseded_by_number) != sorted(recorded_superseded_by_number):
            freshness_blockers.append("superseded_pull_request_scope_drift")
        for number, recorded in recorded_superseded_by_number.items():
            matched_live_row = live_superseded_by_number.get(number)
            if matched_live_row is None:
                continue
            for key in ("state", "merged"):
                if matched_live_row.get(key) != recorded.get(key):
                    freshness_blockers.append(
                        f"superseded_pull_request_{key}_drift:{number}"
                    )

    declared_closure_blockers = inventory.get("closure_blockers")
    if not isinstance(declared_closure_blockers, list):
        blockers.append("closure_blockers_missing")
        declared_closure_blockers = []
    derived_closure_blockers = [
        f"observed_open_pull_request_unresolved:{number}"
        for number in sorted(set(pull_request_numbers))
    ]
    remote_branch_inventory = inventory.get("remote_branch_inventory")
    if not isinstance(remote_branch_inventory, dict):
        blockers.append("remote_branch_inventory_missing")
        derived_closure_blockers.append("remote_branch_inventory_missing")
    else:
        if remote_branch_inventory.get("staleness_assessment_complete") is not True:
            derived_closure_blockers.append(
                "remote_branch_staleness_assessment_incomplete"
            )
        stale_count = remote_branch_inventory.get("observed_stale_remote_branch_count")
        if not isinstance(stale_count, int) or stale_count < 0:
            blockers.append("observed_stale_remote_branch_count_invalid")
            derived_closure_blockers.append(
                "observed_stale_remote_branch_count_invalid"
            )
        elif stale_count:
            derived_closure_blockers.append(
                f"observed_stale_remote_branches_present:{stale_count}"
            )
    effective_closure_blockers = sorted(
        {
            str(item).strip()
            for item in [
                *declared_closure_blockers,
                *derived_closure_blockers,
            ]
            if str(item).strip()
        }
    )
    declared_closure_pass = inventory.get("closure_pass")
    if not isinstance(declared_closure_pass, bool):
        blockers.append("closure_pass_boolean_required")
    elif declared_closure_pass != (not effective_closure_blockers):
        blockers.append("closure_pass_inconsistent_with_observed_state")

    blockers = sorted(dict.fromkeys([*blockers, *freshness_blockers]))
    freshness_status = (
        "unavailable"
        if live_observation_path is None
        else ("invalid" if freshness_blockers else "available")
    )
    return {
        "schema_version": "repository-hygiene-inventory-check.v3",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "freshness": {
            "status": freshness_status,
            "observed_at": live_observed_at,
            "blockers": sorted(dict.fromkeys(freshness_blockers)),
        },
        "closure_pass": bool(declared_closure_pass) and not effective_closure_blockers,
        "observed_at": inventory.get("observed_at"),
        "observed_default_branch_head": inventory.get("observed_default_branch_head"),
        "open_pull_request_count": len(pull_requests),
        "candidate_metadata_check_status": candidate_metadata_check_status,
        "open_issue_count": len(open_issue_rows),
        "implemented_but_open_issue_count": len(
            issue_scope.get("implemented_but_open_issues", [])
        ),
        "orphan_issue_count": len(issue_scope.get("orphan_issues", [])),
        "superseded_pull_request_count": len(superseded_rows),
        "stale_remote_branch_count": int(
            inventory.get("remote_branch_inventory", {}).get(
                "observed_stale_remote_branch_count", 0
            )
        ),
        "external_actions_performed": external_actions,
        "declared_closure_blockers": declared_closure_blockers,
        "derived_closure_blockers": sorted(set(derived_closure_blockers)),
        "closure_blockers": effective_closure_blockers,
        "blockers": blockers,
        "claim_boundary": inventory.get("claim_boundary", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--live-observation", type=Path)
    parser.add_argument("--require-live-freshness", action="store_true")
    parser.add_argument("--expected-candidate-number", type=int)
    parser.add_argument("--fail-open", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        args.repo_root,
        inventory_path=args.inventory,
        live_observation_path=args.live_observation,
        require_live_freshness=args.require_live_freshness,
        expected_candidate_number=args.expected_candidate_number,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"repository hygiene inventory: {report['status']} | "
            f"freshness={report['freshness']['status']} | "
            f"closure={'pass' if report['closure_pass'] else 'open'}"
        )
    if not report["contract_pass"]:
        return 1
    if args.fail_open and not report["closure_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
