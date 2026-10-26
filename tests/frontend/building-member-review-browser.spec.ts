import { expect, test, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { canonicalNativeJson, nativeFrameModelIdentity } from '../../src/workbench-v2/model/nativeFrameProvider'
import { createBuildingMemberMappingTemplate, type BuildingMemberMapping } from '../../src/workbench-v2/model/buildingMemberReview'
import { nativeFrameResultFixture, fixtureHash } from './nativeFrameFixture'

const origin = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:5128'
const bytes = (value: unknown): Buffer => Buffer.from(JSON.stringify(value, null, 2))

async function fixture(): Promise<{ model: Buffer; result: Buffer; mapping: BuildingMemberMapping }> {
  // Existing synthetic contract data only. No solver or physical validation is run.
  const model = JSON.parse(readFileSync('native/distribution/frame-alpha-cantilever.model-ir.json', 'utf8'))
  const result = nativeFrameResultFixture() as any
  model.model_id = 'synthetic-contract-frame-alpha'
  result.bindings.model_id = model.model_id
  result.result_id = 'synthetic-contract-frame-alpha.LC1'
  model.load_patterns[0].id = result.bindings.load_pattern_id
  model.elements.push({ ...structuredClone(model.elements[0]), id: 'E2', index: 1 })
  result.members[0].end_i_force_n_nm = [-100000, 17, -9, 3, -5, 11]
  result.members[0].end_j_force_n_nm = [100000, -17, 9, -3, 5, -11]
  result.members.push({ member_id: 'E2', end_i_force_n_nm: [-20, 1, 2, 3, 4, 5], end_j_force_n_nm: [20, -1, -2, -3, -4, -5] })
  Object.assign(result.bindings, await nativeFrameModelIdentity(model))
  const body = { ...result }; delete body.result_hash; result.result_hash = fixtureHash(body)
  const modelBytes = Buffer.from(canonicalNativeJson(model)), resultBytes = bytes(result)
  return { model: modelBytes, result: resultBytes, mapping: await createBuildingMemberMappingTemplate(modelBytes, resultBytes) }
}
async function choose(page: Page, label: string, buffer: Buffer): Promise<void> {
  await page.getByLabel(label, { exact: true }).setInputFiles({ name: `${label.replaceAll(' ', '-')}.json`, mimeType: 'application/json', buffer })
}
async function sourceFiles(page: Page, data: Awaited<ReturnType<typeof fixture>>): Promise<void> {
  await choose(page, 'Stored native ModelIR file', data.model)
  await choose(page, 'Stored native ResultIR file', data.result)
}
async function openMapping(page: Page, mapping: unknown): Promise<void> {
  await choose(page, 'Import operator-declared mapping', bytes(mapping))
  await expect(page.locator('[data-building-member-status]')).toContainText('Mapping loaded into the editor')
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('Opened the stored result')
}
function mapped(data: Awaited<ReturnType<typeof fixture>>, id = 'C1'): BuildingMemberMapping {
  return { ...data.mapping, storeys: [{ storey_id: 'S1', label: 'Declared first storey', elevation_m: 3 }], members: [
    { member_id: id, label: 'Author-declared column', storey_id: 'S1',
      segments: [{ segment_id: 'SEG1', element_id: 'E1', member_start: 0.2, member_end: 0.6, orientation: 'j_to_i' }],
      review_locations: [{ location_id: 'LOC1', element_id: 'E1', end: 'i' }] },
    { member_id: 'unmapped', label: 'Declared member without elements', storey_id: 'S1', segments: [], review_locations: [] },
  ] }
}
async function offline(page: Page): Promise<{ calls: string[] }> {
  await page.addInitScript(() => {
    const host = window as any; host.__buildingAuthCalls = 0
    host.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobStatusUrl: '/v1/jobs/unavailable',
      jobAuthorization: async () => { host.__buildingAuthCalls++; throw new Error('no_service_access') } }
  })
  const calls: string[] = []
  await page.route('**/v1/jobs**', async route => { calls.push(route.request().url()); await route.abort() })
  await page.goto(`${origin}/#/building-review`)
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
  await expect(page.locator('[data-rc-project-workspace]')).toHaveCount(0)
  return { calls }
}

test('authors storeys and member segments without hashes, keeps signed native forces and unmapped endpoints, and reopens exports offline', async ({ page, browser }, testInfo) => {
  const data = await fixture(), { calls } = await offline(page)
  await sourceFiles(page, data)
  await page.getByRole('button', { name: 'Prepare empty member mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-review]')).toHaveAttribute('data-building-member-review', 'admitted')
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('0 / 2')
  await expect(page.locator('[data-building-physical-members] tbody tr')).toHaveCount(0)
  await page.getByLabel('Storey ID', { exact: true }).fill('S1')
  await page.getByLabel('Storey label', { exact: true }).fill('First storey')
  await page.getByLabel('Declared elevation (m)', { exact: true }).fill('3')
  await page.getByRole('button', { name: 'Add storey to draft', exact: true }).click()
  await page.getByLabel('Physical member ID', { exact: true }).fill('C1')
  await page.getByLabel('Physical member label', { exact: true }).fill('Column 1')
  await page.getByLabel('Declared storey ID', { exact: true }).fill('S1')
  await page.getByRole('button', { name: 'Add physical member to draft', exact: true }).click()
  await page.getByLabel('Segment ID', { exact: true }).fill('SEG1')
  await page.getByLabel('Physical start station', { exact: true }).fill('0.2')
  await page.getByLabel('Physical end station', { exact: true }).fill('0.6')
  await page.getByLabel('Physical start to end', { exact: true }).selectOption('j_to_i')
  await page.getByRole('button', { name: 'Add segment and native end locations to draft', exact: true }).click()
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('0 / 2')
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('1 / 1')
  const physical = page.locator('[data-building-physical-members] tbody tr')
  await expect(physical).toContainText('PARTIAL / INCOMPLETE')
  await expect(physical).toContainText('0–0.2, 0.6–1')
  await expect(physical).toContainText('NOT_REVIEWED')
  const nativeI = page.locator('[data-building-element="E1"][data-building-end="i"]')
  await expect(nativeI).toContainText('i / N1')
  await expect(nativeI).toContainText('0.6 / j_to_i')
  await expect(nativeI.locator('[data-building-component]')).toHaveText(['-100000', '17', '-9', '3', '-5', '11'])
  expect(await nativeI.locator('[data-building-component]').evaluateAll(cells => cells.map(cell => getComputedStyle(cell).whiteSpace)))
    .toEqual(Array(6).fill('nowrap'))
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
  await expect(page.locator('[data-building-load-pattern]')).toHaveText('LC1')
  await page.getByLabel('Member rows', { exact: true }).selectOption('unmapped')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(2)
  await expect(page.locator('[data-building-force-rows] tbody')).toContainText('E2')
  const reviewEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export complete member review', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await reviewEvent).path())!, 'utf8'))
  expect(exported.rows).toHaveLength(4)
  expect(exported.rows.map((row: any) => row.review_status)).toEqual(Array(4).fill('NOT_REVIEWED'))
  expect(exported.source.result_hash).toBe(JSON.parse(data.result.toString()).result_hash)
  expect(exported.rows[0].force_n_nm).toEqual([-100000, 17, -9, 3, -5, 11])
  const mappingEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export admitted member mapping', exact: true }).click()
  const mappingBytes = readFileSync((await (await mappingEvent).path())!)
  writeFileSync(testInfo.outputPath('synthetic-native-model.json'), data.model)
  writeFileSync(testInfo.outputPath('synthetic-native-result.json'), data.result)
  writeFileSync(testInfo.outputPath('synthetic-building-member-mapping.json'), mappingBytes)
  writeFileSync(testInfo.outputPath('synthetic-member-review.json'), JSON.stringify(exported, null, 2))
  writeFileSync(testInfo.outputPath('synthetic-fixture-scope.txt'), 'Synthetic contract fixture only. No solver, physical validation, design check or engineering acceptance was performed. Model/result values are authored test data.\n')
  const fresh = await browser.newContext()
  try {
    const reopened = await fresh.newPage(), freshOffline = await offline(reopened); await sourceFiles(reopened, data)
    await choose(reopened, 'Import operator-declared mapping', mappingBytes)
    await reopened.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
    await expect(reopened.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
    await expect(reopened.locator('[data-building-member-authority]')).toContainText('NOT_REVIEWED')
    await expect(reopened.getByRole('button', { name: /run analysis|submit|design check/i })).toHaveCount(0)
    expect(freshOffline.calls).toEqual([])
    expect(await reopened.evaluate(() => (window as any).__buildingAuthCalls)).toBe(0)
    await reopened.screenshot({ path: testInfo.outputPath('building-member-offline-review.png'), fullPage: true })
  } finally { await fresh.close() }
  expect(calls).toEqual([])
  expect(await page.evaluate(() => (window as any).__buildingAuthCalls)).toBe(0)
})

test('retains empty members and partial gaps, distinguishes physical IDs from filter sentinels, and exports unselected endpoints', async ({ page }) => {
  const data = await fixture(); await offline(page); await sourceFiles(page, data)
  await openMapping(page, mapped(data, 'all'))
  await expect(page.locator('[data-building-physical-members] tbody tr')).toHaveCount(2)
  await expect(page.locator('[data-building-physical-members] tbody tr').filter({ hasText: 'Declared member without elements' })).toContainText('UNMAPPED / UNMAPPED')
  await page.getByLabel('Member rows', { exact: true }).selectOption('member:all')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(2)
  await expect(page.locator('[data-building-element="E1"][data-building-end="j"]')).toContainText('Not declared')
  await page.getByLabel('Member rows', { exact: true }).selectOption('member:unmapped')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(0)
  await expect(page.locator('[data-building-row-count]')).toContainText('of 0. Export retains all 4')
  await page.getByLabel('Member rows', { exact: true }).selectOption('unmapped')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(2)
})

test('invalid replacements and duplicate-key editor changes keep the previous admitted review and mapping', async ({ page }) => {
  const data = await fixture(); await offline(page); await sourceFiles(page, data)
  const mapping = mapped(data)
  await openMapping(page, mapping)
  const originalDraft = await page.getByLabel('Operator-declared mapping JSON', { exact: true }).inputValue()
  const invalid = { ...mapping, bindings: { ...mapping.bindings, result_hash: `sha256:${'0'.repeat(64)}` } }
  await choose(page, 'Import operator-declared mapping', bytes(invalid))
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('Any previously opened review is retained')
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('1 / 1')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export admitted member mapping', exact: true }).click()
  expect(JSON.parse(readFileSync((await (await download).path())!, 'utf8'))).toEqual(mapping)
  const beforeBom = await page.getByLabel('Operator-declared mapping JSON', { exact: true }).inputValue()
  await choose(page, 'Import operator-declared mapping', Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), bytes(mapping)]))
  await expect(page.locator('[data-building-member-status]')).toContainText('BOM is not supported')
  await expect(page.getByLabel('Operator-declared mapping JSON', { exact: true })).toHaveValue(beforeBom)
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('1 / 1')
  const duplicate = originalDraft.replace('"storeys":', '"storeys": [], "storeys":')
  await page.getByLabel('Operator-declared mapping JSON', { exact: true }).fill(duplicate)
  await page.getByLabel('Storey ID', { exact: true }).fill('S2')
  await page.getByLabel('Storey label', { exact: true }).fill('Second')
  await page.getByLabel('Declared elevation (m)', { exact: true }).fill('6')
  await page.getByRole('button', { name: 'Add storey to draft', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('duplicate')
  await expect(page.getByLabel('Operator-declared mapping JSON', { exact: true })).toHaveValue(duplicate)
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
  await choose(page, 'Stored native ModelIR file', Buffer.from('{"schema_version":"invalid"}'))
  await page.getByRole('button', { name: 'Prepare empty member mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('Any previously opened review is retained')
  await expect(page.locator('[data-building-mapping-counts]')).toHaveText('1 / 1')
})

test('rejects oversized local files without replacing the displayed review', async ({ page }) => {
  const data = await fixture(); await offline(page); await sourceFiles(page, data); await openMapping(page, mapped(data))
  await choose(page, 'Stored native ResultIR file', Buffer.alloc(2 * 1024 * 1024 + 1, 32))
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('at most 2 MiB')
  await expect(page.locator('[data-building-force-rows] tbody tr')).toHaveCount(4)
})

test('protects edited mapping drafts on navigation and lets users save and reopen unvalidated text', async ({ page }) => {
  const data = await fixture(); await offline(page); await sourceFiles(page, data); await openMapping(page, mapped(data))
  const editor = page.getByLabel('Operator-declared mapping JSON', { exact: true })
  const edited = (await editor.inputValue()).replace('Author-declared column', 'Edited column label')
  await editor.fill(edited)
  await expect(page.locator('[data-building-draft-status]')).toContainText('Unsaved mapping draft')
  const cancelled: string[] = []
  page.once('dialog', async dialog => { cancelled.push(dialog.message()); await dialog.dismiss() })
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
  await expect(editor).toHaveValue(edited)
  expect(cancelled).toHaveLength(1)
  await page.getByRole('button', { name: 'Open declared mapping', exact: true }).click()
  await expect(page.locator('[data-building-member-status]')).toContainText('Opened the stored result')
  await expect(page.locator('[data-building-draft-status]')).toContainText('Unsaved mapping draft')
  const admittedDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export admitted member mapping', exact: true }).click()
  await admittedDownload
  await expect(page.locator('[data-building-draft-status]')).not.toContainText('Unsaved mapping draft')
  const unfinished = '{ "schema_version": "unfinished operator draft",'
  await editor.fill(unfinished)
  const previousDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export admitted member mapping', exact: true }).click()
  await previousDownload
  await expect(page.locator('[data-building-draft-status]')).toContainText('Unsaved mapping draft')
  const draftDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download unvalidated mapping draft', exact: true }).click()
  const downloaded = await draftDownload, draftBytes = readFileSync((await downloaded.path())!)
  expect(downloaded.suggestedFilename()).toBe('building-member-mapping-unvalidated.draft.json')
  expect(draftBytes.toString('utf8')).toBe(unfinished)
  await expect(page.locator('[data-building-draft-status]')).not.toContainText('Unsaved mapping draft')
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toHaveCount(0)
  await page.getByRole('link', { name: 'Review building members', exact: true }).click()
  await choose(page, 'Import operator-declared mapping', draftBytes)
  await expect(page.getByLabel('Operator-declared mapping JSON', { exact: true })).toHaveValue(unfinished)
  await expect(page.locator('[data-building-draft-status]')).not.toContainText('Unsaved mapping draft')
})

for (const [route, base] of [['/building-review///?source=local', '/'], ['/nested/building-review/?source=local', '/nested/']] as const)
test(`direct building path ${route} returns to Workbench and preserves keyboard navigation`, async ({ page }) => {
  await page.goto(`${origin}${route}`)
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toHaveCount(0)
  expect(new URL(page.url()).pathname).toBe(base)
  expect(new URL(page.url()).search).toBe('?source=local')
  const skip = page.getByRole('link', { name: 'Skip to workbench', exact: true })
  await expect(skip).toBeAttached(); await page.keyboard.press('Tab'); await expect(skip).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main', { name: 'Workbench content', exact: true })).toBeFocused()
  await expect(page.locator('[data-building-member-workspace]')).toHaveCount(0)
  await page.getByRole('link', { name: 'Review building members', exact: true }).click()
  await expect(page.locator('[data-building-member-workspace]')).toBeVisible()
})
