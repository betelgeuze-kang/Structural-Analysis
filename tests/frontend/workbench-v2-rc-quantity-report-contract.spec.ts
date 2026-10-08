import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { document, fields, rawValues, selfHash, type RcObject, type RcQuantityReportSource } from '../../src/workbench-v2/model/rcJobSchema'
import { loadRcJobReview } from '../../src/workbench-v2/model/rcJobReview'
import {
  parseRcDeclaredPrices, parseRcQuantityReportIndex, parseRcQuantityReportReference,
  RC_QUANTITY_REPORT_CLAIM_BOUNDARY, RC_QUANTITY_REPORT_MAX_BYTES, validateRcQuantityReport,
} from '../../src/workbench-v2/model/rcQuantityReportSchema'

// Small synthetic quantity/custody contracts only. No numerical response arrays,
// filesystem result fixtures, worker execution, or solver campaigns are needed.
const digest = (value: string | Uint8Array) => `sha256:${createHash('sha256').update(value).digest('hex')}`
const bytes = (raw: string) => new TextEncoder().encode(raw)
const h = (letter: string) => `sha256:${letter.repeat(64)}`
function canonical(value: any): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`
  return JSON.stringify(value)
}
function encode(values: Map<string, string>): string {
  return `{${[...values].sort(([a], [b]) => a < b ? -1 : 1).map(([key, value]) => `${JSON.stringify(key)}:${value}`).join(',')}}`
}
function edit(raw: string, path: (string | number)[], value: string): string {
  if (!path.length) return value
  const [key, ...rest] = path
  if (typeof key === 'number') {
    const rows = rawValues(raw); rows[key] = edit(rows[key], rest, value); return `[${rows.join(',')}]`
  }
  const members = new Map([...fields(raw)].map(([key, row]) => [key, row.value]))
  members.set(key, rest.length ? edit(members.get(key)!, rest, value) : value)
  return encode(members)
}
function rehash(raw: string, key: string): string {
  const members = new Map([...fields(raw)].map(([key, row]) => [key, row.value])); members.delete(key)
  members.set(key, JSON.stringify(digest(encode(members))))
  return encode(members)
}
const model = {
  nodes: [{ id: 'N1', coordinates: [0, 0, 0] }, { id: 'N2', coordinates: [2, 0, 0] }],
  elements: [{ id: 'M1', section: 'S1', nodes: ['N1', 'N2'] }],
  sections: [{ id: 'S1', width_m: 0.3, depth_m: 0.5, cover_m: 0.05,
    bar_area_m2: 0.0002, top_bar_count: 2, bottom_bar_count: 2 }],
}
const excluded = ['transverse_reinforcement', 'laps_anchorage_hooks', 'waste', 'formwork', 'labor', 'fabrication', 'transport', 'tax']
const scope = 'gross_concrete_and_straight_authored_longitudinal_rebar.v1'
const authority = {
  design_authority: false, experimental_small_displacement_rc_control: true,
  independent_execution_authentication: false, independent_physical_validation: false,
  production_promotion_eligible: false, public_j1_j5_authority: false,
  release_approved: false, service_numerical_verification_performed: false,
  trusted_worker_verification_attestation: true, workbench_execution: false,
}
function source(checkpoint = true): RcQuantityReportSource {
  const ref = (role: string, letter: string) => ({ role, content_hash: h(letter), byte_length: 3, media_type: 'application/json' })
  return {
    tenantId: 'synthetic-companion', model: structuredClone(model), structuralAuthority: structuredClone(authority),
    bindings: {
      tenant_id: 'synthetic-companion', job_id: `job_${'a'.repeat(32)}`, completed_job_revision: 4,
      terminal_event_hash: h('a'), original_artifacts: {
        request: ref('request', 'b'), checkpoint: checkpoint ? ref('checkpoint', 'c') : null,
        result: ref('result', 'd'), evidence: ref('evidence', 'e'),
      },
      case_id: 'synthetic-only', source_revision: 'a'.repeat(40), source_revision_is_execution_attestation: false,
      canonical_model_checksum: h('1'), model_input_checksum: h('1'),
      compiler_profile: 'planar_serial_cantilever_explicit_rectangular_rc.v1', config_hash: h('2'),
      profile: 'bounded_rc_fiber_durable_chunk_execution.v1', numerical_request_hash: h('b'), resume_contract_hash: h('3'),
      durable_result_hash: h('4'), api_result_hash: h('5'), terminal_native_checkpoint_sha256: h('6'),
      terminal_native_checkpoint_byte_length: 17, worker_validation_report_hash: h('7'), receipt_hashes: [h('8')],
    },
  }
}
const declared = { concrete_per_m3: 10, rebar_per_kg: 2, currency: 'KRW', as_of: '2026-10-03', source: 'synthetic declared rates only' }
function report(original: RcQuantityReportSource, prices: RcObject | null = declared): string {
  const totals = { gross_concrete_volume_m3: 0.3, longitudinal_rebar_volume_m3: 0.0016, longitudinal_rebar_mass_kg: 12.56 }
  const qRaw = rehash(canonical({
    schema_version: 'public-rc-fiber-member-quantities.v1', model_checksum: original.bindings.canonical_model_checksum,
    scope, rebar_density_kg_per_m3: 7850, concrete_basis: 'gross_section_volume_without_rebar_displacement_deduction',
    reinforcement_basis: 'authored_longitudinal_bars_times_member_length', detailed_takeoff: false, excluded_items: excluded,
    members: [{ member_id: 'M1', section_id: 'S1', length_m: 2, ...totals }], totals,
  }), 'quantity_hash')
  const quantities = JSON.parse(qRaw)
  const priceTableHash = prices === null ? null : digest(canonical({ schema_version: 'declared-rc-material-prices.v1', ...prices }))
  const materialEstimate = prices === null ? null : {
    scope, currency: prices.currency, price_table_hash: priceTableHash, quantity_hash: quantities.quantity_hash,
    members: [{ member_id: 'M1', concrete: totals.gross_concrete_volume_m3 * prices.concrete_per_m3,
      longitudinal_rebar: totals.longitudinal_rebar_mass_kg * prices.rebar_per_kg }],
    total: totals.gross_concrete_volume_m3 * prices.concrete_per_m3 + totals.longitudinal_rebar_mass_kg * prices.rebar_per_kg,
    excluded_items: excluded, verified_quote: false, confirmed_currency_savings: false,
  }
  return rehash(canonical({
    schema_version: 'durable-rc-fiber-quantity-price-report.v1', bindings: original.bindings,
    structural_status: 'succeeded', structural_authority: original.structuralAuthority, quantities,
    declared_prices: prices, price_table_hash: priceTableHash, material_estimate: materialEstimate,
    derivation: { fresh_analysis_invocations: 0, fresh_verification_invocations: 0, new_structural_authority: false,
      rebar_density_basis: 'declared_takeoff_assumption_7850_kg_per_m3' }, claim_boundary: RC_QUANTITY_REPORT_CLAIM_BOUNDARY,
  }), 'report_hash')
}
function reference(raw: string, revision = 1) {
  return { schema_version: 'durable-rc-fiber-quantity-report-reference.v1', tenant_id: 'synthetic-companion',
    job_id: `job_${'a'.repeat(32)}`, report_id: `rcq_${digest(raw).slice(7)}`, revision,
    content_hash: digest(raw), byte_length: bytes(raw).byteLength, media_type: 'application/json', created_at: '2026-10-03T00:00:00+00:00' }
}
async function verify(raw: string, original = source(), revision = 1) {
  return validateRcQuantityReport(bytes(raw), original, parseRcQuantityReportReference(reference(raw, revision)))
}
async function validHash(raw: string) {
  const doc = document(bytes(raw)); await selfHash(doc.raw, doc.value, 'report_hash')
}

test('null prices preserve quantities while explicit zero prices produce a saved zero estimate', async () => {
  const unpriced = await verify(report(source(), null))
  expect(unpriced.declared_prices).toBeNull(); expect(unpriced.material_estimate).toBeNull()
  const zero = await verify(report(source(), { ...declared, concrete_per_m3: 0, rebar_per_kg: 0 }))
  expect(zero.material_estimate?.total).toBe(0); expect(zero.declared_prices?.concrete_per_m3).toBe(0)
  expect(zero.quantities).toEqual(unpriced.quantities)
  expect(zero.bindings).toEqual(unpriced.bindings)
})
test('a valid changed price is a distinct immutable revision with unchanged original custody', async () => {
  const original = source(), before = structuredClone(original)
  const first = await verify(report(original), original)
  const next = await verify(report(original, { ...declared, rebar_per_kg: 4 }), original, 2)
  expect(next.report_id).not.toBe(first.report_id); expect(next.price_table_hash).not.toBe(first.price_table_hash)
  expect(next.revision).toBe(2); expect(next.bindings).toEqual(first.bindings); expect(next.quantities).toEqual(first.quantities)
  expect(original).toEqual(before)
  expect(next).not.toHaveProperty('response_history')
})
for (const [name, price] of [
  ['negative', { ...declared, rebar_per_kg: -1 }], ['boolean', { ...declared, concrete_per_m3: false }],
  ['invalid calendar', { ...declared, as_of: '2026-02-30' }], ['blank source', { ...declared, source: '  ' }],
  ['extra authority', { ...declared, verified_quote: true }], ['missing field', { concrete_per_m3: 0 }],
] as const) test(`declared price rejects ${name}`, () => { expect(() => parseRcDeclaredPrices(price)).toThrow('rc_review_') })

for (const [name, path, value] of [
  ['tenant', ['tenant_id'], 'another-tenant'], ['job', ['job_id'], `job_${'b'.repeat(32)}`],
  ['revision', ['completed_job_revision'], 5], ['event', ['terminal_event_hash'], h('b')],
  ['source', ['source_revision'], 'b'.repeat(40)], ['attestation', ['source_revision_is_execution_attestation'], true],
  ['config', ['config_hash'], h('a')], ['compiler', ['compiler_profile'], 'wrong-profile'],
  ['model', ['canonical_model_checksum'], h('a')], ['model input', ['model_input_checksum'], h('a')],
  ['profile', ['profile'], 'wrong-profile'], ['resume', ['resume_contract_hash'], h('a')],
  ['numerical request', ['numerical_request_hash'], h('a')], ['durable result', ['durable_result_hash'], h('a')],
  ['api result', ['api_result_hash'], h('a')], ['validation report', ['worker_validation_report_hash'], h('a')],
  ['receipt', ['receipt_hashes'], [h('a')]], ['native checkpoint', ['terminal_native_checkpoint_sha256'], h('a')],
  ['native bytes', ['terminal_native_checkpoint_byte_length'], 18],
  ['request ref', ['original_artifacts', 'request', 'content_hash'], h('a')],
  ['result ref', ['original_artifacts', 'result', 'byte_length'], 4],
  ['evidence ref', ['original_artifacts', 'evidence', 'content_hash'], h('a')],
  ['service checkpoint ref', ['original_artifacts', 'checkpoint'], null],
] as Array<[string, string[], unknown]>) test(`coherently rehashed report rejects wrong ${name} custody`, async () => {
  const raw = rehash(edit(report(source()), ['bindings', ...path], canonical(value)), 'report_hash')
  await validHash(raw); await expect(verify(raw)).rejects.toThrow('quantity_source_binding_invalid')
})
test('nullable service checkpoint remains separate from the terminal native checkpoint', async () => {
  const original = source(false), raw = report(original)
  const accepted = await verify(raw, original)
  expect(accepted.bindings.original_artifacts.checkpoint).toBeNull()
  expect(accepted.bindings.terminal_native_checkpoint_sha256).toBe(h('6'))
  const forged = rehash(edit(raw, ['bindings', 'original_artifacts', 'checkpoint'], canonical({
    role: 'checkpoint', content_hash: h('6'), byte_length: 17, media_type: 'application/json',
  })), 'report_hash')
  await expect(verify(forged, original)).rejects.toThrow('quantity_source_binding_invalid')
})
test('unknown authenticated tenant blocks only companion verification', async () => {
  const original = source(), raw = report(original); original.tenantId = null
  await expect(verify(raw, original)).rejects.toThrow('quantity_source_tenant_unavailable')
})
test('quantity and estimate coherent rehash cannot replace trusted model geometry', async () => {
  let raw = report(source())
  let qRaw = fields(raw).get('quantities')!.value
  qRaw = rehash(edit(edit(qRaw, ['members', 0, 'gross_concrete_volume_m3'], '3'), ['totals', 'gross_concrete_volume_m3'], '3'), 'quantity_hash')
  raw = edit(raw, ['quantities'], qRaw)
  raw = edit(raw, ['material_estimate', 'quantity_hash'], JSON.stringify(JSON.parse(qRaw).quantity_hash))
  raw = edit(raw, ['material_estimate', 'members', 0, 'concrete'], '30')
  raw = rehash(edit(raw, ['material_estimate', 'total'], '55.12'), 'report_hash')
  await validHash(raw); await expect(verify(raw)).rejects.toThrow('study_member_quantity_invalid')
})
test('small coherent quantity changes exceed only-rounding tolerance and are rejected', async () => {
  let raw = report(source())
  const qRaw = rehash(edit(fields(raw).get('quantities')!.value, ['members', 0, 'gross_concrete_volume_m3'], '0.3000000000001'), 'quantity_hash')
  raw = edit(edit(raw, ['quantities'], qRaw), ['material_estimate', 'quantity_hash'], JSON.stringify(JSON.parse(qRaw).quantity_hash))
  raw = rehash(raw, 'report_hash'); await validHash(raw)
  await expect(verify(raw)).rejects.toThrow('study_member_quantity_invalid')
})
test('changed declared price with coherent price and report hashes still requires recomputed estimate', async () => {
  let raw = report(source())
  const priceRaw = edit(fields(raw).get('declared_prices')!.value, ['rebar_per_kg'], '4')
  const priceHash = digest(edit(priceRaw, ['schema_version'], '"declared-rc-material-prices.v1"'))
  raw = edit(edit(raw, ['declared_prices'], priceRaw), ['price_table_hash'], JSON.stringify(priceHash))
  raw = rehash(edit(raw, ['material_estimate', 'price_table_hash'], JSON.stringify(priceHash)), 'report_hash')
  await validHash(raw); await expect(verify(raw)).rejects.toThrow('study_estimate_invalid')
})
for (const [path, value] of [
  [['structural_authority', 'design_authority'], true], [['derivation', 'fresh_analysis_invocations'], 1],
  [['derivation', 'new_structural_authority'], true], [['claim_boundary'], 'verified quote'],
  [['material_estimate', 'verified_quote'], true], [['material_estimate', 'confirmed_currency_savings'], true],
  [['quantities', 'concrete_basis'], 'net_takeoff'], [['quantities', 'unexpected_authority'], true],
] as Array<[string[], unknown]>) test(`coherently rehashed report rejects promoted ${path.join('.')}`, async () => {
  let raw = edit(report(source()), path, canonical(value))
  if (path[0] === 'quantities') raw = edit(raw, ['quantities'], rehash(fields(raw).get('quantities')!.value, 'quantity_hash'))
  raw = rehash(raw, 'report_hash'); await validHash(raw)
  await expect(verify(raw)).rejects.toThrow('rc_review_')
})
test('raw bytes, ID suffix and self hash have separate identities', async () => {
  const original = source(), raw = report(original), ref = reference(raw)
  const self = JSON.parse(raw).report_hash
  expect(self).not.toBe(ref.content_hash)
  await expect(validateRcQuantityReport(bytes(`${raw}\n`), original, parseRcQuantityReportReference(ref))).rejects.toThrow('quantity_raw_reference_mismatch')
  await expect(validateRcQuantityReport(bytes(raw), original, parseRcQuantityReportReference({ ...ref, content_hash: self, report_id: `rcq_${self.slice(7)}` }))).rejects.toThrow('quantity_raw_reference_mismatch')
  expect(() => parseRcQuantityReportReference({ ...ref, report_id: `rcq_${'b'.repeat(64)}` })).toThrow('quantity_reference_invalid')
})
test('producer float tokens remain hash-bound without JSON reserialization', async () => {
  const original = source()
  let raw = report(original, { ...declared, concrete_per_m3: 0, rebar_per_kg: 0 })
  const priceRaw = edit(edit(fields(raw).get('declared_prices')!.value, ['concrete_per_m3'], '0.0'), ['rebar_per_kg'], '0.0')
  const priceHash = digest(edit(priceRaw, ['schema_version'], '"declared-rc-material-prices.v1"'))
  raw = edit(edit(raw, ['declared_prices'], priceRaw), ['price_table_hash'], JSON.stringify(priceHash))
  raw = edit(raw, ['material_estimate', 'price_table_hash'], JSON.stringify(priceHash))
  const qRaw = rehash(edit(fields(raw).get('quantities')!.value, ['rebar_density_kg_per_m3'], '7850.0'), 'quantity_hash')
  raw = edit(edit(raw, ['quantities'], qRaw), ['material_estimate', 'quantity_hash'], JSON.stringify(JSON.parse(qRaw).quantity_hash))
  raw = rehash(raw, 'report_hash')
  expect((await verify(raw)).material_estimate?.total).toBe(0)
  await expect(verify(JSON.stringify(JSON.parse(raw)))).rejects.toThrow('logical_hash_mismatch')
})
test('strict JSON, bounded reports and exact field presence reject invalid companions', async () => {
  const raw = report(source())
  await expect(verify(raw.replace('"structural_status":', '"structural_status":"succeeded","structural_status":'))).rejects.toThrow('duplicate')
  await expect(validateRcQuantityReport(new Uint8Array(RC_QUANTITY_REPORT_MAX_BYTES + 1), source())).rejects.toThrow('quantity_report_too_large')
  const members = new Map([...fields(raw)].map(([key, value]) => [key, value.value])); members.delete('declared_prices')
  await expect(verify(rehash(encode(members), 'report_hash'))).rejects.toThrow('quantity_report_fields_invalid')
})
test('bounded revision index binds tenant/job, order, uniqueness and exact requested cursor', () => {
  const first = reference(report(source()), 1), second = reference(report(source(), null), 2)
  const index = { schema_version: 'durable-rc-fiber-quantity-report-index.v1', tenant_id: first.tenant_id,
    job_id: first.job_id, reports: [first, second], next_after_revision: 2 }
  const expected = { tenant_id: first.tenant_id, job_id: first.job_id, after_revision: 0, limit: 2 }
  expect(parseRcQuantityReportIndex(index, expected).reports).toHaveLength(2)
  expect(() => parseRcQuantityReportIndex(index, { ...expected, tenant_id: 'another-tenant' })).toThrow('quantity_index_identity_invalid')
  expect(() => parseRcQuantityReportIndex(index, { ...expected, limit: 1 })).toThrow('quantity_index_page_invalid')
  expect(() => parseRcQuantityReportIndex({ ...index, reports: [second, first] }, expected)).toThrow('quantity_index_order_invalid')
  expect(() => parseRcQuantityReportIndex({ ...index, reports: [first, { ...first, revision: 2 }] }, expected)).toThrow('quantity_index_order_invalid')
  expect(() => parseRcQuantityReportIndex({ ...index, next_after_revision: 3 }, expected)).toThrow('quantity_index_cursor_invalid')
  expect(parseRcQuantityReportIndex({ ...index, reports: [], next_after_revision: 2 }, { ...expected, after_revision: 2 }).next_after_revision).toBe(2)
})

test('host companion RPC errors preserve the initialized original review and exact-download RPC', async () => {
  const previousWorker = globalThis.Worker
  const calls: string[] = [], failures: string[] = []
  let terminated = false, initializedTenant: string | undefined
  class RpcWorker {
    onmessage: ((event: { data: any }) => void) | null = null
    onerror: (() => void) | null = null
    onmessageerror: (() => void) | null = null
    terminate() { terminated = true }
    postMessage(data: any) {
      calls.push(data.type)
      const respond = (response: any) => queueMicrotask(() => this.onmessage?.({ data: { id: data.id, ...response } }))
      if (data.type === 'initialize') {
        initializedTenant = data.tenantId
        respond({ value: { resultHash: h('4'), sourceRevision: 'a'.repeat(40), targets: [0.001],
          control: { node_id: 'N2', component: 'UY', unit: 'm' }, reservedInvocations: 2,
          confirmedInvocations: 2, knownCoreCalls: 1, knownNewtonIterations: 1, unknownWork: false, artifactRoles: ['result'] } })
      } else if (data.type === 'quantityReport') respond({ quantityError: 'rc_review_quantity_source_binding_invalid' })
      else if (data.type === 'epoch') respond({ value: { epoch: 1 } })
      else if (data.type === 'download') respond({ value: new Blob([bytes('{"original":1.0}')], { type: 'application/json' }) })
      else if (data.type === 'quantityDownload') respond({ quantityError: 'rc_review_quantity_download_unavailable' })
    }
  }
  globalThis.Worker = RpcWorker as unknown as typeof Worker
  let review: Awaited<ReturnType<typeof loadRcJobReview>> | undefined
  try {
    const ref = { role: 'request', content_hash: h('b'), byte_length: 2, media_type: 'application/json' }
    const job: any = { request: ref, checkpoint: null, result: { ...ref, role: 'result' }, evidence: { ...ref, role: 'evidence' } }
    const transport = { tenantId: 'synthetic-companion', get: async () => new Response('{}', { headers: { 'content-type': 'application/json' } }) }
    review = await loadRcJobReview(job, transport)
    review.onFailure(message => failures.push(message))
    await expect(review.verifyQuantityReport!(bytes('{}'))).rejects.toThrow('quantity_source_binding_invalid')
    await expect(review.downloadQuantityReport!(`rcq_${'a'.repeat(64)}`)).rejects.toThrow('quantity_download_unavailable')
    expect((await review.epoch(0)).epoch).toBe(1)
    expect(await (await review.download('result')).text()).toBe('{"original":1.0}')
    expect(initializedTenant).toBe('synthetic-companion')
    expect(calls.filter(call => call === 'initialize')).toHaveLength(1)
    expect(failures).toEqual([]); expect(terminated).toBe(false)
  } finally { review?.dispose(); globalThis.Worker = previousWorker }
})
