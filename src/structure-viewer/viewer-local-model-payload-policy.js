import {
  AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT,
  AUTHORITATIVE_VIEWER_MAX_NODE_COUNT,
} from './viewer-authoritative-payload-contract.js';
import {
  STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT,
} from './viewer-evidence-ingest-resource-policy.js';

export const VIEWER_LOCAL_MODEL_OBJECT_POLICY = 'structure_viewer_local_model_object_budget_v1';
export const VIEWER_LOCAL_MODEL_MAX_NODE_COUNT = AUTHORITATIVE_VIEWER_MAX_NODE_COUNT;
export const VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT = AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT;
export const VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT = STRUCTURE_VIEWER_INGEST_MAX_SEGMENT_COUNT;
export const VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH = 64;
export const VIEWER_LOCAL_MODEL_MAX_JSON_CONTAINERS = 1_000_000;

export class ViewerLocalModelPayloadError extends Error {
  constructor(code, path, detail) {
    super(`${code}@${path}: ${detail}`);
    this.name = 'ViewerLocalModelPayloadError';
    this.code = code;
    this.path = path;
    this.detail = detail;
  }
}

function fail(code, path, detail) {
  throw new ViewerLocalModelPayloadError(code, path, detail);
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireLimit(value, path) {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail(
      'local_model_resource_limit_invalid',
      path,
      'Local model resource limits must be non-negative safe integers.',
    );
  }
  return value;
}

function validateArrayCount(value, {
  path,
  limit,
  code,
  label,
}) {
  if (!Array.isArray(value)) return 0;
  if (value.length > limit) {
    fail(
      code,
      path,
      `${label} count ${value.length} exceeds ${limit} under ${VIEWER_LOCAL_MODEL_OBJECT_POLICY}.`,
    );
  }
  return value.length;
}

function childPath(basePath, field) {
  return `${basePath}/${field}` || `/${field}`;
}

export function inspectViewerLocalModelJsonStructure(text, {
  maxDepth = VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH,
  maxContainers = VIEWER_LOCAL_MODEL_MAX_JSON_CONTAINERS,
} = {}) {
  if (typeof text !== 'string') {
    fail(
      'local_model_json_structure_text_invalid',
      '/text',
      'Local model JSON structure inspection requires a string.',
    );
  }
  requireLimit(maxDepth, '/limits/max_json_depth');
  requireLimit(maxContainers, '/limits/max_json_containers');

  let inString = false;
  let escaped = false;
  let depth = 0;
  let maximumDepth = 0;
  let containerCount = 0;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (character === '\\') {
        escaped = true;
      } else if (character === '"') {
        inString = false;
      }
      continue;
    }

    if (character === '"') {
      inString = true;
      continue;
    }
    if (character === '{' || character === '[') {
      depth += 1;
      containerCount += 1;
      maximumDepth = Math.max(maximumDepth, depth);
      if (maximumDepth > maxDepth) {
        fail(
          'local_model_nesting_depth_limit_exceeded',
          '/',
          `Local model JSON nesting depth ${maximumDepth} exceeds ${maxDepth} under ${VIEWER_LOCAL_MODEL_OBJECT_POLICY}.`,
        );
      }
      if (containerCount > maxContainers) {
        fail(
          'local_model_container_count_limit_exceeded',
          '/',
          `Local model JSON container count exceeds ${maxContainers} under ${VIEWER_LOCAL_MODEL_OBJECT_POLICY}.`,
        );
      }
      continue;
    }
    if (character === '}' || character === ']') {
      depth = Math.max(0, depth - 1);
    }
  }

  return Object.freeze({
    policy: VIEWER_LOCAL_MODEL_OBJECT_POLICY,
    maximumDepth,
    containerCount,
  });
}

export function validateViewerLocalModelPayloadResources(payload) {
  if (!isRecord(payload)) {
    fail(
      'local_model_payload_object_required',
      '/',
      'Local model payload must use an object root.',
    );
  }

  const modelContainers = [
    {path: '', value: payload},
    {path: '/model', value: payload.model},
    {path: '/native_model', value: payload.native_model},
    {path: '/geometry', value: payload.geometry},
  ];
  let maximumNodeCount = 0;
  let maximumElementCount = 0;
  let modelContainerCount = 0;

  for (const candidate of modelContainers) {
    if (!isRecord(candidate.value)) continue;
    const nodeCount = validateArrayCount(candidate.value.nodes, {
      path: childPath(candidate.path, 'nodes'),
      limit: VIEWER_LOCAL_MODEL_MAX_NODE_COUNT,
      code: 'local_model_node_count_limit_exceeded',
      label: 'Local model node',
    });
    const elementCount = validateArrayCount(candidate.value.elements, {
      path: childPath(candidate.path, 'elements'),
      limit: VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT,
      code: 'local_model_element_count_limit_exceeded',
      label: 'Local model element',
    });
    if (nodeCount || elementCount) modelContainerCount += 1;
    maximumNodeCount = Math.max(maximumNodeCount, nodeCount);
    maximumElementCount = Math.max(maximumElementCount, elementCount);
  }

  const interactiveContainers = [
    {path: '', value: payload},
    {path: '/interactive_3d', value: payload.interactive_3d},
    {path: '/interactive_3d_payload', value: payload.interactive_3d_payload},
  ];
  let maximumSegmentCount = 0;
  let interactiveContainerCount = 0;
  for (const candidate of interactiveContainers) {
    if (!isRecord(candidate.value)) continue;
    const baselineCount = Array.isArray(candidate.value.baseline_segments)
      ? candidate.value.baseline_segments.length
      : 0;
    const afterCount = Array.isArray(candidate.value.after_segments)
      ? candidate.value.after_segments.length
      : 0;
    const segmentCount = baselineCount + afterCount;
    if (segmentCount > VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT) {
      fail(
        'local_model_segment_count_limit_exceeded',
        childPath(candidate.path, 'segments'),
        `Local model segment count ${segmentCount} exceeds ${VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT} under ${VIEWER_LOCAL_MODEL_OBJECT_POLICY}.`,
      );
    }
    if (baselineCount || afterCount) interactiveContainerCount += 1;
    maximumSegmentCount = Math.max(maximumSegmentCount, segmentCount);
  }

  return Object.freeze({
    policy: VIEWER_LOCAL_MODEL_OBJECT_POLICY,
    maximumNodeCount,
    maximumElementCount,
    maximumSegmentCount,
    modelContainerCount,
    interactiveContainerCount,
  });
}

export function viewerLocalModelObjectLimits() {
  return Object.freeze({
    policy: VIEWER_LOCAL_MODEL_OBJECT_POLICY,
    max_nodes: VIEWER_LOCAL_MODEL_MAX_NODE_COUNT,
    max_elements: VIEWER_LOCAL_MODEL_MAX_ELEMENT_COUNT,
    max_segments: VIEWER_LOCAL_MODEL_MAX_SEGMENT_COUNT,
    max_json_depth: VIEWER_LOCAL_MODEL_MAX_JSON_DEPTH,
    max_json_containers: VIEWER_LOCAL_MODEL_MAX_JSON_CONTAINERS,
  });
}
