import { expect, test, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'

// Software integration tests replay retained, actual backend snapshot bytes.
// HTTP responses below are controlled test routes; they grant no new execution
// authenticity, physical validation or service deployment evidence.
const origin = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:5128'
const retained = process.env.RC_COROTATIONAL_REPORT_FIXTURE_DIR
const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`

for (const profile of ['v6', 'v7'] as const) test.describe(`Corotational report workflow ${profile}`, () => {
  test.skip(!retained, 'Use retained actual snapshots; this suite never executes the numerical fixture.')
  let snapshot: any, requestBytes: Buffer, reportBytes: Buffer
  test.beforeAll(() => {
    snapshot = JSON.parse(readFileSync(path.join(retained!, `${profile}-review-snapshot.json`), 'utf8'))
    requestBytes = Buffer.from(snapshot.artifacts.request, 'base64')
    reportBytes = Buffer.from(snapshot.report.body_base64, 'base64')
  })
  async function setup(page: Page, options: { mode?: 'submit' | 'failed' | 'poll'; body?: Buffer; headers?: Record<string, string>; reportStatus?: number; maximum?: number; standalone?: boolean } = {}) {
    const calls: Array<{ method: string; path: string; headers: Record<string, string>; body: string | null }> = []
    let resumed = false, statusReads = 0
    const failed = { ...snapshot.job, status: 'failed', can_resume: true, result: null, evidence: null, error_code: 'worker_failure' }
    const checkpointed = { ...failed, status: 'checkpointed', error_code: null }
    await page.addInitScript(({ tenant, maximum, standalone, jobId }) => {
      const host = window as any
      host.__coroTenant = tenant
      host.__STRUCTURAL_WORKBENCH_CONFIG__ = {
        ...(standalone ? { jobStatusUrl: `/v1/jobs/${jobId}` } : { rcJobCollectionUrl: '/v1/jobs' }),
        ...(maximum === undefined ? {} : { rcReviewResultMaxBytes: maximum }),
        jobAuthorization: async () => ({ tenantId: host.__coroTenant, bearerToken: 'test-token' }),
      }
    }, { tenant: snapshot.tenant_id, maximum: options.maximum, standalone: options.standalone, jobId: snapshot.job.job_id })
    await page.route('**/v1/jobs**', async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname
      calls.push({ method: request.method(), path: pathname, headers: request.headers(), body: request.postData() })
      const json = (value: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) })
      if (request.headers()['x-structural-tenant'] !== snapshot.tenant_id) return route.fulfill({ status: 401 })
      if (pathname === '/v1/jobs' && request.method() === 'POST') return json(snapshot.job)
      if (pathname === `/v1/jobs/${snapshot.job.job_id}/resume`) { resumed = true; return json(snapshot.job) }
      if (pathname.endsWith('/rc-corotational-report')) return route.fulfill({
        status: options.reportStatus ?? 200, headers: options.headers ?? snapshot.report.headers, body: options.body ?? reportBytes,
      })
      if (pathname.endsWith('/request')) return route.fulfill({ status: 200, contentType: 'application/json', body: requestBytes })
      if (pathname === `/v1/jobs/${snapshot.job.job_id}`) {
        statusReads++
        if (options.mode === 'failed' && !resumed) return json(failed)
        if (options.mode === 'poll' && statusReads === 1) return json(checkpointed)
        return json(snapshot.job)
      }
      return route.fulfill({ status: 404 })
    })
    const saved = options.mode === 'submit' ? '' : `?rcJob=${snapshot.job.job_id}`
    await page.goto(`${origin}/${saved}#/workbench-v2`)
    return calls
  }
  async function ready(page: Page) {
    await expect(page.locator('[data-rc-corotational-review]')).toHaveAttribute('data-rc-corotational-review', 'report_verified')
  }

  test('opens exact nodal values with distinct target/state/attempt budgets in a dedicated worker', async ({ page }, testInfo) => {
    const workers: string[] = []; page.on('worker', worker => workers.push(worker.url()))
    const calls = await setup(page)
    await ready(page)
    expect(workers.some(url => url.includes('rcCorotationalReportReview.worker'))).toBe(true)
    await expect(page.locator('[data-rc-corotational-targets]')).toHaveText('3/3')
    await expect(page.locator('[data-rc-corotational-attempts]')).toHaveText('3/255')
    await expect(page.locator('[data-rc-corotational-states]')).toContainText('4 · preload')
    await expect(page.locator('[data-rc-corotational-budget]')).toHaveText('5/6')
    await expect(page.locator('[data-rc-corotational-unknown]')).toContainText('Known counts are subtotals')
    await expect(page.locator('[data-rc-corotational-authority]')).toContainText('Original result and evidence custody remains with the service')
    const report = JSON.parse(reportBytes.toString('utf8')), selected = report.responses[3]
    for (const kind of ['displacements_m_rad', 'external_loads_kn_knm', 'reactions_kn_knm']) {
      const table = page.locator(`[data-rc-corotational-table="${kind}"]`)
      for (const node of selected.nodes) await expect(table.locator('tbody tr').filter({ has: page.getByRole('rowheader', { name: node.node_id, exact: true }) }).locator('td'))
        .toHaveText(node[kind].map(String))
    }
    await expect(page.getByRole('columnheader', { name: 'RZ (rad)', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'RZ (rad)', exact: true })).toHaveCSS('text-transform', 'none')
    await expect(page.getByRole('columnheader', { name: 'MZ (kN*m)', exact: true }).first()).toHaveCSS('text-transform', 'none')
    await expect(page.getByRole('columnheader', { name: 'MZ (kN*m)', exact: true })).toHaveCount(2)
    // Geometry comes from the original request and translations from the
    // authenticated response. Plot coordinates retain stored order and units.
    const shape = page.locator('[data-rc-deformed-shape]')
    await expect(shape).toBeVisible()
    const checkShape = async (response: any, scale: number) => {
      await expect(shape.locator('[data-rc-member]')).toHaveCount(snapshot.request.model.elements.length)
      for (const member of snapshot.request.model.elements) {
        const element = shape.locator(`[data-rc-member="${member.id}"]`)
        for (const [index, nodeId] of member.nodes.entries()) {
          const node = snapshot.request.model.nodes.find((value: any) => value.id === nodeId)
          const displacement = response.nodes.find((value: any) => value.node_id === nodeId).displacements_m_rad
          for (const [axis, component] of [['x', 0], ['y', 1]] as const) {
            const coordinate = node.coordinates[component]
            await expect(element).toHaveAttribute(`data-rc-${axis}${index + 1}`, String(coordinate))
            await expect(element).toHaveAttribute(`data-rc-deformed-${axis}${index + 1}`, String(coordinate + scale * displacement[component]))
          }
        }
      }
    }
    await checkShape(selected, 1)
    await page.getByLabel('Deformation scale', { exact: true }).fill('1000')
    await checkShape(selected, 1000)
    // The two-member L frame exercises keyboard member selection and the
    // corresponding table highlights without changing the response itself.
    const chosenMember = snapshot.request.model.elements[1]
    const memberButton = shape.getByRole('button', { name: `Select member ${chosenMember.id}`, exact: true })
    await memberButton.focus(); await memberButton.press('Enter')
    await expect(page.getByLabel('Result member', { exact: true })).toHaveValue(chosenMember.id)
    await expect(page.locator('[data-rc-corotational-selected-member]')).toContainText(`Member ${chosenMember.id}`)
    await expect(page.locator('[data-rc-corotational-table="displacements_m_rad"] tr[data-rc-selected-node="true"] th'))
      .toHaveText(chosenMember.nodes)
    const history = page.locator('[data-rc-history-plot="Accepted control history"]')
    await expect(history.locator('[data-rc-history-point]')).toHaveCount(report.responses.length)
    expect(await history.locator('[data-rc-history-point]').evaluateAll(elements => elements.map(element => ({
      state: Number(element.getAttribute('data-rc-history-point')), x: Number(element.getAttribute('data-rc-x')), y: Number(element.getAttribute('data-rc-y')),
    })))).toEqual(report.responses.map((response: any) => ({ state: response.state_index, x: response.control_displacement_m, y: response.load_factor })))
    const firstPoint = history.locator('[data-rc-history-point="0"]')
    await firstPoint.focus(); await firstPoint.press('Enter')
    await expect(page.locator('[data-rc-corotational-selected]')).toContainText('Accepted state 0 · preload')
    await expect(page.getByLabel('Accepted state to inspect', { exact: true })).toHaveValue('0')
    await checkShape(report.responses[0], 1000)
    for (const node of report.responses[0].nodes) await expect(page.locator('[data-rc-corotational-table="displacements_m_rad"] tbody tr')
      .filter({ has: page.getByRole('rowheader', { name: node.node_id, exact: true }) }).locator('td')).toHaveText(node.displacements_m_rad.map(String))
    await expect(page.getByRole('button', { name: 'Previous accepted state', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: 'Next accepted state', exact: true }).click()
    await expect(page.getByLabel('Accepted state to inspect', { exact: true })).toHaveValue('1')
    await checkShape(report.responses[1], 1000)
    await page.getByRole('button', { name: 'Previous accepted state', exact: true }).click()
    await expect(page.getByLabel('Accepted state to inspect', { exact: true })).toHaveValue('0')
    await expect(page.locator('[data-rc-corotational-member-unavailable]')).toContainText('unavailable in this saved nodal report')
    await expect(page.locator('[data-rc-history-plot="Section moment–curvature history"]')).toHaveCount(0)
    await expect(page.locator('[data-rc-history-plot="Fiber stress–strain history"]')).toHaveCount(0)
    expect(calls.filter(call => call.method === 'POST')).toEqual([])
    const explorerScreenshot = testInfo.outputPath(`${profile}-saved-result-explorer.png`)
    await page.locator('[data-rc-corotational-review]').screenshot({ path: explorerScreenshot })
    await testInfo.attach(`${profile}-saved-result-explorer.png`, { path: explorerScreenshot, contentType: 'image/png' })
    const reportCall = calls.find(call => call.path.endsWith('/rc-corotational-report'))!
    expect(reportCall.headers.authorization).toBe('Bearer test-token')
    expect(reportCall.headers['x-structural-expected-request-hash']).toBe(snapshot.job.request.content_hash)
    expect(reportCall.headers['x-structural-expected-result-hash']).toBe(snapshot.job.result.content_hash)
    expect(reportCall.headers['x-structural-expected-evidence-hash']).toBe(snapshot.job.evidence.content_hash)
    expect(calls.some(call => /\/(?:result|evidence|checkpoint)$/.test(call.path))).toBe(false)
    await expect(page.locator('[data-rc-quantity-report]')).toHaveCount(0)
    await page.setViewportSize({ width: 390, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  })

  test('downloads exact raw bytes and only reopens the authenticated report', async ({ page }) => {
    await setup(page); await ready(page)
    const downloadEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download corotational nodal report', exact: true }).click()
    const download = await downloadEvent, output = await download.path()
    expect(digest(readFileSync(output!))).toBe(snapshot.report.headers['x-structural-report-sha256'])
    const input = page.getByLabel('Reopen corotational report JSON', { exact: true })
    await input.setInputFiles({ name: 'different.json', mimeType: 'application/json', buffer: Buffer.from('{}') })
    await expect(page.locator('[data-rc-corotational-file-status]')).toContainText('saved review is retained')
    await ready(page)
    await input.setInputFiles({ name: download.suggestedFilename(), mimeType: 'application/json', buffer: reportBytes })
    await expect(page.locator('[data-rc-corotational-file-status]')).toContainText('Reopened exact report bytes match')
    const link = await page.locator('[data-rc-corotational-project-link]').getAttribute('href')
    expect(new URL(link!).searchParams.get('rcReport')).toBe(snapshot.report.headers['x-structural-report-id'])
    await page.goto(link!); await ready(page)
    const mismatch = new URL(link!); mismatch.searchParams.set('rcReport', `rcc_${'0'.repeat(64)}`)
    await page.goto(mismatch.href)
    await expect(page.locator('[data-rc-corotational-review]')).toHaveAttribute('data-rc-corotational-review', 'invalid')
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('submits retained typed input and binds the normalized saved request', async ({ page }) => {
    const calls = await setup(page, { mode: 'submit' })
    await page.getByText('Submit a new RC input', { exact: true }).click()
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill(Buffer.from(snapshot.submitted_request_base64, 'base64').toString('utf8'))
    await expect(page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await ready(page)
    const submission = calls.find(call => call.method === 'POST' && call.path === '/v1/jobs')!
    expect(JSON.parse(submission.body!)).toEqual(snapshot.request)
    expect(submission.headers['idempotency-key']).toMatch(/^rc-ui-/)
  })

  test('compares a captured scenario through the real nodal reviewer worker and exports bound quantities', async ({ page }) => {
    const workers: string[] = []; page.on('worker', worker => workers.push(worker.url()))
    const calls = await setup(page, { mode: 'submit' })
    await page.getByText('Submit a new RC input', { exact: true }).click()
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill(Buffer.from(snapshot.submitted_request_base64, 'base64').toString('utf8'))
    const panel = page.locator('[data-rc-scenario-comparison]')
    await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(0)
    await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
    await expect(panel.locator('[data-scenario-id]')).toContainText('succeeded')
    expect(workers.some(url => url.includes('rcCorotationalReportReview.worker'))).toBe(true)
    await panel.getByText('Original bindings and recorded work', { exact: true }).click()
    await expect(panel).toContainText('authenticated_saved_nodal_report')
    await expect(panel).toContainText('Unavailable in the saved nodal report')
    await expect(panel).toContainText(snapshot.request.source_revision)
    await expect(panel).toContainText(snapshot.job.request.content_hash)
    await expect(panel.getByRole('img', { name: 'Accepted control displacement versus load factor by scenario' })).toBeVisible()

    const downloadEvent = page.waitForEvent('download')
    await panel.getByRole('button', { name: 'Export scenario JSON', exact: true }).click()
    const download = await downloadEvent, output = await download.path()
    const exported = JSON.parse(readFileSync(output!, 'utf8'))
    expect(exported.scenarios).toHaveLength(1)
    const selected = exported.scenarios[0], summary = selected.summary
    expect(selected.status).toBe('succeeded')
    expect(summary.reviewKind).toBe('authenticated_saved_nodal_report')
    expect(summary.sourceRevision).toBe(snapshot.request.source_revision)
    expect(summary.bindings).toEqual({
      jobId: snapshot.job.job_id, requestHash: snapshot.job.request.content_hash,
      resultHash: snapshot.job.result.content_hash, evidenceHash: snapshot.job.evidence.content_hash,
      checkpointHash: snapshot.job.checkpoint?.content_hash ?? null, revision: snapshot.job.revision,
      terminalEventHash: snapshot.job.terminal_event_hash,
    })
    const report = JSON.parse(reportBytes.toString('utf8')), final = report.responses[report.responses.length - 1]
    expect(summary.targetsM).toEqual(report.declarations.targets_m)
    expect(summary.targetIndex).toBe(report.declarations.targets_m.length - 1)
    expect(summary.targetM).toBe(report.declarations.targets_m[summary.targetIndex])
    expect(summary.curve).toEqual(report.responses.filter((row: any) => row.phase === 'control').map((row: any) => ({
      state: row.state_index, displacementM: row.control_displacement_m, loadFactor: row.load_factor,
    })))
    for (const node of final.nodes) for (let index = 0; index < 3; index++) {
      const component = ['UX', 'UY', 'RZ'][index]
      expect(summary.values.find((row: any) => row.kind === 'reaction' && row.entity === node.node_id && row.component === component))
        .toMatchObject({ unit: index === 2 ? 'N*m' : 'N', value: node.reactions_kn_knm[index] * 1000 })
      expect(summary.values.find((row: any) => row.kind === 'displacement' && row.entity === node.node_id && row.component === component))
        .toMatchObject({ unit: index === 2 ? 'rad' : 'm', value: node.displacements_m_rad[index] })
    }
    expect(summary.memberForcesAvailable).toBe(false)
    expect(summary.values.some((row: any) => row.kind === 'member_force')).toBe(false)
    expect(summary.unknownWork).toBe(report.execution.unknown_execution_work)
    if (summary.unknownWork) expect(summary.recordedPhaseWallSeconds).toBeNull()
    expect(exported.baselineJobId).toBe(snapshot.job.job_id)
    expect(exported.comparisons).toHaveLength(1)
    expect(exported.comparisons[0]).toMatchObject({ jobId: snapshot.job.job_id, compatible: true })
    expect(exported.comparisons[0].rows).toHaveLength(summary.values.length)
    expect(exported.comparisons[0].rows.every((row: any) => row.delta === 0 && row.baseline === row.variant)).toBe(true)
    const submissions = calls.filter(call => call.method === 'POST')
    expect(submissions).toHaveLength(1)
    expect(submissions[0].path).toBe('/v1/jobs')
    expect(submissions[0].headers['idempotency-key']).toMatch(/^rc-scenario-/)
    expect(JSON.parse(submissions[0].body!)).toEqual(snapshot.request)
    expect(calls.some(call => /\/(?:result|evidence|checkpoint)$/.test(call.path))).toBe(false)
  })

  test('polls checkpointed state and resumes failed state only on explicit retry', async ({ page }) => {
    const calls = await setup(page, { mode: 'failed' })
    await expect(page.getByRole('button', { name: 'Resume RC from saved checkpoint', exact: true })).toBeEnabled()
    expect(calls.some(call => call.path.endsWith('/resume'))).toBe(false)
    await page.getByRole('button', { name: 'Resume RC from saved checkpoint', exact: true }).click()
    await ready(page)
    const resume = calls.find(call => call.path.endsWith('/resume'))!
    expect(JSON.parse(resume.body!)).toEqual({ expected_request_hash: snapshot.job.request.content_hash, expected_checkpoint_hash: snapshot.job.checkpoint.content_hash })
    await page.close()
  })

  test('keeps polling an in-progress checkpoint before loading its terminal report', async ({ page }) => {
    const calls = await setup(page, { mode: 'poll' }); await ready(page)
    expect(calls.filter(call => call.path === `/v1/jobs/${snapshot.job.job_id}`).length).toBeGreaterThanOrEqual(2)
  })

  test('rejects altered raw report bytes', async ({ page }) => {
    await setup(page, { body: Buffer.from(reportBytes.toString('utf8').replace('durable-rc-corotational-report.v1', 'durable-rc-corotational-report.v2')) })
    await expect(page.locator('[data-rc-workflow-error]')).toBeVisible()
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('enforces the configured report body size limit', async ({ page }) => {
    await setup(page, { maximum: reportBytes.length - 1 })
    await expect(page.locator('[data-rc-workflow-error]')).toContainText('review size limit')
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('rejects mismatched report hash headers', async ({ page }) => {
    await setup(page, { headers: { ...snapshot.report.headers, 'x-structural-report-id': `rcc_${'0'.repeat(64)}` } })
    await expect(page.locator('[data-rc-workflow-error]')).toBeVisible()
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('removes nodal values when authorization scope changes before a review action', async ({ page }) => {
    await setup(page); await ready(page)
    await page.evaluate(() => { (window as any).__coroTenant = 'other' })
    await page.getByLabel('Accepted state to inspect', { exact: true }).selectOption('0')
    await expect(page.locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('rejects an unavailable authenticated report response', async ({ page }) => {
    await setup(page, { reportStatus: 401 })
    await expect(page.locator('[data-rc-workflow-error]')).toContainText('Authentication is unavailable')
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
  })

  test('shows the report for standalone authenticated job configuration', async ({ page }) => {
    await setup(page, { standalone: true }); await ready(page)
    await expect(page.locator('[data-rc-workflow="project"]')).toHaveCount(0)
  })
})
