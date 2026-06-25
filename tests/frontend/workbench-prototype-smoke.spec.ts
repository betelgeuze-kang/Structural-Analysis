import { expect, test, type Page } from '@playwright/test'

// Browser smoke for the Structural Workbench demo prototype. The runner
// (scripts/verify-workbench-prototype-browser-smoke.mjs) serves the prototype
// directory so ./demo-case.json and ./styles/* resolve.

const baseUrl = process.env.WORKBENCH_PROTOTYPE_BASE_URL ?? 'http://127.0.0.1:4273'
const pageUrl = `${baseUrl}/index.html`

test.setTimeout(60000)

async function open(page: Page): Promise<void> {
  await page.goto(pageUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb-mode-badge]').waitFor({ state: 'visible', timeout: 15000 })
}

test.describe('Workbench prototype — claim boundary & states', () => {
  test('shows a DEMO badge and claim boundary', async ({ page }) => {
    await open(page)
    const badge = page.locator('[data-wb-mode-badge]')
    await expect(badge).toHaveAttribute('data-state', 'DEMO')
    await expect(badge).toContainText('DEMO')
    await expect(page.locator('[data-wb-claim]')).toContainText(/claim boundary/i)
  })

  test('maps demo status to BLOCKED / UNAVAILABLE / MISSING (never PASS)', async ({ page }) => {
    await open(page)
    const states = await page.locator('[data-wb-status] .wb-chip').evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute('data-state')),
    )
    expect(states).toEqual(['BLOCKED', 'UNAVAILABLE', 'UNAVAILABLE', 'MISSING'])
  })

  test('the page contains no automated PASS verdict', async ({ page }) => {
    await open(page)
    const bodyText = (await page.locator('body').innerText()).toUpperCase()
    expect(bodyText).not.toMatch(/\bPASS\b/)
  })
})

test.describe('Workbench prototype — user input is inert', () => {
  test('a script-like reviewer note is rendered as text, not executed', async ({ page }) => {
    let dialogFired = false
    page.on('dialog', async (dialog) => {
      dialogFired = true
      await dialog.dismiss()
    })
    await open(page)
    const payload = '<img src=x onerror=alert(1)>'
    await page.locator('[data-wb-comment]').fill(payload)
    const preview = page.locator('[data-wb-comment-preview]')
    await expect(preview).toHaveText(payload)
    // No element was injected from the text, and no dialog ran.
    expect(await preview.locator('img').count()).toBe(0)
    expect(dialogFired).toBe(false)
  })

  test('a script-like file name is shown as text only', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb-file]').setInputFiles({
      name: '<img src=x onerror=alert(2)>.dxf',
      mimeType: 'text/plain',
      buffer: Buffer.from('demo'),
    })
    const out = page.locator('[data-wb-file-name]')
    await expect(out).toContainText('onerror')
    expect(await out.locator('img').count()).toBe(0)
  })
})

test.describe('Workbench prototype — export & accessibility', () => {
  test('exports a demo bundle as JSON', async ({ page }) => {
    await open(page)
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      page.locator('[data-wb-export]').click(),
    ])
    expect(download.suggestedFilename()).toMatch(/workbench_demo_bundle\.json/)
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    expect(payload.is_demo).toBe(true)
    expect(payload.schema_version).toBe('workbench-demo-export.v1')
  })

  test('is keyboard operable on a mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 720 })
    await open(page)
    await page.keyboard.press('Tab')
    const active = await page.evaluate(() => document.activeElement?.className ?? '')
    expect(active).toContain('wb-skip-link')
    await expect(page.locator('[data-wb-status] .wb-chip').first()).toBeVisible()
  })
})
