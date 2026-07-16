export const VIEWER_LOCAL_OPS_STORAGE_POLICY = 'structure_viewer_local_ops_storage_v1';

function normalizeText(value) {
  return String(value ?? '').trim();
}

function frozenReceipt({
  ok,
  operation,
  status,
  key,
  text = '',
  errorCode = '',
  errorPath = '',
}) {
  return Object.freeze({
    policy: VIEWER_LOCAL_OPS_STORAGE_POLICY,
    ok: Boolean(ok),
    operation,
    status,
    key,
    text,
    error_code: errorCode,
    error_path: errorPath,
  });
}

function storageFailure(error, operation, key) {
  const name = normalizeText(error?.name);
  const code = Number(error?.code);
  const path = operation === 'read' ? '/storage/get' : '/storage/set';
  if (
    name === 'QuotaExceededError'
    || code === 22
    || code === 1014
  ) {
    return frozenReceipt({
      ok: false,
      operation,
      status: 'blocked',
      key,
      errorCode: 'local_ops_storage_quota_exceeded',
      errorPath: path,
    });
  }
  if (name === 'SecurityError') {
    return frozenReceipt({
      ok: false,
      operation,
      status: 'blocked',
      key,
      errorCode: 'local_ops_storage_access_denied',
      errorPath: path,
    });
  }
  return frozenReceipt({
    ok: false,
    operation,
    status: 'blocked',
    key,
    errorCode: operation === 'read'
      ? 'local_ops_storage_read_failed'
      : 'local_ops_storage_write_failed',
    errorPath: path,
  });
}

function adapterFailure(operation, key) {
  return frozenReceipt({
    ok: false,
    operation,
    status: 'blocked',
    key,
    errorCode: 'local_ops_storage_adapter_invalid',
    errorPath: operation === 'read' ? '/storage/get' : '/storage/set',
  });
}

function requireKey(key, operation) {
  const normalized = normalizeText(key);
  if (normalized) return normalized;
  return frozenReceipt({
    ok: false,
    operation,
    status: 'blocked',
    key: '',
    errorCode: 'local_ops_storage_key_invalid',
    errorPath: '/storage/key',
  });
}

export function readViewerLocalOpsStorage({
  storageGet,
  storageKey,
} = {}) {
  const key = requireKey(storageKey, 'read');
  if (typeof key !== 'string') return key;
  if (typeof storageGet !== 'function') return adapterFailure('read', key);

  let value;
  try {
    value = storageGet(key);
  } catch (error) {
    return storageFailure(error, 'read', key);
  }
  if (value === null || value === undefined || value === '') {
    return frozenReceipt({
      ok: true,
      operation: 'read',
      status: 'empty',
      key,
      text: '',
    });
  }
  if (typeof value !== 'string') {
    return frozenReceipt({
      ok: false,
      operation: 'read',
      status: 'blocked',
      key,
      errorCode: 'local_ops_storage_value_type_invalid',
      errorPath: '/storage/value',
    });
  }
  return frozenReceipt({
    ok: true,
    operation: 'read',
    status: 'ready',
    key,
    text: value,
  });
}

export function writeViewerLocalOpsStorage({
  storageSet,
  storageKey,
  text,
} = {}) {
  const key = requireKey(storageKey, 'write');
  if (typeof key !== 'string') return key;
  if (typeof storageSet !== 'function') return adapterFailure('write', key);
  if (typeof text !== 'string') {
    return frozenReceipt({
      ok: false,
      operation: 'write',
      status: 'blocked',
      key,
      errorCode: 'local_ops_storage_text_type_invalid',
      errorPath: '/storage/text',
    });
  }

  try {
    storageSet(key, text);
  } catch (error) {
    return storageFailure(error, 'write', key);
  }
  return frozenReceipt({
    ok: true,
    operation: 'write',
    status: 'written',
    key,
  });
}

export function viewerLocalOpsStorageReceiptMetadata(receipt) {
  if (
    receipt === null
    || typeof receipt !== 'object'
    || Array.isArray(receipt)
    || receipt.policy !== VIEWER_LOCAL_OPS_STORAGE_POLICY
  ) {
    return Object.freeze({
      policy: VIEWER_LOCAL_OPS_STORAGE_POLICY,
      ok: false,
      operation: '',
      status: 'blocked',
      error_code: 'local_ops_storage_receipt_invalid',
      error_path: '/storage/receipt',
    });
  }
  return Object.freeze({
    policy: receipt.policy,
    ok: Boolean(receipt.ok),
    operation: normalizeText(receipt.operation),
    status: normalizeText(receipt.status),
    error_code: normalizeText(receipt.error_code),
    error_path: normalizeText(receipt.error_path),
  });
}
