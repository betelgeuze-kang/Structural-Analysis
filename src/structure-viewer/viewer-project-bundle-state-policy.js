export const VIEWER_PROJECT_BUNDLE_STATE_POLICY = 'structure_viewer_project_bundle_state_budget_v1';
export const VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES = 4 * 1024 * 1024;
export const VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS = 12;
export const VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES = 80;
export const VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY = 20;
export const VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES = 80;
export const VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS = 200;
export const VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS = 500;
export const VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS = 500;

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function utf8ByteLengthUpTo(text, maxBytes) {
  let byteLength = 0;
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    if (unit <= 0x7f) byteLength += 1;
    else if (unit <= 0x7ff) byteLength += 2;
    else if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = index + 1 < text.length ? text.charCodeAt(index + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        byteLength += 4;
        index += 1;
      } else byteLength += 3;
    } else byteLength += 3;
    if (byteLength > maxBytes) return {byteLength, exceeded: true};
  }
  return {byteLength, exceeded: false};
}

function countOwnKeysUpTo(value, maxCount) {
  if (!isRecord(value)) return {count: 0, exceeded: false, validType: false};
  let count = 0;
  for (const key in value) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) continue;
    count += 1;
    if (count > maxCount) return {count, exceeded: true, validType: true};
  }
  return {count, exceeded: false, validType: true};
}

function auditLines(value) {
  return normalizeText(value).split('\n').filter(Boolean);
}

function limitIssue(code, path, field, count, limit) {
  return {
    severity: 'critical',
    issue: 'project bundle local state limit exceeded',
    value: `${field}=${count} limit=${limit}`,
    code,
    path,
  };
}

function typeIssue(path, field, expected) {
  return {
    severity: 'critical',
    issue: 'project bundle local state type invalid',
    value: `${field} requires ${expected}`,
    code: 'project_bundle_local_state_type_invalid',
    path,
  };
}

function emptyCounts() {
  return Object.freeze({
    recentSelections: 0,
    auditEvents: 0,
    exportHistory: 0,
    reviewNotes: 0,
    reviewTasks: 0,
    annotations: 0,
    receiptIndex: 0,
  });
}

export function viewerProjectBundleStateLimits() {
  return Object.freeze({
    policy: VIEWER_PROJECT_BUNDLE_STATE_POLICY,
    max_serialized_bytes: VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES,
    max_recent_selections: VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS,
    max_audit_lines: VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES,
    max_export_history: VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY,
    max_review_notes: VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES,
    max_review_tasks: VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS,
    max_annotations: VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS,
    max_receipts: VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
  });
}

export function inspectViewerProjectBundleLocalState(localState) {
  const issues = [];
  if (!isRecord(localState)) {
    issues.push(typeIssue('/local_state', 'local_state', 'an object'));
    return Object.freeze({
      valid: false,
      policy: VIEWER_PROJECT_BUNDLE_STATE_POLICY,
      limits: viewerProjectBundleStateLimits(),
      counts: emptyCounts(),
      serialized_bytes: 0,
      issues: Object.freeze(issues),
    });
  }

  const recentSelections = Array.isArray(localState.recentSelections)
    ? localState.recentSelections.length
    : 0;
  if (localState.recentSelections !== undefined && !Array.isArray(localState.recentSelections)) {
    issues.push(typeIssue('/local_state/recentSelections', 'recentSelections', 'an array'));
  }
  if (recentSelections > VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS) {
    issues.push(limitIssue(
      'project_bundle_recent_selection_limit_exceeded',
      '/local_state/recentSelections',
      'recentSelections',
      recentSelections,
      VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS,
    ));
  }

  if (
    localState.auditEventsJsonl !== undefined
    && typeof localState.auditEventsJsonl !== 'string'
  ) {
    issues.push(typeIssue(
      '/local_state/auditEventsJsonl',
      'auditEventsJsonl',
      'a string',
    ));
  }
  const auditEvents = typeof localState.auditEventsJsonl === 'string'
    ? auditLines(localState.auditEventsJsonl).length
    : 0;
  if (auditEvents > VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES) {
    issues.push(limitIssue(
      'project_bundle_audit_line_limit_exceeded',
      '/local_state/auditEventsJsonl',
      'auditEvents',
      auditEvents,
      VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES,
    ));
  }

  const exportHistory = Array.isArray(localState.exportHistory)
    ? localState.exportHistory.length
    : 0;
  if (localState.exportHistory !== undefined && !Array.isArray(localState.exportHistory)) {
    issues.push(typeIssue('/local_state/exportHistory', 'exportHistory', 'an array'));
  }
  if (exportHistory > VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY) {
    issues.push(limitIssue(
      'project_bundle_export_history_limit_exceeded',
      '/local_state/exportHistory',
      'exportHistory',
      exportHistory,
      VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY,
    ));
  }

  const objectFields = [
    ['reviewNotes', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES, 'project_bundle_review_note_limit_exceeded'],
    ['reviewTasks', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS, 'project_bundle_review_task_limit_exceeded'],
    ['annotations', VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS, 'project_bundle_annotation_limit_exceeded'],
    ['receiptIndex', VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS, 'project_bundle_receipt_limit_exceeded'],
  ];
  const objectCounts = {};
  for (const [field, limit, code] of objectFields) {
    const result = countOwnKeysUpTo(localState[field], limit);
    objectCounts[field] = result.count;
    if (localState[field] !== undefined && !result.validType) {
      issues.push(typeIssue(`/local_state/${field}`, field, 'an object'));
    }
    if (result.exceeded) {
      issues.push(limitIssue(
        code,
        `/local_state/${field}`,
        field,
        result.count,
        limit,
      ));
    }
  }

  let serializedBytes = 0;
  try {
    const serialized = JSON.stringify(localState);
    if (typeof serialized !== 'string') throw new TypeError('serialization returned no text');
    const measurement = utf8ByteLengthUpTo(
      serialized,
      VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES,
    );
    serializedBytes = measurement.byteLength;
    if (measurement.exceeded) {
      issues.push(limitIssue(
        'project_bundle_local_state_byte_limit_exceeded',
        '/local_state',
        'serialized_bytes',
        serializedBytes,
        VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES,
      ));
    }
  } catch (_error) {
    issues.push({
      severity: 'critical',
      issue: 'project bundle local state serialization failed',
      value: '--',
      code: 'project_bundle_local_state_serialization_failed',
      path: '/local_state',
    });
  }

  return Object.freeze({
    valid: !issues.some((issue) => issue.severity === 'critical'),
    policy: VIEWER_PROJECT_BUNDLE_STATE_POLICY,
    limits: viewerProjectBundleStateLimits(),
    counts: Object.freeze({
      recentSelections,
      auditEvents,
      exportHistory,
      reviewNotes: objectCounts.reviewNotes,
      reviewTasks: objectCounts.reviewTasks,
      annotations: objectCounts.annotations,
      receiptIndex: objectCounts.receiptIndex,
    }),
    serialized_bytes: serializedBytes,
    issues: Object.freeze(issues),
  });
}

function objectOrEmpty(value) {
  return isRecord(value) ? value : {};
}

function boundedObjectMerge(current, incoming, limit) {
  const merged = new Map();
  for (const [key, value] of Object.entries(objectOrEmpty(current))) {
    merged.set(key, value);
  }
  for (const [key, value] of Object.entries(objectOrEmpty(incoming))) {
    if (merged.has(key)) merged.delete(key);
    merged.set(key, value);
  }
  while (merged.size > limit) {
    const oldest = merged.keys().next().value;
    merged.delete(oldest);
  }
  return Object.fromEntries(merged);
}

function rejectedMerge(currentState, inspection, source) {
  return Object.freeze({
    valid: false,
    state: currentState,
    source,
    inspection,
  });
}

export function mergeViewerProjectBundleLocalState(currentState = {}, incomingState = {}) {
  const currentInspection = inspectViewerProjectBundleLocalState(currentState);
  if (!currentInspection.valid) {
    return rejectedMerge(currentState, currentInspection, 'current_state');
  }
  const incomingInspection = inspectViewerProjectBundleLocalState(incomingState);
  if (!incomingInspection.valid) {
    return rejectedMerge(currentState, incomingInspection, 'incoming_state');
  }

  const current = objectOrEmpty(currentState);
  const incoming = objectOrEmpty(incomingState);
  const audit = [
    ...auditLines(current.auditEventsJsonl),
    ...auditLines(incoming.auditEventsJsonl),
  ].slice(-VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES);
  const candidate = {
    ...current,
    recentSelections: [
      ...(Array.isArray(incoming.recentSelections) ? incoming.recentSelections : []),
      ...(Array.isArray(current.recentSelections) ? current.recentSelections : []),
    ].slice(0, VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS),
    auditEventsJsonl: audit.join('\n'),
    exportHistory: [
      ...(Array.isArray(incoming.exportHistory) ? incoming.exportHistory : []),
      ...(Array.isArray(current.exportHistory) ? current.exportHistory : []),
    ].slice(0, VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY),
    reviewNotes: boundedObjectMerge(
      current.reviewNotes,
      incoming.reviewNotes,
      VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES,
    ),
    reviewTasks: boundedObjectMerge(
      current.reviewTasks,
      incoming.reviewTasks,
      VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS,
    ),
    annotations: boundedObjectMerge(
      current.annotations,
      incoming.annotations,
      VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS,
    ),
    receiptIndex: boundedObjectMerge(
      current.receiptIndex,
      incoming.receiptIndex,
      VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
    ),
    lastIngestRenderablePayload: isRecord(incoming.lastIngestRenderablePayload)
      ? incoming.lastIngestRenderablePayload
      : current.lastIngestRenderablePayload || null,
  };
  const candidateInspection = inspectViewerProjectBundleLocalState(candidate);
  return Object.freeze({
    valid: candidateInspection.valid,
    state: candidateInspection.valid ? candidate : currentState,
    source: 'merged_state',
    inspection: candidateInspection,
  });
}
