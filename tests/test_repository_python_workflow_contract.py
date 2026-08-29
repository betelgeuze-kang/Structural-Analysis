from __future__ import annotations

import json
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
    assert "python scripts/run_pytest_shard.py" in workflow
    shard_job = workflow.split("  full_shards:", 1)[1].split("  full:", 1)[0]
    assert "name: pytest-full-shard-${{ matrix.shard }}" in shard_job
    assert "fail-fast: false" in shard_job
    assert "shard: [0, 1, 2, 3]" in shard_job
    assert '--shard-index "${{ matrix.shard }}"' in shard_job
    assert "--shard-count 4" in shard_job
    assert "timeout-minutes: 360" in shard_job
    full_checkout = shard_job.split(
        "      - name: Set up Python",
        1,
    )[0]
    assert "fetch-depth: 0" in full_checkout
    aggregate_job = workflow.split("  full:", 1)[1]
    assert "name: pytest-full" in aggregate_job
    assert "if: ${{ always() }}" in aggregate_job
    assert "needs: full_shards" in aggregate_job
    assert 'test "$FULL_SHARDS_RESULT" = "success"' in aggregate_job
    pristine_ledger = workflow.index("- name: Validate pristine commercial gap ledger")
    hosted_hip_source = workflow.index(
        "- name: Validate hosted HIP receipt source binding"
    )
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    full_suite = workflow.index("- name: Run materialized repository test suite shard")
    ledger_nodeid = (
        "tests/test_commercial_gap_ledger_status.py::"
        "test_commercial_gap_ledger_status_is_honest_about_current_blockers"
    )
    assert workflow.count(ledger_nodeid) == 2
    hip_reproduction_nodeid = (
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::"
        "test_committed_receipt_is_reproducible"
    )
    assert workflow.count(hip_reproduction_nodeid) == 1
    assert "--check-source-only" in workflow[hosted_hip_source:pristine_ledger]
    assert hosted_hip_source < pristine_ledger < materialize < full_suite
    assert "--deselect" in workflow[full_suite:]
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

    assert "python scripts/verify_quality_gate.py" in workflow
    assert "--mode full" in workflow
    assert "--python-suite-delegated-to-workflow-shards" in workflow
    assert "python scripts/verify_quality_gate.py --mode pr" not in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    for checkout in workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    )[1:]:
        checkout_options = checkout.split("\n\n", 1)[0]
        assert checkout_options.count("with:") == 1
        assert "fetch-depth: 0" in checkout_options
        assert "persist-credentials: false" in checkout_options
    assert "- name: Deterministic Python regression suite" not in workflow
    assert "python_full_shards:" in workflow
    assert "matrix:\n        shard: [0, 1, 2, 3]" in workflow
    assert "python scripts/run_pytest_shard.py" in workflow
    assert workflow.count("--deselect") == 2
    assert "full_quality:" in workflow
    assert "if: ${{ always() }}" in workflow
    assert "needs: [python_full_shards, deterministic_quality]" in workflow
    assert 'test "$PYTHON_FULL_SHARDS_RESULT" = "success"' in workflow
    assert 'test "$DETERMINISTIC_QUALITY_RESULT" = "success"' in workflow
    assert (
        "tests/test_commercial_gap_ledger_status.py::"
        "test_commercial_gap_ledger_status_is_honest_about_current_blockers" in workflow
    )
    assert (
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::"
        "test_committed_receipt_is_reproducible" in workflow
    )
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    quality_gate = workflow.index("- name: Deterministic repository quality gate")
    propagation = workflow.index("for pass in 1 2 3; do")
    assert materialize < propagation < quality_gate
    phase1 = workflow.index(
        "python scripts/build_phase1_core_api_contract_artifacts.py",
        materialize,
    )
    assert materialize < phase1 < propagation
    for command in (
        "python scripts/build_developer_preview_readiness.py",
        "python scripts/build_developer_preview_rc_status.py",
        "python scripts/report_release_evidence_freshness.py",
        "python scripts/report_pm_release_gate.py",
        "python scripts/build_pm_release_blocker_action_register.py",
        "python scripts/build_product_readiness_snapshot.py",
        "python scripts/build_structural_product_development_roadmap.py",
    ):
        assert propagation < workflow.index(command, propagation) < quality_gate
    assert "scripts/build_product_state.py" not in workflow

    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    assert '[_python(), "-m", "pytest", "-q"]' in gate
    assert "python_suite_delegated_to_workflow_shards" in gate


def test_heavy_quality_separates_python_and_readiness_evidence_epochs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nightly-heavy-solver.yml").read_text(
        encoding="utf-8"
    )

    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    python_suite = workflow.index("- name: Run materialized repository Python suite")
    readiness = workflow.index("- name: Materialize current-source readiness graph")
    quality_gate = workflow.index("- name: Full workstation/release quality gate")
    assert materialize < python_suite < readiness < quality_gate
    assert "timeout-minutes: 420" in workflow
    assert "--python-suite-verified-in-prior-step" in workflow[quality_gate:]
    assert "--materialized-python-suite" not in workflow
    assert "python -m pytest -q" in workflow[python_suite:readiness]
    assert workflow[python_suite:readiness].count("--deselect") == 2
    assert (
        "python scripts/build_phase1_core_api_contract_artifacts.py"
        in workflow[readiness:quality_gate]
    )
    assert "for pass in 1 2 3; do" in workflow[readiness:quality_gate]
    checkout = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout.count("with:") == 1
    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: false" in checkout


def test_current_product_state_records_every_completed_main_nightly_outcome() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )

    assert "timeout-minutes: 45" in workflow
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
    assert "PRODUCT_STATE_WORKFLOW_SHA: ${{ github.workflow_sha }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_REF: ${{ github.workflow_ref }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_NAME: ${{ github.workflow }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_EVENT: ${{ github.event_name }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_ID: ${{ github.run_id }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_NUMBER: ${{ github.run_number }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_ATTEMPT: ${{ github.run_attempt }}" in workflow
    assert "ref: ${{ env.PRODUCT_STATE_SHA }}" in workflow
    assert 'test "$PRODUCT_STATE_WORKFLOW_SHA" = "$PRODUCT_STATE_SHA"' in workflow
    assert 'test "$PRODUCT_STATE_WORKFLOW_EVENT" = "workflow_run"' in workflow
    assert (
        "$GITHUB_REPOSITORY/.github/workflows/"
        "product-state-current.yml@refs/heads/main" in workflow
    )
    identity_step = workflow.index("Verify product-state workflow execution identity")
    evidence_step = workflow.index("Verify generated capability surfaces")
    assert identity_step < evidence_step
    assert 'python-version: "3.12.11"' in workflow
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in workflow
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
    assert "scripts/build_product_state.py" in workflow
    assert "scripts/generate_capability_surfaces.py" in workflow
    assert "opensees-calculix-current-source.yml/runs?branch=main" in workflow
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert "CLEAN_RUNNER_RUN_CONCLUSION" in workflow
    assert "if: ${{ env.CLEAN_RUNNER_RUN_CONCLUSION == 'success' }}" in workflow
    assert "opensees-calculix-current-source-{os.environ['CLEAN_RUNNER_RUN_ID']}" in workflow
    assert (
        "CLEAN_RUNNER_EVIDENCE_ROOT: "
        ".ci/product-state-inputs/opensees-calculix-clean-runner" in workflow
    )
    assert "CLEAN_RUNNER_RECEIPT_DIR" not in workflow
    assert "actions/runs/$CLEAN_RUNNER_RUN_ID/jobs?per_page=100" in workflow
    assert "actions/runs/$CLEAN_RUNNER_RUN_ID/artifacts?per_page=100" in workflow
    assert "actions/artifacts/$artifact_id/zip" in workflow
    assert 'candidate.get("archive_download_url") == expected_url' in workflow
    assert 'workflow_run.get("id") == run["id"]' in workflow
    assert "expected_producer_name" in workflow
    assert "producer-artifact.json" in workflow
    assert 'artifact["id"] == producer_artifact["id"]' in workflow
    assert '"id": producer_artifact["id"]' in workflow
    assert '"digest": producer_artifact["digest"].removeprefix("sha256:")' in workflow
    assert "clean_runner_artifact_archive_invalid" in workflow
    assert "clean_runner_artifact_file_set_invalid" in workflow
    assert (
        '"artifact_status": "unavailable"' in workflow
        and "exact_sha_artifact_download_failed_after_bounded_retry" in workflow
    )
    unavailable_branch = workflow.index(
        "if ! gh api -H 'Accept: application/vnd.github+json'"
    )
    unavailable_exit = workflow.index("exit 0", unavailable_branch)
    materialized_copy = workflow.index(
        'materialized_receipt_dir="$CLEAN_RUNNER_EVIDENCE_ROOT/'
        'artifacts/vv/opensees_calculix_clean_runner"'
    )
    assert unavailable_branch < unavailable_exit < materialized_copy
    assert 'cp -R "$artifact_root"/. "$materialized_receipt_dir"/' in workflow
    assert 'materialized_host="$CLEAN_RUNNER_EVIDENCE_ROOT/$host_receipt"' in workflow
    assert (
        "git status --porcelain=v1 --untracked-files=all -- \\\n"
        "              artifacts/vv/opensees_calculix_clean_runner" in workflow
    )
    assert (
        'cp -R "$artifact_root"/. '
        '"artifacts/vv/opensees_calculix_clean_runner"/' not in workflow
    )
    product_state_upload = workflow.index(
        "- name: Upload current and historical product-state manifests"
    )
    assert ".ci/product-state-inputs" in workflow[product_state_upload:]
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/opensees-calculix-clean-runner-attestor.yml"'
        in workflow
    )
    assert 'certificate["runInvocationURI"] == invocation' in workflow
    assert 'statement["predicate"]["runDetails"]["metadata"]["invocationId"]' in workflow
    assert 'statement["subject"] == [{' in workflow
    assert '--signer-digest "$PRODUCT_STATE_SHA"' in workflow
    assert '--clean-runner-summary "$CLEAN_RUNNER_SUMMARY_PATH"' in workflow
    assert (
        "--same-operator-supplemental-receipt "
        '"$SAME_OPERATOR_SUPPLEMENTAL_RECEIPT_PATH"' in workflow
    )
    assert '--external-vv-clean-runner-summary "$CLEAN_RUNNER_SUMMARY_PATH"' in workflow
    assert "p0-canonical-contract.yml" in workflow
    assert "head_sha=$PRODUCT_STATE_SHA" in workflow
    assert "for attempt in {1..30}" in workflow
    assert "sleep 10" in workflow
    assert "canonical workflow lookup failed after bounded retry" in workflow
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert "gh run download" in workflow
    assert "for attempt in {1..12}" in workflow
    assert "sleep 5" in workflow
    assert "exact-SHA canonical artifact unavailable after bounded retry" in workflow
    assert (
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert (
        "CANONICAL_WHEEL_CONTRACT_PATH: .ci/canonical-project-wheel-contract.json"
        in workflow
    )
    assert (
        "CANONICAL_WHEEL_PATH: .ci/canonical-wheel/"
        "structural_analysis-0.3.0-py3-none-any.whl" in workflow
    )
    assert (
        "NIGHTLY_WORKFLOW_RUN_EVENT_PATH: "
        ".ci/product-state-inputs/nightly-workflow-run-event.json" in workflow
    )
    assert (
        'receipt["contract_profile"] == "p0-canonical-installed-wheel.v1"' in workflow
    )
    assert 'receipt["source_commit_sha"] == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert 'receipt["project_wheel"] == wheel_contract' in workflow
    assert "hashlib.sha256(wheel_path.read_bytes()).hexdigest()" in workflow
    assert 'receipt["contract_pass"] is True' in workflow
    assert 'cp "$GITHUB_EVENT_PATH" "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    assert (
        workflow.count(
            "gh api \"repos/$GITHUB_REPOSITORY/git/ref/heads/main\" --jq '.object.sha'"
        )
        == 2
    )
    assert '--observed-main-sha "${{ steps.observe_main.outputs.sha }}"' in workflow
    assert "github_api_refs_heads_main_pre_build" in workflow
    assert (
        workflow.count(
            '--nightly-workflow-run-event "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"'
        )
        == 2
    )
    assert '--product-state-workflow-sha "$PRODUCT_STATE_WORKFLOW_SHA"' in workflow
    assert '--product-state-workflow-ref "$PRODUCT_STATE_WORKFLOW_REF"' in workflow
    assert '--product-state-workflow-name "$PRODUCT_STATE_WORKFLOW_NAME"' in workflow
    assert '--product-state-workflow-event "$PRODUCT_STATE_WORKFLOW_EVENT"' in workflow
    assert (
        '--product-state-workflow-run-id "$PRODUCT_STATE_WORKFLOW_RUN_ID"' in workflow
    )
    assert (
        '--product-state-workflow-run-number "$PRODUCT_STATE_WORKFLOW_RUN_NUMBER"'
        in workflow
    )
    assert (
        "--product-state-workflow-run-attempt "
        '"$PRODUCT_STATE_WORKFLOW_RUN_ATTEMPT"' in workflow
    )
    assert "--verify-legacy-git-objects" in workflow
    assert 'payload["source_commit_sha"] == source_sha' in workflow
    assert 'payload["observed_github_main_sha"] == observed_main_sha' in workflow
    assert "if source_sha != observed_main_sha:" in workflow
    assert 'payload["quality_evidence"]["status"] == "invalid"' in workflow
    assert 'payload["quality_evidence"]["status"] == "available"' in workflow
    assert '"source_commit_does_not_match_observed_github_main"' in workflow
    assert '"nightly_full_quality_evidence_invalid:head_sha"' in workflow
    assert 'payload["quality_evidence"]["conclusion"] == conclusion' in workflow
    assert 'elif conclusion == "success":' in workflow
    assert 'payload["contract_pass"] is True' in workflow
    assert 'payload["contract_pass"] is False' in workflow
    assert 'f"nightly_full_quality_not_success:{conclusion}"' in workflow
    assert "continue-on-error: true" in workflow
    assert '--write-state "$DAG_STATE_PATH"' in workflow
    assert '--report "$DAG_REPORT_PATH"' in workflow
    assert 'cat "$DAG_REPORT_PATH"' in workflow
    assert (
        '--product-state-nightly-event "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    )
    assert "--allow-missing" not in workflow
    assert "canonical/generated-artifact-dag-state.v2.schema.json" in workflow
    assert "canonical/generated-artifact-dag-report.v2.schema.json" in workflow
    assert 'report["contract_pass"] is True' in workflow
    assert 'report["stale_nodes"] == []' in workflow
    assert 'row["current_binding"]["status"] == "current"' in workflow
    assert 'payload["release_authority"] is False' in workflow
    assert 'git_object_verification"] == "passed"' in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "actions/checkout@v" not in workflow
    assert "actions/setup-python@v" not in workflow
    assert "actions/attest@v" not in workflow
    assert "actions/upload-artifact@v" not in workflow
    assert "product-state.current.sigstore.json" in workflow
    assert "scripts/build_product_state_provenance_bundle.py" in workflow
    assert '--source-sha "$PRODUCT_STATE_SHA"' in workflow
    assert '--product-state "$PRODUCT_STATE_PATH"' in workflow
    assert '--canonical-receipt "$CANONICAL_RECEIPT_PATH"' in workflow
    assert '--canonical-wheel-contract "$CANONICAL_WHEEL_CONTRACT_PATH"' in workflow
    assert '--canonical-wheel "$CANONICAL_WHEEL_PATH"' in workflow
    assert '--dag-state "$DAG_STATE_PATH"' in workflow
    assert '--dag-report "$DAG_REPORT_PATH"' in workflow
    assert "canonical-verification-workflow-run.json" in workflow
    assert "product-state.provenance-bundle.v1.json" in workflow
    assert (
        workflow.count("actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d") == 2
    )
    assert "steps.attest_provenance.outputs.bundle-path" in workflow
    assert workflow.index("steps.attest.outputs.bundle-path") < workflow.index(
        "id: attest_provenance"
    )
    assert "product-state.provenance-bundle.sigstore.json" in workflow
    assert "product-state.provenance-bundle.attestation-verification.json" in workflow
    assert workflow.count(".github/workflows/product-state-current.yml") >= 5
    assert workflow.count("gh attestation verify") == 4
    assert workflow.count('--signer-digest "$PRODUCT_STATE_WORKFLOW_SHA"') == 2
    assert workflow.count('--source-digest "$PRODUCT_STATE_SHA"') == 4
    assert workflow.count("--source-ref refs/heads/main") == 4
    assert "canonical/product-state.current.v1.schema.json" in workflow
    assert "jsonschema.Draft202012Validator.check_schema(schema)" in workflow
    assert 'test "$current_main_sha" = "$PRODUCT_STATE_SHA"' in workflow
    assert workflow.index("Validate current product-state schema") < workflow.index(
        "Verify current-main binding, outcome, and bounded authority"
    )
    assert workflow.index("Confirm main observation is stable before attestation") < (
        workflow.index("id: attest")
    )
    assert workflow.count("include-hidden-files: true") == 1
    assert "retention-days: 90" in workflow


def test_product_state_reverifies_all_exact_sha_supplemental_attestations() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )
    step = workflow.split(
        "- name: Download and reverify exact-SHA supplemental technical attestations",
        1,
    )[1].split(
        "- name: Materialize attested exact-SHA clean-runner evidence when available",
        1,
    )[0]

    for path in (
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
    ):
        assert step.count(path) == 1
    assert "status=success&head_sha=$PRODUCT_STATE_SHA" in step
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in step
    assert 'row.get("head_branch") == "main"' in step
    assert 'row.get("conclusion") == "success"' in step
    assert "type(run_id) is not int" in step
    assert "type(run_attempt) is not int" in step
    assert "for lookup_attempt in {1..30}" in step
    assert "gh run download" in step
    assert "mark_supplemental_unavailable" in step
    assert "workflow_run_lookup_failed_after_bounded_retry" in step
    assert "successful_exact_sha_workflow_run_missing" in step
    assert "actions/runs/$run_id/artifacts?per_page=100" in step
    assert 'artifact.get("expired")' in step
    assert "type(artifact_id) is not int" in step
    assert "exact_sha_artifact_missing" in step
    assert "exact_sha_artifact_expired" in step
    assert "available exact-SHA supplemental artifact download failed" in step
    unavailable_branch = step.index('if test "$supplemental_available" != "true"; then')
    assert step.index("exit 0", unavailable_branch) < step.index(
        "scripts/build_bounded_planar_current_source_supplemental_attestation.py"
    )
    assert "gh attestation verify" in step
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/'
        'bounded-planar-sealed-technical-attestor.yml"' in step
    )
    assert '--signer-digest "$PRODUCT_STATE_SHA"' in step
    assert '--source-digest "$PRODUCT_STATE_SHA"' in step
    assert "--source-ref refs/heads/main" in step
    assert "--deny-self-hosted-runners" in step
    assert "product-state-attestation-verification.json" in step
    assert (
        "scripts/build_bounded_planar_current_source_supplemental_attestation.py"
        in step
    )
    assert '--out "$SAME_OPERATOR_SUPPLEMENTAL_RECEIPT_PATH"' in step


def test_supplemental_workflows_upload_hidden_attestation_inputs() -> None:
    workflow_paths = (
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
    )

    for relative_path in workflow_paths:
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
            in workflow
        )
        assert ".ci/bounded-planar-" in workflow
        assert workflow.count("include-hidden-files: true") == 1
        assert "if-no-files-found: error" in workflow


def test_canonical_workflow_binds_receipt_to_the_checked_out_sha() -> None:
    workflow = (ROOT / ".github" / "workflows" / "p0-canonical-contract.yml").read_text(
        encoding="utf-8"
    )
    config = json.loads(
        (ROOT / "canonical/verification-environment.v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert "timeout-minutes: 30" in workflow
    assert "merge_group:" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert config["container"]["platform"] == "linux/amd64"
    assert config["python"]["abi"] == "cp312"
    assert config["dependency_lock"]["path"].endswith(
        "requirements-cp312-manylinux2014-x86_64.lock"
    )
    assert (
        f"image: {config['container']['image']}@{config['container']['digest']}"
        in workflow
    )
    source_control_probe = workflow.index("- name: Verify source-control toolchain")
    checkout = workflow.index("- name: Checkout exact source")
    assert source_control_probe < checkout
    assert "command -v git" in workflow
    assert "git --version" in workflow
    push = workflow.split("  push:", 1)[1].split("  workflow_dispatch:", 1)[0]
    assert "paths:" not in push
    assert '--source-sha "${{ github.sha }}"' in workflow
    assert "ref: ${{ github.sha }}" in workflow
    checkout_options = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout_options.count("with:") == 1
    assert "fetch-depth: 0" in checkout_options
    assert "persist-credentials: false" in checkout_options
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert "python -m pip download" in workflow
    assert "--no-index" in workflow
    assert "--force-reinstall" in workflow
    assert "--no-cache-dir" in workflow
    assert '--find-links "$CANONICAL_WHEELHOUSE"' in workflow
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" rev-parse HEAD' in workflow
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" show -s --format=%ct' in workflow
    assert 'test "$checkout_sha" = "$source_sha"' in workflow
    assert "''|*[!0-9]*)" in workflow
    assert 'echo "SOURCE_DATE_EPOCH=$source_date_epoch"' in workflow
    assert "git config --global" not in workflow
    assert 'echo "SOURCE_DATE_EPOCH=$(git show' not in workflow
    assert 'echo "GIT_CONFIG_COUNT=1" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GIT_CONFIG_KEY_0=safe.directory" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GIT_CONFIG_VALUE_0=$GITHUB_WORKSPACE" >> "$GITHUB_ENV"' in workflow
    assert "GIT_CONFIG_VALUE_0: ${{ github.workspace }}" not in workflow
    assert "scripts/build_canonical_project_wheel.py" in workflow
    assert '--source-date-epoch "$SOURCE_DATE_EPOCH"' in workflow
    assert '--wheelhouse "$CANONICAL_WHEELHOUSE"' in workflow
    assert '--project-wheel-contract "$CANONICAL_WHEEL_CONTRACT"' in workflow
    assert '--dependency-wheelhouse "$CANONICAL_WHEELHOUSE"' in workflow
    assert "canonical-project-wheel-contract.v1.schema.json" in workflow
    assert (
        'receipt["contract_profile"] == "p0-canonical-installed-wheel.v1"' in workflow
    )
    assert 'receipt["contract_pass"] is True' in workflow
    assert "--no-build-isolation -e ." not in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "actions/checkout@v" not in workflow
    assert "actions/upload-artifact@v" not in workflow
    assert "retention-days: 90" in workflow
    assert "scripts/generate_capability_surfaces.py" in workflow
    assert (
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert '--write-candidate-state "$DAG_CANDIDATE_STATE_PATH"' in workflow
    assert '--report "$DAG_CANDIDATE_REPORT_PATH"' in workflow
    assert 'report["scope_pass"] is True' in workflow
    assert 'report["contract_pass"] is False' in workflow
    assert 'report["stale_nodes"] == ["product-state"]' in workflow
    assert '["current_binding"]["status"] == "out_of_scope"' in workflow
    assert "generated-artifact-dag-candidate-${{ github.sha }}" in workflow
    assert workflow.count("include-hidden-files: true") == 2


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
        assert "paths-ignore:" not in pull_request
        assert "merge_group:" in workflow
        assert f"name: {context}" in workflow


def test_workflow_contract_self_validates_strict_yaml_and_full_history() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "workflow-contract-ci.yml"
    ).read_text(encoding="utf-8")
    checkout = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout.count("with:") == 1
    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: false" in checkout

    merge_trigger = workflow.split("  merge_group:", 1)[1].split(
        "  pull_request:", 1
    )[0]
    pull_trigger = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
    push_trigger = workflow.split("  push:", 1)[1].split(
        "  workflow_dispatch:", 1
    )[0]
    for trigger in (merge_trigger, pull_trigger, push_trigger):
        assert "paths:" not in trigger
        assert "paths-ignore:" not in trigger
    assert "types: [checks_requested]" in merge_trigger

    ancestry = workflow.split(
        "- name: Verify local direct and nested merge-parent ancestry", 1
    )[1].split("- name: Set up Python", 1)[0]
    assert "git fetch" not in ancestry
    assert " origin " not in ancestry
    assert "github.token" not in ancestry
    assert "GITHUB_TOKEN" not in ancestry
    assert "git cat-file -p HEAD" in ancestry
    assert 'git cat-file -e "${parent}^{commit}"' in ancestry
    assert 'git cat-file -p "$parent"' in ancestry
    assert 'git cat-file -e "${nested_parent}^{commit}"' in ancestry

    assert "yaml.safe_load" not in workflow
    assert "class StrictWorkflowLoader(yaml.SafeLoader)" in workflow
    assert "path.lstat()" in workflow
    assert "path.is_symlink()" in workflow
    assert "workflow_root.rglob('*.yml')" in workflow
    assert "workflow_root.rglob('*.yaml')" in workflow
    assert "found duplicate key" in workflow
    assert workflow.count("tests/test_repository_python_workflow_contract.py") == 1
    assert workflow.count("tests/test_workflow_yaml_strict.py") == 1


def test_pytest_full_aggregate_is_unique_and_covers_every_shard() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert workflow.count("    name: pytest-full\n") == 1
    assert workflow.count("  full_shards:\n") == 1
    assert workflow.count("  full:\n") == 1
    assert "needs: full_shards" in workflow.split("  full:\n", 1)[1]
    assert "FULL_SHARDS_RESULT: ${{ needs.full_shards.result }}" in workflow
