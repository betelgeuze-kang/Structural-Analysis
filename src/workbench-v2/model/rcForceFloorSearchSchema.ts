import { sha256Bytes } from './checksum'
import { candidateRanking, LEGACY_RANKING } from './rcControlCandidateRanking'
import { costOptimality, RC_COST_AUDIT_V4 } from './rcControlSearchCost'
import { validateRcDesignStudy, validateRcForceFloor, validateRcStudyLimits, verifyQuantities, type StudyRead } from './rcControlDesignSchema'
import type { RcSearchReview } from './rcControlSearchSchema'
import { validateRcTrainingIntervals } from './rcTrainingCost'
import { check, document, fields, rawValues, same, selfHash, type RcObject } from './rcJobSchema'

const MAX = 2 * 1024 ** 2
const arms = ['price_order', 'learned_order'] as const
const targets = ['terminal_maximum_translation_m', 'terminal_maximum_absolute_fiber_strain',
  'maximum_translation_m', 'maximum_absolute_fiber_strain', 'maximum_steel_accumulated_plastic_strain',
  'maximum_concrete_tensile_damage', 'maximum_concrete_compressive_damage', 'load_factor_at_target']
const claims = { known_pool_cost_optimality_only: true, learned_policy_used: true, net_ai_savings_proved: false,
  independent_physical_validation: false, independent_generalization: false, confirmed_currency_savings: false,
  workbench_search_review_integrated: false, precommitted_protocol_independently_verified: false }
const nat = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const hash = (v: unknown): v is string => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)
const keys = (v: RcObject, expected: string[]) => v && same(Object.keys(v).sort(), [...expected].sort())
const id = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(v)

function artifact(ref: RcObject, path: string, bytes: Uint8Array): Promise<void> {
  check(ref && ref.path === path && ref.byte_length === bytes.byteLength && hash(ref.sha256), 'force_search_artifact_reference_invalid')
  return sha256Bytes(bytes).then(digest => { check(digest === ref.sha256, 'force_search_artifact_bytes_invalid') })
}

/** Review original solver/replay records and declared training costs. The browser
 * does not refit the policy, attest its Git revision, or validate physical truth. */
export async function validateRcForceFloorSearch(raw: Uint8Array, read: StudyRead,
  searchWork: (rows: RcObject[]) => RcObject,
  coverage: (plan: RcObject, oracle: RcObject | null) => RcObject): Promise<RcSearchReview> {
  const resultDoc = document(raw), report = resultDoc.value
  await selfHash(resultDoc.raw, report, 'report_hash')
  check(report.schema_version === 'experimental-rc-control-force-floor-learned-search.v2'
    && same(report.claims, claims) && /^[a-f0-9]{40}$/.test(report.source_revision)
    && keys(report.arms, [...arms]) && report.oracle && report.historical_training_cost_counted_once_outside_online_arms === true,
  'force_search_report_invalid')
  check(report.timing_scope === 'preflight_signed_factor_ranking_two_online_full_reference_arms_then_separate_oracle_and_IO_excluding_final_report_write',
    'force_search_time_scope_invalid')
  const planDoc = document(await read('plan.json', MAX)), plan = planDoc.value
  await selfHash(planDoc.raw, plan, 'plan_hash')
  const floor = validateRcForceFloor(plan)
  check(plan.schema_version === 'experimental-rc-control-force-floor-learned-search-plan.v2'
    && plan.plan_hash === report.plan_hash && plan.source_revision === report.source_revision
    && plan.source_revision_is_attestation === false && same(report.force_response_floor, floor)
    && plan.learned_policy_used === true && plan.original_training_and_pool_models_disjoint === true
    && plan.independent_project_geometry_history_split === false && plan.oracle_after_online_arms === true
    && plan.ranking_strategy === LEGACY_RANKING && typeof plan.line_search_assembly_reuse === 'boolean'
    && keys(plan.plans, [...arms]) && Array.isArray(plan.pool) && plan.pool.length >= 2 && plan.pool.length <= 17
    && plan.pool[0].candidate_id === 'baseline' && plan.pool.length === report.candidate_denominator
    && nat(plan.full_analysis_budget_including_baseline_per_arm) && plan.full_analysis_budget_including_baseline_per_arm >= 2
    && plan.full_analysis_budget_including_baseline_per_arm <= plan.pool.length
    && same(plan.pool.slice(1).map((r: RcObject) => r.candidate_id), plan.candidates.map((c: RcObject) => c.candidate_id))
    && plan.pool.every((r: RcObject) => id(r.candidate_id) && hash(r.model_checksum) && hash(r.model_identity))
    && new Set(plan.pool.map((r: RcObject) => r.candidate_id)).size === plan.pool.length
    && new Set(plan.pool.map((r: RcObject) => r.model_identity)).size === plan.pool.length
    && hash(plan.price_table_hash) && hash(plan.policy_hash) && hash(plan.training_report_hash)
    && hash(plan.baseline_checksum) && plan.pool[0].model_checksum === plan.baseline_checksum,
  'force_search_plan_invalid')
  const binding = plan.protocol_binding
  check(binding && keys(binding, ['protocol_commit', 'protocol_path', 'protocol_sha256', 'input_sha256'])
    && typeof binding.protocol_commit === 'string' && /^[a-f0-9]{40}$/.test(binding.protocol_commit)
    && typeof binding.protocol_path === 'string' && /^examples\/research\/[A-Za-z0-9_.\/-]+\.json$/.test(binding.protocol_path)
    && !binding.protocol_path.split('/').includes('..') && hash(binding.protocol_sha256)
    && keys(binding.input_sha256, ['model', 'request', 'training_experiment', 'experiment', 'floor_plan', 'learning_plan'])
    && Object.values(binding.input_sha256).every(hash), 'force_search_protocol_declaration_invalid')
  const priceSort = (a: string, b: string) => {
    const left = plan.pool.find((r: RcObject) => r.candidate_id === a).material_estimate.total
    const right = plan.pool.find((r: RcObject) => r.candidate_id === b).material_estimate.total
    return left - right || (a < b ? -1 : a > b ? 1 : 0)
  }
  const policyBytes = await read('policy.json', MAX), trainingBytes = await read('historical-training.json', MAX)
  await artifact(plan.policy_artifact, 'policy.json', policyBytes)
  await artifact(plan.historical_training_artifact, 'historical-training.json', trainingBytes)
  const policyDoc = document(policyBytes), policy = policyDoc.value
  const trainingDoc = document(trainingBytes), training = trainingDoc.value
  await selfHash(policyDoc.raw, policy, 'policy_hash')
  await selfHash(trainingDoc.raw, training, 'report_hash')
  check(policy.schema_version === 'experimental-rc-control-force-factor-policy.v1'
    && training.schema_version === 'experimental-rc-control-force-factor-training.v1'
    && policy.policy_hash === plan.policy_hash && training.policy_hash === plan.policy_hash
    && training.report_hash === plan.training_report_hash && same(training, report.historical_training_cost)
    && training.label_comparison_hash === policy.label_comparison_hash
    && training.source_revision === plan.source_revision && hash(policy.context_hash) && hash(policy.label_comparison_hash)
    && training.timing_scope === 'training_preparation_labels_fresh_replay_fit_and_artifact_IO_excluding_final_report_write'
    && same(training.force_response_floor, floor)
    && same(policy.force_target, { target_index: floor.target_index, target_control_displacement_m: floor.target_control_displacement_m })
    && training.independent_generalization === false && training.net_savings_proved === false
    && nat(training.sample_count) && training.sample_count >= 2 && training.sample_count <= 17
    && Array.isArray(policy.training_model_identities) && policy.training_model_identities.length === training.sample_count
    && policy.training_model_identities.every(hash) && new Set(policy.training_model_identities).size === training.sample_count
    && plan.pool.every((r: RcObject) => !policy.training_model_identities.includes(r.model_identity))
    && Array.isArray(policy.training_sample_hashes) && policy.training_sample_hashes.length === training.sample_count
    && policy.training_sample_hashes.every(hash) && Array.isArray(training.label_invocations)
    && training.label_invocations.length === 2 * training.sample_count
    && training.fit?.status === 'completed' && training.fit.unknown_fit_work_until_outcome === false
    && [training.wall_ns, training.cpu_ns, training.label_generation_wall_ns, training.fit.wall_ns, training.fit.cpu_ns].every(nat),
  'force_search_training_invalid')
  check(Array.isArray(policy.features) && policy.features.length > 0 && policy.features.length <= 512
    && policy.features.every((feature: unknown) => typeof feature === 'string' && feature.length > 0)
    && new Set(policy.features).size === policy.features.length && same(policy.targets, targets)
    && Array.isArray(policy.weights) && policy.weights.length === policy.features.length + 1
    && policy.weights.every((row: unknown) => Array.isArray(row) && row.length === policy.targets.length && row.every(num))
    && ['mean', 'scale', 'minimum', 'maximum'].every(k => Array.isArray(policy[k]) && policy[k].length === policy.features.length && policy[k].every(num))
    && policy.scale.every((value: number) => value > 0)
    && policy.minimum.every((value: number, index: number) => value <= policy.maximum[index])
    && Array.isArray(policy.target_scale) && policy.target_scale.length === policy.targets.length
    && policy.target_scale.every((value: unknown) => num(value) && value > 0)
    && num(policy.ridge) && policy.ridge > 0 && num(policy.ood_margin) && policy.ood_margin >= 0 && policy.ood_margin <= 1,
  'force_search_policy_invalid')
  const trainingWork = searchWork([{ invocations: training.label_invocations }])
  validateRcTrainingIntervals(training)
  check(same(report.historical_training_execution_work, trainingWork), 'force_search_training_work_invalid')

  const ids: string[] = plan.pool.slice(1).map((r: RcObject) => r.candidate_id)
  const estimates = new Map<string, number>(plan.pool.map((r: RcObject) => [r.candidate_id, r.material_estimate?.total]))
  check([...estimates.values()].every(v => num(v) && v >= 0), 'force_search_prices_invalid')
  const limits = validateRcStudyLimits(plan)
  limits.load_factor_at_target = floor.minimum_load_factor
  check(Array.isArray(plan.predictions) && same(plan.predictions.map((r: RcObject) => r.candidate_id), ids), 'force_search_predictions_invalid')
  for (const row of plan.predictions) {
    const prediction = row.prediction
    check(prediction && prediction.policy_hash === policy.policy_hash && typeof prediction.abstained === 'boolean'
      && prediction.physical_result_authority === false && prediction.uncertainty_calibrated === false
      && typeof prediction.reason === 'string' && row.estimate === estimates.get(row.candidate_id),
    'force_search_prediction_authority_invalid')
    if (prediction.abstained) {
      check(row.predicted_force_floor_status === 'unavailable' && row.predicted_screens === null
        && prediction.performance === null && row.ranking_tier === 1, 'force_search_prediction_abstention_invalid')
    } else {
      check(row.predicted_force_floor_status === 'available' && keys(prediction.performance, Object.keys(limits))
        && keys(row.predicted_screens, Object.keys(limits)), 'force_search_prediction_screens_invalid')
      for (const [key, limit] of Object.entries(limits)) {
        const value = prediction.performance[key]
        check(num(value) && (key === 'load_factor_at_target' || value >= 0), 'force_search_prediction_value_invalid')
        const expected = key === 'load_factor_at_target'
          ? { value, limit, comparison: 'at_least', status: value >= Number(limit) ? 'pass' : 'fail' }
          : { value, limit, status: value <= Number(limit) ? 'pass' : 'fail' }
        check(same(row.predicted_screens[key], expected), 'force_search_prediction_screen_invalid')
      }
      check(row.ranking_tier === (Object.values(row.predicted_screens).every((s: any) => s.status === 'pass') ? 0 : 2),
        'force_search_prediction_tier_invalid')
    }
  }
  const ranked = candidateRanking(plan.predictions, LEGACY_RANKING)
  check(ranked.detail === null, 'force_search_ranking_invalid')
  for (const name of arms) {
    const ordering = name === 'price_order' ? [...ids].sort(priceSort) : ranked.ordering
    check(same(plan.plans[name], { ordering, shortlist: ordering.slice(0, plan.full_analysis_budget_including_baseline_per_arm - 1) }),
      'force_search_shortlist_invalid')
  }

  const designs: RcSearchReview['designs'] = {}
  const names = [...arms, 'exhaustive_oracle']
  for (const name of names) {
    const outcome = name === 'exhaustive_oracle' ? report.oracle : report.arms[name]
    check(outcome?.status === 'completed' && outcome.comparison_path === `${name}/comparison.json`
      && outcome.unknown_work_until_outcome === false && [outcome.wall_ns, outcome.cpu_ns].every(nat),
    'force_search_arm_invalid')
    const comparison = await validateRcDesignStudy(await read(outcome.comparison_path, MAX),
      (path, maximum, expected) => read(`${name}/${path}`, maximum, expected))
    const study = comparison.report
    const expected = ['baseline', ...(name === 'exhaustive_oracle' ? plan.plans.price_order.ordering : plan.plans[name].shortlist)]
    check(study.schema_version === 'experimental-rc-control-design-comparison.v2'
      && study.report_hash === outcome.comparison_hash && study.source_revision === report.source_revision
      && same(study.rows.map((r: RcObject) => r.candidate_id), expected) && outcome.request_count === expected.length
      && ['baseline_checksum', 'candidates', 'control_request', 'force_response_floor', 'history_limits', 'material_limits', 'terminal_limits', 'prices', 'price_table_hash'].every(k =>
        k === 'candidates' ? same(study.candidates, expected.slice(1).map(candidateId => plan.candidates.find((c: RcObject) => c.candidate_id === candidateId))) : same(study[k], plan[k]))
      && study.line_search_assembly_reuse === (plan.line_search_assembly_reuse ? 'rc-control-immediate-line-search-reuse.v1' : undefined)
      && same(searchWork(study.rows), outcome.execution_work)
      && study.total_wall_ns <= outcome.wall_ns && study.total_process_cpu_ns <= outcome.cpu_ns,
    'force_search_comparison_invalid')
    for (const row of study.rows) {
      const pool = plan.pool.find((p: RcObject) => p.candidate_id === row.candidate_id)
      check(pool && row.artifacts.model?.sha256 === pool.model_checksum
        && same(row.quantities, pool.quantities) && same(row.material_estimate, pool.material_estimate),
      'force_search_pool_result_invalid')
    }
    const selected = study.rows.find((r: RcObject) => r.candidate_id === study.selected_candidate_id)
    check(outcome.selected_candidate_id === study.selected_candidate_id
      && outcome.selected_estimate === (selected?.material_estimate.total ?? null)
      && outcome.selected_full_reference_verified === Boolean(selected?.full_reference_verification_pass),
    'force_search_selection_invalid')
    designs[name] = comparison
  }
  const poolSlices = rawValues(fields(planDoc.raw).get('pool')!.value)
  for (const [index, row] of plan.pool.entries()) {
    const ref = row.model_artifact
    check(ref?.path === `pool/${row.candidate_id}.json` && nat(ref.byte_length) && ref.byte_length > 0
      && ref.byte_length <= 16 * MAX && ref.sha256 === row.model_checksum, 'force_search_pool_reference_invalid')
    const bytes = await read(ref.path, 16 * MAX, ref.byte_length)
    check(await sha256Bytes(bytes) === ref.sha256, 'force_search_pool_bytes_invalid')
    const model = document(bytes).value
    check(model.schema_version === 'structural-analysis-canonical-model.v1', 'force_search_pool_model_invalid')
    await verifyQuantities({ ...row, artifacts: { model: ref } }, model, poolSlices[index], designs.price_order.report)
  }
  const expectedCoverage = { ...coverage(plan, designs.exhaustive_oracle.report),
    schema_version: 'rc-control-force-floor-candidate-coverage-audit.v2', force_response_floor: floor }
  check(same(report.candidate_coverage_audit, expectedCoverage), 'force_search_coverage_invalid')
  const cost = costOptimality(plan, Object.fromEntries(Object.entries(designs).map(([name, review]) => [name, review.report])), RC_COST_AUDIT_V4)
  check(same(report.candidate_cost_optimality_audit, cost), 'force_search_cost_invalid')
  check([report.ranking_wall_ns, report.online_and_oracle_wall_ns, report.online_and_oracle_cpu_ns].every(nat)
    && report.online_and_oracle_wall_ns >= names.reduce((n, name) => n + (name === 'exhaustive_oracle' ? report.oracle : report.arms[name]).wall_ns, 0)
    && report.online_and_oracle_cpu_ns >= names.reduce((n, name) => n + (name === 'exhaustive_oracle' ? report.oracle : report.arms[name]).cpu_ns, 0),
  'force_search_time_invalid')
  return { report, plan, designs, costOptimality: cost }
}
