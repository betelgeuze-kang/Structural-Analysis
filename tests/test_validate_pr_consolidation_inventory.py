from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_pr_consolidation_inventory import validate_inventory


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_INVENTORY = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v1.json").read_text(encoding="utf-8")
)
INVENTORY = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v2.json").read_text(encoding="utf-8")
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
EXPECTED_OPEN_PRS = (EXPECTED_HISTORICAL_OPEN_PRS - {277}) | {
    299,
    301,
    303,
    306,
    307,
    309,
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
    report = validate_inventory(HISTORICAL_INVENTORY)

    assert report["contract_pass"] is True
    assert set(HISTORICAL_INVENTORY["snapshot_open_pr_numbers"]) == (
        EXPECTED_HISTORICAL_OPEN_PRS
    )


def test_v2_delta_reconciles_previous_added_and_closed_sets() -> None:
    previous = set(INVENTORY["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(INVENTORY["added_since_previous"])
    closed = {row["pr_number"] for row in INVENTORY["closed_since_previous"]}

    assert previous == EXPECTED_HISTORICAL_OPEN_PRS
    assert added == {299, 301, 303, 306, 307, 309}
    assert closed == {277}
    assert (previous | added) - closed == EXPECTED_OPEN_PRS


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
    payload["added_since_previous"].remove(307)
    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "snapshot_delta_reconciliation_failed" in report["errors"]


def test_closed_pr_requires_authoritative_merged_state() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["closed_since_previous"][0]["merged"] = False
    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "closed_since_previous_merge_invalid:277" in report["errors"]


def test_unknown_close_disposition_is_rejected() -> None:
    payload = copy.deepcopy(INVENTORY)
    payload["entries"][0]["disposition"] = "close-now"
    report = validate_inventory(payload)
    assert report["contract_pass"] is False
    assert "unsafe_or_unknown_disposition:0" in report["errors"]


def test_every_legacy_pr_has_replacement_and_close_condition() -> None:
    for entry in INVENTORY["entries"]:
        if entry["base_class"] != "legacy-stack":
            continue
        assert entry["replacement_destination"].strip()
        assert entry["close_condition"].strip()
        assert entry["disposition"] != "merge-when-required-checks-pass"
