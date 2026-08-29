from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.validate_pr_consolidation_inventory import (
    CANONICAL_CLAIM_BOUNDARIES,
    validate_inventory,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_V1 = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v1.json").read_text(encoding="utf-8")
)
HISTORICAL_V2 = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v2.json").read_text(encoding="utf-8")
)
HISTORICAL_V3 = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v3.json").read_text(encoding="utf-8")
)
INVENTORY = json.loads(
    (ROOT / "docs/open-pr-consolidation-inventory.v4.json").read_text(encoding="utf-8")
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
EXPECTED_V3_OPEN_PRS = {
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
EXPECTED_OPEN_PRS = {372}
HISTORICAL_INVENTORY_SHA256 = {
    "open-pr-consolidation-inventory.v1.json": (
        "706bedb44f2a5a6fe77c37339938918211d45827646c29b4937c98873a58bd3e"
    ),
    "open-pr-consolidation-inventory.v2.json": (
        "726a007d7143e00e5e546599728e47885d86e8ed943c757c310f949573faab4f"
    ),
    "open-pr-consolidation-inventory.v3.json": (
        "2fe3dd88dd7f7e4de989233a1aa477b662a6fd390c42a2b9f052a44fceadce0b"
    ),
}


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_git_chain(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Inventory Test")
    _git(repository, "config", "user.email", "inventory@example.invalid")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "base")
    base_branch = _git(repository, "branch", "--show-current")
    _git(repository, "checkout", "--quiet", "-b", "replacement")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "superseded head")
    head_commit = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "replacement head")
    replacement_head = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "--quiet", base_branch)
    _git(repository, "merge", "--quiet", "--no-ff", "replacement")
    replacement_merge = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "snapshot source")
    source_commit = _git(repository, "rev-parse", "HEAD")
    return repository, head_commit, replacement_head, replacement_merge, source_commit


def _make_v4_payload(
    *,
    head_commit: str,
    replacement_head: str,
    replacement_merge: str,
    source_commit: str,
) -> dict[str, object]:
    payload = copy.deepcopy(HISTORICAL_V3)
    payload.update(
        {
            "schema_version": "open-pr-consolidation-inventory.v4",
            "snapshot_at": "2026-08-28T00:00:01Z",
            "source_commit": source_commit,
            "previous_snapshot": {
                "schema_version": "open-pr-consolidation-inventory.v3",
                "path": "docs/open-pr-consolidation-inventory.v3.json",
                "content_sha256": HISTORICAL_INVENTORY_SHA256[
                    "open-pr-consolidation-inventory.v3.json"
                ],
                "snapshot_open_pr_numbers": HISTORICAL_V3[
                    "snapshot_open_pr_numbers"
                ],
            },
            "added_since_previous": [9999],
            "closed_since_previous": [
                {
                    "pr_number": 9999,
                    "state": "closed",
                    "merged": False,
                    "closed_at": "2026-08-28T00:00:00Z",
                    "resolution": "superseded_by_pull_requests",
                    "superseded_by_pull_requests": [9998],
                    "head_commit": head_commit,
                    "supersession_proof": {
                        "replacement_pr_number": 9998,
                        "replacement_head_commit": replacement_head,
                        "replacement_merge_commit": replacement_merge,
                    },
                    "reason": "The replacement merge contains the exact superseded head.",
                }
            ],
            "claim_boundary": CANONICAL_CLAIM_BOUNDARIES[
                "open-pr-consolidation-inventory.v4"
            ],
        }
    )
    return payload


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
    v3_report = validate_inventory(HISTORICAL_V3)

    assert v1_report["contract_pass"] is True
    assert v2_report["contract_pass"] is True
    assert v3_report["contract_pass"] is True
    assert set(HISTORICAL_V1["snapshot_open_pr_numbers"]) == (
        EXPECTED_HISTORICAL_OPEN_PRS
    )
    assert set(HISTORICAL_V2["snapshot_open_pr_numbers"]) == EXPECTED_V2_OPEN_PRS
    assert set(HISTORICAL_V3["snapshot_open_pr_numbers"]) == EXPECTED_V3_OPEN_PRS


def test_historical_inventory_bytes_are_immutable() -> None:
    for filename, expected_hash in HISTORICAL_INVENTORY_SHA256.items():
        inventory_bytes = (ROOT / "docs" / filename).read_bytes()
        assert hashlib.sha256(inventory_bytes).hexdigest() == expected_hash


def test_v4_allows_a_pr_added_and_closed_between_snapshots(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is True
    assert report["schema_version"] == ("open-pr-consolidation-inventory-validation.v4")


def test_v4_rejects_a_supersession_without_local_ancestry(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    _git(repository, "checkout", "--quiet", "--orphan", "unrelated")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "unrelated")
    unrelated_commit = _git(repository, "rev-parse", "HEAD")
    payload = _make_v4_payload(
        head_commit=unrelated_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert any(
        error.startswith("local_git_ancestry_failed:superseded_head_to_replacement")
        for error in report["errors"]
    )


def test_v4_rejects_missing_replacement_merge_sha(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    payload["closed_since_previous"][0]["supersession_proof"].pop(
        "replacement_merge_commit"
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert (
        "closed_since_previous_replacement_merge_commit_invalid:9999"
        in report["errors"]
    )


def test_v4_replacement_sha_must_be_a_merge_commit(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, _replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=source_commit,
        source_commit=source_commit,
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert any(
        error.startswith("local_git_merge_commit_invalid:replacement_head_to_merge")
        for error in report["errors"]
    )


def test_v4_replacement_head_must_be_a_direct_merge_parent(tmp_path: Path) -> None:
    repository, head_commit, _replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=head_commit,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert any(
        error.startswith("local_git_merge_parent_missing:replacement_head_to_merge")
        for error in report["errors"]
    )


def test_v4_replacement_merge_must_be_in_snapshot_source(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, _source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=head_commit,
    )

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert any(
        error.startswith("local_git_ancestry_failed:replacement_merge_to_source")
        for error in report["errors"]
    )


def test_v4_accepts_a_normally_merged_pr(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    closure = payload["closed_since_previous"][0]
    closure.update(
        {
            "merged": True,
            "merged_at": closure["closed_at"],
            "resolution": "merged",
            "head_commit": replacement_head,
            "merge_commit": replacement_merge,
        }
    )
    closure.pop("superseded_by_pull_requests")
    closure.pop("supersession_proof")

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is True


def test_v4_accepts_a_pr_merged_through_a_carrier_pr(tmp_path: Path) -> None:
    repository, head_commit, carrier_head, carrier_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=carrier_head,
        replacement_merge=carrier_merge,
        source_commit=source_commit,
    )
    closure = payload["closed_since_previous"][0]
    closure.update(
        {
            "merged": True,
            "merged_at": closure["closed_at"],
            "resolution": "merged_via_pull_request",
            "head_commit": head_commit,
            "merge_commit": carrier_merge,
            "merged_via_pull_request_proof": {
                "carrier_pr_number": 9998,
                "carrier_head_commit": carrier_head,
                "carrier_merge_commit": carrier_merge,
            },
        }
    )
    closure.pop("superseded_by_pull_requests")
    closure.pop("supersession_proof")

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is True


def test_v4_rejects_a_carrier_merge_commit_mismatch(tmp_path: Path) -> None:
    repository, head_commit, carrier_head, carrier_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=carrier_head,
        replacement_merge=carrier_merge,
        source_commit=source_commit,
    )
    closure = payload["closed_since_previous"][0]
    closure.update(
        {
            "merged": True,
            "merged_at": closure["closed_at"],
            "resolution": "merged_via_pull_request",
            "head_commit": head_commit,
            "merge_commit": source_commit,
            "merged_via_pull_request_proof": {
                "carrier_pr_number": 9998,
                "carrier_head_commit": carrier_head,
                "carrier_merge_commit": carrier_merge,
            },
        }
    )
    closure.pop("superseded_by_pull_requests")
    closure.pop("supersession_proof")

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert (
        "closed_since_previous_merge_carrier_commit_mismatch:9999"
        in report["errors"]
    )


def test_v4_cli_uses_the_declared_local_repository(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    inventory_path = tmp_path / "inventory.v4.json"
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_pr_consolidation_inventory.py"),
            str(inventory_path),
            "--repository-root",
            str(repository),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["contract_pass"] is True


def test_v4_rejects_missing_local_git_repository(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )

    report = validate_inventory(payload, repository_root=repository / "does-not-exist")

    assert report["contract_pass"] is False
    assert "local_git_repository_unavailable" in report["errors"]


def test_v4_snapshot_must_be_strict_utc_and_after_previous(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    payload["snapshot_at"] = "2026-08-28T00:00:01+00:00"

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert "invalid_snapshot_at" in report["errors"]

    payload["snapshot_at"] = "2026-8-28T00:00:01Z"
    report = validate_inventory(payload, repository_root=repository)
    assert "invalid_snapshot_at" in report["errors"]

    payload["snapshot_at"] = HISTORICAL_V3["snapshot_at"]
    report = validate_inventory(payload, repository_root=repository)
    assert "snapshot_at_not_after_previous_snapshot" in report["errors"]


def test_v4_rejects_closure_after_snapshot(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    payload["closed_since_previous"][0]["closed_at"] = "2026-08-28T00:00:02Z"

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert "closed_since_previous_after_snapshot:9999" in report["errors"]


def test_v4_previous_snapshot_hash_is_bound(tmp_path: Path) -> None:
    repository, head_commit, replacement_head, replacement_merge, source_commit = (
        _make_git_chain(tmp_path)
    )
    payload = _make_v4_payload(
        head_commit=head_commit,
        replacement_head=replacement_head,
        replacement_merge=replacement_merge,
        source_commit=source_commit,
    )
    payload["previous_snapshot"]["content_sha256"] = "0" * 64

    report = validate_inventory(payload, repository_root=repository)

    assert report["contract_pass"] is False
    assert "previous_snapshot_content_sha256_mismatch" in report["errors"]


def test_v2_delta_reconciles_previous_added_and_closed_sets() -> None:
    previous = set(HISTORICAL_V2["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(HISTORICAL_V2["added_since_previous"])
    closed = {row["pr_number"] for row in HISTORICAL_V2["closed_since_previous"]}

    assert previous == EXPECTED_HISTORICAL_OPEN_PRS
    assert added == {299, 301, 303, 306, 307, 309}
    assert closed == {277}
    assert (previous | added) - closed == EXPECTED_V2_OPEN_PRS


def test_v3_delta_records_merged_superseded_and_retired_rows() -> None:
    previous = set(HISTORICAL_V3["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(HISTORICAL_V3["added_since_previous"])
    closed = {
        row["pr_number"] for row in HISTORICAL_V3["closed_since_previous"]
    }
    resolutions = {
        row["resolution"] for row in HISTORICAL_V3["closed_since_previous"]
    }

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
    assert (previous | added) - closed == EXPECTED_V3_OPEN_PRS
    assert resolutions == {
        "merged",
        "retired_out_of_scope",
        "superseded_by_pull_requests",
    }
    assert set(HISTORICAL_V3["active_implementation_pr_numbers"]) == {
        374,
        379,
        389,
        391,
    }


def test_v4_delta_reconciles_the_final_pre_replacement_snapshot() -> None:
    previous = set(INVENTORY["previous_snapshot"]["snapshot_open_pr_numbers"])
    added = set(INVENTORY["added_since_previous"])
    closed = {row["pr_number"] for row in INVENTORY["closed_since_previous"]}
    resolutions = {row["resolution"] for row in INVENTORY["closed_since_previous"]}

    assert INVENTORY["schema_version"] == "open-pr-consolidation-inventory.v4"
    assert INVENTORY["source_commit"] == (
        "95ffcc59b7fa2b97d547483dca76561f6bc32e14"
    )
    assert previous == EXPECTED_V3_OPEN_PRS
    assert added == {393, 394, 396, 397, 402}
    assert (previous | added) - closed == EXPECTED_OPEN_PRS
    assert resolutions == {
        "merged",
        "merged_via_pull_request",
        "superseded_by_pull_requests",
    }
    assert INVENTORY["active_implementation_pr_numbers"] == []


def test_duplicate_pr_number_is_rejected() -> None:
    payload = copy.deepcopy(HISTORICAL_V3)
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
    payload["added_since_previous"].remove(393)
    report = validate_inventory(payload)

    assert report["contract_pass"] is False
    assert "closed_since_previous_not_in_previous_or_added" in report["errors"]


def test_embedded_previous_snapshot_must_match_referenced_inventory() -> None:
    payload = copy.deepcopy(INVENTORY)
    removed = payload["previous_snapshot"]["snapshot_open_pr_numbers"].pop()
    payload["closed_since_previous"] = [
        row for row in payload["closed_since_previous"] if row["pr_number"] != removed
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
    payload = copy.deepcopy(HISTORICAL_V3)
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
    payload = copy.deepcopy(HISTORICAL_V3)
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
    payload = copy.deepcopy(HISTORICAL_V3)
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
    payload = copy.deepcopy(HISTORICAL_V3)
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
    for entry in HISTORICAL_V3["entries"] + INVENTORY["entries"]:
        if entry["base_class"] != "legacy-stack":
            continue
        assert entry["replacement_destination"].strip()
        assert entry["close_condition"].strip()
        assert entry["disposition"] != "merge-when-required-checks-pass"
