import { sha256Bytes } from './checksum'
import { check, document, same, selfHash, type RcObject } from './rcJobSchema'
import { artifactMaximum, validateRcStudyControl, verifyRcDesignCandidate, type StudyRead } from './rcControlDesignSchema'
import { validateLayoutPruning } from './rcLayoutCostPruning'

const MAX = 2 * 1024 ** 2
const metrics = ['maximum_translation_m', 'maximum_absolute_fiber_strain', 'maximum_steel_accumulated_plastic_strain', 'maximum_concrete_tensile_damage', 'maximum_concrete_compressive_damage']
export function validateStagingPolicy(plan: RcObject, report: RcObject): void {
  const count = plan.prefix_screening?.target_count
  check(Number.isSafeInteger(count) && count >= 1 && count < plan.control_request.targets_m.length, 'layout_prefix_count_invalid')
  const expected = { profile: 'verified-history-maximum-prefix.v1', target_count: count, baseline: 'full_reference_without_prefix', prefix_pass_is_full_acceptance: false, reuse_prefix_checkpoint: false, terminal_limits_used: false }
  check(same(plan.prefix_screening, expected) && same(report.prefix_screening, expected), 'layout_prefix_policy_invalid')
}

export async function validateLayoutStaging(plan: RcObject, comparison: RcObject, slices: string[], outcome: RcObject, name: string, read: StudyRead, common: RcObject, poolModels: Record<string, RcObject>, requestHash: string, work: (rows: RcObject[]) => RcObject): Promise<{ work: RcObject; records: Record<string, RcObject> }> {
  const info = comparison.prefix_screening, rows: RcObject[] = [], rejected: string[] = [], records: Record<string, RcObject> = Object.create(null)
  check(info && same(info, outcome.prefix_screening) && Array.isArray(info.decisions), 'layout_prefix_records_invalid')
  let cursor = 0, totalBytes = 0
  async function original(folder: string, ref: RcObject, path: string) {
    check(ref && same(Object.keys(ref).sort(), ['byte_length', 'path', 'sha256']) && ref.path === path && Number.isSafeInteger(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= MAX, 'layout_prefix_reference_invalid')
    const bytes = await read(`${folder}/${path}`, MAX, ref.byte_length)
    check(bytes.byteLength === ref.byte_length && await sha256Bytes(bytes) === ref.sha256, 'layout_prefix_bytes_invalid')
    return document(bytes)
  }
  await validateLayoutPruning(plan, comparison, slices, outcome, name, read, async key => {
    const record = info.decisions[cursor++], folder = `${name}/prefix/${key}`
    check(record && same(Object.keys(record).sort(), ['action', 'artifact', 'candidate_id']) && record.candidate_id === key, 'layout_prefix_order_invalid')
    const d = await original(name, record.artifact, `prefix/${key}/decision.json`), decision = d.value
    await selfHash(d.raw, decision, 'decision_hash')
    const r = await original(folder, decision.prefix_request, 'request.json'), request = r.value
    validateRcStudyControl(request)
    check(same(request, { ...plan.control_request, targets_m: plan.control_request.targets_m.slice(0, plan.prefix_screening.target_count) }), 'layout_prefix_request_invalid')
    const doc = await original(folder, decision.prefix_row, 'row.json'), row = doc.value
    check(row.candidate_id === 'baseline', 'layout_prefix_row_identity_invalid')
    for (const [role, ref] of Object.entries(row.artifacts) as [string, RcObject][]) {
      check(Number.isSafeInteger(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= artifactMaximum(role), 'layout_prefix_artifact_size_invalid')
      totalBytes += ref.byte_length
    }
    check(totalBytes <= 256 * 1024 ** 2, 'layout_prefix_bytes_exceeded')
    const prefixCommon = { ...common, control_request: request, terminal_limits: null }
    const originals = new Map<string, Uint8Array>()
    const model = await verifyRcDesignCandidate(row, doc.raw, prefixCommon, async (path, maximum, expected) => {
      const bytes = await read(`${folder}/${path}`, maximum, expected); originals.set(path, bytes); return bytes
    })
    const pool = plan.pool.find((p: RcObject) => p.candidate_id === key)
    check(model && same(model, poolModels[key]) && same(row.quantities, pool.quantities) && same(row.material_estimate, pool.material_estimate) && row.artifacts.model.sha256 === pool.model_artifact.sha256, 'layout_prefix_model_invalid')
    const w = work([row])
    check(w.api_invocation_count === 2 && row.invocations.every((i: RcObject) => i.status === 'returned'), 'layout_prefix_work_invalid')
    if (row.full_reference_verification_pass) check(row.invocations.every((i: RcObject) => i.work.attempted_step_count >= request.targets_m.length + (request.constant_nodal_loads?.length ? 1 : 0)), 'layout_prefix_complete_work_invalid')
    if (!row.full_reference_verification_pass) {
      const apiDoc = document(originals.get(row.artifacts.result?.path)!), api = apiDoc.value
      const validation = document(originals.get(row.artifacts.verification?.path)!).value
      await selfHash(apiDoc.raw, api, 'result_hash')
      check(api.model?.canonical_model_checksum === row.quantities.model_checksum && same(api.request?.targets_m, request.targets_m)
        && api.request.control_global_dof === request.control_global_dof && api.request.restart_input_sha256 === null
        && api.request.allow_reversals === request.allow_reversals && api.request.maximum_reversals === request.maximum_reversals && api.request.maximum_targets === request.maximum_targets
        && same(api.request.constant_nodal_loads ?? [], request.constant_nodal_loads ?? [])
        && same(api.request.configuration, { ...request.solver_config, augmented_coordinates: '[q_free_m,load_factor_coordinate_scale_m*lambda]', control_row_weight: 'F_reference*residual_tolerance/control_tolerance_m', profile: 'small-displacement-rc-fiber-direct-control.v1' })
        && validation.verified_result_hash === api.result_hash && validation.unavailable_execution_work === false
        && same(row.invocations[0].work, api.metrics.control_work) && same(row.invocations[1].work, validation.replay_control_work), 'layout_prefix_unverified_binding_invalid')
    }
    const violations = row.full_reference_verification_pass ? metrics.filter(k => row.screens[k]?.status === 'fail').map(k => ({ metric: k, value: row.screens[k].value, limit: row.screens[k].limit })) : []
    const action = violations.length ? 'reject_history_maximum' : 'execute_full_reference'
    const expected = { schema_version: 'experimental-rc-layout-prefix-screen.v1', full_request_hash: requestHash, prefix_request: decision.prefix_request, prefix_row: decision.prefix_row,
      model_checksum: row.quantities.model_checksum, prefix_target_count: request.targets_m.length, prefix_verified: row.full_reference_verification_pass, history_maximum_violations: violations,
      action, full_history_acceptance: false, terminal_limits_used: false, execution_work: w, decision_hash: decision.decision_hash }
    check(same(decision, expected) && record.action === action, 'layout_prefix_decision_invalid')
    rows.push(row); records[key] = { decision, row, request }
    if (violations.length) rejected.push(key)
    return violations.length > 0
  })
  check(cursor === info.decisions.length && same(info, { prefix_request_count: rows.length, full_reference_request_count: comparison.rows.length, decisions: info.decisions,
    rejected_history_maximum_candidate_ids: rejected, prefix_execution_work: work(rows), full_reference_execution_work: work(comparison.rows), full_history_acceptance_from_prefix: false }), 'layout_prefix_accounting_invalid')
  return { work: work([...comparison.rows, ...rows]), records }
}
