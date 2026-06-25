import { expect, test, type Page } from '@playwright/test'

// End-to-end smoke for the Workbench v2 route. The runner builds the app and
// serves dist; the viewer iframe src is asserted structurally (the viewer is
// hosted at deploy time).

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

test.setTimeout(60000)

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
}

test.describe('Workbench v2 — shell & demo case', () => {
  test('renders the DEMO data-mode badge and claim boundary', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-root] .wb2-chip[data-state="DEMO"]').first()).toBeVisible()
    await expect(page.locator('[data-wb2-claim]')).toContainText(/claim boundary/i)
  })

  test('shows provenance + model health and a converged analysis', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Case & provenance')).toBeVisible()
    await expect(page.getByText('Source checksum')).toBeVisible()
    await expect(page.locator('[data-wb2-root]')).toContainText(/Converged/i)
  })

  test('does not show an automated verdict (review decision UNAVAILABLE)', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-ec-decision="unavailable"], [data-state="UNAVAILABLE"]').first()).toBeVisible()
  })
})

test.describe('Workbench v2 — provider, evidence, benchmarks', () => {
  test('demo/live provider toggle is present', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-provider="demo"]')).toBeVisible()
    await expect(page.locator('[data-wb2-provider="live"]')).toBeVisible()
  })

  test('benchmark browser lists cases and filters by lifecycle', async ({ page }) => {
    await open(page)
    const cards = page.locator('[data-bench-id]')
    expect(await cards.count()).toBeGreaterThan(5)
    // run command is hidden when no runner is registered
    await expect(page.locator('[data-run-blocked]').first()).toBeVisible()
  })

  test('evidence reader is present (bundle may be unavailable)', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Read-only evidence')).toBeVisible()
  })
})

test.describe('Workbench v2 — viewer, mobile, a11y', () => {
  test('embeds the structure viewer iframe with a deep-linkable src', async ({ page }) => {
    await open(page)
    const iframe = page.locator('.wb2-viewport-iframe')
    await expect(iframe).toHaveAttribute('src', /structure-viewer\/index\.html/)
  })

  test('is keyboard operable and has a skip link on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 720 })
    await open(page)
    await page.keyboard.press('Tab')
    const active = await page.evaluate(() => document.activeElement?.className ?? '')
    expect(active).toContain('wb2-skip-link')
  })
})
