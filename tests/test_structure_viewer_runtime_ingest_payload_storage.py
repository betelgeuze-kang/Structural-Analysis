from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_payload_storage_is_fail_closed_and_preserves_memory() -> None:
    script = r"""
import {
  VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY,
  RuntimeIngestPayloadStorageError,
  createRuntimeIngestPayloadStorage,
  runtimeIngestStorageReceiptMetadata,
  validateRuntimeIngestPayload,
} from './src/structure-viewer/viewer-runtime-ingest-payload-storage.js';

function namedError(name, message, code = undefined) {
  const error = new Error(message);
  error.name = name;
  if (code !== undefined) Object.defineProperty(error, 'code', {value: code});
  return error;
}

function directPayload(marker = 'safe', nodeCount = 2, elementCount = 1) {
  return {
    schema_version: 'structure-viewer-renderable-ingest-payload.v1',
    source_name: marker,
    payload_kind: 'direct_model',
    node_count: nodeCount,
    element_count: elementCount,
    segment_count: 0,
    payload: {
      model: {
        nodes: new Array(nodeCount).fill(null).map((_, index) => ({id: `N${index}`})),
        elements: new Array(elementCount).fill(null).map((_, index) => ({id: `E${index}`})),
      },
    },
  };
}

function interactivePayload() {
  return {
    schema_version: 'structure-viewer-renderable-ingest-payload.v1',
    source_name: 'interactive',
    payload_kind: 'interactive_3d',
    node_count: 0,
    element_count: 0,
    segment_count: 3,
    payload: {
      interactive_3d: {
        baseline_segments: [{}, {}],
        after_segments: [{}],
      },
    },
  };
}

function capture(fn) {
  try {
    return {value: fn(), error: null};
  } catch (error) {
    return {
      value: null,
      error: {
        expectedType: error instanceof RuntimeIngestPayloadStorageError,
        code: error.code || '',
        path: error.path || '',
      },
    };
  }
}

let stored = '';
const persisted = createRuntimeIngestPayloadStorage({
  storageGet: () => stored || null,
  storageSet: (_key, text) => { stored = text; },
  storageRemove: () => { stored = ''; },
});
const mutableInput = directPayload('MUTABLE_INPUT');
const persistedReceipt = persisted.write(mutableInput);
mutableInput.payload.model.nodes.push({id: 'MUTATED_AFTER_WRITE'});
const persistedCurrent = persisted.current();

const reloaded = createRuntimeIngestPayloadStorage({
  storageGet: () => stored,
  storageSet: () => {},
  storageRemove: () => { stored = ''; },
});
const reloadedResult = reloaded.read();

const quota = createRuntimeIngestPayloadStorage({
  storageGet: () => null,
  storageSet: () => { throw namedError('QuotaExceededError', 'SECRET_QUOTA'); },
  storageRemove: () => {},
});
const quotaReceipt = quota.write(directPayload('SECRET_QUOTA_PAYLOAD'));
const quotaCurrent = quota.current();

const securityWrite = createRuntimeIngestPayloadStorage({
  storageGet: () => null,
  storageSet: () => { throw namedError('SecurityError', 'SECRET_SECURITY_WRITE'); },
  storageRemove: () => {},
});
const securityWriteReceipt = securityWrite.write(directPayload());

let retainedText = '';
const retained = createRuntimeIngestPayloadStorage({
  storageGet: () => retainedText || null,
  storageSet: (_key, text) => { retainedText = text; },
  storageRemove: () => { retainedText = ''; },
});
retained.write(directPayload('PREVIOUS_SAFE'));
const mismatched = directPayload('SECRET_MISMATCH');
mismatched.node_count = 999;
const mismatchReceipt = retained.write(mismatched);
const retainedAfterMismatch = retained.current();
const circular = directPayload('SECRET_CIRCULAR');
circular.payload.self = circular;
const circularReceipt = retained.write(circular);
const retainedAfterCircular = retained.current();

let clearBlockedText = '';
const clearBlocked = createRuntimeIngestPayloadStorage({
  storageGet: () => clearBlockedText || null,
  storageSet: (_key, text) => { clearBlockedText = text; },
  storageRemove: () => { throw namedError('SecurityError', 'SECRET_CLEAR'); },
});
clearBlocked.write(directPayload('PREVIOUS_CLEAR_SAFE'));
const clearBlockedReceipt = clearBlocked.clear();
const clearBlockedCurrent = clearBlocked.current();

let malformedRemoved = false;
const malformed = createRuntimeIngestPayloadStorage({
  storageGet: () => '{"SECRET_MALFORMED":',
  storageSet: () => {},
  storageRemove: () => { malformedRemoved = true; },
});
const malformedResult = malformed.read();

const malformedCleanupBlocked = createRuntimeIngestPayloadStorage({
  storageGet: () => '{bad json SECRET_CLEANUP}',
  storageSet: () => {},
  storageRemove: () => { throw namedError('SecurityError', 'SECRET_REMOVE'); },
});
const malformedCleanupResult = malformedCleanupBlocked.read();

let invalidRemoved = false;
const invalidStored = directPayload('SECRET_INVALID_STORED');
invalidStored.element_count = 7;
const invalid = createRuntimeIngestPayloadStorage({
  storageGet: () => JSON.stringify(invalidStored),
  storageSet: () => {},
  storageRemove: () => { invalidRemoved = true; },
});
const invalidResult = invalid.read();

const readSecurity = createRuntimeIngestPayloadStorage({
  storageGet: () => { throw namedError('SecurityError', 'SECRET_SECURITY_READ'); },
  storageSet: () => {},
  storageRemove: () => {},
});
const readSecurityResult = readSecurity.read();

const readGeneric = createRuntimeIngestPayloadStorage({
  storageGet: () => { throw new Error('SECRET_GENERIC_READ'); },
  storageSet: () => {},
  storageRemove: () => {},
});
const readGenericResult = readGeneric.read();

let typeRemoved = false;
const readWrongType = createRuntimeIngestPayloadStorage({
  storageGet: () => ({secret: 'SECRET_NON_STRING'}),
  storageSet: () => {},
  storageRemove: () => { typeRemoved = true; },
});
const wrongTypeResult = readWrongType.read();

const empty = createRuntimeIngestPayloadStorage({
  storageGet: () => null,
  storageSet: () => {},
  storageRemove: () => {},
});
const emptyResult = empty.read();

const excessiveSegments = interactivePayload();
excessiveSegments.segment_count = 200001;
excessiveSegments.payload.interactive_3d.baseline_segments = new Array(200001).fill(null);
excessiveSegments.payload.interactive_3d.after_segments = [];

console.log(JSON.stringify({
  policy: VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY,
  directValidation: validateRuntimeIngestPayload(directPayload()),
  interactiveValidation: validateRuntimeIngestPayload(interactivePayload()),
  mismatchValidation: capture(() => validateRuntimeIngestPayload(mismatched)),
  resourceValidation: capture(() => validateRuntimeIngestPayload(excessiveSegments)),
  persistedReceipt,
  persistedMemoryNodeCount: persistedCurrent.payload.payload.model.nodes.length,
  persistedMemoryFrozen: Object.isFrozen(persistedCurrent.payload)
    && Object.isFrozen(persistedCurrent.payload.payload.model.nodes),
  reloadedReceipt: reloadedResult.receipt,
  reloadedNodeCount: reloadedResult.payload.payload.model.nodes.length,
  quotaReceipt,
  quotaPayloadRetained: quotaCurrent.payload?.source_name === 'SECRET_QUOTA_PAYLOAD',
  securityWriteReceipt,
  mismatchReceipt,
  retainedAfterMismatch: retainedAfterMismatch.payload?.source_name,
  circularReceipt,
  retainedAfterCircular: retainedAfterCircular.payload?.source_name,
  clearBlockedReceipt,
  clearBlockedCurrent: clearBlockedCurrent.payload?.source_name,
  malformedReceipt: malformedResult.receipt,
  malformedRemoved,
  malformedCleanupReceipt: malformedCleanupResult.receipt,
  invalidReceipt: invalidResult.receipt,
  invalidRemoved,
  readSecurityReceipt: readSecurityResult.receipt,
  readGenericReceipt: readGenericResult.receipt,
  wrongTypeReceipt: wrongTypeResult.receipt,
  typeRemoved,
  emptyReceipt: emptyResult.receipt,
  invalidMetadata: runtimeIngestStorageReceiptMetadata({secret: 'SECRET_RECEIPT'}),
  forgedMetadata: runtimeIngestStorageReceiptMetadata({
    policy: VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY,
    operation: 'write',
    status: 'persisted',
    display_status: 'SECRET_FORGED_STATUS',
    persistence: 'session_storage',
  }),
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

    assert payload["policy"] == "structure_viewer_runtime_ingest_payload_storage_v1"
    assert payload["directValidation"] == {
        "nodeCount": 2,
        "elementCount": 1,
        "segmentCount": 0,
    }
    assert payload["interactiveValidation"] == {
        "nodeCount": 0,
        "elementCount": 0,
        "segmentCount": 3,
    }
    assert payload["mismatchValidation"]["error"] == {
        "expectedType": True,
        "code": "runtime_ingest_payload_count_mismatch",
        "path": "/payload",
    }
    assert payload["resourceValidation"]["error"] == {
        "expectedType": True,
        "code": "evidence_ingest_segment_count_limit_exceeded",
        "path": "/segments",
    }

    assert payload["persistedReceipt"]["status"] == "persisted"
    assert payload["persistedReceipt"]["display_status"] == "Saved locally"
    assert payload["persistedMemoryNodeCount"] == 2
    assert payload["persistedMemoryFrozen"] is True
    assert payload["reloadedReceipt"]["status"] == "ready"
    assert payload["reloadedNodeCount"] == 2

    assert payload["quotaReceipt"]["status"] == "session_only"
    assert payload["quotaReceipt"]["display_status"] == "Session-only"
    assert payload["quotaReceipt"]["error_code"] == (
        "runtime_ingest_storage_quota_exceeded"
    )
    assert payload["quotaReceipt"]["error_path"] == "/storage/set"
    assert payload["quotaPayloadRetained"] is True
    assert payload["securityWriteReceipt"]["error_code"] == (
        "runtime_ingest_storage_access_denied"
    )

    assert payload["mismatchReceipt"]["display_status"] == ("Previous state retained")
    assert payload["mismatchReceipt"]["payload_retained"] is True
    assert payload["mismatchReceipt"]["persistence"] == "session_storage"
    assert payload["retainedAfterMismatch"] == "PREVIOUS_SAFE"
    assert payload["circularReceipt"]["error_code"] == (
        "runtime_ingest_payload_serialization_failed"
    )
    assert payload["retainedAfterCircular"] == "PREVIOUS_SAFE"
    assert payload["clearBlockedReceipt"]["display_status"] == (
        "Previous state retained"
    )
    assert payload["clearBlockedReceipt"]["persistence"] == "session_storage"
    assert payload["clearBlockedReceipt"]["error_code"] == (
        "runtime_ingest_storage_access_denied"
    )
    assert payload["clearBlockedReceipt"]["error_path"] == "/storage/remove"
    assert payload["clearBlockedCurrent"] == "PREVIOUS_CLEAR_SAFE"

    assert payload["malformedReceipt"]["error_code"] == (
        "runtime_ingest_storage_json_malformed"
    )
    assert payload["malformedReceipt"]["error_path"] == "/storage/value"
    assert payload["malformedReceipt"]["corrupted_entry_removed"] is True
    assert payload["malformedRemoved"] is True
    assert payload["malformedCleanupReceipt"]["cleanup_error_code"] == (
        "runtime_ingest_storage_access_denied"
    )
    assert payload["malformedCleanupReceipt"]["cleanup_error_path"] == (
        "/storage/remove"
    )
    assert payload["invalidReceipt"]["error_code"] == (
        "runtime_ingest_payload_count_mismatch"
    )
    assert payload["invalidReceipt"]["corrupted_entry_removed"] is True
    assert payload["invalidRemoved"] is True

    assert payload["readSecurityReceipt"]["error_code"] == (
        "runtime_ingest_storage_access_denied"
    )
    assert payload["readSecurityReceipt"]["error_path"] == "/storage/get"
    assert payload["readGenericReceipt"]["error_code"] == (
        "runtime_ingest_storage_get_failed"
    )
    assert payload["wrongTypeReceipt"]["error_code"] == (
        "runtime_ingest_storage_value_type_invalid"
    )
    assert payload["typeRemoved"] is True
    assert payload["emptyReceipt"]["status"] == "empty"
    assert payload["emptyReceipt"]["display_status"] == "Session-only"
    assert payload["invalidMetadata"]["error_code"] == (
        "runtime_ingest_storage_receipt_invalid"
    )
    assert payload["forgedMetadata"]["error_code"] == (
        "runtime_ingest_storage_receipt_invalid"
    )

    serialized_receipts = json.dumps(payload, sort_keys=True)
    for marker in (
        "SECRET_MALFORMED",
        "SECRET_CLEANUP",
        "SECRET_REMOVE",
        "SECRET_SECURITY_READ",
        "SECRET_GENERIC_READ",
        "SECRET_NON_STRING",
        "SECRET_RECEIPT",
        "SECRET_FORGED_STATUS",
        "SECRET_CIRCULAR",
        "SECRET_MISMATCH",
        "SECRET_CLEAR",
    ):
        assert marker not in serialized_receipts


def test_runtime_payload_storage_statuses_are_visible_in_report_panel() -> None:
    script = r"""
import {buildReportExportPanelHtml} from './src/structure-viewer/viewer-report-panel-renderer.js';
import {createRuntimeIngestPayloadStorage} from './src/structure-viewer/viewer-runtime-ingest-payload-storage.js';

function directPayload(marker = 'safe') {
  return {
    schema_version: 'structure-viewer-renderable-ingest-payload.v1',
    source_name: marker,
    payload_kind: 'direct_model',
    node_count: 2,
    element_count: 1,
    segment_count: 0,
    payload: {
      model: {
        nodes: [{id: 'N1'}, {id: 'N2'}],
        elements: [{id: 'E1'}],
      },
    },
  };
}

let stored = '';
const persisted = createRuntimeIngestPayloadStorage({
  storageGet: () => stored || null,
  storageSet: (_key, text) => { stored = text; },
  storageRemove: () => { stored = ''; },
});
const saved = persisted.write(directPayload());
const invalid = directPayload();
invalid.node_count = 7;
const retained = persisted.write(invalid);

const sessionOnlyStorage = createRuntimeIngestPayloadStorage({
  storageGet: () => null,
  storageSet: () => {
    const error = new Error('private quota detail');
    error.name = 'QuotaExceededError';
    throw error;
  },
  storageRemove: () => {},
});
const sessionOnly = sessionOnlyStorage.write(directPayload());

const unavailableStorage = createRuntimeIngestPayloadStorage({
  storageGet: () => {
    const error = new Error('private security detail');
    error.name = 'SecurityError';
    throw error;
  },
  storageSet: () => {},
  storageRemove: () => {},
});
const unavailable = unavailableStorage.read().receipt;

const panels = [saved, sessionOnly, unavailable, retained].map((receipt) => (
  buildReportExportPanelHtml({runtimeIngestStorage: receipt})
));
console.log(JSON.stringify({panels}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    panels = json.loads(completed.stdout)["panels"]

    expected = (
        ("Saved locally", "persisted", "session_storage"),
        ("Session-only", "session_only", "memory_only"),
        ("Storage unavailable", "blocked", "none"),
        ("Previous state retained", "blocked", "session_storage"),
    )
    for panel, (label, status, persistence) in zip(panels, expected, strict=True):
        assert "data-runtime-ingest-storage-row" in panel
        assert label in panel
        assert f'data-runtime-ingest-storage-status="{status}"' in panel
        assert f'data-runtime-ingest-storage-persistence="{persistence}"' in panel

    assert "private quota detail" not in panels[1]
    assert "runtime_ingest_storage_quota_exceeded" in panels[1]
    assert "private security detail" not in panels[2]
    assert "runtime_ingest_storage_access_denied" in panels[2]


def test_runtime_payload_storage_is_wired_into_viewer_and_ci() -> None:
    index = (ROOT / "src/structure-viewer/index.html").read_text(encoding="utf-8")
    storage_facade = (
        ROOT / "src/structure-viewer/viewer-storage.js"
    ).read_text(encoding="utf-8")
    renderer = (
        ROOT / "src/structure-viewer/viewer-report-panel-renderer.js"
    ).read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/runtime-input-viewer-ci.yml").read_text(
        encoding="utf-8"
    )
    frontend_contract = (
        ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
    ).read_text(encoding="utf-8")

    assert "from './viewer-storage.js'" in index
    assert "createBrowserRuntimeIngestPayloadStorage(window)" in index
    assert "createRuntimeIngestPayloadStorage({" in storage_facade
    assert "storageGet: key => browserWindow.sessionStorage.getItem(key)" in storage_facade
    assert (
        "storageSet: (key, text) => browserWindow.sessionStorage.setItem(key, text)"
        in storage_facade
    )
    assert "storageRemove: key => browserWindow.sessionStorage.removeItem(key)" in storage_facade
    assert "runtimeIngestPayloadStorage.read()" in index
    assert "runtimeIngestPayloadStorage.write(payload)" in index
    assert "runtimeIngestPayloadStorage.clear()" in index
    assert "runtimeIngestStorage:runtimeIngestStorageStatus" in index
    assert "__STRUCTURE_VIEWER_RUNTIME_INGEST_STORAGE_STATUS__" in index

    # These helpers remain necessary for unrelated viewer preferences. Runtime
    # ingest persistence itself must go through the validating controller.
    assert "function safeSessionStorageGet(key)" in index
    assert "function safeSessionStorageSet(key,value)" in index
    assert (
        "JSON.parse(safeSessionStorageGet(VIEWER_RUNTIME_INGEST_PAYLOAD_SESSION_KEY)"
        not in index
    )

    assert "data-runtime-ingest-storage-row" in renderer
    assert "data-runtime-ingest-storage-status" in renderer
    assert "data-runtime-ingest-storage-persistence" in renderer
    assert "data-runtime-ingest-storage-error-code" in renderer
    assert "data-runtime-ingest-storage-error-path" in renderer
    for label in (
        "Saved locally",
        "Session-only",
        "Storage unavailable",
        "Previous state retained",
    ):
        assert label in renderer

    assert '"src/structure-viewer/viewer-runtime-ingest-payload-storage.js"' in workflow
    assert '"src/structure-viewer/viewer-report-panel-renderer.js"' in workflow
    assert '"src/structure-viewer/index.html"' in workflow
    assert "tests/test_structure_viewer_runtime_ingest_payload_storage.py" in workflow
    assert (
        "node --check src/structure-viewer/viewer-runtime-ingest-payload-storage.js"
        in workflow
    )
    assert (
        '"src/structure-viewer/viewer-runtime-ingest-payload-storage.js"'
        in frontend_contract
    )
