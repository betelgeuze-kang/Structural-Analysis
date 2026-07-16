from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMP_WORKFLOW = ROOT / ".github/workflows/codex-temp-local-ops-storage-patch.yml"


def test_local_ops_state_preserves_safe_state_across_storage_failures() -> None:
    script = """
import {
  VIEWER_LOCAL_OPS_STATE_KEY,
  readViewerLocalOpsState,
  writeViewerLocalOpsState,
} from './src/structure-viewer/viewer-local-ops-state.js';

function namedError(name, message) {
  const error = new Error(message);
  error.name = name;
  return error;
}

const previousText = JSON.stringify({
  reviewNotes: {safe: 'preserve'},
  reviewTasks: {task: {status: 'needs_check'}},
});
const emptyShape = readViewerLocalOpsState({storageGet: () => null});
const readSecurity = readViewerLocalOpsState({
  storageGet: () => { throw namedError('SecurityError', 'SECRET_READ_SECURITY'); },
});
const readGeneric = readViewerLocalOpsState({
  storageGet: () => { throw new Error('SECRET_READ_GENERIC'); },
});
const readBadType = readViewerLocalOpsState({
  storageGet: () => ({secret: 'SECRET_BAD_VALUE'}),
});
const readMalformed = readViewerLocalOpsState({
  storageGet: () => '{',
});
const previous = readViewerLocalOpsState({storageGet: () => previousText});

let successSetCount = 0;
let successStoredKey = '';
let successStoredText = '';
const success = writeViewerLocalOpsState({
  reviewNotes: {next: 'written'},
  auditEventsJsonl: '{"event":"write"}',
}, {
  storageGet: () => previousText,
  storageSet: (key, value) => {
    successSetCount += 1;
    successStoredKey = key;
    successStoredText = value;
  },
});

let quotaSetCount = 0;
const quota = writeViewerLocalOpsState({reviewNotes: {next: 'quota'}}, {
  storageGet: () => previousText,
  storageSet: () => {
    quotaSetCount += 1;
    throw namedError('QuotaExceededError', 'SECRET_QUOTA_MESSAGE');
  },
});

let securitySetCount = 0;
const security = writeViewerLocalOpsState({reviewNotes: {next: 'security'}}, {
  storageGet: () => previousText,
  storageSet: () => {
    securitySetCount += 1;
    throw namedError('SecurityError', 'SECRET_WRITE_SECURITY');
  },
});

let genericSetCount = 0;
const generic = writeViewerLocalOpsState({reviewNotes: {next: 'generic'}}, {
  storageGet: () => previousText,
  storageSet: () => {
    genericSetCount += 1;
    throw new Error('SECRET_WRITE_GENERIC');
  },
});

const missingAdapter = writeViewerLocalOpsState({reviewNotes: {next: 'missing'}}, {
  storageGet: () => previousText,
  storageSet: null,
});

let readFailureWriteCount = 0;
let readFailureStored = '';
const readFailureThenWrite = writeViewerLocalOpsState({
  reviewNotes: {fresh: 'allowed'},
}, {
  storageGet: () => { throw namedError('SecurityError', 'SECRET_PREVIOUS_READ'); },
  storageSet: (_key, value) => {
    readFailureWriteCount += 1;
    readFailureStored = value;
  },
});

const doubleFailure = writeViewerLocalOpsState({reviewNotes: {fresh: 'blocked'}}, {
  storageGet: () => { throw namedError('SecurityError', 'SECRET_DOUBLE_READ'); },
  storageSet: () => { throw namedError('QuotaExceededError', 'SECRET_DOUBLE_WRITE'); },
});

console.log(JSON.stringify({
  stateKey: VIEWER_LOCAL_OPS_STATE_KEY,
  emptyShape,
  readSecurity,
  readGeneric,
  readBadType,
  readMalformed,
  previous,
  success: {
    result: success,
    setCount: successSetCount,
    storedKey: successStoredKey,
    storedState: JSON.parse(successStoredText),
  },
  quota: {result: quota, setCount: quotaSetCount},
  security: {result: security, setCount: securitySetCount},
  generic: {result: generic, setCount: genericSetCount},
  missingAdapter,
  readFailureThenWrite: {
    result: readFailureThenWrite,
    setCount: readFailureWriteCount,
    storedState: JSON.parse(readFailureStored),
  },
  doubleFailure,
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

    expected_empty = {
        "recentSelections": [],
        "auditEventsJsonl": "",
        "exportHistory": [],
        "reviewNotes": {},
        "reviewTasks": {},
        "annotations": {},
        "receiptIndex": {},
        "lastImportPreview": None,
        "lastIngestPreview": None,
        "lastIngestRenderablePayload": None,
    }
    assert payload["stateKey"] == "structure-viewer-local-ops-state-v1"
    assert payload["emptyShape"] == expected_empty
    assert payload["readSecurity"] == expected_empty
    assert payload["readGeneric"] == expected_empty
    assert payload["readBadType"] == expected_empty
    assert payload["readMalformed"] == expected_empty

    previous = payload["previous"]
    assert previous["reviewNotes"] == {"safe": "preserve"}
    assert previous["reviewTasks"] == {"task": {"status": "needs_check"}}

    success = payload["success"]
    assert success["setCount"] == 1
    assert success["storedKey"] == payload["stateKey"]
    assert success["result"] == success["storedState"]
    assert success["result"]["reviewNotes"] == {"next": "written"}
    assert success["result"]["auditEventsJsonl"] == '{"event":"write"}'

    for name in ("quota", "security", "generic"):
        row = payload[name]
        assert row["setCount"] == 1
        assert row["result"] == previous
    assert payload["missingAdapter"] == previous

    read_then_write = payload["readFailureThenWrite"]
    assert read_then_write["setCount"] == 1
    assert read_then_write["result"] == read_then_write["storedState"]
    assert read_then_write["result"]["reviewNotes"] == {"fresh": "allowed"}
    assert payload["doubleFailure"] == expected_empty

    serialized = json.dumps(payload, sort_keys=True)
    for marker in (
        "SECRET_READ_SECURITY",
        "SECRET_READ_GENERIC",
        "SECRET_BAD_VALUE",
        "SECRET_QUOTA_MESSAGE",
        "SECRET_WRITE_SECURITY",
        "SECRET_WRITE_GENERIC",
        "SECRET_PREVIOUS_READ",
        "SECRET_DOUBLE_READ",
        "SECRET_DOUBLE_WRITE",
    ):
        assert marker not in serialized


def test_temporary_storage_patch_workflow_is_absent() -> None:
    assert not TEMP_WORKFLOW.exists()
