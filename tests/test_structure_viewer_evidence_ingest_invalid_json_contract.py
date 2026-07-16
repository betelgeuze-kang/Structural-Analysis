from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_invalid_and_nonobject_json_return_bounded_blocked_previews() -> None:
    script = """
import {
  buildEvidenceIngestPreviewFromText,
  extractRenderableEvidencePayloadFromText,
  inspectRenderableEvidencePayloadFromText,
} from './src/structure-viewer/viewer-evidence-ingest-model.js';

const malformedText = '{"nodes":["SECRET_RAW_PAYLOAD_MARKER"';
const malformedInspection = inspectRenderableEvidencePayloadFromText(
  malformedText,
  {sourceType: 'auto', sourceName: 'broken.json'},
);
const malformedPreview = buildEvidenceIngestPreviewFromText(
  malformedText,
  {sourceType: 'auto', projectId: 'broken_json', artifactPath: 'broken.json'},
);
const malformedExtract = extractRenderableEvidencePayloadFromText(
  malformedText,
  {sourceType: 'auto', sourceName: 'broken.json'},
);

const scalarText = JSON.stringify('not-an-object');
const scalarPreview = buildEvidenceIngestPreviewFromText(
  scalarText,
  {sourceType: 'json', projectId: 'scalar_json', artifactPath: 'scalar.json'},
);

const malformedAuthoritative = {
  schema_version: 'structural-analysis-viewer-payload.v2',
  source: 'authoritative_solver_result',
  solver_path_id: 'authoritative_cpu_linear_fea_3d_v1',
  analysis_fidelity: 'cpu_reference_linear_fea',
  reaction_definition: 'constrained_dof_internal_minus_external_force',
  equilibrium_residual_definition: 'free_dof_internal_minus_external_force; constrained entries are zero',
  nodes: [{id: 'N1', coordinates: [0, 0, 0]}],
  elements: [],
};
const authoritativePreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify(malformedAuthoritative),
  {sourceType: 'json', projectId: 'blocked_authoritative', artifactPath: 'blocked-authoritative.json'},
);

function compact(preview) {
  const drawing = preview.manifest.projects[0].drawings[0];
  const row = preview.normalized_rows[0];
  return {
    sourceType: preview.source_type,
    rowCount: preview.row_count,
    drawingCount: preview.drawing_count,
    blockedIssueCount: preview.blocked_issues.length,
    validationStatus: preview.renderable_payload_validation_status,
    errorCode: preview.renderable_payload_error_code,
    errorPath: preview.renderable_payload_error_path,
    drawingStatus: drawing.commercial_review_status,
    drawingId: drawing.drawing_id,
    artifactPath: drawing.artifact_path,
    loadModelStatus: row.load_model_status,
    qualityFlags: drawing.quality_flags,
    hasRawNodes: Object.prototype.hasOwnProperty.call(row, 'nodes'),
    hasRawElements: Object.prototype.hasOwnProperty.call(row, 'elements'),
    serialized: JSON.stringify(preview),
  };
}

console.log(JSON.stringify({
  malformedInspection,
  malformed: compact(malformedPreview),
  malformedExtract,
  scalar: compact(scalarPreview),
  authoritative: compact(authoritativePreview),
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

    inspection = payload["malformedInspection"]
    assert inspection["source_type"] == "json"
    assert inspection["available"] is False
    assert inspection["validation_status"] == "unavailable"
    assert inspection["validation_error_code"] == "json_parse_failed"
    assert inspection["validation_error_path"] == "/"
    assert inspection["payload"] is None
    assert payload["malformedExtract"] is None

    malformed = payload["malformed"]
    assert malformed["sourceType"] == "json"
    assert malformed["rowCount"] == 1
    assert malformed["drawingCount"] == 1
    assert malformed["blockedIssueCount"] == 1
    assert malformed["validationStatus"] == "unavailable"
    assert malformed["errorCode"] == "json_parse_failed"
    assert malformed["errorPath"] == "/"
    assert malformed["drawingStatus"] == "blocked"
    assert malformed["drawingId"] == "broken_json_blocked_json_ingest"
    assert malformed["artifactPath"] == "broken.json"
    assert malformed["loadModelStatus"] == "json_parse_failed"
    assert "evidence_ingest_blocked" in malformed["qualityFlags"]
    assert "json_parse_failed" in malformed["qualityFlags"]
    assert malformed["hasRawNodes"] is False
    assert malformed["hasRawElements"] is False
    assert "SECRET_RAW_PAYLOAD_MARKER" not in malformed["serialized"]

    scalar = payload["scalar"]
    assert scalar["blockedIssueCount"] == 1
    assert scalar["validationStatus"] == "unavailable"
    assert scalar["errorCode"] == "json_object_required"
    assert scalar["drawingStatus"] == "blocked"
    assert scalar["artifactPath"] == "scalar.json"
    assert scalar["loadModelStatus"] == "json_object_required"

    authoritative = payload["authoritative"]
    assert authoritative["blockedIssueCount"] == 1
    assert authoritative["validationStatus"] == "blocked_authoritative_contract"
    assert authoritative["errorCode"] == "viewer_model_identity_missing"
    assert authoritative["errorPath"] == "/model_identity"
    assert authoritative["drawingStatus"] == "blocked"
    assert authoritative["drawingId"] == (
        "blocked_authoritative_blocked_authoritative_viewer"
    )
    assert authoritative["artifactPath"] == "blocked-authoritative.json"
    assert authoritative["hasRawNodes"] is False
    assert authoritative["hasRawElements"] is False
