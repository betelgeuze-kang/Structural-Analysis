import { expect, test } from '@playwright/test'
import { loadCandidateProcessReview, parseCandidateProcessJson } from '../../src/workbench-v2/model/candidateProcessProvider'
import { validateCandidateProcessManifest } from '../../src/workbench-v2/model/candidateProcessSchema'
import { candidateBytes, candidateProcessObservedFixture, candidateProcessIncompleteFixture, replaceCandidateArtifact, sealCandidateFixture, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { candidateProcessMaterialHistoryFixture } from './candidateProcessMaterialHistoryFixture'

const origin = 'https://example.test'
const url = `${origin}/candidate-review/manifest.json`
async function load(fixture: CandidateObservedFixture, transform?: (path: string, bytes: Uint8Array) => Response): Promise<Awaited<ReturnType<typeof loadCandidateProcessReview>>> {
  const savedFetch = globalThis.fetch; const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: `${origin}/workbench-v2`, origin } } })
  globalThis.fetch = async (input, options) => {
    expect(options?.method).toBe('GET'); expect(options?.redirect).toBe('error'); expect(options?.credentials).toBe('same-origin')
    const target = new URL(String(input)); expect(target.origin).toBe(origin); expect(target.pathname.startsWith('/candidate-review/')).toBe(true)
    const path = target.pathname.slice('/candidate-review/'.length); const bytes = fixture.files.get(path)
    if (!bytes) return new Response('', { status: 404 })
    return transform?.(path, bytes) ?? new Response(bytes, { headers: { 'content-type': 'application/json' } })
  }
  try { return await loadCandidateProcessReview(url) } finally { globalThis.fetch = savedFetch; if (windowDescriptor) Object.defineProperty(globalThis, 'window', windowDescriptor); else delete (globalThis as { window?: unknown }).window }
}

test('exact historical bytes retain all 12 slots, eight original comparisons and disjoint scoped totals', async () => {
  const fixture = candidateProcessObservedFixture(); const result = await load(fixture)
  expect(result.errors).toEqual([]); expect(result.status).toBe('verified')
  const bundle = result.bundle!; expect(bundle.suite.status).toBe('ready'); expect(bundle.slots).toHaveLength(12)
  expect(bundle.slots.filter(slot => slot.comparison)).toHaveLength(8)
  expect(bundle.suite.cost_accounting.current_analysis_request_count).toBe(28)
  expect(bundle.suite.cost_accounting.historical_training_analysis_request_count).toBe(4)
  expect(bundle.suite.cost_accounting.total_analysis_request_count_including_training_warmups_and_oracles).toBe(32)
  expect(bundle.suite.resource_accounting.current_parent_plus_workers_cpu_time_ns).toBe(322245242470)
  expect(Buffer.from(bundle.suiteBytes).equals(Buffer.from(fixture.files.get('suite.json')!))).toBe(true); expect(Buffer.from(bundle.manifestBytes).equals(Buffer.from(fixture.files.get('manifest.json')!))).toBe(true)
  for (const slot of bundle.slots) {
    expect(slot.run).toBe(bundle.suite.runs[bundle.slots.indexOf(slot)])
    if (slot.comparison) { expect(slot.comparison.report).toEqual(slot.run.report!.arm!.design_comparison); expect(Buffer.from(slot.comparisonReportBytes!).equals(Buffer.from(fixture.files.get(new URL(slot.comparison.reportUrl).pathname.slice('/candidate-review/'.length))!))).toBe(true) }
    else expect(slot.strategy).toBe('oracle')
  }
})

test('mixed material suite keeps new case scope and exact legacy worker report bytes', async () => {
  const fixture = candidateProcessMaterialHistoryFixture(); const historical = candidateProcessObservedFixture()
  const result = await load(fixture)
  expect(result.errors).toEqual([]); expect(result.status).toBe('verified')
  expect(result.bundle!.manifest.schema_version).toBe('rc-fiber-candidate-process-review-bundle.v2')
  expect(result.bundle!.suite.schema_version).toBe('rc-fiber-candidate-process-suite.v2')
  const materialCase = fixture.suite.runs[0].case_id
  for (const slot of result.bundle!.slots) {
    if (slot.caseId === materialCase) {
      expect(slot.run.report!.schema_version).toBe(slot.strategy === 'oracle' ? 'fiber-frame-candidate-search-oracle.v2' : 'fiber-frame-candidate-search-arm.v2')
      if (slot.comparison) expect(slot.comparison.report.schema_version).toBe('public-rc-fiber-design-comparison.v3')
    } else {
      const path = `${slot.run.worker_directory}/search.json`
      const entry = fixture.manifest.artifacts.find(row => row.source_path === path)!
      expect(Buffer.from(fixture.files.get(entry.file)!)).toEqual(Buffer.from(historical.files.get(entry.file)!))
      if (slot.comparison) expect(slot.comparison.report.schema_version).toBe('public-rc-fiber-design-comparison.v2')
    }
  }
})

for (const [name, mutate] of [
  ['detached oracle source', (row: any) => { row.constitutive_history.bindings.source_result_hash = 'sha256:' + '0'.repeat(64) }],
  ['missing oracle memory state', (row: any) => { row.constitutive_history.states.pop() }],
  ['boolean oracle memory count', (row: any) => { row.constitutive_history.states[1].materials.steel.point_count = true }],
  ['wrong oracle displayed maximum', (row: any) => { row.performance.history_maximum_steel_accumulated_plastic_strain = 1 }],
  ['false oracle material failure', (row: any) => { row.material_history_limit_status = 'fail' }],
] as const) test(`material process rejects coherently transported ${name}`, async () => {
  const fixture = candidateProcessMaterialHistoryFixture()
  const run = fixture.suite.runs.find(row => row.case_id === fixture.suite.runs[0].case_id && row.strategy === 'oracle')!
  mutate((run.report!.rows as any[])[1])
  const search = replaceCandidateArtifact(fixture, `${run.worker_directory}/search.json`, run.report)
  const oldSize = Number(run.resources!.report_bytes_written)
  Object.assign(run.resources!, { search_sha256: search.sha256, search_byte_length: search.byte_length, report_bytes_written: search.byte_length })
  const resources = replaceCandidateArtifact(fixture, `${run.worker_directory}/resources.json`, run.resources)
  run.manifest!.artifacts['search.json'] = { sha256: search.sha256, byte_length: search.byte_length }
  run.manifest!.artifacts['resources.json'] = { sha256: resources.sha256, byte_length: resources.byte_length }
  replaceCandidateArtifact(fixture, `${run.worker_directory}/manifest.json`, run.manifest)
  fixture.suite.resource_accounting.workers_by_strategy.oracle.measured.report_bytes_written += search.byte_length - oldSize
  sealCandidateFixture(fixture)
  const result = await load(fixture)
  expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull()
  expect(result.errors.join(' ')).toContain('design comparison')
})

test('material process cannot silently downgrade the review schema', async () => {
  const fixture = candidateProcessMaterialHistoryFixture()
  fixture.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v1'
  sealCandidateFixture(fixture)
  expect((await load(fixture)).status).toBe('invalid')
})

for (const [name, mutate] of [
  ['removed slot', (f: CandidateObservedFixture) => f.suite.runs.pop()],
  ['duplicate slot', (f: CandidateObservedFixture) => { f.suite.runs[1] = f.suite.runs[0] }],
  ['reordered oracle', (f: CandidateObservedFixture) => { [f.suite.runs[0], f.suite.runs[2]] = [f.suite.runs[2], f.suite.runs[0]] }],
  ['duplicate training charge', (f: CandidateObservedFixture) => { f.suite.cost_accounting.historical_training_analysis_request_count += 4 }],
  ['warmup folded into measured', (f: CandidateObservedFixture) => { f.suite.cost_accounting.phases.warmup.total_analysis_request_count = 1 }],
  ['false zero unknown coverage', (f: CandidateObservedFixture) => { f.suite.cost_accounting.phases.measured.unknown_request_slots = 1 }],
  ['summed memory peaks', (f: CandidateObservedFixture) => { f.suite.resource_accounting.workers_by_strategy.learned.measured.peak_memory_bytes.median! *= 4 }],
  ['worker CPU omitted', (f: CandidateObservedFixture) => { f.suite.resource_accounting.current_parent_plus_workers_cpu_time_ns = f.suite.resource_accounting.parent_cpu_time_ns }],
  ['parent preflight charged twice', (f: CandidateObservedFixture) => { f.suite.cost_accounting.accounted_wall_ns_including_historical_generation_and_fit += f.suite.resource_accounting.parent_preflight_wall_ns }],
  ['paired launcher time substituted', (f: CandidateObservedFixture) => { f.suite.case_summaries[0].measured_pairs[0].deterministic_minus_learned_slot_wall_ns = 0 }],
  ['unavailable projection promoted', (f: CandidateObservedFixture) => { f.suite.case_summaries[0].projected_reuses_to_amortize_this_training_artifact = 1 }],
  ['oracle denominator dropped', (f: CandidateObservedFixture) => { const pair = f.suite.case_summaries[0].measured_pairs[0] as any; pair.oracle_audit.learned.oracle_verified_candidate_count = 1 }],
  ['general speed claim', (f: CandidateObservedFixture) => { f.suite.claims.generalized_speedup_claimed = true }],
  ['missing comparison', (f: CandidateObservedFixture) => { f.manifest.comparisons.pop() }],
  ['comparison from other worker', (f: CandidateObservedFixture) => { f.manifest.comparisons[0].worker_report_hash = f.manifest.comparisons[1].worker_report_hash }],
] as const) test(`rejects resealed transport with ${name}`, async () => {
  const fixture = candidateProcessObservedFixture(); mutate(fixture); sealCandidateFixture(fixture)
  const result = await load(fixture); expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull()
})

for (const path of ['../escape.json', '/absolute.json', 'https://elsewhere.test/file.json', 'artifacts/%2e%2e/file.json', 'artifacts\\file.json', 'artifacts/../file.json']) test(`rejects unsafe artifact file ${path}`, () => {
  const fixture = candidateProcessObservedFixture(); fixture.manifest.artifacts[0].file = path
  expect(() => validateCandidateProcessManifest(fixture.manifest)).toThrow()
})

test('strict parsing rejects duplicate keys, nonfinite/overflow and bounded nesting before recursion', () => {
  for (const text of ['{"a":1,"a":2}', '{"n":1e999}', '{"n":NaN}', '['.repeat(65) + '0' + ']'.repeat(65)]) expect(() => parseCandidateProcessJson(new TextEncoder().encode(text))).toThrow()
  expect(parseCandidateProcessJson(candidateBytes({ quote: '"[[[' }))).toEqual({ quote: '"[[[' })
})

test('missing or byte-altered worker artifacts fail closed without partial physical objects', async () => {
  const fixture = candidateProcessObservedFixture(); fixture.files.delete(fixture.manifest.artifacts[0].file)
  expect((await load(fixture)).status).toBe('missing')
  const changed = candidateProcessObservedFixture()
  const result = await load(changed, (path, bytes) => new Response(path === changed.manifest.artifacts[0].file ? new Uint8Array(bytes.length) : bytes, { headers: { 'content-type': 'application/json' } }))
  expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull()
})

test('valid incomplete review retains malformed failed bytes, warmups, unlaunched slots and unknown attempted costs', async () => {
  const fixture = candidateProcessIncompleteFixture(); const result = await load(fixture)
  expect(result.errors).toEqual([]); expect(result.status).toBe('verified')
  const bundle = result.bundle!
  expect(bundle.suite.status).toBe('incomplete'); expect(bundle.slots).toHaveLength(18)
  expect(bundle.slots.filter(slot => slot.phase === 'warmup' && !slot.run.attempted)).toHaveLength(6)
  expect(bundle.suite.cost_accounting.phases.warmup.total_analysis_request_count).toBe(0)
  expect(bundle.suite.cost_accounting.phases.measured.total_analysis_request_count).toBeNull()
  expect(bundle.suite.cost_accounting.current_analysis_request_count).toBeNull()
  expect(bundle.suite.resource_accounting.worker_cpu_process_time_ns).toBeNull()
  expect(bundle.suite.resource_accounting.worker_cpu_process_time_ns_subtotal).toBeGreaterThan(0)
  expect(bundle.slots.filter(slot => slot.comparison)).toHaveLength(8)
})

for (const [name, mutate] of [
  ['solver configuration', (request: any) => { request.case.configuration.load_steps = 3 }],
  ['model path', (request: any) => { request.case.model_file = request.case.training_file }],
  ['training path', (request: any) => { request.case.training_file = request.case.model_file }],
  ['injected source declaration', (request: any) => { request.source_revision = 'f'.repeat(40) }],
  ['expected input order', (request: any) => { request.expected_inputs.reverse() }],
  ['oracle predecessor injection into online arm', (request: any) => { request.online_completion_hashes = { learned: 'sha256:' + '0'.repeat(64) } }],
] as const) test(`coherently transported changed worker ${name} cannot replace frozen inputs`, async () => {
  const fixture = candidateProcessObservedFixture(); const run = fixture.suite.runs[0]
  const entry = fixture.manifest.artifacts.find(row => row.source_path === run.request_file)!
  const request = JSON.parse(new TextDecoder().decode(fixture.files.get(entry.file)!)); mutate(request)
  const identity = replaceCandidateArtifact(fixture, String(run.request_file), request); run.request_identity = identity
  const inputs = run.resources!.inputs as any[]; Object.assign(inputs[0], identity)
  run.resources!.input_bytes_read = inputs.reduce((n, row) => n + row.byte_length, 0)
  const resourceIdentity = replaceCandidateArtifact(fixture, `${run.worker_directory}/resources.json`, run.resources)
  run.manifest!.artifacts['resources.json'] = { sha256: resourceIdentity.sha256, byte_length: resourceIdentity.byte_length }
  replaceCandidateArtifact(fixture, `${run.worker_directory}/manifest.json`, run.manifest)
  sealCandidateFixture(fixture)
  const result = await load(fixture); expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull()
})

for (const [name, mutate] of [
  ['duplicate process PID', (fixture: CandidateObservedFixture) => { const row = fixture.suite.runs[1]; row.manifest!.worker_pid = fixture.suite.runs[0].manifest!.worker_pid; row.resources!.worker_pid = row.manifest!.worker_pid }],
  ['boolean peak', (fixture: CandidateObservedFixture) => { const row = fixture.suite.runs[1]; (row.resources as any).peak_memory_bytes = true; row.resources!.per_strategy_peak_memory_bytes = true }],
  ['changed process scope', (fixture: CandidateObservedFixture) => { fixture.suite.runs[1].resources!.process_cpu_scope = 'solver_only' }],
  ['swapped resource input order', (fixture: CandidateObservedFixture) => { (fixture.suite.runs[1].resources!.inputs as any[]).reverse() }],
  ['worker timing beyond launch', (fixture: CandidateObservedFixture) => { const row = fixture.suite.runs[1]; row.resources!.worker_observed_wall_ns = row.manifest!.launch_to_exit_wall_ns + 1 }],
] as const) test(`coherently transported ${name} is rejected`, async () => {
  const fixture = candidateProcessObservedFixture(); mutate(fixture); const row = fixture.suite.runs[1]
  const resourceIdentity = replaceCandidateArtifact(fixture, `${row.worker_directory}/resources.json`, row.resources)
  row.manifest!.artifacts['resources.json'] = { sha256: resourceIdentity.sha256, byte_length: resourceIdentity.byte_length }
  replaceCandidateArtifact(fixture, `${row.worker_directory}/manifest.json`, row.manifest); sealCandidateFixture(fixture)
  expect((await load(fixture)).status).toBe('invalid')
})

test('missing cryptographic verification exposes neither review nor physical values', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: {} })
  try { const result = await load(candidateProcessObservedFixture()); expect(result.status).toBe('integrity_unavailable'); expect(result.bundle).toBeNull() }
  finally { if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor); else delete (globalThis as { crypto?: unknown }).crypto }
})

test('oversized streaming bytes, incorrect content type and redirects fail closed', async () => {
  for (const response of [
    () => new Response('{}', { headers: { 'content-type': 'text/html' } }),
    () => new Response('{}', { headers: { 'content-type': 'application/json', 'content-length': String(5 * 1024 * 1024) } }),
    () => { const response = new Response('{}', { headers: { 'content-type': 'application/json' } }); Object.defineProperty(response, 'url', { value: 'https://other.test/manifest.json' }); return response },
  ]) { const result = await load(candidateProcessObservedFixture(), response); expect(result.status).toBe('invalid'); expect(result.bundle).toBeNull() }
})

test('an oracle evaluation exception remains a requested analysis with unknown solver execution', async () => {
  const fixture = candidateProcessObservedFixture(); const run = fixture.suite.runs[11]; const report = run.report!
  const row = (report.rows as any[])[1]
  Object.assign(row, { result: null, validation: null, full_reference_verification_pass: false, full_history_verification_pass: false, response_history: null, history_limit_status: 'unavailable', history_failure: { kind: 'reference_unavailable' }, quantities: null, material_estimate: null, performance: null, terminal_limit_status: 'unavailable', violated_terminal_limits: [], violated_history_limits: [], status: 'error', solver_executed: null, failure: { kind: 'evaluation_exception', exception_type: 'RuntimeError' } })
  report.status = 'blocked'; report.cost_accounting.known_solver_execution_count = 2; report.cost_accounting.unknown_solver_execution_count = 1
  const search = replaceCandidateArtifact(fixture, `${run.worker_directory}/search.json`, report)
  const oldLength = run.resources!.report_bytes_written
  Object.assign(run.resources!, { search_sha256: search.sha256, search_byte_length: search.byte_length, report_bytes_written: search.byte_length })
  const resources = replaceCandidateArtifact(fixture, `${run.worker_directory}/resources.json`, run.resources)
  run.manifest!.artifacts['search.json'] = { sha256: search.sha256, byte_length: search.byte_length }; run.manifest!.artifacts['resources.json'] = { sha256: resources.sha256, byte_length: resources.byte_length }
  replaceCandidateArtifact(fixture, `${run.worker_directory}/manifest.json`, run.manifest)
  const suite = fixture.suite; suite.cost_accounting.phases.measured.known_solver_execution_subtotal--; suite.cost_accounting.phases.measured.unknown_solver_execution_subtotal++
  suite.resource_accounting.workers_by_strategy.oracle.measured.report_bytes_written += search.byte_length - oldLength
  const audits = suite.case_summaries[1].measured_pairs[1].oracle_audit as any
  for (const strategy of ['deterministic', 'learned']) Object.assign(audits[strategy], { oracle_verified_candidate_count: 1, oracle_unverifiable_candidate_count: 1, oracle_combined_verified_candidate_count: 1, oracle_combined_unverifiable_candidate_count: 1 })
  sealCandidateFixture(fixture)
  const result = await load(fixture); expect(result.errors).toEqual([]); expect(result.status).toBe('verified')
  expect(result.bundle!.suite.cost_accounting.current_analysis_request_count).toBe(28)
  expect(result.bundle!.suite.cost_accounting.phases.measured.unknown_solver_execution_subtotal).toBe(1)
  expect(result.bundle!.slots[11].run.report!.status).toBe('blocked')
})

test('unconfigured and already aborted requests cannot expose a previous review', async () => {
  expect(await loadCandidateProcessReview(undefined)).toEqual({ status: 'unconfigured', bundle: null, errors: [] })
  const controller = new AbortController(); controller.abort()
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: `${origin}/workbench-v2`, origin } } })
  try { expect(await loadCandidateProcessReview(url, controller.signal)).toEqual({ status: 'unconfigured', bundle: null, errors: [] }) }
  finally { if (descriptor) Object.defineProperty(globalThis, 'window', descriptor); else delete (globalThis as { window?: unknown }).window }
})
