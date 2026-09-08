// Synthetic stopping/accounting metadata on historical rows: no solver, fit or timing evidence.
// Python logical hash labels are not regenerated or authenticated by this helper.
import { candidateProcessHistoryPredictionFixture, readHistoryArtifact, resealHistoryPredictionFixture } from './candidateProcessHistoryPredictionFixture'
import { replaceCandidateArtifact, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { FIRST_VERIFIED_FEASIBLE, recomputeCandidatePredictionAudit, withCandidateUnrequestedFeasible } from '../../src/workbench-v2/model/candidateProcessSchema'

export function candidateProcessStopFixture(): CandidateObservedFixture {
  const fixture = candidateProcessHistoryPredictionFixture(); const suite: any = fixture.suite
  const declared = suite.declaration.cases[0]; const input = declared.input_binding; const inputs = suite.declaration.inputs
  input.stop_mode = FIRST_VERIFIED_FEASIBLE
  suite.schema_version = 'rc-fiber-candidate-process-suite.v3'; fixture.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v3'
  const original = readHistoryArtifact(fixture, inputs[0].path)
  original.schema_version = 'rc-fiber-candidate-process-suite-request.v3'; original.cases[0].stop_mode = FIRST_VERIFIED_FEASIBLE
  replaceCandidateArtifact(fixture, inputs[0].path, original)
  const frozen = readHistoryArtifact(fixture, inputs[inputs.length - 1].path)
  frozen.cases[0].request.stop_mode = FIRST_VERIFIED_FEASIBLE
  replaceCandidateArtifact(fixture, inputs[inputs.length - 1].path, frozen)
  for (const strategy of ['deterministic', 'learned', 'oracle']) declared.plans[strategy].frozen_plan.stop_mode = FIRST_VERIFIED_FEASIBLE
  for (const run of suite.runs.filter((run: any) => run.case_id === declared.case_id)) {
    const report = run.report; const oracle = run.strategy === 'oracle'
    report.stop_mode = FIRST_VERIFIED_FEASIBLE; report.input_binding = structuredClone(input)
    report.frozen_plan = structuredClone(declared.plans[run.strategy].frozen_plan)
    report.schema_version = oracle ? 'fiber-frame-candidate-search-oracle.v3' : 'fiber-frame-candidate-search-arm.v3'
    const request = readHistoryArtifact(fixture, run.request_file)
    request.schema_version = 'rc-fiber-candidate-process-worker-request.v3'; request.case.stop_mode = FIRST_VERIFIED_FEASIBLE
    replaceCandidateArtifact(fixture, run.request_file, request)
    if (oracle) continue
    const arm = report.arm; const planned = arm.shortlist as string[]
    arm.execution = { stop_mode: FIRST_VERIFIED_FEASIBLE, attempted_candidate_ids: [], unattempted_candidate_ids: [...planned], termination_reason: FIRST_VERIFIED_FEASIBLE, stop_candidate_id: 'baseline', unused_analysis_request_budget: input.full_analysis_budget - 1, selection_scope: 'first_verified_feasible_in_frozen_evaluation_order', global_material_optimality_verified: false }
    arm.candidate_outcomes = report.candidate_pool.map((row: any) => ({ candidate_id: row.candidate_id, status: planned.includes(row.candidate_id) ? 'not_attempted_after_stop' : row.screening_status === 'ready' ? 'not_shortlisted' : 'preanalysis_blocked', analysis_requested: false, solver_executed: false, result: null, full_reference_verification_pass: false, failure: planned.includes(row.candidate_id) ? null : row.failure }))
    arm.final_selection = structuredClone(arm.baseline); arm.selection_difference_from_baseline = structuredClone(arm.baseline.difference_from_baseline)
    arm.design_comparison = null; arm.design_comparison_unavailable_reason = 'stopped_before_candidate_evaluation'
    Object.assign(arm.cost_accounting, { candidate_analysis_request_count: 0, total_analysis_request_count: 1, known_solver_execution_count: 1, unknown_solver_execution_count: 0 })
  }
  fixture.manifest.comparisons = fixture.manifest.comparisons.filter(entry => {
    if (entry.case_id !== declared.case_id) return true
    fixture.files.delete(entry.manifest_file); fixture.files.delete(entry.manifest_file.replace(/manifest\.json$/, 'comparison.json')); return false
  })
  for (const summary of suite.case_summaries) if (summary.case_id === declared.case_id) for (const pair of summary.measured_pairs) {
    pair.selected_candidate_ids = { deterministic: 'baseline', learned: 'baseline' }; pair.learned_verified_scoped_material_cost_not_worse = true
    const oracle = suite.runs.find((run: any) => run.case_id === declared.case_id && run.phase === 'measured' && run.repetition === pair.repetition && run.strategy === 'oracle').report.rows
    for (const strategy of ['deterministic', 'learned']) {
      const pool = declared.plans.learned.candidate_pool; const plan = declared.plans[strategy].frozen_plan
      pair.oracle_audit[strategy] = withCandidateUnrequestedFeasible(recomputeCandidatePredictionAudit(pool, plan.shortlist, oracle, true, strategy === 'deterministic', true), pool, [], oracle, input)
    }
  }
  for (const phase of ['measured', 'warmup']) {
    const rows = suite.runs.filter((run: any) => run.phase === phase)
    const requested = (run: any) => (run.strategy === 'oracle' ? run.report.rows : [run.report.arm.baseline, ...run.report.arm.candidate_outcomes]).filter((row: any) => row.analysis_requested)
    const counts = suite.cost_accounting.phases[phase]
    counts.validated_online_request_subtotal = rows.filter((run: any) => run.strategy !== 'oracle').reduce((sum: number, run: any) => sum + requested(run).length, 0)
    counts.validated_oracle_request_subtotal = rows.filter((run: any) => run.strategy === 'oracle').reduce((sum: number, run: any) => sum + requested(run).length, 0)
    counts.total_analysis_request_count = counts.validated_online_request_subtotal + counts.validated_oracle_request_subtotal
    counts.known_solver_execution_subtotal = rows.reduce((sum: number, run: any) => sum + requested(run).filter((row: any) => row.solver_executed === true).length, 0)
    counts.unknown_solver_execution_subtotal = rows.reduce((sum: number, run: any) => sum + requested(run).filter((row: any) => row.solver_executed === null).length, 0)
  }
  suite.cost_accounting.current_analysis_request_count = suite.cost_accounting.phases.measured.total_analysis_request_count + suite.cost_accounting.phases.warmup.total_analysis_request_count
  suite.cost_accounting.total_analysis_request_count_including_training_warmups_and_oracles = suite.cost_accounting.current_analysis_request_count + suite.cost_accounting.historical_training_analysis_request_count
  resealHistoryPredictionFixture(fixture)
  return fixture
}
