from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_file_reader_preflights_size_before_text_and_maps_read_failures() -> None:
    script = """
import {
  STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES,
  EvidenceIngestResourceLimitError,
} from './src/structure-viewer/viewer-evidence-ingest-resource-policy.js';
import {
  STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT,
  EvidenceIngestFileReadError,
  readEvidenceIngestFileText,
} from './src/structure-viewer/viewer-evidence-ingest-file-reader.js';

async function capture(fn) {
  try {
    return {value: await fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        fileReadError: error instanceof EvidenceIngestFileReadError,
        resourceError: error instanceof EvidenceIngestResourceLimitError,
        code: error.code || '',
        path: error.path || '',
        hasCause: Boolean(error.cause),
      },
    };
  }
}

let oversizedReadCount = 0;
const oversized = await capture(() => readEvidenceIngestFileText({
  name: 'oversized.json',
  size: STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES + 1,
  type: 'application/json',
  lastModified: 123,
  async text() {
    oversizedReadCount += 1;
    throw new Error('must not run');
  },
}));

let validReadCount = 0;
const valid = await capture(() => readEvidenceIngestFileText({
  name: 'valid.json',
  size: 7,
  type: 'application/json',
  lastModified: 456,
  async text() {
    validReadCount += 1;
    return 'Aé😀';
  },
}));

let decodedOverReadCount = 0;
const decodedOver = await capture(() => readEvidenceIngestFileText({
  name: 'decoded-over.json',
  size: 1,
  type: 'application/json',
  lastModified: 789,
  async text() {
    decodedOverReadCount += 1;
    return 'x'.repeat(STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES + 1);
  },
}));

const missingReader = await capture(() => readEvidenceIngestFileText({
  name: 'missing-reader.json',
  size: 1,
  type: 'application/json',
}));

let rejectedReadCount = 0;
const rejected = await capture(() => readEvidenceIngestFileText({
  name: 'rejected.json',
  size: 1,
  type: 'application/json',
  async text() {
    rejectedReadCount += 1;
    throw new Error('synthetic read failure');
  },
}));

let immutable = false;
if (valid.value) {
  try {
    valid.value.name = 'mutated.json';
  } catch (_error) {
    immutable = valid.value.name === 'valid.json';
  }
}

console.log(JSON.stringify({
  contract: STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT,
  oversizedReadCount,
  oversized,
  validReadCount,
  valid,
  immutable,
  decodedOverReadCount,
  decodedOver,
  missingReader,
  rejectedReadCount,
  rejected,
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

    assert payload["contract"] == "structure_viewer_evidence_file_read_v1"
    assert payload["oversizedReadCount"] == 0
    assert payload["oversized"]["error"] == {
        "fileReadError": False,
        "resourceError": True,
        "code": "evidence_ingest_file_byte_limit_exceeded",
        "path": "/file/size",
        "hasCause": False,
    }

    assert payload["validReadCount"] == 1
    valid = payload["valid"]["value"]
    assert valid == {
        "contract": "structure_viewer_evidence_file_read_v1",
        "resourcePolicy": "structure_viewer_evidence_ingest_budget_v1",
        "name": "valid.json",
        "size": 7,
        "type": "application/json",
        "lastModified": 456,
        "textByteLength": 7,
        "text": "Aé😀",
    }
    assert payload["immutable"] is True

    assert payload["decodedOverReadCount"] == 1
    assert payload["decodedOver"]["error"] == {
        "fileReadError": False,
        "resourceError": True,
        "code": "evidence_ingest_text_byte_limit_exceeded",
        "path": "/text",
        "hasCause": False,
    }

    assert payload["missingReader"]["error"] == {
        "fileReadError": True,
        "resourceError": False,
        "code": "evidence_ingest_file_text_reader_missing",
        "path": "/file/text",
        "hasCause": False,
    }
    assert payload["rejectedReadCount"] == 1
    assert payload["rejected"]["error"] == {
        "fileReadError": True,
        "resourceError": False,
        "code": "evidence_ingest_file_read_failed",
        "path": "/file/text",
        "hasCause": True,
    }
