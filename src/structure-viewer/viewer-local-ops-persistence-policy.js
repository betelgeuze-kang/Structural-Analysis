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
export const VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS = 1000;
export const VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES = 100;
export const VIEWER_LOCAL_OPS_MAX_ISSUE_FLAGS = 20;
export const VIEWER_LOCAL_OPS_MAX_TOOL_PROFILES = 100;

const RESOURCE_LIMIT_FIELDS = [
  'policy',
  'max_text_bytes',
  'max_rows',
  'max_nodes',
  'max_elements',
  'max_segments',
  'max_serialized_bytes',
  'max_recent_selections',
  'max_audit_lines',
  'max_export_history',
  'max_review_notes',
  'max_review_tasks',
  'max_annotations',
  'max_receipts',
];
const INCOMING_COUNT_FIELDS = [
  'recentSelections',
  'auditEvents',
  'exportHistory',
  'reviewNotes',
  'reviewTasks',
  'annotations',
  'receiptIndex',
];
const FILE_READ_TEXT_FIELDS = [
  'contract',
  'resource_policy',
  'file_name',
  'file_type',
  'status',
  'error_code',
  'error_path',
];
const FILE_READ_INTEGER_FIELDS = [
  'file_size',
  'last_modified',
  'text_byte_length',
];
const NORMALIZED_ROW_FIELDS = [
  'project_id', 'projectId', 'drawing_id', 'drawingId', 'drawing_title', 'title', 'name',
  'source_family', 'sourceFamily', 'source_type', 'source_tool', 'tool', 'program',
  'analysis_program', 'application', 'source_tool_profile', 'source_profile',
  'member_id', 'memberId', 'external_member_id', 'source_member_id', 'sourceMemberId',
  'frame', 'frame_id', 'object_id', 'unique_name', 'element_id', 'guid', 'global_id',
  'globalid', 'label', 'id',
  'section', 'section_name', 'frame_section', 'property', 'profile', 'profile_name',
  'family_type', 'type_name', 'cross_section',
  'dcr', 'dcr_after', 'max_dcr_after', 'dcr_before', 'max_dcr_before', 'utilization',
  'usage', 'ratio', 'pm_ratio', 'design_ratio',
  'story', 'story_name', 'level', 'storey', 'building_storey', 'floor', 'location',
  'phase', 'base_level', 'reference_level',
  'mode', 'mode_id', 'mode_number', 'modal_case', 'mode_shape', 'eigenmode',
  'material', 'material_name', 'material_id', 'grade', 'structural_material',
  'load_combo', 'combination', 'output_case', 'case', 'combo', 'lc', 'loading',
  'load_combination',
  'receipt_path', 'receiptPath', 'path', 'artifact_path', 'source_path', 'model_path',
  'ifc_path',
  'member_count', 'node_count', 'element_count', 'load_model_status', 'evidence_level',
  'status', 'receipt_status', 'governing_constraint', 'constraint',
];

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

function boundedNumericObject(value, limit) {
  if (!isRecord(value)) return {};
  const entries = Object.entries(value)
    .filter(([, row]) => typeof row === 'number' && Number.isFinite(row))
    .slice(-limit);
  return Object.fromEntries(entries);
}

function boundedArray(value, limit, {take = 'first'} = {}) {
  if (!Array.isArray(value)) return [];
  return take === 'last' ? value.slice(-limit) : value.slice(0, limit);
}

function compactKnownScalars(value, fields) {
  if (!isRecord(value)) return {};
  const output = {};
  for (const field of fields) {
    const row = value[field];
    if (
      typeof row === 'string'
      || typeof row === 'boolean'
      || (typeof row === 'number' && Number.isFinite(row))
      || row === null
    ) {
      output[field] = row;
    }
  }
  return output;
}

function compactNormalizedRows(value) {
  return boundedArray(value, VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS)
    .map((row) => compactKnownScalars(row, NORMALIZED_ROW_FIELDS))
    .filter((row) => Object.keys(row).length > 0);
}

function compactIssue(row) {
  if (!isRecord(row)) {
    return {severity: 'warning', issue: normalizeText(row)};
  }
  const output = {
    severity: normalizeText(row.severity) || 'warning',
    issue: normalizeText(row.issue),
  };
  for (const field of ['value', 'code', 'path', 'drawing_id']) {
    const value = normalizeText(row[field]);
    if (value) output[field] = value;
  }
  if (Array.isArray(row.quality_flags)) {
    output.quality_flags = row.quality_flags
      .slice(0, VIEWER_LOCAL_OPS_MAX_ISSUE_FLAGS)
      .map((value) => normalizeText(value))
      .filter(Boolean);
  }
  return output;
}

function boundedIssues(value) {
  return boundedArray(value, VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES)
    .map((row) => compactIssue(row));
}

function compactFileRead(value) {
  if (!isRecord(value)) return null;
  const output = {};
  for (const field of FILE_READ_TEXT_FIELDS) {
    const row = normalizeText(value[field]);
    if (row) output[field] = row;
  }
  for (const field of FILE_READ_INTEGER_FIELDS) {
    const row = value[field];
    if (Number.isSafeInteger(row) && row >= 0) output[field] = row;
  }
  return output;
}

function compactModelIdentity(value) {
  if (!isRecord(value)) return null;
  const output = {};
  for (const field of [
    'identity_policy',
    'source_input_checksum',
    'canonical_model_checksum',
    'analysis_input_snapshot',
  ]) {
    const row = normalizeText(value[field]);
    if (row) output[field] = row;
  }
  return Object.keys(output).length ? output : null;
}

function compactEvidenceIngestPreview(value, {
  includeManifest = true,
  includeNormalizedRows = true,
  renderablePayloadPersisted = false,
} = {}) {
  if (!isRecord(value)) return null;
  const normalizedRows = includeNormalizedRows
    ? compactNormalizedRows(value.normalized_rows)
    : [];
  return {
    schema_version: normalizeText(value.schema_version),
    source_type: normalizeText(value.source_type),
    generated_at: normalizeText(value.generated_at),
    resource_policy: normalizeText(value.resource_policy),
    resource_limits: compactKnownScalars(value.resource_limits, RESOURCE_LIMIT_FIELDS),
    ingest_text_byte_count: Number.isSafeInteger(value.ingest_text_byte_count)
      ? value.ingest_text_byte_count
      : 0,
    row_count: Number.isSafeInteger(value.row_count) ? value.row_count : 0,
    drawing_count: Number.isSafeInteger(value.drawing_count) ? value.drawing_count : 0,
    ...(normalizedRows.length ? {normalized_rows: normalizedRows} : {}),
    commercial_tool_profiles: boundedNumericObject(
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
    renderable_payload_model_identity: compactModelIdentity(
      value.renderable_payload_model_identity,
    ),
    renderable_node_count: Number.isSafeInteger(value.renderable_node_count)
      ? value.renderable_node_count
      : 0,
    renderable_element_count: Number.isSafeInteger(value.renderable_element_count)
      ? value.renderable_element_count
      : 0,
    renderable_segment_count: Number.isSafeInteger(value.renderable_segment_count)
      ? value.renderable_segment_count
      : 0,
    ingest_file_read: compactFileRead(value.ingest_file_read),
    renderable_payload_persisted: Boolean(renderablePayloadPersisted),
    normalized_rows_persisted: normalizedRows.length > 0,
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
    incoming_counts: compactKnownScalars(value.incoming_counts, INCOMING_COUNT_FIELDS),
    state_policy: normalizeText(value.state_policy),
    state_limits: compactKnownScalars(value.state_limits, RESOURCE_LIMIT_FIELDS),
    local_state_serialized_bytes: Number.isSafeInteger(value.local_state_serialized_bytes)
      ? value.local_state_serialized_bytes
      : 0,
    manifest: includePayload && isRecord(value.manifest) ? value.manifest : null,
    local_state: includePayload && isRecord(value.local_state) ? value.local_state : {},
    file_read: compactFileRead(value.file_read),
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
        includeNormalizedRows: true,
        renderablePayloadPersisted: false,
      },
    );
    degradedFields.push('lastIngestRenderablePayload');
    inspection = inspectViewerProjectBundleLocalState(candidate);
    if (inspection.valid) return result(candidate, inspection, degradedFields);
  }

  if (candidate.lastIngestPreview?.normalized_rows?.length) {
    candidate.lastIngestPreview = compactEvidenceIngestPreview(
      candidate.lastIngestPreview,
      {
        includeManifest: true,
        includeNormalizedRows: false,
        renderablePayloadPersisted: false,
      },
    );
    degradedFields.push('lastIngestPreview.normalized_rows');
    inspection = inspectViewerProjectBundleLocalState(candidate);
    if (inspection.valid) return result(candidate, inspection, degradedFields);
  }

  if (candidate.lastIngestPreview?.manifest) {
    candidate.lastIngestPreview = compactEvidenceIngestPreview(
      candidate.lastIngestPreview,
      {
        includeManifest: false,
        includeNormalizedRows: false,
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
    max_normalized_rows: VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS,
    max_preview_issues: VIEWER_LOCAL_OPS_MAX_PREVIEW_ISSUES,
    max_issue_flags: VIEWER_LOCAL_OPS_MAX_ISSUE_FLAGS,
    max_tool_profiles: VIEWER_LOCAL_OPS_MAX_TOOL_PROFILES,
  });
}
