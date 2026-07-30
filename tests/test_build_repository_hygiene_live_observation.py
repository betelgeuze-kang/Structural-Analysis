from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_repository_hygiene_live_observation.py"
SPEC = importlib.util.spec_from_file_location(
    "build_repository_hygiene_live_observation", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


def _pr(number: int, sha_character: str) -> dict:
    return {
        "number": number,
        "state": "open",
        "head": {"sha": sha_character * 40},
        "updated_at": "2026-07-28T06:00:00Z",
        "draft": number == 215,
    }


def _candidate_detail() -> dict:
    return {
        "number": 243,
        "state": "open",
        "head": {"sha": "c" * 40},
        "base": {"sha": "f" * 40},
        "commits": 1,
        "changed_files": 4,
    }


def _candidate_compare() -> dict:
    return {
        "merge_base_commit": {"sha": "f" * 40},
        "ahead_by": 1,
        "behind_by": 0,
        "files": [{"filename": f"path-{index}"} for index in range(4)],
    }


def _issue(number: int, *, state: str = "open") -> dict:
    return {
        "number": number,
        "state": state,
        "state_reason": "completed" if state == "closed" else None,
        "updated_at": "2026-07-28T06:00:00Z",
        "closed_at": "2026-07-28T01:51:47Z" if state == "closed" else None,
    }


def _superseded_pull_request(number: int) -> dict:
    return {
        "number": number,
        "state": "closed",
        "merged": False,
        "updated_at": "2026-07-28T06:00:00Z",
        "closed_at": "2026-07-26T14:42:36Z",
    }


def test_build_observation_normalizes_and_sorts_open_pull_requests() -> None:
    payload = observer.build_observation(
        repository="betelgeuze-kang/Structural-Analysis",
        repository_payload={
            "full_name": "betelgeuze-kang/Structural-Analysis",
            "default_branch": "main",
        },
        default_branch_commit={"sha": "f" * 40},
        pull_requests=[_pr(243, "c"), _pr(215, "a"), _pr(221, "b")],
        open_issues=[_issue(242), _issue(143)],
        tracked_issues=[_issue(207, state="closed")],
        superseded_pull_requests=[_superseded_pull_request(77)],
        observed_at="2026-07-28T06:03:37Z",
        candidate_pull_request=_candidate_detail(),
        candidate_compare=_candidate_compare(),
    )

    assert payload["default_branch_head"] == "f" * 40
    assert [row["number"] for row in payload["open_pull_requests"]] == [215, 221, 243]
    assert payload["open_pull_requests"][0]["draft"] is True
    assert payload["candidate_pull_request"] == {
        "number": 243,
        "state": "open",
        "head_sha": "c" * 40,
        "base_sha": "f" * 40,
        "merge_base_sha": "f" * 40,
        "commit_count": 1,
        "changed_file_count": 4,
        "ahead_by": 1,
        "behind_by": 0,
        "comparison_changed_path_count": 4,
        "comparison_files_complete": True,
    }
    assert [row["number"] for row in payload["open_issues"]] == [143, 242]
    assert payload["tracked_issues"][0]["state_reason"] == "completed"
    assert payload["superseded_pull_requests"] == [
        {
            "number": 77,
            "state": "closed",
            "merged": False,
            "updated_at": "2026-07-28T06:00:00Z",
            "closed_at": "2026-07-26T14:42:36Z",
        }
    ]
    assert "no mutation" in payload["claim_boundary"]


def test_build_observation_rejects_repository_identity_mismatch() -> None:
    with pytest.raises(ValueError, match="repository identity mismatch"):
        observer.build_observation(
            repository="betelgeuze-kang/Structural-Analysis",
            repository_payload={
                "full_name": "other/repository",
                "default_branch": "main",
            },
            default_branch_commit={"sha": "f" * 40},
            pull_requests=[],
            open_issues=[],
            tracked_issues=[],
            superseded_pull_requests=[],
            observed_at="2026-07-28T06:03:37Z",
        )


def test_build_observation_rejects_duplicate_pull_request_numbers() -> None:
    with pytest.raises(ValueError, match="duplicate pull request number"):
        observer.build_observation(
            repository="betelgeuze-kang/Structural-Analysis",
            repository_payload={
                "full_name": "betelgeuze-kang/Structural-Analysis",
                "default_branch": "main",
            },
            default_branch_commit={"sha": "f" * 40},
            pull_requests=[_pr(215, "a"), _pr(215, "b")],
            open_issues=[],
            tracked_issues=[],
            superseded_pull_requests=[],
            observed_at="2026-07-28T06:03:37Z",
        )


def test_build_observation_rejects_incomplete_candidate_comparison() -> None:
    with pytest.raises(ValueError, match="comparison are both required"):
        observer.build_observation(
            repository="betelgeuze-kang/Structural-Analysis",
            repository_payload={
                "full_name": "betelgeuze-kang/Structural-Analysis",
                "default_branch": "main",
            },
            default_branch_commit={"sha": "f" * 40},
            pull_requests=[_pr(243, "c")],
            open_issues=[],
            tracked_issues=[],
            superseded_pull_requests=[],
            observed_at="2026-07-28T06:03:37Z",
            candidate_pull_request=_candidate_detail(),
        )


def test_build_observation_filters_pull_requests_from_open_issue_query() -> None:
    pull_request_issue_row = _issue(243)
    pull_request_issue_row["pull_request"] = {
        "url": "https://api.github.com/repos/example/repo/pulls/243"
    }

    payload = observer.build_observation(
        repository="betelgeuze-kang/Structural-Analysis",
        repository_payload={
            "full_name": "betelgeuze-kang/Structural-Analysis",
            "default_branch": "main",
        },
        default_branch_commit={"sha": "f" * 40},
        pull_requests=[],
        open_issues=[pull_request_issue_row, _issue(242)],
        tracked_issues=[],
        superseded_pull_requests=[],
        observed_at="2026-07-28T06:03:37Z",
    )

    assert [row["number"] for row in payload["open_issues"]] == [242]
