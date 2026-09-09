import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createJobReadTransport, readBoundedJobBytes } from '../../src/workbench-v2/model/jobTransport'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
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
