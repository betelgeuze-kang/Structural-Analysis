import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, truncateSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {
  controlOptions, controlsSourceUnchanged, maxControlReportBytes, negativeTitles, positiveTitles,
  prepareControls, qualifyControlsNative, retainControlsNative,
} from '../scripts/rc-observer-controls-artifacts.mjs'

// Receipt-shaped unit fixtures only. They are not genuine browser/hosted/solver evidence.
let fixtureId = 0
function fixture() {
  const root = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'rc-control-unit-')))
  mkdirSync(path.join(root, 'tests', 'frontend'), { recursive: true })
  writeFileSync(path.join(root, 'source.txt'), 'owned source identity\n')
  const run = String(Date.now()) + String(process.pid) + String(++fixtureId)
  const options = { sha: 'a'.repeat(40), 'run-id': run, 'run-attempt': '1',
    dir: path.join(os.tmpdir(), 'rc-observer-controls-' + run + '-1') }
  return { root, options, prepare: () => prepareControls(options, root, ['source.txt']),
    cleanup() { rmSync(options.dir, { recursive: true, force: true }); rmSync(root, { recursive: true, force: true }) } }
}
function phaseRows(kind) {
  let phases
  if (kind === 'strict') phases = [
    [1, 'effect.setup'], [1, 'effect.cleanup'], [2, 'effect.setup'], [2, 'ui.ready.queue'],
    [2, 'ui.ready.commit'], [2, 'effect.cleanup'], [3, 'effect.setup'], [3, 'effect.cleanup'],
    [4, 'effect.setup'], [4, 'ui.ready.queue'], [4, 'ui.ready.commit'], [4, 'effect.cleanup'],
  ]
  else if (kind === 'delayed') phases = [[1, 'effect.setup'], [1, 'effect.cleanup'],
    [2, 'effect.setup'], [2, 'ui.ready.queue'], [2, 'ui.ready.commit'], [2, 'effect.cleanup']]
  else if (kind === 'empty') phases = []
  else if (kind === 'provider') phases = [[1, 'http.fetch.begin'], [1, 'http.fetch.end']]
  else phases = [[1, 'effect.setup'], [1, 'ui.ready.queue'], [1, 'ui.ready.commit'], [1, 'effect.cleanup']]
  const sequence = new Map()
  return phases.map(([session, phase], index) => {
    const next = (sequence.get(session) || 0) + 1; sequence.set(session, next)
    return { schema: 1, session, generation: 1, sequence: next, phase, monotonic_ms: index }
  })
}
function capture(kind) {
  const rows = phaseRows(kind), bytes = Buffer.from(JSON.stringify({ rows, overflow: false }))
  return { rows: rows.length, bytes: bytes.length, body: bytes.toString('base64') }
}
function ledger(kind, status = 'passed', attempts = 0, body = capture('empty')) {
  const value = { schema: 1, initialStatus: status, finalStatus: status, initialErrors: status === 'failed' ? 1 : 0,
    finalErrors: status === 'failed' ? 1 : 0, originalErrorsRetained: true, releaseAttempts: attempts, releaseErrors: 0,
    pageCleanup: 'complete', retrieval: 'absent', rows: 0, overflow: false, bytes: 0,
    serialization: 'not_attempted', attachment: 'not_attempted', diagnosticQualified: true }
  if (kind === 'present' || kind === 'attachment') Object.assign(value, {
    retrieval: 'present', rows: body.rows, bytes: body.bytes, serialization: 'complete',
    attachment: kind === 'attachment' ? 'error' : 'complete', diagnosticQualified: kind === 'present' })
  if (kind === 'closed') Object.assign(value, { pageCleanup: 'closed', retrieval: 'error', diagnosticQualified: false })
  if (kind === 'invalid') Object.assign(value, { retrieval: 'invalid', diagnosticQualified: false })
  return value
}
function caseFixture(root, title, index, negative) {
  const status = negative ? 'failed' : 'passed', body = capture(index === 6 ? 'strict' : index === 5 ? 'delayed'
    : index > 6 ? 'empty' : index > 0 ? 'provider' : 'panel')
  let ledgers, tag
  if (negative) ledgers = [index === 0 ? ledger('closed', status) : ledger('attachment', status, 1, capture('provider'))]
  else if (index < 5) ledgers = ['absent', 'absent', 'present', 'absent', 'absent', 'absent'].map(kind => ledger(kind, status, 0, body))
  else if (index < 7) ledgers = [ledger('present', status, 0, body)]
  else if (index === 7) ledgers = [ledger('present', status, 1, body), ledger('present', status, 0, body)]
  else if (index === 8) { ledgers = [ledger('closed', status, 1), ledger('absent')]; tag = 'closed-page-retrieval' }
  else if (index === 9) { ledgers = [ledger('attachment', status, 1, body), ledger('present', status, 0, body)]; tag = 'missing-file-attachment' }
  else { ledgers = [ledger('invalid'), ledger('invalid')]; tag = index === 10 ? 'invalid-extra-BigInt' : 'invalid-extra-cycle' }
  const annotations = ledgers.map(value => ({ type: 'rc-initial-ready-diagnostic-ledger', description: JSON.stringify(value) }))
  if (tag) annotations.push({ type: 'rc-marker-expected-diagnostic-failure', description: tag })
  if (negative) annotations.push({ type: 'rc-marker-expected-negative-initial-ready',
    description: 'one-original-5000ms-assertion-failure-separate-diagnostic-ledger' })
  const file = 'tests/frontend/' + (negative ? 'rc-observer-teardown-negative-control.spec.ts' : 'rc-observer-browser.spec.ts')
  const errors = negative ? [{ location: { file: path.join(root, file), line: 55 },
    message: 'Error: expect(locator).toHaveAttribute(expected) failed\nLocator: locator(\'[data-rc-workflow="project"] [data-job-service="ready"]\')\nExpected: "failed"\nTimeout: 5000ms' }] : []
  const attachments = ledgers.filter(value => value.attachment === 'complete')
    .map(() => ({ name: 'rc-initial-ready-phases', contentType: 'application/json', body: body.body }))
  return { title, file, tests: [{ expectedStatus: 'passed', status: negative ? 'unexpected' : 'expected', annotations,
    results: [{ status, retry: 0, parallelIndex: 0, errors, annotations, attachments }] }] }
}
function report(root, negative = false) {
  return { config: { rootDir: root, workers: 1, projects: [{ retries: 0, repeatEach: 1, timeout: 30000 }] },
    stats: { expected: negative ? 0 : 12, unexpected: negative ? 2 : 0, skipped: 0, flaky: 0 }, errors: [],
    suites: [{ specs: (negative ? negativeTitles : positiveTitles).map((title, index) => caseFixture(root, title, index, negative)) }] }
}
const spec = (value, index = 0) => value.suites[0].specs[index]
const result = (value, index = 0) => spec(value, index).tests[0].results[0]
function mutateLedger(value, index, position, mutate) {
  const annotation = spec(value, index).tests[0].annotations[position]
  const data = JSON.parse(annotation.description); mutate(data); annotation.description = JSON.stringify(data)
}

test('exact controls identity rejects duplicates, overrides and output reuse/redirect', () => {
  const f = fixture()
  try {
    const args = ['--controls-dir=' + f.options.dir, '--controls-sha=' + f.options.sha,
      '--controls-run-id=' + f.options['run-id'], '--controls-run-attempt=1']
    assert.deepEqual(controlOptions(args), f.options)
    for (const invalid of [args.slice(1), [...args, args[0]], [...args, '--grep=one'], [...args, '--retries=1']]) {
      assert.throws(() => controlOptions(invalid), /rc_control_/)
    }
    assert.throws(() => prepareControls({ ...f.options, dir: f.root }, f.root, ['source.txt']), /output_outside/)
    symlinkSync(f.root, f.options.dir, 'dir'); assert.throws(f.prepare, /EEXIST/); rmSync(f.options.dir)
    f.prepare(); assert.throws(f.prepare, /EEXIST/)
  } finally { f.cleanup() }
})

test('positive12 and separately unexpected-negative2 profiles remain distinct', () => {
  const f = fixture()
  try {
    const positive = qualifyControlsNative(report(f.root), f.root, 'positive', 0)
    const negative = qualifyControlsNative(report(f.root, true), f.root, 'negative', 1)
    assert.equal(positive.cases.length, 12); assert.equal(negative.cases.length, 2)
    assert.equal(positive.cases.reduce((sum, item) => sum + item.ledgers.length, 0), 42)
    assert.equal(positive.cases.flatMap(item => item.ledgers).filter(item => !item.diagnosticQualified).length, 6)
    assert.equal(positive.cases.flatMap(item => item.captures).length, 10)
    assert.equal(positive.cases.flatMap(item => item.captures).filter(item => item.rows === 0).length, 3)
    assert.equal(negative.native_exit_code, 1)
    assert.equal(negative.native_stats.unexpected, 2)
    assert.equal(negative.tests_rewritten_as_expected_failure, false)
  } finally { f.cleanup() }
})

test('named false-ledger controls cannot qualify by a uniform or swapped profile', () => {
  const f = fixture()
  try {
    for (const mutate of [
      value => { mutateLedger(value, 1, 2, data => { data.diagnosticQualified = false }) },
      value => { spec(value, 8).tests[0].annotations.pop() },
      value => { mutateLedger(value, 10, 0, data => { data.retrieval = 'present' }) },
      value => { spec(value, 0).tests[0].annotations.pop() },
    ]) {
      const value = report(f.root); mutate(value)
      assert.throws(() => qualifyControlsNative(value, f.root, 'positive', 0), /rc_control_/)
    }
  } finally { f.cleanup() }
})

test('phase attachments reject unknown shape/order/encoding and lost ready commit', () => {
  const f = fixture()
  try {
    for (const mode of ['extra', 'order', 'encoding', 'ready']) {
      const value = report(f.root), attachment = result(value).attachments[0]
      if (mode === 'encoding') attachment.body = 'not-base64'
      else {
        const data = JSON.parse(Buffer.from(attachment.body, 'base64').toString('utf8'))
        if (mode === 'extra') data.rows[0].extra = 'fixture-only rejected data'
        if (mode === 'order') data.rows[1].sequence = data.rows[0].sequence
        if (mode === 'ready') data.rows[2].phase = 'ui.other.queue'
        const bytes = Buffer.from(JSON.stringify(data)); attachment.body = bytes.toString('base64')
        mutateLedger(value, 0, 2, ledger => { ledger.bytes = bytes.length })
      }
      assert.throws(() => qualifyControlsNative(value, f.root, 'positive', 0), /rc_control_/)
    }
  } finally { f.cleanup() }
})

test('negative witness requires the original5000 locator error and one retained error', () => {
  const f = fixture()
  try {
    for (const mutate of [
      value => { result(value).status = 'timedOut' },
      value => { result(value).errors.push({ message: 'extra cleanup failure' }) },
      value => { result(value).errors[0].message = 'unrelated failure' },
      value => { result(value).errors[0].message = result(value).errors[0].message.replace('5000ms', '6000ms') },
      value => { mutateLedger(value, 1, 0, data => { data.originalErrorsRetained = false }) },
    ]) {
      const value = report(f.root, true); mutate(value)
      assert.throws(() => qualifyControlsNative(value, f.root, 'negative', 1), /rc_control_/)
    }
    assert.throws(() => qualifyControlsNative(report(f.root, true), f.root, 'negative', 0), /rc_control_/)
    const contextOnly = report(f.root, true)
    result(contextOnly, 1).attachments.push({ name: 'error-context', contentType: 'text/plain', path: '/fixture-context-only' })
    assert.equal(qualifyControlsNative(contextOnly, f.root, 'negative', 1).cases[1].captures.length, 0)
  } finally { f.cleanup() }
})

test('roster/root/one-worker/retry0 omissions visibly fail qualification', () => {
  const f = fixture()
  try {
    const nested = report(f.root); nested.config.rootDir = path.join(f.root, 'tests', 'frontend')
    for (const entry of nested.suites[0].specs) entry.file = 'rc-observer-browser.spec.ts'
    assert.equal(qualifyControlsNative(nested, f.root, 'positive', 0).cases.length, 12)
    for (const mutate of [
      value => { value.config.rootDir = os.tmpdir() },
      value => { value.config.workers = 2 },
      value => { value.config.projects[0].retries = 1 },
      value => { value.suites[0].specs.pop() },
      value => { spec(value).file = path.join(f.root, 'tests/frontend/rc-observer-browser.spec.ts') },
      value => { spec(value).file = '../rc-observer-browser.spec.ts' },
      value => { spec(value).title = 'different roster' },
      value => { result(value).annotations = [] },
    ]) {
      const value = report(f.root); mutate(value)
      assert.throws(() => qualifyControlsNative(value, f.root, 'positive', 0), /rc_control_/)
    }
  } finally { f.cleanup() }
})

test('ledger projection rejects extra string/object fields, wrong types and oversize', () => {
  const f = fixture()
  try {
    for (const mutate of [
      data => { data.extra = 'fixture-only rejected string' },
      data => { data.extra = { nested: 'fixture-only rejected object' } },
      data => { data.rows = '4' }, data => { data.bytes = true },
      data => { data.pageCleanup = { kind: 'complete' } },
    ]) {
      const value = report(f.root); mutateLedger(value, 0, 2, mutate)
      assert.throws(() => qualifyControlsNative(value, f.root, 'positive', 0), /rc_control_ledger_/)
    }
    const oversized = report(f.root)
    spec(oversized).tests[0].annotations[0].description += ' '.repeat(4097)
    assert.throws(() => qualifyControlsNative(oversized, f.root, 'positive', 0), /ledger_budget/)
  } finally { f.cleanup() }
})

test('bounded raw native bytes and selected source drift stay separate from controls verdict', () => {
  const f = fixture()
  try {
    const state = f.prepare(), value = report(f.root, true), bytes = Buffer.from(JSON.stringify(value))
    writeFileSync(path.join(state.directory, 'negative-raw-native.json'), bytes)
    const retained = retainControlsNative(state, 'negative', 1)
    assert.deepEqual(readFileSync(path.join(state.directory, 'negative-native-playwright.json')), bytes)
    assert.equal(retained.result.native_exit_code, 1)
    assert.equal(controlsSourceUnchanged(state), true)
    writeFileSync(path.join(f.root, 'source.txt'), 'changed source\n')
    assert.equal(controlsSourceUnchanged(state), false)
  } finally { f.cleanup() }
})

test('oversized native report is never copied to the artifact allowlist', () => {
  const f = fixture()
  try {
    const state = f.prepare(), raw = path.join(state.directory, 'positive-raw-native.json')
    writeFileSync(raw, ''); truncateSync(raw, maxControlReportBytes + 1)
    assert.throws(() => retainControlsNative(state, 'positive', 0), /budget/)
    assert.throws(() => readFileSync(path.join(state.directory, 'positive-native-playwright.json')), /ENOENT/)
  } finally { f.cleanup() }
})

test('dedicated configs keep the intentional negative out of the positive/default lane', () => {
  const positive = readFileSync(new URL('../scripts/rc-observer-positive.config.mjs', import.meta.url), 'utf8')
  const negative = readFileSync(new URL('../scripts/rc-observer-negative.config.mjs', import.meta.url), 'utf8')
  assert.ok(positive.includes("testMatch: ['**/rc-observer-browser.spec.ts']"))
  assert.equal(positive.includes('rc-observer-teardown-negative-control.spec.ts'), false)
  assert.ok(negative.includes("testMatch: ['**/rc-observer-teardown-negative-control.spec.ts']"))
  for (const source of [positive, negative]) {
    assert.ok(source.includes('workers: 1')); assert.ok(source.includes('retries: 0'))
    assert.equal(source.includes('timeout:'), false); assert.equal(source.includes('expect:'), false)
    assert.equal(source.includes('webServer:'), false)
  }
  const normal = readFileSync(new URL('../scripts/verify-workbench-v2-e2e.mjs', import.meta.url), 'utf8')
  assert.equal(normal.includes('rc-observer-teardown-negative-control.spec.ts'), false)
})
