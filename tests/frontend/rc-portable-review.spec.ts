import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { createRcPortableReviewBlob, parseRcPortableReview, RC_PORTABLE_REVIEW_MAX_BYTES,
  RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES, RC_PORTABLE_REVIEW_REPORT_MAX_BYTES,
  type RcPortableReviewSource } from '../../src/workbench-v2/model/rcPortableReviewSchema'
import { loadRcCorotationalReportReview } from '../../src/workbench-v2/model/rcCorotationalReportReview'
import type { JobReadTransport } from '../../src/workbench-v2/model/jobTransport'

const digest = (bytes: Uint8Array) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))
const retained = process.env.RC_COROTATIONAL_REPORT_FIXTURE_DIR
const blank = { schema_version: 'rc-portable-nodal-review.v1', custody: 'portable_unverified_origin',
  recorded_tenant_id: 'test', job: {}, report_id: `rcc_${'0'.repeat(64)}`,
  request: { encoding: 'base64', byte_length: 1, content_hash: `sha256:${'0'.repeat(64)}`, body_base64: 'AA==' },
  report: { encoding: 'base64', byte_length: 1, content_hash: `sha256:${'0'.repeat(64)}`, body_base64: 'AA==' } }

test('portable envelope admits only exact versioned fields and never credential or service authority', async () => {
  for (const mutate of [
    (value: any) => { value.schema_version = 'rc-portable-nodal-review.v2' },
    (value: any) => { value.custody = 'authenticated' },
    (value: any) => { value.bearerToken = 'credential-must-not-be-admitted' },
    (value: any) => { value.service_url = 'https://example.invalid/jobs' },
    (value: any) => { value.permissions = ['execute'] },
    (value: any) => { delete value.report },
  ]) {
    const value = structuredClone(blank); mutate(value)
    await expect(parseRcPortableReview(encode(value))).rejects.toThrow(/^rc_portable_review_/)
  }
  const duplicate = JSON.stringify(blank).replace('"custody":', '"custody":"portable_unverified_origin","custody":')
  await expect(parseRcPortableReview(new TextEncoder().encode(duplicate))).rejects.toThrow('contract_invalid')
  for (const text of ['[]', 'null', '{}', '{"schema_version":"rc-portable-nodal-review.v1"}', '{']) {
    await expect(parseRcPortableReview(new TextEncoder().encode(text))).rejects.toThrow(/^rc_portable_review_/)
  }
})

test.describe('portable export single-flight lifecycle', () => {
  test.skip(!retained, 'Uses retained bytes and controlled worker scheduling; never generates numerical fixtures.')
  const snapshot = () => JSON.parse(readFileSync(path.join(retained!, 'v7-review-snapshot.json'), 'utf8'))

  test('client refuses duplicate work before authorization, permits retry, and rejects exports after dispose or abort', async () => {
    const originalWorker = Object.getOwnPropertyDescriptor(globalThis, 'Worker')
    const instances: ControlledWorker[] = []
    class ControlledWorker {
      onmessage: ((event: any) => void) | null = null
      onerror: (() => void) | null = null
      onmessageerror: (() => void) | null = null
      messages: any[] = []
      terminated = false
      constructor() { instances.push(this) }
      postMessage(message: any): void {
        this.messages.push(message)
        if (message.type === 'initialize') queueMicrotask(() => this.onmessage?.({ data: { id: message.id, value: {} } }))
      }
      terminate(): void { this.terminated = true }
      reply(value?: Blob, operationError?: string): void {
        const pending = this.messages.filter(message => message.type === 'portableDownload').at(-1)
        this.onmessage?.({ data: { id: pending.id, value, operationError } })
      }
    }
    Object.defineProperty(globalThis, 'Worker', { configurable: true, value: ControlledWorker })
    let authorizationCalls = 0, authorizationGate: Promise<void> | null = null
    let authorizationEntered = () => {}
    const data = snapshot(), request = new Uint8Array(Buffer.from(data.artifacts.request, 'base64'))
    const report = new Uint8Array(Buffer.from(data.report.body_base64, 'base64'))
    const transport = {
      tenantId: data.tenant_id,
      verifyAuthorizationScope: async () => {
        authorizationCalls++
        if (authorizationGate) { authorizationEntered(); await authorizationGate }
      },
      get: async () => new Response(request, { headers: { 'content-type': 'application/json' } }),
      getCorotationalReport: async () => new Response(report, { headers: data.report.headers }),
    } as unknown as JobReadTransport
    try {
      const review = await loadRcCorotationalReportReview(data.job, transport)
      const worker = instances.at(-1)!, before = authorizationCalls
      const first = review.portableDownload!()
      await expect(review.portableDownload!()).rejects.toThrow('portable_export_busy')
      await expect.poll(() => worker.messages.filter(message => message.type === 'portableDownload').length).toBe(1)
      expect(authorizationCalls).toBe(before + 1)
      const rejected = expect(first).rejects.toThrow('portable_export_unavailable')
      worker.reply(undefined, 'rc_corotational_report_portable_export_unavailable')
      await rejected

      const retry = review.portableDownload!()
      await expect.poll(() => worker.messages.filter(message => message.type === 'portableDownload').length).toBe(2)
      worker.reply(new Blob(['portable']))
      expect(await (await retry).text()).toBe('portable')
      expect(authorizationCalls).toBe(before + 3) // failed start + successful before/after

      const pending = review.portableDownload!()
      await expect.poll(() => worker.messages.filter(message => message.type === 'portableDownload').length).toBe(3)
      const disposed = expect(pending).rejects.toThrow('disposed')
      review.dispose()
      await disposed
      const afterDispose = authorizationCalls
      await expect(review.portableDownload!()).rejects.toThrow('disposed')
      expect(authorizationCalls).toBe(afterDispose)
      expect(worker.terminated).toBe(true)

      const controller = new AbortController()
      const abortable = await loadRcCorotationalReportReview(data.job, transport, controller.signal)
      const abortWorker = instances.at(-1)!, abortExport = abortable.portableDownload!()
      await expect.poll(() => abortWorker.messages.filter(message => message.type === 'portableDownload').length).toBe(1)
      const aborted = expect(abortExport).rejects.toThrow('disposed')
      controller.abort()
      await aborted
      const afterAbort = authorizationCalls
      await expect(abortable.portableDownload!()).rejects.toThrow('disposed')
      expect(authorizationCalls).toBe(afterAbort)
      expect(abortWorker.terminated).toBe(true)

      const finalCheckReview = await loadRcCorotationalReportReview(data.job, transport)
      const finalCheckWorker = instances.at(-1)!, completedExport = finalCheckReview.portableDownload!()
      await expect.poll(() => finalCheckWorker.messages.filter(message => message.type === 'portableDownload').length).toBe(1)
      let releaseAuthorization!: () => void
      authorizationGate = new Promise<void>(resolve => { releaseAuthorization = resolve })
      const finalAuthorizationEntered = new Promise<void>(resolve => { authorizationEntered = resolve })
      finalCheckWorker.reply(new Blob(['completed before disposal']))
      await finalAuthorizationEntered
      const disposedDuringFinalCheck = expect(completedExport).rejects.toThrow('disposed')
      finalCheckReview.dispose()
      releaseAuthorization()
      await disposedDuringFinalCheck
      authorizationGate = null
      const afterFinalDispose = authorizationCalls
      await expect(finalCheckReview.portableDownload!()).rejects.toThrow('disposed')
      expect(authorizationCalls).toBe(afterFinalDispose)
      expect(finalCheckWorker.terminated).toBe(true)
    } finally {
      if (originalWorker) Object.defineProperty(globalThis, 'Worker', originalWorker)
      else delete (globalThis as any).Worker
    }
  })

  test('actual worker bounds retained request bytes and rejects overlapping encodes while allowing failure retry', async () => {
    const originalSelf = Object.getOwnPropertyDescriptor(globalThis, 'self')
    const subtle = crypto.subtle, originalDigest = subtle.digest.bind(subtle)
    const digestDescriptor = Object.getOwnPropertyDescriptor(subtle, 'digest')
    const messages: any[] = [], scope: any = { postMessage: (message: any) => { messages.push(message) } }
    Object.defineProperty(globalThis, 'self', { configurable: true, value: scope })
    const restoreDigest = () => {
      if (digestDescriptor) Object.defineProperty(subtle, 'digest', digestDescriptor)
      else delete (subtle as any).digest
    }
    try {
      await import('../../src/workbench-v2/model/rcCorotationalReportReview.worker')
      const dispatch = (id: number, type: string, input: object = {}) => scope.onmessage({ data: { id, type, ...input } })
      const data = snapshot(), requestBytes = new Uint8Array(Buffer.from(data.artifacts.request, 'base64'))
      const reportBytes = new Uint8Array(Buffer.from(data.report.body_base64, 'base64')), contentHash = digest(reportBytes)
      const input = { job: data.job, tenantId: data.tenant_id, requestBytes, bytes: reportBytes,
        reportId: `rcc_${contentHash.slice(7)}`, contentHash, maximumBytes: RC_PORTABLE_REVIEW_REPORT_MAX_BYTES }
      await dispatch(1, 'initialize', { ...input, requestBytes: new Uint8Array(RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES + 1) })
      expect(messages.find(message => message.id === 1).error).toBe('rc_corotational_report_request_size_invalid')
      await dispatch(2, 'initialize', input)
      expect(messages.find(message => message.id === 2).value.jobId).toBe(data.job.job_id)

      let release!: () => void, started!: () => void, blocked = false
      const gate = new Promise<void>(resolve => { release = resolve })
      const began = new Promise<void>(resolve => { started = resolve })
      Object.defineProperty(subtle, 'digest', { configurable: true, value: async (algorithm: any, bytes: any) => {
        if (!blocked) { blocked = true; started(); await gate }
        return originalDigest(algorithm, bytes)
      } })
      const first = dispatch(3, 'portableDownload')
      await began
      await dispatch(4, 'portableDownload')
      expect(messages.find(message => message.id === 4).operationError).toBe('rc_corotational_report_portable_export_busy')
      release(); await first
      expect(messages.find(message => message.id === 3).value).toBeInstanceOf(Blob)

      Object.defineProperty(subtle, 'digest', { configurable: true, value: async () => { throw new Error('controlled integrity failure') } })
      await dispatch(5, 'portableDownload')
      expect(messages.find(message => message.id === 5).operationError).toBe('rc_corotational_report_portable_export_unavailable')
      restoreDigest()
      await dispatch(6, 'portableDownload')
      const recovered = messages.find(message => message.id === 6).value as Blob
      expect((await parseRcPortableReview(new Uint8Array(await recovered.arrayBuffer()))).summary.jobId).toBe(data.job.job_id)
      await dispatch(7, 'statePage', { start: 0, count: 2 })
      expect(messages.find(message => message.id === 7).value).toHaveLength(2)
    } finally {
      restoreDigest()
      if (originalSelf) Object.defineProperty(globalThis, 'self', originalSelf)
      else delete (globalThis as any).self
    }
  })
})

test('portable input applies byte and UTF-8 bounds before schema parsing', async () => {
  await expect(parseRcPortableReview(new Uint8Array())).rejects.toThrow('file_too_large')
  const oversize = new Uint8Array(RC_PORTABLE_REVIEW_MAX_BYTES + 1)
  await expect(parseRcPortableReview(oversize)).rejects.toThrow('file_too_large')
  await expect(parseRcPortableReview(Uint8Array.of(0xff))).rejects.toThrow('contract_invalid')
  await expect(parseRcPortableReview(Uint8Array.of(0xef, 0xbb, 0xbf, 0x7b, 0x7d))).rejects.toThrow('encoding_invalid')
})

for (const profile of ['v6', 'v7'] as const) test.describe(`portable retained ${profile} result review`, () => {
  test.skip(!retained, 'Requires retained actual report snapshots; this test never generates a numerical fixture.')
  let source: RcPortableReviewSource, envelope: any, original: any
  test.beforeAll(async () => {
    const snapshot = JSON.parse(readFileSync(path.join(retained!, `${profile}-review-snapshot.json`), 'utf8'))
    const requestBytes = new Uint8Array(Buffer.from(snapshot.artifacts.request, 'base64'))
    const reportBytes = new Uint8Array(Buffer.from(snapshot.report.body_base64, 'base64'))
    const contentHash = digest(reportBytes)
    source = { job: snapshot.job, tenantId: snapshot.tenant_id, requestBytes, reportBytes,
      contentHash, reportId: `rcc_${contentHash.slice(7)}` }
    original = JSON.parse(new TextDecoder().decode(reportBytes))
    envelope = JSON.parse(await (await createRcPortableReviewBlob(source)).text())
  })

  test('retains exact request and report bytes, unknown work and accepted-state accounting', async () => {
    const parsed = await parseRcPortableReview(encode(envelope))
    expect(parsed.requestBytes).toEqual(source.requestBytes)
    expect(parsed.reportBytes).toEqual(source.reportBytes)
    expect(parsed.report).toEqual(original)
    expect(parsed.summary.unknownWork).toBe(original.execution.unknown_execution_work)
    expect(parsed.summary.pendingInvocations).toBe(original.execution.pending_ordinals.length)
    expect(parsed.summary.targetProgress).toEqual(original.progress.authored_targets)
    expect(parsed.summary.attemptProgress).toEqual(original.progress.control_solver_attempts)
    expect(parsed.summary.stateCount).toBe(original.progress.accepted_response_states)
    expect(parsed.report.responses.map(row => row.control_displacement_m)).toEqual(original.responses.map((row: any) => row.control_displacement_m))
    expect(Object.keys(envelope).sort()).toEqual(['custody', 'job', 'recorded_tenant_id', 'report', 'report_id', 'request', 'schema_version'])
    expect(envelope.custody).toBe('portable_unverified_origin')
  })

  test('refuses corruption, missing payload, mixed job identity, invalid base64 and oversized declared artifacts', async () => {
    function jobChange(value: any, mutate: (job: any) => void): void {
      const job = JSON.parse(Buffer.from(value.job.body_base64, 'base64').toString('utf8'))
      mutate(job)
      const bytes = encode(job)
      value.job = { encoding: 'base64', byte_length: bytes.length,
        content_hash: digest(bytes), body_base64: Buffer.from(bytes).toString('base64') }
    }
    for (const mutate of [
      (value: any) => jobChange(value, job => { job.job_id = `job_${'0'.repeat(32)}` }),
      (value: any) => jobChange(value, job => { job.revision++ }),
      (value: any) => { value.recorded_tenant_id = 'other' },
      (value: any) => jobChange(value, job => { job.status = 'failed'; job.result = null; job.evidence = null; job.can_resume = true }),
      (value: any) => { value.job.content_hash = `sha256:${'0'.repeat(64)}` },
      (value: any) => { value.job.byte_length = 65537 },
      (value: any) => { value.report_id = `rcc_${'0'.repeat(64)}` },
      (value: any) => { value.request.byte_length++ },
      (value: any) => { value.report.content_hash = `sha256:${'0'.repeat(64)}`; value.report_id = `rcc_${'0'.repeat(64)}` },
      (value: any) => { value.request.body_base64 = '!' + value.request.body_base64.slice(1) },
      (value: any) => { value.report.body_base64 = value.report.body_base64.slice(4) },
      (value: any) => { value.report.body_base64 = (value.report.body_base64[0] === 'A' ? 'B' : 'A') + value.report.body_base64.slice(1) },
      (value: any) => { value.report.byte_length = RC_PORTABLE_REVIEW_REPORT_MAX_BYTES + 1 },
      (value: any) => { value.request.byte_length = RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES + 1 },
      (value: any) => { value.report.byte_length = NaN },
      (value: any) => { value.request.encoding = 'utf8' },
      (value: any) => { value.report.url = 'https://example.invalid/report' },
      (value: any) => jobChange(value, job => { job.request.media_type = 'application/json'.repeat(10000) }),
    ]) {
      const value = structuredClone(envelope); mutate(value)
      await expect(parseRcPortableReview(encode(value))).rejects.toThrow(/^rc_portable_review_/)
    }
    // Recomputing the outer file's raw hash cannot turn an unrelated report
    // into the selected job's report; the original semantic parser still runs.
    const value = structuredClone(envelope), changed = JSON.parse(new TextDecoder().decode(source.reportBytes))
    changed.bindings.job_id = `job_${'0'.repeat(32)}`
    const changedBytes = encode(changed)
    value.report = { encoding: 'base64', byte_length: changedBytes.length,
      content_hash: digest(changedBytes), body_base64: Buffer.from(changedBytes).toString('base64') }
    value.report_id = `rcc_${digest(changedBytes).slice(7)}`
    await expect(parseRcPortableReview(encode(value))).rejects.toThrow('contract_invalid')
  })

  test('rejects export of a request or report different from validated original custody', async () => {
    await expect(createRcPortableReviewBlob({ ...source, requestBytes: Uint8Array.of(0) })).rejects.toThrow('request_binding_invalid')
    await expect(createRcPortableReviewBlob({ ...source, reportBytes: Uint8Array.of(0) })).rejects.toThrow('report_binding_invalid')
    await expect(createRcPortableReviewBlob({ ...source, reportId: 'rcc_bad' })).rejects.toThrow('report_binding_invalid')
  })
})
