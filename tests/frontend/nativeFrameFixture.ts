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
      load_combination_id: null,
      native_abi_version: 65541,
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
      nodal_load_only: false,
      uniform_member_load_initial_local: true,
      self_weight_standard_gravity: true,
      linear_load_combination_superposition: true,
      member_end_rotational_release: true,
      rigid_member_end_offset: true,
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
      load_combination_id: bindings.load_combination_id,
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
      'load_scope_nodal_uniform_self_weight_and_nested_linear_combinations',
      'no_nonuniform_or_member_point_load',
      'release_scope_rotational_rx_ry_rz_only',
      'released_coordinate_must_remain_globally_stable',
      'offset_scope_finite_global_rigid_end_arms',
      'no_translational_release',
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

export function nativeFrameReferenceFixture(result: Record<string, unknown>): Record<string, unknown> {
  const bindings = result.bindings as Record<string, unknown>
  const nodes = result.nodes as Array<Record<string, unknown>>
  const members = result.members as Array<Record<string, unknown>>
  return {
    schema_version: 'structural-external-linear-frame3d-reference.v1',
    reference_id: 'frame-alpha.LC1.synthetic-reference',
    source: {
      tool: 'synthetic_fixture',
      version: 'contract-v1',
      origin: 'synthetic_contract_fixture',
      export_sha256: fixedHash('d'),
    },
    bindings: {
      model_content_hash: bindings.model_content_hash,
      load_pattern_id: bindings.load_pattern_id,
      load_combination_id: bindings.load_combination_id,
    },
    axes: {
      node_displacement: 'global_ux_uy_uz_rx_ry_rz',
      node_reaction: 'global_fx_fy_fz_mx_my_mz',
      member_end_force: 'member_local_fx_fy_fz_mx_my_mz_i_then_j',
      sign_convention: 'native_result_ir_compatible',
    },
    units: { translation: 'mm', rotation: 'rad', force: 'kN', moment: 'kN*m' },
    nodes: nodes.map((node) => ({
      node_id: node.node_id,
      displacement: (node.displacement_m_rad as number[]).map((value, index) => index < 3 ? value * 1e3 : value),
      reaction: (node.reaction_n_nm as number[]).map((value) => value / 1e3),
    })),
    members: members.map((member) => ({
      member_id: member.member_id,
      end_i_force: (member.end_i_force_n_nm as number[]).map((value) => value / 1e3),
      end_j_force: (member.end_j_force_n_nm as number[]).map((value) => value / 1e3),
    })),
    claim_boundary: 'operator_declared_mapping_and_units_not_independent_validation_or_release_authority',
  }
}

export function nativeFrameComparisonFixture(
  result: Record<string, unknown>,
  reference: Record<string, unknown>,
): Record<string, unknown> {
  const resultNodes = result.nodes as Array<Record<string, unknown>>
  const resultMembers = result.members as Array<Record<string, unknown>>
  const referenceNodes = new Map((reference.nodes as Array<Record<string, unknown>>).map((row) => [row.node_id, row]))
  const referenceMembers = new Map((reference.members as Array<Record<string, unknown>>).map((row) => [row.member_id, row]))
  const displacementComponents = ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ']
  const forceComponents = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ']
  const rows: Array<Record<string, unknown>> = []
  const add = (
    quantity: 'displacement' | 'reaction' | 'member_end_force',
    entityId: unknown,
    component: string,
    unit: string,
    nativeValue: number,
    referenceValue: number,
  ) => {
    const tolerance = quantity === 'member_end_force' ? 0.01 : 0.005
    const floor = quantity === 'displacement' ? 1e-12 : 1e-6
    const absoluteDifference = Math.abs(nativeValue - referenceValue)
    const scaledDifference = absoluteDifference / Math.max(Math.abs(nativeValue), Math.abs(referenceValue), floor)
    rows.push({
      quantity, entity_id: entityId, component, unit, native_value: nativeValue,
      reference_value: referenceValue, absolute_difference: absoluteDifference,
      scaled_difference: scaledDifference, tolerance, passed: scaledDifference <= tolerance,
    })
  }
  for (const node of resultNodes) {
    const target = referenceNodes.get(node.node_id)!
    ;(node.displacement_m_rad as number[]).forEach((value, index) => add(
      'displacement', node.node_id, displacementComponents[index], index < 3 ? 'm' : 'rad', value,
      (target.displacement as number[])[index] * (index < 3 ? 1e-3 : 1),
    ))
    ;(node.reaction_n_nm as number[]).forEach((value, index) => add(
      'reaction', node.node_id, forceComponents[index], index < 3 ? 'N' : 'N*m', value,
      (target.reaction as number[])[index] * 1e3,
    ))
  }
  for (const member of resultMembers) {
    const target = referenceMembers.get(member.member_id)!
    for (const [end, nativeValues, referenceValues] of [
      ['I', member.end_i_force_n_nm, target.end_i_force],
      ['J', member.end_j_force_n_nm, target.end_j_force],
    ] as const) {
      ;(nativeValues as number[]).forEach((value, index) => add(
        'member_end_force', member.member_id, `${forceComponents[index]}_${end}`,
        index < 3 ? 'N' : 'N*m', value, (referenceValues as number[])[index] * 1e3,
      ))
    }
  }
  const families = ([
    ['displacement', 0.005], ['reaction', 0.005], ['member_end_force', 0.01],
  ] as const).map(([quantity, tolerance]) => {
    const selected = rows.filter((row) => row.quantity === quantity)
    let worst = selected[0]
    for (const row of selected.slice(1)) {
      if ((row.scaled_difference as number) > (worst.scaled_difference as number)) worst = row
    }
    const failing = selected.filter((row) => row.passed === false).length
    return {
      quantity, row_count: selected.length, failing_row_count: failing,
      max_scaled_difference: worst.scaled_difference, tolerance,
      worst_entity_id: worst.entity_id, worst_component: worst.component, passed: failing === 0,
    }
  })
  const failing = rows.filter((row) => row.passed === false).length
  const body = {
    schema_version: 'structural-native-linear-frame3d-comparison-ir.v1',
    comparison_id: 'frame-alpha.LC1.synthetic-comparison',
    comparison_hash: fixedHash('0'),
    comparison_kind: 'bounded_native_to_external_linear_frame3d',
    source_result: {
      schema_version: result.schema_version,
      result_id: result.result_id,
      result_hash: result.result_hash,
      model_content_hash: (result.bindings as Record<string, unknown>).model_content_hash,
    },
    source_reference: {
      schema_version: reference.schema_version,
      reference_id: reference.reference_id,
      reference_hash: fixtureHash(reference),
      ...(reference.source as Record<string, unknown>),
    },
    tolerance_profile: {
      profile: 'frame_alpha_cross_code.v1',
      scaled_difference: 'abs(native-reference)/max(abs(native),abs(reference),absolute_floor)',
      displacement_relative: 0.005,
      reaction_relative: 0.005,
      member_end_force_relative: 0.01,
      translation_rotation_absolute_floor: 1e-12,
      force_moment_absolute_floor: 1e-6,
    },
    summary: { row_count: rows.length, failing_row_count: failing, passed: failing === 0, families },
    rows,
    authority: {
      source_result: 'bounded_candidate',
      reference_input: 'operator_declared_or_synthetic_fixture',
      comparison: 'bounded_cross_code_evaluation',
      external_validation: 'not_established',
      engineering_design: 'not_authoritative',
      release_readiness: 'not_authoritative',
    },
    claim_boundary: 'strict_mapping_unit_normalization_and_tolerance_evaluation_not_external_validation_design_or_release_authority',
  }
  return { ...body, comparison_hash: fixtureHash(body) }
}

export function artifactBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value))
}
