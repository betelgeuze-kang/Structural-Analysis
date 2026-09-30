// Synthetic contract fixture only; not solver evidence or a priced engineering design.
export const designHash = (character: string): string => `sha256:${character.repeat(64)}`
const scope = 'gross_concrete_and_straight_authored_longitudinal_rebar.v1'
const profile = 'planar_serial_cantilever_explicit_rectangular_rc.v1'
const excluded = ['transverse_reinforcement', 'laps_anchorage_hooks', 'waste', 'formwork', 'labor', 'fabrication', 'transport', 'tax']

export function designComparisonFixture(): Record<string, any> {
  const config = { load_steps: 2, maximum_iterations: 40, residual_tolerance: 1e-10, increment_tolerance_m: 1e-12 }
  const model = (width: number) => ({
    schema_version: 'structural-analysis-canonical-model.v1',
    units: { length: 'm', force: 'kN' },
    nodes: [{ id: 'N1', coordinates: [0, 0, 0] }, { id: 'N2', coordinates: [1, 0, 0] }],
    elements: [{ id: 'M1', nodes: ['N1', 'N2'], section: 'RC1', type: 'stateful_rc_fiber_frame2d' }],
    sections: [{ id: 'RC1', width_m: width, depth_m: 1, cover_m: 0.05, top_bar_count: 1, bottom_bar_count: 1, bar_area_m2: 0.01 }],
  })
  const row = (id: string, width: number, modelHash: string, quantityHash: string, resultHash: string) => ({
    candidate_id: id, model_checksum: modelHash, canonical_model: model(width), status: 'ready',
    full_reference_verification_pass: true, solver_executed: true, reference_and_quantity_wall_ns: 100,
    result: {
      schema_version: 'public-rc-fiber-frame-result.v1', result_hash: resultHash, canonical_model_checksum: modelHash,
      compiler_profile: profile, status: 'ready', contract_pass: true,
      checkpoint: { available: true, terminal_epoch: 2, terminal_load_factor: 1, chain_hash: designHash('9'), artifact_hash: designHash('8') },
      contract_bindings: { checkpoint_chain_hash: designHash('9'), checkpoint_chain_artifact_hash: designHash('8') },
      node_displacements: [{ node_id: 'N1', UX_m: 0, UY_m: 0, UZ_m: 0 }, { node_id: 'N2', UX_m: 0, UY_m: 0.001, UZ_m: 0 }],
      fiber_results: [{ strain: 0.0001 }],
      configuration: { load_steps: 2, target_load_factors: [0.5, 1], scaled_residual_tolerance: 1e-10, solver_coordinate_increment_tolerance_m: 1e-12, maximum_iterations: 40, restart_supplied: false, restart_checkpoint_artifact_hash: null },
      authority: { reaction: 'authoritative', member_force: 'authoritative', section_resultant: 'authoritative', fiber_strain_stress: 'authoritative', engineering_design: 'not_authoritative', code_compliance: 'not_authoritative', commercial_use: 'not_authoritative', release_readiness: 'not_authoritative' },
      unsupported_features: [],
    },
    validation: { schema_version: 'public-rc-fiber-frame-validation-report.v1', status: 'ready', contract_pass: true, result_hash: resultHash, exact_engineering_recovery: true, checkpoint_available: true, terminal_epoch: 2, terminal_load_factor: 1, fallback_count: 0, regularization_count: 0, unsupported_feature_count: 0 },
    quantities: {
      schema_version: 'public-rc-fiber-member-quantities.v1', model_checksum: modelHash, scope,
      rebar_density_kg_per_m3: 7850, detailed_takeoff: false, excluded_items: excluded,
      concrete_basis: 'gross_section_volume_without_rebar_displacement_deduction', reinforcement_basis: 'authored_longitudinal_bars_times_member_length',
      members: [{ member_id: 'M1', section_id: 'RC1', length_m: 1, gross_concrete_volume_m3: width, longitudinal_rebar_volume_m3: 0.02, longitudinal_rebar_mass_kg: 157 }],
      totals: { gross_concrete_volume_m3: width, longitudinal_rebar_volume_m3: 0.02, longitudinal_rebar_mass_kg: 157 }, quantity_hash: quantityHash,
    },
    material_estimate: {
      scope, currency: 'KRW', price_table_hash: designHash('c'), quantity_hash: quantityHash,
      members: [{ member_id: 'M1', concrete: width * 100, longitudinal_rebar: 314 }], total: width * 100 + 314,
      excluded_items: excluded, verified_quote: false, confirmed_currency_savings: false,
    },
    performance: { terminal_maximum_translation_m: 0.001, terminal_maximum_absolute_fiber_strain: 0.0001 },
    terminal_limit_status: 'pass', violated_terminal_limits: [], failure: null, comparable_to_baseline: true,
    difference_from_baseline: {
      quantity_delta: { gross_concrete_volume_m3: width - 1, longitudinal_rebar_volume_m3: 0, longitudinal_rebar_mass_kg: 0 },
      terminal_performance_delta: { terminal_maximum_translation_m: 0, terminal_maximum_absolute_fiber_strain: 0 },
      scoped_material_estimate_reduction: 100 * (1 - width), confirmed_currency_savings: null,
    },
  })
  return {
    schema_version: 'public-rc-fiber-design-comparison.v1', status: 'ready', baseline_id: 'baseline', report_hash: designHash('d'), experiment_identity_hash: designHash('e'),
    identity: {
      schema_version: 'public-rc-fiber-design-comparison.v1', source_revision: 'a'.repeat(40), compiler_profile: profile, configuration: config,
      baseline_model_checksum: designHash('1'),
      candidates: [{ candidate_id: 'narrow', model_checksum: designHash('2'), changes: [{ section_id: 'RC1', width_m: 0.5, depth_m: null, cover_m: null, top_bar_count: null, bottom_bar_count: null, bar_area_m2: null }] }],
      price_table_hash: designHash('c'), terminal_limits: { maximum_translation_m: 0.01, maximum_absolute_fiber_strain: 0.001 }, quantity_scope: scope, rebar_density_kg_per_m3: 7850,
    },
    rows: [row('baseline', 1, designHash('1'), designHash('3'), designHash('5')), row('narrow', 0.5, designHash('2'), designHash('4'), designHash('6'))],
    price_basis: { concrete_per_m3: 100, rebar_per_kg: 2, currency: 'KRW', as_of: '2026-09-08', source: 'Synthetic contract fixture; not a quote', price_table_hash: designHash('c') },
    selection: { criterion: 'minimum_scoped_material_estimate_with_verified_terminal_limits', candidate_id: 'narrow', eligible_count: 2, evaluated_pool_size: 2, reason: 'selected_within_declared_scope' },
    runtime: { total_wall_ns: 100 },
    claims: { actual_physical_design_changes: true, quantities_are_geometry_derived: true, all_analysis_requests_start_at_epoch_zero: true, all_requested_models_verified: true, limits_scope: 'terminal_translation_and_fiber_strain_only', detailed_takeoff: false, confirmed_currency_savings: false, design_code_compliance: false, engineering_approval: false, ai_acceleration_measured: false, commercial_readiness: false },
  }
}
