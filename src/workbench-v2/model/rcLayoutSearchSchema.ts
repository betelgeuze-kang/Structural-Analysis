import { sha256Bytes, sha256Hex } from './checksum'
import { check, document, fields, rawValues, same, selfHash, type RcObject } from './rcJobSchema'
import { artifactMaximum, validateRcStudyControl, validateRcStudyLimits, verifyRcDesignCandidate, verifyQuantities, type RcDesignReview, type StudyRead } from './rcControlDesignSchema'
import { candidateRanking, CHEAPER_BOUNDARY_RANKING } from './rcControlCandidateRanking'
import { costOptimality } from './rcControlSearchCost'
import type { RcSearchReview } from './rcControlSearchSchema'

const MAX = 2 * 1024 ** 2
const nat = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const hash = (v: unknown) => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)
const keys = (v: RcObject, expected: string[]) => v && same(Object.keys(v).sort(), [...expected].sort())
const targets = ['terminal_maximum_translation_m', 'terminal_maximum_absolute_fiber_strain', 'maximum_translation_m', 'maximum_absolute_fiber_strain', 'maximum_steel_accumulated_plastic_strain', 'maximum_concrete_tensile_damage', 'maximum_concrete_compressive_damage']
const features = ['member_count', 'total_length_m', 'gross_concrete_volume_m3', 'longitudinal_rebar_volume_m3', 'mean_width_m', 'mean_depth_m', 'mean_cover_m', 'sum_rectangular_inertia_m4', 'sum_top_bar_count', 'sum_bottom_bar_count', 'sum_bar_area_m2',
  ...Array.from({ length: 15 }, (_, i) => ['width_m', 'depth_m', 'cover_m', 'top_bar_count', 'bottom_bar_count', 'bar_area_m2'].map(n => `member_${i}_${n}`)).flat(),
  'node_count', 'rotation_coordinate_scale_m', ...Array.from({ length: 30 }, (_, i) => [`node_${i}_relative_x_m`, `node_${i}_relative_y_m`]).flat()]

export async function validateRcLayoutSearch(raw: Uint8Array, read: StudyRead, work: (rows: RcObject[]) => RcObject, coverage: (plan: RcObject, oracle: RcObject | null) => RcObject): Promise<RcSearchReview> {
  const doc = document(raw), report = doc.value
  await selfHash(doc.raw, report, 'report_hash')
  const arms = ['price_order', 'learned_order']
  check(report.schema_version === 'experimental-rc-control-layout-search.v1' && keys(report.arms, arms)
    && same(report.claims, { physical_winner_requires_full_reference_and_screens: true, independent_generalization: false, functional_equivalence_verified: false, net_savings_proved: false, confirmed_currency_savings: false, workbench_search_review_integrated: false })
    && /^[a-f0-9]{40}$/.test(report.source_revision) && report.historical_training_cost_counted_once_outside_online_arms === true, 'layout_report_invalid')
  const planDoc = document(await read('plan.json', MAX)), plan = planDoc.value
  await selfHash(planDoc.raw, plan, 'plan_hash')
  check(plan.schema_version === 'experimental-rc-control-layout-search-plan.v1' && plan.plan_hash === report.plan_hash && plan.source_revision === report.source_revision
    && plan.functional_equivalence_verified === false && plan.independent_project_geometry_history_split === false
    && Array.isArray(plan.pool) && plan.pool.length >= 2 && plan.pool.length <= 17 && plan.pool[0].candidate_id === 'baseline'
    && plan.pool.every((p: RcObject) => typeof p.candidate_id === 'string' && /^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$/.test(p.candidate_id) && hash(p.model_identity))
    && new Set(plan.pool.map((p: RcObject) => p.candidate_id)).size === plan.pool.length
    && new Set(plan.pool.map((p: RcObject) => p.model_identity)).size === plan.pool.length
    && nat(plan.full_analysis_budget_per_arm) && plan.full_analysis_budget_per_arm >= 2 && plan.full_analysis_budget_per_arm <= 17
    && typeof plan.oracle_after_online_arms === 'boolean' && plan.oracle_after_online_arms === (report.oracle !== null) && keys(plan.plans, arms), 'layout_plan_invalid')
  validateRcStudyControl(plan.control_request)
  const priceDoc = document(await read('price-table.json', MAX)), prices = priceDoc.value
  check(keys(prices, ['concrete_per_m3', 'rebar_per_kg', 'currency', 'as_of', 'source']) && num(prices.concrete_per_m3) && prices.concrete_per_m3 >= 0 && num(prices.rebar_per_kg) && prices.rebar_per_kg >= 0
    && typeof prices.currency === 'string' && /^[A-Z]{3}$/.test(prices.currency) && typeof prices.as_of === 'string' && typeof prices.source === 'string', 'layout_prices_invalid')
  const priceFields = fields(priceDoc.raw)
  priceFields.set('schema_version', { member: '"schema_version":"declared-rc-material-prices.v1"', value: '' })
  check(await sha256Hex(`{${[...priceFields.entries()].sort(([a], [b]) => a < b ? -1 : 1).map(([, v]) => v.member).join(',')}}`) === plan.price_table_hash, 'layout_price_hash_invalid')
  const policyBytes = await read('policy.json', MAX), policyDoc = document(policyBytes), policy = policyDoc.value
  await selfHash(policyDoc.raw, policy, 'policy_hash')
  check(policy.schema_version === 'experimental-rc-control-layout-policy.v1' && policy.policy_hash === plan.policy_hash && hash(policy.context_hash) && hash(policy.label_comparison_hash)
    && same(policy.features, features) && same(policy.targets, targets) && num(policy.ridge) && policy.ridge > 0 && num(policy.ood_margin) && policy.ood_margin >= 0 && policy.ood_margin <= 1, 'layout_policy_invalid')
  for (const k of ['mean', 'scale', 'minimum', 'maximum', 'target_scale']) check(Array.isArray(policy[k]) && policy[k].length === (k === 'target_scale' ? 7 : 163) && policy[k].every(num), 'layout_policy_dimensions_invalid')
  check([...policy.scale, ...policy.target_scale].every((v: number) => v > 0) && policy.minimum.every((v: number, i: number) => v <= policy.maximum[i])
    && Array.isArray(policy.weights) && policy.weights.length === 164 && policy.weights.every((r: unknown) => Array.isArray(r) && r.length === 7 && r.every(num)), 'layout_policy_weights_invalid')
  const trainingDoc = document(await read('historical-training.json', MAX)), training = trainingDoc.value
  await selfHash(trainingDoc.raw, training, 'report_hash')
  check(training.schema_version === 'experimental-rc-control-layout-training.v1' && training.report_hash === plan.training_report_hash && same(training, report.historical_training_cost)
    && training.labels_report_hash === policy.label_comparison_hash && training.policy?.sha256 === await sha256Bytes(policyBytes) && training.policy.byte_length === policyBytes.byteLength
    && nat(training.sample_count) && training.sample_count >= 2 && training.sample_count <= 30 && training.fit?.status === 'completed' && training.fit.unknown_fit_work_until_outcome === false
    && training.independent_physical_validation === false && training.joint_geometry_history_generalization === false && training.net_savings_proved === false
    && [training.wall_ns, training.cpu_ns, training.fit.wall_ns, training.fit.cpu_ns, training.label_generation_wall_ns].every(nat)
    && training.wall_ns >= training.label_generation_wall_ns + training.fit.wall_ns, 'layout_training_invalid')
  for (const k of ['training_model_identities', 'training_sample_hashes']) check(Array.isArray(policy[k]) && policy[k].length === training.sample_count && policy[k].every(hash) && new Set(policy[k]).size === training.sample_count, 'layout_training_identities_invalid')
  check(!plan.pool.some((r: RcObject) => policy.training_model_identities.includes(r.model_identity)) && Array.isArray(training.label_invocations) && training.label_invocations.length === 2 * training.sample_count
    && training.label_invocations.every((r: RcObject, i: number) => r.phase === (i % 2 ? 'verification' : 'analysis') && r.status === 'returned'), 'layout_training_work_invalid')
  work([{ invocations: training.label_invocations }])
  const common = { control_request: plan.control_request, history_limits: plan.history_limits, material_limits: plan.material_limits, terminal_limits: plan.terminal_limits, prices, price_table_hash: plan.price_table_hash }
  validateRcStudyLimits(common)
  const poolSlices = rawValues(fields(planDoc.raw).get('pool')!.value)
  const poolModels: Record<string, RcObject> = {}
  for (const [i, row] of plan.pool.entries()) {
    const ref = row.model_artifact
    check(ref && ref.path === `pool/${row.candidate_id}.json` && nat(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= 16 * MAX && hash(ref.sha256), 'layout_pool_reference_invalid')
    const bytes = await read(ref.path, 16 * MAX, ref.byte_length)
    check(bytes.byteLength === ref.byte_length && await sha256Bytes(bytes) === ref.sha256, 'layout_pool_bytes_invalid')
    const model = document(bytes).value
    check(model.schema_version === 'structural-analysis-canonical-model.v1', 'layout_model_invalid')
    await verifyQuantities({ ...row, artifacts: { model: ref } }, model, poolSlices[i], common)
    poolModels[row.candidate_id] = model
  }
  const ids: string[] = plan.pool.slice(1).map((r: RcObject) => r.candidate_id)
  check(Array.isArray(plan.predictions) && same(plan.predictions.map((r: RcObject) => r.candidate_id), ids), 'layout_prediction_pool_invalid')
  const limits: RcObject = { ...plan.history_limits, ...plan.material_limits, ...Object.fromEntries(Object.entries(plan.terminal_limits ?? {}).map(([k, v]) => [`terminal_${k}`, v])) }
  for (const row of plan.predictions) {
    const p = row.prediction
    check(p && p.policy_hash === policy.policy_hash && typeof p.abstained === 'boolean' && p.physical_result_authority === false && p.uncertainty_calibrated === false && p.joint_geometry_history_generalization === false
      && row.estimate === plan.pool.find((r: RcObject) => r.candidate_id === row.candidate_id).material_estimate.total, 'layout_prediction_invalid')
    if (p.abstained) check(p.performance === null && row.predicted_screens === null && row.ranking_tier === 1, 'layout_abstention_invalid')
    else {
      check(keys(p.performance, targets) && targets.every(k => num(p.performance[k]) && p.performance[k] >= 0) && p.performance[targets[0]] <= p.performance[targets[2]] && p.performance[targets[1]] <= p.performance[targets[3]]
        && p.performance[targets[5]] <= 1 && p.performance[targets[6]] <= 1, 'layout_prediction_values_invalid')
      const screens = Object.fromEntries(Object.entries(limits).map(([k, limit]) => [k, { value: p.performance[k], limit, status: p.performance[k] <= Number(limit) ? 'pass' : 'fail' }]))
      check(same(row.predicted_screens, screens) && row.ranking_tier === (Object.values(screens).every(s => s.status === 'pass') ? 0 : 2), 'layout_prediction_screens_invalid')
    }
  }
  const ranked = candidateRanking(plan.predictions, CHEAPER_BOUNDARY_RANKING)
  check(same(plan.ranking, ranked.detail), 'layout_ranking_invalid')
  const priceOrder = [...ids].sort((a, b) => plan.pool.find((p: RcObject) => p.candidate_id === a).material_estimate.total - plan.pool.find((p: RcObject) => p.candidate_id === b).material_estimate.total || (a < b ? -1 : a > b ? 1 : 0))
  for (const name of arms) {
    const ordering = name === 'price_order' ? priceOrder : ranked.ordering
    check(same(plan.plans[name], { ordering, shortlist: ordering.slice(0, plan.full_analysis_budget_per_arm - 1) }), 'layout_schedule_invalid')
  }
  const designs: Record<string, RcDesignReview> = {}
  const names = [...arms, ...(report.oracle ? ['exhaustive_oracle'] : [])]
  for (const name of names) {
    const outcome = name === 'exhaustive_oracle' ? report.oracle : report.arms[name]
    check(outcome.status === 'completed' && outcome.comparison_path === `${name}/comparison.json` && outcome.unknown_work_until_outcome === false && [outcome.wall_ns, outcome.cpu_ns].every(nat), 'layout_arm_invalid')
    const comparisonDoc = document(await read(outcome.comparison_path, MAX)), comparison = comparisonDoc.value
    await selfHash(comparisonDoc.raw, comparison, 'report_hash')
    const expectedIds = ['baseline', ...(name === 'exhaustive_oracle' ? priceOrder : plan.plans[name].shortlist)]
    check(comparison.schema_version === 'experimental-rc-control-layout-comparison.v1' && comparison.report_hash === outcome.comparison_hash && comparison.price_table_hash === plan.price_table_hash
      && Array.isArray(comparison.rows) && same(comparison.rows.map((r: RcObject) => r.candidate_id), expectedIds) && outcome.request_count === expectedIds.length, 'layout_comparison_invalid')
    const slices = rawValues(fields(comparisonDoc.raw).get('rows')!.value), models: Record<string, RcObject> = {}
    let bytes = 0
    for (const [i, row] of comparison.rows.entries()) {
      for (const [role, ref] of Object.entries(row.artifacts) as [string, RcObject][]) { check(nat(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= artifactMaximum(role), 'layout_row_reference_invalid'); bytes += ref.byte_length }
      check(bytes <= 256 * 1024 ** 2, 'layout_comparison_bytes_exceeded')
      const model = await verifyRcDesignCandidate(row, slices[i], common, (p, max, expected) => read(`${name}/${p}`, max, expected), 'layout')
      const pool = plan.pool.find((p: RcObject) => p.candidate_id === row.candidate_id)
      check(pool && row.artifacts.model?.sha256 === pool.model_artifact.sha256 && same(row.quantities, pool.quantities) && same(row.material_estimate, pool.material_estimate) && same(model, poolModels[row.candidate_id]), 'layout_reference_pool_mismatch')
      if (model) models[row.candidate_id] = model
    }
    check(same(work(comparison.rows), outcome.execution_work), 'layout_arm_work_invalid')
    const eligible = comparison.rows.filter((r: RcObject) => r.selection_eligible).sort((a: RcObject, b: RcObject) => a.material_estimate.total - b.material_estimate.total || (a.candidate_id < b.candidate_id ? -1 : 1))
    const selected = eligible[0]?.candidate_id ?? null
    check(comparison.selected_candidate_id === selected && outcome.selected_candidate_id === selected, 'layout_selection_invalid')
    const base = comparison.rows[0], verified = comparison.rows.filter((r: RcObject) => r.full_reference_verification_pass).length
    const displayReport = { ...comparison, ...common, source_revision: report.source_revision, verified_count: verified, candidate_denominator: comparison.rows.length, status: verified === comparison.rows.length ? 'complete' : 'incomplete',
      total_wall_ns: outcome.wall_ns, total_process_cpu_ns: outcome.cpu_ns, rows: comparison.rows.map((r: RcObject) => ({ ...r,
        quantity_delta: r.quantities && base.quantities ? Object.fromEntries(Object.keys(base.quantities.totals).map(k => [k, r.quantities.totals[k] - base.quantities.totals[k]])) : null,
        scoped_estimate_reduction: r.material_estimate && base.material_estimate ? base.material_estimate.total - r.material_estimate.total : null })) }
    designs[name] = { report: comparison, models, displayReport }
  }
  const cost = costOptimality(plan, Object.fromEntries(Object.entries(designs).map(([name, value]) => [name, value.report])))
  check(same(report.candidate_cost_optimality_audit, cost) && same(report.candidate_coverage_audit, coverage(plan, designs.exhaustive_oracle?.report ?? null)), 'layout_audit_invalid')
  check([report.ranking_wall_ns, report.online_and_optional_oracle_wall_ns, report.online_and_optional_oracle_cpu_ns].every(nat)
    && report.online_and_optional_oracle_wall_ns >= report.ranking_wall_ns + names.reduce((s, n) => s + (n === 'exhaustive_oracle' ? report.oracle : report.arms[n]).wall_ns, 0)
    && report.online_and_optional_oracle_cpu_ns >= names.reduce((s, n) => s + (n === 'exhaustive_oracle' ? report.oracle : report.arms[n]).cpu_ns, 0), 'layout_total_cost_invalid')
  return { report, plan, designs, costOptimality: cost }
}
