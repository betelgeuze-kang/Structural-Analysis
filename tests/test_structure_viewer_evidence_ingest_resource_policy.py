from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_text_file_row_and_renderable_resource_budgets_fail_closed() -> None:
    script = """
import {
  STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT,
  STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT,
  STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT,
  STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT,
  STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES,
  STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
  EvidenceIngestResourceLimitError,
  evidenceIngestResourceLimits,
  measureUtf8Bytes,
  validateEvidenceIngestFileMetadata,
  validateEvidenceIngestRenderableCounts,
  validateEvidenceIngestRowCount,
} from './src/structure-viewer/viewer-evidence-ingest-resource-policy.js';
import {
  buildEvidenceIngestPreview,
  buildEvidenceIngestPreviewFromText,
  inspectRenderableEvidencePayloadFromText,
} from './src/structure-viewer/viewer-evidence-ingest-model.js';

function capture(fn) {
  try {
    return {value: fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof EvidenceIngestResourceLimitError,
        code: error.code || '',
        path: error.path || '',
      },
    };
  }
}

const utf8At = measureUtf8Bytes('Aé😀', 7);
const utf8Over = measureUtf8Bytes('Aé😀', 6);
const exactFile = capture(() => validateEvidenceIngestFileMetadata({
  name: 'exact.json',
  size: STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES,
}));
const oversizedFile = capture(() => validateEvidenceIngestFileMetadata({
  name: 'oversized.json',
  size: STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES + 1,
}));
const oversizedTextInspection = inspectRenderableEvidencePayloadFromText(
  'x'.repeat(STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES + 1),
  {sourceType: 'json', sourceName: 'oversized.json'},
);

const rowLimit = capture(() => validateEvidenceIngestRowCount(
  STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT + 1,
));
const directRowsPreview = buildEvidenceIngestPreview({
  rows: new Array(STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT + 1).fill({
    drawing_id: 'SHOULD_NOT_SURVIVE',
    artifact_path: 'SHOULD_NOT_SURVIVE.json',
  }),
  sourceType: 'json',
  projectId: 'row_limit',
});
const csvText = [
  'drawing_id,artifact_path,member_count,node_count,element_count',
  ...new Array(STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT + 1).fill('row,row.csv,1,2,1'),
].join('\n');
const csvPreview = buildEvidenceIngestPreviewFromText(csvText, {
  sourceType: 'csv',
  projectId: 'csv_limit',
  artifactPath: 'rows.csv',
});
const jsonText = JSON.stringify(new Array(
  STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT + 1,
).fill({drawing_id: 'row'}));
const jsonPreview = buildEvidenceIngestPreviewFromText(jsonText, {
  sourceType: 'json',
  projectId: 'json_limit',
  artifactPath: 'rows.json',
});

const nodeCounts = capture(() => validateEvidenceIngestRenderableCounts({
  nodeCount: STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT + 1,
  elementCount: 0,
  segmentCount: 0,
}));
const elementCounts = capture(() => validateEvidenceIngestRenderableCounts({
  nodeCount: 0,
  elementCount: STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT + 1,
  segmentCount: 0,
}));
const segmentCounts = capture(() => validateEvidenceIngestRenderableCounts({
  nodeCount: 0,
  elementCount: 0,
  segmentCount: STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT + 1,
}));

const nodeInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify({
  model: {
    nodes: new Array(STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT + 1).fill(null),
    elements: [],
  },
}), {sourceType: 'json', sourceName: 'nodes.json'});
const elementInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify({
  model: {
    nodes: [],
    elements: new Array(STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT + 1).fill(null),
  },
}), {sourceType: 'json', sourceName: 'elements.json'});
const segmentInspection = inspectRenderableEvidencePayloadFromText(JSON.stringify({
  interactive_3d: {
    baseline_segments: new Array(STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT + 1).fill(null),
    after_segments: [],
  },
}), {sourceType: 'json', sourceName: 'segments.json'});

const validPreview = buildEvidenceIngestPreview({
  rows: [{
    drawing_id: 'valid',
    artifact_path: 'valid.json',
    member_count: 1,
    node_count: 2,
    element_count: 1,
  }],
  sourceType: 'json',
  projectId: 'valid',
});

function compactPreview(preview) {
  const row = preview.normalized_rows[0];
  return {
    rowCount: preview.row_count,
    drawingCount: preview.drawing_count,
    blockedIssueCount: preview.blocked_issues.length,
    status: preview.manifest.projects[0].drawings[0].commercial_review_status,
    errorCode: row.ingest_summary?.validation_error_code || '',
    errorPath: row.ingest_summary?.validation_error_path || '',
    serialized: JSON.stringify(preview),
  };
}

console.log(JSON.stringify({
  constants: evidenceIngestResourceLimits(),
  utf8At,
  utf8Over,
  exactFile,
  oversizedFile,
  oversizedTextInspection,
  rowLimit,
  directRows: compactPreview(directRowsPreview),
  csv: compactPreview(csvPreview),
  json: compactPreview(jsonPreview),
  nodeCounts,
  elementCounts,
  segmentCounts,
  nodeInspection,
  elementInspection,
  segmentInspection,
  valid: {
    policy: validPreview.resource_policy,
    limits: validPreview.resource_limits,
    rowCount: validPreview.row_count,
    drawingCount: validPreview.drawing_count,
    blockedIssueCount: validPreview.blocked_issues.length,
    status: validPreview.manifest.projects[0].drawings[0].commercial_review_status,
  },
  policy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    payload = json.loads(completed.stdout)

    limits = payload["constants"]
    assert payload["policy"] == "structure_viewer_evidence_ingest_budget_v1"
    assert limits == {
        "policy": payload["policy"],
        "max_text_bytes": 64 * 1024 * 1024,
        "max_rows": 10_000,
        "max_nodes": 200_000,
        "max_elements": 100_000,
        "max_segments": 200_000,
    }
    assert payload["utf8At"] == {
        "byteLength": 7,
        "limitExceeded": False,
        "maxBytes": 7,
    }
    assert payload["utf8Over"] == {
        "byteLength": 7,
        "limitExceeded": True,
        "maxBytes": 6,
    }
    assert payload["exactFile"]["value"]["allowed"] is True
    assert payload["exactFile"]["value"]["size"] == limits["max_text_bytes"]
    assert payload["oversizedFile"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_file_byte_limit_exceeded",
        "path": "/file/size",
    }
    text_block = payload["oversizedTextInspection"]
    assert text_block["available"] is False
    assert text_block["validation_status"] == "blocked_resource_limit"
    assert text_block["validation_error_code"] == (
        "evidence_ingest_text_byte_limit_exceeded"
    )
    assert text_block["validation_error_path"] == "/text"
    assert text_block["payload"] is None

    assert payload["rowLimit"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_row_count_limit_exceeded",
        "path": "/rows",
    }
    for name in ("directRows", "csv", "json"):
        preview = payload[name]
        assert preview["rowCount"] == 1
        assert preview["drawingCount"] == 1
        assert preview["blockedIssueCount"] == 1
        assert preview["status"] == "blocked"
        assert preview["errorCode"] == "evidence_ingest_row_count_limit_exceeded"
        assert "SHOULD_NOT_SURVIVE" not in preview["serialized"]
    assert payload["directRows"]["errorPath"] == "/rows"
    assert payload["csv"]["errorPath"] == "/rows"
    assert payload["json"]["errorPath"] == "/rows"

    assert payload["nodeCounts"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_node_count_limit_exceeded",
        "path": "/nodes",
    }
    assert payload["elementCounts"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_element_count_limit_exceeded",
        "path": "/elements",
    }
    assert payload["segmentCounts"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_segment_count_limit_exceeded",
        "path": "/segments",
    }
    for key, code, path in (
        ("nodeInspection", "evidence_ingest_node_count_limit_exceeded", "/nodes"),
        (
            "elementInspection",
            "evidence_ingest_element_count_limit_exceeded",
            "/elements",
        ),
        (
            "segmentInspection",
            "evidence_ingest_segment_count_limit_exceeded",
            "/segments",
        ),
    ):
        inspection = payload[key]
        assert inspection["available"] is False
        assert inspection["validation_status"] == "blocked_resource_limit"
        assert inspection["validation_error_code"] == code
        assert inspection["validation_error_path"] == path
        assert inspection["payload"] is None

    assert payload["valid"] == {
        "policy": payload["policy"],
        "limits": limits,
        "rowCount": 1,
        "drawingCount": 1,
        "blockedIssueCount": 0,
        "status": "ready",
    }
