import { expect, test, type Page } from '@playwright/test'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
}

test.describe('Workbench v2 — live provider guardrails', () => {
  test('rejects a live case response with a non-JSON content type', async ({ page }) => {
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: '<!doctype html><title>fallback</title>',
      })
    })

    await open(page)
    await page.locator('[data-wb2-provider="live"]').click()
    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /unexpected live case content-type: text\/html/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })

  test('rejects an oversized live case payload before parsing', async ({ page }) => {
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({ oversized: 'x'.repeat(270_000) }),
      })
    })

    await open(page)
    await page.locator('[data-wb2-provider="live"]').click()
    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /live case payload too large:/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })
})
