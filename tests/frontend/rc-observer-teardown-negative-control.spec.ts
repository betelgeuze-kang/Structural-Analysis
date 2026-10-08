import { expect, test } from '@playwright/test'
import type { RcPhaseMarker } from '../../src/workbench-v2/model/rcWorkflowTrace'
import { finishRcInitialReadyDiagnostics } from './rcInitialReadyDiagnostics'

// Intentionally failing controls. Run separately; the standard CLI must exit 1 for these exact two 5000ms assertion failures.
// This does not retry or reproduce the hosted root cause and is never part of a passing production gate.
const base = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const jobId = `job_${'a'.repeat(32)}`
const releases = new Set<() => void>()
test.describe('negative initial-ready diagnostic outcome isolation', () => {
  test.describe.configure({ mode: 'default' })
  test.afterEach(async ({ page }, testInfo) => {
    const originalStatus = testInfo.status, originalErrors = [...testInfo.errors]
    expect(['failed', 'timedOut']).toContain(originalStatus)
    expect(originalErrors).toHaveLength(1)
    if (testInfo.title.includes('retrieval')) {
      for (const release of [...releases]) release()
      await page.close()
    }
    const ledger = await finishRcInitialReadyDiagnostics(page, testInfo, releases,
      testInfo.title.includes('attachment')
        ? () => testInfo.attach('rc-negative-missing-file', { path: testInfo.outputPath('uncreated-negative-marker.json') })
        : undefined)
    expect(ledger.initialStatus).toBe(originalStatus)
    expect(ledger.finalStatus).toBe(originalStatus)
    expect(ledger.initialErrors).toBe(1)
    expect(ledger.finalErrors).toBe(1)
    expect(ledger.originalErrorsRetained).toBe(true)
    expect(ledger.diagnosticQualified).toBe(false)
    if (testInfo.title.includes('retrieval')) expect(ledger).toMatchObject({ retrieval: 'error', attachment: 'not_attempted' })
    else expect(ledger).toMatchObject({ retrieval: 'present', attachment: 'error' })
    testInfo.annotations.push({ type: 'rc-marker-expected-negative-initial-ready', description: 'one-original-5000ms-assertion-failure-separate-diagnostic-ledger' })
  })
  for (const failure of ['retrieval', 'attachment'] as const) {
    test(`original ready failure survives real ${failure} failure`, async ({ page }) => {
      await page.addInitScript(jobId => {
        window.__RC_OBSERVER_CONFIG__ = { jobId, tenantId: 'rc-negative-control', bearerToken: 'synthetic-memory-only-negative-token' }
        const capture: { rows: RcPhaseMarker[]; overflow: boolean } = { rows: [], overflow: false }
        window.__RC_INITIAL_READY_MARKERS__ = capture
        window.__RC_INITIAL_READY_MARKER_HOOK__ = marker => {
          if (capture.rows.length >= 512) capture.overflow = true
          else capture.rows.push(marker)
        }
      }, jobId)
      let resolve!: () => void
      const held = new Promise<void>(value => { resolve = value })
      const release = () => { releases.delete(release); resolve() }
      releases.add(release)
      await page.route(new RegExp(`/api/v1/jobs/${jobId}$`), async route => {
        await held
        await route.abort('aborted').catch(() => { /* Closed-page route has no response/result authority. */ })
      })
      await page.goto(`${base}/tests/frontend/rc-observer-harness.html`)
      // Deliberate controlled missing ready; unchanged default5000ms and no retry/timeout override.
      await expect(page.locator('[data-rc-workflow="project"] [data-job-service="ready"]')).toHaveAttribute('data-job-status', 'failed')
    })
  }
})
