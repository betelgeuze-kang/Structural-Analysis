import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { cohortBytes } from './rc-cohort-fixture'
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
for (const width of [1440, 390]) {
  test.describe(`cohort ${width}`, () => {
    test.use({ viewport: { width, height: 1000 } })
    test('verifies paired costs, original downloads and invalidates changed child designs', async ({ page }) => {
      let tamper = false
      const errors: string[] = []
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlStrategyCohortUrl: '/rc-cohort/cohort.json', jobAuthorization: () => ({ tenantId: 'cohort-test', bearerToken: 'synthetic-only' }) } })
      await page.route('**/rc-cohort/**', async route => {
        expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-only')
        expect(await route.request().headerValue('x-structural-tenant')).toBe('cohort-test')
        const path = new URL(route.request().url()).pathname.replace('/rc-cohort/', '')
        const bytes = Buffer.from(cohortBytes(path))
        await route.fulfill({ contentType: 'application/json', body: tamper && path.endsWith('/checkpoint.json') ? Buffer.concat([bytes, Buffer.from(' ')]) : bytes })
      })
      await page.goto(`${baseUrl}/#/workbench-v2`)
      const panel = page.locator('[data-rc-cohort]')
      await expect(panel).toHaveAttribute('data-rc-cohort', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-cohort-pair]')).toHaveCount(1)
      await expect(panel.locator('[data-rc-cohort-execution]')).toHaveCount(2)
      await expect(panel.locator('[data-rc-cohort-totals]')).toContainText('Historical training counted once per artifact')
      for (const [name, path] of [['Download original cohort', 'cohort.json'], ['Download runtime 1', 'pairs/0/price_order/strategy-runtime.json'], ['Download runtime 2', 'pairs/0/learned_order/strategy-runtime.json']]) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(cohortBytes(path)))
      }
      await panel.getByRole('button', { name: 'Review execution 1', exact: true }).click()
      await expect(panel.locator('[data-rc-search]')).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'cheap')
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
      await panel.screenshot({ path: `test-results/rc-cohort-${width}.png` })
      tamper = true
      await panel.getByRole('button', { name: 'Review execution 2', exact: true }).click()
      await expect(panel).toHaveAttribute('data-rc-cohort', 'invalid', { timeout: 60000 })
      await expect(panel.locator('[data-rc-cohort-totals]')).toHaveCount(0)
      await expect(panel.locator('[data-rc-design-selected]')).toHaveCount(0)
      expect(errors).toEqual([])
    })
  })
}

test('cohort rejects a separately valid replacement report at the original URL', async ({ page }) => {
  const { rebind } = await import('./rc-search-standalone-fixture')
  const { validateRcControlSearch } = await import('../../src/workbench-v2/model/rcControlSearchSchema')
  const prefix = 'pairs/0/price_order/'
  const original = new TextDecoder().decode(cohortBytes(prefix + 'result.json'))
  const replacement = rebind(original, { online_and_optional_oracle_wall_ns: JSON.parse(original).online_and_optional_oracle_wall_ns + 1 }, 'report_hash')
  // A valid child by itself must still match the cohort's previously verified identity.
  await validateRcControlSearch(replacement, async path => cohortBytes(prefix + path))
  let swap = false
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlStrategyCohortUrl: '/rc-cohort/cohort.json' } })
  await page.route('**/rc-cohort/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/rc-cohort/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(swap && path === prefix + 'result.json' ? replacement : cohortBytes(path)) })
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = page.locator('[data-rc-cohort]')
  await expect(panel).toHaveAttribute('data-rc-cohort', 'verified', { timeout: 60000 })
  swap = true
  await panel.getByRole('button', { name: 'Review execution 1', exact: true }).click()
  await expect(panel).toHaveAttribute('data-rc-cohort', 'invalid', { timeout: 60000 })
  await expect(panel.locator('[data-rc-cohort-totals]')).toHaveCount(0)
})


test('cohort host rejects missing scripts while preserving application navigation', async ({ request }) => {
  const missing = await request.get(`${baseUrl}/src/structure-viewer/missing-controlled-cohort.js`)
  expect(missing.status()).toBe(404)
  expect((await missing.text()).trim()).not.toContain('<!DOCTYPE html>')
  const navigation = await request.get(`${baseUrl}/controlled-cohort-navigation`)
  expect(navigation.status()).toBe(200)
  expect(await navigation.text()).toContain('<!DOCTYPE html>')
})
