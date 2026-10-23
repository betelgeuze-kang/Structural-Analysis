import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import { captureRcScenario, runRcScenario } from '../../src/workbench-v2/model/rcScenarioRunner'
import { createJobWorkflowTransport, type RcJobTransport } from '../../src/workbench-v2/model/jobTransport'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import {
  createRcControlIntent, loadRcJobControl, parseRcControlCommand, parseRcControlReceipt, parseRcJobControl,
  postRcJobControl, RcControlConflictError, RcControlUnconfirmedError, type RcJobControlView,
} from '../../src/workbench-v2/model/rcJobControl'

const hash = (text: string) => `sha256:${createHash('sha256').update(text).digest('hex')}`
const controlId = 'rc-control-00000000-0000-4000-8000-000000000001'
const request = JSON.stringify(createRcEditorExample('a'.repeat(40)))
function job(): WorkbenchJobView {
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: `job_${'1'.repeat(32)}`, status: 'queued', revision: 0, attempt: 0, progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z', lease_expires_at: null,
    error_code: null, can_resume: false, request: { role: 'request', content_hash: hash(request), byte_length: Buffer.byteLength(request), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null, solver_truth_owner: 'structural_analysis_core',
    result_authority: 'referenced_result_and_evidence_contracts_only', claim_boundary: 'Synthetic control test only.', terminal_event_hash: hash('created'),
  }
}
function available(): RcJobControlView {
  const j = job()
  return { schema_version: 'rc-job-control.v1', job: { job_id: j.job_id, tenant_id: 'test-tenant', request_hash: j.request.content_hash, checkpoint_hash: null, attempt: 0, revision: 0, status: 'queued', terminal_event_hash: j.terminal_event_hash }, control_revision: 0, state: 'available', last_command: null, can_pause: true, can_cancel: true, can_resume_control: false }
}
async function paused(): Promise<RcJobControlView> {
  const v = available(), intent = await createRcControlIntent(v, 'pause', controlId)
  return { ...v, job: { ...v.job, revision: 2, terminal_event_hash: hash('paused') }, control_revision: 1, state: 'paused', can_pause: false, can_resume_control: true,
    last_command: { control_id: controlId, command_hash: intent.commandHash, action: 'pause', control_revision: 1, requested_event_revision: 1, resolved_event_revision: 2, disposition: 'paused', boundary: 'unleased', applied_checkpoint_hash: null, applied_progress: { completed: 0, total: 2 } } }
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function transport(overrides: Partial<RcJobTransport> = {}): RcJobTransport {
  return { tenantId: 'test-tenant', collectionUrl: 'https://example.test/v1/jobs', verifyAuthorizationScope: async () => {},
    getRequest: async () => new Response(request, { headers: { 'Content-Type': 'application/json' } }), ...overrides } as RcJobTransport
}

test('control commands use exact sorted canonical bytes and stable SHA-256, never a job submission key', async () => {
  const intent = await createRcControlIntent(available(), 'pause', controlId)
  expect(intent.serialized).toBe(JSON.stringify(Object.fromEntries(Object.entries(intent.command).sort(([a], [b]) => a.localeCompare(b)))))
  expect(intent.commandHash).toBe(hash(intent.serialized))
  expect(parseRcControlCommand(JSON.parse(intent.serialized))).toEqual(intent.command)
  expect(intent.command.expected_checkpoint_hash).toBeNull()
  for (const mutate of [(v: any) => { v.extra = 0 }, (v: any) => { v.expected_attempt = true }, (v: any) => { v.expected_control_revision = Number.MAX_SAFE_INTEGER + 1 }, (v: any) => { v.control_id = 'rc-control-not-uuid' }]) {
    const command = structuredClone(intent.command); mutate(command)
    expect(() => parseRcControlCommand(command)).toThrow()
  }
})

test('strict control view rejects wrong binding, unknown fields, unsafe integers and contradictory capabilities', async () => {
  expect(parseRcJobControl(available(), job(), 'test-tenant').state).toBe('available')
  const accepted = await paused()
  expect(parseRcJobControl(accepted, job(), 'test-tenant').state).toBe('paused')
  for (const mutate of [
    (v: any) => { v.extra = 1 }, (v: any) => { v.job.tenant_id = 'foreign' }, (v: any) => { v.job.request_hash = hash('wrong') },
    (v: any) => { v.job.job_id = `job_${'9'.repeat(32)}` }, (v: any) => { v.job.attempt = true }, (v: any) => { v.control_revision = Number.MAX_SAFE_INTEGER + 1 },
    (v: any) => { v.can_pause = true }, (v: any) => { v.state = 'available' }, (v: any) => { v.last_command.boundary = 'worker_failure' },
    (v: any) => { v.last_command.requested_event_revision = 0 }, (v: any) => { v.last_command.applied_progress.total = 0 },
    (v: any) => { v.last_command.resolved_event_revision = 1 }, (v: any) => { v.last_command.command_hash = 'missing' },
  ]) { const v = structuredClone(accepted); mutate(v); expect(() => parseRcJobControl(v, job(), 'test-tenant')).toThrow() }
  expect(() => parseRcJobControl(available(), job(), undefined)).toThrow()
  const stale = available(); stale.job.terminal_event_hash = hash('different same revision')
  expect(() => parseRcJobControl(stale, job(), 'test-tenant')).toThrow()
})

test('old command receipt stays separate from a later latest command and verifies the original ID/hash', async () => {
  const intent = await createRcControlIntent(available(), 'pause', controlId), latest = await paused()
  latest.job.revision = 4; latest.job.terminal_event_hash = hash('resumed'); latest.control_revision = 2
  latest.state = 'available'; latest.can_pause = true; latest.can_resume_control = false
  latest.last_command = { ...latest.last_command!, control_id: 'rc-control-00000000-0000-4000-8000-000000000002', command_hash: hash('resume'), action: 'resume', control_revision: 2, requested_event_revision: 3, resolved_event_revision: 4, disposition: 'resumed' }
  const value = { schema_version: 'rc-job-control-command-result.v1', control_id: controlId, command_hash: intent.commandHash, accepted_control_revision: 1, view: latest }
  const receipt = await parseRcControlReceipt(value, intent, job(), 'test-tenant')
  expect(receipt.control_id).not.toBe(receipt.view.last_command!.control_id)
  for (const change of [{ control_id: latest.last_command.control_id }, { command_hash: hash('wrong') }, { accepted_control_revision: 2 }, { extra: 1 }]) {
    await expect(parseRcControlReceipt({ ...value, ...change }, intent, job(), 'test-tenant')).rejects.toThrow()
  }
})

test('unknown POST retries preserve one canonical body and command ID; malformed receipts stay unconfirmed', async () => {
  const intent = await createRcControlIntent(available(), 'pause', controlId), calls: string[] = []
  const session = transport({ postRcControl: async (_id, raw) => { calls.push(raw); return calls.length === 1 ? json({}, 503) : json({ schema_version: 'rc-job-control-command-result.v1', control_id: controlId, command_hash: intent.commandHash, accepted_control_revision: 1, view: await paused() }) } })
  await expect(postRcJobControl(session, job(), intent)).rejects.toBeInstanceOf(RcControlUnconfirmedError)
  expect((await postRcJobControl(session, job(), intent)).view.state).toBe('paused')
  expect(calls).toEqual([intent.serialized, intent.serialized])
  await expect(postRcJobControl(transport({ postRcControl: async () => json({}) }), job(), intent)).rejects.toBeInstanceOf(RcControlUnconfirmedError)
  await expect(postRcJobControl(session, job(), { ...intent, serialized: intent.serialized + ' ' })).rejects.toThrow('command_invalid')
  expect(calls).toHaveLength(2)
})

for (const status of [400, 409, 401, 403]) {
  test(`control POST status ${status} preserves rejection versus authorization loss without automatic retry`, async () => {
    const intent = await createRcControlIntent(available(), 'pause', controlId)
    let calls = 0
    const pending = postRcJobControl(transport({ postRcControl: async () => { calls++; return json({}, status) } }), job(), intent)
    if (status < 401 || status === 409) await expect(pending).rejects.toBeInstanceOf(RcControlConflictError)
    else await expect(pending).rejects.toThrow(`job_api_http_${status}`)
    expect(calls).toBe(1)
  })
}

test('old service control 404 is unsupported and never falls back to POST or legacy resume', async () => {
  let posts = 0, reads = 0
  const session = transport({ getRcControl: async () => { reads++; return json({}, 404) }, postRcControl: async () => { posts++; return json({}) }, resume: async () => { posts++; return json({}) } })
  expect(await loadRcJobControl(session, job())).toBeNull()
  expect(reads).toBe(1); expect(posts).toBe(0)
})

test('control read verifies authorization again before releasing the parsed view', async () => {
  const session = transport({ getRcControl: async () => json(available()), verifyAuthorizationScope: async () => { throw new Error('job_authorization_scope_changed') } })
  await expect(loadRcJobControl(session, job())).rejects.toThrow('job_authorization_scope_changed')
})

test('a stored paused scenario returns its original job without polling, submission or resume', async () => {
  const intent = captureRcScenario(JSON.parse(request), 'Paused', 'paused-scenario', request)
  const calls: string[] = [], seen: WorkbenchJobView[] = [], old = job()
  const session = transport({ getRcControl: async () => { calls.push('control GET'); return json(await paused()) }, getJob: async () => { calls.push('job GET'); return json(old) }, submit: async () => { calls.push('POST'); return json(old) }, resume: async () => { calls.push('resume'); return json(old) } })
  let held = false
  const result = await runRcScenario(session, intent, { signal: new AbortController().signal, existingJob: old, onJob: value => seen.push(value), onPaused: () => { held = true }, pollIntervalMs: 0, maximumPolls: 2 })
  expect(result).toBe(old); expect(held).toBe(true); expect(seen).toEqual([]); expect(calls).toEqual(['control GET'])
})

test('transport control requests use the scoped job endpoint and unchanged canonical bytes', async () => {
  const original = globalThis.fetch, calls: Array<{ url: string; method: string; body: string | null }> = []
  globalThis.fetch = (async (url, init) => { calls.push({ url: String(url), method: init?.method ?? 'GET', body: init?.body as string ?? null }); return json(available()) }) as typeof fetch
  try {
    const session = await createJobWorkflowTransport('https://example.test/v1/jobs')
    const intent = await createRcControlIntent(available(), 'pause', controlId)
    await session.getRcControl!(job().job_id); await session.postRcControl!(job().job_id, intent.serialized)
    expect(calls).toEqual([{ url: `https://example.test/v1/jobs/${job().job_id}/rc-control`, method: 'GET', body: null }, { url: `https://example.test/v1/jobs/${job().job_id}/rc-control`, method: 'POST', body: intent.serialized }])
    await expect(async () => session.postRcControl!('invalid', intent.serialized)).rejects.toThrow('job_id_invalid')
    expect(calls).toHaveLength(2)
  } finally { globalThis.fetch = original }
})

test('control view binds queued and checkpointed status to checkpoint presence without fabricating missing checkpoints', async () => {
  const queued = await paused()
  queued.job.checkpoint_hash = hash('unexpected checkpoint')
  queued.last_command!.applied_checkpoint_hash = queued.job.checkpoint_hash
  expect(() => parseRcJobControl(queued, job(), 'test-tenant')).toThrow()
  const checkpointed = await paused()
  checkpointed.job.status = 'checkpointed'
  expect(() => parseRcJobControl(checkpointed, job(), 'test-tenant')).toThrow()
  checkpointed.job.checkpoint_hash = hash('saved checkpoint')
  checkpointed.last_command!.applied_checkpoint_hash = checkpointed.job.checkpoint_hash
  expect(parseRcJobControl(checkpointed, job(), 'test-tenant').job.checkpoint_hash).toBe(hash('saved checkpoint'))
  checkpointed.last_command!.applied_checkpoint_hash = hash('another checkpoint')
  expect(() => parseRcJobControl(checkpointed, job(), 'test-tenant')).toThrow()
})

test('control token fields reject array wrappers instead of coercing valid text', async () => {
  const intent = await createRcControlIntent(available(), 'pause', controlId)
  for (const key of ['control_id', 'expected_request_hash', 'expected_checkpoint_hash']) {
    const command: any = structuredClone(intent.command)
    command[key] = [key === 'expected_checkpoint_hash' ? hash('checkpoint') : command[key]]
    expect(() => parseRcControlCommand(command)).toThrow()
  }
  for (const [container, key] of [['job', 'terminal_event_hash'], ['job', 'request_hash'], ['job', 'checkpoint_hash'], ['last_command', 'control_id'], ['last_command', 'command_hash'], ['last_command', 'applied_checkpoint_hash']] as const) {
    const view: any = await paused()
    view[container][key] = [view[container][key] ?? hash('checkpoint')]
    expect(() => parseRcJobControl(view, job(), 'test-tenant')).toThrow()
  }
  for (const key of ['control_id', 'command_hash']) {
    const receipt: any = { schema_version: 'rc-job-control-command-result.v1', control_id: controlId, command_hash: intent.commandHash, accepted_control_revision: 1, view: await paused() }
    receipt[key] = [receipt[key]]
    await expect(parseRcControlReceipt(receipt, intent, job(), 'test-tenant')).rejects.toThrow()
  }
})

test('control response integer fields reject fractional or exponent tokens even when Number rounds them to safe integers', async () => {
  for (const token of ['1.0', '1e0', '9007199254740991.1']) {
    const value = available(); value.job.revision = 1
    const raw = JSON.stringify(value).replace('"revision":1', `"revision":${token}`)
    expect(Number.isSafeInteger(JSON.parse(raw).job.revision)).toBe(true)
    const session = transport({ getRcControl: async () => new Response(raw, { headers: { 'Content-Type': 'application/json' } }) })
    await expect(loadRcJobControl(session, job())).rejects.toThrow('rc_control_response_invalid')
  }
})
