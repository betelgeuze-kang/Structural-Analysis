import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import {
  compareRcScenarios, exportRcScenarios, fixedRcScenarioSummary,
  rcScenarioAuthorizationFailure, rcScenarioCompatibility, rcScenarioRecordedWallSeconds, type RcScenarioSummary,
} from '../../src/workbench-v2/model/rcScenarioComparison'
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
  const changed = draft(); changed.model.sections[0].width_m = 0.8
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(JSON.stringify(changed))
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
