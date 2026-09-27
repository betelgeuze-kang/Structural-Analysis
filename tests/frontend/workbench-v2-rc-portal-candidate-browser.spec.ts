import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { portalCandidateBytes } from './rcPortalCandidateFixture'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

for (const width of [1440, 390]) {
  test(`two-fixed portal candidate originals are reviewable at ${width}px`, async ({ page }) => {
    test.setTimeout(60000)
    await page.setViewportSize({ width, height: 1000 })
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
        rcControlSearchUrl: '/rc-search/result.json',
        jobAuthorization: () => ({ tenantId: 'synthetic-portal', bearerToken: 'synthetic-test-only' }),
      }
    })
    await page.route('**/rc-search/**', async route => {
      expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-test-only')
      expect(await route.request().headerValue('x-structural-tenant')).toBe('synthetic-portal')
      const path = new URL(route.request().url()).pathname.replace('/rc-search/', '')
      await route.fulfill({ contentType: 'application/json', body: Buffer.from(portalCandidateBytes(path)) })
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    const panel = page.locator('[data-rc-search]')
    await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
    await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(3)
    await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('narrower-036')
    await expect(panel.locator('[data-rc-search-cost="learned_order"]')).toContainText('Yes')
    await panel.getByRole('button', { name: 'Review Learned order', exact: true }).click()
    await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'narrower-036')
    await panel.getByRole('button', { name: 'Select narrower-036', exact: true }).click()
    const details = panel.locator('[data-rc-design-details="narrower-036"]')
    for (const [label, path] of [
      ['Download narrower-036 result', 'learned_order/narrower-036/result.json'],
      ['Download narrower-036 verification', 'learned_order/narrower-036/verification.json'],
    ]) {
      const pending = page.waitForEvent('download')
      await details.getByRole('button', { name: label, exact: true }).click()
      expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(portalCandidateBytes(path)))
    }
    const pending = page.waitForEvent('download')
    await panel.getByRole('button', { name: 'Download search plan', exact: true }).click()
    expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(portalCandidateBytes('plan.json')))
    const bounds = await panel.boundingBox()
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
  })
}
