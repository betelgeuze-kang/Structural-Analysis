/** Controlled metadata conversion of existing originals, not new solver evidence. */
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { fields } from '../../src/workbench-v2/model/rcJobSchema'
export const standaloneRoot = 'tests/frontend/fixtures/rc-control-search-cost-no-oracle/'
export function rebind(raw: string, changes: Record<string, unknown>, field: string): Uint8Array {
  const values = new Map([...fields(raw)].map(([k, v]) => [k, v.value]))
  values.delete(field)
  // A full replacement object may still contain its previous self-hash.
  // Exclude it from the new digest just as for fields preserved from raw.
  for (const [k, v] of Object.entries(changes)) if (k !== field) values.set(k, JSON.stringify(v))
  const serialize = () => `{${[...values].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => `${JSON.stringify(k)}:${v}`).join(',')}}`
  values.set(field, JSON.stringify(`sha256:${createHash('sha256').update(serialize()).digest('hex')}`))
  return new TextEncoder().encode(serialize())
}
export function standaloneFixture(strategy: 'price_order' | 'learned_order') {
  const planRaw = readFileSync(standaloneRoot + 'plan.json', 'utf8'), originalPlan = JSON.parse(planRaw)
  const reportRaw = readFileSync(standaloneRoot + 'result.json', 'utf8'), originalReport = JSON.parse(reportRaw)
  const price = strategy === 'price_order'
  const plan = rebind(planRaw, { schema_version: 'experimental-rc-control-candidate-strategy-plan.v1', strategy,
    plans: { [strategy]: originalPlan.plans[strategy] },
    ...(price ? { predictions: [], policy_hash: null, training_report_hash: null, original_training_and_pool_models_disjoint: null } : {}),
  }, 'plan_hash')
  const audit = originalReport.candidate_coverage_audit
  audit.arms = { [strategy]: audit.arms[strategy] }
  for (const row of audit.candidates) row.shortlisted_by = row.shortlisted_by.filter((s: string) => s === strategy)
  const cost = originalReport.candidate_cost_optimality_audit
  cost.arms = { [strategy]: cost.arms[strategy] }
  const report = rebind(reportRaw, { schema_version: 'experimental-rc-control-candidate-strategy.v1', strategy,
    plan_hash: JSON.parse(new TextDecoder().decode(plan)).plan_hash,
    arms: { [strategy]: originalReport.arms[strategy] }, candidate_coverage_audit: price ? null : audit,
    candidate_cost_optimality_audit: cost,
    timing_scope: 'single_strategy_preparation_ranking_full_reference_and_IO_excluding_final_report_write',
    ...(price ? { historical_training_cost: null, ranking_wall_ns: 0 } : {}),
  }, 'report_hash')
  const read = (path: string): Uint8Array => path === 'result.json' ? report : path === 'plan.json' ? plan : new Uint8Array(readFileSync(standaloneRoot + path))
  return { plan, report, read }
}
