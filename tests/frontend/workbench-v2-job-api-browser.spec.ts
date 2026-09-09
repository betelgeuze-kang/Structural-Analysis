import { expect, test } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import { waitForJobService } from './jobServiceBrowserWait'

const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-memory-only-token' }

test.describe('real durable API browser authentication', () => {
  let server: ChildProcess
  let origin: string
  let realJob: WorkbenchJobView
  test.beforeAll(async () => {
    server = spawn('python3', ['-B', 'tests/frontend/job_transport_server.py'], {
      env: { ...process.env, PYTHONPATH: resolve('src') }, stdio: ['ignore', 'pipe', 'pipe'],
    })
    const ready = await new Promise<{ origin: string; job: WorkbenchJobView }>((resolveReady, reject) => {
      let output = ''
      let error = ''
      const timer = setTimeout(() => reject(new Error(`test API startup timed out: ${error}`)), 15000)
      server.once('error', (failure) => { clearTimeout(timer); reject(failure) })
      server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`test API exited ${code}: ${error}`)) })
      server.stderr!.on('data', (chunk) => { error = (error + String(chunk)).slice(-2000) })
      server.stdout!.on('data', (chunk) => {
        output += String(chunk)
        if (!output.includes('\n')) return
        clearTimeout(timer)
        try { resolveReady(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('test API ready message is invalid')) }
      })
    })
    origin = ready.origin
    realJob = ready.job
  })
  test.afterAll(async () => {
    if (!server || server.exitCode !== null || server.signalCode !== null) return
    const closed = new Promise<void>((done) => server.once('exit', () => done()))
    server.kill('SIGTERM')
    await closed
  })
  test('loads the real queued RC job and reads its exact original request with tenant isolation', async ({ page }) => {
    const path = `/v1/jobs/${realJob.job_id}`
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path, credentials })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page)
    await expect(page.locator('[data-job-service]')).toHaveAttribute('data-job-status', 'queued')
    await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
    // These network reads also exercise the real WSGI original-request route.
    // The page above tests the host callback -> provider -> actual API chain.
    const headers = { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` }
    const response = await page.request.get(`${origin}${path}/request`, { headers })
    expect(response.status()).toBe(200)
    const bytes = await response.body()
    expect(bytes.byteLength).toBe(realJob.request.byte_length)
    expect(`sha256:${createHash('sha256').update(bytes).digest('hex')}`).toBe(realJob.request.content_hash)
    expect(JSON.parse(bytes.toString()).operation).toBe('bounded_rc_fiber_direct_control')
    expect((await page.request.get(`${origin}${path}/request`)).status()).toBe(401)
    expect((await page.request.get(`${origin}${path}/request`, {
      headers: { 'X-Structural-Tenant': 'other-tenant', Authorization: 'Bearer synthetic-other-tenant-token' },
    })).status()).toBe(404)
  })
  test('fails closed on an actual API credential rejection', async ({ page }) => {
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path: `/v1/jobs/${realJob.job_id}`, credentials: { ...credentials, bearerToken: 'wrong-synthetic-token' } })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page, 'error')
    await expect(page.locator('[data-job-service]')).toContainText('HTTP 401')
    await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
  })
})
