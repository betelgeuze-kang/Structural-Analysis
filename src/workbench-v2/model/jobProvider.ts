import { canonicalJson, sha256Bytes, sha256Hex } from './checksum'
import {
  validateWorkbenchJobView,
  type JobArtifactReference,
  type WorkbenchJobView,
} from './jobSchema'

export type JobLoadStatus = 'unconfigured' | 'loading' | 'ready' | 'missing' | 'invalid' | 'error'

export interface JobLoadResult {
  status: JobLoadStatus
  job: WorkbenchJobView | null
  errors: string[]
  artifactStatus?: 'not_published' | 'verified' | 'integrity_unavailable' | 'invalid'
  engineeringResultIr?: EngineeringResultIrManifest
}

export interface EngineeringResultIrManifest {
  schema_version: 'corotational-fiber-frame2d-engineering-result-ir.v1'
  engineering_result_id: string
  engineering_result_hash: string
  result_kind: string
  recovery_profile: string
  authority_profile: string
  compiler_hash: string
  source_adapter_hash: string
  model_content_hash: string
  problem_contract_hash: string
  terminal_checkpoint_hash: string
  terminal_assembly_hash: string
  array_bundle_hash: string
  quantity_catalog_hash: string
  load_factor: 1
  counts: {
    node: number
    member: number
    section: number
    fiber: number
  }
  member_ids: string[]
  metrics: Record<string, number | boolean>
  authority_axes: Record<string, string>
  limitations: string[]
  array_descriptors: EngineeringArrayDescriptor[]
}

export interface EngineeringArrayDescriptor {
  name: string
  dtype: '<f8' | '<i8'
  shape: number[]
  unit: string
  quantity_ids: string[]
  order_scope: 'node' | 'member' | 'section' | 'fiber'
  authority_role: 'output' | 'mapping'
  order_hash: string
  data_hash: string
  content_hash: string
}

const JOB_VIEW_MAX_BYTES = 256 * 1024
const RESULT_MAX_BYTES = 64 * 1024 * 1024
const EVIDENCE_MAX_BYTES = 16 * 1024 * 1024
const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i

export async function loadWorkbenchJob(url: string, signal?: AbortSignal): Promise<JobLoadResult> {
  if (!url) return { status: 'unconfigured', job: null, errors: [] }
  try {
    const response = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (response.status === 404) return { status: 'missing', job: null, errors: ['job not found'] }
    if (!response.ok) return { status: 'error', job: null, errors: [`job API returned HTTP ${response.status}`] }
    const viewBytes = await boundedBytes(response, JOB_VIEW_MAX_BYTES, 'job view')
    const validation = validateWorkbenchJobView(parseJson(viewBytes, 'job view'))
    if (!validation.ok || !validation.value) {
      return { status: 'invalid', job: null, errors: validation.errors, artifactStatus: 'invalid' }
    }
    const job = validation.value
    if (job.status !== 'succeeded' || !job.result || !job.evidence) {
      return { status: 'ready', job, errors: [], artifactStatus: 'not_published' }
    }
    const [result, evidence] = await Promise.all([
      fetchArtifact(url, job.result, RESULT_MAX_BYTES, signal),
      fetchArtifact(url, job.evidence, EVIDENCE_MAX_BYTES, signal),
    ])
    const artifactErrors = [...result.errors, ...evidence.errors]
    if (artifactErrors.length) {
      return { status: 'invalid', job, errors: artifactErrors, artifactStatus: 'invalid' }
    }
    const resultPayload = result.value
    const evidencePayload = evidence.value
    const resultValidation = await validatePublishedEngineeringResultIr(resultPayload, artifactErrors)
    const resultIr = resultValidation.value
    if (
      !record(evidencePayload)
      || evidencePayload.schema_version !== 'structural-analysis-job-completion-evidence.v1'
      || evidencePayload.job_id !== job.job_id
      || evidencePayload.request_hash !== job.request.content_hash
      || evidencePayload.checkpoint_hash !== (job.checkpoint?.content_hash ?? null)
      || evidencePayload.result_artifact_hash !== job.result.content_hash
      || evidencePayload.contract_pass !== true
      || evidencePayload.solver_truth_owner !== 'structural_analysis_core'
      || evidencePayload.validator_id !== 'structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result'
      || !validCoreValidationReport(evidencePayload.validation_report, resultPayload)
    ) {
      artifactErrors.push('published completion evidence binding is invalid')
    }
    if (artifactErrors.length) {
      return { status: 'invalid', job, errors: artifactErrors, artifactStatus: 'invalid' }
    }
    return {
      status: 'ready',
      job,
      errors: [],
      artifactStatus: result.integrityUnavailable || evidence.integrityUnavailable || resultValidation.integrityUnavailable
        ? 'integrity_unavailable'
        : 'verified',
      engineeringResultIr: resultIr ?? undefined,
    }
  } catch (error: unknown) {
    if ((error as Error)?.name === 'AbortError') return { status: 'unconfigured', job: null, errors: [] }
    return { status: 'error', job: null, errors: ['job API request failed'] }
  }
}

async function fetchArtifact(
  statusUrl: string,
  reference: JobArtifactReference,
  maximumBytes: number,
  signal?: AbortSignal,
): Promise<{ value: unknown; errors: string[]; integrityUnavailable: boolean }> {
  const response = await fetch(`${statusUrl}/${reference.role}`, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: reference.media_type },
    signal,
  })
  if (!response.ok) return { value: null, errors: [`${reference.role} HTTP ${response.status}`], integrityUnavailable: false }
  const bytes = await boundedBytes(response, maximumBytes, reference.role)
  if (bytes.byteLength !== reference.byte_length) {
    return { value: null, errors: [`${reference.role} byte length mismatch`], integrityUnavailable: false }
  }
  const digest = await sha256Bytes(bytes)
  if (digest !== null && digest !== reference.content_hash) {
    return { value: null, errors: [`${reference.role} sha256 mismatch`], integrityUnavailable: false }
  }
  return { value: parseJson(bytes, reference.role), errors: [], integrityUnavailable: digest === null }
}

async function boundedBytes(response: Response, maximumBytes: number, label: string): Promise<Uint8Array> {
  const contentType = response.headers.get('content-type') ?? ''
  if (!JSON_CONTENT_TYPE.test(contentType)) throw new Error(`${label.replace(' ', '_')}_content_type_invalid`)
  const declared = Number(response.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > maximumBytes) throw new Error(`${label.replace(' ', '_')}_too_large`)
  const bytes = new Uint8Array(await response.arrayBuffer())
  if (bytes.byteLength > maximumBytes) throw new Error(`${label.replace(' ', '_')}_too_large`)
  return bytes
}

function parseJson(bytes: Uint8Array, label: string): unknown {
  try {
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
  } catch {
    throw new Error(`${label.replace(' ', '_')}_json_invalid`)
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

async function validatePublishedEngineeringResultIr(
  value: unknown,
  errors: string[],
): Promise<{ value: EngineeringResultIrManifest | null; integrityUnavailable: boolean }> {
  if (
    !record(value)
    || value.schema_version !== 'unified-nonlinear-frame-result.v1'
    || value.status !== 'ready'
    || value.contract_pass !== true
    || (
      value.profile !== 'corotational_one_bay_portal.v1'
      && value.profile !== 'corotational_connected_frame2d.v1'
    )
  ) {
    errors.push('published result contract is unsupported')
    return { value: null, integrityUnavailable: false }
  }
  const ir = value.engineering_result_ir
  const bindings = value.contract_bindings
  const authority = value.authority
  if (
    !validEngineeringResultIrShape(ir)
    || !record(bindings)
    || !record(authority)
    || !hash(value.result_hash)
    || value.source_result_hash !== ir.engineering_result_hash
    || bindings.engineering_result_hash !== ir.engineering_result_hash
    || bindings.engineering_array_bundle_hash !== ir.array_bundle_hash
    || bindings.quantity_catalog_hash !== ir.quantity_catalog_hash
  ) {
    errors.push('published engineering ResultIR binding is invalid')
    return { value: null, integrityUnavailable: false }
  }
  const irAuthority = ir.authority_axes
  if (!record(irAuthority)) {
    errors.push('published engineering ResultIR authority axes are invalid')
    return { value: null, integrityUnavailable: false }
  }
  for (const axis of [
    'convergence',
    'displacement',
    'reaction',
    'member_force',
    'member_features',
    'section_resultant',
    'fiber_result',
    'fallback',
    'external_vv',
    'engineering_design',
    'release_readiness',
  ]) {
    if (authority[axis] !== irAuthority[axis]) {
      errors.push(`published engineering ResultIR authority axis is invalid: ${axis}`)
      return { value: null, integrityUnavailable: false }
    }
  }
  const manifest = ir as unknown as EngineeringResultIrManifest
  // The Python producer's canonical float spelling (for example 1.0 and -0.0)
  // cannot be recovered after browser JSON parsing. The raw artifact SHA and
  // core validation report bind the full manifest/result. Array descriptors
  // contain only strings and integers, so their bundle hash is safe to replay.
  const arrayBundleHash = await sha256Hex(canonicalJson(ir.array_descriptors))
  const integrityUnavailable = arrayBundleHash === null
  if (arrayBundleHash !== null && arrayBundleHash !== ir.array_bundle_hash) {
    errors.push('published engineering ResultIR array bundle hash is invalid')
    return { value: null, integrityUnavailable }
  }
  return { value: manifest, integrityUnavailable }
}

function validEngineeringResultIrShape(value: unknown): value is Record<string, unknown> {
  if (!record(value)) return false
  const requiredHashes = [
    'engineering_result_hash',
    'compiler_hash',
    'source_adapter_hash',
    'model_content_hash',
    'problem_contract_hash',
    'terminal_checkpoint_hash',
    'terminal_assembly_hash',
    'quantity_catalog_hash',
    'array_bundle_hash',
  ]
  const counts = value.counts
  const descriptors = value.array_descriptors
  return value.schema_version === 'corotational-fiber-frame2d-engineering-result-ir.v1'
    && typeof value.engineering_result_id === 'string'
    && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(value.engineering_result_id)
    && typeof value.result_kind === 'string'
    && typeof value.recovery_profile === 'string'
    && typeof value.authority_profile === 'string'
    && requiredHashes.every((key) => hash(value[key]))
    && value.load_factor === 1
    && record(counts)
    && integerInRange(counts.node, 2, 128)
    && integerInRange(counts.member, 1, 256)
    && integerInRange(counts.section, 1)
    && integerInRange(counts.fiber, 1)
    && stringArray(value.member_ids, 1, 256, true)
    && (value.member_ids as string[]).length === counts.member
    && record(value.metrics)
    && record(value.authority_axes)
    && stringArray(value.limitations, 1)
    && Array.isArray(descriptors)
    && descriptors.length === 18
    && descriptors.every(validArrayDescriptor)
}

function validArrayDescriptor(value: unknown): boolean {
  if (!record(value)) return false
  return typeof value.name === 'string'
    && value.name.length > 0
    && (value.dtype === '<f8' || value.dtype === '<i8')
    && Array.isArray(value.shape)
    && value.shape.length > 0
    && value.shape.every((item) => integerInRange(item, 0))
    && typeof value.unit === 'string'
    && value.unit.length > 0
    && stringArray(value.quantity_ids, 0, undefined, true)
    && ['node', 'member', 'section', 'fiber'].includes(String(value.order_scope))
    && (value.authority_role === 'output' || value.authority_role === 'mapping')
    && hash(value.order_hash)
    && hash(value.data_hash)
    && hash(value.content_hash)
}

function validCoreValidationReport(report: unknown, result: unknown): boolean {
  if (!record(report) || !record(result)) return false
  return report.schema_version === 'unified-nonlinear-frame-validation-report.v1'
    && report.status === 'ready'
    && report.contract_pass === true
    && report.result_hash === result.result_hash
    && report.profile === result.profile
    && report.exact_engineering_recovery === true
    && report.exact_checkpoint_chain_replay === true
    && report.checkpoint_available === true
    && report.unsupported_feature_count === 0
    && report.fallback_count === 0
    && report.regularization_count === 0
}

function integerInRange(value: unknown, minimum: number, maximum?: number): value is number {
  return typeof value === 'number'
    && Number.isInteger(value)
    && value >= minimum
    && (maximum === undefined || value <= maximum)
}

function stringArray(
  value: unknown,
  minimum: number,
  maximum?: number,
  unique = false,
): value is string[] {
  if (!Array.isArray(value) || value.length < minimum || (maximum !== undefined && value.length > maximum)) return false
  if (!value.every((item) => typeof item === 'string' && item.length > 0)) return false
  return !unique || new Set(value).size === value.length
}

function hash(value: unknown): value is string {
  return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value)
}
