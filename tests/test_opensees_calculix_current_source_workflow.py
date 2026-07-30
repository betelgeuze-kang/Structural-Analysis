from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/opensees-calculix-current-source.yml"


def test_workflow_runs_exact_current_main_in_isolated_clean_runner() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "runs-on: ubuntu-22.04" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert "scripts/run_external_vv_clean_runner.sh" in source
    assert '"$EXTERNAL_ASSET_DIR"' in source
    assert "--network none" not in source  # enforced inside the reviewed wrapper
    assert "same_operator_container_isolated_reproduction" in source
    assert "actual_external_solver_execution" in source
    assert "external_runtime_current_source_rerun_missing" in source


def test_workflow_pins_assets_and_never_uploads_solver_packages() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

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
    assert "path: ${{ env.RECEIPT_DIR }}" in source
    upload_section = source.split("- name: Upload receipts without external runtime assets", 1)[1]
    assert "EXTERNAL_ASSET_DIR" not in upload_section


def test_workflow_attests_without_promoting_level2() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    workflow_header = source.split("jobs:", 1)[0]
    job = source.split("  execute-and-attest:", 1)[1]

    assert "id-token: write" not in workflow_header
    assert "attestations: write" not in workflow_header
    assert "id-token: write" in job
    assert "attestations: write" in job
    assert "artifact-metadata: write" in job
    assert "uses: actions/attest@v4" in source
    assert "steps.attest.outputs.bundle-path" in source
    assert "gh attestation verify" in source
    assert "--source-digest" in source
    assert "--source-ref refs/heads/main" in source
    assert "--deny-self-hosted-runners" in source
    assert 'claims.get("verification_level_2") is not False' in source
