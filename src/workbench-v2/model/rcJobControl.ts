import { canonicalJson, sha256Hex } from './checksum'
import { JobArtifactError, readBoundedJobBytes, type RcJobTransport } from './jobTransport'
import type { WorkbenchJobView } from './jobSchema'
import { parseNativeJsonStrict } from './nativeFrameProvider'

const HASH = /^sha256:[0-9a-f]{64}$/
const JOB = /^job_[0-9a-f]{32}$/
const CONTROL = /^rc-control-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const TENANT = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const ACTIONS = ['pause', 'cancel', 'resume'] as const
const STATES = ['available', 'pause_pending', 'cancel_pending', 'paused', 'terminal'] as const
const BOUNDARIES = ['unleased', 'before_analysis', 'verified_checkpoint', 'verified_final', 'lease_expired', 'worker_failure'] as const
export type RcControlAction = typeof ACTIONS[number]
export interface RcJobControlCommand {
  schema_version: 'rc-job-control-request.v1'; control_id: string; action: RcControlAction
  expected_request_hash: string; expected_checkpoint_hash: string | null
  expected_control_revision: number; expected_attempt: number
}
export interface RcJobControlView {
  schema_version: 'rc-job-control.v1'
  job: { job_id: string; tenant_id: string; request_hash: string; checkpoint_hash: string | null; attempt: number; revision: number; status: WorkbenchJobView['status']; terminal_event_hash: string }
  control_revision: number; state: typeof STATES[number]
  last_command: null | { control_id: string; command_hash: string; action: RcControlAction; control_revision: number; requested_event_revision: number; resolved_event_revision: number | null; disposition: 'pending' | 'paused' | 'cancelled' | 'resumed' | 'completed' | 'failed'; boundary: typeof BOUNDARIES[number] | null; applied_checkpoint_hash: string | null; applied_progress: { completed: number; total: number } | null }
  can_pause: boolean; can_cancel: boolean; can_resume_control: boolean
}
export interface RcJobControlIntent { command: RcJobControlCommand; serialized: string; commandHash: string }
export interface RcJobControlReceipt {
  schema_version: 'rc-job-control-command-result.v1'; control_id: string; command_hash: string
  accepted_control_revision: number; view: RcJobControlView
}
export interface RcJobControlCustodyEntry { intent: RcJobControlIntent | null; receipt: RcJobControlReceipt | null; refreshRequired: boolean }
export interface RcJobControlCustody { current: Map<string, RcJobControlCustodyEntry> }
type Obj = Record<string, any>
function requireValue(value: unknown): asserts value { if (!value) throw new JobArtifactError('rc_control_view_invalid') }
function object(value: unknown, keys: string[]): Obj {
  requireValue(value && typeof value === 'object' && !Array.isArray(value))
  const row = value as Obj
  requireValue(Object.keys(row).sort().join(',') === keys.sort().join(','))
  return row
}
const nat = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const isHash = (value: unknown): value is string => typeof value === 'string' && HASH.test(value)
const isControlId = (value: unknown): value is string => typeof value === 'string' && CONTROL.test(value)
const hashOrNull = (value: unknown): boolean => value === null || isHash(value)

export function parseRcJobControl(value: unknown, job: WorkbenchJobView, tenantId: string | undefined): RcJobControlView {
  const v = object(value, ['schema_version', 'job', 'control_revision', 'state', 'last_command', 'can_pause', 'can_cancel', 'can_resume_control'])
  const j = object(v.job, ['job_id', 'tenant_id', 'request_hash', 'checkpoint_hash', 'attempt', 'revision', 'status', 'terminal_event_hash'])
  requireValue(v.schema_version === 'rc-job-control.v1' && STATES.includes(v.state)
    && nat(v.control_revision) && typeof v.can_pause === 'boolean' && typeof v.can_cancel === 'boolean' && typeof v.can_resume_control === 'boolean'
    && typeof tenantId === 'string' && TENANT.test(tenantId) && j.tenant_id === tenantId
    && typeof j.job_id === 'string' && JOB.test(j.job_id) && j.job_id === job.job_id
    && j.request_hash === job.request.content_hash && isHash(j.request_hash)
    && hashOrNull(j.checkpoint_hash) && nat(j.attempt) && j.attempt >= job.attempt
    && nat(j.revision) && j.revision >= job.revision && isHash(j.terminal_event_hash)
    && ['queued', 'running', 'checkpointed', 'succeeded', 'failed', 'cancelled'].includes(j.status))
  requireValue(v.control_revision <= j.revision)
  if (j.status === 'queued') requireValue(j.checkpoint_hash === null)
  if (j.status === 'checkpointed') requireValue(j.checkpoint_hash !== null)
  if (j.revision === job.revision) requireValue(j.attempt === job.attempt && j.status === job.status
    && j.checkpoint_hash === (job.checkpoint?.content_hash ?? null) && j.terminal_event_hash === job.terminal_event_hash)
  const terminal = ['succeeded', 'failed', 'cancelled'].includes(j.status)
  requireValue((v.state === 'terminal') === terminal)
  if (v.last_command === null) requireValue(v.control_revision === 0 && ['available', 'terminal'].includes(v.state))
  else {
    const c = object(v.last_command, ['control_id', 'command_hash', 'action', 'control_revision', 'requested_event_revision', 'resolved_event_revision', 'disposition', 'boundary', 'applied_checkpoint_hash', 'applied_progress'])
    requireValue(isControlId(c.control_id) && isHash(c.command_hash) && ACTIONS.includes(c.action)
      && nat(c.control_revision) && c.control_revision > 0 && c.control_revision === v.control_revision
      && nat(c.requested_event_revision) && c.requested_event_revision >= c.control_revision && c.requested_event_revision <= j.revision
      && ['pending', 'paused', 'cancelled', 'resumed', 'completed', 'failed'].includes(c.disposition)
      && hashOrNull(c.applied_checkpoint_hash))
    if (c.disposition === 'pending') requireValue(c.resolved_event_revision === null && c.boundary === null
      && c.applied_checkpoint_hash === null && c.applied_progress === null && j.status === 'running'
      && v.state === (c.action === 'pause' ? 'pause_pending' : c.action === 'cancel' ? 'cancel_pending' : 'invalid'))
    else {
      requireValue(nat(c.resolved_event_revision) && c.resolved_event_revision > c.requested_event_revision && c.resolved_event_revision <= j.revision && BOUNDARIES.includes(c.boundary))
      const progress = object(c.applied_progress, ['completed', 'total'])
      requireValue(nat(progress.completed) && nat(progress.total) && progress.total > 0 && progress.completed <= progress.total)
      if (c.disposition === 'paused') requireValue(c.action === 'pause' && v.state === 'paused' && ['queued', 'checkpointed'].includes(j.status) && c.applied_checkpoint_hash === j.checkpoint_hash && ['unleased', 'before_analysis', 'verified_checkpoint', 'lease_expired'].includes(c.boundary))
      if (c.disposition === 'cancelled') requireValue(c.action === 'cancel' && j.status === 'cancelled' && c.boundary !== 'worker_failure')
      if (c.disposition === 'resumed') requireValue(c.action === 'resume' && ['available', 'terminal'].includes(v.state) && c.boundary === 'unleased')
      if (c.disposition === 'completed') requireValue(c.action === 'pause' && j.status === 'succeeded' && c.boundary === 'verified_final')
      if (c.disposition === 'failed') requireValue(c.action !== 'resume' && ['available', 'terminal'].includes(v.state) && c.boundary === 'worker_failure')
    }
  }
  if (['pause_pending', 'cancel_pending', 'paused'].includes(v.state)) requireValue(v.last_command !== null)
  requireValue(v.can_pause === (v.state === 'available')
    && v.can_cancel === ['available', 'pause_pending', 'paused'].includes(v.state)
    && v.can_resume_control === (v.state === 'paused'))
  return v as RcJobControlView
}

export function parseRcControlCommand(value: unknown): RcJobControlCommand {
  const c = object(value, ['schema_version', 'control_id', 'action', 'expected_request_hash', 'expected_checkpoint_hash', 'expected_control_revision', 'expected_attempt'])
  requireValue(c.schema_version === 'rc-job-control-request.v1' && isControlId(c.control_id) && ACTIONS.includes(c.action)
    && isHash(c.expected_request_hash) && hashOrNull(c.expected_checkpoint_hash) && nat(c.expected_control_revision) && nat(c.expected_attempt))
  return c as RcJobControlCommand
}
export async function createRcControlIntent(view: RcJobControlView, action: RcControlAction, id = `rc-control-${crypto.randomUUID()}`): Promise<RcJobControlIntent> {
  if (!Number.isSafeInteger(view.control_revision + 1)) throw new JobArtifactError('rc_control_revision_limit')
  if (!(action === 'pause' ? view.can_pause : action === 'cancel' ? view.can_cancel : view.can_resume_control)) throw new JobArtifactError('rc_control_state_conflict')
  const command = parseRcControlCommand({ schema_version: 'rc-job-control-request.v1', control_id: id, action,
    expected_request_hash: view.job.request_hash, expected_checkpoint_hash: view.job.checkpoint_hash,
    expected_control_revision: view.control_revision, expected_attempt: view.job.attempt })
  const serialized = canonicalJson(command), commandHash = await sha256Hex(serialized)
  if (!commandHash) throw new JobArtifactError('rc_control_integrity_unavailable')
  return { command: Object.freeze(command), serialized, commandHash }
}
export async function parseRcControlReceipt(value: unknown, intent: RcJobControlIntent, job: WorkbenchJobView, tenantId?: string): Promise<RcJobControlReceipt> {
  const r = object(value, ['schema_version', 'control_id', 'command_hash', 'accepted_control_revision', 'view'])
  requireValue(r.schema_version === 'rc-job-control-command-result.v1' && isControlId(r.control_id) && isHash(r.command_hash) && r.control_id === intent.command.control_id && r.command_hash === intent.commandHash
    && nat(r.accepted_control_revision) && r.accepted_control_revision === intent.command.expected_control_revision + 1)
  const view = parseRcJobControl(r.view, job, tenantId)
  requireValue(view.control_revision >= r.accepted_control_revision)
  if (view.control_revision === r.accepted_control_revision) {
    const latest = view.last_command
    requireValue(latest && latest.control_id === r.control_id && latest.command_hash === r.command_hash && latest.action === intent.command.action)
  }
  return { ...r, view } as RcJobControlReceipt
}
async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  try {
    const raw = new TextDecoder('utf-8', { fatal: true }).decode(await readBoundedJobBytes(response, 16 * 1024, 'rc_control'))
    const value = parseNativeJsonStrict(raw)
    // Every numeric field is an integer counter. Reject decimal/exponent
    // tokens before Number rounding can disguise them as valid integers.
    const numbers = raw.replace(/"(?:\\.|[^"\\])*"/g, '""').match(/-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g) ?? []
    if (numbers.some(token => !/^-?(?:0|[1-9]\d*)$/.test(token) || !nat(Number(token)))) throw new Error('integer token required')
    return value
  }
  catch { throw new JobArtifactError('rc_control_response_invalid') }
}
export async function loadRcJobControl(transport: RcJobTransport, job: WorkbenchJobView): Promise<RcJobControlView | null> {
  if (!transport.getRcControl || !transport.tenantId) return null
  const response = await transport.getRcControl(job.job_id)
  if (response.status === 404) { await response.body?.cancel(); await transport.verifyAuthorizationScope(); return null }
  const result = parseRcJobControl(await readJson(response), job, transport.tenantId)
  await transport.verifyAuthorizationScope()
  return result
}
export class RcControlUnconfirmedError extends Error { constructor() { super('rc_control_outcome_unconfirmed') } }
export class RcControlConflictError extends Error { constructor() { super('rc_control_refresh_required') } }
export async function postRcJobControl(transport: RcJobTransport, job: WorkbenchJobView, intent: RcJobControlIntent): Promise<RcJobControlReceipt> {
  if (!transport.postRcControl || !transport.tenantId) throw new JobArtifactError('rc_control_unsupported')
  // Custody may outlive a panel generation; reject edited/reconstructed retries.
  const canonical = canonicalJson(parseRcControlCommand(intent.command))
  if (canonical !== intent.serialized || await sha256Hex(canonical) !== intent.commandHash || intent.command.expected_request_hash !== job.request.content_hash) throw new JobArtifactError('rc_control_command_invalid')
  try {
    const response = await transport.postRcControl(job.job_id, intent.serialized)
    if (response.status === 400 || response.status === 409) { await response.body?.cancel(); throw new RcControlConflictError() }
    const result = await parseRcControlReceipt(await readJson(response), intent, job, transport.tenantId)
    await transport.verifyAuthorizationScope()
    return result
  } catch (error) {
    if (error instanceof RcControlConflictError || /authorization|job_api_http_(?:401|403)$/.test(error instanceof Error ? error.message : '')) throw error
    throw new RcControlUnconfirmedError()
  }
}
