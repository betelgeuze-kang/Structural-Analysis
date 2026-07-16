from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_direct_ingest_rejects_invalid_containers_without_partial_state() -> None:
    script = """
import {
  buildEvidenceIngestPreview,
  normalizeEvidenceIngestRow,
} from './src/structure-viewer/viewer-evidence-ingest-model.js';

const invalidContainer = buildEvidenceIngestPreview({
  rows: {drawing_id: 'SECRET_CONTAINER_MARKER'},
  sourceType: 'json',
  projectId: 'object_container',
});
const mixedRows = buildEvidenceIngestPreview({
  rows: [
    {
      drawing_id: 'candidate',
      artifact_path: 'candidate.json',
      member_count: 1,
      node_count: 2,
      element_count: 1,
      raw_marker: 'SECRET_VALID_ROW_MARKER',
    },
    null,
  ],
  sourceType: 'json',
  projectId: 'mixed_direct_rows',
});
const normalizedNull = normalizeEvidenceIngestRow(null, {
  sourceType: 'csv',
  projectId: 'single_row',
  drawingId: 'ignored_drawing',
  rowIndex: 3,
});
const valid = buildEvidenceIngestPreview({
  rows: [
    {
      drawing_id: 'valid_1',
      artifact_path: 'valid-1.json',
      member_count: 1,
      node_count: 2,
      element_count: 1,
    },
    {
      drawing_id: 'valid_2',
      artifact_path: 'valid-2.json',
      member_count: 2,
      node_count: 3,
      element_count: 2,
    },
  ],
  sourceType: 'json',
  projectId: 'valid_direct_rows',
});

function compact(preview) {
  const row = preview.normalized_rows[0];
  const drawing = preview.manifest.projects[0].drawings[0];
  return {
    rowCount: preview.row_count,
    drawingCount: preview.drawing_count,
    blockedIssueCount: preview.blocked_issues.length,
    drawingId: drawing.drawing_id,
    drawingStatus: drawing.commercial_review_status,
    artifactPath: drawing.artifact_path,
    loadModelStatus: row.load_model_status,
    errorCode: row.ingest_summary?.validation_error_code || '',
    errorPath: row.ingest_summary?.validation_error_path || '',
    serialized: JSON.stringify(preview),
  };
}

console.log(JSON.stringify({
  invalidContainer: compact(invalidContainer),
  mixedRows: compact(mixedRows),
  normalizedNull,
  valid: {
    rowCount: valid.row_count,
    drawingCount: valid.drawing_count,
    blockedIssueCount: valid.blocked_issues.length,
    statuses: valid.manifest.projects[0].drawings.map((row) => row.commercial_review_status),
    drawingIds: valid.manifest.projects[0].drawings.map((row) => row.drawing_id),
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

    invalid = payload["invalidContainer"]
    assert invalid["rowCount"] == 1
    assert invalid["drawingCount"] == 1
    assert invalid["blockedIssueCount"] == 1
    assert invalid["drawingId"] == "object_container_blocked_json_ingest"
    assert invalid["drawingStatus"] == "blocked"
    assert invalid["artifactPath"] == "inline-json-ingest-rows"
    assert invalid["loadModelStatus"] == "ingest_rows_array_required"
    assert invalid["errorCode"] == "ingest_rows_array_required"
    assert invalid["errorPath"] == "/rows"
    assert "SECRET_CONTAINER_MARKER" not in invalid["serialized"]

    mixed = payload["mixedRows"]
    assert mixed["rowCount"] == 1
    assert mixed["drawingCount"] == 1
    assert mixed["blockedIssueCount"] == 1
    assert mixed["drawingId"] == "mixed_direct_rows_blocked_json_ingest"
    assert mixed["drawingStatus"] == "blocked"
    assert mixed["artifactPath"] == "inline-json-ingest-rows"
    assert mixed["loadModelStatus"] == "ingest_row_object_required"
    assert mixed["errorCode"] == "ingest_row_object_required"
    assert mixed["errorPath"] == "/rows/1"
    assert "SECRET_VALID_ROW_MARKER" not in mixed["serialized"]
    assert "candidate.json" not in mixed["serialized"]

    normalized = payload["normalizedNull"]
    assert normalized["drawing_id"] == "single_row_blocked_csv_ingest"
    assert normalized["source_family"] == "csv_blocked_ingest"
    assert normalized["artifact_path"] == "inline-csv-ingest-rows"
    assert normalized["load_model_status"] == "ingest_row_object_required"
    assert normalized["commercial_review_status"] == "blocked"
    assert normalized["ingest_summary"]["validation_error_path"] == "/rows/3"

    valid = payload["valid"]
    assert valid == {
        "rowCount": 2,
        "drawingCount": 2,
        "blockedIssueCount": 0,
        "statuses": ["ready", "ready"],
        "drawingIds": ["valid_1", "valid_2"],
    }
