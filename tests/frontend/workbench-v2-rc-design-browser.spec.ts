import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'
const directory = 'tests/frontend/fixtures/rc-control-design/'
const report = JSON.parse(readFileSync(`${directory}comparison.json`, 'utf8'))
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
async function setup(page: Page, changed = false, reportName = 'comparison', artifactDelayMs = 0) {
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlDesignUrl: '/rc-study/comparison.json', jobAuthorization: () => ({ tenantId: 'synthetic-study', bearerToken: 'synthetic-only' }) }
  })
  await page.route('**/rc-study/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-only')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('synthetic-study')
    const relative = new URL(route.request().url()).pathname.replace('/rc-study/', '')
    if (relative === 'baseline/result.json' && artifactDelayMs) await delay(artifactDelayMs)
    const bytes = readFileSync(directory + (relative === 'comparison.json' ? reportName + '.json' : relative))
    await route.fulfill({ contentType: 'application/json', body: changed && relative === 'wider/result.json' ? Buffer.concat([bytes, Buffer.from(' ')]) : bytes })
  })
}
// Wait only at the asynchronous original-artifact validation boundary. A wrong
// terminal state fails immediately; integrity and rendering limits stay strict.
async function waitForRcDesign(page: Page, expected: 'verified' | 'invalid' = 'verified') {
  return test.step(`RC study finishes validation as ${expected}`, async () => {
    const panel = page.locator('[data-rc-design]')
    await expect(panel).toHaveAttribute('data-rc-design', /^(verified|invalid)$/, { timeout: 60000 })
    const status = await panel.getAttribute('data-rc-design')
    expect(status, `RC study terminal state ${status}: ${(await panel.innerText()).slice(0, 1000)}`).toBe(expected)
    await expect(panel).toBeVisible()
    return panel
  })
}
for (const width of [1440, 390]) {
  test.describe(`RC study browser ${width}`, () => {
    test.use({ viewport: { width, height: 1000 } })
    test('selects verified alternatives and exports exact original identities', async ({ page }) => {
      await setup(page)
      await page.goto(`${baseUrl}/#/workbench-v2`)
      const panel = await waitForRcDesign(page)
      await expect(panel.locator('[data-rc-design-candidate]')).toHaveCount(3)
      await expect(panel.getByRole('button', { name: 'Select invalid', exact: true })).toBeDisabled()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'baseline')
      await panel.getByRole('button', { name: 'Select wider', exact: true }).click()
      await expect(panel.locator('[data-rc-design-selected]')).toContainText('width 0.5 m')
      const details = panel.locator('[data-rc-design-details="wider"]')
      await expect(details.locator('[data-rc-design-metric="maximum_translation_m"] td').nth(1)).toHaveText(String(report.rows[1].performance.maximum_translation_m))
      await expect(details.locator('[data-rc-design-performance-delta="maximum_translation_m"]')).toHaveText(String(report.rows[1].performance.maximum_translation_m - report.rows[0].performance.maximum_translation_m))
      for (const role of ['model', 'result', 'checkpoint', 'verification']) {
        const pending = page.waitForEvent('download')
        await details.getByRole('button', { name: `Download wider ${role}`, exact: true }).click()
        const download = await pending
        expect(await readFile((await download.path())!)).toEqual(readFileSync(`${directory}wider/${role}.json`))
      }
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: 'Download original RC comparison' }).click()
      expect(await readFile((await (await pending).path())!)).toEqual(readFileSync(`${directory}comparison.json`))
      const header = panel.getByRole('region', { name: 'RC design alternatives', exact: true }).locator('th').nth(4)
      expect((await header.boundingBox())!.width).toBeGreaterThanOrEqual(120)
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
    })
  })
}
test('RC study browser hides selection and all values when one alternative is tampered', async ({ page }) => {
  await setup(page, true)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForRcDesign(page, 'invalid')
  await expect(page.locator('[data-rc-design-candidate]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Download .*RC comparison/ })).toHaveCount(0)
})
test('RC study browser retires its worker on navigation and hides values after worker failure', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => {
    const workers: Worker[] = [], NativeWorker = window.Worker
    let retired = 0
    Object.assign(window, { __studyWorkers: { workers, retired: () => retired } })
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) { super(url, options); workers.push(this) }
      terminate() { retired++; super.terminate() }
    }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForRcDesign(page)
  await page.evaluate(() => { location.hash = '#/legacy' })
  await expect.poll(() => page.evaluate(() => (window as any).__studyWorkers.retired())).toBe(1)
  await page.evaluate(() => { location.hash = '#/workbench-v2' })
  await waitForRcDesign(page)
  await page.evaluate(() => { (window as any).__studyWorkers.workers.at(-1).dispatchEvent(new ErrorEvent('error')) })
  await expect(page.locator('[data-rc-design="invalid"]')).toBeVisible()
  await expect(page.locator('[data-rc-design-candidate]')).toHaveCount(0)
})

for (const name of ['unpriced', 'strict']) {
  test(`RC study browser blocks every candidate selection when ${name}`, async ({ page }) => {
    await setup(page, false, name)
    await page.goto(`${baseUrl}/#/workbench-v2`)
    const panel = await waitForRcDesign(page)
    await expect(panel.locator('[data-rc-design-selected]')).toHaveCount(0)
    for (const candidate of ['baseline', 'wider', 'invalid']) await expect(panel.getByRole('button', { name: `Select ${candidate}`, exact: true })).toBeDisabled()
  })
}
test('RC study browser rejects changed downloads after an initially valid review', async ({ page }) => {
  await setup(page)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = await waitForRcDesign(page)
  await page.route('**/rc-study/baseline/result.json', route => route.fulfill({ contentType: 'application/json', body: '{}'}))
  await panel.getByRole('button', { name: 'Download baseline result', exact: true }).click()
  await expect(page.locator('[data-rc-design="invalid"]')).toBeVisible()
  await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
})
test('RC study browser validates the origin before invoking the credential callback', async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, { __studyAuthorizationCalls: 0 })
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlDesignUrl: 'https://invalid.example/comparison.json', jobAuthorization: () => {
      (window as any).__studyAuthorizationCalls++
      return { tenantId: 'synthetic-study', bearerToken: 'synthetic-only' }
    } }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForRcDesign(page, 'invalid')
  expect(await page.evaluate(() => (window as any).__studyAuthorizationCalls)).toBe(0)
})

for (const changed of [false, true]) {
  test(`RC study browser waits for delayed original validation with tampered=${changed}`, async ({ page }) => {
    await setup(page, changed, 'comparison', 6000)
    await page.goto(`${baseUrl}/#/workbench-v2`)
    await expect(page.locator('[data-rc-design="loading"]')).toBeVisible()
    await expect(page.locator('[data-rc-design-candidate]')).toHaveCount(0)
    const panel = await waitForRcDesign(page, changed ? 'invalid' : 'verified')
    await expect(panel.locator('[data-rc-design-candidate]')).toHaveCount(changed ? 0 : 3)
  })
}
