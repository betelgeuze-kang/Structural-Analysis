import { expect, test, type Page } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-search-memory-token' }
const path = '/v1/rc-search/regression/result.json'
const fixture = 'tests/frontend/fixtures/rc-control-search/'

test.describe('RC search real HTTP', () => {
  let server: ChildProcess, origin: string, receipt: string
  test.beforeAll(async () => {
    receipt = resolve(`test-results/rc-search-real-http-${process.pid}.json`)
    server = spawn('python3', ['-B', 'tests/frontend/rc_search_transport_server.py', '--receipt', receipt], {
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
    origin = ready.origin; expect(ready.artifact_count).toBe(75)
  })
  test.afterAll(async () => {
    if (server && server.exitCode === null && server.signalCode === null) {
      const closed = new Promise<void>(done => server.once('exit', () => done()))
      server.kill('SIGTERM'); await closed
    }
    const record = JSON.parse(await readFile(receipt, 'utf8'))
    expect(record.new_solver_calls).toBe(0); expect(record.new_fits).toBe(0)
    for (const request of record.requests.filter((r: any) => r.status === 200)) {
      const bytes = readFileSync(fixture + request.path.replace('/v1/rc-search/regression/', ''))
      expect(request.bytes).toBe(bytes.byteLength)
      expect(request.sha256).toBe(createHash('sha256').update(bytes).digest('hex'))
    }
  })
  async function configure(page: Page, auth = credentials) {
    await page.addInitScript(({ path, auth }) => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: path, jobAuthorization: () => auth } }, { path, auth })
  }
  for (const width of [1440, 390]) {
    test(`serves verified search and exact original downloads at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 }); await configure(page)
      await page.goto(`${origin}/#/workbench-v2`)
      const panel = page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(3)
      await expect(panel.locator('[data-rc-search-candidate]')).toHaveCount(3)
      await panel.getByRole('button', { name: 'Review Learned order', exact: true }).click()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'cheap')
      for (const role of ['model', 'result', 'checkpoint', 'verification']) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download cheap ${role}`, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(readFileSync(`${fixture}learned_order/cheap/${role}.json`))
      }
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: 'Download search result', exact: true }).click()
      expect(await readFile((await (await pending).path())!)).toEqual(readFileSync(fixture + 'result.json'))
      const bounds = await panel.boundingBox(); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
      await panel.screenshot({ path: `test-results/rc-search-real-http-${width}.png` })
    })
  }
  test('enforces real tenant isolation, immutable reads and method restrictions', async ({ request }) => {
    const headers = { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` }
    expect((await request.get(origin + path)).status()).toBe(401)
    expect((await request.get(origin + path, { headers: { 'X-Structural-Tenant': 'other-tenant', Authorization: 'Bearer synthetic-other-search-token' } })).status()).toBe(404)
    expect((await request.get(origin + path, { headers: { ...headers, Authorization: 'Bearer wrong-token' } })).status()).toBe(401)
    expect((await request.post(origin + path, { headers, data: '{}' })).status()).toBe(405)
    expect((await request.get(origin + '/v1/rc-search/regression/provenance.json', { headers })).status()).toBe(404)
    const response = await request.get(origin + path, { headers })
    expect(response.status()).toBe(200); expect(await response.body()).toEqual(readFileSync(fixture + 'result.json'))
    expect(response.headers()['cache-control']).toBe('no-store')
  })
  test('hides selection after an actual credential rejection', async ({ page }) => {
    await configure(page, { ...credentials, bearerToken: 'wrong-token' }); await page.goto(`${origin}/#/workbench-v2`)
    await expect(page.locator('[data-rc-search]')).toHaveAttribute('data-rc-search', 'invalid', { timeout: 60000 })
    await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
  })
})
