from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ci_consecutive_pass_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_ci_consecutive_pass_manifest", SCRIPT_PATH)
assert SPEC is not None
build_ci_consecutive_pass_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ci_consecutive_pass_manifest)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_manifest_counts_trailing_pass_streak(tmp_path: Path) -> None:
    pr_reports = [
        _write(tmp_path / "pr1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "pr2.json", {"reason_code": "ERR"}),
        _write(tmp_path / "pr3.json", {"reason_code": "PASS"}),
    ]
    nightly_reports = [
        _write(tmp_path / "nightly1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "nightly2.json", {"contract_pass": True}),
        _write(tmp_path / "nightly3.json", {"reason_code": "PASS"}),
    ]

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=3,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CI_STREAK_INCOMPLETE"
    assert "pr:pr_ci_3_consecutive_pass_evidence_missing" in payload["blockers"]
    assert "nightly:nightly_ci_3_consecutive_pass_evidence_missing" in payload["blockers"]
    assert payload["lanes"]["pr"]["local_consecutive_pass_count"] == 1
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 0
    assert payload["lanes"]["pr"]["missing_consecutive_pass_count"] == 3
    assert payload["lanes"]["pr"]["threshold_pass"] is False
    assert payload["lanes"]["pr"]["blockers"] == ["pr_ci_3_consecutive_pass_evidence_missing"]
    assert payload["lanes"]["pr"]["owner_action"].startswith(
        "Collect 3 additional consecutive successful PR CI run"
    )
    assert "release streak credit requires tracked PR CI evidence" in payload["lanes"]["pr"]["claim_boundary"]
    assert payload["lanes"]["nightly"]["local_consecutive_pass_count"] == 3
    assert payload["lanes"]["nightly"]["consecutive_pass_count"] == 0
    assert payload["lanes"]["nightly"]["missing_consecutive_pass_count"] == 3
    assert payload["lanes"]["nightly"]["threshold_pass"] is False
    assert payload["summary"]["pr_missing_consecutive_pass_count"] == 3
    assert payload["summary"]["nightly_missing_consecutive_pass_count"] == 3
    assert payload["summary"]["pr_owner_action"] == payload["lanes"]["pr"]["owner_action"]


def test_build_manifest_uses_github_actions_streak_evidence_when_available(tmp_path: Path) -> None:
    pr_reports = [
        _write(tmp_path / "pr1.json", {"reason_code": "PASS"}),
        _write(tmp_path / "pr2.json", {"reason_code": "PASS"}),
    ]
    nightly_reports = [_write(tmp_path / "nightly1.json", {"reason_code": "PASS"})]
    github_evidence = _write(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "lanes": {
                "pr": {"consecutive_pass_count": 30},
                "nightly": {"consecutive_pass_count": 30},
            },
        },
    )

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=30,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=github_evidence,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["blockers"] == []
    assert payload["lanes"]["pr"]["local_consecutive_pass_count"] == 2
    assert payload["lanes"]["pr"]["github_actions_consecutive_pass_count"] == 30
    assert payload["lanes"]["pr"]["consecutive_pass_count"] == 30
    assert payload["lanes"]["pr"]["missing_consecutive_pass_count"] == 0
    assert payload["lanes"]["pr"]["streak_source"] == "github_actions"


def test_build_manifest_surfaces_github_actions_workflow_registration_gap(tmp_path: Path) -> None:
    pr_reports = [_write(tmp_path / "pr1.json", {"reason_code": "PASS"})]
    nightly_reports = [_write(tmp_path / "nightly1.json", {"reason_code": "PASS"})]
    github_evidence = _write(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "lanes": {
                "pr": {
                    "consecutive_pass_count": 0,
                    "workflow_registered": True,
                    "queried_run_count": 100,
                    "run_count": 0,
                    "pull_request_run_source_present": False,
                    "ignored_event_names": ["push"],
                    "blockers": [
                        "pr_pull_request_run_source_absent",
                        "pr_github_actions_30_consecutive_pass_evidence_missing",
                    ],
                },
                "nightly": {
                    "consecutive_pass_count": 0,
                    "workflow_registered": False,
                    "local_workflow_present": True,
                    "query_error": "failed to get runs: could not find any workflows named Nightly Full Quality",
                    "blockers": [
                        "github_actions_query_failed",
                        "github_actions_workflow_not_registered",
                        "nightly_github_actions_30_consecutive_pass_evidence_missing",
                    ],
                },
            },
        },
    )

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=30,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=github_evidence,
    )

    assert payload["contract_pass"] is False
    assert payload["lanes"]["pr"]["github_actions_workflow_registered"] is True
    assert payload["lanes"]["pr"]["github_actions_queried_run_count"] == 100
    assert payload["lanes"]["pr"]["github_actions_ignored_event_names"] == ["push"]
    assert payload["lanes"]["pr"]["pull_request_run_source_present"] is False
    assert payload["lanes"]["pr"]["streak_source"] == "no_pull_request_run_source"
    assert "pr_pull_request_run_source_absent" in payload["lanes"]["pr"]["blockers"]
    assert payload["lanes"]["pr"]["owner_action"].startswith("No pull_request-triggered CI runs")
    assert payload["lanes"]["nightly"]["github_actions_workflow_registered"] is False
    assert payload["lanes"]["nightly"]["local_workflow_present"] is True
    assert payload["lanes"]["nightly"]["streak_source"] == "github_actions_workflow_not_registered"
    assert "nightly_github_actions_query_failed" in payload["lanes"]["nightly"]["blockers"]
    assert "nightly_github_actions_workflow_not_registered" in payload["lanes"]["nightly"]["blockers"]
    assert payload["lanes"]["nightly"]["owner_action"].startswith("Register or enable the nightly")
    assert payload["summary"]["github_actions_nightly_workflow_registered"] is False
    assert payload["summary"]["pr_pull_request_run_source_present"] is False


def test_build_manifest_distinguishes_insufficient_pr_streak_from_missing_pr_source(tmp_path: Path) -> None:
    pr_reports = [_write(tmp_path / "pr1.json", {"reason_code": "PASS"})]
    nightly_reports = [_write(tmp_path / "nightly1.json", {"reason_code": "PASS"})]
    github_evidence = _write(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "lanes": {
                "pr": {
                    "consecutive_pass_count": 5,
                    "workflow_registered": True,
                    "queried_run_count": 5,
                    "run_count": 5,
                    "pull_request_run_source_present": True,
                    "blockers": ["pr_github_actions_30_consecutive_pass_evidence_missing"],
                },
                "nightly": {"consecutive_pass_count": 30, "workflow_registered": True},
            },
        },
    )

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=30,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=github_evidence,
    )

    pr = payload["lanes"]["pr"]

    assert pr["pull_request_run_source_present"] is True
    assert pr["streak_source"] == "github_actions"
    assert "pr_pull_request_run_source_absent" not in pr["blockers"]
    assert pr["owner_action"].startswith("Collect 25 additional consecutive successful PR CI run")


def test_build_manifest_propagates_github_actions_job_start_blocker(tmp_path: Path) -> None:
    pr_reports = [_write(tmp_path / "pr1.json", {"reason_code": "PASS"})]
    nightly_reports = [_write(tmp_path / "nightly1.json", {"reason_code": "PASS"})]
    github_evidence = _write(
        tmp_path / "github_actions_ci_streak_evidence.json",
        {
            "schema_version": "github-actions-ci-streak-evidence.v1",
            "lanes": {
                "pr": {
                    "consecutive_pass_count": 0,
                    "workflow_registered": True,
                    "queried_run_count": 5,
                    "run_count": 0,
                    "pull_request_run_source_present": False,
                    "job_start_blockers": [
                        {
                            "run_id": 100,
                            "job_id": 200,
                            "reason_code": "github_actions_billing_or_spending_limit",
                            "message": "The job was not started because recent account payments have failed.",
                        }
                    ],
                    "blockers": [
                        "github_actions_job_start_blocked",
                        "pr_pull_request_run_source_absent",
                        "pr_github_actions_30_consecutive_pass_evidence_missing",
                    ],
                },
                "nightly": {"consecutive_pass_count": 30, "workflow_registered": True},
            },
        },
    )

    payload = build_ci_consecutive_pass_manifest.build_manifest(
        threshold=30,
        pr_reports=pr_reports,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=github_evidence,
    )

    pr = payload["lanes"]["pr"]

    assert payload["contract_pass"] is False
    assert pr["streak_source"] == "github_actions_job_start_blocked"
    assert pr["github_actions_job_start_blocker_count"] == 1
    assert pr["github_actions_job_start_blockers"][0]["reason_code"] == "github_actions_billing_or_spending_limit"
    assert "pr_github_actions_job_start_blocked" in pr["blockers"]
    assert "pr:pr_github_actions_job_start_blocked" in payload["blockers"]
    assert payload["summary"]["github_actions_pr_job_start_blocker_count"] == 1
    assert pr["owner_action"].startswith("Resolve the pr GitHub Actions job-start blocker")
