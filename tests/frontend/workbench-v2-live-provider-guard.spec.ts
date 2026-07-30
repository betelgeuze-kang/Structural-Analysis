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

  test('never writes a draft for a commit key that the read policy rejects', async ({ page }) => {
    const sourceCommitSha = 'c'.repeat(257)
    await page.addInitScript(() => {
      const nativeSetItem = Storage.prototype.setItem
      const writeCounter = window as unknown as { __reviewDraftWrites: number }
      writeCounter.__reviewDraftWrites = 0
      Storage.prototype.setItem = function setItem(key: string, value: string): void {
        if (String(key).startsWith('wb2-review-draft:')) {
          writeCounter.__reviewDraftWrites += 1
        }
        nativeSetItem.call(this, key, value)
      }
    })
    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schemaVersion: 'workbench-case.v2',
          provenance: {
            sourcePath: 'guard/overlong-commit.workbench-case.json',
            sourceSha256: `sha256:${'b'.repeat(64)}`,
            sourceCommitSha,
            engineVersion: 'guard',
            generatedAt: '2026-07-19T00:00:00Z',
          },
          model: {
            unitSystem: 'SI',
            coordinateSystem: 'global_xyz',
            nodeCount: 0,
            elementCount: 0,
            dofCount: 0,
          },
          residualHistory: [],
        }),
      })
    })

    await openLive(page)
    const draft = page.locator('[data-wb2-review-draft]')
    const unavailable = draft.locator('[data-wb2-persistence-display="Storage unavailable"]')
    await expect(unavailable).toHaveAttribute(
      'data-wb2-persistence-error-code',
      'review_draft_source_commit_invalid',
    )

    await draft.locator('[data-wb2-decision="pass"]').click()
    const retained = draft.locator('[data-wb2-persistence-display="Previous state retained"]')
    await expect(retained).toHaveAttribute(
      'data-wb2-persistence-error-code',
      'review_draft_source_commit_invalid',
    )
    await expect(draft.locator('[data-wb2-decision="pass"]')).toHaveAttribute('aria-checked', 'false')
    expect(await page.evaluate(() => (
      window as unknown as { __reviewDraftWrites: number }
    ).__reviewDraftWrites)).toBe(0)
  })
})
