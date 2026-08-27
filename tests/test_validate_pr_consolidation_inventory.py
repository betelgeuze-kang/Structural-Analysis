from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_pr_consolidation_inventory import validate_inventory


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_V1 = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v1.json").read_text(encoding="utf-8")
)
HISTORICAL_V2 = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v2.json").read_text(encoding="utf-8")
)
INVENTORY = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v3.json").read_text(encoding="utf-8")
)
EXPECTED_HISTORICAL_OPEN_PRS = {
    248,
    249,
    250,
    251,
    252,
    264,
    267,
    269,
    271,
    272,
    273,
    274,
    275,
    276,
    277,
    279,
    284,
    286,
    288,
    294,
}
EXPECTED_V2_OPEN_PRS = (EXPECTED_HISTORICAL_OPEN_PRS - {277}) | {
    299,
    301,
    303,
    306,
    307,
    309,
}
EXPECTED_OPEN_PRS = {
    286,
    288,
    372,
    373,
    374,
    375,
    376,
    377,
    379,
    380,
    381,
    382,
    383,
    389,
    391,
}


def test_current_inventory_is_complete_and_fail_closed() -> None:
    report = validate_inventory(INVENTORY)
    assert report["contract_pass"] is True
    assert report["entry_count"] == len(EXPECTED_OPEN_PRS)
    assert set(INVENTORY["snapshot_open_pr_numbers"]) == EXPECTED_OPEN_PRS
    assert {entry["pr_number"] for entry in INVENTORY["entries"]} == EXPECTED_OPEN_PRS
    assert "no numerical" in report["claim_boundary"]
    assert "no" in report["claim_boundary"]
    assert "release authority" in report["claim_boundary"]


def test_historical_inventory_remains_valid_and_unchanged() -> None:
    v1_report = validate_inventory(HISTORICAL_V1)
    v2_report = validate_inventory(HISTORICAL_V2)

    assert v1_report["contract_pass"] is True
    assert v2_report["contract_pass"] is True
    assert set(HISTORICAL_V1["snapshot_open_pr_numbers"]) == (
        EXPECTED_HISTORICAL_OPEN_PRS
    )
    assert set(HISTORICAL_V2["snapshot_open_pr_numbers"]) == EXPECTED_V2_OPEN_PRS


def test_v2_delta_reconciles_previous_added_and_closed_sets() -> None:
    previous = set(HISTORICAL_V2["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(HISTORICAL_V2["added_since_previous"])
    closed = {row["pr_number"] for row in HISTORICAL_V2["closed_since_previous"]}

    assert previous == EXPECTED_HISTORICAL_OPEN_PRS
    assert added == {299, 301, 303, 306, 307, 309}
    assert closed == {277}
    assert (previous | added) - closed == EXPECTED_V2_OPEN_PRS


def test_v3_delta_records_merged_superseded_and_retired_rows() -> None:
    previous = set(INVENTORY["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(INVENTORY["added_since_previous"])
    closed = {row["pr_number"] for row in INVENTORY["closed_since_previous"]}
    resolutions = {row["resolution"] for row in INVENTORY["closed_since_previous"]}

    assert previous == EXPECTED_V2_OPEN_PRS
    assert added == {
        372,
        373,
        374,
        375,
        376,
        377,
        379,
        380,
        381,
        382,
        383,
        389,
        391,
    }
    assert (previous | added) - closed == EXPECTED_OPEN_PRS
    assert resolutions == {
        "merged",
        "retired_out_of_scope",
        "superseded_by_pull_requests",
    }
    assert set(INVENTORY["active_implementation_pr_numbers"]) == {
        374,
        379,
        389,
        391,
    }


def test_duplicate_pr_number_is_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["entries"][1]["pr_number"] = payload["entries"][0]["pr_number"]
    report = validate_inventory(payload)
    assert report["contract_pass"] is False
    assert "duplicate_entry_pr_number" in report["errors"]


def test_snapshot_entry_gap_is_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    removed = payload["entries"].pop()
    report = validate_inventory(payload)
    assert report["contract_pass"] is False
    assert f"snapshot_prs_missing_entries:{removed['pr_number']}" in report["errors"]


def test_snapshot_delta_drift_is_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["added_since_previous"].remove(372)
    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "snapshot_delta_reconciliation_failed" in report["errors"]


def test_embedded_previous_snapshot_must_match_referenced_inventory() -> None:
    payload = copy.deepcopy(INVENTORY)
    removed = payload["previous_snapshot"]["snapshot_open_pr_numbers"].pop()
    payload["closed_since_previous"] = [
        row
        for row in payload["closed_since_previous"]
        if row["pr_number"] != removed
    ]

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "previous_snapshot_file_numbers_mismatch" in report["errors"]


def test_closed_pr_requires_authoritative_merged_state() -> None:
    payload = copy.deepcopy(HISTORICAL_V2)
    payload["closed_since_previous"][0]["merged"] = False
    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "closed_since_previous_merge_invalid:277" in report["errors"]


def test_v3_supersession_requires_replacement_pull_request() -> None:
    payload = copy.deepcopy(INVENTORY)
    row = next(
        row
        for row in payload["closed_since_previous"]
        if row["resolution"] == "superseded_by_pull_requests"
    )
    row["superseded_by_pull_requests"] = []

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert (
        f"closed_since_previous_replacements_invalid:{row['pr_number']}"
        in report["errors"]
    )


def test_v3_supersession_cannot_reference_itself() -> None:
    payload = copy.deepcopy(INVENTORY)
    row = next(
        row
        for row in payload["closed_since_previous"]
        if row["resolution"] == "superseded_by_pull_requests"
    )
    row["superseded_by_pull_requests"] = [row["pr_number"]]

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert (
        f"closed_since_previous_replacements_self_reference:{row['pr_number']}"
        in report["errors"]
    )


def test_v3_retirement_requires_scope_decision_issue() -> None:
    payload = copy.deepcopy(INVENTORY)
    row = next(
        row
        for row in payload["closed_since_previous"]
        if row["resolution"] == "retired_out_of_scope"
    )
    row.pop("scope_decision_issue")

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert (
        f"closed_since_previous_scope_decision_invalid:{row['pr_number']}"
        in report["errors"]
    )


def test_v3_active_implementation_count_fails_closed() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["active_implementation_pr_numbers"].append(286)
    next(entry for entry in payload["entries"] if entry["pr_number"] == 286)[
        "active_implementation"
    ] = True

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "active_implementation_pr_target_exceeded" in report["errors"]


def test_unknown_close_disposition_is_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["entries"][0]["disposition"] = "close-now"
    report = validate_inventory(payload)
    assert report["contract_pass"] is False
    assert "unsafe_or_unknown_disposition:0" in report["errors"]


def test_legacy_stack_cannot_be_marked_for_direct_merge() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["entries"][0]["base_class"] = "legacy-stack"
    payload["entries"][0]["disposition"] = "merge-when-required-checks-pass"

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "legacy_stack_merge_disposition_invalid:0" in report["errors"]


def test_non_object_entry_returns_a_fail_closed_report() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["entries"][0] = "not-an-entry"

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "entry_not_object:0" in report["errors"]


def test_source_commit_must_be_a_lowercase_git_sha() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["source_commit"] = "z" * 40

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "invalid_source_commit" in report["errors"]


def test_closure_timestamps_are_parsed_as_utc_datetimes() -> None:
    payload = copy.deepcopy(INVENTORY)
    row = payload["closed_since_previous"][0]
    row["closed_at"] = "not-a-timeZ"

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert (
        f"closed_since_previous_closed_at_invalid:{row['pr_number']}"
        in report["errors"]
    )


def test_boolean_pr_numbers_are_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    original = payload["snapshot_open_pr_numbers"][0]
    payload["snapshot_open_pr_numbers"][0] = True
    next(entry for entry in payload["entries"] if entry["pr_number"] == original)[
        "pr_number"
    ] = True

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "invalid_snapshot_open_pr_numbers" in report["errors"]
    assert "invalid_pr_number:0" in report["errors"]


def test_claim_boundary_must_match_the_canonical_non_authority_text() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["claim_boundary"] = (
        "This inventory does not merge code, but it grants release authority and "
        "proves numerical correctness."
    )

    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "claim_boundary_missing_or_unsafe" in report["errors"]


def test_every_legacy_pr_has_replacement_and_close_condition() -> None:
    for entry in INVENTORY["entries"]:
        if entry["base_class"] != "legacy-stack":
            continue
        assert entry["replacement_destination"].strip()
        assert entry["close_condition"].strip()
        assert entry["disposition"] != "merge-when-required-checks-pass"
