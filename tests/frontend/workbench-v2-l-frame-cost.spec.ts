import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { validateRcDesignStudy } from '../../src/workbench-v2/model/rcControlDesignSchema'

const packed = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/l-frame-cost-artifacts.json.gz')).toString())
const originals = new Map<string, Uint8Array>(Object.entries(packed).map(([path, value]) => [path, new Uint8Array(Buffer.from(value as string, 'base64'))]))
const read = async (path: string) => {
  const value = originals.get(path)
  if (!value) throw new Error(`Missing original L-frame artifact: ${path}`)
  return value
}
const report = JSON.parse(Buffer.from(originals.get('comparison.json')!).toString())

test('actual nonlinear L-frame design retains plasticity, two-member quantities and unknown cost skips', async () => {
  const review = await validateRcDesignStudy(await read('comparison.json'), read)
  expect(review.report.selected_candidate_id).toBe('cheap')
  expect(review.report.control_request.targets_m).toHaveLength(12)
  expect(review.report.cost_pruning.skipped_candidate_ids).toEqual(['middle', 'costly'])
  for (const row of review.report.rows.slice(0, 2)) {
    expect(row.full_reference_verification_pass).toBe(true)
    expect(row.performance.maximum_steel_accumulated_plastic_strain).toBeGreaterThan(0)
    expect(row.quantities.members).toHaveLength(2)
  }
  for (const row of review.report.rows.slice(2)) {
    expect(row.performance).toBeNull()
    expect(row.invocations).toHaveLength(0)
    expect(row.selection_eligible).toBe(false)
  }
})

for (const width of [1440, 390]) test(`verified plastic L-frame design and exact download at ${width}px`, async ({ page }) => {
  // Hosted runs exhausted 30s at the final screenshot after all semantic checks.
  test.setTimeout(60000)
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlDesignUrl: '/l-frame/comparison.json', jobAuthorization: () => ({ tenantId: 'synthetic-l-frame', bearerToken: 'fixture-only' }) }
  })
  await page.route('**/l-frame/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer fixture-only')
    const path = new URL(route.request().url()).pathname.replace('/l-frame/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(await read(path)) })
  })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'}/#/workbench-v2`)
  const panel = page.locator('[data-rc-design]')
  await expect(panel).toHaveAttribute('data-rc-design', 'verified', { timeout: 60000 })
  await expect(panel.locator('[data-rc-design-constants]')).toContainText('N3, 0, -20, 0')
  await expect(panel.locator('[data-rc-design-cost-pruning]')).toContainText('2 candidates excluded')
  for (const id of ['middle', 'costly']) await expect(panel.getByRole('button', { name: `Select ${id}`, exact: true })).toBeDisabled()
  await panel.getByRole('button', { name: 'Select cheap', exact: true }).click()
  const row = report.rows.find((r: { candidate_id: string }) => r.candidate_id === 'cheap')
  const summary = panel.locator('[data-rc-design-summary="cheap"]')
  await expect(summary.locator('[data-rc-design-summary-field="estimate"] dd')).toHaveAttribute('title', String(row.material_estimate.total))
  const details = panel.locator('[data-rc-design-details="cheap"]')
  await expect(details.locator('[data-rc-design-metric="maximum_steel_accumulated_plastic_strain"] td').nth(1)).toHaveText(String(row.performance.maximum_steel_accumulated_plastic_strain))
  const pending = page.waitForEvent('download')
  await details.getByRole('button', { name: 'Download cheap result', exact: true }).click()
  const stream = await (await pending).createReadStream(), chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  expect(Buffer.concat(chunks)).toEqual(Buffer.from(await read('cheap/result.json')))
  const bounds = await panel.boundingBox()
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
  await panel.screenshot({ path: `test-results/l-frame-cost-${width}.png` })
})

for (const width of [1440, 390]) test(`L-frame material limit rejects cheaper design while preserving originals at ${width}px`, async ({ page }) => {
  test.setTimeout(60000)
  const packedBoundary = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/l-frame-boundary-artifacts.json.gz')).toString())
  const readBoundary = async (path: string) => {
    if (typeof packedBoundary[path] !== 'string') throw new Error(`Missing boundary artifact: ${path}`)
    return new Uint8Array(Buffer.from(packedBoundary[path], 'base64'))
  }
  const review = await validateRcDesignStudy(await readBoundary('comparison.json'), readBoundary)
  expect(review.report.selected_candidate_id).toBe('baseline')
  const rejected = review.report.rows.find((row: { candidate_id: string }) => row.candidate_id === 'cheap')!
  expect(rejected.full_reference_verification_pass).toBe(true)
  expect(rejected.selection_eligible).toBe(false)
  const screen = rejected.screens.maximum_steel_accumulated_plastic_strain
  expect(screen.status).toBe('fail')
  expect(screen.value).toBeGreaterThan(screen.limit)
  expect(screen.limit).toBe(0.00008)
  expect(rejected.invocations).toHaveLength(2)
  expect(review.report.cost_pruning.skipped_candidate_ids).toEqual(['middle', 'costly'])
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlDesignUrl: '/l-boundary/comparison.json', jobAuthorization: () => ({ tenantId: 'synthetic-boundary', bearerToken: 'fixture-only' }) }
  })
  await page.route('**/l-boundary/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer fixture-only')
    const path = new URL(route.request().url()).pathname.replace('/l-boundary/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(await readBoundary(path)) })
  })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'}/#/workbench-v2`)
  const panel = page.locator('[data-rc-design]')
  await expect(panel).toHaveAttribute('data-rc-design', 'verified', { timeout: 60000 })
  await expect(panel.locator('[data-rc-design-summary="baseline"]')).toBeVisible()
  for (const id of ['cheap', 'middle', 'costly']) await expect(panel.getByRole('button', { name: `Select ${id}`, exact: true })).toBeDisabled()
  await expect(panel.locator('[data-rc-design-candidate="cheap"]')).toContainText('Analysis verified; requested limits failed')
  await expect(panel.locator('[data-rc-design-candidate="middle"]')).toContainText('Not analyzed: more expensive')
  const details = panel.locator('[data-rc-design-details="cheap"]')
  await details.locator('summary').click()
  await expect(details.locator('[data-rc-design-limit-failure="maximum_steel_accumulated_plastic_strain"]')).toContainText(`Value ${screen.value}; limit ${screen.limit}`)
  const pending = page.waitForEvent('download')
  await details.getByRole('button', { name: 'Download cheap result', exact: true }).click()
  const stream = await (await pending).createReadStream(), chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  expect(Buffer.concat(chunks)).toEqual(Buffer.from(await readBoundary('cheap/result.json')))
  const bounds = await panel.boundingBox()
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
  await panel.screenshot({ path: `test-results/l-frame-boundary-${width}.png` })
})
