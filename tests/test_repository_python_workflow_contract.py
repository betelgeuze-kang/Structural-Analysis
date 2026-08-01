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
    assert "collect:\n    if:" not in workflow
    assert workflow.count("python -m pip install numpy==1.26.4 scipy==1.12.0") == 2
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow


def test_merge_queue_and_main_run_the_complete_pytest_suite() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert "merge_group:" in workflow
    assert 'branches: ["main"]' in workflow
    assert "python -m pytest -q" in workflow
    assert "full:\n    if:" not in workflow
    full_checkout = workflow.split("  full:", 1)[1].split(
        "      - name: Set up Python",
        1,
    )[0]
    assert "fetch-depth: 0" in full_checkout
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    full_suite = workflow.index("- name: Run complete repository test suite")
    for command in (
        "python scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py",
        "python scripts/build_fracture_energy_concrete_benchmark.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.py",
    ):
        assert command in workflow
        assert materialize < workflow.index(command) < full_suite


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
    assert 'python-version: "3.12.11"' in workflow
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in workflow
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
    assert "scripts/build_product_state.py" in workflow
    assert '--observed-main-sha "${{ steps.observe_main.outputs.sha }}"' in workflow
    assert "github_api_refs_heads_main_pre_build" in workflow
    assert 'gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"' in workflow
    assert workflow.count(
        'gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"'
    ) == 2
    assert '--nightly-workflow-run-event "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    assert 'cp "$GITHUB_EVENT_PATH" "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    assert "--verify-legacy-git-objects" in workflow
    assert 'payload["source_commit_sha"] == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert (
        'payload["observed_github_main_sha"] == observed_main_sha'
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
    assert "uses: actions/attest@v4" in workflow
    assert "product-state.current.sigstore.json" in workflow
    assert "gh attestation verify" in workflow
    assert "retention-days: 90" in workflow
    assert "timeout-minutes: 45" in workflow
    assert (
        "CANONICAL_VERIFICATION_RECEIPT_PATH: "
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert "python scripts/generate_capability_surfaces.py --json" in workflow
    assert '--source-sha "$PRODUCT_STATE_SHA"' in workflow
    assert 'test "$(git rev-parse HEAD)" = "$PRODUCT_STATE_SHA"' in workflow
    assert workflow.count("--verify-head") == 1
    assert "--require-through product-state" in workflow
    assert '--write-state "$GENERATED_ARTIFACT_DAG_STATE_PATH"' in workflow
    assert '--state "$GENERATED_ARTIFACT_DAG_STATE_PATH"' not in workflow
    assert "GENERATED_ARTIFACT_DAG_REPORT_PATH" not in workflow
    assert "canonical/generated-artifact-dag-state.v1.schema.json" in workflow
    assert "canonical/product-state.current.v1.schema.json" in workflow
    assert "jsonschema.Draft202012Validator(schema).validate(product_state)" in workflow
    assert 'receipt["source_commit_sha"] == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert "canonical-receipt:" in workflow
    assert "needs: canonical-receipt" in workflow
    assert (
        "docker.io/library/python:3.12.11-slim-bookworm@sha256:"
        "519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
        in workflow
    )
    assert "uses: actions/upload-artifact@v7" in workflow
    assert "uses: actions/download-artifact@v7" in workflow
    assert "product-state-canonical-receipt-${{ env.PRODUCT_STATE_SHA }}" in workflow
    download = workflow.index("Download canonical environment receipt")
    downloaded_receipt_validation = workflow.index(
        "Validate canonical receipt schema and source binding", download
    )
    assert download < downloaded_receipt_validation
    observe = workflow.index(
        "      - name: Observe refs/heads/main immediately before build"
    )
    build = workflow.index("      - name: Build source-bound current product state")
    assert observe < build
    assert workflow[observe:build].count("      - name:") == 1
    assert 'source_sha == observed_main_sha' in workflow
    assert 'payload["source_matches_observed_github_main"] is True' not in workflow
    stable = workflow.index("Confirm main observation is stable before attestation")
    attest = workflow.index("Attest exact-SHA product state")
    assert stable < attest
    assert 'test "$current_main_sha" = "$OBSERVED_MAIN_SHA"' in workflow
    assert workflow.index("python scripts/build_product_state.py") < workflow.index(
        '--write-state "$GENERATED_ARTIFACT_DAG_STATE_PATH"'
    )


def test_canonical_workflow_binds_receipt_to_the_checked_out_sha() -> None:
    workflow = (ROOT / ".github" / "workflows" / "p0-canonical-contract.yml").read_text(
        encoding="utf-8"
    )

    assert "merge_group:" in workflow
    assert '--source-sha "${{ github.sha }}"' in workflow
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert (
        "CANONICAL_VERIFICATION_RECEIPT_PATH: "
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert "python scripts/generate_capability_surfaces.py --json" in workflow
    assert "--verify-head" not in workflow
    assert "--require-through verification-receipts" in workflow
    assert '--write-state "$GENERATED_ARTIFACT_DAG_STATE_PATH"' in workflow
    assert '--state "$GENERATED_ARTIFACT_DAG_STATE_PATH"' not in workflow
    assert "GENERATED_ARTIFACT_DAG_REPORT_PATH" not in workflow
    assert "canonical/generated-artifact-dag-state.v1.schema.json" in workflow
    assert "${{ env.CANONICAL_VERIFICATION_RECEIPT_PATH }}" in workflow
    assert "${{ env.GENERATED_ARTIFACT_DAG_STATE_PATH }}" in workflow
    assert 'receipt["source_commit_sha"] == os.environ["GITHUB_SHA"]' in workflow


def test_required_workflow_contexts_are_unique_and_unconditional_on_prs() -> None:
    workflows = {
        "canonical-contract": "p0-canonical-contract.yml",
        "workflow-contract": "workflow-contract-ci.yml",
        "git-lfs-integrity": "git-lfs-integrity.yml",
        "pytest-collection": "python-test-collection.yml",
        "pytest-full": "python-test-collection.yml",
    }

    for context, filename in workflows.items():
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(
            encoding="utf-8"
        )
        pull_request = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
        assert "paths:" not in pull_request
        assert "merge_group:" in workflow
        assert f"name: {context}" in workflow
