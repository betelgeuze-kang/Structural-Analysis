// Browser rendering and transport over synthetic stopping metadata; no new solver evidence.
import { expect, test, type Locator, type Page } from '@playwright/test'
import { candidateProcessStopFixture } from './candidateProcessStopFixture'
import { resealHistoryPredictionFixture } from './candidateProcessHistoryPredictionFixture'
import type { CandidateObservedFixture } from './candidateProcessObservedFixture'
import { waitForCandidateProcess } from './candidateProcessBrowserWait'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
test.setTimeout(120000)

async function serveStopReview(page: Page, fixture: CandidateObservedFixture) {
  const requests: string[] = []
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { candidateSearchProcessUrl: '/stop-review/manifest.json' }
  })
  await page.route('**/stop-review/**', async route => {
    expect(route.request().method()).toBe('GET')
    const relative = new URL(route.request().url()).pathname.slice('/stop-review/'.length)
    requests.push(relative)
    const bytes = fixture.files.get(relative)
    await route.fulfill({ status: bytes ? 200 : 404, contentType: 'application/json', body: bytes ? Buffer.from(bytes) : '{}' })
  })
  return requests
}

async function selectSlot(panel: Locator, slot: { case_id: string; phase: string; repetition: number; strategy: string }) {
  for (const [name, value] of [['Search case', slot.case_id], ['Phase', slot.phase], ['Repetition', String(slot.repetition)], ['Search strategy', slot.strategy]]) {
    const selector = panel.getByRole('combobox', { name, exact: true })
    if (await selector.inputValue() !== value) await selector.selectOption({ value })
    await expect(selector).toHaveValue(value)
  }
  await expect(panel.locator('[data-candidate-selected-slot]')).toHaveAttribute('data-candidate-selected-slot', JSON.stringify([slot.case_id, slot.phase, slot.repetition, slot.strategy]))
}

async function downloadedBytes(page: Page, name: string): Promise<Buffer> {
  await page.waitForTimeout(250)
  const pending = page.waitForEvent('download', { timeout: 15000 })
  await page.getByRole('button', { name, exact: true }).click()
  const stream = await (await pending).createReadStream()
  expect(stream).not.toBeNull()
  const chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  return Buffer.concat(chunks)
}

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }],
] as const) test.describe(`first verified feasible review on ${name}`, () => {
  test.use({ viewport })
  test('preserves baseline stop, planned versus attempted budgets, legacy comparisons and full-pool audits', async ({ page }) => {
    const fixture = candidateProcessStopFixture()
    const cases = fixture.suite.declaration.cases as any[]
    const stoppingCase = cases[0].case_id
    const legacyCase = cases[1].case_id
    const requests = await serveStopReview(page, fixture)
    await page.goto(`${baseUrl}/#/workbench-v2`)
    const panel = await waitForCandidateProcess(page)
    const loadedRequestCount = requests.length

    const stoppedRuns = fixture.suite.runs.filter(run => run.case_id === stoppingCase && run.strategy !== 'oracle')
    expect(stoppedRuns).toHaveLength(4)
    for (const run of stoppedRuns) {
      await selectSlot(panel, run)
      await expect(panel.locator('[data-candidate-stop-mode]')).toBeVisible()
      await expect(panel.locator('[data-candidate-stop-mode]')).toContainText('First verified feasible')
      await expect(panel.locator('[data-candidate-stop-mode]')).toContainText('does not establish the globally cheapest design')
      await expect(panel.locator('[data-candidate-stop-reason]')).toHaveText('First verified feasible')
      await expect(panel.locator('[data-candidate-stop-id]')).toHaveText('baseline')
      for (const [id, value] of [['planned-candidates', '1'], ['attempted-candidates', '0'], ['unused-budget', '1'], ['baseline-requests', '1'], ['candidate-requests', '0'], ['arm-requests', '1']]) {
        await expect(panel.locator(`[data-candidate-cost="${id}"]`)).toHaveText(value)
      }
      await expect(panel.locator('[data-candidate-plan-order]')).toContainText(`Planned order: ${run.report!.arm!.shortlist.join(' → ')}`)
      await expect(panel.locator('[data-candidate-plan-order]')).toContainText('Attempted prefix: None')
      await expect(panel.locator('[data-candidate-plan-order]')).toContainText('Unattempted candidates have no result or feasibility claim')
      await expect(panel.locator('[data-candidate-physical-status]')).toHaveText('baseline · ready')
      await expect(panel.locator('[data-design-comparison]')).toHaveCount(0)
      await expect(panel.locator('[data-design-candidate]')).toHaveCount(0)
      await expect(panel.locator('[data-candidate-comparison-unavailable]')).toBeVisible()
      await expect(panel.getByRole('button', { name: /^Download selected comparison/ })).toHaveCount(0)
    }
    expect((await downloadedBytes(page, 'Download whole search JSON')).equals(Buffer.from(fixture.files.get('suite.json')!))).toBe(true)
    expect((await downloadedBytes(page, 'Download review manifest')).equals(Buffer.from(fixture.files.get('manifest.json')!))).toBe(true)

    const legacy = fixture.manifest.comparisons.find(entry => entry.case_id === legacyCase && entry.strategy === 'learned')!
    expect(legacy).toBeDefined()
    await selectSlot(panel, legacy)
    await expect(panel.locator('[data-candidate-stop-mode]')).toHaveCount(0)
    await expect(panel.locator('[data-candidate-stop-reason]')).toHaveCount(0)
    await expect(panel.locator('[data-candidate-cost="attempted-candidates"]')).toHaveCount(0)
    const manifestBytes = fixture.files.get(legacy.manifest_file)!
    const manifest = JSON.parse(Buffer.from(manifestBytes).toString('utf8'))
    const reportFile = `${legacy.manifest_file.slice(0, legacy.manifest_file.lastIndexOf('/') + 1)}${manifest.report_file}`
    const reportBytes = fixture.files.get(reportFile)!
    const report = JSON.parse(Buffer.from(reportBytes).toString('utf8'))
    const comparison = panel.getByRole('region', { name: 'Selected candidate comparison', exact: true })
    await expect(comparison).toBeVisible()
    await expect(comparison.getByText(report.report_hash, { exact: true })).toBeVisible()
    expect(await comparison.locator('[data-design-candidate]').evaluateAll(rows => rows.map(row => row.getAttribute('data-design-candidate')))).toEqual(report.rows.map((row: any) => row.candidate_id))
    await expect(comparison.locator('[data-design-selected="true"]')).toHaveCount(report.selection.candidate_id === null ? 0 : 1)
    if (report.selection.candidate_id !== null) await expect(comparison.locator(`[data-design-candidate="${report.selection.candidate_id}"]`)).toHaveAttribute('data-design-selected', 'true')
    expect((await downloadedBytes(page, 'Download selected comparison manifest')).equals(Buffer.from(manifestBytes))).toBe(true)
    expect((await downloadedBytes(page, 'Download selected comparison JSON')).equals(Buffer.from(reportBytes))).toBe(true)

    for (const oracle of fixture.suite.runs.filter(run => run.case_id === stoppingCase && run.strategy === 'oracle')) {
      await selectSlot(panel, oracle)
      await expect(panel.locator('[data-candidate-stop-mode]')).toContainText('The oracle still evaluates the full pool after online selection')
      await expect(panel.locator('[data-candidate-stop-reason]')).toHaveCount(0)
      await expect(panel.locator('[data-candidate-stop-id]')).toHaveCount(0)
      await expect(panel.locator('[data-candidate-plan-order]')).toHaveCount(0)
      for (const id of ['planned-candidates', 'attempted-candidates', 'unused-budget']) await expect(panel.locator(`[data-candidate-cost="${id}"]`)).toHaveCount(0)
      await expect(panel.locator('[data-candidate-physical-status]')).toHaveText('Audit only; not an online selection')
      await expect(panel.locator('[data-candidate-cost="arm-budget"]')).toHaveText('UNAVAILABLE')
      const requested = (oracle.report!.rows as any[]).filter(row => row.analysis_requested).length
      expect(requested).toBe(3)
      await expect(panel.locator('[data-candidate-cost="arm-requests"]')).toHaveText(String(requested))
      await expect(panel.locator('[data-design-candidate]')).toHaveCount(0)
      await expect(panel.getByRole('button', { name: /^Download selected comparison/ })).toHaveCount(0)
    }
    expect(requests.length).toBe(loadedRequestCount)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    for (const selector of await panel.getByRole('combobox').all()) expect((await selector.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  })
})

test('raw-resealed false stop candidate fails closed without physical rows or candidate downloads', async ({ page }) => {
  const fixture = candidateProcessStopFixture()
  const stoppingCase = (fixture.suite.declaration.cases as any[])[0].case_id
  const run = fixture.suite.runs.find(row => row.case_id === stoppingCase && row.strategy === 'learned')!
  ;(run.report!.arm!.execution as any).stop_candidate_id = run.report!.arm!.shortlist[0]
  resealHistoryPredictionFixture(fixture)
  await serveStopReview(page, fixture)
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = await waitForCandidateProcess(page, 'invalid')
  await expect(panel).toContainText('UNAVAILABLE')
  await expect(page.locator('[data-design-candidate]')).toHaveCount(0)
  await expect(panel.locator('[data-candidate-stop-id]')).toHaveCount(0)
  await expect(panel.locator('[data-candidate-cost]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Download (review manifest|whole search JSON|selected comparison)/ })).toHaveCount(0)
})
