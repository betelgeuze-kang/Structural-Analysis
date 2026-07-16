from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_model_file_reader_preflights_parses_and_bounds_failures() -> None:
    script = """
import {
  VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT,
  VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES,
  VIEWER_LOCAL_MODEL_RESOURCE_POLICY,
  ViewerLocalModelFileError,
  readViewerLocalModelFile,
  viewerLocalModelFileFailure,
  viewerLocalModelFileMetadata,
} from './src/structure-viewer/viewer-local-model-file-reader.js';

async function capture(fn) {
  try {
    return {value: await fn(), error: null, rawError: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof ViewerLocalModelFileError,
        code: error.code || '',
        path: error.path || '',
        hasCause: Boolean(error.cause),
      },
      rawError: error,
    };
  }
}

let oversizedReadCount = 0;
const oversized = await capture(() => readViewerLocalModelFile({
  name: 'oversized.json',
  size: VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES + 1,
  async text() {
    oversizedReadCount += 1;
    throw new Error('must not run');
  },
}));

let validReadCount = 0;
const valid = await capture(() => readViewerLocalModelFile({
  name: 'model.json',
  size: 16,
  type: 'application/json',
  lastModified: 123,
  async text() {
    validReadCount += 1;
    return JSON.stringify({name: 'Aé😀'});
  },
}));
const metadata = viewerLocalModelFileMetadata(valid.value);

let decodedOverReadCount = 0;
const decodedOver = await capture(() => readViewerLocalModelFile({
  name: 'decoded-over.json',
  size: 1,
  async text() {
    decodedOverReadCount += 1;
    return 'x'.repeat(VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES + 1);
  },
}));

const invalidJson = await capture(() => readViewerLocalModelFile({
  name: 'invalid.json',
  size: 1,
  async text() { return '{'; },
}));
const arrayRoot = await capture(() => readViewerLocalModelFile({
  name: 'array.json',
  size: 2,
  async text() { return '[]'; },
}));
const scalarRoot = await capture(() => readViewerLocalModelFile({
  name: 'scalar.json',
  size: 4,
  async text() { return 'null'; },
}));
const missingReader = await capture(() => readViewerLocalModelFile({
  name: 'missing.json',
  size: 1,
}));
let rejectedReadCount = 0;
const rejected = await capture(() => readViewerLocalModelFile({
  name: 'rejected.json',
  size: 1,
  async text() {
    rejectedReadCount += 1;
    throw new Error('SECRET_READER_MESSAGE');
  },
}));

const oversizedFailure = viewerLocalModelFileFailure(
  oversized.rawError,
  {sourceName: 'oversized.json'},
);
const rejectedFailure = viewerLocalModelFileFailure(
  rejected.rawError,
  {sourceName: 'rejected.json'},
);

console.log(JSON.stringify({
  contract: VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT,
  policy: VIEWER_LOCAL_MODEL_RESOURCE_POLICY,
  maxBytes: VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES,
  oversizedReadCount,
  oversized,
  validReadCount,
  valid: valid.value,
  metadata,
  metadataHasPayload: Object.prototype.hasOwnProperty.call(metadata, 'payload'),
  decodedOverReadCount,
  decodedOver,
  invalidJson,
  arrayRoot,
  scalarRoot,
  missingReader,
  rejectedReadCount,
  rejected,
  oversizedFailure,
  rejectedFailure,
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = json.loads(completed.stdout)

    assert payload["contract"] == "structure_viewer_local_model_file_read_v1"
    assert payload["policy"] == "structure_viewer_local_model_file_budget_v1"
    assert payload["maxBytes"] == 64 * 1024 * 1024

    assert payload["oversizedReadCount"] == 0
    assert payload["oversized"]["error"] == {
        "expectedType": True,
        "code": "local_model_file_byte_limit_exceeded",
        "path": "/file/size",
        "hasCause": False,
    }

    assert payload["validReadCount"] == 1
    valid = payload["valid"]
    assert valid["contract"] == payload["contract"]
    assert valid["resourcePolicy"] == payload["policy"]
    assert valid["name"] == "model.json"
    assert valid["type"] == "application/json"
    assert valid["lastModified"] == 123
    assert valid["payload"] == {"name": "Aé😀"}
    assert valid["textByteLength"] == len(
        json.dumps({"name": "Aé😀"}, ensure_ascii=False).encode("utf-8")
    )
    assert payload["metadata"] == {
        "contract": payload["contract"],
        "resource_policy": payload["policy"],
        "file_name": "model.json",
        "file_size": 16,
        "file_type": "application/json",
        "last_modified": 123,
        "text_byte_length": valid["textByteLength"],
    }
    assert payload["metadataHasPayload"] is False

    assert payload["decodedOverReadCount"] == 1
    assert payload["decodedOver"]["error"] == {
        "expectedType": True,
        "code": "local_model_text_byte_limit_exceeded",
        "path": "/text",
        "hasCause": False,
    }
    assert payload["invalidJson"]["error"] == {
        "expectedType": True,
        "code": "local_model_json_parse_failed",
        "path": "/",
        "hasCause": True,
    }
    for name in ("arrayRoot", "scalarRoot"):
        assert payload[name]["error"] == {
            "expectedType": True,
            "code": "local_model_json_object_required",
            "path": "/",
            "hasCause": False,
        }
    assert payload["missingReader"]["error"] == {
        "expectedType": True,
        "code": "local_model_file_text_reader_missing",
        "path": "/file/text",
        "hasCause": False,
    }
    assert payload["rejectedReadCount"] == 1
    assert payload["rejected"]["error"] == {
        "expectedType": True,
        "code": "local_model_file_read_failed",
        "path": "/file/text",
        "hasCause": True,
    }

    assert payload["oversizedFailure"] == {
        "contract": payload["contract"],
        "resource_policy": payload["policy"],
        "file_name": "oversized.json",
        "status": "blocked",
        "error_code": "local_model_file_byte_limit_exceeded",
        "error_path": "/file/size",
    }
    assert payload["rejectedFailure"]["error_code"] == (
        "local_model_file_read_failed"
    )
    assert payload["rejectedFailure"]["error_path"] == "/file/text"
    assert "SECRET_READER_MESSAGE" not in json.dumps(payload["rejectedFailure"])
