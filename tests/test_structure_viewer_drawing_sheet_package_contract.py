from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_drawing_sheet_package_links_revision_callout_and_deep_link_to_report() -> None:
    payload = _run_node(
        """
import {
  buildDrawingSheetPackage,
  buildDrawingSheetPackageReportRows,
} from './src/structure-viewer/viewer-drawing-sheet-package-model.js';
import {buildStructureViewerReportExport} from './src/structure-viewer/viewer-report-export.js';
import {buildReportExportPanelHtml} from './src/structure-viewer/viewer-report-panel-renderer.js';
import {buildDrawingHandoffPanelHtml} from './src/structure-viewer/viewer-drawing-handoff-panel-renderer.js';

const workspace = {
  projectId: 'midas33_release',
  projectTitle: 'MIDAS33 Release Models',
  drawingId: 'midas33_optimized',
  drawingTitle: 'MIDAS33 Optimized Roundtrip',
  variant: 'compare',
  drawing: {
    revision_id: 'R7',
    commercial_review_status: 'ready',
    source_family: 'midas_mgt',
  },
};
const selectedElement = {
  id: 911,
  member_id: '911',
  section: 'SRC-900',
  callout_id: 'C-911',
  callout_label: 'Column 911 drift callout',
};
const deepLinkUrl = 'https://viewer.local/index.html?project=midas33_release&drawing=midas33_optimized&variant=compare&member=911';
const sheetPackageBase = buildDrawingSheetPackage({
  workspace,
  selectedElement,
  deepLinkUrl,
  generatedAt: '2026-05-19T00:00:00Z',
  sheetLinks: [
    {label: 'Plan', href: 'https://viewer.local/structural_svg/plan_z12.0.svg?member=911&revision=R7&callout=C-911'},
    {label: 'Elev-X', href: 'https://viewer.local/structural_svg/elevation_xz.svg?member=911&revision=R7&callout=C-911'},
  ],
});
const sheetPackage = {
  ...sheetPackageBase,
  rows: buildDrawingSheetPackageReportRows(sheetPackageBase),
};
const report = buildStructureViewerReportExport({
  workspace,
  data: {nodes: [], elements: [], meta: {name: 'fixture'}},
  selectedElement,
  drawingSheetPackage: sheetPackage,
  generatedAt: '2026-05-19T00:00:00Z',
});
const panel = buildReportExportPanelHtml({
  workspace,
  comparison: {headline: 'Members 11,334 -> 2,242 (-80.2%)', rows: []},
  drawingReview: {label: 'Review ready', tone: 'success'},
  drawingSheetPackage: sheetPackage,
});
const handoffPanel = buildDrawingHandoffPanelHtml({
  workspace,
  drawingReview: {label: 'Review ready', tone: 'success'},
  drawingSheetPackage: sheetPackage,
});
console.log(JSON.stringify({
  schema: sheetPackage.schema_version,
  status: sheetPackage.status,
  summary: sheetPackage.summary,
  sheetCount: sheetPackage.sheet_count,
  primarySheet: sheetPackage.primary_sheet_name,
  firstSheetDeepLinked: sheetPackage.sheets[0].deep_linked,
  calloutRow: sheetPackage.rows.find((row) => row.label === 'Callout'),
  reportHasSheetPackage: report.html.includes('Drawing Sheet Package'),
  reportHasRevision: report.html.includes('R7'),
  reportHasCallout: report.html.includes('C-911') && report.html.includes('Column 911 drift callout'),
  reportHasDeepLink: report.html.includes('Open viewer deep-link'),
  reportHasSheetEvidenceRows: report.html.includes('Sheet / Callout Evidence Rows') && report.html.includes('member callout deep-link'),
  panelHasPackage: panel.includes('Sheet Package') && panel.includes('Drawing sheet package: linked'),
  panelHasSvgLinks: panel.includes('Plan') && panel.includes('Elev-X'),
  handoffHasPanel: handoffPanel.includes('data-drawing-handoff-panel') && handoffPanel.includes('data-drawing-handoff-status="linked"'),
  handoffHasPreview: handoffPanel.includes('data-drawing-handoff-preview')
    && handoffPanel.includes('data-drawing-handoff-preview-sheet="plan_z12.0"')
    && handoffPanel.includes('data-drawing-handoff-preview-callout="C-911"')
    && handoffPanel.includes('data-drawing-handoff-preview-link')
    && handoffPanel.includes('data-drawing-handoff-preview-label')
    && handoffPanel.includes('data-drawing-handoff-preview-meta')
    && handoffPanel.includes('Sheet Preview'),
  handoffHasActiveSheetAction: handoffPanel.includes('data-drawing-handoff-active-sheet-open')
    && handoffPanel.includes('data-drawing-handoff-active-sheet-name="plan_z12.0"')
    && handoffPanel.includes('Open Active Sheet'),
  handoffHasRevisionCallout: handoffPanel.includes('R7') && handoffPanel.includes('C-911') && handoffPanel.includes('Column 911 drift callout'),
  handoffHasDeepLinkActions: handoffPanel.includes('Open Deep Link') && handoffPanel.includes('data-drawing-handoff-copy-link'),
  handoffHasSheetButtons: handoffPanel.includes('data-drawing-handoff-sheet="plan_z12.0"')
    && handoffPanel.includes('data-drawing-handoff-sheet="elevation_xz"')
    && handoffPanel.includes('data-drawing-handoff-sheet-href="https://viewer.local/structural_svg/plan_z12.0.svg?member=911&amp;revision=R7&amp;callout=C-911"')
    && handoffPanel.includes('aria-current="true"')
    && handoffPanel.includes('aria-disabled="false"'),
}));
"""
    )

    assert payload["schema"] == "structure-viewer-drawing-sheet-package.v1"
    assert payload["status"] == "linked"
    assert payload["summary"] == "Drawing sheet package: linked | sheets=2 | member=911 | revision=R7"
    assert payload["sheetCount"] == 2
    assert payload["primarySheet"] == "plan_z12.0"
    assert payload["firstSheetDeepLinked"] is True
    assert payload["calloutRow"]["value"] == "C-911"
    assert payload["reportHasSheetPackage"] is True
    assert payload["reportHasRevision"] is True
    assert payload["reportHasCallout"] is True
    assert payload["reportHasDeepLink"] is True
    assert payload["reportHasSheetEvidenceRows"] is True
    assert payload["panelHasPackage"] is True
    assert payload["panelHasSvgLinks"] is True
    assert payload["handoffHasPanel"] is True
    assert payload["handoffHasPreview"] is True
    assert payload["handoffHasActiveSheetAction"] is True
    assert payload["handoffHasRevisionCallout"] is True
    assert payload["handoffHasDeepLinkActions"] is True
    assert payload["handoffHasSheetButtons"] is True
