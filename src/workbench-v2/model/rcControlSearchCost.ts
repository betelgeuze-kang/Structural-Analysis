import type { RcObject } from './rcJobSchema'

/** Derive only after original models, quantities, prices and all design reports
 * have passed validateRcControlSearch's full artifact checks. */
export function costOptimality(plan: RcObject, comparisons: Record<string, RcObject>): RcObject {
  const pool: RcObject[] = plan.pool, oracle = comparisons.exhaustive_oracle ?? null
  const estimates = new Map<string, number>(pool.map(r => [r.candidate_id, r.material_estimate.total]))
  const requested = [...Object.keys(plan.history_limits), ...Object.keys(plan.material_limits), ...Object.keys(plan.terminal_limits ?? {}).map(k => `terminal_${k}`)].sort()
  const outcome = (r: RcObject): boolean | null => {
    if (!r.full_reference_verification_pass || !r.screens || !Object.keys(r.screens).length
      || JSON.stringify(Object.keys(r.screens).sort()) !== JSON.stringify(requested)
      || !Object.values(r.screens).every((s: any) => s && ['pass', 'fail'].includes(s.status))) return null
    return Object.values(r.screens).every((s: any) => s.status === 'pass')
  }
  const outcomes = new Map<string, boolean | null>(pool.map(r => [r.candidate_id, null]))
  if (oracle) for (const row of oracle.rows) outcomes.set(row.candidate_id, outcome(row))
  const unknown = pool.filter(r => outcomes.get(r.candidate_id) === null).map(r => r.candidate_id)
  const feasible = pool.filter(r => outcomes.get(r.candidate_id) === true).map(r => r.candidate_id)
  const status = !oracle ? 'oracle_not_run' : unknown.length ? 'oracle_incomplete' : !feasible.length ? 'no_feasible_candidate' : 'complete'
  const minimum = status === 'complete' ? Math.min(...feasible.map(c => estimates.get(c)!)) : null
  const winners = minimum === null ? null : feasible.filter(c => estimates.get(c) === minimum).sort()
  const arms: RcObject = {}
  for (const name of Object.keys(plan.plans)) {
    const selectedId: string | null = comparisons[name].selected_candidate_id
    const selectedEstimate = selectedId === null ? null : estimates.get(selectedId)!
    const armStatus = status !== 'complete' ? status : selectedId === null ? 'no_verified_selection'
      : outcomes.get(selectedId) !== true ? 'selection_not_confirmed_by_oracle' : 'compared'
    const gap = armStatus === 'compared' ? selectedEstimate! - minimum! : null
    const requestedIds = new Set(['baseline', ...plan.plans[name].shortlist])
    const missed = armStatus === 'compared' ? pool.filter(r => !requestedIds.has(r.candidate_id)
      && outcomes.get(r.candidate_id) === true && estimates.get(r.candidate_id)! < selectedEstimate!).map(r => r.candidate_id) : null
    arms[name] = { status: armStatus, selected_candidate_id: selectedId, selected_estimate: selectedEstimate,
      selected_minus_pool_minimum_estimate: gap, matches_pool_minimum: gap === null ? null : gap === 0,
      missed_cheaper_feasible_count: missed === null ? null : missed.length, missed_cheaper_feasible_candidate_ids: missed }
  }
  return { schema_version: 'rc-control-candidate-cost-optimality.v1', status,
    candidate_denominator: pool.length, baseline_included: true, price_table_hash: plan.price_table_hash,
    currency: pool[0].material_estimate.currency, quantity_scope: pool[0].material_estimate.scope,
    oracle_comparison_hash: oracle?.report_hash ?? null, oracle_unverifiable_candidate_ids: oracle ? unknown : null,
    pool_minimum_feasible_estimate: minimum, pool_minimum_feasible_candidate_ids: winners, arms,
    global_design_optimality_proved: false, confirmed_currency_savings: false, independent_physical_validation: false }
}
