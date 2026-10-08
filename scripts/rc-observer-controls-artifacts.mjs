import { createHash } from 'node:crypto'
import { lstatSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const maxControlReportBytes = 64 * 1024 * 1024
export const positiveTitles = Object.freeze([
  "paired real panel failed load and explicit resume503 preserve outcome, binding and cleanup",
  "paired real provider request returns/errors/cancellation stay equal across observer modes",
  "paired real provider bad_hash returns/errors/cancellation stay equal across observer modes",
  "paired real provider http503 returns/errors/cancellation stay equal across observer modes",
  "paired real provider cancel returns/errors/cancellation stay equal across observer modes",
  "delayed old generation is cancelled and cannot replace the new real ready commit",
  "actual development StrictMode cleanup remount and unmount keep each first-ready queue before its commit",
  "real open-page retrieval and body attachment retain test status and release gates first",
  "real closed-page retrieval failure remains a separate unqualified diagnostic ledger",
  "real missing-file attachment failure retains cleanup and original framework outcome",
  "real BigInt extra capture is rejected without serialization or replacing test outcome",
  "real cycle extra capture is rejected without serialization or replacing test outcome"
])
export const negativeTitles = Object.freeze([
  "original ready failure survives real retrieval failure",
  "original ready failure survives real attachment failure"
])
const ledgerType = 'rc-initial-ready-diagnostic-ledger'
const expectedNegativeTag = 'one-original-5000ms-assertion-failure-separate-diagnostic-ledger'
const ledgerKeys = ['schema', 'initialStatus', 'finalStatus', 'initialErrors', 'finalErrors',
  'originalErrorsRetained', 'releaseAttempts', 'releaseErrors', 'pageCleanup', 'retrieval',
  'rows', 'overflow', 'bytes', 'serialization', 'attachment', 'diagnosticQualified'].sort().join(',')
const phases = new Set([
  'effect.setup', 'effect.cleanup', 'transport.ready', 'poll.begin', 'poll.error',
  'poll.job.begin', 'poll.job.end', 'poll.failed-load.begin', 'poll.failed-load.end',
  'auth.begin', 'auth.end', 'auth.error', 'scope.begin', 'scope.end', 'scope.changed',
  'http.fetch.begin', 'http.fetch.end', 'http.fetch.error', 'http.cancel.begin', 'http.cancel.settled',
  'body.read.begin', 'body.read.end', 'body.read.error', 'request.hash.begin', 'request.hash.end',
  'request.parse.begin', 'request.parse.end', 'job.load.begin', 'job.parse.begin', 'job.parse.end',
  'job.load.error', 'diagnostic.begin', 'diagnostic.absent', 'ui.ready.queue', 'ui.other.queue',
  'ui.ready.commit', 'trace.cap',
])
const fail = reason => { throw new Error(reason) }
export const controlHash = bytes => createHash('sha256').update(bytes).digest('hex')

export function controlBytes(file, maximum) {
  const stat = lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink() || realpathSync(file) !== file
    || stat.size <= 0 || stat.size > maximum) fail('rc_control_file_unsafe_or_budget')
  const bytes = readFileSync(file)
  if (bytes.length !== stat.size || bytes.length > maximum) fail('rc_control_file_changed_or_budget')
  return bytes
}

export function controlOptions(args) {
  const options = {}
  for (const arg of args) {
    const match = /^--controls-(dir|sha|run-id|run-attempt)=(.+)$/.exec(arg)
    if (!match || Object.hasOwn(options, match[1])) fail('rc_control_options_invalid')
    options[match[1]] = match[2]
  }
  if (Object.keys(options).length !== 4 || !/^[a-f0-9]{40}$/.test(options.sha ?? '')
    || !/^[1-9][0-9]*$/.test(options['run-id'] ?? '')
    || !/^[1-9][0-9]*$/.test(options['run-attempt'] ?? '')) fail('rc_control_identity_invalid')
  return options
}

export function controlSourcePins(root, relatives) {
  if (relatives.length > 128 || new Set(relatives).size !== relatives.length) fail('rc_control_source_scope')
  return relatives.map(relative => {
    const file = path.resolve(root, relative)
    if (!file.startsWith(root + path.sep)) fail('rc_control_source_outside')
    const bytes = controlBytes(file, 1024 * 1024)
    return { relative_path: relative, bytes: bytes.length, sha256: controlHash(bytes) }
  })
}

export function prepareControls(options, root, relatives) {
  const temp = os.tmpdir()
  if (realpathSync(root) !== root || !path.isAbsolute(temp) || realpathSync(temp) !== temp) fail('rc_control_roots_noncanonical')
  const directory = path.join(temp, 'rc-observer-controls-' + options['run-id'] + '-' + options['run-attempt'])
  if (options.dir !== directory || directory === root || directory.startsWith(root + path.sep)) fail('rc_control_output_outside_owned_temp')
  const sourcePins = controlSourcePins(root, relatives)
  mkdirSync(directory, { mode: 0o700 })
  const identity = { schema: 1, checkout_sha_from_workflow: options.sha, github_run_id: options['run-id'],
    github_run_attempt: options['run-attempt'], root, source_pins: sourcePins,
    generated_artifact_is_immutable_source_proof: false, physical_or_release_authority: false }
  writeFileSync(path.join(directory, 'run-linkage.json'), JSON.stringify(identity, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
  return { directory, root, relatives, identity }
}

export function assertControlDirectory(directory) {
  const temp = os.tmpdir(), stat = lstatSync(directory)
  if (realpathSync(temp) !== temp || !stat.isDirectory() || stat.isSymbolicLink()
    || realpathSync(directory) !== directory || path.dirname(directory) !== temp
    || !/^rc-observer-controls-[1-9][0-9]*-[1-9][0-9]*$/.test(path.basename(directory))) fail('rc_control_directory_unsafe')
}

function reportRoot(value, root) {
  if (typeof value !== 'string' || !path.isAbsolute(value) || value !== root && !value.startsWith(root + path.sep)) fail('rc_control_report_root')
  try { if (realpathSync(root) !== root || realpathSync(value) !== value || !lstatSync(value).isDirectory()) fail('rc_control_report_root') }
  catch { fail('rc_control_report_root') }
  return value
}
const flatten = suites => suites.flatMap(suite => [...(suite.specs || []), ...flatten(suite.suites || [])])
function nativeFile(file, base) {
  if (typeof file !== 'string' || path.isAbsolute(file) || file.includes('\0') || file.split(/[\\/]/).includes('..')) fail('rc_control_spec_path')
  return path.resolve(base, file)
}

function ledgerFrom(description) {
  if (typeof description !== 'string' || Buffer.byteLength(description) > 4096) fail('rc_control_ledger_budget')
  let value
  try { value = JSON.parse(description) } catch { fail('rc_control_ledger_json') }
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).sort().join(',') !== ledgerKeys) fail('rc_control_ledger_shape')
  if (value.schema !== 1 || !['passed', 'failed'].includes(value.initialStatus) || value.finalStatus !== value.initialStatus
    || ![value.initialErrors, value.finalErrors, value.releaseAttempts, value.releaseErrors, value.rows, value.bytes]
      .every(number => Number.isSafeInteger(number) && number >= 0)
    || value.initialErrors !== value.finalErrors || value.originalErrorsRetained !== true || value.releaseErrors !== 0
    || value.rows > 512 || value.bytes > 128 * 1024 || value.overflow !== false
    || !['complete', 'closed', 'error'].includes(value.pageCleanup)
    || !['absent', 'present', 'invalid', 'error'].includes(value.retrieval)
    || !['not_attempted', 'complete', 'oversize', 'error'].includes(value.serialization)
    || !['not_attempted', 'complete', 'error'].includes(value.attachment)
    || typeof value.diagnosticQualified !== 'boolean') fail('rc_control_ledger_types')
  return Object.freeze({ schema: 1, initialStatus: value.initialStatus, finalStatus: value.finalStatus,
    initialErrors: value.initialErrors, finalErrors: value.finalErrors, originalErrorsRetained: true,
    releaseAttempts: value.releaseAttempts, releaseErrors: 0, pageCleanup: value.pageCleanup,
    retrieval: value.retrieval, rows: value.rows, overflow: false, bytes: value.bytes,
    serialization: value.serialization, attachment: value.attachment, diagnosticQualified: value.diagnosticQualified })
}

function captureFrom(body) {
  if (typeof body !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(body)) fail('rc_control_body_missing')
  const bytes = Buffer.from(body, 'base64')
  if (!bytes.length || bytes.length > 128 * 1024 || bytes.toString('base64') !== body) fail('rc_control_body_budget_or_encoding')
  let value
  try { value = JSON.parse(bytes.toString('utf8')) } catch { fail('rc_control_body_json') }
  if (!value || Object.keys(value).sort().join(',') !== 'overflow,rows' || !Array.isArray(value.rows)
    || value.rows.length > 512 || value.overflow !== false
    || bytes.toString('utf8') !== JSON.stringify({ rows: value.rows, overflow: false })) fail('rc_control_capture_shape')
  const last = new Map()
  for (const row of value.rows) {
    const previous = last.get(row?.session)
    if (!row || Object.keys(row).sort().join(',') !== 'generation,monotonic_ms,phase,schema,sequence,session'
      || row.schema !== 1 || !Number.isSafeInteger(row.session) || row.session <= 0
      || !Number.isSafeInteger(row.generation) || row.generation < 0
      || !Number.isSafeInteger(row.sequence) || row.sequence <= 0 || row.sequence > 256
      || !Number.isFinite(row.monotonic_ms) || row.monotonic_ms < 0 || !phases.has(row.phase)
      || previous && (row.sequence <= previous.sequence || row.monotonic_ms < previous.monotonic_ms || row.generation !== previous.generation)) fail('rc_control_marker_shape_or_order')
    last.set(row.session, row)
  }
  return { rows: value.rows, bytes: bytes.length, sha256: controlHash(bytes) }
}

const absent = { pageCleanup: 'complete', retrieval: 'absent', rows: 0, bytes: 0,
  serialization: 'not_attempted', attachment: 'not_attempted', diagnosticQualified: true }
const present = { pageCleanup: 'complete', retrieval: 'present', serialization: 'complete',
  attachment: 'complete', diagnosticQualified: true }
const closed = { pageCleanup: 'closed', retrieval: 'error', rows: 0, bytes: 0,
  serialization: 'not_attempted', attachment: 'not_attempted', diagnosticQualified: false }
const invalid = { pageCleanup: 'complete', retrieval: 'invalid', rows: 0, bytes: 0,
  serialization: 'not_attempted', attachment: 'not_attempted', diagnosticQualified: false }
const failedAttachment = { pageCleanup: 'complete', retrieval: 'present', serialization: 'complete',
  attachment: 'error', diagnosticQualified: false }
function matches(ledger, expected) {
  if (Object.entries(expected).some(([key, value]) => ledger[key] !== value)) fail('rc_control_named_ledger_profile')
}
function verifyReady(rows, kind) {
  const queued = rows.filter(row => row.phase === 'ui.ready.queue'), committed = rows.filter(row => row.phase === 'ui.ready.commit')
  const expected = kind === 'strict' ? 2 : 1
  if (queued.length !== expected || committed.length !== expected || committed.some(commit =>
    !queued.some(queue => queue.session === commit.session && queue.generation === commit.generation && queue.sequence < commit.sequence))) fail('rc_control_ready_queue_commit')
  if (kind === 'strict' && (rows.filter(row => row.phase === 'effect.setup').length !== 4
    || rows.filter(row => row.phase === 'effect.cleanup').length !== 4
    || new Set(committed.map(row => row.session)).size !== 2)) fail('rc_control_strictmode_profile')
  if (kind === 'delayed' && !rows.some(row => row.phase === 'effect.cleanup' && row.session !== committed[0].session)) fail('rc_control_old_generation_cleanup')
}

function inspectCase(spec, lane, index, root) {
  if (spec.tests?.length !== 1) fail('rc_control_case_ambiguity')
  const test = spec.tests[0], result = test.results?.[0], negative = lane === 'negative'
  if (test.expectedStatus !== 'passed' || test.status !== (negative ? 'unexpected' : 'expected')
    || test.results?.length !== 1 || result?.status !== (negative ? 'failed' : 'passed') || result.retry !== 0
    || !Array.isArray(result.errors) || result.errors.length !== (negative ? 1 : 0) || result.parallelIndex !== 0) fail('rc_control_native_case_status')
  if (!Array.isArray(test.annotations) || JSON.stringify(test.annotations) !== JSON.stringify(result.annotations)) fail('rc_control_native_annotations')
  const ledgers = test.annotations.filter(item => item.type === ledgerType).map(item => ledgerFrom(item.description))
  const controlTags = test.annotations.filter(item => item.type === 'rc-marker-expected-diagnostic-failure')
  const bodies = (result.attachments || []).filter(item => item.name === 'rc-initial-ready-phases' && item.contentType === 'application/json').map(item => captureFrom(item.body))
  if (ledgers.some(ledger => ledger.initialStatus !== (negative ? 'failed' : 'passed') || ledger.initialErrors !== (negative ? 1 : 0))) fail('rc_control_original_outcome_retention')
  let profile
  if (negative) {
    profile = [index === 0 ? { ...closed, releaseAttempts: 0 } : { ...failedAttachment, releaseAttempts: 1 }]
    if (index === 1 && (!ledgers[0]?.rows || !ledgers[0]?.bytes)) fail('rc_control_negative_capture_missing')
    const tags = test.annotations.filter(item => item.type === 'rc-marker-expected-negative-initial-ready')
    if (controlTags.length || tags.length !== 1 || tags[0].description !== expectedNegativeTag || bodies.length) fail('rc_control_negative_tag_or_body')
    const error = result.errors[0], message = typeof error.message === 'string' ? error.message.replace(/\x1b\[[0-9;]*m/g, '') : ''
    if (error.location?.file !== path.join(root, 'tests/frontend/rc-observer-teardown-negative-control.spec.ts')
      || error.location.line !== 55 || !message.includes('toHaveAttribute') || !message.includes('Timeout: 5000ms')
      || !message.includes("locator('[data-rc-workflow=\"project\"] [data-job-service=\"ready\"]')")
      || !message.includes('Expected: "failed"')) fail('rc_control_original_5000_error')
  } else if (index < 5) {
    profile = [absent, absent, present, absent, absent, absent].map(value => ({ ...value, releaseAttempts: 0 }))
  } else if (index < 7) {
    profile = [{ ...present, releaseAttempts: 0 }]
  } else if (index === 7) {
    profile = [{ ...present, rows: 0, releaseAttempts: 1 }, { ...present, rows: 0, releaseAttempts: 0 }]
  } else if (index === 8) {
    profile = [{ ...closed, releaseAttempts: 1 }, { ...absent, releaseAttempts: 0 }]
  } else if (index === 9) {
    profile = [{ ...failedAttachment, rows: 0, bytes: 28, releaseAttempts: 1 }, { ...present, rows: 0, releaseAttempts: 0 }]
  } else {
    profile = [{ ...invalid, releaseAttempts: 0 }, { ...invalid, releaseAttempts: 0 }]
  }
  if (ledgers.length !== profile.length) fail('rc_control_ledger_count')
  profile.forEach((expected, position) => matches(ledgers[position], expected))
  if (!negative) {
    const tags = { 8: 'closed-page-retrieval', 9: 'missing-file-attachment', 10: 'invalid-extra-BigInt', 11: 'invalid-extra-cycle' }
    if (tags[index] ? controlTags.length !== 1 || controlTags[0].description !== tags[index] : controlTags.length !== 0) fail('rc_control_fault_association')
    if (test.annotations.some(item => item.type === 'rc-marker-expected-negative-initial-ready')) fail('rc_control_wrong_lane_tag')
  }
  const complete = ledgers.filter(ledger => ledger.attachment === 'complete')
  if (bodies.length !== complete.length || complete.some((ledger, position) => ledger.rows !== bodies[position].rows.length || ledger.bytes !== bodies[position].bytes)) fail('rc_control_body_ledger_binding')
  if (!negative && index < 7 && bodies.some(body => !body.rows.length)) fail('rc_control_operation_capture_empty')
  if (!negative && [0, 5, 6].includes(index)) verifyReady(bodies[0].rows, index === 6 ? 'strict' : index === 5 ? 'delayed' : 'panel')
  return { title: spec.title, native_status: result.status, original_errors: result.errors.length,
    ledgers, captures: bodies.map(body => ({ rows: body.rows.length, bytes: body.bytes, sha256: body.sha256 })) }
}

export function qualifyControlsNative(report, root, lane, nativeCode) {
  const negative = lane === 'negative', titles = negative ? negativeTitles : positiveTitles
  if (!['positive', 'negative'].includes(lane) || nativeCode !== (negative ? 1 : 0)
    || !Array.isArray(report?.suites) || !Array.isArray(report.errors) || report.errors.length
    || report.stats?.expected !== (negative ? 0 : 12) || report.stats.unexpected !== (negative ? 2 : 0)
    || report.stats.skipped !== 0 || report.stats.flaky !== 0 || report.config?.workers !== 1
    || report.config.projects?.length !== 1 || report.config.projects[0].retries !== 0
    || report.config.projects[0].repeatEach !== 1 || report.config.projects[0].timeout !== 30000) fail('rc_control_native_lane_counts_or_exit')
  const base = reportRoot(report.config.rootDir, root), file = path.join(root, 'tests/frontend',
    negative ? 'rc-observer-teardown-negative-control.spec.ts' : 'rc-observer-browser.spec.ts')
  const selected = flatten(report.suites)
  if (selected.length !== titles.length || selected.some(spec => nativeFile(spec.file, base) !== file)
    || new Set(selected.map(spec => spec.title)).size !== titles.length
    || titles.some(title => !selected.some(spec => spec.title === title))) fail('rc_control_exact_named_roster')
  return { lane, native_exit_code: nativeCode, native_stats: { expected: report.stats.expected,
    unexpected: report.stats.unexpected, skipped: 0, flaky: 0 },
    cases: titles.map((title, index) => inspectCase(selected.find(spec => spec.title === title), lane, index, root)),
    tests_rewritten_as_expected_failure: false, physical_or_full_R2_authority: false }
}

export function retainControlsNative(state, lane, nativeCode) {
  assertControlDirectory(state.directory)
  const bytes = controlBytes(path.join(state.directory, lane + '-raw-native.json'), maxControlReportBytes)
  writeFileSync(path.join(state.directory, lane + '-native-playwright.json'), bytes, { flag: 'wx', mode: 0o600 })
  let report
  try { report = JSON.parse(bytes.toString('utf8')) } catch { fail('rc_control_native_json_invalid') }
  return { bytes: bytes.length, sha256: controlHash(bytes), result: qualifyControlsNative(report, state.root, lane, nativeCode) }
}

export function controlsSourceUnchanged(state) {
  return JSON.stringify(controlSourcePins(state.root, state.relatives)) === JSON.stringify(state.identity.source_pins)
}

export function writeControlsReceipt(state, receipt) {
  assertControlDirectory(state.directory)
  writeFileSync(path.join(state.directory, 'control-retention.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
}
