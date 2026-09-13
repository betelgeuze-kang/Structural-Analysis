import { expect, test, type Page } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { cohortBytes } from './rc-cohort-fixture'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-search-memory-token' }
const path = '/v1/rc-search/regression/cohort.json'

test.describe('RC cohort real HTTP', () => {
  let server: ChildProcess, origin: string, receipt: string
  test.beforeAll(async () => {
    receipt = resolve(`test-results/rc-cohort-real-http-${process.pid}.json`)
    server = spawn('python3', ['-B', 'tests/frontend/rc_search_transport_server.py', '--receipt', receipt, '--fixture', 'rc-strategy-cohort-control'], {
      env: { ...process.env, PYTHONPATH: resolve('src') }, stdio: ['ignore', 'pipe', 'pipe'],
    })
    const ready = await new Promise<{ origin: string; artifact_count: number }>((resolveReady, reject) => {
      let output = '', error = ''
      const timer = setTimeout(() => { server.kill('SIGTERM'); reject(new Error(`RC artifact API startup timed out: ${error}`)) }, 15000)
      server.once('error', failure => { clearTimeout(timer); reject(failure) })
      server.once('exit', code => { clearTimeout(timer); reject(new Error(`RC artifact API exited ${code}: ${error}`)) })
      server.stderr!.on('data', chunk => { error = (error + String(chunk)).slice(-2000) })
      server.stdout!.on('data', chunk => {
        output += String(chunk)
        if (!output.includes('\n')) return
        clearTimeout(timer)
        try { resolveReady(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('RC artifact API ready record is invalid')) }
      })
    })
    origin = ready.origin; expect(ready.artifact_count).toBeGreaterThan(40)
  })
  test.afterAll(async () => {
    if (server && server.exitCode === null && server.signalCode === null) {
      const closed = new Promise<void>(done => server.once('exit', () => done()))
      server.kill('SIGTERM'); await closed
    }
    const record = JSON.parse(await readFile(receipt, 'utf8'))
    expect(record.new_solver_calls).toBe(0); expect(record.new_fits).toBe(0)
    for (const request of record.requests.filter((r: any) => r.status === 200)) {
      const bytes = Buffer.from(cohortBytes(request.path.replace('/v1/rc-search/regression/', '')))
      expect(request.bytes).toBe(bytes.byteLength)
      expect(request.sha256).toBe(createHash('sha256').update(bytes).digest('hex'))
    }
  })
  async function configure(page: Page, auth = credentials) {
    await page.addInitScript(({ path, auth }) => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlStrategyCohortUrl: path, jobAuthorization: () => auth } }, { path, auth })
  }
  for (const width of [1440, 390]) {
    test(`serves verified search and exact original downloads at ${width}px`, async ({ page }) => {
      const errors: string[] = []
      page.on('pageerror', error => errors.push(error.message))
      await page.setViewportSize({ width, height: 1000 }); await configure(page)
      await page.goto(`${origin}/#/workbench-v2`)
      const panel = page.locator('[data-rc-cohort]')
      await expect(panel).toHaveAttribute('data-rc-cohort', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-cohort-pair]')).toHaveCount(1)
      await expect(panel.locator('[data-rc-cohort-execution]')).toHaveCount(2)
      await panel.getByRole('button', { name: 'Review execution 2', exact: true }).click()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'cheap', { timeout: 60000 })
      for (const role of ['model', 'result', 'checkpoint', 'verification']) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download cheap ${role}`, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(cohortBytes(`pairs/0/learned_order/learned_order/cheap/${role}.json`)))
      }
      for (const [name, original] of [['Download original cohort', 'cohort.json'], ['Download runtime 2', 'pairs/0/learned_order/strategy-runtime.json']]) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(cohortBytes(original)))
      }
      const bounds = await panel.boundingBox(); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
      await panel.screenshot({ path: `test-results/rc-cohort-real-http-${width}.png` })
      expect(errors).toEqual([])
    })
  }
  test('enforces real tenant isolation, immutable reads and method restrictions', async ({ request }) => {
    const missingScript = await request.get(origin + '/src/structure-viewer/missing-controlled-data.js')
    expect(missingScript.status()).toBe(404)
    expect(missingScript.headers()['content-type']).toBe('text/plain')
    const headers = { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` }
    expect((await request.get(origin + path)).status()).toBe(401)
    expect((await request.get(origin + path, { headers: { 'X-Structural-Tenant': 'other-tenant', Authorization: 'Bearer synthetic-other-search-token' } })).status()).toBe(404)
    expect((await request.get(origin + path, { headers: { ...headers, Authorization: 'Bearer wrong-token' } })).status()).toBe(401)
    expect((await request.post(origin + path, { headers, data: '{}' })).status()).toBe(405)
    expect((await request.get(origin + '/v1/rc-search/regression/provenance.json', { headers })).status()).toBe(404)
    const response = await request.get(origin + path, { headers })
    expect(response.status()).toBe(200); expect(await response.body()).toEqual(Buffer.from(cohortBytes('cohort.json')))
    expect(response.headers()['cache-control']).toBe('no-store')
  })
  test('hides selection after an actual credential rejection', async ({ page }) => {
    await configure(page, { ...credentials, bearerToken: 'wrong-token' }); await page.goto(`${origin}/#/workbench-v2`)
    await expect(page.locator('[data-rc-cohort]')).toHaveAttribute('data-rc-cohort', 'invalid', { timeout: 60000 })
    await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
  })
})
