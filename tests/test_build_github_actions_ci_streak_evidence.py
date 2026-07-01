from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_github_actions_ci_streak_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_github_actions_ci_streak_evidence", SCRIPT_PATH)
assert SPEC is not None
build_github_actions_ci_streak_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_github_actions_ci_streak_evidence)


def _run(run_id: int, event: str, conclusion: str, created_at: datetime) -> dict[str, object]:
    return {
        "databaseId": run_id,
        "event": event,
        "conclusion": conclusion,
        "status": "completed",
        "headSha": f"sha-{run_id}",
        "headBranch": "feature",
        "createdAt": created_at.isoformat().replace("+00:00", "Z"),
        "updatedAt": created_at.isoformat().replace("+00:00", "Z"),
        "url": f"https://example.test/actions/runs/{run_id}",
        "name": "CI",
    }


def _queued_run(run_id: int, event: str, created_at: datetime) -> dict[str, object]:
    row = _run(run_id, event, "", created_at)
    row["status"] = "queued"
    return row


def test_build_evidence_filters_pr_and_nightly_events_for_streaks() -> None:
    base = datetime(2026, 6, 16, tzinfo=timezone.utc)
    pr_rows = [_run(i, "pull_request", "success", base - timedelta(minutes=i)) for i in range(3)]
    pr_rows.append(_run(99, "push", "failure", base + timedelta(minutes=1)))
    nightly_rows = [
        _run(200, "schedule", "success", base),
        _run(201, "workflow_dispatch", "success", base - timedelta(minutes=1)),
        _run(202, "push", "failure", base + timedelta(minutes=1)),
    ]

    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=pr_rows,
        nightly_rows=nightly_rows,
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
            },
        ],
    )

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 3
    assert payload["lanes"]["pr"]["threshold_pass"] is True
    assert payload["lanes"]["nightly"]["consecutive_pass_count"] == 2
    assert payload["lanes"]["nightly"]["threshold_pass"] is False
    assert all(row["event"] != "push" for row in payload["lanes"]["pr"]["rows"])
    assert payload["lanes"]["pr"]["queried_run_count"] == 4
    assert payload["lanes"]["pr"]["ignored_event_count"] == 1
    assert payload["lanes"]["pr"]["workflow_registered"] is True
    assert payload["lanes"]["pr"]["pull_request_run_source_present"] is True
    assert payload["lanes"]["pr"]["local_workflow_trigger_events"] == ["pull_request", "push"]
    assert payload["lanes"]["pr"]["local_required_trigger_present"] is True
    assert payload["lanes"]["pr"]["local_pull_request_trigger_present"] is True
    assert payload["lanes"]["nightly"]["local_schedule_trigger_present"] is True
    assert payload["lanes"]["nightly"]["local_workflow_dispatch_trigger_present"] is True
    assert "pr_pull_request_run_source_absent" not in payload["lanes"]["pr"]["blockers"]
    assert payload["summary"]["nightly_workflow_registered"] is True
    assert payload["summary"]["pr_local_required_trigger_present"] is True
    assert payload["summary"]["nightly_local_required_trigger_present"] is True


def test_cli_default_limit_retains_pr_runs_when_push_runs_are_dense() -> None:
    parser = build_github_actions_ci_streak_evidence.build_parser()
    args = parser.parse_args([])

    assert args.limit == build_github_actions_ci_streak_evidence.DEFAULT_LIMIT
    assert args.limit >= 500


def test_build_evidence_flags_missing_pull_request_run_source_when_only_push_events() -> None:
    base = datetime(2026, 6, 16, tzinfo=timezone.utc)
    pr_rows = [_run(i, "push", "success", base - timedelta(minutes=i)) for i in range(3)]

    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=pr_rows,
        nightly_rows=[],
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
            },
        ],
    )

    pr = payload["lanes"]["pr"]

    assert pr["workflow_registered"] is True
    assert pr["queried_run_count"] == 3
    assert pr["run_count"] == 0
    assert pr["ignored_event_names"] == ["push"]
    assert pr["pull_request_run_source_present"] is False
    assert pr["local_required_trigger_present"] is True
    assert "pr_pull_request_run_source_absent" in pr["blockers"]
    assert "pr_github_actions_3_consecutive_pass_evidence_missing" in pr["blockers"]


def test_build_evidence_surfaces_github_actions_job_start_blockers() -> None:
    base = datetime(2026, 6, 16, tzinfo=timezone.utc)
    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=[_run(1, "push", "failure", base)],
        nightly_rows=[],
        pr_job_start_blockers=[
            {
                "run_id": 1,
                "job_id": 10,
                "event": "push",
                "head_sha": "sha-1",
                "reason_code": "github_actions_billing_or_spending_limit",
                "message": (
                    "The job was not started because recent account payments have failed or "
                    "your spending limit needs to be increased."
                ),
            }
        ],
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
            },
        ],
    )

    pr = payload["lanes"]["pr"]

    assert payload["contract_pass"] is False
    assert pr["job_start_blocker_count"] == 1
    assert pr["job_start_blockers"][0]["reason_code"] == "github_actions_billing_or_spending_limit"
    assert "github_actions_job_start_blocked" in pr["blockers"]
    assert payload["summary"]["pr_job_start_blocker_count"] == 1
    assert "do not create CI streak credit" in payload["claim_boundary"]


def test_job_start_blocker_classifies_self_hosted_runner_unavailable() -> None:
    reason = build_github_actions_ci_streak_evidence._job_start_blocker_code(
        "No runner matching the specified labels was found: self-hosted, linux, x64"
    )

    assert reason == "github_actions_self_hosted_runner_unavailable"


def test_build_evidence_surfaces_stale_queued_self_hosted_runner_blockers() -> None:
    now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=[_queued_run(1, "pull_request", now - timedelta(minutes=31))],
        nightly_rows=[_queued_run(2, "schedule", now - timedelta(minutes=45))],
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
                "self_hosted_runner_default": True,
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
                "self_hosted_runner_default": True,
            },
        ],
        now=now,
    )

    pr = payload["lanes"]["pr"]
    nightly = payload["lanes"]["nightly"]

    assert payload["contract_pass"] is False
    assert pr["job_start_blocker_count"] == 1
    assert nightly["job_start_blocker_count"] == 1
    assert pr["job_start_blockers"][0]["reason_code"] == "github_actions_self_hosted_runner_queued_timeout"
    assert pr["job_start_blockers"][0]["queued_minutes"] == 31.0
    assert "github_actions_job_start_blocked" in pr["blockers"]
    assert "github_actions_job_start_blocked" in nightly["blockers"]
    assert payload["summary"]["pr_job_start_blocker_count"] == 1
    assert payload["summary"]["nightly_job_start_blocker_count"] == 1
    assert "stale queued self-hosted runs" in payload["claim_boundary"]


def test_build_evidence_does_not_count_fresh_queued_runs_as_stale_blockers() -> None:
    now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=[_queued_run(1, "pull_request", now - timedelta(minutes=5))],
        nightly_rows=[],
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
                "self_hosted_runner_default": True,
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
                "self_hosted_runner_default": True,
            },
        ],
        now=now,
    )

    pr = payload["lanes"]["pr"]

    assert pr["job_start_blocker_count"] == 0
    assert "github_actions_job_start_blocked" not in pr["blockers"]


def test_build_evidence_records_missing_registered_workflow_and_sanitized_query_error() -> None:
    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=[],
        nightly_rows=[],
        nightly_error=(
            "* Request at 2026-06-17T00:00:00Z\n"
            "* Request to https://api.github.com/repos/owner/repo/actions/workflows\n"
            "failed to get runs: could not find any workflows named Nightly Full Quality"
        ),
        registered_workflows=[{"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
            },
        ],
    )

    nightly = payload["lanes"]["nightly"]

    assert payload["contract_pass"] is False
    assert nightly["workflow_registered"] is False
    assert nightly["local_workflow_present"] is True
    assert nightly["local_required_trigger_present"] is True
    assert nightly["local_workflow_trigger_events"] == ["schedule", "workflow_dispatch"]
    assert "github_actions_workflow_not_registered" in nightly["blockers"]
    assert nightly["query_error"] == "failed to get runs: could not find any workflows named Nightly Full Quality"
    assert "* Request" not in nightly["query_error"]


def test_local_workflow_parser_records_release_trigger_readiness(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        """
name: CI

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  verify:
    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || '["self-hosted","linux","x64"]') }}
""",
        encoding="utf-8",
    )
    (workflow_dir / "nightly.yml").write_text(
        """
name: Nightly Full Quality

on:
  workflow_dispatch:
  schedule:
    - cron: "17 18 * * *"

jobs:
  full-quality:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )

    workflows = build_github_actions_ci_streak_evidence._local_workflows(workflow_dir)
    by_name = {row["name"]: row for row in workflows}

    assert by_name["CI"]["trigger_events"] == ["pull_request", "push"]
    assert by_name["CI"]["pull_request_trigger_present"] is True
    assert by_name["CI"]["self_hosted_runner_default"] is True
    assert by_name["CI"]["github_hosted_runner_default"] is False
    assert by_name["Nightly Full Quality"]["trigger_events"] == ["schedule", "workflow_dispatch"]
    assert by_name["Nightly Full Quality"]["schedule_trigger_present"] is True
    assert by_name["Nightly Full Quality"]["workflow_dispatch_trigger_present"] is True
    assert by_name["Nightly Full Quality"]["self_hosted_runner_default"] is False
    assert by_name["Nightly Full Quality"]["github_hosted_runner_default"] is True


def test_local_workflow_trigger_readiness_does_not_replace_remote_streaks() -> None:
    base = datetime(2026, 6, 16, tzinfo=timezone.utc)
    payload = build_github_actions_ci_streak_evidence.build_evidence(
        repo="owner/repo",
        threshold=3,
        limit=10,
        pr_workflow="CI",
        nightly_workflow="Nightly Full Quality",
        pr_rows=[_run(i, "pull_request", "success", base - timedelta(minutes=i)) for i in range(2)],
        nightly_rows=[_run(i, "workflow_dispatch", "success", base - timedelta(minutes=i)) for i in range(2)],
        registered_workflows=[
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
            {
                "id": 2,
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "state": "active",
            },
        ],
        local_workflows=[
            {
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "exists": True,
                "trigger_events": ["pull_request", "push"],
            },
            {
                "name": "Nightly Full Quality",
                "path": ".github/workflows/nightly-full-quality.yml",
                "exists": True,
                "trigger_events": ["schedule", "workflow_dispatch"],
            },
        ],
    )

    assert payload["lanes"]["pr"]["local_required_trigger_present"] is True
    assert payload["lanes"]["nightly"]["local_required_trigger_present"] is True
    assert payload["contract_pass"] is False
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 2
    assert payload["lanes"]["nightly"]["consecutive_pass_count"] == 2


def test_local_metadata_only_refresh_preserves_run_history_timestamp(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI\non:\n  pull_request:\n", encoding="utf-8")
    (workflow_dir / "nightly.yml").write_text(
        "name: Nightly Full Quality\non: [schedule, workflow_dispatch]\n",
        encoding="utf-8",
    )
    existing = tmp_path / "github_actions_ci_streak_evidence.json"
    generated_at = "2026-06-16T19:55:48+00:00"
    existing.write_text(
        json_dumps(
            {
                "schema_version": "github-actions-ci-streak-evidence.v1",
                "generated_at": generated_at,
                "threshold": 30,
                "contract_pass": False,
                "workflow_discovery": {"query_error": ""},
                "lanes": {
                    "pr": {"workflow": "CI", "consecutive_pass_count": 0, "threshold_pass": False},
                    "nightly": {
                        "workflow": "Nightly Full Quality",
                        "consecutive_pass_count": 0,
                        "threshold_pass": False,
                    },
                },
                "summary": {},
            }
        ),
        encoding="utf-8",
    )

    payload = build_github_actions_ci_streak_evidence.refresh_local_workflow_metadata(
        existing_evidence_path=existing,
        local_workflow_dir=workflow_dir,
    )

    assert payload["generated_at"] == generated_at
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is True
    assert payload["lanes"]["pr"]["local_required_trigger_present"] is True
    assert payload["lanes"]["pr"]["local_workflow_trigger_events"] == ["pull_request"]
    assert payload["lanes"]["nightly"]["local_required_trigger_present"] is True
    assert payload["lanes"]["nightly"]["local_workflow_trigger_events"] == ["schedule", "workflow_dispatch"]
    assert payload["summary"]["pr_local_required_trigger_present"] is True
    assert payload["summary"]["nightly_local_required_trigger_present"] is True


def test_local_metadata_only_refresh_claim_boundary_is_idempotent(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI\non:\n  pull_request:\n", encoding="utf-8")
    (workflow_dir / "nightly.yml").write_text(
        "name: Nightly Full Quality\non: [schedule, workflow_dispatch]\n",
        encoding="utf-8",
    )
    existing = tmp_path / "github_actions_ci_streak_evidence.json"
    existing.write_text(
        json_dumps(
            {
                "schema_version": "github-actions-ci-streak-evidence.v1",
                "generated_at": "2026-06-16T19:55:48+00:00",
                "threshold": 30,
                "contract_pass": False,
                "claim_boundary": (
                    "GitHub Actions run history only. "
                    f"{build_github_actions_ci_streak_evidence.LOCAL_METADATA_CLAIM_BOUNDARY} "
                    f"{build_github_actions_ci_streak_evidence.LOCAL_METADATA_CLAIM_BOUNDARY}"
                ),
                "workflow_discovery": {"query_error": ""},
                "lanes": {
                    "pr": {"workflow": "CI", "consecutive_pass_count": 0, "threshold_pass": False},
                    "nightly": {
                        "workflow": "Nightly Full Quality",
                        "consecutive_pass_count": 0,
                        "threshold_pass": False,
                    },
                },
                "summary": {},
            }
        ),
        encoding="utf-8",
    )

    first = build_github_actions_ci_streak_evidence.refresh_local_workflow_metadata(
        existing_evidence_path=existing,
        local_workflow_dir=workflow_dir,
    )
    existing.write_text(json_dumps(first), encoding="utf-8")
    second = build_github_actions_ci_streak_evidence.refresh_local_workflow_metadata(
        existing_evidence_path=existing,
        local_workflow_dir=workflow_dir,
    )

    boundary = second["claim_boundary"]
    local_boundary = build_github_actions_ci_streak_evidence.LOCAL_METADATA_CLAIM_BOUNDARY
    assert boundary.count(local_boundary) == 1


def json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
