import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { gunzipSync } from 'node:zlib'
import type { Page } from '@playwright/test'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const directory = 'tests/frontend/fixtures/rc-pin-roller-original/'
const roles = ['model', 'request', 'result', 'checkpoint', 'verification'] as const
const names = { model: 'model.json', request: 'request.json', result: 'result.json', checkpoint: 'checkpoint.json', verification: 'verify-report.json' }
function originalBytes(fixture: string, role: typeof roles[number]) {
  return role === 'result' ? gunzipSync(readFileSync(fixture + 'result.json.gz')) : readFileSync(fixture + names[role])
}
async function upload(page: Page, fixture = directory) {
  const panel = page.locator('[data-rc-pin-roller-original]')
  for (const role of roles) {
    const name = names[role]
    await panel.locator(`[data-rc-pin-roller-file="${role}"]`).setInputFiles({ name, mimeType: 'application/json', buffer: originalBytes(fixture, role) })
  }
  await panel.getByRole('button', { name: 'Review original bundle' }).click()
  return panel
}

for (const width of [1440, 390]) {
  test(`v4 original browser review shows exact rows, unknown run cost and original downloads at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const writes: string[] = []
    page.on('request', request => { if (request.method() !== 'GET') writes.push(request.url()) })
    await page.goto(`${baseUrl}/#/rc-pin-roller-original`)
    const panel = await upload(page)
    await expect(panel).toHaveAttribute('data-rc-pin-roller-original', 'verified')
    await expect(panel.locator('[data-rc-pin-roller-authority]')).toContainText('unsigned local consistency')
    await expect(panel.locator('[data-rc-pin-roller-cost]')).toContainText('unknown')
    await expect(panel.locator('[data-rc-pin-roller-reactions] tbody tr')).toHaveCount(3)
    await expect(panel.locator('[data-rc-pin-roller-reactions] tbody')).toContainText('N2')
    await expect(panel.locator('[data-rc-pin-roller-reactions] tbody')).toContainText('N6')
    const bounds = await panel.boundingBox()
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
    for (const [role, label] of [
      ['model', 'original neutral model'], ['request', 'original v4 request'],
      ['result', 'original API result'], ['checkpoint', 'original checkpoint'],
      ['verification', 'cli verify report'],
    ] as const) {
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: `Download ${label}` }).click()
      const download = await pending
      expect(download.suggestedFilename()).toBe(names[role])
      expect((await readFile((await download.path())!)).equals(originalBytes(directory, role))).toBe(true)
    }
    expect(writes).toEqual([])
  })
}

test('v4 original browser rejects run report and clears previous review', async ({ page }) => {
  await page.goto(`${baseUrl}/#/rc-pin-roller-original`)
  const panel = await upload(page)
  await expect(panel).toHaveAttribute('data-rc-pin-roller-original', 'verified')
  await panel.locator('[data-rc-pin-roller-file="verification"]').setInputFiles({ name: 'run-report.json', mimeType: 'application/json', buffer: readFileSync(directory + 'run-report.json') })
  await expect(panel.locator('[data-rc-pin-roller-review]')).toHaveCount(0)
  await panel.getByRole('button', { name: 'Review original bundle' }).click()
  await expect(panel).toHaveAttribute('data-rc-pin-roller-original', 'invalid')
  await expect(panel.getByRole('alert')).toContainText('Original bundle unavailable')
})

test('v4 original browser exposes the separate accepted preload response', async ({ page }) => {
  await page.goto(`${baseUrl}/#/rc-pin-roller-original`)
  const panel = await upload(page, 'tests/frontend/fixtures/rc-pin-roller-preload/')
  await expect(panel).toHaveAttribute('data-rc-pin-roller-original', 'verified')
  await expect(panel.getByRole('combobox', { name: 'Response to inspect' })).toHaveValue('-1')
  await expect(panel.locator('[data-rc-pin-roller-reactions] tbody tr')).toHaveCount(3)
  await expect(panel).toContainText('and the preload')
  await panel.getByRole('combobox', { name: 'Response to inspect' }).selectOption('0')
  await expect(panel.locator('[data-rc-pin-roller-reactions] tbody tr')).toHaveCount(3)
})
