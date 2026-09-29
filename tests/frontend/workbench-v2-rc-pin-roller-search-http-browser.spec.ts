import { expect, test, type Page } from '@playwright/test'
import { spawn, execFileSync, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const archive = resolve('tests/frontend/fixtures/rc-pin-roller-search-v4.tar.gz')
const archiveSha256 = '639131b23eef4bd9f2f3b921eabadfa154bb4567783cc011cac725fb119d9eab'
const reportHash = 'sha256:8bc487770f2ee052e2e6e709f51ac9a901acc4ae9e9202ac4e89e07dc7b5ca01'
const path = '/v1/rc-search/regression/result.json'
const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-search-memory-token' }

test.describe('frozen six-model pin/roller search over real HTTP', () => {
  let server: ChildProcess | null = null, origin = '', study = '', receipt = ''

  test.beforeAll(async () => {
    expect(createHash('sha256').update(readFileSync(archive)).digest('hex')).toBe(archiveSha256)
    mkdirSync(resolve('test-results'), { recursive: true })
    study = mkdtempSync(resolve('test-results/rc-pin-roller-search-v4-'))
    receipt = resolve(`test-results/rc-pin-roller-search-http-${process.pid}.json`)
    execFileSync('tar', ['-xzf', archive, '-C', study])
    expect(JSON.parse(readFileSync(resolve(study, 'result.json'), 'utf8')).report_hash).toBe(reportHash)
    server = spawn('python3', ['-B', 'tests/frontend/rc_search_transport_server.py', '--receipt', receipt,
      '--study-directory', study, '--expected-report-hash', reportHash], {
      env: { ...process.env, PYTHONPATH: resolve('src') }, stdio: ['ignore', 'pipe', 'pipe'],
    })
    const ready = await new Promise<{ origin: string; artifact_count: number; snapshot_bytes: number }>((done, reject) => {
      let output = '', error = ''
      const timer = setTimeout(() => { server?.kill('SIGTERM'); reject(new Error(`RC artifact API startup timed out: ${error}`)) }, 15000)
      server!.once('error', failure => { clearTimeout(timer); reject(failure) })
      server!.once('exit', code => { clearTimeout(timer); reject(new Error(`RC artifact API exited ${code}: ${error}`)) })
      server!.stderr!.on('data', chunk => { error = (error + String(chunk)).slice(-2000) })
      server!.stdout!.on('data', chunk => {
        output += String(chunk)
        if (!output.includes('\n')) return
        clearTimeout(timer)
        try { done(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('RC artifact API ready record is invalid')) }
      })
    })
    origin = ready.origin
    expect(ready.artifact_count).toBe(109)
    expect(ready.snapshot_bytes).toBe(12133108)
  })

  test.afterAll(async () => {
    if (server && server.exitCode === null && server.signalCode === null) {
      const closed = new Promise<void>(done => server!.once('exit', () => done()))
      server.kill('SIGTERM'); await closed
    }
    if (receipt) {
      const record = JSON.parse(await readFile(receipt, 'utf8'))
      expect(record.report_hash).toBe(reportHash)
      expect(record.new_solver_calls).toBe(0)
      expect(record.new_fits).toBe(0)
      for (const request of record.requests.filter((r: any) => r.status === 200)) {
        const original = readFileSync(resolve(study, request.path.replace('/v1/rc-search/regression/', '')))
        expect(request.bytes).toBe(original.byteLength)
        expect(request.sha256).toBe(createHash('sha256').update(original).digest('hex'))
      }
    }
    if (study) rmSync(study, { recursive: true, force: true })
  })

  async function configure(page: Page) {
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: path, jobAuthorization: () => credentials }
    }, { path, credentials })
  }

  for (const width of [1440, 390]) {
    test(`shows the verified cheaper false negative and original records at ${width}px`, async ({ page }) => {
      // Exercise a cold production shell and 109 original HTTP artifacts.
      // A progressing search may exceed the default one-minute idle bound.
      test.setTimeout(240000)
      await page.setViewportSize({ width, height: 900 })
      await configure(page)
      await page.goto(`${origin}/#/workbench-v2`)
      const panel = page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 210000 })
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(3)
      await expect(panel.locator('[data-rc-search-candidate]')).toHaveCount(5)
      await expect(panel.locator('[data-rc-search-arm="price_order"]')).toContainText('None')
      await expect(panel.locator('[data-rc-search-arm="learned_order"]')).toContainText('w50')
      await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('w46')
      await expect(panel.locator('[data-rc-search-cost="learned_order"]')).toContainText('4.56')
      await expect(panel.locator('[data-rc-search-cheaper-false-negative="learned_order"]')).toHaveText('1: w46')
      await expect(panel.locator('[data-rc-search-cheaper-false-negative="price_order"]')).toHaveText('Not applicable')
      const w46 = panel.locator('[data-rc-search-candidate="w46"]')
      await expect(w46).toContainText('Predicted limit failure')
      await expect(w46).toContainText('Not requested')
      await expect(w46).toContainText('Verified limits pass')
      await expect(panel.locator('[data-rc-search-authority]')).toContainText('confirmed monetary savings')
      await panel.getByRole('button', { name: 'Review Later exhaustive check', exact: true }).click()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'w46')
      for (const [button, original] of [
        ['Download search result', 'result.json'],
        ['Download w46 result', 'exhaustive_oracle/w46/result.json'],
      ]) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: button, exact: true }).click()
        expect((await readFile((await (await pending).path())!)).equals(readFileSync(resolve(study, original)))).toBe(true)
      }
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
    })
  }
})
