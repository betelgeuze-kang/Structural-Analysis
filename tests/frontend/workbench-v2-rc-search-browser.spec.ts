import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
const root = 'tests/frontend/fixtures/rc-control-search/'
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
async function setup(page: Page, directory = root, tamper = false) {
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/rc-search/result.json', jobAuthorization: () => ({ tenantId: 'synthetic-search', bearerToken: 'synthetic-test-only' }) } })
  await page.route('**/rc-search/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-test-only')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('synthetic-search')
    const path = new URL(route.request().url()).pathname.replace('/rc-search/', '')
    const bytes = readFileSync(directory + path)
    await route.fulfill({ contentType: 'application/json', body: tamper && path === 'pool/middle.json' ? Buffer.concat([bytes, Buffer.from(' ')]) : bytes })
  })
}
async function ready(page: Page, status = 'verified') {
  const panel = page.locator('[data-rc-search]')
  await expect(panel).toHaveAttribute('data-rc-search', /^(verified|invalid)$/, { timeout: 60000 })
  expect(await panel.getAttribute('data-rc-search'), (await panel.innerText()).slice(0, 1000)).toBe(status)
  return panel
}
for (const width of [1440, 390]) {
  test.describe(`RC search browser ${width}`, () => {
    test.use({ viewport: { width, height: 1000 } })
    test('reviews strategies, original designs, full costs and exact downloads', async ({ page }) => {
      await setup(page); await page.goto(`${baseUrl}/#/workbench-v2`)
      const panel = await ready(page)
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(3)
      const reviewButton = await panel.getByRole('button', { name: 'Review Learned order', exact: true }).boundingBox()
      expect(reviewButton!.width).toBeGreaterThan(80)
      expect(reviewButton!.height).toBeLessThan(60)
      await expect(panel.locator('[data-rc-search-candidate]')).toHaveCount(3)
      await expect(panel.locator('[data-rc-search-training]')).toContainText('48 core calls')
      await expect(panel.locator('[data-rc-search-candidate="middle"]')).toContainText('Not requested')
      for (const [arm, title] of [['learned_order', 'Learned order'], ['exhaustive_oracle', 'Later exhaustive check']]) {
        await panel.getByRole('button', { name: `Review ${title}`, exact: true }).click()
        await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'cheap')
        const candidate = arm === 'exhaustive_oracle' ? 'middle' : 'cheap'
        await panel.getByRole('button', { name: `Select ${candidate}`, exact: true }).click()
        const details = panel.locator(`[data-rc-design-details="${candidate}"]`)
        for (const role of ['model', 'result', 'checkpoint', 'verification']) {
          const pending = page.waitForEvent('download')
          await details.getByRole('button', { name: `Download ${candidate} ${role}`, exact: true }).click()
          expect(await readFile((await (await pending).path())!)).toEqual(readFileSync(`${root}${arm}/${candidate}/${role}.json`))
        }
      }
      for (const role of ['result', 'plan', 'policy', 'historical-training']) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download search ${role}`, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(readFileSync(`${root}${role}.json`))
      }
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
      await panel.screenshot({ path: `test-results/rc-control-search-${width}.png` })
    })
    test('shows unavailable whole-pool evaluation when the exhaustive check was not run', async ({ page }) => {
      await setup(page, 'tests/frontend/fixtures/rc-control-search-no-oracle/'); await page.goto(`${baseUrl}/#/workbench-v2`)
      const panel = await ready(page)
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(2)
      await expect(panel.getByRole('region', { name: 'RC prediction errors' })).toContainText('Unavailable')
      await expect(panel.locator('[data-rc-search-candidate="costly"]')).toContainText('Not run')
    })
  })
}
test('RC search hides every result when an unrequested candidate model is tampered', async ({ page }) => {
  await setup(page, root, true); await page.goto(`${baseUrl}/#/workbench-v2`)
  await ready(page, 'invalid')
  await expect(page.locator('[data-rc-search-arm]')).toHaveCount(0)
  await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
})
test('RC search rejects changed downloads and retires the shared worker on navigation', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => {
    const Native = window.Worker
    Object.assign(window, { __searchRetired: 0 })
    window.Worker = class extends Native { terminate() { (window as any).__searchRetired++; super.terminate() } }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`); const panel = await ready(page)
  await page.route('**/rc-search/price_order/cheap/result.json', route => route.fulfill({ contentType: 'application/json', body: '{}' }))
  await panel.getByRole('button', { name: 'Download cheap result', exact: true }).click()
  await expect(page.locator('[data-rc-search]')).toHaveAttribute('data-rc-search', 'invalid', { timeout: 10000 })
  await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
  expect(await page.evaluate(() => (window as any).__searchRetired)).toBe(1)
  await page.evaluate(() => { location.hash = '#/legacy' })
  expect(await page.evaluate(() => (window as any).__searchRetired)).toBe(1)
})
test('RC search rejects foreign origins before requesting credentials', async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, { __searchAuthCalls: 0 })
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: 'https://invalid.example/result.json', jobAuthorization: () => { (window as any).__searchAuthCalls++; return { tenantId: 'synthetic', bearerToken: 'synthetic' } } }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`); await ready(page, 'invalid')
  expect(await page.evaluate(() => (window as any).__searchAuthCalls)).toBe(0)
})
