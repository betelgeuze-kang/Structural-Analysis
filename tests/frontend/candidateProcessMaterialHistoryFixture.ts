// Synthetic material metadata on historical transport: no new physical or timing evidence.
import { candidateBytes, candidateDigest, candidateProcessObservedFixture, replaceCandidateArtifact, sealCandidateFixture, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { designMaterialHistoryComparisonFixture } from './designMaterialHistoryComparisonFixture'

const materialKeys = ['constitutive_history', 'full_material_history_verification_pass', 'material_history_limit_status', 'violated_material_history_limits', 'material_history_failure']
const limits = { maximum_steel_accumulated_plastic_strain: 0, maximum_concrete_tensile_damage: 0, maximum_concrete_compressive_damage: 0 }

function addMaterialRow(row: any, source: any): void {
  if (!row.analysis_requested && row.analysis_requested !== undefined) return
  if (!row.full_history_verification_pass) {
    Object.assign(row, { constitutive_history: null, full_material_history_verification_pass: false, material_history_limit_status: 'unavailable', violated_material_history_limits: [], material_history_failure: { kind: 'response_history_verification_unavailable' } })
    return
  }
  const response = row.response_history; const history = response.history; const fibers = row.result.fiber_results
  const states = [null, ...history.steps].map((step: any, epoch: number) => {
    const materials = structuredClone(source.states[0].materials)
    for (const [kind, material] of Object.entries(materials) as [string, any][]) {
      const indices = fibers.map((fiber: any, index: number) => fiber.material_kind === kind ? index : -1).filter((index: number) => index >= 0)
      material.point_count = indices.length
      for (const [name, stats] of Object.entries(material.fields) as [string, any][]) {
        const density = name === 'dissipated_energy_density_mj_per_m3'
        const values = indices.map((index: number) => density && step ? step.fiber_results[index].dissipated_energy_density_MJ_per_m3 : 0)
        const previous = indices.map((index: number) => density && epoch > 1 ? history.steps[epoch - 2].fiber_results[index].dissipated_energy_density_MJ_per_m3 : 0)
        Object.assign(stats, { minimum: Math.min(...values), maximum: Math.max(...values), maximum_absolute: Math.max(...values.map(Math.abs)), positive_value_point_count: values.filter((value: number) => value > 0).length, changed_from_parent_point_count: epoch ? values.filter((value: number, index: number) => value !== previous[index]).length : null, increased_from_parent_point_count: epoch ? values.filter((value: number, index: number) => value > previous[index]).length : null, decreased_from_parent_point_count: epoch ? values.filter((value: number, index: number) => value < previous[index]).length : null, parent_comparison_reason: epoch ? null : 'genesis_has_no_parent' })
      }
    }
    return { epoch, step_index: epoch, load_factor: step?.target_load_factor ?? 0, checkpoint_state_hash: step?.bindings.checkpoint_state_hash ?? history.bindings.root_checkpoint_state_hash, parent_checkpoint_state_hash: step?.bindings.parent_checkpoint_state_hash ?? null, engineering_recovery_hash: step?.recovery_hash ?? null, total_dissipated_energy_mj: step?.metrics.total_dissipated_energy_mj ?? null, engineering_recovery_reason: epoch ? null : 'genesis_has_no_engineering_recovery', material_point_count: fibers.length, materials }
  })
  Object.assign(row, { full_material_history_verification_pass: true, material_history_limit_status: 'pass', violated_material_history_limits: [], material_history_failure: null,
    constitutive_history: { ...structuredClone(source), accepted_epoch_count: history.epoch_count, states,
      bindings: { source_result_hash: row.result.result_hash, canonical_model_checksum: row.model_checksum, input_checksum: row.result.input_checksum, problem_contract_hash: row.result.contract_bindings.problem_contract_hash, checkpoint_chain_hash: row.result.checkpoint.chain_hash, checkpoint_artifact_hash: row.result.checkpoint.artifact_hash, checkpoint_artifact_byte_length: row.result.checkpoint.artifact_byte_length, response_history_report_hash: response.report_hash, engineering_history_hash: history.history_hash },
    },
  })
  Object.assign(row.performance, { history_maximum_steel_accumulated_plastic_strain: 0, history_maximum_concrete_tensile_damage: 0, history_maximum_concrete_compressive_damage: 0 })
}

/** Only the first case requests material screens: every other case retains v1. */
export function candidateProcessMaterialHistoryFixture(): CandidateObservedFixture {
  const fixture = candidateProcessObservedFixture(); const suite: any = fixture.suite
  const read = (path: string): any => JSON.parse(new TextDecoder().decode(fixture.files.get(fixture.manifest.artifacts.find(row => row.source_path === path)!.file)!))
  const inputs = suite.declaration.inputs; const cases = suite.declaration.cases
  const selectedCase = cases[0]; const source = designMaterialHistoryComparisonFixture().rows[0].constitutive_history
  selectedCase.input_binding.material_history_limits = structuredClone(limits)
  const request = read(inputs[0].path); request.schema_version = 'rc-fiber-candidate-process-suite-request.v2'; request.cases[0].material_history_limits = structuredClone(limits)
  inputs[0] = replaceCandidateArtifact(fixture, inputs[0].path, request)
  const frozen = read(inputs[inputs.length - 1].path)
  frozen.identities = inputs.slice(0, -1)
  frozen.cases[0].request.material_history_limits = structuredClone(limits)
  frozen.cases[0].expectations.input_binding = structuredClone(selectedCase.input_binding)
  inputs[inputs.length - 1] = replaceCandidateArtifact(fixture, inputs[inputs.length - 1].path, frozen)
  for (const run of suite.runs) {
    if (run.case_id !== selectedCase.case_id) continue
    const report = run.report; const oracle = run.strategy === 'oracle'
    report.schema_version = oracle ? 'fiber-frame-candidate-search-oracle.v2' : 'fiber-frame-candidate-search-arm.v2'
    report.input_binding = structuredClone(selectedCase.input_binding)
    const rows = oracle ? report.rows : [report.arm.baseline, ...report.arm.candidate_outcomes]
    rows.forEach((row: any) => addMaterialRow(row, source))
    if (!oracle) {
      const arm = report.arm
      if (arm.final_selection) arm.final_selection = structuredClone(rows.find((row: any) => row.candidate_id === arm.final_selection.candidate_id))
      const comparison = arm.design_comparison
      comparison.schema_version = comparison.identity.schema_version = 'public-rc-fiber-design-comparison.v3'
      comparison.identity.material_history_limits = structuredClone(limits)
      comparison.rows.forEach((row: any) => {
        const outcome = rows.find((item: any) => item.candidate_id === row.candidate_id)
        for (const key of materialKeys) row[key] = structuredClone(outcome[key])
        row.performance = structuredClone(outcome.performance)
      })
      comparison.selection.criterion = 'minimum_scoped_material_estimate_with_verified_terminal_history_and_material_history_limits'
      Object.assign(comparison.claims, { limits_scope: 'terminal_and_committed_history_translation_fiber_strain_and_material_memory', all_requested_material_history_verified: true, material_history_limits_are_caller_declared: true, material_memory_is_current_yield_event: false })
      const entry = fixture.manifest.comparisons.find(row => row.case_id === run.case_id && row.phase === run.phase && row.repetition === run.repetition && row.strategy === run.strategy)!
      const manifestBytes = fixture.files.get(entry.manifest_file)!; const manifest = JSON.parse(new TextDecoder().decode(manifestBytes))
      const body = candidateBytes(comparison); const comparisonFile = entry.manifest_file.replace(/manifest\.json$/, 'comparison.json')
      manifest.report_sha256 = candidateDigest(body); manifest.report_byte_length = body.length
      const encoded = candidateBytes(manifest)
      fixture.files.set(comparisonFile, body); fixture.files.set(entry.manifest_file, encoded)
      entry.manifest_byte_length = encoded.length; entry.manifest_sha256 = candidateDigest(encoded)
    }
    const workerRequest = read(run.request_file)
    workerRequest.schema_version = 'rc-fiber-candidate-process-worker-request.v2'; workerRequest.case.material_history_limits = structuredClone(limits)
    if (oracle) for (const strategy of ['deterministic', 'learned']) {
      const previous = suite.runs.find((row: any) => row.case_id === run.case_id && row.phase === run.phase && row.repetition === run.repetition && row.strategy === strategy)
      workerRequest.online_completion_hashes[strategy] = previous.manifest.artifacts['search.json'].sha256
    }
    run.request_identity = replaceCandidateArtifact(fixture, run.request_file, workerRequest)
    Object.assign(run.resources.inputs[0], run.request_identity)
    run.resources.input_bytes_read = run.resources.inputs.reduce((sum: number, row: any) => sum + row.byte_length, 0)
    const search = replaceCandidateArtifact(fixture, `${run.worker_directory}/search.json`, report)
    Object.assign(run.resources, { search_sha256: search.sha256, search_byte_length: search.byte_length, report_bytes_written: search.byte_length })
    run.manifest.artifacts['search.json'] = { sha256: search.sha256, byte_length: search.byte_length }
    const resources = replaceCandidateArtifact(fixture, `${run.worker_directory}/resources.json`, run.resources)
    run.manifest.artifacts['resources.json'] = { sha256: resources.sha256, byte_length: resources.byte_length }
    replaceCandidateArtifact(fixture, `${run.worker_directory}/manifest.json`, run.manifest)
  }
  for (const summary of suite.case_summaries) if (summary.case_id === selectedCase.case_id) for (const pair of summary.measured_pairs) for (const audit of Object.values(pair.oracle_audit) as any[]) {
    audit.predicted_material_history_safety_available = false
    audit.missed_feasible_definition = 'oracle_verified_terminal_history_and_material_history_feasible_candidate_not_in_shortlist'
  }
  for (const strategy of ['deterministic', 'learned', 'oracle']) for (const phase of ['warmup', 'measured']) {
    const runs = suite.runs.filter((run: any) => run.strategy === strategy && run.phase === phase && run.resource_contract_pass)
    for (const key of ['input_bytes_read', 'report_bytes_written']) suite.resource_accounting.workers_by_strategy[strategy][phase][key] = runs.reduce((sum: number, run: any) => sum + run.resources[key], 0)
  }
  suite.schema_version = 'rc-fiber-candidate-process-suite.v2'; fixture.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v2'
  sealCandidateFixture(fixture)
  return fixture
}
