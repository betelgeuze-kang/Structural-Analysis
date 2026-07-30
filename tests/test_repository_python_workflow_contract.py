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
    workflow = (
        ROOT / ".github" / "workflows" / "nightly-full-quality.yml"
    ).read_text(encoding="utf-8")

    assert "python scripts/verify_quality_gate.py --mode full" in workflow
    assert "python scripts/verify_quality_gate.py --mode pr" not in workflow
    assert "run: python -m pytest -q" in workflow
