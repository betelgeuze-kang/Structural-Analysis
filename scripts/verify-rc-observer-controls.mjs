import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawn } from 'node:child_process'
import { connect } from 'node:net'
import { trustedNode, trustedRepoTool, sanitizedFrontendEnvironment } from './trusted-frontend-runtime.mjs'
import { startRcObserverCompiled } from './serve-rc-observer-compiled.mjs'
import {
  controlBytes, controlHash, controlOptions, controlsSourceUnchanged, prepareControls,
  retainControlsNative, writeControlsReceipt,
} from './rc-observer-controls-artifacts.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sources = [
  'package.json', 'package-lock.json', '.github/workflows/frontend-web-ci.yml',
  'scripts/verify-rc-observer-controls.mjs', 'scripts/rc-observer-controls-artifacts.mjs',
  'scripts/build-rc-observer-harness.mjs', 'scripts/serve-rc-observer-compiled.mjs',
  'scripts/rc-observer-positive.config.mjs', 'scripts/rc-observer-negative.config.mjs',
  'scripts/trusted-frontend-runtime.mjs', 'scripts/json-module-loader.mjs', 'tests/rc-observer-controls-retention.test.mjs',
  'tests/frontend/rc-observer-browser.spec.ts', 'tests/frontend/rc-observer-teardown-negative-control.spec.ts',
  'tests/frontend/rc-observer-harness.tsx', 'tests/frontend/rc-observer-harness.html',
  'tests/frontend/rcInitialReadyDiagnostics.ts', 'tests/frontend/workbench-v2-rc-workflow-browser.spec.ts',
  'src/vite-env.d.ts', 'src/workbench-v2/components/RcJobWorkflowPanel.tsx',
  'src/workbench-v2/model/rcWorkflowTrace.ts', 'src/workbench-v2/model/jobTransport.ts',
  'src/workbench-v2/model/jobProvider.ts', 'src/workbench-v2/model/rcWorkflowProvider.ts',
  'src/workbench-v2/model/failureDiagnostic.ts',
]
const active = new Set()
let interrupted = false
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
function groupExists(pid) {
  try { process.kill(-pid, 0); return true } catch (error) { if (error.code === 'ESRCH') return false; throw error }
}
function signalOwned(child, signal) {
  if (!Number.isSafeInteger(child.pid) || child.pid <= 0) return
  try { process.kill(-child.pid, signal) } catch (error) { if (error.code !== 'ESRCH') throw error }
}
async function closeOwnedGroup(child) {
  if (!Number.isSafeInteger(child.pid) || child.pid <= 0) return { absent: true, termSent: false, killSent: false }
  const observation = { absent: !groupExists(child.pid), termSent: false, killSent: false }
  if (!observation.absent) {
    signalOwned(child, 'SIGTERM'); observation.termSent = true
    for (let count = 0; count < 20 && groupExists(child.pid); count++) await delay(50)
    if (groupExists(child.pid)) { signalOwned(child, 'SIGKILL'); observation.killSent = true }
    for (let count = 0; count < 80 && groupExists(child.pid); count++) await delay(50)
    observation.absent = !groupExists(child.pid)
  }
  return observation
}
function interrupt() {
  interrupted = true
  for (const child of active) signalOwned(child, 'SIGTERM')
}
process.once('SIGTERM', interrupt)
process.once('SIGINT', interrupt)

async function runOwned(node, argv, environment, stage, budget) {
  if (interrupted) throw new Error('rc_control_interrupted')
  const child = spawn(node, argv, { cwd: root, stdio: 'inherit', env: environment, detached: true })
  active.add(child)
  let timedOut = false, killTimer
  const timer = setTimeout(() => {
    timedOut = true
    signalOwned(child, 'SIGTERM')
    killTimer = setTimeout(() => signalOwned(child, 'SIGKILL'), 5000)
  }, budget)
  const result = await new Promise(resolve => {
    child.once('error', () => resolve({ code: 1, signal: null, spawnError: true }))
    child.once('close', (code, signal) => resolve({ code: code ?? 1, signal, spawnError: false }))
  })
  clearTimeout(timer); clearTimeout(killTimer)
  const groupCleanup = await closeOwnedGroup(child)
  active.delete(child)
  return { stage, pid: child.pid ?? null, argv, ...result, timedOut, ownedProcessGroup: true, groupCleanup }
}

async function ownPortClosed(port) {
  return new Promise(resolve => {
    const socket = connect({ host: '127.0.0.1', port })
    let finished = false
    const finish = value => { if (!finished) { finished = true; socket.destroy(); resolve(value) } }
    socket.once('error', error => finish(error.code === 'ECONNREFUSED'))
    socket.once('connect', () => finish(false))
    socket.setTimeout(1000, () => finish(false))
  })
}
const complete = record => !record.timedOut && !record.spawnError && !record.signal && record.groupCleanup.absent

async function main() {
  const node = trustedNode(), options = controlOptions(process.argv.slice(2))
  const compiler = trustedRepoTool(root, 'node_modules/typescript/bin/tsc', 'rc_control_typescript')
  const playwright = trustedRepoTool(root, 'node_modules/playwright/cli.js', 'rc_control_playwright')
  const builder = trustedRepoTool(root, 'scripts/build-rc-observer-harness.mjs', 'rc_control_builder')
  const jsonLoader = trustedRepoTool(root, 'scripts/json-module-loader.mjs', 'rc_control_json_loader')
  const positiveConfig = trustedRepoTool(root, 'scripts/rc-observer-positive.config.mjs', 'rc_control_positive_config')
  const negativeConfig = trustedRepoTool(root, 'scripts/rc-observer-negative.config.mjs', 'rc_control_negative_config')
  const unit = trustedRepoTool(root, 'tests/rc-observer-controls-retention.test.mjs', 'rc_control_retention_test')
  const state = prepareControls(options, root, sources)
  const receipt = { schema: 1, checkout_sha_from_workflow: options.sha, github_run_id: options['run-id'],
    github_run_attempt: options['run-attempt'], stages: [], positive: null, negative: null,
    cleanup: null, ownPortRefusedAfterClose: false, sourceUnchanged: false, controlsQualified: false,
    reason: null, interpretation: 'Positive12 native pass plus separately declared intentional-negative2 native failure witness.',
    generated_artifact_is_immutable_source_proof: false, full_R2_hosted_physical_release_authority: false }
  let server, originalPositiveCode = 0
  try {
    const environment = sanitizedFrontendEnvironment(node)
    const compilerArgs = [compiler, '--noEmit', '--target', 'ES2020', '--useDefineForClassFields', 'true',
      '--lib', 'ES2020,DOM,DOM.Iterable', '--module', 'ESNext', '--skipLibCheck', 'true',
      '--moduleResolution', 'Bundler', '--resolveJsonModule', 'true', '--isolatedModules', 'true',
      '--jsx', 'react-jsx', '--strict', 'true',
      'tests/frontend/rc-observer-browser.spec.ts', 'tests/frontend/rc-observer-harness.tsx',
      'tests/frontend/rc-observer-teardown-negative-control.spec.ts', 'tests/frontend/rcInitialReadyDiagnostics.ts',
      'tests/frontend/workbench-v2-rc-workflow-browser.spec.ts', 'src/vite-env.d.ts']
    for (const [stage, argv] of [
      ['unit-tests', ['--test', unit]],
      ['test-source-compiler', compilerArgs],
      ['development-harness-build', [builder, root, state.directory]],
    ]) {
      const record = await runOwned(node, argv, environment, stage, 120000)
      receipt.stages.push(record)
      if (record.code !== 0 || !complete(record)) throw new Error('rc_control_preflight_failed')
    }
    const manifestBytes = controlBytes(path.join(state.directory, 'compiled-manifest.json'), 128 * 1024)
    server = await startRcObserverCompiled({ directory: state.directory, manifestSha256: controlHash(manifestBytes) })
    const base = 'http://127.0.0.1:' + server.port
    const loader = '--loader=' + pathToFileURL(jsonLoader).href
    const native = {}
    for (const [lane, config, budget] of [['positive', positiveConfig, 180000], ['negative', negativeConfig, 90000]]) {
      const record = await runOwned(node, [loader, playwright, 'test', '--config', config],
        sanitizedFrontendEnvironment(node, { WORKBENCH_V2_BASE_URL: base,
          PLAYWRIGHT_JSON_OUTPUT_FILE: path.join(state.directory, lane + '-raw-native.json') }), lane, budget)
      receipt.stages.push(record); native[lane] = record
      if (lane === 'positive') originalPositiveCode = record.code
    }
    // Both original native invocations are retained, even if qualification of either fails.
    const failures = []
    for (const lane of ['positive', 'negative']) {
      try {
        receipt[lane] = retainControlsNative(state, lane, native[lane].code)
        if (!complete(native[lane])) throw new Error('rc_control_native_process_cleanup')
      } catch (error) {
        failures.push(typeof error.message === 'string' && error.message.startsWith('rc_control_') ? error.message : 'rc_control_native_retention_error')
      }
    }
    if (failures.length) throw new Error(failures.join(','))
    if (interrupted) throw new Error('rc_control_interrupted')
  } catch (error) {
    receipt.reason = typeof error?.message === 'string' && error.message.startsWith('rc_control_')
      ? error.message.slice(0, 256) : 'rc_control_execution_error'
    console.error('RC observer controls unqualified: ' + receipt.reason)
  } finally {
    try {
      if (server) {
        receipt.cleanup = await server.close()
        receipt.ownPortRefusedAfterClose = await ownPortClosed(server.port)
        if (!receipt.cleanup.closed || receipt.cleanup.closeError || receipt.cleanup.timedOut
          || receipt.cleanup.errors !== 0 || receipt.cleanup.pinRefusals !== 0 || receipt.cleanup.listenerErrors !== 0
          || receipt.cleanup.requests <= 0 || !receipt.ownPortRefusedAfterClose) receipt.reason = 'rc_control_listener_cleanup_or_pin_failure'
      } else if (!receipt.reason) receipt.reason = 'rc_control_listener_missing'
    } catch { receipt.reason = 'rc_control_listener_cleanup_error' }
    try {
      receipt.sourceUnchanged = controlsSourceUnchanged(state)
      if (!receipt.sourceUnchanged) receipt.reason = 'rc_control_source_changed'
    } catch { receipt.reason = 'rc_control_source_readback_failed' }
    receipt.controlsQualified = !receipt.reason && Boolean(receipt.positive && receipt.negative && receipt.cleanup)
    try { writeControlsReceipt(state, receipt) } catch {
      receipt.controlsQualified = false; receipt.reason = 'rc_control_receipt_write_failed'
      console.error('RC observer controls unqualified: ' + receipt.reason)
    }
    process.removeListener('SIGTERM', interrupt); process.removeListener('SIGINT', interrupt)
    process.exitCode = originalPositiveCode !== 0 ? originalPositiveCode : receipt.controlsQualified ? 0 : 1
  }
  if (receipt.controlsQualified) console.log('RC observer controls retained: positive native exit0/12 expected; intentional negative native exit1/2 unexpected.')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
