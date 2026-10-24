import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { createRcEditorExample, createRcPortalEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import {
  compareRcScenarios, exportRcScenarios, fixedRcScenarioSummary,
  rcScenarioAuthorizationFailure, rcScenarioCompatibility, rcScenarioCompatibilityFields, rcScenarioRecordedWallSeconds, type RcScenarioSummary,
} from '../../src/workbench-v2/model/rcScenarioComparison'
import { compareRcScenarioInputs, RC_INPUT_COMPARISON_BYTES } from '../../src/workbench-v2/model/rcScenarioInputComparison'
import { captureRcScenario, runRcScenario, RcScenarioUnconfirmedError } from '../../src/workbench-v2/model/rcScenarioRunner'
import type { RcJobTransport } from '../../src/workbench-v2/model/jobTransport'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const source = 'a'.repeat(40), hash = (text: string) => `sha256:${createHash('sha256').update(text).digest('hex')}`
const draft = () => createRcEditorExample(source)
function job(request: string, status: WorkbenchJobView['status'] = 'queued'): WorkbenchJobView {
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: `job_${'1'.repeat(32)}`, status, revision: 0, attempt: 0, progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z', lease_expires_at: null,
    error_code: null, can_resume: false,
    request: { role: 'request', content_hash: hash(request), byte_length: Buffer.byteLength(request), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'Software test orchestration fixture only.', terminal_event_hash: `sha256:${'2'.repeat(64)}`,
  }
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function summary(): RcScenarioSummary {
  const request = draft(), terminal = job(JSON.stringify(request), 'succeeded')
  terminal.result = { role: 'result', content_hash: `sha256:${'3'.repeat(64)}`, byte_length: 1, media_type: 'application/json' }
  terminal.evidence = { role: 'evidence', content_hash: `sha256:${'4'.repeat(64)}`, byte_length: 1, media_type: 'application/json' }
  // Deliberately small synthetic unit-test rows. This function is a projection
  // test; only reviewer workers may call it on actual validated artifacts.
  return fixedRcScenarioSummary(request, terminal, {
    resultHash: terminal.result.content_hash, sourceRevision: source, targets: [-1e-6, -2e-6],
    control: { node_id: 'N2', component: 'UY', unit: 'm' }, reservedInvocations: 0, confirmedInvocations: 0,
    knownCoreCalls: 0, knownNewtonIterations: 0, unknownWork: true, artifactRoles: [],
  }, [-1e-6, -2e-6].map((target, index) => ({
    epoch: index + 1, load_factor: index + 1,
    node_displacements: [{ node_id: 'N2', UX_m: 0, UY_m: target, RZ_rad: -3e-6 }, { node_id: 'N1', UX_m: 0, UY_m: 0, RZ_rad: 0 }],
    support_reactions: [{ node_id: 'N1', dof: 'UY', unit: 'N', value_si: 20 }],
    member_end_forces: [{ member_id: 'M1', local_end_i: { FX_N: 1, FY_N: 20, MZ_Nm: 60 }, local_end_j: { FX_N: -1, FY_N: -20, MZ_Nm: 0 } }],
    section_results: [{ confidential_unused: true }], fiber_results: [{ confidential_unused: true }],
  })))
}

test('captures immutable original bytes and rejects invalid name/request', () => {
  const input = draft(), captured = captureRcScenario(input, ' Baseline ', 'stable-1')
  input.model.sections[0].width_m = 99
  expect(JSON.parse(captured.serialized).model.sections[0].width_m).toBe(0.4)
  expect(captured.name).toBe('Baseline')
  expect(captured.idempotencyKey).toBe('rc-scenario-stable-1')
  expect(Object.isFrozen(captured)).toBe(true)
  expect(() => captureRcScenario(draft(), '\u0000invalid', 'a')).toThrow('name_invalid')
  expect(() => captureRcScenario({} as never, 'bad', 'a')).toThrow()
  const imported = draft(), originalText = JSON.stringify(imported, null, 2).replace('200000', '200000.0')
  expect(captureRcScenario(imported, 'imported', 'native-float', originalText).serialized).toBe(originalText)
  const changed = structuredClone(imported); changed.model.sections[0].width_m = 1
  expect(() => captureRcScenario(changed, 'mismatched', 'native-float-mismatch', originalText)).toThrow('draft_binding_invalid')
  const native = draft(); native.model.metadata = { native_float: 1, native_integer: 0 }
  const nativeText = JSON.stringify(native).replace('"native_float":1', '"native_float":1.0')
    .replace('"native_integer":0', '"native_integer":9007199254740993')
  const displayed = JSON.parse(nativeText)
  expect(displayed.model.metadata.native_integer).toBe(9007199254740992)
  const preserved = captureRcScenario(displayed, 'native numeric custody', 'native-numbers', nativeText)
  expect(preserved.serialized).toBe(nativeText)
  expect(preserved.serialized).toContain('"native_float":1.0')
  expect(preserved.serialized).toContain('9007199254740993')
})

test('captured input comparison separates original text equality from formatting and decoded value equality', () => {
  const input = draft(), raw = JSON.stringify(input)
  const captured = captureRcScenario(input, 'Original', 'input-original', raw)
  input.model.sections[0].width_m = 9
  const exact = compareRcScenarioInputs(captured.serialized, raw)
  expect(exact).toMatchObject({ status: 'available', rawIdentical: true, changes: [], compatibility: 'compatible', precisionLimited: false })
  const formatted = compareRcScenarioInputs(raw, JSON.stringify(JSON.parse(raw), null, 2))
  expect(formatted).toMatchObject({ rawIdentical: false, changes: [], compatibility: 'compatible' })
  expect(formatted.message).toContain('Whitespace, key order or string escaping')
  const reordered = Object.fromEntries(Object.entries(JSON.parse(raw)).reverse())
  expect(compareRcScenarioInputs(raw, JSON.stringify(reordered))).toMatchObject({ rawIdentical: false, changes: [], compatibility: 'compatible' })
})

test('captured input comparison names shared numerical scope mismatches while allowing geometric and material design changes', () => {
  const left = draft(), changed = structuredClone(left)
  changed.model.nodes[1].coordinates[0] = 4.5; changed.model.sections[0].width_m = 0.6; changed.model.materials[0].yield_stress_mpa = 350
  expect(compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(changed))).toMatchObject({ compatibility: 'compatible', reasons: [] })
  for (const [key, mutate] of [
    ['source', (value: any) => { value.source_revision = 'b'.repeat(40) }],
    ['loads', (value: any) => { value.model.loads[0].components.FY = -99 }],
    ['supports', (value: any) => { value.model.supports[0].node = 'N2'; value.config.control_global_dof = 1 }],
    ['control', (value: any) => { value.config.control_global_dof = 3 }],
    ['members', (value: any) => { value.model.elements[0].nodes.reverse() }],
    ['targets', (value: any) => { value.config.targets_m = [-1e-6, -3e-6] }],
  ] as const) {
    const right = structuredClone(left); mutate(right)
    const comparison = compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(right))
    expect(comparison.status, key).toBe('available')
    expect(comparison.compatibility, key).toBe('incompatible')
    expect(comparison.reasons.map(reason => reason.key), key).toContain(key)
    expect(rcScenarioCompatibility(left), key).not.toBe(rcScenarioCompatibility(right))
  }
  const supportOrder = structuredClone(left); supportOrder.model.supports[0].dofs.reverse()
  expect(compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(supportOrder))).toMatchObject({ compatibility: 'compatible', reasons: [] })
  const portal = createRcPortalEditorExample(source), portalChanged = structuredClone(portal)
  portalChanged.model.nodes[1].coordinates[0] = portalChanged.model.nodes[3].coordinates[0] = 5
  expect(compareRcScenarioInputs(JSON.stringify(portal), JSON.stringify(portalChanged)).compatibility).toBe('compatible')
  expect(rcScenarioCompatibilityFields(portal).find(field => field.key === 'portal')).toMatchObject({ label: 'Portal profile opt-in', signature: 'true' })
  delete portalChanged.config.experimental_portal_frame
  expect(rcScenarioCompatibility(portal)).not.toBe(rcScenarioCompatibility(portalChanged))
  expect(compareRcScenarioInputs(JSON.stringify(portal), JSON.stringify(portalChanged))).toMatchObject({ status: 'invalid', compatibility: 'unavailable' })
})

test('captured input comparison preserves unsafe integer digits and never infers numerical compatibility from rounded equality', () => {
  const value = draft(); value.model.loads[0].components.FY = 0
  const raw = JSON.stringify(value)
  const left = raw.replace('"FY":0', '"FY":9007199254740992'), right = raw.replace('"FY":0', '"FY":9007199254740993')
  expect(JSON.parse(left)).toEqual(JSON.parse(right))
  const compared = compareRcScenarioInputs(left, right)
  expect(compared).toMatchObject({ status: 'available', rawIdentical: false, precisionLimited: true, compatibility: 'unavailable' })
  expect(compared.changes).toContainEqual({ path: '/model/loads/0/components/FY', before: '9007199254740992', after: '9007199254740993', beforeClipped: false, afterClipped: false, kind: 'numeric_token' })
  expect(compareRcScenarioInputs(left, left)).toMatchObject({ rawIdentical: true, precisionLimited: true, compatibility: 'unavailable' })
})

test('captured input comparison distinguishes harmless numeric spelling, negative zero and actual decimal precision collisions', () => {
  const value = draft(); value.model.metadata = { amount: 0 }
  const raw = JSON.stringify(value), authored = (token: string) => raw.replace('"amount":0', `"amount":${token}`)
  for (const [a, b] of [['1.0', '1'], ['-0', '0'], ['1e-3', '0.001'], ['10e-1', '1']]) {
    const compared = compareRcScenarioInputs(authored(a), authored(b))
    expect(compared).toMatchObject({ rawIdentical: false, precisionLimited: false, compatibility: 'compatible' })
    expect(compared.changes).toEqual([{ path: '/model/metadata/amount', before: a, after: b, beforeClipped: false, afterClipped: false, kind: 'numeric_token' }])
  }
  const collision = compareRcScenarioInputs(authored('0.10000000000000001'), authored('0.1'))
  expect(collision).toMatchObject({ precisionLimited: true, compatibility: 'unavailable' })
  expect(collision.changes[0]).toMatchObject({ before: '0.10000000000000001', after: '0.1' })
  expect(compareRcScenarioInputs(authored('1e-999'), authored('0'))).toMatchObject({ precisionLimited: true, compatibility: 'unavailable' })
  expect(compareRcScenarioInputs(authored('1e999'), authored('0'))).toMatchObject({ status: 'invalid', compatibility: 'unavailable' })
})

test('captured input comparison preserves missing, null, zero, escaped paths and prototype-named authored keys', () => {
  const left = draft(), right = draft()
  left.model.metadata = { 'a/b~c': 0, presentNull: null }
  right.model.metadata = { addedZero: 0, presentNull: 0 }
  const compared = compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(right))
  expect(compared.changes).toEqual(expect.arrayContaining([
    expect.objectContaining({ path: '/model/metadata/a~1b~0c', before: '0', after: '(absent)' }),
    expect.objectContaining({ path: '/model/metadata/addedZero', before: '(absent)', after: '0' }),
    expect.objectContaining({ path: '/model/metadata/presentNull', before: 'null', after: '0' }),
  ]))
  left.model.metadata = {}; right.model.metadata = JSON.parse('{"__proto__":{},"constructor":0,"toString":0,"":0}')
  const special = compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(right))
  expect(special.changes).toEqual(expect.arrayContaining([
    expect.objectContaining({ path: '/model/metadata/__proto__', before: '(absent)', after: '{}' }),
    expect.objectContaining({ path: '/model/metadata/constructor', before: '(absent)', after: '0' }),
    expect.objectContaining({ path: '/model/metadata/toString', before: '(absent)', after: '0' }),
    expect.objectContaining({ path: '/model/metadata/', before: '(absent)', after: '0' }),
  ]))
})

test('captured input comparison marks cell and row truncation and refuses bounded or invalid inputs explicitly', () => {
  const left = draft(), right = draft()
  left.model.metadata = { value: 'a'.repeat(300) }; right.model.metadata = { value: 'b'.repeat(300) }
  const clipped = compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(right))
  expect(clipped.changes[0]).toMatchObject({ beforeClipped: true, afterClipped: true })
  expect(clipped.changes[0].before).toHaveLength(240)
  left.model.metadata = {}; right.model.metadata = { a: 0, b: 1, c: 2 }
  expect(compareRcScenarioInputs(JSON.stringify(left), JSON.stringify(right), 2)).toMatchObject({ truncated: true, changes: [expect.anything(), expect.anything()] })
  const raw = JSON.stringify(left)
  expect(compareRcScenarioInputs(null, raw)).toMatchObject({ status: 'missing', rawIdentical: null, compatibility: 'unavailable' })
  const missingProjection = structuredClone(left); delete missingProjection.model.loads
  expect(compareRcScenarioInputs(raw, JSON.stringify(missingProjection))).toMatchObject({ status: 'invalid', compatibility: 'unavailable' })
  for (const invalid of ['', '{}', '{"a":1,"a":2}', raw.replace('"case_id":', '"case_id":"duplicate","case_id":')]) expect(compareRcScenarioInputs(raw, invalid)).toMatchObject({ status: 'invalid', compatibility: 'unavailable' })
  expect(compareRcScenarioInputs(raw, ' '.repeat(RC_INPUT_COMPARISON_BYTES + 1))).toMatchObject({ status: 'limited', compatibility: 'unavailable', truncated: true })
  right.model.metadata = Array.from({ length: 20001 }, () => 0)
  expect(compareRcScenarioInputs(raw, JSON.stringify(right)).status).toBe('limited')
  right.model.metadata = { deeply: 0 }
  for (let count = 0; count < 50; count++) right.model.metadata = { child: right.model.metadata }
  expect(compareRcScenarioInputs(raw, JSON.stringify(right)).status).toBe('limited')
  expect(compareRcScenarioInputs(raw, raw.replace('"metadata":{}', `"metadata":{"number":${'1'.repeat(257)}}`)).status).toBe('limited')
})

test('matches actual entity/component/unit keys across row order and preserves missing values', () => {
  const baseline = summary(), variant = structuredClone(baseline)
  variant.values.reverse()
  const moved = variant.values.find(row => row.kind === 'member_force' && row.component === 'i:FY')!
  moved.value = 27
  const missing = variant.values.find(row => row.kind === 'reaction')!
  variant.values = variant.values.filter(row => row.key !== missing.key)
  const comparison = compareRcScenarios(baseline, variant)
  expect(comparison.compatible).toBe(true)
  expect(comparison.rows.find(row => row.key === moved.key)?.delta).toBe(7)
  expect(comparison.rows.find(row => row.key === missing.key)).toMatchObject({ baseline: 20, variant: null, delta: null })
  expect(JSON.stringify(baseline)).not.toContain('confidential_unused')
  expect(baseline.values.some(row => row.kind === 'displacement' && row.unit === 'rad')).toBe(true)
})

test('geometry/material designs can differ but loading, supports, source and target occurrence order cannot', () => {
  const input = draft(), changed = structuredClone(input)
  changed.model.sections[0].width_m = 0.6
  changed.model.nodes[1].coordinates[0] = 4
  expect(rcScenarioCompatibility(changed)).toBe(rcScenarioCompatibility(input))
  for (const mutate of [
    (value: any) => { value.source_revision = 'b'.repeat(40) },
    (value: any) => { value.config.targets_m.reverse() },
    (value: any) => { value.config.control_global_dof = 3 },
    (value: any) => { value.model.loads[0].components.FY = -99 },
    (value: any) => { value.model.supports[0].dofs.pop() },
    (value: any) => { value.model.elements[0].nodes.reverse() },
  ]) {
    const variant = structuredClone(input); mutate(variant)
    const left = summary(), right = structuredClone(left)
    right.compatibility = rcScenarioCompatibility(variant)
    expect(compareRcScenarios(left, right)).toMatchObject({ compatible: false, rows: [] })
  }
})

test('repeated targets retain their occurrence order and export includes unknown cases and original bindings', () => {
  const baseline = summary(), variant = structuredClone(baseline)
  baseline.targetsM = [1e-6, 2e-6, 1e-6]; baseline.targetIndex = 2; baseline.targetM = 1e-6
  expect(compareRcScenarios(baseline, variant).compatible).toBe(false)
  const parsed = JSON.parse(exportRcScenarios([
    { name: 'baseline', status: 'succeeded', summary: variant }, { name: 'failure', status: 'failed', jobId: 'job-failed' },
  ], variant.bindings.jobId))
  expect(parsed.scenarios).toHaveLength(2)
  expect(parsed.scenarios[0].summary.bindings).toEqual(variant.bindings)
  expect(parsed.scenarios[1]).toEqual({ name: 'failure', status: 'failed', jobId: 'job-failed' })
  expect(parsed.scenarios[0].summary.recordedPhaseWallSeconds).toBeNull()
  expect(() => exportRcScenarios(Array.from({ length: 5 }, () => ({ name: 'x', status: 'failed' })), null)).toThrow('export_limit')
})

test('recorded phase wall time requires complete paired work and retains unknown totals', () => {
  const value = summary(); value.unknownWork = false
  const diagnostics: any = {
    jobId: value.bindings.jobId, requestHash: value.bindings.requestHash, unknownWork: false, pending: [],
    analysisWallSeconds: 1, verificationWallSeconds: 2,
    invocations: ['analysis', 'verification'].map(phase => ({ phase, status: 'returned', unavailable_execution_work: false,
      chunk_request_hash: 'chunk', completed_before: 0, completed_after: 2, restart_input_sha256: null })),
  }
  expect(rcScenarioRecordedWallSeconds(value, diagnostics)).toBe(3)
  for (const mutate of [
    (row: any) => { row.unknownWork = true }, (row: any) => { row.pending = [3] },
    (row: any) => { row.verificationWallSeconds = null }, (row: any) => { row.invocations.pop() },
    (row: any) => { row.invocations[1].chunk_request_hash = 'other' }, (row: any) => { row.requestHash = 'other' },
  ]) {
    const changed = structuredClone(diagnostics); mutate(changed)
    expect(rcScenarioRecordedWallSeconds(value, changed)).toBeNull()
  }
})

test('uncertain POST retries the exact original key/bytes, then known jobs use GET only', async () => {
  const intent = captureRcScenario(draft(), 'first', 'uncertain-1'), queued = job(intent.serialized)
  const posts: Array<{ bytes: number[]; key: string }> = []
  let reads = 0
  const transport = {
    submit: async (bytes: Uint8Array, key: string) => {
      posts.push({ bytes: [...bytes], key })
      return posts.length === 1 ? json({}, 503) : json(queued)
    },
    getRequest: async () => new Response(intent.serialized, { headers: { 'Content-Type': 'application/json' } }),
    getJob: async () => { reads++; return json(job(intent.serialized, 'failed')) },
    verifyAuthorizationScope: async () => {},
  } as unknown as RcJobTransport
  const signal = new AbortController().signal, onJob = () => {}
  await expect(runRcScenario(transport, intent, { signal, onJob, maximumPolls: 0 })).rejects.toBeInstanceOf(RcScenarioUnconfirmedError)
  const accepted = await runRcScenario(transport, intent, { signal, onJob, maximumPolls: 0 })
  expect(posts).toHaveLength(2); expect(posts[0]).toEqual(posts[1])
  expect(await runRcScenario(transport, intent, { signal, onJob, existingJob: accepted, maximumPolls: 1, pollIntervalMs: 0 })).toMatchObject({ status: 'failed' })
  expect(posts).toHaveLength(2); expect(reads).toBe(1)
})

test('refuses scope changes and altered stored request without publishing a comparison', async () => {
  const intent = captureRcScenario(draft(), 'first', 'binding-1'), accepted = job(intent.serialized)
  const transport = { getRequest: async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }), verifyAuthorizationScope: async () => {} } as unknown as RcJobTransport
  await expect(runRcScenario(transport, intent, { signal: new AbortController().signal, onJob: () => {}, existingJob: accepted, maximumPolls: 0 })).rejects.toThrow('request byte length mismatch')
  const noScope = { getRequest: async () => new Response(intent.serialized, { headers: { 'Content-Type': 'application/json' } }), verifyAuthorizationScope: async () => { throw new Error('job_authorization_scope_changed') } } as unknown as RcJobTransport
  await expect(runRcScenario(noScope, intent, { signal: new AbortController().signal, onJob: () => {}, existingJob: accepted, maximumPolls: 0 })).rejects.toThrow('scope_changed')
  for (const message of ['job_api_http_401', 'rc_result_HTTP_403', 'job_authorization_scope_changed']) expect(rcScenarioAuthorizationFailure(new Error(message))).toBe(true)
  expect(rcScenarioAuthorizationFailure(new Error('job_api_http_503'))).toBe(false)
})

test('browser captures without executing; uncertain submission stops the queue and retains the same retry intent', async ({ page }) => {
  const posts: Array<{ body: string; key: string }> = []
  await page.addInitScript(() => {
    ;(window as any).__rcScenarioTenant = 'a'
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobAuthorization: () => ({ tenantId: (window as any).__rcScenarioTenant, bearerToken: 'example-test-token' }) }
  })
  await page.route('**/v1/jobs', async route => {
    if (route.request().method() === 'POST') {
      posts.push({ body: route.request().postData()!, key: route.request().headers()['idempotency-key'] })
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"secret":"DO-NOT-DISPLAY"}' })
    } else await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await page.getByText('Submit a new RC input', { exact: true }).click()
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(draft()))
  const panel = page.locator('[data-rc-scenario-comparison]')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  await panel.getByLabel('Scenario name', { exact: true }).fill('Second design')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  expect(posts).toEqual([])
  await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
  await expect(panel).toContainText('Submission outcome is unconfirmed')
  expect(posts).toHaveLength(1)
  await expect(panel.getByRole('button', { name: 'Run captured designs', exact: true })).toBeDisabled()
  const inputs = panel.locator('[data-rc-scenario-input-comparison]')
  await expect(inputs.getByLabel('Input baseline design', { exact: true }).locator('option')).toContainText(['Select a captured input', 'Design 1 (unconfirmed)', 'Second design (captured)'])
  await expect(inputs.locator('[data-rc-input-identity]')).toContainText('exactly identical')
  const changed = draft(); changed.model.sections[0].width_m = 0.8
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(changed))
  await expect(inputs.locator('[data-rc-input-identity]')).toContainText('exactly identical')
  expect(posts).toHaveLength(1)
  await panel.getByRole('button', { name: 'Retry same submission for Design 1', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[0]).toEqual(posts[1])
  await expect(panel).not.toContainText('DO-NOT-DISPLAY')
  await expect(panel).toContainText('Second design')
  const downloadEvent = page.waitForEvent('download')
  await panel.getByRole('button', { name: 'Export scenario JSON', exact: true }).click()
  const download = await downloadEvent, path = await download.path()
  const exported = JSON.parse(await readFile(path!, 'utf8'))
  expect(exported.scenarios.map((row: any) => row.status)).toEqual(['unconfirmed', 'captured'])
  expect(exported.scenarios.every((row: any) => row.summary === undefined)).toBe(true)
  await page.evaluate(() => { (window as any).__rcScenarioTenant = 'b' })
  await expect(panel).toContainText('Authorization changed')
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
})


test('browser compares original captured numeric tokens without posting or changing saved numerical selections', async ({ page }) => {
  const posts: string[] = []
  page.on('request', outgoing => { if (outgoing.method() === 'POST') posts.push(outgoing.url()) })
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs' } })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await page.getByText('Submit a new RC input', { exact: true }).click()
  const request = draft(); request.model.metadata = { native_integer: 0, native_float: 1 }
  const left = JSON.stringify(request).replace('"native_integer":0', '"native_integer":9007199254740992').replace('"native_float":1', '"native_float":1.0')
  const right = JSON.stringify(request).replace('"native_integer":0', '"native_integer":9007199254740993')
  const raw = page.getByLabel('Typed RC request JSON', { exact: true })
  const panel = page.locator('[data-rc-scenario-comparison]')
  await raw.fill(left)
  await panel.getByLabel('Scenario name', { exact: true }).fill('Input A')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  await raw.fill(right)
  await panel.getByLabel('Scenario name', { exact: true }).fill('Input B')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  const inputs = panel.locator('[data-rc-scenario-input-comparison]')
  const integer = inputs.locator('[data-rc-input-change="/model/metadata/native_integer"]')
  const float = inputs.locator('[data-rc-input-change="/model/metadata/native_float"]')
  await expect(integer.locator('td').nth(1)).toHaveText('9007199254740992')
  await expect(integer.locator('td').nth(2)).toHaveText('9007199254740993')
  await expect(float.locator('td').nth(1)).toHaveText('1.0')
  await expect(float.locator('td').nth(2)).toHaveText('1')
  await expect(inputs.locator('[data-rc-input-precision]')).toBeVisible()
  await expect(inputs.locator('[data-rc-input-compatibility]')).toContainText('unavailable')
  // Current draft is a third design, and is deliberately not captured.
  request.model.sections[0].width_m = 0.9
  await raw.fill(JSON.stringify(request))
  await expect(integer.locator('td').nth(2)).toHaveText('9007199254740993')
  await expect(inputs.locator('[data-rc-input-change="/model/sections/0/width_m"]')).toHaveCount(0)
  const ids = await panel.locator('[data-scenario-id]').evaluateAll(rows => rows.map(row => row.getAttribute('data-scenario-id')!))
  await inputs.getByLabel('Input compared design', { exact: true }).selectOption(ids[0])
  await expect(inputs.locator('[data-rc-input-identity]')).toContainText('exactly identical')
  await inputs.getByLabel('Input baseline design', { exact: true }).selectOption(ids[1])
  await expect(integer.locator('td').nth(1)).toHaveText('9007199254740993')
  await expect(integer.locator('td').nth(2)).toHaveText('9007199254740992')
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
  const download = await pending, project = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(project.scenarios.map((row: any) => row.intent.serialized)).toEqual([left, right])
  expect(project.baselineId).toBeNull(); expect(project.variantId).toBeNull()
  expect(project.draft).toBe(JSON.stringify(request))
  expect(posts).toEqual([])
})
