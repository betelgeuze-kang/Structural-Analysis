from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow() -> str:
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ci_materializes_validates_and_uploads_current_head_snapshot() -> None:
    workflow = _workflow()

    assert "Build current-HEAD readiness snapshot" in workflow
    assert "python scripts/build_product_readiness_snapshot.py" in workflow
    assert "current-head-product-readiness-snapshot.json" in workflow
    assert 'payload.get("source_commit_sha")' in workflow
    assert 'os.environ["GITHUB_SHA"]' in workflow
    assert "name: current-head-product-readiness-${{ github.sha }}" in workflow
    assert (
        "path: ${{ runner.temp }}/current-head-product-readiness-snapshot.json"
        in workflow
    )


def test_current_head_snapshot_preserves_blocked_release_state() -> None:
    workflow = _workflow()
    step = workflow.split("- name: Build current-HEAD readiness snapshot", 1)[1]
    step = step.split("- name: Upload current-HEAD readiness snapshot", 1)[0]

    assert "--fail-blocked" not in step
    assert "--check" not in step
    assert "--no-write" not in step
