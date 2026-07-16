import {
  STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
  EvidenceIngestResourceLimitError,
  evidenceIngestResourceLimits,
  validateEvidenceIngestFileMetadata,
  validateEvidenceIngestText,
} from './viewer-evidence-ingest-resource-policy.js';

export const STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT = 'structure_viewer_evidence_file_read_v1';

export class EvidenceIngestFileReadError extends Error {
  constructor(code, path, message, options = undefined) {
    super(`${code}@${path}: ${message}`, options);
    this.name = 'EvidenceIngestFileReadError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message, cause = undefined) {
  const options = cause === undefined ? undefined : {cause};
  throw new EvidenceIngestFileReadError(code, path, message, options);
}

function normalizeToken(value, fallback = '') {
  const token = String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return token || fallback;
}

export async function readEvidenceIngestFileText(file) {
  const metadata = validateEvidenceIngestFileMetadata(file);
  if (typeof file.text !== 'function') {
    fail(
      'evidence_ingest_file_text_reader_missing',
      '/file/text',
      'Evidence ingest file must provide an asynchronous text() reader.',
    );
  }

  let text;
  try {
    text = await file.text();
  } catch (error) {
    fail(
      'evidence_ingest_file_read_failed',
      '/file/text',
      'Evidence ingest file text read failed.',
      error,
    );
  }
  const measurement = validateEvidenceIngestText(text);
  return Object.freeze({
    contract: STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT,
    resourcePolicy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
    name: metadata.name,
    size: metadata.size,
    type: String(file.type ?? ''),
    lastModified: Number.isSafeInteger(file.lastModified) && file.lastModified >= 0
      ? file.lastModified
      : null,
    textByteLength: measurement.byteLength,
    text,
  });
}

export function evidenceIngestFileReadMetadata(receipt) {
  if (
    receipt === null
    || typeof receipt !== 'object'
    || Array.isArray(receipt)
    || receipt.contract !== STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT
    || receipt.resourcePolicy !== STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY
  ) {
    fail(
      'evidence_ingest_file_read_receipt_invalid',
      '/file_read',
      'Expected a current Viewer evidence file-read receipt.',
    );
  }
  return Object.freeze({
    contract: receipt.contract,
    resource_policy: receipt.resourcePolicy,
    file_name: String(receipt.name ?? ''),
    file_size: Number.isSafeInteger(receipt.size) ? receipt.size : null,
    file_type: String(receipt.type ?? ''),
    last_modified: Number.isSafeInteger(receipt.lastModified)
      ? receipt.lastModified
      : null,
    text_byte_length: Number.isSafeInteger(receipt.textByteLength)
      ? receipt.textByteLength
      : null,
  });
}

export function buildEvidenceIngestFileReadFailurePreview(error, {
  sourceType = 'unknown',
  sourceName = '',
  drawingId = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const isResourceLimit = error instanceof EvidenceIngestResourceLimitError;
  const isReadFailure = error instanceof EvidenceIngestFileReadError;
  const fallbackCode = isResourceLimit
    ? 'evidence_ingest_resource_limit'
    : isReadFailure
      ? 'evidence_ingest_file_read_failed'
      : 'evidence_ingest_file_preview_failed';
  const code = normalizeToken(error?.code, fallbackCode);
  const path = typeof error?.path === 'string' && error.path.startsWith('/')
    ? error.path
    : '/file';
  const normalizedSourceType = normalizeToken(sourceType, 'unknown');
  const normalizedSourceName = String(sourceName ?? '').trim();
  const issue = isResourceLimit
    ? 'evidence ingest file resource limit'
    : isReadFailure
      ? 'evidence ingest file read failed'
      : 'evidence ingest file preview failed';

  return Object.freeze({
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: normalizedSourceType,
    generated_at: generatedAt,
    resource_policy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
    resource_limits: evidenceIngestResourceLimits(),
    ingest_text_byte_count: 0,
    row_count: 0,
    drawing_count: 0,
    normalized_rows: [],
    commercial_tool_profiles: {},
    crosswalk_candidate_count: 0,
    blocked_issues: [{
      drawing_id: String(drawingId ?? ''),
      issue,
      quality_flags: [code, path],
    }],
    renderable_payload_available: false,
    renderable_payload_kind: '',
    renderable_payload_validation_status: isResourceLimit
      ? 'blocked_resource_limit'
      : 'unavailable',
    renderable_payload_error_code: code,
    renderable_payload_error_path: path,
    renderable_payload_model_identity: null,
    renderable_node_count: 0,
    renderable_element_count: 0,
    renderable_segment_count: 0,
    ingest_file_read: Object.freeze({
      contract: STRUCTURE_VIEWER_INGEST_FILE_READ_CONTRACT,
      resource_policy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
      file_name: normalizedSourceName,
      status: 'blocked',
      error_code: code,
      error_path: path,
    }),
    manifest: {
      schema_version: 'structure-viewer-project-manifest.v1',
      generated_at: generatedAt,
      projects: [],
    },
  });
}
