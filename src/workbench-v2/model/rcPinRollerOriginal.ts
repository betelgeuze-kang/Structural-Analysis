import { sha256Bytes, sha256Hex } from './checksum'
import { CLAIMS, document, fields, object, rawValues, same, type RcObject } from './rcJobSchema'

export const RC_PIN_ROLLER_FILE_LIMITS = {
  model: 16 * 1024 * 1024,
  request: 128 * 1024,
  result: 8 * 1024 * 1024,
  checkpoint: 8 * 1024 * 1024,
  verification: 1024 * 1024,
} as const
export type RcPinRollerRole = keyof typeof RC_PIN_ROLLER_FILE_LIMITS
export type RcPinRollerOriginals = Record<RcPinRollerRole, Uint8Array>
const roles = ['model', 'request', 'result', 'checkpoint', 'verification'] as const
const profile = 'planar_serial_horizontal_pin_roller_beam_explicit_rectangular_rc_direct_control.v1'
const hash = (value: unknown): value is string => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value)
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const count = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0
function ensure(value: unknown, code: string): asserts value { if (!value) throw new Error(`rc_pin_roller_${code}`) }

// The CLI hashes compact, sorted Python JSON. Work from the original numeric
// tokens so 1.0, -0.0 and exponent spelling survive the browser's JSON parser.
function canonical(raw: string): string {
  const text = raw.trim()
  if (text[0] === '{') return `{${[...fields(text)]
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, field]) => `${JSON.stringify(key)}:${canonical(field.value)}`).join(',')}}`
  if (text[0] === '[') return `[${rawValues(text).map(canonical).join(',')}]`
  if (text[0] === '"') return JSON.stringify(JSON.parse(text))
  return text
}
function unsigned(raw: string, key: string): string {
  const members = fields(raw)
  ensure(members.delete(key), 'self_hash_missing')
  return `{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([name, field]) => `${JSON.stringify(name)}:${canonical(field.value)}`).join(',')}}`
}
async function selfHash(raw: string, value: RcObject, key: string): Promise<void> {
  ensure(hash(value[key]) && await sha256Hex(unsigned(raw, key)) === value[key], `${key}_mismatch`)
}
function reactionIds(model: RcObject): Array<[string, 'UX' | 'UY']> {
  ensure(model.schema_version === 'structural-analysis-canonical-model.v1'
    && Array.isArray(model.nodes) && model.nodes.length >= 2 && model.nodes.length <= 16
    && Array.isArray(model.supports) && model.supports.length === 2, 'model_boundary_invalid')
  const nodes = model.nodes.map((row: unknown) => object(row).id)
  ensure(nodes.every((id: unknown) => typeof id === 'string' && id.length > 0)
    && new Set(nodes).size === nodes.length, 'model_nodes_invalid')
  const supported = new Map<string, string[]>()
  for (const item of model.supports) {
    const row = object(item)
    ensure(typeof row.node === 'string' && nodes.includes(row.node) && !supported.has(row.node)
      && Array.isArray(row.dofs), 'model_supports_invalid')
    supported.set(row.node, row.dofs)
  }
  ensure([...supported.values()].filter(dofs => same(dofs, ['UX', 'UY']) || same(dofs, ['UY', 'UX'])).length === 1
    && [...supported.values()].filter(dofs => same(dofs, ['UY'])).length === 1, 'model_support_roles_invalid')
  return nodes.flatMap((node: string) => {
    const dofs = supported.get(node)
    return dofs?.length === 2 ? [[node, 'UX'], [node, 'UY']] as Array<[string, 'UX' | 'UY']>
      : dofs?.length === 1 ? [[node, 'UY']] as Array<[string, 'UX' | 'UY']> : []
  })
}
function checkResponse(value: unknown, expected: Array<[string, 'UX' | 'UY']>, label: string): void {
  const row = object(value)
  ensure(Array.isArray(row.support_reactions) && row.support_reactions.length === 3, `${label}_reaction_count_invalid`)
  row.support_reactions.forEach((item: unknown, i: number) => {
    const reaction = object(item)
    ensure(reaction.node_id === expected[i][0] && reaction.dof === expected[i][1]
      && reaction.unit === 'N' && finite(reaction.value_si), `${label}_reaction_invalid`)
  })
  ensure(Array.isArray(row.node_displacements), `${label}_nodes_invalid`)
  const displacements = new Map(row.node_displacements.map((item: unknown) => {
    const node = object(item)
    return [node.node_id, node] as const
  }))
  for (const [node, dof] of expected) {
    const displacement = displacements.get(node)
    ensure(displacement && displacement[`${dof}_m`] === 0, `${label}_restrained_displacement_invalid`)
  }
}

export interface RcPinRollerReview {
  files: RcPinRollerOriginals
  fileHashes: Record<RcPinRollerRole, string>
  reportHash: string
  resultHash: string
  status: 'ready' | 'blocked'
  pin: string
  roller: string
  targets: number[]
  history: RcObject[]
  preload: RcObject | null
  verificationWork: RcObject
}

/** Checks a supplied unsigned CLI verify receipt and its original bytes.
 * Only the Python CLI can perform the claimed fresh solver replay.
 */
export async function reviewRcPinRollerOriginals(files: RcPinRollerOriginals): Promise<RcPinRollerReview> {
  const fileHashes = {} as Record<RcPinRollerRole, string>
  for (const role of roles) {
    const bytes = files[role]
    ensure(bytes instanceof Uint8Array && bytes.byteLength > 0
      && bytes.byteLength <= RC_PIN_ROLLER_FILE_LIMITS[role], `${role}_size_invalid`)
    const digest = await sha256Bytes(bytes)
    ensure(hash(digest), 'hash_unavailable')
    fileHashes[role] = digest
  }
  const model = document(files.model).value
  const requestDoc = document(files.request), request = requestDoc.value
  const resultDoc = document(files.result), result = resultDoc.value
  const checkpointDoc = document(files.checkpoint), checkpoint = checkpointDoc.value
  const reportDoc = document(files.verification), report = reportDoc.value
  const expected = reactionIds(model)
  const pin = expected.find(([_, dof]) => dof === 'UX')![0]
  const roller = expected.find(([node]) => node !== pin)![0]
  ensure(request.schema_version === 'bounded-rc-fiber-direct-control-request.v4'
    && request.experimental_pin_roller_beam === true && request.experimental_two_fixed_endpoints === undefined
    && count(request.control_global_dof) && request.control_global_dof < model.nodes.length * 3
    && request.control_global_dof % 3 !== 2
    && Array.isArray(request.targets_m) && request.targets_m.length > 0 && request.targets_m.length <= 255
    && request.targets_m.every(finite) && count(request.maximum_targets)
    && request.maximum_targets >= request.targets_m.length, 'request_v4_invalid')
  const requestHash = await sha256Hex(canonical(requestDoc.raw))
  const resumeHash = await sha256Hex(unsigned(requestDoc.raw, 'targets_m'))
  ensure(hash(requestHash) && hash(resumeHash), 'request_hash_unavailable')
  // This deliberately accepts only the full typed request serialization. The
  // CLI also accepts abbreviated JSON and expands defaults before hashing it.
  ensure(same(report.request, request)
    && canonical(fields(reportDoc.raw).get('request')?.value ?? '') === canonical(requestDoc.raw)
    && report.request_hash === requestHash && report.resume_contract_hash === resumeHash,
  'full_typed_v4_request_required')
  await selfHash(resultDoc.raw, result, 'result_hash')
  await selfHash(checkpointDoc.raw, checkpoint, 'artifact_hash')
  await selfHash(reportDoc.raw, report, 'report_hash')
  const resultRequestRaw = fields(resultDoc.raw).get('request')?.value
  ensure(resultRequestRaw, 'result_request_missing')
  const configurationRaw = fields(resultRequestRaw).get('configuration')?.value
  ensure(configurationRaw, 'configuration_missing')
  const configurationHash = await sha256Hex(canonical(configurationRaw))
  const configuration = {
    ...object(request.solver_config),
    profile: 'small-displacement-rc-fiber-direct-control.v1',
    control_row_weight: 'F_reference*residual_tolerance/control_tolerance_m',
    augmented_coordinates: '[q_free_m,load_factor_coordinate_scale_m*lambda]',
  }
  ensure(hash(configurationHash) && result.request?.configuration_hash === configurationHash
    && same(result.request?.configuration, configuration), 'configuration_binding_invalid')
  const controlNode = model.nodes[Math.floor(request.control_global_dof / 3)]
  const controlComponent = request.control_global_dof % 3 === 0 ? 'UX' : 'UY'
  ensure(result.schema_version === (request.constant_nodal_loads === undefined
    ? 'bounded-rc-fiber-direct-control-result.v1' : 'bounded-rc-fiber-direct-control-result.v2')
    && ['ready', 'blocked'].includes(result.status) && result.failure === null
    && result.model?.compiler_profile === profile && result.model?.source_format === 'neutral_json'
    && result.model?.input_checksum === fileHashes.model && hash(result.model?.problem_contract_hash)
    && result.request?.experimental_pin_roller_beam === true
    && result.request?.experimental_two_fixed_endpoints === undefined
    && result.request?.restart_input_sha256 === null
    && result.request?.control_global_dof === request.control_global_dof
    && same(result.request?.targets_m, request.targets_m)
    && result.request?.allow_reversals === request.allow_reversals
    && result.request?.maximum_reversals === request.maximum_reversals
    && result.request?.maximum_targets === request.maximum_targets
    && same(result.request?.constant_nodal_loads, request.constant_nodal_loads)
    && same(result.request?.configuration?.newton, request.solver_config?.newton)
    && result.request?.configuration?.control_tolerance_m === request.solver_config?.control_tolerance_m
    && result.request?.configuration?.load_factor_coordinate_scale_m === request.solver_config?.load_factor_coordinate_scale_m
    && result.control?.global_dof === request.control_global_dof
    && result.control?.node_id === controlNode?.id
    && result.control?.component === controlComponent && result.control?.unit === 'm'
    && same(result.claims, CLAIMS), 'result_source_invalid')
  const scope = result.path?.scope
  ensure(scope && same(scope, checkpoint.scope), 'checkpoint_scope_mismatch')
  ensure(scope.allow_reversals === request.allow_reversals
    && scope.maximum_reversals === request.maximum_reversals
    && scope.maximum_targets === request.maximum_targets
    && scope.configuration_hash === configurationHash
    && same(scope.configuration, configuration)
    && scope.control_global_dof === request.control_global_dof
    && scope.control_unit === 'm'
    && scope.problem_contract_hash === result.model.problem_contract_hash,
  'scope_source_policy_invalid')
  ensure(result.checkpoint?.sha256 === fileHashes.checkpoint
    && result.checkpoint?.byte_length === files.checkpoint.byteLength
    && checkpoint.scope?.problem_contract_hash === result.model.problem_contract_hash
    && checkpoint.artifact_hash === result.path?.restart_artifact_hash
    && same(checkpoint.accepted_targets_m, result.path?.accepted_target_prefix_m), 'checkpoint_binding_invalid')
  ensure(Array.isArray(result.response_history) && result.response_history.length > 0
    && result.response_history.length <= request.targets_m.length
    && same(result.terminal_response, result.response_history[result.response_history.length - 1])
    && same(result.path?.accepted_target_prefix_m, request.targets_m.slice(0, result.response_history.length))
    && result.path?.status === result.status, 'history_binding_invalid')
  const complete = result.status === 'ready'
  ensure(result.contract_pass === complete && (complete ? result.response_history.length === request.targets_m.length : true), 'path_status_invalid')
  result.response_history.forEach((row: unknown, i: number) => checkResponse(row, expected, `history_${i}`))
  const preload = request.constant_nodal_loads === undefined ? null : object(result.preload_response)
  ensure(request.constant_nodal_loads === undefined ? result.preload_response === undefined : preload !== null, 'preload_invalid')
  if (preload) checkResponse(preload, expected, 'preload')
  const inputs = report.inputs
  ensure(report.schema_version === 'bounded-rc-fiber-direct-control-cli-report.v1'
    && report.operation === 'verify' && report.analysis_performed_by_cli === false
    && report.analysis_api_timing === null && report.verification_performed === true
    && report.result_max_bytes === 512 * 1024 * 1024
    && Array.isArray(inputs) && inputs.length === 4
    && same(inputs.map((item: RcObject) => item.role), ['request', 'model', 'result', 'checkpoint']), 'verify_report_invalid')
  for (const role of ['request', 'model', 'result', 'checkpoint'] as const) {
    const row = object(inputs.find((item: RcObject) => item.role === role))
    ensure(row.byte_length === files[role].byteLength && row.sha256 === fileHashes[role]
      && typeof row.path === 'string' && row.path.length > 0, `${role}_receipt_binding_invalid`)
  }
  const verification = object(report.verification)
  ensure(report.status === 'valid_artifact' && report.artifact_contract_pass === true
    && report.contract_pass === complete && verification.schema_version === 'bounded-rc-fiber-direct-control-validation.v1'
    && verification.status === 'valid_artifact' && verification.artifact_contract_pass === true
    && verification.contract_pass === complete && verification.physical_path_complete === complete
    && verification.fresh_source_execution_invoked === true && verification.solver_replay_performed === true
    && verification.unavailable_execution_work === false
    && verification.verification_scope === 'fresh_complete_request_solver_and_original_transition_replay'
    && verification.verified_result_hash === result.result_hash
    && same(verification.errors, []) && same(verification.claims, CLAIMS), 'fresh_replay_receipt_invalid')
  const work = object(verification.replay_control_work)
  ensure(count(work.attempted_step_count) && work.attempted_step_count > 0
    && count(work.known_linear_solve_count) && count(work.known_newton_iteration_count)
    && count(work.unknown_solver_work_attempt_count), 'replay_work_invalid')
  return { files, fileHashes, reportHash: report.report_hash, resultHash: result.result_hash,
    status: result.status, pin, roller, targets: request.targets_m,
    history: result.response_history, preload, verificationWork: work }
}
