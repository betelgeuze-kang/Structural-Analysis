export const VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT = 'structure_viewer_project_bundle_file_read_v1';
export const VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY = 'structure_viewer_project_bundle_budget_v1';
export const VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES = 16 * 1024 * 1024;

export class ViewerProjectBundleFileError extends Error {
  constructor(code, path, message, options = undefined) {
    super(`${code}@${path}: ${message}`, options);
    this.name = 'ViewerProjectBundleFileError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message, cause = undefined) {
  const options = cause === undefined ? undefined : {cause};
  throw new ViewerProjectBundleFileError(code, path, message, options);
}

function requireFileMetadata(file) {
  if (file === null || typeof file !== 'object' || Array.isArray(file)) {
    fail(
      'project_bundle_file_metadata_invalid',
      '/file',
      'Project bundle file metadata must be an object.',
    );
  }
  if (!Number.isSafeInteger(file.size) || file.size < 0) {
    fail(
      'project_bundle_file_size_invalid',
      '/file/size',
      'Project bundle file size must be a non-negative safe integer.',
    );
  }
  if (file.size > VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES) {
    fail(
      'project_bundle_file_byte_limit_exceeded',
      '/file/size',
      `Project bundle file size ${file.size} exceeds ${VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES} bytes under ${VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY}.`,
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

function measureUtf8Bytes(text, maxBytes = VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES) {
  if (typeof text !== 'string') {
    fail(
      'project_bundle_text_type_invalid',
      '/text',
      'Project bundle text reader must return a string.',
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
        'project_bundle_text_byte_limit_exceeded',
        '/text',
        `Decoded project bundle exceeds ${VIEWER_PROJECT_BUNDLE_MAX_TEXT_BYTES} UTF-8 bytes under ${VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY}.`,
      );
    }
  }
  return byteLength;
}

export async function readViewerProjectBundleFile(file) {
  const metadata = requireFileMetadata(file);
  if (typeof file.text !== 'function') {
    fail(
      'project_bundle_file_text_reader_missing',
      '/file/text',
      'Project bundle file must provide an asynchronous text() reader.',
    );
  }

  let text;
  try {
    text = await file.text();
  } catch (error) {
    fail(
      'project_bundle_file_read_failed',
      '/file/text',
      'Project bundle file text read failed.',
      error,
    );
  }
  const textByteLength = measureUtf8Bytes(text);

  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    fail(
      'project_bundle_json_parse_failed',
      '/',
      'Project bundle must contain valid JSON.',
      error,
    );
  }
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    fail(
      'project_bundle_json_object_required',
      '/',
      'Project bundle JSON root must be an object.',
    );
  }

  return Object.freeze({
    contract: VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT,
    resourcePolicy: VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY,
    name: metadata.name,
    size: metadata.size,
    type: metadata.type,
    lastModified: metadata.lastModified,
    textByteLength,
    payload,
  });
}

export function viewerProjectBundleFileMetadata(receipt) {
  if (
    receipt === null
    || typeof receipt !== 'object'
    || Array.isArray(receipt)
    || receipt.contract !== VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT
    || receipt.resourcePolicy !== VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY
  ) {
    fail(
      'project_bundle_file_read_receipt_invalid',
      '/file_read',
      'Expected a current project-bundle file-read receipt.',
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

export function buildViewerProjectBundleFileFailurePreview(error, {
  sourceName = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const code = typeof error?.code === 'string' && error.code.trim()
    ? error.code.trim()
    : 'project_bundle_preview_failed';
  const path = typeof error?.path === 'string' && error.path.startsWith('/')
    ? error.path
    : '/file';
  const fileName = String(sourceName ?? '').trim();
  return Object.freeze({
    schema_version: 'structure-viewer-project-bundle-import-preview.v1',
    source_schema_version: '',
    project_id: '',
    drawing_id: '',
    variant: '',
    blocked: true,
    issues: [{
      severity: 'critical',
      issue: 'project bundle file preview blocked',
      value: `${code}@${path}`,
    }],
    incoming_counts: {
      recentSelections: 0,
      exportHistory: 0,
      reviewTasks: 0,
      annotations: 0,
      receiptIndex: 0,
    },
    manifest: null,
    local_state: null,
    generated_at: generatedAt,
    file_read: Object.freeze({
      contract: VIEWER_PROJECT_BUNDLE_FILE_READ_CONTRACT,
      resource_policy: VIEWER_PROJECT_BUNDLE_RESOURCE_POLICY,
      file_name: fileName,
      status: 'blocked',
      error_code: code,
      error_path: path,
    }),
  });
}
