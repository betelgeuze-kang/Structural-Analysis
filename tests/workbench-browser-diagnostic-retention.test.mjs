import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, truncateSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {
  finishWorkbenchDiagnostics, maxLedgerDescriptionBytes, maxNativeReportBytes, prepareWorkbenchDiagnostics,
  qualifyWorkbenchDiagnosticReport, workbenchDiagnosticOptions, workbenchExitCode,
} from '../scripts/workbench-browser-diagnostics.mjs'
import { sanitizedFrontendEnvironment } from '../scripts/trusted-frontend-runtime.mjs'

// Receipt-shaped unit fixtures only; these are not genuine Playwright/browser/hosted evidence.
let fixtureId = 0
function fixture() {
  const root = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'workbench-diagnostic-test-')))
  const runId = String(Date.now()) + String(process.pid) + String(++fixtureId)
  const options = { sha: 'a'.repeat(40), 'run-id': runId, 'run-attempt': '1',
    dir: path.join(os.tmpdir(), 'workbench-browser-diagnostics-' + runId + '-1') }
  writeFileSync(path.join(root, 'source.txt'), 'source identity\n')
  mkdirSync(path.join(root, 'tests', 'frontend'), { recursive: true })
  return { root, options, prepare: () => prepareWorkbenchDiagnostics(options, root, ['source.txt']),
    cleanup: () => { rmSync(root, { recursive: true, force: true }); rmSync(options.dir, { recursive: true, force: true }) } }
}
function report(root) {
  const rows = ['effect.setup', 'ui.ready.queue', 'ui.ready.commit', 'effect.cleanup']
    .map((phase, index) => ({ schema: 1, session: 1, generation: 1, sequence: index + 1, phase, monotonic_ms: index }))
  const bytes = Buffer.from(JSON.stringify({ rows, overflow: false }))
  const ledger = { schema: 1, initialStatus: 'passed', finalStatus: 'passed', initialErrors: 0,
    finalErrors: 0, originalErrorsRetained: true, releaseAttempts: 1, releaseErrors: 0,
    pageCleanup: 'complete', retrieval: 'present', rows: rows.length, overflow: false,
    bytes: bytes.length, serialization: 'complete', attachment: 'complete', diagnosticQualified: true }
  const annotations = [{ type: 'rc-initial-ready-diagnostic-ledger', description: JSON.stringify(ledger) }]
  return { config: { rootDir: root }, errors: [], stats: { expected: 1, unexpected: 0, skipped: 0, flaky: 0 },
    suites: [{ specs: [{ title: 'resume503 requires fresh failed GET before explicit null checkpoint retry',
      file: 'tests/frontend/workbench-v2-rc-workflow-browser.spec.ts', tests: [{ expectedStatus: 'passed',
        status: 'expected', annotations, results: [{ status: 'passed', retry: 0, errors: [], annotations,
          attachments: [{ name: 'rc-initial-ready-phases', contentType: 'application/json', body: bytes.toString('base64') }] }] }] }] }] }
}
const nativeResult = value => value.suites[0].specs[0].tests[0].results[0]
function writeReport(state, value) { writeFileSync(state.rawReport, JSON.stringify(value, null, 2)) }

test('hosted options require all exact identity values and reject runner overrides in both forms', () => {
  const f = fixture()
  try {
    const args = ['--diagnostics-dir=' + f.options.dir, '--diagnostics-sha=' + f.options.sha,
      '--diagnostics-run-id=' + f.options['run-id'], '--diagnostics-run-attempt=1']
    assert.equal(workbenchDiagnosticOptions(['--grep=local']).options, null)
    assert.deepEqual(workbenchDiagnosticOptions([...args, '--trace=retain-on-failure']).passthrough, ['--trace=retain-on-failure'])
    assert.throws(() => workbenchDiagnosticOptions(args.slice(1)), /identity_missing/)
    assert.throws(() => workbenchDiagnosticOptions([...args, args[0]]), /duplicate/)
    assert.throws(() => workbenchDiagnosticOptions(args.map(arg => arg.replace(f.options.sha, '../unsafe'))), /identity_invalid/)
    for (const extra of [['--reporter=json'], ['--reporter', 'line'], ['--output=elsewhere'],
      ['--output', 'elsewhere'], ['--config=alternate'], ['--grep=one'], ['--retries=1'], ['--timeout=1']]) {
      assert.throws(() => workbenchDiagnosticOptions([...args, ...extra]), /runner_override/)
    }
  } finally { f.cleanup() }
})

test('only one chosen native JSON variable enters sanitized child environment', () => {
  const env = sanitizedFrontendEnvironment('/controlled/node', { PLAYWRIGHT_JSON_OUTPUT_FILE: '/controlled/native.json' })
  assert.equal(env.PLAYWRIGHT_JSON_OUTPUT_FILE, '/controlled/native.json')
  for (const extra of [{ GITHUB_TOKEN: 'fixture-only' }, { NODE_OPTIONS: '--require=fixture' }, { PLAYWRIGHT_JSON_OUTPUT_FILE: 1 }]) {
    assert.throws(() => sanitizedFrontendEnvironment('/controlled/node', extra), /key_not_allowed/)
  }
})

test('output is exclusive and cannot redirect to outside/source or an existing symlink', () => {
  const f = fixture()
  try {
    assert.throws(() => prepareWorkbenchDiagnostics({ ...f.options, dir: path.join(f.root, 'source.txt') }, f.root, ['source.txt']), /outside_owned_temp/)
    symlinkSync(f.root, f.options.dir, 'dir')
    assert.throws(f.prepare, /EEXIST/)
    rmSync(f.options.dir)
    const state = f.prepare()
    assert.throws(f.prepare, /EEXIST/)
    assert.equal(realpathSync(state.directory), state.directory)
    assert.throws(() => prepareWorkbenchDiagnostics({ ...f.options, 'run-id': '1', dir: '/outside' }, f.root, ['../outside']), /outside_owned_temp/)
  } finally { f.cleanup() }
})

test('bounded native bytes, source linkage and matching real-format ledger are retained separately', () => {
  const f = fixture()
  try {
    const state = f.prepare(), value = report(f.root)
    writeReport(state, value)
    const bytes = readFileSync(state.rawReport)
    const completed = finishWorkbenchDiagnostics(state, 0)
    assert.equal(completed.qualified, true)
    assert.deepEqual(readFileSync(path.join(state.directory, 'native-playwright.json')), bytes)
    const receipt = JSON.parse(readFileSync(path.join(state.directory, 'retention.json'), 'utf8'))
    assert.equal(receipt.original_exit_code, 0)
    assert.equal(receipt.target.capture.rows, 4)
    assert.equal(receipt.native_report.bytes, bytes.length)
    assert.equal(receipt.generated_artifact_is_immutable_source_proof, false)
    assert.equal(JSON.parse(readFileSync(path.join(state.directory, 'run-linkage.json'), 'utf8')).source_pins.length, 1)
  } finally { f.cleanup() }
})

test('missing report and failed native status cannot become a passing invocation', () => {
  const f = fixture()
  try {
    const state = f.prepare()
    const completed = finishWorkbenchDiagnostics(state, 2)
    assert.equal(completed.qualified, false)
    assert.equal(completed.receipt.original_exit_code, 2)
    assert.equal(workbenchExitCode(2, false), 2)
    assert.equal(workbenchExitCode(1, true), 1)
    assert.equal(workbenchExitCode(0, false), 1)
    assert.equal(workbenchExitCode(0, true), 0)
    assert.equal(JSON.parse(readFileSync(path.join(state.directory, 'retention.json'), 'utf8')).diagnosticQualified, false)
  } finally { f.cleanup() }
})

test('oversized raw report is not read/copied into the artifact allowlist', () => {
  const f = fixture()
  try {
    const state = f.prepare()
    writeFileSync(state.rawReport, '')
    truncateSync(state.rawReport, maxNativeReportBytes + 1)
    const completed = finishWorkbenchDiagnostics(state, 0)
    assert.equal(completed.qualified, false)
    assert.match(completed.receipt.reason, /oversize/)
    assert.throws(() => readFileSync(path.join(state.directory, 'native-playwright.json')), /ENOENT/)
  } finally { f.cleanup() }
})

test('invalid native JSON is preserved within budget with a false qualification receipt', () => {
  const f = fixture()
  try {
    const state = f.prepare()
    writeFileSync(state.rawReport, '{ invalid native JSON')
    const completed = finishWorkbenchDiagnostics(state, 1)
    assert.equal(completed.qualified, false)
    assert.equal(completed.receipt.original_exit_code, 1)
    assert.equal(readFileSync(path.join(state.directory, 'native-playwright.json'), 'utf8'), '{ invalid native JSON')
  } finally { f.cleanup() }
})

test('native failure and report-root/target/ledger/body omissions are qualification failures', () => {
  const f = fixture()
  try {
    for (const mutate of [
      value => { value.stats.unexpected = 1 },
      value => { value.config.rootDir = '/different-root' },
      value => { value.suites = [] },
      value => { value.suites[0].specs[0].tests[0].annotations = [] },
      value => { nativeResult(value).annotations = [] },
      value => { nativeResult(value).attachments = [] },
      value => { nativeResult(value).status = 'failed'; nativeResult(value).errors = [{ message: 'original failure' }] },
      value => { nativeResult(value).attachments[0].body = Buffer.from('{"rows":[],"overflow":false}').toString('base64') },
      value => { nativeResult(value).attachments[0].body = 'not-base64' },
      value => {
        const test = value.suites[0].specs[0].tests[0]
        const ledger = JSON.parse(test.annotations[0].description)
        ledger.diagnosticQualified = false
        test.annotations[0].description = JSON.stringify(ledger)
      },
    ]) {
      const value = report(f.root); mutate(value)
      assert.throws(() => qualifyWorkbenchDiagnosticReport(value, f.root), /diagnostic_/)
    }
  } finally { f.cleanup() }
})

test('source drift and native-output symlinks are visible false qualification', () => {
  for (const mode of ['source', 'symlink']) {
    const f = fixture()
    try {
      const state = f.prepare()
      if (mode === 'source') { writeReport(state, report(f.root)); writeFileSync(path.join(f.root, 'source.txt'), 'changed\n') }
      else { writeFileSync(path.join(f.root, 'untrusted.json'), JSON.stringify(report(f.root))); symlinkSync(path.join(f.root, 'untrusted.json'), state.rawReport) }
      const completed = finishWorkbenchDiagnostics(state, 0)
      assert.equal(completed.qualified, false)
      assert.match(completed.receipt.reason, mode === 'source' ? /source_changed/ : /file_unsafe/)
    } finally { f.cleanup() }
  }
})

function setLedger(value, ledger) {
  const annotations = [{ type: 'rc-initial-ready-diagnostic-ledger', description: JSON.stringify(ledger) }]
  const test = value.suites[0].specs[0].tests[0]
  test.annotations = annotations
  nativeResult(value).annotations = annotations
}

test('qualification ledger has exactly known bounded enum/integer/boolean fields', () => {
  const f = fixture()
  try {
    const value = report(f.root)
    const original = JSON.parse(value.suites[0].specs[0].tests[0].annotations[0].description)
    const selected = qualifyWorkbenchDiagnosticReport(value, f.root)
    assert.deepEqual(selected.ledger, original)
    assert.equal(Object.keys(selected.ledger).length, 16)
    assert.ok(Buffer.byteLength(JSON.stringify(selected.ledger)) < maxLedgerDescriptionBytes)
    for (const mutate of [
      ledger => { ledger.extra = 'fixture-only unknown string' },
      ledger => { ledger.extra = { nested: 'fixture-only unknown object' } },
      ledger => { delete ledger.releaseAttempts },
      ledger => { ledger.releaseAttempts = '1' },
      ledger => { ledger.releaseAttempts = Number.MAX_SAFE_INTEGER + 1 },
      ledger => { ledger.rows = '4' },
      ledger => { ledger.bytes = true },
      ledger => { ledger.initialErrors = '0' },
      ledger => { ledger.pageCleanup = { state: 'complete' } },
      ledger => { ledger.originalErrorsRetained = 'true' },
    ]) {
      const invalid = report(f.root), ledger = { ...original }; mutate(ledger)
      setLedger(invalid, ledger)
      assert.throws(() => qualifyWorkbenchDiagnosticReport(invalid, f.root), /diagnostic_ledger_/)
    }
    const oversized = report(f.root)
    const annotations = oversized.suites[0].specs[0].tests[0].annotations
    annotations[0].description += ' '.repeat(maxLedgerDescriptionBytes + 1)
    assert.throws(() => qualifyWorkbenchDiagnosticReport(oversized, f.root), /description_budget/)
  } finally { f.cleanup() }
})

test('native report roots support repository-relative and nested test-directory forms only', () => {
  const f = fixture()
  try {
    const repository = report(f.root)
    const nested = report(f.root)
    nested.config.rootDir = path.join(f.root, 'tests', 'frontend')
    nested.suites[0].specs[0].file = 'workbench-v2-rc-workflow-browser.spec.ts'
    assert.deepEqual(qualifyWorkbenchDiagnosticReport(nested, f.root), qualifyWorkbenchDiagnosticReport(repository, f.root))
    for (const mutate of [
      value => { value.config.rootDir = os.tmpdir() },
      value => { value.config.rootDir = 'tests/frontend' },
      value => { value.config.rootDir += '/.' },
      value => { value.suites[0].specs[0].file = path.join(f.root, 'tests', 'frontend', 'workbench-v2-rc-workflow-browser.spec.ts') },
      value => { value.suites[0].specs[0].file = '../frontend/workbench-v2-rc-workflow-browser.spec.ts' },
      value => { value.suites[0].specs.push(structuredClone(value.suites[0].specs[0])) },
    ]) {
      const invalid = structuredClone(nested); mutate(invalid)
      assert.throws(() => qualifyWorkbenchDiagnosticReport(invalid, f.root), /diagnostic_/)
    }
    const alias = path.join(f.root, 'frontend-alias')
    symlinkSync(nested.config.rootDir, alias, 'dir')
    nested.config.rootDir = alias
    assert.throws(() => qualifyWorkbenchDiagnosticReport(nested, f.root), /report_root_unsafe/)
  } finally { f.cleanup() }
})

test('unknown ledger data remains raw native evidence and never enters qualified retention', () => {
  const f = fixture()
  try {
    const state = f.prepare(), value = report(f.root)
    const ledger = JSON.parse(value.suites[0].specs[0].tests[0].annotations[0].description)
    ledger.extra = { text: 'fixture-only raw diagnostic data' }
    setLedger(value, ledger)
    writeReport(state, value)
    const bytes = readFileSync(state.rawReport)
    const completed = finishWorkbenchDiagnostics(state, 1)
    assert.equal(completed.qualified, false)
    assert.equal(completed.receipt.original_exit_code, 1)
    assert.equal(completed.receipt.target, null)
    assert.equal(completed.receipt.reason, 'diagnostic_ledger_shape')
    assert.equal(workbenchExitCode(1, completed.qualified), 1)
    assert.deepEqual(readFileSync(path.join(state.directory, 'native-playwright.json')), bytes)
    const retained = readFileSync(path.join(state.directory, 'retention.json'), 'utf8')
    assert.equal(retained.includes('fixture-only raw diagnostic data'), false)
  } finally { f.cleanup() }
})
