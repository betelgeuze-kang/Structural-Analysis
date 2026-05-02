from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release-publish.yml"


def test_release_publish_workflow_keeps_publication_gates_in_order() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    expected_order = [
        "Source boundary preflight",
        "Regenerate release viewer artifacts",
        "Build fresh publication candidate",
        "Publish manifest-listed release assets",
        "Verify published release closure",
        "Upload publication evidence",
        "Promote verified manifest",
    ]
    positions = [text.index(label) for label in expected_order]

    assert positions == sorted(positions)
    assert "permissions:\n  contents: write" in text
    assert "scripts/publish_github_release_assets.py" in text
    assert "--replace-existing" in text
    assert "scripts/check_release_p0_closure.py" in text
    assert "scripts/check_p0_closure_status.py" in text
    assert '--manifest "$CANDIDATE_MANIFEST"' in text
    assert '--release-assets-json "$RELEASE_ASSETS_JSON"' in text
    assert '--artifact-root "$RELEASE_ROOT"' in text
    assert "structural-p0-closure-status.json" in text
    assert "structural-p0-closure-status.md" in text
    assert "implementation/phase1/release_artifacts_manifest.json" in text


def test_release_publish_workflow_does_not_use_runner_context_in_job_env() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    job_env = text.split("    env:", 1)[1].split("    steps:", 1)[0]

    assert "runner.temp" not in job_env
    assert "RUNNER_TEMP" in text


def test_release_publish_workflow_opts_into_node24_actions_runtime() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' in text


def test_release_publish_workflow_reuses_checked_in_gate_evidence_and_uploads_failure_report() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "--no-reuse-existing-if-present" not in text
    assert "Nightly release gate summary" in text
    assert "implementation/phase1/release/nightly_release_gate_report.json" in text
