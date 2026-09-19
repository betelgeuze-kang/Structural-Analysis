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
