import { expect, test, type Page } from '@playwright/test'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

async function openLive(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
  await page.locator('[data-wb2-provider="live"]').click()
}

test.describe('Workbench v2 — live evidence provider guardrails', () => {
  test('rejects a non-JSON response before schema validation', async ({ page }) => {
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: '<!doctype html><title>fallback</title>',
      })
    })

    await openLive(page)

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /unexpected live case content-type: text\/html/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })

  test('rejects an oversized response before JSON parsing', async ({ page }) => {
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({ oversized: 'x'.repeat(270_000) }),
      })
    })

    await openLive(page)

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /live case payload too large:/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })

  test('reports malformed JSON without exposing a partial case', async ({ page }) => {
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"schemaVersion":',
      })
    })

    await openLive(page)

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /invalid live case JSON:/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })
})
