// Synthetic stop metadata and retained transport; no new physical or performance evidence.
import { expect, test } from '@playwright/test'
import { loadCandidateProcessReview } from '../../src/workbench-v2/model/candidateProcessProvider'
import { FIRST_VERIFIED_FEASIBLE, validateCandidateStopExecution, withCandidateUnrequestedFeasible } from '../../src/workbench-v2/model/candidateProcessSchema'
import { candidateProcessStopFixture } from './candidateProcessStopFixture'
import { readHistoryArtifact, resealHistoryPredictionFixture } from './candidateProcessHistoryPredictionFixture'
import { replaceCandidateArtifact, type CandidateObservedFixture } from './candidateProcessObservedFixture'

let seed: CandidateObservedFixture
const fixture = () => structuredClone(seed ??= candidateProcessStopFixture())
async function load(f: CandidateObservedFixture) {
  const fetchBefore = globalThis.fetch; const windowBefore = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: 'https://example.test/', origin: 'https://example.test' } } })
  globalThis.fetch = async (input, options) => {
    expect(options?.method).toBe('GET'); expect(options?.redirect).toBe('error')
    const url = new URL(String(input)); expect(url.origin).toBe('https://example.test')
    const bytes = f.files.get(url.pathname.slice('/stop/'.length))
    return bytes ? new Response(bytes, { headers: { 'content-type': 'application/json' } }) : new Response('', { status: 404 })
  }
  try { return await loadCandidateProcessReview('/stop/manifest.json') }
  finally { globalThis.fetch = fetchBefore; if (windowBefore) Object.defineProperty(globalThis, 'window', windowBefore); else delete (globalThis as { window?: unknown }).window }
}

test('mixed v3 stop and legacy cases retain raw bytes, unused budget and baseline-only source verification', async () => {
  const f = fixture(); const result = await load(f)
  expect(result.errors).toEqual([]); expect(result.status).toBe('verified'); expect(result.bundle!.slots).toHaveLength(12)
  expect(result.bundle!.manifest.schema_version).toBe('rc-fiber-candidate-process-review-bundle.v3')
  const stopped = result.bundle!.slots.filter(slot => slot.caseId === result.bundle!.slots[0].caseId && slot.strategy !== 'oracle')
  for (const slot of stopped) {
    expect(slot.run.report!.arm!.execution).toMatchObject({ attempted_candidate_ids: [], stop_candidate_id: 'baseline', unused_analysis_request_budget: 1 })
    expect(slot.comparison).toBeNull(); expect(slot.comparisonManifestBytes).toBeNull(); expect(slot.comparisonReportBytes).toBeNull()
  }
  expect(result.bundle!.slots.filter(slot => slot.caseId !== stopped[0].caseId && slot.strategy !== 'oracle').every(slot => slot.comparison !== null)).toBe(true)
  expect(Buffer.from(result.bundle!.suiteBytes)).toEqual(Buffer.from(f.files.get('suite.json')!))
  expect(Buffer.from(result.bundle!.manifestBytes)).toEqual(Buffer.from(f.files.get('manifest.json')!))
})

for (const [label, mutate] of [
  ['unbound outer mode', (f: any) => { delete f.suite.runs[0].report.stop_mode }],
  ['null input mode', (f: any) => { f.suite.declaration.cases[0].input_binding.stop_mode = null }],
  ['v2 envelope downgrade', (f: any) => { f.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v2' }],
  ['mode omitted from frozen plan', (f: any) => { delete f.suite.declaration.cases[0].plans.deterministic.frozen_plan.stop_mode }],
  ['request mode omission', (f: any) => { const path = f.suite.runs[0].request_file; const request = readHistoryArtifact(f, path); delete request.case.stop_mode; replaceCandidateArtifact(f, path, request) }],
  ['baseline price forged', (f: any) => { const arm = f.suite.runs[0].report.arm; arm.baseline.material_estimate.total += 1; arm.final_selection = structuredClone(arm.baseline) }],
  ['baseline validation forged', (f: any) => { const arm = f.suite.runs[0].report.arm; arm.baseline.validation.contract_pass = false; arm.final_selection = structuredClone(arm.baseline) }],
  ['baseline source config forged', (f: any) => { const arm = f.suite.runs[0].report.arm; arm.baseline.result.configuration.maximum_iterations += 1; arm.final_selection = structuredClone(arm.baseline) }],
  ['unattempted row gets result', (f: any) => { f.suite.runs[0].report.arm.candidate_outcomes[0].result = {} }],
  ['planned requests counted as actual work', (f: any) => { f.suite.runs[0].report.arm.cost_accounting.candidate_analysis_request_count = 1 }],
  ['audit hides unrequested feasibility', (f: any) => { f.suite.case_summaries[0].measured_pairs[0].oracle_audit.learned.unrequested_feasible_count = 0 }],
] as const) test(`raw resealing cannot legitimize ${label}`, async () => {
  const f = fixture(); mutate(f); resealHistoryPredictionFixture(f)
  const result = await load(f); expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull()
})

function orderedFixture() {
  const input: any = { stop_mode: FIRST_VERIFIED_FEASIBLE, full_analysis_budget: 5, history_limits: {}, material_history_limits: {} }
  const row = (id: string, passed = false): any => ({ candidate_id: id, analysis_requested: true, full_reference_verification_pass: true, full_history_verification_pass: true, full_material_history_verification_pass: true, terminal_limit_status: 'pass', history_limit_status: 'pass', material_history_limit_status: passed ? 'pass' : 'fail', material_estimate: { total: 10 } })
  const baseline = row('baseline'); const a = row('failed'); a.solver_executed = null; const b = row('unverifiable', true); b.full_material_history_verification_pass = false; b.material_history_limit_status = 'unavailable'; const c = row('accepted', true)
  const tail = { candidate_id: 'tail', status: 'not_attempted_after_stop', analysis_requested: false, solver_executed: false, result: null, full_reference_verification_pass: false, failure: null }
  const pool = [a, b, c, tail].map(row => ({ candidate_id: row.candidate_id, screening_status: 'ready', failure: null, prediction: { ood: row.candidate_id === 'accepted' } }))
  const arm: any = { baseline, shortlist: pool.map(row => row.candidate_id), candidate_outcomes: [a, b, c, tail], final_selection: c, execution: { stop_mode: FIRST_VERIFIED_FEASIBLE, attempted_candidate_ids: ['failed', 'unverifiable', 'accepted'], unattempted_candidate_ids: ['tail'], termination_reason: FIRST_VERIFIED_FEASIBLE, stop_candidate_id: 'accepted', unused_analysis_request_budget: 1, selection_scope: 'first_verified_feasible_in_frozen_evaluation_order', global_material_optimality_verified: false } }
  return { input, arm, pool }
}

test('failed and unavailable requests precede an OOD candidate verified feasible; unknown execution is preserved', () => {
  const { input, arm, pool } = orderedFixture(); const before = structuredClone(arm)
  expect(validateCandidateStopExecution(arm, input, pool).attempted_candidate_ids).toEqual(['failed', 'unverifiable', 'accepted'])
  expect(arm).toEqual(before); expect(arm.candidate_outcomes[0].solver_executed).toBeNull()
})

for (const [label, mutate] of [
  ['skip preceding candidate', (a: any) => { a.execution.attempted_candidate_ids = ['unverifiable', 'accepted'] }],
  ['premature material-failing stop', (a: any) => { a.execution.stop_candidate_id = 'failed' }],
  ['premature unavailable stop', (a: any) => { a.execution.stop_candidate_id = 'unverifiable' }],
  ['continue after feasible', (a: any) => { a.candidate_outcomes[0].material_history_limit_status = 'pass' }],
  ['missing suffix', (a: any) => { a.execution.unattempted_candidate_ids = [] }],
  ['wrong unused budget', (a: any) => { a.execution.unused_analysis_request_budget = 0 }],
  ['boolean unused budget', (a: any) => { a.execution.unused_analysis_request_budget = true }],
  ['invent global optimum', (a: any) => { a.execution.global_material_optimality_verified = true }],
  ['wrong termination', (a: any) => { a.execution.termination_reason = 'planned_shortlist_exhausted' }],
  ['unknown execution metadata', (a: any) => { a.execution.extra = true }],
] as const) test(`stop contract rejects ${label}`, () => {
  const { input, arm, pool } = orderedFixture(); mutate(arm)
  expect(() => validateCandidateStopExecution(arm, input, pool)).toThrow()
})

test('full requested baseline verification is required before any candidate can justify selection', () => {
  const { input, arm, pool } = orderedFixture(); arm.baseline.full_history_verification_pass = false
  expect(() => validateCandidateStopExecution(arm, input, pool)).toThrow()
  arm.final_selection = null
  arm.candidate_outcomes = pool.map(row => ({ candidate_id: row.candidate_id, status: 'not_attempted_after_stop', analysis_requested: false, solver_executed: false, result: null, full_reference_verification_pass: false, failure: null }))
  Object.assign(arm.execution, { attempted_candidate_ids: [], unattempted_candidate_ids: [...arm.shortlist], termination_reason: 'baseline_verification_unavailable', stop_candidate_id: null, unused_analysis_request_budget: 4 })
  expect(() => validateCandidateStopExecution(arm, input, pool)).not.toThrow()
})

test('exhausted plan remains blocked after every requested candidate fails a required limit', () => {
  const { input, arm, pool } = orderedFixture()
  arm.shortlist = arm.shortlist.slice(0, 3); arm.final_selection = null
  arm.candidate_outcomes[2].history_limit_status = 'fail'
  arm.candidate_outcomes[3].status = 'not_shortlisted'
  Object.assign(arm.execution, { unattempted_candidate_ids: [], termination_reason: 'planned_shortlist_exhausted', stop_candidate_id: null })
  expect(() => validateCandidateStopExecution(arm, input, pool)).not.toThrow()
  expect(arm.execution.unused_analysis_request_budget).toBe(1)
})

test('missing oracle remains null; unrequested feasible includes planned suffix but excludes baseline and unverifiable rows', () => {
  const { input, arm, pool } = orderedFixture()
  const original = { missed_feasible_count: 0 }
  const oracle = [...arm.candidate_outcomes.slice(0, 3), { ...arm.final_selection, candidate_id: 'tail' }, { ...arm.final_selection, candidate_id: 'baseline' }]
  const audit = withCandidateUnrequestedFeasible(original, pool, ['failed', 'unverifiable', 'accepted'], oracle, input)
  expect(audit.unrequested_feasible_candidate_ids).toEqual(['tail']); expect(audit.missed_feasible_count).toBe(0); expect(original).toEqual({ missed_feasible_count: 0 })
  expect(withCandidateUnrequestedFeasible(original, pool, [], null, input).unrequested_feasible_count).toBeNull()
})
