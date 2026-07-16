export const AUTHORITATIVE_VIEWER_SCHEMA_VERSION = 'structural-analysis-viewer-payload.v2';
export const AUTHORITATIVE_VIEWER_IDENTITY_POLICY = 'source_bytes_and_detached_canonical_model_v1';
export const AUTHORITATIVE_VIEWER_PAYLOAD_KIND = 'authoritative_viewer_v2';
export const AUTHORITATIVE_VIEWER_RESOURCE_LIMIT_POLICY = 'authoritative_viewer_large_model_gate_v1';
export const AUTHORITATIVE_VIEWER_MAX_NODE_COUNT = 200000;
export const AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT = 100000;

const SOURCE = 'authoritative_solver_result';
const SOLVER_PATH_ID = 'authoritative_cpu_linear_fea_3d_v1';
const ANALYSIS_FIDELITY = 'cpu_reference_linear_fea';
const REACTION_DEFINITION = 'constrained_dof_internal_minus_external_force';
const EQUILIBRIUM_RESIDUAL_DEFINITION = 'free_dof_internal_minus_external_force; constrained entries are zero';
const ANALYSIS_INPUT_SNAPSHOT = 'detached_canonical_model_v1';
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const DISPLACEMENT_LABELS = ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ'];
const FORCE_LABELS = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'];
const FRAME_FORCE_LABELS = [
  'FX_I', 'FY_I', 'FZ_I', 'MX_I', 'MY_I', 'MZ_I',
  'FX_J', 'FY_J', 'FZ_J', 'MX_J', 'MY_J', 'MZ_J',
];
const AXIAL_FORCE_LABELS = ['FX_I', 'FX_J'];
const FRAME_TYPES = new Set(['frame', 'beam', 'column']);
const AXIAL_TYPES = new Set(['truss', 'axial']);

export class AuthoritativeViewerPayloadValidationError extends Error {
  constructor(code, path, message) {
    super(`${code}@${path}: ${message}`);
    this.name = 'AuthoritativeViewerPayloadValidationError';
    this.code = code;
    this.path = path;
  }
}

function fail(code, path, message) {
  throw new AuthoritativeViewerPayloadValidationError(code, path, message);
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireRecord(value, path) {
  if (!isRecord(value)) fail('viewer_payload_type_invalid', path, 'Expected an object.');
  return value;
}

function requireExactKeys(value, required, optional, path) {
  const record = requireRecord(value, path);
  const allowed = new Set([...required, ...optional]);
  const missing = required.filter((key) => !Object.prototype.hasOwnProperty.call(record, key));
  if (missing.length) {
    fail('viewer_payload_schema_invalid', path, `Missing required fields: ${missing.join(', ')}.`);
  }
  const extra = Object.keys(record).filter((key) => !allowed.has(key));
  if (extra.length) {
    fail('viewer_payload_schema_invalid', path, `Unknown fields: ${extra.join(', ')}.`);
  }
  return record;
}

function requireFiniteNumber(value, path) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    fail('viewer_numeric_value_invalid', path, 'Expected a finite JSON number.');
  }
  return value;
}

function requireStableId(value, path) {
  if (typeof value !== 'string' || !value.length || value.length > 128) {
    fail('viewer_payload_schema_invalid', path, 'Expected a non-empty string ID with at most 128 characters.');
  }
  return value;
}

function requireHash(value, path) {
  if (typeof value !== 'string' || !SHA256_PATTERN.test(value)) {
    fail('viewer_checksum_invalid', path, 'Expected sha256:<64 lowercase hex>.');
  }
  return value;
}

function requireExactNumericVector(value, labels, path) {
  const record = requireExactKeys(value, labels, [], path);
  for (const label of labels) requireFiniteNumber(record[label], `${path}/${label}`);
  return record;
}

function validateIdentity(value) {
  const identity = requireExactKeys(value, [
    'identity_policy',
    'source_input_checksum',
    'canonical_model_checksum',
    'analysis_input_snapshot',
  ], [], '/model_identity');
  if (identity.identity_policy !== AUTHORITATIVE_VIEWER_IDENTITY_POLICY) {
    fail('viewer_model_identity_policy_invalid', '/model_identity/identity_policy', 'Unknown model identity policy.');
  }
  if (identity.analysis_input_snapshot !== ANALYSIS_INPUT_SNAPSHOT) {
    fail('viewer_model_identity_snapshot_invalid', '/model_identity/analysis_input_snapshot', 'Unknown analysis input snapshot policy.');
  }
  requireHash(identity.source_input_checksum, '/model_identity/source_input_checksum');
  requireHash(identity.canonical_model_checksum, '/model_identity/canonical_model_checksum');
}

function validateNode(row, index) {
  const path = `/nodes/${index}`;
  const node = requireExactKeys(row, [
    'id',
    'coordinates',
    'displacement',
    'reaction',
    'equilibrium_residual',
  ], [], path);
  requireStableId(node.id, `${path}/id`);
  if (!Array.isArray(node.coordinates) || node.coordinates.length !== 3) {
    fail('viewer_payload_schema_invalid', `${path}/coordinates`, 'Expected exactly three coordinates.');
  }
  node.coordinates.forEach((value, coordinateIndex) => {
    requireFiniteNumber(value, `${path}/coordinates/${coordinateIndex}`);
  });
  requireExactNumericVector(node.displacement, DISPLACEMENT_LABELS, `${path}/displacement`);
  requireExactNumericVector(node.reaction, FORCE_LABELS, `${path}/reaction`);
  requireExactNumericVector(node.equilibrium_residual, FORCE_LABELS, `${path}/equilibrium_residual`);
  return node.id;
}

function validateElement(row, index, nodeIds) {
  const path = `/elements/${index}`;
  const record = requireRecord(row, path);
  const type = String(record.type ?? '');
  const frame = FRAME_TYPES.has(type);
  const axial = AXIAL_TYPES.has(type);
  if (!frame && !axial) {
    fail('viewer_payload_schema_invalid', `${path}/type`, `Unsupported element type: ${type || '<empty>'}.`);
  }
  const required = frame
    ? ['id', 'type', 'nodes', 'local_end_forces']
    : ['id', 'type', 'nodes', 'axial_force', 'elongation', 'local_end_forces'];
  const element = requireExactKeys(record, required, [], path);
  const elementId = requireStableId(element.id, `${path}/id`);
  if (!Array.isArray(element.nodes) || element.nodes.length !== 2) {
    fail('viewer_payload_schema_invalid', `${path}/nodes`, 'Expected exactly two element node IDs.');
  }
  const endpoints = element.nodes.map((value, endpointIndex) => requireStableId(value, `${path}/nodes/${endpointIndex}`));
  if (endpoints[0] === endpoints[1]) {
    fail('viewer_element_connectivity_degenerate', `${path}/nodes`, 'Element endpoints must be distinct.');
  }
  const missing = endpoints.filter((value) => !nodeIds.has(value));
  if (missing.length) {
    fail('viewer_element_node_missing', `${path}/nodes`, `Element references unknown nodes: ${missing.join(', ')}.`);
  }
  requireExactNumericVector(
    element.local_end_forces,
    frame ? FRAME_FORCE_LABELS : AXIAL_FORCE_LABELS,
    `${path}/local_end_forces`,
  );
  if (axial) {
    requireFiniteNumber(element.axial_force, `${path}/axial_force`);
    requireFiniteNumber(element.elongation, `${path}/elongation`);
  }
  return elementId;
}

export function validateAuthoritativeViewerResourceCounts({nodeCount, elementCount} = {}) {
  if (!Number.isInteger(nodeCount) || nodeCount < 0) {
    fail('viewer_resource_count_invalid', '/nodes', 'Viewer node count must be a non-negative integer.');
  }
  if (!Number.isInteger(elementCount) || elementCount < 0) {
    fail('viewer_resource_count_invalid', '/elements', 'Viewer element count must be a non-negative integer.');
  }
  if (nodeCount > AUTHORITATIVE_VIEWER_MAX_NODE_COUNT) {
    fail(
      'viewer_node_count_limit_exceeded',
      '/nodes',
      `Viewer payload contains ${nodeCount} nodes; limit is ${AUTHORITATIVE_VIEWER_MAX_NODE_COUNT} under ${AUTHORITATIVE_VIEWER_RESOURCE_LIMIT_POLICY}.`,
    );
  }
  if (elementCount > AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT) {
    fail(
      'viewer_element_count_limit_exceeded',
      '/elements',
      `Viewer payload contains ${elementCount} elements; limit is ${AUTHORITATIVE_VIEWER_MAX_ELEMENT_COUNT} under ${AUTHORITATIVE_VIEWER_RESOURCE_LIMIT_POLICY}.`,
    );
  }
  return {nodeCount, elementCount};
}

export function claimsAuthoritativeViewerContract(payload) {
  if (!isRecord(payload)) return false;
  const identity = isRecord(payload.model_identity) ? payload.model_identity : null;
  return payload.schema_version === AUTHORITATIVE_VIEWER_SCHEMA_VERSION
    || payload.source === SOURCE
    || payload.solver_path_id === SOLVER_PATH_ID
    || identity?.identity_policy === AUTHORITATIVE_VIEWER_IDENTITY_POLICY;
}

export function validateAuthoritativeViewerPayload(payload) {
  const root = requireExactKeys(payload, [
    'schema_version',
    'source',
    'solver_path_id',
    'analysis_fidelity',
    'reaction_definition',
    'equilibrium_residual_definition',
    'nodes',
    'elements',
  ], ['model_identity'], '/');
  if (!Object.prototype.hasOwnProperty.call(root, 'model_identity')) {
    fail('viewer_model_identity_missing', '/model_identity', 'Authoritative Viewer payload requires model identity.');
  }
  const constants = [
    ['schema_version', AUTHORITATIVE_VIEWER_SCHEMA_VERSION],
    ['source', SOURCE],
    ['solver_path_id', SOLVER_PATH_ID],
    ['analysis_fidelity', ANALYSIS_FIDELITY],
    ['reaction_definition', REACTION_DEFINITION],
    ['equilibrium_residual_definition', EQUILIBRIUM_RESIDUAL_DEFINITION],
  ];
  for (const [field, expected] of constants) {
    if (root[field] !== expected) {
      fail('viewer_payload_schema_invalid', `/${field}`, `Expected ${JSON.stringify(expected)}.`);
    }
  }
  validateIdentity(root.model_identity);
  if (!Array.isArray(root.nodes) || !root.nodes.length) {
    fail('viewer_payload_schema_invalid', '/nodes', 'At least one node is required.');
  }
  if (!Array.isArray(root.elements) || !root.elements.length) {
    fail('viewer_payload_schema_invalid', '/elements', 'At least one element is required.');
  }
  validateAuthoritativeViewerResourceCounts({
    nodeCount: root.nodes.length,
    elementCount: root.elements.length,
  });
  const nodeIds = new Set();
  root.nodes.forEach((row, index) => {
    const nodeId = validateNode(row, index);
    if (nodeIds.has(nodeId)) fail('viewer_node_id_duplicate', '/nodes', `Duplicate node ID: ${nodeId}.`);
    nodeIds.add(nodeId);
  });
  const elementIds = new Set();
  root.elements.forEach((row, index) => {
    const elementId = validateElement(row, index, nodeIds);
    if (elementIds.has(elementId)) fail('viewer_element_id_duplicate', '/elements', `Duplicate element ID: ${elementId}.`);
    elementIds.add(elementId);
  });
  return payload;
}
