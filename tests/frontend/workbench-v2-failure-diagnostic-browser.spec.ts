import { expect, test } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import { waitForJobService } from './jobServiceBrowserWait'

const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-memory-only-token' }
test.describe('nonlinear failure diagnostic browser', () => {
  let server: ChildProcess, origin: string, job: WorkbenchJobView
  let mutants: Record<string, string>
  test.beforeAll(async () => {
    server = spawn('python3', ['-B', 'tests/frontend/job_transport_server.py', '--nonlinear-failure'], {
      env: { ...process.env, PYTHONPATH: resolve('src'), OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
    })
    const ready = await new Promise<{ origin: string; failed_job: WorkbenchJobView; mutants: Record<string, string> }>((done, reject) => {
      let output = '', error = ''
      const timer = setTimeout(() => reject(new Error(`failure API startup timed out: ${error}`)), 30000)
      server.once('error', e => { clearTimeout(timer); reject(e) })
      server.once('exit', code => { clearTimeout(timer); reject(new Error(`failure API exited ${code}: ${error}`)) })
      server.stderr!.on('data', chunk => { error = (error + String(chunk)).slice(-2000) })
      server.stdout!.on('data', chunk => {
        output += String(chunk)
        if (!output.includes('\n')) return
        clearTimeout(timer)
        try { done(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('invalid failure API ready message')) }
      })
    })
    origin = ready.origin; job = ready.failed_job; mutants = ready.mutants
  })
  test.afterAll(async () => {
    if (!server || server.exitCode !== null || server.signalCode !== null) return
    const closed = new Promise<void>(done => server.once('exit', () => done()))
    server.kill('SIGTERM'); await closed
  })
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path: `/v1/jobs/${job.job_id}`, credentials })
  })

  for (const width of [1280, 390]) {
    test(`actual partial failure and exact original downloads at width ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(`${origin}/#/workbench-v2`)
      await waitForJobService(page)
      await expect(page.locator('[data-failure-diagnostic]')).toHaveAttribute('data-failure-diagnostic', 'verified')
      await expect(page.locator('[data-failure-attempted]')).toHaveText('3')
      await expect(page.locator('[data-failure-committed]')).toHaveText('2')
      await expect(page.locator('[data-failure-history-rows]')).toHaveText('18')
      await expect(page.locator('[data-failure-step]')).toHaveCount(3)
      await expect(page.locator('[data-failure-rollback]')).toContainText('Rollback: exact')
      await expect(page.locator('[data-job-convergence]')).toHaveAttribute('data-job-convergence', 'unavailable')
      await expect(page.locator('[data-job-result-ir]')).toHaveAttribute('data-job-result-ir', 'unavailable')
      const panel = page.locator('[data-failure-diagnostic]')
      expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true)
      await panel.screenshot({ path: testInfo.outputPath(`failure-${width}.png`) })
      const response = await page.request.get(`${origin}/v1/jobs/${job.job_id}/failure-diagnostics/1`, {
        headers: { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` },
      })
      expect(response.status()).toBe(200)
      const original = await response.body()
      for (const [label, bytes] of [
        ['Download original diagnostic', original],
        ['Download original failed result', Buffer.from(JSON.parse(original.toString()).result_bytes_base64, 'base64')],
      ] as const) {
        const downloadPromise = page.waitForEvent('download')
        await page.getByRole('button', { name: label, exact: true }).click()
        const download = await downloadPromise
        expect(await readFile((await download.path())!)).toEqual(bytes)
      }
    })
  }
  for (const kind of ['wrong_total', 'float_count']) {
    test(`rejects coherently rehashed ${kind}`, async ({ page }) => {
      await page.route(`**/failure-diagnostics/1`, route => route.fulfill({ status: 200, contentType: 'application/json', body: mutants[kind] }))
      await page.goto(`${origin}/#/workbench-v2`)
      await waitForJobService(page, 'invalid')
      await expect(page.locator('[data-failure-diagnostic]')).toHaveCount(0)
    })
  }
  for (const kind of ['unknown_work', 'rollback_false']) {
    test(`preserves unfavorable ${kind} without result authority`, async ({ page }) => {
      await page.route(`**/failure-diagnostics/1`, route => route.fulfill({ status: 200, contentType: 'application/json', body: mutants[kind] }))
      await page.goto(`${origin}/#/workbench-v2`)
      await waitForJobService(page)
      await expect(page.locator('[data-failure-diagnostic]')).toHaveCount(1)
      if (kind === 'unknown_work') {
        await expect(page.locator('[data-failure-attempted]')).toHaveText('unavailable')
        await expect(page.locator('[data-failure-work-unavailable]')).toContainText('does not mean zero work')
      } else await expect(page.locator('[data-failure-rollback]')).toContainText('not exact')
      await expect(page.locator('[data-job-convergence]')).toHaveAttribute('data-job-convergence', 'unavailable')
    })
  }
  test('rejects a stale attempt binding', async ({ page }) => {
    await page.route('**/failure-diagnostics/1', async route => {
      const response = await route.fetch()
      const body = await response.json(); body.binding.attempt = 2
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page, 'invalid')
    await expect(page.locator('[data-failure-diagnostic]')).toHaveCount(0)
  })
  test('rejects a same-length request mutation before showing diagnostics', async ({ page }) => {
    await page.route(`**/v1/jobs/${job.job_id}/request`, async route => {
      const response = await route.fetch()
      const original = await response.text()
      const changed = original.replace('actual-planar-failure', 'forged-planar-failure')
      expect(changed).not.toBe(original)
      expect(Buffer.byteLength(changed)).toBe(Buffer.byteLength(original))
      await route.fulfill({ status: 200, contentType: 'application/json', body: changed })
    })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page, 'invalid')
    await expect(page.locator('[data-failure-diagnostic]')).toHaveCount(0)
  })
})
