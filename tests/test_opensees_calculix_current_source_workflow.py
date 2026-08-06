from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/opensees-calculix-current-source.yml"
_JOB_HEADING = re.compile(r"(?m)^  [A-Za-z0-9_-]+:\s*$")


def _workflow_source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job_block(source: str, name: str) -> str:
    marker = f"  {name}:\n"
    assert marker in source
    tail = source.split(marker, 1)[1]
    next_job = _JOB_HEADING.search(tail)
    return tail if next_job is None else tail[: next_job.start()]


def _step_block(source: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    assert marker in source
    tail = source.split(marker, 1)[1]
    next_step = tail.find("\n      - name: ")
    return tail if next_step < 0 else tail[:next_step]


def test_workflow_runs_exact_current_source_in_pr_and_main_lanes() -> None:
    source = _workflow_source()
    workflow_header = source.split("jobs:", 1)[0]
    job = _job_block(source, "execute-technical")

    assert "pull_request:" in workflow_header
    assert 'branches: ["main"]' in workflow_header
    assert "workflow_dispatch:" in workflow_header
    assert "runs-on: ubuntu-22.04" in job
    assert "ref: ${{ env.SOURCE_SHA }}" in job
    assert "scripts/run_external_vv_clean_runner.sh" in job
    assert '"$EXTERNAL_ASSET_DIR"' in job
    assert "--network none" not in job  # enforced inside the reviewed wrapper
    assert "same_operator_container_isolated_reproduction" in job
    assert "actual_external_solver_execution" in job
    assert "external_runtime_current_source_rerun_missing" in job

    attest = _step_block(source, "Attest main clean-runner summary provenance")
    verify = _step_block(source, "Retain and verify exact main provenance bundle")
    assert "if: github.ref == 'refs/heads/main'" in attest
    assert "if: github.ref == 'refs/heads/main'" in verify


def test_workflow_pins_assets_and_never_uploads_solver_packages() -> None:
    source = _workflow_source()

    for name, digest in {
        "openseespy-3.7.1.2-py3-none-any.whl": (
            "1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
        ),
        "openseespylinux-3.7.1.2-py3-none-any.whl": (
            "63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
        ),
        "calculix-ccx_2.17-3_amd64.deb": (
            "3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e"
        ),
        "libarpack2_3.8.0-1_amd64.deb": (
            "07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a"
        ),
        "libspooles2.2_2.2-14_amd64.deb": (
            "34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917"
        ),
    }.items():
        assert name in source
        assert digest in source

    assert 'EXTERNAL_ASSET_DIR: "/tmp/' in source
    upload = _step_block(source, "Upload receipts without external runtime assets")
    assert "path: |" in upload
    assert "${{ env.RECEIPT_DIR }}" in upload
    assert "${{ env.HOST_CODE_RECEIPT }}" in upload
    assert "${{ env.HOST_MODAL_RECEIPT }}" in upload
    assert "EXTERNAL_ASSET_DIR" not in upload


def test_workflow_attests_main_only_without_promoting_level2() -> None:
    source = _workflow_source()
    workflow_header = source.split("jobs:", 1)[0]
    job = _job_block(source, "execute-technical")
    attest = _step_block(source, "Attest main clean-runner summary provenance")
    verify = _step_block(source, "Retain and verify exact main provenance bundle")
    boundary = _step_block(source, "Verify fresh current-source technical boundary")

    assert "id-token: write" not in workflow_header
    assert "attestations: write" not in workflow_header
    assert "id-token: write" in job
    assert "attestations: write" in job
    assert "artifact-metadata: write" in job
    assert "uses: actions/attest@v4" in attest
    assert "steps.attest.outputs.bundle-path" in verify
    assert "gh attestation verify" in verify
    assert "--source-digest" in verify
    assert "--source-ref refs/heads/main" in verify
    assert "--deny-self-hosted-runners" in verify
    assert 'claims.get("verification_level_2") is not False' in boundary
    assert 'claims.get("independent_operator_attestation") is not False' in boundary
