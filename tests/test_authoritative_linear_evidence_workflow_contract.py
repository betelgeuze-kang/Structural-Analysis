from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/authoritative-core-evidence-resync.yml"


def test_authoritative_evidence_has_one_branch_writer() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["evidence/authoritative-core-resync"]' in text
    assert "pull_request:" not in text
    assert "contents: write" in text
    assert "github.actor != 'github-actions[bot]'" in text
    assert "source_commit_then_evidence_only_commit" in text
    assert "Verify exact evidence head" in text
