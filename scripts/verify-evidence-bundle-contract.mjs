// Contract test for the evidence-bundle builder.
//
// The builder enforces hard rules (single source commit, sensitive-data gate,
// required source_commit_sha). This test proves those rules hold by running the
// builder with --check against synthetic fixture trees under a temp directory,
// plus the real repository sources. It writes nothing into the repo and never
// touches the originals.
//
// Expected outcomes:
//   single-commit fixture  -> PASS  (exit 0)
//   mixed-commit fixture    -> BLOCKED (exit 1)
//   sensitive-data fixture  -> BLOCKED (exit 1)
//   missing-commit fixture  -> BLOCKED (exit 1)
//   real repository sources -> reported as-is (PASS or BLOCKED), not asserted
//
// Usage: node scripts/verify-evidence-bundle-contract.mjs

import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..')
const builder = path.join(here, 'build-workbench-evidence-bundle.mjs')

// Source layout the builder reads (must mirror SOURCES in the builder).
const SOURCE_PATHS = [
  'implementation/phase1/release_evidence/productization/product_readiness_snapshot.json',
  'implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json',
  'implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json',
  'implementation/phase1/release_evidence/productization/evidence_console_scope_status.json',
  'implementation/phase1/real_project_corpus_measured_status.json',
]

function writeFixture(root, files) {
  for (const [rel, obj] of Object.entries(files)) {
    const abs = path.join(root, rel)
    fs.mkdirSync(path.dirname(abs), { recursive: true })
    fs.writeFileSync(abs, JSON.stringify(obj, null, 2) + '\n')
  }
}

function makeSources(commitFn, extra = () => ({})) {
  const files = {}
  SOURCE_PATHS.forEach((rel, i) => {
    files[rel] = {
      schema_version: 'fixture.v1',
      source_commit_sha: commitFn(i),
      status: 'fixture',
      ...extra(i, rel),
    }
  })
  return files
}

function runCheck(root) {
  const res = spawnSync(process.execPath, [builder, '--check', '--root', root], {
    encoding: 'utf8',
    env: { ...process.env, NODE_OPTIONS: '' },
  })
  return { code: res.status, out: (res.stdout || '') + (res.stderr || '') }
}

const SINGLE = 'a'.repeat(40)
const OTHER = 'b'.repeat(40)

const cases = [
  {
    name: 'single-commit fixture',
    expect: 'pass',
    build: (root) => writeFixture(root, makeSources(() => SINGLE)),
  },
  {
    name: 'mixed-commit fixture',
    expect: 'block',
    build: (root) => writeFixture(root, makeSources((i) => (i === 0 ? OTHER : SINGLE))),
  },
  {
    name: 'sensitive-data fixture',
    expect: 'block',
    build: (root) =>
      writeFixture(root, makeSources(() => SINGLE, (i) => (i === 0 ? { contact_email: 'someone@example.com' } : {}))),
  },
  {
    name: 'missing-commit fixture',
    expect: 'block',
    build: (root) => {
      const files = makeSources(() => SINGLE)
      delete files[SOURCE_PATHS[0]].source_commit_sha
      writeFixture(root, files)
    },
  },
]

const tmpBase = fs.mkdtempSync(path.join(os.tmpdir(), 'evidence-contract-'))
let failures = 0

for (const c of cases) {
  const root = path.join(tmpBase, c.name.replace(/\W+/g, '_'))
  fs.mkdirSync(root, { recursive: true })
  c.build(root)
  const { code, out } = runCheck(root)
  const passed = code === 0
  const ok = c.expect === 'pass' ? passed : !passed
  console.log(`${ok ? 'OK  ' : 'FAIL'}  ${c.name} -> expected ${c.expect}, exit=${code}`)
  if (!ok) {
    failures += 1
    console.log(`      builder output: ${out.trim()}`)
  }
}

// Real repository sources: report state, do not assert (it is legitimately
// BLOCKED today because evidence was generated at different commits).
{
  const { code, out } = runCheck(repoRoot)
  const label = code === 0 ? 'PASS (single snapshot)' : 'BLOCKED (mixed/incomplete)'
  console.log(`INFO  real repository sources -> ${label}`)
  console.log(`      ${out.trim()}`)
}

fs.rmSync(tmpBase, { recursive: true, force: true })

if (failures > 0) {
  console.error(`\nevidence-bundle-contract: ${failures} case(s) did not hold`)
  process.exit(1)
}
console.log('\nevidence-bundle-contract: all rules hold')
