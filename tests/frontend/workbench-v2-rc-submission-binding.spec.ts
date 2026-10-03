import { test, expect } from '@playwright/test'
import { createHash } from 'node:crypto'
import { createJobWorkflowTransport, type RcJobTransport } from '../../src/workbench-v2/model/jobTransport'
import { verifyRcSubmissionBinding } from '../../src/workbench-v2/model/rcWorkflowProvider'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const encode = (text: string) => new TextEncoder().encode(text)
const hash = (text: string) => `sha256:${createHash('sha256').update(text).digest('hex')}`
const original = '{ "operation": "bounded_rc_fiber_direct_control", "model": {"nodes":[{"id":"N1","coordinates":[-0.0,1e-3,0]}]}, "config": {}, "case_id": "한 input", "source_revision":"a", "execution_config":{"maximum_api_invocations":2} }'
const canonical = '{"case_id":"한 input","config":{},"execution_config":{"maximum_api_invocations":2},"model":{"nodes":[{"coordinates":[-0.0,0.001,0],"id":"N1"}]},"operation":"bounded_rc_fiber_direct_control","source_revision":"a"}'
function source(raw: string): { job: WorkbenchJobView; transport: RcJobTransport } {
  const job: WorkbenchJobView = {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: `job_${'a'.repeat(32)}`, status: 'queued', revision: 1, attempt: 0,
    progress: { completed_steps: 0, total_steps: 1 }, created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z',
    lease_expires_at: null, error_code: null, can_resume: false,
    request: { role: 'request', content_hash: hash(raw), byte_length: encode(raw).length, media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'synthetic submission correspondence only', terminal_event_hash: hash('event'),
  }
  const transport = { getRequest: async () => new Response(raw, { headers: { 'content-type': 'application/json' } }) } as RcJobTransport
  return { job, transport }
}
test('accepts service whitespace/key/finite floating spelling normalization without changing original bytes', async () => {
  const { job, transport } = source(canonical), bytes = encode(original), copy = bytes.slice()
  await verifyRcSubmissionBinding(transport, job, bytes)
  expect(bytes).toEqual(copy)
  expect(job.request.content_hash).not.toBe(hash(original))
})
for (const [name, from, to] of [
  ['model', '0.001', '0.002'], ['case', '한 input', 'other input'], ['source', '"source_revision":"a"', '"source_revision":"b"'],
  ['control', '"config":{}', '"config":{"preload":1}'], ['execution budget', '"maximum_api_invocations":2', '"maximum_api_invocations":3'],
  ['floating signed zero', '-0.0', '0.0'], ['integer type', '"maximum_api_invocations":2', '"maximum_api_invocations":2.0'],
] as const) test(`rejects coherent other stored request: ${name}`, async () => {
  const { job, transport } = source(canonical.replace(from, to))
  await expect(verifyRcSubmissionBinding(transport, job, encode(original))).rejects.toThrow('rc_submission_source_mismatch')
})
test('does not round distinct integers above JavaScript safe range into one request', async () => {
  const { job, transport } = source('{"budget":9007199254740993}')
  await expect(verifyRcSubmissionBinding(transport, job, encode('{"budget":9007199254740992}'))).rejects.toThrow('rc_submission_source_mismatch')
})
test('rejects stored request byte hash contradiction and duplicate submitted keys', async () => {
  const { job, transport } = source(canonical)
  await expect(verifyRcSubmissionBinding(transport, { ...job, request: { ...job.request, content_hash: hash('other') } }, encode(original))).rejects.toThrow('request_hash_mismatch')
  await expect(verifyRcSubmissionBinding(transport, job, encode('{"value":1,"value":2}'))).rejects.toThrow('rc_submit_json_invalid')
})
test('tenant switching during an HTTP response rejects its bytes and latches the session', async () => {
  const originalFetch = globalThis.fetch, originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location')
  const credentials = { tenantId: 'synthetic-A', bearerToken: 'synthetic-only-private-value' }
  Object.defineProperty(globalThis, 'location', { value: { origin: 'https://workbench.test' }, configurable: true })
  let release!: () => void, entered!: () => void, calls = 0
  const waiting = new Promise<void>(resolve => { release = resolve })
  const ready = new Promise<void>(resolve => { entered = resolve })
  globalThis.fetch = async () => { calls++; entered(); await waiting; return new Response('{}', { headers: { 'content-type': 'application/json' } }) }
  try {
    const transport = await createJobWorkflowTransport('/api/v1/jobs', undefined, () => credentials)
    const pending = transport.getJob(`job_${'a'.repeat(32)}`)
    await ready; credentials.tenantId = 'synthetic-B'; release()
    await expect(pending).rejects.toThrow('job_authorization_scope_changed')
    await expect(transport.getJob(`job_${'a'.repeat(32)}`)).rejects.toThrow('job_authorization_scope_changed')
    expect(calls).toBe(1)
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation)
    else Reflect.deleteProperty(globalThis, 'location')
  }
})
