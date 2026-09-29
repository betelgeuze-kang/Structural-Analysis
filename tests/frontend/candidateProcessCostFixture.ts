import { readFileSync } from 'node:fs'
import { canonicalJson } from '../../src/workbench-v2/model/checksum'
import type { CandidateProcessCostSidecar } from '../../src/workbench-v2/model/candidateProcessSchema'
import { candidateBytes, candidateDigest, candidateProcessObservedFixture, type CandidateObservedFixture } from './candidateProcessObservedFixture'
import { candidateProcessStopFixture } from './candidateProcessStopFixture'

/** Frozen Python producer output on the historical observed suite; no worker is rerun. */
export function candidateProcessCostFixture(): CandidateObservedFixture {
  const fixture = candidateProcessObservedFixture()
  const bytes = new Uint8Array(readFileSync(new URL('../fixtures/fiber_frame_candidate_review/observed-cost-sidecar.json', import.meta.url)))
  const sidecar = JSON.parse(new TextDecoder().decode(bytes)) as CandidateProcessCostSidecar
  fixture.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v4'
  fixture.manifest.source_suite_schema_version = fixture.suite.schema_version as CandidateProcessManifestSuiteVersion
  fixture.manifest.cost_audit_file = 'cost/candidate-pool-audit.json'
  fixture.manifest.cost_audit_byte_length = bytes.length
  fixture.manifest.cost_audit_sha256 = candidateDigest(bytes)
  fixture.manifest.cost_audit_hash = sidecar.report_hash
  fixture.files.set(fixture.manifest.cost_audit_file, bytes)
  fixture.files.set('manifest.json', candidateBytes(fixture.manifest))
  return fixture
}

type CandidateProcessManifestSuiteVersion = NonNullable<CandidateObservedFixture['manifest']['source_suite_schema_version']>

/** Test-only coherent transport reseal; it does not assert producer provenance. */
export function resealCandidateCostFixture(fixture: CandidateObservedFixture, sidecar: CandidateProcessCostSidecar): void {
  sidecar.source_suite_report_hash = fixture.suite.report_hash
  sidecar.source_suite_identity_hash = fixture.suite.suite_identity_hash
  sidecar.source_suite_sha256 = fixture.manifest.suite_sha256
  const unsealed = { ...sidecar } as Record<string, unknown>
  delete unsealed.report_hash
  sidecar.report_hash = candidateDigest(new TextEncoder().encode(canonicalJson(unsealed)))
  const bytes = new TextEncoder().encode(canonicalJson(sidecar))
  fixture.manifest.cost_audit_hash = sidecar.report_hash
  fixture.manifest.cost_audit_byte_length = bytes.length
  fixture.manifest.cost_audit_sha256 = candidateDigest(bytes)
  fixture.files.set(fixture.manifest.cost_audit_file!, bytes)
  fixture.files.set('manifest.json', candidateBytes(fixture.manifest))
}

/** Synthetic stop transport: the selected baseline precedes an unattempted, cheaper oracle-feasible shortlist member. */
export function candidateProcessStopCostFixture(): CandidateObservedFixture {
  const fixture = candidateProcessStopFixture()
  const observed = candidateProcessCostFixture()
  const sidecar = JSON.parse(new TextDecoder().decode(observed.files.get('cost/candidate-pool-audit.json')!)) as CandidateProcessCostSidecar
  fixture.manifest.schema_version = 'rc-fiber-candidate-process-review-bundle.v4'
  fixture.manifest.source_suite_schema_version = fixture.suite.schema_version as CandidateProcessManifestSuiteVersion
  fixture.manifest.cost_audit_file = 'cost/candidate-pool-audit.json'
  const stoppedCase = fixture.suite.declaration.cases[0].case_id
  for (const group of sidecar.groups) {
    for (const strategy of ['deterministic', 'learned', 'oracle'] as const) {
      const run = fixture.suite.runs.find(row => row.case_id === group.case_id && row.phase === group.phase && row.repetition === group.repetition && row.strategy === strategy)!
      group.worker_report_hashes[strategy] = run.report!.report_hash
    }
    if (group.case_id !== stoppedCase) continue
    const audit = group.audit!
    audit.arms.learned = structuredClone(audit.arms.deterministic)
    audit.arms.learned.missed_cheaper_feasible_candidate_ids = []
    audit.arms.learned.missed_cheaper_feasible_count = 0
    // The frozen planned shortlist still contains near-limit; execution stopped at the baseline.
    // Its oracle-feasible lower estimate therefore counts only outside the attempted prefix.
  }
  resealCandidateCostFixture(fixture, sidecar)
  return fixture
}

/** Change every repeated price identity and reseal only the transport DAG.
 * Python logical identities remain labels, as in the other synthetic fixtures.
 */
export function replaceCandidateCostPriceHash(fixture: CandidateObservedFixture, replacement: string): void {
  const original = String((fixture.suite.declaration.cases[0].input_binding as Record<string, any>).price_basis.price_table_hash)
  let previous = new Map([...fixture.files].map(([path, bytes]) => [path, candidateDigest(bytes)]))
  for (const [path, bytes] of fixture.files) fixture.files.set(path, new TextEncoder().encode(new TextDecoder().decode(bytes).split(original).join(replacement)))
  for (let round = 0; ; round++) {
    if (round >= 32) throw new Error('synthetic transport digest graph did not converge')
    const replacements = new Map<string, string>()
    for (const [path, digest] of previous) { const next = candidateDigest(fixture.files.get(path)!); if (next !== digest) replacements.set(digest, next) }
    if (!replacements.size) break
    previous = new Map([...fixture.files].map(([path, bytes]) => [path, candidateDigest(bytes)]))
    for (const [path, bytes] of fixture.files) {
      let text = new TextDecoder().decode(bytes)
      for (const [from, to] of replacements) text = text.split(from).join(to)
      fixture.files.set(path, new TextEncoder().encode(text))
    }
  }
  fixture.suite = JSON.parse(new TextDecoder().decode(fixture.files.get('suite.json')!))
  fixture.manifest = JSON.parse(new TextDecoder().decode(fixture.files.get('manifest.json')!))
  resealCandidateCostFixture(fixture, JSON.parse(new TextDecoder().decode(fixture.files.get(fixture.manifest.cost_audit_file!)!)))
}
