import { expect, test, type Page, type Route } from '@playwright/test'
import { createHash } from 'node:crypto'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import type { RcPhaseMarker } from '../../src/workbench-v2/model/rcWorkflowTrace'
import { finishRcInitialReadyDiagnostics } from './rcInitialReadyDiagnostics'

// Empty-model orchestration metadata only. No worker, solver or numerical artifacts.
const base = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const harnessUrl = `${base}/tests/frontend/rc-observer-harness.html`
const firstId = `job_${'a'.repeat(32)}`, secondId = `job_${'b'.repeat(32)}`
const host = { tenantId: 'rc-observer-synthetic', bearerToken: 'synthetic-memory-only-observer-token' }
const routePattern = /\/api\/v1\/jobs(?:\/[^?#]*)?$/
const hash = `sha256:${'c'.repeat(64)}`
const raw = (id: string) => ` {"schema_version":"structural-analysis-job-request.v3","operation":"bounded_rc_fiber_direct_control","case_id":"${id}","source_revision":"${'d'.repeat(40)}","result_contract":"bounded-rc-fiber-job-result.v1","execution_config":{"chunk_target_count":1,"maximum_api_invocations":2},"model":{"schema_version":"structural-analysis-canonical-model.v1","nodes":[],"elements":[]},"config":{"annotation":"원문 보존","preview_number":1.0,"preview_zero":-0.0}} `
const firstRaw = raw('synthetic_observer_first'), secondRaw = raw('synthetic_observer_second')
const badHashRaw = firstRaw.replace('"preview_number":1.0', '"preview_number":1.1')
const digest = (value: string) => `sha256:${createHash('sha256').update(value, 'utf8').digest('hex')}`
function job(id: string, body: string): WorkbenchJobView {
  return { schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: id, status: 'failed', revision: 1, attempt: 1, progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z', lease_expires_at: null,
    error_code: 'synthetic_orchestration_failure', can_resume: false,
    request: { role: 'request', content_hash: digest(body), byte_length: Buffer.byteLength(body, 'utf8'), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'Synthetic observation control only; no structural result is qualified.', terminal_event_hash: hash }
}
type Mode = 'absent' | 'nonfunction' | 'record' | 'getter_throw' | 'callback_throw'
const modes: Mode[] = ['absent', 'nonfunction', 'record', 'getter_throw', 'callback_throw']
interface RequestRow { method: string; role: string; authEqual: boolean; body: Buffer | null }
async function observe(route: Route, rows: RequestRow[]) {
  const request = route.request(), path = new URL(request.url()).pathname
  const role = path.endsWith('/resume') ? 'resume' : path.endsWith('/request') ? 'request'
    : path === `/api/v1/jobs/${firstId}` ? 'first' : path === `/api/v1/jobs/${secondId}` ? 'second' : 'metadata'
  const row = { method: request.method(), role, body: request.postDataBuffer(),
    authEqual: await request.headerValue('x-structural-tenant') === host.tenantId
      && await request.headerValue('authorization') === `Bearer ${host.bearerToken}` }
  rows.push(row)
  return { row, path }
}
async function serve(route: Route, path: string, requestBody?: string) {
  if (path === `/api/v1/jobs/${firstId}`) await route.fulfill({ contentType: 'application/json', body: JSON.stringify(job(firstId, firstRaw)) })
  else if (path === `/api/v1/jobs/${secondId}`) await route.fulfill({ contentType: 'application/json', body: JSON.stringify(job(secondId, secondRaw)) })
  else if (path.endsWith('/request')) await route.fulfill({ contentType: 'application/json', body: requestBody ?? (path.includes(firstId) ? firstRaw : secondRaw) })
  else await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
}
async function start(page: Page, mode: Mode, jobId?: string) {
  await page.addInitScript(({ mode, jobId, host }) => {
    window.__RC_OBSERVER_CONFIG__ = { ...host, jobId }
    if (mode === 'nonfunction') Object.defineProperty(window, '__RC_INITIAL_READY_MARKER_HOOK__', { configurable: true, value: null })
    if (mode === 'getter_throw') Object.defineProperty(window, '__RC_INITIAL_READY_MARKER_HOOK__', { configurable: true, get() { throw new Error('synthetic observer getter') } })
    if (mode === 'callback_throw') window.__RC_INITIAL_READY_MARKER_HOOK__ = () => { throw new Error('synthetic observer callback') }
    if (mode === 'record') {
      const capture: { rows: RcPhaseMarker[]; overflow: boolean } = { rows: [], overflow: false }
      window.__RC_INITIAL_READY_MARKERS__ = capture
      window.__RC_INITIAL_READY_MARKER_HOOK__ = marker => {
        if (capture.rows.length >= 512) capture.overflow = true
        else capture.rows.push(marker)
      }
    }
  }, { mode, jobId, host })
  await page.goto(harnessUrl)
  await expect.poll(() => page.evaluate(() => Boolean(window.__RC_OBSERVER_HARNESS__))).toBe(true)
}
const panel = (page: Page) => page.locator('[data-rc-workflow="project"]')
async function ready(page: Page) {
  // Same default 5000ms locator gate; no test timeout increase/retry.
  await expect(panel(page).locator('[data-job-service="ready"]')).toHaveAttribute('data-job-status', 'failed')
  await expect(panel(page).locator('[data-rc-input-summary="stored"]')).toHaveCount(1)
}
const markers = (page: Page) => page.evaluate(() => window.__RC_INITIAL_READY_MARKERS__?.rows ?? [])
const pending = new Set<() => void>()
function gate() {
  let resolve!: () => void
  const promise = new Promise<void>(value => { resolve = value })
  const release = () => { pending.delete(release); resolve() }
  pending.add(release)
  return { promise, release }
}
async function unmount(page: Page) {
  await page.evaluate(() => window.__RC_OBSERVER_HARNESS__!.unmount())
  await expect(panel(page)).toHaveCount(0)
}

test.describe('real RC observation controls', () => {
  test.describe.configure({ mode: 'serial' })
  test.afterEach(async ({ page }, testInfo) => {
    await finishRcInitialReadyDiagnostics(page, testInfo, pending)
  })

  test('paired real panel failed load and explicit resume503 preserve outcome, binding and cleanup', async ({ context }, testInfo) => {
    let reference: unknown
    for (const mode of modes) {
      const page = await context.newPage(), rows: RequestRow[] = []
      try {
        await page.route(routePattern, async route => {
          const { row, path } = await observe(route, rows)
          if (row.role === 'resume') await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
          else await serve(route, path)
        })
        await start(page, mode, firstId)
        await ready(page)
        await panel(page).getByRole('button', { name: 'Retry RC from the beginning', exact: true }).click()
        await expect(panel(page).locator('[data-rc-resume-unconfirmed]')).toHaveCount(1)
        await expect(panel(page).locator('[data-rc-explicit-retry]')).toBeDisabled()
        await expect(panel(page).locator('[data-rc-workflow-error]')).toContainText('outcome is unconfirmed')
        const posts = rows.filter(row => row.method === 'POST')
        expect(posts).toHaveLength(1)
        expect(posts[0].role).toBe('resume')
        expect(JSON.parse(posts[0].body!.toString('utf8'))).toEqual({ expected_request_hash: digest(firstRaw), expected_checkpoint_hash: null })
        expect(rows.every(row => row.authEqual && (row.method === 'POST' || row.body === null))).toBe(true)
        const outcome = { stored: await panel(page).locator('[data-rc-input-summary="stored"]').textContent(),
          error: await panel(page).locator('[data-rc-workflow-error]').textContent(),
          posts: posts.map(row => [row.role, row.authEqual, row.body!.toString('utf8')]) }
        if (reference === undefined) reference = outcome
        else expect(outcome).toEqual(reference)
        if (mode === 'record') {
          const observed = await markers(page), phases = observed.map(row => row.phase)
          for (const phase of ['request.hash.begin', 'request.hash.end', 'request.parse.begin', 'request.parse.end',
            'poll.failed-load.begin', 'poll.failed-load.end', 'diagnostic.absent', 'http.cancel.begin', 'http.cancel.settled', 'ui.ready.queue', 'ui.ready.commit']) {
            expect(phases).toContain(phase)
          }
          expect(phases.filter(phase => phase === 'http.cancel.begin')).toHaveLength(phases.filter(phase => phase === 'http.cancel.settled').length)
        }
        await unmount(page)
        const signals = await page.evaluate(() => window.__RC_OBSERVER_HARNESS__!.signals())
        expect(signals.count).toBeGreaterThan(0)
        expect(signals.aborted).toBe(signals.count)
        expect(signals.overflow).toBe(false)
        const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, [])
        expect(ledger.diagnosticQualified).toBe(true)
      } finally { for (const release of [...pending]) release(); await page.close() }
    }
  })

  for (const kind of ['request', 'bad_hash', 'http503', 'cancel'] as const) {
    test(`paired real provider ${kind} returns/errors/cancellation stay equal across observer modes`, async ({ context }, testInfo) => {
      let reference: unknown
      for (const mode of modes) {
        const page = await context.newPage(), rows: RequestRow[] = [], entered = gate(), held = gate()
        try {
          await page.route(routePattern, async route => {
            const { row, path } = await observe(route, rows)
            if (kind === 'cancel' && row.role === 'first') {
              entered.release(); await held.promise
              try { await serve(route, path) } catch { /* The real caller abort can invalidate this controlled route. */ }
            } else if (kind === 'http503' && row.role === 'first') await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
            else await serve(route, path, kind === 'bad_hash' ? badHashRaw : undefined)
          })
          await start(page, mode)
          const result = page.evaluate(({ operation, firstId, firstRaw }) => window.__RC_OBSERVER_HARNESS__!.operate(operation, firstId, firstRaw),
            { operation: kind === 'request' || kind === 'bad_hash' ? 'request' as const : kind === 'cancel' ? 'cancel' as const : 'load' as const, firstId, firstRaw })
          if (kind === 'cancel') {
            await entered.promise
            await page.evaluate(() => window.__RC_OBSERVER_HARNESS__!.cancel())
          }
          const outcome = await result
          held.release(); entered.release()
          expect(outcome.callerAborted).toBe(true)
          expect(outcome.observedSignals).toBeGreaterThan(0)
          expect(outcome.signalsAborted).toBe(outcome.observedSignals)
          expect(outcome.signalOverflow).toBe(false)
          if (kind === 'request') expect(outcome).toMatchObject({ status: 'request_verified', errors: [], bytesEqual: true, byteLength: Buffer.byteLength(firstRaw, 'utf8') })
          if (kind === 'bad_hash') expect(outcome).toMatchObject({ status: 'error', errors: ['request_hash_mismatch'], errorKind: 'JobArtifactError' })
          if (kind === 'http503') expect(outcome).toMatchObject({ status: 'error', errors: ['job API returned HTTP 503'] })
          if (kind === 'cancel') expect(outcome).toMatchObject({ status: 'unconfigured', errors: [] })
          expect(rows.every(row => row.method === 'GET' && row.body === null && row.authEqual)).toBe(true)
          if (reference === undefined) reference = outcome
          else expect(outcome).toEqual(reference)
          await unmount(page)
          expect((await finishRcInitialReadyDiagnostics(page, testInfo, [])).diagnosticQualified).toBe(true)
        } finally { held.release(); entered.release(); await page.close() }
      }
    })
  }

  test('delayed old generation is cancelled and cannot replace the new real ready commit', async ({ page }) => {
    const held = gate(), entered = gate(), settled = gate(), rows: RequestRow[] = []
    let oldHeld = false
    await page.route(routePattern, async route => {
      const { row, path } = await observe(route, rows)
      if (row.role === 'first' && !oldHeld) {
        oldHeld = true; entered.release(); await held.promise
        try { await serve(route, path) } catch { /* Cancellation is verified from the actual signal below. */ }
        finally { settled.release() }
      } else await serve(route, path)
    })
    try {
      await start(page, 'record', firstId)
      await entered.promise
      await page.evaluate(secondId => window.__RC_OBSERVER_HARNESS__!.replace(secondId), secondId)
      await ready(page)
      await expect(panel(page).locator('[data-job-service="ready"]')).toContainText(secondId)
      const before = await markers(page), commits = before.filter(row => row.phase === 'ui.ready.commit')
      expect(commits).toHaveLength(1)
      const winner = commits[0].session
      expect(before.filter(row => row.phase === 'ui.ready.queue').map(row => row.session)).toEqual([winner])
      expect(before.some(row => row.phase === 'effect.cleanup' && row.session !== winner)).toBe(true)
      held.release(); await settled.promise
      await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
      await expect(panel(page).locator('[data-job-service="ready"]')).toContainText(secondId)
      const after = await markers(page)
      expect(after.filter(row => row.phase === 'ui.ready.commit').map(row => row.session)).toEqual([winner])
      expect(after.filter(row => row.phase === 'ui.ready.queue').map(row => row.session)).toEqual([winner])
      expect((await page.evaluate(() => window.__RC_OBSERVER_HARNESS__!.signals())).aborted).toBeGreaterThan(0)
    } finally { held.release(); entered.release(); settled.release(); await unmount(page) }
  })

  test('actual development StrictMode cleanup remount and unmount keep each first-ready queue before its commit', async ({ page }) => {
    await page.route(routePattern, async route => { const { path } = await observe(route, []); await serve(route, path) })
    await start(page, 'record', firstId)
    await ready(page)
    const first = await markers(page)
    expect(first.filter(row => row.phase === 'effect.setup')).toHaveLength(2)
    expect(first.filter(row => row.phase === 'effect.cleanup')).toHaveLength(1)
    const verifyFirstReady = (rows: RcPhaseMarker[]) => {
      const queued = rows.filter(row => row.phase === 'ui.ready.queue'), committed = rows.filter(row => row.phase === 'ui.ready.commit')
      expect(queued).toHaveLength(1); expect(committed).toHaveLength(1)
      expect(committed[0].session).toBe(queued[0].session)
      expect(committed[0].generation).toBe(queued[0].generation)
      expect(committed[0].sequence).toBeGreaterThan(queued[0].sequence)
      return committed[0].session
    }
    const firstWinner = verifyFirstReady(first)
    await unmount(page)
    const afterUnmount = await markers(page)
    expect(afterUnmount.some(row => row.phase === 'effect.cleanup' && row.session === firstWinner)).toBe(true)
    await page.evaluate(firstId => window.__RC_OBSERVER_HARNESS__!.mount(firstId), firstId)
    await ready(page)
    const all = await markers(page), second = all.filter(row => !first.some(previous => previous.session === row.session))
    expect(second.filter(row => row.phase === 'effect.setup')).toHaveLength(2)
    const secondWinner = verifyFirstReady(second)
    expect(secondWinner).not.toBe(firstWinner)
    await unmount(page)
    expect((await markers(page)).some(row => row.phase === 'effect.cleanup' && row.session === secondWinner)).toBe(true)
    const signals = await page.evaluate(() => window.__RC_OBSERVER_HARNESS__!.signals())
    expect(signals.aborted).toBe(signals.count)
    expect(signals.overflow).toBe(false)
  })

  test('real open-page retrieval and body attachment retain test status and release gates first', async ({ page }, testInfo) => {
    await page.goto('about:blank')
    await page.evaluate(() => { window.__RC_INITIAL_READY_MARKERS__ = { rows: [], overflow: false } })
    let released = false
    const status = testInfo.status, errors = testInfo.errors.length
    const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, [() => { released = true }])
    expect(released).toBe(true)
    expect(ledger).toMatchObject({ retrieval: 'present', attachment: 'complete', releaseAttempts: 1, releaseErrors: 0, diagnosticQualified: true })
    expect(testInfo.status).toBe(status); expect(testInfo.errors).toHaveLength(errors)
  })

  test('real closed-page retrieval failure remains a separate unqualified diagnostic ledger', async ({ context }, testInfo) => {
    const page = await context.newPage(); await page.close()
    const status = testInfo.status, errors = testInfo.errors.length
    let released = false
    const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, [() => { released = true }])
    expect(released).toBe(true)
    expect(ledger).toMatchObject({ retrieval: 'error', attachment: 'not_attempted', pageCleanup: 'closed', diagnosticQualified: false })
    expect(testInfo.status).toBe(status); expect(testInfo.errors).toHaveLength(errors)
    testInfo.annotations.push({ type: 'rc-marker-expected-diagnostic-failure', description: 'closed-page-retrieval' })
  })

  test('real missing-file attachment failure retains cleanup and original framework outcome', async ({ page }, testInfo) => {
    await page.goto('about:blank')
    await page.evaluate(() => { window.__RC_INITIAL_READY_MARKERS__ = { rows: [], overflow: false } })
    const status = testInfo.status, errors = testInfo.errors.length
    let released = false
    const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, [() => { released = true }],
      () => testInfo.attach('rc-control-missing-file', { path: testInfo.outputPath('uncreated-marker-control.json') }))
    expect(released).toBe(true)
    expect(ledger).toMatchObject({ retrieval: 'present', attachment: 'error', diagnosticQualified: false })
    expect(testInfo.status).toBe(status); expect(testInfo.errors).toHaveLength(errors)
    testInfo.annotations.push({ type: 'rc-marker-expected-diagnostic-failure', description: 'missing-file-attachment' })
  })

  for (const extra of ['BigInt', 'cycle'] as const) {
    test(`real ${extra} extra capture is rejected without serialization or replacing test outcome`, async ({ page }, testInfo) => {
      await page.goto('about:blank')
      await page.evaluate(extra => {
        const capture = { rows: [], overflow: false }
        window.__RC_INITIAL_READY_MARKERS__ = capture
        Object.assign(capture, { extra: extra === 'BigInt' ? BigInt(1) : capture })
      }, extra)
      const status = testInfo.status, errors = [...testInfo.errors]
      const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, [])
      expect(ledger).toMatchObject({ retrieval: 'invalid', serialization: 'not_attempted', attachment: 'not_attempted', diagnosticQualified: false, originalErrorsRetained: true })
      expect(testInfo.status).toBe(status); expect(testInfo.errors).toEqual(errors)
      testInfo.annotations.push({ type: 'rc-marker-expected-diagnostic-failure', description: `invalid-extra-${extra}` })
    })
  }
})
