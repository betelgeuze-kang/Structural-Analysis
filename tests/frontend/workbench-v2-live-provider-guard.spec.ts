import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { canonicalJson } from '../../src/workbench-v2/model/checksum'
import { loadReviewDraftState, updateReviewDraftState } from '../../src/workbench-v2/model/reviewDraft'
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


test('case-bound reviewer drafts never follow another result at the same commit', async ({ page }) => {
  let nodeCount = 0
  const commit = 'd'.repeat(40)
  await page.addInitScript(({ commit }) => {
    localStorage.setItem(`wb2-review-draft:${commit}`, JSON.stringify({ decision: 'pass', comment: 'legacy', reviewer: 'old', updatedAt: null, sourceCommitSha: commit }))
  }, { commit })
  await page.route('**/evidence/workbench-case.json', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      schemaVersion: 'workbench-case.v2',
      provenance: { sourcePath: 'review/case.json', sourceSha256: `sha256:${'b'.repeat(64)}`, sourceCommitSha: commit, engineVersion: 'review-test', generatedAt: '2026-10-08T00:00:00Z' },
      model: { unitSystem: 'SI', coordinateSystem: 'global_xyz', nodeCount, elementCount: 0, dofCount: 0 }, residualHistory: [],
    }) })
  })
  await openLive(page)
  await expect(page.locator('[data-wb2-review-state="unreviewed"]')).toBeVisible()
  await page.locator('[data-wb2-review-reviewer]').fill('Case A reviewer')
  await page.locator('[data-wb2-decision="pass"]').click()
  nodeCount = 1
  await page.locator('[data-wb2-provider="demo"]').click()
  await page.locator('[data-wb2-provider="live"]').click()
  await expect(page.locator('[data-wb2-review-state="unreviewed"]')).toBeVisible()
  await expect(page.locator('[data-wb2-review-reviewer]')).toHaveValue('')
  nodeCount = 0
  await page.locator('[data-wb2-provider="demo"]').click()
  await page.locator('[data-wb2-provider="live"]').click()
  await expect(page.locator('[data-wb2-review-state="pass"]')).toBeVisible()
  await expect(page.locator('[data-wb2-review-reviewer]')).toHaveValue('Case A reviewer')
  expect(await page.evaluate(commit => JSON.parse(localStorage.getItem(`wb2-review-draft:${commit}`)!).comment, commit)).toBe('legacy')
  const downloaded = page.waitForEvent('download')
  await page.locator('[data-wb2-export]').click()
  const file = await downloaded
  const bundle = JSON.parse(await readFile((await file.path())!, 'utf8'))
  const subject = bundle.review_envelope.review_subject
  expect(subject.case_sha256).toBe(`sha256:${createHash('sha256').update(canonicalJson(subject.loaded_case)).digest('hex')}`)
  expect(bundle.reviewer_draft.caseSha256).toBe(subject.case_sha256)
  expect(subject.loaded_case.model.nodeCount).toEqual({ status: 'available', value: 0 })

})


test('case-bound storage rejects a substituted digest and retains immutable binding on edits', () => {
  const values = new Map<string, string>()
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) }, removeItem: (key: string) => { values.delete(key) } }
  const a = `sha256:${'a'.repeat(64)}`
  const b = `sha256:${'b'.repeat(64)}`
  const first = loadReviewDraftState('commit', { storage, caseSha256: a })
  const edited = updateReviewDraftState(first, { decision: 'pass', caseSha256: b }, { storage })
  expect(edited.draft.caseSha256).toBe(a)
  expect(loadReviewDraftState('commit', { storage, caseSha256: b }).draft.decision).toBe('unreviewed')
  const key = [...values.keys()][0]
  values.set(key, JSON.stringify({ ...edited.draft, caseSha256: b }))
  const rejected = loadReviewDraftState('commit', { storage, caseSha256: a })
  expect(rejected.receipt.ok).toBe(false)
  expect(rejected.draft.decision).toBe('unreviewed')
})

test('missing case hashing disables reviewer decisions and export', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(crypto, 'subtle', { value: undefined })
  })
  await page.goto(routeUrl)
  await expect(page.locator('[data-wb2-review-loading]')).toContainText('identity could not be verified')
  await expect(page.locator('[data-wb2-review-draft]')).toHaveCount(0)
  await expect(page.locator('[data-wb2-export]')).toHaveCount(0)
})
