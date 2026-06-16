from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
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
            {"name": "CI", "path": ".github/workflows/ci.yml", "exists": True},
            {"name": "Nightly Full Quality", "path": ".github/workflows/nightly-full-quality.yml", "exists": True},
        ],
    )

    assert payload["contract_pass"] is False
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 3
    assert payload["lanes"]["pr"]["threshold_pass"] is True
    assert payload["lanes"]["nightly"]["consecutive_pass_count"] == 2
    assert payload["lanes"]["nightly"]["threshold_pass"] is False
    assert all(row["event"] != "push" for row in payload["lanes"]["pr"]["rows"])
    assert payload["lanes"]["pr"]["queried_run_count"] == 4
    assert payload["lanes"]["pr"]["ignored_event_count"] == 1
    assert payload["lanes"]["pr"]["workflow_registered"] is True
    assert payload["summary"]["nightly_workflow_registered"] is True


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
            {"name": "CI", "path": ".github/workflows/ci.yml", "exists": True},
            {"name": "Nightly Full Quality", "path": ".github/workflows/nightly-full-quality.yml", "exists": True},
        ],
    )

    nightly = payload["lanes"]["nightly"]

    assert payload["contract_pass"] is False
    assert nightly["workflow_registered"] is False
    assert nightly["local_workflow_present"] is True
    assert "github_actions_workflow_not_registered" in nightly["blockers"]
    assert nightly["query_error"] == "failed to get runs: could not find any workflows named Nightly Full Quality"
    assert "* Request" not in nightly["query_error"]
