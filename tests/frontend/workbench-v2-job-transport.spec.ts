import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { createJobReadTransport, createJobWorkflowTransport, readBoundedJobBytes, SUBMIT_MAX_BYTES } from '../../src/workbench-v2/model/jobTransport'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
import { createRcQuantityReport, listRcQuantityReports, loadRcJobRequest, loadRcQuantityReportBytes, refreshRcJob, resumeRcJob, submitRcJob } from '../../src/workbench-v2/model/rcWorkflowProvider'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import type { RcQuantityReportReference } from '../../src/workbench-v2/model/rcQuantityReportSchema'
import { waitForJobService } from './jobServiceBrowserWait'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const directory = 'tests/frontend/fixtures/frame3d-durable-job/'
const originals = Object.fromEntries(['job', 'result', 'evidence'].map((role) => [role, readFileSync(`${directory}${role}.json`)]))
const job = JSON.parse(originals.job.toString())
const statusPath = `/api/v1/jobs/${job.job_id}`
const credentials = { tenantId: 'transport-test', bearerToken: 'synthetic-memory-only-token' }

test('job transport cancels a pending sibling when an artifact exceeds its budget', async () => {
  const originalFetch = globalThis.fetch
  let siblingCancelled = false
  let resultRequested = false
  const oversized = structuredClone(job)
  oversized.result.byte_length = 64 * 1024 * 1024 + 1
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith('/evidence')) {
      return new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => {
          siblingCancelled = true
          reject(new DOMException('aborted', 'AbortError'))
        }, { once: true })
      })
    }
    if (String(input).endsWith('/result')) resultRequested = true
    return new Response(JSON.stringify(oversized), { headers: { 'content-type': 'application/json' } })
  }
  try {
    const result = await loadWorkbenchJob(`https://workbench.test${statusPath}`)
    expect(result).toMatchObject({ status: 'invalid', errors: ['result_too_large'] })
    expect(result.frame3dArtifacts).toBeUndefined()
    expect(siblingCancelled).toBe(true)
    expect(resultRequested).toBe(false)
  } finally { globalThis.fetch = originalFetch }
})

test.describe('bounded job stream', () => {
  function stream(chunks: number[], headers: Record<string, string> = {}) {
    let reads = 0
    let cancelled = false
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (reads === chunks.length) { controller.close(); return }
        controller.enqueue(new Uint8Array(chunks[reads++]).fill(65))
      },
      cancel() { cancelled = true },
    }, { highWaterMark: 0 })
    return {
      response: new Response(body, { headers: { 'content-type': 'application/json', ...headers } }),
      state: () => ({ reads, cancelled, locked: body.locked }),
    }
  }

  for (const expected of [undefined, 7]) {
    test(`retains exact multi-chunk bytes with ${expected === undefined ? 'unknown' : 'referenced'} length`, async () => {
      const source = stream([2, 3, 2])
      expect(await readBoundedJobBytes(source.response, 7, 'result', expected)).toEqual(new Uint8Array(7).fill(65))
      expect(source.state()).toEqual({ reads: 3, cancelled: false, locked: false })
    })
  }
  for (const header of [undefined, '1']) {
    test(`cancels actual overflow with ${header === undefined ? 'absent' : 'dishonest'} Content-Length`, async () => {
      const source = stream([4, 4, 4, 4], header ? { 'content-length': header } : {})
      await expect(readBoundedJobBytes(source.response, 7, 'result')).rejects.toThrow('result_too_large')
      expect(source.state()).toEqual({ reads: 2, cancelled: true, locked: false })
    })
  }
  for (const [name, headers, error] of [
    ['oversize', { 'content-length': '8' }, 'result_too_large'],
    ['non-JSON', { 'content-type': 'text/html' }, 'result_content_type_invalid'],
    ['malformed length', { 'content-length': '1e2' }, 'result_content_length_invalid'],
    ['negative length', { 'content-length': '-1' }, 'result_content_length_invalid'],
    ['mismatched length', { 'content-length': '6' }, 'result byte length mismatch'],
  ] as const) {
    test(`rejects ${name} before reading the body`, async () => {
      const source = stream([7, 7], headers)
      await expect(readBoundedJobBytes(source.response, 7, 'result', 7)).rejects.toThrow(error)
      expect(source.state()).toEqual({ reads: 0, cancelled: true, locked: false })
    })
  }
  test('stops at an overlong referenced body without draining subsequent chunks', async () => {
    const source = stream([3, 3, 3, 3])
    await expect(readBoundedJobBytes(source.response, 20, 'result', 5)).rejects.toThrow('result byte length mismatch')
    expect(source.state()).toEqual({ reads: 2, cancelled: true, locked: false })
  })
  test('rejects a truncated referenced body', async () => {
    const source = stream([2, 2])
    await expect(readBoundedJobBytes(source.response, 7, 'result', 7)).rejects.toThrow('result byte length mismatch')
    expect(source.state().locked).toBe(false)
  })
  test('bounds decoded bytes when the Content-Length describes compression', async () => {
    const source = stream([4, 3], { 'content-encoding': 'gzip', 'content-length': '3' })
    expect((await readBoundedJobBytes(source.response, 7, 'result', 7)).byteLength).toBe(7)
    const overflow = stream([4, 4, 4], { 'content-encoding': 'gzip', 'content-length': '3' })
    await expect(readBoundedJobBytes(overflow.response, 7, 'result', 7)).rejects.toThrow('result_too_large')
    expect(overflow.state()).toEqual({ reads: 2, cancelled: true, locked: false })
  })
  test('propagates a stream abort and releases its reader', async () => {
    const body = new ReadableStream<Uint8Array>({ pull(controller) { controller.error(new DOMException('aborted', 'AbortError')) } })
    await expect(readBoundedJobBytes(new Response(body, { headers: { 'content-type': 'application/json' } }), 7, 'result'))
      .rejects.toMatchObject({ name: 'AbortError' })
    expect(body.locked).toBe(false)
  })
})

test.describe('job credential destination', () => {
  const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location')
  test.beforeEach(() => Object.defineProperty(globalThis, 'location', { configurable: true, value: { origin: 'https://workbench.test' } }))
  test.afterEach(() => {
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation)
    else Reflect.deleteProperty(globalThis, 'location')
  })
  for (const suffix of ['https://other.test/v1/jobs/job', 'https://user:password@workbench.test/v1/jobs/job', '/v1/jobs/job?token=secret', '/v1/jobs/job#secret']) {
    test(`rejects destination before calling host: ${suffix}`, async () => {
      let called = false
      await expect(createJobReadTransport(suffix, undefined, () => { called = true; return credentials })).rejects.toThrow('job_endpoint_invalid')
      expect(called).toBe(false)
    })
  }
  test('does not issue a request when aborted while waiting for host credentials', async () => {
    const controller = new AbortController()
    await expect(createJobReadTransport('/v1/jobs/job', controller.signal, async () => {
      controller.abort()
      return credentials
    })).rejects.toMatchObject({ name: 'AbortError' })
  })
  test('redacts host exceptions and malformed credentials', async () => {
    await expect(createJobReadTransport('/v1/jobs/job', undefined, () => { throw new Error(credentials.bearerToken) }))
      .rejects.toThrow(/^job_authorization_unavailable$/)
    await expect(createJobReadTransport('/v1/jobs/job', undefined, () => ({ ...credentials, tenantId: 'bad\r\nheader' })))
      .rejects.toThrow(/^job_authorization_invalid$/)
  })
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`authenticated job browser ${viewport.width}`, () => {
    test.use({ viewport })
    test('uses tenant and bearer headers for status and exact artifacts without persisting credentials', async ({ page }) => {
      const observed: string[] = []
      await page.addInitScript(({ path, credentials }) => {
        window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: async () => credentials }
      }, { path: statusPath, credentials })
      await page.route('**/api/v1/jobs/**', async (route) => {
        const request = route.request()
        expect(await request.headerValue('x-structural-tenant')).toBe(credentials.tenantId)
        expect(await request.headerValue('authorization')).toBe(`Bearer ${credentials.bearerToken}`)
        const path = new URL(request.url()).pathname
        const role = path === statusPath ? 'job' : path.slice(statusPath.length + 1)
        observed.push(role)
        await route.fulfill({ contentType: 'application/json', body: originals[role] })
      })
      await page.goto(`${baseUrl}/#/workbench-v2`)
      await waitForJobService(page)
      await expect(page.locator('[data-frame3d-job-review="verified"]')).toBeVisible()
      expect(new Set(observed)).toEqual(new Set(['job', 'result', 'evidence']))
      const exposure = await page.evaluate(() => ({ dom: document.body.innerText, local: { ...localStorage }, session: { ...sessionStorage } }))
      expect(JSON.stringify(exposure)).not.toContain(credentials.bearerToken)
      expect(JSON.stringify(exposure)).not.toContain(credentials.tenantId)
    })
  })
}

test('authenticated job browser redacts a failing credential callback and makes no API request', async ({ page }) => {
  let requests = 0
  await page.route('**/api/v1/jobs/**', async (route) => { requests += 1; await route.abort() })
  await page.addInitScript(({ path, token }) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => { throw new Error(token) } }
  }, { path: statusPath, token: credentials.bearerToken })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForJobService(page, 'invalid')
  await expect(page.locator('[data-job-service]')).toContainText('job_authorization_unavailable')
  await expect(page.locator('body')).not.toContainText(credentials.bearerToken)
  await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
  expect(requests).toBe(0)
})

test('authenticated job browser refuses a redirect without forwarding tenant credentials', async ({ page }) => {
  let redirected = 0
  await page.addInitScript(({ path, credentials }) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: path, jobAuthorization: () => credentials }
  }, { path: statusPath, credentials })
  await page.route('**/api/v1/jobs/**', (route) => route.fulfill({ status: 302, headers: { location: 'https://redirect-target.invalid/capture' } }))
  await page.route('https://redirect-target.invalid/**', async (route) => { redirected += 1; await route.abort() })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await waitForJobService(page, 'error')
  expect(redirected).toBe(0)
  await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
})

test.describe('RC workflow transport session', () => {
  let originalFetch: typeof fetch
  let originalLocation: PropertyDescriptor | undefined
  const collection = 'https://workbench.test/api/v1/jobs'
  const id = `job_${'a'.repeat(32)}`
  const hash = `sha256:${'b'.repeat(64)}`
  const encode = (value: string) => new TextEncoder().encode(value)
  const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
  const json = (value: unknown, headers: Record<string, string> = {}) => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json', ...headers } })
  function view(status: WorkbenchJobView['status'] = 'succeeded'): WorkbenchJobView {
    const ref = (role: 'request' | 'result' | 'evidence') => ({ role, content_hash: hash, byte_length: 2, media_type: role === 'result' ? 'application/vnd.structural-analysis.rc-fiber-job-result+json' : 'application/json' })
    return {
      schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
      job_id: id, status, revision: 1, attempt: 1, progress: { completed_steps: status === 'succeeded' ? 1 : 0, total_steps: 1 },
      created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z',
      lease_expires_at: status === 'running' ? '2026-10-03T00:01:00Z' : null, error_code: status === 'failed' ? 'synthetic' : null,
      can_resume: false, request: ref('request'), checkpoint: null, result: status === 'succeeded' ? ref('result') : null,
      evidence: status === 'succeeded' ? ref('evidence') : null, resume_contract_hash: null,
      solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
      claim_boundary: 'synthetic transport metadata only', terminal_event_hash: hash,
    }
  }
  function reference(bytes: Uint8Array): RcQuantityReportReference {
    const contentHash = digest(bytes)
    return { schema_version: 'durable-rc-fiber-quantity-report-reference.v1', tenant_id: credentials.tenantId, job_id: id,
      report_id: `rcq_${contentHash.slice(7)}`, revision: 1, content_hash: contentHash, byte_length: bytes.byteLength,
      media_type: 'application/json', created_at: '2026-10-03T00:00:00Z' }
  }
  test.beforeEach(() => {
    originalFetch = globalThis.fetch
    originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location')
    Object.defineProperty(globalThis, 'location', { value: { origin: 'https://workbench.test' }, configurable: true })
  })
  test.afterEach(() => {
    globalThis.fetch = originalFetch
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation)
    else Reflect.deleteProperty(globalThis, 'location')
  })

  for (const [name, destination] of [['other origin', 'https://other.test/v1/jobs'], ['query', `${collection}?token=private`], ['worker path', 'https://workbench.test/api/v1/jobs/../worker'], ['userinfo', 'https://user:private@workbench.test/v1/jobs']]) {
    test(`validates collection destination before authorization: ${name}`, async () => {
      let calls = 0
      await expect(createJobWorkflowTransport(destination, undefined, () => { calls++; return credentials })).rejects.toThrow(/job_(?:collection_)?endpoint_invalid/)
      expect(calls).toBe(0)
    })
  }

  test('uncertain submit retries retain exact original tokens and idempotency key', async () => {
    const requests: { bytes: string; key: string | null; init: RequestInit }[] = []
    globalThis.fetch = async (_url, init) => {
      requests.push({ bytes: new TextDecoder().decode(init!.body as ArrayBuffer), key: new Headers(init!.headers).get('Idempotency-Key'), init: init! })
      return json(view('queued'))
    }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    const bytes = encode(' {"input":1.0,"negative_zero":-0.0} ')
    await submitRcJob(transport, bytes, 'stable.synthetic:1')
    await submitRcJob(transport, bytes, 'stable.synthetic:1')
    expect(requests.map(row => [row.bytes, row.key])).toEqual([[new TextDecoder().decode(bytes), 'stable.synthetic:1'], [new TextDecoder().decode(bytes), 'stable.synthetic:1']])
    expect(requests.every(row => row.init.redirect === 'error' && row.init.credentials === 'include' && row.init.cache === 'no-store')).toBe(true)
    expect(transport.tenantId).toBe(credentials.tenantId)
    expect(Object.keys(transport)).not.toContain('bearerToken')
  })

  test('all read roles retain one tenant while rotating tokens privately', async () => {
    let calls = 0
    const observed: Headers[] = []
    globalThis.fetch = async (_url, init) => { observed.push(new Headers(init?.headers)); return json(view('queued')) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => ({ ...credentials, bearerToken: `rotating-${++calls}` }))
    await refreshRcJob(transport, id)
    await transport.readTransport(id).get('evidence')
    expect(observed.map(headers => headers.get('X-Structural-Tenant'))).toEqual([credentials.tenantId, credentials.tenantId])
    expect(observed.map(headers => headers.get('Authorization'))).toEqual(['Bearer rotating-2', 'Bearer rotating-4'])
  })

  test('a tenant change in the same callback latches scope failure before any fetch', async () => {
    let tenant = credentials.tenantId
    let fetches = 0
    globalThis.fetch = async () => { fetches++; return json(view()) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => ({ ...credentials, tenantId: tenant }))
    tenant = 'different-tenant'
    await expect(refreshRcJob(transport, id)).rejects.toThrow('job_authorization_scope_changed')
    tenant = credentials.tenantId
    await expect(transport.readTransport(id).get('result')).rejects.toThrow('job_authorization_scope_changed')
    expect(fetches).toBe(0)
  })

  test('mutating the host credential object cannot change the captured session tenant', async () => {
    const mutable = { ...credentials }
    let fetches = 0
    globalThis.fetch = async () => { fetches++; return json(view()) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => mutable)
    mutable.tenantId = 'changed-in-place'
    await expect(transport.verifyAuthorizationScope()).rejects.toThrow('job_authorization_scope_changed')
    expect(transport.tenantId).toBe(credentials.tenantId)
    expect(fetches).toBe(0)
  })

  test('aborted pending host reauthorization cannot issue a stale request', async () => {
    const controller = new AbortController()
    let calls = 0
    let release!: (value: typeof credentials) => void
    let fetches = 0
    globalThis.fetch = async () => { fetches++; return json(view()) }
    const transport = await createJobWorkflowTransport(collection, controller.signal, () => ++calls === 1 ? credentials : new Promise(resolve => { release = resolve }))
    const pending = refreshRcJob(transport, id)
    controller.abort()
    release(credentials)
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetches).toBe(0)
  })

  test('child load abort releases forwarding listeners without aborting its parent session', async () => {
    const parent = new AbortController(), child = new AbortController()
    const parentListeners = new Set<EventListenerOrEventListenerObject>()
    const childListeners = new Set<EventListenerOrEventListenerObject>()
    for (const [signal, listeners] of [[parent.signal, parentListeners], [child.signal, childListeners]] as const) {
      const add = signal.addEventListener.bind(signal), remove = signal.removeEventListener.bind(signal)
      signal.addEventListener = (type, listener, options) => {
        if (type === 'abort' && listener) listeners.add(listener)
        add(type, listener, options)
      }
      signal.removeEventListener = (type, listener, options) => {
        if (type === 'abort' && listener) listeners.delete(listener)
        remove(type, listener, options)
      }
    }
    globalThis.fetch = async (_url, init) => {
      expect(init?.signal?.aborted).toBe(false)
      return json(view('queued'))
    }
    const transport = await createJobWorkflowTransport(collection, parent.signal, () => credentials)
    const read = transport.readTransport(id).withSignal!(child.signal)
    await read.get()
    expect(parentListeners.size).toBeGreaterThan(0)
    expect(childListeners.size).toBeGreaterThan(0)
    child.abort()
    expect(parent.signal.aborted).toBe(false)
    expect(parentListeners.size).toBe(0)
    expect(childListeners.size).toBe(0)
    await expect(read.get()).rejects.toMatchObject({ name: 'AbortError' })
    await expect(transport.getJob(id)).resolves.toBeInstanceOf(Response)
  })

  test('rejects oversize submit, path injection and invalid pagination before reauthorization', async () => {
    let calls = 0, fetches = 0
    globalThis.fetch = async () => { fetches++; return json(view()) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => { calls++; return credentials })
    expect(() => transport.submit(new Uint8Array(SUBMIT_MAX_BYTES + 1), 'stable')).toThrow('job_submit_too_large')
    expect(() => transport.getJob(`${id}/result`)).toThrow('job_id_invalid')
    expect(() => transport.getQuantityReport(id, '../result')).toThrow('rc_report_id_invalid')
    expect(() => transport.listQuantityReports(id, { afterRevision: -1 })).toThrow('rc_report_page_invalid')
    expect(() => transport.listQuantityReports(id, { limit: 101 })).toThrow('rc_report_page_invalid')
    expect(calls).toBe(1)
    expect(fetches).toBe(0)
  })

  test('failed-job explicit resume sends exact hashes including a null checkpoint', async () => {
    let body: unknown
    globalThis.fetch = async (url, init) => { expect(String(url)).toBe(`${collection}/${id}/resume`); body = JSON.parse(init!.body as string); return json(view('queued')) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    await resumeRcJob(transport, view('failed'))
    expect(body).toEqual({ expected_request_hash: hash, expected_checkpoint_hash: null })
    await expect(resumeRcJob(transport, view('checkpointed'))).rejects.toThrow('job_resume_state_invalid')
  })

  test('lightweight refresh rejects a different returned job identity', async () => {
    globalThis.fetch = async () => json({ ...view('queued'), job_id: `job_${'c'.repeat(32)}` })
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    await expect(refreshRcJob(transport, id)).rejects.toThrow('job_view_identity_mismatch')
  })

  test('stored request is read once and bound to exact raw bytes before adoption', async () => {
    const bytes = encode('{"synthetic":1.0}')
    const source = view('queued'); source.request = { ...source.request, byte_length: bytes.byteLength, content_hash: digest(bytes) }
    const paths: string[] = []
    globalThis.fetch = async url => { paths.push(String(url)); return new Response(bytes, { headers: { 'content-type': 'application/json' } }) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    expect(await loadRcJobRequest(transport, source)).toEqual({ bytes, value: { synthetic: 1 } })
    await expect(loadRcJobRequest(transport, { ...source, request: { ...source.request, content_hash: hash } })).rejects.toThrow('request_hash_mismatch')
    expect(paths).toEqual([`${collection}/${id}/request`, `${collection}/${id}/request`])
  })

  test('report creation preserves explicit unpriced null and zero declarations without numerical reads', async () => {
    const raw = encode('{}'), ref = reference(raw)
    const bodies: unknown[] = [], paths: string[] = []
    globalThis.fetch = async (url, init) => { paths.push(String(url)); bodies.push(JSON.parse(init!.body as string)); return json(ref) }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    await createRcQuantityReport(transport, view(), null)
    const prices = { concrete_per_m3: 0, rebar_per_kg: 0, currency: 'KRW', as_of: '2026-10-03', source: 'synthetic only' }
    await createRcQuantityReport(transport, view(), prices)
    expect(bodies).toEqual([null, prices].map(declared_prices => ({ expected_request_hash: hash, expected_result_artifact_hash: hash, declared_prices })))
    expect(paths).toEqual([`${collection}/${id}/rc-quantity-reports`, `${collection}/${id}/rc-quantity-reports`])
  })

  test('report pagination uses bounded headers and checks immutable index identities/cursor', async () => {
    const ref = { ...reference(encode('{}')), revision: 3 }
    let mismatch = false
    globalThis.fetch = async (_url, init) => {
      const headers = new Headers(init?.headers)
      expect(headers.get('X-Structural-Report-After-Revision')).toBe('2')
      expect(headers.get('X-Structural-Report-Limit')).toBe('1')
      return json({ schema_version: 'durable-rc-fiber-quantity-report-index.v1', tenant_id: mismatch ? 'other' : credentials.tenantId, job_id: id, reports: [ref], next_after_revision: 3 })
    }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    expect((await listRcQuantityReports(transport, view(), { afterRevision: 2, limit: 1 })).reports).toEqual([ref])
    mismatch = true
    await expect(listRcQuantityReports(transport, view(), { afterRevision: 2, limit: 1 })).rejects.toThrow('rc_report_index_invalid')
  })

  test('exact report GET checks header, length and raw SHA while leaving semantic review to the worker', async () => {
    const raw = encode('{"transport_only":true}'), ref = reference(raw)
    let corrupted = false
    globalThis.fetch = async url => {
      expect(String(url)).toBe(`${collection}/${id}/rc-quantity-reports/${ref.report_id}`)
      return new Response(corrupted ? encode('{"transport_only":null}') : raw, { headers: { 'content-type': 'application/json', 'x-structural-report-sha256': ref.content_hash } })
    }
    const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
    expect(await loadRcQuantityReportBytes(transport, view(), ref)).toEqual({ reference: ref, bytes: raw })
    corrupted = true
    await expect(loadRcQuantityReportBytes(transport, view(), ref)).rejects.toThrow('rc_report_hash_mismatch')
  })

  for (const fault of ['missing-header', 'wrong-header', 'wrong-tenant', 'wrong-job', 'oversize-ref'] as const) {
    test(`rejects report ${fault} before reading payload`, async () => {
      const raw = encode('{}'), ref = reference(raw)
      if (fault === 'wrong-tenant') ref.tenant_id = 'other'
      if (fault === 'wrong-job') ref.job_id = `job_${'c'.repeat(32)}`
      if (fault === 'oversize-ref') ref.byte_length = 4 * 1024 * 1024 + 1
      let reads = 0, fetches = 0
      globalThis.fetch = async () => {
        fetches++
        const body = new ReadableStream<Uint8Array>({ pull(controller) { reads++; controller.enqueue(raw); controller.close() } }, { highWaterMark: 0 })
        return new Response(body, { headers: { 'content-type': 'application/json', ...(fault === 'missing-header' ? {} : { 'x-structural-report-sha256': fault === 'wrong-header' ? hash : ref.content_hash }) } })
      }
      const transport = await createJobWorkflowTransport(collection, undefined, () => credentials)
      await expect(loadRcQuantityReportBytes(transport, view(), ref)).rejects.toThrow(fault.endsWith('header') ? 'rc_report_hash_header_mismatch' : 'rc_report_reference_invalid')
      expect(reads).toBe(0)
      expect(fetches).toBe(fault.endsWith('header') ? 1 : 0)
    })
  }

  test('server error bodies and host exceptions never become raw diagnostics', async () => {
    let calls = 0
    globalThis.fetch = async () => new Response(`secret=${credentials.bearerToken}`, { status: 409 })
    const transport = await createJobWorkflowTransport(collection, undefined, () => { calls++; if (calls > 3) throw new Error(credentials.bearerToken); return credentials })
    await expect(refreshRcJob(transport, id)).rejects.toThrow('job_api_http_409')
    await expect(refreshRcJob(transport, id)).rejects.toThrow('job_authorization_unavailable')
  })
})
