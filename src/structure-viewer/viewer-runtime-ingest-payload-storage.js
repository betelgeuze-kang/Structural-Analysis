import {
  AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
} from './viewer-authoritative-payload-contract.js';
import {
  extractInteractivePayload,
  extractModelPayload,
} from './viewer-model-normalizer.js';
import {
  EvidenceIngestResourceLimitError,
  validateEvidenceIngestRenderableCounts,
  validateEvidenceIngestText,
} from './viewer-evidence-ingest-resource-policy.js';

export const VIEWER_RUNTIME_INGEST_PAYLOAD_SESSION_KEY = 'structure-viewer-runtime-ingest-payload-v1';
export const VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY = 'structure_viewer_runtime_ingest_payload_storage_v1';
export const VIEWER_RUNTIME_INGEST_PAYLOAD_SCHEMA_VERSION = 'structure-viewer-renderable-ingest-payload.v1';

const DISPLAY_STATUS = Object.freeze({
  saved: 'Saved locally',
  session: 'Session-only',
  unavailable: 'Storage unavailable',
  retained: 'Previous state retained',
});
const RECEIPT_OPERATIONS = new Set([
  'initialize',
  'get',
  'set',
  'read',
  'write',
  'clear',
]);
const RECEIPT_STATUSES = new Set([
  'session_only',
  'blocked',
  'empty',
  'corrupted_removed',
  'ready',
  'cleared',
  'persisted',
]);
const RECEIPT_PERSISTENCE = new Set(['none', 'memory_only', 'session_storage']);
const RECEIPT_DISPLAY_STATUSES = new Set(Object.values(DISPLAY_STATUS));

export class RuntimeIngestPayloadStorageError extends Error {
  constructor(code, path, message) {
    super(`${code}@${path}: ${message}`);
    this.name = 'RuntimeIngestPayloadStorageError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message) {
  throw new RuntimeIngestPayloadStorageError(code, path, message);
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function requireCount(value, path) {
  if (!Number.isInteger(value) || value < 0) {
    fail(
      'runtime_ingest_payload_count_invalid',
      path,
      'Runtime ingest resource counts must be non-negative integers.',
    );
  }
  return value;
}

function runtimePayloadCounts(payload) {
  const inner = payload.payload;
  const model = extractModelPayload(inner);
  const interactive = extractInteractivePayload(inner);
  let payloadKind = '';
  let counts = {nodeCount: 0, elementCount: 0, segmentCount: 0};
  if (model) {
    payloadKind = payload.payload_kind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND
      ? AUTHORITATIVE_VIEWER_PAYLOAD_KIND
      : 'direct_model';
    counts = {
      nodeCount: model.model.nodes.length,
      elementCount: model.model.elements.length,
      segmentCount: 0,
    };
  } else if (interactive) {
    payloadKind = 'interactive_3d';
    counts = {
      nodeCount: 0,
      elementCount: 0,
      segmentCount: (Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.length : 0)
        + (Array.isArray(interactive.after_segments) ? interactive.after_segments.length : 0),
    };
  } else {
    fail(
      'runtime_ingest_payload_shape_invalid',
      '/payload/payload',
      'Runtime ingest payload does not contain renderable model or segment data.',
    );
  }
  if (payload.payload_kind !== payloadKind) {
    fail(
      'runtime_ingest_payload_kind_mismatch',
      '/payload/payload_kind',
      'Declared payload kind does not match the renderable payload shape.',
    );
  }
  return counts;
}

export function validateRuntimeIngestPayload(payload) {
  if (!isRecord(payload)) {
    fail(
      'runtime_ingest_payload_object_required',
      '/payload',
      'Runtime ingest payload must be an object.',
    );
  }
  if (payload.schema_version !== VIEWER_RUNTIME_INGEST_PAYLOAD_SCHEMA_VERSION) {
    fail(
      'runtime_ingest_payload_schema_version_invalid',
      '/payload/schema_version',
      'Runtime ingest payload schema version is unsupported.',
    );
  }
  if (!isRecord(payload.payload)) {
    fail(
      'runtime_ingest_payload_shape_invalid',
      '/payload/payload',
      'Runtime ingest payload body must be an object.',
    );
  }
  const declared = {
    nodeCount: requireCount(payload.node_count, '/payload/node_count'),
    elementCount: requireCount(payload.element_count, '/payload/element_count'),
    segmentCount: requireCount(payload.segment_count, '/payload/segment_count'),
  };
  const actual = runtimePayloadCounts(payload);
  if (
    declared.nodeCount !== actual.nodeCount
    || declared.elementCount !== actual.elementCount
    || declared.segmentCount !== actual.segmentCount
  ) {
    fail(
      'runtime_ingest_payload_count_mismatch',
      '/payload',
      'Declared resource counts do not match the renderable payload.',
    );
  }
  try {
    validateEvidenceIngestRenderableCounts(actual);
  } catch (error) {
    if (!(error instanceof EvidenceIngestResourceLimitError)) throw error;
    fail(error.code, error.path, 'Runtime ingest payload exceeds a resource limit.');
  }
  return Object.freeze({...actual});
}

function freezeJsonValue(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  Object.values(value).forEach(freezeJsonValue);
  return Object.freeze(value);
}

function storageError(error, operation) {
  const name = normalizeText(error?.name);
  const code = Number(error?.code);
  const path = `/storage/${operation}`;
  if (name === 'QuotaExceededError' || code === 22 || code === 1014) {
    return {
      code: 'runtime_ingest_storage_quota_exceeded',
      path,
    };
  }
  if (name === 'SecurityError') {
    return {
      code: 'runtime_ingest_storage_access_denied',
      path,
    };
  }
  return {
    code: `runtime_ingest_storage_${operation}_failed`,
    path,
  };
}

function receipt({
  ok,
  operation,
  status,
  displayStatus,
  persistence,
  errorCode = '',
  errorPath = '',
  cleanupErrorCode = '',
  cleanupErrorPath = '',
  corruptedEntryRemoved = false,
  payloadRetained = false,
} = {}) {
  return Object.freeze({
    policy: VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY,
    ok: Boolean(ok),
    operation: normalizeText(operation),
    status: normalizeText(status),
    display_status: normalizeText(displayStatus),
    persistence: normalizeText(persistence),
    error_code: normalizeText(errorCode),
    error_path: normalizeText(errorPath),
    cleanup_error_code: normalizeText(cleanupErrorCode),
    cleanup_error_path: normalizeText(cleanupErrorPath),
    corrupted_entry_removed: Boolean(corruptedEntryRemoved),
    payload_retained: Boolean(payloadRetained),
  });
}

function adapterReceipt(operation, payloadRetained) {
  return receipt({
    ok: false,
    operation,
    status: 'blocked',
    displayStatus: payloadRetained ? DISPLAY_STATUS.retained : DISPLAY_STATUS.unavailable,
    persistence: payloadRetained ? 'memory_only' : 'none',
    errorCode: 'runtime_ingest_storage_adapter_invalid',
    errorPath: `/storage/${operation}`,
    payloadRetained,
  });
}

function parseValidatedPayload(text) {
  try {
    validateEvidenceIngestText(text);
  } catch (error) {
    if (!(error instanceof EvidenceIngestResourceLimitError)) throw error;
    fail(error.code, '/storage/value', 'Stored runtime ingest payload exceeds the byte limit.');
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (_error) {
    fail(
      'runtime_ingest_storage_json_malformed',
      '/storage/value',
      'Stored runtime ingest payload is not valid JSON.',
    );
  }
  validateRuntimeIngestPayload(parsed);
  return freezeJsonValue(parsed);
}

export function createRuntimeIngestPayloadStorage({
  storageGet,
  storageSet,
  storageRemove,
  storageKey = VIEWER_RUNTIME_INGEST_PAYLOAD_SESSION_KEY,
} = {}) {
  const key = normalizeText(storageKey);
  let memoryPayload = null;
  let memoryPersistence = 'none';
  let lastReceipt = receipt({
    ok: true,
    operation: 'initialize',
    status: 'session_only',
    displayStatus: DISPLAY_STATUS.session,
    persistence: 'memory_only',
  });

  function remember(nextReceipt) {
    lastReceipt = nextReceipt;
    return nextReceipt;
  }

  function cleanupCorruptedEntry() {
    if (typeof storageRemove !== 'function') {
      return {
        removed: false,
        cleanup: {
          code: 'runtime_ingest_storage_adapter_invalid',
          path: '/storage/remove',
        },
      };
    }
    try {
      storageRemove(key);
      return {removed: true, cleanup: {code: '', path: ''}};
    } catch (error) {
      return {removed: false, cleanup: storageError(error, 'remove')};
    }
  }

  function currentResult(nextReceipt = lastReceipt) {
    return Object.freeze({payload: memoryPayload, receipt: nextReceipt});
  }

  function read() {
    if (memoryPayload) return currentResult();
    if (!key || typeof storageGet !== 'function') {
      return currentResult(remember(adapterReceipt('get', false)));
    }
    let text;
    try {
      text = storageGet(key);
    } catch (error) {
      const failure = storageError(error, 'get');
      return currentResult(remember(receipt({
        ok: false,
        operation: 'read',
        status: 'blocked',
        displayStatus: DISPLAY_STATUS.unavailable,
        persistence: 'none',
        errorCode: failure.code,
        errorPath: failure.path,
      })));
    }
    if (text === null || text === undefined || text === '') {
      return currentResult(remember(receipt({
        ok: true,
        operation: 'read',
        status: 'empty',
        displayStatus: DISPLAY_STATUS.session,
        persistence: 'memory_only',
      })));
    }
    if (typeof text !== 'string') {
      const primary = new RuntimeIngestPayloadStorageError(
        'runtime_ingest_storage_value_type_invalid',
        '/storage/value',
        'Stored runtime ingest value must be text.',
      );
      const cleanup = cleanupCorruptedEntry();
      return currentResult(remember(receipt({
        ok: false,
        operation: 'read',
        status: 'corrupted_removed',
        displayStatus: DISPLAY_STATUS.unavailable,
        persistence: 'none',
        errorCode: primary.code,
        errorPath: primary.path,
        cleanupErrorCode: cleanup.cleanup.code,
        cleanupErrorPath: cleanup.cleanup.path,
        corruptedEntryRemoved: cleanup.removed,
      })));
    }
    try {
      memoryPayload = parseValidatedPayload(text);
    } catch (error) {
      const primary = error instanceof RuntimeIngestPayloadStorageError
        ? error
        : new RuntimeIngestPayloadStorageError(
          'runtime_ingest_storage_read_validation_failed',
          '/storage/value',
          'Stored runtime ingest payload validation failed.',
        );
      const cleanup = cleanupCorruptedEntry();
      return currentResult(remember(receipt({
        ok: false,
        operation: 'read',
        status: 'corrupted_removed',
        displayStatus: DISPLAY_STATUS.unavailable,
        persistence: 'none',
        errorCode: primary.code,
        errorPath: primary.path,
        cleanupErrorCode: cleanup.cleanup.code,
        cleanupErrorPath: cleanup.cleanup.path,
        corruptedEntryRemoved: cleanup.removed,
      })));
    }
    memoryPersistence = 'session_storage';
    return currentResult(remember(receipt({
      ok: true,
      operation: 'read',
      status: 'ready',
      displayStatus: DISPLAY_STATUS.saved,
      persistence: 'session_storage',
      payloadRetained: true,
    })));
  }

  function clear() {
    const previousPayload = memoryPayload;
    const previousPersistence = memoryPersistence;
    if (!key || typeof storageRemove !== 'function') {
      return remember(receipt({
        ok: false,
        operation: 'clear',
        status: 'blocked',
        displayStatus: previousPayload ? DISPLAY_STATUS.retained : DISPLAY_STATUS.unavailable,
        persistence: previousPayload ? previousPersistence : 'none',
        errorCode: 'runtime_ingest_storage_adapter_invalid',
        errorPath: '/storage/remove',
        payloadRetained: Boolean(previousPayload),
      }));
    }
    try {
      storageRemove(key);
    } catch (error) {
      const failure = storageError(error, 'remove');
      return remember(receipt({
        ok: false,
        operation: 'clear',
        status: 'blocked',
        displayStatus: previousPayload ? DISPLAY_STATUS.retained : DISPLAY_STATUS.unavailable,
        persistence: previousPayload ? previousPersistence : 'none',
        errorCode: failure.code,
        errorPath: failure.path,
        payloadRetained: Boolean(previousPayload),
      }));
    }
    memoryPayload = null;
    memoryPersistence = 'none';
    return remember(receipt({
      ok: true,
      operation: 'clear',
      status: 'cleared',
      displayStatus: DISPLAY_STATUS.saved,
      persistence: 'session_storage',
    }));
  }

  function write(payload) {
    if (payload === null || payload === undefined) return clear();
    const previousPayload = memoryPayload;
    const previousPersistence = memoryPersistence;
    let serialized;
    let detached;
    try {
      validateRuntimeIngestPayload(payload);
      serialized = JSON.stringify(payload);
      validateEvidenceIngestText(serialized);
      detached = parseValidatedPayload(serialized);
    } catch (error) {
      const primary = error instanceof RuntimeIngestPayloadStorageError
        || error instanceof EvidenceIngestResourceLimitError
        ? error
        : new RuntimeIngestPayloadStorageError(
          'runtime_ingest_payload_serialization_failed',
          '/payload',
          'Runtime ingest payload could not be serialized.',
        );
      memoryPayload = previousPayload;
      memoryPersistence = previousPersistence;
      return remember(receipt({
        ok: false,
        operation: 'write',
        status: 'blocked',
        displayStatus: previousPayload ? DISPLAY_STATUS.retained : DISPLAY_STATUS.session,
        persistence: previousPayload ? previousPersistence : 'none',
        errorCode: primary.code,
        errorPath: primary instanceof EvidenceIngestResourceLimitError
          ? '/payload'
          : primary.path,
        payloadRetained: Boolean(previousPayload),
      }));
    }
    memoryPayload = detached;
    memoryPersistence = 'memory_only';
    if (!key || typeof storageSet !== 'function') {
      return remember(adapterReceipt('set', true));
    }
    try {
      storageSet(key, serialized);
    } catch (error) {
      const failure = storageError(error, 'set');
      return remember(receipt({
        ok: false,
        operation: 'write',
        status: 'session_only',
        displayStatus: DISPLAY_STATUS.session,
        persistence: 'memory_only',
        errorCode: failure.code,
        errorPath: failure.path,
        payloadRetained: true,
      }));
    }
    memoryPersistence = 'session_storage';
    return remember(receipt({
      ok: true,
      operation: 'write',
      status: 'persisted',
      displayStatus: DISPLAY_STATUS.saved,
      persistence: 'session_storage',
      payloadRetained: true,
    }));
  }

  return Object.freeze({
    read,
    write,
    clear,
    current: currentResult,
    status: () => lastReceipt,
  });
}

export function runtimeIngestStorageReceiptMetadata(value) {
  if (
    !isRecord(value)
    || value.policy !== VIEWER_RUNTIME_INGEST_PAYLOAD_STORAGE_POLICY
    || !RECEIPT_OPERATIONS.has(normalizeText(value.operation))
    || !RECEIPT_STATUSES.has(normalizeText(value.status))
    || !RECEIPT_PERSISTENCE.has(normalizeText(value.persistence))
    || !RECEIPT_DISPLAY_STATUSES.has(normalizeText(value.display_status))
  ) {
    return receipt({
      ok: false,
      operation: '',
      status: 'blocked',
      displayStatus: DISPLAY_STATUS.unavailable,
      persistence: 'none',
      errorCode: 'runtime_ingest_storage_receipt_invalid',
      errorPath: '/storage/receipt',
    });
  }
  return receipt({
    ok: value.ok,
    operation: value.operation,
    status: value.status,
    displayStatus: value.display_status,
    persistence: value.persistence,
    errorCode: value.error_code,
    errorPath: value.error_path,
    cleanupErrorCode: value.cleanup_error_code,
    cleanupErrorPath: value.cleanup_error_path,
    corruptedEntryRemoved: value.corrupted_entry_removed,
    payloadRetained: value.payload_retained,
  });
}
