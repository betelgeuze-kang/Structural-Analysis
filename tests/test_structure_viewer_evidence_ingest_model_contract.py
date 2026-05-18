from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_csv_json_ifc_ingest_preview_normalizes_manifest_rows_and_receipts() -> None:
    script = """
import {
  buildEvidenceIngestPreview,
  buildEvidenceIngestPreviewFromText,
  extractRenderableEvidencePayloadFromText,
  normalizeEvidenceIngestRow,
} from './src/structure-viewer/viewer-evidence-ingest-model.js';

const normalized = normalizeEvidenceIngestRow({
  drawing_id: 'CSV Drawing',
  source_tool: 'MIDAS',
  member_id: '911',
  load_combo: 'ULS',
  dcr_before: 0.9,
  dcr_after: 0.86,
  receipt_path: 'receipts/911.json',
  source_tool: 'ETABS 22',
  story: 'L10',
  frame_section: 'W14X90',
  member_count: 8,
  node_count: 12,
  element_count: 8,
  artifact_path: 'model.csv',
}, {sourceType: 'csv', projectId: 'fixture'});
const directPreview = buildEvidenceIngestPreview({
  sourceType: 'json',
  projectId: 'fixture',
  rows: [
    normalized,
    {drawing_id: 'blocked', source_family: 'json', geometry_summary: {node_count: 0, element_count: 0, member_count: 0}},
  ],
});
const csvPreview = buildEvidenceIngestPreviewFromText(
  'drawing_id,artifact_path,member_count,node_count,element_count,member_id,receipt_path,status\\nCSV OK,model.csv,4,6,4,911,receipt.json,verified\\n',
  {sourceType: 'csv', projectId: 'csv_project'},
);
const jsonPreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify([{drawing_id: 'json_ok', artifact_path: 'model.json', member_count: 3, node_count: 4, element_count: 3}]),
  {sourceType: 'json', projectId: 'json_project'},
);
const renderablePayload = {
  drawing_id: 'renderable_json',
  artifact_path: 'renderable.json',
  member_count: 1,
  node_count: 2,
  element_count: 1,
  model: {
    nodes: [{id: 1, x: 0, y: 0, z: 0}, {id: 2, x: 1, y: 0, z: 0}],
    elements: [{id: 'R-1', member_id: 'R-1', node_ids: [1, 2], type: 'beam'}],
  },
};
const renderablePreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify(renderablePayload),
  {sourceType: 'json', projectId: 'renderable_project', artifactPath: 'renderable.json'},
);
const renderable = extractRenderableEvidencePayloadFromText(
  JSON.stringify(renderablePayload),
  {sourceType: 'json', sourceName: 'renderable.json'},
);
const ifcPreview = buildEvidenceIngestPreviewFromText(
  '#1=IFCBEAM();#2=IFCCOLUMN();#3=IFCCARTESIANPOINT();',
  {sourceType: 'ifc', projectId: 'ifc_project', artifactPath: 'model.ifc'},
);
console.log(JSON.stringify({
  normalized,
  directPreview: {
    rowCount: directPreview.row_count,
    drawingCount: directPreview.drawing_count,
    blockedIssues: directPreview.blocked_issues,
    firstDrawing: directPreview.manifest.projects[0].drawings[0],
    profiles: directPreview.commercial_tool_profiles,
    crosswalkCandidateCount: directPreview.crosswalk_candidate_count,
    firstRow: directPreview.normalized_rows[0],
  },
  csvStatus: csvPreview.manifest.projects[0].drawings[0].commercial_review_status,
  csvReceipt: csvPreview.manifest.projects[0].drawings[0].solver_receipts[0],
  jsonStatus: jsonPreview.manifest.projects[0].drawings[0].commercial_review_status,
  renderablePreview: {
    available: renderablePreview.renderable_payload_available,
    kind: renderablePreview.renderable_payload_kind,
    nodes: renderablePreview.renderable_node_count,
    elements: renderablePreview.renderable_element_count,
  },
  renderable,
  ifc: ifcPreview.manifest.projects[0].drawings[0],
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

    assert payload["normalized"]["source_family"] == "csv"
    assert payload["normalized"]["source_tool_profile"] == "etabs"
    assert payload["normalized"]["external_member_id"] == "911"
    assert payload["normalized"]["section"] == "W14X90"
    assert payload["normalized"]["story"] == "L10"
    assert payload["normalized"]["solver_receipts"][0]["status"] == "verified"
    assert payload["normalized"]["solver_receipts"][0]["source_tool_profile"] == "etabs"
    assert payload["directPreview"]["rowCount"] == 2
    assert payload["directPreview"]["drawingCount"] == 2
    assert payload["directPreview"]["blockedIssues"][0]["drawing_id"] == "blocked"
    assert payload["directPreview"]["firstDrawing"]["solver_receipts"][0]["member_id"] == "911"
    assert payload["directPreview"]["profiles"]["etabs"] == 1
    assert payload["directPreview"]["crosswalkCandidateCount"] == 1
    assert payload["directPreview"]["firstRow"]["source_tool"] == "ETABS 22"
    assert payload["csvStatus"] == "ready"
    assert payload["csvReceipt"]["member_id"] == "911"
    assert payload["csvReceipt"]["receipt_path"] == "receipt.json"
    assert payload["jsonStatus"] == "ready"
    assert payload["renderablePreview"]["available"] is True
    assert payload["renderablePreview"]["kind"] == "direct_model"
    assert payload["renderablePreview"]["nodes"] == 2
    assert payload["renderablePreview"]["elements"] == 1
    assert payload["renderable"]["schema_version"] == "structure-viewer-renderable-ingest-payload.v1"
    assert payload["renderable"]["payload_kind"] == "direct_model"
    assert payload["renderable"]["source_name"] == "renderable.json"
    assert payload["ifc"]["source_family"] == "ifc"
    assert payload["ifc"]["commercial_review_status"] == "needs_review"
    assert "load_model_missing" in payload["ifc"]["quality_flags"]
