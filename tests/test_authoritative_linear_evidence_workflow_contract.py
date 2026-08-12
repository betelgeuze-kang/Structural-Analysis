from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "deployment/legacy-python-release-publication/authoritative-core-evidence-resync.yml"


def test_authoritative_evidence_has_one_branch_writer() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ARCHIVED - Authoritative Core Evidence Resync" in text
    assert "pull_request:" in text
    assert "github.head_ref == 'evidence/authoritative-core-resync'" in text
    assert "push:" not in text
    assert "contents: write" in text
    assert "github.actor != 'github-actions[bot]'" in text
    assert "scripts/verify_phase1_evidence_source_state.py" in text
    assert "Verify exact evidence head" in text
    assert "git push origin HEAD:${{ github.head_ref || github.ref_name }}" in text


def test_transient_raw_checkpoints_override_legacy_lfs_attributes_locally() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'runtime_checkpoint_dir="implementation/phase1/release_evidence/productization/mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints"' in text
    assert 'exec > >(tee "$RUNNER_TEMP/evidence-staging.log") 2>&1' in text
    assert "mkdir -p .git/info" in text
    assert "'/%s/** -filter -diff -merge\\n'" in text
    assert '>> .git/info/attributes' in text
    assert 'git diff --name-only -z -- "$runtime_checkpoint_dir"' in text
    assert 'git show "HEAD:${path}" > "$restore_path"' in text
    assert 'git clean -fdx -- "$runtime_checkpoint_dir"' in text
    assert 'git diff --quiet -- "$runtime_checkpoint_dir"' in text
    assert '${{ runner.temp }}/evidence-staging.log' in text
    assert "git lfs install --local" not in text
    assert "git lfs fetch" not in text
    assert "git lfs smudge" not in text
    assert "Transient nonlinear checkpoints were not restored exactly" in text
