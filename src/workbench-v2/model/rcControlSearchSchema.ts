import { sha256Bytes } from './checksum'
import { check, document, fields, rawValues, same, selfHash, type RcObject } from './rcJobSchema'
import { validateRcDesignStudy, verifyQuantities, type RcDesignReview, type StudyRead } from './rcControlDesignSchema'
import { costOptimality } from './rcControlSearchCost'

export const RC_SEARCH_ARMS = ['price_order', 'learned_order'] as const
const MAX = 2 * 1024 ** 2
const counters = ['attempted_step_count', 'known_linear_solve_count', 'known_newton_iteration_count', 'unknown_solver_work_attempt_count']
const nat = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const hash = (v: unknown) => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)
const id = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(v)
const keys = (v: RcObject, expected: readonly string[]) => same(Object.keys(v).sort(), [...expected].sort())
const claims = { physical_winner_requires_full_reference_and_screens: true, independent_generalization: false, net_savings_proved: false, confirmed_currency_savings: false, workbench_search_review_integrated: false }
export interface RcSearchReview {
  report: RcObject
  plan: RcObject
  designs: Record<string, RcDesignReview>
  costOptimality: RcObject
}
export function searchWork(rows: RcObject[]): RcObject {
  const invocations: RcObject[] = rows.flatMap(r => r.invocations)
  const totals: RcObject = Object.fromEntries(counters.map(k => [k, 0]))
  for (const invocation of invocations) {
    check(invocation.unknown_execution_work === false && invocation.work && keys(invocation.work, counters)
      && counters.every(k => nat(invocation.work[k])) && invocation.work.unknown_solver_work_attempt_count === 0, 'search_unknown_work')
    for (const k of counters) { totals[k] += invocation.work[k]; check(nat(totals[k]), 'search_work_overflow') }
  }
  return { known_counters: totals, unknown_work: false, api_invocation_count: invocations.length }
}
function coverage(plan: RcObject, oracle: RcObject | null): RcObject {
  const predictions = new Map<string, RcObject>(plan.predictions.map((p: RcObject) => [p.candidate_id, p]))
  const rows = plan.pool.slice(1).map((p: RcObject) => {
    const prediction = predictions.get(p.candidate_id)!
    const actual = oracle?.rows.find((r: RcObject) => r.candidate_id === p.candidate_id)
    return { candidate_id: p.candidate_id,
      predicted_all_requested_limits_pass: prediction.prediction.abstained ? null : Object.values(prediction.predicted_screens).every((s: any) => s.status === 'pass'),
      oracle_all_requested_limits_pass: !actual || !actual.full_reference_verification_pass ? null : actual.selection_eligible,
      shortlisted_by: RC_SEARCH_ARMS.filter(name => plan.plans[name].shortlist.includes(p.candidate_id)),
    }
  })
  const arms: RcObject = {}
  for (const name of RC_SEARCH_ARMS) {
    const matching = (predicate: (r: RcObject) => boolean) => oracle ? rows.filter(predicate).map((r: RcObject) => r.candidate_id) : null
    const groups = {
      missed_feasible: matching(r => r.oracle_all_requested_limits_pass === true && !r.shortlisted_by.includes(name)),
      oracle_unverifiable: matching(r => r.oracle_all_requested_limits_pass === null),
      false_safe: name === 'learned_order' ? matching(r => r.predicted_all_requested_limits_pass === true && r.oracle_all_requested_limits_pass === false) : null,
      predicted_safe_unverifiable: name === 'learned_order' ? matching(r => r.predicted_all_requested_limits_pass === true && r.oracle_all_requested_limits_pass === null) : null,
      false_negative: name === 'learned_order' ? matching(r => r.predicted_all_requested_limits_pass === false && r.oracle_all_requested_limits_pass === true) : null,
    }
    arms[name] = Object.fromEntries(Object.entries(groups).flatMap(([k, v]) => [[`${k}_count`, v === null ? null : v.length], [`${k}_candidate_ids`, v]]))
  }
  return { schema_version: 'rc-control-candidate-coverage-audit.v1', status: oracle ? 'compared_with_separate_full_reference_oracle' : 'oracle_not_run',
    alternative_denominator: plan.pool.length - 1, baseline_excluded: true, oracle_comparison_hash: oracle?.report_hash ?? null,
    definitions: { missed_feasible: 'oracle_verified_all_requested_limits_pass_but_not_shortlisted', false_safe: 'predicted_all_requested_limits_pass_but_oracle_verified_limit_failure',
      predicted_safe_unverifiable: 'predicted_all_requested_limits_pass_but_oracle_unverifiable', false_negative: 'predicted_limit_failure_but_oracle_verified_all_requested_limits_pass',
      deterministic_prediction_counts: 'not_applicable_strategy_makes_no_predictions', unavailable_counts: 'null_does_not_mean_zero' },
    candidates: rows, arms, independent_physical_validation: false }
}

/** Verify original full-path records before exposing any result to React.
 * Recorded predictions and historical fit declarations are not retrained here.
 */
export async function validateRcControlSearch(raw: Uint8Array, sourceRead: StudyRead): Promise<RcSearchReview> {
  check(raw.byteLength <= MAX, 'search_report_too_large')
  let bytesRead = raw.byteLength
  const read: StudyRead = async (path, max, expected) => {
    check(typeof path === 'string' && /^[A-Za-z0-9_.:/-]+$/.test(path) && path.split('/').every(part => part && part !== '.' && part !== '..') && !path.startsWith('/') && !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(path), 'search_path_invalid')
    const bytes = await sourceRead(path, max, expected)
    bytesRead += bytes.byteLength
    check(bytes.byteLength <= max && (expected === undefined || bytes.byteLength === expected) && bytesRead <= 1024 ** 3, 'search_byte_budget_invalid')
    return bytes
  }
  const resultDoc = document(raw), report = resultDoc.value
  await selfHash(resultDoc.raw, report, 'report_hash')
  check(['experimental-rc-control-candidate-search.v2', 'experimental-rc-control-candidate-search.v3'].includes(report.schema_version) && same(report.claims, claims)
    && /^[a-f0-9]{40}$/.test(report.source_revision) && keys(report.arms, RC_SEARCH_ARMS)
    && report.historical_training_cost_counted_once_outside_online_arms === true, 'search_report_invalid')
  const planDoc = document(await read('plan.json', MAX)), plan = planDoc.value
  await selfHash(planDoc.raw, plan, 'plan_hash')
  check(plan.schema_version === 'experimental-rc-control-candidate-search-plan.v2' && plan.plan_hash === report.plan_hash && plan.source_revision === report.source_revision
    && Array.isArray(plan.pool) && plan.pool.length >= 2 && plan.pool.length <= 17 && report.candidate_denominator === plan.pool.length
    && plan.pool[0].candidate_id === 'baseline' && plan.pool.every((r: RcObject) => id(r.candidate_id) && hash(r.model_identity) && hash(r.model_checksum))
    && new Set(plan.pool.map((r: RcObject) => r.candidate_id)).size === plan.pool.length
    && new Set(plan.pool.map((r: RcObject) => r.model_identity)).size === plan.pool.length
    && new Set(plan.pool.map((r: RcObject) => r.model_checksum)).size === plan.pool.length
    && nat(plan.full_analysis_budget_per_arm) && plan.full_analysis_budget_per_arm >= 2 && plan.full_analysis_budget_per_arm <= 17
    && typeof plan.oracle_after_online_arms === 'boolean' && (report.oracle !== null) === plan.oracle_after_online_arms
    && plan.original_training_and_pool_models_disjoint === true && plan.independent_project_geometry_history_split === false
    && keys(plan.plans, RC_SEARCH_ARMS), 'search_plan_invalid')
  const policyDoc = document(await read('policy.json', MAX)), policy = policyDoc.value
  await selfHash(policyDoc.raw, policy, 'policy_hash')
  const trainingDoc = document(await read('historical-training.json', MAX)), training = trainingDoc.value
  await selfHash(trainingDoc.raw, training, 'report_hash')
  check(policy.policy_hash === plan.policy_hash && training.policy_hash === plan.policy_hash && training.report_hash === plan.training_report_hash
    && same(training, report.historical_training_cost) && training.label_comparison_hash === policy.label_comparison_hash
    && training.schema_version === 'experimental-rc-control-candidate-training.v1' && training.independent_generalization === false && training.net_savings_proved === false
    && nat(training.sample_count) && training.sample_count >= 2 && training.sample_count <= 17
    && Array.isArray(policy.training_model_identities) && policy.training_model_identities.length === training.sample_count
    && policy.training_model_identities.every(hash) && new Set(policy.training_model_identities).size === training.sample_count
    && !plan.pool.some((r: RcObject) => policy.training_model_identities.includes(r.model_identity))
    && Array.isArray(policy.training_sample_hashes) && policy.training_sample_hashes.length === training.sample_count && policy.training_sample_hashes.every(hash)
    && Array.isArray(training.label_invocations) && training.label_invocations.length === 2 * training.sample_count
    && training.fit?.status === 'completed' && training.fit.unknown_fit_work_until_outcome === false
    && [training.wall_ns, training.cpu_ns, training.label_generation_wall_ns, training.fit.wall_ns, training.fit.cpu_ns].every(nat), 'search_training_binding_invalid')
  searchWork([{ invocations: training.label_invocations }])
  const ids: string[] = plan.pool.slice(1).map((r: RcObject) => r.candidate_id)
  const compareId = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0
  const prices = new Map<string, number>(plan.pool.map((r: RcObject) => [r.candidate_id, r.material_estimate?.total]))
  check([...prices.values()].every(p => typeof p === 'number' && Number.isFinite(p) && p >= 0), 'search_estimate_invalid')
  const priceSort = (a: string, b: string) => prices.get(a)! - prices.get(b)! || compareId(a, b)
  check(Array.isArray(plan.predictions) && same(plan.predictions.map((r: RcObject) => r.candidate_id), ids), 'search_prediction_denominator_invalid')
  const limits: RcObject = { ...plan.history_limits, ...plan.material_limits, ...Object.fromEntries(Object.entries(plan.terminal_limits ?? {}).map(([k, v]) => [`terminal_${k}`, v])) }
  for (const row of plan.predictions) {
    const prediction = row.prediction
    check(prediction && prediction.policy_hash === plan.policy_hash && typeof prediction.abstained === 'boolean'
      && prediction.physical_result_authority === false && prediction.uncertainty_calibrated === false && typeof prediction.reason === 'string'
      && row.estimate === prices.get(row.candidate_id), 'search_prediction_invalid')
    if (prediction.abstained) check(row.predicted_screens === null && prediction.performance === null && row.ranking_tier === 1, 'search_abstention_invalid')
    else {
      check(prediction.performance && keys(row.predicted_screens, Object.keys(limits)), 'search_prediction_screens_invalid')
      for (const [k, limit] of Object.entries(limits)) {
        const value = prediction.performance[k]
        check(typeof value === 'number' && value >= 0 && same(row.predicted_screens[k], { value, limit, status: value <= Number(limit) ? 'pass' : 'fail' }), 'search_prediction_screen_invalid')
      }
      check(row.ranking_tier === (Object.values(row.predicted_screens).every((s: any) => s.status === 'pass') ? 0 : 2), 'search_prediction_tier_invalid')
    }
  }
  const tiers = new Map<string, number>(plan.predictions.map((r: RcObject) => [r.candidate_id, r.ranking_tier]))
  for (const name of RC_SEARCH_ARMS) {
    const ordering = [...ids].sort(name === 'price_order' ? priceSort : (a, b) => tiers.get(a)! - tiers.get(b)! || priceSort(a, b))
    check(same(plan.plans[name], { ordering, shortlist: ordering.slice(0, plan.full_analysis_budget_per_arm - 1) }), 'search_ranking_invalid')
  }
  const designs: Record<string, RcDesignReview> = {}
  const names: string[] = [...RC_SEARCH_ARMS, ...(report.oracle ? ['exhaustive_oracle'] : [])]
  for (const name of names) {
    const outcome = name === 'exhaustive_oracle' ? report.oracle : report.arms[name]
    check(outcome && outcome.status === 'completed' && outcome.comparison_path === `${name}/comparison.json` && outcome.unknown_work_until_outcome === false
      && [outcome.wall_ns, outcome.cpu_ns].every(nat), 'search_arm_invalid')
    const comparisonBytes = await read(outcome.comparison_path, MAX)
    const review = await validateRcDesignStudy(comparisonBytes, (path, max, expected) => read(`${name}/${path}`, max, expected))
    const comparison = review.report
    const expected = ['baseline', ...(name === 'exhaustive_oracle' ? plan.plans.price_order.ordering : plan.plans[name].shortlist)]
    check(comparison.report_hash === outcome.comparison_hash && comparison.source_revision === report.source_revision
      && same(comparison.rows.map((r: RcObject) => r.candidate_id), expected) && outcome.request_count === expected.length
      && ['control_request', 'history_limits', 'material_limits', 'terminal_limits', 'price_table_hash'].every(k => same(comparison[k], plan[k]))
      && comparison.prices !== null && same(searchWork(comparison.rows), outcome.execution_work)
      && comparison.total_wall_ns <= outcome.wall_ns && comparison.total_process_cpu_ns <= outcome.cpu_ns, 'search_comparison_binding_invalid')
    for (const row of comparison.rows) {
      const pool = plan.pool.find((p: RcObject) => p.candidate_id === row.candidate_id)
      check(pool && row.artifacts.model?.sha256 === pool.model_checksum && same(row.quantities, pool.quantities) && same(row.material_estimate, pool.material_estimate), 'search_pool_result_mismatch')
    }
    const selected = comparison.rows.find((r: RcObject) => r.candidate_id === comparison.selected_candidate_id)
    check(outcome.selected_candidate_id === comparison.selected_candidate_id && outcome.selected_estimate === (selected?.material_estimate.total ?? null)
      && outcome.selected_full_reference_verified === Boolean(selected?.full_reference_verification_pass), 'search_selection_invalid')
    designs[name] = review
  }
  const poolSlices = rawValues(fields(planDoc.raw).get('pool')!.value)
  const common = designs.price_order.report
  for (const [index, row] of plan.pool.entries()) {
    const ref = row.model_artifact
    check(ref && ref.path === `pool/${row.candidate_id}.json` && nat(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= 16 * MAX && ref.sha256 === row.model_checksum, 'search_pool_model_reference_invalid')
    const bytes = await read(ref.path, 16 * MAX, ref.byte_length)
    check(await sha256Bytes(bytes) === ref.sha256, 'search_pool_model_bytes_invalid')
    const model = document(bytes).value
    check(model.schema_version === 'structural-analysis-canonical-model.v1', 'search_pool_model_invalid')
    await verifyQuantities({ ...row, artifacts: { model: ref } }, model, poolSlices[index], common)
  }
  check(same(report.candidate_coverage_audit, coverage(plan, designs.exhaustive_oracle?.report ?? null)), 'search_coverage_invalid')
  const cost = costOptimality(plan, Object.fromEntries(Object.entries(designs).map(([name, review]) => [name, review.report])))
  check(report.schema_version === 'experimental-rc-control-candidate-search.v3'
    ? same(report.candidate_cost_optimality_audit, cost) : !('candidate_cost_optimality_audit' in report), 'search_cost_optimality_invalid')
  check([report.ranking_wall_ns, report.online_and_optional_oracle_wall_ns, report.online_and_optional_oracle_cpu_ns].every(nat)
    && report.online_and_optional_oracle_wall_ns >= names.reduce((n, name) => n + (name === 'exhaustive_oracle' ? report.oracle : report.arms[name]).wall_ns, 0)
    && report.online_and_optional_oracle_cpu_ns >= names.reduce((n, name) => n + (name === 'exhaustive_oracle' ? report.oracle : report.arms[name]).cpu_ns, 0), 'search_total_time_invalid')
  return { report, plan, designs, costOptimality: cost }
}
