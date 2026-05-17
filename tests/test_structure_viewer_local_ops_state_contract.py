from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_ops_state_keeps_recent_audit_jsonl_and_export_history() -> None:
    script = """
import {
  appendViewerAuditEvent,
  appendViewerExportHistory,
  buildViewerAuditJsonlExport,
  buildViewerProjectBundleExport,
  getViewerReviewNote,
  readViewerLocalOpsState,
  rememberViewerWorkspaceSelection,
  setViewerReviewNote,
  writeViewerLocalOpsState,
} from './src/structure-viewer/viewer-local-ops-state.js';
import {buildProjectRecentListHtml} from './src/structure-viewer/viewer-project-workspace-renderer.js';

const store = new Map();
const storageGet = (key) => store.get(key) || '';
const storageSet = (key, value) => store.set(key, value);
let state = readViewerLocalOpsState({storageGet});
state = rememberViewerWorkspaceSelection(state, {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  variant: 'optimized',
  memberId: '911',
  filter: 'changed',
  label: 'MIDAS33',
});
state = appendViewerAuditEvent(state, {
  type: 'member_selected',
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  variant: 'optimized',
  memberId: '911',
  filter: 'changed',
  at: '2026-05-17T00:00:00Z',
});
state = setViewerReviewNote(state, {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  memberId: '911',
  note: 'verify DCR after section change',
  updatedAt: '2026-05-17T00:00:30Z',
});
state = appendViewerExportHistory(state, {
  filename: 'structure_viewer_report_midas33_release_midas33_optimized_optimized.html',
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  variant: 'optimized',
  at: '2026-05-17T00:01:00Z',
});
writeViewerLocalOpsState(state, {storageSet});
const reread = readViewerLocalOpsState({storageGet});
const auditExport = buildViewerAuditJsonlExport(reread, {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  generatedAt: '2026-05-17T00:02:00Z',
});
const bundleExport = buildViewerProjectBundleExport(reread, {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  variant: 'optimized',
  manifest: {schema_version: 'structure-viewer-project-manifest.v1'},
  generatedAt: '2026-05-17T00:03:00Z',
});
console.log(JSON.stringify({
  recent: reread.recentSelections[0],
  auditLine: JSON.parse(reread.auditEventsJsonl.split('\\n')[0]),
  exportRow: reread.exportHistory[0],
  note: getViewerReviewNote(reread, {
    projectId: 'midas33_release',
    drawingId: 'midas33_optimized',
    memberId: '911',
  }),
  auditExport,
  recentHtml: buildProjectRecentListHtml(reread.recentSelections),
  bundleExport: {
    filename: bundleExport.filename,
    payload: JSON.parse(bundleExport.json),
  },
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["recent"]["drawingId"] == "midas33_optimized"
    assert payload["recent"]["memberId"] == "911"
    assert payload["recent"]["filter"] == "changed"
    assert payload["auditLine"]["type"] == "member_selected"
    assert payload["auditLine"]["memberId"] == "911"
    assert payload["auditLine"]["filter"] == "changed"
    assert payload["exportRow"]["filename"] == "structure_viewer_report_midas33_release_midas33_optimized_optimized.html"
    assert payload["exportRow"]["variant"] == "optimized"
    assert payload["note"] == "verify DCR after section change"
    assert payload["auditExport"]["filename"] == "structure_viewer_audit_midas33_release_midas33_optimized.jsonl"
    assert payload["auditExport"]["eventCount"] == 1
    assert payload["auditExport"]["jsonl"].endswith("\n")
    assert 'data-project-recent-member="911"' in payload["recentHtml"]
    assert 'data-project-recent-comparison-filter="changed"' in payload["recentHtml"]
    assert "member 911" in payload["recentHtml"]
    assert payload["bundleExport"]["filename"] == "structure_viewer_bundle_midas33_release_midas33_optimized.json"
    assert payload["bundleExport"]["payload"]["schema_version"] == "structure-viewer-project-bundle.v1"
    assert payload["bundleExport"]["payload"]["local_state"]["reviewNotes"]
