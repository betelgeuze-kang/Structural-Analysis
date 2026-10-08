import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { waitForJobService } from './jobServiceBrowserWait'

const directory = 'tests/frontend/fixtures/rc-pin-roller-durable-job/'
const bytes = Object.fromEntries(
  ['job', 'checkpointed-job', 'request', 'checkpoint', 'result', 'evidence']
    .map(role => [role, readFileSync(`${directory}${role}.json`)]),
)
const job = JSON.parse(bytes.job.toString())
const path = `/v1/jobs/${job.job_id}`
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

async function setup(page: Page, checkpointed = false): Promise<void> {
  await page.addInitScript(statusUrl => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      jobStatusUrl: statusUrl,
      jobAuthorization: () => ({ tenantId: 'synthetic-pin-roller-review', bearerToken: 'local-review-only' }),
    }
  }, path)
  await page.route('**/v1/jobs/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer local-review-only')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('synthetic-pin-roller-review')
    const role = new URL(route.request().url()).pathname === path ? checkpointed ? 'checkpointed-job' : 'job'
      : route.request().url().split('/').pop()!
    await route.fulfill({ contentType: 'application/json', body: bytes[role] })
  })
}

test('stored v4 pin/roller result shows two accepted steps and exact saved downloads', async ({ page }) => {
  await setup(page)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForJobService(page)
  const panel = page.locator('[data-rc-review="verified"]')
  await expect(panel).toBeVisible()
  await expect(panel.locator('[data-rc-pin-roller-profile]')).toContainText('pin N2 (UX/UY), roller N6 (UY)')
  await expect(panel.locator('[data-rc-authority]')).toContainText('does not rerun the solver')
  const selector = panel.getByRole('combobox', { name: 'RC target to inspect', exact: true })
  await expect(selector.locator('option')).toHaveCount(2)
  for (const index of [0, 1]) {
    await selector.selectOption(String(index))
    await expect(panel.locator('[data-rc-selected]')).toContainText(`Step ${index + 1} ·`)
    const reactions = panel.locator('[data-rc-table="reactions"] tbody tr')
    await expect(reactions).toHaveCount(3)
    await expect(reactions.nth(0)).toContainText('N2')
    await expect(reactions.nth(0)).toContainText('UX')
    await expect(reactions.nth(1)).toContainText('UY')
    await expect(reactions.nth(2)).toContainText('N6')
    await expect(reactions.nth(2)).toContainText('UY')
  }
  for (const role of ['checkpoint', 'result']) {
    const promise = page.waitForEvent('download')
    await panel.getByRole('button', { name: role === 'checkpoint'
      ? 'Download RC saved job checkpoint' : 'Download RC result', exact: true }).click()
    const download = await promise
    expect(await readFile((await download.path())!)).toEqual(bytes[role])
  }
})

test('checkpointed v4 job exposes saved continuation without claiming a result', async ({ page }) => {
  await setup(page, true)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = await waitForJobService(page)
  await expect(panel).toHaveAttribute('data-job-status', 'checkpointed')
  await expect(panel.locator('[data-job-resume]')).toHaveText('Checkpoint saved; worker continuation available')
  await expect(panel).toContainText('1 of 2 step(s) durably committed')
  await expect(page.locator('[data-rc-review]')).toHaveCount(0)
})
