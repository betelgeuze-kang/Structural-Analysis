import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { gunzipSync } from 'node:zlib'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { validateRcDesignStudy } from '../../src/workbench-v2/model/rcControlDesignSchema'
import { fields, document, selfHash } from '../../src/workbench-v2/model/rcJobSchema'

const packed = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/cost-pruned-search-artifacts.json.gz')).toString())
const originals = new Map<string, Uint8Array>(Object.entries(packed).map(([path, encoded]) => [path, new Uint8Array(Buffer.from(encoded as string, 'base64'))]))
const read = async (path: string) => {
  const raw = originals.get(path)
  if (!raw) throw new Error(`unregistered fixture artifact: ${path}`)
  return raw
}
const hash = (raw: string | Uint8Array) => `sha256:${createHash('sha256').update(raw).digest('hex')}`
function changed(raw: string, changes: Record<string, string>, hashField?: string): Uint8Array {
  const values = new Map([...fields(raw)].map(([k, v]) => [k, v.value]))
  if (hashField) values.delete(hashField)
  for (const [key, value] of Object.entries(changes)) values.set(key, value)
  const serialize = () => `{${[...values].sort(([a], [b]) => a < b ? -1 : 1).map(([k, v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`
  if (hashField) values.set(hashField, JSON.stringify(hash(serialize())))
  return new TextEncoder().encode(serialize())
}

test('actual CLI search cost pruning retains full oracle and unknown skipped feasibility', async () => {
  const review = await validateRcControlSearch(await read('result.json'), read)
  for (const name of ['price_order', 'learned_order']) {
    const arm = review.report.arms[name], report = review.designs[name].report
    expect(arm.request_count).toBe(3)
    expect(arm.actual_model_execution_count).toBe(2)
    expect(arm.execution_work.api_invocation_count).toBe(4)
    expect(arm.cost_excluded_candidate_ids).toEqual(['middle'])
    expect(report.selected_candidate_id).toBe('cheaper')
    expect(report.cost_pruning.minimum_scoped_estimate_proved_within_declared_candidates).toBe(true)
    expect(report.cost_pruning.skipped_candidate_feasibility_known).toBe(false)
    expect(report.cost_pruning.saved_wall_time_measured).toBe(false)
    expect(report.rows[2].performance).toBeNull()
  }
  expect(review.designs.exhaustive_oracle.report.verified_count).toBe(4)
  expect(review.designs.exhaustive_oracle.report.cost_pruning).toBeUndefined()
  expect(review.report.claims.net_savings_proved).toBe(false)
})

for (const mutation of ['incumbent', 'price', 'feasibility', 'invocations']) {
  test(`rehashed skip receipt rejects false ${mutation}`, async () => {
    const receiptPath = 'learned_order/middle/cost-skip.json'
    const receipt = JSON.parse(new TextDecoder().decode(await read(receiptPath)))
    if (mutation === 'incumbent') receipt.incumbent.candidate_id = 'baseline'
    if (mutation === 'price') receipt.price_table_hash = `sha256:${'0'.repeat(64)}`
    if (mutation === 'feasibility') receipt.candidate_feasibility = 'verified'
    if (mutation === 'invocations') receipt.solver_invocation_count = 2
    const next = new TextEncoder().encode(JSON.stringify(receipt))
    const original = new TextDecoder().decode(await read('learned_order/comparison.json'))
    const report = JSON.parse(original), old = report.rows[2].artifacts.cost_skip
    // Replace only this artifact reference, preserving original Python number spellings.
    const rebound = original.replace(old.sha256, hash(next)).replace(`"byte_length":${old.byte_length},"path":"middle/cost-skip.json"`, `"byte_length":${next.length},"path":"middle/cost-skip.json"`)
    const raw = changed(rebound, {}, 'report_hash')
    await selfHash(document(raw).raw, document(raw).value, 'report_hash')
    await expect(validateRcDesignStudy(raw, p => p === 'middle/cost-skip.json' ? Promise.resolve(next) : read(`learned_order/${p}`))).rejects.toThrow('study_cost_skip_receipt_invalid')
  })
}

for (const width of [1440, 390]) test(`cost-excluded candidate stays unavailable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/pruned/result.json', jobAuthorization: () => ({ tenantId: 'fixture', bearerToken: 'synthetic' }) }
  })
  await page.route('**/pruned/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/pruned/', '')
    await route.fulfill({ contentType: 'application/json', body: Buffer.from(await read(path)) })
  })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'}/#/workbench-v2`)
  const panel = page.locator('[data-rc-search]')
  await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
  await panel.getByRole('button', { name: 'Review Learned order', exact: true }).click()
  await expect(panel.locator('[data-rc-design-cost-pruning]')).toContainText('1 candidates excluded')
  await expect(panel.getByRole('button', { name: 'Select middle', exact: true })).toBeDisabled()
  const details = panel.locator('[data-rc-design-details="middle"]')
  await details.locator('summary').click()
  await expect(details).toContainText('UNAVAILABLE')
  await expect(details.getByRole('button', { name: 'Download middle result', exact: true })).toHaveCount(0)
  const pending = page.waitForEvent('download')
  await details.getByRole('button', { name: 'Download middle cost skip', exact: true }).click()
  const stream = await (await pending).createReadStream(), chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  expect(Buffer.concat(chunks)).toEqual(Buffer.from(await read('learned_order/middle/cost-skip.json')))
  await panel.screenshot({ path: `test-results/cost-pruned-search-${width}.png` })
})
