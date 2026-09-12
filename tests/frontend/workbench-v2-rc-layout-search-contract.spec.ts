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

import { standaloneLayouts } from './layoutStandaloneFixture'
import { prunedLayouts } from './layoutPrunedFixture'

for (const [id, files] of Object.entries(prunedLayouts)) {
  test(`RC layout pruned validates original decisions ${id}`, async () => {
    const requested: string[] = []
    const review = await validateRcControlSearch(files['result.json'], async path => { requested.push(path); if (!files[path]) throw new Error('missing original'); return files[path] })
    const strategy = id === 'learned' ? 'learned_order' : 'price_order'
    const pruning = review.report.arms[strategy].cost_pruning
    expect(review.costOptimality).toBeNull()
    expect(review.report.candidate_coverage_audit).toBeNull()
    expect(review.report.arms[strategy].selected_candidate_id).toBe(id === 'horizon' ? null : 'middle')
    expect(pruning.skipped_cost_dominated_candidate_ids).toEqual(id === 'horizon' ? [] : id === 'price' ? ['large', 'outside'] : ['outside'])
    expect(pruning.outside_consideration_horizon_candidate_ids).toEqual(id === 'horizon' ? ['middle', 'large', 'outside'] : [])
    expect(pruning.unevaluated_physical_feasibility).toBe('unknown')
    for (const r of pruning.decisions) expect(requested).toContain(`${strategy}/${r.artifact.path}`)
    for (const key of pruning.unevaluated_candidate_ids) {
      expect(requested).toContain(`pool/${key}.json`)
      expect(requested.some(p => p.startsWith(`${strategy}/${key}/`))).toBe(false)
    }
    expect(review.designs[strategy].report).toEqual(JSON.parse(files[`${strategy}/comparison.json`].toString()))
  })
  for (const change of ['decision_action', 'future_rows', 'physical_promotion', 'raw_decision', 'pool_model']) {
    test(`RC layout pruned rejects ${id} ${change}`, async () => {
      const source = { ...files }, result = JSON.parse(source['result.json'].toString()), strategy = result.strategy
      const path = `${strategy}/comparison.json`, comp = JSON.parse(source[path].toString()), pruning = comp.cost_pruning
      const ref = pruning.decisions[0].artifact, decisionPath = `${strategy}/${ref.path}`
      if (change === 'pool_model') source['pool/outside.json'] = Buffer.concat([source['pool/outside.json'], Buffer.from(' ')])
      else if (change === 'raw_decision') source[decisionPath] = Buffer.concat([source[decisionPath], Buffer.from(' ')])
      else {
        if (change === 'physical_promotion') pruning.unevaluated_physical_feasibility = 'infeasible'
        else {
          const edits = change === 'future_rows' ? { evaluated_candidate_ids_before: '["baseline"]' } : { action: '"skip_cost_dominated"' }
          const raw = changed(source[decisionPath], edits, 'decision_hash')
          if (change === 'decision_action') pruning.decisions[0].action = 'skip_cost_dominated'
          ref.byte_length = raw.byteLength; ref.sha256 = `sha256:${createHash('sha256').update(raw).digest('hex')}`
          source[decisionPath] = Buffer.from(raw)
        }
        source[path] = Buffer.from(changed(source[path], { cost_pruning: JSON.stringify(pruning) }, 'report_hash'))
        result.arms[strategy].comparison_hash = JSON.parse(source[path].toString()).report_hash
        result.arms[strategy].cost_pruning = pruning
        source['result.json'] = Buffer.from(changed(source['result.json'], { arms: JSON.stringify(result.arms) }, 'report_hash'))
      }
      await expect(validateRcControlSearch(source['result.json'], async p => source[p])).rejects.toThrow()
    })
  }
}
for (const [id, files] of Object.entries(standaloneLayouts)) {
  test(`RC layout standalone validates original ${id}`, async () => {
    const requested:string[]=[]
    const review=await validateRcControlSearch(files['result.json'],async p=>{ requested.push(p); if (!files[p]) throw new Error('missing'); return files[p] })
    const strategy=id.endsWith('price_order')?'price_order':'learned_order'
    expect(Object.keys(review.designs)).toEqual([strategy])
    expect(review.report.strategy).toBe(strategy)
    expect(review.report.oracle).toBeNull()
    expect(review.costOptimality.status).toBe('oracle_not_run')
    expect(review.designs[strategy].report.selected_candidate_id).toBe(id.startsWith('b3')?'middle':strategy==='price_order'?null:'large')
    expect(review.designs[strategy].report).toEqual(JSON.parse(files[`${strategy}/comparison.json`].toString()))
    expect(requested.includes('policy.json')).toBe(strategy==='learned_order')
    expect(requested.includes('historical-training.json')).toBe(strategy==='learned_order')
  })
  for (const change of ['timing','strategy','coverage','checkpoint']) test(`RC layout standalone rejects ${id} ${change}`,async()=>{
    let raw:Uint8Array=files['result.json']
    if(change==='timing') raw=changed(raw,{timing_scope:JSON.stringify('both_arms')},'report_hash')
    if(change==='strategy') raw=changed(raw,{strategy:JSON.stringify('exhaustive_oracle')},'report_hash')
    if(change==='coverage') raw=changed(raw,{candidate_coverage_audit:'{}'},'report_hash')
    await expect(validateRcControlSearch(raw,async p=>change==='checkpoint'&&p.endsWith('/checkpoint.json')?Buffer.concat([files[p],Buffer.from(' ')]):files[p])).rejects.toThrow()
  })
}

import { stagedFiles } from './layoutStagedFixture'
test('RC staged layout validates prefix originals and includes all work', async () => {
  const review = await validateRcControlSearch(stagedFiles['result.json'], async path => stagedFiles[path])
  expect(review.report.arms.price_order.selected_candidate_id).toBe('middle')
  expect(review.report.arms.price_order.execution_work.known_counters.attempted_step_count).toBe(32)
  expect(review.prefixes?.small.decision.action).toBe('reject_history_maximum')
  expect(review.prefixes?.middle.decision.action).toBe('execute_full_reference')
  expect(Object.keys(review.designs.price_order.models)).toEqual(['baseline', 'middle'])
  expect(review.costOptimality).toBeNull()
})
for (const role of ['request', 'row', 'decision', 'baseline/model', 'baseline/result', 'baseline/checkpoint', 'baseline/verification']) {
  test(`RC staged layout rejects changed prefix ${role}`, async () => {
    const path = `price_order/prefix/small/${role}.json`
    await expect(validateRcControlSearch(stagedFiles['result.json'], async p => p === path ? Buffer.concat([stagedFiles[p], Buffer.from(' ')]) : stagedFiles[p])).rejects.toThrow()
  })
}
for (const change of ['action', 'model', 'acceptance', 'violations', 'target_count', 'accounting', 'policy']) {
  test(`RC staged layout rejects rehashed ${change}`, async () => {
    const files = { ...stagedFiles }, report = JSON.parse(files['result.json'].toString()), plan = JSON.parse(files['plan.json'].toString())
    const comparison = JSON.parse(files['price_order/comparison.json'].toString()), info = comparison.prefix_screening
    const record = info.decisions[0], path = `price_order/${record.artifact.path}`
    const edits: Record<string, string> = {}
    if (change === 'action') { edits.action = JSON.stringify('execute_full_reference'); record.action = 'execute_full_reference' }
    if (change === 'model') edits.model_checksum = JSON.stringify(`sha256:${'0'.repeat(64)}`)
    if (change === 'acceptance') edits.full_history_acceptance = 'true'
    if (change === 'violations') edits.history_maximum_violations = '[]'
    if (change === 'target_count') edits.prefix_target_count = '1'
    const raw = changed(files[path], edits, 'decision_hash'); files[path] = Buffer.from(raw)
    record.artifact = { ...record.artifact, sha256: `sha256:${createHash('sha256').update(raw).digest('hex')}`, byte_length: raw.byteLength }
    files['price_order/comparison.json'] = Buffer.from(changed(files['price_order/comparison.json'], { prefix_screening: JSON.stringify(info) }, 'report_hash'))
    const comparisonHash = JSON.parse(files['price_order/comparison.json'].toString()).report_hash
    report.arms.price_order.comparison_hash = comparisonHash; report.arms.price_order.prefix_screening = info
    if (change === 'accounting') report.arms.price_order.execution_work = info.full_reference_execution_work
    const reportEdits: Record<string, string> = { arms: JSON.stringify(report.arms) }
    if (change === 'policy') {
      plan.prefix_screening.terminal_limits_used = true
      files['plan.json'] = Buffer.from(changed(files['plan.json'], { prefix_screening: JSON.stringify(plan.prefix_screening) }, 'plan_hash'))
      reportEdits.plan_hash = JSON.stringify(JSON.parse(files['plan.json'].toString()).plan_hash)
      reportEdits.prefix_screening = JSON.stringify(plan.prefix_screening)
    }
    files['result.json'] = Buffer.from(changed(files['result.json'], reportEdits, 'report_hash'))
    await expect(validateRcControlSearch(files['result.json'], async p => files[p])).rejects.toThrow()
  })
}

test('RC staged layout keeps full acceptance separate from unavailable prefix verification', async () => {
  const files = { ...stagedFiles }, folder = 'price_order/prefix/middle', comparisonPath = 'price_order/comparison.json'
  const replaceMembers = (raw: Uint8Array, edits: Record<string, string>) => {
    const members = new Map([...fields(new TextDecoder().decode(raw))].map(([k, v]) => [k, v.value]))
    for (const [k, v] of Object.entries(edits)) members.set(k, v)
    return Buffer.from(`{${[...members].sort(([a], [b]) => a < b ? -1 : 1).map(([k, v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`)
  }
  const ref = (path: string, raw: Buffer) => ({ path, byte_length: raw.byteLength, sha256: `sha256:${createHash('sha256').update(raw).digest('hex')}` })
  const row = JSON.parse(files[`${folder}/row.json`].toString())
  files[`${folder}/baseline/verification.json`] = replaceMembers(files[`${folder}/baseline/verification.json`], { solver_replay_performed: 'false', errors: '["simulated verification failure"]' })
  row.artifacts.verification = ref('baseline/verification.json', files[`${folder}/baseline/verification.json`])
  files[`${folder}/row.json`] = replaceMembers(files[`${folder}/row.json`], { artifacts: JSON.stringify(row.artifacts), full_reference_verification_pass: 'false', selection_eligible: 'false', status: '"verification_blocked"', performance: 'null', screens: 'null', failure: '{"phase":"verification","kind":"simulated"}' })
  files[`${folder}/decision.json`] = Buffer.from(changed(files[`${folder}/decision.json`], { prefix_verified: 'false', prefix_row: JSON.stringify(ref('row.json', files[`${folder}/row.json`])) }, 'decision_hash'))
  const comparison = JSON.parse(files[comparisonPath].toString())
  comparison.prefix_screening.decisions.find((d: any) => d.candidate_id === 'middle').artifact = ref('prefix/middle/decision.json', files[`${folder}/decision.json`])
  files[comparisonPath] = Buffer.from(changed(files[comparisonPath], { prefix_screening: JSON.stringify(comparison.prefix_screening) }, 'report_hash'))
  const report = JSON.parse(files['result.json'].toString())
  report.arms.price_order.prefix_screening = comparison.prefix_screening
  report.arms.price_order.comparison_hash = JSON.parse(files[comparisonPath].toString()).report_hash
  files['result.json'] = Buffer.from(changed(files['result.json'], { arms: JSON.stringify(report.arms) }, 'report_hash'))
  const review = await validateRcControlSearch(files['result.json'], async path => files[path])
  expect(review.prefixes?.middle.decision.prefix_verified).toBe(false)
  expect(review.prefixes?.middle.decision.action).toBe('execute_full_reference')
  expect(review.designs.price_order.report.selected_candidate_id).toBe('middle')
  expect(review.designs.price_order.report.rows.find((r: any) => r.candidate_id === 'middle').full_reference_verification_pass).toBe(true)
})
