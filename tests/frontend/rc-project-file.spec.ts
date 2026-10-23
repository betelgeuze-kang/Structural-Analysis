import { expect, test } from '@playwright/test'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import { SUBMIT_MAX_BYTES } from '../../src/workbench-v2/model/jobTransport'
import {
  parseRcProjectFile, RC_PROJECT_MAX_BYTES, rcProjectJobRef, serializeRcProjectFile,
  type RcProjectFile, type RcProjectJobRef,
} from '../../src/workbench-v2/model/rcProjectFile'
import { emptyRcProject, sameRcProject, snapshotRcProject } from '../../src/workbench-v2/model/rcProjectSnapshot'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const scope = { collectionUrl: 'https://example.test/v1/jobs', tenantId: 'tenant-A' }
const ref = (value = '1'): RcProjectJobRef => ({ jobId: `job_${value.repeat(32)}`, requestHash: `sha256:${value.repeat(64)}` })
const primaryKey = 'rc-ui-12345678-1234-4234-8234-123456789abc'
function nativeRequest(): string {
  const request = createRcEditorExample('a'.repeat(40))
  request.model.metadata = { native_float: 1, native_integer: 0 }
  return JSON.stringify(request, null, 2).replace('"native_float": 1', '"native_float": 1.0')
    .replace('"native_integer": 0', '"native_integer": 9007199254740993')
}
function project(): RcProjectFile {
  const serialized = nativeRequest()
  return { schema: 'rc-workbench-project.v1', scope: { ...scope }, draft: serialized,
    submission: { serialized, idempotencyKey: primaryKey, job: ref() }, selectedJob: ref(),
    changedRun: { original: ref('2'), child: ref() },
    scenarios: [
      { intent: { id: 'baseline', name: 'Baseline', serialized, idempotencyKey: 'rc-scenario-baseline' }, attempted: true, job: ref('3') },
      { intent: { id: 'variant', name: '설계안', serialized, idempotencyKey: 'rc-scenario-variant' }, attempted: false, job: null },
    ], baselineId: 'baseline', variantId: 'variant' }
}
function load(value: unknown): RcProjectFile { return parseRcProjectFile(JSON.stringify(value), scope) }

test('round trip preserves native request bytes, pending submission identity, links and authored order', () => {
  const original = project(), encoded = serializeRcProjectFile(original), restored = parseRcProjectFile(encoded, scope)
  expect(restored).toEqual(original)
  expect(restored.submission!.serialized).toContain('"native_float": 1.0')
  expect(restored.submission!.serialized).toContain('9007199254740993')
  expect(restored.scenarios[0].intent.serialized).toBe(original.draft)
  expect(restored.scenarios.map(row => row.intent.id)).toEqual(['baseline', 'variant'])
  expect(Object.keys(restored.scenarios[0]).sort()).toEqual(['attempted', 'intent', 'job'])
  expect(restored.selectedJob).not.toBe(original.selectedJob)
})

test('incomplete input drafts are retained without granting submission or result authority', () => {
  const original = project()
  original.draft = '{ "incomplete":'
  original.submission = null
  original.scenarios = []; original.baselineId = null; original.variantId = null
  expect(parseRcProjectFile(serializeRcProjectFile(original), scope)).toEqual(original)
  original.draft = ''
  expect(load(original).draft).toBe('')
})

test('uncertain submissions and attempted scenarios retain identical keys and request strings without inventing jobs', () => {
  const original = project()
  original.submission!.job = null
  original.scenarios[0].job = null
  original.selectedJob = null
  const restored = parseRcProjectFile(serializeRcProjectFile(original), scope)
  expect(restored.submission).toEqual(original.submission)
  expect(restored.scenarios[0]).toEqual(original.scenarios[0])
  expect(restored.scenarios[0].attempted).toBe(true)
})

for (const [label, mutate, error] of [
  ['unsupported schema', (p: any) => { p.schema = 'rc-workbench-project.v2' }, 'schema_unsupported'],
  ['credential authority', (p: any) => { p.bearerToken = 'never-import-this' }, 'file_fields_invalid'],
  ['saved result authority', (p: any) => { p.scenarios[0].result = { success: true } }, 'scenario_fields_invalid'],
  ['saved status authority', (p: any) => { p.selectedJob.status = 'succeeded' }, 'job_reference_fields_invalid'],
  ['missing top level field', (p: any) => { delete p.changedRun }, 'file_fields_invalid'],
  ['foreign tenant', (p: any) => { p.scope.tenantId = 'tenant-B' }, 'scope_mismatch'],
  ['foreign collection', (p: any) => { p.scope.collectionUrl = 'https://elsewhere.test/v1/jobs' }, 'scope_mismatch'],
  ['scope credentials', (p: any) => { p.scope.authorization = 'not-allowed' }, 'scope_fields_invalid'],
  ['untrimmed scenario name', (p: any) => { p.scenarios[0].intent.name = ' Baseline' }, 'scenario_name_invalid'],
  ['control character scenario name', (p: any) => { p.scenarios[0].intent.name = 'base\nline' }, 'scenario_name_invalid'],
  ['oversized scenario name', (p: any) => { p.scenarios[0].intent.name = 'a'.repeat(81) }, 'scenario_name_invalid'],
  ['duplicate scenario identity', (p: any) => { p.scenarios[1].intent.id = 'baseline' }, 'scenario_identity_invalid'],
  ['retargeted scenario key', (p: any) => { p.scenarios[1].intent.idempotencyKey = 'rc-scenario-baseline' }, 'scenario_key_invalid'],
  ['malformed scenario identity', (p: any) => { p.scenarios[0].intent.id = '../relative' }, 'scenario_identity_invalid'],
  ['nonboolean attempted flag', (p: any) => { p.scenarios[0].attempted = 1 }, 'scenario_attempt_invalid'],
  ['job assigned before attempt', (p: any) => { p.scenarios[1].job = ref('4') }, 'scenario_attempt_invalid'],
  ['foreign selection', (p: any) => { p.variantId = 'missing' }, 'scenario_selection_invalid'],
  ['noncanonical primary key', (p: any) => { p.submission.idempotencyKey = 'rc-ui-other' }, 'submission_key_invalid'],
  ['nonidentical submitted draft', (p: any) => { p.draft += '\n' }, 'submission_draft_mismatch'],
  ['conflicting job request', (p: any) => { p.selectedJob.requestHash = ref('4').requestHash }, 'job_request_conflict'],
  ['same original and child job', (p: any) => { p.changedRun.child = p.changedRun.original }, 'changed_run_same_job'],
  ['malformed job identity', (p: any) => { p.selectedJob.jobId = 'job_not_real' }, 'job_reference_invalid'],
  ['malformed request hash', (p: any) => { p.selectedJob.requestHash = 'sha256:bad' }, 'job_reference_invalid'],
] as const) {
  test(`rejects ${label}`, () => {
    const value = project(); mutate(value)
    expect(() => load(value)).toThrow(error)
    if (error === 'scope_mismatch') expect(() => serializeRcProjectFile(value)).not.toThrow()
    else expect(() => serializeRcProjectFile(value)).toThrow(error)
  })
}

test('serialization validates the file itself and import additionally binds the current endpoint and tenant', () => {
  const value = project(); value.scope.tenantId = null
  const serialized = serializeRcProjectFile(value)
  expect(parseRcProjectFile(serialized, { ...scope, tenantId: null }).scope.tenantId).toBeNull()
  expect(() => parseRcProjectFile(serialized, scope)).toThrow('scope_mismatch')
})

for (const url of [
  'https://user:secret@example.test/v1/jobs', 'https://example.test/v1/jobs?token=secret',
  'https://example.test/v1/jobs#token', 'file:///tmp/jobs', '/v1/jobs',
  'https://EXAMPLE.test:443/v1/jobs', 'https://example.test/v1/jobs/',
  'https://example.test/v1/jobs?', 'https://example.test/v1/jobs#',
]) {
  test(`rejects noncanonical or credential-bearing endpoint ${url}`, () => {
    const value = project(); value.scope.collectionUrl = url
    expect(() => load(value)).toThrow(/scope_url/)
  })
}

test('scope tenant must be null or a bounded nonspace printable ASCII identifier', () => {
  for (const tenantId of ['', 'a b', '\t', 'tenant\nA', '한국어', 'x'.repeat(257)]) {
    const value = project(); value.scope.tenantId = tenantId
    expect(() => load(value)).toThrow('scope_tenant_invalid')
  }
})

test('duplicate JSON fields and prototype-like unexpected fields are rejected before they can hide another intent', () => {
  const serialized = JSON.stringify(project())
  expect(() => parseRcProjectFile(serialized.replace('"schema":', '"schema":"unexpected","schema":'), scope)).toThrow('duplicate_json_key')
  expect(() => parseRcProjectFile(serialized.replace('"scope":{', '"scope":{"__proto__":{},'), scope)).toThrow('scope_fields_invalid')
  const value = project()
  value.scenarios[0].intent = { ...value.scenarios[0].intent, serialized: '{"schema_version":1,"schema_version":2}' }
  expect(() => load(value)).toThrow('duplicate_json_key')
})

test('only supported request profiles are admitted for submitted or captured requests', () => {
  const scenario = project(); scenario.scenarios[0].intent = { ...scenario.scenarios[0].intent, serialized: '{}' }
  expect(() => load(scenario)).toThrow()
  const submission = project(); submission.submission!.serialized = submission.draft = '{"unfinished":'
  expect(() => load(submission)).toThrow()
  const empty = project(); empty.scenarios[0].intent = { ...empty.scenarios[0].intent, serialized: '' }
  expect(() => load(empty)).toThrow('scenario_request_invalid')
})

test('four named designs and identical display names are allowed but a fifth design is rejected', () => {
  const value = project()
  value.scenarios = ['a', 'b', 'c', 'd'].map(id => ({ intent: {
    id, name: 'Same display name', serialized: value.draft, idempotencyKey: `rc-scenario-${id}`,
  }, attempted: false, job: null }))
  value.baselineId = 'a'; value.variantId = 'b'
  expect(load(value).scenarios).toHaveLength(4)
  value.scenarios.push({ ...value.scenarios[0], intent: { ...value.scenarios[0].intent, id: 'e', idempotencyKey: 'rc-scenario-e' } })
  expect(() => load(value)).toThrow('scenario_limit')
})

test('file, draft and request bounds count UTF-8 bytes and refuse oversized input before parsing', () => {
  expect(() => parseRcProjectFile(' '.repeat(RC_PROJECT_MAX_BYTES + 1), scope)).toThrow('file_too_large')
  const value = project(); value.submission = null
  value.draft = 'a'.repeat(SUBMIT_MAX_BYTES)
  expect(load(value).draft.length).toBe(SUBMIT_MAX_BYTES)
  value.draft += 'a'
  expect(() => serializeRcProjectFile(value)).toThrow('draft_too_large')
  value.draft = '가'.repeat(Math.floor(SUBMIT_MAX_BYTES / 3) + 1)
  expect(value.draft.length).toBeLessThan(SUBMIT_MAX_BYTES)
  expect(() => serializeRcProjectFile(value)).toThrow('draft_too_large')
  value.draft = ''
  value.scenarios[0].intent = { ...value.scenarios[0].intent, serialized: ' '.repeat(SUBMIT_MAX_BYTES + 1) }
  expect(() => serializeRcProjectFile(value)).toThrow('scenario_request_too_large')
})

test('job projection retains only validated immutable identity and request binding', () => {
  const original = { job_id: ref().jobId, request: { content_hash: ref().requestHash }, status: 'succeeded', result: { untrusted: true } } as unknown as WorkbenchJobView
  expect(rcProjectJobRef(original)).toEqual(ref())
  original.job_id = '../invalid'
  expect(() => rcProjectJobRef(original)).toThrow('job_reference_invalid')
})


test('project snapshot preserves immutable raw strings and isolates every mutable custody wrapper', () => {
  const original = project(), snapshot = snapshotRcProject(original)
  expect(snapshot).toEqual(original)
  expect(snapshot.draft).toBe(original.draft)
  expect(snapshot.submission!.serialized).toBe(original.submission!.serialized)
  expect(snapshot.selectedJob).not.toBe(original.selectedJob)
  expect(snapshot.submission!.job).not.toBe(original.submission!.job)
  expect(snapshot.changedRun!.original).not.toBe(original.changedRun!.original)
  expect(snapshot.changedRun!.child).not.toBe(original.changedRun!.child)
  expect(snapshot.scenarios[0].intent).not.toBe(original.scenarios[0].intent)
  expect(snapshot.scenarios[0].job).not.toBe(original.scenarios[0].job)
  original.selectedJob!.requestHash = ref('4').requestHash
  original.submission!.job!.jobId = ref('4').jobId
  original.changedRun!.original.requestHash = ref('4').requestHash
  original.changedRun!.child!.jobId = ref('4').jobId
  original.scenarios[0].job!.jobId = ref('4').jobId
  original.scenarios[0].intent = { ...original.scenarios[0].intent, name: 'Later design' }
  expect(snapshot).toEqual(project())
  expect(sameRcProject(original, snapshot)).toBe(false)
})

test('project snapshot comparison includes every saved custody field and exact native numeric text', () => {
  const baseline = snapshotRcProject(project())
  const changes: Array<(value: RcProjectFile) => void> = [
    value => { value.scope.tenantId = 'other' }, value => { value.scope.collectionUrl += '/other' },
    value => { value.draft += '\n' }, value => { value.submission!.serialized = value.submission!.serialized.replace('1.0', '1') },
    value => { value.submission!.idempotencyKey += 'x' }, value => { value.submission!.job = null },
    value => { value.selectedJob = null }, value => { value.changedRun!.child = null },
    value => { value.changedRun!.original = ref('4') }, value => { value.scenarios.reverse() },
    value => { value.scenarios[0].attempted = false }, value => { value.scenarios[0].job = null },
    value => { value.scenarios[0].intent = { ...value.scenarios[0].intent, serialized: value.scenarios[0].intent.serialized.replace('9007199254740993', '9007199254740992') } },
    value => { value.scenarios[0].intent = { ...value.scenarios[0].intent, name: 'Renamed' } },
    value => { value.scenarios[0].intent = { ...value.scenarios[0].intent, id: 'new-id' } },
    value => { value.scenarios[0].intent = { ...value.scenarios[0].intent, idempotencyKey: 'new-key' } },
    value => { value.baselineId = null }, value => { value.variantId = 'baseline' },
  ]
  expect(sameRcProject(project(), baseline)).toBe(true)
  for (const change of changes) { const current = project(); change(current); expect(sameRcProject(current, baseline)).toBe(false) }
})

test('project dirtiness ignores result polling metadata and handles large incomplete drafts without serialization', () => {
  const original = project(), baseline = snapshotRcProject(original)
  const polled = snapshotRcProject(original) as RcProjectFile & { status: string; revision: number; result: unknown }
  polled.status = 'succeeded'; polled.revision = 42; polled.result = { arbitrary: true }
  expect(sameRcProject(polled, baseline)).toBe(true)
  const incomplete = project(); incomplete.submission = null; incomplete.draft = '{' + ' '.repeat(1024 * 1024)
  const nativeStringify = JSON.stringify
  let equal = false, changed = false
  try {
    JSON.stringify = () => { throw new Error('Snapshot equality must not serialize') }
    const saved = snapshotRcProject(incomplete)
    equal = sameRcProject(incomplete, saved)
    incomplete.draft += '0'
    changed = !sameRcProject(incomplete, saved)
  } finally { JSON.stringify = nativeStringify }
  expect(equal).toBe(true); expect(changed).toBe(true)
})

test('an empty initial project is clean independently of account discovery but authored values are not empty', () => {
  const value = project()
  value.draft = ''; value.submission = null; value.selectedJob = null; value.changedRun = null
  value.scenarios = []; value.baselineId = null; value.variantId = null
  expect(emptyRcProject(value)).toBe(true)
  value.scope.tenantId = null
  expect(emptyRcProject(value)).toBe(true)
  value.draft = '{'
  expect(emptyRcProject(value)).toBe(false)
  value.draft = ''; value.selectedJob = ref()
  expect(emptyRcProject(value)).toBe(false)
})
