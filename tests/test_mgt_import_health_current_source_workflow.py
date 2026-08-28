from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/mgt-import-health-current-source.yml"
VERIFIER = ROOT / ".github/workflows/_technical-evidence-attest.yml"
IMMUTABLE_ACTION_RE = re.compile(
    r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def test_workflow_runs_only_on_exact_current_main_and_attests_available_set() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "runs-on: ubuntu-24.04" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in source
    assert "scripts/build_mgt_import_health_current_source_receipt.py" in source
    assert "--fail-available-blocked" in source
    assert "--fail-target-blocked" not in source
    assert "target_10_case_contract_pass" in verifier
    assert "name: produce-unprivileged" in source
    assert "uses: ./.github/workflows/_technical-evidence-attest.yml" in source
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in verifier
    assert "class NoRedirect(HTTPRedirectHandler)" in verifier


def test_workflow_actions_are_immutable_and_permissions_are_job_scoped() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    action_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith("uses: actions/")
    ]
    header = source.split("jobs:", 1)[0]
    producer = source.split("  produce:", 1)[1].split("\n  attest:", 1)[0]
    attest = source.split("\n  attest:", 1)[1]

    assert action_lines
    assert all(IMMUTABLE_ACTION_RE.fullmatch(line) for line in action_lines)
    assert "id-token: write" not in header
    assert "attestations: write" not in header
    assert 'GH_TOKEN: ""' in producer
    assert "id-token: write" not in producer
    assert "attestations: write" not in producer
    assert "artifact-metadata: write" not in producer
    assert "id-token: write" in attest
    assert "attestations: write" in attest
    assert "artifact-metadata: write" in attest


def test_workflow_uploads_only_runtime_json_and_preserves_non_authority() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    upload = source.split("- name: Upload unprivileged sealed handoff without raw MGT", 1)[1]

    assert "path: ${{ env.HANDOFF_ROOT }}" in upload
    assert "include-hidden-files: true" in upload
    assert "find \"$EVIDENCE_DIR\" -type f ! -name '*.json'" in source
    assert 'receipt.get("raw_mgt_files_uploaded") is False' in verifier
    assert "available_independent_case_count" in verifier
    assert "silent_loss_negative_pass_count" in verifier
    assert "all(value is False for value in claims.values())" in verifier
