import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { fields } from '../../src/workbench-v2/model/rcJobSchema'
import { layoutFiles, layoutRead } from './layoutSearchFixture'
function changed(raw: Uint8Array, edits: Record<string,string>, key: string): Uint8Array {
  const values = new Map([...fields(new TextDecoder().decode(raw))].map(([k,v]) => [k,v.value]))
  values.delete(key); for (const [k,v] of Object.entries(edits)) values.set(k,v)
  const encode = () => `{${[...values].sort(([a],[b]) => a < b ? -1 : 1).map(([k,v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`
  values.set(key, JSON.stringify(`sha256:${createHash('sha256').update(encode()).digest('hex')}`))
  return new TextEncoder().encode(encode())
}
test('RC layout search verifies original full-path histories and preserves original reports', async () => {
  const review = await validateRcControlSearch(layoutFiles['result.json'],layoutRead)
  expect(review.report.arms.price_order.selected_candidate_id).toBeNull()
  expect(review.report.arms.learned_order.selected_candidate_id).toBe('large')
  expect(review.costOptimality.pool_minimum_feasible_candidate_ids).toEqual(['middle'])
  expect(review.costOptimality.arms.learned_order.missed_cheaper_feasible_count).toBe(1)
  expect(review.designs.learned_order.report).toEqual(JSON.parse(layoutFiles['learned_order/comparison.json'].toString()))
  expect(review.designs.learned_order.report.prices).toBeUndefined()
  expect(review.designs.learned_order.displayReport?.prices.currency).toBe('KRW')
  expect(review.designs.learned_order.displayReport?.rows[1].scoped_estimate_reduction).toBeLessThan(0)
  expect(review.designs.learned_order.models.large.nodes[1].coordinates[0]).toBe(3.4)
})
for (const path of ['price-table.json','pool/small.json','learned_order/large/baseline/result.json','learned_order/large/baseline/checkpoint.json','learned_order/large/baseline/verification.json']) {
  test(`RC layout search rejects changed original bytes ${path}`,async () => {
    await expect(validateRcControlSearch(layoutFiles['result.json'],async p => p === path ? new Uint8Array(path === 'price-table.json' ? Buffer.from(JSON.stringify({ ...JSON.parse(layoutFiles[p].toString()), concrete_per_m3: 101 })) : Buffer.concat([layoutFiles[p],Buffer.from(' ')])) : layoutRead(p))).rejects.toThrow()
  })
}
for (const [name, mutate] of [
  ['cost gap',(r:any)=>{r.candidate_cost_optimality_audit.arms.learned_order.selected_minus_pool_minimum_estimate=0}],
  ['false promotion',(r:any)=>{r.claims.functional_equivalence_verified=true}],
  ['unknown work',(r:any)=>{r.arms.learned_order.execution_work.unknown_work=true}],
] as const) {
  test(`RC layout search rejects rehashed ${name}`,async () => {
    const r=JSON.parse(layoutFiles['result.json'].toString());mutate(r)
    const edits=Object.fromEntries(Object.entries(r).filter(([k])=>k!=='report_hash').map(([k,v])=>[k,JSON.stringify(v)]))
    await expect(validateRcControlSearch(changed(layoutFiles['result.json'],edits,'report_hash'),layoutRead)).rejects.toThrow()
  })
}
