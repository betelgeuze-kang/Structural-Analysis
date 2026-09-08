export const DESIGN_SCOPE = 'gross_concrete_and_straight_authored_longitudinal_rebar.v1'
const REPORT_SCHEMA = 'public-rc-fiber-design-comparison.v1'
const HISTORY_REPORT_SCHEMA = 'public-rc-fiber-design-comparison.v2'
const PROFILE = 'planar_serial_cantilever_explicit_rectangular_rc.v1'
const HASH = /^sha256:[0-9a-f]{64}$/
const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const QUANTITIES = ['gross_concrete_volume_m3', 'longitudinal_rebar_volume_m3', 'longitudinal_rebar_mass_kg'] as const
const METRICS = ['terminal_maximum_translation_m', 'terminal_maximum_absolute_fiber_strain'] as const
const HISTORY_METRICS = ['history_maximum_translation_m', 'history_maximum_absolute_fiber_strain'] as const
const EXCLUDED = ['transverse_reinforcement', 'laps_anchorage_hooks', 'waste', 'formwork', 'labor', 'fabrication', 'transport', 'tax']
type Obj = Record<string, unknown>

export interface DesignComparisonManifest {
  schema_version: 'rc-fiber-design-comparison-bundle.v1'
  source_revision: string
  report_file: string
  report_byte_length: number
  report_sha256: string
  report_hash: string
  experiment_identity_hash: string
}

export interface DesignComparisonRow extends Obj {
  candidate_id: string
  model_checksum: string
  canonical_model: Obj
  status: string
  full_reference_verification_pass: boolean
  quantities: null | { quantity_hash: string; scope: string; members: Array<Obj & { member_id: string; section_id: string }>; totals: Record<typeof QUANTITIES[number], number> }
  material_estimate: null | { total: number; currency: string; price_table_hash: string; quantity_hash: string }
  performance: null | (Record<typeof METRICS[number], number> & Partial<Record<typeof HISTORY_METRICS[number], number>>)
  terminal_limit_status: 'pass' | 'fail' | 'not_requested' | 'unavailable'
  response_history?: Obj | null
  full_history_verification_pass?: boolean
  history_limit_status?: 'pass' | 'fail' | 'unavailable'
  comparable_to_baseline: boolean
  difference_from_baseline: null | { quantity_delta: Record<typeof QUANTITIES[number], number>; terminal_performance_delta: Record<typeof METRICS[number], number>; scoped_material_estimate_reduction: number | null; confirmed_currency_savings: null }
}

export interface DesignComparisonReport extends Obj {
  schema_version: typeof REPORT_SCHEMA | typeof HISTORY_REPORT_SCHEMA
  status: 'ready' | 'partial'
  report_hash: string
  experiment_identity_hash: string
  identity: Obj & { source_revision: string; baseline_model_checksum: string }
  baseline_id: 'baseline'
  rows: DesignComparisonRow[]
  price_basis: null | { concrete_per_m3: number; rebar_per_kg: number; currency: string; as_of: string; source: string; price_table_hash: string }
  selection: { candidate_id: string | null; eligible_count: number; evaluated_pool_size: number; criterion: string; reason: string }
}

export interface VerifiedDesignComparison {
  manifest: DesignComparisonManifest
  report: DesignComparisonReport
  manifestUrl: string
  reportUrl: string
}

export function validateDesignComparisonManifest(value: unknown): DesignComparisonManifest {
  const root = exact(value, ['schema_version', 'source_revision', 'report_file', 'report_byte_length', 'report_sha256', 'report_hash', 'experiment_identity_hash'])
  equal(root.schema_version, 'rc-fiber-design-comparison-bundle.v1')
  ensure(typeof root.source_revision === 'string' && /^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$/.test(root.source_revision), 'source revision')
  // Only an immediate, ordinary JSON file beside the manifest is supported.
  ensure(typeof root.report_file === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]*\.json$/.test(root.report_file), 'report file')
  integer(root.report_byte_length, 1, 64 * 1024 * 1024)
  for (const key of ['report_sha256', 'report_hash', 'experiment_identity_hash']) hash(root[key])
  return root as unknown as DesignComparisonManifest
}

/** Validate producer bindings and displayed arithmetic; never executes a solver or grants authority. */
export function validateDesignComparisonReport(value: unknown, manifest: DesignComparisonManifest): DesignComparisonReport {
  const root = obj(value)
  finiteTree(root)
  ensure(root.schema_version === REPORT_SCHEMA || root.schema_version === HISTORY_REPORT_SCHEMA, 'report schema')
  const historyRequested = root.schema_version === HISTORY_REPORT_SCHEMA
  equal(root.report_hash, manifest.report_hash)
  equal(root.experiment_identity_hash, manifest.experiment_identity_hash)
  equal(root.baseline_id, 'baseline')
  const identity = obj(root.identity)
  equal(identity.schema_version, root.schema_version)
  equal(identity.source_revision, manifest.source_revision)
  equal(identity.compiler_profile, PROFILE)
  equal(identity.quantity_scope, DESIGN_SCOPE)
  positive(identity.rebar_density_kg_per_m3)
  hash(identity.baseline_model_checksum)
  const config = obj(identity.configuration)
  integer(config.load_steps, 2, 64)
  integer(config.maximum_iterations, 1, 200)
  positive(config.residual_tolerance)
  positive(config.increment_tolerance_m)
  const candidates = list(identity.candidates, 1, 64)
  const rows = list(root.rows, 2, 65)
  equal(rows.length, candidates.length + 1)
  const seen = new Set<string>()
  const models = new Set<string>()
  const baseline = obj(rows[0])
  equal(baseline.candidate_id, 'baseline')
  equal(baseline.model_checksum, identity.baseline_model_checksum)
  const prices = root.price_basis === null ? null : obj(root.price_basis)
  if (prices) {
    nonnegative(prices.concrete_per_m3); nonnegative(prices.rebar_per_kg)
    ensure(typeof prices.currency === 'string' && /^[A-Z]{3}$/.test(prices.currency), 'currency')
    ensure(typeof prices.as_of === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(prices.as_of)
      && new Date(`${prices.as_of}T00:00:00Z`).toISOString().slice(0, 10) === prices.as_of, 'price date')
    ensure(typeof prices.source === 'string' && prices.source.trim().length > 0 && prices.source.length <= 1000, 'price source')
    hash(prices.price_table_hash)
  }
  equal(identity.price_table_hash, prices?.price_table_hash ?? null)
  const limits = identity.terminal_limits === null ? null : obj(identity.terminal_limits)
  if (limits) { positive(limits.maximum_translation_m); positive(limits.maximum_absolute_fiber_strain) }
  const historyLimits = historyRequested ? exact(identity.history_limits, ['maximum_translation_m', 'maximum_absolute_fiber_strain']) : null
  if (historyLimits) { positive(historyLimits.maximum_translation_m); positive(historyLimits.maximum_absolute_fiber_strain) }
  else ensure(!own(identity, 'history_limits'), 'terminal-only history scope')
  rows.forEach((value, index) => {
    const row = obj(value)
    ensure(typeof row.candidate_id === 'string' && ID.test(row.candidate_id) && !seen.has(row.candidate_id), 'candidate identity')
    seen.add(row.candidate_id)
    hash(row.model_checksum)
    ensure(!models.has(String(row.model_checksum)), 'duplicate physical model')
    models.add(String(row.model_checksum))
    const model = obj(row.canonical_model)
    equal(model.schema_version, 'structural-analysis-canonical-model.v1')
    equal(obj(model.units).length, 'm')
    const members = keyed(model.elements, 'id')
    const sections = keyed(model.sections, 'id')
    const nodes = keyed(model.nodes, 'id')
    for (const section of sections.values()) {
      for (const key of ['width_m', 'depth_m', 'cover_m', 'bar_area_m2']) positive(section[key])
      for (const key of ['top_bar_count', 'bottom_bar_count']) integer(section[key], 1, 64)
    }
    if (index > 0) {
      const candidate = obj(candidates[index - 1])
      equal(row.candidate_id, candidate.candidate_id)
      equal(row.model_checksum, candidate.model_checksum)
      validatePhysicalChanges(obj(baseline.canonical_model), model, candidate.changes)
    }
    ensure(typeof row.full_reference_verification_pass === 'boolean', 'verification state')
    ensure(typeof row.status === 'string', 'row status')
    ensure(row.solver_executed === true || row.solver_executed === false || row.solver_executed === null, 'execution state')
    nonnegative(row.reference_and_quantity_wall_ns)
    if (!historyRequested) {
      for (const key of ['response_history', 'full_history_verification_pass', 'history_limit_status', 'violated_history_limits', 'history_failure']) ensure(!own(row, key), 'terminal-only history field')
      if (row.performance !== null) for (const key of HISTORY_METRICS) ensure(!own(obj(row.performance), key), 'terminal-only history metric')
    }
    if (!row.full_reference_verification_pass) {
      for (const key of ['quantities', 'material_estimate', 'performance']) equal(row[key], null)
      equal(row.terminal_limit_status, 'unavailable')
      ensure(row.status !== 'ready', 'unverified ready row')
      if (historyLimits) validateHistory(row, historyLimits, config)
      return
    }
    equal(row.status, 'ready')
    equal(row.solver_executed, true)
    equal(row.failure, null)
    const result = obj(row.result)
    const validation = obj(row.validation)
    equal(result.schema_version, 'public-rc-fiber-frame-result.v1')
    equal(validation.schema_version, 'public-rc-fiber-frame-validation-report.v1')
    hash(result.result_hash)
    equal(result.canonical_model_checksum, row.model_checksum)
    equal(result.compiler_profile, PROFILE)
    equal(result.status, 'ready'); equal(result.contract_pass, true)
    equal(validation.status, 'ready')
    equal(validation.result_hash, result.result_hash)
    for (const key of ['contract_pass', 'exact_engineering_recovery', 'checkpoint_available']) equal(validation[key], true)
    equal(validation.terminal_epoch, config.load_steps)
    equal(validation.terminal_load_factor, 1)
    for (const key of ['fallback_count', 'regularization_count', 'unsupported_feature_count']) equal(validation[key], 0)
    const checkpoint = obj(result.checkpoint)
    equal(checkpoint.available, true)
    hash(checkpoint.chain_hash); hash(checkpoint.artifact_hash)
    const resultBindings = obj(result.contract_bindings)
    equal(resultBindings.checkpoint_chain_hash, checkpoint.chain_hash)
    equal(resultBindings.checkpoint_chain_artifact_hash, checkpoint.artifact_hash)
    equal(checkpoint.terminal_epoch, config.load_steps)
    equal(checkpoint.terminal_load_factor, 1)
    const actualConfig = obj(result.configuration)
    equal(actualConfig.load_steps, config.load_steps)
    equal(actualConfig.scaled_residual_tolerance, config.residual_tolerance)
    equal(actualConfig.solver_coordinate_increment_tolerance_m, config.increment_tolerance_m)
    equal(actualConfig.maximum_iterations, config.maximum_iterations)
    equal(actualConfig.restart_supplied, false)
    equal(actualConfig.restart_checkpoint_artifact_hash, null)
    same(actualConfig.target_load_factors, Array.from({ length: Number(config.load_steps) }, (_, i) => (i + 1) / Number(config.load_steps)))
    for (const axis of ['reaction', 'member_force', 'section_resultant', 'fiber_strain_stress']) equal(obj(result.authority)[axis], 'authoritative')
    for (const axis of ['engineering_design', 'code_compliance', 'commercial_use', 'release_readiness']) equal(obj(result.authority)[axis], 'not_authoritative')
    equal(list(result.unsupported_features, 0, 1).length, 0)
    const quantities = obj(row.quantities)
    equal(quantities.schema_version, 'public-rc-fiber-member-quantities.v1')
    equal(quantities.model_checksum, row.model_checksum)
    equal(quantities.scope, DESIGN_SCOPE)
    equal(quantities.rebar_density_kg_per_m3, identity.rebar_density_kg_per_m3)
    equal(quantities.concrete_basis, 'gross_section_volume_without_rebar_displacement_deduction')
    equal(quantities.reinforcement_basis, 'authored_longitudinal_bars_times_member_length')
    equal(quantities.detailed_takeoff, false)
    same(quantities.excluded_items, EXCLUDED)
    hash(quantities.quantity_hash)
    const quantityMembers = keyed(quantities.members, 'member_id')
    same([...quantityMembers.keys()].sort(), [...members.keys()].sort())
    for (const [id, quantity] of quantityMembers) {
      equal(quantity.section_id, members.get(id)?.section)
      ensure(sections.has(String(quantity.section_id)), 'quantity section')
      positive(quantity.length_m)
      for (const key of QUANTITIES) nonnegative(quantity[key])
      const section = sections.get(String(quantity.section_id))!
      const nodeIds = list(members.get(id)!.nodes, 2, 2)
      const ends = nodeIds.map((nodeId) => {
        ensure(nodes.has(String(nodeId)), 'member node binding')
        return list(nodes.get(String(nodeId))!.coordinates, 3, 3).map((value) => { ensure(typeof value === 'number' && Number.isFinite(value), 'node coordinate'); return value })
      })
      const length = Math.hypot(...ends[0].map((value, index) => value - ends[1][index]))
      const barVolume = (Number(section.top_bar_count) + Number(section.bottom_bar_count)) * Number(section.bar_area_m2) * length
      close(quantity.length_m, length)
      close(quantity.gross_concrete_volume_m3, Number(section.width_m) * Number(section.depth_m) * length)
      close(quantity.longitudinal_rebar_volume_m3, barVolume)
      close(quantity.longitudinal_rebar_mass_kg, barVolume * Number(identity.rebar_density_kg_per_m3))
    }
    for (const key of QUANTITIES) close(obj(quantities.totals)[key], [...quantityMembers.values()].reduce((sum, row) => sum + Number(row[key]), 0))
    if (prices) {
      const estimate = obj(row.material_estimate)
      equal(estimate.scope, DESIGN_SCOPE)
      equal(estimate.currency, prices.currency)
      equal(estimate.price_table_hash, prices.price_table_hash)
      equal(estimate.quantity_hash, quantities.quantity_hash)
      equal(estimate.verified_quote, false); equal(estimate.confirmed_currency_savings, false)
      same(estimate.excluded_items, EXCLUDED)
      const costs = keyed(estimate.members, 'member_id')
      same([...costs.keys()].sort(), [...members.keys()].sort())
      for (const [id, cost] of costs) {
        const quantity = quantityMembers.get(id)!
        close(cost.concrete, Number(quantity.gross_concrete_volume_m3) * Number(prices.concrete_per_m3))
        close(cost.longitudinal_rebar, Number(quantity.longitudinal_rebar_mass_kg) * Number(prices.rebar_per_kg))
      }
      close(estimate.total, [...costs.values()].reduce((sum, cost) => sum + Number(cost.concrete) + Number(cost.longitudinal_rebar), 0))
    } else equal(row.material_estimate, null)
    const performance = obj(row.performance)
    for (const key of METRICS) nonnegative(performance[key])
    const translations = list(result.node_displacements, 1, 1024).map((value) => {
      const node = obj(value)
      const components = ['UX_m', 'UY_m', 'UZ_m'].map((key) => { ensure(typeof node[key] === 'number' && Number.isFinite(node[key]), 'result translation'); return Number(node[key]) })
      return Math.hypot(...components)
    })
    const strains = list(result.fiber_results, 1, 100000).map((value) => { const strain = obj(value).strain; ensure(typeof strain === 'number' && Number.isFinite(strain), 'result strain'); return Math.abs(strain) })
    close(performance.terminal_maximum_translation_m, Math.max(...translations))
    close(performance.terminal_maximum_absolute_fiber_strain, strains.reduce((largest, value) => Math.max(largest, value), 0))
    const violated = limits ? METRICS.filter((key, i) => Number(performance[key]) > Number(limits[i === 0 ? 'maximum_translation_m' : 'maximum_absolute_fiber_strain'])) : []
    same(row.violated_terminal_limits, violated)
    equal(row.terminal_limit_status, limits ? violated.length ? 'fail' : 'pass' : 'not_requested')
    if (historyLimits) validateHistory(row, historyLimits, config)
  })
  rows.forEach((value) => {
    const row = obj(value)
    const comparable = baseline.full_reference_verification_pass === true && row.full_reference_verification_pass === true
    equal(row.comparable_to_baseline, comparable)
    if (!comparable) { equal(row.difference_from_baseline, null); return }
    const delta = obj(row.difference_from_baseline)
    for (const key of QUANTITIES) close(obj(delta.quantity_delta)[key], Number(obj(obj(row.quantities).totals)[key]) - Number(obj(obj(baseline.quantities).totals)[key]))
    for (const key of METRICS) close(obj(delta.terminal_performance_delta)[key], Number(obj(row.performance)[key]) - Number(obj(baseline.performance)[key]))
    if (prices) close(delta.scoped_material_estimate_reduction, Number(obj(baseline.material_estimate).total) - Number(obj(row.material_estimate).total))
    else equal(delta.scoped_material_estimate_reduction, null)
    equal(delta.confirmed_currency_savings, null)
  })
  const eligible = rows.map(obj).filter((row) => row.full_reference_verification_pass === true && row.terminal_limit_status === 'pass' && row.material_estimate !== null
    && (!historyRequested || row.full_history_verification_pass === true && row.history_limit_status === 'pass'))
  const selection = obj(root.selection)
  equal(selection.criterion, historyRequested ? 'minimum_scoped_material_estimate_with_verified_terminal_and_history_limits' : 'minimum_scoped_material_estimate_with_verified_terminal_limits')
  equal(selection.evaluated_pool_size, rows.length)
  equal(selection.eligible_count, eligible.length)
  const winner = baseline.full_reference_verification_pass === true && (!historyRequested || baseline.full_history_verification_pass === true) ? eligible.sort((a, b) => Number(obj(a.material_estimate).total) - Number(obj(b.material_estimate).total) || (String(a.candidate_id) < String(b.candidate_id) ? -1 : 1))[0] : undefined
  equal(selection.candidate_id, winner?.candidate_id ?? null)
  equal(selection.reason, winner ? 'selected_within_declared_scope' : 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes')
  const allVerified = rows.every((row) => obj(row).full_reference_verification_pass === true)
  const allHistoryVerified = !historyRequested || rows.every((row) => obj(row).full_history_verification_pass === true)
  equal(root.status, allVerified && allHistoryVerified ? 'ready' : 'partial')
  const claims = obj(root.claims)
  for (const key of ['actual_physical_design_changes', 'quantities_are_geometry_derived', 'all_analysis_requests_start_at_epoch_zero']) equal(claims[key], true)
  equal(claims.all_requested_models_verified, allVerified)
  if (historyRequested) equal(claims.all_requested_history_verified, allHistoryVerified)
  equal(claims.limits_scope, historyRequested ? 'terminal_and_committed_history_translation_and_fiber_strain' : 'terminal_translation_and_fiber_strain_only')
  for (const key of ['detailed_takeoff', 'confirmed_currency_savings', 'design_code_compliance', 'engineering_approval', 'ai_acceleration_measured', 'commercial_readiness']) equal(claims[key], false)
  return root as unknown as DesignComparisonReport
}

/** The provider binds all sidecar bytes; this validates source links and displayed extrema. */
function validateHistory(row: Obj, limits: Obj, config: Obj): void {
  ensure(typeof row.full_history_verification_pass === 'boolean', 'history verification state')
  if (!row.full_history_verification_pass) {
    equal(row.response_history, null)
    equal(row.history_limit_status, 'unavailable')
    same(row.violated_history_limits, [])
    if (row.performance !== null) for (const key of HISTORY_METRICS) ensure(!own(obj(row.performance), key), 'unverified history metric')
    return
  }
  equal(row.full_reference_verification_pass, true)
  if (own(row, 'history_failure')) equal(row.history_failure, null)
  const result = obj(row.result)
  const source = obj(result.contract_bindings)
  const checkpoint = obj(result.checkpoint)
  const sidecar = obj(row.response_history)
  equal(sidecar.schema_version, 'public-rc-fiber-frame-response-history.v1')
  equal(sidecar.status, 'ready'); equal(sidecar.contract_pass, true)
  hash(sidecar.report_hash); hash(sidecar.history_hash)
  equal(sidecar.source_result_hash, result.result_hash)
  equal(sidecar.canonical_model_checksum, row.model_checksum)
  const history = obj(sidecar.history)
  equal(history.schema_version, 'stateful-fiber-frame2d-nonlinear-engineering-history.v1')
  equal(history.status, 'ready'); equal(history.contract_pass, true)
  equal(history.history_hash, sidecar.history_hash)
  equal(history.epoch_count, config.load_steps); equal(history.terminal_epoch, config.load_steps)
  equal(history.terminal_load_factor, 1)
  const scope = obj(history.scope)
  equal(scope.committed_epochs_only, true); equal(scope.genesis_included, false)
  equal(scope.complete_monotonic_static_load_path, true)
  for (const key of ['between_step_extrema_verified', 'cyclic_or_dynamic_history_verified', 'constitutive_law_independently_verified', 'engineering_design_verified', 'code_compliance_verified', 'production_promotion_eligible']) equal(scope[key], false)
  same(history.authority, result.authority)
  const bindings = obj(history.bindings)
  for (const key of ['source_result_adapter_hash', 'source_binding_hash', 'source_numerical_result_hash', 'problem_contract_hash', 'model_ir_content_hash', 'execution_topology_plan_hash', 'physical_equation_scaling_binding_hash', 'execution_state_binding_hash', 'checkpoint_chain_hash', 'root_checkpoint_state_hash', 'terminal_checkpoint_state_hash', 'kinematic_state_chain_hash', 'material_state_projection_chain_hash', 'terminal_receipt_hash']) hash(bindings[key])
  for (const [key, expected] of [
    ['source_result_adapter_hash', source.source_result_adapter_hash], ['source_numerical_result_hash', source.numerical_result_hash],
    ['problem_contract_hash', source.problem_contract_hash], ['model_ir_content_hash', row.model_checksum],
    ['execution_topology_plan_hash', source.execution_topology_plan_hash], ['checkpoint_chain_hash', checkpoint.chain_hash],
    ['root_checkpoint_state_hash', checkpoint.root_state_hash], ['terminal_checkpoint_state_hash', checkpoint.terminal_state_hash],
  ]) equal(bindings[String(key)], expected)
  const receipt = obj(history.source_terminal_receipt)
  equal(receipt.terminal_receipt_hash, bindings.terminal_receipt_hash)
  const receiptBindings = obj(receipt.bindings)
  for (const key of ['problem_contract_hash', 'model_ir_content_hash', 'execution_topology_plan_hash', 'physical_equation_scaling_binding_hash', 'execution_state_binding_hash', 'checkpoint_chain_hash', 'root_checkpoint_state_hash', 'terminal_checkpoint_state_hash', 'kinematic_state_chain_hash', 'material_state_projection_chain_hash']) equal(receiptBindings[key], bindings[key])
  const terminal = obj(receipt.terminal)
  equal(terminal.accepted_step_count, config.load_steps); equal(terminal.terminal_epoch, config.load_steps)
  equal(terminal.terminal_load_factor, 1); equal(terminal.converged, true)
  equal(terminal.fallback_count, 0); equal(terminal.regularization_count, 0)
  const count = Number(config.load_steps)
  const steps = list(history.steps, count, count).map(obj)
  const receipts = list(receipt.step_receipts, count, count).map(obj)
  const terminalNodes = list(result.node_displacements, 1, 16).map(obj)
  const terminalFibers = list(result.fiber_results, 1, 100000).map(obj)
  same([...keyed(result.node_displacements, 'node_id').keys()].sort(), [...keyed(obj(row.canonical_model).nodes, 'id').keys()].sort())
  const memberIds = keyed(obj(row.canonical_model).elements, 'id')
  let parent = bindings.root_checkpoint_state_hash
  const recovered: Obj[] = []
  steps.forEach((step, index) => {
    const epoch = index + 1
    equal(step.epoch, epoch); equal(step.step_index, epoch)
    equal(step.target_load_factor, epoch / count)
    hash(step.recovery_hash); hash(step.array_bundle_hash)
    obj(step.orders); obj(step.metrics); obj(step.recovery_arrays)
    list(step.recovery_array_descriptors, 1, 128); obj(step.displacement_array_descriptor)
    const bound = obj(step.bindings)
    for (const key of ['checkpoint_state_hash', 'parent_checkpoint_state_hash', 'kinematic_state_hash', 'material_projection_receipt_hash', 'material_state_bundle_hash', 'execution_epoch_binding_hash', 'step_receipt_hash', 'source_solution_data_hash']) hash(bound[key])
    equal(bound.parent_checkpoint_state_hash, parent)
    parent = bound.checkpoint_state_hash
    const stepReceipt = receipts[index]
    equal(stepReceipt.step_receipt_hash, bound.step_receipt_hash)
    same(stepReceipt.coordinates, { epoch, step_index: epoch, target_load_factor: epoch / count })
    const stepReceiptBindings = obj(stepReceipt.bindings)
    for (const [key, expected] of [
      ['parent_checkpoint_state_hash', bound.parent_checkpoint_state_hash], ['accepted_checkpoint_state_hash', bound.checkpoint_state_hash],
      ['committed_kinematic_state_hash', bound.kinematic_state_hash], ['committed_material_state_bundle_hash', bound.material_state_bundle_hash],
    ]) equal(stepReceiptBindings[String(key)], expected)
    equal(obj(stepReceipt.binary_identities).source_solution_data_hash, bound.source_solution_data_hash)
    const nodes = list(step.node_displacements, terminalNodes.length, terminalNodes.length).map(obj)
    same(nodes.map(node => node.node_id), terminalNodes.map(node => node.node_id))
    const displacement = list(step.displacement_canonical_si, nodes.length * 6, nodes.length * 6)
    nodes.forEach((node, nodeIndex) => {
      exact(node, ['node_id', 'UX_m', 'UY_m', 'UZ_m', 'RX_rad', 'RY_rad', 'RZ_rad'])
      for (const [component, key] of ['UX_m', 'UY_m', 'UZ_m', 'RX_rad', 'RY_rad', 'RZ_rad'].entries()) {
        ensure(typeof node[key] === 'number' && Number.isFinite(node[key]), 'history displacement')
        close(displacement[nodeIndex * 6 + component], Number(node[key]))
      }
    })
    const fibers = list(step.fiber_results, terminalFibers.length, terminalFibers.length).map(obj)
    const recoveredStrains = list(obj(step.recovery_arrays).fiber_strain, fibers.length, fibers.length)
    const fiberIds = new Set<string>()
    fibers.forEach((fiber, fiberIndex) => {
      exact(fiber, ['member_id', 'integration_point_index', 'fiber_index', 'fiber_id', 'material_kind', 'y_m', 'area_m2', 'strain', 'stress_MPa', 'dissipated_energy_density_MJ_per_m3'])
      ensure(typeof fiber.member_id === 'string' && memberIds.has(fiber.member_id), 'history fiber member')
      ensure(typeof fiber.fiber_id === 'string' && ID.test(fiber.fiber_id), 'history fiber label')
      integer(fiber.integration_point_index, 0, 1024); integer(fiber.fiber_index, 0, 100000)
      const fiberKey = JSON.stringify([fiber.member_id, fiber.integration_point_index, fiber.fiber_index])
      ensure(!fiberIds.has(fiberKey), 'duplicate history fiber'); fiberIds.add(fiberKey)
      ensure(fiber.material_kind === 'steel' || fiber.material_kind === 'concrete', 'history material kind')
      positive(fiber.area_m2); nonnegative(fiber.dissipated_energy_density_MJ_per_m3)
      for (const key of ['y_m', 'strain', 'stress_MPa']) ensure(typeof fiber[key] === 'number' && Number.isFinite(fiber[key]), 'history fiber value')
      for (const key of ['member_id', 'integration_point_index', 'fiber_index', 'fiber_id', 'material_kind', 'y_m', 'area_m2']) equal(fiber[key], terminalFibers[fiberIndex][key])
      close(recoveredStrains[fiberIndex], Number(fiber.strain))
    })
    const translations = nodes.map(node => Math.hypot(Number(node.UX_m), Number(node.UY_m), Number(node.UZ_m)))
    const strains = fibers.map(fiber => Math.abs(Number(fiber.strain)))
    const translationIndex = translations.reduce((largest, value, i) => value > translations[largest] ? i : largest, 0)
    const strainIndex = strains.reduce((largest, value, i) => value > strains[largest] ? i : largest, 0)
    const envelope = obj(step.envelope)
    close(envelope.maximum_translation_m, translations[translationIndex])
    close(envelope.maximum_absolute_fiber_strain, strains[strainIndex])
    same(envelope.governing_translation, { epoch, ...nodes[translationIndex], translation_m: envelope.maximum_translation_m })
    same(envelope.governing_fiber_strain, { epoch, ...fibers[strainIndex], absolute_strain: strains[strainIndex] })
    recovered.push(envelope)
  })
  equal(parent, checkpoint.terminal_state_hash)
  const last = steps[steps.length - 1]
  same(last.node_displacements, result.node_displacements); same(last.fiber_results, result.fiber_results)
  equal(obj(last.bindings).kinematic_state_hash, source.terminal_kinematic_state_hash)
  equal(obj(last.bindings).material_state_bundle_hash, source.terminal_material_state_bundle_hash)
  const translation = recovered.reduce((largest, value) => Number(value.maximum_translation_m) > Number(largest.maximum_translation_m) ? value : largest)
  const strain = recovered.reduce((largest, value) => Number(value.maximum_absolute_fiber_strain) > Number(largest.maximum_absolute_fiber_strain) ? value : largest)
  const envelope = obj(history.envelope)
  close(envelope.maximum_translation_m, Number(translation.maximum_translation_m))
  close(envelope.maximum_absolute_fiber_strain, Number(strain.maximum_absolute_fiber_strain))
  same(envelope.governing_translation, translation.governing_translation)
  same(envelope.governing_fiber_strain, strain.governing_fiber_strain)
  const performance = obj(row.performance)
  close(performance.history_maximum_translation_m, Number(envelope.maximum_translation_m))
  close(performance.history_maximum_absolute_fiber_strain, Number(envelope.maximum_absolute_fiber_strain))
  const violated = HISTORY_METRICS.filter((key, index) => Number(performance[key]) > Number(limits[index === 0 ? 'maximum_translation_m' : 'maximum_absolute_fiber_strain']))
  same(row.violated_history_limits, violated)
  equal(row.history_limit_status, violated.length ? 'fail' : 'pass')
}

function validatePhysicalChanges(baseline: Obj, candidate: Obj, value: unknown): void {
  const expected = structuredClone(baseline)
  const sections = keyed(expected.sections, 'id')
  const changed = new Set<string>()
  let actualChange = false
  for (const item of list(value, 1, 16)) {
    const change = exact(item, ['section_id', 'width_m', 'depth_m', 'cover_m', 'top_bar_count', 'bottom_bar_count', 'bar_area_m2'])
    ensure(typeof change.section_id === 'string' && !changed.has(change.section_id), 'section change identity')
    changed.add(change.section_id)
    const section = sections.get(change.section_id)
    ensure(!!section, 'unknown changed section')
    for (const [key, next] of Object.entries(change)) {
      if (key === 'section_id' || next === null) continue
      key.endsWith('bar_count') ? integer(next, 1, 64) : positive(next)
      actualChange ||= section![key] !== next
      section![key] = next
    }
  }
  ensure(actualChange, 'physical design is unchanged')
  same(candidate, expected)
}

function ensure(condition: boolean, detail: string): asserts condition { if (!condition) throw new Error(`design comparison ${detail} is invalid`) }
function own(value: Obj, key: string): boolean { return Object.prototype.hasOwnProperty.call(value, key) }
function obj(value: unknown): Obj { ensure(!!value && typeof value === 'object' && !Array.isArray(value), 'object'); return value as Obj }
function exact(value: unknown, keys: string[]): Obj { const result = obj(value); same(Object.keys(result).sort(), [...keys].sort()); return result }
function list(value: unknown, minimum: number, maximum: number): unknown[] { ensure(Array.isArray(value) && value.length >= minimum && value.length <= maximum, 'array'); return value }
function keyed(value: unknown, field: string): Map<string, Obj> { const result = new Map<string, Obj>(); for (const item of list(value, 1, 1024)) { const row = obj(item); ensure(typeof row[field] === 'string' && ID.test(row[field] as string) && !result.has(row[field] as string), 'entity identity'); result.set(row[field] as string, row) } return result }
function equal(value: unknown, expected: unknown): void { ensure(value === expected, 'binding') }
function same(value: unknown, expected: unknown): void {
  if (Array.isArray(value) || Array.isArray(expected)) {
    ensure(Array.isArray(value) && Array.isArray(expected) && value.length === expected.length, 'content binding')
    value.forEach((item, index) => same(item, expected[index]))
  } else if (value && expected && typeof value === 'object' && typeof expected === 'object') {
    const actualKeys = Object.keys(value).sort()
    const expectedKeys = Object.keys(expected).sort()
    ensure(actualKeys.length === expectedKeys.length && actualKeys.every((key, index) => key === expectedKeys[index]), 'content binding')
    actualKeys.forEach((key) => same((value as Obj)[key], (expected as Obj)[key]))
  } else ensure(Object.is(value, expected), 'content binding')
}
function hash(value: unknown): void { ensure(typeof value === 'string' && HASH.test(value), 'hash') }
function nonnegative(value: unknown): asserts value is number { ensure(typeof value === 'number' && Number.isFinite(value) && value >= 0, 'nonnegative number') }
function positive(value: unknown): void { nonnegative(value); ensure(value > 0, 'positive number') }
function integer(value: unknown, min: number, max: number): void { ensure(typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max, 'integer') }
function close(value: unknown, expected: number): void { ensure(typeof value === 'number' && Number.isFinite(value) && Math.abs(value - expected) <= 1e-10 * Math.max(1, Math.abs(value), Math.abs(expected)), 'arithmetic binding') }
function finiteTree(value: unknown): void { if (typeof value === 'number') ensure(Number.isFinite(value), 'finite number'); else if (Array.isArray(value)) value.forEach(finiteTree); else if (value && typeof value === 'object') Object.values(value).forEach(finiteTree) }
