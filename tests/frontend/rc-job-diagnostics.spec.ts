import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { loadRcInvocationDetail, loadRcJobDiagnostics, parseRcJobDiagnostics, rcRequestChanges, type RcInvocationObservation } from '../../src/workbench-v2/model/rcJobDiagnostics'
import { createJobReadTransport, createJobWorkflowTransport, type RcJobTransport } from '../../src/workbench-v2/model/jobTransport'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const requestHash = `sha256:${'1'.repeat(64)}`
const chunkHash = `sha256:${'2'.repeat(64)}`
const artifactHash = `sha256:${'3'.repeat(64)}`
const jobId = `job_${'a'.repeat(32)}`
const job = {
  schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
  job_id: jobId, status: 'failed', revision: 2, attempt: 1,
  progress: { completed_steps: 0, total_steps: 3 },
  created_at: '2026-10-23T00:00:00.000000Z', updated_at: '2026-10-23T00:00:01.000000Z',
  lease_expires_at: null, error_code: 'rc_fiber_worker_chunk_blocked', can_resume: true,
  request: { role: 'request', content_hash: requestHash, byte_length: 100, media_type: 'application/json' },
  checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
  solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
  claim_boundary: 'orchestration only', terminal_event_hash: artifactHash,
} as WorkbenchJobView

function observation(ordinal = 1, extra: Partial<RcInvocationObservation> = {}): RcInvocationObservation {
  return { ordinal, content_hash: artifactHash, byte_length: 100,
    schema_version: 'bounded-rc-fiber-job-invocation.v1', phase: 'analysis', status: 'returned',
    job_request_hash: requestHash, chunk_request_hash: chunkHash,
    completed_before: 0, completed_after: 1, restart_input_sha256: null,
    timing: { wall_ns: 2_000_000_000, process_cpu_ns: 1_000_000_000 }, unavailable_execution_work: false, ...extra }
}

function index(invocations: RcInvocationObservation[] = [], pending: number[] = []) {
  const reserved = invocations.length + pending.length
  return { schema_version: 'bounded-rc-fiber-job-invocation-evidence.v1', job_id: jobId,
    job_request_hash: requestHash, execution_budget_unit: 'reserved_api_invocations',
    execution_budget: { maximum_attempts: 12, reserved_attempts: reserved, remaining_attempts: 12 - reserved },
    pending_ordinals: pending, pending_execution_work: pending.length ? 'unknown' : 'none_pending', invocations }
}

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
}

function transport(response: () => Response, verify = async () => {}): RcJobTransport {
  return { getRcInvocations: async () => response(), verifyAuthorizationScope: verify } as unknown as RcJobTransport
}

test('absent phases and unobserved reservations stay unavailable rather than zero', () => {
  const empty = parseRcJobDiagnostics(index(), job)
  expect(empty).toMatchObject({ analysisWallSeconds: null, verificationWallSeconds: null, processCpuSeconds: null, unknownWork: false })
  const pending = parseRcJobDiagnostics(index([], [1, 2]), job)
  expect(pending).toMatchObject({ pending: [1, 2], analysisWallSeconds: null, verificationWallSeconds: null, processCpuSeconds: null, unknownWork: true })
})

test('phase timings retain observed raised work without inventing pending timing or committed progress', () => {
  const analysis = observation(1, { status: 'raised', unavailable_execution_work: true, completed_after: 3 })
  const verification = observation(2, { phase: 'verification', timing: { wall_ns: 3_000_000_000, process_cpu_ns: 500_000_000 } })
  const value = parseRcJobDiagnostics(index([verification, analysis], [3]), job)
  expect(value).toMatchObject({ analysisWallSeconds: 2, verificationWallSeconds: 3, processCpuSeconds: 1.5, unknownWork: true, pending: [3] })
  expect(value.invocations.map(row => row.ordinal)).toEqual([1, 2])
  expect(job.progress.completed_steps).toBe(0)
})

test('an overflowing observed subtotal is unavailable while a safe other phase remains usable', () => {
  const large = { wall_ns: Number.MAX_SAFE_INTEGER, process_cpu_ns: Number.MAX_SAFE_INTEGER }
  const rows = [observation(1, { timing: large }), observation(2, { timing: large }),
    observation(3, { phase: 'verification', timing: { wall_ns: 1_000_000_000, process_cpu_ns: 1 } })]
  expect(parseRcJobDiagnostics(index(rows), job)).toMatchObject({ analysisWallSeconds: null, verificationWallSeconds: 1, processCpuSeconds: null })
})

const corotationalJob: WorkbenchJobView = { ...job, schema_version: 'structural-analysis-job-view.v2',
  progress: { ...job.progress, unit: 'control_solver_attempts' } }
const corotationalSchemaV1 = 'bounded-rc-corotational-job-invocation.v1'
const corotationalSchemaV2 = 'bounded-rc-corotational-job-invocation.v2'

test('corotational v1 metadata retains directly observed phase timings', () => {
  const rows = [observation(1, { schema_version: corotationalSchemaV1 }),
    observation(2, { schema_version: corotationalSchemaV1, phase: 'verification', timing: { wall_ns: 3_000_000_000, process_cpu_ns: 500_000_000 } })]
  expect(parseRcJobDiagnostics(index(rows), corotationalJob)).toMatchObject({ analysisWallSeconds: 2, verificationWallSeconds: 3, processCpuSeconds: 1.5, unknownWork: false })
})

test('corotational v2 interrupted child keeps measured wall span and propagates unavailable CPU through the total', () => {
  const rows = [observation(1, { schema_version: corotationalSchemaV2, status: 'raised', unavailable_execution_work: true,
    timing: { wall_ns: 2_500_000_000, process_cpu_ns: null } }),
  observation(2, { schema_version: corotationalSchemaV2, phase: 'verification', timing: { wall_ns: 1_000_000_000, process_cpu_ns: 300_000_000 } })]
  const value = parseRcJobDiagnostics(index(rows), corotationalJob)
  expect(value).toMatchObject({ analysisWallSeconds: 2.5, verificationWallSeconds: 1, processCpuSeconds: null, unknownWork: true })
  expect(value.invocations[0].timing.process_cpu_ns).toBeNull()
  expect(value.invocations[1].timing.process_cpu_ns).toBe(300_000_000)
})

test('corotational v2 returned metadata preserves directly observed CPU even with unknown internal solver work', () => {
  const row = observation(1, { schema_version: corotationalSchemaV2, unavailable_execution_work: true,
    timing: { wall_ns: 3_000_000_000, process_cpu_ns: 700_000_000 } })
  expect(parseRcJobDiagnostics(index([row]), corotationalJob)).toMatchObject({ analysisWallSeconds: 3,
    verificationWallSeconds: null, processCpuSeconds: 0.7, unknownWork: true })
})

test('legacy and corotational diagnostic families cannot be admitted through each other’s job denominator', () => {
  for (const schema_version of [corotationalSchemaV1, corotationalSchemaV2]) {
    expect(() => parseRcJobDiagnostics(index([observation(1, { schema_version })]), job)).toThrow('rc_diagnostics_invalid')
  }
  expect(() => parseRcJobDiagnostics(index([observation()]), corotationalJob)).toThrow('rc_diagnostics_invalid')
})

test('null CPU is rejected unless it is an unknown raised corotational v2 observation', () => {
  for (const schema_version of ['bounded-rc-fiber-job-invocation.v1', corotationalSchemaV1]) {
    const boundJob = schema_version === corotationalSchemaV1 ? corotationalJob : job
    expect(() => parseRcJobDiagnostics(index([observation(1, { schema_version, status: 'raised', unavailable_execution_work: true,
      timing: { wall_ns: 1, process_cpu_ns: null } })]), boundJob)).toThrow('rc_diagnostics_invalid')
  }
  for (const change of [{ status: 'returned' as const, unavailable_execution_work: true },
    { status: 'raised' as const, unavailable_execution_work: false }]) {
    expect(() => parseRcJobDiagnostics(index([observation(1, { schema_version: corotationalSchemaV2, ...change,
      timing: { wall_ns: 1, process_cpu_ns: null } })]), corotationalJob)).toThrow('rc_diagnostics_invalid')
  }
})

test('corotational v2 detail binds a nullable child CPU observation to the exact stored artifact', async () => {
  const metadata = { schema_version: corotationalSchemaV2, status: 'raised' as const, unavailable_execution_work: true,
    timing: { wall_ns: 2_500_000_000, process_cpu_ns: null } }
  const bytes = detailBytes(invocation({ ...metadata, api_result: null, error: { type: 'TimeoutError', code: 'phase_timeout' } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), corotationalJob, detailObservation(bytes, metadata))
  expect(value).toMatchObject({ errorType: 'TimeoutError', errorCode: 'phase_timeout', outcomeStatus: null, attempts: [] })
  const rebound = detailObservation(bytes, { ...metadata, timing: { ...metadata.timing, process_cpu_ns: 0 } })
  await expect(loadRcInvocationDetail(transport(() => byteResponse(bytes)), corotationalJob, rebound)).rejects.toThrow('rc_diagnostics_invalid')
})

for (const [label, mutate] of [
  ['wrong job', (value: any) => { value.job_id = `job_${'b'.repeat(32)}` }],
  ['wrong request', (value: any) => { value.job_request_hash = chunkHash }],
  ['row request mismatch', (value: any) => { value.invocations[0].job_request_hash = chunkHash }],
  ['duplicate row ordinal', (value: any) => { value.invocations[1].ordinal = 1 }],
  ['duplicate pending ordinal', (value: any) => { value.pending_ordinals = [1]; value.invocations.pop() }],
  ['missing reserved outcome', (value: any) => { value.invocations.pop() }],
  ['out of range coverage', (value: any) => { value.invocations[1].ordinal = 3 }],
  ['unsafe integer timing', (value: any) => { value.invocations[0].timing.wall_ns = Number.MAX_SAFE_INTEGER + 1 }],
  ['negative timing', (value: any) => { value.invocations[0].timing.process_cpu_ns = -1 }],
  ['raised known work', (value: any) => { value.invocations[0].status = 'raised' }],
  ['unaccounted pending work', (value: any) => { value.pending_ordinals = [2]; value.invocations.pop(); value.pending_execution_work = 'none_pending' }],
] as const) {
  test(`rejects ${label} in diagnostic metadata`, () => {
    const value = index([observation(1), observation(2)])
    mutate(value)
    expect(() => parseRcJobDiagnostics(value, job)).toThrow('rc_diagnostics_invalid')
  })
}

test('diagnostic index verifies authorization again after the response body is read', async () => {
  let verified = 0
  const api = transport(() => jsonResponse(index([observation()])), async () => { verified++; throw new Error('job_authorization_scope_changed') })
  await expect(loadRcJobDiagnostics(api, job)).rejects.toThrow('job_authorization_scope_changed')
  expect(verified).toBe(1)
})

function invocation(extra: Record<string, unknown> = {}) {
  const row = observation()
  const { ordinal: _ordinal, content_hash: _hash, byte_length: _length, ...metadata } = row
  return { ...metadata, api_result: { status: 'blocked', failure: 'line_search_failed_to_reduce_residual' },
    verification_report: null, checkpoint_artifact_base64: null, error: null, ...extra }
}

function detailBytes(value: unknown) { return new TextEncoder().encode(JSON.stringify(value)) }
function detailObservation(bytes: Uint8Array, extra: Partial<RcInvocationObservation> = {}) {
  return observation(1, { byte_length: bytes.length, content_hash: `sha256:${createHash('sha256').update(bytes).digest('hex')}`, ...extra })
}
function byteResponse(bytes: Uint8Array) {
  return new Response(bytes, { headers: { 'Content-Type': 'application/json' } })
}

test('exact artifact bytes and metadata produce bounded codes without granting numerical authority', async () => {
  const bytes = detailBytes(invocation())
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))
  expect(value).toMatchObject({ errorType: null, outcomeStatus: 'blocked', failure: 'line_search_failed_to_reduce_residual', checks: [] })
  expect(value).not.toHaveProperty('converged')
})

test('verification error codes are bounded and arbitrary error text is not rendered', async () => {
  const bytes = detailBytes(invocation({ phase: 'verification', api_result: null,
    verification_report: { status: 'blocked', errors: ['finite_check_failed', { code: 'target_incomplete' },
      { code: '<script>unsafe</script>' }, ...Array.from({ length: 40 }, () => 'later_check')] } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes, { phase: 'verification' }))
  expect(value.checks.slice(0, 2)).toEqual(['finite_check_failed', 'target_incomplete'])
  expect(value.checks).toHaveLength(31)
  expect(value.checks.join(' ')).not.toContain('<script>')
})

test('a raised invocation retains its observed error type while unsafe arbitrary messages stay absent', async () => {
  const bytes = detailBytes(invocation({ status: 'raised', unavailable_execution_work: true, api_result: null,
    error: { type: 'ValueError', code: 'bad_input', message: 'private path /root/example; <script>unsafe</script>' } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job,
    detailObservation(bytes, { status: 'raised', unavailable_execution_work: true }))
  expect(value).toMatchObject({ errorType: 'ValueError', errorCode: 'bad_input', outcomeStatus: null, failure: null })
  expect(JSON.stringify(value)).not.toContain('private path')
})

test('failed attempted targets expose stored dimensionless convergence without fabricating physical result rows', async () => {
  const attempt = { target_control_displacement_m: 0.003, committed: false,
    step: { trial_solution: { status: 'blocked', convergence_history: [
      { iteration: 0, relative_residual: 0.8, residual_kn: [2, -1, 9] },
      { iteration: 1, relative_residual: 0.4, residual_kn: [1, -0.5, 4] },
    ] } }, failure: null }
  const bytes = detailBytes(invocation({ api_result: { status: 'blocked', path: { attempts: [attempt] } } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))
  expect(value.attempts).toEqual([{ targetM: 0.003, committed: false, status: 'blocked', failureType: null,
    convergence: [{ iteration: 0, relativeResidual: 0.8 }, { iteration: 1, relativeResidual: 0.4 }] }])
  expect(value.traceTruncated).toBe(false)
  expect(JSON.stringify(value.attempts)).not.toContain('residual_kn')
  expect(value).not.toHaveProperty('memberForces')
})

test('invalid-execution failure attempts are available without an accepted step or invented residual history', async () => {
  const bytes = detailBytes(invocation({ api_result: { status: 'invalid_execution', failure: { attempts: [
    { target_control_displacement_m: 0.004, committed: false, step: null, failure: { type: 'ValueError', message: 'raw exception text' } },
  ] } } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))
  expect(value.attempts).toEqual([{ targetM: 0.004, committed: false, status: null, failureType: 'ValueError', convergence: [] }])
  expect(JSON.stringify(value)).not.toContain('raw exception text')
})

test('long traces keep the last failed attempts and mark both attempt and iteration truncation', async () => {
  const attempts = Array.from({ length: 18 }, (_, target) => ({ target_control_displacement_m: target / 1000,
    committed: target < 17, step: { trial_solution: { status: target === 17 ? 'blocked' : 'ready',
      convergence_history: Array.from({ length: 130 }, (_, iteration) => ({ iteration, relative_residual: 1 / (iteration + 1) })) } }, failure: null }))
  const bytes = detailBytes(invocation({ api_result: { status: 'blocked', path: { attempts } } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))
  expect(value.traceTruncated).toBe(true)
  expect(value.attempts).toHaveLength(16)
  expect(value.attempts[0].targetM).toBe(0.002)
  expect(value.attempts[15]).toMatchObject({ targetM: 0.017, committed: false, status: 'blocked' })
  expect(value.attempts[15].convergence).toHaveLength(128)
  expect(value.attempts[15].convergence[0].iteration).toBe(2)
  expect(value.attempts[15].convergence[127].iteration).toBe(129)
})

test('rejects changed bytes even when the JSON stays valid and has the same length', async () => {
  const bytes = detailBytes(invocation())
  const changed = new Uint8Array(bytes)
  const text = new TextDecoder().decode(bytes), position = text.indexOf('blocked')
  changed.set(new TextEncoder().encode('unknown'), position)
  await expect(loadRcInvocationDetail(transport(() => byteResponse(changed)), job, detailObservation(bytes))).rejects.toThrow('rc_diagnostics_invalid')
})

test('a matching byte hash cannot conceal different stored invocation metadata', async () => {
  const bytes = detailBytes(invocation({ phase: 'verification' }))
  await expect(loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))).rejects.toThrow('rc_diagnostics_invalid')
})

test('details declared above 8 MiB are rejected before fetching', async () => {
  let fetches = 0
  const api = transport(() => { fetches++; return jsonResponse({}) })
  await expect(loadRcInvocationDetail(api, job, observation(1, { byte_length: 8 * 1024 * 1024 + 1 }))).rejects.toThrow('rc_diagnostics_detail_too_large')
  expect(fetches).toBe(0)
})

test('standalone detail observations reject malformed references before fetching', async () => {
  let fetches = 0
  const api = transport(() => { fetches++; return jsonResponse({}) })
  for (const change of [{ ordinal: 0 }, { ordinal: 4097 }, { content_hash: 'unbound' }, { byte_length: 0 }, { byte_length: 1.5 }]) {
    await expect(loadRcInvocationDetail(api, job, observation(1, change))).rejects.toThrow('rc_diagnostics_invalid')
  }
  expect(fetches).toBe(0)
})

test('discarded malformed convergence observations explicitly mark the displayed trace incomplete', async () => {
  const bytes = detailBytes(invocation({ api_result: { status: 'blocked', path: { attempts: [null,
    { target_control_displacement_m: 0.003, committed: false, step: { trial_solution: { status: 'blocked', convergence_history: [
      { iteration: 0, relative_residual: 1 }, { iteration: 1, relative_residual: -1 }, { iteration: 1.5, relative_residual: 0.5 },
    ] } } },
  ] } } }))
  const value = await loadRcInvocationDetail(transport(() => byteResponse(bytes)), job, detailObservation(bytes))
  expect(value.traceTruncated).toBe(true)
  expect(value.attempts).toHaveLength(1)
  expect(value.attempts[0].convergence).toEqual([{ iteration: 0, relativeResidual: 1 }])
})

test('detail bytes cannot be exposed after the authorization scope changes', async () => {
  const bytes = detailBytes(invocation())
  const api = transport(() => byteResponse(bytes), async () => { throw new Error('job_authorization_scope_changed') })
  await expect(loadRcInvocationDetail(api, job, detailObservation(bytes))).rejects.toThrow('job_authorization_scope_changed')
})

test('request differences preserve both immutable inputs and separate model and configuration changes', () => {
  const before = { model: { nodes: [{ id: 'tip', x: 2 }], 'a/b~c': 1 }, config: { solver_config: { newton: { max_iterations: 10 } } } }
  const after = { model: { nodes: [{ id: 'tip', x: 3 }], 'a/b~c': 2 }, config: { solver_config: { newton: { max_iterations: 20 } } } }
  const snapshot = [JSON.stringify(before), JSON.stringify(after)]
  expect(rcRequestChanges(before, after)).toEqual({ changes: [
    { path: '/config/solver_config/newton/max_iterations', before: '10', after: '20' },
    { path: '/model/a~1b~0c', before: '1', after: '2' },
    { path: '/model/nodes/0/x', before: '2', after: '3' },
  ], truncated: false })
  expect([JSON.stringify(before), JSON.stringify(after)]).toEqual(snapshot)
})

test('request differences explicitly report truncation and added or removed fields', () => {
  expect(rcRequestChanges({ old: true }, { added: 1 })).toEqual({ changes: [
    { path: '/added', before: '(absent)', after: '1' }, { path: '/old', before: 'true', after: '(absent)' },
  ], truncated: false })
  expect(rcRequestChanges({ a: 1, b: 2 }, { a: 3, b: 4 }, 1)).toEqual({ changes: [{ path: '/a', before: '1', after: '3' }], truncated: true })
})

test('invocation transport uses exact same-origin routes and rejects invalid ordinals before fetch', async () => {
  const original = globalThis.fetch
  const calls: Array<{ url: string; method: string; redirect: string }> = []
  globalThis.fetch = async (input, init) => { calls.push({ url: String(input), method: init?.method ?? '', redirect: init?.redirect ?? '' }); return jsonResponse({}) }
  try {
    const api = await createJobWorkflowTransport('https://workbench.test/v1/jobs')
    await api.getRcInvocations!(jobId)
    await api.getRcInvocations!(jobId, 2)
    expect(calls).toEqual([
      { url: `https://workbench.test/v1/jobs/${jobId}/rc-invocations`, method: 'GET', redirect: 'error' },
      { url: `https://workbench.test/v1/jobs/${jobId}/rc-invocations/2`, method: 'GET', redirect: 'error' },
    ])
    for (const ordinal of [0, -1, 1.5, 10000, Number.MAX_SAFE_INTEGER + 1, NaN]) expect(() => api.getRcInvocations!(jobId, ordinal)).toThrow('rc_invocation_ordinal_invalid')
    expect(calls).toHaveLength(2)
  } finally { globalThis.fetch = original }
})

test('detailed corotational reports use bound read-only routes in every transport', async () => {
  const original = globalThis.fetch
  const calls: Array<{ url: string; method: string; redirect: string; headers: Headers }> = []
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), method: init?.method ?? '', redirect: init?.redirect ?? '', headers: new Headers(init?.headers) })
    return jsonResponse({})
  }
  const binding = { requestHash, resultHash: chunkHash, evidenceHash: artifactHash }
  try {
    const workflow = await createJobWorkflowTransport('https://workbench.test/v1/jobs')
    const read = await createJobReadTransport(`https://workbench.test/v1/jobs/${jobId}`)
    await workflow.getCorotationalDetailReport!(jobId, binding)
    await workflow.readTransport(jobId).getCorotationalDetailReport!(binding)
    await read.getCorotationalDetailReport!(binding)
    expect(calls).toHaveLength(3)
    for (const call of calls) {
      expect(call).toMatchObject({ url: `https://workbench.test/v1/jobs/${jobId}/rc-corotational-detail-report`, method: 'GET', redirect: 'error' })
      expect(call.headers.get('X-Structural-Expected-Request-Hash')).toBe(requestHash)
      expect(call.headers.get('X-Structural-Expected-Result-Hash')).toBe(chunkHash)
      expect(call.headers.get('X-Structural-Expected-Evidence-Hash')).toBe(artifactHash)
    }
    await expect(read.getCorotationalDetailReport!({ ...binding, resultHash: 'invalid' })).rejects.toThrow('rc_corotational_report_binding_invalid')
    expect(() => workflow.getCorotationalDetailReport!('invalid', binding)).toThrow('job_id_invalid')
    expect(calls).toHaveLength(3)
  } finally { globalThis.fetch = original }
})

for (const kind of ['read', 'workflow'] as const) test(`detailed report ${kind} transport discards bytes after an account change`, async () => {
  const originalFetch = globalThis.fetch, originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location')
  Object.defineProperty(globalThis, 'location', { value: { origin: 'https://workbench.test' }, configurable: true })
  let changed = false, calls = 0, cancelled = false
  const authorize = async () => ({ tenantId: changed ? 'other-account' : 'original-account', bearerToken: 'test-token' })
  globalThis.fetch = async () => {
    calls++; changed = true
    return new Response(new ReadableStream({ cancel() { cancelled = true } }), { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const read = kind === 'read'
      ? await createJobReadTransport(`https://workbench.test/v1/jobs/${jobId}`, undefined, authorize)
      : (await createJobWorkflowTransport('https://workbench.test/v1/jobs', undefined, authorize)).readTransport(jobId)
    const binding = { requestHash, resultHash: chunkHash, evidenceHash: artifactHash }
    await expect(read.getCorotationalDetailReport!(binding)).rejects.toThrow('job_authorization_scope_changed')
    expect(cancelled).toBe(true)
    await expect(read.getCorotationalDetailReport!(binding)).rejects.toThrow('job_authorization_scope_changed')
    expect(calls).toBe(1)
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation)
    else Reflect.deleteProperty(globalThis, 'location')
  }
})
