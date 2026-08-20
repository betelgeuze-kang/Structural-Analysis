from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_git_object_verifiers_checkout_complete_history() -> None:
    workflow_jobs = {
        "ci.yml": "  verify:",
        "python-test-collection.yml": "  full_shards:",
        "legacy-evidence-ci.yml": "  legacy-evidence:",
        "nightly-full-quality.yml": "  full-quality:",
        "product-state-current.yml": "  build-current-state:",
    }

    for filename, job_marker in workflow_jobs.items():
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(
            encoding="utf-8"
        )
        job = workflow.split(job_marker, 1)[1]
        checkout = job.split("- name: Checkout", 1)[1].split("- name:", 1)[0]
        assert "fetch-depth: 0" in checkout, filename
