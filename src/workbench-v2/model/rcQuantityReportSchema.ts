import { sha256Bytes, sha256Hex } from './checksum'
import { verifyRcQuantityEstimate, verifyRcQuantityGeometry } from './rcControlDesignSchema'
import { validRcPriceMetadata } from './rcPriceMetadata'
import { check, document, fields, object, same, selfHash, type RcObject, type RcQuantityReportSource } from './rcJobSchema'

export const RC_QUANTITY_REPORT_MAX_BYTES = 4 * 1024 * 1024
export const RC_QUANTITY_REPORT_SCHEMA = 'durable-rc-fiber-quantity-price-report.v1'
export const RC_QUANTITY_REPORT_CLAIM_BOUNDARY = 'Geometry quantities and caller-declared material prices for the referenced successful durable RC job only. No fresh solve or verification is performed. Structural authority remains with the original result and worker evidence. Gross concrete and straight authored longitudinal bars exclude detailing and the listed cost items; this is not a verified quote, design approval, independent physical validation, or release qualification.'
const HASH = /^sha256:[a-f0-9]{64}$/
const JOB_ID = /^job_[a-f0-9]{32}$/
const REPORT_ID = /^rcq_[a-f0-9]{64}$/
const TENANT = /^[\x21-\x7e]{1,256}$/
const PRICES = ['as_of', 'concrete_per_m3', 'currency', 'rebar_per_kg', 'source']
const QUANTITY_KEYS = ['gross_concrete_volume_m3', 'longitudinal_rebar_volume_m3', 'longitudinal_rebar_mass_kg']
const exact = (value: unknown, keys: string[], code: string): RcObject => {
  const row = object(value)
  check(same(Object.keys(row).sort(), [...keys].sort()), code)
  return row
}
const natural = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export interface RcQuantityReportReference {
  schema_version: 'durable-rc-fiber-quantity-report-reference.v1'
  tenant_id: string
  job_id: string
  report_id: string
  revision: number
  content_hash: string
  byte_length: number
  media_type: 'application/json'
  created_at: string
}
export interface RcQuantityReportIndex {
  schema_version: 'durable-rc-fiber-quantity-report-index.v1'
  tenant_id: string
  job_id: string
  reports: RcQuantityReportReference[]
  next_after_revision: number
}
export interface RcDeclaredPrices {
  concrete_per_m3: number
  rebar_per_kg: number
  currency: string
  as_of: string
  source: string
}
export interface RcQuantityReportReview {
  report_id: string
  content_hash: string
  report_hash: string
  revision: number | null
  bindings: RcObject
  quantities: RcObject
  declared_prices: RcDeclaredPrices | null
  price_table_hash: string | null
  material_estimate: RcObject | null
  claim_boundary: string
}
export interface RcQuantityIdentity { tenant_id: string; job_id: string }

/** Index entries are discovery identities, never structural-result authority. */
export function parseRcQuantityReportReference(value: unknown, expected?: RcQuantityIdentity): RcQuantityReportReference {
  const row = exact(value, ['schema_version', 'tenant_id', 'job_id', 'report_id', 'revision', 'content_hash', 'byte_length', 'media_type', 'created_at'], 'quantity_reference_fields_invalid')
  check(row.schema_version === 'durable-rc-fiber-quantity-report-reference.v1'
    && typeof row.tenant_id === 'string' && TENANT.test(row.tenant_id)
    && typeof row.job_id === 'string' && JOB_ID.test(row.job_id)
    && typeof row.report_id === 'string' && REPORT_ID.test(row.report_id)
    && typeof row.content_hash === 'string' && HASH.test(row.content_hash)
    && row.report_id === `rcq_${row.content_hash.slice(7)}`
    && natural(row.revision) && row.revision >= 1
    && natural(row.byte_length) && row.byte_length > 0 && row.byte_length <= RC_QUANTITY_REPORT_MAX_BYTES
    && row.media_type === 'application/json'
    && typeof row.created_at === 'string' && row.created_at.length > 0 && row.created_at.length <= 128
    && Number.isFinite(Date.parse(row.created_at)), 'quantity_reference_invalid')
  if (expected) check(row.tenant_id === expected.tenant_id && row.job_id === expected.job_id, 'quantity_reference_identity_invalid')
  return row as RcQuantityReportReference
}

export function parseRcQuantityReportIndex(value: unknown, expected?: RcQuantityIdentity & { after_revision?: number; limit?: number }): RcQuantityReportIndex {
  const row = exact(value, ['schema_version', 'tenant_id', 'job_id', 'reports', 'next_after_revision'], 'quantity_index_fields_invalid')
  check(row.schema_version === 'durable-rc-fiber-quantity-report-index.v1'
    && typeof row.tenant_id === 'string' && TENANT.test(row.tenant_id)
    && typeof row.job_id === 'string' && JOB_ID.test(row.job_id)
    && Array.isArray(row.reports) && row.reports.length <= 100
    && natural(row.next_after_revision), 'quantity_index_invalid')
  if (expected) check(row.tenant_id === expected.tenant_id && row.job_id === expected.job_id, 'quantity_index_identity_invalid')
  const after = expected?.after_revision ?? 0, limit = expected?.limit ?? 100
  check(natural(after) && natural(limit) && limit >= 1 && limit <= 100 && row.reports.length <= limit, 'quantity_index_page_invalid')
  const reports = row.reports.map((item: unknown) => parseRcQuantityReportReference(item, { tenant_id: row.tenant_id, job_id: row.job_id }))
  let previous = after
  const ids = new Set<string>()
  for (const ref of reports) {
    check(ref.revision > previous && !ids.has(ref.report_id), 'quantity_index_order_invalid')
    previous = ref.revision; ids.add(ref.report_id)
  }
  check(row.next_after_revision === previous, 'quantity_index_cursor_invalid')
  return { ...row, reports } as RcQuantityReportIndex
}

export function parseRcDeclaredPrices(value: unknown): RcDeclaredPrices | null {
  if (value === null) return null
  const prices = exact(value, PRICES, 'quantity_price_fields_invalid')
  check(number(prices.concrete_per_m3) && prices.concrete_per_m3 >= 0
    && number(prices.rebar_per_kg) && prices.rebar_per_kg >= 0
    && validRcPriceMetadata(prices), 'quantity_prices_invalid')
  return prices as RcDeclaredPrices
}

/** Only a source returned by original durable validation is used by the worker. */
export async function validateRcQuantityReport(bytes: Uint8Array, source: RcQuantityReportSource, reference?: RcQuantityReportReference): Promise<RcQuantityReportReview> {
  check(bytes.byteLength > 0 && bytes.byteLength <= RC_QUANTITY_REPORT_MAX_BYTES, 'quantity_report_too_large')
  check(source.tenantId && TENANT.test(source.tenantId), 'quantity_source_tenant_unavailable')
  const identity = { tenant_id: source.tenantId, job_id: source.bindings.job_id }
  const ref = reference === undefined ? undefined : parseRcQuantityReportReference(reference, identity)
  const contentHash = await sha256Bytes(bytes)
  check(contentHash && HASH.test(contentHash), 'quantity_raw_hash_unavailable')
  if (ref) check(ref.byte_length === bytes.byteLength && ref.content_hash === contentHash, 'quantity_raw_reference_mismatch')
  const { raw, value: report } = document(bytes)
  exact(report, ['schema_version', 'bindings', 'structural_status', 'structural_authority', 'quantities', 'declared_prices', 'price_table_hash', 'material_estimate', 'derivation', 'claim_boundary', 'report_hash'], 'quantity_report_fields_invalid')
  await selfHash(raw, report, 'report_hash')
  check(report.schema_version === RC_QUANTITY_REPORT_SCHEMA && report.structural_status === 'succeeded'
    && same(report.bindings, source.bindings) && same(report.structural_authority, source.structuralAuthority), 'quantity_source_binding_invalid')
  check(report.claim_boundary === RC_QUANTITY_REPORT_CLAIM_BOUNDARY
    && same(report.derivation, {
      fresh_analysis_invocations: 0, fresh_verification_invocations: 0, new_structural_authority: false,
      rebar_density_basis: 'declared_takeoff_assumption_7850_kg_per_m3',
    }), 'quantity_claim_boundary_invalid')
  const quantities = exact(report.quantities, ['schema_version', 'model_checksum', 'scope', 'rebar_density_kg_per_m3', 'concrete_basis', 'reinforcement_basis', 'detailed_takeoff', 'excluded_items', 'members', 'totals', 'quantity_hash'], 'quantity_fields_invalid')
  check(quantities.concrete_basis === 'gross_section_volume_without_rebar_displacement_deduction'
    && quantities.reinforcement_basis === 'authored_longitudinal_bars_times_member_length'
    && Array.isArray(quantities.members) && quantities.members.length <= 64, 'quantity_basis_invalid')
  exact(quantities.totals, QUANTITY_KEYS, 'quantity_totals_fields_invalid')
  check(QUANTITY_KEYS.every(key => number(quantities.totals[key]) && quantities.totals[key] >= 0), 'quantity_totals_invalid')
  for (const [index, row] of quantities.members.entries()) {
    const member = exact(row, ['member_id', 'section_id', 'length_m', ...QUANTITY_KEYS], 'quantity_member_fields_invalid')
    check(member.member_id === source.model.elements[index]?.id, 'quantity_member_order_invalid')
    check(number(member.length_m) && member.length_m > 0
      && QUANTITY_KEYS.every(key => number(member[key]) && member[key] >= 0), 'quantity_member_values_invalid')
  }
  const members = fields(raw)
  await verifyRcQuantityGeometry(quantities, source.model, members.get('quantities')!.value, source.bindings.canonical_model_checksum, true)
  const prices = parseRcDeclaredPrices(report.declared_prices)
  if (prices === null) check(report.price_table_hash === null && report.material_estimate === null, 'quantity_unpriced_invalid')
  else {
    const priceFields = fields(members.get('declared_prices')!.value)
    priceFields.set('schema_version', { member: '"schema_version":"declared-rc-material-prices.v1"', value: '' })
    check(await sha256Hex(`{${[...priceFields.entries()].sort(([a], [b]) => a < b ? -1 : 1).map(([, value]) => value.member).join(',')}}`) === report.price_table_hash, 'quantity_price_hash_invalid')
    const estimate = exact(report.material_estimate, ['scope', 'currency', 'price_table_hash', 'quantity_hash', 'members', 'total', 'excluded_items', 'verified_quote', 'confirmed_currency_savings'], 'quantity_estimate_fields_invalid')
    check(Array.isArray(estimate.members) && estimate.members.length === quantities.members.length
      && estimate.members.every((row: RcObject, index: number) => row.member_id === quantities.members[index].member_id), 'quantity_estimate_order_invalid')
  }
  verifyRcQuantityEstimate(quantities, prices, report.material_estimate, report.price_table_hash, true)
  return {
    report_id: `rcq_${contentHash.slice(7)}`, content_hash: contentHash, report_hash: report.report_hash,
    revision: ref?.revision ?? null, bindings: report.bindings, quantities, declared_prices: prices,
    price_table_hash: report.price_table_hash, material_estimate: report.material_estimate, claim_boundary: report.claim_boundary,
  }
}
