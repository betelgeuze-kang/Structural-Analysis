export const VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT = 'structure_viewer_local_model_file_read_v1';
export const VIEWER_LOCAL_MODEL_RESOURCE_POLICY = 'structure_viewer_local_model_file_budget_v1';
export const VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES = 64 * 1024 * 1024;

export class ViewerLocalModelFileError extends Error {
  constructor(code, path, message, options = undefined) {
    super(`${code}@${path}: ${message}`, options);
    this.name = 'ViewerLocalModelFileError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message, cause = undefined) {
  const options = cause === undefined ? undefined : {cause};
  throw new ViewerLocalModelFileError(code, path, message, options);
}

function requireFileMetadata(file) {
  if (file === null || typeof file !== 'object' || Array.isArray(file)) {
    fail(
      'local_model_file_metadata_invalid',
      '/file',
      'Local model file metadata must be an object.',
    );
  }
  if (!Number.isSafeInteger(file.size) || file.size < 0) {
    fail(
      'local_model_file_size_invalid',
      '/file/size',
      'Local model file size must be a non-negative safe integer.',
    );
  }
  if (file.size > VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES) {
    fail(
      'local_model_file_byte_limit_exceeded',
      '/file/size',
      `Local model file size ${file.size} exceeds ${VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES} bytes under ${VIEWER_LOCAL_MODEL_RESOURCE_POLICY}.`,
    );
  }
  return {
    name: String(file.name ?? ''),
    size: file.size,
    type: String(file.type ?? ''),
    lastModified: Number.isSafeInteger(file.lastModified) && file.lastModified >= 0
      ? file.lastModified
      : null,
  };
}

function measureUtf8Bytes(text, maxBytes = VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES) {
  if (typeof text !== 'string') {
    fail(
      'local_model_text_type_invalid',
      '/text',
      'Local model text reader must return a string.',
    );
  }
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
      fail(
        'local_model_text_byte_limit_exceeded',
        '/text',
        `Decoded local model exceeds ${VIEWER_LOCAL_MODEL_MAX_TEXT_BYTES} UTF-8 bytes under ${VIEWER_LOCAL_MODEL_RESOURCE_POLICY}.`,
      );
    }
  }
  return byteLength;
}

export async function readViewerLocalModelFile(file) {
  const metadata = requireFileMetadata(file);
  if (typeof file.text !== 'function') {
    fail(
      'local_model_file_text_reader_missing',
      '/file/text',
      'Local model file must provide an asynchronous text() reader.',
    );
  }

  let text;
  try {
    text = await file.text();
  } catch (error) {
    fail(
      'local_model_file_read_failed',
      '/file/text',
      'Local model file text read failed.',
      error,
    );
  }
  const textByteLength = measureUtf8Bytes(text);

  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    fail(
      'local_model_json_parse_failed',
      '/',
      'Local model file must contain valid JSON.',
      error,
    );
  }
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    fail(
      'local_model_json_object_required',
      '/',
      'Local model JSON root must be an object.',
    );
  }

  return Object.freeze({
    contract: VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT,
    resourcePolicy: VIEWER_LOCAL_MODEL_RESOURCE_POLICY,
    name: metadata.name,
    size: metadata.size,
    type: metadata.type,
    lastModified: metadata.lastModified,
    textByteLength,
    payload,
  });
}

export function viewerLocalModelFileMetadata(receipt) {
  if (
    receipt === null
    || typeof receipt !== 'object'
    || Array.isArray(receipt)
    || receipt.contract !== VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT
    || receipt.resourcePolicy !== VIEWER_LOCAL_MODEL_RESOURCE_POLICY
  ) {
    fail(
      'local_model_file_read_receipt_invalid',
      '/file_read',
      'Expected a current local-model file-read receipt.',
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

export function viewerLocalModelFileFailure(error, {
  sourceName = '',
} = {}) {
  const code = typeof error?.code === 'string' && error.code.trim()
    ? error.code.trim()
    : 'local_model_file_load_failed';
  const path = typeof error?.path === 'string' && error.path.startsWith('/')
    ? error.path
    : '/file';
  return Object.freeze({
    contract: VIEWER_LOCAL_MODEL_FILE_READ_CONTRACT,
    resource_policy: VIEWER_LOCAL_MODEL_RESOURCE_POLICY,
    file_name: String(sourceName ?? '').trim(),
    status: 'blocked',
    error_code: code,
    error_path: path,
  });
}
