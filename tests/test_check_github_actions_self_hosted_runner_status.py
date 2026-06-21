from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_github_actions_self_hosted_runner_status.py"
SPEC = importlib.util.spec_from_file_location("check_github_actions_self_hosted_runner_status", SCRIPT_PATH)
assert SPEC is not None
runner_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner_status
SPEC.loader.exec_module(runner_status)


def test_self_hosted_runner_status_passes_online_idle_matching_runner() -> None:
    payload = runner_status.build_status(
        repo="owner/repo",
        runner_rows=[
            {
                "id": 1,
                "name": "local-5900x",
                "os": "linux",
                "status": "online",
                "busy": False,
                "labels": [
                    {"name": "self-hosted"},
                    {"name": "linux"},
                    {"name": "x64"},
                ],
            }
        ],
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["ready_runner_count"] == 1
    assert payload["blockers"] == []
    assert payload["schema_version"] == "github-actions-self-hosted-runner-status.v1"
    assert payload["generated_at"]
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False


def test_self_hosted_runner_status_blocks_missing_matching_labels() -> None:
    payload = runner_status.build_status(
        repo="owner/repo",
        runner_rows=[
            {
                "id": 1,
                "name": "mac",
                "status": "online",
                "busy": False,
                "labels": [{"name": "self-hosted"}, {"name": "macOS"}],
            }
        ],
    )

    assert payload["contract_pass"] is False
    assert "self_hosted_runner_matching_labels_missing" in payload["blockers"]
    assert payload["matching_runner_count"] == 0


def test_self_hosted_runner_status_blocks_offline_or_busy_matching_runner() -> None:
    offline = runner_status.build_status(
        repo="owner/repo",
        runner_rows=[
            {
                "id": 1,
                "name": "offline",
                "status": "offline",
                "busy": False,
                "labels": [{"name": "self-hosted"}, {"name": "linux"}, {"name": "x64"}],
            }
        ],
    )
    busy = runner_status.build_status(
        repo="owner/repo",
        runner_rows=[
            {
                "id": 2,
                "name": "busy",
                "status": "online",
                "busy": True,
                "labels": [{"name": "self-hosted"}, {"name": "linux"}, {"name": "x64"}],
            }
        ],
    )

    assert "self_hosted_runner_matching_labels_not_online" in offline["blockers"]
    assert "self_hosted_runner_matching_labels_all_busy" in busy["blockers"]


def test_self_hosted_runner_status_query_error_blocks_release_credit() -> None:
    payload = runner_status.build_status(
        repo="owner/repo",
        runner_rows=[],
        query_error="gh auth required",
    )

    assert payload["contract_pass"] is False
    assert "github_actions_self_hosted_runner_query_failed" in payload["blockers"]
    assert "self_hosted_runner_matching_labels_missing" in payload["blockers"]
