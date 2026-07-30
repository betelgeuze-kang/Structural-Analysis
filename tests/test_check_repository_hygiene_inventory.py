from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_repository_hygiene_inventory.py"
SPEC = importlib.util.spec_from_file_location(
    "check_repository_hygiene_inventory", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def _source_payload() -> dict:
    source = ROOT / "artifacts/manifests/repository_hygiene_inventory.json"
    return json.loads(source.read_text(encoding="utf-8"))


def _write_json(tmp_path: Path, name: str, payload: dict) -> Path:
    target = tmp_path / name
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _matching_live_observation(payload: dict) -> dict:
    candidate = payload["open_pull_request_scope"]["candidate_pull_request"]
    return {
        "schema_version": "repository-hygiene-live-observation.v2",
        "repository": payload["repository"],
        "observed_at": "2026-07-28T06:03:37Z",
        "default_branch_head": payload["observed_default_branch_head"],
        "open_pull_requests": [
            {
                "number": row["number"],
                "state": "open",
                "head_sha": row["head_sha"],
            }
            for row in payload["open_pull_requests"]
        ]
        + [
            {
                "number": candidate["number"],
                "state": "open",
                "head_sha": candidate["head_sha"],
            }
        ],
        "candidate_pull_request": {
            "number": candidate["number"],
            "state": "open",
            "head_sha": candidate["head_sha"],
            "base_sha": candidate["base_sha"],
            "merge_base_sha": candidate["merge_base_sha"],
            "commit_count": candidate["commit_count"],
            "changed_file_count": candidate["changed_file_count"],
            "ahead_by": candidate["ahead_by"],
            "behind_by": candidate["behind_by"],
            "comparison_changed_path_count": candidate["changed_file_count"],
            "comparison_files_complete": True,
        },
        "open_issues": [
            {
                "number": row["number"],
                "state": row["state"],
                "state_reason": None,
            }
            for row in payload["issue_hygiene_scope"]["open_issues"]
        ],
        "tracked_issues": [
            {
                "number": row["number"],
                "state": row["state"],
                "state_reason": row["state_reason"],
            }
            for row in payload["issue_hygiene_scope"]["resolved_issue_watchlist"]
        ],
        "superseded_pull_requests": [
            {
                "number": row["number"],
                "state": row["state"],
                "merged": row["merged"],
            }
            for row in payload["superseded_pull_requests"]
        ],
    }


def test_hygiene_inventory_is_valid_but_does_not_claim_external_closure() -> None:
    report = inventory.build_report(ROOT)

    assert report["contract_pass"] is True
    assert report["freshness"]["status"] == "unavailable"
    assert report["closure_pass"] is False
    assert report["open_pull_request_count"] == 2
    assert report["candidate_metadata_check_status"] == (
        "validator_fix_not_on_candidate_head"
    )
    assert report["open_issue_count"] == 5
    assert report["implemented_but_open_issue_count"] == 0
    assert report["orphan_issue_count"] == 0
    assert report["superseded_pull_request_count"] == 7
    assert report["stale_remote_branch_count"] == 0
    assert report["external_actions_performed"] == []
    assert report["derived_closure_blockers"] == [
        "observed_open_pull_request_unresolved:215",
        "observed_open_pull_request_unresolved:221",
        "remote_branch_staleness_assessment_incomplete",
    ]
    assert "open_pr_215_conflicts_with_default_branch" in report["closure_blockers"]
    assert "external_pr_or_branch_mutation_not_authorized" in report["closure_blockers"]


def test_candidate_metadata_validator_drift_requires_ordered_observation(
    tmp_path,
) -> None:
    payload = _source_payload()
    metadata = payload["open_pull_request_scope"]["candidate_pull_request"][
        "metadata_check_observation"
    ]
    metadata["pull_request_body_updated_at"] = "2026-07-26T15:18:00Z"
    metadata["current_worktree_validator_contract_pass"] = False
    metadata["candidate_head_validator_blockers"] = []
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "candidate_metadata_current_validator_not_passing" in report["blockers"]
    assert "candidate_metadata_head_blockers_invalid" in report["blockers"]
    assert "candidate_metadata_failure_not_stale" in report["blockers"]


def test_external_actions_must_be_an_explicit_empty_list(tmp_path) -> None:
    for index, value in enumerate((None, "", {}, ["closed_pr_215"])):
        payload = _source_payload()
        if value is None:
            del payload["external_actions_performed"]
        else:
            payload["external_actions_performed"] = value
        target = _write_json(tmp_path, f"inventory-{index}.json", payload)

        report = inventory.build_report(ROOT, inventory_path=target)

        assert report["contract_pass"] is False
        assert (
            "external_actions_performed_must_be_explicit_empty_list"
            in report["blockers"]
        )


def test_closure_is_derived_from_observed_pr_and_branch_state(tmp_path) -> None:
    payload = _source_payload()
    payload["closure_blockers"] = []
    payload["closure_pass"] = True
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert report["closure_pass"] is False
    assert "closure_pass_inconsistent_with_observed_state" in report["blockers"]
    assert (
        "observed_open_pull_request_unresolved:215"
        in report["derived_closure_blockers"]
    )
    assert (
        "remote_branch_staleness_assessment_incomplete"
        in report["derived_closure_blockers"]
    )


def test_hygiene_inventory_rejects_incomplete_open_pull_request_enumeration(
    tmp_path,
) -> None:
    payload = _source_payload()
    payload["observed_open_pull_request_count"] = len(payload["open_pull_requests"]) + 1
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "open_pull_request_inventory_incomplete" in report["blockers"]


def test_hygiene_inventory_rejects_inferred_disposition_authority(tmp_path) -> None:
    payload = _source_payload()
    payload["open_pull_requests"][0]["disposition_authorized"] = True
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert any(
        blocker.startswith("disposition_authority_must_not_be_inferred")
        for blocker in report["blockers"]
    )


def test_hygiene_inventory_rejects_unclassified_and_incomplete_issue_rows(
    tmp_path,
) -> None:
    payload = _source_payload()
    payload["issue_hygiene_scope"]["open_issues"][0]["classification"] = "unknown"
    payload["issue_hygiene_scope"]["observed_open_issue_count"] += 1
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "open_issue_classification_invalid:143" in report["blockers"]
    assert "open_issue_inventory_incomplete" in report["blockers"]


def test_hygiene_inventory_rejects_bad_resolution_and_supersession(tmp_path) -> None:
    payload = _source_payload()
    payload["issue_hygiene_scope"]["resolved_issue_watchlist"][0]["state"] = "open"
    payload["superseded_pull_requests"][0]["superseded_by_issue"] = None
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "resolved_issue_not_closed:207" in report["blockers"]
    assert "superseded_pull_request_target_invalid:77" in report["blockers"]


def test_candidate_pull_request_exclusion_must_be_explicit(tmp_path) -> None:
    payload = _source_payload()
    del payload["open_pull_request_scope"]
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "open_pull_request_scope_missing" in report["blockers"]


def test_candidate_pull_request_cannot_appear_in_authoritative_rows(tmp_path) -> None:
    payload = _source_payload()
    candidate = payload["open_pull_request_scope"]["candidate_pull_request"]
    payload["open_pull_requests"].append(
        {
            "number": candidate["number"],
            "state": "open",
            "head_sha": candidate["head_sha"],
            "recommended_disposition": "candidate_self_observation_only",
            "disposition_authorized": False,
            "blockers": ["candidate_pull_request_not_in_authoritative_scope"],
        }
    )
    payload["observed_open_pull_request_count"] += 1
    payload["open_pull_request_scope"][
        "observed_unfiltered_open_pull_request_count"
    ] += 1
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "candidate_pull_request_present_in_authoritative_rows" in report["blockers"]


def test_candidate_pull_request_static_base_and_counts_are_validated(tmp_path) -> None:
    payload = _source_payload()
    candidate = payload["open_pull_request_scope"]["candidate_pull_request"]
    candidate["base_sha"] = "not-a-sha"
    candidate["changed_file_count"] = -1
    target = _write_json(tmp_path, "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "candidate_pull_request_base_sha_invalid" in report["blockers"]
    assert "candidate_pull_request_changed_file_count_invalid" in report["blockers"]


def test_matching_live_observation_makes_freshness_available(tmp_path) -> None:
    payload = _source_payload()
    live = _matching_live_observation(payload)
    live_path = _write_json(tmp_path, "live.json", live)

    report = inventory.build_report(
        ROOT,
        live_observation_path=live_path,
        checked_at=datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc),
        require_live_freshness=True,
    )

    assert report["contract_pass"] is True
    assert report["freshness"] == {
        "status": "available",
        "observed_at": "2026-07-28T06:03:37Z",
        "blockers": [],
    }


def test_live_observation_rejects_default_branch_drift(tmp_path) -> None:
    payload = _source_payload()
    live = _matching_live_observation(payload)
    live["default_branch_head"] = "a" * 40
    live_path = _write_json(tmp_path, "live.json", live)

    report = inventory.build_report(
        ROOT,
        live_observation_path=live_path,
        checked_at=datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc),
        require_live_freshness=True,
    )

    assert report["contract_pass"] is False
    assert report["freshness"]["status"] == "invalid"
    assert "default_branch_head_drift" in report["freshness"]["blockers"]


def test_live_observation_rejects_stale_timestamp_and_pr_scope_drift(tmp_path) -> None:
    payload = _source_payload()
    live = _matching_live_observation(payload)
    live["observed_at"] = "2026-07-26T06:03:37Z"
    live["open_pull_requests"] = [
        row for row in live["open_pull_requests"] if row["number"] != 221
    ]
    live_path = _write_json(tmp_path, "live.json", live)

    report = inventory.build_report(
        ROOT,
        live_observation_path=live_path,
        checked_at=datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc),
        require_live_freshness=True,
    )

    assert report["contract_pass"] is False
    assert "live_observation_stale" in report["freshness"]["blockers"]
    assert "open_pull_request_scope_drift" in report["freshness"]["blockers"]


def test_live_observation_rejects_candidate_base_and_count_drift(tmp_path) -> None:
    payload = _source_payload()
    live = _matching_live_observation(payload)
    live["candidate_pull_request"]["base_sha"] = "a" * 40
    live["candidate_pull_request"]["changed_file_count"] += 1
    live_path = _write_json(tmp_path, "live.json", live)

    report = inventory.build_report(
        ROOT,
        live_observation_path=live_path,
        checked_at=datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc),
        require_live_freshness=True,
    )

    assert report["contract_pass"] is False
    assert "candidate_pull_request_base_sha_drift" in report["freshness"]["blockers"]
    assert (
        "candidate_pull_request_changed_file_count_drift"
        in report["freshness"]["blockers"]
    )


def test_live_observation_rejects_issue_and_supersession_drift(tmp_path) -> None:
    payload = _source_payload()
    live = _matching_live_observation(payload)
    live["open_issues"] = [row for row in live["open_issues"] if row["number"] != 143]
    live["tracked_issues"][0]["state"] = "open"
    live["superseded_pull_requests"][0]["merged"] = True
    live_path = _write_json(tmp_path, "live.json", live)

    report = inventory.build_report(
        ROOT,
        live_observation_path=live_path,
        checked_at=datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc),
        require_live_freshness=True,
    )

    assert report["contract_pass"] is False
    assert "open_issue_scope_drift" in report["freshness"]["blockers"]
    assert "resolved_issue_state_drift:207" in report["freshness"]["blockers"]
    assert "superseded_pull_request_merged_drift:77" in report["freshness"]["blockers"]


def test_required_live_freshness_fails_closed_without_observation() -> None:
    report = inventory.build_report(ROOT, require_live_freshness=True)

    assert report["contract_pass"] is False
    assert report["freshness"]["status"] == "unavailable"
    assert report["freshness"]["blockers"] == ["live_observation_missing"]


def test_hygiene_workflow_fetches_candidate_detail_and_comparison() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "repository-hygiene-freshness.yml"
    ).read_text(encoding="utf-8")

    assert 'pulls/$candidate_number"' in workflow
    assert 'compare/$candidate_base_sha...$candidate_head_sha"' in workflow
    assert "--candidate-pull-request-json" in workflow
    assert "--candidate-compare-json" in workflow
    assert "--open-issues-json" in workflow
    assert "--tracked-issues-json" in workflow
    assert "--superseded-pull-requests-json" in workflow
    assert "gh api --paginate" in workflow
    assert "| jq -s 'add'" in workflow
    assert "--slurp" not in workflow
