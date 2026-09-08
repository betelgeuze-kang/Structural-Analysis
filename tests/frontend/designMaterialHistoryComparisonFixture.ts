// Synthetic transport/consumer contracts only, never solver or material V&V evidence.
import { designHash } from './designComparisonFixture'
import { designHistoryComparisonFixture } from './designHistoryComparisonFixture'

const definitions: Record<string, Record<string, [string, string]>> = {
  steel: { accumulated_plastic_strain: ['1', 'accumulated_plastic_memory'], plastic_strain: ['1', 'signed_plastic_strain'], backstress_mpa: ['MPa', 'signed_backstress'], dissipated_energy_density_mj_per_m3: ['MJ/m^3', 'cumulative_density'] },
  concrete: { tensile_history_strain: ['1', 'maximum_tensile_history'], compressive_history_strain: ['1', 'maximum_compressive_history_magnitude'], tensile_damage: ['1', 'damage_memory'], compressive_damage: ['1', 'damage_memory'], dissipated_energy_density_mj_per_m3: ['MJ/m^3', 'cumulative_density'] },
}

export function designMaterialHistoryComparisonFixture(): Record<string, any> {
  const report = designHistoryComparisonFixture()
  report.schema_version = report.identity.schema_version = 'public-rc-fiber-design-comparison.v3'
  report.identity.history_limits = { maximum_translation_m: 0.01, maximum_absolute_fiber_strain: 0.01 }
  report.identity.material_history_limits = { maximum_steel_accumulated_plastic_strain: 0.002, maximum_concrete_tensile_damage: 0.2, maximum_concrete_compressive_damage: 0.1 }
  Object.assign(report.claims, { limits_scope: 'terminal_and_committed_history_translation_fiber_strain_and_material_memory', all_requested_material_history_verified: true, material_history_limits_are_caller_declared: true, material_memory_is_current_yield_event: false })
  report.selection.criterion = 'minimum_scoped_material_estimate_with_verified_terminal_history_and_material_history_limits'
  report.rows.forEach((row: any, index: number) => {
    row.result.input_checksum = designHash('6')
    row.result.checkpoint.artifact_byte_length = 2048
    const response = row.response_history; const history = response.history
    const peakSteel = index ? 0.003 : 0.001; const peakTension = index ? 0.25 : 0.1; const peakCompression = 0.05
    let prior: Record<string, Record<string, number>> | null = null
    const states = [0, 1, 2].map(epoch => {
      const factor = epoch / 2
      const values: Record<string, Record<string, number>> = {
        steel: { accumulated_plastic_strain: peakSteel * factor, plastic_strain: -peakSteel * factor, backstress_mpa: -5000 * peakSteel * factor, dissipated_energy_density_mj_per_m3: 250 * peakSteel * factor },
        concrete: { tensile_history_strain: 0.001 * factor, compressive_history_strain: 0.002 * factor, tensile_damage: peakTension * factor, compressive_damage: peakCompression * factor, dissipated_energy_density_mj_per_m3: 0.1 * factor },
      }
      if (epoch === 0) for (const fields of Object.values(values)) for (const key of Object.keys(fields)) fields[key] = 0
      const materials = Object.fromEntries(Object.entries(definitions).map(([kind, fields]) => [kind, {
        point_count: 1,
        fields: Object.fromEntries(Object.entries(fields).map(([name, [unit, interpretation]]) => {
          const value = values[kind][name]; const previous = prior?.[kind][name]
          return [name, { unit, interpretation, minimum: value, maximum: value, maximum_absolute: Math.abs(value), positive_value_point_count: Number(value > 0), changed_from_parent_point_count: previous === undefined ? null : Number(value !== previous), increased_from_parent_point_count: previous === undefined ? null : Number(value > previous), decreased_from_parent_point_count: previous === undefined ? null : Number(value < previous), parent_comparison_reason: epoch === 0 ? 'genesis_has_no_parent' : null }]
        })),
      }]))
      prior = values
      const step = epoch ? history.steps[epoch - 1] : null
      const total = epoch ? 0.02 * epoch : null
      if (step) {
        const steel = step.fiber_results[0]
        steel.dissipated_energy_density_MJ_per_m3 = values.steel.dissipated_energy_density_mj_per_m3
        const concrete = { ...steel, fiber_index: 1, fiber_id: 'concrete-0', material_kind: 'concrete', strain: 0, stress_MPa: 0, dissipated_energy_density_MJ_per_m3: values.concrete.dissipated_energy_density_mj_per_m3 }
        step.fiber_results.push(concrete)
        step.recovery_arrays.fiber_strain.push(0)
        step.metrics.total_dissipated_energy_mj = total
        step.envelope.governing_fiber_strain = { epoch, ...steel, absolute_strain: Math.abs(steel.strain) }
      }
      return { epoch, step_index: epoch, load_factor: factor, checkpoint_state_hash: step ? step.bindings.checkpoint_state_hash : history.bindings.root_checkpoint_state_hash, parent_checkpoint_state_hash: step ? step.bindings.parent_checkpoint_state_hash : null, engineering_recovery_hash: step?.recovery_hash ?? null, total_dissipated_energy_mj: total, engineering_recovery_reason: epoch ? null : 'genesis_has_no_engineering_recovery', material_point_count: 2, materials }
    })
    row.result.fiber_results = structuredClone(history.steps[1].fiber_results)
    history.envelope = structuredClone(history.steps[0].envelope)
    Object.assign(row, {
      full_history_verification_pass: true, history_limit_status: 'pass', violated_history_limits: [],
      full_material_history_verification_pass: true, material_history_limit_status: index ? 'fail' : 'pass',
      violated_material_history_limits: index ? ['history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage'] : [], material_history_failure: null,
      constitutive_history: {
        schema_version: 'public-rc-fiber-frame-constitutive-history.v1', status: 'ready', contract_pass: true, report_hash: designHash('4'),
        bindings: { source_result_hash: row.result.result_hash, canonical_model_checksum: row.model_checksum, input_checksum: row.result.input_checksum, problem_contract_hash: row.result.contract_bindings.problem_contract_hash, checkpoint_chain_hash: row.result.checkpoint.chain_hash, checkpoint_artifact_hash: row.result.checkpoint.artifact_hash, checkpoint_artifact_byte_length: row.result.checkpoint.artifact_byte_length, response_history_report_hash: response.report_hash, engineering_history_hash: history.history_hash },
        accepted_epoch_count: 2, states,
        scope: { validation: 'existing_full_public_response_history_accessor_then_retained_material_memory_aggregation', material_point: 'member_integration_point_modeled_fiber_not_individual_bar', state_value_counts: 'strictly_positive_native_values_not_current_step_yield_events', transition_counts: 'exact_comparison_with_immediately_preceding_accepted_state', total_energy: 'original_per_epoch_engineering_recovery_MJ_not_density_or_epoch_sum' },
        claim_boundary: { independent_physical_validation: false, cyclic_loading_verified: false, production_promotion_eligible: false, state_changes_identify_solver_yield_events: false, density_sum_is_total_energy: false },
      },
    })
    Object.assign(row.performance, { history_maximum_steel_accumulated_plastic_strain: peakSteel, history_maximum_concrete_tensile_damage: peakTension, history_maximum_concrete_compressive_damage: peakCompression })
  })
  return report
}

export function removeVerifiedMaterialHistory(report: Record<string, any>, index: number): void {
  const row = report.rows[index]
  Object.assign(row, { constitutive_history: null, full_material_history_verification_pass: false, material_history_limit_status: 'unavailable', violated_material_history_limits: [], material_history_failure: { kind: 'material_history_recovery_failed', exception_type: 'ValueError' } })
  for (const key of ['history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage', 'history_maximum_concrete_compressive_damage']) delete row.performance[key]
  report.status = 'partial'; report.claims.all_requested_material_history_verified = false
  report.selection.eligible_count = report.rows.filter((item: any) => item.full_material_history_verification_pass && item.material_history_limit_status === 'pass').length
  if (index === 0) { report.selection.candidate_id = null; report.selection.reason = 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes' }
}
