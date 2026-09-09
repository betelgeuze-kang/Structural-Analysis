import { sha256Bytes, sha256Hex } from './checksum'
import { check, document, fields, rawValues, same, selfHash, CLAIMS, PATH_CLAIMS, validateRcAcceptedHistory, validateRcPreload, type RcObject } from './rcJobSchema'

export const RC_STUDY_SCHEMA = 'experimental-rc-control-design-comparison.v1'
const CLAIMS_STUDY = { experimental_rc_control: true, independent_physical_validation: false, design_authority: false, confirmed_currency_savings: false, performance_improvement: false, release_approved: false }
const SCOPE = 'gross_concrete_and_straight_authored_longitudinal_rebar.v1'
const EXCLUDED = ['transverse_reinforcement', 'laps_anchorage_hooks', 'waste', 'formwork', 'labor', 'fabrication', 'transport', 'tax']
const QUANTITIES = ['gross_concrete_volume_m3', 'longitudinal_rebar_volume_m3', 'longitudinal_rebar_mass_kg']
const ROLES = ['model', 'result', 'checkpoint', 'verification', 'analysis_started', 'analysis_outcome', 'verification_started', 'verification_outcome']
export const artifactMaximum = (role: string): number => role === 'result' ? 64 * 1024 ** 2 : role === 'checkpoint' ? 128 * 1024 ** 2 : 16 * 1024 ** 2
const nat = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const hash = (v: unknown): boolean => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)
const close = (a: unknown, b: number): boolean => num(a) && Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(b))
export type StudyRead = (relative: string, maximum: number, expected?: number) => Promise<Uint8Array>
export interface RcDesignReview { report: RcObject; models: Record<string, RcObject> }

export async function verifiedStudyBytes(read: StudyRead, row: RcObject, role: string): Promise<Uint8Array> {
  const ref = row.artifacts[role]
  check(ROLES.includes(role) && ref, 'study_role_invalid')
  check(ref.path === `${row.candidate_id}/${role.replace(/_/g, '-')}.json`, 'study_path_invalid')
  check(nat(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= artifactMaximum(role) && hash(ref.sha256), 'study_reference_invalid')
  const raw = await read(ref.path, artifactMaximum(role), ref.byte_length)
  check(raw.byteLength === ref.byte_length && await sha256Bytes(raw) === ref.sha256, 'study_bytes_invalid')
  return raw
}

function limits(report: RcObject): RcObject {
  const geometric = ['maximum_translation_m', 'maximum_absolute_fiber_strain']
  const material = ['maximum_steel_accumulated_plastic_strain', 'maximum_concrete_tensile_damage', 'maximum_concrete_compressive_damage']
  const result: RcObject = {}
  for (const [group, keys, prefix] of [[report.history_limits, geometric, ''], [report.material_limits, material, ''], [report.terminal_limits, geometric, 'terminal_']] as const) {
    if (group === null && prefix) continue
    check(group && same(Object.keys(group).sort(), [...keys].sort()), 'study_limits_invalid')
    for (const key of keys) {
      check(num(group[key]) && group[key] >= 0 && (!key.includes('damage') || group[key] <= 1), 'study_limit_invalid')
      result[prefix + key] = group[key]
    }
  }
  return result
}
function work(value: RcObject | null): void {
  if (value === null) return
  check(value && same(Object.keys(value).sort(), ['attempted_step_count', 'known_linear_solve_count', 'known_newton_iteration_count', 'unknown_solver_work_attempt_count'].sort())
    && Object.values(value).every(nat), 'study_work_invalid')
}
function performance(history: RcObject[]): RcObject {
  const out: RcObject = { maximum_translation_m: 0, maximum_absolute_fiber_strain: 0, maximum_steel_accumulated_plastic_strain: null, maximum_concrete_tensile_damage: null, maximum_concrete_compressive_damage: null,
    terminal_maximum_translation_m: 0, terminal_maximum_absolute_fiber_strain: 0, minimum_load_factor: Infinity, maximum_load_factor: -Infinity, terminal_load_factor: history[history.length - 1].load_factor, accepted_epoch_count: history.length }
  for (const [i, row] of history.entries()) {
    out.minimum_load_factor = Math.min(out.minimum_load_factor, row.load_factor); out.maximum_load_factor = Math.max(out.maximum_load_factor, row.load_factor)
    for (const node of row.node_displacements) {
      const v = Math.hypot(node.UX_m, node.UY_m, node.UZ_m)
      out.maximum_translation_m = Math.max(out.maximum_translation_m, v)
      if (i === history.length - 1) out.terminal_maximum_translation_m = Math.max(out.terminal_maximum_translation_m, v)
    }
    for (const p of row.fiber_results) {
      out.maximum_absolute_fiber_strain = Math.max(out.maximum_absolute_fiber_strain, Math.abs(p.strain))
      if (i === history.length - 1) out.terminal_maximum_absolute_fiber_strain = Math.max(out.terminal_maximum_absolute_fiber_strain, Math.abs(p.strain))
      for (const key of (p.material_kind === 'steel' ? ['accumulated_plastic_strain'] : ['tensile_damage', 'compressive_damage'])) {
        const target = `maximum_${p.material_kind}_${key}`
        out[target] = Math.max(out[target] ?? -Infinity, p.material_state[key])
      }
    }
  }
  return out
}

async function verifyQuantities(row: RcObject, model: RcObject, rowRaw: string, report: RcObject): Promise<void> {
  const q = row.quantities
  check(q && q.schema_version === 'public-rc-fiber-member-quantities.v1' && q.scope === SCOPE && q.detailed_takeoff === false
    && same(q.excluded_items, EXCLUDED) && q.rebar_density_kg_per_m3 === 7850 && q.model_checksum === row.artifacts.model.sha256, 'study_quantity_scope_invalid')
  await selfHash(fields(rowRaw).get('quantities')!.value, q, 'quantity_hash')
  check(q.members.length === model.elements.length && new Set(q.members.map((m: RcObject) => m.member_id)).size === q.members.length, 'study_member_count_invalid')
  const totals: RcObject = Object.fromEntries(QUANTITIES.map(k => [k, 0]))
  for (const member of model.elements) {
    const section = model.sections.find((s: RcObject) => s.id === member.section)
    const nodes = member.nodes.map((id: string) => model.nodes.find((n: RcObject) => n.id === id))
    check(nodes.length === 2 && nodes.every(Boolean) && section, 'study_geometry_invalid')
    const length = Math.hypot(...nodes[0].coordinates.map((v: number, i: number) => v - nodes[1].coordinates[i]))
    const volume = length * section.width_m * section.depth_m
    const rebar = length * (section.top_bar_count + section.bottom_bar_count) * section.bar_area_m2
    const values = [volume, rebar, rebar * 7850]
    const actual = q.members.find((m: RcObject) => m.member_id === member.id)
    check(actual && actual.section_id === member.section && close(actual.length_m, length), 'study_member_identity_invalid')
    QUANTITIES.forEach((key, i) => { check(close(actual[key], values[i]), 'study_member_quantity_invalid'); totals[key] += values[i] })
  }
  QUANTITIES.forEach(key => check(close(q.totals[key], totals[key]), 'study_quantity_total_invalid'))
  const price = report.prices, estimate = row.material_estimate
  if (price === null) { check(estimate === null, 'study_unpriced_estimate'); return }
  check(estimate && estimate.scope === SCOPE && estimate.verified_quote === false && estimate.confirmed_currency_savings === false
    && same(estimate.excluded_items, EXCLUDED) && estimate.quantity_hash === q.quantity_hash && estimate.price_table_hash === report.price_table_hash
    && estimate.currency === price.currency && close(estimate.total, totals.gross_concrete_volume_m3 * price.concrete_per_m3 + totals.longitudinal_rebar_mass_kg * price.rebar_per_kg), 'study_estimate_invalid')
}

async function verifyCandidate(row: RcObject, rowRaw: string, report: RcObject, read: StudyRead): Promise<RcObject | null> {
  const artifacts: Record<string, { raw: string; value: RcObject }> = {}
  for (const role of Object.keys(row.artifacts)) artifacts[role] = document(await verifiedStudyBytes(read, row, role))
  if (!artifacts.model) {
    check(row.status === 'invalid_candidate' && row.quantities === null && row.material_estimate === null && row.invocations.length === 0 && Object.keys(artifacts).length === 0, 'study_preparation_invalid')
  } else {
    check(artifacts.model.value.schema_version === 'structural-analysis-canonical-model.v1', 'study_model_invalid')
    await verifyQuantities(row, artifacts.model.value, rowRaw, report)
  }
  check(Array.isArray(row.invocations) && row.invocations.length <= 2, 'study_invocations_invalid')
  for (const [i, invocation] of row.invocations.entries()) {
    const phase = i === 0 ? 'analysis' : 'verification'
    check(invocation.phase === phase && ['returned', 'raised'].includes(invocation.status) && nat(invocation.wall_ns) && nat(invocation.process_cpu_ns), 'study_invocation_invalid')
    work(invocation.work)
    check(invocation.unknown_execution_work === (invocation.work === null || invocation.work.unknown_solver_work_attempt_count > 0)
      && same(artifacts[`${phase}_started`]?.value, { phase, status: 'started', unknown_execution_work: true, work: null })
      && same(artifacts[`${phase}_outcome`]?.value, invocation), 'study_invocation_binding_invalid')
  }
  if (row.full_reference_verification_pass !== true) {
    check(row.full_reference_verification_pass === false && row.selection_eligible === false && row.performance === null && row.screens === null
      && ['invalid_candidate', 'execution_error', 'verification_blocked'].includes(row.status), 'study_unverified_promotion')
    return artifacts.model?.value ?? null
  }
  const apiDoc = artifacts.result, nativeDoc = artifacts.checkpoint, validation = artifacts.verification?.value
  check(apiDoc && nativeDoc && validation && row.status === 'verified' && row.failure === null && row.invocations.length === 2, 'study_verified_missing')
  const api = apiDoc.value, native = nativeDoc.value, config = report.control_request, targets = config.targets_m
  const hasPreload = config.schema_version === 'bounded-rc-fiber-direct-control-request.v2'
  const version = hasPreload ? 'v2' : 'v1'
  await selfHash(apiDoc.raw, api, 'result_hash'); await selfHash(nativeDoc.raw, native, 'artifact_hash')
  check(api.schema_version === `bounded-rc-fiber-direct-control-result.${version}` && api.status === 'ready' && api.contract_pass === true && api.failure === null
    && same(api.claims, CLAIMS) && same(api.unsupported_features, []) && same(api.path.claims, PATH_CLAIMS) && same(native.claims, PATH_CLAIMS), 'study_api_invalid')
  check(api.model.canonical_model_checksum === row.quantities.model_checksum
    && api.control.global_dof === config.control_global_dof && api.control.unit === 'm' && ['UX', 'UY'].includes(api.control.component)
    && api.request.restart_input_sha256 === null && api.path.initial_checkpoint.epoch === (hasPreload ? 1 : 0)
    && same(api.request.targets_m, targets) && api.request.allow_reversals === config.allow_reversals
    && api.request.maximum_reversals === config.maximum_reversals && api.request.maximum_targets === config.maximum_targets
    && same(api.request.configuration, { ...config.solver_config, augmented_coordinates: '[q_free_m,load_factor_coordinate_scale_m*lambda]', control_row_weight: 'F_reference*residual_tolerance/control_tolerance_m', profile: 'small-displacement-rc-fiber-direct-control.v1' }), 'study_request_binding_invalid')
  check(validation.schema_version === 'bounded-rc-fiber-direct-control-validation.v1' && validation.verified_result_hash === api.result_hash
    && ['artifact_contract_pass', 'contract_pass', 'physical_path_complete', 'fresh_source_execution_invoked', 'solver_replay_performed'].every(k => validation[k] === true)
    && validation.unavailable_execution_work === false && same(validation.errors, []) && same(validation.claims, CLAIMS)
    && same(row.invocations[0].work, api.metrics.control_work) && same(row.invocations[1].work, validation.replay_control_work)
    && row.invocations.every((i: RcObject) => i.status === 'returned'), 'study_verification_invalid')
  check(native.schema_version === `stateful-fiber-frame2d-control-restart.${version}` && same(native.accepted_targets_m, targets)
    && Array.isArray(native.accepted_step_bindings) && native.accepted_step_bindings.length === targets.length
    && api.checkpoint.sha256 === row.artifacts.checkpoint.sha256 && api.checkpoint.byte_length === row.artifacts.checkpoint.byte_length
    && await sha256Hex(fields(nativeDoc.raw).get('terminal_checkpoint')!.value) === native.terminal_checkpoint_sha256
    && same(native.terminal_checkpoint, api.path.final_checkpoint) && api.path.status === 'ready'
    && same(api.path.accepted_target_prefix_m, targets) && api.response_history.length === targets.length
    && same(api.terminal_response, api.response_history.at(-1)), 'study_checkpoint_invalid')
  check(native.scope.problem_contract_hash === api.model.problem_contract_hash && same(native.scope, api.path.scope), 'study_scope_invalid')
  await validateRcPreload(api, apiDoc.raw, native, config, targets)
  if (hasPreload) check(same(api.path.initial_checkpoint, native.preload_checkpoint), 'study_preload_origin_invalid')
  const history = validateRcAcceptedHistory(api, native, artifacts.model.value, config)
  check(history[0].parent_checkpoint_hash === (hasPreload ? api.path.preload_attempts[0].step.parent_checkpoint.state_hash : api.path.initial_checkpoint.state_hash), 'study_genesis_invalid')
  const values = performance(history)
  check(same(Object.keys(values).sort(), Object.keys(row.performance).sort()), 'study_performance_keys_invalid')
  for (const [key, value] of Object.entries(values)) check(value === null ? row.performance[key] === null : close(row.performance[key], Number(value)), 'study_performance_invalid')
  const requested = limits(report)
  check(same(Object.keys(requested).sort(), Object.keys(row.screens).sort()), 'study_screen_keys_invalid')
  for (const [key, limit] of Object.entries(requested)) {
    const value = row.performance[key]
    check(same(row.screens[key], { value, limit, status: value === null ? 'unavailable' : value <= Number(limit) ? 'pass' : 'fail' }), 'study_screen_invalid')
  }
  check(row.selection_eligible === Object.values(row.screens).every((s: any) => s.status === 'pass'), 'study_eligibility_invalid')
  return artifacts.model.value
}

export async function validateRcDesignStudy(raw: Uint8Array, read: StudyRead): Promise<RcDesignReview> {
  const doc = document(raw), report = doc.value
  await selfHash(doc.raw, report, 'report_hash')
  check(report.schema_version === RC_STUDY_SCHEMA && same(report.claims, CLAIMS_STUDY) && report.source_revision_is_attestation === false
    && typeof report.source_revision === 'string' && /^[a-f0-9]{40}$/.test(report.source_revision), 'study_identity_invalid')
  const identityKeys = ['schema_version', 'baseline_checksum', 'candidates', 'control_request', 'history_limits', 'material_limits', 'terminal_limits', 'prices', 'price_table_hash', 'source_revision', 'source_revision_is_attestation']
  const members = fields(doc.raw)
  check(await sha256Hex(`{${identityKeys.sort().map(k => { check(members.has(k), 'study_identity_missing'); return members.get(k)!.member }).join(',')}}`) === report.request_hash, 'study_request_hash_invalid')
  const config = report.control_request
  check(['bounded-rc-fiber-direct-control-request.v1', 'bounded-rc-fiber-direct-control-request.v2'].includes(config?.schema_version) && Array.isArray(config.targets_m) && config.targets_m.length > 0 && config.targets_m.length <= 255
    && config.targets_m.every(num) && nat(config.control_global_dof) && num(config.solver_config?.control_tolerance_m) && config.solver_config.control_tolerance_m > 0, 'study_control_invalid')
  if (config.schema_version.endsWith('.v2')) {
    check(Array.isArray(config.constant_nodal_loads) && config.constant_nodal_loads.length > 0 && config.constant_nodal_loads.length <= 16
      && new Set(config.constant_nodal_loads.map((r: RcObject) => r?.node_id)).size === config.constant_nodal_loads.length
      && config.constant_nodal_loads.every((r: RcObject) => r && same(Object.keys(r).sort(), ['FX_kN', 'FY_kN', 'MZ_kNm', 'node_id']) && typeof r.node_id === 'string'
        && ['FX_kN', 'FY_kN', 'MZ_kNm'].every(k => num(r[k])) && ['FX_kN', 'FY_kN', 'MZ_kNm'].some(k => r[k] !== 0)), 'study_constant_loads_invalid')
  } else check(config.constant_nodal_loads === undefined, 'study_constant_profile_invalid')
  limits(report)
  check(Array.isArray(report.rows) && Array.isArray(report.candidates) && report.candidates.length >= 1 && report.candidates.length <= 16
    && report.rows.length === report.candidates.length + 1 && report.candidate_denominator === report.rows.length
    && same(report.rows.map((r: RcObject) => r.candidate_id), ['baseline', ...report.candidates.map((c: RcObject) => c.candidate_id)])
    && new Set(report.rows.map((r: RcObject) => r.candidate_id)).size === report.rows.length, 'study_denominator_invalid')
  if (report.prices !== null) {
    check(num(report.prices.concrete_per_m3) && report.prices.concrete_per_m3 >= 0 && num(report.prices.rebar_per_kg) && report.prices.rebar_per_kg >= 0
      && ['currency', 'as_of', 'source'].every(k => typeof report.prices[k] === 'string'), 'study_prices_invalid')
    const priceFields = fields(members.get('prices')!.value)
    priceFields.set('schema_version', { member: '"schema_version":"declared-rc-material-prices.v1"', value: '' })
    check(await sha256Hex(`{${[...priceFields.entries()].sort(([a], [b]) => a < b ? -1 : 1).map(([, v]) => v.member).join(',')}}`) === report.price_table_hash, 'study_price_hash_invalid')
  } else check(report.price_table_hash === null, 'study_price_missing')
  let budget = 0
  for (const row of report.rows) {
    check(typeof row.candidate_id === 'string' && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(row.candidate_id), 'study_candidate_id_invalid')
    check(row.artifacts && typeof row.artifacts === 'object' && !Array.isArray(row.artifacts), 'study_artifacts_invalid')
    for (const [role, ref] of Object.entries(row.artifacts) as [string, RcObject][]) {
      check(ROLES.includes(role) && ref.path === `${row.candidate_id}/${role.replace(/_/g, '-')}.json`
        && nat(ref.byte_length) && ref.byte_length > 0 && ref.byte_length <= artifactMaximum(role) && hash(ref.sha256), 'study_reference_invalid')
      budget += ref.byte_length
    }
  }
  check(budget <= 256 * 1024 ** 2, 'study_total_bytes_exceeded')
  // Candidates are validated serially. Large histories are not returned to React.
  const rowSlices = rawValues(members.get('rows')!.value)
  const models: Record<string, RcObject> = {}
  for (const [i, row] of report.rows.entries()) {
    const model = await verifyCandidate(row, rowSlices[i], report, read)
    if (model) models[row.candidate_id] = model
  }
  const base = report.rows[0]
  check(base.artifacts.model?.sha256 === report.baseline_checksum || base.status === 'invalid_candidate', 'study_baseline_invalid')
  for (const candidate of report.candidates) {
    const actual = models[candidate.candidate_id]
    if (!actual) continue
    check(models.baseline && Array.isArray(candidate.changes), 'study_change_baseline_missing')
    const expected = structuredClone(models.baseline)
    let changed = false
    for (const change of candidate.changes) {
      const section = expected.sections.find((s: RcObject) => s.id === change.section_id)
      check(section, 'study_change_section_invalid')
      for (const [key, value] of Object.entries(change)) {
        if (key === 'section_id') continue
        check(['width_m', 'depth_m', 'cover_m', 'top_bar_count', 'bottom_bar_count', 'bar_area_m2'].includes(key), 'study_change_field_invalid')
        if (value !== null) { check(num(value) && value >= 0, 'study_change_value_invalid'); changed ||= section[key] !== value; section[key] = value }
      }
    }
    check(changed && same(actual, expected), 'study_canonical_change_invalid')
  }
  for (const row of report.rows) {
    if (base.quantities && row.quantities) QUANTITIES.forEach(k => check(close(row.quantity_delta?.[k], row.quantities.totals[k] - base.quantities.totals[k]), 'study_quantity_delta_invalid'))
    else check(row.quantity_delta === null, 'study_quantity_delta_unavailable')
    if (base.material_estimate && row.material_estimate) check(close(row.scoped_estimate_reduction, base.material_estimate.total - row.material_estimate.total), 'study_estimate_delta_invalid')
    else check(row.scoped_estimate_reduction === null, 'study_estimate_delta_unavailable')
  }
  const eligible = report.rows.filter((r: RcObject) => r.selection_eligible)
  if (report.prices !== null) eligible.sort((a: RcObject, b: RcObject) => a.material_estimate.total - b.material_estimate.total || (a.candidate_id < b.candidate_id ? -1 : 1))
  const selected = report.prices !== null && eligible.length ? eligible[0].candidate_id : null
  check(report.selected_candidate_id === selected && report.selection_status === (report.prices === null ? 'prices_unavailable' : selected === null ? 'no_verified_feasible_candidate' : 'selected')
    && report.verified_count === report.rows.filter((r: RcObject) => r.full_reference_verification_pass).length
    && report.status === (report.verified_count === report.rows.length ? 'complete' : 'incomplete') && nat(report.total_wall_ns) && nat(report.total_process_cpu_ns), 'study_selection_invalid')
  return { report, models }
}
