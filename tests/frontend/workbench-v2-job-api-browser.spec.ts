import { expect, test } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { gzipSync } from 'node:zlib'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import { waitForJobService } from './jobServiceBrowserWait'

const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-memory-only-token' }

test.describe('real durable API browser authentication', () => {
  let server: ChildProcess
  let origin: string
  let realJob: WorkbenchJobView
  let failedJob: WorkbenchJobView
  test.beforeAll(async () => {
    server = spawn('python3', ['-B', 'tests/frontend/job_transport_server.py'], {
      env: { ...process.env, PYTHONPATH: resolve('src') }, stdio: ['ignore', 'pipe', 'pipe'],
    })
    const ready = await new Promise<{ origin: string; job: WorkbenchJobView; failed_job: WorkbenchJobView }>((resolveReady, reject) => {
      let output = ''
      let error = ''
      const timer = setTimeout(() => reject(new Error(`test API startup timed out: ${error}`)), 15000)
      server.once('error', (failure) => { clearTimeout(timer); reject(failure) })
      server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`test API exited ${code}: ${error}`)) })
      server.stderr!.on('data', (chunk) => { error = (error + String(chunk)).slice(-2000) })
      server.stdout!.on('data', (chunk) => {
        output += String(chunk)
        if (!output.includes('\n')) return
        clearTimeout(timer)
        try { resolveReady(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('test API ready message is invalid')) }
      })
    })
    origin = ready.origin
    realJob = ready.job
    failedJob = ready.failed_job
  })
  test.afterAll(async () => {
    if (!server || server.exitCode !== null || server.signalCode !== null) return
    const closed = new Promise<void>((done) => server.once('exit', () => done()))
    server.kill('SIGTERM')
    await closed
  })
  test('loads the real queued RC job and reads its exact original request with tenant isolation', async ({ page }) => {
    const path = `/v1/jobs/${realJob.job_id}`
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path, credentials })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page)
    await expect(page.locator('[data-job-service]')).toHaveAttribute('data-job-status', 'queued')
    await expect(page.locator('[data-job-error-code]')).toHaveText('none reported')
    await expect(page.locator('[data-job-failure-scope]')).toHaveCount(0)
    await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
    // These network reads also exercise the real WSGI original-request route.
    // The page above tests the host callback -> provider -> actual API chain.
    const headers = { 'X-Structural-Tenant': credentials.tenantId, Authorization: `Bearer ${credentials.bearerToken}` }
    const response = await page.request.get(`${origin}${path}/request`, { headers })
    expect(response.status()).toBe(200)
    const bytes = await response.body()
    expect(bytes.byteLength).toBe(realJob.request.byte_length)
    expect(`sha256:${createHash('sha256').update(bytes).digest('hex')}`).toBe(realJob.request.content_hash)
    expect(JSON.parse(bytes.toString()).operation).toBe('bounded_rc_fiber_direct_control')
    expect((await page.request.get(`${origin}${path}/request`)).status()).toBe(401)
    expect((await page.request.get(`${origin}${path}/request`, {
      headers: { 'X-Structural-Tenant': 'other-tenant', Authorization: 'Bearer synthetic-other-tenant-token' },
    })).status()).toBe(404)
  })
  test('fails closed on an actual API credential rejection', async ({ page }) => {
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path: `/v1/jobs/${realJob.job_id}`, credentials: { ...credentials, bearerToken: 'wrong-synthetic-token' } })
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page, 'error')
    await expect(page.locator('[data-job-service]')).toContainText('HTTP 401')
    await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
  })
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    test(`shows durable failure without numerical authority at width ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await page.addInitScript(({ path, credentials }) => {
        window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
      }, { path: `/v1/jobs/${failedJob.job_id}`, credentials })
      await page.goto(`${origin}/#/workbench-v2`)
      await waitForJobService(page)
      await expect(page.locator('[data-job-service]')).toHaveAttribute('data-job-status', 'failed')
      await expect(page.locator('[data-job-error-code]')).toHaveText('synthetic_transport_failure')
      await expect(page.locator('[data-job-failure-scope]')).toContainText('does not include every attempted calculation')
      await expect(page.locator('[data-job-convergence]')).toHaveAttribute('data-job-convergence', 'unavailable')
      await expect(page.locator('[data-job-result-ir]')).toHaveAttribute('data-job-result-ir', 'unavailable')
      await expect(page.locator('[data-rc-job-review], [data-frame3d-job-review]')).toHaveCount(0)
    })
  }
})

type LiveReady = { origin: string; originals: Record<string, { path: string; bytes: number; sha256: string }> }
const liveCredentials = { tenantId: 'rc-live-test', bearerToken: 'synthetic-rc-live-tenant-token' }
const liveHeaders = { 'X-Structural-Tenant': liveCredentials.tenantId, Authorization: `Bearer ${liveCredentials.bearerToken}`, 'Content-Type': 'application/json' }
const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`

type LiveProcess = { child: ChildProcess; role: string; output: string; error: string; ended: boolean; closed: Promise<void> }

function trackLiveProcess(role: string, args: string[], processes: LiveProcess[]): LiveProcess {
  const child = spawn('python3', ['-B', 'tests/frontend/rc_pin_roller_http_fixture.py', ...args], {
    env: { ...process.env, PYTHONPATH: resolve('src') }, stdio: ['ignore', 'pipe', 'pipe'],
  })
  const record: LiveProcess = { child, role, output: '', error: '', ended: false, closed: Promise.resolve() }
  record.closed = new Promise<void>(done => child.once('close', () => { record.ended = true; done() }))
  child.stdout!.on('data', chunk => { record.output += String(chunk) })
  child.stderr!.on('data', chunk => { record.error += String(chunk) })
  child.on('error', error => { record.error += String(error) })
  processes.push(record)
  return record
}

async function boundedWait(closed: Promise<void>, milliseconds: number): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([closed.then(() => true), new Promise<boolean>(done => { timer = setTimeout(() => done(false), milliseconds) })])
  } finally { if (timer) clearTimeout(timer) }
}

async function closeLiveServer(record: LiveProcess): Promise<void> {
  if (record.ended) return
  record.child.kill('SIGTERM')
  if (await boundedWait(record.closed, 5000)) return
  record.child.kill('SIGKILL')
  if (!(await boundedWait(record.closed, 5000))) throw new Error(`Unreaped ${record.role} child; retain its store`)
}

async function startLiveServer(store: string, processes: LiveProcess[]): Promise<{ child: ChildProcess; record: LiveProcess; ready: LiveReady }> {
  const record = trackLiveProcess('server', ['serve', '--store', store], processes)
  const child = record.child
  const ready = await new Promise<LiveReady>((done, reject) => {
    let output = '', error = ''
    const timer = setTimeout(() => reject(new Error(`RC HTTP startup timeout: ${error}`)), 15000)
    child.once('error', failure => { clearTimeout(timer); reject(failure) })
    child.once('exit', code => { clearTimeout(timer); reject(new Error(`RC HTTP startup exited ${code}: ${error}`)) })
    child.stderr!.on('data', chunk => { error = (error + String(chunk)).slice(-2000) })
    child.stdout!.on('data', chunk => {
      output += String(chunk)
      if (!output.includes('\n')) return
      clearTimeout(timer)
      try { done(JSON.parse(output.split('\n')[0])) } catch { reject(new Error('Invalid RC HTTP ready message')) }
    })
  }).catch(async error => { await closeLiveServer(record); throw error })
  return { child, record, ready }
}

async function runLiveWorker(store: string, processes: LiveProcess[]): Promise<any> {
  const record = trackLiveProcess('worker', ['worker', '--store', store, '--execute-rc-pin-roller'], processes)
  if (!(await boundedWait(record.closed, 45000))) {
    await closeLiveServer(record)
    throw new Error('Actual RC worker timeout; durable store retained with unknown pending work')
  }
  if (record.child.exitCode !== 0) throw new Error(`Actual RC worker exit ${record.child.exitCode}: ${record.error}`)
  try { return JSON.parse(record.output.trim()) } catch { throw new Error(`Invalid actual RC worker result: ${record.error}`) }
}

async function blobNames(directory: string): Promise<string[]> {
  const names: string[] = []
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, item.name)
    if (item.isDirectory()) names.push(...await blobNames(path))
    else names.push(path)
  }
  return names.sort()
}

for (const hasPreload of [false, true]) {
test(`actual pin/roller HTTP ${hasPreload ? 'with constant preload' : 'without preload'} chunks survive a new server process and match a full fresh worker path`, async ({ page }, testInfo) => {
  test.setTimeout(180000)
  const store = await mkdtemp(join(tmpdir(), 'structural-rc-live-http-'))
  const originals: Record<string, Buffer> = {}
  const processes: LiveProcess[] = []
  const requestName = hasPreload ? 'preload' : 'request'
  const fullName = hasPreload ? 'preload-full' : 'full'
  const observations: any = { has_preload: hasPreload, source_role: 'authored software regression', independent_physical_validation: false, hardware_attestation: false, browser_reruns_solver: false }
  let mounted: Awaited<ReturnType<typeof startLiveServer>> | undefined
  try {
    mounted = await startLiveServer(store, processes)
    let origin = mounted.ready.origin
    const request = await readFile(mounted.ready.originals[requestName].path)
    expect(digest(request)).toBe(mounted.ready.originals[requestName].sha256)
    expect(request.length).toBe(mounted.ready.originals[requestName].bytes)
    originals['submitted-request.json'] = request
    const input = JSON.parse(request.toString())
    observations.source_revision_caller_declaration = input.source_revision
    const submit = async (name: string, key: string, headers = liveHeaders) => page.request.post(`${origin}/v1/jobs`, {
      headers: { ...headers, 'Idempotency-Key': key }, data: await readFile(mounted!.ready.originals[name].path),
    })
    expect((await page.request.post(`${origin}/v1/jobs`, { data: request, headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'unauthorized' } })).status()).toBe(401)
    expect((await submit(requestName, 'wrong-auth', { ...liveHeaders, Authorization: 'Bearer wrong-synthetic-token' })).status()).toBe(401)
    const posted = await submit(requestName, 'actual-pin-roller')
    expect(posted.status()).toBe(202)
    const job = await posted.json()
    observations.submitted_job_id = job.job_id
    const path = `/v1/jobs/${job.job_id}`
    const initialBlobs = await blobNames(join(store, 'blobs'))
    const retry = await submit(requestName, 'actual-pin-roller')
    expect(retry.status()).toBe(202)
    expect((await retry.json()).job_id).toBe(job.job_id)
    expect((await submit('conflict', 'actual-pin-roller')).status()).toBe(409)
    for (const [name, code] of [['bad-preload', 'rc_fiber_job_request_invalid'], ['wrong-profile', 'job_schema_invalid']]) {
      const rejected = await submit(name, `unsupported-${name}`)
      expect(rejected.status()).toBe(400)
      const exclusion = (await rejected.json()).error
      // Constant loads on supports fail pure validation; two fixed endpoints
      // remain excluded by the public schema. Neither reaches a numerical call.
      expect(exclusion.code).toBe(code)
      observations[`${name}_http_exclusion`] = exclusion
    }
    expect(await blobNames(join(store, 'blobs'))).toEqual(initialBlobs)
    expect((await page.request.get(`${origin}${path}/request`)).status()).toBe(401)
    expect((await page.request.get(`${origin}${path}/request`, { headers: { 'X-Structural-Tenant': 'other-tenant', Authorization: 'Bearer synthetic-other-tenant-token' } })).status()).toBe(404)
    const get = async (role?: string): Promise<Buffer> => {
      const response = await page.request.get(`${origin}${path}${role ? `/${role}` : ''}`, { headers: liveHeaders })
      expect(response.status()).toBe(200)
      return response.body()
    }
    const persistedRequest = await get('request')
    expect(persistedRequest).toEqual(request)
    expect(digest(persistedRequest)).toBe(job.request.content_hash)
    const first = await runLiveWorker(store, processes)
    expect(first.job.status).toBe('checkpointed')
    expect(first.job.progress).toEqual({ completed_steps: 1, total_steps: 2 })
    expect(first.job.result).toBeNull()
    expect(first.job.evidence).toBeNull()
    expect(first.actual_calls).toMatchObject({ analysis: 1, verification: 1, core_targets: 2, core_preloads: hasPreload ? 2 : 0, preload_by_phase: { analysis: hasPreload ? 1 : 0, verification: hasPreload ? 1 : 0 } })
    observations.first_worker = first
    originals['first-checkpoint.json'] = await get('checkpoint')
    expect(digest(originals['first-checkpoint.json'])).toBe(first.job.checkpoint.content_hash)
    const firstCheckpoint = JSON.parse(originals['first-checkpoint.json'].toString())
    const prefix = JSON.parse((await get('rc-invocations')).toString())
    expect(prefix.pending_ordinals).toEqual([])
    expect(prefix.invocations).toHaveLength(2)
    for (const ref of prefix.invocations) {
      const bytes = await get(`rc-invocations/${ref.ordinal}`)
      expect(digest(bytes)).toBe(ref.content_hash); expect(bytes.length).toBe(ref.byte_length)
      originals[`invocation-${ref.ordinal}.json`] = bytes
    }
    await page.addInitScript(({ path, credentials }) => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
    }, { path, credentials: liveCredentials })
    await page.goto(`${origin}/#/workbench-v2`)
    const checkpointPanel = await waitForJobService(page)
    await expect(checkpointPanel).toHaveAttribute('data-job-status', 'checkpointed')
    await expect(checkpointPanel.locator('[data-job-resume]')).toContainText('Checkpoint saved; worker continuation available')
    await expect(checkpointPanel).toContainText('1 of 2 step(s) durably committed')
    await expect(page.locator('[data-rc-review]')).toHaveCount(0)
    const beforeRestart = await get()
    await closeLiveServer(mounted.record)
    expect(mounted.child.exitCode).toBe(0)
    mounted = await startLiveServer(store, processes)
    origin = mounted.ready.origin
    expect(await get()).toEqual(beforeRestart)
    expect(await get('request')).toEqual(persistedRequest)
    expect(await get('checkpoint')).toEqual(originals['first-checkpoint.json'])
    for (const ref of prefix.invocations) expect(await get(`rc-invocations/${ref.ordinal}`)).toEqual(originals[`invocation-${ref.ordinal}.json`])
    observations.server_reopened_in_new_process = true
    const second = await runLiveWorker(store, processes)
    expect(second.job.status).toBe('succeeded')
    expect(second.job.attempt).toBe(2)
    expect(second.job.progress).toEqual({ completed_steps: 2, total_steps: 2 })
    expect(second.actual_calls).toMatchObject({ analysis: 1, verification: 1, core_targets: 4, core_preloads: hasPreload ? 2 : 0, preload_by_phase: { analysis: hasPreload ? 1 : 0, verification: hasPreload ? 1 : 0 } })
    observations.second_worker = second
    for (const role of ['request', 'checkpoint', 'result', 'evidence']) {
      const body = await get(role)
      originals[`${role}.json`] = body
      expect(digest(body)).toBe(second.job[role].content_hash)
      expect(body.length).toBe(second.job[role].byte_length)
    }
    const result = JSON.parse(originals['result.json'].toString())
    expect(result.receipts).toHaveLength(2)
    expect(result.receipts[0]).toEqual(firstCheckpoint.receipts[0])
    expect(result.receipts[1].api_request.restart_input_sha256).toBe(firstCheckpoint.receipts[0].checkpoint_sha256)
    const envelope = JSON.parse((await get('rc-invocations')).toString())
    expect(envelope.pending_ordinals).toEqual([])
    expect(envelope.invocations.map((x: any) => x.ordinal)).toEqual([1, 2, 3, 4])
    const outcomes = []
    for (const ref of envelope.invocations) {
      const body = await get(`rc-invocations/${ref.ordinal}`)
      expect(digest(body)).toBe(ref.content_hash); expect(body.length).toBe(ref.byte_length)
      originals[`invocation-${ref.ordinal}.json`] = body
      outcomes.push(JSON.parse(body.toString()))
    }
    expect(outcomes.map(x => x.phase)).toEqual(['analysis', 'verification', 'analysis', 'verification'])
    for (const outcome of outcomes) {
      expect(outcome.status).toBe('returned')
      expect(outcome.unavailable_execution_work).toBe(false)
      if (outcome.phase === 'verification') for (const key of ['artifact_contract_pass', 'contract_pass', 'physical_path_complete', 'fresh_source_execution_invoked', 'solver_replay_performed']) expect(outcome.verification_report[key]).toBe(true)
    }
    const fullPosted = await submit(fullName, 'full-reference')
    expect(fullPosted.status()).toBe(202)
    const fullJob = await fullPosted.json()
    const full = await runLiveWorker(store, processes)
    expect(full.job.job_id).toBe(fullJob.job_id)
    expect(full.job.status).toBe('succeeded')
    expect(full.actual_calls).toMatchObject({ analysis: 1, verification: 1, core_targets: 4, core_preloads: hasPreload ? 2 : 0, preload_by_phase: { analysis: hasPreload ? 1 : 0, verification: hasPreload ? 1 : 0 } })
    observations.full_reference_worker = full
    const fullResponse = await page.request.get(`${origin}/v1/jobs/${full.job.job_id}/result`, { headers: liveHeaders })
    expect(fullResponse.status()).toBe(200)
    originals['full-result.json'] = await fullResponse.body()
    expect(digest(originals['full-result.json'])).toBe(full.job.result.content_hash)
    const reference = JSON.parse(originals['full-result.json'].toString())
    expect(Buffer.from(result.terminal_checkpoint_artifact_base64, 'base64')).toEqual(Buffer.from(reference.terminal_checkpoint_artifact_base64, 'base64'))
    for (const key of ['preload_response', 'response_history', 'terminal_response', 'checkpoint', 'model', 'claims']) expect(result.api_result[key]).toEqual(reference.api_result[key])
    expect(result.api_result.request).not.toEqual(reference.api_result.request)
    await page.goto(`${origin}/#/workbench-v2`)
    await waitForJobService(page)
    const panel = page.locator('[data-rc-review="verified"]')
    await expect(panel).toBeVisible()
    await expect(panel.locator('[data-rc-pin-roller-profile]')).toContainText('pin N2 (UX/UY), roller N6 (UY)')
    await expect(panel.locator('[data-rc-authority]')).toContainText('does not rerun the solver')
    await expect(panel.locator('[data-rc-authority]')).toContainText('retained worker attestation')
    await expect(panel.locator('[data-rc-source]')).toHaveText(input.source_revision)
    await expect(panel.locator('[data-rc-reserved]')).toHaveText('4')
    await expect(panel.locator('[data-rc-unknown]')).toContainText('No reservation gap or unknown work')
    const selector = panel.getByRole('combobox', { name: 'RC target to inspect', exact: true })
    await expect(selector.locator('option')).toHaveCount(hasPreload ? 3 : 2)
    if (hasPreload) {
      expect(result.api_result.preload_response.epoch).toBe(1)
      expect(result.api_result.response_history.map((row: any) => row.epoch)).toEqual([2, 3])
      expect(result.api_result.request.constant_nodal_loads).toEqual(input.config.constant_nodal_loads)
      await expect(panel.locator('[data-rc-preload-note]')).toContainText('included in the stored material history and core-call totals')
      await expect(panel.locator('[data-rc-table="constant-loads"]')).toContainText('N4')
    }
    for (const index of hasPreload ? [0, 1, 2] : [0, 1]) {
      await selector.selectOption(String(index))
      await expect(panel.locator('[data-rc-table="reactions"] tbody tr')).toHaveCount(3)
    }
    await expect(panel.locator('[data-rc-material-count]')).toContainText(`${hasPreload ? 3 : 2} stored material steps`)
    for (const role of ['checkpoint', 'result']) {
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: role === 'checkpoint' ? 'Download RC saved job checkpoint' : 'Download RC result', exact: true }).click()
      expect(await readFile((await (await pending).path())!)).toEqual(originals[`${role}.json`])
    }
    observations.split_reserved_invocations = 4
    observations.full_reference_reserved_invocations = 2
    observations.split_core_targets = first.actual_calls.core_targets + second.actual_calls.core_targets
    observations.full_reference_core_targets = full.actual_calls.core_targets
    observations.split_core_preloads = first.actual_calls.core_preloads + second.actual_calls.core_preloads
    observations.full_reference_core_preloads = full.actual_calls.core_preloads
    observations.split_total_native_calls = observations.split_core_targets + observations.split_core_preloads
    observations.full_reference_total_native_calls = full.actual_calls.core_targets + full.actual_calls.core_preloads
    observations.completed = true
  } finally {
    const cleanupErrors: string[] = []
    for (const record of processes) {
      try { await closeLiveServer(record) } catch (error) { cleanupErrors.push(String(error)) }
    }
    observations.processes = processes.map((record, index) => {
      originals[`process-${index}-stdout.txt`] = Buffer.from(record.output)
      originals[`process-${index}-stderr.txt`] = Buffer.from(record.error)
      return { role: record.role, pid: record.child.pid ?? null, reaped: record.ended, exit_code: record.child.exitCode, signal: record.child.signalCode }
    })
    observations.cleanup_errors = cleanupErrors
    const removeCompletedStore = observations.completed === true && cleanupErrors.length === 0 && processes.every(record => record.ended)
    observations.retained_store = removeCompletedStore ? null : store
    const files = Object.fromEntries(Object.entries(originals).map(([path, body]) => [path, { bytes: body.length, sha256: digest(body), base64: body.toString('base64') }]))
    const packetPath = testInfo.outputPath('actual-pin-roller-http-originals.json.gz')
    const proofPath = testInfo.outputPath('actual-pin-roller-http-proof.json')
    await writeFile(packetPath, gzipSync(Buffer.from(JSON.stringify({ schema_version: 'actual-rc-http-originals.v1', observations, files }))))
    await writeFile(proofPath, JSON.stringify(observations))
    await testInfo.attach('actual-pin-roller-http-originals', { path: packetPath, contentType: 'application/gzip' })
    await testInfo.attach('actual-pin-roller-http-proof', { path: proofPath, contentType: 'application/json' })
    if (removeCompletedStore) await rm(store, { recursive: true, force: true })
    if (cleanupErrors.length) throw new Error(cleanupErrors.join('\n'))
  }
})
}
