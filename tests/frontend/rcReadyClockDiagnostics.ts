import type { Page, TestInfo } from '@playwright/test'
import { performance as nodePerformance } from 'node:perf_hooks'
import { createHash } from 'node:crypto'
import { finishRcInitialReadyDiagnostics } from './rcInitialReadyDiagnostics'

// Diagnostic-only candidate. No clock equivalence or exact internal deadline is asserted.
const nodeWallNow = Date.now.bind(Date)
const MAX_CLOCK_ROWS = 32, MAX_CLOCK_BYTES = 16 * 1024, MAX_COMBINED_BYTES = 128 * 1024
type Expected = 'queued' | 'failed' | 'checkpointed' | 'cancelled'
type ClockStatus = 'available' | 'unavailable' | 'invalid' | 'error'
interface NodeStamp { clockStatus: ClockStatus; monotonicMs: number | null; timeOriginMs: number | null; wallMs: number | null }
interface Boundary { expected: Expected; before: NodeStamp; after: NodeStamp | null; outcome: 'unobserved' | 'passed' | 'failed'; nominalTimeoutMs: 5000; nominalDeadlineMonotonicMs: number | null }
export interface RcReadyBoundaryToken { readonly kind: 'rc-ready-boundary-token.v1' }
interface State { enabled: boolean; begun: boolean; boundary: Boundary | null }
const states = new WeakMap<Page, State>(), tokens = new WeakMap<RcReadyBoundaryToken, Boundary>()
interface AwaitObserver { begin(expected: Expected): object | undefined; end(token: object): unknown }
const awaitObservations = new WeakMap<Boundary, { observer: AwaitObserver; token: object; capture?: unknown }>()
function awaitObserver(): AwaitObserver | undefined {
  return (globalThis as unknown as Record<symbol, AwaitObserver | undefined>)[Symbol.for('structural.rc.expect-await.v1')]
}
const clockStatuses = new Set(['available', 'unavailable', 'invalid', 'error'])
const jobStatuses = new Set(['queued', 'failed', 'checkpointed', 'cancelled', 'succeeded', 'absent', 'ambiguous', 'invalid', 'unobserved'])
const rowKeys = ['schema', 'session', 'generation', 'sequence', 'clockSource', 'clockStatus',
  'realMonotonicMs', 'realTimeOriginMs', 'realWallMs', 'exposedClockStatus', 'exposedMonotonicMs',
  'exposedTimeOriginMs', 'exposedWallMs', 'domStatus', 'projectCount', 'readyCount', 'storedInputCount', 'jobStatus'].sort().join(',')
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value) }
function exact(value: Record<string, unknown>, keys: string): boolean { return Object.keys(value).sort().join(',') === keys }
function finite(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER }
function stamp(): NodeStamp {
  const empty: NodeStamp = { clockStatus: 'unavailable', monotonicMs: null, timeOriginMs: null, wallMs: null }
  try {
    const values = [nodePerformance.now(), nodePerformance.timeOrigin, nodeWallNow()]
    if (!values.every(finite)) return { ...empty, clockStatus: 'invalid' }
    return { clockStatus: 'available', monotonicMs: values[0], timeOriginMs: values[1], wallMs: values[2] }
  } catch { return { ...empty, clockStatus: 'error' } }
}

/** Node-only opt-in; introduces no page command or awaited pre-assertion probe. */
export function enableRcReadyClockDiagnostics(page: Page, enabled: boolean): void {
  try {
    const previous = states.get(page)
    if (previous) previous.enabled = enabled
    else states.set(page, { enabled, begun: false, boundary: null })
  } catch { /* Optional observations never replace an operation outcome. */ }
}
/** Only the first original attribute-ready assertion on this Page is observed. */
export function beginRcReadyBoundary(page: Page, expected: Expected): RcReadyBoundaryToken | undefined {
  try {
    const state = states.get(page)
    if (!state?.enabled || state.begun || !['queued', 'failed', 'checkpointed', 'cancelled'].includes(expected)) return undefined
    state.begun = true
    const before = stamp(), nominal = before.monotonicMs === null ? null : before.monotonicMs + 5000
    const boundary: Boundary = { expected, before, after: null, outcome: 'unobserved', nominalTimeoutMs: 5000,
      nominalDeadlineMonotonicMs: finite(nominal) ? nominal : null }
    const token: RcReadyBoundaryToken = Object.freeze({ kind: 'rc-ready-boundary-token.v1' })
    state.boundary = boundary; tokens.set(token, boundary)
    try {
      const observer = awaitObserver(), observerToken = observer?.begin(expected)
      if (observer && observerToken) awaitObservations.set(boundary, { observer, token: observerToken })
    } catch { /* Retain the existing clock boundary even if the optional observer fails. */ }
    return token
  } catch { return undefined }
}
export function finishRcReadyBoundary(token: RcReadyBoundaryToken | undefined, passed: boolean): void {
  try {
    if (!token) return
    const boundary = tokens.get(token)
    if (!boundary || boundary.after !== null) return
    boundary.after = stamp(); boundary.outcome = passed ? 'passed' : 'failed'
    tokens.delete(token)
    const observation = awaitObservations.get(boundary)
    if (observation) observation.capture = observation.observer.end(observation.token)
  } catch { /* No exception can supersede the original assertion. */ }
}

function commitKeys(body: Buffer): Set<string> | null {
  try {
    const capture: unknown = JSON.parse(body.toString('utf8'))
    if (!object(capture) || !exact(capture, 'overflow,rows') || capture.overflow !== false
      || !Array.isArray(capture.rows) || capture.rows.length > 512 || body.length > MAX_COMBINED_BYTES) return null
    const keys = new Set<string>()
    for (const row of capture.rows) {
      if (!object(row) || !exact(row, 'generation,monotonic_ms,phase,schema,sequence,session') || row.schema !== 1
        || !Number.isSafeInteger(row.session) || (row.session as number) <= 0
        || !Number.isSafeInteger(row.generation) || (row.generation as number) < 0
        || !Number.isSafeInteger(row.sequence) || (row.sequence as number) <= 0 || (row.sequence as number) > 256
        || typeof row.phase !== 'string' || typeof row.monotonic_ms !== 'number'
        || !Number.isFinite(row.monotonic_ms) || row.monotonic_ms < 0) return null
      if (row.phase === 'ui.ready.commit') {
        const key = `${row.session}:${row.generation}:${row.sequence}`
        if (keys.has(key)) return null
        keys.add(key)
      }
    }
    return keys
  } catch { return null }
}
function clockValues(status: unknown, values: unknown[]): boolean {
  return typeof status === 'string' && clockStatuses.has(status)
    && (status === 'available' ? values.every(finite) : values.every(value => value === null))
}
function validNodeStamp(value: unknown): value is NodeStamp {
  return object(value) && exact(value, 'clockStatus,monotonicMs,timeOriginMs,wallMs')
    && clockValues(value.clockStatus, [value.monotonicMs, value.timeOriginMs, value.wallMs])
}
function validBoundary(value: unknown): value is Boundary | null {
  if (value === null) return true
  if (!object(value) || !exact(value, 'after,before,expected,nominalDeadlineMonotonicMs,nominalTimeoutMs,outcome')
    || !['queued', 'failed', 'checkpointed', 'cancelled'].includes(value.expected as string)
    || !validNodeStamp(value.before) || value.nominalTimeoutMs !== 5000) return false
  const expectedDeadline = value.before.monotonicMs === null ? null : value.before.monotonicMs + 5000
  if (value.nominalDeadlineMonotonicMs !== (finite(expectedDeadline) ? expectedDeadline : null)) return false
  return value.after === null ? value.outcome === 'unobserved' : validNodeStamp(value.after)
    && ['passed', 'failed'].includes(value.outcome as string)
    && (value.before.monotonicMs === null || value.after.monotonicMs === null || value.after.monotonicMs >= value.before.monotonicMs)
}
function count(value: unknown): value is number { return value === 0 || value === 1 || value === 2 }
function validCapture(value: unknown): value is { schema: 1; rows: Record<string, unknown>[]; overflow: boolean } {
  if (!object(value) || !exact(value, 'overflow,rows,schema') || value.schema !== 1
    || typeof value.overflow !== 'boolean' || !Array.isArray(value.rows) || value.rows.length > MAX_CLOCK_ROWS
    || Object.keys(value.rows).length !== value.rows.length) return false
  return Array.from(value.rows).every(row => {
    if (!object(row) || !exact(row, rowKeys) || row.schema !== 1
      || !Number.isSafeInteger(row.session) || (row.session as number) <= 0
      || !Number.isSafeInteger(row.generation) || (row.generation as number) < 0
      || !Number.isSafeInteger(row.sequence) || (row.sequence as number) <= 0 || (row.sequence as number) > 256
      || !['retained_pwClock_builtins', 'global_without_pwClock', 'unavailable'].includes(row.clockSource as string)
      || !clockValues(row.clockStatus, [row.realMonotonicMs, row.realTimeOriginMs, row.realWallMs])
      || !clockValues(row.exposedClockStatus, [row.exposedMonotonicMs, row.exposedTimeOriginMs, row.exposedWallMs])
      || row.clockSource === 'unavailable' && !['unavailable', 'error'].includes(row.clockStatus as string)
      || !jobStatuses.has(row.jobStatus as string)) return false
    if (row.domStatus === 'error') return row.projectCount === null && row.readyCount === null
      && row.storedInputCount === null && row.jobStatus === 'unobserved'
    if (!count(row.projectCount) || !count(row.readyCount) || !count(row.storedInputCount)
      || row.projectCount === 0 && (row.readyCount !== 0 || row.storedInputCount !== 0)) return false
    if (row.domStatus === 'ambiguous') return (row.projectCount === 2 || row.readyCount === 2) && row.jobStatus === 'ambiguous'
    return row.domStatus === 'available' && row.projectCount <= 1 && row.readyCount <= 1
      && (row.readyCount === 0 ? row.jobStatus === 'absent' : row.jobStatus !== 'absent'
        && row.jobStatus !== 'ambiguous' && row.jobStatus !== 'unobserved')
  })
}

/** Existing phase collector runs exactly once; its schema, ledger and attachment behavior remain unchanged. */
export async function finishRcInitialReadyDiagnosticsWithClock(page: Page, testInfo: TestInfo, pendingGates: Iterable<() => void>) {
  let phaseBody: Buffer | undefined
  const phaseLedger = await finishRcInitialReadyDiagnostics(page, testInfo, pendingGates, async body => {
    await testInfo.attach('rc-initial-ready-phases', { body, contentType: 'application/json' })
    phaseBody = body // Retain the exact Buffer successfully passed to the unchanged attachment path.
  })
  const originalStatus = testInfo.status, originalErrors = [...testInfo.errors]
  const state = states.get(page)
  // Server-side diagnostic snapshot was closed synchronously with the original
  // assertion. It does not issue page commands or alter the existing phase ledger.
  try {
    const observation = state?.boundary && awaitObservations.get(state.boundary)
    if (observation?.capture) {
      const body = Buffer.from(JSON.stringify(observation.capture), 'utf8')
      if (body.length <= 64 * 1024) await testInfo.attach('rc-initial-ready-await-observation', { body, contentType: 'application/json' })
    }
  } catch { /* Optional attachment failure does not replace the original outcome. */ }
  let retrieval = 'disabled', binding = 'not_attempted', serialization = 'not_attempted', attachment = 'not_attempted'
  let data = 'unobserved', boundaryStatus = state?.boundary ? 'observed' : 'absent'
  try {
    if (state?.enabled) {
      retrieval = 'error'
      const observed: unknown = await page.evaluate(() => (window as unknown as { __RC_INITIAL_READY_CLOCK__?: unknown }).__RC_INITIAL_READY_CLOCK__ ?? null)
      retrieval = observed === null || observed === undefined ? 'absent' : 'invalid'
      if (validCapture(observed)) {
        retrieval = observed.overflow ? 'overflow' : 'present'
        if (!observed.overflow) {
          const keys = phaseBody && phaseLedger.attachment === 'complete' ? commitKeys(phaseBody) : null
          const seen = new Set<string>()
          binding = keys ? 'bound' : 'phase_unavailable'
          for (const row of observed.rows) {
            const key = `${row.session}:${row.generation}:${row.sequence}`
            if (!keys?.has(key) || seen.has(key)) binding = 'invalid'
            seen.add(key)
          }
          if (binding === 'bound' && !validBoundary(state.boundary)) binding = 'invalid'
          if (binding === 'bound' && phaseBody) {
            const boundary = state.boundary
            boundaryStatus = boundary?.after ? 'complete' : boundary ? 'incomplete' : 'absent'
            data = observed.rows.length === 0 ? 'empty' : observed.rows.every(row => row.clockStatus === 'available'
              && row.exposedClockStatus === 'available' && row.domStatus === 'available')
              && boundary?.before.clockStatus === 'available' && boundary.after?.clockStatus === 'available' ? 'complete' : 'partial'
            const body = Buffer.from(JSON.stringify({ schema: 1, clockCapture: observed, readyBoundary: boundary,
              deadlineInterpretation: 'nominal_call_start_plus_5000ms_not_internal_deadline',
              clockInterpretation: 'separate_domains_no_exact_conversion',
              collectionInterpretation: 'after_original_phase_cleanup_not_deadline_snapshot',
              phaseBinding: { bytes: phaseBody.length, sha256: createHash('sha256').update(phaseBody).digest('hex') } }), 'utf8')
            serialization = body.length <= MAX_CLOCK_BYTES && body.length + phaseBody.length <= MAX_COMBINED_BYTES ? 'complete' : 'oversize'
            if (serialization === 'complete') {
              try { await testInfo.attach('rc-initial-ready-clock-observation', { body, contentType: 'application/json' }); attachment = 'complete' }
              catch { attachment = 'error' }
            }
          }
        }
      }
    }
  } catch { if (retrieval === 'present') serialization = 'error'; else retrieval = 'error' }
  const outcome = testInfo.status === originalStatus && testInfo.errors.length === originalErrors.length
    && originalErrors.every((error, index) => testInfo.errors[index] === error) ? 'retained' : 'changed'
  // This independent fixed-enum ledger makes no change to hosted passing qualification.
  try { testInfo.annotations.push({ type: 'rc-initial-ready-clock-ledger', description: JSON.stringify({ schema: 1,
    retrieval, binding, serialization, attachment, data, boundaryStatus, originalOutcome: outcome,
    retention: attachment === 'complete' && outcome === 'retained' ? 'retained' : 'unqualified' }) }) }
  catch { /* An optional annotation cannot replace the original outcome. */ }
  return phaseLedger
}
