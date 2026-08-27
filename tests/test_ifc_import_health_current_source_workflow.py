from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ifc-import-health-current-source.yml"
IMMUTABLE_ACTION_RE = re.compile(
    r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def test_workflow_runs_exact_current_main_and_attests_technical_receipt() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "runs-on: ubuntu-22.04" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in source
    assert "scripts/acquire_buildingsmart_ifc_current_source.py" in source
    assert "scripts/build_phase3_ifc_import_health_execution_receipt.py" in source
    assert "scripts/build_phase6_silent_import_loss_status.py" in source
    assert "scripts/build_ifc_import_health_current_source_receipt.py" in source
    assert "--fail-technical-blocked" in source
    assert "uses: actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in source
    assert "gh attestation verify" in source
    assert "--source-digest" in source
    assert "--source-ref refs/heads/main" in source
    assert "--deny-self-hosted-runners" in source


def test_workflow_actions_are_immutable_and_permissions_are_job_scoped() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    action_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith("uses: actions/")
    ]
    header = source.split("jobs:", 1)[0]
    job = source.split("  execute-and-attest:", 1)[1]

    assert action_lines
    assert all(IMMUTABLE_ACTION_RE.fullmatch(line) for line in action_lines)
    assert "id-token: write" not in header
    assert "attestations: write" not in header
    assert "id-token: write" in job
    assert "attestations: write" in job
    assert "artifact-metadata: write" in job


def test_workflow_never_uploads_raw_private_corpus_and_preserves_non_authority() -> (
    None
):
    source = WORKFLOW.read_text(encoding="utf-8")
    upload = source.split("- name: Upload receipts without raw IFC inputs", 1)[1]

    assert "path: ${{ env.EVIDENCE_DIR }}" in upload
    assert "private_corpus" not in upload
    assert "find \"$EVIDENCE_DIR\" -type f ! -name '*.json'" in source
    assert '"raw_ifc_files_uploaded"' in source
    for claim in {
        "solver_ready_geometry_or_topology",
        "independent_reproduction",
        "product_legal_approval",
        "redistribution_authority",
        "commercial_use_authority",
        "phase3_quantity_credit",
        "release_authority",
    }:
        assert claim in source
