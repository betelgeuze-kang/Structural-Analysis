// Synthetic history contract fixture only; no solver or engineering evidence.
import { designComparisonFixture, designHash } from './designComparisonFixture'

export function designHistoryComparisonFixture(): Record<string, any> {
  const report = designComparisonFixture()
  report.schema_version = report.identity.schema_version = 'public-rc-fiber-design-comparison.v2'
  report.identity.history_limits = { maximum_translation_m: 0.002, maximum_absolute_fiber_strain: 0.0002 }
  report.claims.limits_scope = 'terminal_and_committed_history_translation_and_fiber_strain'
  report.claims.all_requested_history_verified = true
  report.selection.criterion = 'minimum_scoped_material_estimate_with_verified_terminal_and_history_limits'
  report.selection.candidate_id = 'baseline'
  report.selection.eligible_count = 1
  report.rows.forEach((row: any, candidateIndex: number) => {
    row.result.node_displacements.forEach((node: any) => Object.assign(node, { RX_rad: 0, RY_rad: 0, RZ_rad: 0 }))
    Object.assign(row.result.fiber_results[0], {
      member_id: 'M1', integration_point_index: 0, fiber_index: 0, fiber_id: 'steel-top-0',
      material_kind: 'steel', y_m: 0.45, area_m2: 0.01, stress_MPa: 20, dissipated_energy_density_MJ_per_m3: 0,
    })
    Object.assign(row.result.checkpoint, { root_state_hash: designHash('a'), terminal_state_hash: designHash('b') })
    Object.assign(row.result.contract_bindings, {
      source_result_adapter_hash: designHash('c'), numerical_result_hash: designHash('d'),
      problem_contract_hash: designHash('e'), execution_topology_plan_hash: designHash('f'),
      terminal_kinematic_state_hash: designHash('1'), terminal_material_state_bundle_hash: designHash('2'),
    })
    const bindings = {
      source_result_adapter_hash: designHash('c'), source_binding_hash: designHash('3'), source_numerical_result_hash: designHash('d'),
      problem_contract_hash: designHash('e'), model_ir_content_hash: row.model_checksum, execution_topology_plan_hash: designHash('f'),
      physical_equation_scaling_binding_hash: designHash('4'), execution_state_binding_hash: designHash('5'),
      checkpoint_chain_hash: designHash('9'), root_checkpoint_state_hash: designHash('a'), terminal_checkpoint_state_hash: designHash('b'),
      kinematic_state_chain_hash: designHash('6'), material_state_projection_chain_hash: designHash('7'), terminal_receipt_hash: designHash('8'),
    }
    const peakTranslation = candidateIndex ? 0.003 : 0.0015
    const peakStrain = candidateIndex ? 0.0003 : 0.00015
    const envelope = (epoch: number, nodes: any[], fibers: any[]) => ({
      maximum_translation_m: nodes[1].UY_m,
      maximum_absolute_fiber_strain: Math.abs(fibers[0].strain),
      governing_translation: { epoch, ...nodes[1], translation_m: nodes[1].UY_m },
      governing_fiber_strain: { epoch, ...fibers[0], absolute_strain: Math.abs(fibers[0].strain) },
    })
    const steps = [1, 2].map(epoch => {
      const nodes = structuredClone(row.result.node_displacements)
      const fibers = structuredClone(row.result.fiber_results)
      if (epoch === 1) { nodes[1].UY_m = peakTranslation; fibers[0].strain = -peakStrain }
      return {
        epoch, step_index: epoch, target_load_factor: epoch / 2,
        bindings: {
          checkpoint_state_hash: epoch === 1 ? designHash('0') : designHash('b'),
          parent_checkpoint_state_hash: epoch === 1 ? designHash('a') : designHash('0'),
          kinematic_state_hash: designHash('1'), material_projection_receipt_hash: designHash('3'),
          material_state_bundle_hash: designHash('2'), execution_epoch_binding_hash: designHash('4'),
          step_receipt_hash: designHash(epoch === 1 ? '5' : '6'), source_solution_data_hash: designHash('7'),
        },
        recovery_hash: designHash('a'), array_bundle_hash: designHash('b'), orders: {}, metrics: {},
        recovery_arrays: { fiber_strain: fibers.map((fiber: any) => fiber.strain) },
        recovery_array_descriptors: [{ name: 'fiber_strain' }], displacement_array_descriptor: { name: 'canonical_displacement_si' },
        displacement_canonical_si: nodes.flatMap((node: any) => ['UX_m', 'UY_m', 'UZ_m', 'RX_rad', 'RY_rad', 'RZ_rad'].map(key => node[key])),
        node_displacements: nodes, fiber_results: fibers, envelope: envelope(epoch, nodes, fibers),
      }
    })
    const sourceTerminalReceipt = {
      terminal_receipt_hash: bindings.terminal_receipt_hash,
      bindings: { ...bindings },
      terminal: { accepted_step_count: 2, terminal_epoch: 2, terminal_load_factor: 1, converged: true, fallback_count: 0, regularization_count: 0 },
      step_receipts: steps.map(step => ({
        step_receipt_hash: step.bindings.step_receipt_hash,
        coordinates: { epoch: step.epoch, step_index: step.epoch, target_load_factor: step.target_load_factor },
        bindings: {
          parent_checkpoint_state_hash: step.bindings.parent_checkpoint_state_hash,
          accepted_checkpoint_state_hash: step.bindings.checkpoint_state_hash,
          committed_kinematic_state_hash: step.bindings.kinematic_state_hash,
          committed_material_state_bundle_hash: step.bindings.material_state_bundle_hash,
        },
        binary_identities: { source_solution_data_hash: step.bindings.source_solution_data_hash },
      })),
    }
    const history = {
      schema_version: 'stateful-fiber-frame2d-nonlinear-engineering-history.v1', history_hash: designHash('c'), status: 'ready', contract_pass: true,
      bindings, source_terminal_receipt: sourceTerminalReceipt,
      scope: {
        committed_epochs_only: true, genesis_included: false, complete_monotonic_static_load_path: true,
        between_step_extrema_verified: false, cyclic_or_dynamic_history_verified: false, constitutive_law_independently_verified: false,
        engineering_design_verified: false, code_compliance_verified: false, production_promotion_eligible: false,
      },
      authority: structuredClone(row.result.authority), epoch_count: 2, terminal_epoch: 2, terminal_load_factor: 1,
      steps, envelope: structuredClone(steps[0].envelope),
    }
    Object.assign(row, {
      full_history_verification_pass: true,
      history_limit_status: candidateIndex ? 'fail' : 'pass',
      violated_history_limits: candidateIndex ? ['history_maximum_translation_m', 'history_maximum_absolute_fiber_strain'] : [],
      history_failure: null,
      response_history: {
        schema_version: 'public-rc-fiber-frame-response-history.v1', report_hash: designHash('d'), status: 'ready', contract_pass: true,
        source_result_hash: row.result.result_hash, canonical_model_checksum: row.model_checksum, history_hash: history.history_hash, history,
      },
    })
    Object.assign(row.performance, { history_maximum_translation_m: peakTranslation, history_maximum_absolute_fiber_strain: peakStrain })
  })
  return report
}

export function removeVerifiedHistory(report: Record<string, any>, index: number): void {
  const row = report.rows[index]
  Object.assign(row, {
    full_history_verification_pass: false, history_limit_status: 'unavailable', violated_history_limits: [],
    response_history: null, history_failure: { kind: 'history_recovery_blocked' },
  })
  delete row.performance.history_maximum_translation_m
  delete row.performance.history_maximum_absolute_fiber_strain
  report.status = 'partial'
  report.claims.all_requested_history_verified = false
  report.selection.eligible_count = report.rows.filter((value: any) => value.full_history_verification_pass && value.history_limit_status === 'pass').length
  if (index === 0) {
    report.selection.candidate_id = null
    report.selection.reason = 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes'
  }
}
