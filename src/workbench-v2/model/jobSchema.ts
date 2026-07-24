// Read-only Workbench projection of the durable job-service contract.
// It deliberately contains references and orchestration state, not solver values.

export type JobStatus = 'queued' | 'running' | 'checkpointed' | 'succeeded' | 'failed' | 'cancelled'
export type JobArtifactRole = 'request' | 'checkpoint' | 'result' | 'evidence'

export interface JobArtifactReference {
  role: JobArtifactRole
  content_hash: string
  byte_length: number
  media_type: string
}

export interface WorkbenchJobView {
  schema_version: 'structural-analysis-job-view.v1'
  service_profile: 'sqlite_wal_content_addressed_single_host.v1'
  job_id: string
  status: JobStatus
  revision: number
  attempt: number
  progress: { completed_steps: number; total_steps: number }
  created_at: string
  updated_at: string
  lease_expires_at: string | null
  error_code: string | null
  can_resume: boolean
  request: JobArtifactReference
  checkpoint: JobArtifactReference | null
  result: JobArtifactReference | null
  evidence: JobArtifactReference | null
  resume_contract_hash: string | null
  solver_truth_owner: 'structural_analysis_core'
  result_authority: 'referenced_result_and_evidence_contracts_only'
  claim_boundary: string
  terminal_event_hash: string
}

export interface JobViewValidation {
  ok: boolean
  value: WorkbenchJobView | null
  errors: string[]
}

const HASH = /^sha256:[0-9a-f]{64}$/
const JOB_ID = /^job_[0-9a-f]{32}$/
const STATUS = new Set<JobStatus>(['queued', 'running', 'checkpointed', 'succeeded', 'failed', 'cancelled'])
const TOP_LEVEL_KEYS = new Set([
  'schema_version', 'service_profile', 'job_id', 'status', 'revision', 'attempt',
  'progress', 'created_at', 'updated_at', 'lease_expires_at', 'error_code',
  'can_resume', 'request', 'checkpoint', 'result', 'evidence',
  'resume_contract_hash', 'solver_truth_owner', 'result_authority',
  'claim_boundary', 'terminal_event_hash',
])

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function exactKeys(value: Record<string, unknown>, expected: ReadonlySet<string>): boolean {
  const keys = Object.keys(value)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}

function artifact(value: unknown, role: JobArtifactRole, path: string, errors: string[]): JobArtifactReference | null {
  if (!record(value) || !exactKeys(value, new Set(['role', 'content_hash', 'byte_length', 'media_type']))) {
    errors.push(`${path} must be one exact artifact reference`)
    return null
  }
  if (value.role !== role) errors.push(`${path}.role must be ${role}`)
  if (typeof value.content_hash !== 'string' || !HASH.test(value.content_hash)) errors.push(`${path}.content_hash is invalid`)
  if (!Number.isInteger(value.byte_length) || (value.byte_length as number) < 0) errors.push(`${path}.byte_length is invalid`)
  if (typeof value.media_type !== 'string' || !/^[a-z0-9.+-]+\/[a-z0-9.+-]+$/.test(value.media_type)) errors.push(`${path}.media_type is invalid`)
  if (errors.some((error) => error.startsWith(path))) return null
  return value as unknown as JobArtifactReference
}

export function validateWorkbenchJobView(raw: unknown): JobViewValidation {
  const errors: string[] = []
  if (!record(raw) || !exactKeys(raw, TOP_LEVEL_KEYS)) {
    return { ok: false, value: null, errors: ['job view must contain the exact v1 fields'] }
  }
  if (raw.schema_version !== 'structural-analysis-job-view.v1') errors.push('schema_version is unsupported')
  if (raw.service_profile !== 'sqlite_wal_content_addressed_single_host.v1') errors.push('service_profile is unsupported')
  if (typeof raw.job_id !== 'string' || !JOB_ID.test(raw.job_id)) errors.push('job_id is invalid')
  if (typeof raw.status !== 'string' || !STATUS.has(raw.status as JobStatus)) errors.push('status is invalid')
  if (!Number.isInteger(raw.revision) || (raw.revision as number) < 0) errors.push('revision is invalid')
  if (!Number.isInteger(raw.attempt) || (raw.attempt as number) < 0) errors.push('attempt is invalid')
  if (!record(raw.progress) || !exactKeys(raw.progress, new Set(['completed_steps', 'total_steps']))) {
    errors.push('progress is invalid')
  }
  const completed = record(raw.progress) ? raw.progress.completed_steps : null
  const total = record(raw.progress) ? raw.progress.total_steps : null
  if (!Number.isInteger(completed) || (completed as number) < 0) errors.push('progress.completed_steps is invalid')
  if (!Number.isInteger(total) || (total as number) < 1 || (completed as number) > (total as number)) errors.push('progress.total_steps is invalid')
  if (typeof raw.created_at !== 'string' || !raw.created_at) errors.push('created_at is invalid')
  if (typeof raw.updated_at !== 'string' || !raw.updated_at) errors.push('updated_at is invalid')
  if (raw.lease_expires_at !== null && typeof raw.lease_expires_at !== 'string') errors.push('lease_expires_at is invalid')
  if (raw.error_code !== null && typeof raw.error_code !== 'string') errors.push('error_code is invalid')
  if (typeof raw.can_resume !== 'boolean') errors.push('can_resume is invalid')
  const request = artifact(raw.request, 'request', 'request', errors)
  const checkpoint = raw.checkpoint === null ? null : artifact(raw.checkpoint, 'checkpoint', 'checkpoint', errors)
  const result = raw.result === null ? null : artifact(raw.result, 'result', 'result', errors)
  const evidence = raw.evidence === null ? null : artifact(raw.evidence, 'evidence', 'evidence', errors)
  if (raw.resume_contract_hash !== null && (typeof raw.resume_contract_hash !== 'string' || !HASH.test(raw.resume_contract_hash))) errors.push('resume_contract_hash is invalid')
  if (raw.solver_truth_owner !== 'structural_analysis_core') errors.push('solver_truth_owner is invalid')
  if (raw.result_authority !== 'referenced_result_and_evidence_contracts_only') errors.push('result_authority is invalid')
  if (typeof raw.claim_boundary !== 'string' || !raw.claim_boundary) errors.push('claim_boundary is missing')
  if (typeof raw.terminal_event_hash !== 'string' || !HASH.test(raw.terminal_event_hash)) errors.push('terminal_event_hash is invalid')

  const status = raw.status as JobStatus
  const published = result !== null && evidence !== null
  if ((result === null) !== (evidence === null)) errors.push('result and evidence must be an atomic pair')
  if (status === 'succeeded' && (!published || completed !== total)) errors.push('succeeded job is not terminal and published')
  if (status !== 'succeeded' && published) errors.push('non-succeeded job exposes published artifacts')
  if ((status === 'running') !== (raw.lease_expires_at !== null)) errors.push('lease expiry does not match running status')
  const expectedResume = checkpoint !== null && (status === 'checkpointed' || status === 'failed')
  if (raw.can_resume !== expectedResume) errors.push('can_resume does not match checkpoint/status')

  if (errors.length || request === null) return { ok: false, value: null, errors }
  return { ok: true, value: raw as unknown as WorkbenchJobView, errors }
}
