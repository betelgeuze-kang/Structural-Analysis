import { expect, test, type Page, type Route } from '@playwright/test'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import { createServer, type Server } from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { build } from 'vite'
import react from '@vitejs/plugin-react'
import type { RcDeclaredPrices, RcQuantityReportReference } from '../../src/workbench-v2/model/rcQuantityReportSchema'

// Compiles the original report panel with an injected, explicitly nonphysical
// review. Real transport/reference/raw-byte checks remain active. This isolated
// UI test is separate from the literal production-app workflow browser cases.
const fixtureRoot = path.resolve('tests/frontend/fixtures/rc-recovery-report')
const firstId = `job_${'a'.repeat(32)}`, secondId = `job_${'b'.repeat(32)}`
const host = { tenantId: 'rc-report-ui-synthetic', bearerToken: 'synthetic-report-memory-only' }
const collection = '/api/v1/jobs'
const routes = /\/api\/v1\/jobs\/job_[a-f0-9]{32}\/rc-quantity-reports(?:\/rcq_[a-f0-9]{64})?$/
const declared: RcDeclaredPrices = { concrete_per_m3: 123, rebar_per_kg: 456, currency: 'KRW', as_of: '2026-10-03', source: 'Synthetic UI test declaration only' }
interface HarnessControl { host: typeof host; reviewCalls: string[]; rejectReview: boolean; open(jobId: string): void }
declare global { interface Window { __rcReportRecoveryHost?: typeof host; __rcReportRecovery?: HarnessControl; __rcReportRecoveryInitialReport?: string } }
interface Companion { reference: RcQuantityReportReference; raw: string }
interface Observed { method: string; path: string; after: string | null; limit: string | null; body: string | null; tenant: string | null }
function companion(revision: number, prices: RcDeclaredPrices | null = null, jobId = firstId): Companion {
  const raw = JSON.stringify({ synthetic: 'rc-report-ui-only', revision, declared_prices: prices })
  const contentHash = `sha256:${createHash('sha256').update(raw).digest('hex')}`
  return { raw, reference: { schema_version: 'durable-rc-fiber-quantity-report-reference.v1', tenant_id: host.tenantId, job_id: jobId,
    report_id: `rcq_${contentHash.slice(7)}`, revision, content_hash: contentHash, byte_length: Buffer.byteLength(raw), media_type: 'application/json', created_at: '2026-10-03T00:00:00Z' } }
}
async function observe(route: Route, requests: Observed[]): Promise<Observed> {
  const request = route.request()
  const row = { method: request.method(), path: new URL(request.url()).pathname, after: await request.headerValue('x-structural-report-after-revision'),
    limit: await request.headerValue('x-structural-report-limit'), body: request.postData(), tenant: await request.headerValue('x-structural-tenant') }
  requests.push(row); return row
}
async function index(route: Route, reports: Companion[], jobId = firstId): Promise<void> {
  await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ schema_version: 'durable-rc-fiber-quantity-report-index.v1',
    tenant_id: host.tenantId, job_id: jobId, reports: reports.map(report => report.reference), next_after_revision: reports.at(-1)?.reference.revision ?? 0 }) })
}
async function bytes(route: Route, report: Companion, header = report.reference.content_hash): Promise<void> {
  await route.fulfill({ contentType: 'application/json', headers: { 'x-structural-report-sha256': header }, body: report.raw })
}
const panel = (page: Page) => page.locator('[data-rc-quantity-report]')
async function draft(page: Page): Promise<void> {
  await panel(page).getByLabel('Include declared prices', { exact: true }).check()
  await panel(page).getByLabel('Concrete price per m³', { exact: true }).fill(String(declared.concrete_per_m3))
  await panel(page).getByLabel('Rebar price per kg', { exact: true }).fill(String(declared.rebar_per_kg))
  await panel(page).getByLabel('Price date', { exact: true }).fill(declared.as_of)
  await panel(page).getByLabel('Declared source', { exact: true }).fill(declared.source)
}
async function assertDraft(page: Page): Promise<void> {
  await expect(panel(page).getByLabel('Include declared prices', { exact: true })).toBeChecked()
  await expect(panel(page).getByLabel('Concrete price per m³', { exact: true })).toHaveValue(String(declared.concrete_per_m3))
  await expect(panel(page).getByLabel('Rebar price per kg', { exact: true })).toHaveValue(String(declared.rebar_per_kg))
  await expect(panel(page).getByLabel('Price date', { exact: true })).toHaveValue(declared.as_of)
  await expect(panel(page).getByLabel('Declared source', { exact: true })).toHaveValue(declared.source)
}
async function select(page: Page, report: Companion): Promise<void> {
  await panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).selectOption(report.reference.report_id)
  await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(report.reference.report_id)
}
const gates = new Set<() => void>()
function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(value => { resolve = value })
  const release = () => { gates.delete(release); resolve() }
  gates.add(release); return { promise, release }
}
let baseUrl = '', output = '', server: Server | undefined
test.describe('RC report recovery follow-up with injected review', () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000)
    output = await mkdtemp(path.join(os.tmpdir(), 'rc-report-recovery-ui-'))
    await build({ configFile: false, envDir: false, root: fixtureRoot, base: '/', plugins: [react()], logLevel: 'error',
      build: { outDir: output, emptyOutDir: true, rollupOptions: { input: path.join(fixtureRoot, 'index.html') } } })
    const mime: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
    server = createServer(async (request, response) => {
      try {
        const pathname = decodeURIComponent(new URL(request.url ?? '/', 'http://127.0.0.1').pathname)
        const target = path.resolve(output, `.${pathname === '/' ? '/index.html' : pathname}`)
        if (!target.startsWith(`${output}${path.sep}`) || !(await stat(target)).isFile()) { response.writeHead(404).end(); return }
        response.writeHead(200, { 'Content-Type': mime[path.extname(target)] ?? 'application/octet-stream' }); response.end(await readFile(target))
      } catch { response.writeHead(404).end() }
    })
    await new Promise<void>((resolve, reject) => { server!.once('error', reject); server!.listen(0, '127.0.0.1', resolve) })
    const address = server.address()
    if (!address || typeof address === 'string') throw new Error('synthetic_harness_listener_unavailable')
    baseUrl = `http://127.0.0.1:${address.port}`
  })
  test.afterAll(async () => {
    if (server) await new Promise<void>((resolve, reject) => server!.close(error => error ? reject(error) : resolve()))
    // Only the exact mkdtemp directory created by this harness is removed.
    if (output) await rm(output, { recursive: true, force: true })
  })
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(host => { window.__rcReportRecoveryHost = { ...host } }, host)
  })
  test.afterEach(() => { for (const release of gates) release() })

  test('initial list503 uses GET-only local refresh and retains the price draft', async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1)
    let unavailable = true
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.path.endsWith('/rc-quantity-reports')) {
        if (unavailable) await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
        else await index(route, [saved])
      } else await bytes(route, saved)
    })
    await page.goto(baseUrl)
    await expect(panel(page).locator('[data-rc-report-error]')).toContainText('temporarily unavailable')
    await draft(page)
    unavailable = false
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(2)
    await assertDraft(page)
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveCount(0)
    expect(await page.evaluate(() => window.__rcReportRecovery!.reviewCalls)).toEqual([])
    await select(page, saved)
    await assertDraft(page)
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
    expect(requests.filter(row => row.path.endsWith('/rc-quantity-reports')).map(row => [row.after, row.limit])).toEqual([['0', '20'], ['0', '20']])
  })

  test('list refresh retains a verified selection and draft even when that revision leaves the first page', async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1), other = companion(2, declared)
    let refresh = false, unavailable = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.path.endsWith('/rc-quantity-reports')) {
        if (unavailable) await route.abort('failed')
        else await index(route, refresh ? [other] : [saved])
      } else await bytes(route, saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    unavailable = true
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).locator('[data-rc-report-error]')).toContainText('temporarily unavailable')
    await assertDraft(page)
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(saved.reference.report_id)
    unavailable = false; refresh = true
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(3)
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true })).toHaveValue(saved.reference.report_id)
    await expect(panel(page).locator('[data-rc-saved-prices]')).toContainText('No prices declared')
    await assertDraft(page)
    expect(await page.evaluate(() => window.__rcReportRecovery!.reviewCalls)).toEqual([saved.reference.report_id])
    expect(requests.every(row => row.method === 'GET')).toBe(true)
  })

  test('confirmed save after initial list failure prevents refresh from substituting the initial report', async ({ page }) => {
    const requests: Observed[] = [], initial = companion(1), created = companion(2, declared)
    let confirmed = false
    await page.addInitScript(id => { window.__rcReportRecoveryInitialReport = id }, initial.reference.report_id)
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST') { confirmed = true; await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created.reference) }) }
      else if (row.path.endsWith('/rc-quantity-reports')) {
        if (confirmed) await index(route, [initial])
        else await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
      } else await bytes(route, row.path.endsWith(created.reference.report_id) ? created : initial)
    })
    await page.goto(baseUrl)
    await expect(panel(page).locator('[data-rc-report-error]')).toContainText('temporarily unavailable')
    await draft(page)
    await panel(page).getByRole('button', { name: 'Save quantity and price revision', exact: true }).click()
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(created.reference.report_id)
    await expect(panel(page).locator('[data-rc-price-draft]')).toHaveCount(0)
    await panel(page).getByLabel('Concrete price per m³', { exact: true }).fill('999')
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(3)
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(created.reference.report_id)
    await expect(panel(page).getByLabel('Concrete price per m³', { exact: true })).toHaveValue('999')
    await expect(panel(page).locator('[data-rc-price-draft]')).toBeVisible()
    expect(await page.evaluate(() => window.__rcReportRecovery!.reviewCalls)).toEqual([created.reference.report_id])
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(1)
    expect(requests.some(row => row.path.endsWith(initial.reference.report_id))).toBe(false)
  })

  for (const failure of ['network', '503'] as const) test(`lost save ${failure} stays unconfirmed after listing and selecting equal prices`, async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1), matching = companion(2, declared)
    let committed = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST') {
        committed = true
        if (failure === 'network') await route.abort('failed')
        else await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
      } else if (row.path.endsWith('/rc-quantity-reports')) await index(route, committed ? [saved, matching] : [saved])
      else await bytes(route, row.path.endsWith(matching.reference.report_id) ? matching : saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    await panel(page).getByRole('button', { name: 'Save quantity and price revision', exact: true }).click()
    await expect(panel(page).locator('[data-rc-price-draft]')).toContainText('save outcome is unconfirmed')
    await expect(panel(page).locator('[data-rc-price-draft]')).not.toContainText('have not been saved')
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(saved.reference.report_id)
    await assertDraft(page)
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(1)
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(3)
    await expect(panel(page).locator('[data-rc-price-draft]')).toContainText('save outcome is unconfirmed')
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(saved.reference.report_id)
    await select(page, matching)
    await expect(panel(page).locator('[data-rc-saved-prices]')).toContainText(declared.source)
    await expect(panel(page).locator('[data-rc-price-draft]')).toContainText('save outcome is unconfirmed')
    await assertDraft(page)
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(1)
  })

  for (const rejection of ['read503', 'hash', 'review', 'declaration'] as const) test(`save confirmation ${rejection} preserves the previous selection and unconfirmed draft`, async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1)
    const created = companion(2, rejection === 'declaration' ? { ...declared, concrete_per_m3: 789 } : declared)
    let posted = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.method === 'POST') { posted = true; await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created.reference) }) }
      else if (row.path.endsWith('/rc-quantity-reports')) await index(route, posted ? [saved, created] : [saved])
      else if (row.path.endsWith(created.reference.report_id)) {
        if (rejection === 'read503') await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
        else await bytes(route, created, rejection === 'hash' ? `sha256:${'f'.repeat(64)}` : created.reference.content_hash)
      } else await bytes(route, saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    if (rejection === 'review') await page.evaluate(() => { window.__rcReportRecovery!.rejectReview = true })
    await panel(page).getByRole('button', { name: 'Save quantity and price revision', exact: true }).click()
    await expect(panel(page).locator('[data-rc-report-error]')).toBeVisible()
    await expect(panel(page).locator('[data-rc-price-draft]')).toContainText('save outcome is unconfirmed')
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(saved.reference.report_id)
    await assertDraft(page)
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(3)
    await expect(panel(page).locator('[data-rc-price-draft]')).toContainText('save outcome is unconfirmed')
    await expect(panel(page).locator('[data-rc-saved-report-id]')).toHaveText(saved.reference.report_id)
    expect(requests.filter(row => row.method === 'POST')).toHaveLength(1)
  })

  test('delayed revision refresh rejects a changed tenant and removes the old panel', async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1), gate = deferred()
    let delay = false, started = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.path.endsWith('/rc-quantity-reports')) { if (delay) { started = true; await gate.promise }; await index(route, [saved]) }
      else await bytes(route, saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    delay = true
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect.poll(() => started).toBe(true)
    await page.evaluate(() => { window.__rcReportRecovery!.host.tenantId = 'changed-report-ui-tenant' })
    gate.release()
    await expect(page.locator('[data-rc-report-harness-denied]')).toBeVisible()
    await expect(panel(page)).toHaveCount(0)
    expect(requests.every(row => row.method === 'GET' && row.tenant === host.tenantId)).toBe(true)
  })

  test('HTTP401 revision refresh clears the old selection without a write retry', async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1)
    let unauthorized = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (unauthorized) await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' })
      else if (row.path.endsWith('/rc-quantity-reports')) await index(route, [saved])
      else await bytes(route, saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    unauthorized = true
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect(page.locator('[data-rc-report-harness-denied]')).toBeVisible()
    await expect(panel(page)).toHaveCount(0)
    expect(requests.every(row => row.method === 'GET')).toBe(true)
  })

  test('aborted delayed refresh cannot restore a selection after switching project keys', async ({ page }) => {
    const requests: Observed[] = [], saved = companion(1), next = companion(1, null, secondId), gate = deferred()
    let delay = false, started = false, completed = false
    await page.route(routes, async route => {
      const row = await observe(route, requests)
      if (row.path === `${collection}/${firstId}/rc-quantity-reports` && delay) {
        started = true; await gate.promise
        try { await index(route, [saved]) } catch { /* Key switch aborts the old transport. */ }
        finally { completed = true }
      } else if (row.path.endsWith('/rc-quantity-reports')) await index(route, row.path.includes(secondId) ? [next] : [saved], row.path.includes(secondId) ? secondId : firstId)
      else await bytes(route, saved)
    })
    await page.goto(baseUrl); await select(page, saved); await draft(page)
    delay = true
    await panel(page).getByRole('button', { name: 'Refresh saved revisions', exact: true }).click()
    await expect.poll(() => started).toBe(true)
    await page.evaluate(id => window.__rcReportRecovery!.open(id), secondId)
    await expect(panel(page)).toHaveAttribute('data-rc-quantity-report', 'unselected')
    await expect(panel(page).getByRole('combobox', { name: 'Saved quantity revision', exact: true }).locator('option')).toHaveCount(2)
    gate.release(); await expect.poll(() => completed).toBe(true)
    await expect(panel(page).locator('[data-rc-saved-report-id], [data-rc-price-draft]')).toHaveCount(0)
    await expect(panel(page).getByLabel('Include declared prices', { exact: true })).not.toBeChecked()
    expect(requests.every(row => row.method === 'GET')).toBe(true)
  })
})
