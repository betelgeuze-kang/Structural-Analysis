import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { validRcPriceMetadata } from '../../src/workbench-v2/model/rcPriceMetadata'
import { validateRcDesignStudy } from '../../src/workbench-v2/model/rcControlDesignSchema'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { document, fields, selfHash } from '../../src/workbench-v2/model/rcJobSchema'
import { standaloneLayouts } from './layoutStandaloneFixture'

// These tests review stored bytes and declarations only; they run no solver.
const base = { currency: 'KRW', as_of: '2026-10-02', source: 'synthetic material rates only' }
const valid: Array<[string, Record<string, unknown>]> = [
  ['ordinary declaration', base],
  ['unregistered uppercase currency code', { currency: 'ABC' }],
  ['Gregorian leap day', { as_of: '2000-02-29' }],
  ['first Python date year', { as_of: '0001-01-01' }],
  ['last Python date year', { as_of: '9999-12-31' }],
  ['padded nonempty source', { source: ' \t declared fixture rates \n' }],
  ['1000 non-BMP code points', { source: '𐐀'.repeat(1000) }],
  ['Python non-whitespace byte order mark', { source: '\ufeff' }],
  ['Python non-whitespace zero width space', { source: '\u200b' }],
]
const invalid: Array<[string, Record<string, unknown>]> = [
  ['empty source', { source: '' }],
  ['ordinary whitespace source', { source: ' \t\r\n' }],
  ['Python whitespace source', { source: '\u001c\u001d\u001e\u001f\u0085' }],
  ['Unicode whitespace source', { source: '\u00a0\u1680\u2000\u200a\u2028\u2029\u202f\u205f\u3000' }],
  ['overlong ASCII source', { source: 'a'.repeat(1001) }],
  ['overlong non-BMP source', { source: '𐐀'.repeat(1001) }],
  ['non-string source', { source: 1 }],
  ['lowercase currency', { currency: 'krw' }],
  ['short currency', { currency: 'KR' }],
  ['currency final newline', { currency: 'KRW\n' }],
  ['non-string currency', { currency: null }],
  ['non-calendar date', { as_of: '2026-02-30' }],
  ['non-leap century', { as_of: '1900-02-29' }],
  ['non-leap year', { as_of: '2026-02-29' }],
  ['zero date year', { as_of: '0000-01-01' }],
  ['date month zero', { as_of: '2026-00-01' }],
  ['date month thirteen', { as_of: '2026-13-01' }],
  ['date day zero', { as_of: '2026-01-00' }],
  ['non-padded date', { as_of: '2026-1-01' }],
  ['date final newline', { as_of: '2026-01-01\n' }],
  ['non-ASCII date digits', { as_of: '２０２６-０１-０１' }],
  ['non-string date', { as_of: false }],
]
for (const [name, edits] of valid) test(`RC price metadata accepts producer-valid ${name}`, () => {
  expect(validRcPriceMetadata({ ...base, ...edits })).toBe(true)
})
for (const [name, edits] of invalid) test(`RC price metadata rejects producer-invalid ${name}`, () => {
  expect(validRcPriceMetadata({ ...base, ...edits })).toBe(false)
})

const hash = (value: string | Uint8Array) => `sha256:${createHash('sha256').update(value).digest('hex')}`
const bytes = (raw: string) => new TextEncoder().encode(raw)
function encode(values: Map<string, string>): string {
  return `{${[...values].sort(([a], [b]) => a < b ? -1 : 1).map(([key, value]) => `${JSON.stringify(key)}:${value}`).join(',')}}`
}
function edit(raw: string, edits: Record<string, string>, hashKey?: string): string {
  const values = new Map([...fields(raw)].map(([key, value]) => [key, value.value]))
  if (hashKey) values.delete(hashKey)
  for (const [key, value] of Object.entries(edits)) values.set(key, value)
  if (hashKey) values.set(hashKey, JSON.stringify(hash(encode(values))))
  return encode(values)
}
function priceHash(raw: string): string {
  return hash(edit(raw, { schema_version: '"declared-rc-material-prices.v1"' }))
}
function declaration(raw: string, edits: Record<string, unknown>): string {
  return edit(raw, Object.fromEntries(Object.entries(edits).map(([key, value]) => [key, JSON.stringify(value)])))
}
function rebindPrice(raw: string, before: string, after: string, edits: Record<string, unknown>): string {
  raw = raw.replaceAll(before, after)
  // Keep every estimate's currency consistent with the changed table. No rate,
  // quantity, estimate arithmetic or original numerical artifact is altered.
  return edits.currency === undefined ? raw : raw.replaceAll('"currency":"KRW"', `"currency":${JSON.stringify(edits.currency)}`)
}
const designRoot = 'tests/frontend/fixtures/rc-control-design/'
const designOriginal = readFileSync(`${designRoot}comparison.json`, 'utf8')
const designRead = async (path: string) => new Uint8Array(readFileSync(`${designRoot}${path}`))
function reboundDesign(edits: Record<string, unknown>): Uint8Array {
  const old = JSON.parse(designOriginal)
  const prices = declaration(fields(designOriginal).get('prices')!.value, edits)
  let raw = edit(designOriginal, { prices })
  raw = rebindPrice(raw, old.price_table_hash, priceHash(prices), edits)
  const identityKeys = ['schema_version', 'baseline_checksum', 'candidates', 'control_request', 'history_limits', 'material_limits', 'terminal_limits', 'prices', 'price_table_hash', 'source_revision', 'source_revision_is_attestation']
  const reportFields = fields(raw)
  const identity = encode(new Map(identityKeys.map(key => [key, reportFields.get(key)!.value])))
  return bytes(edit(raw, { request_hash: JSON.stringify(hash(identity)) }, 'report_hash'))
}
const layoutOriginal = standaloneLayouts['b2-o0-price_order']
function reboundLayout(edits: Record<string, unknown>): Record<string, Uint8Array> {
  const oldPlan = JSON.parse(layoutOriginal['plan.json'].toString())
  const oldComparison = JSON.parse(layoutOriginal['price_order/comparison.json'].toString())
  const prices = declaration(layoutOriginal['price-table.json'].toString(), edits)
  const nextHash = priceHash(prices)
  const plan = edit(rebindPrice(layoutOriginal['plan.json'].toString(), oldPlan.price_table_hash, nextHash, edits), {}, 'plan_hash')
  const comparison = edit(rebindPrice(layoutOriginal['price_order/comparison.json'].toString(), oldPlan.price_table_hash, nextHash, edits), {}, 'report_hash')
  const result = rebindPrice(layoutOriginal['result.json'].toString(), oldPlan.price_table_hash, nextHash, edits)
    .replaceAll(oldPlan.plan_hash, JSON.parse(plan).plan_hash)
    .replaceAll(oldComparison.report_hash, JSON.parse(comparison).report_hash)
  return { ...layoutOriginal, 'price-table.json': bytes(prices), 'plan.json': bytes(plan),
    'price_order/comparison.json': bytes(comparison), 'result.json': bytes(edit(result, {}, 'report_hash')) }
}
async function validOuterHash(raw: Uint8Array, key: string): Promise<void> {
  const doc = document(raw)
  await selfHash(doc.raw, doc.value, key)
}
test('new RC price boundary accepts unchanged original metadata in both contracts', () => {
  expect(validRcPriceMetadata(JSON.parse(designOriginal).prices)).toBe(true)
  expect(validRcPriceMetadata(JSON.parse(layoutOriginal['price-table.json'].toString()))).toBe(true)
})
test('RC price metadata rebind preserves accepted design and layout bytes and selection', async () => {
  const edits = { source: '  synthetic declaration with valid provenance text  ', as_of: '2000-02-29' }
  const design = reboundDesign(edits), layout = reboundLayout(edits)
  const reviewedDesign = await validateRcDesignStudy(design, designRead)
  expect(reviewedDesign.report.prices.source).toBe(edits.source)
  expect(reviewedDesign.report.selected_candidate_id).toBe(JSON.parse(designOriginal).selected_candidate_id)
  const reviewedLayout = await validateRcControlSearch(layout['result.json'], async path => layout[path])
  expect(reviewedLayout.designs.price_order.displayReport?.prices.source).toBe(edits.source)
  expect(reviewedLayout.report.arms.price_order.selected_candidate_id).toBe(JSON.parse(layoutOriginal['result.json'].toString()).arms.price_order.selected_candidate_id)
  for (const [path, original] of Object.entries(layoutOriginal)) {
    if (['price-table.json', 'plan.json', 'price_order/comparison.json', 'result.json'].includes(path)) continue
    expect(layout[path]).toBe(original)
  }
})
for (const [name, edits] of invalid.filter(([name]) => ['empty source', 'Python whitespace source', 'non-calendar date', 'lowercase currency'].includes(name))) {
  test(`RC design rejects completely rehashed price metadata: ${name}`, async () => {
    const raw = reboundDesign(edits)
    await validOuterHash(raw, 'report_hash')
    await expect(validateRcDesignStudy(raw, designRead)).rejects.toThrow('study_prices_invalid')
  })
  test(`RC layout rejects completely rehashed price metadata: ${name}`, async () => {
    const files = reboundLayout(edits)
    for (const [path, key] of [['result.json', 'report_hash'], ['plan.json', 'plan_hash'], ['price_order/comparison.json', 'report_hash']]) {
      await validOuterHash(files[path], key)
    }
    const plan = document(files['plan.json']).value
    expect(plan.price_table_hash).toBe(priceHash(new TextDecoder().decode(files['price-table.json'])))
    await expect(validateRcControlSearch(files['result.json'], async path => files[path])).rejects.toThrow('layout_prices_invalid')
  })
}
