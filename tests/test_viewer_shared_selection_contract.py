from pathlib import Path


def test_index_viewer_publishes_shared_selection_contract() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "structural-viewer-selection-v1" in text
    assert "publishSharedSelection" in text
    assert "BroadcastChannel" in text
    assert "window.addEventListener('storage'" in text
    assert "focus_member" in text
    assert "drawing_asset" in text
    assert "asset_ref" in text
    assert "member_set" in text
    assert "memberIds" in text
    assert 'id="review-row-link"' in text
    assert 'id="header-review-row-link"' in text
    assert 'id="copy-deep-link-button"' in text
    assert 'id="provenance-source-label"' in text
    assert "structural_optimization_viewer.html" in text


def test_charts_viewer_hydrates_and_publishes_shared_selection_contract() -> None:
    text = Path("src/structure-viewer/charts.html").read_text(encoding="utf-8")

    assert "structural-viewer-selection-v1" in text
    assert "publishSharedSelection" in text
    assert "BroadcastChannel" in text
    assert "member-select" in text
    assert "load_case" in text
    assert "member_set" in text
    assert "memberIds" in text
    assert 'id="copy-deep-link-button"' in text
    assert 'id="provenance-source-label"' in text
    assert 'data-tab-key="timeseries"' in text
    assert "window.addEventListener('storage'" in text
    assert 'id="review-row-link"' in text
    assert "structural_optimization_viewer.html" in text


def test_panel_zone_viewer_reads_shared_selection_contract() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "structural-viewer-selection-v1" in text
    assert "BroadcastChannel" in text
    assert "matchRowByMember" in text
    assert "panel_zone_object_id" in text
    assert "panel_zone_object_kind" in text
    assert "panelZoneObjectId" in text
    assert "panelZoneObjectKind" in text
    assert "focus_member" in text
    assert "load_case" in text
    assert "member_set" in text
    assert "memberIds" in text
    assert "combination" in text
    assert "buildObjectSelection(" in text
    assert "buildSelectionQueryUrl" in text
    assert "syncSelectionQuery" in text
    assert "window.addEventListener('storage'" in text
    assert 'id="review-row-link"' in text
    assert 'id="copy-deep-link"' in text
    assert 'id="provenance-selection"' in text
    assert "structural_optimization_viewer.html" in text


def test_panel_zone_viewer_keeps_stage_handoff_and_selection_hud_contract() -> None:
    text = Path("src/structure-viewer/panel_zone.html").read_text(encoding="utf-8")

    assert "readSharedSelection" in text
    assert "publishSharedSelection" in text
    assert "buildSelectionQueryUrl" in text
    assert "syncSelectionQuery" in text
    assert "buildSelectionLabel" in text
    assert "updateSelectionHandoff(" in text
    assert "panel_zone_object_id" in text
    assert "panel_zone_object_kind" in text
    assert "panelZoneObjectId" in text
    assert "panelZoneObjectKind" in text
    assert "buildObjectSelection(" in text
    assert "panel_zone_pick" in text
    assert 'id="viewport-selection-chip"' in text
    assert 'id="stage-handoff-mode"' in text
    assert 'id="viewport-pick-status"' in text
    assert 'id="copy-deep-link-status"' in text
    assert 'id="provenance-selection"' in text
    assert 'id="review-row-link"' in text
    assert "panel-crosshair" in text
    assert "source:'panel_zone'" in text
    assert any(fragment in text for fragment in ("member_set", "memberIds", "focus_member"))
    assert any(fragment in text for fragment in ("load_case", "combination"))


def test_optimization_history_viewer_reads_and_updates_shared_selection_contract() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    assert "structural-viewer-selection-v1" in text
    assert "publishSharedSelection" in text
    assert "BroadcastChannel" in text
    assert "syncSelectionQuery" in text
    assert "buildSelectionQueryUrl" in text
    assert 'id="row-provenance-link"' in text
    assert 'id="copy-deep-link"' in text
    assert 'id="provenance-selection"' in text
    assert "window.addEventListener(\"storage\"" in text
    assert "structural_optimization_viewer.html" in text
    assert "row_ref" in text
    assert "overlay_row_id" in text
    assert "results_card" in text
    assert "results_series_index" in text
    assert "viewerRowUrl" in text
    assert "overlay_member_id" in text
    assert "overlay_group_id" in text
