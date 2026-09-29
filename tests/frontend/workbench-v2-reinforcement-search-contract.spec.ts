import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'

// Original bytes produced by the real train/search CLIs and checked by the HTTP mount.
const packed = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/reinforcement-search-artifacts.json.gz')).toString())
const originals = new Map<string, Uint8Array>(Object.entries(packed).map(([path, encoded]) => [path, new Uint8Array(Buffer.from(encoded as string, 'base64'))]))
const read = async (path: string) => {
  const raw = originals.get(path)
  if (!raw) throw new Error('unregistered fixture artifact')
  return raw
}

test('Workbench verifies original reinforcement policy search with full cost and oracle', async () => {
  const review = await validateRcControlSearch(await read('result.json'), read)
  expect(review.report.historical_training_cost.schema_version).toBe('experimental-rc-control-reinforcement-training.v1')
  expect(review.report.historical_training_cost.sample_count).toBe(3)
  for (const arm of ['price_order', 'learned_order']) {
    expect(review.report.arms[arm].selected_candidate_id).toBe('cheaper')
    expect(review.report.arms[arm].selected_full_reference_verified).toBe(true)
  }
  expect(review.report.claims.net_savings_proved).toBe(false)
  expect(review.report.oracle).not.toBeNull()
})

test('reinforcement search preserves exact original policy bytes', async () => {
  const wrong = async (path: string) => path === 'policy.json'
    ? new TextEncoder().encode(new TextDecoder().decode(await read(path)).replace('reinforcement-policy.v1', 'candidate-policy.v1'))
    : read(path)
  await expect(validateRcControlSearch(await read('result.json'), wrong)).rejects.toThrow()
})

for (const width of [1440, 390]) test(`reinforcement search original design review at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/reinforcement/result.json', jobAuthorization: () => ({ tenantId: 'fixture', bearerToken: 'synthetic' }) }
  })
  await page.route('**/reinforcement/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('fixture')
    const path = new URL(route.request().url()).pathname.replace('/reinforcement/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(await read(path)) })
  })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'}/#/workbench-v2`)
  const panel = page.locator('[data-rc-search]')
  await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
  await panel.getByRole('button', { name: 'Review Learned order', exact: true }).click()
  await panel.getByRole('button', { name: 'Select cheaper', exact: true }).click()
  const details = panel.locator('[data-rc-design-details="cheaper"]')
  await expect(panel.locator('[data-rc-design-selected="cheaper"]')).toContainText('top 4 × 0.00025 m²; bottom 4 × 0.00035 m²')
  const pending = page.waitForEvent('download')
  await details.getByRole('button', { name: 'Download cheaper result', exact: true }).click()
  const stream = await (await pending).createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  expect(Buffer.concat(chunks)).toEqual(Buffer.from(await read('learned_order/cheaper/result.json')))
  await panel.screenshot({ path: `test-results/reinforcement-search-${width}.png` })
})

// Real later observation: the learned middle candidate crosses the fixed screen.
const boundaryPacked = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/boundary-search-artifacts.json.gz')).toString())
const boundaryRead = async (path: string) => {
  if (!(path in boundaryPacked)) throw new Error('unregistered boundary artifact')
  return new Uint8Array(Buffer.from(boundaryPacked[path], 'base64'))
}

test('actual boundary prediction cannot override verified screen failure', async () => {
  const review = await validateRcControlSearch(await boundaryRead('result.json'), boundaryRead)
  const row = review.designs.learned_order.report.rows.find((r: any) => r.candidate_id === 'middle')
  const prediction = review.plan.predictions.find((r: any) => r.candidate_id === 'middle')
  expect(prediction.predicted_screens.maximum_absolute_fiber_strain.status).toBe('pass')
  expect(row.full_reference_verification_pass).toBe(true)
  expect(row.screens.maximum_absolute_fiber_strain.status).toBe('fail')
  expect(row.selection_eligible).toBe(false)
  expect(review.report.candidate_coverage_audit.arms.learned_order.false_safe_candidate_ids).toEqual(['middle'])
  expect(review.report.arms.learned_order.selected_candidate_id).toBe('cheap')
  expect(review.costOptimality.arms.learned_order.selected_minus_pool_minimum_estimate).toBe(0)
  expect(review.report.claims.net_savings_proved).toBe(false)
})

for (const width of [1440, 390]) test(`actual false-pass candidate stays unselectable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/boundary/result.json', jobAuthorization: () => ({ tenantId: 'fixture', bearerToken: 'synthetic' }) }
  })
  await page.route('**/boundary/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic')
    expect(await route.request().headerValue('x-structural-tenant')).toBe('fixture')
    const path = new URL(route.request().url()).pathname.replace('/boundary/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(await boundaryRead(path)) })
  })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'}/#/workbench-v2`)
  const panel = page.locator('[data-rc-search]')
  await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
  const coverage = panel.locator('[data-rc-search-candidate="middle"]')
  await expect(coverage).toContainText('Predicted pass')
  await expect(coverage).toContainText('Verified limit failure')
  await panel.getByRole('button', { name: 'Review Learned order', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Select middle', exact: true })).toBeDisabled()
  await panel.getByRole('button', { name: 'Select cheap', exact: true }).click()
  await expect(panel.locator('[data-rc-design-selected="cheap"]')).toBeVisible()
  const details = panel.locator('[data-rc-design-details="middle"]')
  await details.locator('summary').click()
  const reason = details.locator('[data-rc-design-limit-failure="maximum_absolute_fiber_strain"]')
  await expect(reason).toBeVisible()
  await expect(reason).toContainText('Value 0.0007000920865862819; limit 0.0007')
  const bounds = await reason.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
  await expect(panel.locator('[data-rc-design-candidate="middle"]')).toContainText('Analysis verified; requested limits failed')
  const strain = details.locator('[data-rc-design-metric="maximum_absolute_fiber_strain"]')
  await expect(strain).toContainText('0.0007000920865862819')
  await expect(strain).toContainText('fail')
  const pending = page.waitForEvent('download')
  await details.getByRole('button', { name: 'Download middle result', exact: true }).click()
  const stream = await (await pending).createReadStream(), chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  expect(Buffer.concat(chunks)).toEqual(Buffer.from(await boundaryRead('learned_order/middle/result.json')))
  await details.screenshot({ path: `test-results/boundary-middle-${width}.png` })
})
