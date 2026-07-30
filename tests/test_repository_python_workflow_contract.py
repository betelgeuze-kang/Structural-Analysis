from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_pull_request_collects_the_complete_pytest_suite() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "paths:" not in workflow
    assert "python -m pytest --collect-only -q" in workflow
    assert "github.event_name == 'pull_request'" in workflow


def test_merge_queue_and_main_run_the_complete_pytest_suite() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert "merge_group:" in workflow
    assert 'branches: ["main"]' in workflow
    assert "python -m pytest -q" in workflow
    assert "github.event_name == 'merge_group'" in workflow
    assert "github.event_name == 'push'" in workflow


def test_nightly_full_quality_is_full_in_name_and_execution() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nightly-full-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "python scripts/verify_quality_gate.py --mode full" in workflow
    assert "python scripts/verify_quality_gate.py --mode pr" not in workflow
    assert "run: python -m pytest -q" in workflow
    assert "scripts/build_product_state.py" not in workflow


def test_current_product_state_records_every_completed_main_nightly_outcome() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_run:" in workflow
    assert 'workflows: ["Nightly Full Quality"]' in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in workflow
    assert "PRODUCT_STATE_SHA: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert (
        "PRODUCT_STATE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}"
        in workflow
    )
    assert "ref: ${{ env.PRODUCT_STATE_SHA }}" in workflow
    assert "scripts/build_product_state.py" in workflow
    assert '--observed-main-sha "$PRODUCT_STATE_SHA"' in workflow
    assert "github_nightly_full_quality_observation" in workflow
    assert '--nightly-workflow-run-event "$GITHUB_EVENT_PATH"' in workflow
    assert "--verify-legacy-git-objects" in workflow
    assert 'payload["source_commit_sha"] == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert (
        'payload["observed_github_main_sha"] == os.environ["PRODUCT_STATE_SHA"]'
        in workflow
    )
    assert 'payload["quality_evidence"]["status"] == "available"' in workflow
    assert 'payload["quality_evidence"]["conclusion"] == conclusion' in workflow
    assert 'if conclusion == "success":' in workflow
    assert 'payload["contract_pass"] is True' in workflow
    assert 'payload["contract_pass"] is False' in workflow
    assert 'f"nightly_full_quality_not_success:{conclusion}"' in workflow
    assert "continue-on-error: true" in workflow
    assert 'payload["release_authority"] is False' in workflow
    assert 'git_object_verification"] == "passed"' in workflow
