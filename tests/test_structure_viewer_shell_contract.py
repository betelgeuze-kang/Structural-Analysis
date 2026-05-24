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
    analysis_cockpit_text = (
        ROOT / "src" / "structure-viewer" / "viewer-analysis-cockpit-model.js"
    ).read_text(encoding="utf-8")
    panel_zone_evidence_text = (
        ROOT / "src" / "structure-viewer" / "viewer-panel-zone-evidence.js"
    ).read_text(encoding="utf-8")
    panel_model_text = (ROOT / "src" / "structure-viewer" / "viewer-real-drawing-panel-model.js").read_text(
        encoding="utf-8"
    )
    panel_events_text = (ROOT / "src" / "structure-viewer" / "viewer-real-drawing-panel-events.js").read_text(
        encoding="utf-8"
    )
    tree_model_text = (ROOT / "src" / "structure-viewer" / "viewer-real-drawing-tree-model.js").read_text(
        encoding="utf-8"
    )
    side_panel_model_text = (ROOT / "src" / "structure-viewer" / "viewer-side-panel-model.js").read_text(
        encoding="utf-8"
    )
    search_results_model_text = (ROOT / "src" / "structure-viewer" / "viewer-search-results-model.js").read_text(
        encoding="utf-8"
    )
    selection_summary_model_text = (
        ROOT / "src" / "structure-viewer" / "viewer-selection-summary-model.js"
    ).read_text(encoding="utf-8")
    renderer_text = (ROOT / "src" / "structure-viewer" / "viewer-real-drawing-panel-renderer.js").read_text(
        encoding="utf-8"
    )
    drawing_handoff_renderer_text = (
        ROOT / "src" / "structure-viewer" / "viewer-drawing-handoff-panel-renderer.js"
    ).read_text(encoding="utf-8")
    stage_callouts_renderer_text = (
        ROOT / "src" / "structure-viewer" / "viewer-stage-result-callouts-renderer.js"
    ).read_text(encoding="utf-8")

    expected_shell_primitives = {
        "top search shell": 'class="top-search-shell"',
        "project pill": 'id="shell-project-pill"',
        "topbar project selector": "data-shell-project-select",
        "topbar project receipt": "data-shell-project-receipt",
        "status pill": 'id="shell-status-pill"',
        "top run control": "data-top-run-control",
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
    assert 'id="shell-meta-height"' in text
    assert 'id="shell-meta-units"' in text
    assert 'id="shell-meta-analysis-type"' in text
    assert 'id="shell-meta-last-run"' in text
    assert 'id="shell-meta-review"' in text
    assert 'id="shell-meta-source"' in text
    assert 'data-model-overview-panel' in text
    assert 'data-source-adapter-matrix' in text
    assert 'id="shell-source-adapter-stack"' in text
    assert "structure-viewer-source-adapter-matrix.v1" in text
    assert "buildSourceAdapterMatrix" in text
    assert "renderSourceAdapterMatrix" in text
    assert 'id="top-run-compare-button"' in text
    assert 'id="top-run-new-button"' in text
    assert "data-top-run-receipt" in text
    assert "data-top-run-action" in text
    assert "syncTopRunControl" in text
    assert "startNewReviewRun" in text
    assert "renderTopbarProjectSelector" in text
    assert "setTopbarWorkspaceSelection" in text
    assert "Real Drawing Assets" in tree_model_text
    assert "getRealDrawingAssetRegistry" in text
    assert 'id="real-drawing-quality-panel"' in text
    assert "setRealDrawingQualityFilter" in text
    assert "getRealDrawingSegmentLabel" in tree_model_text
    assert "real-drawing-switcher" in renderer_text
    assert "data-real-drawing-asset-select" in renderer_text
    assert "stepRealDrawingAsset" in text
    assert "focusRealDrawingAssetRef" in text
    assert "data-real-drawing-active-inspector" in renderer_text
    assert "getRealDrawingInspectorRows" in renderer_text
    assert "data-real-drawing-browser-query" in renderer_text
    assert "data-real-drawing-browser-sort" in renderer_text
    assert "data-real-drawing-next-review" in renderer_text
    assert "REAL_DRAWING_BROWSER_STATE_KEY" in text
    assert "viewer-real-drawing-browser-state.js" in text
    assert "viewer-real-drawing-quality.js" in text
    assert "viewer-real-drawing-panel-events.js" in text
    assert "viewer-real-drawing-panel-model.js" in text
    assert "viewer-real-drawing-panel-renderer.js" in text
    assert "viewer-real-drawing-selection.js" in text
    assert "viewer-real-drawing-tree-model.js" in text
    assert "viewer-search-results-model.js" in text
    assert "viewer-selection-summary-model.js" in text
    assert "viewer-side-panel-model.js" in text
    assert "viewer-stats-summary.js" in text
    assert "viewer-analysis-cockpit-model.js" in text
    assert "viewer-panel-zone-evidence.js" in text
    assert "viewer-drawing-handoff-panel-renderer.js" in text
    assert "viewer-stage-result-callouts-renderer.js" in text
    assert "buildAnalysisCockpitModel" in text
    assert "buildDrawingHandoffPanelHtml" in text
    assert "buildStageResultCalloutsHtml" in text
    assert "renderStageResultCallouts" in text
    assert "syncCriticalMemberReviewFocus" in text
    assert 'id="stage-result-callouts"' in text
    assert 'id="stage-result-receipt"' in text
    assert "data-stage-result-receipt" in text
    assert "renderStageResultReceipt" in text
    assert "formatContourSourceLabel" in text
    assert "stage-result-receipt__row" in text
    assert 'id="stage-critical-hotspots"' in text
    assert "data-stage-critical-hotspots" in text
    assert "structure-viewer-stage-critical-hotspots.v1" in text
    assert "renderStageCriticalHotspots" in text
    assert "positionStageCriticalHotspots" in text
    assert "__STRUCTURE_VIEWER_STAGE_CRITICAL_HOTSPOTS_STATE__" in text
    assert "data-stage-review-controls" in text
    assert "data-stage-view-mode-select" in text
    assert "data-stage-model-stack" in text
    assert "data-stage-review-control-receipt" in text
    assert "data-stage-deformation-control" in text
    assert "data-stage-deformation-scale-slider" in text
    assert "structure-viewer-deformation-control.v1" in text
    assert "updateDeformDisplayScale" in text
    assert "formatDeformDisplayScale" in text
    assert "syncStageReviewControls" in text
    assert "stage-review-control-receipt__row" in text
    assert "data-contour-scale-evidence" in text
    assert "data-contour-scale-ticks" in text
    assert "data-contour-colorbar" in text
    assert "renderContourScaleEvidence" in text
    assert "data-analysis-result-evidence" in text
    assert "renderAnalysisResultEvidence" in text
    assert "analysis-result-evidence-row" in text
    assert 'id="result-step-schedule-panel"' in text
    assert "data-result-step-schedule" in text
    assert "renderResultStepSchedule" in text
    assert "buildResultStepScheduleModel" in text
    assert "structure-viewer-result-step-schedule.v1" in text
    assert "data-result-step-row" in text
    assert "data-result-step-active" in text
    assert "setAnalysisTimelineStep" in text
    assert 'id="result-envelope-panel"' in text
    assert "data-result-envelope" in text
    assert "renderResultEnvelope" in text
    assert "buildResultEnvelopeModel" in text
    assert "structure-viewer-result-envelope.v1" in text
    assert "data-result-envelope-row" in text
    assert "data-result-envelope-member-id" in text
    assert 'id="panel-zone-evidence-panel"' in text
    assert "data-panel-zone-evidence" in text
    assert "data-panel-zone-member-row" in text
    assert "renderPanelZoneEvidencePanel" in text
    assert "buildPanelZoneEvidenceModel" in text
    assert "structure-viewer-panel-zone-evidence.v1" in text
    assert 'id="panel-zone-stage-badge"' in text
    assert "data-panel-zone-stage-badge" in text
    assert "structure-viewer-panel-zone-stage-badge.v1" in text
    assert "renderPanelZoneStageBadge" in text
    assert "positionPanelZoneStageBadge" in text
    assert "__STRUCTURE_VIEWER_PANEL_ZONE_STAGE_BADGE_STATE__" in text
    assert "PANEL_ZONE_EVIDENCE_SCHEMA" in panel_zone_evidence_text
    assert "panel_zone_clash_artifact.json" in panel_zone_evidence_text
    assert "panel_zone_solver_verified_handoff_report.json" in panel_zone_evidence_text
    assert "data-delivery-review-receipt" in text
    assert "buildDeliveryReviewReceiptModel" in text
    assert "renderDeliveryReviewReceipt" in text
    assert "structure-viewer-delivery-review-receipt.v1" in text
    assert "delivery-review-receipt__row" in text
    assert 'id="material-member-catalog-panel"' in text
    assert "data-material-member-catalog" in text
    assert "buildMaterialMemberCatalogPanelModel" in text
    assert "renderMaterialMemberCatalogPanel" in text
    assert "structure-viewer-material-member-catalog.v1" in text
    assert "MATERIAL_FAMILY_ONTOLOGY" in text
    assert "data-material-family-coverage" in text
    assert "data-material-family-chip" in text
    assert "data-material-family-ontology-count" in text
    assert "rail_steel" in text
    assert "seismic_isolator" in text
    assert "damper" in text
    assert "fireproofing" in text
    assert "waterproofing" in text
    assert "insulation" in text
    assert "expansion_joint" in text
    assert "known_material_family_count" in (
        ROOT / "src" / "structure-viewer" / "viewer-direct-model-normalizer.js"
    ).read_text(encoding="utf-8")
    assert "material_family_ontology_count" in (
        ROOT / "src" / "structure-viewer" / "viewer-direct-model-normalizer.js"
    ).read_text(encoding="utf-8")
    assert "structure-viewer-material-family-coverage.v1" in (
        ROOT / "src" / "structure-viewer" / "viewer-direct-model-normalizer.js"
    ).read_text(encoding="utf-8")
    assert "material-catalog-row__props" in text
    assert "data-material-section-schedule" in text
    assert "data-material-section-row" in text
    assert "material_section_schedule_count" in text
    assert "material_section" in text
    assert "data-section-schedule" in text
    assert "data-section-schedule-row" in text
    assert "section_material_schedule_count" in text
    assert "section_id" in text
    assert "material_catalog_summary" in (
        ROOT / "src" / "structure-viewer" / "viewer-direct-model-normalizer.js"
    ).read_text(encoding="utf-8")
    assert "buildMaterialCatalogSummary" in (
        ROOT / "src" / "structure-viewer" / "viewer-direct-model-normalizer.js"
    ).read_text(encoding="utf-8")
    assert "data-utilization-heatmap-evidence" in text
    assert "analysis-heatmap-receipt" in text
    assert "analysis-heatmap-hotspot" in text
    assert "data-heatmap-level-chip" in text
    assert 'id="stage-overlay-receipt"' in text
    assert "data-stage-overlay-receipt" in text
    assert "data-stage-overlay-visual-evidence" in text
    assert "data-stage-overlay-load-key" in text
    assert "data-stage-overlay-support-key" in text
    assert "renderAnalysisStageOverlayReceipt" in text
    assert "setAnalysisStageOverlayState" in text
    assert "__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__" in text
    assert "stage-overlay-receipt__row" in text
    assert "stage-overlay-legend-swatch--load" in text
    assert "stage-overlay-legend-swatch--support" in text
    assert "load-case-evidence-row" in text
    assert "data-load-case-status" in text
    assert "data-load-case-kind" in text
    assert "data-viewport-tool-rail" in text
    assert "data-viewport-tool-render-mode" in text
    assert "data-viewport-view-preset" in text
    assert "syncViewportToolRailState" in text
    assert "classifyLoadCaseKind" in (
        ROOT / "src" / "structure-viewer" / "viewer-side-panel-model.js"
    ).read_text(encoding="utf-8")
    assert "load-case-evidence-row__bar" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "stage-model-stack__row" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "stage-deformation-control__head" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "stage-contour-scale__body" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "analysis-heatmap-gradient" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "viewport-tool-group" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert "viewport-tool-rail button::after" in (
        ROOT / "src" / "structure-viewer" / "design-theme.css"
    ).read_text(encoding="utf-8")
    assert 'id="viewport-selection-focus-badge"' in text
    assert "selectionFocusOverlayGroup" in text
    assert "selected-member-focus-overlays" in text
    assert "getViewerPointFromCoordinate" in text
    assert "buildElementFocusState" in text
    assert "getSelectedFocusRecords" in text
    assert "rebuildSelectionFocusOverlay" in text
    assert "positionViewportSelectionFocusBadge" in text
    assert "positionStageResultCalloutDock" in text
    assert "window.positionStageResultCalloutDock=positionStageResultCalloutDock;" in text
    assert "getRectOverlapArea" in text
    assert "data-stage-callout-dock" in text
    assert "data-stage-callout-overlap" in text
    assert "selected_member_focus_halo" in text
    assert "selected_member_focus_secondary_marker" in text
    assert "data-viewport-selection-focus-count" in text
    assert "data-viewport-selection-focus-edge" in text
    assert "is-edge-pinned" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "data-stage-result-callouts" in text
    assert "data-stage-result-callout-key" in stage_callouts_renderer_text
    assert "data-stage-callout-focus-member" in stage_callouts_renderer_text
    assert "max-displacement" in stage_callouts_renderer_text
    assert "critical-member" in stage_callouts_renderer_text
    assert "aria-pressed" in stage_callouts_renderer_text
    assert "mode:event.ctrlKey||event.metaKey?'toggle':'replace'" in text
    assert "memberIds:currentSelection.memberIds" in text
    assert "renderDrawingHandoffPanel" in text
    assert "setDrawingHandoffActiveSheet" in text
    assert "bindDrawingHandoffSheetInteractions" in text
    assert "copyDrawingHandoffDeepLink" in text
    assert "data-drawing-handoff-preview" in drawing_handoff_renderer_text
    assert "data-drawing-handoff-preview-link" in drawing_handoff_renderer_text
    assert "data-drawing-handoff-active-sheet-open" in drawing_handoff_renderer_text
    assert "data-drawing-handoff-sheet-href" in drawing_handoff_renderer_text
    assert "aria-current" in drawing_handoff_renderer_text
    assert "drawing-handoff-preview__svg" in drawing_handoff_renderer_text
    assert "data-drawing-handoff-copy-link" in drawing_handoff_renderer_text
    assert "data-drawing-handoff-sheet" in drawing_handoff_renderer_text
    assert "Drawing Handoff" in drawing_handoff_renderer_text
    assert "ANALYSIS_COCKPIT_KPI_KEYS" in analysis_cockpit_text
    assert "Max Displacement" in analysis_cockpit_text
    assert "referenceLabel" in analysis_cockpit_text
    assert "trendLabel" in analysis_cockpit_text
    assert "evidenceLabel" in analysis_cockpit_text
    assert "kpi-card__evidence" in text
    assert "kpi-card__trend" in text
    assert "kpi-card__reference" in text
    assert "kpi-sparkline__area" in text
    assert "kpi-sparkline__dot" in text
    assert "Critical Members" in text
    assert "data-critical-status" in text
    assert "data-critical-ratio" in text
    assert "critical-member-ratio__track" in text
    assert "critical-member-drift" in text
    assert "critical-member-action" in text
    assert 'id="optimization-summary-panel"' in text
    assert "data-optimization-summary-details-link" in text
    assert "optimization-summary-card__source" in text
    assert "optimization-summary-bars" in text
    assert "optimization-summary-bar--after" in text
    assert "optimization-summary-saved" in text
    assert 'id="drawing-handoff-panel"' in text
    assert 'id="critical-members-panel"' in text
    assert 'id="analysis-cockpit-chart-strip"' in text
    assert 'id="analysis-timeline-status"' in text
    assert "analysis-timeline-control" in text
    assert "setAnalysisTimelineStep" in text
    assert "stepAnalysisTimeline" in text
    assert "toggleAnalysisTimelinePlayback" in text
    assert "analysisTimelineStepOverride" in text
    assert "analysis-timeline-slider" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "analysis-timeline-buttons" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "analysis-drift-chart" in text
    assert "analysis-chart-grid" in text
    assert "analysis-chart-dot" in text
    assert "analysis-chart-ticks" in text
    assert "analysis-chart-peak-label" in text
    assert "analysis-chart-step-label" in text
    assert "analysis-load-step-chart" in text
    assert "analysis-chart-legend--drift" in text
    assert "originalDriftPct" in text
    assert "optimizedDriftPct" in text
    assert "analysis-material-chart" in text
    assert "analysis-material-group" in text
    assert "analysis-material-bar--original" in text
    assert "analysis-material-bar--optimized" in text
    assert "analysis-material-chart" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "kpi-card__trend--success" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "critical-member-ratio__track" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "critical-member-action--danger" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "analysis-chart-ticks" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "analysis-material-chart" in (
        ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"
    ).read_text(encoding="utf-8")
    assert "drawing-handoff-preview" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "stage-result-callouts" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "Dense cockpit short-viewport compression" in (
        ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"
    ).read_text(encoding="utf-8")
    assert "@media (max-height: 940px) and (min-width: 1221px)" in (
        ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"
    ).read_text(encoding="utf-8")
    assert 'data-stage-callout-dock="bottom-right"' in (
        ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"
    ).read_text(encoding="utf-8")
    assert "critical-members-row.is-selected" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "viewport-selection-focus-badge" in (ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css").read_text(
        encoding="utf-8"
    )
    assert "renderAnalysisCockpitCharts" in text
    assert "analysis-stage-overlays" in text
    assert "lateral_load_arrow" in text
    assert "support_marker" in text
    assert "stage-overlay-receipt" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "stage-overlay-visual-evidence" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "<span>Drift</span>" in text
    assert "analysisStageOverlayDark" in (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    assert "clip-path:inset(50%)" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "drawing_asset" in text
    assert "data-real-drawing-copy-link" in renderer_text
    assert "data-real-drawing-recent-asset" in renderer_text
    assert "rememberRealDrawingAssetRef" in text
    assert "bindRealDrawingQualityPanelEvents" in text
    assert "copyRealDrawingDeepLink" in text
    assert "setRealDrawingAssetQuery" in text
    assert "setRealDrawingBrowserSort" in text
    assert "sortRealDrawingBrowserAssets" in panel_model_text
    assert "realDrawingAssetMatchesBrowserQuery" in panel_model_text
    assert "data-real-drawing-browser-clear" in panel_events_text
    assert "data-real-drawing-promotion-asset" in panel_events_text
    assert "buildRealDrawingTreeModel" in text
    assert "badge-real-drawing-" in text
    assert "No assets match the active drawing quality filter." in tree_model_text
    assert "buildLoadCaseListModel" in text
    assert "buildLayerToggleItems" in text
    assert "Artifact-driven view" in side_panel_model_text
    assert "buildViewerSearchResultsModel" in text
    assert "Search ready | members" in search_results_model_text
    assert "data-search-focus" in text
    assert "buildSelectionSetSummary" in text
    assert "Clear Selection (" in selection_summary_model_text
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
    assert "Next Unlock Batch" in renderer_text
    assert "Solver-Exact Target Reached" in renderer_text
    assert "IFC Reconstruction Queue" in panel_model_text
    assert "getRealDrawingOpenPromotionItems" in panel_model_text
    assert "data-real-drawing-open-promotion-count" in renderer_text
    assert "getRealDrawingPromotionQueue" in panel_model_text
    assert "data-real-drawing-promotion-asset" in renderer_text
    assert "quality-badge--exact" in (ROOT / "src" / "structure-viewer" / "design-theme.css").read_text(
        encoding="utf-8"
    )
    assert "Structural Insight Viewer" in text
    assert "Optimization Cockpit" in text
    assert "function getViewerModelBounds()" in text
    assert "function setViewerCameraPose(" in text
    assert "viewer-viewport-command-state.js" in text
    assert "buildViewerRenderModeButtonStates" in text
    assert "getViewerLegendDisplayForRenderMode" in text
    assert 'id="midas33-view-toolbar"' in text
    assert "viewer-midas33-view-presets.js" in text
    assert "setMidas33ViewPreset('review')" in text
    assert "buildMidas33CameraPoseFromBounds" in text
    assert "buildMidas33ViewButtonStates" in text
    assert "function setMidas33ViewPreset(" in text
    assert "function applyDefaultViewPreset()" in text
    assert "viewer-project-workspace.js" in text
    assert "viewer-explainability-model.js" in text
    assert "viewer-optimization-comparison-model.js" in text
    assert "viewer-report-export.js" in text
    assert "viewer-local-ops-state.js" in text
    assert 'id="project-workspace-section"' in text
    assert 'id="project-drawing-list"' in text
    assert 'id="project-workspace-query"' in text
    assert "setProjectWorkspaceSearch" in text
    assert 'id="explainability-panel"' in text
    assert 'id="viewer-report-export-panel"' in text
    assert "function exportWorkspaceHtmlReport()" in text
    assert "function exportWorkspaceAuditJsonl()" in text
    assert "buildOptimizationComparisonModel" in text
    assert "Export Audit" in text
    assert "structure-viewer-project-manifest.v1" in (
        ROOT / "src" / "structure-viewer" / "viewer-project-workspace.js"
    ).read_text(encoding="utf-8")
    assert "window.getViewerModelBounds=getViewerModelBounds;" in text
    assert "window.setViewerCameraPose=setViewerCameraPose;" in text
    assert "window.setMidas33ViewPreset=setMidas33ViewPreset;" in text


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
