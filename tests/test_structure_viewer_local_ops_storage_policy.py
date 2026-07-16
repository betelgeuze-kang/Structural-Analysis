from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_storage_policy_classifies_failures_without_raw_exceptions() -> None:
    script = """
import {
  VIEWER_LOCAL_OPS_STORAGE_POLICY,
  readViewerLocalOpsStorage,
  viewerLocalOpsStorageReceiptMetadata,
  writeViewerLocalOpsStorage,
} from './src/structure-viewer/viewer-local-ops-storage-policy.js';

function namedError(name, message, code = undefined) {
  const error = new Error(message);
  error.name = name;
  if (code !== undefined) Object.defineProperty(error, 'code', {value: code});
  return error;
}

const readReady = readViewerLocalOpsStorage({
  storageGet: () => '{"safe":true}',
  storageKey: 'state',
});
const readEmpty = readViewerLocalOpsStorage({
  storageGet: () => null,
  storageKey: 'state',
});
const readType = readViewerLocalOpsStorage({
  storageGet: () => ({secret: 'SECRET_STORAGE_VALUE'}),
  storageKey: 'state',
});
const readSecurity = readViewerLocalOpsStorage({
  storageGet: () => { throw namedError('SecurityError', 'SECRET_SECURITY_READ'); },
  storageKey: 'state',
});
const readGeneric = readViewerLocalOpsStorage({
  storageGet: () => { throw new Error('SECRET_GENERIC_READ'); },
  storageKey: 'state',
});
const readMissing = readViewerLocalOpsStorage({
  storageKey: 'state',
});
const readBadKey = readViewerLocalOpsStorage({
  storageGet: () => '',
  storageKey: '   ',
});

let writeCount = 0;
const writeReady = writeViewerLocalOpsStorage({
  storageSet: (_key, _text) => { writeCount += 1; },
  storageKey: 'state',
  text: '{}',
});
const writeQuota = writeViewerLocalOpsStorage({
  storageSet: () => { throw namedError('QuotaExceededError', 'SECRET_QUOTA'); },
  storageKey: 'state',
  text: '{}',
});
const writeLegacyQuota = writeViewerLocalOpsStorage({
  storageSet: () => { throw namedError('Error', 'SECRET_CODE_QUOTA', 22); },
  storageKey: 'state',
  text: '{}',
});
const writeSecurity = writeViewerLocalOpsStorage({
  storageSet: () => { throw namedError('SecurityError', 'SECRET_SECURITY_WRITE'); },
  storageKey: 'state',
  text: '{}',
});
const writeGeneric = writeViewerLocalOpsStorage({
  storageSet: () => { throw new Error('SECRET_GENERIC_WRITE'); },
  storageKey: 'state',
  text: '{}',
});
const writeMissing = writeViewerLocalOpsStorage({
  storageKey: 'state',
  text: '{}',
});
const writeType = writeViewerLocalOpsStorage({
  storageSet: () => {},
  storageKey: 'state',
  text: {secret: 'SECRET_STORAGE_TEXT'},
});
const invalidMetadata = viewerLocalOpsStorageReceiptMetadata({secret: 'SECRET_RECEIPT'});
const readyMetadata = viewerLocalOpsStorageReceiptMetadata(writeReady);

console.log(JSON.stringify({
  policy: VIEWER_LOCAL_OPS_STORAGE_POLICY,
  readReady,
  readEmpty,
  readType,
  readSecurity,
  readGeneric,
  readMissing,
  readBadKey,
  writeCount,
  writeReady,
  writeQuota,
  writeLegacyQuota,
  writeSecurity,
  writeGeneric,
  writeMissing,
  writeType,
  invalidMetadata,
  readyMetadata,
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

    assert payload["policy"] == "structure_viewer_local_ops_storage_v1"
    assert payload["readReady"] == {
        "policy": payload["policy"],
        "ok": True,
        "operation": "read",
        "status": "ready",
        "key": "state",
        "text": '{"safe":true}',
        "error_code": "",
        "error_path": "",
    }
    assert payload["readEmpty"]["ok"] is True
    assert payload["readEmpty"]["status"] == "empty"
    assert payload["readEmpty"]["text"] == ""
    assert payload["readType"]["error_code"] == (
        "local_ops_storage_value_type_invalid"
    )
    assert payload["readType"]["error_path"] == "/storage/value"
    assert payload["readSecurity"]["error_code"] == (
        "local_ops_storage_access_denied"
    )
    assert payload["readSecurity"]["error_path"] == "/storage/get"
    assert payload["readGeneric"]["error_code"] == "local_ops_storage_read_failed"
    assert payload["readMissing"]["error_code"] == (
        "local_ops_storage_adapter_invalid"
    )
    assert payload["readBadKey"]["error_code"] == "local_ops_storage_key_invalid"
    assert payload["readBadKey"]["error_path"] == "/storage/key"

    assert payload["writeCount"] == 1
    assert payload["writeReady"]["ok"] is True
    assert payload["writeReady"]["status"] == "written"
    assert payload["writeQuota"]["error_code"] == (
        "local_ops_storage_quota_exceeded"
    )
    assert payload["writeLegacyQuota"]["error_code"] == (
        "local_ops_storage_quota_exceeded"
    )
    assert payload["writeSecurity"]["error_code"] == (
        "local_ops_storage_access_denied"
    )
    assert payload["writeSecurity"]["error_path"] == "/storage/set"
    assert payload["writeGeneric"]["error_code"] == (
        "local_ops_storage_write_failed"
    )
    assert payload["writeMissing"]["error_code"] == (
        "local_ops_storage_adapter_invalid"
    )
    assert payload["writeType"]["error_code"] == (
        "local_ops_storage_text_type_invalid"
    )
    assert payload["writeType"]["error_path"] == "/storage/text"

    assert payload["invalidMetadata"] == {
        "policy": payload["policy"],
        "ok": False,
        "operation": "",
        "status": "blocked",
        "error_code": "local_ops_storage_receipt_invalid",
        "error_path": "/storage/receipt",
    }
    assert payload["readyMetadata"] == {
        "policy": payload["policy"],
        "ok": True,
        "operation": "write",
        "status": "written",
        "error_code": "",
        "error_path": "",
    }

    serialized = json.dumps(payload, sort_keys=True)
    for marker in (
        "SECRET_STORAGE_VALUE",
        "SECRET_SECURITY_READ",
        "SECRET_GENERIC_READ",
        "SECRET_QUOTA",
        "SECRET_CODE_QUOTA",
        "SECRET_SECURITY_WRITE",
        "SECRET_GENERIC_WRITE",
        "SECRET_STORAGE_TEXT",
        "SECRET_RECEIPT",
    ):
        assert marker not in serialized
