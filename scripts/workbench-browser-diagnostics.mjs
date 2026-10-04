import { createHash } from 'node:crypto'
import { lstatSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const maxNativeReportBytes = 64 * 1024 * 1024
export const maxLedgerDescriptionBytes = 4 * 1024
const maxMarkerBytes = 128 * 1024
const targetTitle = 'resume503 requires fresh failed GET before explicit null checkpoint retry'
const targetFile = 'tests/frontend/workbench-v2-rc-workflow-browser.spec.ts'
const ledgerType = 'rc-initial-ready-diagnostic-ledger'
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
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')
const fail = reason => { throw new Error(reason) }

export function workbenchDiagnosticOptions(args) {
  const names = ['dir', 'sha', 'run-id', 'run-attempt']
  const options = {}, passthrough = []
  for (const arg of args) {
    if (!arg.startsWith('--diagnostics-')) { passthrough.push(arg); continue }
    const match = /^--diagnostics-(dir|sha|run-id|run-attempt)=(.+)$/.exec(arg)
    if (!match || Object.hasOwn(options, match[1])) fail('diagnostic_option_invalid_or_duplicate')
    options[match[1]] = match[2]
  }
  if (!Object.keys(options).length) return { options: null, passthrough }
  if (names.some(name => !Object.hasOwn(options, name))) fail('diagnostic_identity_missing')
  if (!/^[a-f0-9]{40}$/.test(options.sha) || !/^[1-9][0-9]*$/.test(options['run-id'])
    || !/^[1-9][0-9]*$/.test(options['run-attempt'])) fail('diagnostic_identity_invalid')
  // This hosted mode keeps the entire registered lane and standard runner defaults.
  // Local invocations without diagnostic options retain their existing passthrough.
  if (passthrough.some(arg => arg !== '--trace=retain-on-failure') || passthrough.length > 1) {
    fail('diagnostic_runner_override')
  }
  return { options, passthrough }
}

function regularBytes(file, maximum) {
  const stat = lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink() || realpathSync(file) !== file) fail('diagnostic_file_unsafe')
  if (stat.size <= 0 || stat.size > maximum) fail('diagnostic_file_missing_or_oversize')
  const bytes = readFileSync(file)
  if (bytes.length !== stat.size || bytes.length > maximum) fail('diagnostic_file_changed_or_oversize')
  return bytes
}

function sourcePins(root, relatives) {
  if (relatives.length > 128 || new Set(relatives).size !== relatives.length) fail('diagnostic_source_scope_invalid')
  return relatives.map(relative => {
    const file = path.resolve(root, relative)
    if (!file.startsWith(root + path.sep)) fail('diagnostic_source_outside_repository')
    const bytes = regularBytes(file, 1024 * 1024)
    return { relative_path: relative, bytes: bytes.length, sha256: sha256(bytes) }
  })
}

export function prepareWorkbenchDiagnostics(options, root, relatives) {
  if (!options) return null
  if (realpathSync(root) !== root) fail('diagnostic_root_not_canonical')
  const temp = os.tmpdir()
  if (!path.isAbsolute(temp) || realpathSync(temp) !== temp) fail('diagnostic_temp_not_canonical')
  const directory = path.join(temp, 'workbench-browser-diagnostics-' + options['run-id'] + '-' + options['run-attempt'])
  if (options.dir !== directory) fail('diagnostic_directory_outside_owned_temp')
  const pins = sourcePins(root, relatives)
  mkdirSync(directory, { mode: 0o700 }) // Exclusive: never reuse or remove another run's output.
  if (realpathSync(directory) !== directory) fail('diagnostic_directory_not_canonical')
  const identity = { schema: 1, checkout_sha_from_workflow: options.sha,
    github_run_id: options['run-id'], github_run_attempt: options['run-attempt'],
    repository_root: root, source_pins: pins, generated_artifact_is_immutable_source_proof: false,
    physical_or_release_authority: false }
  writeFileSync(path.join(directory, 'run-linkage.json'), JSON.stringify(identity, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
  return { directory, rawReport: path.join(directory, 'raw-native-playwright.json'), root, relatives, identity }
}

function ownedDirectory(state) {
  const stat = lstatSync(state.directory)
  if (!stat.isDirectory() || stat.isSymbolicLink() || realpathSync(state.directory) !== state.directory) fail('diagnostic_directory_unsafe')
}

function specs(suites) {
  return suites.flatMap(suite => [...(suite.specs || []), ...specs(suite.suites || [])])
}

function captureFrom(body) {
  if (typeof body !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(body)) fail('diagnostic_attachment_body_missing')
  const bytes = Buffer.from(body, 'base64')
  if (!bytes.length || bytes.length > maxMarkerBytes || bytes.toString('base64') !== body) fail('diagnostic_attachment_encoding_or_budget')
  const capture = JSON.parse(bytes.toString('utf8'))
  if (!capture || Object.keys(capture).sort().join(',') !== 'overflow,rows'
    || !Array.isArray(capture.rows) || capture.rows.length < 1 || capture.rows.length > 512
    || capture.overflow !== false) fail('diagnostic_capture_invalid')
  const previous = new Map()
  for (const row of capture.rows) {
    if (!row || Object.keys(row).sort().join(',') !== 'generation,monotonic_ms,phase,schema,sequence,session'
      || row.schema !== 1 || !Number.isSafeInteger(row.session) || row.session <= 0
      || !Number.isSafeInteger(row.generation) || row.generation < 0
      || !Number.isSafeInteger(row.sequence) || row.sequence <= 0 || row.sequence > 256
      || !phases.has(row.phase) || !Number.isFinite(row.monotonic_ms) || row.monotonic_ms < 0) fail('diagnostic_marker_invalid')
    const last = previous.get(row.session)
    if (last && (row.sequence <= last.sequence || row.monotonic_ms < last.monotonic_ms || row.generation !== last.generation)) fail('diagnostic_marker_order_invalid')
    previous.set(row.session, row)
  }
  if (!capture.rows.some(commit => commit.phase === 'ui.ready.commit'
    && capture.rows.some(queue => queue.phase === 'ui.ready.queue' && queue.session === commit.session
      && queue.generation === commit.generation && queue.sequence < commit.sequence))) fail('diagnostic_ready_queue_commit_missing')
  if (bytes.toString('utf8') !== JSON.stringify({ rows: capture.rows, overflow: false })) fail('diagnostic_capture_not_canonical')
  return { rows: capture.rows.length, bytes: bytes.length, sha256: sha256(bytes) }
}

function nativeReportRoot(value, root) {
  if (typeof value !== 'string' || !path.isAbsolute(value)
    || value !== root && !value.startsWith(root + path.sep)) fail('diagnostic_report_root_unsafe')
  try {
    if (realpathSync(root) !== root || realpathSync(value) !== value || !lstatSync(value).isDirectory()) fail('diagnostic_report_root_unsafe')
  } catch { fail('diagnostic_report_root_unsafe') }
  return value
}

function nativeSpecFile(file, reportRoot) {
  if (typeof file !== 'string' || !file || path.isAbsolute(file) || file.includes('\0')
    || file.split(/[\\/]/).includes('..')) fail('diagnostic_target_path_unsafe')
  const resolved = path.resolve(reportRoot, file)
  if (!resolved.startsWith(reportRoot + path.sep)) fail('diagnostic_target_path_unsafe')
  return resolved
}

const ledgerKeys = ['schema', 'initialStatus', 'finalStatus', 'initialErrors', 'finalErrors',
  'originalErrorsRetained', 'releaseAttempts', 'releaseErrors', 'pageCleanup', 'retrieval',
  'rows', 'overflow', 'bytes', 'serialization', 'attachment', 'diagnosticQualified'].sort().join(',')

function ledgerProjection(description) {
  if (typeof description !== 'string' || Buffer.byteLength(description, 'utf8') > maxLedgerDescriptionBytes) fail('diagnostic_ledger_description_budget')
  const value = JSON.parse(description)
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).sort().join(',') !== ledgerKeys) fail('diagnostic_ledger_shape')
  if (value.schema !== 1 || value.initialStatus !== 'passed' || value.finalStatus !== 'passed'
    || value.initialErrors !== 0 || value.finalErrors !== 0 || value.originalErrorsRetained !== true
    || !Number.isSafeInteger(value.releaseAttempts) || value.releaseAttempts < 0
    || value.releaseErrors !== 0 || value.pageCleanup !== 'complete' || value.retrieval !== 'present'
    || !Number.isSafeInteger(value.rows) || value.rows < 1 || value.rows > 512
    || !Number.isSafeInteger(value.bytes) || value.bytes < 1 || value.bytes > maxMarkerBytes
    || value.overflow !== false || value.serialization !== 'complete' || value.attachment !== 'complete'
    || value.diagnosticQualified !== true) fail('diagnostic_ledger_unqualified')
  // Only this known enum/integer/boolean projection enters the qualification receipt.
  return Object.freeze({ schema: 1, initialStatus: 'passed', finalStatus: 'passed',
    initialErrors: 0, finalErrors: 0, originalErrorsRetained: true,
    releaseAttempts: value.releaseAttempts, releaseErrors: 0, pageCleanup: 'complete',
    retrieval: 'present', rows: value.rows, overflow: false, bytes: value.bytes,
    serialization: 'complete', attachment: 'complete', diagnosticQualified: true })
}

export function qualifyWorkbenchDiagnosticReport(report, root) {
  if (!Array.isArray(report?.suites) || !Array.isArray(report.errors)
    || report.errors.length || report.stats?.unexpected !== 0 || report.stats?.flaky !== 0) fail('diagnostic_native_report_invalid_or_failed')
  const reportRoot = nativeReportRoot(report.config?.rootDir, root)
  const selected = specs(report.suites).filter(spec => spec.title === targetTitle)
    .filter(spec => nativeSpecFile(spec.file, reportRoot) === path.join(root, targetFile))
  if (selected.length !== 1 || selected[0].tests?.length !== 1) fail('diagnostic_target_missing_or_ambiguous')
  const test = selected[0].tests[0]
  const result = test.results?.[0]
  if (test.expectedStatus !== 'passed' || test.status !== 'expected' || test.results.length !== 1
    || result.status !== 'passed' || result.retry !== 0 || !Array.isArray(result.errors) || result.errors.length) fail('diagnostic_target_not_single_native_pass')
  const annotations = test.annotations?.filter(value => value.type === ledgerType)
  const resultAnnotations = result.annotations?.filter(value => value.type === ledgerType)
  if (annotations?.length !== 1 || JSON.stringify(annotations) !== JSON.stringify(resultAnnotations)) fail('diagnostic_ledger_missing_or_mismatched')
  const ledger = ledgerProjection(annotations[0].description)
  const attachments = result.attachments?.filter(value => value.name === 'rc-initial-ready-phases' && value.contentType === 'application/json')
  if (attachments?.length !== 1) fail('diagnostic_attachment_missing_or_ambiguous')
  const capture = captureFrom(attachments[0].body)
  if (capture.rows !== ledger.rows || capture.bytes !== ledger.bytes) fail('diagnostic_ledger_body_mismatch')
  return { target_title: targetTitle, ledger, capture }
}

export function workbenchExitCode(nativeCode, qualified) {
  return nativeCode !== 0 ? nativeCode : qualified ? 0 : 1
}

export function finishWorkbenchDiagnostics(state, nativeCode, executionStage = 'playwright') {
  if (!state) return { qualified: true }
  const receipt = { schema: 1, checkout_sha_from_workflow: state.identity.checkout_sha_from_workflow,
    github_run_id: state.identity.github_run_id, github_run_attempt: state.identity.github_run_attempt,
    execution_stage: executionStage, original_exit_code: nativeCode, native_report: null,
    diagnosticQualified: false, reason: null, target: null, generated_artifact_is_immutable_source_proof: false,
    whole_suite_hosted_physical_release_authority: false }
  try {
    ownedDirectory(state)
    const bytes = regularBytes(state.rawReport, maxNativeReportBytes)
    // Upload only this bounded byte copy, never an arbitrary raw directory or source/cache tree.
    writeFileSync(path.join(state.directory, 'native-playwright.json'), bytes, { flag: 'wx', mode: 0o600 })
    receipt.native_report = { bytes: bytes.length, sha256: sha256(bytes) }
    const report = JSON.parse(bytes.toString('utf8'))
    receipt.target = qualifyWorkbenchDiagnosticReport(report, state.root)
    if (JSON.stringify(sourcePins(state.root, state.relatives)) !== JSON.stringify(state.identity.source_pins)) fail('diagnostic_source_changed')
    if (nativeCode !== 0 || executionStage !== 'playwright') fail('diagnostic_original_execution_failed')
    receipt.diagnosticQualified = true
  } catch (error) {
    receipt.reason = error instanceof Error ? error.message : 'diagnostic_retention_error'
  }
  try {
    ownedDirectory(state)
    writeFileSync(path.join(state.directory, 'retention.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
  } catch {
    receipt.diagnosticQualified = false
    receipt.reason = 'diagnostic_receipt_write_failed'
  }
  if (!receipt.diagnosticQualified) console.error('Workbench diagnostic retention unqualified: ' + receipt.reason)
  return { qualified: receipt.diagnosticQualified, receipt }
}
