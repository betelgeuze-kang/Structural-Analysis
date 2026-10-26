import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { createRcPortableReviewBlob, parseRcPortableReview, RC_PORTABLE_REVIEW_DETAIL_MAX_BYTES,
  RC_PORTABLE_REVIEW_V1_MAX_BYTES, type RcPortableReviewSource } from '../../src/workbench-v2/model/rcPortableReviewSchema'
import { fields, rawValues } from '../../src/workbench-v2/model/rcJobSchema'
import { loadRcCorotationalReportReview } from '../../src/workbench-v2/model/rcCorotationalReportReview'
import type { JobReadTransport } from '../../src/workbench-v2/model/jobTransport'

const retained = process.env.RC_COROTATIONAL_REPORT_FIXTURE_DIR
const digest = (bytes: Uint8Array | string) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))
const artifact = (bytes: Uint8Array) => ({ encoding: 'base64', byte_length: bytes.byteLength, content_hash: digest(bytes), body_base64: Buffer.from(bytes).toString('base64') })
function source(profile: 'v6' | 'v7'): { data: any; value: RcPortableReviewSource } {
  const data = JSON.parse(readFileSync(path.join(retained!, `${profile}-review-snapshot.json`), 'utf8'))
  const reportBytes = new Uint8Array(Buffer.from(data.report.body_base64, 'base64'))
  const detailBytes = new Uint8Array(Buffer.from(data.detail_report.body_base64, 'base64'))
  return { data, value: { job: data.job, tenantId: data.tenant_id,
    requestBytes: new Uint8Array(Buffer.from(data.artifacts.request, 'base64')), reportBytes,
    reportId: data.report.headers['x-structural-report-id'], contentHash: digest(reportBytes),
    detailReport: { bytes: detailBytes, reportId: data.detail_report.headers['x-structural-report-id'], contentHash: digest(detailBytes) } } }
}
// Preserve producer numeric tokens while repairing the logical hash, so these
// mutations reach the existing identity/state binders rather than a hash check.
function replace(raw: string, route: (string | number)[], replacement: string): string {
  if (!route.length) return replacement
  const [key, ...rest] = route
  if (typeof key === 'number') {
    const values = rawValues(raw); values[key] = replace(values[key], rest, replacement)
    return `[${values.join(',')}]`
  }
  const members = fields(raw), previous = members.get(key)
  if (!previous) throw new Error('test_mutation_path_invalid')
  const value = replace(previous.value, rest, replacement)
  members.set(key, { member: `${JSON.stringify(key)}:${value}`, value })
  return `{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`
}
function rehash(raw: string): Uint8Array {
  const members = fields(raw); members.delete('report_hash')
  const hash = digest(`{${[...members.values()].map(row => row.member).join(',')}}`)
  members.set('report_hash', { member: `"report_hash":${JSON.stringify(hash)}`, value: JSON.stringify(hash) })
  return new TextEncoder().encode(`{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`)
}

for (const profile of ['v6', 'v7'] as const) test.describe(`portable ${profile} optional stored detail`, () => {
  test.skip(!retained, 'Requires retained hosted report bytes; no solver or fixture generator is called.')
  test('v2 retains original input, nodal and detail bytes and admits their existing strict bindings', async () => {
    const { value } = source(profile), blob = await createRcPortableReviewBlob(value)
    const envelope = JSON.parse(await blob.text()), parsed = await parseRcPortableReview(new Uint8Array(await blob.arrayBuffer()))
    expect(envelope.schema_version).toBe('rc-portable-nodal-review.v2')
    expect(Object.keys(envelope).sort()).toEqual(['custody', 'detail_report', 'detail_report_id', 'job', 'recorded_tenant_id', 'report', 'report_id', 'request', 'schema_version'])
    expect(parsed.requestBytes).toEqual(value.requestBytes); expect(parsed.reportBytes).toEqual(value.reportBytes)
    expect(parsed.detailReport!.bytes).toEqual(value.detailReport!.bytes)
    expect(parsed.detailSummary!.reportId).toBe(value.detailReport!.reportId)
    expect(parsed.detail!.nodal_report_hash).toBe(parsed.report.report_hash)
    expect(parsed.detail!.bindings).toEqual(parsed.report.bindings)
    expect(parsed.summary.unknownWork).toBe(true)
    expect(parsed.detailSummary!.members.map(member => member.member_id)).toEqual(parsed.detail!.responses[0].members.map(member => member.member_id))
    expect(envelope.custody).toBe('portable_unverified_origin')
    expect(Object.keys(envelope)).not.toContain('service_url')
  })

  test('v1 remains nodal-only with exact original payload and cannot silently admit declared details', async () => {
    const { value } = source(profile), { detailReport: _detail, ...nodal } = value
    const envelope = JSON.parse(await (await createRcPortableReviewBlob(nodal)).text())
    expect(envelope.schema_version).toBe('rc-portable-nodal-review.v1')
    const parsed = await parseRcPortableReview(encode(envelope))
    expect(parsed.detailSummary).toBeNull(); expect(parsed.detail).toBeNull(); expect(parsed.detailReport).toBeUndefined()
    expect(parsed.requestBytes).toEqual(value.requestBytes); expect(parsed.reportBytes).toEqual(value.reportBytes)
    envelope.detail_report = artifact(value.detailReport!.bytes); envelope.detail_report_id = value.detailReport!.reportId
    await expect(parseRcPortableReview(encode(envelope))).rejects.toThrow('file_fields_invalid')
    // The higher v2 ceiling must not change v1 admission. JSON trailing spaces
    // make a valid v1 file cross its own boundary without changing its values.
    const original = encode({ ...envelope, detail_report: undefined, detail_report_id: undefined })
    const oversizedV1 = new Uint8Array(RC_PORTABLE_REVIEW_V1_MAX_BYTES + 1).fill(32); oversizedV1.set(original)
    await expect(parseRcPortableReview(oversizedV1)).rejects.toThrow('file_too_large')
  })

  test('declared missing, corrupt, oversized or foreign detail rejects the complete candidate', async () => {
    const { value } = source(profile), envelope = JSON.parse(await (await createRcPortableReviewBlob(value)).text())
    for (const mutate of [
      (row: any) => { delete row.detail_report }, (row: any) => { delete row.detail_report_id },
      (row: any) => { row.detail_report = null }, (row: any) => { row.detail_report_id = `rcd_${'0'.repeat(64)}` },
      (row: any) => { row.detail_report.body_base64 = '!' + row.detail_report.body_base64.slice(1) },
      (row: any) => { row.detail_report.body_base64 = row.detail_report.body_base64.slice(4) },
      (row: any) => { row.detail_report.byte_length = RC_PORTABLE_REVIEW_DETAIL_MAX_BYTES + 1 },
      (row: any) => { row.detail_report.content_hash = `sha256:${'0'.repeat(64)}`; row.detail_report_id = `rcd_${'0'.repeat(64)}` },
      (row: any) => { row.detail_report.authorization = 'credential-not-admitted' },
    ]) {
      const altered = structuredClone(envelope); mutate(altered)
      await expect(parseRcPortableReview(encode(altered))).rejects.toThrow(/^rc_portable_review_/)
    }
    const raw = new TextDecoder().decode(value.detailReport!.bytes)
    for (const [route, token] of [
      [['bindings', 'job_id'], `"job_${'0'.repeat(32)}"`],
      [['bindings', 'source_revision'], `"${'f'.repeat(40)}"`],
      [['nodal_report_hash'], `"sha256:${'0'.repeat(64)}"`],
      [['responses', 0, 'checkpoint_hash'], `"sha256:${'0'.repeat(64)}"`],
      [['responses', 1, 'state_index'], '0'],
      [['responses', 0, 'members', 0, 'member_id'], '"foreign-member"'],
    ] as Array<[(string | number)[], string]>) {
      const bytes = rehash(replace(raw, route, token)), altered = structuredClone(envelope)
      altered.detail_report = artifact(bytes); altered.detail_report_id = `rcd_${digest(bytes).slice(7)}`
      await expect(parseRcPortableReview(encode(altered))).rejects.toThrow('contract_invalid')
    }
    await expect(createRcPortableReviewBlob({ ...value, detailReport: { ...value.detailReport!, reportId: 'rcd_foreign' } })).rejects.toThrow('detail_binding_invalid')
  })
})

test.describe('portable detail worker and live export lifecycle', () => {
  test.skip(!retained, 'Requires retained hosted bytes; worker dispatch is a read-only stored-data exercise.')
  test('offline worker returns bounded detail projections and exact bytes, with local errors leaving nodal review usable', async () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'self'), messages: any[] = []
    const scope: any = { postMessage: (message: any) => messages.push(message) }
    Object.defineProperty(globalThis, 'self', { configurable: true, value: scope })
    try {
      await import('../../src/workbench-v2/model/rcPortableReview.worker.ts?portable-detail-extension')
      const dispatch = async (id: number, type: string, input: object = {}) => { await scope.onmessage({ data: { id, type, ...input } }); return messages.find(row => row.id === id) }
      const { value } = source('v7'), parsed = await parseRcPortableReview(new Uint8Array(await (await createRcPortableReviewBlob(value)).arrayBuffer()))
      const initialized = await dispatch(1, 'initialize', { bytes: new Uint8Array(await (await createRcPortableReviewBlob(value)).arrayBuffer()) })
      expect(initialized.value.detailSummary).toEqual(parsed.detailSummary)
      expect(initialized.value).not.toHaveProperty('detail'); expect(initialized.value).not.toHaveProperty('responses')
      const original = parsed.detail!.responses[1].members[0], member = original.member_id
      const projected = (await dispatch(2, 'detailMember', { state: 1, member })).value
      expect(projected.end_force_local_kn_knm).toEqual(original.end_force_local_kn_knm)
      expect(projected.sections[0]).toEqual({ integration_point_index: 0, xi: original.sections[0].xi, section_id: original.sections[0].section_id, fiberCount: original.sections[0].fibers.length })
      expect(projected.sections[0]).not.toHaveProperty('fibers')
      const section = (await dispatch(3, 'detailSection', { state: 1, member, point: 0 })).value
      expect(section.moment_z_kn_m).toBe(original.sections[0].moment_z_kn_m); expect(section).not.toHaveProperty('fibers')
      expect((await dispatch(4, 'detailFiber', { state: 1, member, point: 0, fiber: 0 })).value).toEqual(original.sections[0].fibers[0])
      const history = (await dispatch(5, 'detailFiberPage', { member, point: 0, fiber: 0, start: 0, count: 2 })).value
      expect(history.map((row: any) => [row.state_index, row.strain, row.stress_mpa])).toEqual(parsed.detail!.responses.slice(0, 2).map(row => [row.state_index, row.members[0].sections[0].fibers[0].strain, row.members[0].sections[0].fibers[0].stress_mpa]))
      expect((await dispatch(6, 'detailSectionPage', { member, point: 0, start: 0, count: 51 })).operationError).toBe('rc_corotational_report_detail_page_invalid')
      expect((await dispatch(7, 'detailMember', { state: 0, member: 'missing' })).operationError).toBe('rc_corotational_report_detail_member_invalid')
      expect((await dispatch(8, 'state', { index: 1 })).value).toEqual(parsed.report.responses[1])
      const blob = (await dispatch(9, 'detailDownload')).value as Blob
      expect(new Uint8Array(await blob.arrayBuffer())).toEqual(value.detailReport!.bytes)
    } finally {
      if (descriptor) Object.defineProperty(globalThis, 'self', descriptor); else delete (globalThis as any).self
    }
  })

  test('live worker never adds details implicitly and keeps nodal export usable after explicit missing detail', async () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'self'), messages: any[] = []
    const scope: any = { postMessage: (message: any) => messages.push(message) }
    Object.defineProperty(globalThis, 'self', { configurable: true, value: scope })
    try {
      await import('../../src/workbench-v2/model/rcCorotationalReportReview.worker.ts?portable-detail-extension')
      const dispatch = async (id: number, type: string, input: object = {}) => { await scope.onmessage({ data: { id, type, ...input } }); return messages.find(row => row.id === id) }
      const { value } = source('v7')
      expect((await dispatch(1, 'initialize', { job: value.job, tenantId: value.tenantId, requestBytes: value.requestBytes, bytes: value.reportBytes, reportId: value.reportId, contentHash: value.contentHash, maximumBytes: 64 * 1024 * 1024 })).error).toBeUndefined()
      expect((await dispatch(2, 'portableDownload', { includeDetails: true })).operationError).toBe('rc_corotational_report_portable_export_unavailable')
      const nodal = (await dispatch(3, 'portableDownload')).value as Blob
      expect(JSON.parse(await nodal.text()).schema_version).toBe('rc-portable-nodal-review.v1')
      const detail = value.detailReport!
      expect((await dispatch(4, 'openDetails', { bytes: detail.bytes, reportId: detail.reportId, contentHash: detail.contentHash })).value.reportId).toBe(detail.reportId)
      // Loading details for review does not change the default export contract.
      expect(JSON.parse(await ((await dispatch(5, 'portableDownload')).value as Blob).text()).schema_version).toBe('rc-portable-nodal-review.v1')
      const included = (await dispatch(6, 'portableDownload', { includeDetails: true })).value as Blob
      expect((await parseRcPortableReview(new Uint8Array(await included.arrayBuffer()))).detailReport!.bytes).toEqual(detail.bytes)
    } finally {
      if (descriptor) Object.defineProperty(globalThis, 'self', descriptor); else delete (globalThis as any).self
    }
  })

  test('explicit client export fetches details once under authorization and single-flight, with missing data retry and disposal guards', async () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'Worker'), instances: ControlledWorker[] = []
    class ControlledWorker {
      onmessage: ((event: any) => void) | null = null; onerror: (() => void) | null = null; onmessageerror: (() => void) | null = null
      messages: any[] = []; terminated = false
      constructor() { instances.push(this) }
      postMessage(message: any): void {
        this.messages.push(message)
        if (message.type === 'initialize' || message.type === 'openDetails') queueMicrotask(() => this.onmessage?.({ data: { id: message.id, value: {} } }))
        if (message.type === 'portableDownload') queueMicrotask(() => this.onmessage?.({ data: { id: message.id, value: new Blob([JSON.stringify({ includeDetails: message.includeDetails })]) } }))
      }
      terminate(): void { this.terminated = true }
    }
    Object.defineProperty(globalThis, 'Worker', { configurable: true, value: ControlledWorker })
    const { data, value } = source('v7')
    let detailCalls = 0, detailAvailable = false, authorizationCalls = 0, authorizationGate: Promise<void> | null = null
    const transport = { tenantId: data.tenant_id,
      verifyAuthorizationScope: async () => { authorizationCalls++; if (authorizationGate) await authorizationGate },
      get: async () => new Response(value.requestBytes, { headers: { 'content-type': 'application/json' } }),
      getCorotationalReport: async () => new Response(value.reportBytes, { headers: data.report.headers }),
      getCorotationalDetailReport: async () => { detailCalls++; return detailAvailable ? new Response(value.detailReport!.bytes, { headers: data.detail_report.headers }) : new Response(null, { status: 404 }) },
    } as unknown as JobReadTransport
    try {
      const review = await loadRcCorotationalReportReview(value.job, transport), worker = instances.at(-1)!
      expect(JSON.parse(await (await review.portableDownload!()).text()).includeDetails).toBe(false); expect(detailCalls).toBe(0)
      await expect(review.portableDownload!({ includeDetails: true })).rejects.toThrow('detail_unavailable')
      expect(detailCalls).toBe(1)
      expect(JSON.parse(await (await review.portableDownload!()).text()).includeDetails).toBe(false)
      detailAvailable = true
      const included = review.portableDownload!({ includeDetails: true })
      await expect(review.portableDownload!({ includeDetails: true })).rejects.toThrow('portable_export_busy')
      expect(JSON.parse(await (await included).text()).includeDetails).toBe(true)
      expect(detailCalls).toBe(2); expect(worker.messages.filter(row => row.type === 'openDetails')).toHaveLength(1)
      await review.portableDownload!({ includeDetails: true }); expect(detailCalls).toBe(2)
      review.dispose(); const calls = authorizationCalls
      await expect(review.portableDownload!({ includeDetails: true })).rejects.toThrow('disposed')
      expect(authorizationCalls).toBe(calls)
      // Disposal while initial detail authorization is pending must not fetch.
      const delayed = await loadRcCorotationalReportReview(value.job, transport)
      let release!: () => void; authorizationGate = new Promise<void>(resolve => { release = resolve })
      const pending = delayed.portableDownload!({ includeDetails: true }), rejected = expect(pending).rejects.toThrow('disposed')
      delayed.dispose(); release(); await rejected
      expect(detailCalls).toBe(2)
    } finally {
      if (descriptor) Object.defineProperty(globalThis, 'Worker', descriptor); else delete (globalThis as any).Worker
    }
  })
})
