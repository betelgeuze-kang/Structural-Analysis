from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release-publish.yml"
WORKFLOWS_DIR = WORKFLOW.parent


def test_release_publish_workflow_keeps_publication_gates_in_order() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    expected_order = [
        "Source boundary preflight",
        "Regenerate release viewer artifacts",
        "Build fresh publication candidate",
        "Strict release quality gate",
        "Publish manifest-listed release assets",
        "Verify published release closure",
        "Hydrate published release assets",
        "Write publication failure report",
        "Upload publication evidence",
        "Promote verified manifest",
    ]
    positions = [text.index(label) for label in expected_order]

    assert positions == sorted(positions)
    assert "permissions:\n  contents: write" in text
    assert "scripts/publish_github_release_assets.py" in text
    assert "python scripts/verify_quality_gate.py --mode release" in text
    assert "--replace-existing" in text
    assert "scripts/check_release_p0_closure.py" in text
    assert "scripts/check_p0_closure_status.py" in text
    assert text.count("--require-exact") >= 2
    assert '--manifest "$CANDIDATE_MANIFEST"' in text
    assert '--release-assets-json "$RELEASE_ASSETS_JSON"' in text
    assert '--artifact-root "$RELEASE_ROOT"' in text
    assert "structural-p0-closure-status.json" in text
    assert "structural-p0-closure-status.md" in text
    assert "structural-release-metadata-preflight.json" in text
    assert "--hydrate-preflight" in text
    assert '--out "$RELEASE_METADATA_PREFLIGHT"' in text
    assert '--upload-plan-json "$RELEASE_UPLOAD_PLAN"' in text
    assert '--metadata-preflight-json "$RELEASE_METADATA_PREFLIGHT"' in text
    assert "structural-release-hydrated-assets" in text
    assert "scripts/hydrate_github_release_assets.py" in text
    assert "structural-post-publish-roundtrip.json" in text
    assert '--post-publish-roundtrip-json "$POST_PUBLISH_ROUNDTRIP_JSON"' in text
    assert "implementation/phase1/release_artifacts_manifest.json" in text


def test_release_publish_workflow_runs_strict_release_gate_before_publish() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    strict_step = text.split("      - name: Strict release quality gate", 1)[1].split(
        "      - name: Publish manifest-listed release assets", 1
    )[0]

    assert "python scripts/verify_quality_gate.py --mode release" in strict_step
    assert text.index("Strict release quality gate") < text.index(
        "Publish manifest-listed release assets"
    )


def test_release_publish_workflow_only_closes_p0_after_post_publish_roundtrip() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    listing_step = text.split("      - name: Verify published release closure", 1)[1].split(
        "      - name: Hydrate published release assets", 1
    )[0]
    hydrate_step = text.split("      - name: Hydrate published release assets", 1)[1].split(
        "      - name: Write publication failure report", 1
    )[0]

    assert "scripts/check_release_asset_listing.py" in listing_step
    assert "scripts/check_release_p0_closure.py" not in listing_step
    assert "scripts/check_p0_closure_status.py" not in listing_step
    assert "scripts/hydrate_github_release_assets.py" in hydrate_step
    assert "scripts/check_release_p0_closure.py" in hydrate_step
    assert "scripts/check_p0_closure_status.py" in hydrate_step
    assert hydrate_step.index("scripts/hydrate_github_release_assets.py") < hydrate_step.index(
        "scripts/check_release_p0_closure.py"
    )


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
    assert "--allow-cpu-required" in text
    assert "--no-enable-hip-kernel-smoke" in text
    assert "Release workflow github.sha" in text
    assert "Release workflow checkout HEAD" in text
    assert "Track irregularity generator import preflight" in text
    assert "implementation/phase1/track_irregularity_generator.py" in text
    assert "scripts/materialize_release_publication_sidecars.py" in text
    assert "Nightly release gate summary" in text
    assert "failed_step_report_path" in text
    assert "failed_step_report_failed_checks" in text
    assert "failed_step_report_child_step" in text
    assert "implementation/phase1/release/nightly_release_gate_report.json" in text
    assert "structural-release-publication-report.json" in text
    assert "structural-release-publication-report.md" in text
    assert "structural-release-publication-evidence-index.json" in text
    assert "scripts/build_release_publication_evidence_index.py" in text
    assert "release-publication-report" in text
    assert '"failure_report_written": True' in text


def test_release_publish_workflow_uploads_evidence_artifact_even_on_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    report_step = text.split("      - name: Write publication failure report", 1)[1].split(
        "      - name: Upload publication evidence", 1
    )[0]
    upload_step = text.split("      - name: Upload publication evidence", 1)[1].split(
        "      - name: Promote verified manifest", 1
    )[0]

    assert "if: always()" in report_step
    assert "--fail-open" not in report_step
    assert "if: always()" in upload_step
    assert "uses: actions/upload-artifact@v7" in upload_step
    assert "${{ runner.temp }}/structural-release-publication-report.json" in upload_step
    assert "${{ runner.temp }}/structural-release-publication-report.md" in upload_step
    assert "${{ runner.temp }}/structural-release-publication-evidence-index.json" in upload_step
    assert "${{ runner.temp }}/structural-release-metadata-preflight.json" in upload_step
    assert "if-no-files-found: error" in upload_step


def test_workflows_use_node24_ready_official_actions() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS_DIR.glob("*.yml")))

    assert "actions/checkout@v4" not in combined
    assert "actions/setup-python@v5" not in combined
    assert "actions/setup-node@v4" not in combined
    assert "actions/upload-artifact@v4" not in combined
    assert "actions/checkout@v6" in combined
    assert "actions/setup-python@v6" in combined
    assert "actions/setup-node@v6" in combined
    assert "actions/upload-artifact@v7" in combined
