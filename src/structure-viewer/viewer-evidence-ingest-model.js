import {
  buildProjectManifestFromRows,
} from './viewer-project-workspace.js';
import {
  inferCommercialToolProfile,
} from './viewer-commercial-tool-crosswalk-model.js';
import {
  AUTHORITATIVE_VIEWER_PAYLOAD_KIND,
  AUTHORITATIVE_VIEWER_SCHEMA_VERSION,
  AuthoritativeViewerPayloadValidationError,
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

function parseCsvRows(text = '') {
  const lines = normalizeText(text).split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const headers = lines[0].split(',').map((header) => normalizeToken(header));
  return lines.slice(1).map((line) => {
    const cells = line.split(',');
    return Object.fromEntries(headers.map((header, index) => [header, normalizeText(cells[index])]));
  });
}

function parseJsonRows(text = '') {
  const parsed = JSON.parse(text);
  if (Array.isArray(parsed)) return parsed;
  if (Array.isArray(parsed.rows)) return parsed.rows;
  if (Array.isArray(parsed.drawings)) return parsed.drawings;
  if (parsed && typeof parsed === 'object') return [parsed];
  return [];
}

function parseJsonValue(text = '') {
  try {
    return JSON.parse(text);
  } catch (_err) {
    return null;
  }
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
  const normalizedSourceType = normalizeToken(sourceType);
  if (normalizedSourceType !== 'json') {
    return inspectionEnvelope({
      sourceType: normalizedSourceType,
      sourceName,
      generatedAt,
      validationStatus: 'not_json',
    });
  }
  const payload = parseJsonValue(text);
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
  if (payload.schema_version === AUTHORITATIVE_VIEWER_SCHEMA_VERSION) {
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
  const type = normalizeToken(sourceType);
  let rows = [];
  if (type === 'csv') rows = parseCsvRows(text);
  else if (type === 'ifc') rows = [buildIfcMetadataRow(text, { drawingId: projectId, artifactPath })];
  else rows = parseJsonRows(text);
  const preview = buildEvidenceIngestPreview({
    rows,
    sourceType: type || 'json',
    projectId,
    projectTitle,
    generatedAt,
  });
  const inspection = inspectRenderableEvidencePayloadFromText(text, {
    sourceType: type || 'json',
    sourceName: artifactPath,
    generatedAt,
  });
  return {
    ...preview,
    renderable_payload_available: inspection.available,
    renderable_payload_kind: inspection.payload_kind,
    renderable_payload_validation_status: inspection.validation_status,
    renderable_payload_error_code: inspection.validation_error_code,
    renderable_payload_error_path: inspection.validation_error_path,
    renderable_payload_model_identity: inspection.model_identity,
    renderable_node_count: inspection.node_count,
    renderable_element_count: inspection.element_count,
    renderable_segment_count: inspection.segment_count,
  };
}
