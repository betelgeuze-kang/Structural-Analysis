import {
  STRUCTURE_VIEWER_INGEST_RESOURCE_POLICY,
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
