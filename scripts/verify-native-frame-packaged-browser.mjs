#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { pathToFileURL } from 'node:url'

const schemaVersion = 'structural-frame-alpha-packaged-browser-replay.v1'
const platforms = new Set(['linux-x86_64-gnu', 'windows-x86_64-msvc'])
const expectedModelId = 'frame-alpha-distribution-cantilever'
const expectedLoadPatternId = 'LC_WEAK'
const expectedResultId = 'result.browser.LC_WEAK'
const maxReceiptElapsedMs = 180000
const maxHostRequests = 1024
const maxDiagnosticTextBytes = 2048
const maxDiagnosticTextNodes = 2048
const maxDiagnosticPageErrors = 8
const maxDiagnosticBytes = 32768
const maxDiagnosticJobViewBytes = 65536
const maxDiagnosticJobViewFetchMs = 2000
const maxArtifactResponseBytes = 2 * 1024 * 1024
const maxArtifactFetchMs = 5000
const maxBrowserCleanupMs = 5000
const maxFailureCleanupWatchdogMs = 12000
const maxStderrDrainMs = 1000
const maxHostStartupLineBytes = 16 * 1024
const maxHostStartupWaitMs = 15000
const jobIdPattern = /^job_[0-9a-f]{32}$/
const diagnosticCodePrefixes = new Set([
  'analysis', 'artifact', 'browser', 'bundle', 'cancel', 'cancellation', 'contract',
  'diagnostic', 'ffi', 'host', 'internal', 'invalid', 'io', 'job', 'load', 'manifest',
  'model', 'native', 'package', 'process', 'receipt', 'release', 'result', 'runtime',
  'schema', 'singular', 'solver', 'submission', 'success', 'timeout', 'unsupported',
  'worker', 'workbench', 'workstation',
])
const receiptSchemaUrl = new URL(
  '../native/distribution/frame_alpha_packaged_browser_replay_v1.schema.json',
  import.meta.url,
)

function fail(code, detail = '') {
  throw new Error(detail ? `${code}:${detail}` : code)
}

function diagnosticByteLength(value) {
  return Math.min(Buffer.byteLength(String(value ?? ''), 'utf8'), maxDiagnosticTextBytes)
}

function boundedDiagnosticByteCount(value) {
  const bytes = Number(value)
  return Number.isSafeInteger(bytes) && bytes > 0
    ? Math.min(bytes, maxDiagnosticTextBytes)
    : 0
}

export function extractStableDiagnosticCode(value) {
  const text = String(value ?? '').replace(/^Error:\s*/, '')
  const match = text.match(/^([A-Za-z][A-Za-z0-9_.-]{0,127})(?=[:\s]|$)/)
  const code = match?.[1] ?? ''
  const prefix = code.split('_', 1)[0]
  return /^[a-z][a-z0-9_.-]{1,95}$/.test(code) && diagnosticCodePrefixes.has(prefix)
    ? code
    : null
}

export function classifyNativeFramePanelState(status, { timedOut = false } = {}) {
  if (status === 'succeeded' || status === 'failed' || status === 'cancelled') return status
  return timedOut ? 'timeout' : 'pending'
}

export function recordBoundedPageError(pageErrors) {
  if (pageErrors.length < maxDiagnosticPageErrors + 1) pageErrors.push(null)
}

export function classifyCleanupFailure({ browserClosed, hostStopped }) {
  if (!browserClosed) return 'browser_cleanup_timeout'
  if (!hostStopped) return 'host_cleanup_timeout'
  return null
}

export function hasChildStopped(child) {
  return child.exitCode !== null || child.signalCode !== null
}

export function requireMatchingJobIdentity(left, right, code) {
  if (!jobIdPattern.test(left ?? '') || !jobIdPattern.test(right ?? '') || left !== right) {
    fail(code)
  }
}

export function requireArtifactByteLength(artifact, bytes, code) {
  if (
    !Number.isSafeInteger(artifact?.byte_length)
    || artifact.byte_length < 1
    || artifact.byte_length !== bytes.length
  ) fail(code)
}

export function buildBrowserFailureDiagnostic({
  sourceCommit,
  platformTag,
  phase,
  panel,
  submittedJobId,
  jobView,
  pageErrors,
  verifierError,
  hostExitCode,
  hostStderrBytes,
  elapsedMs,
}) {
  const diagnostic = {
    schema_version: 'structural-frame-alpha-packaged-browser-diagnostic.v1',
    status: 'fail',
    source_commit: sourceCommit,
    platform_tag: platformTag,
    phase: extractStableDiagnosticCode(phase) ?? 'unavailable',
    elapsed_ms: Math.max(0, Math.min(Number(elapsedMs) || 0, maxReceiptElapsedMs)),
    panel: {
      status: [
        'unconfigured', 'idle', 'reading', 'submitting', 'running',
        'succeeded', 'failed', 'cancelled',
      ].includes(panel?.status) ? panel.status : 'unavailable',
      job_id: jobIdPattern.test(submittedJobId ?? '') ? submittedJobId : null,
      error_code: extractStableDiagnosticCode(panel?.errorText),
      job_text_bytes: diagnosticByteLength(panel?.jobText),
      error_text_bytes: diagnosticByteLength(panel?.errorText),
    },
    job_view: {
      status: ['queued', 'running', 'succeeded', 'failed', 'cancelled']
        .includes(jobView?.status) ? jobView.status : 'unavailable',
      error_code: extractStableDiagnosticCode(jobView?.errorCode),
    },
    page_errors: {
      count: Math.min(Array.isArray(pageErrors) ? pageErrors.length : 0, maxDiagnosticPageErrors),
      overflow: Array.isArray(pageErrors) && pageErrors.length > maxDiagnosticPageErrors,
    },
    verifier: {
      error_code: extractStableDiagnosticCode(verifierError),
      error_bytes: diagnosticByteLength(verifierError),
    },
    workstation: {
      exit_code: Number.isInteger(hostExitCode) ? hostExitCode : null,
      stderr_bytes: boundedDiagnosticByteCount(hostStderrBytes),
    },
    authority: {
      packaged_browser_execution: 'failed',
      engineering_design: 'not_authoritative',
      commercial_use: 'not_authoritative',
      release_readiness: 'not_authoritative',
    },
    claim_boundary: 'bounded_failure_diagnostic_only_not_retry_result_validation_or_release_authority',
  }
  if (Buffer.byteLength(JSON.stringify(diagnostic), 'utf8') > maxDiagnosticBytes) {
    fail('browser_failure_diagnostic_size_invalid')
  }
  return diagnostic
}

function parseArguments(values) {
  const result = new Map()
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index]
    const value = values[index + 1]
    if (!key?.startsWith('--') || value === undefined) fail('arguments_invalid')
    if (result.has(key)) fail('argument_duplicate', key)
    result.set(key, value)
  }
  for (const required of ['--package-root', '--source-commit', '--platform-tag', '--output']) {
    if (!result.has(required)) fail('argument_missing', required)
  }
  const sourceCommit = result.get('--source-commit')
  const platformTag = result.get('--platform-tag')
  if (!/^[0-9a-f]{40}$/.test(sourceCommit)) fail('source_commit_invalid')
  if (!platforms.has(platformTag)) fail('platform_tag_invalid')
  return {
    packageRoot: path.resolve(result.get('--package-root')),
    sourceCommit,
    platformTag,
    output: path.resolve(result.get('--output')),
  }
}

function sha256(bytes) {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

function requireObject(value, code) {
  if (value === null || Array.isArray(value) || typeof value !== 'object') fail(code)
  return value
}

async function readObject(filename, code) {
  let value
  try {
    value = JSON.parse(await readFile(filename, 'utf8'))
  } catch (error) {
    fail(code, String(error))
  }
  return requireObject(value, code)
}

function isSha256(value) {
  return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value)
}

export function validateBrowserResultContract({ model, view, bundle, result, pageErrors }) {
  const bindings = requireObject(result.bindings, 'result_bindings_invalid')
  const bundleBindings = requireObject(bundle.bindings, 'bundle_bindings_invalid')
  const bundleArtifacts = requireObject(bundle.artifacts, 'bundle_artifacts_invalid')
  const modelArtifact = requireObject(bundleArtifacts.model_ir, 'model_artifact_invalid')
  const gates = requireObject(result.gates, 'result_gates_invalid')
  const authority = requireObject(result.authority, 'result_authority_invalid')
  if (
    model.model_id !== expectedModelId
    || bundle.schema_version !== 'structural-native-linear-frame3d-workbench-bundle.v1'
    || bundle.status !== 'complete'
    || view.model_content_hash !== bindings.model_content_hash
    || bundleBindings.model_content_hash !== bindings.model_content_hash
    || modelArtifact.content_hash !== bindings.model_content_hash
    || bundleBindings.result_id !== result.result_id
    || bundleBindings.result_hash !== result.result_hash
    || bindings.model_id !== model.model_id
    || !isSha256(bindings.model_content_hash)
    || !isSha256(bindings.model_semantic_hash)
    || !isSha256(bindings.model_provenance_hash)
    || bindings.load_pattern_id !== expectedLoadPatternId
    || bindings.load_combination_id !== null
    || result.schema_version !== 'structural-native-linear-frame3d-result-ir.v1'
    || result.result_id !== expectedResultId
    || !isSha256(result.result_hash)
    || authority.release_readiness !== 'not_authoritative'
    || gates.native_residual_gate_passed !== true
    || gates.global_resultant_gate_passed !== true
    || gates.independent_recovery_replay_passed !== true
    || gates.fallback_count !== 0
    || gates.regularization_count !== 0
    || pageErrors.length !== 0
  ) fail('browser_result_contract_invalid', `page_error_count=${pageErrors.length}`)
}

function validatedElapsedMs(started) {
  const elapsedMs = Date.now() - started
  if (!Number.isInteger(elapsedMs) || elapsedMs < 1 || elapsedMs > maxReceiptElapsedMs) {
    fail('browser_receipt_elapsed_invalid', String(elapsedMs))
  }
  return elapsedMs
}

async function validateReceiptAgainstSchema(receipt) {
  const schema = await readObject(receiptSchemaUrl, 'receipt_schema_invalid')
  const { default: Ajv2020 } = await import('ajv/dist/2020.js')
  const validate = new Ajv2020({ allErrors: true, strict: true }).compile(schema)
  if (!validate(receipt)) {
    fail('browser_receipt_schema_invalid', JSON.stringify(validate.errors ?? []))
  }
}

async function writeValidatedReceipt(output, receipt) {
  await validateReceiptAgainstSchema(receipt)
  await writeFile(output, `${JSON.stringify(receipt, null, 2)}\n`, { flag: 'wx', mode: 0o600 })
}

export async function optionalLocatorText(locator) {
  try {
    return await locator.first().evaluate(
      collectBoundedElementText,
      {
        maximumCharacters: maxDiagnosticTextBytes,
        maximumNodes: maxDiagnosticTextNodes,
      },
      { timeout: 1000 },
    )
  } catch {
    return ''
  }
}

export function collectBoundedElementText(element, { maximumCharacters, maximumNodes }) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
  let text = ''
  let visitedNodes = 0
  while (
    text.length < maximumCharacters
    && visitedNodes < maximumNodes
    && walker.nextNode()
  ) {
    visitedNodes += 1
    const value = walker.currentNode.nodeValue ?? ''
    text += value.slice(0, maximumCharacters - text.length)
  }
  return text
}

async function capturePanelDiagnostic(page) {
  try {
    const panel = page.locator('[data-native-frame-run]').first()
    return {
      status: (await panel.getAttribute('data-native-frame-run', { timeout: 1000 })) ?? 'missing',
      jobText: await optionalLocatorText(page.locator('[data-native-frame-run-job]')),
      errorText: await optionalLocatorText(page.locator('[data-native-frame-run-error]')),
    }
  } catch {
    return { status: 'unavailable', jobText: '', errorText: '' }
  }
}

async function readBoundedResponseBytes(response, limit) {
  if (!response.body) return Buffer.alloc(0)
  const reader = response.body.getReader()
  const chunks = []
  let total = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
    if (total > limit) {
      await reader.cancel()
      return null
    }
    chunks.push(Buffer.from(value))
  }
  return Buffer.concat(chunks, total)
}

function boundedPositiveInteger(value, fallback, maximum) {
  return Number.isFinite(value)
    ? Math.max(1, Math.min(Math.trunc(value), maximum))
    : fallback
}

export async function captureJobViewDiagnostic(
  origin,
  jobId,
  { timeoutMs = maxDiagnosticJobViewFetchMs } = {},
) {
  if (!jobIdPattern.test(jobId)) return { status: 'unavailable', errorCode: null }
  const boundedTimeoutMs = boundedPositiveInteger(
    timeoutMs,
    maxDiagnosticJobViewFetchMs,
    maxDiagnosticJobViewFetchMs,
  )
  try {
    const response = await fetch(`${origin}/api/v1/frame3d/jobs/${jobId}/view.json`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(boundedTimeoutMs),
    })
    const declared = Number(response.headers.get('content-length'))
    if (!response.ok || (Number.isFinite(declared) && declared > maxDiagnosticJobViewBytes)) {
      await response.body?.cancel()
      return { status: 'unavailable', errorCode: null }
    }
    const bytes = await readBoundedResponseBytes(response, maxDiagnosticJobViewBytes)
    if (bytes === null) {
      return { status: 'unavailable', errorCode: null }
    }
    const view = requireObject(JSON.parse(bytes.toString('utf8')), 'diagnostic_job_view_invalid')
    if (view.job_id !== jobId) return { status: 'unavailable', errorCode: null }
    const terminalError = view.status === 'cancelled' ? view.cancellation : view.error
    return {
      status: view.status,
      errorCode: requireObject(terminalError ?? {}, 'diagnostic_job_error_invalid').code ?? null,
    }
  } catch {
    return { status: 'unavailable', errorCode: null }
  }
}

async function writeFailureDiagnostic(output, values) {
  const diagnostic = buildBrowserFailureDiagnostic(values)
  await writeFile(output, `${JSON.stringify(diagnostic, null, 2)}\n`, {
    flag: 'wx',
    mode: 0o600,
  })
}

export async function firstLine(child) {
  if (!child.stdout) fail('host_stdout_missing')
  return await new Promise((resolve, reject) => {
    const chunks = []
    let total = 0
    let settled = false
    let timeout
    const cleanup = () => {
      clearTimeout(timeout)
      child.stdout.off('data', onData)
      child.stdout.off('error', onStdoutError)
      child.off('error', onError)
      child.off('exit', onExit)
      child.stdout.resume()
    }
    const finish = (error, line = '') => {
      if (settled) return
      settled = true
      cleanup()
      if (error) reject(error)
      else resolve(line)
    }
    const onData = (chunk) => {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
      const newline = bytes.indexOf(0x0a)
      const prefix = newline === -1 ? bytes : bytes.subarray(0, newline)
      if (total + prefix.length > maxHostStartupLineBytes) {
        finish(new Error('host_startup_line_too_large'))
        return
      }
      chunks.push(prefix)
      total += prefix.length
      if (newline !== -1) {
        const line = Buffer.concat(chunks, total).toString('utf8').replace(/\r$/, '')
        finish(null, line)
      }
    }
    const onError = (error) => finish(error)
    const onStdoutError = () => finish(new Error('host_stdout_error'))
    const onDrainedStdoutError = () => {}
    const onExit = (code) => finish(new Error(`host_exited_before_startup:${code}`))
    child.stdout.on('error', onDrainedStdoutError)
    child.stdout.once('error', onStdoutError)
    child.once('error', onError)
    child.once('exit', onExit)
    timeout = setTimeout(
      () => finish(new Error('host_startup_timeout')),
      maxHostStartupWaitMs,
    )
    child.stdout.on('data', onData)
  })
}

export async function fetchBytes(
  url,
  code,
  { maximumBytes = maxArtifactResponseBytes, timeoutMs = maxArtifactFetchMs } = {},
) {
  const boundedMaximumBytes = boundedPositiveInteger(
    maximumBytes,
    maxArtifactResponseBytes,
    maxArtifactResponseBytes,
  )
  const boundedTimeoutMs = boundedPositiveInteger(
    timeoutMs,
    maxArtifactFetchMs,
    maxArtifactFetchMs,
  )
  let response
  try {
    response = await fetch(url, {
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(boundedTimeoutMs),
    })
  } catch (error) {
    fail(code, error?.name === 'TimeoutError' ? 'timeout' : 'request_failed')
  }
  const declared = Number(response.headers.get('content-length'))
  if (!response.ok) {
    await response.body?.cancel()
    fail(code, `status_${response.status}`)
  }
  if (Number.isFinite(declared) && declared > boundedMaximumBytes) {
    await response.body?.cancel()
    fail(code, 'response_too_large')
  }
  let bytes
  try {
    bytes = await readBoundedResponseBytes(response, boundedMaximumBytes)
  } catch (error) {
    fail(code, error?.name === 'TimeoutError' ? 'timeout' : 'response_read_failed')
  }
  if (bytes === null) fail(code, 'response_too_large')
  return bytes
}

export async function closeBrowserBounded(
  browser,
  { timeoutMs = maxBrowserCleanupMs } = {},
) {
  const boundedTimeoutMs = boundedPositiveInteger(
    timeoutMs,
    maxBrowserCleanupMs,
    maxBrowserCleanupMs,
  )
  let timer
  const closed = Promise.resolve()
    .then(() => browser.close())
    .then(() => true, () => false)
  const timedOut = new Promise((resolve) => {
    timer = setTimeout(() => resolve(false), boundedTimeoutMs)
  })
  const result = await Promise.race([closed, timedOut])
  clearTimeout(timer)
  return result
}

async function waitBounded(operation, timeoutMs) {
  let timer
  const completed = Promise.resolve(operation).then(() => true, () => false)
  const timedOut = new Promise((resolve) => {
    timer = setTimeout(() => resolve(false), timeoutMs)
  })
  const result = await Promise.race([completed, timedOut])
  clearTimeout(timer)
  return result
}

async function stop(child) {
  if (hasChildStopped(child)) return
  child.kill()
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (!hasChildStopped(child)) child.kill('SIGKILL')
      resolve()
    }, 5000)
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

async function main() {
  const options = parseArguments(process.argv.slice(2))
  const manifestPath = path.join(options.packageRoot, 'manifest.json')
  const manifestBytes = await readFile(manifestPath)
  const manifest = requireObject(JSON.parse(manifestBytes.toString('utf8')), 'manifest_invalid')
  const source = requireObject(manifest.source, 'manifest_source_invalid')
  const binary = requireObject(manifest.binary, 'manifest_binary_invalid')
  if (
    source.commit_sha !== options.sourceCommit
    || manifest.platform_tag !== options.platformTag
    || typeof source.tree_sha !== 'string'
    || !/^[0-9a-f]{40}$/.test(source.tree_sha)
    || typeof binary.path !== 'string'
  ) fail('package_source_or_platform_mismatch')

  const binaryPath = path.join(options.packageRoot, ...binary.path.split('/'))
  const workbenchPath = path.join(options.packageRoot, 'workbench')
  const modelPath = path.join(
    options.packageRoot,
    'examples',
    'frame-alpha-cantilever.model-ir.json',
  )
  const model = await readObject(modelPath, 'model_invalid')
  if (
    model.model_id !== expectedModelId
    || !Array.isArray(model.load_patterns)
    || model.load_patterns.filter((row) => row?.id === expectedLoadPatternId).length !== 1
  ) fail('model_load_contract_invalid')
  const storePath = path.join(path.dirname(options.output), 'browser-job-store')
  const failureOutput = path.join(path.dirname(options.output), 'failure.json')
  let hostStderrBytes = 0
  const host = spawn(binaryPath, [
    'workstation',
    'serve',
    '--store', storePath,
    '--workbench', workbenchPath,
    '--listen', '127.0.0.1:0',
    '--worker-timeout-seconds', '30',
    '--max-requests', String(maxHostRequests),
  ], { stdio: ['ignore', 'pipe', 'pipe'] })
  const hostStderrDrained = new Promise((resolve) => {
    if (!host.stderr) {
      resolve()
      return
    }
    host.stderr.on('data', (chunk) => {
      hostStderrBytes = Math.min(
        maxDiagnosticTextBytes,
        hostStderrBytes + Buffer.byteLength(chunk),
      )
    })
    host.stderr.once('end', resolve)
    host.stderr.once('close', resolve)
    host.stderr.once('error', resolve)
  })

  let browser
  let page
  let failure
  let successReceipt
  let failureDiagnosticWritten = false
  let cleanupWatchdog
  let phase = 'host_startup'
  let panelDiagnostic = { status: 'unavailable', jobText: '', errorText: '' }
  let submittedJobId = ''
  let jobViewDiagnostic = { status: 'unavailable', errorCode: null }
  const pageErrors = []
  const started = Date.now()
  const armCleanupWatchdog = () => {
    if (!cleanupWatchdog) {
      cleanupWatchdog = setTimeout(() => process.exit(1), maxFailureCleanupWatchdogMs)
    }
  }
  const persistFailureDiagnostic = async () => {
    if (failureDiagnosticWritten) return
    await writeFailureDiagnostic(failureOutput, {
      sourceCommit: options.sourceCommit,
      platformTag: options.platformTag,
      phase,
      panel: panelDiagnostic,
      submittedJobId,
      jobView: jobViewDiagnostic,
      pageErrors,
      verifierError: String(failure),
      hostExitCode: host.exitCode,
      hostStderrBytes,
      elapsedMs: Date.now() - started,
    })
    failureDiagnosticWritten = true
  }
  try {
    const startup = requireObject(JSON.parse(await firstLine(host)), 'host_startup_invalid')
    if (
      startup.schema_version !== 'structural-native-frame-alpha-workstation-host.v2'
      || startup.service_profile !== 'loopback_worker_process_cancellation.v2'
      || !/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(startup.origin)
      || startup.submission_url !== `${startup.origin}/api/v1/frame3d/jobs`
    ) fail('host_startup_contract_invalid')

    phase = 'browser_launch'
    const { chromium } = await import('@playwright/test')
    browser = await chromium.launch()
    page = await browser.newPage()
    page.on('pageerror', () => recordBoundedPageError(pageErrors))
    page.on('request', (request) => {
      if (request.method() !== 'POST' || request.url() !== startup.submission_url) return
      try {
        const payload = request.postDataJSON()
        if (jobIdPattern.test(payload?.job_id ?? '')) submittedJobId = payload.job_id
      } catch {
        submittedJobId = ''
      }
    })
    phase = 'workbench_navigation'
    await page.goto(`${startup.origin}/#/workbench-v2`, {
      waitUntil: 'load',
      timeout: 30000,
    })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('[data-native-frame-model-file]').setInputFiles(modelPath)
    await page.locator('[data-native-frame-load-id]').fill(expectedLoadPatternId)
    await page.locator('[data-native-frame-result-id]').fill(expectedResultId)
    await page.locator('[data-native-frame-report-id]').fill('report.browser.LC_WEAK')
    phase = 'native_job_terminal_wait'
    await page.locator('[data-native-frame-run-submit]').click()
    let timedOut = false
    try {
      await page.locator([
        '[data-native-frame-run="succeeded"]',
        '[data-native-frame-run="failed"]',
        '[data-native-frame-run="cancelled"]',
      ].join(', ')).waitFor({ state: 'visible', timeout: 60000 })
    } catch (error) {
      if (error?.name !== 'TimeoutError') throw error
      timedOut = true
    }
    panelDiagnostic = await capturePanelDiagnostic(page)
    const panelOutcome = classifyNativeFramePanelState(panelDiagnostic.status, { timedOut })
    if (panelOutcome !== 'succeeded') {
      jobViewDiagnostic = await captureJobViewDiagnostic(startup.origin, submittedJobId)
      fail(
        `browser_native_run_${panelOutcome}`,
        [
          panelDiagnostic.status,
          extractStableDiagnosticCode(panelDiagnostic.errorText),
          submittedJobId,
          jobViewDiagnostic.status,
          extractStableDiagnosticCode(jobViewDiagnostic.errorCode),
        ].filter(Boolean).join('|'),
      )
    }
    phase = 'browser_artifact_validation'
    const artifacts = page.locator('[data-native-frame-artifacts="ready"]')
    await artifacts.waitFor({ state: 'visible', timeout: 30000 })
    if (await artifacts.getAttribute('data-native-frame-integrity') !== 'bundle_verified') {
      fail('browser_bundle_integrity_not_verified')
    }
    if (await artifacts.locator('[data-native-frame-result-ir]').getAttribute('data-native-frame-result-ir') !== 'verified') {
      fail('browser_result_ir_not_verified')
    }
    const releaseAuthority = await artifacts.locator('[data-native-frame-release-authority]').innerText()
    if (releaseAuthority.trim() !== 'not_authoritative') fail('browser_release_authority_promoted')
    const jobText = await page.locator('[data-native-frame-run-job]').innerText()
    const jobMatch = jobText.match(/job_[0-9a-f]{32}/)
    if (!jobMatch) fail('browser_job_id_missing')
    const jobId = jobMatch[0]
    requireMatchingJobIdentity(
      jobId,
      submittedJobId,
      'browser_submitted_job_identity_mismatch',
    )

    const viewUrl = `${startup.origin}/api/v1/frame3d/jobs/${jobId}/view.json`
    const viewBytes = await fetchBytes(viewUrl, 'job_view_fetch_failed')
    const view = requireObject(JSON.parse(viewBytes.toString('utf8')), 'job_view_invalid')
    requireMatchingJobIdentity(view.job_id, jobId, 'job_view_identity_mismatch')
    const bundleReference = requireObject(view.bundle_manifest, 'bundle_reference_invalid')
    if (view.status !== 'succeeded' || bundleReference.path !== 'bundle/manifest.json') {
      fail('job_view_not_succeeded')
    }
    const bundleUrl = new URL(bundleReference.path, viewUrl).toString()
    const bundleBytes = await fetchBytes(bundleUrl, 'bundle_manifest_fetch_failed')
    requireArtifactByteLength(
      bundleReference,
      bundleBytes,
      'bundle_manifest_byte_length_mismatch',
    )
    if (sha256(bundleBytes) !== bundleReference.content_hash) fail('bundle_manifest_hash_mismatch')
    const bundle = requireObject(JSON.parse(bundleBytes.toString('utf8')), 'bundle_manifest_invalid')
    const bundleArtifacts = requireObject(bundle.artifacts, 'bundle_artifacts_invalid')
    const modelArtifact = requireObject(bundleArtifacts.model_ir, 'model_artifact_invalid')
    const resultArtifact = requireObject(
      bundleArtifacts.result_ir,
      'result_artifact_invalid',
    )
    if (modelArtifact.path !== 'model-ir.json' || resultArtifact.path !== 'result-ir.json') {
      fail('bundle_artifact_path_invalid')
    }
    const bundledModelUrl = new URL(modelArtifact.path, bundleUrl).toString()
    const bundledModelBytes = await fetchBytes(bundledModelUrl, 'model_ir_fetch_failed')
    requireArtifactByteLength(modelArtifact, bundledModelBytes, 'model_ir_byte_length_mismatch')
    if (sha256(bundledModelBytes) !== modelArtifact.content_hash) fail('model_ir_hash_mismatch')
    const bundledModel = requireObject(
      JSON.parse(bundledModelBytes.toString('utf8')),
      'bundled_model_invalid',
    )
    if (bundledModel.model_id !== model.model_id) fail('bundled_model_identity_mismatch')
    const resultUrl = new URL(resultArtifact.path, bundleUrl).toString()
    const resultBytes = await fetchBytes(resultUrl, 'result_ir_fetch_failed')
    requireArtifactByteLength(resultArtifact, resultBytes, 'result_ir_byte_length_mismatch')
    if (sha256(resultBytes) !== resultArtifact.content_hash) fail('result_ir_hash_mismatch')
    const result = requireObject(JSON.parse(resultBytes.toString('utf8')), 'result_ir_invalid')
    validateBrowserResultContract({ model, view, bundle, result, pageErrors })

    const elapsedMs = validatedElapsedMs(started)
    successReceipt = {
      schema_version: schemaVersion,
      status: 'pass',
      source,
      platform_tag: options.platformTag,
      package: {
        package_id: manifest.package_id,
        manifest_sha256: sha256(manifestBytes),
        binary_sha256: binary.sha256,
        workbench_index_sha256: manifest.workbench?.index_sha256,
      },
      browser: {
        engine: 'chromium',
        version: browser.version(),
        route: '/#/workbench-v2',
        packaged_static_files_only: true,
      },
      execution: {
        job_id: jobId,
        job_view_sha256: sha256(viewBytes),
        bundle_manifest_sha256: sha256(bundleBytes),
        model_ir_sha256: sha256(bundledModelBytes),
        result_ir_sha256: sha256(resultBytes),
        result_hash: result.result_hash,
        elapsed_ms: elapsedMs,
      },
      checks: {
        model_file_uploaded: true,
        same_origin_job_submitted: true,
        native_worker_succeeded: true,
        bundle_integrity_verified_in_browser: true,
        result_ir_verified_in_browser: true,
        selected_load_binding_verified: true,
        model_result_bindings_verified: true,
        numerical_gates_passed: true,
        receipt_schema_validated_before_write: true,
        release_authority_remained_blocked: true,
        page_error_count: 0,
      },
      authority: {
        packaged_browser_execution: 'passed',
        human_new_user_observation: 'not_evaluated',
        accessibility_review: 'not_evaluated',
        os_code_signing: 'not_evaluated',
        automatic_update: 'not_implemented',
        rollback: 'not_implemented',
        engineering_design: 'not_authoritative',
        commercial_use: 'not_authoritative',
        release_readiness: 'not_authoritative',
      },
      claim_boundary: 'one_packaged_workbench_chromium_upload_submit_run_poll_and_verified_result_replay_not_human_observation_accessibility_code_signing_update_rollback_or_release_authority',
    }
    phase = 'browser_cleanup'
  } catch (error) {
    failure = error
    armCleanupWatchdog()
    if (page) panelDiagnostic = await capturePanelDiagnostic(page)
    await stop(host)
    await waitBounded(hostStderrDrained, maxStderrDrainMs)
    await persistFailureDiagnostic()
  } finally {
    const browserClosed = browser ? await closeBrowserBounded(browser) : true
    await stop(host)
    await waitBounded(hostStderrDrained, maxStderrDrainMs)
    const cleanupFailure = classifyCleanupFailure({
      browserClosed,
      hostStopped: hasChildStopped(host),
    })
    if (!failure && cleanupFailure) {
      phase = cleanupFailure === 'browser_cleanup_timeout' ? 'browser_cleanup' : 'host_cleanup'
      failure = new Error(cleanupFailure)
      armCleanupWatchdog()
      await persistFailureDiagnostic()
    }
    if (cleanupWatchdog && browserClosed && hasChildStopped(host)) {
      clearTimeout(cleanupWatchdog)
    }
  }
  if (failure) {
    throw failure
  }
  phase = 'success_receipt_write'
  try {
    await writeValidatedReceipt(options.output, successReceipt)
    process.stdout.write(`${JSON.stringify(successReceipt)}\n`)
  } catch (error) {
    failure = error
    armCleanupWatchdog()
    try {
      await persistFailureDiagnostic()
      throw failure
    } finally {
      if (cleanupWatchdog) clearTimeout(cleanupWatchdog)
    }
  }
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`Packaged browser replay failed: ${String(error)}\n`)
    process.exitCode = 1
  })
}
