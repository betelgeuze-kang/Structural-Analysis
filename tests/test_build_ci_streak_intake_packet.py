from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ci_streak_intake_packet.py"
SPEC = importlib.util.spec_from_file_location("build_ci_streak_intake_packet", SCRIPT_PATH)
assert SPEC is not None
build_ci_streak_intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ci_streak_intake_packet)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_github_actions_evidence(path: Path, *, now: datetime, threshold: int = 30) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": threshold,
            "workflow_discovery": {"query_error": ""},
            "lanes": {
                "pr": {
                    "threshold": threshold,
                    "threshold_pass": True,
                    "consecutive_pass_count": threshold,
                    "run_count": threshold,
                    "queried_run_count": threshold,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["pull_request", "push"],
                    "local_workflow_runs_on": [
                        "${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || '[\"self-hosted\",\"linux\",\"x64\"]') }}"
                    ],
                    "local_self_hosted_runner_default": True,
                    "local_github_hosted_runner_default": False,
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "query_error": "",
                    "pull_request_run_source_present": True,
                },
                "nightly": {
                    "threshold": threshold,
                    "threshold_pass": True,
                    "consecutive_pass_count": threshold,
                    "run_count": threshold,
                    "queried_run_count": threshold,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["schedule", "workflow_dispatch"],
                    "local_workflow_runs_on": [
                        "${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || '[\"self-hosted\",\"linux\",\"x64\"]') }}"
                    ],
                    "local_self_hosted_runner_default": True,
                    "local_github_hosted_runner_default": False,
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "local_workflow_dispatch_trigger_present": True,
                    "query_error": "",
                },
            },
        },
    )


def test_ci_streak_intake_packet_surfaces_missing_pr_streak(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 2,
                    "local_consecutive_pass_count": 2,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 28,
                    "streak_source": "local_artifacts",
                    "github_actions_workflow_registered": True,
                    "github_actions_queried_run_count": 2,
                    "github_actions_filtered_run_count": 0,
                    "pull_request_run_source_present": False,
                    "github_actions_ignored_event_names": ["push"],
                    "owner_action": "No pull_request-triggered CI runs have been observed.",
                    "claim_boundary": "PR release streak credit requires tracked PR CI evidence.",
                    "blockers": [
                        "pr_pull_request_run_source_absent",
                        "pr_ci_30_consecutive_pass_evidence_missing",
                    ],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": True,
                    "consecutive_pass_count": 230,
                    "local_consecutive_pass_count": 230,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 0,
                    "streak_source": "local_artifacts",
                    "github_actions_workflow_registered": False,
                    "github_actions_query_error": "failed to get runs: could not find any workflows named Nightly Full Quality",
                    "local_workflow_present": True,
                    "owner_action": "No release action required; consecutive pass threshold is satisfied.",
                    "claim_boundary": "Nightly release streak credit requires tracked nightly CI evidence.",
                    "blockers": [],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": 30,
            "workflow_discovery": {"query_error": ""},
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "consecutive_pass_count": 0,
                    "threshold_pass": False,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["pull_request", "push"],
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "run_count": 0,
                    "pull_request_run_source_present": False,
                    "query_error": "",
                },
                "nightly": {
                    "threshold": 30,
                    "consecutive_pass_count": 0,
                    "threshold_pass": False,
                    "workflow_registered": False,
                    "registered_workflow": {},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["schedule", "workflow_dispatch"],
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "local_workflow_dispatch_trigger_present": True,
                    "run_count": 0,
                    "query_error": "failed to get runs",
                },
            }
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )
    rows = {row["lane"]: row for row in payload["lane_rows"]}

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE"
    assert payload["summary_line"] == (
        "CI streak intake: BLOCKED | lanes=0/2 | pr_missing=30 | "
        "nightly_missing=30 | blockers=12 | runner=not_evaluated"
    )
    assert payload["current_blocker_count"] == 12
    assert payload["release_area"] == "basic_ci"
    assert payload["release_area_blocker_ids"] == [
        "pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "pm_release::basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
    ]
    assert "ci_streak::pr:pr_ci_30_consecutive_pass_evidence_missing" in payload[
        "blocker_ids"
    ]
    assert "ci_streak::nightly:github_actions_query_error" in payload[
        "blocker_ids"
    ]
    assert payload["blocker_id_count"] == 14
    assert payload["evidence_intake_artifact_count"] == 5
    assert str(manifest) in payload["evidence_intake_artifacts"]
    assert payload["summary"]["release_area_blocker_count"] == 2
    assert payload["summary"]["blocker_id_count"] == 14
    assert payload["ci_release_credit_policy"]["required_consecutive_pass_count"] == 30
    assert payload["summary"]["source_evidence_pass"] is False
    assert payload["summary"]["source_evidence_freshness_pass"] is True
    assert payload["summary"]["pr_missing_consecutive_pass_count"] == 30
    assert payload["summary"]["pr_pull_request_run_source_present"] is False
    assert payload["summary"]["nightly_missing_consecutive_pass_count"] == 30
    assert rows["pr"]["threshold_pass"] is False
    assert rows["pr"]["github_actions_consecutive_pass_count"] == 0
    assert rows["pr"]["github_actions_workflow_registered"] is True
    assert rows["pr"]["github_actions_workflow_state"] == "active"
    assert rows["pr"]["local_required_trigger_present"] is True
    assert rows["pr"]["local_workflow_trigger_events"] == ["pull_request", "push"]
    assert rows["pr"]["pull_request_run_source_present"] is False
    assert rows["pr"]["github_actions_ignored_event_names"] == ["push"]
    assert rows["nightly"]["threshold_pass"] is False
    assert rows["nightly"]["github_actions_workflow_registered"] is False
    assert rows["nightly"]["local_required_trigger_present"] is True
    assert rows["nightly"]["local_workflow_trigger_events"] == ["schedule", "workflow_dispatch"]
    assert rows["nightly"]["github_actions_query_error"].startswith("failed to get runs")
    assert "pr:pr_ci_30_consecutive_pass_evidence_missing" in payload["current_blockers"]
    assert "pr:pr_pull_request_run_source_absent" in payload["current_blockers"]
    assert "nightly:github_actions_query_error" in payload["current_blockers"]
    assert payload["summary"]["nightly_github_actions_workflow_registered"] is False
    assert payload["summary"]["pr_local_required_trigger_present"] is True
    assert payload["summary"]["nightly_local_required_trigger_present"] is True
    assert any("build_ci_consecutive_pass_manifest.py" in command for command in payload["validation_commands"])


def test_ci_streak_intake_packet_blocks_closed_manifest_without_source_evidence(tmp_path: Path) -> None:
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=tmp_path / "missing-github.json",
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE"
    assert payload["status"] == "blocked"
    assert payload["summary_line"].startswith("CI streak intake: BLOCKED")
    assert payload["source_evidence"]["present"] is False
    assert "pr:github_actions_ci_streak_evidence_missing" in payload["current_blockers"]
    assert payload["summary"]["lane_pass_count"] == 0


def test_ci_streak_intake_packet_preserves_observed_partial_github_streak(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 12,
                    "local_consecutive_pass_count": 2,
                    "github_actions_consecutive_pass_count": 12,
                    "missing_consecutive_pass_count": 18,
                    "streak_source": "github_actions",
                    "github_actions_workflow_registered": True,
                    "github_actions_queried_run_count": 500,
                    "github_actions_filtered_run_count": 70,
                    "pull_request_run_source_present": True,
                    "github_actions_ignored_event_names": ["push"],
                    "owner_action": "Collect 18 additional consecutive successful PR CI run(s).",
                    "claim_boundary": "PR release streak credit requires tracked PR CI evidence.",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "local_consecutive_pass_count": 230,
                    "github_actions_consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 30,
                    "streak_source": "missing_tracked_ci_evidence",
                    "github_actions_workflow_registered": True,
                    "github_actions_queried_run_count": 11,
                    "github_actions_filtered_run_count": 11,
                    "owner_action": "Collect 30 additional consecutive successful nightly CI run(s).",
                    "claim_boundary": "Nightly release streak credit requires tracked nightly CI evidence.",
                    "blockers": ["nightly_ci_30_consecutive_pass_evidence_missing"],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": 30,
            "workflow_discovery": {"query_error": ""},
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 12,
                    "run_count": 70,
                    "queried_run_count": 500,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["pull_request", "push"],
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "query_error": "",
                    "pull_request_run_source_present": True,
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 11,
                    "queried_run_count": 11,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_workflow_trigger_events": ["schedule", "workflow_dispatch"],
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "local_workflow_dispatch_trigger_present": True,
                    "query_error": "",
                },
            },
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )
    rows = {row["lane"]: row for row in payload["lane_rows"]}
    markdown = build_ci_streak_intake_packet._markdown(payload)

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert rows["pr"]["threshold_pass"] is False
    assert rows["pr"]["consecutive_pass_count"] == 12
    assert rows["pr"]["github_actions_consecutive_pass_count"] == 12
    assert rows["pr"]["source_observation_usable"] is True
    assert rows["pr"]["missing_consecutive_pass_count"] == 18
    assert payload["summary"]["pr_missing_consecutive_pass_count"] == 18
    assert "| `pr` | `12/30` | `18` |" in markdown
    assert "Observed Streak" in markdown


def test_ci_streak_intake_packet_surfaces_job_start_blocker_queue(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "streak_source": "github_actions_job_start_blocked",
                    "owner_action": "Resolve queued PR run.",
                    "blockers": ["pr_github_actions_job_start_blocked"],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "owner_action": "Collect nightly passes.",
                    "blockers": ["nightly_ci_30_consecutive_pass_evidence_missing"],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": 30,
            "workflow_discovery": {"query_error": ""},
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 30,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "query_error": "",
                    "pull_request_run_source_present": True,
                    "job_start_blockers": [
                        {
                            "run_id": 123,
                            "url": "https://example.test/actions/runs/123",
                            "head_sha": "abc123",
                            "head_branch": "release-branch",
                            "reason_code": (
                                "github_actions_self_hosted_runner_queued_timeout"
                            ),
                            "queued_minutes": 42.5,
                            "message": (
                                "pr workflow run has remained queued for "
                                "42.5 minutes on a self-hosted runner lane."
                            ),
                        }
                    ],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 30,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "query_error": "",
                },
            },
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )
    rows = {row["lane"]: row for row in payload["lane_rows"]}
    queue = payload["job_start_blocker_queue"]
    markdown = build_ci_streak_intake_packet._markdown(payload)

    assert rows["pr"]["job_start_blocker_count"] == 1
    assert rows["pr"]["job_start_blockers"][0]["run_id"] == 123
    assert payload["summary"]["job_start_blocker_lane_count"] == 1
    assert payload["summary"]["job_start_blocker_count"] == 1
    assert queue == [payload["first_job_start_blocker"]]
    assert queue[0]["lane"] == "pr"
    assert queue[0]["first_run_id"] == 123
    assert queue[0]["first_head_sha"] == "abc123"
    assert queue[0]["first_head_branch"] == "release-branch"
    assert queue[0]["first_queued_minutes"] == 42.5
    assert queue[0]["reason_codes"] == [
        "github_actions_self_hosted_runner_queued_timeout"
    ]
    assert "Job Start Blocker Queue" in markdown
    assert "https://example.test/actions/runs/123" not in markdown


def test_ci_streak_intake_packet_surfaces_workflow_queue_backlog(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "streak_source": "github_actions_job_start_blocked",
                    "owner_action": "Collect PR passes.",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "owner_action": "Collect nightly passes.",
                    "blockers": ["nightly_ci_30_consecutive_pass_evidence_missing"],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": 30,
            "workflow_discovery": {"query_error": ""},
            "workflow_queue_backlog": [
                {
                    "lane": "pr",
                    "workflow": "CI",
                    "run_id": 456,
                    "url": "https://example.test/actions/runs/456",
                    "event": "push",
                    "head_sha": "def456",
                    "head_branch": "main",
                    "reason_code": "github_actions_self_hosted_runner_queued_timeout",
                    "queued_minutes": 61.0,
                    "message": "CI run has remained queued for 61.0 minutes.",
                }
            ],
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 0,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "query_error": "",
                    "pull_request_run_source_present": False,
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 0,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "query_error": "",
                },
            },
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )
    queue = payload["workflow_queue_backlog"]
    markdown = build_ci_streak_intake_packet._markdown(payload)

    assert payload["summary"]["workflow_queue_backlog_count"] == 1
    assert payload["summary"]["workflow_queue_backlog_lane_count"] == 1
    assert queue == [payload["first_workflow_queue_backlog"]]
    assert queue[0]["workflow"] == "CI"
    assert queue[0]["event"] == "push"
    assert queue[0]["run_id"] == 456
    assert queue[0]["head_branch"] == "main"
    assert "Workflow Queue Backlog" in markdown
    assert "| `CI` | `push` | `pr` | `61.0` | `456` |" in markdown


def test_ci_streak_intake_packet_surfaces_offline_self_hosted_runner(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "owner_action": "Collect 30 PR passes.",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "owner_action": "Collect 30 nightly passes.",
                    "blockers": ["nightly_ci_30_consecutive_pass_evidence_missing"],
                },
            },
        },
    )
    github_actions = _write_json(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "generated_at": now.isoformat(),
            "threshold": 30,
            "workflow_discovery": {"query_error": ""},
            "lanes": {
                "pr": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 30,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_pull_request_trigger_present": True,
                    "query_error": "",
                    "pull_request_run_source_present": True,
                },
                "nightly": {
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "run_count": 30,
                    "workflow_registered": True,
                    "registered_workflow": {"state": "active"},
                    "local_workflow_present": True,
                    "local_required_trigger_present": True,
                    "local_schedule_trigger_present": True,
                    "query_error": "",
                },
            },
        },
    )
    runner_status = _write_json(
        tmp_path / "github_actions_self_hosted_runner_status.json",
        {
            "schema_version": "github-actions-self-hosted-runner-status.v1",
            "contract_pass": False,
            "status": "blocked",
            "blockers": ["self_hosted_runner_matching_labels_not_online"],
            "required_labels": ["self-hosted", "linux", "x64"],
            "matching_runner_count": 1,
            "online_matching_runner_count": 0,
            "ready_runner_count": 0,
        },
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        runner_status_path=runner_status,
        now=now,
    )
    markdown = build_ci_streak_intake_packet._markdown(payload)

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert payload["runner_precondition"]["evaluated"] is True
    assert payload["runner_precondition"]["contract_pass"] is False
    assert payload["summary"]["runner_precondition_pass"] is False
    assert payload["summary"]["runner_online_matching_runner_count"] == 0
    assert (
        "runner:self_hosted_runner_matching_labels_not_online"
        in payload["current_blockers"]
    )
    assert payload["summary_line"] == (
        "CI streak intake: BLOCKED | lanes=0/2 | pr_missing=30 | "
        "nightly_missing=30 | blockers=9 | runner=blocked"
    )
    assert payload["current_blocker_count"] == 9
    assert "Runner Precondition" in markdown
    assert "self-hosted, linux, x64" in payload["runner_precondition"]["owner_action"]


def test_ci_streak_intake_packet_passes_closed_manifest_with_valid_source_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    github_actions = _valid_github_actions_evidence(
        tmp_path / "github_actions_ci_streak_evidence.json",
        now=now,
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["reason_code"] == "PASS"
    assert payload["summary_line"] == (
        "CI streak intake: PASS | lanes=2/2 | pr_missing=0 | "
        "nightly_missing=0 | blockers=0 | runner=not_evaluated"
    )
    assert payload["current_blocker_count"] == 0
    assert payload["current_blockers"] == []
    assert payload["release_area_blocker_ids"] == []
    assert payload["blocker_ids"] == []
    assert payload["blocker_id_count"] == 0
    assert payload["summary"]["lane_pass_count"] == 2
    assert payload["summary"]["source_evidence_pass"] is True
    assert payload["summary"]["pr_source_threshold_pass"] is True
    assert payload["summary"]["pr_local_required_trigger_present"] is True
    assert payload["summary"]["nightly_local_required_trigger_present"] is True
    assert payload["source_evidence"]["lanes"]["pr"]["workflow_active"] is True
    assert payload["source_evidence"]["lanes"]["pr"]["local_self_hosted_runner_default"] is True


def test_ci_streak_intake_packet_rejects_github_hosted_runner_default(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    github_actions = _valid_github_actions_evidence(
        tmp_path / "github_actions_ci_streak_evidence.json",
        now=now,
    )
    payload = json.loads(github_actions.read_text(encoding="utf-8"))
    payload["lanes"]["pr"]["local_workflow_runs_on"] = ["ubuntu-latest"]
    payload["lanes"]["pr"]["local_self_hosted_runner_default"] = False
    payload["lanes"]["pr"]["local_github_hosted_runner_default"] = True
    github_actions.write_text(json.dumps(payload), encoding="utf-8")

    packet = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )

    assert packet["contract_pass"] is False
    assert "pr:local_workflow_uses_github_hosted_runner" in packet["current_blockers"]
    assert "pr:local_self_hosted_runner_default_missing" in packet["current_blockers"]


def test_ci_streak_intake_packet_rejects_stale_source_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    github_actions = _valid_github_actions_evidence(
        tmp_path / "github_actions_ci_streak_evidence.json",
        now=now - timedelta(days=10),
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )

    assert payload["contract_pass"] is False
    assert payload["source_evidence"]["freshness_pass"] is False
    assert "pr:github_actions_ci_streak_evidence_stale" in payload["current_blockers"]


def test_ci_streak_intake_packet_rejects_source_threshold_mismatch(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": True,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    github_actions = _valid_github_actions_evidence(
        tmp_path / "github_actions_ci_streak_evidence.json",
        now=now,
        threshold=1,
    )

    payload = build_ci_streak_intake_packet.build_packet(
        manifest_path=manifest,
        github_actions_evidence_path=github_actions,
        now=now,
    )

    assert payload["contract_pass"] is False
    assert payload["source_evidence"]["threshold_match"] is False
    assert "pr:github_actions_ci_streak_evidence_threshold_mismatch" in payload["current_blockers"]


def test_ci_streak_intake_packet_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    manifest = _write_json(
        tmp_path / "ci_consecutive_pass_manifest.json",
        {
            "contract_pass": False,
            "threshold": 30,
            "lanes": {
                "pr": {"threshold": 30, "threshold_pass": False, "consecutive_pass_count": 2},
                "nightly": {"threshold": 30, "threshold_pass": True, "consecutive_pass_count": 30},
            },
        },
    )
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = build_ci_streak_intake_packet.main(
        [
            "--manifest",
            str(manifest),
            "--github-actions-evidence",
            str(tmp_path / "missing-github.json"),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CI Streak Intake Packet" in captured.out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["open_blocker_count"] > 1
    assert payload["status"] == "blocked"
    assert payload["current_blocker_count"] == payload["summary"]["open_blocker_count"]
    assert payload["reason_code"] == "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE"
    markdown = out_md.read_text(encoding="utf-8")
    assert "summary_line" in markdown
    assert "Validation Commands" in markdown
    assert "Blocker IDs" in markdown
    assert "Evidence Intake Artifacts" in markdown
    assert "CI Release Credit Policy" in markdown
    assert "Workflow Registered" in markdown
    assert "Source Evidence" in markdown
