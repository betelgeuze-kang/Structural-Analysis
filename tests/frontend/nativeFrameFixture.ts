import { createHash } from 'node:crypto'
import { canonicalNativeJson } from '../../src/workbench-v2/model/nativeFrameProvider'

export const fixedHash = (character: string): string => `sha256:${character.repeat(64)}`

export function fixtureHash(value: unknown): string {
  return `sha256:${createHash('sha256').update(canonicalNativeJson(value)).digest('hex')}`
}

export function nativeFrameResultFixture(): Record<string, unknown> {
  const body = {
    schema_version: 'structural-native-linear-frame3d-result-ir.v1',
    result_id: 'frame-alpha.LC1',
    result_kind: 'linear_static_frame3d',
    authority_profile: 'bounded_native_cpu_result_candidate.v1',
    promotion_basis: 'native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1',
    bindings: {
      model_id: 'frame-alpha',
      model_content_hash: fixedHash('a'),
      model_semantic_hash: fixedHash('b'),
      model_provenance_hash: fixedHash('c'),
      load_pattern_id: 'LC1',
      native_abi_version: 65538,
    },
    solver: {
      formulation: 'linear_timoshenko_frame3d',
      backend: 'cpu_reference_dense',
      residual_sign: 'internal_minus_external',
      unit_profile: 'node_m_rad_force_n_nm_member_local_n_nm.v1',
    },
    gates: {
      native_residual_gate_passed: true,
      free_residual_scaled_linf: 2e-15,
      free_residual_scaled_linf_tolerance: 1e-9,
      global_force_balance_scaled_linf: 3e-16,
      global_force_balance_scaled_linf_tolerance: 1e-9,
      global_moment_balance_scaled_linf: 4e-16,
      global_moment_balance_scaled_linf_tolerance: 1e-9,
      global_resultant_gate_passed: true,
      independent_recovery_replay_passed: true,
      member_force_replay_scaled_linf: 5e-16,
      member_force_replay_scaled_linf_tolerance: 1e-9,
      zero_prescribed_displacement_gate_passed: true,
      fallback_count: 0,
      regularization_count: 0,
    },
    nodes: [
      {
        node_id: 'N1',
        displacement_m_rad: [0, 0, 0, 0, 0, 0],
        reaction_n_nm: [-100000, 0, 0, 0, 0, 0],
      },
      {
        node_id: 'N2',
        displacement_m_rad: [5e-5, 0, 0, 0, 0, 0],
        reaction_n_nm: [0, 0, 0, 0, 0, 0],
      },
    ],
    members: [{
      member_id: 'E1',
      end_i_force_n_nm: [-100000, 0, 0, 0, 0, 0],
      end_j_force_n_nm: [100000, 0, 0, 0, 0, 0],
    }],
    authority: {
      numerical_state: 'bounded_candidate',
      convergence: 'bounded_candidate',
      displacement: 'bounded_candidate',
      reaction: 'bounded_candidate',
      member_force: 'bounded_candidate',
      engineering_design: 'not_authoritative',
      code_compliance: 'not_authoritative',
      release_readiness: 'not_authoritative',
      commercial_use: 'not_authoritative',
    },
    claim_boundary: {
      bounded_linear_static_timoshenko_frame3d: true,
      cpu_only: true,
      zero_prescribed_displacement_only: true,
      nodal_load_only: true,
      reaction_from_global_residual: true,
      member_force_from_native_local_recovery: true,
      independent_recovery_replay: true,
      cpu_hip_parity_established: false,
      external_validation_established: false,
      workbench_e2e: false,
      release_readiness: false,
      commercial_claim: false,
    },
  }
  return { ...body, result_hash: fixtureHash(body) }
}

export function nativeFrameReportFixture(result: Record<string, unknown>): Record<string, unknown> {
  const bindings = result.bindings as Record<string, unknown>
  const solver = result.solver as Record<string, unknown>
  const nodes = result.nodes as unknown[]
  const members = result.members as unknown[]
  const body = {
    schema_version: 'structural-native-linear-frame3d-report-ir.v1',
    report_id: 'frame-alpha.LC1.report',
    report_kind: 'linear_frame3d_analysis_summary',
    source_result: {
      schema_version: result.schema_version,
      result_id: result.result_id,
      result_hash: result.result_hash,
    },
    summary: {
      model_id: bindings.model_id,
      load_pattern_id: bindings.load_pattern_id,
      formulation: solver.formulation,
      backend: solver.backend,
      node_count: nodes.length,
      member_count: members.length,
    },
    gates: result.gates,
    extrema: [
      { quantity: 'displacement', entity_id: 'N2', component: 'UX', signed_value: 5e-5, absolute_value: 5e-5, unit: 'm' },
      { quantity: 'reaction', entity_id: 'N1', component: 'FX', signed_value: -100000, absolute_value: 100000, unit: 'N' },
      { quantity: 'member_end_force', entity_id: 'E1', component: 'FX_I', signed_value: -100000, absolute_value: 100000, unit: 'N' },
    ],
    limitations: [
      'cpu_only_no_hip_parity',
      'nodal_load_only',
      'no_distributed_member_load',
      'no_release_or_offset',
      'no_nonzero_prescribed_displacement',
      'no_workbench_e2e',
      'no_design_or_release_authority',
    ],
    authority: {
      source_result: 'bounded_candidate',
      presentation: 'deterministic_projection',
      comparison: 'not_evaluated',
      engineering_design: 'not_authoritative',
      release_readiness: 'not_authoritative',
    },
    claim_boundary: 'deterministic_presentation_of_bounded_candidate_result_not_comparison_design_or_release_authority',
  }
  return { ...body, report_hash: fixtureHash(body) }
}

export function artifactBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value))
}
