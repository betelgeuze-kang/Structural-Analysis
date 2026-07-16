from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_bundle_file_reader_preflights_parses_and_bounds_failures() -> None:
    script = """
import {
  VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT,
  VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES,
  VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY,
  ViewerProjectBundleFileError,
  buildViewerProjectBundleFileFailurePreview,
  readViewerProjectBundleFile,
  viewerProjectBundleFileMetadata,
} from './src/structure-viewer/viewer-project-bundle-file-reader.js';

async function capture(fn) {
  try {
    return {value: await fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof ViewerProjectBundleFileError,
        code: error.code || '',
        path: error.path || '',
        hasCause: Boolean(error.cause),
      },
      rawError: error,
    };
  }
}

let oversizedReadCount = 0;
const oversized = await capture(() => readViewerProjectBundleFile({
  name: 'oversized.json',
  size: VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES + 1,
  async text() {
    oversizedReadCount += 1;
    throw new Error('must not run');
  },
}));

let validReadCount = 0;
const valid = await capture(() => readViewerProjectBundleFile({
  name: 'bundle.json',
  size: 51,
  type: 'application/json',
  lastModified: 123,
  async text() {
    validReadCount += 1;
    return JSON.stringify({
      schema_version: 'structure-viewer-project-bundle.v1',
      project_id: 'project',
    });
  },
}));
const metadata = viewerProjectBundleFileMetadata(valid.value);

let decodedOverReadCount = 0;
const decodedOver = await capture(() => readViewerProjectBundleFile({
  name: 'decoded-over.json',
  size: 1,
  async text() {
    decodedOverReadCount += 1;
    return 'x'.repeat(VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES + 1);
  },
}));

const invalidJson = await capture(() => readViewerProjectBundleFile({
  name: 'invalid.json',
  size: 1,
  async text() { return '{'; },
}));
const arrayRoot = await capture(() => readViewerProjectBundleFile({
  name: 'array.json',
  size: 2,
  async text() { return '[]'; },
}));
const scalarRoot = await capture(() => readViewerProjectBundleFile({
  name: 'scalar.json',
  size: 4,
  async text() { return 'null'; },
}));
const missingReader = await capture(() => readViewerProjectBundleFile({
  name: 'missing.json',
  size: 1,
}));
let rejectedReadCount = 0;
const rejected = await capture(() => readViewerProjectBundleFile({
  name: 'rejected.json',
  size: 1,
  async text() {
    rejectedReadCount += 1;
    throw new Error('SECRET_READER_MESSAGE');
  },
}));

const oversizedPreview = buildViewerProjectBundleFileFailurePreview(
  oversized.rawError,
  {sourceName: 'oversized.json', generatedAt: '2026-07-16T00:00:00Z'},
);
const rejectedPreview = buildViewerProjectBundleFileFailurePreview(
  rejected.rawError,
  {sourceName: 'rejected.json', generatedAt: '2026-07-16T00:00:01Z'},
);

console.log(JSON.stringify({
  contract: VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT,
  policy: VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY,
  maxBytes: VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES,
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
  oversizedPreview,
  rejectedPreview,
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)

    assert payload["contract"] == "structure_viewer_project_bundle_file_read_v1"
    assert payload["policy"] == "structure_viewer_project_bundle_budget_v1"
    assert payload["maxBytes"] == 16 * 1024 * 1024

    assert payload["oversizedReadCount"] == 0
    assert payload["oversized"]["error"] == {
        "expectedType": True,
        "code": "project_bundle_file_byte_limit_exceeded",
        "path": "/file/size",
        "hasCause": False,
    }

    assert payload["validReadCount"] == 1
    assert payload["valid"]["contract"] == payload["contract"]
    assert payload["valid"]["resourcePolicy"] == payload["policy"]
    assert payload["valid"]["name"] == "bundle.json"
    assert payload["valid"]["type"] == "application/json"
    assert payload["valid"]["lastModified"] == 123
    assert payload["valid"]["payload"] == {
        "schema_version": "structure-viewer-project-bundle.v1",
        "project_id": "project",
    }
    assert payload["valid"]["textByteLength"] > 0
    assert payload["metadata"] == {
        "contract": payload["contract"],
        "resource_policy": payload["policy"],
        "file_name": "bundle.json",
        "file_size": 51,
        "file_type": "application/json",
        "last_modified": 123,
        "text_byte_length": payload["valid"]["textByteLength"],
    }
    assert payload["metadataHasPayload"] is False

    assert payload["decodedOverReadCount"] == 1
    assert payload["decodedOver"]["error"] == {
        "expectedType": True,
        "code": "project_bundle_text_byte_limit_exceeded",
        "path": "/text",
        "hasCause": False,
    }
    assert payload["invalidJson"]["error"] == {
        "expectedType": True,
        "code": "project_bundle_json_parse_failed",
        "path": "/",
        "hasCause": True,
    }
    for name in ("arrayRoot", "scalarRoot"):
        assert payload[name]["error"] == {
            "expectedType": True,
            "code": "project_bundle_json_object_required",
            "path": "/",
            "hasCause": False,
        }
    assert payload["missingReader"]["error"] == {
        "expectedType": True,
        "code": "project_bundle_file_text_reader_missing",
        "path": "/file/text",
        "hasCause": False,
    }
    assert payload["rejectedReadCount"] == 1
    assert payload["rejected"]["error"] == {
        "expectedType": True,
        "code": "project_bundle_file_read_failed",
        "path": "/file/text",
        "hasCause": True,
    }

    oversized_preview = payload["oversizedPreview"]
    assert oversized_preview["blocked"] is True
    assert oversized_preview["issues"] == [
        {
            "severity": "critical",
            "issue": "project bundle file preview blocked",
            "value": "project_bundle_file_byte_limit_exceeded@/file/size",
        }
    ]
    assert oversized_preview["file_read"] == {
        "contract": payload["contract"],
        "resource_policy": payload["policy"],
        "file_name": "oversized.json",
        "status": "blocked",
        "error_code": "project_bundle_file_byte_limit_exceeded",
        "error_path": "/file/size",
    }
    assert "SECRET_READER_MESSAGE" not in json.dumps(payload["rejectedPreview"])
    assert payload["rejectedPreview"]["issues"][0]["value"] == (
        "project_bundle_file_read_failed@/file/text"
    )
