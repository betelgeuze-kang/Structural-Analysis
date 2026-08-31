from __future__ import annotations

from pathlib import Path

from scripts import check_github_actions_runner_policy


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/g1-production-mgt-gfx1100-hardware.yml"
RUNBOOK_PATH = ROOT / "docs/ai/G1_MGT_GFX1100_RUNBOOK.md"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_runbook_matches_cli_and_ephemeral_auth_preflight() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "gh attestation verify" in runbook
    assert "workflow-scoped" in runbook
    assert "${{ github.token }}" in runbook
    assert "no persistent runner login" in runbook
    assert "--retained-file gfx1100.worker-contract.json" in runbook
    assert "successful run and exact-head SHA" in runbook
    assert "wheel_identity_bound_at_execution=false" in runbook


def test_gfx1100_lane_is_manual_main_only_and_dedicated() -> None:
    workflow = _workflow()
    trigger = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]

    assert trigger.strip() == "workflow_dispatch: {}"
    for forbidden in (
        "pull_request:",
        "pull_request_target:",
        "push:",
        "schedule:",
        "workflow_run:",
    ):
        assert forbidden not in trigger
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "environment: g1-production-gfx1100" in workflow
    assert (
        "runs-on: [self-hosted, linux, x64, amd, rocm, gfx1100, g1-production-gfx1100]"
    ) in workflow
    assert "cancel-in-progress: false" in workflow
    assert "inputs.source_sha" not in workflow
    assert "github.event.inputs" not in workflow

    policy = check_github_actions_runner_policy.check_runner_policy()
    row = next(
        item
        for item in policy["rows"]
        if item["workflow"]
        == ".github/workflows/g1-production-mgt-gfx1100-hardware.yml"
    )
    assert row["execution_class"] == "hardware_or_private_self_hosted"
    assert row["ok"] is True
    assert policy["contract_pass"] is True


def test_gfx1100_lane_fails_closed_on_exact_source_device_and_retained_bytes() -> None:
    workflow = _workflow()

    required = (
        "ref: ${{ github.sha }}",
        "fetch-depth: 0",
        "persist-credentials: false",
        'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"',
        "git ls-remote --exit-code origin refs/heads/main",
        'test "$remote_main" = "$EXPECTED_SOURCE_SHA"',
        "git status --porcelain --untracked-files=all",
        'test "$INDEPENDENCE_ATTESTED" = "true"',
        'test "$EVIDENCE_RUNNER_ID" = "$EXPECTED_RUNNER_ID"',
        "^sha256:[0-9a-f]{64}$",
        "test -c /dev/kfd",
        "test -d /dev/dri",
        "grep -q 'Name:[[:space:]]*gfx1100'",
        "default_arch=",
        "runner._detect_architecture",
        'test "$default_arch" = "$EXPECTED_DEVICE_ARCHITECTURE"',
        "--no-deps",
        "--no-build-isolation",
        '--source-sha "$EXPECTED_SOURCE_SHA"',
        '--github-run-id "$GITHUB_RUN_ID"',
        '--github-run-attempt "$GITHUB_RUN_ATTEMPT"',
        '--artifact-prefix "$RUN_ARTIFACT_PREFIX"',
        '--receipt-runner-id "$RECEIPT_RUNNER_ID"',
        "--expected-signer-public-key-sha256",
        '--wheel "$GFX1100_WHEEL"',
        '--runner-id "$RECEIPT_RUNNER_ID"',
        'hardware["gcn_arch_name"] == os.environ["EXPECTED_DEVICE_ARCHITECTURE"]',
        'receipt["signature"]["state"] == "unsigned"',
        'evidence["wheel"]["bound_at_execution"] is False',
        'receipt["claims"]["wheel_identity_bound_at_execution"] is False',
        "wheel_identity_not_bound_at_execution",
        '--artifact-root "$ARTIFACT_ROOT"',
        '--retained-wheel "$GFX1100_WHEEL_REL"',
        '--retained-file "$GFX1100_SIGNING_PAYLOAD_REL"',
        "--build-archive",
        "--check-archive",
        "gh attestation verify --help >/dev/null",
        "gh auth status --hostname github.com >/dev/null 2>&1",
        'assert gate["claims"][claim] is False',
        "current_source_gfx1030_receipt_missing",
        "independently_attested_cpu_fallback_zero_missing",
        "gfx1030_gfx1100_terminal_resultir_diagnosticir_parity_missing",
        "signed_retained_bundle_provenance_not_imported",
        "gfx1100_retained_wheel_bytes_not_bound",
    )
    for value in required:
        assert value in workflow

    assert "if: always()" not in workflow
    assert "if: success()" in workflow
    assert "dist/structural_analysis" not in workflow
    assert "git lfs" not in workflow.lower()
    assert "release_evidence/productization" not in workflow
    assert "EXPECTED_WHEEL_SHA256" not in workflow
    assert "EXPECTED_SOURCE_SHA: ${{ github.sha }}" in workflow
    assert "secrets." not in workflow
    assert "--private-key" not in workflow
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    assert 'echo "$GH_TOKEN"' not in workflow
    assert "printenv GH_TOKEN" not in workflow
    assert workflow.count('--github-run-id "$GITHUB_RUN_ID"') >= 4
    assert workflow.count('--github-run-attempt "$GITHUB_RUN_ATTEMPT"') >= 4
    assert workflow.count('--artifact-prefix "$RUN_ARTIFACT_PREFIX"') >= 4
    assert workflow.count('--expected-runner-id "$EXPECTED_RUNNER_ID"') >= 4


def test_gfx1100_lane_retains_and_verifies_signed_workflow_provenance() -> None:
    workflow = _workflow()

    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "artifact-metadata: write" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert "subject-path: ${{ env.EVIDENCE_ARCHIVE }}" in workflow
    assert 'gh attestation verify "$EVIDENCE_ARCHIVE"' in workflow
    assert '--signer-digest "$EXPECTED_SOURCE_SHA"' in workflow
    assert '--source-digest "$EXPECTED_SOURCE_SHA"' in workflow
    assert "--source-ref refs/heads/main" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "include-hidden-files: false" in workflow
    assert "retention-days: 90" in workflow
    upload = workflow.split("- name: Upload immutable archive and provenance only", 1)[
        1
    ]
    assert "${{ env.EVIDENCE_ARCHIVE }}" in upload
    assert "${{ env.PROVENANCE_BUNDLE }}" in upload
    assert "${{ env.ARTIFACT_ROOT }}" not in upload
    assert "path: ${{ env.ARTIFACT_ROOT }}" not in workflow


def test_final_main_drift_guards_precede_attestation_and_upload() -> None:
    workflow = _workflow()
    attest_guard = workflow.index(
        "- name: Final current-main and immutable archive guard before attestation"
    )
    attest = workflow.index(
        "- name: Attest the deterministic immutable evidence archive"
    )
    upload_guard = workflow.index(
        "- name: Final current-main guard immediately before upload"
    )
    upload = workflow.index("- name: Upload immutable archive and provenance only")
    post_upload_guard = workflow.index("- name: Reject a moving main after upload")
    assert attest_guard < attest < upload_guard < upload < post_upload_guard
    assert workflow.count("git ls-remote --exit-code origin refs/heads/main") >= 4
    for section in (
        workflow[attest_guard:attest],
        workflow[upload_guard:upload],
    ):
        assert 'test "$remote_main" = "$EXPECTED_SOURCE_SHA"' in section
        assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"' in section
        assert "git status --porcelain --untracked-files=all" in section
        assert "--check-archive" in section
    post_upload_section = workflow[post_upload_guard:]
    assert 'test "$remote_main" = "$EXPECTED_SOURCE_SHA"' in post_upload_section
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"' in (
        post_upload_section
    )


def test_gfx1100_lane_sources_compile_and_do_not_expand_artifact_allowlist() -> None:
    python_paths = (
        "scripts/build_g1_hip_residual_jvp_worker_contract.py",
        "scripts/build_g1_mgt_cross_device_gate.py",
        "src/structural_analysis/engine_v2_backends/"
        "_hip_residual_jvp_worker_contract.py",
        "src/structural_analysis/engine_v2_backends/hip_residual_jvp_worker.py",
    )
    for relative in python_paths:
        source = (ROOT / relative).read_text(encoding="utf-8")
        compile(source, relative, "exec")

    allowlist = (
        ROOT / "implementation/phase1/source_boundary_allowlist.json"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "g1-production-mgt-gfx1100",
        "g1_mgt_cross_device_gate",
        "structural_analysis-current.whl",
        "gfx1100.device-receipt",
        "gfx1100.provenance-bundle",
    ):
        assert forbidden not in allowlist
    for path in (
        WORKFLOW_PATH,
        ROOT / "docs/ai/G1_MGT_GFX1100_RUNBOOK.md",
        *(ROOT / relative for relative in python_paths),
    ):
        assert path.stat().st_size < 1024 * 1024
