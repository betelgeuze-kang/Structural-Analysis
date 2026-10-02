import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { fields, document, rawValues, selfHash } from '../../src/workbench-v2/model/rcJobSchema'
import { layoutFiles, layoutRead } from './layoutSearchFixture'
function changed(raw: Uint8Array, edits: Record<string,string>, key: string): Uint8Array {
  const values = new Map([...fields(new TextDecoder().decode(raw))].map(([k,v]) => [k,v.value]))
  values.delete(key); for (const [k,v] of Object.entries(edits)) values.set(k,v)
  const encode = () => `{${[...values].sort(([a],[b]) => a < b ? -1 : 1).map(([k,v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`
  values.set(key, JSON.stringify(`sha256:${createHash('sha256').update(encode()).digest('hex')}`))
  return new TextEncoder().encode(encode())
}
for (const clock of ['wall', 'cpu']) {
  test(`RC layout rejects rehashed training with erased parent ${clock} time`, async () => {
    const training = JSON.parse(layoutFiles['historical-training.json'].toString())
    if (clock === 'wall') training.wall_ns = training.label_generation_wall_ns = training.fit.wall_ns = 0
    else training.cpu_ns = training.fit.cpu_ns = 0
    const t = changed(layoutFiles['historical-training.json'], {
      wall_ns: JSON.stringify(training.wall_ns), cpu_ns: JSON.stringify(training.cpu_ns),
      label_generation_wall_ns: JSON.stringify(training.label_generation_wall_ns), fit: JSON.stringify(training.fit),
    }, 'report_hash')
    const p = changed(layoutFiles['plan.json'], { training_report_hash: JSON.stringify(document(t).value.report_hash) }, 'plan_hash')
    const r = changed(layoutFiles['result.json'], { plan_hash: JSON.stringify(document(p).value.plan_hash),
      historical_training_cost: new TextDecoder().decode(t) }, 'report_hash')
    for (const [bytes, field] of [[t, 'report_hash'], [p, 'plan_hash'], [r, 'report_hash']] as const) {
      const doc = document(bytes); await selfHash(doc.raw, doc.value, field)
    }
    await expect(validateRcControlSearch(r, async path => path === 'plan.json' ? p
      : path === 'historical-training.json' ? t : layoutRead(path))).rejects.toThrow('search_training_interval_invalid')
  })
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
import { portalSpanBytes, portalSpanRead } from './rcPortalLayoutSpanFixture'

test('two-fixed portal span fixture preserves 79 deterministic byte-exact originals', () => {
  const archive = readFileSync('tests/frontend/fixtures/rc-portal-layout-span-artifacts.json.gz')
  const manifestBytes = readFileSync('tests/frontend/fixtures/rc-portal-layout-span-manifest.json')
  expect(createHash('sha256').update(manifestBytes).digest('hex')).toBe('a7a152d37c7a8500b0b786215f5972f02f217e7b8ea405caa9771521837dd1de')
  const manifest = JSON.parse(manifestBytes.toString('utf8'))
  expect(manifest.producer_source_revision).toBe('e0146cd9b33fa7c02d2fd8a81ec31c177fb64dba')
  expect(manifest.execution_order).toEqual(['staged', 'full'])
  expect(archive.byteLength).toBe(2596579)
  expect(createHash('sha256').update(archive).digest('hex')).toBe('fc9c3ac52bf3cc233e8f07333b27b1f34f6fab414892097b5be6a2a395e16174')
  expect(archive.subarray(4, 8)).toEqual(Buffer.alloc(4)) // gzip mtime = 0
  const unpacked = gunzipSync(archive)
  expect(createHash('sha256').update(unpacked).digest('hex')).toBe('f4d366c7fbb24b155eae0de14439c4bc38bcc8e94f7d25a97cb47a7222c9800e')
  const files: Record<string, string> = JSON.parse(unpacked.toString('utf8'))
  const paths = Object.keys(files)
  expect(paths).toEqual([...paths].sort())
  expect(paths.filter(path => path.startsWith('staged/'))).toHaveLength(42)
  expect(paths.filter(path => path.startsWith('full/'))).toHaveLength(37)
  expect(Object.keys(manifest.originals)).toEqual(paths)
  const originals = createHash('sha256')
  let originalBytes = 0
  for (const path of paths) {
    const raw = Buffer.from(files[path], 'base64')
    expect(manifest.originals[path]).toEqual({ byte_length: raw.byteLength, sha256: createHash('sha256').update(raw).digest('hex') })
    const length = Buffer.alloc(8)
    length.writeBigUInt64BE(BigInt(raw.byteLength))
    originals.update(Buffer.from(path)).update(Buffer.from([0])).update(length).update(raw)
    originalBytes += raw.byteLength
  }
  expect(originalBytes).toBe(10871903)
  expect(originals.digest('hex')).toBe('9f4cd695244378eb7da37571a8de9be93f7727b0ba3165430b1f0ea9f3f855e4')
  for (const [name, ref] of Object.entries(manifest.new_input_files) as [string, any][]) {
    const raw = readFileSync(`examples/research/rc_internal_portal_20mm/${name}`)
    expect({ byte_length: raw.byteLength, sha256: createHash('sha256').update(raw).digest('hex') }).toEqual(ref)
  }
})

for (const run of ['staged', 'full'] as const) {
  test(`two-fixed portal span ${run} reviews original geometry and full-path records`, async () => {
    const review = await validateRcControlSearch(portalSpanBytes(run, 'result.json'), portalSpanRead(run))
    expect(review.report.source_revision).toBe('e0146cd9b33fa7c02d2fd8a81ec31c177fb64dba')
    expect(review.plan.control_request.experimental_two_fixed_endpoints).toBe(true)
    expect(review.plan.control_request.constant_nodal_loads).toHaveLength(2)
    expect(review.plan.control_request.targets_m).toEqual([-0.01, -0.02, 0.01])
    expect(review.plan.pool.map((row: any) => row.candidate_id)).toEqual([
      'baseline', 'shorter_span_360', 'longer_span_440',
    ])
    expect(review.report.arms.price_order.selected_candidate_id).toBe('shorter_span_360')
    expect(review.designs.price_order.models.shorter_span_360.nodes.find((node: any) => node.id === 'N4').coordinates[0]).toBe(3.6)
    expect(review.report.claims.net_savings_proved).toBe(false)
    const ids = review.designs.price_order.report.rows.map((row: any) => row.candidate_id)
    if (run === 'staged') {
      expect(ids).toEqual(['baseline', 'shorter_span_360'])
      expect(review.report.arms.price_order.cost_pruning.skipped_cost_dominated_candidate_ids).toEqual(['longer_span_440'])
      expect(review.report.arms.price_order.cost_pruning.unevaluated_physical_feasibility).toBe('unknown')
      expect(review.prefixes?.shorter_span_360.decision.action).toBe('execute_full_reference')
      expect(review.prefixes?.shorter_span_360.row.full_reference_verification_pass).toBe(true)
      expect(review.costOptimality).toBeNull()
    } else {
      expect(ids).toEqual(['baseline', 'shorter_span_360', 'longer_span_440'])
      expect(review.designs.price_order.models.longer_span_440.nodes.find((node: any) => node.id === 'N4').coordinates[0]).toBe(4.4)
      expect(review.designs.price_order.report.rows.every((row: any) => row.full_reference_verification_pass)).toBe(true)
    }
  })

  test(`two-fixed portal span ${run} rejects changed original result`, async () => {
    const target = run === 'staged'
      ? 'price_order/prefix/shorter_span_360/baseline/result.json'
      : 'price_order/longer_span_440/baseline/result.json'
    await expect(validateRcControlSearch(portalSpanBytes(run, 'result.json'), async path =>
      path === target
        ? Uint8Array.from(Buffer.concat([Buffer.from(portalSpanBytes(run, path)), Buffer.from(' ')]))
        : portalSpanBytes(run, path),
    )).rejects.toThrow()
  })
}

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

// New metadata-only pool mutations leave every numerical payload untouched.
function poolBindingMembers(raw: string, edits: Record<string, string>): string {
  const values = new Map([...fields(raw)].map(([key, value]) => [key, value.value]))
  for (const [key, value] of Object.entries(edits)) values.set(key, value)
  return `{${[...values].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, value]) => `${JSON.stringify(key)}:${value}`).join(',')}}`
}
function poolBindingMetadata(original: Record<string, Buffer>, mutate: (model: any, id: string) => void,
  control: Record<string, unknown> = {}): Record<string, Buffer> {
  const files = { ...original }, plan = document(files['plan.json'])
  const rows = rawValues(fields(plan.raw).get('pool')!.value)
  for (const [index, row] of plan.value.pool.entries()) {
    const model = document(files[row.model_artifact.path]), value = structuredClone(model.value)
    mutate(value, row.candidate_id)
    if (JSON.stringify(value) === JSON.stringify(model.value)) continue
    const edits = Object.fromEntries(Object.entries(value).filter(([key, v]) => JSON.stringify(v) !== JSON.stringify(model.value[key])).map(([key, v]) => [key, JSON.stringify(v)]))
    const bytes = Buffer.from(poolBindingMembers(model.raw, edits))
    files[row.model_artifact.path] = bytes
    const ref = { path: row.model_artifact.path, byte_length: bytes.byteLength, sha256: `sha256:${createHash('sha256').update(bytes).digest('hex')}` }
    const rowFields = fields(rows[index])
    const quantity = changed(Buffer.from(rowFields.get('quantities')!.value), { model_checksum: JSON.stringify(ref.sha256) }, 'quantity_hash')
    const estimate = poolBindingMembers(rowFields.get('material_estimate')!.value, { quantity_hash: JSON.stringify(document(quantity).value.quantity_hash) })
    rows[index] = poolBindingMembers(rows[index], { model_artifact: JSON.stringify(ref), quantities: new TextDecoder().decode(quantity), material_estimate: estimate })
  }
  const request = poolBindingMembers(fields(plan.raw).get('control_request')!.value, Object.fromEntries(Object.entries(control).map(([key, value]) => [key, JSON.stringify(value)])))
  files['plan.json'] = Buffer.from(changed(files['plan.json'], { pool: `[${rows.join(',')}]`, control_request: request }, 'plan_hash'))
  files['result.json'] = Buffer.from(changed(files['result.json'], { plan_hash: JSON.stringify(document(files['plan.json']).value.plan_hash) }, 'report_hash'))
  const changedPaths = Object.keys(files).filter(path => !files[path].equals(original[path]))
  expect(changedPaths.every(path => path === 'plan.json' || path === 'result.json' || path.startsWith('pool/'))).toBe(true)
  return files
}
function poolBindingRename(model: any, left: string, right: string): void {
  const remap = (id: string) => id === left ? right : id === right ? left : id
  model.nodes.forEach((node: any) => { node.id = remap(node.id) })
  model.elements.forEach((element: any) => { element.nodes = element.nodes.map(remap) })
  for (const row of [...model.loads, ...model.supports]) row.node = remap(row.node)
}
const poolBindingSeed = standaloneLayouts['b2-o0-price_order']
test('RC layout pool binding accepts rehashed ID rename with unchanged control meaning', async () => {
  const files = poolBindingMetadata(poolBindingSeed, (model, id) => {
    if (id === 'outside') for (const node of [...model.nodes]) poolBindingRename(model, node.id, `renamed_${node.id}`)
  })
  const review = await validateRcControlSearch(files['result.json'], async path => files[path])
  expect(review.plan.pool.some((row: any) => row.candidate_id === 'outside')).toBe(true)
  expect(review.designs.price_order.report).toEqual(document(poolBindingSeed['price_order/comparison.json']).value)
})
for (const [mode, seed] of [['full', poolBindingSeed], ['pruned', prunedLayouts.price], ['staged', stagedFiles]] as const) {
  test(`RC layout pool binding rejects unvisited control drift in ${mode}`, async () => {
    const rows = document(seed['price_order/comparison.json']).value.rows
    const unvisited = document(seed['plan.json']).value.pool.find((row: any) => !rows.some((visited: any) => visited.candidate_id === row.candidate_id))
    expect(unvisited).toBeTruthy()
    const files = poolBindingMetadata(seed, (model, id) => { if (id === unvisited.candidate_id) model.nodes.reverse() })
    const requested: string[] = []
    await expect(validateRcControlSearch(files['result.json'], async path => { requested.push(path); return files[path] }))
      .rejects.toThrow('layout_pool_control_binding_mismatch')
    expect(requested.some(path => path.startsWith('price_order/') || path.startsWith('learned_order/'))).toBe(false)
  })
}
const preload = [{ node_id: 'N2', FX_kN: -0, FY_kN: -10, MZ_kNm: 2 }]
const signedLoads = [{ node_id: 'N2', FX_kN: -5, FY_kN: 6, MZ_kNm: -7 }, { node_id: 'N1', FX_kN: 2, FY_kN: -3, MZ_kNm: 4 }]
const preloadRequest = (loads: unknown[]) => ({ schema_version: 'bounded-rc-fiber-direct-control-request.v2', constant_nodal_loads: loads })
const poolBindingCases: Array<[string, (model: any, id: string) => void, Record<string, unknown>, string | null]> = [
  ['non-control declaration permutation', (model, id) => { if (id === 'outside') [model.nodes[0], model.nodes[1]] = [model.nodes[1], model.nodes[0]] }, {}, null],
  ['translated geometry', (model, id) => { if (id === 'outside') model.nodes.forEach((node: any) => { node.coordinates[0] += 100; node.coordinates[1] -= 20 }) }, {}, null],
  ['common signed preload', () => {}, preloadRequest(preload), null],
  ['preload canonical node drift', (model, id) => { if (id === 'outside') poolBindingRename(model, 'N1', 'N2') }, preloadRequest(preload), 'layout_pool_control_binding_mismatch'],
  ['missing preload node', () => {}, preloadRequest([{ ...preload[0], node_id: 'missing' }]), 'layout_pool_preload_node_invalid'],
  ['control outside model', () => {}, { control_global_dof: 46 }, 'layout_pool_control_node_invalid'],
  ['rotational control', () => {}, { control_global_dof: 8 }, 'layout_pool_control_node_invalid'],
  ['multiple signed loads with declaration remap', (model, id) => { if (id === 'outside') [model.nodes[0], model.nodes[1]] = [model.nodes[1], model.nodes[0]] }, preloadRequest(signedLoads), null],
  ['multiple signed loads with node rank drift', (model, id) => { if (id === 'outside') poolBindingRename(model, 'N1', 'N2') }, preloadRequest(signedLoads), 'layout_pool_control_binding_mismatch'],
]
for (const [name, mutate, control, error] of poolBindingCases) {
  test(`RC layout pool binding metadata ${name}`, async () => {
    const files = poolBindingMetadata(poolBindingSeed, mutate, control), requested: string[] = []
    // Stop after pool admission; these altered requests have no new solver proof.
    const review = validateRcControlSearch(files['result.json'], async path => {
      requested.push(path)
      if (path.startsWith('price_order/')) throw new Error('metadata_pool_admission_complete')
      return files[path]
    })
    await expect(review).rejects.toThrow(error ?? 'metadata_pool_admission_complete')
    expect(requested.some(path => path.startsWith('price_order/'))).toBe(error === null)
  })
}
