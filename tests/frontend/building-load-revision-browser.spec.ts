import { expect, test, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { buildingFixtureBytes, buildingMemberFixture } from './buildingMemberFixture'

const origin = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:5128'
type Fixture = Awaited<ReturnType<typeof buildingMemberFixture>>
const bytes = (value: unknown): Buffer => Buffer.from(buildingFixtureBytes(value))
async function file(page: Page, label: string, buffer: Buffer): Promise<void> {
  await page.getByLabel(label, { exact: true }).setInputFiles({ name: 'synthetic-contract-data.json', mimeType: 'application/json', buffer })
}
async function offline(page: Page): Promise<string[]> {
  await page.addInitScript(() => {
    const host = window as any; host.__buildingRevisionAuthCalls = 0
    host.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: '/v1/jobs', jobStatusUrl: '/v1/jobs/unavailable', nativeFrameSubmissionUrl: '/v1/native/jobs',
      jobAuthorization: async () => { host.__buildingRevisionAuthCalls++; throw new Error('no_service_access') },
    }
  })
  const calls: string[] = []
  await page.route('**/v1/**', async route => { calls.push(route.request().url()); await route.abort() })
  await page.goto(`${origin}/#/building-review`)
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
  return calls
}
async function openSource(page: Page, fixture: Fixture): Promise<void> {
  await file(page, 'Stored native ModelIR file', Buffer.from(fixture.modelBytes))
  await file(page, 'Stored native ResultIR file', Buffer.from(fixture.resultBytes))
  await file(page, 'Import operator-declared mapping', bytes(fixture.mapping))
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('Opened the stored result')
  await expect(page.locator('[data-building-load-revision]')).toBeVisible()
}
async function prepare(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Prepare load revision from admitted files', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('Prepared a load revision')
}
async function validate(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Validate load revision', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('Validated this exact load revision')
  await expect(page.locator('[data-building-load-target]')).toContainText('NOT_RUN / NOT_REVIEWED')
}
async function download(page: Page, label: string): Promise<Buffer> {
  const event = page.waitForEvent('download')
  await page.getByRole('button', { name: label, exact: true }).click()
  return readFileSync((await (await event).path())!)
}

test('edits signed static loads, exports a separate unrun target and reopens a self-contained draft offline', async ({ page, browser }, testInfo) => {
  const fixture = await buildingMemberFixture({ combination: true }), calls = await offline(page)
  await openSource(page, fixture); await prepare(page)
  await expect(page.locator('[data-building-load-draft-status]')).toContainText('Unsaved load revision draft')
  await page.getByLabel('Self-weight Z multiplier', { exact: true }).fill('-1')
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-12345.5')
  await page.getByLabel('Load L_WEAK_N2 MX (N·m)', { exact: true }).fill('17.25')
  await page.getByLabel('New nodal load ID', { exact: true }).fill('ADDED_N3')
  await page.getByLabel('New load model node', { exact: true }).selectOption('N3')
  await page.getByRole('button', { name: 'Add explicit nodal load row', exact: true }).click()
  await page.getByLabel('Load ADDED_N3 FX (N)', { exact: true }).fill('-31')
  await page.getByLabel('Load ADDED_N3 MZ (N·m)', { exact: true }).fill('-7')
  await validate(page)
  await expect(page.locator('[data-building-load-draft-status]')).toContainText('Unsaved load revision draft')
  await expect(page.locator('[data-building-load-parent]')).toContainText('Original stored result is parent context only')
  await expect(page.locator('[data-building-load-combination]')).toHaveText('COMB1')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
  const modelBytes = await download(page, 'Export revised ModelIR'), model = JSON.parse(modelBytes.toString())
  expect(model.load_patterns[0].self_weight).toEqual([0, 0, -1])
  expect(model.load_patterns[0].nodal_loads[0]).toEqual({ ...fixture.model.load_patterns[0].nodal_loads[0],
    components_si: { FX: 0, FY: -12345.5, FZ: 0, MX: 17.25, MY: 0, MZ: 0 } })
  expect(model.load_patterns[0].nodal_loads[1]).toMatchObject({ id: 'ADDED_N3', node_id: 'N3', components_si: { FX: -31, FY: 0, FZ: 0, MX: 0, MY: 0, MZ: -7 } })
  for (const key of ['nodes', 'elements', 'materials', 'sections', 'constraints', 'load_combinations']) expect(model[key]).toEqual(fixture.model[key])
  expect(model.load_patterns[0].uniform_member_loads).toEqual(fixture.model.load_patterns[0].uniform_member_loads)
  const recordBytes = await download(page, 'Export load revision record'), record = JSON.parse(recordBytes.toString())
  expect(record.parent.result_hash).toBe(fixture.result.result_hash)
  expect(record.unchanged_inventory).toEqual({ storeys: fixture.mapping.storeys, members: fixture.mapping.members })
  expect(record.target).toMatchObject({ analysis_status: 'NOT_RUN', review_status: 'NOT_REVIEWED', result: null })
  expect(record.target.model_content_hash).not.toBe(fixture.mapping.bindings.model_content_hash)
  const recipe = await download(page, 'Export load edit recipe')
  const recipeHash = `sha256:${createHash('sha256').update(recipe).digest('hex')}`
  expect(recipeHash).toBe(model.provenance.source_sha256)
  expect(recipeHash).toBe(record.edit_recipe_hash)
  await expect(page.locator('[data-building-load-draft-status]')).toContainText('Unsaved load revision draft')
  const draft = await download(page, 'Download load revision draft')
  await expect(page.locator('[data-building-load-draft-status]')).not.toContainText('Unsaved load revision draft')
  writeFileSync(testInfo.outputPath('synthetic-parent-model.json'), fixture.modelBytes)
  writeFileSync(testInfo.outputPath('synthetic-parent-result.json'), fixture.resultBytes)
  writeFileSync(testInfo.outputPath('synthetic-parent-mapping.json'), bytes(fixture.mapping))
  writeFileSync(testInfo.outputPath('synthetic-load-revision.draft.json'), draft)
  writeFileSync(testInfo.outputPath('synthetic-load-revision.model-ir.json'), modelBytes)
  writeFileSync(testInfo.outputPath('synthetic-load-revision.record.json'), recordBytes)
  writeFileSync(testInfo.outputPath('synthetic-load-revision.recipe.json'), recipe)
  writeFileSync(testInfo.outputPath('synthetic-fixture-scope.txt'), 'Authored software contract data only. No solver execution, mass source, KDS check, physical validation or engineering acceptance. Target is NOT_RUN and NOT_REVIEWED.\n')
  await page.screenshot({ path: testInfo.outputPath('building-static-load-revision.png'), fullPage: true })
  const fresh = await browser.newContext()
  try {
    const reopened = await fresh.newPage(), freshCalls = await offline(reopened)
    await expect(reopened.locator('[data-building-member-review]')).toHaveCount(0)
    await expect(reopened.getByRole('button', { name: 'Prepare load revision from admitted files', exact: true })).toBeDisabled()
    await file(reopened, 'Import saved load revision draft', draft)
    await expect(reopened.locator('[data-building-load-status]')).toContainText('Opened the saved revision draft')
    await expect(reopened.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('-12345.5')
    await expect(reopened.getByRole('button', { name: 'Export revised ModelIR', exact: true })).toHaveCount(0)
    await validate(reopened)
    await expect(reopened.locator('[data-building-member-review]')).toHaveCount(0)
    await expect(reopened.locator('[data-building-force-rows]')).toHaveCount(0)
    await expect(reopened.locator('[data-building-load-source-changed]')).toHaveCount(0)
    expect(await download(reopened, 'Export revised ModelIR')).toEqual(modelBytes)
    expect(await download(reopened, 'Export load revision record')).toEqual(recordBytes)
    expect(await download(reopened, 'Export load edit recipe')).toEqual(recipe)
    expect(freshCalls).toEqual([])
    expect(await reopened.evaluate(() => (window as any).__buildingRevisionAuthCalls)).toBe(0)
  } finally { await fresh.close() }
  expect(calls).toEqual([])
  expect(await page.evaluate(() => (window as any).__buildingRevisionAuthCalls)).toBe(0)
  await expect(page.getByRole('button', { name: /submit and run|run analysis|design check/i })).toHaveCount(0)
})

test('each edit removes stale target exports, blank input stays invalid, and prepared work can be saved before target generation', async ({ page }) => {
  const fixture = await buildingMemberFixture(); await offline(page); await openSource(page, fixture); await prepare(page)
  const beforeTarget = await download(page, 'Download load revision draft')
  expect(JSON.parse(beforeTarget.toString()).schema_version).toBe('structural-building-load-revision-draft.v1')
  await validate(page)
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('')
  await expect(page.getByRole('button', { name: 'Export revised ModelIR', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Export load revision record', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Validate load revision', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('must be a finite, explicitly entered number')
  await expect(page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('')
  await expect(page.locator('[data-building-load-draft-status]')).toContainText('Unsaved load revision draft')
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-91')
  const edited = JSON.parse((await download(page, 'Download load revision draft')).toString())
  expect(edited.patches[0].nodal_loads[0].components_si.FY).toBe(-91)
  await expect(page.getByRole('button', { name: 'Export revised ModelIR', exact: true })).toHaveCount(0)
})

test('invalid, tampered, duplicate, BOM and oversized draft replacements retain the exact opened revision and compiled target', async ({ page }) => {
  const fixture = await buildingMemberFixture(); await offline(page); await openSource(page, fixture); await prepare(page)
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-202')
  const valid = await download(page, 'Download load revision draft'); await validate(page)
  const target = await download(page, 'Export revised ModelIR')
  const tampered = JSON.parse(valid.toString()); tampered.parent.model_ir.sha256 = `sha256:${'a'.repeat(64)}`
  for (const invalid of [Buffer.from('{'), bytes(tampered), Buffer.from(valid.toString().replace('"patches":', '"patches":[],"patches":')), Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), valid]), Buffer.from([0xff])]) {
    await file(page, 'Import saved load revision draft', invalid)
    await expect(page.locator('[data-building-load-status]')).toContainText('previous revision and target downloads are retained')
    await expect(page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('-202')
    expect(await download(page, 'Export revised ModelIR')).toEqual(target)
  }
  await file(page, 'Import saved load revision draft', Buffer.alloc(8 * 1024 * 1024 + 1, 32))
  await expect(page.locator('[data-building-load-status]')).toContainText('at most 8 MiB')
  expect(await download(page, 'Export revised ModelIR')).toEqual(target)
})

test('changing the admitted parent preserves the frozen draft and requires explicit confirmation before replacement or navigation', async ({ page }) => {
  const original = await buildingMemberFixture(), replacement = await buildingMemberFixture({ remesh: true })
  await offline(page); await openSource(page, original); await prepare(page)
  await page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true }).fill('-303')
  await openSource(page, replacement)
  await expect(page.locator('[data-building-load-source-changed]')).toContainText('has not been retargeted')
  await expect(page.locator('[data-building-load-parent]')).toContainText('synthetic-building')
  await expect(page.locator('[data-building-load-parent]')).not.toContainText('synthetic-building-remesh')
  await expect(page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('-303')
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: 'Prepare load revision from admitted files', exact: true }).click()
  await expect(page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('-303')
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
  await expect(page.getByLabel('Load L_WEAK_N2 FY (N)', { exact: true })).toHaveValue('-303')
  const draft = JSON.parse((await download(page, 'Download load revision draft')).toString())
  expect(JSON.parse(Buffer.from(draft.parent.mapping.body_base64, 'base64').toString()).bindings.result_hash).toBe(original.result.result_hash)
  expect(draft.patches[0].nodal_loads[0].components_si.FY).toBe(-303)
  await page.getByRole('button', { name: 'Prepare load revision from admitted files', exact: true }).click()
  await expect(page.locator('[data-building-load-status]')).toContainText('Prepared a load revision')
  await expect(page.locator('[data-building-load-source-changed]')).toHaveCount(0)
  await expect(page.locator('[data-building-load-parent]')).toContainText('synthetic-building-remesh')
  await expect(page.locator('[data-building-load-draft-status]')).toContainText('Unsaved load revision draft')
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toHaveCount(0)
})

test('deleting an existing load does not renumber a surviving row, and new explicit rows may share its node', async ({ page }) => {
  const fixture = await buildingMemberFixture(); await offline(page); await openSource(page, fixture); await prepare(page)
  await page.getByLabel('New nodal load ID', { exact: true }).fill('SECOND_N2')
  await page.getByLabel('New load model node', { exact: true }).selectOption('N2')
  await page.getByRole('button', { name: 'Add explicit nodal load row', exact: true }).click()
  await page.getByLabel('Load SECOND_N2 FZ (N)', { exact: true }).fill('-7')
  await page.getByRole('button', { name: 'Remove load L_WEAK_N2', exact: true }).click()
  await expect(page.locator('[data-building-load-rows] tbody tr')).toHaveCount(1)
  await expect(page.locator('[data-building-nodal-load="SECOND_N2"]')).toContainText('SECOND_N2 / 1')
  await validate(page)
  const model = JSON.parse((await download(page, 'Export revised ModelIR')).toString())
  expect(model.load_patterns[0].nodal_loads).toHaveLength(1)
  expect(model.load_patterns[0].nodal_loads[0]).toMatchObject({ id: 'SECOND_N2', index: 1, node_id: 'N2' })
})

test('deleting before adding reserves original parent indices and produces a reopenable replacement load draft', async ({ page }) => {
  const fixture = await buildingMemberFixture(); await offline(page); await openSource(page, fixture); await prepare(page)
  await page.getByRole('button', { name: 'Remove load L_WEAK_N2', exact: true }).click()
  await page.getByLabel('New nodal load ID', { exact: true }).fill('REPLACEMENT_N2')
  await page.getByLabel('New load model node', { exact: true }).selectOption('N2')
  await page.getByRole('button', { name: 'Add explicit nodal load row', exact: true }).click()
  await page.getByLabel('Load REPLACEMENT_N2 FY (N)', { exact: true }).fill('-42')
  const draft = await download(page, 'Download load revision draft')
  await file(page, 'Import saved load revision draft', draft)
  await expect(page.locator('[data-building-load-status]')).toContainText('Opened the saved revision draft')
  await expect(page.locator('[data-building-nodal-load="REPLACEMENT_N2"]')).toContainText('REPLACEMENT_N2 / 1')
  await validate(page)
  const model = JSON.parse((await download(page, 'Export revised ModelIR')).toString())
  expect(model.load_patterns[0].nodal_loads[0]).toMatchObject({ id: 'REPLACEMENT_N2', index: 1, node_id: 'N2' })
})

test('half-entered new rows are guarded and cannot be silently omitted from saved or validated drafts', async ({ page }) => {
  const fixture = await buildingMemberFixture(); await offline(page); await openSource(page, fixture); await prepare(page)
  await download(page, 'Download load revision draft'); await validate(page)
  await page.getByLabel('New nodal load ID', { exact: true }).fill('PENDING_ENTRY')
  await expect(page.locator('[data-building-load-pending-entry]')).toContainText('not part of the revision draft')
  await expect(page.getByRole('button', { name: 'Download load revision draft', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Validate load revision', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Export revised ModelIR', exact: true })).toHaveCount(0)
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.getByLabel('New nodal load ID', { exact: true })).toHaveValue('PENDING_ENTRY')
  await page.getByRole('button', { name: 'Clear pending nodal load entry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download load revision draft', exact: true })).toBeEnabled()
  await download(page, 'Download load revision draft')
  await expect(page.locator('[data-building-load-draft-status]')).not.toContainText('Unsaved load revision draft')
})
