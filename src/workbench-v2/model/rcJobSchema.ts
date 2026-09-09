import { sha256Bytes, sha256Hex } from './checksum'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import type { WorkbenchJobView } from './jobSchema'

// Producer objects are checked at this boundary; only the selected stored row
// is sent to React. These objects never grant numerical execution authority.
export type RcObject = Record<string, any>
export interface RcJobSummary {
  resultHash: string
  sourceRevision: string
  targets: number[]
  control: { node_id: string; component: string; unit: string }
  reservedInvocations: number
  confirmedInvocations: number
  knownCoreCalls: number
  knownNewtonIterations: number
  unknownWork: boolean
  artifactRoles: string[]
}
export type RcArtifacts = Record<string, Uint8Array>
const AUTHORITY = {
  design_authority: false, experimental_small_displacement_rc_control: true,
  independent_execution_authentication: false, independent_physical_validation: false,
  production_promotion_eligible: false, public_j1_j5_authority: false,
  release_approved: false, service_numerical_verification_performed: false,
  trusted_worker_verification_attestation: true, workbench_execution: false,
}
export const CLAIMS = {
  design_authority: false, experimental_small_displacement_rc_control: true,
  general_cyclic_validation: false, global_capacity_verified: false,
  hashes_authenticate_source: false, independent_physical_validation: false,
  performance_improvement: false, production_promotion_eligible: false,
  public_j1_j5_authority: false, release_approved: false,
}
export const PATH_CLAIMS = {
  design_authority: false, experimental_small_displacement_rc_control: true,
  general_cyclic_material_validation: false, global_capacity_verified: false,
  hashes_authenticate_source: false, independent_physical_validation: false,
  performance_improvement_claimed: false, production_promotion_eligible: false,
  public_j1_j5_authority: false,
}
export function check(value: unknown, code: string): asserts value {
  if (!value) throw new Error(`rc_review_${code}`)
}
export function object(value: unknown): RcObject {
  check(value && typeof value === 'object' && !Array.isArray(value), 'object_invalid')
  return value as RcObject
}
export function same(left: unknown, right: unknown): boolean {
  if (left === right) return true
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object') return false
  if (Array.isArray(left) !== Array.isArray(right)) return false
  const a = Object.keys(left), b = Object.keys(right)
  return a.length === b.length && a.every((key) => Object.prototype.hasOwnProperty.call(right, key)
    && same((left as RcObject)[key], (right as RcObject)[key]))
}
export function finite(value: unknown, depth = 0): void {
  check(depth <= 64, 'depth_exceeded')
  if (typeof value === 'number') check(Number.isFinite(value), 'number_invalid')
  else if (value && typeof value === 'object') Object.values(value).forEach((item) => finite(item, depth + 1))
}
export function document(bytes: Uint8Array): { raw: string; value: RcObject } {
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  const value = object(parseNativeJsonStrict(raw))
  finite(value)
  return { raw, value }
}

/** Slice already strict-validated JSON without rounding Python numeric tokens.
 * Producer artifacts are compact, key-sorted JSON. We verify their original
 * representation; JSON.stringify would change 1.0, -0.0 and exponent spellings.
 */
export function rawValues(raw: string): string[] {
  const values: string[] = []
  let start = 1, depth = 0, quoted = false, escaped = false
  for (let i = 1; i < raw.length - 1; i += 1) {
    const c = raw[i]
    if (quoted) {
      if (escaped) escaped = false
      else if (c === '\\') escaped = true
      else if (c === '"') quoted = false
    } else if (c === '"') quoted = true
    else if (c === '[' || c === '{') depth += 1
    else if (c === ']' || c === '}') depth -= 1
    else if (c === ',' && depth === 0) { values.push(raw.slice(start, i)); start = i + 1 }
  }
  if (start < raw.length - 1) values.push(raw.slice(start, -1))
  return values
}
export function fields(raw: string): Map<string, { member: string; value: string }> {
  return new Map(rawValues(raw.trim()).map((member) => {
    const key = /^\s*("(?:[^"\\]|\\.)*")\s*:/.exec(member)
    check(key, 'raw_field_invalid')
    return [JSON.parse(key[1]), { member, value: member.slice(key[0].length).trim() }]
  }))
}
export async function selfHash(raw: string, value: RcObject, key: string): Promise<void> {
  const members = fields(raw)
  check(members.has(key), 'hash_missing')
  members.delete(key)
  check(await sha256Hex(`{${[...members.values()].map((item) => item.member).join(',')}}`) === value[key], 'logical_hash_mismatch')
}
function nat(value: unknown): value is number { return Number.isSafeInteger(value) && (value as number) >= 0 }
function hash(value: unknown): boolean { return typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value) }

export async function validateRcJobArtifacts(job: WorkbenchJobView, artifacts: RcArtifacts): Promise<{
  summary: RcJobSummary; history: RcObject[]; terminalBytes: Uint8Array
}> {
  check(job.status === 'succeeded' && job.result && job.evidence, 'publication_invalid')
  for (const role of ['request', 'checkpoint', 'result', 'evidence'] as const) {
    const ref = job[role], bytes = artifacts[role]
    if (!ref) { check(!bytes, 'unexpected_artifact'); continue }
    check(bytes && bytes.byteLength === ref.byte_length, 'byte_length_mismatch')
    check(await sha256Bytes(bytes) === ref.content_hash, 'byte_hash_mismatch')
  }
  const requestDoc = document(artifacts.request), request = requestDoc.value
  const resultDoc = document(artifacts.result), result = resultDoc.value
  const evidence = document(artifacts.evidence).value
  check(request.schema_version === 'structural-analysis-job-request.v3'
    && request.operation === 'bounded_rc_fiber_direct_control'
    && request.result_contract === 'bounded-rc-fiber-job-result.v1', 'request_invalid')
  const supplied = object(request.config), solver = supplied.solver_config === undefined ? {} : object(supplied.solver_config)
  // v1 request defaults match the Python decoder; original request bytes remain
  // unchanged and hash-bound. Only semantic comparisons use these defaults.
  const config = {
    allow_reversals: false, maximum_reversals: 0, maximum_targets: 255, ...supplied,
    solver_config: {
      control_tolerance_m: 1e-12, load_factor_coordinate_scale_m: 0.001, ...solver,
      newton: {
        residual_tolerance: 1e-10, increment_tolerance: 1e-12, max_iterations: 25,
        line_search_alphas: [1, 0.5, 0.25, 0.125, 0.0625, 0.03125],
        matrix_backend: 'numpy_linalg_solve_dense', terminal_polishing: false,
        ...(solver.newton === undefined ? {} : object(solver.newton)),
      },
    },
  } as RcObject
  const execution = object(request.execution_config)
  check(config.schema_version === 'bounded-rc-fiber-direct-control-request.v1'
    && request.model.schema_version === 'structural-analysis-canonical-model.v1'
    && typeof config.solver_config.control_tolerance_m === 'number'
    && config.solver_config.control_tolerance_m > 0, 'request_config_invalid')
  const targets = config.targets_m
  check(Array.isArray(targets) && targets.length > 0 && targets.length <= 255
    && targets.every((n: unknown) => typeof n === 'number' && Number.isFinite(n)), 'targets_invalid')
  check(nat(execution.chunk_target_count) && execution.chunk_target_count >= 1
    && execution.chunk_target_count <= 255 && nat(execution.maximum_api_invocations)
    && execution.maximum_api_invocations >= 2 && execution.maximum_api_invocations <= 4096, 'execution_config_invalid')
  await selfHash(resultDoc.raw, result, 'result_hash')
  check(result.schema_version === 'bounded-rc-fiber-job-result.v1'
    && result.profile === 'bounded_rc_fiber_durable_chunk_execution.v1'
    && result.status === 'ready' && result.contract_pass === true
    && result.request_hash === job.request.content_hash && result.case_id === request.case_id
    && result.source_revision === request.source_revision && /^[a-f0-9]{40}$/.test(result.source_revision)
    && result.source_revision_is_attestation === false && same(result.authority, AUTHORITY)
    && same(result.control_targets, targets) && result.completed_target_count === targets.length
    && result.total_target_count === targets.length && job.progress.completed_steps === targets.length
    && job.progress.total_steps === targets.length, 'result_binding_invalid')
  const budget = object(result.execution_budget)
  check(result.execution_budget_unit === 'reserved_api_invocations'
    && budget.maximum_attempts === execution.maximum_api_invocations
    && nat(budget.reserved_attempts) && nat(budget.remaining_attempts)
    && budget.reserved_attempts + budget.remaining_attempts === budget.maximum_attempts, 'budget_invalid')
  const report = object(evidence.validation_report)
  check(evidence.schema_version === 'structural-analysis-job-completion-evidence.v1'
    && evidence.validator_id === 'structural_analysis.execution.rc_fiber_job_contract.validate_rc_fiber_job_result'
    && evidence.job_id === job.job_id && evidence.request_hash === job.request.content_hash
    && evidence.result_artifact_hash === job.result.content_hash
    && evidence.checkpoint_hash === (job.checkpoint?.content_hash ?? null)
    && evidence.contract_pass === true && evidence.solver_truth_owner === 'structural_analysis_core'
    && report.schema_version === 'bounded-rc-fiber-job-validation-report.v1'
    && report.contract_pass === true && report.request_hash === result.request_hash
    && report.result_hash === result.result_hash && same(report.authority, AUTHORITY)
    && report.completed_target_count === targets.length && report.total_target_count === targets.length
    && same(report.execution_budget, budget) && report.execution_budget_unit === result.execution_budget_unit, 'evidence_invalid')
  const api = object(result.api_result), apiRaw = fields(resultDoc.raw).get('api_result')!.value
  await selfHash(apiRaw, api, 'result_hash')
  check(api.schema_version === 'bounded-rc-fiber-direct-control-result.v1'
    && api.status === 'ready' && api.contract_pass === true && api.failure === null
    && same(api.unsupported_features, []) && same(api.claims, CLAIMS), 'api_invalid')
  check(await sha256Hex(fields(requestDoc.raw).get('model')!.value) === api.model.input_checksum
    && api.model.canonical_model_checksum === api.model.input_checksum, 'model_binding_invalid')
  check(api.control.global_dof === config.control_global_dof && api.control.unit === 'm'
    && ['UX', 'UY'].includes(api.control.component), 'control_invalid')
  const binary = atob(result.terminal_checkpoint_artifact_base64)
  check(binary.length <= 128 * 1024 * 1024, 'native_too_large')
  const terminalBytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
  const nativeDoc = document(terminalBytes), native = nativeDoc.value
  await selfHash(nativeDoc.raw, native, 'artifact_hash')
  const terminalHash = await sha256Bytes(terminalBytes)
  check(api.checkpoint.sha256 === terminalHash && api.checkpoint.byte_length === terminalBytes.byteLength
    && report.terminal_checkpoint_sha256 === terminalHash
    && native.schema_version === 'stateful-fiber-frame2d-control-restart.v1'
    && same(native.claims, PATH_CLAIMS) && same(api.path.claims, PATH_CLAIMS)
    && same(native.accepted_targets_m, targets) && Array.isArray(native.accepted_step_bindings)
    && native.accepted_step_bindings.length === targets.length
    && native.terminal_checkpoint.epoch === targets.length
    && await sha256Hex(fields(nativeDoc.raw).get('terminal_checkpoint')!.value) === native.terminal_checkpoint_sha256,
  'native_binding_invalid')
  const history = api.response_history
  check(Array.isArray(history) && history.length === targets.length
    && same(api.terminal_response, history[history.length - 1])
    && api.path.status === 'ready'
    && same(api.path.accepted_target_prefix_m, targets)
    && same(api.path.final_checkpoint, native.terminal_checkpoint), 'history_binding_invalid')
  const receipts = result.receipts
  check(Array.isArray(receipts) && receipts.length > 0 && receipts.length <= targets.length
    && same(report.receipt_hashes, receipts.map((r: RcObject) => r.receipt_hash)), 'receipts_invalid')
  const receiptRaws = rawValues(fields(resultDoc.raw).get('receipts')!.value)
  let completed = 0, previousOrdinal = 0, restart: string | null = null, core = 0, iterations = 0, unknown = false
  for (const [index, item] of receipts.entries()) {
    const receipt = object(item)
    await selfHash(receiptRaws[index], receipt, 'receipt_hash')
    const after = Math.min(targets.length, completed + execution.chunk_target_count)
    const validation = object(receipt.validation_report)
    check(receipt.completed_before === completed && receipt.completed_after === after
      && receipt.job_request_hash === result.request_hash && receipt.restart_input_sha256 === restart
      && nat(receipt.analysis_ordinal) && receipt.analysis_ordinal > previousOrdinal
      && nat(receipt.verification_ordinal) && receipt.verification_ordinal > receipt.analysis_ordinal
      && receipt.verification_ordinal <= budget.reserved_attempts
      && same(receipt.api_request.targets_m, targets.slice(completed, after))
      && receipt.api_request.restart_input_sha256 === restart
      && receipt.api_request.control_global_dof === config.control_global_dof
      && receipt.api_request.allow_reversals === config.allow_reversals
      && receipt.api_request.maximum_reversals === config.maximum_reversals
      && receipt.api_request.maximum_targets === config.maximum_targets
      && same(receipt.api_request.configuration.newton, config.solver_config.newton)
      && receipt.api_request.configuration.control_tolerance_m === config.solver_config.control_tolerance_m
      && receipt.api_request.configuration.load_factor_coordinate_scale_m === config.solver_config.load_factor_coordinate_scale_m
      && same(receipt.control, api.control) && same(receipt.model_binding, api.model)
      && validation.schema_version === 'bounded-rc-fiber-direct-control-validation.v1'
      && validation.contract_pass === true && validation.artifact_contract_pass === true
      && validation.fresh_source_execution_invoked === true && validation.solver_replay_performed === true
      && validation.physical_path_complete === true && validation.unavailable_execution_work === false
      && same(validation.errors, []) && same(validation.claims, CLAIMS)
      && validation.verified_result_hash === receipt.result_hash
      && receipt.checkpoint_state_hash === native.accepted_step_bindings[after - 1].accepted_checkpoint_hash,
    'receipt_binding_invalid')
    for (const metrics of [receipt.analysis_metrics, receipt.verification_metrics]) {
      const work = object(metrics.control_work ?? metrics.replay_control_work)
      check(Object.values(work).every(nat) && nat(work.attempted_step_count)
        && nat(work.known_newton_iteration_count) && nat(work.unknown_solver_work_attempt_count), 'work_invalid')
      core += work.attempted_step_count; iterations += work.known_newton_iteration_count
      unknown ||= work.unknown_solver_work_attempt_count > 0
    }
    completed = after; previousOrdinal = receipt.verification_ordinal; restart = receipt.checkpoint_sha256
  }
  const tail = receipts[receipts.length - 1]
  check(completed === targets.length && restart === terminalHash
    && tail.checkpoint_byte_length === terminalBytes.byteLength
    && tail.result_hash === api.result_hash && tail.result_artifact_sha256 === await sha256Hex(apiRaw)
    && same(tail.api_request, api.request) && same(tail.analysis_metrics, api.metrics), 'receipt_tail_invalid')
  if (job.checkpoint) {
    const checkpointDoc = document(artifacts.checkpoint), checkpoint = checkpointDoc.value
    await selfHash(checkpointDoc.raw, checkpoint, 'checkpoint_hash')
    check(checkpoint.schema_version === 'bounded-rc-fiber-job-checkpoint.v1'
      && checkpoint.status === 'checkpointed' && checkpoint.contract_pass === true
      && checkpoint.request_hash === result.request_hash
      && checkpoint.resume_contract_hash === result.resume_contract_hash
      && job.resume_contract_hash === result.resume_contract_hash
      && checkpoint.completed_target_count < targets.length && checkpoint.completed_target_count > 0
      && Array.isArray(checkpoint.receipts) && checkpoint.receipts.length > 0
      && checkpoint.completed_target_count === checkpoint.receipts[checkpoint.receipts.length - 1].completed_after
      && same(checkpoint.authority, AUTHORITY) && same(checkpoint.control_targets, targets)
      && same(checkpoint.receipts, receipts.slice(0, checkpoint.receipts.length)), 'checkpoint_prefix_invalid')
    const prefixBytes = Uint8Array.from(atob(checkpoint.terminal_checkpoint_artifact_base64), (c) => c.charCodeAt(0))
    const prefixTail = checkpoint.receipts[checkpoint.receipts.length - 1]
    check(await sha256Bytes(prefixBytes) === prefixTail.checkpoint_sha256
      && prefixBytes.byteLength === prefixTail.checkpoint_byte_length, 'checkpoint_native_invalid')
  }
  validateRcAcceptedHistory(api, native, request.model, config)
  check(nat(core) && nat(iterations), 'work_total_invalid')
  return { history, terminalBytes, summary: {
    resultHash: result.result_hash, sourceRevision: result.source_revision,
    targets, control: api.control, reservedInvocations: budget.reserved_attempts,
    confirmedInvocations: receipts.length * 2, knownCoreCalls: core, knownNewtonIterations: iterations,
    unknownWork: unknown || budget.reserved_attempts !== receipts.length * 2,
    artifactRoles: [...Object.keys(artifacts), 'terminal'],
  } }
}

/** Shared stored-history binding checks; no numerical execution. */
export function validateRcAcceptedHistory(api: RcObject, native: RcObject, model: RcObject, config: RcObject): RcObject[] {
  const history = api.response_history, targets = config.targets_m
  const nodeIds = model.nodes.map((n: RcObject) => n.id)
  const memberIds = model.elements.map((n: RcObject) => n.id)
  for (const [index, entry] of history.entries()) {
    const row = object(entry), binding = native.accepted_step_bindings[index]
    check(row.epoch === index + 1 && row.step_index === index + 1
      && typeof row.load_factor === 'number'
      && row.checkpoint_hash === binding.accepted_checkpoint_hash
      && row.parent_checkpoint_hash === binding.parent_checkpoint_hash
      && row.source_step_hash === binding.step_hash && hash(row.replayed_assembly_hash)
      && binding.target_control_displacement_m === targets[index]
      && (index === 0 || row.parent_checkpoint_hash === history[index - 1].checkpoint_hash)
      && row.recovery_scope === 'exact_previous_parent_original_newton_coordinates_constitutive_transition', 'epoch_binding_invalid')
    for (const name of ['node_displacements', 'support_reactions', 'member_end_forces', 'section_results', 'fiber_results']) {
      check(Array.isArray(row[name]) && row[name].length > 0 && row[name].length <= 100000, 'physical_rows_invalid')
    }
    check(same(row.node_displacements.map((n: RcObject) => n.node_id).sort(), [...nodeIds].sort())
      && same(row.member_end_forces.map((m: RcObject) => m.member_id).sort(), [...memberIds].sort())
      && row.fiber_results.length === row.material_point_count, 'entity_binding_invalid')
    for (const n of row.node_displacements) check(['UX_m', 'UY_m', 'UZ_m', 'RX_rad', 'RY_rad', 'RZ_rad'].every((key) => typeof n[key] === 'number'), 'displacement_invalid')
    const controlled = row.node_displacements.find((n: RcObject) => n.node_id === api.control.node_id)
    check(controlled && Math.abs(controlled[`${api.control.component}_m`] - targets[index]) <= config.solver_config.control_tolerance_m, 'controlled_target_invalid')
    for (const r of row.support_reactions) check(nodeIds.includes(r.node_id) && ['UX', 'UY', 'RZ'].includes(r.dof)
      && r.unit === (r.dof === 'RZ' ? 'N*m' : 'N') && typeof r.value_si === 'number', 'reaction_invalid')
    for (const m of row.member_end_forces) check(nodeIds.includes(m.node_i) && nodeIds.includes(m.node_j)
      && ['local_end_i', 'local_end_j'].every((end) => ['FX_N', 'FY_N', 'MZ_Nm'].every((key) => typeof object(m[end])[key] === 'number')), 'member_invalid')
    for (const s of row.section_results) check(memberIds.includes(s.member_id) && nat(s.integration_point_index)
      && ['axial_strain', 'curvature_z_per_m', 'axial_force_N', 'moment_z_Nm'].every((key) => typeof s[key] === 'number'), 'section_invalid')
    for (const f of row.fiber_results) check(memberIds.includes(f.member_id) && nat(f.integration_point_index)
      && nat(f.fiber_index) && typeof f.fiber_id === 'string' && ['steel', 'concrete'].includes(f.material_kind)
      && typeof f.strain === 'number' && typeof f.stress_MPa === 'number'
      && hash(object(f.material_state).state_hash), 'material_invalid')
    const identities = row.fiber_results.map((f: RcObject) => JSON.stringify([f.member_id, f.integration_point_index, f.fiber_index, f.fiber_id, f.material_kind]))
    check(new Set(identities).size === identities.length
      && same(identities, history[0].fiber_results.map((f: RcObject) => JSON.stringify([f.member_id, f.integration_point_index, f.fiber_index, f.fiber_id, f.material_kind]))), 'material_identity_invalid')
    for (const f of row.fiber_results) {
      const state = f.material_state, steel = f.material_kind === 'steel'
      const names = steel ? ['accumulated_plastic_strain', 'backstress_mpa', 'plastic_strain']
        : ['compressive_damage', 'compressive_history_strain', 'tensile_damage', 'tensile_history_strain']
      check(state.schema_version === (steel ? 'uniaxial-combined-hardening-state.v1' : 'uniaxial-asymmetric-concrete-damage-state.v1')
        && names.every((key) => typeof state[key] === 'number') && typeof state.dissipated_energy_density_mj_per_m3 === 'number', 'material_state_invalid')
    }
  }
  check(history[history.length - 1].checkpoint_hash === native.terminal_checkpoint.state_hash
    && history[history.length - 1].load_factor === native.terminal_checkpoint.load_factor, 'terminal_state_invalid')
  return history
}
