import {
  buildProjectManifestFromRows,
} from './viewer-project-workspace.js';
import {
  inferCommercialToolProfile,
} from './viewer-commercial-tool-crosswalk-model.js';
import {
  AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
  AuthoritativeViewerPayloadValidationError,
  claimsAuthoritativeViewerContract,
  validateAuthoritativeViewerPayload,
} from './viewer-authoritative-payload-contract.js';

export const STRUCTURE_VIEWER_INGEST_PREVIEW_SCHEMA_VERSION = 'structure-viewer-evidence-ingest-preview.v1';
export const STRUCTURE_VIEWER_RENDERABLE_INSPECTION_SCHEMA_VERSION = 'structure-viewer-renderable-ingest-inspection.v1';

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function firstText(...values) {
  return values.map(normalizeText).find(Boolean) || '';
}

function resolveEvidenceSourceType(sourceType = '', text = '', sourceName = '') {
  const requested = normalizeToken(sourceType);
  if (requested && requested !== 'auto') return requested;
  const name = normalizeText(sourceName).toLowerCase();
  if (name.endsWith('.csv')) return 'csv';
  if (name.endsWith('.ifc')) return 'ifc';
  if (name.endsWith('.json')) return 'json';
  const body = normalizeText(text);
  if (body.startsWith('{') || body.startsWith('[')) return 'json';
  if (/^(ISO-10303-21;|#\d+=IFC)/i.test(body)) return 'ifc';
  if (body.includes(',') && body.includes('\n')) return 'csv';
  return 'json';
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseCsvRows(text = '') {
  const lines = normalizeText(text).split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const headers = lines[0].split(',').map((header) => normalizeToken(header));
  return lines.slice(1).map((line) => {
    const cells = line.split(',');
    return Object.fromEntries(headers.map((header, index) => [header, normalizeText(cells[index])]));
  });
}

function parseJsonDocument(text = '') {
  try {
    return {
      parsed: true,
      value: JSON.parse(text),
      errorCode: '',
      errorPath: '',
    };
  } catch (_error) {
    return {
      parsed: false,
      value: null,
      errorCode: 'json_parse_failed',
      errorPath: '/',
    };
  }
}

function selectJsonRows(value) {
  let rows = [];
  let pathPrefix = '';
  if (Array.isArray(value)) rows = value;
  else if (isRecord(value) && Array.isArray(value.rows)) {
    rows = value.rows;
    pathPrefix = '/rows';
  } else if (isRecord(value) && Array.isArray(value.drawings)) {
    rows = value.drawings;
    pathPrefix = '/drawings';
  } else if (isRecord(value)) rows = [value];
  else {
    return {
      valid: false,
      rows: [],
      errorCode: 'json_object_required',
      errorPath: '/',
    };
  }
  const invalidIndex = rows.findIndex((row) => !isRecord(row));
  if (invalidIndex >= 0) {
    return {
      valid: false,
      rows: [],
      errorCode: 'json_row_object_required',
      errorPath: `${pathPrefix}/${invalidIndex}` || '/',
    };
  }
  return {
    valid: true,
    rows,
    errorCode: '',
    errorPath: '',
  };
}

function resolveRenderablePayloadKind(payload = null) {
  if (!payload || typeof payload !== 'object') return '';
  const model = payload.model && typeof payload.model === 'object' ? payload.model : payload;
  if (Array.isArray(model.nodes) && Array.isArray(model.elements)) return 'direct_model';
  const interactive = payload.interactive_3d && typeof payload.interactive_3d === 'object'
    ? payload.interactive_3d
    : payload.interactive_3d_payload && typeof payload.interactive_3d_payload === 'object'
      ? payload.interactive_3d_payload
      : payload;
  if (Array.isArray(interactive.baseline_segments) || Array.isArray(interactive.after_segments)) return 'interactive_3d';
  return '';
}

function countRenderablePayload(payload = null, kind = '') {
  if (!payload || typeof payload !== 'object') return { nodeCount: 0, elementCount: 0, segmentCount: 0 };
  if (kind === 'direct_model' || kind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND) {
    const model = payload.model && typeof payload.model === 'object' ? payload.model : payload;
    return {
      nodeCount: Array.isArray(model.nodes) ? model.nodes.length : 0,
      elementCount: Array.isArray(model.elements) ? model.elements.length : 0,
      segmentCount: 0,
    };
  }
  const interactive = payload.interactive_3d && typeof payload.interactive_3d === 'object'
    ? payload.interactive_3d
    : payload.interactive_3d_payload && typeof payload.interactive_3d_payload === 'object'
      ? payload.interactive_3d_payload
      : payload;
  return {
    nodeCount: 0,
    elementCount: 0,
    segmentCount: (Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.length : 0)
      + (Array.isArray(interactive.after_segments) ? interactive.after_segments.length : 0),
  };
}

function inspectionEnvelope({
  sourceType,
  sourceName,
  generatedAt,
  available = false,
  payloadKind = '',
  validationStatus = 'unavailable',
  validationErrorCode = '',
  validationErrorPath = '',
  payload = null,
} = {}) {
  const counts = countRenderablePayload(payload, payloadKind);
  return {
    schema_version: STRUCTURE_VIEWER_RENDERABLE_INSPECTION_SCHEMA_VERSION,
    source_type: normalizeToken(sourceType) || 'json',
    source_name: normalizeText(sourceName) || 'browser-json-ingest',
    generated_at: generatedAt,
    available: Boolean(available),
    payload_kind: payloadKind,
    validation_status: validationStatus,
    validation_error_code: validationErrorCode,
    validation_error_path: validationErrorPath,
    node_count: counts.nodeCount,
    element_count: counts.elementCount,
    segment_count: counts.segmentCount,
    model_identity: payloadKind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND
      && payload?.model_identity && typeof payload.model_identity === 'object'
      ? { ...payload.model_identity }
      : null,
    payload: available ? payload : null,
  };
}

export function inspectRenderableEvidencePayloadFromText(text = '', {
  sourceType = 'json',
  sourceName = '',
  generatedAt = '2026-05-17T00:00:00Z',
} = {}) {
  const normalizedSourceType = resolveEvidenceSourceType(sourceType, text, sourceName);
  if (normalizedSourceType !== 'json') {
    return inspectionEnvelope({
      sourceType: normalizedSourceType,
      sourceName,
      generatedAt,
      validationStatus: 'not_json',
    });
  }
  const document = parseJsonDocument(text);
  if (!document.parsed) {
    return inspectionEnvelope({
      sourceType: normalizedSourceType,
      sourceName,
      generatedAt,
      validationStatus: 'unavailable',
      validationErrorCode: document.errorCode,
      validationErrorPath: document.errorPath,
    });
  }
  const payload = document.value;
  if (!payload || typeof payload !== 'object') {
    return inspectionEnvelope({
      sourceType: normalizedSourceType,
      sourceName,
      generatedAt,
      validationStatus: 'unavailable',
      validationErrorCode: 'json_object_required',
      validationErrorPath: '/',
    });
  }
  if (claimsAuthoritativeViewerContract(payload)) {
    try {
      validateAuthoritativeViewerPayload(payload);
      return inspectionEnvelope({
        sourceType: normalizedSourceType,
        sourceName,
        generatedAt,
        available: true,
        payloadKind: AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
        validationStatus: 'validated_authoritative_contract',
        payload,
      });
    } catch (error) {
      if (!(error instanceof AuthoritativeViewerPayloadValidationError)) throw error;
      return inspectionEnvelope({
        sourceType: normalizedSourceType,
        sourceName,
        generatedAt,
        payloadKind: AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
        validationStatus: 'blocked_authoritative_contract',
        validationErrorCode: error.code,
        validationErrorPath: error.path,
      });
    }
  }
  const kind = resolveRenderablePayloadKind(payload);
  if (!kind) {
    return inspectionEnvelope({
      sourceType: normalizedSourceType,
      sourceName,
      generatedAt,
      validationStatus: 'unavailable',
      validationErrorCode: 'renderable_payload_shape_not_found',
      validationErrorPath: '/',
    });
  }
  return inspectionEnvelope({
    sourceType: normalizedSourceType,
    sourceName,
    generatedAt,
    available: true,
    payloadKind: kind,
    validationStatus: 'basic_shape_only',
    payload,
  });
}

export function extractRenderableEvidencePayloadFromText(text = '', options = {}) {
  const inspection = inspectRenderableEvidencePayloadFromText(text, options);
  if (!inspection.available || !inspection.payload) return null;
  return {
    schema_version: 'structure-viewer-renderable-ingest-payload.v1',
    source_type: inspection.source_type,
    source_name: inspection.source_name,
    generated_at: inspection.generated_at,
    payload_kind: inspection.payload_kind,
    validation_status: inspection.validation_status,
    validation_error_code: '',
    validation_error_path: '',
    node_count: inspection.node_count,
    element_count: inspection.element_count,
    segment_count: inspection.segment_count,
    model_identity: inspection.model_identity,
    payload: inspection.payload,
  };
}

function buildIfcMetadataRow(text = '', {
  drawingId = 'ifc_ingest',
  artifactPath = '',
} = {}) {
  const body = normalizeText(text);
  const memberMatches = body.match(/IFC(BEAM|COLUMN|MEMBER|BUILDINGELEMENTPROXY)/gi) || [];
  const pointMatches = body.match(/IFCCARTESIANPOINT/gi) || [];
  return {
    drawing_id: drawingId,
    drawing_title: 'IFC metadata ingest',
    source_family: 'ifc',
    artifact_path: artifactPath || 'inline.ifc',
    member_count: memberMatches.length,
    node_count: pointMatches.length,
    element_count: memberMatches.length,
    load_model_status: 'source_ifc_load_model_missing',
    evidence_level: 'ifc metadata summary',
  };
}

function buildAuthoritativeViewerMetadataRow(inspection, {
  projectId = 'ingested_project',
  artifactPath = '',
} = {}) {
  const identity = inspection.model_identity && typeof inspection.model_identity === 'object'
    ? inspection.model_identity
    : {};
  const sourcePath = normalizeText(artifactPath) || inspection.source_name || 'browser-json-ingest';
  return {
    project_id: normalizeToken(projectId),
    drawing_id: `${normalizeToken(projectId) || 'ingested_project'}_authoritative_viewer`,
    drawing_title: 'Validated authoritative Viewer payload',
    source_family: AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
    source_tool: 'Structural Analysis authoritative CPU solver',
    source_tool_profile: 'generic',
    artifact_path: sourcePath,
    member_count: inspection.element_count,
    node_count: inspection.node_count,
    element_count: inspection.element_count,
    load_model_status: 'authoritative_viewer_payload_validated',
    evidence_level: 'validated authoritative Viewer contract',
    quality_flags: [
      'authoritative_viewer_contract_validated',
      'engineer_review_required',
    ],
    commercial_review_status: 'needs_review',
    provenance: {
      source_path: sourcePath,
      evidence_level: 'validated authoritative Viewer contract',
      identity_policy: normalizeText(identity.identity_policy),
      source_input_checksum: normalizeText(identity.source_input_checksum),
      canonical_model_checksum: normalizeText(identity.canonical_model_checksum),
      analysis_input_snapshot: normalizeText(identity.analysis_input_snapshot),
    },
    ingest_summary: {
      status: 'validated authoritative Viewer contract',
      payload_kind: inspection.payload_kind,
      validation_status: inspection.validation_status,
      node_count: inspection.node_count,
      element_count: inspection.element_count,
      model_identity: identity,
      preview_only: true,
    },
  };
}

function buildBlockedEvidenceMetadataRow(inspection, {
  projectId = 'ingested_project',
  artifactPath = '',
} = {}) {
  const normalizedProjectId = normalizeToken(projectId) || 'ingested_project';
  const sourcePath = normalizeText(artifactPath) || inspection.source_name || 'browser-evidence-ingest';
  const errorCode = normalizeToken(inspection.validation_error_code) || 'evidence_ingest_blocked';
  const errorPath = normalizeText(inspection.validation_error_path) || '/';
  const authoritative = inspection.payload_kind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND;
  return {
    project_id: normalizedProjectId,
    drawing_id: `${normalizedProjectId}_${authoritative ? 'blocked_authoritative_viewer' : 'blocked_json_ingest'}`,
    drawing_title: authoritative ? 'Blocked authoritative Viewer payload' : 'Blocked JSON evidence ingest',
    source_family: authoritative ? AUTHORITATIVE_VIEWER_PAYLOAD_KIND : 'json_blocked_ingest',
    source_tool: authoritative ? 'Structural Analysis authoritative CPU solver' : 'Browser JSON ingest',
    source_tool_profile: 'generic',
    artifact_path: sourcePath,
    member_count: 0,
    node_count: 0,
    element_count: 0,
    load_model_status: errorCode,
    evidence_level: 'blocked evidence ingest',
    quality_flags: [
      'evidence_ingest_blocked',
      errorCode,
    ],
    commercial_review_status: 'blocked',
    provenance: {
      source_path: sourcePath,
      evidence_level: 'blocked evidence ingest',
    },
    ingest_summary: {
      status: 'blocked evidence ingest',
      payload_kind: inspection.payload_kind,
      validation_status: inspection.validation_status,
      validation_error_code: errorCode,
      validation_error_path: errorPath,
      preview_only: true,
    },
  };
}

export function normalizeEvidenceIngestRow(row = {}, {
  sourceType = '',
  projectId = '',
  drawingId = '',
} = {}) {
  const type = normalizeToken(sourceType || row.source_type || row.format || row.input_format) || 'json';
  const sourceTool = firstText(
    row.source_tool,
    row.tool,
    row.program,
    row.analysis_program,
    row.application,
    row.source_family,
    type,
  );
  const sourceToolProfile = inferCommercialToolProfile(firstText(
    row.source_tool_profile,
    row.source_profile,
    row.source_tool,
    row.tool,
    row.program,
    row.application,
    row.source_family,
    type,
  ));
  const memberId = firstText(
    row.member_id,
    row.memberId,
    row.external_member_id,
    row.source_member_id,
    row.frame,
    row.frame_id,
    row.object_id,
    row.unique_name,
    row.element_id,
    row.guid,
    row.global_id,
    row.globalid,
    row.label,
    row.id,
  );
  const receiptPath = normalizeText(row.receipt_path || row.receiptPath);
  const normalized = {
    ...row,
    project_id: normalizeToken(row.project_id || row.projectId || projectId),
    drawing_id: normalizeToken(row.drawing_id || row.drawingId || drawingId || row.case_id || row.name),
    drawing_title: normalizeText(row.drawing_title || row.title || row.name),
    source_family: normalizeText(row.source_family || row.sourceFamily || type),
    source_tool: sourceTool,
    source_tool_profile: sourceToolProfile,
    external_member_id: memberId,
    source_member_id: firstText(row.source_member_id, row.sourceMemberId, row.unique_name, row.guid, row.global_id, row.globalid),
    story: firstText(row.story, row.level, row.storey),
    section: firstText(row.section, row.section_name, row.frame_section, row.property, row.profile, row.profile_name, row.family_type, row.type_name),
    material: firstText(row.material, row.material_name, row.material_id),
    artifact_path: normalizeText(row.artifact_path || row.path || row.source_path),
    member_count: row.member_count ?? row.members ?? row.memberCount,
    node_count: row.node_count ?? row.nodes ?? row.nodeCount,
    element_count: row.element_count ?? row.elements ?? row.elementCount,
    load_model_status: normalizeText(row.load_model_status || row.loadStatus),
    evidence_level: normalizeText(row.evidence_level || row.evidenceLevel) || `${type} ingest`,
  };
  if (memberId || receiptPath) {
    normalized.solver_receipts = [{
      project_id: normalized.project_id,
      drawing_id: normalized.drawing_id,
      member_id: memberId,
      source_tool: sourceTool,
      source_tool_profile: sourceToolProfile,
      load_combo: normalizeText(row.load_combo || row.combination),
      dcr_before: row.dcr_before ?? row.max_dcr_before,
      dcr_after: row.dcr_after ?? row.max_dcr_after ?? row.dcr,
      governing_constraint: normalizeText(row.governing_constraint || row.constraint),
      status: normalizeText(row.status || row.receipt_status || (receiptPath ? 'verified' : 'pending')),
      receipt_path: receiptPath,
      evidence_level: normalizeText(row.receipt_evidence_level || row.evidence_level) || `${type} result row`,
    }];
  }
  return normalized;
}

export function buildEvidenceIngestPreview({
  rows = [],
  sourceType = 'json',
  projectId = 'ingested_project',
  projectTitle = 'Ingested Evidence Project',
  generatedAt = '2026-05-17T00:00:00Z',
} = {}) {
  const normalizedRows = (Array.isArray(rows) ? rows : []).map((row, index) => normalizeEvidenceIngestRow(row, {
    sourceType,
    projectId,
    drawingId: row?.drawing_id || row?.drawingId || `ingest_${index + 1}`,
  }));
  const manifest = buildProjectManifestFromRows(normalizedRows, {
    project_id: projectId,
    project_title: projectTitle,
    generated_at: generatedAt,
  });
  const drawings = manifest.projects?.[0]?.drawings || [];
  const blockedIssues = drawings.flatMap((drawing) => (
    drawing.commercial_review_status === 'blocked'
      ? [{ drawing_id: drawing.drawing_id, issue: 'blocked quality status', quality_flags: drawing.quality_flags }]
      : []
  ));
  const profileCounts = normalizedRows.reduce((acc, row) => {
    const profile = normalizeToken(row.source_tool_profile) || 'generic';
    acc[profile] = (acc[profile] || 0) + 1;
    return acc;
  }, {});
  const resultRows = normalizedRows.filter((row) => normalizeText(row.external_member_id || row.member_id || row.receipt_path));
  return {
    schema_version: STRUCTURE_VIEWER_INGEST_PREVIEW_SCHEMA_VERSION,
    source_type: normalizeToken(sourceType) || 'json',
    generated_at: generatedAt,
    row_count: normalizedRows.length,
    drawing_count: drawings.length,
    normalized_rows: normalizedRows.slice(0, 1000),
    commercial_tool_profiles: profileCounts,
    crosswalk_candidate_count: resultRows.length,
    blocked_issues: blockedIssues,
    manifest,
  };
}

export function buildEvidenceIngestPreviewFromText(text = '', {
  sourceType = 'json',
  projectId = 'ingested_project',
  projectTitle = 'Ingested Evidence Project',
  artifactPath = '',
  generatedAt = '2026-05-17T00:00:00Z',
} = {}) {
  const type = resolveEvidenceSourceType(sourceType, text, artifactPath);
  const inspection = inspectRenderableEvidencePayloadFromText(text, {
    sourceType: type,
    sourceName: artifactPath,
    generatedAt,
  });
  const jsonDocument = type === 'json' ? parseJsonDocument(text) : null;
  const jsonRows = jsonDocument?.parsed ? selectJsonRows(jsonDocument.value) : null;
  let effectiveInspection = inspection;
  if (
    type === 'json'
    && jsonDocument?.parsed
    && jsonDocument.value
    && typeof jsonDocument.value === 'object'
    && inspection.validation_status !== 'blocked_authoritative_contract'
    && jsonRows
    && !jsonRows.valid
  ) {
    effectiveInspection = {
      ...inspection,
      validation_status: 'unavailable',
      validation_error_code: jsonRows.errorCode,
      validation_error_path: jsonRows.errorPath,
    };
  }
  let rows = [];
  if (type === 'csv') rows = parseCsvRows(text);
  else if (type === 'ifc') rows = [buildIfcMetadataRow(text, { drawingId: projectId, artifactPath })];
  else if (
    effectiveInspection.available
    && effectiveInspection.payload_kind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND
    && effectiveInspection.validation_status === 'validated_authoritative_contract'
  ) {
    rows = [buildAuthoritativeViewerMetadataRow(effectiveInspection, { projectId, artifactPath })];
  } else if (
    !jsonDocument?.parsed
    || !jsonRows?.valid
    || (
      effectiveInspection.payload_kind === AUTHORITATIVE_VIEWER_PAYLOAD_KIND
      && effectiveInspection.validation_status === 'blocked_authoritative_contract'
    )
  ) {
    rows = [buildBlockedEvidenceMetadataRow(effectiveInspection, { projectId, artifactPath })];
  } else rows = jsonRows.rows;
  const preview = buildEvidenceIngestPreview({
    rows,
    sourceType: type,
    projectId,
    projectTitle,
    generatedAt,
  });
  return {
    ...preview,
    renderable_payload_available: effectiveInspection.available,
    renderable_payload_kind: effectiveInspection.payload_kind,
    renderable_payload_validation_status: effectiveInspection.validation_status,
    renderable_payload_error_code: effectiveInspection.validation_error_code,
    renderable_payload_error_path: effectiveInspection.validation_error_path,
    renderable_payload_model_identity: effectiveInspection.model_identity,
    renderable_node_count: effectiveInspection.node_count,
    renderable_element_count: effectiveInspection.element_count,
    renderable_segment_count: effectiveInspection.segment_count,
  };
}
