import { compileBuildingLoadRevision, prepareBuildingLoadRevision, serializeBuildingLoadRevisionDraft } from '../../src/workbench-v2/model/buildingLoadRevision'
import { buildingFixtureBytes, buildingMemberFixture } from './buildingMemberFixture'
import { fixtureHash } from './nativeFrameFixture'

/** Authored software contract data only: these values are not produced by a solver. */
export async function buildingRevisionResultFixture(options: { combination?: boolean } = {}) {
  const fixture = await buildingMemberFixture({ combination: options.combination ?? true })
  // Retain an explicitly unconnected physical member as well as the mapped beam.
  fixture.mapping.members.push({ member_id: 'PHYSICAL_C12', label: 'Unmapped column C12', storey_id: 'STOREY_1', segments: [], review_locations: [] })
  const draft = await prepareBuildingLoadRevision(fixture.modelBytes, fixture.resultBytes, buildingFixtureBytes(fixture.mapping), 'synthetic.load.revision')
  const loads = structuredClone(fixture.model.load_patterns[0].nodal_loads)
  loads[0].components_si.FY = -7654.25
  draft.patches = [{ pattern_id: 'LC1', self_weight: [0, 0, -1], nodal_loads: loads }]
  const draftBytes = serializeBuildingLoadRevisionDraft(draft)
  const compiled = await compileBuildingLoadRevision(draft)
  // Independently authored target-result fixture. No parent result forces, nodal
  // response or gate measurements are reused or represented as an execution.
  const body = {
    schema_version: 'structural-native-linear-frame3d-result-ir.v1',
    result_id: 'synthetic.revision.result',
    result_kind: 'linear_static_frame3d',
    authority_profile: 'bounded_native_cpu_result_candidate.v1',
    promotion_basis: 'native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1',
    bindings: { model_id: String(compiled.modelIr.model_id), ...compiled.targetIdentity,
      load_pattern_id: options.combination === false ? 'LC1' : null,
      load_combination_id: options.combination === false ? null : 'COMB1', native_abi_version: 65541 },
    solver: { formulation: 'linear_timoshenko_frame3d', backend: 'cpu_reference_dense', residual_sign: 'internal_minus_external', unit_profile: 'node_m_rad_force_n_nm_member_local_n_nm.v1' },
    gates: {
      native_residual_gate_passed: true, free_residual_scaled_linf: 7e-15, free_residual_scaled_linf_tolerance: 1e-9,
      global_force_balance_scaled_linf: 8e-16, global_force_balance_scaled_linf_tolerance: 1e-9,
      global_moment_balance_scaled_linf: 9e-16, global_moment_balance_scaled_linf_tolerance: 1e-9,
      global_resultant_gate_passed: true, independent_recovery_replay_passed: true,
      member_force_replay_scaled_linf: 6e-16, member_force_replay_scaled_linf_tolerance: 1e-9,
      zero_prescribed_displacement_gate_passed: true, fallback_count: 0, regularization_count: 0,
    },
    nodes: [
      { node_id: 'N1', displacement_m_rad: [0, 0, 0, 0, 0, 0], reaction_n_nm: [-111.125, 222.25, -333.5, 444.75, -555.875, 666.0625] },
      { node_id: 'N2', displacement_m_rad: [0.0001, -0.0002, 0.0003, -0.0004, 0.0005, -0.0006], reaction_n_nm: [0, 0, 0, 0, 0, 0] },
      { node_id: 'N3', displacement_m_rad: [0.0011, -0.0012, 0.0013, -0.0014, 0.0015, -0.0016], reaction_n_nm: [0, 0, 0, 0, 0, 0] },
    ],
    members: [
      { member_id: 'E2', end_i_force_n_nm: [-701.25, 702.5, -703.75, 704.125, -705.25, 706.5], end_j_force_n_nm: [711.25, -712.5, 713.75, -714.125, 715.25, -716.5] },
      { member_id: 'E1', end_i_force_n_nm: [-801.25, 802.5, -803.75, 804.125, -805.25, 806.5], end_j_force_n_nm: [811.25, -812.5, 813.75, -814.125, 815.25, -816.5] },
    ],
    authority: { numerical_state: 'bounded_candidate', convergence: 'bounded_candidate', displacement: 'bounded_candidate', reaction: 'bounded_candidate', member_force: 'bounded_candidate', engineering_design: 'not_authoritative', code_compliance: 'not_authoritative', release_readiness: 'not_authoritative', commercial_use: 'not_authoritative' },
    claim_boundary: {
      bounded_linear_static_timoshenko_frame3d: true, cpu_only: true, zero_prescribed_displacement_only: true, nodal_load_only: false,
      uniform_member_load_initial_local: true, self_weight_standard_gravity: true, linear_load_combination_superposition: true,
      member_end_rotational_release: true, rigid_member_end_offset: true, reaction_from_global_residual: true,
      member_force_from_native_local_recovery: true, independent_recovery_replay: true,
      cpu_hip_parity_established: false, external_validation_established: false, workbench_e2e: false, release_readiness: false, commercial_claim: false,
    },
  }
  const result = { ...body, result_hash: fixtureHash(body) }
  return { fixture, draft, draftBytes, compiled, result, resultBytes: buildingFixtureBytes(result) }
}
