import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { waitForJobService } from './jobServiceBrowserWait'

const directory = 'tests/frontend/fixtures/rc-fiber-durable-job/'
const bytes = Object.fromEntries(['job', 'request', 'checkpoint', 'result', 'evidence'].map((role) => [role, readFileSync(`${directory}${role}.json`)]))
const job = JSON.parse(bytes.job.toString())
const payload = JSON.parse(bytes.result.toString())
const path = `/v1/jobs/${job.job_id}`
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

async function setup(page: Page, tamper = false): Promise<void> {
  await page.addInitScript((path) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      jobStatusUrl: path,
      jobAuthorization: () => ({ tenantId: 'synthetic-rc-review', bearerToken: 'synthetic-only' }),
    }
  }, path)
  await page.route('**/v1/jobs/**', async (route) => {
    const request = route.request()
    expect(await request.headerValue('authorization')).toBe('Bearer synthetic-only')
    expect(await request.headerValue('x-structural-tenant')).toBe('synthetic-rc-review')
    const role = new URL(request.url()).pathname === path ? 'job' : request.url().split('/').pop()!
    await route.fulfill({ contentType: 'application/json', body: tamper && role === 'result' ? Buffer.concat([bytes.result, Buffer.from(' ')]) : bytes[role] })
  })
}
for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`stored RC browser ${viewport.width}`, () => {
    test.use({ viewport })
    test('reviews every step and both material laws and downloads exact originals', async ({ page }) => {
      await setup(page)
      await page.goto(`${baseUrl}/#/workbench-v2`)
      await waitForJobService(page)
      const panel = page.locator('[data-rc-review="verified"]')
      await expect(panel).toBeVisible()
      await expect(panel.locator('[data-rc-core]')).toHaveText('12')
      await expect(panel.locator('[data-rc-reserved]')).toHaveText('6')
      await expect(panel.locator('[data-rc-authority]')).toContainText('does not rerun the solver')
      const selector = panel.getByRole('combobox', { name: 'RC target to inspect', exact: true })
      await expect(selector).toHaveValue('2')
      for (const index of [0, 1, 2]) {
        await selector.selectOption(String(index))
        await expect(panel.locator('[data-rc-selected]')).toContainText(`Step ${index + 1} ·`)
        const row = payload.api_result.response_history[index]
        await expect(panel.locator('[data-rc-table="fibers"] tbody tr')).toHaveCount(84)
        await expect(panel.locator('[data-rc-table="sections"] tbody tr')).toHaveCount(row.section_results.length)
        await expect(panel.locator('[data-rc-table="nodes"] tbody tr').nth(2).locator('td').nth(1)).toHaveText(String(row.node_displacements[2].UY_m))
        await expect(panel.locator('[data-rc-table="reactions"] tbody tr').nth(2)).toContainText('N*m')
      }
      const material = panel.getByRole('combobox', { name: 'RC material point history', exact: true })
      for (const kind of ['concrete', 'steel']) {
        const point = payload.api_result.response_history[0].fiber_results.find((f: any) => f.material_kind === kind)
        await material.selectOption(JSON.stringify([point.member_id, point.integration_point_index, point.fiber_index]))
        const table = panel.locator('[data-rc-table="material-history"]')
        await expect(table.locator('tbody tr')).toHaveCount(3)
        await expect(table).toContainText(kind === 'steel' ? 'accumulated_plastic_strain' : 'compressive_damage')
        for (let epoch = 0; epoch < 3; epoch += 1) {
          const expected = payload.api_result.response_history[epoch].fiber_results.find((f: any) => f.member_id === point.member_id && f.integration_point_index === point.integration_point_index && f.fiber_index === point.fiber_index)
          await expect(table.locator('tbody tr').nth(epoch)).toContainText(expected.material_state.state_hash)
        }
      }
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1)
      // A selected early step never changes the original terminal downloads.
      await selector.selectOption('0')
      for (const role of ['request', 'checkpoint', 'result', 'evidence', 'terminal']) {
        const label = role === 'checkpoint' ? 'saved job checkpoint' : role === 'terminal' ? 'terminal restart' : role
        const promise = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download RC ${label}`, exact: true }).click()
        const download = await promise
        const expected = role === 'terminal' ? Buffer.from(payload.terminal_checkpoint_artifact_base64, 'base64') : bytes[role]
        expect(await readFile((await download.path())!)).toEqual(expected)
      }
    })
  })
}
test('stored RC browser exposes no physical rows or downloads after raw tampering', async ({ page }) => {
  await setup(page, true)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForJobService(page, 'invalid')
  await expect(page.locator('[data-rc-table]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Download RC/ })).toHaveCount(0)
})
test('stored RC browser retires workers on navigation and clears values on worker failure', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => {
    const workers: Worker[] = []
    const NativeWorker = window.Worker
    let retired = 0
    Object.assign(window, { __rcWorkerState: { workers, retired: () => retired } })
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) { super(url, options); workers.push(this) }
      terminate() { retired += 1; super.terminate() }
    }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForJobService(page)
  await expect(page.locator('[data-rc-review="verified"]')).toBeVisible()
  await page.evaluate(() => { location.hash = '#/legacy' })
  await expect(page.locator('[data-rc-table]')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => (window as any).__rcWorkerState.retired())).toBe(1)
  await page.evaluate(() => { location.hash = '#/workbench-v2' })
  await waitForJobService(page)
  await expect(page.locator('[data-rc-review="verified"]')).toBeVisible()
  await page.evaluate(() => { (window as any).__rcWorkerState.workers.at(-1).dispatchEvent(new ErrorEvent('error')) })
  await expect(page.locator('[data-rc-review="invalid"]')).toBeVisible()
  await expect(page.locator('[data-rc-table]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Download RC/ })).toHaveCount(0)
})
