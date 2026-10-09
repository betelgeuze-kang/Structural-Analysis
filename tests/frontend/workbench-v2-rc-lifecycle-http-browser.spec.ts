import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

type Credentials = { tenantId: string; bearerToken: string }
type ReportReference = { report_id: string; revision: number; content_hash: string; byte_length: number }
type Ready = {
  ready: boolean; request: Record<string, unknown>; credentials: Credentials; other_credentials: Credentials
  explicit_layers_request: Record<string, unknown>
  proof: { checkout_sha: string | null; github_sha: string | null; github_run_id: string | null; github_run_attempt: string | null; source_revision_caller_declaration: string }
}
type Server = { pid: number; origin: string; port: number; previous_pid?: number }
const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
const headers = ({ tenantId, bearerToken }: Credentials) => ({ 'X-Structural-Tenant': tenantId, Authorization: `Bearer ${bearerToken}` })

async function deadline<T>(pending: Promise<T>, milliseconds: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([pending, new Promise<T>((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), milliseconds)
    })])
  } finally { if (timer) clearTimeout(timer) }
}

class Driver {
  readonly child: ChildProcess
  readonly closed: Promise<void>
  readonly lines: AsyncIterator<string>
  stdout = ''
  stderr = ''
  sequence = 0
  ended = false
  protocolHealthy = true
  constructor(workspace: string) {
    // This separate hosted lane intentionally retains setup-python's PATH.
    // The normal sanitized frontend runner is unchanged and never starts Python.
    this.child = spawn('python', ['-B', 'tests/frontend/rc_lifecycle_http_fixture.py', 'driver', '--workspace', workspace], {
      env: { ...process.env, PYTHONPATH: resolve('src'), OPENBLAS_NUM_THREADS: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.closed = new Promise(done => this.child.once('close', () => { this.ended = true; done() }))
    this.child.on('error', error => { this.stderr += String(error) })
    this.child.stdin!.on('error', error => { this.stderr += String(error); this.protocolHealthy = false })
    this.child.stdout!.on('data', chunk => { this.stdout += String(chunk) })
    this.child.stderr!.on('data', chunk => { this.stderr += String(chunk) })
    this.lines = createInterface({ input: this.child.stdout! })[Symbol.asyncIterator]()
  }
  async read<T>(milliseconds = 90000): Promise<T> {
    const line = await deadline(this.lines.next(), milliseconds, `Fixture barrier timed out: ${this.stderr}`)
    if (line.done) throw new Error(`Fixture exited ${this.child.exitCode}: ${this.stderr}`)
    return JSON.parse(line.value) as T
  }
  async command<T = Record<string, unknown>>(command: string, fields: Record<string, unknown> = {}, milliseconds = 90000): Promise<T> {
    const id = ++this.sequence
    if (this.ended) throw new Error(`Fixture already exited: ${this.stderr}`)
    this.child.stdin!.write(JSON.stringify({ id, command, ...fields }) + '\n')
    try {
      const response = await this.read<{ id: number; ok: boolean; result: T; error?: string }>(milliseconds)
      expect(response.id).toBe(id)
      if (!response.ok) throw new Error(`${command}: ${response.error}\n${this.stderr}`)
      return response.result
    } catch (error) { this.protocolHealthy = false; throw error }
  }
  async close(): Promise<void> {
    if (!this.ended) {
      if (this.protocolHealthy) {
        try { await this.command('stop', {}, 15000) } catch { this.child.kill('SIGTERM') }
      } else this.child.kill('SIGTERM')
      try { await deadline(this.closed, 15000, 'Fixture did not reap its children') }
      catch {
        this.child.kill('SIGKILL')
        await deadline(this.closed, 5000, 'Fixture remained alive after SIGKILL')
        throw new Error('Fixture needed SIGKILL; descendant cleanup is unverified, retain evidence')
      }
    }
  }
}

async function freshPage(browser: Browser, credentials: Credentials, contexts: BrowserContext[], evidence: Record<string, unknown>) {
  const context = await browser.newContext({ acceptDownloads: true })
  contexts.push(context)
  expect(await context.storageState()).toEqual({ cookies: [], origins: [] })
  await context.addInitScript(credentials => {
    // This is only the application host's documented configuration seam.
    // No request routes, Worker implementation, solver bytes or reviewer result
    // are replaced. Credentials exist solely in this new context's callback.
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: '/v1/jobs', jobAuthorization: async () => {
        // Exercise delayed host sign-in without replacing any HTTP response.
        const host = window as any
        const gate = host.__rcAuthorizationGate as Promise<void> | undefined
        if (gate) { host.__rcAuthorizationWaiting = true; await gate; host.__rcAuthorizationSettled = true }
        return credentials
      },
    }
  }, credentials)
  const page = await context.newPage()
  const workerUrls: string[] = []
  page.on('worker', worker => workerUrls.push(worker.url()))
  evidence[`context_${contexts.length}`] = { initial_storage_empty: true, worker_urls: workerUrls }
  return { page, context, workerUrls }
}

async function navigateSavedLink(page: Page, url: string): Promise<void> {
  await page.evaluate(url => {
    history.pushState({}, '', url)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, url)
}

async function verifiedReview(page: Page, workerUrls: string[]) {
  await expect(page.locator('[data-job-service="ready"][data-job-status="succeeded"]')).toBeVisible({ timeout: 90000 })
  await expect(page.locator('[data-rc-review="verified"]')).toBeVisible({ timeout: 90000 })
  // The real reviewer runs in the built application's Worker, in every fresh
  // context that renders a result. No injected reviewer can satisfy this alone.
  expect(workerUrls.some(url => /\/assets\/rcJobReview\.worker[^/]*\.js(?:\?.*)?$/.test(url))).toBe(true)
}

for (const profile of ['legacy', 'explicit-layers'] as const) {
test(`actual Workbench ${profile} RC job survives SIGKILL and two cold HTTP/browser reopens, then downloads immutable price revision two`, async ({ browser }, testInfo) => {
  test.setTimeout(300000)
  const workspace = await mkdtemp(join(tmpdir(), 'structural-rc-browser-'))
  const driver = new Driver(workspace)
  const contexts: BrowserContext[] = []
  const evidence: Record<string, unknown> = {
    schema_version: 'workbench-rc-hosted-browser-proof.v1',
    independent_physical_validation: false, design_authority: false, completed: false,
  }
  let cleanupError: unknown
  try {
    const ready = await driver.read<Ready>(20000)
    expect(ready.ready).toBe(true)
    if (profile === 'explicit-layers') ready.request = ready.explicit_layers_request
    evidence.profile = profile
    evidence.source = ready.proof
    // A hosted receipt must name the checked-out commit and run identity rather
    // than relabel the caller-authored source_revision as attestation.
    if (process.env.GITHUB_ACTIONS === 'true') {
      expect(ready.proof.checkout_sha).toMatch(/^[0-9a-f]{40}$/)
      expect(ready.proof.checkout_sha).toBe(process.env.GITHUB_SHA)
      expect(ready.proof.github_run_id).toBe(process.env.GITHUB_RUN_ID)
      expect(ready.proof.github_run_attempt).toBe(process.env.GITHUB_RUN_ATTEMPT)
    }
    expect(ready.proof.source_revision_caller_declaration).toBe('a'.repeat(40))
    let server = await driver.command<Server>('start_http')
    const servers = [server]
    evidence.http_processes = servers
    let view = await freshPage(browser, ready.credentials, contexts, evidence)
    await view.page.goto(`${server.origin}/#/workbench-v2`)
    await view.page.getByText('Submit a new RC input', { exact: true }).click()
    await view.page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(ready.request))
    const submission = view.page.waitForResponse(response => response.url() === `${server.origin}/v1/jobs` && response.request().method() === 'POST')
    await view.page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    const submitted = await submission
    expect(submitted.status()).toBe(202)
    expect(submitted.request().postDataJSON()).toEqual(ready.request)
    const job = await submitted.json()
    expect(job.status).toBe('queued')
    expect(job.job_id).toMatch(/^job_[0-9a-f]{32}$/)
    evidence.submission = { status: submitted.status(), job_id: job.job_id, request: job.request }
    const persisted = await driver.command<{ original_request: Record<string, unknown>; original_request_hash: string }>('inspect_job', { job_id: job.job_id })
    expect(persisted.original_request).toEqual(ready.request)
    expect(persisted.original_request_hash).toBe(job.request.content_hash)
    const projectLink = view.page.locator('[data-rc-project-link]')
    await expect(projectLink).toBeVisible()
    const savedJobUrl = (await projectLink.getAttribute('href'))!
    expect(new URL(savedJobUrl).searchParams.get('rcJob')).toBe(job.job_id)
    expect(new URL(savedJobUrl).origin).toBe(server.origin)
    // Submission creates local Open intent. A same-surface history entry must
    // replace that intent, then actual Back/Forward must restore URL identity.
    const missingJobUrl = new URL(savedJobUrl)
    missingJobUrl.searchParams.set('rcJob', `job_${'f'.repeat(32)}`)
    await navigateSavedLink(view.page, missingJobUrl.href)
    await expect(view.page.locator('[data-rc-workflow-error]')).toBeVisible()
    await expect(view.page.locator('[data-job-service="ready"]')).toHaveCount(0)
    await view.page.goBack()
    // The prior URL was the empty submission page, not a saved job link.
    await expect(view.page.locator('[data-rc-project-link]')).toHaveCount(0)
    await view.page.goForward()
    await expect(view.page.locator('[data-rc-workflow-error]')).toBeVisible()
    await navigateSavedLink(view.page, savedJobUrl)
    await expect(view.page.locator('[data-rc-input-summary="stored"]')).toBeAttached()
    await expect(view.page.locator('[data-rc-project-link]')).toHaveAttribute('href', savedJobUrl)
    const first = await driver.command<{ pid: number; checkpoint_hash: string; abandoned_ordinal: number; actual_calls: { analysis: number; verification: number } }>('first_checkpoint')
    expect(first.actual_calls).toEqual({ analysis: 1, verification: 1 })
    expect(first.abandoned_ordinal).toBe(3)
    const killed = await driver.command<{ returncode: number; signal: string }>('kill_first')
    expect(killed).toMatchObject({ returncode: -9, signal: 'SIGKILL' })
    evidence.first_checkpoint = first
    evidence.worker_death = killed

    await view.context.close()
    server = await driver.command<Server>('restart_http')
    servers.push(server)
    expect(server.origin).toBe(new URL(savedJobUrl).origin)
    expect(server.pid).not.toBe(servers[0].pid)
    view = await freshPage(browser, ready.credentials, contexts, evidence)
    await view.page.goto(savedJobUrl)
    await expect(view.page.locator('[data-rc-input-summary="stored"]')).toBeAttached()
    await expect(view.page.locator('[data-job-service="ready"]')).toBeVisible()
    const restored = await driver.command<{ pid: number; checkpoint_hash: string; request_hash: string; progress: number; actual_calls: { analysis: number; verification: number } }>('resume_ready')
    expect(restored.pid).not.toBe(first.pid)
    expect(restored.checkpoint_hash).toBe(first.checkpoint_hash)
    expect(restored.request_hash).toBe(job.request.content_hash)
    expect(restored.progress).toBe(1)
    expect(restored.actual_calls).toEqual({ analysis: 0, verification: 0 })
    evidence.restored_before_numerical_calls = restored
    const completed = await driver.command<{ job: { status: string; result: { content_hash: string } }; actual_calls: { analysis: number; verification: number } }>('complete')
    expect(completed.job.status).toBe('succeeded')
    expect(completed.actual_calls).toEqual({ analysis: 1, verification: 1 })
    await verifiedReview(view.page, view.workerUrls)
    const invocationResponse = await view.page.request.get(`${server.origin}/v1/jobs/${job.job_id}/rc-invocations`, { headers: headers(ready.credentials) })
    expect(invocationResponse.status()).toBe(200)
    const invocations = await invocationResponse.json()
    expect(invocations.pending_ordinals).toEqual([3])
    expect(invocations.pending_execution_work).toBe('unknown')
    expect(invocations.invocations.map((row: { ordinal: number }) => row.ordinal)).toEqual([1, 2, 4, 5])
    await expect(view.page.locator('[data-rc-reserved]')).toHaveText('5')
    await expect(view.page.locator('[data-rc-unknown]')).toContainText(/unknown/i)
    evidence.invocation_evidence = invocations
    await driver.command('begin_prices', { job_id: job.job_id })
    await view.page.getByLabel('Include declared prices', { exact: true }).check()
    await view.page.getByLabel('Concrete price per m³', { exact: true }).fill('120')
    await view.page.getByLabel('Rebar price per kg', { exact: true }).fill('2')
    await view.page.getByLabel('Currency', { exact: true }).fill('USD')
    await view.page.getByLabel('Price date', { exact: true }).fill('2026-10-07')
    await view.page.getByLabel('Declared source', { exact: true }).fill('authored hosted lifecycle test declaration')
    const reports: ReportReference[] = []
    for (const concrete of ['120', '150']) {
      await view.page.getByLabel('Concrete price per m³', { exact: true }).fill(concrete)
      const saved = view.page.waitForResponse(response => response.url() === `${server.origin}/v1/jobs/${job.job_id}/rc-quantity-reports` && response.request().method() === 'POST')
      await view.page.getByRole('button', { name: 'Save quantity and price revision', exact: true }).click()
      const response = await saved
      expect(response.status()).toBe(200)
      const declaration = response.request().postDataJSON()
      expect(declaration.expected_request_hash).toBe(job.request.content_hash)
      expect(declaration.expected_result_artifact_hash).toBe(completed.job.result.content_hash)
      expect(declaration.declared_prices.concrete_per_m3).toBe(Number(concrete))
      const reference = await response.json() as ReportReference
      reports.push(reference)
      await expect(view.page.locator('[data-rc-quantity-report="verified"]')).toBeVisible()
      await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reference.report_id)
    }
    expect(reports.map(report => report.revision)).toEqual([1, 2])
    expect(reports[1].content_hash).not.toBe(reports[0].content_hash)
    const beforeRestart = await driver.command<{ reports: ReportReference[]; numerical_state_unchanged: boolean; http_numerical_calls: number; numerical_state_hash: string }>('verify_prices', { job_id: job.job_id })
    expect(beforeRestart.reports).toEqual(reports)
    expect(beforeRestart.numerical_state_unchanged).toBe(true)
    expect(beforeRestart.http_numerical_calls).toBe(0)
    const savedReportUrl = (await view.page.locator('[data-rc-report-link]').getAttribute('href'))!
    expect(new URL(savedReportUrl).searchParams.get('rcJob')).toBe(job.job_id)
    expect(new URL(savedReportUrl).searchParams.get('rcReport')).toBe(reports[1].report_id)
    expect(new URL(savedReportUrl).origin).toBe(server.origin)
    evidence.saved_report_url = savedReportUrl
    evidence.price_only = beforeRestart

    await view.context.close()
    server = await driver.command<Server>('restart_http')
    servers.push(server)
    expect(new Set(servers.map(row => row.pid)).size).toBe(3)
    view = await freshPage(browser, ready.credentials, contexts, evidence)
    await view.page.goto(savedReportUrl)
    await verifiedReview(view.page, view.workerUrls)
    await expect(view.page.locator('[data-rc-quantity-report="verified"]')).toBeVisible({ timeout: 90000 })
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    const revision = view.page.getByRole('combobox', { name: 'Saved quantity revision', exact: true })
    // Explicitly select each persisted revision after cold reopen, ensuring the
    // download is not merely a stale in-memory choice from the prior page.
    await revision.selectOption(reports[0].report_id)
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[0].report_id)
    await revision.selectOption(reports[1].report_id)
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    // A manual Open must not shadow later URL changes on the same surface.
    await view.page.getByLabel('Saved RC job ID', { exact: true }).fill(job.job_id)
    await view.page.getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    await navigateSavedLink(view.page, missingJobUrl.href)
    await expect(view.page.locator('[data-rc-workflow-error]')).toBeVisible()
    await expect(view.page.locator('[data-rc-review="verified"], [data-rc-quantity-report="verified"]')).toHaveCount(0)
    await view.page.goBack()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    await view.page.goForward()
    await expect(view.page.locator('[data-rc-workflow-error]')).toBeVisible()
    await view.page.goBack()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)

    // Release an obsolete Open's delayed authorization only after a newer
    // saved report has been verified. The old continuation must be discarded.
    await view.page.evaluate(() => {
      const host = window as any
      host.__rcAuthorizationWaiting = false; host.__rcAuthorizationSettled = false
      host.__rcAuthorizationGate = new Promise<void>(resolve => { host.__rcAuthorizationRelease = resolve })
    })
    await view.page.getByLabel('Saved RC job ID', { exact: true }).fill(`job_${'f'.repeat(32)}`)
    await view.page.getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await expect.poll(() => view.page.evaluate(() => (window as any).__rcAuthorizationWaiting)).toBe(true)
    const firstReportUrl = new URL(savedReportUrl)
    firstReportUrl.searchParams.set('rcReport', reports[0].report_id)
    await view.page.evaluate(() => { delete (window as any).__rcAuthorizationGate })
    await navigateSavedLink(view.page, firstReportUrl.href)
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[0].report_id)
    await view.page.evaluate(() => (window as any).__rcAuthorizationRelease())
    await expect.poll(() => view.page.evaluate(() => (window as any).__rcAuthorizationSettled)).toBe(true)
    await view.page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[0].report_id)
    await expect(view.page.locator('[data-rc-workflow-error]')).toHaveCount(0)
    await view.page.goBack()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    await view.page.goForward()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[0].report_id)
    await view.page.goBack()
    await expect(view.page.locator('[data-rc-saved-report-id]')).toHaveText(reports[1].report_id)
    evidence.navigation = { after_submit: true, after_manual_open: true, back_forward_report_identity: true, delayed_authorization_discarded: true }

    const pendingDownload = view.page.waitForEvent('download')
    await view.page.getByRole('button', { name: 'Download saved quantity report', exact: true }).click()
    const download = await pendingDownload
    expect(await download.failure()).toBeNull()
    const downloaded = await readFile((await download.path())!)
    const stored = await driver.command<{ base64: string; sha256: string; bytes: number }>('inspect_report', { job_id: job.job_id, report_id: reports[1].report_id })
    expect(downloaded).toEqual(Buffer.from(stored.base64, 'base64'))
    expect(downloaded.length).toBe(stored.bytes)
    if (profile === 'explicit-layers') expect(JSON.parse(downloaded.toString()).quantities.totals.longitudinal_rebar_mass_kg).toBeCloseTo(28.26, 10)
    expect(digest(downloaded)).toBe(stored.sha256)
    expect(stored.sha256).toBe(reports[1].content_hash)
    const direct = await view.page.request.get(`${server.origin}/v1/jobs/${job.job_id}/rc-quantity-reports/${reports[1].report_id}`, { headers: headers(ready.credentials) })
    expect(direct.status()).toBe(200)
    expect(direct.headers()['x-structural-report-sha256']).toBe(stored.sha256)
    expect(await direct.body()).toEqual(downloaded)
    const afterRestart = await driver.command('verify_prices', { job_id: job.job_id })
    expect(afterRestart).toEqual(beforeRestart)
    await writeFile(testInfo.outputPath('downloaded-revision-2.json'), downloaded)
    await testInfo.attach('downloaded-revision-2', { path: testInfo.outputPath('downloaded-revision-2.json'), contentType: 'application/json' })
    evidence.download = { bytes: downloaded.length, sha256: digest(downloaded), filename: download.suggestedFilename() }
    expect(await view.page.evaluate(token => JSON.stringify({ ...localStorage, ...sessionStorage }).includes(token), ready.credentials.bearerToken)).toBe(false)

    const authorizationResults = []
    for (const [name, credentials, expected] of [
      ['wrong-principal', { ...ready.credentials, bearerToken: 'wrong-synthetic-token' }, 401],
      ['tenant-b', ready.other_credentials, 404],
    ] as const) {
      const rejected = await freshPage(browser, credentials, contexts, evidence)
      const jobRead = rejected.page.waitForResponse(response => response.url() === `${server.origin}/v1/jobs/${job.job_id}`)
      await rejected.page.goto(savedReportUrl)
      expect((await jobRead).status()).toBe(expected)
      await expect(rejected.page.locator('[data-rc-workflow-error]')).toBeVisible()
      await expect(rejected.page.locator('[data-rc-review="verified"], [data-rc-quantity-report="verified"]')).toHaveCount(0)
      await expect(rejected.page.getByRole('button', { name: 'Download saved quantity report', exact: true })).toHaveCount(0)
      const reportRead = await rejected.page.request.get(`${server.origin}/v1/jobs/${job.job_id}/rc-quantity-reports/${reports[1].report_id}`, { headers: headers(credentials) })
      expect(reportRead.status()).toBe(expected)
      authorizationResults.push({ name, job_status: expected, report_status: reportRead.status() })
      await rejected.context.close()
    }
    evidence.authorization = authorizationResults
    evidence.completed = true
  } finally {
    for (const context of contexts) await context.close().catch(() => undefined)
    try { await driver.close() } catch (error) { cleanupError = error }
    evidence.driver_exit = { exit_code: driver.child.exitCode, signal: driver.child.signalCode, ended: driver.ended }
    evidence.cleanup_error = cleanupError ? String(cleanupError) : null
    await mkdir(testInfo.outputPath('lifecycle-store'), { recursive: true })
    // Preserve the actual SQLite store, blobs and process receipts on both
    // success and failure. No passing flags are added by this evidence copy.
    await cp(workspace, testInfo.outputPath('lifecycle-store'), { recursive: true })
    await writeFile(testInfo.outputPath('driver-stdout.jsonl'), driver.stdout)
    await writeFile(testInfo.outputPath('driver-stderr.txt'), driver.stderr)
    await writeFile(testInfo.outputPath('rc-lifecycle-browser-proof.json'), JSON.stringify(evidence, null, 2))
    await testInfo.attach('rc-lifecycle-browser-proof', { path: testInfo.outputPath('rc-lifecycle-browser-proof.json'), contentType: 'application/json' })
    if (!cleanupError && driver.ended && driver.child.exitCode === 0) await rm(workspace, { recursive: true, force: true })
    if (cleanupError) throw cleanupError
    expect(driver.child.exitCode).toBe(0)
  }
})
}
