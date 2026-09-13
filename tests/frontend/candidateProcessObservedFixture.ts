import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import type { CandidateProcessManifest, CandidateProcessSuite } from '../../src/workbench-v2/model/candidateProcessSchema'

export const candidateBytes = (value: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(value))
export const candidateDigest = (value: Uint8Array): string => `sha256:${createHash('sha256').update(value).digest('hex')}`
export interface CandidateObservedFixture { files: Map<string, Uint8Array>; manifest: CandidateProcessManifest; suite: CandidateProcessSuite }
let archive: { files: { path: string; utf8: string; sha256: string; byte_length: number }[]; suite_file: string; expected_comparisons: { case_id: string; phase: 'measured'; repetition: number; strategy: 'deterministic' | 'learned'; directory: string }[] } | undefined

/** Exact historical producer bytes in synthetic packaging. This is not a new exporter or solver observation. */
export function candidateProcessObservedFixture(): CandidateObservedFixture {
  archive ??= JSON.parse(gunzipSync(readFileSync(new URL('../fixtures/fiber_frame_candidate_review/observed-suite.json.gz', import.meta.url))).toString('utf8'))
  const source = new Map<string, Uint8Array>()
  for (const entry of archive!.files) {
    const bytes = new TextEncoder().encode(entry.utf8)
    if (bytes.length !== entry.byte_length || candidateDigest(bytes) !== entry.sha256) throw new Error(`historical fixture byte identity mismatch: ${entry.path}`)
    source.set(entry.path, bytes)
  }
  const suiteBytes = source.get(archive!.suite_file)!
  const suite = JSON.parse(new TextDecoder().decode(suiteBytes)) as CandidateProcessSuite
  const files = new Map<string, Uint8Array>([['suite.json', suiteBytes]])
  const artifacts: CandidateProcessManifest['artifacts'] = []
  // Recover the recorded absolute source label through the frozen suite declaration.
  const inputs = suite.declaration.inputs as { path: string }[]
  const originalRoot = inputs[0].path.slice(0, inputs[0].path.lastIndexOf('/suite/inputs/'))
  let index = 0
  for (const [path, bytes] of source) {
    if (!path.startsWith('suite/') || path === archive!.suite_file) continue
    const file = `artifacts/file-${String(index++).padStart(5, '0')}.json`
    files.set(file, bytes)
    artifacts.push({ source_path: `${originalRoot}/${path}`, file, byte_length: bytes.length, sha256: candidateDigest(bytes) })
  }
  const comparisons: CandidateProcessManifest['comparisons'] = []
  for (const entry of archive!.expected_comparisons) {
    const run = suite.runs.find(row => row.case_id === entry.case_id && row.phase === entry.phase && row.repetition === entry.repetition && row.strategy === entry.strategy)!
    const directory = `comparisons/slot-${String(suite.runs.indexOf(run)).padStart(5, '0')}`
    const bytes = source.get(`${entry.directory}/manifest.json`)!
    files.set(`${directory}/manifest.json`, bytes)
    files.set(`${directory}/comparison.json`, source.get(`${entry.directory}/comparison.json`)!)
    comparisons.push({ case_id: entry.case_id, phase: entry.phase, repetition: entry.repetition, strategy: entry.strategy, worker_report_hash: run.report!.report_hash, manifest_file: `${directory}/manifest.json`, manifest_byte_length: bytes.length, manifest_sha256: candidateDigest(bytes) })
  }
  const manifest: CandidateProcessManifest = { schema_version: 'rc-fiber-candidate-process-review-bundle.v1', source_revision: suite.declaration.source_revision as string, suite_file: 'suite.json', suite_byte_length: suiteBytes.length, suite_sha256: candidateDigest(suiteBytes), suite_report_hash: suite.report_hash, suite_identity_hash: suite.suite_identity_hash, artifacts, comparisons }
  files.set('manifest.json', candidateBytes(manifest))
  return { files, manifest, suite }
}

/** Reseal transported JSON bytes only. Deliberately never recompute Python canonical identities in JavaScript. */
export function sealCandidateFixture(fixture: CandidateObservedFixture): void {
  const suiteBytes = candidateBytes(fixture.suite)
  fixture.files.set('suite.json', suiteBytes)
  fixture.manifest.suite_byte_length = suiteBytes.length; fixture.manifest.suite_sha256 = candidateDigest(suiteBytes)
  fixture.files.set('manifest.json', candidateBytes(fixture.manifest))
}

export function replaceCandidateArtifact(fixture: CandidateObservedFixture, sourcePath: string, value: unknown | Uint8Array): { path: string; byte_length: number; sha256: string } {
  const entry = fixture.manifest.artifacts.find(row => row.source_path === sourcePath)!
  const bytes = value instanceof Uint8Array ? value : candidateBytes(value)
  fixture.files.set(entry.file, bytes); entry.byte_length = bytes.length; entry.sha256 = candidateDigest(bytes)
  return { path: sourcePath, byte_length: bytes.length, sha256: entry.sha256 }
}

function stats(values: number[]) {
  values.sort((a, b) => a - b); const n = values.length; const average = values.reduce((a, b) => a + b, 0) / n
  return { count: n, minimum: n ? values[0] : null, maximum: n ? values[n - 1] : null, median: n ? n % 2 ? values[Math.floor(n / 2)] : (values[n / 2 - 1] + values[n / 2]) / 2 : null, population_standard_deviation: n ? Math.sqrt(values.reduce((sum, v) => sum + (v - average) ** 2, 0) / n) : null }
}

/** Synthetic failed oracle plus unlaunched warmup slots. Historical numerical rows remain exact; this is contract evidence only. */
export function candidateProcessIncompleteFixture(): CandidateObservedFixture {
  const fixture = candidateProcessObservedFixture(); const suite = fixture.suite
  const failed = suite.runs[suite.runs.length - 1]
  failed.report_contract_pass = false; failed.resource_contract_pass = false; failed.report = null; failed.resources = null; failed.manifest = null
  failed.failure = { report: 'synthetic_worker_report_invalid', resources: 'synthetic_resource_unavailable' }
  replaceCandidateArtifact(fixture, `${failed.worker_directory}/search.json`, new TextEncoder().encode('{unfinished worker output'))
  const warmup = suite.runs.slice(0, 6).map(run => {
    const row = { ...run, phase: 'warmup' as const, attempted: false, report_contract_pass: false, resource_contract_pass: false, report: null, resources: null, manifest: null, parent_slot_observed_wall_ns: 0, parent_slot_cpu_time_ns: 0, worker_directory: `${run.worker_directory}-synthetic-warmup`, request_file: `${run.request_file}-synthetic-warmup`, failure: { report: 'frozen_input_changed', resources: 'frozen_input_changed' } }
    delete row.request_identity
    return row
  })
  suite.runs = [...warmup, ...suite.runs]
  const inputs = suite.declaration.inputs as { path: string; byte_length: number; sha256: string }[]
  const readArtifact = (path: string): any => JSON.parse(new TextDecoder().decode(fixture.files.get(fixture.manifest.artifacts.find(row => row.source_path === path)!.file)!))
  const original = readArtifact(inputs[0].path); original.warmups = 1
  inputs[0] = replaceCandidateArtifact(fixture, inputs[0].path, original)
  const frozen = readArtifact(inputs[inputs.length - 1].path); frozen.configuration.warmups = 1; frozen.identities = inputs.slice(0, -1)
  inputs[inputs.length - 1] = replaceCandidateArtifact(fixture, inputs[inputs.length - 1].path, frozen)
  ;(suite.declaration.configuration as any).warmups = 1
  const cost = suite.cost_accounting; const measured = cost.phases.measured
  measured.validated_report_count--; measured.unknown_request_slots++; measured.validated_oracle_request_subtotal -= 3; measured.known_solver_execution_subtotal -= 3; measured.total_analysis_request_count = null
  cost.phases.warmup = { ...cost.phases.warmup, declared_worker_slots: 6, not_launched_slots: 6 }
  cost.current_analysis_request_count = null; cost.total_analysis_request_count_including_training_warmups_and_oracles = null
  const resources = suite.resource_accounting
  const selected = suite.runs.filter(run => run.strategy === 'oracle' && run.resource_contract_pass)
  const oracle = resources.workers_by_strategy.oracle.measured
  oracle.observed_workers = selected.length
  oracle.worker_cpu_process_time_ns = stats(selected.map(run => run.resources!.cpu_process_time_ns))
  oracle.launch_to_exit_wall_ns = stats(selected.map(run => run.manifest!.launch_to_exit_wall_ns))
  oracle.peak_memory_bytes = stats(selected.map(run => run.resources!.peak_memory_bytes!))
  for (const key of ['input_bytes_read', 'input_read_wall_ns', 'report_bytes_written', 'report_write_flush_fsync_wall_ns']) oracle[key] = selected.reduce((total, run) => total + Number(run.resources![key]), 0)
  for (const strategy of ['deterministic', 'learned', 'oracle'] as const) resources.workers_by_strategy[strategy].warmup.declared_slots = 2
  resources.validated_resource_worker_count = 11
  resources.worker_cpu_process_time_ns_subtotal = suite.runs.filter(run => run.resource_contract_pass).reduce((total, run) => total + run.resources!.cpu_process_time_ns, 0)
  resources.worker_cpu_process_time_ns = null; resources.current_parent_plus_workers_cpu_time_ns = null
  for (const summary of suite.case_summaries) { summary.all_online_attempts_ready = false; summary.projected_reuses_to_amortize_this_training_artifact = null }
  const pair = suite.case_summaries.find(row => row.case_id === failed.case_id)!.measured_pairs[1]
  const missing = { missed_feasible_count: null, false_safe_count: null, predicted_safe_unverifiable_count: null, oracle_verified_candidate_count: null, reason: 'exhaustive_oracle_not_run', oracle_combined_verified_candidate_count: null, oracle_combined_unverifiable_candidate_count: null, predicted_history_safety_available: false }
  pair.oracle_audit = { learned: { ...missing }, deterministic: { ...missing, false_safe_candidate_ids: null, predicted_safe_unverifiable_candidate_ids: null, false_safe_applicability: 'strategy_makes_no_predicted_safety_claim' } }
  suite.status = 'incomplete'; suite.claims.report_contract_pass = false; suite.claims.local_timing_evidence_eligible = false
  sealCandidateFixture(fixture)
  return fixture
}
