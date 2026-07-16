from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_file_read_receipts_exclude_text_and_failures_use_stable_preview_fields() -> None:
    script = """
import {
  STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES,
} from './src/structure-viewer/viewer-evidence-ingest-resource-policy.js';
import {
  EvidenceIngestFileReadError,
  buildEvidenceIngestFileReadFailurePreview,
  evidenceIngestFileReadMetadata,
  readEvidenceIngestFileText,
} from './src/structure-viewer/viewer-evidence-ingest-file-reader.js';

const receipt = await readEvidenceIngestFileText({
  name: 'valid.json',
  size: 2,
  type: 'application/json',
  lastModified: 100,
  async text() { return '{}'; },
});
const metadata = evidenceIngestFileReadMetadata(receipt);
let oversizedError = null;
try {
  await readEvidenceIngestFileText({
    name: 'oversized.json',
    size: STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES + 1,
    async text() { throw new Error('must not run'); },
  });
} catch (error) {
  oversizedError = error;
}
const oversized = buildEvidenceIngestFileReadFailurePreview(
  oversizedError,
  {
    sourceType: 'json',
    sourceName: 'oversized.json',
    drawingId: 'drawing-1',
    generatedAt: '2026-07-16T00:00:00Z',
  },
);
const readFailure = buildEvidenceIngestFileReadFailurePreview(
  new EvidenceIngestFileReadError(
    'evidence_ingest_file_read_failed',
    '/file/text',
    'synthetic',
  ),
  {
    sourceType: 'csv',
    sourceName: 'failed.csv',
    drawingId: 'drawing-2',
    generatedAt: '2026-07-16T00:00:01Z',
  },
);

console.log(JSON.stringify({
  metadata,
  receiptHasText: Object.prototype.hasOwnProperty.call(receipt, 'text'),
  metadataHasText: Object.prototype.hasOwnProperty.call(metadata, 'text'),
  oversized,
  readFailure,
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout)

    assert payload["receiptHasText"] is True
    assert payload["metadataHasText"] is False
    assert payload["metadata"] == {
        "contract": "structure_viewer_evidence_file_read_v1",
        "resource_policy": "structure_viewer_evidence_ingest_budget_v1",
        "file_name": "valid.json",
        "file_size": 2,
        "file_type": "application/json",
        "last_modified": 100,
        "text_byte_length": 2,
    }

    oversized = payload["oversized"]
    assert oversized["source_type"] == "json"
    assert oversized["generated_at"] == "2026-07-16T00:00:00Z"
    assert oversized["row_count"] == 0
    assert oversized["drawing_count"] == 0
    assert oversized["blocked_issues"] == [
        {
            "drawing_id": "drawing-1",
            "issue": "evidence ingest file resource limit",
            "quality_flags": [
                "evidence_ingest_file_byte_limit_exceeded",
                "/file/size",
            ],
        }
    ]
    assert oversized["renderable_payload_validation_status"] == (
        "blocked_resource_limit"
    )
    assert oversized["renderable_payload_error_code"] == (
        "evidence_ingest_file_byte_limit_exceeded"
    )
    assert oversized["renderable_payload_error_path"] == "/file/size"
    assert oversized["ingest_file_read"] == {
        "contract": "structure_viewer_evidence_file_read_v1",
        "resource_policy": "structure_viewer_evidence_ingest_budget_v1",
        "file_name": "oversized.json",
        "status": "blocked",
        "error_code": "evidence_ingest_file_byte_limit_exceeded",
        "error_path": "/file/size",
    }
    assert "text" not in json.dumps(oversized)

    read_failure = payload["readFailure"]
    assert read_failure["source_type"] == "csv"
    assert read_failure["blocked_issues"][0] == {
        "drawing_id": "drawing-2",
        "issue": "evidence ingest file read failed",
        "quality_flags": ["evidence_ingest_file_read_failed", "/file/text"],
    }
    assert read_failure["renderable_payload_validation_status"] == "unavailable"
    assert read_failure["renderable_payload_error_code"] == (
        "evidence_ingest_file_read_failed"
    )
    assert read_failure["renderable_payload_error_path"] == "/file/text"
