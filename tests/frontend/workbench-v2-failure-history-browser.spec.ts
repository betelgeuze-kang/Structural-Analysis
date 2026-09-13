import { expect, test } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { waitForJobService } from './jobServiceBrowserWait'
import { validateFailureDiagnostic } from '../../src/workbench-v2/model/failureDiagnostic'
import { validateWorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

let server: ChildProcess, origin: string, job: any
const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-memory-only-token' }
test.beforeAll(async () => {
  server = spawn('python3', ['-B', 'tests/frontend/job_transport_server.py', '--nonlinear-failure', '--failure-history'], {
    env: { ...process.env, PYTHONPATH: resolve('src'), OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
  })
  const ready: any = await new Promise((done, reject) => {
    let output = '', error = ''
    const timer = setTimeout(() => { server.kill(); reject(new Error(error || 'history startup timeout')) }, 30000)
    server.on('error', reject)
    server.stderr!.on('data', b => { error = (error + b).slice(-2000) })
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`history server ${code}: ${error}`)) })
    server.stdout!.on('data', b => { output += b; if (output.includes('\n')) { clearTimeout(timer); done(JSON.parse(output.split('\n')[0])) } })
  })
  origin = ready.origin; job = ready.failed_job
  expect(job.attempt).toBe(2)
})
test.afterAll(async () => {
  if (server && server.exitCode === null && server.signalCode === null) {
    const closed = new Promise<void>(done => server.once('exit', () => done()))
    server.kill(); await closed
  }
})
test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ path, credentials }) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
  }, { path: `/v1/jobs/${job.job_id}`, credentials })
})
for (const width of [1280, 390]) test(`reads actual earlier failure without changing current attempt at ${width}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 900 })
  await page.goto(`${origin}/#/workbench-v2`); await waitForJobService(page)
  const history = page.locator('[data-failure-history]')
  await expect(history).toHaveAttribute('data-failure-history', 'idle')
  await history.getByRole('button', { name: 'Review previous attempt' }).click()
  await expect(history).toHaveAttribute('data-failure-history', 'verified')
  await expect(history.getByRole('heading', { name: 'Failed attempt 1', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Failed attempt 2', exact: true })).toBeVisible()
  await expect(page.locator('[data-job-service]')).toHaveAttribute('data-job-status', 'failed')
  await expect(page.locator('[data-job-result-ir]')).toHaveAttribute('data-job-result-ir', 'unavailable')
  const response = await page.request.get(`${origin}/v1/jobs/${job.job_id}/failure-diagnostics/1`, { headers: { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` } })
  expect(response.status()).toBe(200)
  const bytes = await response.body(), pending = page.waitForEvent('download')
  await history.getByRole('button', { name: 'Download original diagnostic', exact: true }).click()
  expect(await readFile((await (await pending).path())!)).toEqual(bytes)
  await history.screenshot({ path: info.outputPath(`history-${width}.png`) })
  await history.getByLabel('Previous attempt').fill('2')
  await expect(history.getByRole('button', { name: 'Review previous attempt' })).toBeDisabled()
  await expect(history.locator('[data-failure-diagnostic]')).toHaveCount(0)
})
for (const kind of ['missing', 'wrong_attempt']) test(`historical ${kind} leaves current review intact`, async ({ page }) => {
  await page.route('**/failure-diagnostics/1', async route => {
    if (kind === 'missing') return route.fulfill({ status: 404, body: '{}' })
    const response = await route.fetch(), body = await response.json(); body.binding.attempt = 2
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto(`${origin}/#/workbench-v2`); await waitForJobService(page)
  const history = page.locator('[data-failure-history]')
  await history.getByRole('button', { name: 'Review previous attempt' }).click()
  await expect(history).toHaveAttribute('data-failure-history', kind === 'missing' ? 'missing' : 'invalid')
  await expect(history.locator('[data-failure-diagnostic]')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Failed attempt 2', exact: true })).toBeVisible()
})

// These two tests vary job-view metadata only. They validate the consumer boundary,
// not an actually successful retry or a newly generated restart checkpoint.
for (const state of ['succeeded', 'changed_checkpoint'] as const) {
  test(`historical consumer contract for synthetic ${state} view`, async ({ request }) => {
    const headers = { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` }
    const diagnostic = await request.get(`${origin}/v1/jobs/${job.job_id}/failure-diagnostics/1`, { headers })
    const sourceRequest = await request.get(`${origin}/v1/jobs/${job.job_id}/request`, { headers })
    expect(diagnostic.status()).toBe(200)
    expect(sourceRequest.status()).toBe(200)
    const bytes = await diagnostic.body(), requestBytes = await sourceRequest.body()
    const view = structuredClone(job)
    if (state === 'succeeded') {
      view.status = 'succeeded'
      view.progress.completed_steps = view.progress.total_steps
      view.can_resume = false
      view.error_code = null
      view.result = { ...view.request, role: 'result' }
      view.evidence = { ...view.request, role: 'evidence' }
    } else {
      view.checkpoint = { ...view.request, role: 'checkpoint' }
      view.can_resume = true
    }
    const validated = validateWorkbenchJobView(view)
    expect(validated.errors).toEqual([])
    expect(validated.ok).toBe(true)
    const before = JSON.stringify(view)
    if (state === 'succeeded') {
      const historical = await validateFailureDiagnostic(bytes, requestBytes, validated.value!, 1)
      expect(historical.attempt).toBe(1)
      expect(Buffer.from(historical.diagnosticBytes).equals(bytes)).toBe(true)
      // Success never authorizes reading a failure as the current accepted result.
      await expect(validateFailureDiagnostic(bytes, requestBytes, validated.value!)).rejects.toThrow('nonlinear_failure_diagnostic_invalid')
    } else {
      await expect(validateFailureDiagnostic(bytes, requestBytes, validated.value!, 1)).rejects.toThrow('nonlinear_failure_diagnostic_invalid')
    }
    expect(JSON.stringify(view)).toBe(before)
  })
}
