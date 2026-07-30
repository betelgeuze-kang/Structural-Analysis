from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bounded-planar-opensees-technical.yml"
DOC = ROOT / "docs/bounded-planar-opensees-technical-workflow.md"


def test_workflow_executes_exact_main_package_and_fails_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert 'python-version: "3.10"' in source
    assert (
        "artifacts/vv/bounded_planar_external_linear_case_package/requirements.txt"
        in source
    )
    assert "build_bounded_planar_external_linear_case_package.py" in source
    assert "--check" in source
    assert "bounded_planar_linear_portal.py" in source
    assert "bounded_planar_linear_multistory.py" in source
    assert "ingest_bounded_planar_external_linear_results.py" in source
    assert "--fail-technical-blocked" in source
    assert "continue-on-error" not in source


def test_workflow_attests_receipt_without_promoting_level2() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    documentation = DOC.read_text(encoding="utf-8")

    assert "contents: read" in source
    assert "id-token: write" in source
    assert "attestations: write" in source
    assert "artifact-metadata: write" in source
    assert "uses: actions/attest@v4" in source
    assert "subject-path: ${{ env.RECEIPT_PATH }}" in source
    assert "steps.attest.outputs.bundle-path" in source
    assert "gh attestation verify" in source
    assert '--bundle "$ATTESTATION_BUNDLE_PATH"' in source
    assert "--signer-workflow" in source
    assert '--source-digest "$SOURCE_SHA"' in source
    assert "--source-ref refs/heads/main" in source
    assert "--deny-self-hosted-runners" in source
    assert '--format json > "$ATTESTATION_VERIFICATION_PATH"' in source
    assert "uses: actions/upload-artifact@v7" in source
    assert "if-no-files-found: error" in source
    assert "gh attestation verify" in documentation
    assert "--signer-workflow" in documentation
    assert "independent-operator reproduction" in documentation
    assert "Verification Level 2" in documentation
