import { expect, test, type Browser, type BrowserContext, type Page, type Response } from '@playwright/test'
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
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
  pin_roller_layers_request: Record<string, unknown>
  proof: { checkout_sha: string | null; github_sha: string | null; github_run_id: string | null; github_run_attempt: string | null; source_revision_caller_declaration: string }
}
type Server = { pid: number; origin: string; port: number; previous_pid?: number }
const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
const headers = ({ tenantId, bearerToken }: Credentials) => ({ 'X-Structural-Tenant': tenantId, Authorization: `Bearer ${bearerToken}` })

// Deliberately expose no body-reading method: every lifecycle profile must
// retain its assertions even when the browser protocol has no body to return.
function mutationMetadata(response: Response): Pick<Response, 'status' | 'request'> {
  return { status: () => response.status(), request: () => response.request() }
}

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
  constructor(workspace: string, managed = false, fixture = 'rc_lifecycle_http_fixture.py') {
    // This separate hosted lane intentionally retains setup-python's PATH.
    // The normal sanitized frontend runner is unchanged and never starts Python.
    this.child = spawn('python', ['-B', `tests/frontend/${fixture}`, 'driver', '--workspace', workspace, ...(managed ? ['--managed'] : [])], {
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

test('actual authored designs compare real core outputs and a failed input becomes an explicitly changed new job', async ({ browser }, testInfo) => {
  test.setTimeout(240000)
  const workspace = await mkdtemp(join(tmpdir(), 'structural-rc-browser-'))
  const driver = new Driver(workspace, false, 'rc_authoring_http_fixture.py')
  const contexts: BrowserContext[] = []
  const evidence: Record<string, unknown> = { scope: 'bounded actual core software integration; no physical validation', completed: false }
  try {
    const ready = await driver.read<{ ready: boolean; requests: Record<string, any>; credentials: Credentials }>(20000)
    expect(ready.ready).toBe(true)
    const server = await driver.command<Server>('start_http')
    const view = await freshPage(browser, ready.credentials, contexts, evidence)
    await view.page.goto(`${server.origin}/#/workbench-v2`)
    await view.page.getByText('Submit a new RC input', { exact: true }).click()
    await view.page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(ready.requests.baseline))
    const editor = view.page.locator('[data-rc-model-editor]')
    await expect(editor.locator('[data-rc-preview-node]')).toHaveCount(2)
    const scenarios = view.page.locator('[data-rc-scenario-comparison]')
    await scenarios.getByLabel('Scenario name', { exact: true }).fill('Baseline')
    await scenarios.getByRole('button', { name: 'Capture current design', exact: true }).click()
    // Change a physical section through the real editor, then explicitly apply
    // before capture. No HTTP submission occurs during authoring.
    await editor.getByLabel('case_id', { exact: true }).fill('authoring-wider')
    await editor.getByText('Sections (1)', { exact: true }).click()
    await editor.getByLabel('width_m', { exact: true }).fill(String(ready.requests.wider.model.sections[0].width_m))
    await expect(scenarios.getByRole('button', { name: 'Capture current design', exact: true })).toBeDisabled()
    await editor.getByRole('button', { name: 'Apply structured model to draft', exact: true }).click()
    await expect(view.page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(JSON.stringify(ready.requests.wider, null, 2))
    await scenarios.getByLabel('Scenario name', { exact: true }).fill('Wider')
    await scenarios.getByRole('button', { name: 'Capture current design', exact: true }).click()
    await scenarios.getByRole('button', { name: 'Run captured designs', exact: true }).click()
    await expect(scenarios.locator('[data-scenario-id]').nth(0)).toContainText(/job_[a-f0-9]{32}/)
    const first = await driver.command<any>('execute_one', {}, 90000)
    expect(first.job.status).toBe('succeeded')
    await expect(scenarios.locator('[data-scenario-id]').nth(0)).toContainText('succeeded', { timeout: 90000 })
    await expect(scenarios.locator('[data-scenario-id]').nth(1)).toContainText(/job_[a-f0-9]{32}/)
    const second = await driver.command<any>('execute_one', {}, 90000)
    expect(second.job.status).toBe('succeeded')
    await expect(scenarios.locator('[data-scenario-id]').nth(1)).toContainText('succeeded', { timeout: 90000 })
    await expect(scenarios.locator('[data-scenario-curve]')).toHaveCount(2)
    await expect(scenarios.getByRole('table')).toContainText('member_force')
    expect(view.workerUrls.some(url => /rcJobReview\.worker/.test(url))).toBe(true)
    const downloaded = view.page.waitForEvent('download')
    await scenarios.getByRole('button', { name: 'Export scenario JSON', exact: true }).click()
    const exportPath = join(workspace, 'comparison.json')
    await (await downloaded).saveAs(exportPath)
    const exported = JSON.parse(await readFile(exportPath, 'utf8'))
    expect(exported.scenarios.map((row: any) => row.status)).toEqual(['succeeded', 'succeeded'])
    expect(exported.scenarios[0].summary.bindings.resultHash).toBe(first.job.result.content_hash)
    expect(exported.scenarios[1].summary.bindings.resultHash).toBe(second.job.result.content_hash)
    const left = new Map(exported.scenarios[0].summary.values.map((row: any) => [row.key, row.value]))
    expect(exported.scenarios[1].summary.values.some((row: any) => row.value !== left.get(row.key))).toBe(true)
    const screenshot = testInfo.outputPath('actual-design-comparison.png')
    await scenarios.screenshot({ path: screenshot })
    await testInfo.attach('actual-design-comparison.png', { path: screenshot, contentType: 'image/png' })
    await view.page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(ready.requests.failed))
    await view.page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect(view.page.locator('[data-rc-project-link]')).toBeVisible()
    const failed = await driver.command<any>('execute_one', {}, 90000)
    expect(failed.job.status).toBe('failed')
    await expect(view.page.locator('[data-job-status="failed"]')).toBeVisible({ timeout: 90000 })
    const diagnostics = view.page.locator('[data-rc-diagnostics]')
    await expect(diagnostics.getByRole('table')).toContainText('verification')
    await diagnostics.getByRole('button', { name: 'Inspect invocation 1', exact: true }).click()
    await expect(diagnostics.locator('[data-rc-invocation-detail]')).toContainText('Invocation 1')
    await diagnostics.getByRole('button', { name: 'Copy failed input for a changed run', exact: true }).click()
    await expect(view.page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeDisabled()
    await view.page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(ready.requests.repaired))
    await expect(view.page.locator('[data-rc-changed-run]')).toContainText('/execution_config/maximum_api_invocations')
    await view.page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect(view.page.locator('[data-rc-changed-run]')).toContainText('New job:')
    const repaired = await driver.command<any>('execute_one', {}, 90000)
    expect(repaired.job.status).toBe('succeeded')
    expect(repaired.job.job_id).not.toBe(failed.job.job_id)
    await verifiedReview(view.page, view.workerUrls)
    // Inspect the already-produced result. These interactions may only read
    // retained values; they add no fifth job or numerical execution.
    const visualizationPosts: string[] = []
    view.page.on('request', request => { if (request.method() === 'POST') visualizationPosts.push(request.url()) })
    const fixedReview = view.page.locator('[data-rc-review="verified"]')
    const originalResultDownload = view.page.waitForEvent('download')
    await fixedReview.getByRole('button', { name: 'Download RC result', exact: true }).click()
    const originalResultPath = join(workspace, 'visualized-original-result.json')
    await (await originalResultDownload).saveAs(originalResultPath)
    const originalResultBytes = await readFile(originalResultPath)
    expect(digest(originalResultBytes)).toBe(repaired.job.result.content_hash)
    const apiResult = JSON.parse(originalResultBytes.toString('utf8')).api_result
    const resultHistory = apiResult.preload_response ? [apiResult.preload_response, ...apiResult.response_history] : apiResult.response_history
    const finalResponse = resultHistory[resultHistory.length - 1], shape = fixedReview.locator('[data-rc-deformed-shape]')
    const checkShape = async (response: any, scale: number) => {
      await expect(shape.locator('[data-rc-member]')).toHaveCount(ready.requests.repaired.model.elements.length)
      for (const member of ready.requests.repaired.model.elements) {
        const element = shape.locator(`[data-rc-member="${member.id}"]`)
        for (const [index, nodeId] of member.nodes.entries()) {
          const node = ready.requests.repaired.model.nodes.find((value: any) => value.id === nodeId)
          const displacement = response.node_displacements.find((value: any) => value.node_id === nodeId)
          for (const [axis, component, field] of [['x', 0, 'UX_m'], ['y', 1, 'UY_m']] as const) {
            const coordinate = node.coordinates[component]
            await expect(element).toHaveAttribute(`data-rc-${axis}${index + 1}`, String(coordinate))
            await expect(element).toHaveAttribute(`data-rc-deformed-${axis}${index + 1}`, String(coordinate + scale * displacement[field]))
          }
        }
      }
    }
    await checkShape(finalResponse, 1)
    await fixedReview.getByLabel('Deformation scale', { exact: true }).fill('1000')
    await checkShape(finalResponse, 1000)
    const memberId = ready.requests.repaired.model.elements[0].id
    await fixedReview.getByLabel('Result member', { exact: true }).selectOption('')
    const selectedMember = shape.getByRole('button', { name: `Select member ${memberId}`, exact: true })
    await selectedMember.focus(); await selectedMember.press('Enter')
    await expect(fixedReview.getByLabel('Result member', { exact: true })).toHaveValue(memberId)
    await expect(selectedMember).toHaveAttribute('aria-pressed', 'true')
    const memberResponse = finalResponse.member_end_forces.find((value: any) => value.member_id === memberId)
    await expect(fixedReview.locator('[data-rc-table="members"] tbody tr').filter({ has: view.page.getByRole('rowheader', { name: memberId, exact: true }) }).locator('td'))
      .toHaveText([memberResponse.local_end_i.FX_N, memberResponse.local_end_i.FY_N, memberResponse.local_end_i.MZ_Nm,
        memberResponse.local_end_j.FX_N, memberResponse.local_end_j.FY_N, memberResponse.local_end_j.MZ_Nm].map(String))
    const sectionPlot = fixedReview.locator('[data-rc-history-plot="Section moment–curvature history"]')
    const fiberPlot = fixedReview.locator('[data-rc-history-plot="Fiber stress–strain history"]')
    await expect(sectionPlot.locator('[data-rc-history-point]')).toHaveCount(resultHistory.length)
    await expect(fiberPlot.locator('[data-rc-history-point]')).toHaveCount(resultHistory.length)
    const sectionKey = JSON.parse(await fixedReview.getByLabel('RC section history', { exact: true }).inputValue())
    const fiberKey = JSON.parse(await fixedReview.getByLabel('RC material point history', { exact: true }).inputValue())
    const plotted = async (locator: typeof sectionPlot) => locator.locator('[data-rc-history-point]').evaluateAll(elements => elements.map(element => ({
      state: Number(element.getAttribute('data-rc-history-point')), x: Number(element.getAttribute('data-rc-x')), y: Number(element.getAttribute('data-rc-y')),
    })))
    expect(await plotted(sectionPlot)).toEqual(resultHistory.map((response: any, state: number) => {
      const section = response.section_results.find((value: any) => value.member_id === sectionKey[0] && value.integration_point_index === sectionKey[1])
      return { state, x: section.curvature_z_per_m, y: section.moment_z_Nm }
    }))
    expect(await plotted(fiberPlot)).toEqual(resultHistory.map((response: any, state: number) => {
      const fiber = response.fiber_results.find((value: any) => value.member_id === fiberKey[0] && value.integration_point_index === fiberKey[1] && value.fiber_index === fiberKey[2])
      return { state, x: fiber.strain, y: fiber.stress_MPa }
    }))
    const firstSectionPoint = sectionPlot.locator('[data-rc-history-point="0"]')
    await firstSectionPoint.focus(); await firstSectionPoint.press('Enter')
    await expect(fixedReview.getByLabel('RC target to inspect', { exact: true })).toHaveValue('0')
    await checkShape(resultHistory[0], 1000)
    for (const node of resultHistory[0].node_displacements) await expect(fixedReview.locator('[data-rc-table="nodes"] tbody tr')
      .filter({ has: view.page.getByRole('rowheader', { name: node.node_id, exact: true }) }).locator('td'))
      .toHaveText([node.UX_m, node.UY_m, node.UZ_m, node.RX_rad, node.RY_rad, node.RZ_rad].map(String))
    await fixedReview.getByLabel('Fiber stress–strain history stored state', { exact: true }).selectOption(String(resultHistory.length - 1))
    await expect(fixedReview.getByLabel('RC target to inspect', { exact: true })).toHaveValue(String(resultHistory.length - 1))
    await checkShape(finalResponse, 1000)
    expect(visualizationPosts).toEqual([])
    const explorerScreenshot = testInfo.outputPath('actual-fixed-result-explorer.png')
    await fixedReview.screenshot({ path: explorerScreenshot })
    await testInfo.attach('actual-fixed-result-explorer.png', { path: explorerScreenshot, contentType: 'image/png' })
    evidence.resultExploration = { sourceResultHash: repaired.job.result.content_hash, states: resultHistory.length,
      geometryScale: 1000, selectedMember: memberId, sectionKey, fiberKey, additionalSubmissions: visualizationPosts.length }
    await view.page.getByText('Submit a new RC input', { exact: true }).click()
    await expect(view.page.locator('[data-rc-changed-run]')).toContainText('current new job status: succeeded')
    const retained = await driver.command<any>('inspect_job', { job_id: failed.job.job_id })
    expect(retained.job.status).toBe('failed')
    expect(retained.original_request).toEqual(ready.requests.failed)
    expect(retained.original_request_hash).toBe(failed.job.request.content_hash)
    // Reopen the complete authored project in a new browser context. Existing
    // numerical work is reused through authenticated reads and fresh reviewers;
    // no fifth solver job or submission is permitted by this restoration test.
    const projectDownload = view.page.waitForEvent('download')
    await view.page.getByRole('button', { name: 'Save RC project', exact: true }).click()
    const projectPath = join(workspace, 'rc-workbench-project.json')
    await (await projectDownload).saveAs(projectPath)
    const projectBytes = await readFile(projectPath), projectFile = JSON.parse(projectBytes.toString('utf8'))
    expect(projectFile.scenarios).toHaveLength(2)
    expect(projectFile.submission.job.jobId).toBe(repaired.job.job_id)
    expect(projectFile.changedRun.original.jobId).toBe(failed.job.job_id)
    const reopened = await freshPage(browser, ready.credentials, contexts, evidence)
    const reopenedPosts: string[] = []
    reopened.page.on('request', request => { if (request.method() === 'POST') reopenedPosts.push(request.url()) })
    await reopened.page.goto(`${server.origin}/#/workbench-v2`)
    const projectInput = reopened.page.getByLabel('Open RC project file', { exact: true })
    await expect(projectInput).toBeEnabled()
    await projectInput.setInputFiles({ name: 'rc-workbench-project.json', mimeType: 'application/json', buffer: projectBytes })
    await verifiedReview(reopened.page, reopened.workerUrls)
    const restoredScenarios = reopened.page.locator('[data-rc-scenario-comparison]')
    await expect(restoredScenarios.locator('[data-scenario-curve]')).toHaveCount(0)
    for (const name of ['Baseline', 'Wider']) {
      await restoredScenarios.getByRole('button', { name: `Refresh ${name}`, exact: true }).click()
      await expect(restoredScenarios.locator('[data-scenario-id]').filter({ has: reopened.page.getByText(name, { exact: true }) })).toContainText('succeeded')
    }
    await expect(restoredScenarios.locator('[data-scenario-curve]')).toHaveCount(2)
    await reopened.page.getByText('Submit a new RC input', { exact: true }).click()
    await expect(reopened.page.locator('[data-rc-changed-run]')).toContainText(failed.job.job_id)
    await expect(reopened.page.locator('[data-rc-changed-run]')).toContainText(repaired.job.job_id)
    await expect(reopened.page.locator('[data-rc-changed-run]')).toContainText('/execution_config/maximum_api_invocations')
    const reexportDownload = reopened.page.waitForEvent('download')
    await restoredScenarios.getByRole('button', { name: 'Export scenario JSON', exact: true }).click()
    const reexportPath = join(workspace, 'restored-comparison.json')
    await (await reexportDownload).saveAs(reexportPath)
    const reexported = JSON.parse(await readFile(reexportPath, 'utf8'))
    expect(reexported).toEqual(exported)
    expect(reopenedPosts).toEqual([])
    evidence.projectRestoration = { schema: projectFile.schema, freshBrowser: true, submissions: reopenedPosts.length,
      verifiedJobIds: [first.job.job_id, second.job.job_id, repaired.job.job_id], comparisonUnchanged: true,
      originalFailedJobId: failed.job.job_id }
    evidence.completed = true
    evidence.jobs = [first.job, second.job, failed.job, repaired.job]
    evidence.workerProcesses = [first.process, second.process, failed.process, repaired.process]
    expect((evidence.workerProcesses as any[]).every(process => process.reaped && process.returncode === 0)).toBe(true)
    evidence.comparison = exported
    const proof = testInfo.outputPath('authoring-scenario-diagnostics.json')
    await writeFile(proof, JSON.stringify(evidence, null, 2))
    await testInfo.attach('authoring-scenario-diagnostics.json', { path: proof, contentType: 'application/json' })
  } finally {
    try { for (const context of contexts) await context.close() }
    finally { await driver.close() }
    const output = testInfo.outputPath('authoring-driver-output.json')
    await writeFile(output, JSON.stringify({ stdout: driver.stdout, stderr: driver.stderr, workspace }))
    await testInfo.attach('authoring-driver-output', { path: output, contentType: 'application/json' })
    // Keep the disposable test artifacts if any assertion failed.
    if (evidence.completed) expect(driver.child.exitCode).toBe(0)
    if (evidence.completed && driver.ended && driver.child.exitCode === 0) await rm(workspace, { recursive: true, force: true })
  }
})

for (const { profile, isolated, managed } of [
  ...['cantilever', 'explicit-layers', 'pin-roller', 'pin-roller-layers', 'fixed-guided'].map(profile => ({ profile, isolated: false, managed: false })),
  { profile: 'pin-roller-layers', isolated: true, managed: false },
  { profile: 'pin-roller-layers', isolated: true, managed: true },
]) {
test(`actual Workbench ${profile}${isolated ? ' isolated' : ''}${managed ? ' managed' : ''} RC job survives SIGKILL and two cold HTTP/browser reopens, then downloads immutable price revision two`, async ({ browser }, testInfo) => {
  test.setTimeout(300000)
  const workspace = await mkdtemp(join(tmpdir(), 'structural-rc-browser-'))
  const driver = new Driver(workspace, managed)
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
    if (profile === 'pin-roller') ready.request = JSON.parse(execFileSync('python3',
      ['tests/frontend/rc_pin_roller_request.py'], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: resolve('src') } }))
    if (profile === 'fixed-guided') ready.request = JSON.parse(execFileSync('python3',
      ['tests/frontend/rc_fixed_guided_request.py'], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: resolve('src') } }))
    evidence.support_profile = profile
    if (profile === 'pin-roller-layers') ready.request = ready.pin_roller_layers_request
    if (isolated) (ready.request.execution_config as Record<string, unknown>).phase_execution_policy = {
      schema_version: 'bounded-rc-fiber-phase-execution-policy.v1',
      analysis_timeout_ms: 30000, verification_timeout_ms: 30000, termination_grace_ms: 100,
    }
    evidence.isolated = isolated
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
    const submitted = mutationMetadata(await submission)
    expect(submitted.status()).toBe(202)
    expect(submitted.request().postDataJSON()).toEqual(ready.request)
    // Chromium may discard the DevTools copy of a consumed fetch body. Bind
    // the browser's real POST to its visible identity and independent store read.
    const projectLink = view.page.locator('[data-rc-project-link]')
    await expect(projectLink).toBeVisible()
    const savedJobUrl = (await projectLink.getAttribute('href'))!
    expect(new URL(savedJobUrl).origin).toBe(server.origin)
    const visibleJobId = new URL(savedJobUrl).searchParams.get('rcJob')
    expect(visibleJobId).toMatch(/^job_[0-9a-f]{32}$/)
    const persisted = await driver.command<{
      job: { job_id: string; status: string; request: { content_hash: string } }
      original_request: Record<string, unknown>; original_request_hash: string
    }>('inspect_job', { job_id: visibleJobId })
    const job = persisted.job
    expect(job.job_id).toBe(visibleJobId)
    expect(job.status).toBe('queued')
    expect(job.job_id).toMatch(/^job_[0-9a-f]{32}$/)
    evidence.submission = { status: submitted.status(), job_id: job.job_id, request: job.request }
    expect(persisted.original_request).toEqual(ready.request)
    expect(persisted.original_request_hash).toBe(job.request.content_hash)
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
    const first = await driver.command<{ pid: number; checkpoint_hash: string; abandoned_ordinal: number; actual_calls: { analysis: number; verification: number }; isolated_phases: { phase: string; status: string; supervision: { child_pid: number; child_returncode: number; direct_child_reaped: boolean } }[] }>('first_checkpoint')
    expect(first.actual_calls).toEqual({ analysis: isolated ? 0 : 1, verification: isolated ? 0 : 1 })
    expect(first.abandoned_ordinal).toBe(3)
    const killed = await driver.command<{ returncode: number; signal: string }>('kill_first')
    expect(killed).toMatchObject({ returncode: -9, signal: 'SIGKILL' })
    evidence.first_checkpoint = first
    evidence.worker_death = killed

    await view.context.close()
    if (profile === 'pin-roller-layers') {
      const backup = await driver.command<{ restored_rows_equal: boolean; source_store: string; restored_store: string; original_worker_returncode: number; original_http_returncode: number; automatic_original_writer_fencing: boolean; managed_activation: { status: string; generation: number } | null; stale_source_rejected: boolean }>('backup_restore')
      expect(backup.restored_rows_equal).toBe(true)
      expect(backup.source_store).not.toBe(backup.restored_store)
      expect(backup.original_worker_returncode).toBe(-9)
      expect(backup.original_http_returncode).not.toBeNull()
      expect(backup.automatic_original_writer_fencing).toBe(false)
      expect(backup.stale_source_rejected).toBe(managed)
      if (managed) expect(backup.managed_activation).toMatchObject({ status: 'activated', generation: 2 })
      else expect(backup.managed_activation).toBeNull()
      evidence.operator_backup_restore = backup
    }
    server = await driver.command<Server>('restart_http')
    servers.push(server)
    expect(server.origin).toBe(new URL(savedJobUrl).origin)
    expect(server.pid).not.toBe(servers[0].pid)
    view = await freshPage(browser, ready.credentials, contexts, evidence)
    await view.page.goto(savedJobUrl)
    await expect(view.page.locator('[data-rc-input-summary="stored"]')).toBeAttached()
    await expect(view.page.locator('[data-job-service="ready"]')).toBeVisible()
    const restored = await driver.command<{ pid: number; checkpoint_hash: string; request_hash: string; progress: number; actual_calls: { analysis: number; verification: number }; isolated_phases: { phase: string; status: string; supervision: { child_pid: number; child_returncode: number; direct_child_reaped: boolean } }[] }>('resume_ready')
    expect(restored.pid).not.toBe(first.pid)
    expect(restored.checkpoint_hash).toBe(first.checkpoint_hash)
    expect(restored.request_hash).toBe(job.request.content_hash)
    expect(restored.progress).toBe(1)
    expect(restored.actual_calls).toEqual({ analysis: 0, verification: 0 })
    evidence.restored_before_numerical_calls = restored
    const completed = await driver.command<{ job: { status: string; result: { content_hash: string } }; actual_calls: { analysis: number; verification: number }; isolated_phases: { phase: string; status: string; supervision: { child_pid: number; child_returncode: number; direct_child_reaped: boolean } }[] }>('complete')
    expect(completed.job.status).toBe('succeeded')
    expect(completed.actual_calls).toEqual({ analysis: isolated ? 0 : 1, verification: isolated ? 0 : 1 })
    for (const phaseRecords of [first.isolated_phases, completed.isolated_phases]) {
      expect(phaseRecords.map(record => record.phase)).toEqual(isolated ? ['analysis', 'verification'] : [])
      for (const record of phaseRecords) {
        expect(record.status).toBe('returned')
        expect(record.supervision.direct_child_reaped).toBe(true)
        expect(record.supervision.child_returncode).toBe(0)
      }
    }
    expect(restored.isolated_phases).toEqual([])
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
      const response = mutationMetadata(await saved)
      expect(response.status()).toBe(200)
      const declaration = response.request().postDataJSON()
      expect(declaration.expected_request_hash).toBe(job.request.content_hash)
      expect(declaration.expected_result_artifact_hash).toBe(completed.job.result.content_hash)
      expect(declaration.declared_prices.concrete_per_m3).toBe(Number(concrete))
      await expect(view.page.locator('[data-rc-quantity-report="verified"]')).toBeVisible()
      const visibleReport = view.page.locator('[data-rc-saved-report-id]')
      await expect(visibleReport).toBeVisible()
      if (reports.length) await expect(visibleReport).not.toHaveText(reports[reports.length - 1].report_id)
      const visibleReportId = (await visibleReport.textContent())!.trim()
      // Read actual persisted references through the authenticated API, not
      // Chromium's optional response-body cache. No POST is repeated.
      const reportList = await view.context.request.get(`${server.origin}/v1/jobs/${job.job_id}/rc-quantity-reports`, { headers: headers(ready.credentials) })
      expect(reportList.status()).toBe(200)
      const listed = await reportList.json() as { reports: ReportReference[] }
      expect(listed.reports).toHaveLength(reports.length + 1)
      const matches = listed.reports.filter(reference => reference.report_id === visibleReportId)
      expect(matches).toHaveLength(1)
      const reference = matches[0]
      expect(reference.revision).toBe(reports.length + 1)
      reports.push(reference)
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
    if (profile.endsWith('layers')) expect(JSON.parse(downloaded.toString()).quantities.totals.longitudinal_rebar_mass_kg).toBeCloseTo(profile === 'pin-roller-layers' ? 17.898 : 28.26, 10)
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
