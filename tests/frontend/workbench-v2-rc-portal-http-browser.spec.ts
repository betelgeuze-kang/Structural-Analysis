import { expect, test, type BrowserContext } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

async function deadline<T>(pending: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try { return await Promise.race([pending, new Promise<T>((_, reject) => { timer = setTimeout(() => reject(new Error('Portal fixture timed out')), ms) })]) }
  finally { if (timer) clearTimeout(timer) }
}
class Driver {
  child; lines; closed; sequence = 0; stdout = ''; stderr = ''; healthy = true
  constructor(workspace: string) {
    this.child = spawn('python', ['-B', 'tests/frontend/rc_portal_http_fixture.py', 'driver', '--workspace', workspace], {
      env: { ...process.env, PYTHONPATH: resolve('src'), OPENBLAS_NUM_THREADS: '1' }, stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.closed = new Promise<void>(done => this.child.once('close', () => done()))
    this.child.on('error', error => { this.stderr += String(error); this.healthy = false })
    this.child.stdin.on('error', error => { this.stderr += String(error); this.healthy = false })
    this.child.stdout.on('data', value => { this.stdout += String(value) })
    this.child.stderr.on('data', value => { this.stderr += String(value) })
    this.lines = createInterface({ input: this.child.stdout })[Symbol.asyncIterator]()
  }
  async read(): Promise<any> {
    const line = await deadline(this.lines.next(), 90000)
    if (line.done) throw new Error(`Portal fixture exited: ${this.stderr}`)
    return JSON.parse(line.value)
  }
  async command(command: string, fields = {}): Promise<any> {
    const id = ++this.sequence
    this.child.stdin.write(JSON.stringify({ id, command, ...fields }) + '\n')
    try {
      const value = await this.read()
      expect(value.id).toBe(id); expect(value.ok).toBe(true)
      return value.result
    } catch (error) { this.healthy = false; throw error }
  }
  async close() {
    if (this.child.exitCode === null && this.child.signalCode === null) {
      if (this.healthy) { try { await this.command('stop') } catch { this.child.kill('SIGTERM') } }
      else this.child.kill('SIGTERM')
      try { await deadline(this.closed, 15000) }
      catch { this.child.kill('SIGKILL'); await deadline(this.closed, 5000); throw new Error('Portal driver forced shut down; retain child cleanup evidence') }
    }
  }
}

test('RC portal is authored, paused at a checkpoint, saved, resumed in a fresh process and reviewed after cold reopen', async ({ browser }, testInfo) => {
  test.setTimeout(240000)
  const workspace = await mkdtemp(join(tmpdir(), 'structural-rc-browser-'))
  const driver = new Driver(workspace), contexts: BrowserContext[] = []
  const evidence: Record<string, any> = { completed: false, scope: 'tiny portal software integration; elastic-range reference; no physical qualification' }
  try {
    const ready = await driver.read()
    expect(ready.ready).toBe(true)
    let server = await driver.command('start_http')
    const newView = async () => {
      const context = await browser.newContext({ acceptDownloads: true }); contexts.push(context)
      expect(await context.storageState()).toEqual({ cookies: [], origins: [] })
      await context.addInitScript(credentials => {
        window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobAuthorization: async () => credentials }
      }, ready.credentials)
      const page = await context.newPage(), posts: string[] = [], workers: string[] = []
      page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()) })
      page.on('worker', worker => workers.push(worker.url()))
      await page.goto(`${server.origin}/#/workbench-v2`)
      return { page, context, posts, workers }
    }
    const view = await newView()
    await view.page.getByText('Submit a new RC input', { exact: true }).click()
    const editor = view.page.locator('[data-rc-model-editor]')
    await editor.getByText('Start from the RC portal example', { exact: true }).click()
    await editor.getByLabel('Caller-declared source revision for portal example', { exact: true }).fill(ready.request.source_revision)
    await editor.getByRole('button', { name: 'Load portal example locally', exact: true }).click()
    await expect(editor.locator('[data-rc-preview-node]')).toHaveCount(4)
    await expect(editor.locator('[data-rc-preview-load-phase="fixed"]')).toHaveCount(2)
    await expect(editor.locator('[data-rc-preview-load-phase="reference"]')).toHaveCount(1)
    await editor.getByRole('button', { name: 'Apply structured model to draft', exact: true }).click()
    expect(JSON.parse(await view.page.getByLabel('Typed RC request JSON', { exact: true }).inputValue())).toEqual(ready.request)
    expect(view.posts).toEqual([])
    await view.page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect(view.page.locator('[data-rc-project-link]')).toBeVisible()
    const first = await driver.command('first_checkpoint')
    expect(first.job.status).toBe('checkpointed')
    await expect(view.page.locator('[data-job-status="checkpointed"]')).toBeVisible({ timeout: 30000 })
    await view.page.getByRole('button', { name: 'Pause job', exact: true }).click()
    await expect(view.page.locator('[data-rc-job-control-state="paused"]')).toBeVisible()
    const held = await driver.command('inspect_paused', { job_id: first.job.job_id })
    expect(held.claim_held).toBe(true)
    expect(held.state_unchanged).toBe(true)
    expect(held.control.job.checkpoint_hash).toBe(first.checkpoint_hash)
    expect(held.control.last_command.disposition).toBe('paused')
    const killed = await driver.command('kill_first')
    expect(killed.returncode).toBe(-9)
    const download = view.page.waitForEvent('download')
    await view.page.getByRole('button', { name: 'Save RC project', exact: true }).click()
    const projectPath = join(workspace, 'portal-project.json')
    await (await download).saveAs(projectPath)
    const projectBytes = await readFile(projectPath)
    expect(JSON.parse(projectBytes.toString()).submission.job.jobId).toBe(first.job.job_id)
    expect(view.posts).toHaveLength(2)
    expect(view.posts.filter(url => url.endsWith('/rc-control'))).toHaveLength(1)
    await view.context.close()
    server = await driver.command('restart_http')
    const reopened = await newView()
    await reopened.page.getByLabel('Open RC project file', { exact: true }).setInputFiles({ name: 'portal-project.json', mimeType: 'application/json', buffer: projectBytes })
    await expect(reopened.page.locator('[data-job-status="checkpointed"]')).toBeVisible({ timeout: 30000 })
    const inspected = await driver.command('inspect_job', { job_id: first.job.job_id })
    expect(inspected.job.checkpoint.content_hash).toBe(first.checkpoint_hash)
    expect(inspected.control).toEqual(held.control)
    expect(inspected.invocations).toEqual(held.invocations)
    await expect(reopened.page.locator('[data-rc-job-control-state="paused"]')).toBeVisible()
    expect(reopened.posts).toEqual([])
    await reopened.page.getByRole('button', { name: 'Resume paused job', exact: true }).click()
    await expect(reopened.page.locator('[data-rc-job-control-state="available"]')).toBeVisible()
    const resumed = await driver.command('inspect_job', { job_id: first.job.job_id })
    expect(resumed.job.request).toEqual(inspected.job.request)
    expect(resumed.job.checkpoint).toEqual(inspected.job.checkpoint)
    expect(resumed.job.attempt).toBe(inspected.job.attempt)
    expect(resumed.invocations).toEqual(inspected.invocations)
    expect(resumed.control.last_command.disposition).toBe('resumed')
    const finished = await driver.command('finish')
    expect(finished.job.status).toBe('succeeded')
    expect(finished.resumed_checkpoint_hash).toBe(first.checkpoint_hash)
    expect(finished.job.request.content_hash).toBe(first.job.request.content_hash)
    expect(finished.pid).not.toBe(first.pid)
    const review = reopened.page.locator('[data-rc-corotational-review="report_verified"]')
    await expect(review).toBeVisible({ timeout: 90000 })
    await expect(review.locator('[data-rc-corotational-targets]')).toHaveText('3/3')
    expect(reopened.workers.some(url => /rcCorotationalReportReview\.worker/.test(url))).toBe(true)
    const reportDownload = reopened.page.waitForEvent('download')
    await review.getByRole('button', { name: 'Download corotational nodal report', exact: true }).click()
    const reportPath = join(workspace, 'portal-report.json')
    await (await reportDownload).saveAs(reportPath)
    const report = JSON.parse(await readFile(reportPath, 'utf8'))
    expect(report.report_hash).toMatch(/^sha256:[a-f0-9]{64}$/)
    await testInfo.attach('portal-report', { path: reportPath, contentType: 'application/json' })
    await testInfo.attach('portal-project', { path: projectPath, contentType: 'application/json' })
    expect(report.responses[0].phase).toBe('preload')
    expect(report.responses.slice(1).map((row: any) => row.control_displacement_m)).toEqual(ready.request.config.targets_m)
    await review.getByLabel('Deformation scale', { exact: true }).fill('1000')
    for (const row of report.responses) {
      await review.getByLabel('Accepted state to inspect', { exact: true }).selectOption(String(row.state_index))
      await expect(review.locator('[data-rc-corotational-selected]')).toContainText(`Accepted state ${row.state_index} ·`)
      const shape = review.locator('[data-rc-deformed-shape]')
      await expect(shape.locator('[data-rc-member]')).toHaveCount(3)
      for (const member of ready.request.model.elements) {
        for (const [i, id] of member.nodes.entries()) {
          const node = ready.request.model.nodes.find((value: any) => value.id === id)
          const response = row.nodes.find((value: any) => value.node_id === id)
          await expect(shape.locator(`[data-rc-member="${member.id}"]`)).toHaveAttribute(`data-rc-deformed-x${i + 1}`, String(node.coordinates[0] + 1000 * response.displacements_m_rad[0]))
          await expect(shape.locator(`[data-rc-member="${member.id}"]`)).toHaveAttribute(`data-rc-deformed-y${i + 1}`, String(node.coordinates[1] + 1000 * response.displacements_m_rad[1]))
        }
      }
      for (const node of row.nodes) {
        await expect(review.locator('[data-rc-corotational-table="external_loads_kn_knm"] tbody tr')
          .filter({ has: reopened.page.getByRole('rowheader', { name: node.node_id, exact: true }) }).locator('td')).toHaveText(node.external_loads_kn_knm.map(String))
      }
      for (const id of ['N3', 'N4']) expect(row.nodes.find((node: any) => node.node_id === id).external_loads_kn_knm[1]).toBe(-1)
    }
    const member = review.getByRole('button', { name: 'Select member beam-top', exact: true })
    await member.focus(); await member.press('Enter')
    await expect(review.locator('[data-rc-corotational-selected-member]')).toContainText('beam-top: N3 → N4')
    await review.getByRole('button', { name: 'Open stored RC details', exact: true }).click()
    const details = review.locator('[data-rc-corotational-details="verified"]')
    await expect(details).toBeVisible({ timeout: 30000 })
    const detailDownload = reopened.page.waitForEvent('download')
    await details.getByRole('button', { name: 'Download corotational detail report', exact: true }).click()
    const detailPath = join(workspace, 'portal-detail-report.json')
    await (await detailDownload).saveAs(detailPath)
    const detail = JSON.parse(await readFile(detailPath, 'utf8'))
    expect(detail.nodal_report_hash).toBe(report.report_hash)
    expect(detail.responses.map((row: any) => row.checkpoint_hash)).toEqual(report.responses.map((row: any) => row.checkpoint_hash))
    for (const row of detail.responses) {
      await review.getByLabel('Accepted state to inspect', { exact: true }).selectOption(String(row.state_index))
      for (const response of row.members) {
        await details.getByLabel('Detail member', { exact: true }).selectOption(response.member_id)
        await expect(details.locator('[data-rc-detail-member]')).toContainText(`Accepted state ${row.state_index} · ${response.member_id}:`)
        for (const frame of ['global', 'local']) {
          for (const [end, offset] of [['i', 0], ['j', 3]] as const) {
            await expect(details.locator(`[data-rc-detail-force="${frame}:${end}"] td`)).toHaveText([
              `${end}: ${response[`node_${end}`]}`, ...response[`end_force_${frame}_kn_knm`].slice(offset, offset + 3).map(String),
            ])
          }
        }
        const section = response.sections.at(-1)
        await details.getByLabel('Detail integration point', { exact: true }).selectOption(String(section.integration_point_index))
        await expect(details.locator('[data-rc-detail-section-table] tbody td')).toHaveText([
          section.axial_strain, section.curvature_z_per_m, section.axial_force_kn, section.moment_z_kn_m,
        ].map(String))
        const fiber = section.fibers.at(-1)
        await details.getByLabel('Detail fiber index', { exact: true }).fill(String(fiber.fiber_index))
        await expect(details.locator('[data-rc-detail-fiber-table] tbody td')).toHaveText([
          fiber.fiber_index, fiber.material_kind, fiber.strain, fiber.stress_mpa,
        ].map(String))
      }
    }
    await expect(details.getByRole('group', { name: 'Section moment–curvature history', exact: true })).toBeVisible()
    await expect(details.getByRole('group', { name: 'Fiber stress–strain history', exact: true })).toBeVisible()
    await testInfo.attach('portal-detail-report', { path: detailPath, contentType: 'application/json' })
    expect(reopened.posts).toHaveLength(1)
    expect(reopened.posts[0]).toMatch(/\/rc-control$/)
    const receipt = await driver.command('verify_reads')
    expect(receipt.http_numerical_calls).toBe(0)
    const screenshot = testInfo.outputPath('actual-portal-result.png')
    await review.screenshot({ path: screenshot })
    await testInfo.attach('actual-portal-result', { path: screenshot, contentType: 'image/png' })
    evidence.completed = true
    Object.assign(evidence, { first, held, killed, resumed, finished, receipt, authoredSubmissions: view.posts.filter(url => !url.endsWith('/rc-control')).length, reopenedSubmissions: reopened.posts.filter(url => !url.endsWith('/rc-control')).length, controlRequests: view.posts.concat(reopened.posts).filter(url => url.endsWith('/rc-control')).length, checkpointHash: first.checkpoint_hash, reportHash: report.report_hash, detailReportHash: detail.report_hash })
  } finally {
    try {
      try { for (const context of contexts) await context.close() } finally { await driver.close() }
    } finally {
      const output = testInfo.outputPath('portal-lifecycle.json')
      await writeFile(output, JSON.stringify({ ...evidence, stdout: driver.stdout, stderr: driver.stderr, workspace }, null, 2))
      await testInfo.attach('portal-lifecycle', { path: output, contentType: 'application/json' })
    }
    if (evidence.completed) expect(driver.child.exitCode).toBe(0)
    if (evidence.completed && driver.child.exitCode === 0) await rm(workspace, { recursive: true, force: true })
  }
})
