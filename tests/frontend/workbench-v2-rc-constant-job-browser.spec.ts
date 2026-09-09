import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { waitForJobService } from './jobServiceBrowserWait'

const directory = 'tests/frontend/fixtures/rc-fiber-constant-durable-job/'
const bytes = Object.fromEntries(['job', 'request', 'checkpoint', 'result', 'evidence'].map((role) => [role, readFileSync(`${directory}${role}.json`)]))
const job = JSON.parse(bytes.job.toString()), payload = JSON.parse(bytes.result.toString())
const history = [payload.api_result.preload_response, ...payload.api_result.response_history]
const path = `/v1/jobs/${job.job_id}`
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
async function setup(page: Page): Promise<void> {
  await page.addInitScript((path) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      jobStatusUrl: path,
      jobAuthorization: () => ({ tenantId: 'stored-constant-review', bearerToken: 'local-review-only' }),
    }
  }, path)
  await page.route('**/v1/jobs/**', async (route) => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer local-review-only')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('stored-constant-review')
    const role = new URL(route.request().url()).pathname === path ? 'job' : route.request().url().split('/').pop()!
    await route.fulfill({ contentType: 'application/json', body: bytes[role] })
  })
}
for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`constant RC browser ${viewport.width}`, () => {
    test.use({ viewport })
    test('reviews preload, every lateral target, material history and exact downloads', async ({ page }, info) => {
      await setup(page)
      await page.goto(`${baseUrl}/#/workbench-v2`)
      await waitForJobService(page)
      const panel = page.locator('[data-rc-review="verified"]')
      await expect(panel).toBeVisible()
      await expect(panel.locator('[data-rc-core]')).toHaveText('18')
      await expect(panel.locator('[data-rc-reserved]')).toHaveText('6')
      await expect(panel.locator('[data-rc-table="constant-loads"] tbody tr')).toContainText('N2-60000')
      await expect(panel.locator('[data-rc-preload-note]')).toContainText('Preload is included')
      const selector = panel.getByRole('combobox', { name: 'RC target to inspect', exact: true })
      await expect(selector).toHaveValue('3')
      await expect(selector.locator('option')).toHaveCount(4)
      for (let index = 0; index < 4; index += 1) {
        await selector.selectOption(String(index))
        await expect(panel.locator('[data-rc-selected]')).toContainText(index === 0 ? 'Preload · constant loads' : `Step ${index + 1} ·`)
        const row = history[index]
        await expect(panel.locator('[data-rc-table="fibers"] tbody tr')).toHaveCount(row.fiber_results.length)
        await expect(panel.locator('[data-rc-table="reactions"] tbody tr').first().locator('td').nth(1)).toHaveText(String(row.support_reactions[0].value_si))
        await expect(panel.locator('[data-rc-table="nodes"] tbody tr').nth(1).locator('td').first()).toHaveText(String(row.node_displacements[1].UX_m))
      }
      const material = panel.getByRole('combobox', { name: 'RC material point history', exact: true })
      for (const kind of ['concrete', 'steel']) {
        const point = history[0].fiber_results.find((f: any) => f.material_kind === kind)
        await material.selectOption(JSON.stringify([point.member_id, point.integration_point_index, point.fiber_index]))
        const table = panel.locator('[data-rc-table="material-history"]')
        await expect(table.locator('tbody tr')).toHaveCount(4)
        for (let i = 0; i < 4; i += 1) {
          const expected = history[i].fiber_results.find((f: any) => f.member_id === point.member_id && f.integration_point_index === point.integration_point_index && f.fiber_index === point.fiber_index)
          await expect(table.locator('tbody tr').nth(i)).toContainText(expected.material_state.state_hash)
        }
      }
      await selector.selectOption('0')
      await expect(panel.locator('[data-rc-selected]')).toContainText('Preload · constant loads')
      await selector.scrollIntoViewIfNeeded()
      await page.screenshot({ path: info.outputPath(`constant-preload-${viewport.width}.png`) })
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1)
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
