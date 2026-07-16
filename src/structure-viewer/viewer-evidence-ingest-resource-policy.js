import {
  AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
} from './viewer-authoritative-payload-contract.js';

export const STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY = 'structure_viewer_evidence_ingest_budget_v1';
export const STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES = 64 * 1024 * 1024;
export const STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT = 10000;
export const STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT = AUTHORITATIVE_VIEWER_MAX_NODE_COUNT;
export const STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT = AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT;
export const STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT = 200000;

export class EvidenceIngestResourceLimitError extends Error {
  constructor(code, path, message) {
    super(`${code}@${path}: ${message}`);
    this.name = 'EvidenceIngestResourceLimitError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message) {
  throw new EvidenceIngestResourceLimitError(code, path, message);
}

function requireCount(value, path) {
  if (!Number.isInteger(value) || value < 0) {
    fail(
      'evidence_ingest_resource_count_invalid',
      path,
      'Evidence ingest resource counts must be non-negative integers.',
    );
  }
  return value;
}

export function measureUtf8Bytes(text, maxBytes = STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES) {
  if (typeof text !== 'string') {
    fail('evidence_ingest_text_type_invalid', '/text', 'Evidence ingest text must be a string.');
  }
  requireCount(maxBytes, '/limits/max_text_bytes');
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
    if (byteLength > maxBytes) {
      return {byteLength, limitExceeded: true, maxBytes};
    }
  }
  return {byteLength, limitExceeded: false, maxBytes};
}

export function validateEvidenceIngestText(text) {
  const measurement = measureUtf8Bytes(text);
  if (measurement.limitExceeded) {
    fail(
      'evidence_ingest_text_byte_limit_exceeded',
      '/text',
      `Evidence ingest text exceeds ${STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES} UTF-8 bytes under ${STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY}.`,
    );
  }
  return measurement;
}

export function validateEvidenceIngestFileMetadata(file = {}) {
  if (file === null || typeof file !== 'object' || Array.isArray(file)) {
    fail('evidence_ingest_file_metadata_invalid', '/file', 'File metadata must be an object.');
  }
  const size = requireCount(file.size, '/file/size');
  if (size > STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES) {
    fail(
      'evidence_ingest_file_byte_limit_exceeded',
      '/file/size',
      `Evidence ingest file size ${size} exceeds ${STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES} bytes under ${STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY}.`,
    );
  }
  return {
    allowed: true,
    name: String(file.name ?? ''),
    size,
    resourcePolicy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
  };
}

export function validateEvidenceIngestRowCount(rowCount, path = '/rows') {
  requireCount(rowCount, path);
  if (rowCount > STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT) {
    fail(
      'evidence_ingest_row_count_limit_exceeded',
      path,
      `Evidence ingest contains ${rowCount} rows; limit is ${STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT}.`,
    );
  }
  return rowCount;
}

export function validateEvidenceIngestRenderableCounts({
  nodeCount = 0,
  elementCount = 0,
  segmentCount = 0,
} = {}) {
  requireCount(nodeCount, '/nodes');
  requireCount(elementCount, '/elements');
  requireCount(segmentCount, '/segments');
  if (nodeCount > STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT) {
    fail(
      'evidence_ingest_node_count_limit_exceeded',
      '/nodes',
      `Evidence ingest contains ${nodeCount} nodes; limit is ${STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT}.`,
    );
  }
  if (elementCount > STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT) {
    fail(
      'evidence_ingest_element_count_limit_exceeded',
      '/elements',
      `Evidence ingest contains ${elementCount} elements; limit is ${STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT}.`,
    );
  }
  if (segmentCount > STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT) {
    fail(
      'evidence_ingest_segment_count_limit_exceeded',
      '/segments',
      `Evidence ingest contains ${segmentCount} segments; limit is ${STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT}.`,
    );
  }
  return {nodeCount, elementCount, segmentCount};
}

export function evidenceIngestResourceLimits() {
  return {
    policy: STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
    max_text_bytes: STRUCTURE_VIEWER_INGEST_MAX_TEXT_BYTES,
    max_rows: STRUCTURE_VIEWER_INGEST_MAX_ROW_COUNT,
    max_nodes: STRUCTURE_VIEWER_INGEST_MAX_NODE_COUNT,
    max_elements: STRUCTURE_VIEWER_INGEST_MAX_ELEMENT_COUNT,
    max_segments: STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT,
  };
}
