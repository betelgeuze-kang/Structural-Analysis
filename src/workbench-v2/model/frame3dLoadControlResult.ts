import { canonicalJson, sha256Bytes, sha256Hex } from './checksum'

export const FRAME3D_LOAD_CONTROL_ADAPTER_ID = 'frame3d-bounded-load-control.v1'
export const FRAME3D_LOAD_CONTROL_RESULT_CONTRACT = 'bounded-frame3d-load-control-result.v1'
export const FRAME3D_LOAD_CONTROL_PROFILE = 'bounded_multimember_frame3d_load_control_model_ir_api.v1'
export const FRAME3D_LOAD_CONTROL_SOURCE_ADAPTER_PROFILE = 'model_ir_v2_to_multimember_corotational_frame3d_load_control.v1'
export const FRAME3D_LOAD_CONTROL_SOLVER_PROFILE = 'dense_elastic_corotational_timoshenko_frame3d_load_control.v2'
export const FRAME3D_LOAD_CONTROL_BACKEND_ROLE = 'cpu_reference'
export const FRAME3D_LOAD_CONTROL_VALIDATOR_ID = 'structural_analysis.api.frame3d_load_control.validate_bounded_frame3d_load_control_result_manifest'
export const FRAME3D_LOAD_CONTROL_VALIDATION_REPORT = 'bounded-frame3d-load-control-validation-report.v1'

const RESULT_CLAIM_BOUNDARY = 'This bounded candidate API executes one source-bound 3-16 node, 2-32 member elastic ModelIR v2 Frame3D load-control path. It returns authoritative nonlinear numerical ResultIR displacement/convergence, exact durable checkpoint restart, and bounded solver-derived reactions, member recovery, and full-node equilibrium. It has no stateful material, distributed load, offset/release, external-V&V, design, public-product, release, or commercial authority.'
const SOURCE_ADAPTER_CLAIM_BOUNDARY = 'This adapter compiles one selected zero-self-weight ModelIR v2 load pattern into the bounded dense elastic corotational Frame3D load-control model. It requires 3-16 nodes, 2-32 connected unreleased zero-offset frame members, zero prescribed support values, bounded exact-binary64 coordinates, properties and loads, and a nonzero load on a free equation. It creates no stateful-material, external-V&V, design, public-product, release, or commercial authority.'
const SOURCE_SOLVER_CLAIM_BOUNDARY = 'Small dense elastic 3D frame verification path using the numerical-energy element tangent, explicit nodal loads and restraints, residual-and-increment commit gates, deterministic backtracking, and exact checkpoint lineage. It has no stateful section, distributed load, release/offset, warping coupling, transient dynamics, external V&V, or release authority.'

const HASH = /^sha256:[0-9a-f]{64}$/
const STABLE_ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/

const TOP_LEVEL_KEYS = new Set([
  'schema_version', 'profile', 'status', 'contract_pass', 'result_hash',
  'source_binding', 'load_factors', 'solver', 'numerical_result_ir',
  'node_displacements', 'support_reactions', 'member_recovery',
  'full_node_equilibrium', 'checkpoint_artifact', 'metrics', 'authority',
  'warnings', 'claim_boundary',
])
const SOURCE_KEYS = new Set([
  'schema_version', 'adapter_profile', 'adapter_hash', 'model_ir_content_hash',
  'model_ir_semantic_hash', 'model_ir_provenance_hash', 'load_pattern_id',
  'model_hash', 'node_ids', 'member_ids', 'material_ids', 'section_ids',
  'restrained_global_dofs', 'unit_conversion_hash', 'entity_mapping_hash',
  'claim_boundary', 'request_hash',
])
const SOURCE_RECEIPT_KEYS = new Set([
  'schema_version', 'profile', 'model_hash', 'solver_contract_hash',
  'start_checkpoint_hash', 'steps', 'maximum_free_residual_inf_norm_kn',
  'maximum_scaled_residual_inf_norm', 'maximum_scaled_increment_inf_norm',
  'equation_scaling', 'result_hash', 'exact_checkpoint_resume_supported',
  'regularization_used', 'fallback_used', 'contract_pass', 'claim_boundary',
])
const EXECUTION_KEYS = new Set([
  'start_checkpoint', 'requested_load_factors', 'accepted_load_factors',
  'maximum_new_steps', 'completed_prefix_count', 'remaining_load_factor_count',
  'state_epoch_scope',
])
const EQUILIBRIUM_SUMMARY_KEYS = new Set([
  'equilibrium_scaling_hash', 'scaled_tolerance',
  'maximum_scaled_balance_residual', 'maximum_force_balance_residual_n',
  'maximum_moment_balance_residual_n_m', 'force_tolerance_n',
  'moment_tolerance_n_m', 'contract_pass',
])
const CHECKPOINT_ARTIFACT_KEYS = new Set([
  'schema_version', 'profile', 'artifact_hash', 'model_ir_content_hash',
  'adapter_hash', 'model_hash', 'load_pattern_id', 'node_ids', 'member_ids',
  'solver_contract_hash', 'request_hash', 'resume_contract_hash', 'checkpoint',
  'public_product_promotion', 'release_eligible',
])
const CHECKPOINT_KEYS = new Set([
  'schema_version', 'profile', 'model_hash', 'solver_contract_hash',
  'load_factor', 'displacement', 'converged_iterations',
  'residual_inf_norm_kn', 'parent_checkpoint_hash', 'checkpoint_hash',
])
const STEP_KEYS = new Set([
  'load_factor', 'applied_load', 'reactions', 'free_residual_inf_norm_kn',
  'relative_residual', 'condition_number',
  'raw_translational_residual_inf_norm_kn',
  'raw_rotational_residual_inf_norm_kn_m', 'scaled_residual_inf_norm',
  'raw_translation_increment_inf_norm_m', 'raw_rotation_increment_inf_norm_rad',
  'scaled_increment_inf_norm', 'scaled_residual_tolerance',
  'scaled_increment_tolerance', 'residual_gate_passed',
  'increment_gate_passed', 'line_search_required',
  'selected_line_search_alpha', 'line_search_valid',
  'final_reassembled_equilibrium_passed', 'parent_state_immutable',
  'scaled_condition_number_1', 'equation_scaling_hash',
  'convergence_history', 'line_search_history', 'checkpoint', 'members',
])
const STEP_MEMBER_KEYS = new Set([
  'member_id', 'node_i', 'node_j', 'initial_length_m', 'current_length_m',
  'strain_energy_kn_m', 'basic_deformations', 'basic_forces',
  'global_end_forces',
])
const EQUATION_SCALING_KEYS = new Set([
  'schema_version', 'policy', 'source_identity_hash', 'characteristic_length_m',
  'reference_force', 'residual_translation_scale', 'residual_rotation_scale',
  'increment_translation_scale_m', 'increment_rotation_scale_rad', 'dof_count',
  'free_equation_count', 'source_node_coordinates_hash',
  'source_reference_load_hash', 'source_free_dofs_hash',
  'row_equilibration_hash', 'column_equilibration_hash', 'scaling_hash',
])
const NUMERICAL_RESULT_KEYS = new Set([
  'schema_version', 'result_id', 'result_hash', 'result_kind',
  'authority_profile', 'authority', 'bindings', 'backend', 'load_factor',
  'time_s', 'dof_count', 'displacement_artifact', 'claim_boundary', 'extensions',
])
const NUMERICAL_AUTHORITY = Object.freeze({
  numerical_state: 'authoritative',
  convergence: 'authoritative',
  displacement: 'authoritative',
  material_state: 'authoritative',
  reaction: 'not_evaluated',
  member_force: 'not_evaluated',
  integration_point_engineering_output: 'not_evaluated',
  engineering_design: 'not_authoritative',
  code_compliance: 'not_authoritative',
  release_readiness: 'not_authoritative',
  commercial_use: 'not_authoritative',
})
const NUMERICAL_BINDING_KEYS = new Set([
  'model_ir_content_hash', 'execution_plan_hash', 'equation_scaling_hash',
  'reduced_csr_identity_hash', 'operator_hash', 'state_hash', 'state_epoch',
  'material_state_bundle_hash', 'integration_point_order_hash',
  'path_history_hash', 'nonlinear_terminal_hash', 'full_residual_receipt_hash',
  'boundary_condition_receipt_hash',
])
const NUMERICAL_CLAIM_BOUNDARY = Object.freeze({
  committed_nonlinear_state: true,
  ordered_material_state_bundle: true,
  equation_scaling_replay_bound: true,
  reduced_csr_identity_bound: true,
  source_free_solution_bytes_bound: true,
  residual_and_increment_terminal_gate: true,
  fallback_or_regularization_promoted: false,
  constitutive_law_verified: false,
  material_state_history_replayed: false,
  fiber_frame_kinematic_adapter_authority: false,
  reaction_authority: false,
  member_force_authority: false,
  integration_point_engineering_output_authority: false,
  design_or_code_authority: false,
  viewer_projection: false,
  release_readiness: false,
  commercial_claim: false,
})
const DISPLACEMENT_DESCRIPTOR_KEYS = new Set([
  'name', 'dtype', 'shape', 'layout', 'byte_order', 'byte_length',
  'storage_profile', 'unit_profile', 'data_hash', 'content_hash', 'artifact_uri',
])
const METRIC_KEYS = new Set([
  'final_load_factor', 'accepted_step_count', 'numerical_result_state_epoch',
  'state_epoch_scope', 'completed_prefix_count', 'remaining_load_factor_count',
  'node_count', 'member_count', 'fallback_count', 'regularization_count',
])
const OUTER_AUTHORITY = Object.freeze({
  candidate_api_exposed: true,
  capability_registry_public: false,
  workbench_execution: false,
  numerical_result_ir: 'authoritative_bounded',
  numerical_result_ir_reaction_authority: false,
  numerical_result_ir_member_force_authority: false,
  solver_derived_reaction_recovery: 'bounded_candidate',
  solver_derived_member_recovery: 'bounded_candidate',
  full_node_equilibrium: 'authoritative_reassembled',
  external_vv_level: 0,
  independent_operator_attached: false,
  design_authority: false,
  public_product_promotion: false,
  release_eligible: false,
  commercial_use: false,
})
const REPORT_KEYS = new Set([
  'schema_version', 'status', 'contract_pass', 'result_schema_version',
  'profile', 'source_adapter_profile', 'solver_profile', 'backend_role',
  'validator_id', 'result_hash', 'result_artifact_sha256',
  'job_request_artifact_sha256', 'model_ir_content_hash',
  'model_ir_semantic_hash', 'model_ir_provenance_hash', 'adapter_hash',
  'compiled_model_hash', 'api_request_hash', 'resume_contract_hash',
  'source_solver_receipt_hash', 'numerical_result_ir_hash',
  'resume_checkpoint_artifact_sha256',
  'terminal_checkpoint_hash', 'terminal_checkpoint_artifact_hash',
  'terminal_checkpoint_artifact_sha256', 'recovery_hash',
  'full_node_equilibrium_hash', 'equilibrium_scaling_hash',
  'final_load_factor', 'total_load_factor_count',
  'resume_completed_prefix_count', 'accepted_suffix_step_count',
  'completed_prefix_count', 'remaining_load_factor_count',
  'terminal_checkpoint_embedded',
  'exact_result_manifest_replay', 'exact_source_solver_replay',
  'exact_resume_checkpoint_binding', 'exact_terminal_checkpoint_replay',
  'exact_numerical_result_ir_replay',
  'exact_recovery_replay', 'full_node_equilibrium_pass',
  'residual_gate_pass', 'increment_gate_pass', 'line_search_pass',
  'terminal_reassembled_equilibrium_pass',
  'unsupported_feature_count', 'fallback_count', 'regularization_count',
  'external_vv_level', 'workbench_execution', 'public_product_promotion',
  'release_eligible', 'claim_boundary',
])

export interface PublishedFrame3DLoadControlResult {
  kind: 'frame3d-load-control'
  adapterId: typeof FRAME3D_LOAD_CONTROL_ADAPTER_ID
  resultContract: typeof FRAME3D_LOAD_CONTROL_RESULT_CONTRACT
  profile: typeof FRAME3D_LOAD_CONTROL_PROFILE
  resultHash: string
  source: {
    modelIrContentHash: string
    adapterHash: string
    apiRequestHash: string
    loadPatternId: string
    nodeIds: readonly string[]
    memberIds: readonly string[]
  }
  schedule: {
    loadFactors: readonly number[]
    acceptedStepCount: number
    resumeCompletedPrefixCount: number
    acceptedSuffixStepCount: number
    completedPrefixCount: number
    remainingLoadFactorCount: 0
    finalLoadFactor: number
  }
  numericalResultIr: {
    resultHash: string
    backendRole: typeof FRAME3D_LOAD_CONTROL_BACKEND_ROLE
    displacementDataHash: string
    dofCount: number
    reactionAuthority: 'not_evaluated'
    memberForceAuthority: 'not_evaluated'
  }
  recovery: {
    nodeDisplacementCount: number
    supportReactionCount: number
    memberRecoveryCount: number
    fullNodeEquilibriumCount: number
    reactionAuthority: 'bounded_candidate'
    memberForceAuthority: 'bounded_candidate'
  }
  equilibrium: {
    maximumScaledBalanceResidual: number
    scaledTolerance: number
    maximumForceBalanceResidualN: number
    forceToleranceN: number
    maximumMomentBalanceResidualNM: number
    momentToleranceNM: number
    authority: 'authoritative_reassembled'
  }
  checkpoint: {
    terminalArtifactLogicalHash: string
    resumeContractHash: string
    terminalCheckpointHash: string
  }
  authority: {
    workbenchExecution: false
    externalVvLevel: 0
    designAuthority: false
    publicProductPromotion: false
    releaseEligible: false
    commercialUse: false
  }
}

export interface Frame3DValidationContext {
  jobRequestArtifactSha256: string
  resumeCheckpointArtifactSha256: string | null
  resultArtifactSha256: string
  jobCompletedSteps: number
  jobTotalSteps: number
  jobResumeContractHash: string | null
  evidenceCheckpointHash: string | null
  evidenceValidatorId: unknown
}

export interface Frame3DResultValidation {
  value: PublishedFrame3DLoadControlResult | null
  integrityUnavailable: boolean
}

class Frame3DContractError extends Error {}

function requireContract(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Frame3DContractError(message)
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function exactKeys(value: Record<string, unknown>, expected: ReadonlySet<string>): boolean {
  const keys = Object.keys(value)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}

function exactObject(value: unknown, expected: Readonly<Record<string, unknown>>): boolean {
  return record(value)
    && exactKeys(value, new Set(Object.keys(expected)))
    && Object.entries(expected).every(([key, item]) => value[key] === item)
}

function hash(value: unknown): value is string {
  return typeof value === 'string' && HASH.test(value)
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function integer(value: unknown, minimum: number, maximum?: number): value is number {
  return finite(value)
    && Number.isInteger(value)
    && value >= minimum
    && (maximum === undefined || value <= maximum)
}

function stableIds(value: unknown, minimum: number, maximum?: number): value is string[] {
  return Array.isArray(value)
    && value.length >= minimum
    && (maximum === undefined || value.length <= maximum)
    && value.every((item) => typeof item === 'string' && STABLE_ID.test(item))
    && new Set(value).size === value.length
}

function finiteVector(value: unknown, length: number): value is number[] {
  return Array.isArray(value) && value.length === length && value.every(finite)
}

function sameNumbers(left: unknown, right: readonly number[]): left is number[] {
  return Array.isArray(left)
    && left.length === right.length
    && left.every((value, index) => finite(value) && value === right[index])
}

function sameStrings(left: unknown, right: readonly string[]): left is string[] {
  return Array.isArray(left)
    && left.length === right.length
    && left.every((value, index) => value === right[index])
}

function exactCheckpoint(
  value: unknown,
  modelHash: string,
  solverContractHash: string,
): Record<string, unknown> {
  requireContract(record(value) && exactKeys(value, CHECKPOINT_KEYS), 'published Frame3D checkpoint shape is invalid')
  requireContract(
    value.schema_version === 'corotational-frame3d-global-checkpoint.v1'
      && value.profile === FRAME3D_LOAD_CONTROL_SOLVER_PROFILE
      && value.model_hash === modelHash
      && value.solver_contract_hash === solverContractHash
      && finite(value.load_factor)
      && finiteVector(value.displacement, (value.displacement as unknown[])?.length ?? -1)
      && (value.displacement as unknown[]).length >= 18
      && (value.displacement as unknown[]).length <= 96
      && (value.displacement as unknown[]).length % 6 === 0
      && integer(value.converged_iterations, 0, 100)
      && finite(value.residual_inf_norm_kn)
      && value.residual_inf_norm_kn >= 0
      && (value.parent_checkpoint_hash === null || hash(value.parent_checkpoint_hash))
      && hash(value.checkpoint_hash),
    'published Frame3D checkpoint binding is invalid',
  )
  return value
}

function validateSchedule(value: unknown): number[] {
  requireContract(Array.isArray(value) && value.length >= 1 && value.length <= 64, 'published Frame3D load schedule is invalid')
  const schedule = value as unknown[]
  requireContract(
    schedule.every((factor, index) => finite(factor)
      && factor > 0
      && factor <= 1
      && (index === 0 || factor > (schedule[index - 1] as number)))
      && finite(schedule[schedule.length - 1]),
    'published Frame3D load schedule is invalid',
  )
  return schedule as number[]
}

function validateSource(value: unknown): Record<string, unknown> {
  requireContract(record(value) && exactKeys(value, SOURCE_KEYS), 'published Frame3D source adapter binding is invalid')
  requireContract(
    value.schema_version === 'bounded-frame3d-load-control-model-ir-adapter.v1'
      && value.adapter_profile === FRAME3D_LOAD_CONTROL_SOURCE_ADAPTER_PROFILE
      && hash(value.adapter_hash)
      && hash(value.model_ir_content_hash)
      && hash(value.model_ir_semantic_hash)
      && hash(value.model_ir_provenance_hash)
      && typeof value.load_pattern_id === 'string'
      && STABLE_ID.test(value.load_pattern_id)
      && hash(value.model_hash)
      && stableIds(value.node_ids, 3, 16)
      && stableIds(value.member_ids, 2, 32)
      && stableIds(value.material_ids, 1)
      && stableIds(value.section_ids, 1)
      && Array.isArray(value.restrained_global_dofs)
      && value.restrained_global_dofs.length >= 1
      && value.restrained_global_dofs.length < (value.node_ids as string[]).length * 6
      && value.restrained_global_dofs.every((item, index, rows) => integer(item, 0, (value.node_ids as string[]).length * 6 - 1)
        && (index === 0 || item > (rows[index - 1] as number)))
      && hash(value.unit_conversion_hash)
      && hash(value.entity_mapping_hash)
      && value.claim_boundary === SOURCE_ADAPTER_CLAIM_BOUNDARY
      && hash(value.request_hash),
    'published Frame3D source adapter binding is invalid',
  )
  return value
}

function validateNodeDisplacements(value: unknown, nodeIds: readonly string[]): number[] {
  requireContract(Array.isArray(value) && value.length === nodeIds.length, 'published Frame3D node displacement order is invalid')
  const flattened: number[] = []
  value.forEach((item, index) => {
    requireContract(record(item) && exactKeys(item, new Set(['node_id', 'components', 'unit_profile'])), 'published Frame3D node displacement shape is invalid')
    requireContract(item.node_id === nodeIds[index] && item.unit_profile === 'ux_uy_uz_m_rx_ry_rz_rad.v1', 'published Frame3D node displacement order is invalid')
    const components = item.components
    requireContract(record(components) && exactKeys(components, new Set(['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ'])), 'published Frame3D node displacement components are invalid')
    for (const name of ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ']) {
      requireContract(finite(components[name]), 'published Frame3D node displacement components are invalid')
      flattened.push(components[name] as number)
    }
  })
  return flattened
}

function validateSupportReactions(value: unknown, nodeIds: readonly string[]): number {
  requireContract(Array.isArray(value) && value.length >= 1 && value.length <= nodeIds.length, 'published Frame3D support reaction order is invalid')
  let priorIndex = -1
  value.forEach((item) => {
    requireContract(record(item) && exactKeys(item, new Set(['node_id', 'force_n', 'moment_n_m'])), 'published Frame3D support reaction shape is invalid')
    const nodeIndex = nodeIds.indexOf(String(item.node_id))
    requireContract(nodeIndex > priorIndex, 'published Frame3D support reaction order is invalid')
    priorIndex = nodeIndex
    requireContract(record(item.force_n) && exactKeys(item.force_n, new Set(['FX', 'FY', 'FZ'])), 'published Frame3D support reaction force is invalid')
    requireContract(record(item.moment_n_m) && exactKeys(item.moment_n_m, new Set(['MX', 'MY', 'MZ'])), 'published Frame3D support reaction moment is invalid')
    requireContract(Object.values(item.force_n).every(finite) && Object.values(item.moment_n_m).every(finite), 'published Frame3D support reaction values are invalid')
  })
  return value.length
}

function validateMemberRecovery(value: unknown, memberIds: readonly string[], nodeIds: readonly string[]): number {
  requireContract(Array.isArray(value) && value.length === memberIds.length, 'published Frame3D member recovery order is invalid')
  value.forEach((item, index) => {
    requireContract(record(item) && exactKeys(item, new Set([
      'member_id', 'node_ids', 'initial_length_m', 'current_length_m',
      'strain_energy_kn_m', 'basic_deformations', 'basic_forces_solver_units',
      'global_end_forces_solver_units', 'force_unit_profile',
    ])), 'published Frame3D member recovery shape is invalid')
    requireContract(item.member_id === memberIds[index]
      && Array.isArray(item.node_ids)
      && item.node_ids.length === 2
      && item.node_ids[0] !== item.node_ids[1]
      && item.node_ids.every((nodeId) => nodeIds.includes(String(nodeId)))
      && finite(item.initial_length_m) && item.initial_length_m > 0
      && finite(item.current_length_m) && item.current_length_m > 0
      && finite(item.strain_energy_kn_m) && item.strain_energy_kn_m >= 0
      && finiteVector(item.basic_deformations, 7)
      && finiteVector(item.basic_forces_solver_units, 7)
      && finiteVector(item.global_end_forces_solver_units, 12)
      && item.force_unit_profile === 'forces_kn_moments_kn_m.v1',
    'published Frame3D member recovery binding is invalid')
  })
  return value.length
}

function validateFullNodeEquilibrium(value: unknown, nodeIds: readonly string[]): {
  count: number
  maximumForce: number
  maximumMoment: number
} {
  requireContract(Array.isArray(value) && value.length === nodeIds.length, 'published Frame3D full-node equilibrium order is invalid')
  let maximumForce = 0
  let maximumMoment = 0
  value.forEach((item, index) => {
    requireContract(record(item) && exactKeys(item, new Set([
      'node_id', 'internal_minus_applied_force_n',
      'internal_minus_applied_moment_n_m', 'reaction_force_n',
      'reaction_moment_n_m', 'balance_residual_force_n',
      'balance_residual_moment_n_m',
    ])), 'published Frame3D full-node equilibrium shape is invalid')
    requireContract(item.node_id === nodeIds[index], 'published Frame3D full-node equilibrium order is invalid')
    for (const name of [
      'internal_minus_applied_force_n', 'internal_minus_applied_moment_n_m',
      'reaction_force_n', 'reaction_moment_n_m', 'balance_residual_force_n',
      'balance_residual_moment_n_m',
    ]) requireContract(finiteVector(item[name], 3), 'published Frame3D full-node equilibrium values are invalid')
    maximumForce = Math.max(maximumForce, ...(item.balance_residual_force_n as number[]).map(Math.abs))
    maximumMoment = Math.max(maximumMoment, ...(item.balance_residual_moment_n_m as number[]).map(Math.abs))
  })
  return { count: value.length, maximumForce, maximumMoment }
}

function validateStepMemberRows(value: unknown, memberIds: readonly string[]): void {
  requireContract(Array.isArray(value) && value.length === memberIds.length, 'published Frame3D source step member order is invalid')
  value.forEach((item, index) => {
    requireContract(record(item) && exactKeys(item, STEP_MEMBER_KEYS), 'published Frame3D source step member shape is invalid')
    requireContract(item.member_id === memberIds[index]
      && integer(item.node_i, 0) && integer(item.node_j, 0)
      && item.node_i !== item.node_j
      && finite(item.initial_length_m) && item.initial_length_m > 0
      && finite(item.current_length_m) && item.current_length_m > 0
      && finite(item.strain_energy_kn_m) && item.strain_energy_kn_m >= 0
      && finiteVector(item.basic_deformations, 7)
      && finiteVector(item.basic_forces, 7)
      && finiteVector(item.global_end_forces, 12),
    'published Frame3D source step member binding is invalid')
  })
}

async function validateNumericalResult(
  value: unknown,
  source: Record<string, unknown>,
  metrics: Record<string, unknown>,
  displacement: readonly number[],
): Promise<{ projection: PublishedFrame3DLoadControlResult['numericalResultIr']; integrityUnavailable: boolean }> {
  requireContract(record(value) && exactKeys(value, NUMERICAL_RESULT_KEYS), 'published Frame3D numerical ResultIR shape is invalid')
  requireContract(value.schema_version === 'structural-analysis-nonlinear-numerical-result-ir.v1'
    && value.result_id === 'bounded.frame3d.multimember.load-control'
    && hash(value.result_hash)
    && value.result_kind === 'nonlinear_static_numerical_state'
    && value.authority_profile === 'authoritative_converged_nonlinear_numerical_and_terminal_material_state.v1'
    && exactObject(value.authority, NUMERICAL_AUTHORITY)
    && record(value.bindings) && exactKeys(value.bindings, NUMERICAL_BINDING_KEYS)
    && Object.entries(value.bindings).every(([key, item]) => key === 'state_epoch' ? integer(item, 1, 64) : hash(item))
    && value.bindings.model_ir_content_hash === source.model_ir_content_hash
    && value.bindings.state_epoch === metrics.numerical_result_state_epoch
    && record(value.backend) && exactKeys(value.backend, new Set(['role', 'receipt_hash']))
    && value.backend.role === FRAME3D_LOAD_CONTROL_BACKEND_ROLE
    && hash(value.backend.receipt_hash)
    && value.load_factor === metrics.final_load_factor
    && value.time_s === 0
    && integer(value.dof_count, 18, 96)
    && value.dof_count === (source.node_ids as string[]).length * 6
    && exactObject(value.claim_boundary, NUMERICAL_CLAIM_BOUNDARY)
    && record(value.extensions) && Object.keys(value.extensions).length === 0,
  'published Frame3D numerical ResultIR identity or authority is invalid')

  const descriptor = value.displacement_artifact
  requireContract(record(descriptor) && exactKeys(descriptor, DISPLACEMENT_DESCRIPTOR_KEYS), 'published Frame3D displacement descriptor is invalid')
  const stateHash = value.bindings.state_hash as string
  const materialHash = value.bindings.material_state_bundle_hash as string
  const expectedUri = `artifact://nonlinear-result/bounded.frame3d.multimember.load-control/${stateHash.slice(7, 23)}/${materialHash.slice(7, 23)}/displacement_global.f64le`
  requireContract(descriptor.name === 'displacement_global_si'
    && descriptor.dtype === '<f8'
    && sameNumbers(descriptor.shape, [value.dof_count as number])
    && descriptor.layout === 'C'
    && descriptor.byte_order === 'little'
    && descriptor.byte_length === (value.dof_count as number) * 8
    && descriptor.storage_profile === 'canonical_little_endian_fp64_binary.v1'
    && descriptor.unit_profile === 'node_major_ux_uy_uz_m_rx_ry_rz_rad.v1'
    && hash(descriptor.data_hash)
    && hash(descriptor.content_hash)
    && descriptor.artifact_uri === expectedUri,
  'published Frame3D displacement descriptor is invalid')

  const raw = new Uint8Array(displacement.length * 8)
  const view = new DataView(raw.buffer)
  displacement.forEach((item, index) => view.setFloat64(index * 8, item === 0 ? 0 : item, true))
  const replayedDataHash = await sha256Bytes(raw)
  const descriptorBody = { ...descriptor }
  delete descriptorBody.content_hash
  const replayedDescriptorHash = await sha256Hex(canonicalJson(descriptorBody))
  requireContract(replayedDataHash === null || replayedDataHash === descriptor.data_hash, 'published Frame3D displacement data hash is invalid')
  requireContract(replayedDescriptorHash === null || replayedDescriptorHash === descriptor.content_hash, 'published Frame3D displacement descriptor hash is invalid')
  return {
    projection: {
      resultHash: value.result_hash as string,
      backendRole: FRAME3D_LOAD_CONTROL_BACKEND_ROLE,
      displacementDataHash: descriptor.data_hash as string,
      dofCount: value.dof_count as number,
      reactionAuthority: 'not_evaluated',
      memberForceAuthority: 'not_evaluated',
    },
    integrityUnavailable: replayedDataHash === null || replayedDescriptorHash === null,
  }
}

export async function validatePublishedFrame3DLoadControlResult(
  value: Record<string, unknown>,
  errors: string[],
): Promise<Frame3DResultValidation> {
  try {
    requireContract(exactKeys(value, TOP_LEVEL_KEYS)
      && value.schema_version === FRAME3D_LOAD_CONTROL_RESULT_CONTRACT
      && value.profile === FRAME3D_LOAD_CONTROL_PROFILE
      && value.status === 'ready'
      && value.contract_pass === true
      && hash(value.result_hash)
      && value.claim_boundary === RESULT_CLAIM_BOUNDARY
      && Array.isArray(value.warnings)
      && sameStrings(value.warnings, [
        'experimental_bounded_multimember_frame3d_load_control',
        'public_product_promotion_false',
        'external_vv_not_attached',
      ]),
    'published Frame3D load-control result identity is invalid')

    const source = validateSource(value.source_binding)
    const nodeIds = source.node_ids as string[]
    const memberIds = source.member_ids as string[]
    const schedule = validateSchedule(value.load_factors)

    const metrics = value.metrics
    requireContract(record(metrics) && exactKeys(metrics, METRIC_KEYS)
      && metrics.final_load_factor === schedule[schedule.length - 1]
      && integer(metrics.accepted_step_count, 1, 64)
      && integer(metrics.numerical_result_state_epoch, 1, 64)
      && metrics.state_epoch_scope === 'current_request_suffix'
      && metrics.completed_prefix_count === schedule.length
      && metrics.remaining_load_factor_count === 0
      && metrics.node_count === nodeIds.length
      && metrics.member_count === memberIds.length
      && metrics.fallback_count === 0
      && metrics.regularization_count === 0,
    'published Frame3D terminal metrics are invalid')

    const solver = value.solver
    requireContract(record(solver) && exactKeys(solver, new Set(['source_receipt', 'execution', 'full_node_equilibrium'])), 'published Frame3D solver receipt is invalid')
    const sourceReceipt = solver.source_receipt
    requireContract(record(sourceReceipt) && exactKeys(sourceReceipt, SOURCE_RECEIPT_KEYS), 'published Frame3D source solver receipt is invalid')
    requireContract(sourceReceipt.schema_version === 'corotational-frame3d-global-solution.v2'
      && sourceReceipt.profile === FRAME3D_LOAD_CONTROL_SOLVER_PROFILE
      && sourceReceipt.model_hash === source.model_hash
      && hash(sourceReceipt.solver_contract_hash)
      && hash(sourceReceipt.start_checkpoint_hash)
      && finite(sourceReceipt.maximum_free_residual_inf_norm_kn) && sourceReceipt.maximum_free_residual_inf_norm_kn >= 0
      && finite(sourceReceipt.maximum_scaled_residual_inf_norm) && sourceReceipt.maximum_scaled_residual_inf_norm >= 0
      && finite(sourceReceipt.maximum_scaled_increment_inf_norm) && sourceReceipt.maximum_scaled_increment_inf_norm >= 0
      && sourceReceipt.exact_checkpoint_resume_supported === true
      && sourceReceipt.regularization_used === false
      && sourceReceipt.fallback_used === false
      && sourceReceipt.contract_pass === true
      && sourceReceipt.claim_boundary === SOURCE_SOLVER_CLAIM_BOUNDARY
      && hash(sourceReceipt.result_hash),
    'published Frame3D source solver identity is invalid')

    const scaling = sourceReceipt.equation_scaling
    requireContract(record(scaling) && exactKeys(scaling, EQUATION_SCALING_KEYS)
      && scaling.schema_version === 'structural-analysis-equation-scaling-6dof.v1'
      && scaling.policy === 'centroid_diameter_force_moment_6dof.v1'
      && scaling.source_identity_hash === source.model_hash
      && scaling.dof_count === nodeIds.length * 6
      && integer(scaling.free_equation_count, 1, nodeIds.length * 6 - 1)
      && Object.entries(scaling).every(([key, item]) => key.endsWith('_hash')
        ? hash(item)
        : ['schema_version', 'policy', 'dof_count', 'free_equation_count'].includes(key) || finite(item)),
    'published Frame3D equation scaling identity is invalid')

    const execution = solver.execution
    requireContract(record(execution) && exactKeys(execution, EXECUTION_KEYS), 'published Frame3D execution schedule is invalid')
    const accepted = execution.accepted_load_factors
    requireContract(Array.isArray(accepted)
      && accepted.length === metrics.accepted_step_count
      && accepted.length >= 1
      && accepted.length <= schedule.length
      && sameNumbers(accepted, schedule.slice(schedule.length - accepted.length))
      && sameNumbers(execution.requested_load_factors, schedule)
      && execution.completed_prefix_count === schedule.length
      && execution.remaining_load_factor_count === 0
      && execution.state_epoch_scope === 'current_request_suffix'
      && execution.maximum_new_steps === null,
    'published Frame3D execution schedule is invalid')

    const startIndex = schedule.length - accepted.length
    const expectedStartFactor = startIndex === 0 ? 0 : schedule[startIndex - 1]
    const startCheckpoint = exactCheckpoint(execution.start_checkpoint, source.model_hash as string, sourceReceipt.solver_contract_hash as string)
    requireContract(startCheckpoint.load_factor === expectedStartFactor
      && startCheckpoint.checkpoint_hash === sourceReceipt.start_checkpoint_hash,
    'published Frame3D start checkpoint binding is invalid')

    const steps = sourceReceipt.steps
    requireContract(Array.isArray(steps) && steps.length === accepted.length, 'published Frame3D source step count is invalid')
    let parentCheckpointHash = startCheckpoint.checkpoint_hash as string
    let terminalStepCheckpoint: Record<string, unknown> | null = null
    steps.forEach((item, index) => {
      requireContract(record(item) && exactKeys(item, STEP_KEYS), 'published Frame3D source step shape is invalid')
      requireContract(item.load_factor === accepted[index]
        && finiteVector(item.applied_load, nodeIds.length * 6)
        && Array.isArray(item.reactions)
        && item.reactions.every((row) => Array.isArray(row) && row.length === 2 && integer(row[0], 0, nodeIds.length * 6 - 1) && finite(row[1]))
        && finite(item.free_residual_inf_norm_kn) && item.free_residual_inf_norm_kn >= 0
        && finite(item.relative_residual) && item.relative_residual >= 0
        && finite(item.condition_number) && item.condition_number > 0
        && finite(item.raw_translational_residual_inf_norm_kn) && item.raw_translational_residual_inf_norm_kn >= 0
        && finite(item.raw_rotational_residual_inf_norm_kn_m) && item.raw_rotational_residual_inf_norm_kn_m >= 0
        && finite(item.scaled_residual_inf_norm) && item.scaled_residual_inf_norm >= 0
        && finite(item.raw_translation_increment_inf_norm_m) && item.raw_translation_increment_inf_norm_m >= 0
        && finite(item.raw_rotation_increment_inf_norm_rad) && item.raw_rotation_increment_inf_norm_rad >= 0
        && finite(item.scaled_increment_inf_norm) && item.scaled_increment_inf_norm >= 0
        && finite(item.scaled_residual_tolerance) && item.scaled_residual_tolerance > 0
        && finite(item.scaled_increment_tolerance) && item.scaled_increment_tolerance > 0
        && item.residual_gate_passed === true
        && item.increment_gate_passed === true
        && typeof item.line_search_required === 'boolean'
        && finite(item.selected_line_search_alpha) && item.selected_line_search_alpha > 0 && item.selected_line_search_alpha <= 1
        && item.line_search_valid === true
        && item.final_reassembled_equilibrium_passed === true
        && item.parent_state_immutable === true
        && finite(item.scaled_condition_number_1) && item.scaled_condition_number_1 > 0
        && item.equation_scaling_hash === scaling.scaling_hash
        && Array.isArray(item.convergence_history) && item.convergence_history.length >= 1
        && Array.isArray(item.line_search_history),
      'published Frame3D accepted source step is invalid')
      const checkpoint = exactCheckpoint(item.checkpoint, source.model_hash as string, sourceReceipt.solver_contract_hash as string)
      requireContract(checkpoint.load_factor === accepted[index]
        && checkpoint.parent_checkpoint_hash === parentCheckpointHash,
      'published Frame3D source checkpoint lineage is invalid')
      validateStepMemberRows(item.members, memberIds)
      parentCheckpointHash = checkpoint.checkpoint_hash as string
      terminalStepCheckpoint = checkpoint
    })
    requireContract(terminalStepCheckpoint !== null, 'published Frame3D terminal checkpoint is missing')

    const checkpointArtifact = value.checkpoint_artifact
    requireContract(record(checkpointArtifact) && exactKeys(checkpointArtifact, CHECKPOINT_ARTIFACT_KEYS), 'published Frame3D checkpoint artifact binding is invalid')
    requireContract(checkpointArtifact.schema_version === 'bounded-frame3d-load-control-checkpoint-artifact.v1'
      && checkpointArtifact.profile === FRAME3D_LOAD_CONTROL_PROFILE
      && hash(checkpointArtifact.artifact_hash)
      && checkpointArtifact.model_ir_content_hash === source.model_ir_content_hash
      && checkpointArtifact.adapter_hash === source.adapter_hash
      && checkpointArtifact.model_hash === source.model_hash
      && checkpointArtifact.load_pattern_id === source.load_pattern_id
      && sameStrings(checkpointArtifact.node_ids, nodeIds)
      && sameStrings(checkpointArtifact.member_ids, memberIds)
      && checkpointArtifact.solver_contract_hash === sourceReceipt.solver_contract_hash
      && checkpointArtifact.request_hash === source.request_hash
      && hash(checkpointArtifact.resume_contract_hash)
      && checkpointArtifact.public_product_promotion === false
      && checkpointArtifact.release_eligible === false,
    'published Frame3D checkpoint artifact binding is invalid')
    const terminalCheckpoint = exactCheckpoint(checkpointArtifact.checkpoint, source.model_hash as string, sourceReceipt.solver_contract_hash as string)
    requireContract(canonicalJson(terminalCheckpoint) === canonicalJson(terminalStepCheckpoint), 'published Frame3D terminal checkpoint binding is invalid')

    const displacement = validateNodeDisplacements(value.node_displacements, nodeIds)
    requireContract(sameNumbers(terminalCheckpoint.displacement, displacement), 'published Frame3D checkpoint displacement binding is invalid')
    const supportReactionCount = validateSupportReactions(value.support_reactions, nodeIds)
    const memberRecoveryCount = validateMemberRecovery(value.member_recovery, memberIds, nodeIds)
    const fullEquilibrium = validateFullNodeEquilibrium(value.full_node_equilibrium, nodeIds)

    const equilibrium = solver.full_node_equilibrium
    requireContract(record(equilibrium) && exactKeys(equilibrium, EQUILIBRIUM_SUMMARY_KEYS)
      && equilibrium.equilibrium_scaling_hash === scaling.scaling_hash
      && finite(equilibrium.scaled_tolerance) && equilibrium.scaled_tolerance > 0
      && finite(equilibrium.maximum_scaled_balance_residual) && equilibrium.maximum_scaled_balance_residual >= 0
      && equilibrium.maximum_scaled_balance_residual <= equilibrium.scaled_tolerance
      && finite(equilibrium.maximum_force_balance_residual_n) && equilibrium.maximum_force_balance_residual_n >= 0
      && equilibrium.maximum_force_balance_residual_n === fullEquilibrium.maximumForce
      && finite(equilibrium.force_tolerance_n) && equilibrium.force_tolerance_n > 0
      && equilibrium.maximum_force_balance_residual_n <= equilibrium.force_tolerance_n
      && finite(equilibrium.maximum_moment_balance_residual_n_m) && equilibrium.maximum_moment_balance_residual_n_m >= 0
      && equilibrium.maximum_moment_balance_residual_n_m === fullEquilibrium.maximumMoment
      && finite(equilibrium.moment_tolerance_n_m) && equilibrium.moment_tolerance_n_m > 0
      && equilibrium.maximum_moment_balance_residual_n_m <= equilibrium.moment_tolerance_n_m
      && equilibrium.contract_pass === true,
    'published Frame3D full-node equilibrium tolerance is invalid')

    requireContract(exactObject(value.authority, OUTER_AUTHORITY), 'published Frame3D recovery authority is invalid')
    const numerical = await validateNumericalResult(value.numerical_result_ir, source, metrics, displacement)

    return {
      value: {
        kind: 'frame3d-load-control',
        adapterId: FRAME3D_LOAD_CONTROL_ADAPTER_ID,
        resultContract: FRAME3D_LOAD_CONTROL_RESULT_CONTRACT,
        profile: FRAME3D_LOAD_CONTROL_PROFILE,
        resultHash: value.result_hash as string,
        source: {
          modelIrContentHash: source.model_ir_content_hash as string,
          adapterHash: source.adapter_hash as string,
          apiRequestHash: source.request_hash as string,
          loadPatternId: source.load_pattern_id as string,
          nodeIds: Object.freeze([...nodeIds]),
          memberIds: Object.freeze([...memberIds]),
        },
        schedule: {
          loadFactors: Object.freeze([...schedule]),
          acceptedStepCount: metrics.accepted_step_count as number,
          resumeCompletedPrefixCount: startIndex,
          acceptedSuffixStepCount: accepted.length,
          completedPrefixCount: schedule.length,
          remainingLoadFactorCount: 0,
          finalLoadFactor: metrics.final_load_factor as number,
        },
        numericalResultIr: numerical.projection,
        recovery: {
          nodeDisplacementCount: nodeIds.length,
          supportReactionCount,
          memberRecoveryCount,
          fullNodeEquilibriumCount: fullEquilibrium.count,
          reactionAuthority: 'bounded_candidate',
          memberForceAuthority: 'bounded_candidate',
        },
        equilibrium: {
          maximumScaledBalanceResidual: equilibrium.maximum_scaled_balance_residual as number,
          scaledTolerance: equilibrium.scaled_tolerance as number,
          maximumForceBalanceResidualN: equilibrium.maximum_force_balance_residual_n as number,
          forceToleranceN: equilibrium.force_tolerance_n as number,
          maximumMomentBalanceResidualNM: equilibrium.maximum_moment_balance_residual_n_m as number,
          momentToleranceNM: equilibrium.moment_tolerance_n_m as number,
          authority: 'authoritative_reassembled',
        },
        checkpoint: {
          terminalArtifactLogicalHash: checkpointArtifact.artifact_hash as string,
          resumeContractHash: checkpointArtifact.resume_contract_hash as string,
          terminalCheckpointHash: terminalCheckpoint.checkpoint_hash as string,
        },
        authority: {
          workbenchExecution: false,
          externalVvLevel: 0,
          designAuthority: false,
          publicProductPromotion: false,
          releaseEligible: false,
          commercialUse: false,
        },
      },
      integrityUnavailable: numerical.integrityUnavailable,
    }
  } catch (error: unknown) {
    errors.push(error instanceof Frame3DContractError
      ? error.message
      : 'published Frame3D load-control result validation failed')
    return { value: null, integrityUnavailable: false }
  }
}

export function validateFrame3DLoadControlEvidenceReport(
  reportValue: unknown,
  resultValue: unknown,
  context: Frame3DValidationContext,
): boolean {
  if (!record(reportValue) || !exactKeys(reportValue, REPORT_KEYS) || !record(resultValue)) return false
  const source = resultValue.source_binding
  const solver = resultValue.solver
  const numerical = resultValue.numerical_result_ir
  const checkpoint = resultValue.checkpoint_artifact
  const metrics = resultValue.metrics
  if (!record(source) || !record(solver) || !record(solver.source_receipt)
    || !record(solver.execution) || !record(numerical) || !record(numerical.backend)
    || !record(solver.full_node_equilibrium)
    || !Array.isArray(solver.execution.accepted_load_factors)
    || !Array.isArray(resultValue.load_factors)
    || !record(checkpoint) || !record(checkpoint.checkpoint) || !record(metrics)) return false

  const resumeCheckpointRequired = solver.execution.start_checkpoint != null
    && record(solver.execution.start_checkpoint)
    && solver.execution.start_checkpoint.load_factor !== 0
  return reportValue.schema_version === FRAME3D_LOAD_CONTROL_VALIDATION_REPORT
    && reportValue.status === 'ready'
    && reportValue.contract_pass === true
    && reportValue.result_schema_version === FRAME3D_LOAD_CONTROL_RESULT_CONTRACT
    && reportValue.profile === FRAME3D_LOAD_CONTROL_PROFILE
    && reportValue.source_adapter_profile === FRAME3D_LOAD_CONTROL_SOURCE_ADAPTER_PROFILE
    && reportValue.solver_profile === FRAME3D_LOAD_CONTROL_SOLVER_PROFILE
    && reportValue.backend_role === FRAME3D_LOAD_CONTROL_BACKEND_ROLE
    && reportValue.validator_id === FRAME3D_LOAD_CONTROL_VALIDATOR_ID
    && context.evidenceValidatorId === FRAME3D_LOAD_CONTROL_VALIDATOR_ID
    && reportValue.result_hash === resultValue.result_hash
    && reportValue.result_artifact_sha256 === context.resultArtifactSha256
    && reportValue.job_request_artifact_sha256 === context.jobRequestArtifactSha256
    && reportValue.model_ir_content_hash === source.model_ir_content_hash
    && reportValue.model_ir_semantic_hash === source.model_ir_semantic_hash
    && reportValue.model_ir_provenance_hash === source.model_ir_provenance_hash
    && reportValue.adapter_hash === source.adapter_hash
    && reportValue.compiled_model_hash === source.model_hash
    && reportValue.api_request_hash === source.request_hash
    && reportValue.resume_contract_hash === checkpoint.resume_contract_hash
    && (resumeCheckpointRequired
      ? context.jobResumeContractHash === checkpoint.resume_contract_hash
      : context.jobResumeContractHash === null)
    && reportValue.source_solver_receipt_hash === solver.source_receipt.result_hash
    && reportValue.numerical_result_ir_hash === numerical.result_hash
    && reportValue.resume_checkpoint_artifact_sha256 === context.resumeCheckpointArtifactSha256
    && reportValue.resume_checkpoint_artifact_sha256 === context.evidenceCheckpointHash
    && (resumeCheckpointRequired
      ? hash(reportValue.resume_checkpoint_artifact_sha256)
      : reportValue.resume_checkpoint_artifact_sha256 === null)
    && reportValue.terminal_checkpoint_hash === checkpoint.checkpoint.checkpoint_hash
    && reportValue.terminal_checkpoint_artifact_hash === checkpoint.artifact_hash
    && hash(reportValue.terminal_checkpoint_artifact_sha256)
    && hash(reportValue.recovery_hash)
    && hash(reportValue.full_node_equilibrium_hash)
    && reportValue.equilibrium_scaling_hash === solver.full_node_equilibrium.equilibrium_scaling_hash
    && reportValue.final_load_factor === metrics.final_load_factor
    && reportValue.total_load_factor_count === resultValue.load_factors.length
    && reportValue.total_load_factor_count === context.jobTotalSteps
    && reportValue.resume_completed_prefix_count === (resultValue.load_factors.length - solver.execution.accepted_load_factors.length)
    && reportValue.accepted_suffix_step_count === metrics.accepted_step_count
    && reportValue.completed_prefix_count === metrics.completed_prefix_count
    && reportValue.completed_prefix_count === context.jobCompletedSteps
    && reportValue.remaining_load_factor_count === 0
    && reportValue.terminal_checkpoint_embedded === true
    && reportValue.exact_result_manifest_replay === true
    && reportValue.exact_source_solver_replay === true
    && reportValue.exact_resume_checkpoint_binding === true
    && reportValue.exact_terminal_checkpoint_replay === true
    && reportValue.exact_numerical_result_ir_replay === true
    && reportValue.exact_recovery_replay === true
    && reportValue.full_node_equilibrium_pass === true
    && reportValue.residual_gate_pass === true
    && reportValue.increment_gate_pass === true
    && reportValue.line_search_pass === true
    && reportValue.terminal_reassembled_equilibrium_pass === true
    && reportValue.unsupported_feature_count === 0
    && reportValue.fallback_count === 0
    && reportValue.regularization_count === 0
    && reportValue.external_vv_level === 0
    && reportValue.workbench_execution === false
    && reportValue.public_product_promotion === false
    && reportValue.release_eligible === false
    && reportValue.claim_boundary === resultValue.claim_boundary
}
