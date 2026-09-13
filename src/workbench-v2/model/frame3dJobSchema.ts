// Read-only validation of a service-validated experimental Frame3D job bundle.
// Exact artifact bytes are hashed. Python float-bearing logical hashes are
// bound by the service report, never reconstructed from browser JSON numbers.
import Ajv2020 from 'ajv/dist/2020.js'
import resultSchema from '../../structural_analysis/schemas/bounded_frame3d_direct_control_result_v2.schema.json' assert { type: 'json' }
import checkpointV1 from '../../structural_analysis/schemas/bounded_frame3d_direct_control_checkpoint_v1.schema.json' assert { type: 'json' }
import checkpointV2 from '../../structural_analysis/schemas/bounded_frame3d_direct_control_checkpoint_v2.schema.json' assert { type: 'json' }
import { canonicalJson, sha256Bytes, sha256Hex } from './checksum'
import { type WorkbenchJobView, validateWorkbenchJobView } from './jobSchema'
import { parseNativeJsonStrict } from './nativeFrameProvider'

type Obj = Record<string, unknown>
export type Frame3DDof = 'UX' | 'UY' | 'UZ' | 'RX' | 'RY' | 'RZ'
export interface Frame3DNodeDisplacement {
  node_id: string
  UX_m: number; UY_m: number; UZ_m: number
  RX_rad: number; RY_rad: number; RZ_rad: number
}
export interface Frame3DMaterialState {
  member_id: string; material_id: string; plastic_strain: number
  backstress_mpa: number; accumulated_plastic_strain: number
  dissipated_energy_density_mj_per_m3: number; state_hash: string
}
export interface Frame3DTargetResult extends Obj {
  schema_version: 'bounded-frame3d-direct-control-result.v2'
  status: 'ready'; contract_pass: true; result_hash: string; model_hash: string
  source_binding: Obj & { node_ids: string[]; member_ids: string[]; member_material_ids: string[] }
  control: Obj & {
    control_node_id: string; control_dof: Frame3DDof; control_unit: 'm' | 'rad'
    control_global_dof: number; control_targets: number[]; solver_config: Obj
    request_hash: string; resume_contract_hash: string
  }
  metrics: Obj & {
    solve_attempt_count: number; accepted_checkpoint_count: number
    final_load_factor: number; final_control_coordinate: number
    scaled_residual_inf_norm: number; scaled_residual_tolerance: number
    maximum_accumulated_plastic_strain: number
  }
  node_displacements: Frame3DNodeDisplacement[]
  support_reactions: Array<{ node_id: string; dof: Frame3DDof; unit: 'kN' | 'kN_m'; value: number }>
  material_states: Frame3DMaterialState[]
  checkpoint_artifact: Obj & { checkpoint_hash: string; artifact_hash: string; byte_length: number }
  authority: typeof AUTHORITY
}
export interface Frame3DJobReceipt extends Obj {
  target_index: number; authored_target: number; api_result: Frame3DTargetResult
  receipt_hash: string; result_hash: string; checkpoint_sha256: string
  checkpoint_artifact_base64: string; reserved_attempt_ordinals: number[]
}
export interface Frame3DJobPayload extends Obj {
  schema_version: 'bounded-frame3d-job-result.v1'
  status: 'ready'; contract_pass: true; case_id: string
  request_hash: string; result_hash: string; resume_contract_hash: string
  source_revision: string; source_revision_is_attestation: false
  control_targets: number[]; completed_target_count: number; total_target_count: number
  receipts: Frame3DJobReceipt[]; terminal_checkpoint_artifact_base64: string
  execution_budget: { maximum_attempts: number; reserved_attempts: number; remaining_attempts: number }
  authority: typeof AUTHORITY
}
export interface Frame3DJobReview {
  payload: Frame3DJobPayload; terminalResult: Frame3DTargetResult
  terminalCheckpointBytes: Uint8Array
  completedTargetCount: number; totalTargetCount: number
  reservedAttempts: number; confirmedAttempts: number; abandonedReservations: number
  controlNodeId: string; controlDof: Frame3DDof; controlUnit: 'm' | 'rad'
  targets: number[]; sourceRevision: string; requestHash: string; resultHash: string
  terminalCheckpointSha256: string
}

const PROFILE = 'bounded_frame3d_durable_authored_target_execution.v1'
const API_PROFILE = 'bounded_frame3d_direct_displacement_control_model_ir_api.v1'
const DIRECT_PROFILE = 'stateful_corotational_frame3d_sparse_direct_displacement_control.v1'
const FRAME_PROFILE = 'stateful_axial_material_corotational_timoshenko_frame3d_native_coo_csr.v1'
const VALIDATOR = 'structural_analysis.execution.frame3d_job_contract.validate_frame3d_job_result'
const HASH = /^sha256:[0-9a-f]{64}$/
const DOFS = ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ'] as const
const NODE_COMPONENTS = ['UX_m', 'UY_m', 'UZ_m', 'RX_rad', 'RY_rad', 'RZ_rad'] as const
const MATERIAL_COMPONENTS = ['plastic_strain', 'backstress_mpa', 'accumulated_plastic_strain', 'dissipated_energy_density_mj_per_m3', 'state_hash'] as const
const MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024
const AUTHORITY = {
  candidate_api_exposed: true, capability_registry_public: false,
  workbench_execution: false, numerical_authority: 'bounded_candidate',
  recovery_authority: 'node_and_support_candidate', external_vv_level: 0,
  independent_operator_attached: false, design_authority: false,
  formal_verification_level_2: false, release_eligible: false,
} as const
const JOB_BOUNDARY = 'Durable authored-target progress and exact retained candidate API artifacts; '
  + 'per-target result requests remain local to their executed targets. Reserved '
  + 'attempts may include abandoned work and are not an exact completed-work count. '
  + 'Internal consistency is not independent execution authentication, full-history '
  + 'replay verification, public/Workbench/design authority, external validation, '
  + 'or source attestation.'
const SERVICE_BOUNDARY = 'The job service owns durable orchestration state and content integrity only. '
  + 'It does not define solver truth, engineering acceptance, design-code '
  + 'compliance, distributed consensus, or release readiness.'
const API_BOUNDARY = 'This candidate API executes the source-bound bounded ModelIR v2 Frame3D '
  + 'single-coordinate direct displacement-control profile and returns node kinematics, '
  + 'support reactions, material-state summaries, and an exact checkpoint/resume '
  + 'artifact when the internal boundary permits it. The API optionally admits bounded '
  + 'reversal paths only for exact bilinear combined-hardening steel and uses a v2 '
  + 'rolling target-chain artifact; the v1 artifact remains monotonic-only. This is '
  + 'not a general cyclic-material claim. Persisted artifacts require finite '
  + 'repository-canonical JSON bytes and a deterministic unloaded checkpoint '
  + 'genesis/parent contract, complete ordered entity identities, and raw-to-typed '
  + 'checkpoint, resume-binding, and top-level artifact-envelope numeric identity. '
  + 'The API remains experimental and non-public in the capability registry. It does '
  + 'not support prescribed supports, offsets, releases, multiple controls, arc length, '
  + 'or Workbench execution. Same-operator OpenSees direct-control comparisons are '
  + 'internal supplemental evidence only. Artifact hashes are unsigned internal '
  + 'consistency checks, not authentication against an actor who recomputes them. '
  + 'Independent review, design authority, formal Level 2, and release authority '
  + 'remain absent.'
const ajv = new Ajv2020({ strict: false, allErrors: false })
const validRawResult = ajv.compile(resultSchema)
const validCheckpointV1 = ajv.compile(checkpointV1)
const validCheckpointV2 = ajv.compile(checkpointV2)

function ensure(condition: unknown, label: string): asserts condition {
  if (!condition) throw new Error(`frame3d_job_invalid: ${label}`)
}
function object(value: unknown, label: string): Obj {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value), label)
  return value as Obj
}
function exact(value: unknown, keys: readonly string[], label: string): Obj {
  const obj = object(value, label)
  ensure(Object.keys(obj).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(obj, key)), `${label} fields`)
  return obj
}
function same(actual: unknown, expected: unknown, label: string): void {
  // Semantic equality is deliberate. It is not Python canonical-hash replay.
  ensure(canonicalJson(actual) === canonicalJson(expected), label)
}
function integer(value: unknown, minimum: number, maximum: number, label: string): number {
  ensure(typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum && value <= maximum, label)
  return value
}
function finite(value: unknown, label: string, minimum = -Infinity): number {
  ensure(typeof value === 'number' && Number.isFinite(value) && value >= minimum, label)
  return value
}
function positive(value: unknown, label: string): number {
  const number = finite(value, label)
  ensure(number > 0, label)
  return number
}
function hash(value: unknown, label: string): string {
  ensure(typeof value === 'string' && HASH.test(value), label)
  return value
}
function array(value: unknown, minimum: number, maximum: number, label: string): unknown[] {
  ensure(Array.isArray(value) && value.length >= minimum && value.length <= maximum, label)
  return value
}
function finiteTree(value: unknown): void {
  const pending: Array<[unknown, number]> = [[value, 0]]
  while (pending.length) {
    const [item, depth] = pending.pop()!
    ensure(depth <= 128, 'JSON depth')
    if (typeof item === 'number') ensure(Number.isFinite(item), 'finite JSON numbers')
    else if (item && typeof item === 'object') {
      for (const child of Object.values(item)) pending.push([child, depth + 1])
    } else ensure(item === null || typeof item === 'string' || typeof item === 'boolean', 'JSON value type')
  }
}
async function requiredDigest(bytes: Uint8Array): Promise<string> {
  const digest = await sha256Bytes(bytes)
  if (digest === null) throw new Error('frame3d_job_integrity_unavailable')
  return digest
}
async function integerStringDigest(value: unknown): Promise<string> {
  // Call sites contain only strings, booleans, arrays, and bounded integers.
  const digest = await sha256Hex(canonicalJson(value))
  if (digest === null) throw new Error('frame3d_job_integrity_unavailable')
  return digest
}
function decodeCheckpoint(value: unknown): Uint8Array {
  ensure(typeof value === 'string' && value.length > 0 && value.length <= 4 * Math.ceil(MAX_CHECKPOINT_BYTES / 3), 'checkpoint base64 length')
  ensure(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value), 'checkpoint base64 syntax')
  let binary: string
  try { binary = atob(value) } catch { throw new Error('frame3d_job_invalid: checkpoint base64') }
  ensure(binary.length <= MAX_CHECKPOINT_BYTES && btoa(binary) === value, 'canonical checkpoint base64')
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}
function lineSearch(value: unknown, policy: string): void {
  const row = exact(value, ['policy', 'alphas'], 'line search')
  same(row.policy, policy, 'line search policy')
  let previous = Infinity
  // The Python configuration has no alpha-count limit; transport byte bounds
  // belong to the provider. Preserve every otherwise valid finite schedule.
  const alphas = array(row.alphas, 1, Number.MAX_SAFE_INTEGER, 'line search alphas')
  same(alphas[0], 1, 'first line search alpha')
  for (const alpha of alphas) {
    const number = positive(alpha, 'line search alpha')
    ensure(number <= 1 && number < previous, 'line search decreasing alphas')
    previous = number
  }
}
function solverConfiguration(value: unknown, total: number, maximumAttempts: number): Obj {
  const solver = exact(value, [
    'profile', 'frame_config', 'control_relative_tolerance', 'control_absolute_tolerance_m',
    'control_absolute_tolerance_rad', 'minimum_control_reference_m', 'load_factor_increment_tolerance',
    'maximum_iterations', 'maximum_path_targets', 'path_direction', 'line_search', 'control_dof_count',
    'load_factor_coordinate_scale', 'target_cutback', 'target_cutback_supported', 'regularization_allowed', 'fallback_allowed',
  ], 'solver configuration')
  same(solver.profile, DIRECT_PROFILE, 'direct profile')
  same(solver.control_dof_count, 1, 'single control')
  same(solver.load_factor_coordinate_scale, 'characteristic_length_m', 'control scale')
  same(solver.target_cutback_supported, true, 'cutback support')
  same(solver.regularization_allowed, false, 'regularization')
  same(solver.fallback_allowed, false, 'fallback')
  integer(solver.maximum_path_targets, total, 4096, 'maximum targets')
  for (const key of ['control_relative_tolerance', 'control_absolute_tolerance_m', 'control_absolute_tolerance_rad', 'minimum_control_reference_m', 'load_factor_increment_tolerance']) positive(solver[key], key)
  const direction = exact(solver.path_direction, ['reversal_supported', 'allow_direction_reversal', 'maximum_direction_reversals', 'equal_consecutive_targets_allowed'], 'direction policy')
  same(direction.reversal_supported, true, 'reversal supported')
  same(direction.equal_consecutive_targets_allowed, false, 'equal targets unsupported')
  ensure(typeof direction.allow_direction_reversal === 'boolean', 'reversal option')
  const reversals = integer(direction.maximum_direction_reversals, 0, 4095, 'maximum reversals')
  ensure(direction.allow_direction_reversal ? reversals > 0 && reversals < (solver.maximum_path_targets as number) : reversals === 0, 'reversal policy bound')
  const cutback = exact(solver.target_cutback, ['supported', 'enabled', 'ratio', 'maximum_depth', 'maximum_accepted_substeps_per_requested_target', 'maximum_path_solve_attempts', 'minimum_translation_increment_m', 'minimum_rotation_increment_rad', 'retry_reason_codes'], 'target cutback')
  same(cutback.supported, true, 'target cutback support')
  ensure(typeof cutback.enabled === 'boolean', 'target cutback enabled')
  ensure(positive(cutback.ratio, 'target cutback ratio') < 1, 'target cutback ratio')
  integer(cutback.maximum_depth, 0, 32, 'target cutback depth')
  integer(cutback.maximum_accepted_substeps_per_requested_target, 1, 4096, 'target cutback steps')
  same(cutback.maximum_path_solve_attempts, maximumAttempts, 'global attempt limit')
  positive(cutback.minimum_translation_increment_m, 'translation increment')
  positive(cutback.minimum_rotation_increment_rad, 'rotation increment')
  same(cutback.retry_reason_codes, ['direct_control_maximum_iterations_exceeded', 'direct_control_line_search_failed'], 'target retry policy')
  lineSearch(solver.line_search, 'strict_augmented_gate_normalized_merit_decrease.v1')
  const frame = exact(solver.frame_config, ['profile', 'residual_relative_tolerance', 'residual_absolute_tolerance_kn', 'increment_relative_tolerance', 'increment_absolute_tolerance_m', 'maximum_iterations', 'minimum_characteristic_length_m', 'minimum_reference_force_kn', 'assembly', 'equation_scaling', 'linear_solver', 'factorization_policy', 'load_control', 'line_search', 'regularization_allowed', 'fallback_allowed'], 'frame configuration')
  same(frame.profile, FRAME_PROFILE, 'frame profile')
  same(frame.assembly, 'member_12x12_triplet_coalesce_sorted_csr_fp64.v1', 'assembly profile')
  same(frame.equation_scaling, 'centroid_diameter_force_moment_6dof.v1', 'equation scaling')
  same(frame.regularization_allowed, false, 'frame regularization')
  same(frame.fallback_allowed, false, 'frame fallback')
  const frameIterations = integer(frame.maximum_iterations, 1, Number.MAX_SAFE_INTEGER, 'frame iterations')
  integer(solver.maximum_iterations, 1, Math.min(200, frameIterations), 'direct iterations')
  for (const key of ['residual_relative_tolerance', 'residual_absolute_tolerance_kn', 'increment_relative_tolerance', 'increment_absolute_tolerance_m', 'minimum_characteristic_length_m', 'minimum_reference_force_kn']) positive(frame[key], key)
  lineSearch(frame.line_search, 'strict_scaled_residual_decrease.v1')
  const load = exact(frame.load_control, ['policy', 'adaptive_cutback'], 'frame load control')
  same(load.policy, 'ordered_finite_targets_with_reversal_allowed', 'frame load policy')
  const loadCutback = exact(load.adaptive_cutback, ['enabled', 'ratio', 'maximum_depth', 'maximum_accepted_substeps', 'minimum_increment_factor', 'retry_reason_codes', 'retry_requires_explicit_convergence_classification'], 'frame cutback')
  ensure(typeof loadCutback.enabled === 'boolean', 'frame cutback option')
  ensure(positive(loadCutback.ratio, 'frame cutback ratio') < 1, 'frame cutback ratio')
  integer(loadCutback.maximum_depth, 0, Number.MAX_SAFE_INTEGER, 'frame cutback depth')
  integer(loadCutback.maximum_accepted_substeps, 1, Number.MAX_SAFE_INTEGER, 'frame cutback steps')
  positive(loadCutback.minimum_increment_factor, 'frame cutback increment')
  same(loadCutback.retry_reason_codes, ['maximum_iterations_exceeded', 'line_search_failed'], 'frame retry reasons')
  same(loadCutback.retry_requires_explicit_convergence_classification, true, 'frame retry classification')
  const policy = object(frame.factorization_policy, 'factorization policy')
  const scalable = policy.policy_id === 'experimental_blocked_exact_sparse_factorization_fail_closed.v1'
  exact(policy, ['policy_id', 'maximum_condition_number_1', 'minimum_normalized_absolute_pivot', 'maximum_backward_error', 'regularization_allowed', 'fallback_allowed', 'policy_hash', ...(scalable ? ['maximum_equations', 'inverse_solve_block_size', 'condition_estimate_is_exact'] : ['maximum_exact_condition_equations'])], 'factorization policy')
  same(policy.policy_id, scalable ? 'experimental_blocked_exact_sparse_factorization_fail_closed.v1' : 'public_sparse_factorization_fail_closed.v1', 'factorization profile')
  same(frame.linear_solver, scalable ? 'scipy_superlu_splu_cpu_blocked_exact_condition_fail_closed' : 'scipy_superlu_splu_cpu_exact_condition_fail_closed', 'factorization backend')
  same(policy.regularization_allowed, false, 'factorization regularization')
  same(policy.fallback_allowed, false, 'factorization fallback')
  for (const key of ['maximum_condition_number_1', 'minimum_normalized_absolute_pivot', 'maximum_backward_error']) positive(policy[key], key)
  hash(policy.policy_hash, 'factorization policy hash')
  if (scalable) {
    const size = integer(policy.maximum_equations, 1, Number.MAX_SAFE_INTEGER, 'factorization size')
    integer(policy.inverse_solve_block_size, 1, size, 'factorization block size')
    same(policy.condition_estimate_is_exact, true, 'exact conditioning')
  } else integer(policy.maximum_exact_condition_equations, 1, Number.MAX_SAFE_INTEGER, 'factorization size')
  return solver
}

export async function validateFrame3DJobResult(value: unknown, evidence: unknown, job: WorkbenchJobView): Promise<Frame3DJobReview> {
  ensure(validateWorkbenchJobView(job).ok && job.status === 'succeeded' && job.result && job.evidence, 'published job view')
  finiteTree(value)
  finiteTree(evidence)
  const root = exact(value, ['schema_version', 'profile', 'status', 'contract_pass', 'request_hash', 'resume_contract_hash', 'case_id', 'source_revision', 'source_revision_is_attestation', 'control_targets', 'total_target_count', 'completed_target_count', 'receipts', 'execution_budget', 'terminal_checkpoint_artifact_base64', 'authority', 'claim_boundary', 'result_hash'], 'job result')
  same(root.schema_version, 'bounded-frame3d-job-result.v1', 'result schema')
  same(root.profile, PROFILE, 'job profile')
  same(root.status, 'ready', 'ready result')
  same(root.contract_pass, true, 'result contract')
  same(root.authority, AUTHORITY, 'candidate authority')
  same(root.claim_boundary, JOB_BOUNDARY, 'job claim boundary')
  same(root.source_revision_is_attestation, false, 'source declaration scope')
  ensure(typeof root.case_id === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(root.case_id), 'case id')
  ensure(typeof root.source_revision === 'string' && /^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$/.test(root.source_revision), 'source revision')
  hash(root.result_hash, 'result hash')
  same(hash(root.request_hash, 'request hash'), job.request.content_hash, 'job request binding')
  same(hash(root.resume_contract_hash, 'resume hash'), await integerStringDigest({ profile: PROFILE, request_hash: root.request_hash }), 'full request resume hash')
  if (job.resume_contract_hash !== null) same(root.resume_contract_hash, job.resume_contract_hash, 'durable resume hash')
  const total = integer(root.total_target_count, 1, 4096, 'target count')
  same(root.completed_target_count, total, 'all authored targets completed')
  same(job.progress, { completed_steps: total, total_steps: total }, 'job progress')
  const targets = array(root.control_targets, total, total, 'full target list').map((target) => finite(target, 'authored target'))
  const receipts = array(root.receipts, total, total, 'receipt coverage')
  const budget = exact(root.execution_budget, ['maximum_attempts', 'reserved_attempts', 'remaining_attempts'], 'execution budget')
  const maximum = integer(budget.maximum_attempts, 1, 65536, 'maximum attempts')
  const reserved = integer(budget.reserved_attempts, 0, maximum, 'reserved attempts')
  same(budget.remaining_attempts, maximum - reserved, 'remaining attempts')
  let lastOrdinal = 0
  let confirmed = 0
  let priorCheckpoint: Obj | null = null
  let priorBytesHash: string | null = null
  let priorSource: unknown = null
  let priorSolver: Obj | null = null
  let priorBinding: Obj | null = null
  let priorControl: unknown = null
  let previousTarget = 0
  let previousDirection: number | null = null
  let reversals = 0
  let terminalBytes = new Uint8Array()
  for (const [position, rawReceipt] of receipts.entries()) {
    const index = position + 1
    const target = targets[position]
    ensure(target !== previousTarget, 'zero or repeated authored target')
    const direction = target > previousTarget ? 1 : -1
    const reversal = previousDirection !== null && direction !== previousDirection
    reversals += reversal ? 1 : 0
    const receipt = exact(rawReceipt, ['receipt_hash', 'target_index', 'authored_target', 'request_hash', 'api_request_hash', 'restart_checkpoint_sha256', 'result_hash', 'api_result', 'checkpoint_artifact_base64', 'checkpoint_sha256', 'reserved_attempt_ordinals', 'target_chain_proof'], 'target receipt')
    hash(receipt.receipt_hash, 'receipt hash')
    same(receipt.target_index, index, 'receipt index')
    same(receipt.authored_target, target, 'receipt target')
    same(receipt.request_hash, root.request_hash, 'receipt full request')
    same(receipt.restart_checkpoint_sha256, priorBytesHash, 'receipt restart prefix')
    ensure(validRawResult(receipt.api_result), 'raw API result schema')
    const result = receipt.api_result as unknown as Frame3DTargetResult
    same(result.status, 'ready', 'raw API ready')
    same(result.contract_pass, true, 'raw API contract')
    same(result.terminal_reason_code, null, 'raw API terminal reason')
    same(result.authority, AUTHORITY, 'raw API authority')
    same(result.claim_boundary, API_BOUNDARY, 'raw API claim boundary')
    same(result.result_hash, hash(receipt.result_hash, 'receipt result hash'), 'raw API result hash')
    const control = result.control
    same(control.control_targets, [target], 'unchanged one-target API request')
    same(control.request_hash, hash(receipt.api_request_hash, 'API request hash'), 'API request binding')
    const controlOffset = DOFS.indexOf(control.control_dof)
    const globalDof = integer(control.control_global_dof, 0, 767, 'control global dof')
    same(globalDof % 6, controlOffset, 'control component mapping')
    same(control.control_unit, controlOffset < 3 ? 'm' : 'rad', 'control unit')
    const solver = solverConfiguration(control.solver_config, total, maximum)
    const directionPolicy = solver.path_direction as Obj
    const cyclic = directionPolicy.allow_direction_reversal === true
    ensure(cyclic ? reversals <= (directionPolicy.maximum_direction_reversals as number) : reversals === 0, 'authored reversal bounds')
    const stableControl = { node: control.control_node_id, dof: control.control_dof, unit: control.control_unit, globalDof, resumeHash: control.resume_contract_hash }
    if (position > 0) {
      same(result.source_binding, priorSource, 'source identity across receipts')
      same(solver, priorSolver, 'solver policy across receipts')
      same(stableControl, priorControl, 'control identity across receipts')
    }
    const source = result.source_binding
    same(source.adapter_profile, 'model_ir_v2_to_stateful_corotational_frame3d_direct_control.v1', 'adapter profile')
    same(source.node_ids[Math.floor(globalDof / 6)], control.control_node_id, 'control node order')
    const recoveryIdentity = { entity_mapping_hash: source.entity_mapping_hash, node_ids: source.node_ids, member_ids: source.member_ids, member_material_ids: source.member_material_ids }
    same(source.recovery_identity_hash, await integerStringDigest(recoveryIdentity), 'recovery entity identity')
    const bytes = decodeCheckpoint(receipt.checkpoint_artifact_base64)
    const bytesHash = await requiredDigest(bytes)
    same(bytesHash, hash(receipt.checkpoint_sha256, 'checkpoint SHA'), 'checkpoint bytes SHA')
    let decoded: unknown
    try { decoded = parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) } catch { throw new Error('frame3d_job_invalid: checkpoint JSON') }
    finiteTree(decoded)
    ensure(cyclic ? validCheckpointV2(decoded) : validCheckpointV1(decoded), 'checkpoint schema')
    const artifact = decoded as Obj
    const checkpoint = object(artifact.checkpoint, 'checkpoint')
    const binding = object(artifact.resume_binding, 'resume binding')
    same(result.checkpoint_artifact, {
      available: true, schema_version: artifact.schema_version,
      artifact_hash: artifact.artifact_hash, byte_length: bytes.byteLength,
      checkpoint_hash: checkpoint.checkpoint_hash, exact_resume_supported: true,
    }, 'checkpoint descriptor')
    for (const key of ['model_ir_content_hash', 'adapter_hash', 'entity_mapping_hash', 'node_ids', 'member_ids', 'member_material_ids']) same(artifact[key], source[key], `checkpoint source ${key}`)
    for (const key of ['control_node_id', 'control_dof', 'control_global_dof', 'control_unit', 'resume_contract_hash']) same(artifact[key], control[key], `checkpoint control ${key}`)
    same(artifact.profile, API_PROFILE, 'checkpoint API profile')
    same(artifact.model_hash, result.model_hash, 'checkpoint model')
    same(checkpoint.model_hash, result.model_hash, 'state model')
    same(binding.model_hash, result.model_hash, 'resume model')
    if (priorCheckpoint) same(result.model_hash, priorCheckpoint.model_hash, 'model identity across checkpoints')
    same(binding.control_global_dof, globalDof, 'resume control dof')
    same(binding.control_unit, control.control_unit, 'resume control unit')
    same(binding.frame_solver_contract_hash, checkpoint.solver_contract_hash, 'frame contract binding')
    if (priorBinding) {
      same(binding.frame_solver_contract_hash, priorBinding.frame_solver_contract_hash, 'unchanged frame contract')
      same(binding.direct_control_contract_hash, priorBinding.direct_control_contract_hash, 'unchanged direct contract')
    }
    same(control.resume_contract_hash, await integerStringDigest({ profile: API_PROFILE, control_node_id: control.control_node_id, control_dof: control.control_dof, control_unit: control.control_unit, solver_contract_hash: binding.direct_control_contract_hash }), 'API resume contract identity')
    same(binding.accepted_checkpoint_hash, checkpoint.checkpoint_hash, 'resume checkpoint')
    same(binding.accepted_step_index, checkpoint.step_index, 'resume step index')
    const metrics = result.metrics
    same(metrics.requested_target_count, 1, 'one requested target')
    same(metrics.completed_requested_target_count, 1, 'one completed target')
    same(metrics.final_checkpoint_at_requested_target_boundary, true, 'requested boundary')
    same(metrics.exact_checkpoint_resume_supported, true, 'exact checkpoint resume')
    same(metrics.final_load_factor, checkpoint.load_factor, 'terminal load factor')
    ensure(metrics.scaled_residual_inf_norm <= metrics.scaled_residual_tolerance, 'retained residual gate')
    const cutbackPolicy = solver.target_cutback as Obj
    const accepted = integer(metrics.accepted_checkpoint_count, 1, cutbackPolicy.maximum_accepted_substeps_per_requested_target as number, 'accepted checkpoint count')
    const attempts = integer(metrics.solve_attempt_count, accepted, maximum, 'confirmed solve attempts')
    const cutbackCount = integer(metrics.target_cutback_attempt_count, 0, attempts - accepted, 'failed cutback count')
    same(attempts, accepted + cutbackCount, 'ready attempt count balance')
    same(metrics.adaptive_target_cutback_used, cutbackCount > 0, 'cutback usage')
    if (cutbackPolicy.enabled === false) same([accepted, cutbackCount], [1, 0], 'disabled cutback scope')
    same(checkpoint.step_index, (priorCheckpoint?.step_index as number ?? 0) + accepted, 'accepted checkpoint progress')
    if (priorCheckpoint && accepted === 1) same(checkpoint.parent_checkpoint_hash, priorCheckpoint.checkpoint_hash, 'checkpoint parent')
    const ordinals = array(receipt.reserved_attempt_ordinals, attempts, attempts, 'reservation receipt count')
    for (const ordinal of ordinals) lastOrdinal = integer(ordinal, lastOrdinal + 1, reserved, 'increasing reserved ordinal')
    confirmed += attempts
    ensure(confirmed <= reserved, 'confirmed attempts within reservation budget')
    const displacement = array(checkpoint.displacement, source.node_ids.length * 6, source.node_ids.length * 6, 'six dof displacement vector')
    same(result.node_displacements.length, source.node_ids.length, 'node coverage')
    for (const [nodeIndex, node] of result.node_displacements.entries()) {
      same(node.node_id, source.node_ids[nodeIndex], 'node row identity/order')
      for (const [offset, key] of NODE_COMPONENTS.entries()) same(node[key], displacement[nodeIndex * 6 + offset], `node ${key} checkpoint value`)
    }
    same(metrics.final_control_coordinate, displacement[globalDof], 'control displacement')
    same(binding.accepted_control_target, displacement[globalDof], 'accepted control value')
    // This is only a conservative contradiction screen, not a replay of the
    // scaled solver gate. The geometry's actual characteristic length is absent;
    // its configured lower bound gives a potentially much looser rotation
    // tolerance. An overflowing upper bound supplies no numerical constraint
    // and must not reject an otherwise valid producer artifact. Exact coordinate
    // and checkpoint bindings above remain mandatory in either case.
    const previousCoordinate = priorCheckpoint ? (priorCheckpoint.displacement as number[])[globalDof] : 0
    const frame = solver.frame_config as Obj
    const reference = Math.max(Math.abs(target), Math.abs(target - previousCoordinate), (solver.minimum_control_reference_m as number) / (controlOffset < 3 ? 1 : frame.minimum_characteristic_length_m as number))
    const coordinateTolerance = (solver.control_relative_tolerance as number) * reference + (controlOffset < 3 ? solver.control_absolute_tolerance_m as number : solver.control_absolute_tolerance_rad as number)
    if (Number.isFinite(coordinateTolerance)) ensure(Math.abs(metrics.final_control_coordinate - target) <= coordinateTolerance, 'target coordinate consistency')
    const states = array(checkpoint.material_states, source.member_ids.length, source.member_ids.length, 'material checkpoint coverage')
    same(source.member_material_ids.length, source.member_ids.length, 'material identity coverage')
    same(result.material_states.length, source.member_ids.length, 'material result coverage')
    for (const [memberIndex, material] of result.material_states.entries()) {
      same(material.member_id, source.member_ids[memberIndex], 'material member identity/order')
      same(material.material_id, source.member_material_ids[memberIndex], 'material law identity/order')
      const state = object(states[memberIndex], 'checkpoint material')
      for (const key of MATERIAL_COMPONENTS) same(material[key], state[key], `material ${key} checkpoint value`)
    }
    same(metrics.maximum_accumulated_plastic_strain, Math.max(...result.material_states.map((row) => row.accumulated_plastic_strain)), 'maximum accumulated plastic strain')
    const reactionIds = new Set<string>()
    for (const reaction of result.support_reactions) {
      ensure(source.node_ids.includes(reaction.node_id), 'reaction node identity')
      same(reaction.unit, DOFS.indexOf(reaction.dof) < 3 ? 'kN' : 'kN_m', 'reaction unit')
      const identity = `${reaction.node_id}/${reaction.dof}`
      ensure(!reactionIds.has(identity), 'duplicate reaction row')
      reactionIds.add(identity)
    }
    if (cyclic) {
      same(metrics.path_mode, 'cyclic_reversal', 'cyclic path mode')
      same(metrics.cumulative_completed_target_count, index, 'cyclic target cursor')
      same(metrics.cumulative_direction_reversal_count, reversals, 'cyclic reversal count')
      same(metrics.resumed_with_direction_reversal, reversal, 'cyclic resumed reversal')
      same(metrics.requested_direction_reversal_count, reversal ? 1 : 0, 'requested reversal count')
      same(metrics.completed_direction_reversal_count, reversal ? 1 : 0, 'completed reversal count')
      for (const [key, expected] of Object.entries({ path_mode: 'cyclic_reversal', cumulative_completed_target_count: index, cumulative_reversal_count: reversals, last_completed_leg_direction_sign: direction, accepted_target_chain_hash: metrics.accepted_target_chain_hash })) {
        same(artifact[key], expected, `cyclic artifact ${key}`)
        same(binding[key], expected, `cyclic binding ${key}`)
      }
      const proof = exact(receipt.target_chain_proof, ['preimage', 'cutback_history'], 'cyclic proof')
      const preimage = exact(proof.preimage, ['schema_version', 'entry_kind', 'previous_chain_hash', 'cumulative_target_index', 'authored_target', 'leg_direction_sign', 'reversal_from_previous_leg', 'requested_boundary_checkpoint_hash', 'accepted_step_hashes', 'cutback_history_hash'], 'cyclic preimage')
      same(preimage.schema_version, 'stateful-corotational-frame3d-displacement-control-target-chain.v1', 'chain profile')
      same(preimage.entry_kind, 'completed_authored_target', 'chain entry')
      hash(preimage.previous_chain_hash, 'previous chain hash')
      if (priorBinding) same(preimage.previous_chain_hash, priorBinding.accepted_target_chain_hash, 'cyclic previous chain binding')
      same(preimage.cumulative_target_index, index, 'chain target index')
      same(preimage.authored_target, target, 'chain target')
      same(preimage.leg_direction_sign, direction, 'chain direction')
      same(preimage.reversal_from_previous_leg, reversal, 'chain reversal')
      same(preimage.requested_boundary_checkpoint_hash, checkpoint.checkpoint_hash, 'chain boundary checkpoint')
      const stepHashes = array(preimage.accepted_step_hashes, accepted, accepted, 'chain accepted steps')
      for (const item of stepHashes) hash(item, 'chain step hash')
      ensure(new Set(stepHashes).size === stepHashes.length, 'distinct chain steps')
      const cutbacks = array(proof.cutback_history, cutbackCount, cutbackCount, 'chain cutback coverage')
      hash(preimage.cutback_history_hash, 'chain cutback hash')
      if (cutbacks.length === 0) same(preimage.cutback_history_hash, await integerStringDigest([]), 'empty cutback history hash')
      for (const [cutbackIndex, entry] of cutbacks.entries()) {
        const cutback = exact(entry, ['attempt_index', 'recursion_depth', 'cumulative_target_index', 'leg_direction_sign', 'reversal_from_previous_leg', 'control_global_dof', 'control_unit', 'requested_target_control_coordinate', 'rejected_target_control_coordinate', 'accepted_parent_control_coordinate', 'accepted_parent_checkpoint_hash', 'cutback_target_control_coordinate', 'reason_code', 'outcome', 'outcome_reason_code', 'rejected_result_hash', 'parent_state_immutable'], 'chain cutback')
        same(cutback.attempt_index, cutbackIndex, 'cutback attempt index')
        integer(cutback.recursion_depth, 0, (cutbackPolicy.maximum_depth as number) - 1, 'cutback recursion depth')
        same(cutback.cumulative_target_index, index, 'cutback target index')
        same(cutback.leg_direction_sign, direction, 'cutback direction')
        same(cutback.reversal_from_previous_leg, reversal, 'cutback reversal')
        same(cutback.requested_target_control_coordinate, target, 'cutback authored target')
        same(cutback.control_global_dof, globalDof, 'cutback control')
        same(cutback.control_unit, control.control_unit, 'cutback unit')
        same(cutback.parent_state_immutable, true, 'cutback parent immutable')
        hash(cutback.accepted_parent_checkpoint_hash, 'cutback parent checkpoint')
        hash(cutback.rejected_result_hash, 'cutback rejected result')
        ensure((cutbackPolicy.retry_reason_codes as unknown[]).includes(cutback.reason_code), 'cutback retry reason')
        same(cutback.outcome, 'cutback_scheduled', 'ready cutback outcome')
        same(cutback.outcome_reason_code, null, 'ready cutback reason')
        const parentCoordinate = finite(cutback.accepted_parent_control_coordinate, 'cutback parent coordinate')
        const rejectedCoordinate = finite(cutback.rejected_target_control_coordinate, 'cutback rejected coordinate')
        const retryCoordinate = finite(cutback.cutback_target_control_coordinate, 'cutback retry coordinate')
        ensure(direction * (retryCoordinate - parentCoordinate) > 0 && direction * (rejectedCoordinate - retryCoordinate) > 0, 'cutback ordered inside target leg')
      }
    } else {
      same(receipt.target_chain_proof, null, 'monotonic proof scope')
      same(metrics.path_mode, 'monotonic_v1', 'monotonic path mode')
      same(metrics.cumulative_completed_target_count, 1, 'monotonic invocation count')
      for (const key of ['cumulative_direction_reversal_count', 'requested_direction_reversal_count', 'completed_direction_reversal_count']) same(metrics[key], 0, 'monotonic reversal count')
      same(metrics.accepted_target_chain_hash, null, 'monotonic chain scope')
      same(metrics.resumed_with_direction_reversal, false, 'monotonic resumed direction')
      same(artifact.direction_sign, direction, 'monotonic artifact direction')
      same(binding.direction_sign, direction, 'monotonic binding direction')
    }
    priorCheckpoint = checkpoint; priorBytesHash = bytesHash; priorSource = source
    priorSolver = solver; priorControl = stableControl; priorBinding = binding
    previousTarget = target; previousDirection = direction; terminalBytes = bytes
  }
  same(root.terminal_checkpoint_artifact_base64, (receipts[total - 1] as Obj).checkpoint_artifact_base64, 'terminal artifact receipt tail')
  const outer = exact(evidence, ['schema_version', 'job_id', 'request_hash', 'checkpoint_hash', 'result_artifact_hash', 'validator_id', 'contract_pass', 'solver_truth_owner', 'validation_report', 'claim_boundary'], 'completion evidence')
  same(outer.schema_version, 'structural-analysis-job-completion-evidence.v1', 'evidence schema')
  same(outer.job_id, job.job_id, 'evidence job')
  same(outer.request_hash, root.request_hash, 'evidence request')
  same(outer.checkpoint_hash, job.checkpoint?.content_hash ?? null, 'evidence durable checkpoint')
  same(outer.result_artifact_hash, job.result!.content_hash, 'evidence raw result bytes')
  same(outer.validator_id, VALIDATOR, 'core validator identity')
  same(outer.contract_pass, true, 'evidence contract')
  same(outer.solver_truth_owner, 'structural_analysis_core', 'evidence owner')
  same(outer.claim_boundary, SERVICE_BOUNDARY, 'service claim boundary')
  const expectedReport = {
    schema_version: 'bounded-frame3d-job-validation-report.v1', contract_pass: true,
    request_hash: root.request_hash, result_hash: root.result_hash,
    completed_target_count: total, total_target_count: total, execution_budget: budget,
    terminal_checkpoint_sha256: priorBytesHash,
    receipt_hashes: receipts.map((row) => (row as Obj).receipt_hash),
    authority: AUTHORITY, claim_boundary: JOB_BOUNDARY,
  }
  same(exact(outer.validation_report, Object.keys(expectedReport), 'core validation report'), expectedReport, 'complete core validation report binding')
  const payload = value as Frame3DJobPayload
  const terminal = payload.receipts[total - 1].api_result
  return {
    payload, terminalResult: terminal, terminalCheckpointBytes: terminalBytes,
    completedTargetCount: total, totalTargetCount: total,
    reservedAttempts: reserved, confirmedAttempts: confirmed, abandonedReservations: reserved - confirmed,
    controlNodeId: terminal.control.control_node_id, controlDof: terminal.control.control_dof,
    controlUnit: terminal.control.control_unit, targets,
    sourceRevision: payload.source_revision, requestHash: payload.request_hash,
    resultHash: payload.result_hash, terminalCheckpointSha256: priorBytesHash!,
  }
}
