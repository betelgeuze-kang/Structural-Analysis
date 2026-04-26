from pathlib import Path


def test_charts_html_prefers_inline_then_repo_artifacts_then_demo() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert "readInlineArtifactPayload" in text
    assert "__STRUCTURAL_CHARTS_DATA__" in text
    assert "__STRUCTURE_VIEWER_DATA__" in text
    assert "__STRUCTURE_VIEWER_PAYLOAD__" in text
    assert "charts-artifact-data" in text
    assert "results-explorer-data" in text
    assert "../../implementation/phase1/release/visualization/structural_optimization_viewer.json" in text
    assert "../../implementation/phase1/dynamic_time_history_report.json" in text
    assert "../../implementation/phase1/nonlinear_ndtha_stress_report.json" in text
    assert "../../implementation/phase1/member_force_soft_accept_report.json" in text
    assert "cache:'no-store'" in text or 'cache:"no-store"' in text
    assert "demo fallback" in text


def test_charts_html_keeps_suite_shell_identity_and_dense_chrome() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert 'body class="structural-surface charts-command-shell"' in text
    assert 'class="companion-topbar"' in text
    assert 'class="tabs"' in text
    assert 'class="shell-nav-list"' in text
    assert 'class="status-pill"' in text
    assert 'class="companion-canvas"' in text
    assert 'class="companion-insight"' in text


def test_charts_html_surfaces_panel_provenance_labels() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    for element_id in [
        "time-history-info",
        "case-response-info",
        "moment-panel-info",
        "shear-panel-info",
        "distribution-panel-info",
        "story-drift-left-info",
        "story-drift-right-info",
        "envelope-info",
        "artifact-source-pill",
        "artifact-coverage-pill",
    ]:
        assert f'id="{element_id}"' in text


def test_charts_html_adds_line_panel_tooltip_zoom_and_distribution_chart() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert 'id="chart-tooltip"' in text
    assert "function bindLinePanelInteractions(" in text
    assert "function drawLinePanelFocusOverlay(" in text
    assert "canvas.addEventListener('mousedown'" in text
    assert "canvas.addEventListener('click'" in text
    assert "canvas.addEventListener('wheel'" in text
    assert "canvas.addEventListener('mousemove'" in text
    assert "shift+drag: brush zoom" in text
    assert "click: pin" in text
    assert "hover: crosshair sync" in text
    assert 'id="distribution-chart"' in text
    assert 'id="distribution-chart-legend"' in text
    assert "buildDerivedDistributionChart(" in text
    assert "buildExplicitDistributionChart(" in text
    assert "setSharedLineInteraction('hover'" in text
    assert "setSharedLineInteraction('selected'" in text
    assert "resolveSharedLineInteractionForPanel('hover'" in text
    assert "resolveSharedLineInteractionForPanel('selected'" in text


def test_charts_html_adds_grouped_bar_hover_and_click_selection() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert "const groupedBarState=new Map();" in text
    assert "function getGroupedBarState(canvasId)" in text
    assert "function buildGroupedBarInteractionContext(canvasId,chart,bar,kind='hover')" in text
    assert "setSharedGroupedBarInteraction('selected',selectedContext);" in text
    assert "setSharedGroupedBarInteraction('hover',hoverContext);" in text
    assert "Selected · ${selected.category} · ${selected.seriesLabel}" in text
    assert "hover: inspect · click: pin bar · dblclick: clear" in text


def test_charts_html_preserves_selection_set_in_query_and_shared_storage() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert "function normalizeSelectionValues(values)" in text
    assert "params.get('member_set')" in text
    assert "memberIds," in text
    assert "memberSet:memberIds" in text
    assert "selectionSetCount:memberIds.length" in text
    assert "url.searchParams.set('member_set',memberIds.join('|'))" in text


def test_charts_html_adds_synced_cursor_and_point_drilldown_links() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert "const lineInteractionState={hover:null,selected:null};" in text
    assert "function buildChartPointCaseDetailUrl(context)" in text
    assert "function buildChartPointProvenanceUrl(context)" in text
    assert "function updatePointDrilldownLinks()" in text
    assert 'id="case-detail-link"' in text
    assert 'id="point-focus-label"' in text
    assert "getChartInteractionSourceLabel(context,'case_detail')" in text
    assert "getChartInteractionSourceLabel(context,'row_provenance')" in text
    assert "chooseLatestInteractionContext(lineInteractionState.selected,groupedBarInteractionState.selected)" in text
    assert "url.searchParams.set('results_detail_item_index',String(sampleIndex));" in text
    assert "url.searchParams.set('results_companion_item_index',String(sampleIndex));" in text


def test_charts_html_adds_png_export_for_active_tab() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert 'id="export-png-button"' in text
    assert "function drawStoryDriftExportPanel(" in text
    assert "function buildChartExportPanels()" in text
    assert "function exportActiveChartsPng()" in text
    assert "downloadBlob(blob,`structural_charts_${state.activeTab}.png`)" in text


def test_charts_html_adds_point_drilldown_links_and_shared_line_cursor_state() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert 'id="case-detail-link"' in text
    assert 'id="point-focus-label"' in text
    assert "const lineInteractionState={hover:null,selected:null};" in text
    assert "function buildChartPointCaseDetailUrl(" in text
    assert "function buildChartPointProvenanceUrl(" in text
    assert "function updatePointDrilldownLinks()" in text
    assert "getChartInteractionSourceLabel(context,'case_detail')" in text
    assert "getChartInteractionSourceLabel(context,'row_provenance')" in text
