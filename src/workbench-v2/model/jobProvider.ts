import { sha256Bytes } from './checksum'
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
