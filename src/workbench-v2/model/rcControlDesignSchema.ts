import { longitudinalSteelArea } from './rcSteelLayers'
import { check, same, selfHash, type RcObject } from './rcJobSchema'

const SCOPE = 'gross_concrete_and_straight_authored_longitudinal_rebar.v1'
const EXCLUDED = ['transverse_reinforcement', 'laps_anchorage_hooks', 'waste', 'formwork', 'labor', 'fabrication', 'transport', 'tax']
const QUANTITIES = ['gross_concrete_volume_m3', 'longitudinal_rebar_volume_m3', 'longitudinal_rebar_mass_kg']
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const close = (a: unknown, b: number): boolean => num(a) && Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(b))
const preciseClose = (a: unknown, b: number): boolean => num(a) && num(b)
  && Math.abs(a - b) <= 4 * Number.EPSILON * Math.max(Number.MIN_VALUE, Math.abs(a), Math.abs(b))
function compensatedSum(values: number[]): number {
  let total = 0, correction = 0
  for (const value of values) {
    const next = total + value
    correction += Math.abs(total) >= Math.abs(value) ? (total - next) + value : (value - next) + total
    total = next
  }
  return total + correction
}

/** Geometry validation accepts an explicit trusted checksum, rather than a study artifact role. */
export async function verifyRcQuantityGeometry(q: RcObject, model: RcObject, quantityRaw: string, modelChecksum: string, strict = false): Promise<void> {
  const matches = strict ? preciseClose : close
  check(q && q.schema_version === 'public-rc-fiber-member-quantities.v1' && q.scope === SCOPE && q.detailed_takeoff === false
    && same(q.excluded_items, EXCLUDED) && q.rebar_density_kg_per_m3 === 7850 && q.model_checksum === modelChecksum, 'study_quantity_scope_invalid')
  await selfHash(quantityRaw, q, 'quantity_hash')
  check(Array.isArray(q.members) && q.members.length === model.elements.length && new Set(q.members.map((m: RcObject) => m.member_id)).size === q.members.length, 'study_member_count_invalid')
  const totals: RcObject = Object.fromEntries(QUANTITIES.map(k => [k, 0]))
  const terms: Record<string, number[]> = Object.fromEntries(QUANTITIES.map(k => [k, []]))
  for (const member of model.elements) {
    const section = model.sections.find((s: RcObject) => s.id === member.section)
    const nodes = member.nodes.map((id: string) => model.nodes.find((n: RcObject) => n.id === id))
    check(nodes.length === 2 && nodes.every(Boolean) && section, 'study_geometry_invalid')
    const length = Math.hypot(...nodes[0].coordinates.map((v: number, i: number) => v - nodes[1].coordinates[i]))
    const volume = length * section.width_m * section.depth_m
    const rebar = length * longitudinalSteelArea(section)
    const values = [volume, rebar, rebar * 7850]
    const actual = q.members.find((m: RcObject) => m.member_id === member.id)
    check(actual && actual.section_id === member.section && matches(actual.length_m, length), 'study_member_identity_invalid')
    QUANTITIES.forEach((key, i) => { check(matches(actual[key], values[i]), 'study_member_quantity_invalid'); totals[key] += values[i]; terms[key].push(values[i]) })
  }
  QUANTITIES.forEach(key => check(matches(q.totals[key], strict ? compensatedSum(terms[key]) : totals[key]), 'study_quantity_total_invalid'))
}

/** Declared material prices never acquire quote or savings authority. */
export function verifyRcQuantityEstimate(q: RcObject, price: RcObject | null, estimate: RcObject | null, priceTableHash: string | null, strict = false): void {
  const matches = strict ? preciseClose : close
  if (price === null) { check(estimate === null, 'study_unpriced_estimate'); return }
  const total = strict ? compensatedSum(q.members.map((member: RcObject) =>
    member.gross_concrete_volume_m3 * price.concrete_per_m3 + member.longitudinal_rebar_mass_kg * price.rebar_per_kg))
    : q.totals.gross_concrete_volume_m3 * price.concrete_per_m3 + q.totals.longitudinal_rebar_mass_kg * price.rebar_per_kg
  check(estimate && estimate.scope === SCOPE && estimate.verified_quote === false && estimate.confirmed_currency_savings === false
    && same(estimate.excluded_items, EXCLUDED) && estimate.quantity_hash === q.quantity_hash && estimate.price_table_hash === priceTableHash
    && estimate.currency === price.currency && matches(estimate.total, total), 'study_estimate_invalid')
  check(Array.isArray(estimate.members) && estimate.members.length === q.members.length
    && new Set(estimate.members.map((m: RcObject) => m.member_id)).size === q.members.length, 'study_member_estimate_count_invalid')
  for (const member of q.members) {
    const cost = estimate.members.find((m: RcObject) => m.member_id === member.member_id)
    check(cost && same(Object.keys(cost).sort(), ['concrete', 'longitudinal_rebar', 'member_id'])
      && matches(cost.concrete, member.gross_concrete_volume_m3 * price.concrete_per_m3)
      && matches(cost.longitudinal_rebar, member.longitudinal_rebar_mass_kg * price.rebar_per_kg), 'study_member_estimate_invalid')
  }
}

