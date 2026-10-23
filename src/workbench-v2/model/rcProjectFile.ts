import type { WorkbenchJobView } from './jobSchema'
import { SUBMIT_MAX_BYTES } from './jobTransport'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { validateRcRequestProfile } from './rcJobSchema'
import type { RcScenarioIntent } from './rcScenarioComparison'

export const RC_PROJECT_MAX_BYTES = 96 * 1024 * 1024
export interface RcProjectScope { collectionUrl: string; tenantId: string | null }
export interface RcProjectJobRef { jobId: string; requestHash: string }
export interface RcProjectScenario { intent: RcScenarioIntent; attempted: boolean; job: RcProjectJobRef | null }
/** Portable authoring state and untrusted job references, never saved result or authorization authority. */
export interface RcProjectFile {
  schema: 'rc-workbench-project.v1'
  scope: RcProjectScope
  draft: string
  submission: { serialized: string; idempotencyKey: string; job: RcProjectJobRef | null } | null
  selectedJob: RcProjectJobRef | null
  changedRun: { original: RcProjectJobRef; child: RcProjectJobRef | null } | null
  scenarios: RcProjectScenario[]
  baselineId: string | null
  variantId: string | null
}

const JOB_ID = /^job_[0-9a-f]{32}$/
const HASH = /^sha256:[0-9a-f]{64}$/
const SCENARIO_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,110}$/
const PRIMARY_KEY = /^rc-ui-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const encoder = new TextEncoder()
function check(condition: unknown, code: string): asserts condition { if (!condition) throw new Error(`rc_project_${code}`) }
function exact(value: unknown, keys: string[], label: string): Record<string, unknown> {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), `${label}_invalid`)
  const record = value as Record<string, unknown>, actual = Object.keys(record)
  check(actual.length === keys.length && actual.every(key => keys.includes(key)), `${label}_fields_invalid`)
  return record
}
function boundedText(value: unknown, maximum: number, label: string): string {
  // UTF-16 length is a cheap preliminary bound before allocating encoded bytes.
  check(typeof value === 'string' && value.length <= maximum && encoder.encode(value).byteLength <= maximum, `${label}_too_large`)
  return value
}
function scope(value: unknown): RcProjectScope {
  const raw = exact(value, ['collectionUrl', 'tenantId'], 'scope')
  check(typeof raw.collectionUrl === 'string' && raw.collectionUrl.length <= 8192, 'scope_url_invalid')
  let url: URL
  try { url = new URL(raw.collectionUrl) } catch { throw new Error('rc_project_scope_url_invalid') }
  check(/^https?:$/.test(url.protocol) && !url.username && !url.password && !url.search && !url.hash
    && !raw.collectionUrl.includes('?') && !raw.collectionUrl.includes('#'), 'scope_url_invalid')
  url.pathname = url.pathname.replace(/\/+$/, '')
  check(url.href === raw.collectionUrl, 'scope_url_not_normalized')
  check(raw.tenantId === null || (typeof raw.tenantId === 'string' && /^[\x21-\x7e]{1,256}$/.test(raw.tenantId)), 'scope_tenant_invalid')
  return { collectionUrl: raw.collectionUrl, tenantId: raw.tenantId as string | null }
}
function request(value: unknown, label: string): string {
  const text = boundedText(value, SUBMIT_MAX_BYTES, label)
  check(text.length > 0, `${label}_invalid`)
  validateRcRequestProfile(parseNativeJsonStrict(text))
  return text
}
function jobReference(value: unknown): RcProjectJobRef {
  const raw = exact(value, ['jobId', 'requestHash'], 'job_reference')
  check(typeof raw.jobId === 'string' && JOB_ID.test(raw.jobId)
    && typeof raw.requestHash === 'string' && HASH.test(raw.requestHash), 'job_reference_invalid')
  return { jobId: raw.jobId as string, requestHash: raw.requestHash as string }
}
export function rcProjectJobRef(job: WorkbenchJobView): RcProjectJobRef {
  return jobReference({ jobId: job.job_id, requestHash: job.request.content_hash })
}

function validateProject(value: unknown, expectedScope?: RcProjectScope): RcProjectFile {
  const raw = exact(value, ['schema', 'scope', 'draft', 'submission', 'selectedJob', 'changedRun', 'scenarios', 'baselineId', 'variantId'], 'file')
  check(raw.schema === 'rc-workbench-project.v1', 'schema_unsupported')
  const parsedScope = scope(raw.scope)
  if (expectedScope !== undefined) {
    const expected = scope(expectedScope)
    check(parsedScope.collectionUrl === expected.collectionUrl && parsedScope.tenantId === expected.tenantId, 'scope_mismatch')
  }
  const draft = boundedText(raw.draft, SUBMIT_MAX_BYTES, 'draft')
  // A job may appear in several UI roles, but its request identity must agree.
  const jobHashes = new Map<string, string>()
  function reference(value: unknown): RcProjectJobRef {
    const ref = jobReference(value), previous = jobHashes.get(ref.jobId)
    check(previous === undefined || previous === ref.requestHash, 'job_request_conflict')
    jobHashes.set(ref.jobId, ref.requestHash)
    return ref
  }
  let submission: RcProjectFile['submission'] = null
  if (raw.submission !== null) {
    const item = exact(raw.submission, ['serialized', 'idempotencyKey', 'job'], 'submission')
    const serialized = request(item.serialized, 'submission_request')
    check(serialized === draft, 'submission_draft_mismatch')
    check(typeof item.idempotencyKey === 'string' && PRIMARY_KEY.test(item.idempotencyKey), 'submission_key_invalid')
    submission = { serialized, idempotencyKey: item.idempotencyKey, job: item.job === null ? null : reference(item.job) }
  }
  const selectedJob = raw.selectedJob === null ? null : reference(raw.selectedJob)
  let changedRun: RcProjectFile['changedRun'] = null
  if (raw.changedRun !== null) {
    const item = exact(raw.changedRun, ['original', 'child'], 'changed_run')
    const original = reference(item.original), child = item.child === null ? null : reference(item.child)
    check(child === null || child.jobId !== original.jobId, 'changed_run_same_job')
    changedRun = { original, child }
  }
  check(Array.isArray(raw.scenarios) && raw.scenarios.length <= 4, 'scenario_limit')
  const ids = new Set<string>(), keys = new Set<string>()
  const scenarios = raw.scenarios.map(value => {
    const item = exact(value, ['intent', 'attempted', 'job'], 'scenario')
    const intent = exact(item.intent, ['id', 'name', 'serialized', 'idempotencyKey'], 'scenario_intent')
    check(typeof intent.id === 'string' && SCENARIO_ID.test(intent.id) && !ids.has(intent.id), 'scenario_identity_invalid')
    check(typeof intent.name === 'string' && intent.name.length > 0 && intent.name.length <= 80
      && intent.name.trim() === intent.name && !/[\u0000-\u001f\u007f]/.test(intent.name), 'scenario_name_invalid')
    check(typeof intent.idempotencyKey === 'string' && intent.idempotencyKey === `rc-scenario-${intent.id}`
      && !keys.has(intent.idempotencyKey), 'scenario_key_invalid')
    check(typeof item.attempted === 'boolean' && (item.attempted || item.job === null), 'scenario_attempt_invalid')
    ids.add(intent.id); keys.add(intent.idempotencyKey)
    return { intent: { id: intent.id, name: intent.name, serialized: request(intent.serialized, 'scenario_request'), idempotencyKey: intent.idempotencyKey },
      attempted: item.attempted, job: item.job === null ? null : reference(item.job) }
  })
  for (const key of ['baselineId', 'variantId'] as const) {
    const selection = raw[key]
    check(selection === null || (typeof selection === 'string' && ids.has(selection)), 'scenario_selection_invalid')
  }
  return { schema: 'rc-workbench-project.v1', scope: parsedScope, draft, submission, selectedJob, changedRun, scenarios,
    baselineId: raw.baselineId as string | null, variantId: raw.variantId as string | null }
}

export function parseRcProjectFile(text: string, expectedScope: RcProjectScope): RcProjectFile {
  boundedText(text, RC_PROJECT_MAX_BYTES, 'file')
  return validateProject(parseNativeJsonStrict(text), expectedScope)
}

export function serializeRcProjectFile(project: RcProjectFile): string {
  const validated = validateProject(project)
  // Serialize the envelope only: parsing and reserializing native requests here
  // would destroy float tokens and integers outside JavaScript's safe range.
  return boundedText(JSON.stringify(validated, null, 2), RC_PROJECT_MAX_BYTES, 'file')
}
