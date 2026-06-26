// Build a deployable, read-only evidence bundle for Workbench v2.
//
// Rules (enforced, not optional):
// - originals are never modified; the bundle is a copy under public/evidence/;
// - source_path and sha256 are preserved in the manifest;
// - if the sources do not share a single source_commit_sha, the build FAILS
//   (a bundle must be one consistent snapshot, not a mix of commits);
// - sensitive / customer data must not be included (a scan fails the build);
// - --check verifies consistency without writing anything.

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const args = process.argv.slice(2)
const checkOnly = args.includes('--check')

// --root <dir> overrides the repository root the builder reads sources from.
// This keeps the production behaviour (repo root) the default while letting a
// contract test point the builder at a synthetic fixture tree.
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const rootArgIdx = args.indexOf('--root')
const rootDir = rootArgIdx >= 0 ? path.resolve(args[rootArgIdx + 1]) : repoRoot

const outArgIdx = args.indexOf('--out')
const outDir = path.resolve(rootDir, outArgIdx >= 0 ? args[outArgIdx + 1] : 'public/evidence')

// --include-case <path> optionally includes a workbench-case.json in the bundle.
// The case's sourceCommitSha must match the evidence sources (same single-commit
// rule). If omitted, the bundle contains only readiness artifacts; the workbench
// case can be served separately or left as MISSING (honest).
const caseArgIdx = args.indexOf('--include-case')
const includeCasePath = caseArgIdx >= 0 ? path.resolve(rootDir, args[caseArgIdx + 1]) : null

// id -> source (read-only original) + bundle (copy path, relative to outDir)
const SOURCES = [
  { id: 'product_readiness', label: 'Product readiness', source: 'implementation/phase1/release_evidence/productization/product_readiness_snapshot.json', bundle: 'readiness/product-readiness.json' },
  { id: 'p1_benchmark_breadth', label: 'P1 benchmark breadth', source: 'implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json', bundle: 'readiness/benchmark-breadth.json' },
  { id: 'fresh_full_validation', label: 'Fresh full validation lane', source: 'implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json', bundle: 'readiness/fresh-validation.json' },
  { id: 'evidence_console_scope', label: 'Evidence Console scope', source: 'implementation/phase1/release_evidence/productization/evidence_console_scope_status.json', bundle: 'readiness/evidence-console-scope.json' },
  { id: 'real_project_corpus', label: 'Real project corpus (measured)', source: 'implementation/phase1/real_project_corpus_measured_status.json', bundle: 'readiness/real-project-corpus.json' },
]

// Conservative sensitive-data signals (key names + value patterns). We avoid
// over-broad words; these are clear PII / secret markers.
const SENSITIVE_KEY = /(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key|client[_-]?secret|ssn|social_security)/i
const EMAIL = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/
const CREDIT_CARD = /\b(?:\d[ -]*?){13,16}\b/

function fail(message) {
  console.error(`evidence-bundle: FAIL — ${message}`)
  process.exit(1)
}

function sha256(buffer) {
  return 'sha256:' + crypto.createHash('sha256').update(buffer).digest('hex')
}

function scanSensitive(id, raw, obj) {
  if (EMAIL.test(raw)) return `${id}: contains an email-like value`
  if (CREDIT_CARD.test(raw.replace(/"[^"]*sha256[^"]*"/gi, ''))) {
    // ignore long hashes; only flag digit groups that look like card numbers
    const stripped = raw.replace(/[a-f0-9]{32,}/gi, '')
    if (CREDIT_CARD.test(stripped)) return `${id}: contains a credit-card-like number`
  }
  const keys = []
  const walk = (v) => {
    if (Array.isArray(v)) v.forEach(walk)
    else if (v && typeof v === 'object') for (const k of Object.keys(v)) { keys.push(k); walk(v[k]) }
  }
  walk(obj)
  const bad = keys.find((k) => SENSITIVE_KEY.test(k))
  if (bad) return `${id}: contains a sensitive key "${bad}"`
  return null
}

function main() {
  const loaded = []
  for (const def of SOURCES) {
    const abs = path.join(rootDir, def.source)
    if (!fs.existsSync(abs)) fail(`source not found: ${def.source}`)
    const raw = fs.readFileSync(abs) // bytes, for an exact checksum
    let obj
    try {
      obj = JSON.parse(raw.toString('utf8'))
    } catch {
      fail(`source is not valid JSON: ${def.source}`)
    }
    const commit = typeof obj.source_commit_sha === 'string' ? obj.source_commit_sha : null
    if (!commit) fail(`source missing source_commit_sha: ${def.source}`)
    const sensitive = scanSensitive(def.id, raw.toString('utf8'), obj)
    if (sensitive) fail(`sensitive data gate: ${sensitive}`)
    loaded.push({ def, raw, sha: sha256(raw), commit })
  }

  const commits = Array.from(new Set(loaded.map((l) => l.commit)))
  if (commits.length !== 1) {
    fail(
      `source commit mismatch — bundle must be a single snapshot. Found ${commits.length} commits: ` +
        commits.map((c) => c.slice(0, 8)).join(', ') +
        '. Regenerate all evidence at one commit, then rebuild.',
    )
  }
  const sourceCommitSha = commits[0]

  if (checkOnly) {
    console.log(`evidence-bundle: OK (check) — ${loaded.length} sources at commit ${sourceCommitSha.slice(0, 8)}`)
    return
  }

  // Optionally include a workbench case file in the bundle (same-commit gate).
  let caseArtifact = null
  if (includeCasePath) {
    if (!fs.existsSync(includeCasePath)) fail(`--include-case file not found: ${includeCasePath}`)
    const caseRaw = fs.readFileSync(includeCasePath)
    let caseObj
    try { caseObj = JSON.parse(caseRaw.toString('utf8')) } catch { fail('--include-case is not valid JSON') }
    const caseSha = sha256(caseRaw)
    const caseCommit = caseObj?.provenance?.sourceCommitSha ?? null
    if (caseCommit && caseCommit !== 'demo-local' && caseCommit !== 'sample-not-a-release' && caseCommit !== sourceCommitSha) {
      fail(
        `--include-case source commit (${(caseCommit ?? '').slice(0, 8)}) does not match the evidence sources ` +
          `(${sourceCommitSha.slice(0, 8)}). The case must be generated at the same commit as the readiness bundle.`,
      )
    }
    const sensitive = scanSensitive('workbench_case', caseRaw.toString('utf8'), caseObj)
    if (sensitive) fail(`sensitive data gate (case): ${sensitive}`)
    caseArtifact = { raw: caseRaw, sha: caseSha, sourcePath: path.relative(rootDir, includeCasePath) }
  }

  // Write the read-only copy + manifest. Originals are untouched.
  fs.rmSync(outDir, { recursive: true, force: true })
  fs.mkdirSync(path.join(outDir, 'readiness'), { recursive: true })

  const artifacts = loaded.map(({ def, raw, sha }) => {
    fs.writeFileSync(path.join(outDir, def.bundle), raw)
    return { id: def.id, label: def.label, path: def.bundle, source_path: def.source, sha256: sha, read_only: true }
  })

  if (caseArtifact) {
    fs.writeFileSync(path.join(outDir, 'workbench-case.json'), caseArtifact.raw)
    artifacts.push({
      id: 'workbench_case',
      label: 'Workbench case (analysis result)',
      path: 'workbench-case.json',
      source_path: caseArtifact.sourcePath,
      sha256: caseArtifact.sha,
      read_only: true,
    })
  }

  const manifest = {
    schema_version: 'workbench-evidence-manifest.v1',
    generated_at: new Date().toISOString(),
    source_commit_sha: sourceCommitSha,
    artifacts,
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
  console.log(`evidence-bundle: wrote ${artifacts.length} artifacts + manifest to ${path.relative(rootDir, outDir)} at commit ${sourceCommitSha.slice(0, 8)}`)
}

main()
