import { check, type RcObject } from './rcJobSchema'

export const LEGACY_RANKING = 'feasibility_then_price.v1'
export const CHEAPER_BOUNDARY_RANKING = 'feasibility_then_cheaper_boundary.v1'

/** Reconstruct a frozen schedule from already validated predictions and prices. */
export function candidateRanking(predicted: RcObject[], strategy: string): { ordering: string[]; detail: RcObject | null } {
  check([LEGACY_RANKING, CHEAPER_BOUNDARY_RANKING].includes(strategy), 'search_ranking_strategy_invalid')
  const price = (a: RcObject, b: RcObject) => a.estimate - b.estimate || (a.candidate_id < b.candidate_id ? -1 : a.candidate_id > b.candidate_id ? 1 : 0)
  const legacy = [...predicted].sort((a, b) => a.ranking_tier - b.ranking_tier || price(a, b))
  if (strategy === LEGACY_RANKING) return { ordering: legacy.map(r => r.candidate_id), detail: null }
  const scores = new Map<string, number | null>(predicted.map(r => [r.candidate_id, r.predicted_screens === null ? null
    : Math.max(...Object.values(r.predicted_screens).map((s: any) => s.value > s.limit ? (s.value - s.limit) / s.value : 0))]))
  const seed = legacy.find(r => r.ranking_tier === 0)
  const challengers = seed ? legacy.filter(r => r.estimate < seed.estimate).sort((a, b) => {
    const left = scores.get(a.candidate_id)!, right = scores.get(b.candidate_id)!
    return Number(left !== null) - Number(right !== null) || (left ?? 0) - (right ?? 0) || price(a, b)
  }) : []
  const front = [...(seed ? [seed] : []), ...challengers]
  const frontIds = new Set(front.map(r => r.candidate_id)), challengerIds = new Set(challengers.map(r => r.candidate_id))
  return { ordering: [...front, ...legacy.filter(r => !frontIds.has(r.candidate_id))].map(r => r.candidate_id), detail: {
    strategy, predicted_feasible_seed_id: seed?.candidate_id ?? null,
    fallback_reason: seed ? null : 'no_predicted_feasible_seed', uncertainty_calibrated: false, physical_result_authority: false,
    rows: predicted.map(r => ({ candidate_id: r.candidate_id, relative_exceedance: scores.get(r.candidate_id),
      role: r.candidate_id === seed?.candidate_id ? 'predicted_feasible_seed'
        : challengerIds.has(r.candidate_id) ? scores.get(r.candidate_id) === null ? 'cheaper_unpredicted' : 'cheaper_predicted_boundary'
        : 'remaining_legacy_order' })),
  } }
}
