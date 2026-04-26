from implementation.phase1.generate_singlefile_panel_zone_viewer import (
    build_panel_zone_payload,
    generate_singlefile_panel_zone_html,
)


def test_generate_singlefile_panel_zone_html_inlines_payload_and_vendor_modules() -> None:
    payload = build_panel_zone_payload(
        clash_report={"run_id": "phase1-panel-zone-clash-readiness", "summary": {"max_detailing_violation_ratio": 0.22}},
        clash_artifact={"run_id": "phase1-panel-zone-clash-artifact", "artifacts": {"interference_rows_head": []}},
        clash_verification={"source_kind": "panel_zone_clash_verification_3d", "artifacts": {"source_rows_head": []}},
        joint_geometry={"source_kind": "panel_zone_joint_geometry_3d", "artifacts": {"source_rows_head": []}},
        anchorage={"source_kind": "panel_zone_rebar_anchorage_3d", "artifacts": {"source_rows_head": []}},
        inbox_status={"run_id": "phase1-panel-zone-solver-verified-inbox-status", "summary": {"panel_zone_solver_verified_inbox_status_mode": "empty_without_history"}},
        row_provenance_lookup={
            "member_lookup": {
                "26878": {
                    "baseline_focus_member_id": "26878",
                    "member_id": "C-TRN-001",
                    "case_id": "C-TRN-001",
                    "viewer_row_ref": "gLCB1::0::C-TRN-001::C-TRN-001",
                    "viewer_row_url": "file:///tmp/structural_optimization_viewer.html?source=row_provenance_csv&row=0&row_ref=gLCB1%3A%3A0%3A%3AC-TRN-001%3A%3AC-TRN-001&codecheck_filtered_row=0",
                    "viewer_slice_url": "file:///tmp/structural_optimization_viewer.html?source=row_provenance_csv&row_ref=gLCB1%3A%3A0%3A%3AC-TRN-001%3A%3AC-TRN-001",
                    "bridge_row_provenance_mode_label": "exact row-level provenance",
                    "bridge_row_provenance_summary_label": "rows=12 | combos=2 | clauses=3",
                }
            }
        },
    )
    html = generate_singlefile_panel_zone_html(payload)

    assert "./panel_zone.data.js" not in html
    assert "./design-theme.css" not in html
    assert "inlined from src/structure-viewer/design-theme.css" in html
    assert "window.__STRUCTURAL_SINGLEFILE__=true;" in html
    assert html.count("window.__STRUCTURAL_SINGLEFILE__=true;") == 1
    assert "IS_SINGLEFILE_VIEWER" in html
    assert "@import url(" not in html
    assert "fonts.googleapis" not in html
    assert "https://fonts" not in html
    assert 'body class="structural-surface panel-inspection-shell"' in html
    assert 'class="panel-command-topbar"' in html
    assert 'class="viewer-tabbar"' in html
    assert 'class="context-chip"' in html
    assert 'id="panel-stage"' in html
    assert 'id="panel-viewport"' in html
    assert 'class="panel-tool-rail"' in html
    assert 'class="panel-insight-rail"' in html
    assert 'class="panel-crosshair"' in html
    assert 'aria-label="Panel zone 3D review stage"' in html
    assert 'role="application"' in html
    assert 'tabindex="0"' in html
    assert 'Click structural members, clashes, and reinforcement to select them.' in html
    assert 'aria-label="Panel viewport quick tools"' in html
    assert 'aria-label="Panel zone insight rail"' in html
    assert 'id="viewport-selection-chip"' in html
    assert 'id="stage-handoff-mode"' in html
    assert 'id="viewport-pick-status"' in html
    assert 'id="copy-deep-link-status"' in html
    assert 'id="review-row-link"' in html
    assert "panel_zone_object_id" in html
    assert "panel_zone_object_kind" in html
    assert "panelZoneObjectId" in html
    assert "panelZoneObjectKind" in html
    assert "buildObjectSelection(" in html
    assert "updateSelectionHandoff(" in html
    assert 'id="embedded-panel-zone-payload"' in html
    assert '"viewer_family": "panel_zone_viewer"' in html
    assert '"clash_verification": {' in html
    assert '"inbox_status": {' in html
    assert '"row_provenance_lookup": {' in html
    assert '"viewer_row_url": "file:///tmp/structural_optimization_viewer.html?source=row_provenance_csv&row=0&row_ref=gLCB1%3A%3A0%3A%3AC-TRN-001%3A%3AC-TRN-001&codecheck_filtered_row=0"' in html
    assert '"viewer_slice_url": "file:///tmp/structural_optimization_viewer.html?source=row_provenance_csv&row_ref=gLCB1%3A%3A0%3A%3AC-TRN-001%3A%3AC-TRN-001"' in html
    assert '"bridge_row_provenance_summary_label": "rows=12 | combos=2 | clauses=3"' in html
    assert "data:text/javascript;base64," in html
    assert "./vendor/three.module.js" not in html
    assert "./vendor/OrbitControls.js" not in html
    assert 'type="importmap"' not in html
