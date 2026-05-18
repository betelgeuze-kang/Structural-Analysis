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


def test_project_workspace_manifest_normalizes_quality_and_legacy_preset() -> None:
    payload = _run_node(
        """
import {
  DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST,
  buildProjectBrowserModel,
  buildDrawingArtifactCountVerification,
  buildProjectManifestFromRows,
  buildReleaseVisualizationDrawings,
  buildRuntimeProjectManifest,
  buildWorkspaceUrl,
  normalizeProjectManifest,
  normalizeProjectManifestRow,
  resolveWorkspaceStateFromSearch,
  summarizeProjectManifest,
  validateDrawingQuality,
} from './src/structure-viewer/viewer-project-workspace.js';
import {buildDrawingReviewModel, classifyDrawingQualityFlag} from './src/structure-viewer/viewer-drawing-review-model.js';

const manifest = normalizeProjectManifest(DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST);
const legacyState = resolveWorkspaceStateFromSearch('?preset=midas33_optimized', {
  manifest,
  legacyPreset: 'midas33_optimized',
});
const standardState = resolveWorkspaceStateFromSearch('?project=midas33_release&drawing=midas33_optimized&variant=baseline', {
  manifest,
});
const resumeState = resolveWorkspaceStateFromSearch('?project=midas33_release&drawing=midas33_optimized&variant=compare&comparison_filter=reduced&member=911', {
  manifest,
});
const browser = buildProjectBrowserModel(manifest, {...standardState, filter: 'all'});
const midasDrawing = browser.drawings.find((drawing) => drawing.drawingId === 'midas33_optimized');
const prRecheckDrawing = browser.drawings.find((drawing) => drawing.drawingId === 'midas33_pr_recheck');
const countSourceRow = browser.activeEvidence.rows.find((row) => row.label === 'Count source');
const optimizedVariantEvidence = browser.activeEvidence.variants.find((variant) => variant.variant === 'optimized');
const midasVerification = buildDrawingArtifactCountVerification(
  manifest.projects[0].drawings.find((drawing) => drawing.drawing_id === 'midas33_optimized'),
);
const midasManifestDrawing = manifest.projects[0].drawings.find((drawing) => drawing.drawing_id === 'midas33_optimized');
const missingVerification = buildDrawingArtifactCountVerification({
  drawing_id: 'pending',
  source_family: 'ifc',
});
const releaseProject = manifest.projects.find((project) => project.project_id === 'release_visualization');
const releaseBrowser = buildProjectBrowserModel(manifest, {
  projectId: 'release_visualization',
  drawingId: 'opstool_606m_megatall_model_00020',
  variant: 'compare',
  drawingQuery: '00020',
});
const releaseDrawing = releaseProject.drawings.find((drawing) => drawing.drawing_id === 'opstool_606m_megatall_model_00020');
const releaseCompare = releaseDrawing.variants.find((variant) => variant.variant === 'compare');
const releaseOptimized = releaseDrawing.variants.find((variant) => variant.variant === 'optimized');
const releaseSpecs = buildReleaseVisualizationDrawings();
const summary = summarizeProjectManifest(manifest);
const importedManifest = buildProjectManifestFromRows([
  {
    drawing_id: 'midas_csv_ok',
    drawing_title: 'MIDAS CSV OK',
    source_family: 'midas_csv',
    artifact_path: 'open_data/midas.csv',
    member_count: 12,
    node_count: 20,
    element_count: 12,
    bounds: {x: 18, y: 12, z: 9},
    evidence_level: 'fixture exact',
  },
  {
    drawing_id: 'ifc_axis_review',
    source_family: 'ifc',
    artifact_path: 'models/ifc_axis.ifc',
    load_model_status: 'source_ifc_load_model_missing',
    geometry_summary: {
      node_count: 10,
      element_count: 8,
      member_count: 8,
      bounds: {x: 12, y: 2, z: 3000},
      up_axis: 'y',
      axis_flipped: true,
    },
  },
  {
    drawing_id: 'json_empty',
    source_family: 'json',
    geometry_summary: {node_count: 0, element_count: 0, member_count: 0, bounds: {x: 0, y: 0, z: 0}},
  },
], {project_id: 'fixture_project', project_title: 'Fixture Project'});
const importedRows = importedManifest.projects[0].drawings;
const directIfcRow = normalizeProjectManifestRow({
  drawing_id: 'direct_ifc',
  source_family: 'ifc',
  artifact_path: 'models/direct.ifc',
  load_model_status: 'missing',
  bounds_x: 100,
  bounds_y: 1,
  bounds_z: 1,
  member_count: 3,
  node_count: 4,
  element_count: 3,
  up_axis: 'x',
});
const blocked = validateDrawingQuality({
  source_family: 'ifc',
  load_model_status: 'source_ifc_load_model_missing',
  geometry_summary: {node_count: 0, element_count: 0, member_count: 0, bounds: {x: 0, y: 0, z: 0}},
  quality_flags: [],
});
const review = validateDrawingQuality({
  artifact_path: 'model.ifc',
  source_family: 'ifc',
  load_model_status: 'source_ifc_load_model_missing',
  geometry_summary: {node_count: 10, element_count: 9, member_count: 9, bounds: {x: 10, y: 2, z: 3000}},
  quality_flags: [],
});
const url = buildWorkspaceUrl('http://127.0.0.1/src/structure-viewer/index.html?member=911', {
  ...standardState,
  manifest,
}, {variant: 'optimized', comparisonFilter: 'reduced', memberId: '911'});
const runtimeManifest = buildRuntimeProjectManifest(manifest, {
  fallbackWorkspace: standardState,
  ingestPreview: {
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: 'csv',
    row_count: 1,
    drawing_count: 1,
    commercial_tool_profiles: {etabs: 1},
    crosswalk_candidate_count: 1,
    blocked_issues: [],
    manifest: buildProjectManifestFromRows([{
      drawing_id: 'csv_review',
      drawing_title: 'CSV Review',
      source_family: 'csv',
      artifact_path: 'viewer-evidence.csv',
      member_count: 4,
      node_count: 6,
      element_count: 4,
      member_id: '911',
      source_tool: 'ETABS 22',
      frame_section: 'W14X90',
      receipt_path: 'receipt-911.json',
      status: 'verified',
    }], {project_id: 'csv_upload', project_title: 'CSV Upload'}),
  },
});
const runtimeBrowser = buildProjectBrowserModel(runtimeManifest, {
  projectId: 'evidence_ingest_preview',
  drawingId: 'csv_review',
  variant: 'optimized',
});
const runtimeState = resolveWorkspaceStateFromSearch('?project=evidence_ingest_preview&drawing=csv_review&variant=optimized', {
  manifest: runtimeManifest,
});
const runtimeUrl = buildWorkspaceUrl('http://127.0.0.1/src/structure-viewer/index.html', {
  ...runtimeState,
  manifest: runtimeManifest,
}, {});

console.log(JSON.stringify({
  schema: manifest.schema_version,
  legacy: {
    projectId: legacyState.projectId,
    drawingId: legacyState.drawingId,
    variant: legacyState.variant,
    preset: legacyState.viewerPreset,
  },
  standardPreset: standardState.viewerPreset,
  resumeState: {
    projectId: resumeState.projectId,
    drawingId: resumeState.drawingId,
    variant: resumeState.variant,
    comparisonFilter: resumeState.comparisonFilter,
  },
  activeProject: browser.activeProject.project_id,
  drawingCount: browser.drawings.length,
  midasComparisonLabel: midasDrawing.comparisonLabel,
  midasReviewLabel: midasDrawing.reviewLabel,
  midasReviewVerdict: midasDrawing.reviewVerdict,
  midasIssueCountLabel: midasDrawing.issueCountLabel,
  midasVerificationLabel: midasDrawing.verificationLabel,
  midasVerificationShortLabel: midasDrawing.verificationShortLabel,
  midasVerificationTone: midasDrawing.verificationTone,
  prRecheckVerificationLabel: prRecheckDrawing.verificationLabel,
  prRecheckVerificationTone: prRecheckDrawing.verificationTone,
  activeEvidenceTitle: browser.activeEvidence.title,
  activeEvidenceStatusTone: browser.activeEvidence.statusTone,
  activeEvidenceReviewLabel: browser.activeEvidence.review.label,
  activeEvidenceIssueCount: browser.activeEvidence.review.issueCount,
  activeEvidenceVerification: browser.activeEvidence.verification,
  countSourceRow,
  solverReceiptRow: browser.activeEvidence.rows.find((row) => row.label === 'Solver receipts'),
  lineageRow: browser.activeEvidence.rows.find((row) => row.label === 'Lineage'),
  ingestSummaryRow: browser.activeEvidence.rows.find((row) => row.label === 'Ingest summary'),
  optimizedVariantEvidence,
  midasEvidenceHub: {
    solverReceipts: midasManifestDrawing.solver_receipts,
    lineage: midasManifestDrawing.lineage,
    ingestSummary: midasManifestDrawing.ingest_summary,
  },
  releaseVerificationLabel: releaseBrowser.drawings[0].verificationLabel,
  midasVerification,
  missingVerification,
  releaseDrawingCount: releaseProject.drawings.length,
  releaseFilteredCount: releaseBrowser.drawings.length,
  releaseComparePath: releaseCompare.artifact_path,
  releaseOptimizedPath: releaseOptimized.artifact_path,
  releaseSpecCount: releaseSpecs.length,
  summary,
  importedStatuses: importedRows.map((drawing) => ({
    id: drawing.drawing_id,
    status: drawing.commercial_review_status,
    flags: drawing.quality_flags,
    review: buildDrawingReviewModel(drawing),
  })),
  severity: {
    empty: classifyDrawingQualityFlag('empty_geometry'),
    load: classifyDrawingQualityFlag('load_model_missing'),
    receipt: classifyDrawingQualityFlag('external_receipt_pending'),
  },
  directIfcRow: {
    status: directIfcRow.commercial_review_status,
    flags: directIfcRow.quality_flags,
    review: buildDrawingReviewModel(directIfcRow),
  },
  blocked,
  review,
  url,
  runtime: {
    projectCount: runtimeManifest.projects.length,
    projectTitle: runtimeBrowser.activeProject.project_title,
    drawingTitle: runtimeBrowser.activeDrawing.drawing_title,
    evidenceRows: runtimeBrowser.activeEvidence.rows,
    toolProfileRow: runtimeBrowser.activeEvidence.rows.find((row) => row.label === 'Tool profiles'),
    crosswalkCandidateRow: runtimeBrowser.activeEvidence.rows.find((row) => row.label === 'Crosswalk candidates'),
    variant: runtimeBrowser.activeVariant,
    state: runtimeState,
    url: runtimeUrl,
  },
}));
"""
    )

    assert payload["schema"] == "structure-viewer-project-manifest.v1"
    assert payload["legacy"] == {
        "projectId": "midas33_release",
        "drawingId": "midas33_optimized",
        "variant": "optimized",
        "preset": "midas33_optimized",
    }
    assert payload["standardPreset"] == "midas33"
    assert payload["resumeState"] == {
        "projectId": "midas33_release",
        "drawingId": "midas33_optimized",
        "variant": "compare",
        "comparisonFilter": "reduced",
    }
    assert payload["activeProject"] == "midas33_release"
    assert payload["drawingCount"] >= 1
    assert payload["midasComparisonLabel"] == "members 11,334 -> 2,242 (-80.2%)"
    assert payload["midasReviewLabel"] == "상용 검토 가능"
    assert payload["midasReviewVerdict"] == "ready"
    assert payload["midasIssueCountLabel"] == "0 issues"
    assert payload["midasVerificationLabel"] == "Artifact count verified"
    assert payload["midasVerificationShortLabel"] == "verified counts"
    assert payload["midasVerificationTone"] == "success"
    assert payload["prRecheckVerificationLabel"] == "Manifest comparison only"
    assert payload["prRecheckVerificationTone"] == "warn"
    assert payload["activeEvidenceTitle"] == "MIDAS33 Optimized Roundtrip"
    assert payload["activeEvidenceStatusTone"] == "success"
    assert payload["activeEvidenceReviewLabel"] == "상용 검토 가능"
    assert payload["activeEvidenceIssueCount"] == 0
    assert payload["activeEvidenceVerification"]["status"] == "verified"
    assert payload["countSourceRow"]["value"].endswith("midas33_optimized_roundtrip.json")
    assert payload["solverReceiptRow"]["value"] == "1 receipt slots"
    assert payload["lineageRow"]["value"] == "3 stages"
    assert payload["ingestSummaryRow"]["value"] == "viewer-first evidence hub ready"
    assert payload["optimizedVariantEvidence"]["active"] is False
    assert payload["optimizedVariantEvidence"]["artifactPath"].endswith("midas_generator_33.optimized.roundtrip.json")
    assert payload["midasEvidenceHub"]["solverReceipts"][0]["member_id"] == "911"
    assert payload["midasEvidenceHub"]["lineage"][0]["stage"] == "source_model"
    assert payload["midasEvidenceHub"]["ingestSummary"]["receipt_slots"] == 1
    assert payload["releaseVerificationLabel"] == "Artifact count verified"
    assert payload["midasVerification"]["source"].endswith("midas33_optimized_roundtrip.json")
    assert payload["missingVerification"]["status"] == "missing"
    assert payload["releaseDrawingCount"] >= 8
    assert payload["releaseFilteredCount"] == 1
    assert payload["releaseComparePath"].endswith("opstool_606m_megatall_model_00020_ai_compare.json")
    assert payload["releaseOptimizedPath"].endswith("opstool_606m_megatall_model_00020_after_only.json")
    assert payload["releaseSpecCount"] == payload["releaseDrawingCount"]
    assert payload["summary"]["projectCount"] >= 3
    assert payload["summary"]["drawingCount"] >= 11
    assert payload["summary"]["variantCount"] >= 30
    assert payload["importedStatuses"][0]["status"] == "ready"
    assert payload["importedStatuses"][0]["review"]["verdict"] == "ready"
    assert payload["importedStatuses"][1]["status"] == "needs_review"
    assert payload["importedStatuses"][1]["review"]["verdict"] == "limited_review"
    assert "axis_flipped_review" in payload["importedStatuses"][1]["flags"]
    assert "load_model_missing" in payload["importedStatuses"][1]["flags"]
    assert payload["importedStatuses"][2]["status"] == "blocked"
    assert payload["importedStatuses"][2]["review"]["verdict"] == "blocked"
    assert "provenance_missing" in payload["importedStatuses"][2]["flags"]
    assert payload["severity"] == {"empty": "critical", "load": "warning", "receipt": "info"}
    assert payload["directIfcRow"]["status"] == "needs_review"
    assert payload["directIfcRow"]["review"]["label"] == "제한적 검토"
    assert "aspect_ratio_outlier" in payload["directIfcRow"]["flags"]
    assert payload["blocked"]["commercial_review_status"] == "blocked"
    assert "empty_geometry" in payload["blocked"]["quality_flags"]
    assert payload["review"]["commercial_review_status"] == "needs_review"
    assert "load_model_missing" in payload["review"]["quality_flags"]
    assert "variant=optimized" in payload["url"]
    assert "preset=midas33_optimized" in payload["url"]
    assert "comparison_filter=reduced" in payload["url"]
    assert "member=911" in payload["url"]
    assert payload["runtime"]["projectCount"] == payload["summary"]["projectCount"] + 1
    assert payload["runtime"]["projectTitle"] == "Evidence Ingest Preview (CSV)"
    assert payload["runtime"]["drawingTitle"] == "CSV Review"
    assert payload["runtime"]["state"]["projectId"] == "evidence_ingest_preview"
    assert payload["runtime"]["state"]["viewerPreset"] == "midas33"
    assert payload["runtime"]["variant"]["viewer_preset"] == "midas33"
    assert "project=evidence_ingest_preview" in payload["runtime"]["url"]
    assert "preset=midas33" in payload["runtime"]["url"]
    assert any(row["label"] == "Ingest summary" and row["value"] == "local evidence ingest preview" for row in payload["runtime"]["evidenceRows"])
    assert payload["runtime"]["toolProfileRow"]["value"] == "etabs:1"
    assert payload["runtime"]["crosswalkCandidateRow"]["value"] == "1"
