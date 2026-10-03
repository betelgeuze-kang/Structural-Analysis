import { expect, test, type Page, type Route } from '@playwright/test'
import { createHash } from 'node:crypto'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

// Synthetic orchestration envelopes only. These summary inputs are not admitted
// solver models; no numerical result, checkpoint payload or worker is fabricated.
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const collection = '/api/v1/jobs'
const jobRoute = /\/api\/v1\/jobs(?:\/[^?#]*)?$/
const firstId = `job_${'a'.repeat(32)}`
const secondId = `job_${'b'.repeat(32)}`
const host = { tenantId: 'rc-workflow-browser-synthetic', bearerToken: 'synthetic-memory-only-rc-token' }
const hash = `sha256:${'c'.repeat(64)}`

declare global {
  interface Window {
    __rcWorkflowBrowserHost?: { tenantId: string; bearerToken: string; throwAuthorization?: boolean }
    __rcWorkflowBrowserFile?: { started: boolean; completed: boolean; release: () => void }
  }
}

function input(caseId: string): string {
  // Deliberately retain Unicode, whitespace and numeric spellings on submission.
  return ` {\n"schema_version":"structural-analysis-job-request.v3",\n"operation":"bounded_rc_fiber_direct_control",\n"case_id":"${caseId}",\n"source_revision":"${'d'.repeat(40)}",\n"result_contract":"bounded-rc-fiber-job-result.v1",\n"execution_config":{"chunk_target_count":1,"maximum_api_invocations":2},\n"model":{"schema_version":"structural-analysis-canonical-model.v1","nodes":[],"elements":[]},\n"config":{"preview_number":1.0,"preview_zero":-0.0,"annotation":"원문 보존"}\n} `
}
const firstInput = input('synthetic_first')
const secondInput = input('synthetic_second')
function digest(raw: string): string { return `sha256:${createHash('sha256').update(raw, 'utf8').digest('hex')}` }

function job(id: string, raw: string, status: 'queued' | 'failed' | 'checkpointed' | 'cancelled', attempt = 1): WorkbenchJobView {
  const checkpoint = status === 'checkpointed' ? { role: 'checkpoint' as const, content_hash: hash, byte_length: 2, media_type: 'application/json' } : null
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: id, status, revision: attempt, attempt,
    progress: { completed_steps: checkpoint ? 1 : 0, total_steps: 2 },
    created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z', lease_expires_at: null,
    error_code: status === 'failed' ? 'synthetic_orchestration_failure' : null,
    can_resume: checkpoint !== null,
    request: { role: 'request', content_hash: digest(raw), byte_length: Buffer.byteLength(raw, 'utf8'), media_type: 'application/json' },
    checkpoint, result: null, evidence: null, resume_contract_hash: checkpoint ? hash : null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'Synthetic UI orchestration metadata only; no structural result is qualified.', terminal_event_hash: hash,
  }
}

interface ObservedRequest { method: string; path: string; body: Buffer | null; key: string | null; tenant: string | null; authorization: string | null }
async function observe(route: Route, requests: ObservedRequest[]): Promise<ObservedRequest> {
  const request = route.request()
  const row = { method: request.method(), path: new URL(request.url()).pathname, body: request.postDataBuffer(),
    key: await request.headerValue('idempotency-key'), tenant: await request.headerValue('x-structural-tenant'),
    authorization: await request.headerValue('authorization') }
  requests.push(row)
  return row
}
async function configure(page: Page, initialId?: string): Promise<void> {
  await page.addInitScript(({ collection, initialId, host }) => {
    const mutable: { tenantId: string; bearerToken: string; throwAuthorization?: boolean } = { ...host }
    window.__rcWorkflowBrowserHost = mutable
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: collection,
      ...(initialId ? { jobStatusUrl: `${collection}/${initialId}` } : {}), jobAuthorization: () => {
        if (mutable.throwAuthorization) throw new Error(mutable.bearerToken)
        return mutable
      } }
  }, { collection, initialId, host })
}
async function serve(route: Route, row: ObservedRequest, current: WorkbenchJobView, raw: string): Promise<void> {
  if (row.method === 'GET' && row.path === `${collection}/${current.job_id}`) {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(current) })
  } else if (row.method === 'GET' && row.path === `${collection}/${current.job_id}/request`) {
    await route.fulfill({ contentType: 'application/json', body: raw })
  } else {
    // Missing diagnostic/history is legitimate and grants no result authority.
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  }
}
const workflow = (page: Page) => page.locator('[data-rc-workflow="project"]')
async function ready(page: Page, status: 'queued' | 'failed' | 'checkpointed' | 'cancelled'): Promise<void> {
  await expect(workflow(page).locator('[data-job-service="ready"]')).toHaveAttribute('data-job-status', status)
  await expect(workflow(page).locator('[data-rc-input-summary="stored"]')).toHaveCount(1)
}
const pendingGates = new Set<() => void>()
function deferred(): { promise: Promise<void>; release: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>(value => { resolve = value })
  const release = () => { pendingGates.delete(release); resolve() }
  pendingGates.add(release)
  return { promise, release }
}

test.describe('RC project workflow orchestration browser', () => {
  test.afterEach(async ({ page }) => {
    for (const release of pendingGates) release()
    await page.evaluate(() => window.__rcWorkflowBrowserFile?.release()).catch(() => { /* Closed context needs no gate release. */ })
  })
  test('queued saved job uses hash-checked input without numerical or quantity requests', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'queued')
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, firstInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'queued')
    expect(requests.every(row => row.method === 'GET' && [ `${collection}/${firstId}`, `${collection}/${firstId}/request` ].includes(row.path))).toBe(true)
    expect(requests.every(row => row.tenant === host.tenantId && row.authorization === `Bearer ${host.bearerToken}`)).toBe(true)
    await expect(workflow(page).locator('[data-rc-review], [data-rc-table], [data-rc-explicit-retry]')).toHaveCount(0)
    await expect(workflow(page).locator('[data-job-result-ir="unavailable"]')).toBeVisible()
  })

  test('uncertain submission retries preserve original UTF8 bytes and one idempotency key', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'queued')
    let submissions = 0
    await configure(page)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST' && row.path === collection) {
        if (++submissions === 1) await route.abort('failed')
        else await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(current) })
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await workflow(page).getByText('Submit a new RC input', { exact: true }).click()
    await workflow(page).getByLabel('Typed RC request JSON', { exact: true }).fill(firstInput)
    const submit = workflow(page).getByRole('button', { name: 'Submit RC analysis', exact: true })
    await expect(submit).toBeEnabled()
    const intent = await submit.getAttribute('data-rc-submit-intent')
    await submit.click()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('draft has been retained')
    await expect(submit).toBeEnabled()
    await expect(workflow(page).getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(firstInput)
    await expect(submit).toHaveAttribute('data-rc-submit-intent', intent!)
    await submit.click()
    await ready(page, 'queued')
    const posts = requests.filter(row => row.method === 'POST')
    expect(posts).toHaveLength(2)
    expect(posts.map(row => row.path)).toEqual([collection, collection])
    expect(posts.map(row => row.body)).toEqual([Buffer.from(firstInput, 'utf8'), Buffer.from(firstInput, 'utf8')])
    expect(posts[0].key).toMatch(/^rc-ui-/)
    expect(posts[1].key).toBe(posts[0].key)
  })

  for (const checkpointHash of [null, hash]) test(`failed ${checkpointHash === null ? 'null' : 'saved'}-checkpoint job retries only after explicit action with exact binding`, async ({ page }) => {
    const requests: ObservedRequest[] = []
    let current = job(firstId, firstInput, 'failed')
    if (checkpointHash !== null) {
      current = { ...current, checkpoint: { role: 'checkpoint', content_hash: checkpointHash, byte_length: 2, media_type: 'application/json' },
        can_resume: true, resume_contract_hash: hash, progress: { completed_steps: 1, total_steps: 2 } }
    }
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST' && row.path === `${collection}/${firstId}/resume`) {
        current = { ...current, ...job(firstId, firstInput, 'queued', 2), checkpoint: current.checkpoint,
          resume_contract_hash: current.resume_contract_hash, progress: current.progress }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(current) })
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'failed')
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(0)
    await workflow(page).getByRole('button', { name: checkpointHash === null ? 'Retry RC from the beginning' : 'Resume RC from saved checkpoint', exact: true }).click()
    await ready(page, 'queued')
    const posts = requests.filter(row => row.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0].path).toBe(`${collection}/${firstId}/resume`)
    expect(JSON.parse(posts[0].body!.toString('utf8'))).toEqual({ expected_request_hash: digest(firstInput), expected_checkpoint_hash: checkpointHash })
    expect(requests.some(row => row.path.endsWith('/checkpoint'))).toBe(false)
  })

  test('checkpointed job keeps polling and never issues an implicit resume', async ({ page }) => {
    const requests: ObservedRequest[] = []
    let current = job(firstId, firstInput, 'checkpointed')
    await page.clock.install()
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, firstInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'checkpointed')
    for (let poll = 2; poll <= 3; poll++) {
      await page.clock.fastForward(2100)
      await expect.poll(() => requests.filter(row => row.path === `${collection}/${firstId}`).length).toBeGreaterThanOrEqual(poll)
    }
    await expect(workflow(page).locator('[data-job-resume]')).toContainText('worker continuation available')
    await expect(workflow(page).locator('[data-rc-explicit-retry]')).toHaveCount(0)
    expect(requests.every(row => row.method === 'GET')).toBe(true)
    expect(requests.filter(row => row.path.endsWith('/request'))).toHaveLength(1)
    expect(requests.some(row => row.path.endsWith('/checkpoint') || row.path.endsWith('/result') || row.path.endsWith('/evidence'))).toBe(false)
    current = { ...current, status: 'cancelled', revision: current.revision + 1, can_resume: false }
    await page.clock.fastForward(2100)
    await ready(page, 'cancelled')
    const terminalReads = requests.length
    await page.clock.fastForward(6000)
    expect(requests).toHaveLength(terminalReads)
    await expect(workflow(page).locator('[data-rc-explicit-retry]')).toHaveCount(0)
    expect(requests.every(row => row.method === 'GET')).toBe(true)
  })

  test('switching exact jobs discards a delayed previous status response', async ({ page }) => {
    const requests: ObservedRequest[] = [], gate = deferred()
    let firstStarted = false, firstReleased = false
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}`) {
        firstStarted = true
        await gate.promise
        try { await serve(route, row, job(firstId, firstInput, 'queued'), firstInput) } catch { /* Old fetch can already be aborted by the generation switch. */ }
        finally { firstReleased = true }
      } else await serve(route, row, job(secondId, secondInput, 'queued'), secondInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await expect.poll(() => firstStarted).toBe(true)
    await workflow(page).getByLabel('Saved RC job ID', { exact: true }).fill(secondId)
    await workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await ready(page, 'queued')
    await expect(workflow(page).locator('[data-job-service]')).toContainText(secondId)
    gate.release()
    await expect.poll(() => firstReleased).toBe(true)
    await expect(workflow(page).locator('[data-job-service]')).toContainText(secondId)
    await expect(workflow(page).locator('[data-job-service]')).not.toContainText(firstId)
    await expect(workflow(page).locator('[data-rc-input-summary="stored"] dd').first()).toHaveText('synthetic_second')
    expect(requests.some(row => row.path === `${collection}/${firstId}/request`)).toBe(false)
  })

  test('same mutable host tenant change clears the old project before explicit retry', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'failed')
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, firstInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'failed')
    await page.evaluate(() => { window.__rcWorkflowBrowserHost!.tenantId = 'changed-synthetic-account' })
    await workflow(page).getByRole('button', { name: 'Retry RC from the beginning', exact: true }).click()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
    await expect(workflow(page).locator('[data-rc-input-summary="stored"], [data-rc-project-link], [data-rc-explicit-retry]')).toHaveCount(0)
    await expect(workflow(page).locator('[data-job-service="unconfigured"]')).toBeVisible()
    expect(requests.some(row => row.method === 'POST')).toBe(false)
    expect(requests.every(row => row.tenant === host.tenantId)).toBe(true)
  })

  test('tenant change while a status response is delayed prevents old input adoption', async ({ page }) => {
    const requests: ObservedRequest[] = [], gate = deferred()
    let started = false
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}`) { started = true; await gate.promise }
      await serve(route, row, job(firstId, firstInput, 'queued'), firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await expect.poll(() => started).toBe(true)
    await page.evaluate(() => { window.__rcWorkflowBrowserHost!.tenantId = 'changed-during-http' })
    gate.release()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
    await expect(workflow(page).locator('[data-rc-input-summary="stored"], [data-rc-project-link]')).toHaveCount(0)
    expect(requests.some(row => row.path.endsWith('/request'))).toBe(false)
  })

  test('malformed saved ID cannot substitute a configured job and requires explicit exact opening', async ({ page }) => {
    const requests: ObservedRequest[] = []
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, job(secondId, secondInput, 'queued'), secondInput) })
    const url = new URL(baseUrl); url.searchParams.set('rcJob', `${firstId}/request`); url.hash = '/workbench-v2'
    await page.goto(url.href)
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('saved RC job identifier is invalid')
    expect(requests).toHaveLength(0)
    await expect(workflow(page).locator('[data-rc-project-link], [data-rc-input-summary="stored"]')).toHaveCount(0)
    await workflow(page).getByLabel('Saved RC job ID', { exact: true }).fill(secondId)
    await workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await ready(page, 'queued')
    expect(requests.some(row => row.path.startsWith(`${collection}/${firstId}`))).toBe(false)
    await expect(workflow(page).locator('[data-job-service]')).toContainText(secondId)
  })

  test('project link and browser storage contain bounded identities without credentials', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'queued')
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, firstInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'queued')
    const href = await workflow(page).locator('[data-rc-project-link]').getAttribute('href')
    const link = new URL(href!)
    expect(link.origin).toBe(new URL(baseUrl).origin)
    expect([...link.searchParams.entries()]).toEqual([['rcJob', firstId]])
    expect(link.hash).toBe('#/workbench-v2')
    const exposure = await page.evaluate(() => ({ href: location.href, local: { ...localStorage }, session: { ...sessionStorage }, text: document.body.textContent }))
    for (const secret of [host.tenantId, host.bearerToken]) {
      expect(href).not.toContain(secret)
      expect(JSON.stringify(exposure)).not.toContain(secret)
    }
    expect(requests.every(row => row.authorization === `Bearer ${host.bearerToken}`)).toBe(true)
  })

  test('coherent swapped submit job and saved request cannot replace the original intent', async ({ page }) => {
    const requests: ObservedRequest[] = [], swapped = job(secondId, secondInput, 'queued')
    await configure(page)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST' && row.path === collection) {
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(swapped) })
      } else await serve(route, row, swapped, secondInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await workflow(page).getByText('Submit a new RC input', { exact: true }).click()
    await workflow(page).getByLabel('Typed RC request JSON', { exact: true }).fill(firstInput)
    await workflow(page).getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('could not be verified')
    await expect(workflow(page).locator('[data-rc-input-summary="stored"], [data-rc-project-link]')).toHaveCount(0)
    await expect(workflow(page).getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(firstInput)
    const posts = requests.filter(row => row.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual(Buffer.from(firstInput, 'utf8'))
    expect(requests.some(row => row.path === `${collection}/${secondId}/request`)).toBe(true)
  })

  test('late selected file cannot overwrite the draft after switching project generation', async ({ page }) => {
    await page.addInitScript(() => {
      const original = File.prototype.arrayBuffer
      let release!: () => void
      const gate = new Promise<void>(resolve => { release = resolve })
      const state = { started: false, completed: false, release }
      window.__rcWorkflowBrowserFile = state
      Object.defineProperty(File.prototype, 'arrayBuffer', { configurable: true, value: async function(this: File) {
        if (this.name === 'delayed-rc-input.json') { state.started = true; await gate }
        const bytes = await original.call(this)
        state.completed = true
        return bytes
      } })
    })
    const requests: ObservedRequest[] = [], current = job(secondId, secondInput, 'queued')
    await configure(page)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, secondInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await workflow(page).getByText('Submit a new RC input', { exact: true }).click()
    await workflow(page).getByLabel('Typed RC request JSON', { exact: true }).fill(firstInput)
    await workflow(page).getByLabel('Choose RC request JSON file', { exact: true }).setInputFiles({ name: 'delayed-rc-input.json', mimeType: 'application/json', buffer: Buffer.from(secondInput, 'utf8') })
    await expect.poll(() => page.evaluate(() => window.__rcWorkflowBrowserFile?.started)).toBe(true)
    await workflow(page).getByLabel('Saved RC job ID', { exact: true }).fill(secondId)
    await workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await ready(page, 'queued')
    await page.evaluate(() => window.__rcWorkflowBrowserFile!.release())
    await expect.poll(() => page.evaluate(() => window.__rcWorkflowBrowserFile?.completed)).toBe(true)
    // Let the resolved file handler and React commit settle before checking the
    // draft; an immediate check could pass before a stale write reaches the DOM.
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(workflow(page).getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(firstInput)
    await expect(workflow(page).locator('[data-rc-input-summary="stored"] dd').first()).toHaveText('synthetic_second')
    expect(requests.every(row => row.method === 'GET')).toBe(true)
  })

  test('submit HTTP401 clears authority and leaves account refresh and exact opening usable', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'failed')
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST' && row.path === collection) {
        await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: host.bearerToken }) })
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'failed')
    await workflow(page).getByText('Submit a new RC input', { exact: true }).click()
    await workflow(page).getByLabel('Typed RC request JSON', { exact: true }).fill(firstInput)
    await workflow(page).getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('Authentication is unavailable')
    await expect(workflow(page).locator('[data-rc-project-link], [data-rc-input-summary="stored"]')).toHaveCount(0)
    await expect(workflow(page).locator('[data-job-service="unconfigured"]')).toBeVisible()
    const refresh = workflow(page).getByRole('button', { name: 'Refresh account and job', exact: true })
    const open = workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true })
    await expect(refresh).toBeEnabled()
    await expect(open).toBeEnabled()
    await expect(workflow(page).getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(firstInput)
    await refresh.click()
    await ready(page, 'failed')
    await open.click()
    await ready(page, 'failed')
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(1)
    expect(requests.find(row => row.method === 'POST')!.body).toEqual(Buffer.from(firstInput, 'utf8'))
    await expect(page.locator('body')).not.toContainText(host.bearerToken)
  })

  test('retry host authorization failure clears busy state and can explicitly recover the same account', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'failed')
    await configure(page, firstId)
    await page.route(jobRoute, async route => { const row = await observe(route, requests); await serve(route, row, current, firstInput) })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'failed')
    await page.evaluate(() => { window.__rcWorkflowBrowserHost!.throwAuthorization = true })
    await workflow(page).getByRole('button', { name: 'Retry RC from the beginning', exact: true }).click()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('could not be verified')
    await expect(workflow(page).locator('[data-rc-project-link], [data-rc-input-summary="stored"], [data-rc-explicit-retry]')).toHaveCount(0)
    await expect(workflow(page).locator('[data-job-service="unconfigured"]')).toBeVisible()
    const refresh = workflow(page).getByRole('button', { name: 'Refresh account and job', exact: true })
    const open = workflow(page).getByRole('button', { name: 'Open saved RC job', exact: true })
    await expect(refresh).toBeEnabled()
    await expect(open).toBeEnabled()
    expect(requests.some(row => row.method === 'POST')).toBe(false)
    await page.evaluate(() => { window.__rcWorkflowBrowserHost!.throwAuthorization = false })
    await refresh.click()
    await ready(page, 'failed')
    await expect(open).toBeEnabled()
    await expect(workflow(page).locator('[data-rc-explicit-retry]')).toBeEnabled()
    expect(requests.some(row => row.method === 'POST')).toBe(false)
    await expect(page.locator('body')).not.toContainText(host.bearerToken)
  })

  test('delayed missing historical diagnostic cannot survive a mutable tenant change', async ({ page }) => {
    const requests: ObservedRequest[] = [], current = job(firstId, firstInput, 'failed', 2), gate = deferred()
    let historicalStarted = false
    await configure(page, firstId)
    await page.route(jobRoute, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}/failure-diagnostics/1`) {
        historicalStarted = true
        await gate.promise
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
      } else await serve(route, row, current, firstInput)
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await ready(page, 'failed')
    expect(requests.some(row => row.path === `${collection}/${firstId}/failure-diagnostics/2`)).toBe(true)
    const history = workflow(page).locator('[data-failure-history]')
    await expect(history).toHaveAttribute('data-failure-history', 'idle')
    await history.getByRole('button', { name: 'Review previous attempt', exact: true }).click()
    await expect.poll(() => historicalStarted).toBe(true)
    await expect(history).toHaveAttribute('data-failure-history', 'loading')
    await page.evaluate(() => { window.__rcWorkflowBrowserHost!.tenantId = 'different-history-account' })
    gate.release()
    await expect(workflow(page).locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
    await expect(workflow(page).locator('[data-rc-project-link], [data-rc-input-summary="stored"], [data-failure-history]')).toHaveCount(0)
    await expect(workflow(page).locator('[data-job-service="unconfigured"]')).toBeVisible()
    expect(requests.filter(row => row.path === `${collection}/${firstId}/failure-diagnostics/1`)).toHaveLength(1)
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
    await expect(workflow(page).locator('[data-failure-diagnostic]')).toHaveCount(0)
  })
})
