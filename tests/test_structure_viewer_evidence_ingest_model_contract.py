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
    validationStatus: renderablePreview.renderable_payload_validation_status,
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
    assert payload["renderablePreview"]["validationStatus"] == "basic_shape_only"
    assert payload["renderablePreview"]["nodes"] == 2
    assert payload["renderablePreview"]["elements"] == 1
    assert payload["renderable"]["schema_version"] == "structure-viewer-renderable-ingest-payload.v1"
    assert payload["renderable"]["payload_kind"] == "direct_model"
    assert payload["renderable"]["validation_status"] == "basic_shape_only"
    assert payload["renderable"]["source_name"] == "renderable.json"
    assert payload["ifc"]["source_family"] == "ifc"
    assert payload["ifc"]["commercial_review_status"] == "needs_review"
    assert "load_model_missing" in payload["ifc"]["quality_flags"]


def test_authoritative_viewer_ingest_validates_tracked_payload_and_blocks_downgrade() -> None:
    frame_result = json.loads(
        (
            ROOT
            / "implementation/phase1/release_evidence/productization/phase1_core_api_frame_result.json"
        ).read_text(encoding="utf-8")
    )
    viewer_payload = frame_result["metrics"]["viewer_payload"]
    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/viewer_payload.schema.json"
        ).read_text(encoding="utf-8")
    )
    script = f"""
import {{
  AUTHORITATIVE_VIEWER_IDENTITY_POLICY,
  AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
  AUTHORITATIVE_VIEWER_SCHEMA_VERSION,
  AuthoritativeViewerPayloadValidationError,
  claimsAuthoritativeViewerContract,
  validateAuthoritativeViewerPayload,
}} from './src/structure-viewer/viewer-authoritative-payload-contract.js';
import {{
  buildEvidenceIngestPreviewFromText,
  extractRenderableEvidencePayloadFromText,
  inspectRenderableEvidencePayloadFromText,
}} from './src/structure-viewer/viewer-evidence-ingest-model.js';

const authoritative = {json.dumps(viewer_payload, sort_keys=True)};
function capture(fn) {{
  try {{
    fn();
    return null;
  }} catch (error) {{
    return {{
      expectedType: error instanceof AuthoritativeViewerPayloadValidationError,
      code: error.code || '',
      path: error.path || '',
      message: String(error.message || error),
    }};
  }}
}}

const validInspection = inspectRenderableEvidencePayloadFromText(
  JSON.stringify(authoritative),
  {{sourceType: 'json', sourceName: 'phase1_core_api_frame_result.json'}},
);
const validExtract = extractRenderableEvidencePayloadFromText(
  JSON.stringify(authoritative),
  {{sourceType: 'json', sourceName: 'phase1_core_api_frame_result.json'}},
);
const validPreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify(authoritative),
  {{
    sourceType: 'json',
    projectId: 'authoritative_project',
    projectTitle: 'Authoritative Preview',
    artifactPath: 'phase1_core_api_frame_result.json',
  }},
);
const missingIdentity = structuredClone(authoritative);
delete missingIdentity.model_identity;
const missingInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify(missingIdentity));
const missingPreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify(missingIdentity),
  {{
    sourceType: 'json',
    projectId: 'blocked_authoritative_project',
    artifactPath: 'missing_identity.json',
  }},
);

const downgraded = structuredClone(authoritative);
downgraded.schema_version = 'legacy-viewer-payload.v1';
const downgradedInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify(downgraded));

const missingNode = structuredClone(authoritative);
missingNode.elements[0].nodes[1] = 'missing-node';
const missingNodeInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify(missingNode));

const nonfinite = structuredClone(authoritative);
nonfinite.nodes[0].coordinates[0] = Number.NaN;
const nonfiniteError = capture(() => validateAuthoritativeViewerPayload(nonfinite));

const genericPayload = {{
  model: {{
    nodes: [{{id: 1, x: 0, y: 0, z: 0}}, {{id: 2, x: 1, y: 0, z: 0}}],
    elements: [{{id: 'generic-1', node_ids: [1, 2], type: 'beam'}}],
  }},
}};
const genericInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify(genericPayload));
const validDrawing = validPreview.manifest.projects[0].drawings[0];
const validRow = validPreview.normalized_rows[0];
const missingDrawing = missingPreview.manifest.projects[0].drawings[0];

console.log(JSON.stringify({{
  constants: {{
    schemaVersion: AUTHORITATIVE_VIEWER_SCHEMA_VERSION,
    identityPolicy: AUTHORITATIVE_VIEWER_IDENTITY_POLICY,
    payloadKind: AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
  }},
  claimed: claimsAuthoritativeViewerContract(authoritative),
  validInspection,
  validExtract,
  validPreview: {{
    rowCount: validPreview.row_count,
    drawingCount: validPreview.drawing_count,
    blockedIssues: validPreview.blocked_issues,
    renderableStatus: validPreview.renderable_payload_validation_status,
    identity: validPreview.renderable_payload_model_identity,
    profileCounts: validPreview.commercial_tool_profiles,
    row: {{
      drawingId: validRow.drawing_id,
      nodeCount: validRow.node_count,
      elementCount: validRow.element_count,
      memberCount: validRow.member_count,
      artifactPath: validRow.artifact_path,
      hasRawNodes: Object.prototype.hasOwnProperty.call(validRow, 'nodes'),
      hasRawElements: Object.prototype.hasOwnProperty.call(validRow, 'elements'),
    }},
    drawing: {{
      status: validDrawing.commercial_review_status,
      qualityFlags: validDrawing.quality_flags,
      geometry: validDrawing.geometry_summary,
      provenance: validDrawing.provenance,
      ingestSummary: validDrawing.ingest_summary,
    }},
  }},
  missingInspection,
  missingPreview: {{
    blockedIssueCount: missingPreview.blocked_issues.length,
    drawingStatus: missingDrawing.commercial_review_status,
    validationStatus: missingPreview.renderable_payload_validation_status,
    errorCode: missingPreview.renderable_payload_error_code,
  }},
  downgradedInspection,
  missingNodeInspection,
  nonfiniteError,
  genericInspection,
}}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    expected_schema_version = schema["properties"]["schema_version"]["const"]
    expected_identity_policy = schema["$defs"]["modelIdentity"]["properties"][
        "identity_policy"
    ]["const"]
    assert payload["constants"] == {
        "schemaVersion": expected_schema_version,
        "identityPolicy": expected_identity_policy,
        "payloadKind": "authoritative_viewer_v2",
    }
    assert payload["claimed"] is True

    valid = payload["validInspection"]
    assert valid["available"] is True
    assert valid["payload_kind"] == "authoritative_viewer_v2"
    assert valid["validation_status"] == "validated_authoritative_contract"
    assert valid["node_count"] == len(viewer_payload["nodes"])
    assert valid["element_count"] == len(viewer_payload["elements"])
    assert valid["model_identity"] == viewer_payload["model_identity"]
    assert payload["validExtract"]["validation_status"] == (
        "validated_authoritative_contract"
    )
    assert payload["validExtract"]["model_identity"] == viewer_payload[
        "model_identity"
    ]

    preview = payload["validPreview"]
    assert preview["rowCount"] == 1
    assert preview["drawingCount"] == 1
    assert preview["blockedIssues"] == []
    assert preview["renderableStatus"] == "validated_authoritative_contract"
    assert preview["identity"] == viewer_payload["model_identity"]
    assert preview["profileCounts"] == {"generic": 1}
    assert preview["row"] == {
        "drawingId": "authoritative_project_authoritative_viewer",
        "nodeCount": len(viewer_payload["nodes"]),
        "elementCount": len(viewer_payload["elements"]),
        "memberCount": len(viewer_payload["elements"]),
        "artifactPath": "phase1_core_api_frame_result.json",
        "hasRawNodes": False,
        "hasRawElements": False,
    }
    assert preview["drawing"]["status"] == "needs_review"
    assert "authoritative_viewer_contract_validated" in preview["drawing"][
        "qualityFlags"
    ]
    assert "engineer_review_required" in preview["drawing"]["qualityFlags"]
    assert preview["drawing"]["geometry"]["node_count"] == len(
        viewer_payload["nodes"]
    )
    assert preview["drawing"]["geometry"]["element_count"] == len(
        viewer_payload["elements"]
    )
    assert preview["drawing"]["provenance"]["source_input_checksum"] == (
        viewer_payload["model_identity"]["source_input_checksum"]
    )
    assert preview["drawing"]["provenance"]["canonical_model_checksum"] == (
        viewer_payload["model_identity"]["canonical_model_checksum"]
    )
    assert preview["drawing"]["ingestSummary"]["validation_status"] == (
        "validated_authoritative_contract"
    )

    missing = payload["missingInspection"]
    assert missing["available"] is False
    assert missing["payload_kind"] == "authoritative_viewer_v2"
    assert missing["validation_status"] == "blocked_authoritative_contract"
    assert missing["validation_error_code"] == "viewer_model_identity_missing"
    assert missing["validation_error_path"] == "/model_identity"
    assert payload["missingPreview"] == {
        "blockedIssueCount": 1,
        "drawingStatus": "blocked",
        "validationStatus": "blocked_authoritative_contract",
        "errorCode": "viewer_model_identity_missing",
    }

    downgraded = payload["downgradedInspection"]
    assert downgraded["available"] is False
    assert downgraded["payload_kind"] == "authoritative_viewer_v2"
    assert downgraded["validation_status"] == "blocked_authoritative_contract"
    assert downgraded["validation_error_code"] == "viewer_payload_schema_invalid"
    assert downgraded["validation_error_path"] == "/schema_version"

    missing_node = payload["missingNodeInspection"]
    assert missing_node["available"] is False
    assert missing_node["validation_error_code"] == "viewer_element_node_missing"
    assert missing_node["validation_error_path"] == "/elements/0/nodes"

    assert payload["nonfiniteError"]["expectedType"] is True
    assert payload["nonfiniteError"]["code"] == "viewer_numeric_value_invalid"
    assert payload["nonfiniteError"]["path"] == "/nodes/0/coordinates/0"

    generic = payload["genericInspection"]
    assert generic["available"] is True
    assert generic["payload_kind"] == "direct_model"
    assert generic["validation_status"] == "basic_shape_only"
    assert generic["model_identity"] is None
