import { createHash } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import { candidateProcessIncompleteFixture, candidateProcessObservedFixture } from './candidateProcessObservedFixture'
import { designComparisonFixture } from './designComparisonFixture'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const identity = (bytes: Uint8Array): string => `sha256:${createHash('sha256').update(bytes).digest('hex')}`
const encode = (value: unknown): Uint8Array => Buffer.from(JSON.stringify(value))
test.setTimeout(120000)

async function serveReview(page: Page, options: { corruptSuite?: boolean; standalone?: boolean; incomplete?: boolean } = {}) {
  const fixture = options.incomplete ? candidateProcessIncompleteFixture() : candidateProcessObservedFixture()
  await page.addInitScript((standalone) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      candidateSearchProcessUrl: '/candidate-review/manifest.json',
      ...(standalone ? { designComparisonUrl: '/standalone/manifest.json' } : {}),
    }
  }, options.standalone === true)
  const requests: string[] = []
  await page.route('**/candidate-review/**', async (route) => {
    expect(route.request().method()).toBe('GET')
    const relative = new URL(route.request().url()).pathname.slice('/candidate-review/'.length)
    requests.push(relative)
    const bytes = fixture.files.get(relative)
    if (!bytes) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    return route.fulfill({ contentType: 'application/json', body: options.corruptSuite && relative === 'suite.json'
      ? Buffer.concat([Buffer.from(bytes), Buffer.from('\n')]) : Buffer.from(bytes) })
  })
  return { ...fixture, requests }
}

async function downloadedBytes(page: Page, buttonName: string): Promise<Buffer> {
  // Chromium throttles the 11th rapid download even with trusted clicks and delayed URL revocation.
  // Pace actual user gestures; retain all 18 byte-for-byte download checks on the same page.
  await page.waitForTimeout(250)
  const pending = page.waitForEvent('download', { timeout: 15000 })
  await page.getByRole('button', { name: buttonName, exact: true }).click()
  const stream = await (await pending).createReadStream()
  expect(stream).not.toBeNull()
  const chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  return Buffer.concat(chunks)
}

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test.describe(`candidate process review on ${name}`, () => {
    test.use({ viewport })
    test('loads a whole retained search, selects arms and downloads the exact displayed artifacts', async ({ page }) => {
      // The producer values are retained observation bytes. Serving them performs no new search.
      const fixture = await serveReview(page)
      await page.goto(`${baseUrl}/#/workbench-v2`)
      const panel = page.locator('[data-candidate-process="verified"]')
      await expect(panel).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Physical design comparison', exact: true })).toHaveCount(0)
      await expect(panel.locator('[data-candidate-source]')).toHaveText(fixture.suite.declaration.source_revision)
      await expect(panel.locator('[data-candidate-cost="total-requests"]')).toHaveText(String(fixture.suite.cost_accounting.total_analysis_request_count_including_training_warmups_and_oracles))
      await panel.locator('[data-candidate-paired-outcomes] > summary').click()
      for (const summary of fixture.suite.case_summaries) {
        for (const pair of summary.measured_pairs) {
          const pairValue = panel.locator(`[data-candidate-pair-wall="${summary.case_id}:${pair.repetition}:learned"]`)
          if (pair.deterministic_minus_learned_slot_wall_ns === null) await expect(pairValue).toHaveText('UNAVAILABLE')
          else {
            const shown = Number(await pairValue.innerText())
            expect(Math.sign(shown)).toBe(Math.sign(pair.deterministic_minus_learned_slot_wall_ns))
            expect(Math.abs(shown - pair.deterministic_minus_learned_slot_wall_ns / 1e9)).toBeLessThan(0.000051)
          }
          const casePanel = panel.locator(`[data-candidate-case-summary="${summary.case_id}"]`)
          const row = casePanel.getByRole('row').filter({ has: page.getByRole('rowheader', { name: `${pair.repetition + 1} · Learned search`, exact: true }) })
          const audit = pair.oracle_audit.learned
          await expect(row.locator('td').nth(3)).toHaveText(audit.missed_feasible_count === null ? 'UNAVAILABLE' : String(audit.missed_feasible_count))
          await expect(row.locator('td').nth(4)).toHaveText(audit.false_safe_count === null ? 'UNAVAILABLE' : String(audit.false_safe_count))
        }
      }
      const historical = await panel.locator('[data-candidate-cost="historical-generation"]').innerText()
      const loadedRequestCount = fixture.requests.length
      for (const entry of fixture.manifest.comparisons) {
        await panel.getByRole('combobox', { name: 'Search case', exact: true }).selectOption(entry.case_id)
        await panel.getByRole('combobox', { name: 'Phase', exact: true }).selectOption(entry.phase)
        await panel.getByRole('combobox', { name: 'Repetition', exact: true }).selectOption({ value: String(entry.repetition) })
        await expect(panel.getByRole('combobox', { name: 'Repetition', exact: true })).toHaveValue(String(entry.repetition))
        await panel.getByRole('combobox', { name: 'Search strategy', exact: true }).selectOption(entry.strategy)
        const manifestBytes = fixture.files.get(entry.manifest_file)!
        const manifest = JSON.parse(Buffer.from(manifestBytes).toString('utf8'))
        const reportFile = `${entry.manifest_file.slice(0, entry.manifest_file.lastIndexOf('/') + 1)}${manifest.report_file}`
        const reportBytes = fixture.files.get(reportFile)!
        const report = JSON.parse(Buffer.from(reportBytes).toString('utf8'))
        const comparison = panel.getByRole('region', { name: 'Selected candidate comparison', exact: true })
        await expect(comparison).toBeVisible()
        await expect(comparison.getByText(report.report_hash, { exact: true })).toBeVisible()
        await expect(comparison.locator('[data-design-selected="true"]')).toHaveCount(report.selection.candidate_id === null ? 0 : 1)
        if (report.selection.candidate_id !== null) await expect(comparison.locator(`[data-design-candidate="${report.selection.candidate_id}"]`)).toHaveAttribute('data-design-selected', 'true')
        const run = fixture.suite.runs.find((row: Record<string, unknown>) => row.case_id === entry.case_id && row.phase === entry.phase && row.repetition === entry.repetition && row.strategy === entry.strategy)!
        const resource = run.resources
        for (const [id, expected] of [
          ['worker-rss', resource.peak_memory_bytes], ['input-bytes', resource.input_bytes_read],
          ['output-bytes', resource.report_bytes_written], ['baseline-requests', run.report.arm.cost_accounting.baseline_analysis_request_count],
          ['candidate-requests', run.report.arm.cost_accounting.candidate_analysis_request_count], ['arm-requests', run.report.arm.cost_accounting.total_analysis_request_count],
        ] as const) {
          expect(Number((await panel.locator(`[data-candidate-cost="${id}"]`).innerText()).replace(/,/g, ''))).toBe(expected)
        }
        const displayedCpu = Number(await panel.locator('[data-candidate-cost="worker-cpu"]').innerText())
        expect(Math.abs(displayedCpu - resource.cpu_process_time_ns / 1e9)).toBeLessThan(0.000051)
        await test.step(`Download ${entry.case_id}/${entry.phase}/${entry.repetition}/${entry.strategy}`, async () => {
          expect((await downloadedBytes(page, 'Download selected comparison manifest')).equals(Buffer.from(manifestBytes))).toBe(true)
          expect((await downloadedBytes(page, 'Download selected comparison JSON')).equals(Buffer.from(reportBytes))).toBe(true)
        })
        await expect(panel.locator('[data-candidate-cost="historical-generation"]')).toHaveText(historical)
      }
      expect(fixture.requests.length).toBe(loadedRequestCount)
      await panel.getByRole('combobox', { name: 'Search strategy', exact: true }).selectOption('oracle')
      await expect(panel.locator('[data-candidate-physical-status]')).toContainText('Audit only')
      await expect(panel.locator('[data-candidate-comparison-unavailable]')).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Selected candidate comparison', exact: true })).toHaveCount(0)
      await expect(panel.getByRole('button', { name: 'Download selected comparison JSON', exact: true })).toHaveCount(0)
      await expect(panel.locator('[data-candidate-cost="arm-budget"]')).toHaveText('UNAVAILABLE')
      expect((await downloadedBytes(page, 'Download whole search JSON')).equals(Buffer.from(fixture.files.get('suite.json')!))).toBe(true)
      expect((await downloadedBytes(page, 'Download review manifest')).equals(Buffer.from(fixture.files.get('manifest.json')!))).toBe(true)
      const bounds = await panel.evaluate((element) => ({ right: element.getBoundingClientRect().right, viewport: innerWidth, content: element.scrollWidth, width: element.clientWidth }))
      expect(bounds.right).toBeLessThanOrEqual(bounds.viewport)
      expect(bounds.content).toBeLessThanOrEqual(bounds.width)
      for (const selector of await panel.getByRole('combobox').all()) expect((await selector.boundingBox())!.height).toBeGreaterThanOrEqual(44)
      await expect(panel.getByRole('region', { name: 'Measured and warmup accounting' })).toHaveAttribute('tabindex', '0')
    })
  })
}

test('standalone and suite comparisons retain distinct sources and exact export selections', async ({ page }) => {
  const fixture = await serveReview(page, { standalone: true })
  const standalone = designComparisonFixture()
  const reportBytes = encode(standalone)
  const manifest = { schema_version: 'rc-fiber-design-comparison-bundle.v1', source_revision: standalone.identity.source_revision, report_file: 'comparison.json', report_byte_length: reportBytes.byteLength, report_sha256: identity(reportBytes), report_hash: standalone.report_hash, experiment_identity_hash: standalone.experiment_identity_hash }
  await page.route('**/standalone/manifest.json', (route) => route.fulfill({ json: manifest }))
  await page.route('**/standalone/comparison.json', (route) => route.fulfill({ contentType: 'application/json', body: Buffer.from(reportBytes) }))
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = page.locator('[data-candidate-process="verified"]')
  await expect(panel).toBeVisible()
  await expect(page.getByRole('region', { name: 'Physical design comparison', exact: true })).toBeVisible()
  const entry = fixture.manifest.comparisons.at(-1)!
  await panel.getByRole('combobox', { name: 'Search case', exact: true }).selectOption(entry.case_id)
  await panel.getByRole('combobox', { name: 'Phase', exact: true }).selectOption(entry.phase)
  await panel.getByRole('combobox', { name: 'Repetition', exact: true }).selectOption({ value: String(entry.repetition) })
  await expect(panel.getByRole('combobox', { name: 'Repetition', exact: true })).toHaveValue(String(entry.repetition))
  await panel.getByRole('combobox', { name: 'Search strategy', exact: true }).selectOption(entry.strategy)
  const selected = JSON.parse((await downloadedBytes(page, 'Download selected comparison JSON')).toString('utf8'))
  const exported = JSON.parse((await downloadedBytes(page, 'Export bundle (JSON)')).toString('utf8'))
  expect(exported.physical_design_comparison.report).toEqual(standalone)
  expect(exported.candidate_process_review.suite).toEqual(fixture.suite)
  expect(exported.candidate_process_review.selection).toMatchObject({ case_id: entry.case_id, phase: entry.phase, repetition: entry.repetition, strategy: entry.strategy })
  expect(exported.candidate_process_review.physical_design_comparison.report).toEqual(selected)
  expect(exported.candidate_process_review.selected_run).toEqual(fixture.suite.runs.find((run: Record<string, unknown>) => run.case_id === entry.case_id && run.phase === entry.phase && run.repetition === entry.repetition && run.strategy === entry.strategy))
  await expect(page.locator('#wb2-design-comparison-title')).toHaveCount(1)
  await expect(page.locator('#wb2-candidate-selected-comparison-title')).toHaveCount(1)
})

test('tampered whole-search bytes expose no selected physical rows or downloads', async ({ page }) => {
  await serveReview(page, { corruptSuite: true })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.locator('[data-candidate-process="invalid"]')).toContainText('UNAVAILABLE')
  await expect(page.locator('[data-design-candidate]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Download whole search JSON', exact: true })).toHaveCount(0)
})

test('candidate review without WebCrypto exposes no values or artifact downloads', async ({ page }) => {
  await serveReview(page)
  await page.addInitScript(() => Object.defineProperty(window, 'crypto', { configurable: true, value: undefined }))
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.locator('[data-candidate-process="integrity_unavailable"]')).toContainText('UNAVAILABLE')
  await expect(page.locator('[data-candidate-cost]')).toHaveCount(0)
  await expect(page.locator('[data-design-candidate]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Download (review manifest|whole search JSON|selected comparison)/ })).toHaveCount(0)
})

test('leaving and returning to candidate review cannot publish a delayed prior source', async ({ page }) => {
  // This exercises real component unmount/remount and source replacement, not a numerical run.
  // Runtime configuration is read when RootRouter renders; there is no separate in-place URL editor.
  const oldFixture = await serveReview(page)
  const nextFixture = candidateProcessIncompleteFixture()
  let releaseOld!: () => void
  let enteredOld!: () => void
  let settledOld!: () => void
  const oldEntered = new Promise<void>((resolve) => { enteredOld = resolve })
  const oldReleased = new Promise<void>((resolve) => { releaseOld = resolve })
  const oldSettled = new Promise<void>((resolve) => { settledOld = resolve })
  await page.route('**/candidate-review/suite.json', async (route) => {
    enteredOld()
    await oldReleased
    try { await route.fulfill({ contentType: 'application/json', body: Buffer.from(oldFixture.files.get('suite.json')!) }) }
    finally { settledOld() }
  })
  await page.route('**/candidate-next/**', async (route) => {
    const relative = new URL(route.request().url()).pathname.slice('/candidate-next/'.length)
    const bytes = nextFixture.files.get(relative)
    await route.fulfill({ status: bytes ? 200 : 404, contentType: 'application/json', body: bytes ? Buffer.from(bytes) : '{}' })
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await oldEntered
  await expect(page.locator('[data-candidate-process="loading"]')).toBeVisible()
  const oldAborted = page.waitForEvent('requestfailed', { predicate: (request) => request.url().endsWith('/candidate-review/suite.json') })
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page.locator('[data-legacy-surface]')).toBeVisible()
  await oldAborted
  await page.evaluate(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { candidateSearchProcessUrl: '/candidate-next/manifest.json' } })
  await page.getByRole('link', { name: /return to workbench v2/i }).click()
  const panel = page.locator('[data-candidate-process="verified"]')
  await expect(panel).toBeVisible()
  await expect(panel.locator('[data-candidate-suite-status]')).toHaveText('incomplete')
  releaseOld()
  await oldSettled
  await expect(panel.locator('[data-candidate-suite-status]')).toHaveText('incomplete')
  await expect(panel.locator('[data-candidate-cost="total-requests"]')).toHaveText('UNAVAILABLE')
  expect((await downloadedBytes(page, 'Download whole search JSON')).equals(Buffer.from(nextFixture.files.get('suite.json')!))).toBe(true)
})

test('suite raw downloads remain available when the unrelated live case is missing', async ({ page }) => {
  const fixture = await serveReview(page)
  await page.route('**/evidence/workbench-case.json', (route) => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }))
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.locator('[data-candidate-process="verified"]')).toBeVisible()
  await page.getByRole('button', { name: 'Live', exact: true }).click()
  await expect(page.locator('#wb2-sec-export')).toContainText('Nothing to export until a valid case is loaded.')
  expect((await downloadedBytes(page, 'Download whole search JSON')).equals(Buffer.from(fixture.files.get('suite.json')!))).toBe(true)
})

test('synthetic presentation keeps failed warmups, unknown counts and measured zero distinct', async ({ page }) => {
  // Synthesized failure/coverage metadata around retained numerical rows; not a new solver observation.
  const fixture = await serveReview(page, { incomplete: true })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const panel = page.locator('[data-candidate-process="verified"]')
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('combobox', { name: 'Phase', exact: true }).locator('option')).toHaveText(['Warmup', 'Measured'])
  await expect(panel.locator('[data-candidate-suite-status]')).toHaveText('incomplete')
  await expect(panel.locator('[data-candidate-cost="total-requests"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-cost="declared-slots"]')).toHaveText('18')
  await expect(panel.locator('[data-candidate-cost="observed-workers"]')).toHaveText('11')
  await panel.getByRole('combobox', { name: 'Phase', exact: true }).selectOption('warmup')
  await expect(panel.getByRole('combobox', { name: 'Search strategy', exact: true }).locator('option')).toHaveText(['Deterministic search · not launched', 'Learned search · not launched', 'Full-pool audit · not launched'])
  await expect(panel.locator('[data-candidate-attempt-status]')).toContainText('Not launched')
  await expect(panel.locator('[data-candidate-cost="slot-cpu"]')).toHaveText('0')
  await expect(panel.locator('[data-candidate-cost="worker-cpu"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-phase-cost="warmup"] td').nth(3)).toHaveText('0')
  await expect(panel.locator('[data-candidate-phase-cost="warmup"] td').nth(5)).toHaveText('6')
  await panel.getByRole('combobox', { name: 'Search case', exact: true }).selectOption('pool-b')
  await panel.getByRole('combobox', { name: 'Phase', exact: true }).selectOption('measured')
  await panel.getByRole('combobox', { name: 'Repetition', exact: true }).selectOption({ value: '1' })
  await panel.getByRole('combobox', { name: 'Search strategy', exact: true }).selectOption('oracle')
  await expect(panel.locator('[data-candidate-cost="worker-cpu"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-cost="worker-rss"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-cost="arm-requests"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-cost="input-bytes"]')).toHaveText('UNAVAILABLE')
  await expect(panel.locator('[data-candidate-attempt-failure]')).toContainText('synthetic worker report invalid')
  expect((await downloadedBytes(page, 'Download whole search JSON')).equals(Buffer.from(fixture.files.get('suite.json')!))).toBe(true)
})
