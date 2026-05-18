from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lineage_drilldown_links_source_analysis_optimization_report_and_ingest() -> None:
    script = """
import {buildViewerLineageDrilldownModel} from './src/structure-viewer/viewer-lineage-drilldown-model.js';

const workspace = {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  variant: 'compare',
  variantRow: {label: 'Compare', artifact_path: 'optimized.json'},
  drawing: {
    source_family: 'midas_mgt',
    artifact_path: 'source.json',
    optimized_ref: 'optimized-ref',
    optimization_summary: {
      baseline_member_count: 100,
      optimized_member_count: 82,
      source: 'summary.json',
    },
    provenance: {source_path: 'source-model.mgt'},
    lineage: [
      {stage: 'source_model', label: 'MIDAS source', path: 'source-model.mgt'},
      {stage: 'optimized_model', label: 'optimized roundtrip', path: 'optimized-model.json'},
      {stage: 'viewer_report', label: 'viewer report', path: 'release-report.json'},
    ],
  },
};
const element = {
  member_id: 'M-1',
  before_section: 'H-500',
  after_section: 'H-450',
};
const receipt = {
  status: 'verified',
  label: 'solver receipt verified',
  tone: 'success',
  source_tool: 'MIDAS Gen',
  load_combo: 'ULS-1',
  receipt_path: 'receipt/M-1.json',
  evidence_level: 'exact solver receipt',
};
const reviewTask = {
  label: '승인',
  status: 'approved',
  tone: 'success',
  hasTask: true,
  updatedAt: '2026-05-17T00:00:00Z',
};
const ingestPreview = {
  source_type: 'json',
  renderable_payload_available: true,
  renderable_payload_kind: 'direct_model',
  renderable_node_count: 2,
  renderable_element_count: 1,
  renderable_segment_count: 0,
};
const exact = buildViewerLineageDrilldownModel({workspace, element, solverReceipt: receipt, reviewTask, ingestPreview});
const missing = buildViewerLineageDrilldownModel({
  workspace: {projectId: 'p', drawingId: 'd', variant: 'optimized', drawing: {}},
  element: {member_id: 'M-2'},
});
console.log(JSON.stringify({
  exact,
  source: exact.rows.find((row) => row.stage === 'source_model'),
  analysis: exact.rows.find((row) => row.stage === 'analysis_result'),
  delta: exact.rows.find((row) => row.stage === 'optimization_delta'),
  report: exact.rows.find((row) => row.stage === 'report_package'),
  ingest: exact.rows.find((row) => row.stage === 'evidence_ingest'),
  missing,
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

    assert payload["exact"]["schema_version"] == "structure-viewer-lineage-drilldown.v1"
    assert payload["exact"]["memberId"] == "M-1"
    assert payload["exact"]["status"] == "ready"
    assert payload["source"]["value"] == "source-model.mgt"
    assert payload["source"]["evidence"] == "exact source"
    assert payload["analysis"]["value"] == "MIDAS Gen · ULS-1 · verified"
    assert payload["analysis"]["evidence"] == "exact source"
    assert payload["delta"]["value"] == "H-500 -> H-450"
    assert payload["delta"]["evidence"] == "exact source"
    assert payload["report"]["value"] == "release-report.json"
    assert payload["ingest"]["value"] == "direct_model · elements=1 · segments=0"
    assert payload["ingest"]["evidence"] == "local ingest payload"
    assert payload["missing"]["status"] == "needs_review"
