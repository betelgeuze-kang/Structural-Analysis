import { sha256Bytes } from './checksum'
import {
  validateWorkbenchJobView,
  type JobArtifactReference,
  type WorkbenchJobView,
} from './jobSchema'
import type { EngineeringValue, ExplicitValue, TextValue } from './caseSchema'

export type JobLoadStatus = 'unconfigured' | 'loading' | 'ready' | 'missing' | 'invalid' | 'error'

export interface JobLoadResult {
  status: JobLoadStatus
  job: WorkbenchJobView | null
  errors: string[]
  artifactStatus?: 'not_published' | 'verified' | 'integrity_unavailable' | 'invalid'
  resultSummary?: WorkbenchJobResultSummary | null
}

export interface WorkbenchJobResultSummary {
  solverId: TextValue
  controlMode: TextValue
  publicApiAuthority: TextValue
  externalVvAuthority: TextValue
  terminalLoadFactor: EngineeringValue
  terminalEpoch: EngineeringValue
  terminalControlDisplacement: EngineeringValue
  exactEngineeringRecovery: ExplicitValue<boolean>
  exactCheckpointChainReplay: ExplicitValue<boolean>
  fallbackCount: EngineeringValue
  regularizationCount: EngineeringValue
  acceptedStepCount: EngineeringValue
  rejectedStepCount: EngineeringValue
  nodeDisplacementRows: EngineeringValue
  supportReactionRows: EngineeringValue
  memberEndForceRows: EngineeringValue
  sectionResultRows: EngineeringValue
  fiberResultRows: EngineeringValue
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
    if (!record(resultPayload) || resultPayload.schema_version !== 'unified-nonlinear-frame-result.v1') {
      artifactErrors.push('published result contract is unsupported')
    }
    if (
      !record(evidencePayload)
      || evidencePayload.schema_version !== 'structural-analysis-job-completion-evidence.v1'
      || evidencePayload.job_id !== job.job_id
      || evidencePayload.request_hash !== job.request.content_hash
      || evidencePayload.checkpoint_hash !== (job.checkpoint?.content_hash ?? null)
      || evidencePayload.result_artifact_hash !== job.result.content_hash
      || evidencePayload.contract_pass !== true
      || evidencePayload.solver_truth_owner !== 'structural_analysis_core'
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
      artifactStatus: result.integrityUnavailable || evidence.integrityUnavailable
        ? 'integrity_unavailable'
        : 'verified',
      resultSummary: normalizeResultSummary(resultPayload),
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

function unavailable<T>(label: string): ExplicitValue<T> {
  return { state: 'unavailable', reason: `${label} is not present` }
}

function invalid<T>(label: string, detail: string): ExplicitValue<T> {
  return { state: 'invalid', reason: `${label} is invalid (${detail})` }
}

function textValue(recordValue: unknown, key: string, label: string): TextValue {
  if (!record(recordValue) || !(key in recordValue)) return unavailable(label)
  const value = recordValue[key]
  return typeof value === 'string' && value.trim() !== ''
    ? { state: 'available', value }
    : invalid(label, 'expected a non-empty string')
}

function numberValue(
  recordValue: unknown,
  key: string,
  label: string,
  domain: (value: number) => boolean = () => true,
): EngineeringValue {
  if (!record(recordValue) || !(key in recordValue)) return unavailable(label)
  const value = recordValue[key]
  return typeof value === 'number' && Number.isFinite(value) && domain(value)
    ? { state: 'available', value }
    : invalid(label, 'expected a finite value in the declared domain')
}

function booleanValue(recordValue: unknown, key: string, label: string): ExplicitValue<boolean> {
  if (!record(recordValue) || !(key in recordValue)) return unavailable(label)
  const value = recordValue[key]
  return typeof value === 'boolean'
    ? { state: 'available', value }
    : invalid(label, 'expected a boolean')
}

function arrayCount(recordValue: unknown, key: string, label: string): EngineeringValue {
  if (!record(recordValue) || !(key in recordValue)) return unavailable(label)
  const value = recordValue[key]
  return Array.isArray(value)
    ? { state: 'available', value: value.length }
    : invalid(label, 'expected an array')
}

function terminalControlDisplacement(checkpoint: unknown): EngineeringValue {
  if (!record(checkpoint)) return unavailable('checkpoint terminal control displacement')
  if ('terminal_control_displacement_m' in checkpoint) {
    return numberValue(
      checkpoint,
      'terminal_control_displacement_m',
      'checkpoint.terminal_control_displacement_m',
    )
  }
  if ('terminal_monitor_displacement_m' in checkpoint) {
    return numberValue(
      checkpoint,
      'terminal_monitor_displacement_m',
      'checkpoint.terminal_monitor_displacement_m',
    )
  }
  return unavailable('checkpoint terminal control displacement')
}

export function normalizeResultSummary(payload: unknown): WorkbenchJobResultSummary {
  const result = record(payload) ? payload : {}
  const configuration = record(result.configuration) ? result.configuration : undefined
  const checkpoint = record(result.checkpoint) ? result.checkpoint : undefined
  const metrics = record(result.metrics) ? result.metrics : undefined
  const authority = record(result.authority) ? result.authority : undefined
  const nonNegativeInteger = (value: number): boolean => Number.isInteger(value) && value >= 0
  return {
    solverId: textValue(result, 'solver_id', 'solver_id'),
    controlMode: textValue(configuration, 'control_mode', 'configuration.control_mode'),
    publicApiAuthority: textValue(authority, 'public_api', 'authority.public_api'),
    externalVvAuthority: textValue(authority, 'external_vv', 'authority.external_vv'),
    terminalLoadFactor: numberValue(checkpoint, 'terminal_load_factor', 'checkpoint.terminal_load_factor'),
    terminalEpoch: numberValue(checkpoint, 'terminal_epoch', 'checkpoint.terminal_epoch', nonNegativeInteger),
    terminalControlDisplacement: terminalControlDisplacement(checkpoint),
    exactEngineeringRecovery: booleanValue(metrics, 'exact_engineering_recovery', 'metrics.exact_engineering_recovery'),
    exactCheckpointChainReplay: booleanValue(metrics, 'exact_checkpoint_chain_replay', 'metrics.exact_checkpoint_chain_replay'),
    fallbackCount: numberValue(metrics, 'fallback_count', 'metrics.fallback_count', nonNegativeInteger),
    regularizationCount: numberValue(metrics, 'regularization_count', 'metrics.regularization_count', nonNegativeInteger),
    acceptedStepCount: numberValue(metrics, 'accepted_step_count', 'metrics.accepted_step_count', nonNegativeInteger),
    rejectedStepCount: numberValue(metrics, 'rejected_step_count', 'metrics.rejected_step_count', nonNegativeInteger),
    nodeDisplacementRows: arrayCount(result, 'node_displacements', 'node_displacements'),
    supportReactionRows: arrayCount(result, 'support_reactions', 'support_reactions'),
    memberEndForceRows: arrayCount(result, 'member_end_forces', 'member_end_forces'),
    sectionResultRows: arrayCount(result, 'section_results', 'section_results'),
    fiberResultRows: arrayCount(result, 'fiber_results', 'fiber_results'),
  }
}
