import { expect, test, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const collectionUrl = new URL('/v1/jobs', baseUrl).href
const jobId = `job_${'1'.repeat(32)}`
const hash = (text: string) => `sha256:${createHash('sha256').update(text).digest('hex')}`
const privateToken = 'project-browser-credential-never-save'
const primaryKey = 'rc-ui-7d56a272-83c4-4bc5-b242-714ec879feaa'
type ObservedPost = { body: string; key: string }
type ReadMode = 'failed' | 'missing' | 'mismatch'

function nativeDraft(): string {
  const value = createRcEditorExample('a'.repeat(40))
  value.model.metadata = { native_float: 1, native_integer: 0 }
  return JSON.stringify(value, null, 2).replace('"native_float": 1', '"native_float": 1.0')
    .replace('"native_integer": 0', '"native_integer": 9007199254740993')
}
function storedJob(serialized: string, identity = jobId, attempt = 1): WorkbenchJobView {
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: identity, status: 'failed', revision: 1, attempt,
    progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:01Z', lease_expires_at: null,
    error_code: 'execution_attempt_budget_exhausted', can_resume: false,
    request: { role: 'request', content_hash: hash(serialized), byte_length: Buffer.byteLength(serialized), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'Stub HTTP project-file workflow test only.', terminal_event_hash: `sha256:${'2'.repeat(64)}`,
  }
}
function project(serialized = nativeDraft()) {
  return {
    schema: 'rc-workbench-project.v1', scope: { collectionUrl, tenantId: 'project-tenant' }, draft: serialized,
    submission: null as null | { serialized: string; idempotencyKey: string; job: null | { jobId: string; requestHash: string } },
    selectedJob: null as null | { jobId: string; requestHash: string },
    changedRun: null as null | { original: { jobId: string; requestHash: string }; child: null | { jobId: string; requestHash: string } },
    scenarios: [] as Array<{ intent: { id: string; name: string; serialized: string; idempotencyKey: string }; attempted: boolean; job: null | { jobId: string; requestHash: string } }>,
    baselineId: null as null | string, variantId: null as null | string,
  }
}
async function workspace(page: Page, options: {
  mode?: ReadMode; serialized?: string; postGate?: Promise<void>; jobReadGate?: Promise<void>; requestReadGate?: Promise<void>; initialJob?: boolean
  firstPostResult?: WorkbenchJobView; onPostSettled?: () => void
  records?: Record<string, { serialized: string; mode?: ReadMode; attempt?: number }>
} = {}) {
  const posts: ObservedPost[] = [], gets: string[] = []
  const serialized = options.serialized ?? nativeDraft()
  await page.addInitScript(({ privateToken }) => {
    ;(window as any).__rcProjectTenant = 'project-tenant'
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: '/v1/jobs',
      jobAuthorization: async () => {
        const tenantId = (window as any).__rcProjectTenant
        const split = (window as any).__rcProjectSplitAuthorization
        if (split && ++split.calls === split.blockedCall) {
          split.waiting = true
          await (window as any).__rcProjectSplitAuthorizationGate
          return { tenantId: 'project-tenant', bearerToken: privateToken }
        }
        const marker = (window as any).__rcProjectRestoreGateMarker
        if (marker && document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Typed RC request JSON"]')?.value.includes(marker)) {
          ;(window as any).__rcProjectRestoreWaiting = true
          await (window as any).__rcProjectRestoreAuthorizationGate
          if ((window as any).__rcProjectRestoreAuthorizationFailure) throw new Error('test project authorization unavailable')
        }
        await (window as any).__rcProjectAuthorizationGate
        return { tenantId, bearerToken: privateToken }
      },
    }
  }, { privateToken })
  await page.route('**/v1/jobs**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      posts.push({ body: request.postData()!, key: request.headers()['idempotency-key'] })
      const ordinal = posts.length
      if (options.postGate) await options.postGate
      try {
        return await route.fulfill(options.firstPostResult && ordinal === 1
          ? { status: 200, contentType: 'application/json', body: JSON.stringify(options.firstPostResult) }
          : { status: 503, contentType: 'application/json', body: '{"private":"response-body-never-save"}' })
      } finally { options.onPostSettled?.() }
    }
    gets.push(path)
    if (options.jobReadGate && path === `/v1/jobs/${jobId}`) await options.jobReadGate
    if (options.requestReadGate && path === `/v1/jobs/${jobId}/request`) await options.requestReadGate
    const matched = /^\/v1\/jobs\/(job_[0-9a-f]{32})(\/request)?$/.exec(path)
    const identity = matched?.[1]
    const record = identity ? options.records ? options.records[identity]
      : identity === jobId ? { serialized, mode: options.mode, attempt: 1 } : undefined : undefined
    if (record && record.mode !== 'missing' && !matched?.[2]) {
      const job = storedJob(record.serialized, identity!, record.attempt ?? 1)
      if (record.mode === 'mismatch') job.request.content_hash = `sha256:${'3'.repeat(64)}`
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(job) })
    }
    if (record && record.mode !== 'missing' && matched?.[2]) {
      return route.fulfill({ contentType: 'application/json', body: record.serialized })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
  await page.goto(`${baseUrl}/${options.initialJob ? `?rcJob=${jobId}` : ''}#/workbench-v2`)
  await expect(page.locator('[data-rc-project-file]')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  return { posts, gets }
}
async function revealDraft(page: Page): Promise<void> {
  const input = page.getByLabel('Typed RC request JSON', { exact: true })
  if (!await input.isVisible()) await page.getByText('Submit a new RC input', { exact: true }).click()
}
async function openProject(page: Page, content: unknown, replacement?: 'accept' | 'cancel'): Promise<void> {
  const input = page.getByLabel('Open RC project file', { exact: true })
  await expect(input).toBeEnabled()
  const confirmation = replacement ? page.waitForEvent('dialog').then(async dialog => {
    expect(dialog.type()).toBe('confirm')
    expect(dialog.message()).toContain('Replace it with the selected file')
    if (replacement === 'accept') await dialog.accept(); else await dialog.dismiss()
  }) : null
  await input.setInputFiles({
    name: 'saved-project.json', mimeType: 'application/json',
    buffer: Buffer.from(typeof content === 'string' ? content : JSON.stringify(content)),
  })
  if (confirmation) await confirmation
}
async function saveProject(page: Page): Promise<{ text: string; value: any }> {
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
  const download = await pending
  expect(download.suggestedFilename()).toBe('rc-workbench-project.json')
  const path = await download.path()
  expect(path).not.toBeNull()
  const text = await readFile(path!, 'utf8')
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  return { text, value: JSON.parse(text) }
}
function expectPrivateDataAbsent(text: string): void {
  expect(text).not.toContain(privateToken)
  expect(text).not.toContain('response-body-never-save')
  const keys: string[] = []
  function walk(value: unknown): void {
    if (!value || typeof value !== 'object') return
    for (const [key, child] of Object.entries(value)) { keys.push(key); walk(child) }
  }
  walk(JSON.parse(text))
  for (const forbidden of ['bearerToken', 'Authorization', 'authorization', 'headers', 'result', 'evidence', 'checkpoint', 'summary', 'curve']) {
    expect(keys).not.toContain(forbidden)
  }
}

function custodyProject() {
  const file = project(), serialized = file.draft
  file.scenarios = [
    { intent: { id: 'captured-design', name: 'Captured design', serialized, idempotencyKey: 'rc-scenario-captured-design' }, attempted: false, job: null },
    { intent: { id: 'uncertain-design', name: 'Uncertain design', serialized, idempotencyKey: 'rc-scenario-uncertain-design' }, attempted: true, job: null },
    { intent: { id: 'known-design', name: 'Known design', serialized, idempotencyKey: 'rc-scenario-known-design' }, attempted: true, job: { jobId, requestHash: hash(serialized) } },
  ]
  file.baselineId = 'known-design'; file.variantId = 'uncertain-design'
  return file
}

test('RC project same-account refresh retains captured, uncertain and known scenario custody', async ({ page }) => {
  const { posts, gets } = await workspace(page)
  const file = custodyProject()
  await openProject(page, file)
  const panel = page.locator('[data-rc-scenario-comparison]')
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(3)
  await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
  await expect(panel).toContainText('Authorization refreshed. Designs are retained')
  const saved = await saveProject(page)
  expect(saved.value.scenarios).toEqual(file.scenarios)
  expect(saved.value.baselineId).toBe(file.baselineId)
  expect(saved.value.variantId).toBe(file.variantId)
  expect(posts).toEqual([])
  expect(gets).toEqual([])
  expectPrivateDataAbsent(saved.text)
  await panel.getByRole('button', { name: 'Retry same submission for Uncertain design', exact: true }).click()
  await expect(panel).toContainText('Submission outcome is unconfirmed')
  expect(posts).toEqual([{ body: file.draft, key: file.scenarios[1].intent.idempotencyKey }])
  await panel.getByRole('button', { name: 'Refresh Known design', exact: true }).click()
  await expect(panel.locator('[data-scenario-id="known-design"]')).toContainText('No succeeded numerical result')
  expect(gets).toContain(`/v1/jobs/${jobId}`)
  expect(posts).toHaveLength(1)
  expect((await saveProject(page)).value.scenarios).toEqual(file.scenarios)
})

test('RC project cross-account refresh clears scenario custody and stored selections', async ({ page }) => {
  const { posts } = await workspace(page)
  const file = custodyProject()
  await openProject(page, file)
  const panel = page.locator('[data-rc-scenario-comparison]')
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(3)
  await page.evaluate(() => { (window as any).__rcProjectTenant = 'other-tenant' })
  await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  const saved = await saveProject(page)
  expect(saved.value.scope.tenantId).toBe('other-tenant')
  expect(saved.value.draft).toBe('')
  expect(saved.value.scenarios).toEqual([])
  expect(saved.value.baselineId).toBeNull()
  expect(saved.value.variantId).toBeNull()
  expect(posts).toEqual([])
})

test('RC project opening another file after same-account refresh replaces the prior scenario custody', async ({ page }) => {
  const { posts, gets } = await workspace(page)
  const first = custodyProject(), second = custodyProject()
  second.draft = second.draft.replace('"width_m": 0.4', '"width_m": 0.8')
  second.scenarios = second.scenarios.map((row, index) => ({
    ...row, intent: { ...row.intent, id: `second-${index}`, name: `Second design ${index}`, serialized: second.draft, idempotencyKey: `rc-scenario-second-${index}` },
    job: row.job ? { jobId: `job_${'4'.repeat(32)}`, requestHash: hash(second.draft) } : null,
  }))
  second.baselineId = 'second-2'; second.variantId = 'second-1'
  await openProject(page, first)
  const panel = page.locator('[data-rc-scenario-comparison]')
  await expect(panel.locator('[data-scenario-id="known-design"]')).toBeVisible()
  await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
  await expect(panel).toContainText('Authorization refreshed. Designs are retained')
  await openProject(page, second)
  await expect(panel.locator('[data-scenario-id="second-2"]')).toBeVisible()
  await expect(panel.locator('[data-scenario-id="known-design"]')).toHaveCount(0)
  const saved = (await saveProject(page)).value
  expect(saved.draft).toBe(second.draft)
  expect(saved.scenarios).toEqual(second.scenarios)
  expect(saved.baselineId).toBe(second.baselineId)
  expect(saved.variantId).toBe(second.variantId)
  expect(posts).toEqual([])
  expect(gets).toEqual([])
})

for (const authorizationFails of [false, true]) {
  test(`RC project account refresh ${authorizationFails ? 'clears a failed authorization' : 'continues a pending'} restore without mixing scenario custody`, async ({ page }) => {
    const { posts, gets } = await workspace(page)
    const first = custodyProject(), second = custodyProject()
    second.draft = second.draft.replace(/"case_id": "[^"]+"/, '"case_id": "refresh-race-B"')
    second.scenarios = second.scenarios.map((row, index) => ({
      ...row, intent: { ...row.intent, id: `pending-${index}`, name: `Pending design ${index}`, serialized: second.draft, idempotencyKey: `rc-scenario-pending-${index}` },
      job: row.job ? { jobId: `job_${'5'.repeat(32)}`, requestHash: hash(second.draft) } : null,
    }))
    second.baselineId = 'pending-2'; second.variantId = 'pending-1'
    await openProject(page, first)
    await revealDraft(page)
    const panel = page.locator('[data-rc-scenario-comparison]')
    const refresh = page.getByRole('button', { name: 'Refresh account and job', exact: true })
    await expect(panel.locator('[data-scenario-id="known-design"]')).toBeVisible()
    await page.evaluate(authorizationFails => {
      ;(window as any).__rcProjectRestoreGateMarker = '"case_id": "refresh-race-B"'
      ;(window as any).__rcProjectRestoreAuthorizationFailure = authorizationFails
      ;(window as any).__rcProjectRestoreAuthorizationGate = new Promise<void>(resolve => { (window as any).__rcReleaseProjectRestoreAuthorization = resolve })
    }, authorizationFails)
    try {
      await openProject(page, second)
      await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(second.draft)
      await expect.poll(() => page.evaluate(() => (window as any).__rcProjectRestoreWaiting === true)).toBe(true)
      await expect(panel.locator('[data-scenario-id="known-design"]')).toBeVisible()
      await expect(refresh).toBeEnabled()
      await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
      if (!authorizationFails) {
        await refresh.click()
        await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
        await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
      }
      expect(posts).toEqual([])
    } finally {
      await page.evaluate(() => { (window as any).__rcReleaseProjectRestoreAuthorization() })
    }
    if (authorizationFails) {
      await expect(panel).toContainText('Authorization changed or became unavailable')
      await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
      await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('')
      await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
      await page.evaluate(() => { (window as any).__rcProjectRestoreAuthorizationFailure = false })
      await expect(refresh).toBeEnabled()
      await refresh.click()
      await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
      await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
      await openProject(page, second)
    }
    await expect(panel.locator('[data-scenario-id="pending-2"]')).toBeVisible()
    await expect(panel.locator('[data-scenario-id="known-design"]')).toHaveCount(0)
    await expect(refresh).toBeEnabled()
    const saved = (await saveProject(page)).value
    expect(saved.draft).toBe(second.draft)
    expect(saved.scenarios).toEqual(second.scenarios)
    expect(saved.baselineId).toBe(second.baselineId)
    expect(saved.variantId).toBe(second.variantId)
    expect(posts).toEqual([])
    expect(gets).toEqual([])
  })
}

for (const changedTenant of [false, true]) {
  test(`RC project ${changedTenant ? 'cross' : 'same'}-account refresh aborts a queue awaiting authorization without losing scope custody`, async ({ page }) => {
    const { posts } = await workspace(page)
    await revealDraft(page)
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill(nativeDraft())
    const panel = page.locator('[data-rc-scenario-comparison]')
    await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
    await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
    const before = (await saveProject(page)).value
    await page.evaluate(() => {
      ;(window as any).__rcProjectAuthorizationGate = new Promise<void>(resolve => { (window as any).__rcReleaseProjectAuthorization = resolve })
    })
    try {
      await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
      await expect(panel.locator('[data-scenario-id]').first()).toContainText('submitting')
      if (changedTenant) await page.evaluate(() => { (window as any).__rcProjectTenant = 'other-tenant' })
      const refresh = page.getByRole('button', { name: 'Refresh account and job', exact: true })
      await refresh.click()
      await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
      await expect(panel.getByRole('button', { name: 'Capture current design', exact: true })).toBeDisabled()
      await refresh.click()
      expect(posts).toEqual([])
    } finally {
      await page.evaluate(() => { (window as any).__rcReleaseProjectAuthorization() })
    }
    await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
    const saved = (await saveProject(page)).value
    expect(posts).toEqual([])
    if (changedTenant) {
      expect(saved.scope.tenantId).toBe('other-tenant')
      expect(saved.scenarios).toEqual([])
      expect(saved.baselineId).toBeNull()
      expect(saved.variantId).toBeNull()
    } else {
      expect(saved.scenarios).toEqual(before.scenarios.map((row: any, index: number) => ({ ...row, attempted: index === 0 })))
      await expect(panel.locator('[data-scenario-id]').first()).toContainText('unconfirmed')
      await expect(panel.getByRole('button', { name: 'Run captured designs', exact: true })).toBeDisabled()
      await panel.getByRole('button', { name: 'Retry same submission for Design 1', exact: true }).click()
      await expect(panel).toContainText('Submission outcome is unconfirmed')
      expect(posts).toEqual([{ body: before.scenarios[0].intent.serialized, key: before.scenarios[0].intent.idempotencyKey }])
      expect((await saveProject(page)).value.scenarios).toEqual(saved.scenarios)
    }
  })
}

test('RC project same-account refresh aborts an in-flight POST and ignores its late known-job response', async ({ page }) => {
  let release!: () => void, settled = 0
  const postGate = new Promise<void>(resolve => { release = resolve })
  const serialized = nativeDraft()
  const { posts } = await workspace(page, { postGate, firstPostResult: storedJob(serialized), onPostSettled: () => { settled++ } })
  try {
    await revealDraft(page)
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill(serialized)
    const panel = page.locator('[data-rc-scenario-comparison]')
    await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
    await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
    const before = (await saveProject(page)).value
    await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
    await expect.poll(() => posts.length).toBe(1)
    await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
    await expect(panel).toContainText('Authorization refreshed. Designs are retained')
    await expect(panel.locator('[data-scenario-id]').first()).toContainText('unconfirmed')
    const retained = before.scenarios.map((row: any, index: number) => ({ ...row, attempted: index === 0 }))
    expect((await saveProject(page)).value.scenarios).toEqual(retained)
    release()
    await expect.poll(() => settled).toBe(1)
    expect((await saveProject(page)).value.scenarios).toEqual(retained)
    expect(posts).toEqual([{ body: serialized, key: before.scenarios[0].intent.idempotencyKey }])
    await expect(panel.getByRole('button', { name: 'Run captured designs', exact: true })).toBeDisabled()
    await panel.getByRole('button', { name: 'Retry same submission for Design 1', exact: true }).click()
    await expect(panel).toContainText('Submission outcome is unconfirmed')
    expect(posts).toHaveLength(2)
    expect(posts[1]).toEqual(posts[0])
    expect((await saveProject(page)).value.scenarios).toEqual(retained)
  } finally { release() }
})

test('RC project restores exact draft and captured/uncertain scenarios without running them', async ({ page }) => {
  const { posts } = await workspace(page)
  const original = nativeDraft()
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(original)
  const panel = page.locator('[data-rc-scenario-comparison]')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  await panel.getByLabel('Scenario name', { exact: true }).fill('Unexecuted design')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
  await expect(panel).toContainText('Submission outcome is unconfirmed')
  expect(posts).toHaveLength(1)
  const { text, value } = await saveProject(page)
  expect(value.schema).toBe('rc-workbench-project.v1')
  expect(value.scope).toEqual({ collectionUrl, tenantId: 'project-tenant' })
  expect(value.draft).toBe(original)
  expect(value.scenarios.map((row: any) => row.attempted)).toEqual([true, false])
  expect(value.scenarios.every((row: any) => row.intent.serialized === original && row.job === null)).toBe(true)
  expect(value.scenarios[0].intent.idempotencyKey).toBe(posts[0].key)
  expectPrivateDataAbsent(text)

  await page.reload()
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(0)
  await openProject(page, text)
  await revealDraft(page)
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(original)
  await expect(panel.locator('[data-scenario-id]')).toHaveCount(2)
  await expect(panel.getByRole('button', { name: 'Run captured designs', exact: true })).toBeDisabled()
  expect(posts).toHaveLength(1)
  const restored = await saveProject(page)
  expect(restored.value.scenarios).toEqual(value.scenarios)
  expect(restored.value.draft).toContain('"native_float": 1.0')
  expect(restored.value.draft).toContain('9007199254740993')
  await panel.getByRole('button', { name: 'Retry same submission for Design 1', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  await expect(panel).toContainText('Submission outcome is unconfirmed')
  expect(posts[1]).toEqual(posts[0])
  expectPrivateDataAbsent((await saveProject(page)).text)
})

test('RC project preserves an uncertain primary submission key and native bytes across reload', async ({ page }) => {
  const { posts } = await workspace(page)
  const original = nativeDraft()
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(original)
  await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  await expect(page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeEnabled()
  const saved = await saveProject(page)
  expect(saved.value.submission).toEqual({ serialized: original, idempotencyKey: posts[0].key, job: null })
  expectPrivateDataAbsent(saved.text)
  await page.reload()
  await openProject(page, saved.text)
  await revealDraft(page)
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(original)
  expect(posts).toHaveLength(1)
  await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[1]).toEqual(posts[0])
})

for (const mode of ['failed', 'missing', 'mismatch'] as const) {
  test(`RC project known scenario ${mode} refresh never falls back to a new submission`, async ({ page }) => {
    const serialized = nativeDraft(), file = project(serialized)
    const ref = { jobId, requestHash: hash(serialized) }
    file.scenarios = [{ intent: { id: 'saved-one', name: 'Saved design', serialized, idempotencyKey: 'rc-scenario-saved-one' }, attempted: true, job: ref }]
    file.baselineId = 'saved-one'; file.variantId = 'saved-one'
    const { posts, gets } = await workspace(page, { mode, serialized })
    await openProject(page, file)
    const row = page.locator('[data-scenario-id="saved-one"]')
    await expect(row).toContainText('Saved design')
    expect(posts).toEqual([])
    const refresh = row.getByRole('button', { name: 'Refresh Saved design', exact: true })
    await refresh.click()
    await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(0)
    if (mode === 'failed') {
      await expect(row).toContainText('No succeeded numerical result')
      await expect(refresh).toHaveCount(0)
    } else {
      await expect(refresh).toBeEnabled()
      await expect(row).toContainText('unavailable')
      await refresh.click()
      await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(1)
      await expect(refresh).toBeEnabled()
    }
    expect(posts).toEqual([])
    const saved = await saveProject(page)
    expect(saved.value.scenarios[0].job).toEqual(ref)
    expectPrivateDataAbsent(saved.text)
  })

  test(`RC project known primary ${mode} remains bound to its stored job on explicit submit`, async ({ page }) => {
    const serialized = nativeDraft(), file = project(serialized)
    const ref = { jobId, requestHash: hash(serialized) }
    file.submission = { serialized, idempotencyKey: primaryKey, job: ref }
    const { posts, gets } = await workspace(page, { mode, serialized })
    await openProject(page, file)
    await revealDraft(page)
    await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(serialized)
    expect(posts).toEqual([])
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(0)
    await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
    expect(posts).toEqual([])
    const readCount = gets.filter(path => path === `/v1/jobs/${jobId}`).length
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(readCount)
    await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
    expect(posts).toEqual([])
    const saved = await saveProject(page)
    expect(saved.value.submission).toEqual(file.submission)
    expectPrivateDataAbsent(saved.text)
  })
}

test('RC project rejects corrupt, unsupported and other-scope files without replacing current inputs', async ({ page }) => {
  const { posts } = await workspace(page)
  const original = nativeDraft()
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(original)
  const panel = page.locator('[data-rc-scenario-comparison]')
  await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
  const before = await saveProject(page)
  const mutations: Array<[string, unknown]> = [
    ['invalid JSON', '{'],
    ['unsupported schema', { ...project(), schema: 'rc-workbench-project.v999' }],
    ['other tenant', { ...project(), scope: { collectionUrl, tenantId: 'other-tenant' } }],
    ['other collection', { ...project(), scope: { collectionUrl: new URL('/other/v1/jobs', baseUrl).href, tenantId: 'project-tenant' } }],
    ['result injection', { ...project(), result: { invented: true } }],
  ]
  for (const [label, candidate] of mutations) {
    await test.step(label, async () => {
      await openProject(page, candidate)
      await expect(page.locator('[data-rc-project-file-message]')).toContainText(/invalid|unsupported|mismatch|scope|could not|unavailable|does not|rejected/i)
      await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(original)
      await expect(panel.locator('[data-scenario-id]')).toHaveCount(1)
      const after = await saveProject(page)
      expect(after.value.draft).toBe(before.value.draft)
      expect(after.value.scenarios).toEqual(before.value.scenarios)
      expect(posts).toEqual([])
    })
  }
})

test('RC project file actions require applying or undoing structured edits', async ({ page }) => {
  const { posts } = await workspace(page)
  await revealDraft(page)
  const original = nativeDraft()
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(original)
  await page.locator('[data-rc-editor-field="/case_id"]').fill('locally-edited-case')
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
  await expect(page.getByLabel('Open RC project file', { exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Undo local model changes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  await expect(page.getByLabel('Open RC project file', { exact: true })).toBeEnabled()
  expect((await saveProject(page)).value.draft).toBe(original)
  expect(posts).toEqual([])
})

for (const lane of ['primary', 'scenario'] as const) {
  test(`RC project file actions remain disabled while a ${lane} submission is in flight`, async ({ page }) => {
    let release!: () => void
    const postGate = new Promise<void>(resolve => { release = resolve })
    const { posts } = await workspace(page, { postGate })
    try {
      await revealDraft(page)
      await page.getByLabel('Typed RC request JSON', { exact: true }).fill(nativeDraft())
      if (lane === 'scenario') {
        const panel = page.locator('[data-rc-scenario-comparison]')
        await panel.getByRole('button', { name: 'Capture current design', exact: true }).click()
        await panel.getByRole('button', { name: 'Run captured designs', exact: true }).click()
      } else await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
      await expect.poll(() => posts.length).toBe(1)
      await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
      await expect(page.getByLabel('Open RC project file', { exact: true })).toBeDisabled()
    } finally { release() }
    await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
    await expect(page.getByLabel('Open RC project file', { exact: true })).toBeEnabled()
    expect(posts).toHaveLength(1)
  })
}

test('RC project retains a missing selected job through save and reopen', async ({ page }) => {
  const file = project(), ref = { jobId, requestHash: hash(file.draft) }
  file.selectedJob = ref
  const { posts, gets } = await workspace(page, { mode: 'missing' })
  await openProject(page, file)
  await revealDraft(page)
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(file.draft)
  await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(0)
  await expect(page.locator('[data-rc-workflow-error]')).toContainText('unavailable')
  const saved = await saveProject(page)
  expect(saved.value.selectedJob).toEqual(ref)
  expect(saved.value.draft).toBe(file.draft)
  expect(posts).toEqual([])
  await page.reload()
  await openProject(page, saved.text)
  await expect(page.getByLabel('Saved RC job ID', { exact: true })).toHaveValue(jobId)
  await expect(page.locator('[data-rc-workflow-error]')).toContainText('unavailable')
  expect((await saveProject(page)).value.selectedJob).toEqual(ref)
  expect(posts).toEqual([])
})

for (const missing of ['original', 'child'] as const) {
  test(`RC project preserves unavailable changed-run references when the ${missing} job is missing`, async ({ page }) => {
    const original = nativeDraft(), childId = `job_${'4'.repeat(32)}`
    const child = original.replace('"width_m": 0.4', '"width_m": 0.8')
    const file = project(child)
    file.changedRun = { original: { jobId, requestHash: hash(original) }, child: { jobId: childId, requestHash: hash(child) } }
    const { posts, gets } = await workspace(page, {
      records: { [jobId]: { serialized: original, attempt: 0, mode: missing === 'original' ? 'missing' : 'failed' } },
    })
    await openProject(page, file)
    await revealDraft(page)
    await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(child)
    const unavailable = page.locator('[data-rc-project-unverified-relation]')
    await expect(unavailable).toContainText(jobId)
    await expect(unavailable).toContainText(childId)
    await expect(page.locator('[data-rc-changed-run]')).toHaveCount(0)
    if (missing === 'child') {
      expect(gets).toContain(`/v1/jobs/${jobId}/request`)
      expect(gets).toContain(`/v1/jobs/${childId}`)
    }
    const saved = await saveProject(page)
    expect(saved.value.changedRun).toEqual(file.changedRun)
    expect(saved.value.draft).toBe(child)
    expectPrivateDataAbsent(saved.text)
    await page.reload()
    await openProject(page, saved.text)
    await expect(unavailable).toContainText(childId)
    expect((await saveProject(page)).value.changedRun).toEqual(file.changedRun)
    expect(posts).toEqual([])
  })
}

test('RC project fetches and checks both changed-run requests before showing their input differences', async ({ page }) => {
  const original = nativeDraft(), childId = `job_${'4'.repeat(32)}`
  const child = original.replace('"width_m": 0.4', '"width_m": 0.8')
  const file = project(child)
  file.changedRun = { original: { jobId, requestHash: hash(original) }, child: { jobId: childId, requestHash: hash(child) } }
  const { posts, gets } = await workspace(page, {
    records: { [jobId]: { serialized: original, attempt: 0 }, [childId]: { serialized: child, attempt: 0 } },
  })
  await openProject(page, file)
  await revealDraft(page)
  const comparison = page.locator('[data-rc-changed-run]')
  await expect(comparison).toContainText(jobId)
  await expect(comparison).toContainText(childId)
  const row = comparison.getByRole('row').filter({ hasText: '/model/sections/0/width_m' })
  await expect(row).toContainText('0.4')
  await expect(row).toContainText('0.8')
  await expect(page.locator('[data-rc-project-unverified-relation]')).toHaveCount(0)
  for (const id of [jobId, childId]) {
    expect(gets).toContain(`/v1/jobs/${id}`)
    expect(gets).toContain(`/v1/jobs/${id}/request`)
  }
  const saved = await saveProject(page)
  expect(saved.value.changedRun).toEqual(file.changedRun)
  expectPrivateDataAbsent(saved.text)
  expect(posts).toEqual([])
})

test('RC project does not apply a file after the authenticated tenant changes during its asynchronous read', async ({ page }) => {
  const { posts } = await workspace(page)
  const original = nativeDraft(), incoming = project(original.replace('authored-rc-cantilever', 'pending-file-cannot-apply'))
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(original)
  await page.evaluate(() => {
    const host = window as any, originalRead = File.prototype.arrayBuffer
    const pending = new Promise<void>(resolve => { host.__rcProjectReleaseFile = resolve })
    File.prototype.arrayBuffer = async function () {
      const bytes = await originalRead.call(this)
      host.__rcProjectFileReadPending = true
      await pending
      return bytes
    }
  })
  try {
    await openProject(page, incoming)
    await expect.poll(() => page.evaluate(() => !!(window as any).__rcProjectFileReadPending)).toBe(true)
    await page.evaluate(() => {
      ;(window as any).__rcProjectTenant = 'other-tenant'
      ;(window as any).__rcProjectReleaseFile()
    })
    await expect(page.locator('[data-rc-workflow-error]')).toContainText(/Authentication|account/i)
    await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('')
    await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
    await expect(page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeDisabled()
    expect(posts).toEqual([])
  } finally {
    await page.evaluate(() => { (window as any).__rcProjectReleaseFile?.() })
  }
})

test('RC project opening a restored scenario retains its expected request hash on subsequent manual opens', async ({ page }) => {
  const serialized = nativeDraft(), file = project(serialized), ref = { jobId, requestHash: hash(serialized) }
  file.scenarios = [{ intent: { id: 'open-bound-design', name: 'Bound design', serialized, idempotencyKey: 'rc-scenario-open-bound-design' }, attempted: true, job: ref }]
  const { posts, gets } = await workspace(page, { mode: 'mismatch', serialized })
  await openProject(page, file)
  await page.locator('[data-scenario-id="open-bound-design"]').getByRole('button', { name: 'Open job', exact: true }).click()
  await expect(page.locator('[data-rc-workflow-error]')).toContainText('could not be verified')
  await expect(page.locator('[data-rc-input-summary="stored"]')).toHaveCount(0)
  await expect(page.locator('[data-rc-review], [data-rc-corotational-review]')).toHaveCount(0)
  expect(gets).not.toContain(`/v1/jobs/${jobId}/request`)
  const saved = await saveProject(page)
  expect(saved.value.selectedJob).toEqual(ref)
  expect(saved.value.scenarios[0].job).toEqual(ref)
  const reads = gets.filter(path => path === `/v1/jobs/${jobId}`).length
  await page.getByRole('button', { name: 'Open saved RC job', exact: true }).click()
  await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}`).length).toBeGreaterThan(reads)
  await expect(page.locator('[data-rc-workflow-error]')).toContainText('could not be verified')
  await expect(page.locator('[data-rc-input-summary="stored"]')).toHaveCount(0)
  await expect(page.locator('[data-rc-review], [data-rc-corotational-review]')).toHaveCount(0)
  expect(gets).not.toContain(`/v1/jobs/${jobId}/request`)
  expect((await saveProject(page)).value.selectedJob).toEqual(ref)
  expect(posts).toEqual([])
})

for (const state of ['uncertain', 'known'] as const) {
  test(`RC project identical request-file import retains a restored ${state} primary submission`, async ({ page }) => {
    const serialized = nativeDraft(), file = project(serialized)
    file.submission = { serialized, idempotencyKey: primaryKey, job: state === 'known' ? { jobId, requestHash: hash(serialized) } : null }
    const { posts, gets } = await workspace(page, { serialized, records: { [jobId]: { serialized, attempt: 0 } } })
    await openProject(page, file)
    await revealDraft(page)
    await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(serialized)
    await page.evaluate(() => {
      const host = window as any, originalRead = File.prototype.arrayBuffer
      File.prototype.arrayBuffer = async function () {
        const bytes = await originalRead.call(this)
        // Signal the task after the app has consumed the resolved file bytes.
        setTimeout(() => { host.__rcProjectIdenticalFileRead = true }, 0)
        return bytes
      }
    })
    await page.getByLabel('Choose RC request JSON file', { exact: true }).setInputFiles({
      name: 'same-request.json', mimeType: 'application/json', buffer: Buffer.from(serialized),
    })
    await expect.poll(() => page.evaluate(() => !!(window as any).__rcProjectIdenticalFileRead)).toBe(true)
    expect((await saveProject(page)).value.submission).toEqual(file.submission)
    expect(posts).toEqual([])
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    if (state === 'uncertain') {
      await expect.poll(() => posts.length).toBe(1)
      expect(posts[0]).toEqual({ body: serialized, key: primaryKey })
    } else {
      await expect.poll(() => gets.filter(path => path === `/v1/jobs/${jobId}/request`).length).toBeGreaterThan(0)
      await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
      expect(posts).toEqual([])
    }
    expect((await saveProject(page)).value.submission).toEqual(file.submission)
  })
}

test('RC project removing a restored captured design clears its baseline and variant selections', async ({ page }) => {
  const file = project(), id = 'remove-captured'
  file.scenarios = [{ intent: { id, name: 'Remove captured', serialized: file.draft, idempotencyKey: `rc-scenario-${id}` }, attempted: false, job: null }]
  file.baselineId = id; file.variantId = id
  const { posts } = await workspace(page)
  await openProject(page, file)
  const before = await saveProject(page)
  expect(before.value.baselineId).toBe(id)
  expect(before.value.variantId).toBe(id)
  await page.locator(`[data-scenario-id="${id}"]`).getByRole('button', { name: 'Remove Remove captured', exact: true }).click()
  await expect(page.locator('[data-scenario-id]')).toHaveCount(0)
  const saved = await saveProject(page)
  expect(saved.value.scenarios).toEqual([])
  expect(saved.value.baselineId).toBeNull()
  expect(saved.value.variantId).toBeNull()
  expect(saved.value.draft).toBe(file.draft)
  expect(posts).toEqual([])
})


test('RC project dirty state tracks incomplete drafts, captured custody and successful export or open baselines', async ({ page }) => {
  const { posts } = await workspace(page)
  const dirty = page.locator('[data-rc-project-dirty]')
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
  await revealDraft(page)
  const raw = page.getByLabel('Typed RC request JSON', { exact: true })
  await raw.fill('{ "unfinished":')
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  expect((await saveProject(page)).value.draft).toBe('{ "unfinished":')
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
  await expect(page.locator('[data-rc-project-file-message]')).toContainText('download initiated')
  await raw.fill(nativeDraft())
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  await saveProject(page)
  await page.getByRole('button', { name: 'Capture current design', exact: true }).click()
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  await saveProject(page)
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
  await page.getByRole('button', { name: 'Run captured designs', exact: true }).click()
  await expect(page.locator('[data-rc-scenario-comparison]')).toContainText('Submission outcome is unconfirmed')
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  expect((await saveProject(page)).value.scenarios[0].attempted).toBe(true)
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
  expect(posts).toHaveLength(1)
})

test('RC project replacement validates before prompting and cancellation retains native draft and scenario custody', async ({ page }) => {
  const { posts } = await workspace(page)
  const first = custodyProject(), second = project(nativeDraft().replace('authored-rc-cantilever', 'replacement-project'))
  await openProject(page, first)
  await expect(page.locator('[data-scenario-id]')).toHaveCount(3)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  await revealDraft(page)
  const changed = first.draft + '\n', raw = page.getByLabel('Typed RC request JSON', { exact: true })
  await raw.fill(changed)
  let dialogs = 0
  const unexpected = async (dialog: any) => { dialogs++; await dialog.dismiss() }
  page.on('dialog', unexpected)
  try {
    for (const invalid of ['{', { ...second, scope: { ...second.scope, tenantId: 'foreign' } }]) {
      await openProject(page, invalid)
      await expect(page.locator('[data-rc-project-file-message]')).toContainText('could not be opened')
      await expect(raw).toHaveValue(changed)
    }
  } finally { page.off('dialog', unexpected) }
  expect(dialogs).toBe(0)
  await openProject(page, second, 'cancel')
  await expect(page.locator('[data-rc-project-file-message]')).toContainText('opening cancelled')
  await expect(raw).toHaveValue(changed)
  await expect(page.locator('[data-scenario-id]')).toHaveCount(3)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
  const retained = await saveProject(page)
  expect(retained.value.scenarios).toEqual(first.scenarios)
  expect(retained.value.baselineId).toBe(first.baselineId)
  expect(retained.value.variantId).toBe(first.variantId)
  await raw.fill(changed + ' ')
  await openProject(page, second, 'accept')
  await expect(raw).toHaveValue(second.draft)
  await expect(page.locator('[data-scenario-id]')).toHaveCount(0)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  expect(posts).toEqual([])
})

for (const failure of ['blob', 'url', 'click'] as const) {
  test(`RC project failed ${failure} export keeps its changes unexported`, async ({ page }) => {
    const { posts } = await workspace(page)
    await revealDraft(page)
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill(nativeDraft())
    await page.evaluate(failure => {
      const host = window as any
      if (failure === 'blob') { const original = window.Blob; host.__rcRestoreExport = () => { window.Blob = original }; window.Blob = class { constructor() { throw new Error('test blob failure') } } as any }
      if (failure === 'url') { const original = URL.createObjectURL; host.__rcRestoreExport = () => { URL.createObjectURL = original }; URL.createObjectURL = () => { throw new Error('test URL failure') } }
      if (failure === 'click') { const original = HTMLAnchorElement.prototype.click; host.__rcRestoreExport = () => { HTMLAnchorElement.prototype.click = original }; HTMLAnchorElement.prototype.click = () => { throw new Error('test click failure') } }
    }, failure)
    try {
      await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
      await expect(page.locator('[data-rc-project-file-message]')).toContainText('could not be exported')
      await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
    } finally { await page.evaluate(() => { (window as any).__rcRestoreExport() }) }
    expect((await saveProject(page)).value.draft).toBe(nativeDraft())
    await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
    expect(posts).toEqual([])
  })
}

test('RC project clean baseline retains scenario custody through transient same-account authorization and tracks new draft edits', async ({ page }) => {
  const { posts } = await workspace(page), file = custodyProject()
  await openProject(page, file)
  await expect(page.locator('[data-scenario-id]')).toHaveCount(3)
  const dirty = page.locator('[data-rc-project-dirty]')
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
  await revealDraft(page)
  await page.evaluate(() => { (window as any).__rcProjectAuthorizationGate = new Promise<void>(resolve => { (window as any).__rcReleaseProjectAuthorization = resolve }) })
  try {
    await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
    await expect(page.locator('[data-scenario-id]')).toHaveCount(0)
    await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'false')
    await page.getByLabel('Typed RC request JSON', { exact: true }).fill('{ "new pending draft":')
    await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  } finally { await page.evaluate(() => { (window as any).__rcReleaseProjectAuthorization() }) }
  await expect(page.locator('[data-scenario-id]')).toHaveCount(3)
  await expect(dirty).toHaveAttribute('data-rc-project-dirty', 'true')
  const saved = await saveProject(page)
  expect(saved.value.scenarios).toEqual(file.scenarios)
  expect(saved.value.draft).toBe('{ "new pending draft":')
  expect(posts).toEqual([])
})

for (const blockedCall of [1, 2]) {
  test(`RC project clears private state when reauthorization callers disagree before delayed response ${blockedCall}`, async ({ page }) => {
    const { posts } = await workspace(page)
    await openProject(page, custodyProject())
    await expect(page.locator('[data-scenario-id]')).toHaveCount(3)
    await revealDraft(page)
    await page.evaluate(blockedCall => {
      const host = window as any
      host.__rcProjectSplitAuthorization = { calls: 0, blockedCall, waiting: false }
      host.__rcProjectSplitAuthorizationGate = new Promise<void>(resolve => { host.__rcReleaseSplitAuthorization = resolve })
      host.__rcProjectTenant = 'other-tenant'
    }, blockedCall)
    try {
      await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
      await expect.poll(() => page.evaluate(() => (window as any).__rcProjectSplitAuthorization.waiting)).toBe(true)
      await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('')
      await expect(page.locator('[data-scenario-id]')).toHaveCount(0)
      await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
    } finally { await page.evaluate(() => { (window as any).__rcReleaseSplitAuthorization() }) }
    const saved = await saveProject(page)
    expect(saved.value.scope.tenantId).toBe('other-tenant')
    expect(saved.value.draft).toBe(''); expect(saved.value.scenarios).toEqual([])
    expect(posts).toEqual([])
  })
}

test('RC project new primary key becomes dirty while POST is pending and explicit retry retains the exact key', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const { posts } = await workspace(page, { postGate: gate })
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(nativeDraft())
  await saveProject(page)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  try {
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect.poll(() => posts.length).toBe(1)
    await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
    const rejected = page.waitForEvent('dialog').then(async dialog => { expect(dialog.type()).toBe('confirm'); await dialog.dismiss() })
    await page.evaluate(() => { location.hash = '#/workbench' })
    await rejected
    await expect(page.locator('[data-rc-workflow="project"]')).toBeVisible()
  } finally { release() }
  await expect(page.getByRole('button', { name: 'Submit RC analysis', exact: true })).toBeEnabled()
  const saved = await saveProject(page)
  expect(saved.value.submission).toEqual({ serialized: nativeDraft(), idempotencyKey: posts[0].key, job: null })
  await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[1]).toEqual(posts[0])
})

test('RC project initial read-only link is clean but a selected reference arriving after export remains a new change', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const serialized = nativeDraft()
  const { posts } = await workspace(page, { initialJob: true, jobReadGate: gate, records: { [jobId]: { serialized, attempt: 0 } } })
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  await revealDraft(page)
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill('{ "saved before read":')
  try {
    const early = await saveProject(page)
    expect(early.value.selectedJob).toBeNull()
    await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  } finally { release() }
  await expect(page.locator('[data-rc-input-summary="stored"]')).toBeVisible()
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
  const later = await saveProject(page)
  expect(later.value.selectedJob).toEqual({ jobId, requestHash: hash(serialized) })
  expect(later.value.draft).toBe('{ "saved before read":')
  expect(posts).toEqual([])
})

test('RC project restored uncertain submission becomes dirty as soon as a job reference arrives before binding read completes', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const serialized = nativeDraft(), file = project(serialized)
  file.submission = { serialized, idempotencyKey: primaryKey, job: null }
  const { posts, gets } = await workspace(page, {
    requestReadGate: gate, firstPostResult: storedJob(serialized, jobId, 0),
    records: { [jobId]: { serialized, attempt: 0 } },
  })
  await openProject(page, file)
  await revealDraft(page)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  try {
    await page.getByRole('button', { name: 'Submit RC analysis', exact: true }).click()
    await expect.poll(() => gets.includes(`/v1/jobs/${jobId}/request`)).toBe(true)
    expect(posts).toEqual([{ body: serialized, key: primaryKey }])
    await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
    page.once('dialog', async dialog => { expect(dialog.type()).toBe('confirm'); await dialog.dismiss() })
    await page.locator('[data-wb2-legacy-link]').click()
    await expect(page.locator('[data-rc-workflow="project"]')).toBeVisible()
  } finally { release() }
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  const saved = await saveProject(page)
  expect(saved.value.submission).toEqual({ serialized, idempotencyKey: primaryKey, job: { jobId, requestHash: hash(serialized) } })
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  expect(posts).toHaveLength(1)
})
