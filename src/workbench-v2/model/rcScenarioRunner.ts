import { validateRcRequestProfile, type RcObject } from './rcJobSchema'
import type { WorkbenchJobView } from './jobSchema'
import { SUBMIT_MAX_BYTES, type RcJobTransport } from './jobTransport'
import { refreshRcJob, submitRcJob, verifyRcSubmissionBinding } from './rcWorkflowProvider'
import type { RcScenarioIntent } from './rcScenarioComparison'
import { parseNativeJsonStrict } from './nativeFrameProvider'

export function captureRcScenario(draft: RcObject, name: string, id = crypto.randomUUID(), authoredText?: string): RcScenarioIntent {
  validateRcRequestProfile(draft)
  // Keep native integer/float tokens and original text when the host retains
  // it. Re-serializing an imported request can change its durable binding even
  // when JavaScript has collapsed e.g. 1.0 and 1 to the same Number value.
  const serialized = authoredText ?? JSON.stringify(draft)
  if (new TextEncoder().encode(serialized).byteLength > SUBMIT_MAX_BYTES) throw new Error('rc_scenario_request_too_large')
  if (authoredText !== undefined) {
    const parsed = parseNativeJsonStrict(authoredText)
    validateRcRequestProfile(parsed)
    if (JSON.stringify(parsed) !== JSON.stringify(draft)) throw new Error('rc_scenario_draft_binding_invalid')
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,110}$/.test(id)) throw new Error('rc_scenario_identity_invalid')
  const label = name.trim()
  if (!label || label.length > 80 || /[\u0000-\u001f\u007f]/.test(label)) throw new Error('rc_scenario_name_invalid')
  return Object.freeze({ id, name: label, serialized, idempotencyKey: `rc-scenario-${id}` })
}


export class RcScenarioUnconfirmedError extends Error { constructor() { super('rc_scenario_submission_unconfirmed') } }
export interface RcScenarioRunOptions {
  signal: AbortSignal; existingJob?: WorkbenchJobView; onJob: (job: WorkbenchJobView) => void
  maximumPolls?: number; pollIntervalMs?: number
}
function wait(ms: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted()
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, ms)
    signal.addEventListener('abort', abort, { once: true })
  })
}
/** Explicit sequential queue building block. No failed-job resume is implicit.
 * Uncertain POST responses retain the exact request and idempotency key; known
 * jobs subsequently use GET only, including after a polling bound is reached.
 */
export async function runRcScenario(transport: RcJobTransport, intent: RcScenarioIntent, options: RcScenarioRunOptions): Promise<WorkbenchJobView> {
  const maximum = options.maximumPolls ?? 120, interval = options.pollIntervalMs ?? 2000
  if (!Number.isSafeInteger(maximum) || maximum < 0 || maximum > 300 || !Number.isSafeInteger(interval) || interval < 0 || interval > 10000) throw new Error('rc_scenario_poll_bound_invalid')
  options.signal.throwIfAborted()
  const bytes = new TextEncoder().encode(intent.serialized)
  let job = options.existingJob
  if (!job) {
    try { job = await submitRcJob(transport, bytes, intent.idempotencyKey) }
    catch (error) {
      if (options.signal.aborted) throw error
      const message = error instanceof Error ? error.message : ''
      if (/authorization|job_api_http_(?:400|401|403|404|409|413)$/.test(message)) throw error
      throw new RcScenarioUnconfirmedError()
    }
    options.onJob(job)
  }
  await verifyRcSubmissionBinding(transport, job, bytes)
  for (let count = 0; count < maximum && !['succeeded', 'failed', 'cancelled'].includes(job.status); count++) {
    await wait(interval, options.signal)
    const next = await refreshRcJob(transport, job.job_id)
    if (next.request.content_hash !== job.request.content_hash) throw new Error('rc_scenario_request_binding_changed')
    job = next; options.onJob(job)
  }
  await transport.verifyAuthorizationScope()
  options.signal.throwIfAborted()
  return job
}
