import type { Page, TestInfo } from '@playwright/test'

const phases = new Set([
  'effect.setup', 'effect.cleanup', 'transport.ready', 'poll.begin', 'poll.error',
  'poll.job.begin', 'poll.job.end', 'poll.failed-load.begin', 'poll.failed-load.end',
  'auth.begin', 'auth.end', 'auth.error', 'scope.begin', 'scope.end', 'scope.changed',
  'http.fetch.begin', 'http.fetch.end', 'http.fetch.error', 'http.cancel.begin', 'http.cancel.settled',
  'body.read.begin', 'body.read.end', 'body.read.error', 'request.hash.begin', 'request.hash.end',
  'request.parse.begin', 'request.parse.end', 'job.load.begin', 'job.parse.begin', 'job.parse.end',
  'job.load.error', 'diagnostic.begin', 'diagnostic.absent', 'ui.ready.queue', 'ui.other.queue',
  'ui.ready.commit', 'trace.cap',
])
export interface DiagnosticLedger {
  readonly schema: 1
  readonly initialStatus: TestInfo['status']
  readonly finalStatus: TestInfo['status']
  readonly initialErrors: number
  readonly finalErrors: number
  readonly originalErrorsRetained: boolean
  readonly releaseAttempts: number
  readonly releaseErrors: number
  readonly pageCleanup: 'complete' | 'closed' | 'error'
  readonly retrieval: 'absent' | 'present' | 'invalid' | 'error'
  readonly rows: number
  readonly overflow: boolean
  readonly bytes: number
  readonly serialization: 'not_attempted' | 'complete' | 'oversize' | 'error'
  readonly attachment: 'not_attempted' | 'complete' | 'error'
  readonly diagnosticQualified: boolean
}
function valid(value: unknown): value is { rows: Record<string, unknown>[]; overflow: boolean } {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  if (Object.keys(value).sort().join(',') !== 'overflow,rows') return false
  const item = value as { rows?: unknown; overflow?: unknown }
  if (!Array.isArray(item.rows) || item.rows.length > 512 || typeof item.overflow !== 'boolean') return false
  return item.rows.every(row => row && typeof row === 'object' && !Array.isArray(row)
    && Object.keys(row).sort().join(',') === 'generation,monotonic_ms,phase,schema,sequence,session'
    && row.schema === 1 && Number.isSafeInteger(row.session) && row.session > 0
    && Number.isSafeInteger(row.generation) && row.generation >= 0
    && Number.isSafeInteger(row.sequence) && row.sequence > 0 && row.sequence <= 256
    && typeof row.phase === 'string' && phases.has(row.phase)
    && Number.isFinite(row.monotonic_ms) && row.monotonic_ms >= 0)
}

/** Diagnostic errors remain observable in a separate ledger; never replace the original test outcome. */
export async function finishRcInitialReadyDiagnostics(page: Page, testInfo: TestInfo, pendingGates: Iterable<() => void>,
  attach: (body: Buffer) => Promise<void> = body => testInfo.attach('rc-initial-ready-phases', { body, contentType: 'application/json' }),
): Promise<Readonly<DiagnosticLedger>> {
  const initialStatus = testInfo.status
  const originalErrors = [...testInfo.errors]
  let releaseAttempts = 0, releaseErrors = 0
  for (const release of [...pendingGates]) {
    releaseAttempts++
    try { release() } catch { releaseErrors++ }
  }
  let pageCleanup: DiagnosticLedger['pageCleanup'] = 'complete'
  try { await page.evaluate(() => (window as unknown as { __rcWorkflowBrowserFile?: { release: () => void } }).__rcWorkflowBrowserFile?.release()) }
  catch { pageCleanup = page.isClosed() ? 'closed' : 'error' }
  let retrieval: DiagnosticLedger['retrieval'] = 'absent', rows = 0, overflow = false, bytes = 0
  let attachment: DiagnosticLedger['attachment'] = 'not_attempted'
  let serialization: DiagnosticLedger['serialization'] = 'not_attempted'
  let observed: unknown
  try { observed = await page.evaluate(() => (window as unknown as { __RC_INITIAL_READY_MARKERS__?: unknown }).__RC_INITIAL_READY_MARKERS__ ?? null) }
  catch { retrieval = 'error' }
  if (retrieval !== 'error' && observed !== null && observed !== undefined) {
    try {
      if (!valid(observed)) retrieval = 'invalid'
      else {
        retrieval = 'present'; rows = observed.rows.length; overflow = observed.overflow
        const raw = JSON.stringify({ rows: observed.rows, overflow: observed.overflow })
        bytes = Buffer.byteLength(raw, 'utf8')
        serialization = bytes <= 128 * 1024 ? 'complete' : 'oversize'
        if (!overflow && serialization === 'complete') {
          try { await attach(Buffer.from(raw, 'utf8')); attachment = 'complete' }
          catch { attachment = 'error' }
        }
      }
    } catch {
      if (retrieval === 'present') serialization = 'error'
      else retrieval = 'invalid'
    }
  }
  const originalErrorsRetained = originalErrors.every((error, index) => testInfo.errors[index] === error)
  const diagnosticQualified = testInfo.status === initialStatus && originalErrorsRetained && testInfo.errors.length === originalErrors.length
    && releaseErrors === 0 && pageCleanup === 'complete'
    && (retrieval === 'absent' || retrieval === 'present' && !overflow && bytes <= 128 * 1024 && attachment === 'complete')
  const ledger = Object.freeze({ schema: 1 as const, initialStatus, finalStatus: testInfo.status,
    initialErrors: originalErrors.length, finalErrors: testInfo.errors.length, originalErrorsRetained, releaseAttempts,
    releaseErrors, pageCleanup, retrieval, rows, overflow, bytes, serialization, attachment, diagnosticQualified })
  testInfo.annotations.push({ type: 'rc-initial-ready-diagnostic-ledger', description: JSON.stringify(ledger) })
  return ledger
}
