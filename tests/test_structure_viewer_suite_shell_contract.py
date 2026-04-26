from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_suite_identity_is_documented_in_design_md() -> None:
    text = (ROOT / "DESIGN.md").read_text(encoding="utf-8")

    for fragment in [
        "Structural Insight Viewer suite",
        "index",
        "charts",
        "optimization_history",
        "panel_zone",
        "command-center-shell",
        "charts-command-shell",
        "history-command-shell",
        "panel-inspection-shell",
        "workflow tabs or nav rails",
        "action/status chips",
        "dense but subordinate insight rail",
        "1080px",
        "720px",
    ]:
        assert fragment in text


def test_structure_viewer_suite_has_mobile_overflow_media_rules() -> None:
    css = (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(encoding="utf-8")

    for fragment in [
        "@media (max-width: 1220px)",
        "@media (max-width: 1080px)",
        "@media (max-width: 1120px)",
        "@media (max-width: 820px)",
        "@media (max-width: 720px)",
    ]:
        assert fragment in css

    for fragment in [
        "body.structural-surface.command-center-shell .workflow-nav",
        "body.structural-surface.charts-command-shell .companion-workspace",
        "body.structural-surface.history-command-shell .companion-workspace",
        "body.structural-surface.panel-inspection-shell .panel-stage",
    ]:
        assert fragment in css
