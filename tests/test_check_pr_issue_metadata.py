from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_pr_issue_metadata.py"
SPEC = importlib.util.spec_from_file_location("check_pr_issue_metadata", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _event(*, body: str, commits: int = 2, changed_files: int = 4) -> dict[str, object]:
    return {
        "number": 200,
        "pull_request": {
            "number": 200,
            "title": "Add a bounded product capability",
            "body": body,
            "commits": commits,
            "changed_files": changed_files,
            "base": {"ref": "main"},
            "head": {"ref": "feat/bounded-capability"},
        },
    }


def test_recognized_closing_reference_and_matching_counts_pass() -> None:
    report = validator.build_report(
        _event(
            body=(
                "Closes #199\n\n"
                "This change contains exactly 2 commits and exactly 4 changed files."
            )
        )
    )

    assert report["contract_pass"] is True
    assert report["closing_issue_numbers"] == [199]
    assert report["blockers"] == []


def test_ambiguous_issue_reference_and_stale_counts_fail() -> None:
    report = validator.build_report(
        _event(
            body=(
                "Related to #199. This is one commit with exactly 3 changed files. "
                "TODO: update metadata."
            )
        )
    )

    assert report["contract_pass"] is False
    assert "recognized_closing_issue_reference_missing" in report["blockers"]
    assert "issue_referenced_without_github_closing_keyword" in report["blockers"]
    assert "commit_count_claim_mismatch:claimed=1:actual=2" in report["blockers"]
    assert "changed_file_count_claim_mismatch:claimed=3:actual=4" in report["blockers"]
    assert "pull_request_body_placeholder:TODO:" in report["blockers"]


def test_unlinked_pr_can_be_explicitly_allowed_for_exceptional_workflows() -> None:
    report = validator.build_report(
        _event(body="Documentation-only administrative update."),
        require_closing_issue=False,
    )

    assert report["contract_pass"] is True
    assert report["require_closing_issue"] is False


def test_branch_divergence_observation_is_not_a_pr_commit_count_claim() -> None:
    report = validator.build_report(
        _event(
            body=(
                "Closes #199\n\n"
                "The roadmap candidate base is 76 commits behind main with "
                "328 overlapping changed paths."
            ),
            commits=1,
        )
    )

    assert report["contract_pass"] is True
    assert report["actual_commit_count"] == 1
    assert report["blockers"] == []


def test_explicit_pr_commit_count_without_exactly_is_still_validated() -> None:
    report = validator.build_report(
        _event(
            body="Closes #199\n\nThis PR has 3 commits.",
            commits=2,
        )
    )

    assert report["contract_pass"] is False
    assert "commit_count_claim_mismatch:claimed=3:actual=2" in report["blockers"]


def test_pr_metadata_workflow_is_read_only_and_runs_the_validator() -> None:
    workflow = (ROOT / ".github/workflows/pr-metadata-ci.yml").read_text(
        encoding="utf-8"
    )

    assert "issues: read" in workflow
    assert "pull-requests: read" in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "python scripts/check_pr_issue_metadata.py" in workflow
