import { expect, test, type Page } from '@playwright/test'

// Browser smoke + DOM/interaction contract for the Evidence Console prototype.
//
// The runner (scripts/verify-evidence-console-browser-smoke.mjs) serves the
// repository root so that both the console assets (/src/evidence-console/*) and
// the read-only readiness artifact (/implementation/...) resolve.
//
// Screenshot baselines: run once with `--update-snapshots` to seed the
// baseline image, then subsequent runs assert against it.

const baseUrl = process.env.EVIDENCE_CONSOLE_BASE_URL ?? 'http://127.0.0.1:4173'
const consoleUrl = `${baseUrl}/src/evidence-console/index.html`

test.setTimeout(60000)

async function openConsole(page: Page): Promise<string[]> {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await page.goto(consoleUrl, { waitUntil: 'load', timeout: 30000 })
  // Wait for the fixture-driven case list to hydrate.
  await page.locator('[data-ec-case-id]').first().waitFor({ state: 'visible', timeout: 15000 })
  return errors
}

test.describe('Evidence Console — structure & claim boundary', () => {
  test('renders the DEMO badge and claim boundary banner', async ({ page }) => {
    const errors = await openConsole(page)
    await expect(page.locator('[data-ec-demo-badge]')).toBeVisible()
    await expect(page.locator('[data-ec-demo-badge]')).toContainText(/demo/i)
    await expect(page.locator('[data-ec-claim-boundary]')).toContainText(/claim boundary/i)
    expect(errors).toEqual([])
  })

  test('renders every fixture case in the case list', async ({ page }) => {
    await openConsole(page)
    const buttons = page.locator('[data-ec-case-id]')
    await expect(buttons).toHaveCount(4)
  })

  test('selecting a case updates the detail panel and live status', async ({ page }) => {
    await openConsole(page)
    const second = page.locator('[data-ec-case-id="demo-wallframe-002"]')
    await second.click()
    await expect(page.locator('[data-ec-detail] h2')).toContainText('Wall-frame core')
    await expect(page.locator('[data-ec-status]')).toContainText('Wall-frame core')
  })

  test('a case with no verdict never shows PASS', async ({ page }) => {
    await openConsole(page)
    await page.locator('[data-ec-case-id="demo-truss-004"]').click()
    const decision = page.locator('[data-ec-detail] [data-ec-decision]').first()
    await expect(decision).toHaveAttribute('data-ec-decision', 'unavailable')
    await expect(decision).not.toHaveText(/pass/i)
    // The detail panel exposes explicit "evidence unavailable" markers.
    await expect(page.locator('[data-ec-detail] [data-ec-unavailable]').first()).toBeVisible()
  })
})

test.describe('Evidence Console — readiness integration', () => {
  test('shows the blocked launch gate and the source commit', async ({ page }) => {
    await openConsole(page)
    await expect(page.locator('[data-ec-gate]')).toHaveAttribute('data-ec-gate', 'BLOCKED', { timeout: 15000 })
    await expect(page.locator('[data-ec-gate]')).toContainText(/blocked/i)
    const commit = page.locator('[data-ec-source-commit]')
    await expect(commit).toBeVisible()
    await expect(commit).toContainText('b883c03e')
  })
})

test.describe('Evidence Console — keyboard navigation', () => {
  test('arrow keys move the active case with roving focus', async ({ page }) => {
    await openConsole(page)
    const first = page.locator('[data-ec-case-id="demo-frame-001"]')
    const second = page.locator('[data-ec-case-id="demo-wallframe-002"]')
    await first.focus()
    await expect(first).toHaveAttribute('aria-current', 'true')
    await page.keyboard.press('ArrowDown')
    await expect(second).toHaveAttribute('aria-current', 'true')
    await expect(second).toBeFocused()
  })
})

test.describe('Evidence Console — reproduce bundle export smoke', () => {
  test('exports a demo reproduce bundle as JSON', async ({ page }) => {
    await openConsole(page)
    await page.locator('[data-ec-case-id="demo-frame-001"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      page.locator('[data-ec-export]').click(),
    ])
    expect(download.suggestedFilename()).toMatch(/reproduce_bundle_demo-frame-001\.json/)
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    expect(payload.is_demo).toBe(true)
    expect(payload.case.id).toBe('demo-frame-001')
    expect(payload.schema_version).toBe('evidence-console-reproduce-bundle.v1')
  })
})

test.describe('Evidence Console — visual baseline', () => {
  test('matches the screenshot baseline', async ({ page }) => {
    await openConsole(page)
    await page.locator('[data-ec-case-id="demo-frame-001"]').click()
    // Wait for readiness hydration so the baseline is deterministic.
    await expect(page.locator('[data-ec-gate]')).toBeVisible({ timeout: 15000 })
    await expect(page).toHaveScreenshot('evidence-console-frame.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.02,
      animations: 'disabled',
    })
  })
})
