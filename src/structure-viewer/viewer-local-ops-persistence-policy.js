import {
  VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS,
  VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES,
  VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY,
  VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
  VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS,
  VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES,
  VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS,
  VIEWER_PROJECT_BUNDLE_STATE_POLICY,
  inspectViewerProjectBundleLocalState,
  viewerProjectBundleStateLimits,
} from './viewer-project-bundle-state-policy.js';

export const VIEWER_LOCAL_OPS_PERSISTENCE_POLICY = 'structure_viewer_local_ops_persistence_v1';
export const VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES = 100;
export const VIEWER_LOCAL_OPS_MAX_TOOL_PROFILES = 100;

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function auditLines(value) {
  return normalizeText(value).split('\n').filter(Boolean);
}

function boundedObject(value, limit) {
  if (!isRecord(value)) return {};
  const entries = Object.entries(value);
  return Object.fromEntries(entries.slice(Math.max(0, entries.length - limit)));
}

function boundedArray(value, limit, {take = 'first'} = {}) {
  if (!Array.isArray(value)) return [];
  return take === 'last' ? value.slice(-limit) : value.slice(0, limit);
}

function boundedIssues(value) {
  return boundedArray(value, VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES).map((row) => (
    isRecord(row) ? {...row} : {severity: 'warning', issue: normalizeText(row)}
  ));
}

function copyFileRead(value) {
  return isRecord(value) ? {...value} : null;
}

function compactEvidenceIngestPreview(value, {
  includeManifest = true,
  renderablePayloadPersisted = false,
} = {}) {
  if (!isRecord(value)) return null;
  return {
    schema_version: normalizeText(value.schema_version),
    source_type: normalizeText(value.source_type),
    generated_at: normalizeText(value.generated_at),
    resource_policy: normalizeText(value.resource_policy),
    resource_limits: isRecord(value.resource_limits) ? {...value.resource_limits} : {},
    ingest_text_byte_count: Number.isSafeInteger(value.ingest_text_byte_count)
      ? value.ingest_text_byte_count
      : 0,
    row_count: Number.isSafeInteger(value.row_count) ? value.row_count : 0,
    drawing_count: Number.isSafeInteger(value.drawing_count) ? value.drawing_count : 0,
    commercial_tool_profiles: boundedObject(
      value.commercial_tool_profiles,
      VIEWER_LOCAL_OPS_MAX_TOOL_PROFILES,
    ),
    crosswalk_candidate_count: Number.isSafeInteger(value.crosswalk_candidate_count)
      ? value.crosswalk_candidate_count
      : 0,
    blocked_issues: boundedIssues(value.blocked_issues),
    manifest: includeManifest && isRecord(value.manifest) ? value.manifest : null,
    renderable_payload_available: Boolean(value.renderable_payload_available),
    renderable_payload_kind: normalizeText(value.renderable_payload_kind),
    renderable_payload_validation_status: normalizeText(
      value.renderable_payload_validation_status,
    ),
    renderable_payload_error_code: normalizeText(value.renderable_payload_error_code),
    renderable_payload_error_path: normalizeText(value.renderable_payload_error_path),
    renderable_payload_model_identity: isRecord(value.renderable_payload_model_identity)
      ? {...value.renderable_payload_model_identity}
      : null,
    renderable_node_count: Number.isSafeInteger(value.renderable_node_count)
      ? value.renderable_node_count
      : 0,
    renderable_element_count: Number.isSafeInteger(value.renderable_element_count)
      ? value.renderable_element_count
      : 0,
    renderable_segment_count: Number.isSafeInteger(value.renderable_segment_count)
      ? value.renderable_segment_count
      : 0,
    ingest_file_read: copyFileRead(value.ingest_file_read),
    renderable_payload_persisted: Boolean(renderablePayloadPersisted),
    preview_persistence: includeManifest
      ? 'attachable_metadata'
      : 'summary_only_state_budget',
  };
}

function compactProjectBundleImportPreview(value, {includePayload = true} = {}) {
  if (!isRecord(value)) return null;
  return {
    schema_version: normalizeText(value.schema_version),
    source_schema_version: normalizeText(value.source_schema_version),
    project_id: normalizeText(value.project_id),
    drawing_id: normalizeText(value.drawing_id),
    variant: normalizeText(value.variant),
    blocked: Boolean(value.blocked) || !includePayload,
    issues: boundedIssues(value.issues),
    incoming_counts: isRecord(value.incoming_counts) ? {...value.incoming_counts} : {},
    state_policy: normalizeText(value.state_policy),
    state_limits: isRecord(value.state_limits) ? {...value.state_limits} : {},
    local_state_serialized_bytes: Number.isSafeInteger(value.local_state_serialized_bytes)
      ? value.local_state_serialized_bytes
      : 0,
    manifest: includePayload && isRecord(value.manifest) ? value.manifest : null,
    local_state: includePayload && isRecord(value.local_state) ? value.local_state : {},
    file_read: copyFileRead(value.file_read),
    preview_persistence: includePayload
      ? 'mergeable_metadata'
      : 'summary_only_state_budget',
  };
}

function baseCandidate(state) {
  const source = isRecord(state) ? state : {};
  const renderablePayload = isRecord(source.lastIngestRenderablePayload)
    ? source.lastIngestRenderablePayload
    : null;
  return {
    recentSelections: boundedArray(
      source.recentSelections,
      VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS,
    ),
    auditEventsJsonl: auditLines(source.auditEventsJsonl)
      .slice(-VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES)
      .join('\n'),
    exportHistory: boundedArray(
      source.exportHistory,
      VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY,
    ),
    reviewNotes: boundedObject(
      source.reviewNotes,
      VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES,
    ),
    reviewTasks: boundedObject(
      source.reviewTasks,
      VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS,
    ),
    annotations: boundedObject(
      source.annotations,
      VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS,
    ),
    receiptIndex: boundedObject(
      source.receiptIndex,
      VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
    ),
    lastImportPreview: compactProjectBundleImportPreview(
      source.lastImportPreview,
    ),
    lastIngestPreview: compactEvidenceIngestPreview(
      source.lastIngestPreview,
      {renderablePayloadPersisted: Boolean(renderablePayload)},
    ),
    lastIngestRenderablePayload: renderablePayload,
  };
}

function result(state, inspection, degradedFields = []) {
  return Object.freeze({
    valid: inspection.valid,
    policy: VIEWER_LOCAL_OPS_PERSISTENCE_POLICY,
    state,
    inspection,
    degraded_fields: Object.freeze([...degradedFields]),
  });
}

export function prepareViewerLocalOpsStateForStorage(state = {}) {
  const candidate = baseCandidate(state);
  let inspection = inspectViewerProjectBundleLocalState(candidate);
  if (inspection.valid) return result(candidate, inspection);

  const degradedFields = [];
  if (candidate.lastIngestRenderablePayload !== null) {
    candidate.lastIngestRenderablePayload = null;
    candidate.lastIngestPreview = compactEvidenceIngestPreview(
      candidate.lastIngestPreview,
      {
        includeManifest: true,
        renderablePayloadPersisted: false,
      },
    );
    degradedFields.push('lastIngestRenderablePayload');
    inspection = inspectViewerProjectBundleLocalState(candidate);
    if (inspection.valid) return result(candidate, inspection, degradedFields);
  }

  if (candidate.lastIngestPreview?.manifest) {
    candidate.lastIngestPreview = compactEvidenceIngestPreview(
      candidate.lastIngestPreview,
      {
        includeManifest: false,
        renderablePayloadPersisted: false,
      },
    );
    degradedFields.push('lastIngestPreview.manifest');
    inspection = inspectViewerProjectBundleLocalState(candidate);
    if (inspection.valid) return result(candidate, inspection, degradedFields);
  }

  if (candidate.lastImportPreview?.local_state || candidate.lastImportPreview?.manifest) {
    candidate.lastImportPreview = compactProjectBundleImportPreview(
      candidate.lastImportPreview,
      {includePayload: false},
    );
    degradedFields.push('lastImportPreview.local_state');
    degradedFields.push('lastImportPreview.manifest');
    inspection = inspectViewerProjectBundleLocalState(candidate);
    if (inspection.valid) return result(candidate, inspection, degradedFields);
  }

  return result(candidate, inspection, degradedFields);
}

export function viewerLocalOpsPersistenceLimits() {
  return Object.freeze({
    policy: VIEWER_LOCAL_OPS_PERSISTENCE_POLICY,
    state_policy: VIEWER_PROJECT_BUNDLE_STATE_POLICY,
    state_limits: viewerProjectBundleStateLimits(),
    max_preview_issues: VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES,
    max_tool_profiles: VIEWER_LOCAL_OPS_MAX_TOOL_PROFILES,
  });
}
