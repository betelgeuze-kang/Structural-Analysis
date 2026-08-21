import { sha256Bytes, sha256Hex } from './checksum'

export type NativeFrameLoadStatus =
  | 'unconfigured'
  | 'loading'
  | 'ready'
  | 'missing'
  | 'invalid'
  | 'error'

export type NativeFrameArtifactStatus =
  | 'not_configured'
  | 'result_verified'
  | 'pair_verified'
  | 'bundle_verified'
  | 'integrity_unavailable'
  | 'invalid'

type SixVector = [number, number, number, number, number, number]

export interface NativeFrame3dResultIr {
  schema_version: 'structural-native-linear-frame3d-result-ir.v1'
  result_id: string
  result_hash: string
  result_kind: 'linear_static_frame3d'
  authority_profile: 'bounded_native_cpu_result_candidate.v1'
  promotion_basis: 'native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1'
  bindings: {
    model_id: string
    model_content_hash: string
    model_semantic_hash: string
    model_provenance_hash: string
    load_pattern_id: string | null
    load_combination_id: string | null
    native_abi_version: 65541
  }
  solver: {
    formulation: 'linear_timoshenko_frame3d'
    backend: 'cpu_reference_dense'
    residual_sign: 'internal_minus_external'
    unit_profile: 'node_m_rad_force_n_nm_member_local_n_nm.v1'
  }
  gates: NativeFrame3dGates
  nodes: Array<{
    node_id: string
    displacement_m_rad: SixVector
    reaction_n_nm: SixVector
  }>
  members: Array<{
    member_id: string
    end_i_force_n_nm: SixVector
    end_j_force_n_nm: SixVector
  }>
  authority: {
    numerical_state: 'bounded_candidate'
    convergence: 'bounded_candidate'
    displacement: 'bounded_candidate'
    reaction: 'bounded_candidate'
    member_force: 'bounded_candidate'
    engineering_design: 'not_authoritative'
    code_compliance: 'not_authoritative'
    release_readiness: 'not_authoritative'
    commercial_use: 'not_authoritative'
  }
  claim_boundary: {
    bounded_linear_static_timoshenko_frame3d: true
    cpu_only: true
    zero_prescribed_displacement_only: true
    nodal_load_only: false
    uniform_member_load_initial_local: true
    self_weight_standard_gravity: true
    linear_load_combination_superposition: true
    member_end_rotational_release: true
    rigid_member_end_offset: true
    reaction_from_global_residual: true
    member_force_from_native_local_recovery: true
    independent_recovery_replay: true
    cpu_hip_parity_established: false
    external_validation_established: false
    workbench_e2e: false
    release_readiness: false
    commercial_claim: false
  }
}

export interface NativeFrame3dGates {
  native_residual_gate_passed: true
  free_residual_scaled_linf: number
  free_residual_scaled_linf_tolerance: 1e-9
  global_force_balance_scaled_linf: number
  global_force_balance_scaled_linf_tolerance: 1e-9
  global_moment_balance_scaled_linf: number
  global_moment_balance_scaled_linf_tolerance: 1e-9
  global_resultant_gate_passed: true
  independent_recovery_replay_passed: true
  member_force_replay_scaled_linf: number
  member_force_replay_scaled_linf_tolerance: 1e-9
  zero_prescribed_displacement_gate_passed: true
  fallback_count: 0
  regularization_count: 0
}

export interface NativeFrame3dReportExtremum {
  quantity: 'displacement' | 'reaction' | 'member_end_force'
  entity_id: string
  component: string
  signed_value: number
  absolute_value: number
  unit: 'm' | 'rad' | 'N' | 'N*m'
}

export interface NativeFrame3dReportIr {
  schema_version: 'structural-native-linear-frame3d-report-ir.v1'
  report_id: string
  report_hash: string
  report_kind: 'linear_frame3d_analysis_summary'
  source_result: {
    schema_version: 'structural-native-linear-frame3d-result-ir.v1'
    result_id: string
    result_hash: string
  }
  summary: {
    model_id: string
    load_pattern_id: string | null
    load_combination_id: string | null
    formulation: 'linear_timoshenko_frame3d'
    backend: 'cpu_reference_dense'
    node_count: number
    member_count: number
  }
  gates: NativeFrame3dGates
  extrema: [
    NativeFrame3dReportExtremum,
    NativeFrame3dReportExtremum,
    NativeFrame3dReportExtremum,
  ]
  limitations: string[]
  authority: {
    source_result: 'bounded_candidate'
    presentation: 'deterministic_projection'
    comparison: 'not_evaluated'
    engineering_design: 'not_authoritative'
    release_readiness: 'not_authoritative'
  }
  claim_boundary: 'deterministic_presentation_of_bounded_candidate_result_not_comparison_design_or_release_authority'
}

export interface NativeFrameLoadResult {
  status: NativeFrameLoadStatus
  artifactStatus: NativeFrameArtifactStatus
  resultIr: NativeFrame3dResultIr | null
  reportIr: NativeFrame3dReportIr | null
  errors: string[]
}

interface NativeFrameBundleArtifact {
  path: string
  media_type: string
  content_hash: string
  byte_length: number
}

interface NativeFrameBundleManifest {
  schema_version: 'structural-native-linear-frame3d-workbench-bundle.v1'
  status: 'complete'
  artifacts: {
    model_ir: NativeFrameBundleArtifact
    result_ir: NativeFrameBundleArtifact
    report_ir: NativeFrameBundleArtifact
    html: NativeFrameBundleArtifact
  }
  bindings: {
    model_content_hash: string
    result_id: string
    result_hash: string
    report_id: string
    report_hash: string
  }
  claim_boundary: 'completed_no_overwrite_cli_artifact_bundle_not_job_or_workbench_execution_authority'
}

const RESULT_SCHEMA = 'structural-native-linear-frame3d-result-ir.v1'
const REPORT_SCHEMA = 'structural-native-linear-frame3d-report-ir.v1'
const HASH = /^sha256:[0-9a-f]{64}$/
const STABLE_ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i
const MODEL_MAX_BYTES = 2 * 1024 * 1024
const RESULT_MAX_BYTES = 2 * 1024 * 1024
const REPORT_MAX_BYTES = 1024 * 1024
const HTML_MAX_BYTES = 2 * 1024 * 1024
const MANIFEST_MAX_BYTES = 64 * 1024
const GATE_TOLERANCE = 1e-9
const DISPLACEMENT_COMPONENTS = ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ'] as const
const FORCE_COMPONENTS = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'] as const
const LIMITATIONS = [
  'cpu_only_no_hip_parity',
  'load_scope_nodal_uniform_self_weight_and_nested_linear_combinations',
  'no_nonuniform_or_member_point_load',
  'release_scope_rotational_rx_ry_rz_only',
  'released_coordinate_must_remain_globally_stable',
  'offset_scope_finite_global_rigid_end_arms',
  'no_translational_release',
  'no_nonzero_prescribed_displacement',
  'no_workbench_e2e',
  'no_design_or_release_authority',
] as const

class NativeFrameArtifactError extends Error {
  constructor(
    readonly kind: 'missing' | 'invalid' | 'error',
    message: string,
  ) {
    super(message)
  }
}

/** Python/Rust-compatible canonical JSON used by the native wire contracts. */
export function canonicalNativeJson(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return canonicalNumber(value)
  if (typeof value === 'string') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonicalNativeJson).join(',')}]`
  if (record(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalNativeJson(value[key])}`)
      .join(',')}}`
  }
  throw new Error('native_frame_canonical_json_unsupported_value')
}

/** Strict JSON parser that rejects duplicate object keys before normal JSON decoding. */
export function parseNativeJsonStrict(text: string): unknown {
  let position = 0

  function fail(): never {
    throw new Error('native_frame_json_invalid')
  }

  function whitespace(): void {
    while (position < text.length && /[\t\n\r ]/.test(text[position])) position += 1
  }

  function stringToken(): string {
    if (text[position] !== '"') fail()
    const start = position
    position += 1
    while (position < text.length) {
      const character = text[position]
      if (character === '"') {
        position += 1
        try {
          return JSON.parse(text.slice(start, position)) as string
        } catch {
          fail()
        }
      }
      if (character === '\\') {
        position += 1
        const escape = text[position]
        if (escape === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(position + 1, position + 5))) fail()
          position += 5
          continue
        }
        if (!escape || !'"\\/bfnrt'.includes(escape)) fail()
        position += 1
        continue
      }
      if (character.charCodeAt(0) < 0x20) fail()
      position += 1
    }
    fail()
  }

  function literal(token: string): void {
    if (text.slice(position, position + token.length) !== token) fail()
    position += token.length
  }

  function numberToken(): void {
    const match = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y
    match.lastIndex = position
    const found = match.exec(text)
    if (!found) fail()
    position = match.lastIndex
  }

  function value(): void {
    whitespace()
    const character = text[position]
    if (character === '{') object()
    else if (character === '[') array()
    else if (character === '"') void stringToken()
    else if (character === 't') literal('true')
    else if (character === 'f') literal('false')
    else if (character === 'n') literal('null')
    else numberToken()
    whitespace()
  }

  function object(): void {
    position += 1
    whitespace()
    const keys = new Set<string>()
    if (text[position] === '}') {
      position += 1
      return
    }
    while (position < text.length) {
      const key = stringToken()
      if (keys.has(key)) throw new Error('native_frame_duplicate_json_key')
      keys.add(key)
      whitespace()
      if (text[position] !== ':') fail()
      position += 1
      value()
      if (text[position] === '}') {
        position += 1
        return
      }
      if (text[position] !== ',') fail()
      position += 1
      whitespace()
    }
    fail()
  }

  function array(): void {
    position += 1
    whitespace()
    if (text[position] === ']') {
      position += 1
      return
    }
    while (position < text.length) {
      value()
      if (text[position] === ']') {
        position += 1
        return
      }
      if (text[position] !== ',') fail()
      position += 1
    }
    fail()
  }

  value()
  whitespace()
  if (position !== text.length) fail()
  try {
    return JSON.parse(text) as unknown
  } catch {
    fail()
  }
}

export async function loadNativeFrameArtifacts(
  resultUrl: string | undefined,
  reportUrl?: string,
  signal?: AbortSignal,
): Promise<NativeFrameLoadResult> {
  if (!resultUrl) {
    return {
      status: reportUrl ? 'invalid' : 'unconfigured',
      artifactStatus: reportUrl ? 'invalid' : 'not_configured',
      resultIr: null,
      reportIr: null,
      errors: reportUrl ? ['native Frame3D report URL requires a result URL'] : [],
    }
  }
  try {
    const resultPayload = await fetchJson(resultUrl, RESULT_MAX_BYTES, 'native Frame3D ResultIR', signal)
    const resultValidation = await validateResultIr(resultPayload)
    if (resultValidation.error) throw new NativeFrameArtifactError('invalid', resultValidation.error)
    const resultIr = resultValidation.value
    if (!reportUrl) {
      return {
        status: 'ready',
        artifactStatus: resultValidation.integrityUnavailable
          ? 'integrity_unavailable'
          : 'result_verified',
        resultIr,
        reportIr: null,
        errors: [],
      }
    }
    const reportPayload = await fetchJson(reportUrl, REPORT_MAX_BYTES, 'native Frame3D ReportIR', signal)
    const reportValidation = await validateReportIr(reportPayload, resultIr)
    if (reportValidation.error) throw new NativeFrameArtifactError('invalid', reportValidation.error)
    return {
      status: 'ready',
      artifactStatus: resultValidation.integrityUnavailable || reportValidation.integrityUnavailable
        ? 'integrity_unavailable'
        : 'pair_verified',
      resultIr,
      reportIr: reportValidation.value,
      errors: [],
    }
  } catch (error: unknown) {
    if ((error as Error)?.name === 'AbortError') {
      return {
        status: 'unconfigured',
        artifactStatus: 'not_configured',
        resultIr: null,
        reportIr: null,
        errors: [],
      }
    }
    const failure = error instanceof NativeFrameArtifactError
      ? error
      : new NativeFrameArtifactError('error', 'native Frame3D artifact request failed')
    return {
      status: failure.kind,
      artifactStatus: 'invalid',
      resultIr: null,
      reportIr: null,
      errors: [failure.message],
    }
  }
}

export async function loadNativeFrameBundle(
  manifestUrl: string | undefined,
  signal?: AbortSignal,
): Promise<NativeFrameLoadResult> {
  if (!manifestUrl) {
    return {
      status: 'unconfigured',
      artifactStatus: 'not_configured',
      resultIr: null,
      reportIr: null,
      errors: [],
    }
  }
  try {
    const manifestPayload = await fetchJson(manifestUrl, MANIFEST_MAX_BYTES, 'native Frame3D bundle manifest', signal)
    let manifest: NativeFrameBundleManifest
    try {
      manifest = validateBundleManifest(manifestPayload)
    } catch (error: unknown) {
      throw new NativeFrameArtifactError('invalid', String((error as Error)?.message ?? error))
    }
    const modelUrl = new URL(manifest.artifacts.model_ir.path, manifestUrl).toString()
    const resultUrl = new URL(manifest.artifacts.result_ir.path, manifestUrl).toString()
    const reportUrl = new URL(manifest.artifacts.report_ir.path, manifestUrl).toString()
    const htmlUrl = new URL(manifest.artifacts.html.path, manifestUrl).toString()
    const [modelArtifact, resultArtifact, reportArtifact, htmlArtifact] = await Promise.all([
      fetchPayload(modelUrl, MODEL_MAX_BYTES, 'native Frame3D ModelIR', JSON_CONTENT_TYPE, signal),
      fetchPayload(resultUrl, RESULT_MAX_BYTES, 'native Frame3D ResultIR', JSON_CONTENT_TYPE, signal),
      fetchPayload(reportUrl, REPORT_MAX_BYTES, 'native Frame3D ReportIR', JSON_CONTENT_TYPE, signal),
      fetchPayload(htmlUrl, HTML_MAX_BYTES, 'native Frame3D HTML report', /^text\/html\b/i, signal),
    ])
    await verifyBundleArtifact(modelArtifact.bytes, manifest.artifacts.model_ir, 'ModelIR')
    await verifyBundleArtifact(resultArtifact.bytes, manifest.artifacts.result_ir, 'ResultIR')
    await verifyBundleArtifact(reportArtifact.bytes, manifest.artifacts.report_ir, 'ReportIR')
    await verifyBundleArtifact(htmlArtifact.bytes, manifest.artifacts.html, 'HTML report')
    const resultValidation = await validateResultIr(parseFetchedJson(resultArtifact, 'native Frame3D ResultIR'))
    if (resultValidation.error) throw new NativeFrameArtifactError('invalid', resultValidation.error)
    const resultIr = resultValidation.value
    const reportValidation = await validateReportIr(
      parseFetchedJson(reportArtifact, 'native Frame3D ReportIR'),
      resultIr,
    )
    if (reportValidation.error) throw new NativeFrameArtifactError('invalid', reportValidation.error)
    const reportIr = reportValidation.value
    try {
      requireExactRecord(manifest.bindings, 'bundle bindings', {
        model_content_hash: resultIr.bindings.model_content_hash,
        result_id: resultIr.result_id,
        result_hash: resultIr.result_hash,
        report_id: reportIr.report_id,
        report_hash: reportIr.report_hash,
      })
    } catch (error: unknown) {
      throw new NativeFrameArtifactError('invalid', String((error as Error)?.message ?? error))
    }
    if (resultValidation.integrityUnavailable || reportValidation.integrityUnavailable) {
      throw new NativeFrameArtifactError('invalid', 'native Frame3D bundle integrity is unavailable')
    }
    return {
      status: 'ready',
      artifactStatus: 'bundle_verified',
      resultIr,
      reportIr,
      errors: [],
    }
  } catch (error: unknown) {
    if ((error as Error)?.name === 'AbortError') {
      return {
        status: 'unconfigured',
        artifactStatus: 'not_configured',
        resultIr: null,
        reportIr: null,
        errors: [],
      }
    }
    const failure = error instanceof NativeFrameArtifactError
      ? error
      : new NativeFrameArtifactError('error', 'native Frame3D bundle request failed')
    return {
      status: failure.kind,
      artifactStatus: 'invalid',
      resultIr: null,
      reportIr: null,
      errors: [failure.message],
    }
  }
}

function validateBundleManifest(value: unknown): NativeFrameBundleManifest {
  const root = exactRecord(value, 'bundle manifest', [
    'schema_version', 'status', 'artifacts', 'bindings', 'claim_boundary',
  ])
  requireExact(root.schema_version, 'structural-native-linear-frame3d-workbench-bundle.v1', 'bundle schema')
  requireExact(root.status, 'complete', 'bundle completion status')
  requireExact(
    root.claim_boundary,
    'completed_no_overwrite_cli_artifact_bundle_not_job_or_workbench_execution_authority',
    'bundle claim boundary',
  )
  const artifacts = exactRecord(root.artifacts, 'bundle artifacts', ['model_ir', 'result_ir', 'report_ir', 'html'])
  validateBundleArtifact(artifacts.model_ir, 'model-ir.json', 'application/json', MODEL_MAX_BYTES, 'ModelIR')
  validateBundleArtifact(artifacts.result_ir, 'result-ir.json', 'application/json', RESULT_MAX_BYTES, 'ResultIR')
  validateBundleArtifact(artifacts.report_ir, 'report-ir.json', 'application/json', REPORT_MAX_BYTES, 'ReportIR')
  validateBundleArtifact(artifacts.html, 'report.html', 'text/html', HTML_MAX_BYTES, 'HTML report')
  const bindings = exactRecord(root.bindings, 'bundle bindings', [
    'model_content_hash', 'result_id', 'result_hash', 'report_id', 'report_hash',
  ])
  requireHash(bindings.model_content_hash, 'bundle model content hash')
  requireId(bindings.result_id, 'bundle result id')
  requireHash(bindings.result_hash, 'bundle result hash')
  requireId(bindings.report_id, 'bundle report id')
  requireHash(bindings.report_hash, 'bundle report hash')
  requireExact(
    (artifacts.model_ir as Record<string, unknown>).content_hash,
    bindings.model_content_hash,
    'bundle ModelIR content binding',
  )
  return root as unknown as NativeFrameBundleManifest
}

function validateBundleArtifact(
  value: unknown,
  path: string,
  mediaType: string,
  maximumBytes: number,
  label: string,
): void {
  const artifact = exactRecord(value, `bundle ${label}`, ['path', 'media_type', 'content_hash', 'byte_length'])
  requireExact(artifact.path, path, `bundle ${label} path`)
  requireExact(artifact.media_type, mediaType, `bundle ${label} media type`)
  requireHash(artifact.content_hash, `bundle ${label} content hash`)
  if (!Number.isSafeInteger(artifact.byte_length) || Number(artifact.byte_length) <= 0
    || Number(artifact.byte_length) > maximumBytes) {
    throw new Error(`bundle ${label} byte length is invalid`)
  }
}

async function verifyBundleArtifact(
  bytes: Uint8Array,
  reference: NativeFrameBundleArtifact,
  label: string,
): Promise<void> {
  if (bytes.byteLength !== reference.byte_length) {
    throw new NativeFrameArtifactError('invalid', `native Frame3D bundle ${label} byte length mismatch`)
  }
  const digest = await sha256Bytes(bytes)
  if (digest === null || digest !== reference.content_hash) {
    throw new NativeFrameArtifactError('invalid', `native Frame3D bundle ${label} hash mismatch`)
  }
}

async function fetchJson(
  url: string,
  maximumBytes: number,
  label: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const payload = await fetchPayload(url, maximumBytes, label, JSON_CONTENT_TYPE, signal)
  return parseFetchedJson(payload, label)
}

interface FetchedPayload {
  bytes: Uint8Array
  text: string
}

async function fetchPayload(
  url: string,
  maximumBytes: number,
  label: string,
  acceptedContentType: RegExp,
  signal?: AbortSignal,
): Promise<FetchedPayload> {
  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (response.status === 404) throw new NativeFrameArtifactError('missing', `${label} not found`)
  if (!response.ok) throw new NativeFrameArtifactError('error', `${label} returned HTTP ${response.status}`)
  const contentType = response.headers.get('content-type') ?? ''
  if (!acceptedContentType.test(contentType)) {
    throw new NativeFrameArtifactError('invalid', `${label} content type is invalid`)
  }
  const declared = Number(response.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > maximumBytes) {
    throw new NativeFrameArtifactError('invalid', `${label} exceeds the size limit`)
  }
  const bytes = new Uint8Array(await response.arrayBuffer())
  if (bytes.byteLength > maximumBytes) {
    throw new NativeFrameArtifactError('invalid', `${label} exceeds the size limit`)
  }
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new NativeFrameArtifactError('invalid', `${label} is not valid UTF-8`)
  }
  return { bytes, text }
}

function parseFetchedJson(payload: FetchedPayload, label: string): unknown {
  try {
    return parseNativeJsonStrict(payload.text)
  } catch (error: unknown) {
    const duplicate = (error as Error)?.message === 'native_frame_duplicate_json_key'
    throw new NativeFrameArtifactError(
      'invalid',
      duplicate ? `${label} contains a duplicate JSON key` : `${label} JSON is invalid`,
    )
  }
}

async function validateResultIr(value: unknown): Promise<{
  value: NativeFrame3dResultIr
  integrityUnavailable: boolean
  error?: string
}> {
  try {
    const root = exactRecord(value, 'ResultIR', [
      'schema_version', 'result_id', 'result_hash', 'result_kind', 'authority_profile',
      'promotion_basis', 'bindings', 'solver', 'gates', 'nodes', 'members', 'authority',
      'claim_boundary',
    ])
    requireExact(root.schema_version, RESULT_SCHEMA, 'ResultIR schema')
    requireId(root.result_id, 'ResultIR result_id')
    requireHash(root.result_hash, 'ResultIR result_hash')
    requireExact(root.result_kind, 'linear_static_frame3d', 'ResultIR result_kind')
    requireExact(root.authority_profile, 'bounded_native_cpu_result_candidate.v1', 'ResultIR authority profile')
    requireExact(
      root.promotion_basis,
      'native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1',
      'ResultIR promotion basis',
    )
    const bindings = exactRecord(root.bindings, 'ResultIR bindings', [
      'model_id', 'model_content_hash', 'model_semantic_hash', 'model_provenance_hash',
      'load_pattern_id', 'load_combination_id', 'native_abi_version',
    ])
    requireId(bindings.model_id, 'ResultIR model_id')
    if (typeof bindings.load_pattern_id === 'string' && bindings.load_combination_id === null) {
      requireId(bindings.load_pattern_id, 'ResultIR load_pattern_id')
    } else if (bindings.load_pattern_id === null && typeof bindings.load_combination_id === 'string') {
      requireId(bindings.load_combination_id, 'ResultIR load_combination_id')
    } else {
      throw new Error('ResultIR must bind exactly one load pattern or load combination')
    }
    for (const key of ['model_content_hash', 'model_semantic_hash', 'model_provenance_hash']) {
      requireHash(bindings[key], `ResultIR ${key}`)
    }
    requireExact(bindings.native_abi_version, 65541, 'ResultIR native ABI')
    const solver = exactRecord(root.solver, 'ResultIR solver', [
      'formulation', 'backend', 'residual_sign', 'unit_profile',
    ])
    requireExact(solver.formulation, 'linear_timoshenko_frame3d', 'ResultIR formulation')
    requireExact(solver.backend, 'cpu_reference_dense', 'ResultIR backend')
    requireExact(solver.residual_sign, 'internal_minus_external', 'ResultIR residual sign')
    requireExact(solver.unit_profile, 'node_m_rad_force_n_nm_member_local_n_nm.v1', 'ResultIR unit profile')
    validateGates(root.gates, 'ResultIR gates')
    validateNodes(root.nodes)
    validateMembers(root.members)
    requireExactRecord(root.authority, 'ResultIR authority', {
      numerical_state: 'bounded_candidate',
      convergence: 'bounded_candidate',
      displacement: 'bounded_candidate',
      reaction: 'bounded_candidate',
      member_force: 'bounded_candidate',
      engineering_design: 'not_authoritative',
      code_compliance: 'not_authoritative',
      release_readiness: 'not_authoritative',
      commercial_use: 'not_authoritative',
    })
    requireExactRecord(root.claim_boundary, 'ResultIR claim boundary', {
      bounded_linear_static_timoshenko_frame3d: true,
      cpu_only: true,
      zero_prescribed_displacement_only: true,
      nodal_load_only: false,
      uniform_member_load_initial_local: true,
      self_weight_standard_gravity: true,
      linear_load_combination_superposition: true,
      member_end_rotational_release: true,
      rigid_member_end_offset: true,
      reaction_from_global_residual: true,
      member_force_from_native_local_recovery: true,
      independent_recovery_replay: true,
      cpu_hip_parity_established: false,
      external_validation_established: false,
      workbench_e2e: false,
      release_readiness: false,
      commercial_claim: false,
    })
    const body = { ...root }
    delete body.result_hash
    const computed = await sha256Hex(canonicalNativeJson(body))
    if (computed !== null && computed !== root.result_hash) throw new Error('ResultIR hash mismatch')
    return {
      value: root as unknown as NativeFrame3dResultIr,
      integrityUnavailable: computed === null,
    }
  } catch (error: unknown) {
    return {
      value: null as unknown as NativeFrame3dResultIr,
      integrityUnavailable: false,
      error: String((error as Error)?.message ?? error),
    }
  }
}

async function validateReportIr(value: unknown, result: NativeFrame3dResultIr): Promise<{
  value: NativeFrame3dReportIr
  integrityUnavailable: boolean
  error?: string
}> {
  try {
    const root = exactRecord(value, 'ReportIR', [
      'schema_version', 'report_id', 'report_hash', 'report_kind', 'source_result',
      'summary', 'gates', 'extrema', 'limitations', 'authority', 'claim_boundary',
    ])
    requireExact(root.schema_version, REPORT_SCHEMA, 'ReportIR schema')
    requireId(root.report_id, 'ReportIR report_id')
    requireHash(root.report_hash, 'ReportIR report_hash')
    requireExact(root.report_kind, 'linear_frame3d_analysis_summary', 'ReportIR kind')
    requireExactRecord(root.source_result, 'ReportIR source result', {
      schema_version: result.schema_version,
      result_id: result.result_id,
      result_hash: result.result_hash,
    })
    requireExactRecord(root.summary, 'ReportIR summary', {
      model_id: result.bindings.model_id,
      load_pattern_id: result.bindings.load_pattern_id,
      load_combination_id: result.bindings.load_combination_id,
      formulation: result.solver.formulation,
      backend: result.solver.backend,
      node_count: result.nodes.length,
      member_count: result.members.length,
    })
    validateGates(root.gates, 'ReportIR gates')
    if (canonicalNativeJson(root.gates) !== canonicalNativeJson(result.gates)) {
      throw new Error('ReportIR gates are detached from ResultIR')
    }
    validateExtrema(root.extrema, result)
    requireStringArrayExact(root.limitations, LIMITATIONS, 'ReportIR limitations')
    requireExactRecord(root.authority, 'ReportIR authority', {
      source_result: 'bounded_candidate',
      presentation: 'deterministic_projection',
      comparison: 'not_evaluated',
      engineering_design: 'not_authoritative',
      release_readiness: 'not_authoritative',
    })
    requireExact(
      root.claim_boundary,
      'deterministic_presentation_of_bounded_candidate_result_not_comparison_design_or_release_authority',
      'ReportIR claim boundary',
    )
    const body = { ...root }
    delete body.report_hash
    const computed = await sha256Hex(canonicalNativeJson(body))
    if (computed !== null && computed !== root.report_hash) throw new Error('ReportIR hash mismatch')
    return {
      value: root as unknown as NativeFrame3dReportIr,
      integrityUnavailable: computed === null,
    }
  } catch (error: unknown) {
    return {
      value: null as unknown as NativeFrame3dReportIr,
      integrityUnavailable: false,
      error: String((error as Error)?.message ?? error),
    }
  }
}

function canonicalNumber(value: number): string {
  if (!Number.isFinite(value)) throw new Error('native_frame_non_finite_number')
  if (value === 0) return '0'
  const sign = value < 0 ? '-' : ''
  const shortest = Math.abs(value).toString().toLowerCase()
  const [mantissa, exponentText] = shortest.split('e')
  const explicitExponent = exponentText === undefined ? 0 : Number(exponentText)
  const decimalPosition = mantissa.indexOf('.') === -1 ? mantissa.length : mantissa.indexOf('.')
  const digits = mantissa.replace('.', '')
  const firstNonzero = [...digits].findIndex((character) => character !== '0')
  if (firstNonzero < 0) return '0'
  const significant = digits.slice(firstNonzero)
  const scientificExponent = explicitExponent + decimalPosition - firstNonzero - 1
  if (!Number.isInteger(value) && (scientificExponent < -4 || scientificExponent >= 16)) {
    const fraction = significant.length > 1 ? `.${significant.slice(1)}` : ''
    const exponentSign = scientificExponent < 0 ? '-' : '+'
    const magnitude = Math.abs(scientificExponent).toString().padStart(2, '0')
    return `${sign}${significant[0]}${fraction}e${exponentSign}${magnitude}`
  }
  const fixedPosition = scientificExponent + 1
  if (fixedPosition <= 0) {
    return `${sign}0.${'0'.repeat(-fixedPosition)}${significant}`
  }
  if (fixedPosition >= significant.length) {
    return `${sign}${significant}${'0'.repeat(fixedPosition - significant.length)}`
  }
  return `${sign}${significant.slice(0, fixedPosition)}.${significant.slice(fixedPosition)}`
}

function validateGates(value: unknown, label: string): void {
  const gates = exactRecord(value, label, [
    'native_residual_gate_passed', 'free_residual_scaled_linf',
    'free_residual_scaled_linf_tolerance', 'global_force_balance_scaled_linf',
    'global_force_balance_scaled_linf_tolerance', 'global_moment_balance_scaled_linf',
    'global_moment_balance_scaled_linf_tolerance', 'global_resultant_gate_passed',
    'independent_recovery_replay_passed', 'member_force_replay_scaled_linf',
    'member_force_replay_scaled_linf_tolerance', 'zero_prescribed_displacement_gate_passed',
    'fallback_count', 'regularization_count',
  ])
  requireExact(gates.native_residual_gate_passed, true, `${label} native residual`)
  requireExact(gates.global_resultant_gate_passed, true, `${label} global resultant`)
  requireExact(gates.independent_recovery_replay_passed, true, `${label} independent recovery replay`)
  requireExact(gates.zero_prescribed_displacement_gate_passed, true, `${label} prescribed displacement`)
  requireExact(gates.fallback_count, 0, `${label} fallback count`)
  requireExact(gates.regularization_count, 0, `${label} regularization count`)
  for (const [metric, tolerance] of [
    ['free_residual_scaled_linf', 'free_residual_scaled_linf_tolerance'],
    ['global_force_balance_scaled_linf', 'global_force_balance_scaled_linf_tolerance'],
    ['global_moment_balance_scaled_linf', 'global_moment_balance_scaled_linf_tolerance'],
    ['member_force_replay_scaled_linf', 'member_force_replay_scaled_linf_tolerance'],
  ] as const) {
    requireExact(gates[tolerance], GATE_TOLERANCE, `${label} ${tolerance}`)
    requireFiniteRange(gates[metric], 0, GATE_TOLERANCE, `${label} ${metric}`)
  }
}

function validateNodes(value: unknown): void {
  if (!Array.isArray(value) || value.length < 2 || value.length > 16) {
    throw new Error('ResultIR nodes are outside the bounded profile')
  }
  const ids = new Set<string>()
  for (const item of value) {
    const node = exactRecord(item, 'ResultIR node', ['node_id', 'displacement_m_rad', 'reaction_n_nm'])
    requireId(node.node_id, 'ResultIR node_id')
    if (ids.has(node.node_id as string)) throw new Error('ResultIR node_id is duplicated')
    ids.add(node.node_id as string)
    requireSixFinite(node.displacement_m_rad, 'ResultIR displacement')
    requireSixFinite(node.reaction_n_nm, 'ResultIR reaction')
  }
}

function validateMembers(value: unknown): void {
  if (!Array.isArray(value) || value.length < 1 || value.length > 32) {
    throw new Error('ResultIR members are outside the bounded profile')
  }
  const ids = new Set<string>()
  for (const item of value) {
    const member = exactRecord(item, 'ResultIR member', [
      'member_id', 'end_i_force_n_nm', 'end_j_force_n_nm',
    ])
    requireId(member.member_id, 'ResultIR member_id')
    if (ids.has(member.member_id as string)) throw new Error('ResultIR member_id is duplicated')
    ids.add(member.member_id as string)
    requireSixFinite(member.end_i_force_n_nm, 'ResultIR member i force')
    requireSixFinite(member.end_j_force_n_nm, 'ResultIR member j force')
  }
}

function validateExtrema(value: unknown, result: NativeFrame3dResultIr): void {
  if (!Array.isArray(value) || value.length !== 3) throw new Error('ReportIR extrema shape is invalid')
  const expected = expectedExtrema(result)
  for (let index = 0; index < expected.length; index += 1) {
    const row = exactRecord(value[index], `ReportIR extrema ${index}`, [
      'quantity', 'entity_id', 'component', 'signed_value', 'absolute_value', 'unit',
    ])
    requireExactRecord(row, `ReportIR extrema ${index}`, expected[index])
  }
}

function expectedExtrema(result: NativeFrame3dResultIr): Array<Record<string, unknown>> {
  let displacement = { entityId: result.nodes[0].node_id, index: 0, value: result.nodes[0].displacement_m_rad[0] }
  let reaction = { entityId: result.nodes[0].node_id, index: 0, value: result.nodes[0].reaction_n_nm[0] }
  for (const node of result.nodes) {
    node.displacement_m_rad.forEach((value, index) => {
      if (Math.abs(value) > Math.abs(displacement.value)) displacement = { entityId: node.node_id, index, value }
    })
    node.reaction_n_nm.forEach((value, index) => {
      if (Math.abs(value) > Math.abs(reaction.value)) reaction = { entityId: node.node_id, index, value }
    })
  }
  const first = result.members[0]
  let memberForce = { entityId: first.member_id, index: 0, end: 'I', value: first.end_i_force_n_nm[0] }
  for (const member of result.members) {
    for (const [end, values] of [['I', member.end_i_force_n_nm], ['J', member.end_j_force_n_nm]] as const) {
      values.forEach((value, index) => {
        if (Math.abs(value) > Math.abs(memberForce.value)) {
          memberForce = { entityId: member.member_id, index, end, value }
        }
      })
    }
  }
  return [
    {
      quantity: 'displacement', entity_id: displacement.entityId,
      component: DISPLACEMENT_COMPONENTS[displacement.index], signed_value: displacement.value,
      absolute_value: Math.abs(displacement.value), unit: displacement.index < 3 ? 'm' : 'rad',
    },
    {
      quantity: 'reaction', entity_id: reaction.entityId,
      component: FORCE_COMPONENTS[reaction.index], signed_value: reaction.value,
      absolute_value: Math.abs(reaction.value), unit: reaction.index < 3 ? 'N' : 'N*m',
    },
    {
      quantity: 'member_end_force', entity_id: memberForce.entityId,
      component: `${FORCE_COMPONENTS[memberForce.index]}_${memberForce.end}`,
      signed_value: memberForce.value, absolute_value: Math.abs(memberForce.value),
      unit: memberForce.index < 3 ? 'N' : 'N*m',
    },
  ]
}

function exactRecord(value: unknown, label: string, keys: readonly string[]): Record<string, unknown> {
  if (!record(value)) throw new Error(`${label} is not an object`)
  const actual = Object.keys(value).sort()
  const expected = [...keys].sort()
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${label} fields are invalid`)
  }
  return value
}

function requireExactRecord(
  value: unknown,
  label: string,
  expected: Record<string, unknown>,
): void {
  const actual = exactRecord(value, label, Object.keys(expected))
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (actual[key] !== expectedValue) throw new Error(`${label} ${key} is invalid`)
  }
}

function requireStringArrayExact(
  value: unknown,
  expected: readonly string[],
  label: string,
): void {
  if (!Array.isArray(value) || value.length !== expected.length) throw new Error(`${label} are invalid`)
  value.forEach((item, index) => requireExact(item, expected[index], `${label} ${index}`))
}

function requireExact(value: unknown, expected: unknown, label: string): void {
  if (value !== expected) throw new Error(`${label} is invalid`)
}

function requireId(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !STABLE_ID.test(value)) throw new Error(`${label} is invalid`)
}

function requireHash(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !HASH.test(value)) throw new Error(`${label} is invalid`)
}

function requireFiniteRange(value: unknown, minimum: number, maximum: number, label: string): void {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${label} is invalid`)
  }
}

function requireSixFinite(value: unknown, label: string): asserts value is SixVector {
  if (!Array.isArray(value) || value.length !== 6 || value.some((item) => typeof item !== 'number' || !Number.isFinite(item))) {
    throw new Error(`${label} is invalid`)
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
