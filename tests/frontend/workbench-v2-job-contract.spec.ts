import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { createServer } from 'node:http'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
import { validateWorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const hash = `sha256:${'1'.repeat(64)}`
const jobServiceClaimBoundary = 'The job service owns durable orchestration state and content integrity only. It does not define solver truth, engineering acceptance, design-code compliance, distributed consensus, or release readiness.'

function queuedJob(): Record<string, unknown> {
  return {
    schema_version: 'structural-analysis-job-view.v1',
    service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: `job_${'a'.repeat(32)}`,
    status: 'queued',
    revision: 0,
    attempt: 0,
    progress: { completed_steps: 0, total_steps: 4 },
    created_at: '2026-07-22T00:00:00.000000Z',
    updated_at: '2026-07-22T00:00:00.000000Z',
    lease_expires_at: null,
    error_code: null,
    can_resume: false,
    request: { role: 'request', content_hash: hash, byte_length: 100, media_type: 'application/json' },
    checkpoint: null,
    result: null,
    evidence: null,
    resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core',
    result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: jobServiceClaimBoundary,
    terminal_event_hash: hash,
  }
}

test('Workbench accepts the exact read-only queued job projection', () => {
  const validation = validateWorkbenchJobView(queuedJob())
  expect(validation.ok).toBe(true)
  expect(validation.value?.status).toBe('queued')
})

test('Workbench rejects premature result publication and hidden fields', () => {
  const premature = queuedJob()
  premature.result = { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' }
  premature.evidence = { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' }
  expect(validateWorkbenchJobView(premature).errors).toContain('non-succeeded job exposes published artifacts')

  const hiddenTruth = { ...queuedJob(), converged: true }
  expect(validateWorkbenchJobView(hiddenTruth)).toMatchObject({ ok: false, value: null })
})

test('Workbench requires an atomic result and evidence pair for success', () => {
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded',
    revision: 2,
    attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' },
  }
  expect(validateWorkbenchJobView(succeeded).ok).toBe(true)
  expect(validateWorkbenchJobView({ ...succeeded, evidence: null }).ok).toBe(false)
})

test('job success is publication state and carries no inferred convergence field', () => {
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded',
    revision: 2,
    attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' },
  }
  const validation = validateWorkbenchJobView(succeeded)
  expect(validation.ok).toBe(true)
  expect(validation.value).not.toHaveProperty('converged')
})

test('Workbench never accepts a lease token in the tenant projection', () => {
  expect(validateWorkbenchJobView({ ...queuedJob(), lease_token: 'secret' }).ok).toBe(false)
})

function digest(bytes: Uint8Array): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

function canonical(value: unknown): string {
  const sort = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(sort)
    if (item && typeof item === 'object') {
      return Object.keys(item as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, key) => {
          acc[key] = sort((item as Record<string, unknown>)[key])
          return acc
        }, {})
    }
    return item
  }
  return JSON.stringify(sort(value))
}

function canonicalHash(value: unknown): string {
  return digest(new TextEncoder().encode(canonical(value)))
}

function publishedResult(): Record<string, unknown> {
  const authorityAxes = {
    convergence: 'inherited_bounded_candidate',
    displacement: 'exact_bounded_candidate',
    reaction: 'exact_bounded_candidate',
    member_force: 'exact_bounded_candidate',
    member_features: 'not_supported',
    section_resultant: 'exact_bounded_candidate',
    fiber_result: 'exact_bounded_candidate',
    fallback: 'not_used',
    external_vv: 'not_attached',
    engineering_design: 'not_authoritative',
    release_readiness: 'not_authoritative',
  }
  const descriptorNames = [
    'node_translation_m', 'node_rotation_rad', 'reaction_force_n', 'reaction_moment_nm',
    'member_force_n', 'member_moment_nm', 'section_axial_force_n', 'section_moment_nm',
    'section_strain', 'section_curvature_per_m', 'fiber_strain', 'fiber_stress_pa',
    'member_node_indices', 'section_offsets', 'section_xi', 'fiber_offsets', 'fiber_y_m', 'fiber_area_m2',
  ]
  const descriptors = descriptorNames.map((name, index) => ({
    name,
    dtype: name.includes('indices') || name.includes('offsets') ? '<i8' : '<f8',
    shape: [index < 4 ? 4 : 3],
    unit: '1',
    quantity_ids: [],
    order_scope: index < 4 ? 'node' : index < 8 ? 'member' : index < 12 ? 'section' : 'fiber',
    authority_role: index < 12 ? 'output' : 'mapping',
    order_hash: hash,
    data_hash: hash,
    content_hash: hash,
  }))
  const irBody = {
    schema_version: 'corotational-fiber-frame2d-engineering-result-ir.v1',
    engineering_result_id: 'engineering.portal.test',
    result_kind: 'corotational_portal_reaction_member_section_fiber',
    recovery_profile: 'exact_terminal_parent_corotational_section_global_replay.v1',
    authority_profile: 'exact_bounded_portal_engineering_candidate.v1',
    compiler_hash: hash,
    source_adapter_hash: hash,
    model_content_hash: hash,
    problem_contract_hash: hash,
    terminal_checkpoint_hash: hash,
    terminal_assembly_hash: hash,
    quantity_catalog_hash: hash,
    load_factor: 1,
    counts: { node: 4, member: 3, section: 3, fiber: 6 },
    member_ids: ['M1', 'M2', 'M3'],
    metrics: { terminal_assembly_replay_exact: true },
    authority_axes: authorityAxes,
    limitations: ['external_level2_not_attached'],
    array_bundle_hash: canonicalHash(descriptors),
    array_descriptors: descriptors,
  }
  const engineeringResultIr = {
    ...irBody,
    engineering_result_hash: canonicalHash(irBody),
  }
  const resultBody = {
    schema_version: 'unified-nonlinear-frame-result.v1',
    status: 'ready',
    contract_pass: true,
    profile: 'corotational_one_bay_portal.v1',
    source_result_hash: engineeringResultIr.engineering_result_hash,
    contract_bindings: {
      engineering_result_hash: engineeringResultIr.engineering_result_hash,
      engineering_array_bundle_hash: engineeringResultIr.array_bundle_hash,
      quantity_catalog_hash: engineeringResultIr.quantity_catalog_hash,
    },
    authority: authorityAxes,
    engineering_result_ir: engineeringResultIr,
    // Legacy top-level engineering arrays may coexist for API compatibility,
    // but Workbench must not expose them through its durable-job projection.
    node_displacements: [{ node_id: 'legacy-must-not-be-consumed' }],
  }
  return { ...resultBody, result_hash: canonicalHash(resultBody) }
}

function completionEvidence(
  result: Record<string, unknown>,
  resultArtifactHash: string,
): Record<string, unknown> {
  return {
    schema_version: 'structural-analysis-job-completion-evidence.v1',
    job_id: `job_${'a'.repeat(32)}`,
    request_hash: hash,
    checkpoint_hash: null,
    result_artifact_hash: resultArtifactHash,
    validator_id: 'structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result',
    contract_pass: true,
    solver_truth_owner: 'structural_analysis_core',
    validation_report: {
      schema_version: 'unified-nonlinear-frame-validation-report.v1',
      status: 'ready',
      contract_pass: true,
      result_hash: result.result_hash,
      profile: result.profile,
      exact_engineering_recovery: true,
      exact_checkpoint_chain_replay: true,
      checkpoint_available: true,
      unsupported_feature_count: 0,
      fallback_count: 0,
      regularization_count: 0,
    },
    claim_boundary: jobServiceClaimBoundary,
  }
}

const frame3dClaimBoundary = 'This bounded candidate API executes one source-bound 3-16 node, 2-32 member elastic ModelIR v2 Frame3D load-control path. It returns authoritative nonlinear numerical ResultIR displacement/convergence, exact durable checkpoint restart, and bounded solver-derived reactions, member recovery, and full-node equilibrium. It has no stateful material, distributed load, offset/release, external-V&V, design, public-product, release, or commercial authority.'
const frame3dSourceClaimBoundary = 'This adapter compiles one selected zero-self-weight ModelIR v2 load pattern into the bounded dense elastic corotational Frame3D load-control model. It requires 3-16 nodes, 2-32 connected unreleased zero-offset frame members, zero prescribed support values, bounded exact-binary64 coordinates, properties and loads, and a nonzero load on a free equation. It creates no stateful-material, external-V&V, design, public-product, release, or commercial authority.'
const frame3dSourceSolverClaimBoundary = 'Small dense elastic 3D frame verification path using the numerical-energy element tangent, explicit nodal loads and restraints, residual-and-increment commit gates, deterministic backtracking, and exact checkpoint lineage. It has no stateful section, distributed load, release/offset, warping coupling, transient dynamics, external V&V, or release authority.'
const frame3dValidatorId = 'structural_analysis.api.frame3d_load_control.validate_bounded_frame3d_load_control_result_manifest'
const frame3dHashes = {
  model: `sha256:${'2'.repeat(64)}`,
  solverContract: `sha256:${'3'.repeat(64)}`,
  startCheckpoint: `sha256:${'4'.repeat(64)}`,
  terminalCheckpoint: `sha256:${'5'.repeat(64)}`,
  adapter: `sha256:${'6'.repeat(64)}`,
  modelIrContent: `sha256:${'7'.repeat(64)}`,
  modelIrSemantic: `sha256:${'8'.repeat(64)}`,
  modelIrProvenance: `sha256:${'9'.repeat(64)}`,
  apiRequest: `sha256:${'a'.repeat(64)}`,
  resumeContract: `sha256:${'b'.repeat(64)}`,
  sourceReceipt: `sha256:${'c'.repeat(64)}`,
  numericalResult: `sha256:${'d'.repeat(64)}`,
  equilibriumScaling: `sha256:${'e'.repeat(64)}`,
  state: `sha256:${'f'.repeat(64)}`,
  material: `sha256:${'0'.repeat(64)}`,
  resultLogical: `sha256:${'12'.repeat(32)}`,
  terminalArtifactLogical: `sha256:${'23'.repeat(32)}`,
  terminalArtifactSha256: `sha256:${'34'.repeat(32)}`,
  resumeCheckpointLogical: `sha256:${'45'.repeat(32)}`,
}

function frame3dCheckpoint(
  loadFactor: number,
  parentCheckpointHash: string | null,
  checkpointHash = loadFactor === 0
    ? frame3dHashes.startCheckpoint
    : frame3dHashes.terminalCheckpoint,
): Record<string, unknown> {
  return {
    schema_version: 'corotational-frame3d-global-checkpoint.v1',
    profile: 'dense_elastic_corotational_timoshenko_frame3d_load_control.v2',
    model_hash: frame3dHashes.model,
    solver_contract_hash: frame3dHashes.solverContract,
    load_factor: loadFactor,
    displacement: Array(18).fill(0),
    converged_iterations: loadFactor === 0 ? 0 : 1,
    residual_inf_norm_kn: 0,
    parent_checkpoint_hash: parentCheckpointHash,
    checkpoint_hash: checkpointHash,
  }
}

function frame3dStepMember(memberId: string, nodeI: number, nodeJ: number): Record<string, unknown> {
  return {
    member_id: memberId,
    node_i: nodeI,
    node_j: nodeJ,
    initial_length_m: 1,
    current_length_m: 1,
    strain_energy_kn_m: 0,
    basic_deformations: Array(7).fill(0),
    basic_forces: Array(7).fill(0),
    global_end_forces: Array(12).fill(0),
  }
}

function frame3dPublishedResult(): Record<string, unknown> {
  const zeros = Array(18).fill(0)
  const displacementMetadata = {
    name: 'displacement_global_si',
    dtype: '<f8',
    shape: [18],
    layout: 'C',
    byte_order: 'little',
    byte_length: 144,
    storage_profile: 'canonical_little_endian_fp64_binary.v1',
    unit_profile: 'node_major_ux_uy_uz_m_rx_ry_rz_rad.v1',
    data_hash: digest(new Uint8Array(144)),
    artifact_uri: `artifact://nonlinear-result/bounded.frame3d.multimember.load-control/${'f'.repeat(16)}/${'0'.repeat(16)}/displacement_global.f64le`,
  }
  const displacementArtifact = {
    ...displacementMetadata,
    content_hash: canonicalHash(displacementMetadata),
  }
  const numericalAuthority = {
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
  }
  const numericalClaimBoundary = {
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
  }
  const startCheckpoint = frame3dCheckpoint(0, null)
  const terminalCheckpoint = frame3dCheckpoint(1, frame3dHashes.startCheckpoint)
  const sourceStep = {
    load_factor: 1,
    applied_load: zeros,
    reactions: [[0, 0]],
    free_residual_inf_norm_kn: 0,
    relative_residual: 0,
    condition_number: 1,
    raw_translational_residual_inf_norm_kn: 0,
    raw_rotational_residual_inf_norm_kn_m: 0,
    scaled_residual_inf_norm: 0,
    raw_translation_increment_inf_norm_m: 0,
    raw_rotation_increment_inf_norm_rad: 0,
    scaled_increment_inf_norm: 0,
    scaled_residual_tolerance: 1e-6,
    scaled_increment_tolerance: 1e-6,
    residual_gate_passed: true,
    increment_gate_passed: true,
    line_search_required: true,
    selected_line_search_alpha: 1,
    line_search_valid: true,
    final_reassembled_equilibrium_passed: true,
    parent_state_immutable: true,
    scaled_condition_number_1: 1,
    equation_scaling_hash: frame3dHashes.equilibriumScaling,
    convergence_history: [{}],
    line_search_history: [],
    checkpoint: terminalCheckpoint,
    members: [
      frame3dStepMember('M1', 0, 1),
      frame3dStepMember('M2', 1, 2),
    ],
  }
  const equationScaling = {
    schema_version: 'structural-analysis-equation-scaling-6dof.v1',
    policy: 'centroid_diameter_force_moment_6dof.v1',
    source_identity_hash: frame3dHashes.model,
    characteristic_length_m: 1,
    reference_force: 1,
    residual_translation_scale: 1,
    residual_rotation_scale: 1,
    increment_translation_scale_m: 1,
    increment_rotation_scale_rad: 1,
    dof_count: 18,
    free_equation_count: 12,
    source_node_coordinates_hash: hash,
    source_reference_load_hash: hash,
    source_free_dofs_hash: hash,
    row_equilibration_hash: hash,
    column_equilibration_hash: hash,
    scaling_hash: frame3dHashes.equilibriumScaling,
  }
  const nodeDisplacements = ['N1', 'N2', 'N3'].map((nodeId) => ({
    node_id: nodeId,
    components: { UX: 0, UY: 0, UZ: 0, RX: 0, RY: 0, RZ: 0 },
    unit_profile: 'ux_uy_uz_m_rx_ry_rz_rad.v1',
  }))
  const memberRecovery = [
    { member_id: 'M1', node_ids: ['N1', 'N2'] },
    { member_id: 'M2', node_ids: ['N2', 'N3'] },
  ].map((row) => ({
    ...row,
    initial_length_m: 1,
    current_length_m: 1,
    strain_energy_kn_m: 0,
    basic_deformations: Array(7).fill(0),
    basic_forces_solver_units: Array(7).fill(0),
    global_end_forces_solver_units: Array(12).fill(0),
    force_unit_profile: 'forces_kn_moments_kn_m.v1',
  }))
  const fullNodeEquilibrium = ['N1', 'N2', 'N3'].map((nodeId) => ({
    node_id: nodeId,
    internal_minus_applied_force_n: [0, 0, 0],
    internal_minus_applied_moment_n_m: [0, 0, 0],
    reaction_force_n: [0, 0, 0],
    reaction_moment_n_m: [0, 0, 0],
    balance_residual_force_n: [0, 0, 0],
    balance_residual_moment_n_m: [0, 0, 0],
  }))
  return {
    schema_version: 'bounded-frame3d-load-control-result.v1',
    profile: 'bounded_multimember_frame3d_load_control_model_ir_api.v1',
    status: 'ready',
    contract_pass: true,
    result_hash: frame3dHashes.resultLogical,
    source_binding: {
      schema_version: 'bounded-frame3d-load-control-model-ir-adapter.v1',
      adapter_profile: 'model_ir_v2_to_multimember_corotational_frame3d_load_control.v1',
      adapter_hash: frame3dHashes.adapter,
      model_ir_content_hash: frame3dHashes.modelIrContent,
      model_ir_semantic_hash: frame3dHashes.modelIrSemantic,
      model_ir_provenance_hash: frame3dHashes.modelIrProvenance,
      load_pattern_id: 'LC1',
      model_hash: frame3dHashes.model,
      node_ids: ['N1', 'N2', 'N3'],
      member_ids: ['M1', 'M2'],
      material_ids: ['MAT1'],
      section_ids: ['SEC1'],
      restrained_global_dofs: [0, 1, 2, 3, 4, 5],
      unit_conversion_hash: hash,
      entity_mapping_hash: hash,
      claim_boundary: frame3dSourceClaimBoundary,
      request_hash: frame3dHashes.apiRequest,
    },
    load_factors: [1],
    solver: {
      source_receipt: {
        schema_version: 'corotational-frame3d-global-solution.v2',
        profile: 'dense_elastic_corotational_timoshenko_frame3d_load_control.v2',
        model_hash: frame3dHashes.model,
        solver_contract_hash: frame3dHashes.solverContract,
        start_checkpoint_hash: frame3dHashes.startCheckpoint,
        steps: [sourceStep],
        maximum_free_residual_inf_norm_kn: 0,
        maximum_scaled_residual_inf_norm: 0,
        maximum_scaled_increment_inf_norm: 0,
        equation_scaling: equationScaling,
        result_hash: frame3dHashes.sourceReceipt,
        exact_checkpoint_resume_supported: true,
        regularization_used: false,
        fallback_used: false,
        contract_pass: true,
        claim_boundary: frame3dSourceSolverClaimBoundary,
      },
      execution: {
        start_checkpoint: startCheckpoint,
        requested_load_factors: [1],
        accepted_load_factors: [1],
        maximum_new_steps: null,
        completed_prefix_count: 1,
        remaining_load_factor_count: 0,
        state_epoch_scope: 'current_request_suffix',
      },
      full_node_equilibrium: {
        equilibrium_scaling_hash: frame3dHashes.equilibriumScaling,
        scaled_tolerance: 1e-6,
        maximum_scaled_balance_residual: 0,
        maximum_force_balance_residual_n: 0,
        maximum_moment_balance_residual_n_m: 0,
        force_tolerance_n: 1e-6,
        moment_tolerance_n_m: 1e-6,
        contract_pass: true,
      },
    },
    numerical_result_ir: {
      schema_version: 'structural-analysis-nonlinear-numerical-result-ir.v1',
      result_id: 'bounded.frame3d.multimember.load-control',
      result_hash: frame3dHashes.numericalResult,
      result_kind: 'nonlinear_static_numerical_state',
      authority_profile: 'authoritative_converged_nonlinear_numerical_and_terminal_material_state.v1',
      authority: numericalAuthority,
      bindings: {
        model_ir_content_hash: frame3dHashes.modelIrContent,
        execution_plan_hash: hash,
        equation_scaling_hash: hash,
        reduced_csr_identity_hash: hash,
        operator_hash: hash,
        state_hash: frame3dHashes.state,
        state_epoch: 1,
        material_state_bundle_hash: frame3dHashes.material,
        integration_point_order_hash: hash,
        path_history_hash: hash,
        nonlinear_terminal_hash: hash,
        full_residual_receipt_hash: hash,
        boundary_condition_receipt_hash: hash,
      },
      backend: { role: 'cpu_reference', receipt_hash: hash },
      load_factor: 1,
      time_s: 0,
      dof_count: 18,
      displacement_artifact: displacementArtifact,
      claim_boundary: numericalClaimBoundary,
      extensions: {},
    },
    node_displacements: nodeDisplacements,
    support_reactions: [{
      node_id: 'N1',
      force_n: { FX: 0, FY: 0, FZ: 0 },
      moment_n_m: { MX: 0, MY: 0, MZ: 0 },
    }],
    member_recovery: memberRecovery,
    full_node_equilibrium: fullNodeEquilibrium,
    checkpoint_artifact: {
      schema_version: 'bounded-frame3d-load-control-checkpoint-artifact.v1',
      profile: 'bounded_multimember_frame3d_load_control_model_ir_api.v1',
      artifact_hash: frame3dHashes.terminalArtifactLogical,
      model_ir_content_hash: frame3dHashes.modelIrContent,
      adapter_hash: frame3dHashes.adapter,
      model_hash: frame3dHashes.model,
      load_pattern_id: 'LC1',
      node_ids: ['N1', 'N2', 'N3'],
      member_ids: ['M1', 'M2'],
      solver_contract_hash: frame3dHashes.solverContract,
      request_hash: frame3dHashes.apiRequest,
      resume_contract_hash: frame3dHashes.resumeContract,
      checkpoint: terminalCheckpoint,
      public_product_promotion: false,
      release_eligible: false,
    },
    metrics: {
      final_load_factor: 1,
      accepted_step_count: 1,
      numerical_result_state_epoch: 1,
      state_epoch_scope: 'current_request_suffix',
      completed_prefix_count: 1,
      remaining_load_factor_count: 0,
      node_count: 3,
      member_count: 2,
      fallback_count: 0,
      regularization_count: 0,
    },
    authority: {
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
    },
    warnings: [
      'experimental_bounded_multimember_frame3d_load_control',
      'public_product_promotion_false',
      'external_vv_not_attached',
    ],
    claim_boundary: frame3dClaimBoundary,
  }
}

function frame3dCompletionEvidence(
  result: Record<string, unknown>,
  resultArtifactSha256: string,
  resumeCheckpointArtifactSha256: string | null = null,
): Record<string, unknown> {
  const source = result.source_binding as Record<string, unknown>
  const solver = result.solver as Record<string, Record<string, unknown>>
  const numerical = result.numerical_result_ir as Record<string, unknown>
  const checkpoint = result.checkpoint_artifact as Record<string, unknown>
  const terminalCheckpoint = checkpoint.checkpoint as Record<string, unknown>
  const metrics = result.metrics as Record<string, unknown>
  const loadFactors = result.load_factors as unknown[]
  const acceptedLoadFactors = solver.execution.accepted_load_factors as unknown[]
  const resumeCompletedPrefixCount = loadFactors.length - acceptedLoadFactors.length
  return {
    schema_version: 'structural-analysis-job-completion-evidence.v1',
    job_id: `job_${'a'.repeat(32)}`,
    request_hash: hash,
    checkpoint_hash: resumeCheckpointArtifactSha256,
    result_artifact_hash: resultArtifactSha256,
    validator_id: frame3dValidatorId,
    contract_pass: true,
    solver_truth_owner: 'structural_analysis_core',
    validation_report: {
      schema_version: 'bounded-frame3d-load-control-validation-report.v1',
      status: 'ready',
      contract_pass: true,
      result_schema_version: 'bounded-frame3d-load-control-result.v1',
      profile: 'bounded_multimember_frame3d_load_control_model_ir_api.v1',
      source_adapter_profile: 'model_ir_v2_to_multimember_corotational_frame3d_load_control.v1',
      solver_profile: 'dense_elastic_corotational_timoshenko_frame3d_load_control.v2',
      backend_role: 'cpu_reference',
      validator_id: frame3dValidatorId,
      result_hash: result.result_hash,
      result_artifact_sha256: resultArtifactSha256,
      job_request_artifact_sha256: hash,
      model_ir_content_hash: source.model_ir_content_hash,
      model_ir_semantic_hash: source.model_ir_semantic_hash,
      model_ir_provenance_hash: source.model_ir_provenance_hash,
      adapter_hash: source.adapter_hash,
      compiled_model_hash: source.model_hash,
      api_request_hash: source.request_hash,
      resume_contract_hash: checkpoint.resume_contract_hash,
      source_solver_receipt_hash: solver.source_receipt.result_hash,
      numerical_result_ir_hash: numerical.result_hash,
      resume_checkpoint_artifact_sha256: resumeCheckpointArtifactSha256,
      terminal_checkpoint_hash: terminalCheckpoint.checkpoint_hash,
      terminal_checkpoint_artifact_hash: checkpoint.artifact_hash,
      terminal_checkpoint_artifact_sha256: frame3dHashes.terminalArtifactSha256,
      recovery_hash: hash,
      full_node_equilibrium_hash: hash,
      equilibrium_scaling_hash: solver.full_node_equilibrium.equilibrium_scaling_hash,
      final_load_factor: metrics.final_load_factor,
      total_load_factor_count: loadFactors.length,
      resume_completed_prefix_count: resumeCompletedPrefixCount,
      accepted_suffix_step_count: acceptedLoadFactors.length,
      completed_prefix_count: metrics.completed_prefix_count,
      remaining_load_factor_count: 0,
      terminal_checkpoint_embedded: true,
      exact_result_manifest_replay: true,
      exact_source_solver_replay: true,
      exact_resume_checkpoint_binding: true,
      exact_terminal_checkpoint_replay: true,
      exact_numerical_result_ir_replay: true,
      exact_recovery_replay: true,
      residual_gate_pass: true,
      increment_gate_pass: true,
      line_search_pass: true,
      terminal_reassembled_equilibrium_pass: true,
      full_node_equilibrium_pass: true,
      unsupported_feature_count: 0,
      fallback_count: 0,
      regularization_count: 0,
      external_vv_level: 0,
      workbench_execution: false,
      public_product_promotion: false,
      release_eligible: false,
      claim_boundary: frame3dClaimBoundary,
    },
    claim_boundary: jobServiceClaimBoundary,
  }
}

async function loadPublishedHttpPair(
  resultBytes: Uint8Array,
  evidenceBytes: Uint8Array,
  declaredResultBytes: Uint8Array = resultBytes,
  progress: { completed_steps: number; total_steps: number } = { completed_steps: 4, total_steps: 4 },
  resumeCheckpointArtifactSha256: string | null = null,
) {
  const resultHash = digest(declaredResultBytes)
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded', revision: 2, attempt: 1,
    progress,
    checkpoint: resumeCheckpointArtifactSha256 === null ? null : {
      role: 'checkpoint',
      content_hash: resumeCheckpointArtifactSha256,
      byte_length: 1,
      media_type: 'application/json',
    },
    resume_contract_hash: resumeCheckpointArtifactSha256 === null
      ? null
      : frame3dHashes.resumeContract,
    result: {
      role: 'result',
      content_hash: resultHash,
      byte_length: declaredResultBytes.byteLength,
      media_type: 'application/vnd.structural-analysis.result+json',
    },
    evidence: {
      role: 'evidence',
      content_hash: digest(evidenceBytes),
      byte_length: evidenceBytes.byteLength,
      media_type: 'application/json',
    },
  }
  const statusBytes = new TextEncoder().encode(JSON.stringify(succeeded))
  const jobPath = `/v1/jobs/${succeeded.job_id}`
  const server = createServer((request, response) => {
    const path = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
    const match = path === jobPath
      ? { bytes: statusBytes, contentType: 'application/json' }
      : path === `${jobPath}/result`
        ? { bytes: resultBytes, contentType: 'application/vnd.structural-analysis.result+json' }
        : path === `${jobPath}/evidence`
          ? { bytes: evidenceBytes, contentType: 'application/json' }
          : null
    if (match === null) {
      response.writeHead(404).end()
      return
    }
    response.writeHead(200, {
      'cache-control': 'no-store',
      'content-length': String(match.bytes.byteLength),
      'content-type': match.contentType,
      'x-content-type-options': 'nosniff',
    })
    response.end(match.bytes)
  })
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  if (address === null || typeof address === 'string') {
    await new Promise<void>((resolve) => server.close(() => resolve()))
    throw new Error('published job HTTP fixture did not bind a TCP port')
  }
  try {
    return await loadWorkbenchJob(`http://127.0.0.1:${address.port}${jobPath}`)
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve())
    })
  }
}

test('Workbench verifies a succeeded job/result/evidence HTTP path before display', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))
  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
  expect(loaded.publishedResult).toMatchObject({
    kind: 'frame2d',
    adapterId: 'frame2d-unified-nonlinear-frame.v1',
    resultContract: 'unified-nonlinear-frame-result.v1',
    profile: 'corotational_one_bay_portal.v1',
    resultHash: result.result_hash,
  })
  if (loaded.publishedResult?.kind !== 'frame2d') throw new Error('expected Frame2D durable result')
  expect(loaded.publishedResult.engineeringResultIr.engineering_result_hash).toBe(result.source_result_hash)
  expect('node_displacements' in loaded).toBe(false)
})

test('registered Frame3D arm rejects a cross-wired Frame2D payload', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  result.schema_version = 'bounded-frame3d-load-control-result.v1'
  const resultBody = { ...result }
  delete resultBody.result_hash
  result.result_hash = canonicalHash(resultBody)
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))

  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded.status).toBe('invalid')
  expect(loaded.artifactStatus).toBe('invalid')
  expect(loaded.errors).toContain('published Frame3D load-control result identity is invalid')
  expect(loaded.publishedResult).toBeUndefined()
})

test('Frame2D adapter rejects a profile outside its exact identity', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  result.profile = 'bounded_frame3d_load_control_model_ir_api.v1'
  const resultBody = { ...result }
  delete resultBody.result_hash
  result.result_hash = canonicalHash(resultBody)
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))

  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded.status).toBe('invalid')
  expect(loaded.errors).toContain('published result contract is unsupported')
  expect(loaded.publishedResult).toBeUndefined()
})

test('Frame2D adapter rejects completion evidence from another validator identity', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidence = completionEvidence(result, resultHash)
  evidence.validator_id = 'structural_analysis.api.frame3d_load_control.validate_bounded_frame3d_load_control_result'
  const evidenceBytes = encoder.encode(JSON.stringify(evidence))

  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded.status).toBe('invalid')
  expect(loaded.errors).toContain('published completion evidence binding is invalid')
  expect(loaded.publishedResult).toBeUndefined()
})

test('Workbench blocks a tampered published result', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const declaredResult = encoder.encode(JSON.stringify(result))
  const tamperedResult = encoder.encode(JSON.stringify({ ...result, changed: true }))
  const resultHash = digest(declaredResult)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))
  const loaded = await loadPublishedHttpPair(tamperedResult, evidenceBytes, declaredResult)
  expect(loaded.status).toBe('invalid')
  expect(loaded.artifactStatus).toBe('invalid')
  expect(loaded.errors.join(' ')).toMatch(/result (byte length|sha256) mismatch/)
})

test('Workbench blocks a hash-valid result with a detached ResultIR mismatch', async () => {
  const encoder = new TextEncoder()
  const payload = publishedResult()
  payload.source_result_hash = `sha256:${'2'.repeat(64)}`
  const resultBody = { ...payload }
  delete resultBody.result_hash
  payload.result_hash = canonicalHash(resultBody)
  const resultBytes = encoder.encode(JSON.stringify(payload))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(payload, resultHash)))
  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded.status).toBe('invalid')
  expect(loaded.errors).toContain('published engineering ResultIR binding is invalid')
})

test('Workbench blocks a hash-valid pair when the core validation report is detached', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidence = completionEvidence(result, resultHash)
  ;(evidence.validation_report as Record<string, unknown>).result_hash = `sha256:${'9'.repeat(64)}`
  const evidenceBytes = encoder.encode(JSON.stringify(evidence))
  const loaded = await loadPublishedHttpPair(resultBytes, evidenceBytes)
  expect(loaded.status).toBe('invalid')
  expect(loaded.errors).toContain('published completion evidence binding is invalid')
})

async function loadFrame3DPair(
  mutateResult?: (result: Record<string, unknown>) => void,
  mutateEvidence?: (evidence: Record<string, unknown>) => void,
  resumeCheckpointArtifactSha256: string | null = null,
) {
  const encoder = new TextEncoder()
  const result = frame3dPublishedResult()
  mutateResult?.(result)
  const resultBytes = encoder.encode(JSON.stringify(result))
  const evidence = frame3dCompletionEvidence(
    result,
    digest(resultBytes),
    resumeCheckpointArtifactSha256,
  )
  mutateEvidence?.(evidence)
  const evidenceBytes = encoder.encode(JSON.stringify(evidence))
  const schedule = result.load_factors as unknown[]
  const metrics = result.metrics as Record<string, unknown>
  return loadPublishedHttpPair(
    resultBytes,
    evidenceBytes,
    resultBytes,
    {
      completed_steps: metrics.completed_prefix_count as number,
      total_steps: schedule.length,
    },
    resumeCheckpointArtifactSha256,
  )
}

function makeFrame3DTerminalAtPointEight(result: Record<string, unknown>): void {
  const factors = [0.25, 0.5, 0.8]
  const checkpointHashes = [
    `sha256:${'67'.repeat(32)}`,
    `sha256:${'78'.repeat(32)}`,
    `sha256:${'89'.repeat(32)}`,
  ]
  const solver = result.solver as Record<string, Record<string, unknown>>
  const sourceReceipt = solver.source_receipt
  const baseStep = (sourceReceipt.steps as Record<string, unknown>[])[0]
  sourceReceipt.steps = factors.map((factor, index) => {
    const step = structuredClone(baseStep)
    step.load_factor = factor
    const checkpoint = step.checkpoint as Record<string, unknown>
    checkpoint.load_factor = factor
    checkpoint.parent_checkpoint_hash = index === 0
      ? frame3dHashes.startCheckpoint
      : checkpointHashes[index - 1]
    checkpoint.checkpoint_hash = checkpointHashes[index]
    return step
  })
  solver.execution.requested_load_factors = factors
  solver.execution.accepted_load_factors = factors
  solver.execution.completed_prefix_count = 3
  result.load_factors = factors
  const checkpointArtifact = result.checkpoint_artifact as Record<string, Record<string, unknown>>
  checkpointArtifact.checkpoint.load_factor = 0.8
  checkpointArtifact.checkpoint.parent_checkpoint_hash = checkpointHashes[1]
  checkpointArtifact.checkpoint.checkpoint_hash = checkpointHashes[2]
  const numerical = result.numerical_result_ir as Record<string, unknown>
  numerical.load_factor = 0.8
  const bindings = numerical.bindings as Record<string, unknown>
  bindings.state_epoch = 3
  const metrics = result.metrics as Record<string, unknown>
  metrics.final_load_factor = 0.8
  metrics.accepted_step_count = 3
  metrics.numerical_result_state_epoch = 3
  metrics.completed_prefix_count = 3
}

function makeFrame3DResumedSuffix(result: Record<string, unknown>): void {
  const factors = [0.25, 0.5, 1]
  result.load_factors = factors
  const solver = result.solver as Record<string, Record<string, unknown>>
  solver.execution.requested_load_factors = factors
  solver.execution.accepted_load_factors = [1]
  solver.execution.start_checkpoint = frame3dCheckpoint(
    0.5,
    frame3dHashes.startCheckpoint,
    frame3dHashes.resumeCheckpointLogical,
  )
  solver.execution.completed_prefix_count = 3
  const sourceReceipt = solver.source_receipt
  sourceReceipt.start_checkpoint_hash = frame3dHashes.resumeCheckpointLogical
  const step = (sourceReceipt.steps as Record<string, unknown>[])[0]
  step.load_factor = 1
  const checkpoint = step.checkpoint as Record<string, unknown>
  checkpoint.load_factor = 1
  checkpoint.parent_checkpoint_hash = frame3dHashes.resumeCheckpointLogical
  const metrics = result.metrics as Record<string, unknown>
  metrics.final_load_factor = 1
  metrics.accepted_step_count = 1
  metrics.numerical_result_state_epoch = 1
  metrics.completed_prefix_count = 3
}

test('Frame3D registry verifies the exact bounded CPU candidate over loopback TCP', async () => {
  const loaded = await loadFrame3DPair()
  expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
  expect(loaded.publishedResult).toMatchObject({
    kind: 'frame3d-load-control',
    adapterId: 'frame3d-bounded-load-control.v1',
    resultContract: 'bounded-frame3d-load-control-result.v1',
    profile: 'bounded_multimember_frame3d_load_control_model_ir_api.v1',
    schedule: {
      completedPrefixCount: 1,
      remainingLoadFactorCount: 0,
      finalLoadFactor: 1,
    },
    numericalResultIr: {
      backendRole: 'cpu_reference',
      reactionAuthority: 'not_evaluated',
      memberForceAuthority: 'not_evaluated',
    },
    recovery: {
      reactionAuthority: 'bounded_candidate',
      memberForceAuthority: 'bounded_candidate',
    },
    authority: {
      workbenchExecution: false,
      externalVvLevel: 0,
      publicProductPromotion: false,
      releaseEligible: false,
    },
  })
  if (loaded.publishedResult?.kind !== 'frame3d-load-control') throw new Error('expected Frame3D durable result')
  expect(loaded.publishedResult).not.toHaveProperty('solver')
  expect(loaded.publishedResult).not.toHaveProperty('nodeDisplacements')
  expect(loaded.publishedResult).not.toHaveProperty('supportReactions')
  expect(loaded.publishedResult).not.toHaveProperty('memberRecovery')
  expect(loaded.publishedResult.checkpoint).not.toHaveProperty('displacement')
  expect(loaded.publishedResult.numericalResultIr).not.toHaveProperty('displacement')
})

test('Frame3D registry accepts a complete configured schedule ending below full load', async () => {
  const loaded = await loadFrame3DPair(makeFrame3DTerminalAtPointEight)
  expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
  if (loaded.publishedResult?.kind !== 'frame3d-load-control') throw new Error('expected Frame3D durable result')
  expect(loaded.publishedResult.schedule).toMatchObject({
    loadFactors: [0.25, 0.5, 0.8],
    finalLoadFactor: 0.8,
    resumeCompletedPrefixCount: 0,
    acceptedSuffixStepCount: 3,
    completedPrefixCount: 3,
    remainingLoadFactorCount: 0,
  })
})

test('Frame3D registry preserves resumed prefix and accepted suffix counts', async () => {
  const resumeArtifactSha256 = `sha256:${'56'.repeat(32)}`
  const loaded = await loadFrame3DPair(
    makeFrame3DResumedSuffix,
    undefined,
    resumeArtifactSha256,
  )
  expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
  if (loaded.publishedResult?.kind !== 'frame3d-load-control') throw new Error('expected Frame3D durable result')
  expect(loaded.publishedResult.schedule).toMatchObject({
    loadFactors: [0.25, 0.5, 1],
    finalLoadFactor: 1,
    resumeCompletedPrefixCount: 2,
    acceptedSuffixStepCount: 1,
    completedPrefixCount: 3,
    remainingLoadFactorCount: 0,
  })
})

test('integrity-unavailable Frame3D pair never exposes a published projection', async () => {
  const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined })
  try {
    const loaded = await loadFrame3DPair()
    expect(loaded).toMatchObject({
      status: 'ready',
      artifactStatus: 'integrity_unavailable',
      errors: [],
    })
    expect(loaded.publishedResult).toBeUndefined()
  } finally {
    if (cryptoDescriptor) Object.defineProperty(globalThis, 'crypto', cryptoDescriptor)
    else delete (globalThis as { crypto?: Crypto }).crypto
  }
})

const frame3dResultTampering: Array<[
  string,
  (result: Record<string, unknown>) => void,
]> = [
  ['partial terminal progress', (result) => {
    const metrics = result.metrics as Record<string, unknown>
    metrics.remaining_load_factor_count = 1
  }],
  ['count drift', (result) => {
    const metrics = result.metrics as Record<string, unknown>
    metrics.member_count = 3
  }],
  ['node order drift', (result) => {
    const rows = result.node_displacements as unknown[]
    result.node_displacements = [rows[1], rows[0], rows[2]]
  }],
  ['accepted schedule drift', (result) => {
    const solver = result.solver as Record<string, Record<string, unknown>>
    solver.execution.accepted_load_factors = [0.5]
  }],
  ['bounded advance control in a succeeded envelope', (result) => {
    const solver = result.solver as Record<string, Record<string, unknown>>
    solver.execution.maximum_new_steps = 1
  }],
  ['fallback promotion', (result) => {
    const metrics = result.metrics as Record<string, unknown>
    metrics.fallback_count = 1
  }],
  ['regularization promotion', (result) => {
    const solver = result.solver as Record<string, Record<string, unknown>>
    solver.source_receipt.regularization_used = true
  }],
  ['equilibrium tolerance failure', (result) => {
    const solver = result.solver as Record<string, Record<string, unknown>>
    solver.full_node_equilibrium.maximum_scaled_balance_residual = 2e-6
  }],
  ['checkpoint adapter drift', (result) => {
    const checkpoint = result.checkpoint_artifact as Record<string, unknown>
    checkpoint.adapter_hash = `sha256:${'2'.repeat(64)}`
  }],
  ['displacement data hash drift', (result) => {
    const numerical = result.numerical_result_ir as Record<string, Record<string, unknown>>
    numerical.displacement_artifact.data_hash = `sha256:${'2'.repeat(64)}`
  }],
  ['Numerical ResultIR reaction authority promotion', (result) => {
    const numerical = result.numerical_result_ir as Record<string, Record<string, unknown>>
    numerical.authority.reaction = 'authoritative'
  }],
  ['Numerical ResultIR member authority promotion', (result) => {
    const numerical = result.numerical_result_ir as Record<string, Record<string, unknown>>
    numerical.authority.member_force = 'authoritative'
  }],
  ['outer recovery authority promotion', (result) => {
    const authority = result.authority as Record<string, unknown>
    authority.solver_derived_reaction_recovery = 'authoritative'
  }],
  ['Workbench execution promotion', (result) => {
    const authority = result.authority as Record<string, unknown>
    authority.workbench_execution = true
  }],
  ['public product promotion', (result) => {
    const authority = result.authority as Record<string, unknown>
    authority.public_product_promotion = true
  }],
  ['release promotion', (result) => {
    const authority = result.authority as Record<string, unknown>
    authority.release_eligible = true
  }],
  ['profile drift', (result) => {
    result.profile = 'bounded_frame3d_direct_control_model_ir_api.v2'
  }],
]

for (const [label, mutate] of frame3dResultTampering) {
  test(`Frame3D loopback path rejects ${label}`, async () => {
    const loaded = await loadFrame3DPair(mutate)
    expect(loaded.status).toBe('invalid')
    expect(loaded.artifactStatus).toBe('invalid')
    expect(loaded.errors.join(' ')).toContain('published Frame3D')
    expect(loaded.publishedResult).toBeUndefined()
  })
}

const frame3dEvidenceTampering: Array<[
  string,
  (evidence: Record<string, unknown>) => void,
]> = [
  ['validator identity drift', (evidence) => {
    evidence.validator_id = 'structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result'
  }],
  ['validation report identity drift', (evidence) => {
    const report = evidence.validation_report as Record<string, unknown>
    report.backend_role = 'hip'
  }],
  ['validation report replay drift', (evidence) => {
    const report = evidence.validation_report as Record<string, unknown>
    report.exact_recovery_replay = false
  }],
  ['validation report hash drift', (evidence) => {
    const report = evidence.validation_report as Record<string, unknown>
    report.result_artifact_sha256 = `sha256:${'9'.repeat(64)}`
  }],
  ['validation report hidden field', (evidence) => {
    const report = evidence.validation_report as Record<string, unknown>
    report.release_override = true
  }],
  ['completion evidence hidden field', (evidence) => {
    evidence.release_override = true
  }],
]

for (const [label, mutate] of frame3dEvidenceTampering) {
  test(`Frame3D loopback path rejects ${label}`, async () => {
    const loaded = await loadFrame3DPair(undefined, mutate)
    expect(loaded.status).toBe('invalid')
    expect(loaded.artifactStatus).toBe('invalid')
    expect(loaded.errors).toContain('published completion evidence binding is invalid')
    expect(loaded.publishedResult).toBeUndefined()
  })
}
