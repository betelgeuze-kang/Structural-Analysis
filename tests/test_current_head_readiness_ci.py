from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_materializes_and_uploads_current_head_readiness_snapshot() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "Build current-HEAD readiness snapshot" in workflow
    assert "python scripts/build_product_readiness_snapshot.py" in workflow
    assert "--out current-head-product-readiness-snapshot.json" in workflow
    assert "name: current-head-product-readiness-${{ github.sha }}" in workflow
    assert "path: current-head-product-readiness-snapshot.json" in workflow


def test_current_head_snapshot_does_not_require_release_ready_state() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    step = workflow.split("- name: Build current-HEAD readiness snapshot", 1)[1]
    step = step.split("- name: Upload current-HEAD readiness snapshot", 1)[0]

    assert "--fail-blocked" not in step
    assert "--check" not in step
