from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/mgt-import-health-tenth-source.yml"
IMMUTABLE_ACTION_RE = re.compile(
    r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def test_workflow_is_exact_current_main_hosted_and_attested() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "runs-on: ubuntu-22.04" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in source
    assert "--fail-technical-blocked" in source
    assert "--check-bundle-only" in source
    assert "--check" in source
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


def test_workflow_uploads_hidden_json_only_and_preserves_false_authority() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    upload = source.split("- name: Upload JSON receipts without raw MGT inputs", 1)[1]

    assert "path: ${{ env.EVIDENCE_DIR }}" in upload
    assert "include-hidden-files: true" in upload
    assert "find \"$EVIDENCE_DIR\" -type f ! -name '*.json'" in source
    assert "find \"$EVIDENCE_DIR\" -type f -iname '*.mgt'" in source
    assert "raw_source_retained" in source
    assert "raw_mgt_files_uploaded" in source
    assert (
        'any(value is not False for value in payload.get("claims", {}).values())'
        in source
    )
