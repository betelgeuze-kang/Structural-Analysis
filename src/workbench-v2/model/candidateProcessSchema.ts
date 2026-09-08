import { canonicalJson } from './checksum'
import { validateDesignComparisonReport, validateDesignMaterialHistoryScopes, validateMaterialHistoryLimits, type VerifiedDesignComparison } from './designComparisonSchema'

export type CandidateObject = Record<string, unknown>
export type CandidateProcessStrategy = 'deterministic' | 'learned' | 'oracle'
export type CandidateProcessPhase = 'warmup' | 'measured'
export interface CandidateArtifact { source_path: string; file: string; byte_length: number; sha256: string }
export interface CandidateComparisonEntry { case_id: string; phase: CandidateProcessPhase; repetition: number; strategy: 'deterministic' | 'learned'; worker_report_hash: string; manifest_file: string; manifest_byte_length: number; manifest_sha256: string }
export interface CandidateProcessManifest {
  schema_version: 'rc-fiber-candidate-process-review-bundle.v1' | 'rc-fiber-candidate-process-review-bundle.v2'; source_revision: string
  suite_file: 'suite.json'; suite_byte_length: number; suite_sha256: string; suite_report_hash: string; suite_identity_hash: string
  artifacts: CandidateArtifact[]; comparisons: CandidateComparisonEntry[]
}
export interface CandidateDistribution { count: number; minimum: number | null; maximum: number | null; median: number | null; population_standard_deviation: number | null }
export interface CandidatePhaseCounts { declared_worker_slots: number; attempted_worker_slots: number; validated_report_count: number; unknown_request_slots: number; not_launched_slots: number; validated_online_request_subtotal: number; validated_oracle_request_subtotal: number; total_analysis_request_count: number | null; known_solver_execution_subtotal: number; unknown_solver_execution_subtotal: number }
export interface CandidateProcessCostAccounting extends CandidateObject {
  historical_data_generation_wall_ns: number; historical_training_wall_ns: number; historical_training_analysis_request_count: number
  current_analysis_request_count: number | null; total_analysis_request_count_including_training_warmups_and_oracles: number | null
  current_parent_wall_ns_through_aggregation: number; accounted_wall_ns_including_historical_generation_and_fit: number
  historical_cpu_time_ns: null; phases: Record<CandidateProcessPhase, CandidatePhaseCounts>
}
export interface CandidateWorkerSummary extends CandidateObject {
  observed_workers: number; declared_slots: number; worker_cpu_process_time_ns: CandidateDistribution; launch_to_exit_wall_ns: CandidateDistribution; peak_memory_bytes: CandidateDistribution
  input_bytes_read: number; input_read_wall_ns: number; report_bytes_written: number; report_write_flush_fsync_wall_ns: number
}
export interface CandidateProcessResourceAccounting extends CandidateObject {
  parent_cpu_time_ns: number; parent_wall_ns: number; parent_preflight_cpu_ns: number; parent_preflight_wall_ns: number
  worker_cpu_process_time_ns_subtotal: number; worker_cpu_process_time_ns: number | null; current_parent_plus_workers_cpu_time_ns: number | null
  workers_by_strategy: Record<CandidateProcessStrategy, Record<CandidateProcessPhase, CandidateWorkerSummary>>
}
export interface CandidateWorkerResources extends CandidateObject { cpu_process_time_ns: number; peak_memory_bytes: number | null; input_bytes_read: number; report_bytes_written: number; workload_wall_ns: number; workload_cpu_process_time_ns: number }
export interface CandidateWorkerManifest extends CandidateObject { status: string; worker_pid: number; launch_to_exit_wall_ns: number; parent_orchestration_cpu_time_ns: number; artifacts: Record<string, { sha256: string; byte_length: number }> }
export interface CandidateArmCost extends CandidateObject { total_analysis_request_count: number; known_solver_execution_count: number; unknown_solver_execution_count: number; charged_online_wall_ns: number; inference_wall_ns: number; full_reanalysis_wall_ns: number; baseline_analysis_request_count: number; candidate_analysis_request_count: number }
export interface CandidateOutcome extends CandidateObject { candidate_id: string; analysis_requested: boolean; solver_executed: boolean | null; full_reference_verification_pass: boolean; full_history_verification_pass?: boolean; terminal_limit_status?: string; history_limit_status?: string; material_estimate?: { total: number; currency: string } | null }
export interface CandidateWorkerReport extends CandidateObject {
  status: string; strategy: CandidateProcessStrategy; report_hash: string; cost_accounting: CandidateObject
  arm?: CandidateObject & { cost_accounting: CandidateArmCost; final_selection: CandidateOutcome | null; baseline: CandidateOutcome; candidate_outcomes: CandidateOutcome[]; shortlist: string[]; ranking: string[] }
}
export interface CandidateProcessRun extends CandidateObject {
  case_id: string; phase: CandidateProcessPhase; repetition: number; strategy: CandidateProcessStrategy; attempted: boolean; report_contract_pass: boolean; resource_contract_pass: boolean
  report: CandidateWorkerReport | null; resources: CandidateWorkerResources | null; manifest: CandidateWorkerManifest | null
  parent_slot_observed_wall_ns: number; parent_slot_cpu_time_ns: number
}
export interface CandidateCaseSummary extends CandidateObject { case_id: string; measured_pairs: CandidateObject[]; projected_reuses_to_amortize_this_training_artifact: number | null; paired_deterministic_minus_learned_slot_wall_ns: CandidateDistribution; paired_deterministic_minus_learned_worker_cpu_ns: CandidateDistribution }
export interface CandidateProcessSuite extends CandidateObject {
  status: 'ready' | 'incomplete'; declaration: CandidateObject; report_hash: string; suite_identity_hash: string
  runs: CandidateProcessRun[]; case_summaries: CandidateCaseSummary[]; cost_accounting: CandidateProcessCostAccounting; resource_accounting: CandidateProcessResourceAccounting; claims: CandidateObject
}
export interface CandidateProcessSlot { key: string; caseId: string; phase: CandidateProcessPhase; repetition: number; strategy: CandidateProcessStrategy; run: CandidateProcessRun; comparison: VerifiedDesignComparison | null; comparisonManifestBytes: Uint8Array | null; comparisonReportBytes: Uint8Array | null }
export interface VerifiedCandidateProcessReview { manifest: CandidateProcessManifest; suite: CandidateProcessSuite; manifestUrl: string; suiteUrl: string; manifestBytes: Uint8Array; suiteBytes: Uint8Array; slots: CandidateProcessSlot[] }
export interface CandidateLoadedArtifact { bytes: Uint8Array; value: unknown }
export interface CandidateLoadedComparison { bundle: VerifiedDesignComparison; manifestBytes: Uint8Array; reportBytes: Uint8Array }

const STRATEGIES = ['deterministic', 'learned', 'oracle'] as const
const PHASES = ['warmup', 'measured'] as const
const HASH = /^sha256:[0-9a-f]{64}$/
const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const SCHEDULE = 'round_major_case_order_alternating_online_arms_then_optional_oracle'
const PARENT_SCOPE = 'snapshot_preflight_extra_predictions_launch_wait_validation_aggregation_excludes_final_suite_encoding_and_persistence'
const WORKLOAD_SCOPE = 'input_contract_frozen_training_validation_pool_preparation_ranking_and_full_analysis_through_final_selection_before_report_assembly'
const PAIR_SCOPE = 'sequential_parent_slot_including_request_persistence_worker_spawn_import_input_preparation_ranking_reanalysis_selection_report_persistence_and_parent_validation_excludes_shared_preflight_final_aggregation_and_historical_training'
export const CANDIDATE_HISTORY_TARGET_PROFILE = 'terminal_and_committed_material_history.v1'
const HISTORY_TARGETS = ['history_maximum_translation_m', 'history_maximum_absolute_fiber_strain', 'history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage', 'history_maximum_concrete_compressive_damage']
const TARGETS = ['terminal_maximum_translation_m', 'terminal_maximum_absolute_fiber_strain', ...HISTORY_TARGETS]
const PREDICTED_SCOPE_FIELDS = ['predicted_history_safe', 'predicted_material_history_safe', 'predicted_requested_limits_safe', 'predicted_requested_limit_ratio']

function ensure(ok: unknown, reason: string): asserts ok { if (!ok) throw new Error(`candidate_process_${reason}`) }
function object(value: unknown): CandidateObject { ensure(value !== null && typeof value === 'object' && !Array.isArray(value), 'object_required'); return value as CandidateObject }
function exact(value: unknown, fields: string[]): CandidateObject { const row = object(value); same(Object.keys(row).sort(), fields.sort()); return row }
function array(value: unknown, maximum = 32768): unknown[] { ensure(Array.isArray(value) && value.length <= maximum, 'bounded_array_required'); return value }
function number(value: unknown): number { ensure(typeof value === 'number' && Number.isFinite(value), 'finite_number_required'); return value }
function natural(value: unknown): number { const result = number(value); ensure(Number.isSafeInteger(result) && result >= 0, 'safe_natural_required'); return result }
function boolean(value: unknown): boolean { ensure(typeof value === 'boolean', 'boolean_required'); return value }
function string(value: unknown): string { ensure(typeof value === 'string' && value.length > 0 && value.length <= 4096, 'string_required'); return value }
function hash(value: unknown): string { const result = string(value); ensure(HASH.test(result), 'hash_required'); return result }
function same(a: unknown, b: unknown): void { ensure(canonicalJson(a) === canonicalJson(b), 'binding_or_arithmetic_mismatch') }
function equal(a: unknown, b: unknown): void { ensure(a === b, 'value_mismatch') }
function sum(values: number[]): number { const result = values.reduce((a, b) => a + b, 0); ensure(Number.isSafeInteger(result), 'unsafe_sum'); return result }
function finiteTree(value: unknown, depth = 0, count = { value: 0 }): void {
  ensure(depth <= 64 && ++count.value <= 2_000_000, 'json_complexity_limit')
  if (typeof value === 'number') number(value)
  else if (Array.isArray(value)) value.forEach(item => finiteTree(item, depth + 1, count))
  else if (value !== null && typeof value === 'object') Object.values(value).forEach(item => finiteTree(item, depth + 1, count))
}
export function candidateProcessSlotKey(caseId: string, phase: string, repetition: number, strategy: string): string { return JSON.stringify([caseId, phase, repetition, strategy]) }
export function candidateProcessSafeFile(value: unknown): string {
  const file = string(value)
  ensure(file.length <= 1024 && file.split('/').every(part => /^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$/.test(part) && part !== '.' && part !== '..'), 'unsafe_file')
  return file
}
function byteIdentity(value: unknown): void { const row = object(value); hash(row.sha256); natural(row.byte_length) }

export function validateCandidateProcessManifest(value: unknown): CandidateProcessManifest {
  const m = exact(value, ['schema_version', 'source_revision', 'suite_file', 'suite_byte_length', 'suite_sha256', 'suite_report_hash', 'suite_identity_hash', 'artifacts', 'comparisons'])
  ensure(['rc-fiber-candidate-process-review-bundle.v1', 'rc-fiber-candidate-process-review-bundle.v2'].includes(string(m.schema_version)), 'review_schema'); equal(m.suite_file, 'suite.json')
  ensure(/^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$/.test(string(m.source_revision)), 'source_revision')
  ensure(natural(m.suite_byte_length) > 0 && natural(m.suite_byte_length) <= 64 * 1024 * 1024, 'suite_size')
  for (const key of ['suite_sha256', 'suite_report_hash', 'suite_identity_hash']) hash(m[key])
  const sources = new Set<string>(); const files = new Set(['suite.json', 'manifest.json']); const keys = new Set<string>()
  for (const item of array(m.artifacts)) {
    const row = exact(item, ['source_path', 'file', 'byte_length', 'sha256']); const source = string(row.source_path); const file = candidateProcessSafeFile(row.file)
    ensure(!sources.has(source) && !files.has(file), 'duplicate_artifact'); sources.add(source); files.add(file); byteIdentity(row); ensure(natural(row.byte_length) <= 64 * 1024 * 1024, 'artifact_size')
  }
  for (const item of array(m.comparisons, 4736)) {
    const row = exact(item, ['case_id', 'phase', 'repetition', 'strategy', 'worker_report_hash', 'manifest_file', 'manifest_byte_length', 'manifest_sha256'])
    ensure(ID.test(string(row.case_id)) && PHASES.includes(row.phase as CandidateProcessPhase) && ['deterministic', 'learned'].includes(string(row.strategy)), 'comparison_slot')
    const key = candidateProcessSlotKey(String(row.case_id), String(row.phase), natural(row.repetition), String(row.strategy)); const file = candidateProcessSafeFile(row.manifest_file)
    ensure(!keys.has(key) && !files.has(file), 'duplicate_comparison'); keys.add(key); files.add(file)
    hash(row.worker_report_hash); hash(row.manifest_sha256); ensure(natural(row.manifest_byte_length) > 0 && natural(row.manifest_byte_length) <= 16384, 'comparison_manifest_size')
  }
  return m as unknown as CandidateProcessManifest
}

function distribution(values: number[]): CandidateDistribution {
  if (!values.length) return { count: 0, minimum: null, maximum: null, median: null, population_standard_deviation: null }
  const sorted = [...values].sort((a, b) => a - b); const middle = Math.floor(sorted.length / 2); const mean = values.reduce((a, b) => a + b, 0) / values.length
  return { count: values.length, minimum: sorted[0], maximum: sorted[sorted.length - 1], median: sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2, population_standard_deviation: Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length) }
}
function checkDistribution(value: unknown, values: number[]): void {
  const expected = distribution(values); const row = exact(value, Object.keys(expected))
  for (const [key, x] of Object.entries(expected)) {
    if (x === null) equal(row[key], null)
    else { const actual = number(row[key]); ensure(Math.abs(actual - x) <= Math.max(1e-9, Math.abs(x) * 1e-12), 'distribution_mismatch') }
  }
}
function sourceArtifact(source: unknown, map: Map<string, CandidateLoadedArtifact>): CandidateLoadedArtifact { const row = map.get(string(source)); ensure(row, 'missing_source_artifact'); return row }
function sourceIdentity(value: unknown, manifest: CandidateProcessManifest): void {
  const row = object(value); byteIdentity(row); const artifact = manifest.artifacts.find(item => item.source_path === row.path)
  ensure(artifact && artifact.sha256 === row.sha256 && artifact.byte_length === row.byte_length, 'source_identity_mismatch')
}
function claims(value: unknown, truth: string[], falsity: string[]): void { const row = exact(value, [...truth, ...falsity]); truth.forEach(key => equal(row[key], true)); falsity.forEach(key => equal(row[key], false)) }
function outcomes(report: CandidateObject): CandidateObject[] {
  if (report.strategy === 'oracle') return array(report.rows, 65).map(object)
  const arm = object(report.arm); return [object(arm.baseline), ...array(arm.candidate_outcomes, 64).map(object)]
}
function counts(report: CandidateObject): { requested: number; known: number; unknown: number } {
  const rows = outcomes(report)
  rows.forEach(row => { boolean(row.analysis_requested); ensure(row.solver_executed === true || row.solver_executed === false || row.solver_executed === null, 'solver_execution_state'); if (!row.analysis_requested) equal(row.solver_executed, false) })
  const requested = rows.filter(row => row.analysis_requested)
  return { requested: requested.length, known: requested.filter(row => row.solver_executed === true).length, unknown: requested.filter(row => row.solver_executed === null).length }
}

function historyPredictionProfile(input: CandidateObject): boolean {
  if (input.candidate_target_profile === undefined) return false
  equal(input.candidate_target_profile, CANDIDATE_HISTORY_TARGET_PROFILE)
  return true
}
function nonnegative(value: unknown): number { const result = number(value); ensure(result >= 0, 'negative_prediction_or_limit'); return result }
function boundedRatio(value: number, limit: number): number { return limit === 0 ? value === 0 ? 0 : Number.MAX_VALUE : Math.min(Number.MAX_VALUE, value / limit) }

/** Recompute declared screens from stored estimates, without granting physical authority. */
export function validateCandidatePredictionRow(row: CandidateObject, input: CandidateObject, predicted: boolean): void {
  const historyProfile = historyPredictionProfile(input)
  if (!historyProfile) {
    PREDICTED_SCOPE_FIELDS.forEach(key => ensure(row[key] === undefined, 'unrequested_prediction_scope'))
    if (row.prediction !== null) { const prediction = object(row.prediction); ensure(prediction.target_profile === undefined && prediction.history_prediction === undefined, 'legacy_prediction_profile') }
    return
  }
  PREDICTED_SCOPE_FIELDS.forEach(key => ensure(Object.prototype.hasOwnProperty.call(row, key), 'missing_prediction_scope'))
  if (!predicted || row.screening_status !== 'ready') {
    equal(row.prediction, null)
    for (const key of ['predicted_terminal_safe', 'predicted_limit_ratio', ...PREDICTED_SCOPE_FIELDS]) equal(row[key], null)
    return
  }
  const prediction = exact(row.prediction, ['maximum_translation_m', 'maximum_absolute_fiber_strain', 'ood', 'reason', 'uncertainty_kind', 'physical_result_authority', 'target_profile', 'history_prediction'])
  equal(prediction.target_profile, CANDIDATE_HISTORY_TARGET_PROFILE); boolean(prediction.ood); string(prediction.reason)
  equal(prediction.uncertainty_kind, 'uncalibrated_feature_range_indicator_not_probability'); equal(prediction.physical_result_authority, false)
  if (prediction.ood) {
    for (const key of ['maximum_translation_m', 'maximum_absolute_fiber_strain', 'history_prediction']) equal(prediction[key], null)
    for (const key of ['predicted_terminal_safe', 'predicted_limit_ratio', ...PREDICTED_SCOPE_FIELDS]) equal(row[key], null)
    return
  }
  const terminalValues = [nonnegative(prediction.maximum_translation_m), nonnegative(prediction.maximum_absolute_fiber_strain)]
  const history = exact(prediction.history_prediction, [...HISTORY_TARGETS]); const historyValues = HISTORY_TARGETS.map(key => nonnegative(history[key]))
  ensure(historyValues[0] >= terminalValues[0] && historyValues[1] >= terminalValues[1] && historyValues[3] <= 1 && historyValues[4] <= 1, 'inconsistent_history_prediction')
  const terminal = object(input.terminal_limits)
  const terminalLimits = ['maximum_translation_m', 'maximum_absolute_fiber_strain'].map(key => nonnegative(terminal[key]))
  const scope = (values: number[], limits: number[]) => ({ safe: values.every((value, index) => value <= limits[index]), ratios: values.map((value, index) => boundedRatio(value, limits[index])) })
  const terminalScreen = scope(terminalValues, terminalLimits); const ratios = [...terminalScreen.ratios]; const safety = [terminalScreen.safe]
  equal(row.predicted_terminal_safe, terminalScreen.safe); equal(row.predicted_limit_ratio, Math.max(...terminalScreen.ratios))
  if (input.history_limits !== undefined) {
    const limits = object(input.history_limits); const screen = scope(historyValues.slice(0, 2), ['maximum_translation_m', 'maximum_absolute_fiber_strain'].map(key => nonnegative(limits[key])))
    equal(row.predicted_history_safe, screen.safe); ratios.push(...screen.ratios); safety.push(screen.safe)
  } else equal(row.predicted_history_safe, null)
  if (input.material_history_limits !== undefined) {
    ensure(input.history_limits !== undefined, 'material_prediction_requires_history_scope'); validateMaterialHistoryLimits(input.material_history_limits)
    const limits = object(input.material_history_limits); const screen = scope(historyValues.slice(2), ['maximum_steel_accumulated_plastic_strain', 'maximum_concrete_tensile_damage', 'maximum_concrete_compressive_damage'].map(key => nonnegative(limits[key])))
    equal(row.predicted_material_history_safe, screen.safe); ratios.push(...screen.ratios); safety.push(screen.safe)
  } else equal(row.predicted_material_history_safe, null)
  equal(row.predicted_requested_limits_safe, safety.every(Boolean)); equal(row.predicted_requested_limit_ratio, Math.max(...ratios))
}

/** Validate copied label consistency; raw-byte verification does not replay its source physics. */
function validateHistoryTrainingSample(sample: CandidateObject, training: CandidateObject): void {
  equal(sample.target_profile, CANDIDATE_HISTORY_TARGET_PROFILE)
  for (const key of ['feature_profile', 'identity_profile']) equal(sample[key], training[key])
  ensure(['train', 'validation', 'holdout'].includes(string(sample.split)), 'training_split')
  const targets = array(sample.targets, 7).map(nonnegative); equal(targets.length, 7)
  ensure(targets[2] >= targets[0] && targets[3] >= targets[1] && targets[5] <= 1 && targets[6] <= 1, 'training_target_range')
  const features = array(sample.features, 101); equal(features.length, 101); features.forEach(number)
  const source = exact(sample.history_label_source, ['schema_version', 'bindings', 'constitutive_history_report_hash', 'accepted_epoch_count', 'terminal_checkpoint_state_hash', 'epochs', 'source_hash'])
  equal(source.schema_version, 'fiber-frame-candidate-history-label-source.v1')
  for (const key of ['source_hash', 'constitutive_history_report_hash', 'terminal_checkpoint_state_hash']) hash(source[key])
  const bindings = exact(source.bindings, ['source_result_hash', 'canonical_model_checksum', 'input_checksum', 'problem_contract_hash', 'checkpoint_chain_hash', 'checkpoint_artifact_hash', 'checkpoint_artifact_byte_length', 'response_history_report_hash', 'engineering_history_hash'])
  for (const [key, value] of Object.entries(bindings)) key === 'checkpoint_artifact_byte_length' ? ensure(natural(value) > 0, 'checkpoint_length') : hash(value)
  for (const [key, sampleKey] of [['source_result_hash', 'public_result_hash'], ['canonical_model_checksum', 'canonical_model_checksum'], ['input_checksum', 'input_checksum'], ['checkpoint_chain_hash', 'checkpoint_chain_hash']]) equal(bindings[key], sample[sampleKey])
  const epochs = array(source.epochs, 64).map(object); equal(epochs.length, natural(source.accepted_epoch_count)); ensure(epochs.length > 0, 'label_epochs_required')
  const maxima = Array(5).fill(0) as number[]
  epochs.forEach((value, index) => {
    const epoch = exact(value, ['epoch', 'step_index', 'load_factor', 'checkpoint_state_hash', 'parent_checkpoint_state_hash', 'engineering_recovery_hash', 'targets'])
    equal(natural(epoch.epoch), index + 1); equal(natural(epoch.step_index), index + 1); equal(number(epoch.load_factor), (index + 1) / epochs.length)
    for (const key of ['checkpoint_state_hash', 'parent_checkpoint_state_hash', 'engineering_recovery_hash']) hash(epoch[key])
    if (index) equal(epoch.parent_checkpoint_state_hash, epochs[index - 1].checkpoint_state_hash)
    const values = array(epoch.targets, 5).map(nonnegative); equal(values.length, 5); ensure(values[3] <= 1 && values[4] <= 1, 'label_damage_range')
    values.forEach((value, target) => { maxima[target] = Math.max(maxima[target], value) })
  })
  equal(source.terminal_checkpoint_state_hash, epochs[epochs.length - 1].checkpoint_state_hash)
  same(targets.slice(2), maxima); same(targets.slice(0, 2), array(epochs[epochs.length - 1].targets).slice(0, 2))
  const matches = array(training.cases).map(object).filter(row => row.case_id === sample.case_id); equal(matches.length, 1)
  const row = matches[0]; const validation = object(row.validation)
  equal(row.split, sample.split); equal(row.status, 'ready'); equal(row.analysis_requested, true); equal(row.public_result_hash, sample.public_result_hash); equal(row.history_label_source_hash, source.source_hash)
  for (const key of ['contract_pass', 'exact_engineering_recovery', 'checkpoint_available']) equal(validation[key], true)
  equal(validation.result_hash, sample.public_result_hash); equal(natural(validation.terminal_epoch), epochs.length); equal(number(validation.terminal_load_factor), 1)
  ensure(natural(row.history_label_collection_wall_ns) <= natural(row.data_generation_wall_ns), 'label_collection_cost_scope')
}

/** Match the serialized learner's output scope to each frozen search plan. */
export function validateCandidatePredictionPlans(input: CandidateObject, training: CandidateObject, plans: CandidateObject): void {
  const policy = object(training.policy); const historyProfile = historyPredictionProfile(input)
  if (historyProfile) {
    equal(training.schema_version, 'fiber-frame-candidate-learning.v3'); equal(policy.schema_version, 'fiber-frame-candidate-ridge-policy.v3')
    equal(training.target_profile, CANDIDATE_HISTORY_TARGET_PROFILE); equal(policy.target_profile, CANDIDATE_HISTORY_TARGET_PROFILE); same(policy.targets, TARGETS); same(training.targets, TARGETS)
    const scales = array(policy.target_scale, 7); equal(scales.length, 7); scales.forEach(value => ensure(number(value) > 0, 'target_scale'))
    const features = array(policy.features, 101).map(string); equal(features.length, 101); equal(new Set(features).size, 101)
    for (const key of ['feature_mean', 'feature_scale', 'feature_min', 'feature_max']) { const values = array(policy[key], 101); equal(values.length, 101); values.forEach(value => key === 'feature_scale' ? ensure(number(value) > 0, 'feature_scale') : number(value)) }
    const weights = array(policy.weights, 102); equal(weights.length, 102); weights.forEach(row => { const values = array(row, 7); equal(values.length, 7); values.forEach(number) })
    for (const key of ['feature_profile', 'identity_profile']) { equal(training[key], input[key]); equal(policy[key], input[key]) }
    const labelClaims = object(training.claims)
    equal(labelClaims.history_labels_are_positive_committed_epoch_maxima, true)
    for (const key of ['material_memory_is_current_yield_event', 'caller_limits_used_to_clip_targets', 'frozen_label_validation_is_independent_source_replay']) equal(labelClaims[key], false)
    const samples = array(training.samples).map(object)
    ensure(samples.length > 0, 'training_samples_required')
    const groupOwners = new Map<string, unknown>(); const caseIds = new Set<string>(); const physicalIds = new Set<string>(); const sampleHashes = new Set<string>()
    for (const sample of samples) {
      for (const key of ['case_id', 'project_id', 'geometry_family_id', 'load_history_id']) {
        const value = string(sample[key]); ensure(ID.test(value), 'training_stable_identity')
        if (key !== 'case_id') { const group = `${key}:${value}`; if (groupOwners.has(group)) equal(groupOwners.get(group), sample.split); else groupOwners.set(group, sample.split) }
      }
      const caseId = string(sample.case_id); const physicalId = hash(sample.model_identity_hash); const sampleHash = hash(sample.sample_hash)
      ensure(!caseIds.has(caseId) && !physicalIds.has(physicalId) && !sampleHashes.has(sampleHash), 'duplicate_training_identity')
      caseIds.add(caseId); physicalIds.add(physicalId); sampleHashes.add(sampleHash)
      hash(sample.context_hash); if (sample.split === 'train') equal(sample.context_hash, policy.context_hash)
      validateHistoryTrainingSample(sample, training)
    }
    equal(array(training.cases).length, samples.length)
    same([...new Set(samples.map(sample => sample.split))].sort(), ['holdout', 'train', 'validation'])
    ensure(samples.filter(sample => sample.split === 'train').length >= 2, 'training_membership')
    same(array(policy.training_sample_hashes).map(hash), samples.filter(sample => sample.split === 'train').map(sample => hash(sample.sample_hash)).sort())
  } else {
    equal(training.schema_version, 'fiber-frame-candidate-learning.v2'); equal(policy.schema_version, 'fiber-frame-candidate-ridge-policy.v2')
    ensure(training.target_profile === undefined && training.targets === undefined && policy.target_profile === undefined, 'unbound_training_target_profile')
    array(training.samples).map(object).forEach(sample => ensure(sample.target_profile === undefined && sample.history_label_source === undefined, 'unbound_sample_target_profile'))
  }
  for (const strategy of STRATEGIES) {
    const saved = object(plans[strategy]); const pool = array(saved.candidate_pool, 64).map(object)
    pool.forEach(row => validateCandidatePredictionRow(row, input, strategy === 'learned'))
    if (!historyProfile) continue
    const plan = exact(saved.frozen_plan, ['strategy', 'input_binding_hash', 'ranking', 'shortlist', 'policy_artifact_hash', 'pool_hash'])
    equal(plan.strategy, strategy); equal(plan.policy_artifact_hash, input.policy_artifact_hash); hash(plan.input_binding_hash); hash(plan.pool_hash)
    const valid = pool.filter(row => row.screening_status === 'ready'); const costOrder = (a: CandidateObject, b: CandidateObject) => nonnegative(a.preanalysis_material_estimate) - nonnegative(b.preanalysis_material_estimate) || (string(a.candidate_id) < string(b.candidate_id) ? -1 : a.candidate_id === b.candidate_id ? 0 : 1)
    const budget = natural(input.full_analysis_budget) - 1; const explore = natural(input.exploration_slots)
    let ranked: CandidateObject[], selected: CandidateObject[]
    if (strategy === 'oracle') { ranked = pool; selected = pool.filter(row => row.model_checksum !== null) }
    else if (strategy === 'deterministic') { ranked = [...valid].sort(costOrder); selected = ranked.slice(0, budget) }
    else {
      const priority = (row: CandidateObject) => row.predicted_requested_limits_safe === true ? 0 : row.predicted_requested_limits_safe === null ? 1 : 2
      ranked = [...valid].sort((a, b) => priority(a) - priority(b) || costOrder(a, b)); selected = ranked.slice(0, Math.max(0, budget - explore))
      const remaining = valid.filter(row => !selected.includes(row)).sort((a, b) => Number(b.predicted_requested_limits_safe === null) - Number(a.predicted_requested_limits_safe === null) || Math.abs((a.predicted_requested_limit_ratio === null ? 1 : number(a.predicted_requested_limit_ratio)) - 1) - Math.abs((b.predicted_requested_limit_ratio === null ? 1 : number(b.predicted_requested_limit_ratio)) - 1) || costOrder(a, b))
      selected.push(...remaining.slice(0, Math.max(0, budget - selected.length)))
    }
    same(plan.ranking, ranked.map(row => row.candidate_id)); same(plan.shortlist, selected.map(row => row.candidate_id))
  }
}

function validateWorker(run: CandidateObject, declared: CandidateObject, frozenRequest: CandidateObject, manifest: CandidateProcessManifest, artifacts: Map<string, CandidateLoadedArtifact>, previous: CandidateObject[]): void {
  const input = object(declared.input_binding); const strategy = string(run.strategy); const plans = object(declared.plans); const expected = object(plans[strategy])
  const material = input.material_history_limits !== undefined
  boolean(run.attempted); boolean(run.report_contract_pass); boolean(run.resource_contract_pass)
  natural(run.parent_slot_observed_wall_ns); natural(run.parent_slot_cpu_time_ns); equal(run.slot_wall_includes_worker_launch_and_parent_validation, true)
  const failure = exact(run.failure, ['report', 'resources'])
  for (const axis of ['report', 'resources']) { if (failure[axis] !== null) string(failure[axis]) }
  if (run.report_contract_pass) equal(failure.report, null)
  if (run.resource_contract_pass) equal(failure.resources, null)
  if (!run.attempted) { equal(run.report_contract_pass, false); equal(run.resource_contract_pass, false); equal(run.report, null); equal(run.resources, null); equal(run.manifest, null); ensure(run.request_identity === undefined, 'unlaunched_request_identity'); return }
  {
    sourceIdentity(run.request_identity, manifest); equal(object(run.request_identity).path, run.request_file)
    const request = exact(sourceArtifact(run.request_file, artifacts).value, ['schema_version', 'strategy', 'case', 'expected_inputs', 'expected_plan_hash', 'online_completion_hashes'])
    equal(request.schema_version, material ? 'rc-fiber-candidate-process-worker-request.v2' : 'rc-fiber-candidate-process-worker-request.v1'); equal(request.strategy, strategy)
    same(request.case, frozenRequest)
    const expectedInputs = [frozenRequest.model_file, frozenRequest.training_file].map(path => {
      const entry = manifest.artifacts.find(row => row.source_path === path); ensure(entry, 'worker_input_missing')
      return { path, byte_length: entry.byte_length, sha256: entry.sha256 }
    })
    same(request.expected_inputs, expectedInputs)
    equal(request.expected_plan_hash, expected.frozen_plan_hash)
    const completion: CandidateObject = {}
    if (strategy === 'oracle') for (const row of previous) if (row.case_id === run.case_id && row.phase === run.phase && row.repetition === run.repetition && row.report_contract_pass) completion[string(row.strategy)] = object(object(object(row.manifest).artifacts)['search.json']).sha256
    same(request.online_completion_hashes, completion)
    if (strategy === 'oracle') same(Object.keys(completion).sort(), ['deterministic', 'learned'])
  }
  if (run.manifest !== null) {
    const worker = exact(run.manifest, ['schema_version', 'source_revision', 'status', 'worker_pid', 'parent_pid', 'worker_exit_code', 'fresh_python_process', 'launch_to_exit_wall_ns', 'parent_orchestration_cpu_time_ns', 'parent_cpu_scope', 'launch_scope', 'artifacts', 'worker_measurements_available', 'worker_resource_validation_failure', 'source_revision_is_attestation', 'independent_validation']); same(sourceArtifact(string(run.worker_directory) + '/manifest.json', artifacts).value, worker)
    equal(worker.schema_version, 'rc-fiber-candidate-search-process-manifest.v1'); equal(worker.source_revision, manifest.source_revision)
    ensure(natural(worker.worker_pid) > 0 && natural(worker.parent_pid) > 0 && worker.worker_pid !== worker.parent_pid, 'worker_not_fresh'); equal(worker.fresh_python_process, true)
    ensure(Number.isSafeInteger(number(worker.worker_exit_code)), 'exit_code'); ensure(['ready', 'blocked', 'timeout'].includes(string(worker.status)), 'worker_status')
    equal(worker.parent_cpu_scope, 'launch_wait_and_artifact_validation_before_manifest_emission'); equal(worker.launch_scope, 'spawn_imports_inputs_search_and_worker_persistence_excluding_manifest_emission')
    equal(worker.worker_resource_validation_failure === null, boolean(worker.worker_measurements_available))
    if (worker.status === 'timeout') { equal(run.report_contract_pass, false); equal(run.resource_contract_pass, false) }
    equal(worker.source_revision_is_attestation, false); equal(worker.independent_validation, false)
    ensure(natural(worker.launch_to_exit_wall_ns) <= natural(run.parent_slot_observed_wall_ns), 'slot_wall_scope')
    natural(worker.parent_orchestration_cpu_time_ns)
    for (const [name, identity] of Object.entries(object(worker.artifacts))) {
      ensure(['search.json', 'resources.json', 'failure.json'].includes(name), 'worker_artifact_name')
      const ref = manifest.artifacts.find(item => item.source_path === string(run.worker_directory) + '/' + name); ensure(ref, 'missing_worker_artifact')
      same(identity, { sha256: ref.sha256, byte_length: ref.byte_length })
    }
  }
  if (run.report_contract_pass) {
    const worker = object(run.manifest)
    const searchArtifact = manifest.artifacts.find(item => item.source_path === string(run.worker_directory) + '/search.json'); ensure(searchArtifact, 'report_artifact_missing')
    same(object(worker.artifacts)['search.json'], { sha256: searchArtifact.sha256, byte_length: searchArtifact.byte_length })
    const report = object(run.report); same(sourceArtifact(string(run.worker_directory) + '/search.json', artifacts).value, report)
    if (historyPredictionProfile(input)) equal(report.candidate_target_profile, CANDIDATE_HISTORY_TARGET_PROFILE)
    else ensure(report.candidate_target_profile === undefined, 'unrequested_report_target_profile')
    equal(report.schema_version, strategy === 'oracle' ? material ? 'fiber-frame-candidate-search-oracle.v2' : 'fiber-frame-candidate-search-oracle.v1' : material ? 'fiber-frame-candidate-search-arm.v2' : 'fiber-frame-candidate-search-arm.v1')
    equal(report.strategy, strategy); equal(report.report_contract_pass, true); hash(report.report_hash)
    same(report.input_binding, input); same(report.frozen_plan, expected.frozen_plan); equal(report.frozen_plan_hash, expected.frozen_plan_hash); same(report.candidate_pool, expected.candidate_pool)
    const pool = array(report.candidate_pool, 64).map(object); const plan = object(report.frozen_plan); const shortlist = array(plan.shortlist, 64).map(string)
    same(plan.strategy, strategy); equal(plan.policy_artifact_hash, input.policy_artifact_hash); hash(plan.input_binding_hash); hash(plan.pool_hash)
    ensure(new Set(shortlist).size === shortlist.length && shortlist.every(id => pool.some(row => row.candidate_id === id)), 'shortlist_coverage')
    const rows = outcomes(report); same(rows.map(row => row.candidate_id), ['baseline', ...pool.map(row => row.candidate_id)])
    const c = counts(report); const cost = object(report.cost_accounting)
    for (const row of rows) {
      boolean(row.full_reference_verification_pass)
      if (!row.analysis_requested) { equal(row.result, null); equal(row.full_reference_verification_pass, false); ensure((strategy === 'oracle' ? ['unavailable_model'] : ['not_shortlisted', 'preanalysis_blocked']).includes(string(row.status)), 'unrequested_status') }
      else if (row.result !== null) {
        const actual = object(row.result); const actualSolver = boolean(object(actual.metrics).solver_executed)
        const executionFailed = Boolean(object(actual.contract_bindings).problem_contract_hash) && array(actual.unsupported_features).some(value => object(value).kind === 'rc_fiber_frame_execution_failed')
        equal(row.solver_executed, executionFailed ? null : actualSolver)
        if (row.full_reference_verification_pass) { equal(actual.status, 'ready'); equal(actualSolver, true) }
      } else equal(row.full_reference_verification_pass, false)
      if (material && row.analysis_requested) validateDesignMaterialHistoryScopes(row, input.history_limits, input.material_history_limits, object(input.configuration))
      if (!material) {
        for (const key of ['constitutive_history', 'full_material_history_verification_pass', 'material_history_limit_status', 'violated_material_history_limits', 'material_history_failure']) ensure(row[key] === undefined, 'unrequested_material_row_field')
        if (row.performance !== null && row.performance !== undefined) for (const key of ['history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage', 'history_maximum_concrete_compressive_damage']) ensure(object(row.performance)[key] === undefined, 'unrequested_material_metric')
      }
    }
    equal(cost.training_execution_count, 0); equal(cost.data_collection_execution_count, 0); equal(cost.historical_costs_charged_here, false)
    equal(cost.workload_scope, WORKLOAD_SCOPE); equal(cost.historical_cost_scope, 'identity_bound_prior_generation_and_fit_charged_once_by_parent_per_training_report_hash'); same(cost.historical_training_cost_accounting, input.training_cost_accounting)
    for (const key of ['actual_workload_wall_ns', 'training_artifact_validation_wall_ns', 'pool_preparation_wall_ns', 'inference_count']) natural(cost[key])
    claims(report.claims, ['all_declared_candidates_retained', 'fresh_baseline_in_each_execution'], ['confirmed_construction_savings', 'design_code_compliance', 'generalized_speedup_claimed', 'independent_validation', 'oracle_labels_available_to_online_selection', 'predictor_history_safety_authority', 'production_promotion_eligible', 'source_revision_is_attestation', 'training_reexecuted'])
    const charged = strategy === 'oracle' ? cost : object(object(report.arm).cost_accounting)
    equal(charged.baseline_analysis_request_count, 1); equal(charged.candidate_analysis_request_count, shortlist.length); equal(charged.total_analysis_request_count, c.requested); equal(charged.known_solver_execution_count, c.known); equal(charged.unknown_solver_execution_count, c.unknown)
    equal(c.requested, shortlist.length + 1); ensure(strategy === 'oracle' || c.requested <= natural(input.full_analysis_budget), 'analysis_budget')
    same(rows.filter(row => row.analysis_requested).map(row => row.candidate_id).sort(), ['baseline', ...shortlist].sort())
    if (strategy !== 'oracle') {
      const arm = object(report.arm); equal(arm.strategy, strategy); same(arm.shortlist, shortlist); same(arm.ranking, plan.ranking); equal(arm.frozen_shortlist_hash, report.frozen_plan_hash)
      const components = ['shared_pool_preparation_charged_wall_ns', 'inference_wall_ns', 'shortlist_selection_wall_ns', 'final_selection_wall_ns', 'policy_setup_wall_ns', 'full_reanalysis_wall_ns']
      equal(charged.charged_online_wall_ns, sum(components.map(key => natural(charged[key])))); ensure(natural(charged.charged_online_wall_ns) <= natural(cost.actual_workload_wall_ns), 'online_workload_scope')
      equal(charged.policy_setup_wall_ns, cost.training_artifact_validation_wall_ns); equal(charged.shared_pool_preparation_charged_wall_ns, cost.pool_preparation_wall_ns); equal(charged.inference_count, cost.inference_count)
      const selected = arm.final_selection === null ? null : object(arm.final_selection)
      if (selected) { const row = rows.find(item => item.candidate_id === selected.candidate_id); ensure(row, 'selected_candidate_missing'); same(selected, row); equal(selected.full_reference_verification_pass, true); equal(selected.terminal_limit_status, 'pass'); if (input.history_limits !== undefined) { equal(selected.full_history_verification_pass, true); equal(selected.history_limit_status, 'pass') } if (material) { equal(selected.full_material_history_verification_pass, true); equal(selected.material_history_limit_status, 'pass') } }
      equal(report.status, selected ? 'ready' : 'blocked')
    } else {
      equal(report.status, rows.every(row => row.full_reference_verification_pass === true && row.full_history_verification_pass !== false && (!material || row.full_material_history_verification_pass === true)) ? 'ready' : 'blocked')
      ensure(sum(['training_artifact_validation_wall_ns', 'pool_preparation_wall_ns', 'plan_selection_wall_ns', 'full_reanalysis_wall_ns'].map(key => natural(cost[key]))) <= natural(cost.actual_workload_wall_ns), 'oracle_workload_scope')
    }
    ensure(sum(rows.filter(row => row.analysis_requested).map(row => natural(row.reference_and_quantity_wall_ns))) <= natural(charged.full_reanalysis_wall_ns), 'reference_reanalysis_subset')
  } else equal(run.report, null)
  if (run.resource_contract_pass) {
    const resources = exact(run.resources, ['schema_version', 'source_revision', 'strategy', 'worker_pid', 'status', 'measurement_contract_pass', 'cpu_process_time_ns', 'workload_cpu_process_time_ns', 'workload_wall_ns', 'worker_observed_wall_ns', 'inputs', 'input_bytes_read', 'input_read_wall_ns', 'input_io_scope', 'report_bytes_written', 'report_encode_wall_ns', 'report_write_flush_fsync_wall_ns', 'search_sha256', 'search_byte_length', 'peak_memory_bytes', 'per_strategy_peak_memory_bytes', 'peak_memory_scope_or_reason', 'per_strategy_peak_memory_reason', 'process_cpu_scope', 'workload_scope', 'resource_sidecar_io_included', 'gpu_time_ns', 'gpu_time_reason', 'generalized_speedup_claimed', 'independent_hardware_validation', 'source_revision_is_attestation']); const worker = object(run.manifest); same(sourceArtifact(string(run.worker_directory) + '/resources.json', artifacts).value, resources)
    equal(resources.schema_version, 'rc-fiber-candidate-search-process-resources.v1'); equal(resources.source_revision, manifest.source_revision); equal(resources.strategy, strategy); equal(resources.worker_pid, worker.worker_pid)
    for (const key of ['cpu_process_time_ns', 'workload_cpu_process_time_ns', 'workload_wall_ns', 'worker_observed_wall_ns', 'input_bytes_read', 'input_read_wall_ns', 'report_bytes_written', 'report_encode_wall_ns', 'report_write_flush_fsync_wall_ns']) natural(resources[key])
    ensure(natural(resources.workload_cpu_process_time_ns) <= natural(resources.cpu_process_time_ns) && natural(resources.workload_wall_ns) <= natural(resources.worker_observed_wall_ns) && natural(resources.worker_observed_wall_ns) <= natural(worker.launch_to_exit_wall_ns), 'resource_interval_scope')
    ensure(sum(['input_read_wall_ns', 'workload_wall_ns', 'report_encode_wall_ns', 'report_write_flush_fsync_wall_ns'].map(key => natural(resources[key]))) <= natural(resources.worker_observed_wall_ns), 'worker_interval_subtotals')
    equal(resources.status, boolean(resources.measurement_contract_pass) ? 'ready' : 'blocked'); equal(worker.worker_measurements_available, true)
    equal(worker.status, worker.worker_exit_code === 0 && resources.measurement_contract_pass ? 'ready' : 'blocked')
    equal(resources.process_cpu_scope, 'worker_process_lifetime_through_search_persistence_excluding_resource_sidecar_emission'); equal(resources.workload_scope, 'one_candidate_search_arm_or_later_oracle_including_own_preparation_ranking_full_reanalysis_and_selection')
    equal(resources.resource_sidecar_io_included, false); equal(resources.source_revision_is_attestation, false); equal(resources.independent_hardware_validation, false); equal(resources.generalized_speedup_claimed, false); equal(resources.gpu_time_ns, null)
    equal(resources.input_io_scope, 'bounded_file_reads_only_excluding_decode_parse_and_hashing')
    equal(resources.per_strategy_peak_memory_bytes, resources.peak_memory_bytes)
    if (resources.peak_memory_bytes !== null) { ensure(natural(resources.peak_memory_bytes) > 0, 'peak_memory'); equal(resources.peak_memory_scope_or_reason, 'linux_proc_vmhwm_post_exec_address_space_including_interpreter_imports_and_report_encoding') }
    else ensure(['post_exec_process_peak_rss_not_supported_on_this_platform', 'post_exec_process_peak_rss_unavailable'].includes(string(resources.peak_memory_scope_or_reason)), 'missing_peak_reason')
    equal(resources.gpu_time_reason, 'cpu_only_solver_path')
    equal(resources.per_strategy_peak_memory_reason, 'one_candidate_search_arm_or_oracle_per_fresh_worker_including_inputs_imports_ranking_verification_and_report_persistence')
    const inputs = array(resources.inputs, 3).map(row => exact(row, ['path', 'sha256', 'byte_length', 'read_wall_ns'])); inputs.forEach(row => sourceIdentity(row, manifest)); equal(resources.input_bytes_read, sum(inputs.map(row => natural(row.byte_length)))); equal(resources.input_read_wall_ns, sum(inputs.map(row => natural(row.read_wall_ns))))
    const expectedPaths = [run.request_file, frozenRequest.model_file, frozenRequest.training_file]
    same(inputs.map(row => row.path), expectedPaths)
    const searchIdentity = object(object(worker.artifacts)['search.json']); equal(resources.search_sha256, searchIdentity.sha256); equal(resources.search_byte_length, searchIdentity.byte_length); equal(resources.report_bytes_written, searchIdentity.byte_length)
    if (run.report_contract_pass) {
      equal(resources.status, 'ready'); equal(resources.measurement_contract_pass, true)
      const search = object(object(worker.artifacts)['search.json']); equal(resources.search_sha256, search.sha256); equal(resources.search_byte_length, search.byte_length); equal(resources.report_bytes_written, search.byte_length)
      ensure(natural(object(object(run.report).cost_accounting).actual_workload_wall_ns) <= natural(resources.workload_wall_ns), 'report_workload_scope')
    }
  } else equal(run.resources, null)
}

export function recomputeCandidatePredictionAudit(pool: CandidateObject[], shortlist: string[], oracle: CandidateObject[] | null, history: boolean, deterministic: boolean, material: boolean): CandidateObject {
  ensure(!material || history, 'material_audit_requires_history')
  const combinedProfile = pool.some(row => Object.prototype.hasOwnProperty.call(row, 'predicted_requested_limits_safe'))
  const combinedFalse: string[] = []; const combinedUnknown: string[] = []; const extra: CandidateObject = {}
  if (combinedProfile) {
    Object.assign(extra, { combined_false_safe_count: null, combined_false_safe_candidate_ids: null, combined_predicted_safe_unverifiable_count: null, combined_predicted_safe_unverifiable_candidate_ids: null, combined_false_safe_definition: 'predicted_requested_limits_safe_but_verified_requested_limit_failure', combined_predicted_safe_unverifiable_definition: 'predicted_requested_limits_safe_without_all_requested_verification', predicted_requested_limits_safety_candidate_count: pool.filter(row => typeof row.predicted_requested_limits_safe === 'boolean').length })
    for (const [required, scope] of [[history, 'history'], [material, 'material_history']] as const) if (required) {
      const count = pool.filter(row => typeof row[`predicted_${scope}_safe`] === 'boolean').length
      extra[`predicted_${scope}_safety_available`] = count > 0; extra[`predicted_${scope}_safety_candidate_count`] = count
    }
  }
  let result: CandidateObject
  if (oracle === null) {
    result = { missed_feasible_count: null, false_safe_count: null, predicted_safe_unverifiable_count: null, oracle_verified_candidate_count: null, reason: 'exhaustive_oracle_not_run' }
    if (history) Object.assign(result, { oracle_combined_verified_candidate_count: null, oracle_combined_unverifiable_candidate_count: null, predicted_history_safety_available: false })
  } else {
    const missed: string[] = []; const falseSafe: string[] = []; const unknown: string[] = []; let known = 0; let combined = 0
    for (const candidate of pool) {
      const id = string(candidate.candidate_id); const row = oracle.find(item => item.candidate_id === id); ensure(row, 'oracle_candidate_missing')
      if (combinedProfile && candidate.predicted_requested_limits_safe === true) {
        const verified = row.full_reference_verification_pass === true && (!history || row.full_history_verification_pass === true) && (!material || row.full_material_history_verification_pass === true)
        if (!verified) combinedUnknown.push(id)
        else if (row.terminal_limit_status !== 'pass' || (history && row.history_limit_status !== 'pass') || (material && row.material_history_limit_status !== 'pass')) combinedFalse.push(id)
      }
      if (boolean(row.full_reference_verification_pass)) {
        known++; const terminal = row.terminal_limit_status === 'pass'; const verifiedHistory = (!history || row.full_history_verification_pass === true) && (!material || row.full_material_history_verification_pass === true)
        if (verifiedHistory) combined++
        if (terminal && verifiedHistory && (!history || row.history_limit_status === 'pass') && (!material || row.material_history_limit_status === 'pass') && !shortlist.includes(id)) missed.push(id)
        if (candidate.predicted_terminal_safe === true && !terminal) falseSafe.push(id)
      } else if (candidate.predicted_terminal_safe === true) unknown.push(id)
    }
    result = { missed_feasible_count: missed.length, missed_feasible_candidate_ids: missed, false_safe_count: falseSafe.length, false_safe_candidate_ids: falseSafe, predicted_safe_unverifiable_count: unknown.length, predicted_safe_unverifiable_candidate_ids: unknown, oracle_verified_candidate_count: known, oracle_unverifiable_candidate_count: pool.length - known, false_safe_definition: 'predicted_terminal_safe_but_verified_terminal_limit_failure', missed_feasible_definition: material ? 'oracle_verified_terminal_history_and_material_history_feasible_candidate_not_in_shortlist' : history ? 'oracle_verified_terminal_and_committed_history_feasible_candidate_not_in_shortlist' : 'oracle_verified_terminal_feasible_candidate_not_in_shortlist', reason: 'separate_exhaustive_oracle_with_unverifiable_cases_retained' }
    if (history) Object.assign(result, { oracle_combined_verified_candidate_count: combined, oracle_combined_unverifiable_candidate_count: pool.length - combined, predicted_history_safety_available: false })
    if (combinedProfile) Object.assign(extra, { combined_false_safe_count: combinedFalse.length, combined_false_safe_candidate_ids: combinedFalse, combined_predicted_safe_unverifiable_count: combinedUnknown.length, combined_predicted_safe_unverifiable_candidate_ids: combinedUnknown })
  }
  if (material) result.predicted_material_history_safety_available = false
  Object.assign(result, extra)
  if (deterministic) Object.assign(result, { false_safe_count: null, false_safe_candidate_ids: null, predicted_safe_unverifiable_count: null, predicted_safe_unverifiable_candidate_ids: null, false_safe_applicability: 'strategy_makes_no_predicted_safety_claim' })
  if (deterministic && combinedProfile) {
    Object.assign(result, { combined_false_safe_count: null, combined_false_safe_candidate_ids: null, combined_predicted_safe_unverifiable_count: null, combined_predicted_safe_unverifiable_candidate_ids: null, combined_false_safe_applicability: 'strategy_makes_no_predicted_safety_claim', predicted_requested_limits_safety_candidate_count: 0 })
    for (const [required, scope] of [[history, 'history'], [material, 'material_history']] as const) if (required) { result[`predicted_${scope}_safety_available`] = false; result[`predicted_${scope}_safety_candidate_count`] = 0 }
  }
  return result
}

function validateSummaries(suite: CandidateObject, cases: CandidateObject[], repetitions: number): void {
  const runs = array(suite.runs).map(object); const summaries = array(suite.case_summaries)
  equal(summaries.length, cases.length)
  cases.forEach((declared, index) => {
    const summary = object(summaries[index]); equal(summary.case_id, declared.case_id)
    const rows = runs.filter(row => row.case_id === declared.case_id); const pairs = array(summary.measured_pairs); equal(pairs.length, repetitions)
    const walls: number[] = []; const cpus: number[] = []; let allQuality = true
    for (let repetition = 0; repetition < repetitions; repetition++) {
      const group = rows.filter(row => row.phase === 'measured' && row.repetition === repetition)
      const det = group.find(row => row.strategy === 'deterministic')!; const learned = group.find(row => row.strategy === 'learned')!
      const valid = det.report_contract_pass === true && learned.report_contract_pass === true
      const resourcesValid = det.resource_contract_pass === true && learned.resource_contract_pass === true
      const detArm = det.report_contract_pass ? object(object(det.report).arm) : null; const learnedArm = learned.report_contract_pass ? object(object(learned.report).arm) : null
      const selectedD = detArm?.final_selection ? object(detArm.final_selection) : null; const selectedL = learnedArm?.final_selection ? object(learnedArm.final_selection) : null
      const quality = valid && selectedD !== null && selectedL !== null && number(object(selectedL.material_estimate).total) <= number(object(selectedD.material_estimate).total)
      allQuality &&= quality
      const difference = valid && resourcesValid ? natural(det.parent_slot_observed_wall_ns) - natural(learned.parent_slot_observed_wall_ns) : null
      if (difference !== null) { walls.push(difference); cpus.push(natural(object(det.resources).cpu_process_time_ns) - natural(object(learned.resources).cpu_process_time_ns)) }
      const oracle = group.find(row => row.strategy === 'oracle'); const oracleRows = oracle?.report_contract_pass ? array(object(oracle.report).rows).map(object) : null
      const audits: CandidateObject = {}; const input = object(declared.input_binding)
      if (valid) for (const strategy of ['deterministic', 'learned']) audits[strategy] = recomputeCandidatePredictionAudit(array(object(object(declared.plans).learned).candidate_pool).map(object), array(object(strategy === 'deterministic' ? detArm : learnedArm).shortlist).map(string), oracleRows, input.history_limits !== undefined, strategy === 'deterministic', input.material_history_limits !== undefined)
      same(pairs[repetition], { repetition, online_reports_valid: valid, online_resources_valid: resourcesValid, learned_verified_scoped_material_cost_not_worse: quality, selected_candidate_ids: { deterministic: selectedD?.candidate_id ?? null, learned: selectedL?.candidate_id ?? null }, deterministic_minus_learned_slot_wall_ns: difference, oracle_audit: audits })
    }
    const ready = rows.filter(row => row.strategy !== 'oracle').every(row => row.report_contract_pass === true && row.resource_contract_pass === true && object(row.report).status === 'ready')
    equal(summary.all_online_attempts_ready, ready); checkDistribution(summary.paired_deterministic_minus_learned_slot_wall_ns, walls); checkDistribution(summary.paired_deterministic_minus_learned_worker_cpu_ns, cpus)
    equal(summary.comparison_scope, PAIR_SCOPE); equal(summary.projection_scope, 'conditional_positive_paired_median_for_this_case_including_slot_parent_validation_excludes_shared_preflight_and_final_aggregation'); equal(summary.break_even_is_observed_execution, false)
    const saving = walls.length === repetitions ? distribution(walls).median : null; const training = object(object(declared.input_binding).training_cost_accounting)
    const projection = ready && allQuality && saving !== null && saving > 0 ? Math.max(1, Math.ceil(sum([natural(training.data_generation_wall_ns), natural(training.training_wall_ns)]) / saving)) : null
    equal(summary.projected_reuses_to_amortize_this_training_artifact, projection)
  })
}

function validateAggregates(suite: CandidateObject, cases: CandidateObject[]): void {
  const runs = array(suite.runs).map(object); const cost = object(suite.cost_accounting); const resource = object(suite.resource_accounting)
  const historical: CandidateObject = {}
  for (const row of cases) { const input = object(row.input_binding); const key = hash(input.training_report_hash); const value = object(input.training_cost_accounting); if (historical[key]) same(historical[key], value); historical[key] = value }
  same(cost.training_artifacts_charged_once, historical)
  const historyRows = Object.values(historical).map(object)
  const generation = sum(historyRows.map(row => natural(row.data_generation_wall_ns))); const fit = sum(historyRows.map(row => natural(row.training_wall_ns))); const historicalRequests = sum(historyRows.map(row => natural(row.full_analysis_request_count)))
  equal(cost.historical_data_generation_wall_ns, generation); equal(cost.historical_training_wall_ns, fit); equal(cost.historical_training_analysis_request_count, historicalRequests)
  equal(cost.historical_training_cost_scope, 'one_generation_and_fit_per_distinct_training_report_hash'); equal(cost.historical_cpu_time_ns, null); equal(cost.historical_cpu_reason, 'frozen_training_report_contains_wall_costs_only')
  const totals: (number | null)[] = []
  exact(cost.phases, [...PHASES])
  for (const phase of PHASES) {
    const rows = runs.filter(row => row.phase === phase); const valid = rows.filter(row => row.report_contract_pass); const allCounts = valid.map(row => counts(object(row.report)))
    const total = rows.every(row => !row.attempted || row.report_contract_pass) ? sum(allCounts.map(row => row.requested)) : null; totals.push(total)
    same(object(cost.phases)[phase], { declared_worker_slots: rows.length, attempted_worker_slots: rows.filter(row => row.attempted).length, validated_report_count: valid.length, unknown_request_slots: rows.filter(row => row.attempted && !row.report_contract_pass).length, not_launched_slots: rows.filter(row => !row.attempted).length, validated_online_request_subtotal: sum(valid.filter(row => row.strategy !== 'oracle').map(row => counts(object(row.report)).requested)), validated_oracle_request_subtotal: sum(valid.filter(row => row.strategy === 'oracle').map(row => counts(object(row.report)).requested)), total_analysis_request_count: total, known_solver_execution_subtotal: sum(allCounts.map(row => row.known)), unknown_solver_execution_subtotal: sum(allCounts.map(row => row.unknown)) })
  }
  const total = totals.every(row => row !== null) ? sum(totals as number[]) : null
  equal(cost.current_analysis_request_count, total); equal(cost.total_analysis_request_count_including_training_warmups_and_oracles, total === null ? null : sum([historicalRequests, total]))
  const observed = runs.filter(row => row.resource_contract_pass); const cpu = sum(observed.map(row => natural(object(row.resources).cpu_process_time_ns)))
  equal(resource.validated_resource_worker_count, observed.length); equal(resource.worker_cpu_process_time_ns_subtotal, cpu)
  const completeCPU = runs.every(row => !row.attempted || row.resource_contract_pass) ? cpu : null
  equal(resource.worker_cpu_process_time_ns, completeCPU)
  const parentCPU = natural(resource.parent_cpu_time_ns); const parentWall = natural(resource.parent_wall_ns)
  ensure(sum(runs.map(row => natural(row.parent_slot_cpu_time_ns))) + natural(resource.parent_preflight_cpu_ns) <= parentCPU, 'parent_cpu_subset')
  ensure(sum(runs.map(row => natural(row.parent_slot_observed_wall_ns))) + natural(resource.parent_preflight_wall_ns) <= parentWall, 'parent_wall_subset')
  equal(resource.current_parent_plus_workers_cpu_time_ns, completeCPU === null ? null : sum([parentCPU, completeCPU]))
  equal(cost.current_parent_wall_ns_through_aggregation, parentWall); equal(cost.accounted_wall_ns_including_historical_generation_and_fit, sum([parentWall, generation, fit]))
  equal(resource.cpu_scopes_are_disjoint_parent_and_workers, true); equal(resource.parent_preflight_is_subset, true); equal(resource.parent_scope, PARENT_SCOPE)
  equal(resource.parent_peak_memory_bytes, null); equal(resource.parent_peak_memory_reason, 'coordinator_not_a_fresh_measured_address_space')
  equal(resource.resource_io_scope, 'worker_input_file_reads_and_search_report_encode_flush_fsync_only_sidecars_manifests_and_parent_suite_persistence_excluded'); equal(resource.peak_memory_aggregation, 'distribution_of_separate_process_peaks_never_sum_or_subtract'); equal(resource.gpu_time_ns, null); equal(resource.gpu_time_reason, 'cpu_only_solver_path')
  const byStrategy = exact(resource.workers_by_strategy, [...STRATEGIES])
  for (const strategy of STRATEGIES) {
    const phases = exact(byStrategy[strategy], [...PHASES])
    for (const phase of PHASES) {
      const row = object(phases[phase]); const matching = runs.filter(run => run.strategy === strategy && run.phase === phase); const selected = matching.filter(run => run.resource_contract_pass)
      equal(row.observed_workers, selected.length); equal(row.declared_slots, matching.length); equal(row.peak_values_are_separate_process_high_water_marks, true)
      checkDistribution(row.worker_cpu_process_time_ns, selected.map(run => natural(object(run.resources).cpu_process_time_ns))); checkDistribution(row.launch_to_exit_wall_ns, selected.map(run => natural(object(run.manifest).launch_to_exit_wall_ns)))
      checkDistribution(row.peak_memory_bytes, selected.map(run => object(run.resources).peak_memory_bytes).filter(value => value !== null).map(natural))
      for (const key of ['input_bytes_read', 'input_read_wall_ns', 'report_bytes_written', 'report_write_flush_fsync_wall_ns']) equal(row[key], sum(selected.map(run => natural(object(run.resources)[key]))))
    }
  }
}

/** Validate stored producer contracts. Hash equality links identities; it is not a provenance attestation or a new solver execution. */
export function validateCandidateProcessReview(value: unknown, manifest: CandidateProcessManifest, artifacts: Map<string, CandidateLoadedArtifact>, comparisons: Map<string, CandidateLoadedComparison>): { suite: CandidateProcessSuite; slots: CandidateProcessSlot[] } {
  finiteTree(value)
  const suite = exact(value, ['schema_version', 'status', 'declaration', 'report_hash', 'suite_identity_hash', 'runs', 'case_summaries', 'cost_accounting', 'resource_accounting', 'claims'])
  equal(hash(suite.report_hash), manifest.suite_report_hash); equal(hash(suite.suite_identity_hash), manifest.suite_identity_hash)
  const declaration = exact(suite.declaration, ['source_revision', 'configuration', 'cases', 'inputs', 'execution_schedule', 'parent_plans_frozen_before_first_worker'])
  equal(declaration.source_revision, manifest.source_revision); equal(declaration.execution_schedule, SCHEDULE); equal(declaration.parent_plans_frozen_before_first_worker, true)
  const config = exact(declaration.configuration, ['repetitions', 'warmups', 'oracle_audit']); const repetitions = natural(config.repetitions); const warmups = natural(config.warmups); const oracleEnabled = boolean(config.oracle_audit)
  ensure(repetitions >= 2 && repetitions <= 32 && repetitions % 2 === 0 && warmups <= 5, 'configuration_bounds')
  const cases = array(declaration.cases, 64).map(object); ensure(cases.length > 0 && new Set(cases.map(row => row.case_id)).size === cases.length, 'case_coverage')
  const material = cases.some(row => object(row.input_binding).material_history_limits !== undefined)
  equal(suite.schema_version, material ? 'rc-fiber-candidate-process-suite.v2' : 'rc-fiber-candidate-process-suite.v1')
  equal(manifest.schema_version, material ? 'rc-fiber-candidate-process-review-bundle.v2' : 'rc-fiber-candidate-process-review-bundle.v1')
  const inputs = array(declaration.inputs).map(object); inputs.forEach(row => sourceIdentity(row, manifest)); equal(inputs.length, cases.length * 2 + 2)
  const originalRequest = exact(sourceArtifact(inputs[0].path, artifacts).value, ['schema_version', 'cases', 'repetitions', 'warmups', 'oracle_audit'])
  equal(originalRequest.schema_version, material ? 'rc-fiber-candidate-process-suite-request.v2' : 'rc-fiber-candidate-process-suite-request.v1')
  for (const key of ['repetitions', 'warmups', 'oracle_audit']) equal(originalRequest[key], config[key])
  const originalCases = array(originalRequest.cases).map(object); equal(originalCases.length, cases.length)
  const frozen = object(sourceArtifact(inputs[inputs.length - 1].path, artifacts).value)
  same(frozen.configuration, config); equal(frozen.source_revision, manifest.source_revision); same(frozen.identities, inputs.slice(0, -1))
  const frozenCases = array(frozen.cases).map(object); equal(frozenCases.length, cases.length)
  cases.forEach((row, index) => {
    ensure(ID.test(string(row.case_id)), 'case_id'); exact(row, ['case_id', 'input_binding', 'plans']); exact(row.plans, [...STRATEGIES])
    const input = object(row.input_binding); equal(input.source_revision, manifest.source_revision)
    for (const key of ['baseline_model_checksum', 'policy_artifact_hash', 'training_report_hash']) hash(input[key])
    const bindingBudget = natural(input.full_analysis_budget); ensure(bindingBudget >= 2 && bindingBudget <= 65 && natural(input.exploration_slots) < bindingBudget, 'budget_bounds')
    const saved = frozenCases[index]; equal(saved.case_id, row.case_id); const expectations = object(saved.expectations); same(expectations.input_binding, input)
    for (const strategy of STRATEGIES) same(expectations[strategy], object(row.plans)[strategy])
    const request = object(saved.request); equal(request.case_id, row.case_id); equal(request.model_file, inputs[1 + index * 2].path); equal(request.training_file, inputs[2 + index * 2].path)
    const original = { ...originalCases[index] }; const frozenCase = { ...request }
    for (const key of ['model_file', 'training_file']) { string(original[key]); delete original[key]; delete frozenCase[key] }
    same(original, frozenCase)
    for (const key of ['configuration', 'full_analysis_budget', 'exploration_slots', 'terminal_limits']) same(request[key], input[key])
    same(request.history_limits, input.history_limits ?? null); const prices = { ...object(input.price_basis) }; delete prices.price_table_hash; same(request.prices, prices)
    if (input.material_history_limits !== undefined) {
      validateMaterialHistoryLimits(input.material_history_limits)
      object(input.history_limits)
      same(request.material_history_limits, input.material_history_limits)
    } else ensure(request.material_history_limits === undefined, 'unrequested_material_scope')
    same(request.candidates, array(input.candidates).map(candidate => { const c = object(candidate); return { candidate_id: c.candidate_id, changes: c.changes } }))
    const training = object(sourceArtifact(request.training_file, artifacts).value); equal(training.report_hash, input.training_report_hash); equal(object(training.policy).artifact_hash, input.policy_artifact_hash)
    validateCandidatePredictionPlans(input, training, object(row.plans))
    const trainingCosts = object(training.cost_accounting); for (const key of ['data_generation_wall_ns', 'training_wall_ns', 'full_analysis_request_count']) equal(object(input.training_cost_accounting)[key], trainingCosts[key])
  })
  same(frozen.training_artifacts, object(suite.cost_accounting).training_artifacts_charged_once)
  const runs = array(suite.runs).map(object); const expected: CandidateObject[] = []
  for (const phase of PHASES) for (let repetition = 0; repetition < (phase === 'warmup' ? warmups : repetitions); repetition++) cases.forEach((row, index) => {
    const order = (repetition + index) % 2 === 0 ? ['deterministic', 'learned'] : ['learned', 'deterministic']
    for (const strategy of [...order, ...(oracleEnabled ? ['oracle'] : [])]) expected.push({ case_id: row.case_id, phase, repetition, strategy, execution_order: order })
  })
  equal(runs.length, expected.length); const pids = new Set<number>(); const slots: CandidateProcessSlot[] = []; const covered = new Set<string>()
  runs.forEach((run, index) => {
    for (const key of ['case_id', 'phase', 'repetition', 'strategy', 'execution_order']) same(run[key], expected[index][key])
    const declared = cases.find(row => row.case_id === run.case_id)!; const frozenRequest = object(frozenCases[cases.indexOf(declared)].request)
    validateWorker(run, declared, frozenRequest, manifest, artifacts, runs.slice(0, index))
    if (run.manifest !== null) { const pid = natural(object(run.manifest).worker_pid); ensure(!pids.has(pid), 'duplicate_worker_pid'); pids.add(pid) }
    const key = candidateProcessSlotKey(string(run.case_id), string(run.phase), natural(run.repetition), string(run.strategy))
    const loaded = comparisons.get(key); const entry = manifest.comparisons.find(row => candidateProcessSlotKey(row.case_id, row.phase, row.repetition, row.strategy) === key)
    const arm = run.report_contract_pass && run.strategy !== 'oracle' ? object(object(run.report).arm) : null
    if (arm && arm.design_comparison !== null) {
      ensure(loaded && entry, 'comparison_coverage'); covered.add(key); equal(entry.worker_report_hash, object(run.report).report_hash)
      const report = validateDesignComparisonReport(loaded.bundle.report, loaded.bundle.manifest); same(report, arm.design_comparison)
      const input = object(declared.input_binding)
      equal(report.schema_version, input.material_history_limits !== undefined ? 'public-rc-fiber-design-comparison.v3' : input.history_limits !== undefined ? 'public-rc-fiber-design-comparison.v2' : 'public-rc-fiber-design-comparison.v1')
      if (input.material_history_limits !== undefined) same(report.identity.material_history_limits, input.material_history_limits)
      equal(loaded.bundle.manifest.source_revision, manifest.source_revision)
      const requested = outcomes(object(run.report)).filter(row => row.analysis_requested).map(row => { const detached = { ...row }; delete detached.analysis_requested; return detached })
      same(report.rows, requested); equal(report.selection.candidate_id, arm.final_selection === null ? null : object(arm.final_selection).candidate_id)
      const count = counts(object(run.report)); const runtime = object(report.runtime)
      equal(runtime.reference_analysis_request_count, count.requested); equal(runtime.known_solver_execution_count, count.known); equal(runtime.unknown_solver_execution_count, count.unknown)
      ensure(natural(runtime.total_wall_ns) <= natural(object(arm.cost_accounting).full_reanalysis_wall_ns), 'comparison_reanalysis_subset')
    } else { ensure(!loaded && !entry, 'unexpected_comparison'); if (arm) { same(arm.shortlist, []); equal(arm.design_comparison_unavailable_reason, 'empty_shortlist_baseline_only') } }
    slots.push({ key, caseId: string(run.case_id), phase: run.phase as CandidateProcessPhase, repetition: natural(run.repetition), strategy: run.strategy as CandidateProcessStrategy, run: run as CandidateProcessRun, comparison: loaded?.bundle ?? null, comparisonManifestBytes: loaded?.manifestBytes ?? null, comparisonReportBytes: loaded?.reportBytes ?? null })
  })
  equal(covered.size, manifest.comparisons.length); equal(covered.size, comparisons.size)
  validateAggregates(suite, cases); validateSummaries(suite, cases, repetitions)
  const complete = runs.every(row => row.report_contract_pass === true && row.resource_contract_pass === true)
  const ready = runs.filter(row => row.strategy !== 'oracle').every(row => row.report_contract_pass === true && object(row.report).status === 'ready')
  const expectedClaims = { report_contract_pass: complete, all_declared_slots_retained: true, local_timing_evidence_eligible: complete && ready, historical_training_reexecuted: false, oracle_labels_available_to_online_selection: false, independent_case_families_verified: false, hashes_attest_provenance: false, generalized_speedup_claimed: false, confirmed_construction_savings: false, design_code_compliance: false, production_promotion_eligible: false }
  same(suite.claims, expectedClaims); equal(suite.status, complete && ready ? 'ready' : 'incomplete')
  return { suite: suite as CandidateProcessSuite, slots }
}
