import { sha256Bytes, sha256Hex } from './checksum'
import { check, document, fields, same, selfHash, type RcObject } from './rcJobSchema'
import type { StudyRead } from './rcControlDesignSchema'

export const layoutPruningPolicy = {
  profile: 'verified-incumbent-strict-cost.v1', consideration_horizon: 'frozen_shortlist_including_baseline',
  unused_analysis_budget_reallocated: false, unevaluated_physical_feasibility: 'unknown',
}

/** Recompute decisions only after the caller verifies every original design row. */
export async function validateLayoutPruning(plan: RcObject, comparison: RcObject, slices: string[], outcome: RcObject, name: string, read: StudyRead, prefixCheck?: (key: string) => Promise<boolean>): Promise<void> {
  const pruning = comparison.cost_pruning, considered: string[] = ['baseline', ...plan.plans[name].shortlist]
  const rows: RcObject[] = comparison.rows, evaluated: RcObject[] = [], skipped: string[] = []
  check(pruning && same(outcome.cost_pruning, pruning) && Array.isArray(pruning.decisions) && pruning.decisions.length === considered.length, 'layout_pruning_records_invalid')
  const minimumSteps = plan.control_request.targets_m.length + (plan.control_request.constant_nodal_loads?.length ? 1 : 0)
  for (const row of rows) if (row.full_reference_verification_pass) {
    check(row.invocations.length === 2 && row.invocations.every((i: RcObject) => Number.isSafeInteger(i.work?.attempted_step_count) && i.work.attempted_step_count >= minimumSteps), 'layout_pruning_complete_work_invalid')
  }
  for (const [ordinal, key] of considered.entries()) {
    const ids = evaluated.map(r => r.candidate_id)
    const eligible = evaluated.filter(r => r.full_reference_verification_pass === true && r.selection_eligible === true)
      .sort((a, b) => a.material_estimate.total - b.material_estimate.total || (a.candidate_id < b.candidate_id ? -1 : a.candidate_id > b.candidate_id ? 1 : 0))
    const winner = eligible[0], remaining: RcObject[] = plan.pool.filter((p: RcObject) => !ids.includes(p.candidate_id))
    const dominated = remaining.filter(p => winner && p.material_estimate.total > winner.material_estimate.total).map(p => p.candidate_id)
    const skip = dominated.includes(key), action = skip ? 'skip_cost_dominated' : prefixCheck && key !== 'baseline' ? 'execute_prefix_screen' : 'execute_full_reference'
    const record = pruning.decisions[ordinal], ref = record?.artifact, path = `decisions/${String(ordinal).padStart(2, '0')}.json`
    check(record && same(Object.keys(record).sort(), ['action', 'artifact', 'candidate_id']) && record.candidate_id === key && record.action === action
      && ref && same(Object.keys(ref).sort(), ['byte_length', 'path', 'sha256']) && ref.path === path
      && Number.isSafeInteger(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= 2 * 1024 ** 2, 'layout_pruning_reference_invalid')
    const raw = await read(`${name}/${path}`, 2 * 1024 ** 2, ref.byte_length)
    check(raw.byteLength === ref.byte_length && await sha256Bytes(raw) === ref.sha256, 'layout_pruning_bytes_invalid')
    const doc = document(raw), decision = doc.value
    await selfHash(doc.raw, decision, 'decision_hash')
    const bound = decision.bound, boundRaw = fields(doc.raw).get('bound')!.value
    check(bound && typeof bound === 'object', 'layout_pruning_bound_invalid')
    await selfHash(boundRaw, bound, 'bound_hash')
    const expectedBound = {
      schema_version: 'experimental-rc-layout-cost-dominance.v1', plan_hash: plan.plan_hash, price_table_hash: plan.price_table_hash,
      evaluated_rows_hash: await sha256Hex(`[${slices.slice(0, evaluated.length).join(',')}]`),
      incumbent_candidate_id: winner?.candidate_id ?? null, incumbent_estimate: winner?.material_estimate.total ?? null,
      cost_dominated_unevaluated_candidate_ids: dominated, retained_unevaluated_candidate_ids: remaining.filter(p => !dominated.includes(p.candidate_id)).map(p => p.candidate_id),
      unevaluated_physical_feasibility: 'unknown', original_reference_artifact_verification_required: true,
      global_cost_optimality_proved: false, net_savings_proved: false, execution_skips_performed: 0, bound_hash: bound.bound_hash,
    }
    check(same(bound, expectedBound) && same(decision, { schema_version: prefixCheck ? 'experimental-rc-layout-staged-cost-decision.v1' : 'experimental-rc-layout-cost-pruning-decision.v1', candidate_id: key,
      evaluated_candidate_ids_before: ids, action, bound, physical_feasibility_at_decision: 'unknown', decision_hash: decision.decision_hash }), 'layout_pruning_decision_invalid')
    if (skip) skipped.push(key)
    else if (!(prefixCheck && key !== 'baseline' && await prefixCheck(key))) { check(rows[evaluated.length]?.candidate_id === key, 'layout_pruning_required_row_missing'); evaluated.push(rows[evaluated.length]) }
  }
  check(evaluated.length === rows.length, 'layout_pruning_extra_row')
  const ids = evaluated.map(r => r.candidate_id), poolIds: string[] = plan.pool.map((p: RcObject) => p.candidate_id)
  check(Number.isSafeInteger(pruning.decision_wall_ns) && pruning.decision_wall_ns >= 0 && pruning.decision_wall_ns <= outcome.wall_ns
    && same(pruning, { profile: layoutPruningPolicy.profile, considered_candidate_ids: considered, evaluated_candidate_ids: ids,
      skipped_cost_dominated_candidate_ids: skipped, outside_consideration_horizon_candidate_ids: poolIds.filter(k => !considered.includes(k)),
      unevaluated_candidate_ids: poolIds.filter(k => !ids.includes(k)), decisions: pruning.decisions, decision_wall_ns: pruning.decision_wall_ns,
      unevaluated_physical_feasibility: 'unknown', global_cost_optimality_proved: false }), 'layout_pruning_coverage_invalid')
}
