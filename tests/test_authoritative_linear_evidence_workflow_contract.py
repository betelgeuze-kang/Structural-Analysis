from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/authoritative-core-evidence-resync.yml"


def test_authoritative_evidence_has_one_branch_writer() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "github.head_ref == 'evidence/authoritative-core-resync'" in text
    assert "push:" not in text
    assert "contents: write" in text
    assert "github.actor != 'github-actions[bot]'" in text
    assert "scripts/verify_phase1_evidence_source_state.py" in text
    assert "Verify exact evidence head" in text
    assert "git push origin HEAD:${{ github.head_ref || github.ref_name }}" in text
