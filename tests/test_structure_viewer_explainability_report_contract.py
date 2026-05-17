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


def test_explainability_and_report_export_distinguish_exact_proxy_missing_evidence() -> None:
    payload = _run_node(
        """
import {buildViewerExplainabilityModel} from './src/structure-viewer/viewer-explainability-model.js';
import {buildOptimizationComparisonModel} from './src/structure-viewer/viewer-optimization-comparison-model.js';
import {
  buildStructureViewerReportExport,
  buildStructureViewerReportFilename,
} from './src/structure-viewer/viewer-report-export.js';
import {buildDrawingReviewModel} from './src/structure-viewer/viewer-drawing-review-model.js';
import {buildMemberComparisonModel} from './src/structure-viewer/viewer-member-comparison-model.js';

const workspace = {
  projectId: 'midas33_release',
  projectTitle: 'MIDAS33 Release Models',
  drawingId: 'midas33_optimized',
  drawingTitle: 'MIDAS33 Optimized Roundtrip',
  variant: 'compare',
  drawing: {
    commercial_review_status: 'ready',
    source_family: 'midas_mgt',
    baseline_ref: 'midas33',
    optimized_ref: 'midas33_optimized',
    artifact_path: 'midas_generator_33.optimized.roundtrip.json',
    quality_flags: [],
    optimization_summary: {
      baseline_member_count: 11334,
      optimized_member_count: 2242,
      evidence_level: 'repo exact roundtrip release counts',
      risk_delta_label: 'D/C movement requires engineer-in-loop review',
      source: 'midas33_optimized_roundtrip.json',
      artifact_count_source: 'midas33_optimized_roundtrip.json',
    },
  },
};
const element = {
  id: 911,
  member_id: '911',
  type: 'column',
  section: 'SRC-900',
  material: 'C40',
  dcr: 0.93,
  before_section: 'SRC-1000',
  after_section: 'SRC-900',
  weight_delta_pct: -7.25,
  governing_constraint: 'story drift limit',
};
const explanation = buildViewerExplainabilityModel({
  data: {nodes: [{id: 1}], elements: [element], meta: {name: 'fixture'}},
  element,
  selection: {memberId: '911', loadCase: 'KDS_ULS_1'},
  workspace,
});
const missing = buildViewerExplainabilityModel({
  data: {},
  element: {id: 'M-1', dcr: 1.05},
  selection: {},
  workspace: {...workspace, drawing: {...workspace.drawing, quality_flags: ['load_model_missing'], commercial_review_status: 'needs_review'}},
});
const comparison = buildOptimizationComparisonModel({
  workspace,
  data: {elements: [element], meta: {name: 'fixture'}},
});
const drawingReview = buildDrawingReviewModel(workspace.drawing);
const memberComparison = buildMemberComparisonModel({
  workspace,
  data: {elements: [element], meta: {name: 'fixture'}},
  filter: 'changed',
});
const report = buildStructureViewerReportExport({
  workspace,
  data: {nodes: [{id: 1}], elements: [element], meta: {name: 'fixture'}},
  selectedElement: element,
  explainability: explanation,
  comparison,
  drawingReview,
  memberComparison,
  screenshotDataUrl: 'data:image/png;base64,iVBORw0KGgo=',
  reviewNote: 'Field note: verify changed section with engineer.',
  generatedAt: '2026-05-17T00:00:00Z',
});
console.log(JSON.stringify({
  title: explanation.title,
  usage: explanation.rows.find((row) => row.label === 'Usage'),
  delta: explanation.rows.find((row) => row.label === 'Optimization delta'),
  cost: explanation.rows.find((row) => row.label === 'Weight / cost'),
  rationale: explanation.rows.find((row) => row.label === 'Optimization rationale'),
  comparisonHeadline: comparison.headline,
  comparisonMembers: comparison.rows.find((row) => row.label === 'Members'),
  comparisonVerification: comparison.verification,
  missingDelta: missing.rows.find((row) => row.label === 'Optimization delta'),
  filenameWithoutVariant: buildStructureViewerReportFilename({projectId: workspace.projectId, drawingId: workspace.drawingId}),
  filename: buildStructureViewerReportFilename({projectId: workspace.projectId, drawingId: workspace.drawingId, variant: workspace.variant}),
  reportFilename: report.filename,
  reportHasChecklist: report.html.includes('Engineer-in-loop Checklist'),
  reportHasKoreanChecklist: report.html.includes('단면 변경 확인'),
  reportHasDrawingReview: report.html.includes('Drawing Review') && report.html.includes('상용 검토 가능'),
  reportHasMemberComparison: report.html.includes('Before / After Member Comparison') && report.html.includes('SRC-1000 -&gt; SRC-900'),
  reportHasComparisonHighlightCount: report.html.includes('3D highlight exact members=1'),
  reportHasScreenshotMarker: report.html.includes('viewer screenshot marker'),
  reportHasReviewNote: report.html.includes('Field note: verify changed section with engineer.'),
  reportHasOptimizationSummary: report.html.includes('Optimization Summary'),
  reportHasComparisonHeadline: report.html.includes('Members 11,334 -&gt; 2,242 (-80.2%)'),
  reportHasCountVerification: report.html.includes('Artifact count verified'),
  reportHasCountSource: report.html.includes('midas33_optimized_roundtrip.json'),
  reportHasMember: report.html.includes('911'),
}));
"""
    )

    assert payload["title"] == "Member 911"
    assert payload["usage"]["evidence"] == "derived proxy"
    assert payload["delta"]["value"] == "SRC-1000 -> SRC-900"
    assert payload["delta"]["evidence"] == "exact source"
    assert payload["cost"]["value"] == "weight delta -7.25%"
    assert payload["rationale"]["value"] == "governed by story drift limit"
    assert payload["rationale"]["evidence"] == "exact source"
    assert payload["comparisonHeadline"] == "Members 11,334 -> 2,242 (-80.2%)"
    assert payload["comparisonMembers"]["delta"] == "-9,092 (-80.2%)"
    assert payload["comparisonVerification"]["status"] == "verified"
    assert payload["missingDelta"]["evidence"] == "missing evidence"
    assert payload["filenameWithoutVariant"] == "structure_viewer_report_midas33_release_midas33_optimized.html"
    assert payload["filename"] == "structure_viewer_report_midas33_release_midas33_optimized_compare.html"
    assert payload["reportFilename"] == payload["filename"]
    assert payload["reportHasChecklist"] is True
    assert payload["reportHasKoreanChecklist"] is True
    assert payload["reportHasDrawingReview"] is True
    assert payload["reportHasMemberComparison"] is True
    assert payload["reportHasComparisonHighlightCount"] is True
    assert payload["reportHasScreenshotMarker"] is True
    assert payload["reportHasReviewNote"] is True
    assert payload["reportHasOptimizationSummary"] is True
    assert payload["reportHasComparisonHeadline"] is True
    assert payload["reportHasCountVerification"] is True
    assert payload["reportHasCountSource"] is True
    assert payload["reportHasMember"] is True
