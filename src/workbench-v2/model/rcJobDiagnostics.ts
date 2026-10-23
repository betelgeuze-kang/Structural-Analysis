import type { WorkbenchJobView } from './jobSchema'
import { JobArtifactError, readBoundedJobBytes, type RcJobTransport } from './jobTransport'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { sha256Bytes } from './checksum'

const HASH = /^sha256:[a-f0-9]{64}$/
const INDEX_LIMIT = 4 * 1024 * 1024
const DETAIL_LIMIT = 8 * 1024 * 1024
const MAX_INVOCATIONS = 4096
type Obj = Record<string, any>
function record(value: unknown): Obj {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new JobArtifactError('rc_diagnostics_invalid')
  return value as Obj
}
function requireValue(value: unknown): asserts value { if (!value) throw new JobArtifactError('rc_diagnostics_invalid') }
const nat = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0
function decode(bytes: Uint8Array): Obj { return record(parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))) }

export interface RcInvocationObservation {
  ordinal: number; content_hash: string; byte_length: number
  schema_version: string; phase: 'analysis' | 'verification'; status: 'returned' | 'raised'
  job_request_hash: string; chunk_request_hash: string
  completed_before: number; completed_after: number; restart_input_sha256: string | null
  timing: { wall_ns: number; process_cpu_ns: number | null }
  unavailable_execution_work: boolean
}
export interface RcJobDiagnostics {
  jobId: string; requestHash: string; pending: number[]; invocations: RcInvocationObservation[]
  analysisWallSeconds: number | null; verificationWallSeconds: number | null
  processCpuSeconds: number | null; unknownWork: boolean
}

/** This validates stored observation metadata, not the numerical result or physical model. */
export function parseRcJobDiagnostics(value: unknown, job: WorkbenchJobView): RcJobDiagnostics {
  const v = record(value), budget = record(v.execution_budget)
  requireValue(v.schema_version === 'bounded-rc-fiber-job-invocation-evidence.v1'
    && v.job_id === job.job_id && v.job_request_hash === job.request.content_hash
    && v.execution_budget_unit === 'reserved_api_invocations'
    && nat(budget.maximum_attempts) && nat(budget.reserved_attempts) && nat(budget.remaining_attempts)
    && budget.reserved_attempts + budget.remaining_attempts === budget.maximum_attempts
    && budget.reserved_attempts <= MAX_INVOCATIONS
    && Array.isArray(v.pending_ordinals) && Array.isArray(v.invocations)
    && v.pending_ordinals.length + v.invocations.length === budget.reserved_attempts)
  const seen = new Set<number>()
  const ordinal = (n: unknown): void => { requireValue(nat(n) && n >= 1 && n <= budget.reserved_attempts && !seen.has(n)); seen.add(n) }
  const pending: number[] = v.pending_ordinals.map((n: unknown) => { ordinal(n); return n as number })
  requireValue(v.pending_execution_work === (pending.length ? 'unknown' : 'none_pending'))
  const invocations: RcInvocationObservation[] = v.invocations.map((raw: unknown) => {
    const row = record(raw), timing = record(row.timing)
    const corotational = job.progress.unit === 'control_solver_attempts'
    const isolatedUnknownCpu = corotational && row.schema_version === 'bounded-rc-corotational-job-invocation.v2'
      && row.status === 'raised' && row.unavailable_execution_work === true && timing.process_cpu_ns === null
    ordinal(row.ordinal)
    requireValue((corotational ? ['bounded-rc-corotational-job-invocation.v1', 'bounded-rc-corotational-job-invocation.v2'].includes(row.schema_version)
      : row.schema_version === 'bounded-rc-fiber-job-invocation.v1')
      && row.job_request_hash === job.request.content_hash && HASH.test(row.chunk_request_hash)
      && HASH.test(row.content_hash) && nat(row.byte_length) && row.byte_length > 0
      && ['analysis', 'verification'].includes(row.phase) && ['returned', 'raised'].includes(row.status)
      && nat(row.completed_before) && nat(row.completed_after) && row.completed_before < row.completed_after
      && row.completed_after <= job.progress.total_steps
      && (row.restart_input_sha256 === null || HASH.test(row.restart_input_sha256))
      && nat(timing.wall_ns) && (nat(timing.process_cpu_ns) || isolatedUnknownCpu) && typeof row.unavailable_execution_work === 'boolean'
      && (row.status !== 'raised' || row.unavailable_execution_work))
    return { ordinal: row.ordinal, content_hash: row.content_hash, byte_length: row.byte_length,
      schema_version: row.schema_version, phase: row.phase, status: row.status,
      job_request_hash: row.job_request_hash, chunk_request_hash: row.chunk_request_hash,
      completed_before: row.completed_before, completed_after: row.completed_after,
      restart_input_sha256: row.restart_input_sha256,
      timing: { wall_ns: timing.wall_ns, process_cpu_ns: timing.process_cpu_ns },
      unavailable_execution_work: row.unavailable_execution_work }
  }).sort((a: RcInvocationObservation, b: RcInvocationObservation) => a.ordinal - b.ordinal)
  // An absent phase or unsafe integer total is unavailable, never zero elapsed work.
  function sum(rows: RcInvocationObservation[], key: 'wall_ns' | 'process_cpu_ns'): number | null {
    if (!rows.length) return null
    if (rows.some(r => r.timing[key] === null)) return null
    const n = rows.reduce((s, r) => s + r.timing[key]!, 0)
    return Number.isSafeInteger(n) ? n / 1e9 : null
  }
  return { jobId: job.job_id, requestHash: job.request.content_hash, pending, invocations,
    analysisWallSeconds: sum(invocations.filter(r => r.phase === 'analysis'), 'wall_ns'),
    verificationWallSeconds: sum(invocations.filter(r => r.phase === 'verification'), 'wall_ns'),
    processCpuSeconds: sum(invocations, 'process_cpu_ns'),
    unknownWork: pending.length > 0 || invocations.some(r => r.unavailable_execution_work) }
}

export async function loadRcJobDiagnostics(transport: RcJobTransport, job: WorkbenchJobView): Promise<RcJobDiagnostics> {
  if (!transport.getRcInvocations) throw new JobArtifactError('rc_diagnostics_unavailable')
  const response = await transport.getRcInvocations(job.job_id)
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  const result = parseRcJobDiagnostics(decode(await readBoundedJobBytes(response, INDEX_LIMIT, 'rc_diagnostics')), job)
  await transport.verifyAuthorizationScope()
  return result
}

export interface RcDiagnosticAttempt {
  targetM: number; committed: boolean; status: string | null; failureType: string | null
  convergence: Array<{ iteration: number; relativeResidual: number }>
}
export interface RcInvocationDetail {
  errorType: string | null; errorCode: string | null; outcomeStatus: string | null; failure: string | null; checks: string[]
  attempts: RcDiagnosticAttempt[]; traceTruncated: boolean
}
const identifier = (v: unknown): string | null => typeof v === 'string' && /^[A-Za-z0-9_.:-]{1,160}$/.test(v) ? v : null

export async function loadRcInvocationDetail(transport: RcJobTransport, job: WorkbenchJobView, observation: RcInvocationObservation): Promise<RcInvocationDetail> {
  if (!transport.getRcInvocations || observation.job_request_hash !== job.request.content_hash) throw new JobArtifactError('rc_diagnostics_invalid')
  requireValue(nat(observation.ordinal) && observation.ordinal >= 1 && observation.ordinal <= 4096
    && HASH.test(observation.content_hash) && nat(observation.byte_length) && observation.byte_length > 0)
  if (observation.byte_length > DETAIL_LIMIT) throw new JobArtifactError('rc_diagnostics_detail_too_large')
  const response = await transport.getRcInvocations(job.job_id, observation.ordinal)
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  const bytes = await readBoundedJobBytes(response, DETAIL_LIMIT, 'rc_diagnostics_detail', observation.byte_length)
  requireValue(await sha256Bytes(bytes) === observation.content_hash)
  const value = decode(bytes)
  for (const key of ['schema_version', 'phase', 'status', 'job_request_hash', 'chunk_request_hash', 'completed_before', 'completed_after', 'restart_input_sha256', 'unavailable_execution_work'] as const) requireValue(value[key] === observation[key])
  requireValue(value.timing?.wall_ns === observation.timing.wall_ns && value.timing?.process_cpu_ns === observation.timing.process_cpu_ns)
  const error = value.error && record(value.error)
  const outcome = value.api_result ?? value.verification_report
  const checks = Array.isArray(value.verification_report?.errors)
    ? value.verification_report.errors.slice(0, 32).map((row: unknown) => identifier(typeof row === 'string' ? row : record(row).code)).filter((s: string | null): s is string => s !== null) : []
  const originalAttempts = outcome?.path?.attempts ?? outcome?.failure?.attempts
  let traceTruncated = false
  const attempts: RcDiagnosticAttempt[] = Array.isArray(originalAttempts) ? originalAttempts.slice(-16).flatMap((attempt: any) => {
    if (!attempt || typeof attempt !== 'object' || typeof attempt.target_control_displacement_m !== 'number'
      || !Number.isFinite(attempt.target_control_displacement_m) || typeof attempt.committed !== 'boolean') { traceTruncated = true; return [] }
    const solver = attempt.step?.trial_solution
    const rows = Array.isArray(solver?.convergence_history) ? solver.convergence_history : []
    traceTruncated ||= rows.length > 128
    return [{ targetM: attempt.target_control_displacement_m, committed: attempt.committed,
      status: identifier(solver?.status ?? attempt.step?.status), failureType: identifier(attempt.failure?.type),
      convergence: rows.slice(-128).flatMap((row: any) => {
        if (row && nat(row.iteration) && typeof row.relative_residual === 'number' && Number.isFinite(row.relative_residual) && row.relative_residual >= 0)
          return [{ iteration: row.iteration, relativeResidual: row.relative_residual }]
        traceTruncated = true; return []
      }) }]
  }) : []
  traceTruncated ||= Array.isArray(originalAttempts) && originalAttempts.length > 16
  const detail = { errorType: identifier(error?.type), errorCode: identifier(error?.code),
    outcomeStatus: identifier(outcome?.status), failure: identifier(outcome?.failure?.code ?? outcome?.failure ?? error?.report?.failure), checks, attempts, traceTruncated }
  await transport.verifyAuthorizationScope()
  return detail
}

export interface RcRequestChange { path: string; before: string; after: string }
/** Bounded, deterministic request diff; an edited run never mutates a stored request/checkpoint. */
export function rcRequestChanges(before: unknown, after: unknown, maximum = 200): { changes: RcRequestChange[]; truncated: boolean } {
  const changes: RcRequestChange[] = []; let truncated = false
  const show = (v: unknown): string => v === undefined ? '(absent)' : JSON.stringify(v).slice(0, 240)
  function walk(a: any, b: any, path: string, depth: number): void {
    if (Object.is(a, b)) return
    if (changes.length >= maximum) { truncated = true; return }
    if (depth < 32 && a && b && typeof a === 'object' && typeof b === 'object' && Array.isArray(a) === Array.isArray(b)) {
      for (const key of [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()) walk(a[key], b[key], `${path}/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`, depth + 1)
    } else changes.push({ path: path || '/', before: show(a), after: show(b) })
  }
  walk(before, after, '', 0)
  return { changes, truncated }
}
