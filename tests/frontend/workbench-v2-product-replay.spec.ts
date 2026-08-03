import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { canonicalJson } from '../../src/workbench-v2/model/checksum'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`
const casePath = process.env.WORKBENCH_PRODUCT_REPLAY_CASE
const receiptPath = process.env.WORKBENCH_PRODUCT_REPLAY_RECEIPT

function sha256Canonical(value: unknown): string {
  return `sha256:${createHash('sha256').update(canonicalJson(value)).digest('hex')}`
}

test.describe('Workbench v2 — installed planar product replay', () => {
  test.skip(!casePath || !receiptPath, 'product replay artifacts are not configured')

  test('loads the installed-wheel result and exports two independently hashed envelopes', async ({ page }) => {
    const casePayload = JSON.parse(await readFile(path.resolve(casePath!), 'utf8')) as Record<string, unknown>
    const replayReceipt = JSON.parse(await readFile(path.resolve(receiptPath!), 'utf8')) as Record<string, unknown>

    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(casePayload),
      })
    })
    await page.route('**/evidence/manifest.json', async (route) => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    })

    await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('[data-wb2-provider="live"]').click()

    await expect(page.getByText('Case & provenance')).toBeVisible()
    await expect(page.locator('[data-export-truth-state]')).toContainText('planar_frame_verified_alpha.v1')
    await expect(page.locator('[data-export-truth-state]')).toContainText('converged')
    await expect(page.locator('[data-export-provenance-blocked]')).toHaveCount(0)
    await expect(page.locator('[data-wb2-export]')).toBeEnabled()

    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const download = await downloadPromise
    const downloadedPath = await download.path()
    expect(downloadedPath).not.toBeNull()
    const bundle = JSON.parse(await readFile(downloadedPath!, 'utf8')) as Record<string, unknown>

    expect(bundle.schema_version).toBe('workbench-v2-export.v3')
    const immutableCore = bundle.immutable_analysis_core
    const reviewEnvelope = bundle.review_envelope
    expect(bundle.immutable_analysis_core_sha256).toBe(sha256Canonical(immutableCore))
    expect(bundle.review_envelope_sha256).toBe(sha256Canonical(reviewEnvelope))
    expect(bundle.analysis_result_sha256).toBe(bundle.immutable_analysis_core_sha256)

    const core = immutableCore as Record<string, unknown>
    const receiptTruth = replayReceipt.result_truth as Record<string, unknown>
    expect(core.source_commit_sha).toBe(replayReceipt.source_commit_sha)
    expect((core.product_profile as Record<string, unknown>).id).toEqual({
      status: 'available',
      value: 'planar_frame_verified_alpha.v1',
    })
    expect((core.analysis as Record<string, unknown>).status).toBe('converged')
    expect(receiptTruth.status).toBe('converged')
    expect(receiptTruth.artifact_contract_pass).toBe(true)
    expect(receiptTruth.execution_contract_pass).toBe(true)
    expect(receiptTruth.numerical_result_authority).toBe(true)
    expect(receiptTruth.engineering_result_authority).toBe(true)

    const review = reviewEnvelope as Record<string, unknown>
    expect(review.data_mode).toBe('live')
    expect(review.displayed_blockers).toEqual([])
    expect(bundle.provenance_contract).toEqual({ status: 'available', issues: [] })
  })
})
