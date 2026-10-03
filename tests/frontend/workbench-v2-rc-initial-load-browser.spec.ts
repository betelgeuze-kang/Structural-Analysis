import { expect, test, type Page, type Route } from '@playwright/test'
import { createHash } from 'node:crypto'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

// Synthetic status/request envelopes exercise the literal app's loading state.
// Empty model summaries are not solver inputs; no numerical result, checkpoint,
// worker response or quantity report is fabricated or qualified here.
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const collection = '/api/v1/jobs'
const jobRoute = /\/api\/v1\/jobs(?:\/[^?#]*)?$/
const firstId = `job_${'a'.repeat(32)}`
const secondId = `job_${'b'.repeat(32)}`
const host = { tenantId: 'rc-initial-load-synthetic', bearerToken: 'synthetic-initial-load-token' }
const hash = `sha256:${'c'.repeat(64)}`

declare global {
  interface Window {
    __rcInitialLoadHost?: { tenantId: string; bearerToken: string }
    __rcInitialLoadReadySeen?: number
  }
}

function input(caseId: string): string {
  return JSON.stringify({
    schema_version: 'structural-analysis-job-request.v3', operation: 'bounded_rc_fiber_direct_control',
    case_id: caseId, source_revision: 'd'.repeat(40), result_contract: 'bounded-rc-fiber-job-result.v1',
    execution_config: { chunk_target_count: 1, maximum_api_invocations: 4 },
    model: { schema_version: 'structural-analysis-canonical-model.v1', nodes: [], elements: [] },
    config: { annotation: 'Synthetic loading-state summary only' },
  })
}
const firstInput = input('synthetic_initial_first')
const secondInput = input('synthetic_initial_second')
function job(id: string, raw: string, status: 'queued' | 'failed' = 'queued'): WorkbenchJobView {
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: id, status, revision: 1, attempt: 1,
    progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z', lease_expires_at: null,
    error_code: status === 'failed' ? 'synthetic_initial_load_failure' : null, can_resume: false,
    request: { role: 'request', content_hash: `sha256:${createHash('sha256').update(raw, 'utf8').digest('hex')}`,
      byte_length: Buffer.byteLength(raw, 'utf8'), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'Synthetic loading-state metadata only; no structural result is qualified.', terminal_event_hash: hash,
  }
}

interface SeenRequest { method: string; path: string; tenant: string | null }
async function observe(route: Route, requests: SeenRequest[]): Promise<SeenRequest> {
  const request = route.request()
  const row = { method: request.method(), path: new URL(request.url()).pathname,
    tenant: await request.headerValue('x-structural-tenant') }
  requests.push(row)
  return row
}
async function serve(route: Route, row: SeenRequest, current: WorkbenchJobView, raw: string): Promise<void> {
  if (row.method === 'GET' && row.path === `${collection}/${current.job_id}`) {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(current) })
  } else if (row.method === 'GET' && row.path === `${collection}/${current.job_id}/request`) {
    await route.fulfill({ contentType: 'application/json', body: raw })
  } else {
    // In particular, an absent failed-attempt diagnostic is still an ordinary 404.
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  }
}
async function configure(page: Page, initialId?: string): Promise<void> {
  await page.addInitScript(({ collection, initialId, host }) => {
    const mutable = { ...host }
    window.__rcInitialLoadHost = mutable
    window.__rcInitialLoadReadySeen = 0
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: collection,
      ...(initialId ? { jobStatusUrl: `${collection}/${initialId}` } : {}),
      jobAuthorization: () => mutable,
    }
    new MutationObserver(() => {
      if (document.querySelector('[data-rc-workflow="project"] [data-job-service="ready"]')) {
        window.__rcInitialLoadReadySeen = (window.__rcInitialLoadReadySeen ?? 0) + 1
      }
    }).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-job-service'] })
  }, { collection, initialId, host })
}
const workflow = (page: Page) => page.locator('[data-rc-workflow="project"]')
async function loading(page: Page): Promise<void> {
  await expect(workflow(page).locator('[data-job-service]')).toHaveAttribute('data-job-service', 'loading')
  await expect(workflow(page).locator('[data-job-service="ready"], [data-rc-input-summary="stored"], [data-rc-project-link]')).toHaveCount(0)
}
async function ready(page: Page, status: 'queued' | 'failed', caseId: string): Promise<void> {
  await expect(workflow(page).locator('[data-job-service="ready"]')).toHaveAttribute('data-job-status', status)
  await expect(workflow(page).locator('[data-rc-input-summary="stored"]')).toContainText(caseId)
  await expect(workflow(page).locator('[data-rc-review], [data-rc-quantity-report]')).toHaveCount(0)
}
const pendingGates = new Set<() => void>()
function deferred(): { promise: Promise<void>; release: () => void; entered: boolean; finished: boolean } {
  let resolve!: () => void
  const promise = new Promise<void>(value => { resolve = value })
  const release = () => { pendingGates.delete(release); resolve() }
  pendingGates.add(release)
  return { promise, release, entered: false, finished: false }
}

test.describe('RC saved-job initial loading truth', () => {
  test.afterEach(() => { for (const release of pendingGates) release() })

  test('configured job remains loading while its initial status GET is held, then becomes ready', async ({ page }) => {
    const requests: SeenRequest[] = [], gate = deferred(), current = job(firstId, firstInput)
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}`) {
        gate.entered = true
        await gate.promise
        try { await serve(route, row, current, firstInput) } finally { gate.finished = true }
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await expect.poll(() => gate.entered).toBe(true)
    await loading(page)
    expect(requests.some(row => row.path.endsWith('/request'))).toBe(false)
    expect(await page.evaluate(() => window.__rcInitialLoadReadySeen)).toBe(0)
    gate.release()
    await expect.poll(() => gate.finished).toBe(true)
    await ready(page, 'queued', 'synthetic_initial_first')
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
    expect(requests.every(row => [`${collection}/${firstId}`, `${collection}/${firstId}/request`].includes(row.path))).toBe(true)
  })

  test('unconfigured stays idle and a saved request remains loading until its exact bytes arrive', async ({ page }) => {
    const requests: SeenRequest[] = [], gate = deferred(), current = job(firstId, firstInput, 'failed')
    await configure(page)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}/request`) {
        gate.entered = true
        await gate.promise
        try { await serve(route, row, current, firstInput) } finally { gate.finished = true }
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await workflow(page).getByText('Submit a new RC input', { exact: true }).click()
    await workflow(page).getByRole('textbox', { name: 'Typed RC request JSON', exact: true }).fill(firstInput)
    await expect(workflow(page).getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeEnabled()
    await expect(workflow(page).locator('[data-job-service]')).toHaveAttribute('data-job-service', 'unconfigured')
    expect(requests).toHaveLength(0)
    const url = new URL(baseUrl); url.searchParams.set('rcJob', firstId); url.hash = '/workbench-v2'
    await page.goto(url.href)
    await expect.poll(() => gate.entered).toBe(true)
    await loading(page)
    expect(await page.evaluate(() => window.__rcInitialLoadReadySeen)).toBe(0)
    gate.release()
    await expect.poll(() => gate.finished).toBe(true)
    await ready(page, 'failed', 'synthetic_initial_first')
    expect(requests.some(row => row.path === `${collection}/${firstId}/failure-diagnostics/1`)).toBe(true)
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
    expect(requests.every(row => [`${collection}/${firstId}`, `${collection}/${firstId}/request`, `${collection}/${firstId}/failure-diagnostics/1`].includes(row.path))).toBe(true)
  })

  test('source replacement and tenant invalidation while pending cannot publish stale ready state', async ({ page }) => {
    const requests: SeenRequest[] = [], oldStatus = deferred(), nextRequest = deferred()
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}`) {
        oldStatus.entered = true
        await oldStatus.promise
        try { await serve(route, row, job(firstId, firstInput), firstInput) }
        catch { /* The replaced generation has already aborted this fetch. */ }
        finally { oldStatus.finished = true }
      } else if (row.path === `${collection}/${secondId}/request`) {
        nextRequest.entered = true
        await nextRequest.promise
        try { await serve(route, row, job(secondId, secondInput), secondInput) }
        finally { nextRequest.finished = true }
      } else await serve(route, row, job(secondId, secondInput), secondInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await expect.poll(() => oldStatus.entered).toBe(true)
    await loading(page)
    await workflow(page).getByRole('textbox', { name: 'Saved RC job ID', exact: true }).fill(secondId)
    await workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await expect.poll(() => nextRequest.entered).toBe(true)
    await loading(page)
    oldStatus.release()
    await expect.poll(() => oldStatus.finished).toBe(true)
    await loading(page)
    expect(requests.some(row => row.path === `${collection}/${firstId}/request`)).toBe(false)
    await page.evaluate(() => { window.__rcInitialLoadHost!.tenantId = 'changed-initial-load-tenant' })
    nextRequest.release()
    await expect.poll(() => nextRequest.finished).toBe(true)
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
    await expect(workflow(page).locator('[data-job-service]')).toHaveAttribute('data-job-service', 'invalid')
    await expect(workflow(page).locator('[data-job-service="ready"], [data-rc-input-summary="stored"], [data-rc-project-link]')).toHaveCount(0)
    expect(await page.evaluate(() => window.__rcInitialLoadReadySeen)).toBe(0)
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
    expect(requests.every(row => [`${collection}/${firstId}`, `${collection}/${secondId}`, `${collection}/${secondId}/request`].includes(row.path))).toBe(true)
  })
})
