import { expect, test, type Locator, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { buildingFixtureBytes } from './buildingMemberFixture'
import { buildingRevisionResultFixture } from './buildingRevisionResultFixture'

const origin = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:5128'
type Fixture = Awaited<ReturnType<typeof buildingRevisionResultFixture>>
const bytes = (value: unknown): Buffer => Buffer.from(buildingFixtureBytes(value))
const panel = (page: Page): Locator => page.locator('[data-building-revision-result]')
async function file(page: Page, label: string, buffer: Buffer | Uint8Array, name = 'synthetic-contract-data.json'): Promise<void> {
  await page.getByLabel(label, { exact: true }).setInputFiles({ name, mimeType: 'application/json', buffer: Buffer.from(buffer) })
}
async function offline(page: Page): Promise<string[]> {
  await page.addInitScript(() => {
    const host = window as any; host.__buildingLinkedAuthCalls = 0; host.__buildingLinkedOversizeReads = 0
    host.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: '/v1/jobs', jobStatusUrl: '/v1/jobs/unavailable', nativeFrameSubmissionUrl: '/v1/native/jobs',
      jobAuthorization: async () => { host.__buildingLinkedAuthCalls++; throw new Error('no_service_access') },
    }
    const original = File.prototype.arrayBuffer
    File.prototype.arrayBuffer = function () {
      if (this.name.startsWith('oversized-')) host.__buildingLinkedOversizeReads++
      return original.call(this)
    }
  })
  const calls: string[] = []
  await page.route('**/v1/**', async route => { calls.push(route.request().url()); await route.abort() })
  await page.goto(`${origin}/#/building-review`)
  await expect(panel(page)).toBeVisible()
  return calls
}
async function openDraft(page: Page, f: Fixture): Promise<void> {
  await file(page, 'Import saved load revision draft', f.draftBytes)
  await expect(page.locator('[data-building-load-status]')).toContainText('Opened the saved revision draft')
  await page.getByRole('button', { name: 'Validate load revision', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('Validated this exact load revision')
}
async function attach(page: Page, f: Fixture): Promise<void> {
  await page.getByLabel('Expected target result load source', { exact: true }).selectOption('load_combination:COMB1')
  await file(page, 'Stored target ResultIR file', f.resultBytes)
  await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).click()
  await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('Attached the stored result')
}
async function download(page: Page, label: string): Promise<Buffer> {
  const event = page.waitForEvent('download')
  await panel(page).getByRole('button', { name: label, exact: true }).click()
  return readFileSync((await (await event).path())!)
}

test('a stored target result links explicit member IDs and reopens from one self-contained file without service access', async ({ page, browser }, testInfo) => {
  const f = await buildingRevisionResultFixture(), calls = await offline(page)
  await openDraft(page, f); await attach(page, f)
  const view = panel(page)
  await expect(view.locator('[data-building-revision-result-identity]')).toContainText('synthetic.revision.result')
  await expect(view.locator('[data-building-revision-result-identity]')).toContainText('COMB1')
  await expect(view.locator('[data-building-revision-result-identity]')).toContainText('STORED_RESULT_FILE_CONSISTENT / UNVERIFIED / NOT_REVIEWED')
  await expect(view.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
  await expect(view.locator('[data-building-physical-members]')).toContainText('PHYSICAL_C12')
  await expect(view.locator('[data-building-physical-members]')).toContainText('UNMAPPED')
  await expect(view.locator('[data-building-element="E2"][data-building-end="i"] [data-building-component="FX"]')).toHaveText('-701.25')
  await expect(page.locator('[data-building-load-target]')).toContainText('NOT_RUN / NOT_REVIEWED')
  const attachment = await download(page, 'Export linked revision result')
  const mapping = await download(page, 'Export linked result member mapping'), review = await download(page, 'Export linked result member review')
  const lineage = await download(page, 'Export linked result lineage'), model = await download(page, 'Export linked result target ModelIR')
  expect(await download(page, 'Export exact linked ResultIR')).toEqual(Buffer.from(f.resultBytes))
  const mapped = JSON.parse(mapping.toString()), reviewed = JSON.parse(review.toString()), linked = JSON.parse(lineage.toString())
  expect(mapped.members).toEqual(f.fixture.mapping.members)
  expect(mapped.bindings).toMatchObject({ ...f.compiled.targetIdentity, result_id: f.result.result_id, result_hash: f.result.result_hash })
  expect(reviewed.rows.map((row: any) => row.force_n_nm)).toEqual(f.result.members.flatMap(row => [row.end_i_force_n_nm, row.end_j_force_n_nm]))
  expect(reviewed.rows.every((row: any) => row.review_status === 'NOT_REVIEWED')).toBe(true)
  expect(linked).toMatchObject({ attachment_status: 'STORED_RESULT_FILE_CONSISTENT', result_origin: 'UNVERIFIED', execution_status: 'NOT_VERIFIED', comparison_status: 'NOT_COMPUTED', compilation_analysis_status: 'NOT_RUN', review_status: 'NOT_REVIEWED' })
  expect(JSON.parse(model.toString())).toEqual(f.compiled.modelIr)
  for (const [name, body] of Object.entries({
    'synthetic-parent.model-ir.json': f.fixture.modelBytes, 'synthetic-parent.result-ir.json': f.fixture.resultBytes,
    'synthetic-parent.mapping.json': bytes(f.fixture.mapping), 'synthetic-revision.draft.json': f.draftBytes,
    'synthetic-target.result-ir.json': f.resultBytes, 'synthetic-linked-result.json': attachment,
    'synthetic-target.model-ir.json': model, 'synthetic-linked-mapping.json': mapping,
    'synthetic-linked-review.json': review, 'synthetic-linked-lineage.json': lineage,
  })) writeFileSync(testInfo.outputPath(name), body)
  writeFileSync(testInfo.outputPath('synthetic-fixture-scope.txt'), 'Independently authored software contract fixture only. No solver, calibration, physical validation, authenticated execution, KDS check or engineering acceptance. File binding consistency only; all design review is NOT_REVIEWED.\n')
  await view.screenshot({ path: testInfo.outputPath('building-linked-result.png') })
  const fresh = await browser.newContext()
  try {
    const reopened = await fresh.newPage(), freshCalls = await offline(reopened)
    await expect(reopened.locator('[data-building-member-review]')).toHaveCount(0)
    await expect(reopened.locator('[data-building-load-parent]')).toHaveCount(0)
    await file(reopened, 'Import linked revision result', attachment)
    await expect(panel(reopened).locator('[data-building-revision-result-status]')).toContainText('Opened the self-contained linked revision result')
    await expect(panel(reopened).locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
    await expect(panel(reopened).getByRole('button', { name: 'Attach stored result to validated revision', exact: true })).toBeDisabled()
    expect(await download(reopened, 'Export linked revision result')).toEqual(attachment)
    expect(await download(reopened, 'Export linked result member review')).toEqual(review)
    expect(await download(reopened, 'Export linked result lineage')).toEqual(lineage)
    expect(freshCalls).toEqual([])
    expect(await reopened.evaluate(() => (window as any).__buildingLinkedAuthCalls)).toBe(0)
  } finally { await fresh.close() }
  expect(calls).toEqual([])
  expect(await page.evaluate(() => (window as any).__buildingLinkedAuthCalls)).toBe(0)
  await expect(view.getByRole('button', { name: /submit|run analysis|design check/i })).toHaveCount(0)
})

test('old, malformed, tampered, duplicate, BOM and oversized target results retain the previously attached signed forces', async ({ page }) => {
  const f = await buildingRevisionResultFixture(); await offline(page); await openDraft(page, f); await attach(page, f)
  const expected = await download(page, 'Export linked revision result'), tampered = structuredClone(f.result)
  tampered.members[0].end_i_force_n_nm[0] = 777777
  const valid = Buffer.from(f.resultBytes).toString()
  for (const invalid of [f.fixture.resultBytes, Buffer.from('{'), bytes(tampered), Buffer.from(valid.replace('"result_id":', '"result_id":"duplicate","result_id":')), Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(f.resultBytes)]), Buffer.from([0xff])]) {
    await file(page, 'Stored target ResultIR file', invalid)
    await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).click()
    await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('previously verified attached result is retained')
    expect(await download(page, 'Export linked revision result')).toEqual(expected)
  }
  await file(page, 'Stored target ResultIR file', Buffer.alloc(2 * 1024 * 1024 + 1, 32), 'oversized-target.json')
  await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).click()
  await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('at most 2 MiB')
  expect(await page.evaluate(() => (window as any).__buildingLinkedOversizeReads)).toBe(0)
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
})

test('invalid linked-result replacement preserves the verified session and rejects oversized files before reading them', async ({ page }) => {
  const f = await buildingRevisionResultFixture(); await offline(page); await openDraft(page, f); await attach(page, f)
  const expected = await download(page, 'Export linked revision result'), valid = expected.toString(), tampered = JSON.parse(valid)
  tampered.result_ir.sha256 = `sha256:${'a'.repeat(64)}`
  for (const invalid of [Buffer.from('{'), bytes(tampered), Buffer.from(valid.replace('"schema_version":', '"schema_version":"duplicate","schema_version":')), Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), expected]), Buffer.from([0xff])]) {
    await file(page, 'Import linked revision result', invalid)
    await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('previously verified attached result is retained')
    expect(await download(page, 'Export linked revision result')).toEqual(expected)
  }
  await file(page, 'Import linked revision result', Buffer.alloc(16 * 1024 * 1024 + 1, 32), 'oversized-linked-result.json')
  await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('at most 16 MiB')
  expect(await page.evaluate(() => (window as any).__buildingLinkedOversizeReads)).toBe(0)
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
})

test('an explicit intended load source is required and a different preserved source cannot silently accept the result', async ({ page }) => {
  const f = await buildingRevisionResultFixture(); await offline(page); await openDraft(page, f)
  await file(page, 'Stored target ResultIR file', f.resultBytes)
  await expect(panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true })).toBeDisabled()
  await attach(page, f)
  const expected = await download(page, 'Export linked revision result')
  await page.getByLabel('Expected target result load source', { exact: true }).selectOption('load_pattern:LC1')
  await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).click()
  await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('previously verified attached result is retained')
  await expect(panel(page).locator('[data-building-revision-result-identity]')).toContainText('COMB1')
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
  expect(JSON.parse(expected.toString()).selected_load_source).toEqual({ kind: 'load_combination', id: 'COMB1' })
})

test('authoring edits and replacement drafts do not retarget an already attached result or change NOT_RUN authoring status', async ({ page }) => {
  const f = await buildingRevisionResultFixture(); await offline(page); await openDraft(page, f); await attach(page, f)
  const expected = await download(page, 'Export linked revision result')
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-9191')
  await expect(panel(page).locator('[data-building-revision-result-context-changed]')).toContainText('forces have not been retargeted')
  await expect(panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true })).toBeDisabled()
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
  await page.getByRole('button', { name: 'Validate load revision', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('Validated this exact load revision')
  await expect(page.locator('[data-building-load-target]')).toContainText('NOT_RUN / NOT_REVIEWED')
  await page.getByLabel('Expected target result load source', { exact: true }).selectOption('load_combination:COMB1')
  await expect(panel(page).locator('[data-building-revision-result-context-changed]')).toBeVisible()
  await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).click()
  await expect(panel(page).locator('[data-building-revision-result-status]')).toContainText('previously verified attached result is retained')
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
  // A replacement validated draft does not borrow the previous attached forces either.
  const replacement = structuredClone(f.draft); replacement.revision_id = 'synthetic.other.revision'
  page.once('dialog', dialog => dialog.accept())
  await file(page, 'Import saved load revision draft', bytes(replacement))
  await expect(page.locator('[data-building-load-status]')).toContainText('Opened the saved revision draft')
  await expect(panel(page).locator('[data-building-revision-result-identity]')).toContainText('synthetic.load.revision')
  await expect(panel(page).locator('[data-building-revision-result-identity]')).not.toContainText('synthetic.other.revision')
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
})

test('single-flight and draft-generation guards reject a delayed attachment after the draft changes', async ({ page }) => {
  const f = await buildingRevisionResultFixture(); await offline(page); await openDraft(page, f); await attach(page, f)
  const expected = await download(page, 'Export linked revision result')
  await page.evaluate(() => {
    const host = window as any; host.__buildingDelayedReads = 0
    const original = File.prototype.arrayBuffer
    File.prototype.arrayBuffer = async function () {
      if (this.name === 'delayed-target.json') {
        host.__buildingDelayedReads++
        await new Promise<void>(resolve => { host.__releaseBuildingDelayedRead = resolve })
      }
      return original.call(this)
    }
  })
  await file(page, 'Stored target ResultIR file', f.resultBytes, 'delayed-target.json')
  await panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click() })
  await expect.poll(() => page.evaluate(() => (window as any).__buildingDelayedReads)).toBe(1)
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-8888')
  await expect(panel(page).locator('[data-building-revision-result-context-changed]')).toBeVisible()
  await page.evaluate(() => (window as any).__releaseBuildingDelayedRead())
  expect(await download(page, 'Export linked revision result')).toEqual(expected)
  await expect(panel(page).getByRole('button', { name: 'Attach stored result to validated revision', exact: true })).toBeDisabled()
})
