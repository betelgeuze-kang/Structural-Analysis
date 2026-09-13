// Synthetic prediction/label metadata on historical transport; no learner fit or new solver evidence.
import { candidateBytes, candidateDigest, replaceCandidateArtifact, sealCandidateFixture, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { candidateProcessMaterialHistoryFixture } from './candidateProcessMaterialHistoryFixture'

export const historyProfile = 'terminal_and_committed_material_history.v1'
export const historyTargets = ['history_maximum_translation_m', 'history_maximum_absolute_fiber_strain', 'history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage', 'history_maximum_concrete_compressive_damage']
const allTargets = ['terminal_maximum_translation_m', 'terminal_maximum_absolute_fiber_strain', ...historyTargets]
const syntheticHash = (label: string) => candidateDigest(candidateBytes(`synthetic-history-prediction:${label}`))

export function readHistoryArtifact(fixture: CandidateObservedFixture, path: string): any {
  return JSON.parse(new TextDecoder().decode(fixture.files.get(fixture.manifest.artifacts.find(row => row.source_path === path)!.file)!))
}

/** Re-encode changed transport and byte accounting; Python identity labels are not authenticated here. */
export function resealHistoryPredictionFixture(fixture: CandidateObservedFixture): void {
  const suite: any = fixture.suite; const inputs = suite.declaration.inputs
  const frozen = readHistoryArtifact(fixture, inputs[inputs.length - 1].path)
  inputs.slice(0, -1).forEach((row: any, index: number) => { const entry = fixture.manifest.artifacts.find(entry => entry.source_path === row.path)!; inputs[index] = { path: row.path, byte_length: entry.byte_length, sha256: entry.sha256 } })
  frozen.identities = inputs.slice(0, -1)
  suite.declaration.cases.forEach((row: any, index: number) => { frozen.cases[index].expectations.input_binding = structuredClone(row.input_binding); for (const strategy of ['deterministic', 'learned', 'oracle']) frozen.cases[index].expectations[strategy] = structuredClone(row.plans[strategy]) })
  inputs[inputs.length - 1] = replaceCandidateArtifact(fixture, inputs[inputs.length - 1].path, frozen)
  for (const run of suite.runs) {
    const request = readHistoryArtifact(fixture, run.request_file)
    request.expected_inputs = [request.case.model_file, request.case.training_file].map((path: string) => {
      const entry = fixture.manifest.artifacts.find(row => row.source_path === path)!
      return { path, byte_length: entry.byte_length, sha256: entry.sha256 }
    })
    if (run.strategy === 'oracle') for (const strategy of ['deterministic', 'learned']) {
      const previous = suite.runs.find((row: any) => row.case_id === run.case_id && row.phase === run.phase && row.repetition === run.repetition && row.strategy === strategy)
      request.online_completion_hashes[strategy] = previous.manifest.artifacts['search.json'].sha256
    }
    run.request_identity = replaceCandidateArtifact(fixture, run.request_file, request)
    for (const row of run.resources.inputs) { const entry = fixture.manifest.artifacts.find(item => item.source_path === row.path)!; Object.assign(row, { byte_length: entry.byte_length, sha256: entry.sha256 }) }
    run.resources.input_bytes_read = run.resources.inputs.reduce((sum: number, row: any) => sum + row.byte_length, 0)
    const search = replaceCandidateArtifact(fixture, `${run.worker_directory}/search.json`, run.report)
    Object.assign(run.resources, { search_sha256: search.sha256, search_byte_length: search.byte_length, report_bytes_written: search.byte_length })
    run.manifest.artifacts['search.json'] = { sha256: search.sha256, byte_length: search.byte_length }
    const resources = replaceCandidateArtifact(fixture, `${run.worker_directory}/resources.json`, run.resources)
    run.manifest.artifacts['resources.json'] = { sha256: resources.sha256, byte_length: resources.byte_length }
    replaceCandidateArtifact(fixture, `${run.worker_directory}/manifest.json`, run.manifest)
  }
  for (const strategy of ['deterministic', 'learned', 'oracle']) for (const phase of ['warmup', 'measured']) for (const key of ['input_bytes_read', 'report_bytes_written']) suite.resource_accounting.workers_by_strategy[strategy][phase][key] = suite.runs.filter((run: any) => run.strategy === strategy && run.phase === phase && run.resource_contract_pass).reduce((sum: number, run: any) => sum + run.resources[key], 0)
  sealCandidateFixture(fixture)
}

export function candidateProcessHistoryPredictionFixture(): CandidateObservedFixture {
  const fixture = candidateProcessMaterialHistoryFixture(); const suite: any = fixture.suite
  suite.declaration.cases.forEach((declared: any, index: number) => {
    const input = declared.input_binding; input.candidate_target_profile = historyProfile
    const trainingPath = suite.declaration.inputs[2 + index * 2].path
    const training = readHistoryArtifact(fixture, trainingPath)
    training.schema_version = 'fiber-frame-candidate-learning.v3'; training.target_profile = historyProfile; training.targets = [...allTargets]
    Object.assign(training.claims, { history_labels_are_positive_committed_epoch_maxima: true, material_memory_is_current_yield_event: false, caller_limits_used_to_clip_targets: false, frozen_label_validation_is_independent_source_replay: false })
    Object.assign(training.policy, { schema_version: 'fiber-frame-candidate-ridge-policy.v3', target_profile: historyProfile, targets: [...allTargets], target_scale: [...training.policy.target_scale, 1, 1, 1, 1, 1], weights: training.policy.weights.map((row: number[]) => [...row, 0, 0, 0, 0, 0]) })
    for (const sample of training.samples) {
      const row = training.cases.find((row: any) => row.case_id === sample.case_id)
      const terminal = [...sample.targets]; sample.target_profile = historyProfile; sample.targets.push(...terminal, 0, 0, 0)
      const epochCount = row.validation.terminal_epoch
      const epochs = Array.from({ length: epochCount }, (_, offset) => ({ epoch: offset + 1, step_index: offset + 1, load_factor: (offset + 1) / epochCount, checkpoint_state_hash: syntheticHash(`${sample.case_id}:${offset + 1}`), parent_checkpoint_state_hash: syntheticHash(`${sample.case_id}:${offset}`), engineering_recovery_hash: syntheticHash(`${sample.case_id}:recovery:${offset + 1}`), targets: [terminal[0] * (offset + 1) / epochCount, terminal[1] * (offset + 1) / epochCount, 0, 0, 0] }))
      sample.history_label_source = { schema_version: 'fiber-frame-candidate-history-label-source.v1', bindings: { source_result_hash: sample.public_result_hash, canonical_model_checksum: sample.canonical_model_checksum, input_checksum: sample.input_checksum, problem_contract_hash: syntheticHash('problem'), checkpoint_chain_hash: sample.checkpoint_chain_hash, checkpoint_artifact_hash: syntheticHash('checkpoint-artifact'), checkpoint_artifact_byte_length: 1, response_history_report_hash: syntheticHash('response-history'), engineering_history_hash: syntheticHash('engineering-history') }, constitutive_history_report_hash: syntheticHash('constitutive-history'), accepted_epoch_count: epochCount, terminal_checkpoint_state_hash: epochs[epochs.length - 1].checkpoint_state_hash, epochs, source_hash: syntheticHash(`${sample.case_id}:source`) }
      row.history_label_source_hash = sample.history_label_source.source_hash; row.history_label_collection_wall_ns = 0
    }
    replaceCandidateArtifact(fixture, trainingPath, training)
    for (const strategy of ['deterministic', 'learned', 'oracle']) {
      const saved = declared.plans[strategy]
      for (const row of saved.candidate_pool) {
        Object.assign(row, { predicted_history_safe: null, predicted_material_history_safe: null, predicted_requested_limits_safe: null, predicted_requested_limit_ratio: null })
        if (strategy !== 'learned' || row.screening_status !== 'ready') continue
        const near = saved.frozen_plan.shortlist.includes(row.candidate_id) ? 0.95 : 0.3
        const terminal = ['maximum_translation_m', 'maximum_absolute_fiber_strain'].map(key => Math.min(input.terminal_limits[key], input.history_limits[key]) * 0.1)
        const history = [input.history_limits.maximum_translation_m * near, input.history_limits.maximum_absolute_fiber_strain * near, 0, 0, 0]
        row.prediction = { maximum_translation_m: terminal[0], maximum_absolute_fiber_strain: terminal[1], ood: false, reason: 'in_train_feature_range_uncalibrated', uncertainty_kind: 'uncalibrated_feature_range_indicator_not_probability', physical_result_authority: false, target_profile: historyProfile, history_prediction: Object.fromEntries(historyTargets.map((key, i) => [key, history[i]])) }
        row.predicted_terminal_safe = true; row.predicted_limit_ratio = Math.max(terminal[0] / input.terminal_limits.maximum_translation_m, terminal[1] / input.terminal_limits.maximum_absolute_fiber_strain)
        row.predicted_history_safe = true; row.predicted_material_history_safe = input.material_history_limits ? true : null; row.predicted_requested_limits_safe = true
        row.predicted_requested_limit_ratio = Math.max(row.predicted_limit_ratio, history[0] / input.history_limits.maximum_translation_m, history[1] / input.history_limits.maximum_absolute_fiber_strain)
      }
      if (strategy === 'learned') saved.frozen_plan.ranking = [...saved.candidate_pool].sort((a: any, b: any) => a.preanalysis_material_estimate - b.preanalysis_material_estimate).map((row: any) => row.candidate_id)
    }
    for (const run of suite.runs.filter((run: any) => run.case_id === declared.case_id)) {
      run.report.candidate_target_profile = historyProfile; run.report.input_binding = structuredClone(input)
      run.report.candidate_pool = structuredClone(declared.plans[run.strategy].candidate_pool); run.report.frozen_plan = structuredClone(declared.plans[run.strategy].frozen_plan)
      if (run.report.arm) run.report.arm.ranking = [...run.report.frozen_plan.ranking]
    }
    for (const pair of suite.case_summaries[index].measured_pairs) {
      const oracle = suite.runs.find((run: any) => run.case_id === declared.case_id && run.repetition === pair.repetition && run.strategy === 'oracle').report.rows
      const failures = declared.plans.learned.candidate_pool.filter((candidate: any) => oracle.find((row: any) => row.candidate_id === candidate.candidate_id).terminal_limit_status !== 'pass').map((row: any) => row.candidate_id)
      for (const strategy of ['deterministic', 'learned']) {
        const audit = pair.oracle_audit[strategy]; const deterministic = strategy === 'deterministic'; const known = deterministic ? 0 : declared.plans.learned.candidate_pool.length
        Object.assign(audit, { false_safe_count: deterministic ? null : failures.length, false_safe_candidate_ids: deterministic ? null : [...failures], combined_false_safe_count: deterministic ? null : failures.length, combined_false_safe_candidate_ids: deterministic ? null : [...failures], combined_predicted_safe_unverifiable_count: deterministic ? null : 0, combined_predicted_safe_unverifiable_candidate_ids: deterministic ? null : [], combined_false_safe_definition: 'predicted_requested_limits_safe_but_verified_requested_limit_failure', combined_predicted_safe_unverifiable_definition: 'predicted_requested_limits_safe_without_all_requested_verification', predicted_requested_limits_safety_candidate_count: known, predicted_history_safety_available: !deterministic, predicted_history_safety_candidate_count: known })
        if (input.material_history_limits) { audit.predicted_material_history_safety_available = !deterministic; audit.predicted_material_history_safety_candidate_count = known }
        if (deterministic) audit.combined_false_safe_applicability = 'strategy_makes_no_predicted_safety_claim'
      }
    }
  })
  resealHistoryPredictionFixture(fixture)
  return fixture
}
