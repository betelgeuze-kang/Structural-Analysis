import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { CandidateSearchProcessPanel } from '../../src/workbench-v2/components/CandidateSearchProcessPanel'
import { loadCandidateProcessReview, parseCandidateProcessJson } from '../../src/workbench-v2/model/candidateProcessProvider'
import { recomputeCandidatePredictionAudit, validateCandidatePredictionPlans, validateCandidatePredictionRow } from '../../src/workbench-v2/model/candidateProcessSchema'
import { candidateProcessObservedFixture, replaceCandidateArtifact, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { candidateProcessHistoryPredictionFixture, historyProfile, historyTargets, readHistoryArtifact, resealHistoryPredictionFixture } from './candidateProcessHistoryPredictionFixture'

const clone = <T,>(value: T): T => structuredClone(value)
let seed: CandidateObservedFixture
function fixture(): CandidateObservedFixture { seed ??= candidateProcessHistoryPredictionFixture(); return clone(seed) }
function context(): { input: any; training: any; plans: any } {
  seed ??= candidateProcessHistoryPredictionFixture()
  const suite: any = seed.suite
  return { input: clone(suite.declaration.cases[0].input_binding), training: readHistoryArtifact(seed, suite.declaration.inputs[2].path), plans: clone(suite.declaration.cases[0].plans) }
}
async function load(f: CandidateObservedFixture) {
  const originalFetch = globalThis.fetch; const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: 'https://example.test/workbench-v2', origin: 'https://example.test' } } })
  globalThis.fetch = async (input, options) => {
    expect(options?.credentials).toBe('same-origin'); expect(options?.redirect).toBe('error'); expect(options?.method).toBe('GET')
    const target = new URL(String(input)); expect(target.origin).toBe('https://example.test'); expect(target.pathname.startsWith('/review/')).toBe(true)
    const bytes = f.files.get(target.pathname.slice('/review/'.length))
    return bytes ? new Response(bytes, { headers: { 'content-type': 'application/json' } }) : new Response('', { status: 404 })
  }
  try { return await loadCandidateProcessReview('https://example.test/review/manifest.json') }
  finally { globalThis.fetch = originalFetch; if (windowDescriptor) Object.defineProperty(globalThis, 'window', windowDescriptor); else delete (globalThis as { window?: unknown }).window }
}

test('history prediction transport preserves original engineering rows and all full-reference selections', async () => {
  const f = fixture(); const result = await load(f)
  expect(result.errors).toEqual([]); expect(result.status).toBe('verified'); expect(result.bundle!.slots).toHaveLength(12)
  const before = candidateProcessObservedFixture()
  for (const slot of result.bundle!.slots) {
    expect(slot.run.report!.candidate_target_profile).toBe(historyProfile)
    if (slot.strategy === 'oracle') continue
    const original = before.suite.runs.find(run => run.case_id === slot.caseId && run.repetition === slot.repetition && run.strategy === slot.strategy)!
    expect(slot.run.report!.arm!.final_selection!.candidate_id).toBe(original.report!.arm!.final_selection!.candidate_id)
    expect(slot.run.report!.arm!.baseline.result).toEqual(original.report!.arm!.baseline.result)
    expect(slot.comparison!.report).toEqual(slot.run.report!.arm!.design_comparison)
  }
  expect(Buffer.from(result.bundle!.suiteBytes)).toEqual(Buffer.from(f.files.get('suite.json')!))
  expect(Buffer.from(result.bundle!.manifestBytes)).toEqual(Buffer.from(f.files.get('manifest.json')!))
})

test('frozen learner sample membership is sorted and excludes evaluation labels', () => {
  const c = context(); expect(() => validateCandidatePredictionPlans(c.input, c.training, c.plans)).not.toThrow()
  c.training.policy.training_sample_hashes.push(c.training.samples.find((row: any) => row.split === 'holdout').sample_hash)
  expect(() => validateCandidatePredictionPlans(c.input, c.training, c.plans)).toThrow()
})

for (const [name, mutate] of [
  ['missing input scope', (c: any) => { delete c.input.candidate_target_profile }],
  ['missing training scope', (c: any) => { delete c.training.target_profile }],
  ['missing policy scope', (c: any) => { delete c.training.policy.target_profile }],
  ['downgraded learning schema', (c: any) => { c.training.schema_version = 'fiber-frame-candidate-learning.v2' }],
  ['downgraded policy schema', (c: any) => { c.training.policy.schema_version = 'fiber-frame-candidate-ridge-policy.v2' }],
  ['missing report target names', (c: any) => { delete c.training.targets }],
  ['wrong target order', (c: any) => { c.training.policy.targets.reverse() }],
  ['two-column target scaling', (c: any) => { c.training.policy.target_scale.length = 2 }],
  ['two-column weights', (c: any) => { c.training.policy.weights[0].length = 2 }],
  ['sample profile omission', (c: any) => { delete c.training.samples[0].target_profile }],
  ['missing stable project ID', (c: any) => { delete c.training.samples[0].project_id }],
  ['invalid stable geometry ID', (c: any) => { c.training.samples[0].geometry_family_id = 'not a stable ID' }],
  ['project leakage across splits', (c: any) => { c.training.samples.find((row: any) => row.split === 'holdout').project_id = c.training.samples[0].project_id }],
  ['geometry leakage across splits', (c: any) => { c.training.samples.find((row: any) => row.split === 'validation').geometry_family_id = c.training.samples[0].geometry_family_id }],
  ['load history leakage across splits', (c: any) => { c.training.samples.find((row: any) => row.split === 'holdout').load_history_id = c.training.samples[0].load_history_id }],
  ['training context detachment', (c: any) => { c.training.samples[0].context_hash = 'sha256:' + '0'.repeat(64) }],
  ['duplicate physical training identity', (c: any) => { c.training.samples[1].model_identity_hash = c.training.samples[0].model_identity_hash }],
  ['detached label source', (c: any) => { c.training.samples[0].history_label_source.bindings.source_result_hash = 'sha256:' + '0'.repeat(64) }],
  ['missing positive epoch', (c: any) => { c.training.samples[0].history_label_source.epochs.pop() }],
  ['wrong committed maximum', (c: any) => { c.training.samples[0].targets[2] *= 2 }],
  ['wrong terminal sample label', (c: any) => { c.training.samples[0].targets[0] *= 0.5 }],
  ['detached case source hash', (c: any) => { c.training.cases[0].history_label_source_hash = 'sha256:' + '0'.repeat(64) }],
  ['independent replay promotion', (c: any) => { c.training.claims.frozen_label_validation_is_independent_source_replay = true }],
  ['scope on frozen plan instead of binding', (c: any) => { c.plans.learned.frozen_plan.candidate_target_profile = historyProfile }],
  ['wrong combined ranking', (c: any) => { c.plans.learned.frozen_plan.ranking.reverse() }],
  ['wrong exploration shortlist', (c: any) => { c.plans.learned.frozen_plan.shortlist = [c.plans.learned.candidate_pool[0].candidate_id] }],
] as const) test(`rejects ${name}`, () => {
  const c = context(); mutate(c)
  expect(() => validateCandidatePredictionPlans(c.input, c.training, c.plans)).toThrow()
})

function screen(values: number[], limits = [1, 1, 1, 1, 1, 1, 1]): { input: any; row: any } {
  const input = { candidate_target_profile: historyProfile, terminal_limits: { maximum_translation_m: limits[0], maximum_absolute_fiber_strain: limits[1] }, history_limits: { maximum_translation_m: limits[2], maximum_absolute_fiber_strain: limits[3] }, material_history_limits: { maximum_steel_accumulated_plastic_strain: limits[4], maximum_concrete_tensile_damage: limits[5], maximum_concrete_compressive_damage: limits[6] } }
  const ratio = (indices: number[]) => Math.max(...indices.map(i => limits[i] === 0 ? values[i] === 0 ? 0 : Number.MAX_VALUE : Math.min(Number.MAX_VALUE, values[i] / limits[i])))
  const safe = (indices: number[]) => indices.every(i => values[i] <= limits[i])
  return { input, row: { candidate_id: 'candidate', model_checksum: 'sha256:' + '1'.repeat(64), screening_status: 'ready', preanalysis_material_estimate: 1,
    prediction: { maximum_translation_m: values[0], maximum_absolute_fiber_strain: values[1], ood: false, reason: 'in_train_feature_range_uncalibrated', physical_result_authority: false, uncertainty_kind: 'uncalibrated_feature_range_indicator_not_probability', target_profile: historyProfile, history_prediction: Object.fromEntries(historyTargets.map((key, i) => [key, values[i + 2]])) },
    predicted_terminal_safe: safe([0, 1]), predicted_limit_ratio: ratio([0, 1]), predicted_history_safe: safe([2, 3]), predicted_material_history_safe: safe([4, 5, 6]), predicted_requested_limits_safe: safe([0, 1, 2, 3, 4, 5, 6]), predicted_requested_limit_ratio: ratio([0, 1, 2, 3, 4, 5, 6]) } }
}

test('equal terminal estimates can rank a material pass ahead of a cheaper material failure', () => {
  const c = context(); const failed = screen([0.1, 0.1, 0.2, 0.2, 0, 0.9, 0], [1, 1, 1, 1, 1, 0.5, 1]); const passed = screen([0.1, 0.1, 0.2, 0.2, 0, 0.3, 0], [1, 1, 1, 1, 1, 0.5, 1])
  Object.assign(c.input, failed.input, { exploration_slots: 0 }); Object.assign(failed.row, { candidate_id: 'cheaper', preanalysis_material_estimate: 1 }); Object.assign(passed.row, { candidate_id: 'wider', preanalysis_material_estimate: 2 })
  for (const strategy of ['learned', 'deterministic', 'oracle']) {
    const rows = clone([failed.row, passed.row])
    if (strategy !== 'learned') rows.forEach(row => { row.prediction = null; for (const key of ['predicted_terminal_safe', 'predicted_limit_ratio', 'predicted_history_safe', 'predicted_material_history_safe', 'predicted_requested_limits_safe', 'predicted_requested_limit_ratio']) row[key] = null })
    c.plans[strategy].candidate_pool = rows; c.plans[strategy].frozen_plan.ranking = strategy === 'learned' ? ['wider', 'cheaper'] : ['cheaper', 'wider']; c.plans[strategy].frozen_plan.shortlist = strategy === 'oracle' ? ['cheaper', 'wider'] : [strategy === 'learned' ? 'wider' : 'cheaper']
  }
  expect(failed.row.predicted_terminal_safe).toBe(true); expect(passed.row.predicted_terminal_safe).toBe(true)
  expect(() => validateCandidatePredictionPlans(c.input, c.training, c.plans)).not.toThrow()
  c.plans.learned.frozen_plan.ranking = ['cheaper', 'wider']
  expect(() => validateCandidatePredictionPlans(c.input, c.training, c.plans)).toThrow()
})

test('unrequested material estimates do not change the requested gate or ratio', () => {
  const { input, row } = screen([0.1, 0.1, 0.2, 0.2, 9, 1, 1]); delete input.material_history_limits
  row.predicted_material_history_safe = null; row.predicted_requested_limits_safe = true; row.predicted_requested_limit_ratio = 0.2
  expect(() => validateCandidatePredictionRow(row, input, true)).not.toThrow()
})
for (const [name, values, limits, safe, ratio] of [
  ['all zero values and limits', [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], true, 0],
  ['positive memory at zero limit', [0, 0, 0, 0, 0.1, 0, 0], [0, 0, 0, 0, 0, 0, 0], false, Number.MAX_VALUE],
  ['overflow saturates ratio only', [0, 0, 0, 0, 1e308, 0, 0], [1, 1, 1, 1, Number.MIN_VALUE, 1, 1], false, Number.MAX_VALUE],
] as const) test(name, () => {
  const { input, row } = screen([...values], [...limits]); expect(() => validateCandidatePredictionRow(row, input, true)).not.toThrow()
  expect(row.predicted_requested_limits_safe).toBe(safe); expect(row.predicted_requested_limit_ratio).toBe(ratio)
})

for (const [name, mutate] of [
  ['history field omission', (row: any) => { delete row.prediction.history_prediction }],
  ['prediction profile omission', (row: any) => { delete row.prediction.target_profile }],
  ['combined gate omission', (row: any) => { delete row.predicted_requested_limits_safe }],
  ['non-OOD missing history', (row: any) => { row.prediction.history_prediction = null }],
  ['damage above one', (row: any) => { row.prediction.history_prediction.history_maximum_concrete_tensile_damage = 1.1 }],
  ['history below terminal', (row: any) => { row.prediction.history_prediction.history_maximum_translation_m = 0.01 }],
  ['boolean numerical estimate', (row: any) => { row.prediction.maximum_translation_m = true }],
  ['OOD carrying estimates', (row: any) => { row.prediction.ood = true }],
  ['unavailable confused with false', (row: any) => { row.predicted_requested_limits_safe = null }],
] as const) test(`rejects malformed ${name}`, () => {
  const { input, row } = screen([0.1, 0.1, 0.2, 0.2, 0, 0, 0]); mutate(row)
  expect(() => validateCandidatePredictionRow(row, input, true)).toThrow()
})

test('OOD remains unknown for every requested prediction and does not increase known denominators', () => {
  const { input, row } = screen([0.1, 0.1, 0.2, 0.2, 0, 0, 0])
  Object.assign(row.prediction, { ood: true, reason: 'prediction_history_range_inconsistent', maximum_translation_m: null, maximum_absolute_fiber_strain: null, history_prediction: null })
  for (const key of ['predicted_terminal_safe', 'predicted_limit_ratio', 'predicted_history_safe', 'predicted_material_history_safe', 'predicted_requested_limits_safe', 'predicted_requested_limit_ratio']) row[key] = null
  expect(() => validateCandidatePredictionRow(row, input, true)).not.toThrow()
  const audit = recomputeCandidatePredictionAudit([row], [], null, true, false, true)
  expect(audit.predicted_requested_limits_safety_candidate_count).toBe(0); expect(audit.predicted_material_history_safety_available).toBe(false)
  expect(audit.combined_false_safe_count).toBeNull()
})

test('combined oracle audits separate verified material failure from unavailable verification', () => {
  const pool = ['material-fail', 'unavailable', 'terminal-fail'].map(candidate_id => ({ candidate_id, predicted_terminal_safe: true, predicted_history_safe: true, predicted_material_history_safe: true, predicted_requested_limits_safe: true }))
  const oracle = pool.map(row => ({ candidate_id: row.candidate_id, full_reference_verification_pass: true, full_history_verification_pass: true, full_material_history_verification_pass: row.candidate_id !== 'unavailable', terminal_limit_status: row.candidate_id === 'terminal-fail' ? 'fail' : 'pass', history_limit_status: 'pass', material_history_limit_status: row.candidate_id === 'material-fail' ? 'fail' : row.candidate_id === 'unavailable' ? 'unavailable' : 'pass' }))
  const audit = recomputeCandidatePredictionAudit(pool, [], oracle, true, false, true)
  expect(audit.false_safe_candidate_ids).toEqual(['terminal-fail'])
  expect(audit.combined_false_safe_candidate_ids).toEqual(['material-fail', 'terminal-fail'])
  expect(audit.combined_predicted_safe_unverifiable_candidate_ids).toEqual(['unavailable'])
  expect(audit.predicted_requested_limits_safety_candidate_count).toBe(3)
  const deterministic = recomputeCandidatePredictionAudit(pool, [], oracle, true, true, true)
  expect(deterministic.combined_false_safe_count).toBeNull(); expect(deterministic.predicted_requested_limits_safety_candidate_count).toBe(0); expect(deterministic.predicted_history_safety_available).toBe(false)
})

for (const [name, mutate] of [
  ['worker top profile removal', (f: any) => { delete f.suite.runs[0].report.candidate_target_profile }],
  ['coherent bound scope removal', (f: any) => { delete f.suite.declaration.cases[0].input_binding.candidate_target_profile; for (const run of f.suite.runs.filter((row: any) => row.case_id === f.suite.declaration.cases[0].case_id)) { delete run.report.input_binding.candidate_target_profile; delete run.report.candidate_target_profile } }],
  ['training policy downgrade', (f: any) => { const path = f.suite.declaration.inputs[2].path; const training = readHistoryArtifact(f, path); training.policy.schema_version = 'fiber-frame-candidate-ridge-policy.v2'; replaceCandidateArtifact(f, path, training) }],
] as const) test(`raw-resealed transport rejects ${name}`, async () => {
  const f = fixture(); mutate(f); resealHistoryPredictionFixture(f)
  const result = await load(f); expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull(); expect(result.errors.join(' ')).toContain('candidate_process_')
})

function inspect(node: any): { text: string; props: Record<string, any>[] } {
  if (node === null || node === undefined || typeof node === 'boolean') return { text: '', props: [] }
  if (typeof node === 'string' || typeof node === 'number') return { text: String(node), props: [] }
  if (Array.isArray(node)) return node.map(inspect).reduce((a, b) => ({ text: a.text + b.text, props: [...a.props, ...b.props] }), { text: '', props: [] })
  if (typeof node.type === 'function') return inspect(node.type(node.props))
  const children = inspect(node.props?.children); return { text: children.text, props: [node.props ?? {}, ...children.props] }
}
test('panel identifies prediction scope, preserves zero versus unavailable, and never offers oracle approval', async () => {
  const result = await load(fixture()); expect(result.status).toBe('verified')
  const bundle = result.bundle!; const slot = bundle.slots.find(row => row.strategy === 'learned')!
  const tree = inspect(CandidateSearchProcessPanel({ load: result, selectedSlot: slot, onSelect: () => undefined }))
  expect(tree.text).toContain('History and material prediction'); expect(tree.text).toContain('Predictions are estimates, not engineering approval')
  expect(tree.props.some(props => props['data-candidate-combined-false-safe'])).toBe(true)
  expect(tree.text).toContain('Predicted full-scope pass, verified fail')
  const metric = tree.props.find(props => props['data-candidate-combined-unverifiable'] === `${slot.caseId}:0:learned`)!
  expect(inspect(metric.children).text).toBe('0')
  const pair: any = bundle.suite.case_summaries[0].measured_pairs[0]; pair.oracle_audit.learned.combined_predicted_safe_unverifiable_count = null
  const unavailable = inspect(CandidateSearchProcessPanel({ load: result, selectedSlot: slot, onSelect: () => undefined }))
  expect(inspect(unavailable.props.find(props => props['data-candidate-combined-unverifiable'] === `${slot.caseId}:0:learned`)!.children).text).toContain('UNAVAILABLE')
  const legacy = await load(candidateProcessObservedFixture()); expect(legacy.status).toBe('verified')
  expect(inspect(CandidateSearchProcessPanel({ load: legacy, selectedSlot: legacy.bundle!.slots[0], onSelect: () => undefined })).text).toContain('Terminal-only prediction')
})

function actualProducerContext(): { training: any; input: any; plans: any; provenance: any } {
  const directory = new URL('../fixtures/fiber_frame_candidate_history_process/', import.meta.url)
  const provenance = JSON.parse(readFileSync(new URL('provenance.json', directory), 'utf8'))
  const bytes = readFileSync(new URL(provenance.bundle.file, directory))
  const digest = (value: Uint8Array) => `sha256:${createHash('sha256').update(value).digest('hex')}`
  expect(bytes.length).toBe(provenance.bundle.byte_length); expect(digest(bytes)).toBe(provenance.bundle.sha256)
  const archive = JSON.parse(gunzipSync(bytes).toString('utf8'))
  expect(archive.schema_version).toBe('candidate-history-actual-producer-fixture.v1')
  expect(archive.files.map((file: any) => file.name)).toEqual(['training', 'declaration'])
  const decoded: Record<string, any> = {}
  for (const file of archive.files) {
    const raw = new TextEncoder().encode(file.utf8)
    expect(raw.length).toBe(file.byte_length); expect(digest(raw)).toBe(file.sha256)
    const { utf8: _, ...identity } = file
    expect(identity).toEqual(provenance.retained_files.find((row: any) => row.name === file.name))
    decoded[file.name] = parseCandidateProcessJson(raw)
  }
  const training = decoded.training; const declaration = decoded.declaration
  expect(training.source_revision).toBe(provenance.source_generation_snapshot.source_revision)
  expect(declaration.source_revision).toBe(training.source_revision)
  expect(training.report_hash).toBe(provenance.original_identity_labels.training_report_hash)
  expect(training.policy.artifact_hash).toBe(provenance.original_identity_labels.policy_artifact_hash)
  const { input_binding: input, ...plans } = declaration.cases[0].expectations
  expect(input.training_report_hash).toBe(training.report_hash); expect(input.policy_artifact_hash).toBe(training.policy.artifact_hash)
  return { training, input, plans, provenance }
}

test('actual producer bytes pass the JS frozen history prediction contract', () => {
  const { training, input, plans, provenance } = actualProducerContext()
  expect(() => validateCandidatePredictionPlans(input, training, plans)).not.toThrow()
  expect(training.samples).toHaveLength(4)
  expect(training.samples.every((sample: any) => sample.targets.slice(4).every((value: number) => value === 0))).toBe(true)
  expect(provenance.correctness_scope).toMatchObject({ historical_public_label_analysis_requests: 4, worker_public_analysis_requests: 2, total_public_analysis_requests: 6, fixture_generation_analysis_requests: 0, fixture_generation_training_executions: 0, low_load_zero_material_memory: true })
  expect(provenance.claims).toMatchObject({ independent_physical_validation: false, performance_experiment: false, external_case_validation: false, damage_prediction_accuracy_established: false })
})

test('actual producer bytes reject a stripped training target profile', () => {
  const { training, input, plans } = actualProducerContext()
  delete training.target_profile
  expect(() => validateCandidatePredictionPlans(input, training, plans)).toThrow()
})

test('actual producer bytes reject a material target detached from retained epoch labels', () => {
  const { training, input, plans } = actualProducerContext()
  training.samples[0].targets[4] = 0.01
  expect(() => validateCandidatePredictionPlans(input, training, plans)).toThrow()
})
