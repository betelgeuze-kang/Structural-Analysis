from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_force_diagram_overlay_uses_text_nodes_for_member_identity() -> None:
    source = (REPO_ROOT / "src/structure-viewer/viewer-force-diagram-overlay.js").read_text(
        encoding="utf-8"
    )

    assert "title.innerHTML" not in source
    assert "label.textContent" in source


def test_story_analysis_panel_uses_text_nodes_for_model_identity() -> None:
    source = (REPO_ROOT / "src/structure-viewer/viewer-story-analysis-panel.js").read_text(
        encoding="utf-8"
    )

    assert "info.innerHTML" not in source
    assert "cell.innerHTML" not in source
    assert "headerRow.innerHTML" not in source
    assert "member.textContent" in source
