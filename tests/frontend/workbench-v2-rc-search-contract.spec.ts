import { expect, test } from '@playwright/test'
import { costOptimality } from '../../src/workbench-v2/model/rcControlSearchCost'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { fields } from '../../src/workbench-v2/model/rcJobSchema'
const root = 'tests/frontend/fixtures/rc-control-search/'
const read = async (path: string) => new Uint8Array(readFileSync(root + path))
const original = readFileSync(root + 'result.json')
const hash = (s: string) => `sha256:${createHash('sha256').update(s).digest('hex')}`
function changed(raw: string, changes: Record<string, string>, hashField: string): Uint8Array {
  const values = new Map([...fields(raw)].map(([k, v]) => [k, v.value]))
  values.delete(hashField)
  for (const [key, value] of Object.entries(changes)) values.set(key, value)
  const serialize = () => `{${[...values].sort(([a], [b]) => a < b ? -1 : 1).map(([k, v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`
  values.set(hashField, JSON.stringify(hash(serialize())))
  return new TextEncoder().encode(serialize())
}
test('RC search validates original pool, full-path designs, costs and later coverage', async () => {
  const review = await validateRcControlSearch(original, read)
  expect(Object.keys(review.designs).sort()).toEqual(['exhaustive_oracle', 'learned_order', 'price_order'])
  expect(review.plan.pool).toHaveLength(4)
  for (const name of ['learned_order', 'price_order']) {
    expect(review.report.arms[name].selected_candidate_id).toBe('cheap')
    expect(review.report.arms[name].execution_work.known_counters.attempted_step_count).toBe(32)
    expect(review.report.candidate_coverage_audit.arms[name].missed_feasible_candidate_ids).toEqual(['middle', 'costly'])
  }
  expect(review.designs.learned_order.models.cheap.sections[0].width_m).toBe(.36)
  expect(review.report.historical_training_cost.sample_count).toBe(3)
  expect(review.costOptimality.pool_minimum_feasible_candidate_ids).toEqual(['cheap'])
  expect(review.costOptimality.arms.learned_order.missed_cheaper_feasible_count).toBe(0)
})
test('RC search without an oracle preserves unavailable counts and avoids oracle reads', async () => {
  const directory = 'tests/frontend/fixtures/rc-control-search-no-oracle/'
  const paths: string[] = []
  const review = await validateRcControlSearch(readFileSync(directory + 'result.json'), async p => { paths.push(p); return new Uint8Array(readFileSync(directory + p)) })
  expect(paths.some(p => p.includes('exhaustive_oracle'))).toBe(false)
  expect(review.report.oracle).toBeNull()
  expect(review.report.candidate_coverage_audit.arms.learned_order.false_safe_count).toBeNull()
  expect(review.report.candidate_coverage_audit.arms.price_order.missed_feasible_count).toBeNull()
  expect(review.plan.pool).toHaveLength(4)
  expect(review.costOptimality.pool_minimum_feasible_estimate).toBeNull()
  expect(review.costOptimality.arms.learned_order.selected_minus_pool_minimum_estimate).toBeNull()
})

for (const suffix of ['', '-no-oracle']) {
  test(`RC search v3 verifies original exported cost audit ${suffix || 'with oracle'}`, async () => {
    const dir = `tests/frontend/fixtures/rc-control-search-cost${suffix}/`
    const review = await validateRcControlSearch(readFileSync(dir + 'result.json'), async p => new Uint8Array(readFileSync(dir + p)))
    expect(review.report.schema_version).toBe('experimental-rc-control-candidate-search.v3')
    expect(review.report.candidate_cost_optimality_audit).toEqual(review.costOptimality)
    expect(review.costOptimality.arms.price_order.selected_minus_pool_minimum_estimate).toBe(suffix ? null : 0)
  })
}
for (const [name, mutate] of [
  ['gap', (a: any) => { a.arms.learned_order.selected_minus_pool_minimum_estimate = 1 }],
  ['cheaper missed count', (a: any) => { a.arms.learned_order.missed_cheaper_feasible_count = 2 }],
  ['minimum', (a: any) => { a.pool_minimum_feasible_estimate = 0 }],
  ['baseline exclusion', (a: any) => { a.baseline_included = false }],
  ['global optimum', (a: any) => { a.global_design_optimality_proved = true }],
] as const) {
  test(`RC search v3 rejects a rehashed cost ${name}`, async () => {
    const dir = 'tests/frontend/fixtures/rc-control-search-cost/'
    const original = readFileSync(dir + 'result.json', 'utf8'), audit = JSON.parse(original).candidate_cost_optimality_audit
    mutate(audit)
    const raw = changed(original, { candidate_cost_optimality_audit: JSON.stringify(audit) }, 'report_hash')
    await expect(validateRcControlSearch(raw, async p => new Uint8Array(readFileSync(dir + p)))).rejects.toThrow('search_cost_optimality_invalid')
  })
}
test('RC search v3 refuses zero cost gap when an oracle was not run', async () => {
  const dir = 'tests/frontend/fixtures/rc-control-search-cost-no-oracle/'
  const original = readFileSync(dir + 'result.json', 'utf8'), audit = JSON.parse(original).candidate_cost_optimality_audit
  audit.arms.price_order.selected_minus_pool_minimum_estimate = 0
  const raw = changed(original, { candidate_cost_optimality_audit: JSON.stringify(audit) }, 'report_hash')
  await expect(validateRcControlSearch(raw, async p => new Uint8Array(readFileSync(dir + p)))).rejects.toThrow('search_cost_optimality_invalid')
})
for (const path of ['plan.json', 'policy.json', 'historical-training.json', 'pool/middle.json', 'price_order/cheap/result.json', 'learned_order/baseline/checkpoint.json', 'exhaustive_oracle/costly/verification.json']) {
  test(`RC search rejects changed original ${path}`, async () => {
    await expect(validateRcControlSearch(original, async p => {
      const bytes = await read(p)
      if (p !== path) return bytes
      // Metadata has a logical document hash, while payload references bind
      // exact bytes. Mutate metadata content, not insignificant outer whitespace.
      return ['plan.json', 'policy.json', 'historical-training.json'].includes(path)
        ? new TextEncoder().encode(new TextDecoder().decode(bytes).replace('\"schema_version\":\"', '\"schema_version\":\"tampered-'))
        : new Uint8Array(Buffer.concat([bytes, Buffer.from(' ')]))
    })).rejects.toThrow()
  })
}
for (const [name, field, mutate] of [
  ['coverage', 'candidate_coverage_audit', (v: any) => { v.arms.learned_order.missed_feasible_count = 0 }],
  ['selected candidate', 'arms', (v: any) => { v.learned_order.selected_candidate_id = 'middle' }],
  ['hidden work', 'arms', (v: any) => { v.learned_order.execution_work.known_counters.attempted_step_count = 0 }],
  ['path escape', 'arms', (v: any) => { v.price_order.comparison_path = '../comparison.json' }],
  ['promotion claim', 'claims', (v: any) => { v.net_savings_proved = true }],
  ['duplicate training accounting', 'historical_training_cost_counted_once_outside_online_arms', (_v: any) => false],
] as const) {
  test(`RC search rejects rehashed ${name}`, async () => {
    const value = JSON.parse(original.toString())[field]
    const next = mutate(value) ?? value
    const raw = changed(original.toString(), { [field]: JSON.stringify(next) }, 'report_hash')
    await expect(validateRcControlSearch(raw, read)).rejects.toThrow()
  })
}
test('RC search rejects a rehashed ranking inconsistent with predictions and prices', async () => {
  const rawPlan = readFileSync(root + 'plan.json', 'utf8'), plans = JSON.parse(rawPlan).plans
  plans.learned_order.ordering.reverse()
  const plan = changed(rawPlan, { plans: JSON.stringify(plans) }, 'plan_hash')
  const result = changed(original.toString(), { plan_hash: JSON.stringify(JSON.parse(new TextDecoder().decode(plan)).plan_hash) }, 'report_hash')
  await expect(validateRcControlSearch(result, p => p === 'plan.json' ? Promise.resolve(plan) : read(p))).rejects.toThrow('search_ranking_invalid')
})
test('RC search refuses duplicate keys and oversized reports before any artifact read', async () => {
  let calls = 0
  const counted = async (p: string) => { calls++; return read(p) }
  await expect(validateRcControlSearch(new TextEncoder().encode(original.toString().replace('{', '{"schema_version":"duplicate",')), counted)).rejects.toThrow()
  await expect(validateRcControlSearch(new Uint8Array(2 * 1024 ** 2 + 1), counted)).rejects.toThrow('search_report_too_large')
  expect(calls).toBe(0)
})

test('RC search cost arithmetic distinguishes loss, ties and unknown outcomes in controlled inputs', () => {
  // These are mathematical controls, not validated experimental artifacts.
  const pool = ['baseline', 'cheap', 'middle'].map((candidate_id, i) => ({ candidate_id,
    material_estimate: { total: [300, 100, 200][i], currency: 'KRW', scope: 'test' } }))
  const rows = pool.map(p => ({ ...p, full_reference_verification_pass: true, screens: { limit: { status: 'pass' } } }))
  const plan = { pool, price_table_hash: 'common', history_limits: { limit: 1 }, material_limits: {}, terminal_limits: null,
    plans: { price_order: { shortlist: ['cheap'] }, learned_order: { shortlist: ['middle'] } } }
  const reports = { price_order: { selected_candidate_id: 'cheap' }, learned_order: { selected_candidate_id: 'middle' },
    exhaustive_oracle: { report_hash: 'oracle', rows } }
  const cost = costOptimality(plan, reports)
  expect(cost.arms.price_order.selected_minus_pool_minimum_estimate).toBe(0)
  expect(cost.arms.learned_order.selected_minus_pool_minimum_estimate).toBe(100)
  expect(cost.arms.learned_order.missed_cheaper_feasible_candidate_ids).toEqual(['cheap'])
  rows[0].full_reference_verification_pass = false
  expect(costOptimality(plan, reports).arms.learned_order.selected_minus_pool_minimum_estimate).toBeNull()
  rows[0].full_reference_verification_pass = true
  for (const row of pool) row.material_estimate.total = 0
  const ties = costOptimality(plan, reports)
  expect(ties.pool_minimum_feasible_candidate_ids).toEqual(['baseline', 'cheap', 'middle'])
  expect(ties.arms.learned_order.matches_pool_minimum).toBe(true)
})
