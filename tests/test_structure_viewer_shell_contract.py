from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_HTML_PATHS = {
    "index": ROOT / "src" / "structure-viewer" / "index.html",
    "charts": ROOT / "src" / "structure-viewer" / "charts.html",
    "history": ROOT / "src" / "structure-viewer" / "optimization_history.html",
    "panel": ROOT / "src" / "structure-viewer" / "panel_zone.html",
}


def _read_viewer_html(page_name: str) -> str:
    return VIEWER_HTML_PATHS[page_name].read_text(encoding="utf-8")


def test_index_html_exposes_compact_enterprise_viewer_shell_primitives() -> None:
    text = (ROOT / "src" / "structure-viewer" / "index.html").read_text(encoding="utf-8")
    stats_text = (ROOT / "src" / "structure-viewer" / "viewer-stats-summary.js").read_text(encoding="utf-8")

    expected_shell_primitives = {
        "top search shell": 'class="top-search-shell"',
        "project pill": 'id="shell-project-pill"',
        "status pill": 'id="shell-status-pill"',
        "viewer tabbar": 'class="viewer-tabbar"',
        "left nav list": 'class="shell-nav-list"',
        "stage overlay panel": 'class="stage-overlay-panel stage-overlay-panel--left"',
        "viewport tool rail": 'class="viewport-tool-rail"',
        "model info grid": 'class="shell-meta-grid"',
    }

    for label, marker in expected_shell_primitives.items():
        assert marker in text, label

    assert "command-center-shell" in text
    assert 'id="search-section"' in text
    assert 'id="member-search-input"' in text
    assert 'id="search-results"' in text
    assert 'id="search-status"' in text
    assert 'id="viewer-provenance"' in text
    assert 'id="stage-panel"' in text
    assert 'id="shell-meta-model"' in text
    assert 'id="shell-meta-nodes"' in text
    assert 'id="shell-meta-elements"' in text
    assert 'id="shell-meta-stories"' in text
    assert 'id="shell-meta-review"' in text
    assert 'id="shell-meta-source"' in text
    assert "Real Drawing Assets" in text
    assert "getRealDrawingAssetRegistry" in text
    assert 'id="real-drawing-quality-panel"' in text
    assert "setRealDrawingQualityFilter" in text
    assert "getRealDrawingSegmentLabel" in text
    assert "real-drawing-switcher" in text
    assert "data-real-drawing-asset-select" in text
    assert "stepRealDrawingAsset" in text
    assert "focusRealDrawingAssetRef" in text
    assert "data-real-drawing-active-inspector" in text
    assert "getRealDrawingInspectorRows" in text
    assert "data-real-drawing-browser-query" in text
    assert "data-real-drawing-browser-sort" in text
    assert "data-real-drawing-next-review" in text
    assert "REAL_DRAWING_BROWSER_STATE_KEY" in text
    assert "viewer-real-drawing-browser-state.js" in text
    assert "viewer-real-drawing-quality.js" in text
    assert "viewer-stats-summary.js" in text
    assert "drawing_asset" in text
    assert "data-real-drawing-copy-link" in text
    assert "data-real-drawing-recent-asset" in text
    assert "rememberRealDrawingAssetRef" in text
    assert "copyRealDrawingDeepLink" in text
    assert "setRealDrawingAssetQuery" in text
    assert "setRealDrawingBrowserSort" in text
    assert "sortRealDrawingBrowserAssets" in text
    assert "realDrawingAssetMatchesBrowserQuery" in text
    assert "real-drawing-inspector-cell" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "real-drawing-browser-item" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "real-drawing-recent-rail" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "real-drawing-action-row" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "Drawing Review Queue" in stats_text
    assert "Next Unlock Batch" in text
    assert "Solver-Exact Target Reached" in text
    assert "IFC Reconstruction Queue" in text
    assert "getRealDrawingOpenPromotionItems" in text
    assert "data-real-drawing-open-promotion-count" in text
    assert "getRealDrawingPromotionQueue" in text
    assert "data-real-drawing-promotion-asset" in text
    assert "quality-badge--exact" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "Structural Insight Viewer" in text
    assert "Structural Model Workspace" in text


def test_dark_viewer_shell_pages_keep_shared_provenance_and_control_vocabulary() -> None:
    shared_fragments = (
        "structural-surface",
        "provenance-label",
        "provenance-value",
        "Source",
        "Report",
        "Timestamp",
        "Selection",
        "Light",
        "Shortcuts",
    )
    shell_classes = {
        "index": "command-center-shell",
        "charts": "charts-command-shell",
        "history": "history-command-shell",
        "panel": "panel-inspection-shell",
    }

    for page_name, shell_class in shell_classes.items():
        text = _read_viewer_html(page_name)
        assert shell_class in text, page_name
        for fragment in shared_fragments:
            assert fragment in text, f"{page_name} missing shared vocabulary fragment: {fragment}"

    index_text = _read_viewer_html("index")
    assert "Structural Insight Viewer" in index_text


def test_companion_shell_pages_keep_command_center_stage_markers() -> None:
    charts_text = _read_viewer_html("charts")
    assert 'class="companion-topbar"' in charts_text
    assert 'class="companion-workspace"' in charts_text
    assert 'class="companion-canvas"' in charts_text
    assert 'class="companion-insight"' in charts_text
    assert 'class="controls companion-footer"' in charts_text
    assert 'data-rail-tab-key="timeseries"' in charts_text
    assert "setActiveChartShellTab" in charts_text

    history_text = _read_viewer_html("history")
    assert 'class="companion-topbar"' in history_text
    assert 'class="companion-workspace history-workspace"' in history_text
    assert 'class="container companion-canvas"' in history_text
    assert 'class="summary-bar companion-insight"' in history_text

    panel_text = _read_viewer_html("panel")
    assert 'class="panel-command-topbar"' in panel_text
    assert 'id="panel-stage"' in panel_text
    assert 'id="panel-viewport"' in panel_text
    assert 'class="panel-tool-rail"' in panel_text
    assert 'class="panel-insight-rail"' in panel_text
    assert "panelViewport.appendChild(renderer.domElement)" in panel_text


def test_dark_viewer_shell_pages_keep_suite_shell_grammar_markers() -> None:
    page_contracts = {
        "index": {
            "workflow": ("class=\"viewer-tabbar\"", "class=\"shell-nav-list\""),
            "chip": ("class=\"status-pill\"", "class=\"context-chip\""),
            "stage": ("class=\"stage-shell\"", "class=\"stage-frame\""),
            "insight": ("class=\"insight-rail\"",),
        },
        "charts": {
            "workflow": ("class=\"tabs\"", "class=\"shell-nav-list\""),
            "chip": ("class=\"status-pill\"",),
            "stage": ("class=\"companion-canvas\"",),
            "insight": ("class=\"companion-insight\"",),
        },
        "history": {
            "workflow": ("class=\"shell-nav-list\"",),
            "chip": ("class=\"chip chip-button\"", "class=\"provenance-status\""),
            "stage": ("class=\"container companion-canvas\"",),
            "insight": ("class=\"summary-bar companion-insight\"",),
        },
        "panel": {
            "workflow": ("class=\"viewer-tabbar\"",),
            "chip": ("class=\"context-chip\"", "class=\"provenance-status\""),
            "stage": ("class=\"panel-stage\"",),
            "insight": ("class=\"panel-insight-rail\"",),
        },
    }

    for page_name, contracts in page_contracts.items():
        text = _read_viewer_html(page_name)
        assert "structural-surface" in text, page_name
        for category, fragments in contracts.items():
            assert any(fragment in text for fragment in fragments), f"{page_name} missing {category} marker"


def test_panel_zone_shell_keeps_stage_signal_and_pointer_overlay_contract() -> None:
    html = _read_viewer_html("panel")
    css = (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(encoding="utf-8")

    assert 'id="viewport-selection-chip"' in html
    assert 'id="stage-handoff-mode"' in html
    assert 'id="viewport-pick-status"' in html
    assert "panel_zone_object_id" in html
    assert "panel_zone_object_kind" in html
    assert "panelZoneObjectId" in html
    assert "panelZoneObjectKind" in html
    assert "buildObjectSelection(" in html
    assert "updateSelectionHandoff(" in html
    assert 'role="application"' in html
    assert 'tabindex="0"' in html
    assert 'class="panel-crosshair"' in html
    assert 'class="viewport-status-card"' in html
    assert "body.structural-surface.panel-inspection-shell .panel-crosshair" in css
    assert "body.structural-surface.panel-inspection-shell .panel-tool-rail button" in css
    assert "cursor:pointer" in css
