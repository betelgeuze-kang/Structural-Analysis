from pathlib import Path


def test_panel_zone_html_prefers_local_payload_then_repo_artifacts() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "./panel_zone.data.js" in text
    assert "__PANEL_ZONE_PAYLOAD__" in text
    assert "panel-zone-artifact-data" in text
    assert "../../implementation/phase1/panel_zone_clash_report.json" in text
    assert "../../implementation/phase1/panel_zone_clash_artifact.json" in text
    assert "../../implementation/phase1/panel_zone_clash_verification_3d.json" in text
    assert "../../implementation/phase1/panel_zone_joint_geometry_3d.json" in text
    assert "../../implementation/phase1/panel_zone_rebar_anchorage_3d.json" in text
    assert "../../implementation/phase1/panel_zone_solver_verified_inbox_status.json" in text


def test_panel_zone_html_surfaces_artifact_metrics() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    for element_id in [
        "title",
        "subtitle",
        "status-tag",
        "source-pill",
        "verification-pill",
        "fallback-pill",
        "contract-pill",
        "provenance-source",
        "provenance-report",
        "provenance-timestamp",
        "provenance-selection",
        "provenance-mode",
        "provenance-verification",
        "provenance-coverage",
        "provenance-boundary",
        "provenance-fallback",
        "provenance-input",
        "provenance-group",
        "provenance-section",
        "provenance-clearance",
        "copy-deep-link",
        "export-png",
        "copy-deep-link-status",
        "beam-length",
        "section-size",
        "anchorage",
        "violation-ratio",
        "clearance",
        "clash-pass",
    ]:
        assert f'id="{element_id}"' in text


def test_panel_zone_html_syncs_current_selection_query_and_copy_link() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "buildSelectionQueryUrl" in text
    assert "syncSelectionQuery" in text
    assert "panel_zone_object_id" in text
    assert "panel_zone_object_kind" in text
    assert "panelZoneObjectId" in text
    assert "panelZoneObjectKind" in text
    assert "buildObjectSelection(" in text
    assert "updateSelectionHandoff(" in text
    assert "buildPanelZoneRowLookup(" in text
    assert "buildPanelZoneLookupCandidates(" in text
    assert "scorePanelZoneRowLookupEntry(" in text
    assert "buildPanelZoneContextFallbackUrl(" in text
    assert "buildPanelZoneResultsExplorerUrlFromLookup(" in text
    assert "appendPanelZoneContextParams(" in text
    assert "mergePanelPayload(" in text
    assert "panel_zone_link_mode" in text
    assert "panel_zone_row_provenance_context" in text
    assert "panel_zone_row_provenance_exact" in text
    assert "member_set" in text
    assert "navigator.clipboard" in text
    assert "document.getElementById('copy-deep-link').addEventListener('click'" in text
    assert "Deep link copied" in text


def test_panel_zone_html_reuses_embedded_exact_row_jump_urls_and_alias_matches() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "buildRebasedPanelZoneResultsExplorerUrl(" in text
    assert "setSearchParamDefault(" in text
    assert "rowLookup.viewer_row_url" in text
    assert "rowLookup.viewer_slice_url" in text
    assert "baseline_focus_member_id" in text
    assert "['member_id',normalizeSelectionValue(entry.member_id)]" in text
    assert "['case_id',normalizeSelectionValue(entry.case_id)]" in text
    assert "lookup_match_key" in text
    assert "lookup_match_source" in text
    assert "resultsExplorerSummaryLabel" in text
    assert "resultsExplorerReviewMemberId" in text


def test_panel_zone_html_uses_repo_local_vendor_modules() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "./vendor/three.module.js" in text
    assert "./vendor/OrbitControls.js" in text
    assert "cdn.jsdelivr.net" not in text
    assert "preserveDrawingBuffer:true" in text
    assert "renderer.localClippingEnabled=true;" in text
    assert "function exportPanelZonePng()" in text


def test_panel_zone_html_supports_artifact_vector_geometry_layout() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "artifact_vector_coords" in text
    assert "extractPanelGeometryLayout(" in text
    assert "beam_axis_segment_m" in text
    assert "column_axis_segment_m" in text
    assert "column_rebar_segments_m" in text
    assert "clash_points_m" in text
    assert "points_m" in text
    assert "start_m" in text
    assert "end_m" in text
    assert "panel_zone_clash_verification_3d" in text
    assert "clearance_mm" in text
    assert "determinePanelSourceMode(" in text
    assert "buildPanelBoundaryLabel(" in text
    assert "panel_zone_external_validation_summary_line" in text
    assert "panel_zone_solver_verified_inbox_status_mode" in text
    assert "panel_zone_external_validation_provenance_summary_label" in text
    assert "panel_zone_external_validation_status_label" in text
    assert "panel_zone_external_validation_unattributed_validated_row_count" in text
    assert "unattributed_rows=" in text
    assert "makeOrientedBoxFromSegment(" in text
    assert "makeCylinderBetween(" in text


def test_panel_zone_html_adds_section_cut_and_finishing_quality_controls() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    for element_id in [
        "chk-section-cut",
        "section-cut-axis",
        "section-cut-offset",
        "section-cut-status",
        "reset-section-cut",
        "toggle-light-mode-button",
        "toggle-shortcuts-button",
        "shortcut-help",
    ]:
        assert f'id="{element_id}"' in text
    assert "function configureSectionCutRange(" in text
    assert "function applySectionCut(" in text
    assert "function toggleLightMode()" in text
    assert "function toggleShortcutHelp(" in text
    assert "@media print" in text


def test_panel_zone_html_keeps_explicit_stage_viewport_tool_and_insight_rails() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    for fragment in [
        'class="panel-command-topbar"',
        'class="viewer-tabbar"',
        'class="context-chip"',
        'id="panel-stage"',
        'class="panel-stage"',
        'aria-label="Panel zone 3D review stage"',
        'id="panel-viewport"',
        'class="panel-viewport"',
        'role="application"',
        'tabindex="0"',
        'class="panel-tool-rail"',
        'aria-label="Panel viewport quick tools"',
        'class="panel-insight-rail"',
        'aria-label="Panel zone insight rail"',
        'id="viewport-pick-status"',
        'id="viewport-selection-chip"',
        'id="stage-handoff-mode"',
    ]:
        assert fragment in text


def test_panel_zone_html_exposes_raycaster_hover_selection_and_shared_handoff_contract() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "raycaster=new THREE.Raycaster()" in text
    assert "userData" in text
    assert "pickableObjects" in text
    assert "registerPickable(" in text
    assert "pickable:true" in text
    assert "hoveredPickObject" in text
    assert "selectedPickObject" in text
    assert "selectionMarker" in text
    assert "setHoveredPickObject(" in text
    assert "setSelectedPickObject(" in text
    assert "updateSelectionHandoff(" in text
    assert "panel_zone_object_id" in text
    assert "panel_zone_object_kind" in text
    assert "panelZoneObjectId" in text
    assert "panelZoneObjectKind" in text
    assert "buildObjectSelection(" in text
    assert 'id="viewport-selection-chip"' in text
    assert 'id="stage-handoff-mode"' in text
    assert 'id="viewport-pick-status"' in text
    assert 'id="copy-deep-link"' in text
    assert 'id="review-row-link"' in text
    assert "panel-crosshair" in text
    assert "publishSharedSelection" in text
    assert "buildSelectionQueryUrl" in text
    assert "syncSelectionQuery" in text
    assert "panelViewport.addEventListener('pointermove',handleViewportPointerMove);" in text
    assert "panelViewport.addEventListener('pointerdown',handleViewportPointerDown);" in text
    assert "panelViewport.addEventListener('pointerup',handleViewportPointerUp);" in text
    assert "panelViewport.addEventListener('pointercancel',handleViewportPointerLeave);" in text
    assert "panelViewport.addEventListener('pointerleave',handleViewportPointerLeave);" in text
