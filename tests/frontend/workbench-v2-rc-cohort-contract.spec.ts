import { expect, test } from '@playwright/test'
import { validateRcStrategyCohort } from '../../src/workbench-v2/model/rcStrategyCohortSchema'
import { cohortBytes } from './rc-cohort-fixture'
import { rebind } from './rc-search-standalone-fixture'
import { document, selfHash } from '../../src/workbench-v2/model/rcJobSchema'
import { createHash } from 'node:crypto'

const original = cohortBytes('cohort.json')
test('Python cohort validates both original designs, runtime digests and once-counted training', async () => {
  const review = await validateRcStrategyCohort(original, async p => cohortBytes(p))
  expect(review.executions.map(e => e.selected)).toEqual(['cheap', 'cheap'])
  expect(review.executions).toHaveLength(2)
  expect(Object.keys(review.cost.distinct_historical_training_wall_ns)).toHaveLength(1)
  expect(review.cost).toEqual(review.manifest.cost_accounting)
  expect(review.cost.net_savings_proved).toBe(false)
})
for (const mutation of ['training', 'ratio', 'pair_count', 'path', 'report_hash', 'extra_claim', 'physical_bytes', 'runtime_clock', 'runtime_zero']) {
  test(`cohort rejects rehashed or replaced ${mutation}`, async () => {
    const m = JSON.parse(new TextDecoder().decode(original)); let runtime: Uint8Array | null = null
    if (mutation === 'training') m.cost_accounting.historical_training_wall_ns_counted_once = 0
    if (mutation === 'ratio') m.cost_accounting.learned_plus_historical_over_price_ratio = 0
    if (mutation === 'pair_count') m.cost_accounting.pair_count = true
    if (mutation === 'path') m.pairs[0].price_order.runtime.path = '../runtime.json'
    if (mutation === 'report_hash') m.pairs[0].price_order.report_hash = m.pairs[0].learned_order.report_hash
    if (mutation === 'extra_claim') m.net_savings_proved = true
    if (mutation === 'runtime_clock' || mutation === 'runtime_zero') {
      const r = JSON.parse(new TextDecoder().decode(cohortBytes(m.pairs[0].price_order.runtime.path))); r.wall_ns = mutation === 'runtime_zero' ? 0 : true
      runtime = new TextEncoder().encode(JSON.stringify(r))
      m.pairs[0].price_order.runtime.byte_length = runtime.byteLength
      m.pairs[0].price_order.runtime.sha256 = `sha256:${createHash('sha256').update(runtime).digest('hex')}`
    }
    delete m.report_hash
    const raw = rebind(new TextDecoder().decode(original), m, 'report_hash')
    const rebound = document(raw)
    await selfHash(rebound.raw, rebound.value, 'report_hash')
    const read = async (p: string) => {
      if (mutation === 'physical_bytes' && p.endsWith('/cheap/checkpoint.json')) return new Uint8Array([...cohortBytes(p), 32])
      return runtime && p === m.pairs[0].price_order.runtime.path ? runtime : cohortBytes(p)
    }
    await expect(validateRcStrategyCohort(raw, read)).rejects.toThrow()
  })
}
test('duplicate keys reject before original artifact reads', async () => {
  let reads = 0
  const raw = new TextEncoder().encode(new TextDecoder().decode(original).replace('{', '{"pairs":[], '))
  await expect(validateRcStrategyCohort(raw, async p => { reads++; return cohortBytes(p) })).rejects.toThrow()
  expect(reads).toBe(0)
})

test('process cohort recomputes enclosing intervals and retains original CLI accounting', async () => {
  const { processCohortBytes } = await import('./rc-cohort-fixture')
  const review = await validateRcStrategyCohort(processCohortBytes('cohort.json'), async path => processCohortBytes(path))
  expect(review.processCost!.price_process_interval_sum_ns).toBe(review.cost.price_cli_interval_sum_ns + 1000)
  expect(review.processCost!.historical_training_wall_ns_counted_once).toBe(review.cost.historical_training_wall_ns_counted_once)
  expect(review.processCost!.net_savings_proved).toBe(false)
})
for (const mutation of ['bytes', 'short', 'duplicate', 'bool_exit', 'scope', 'extra', 'cost', 'overflow']) {
  test(`process cohort refuses changed ${mutation}`, async () => {
    const { processCohortBytes } = await import('./rc-cohort-fixture')
    const rootRaw = new TextDecoder().decode(processCohortBytes('cohort.json')), manifest = JSON.parse(rootRaw)
    let processRaw = processCohortBytes('process-observations.json')
    const changes: Record<string, unknown> = {}
    if (mutation === 'cost') { manifest.process_cost_accounting.price_process_interval_sum_ns++; changes.process_cost_accounting = manifest.process_cost_accounting }
    else if (mutation === 'bytes') processRaw = new Uint8Array([...processRaw, 32])
    else {
      const doc = JSON.parse(new TextDecoder().decode(processRaw)), p = doc.processes[0]
      if (mutation === 'short') p.wall_ns = 0
      if (mutation === 'duplicate') doc.processes[1] = p
      if (mutation === 'bool_exit') p.return_code = false
      if (mutation === 'scope') p.scope = 'solver_only'
      if (mutation === 'extra') p.attested = true
      if (mutation === 'overflow') for (const item of doc.processes) item.wall_ns = Number.MAX_SAFE_INTEGER
      processRaw = new TextEncoder().encode(JSON.stringify(doc))
      changes.process_observations = { ...manifest.process_observations, byte_length: processRaw.length, sha256: `sha256:${createHash('sha256').update(processRaw).digest('hex')}` }
    }
    const raw = rebind(rootRaw, changes, 'report_hash')
    await expect(validateRcStrategyCohort(raw, async path => path === 'process-observations.json' ? processRaw : processCohortBytes(path))).rejects.toThrow()
  })
}

for (const path of ['cohort.json', 'pairs/0/price_order/plan.json', 'pairs/0/learned_order/result.json']) {
  test(`full-object mutation helper produces a valid replacement hash for ${path}`, async () => {
    const raw = new TextDecoder().decode(cohortBytes(path))
    const value = JSON.parse(raw), field = path.endsWith('plan.json') ? 'plan_hash' : 'report_hash'
    const replacement = rebind(raw, { ...value, source_revision: 'b'.repeat(40) }, field)
    const doc = document(replacement)
    expect(doc.value.source_revision).toBe('b'.repeat(40))
    expect(doc.value[field]).not.toBe(value[field])
    await selfHash(doc.raw, doc.value, field)
  })
}
