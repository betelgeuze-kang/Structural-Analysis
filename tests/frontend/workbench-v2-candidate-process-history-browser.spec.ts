// Rendering/transport checks over a synthetic profile fixture; no new physics evidence.
import { expect, test } from '@playwright/test'
import { candidateProcessHistoryPredictionFixture } from './candidateProcessHistoryPredictionFixture'
import { waitForCandidateProcess } from './candidateProcessBrowserWait'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
test.setTimeout(120000)

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }],
] as const) test.describe(`history prediction review on ${name}`, () => {
  test.use({ viewport })
  test('shows prediction scope and combined audit while preserving the downloaded source bytes', async ({ page }) => {
    const fixture = candidateProcessHistoryPredictionFixture()
    const requests: string[] = []
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { candidateSearchProcessUrl: '/history-review/manifest.json' }
    })
    await page.route('**/history-review/**', async route => {
      expect(route.request().method()).toBe('GET')
      const relative = new URL(route.request().url()).pathname.slice('/history-review/'.length)
      requests.push(relative)
      const bytes = fixture.files.get(relative)
      await route.fulfill({ status: bytes ? 200 : 404, contentType: 'application/json', body: bytes ? Buffer.from(bytes) : '{}' })
    })
    await page.goto(`${baseUrl}/#/workbench-v2`)
    const panel = await waitForCandidateProcess(page)
    await expect(panel.locator('[data-candidate-prediction-scope]')).toContainText('History and material prediction')
    await expect(panel.locator('[data-candidate-prediction-scope]')).toContainText('Full reference checks')
    await panel.getByRole('combobox', { name: 'Search strategy', exact: true }).selectOption('learned')
    await expect(panel.locator('[data-design-comparison="verified"]')).toBeVisible()
    await panel.locator('[data-candidate-paired-outcomes] > summary').click()
    await expect(panel.locator('[data-candidate-combined-false-safe]').first()).toBeVisible()
    for (const summary of fixture.suite.case_summaries as any[]) for (const pair of summary.measured_pairs) {
      const key = `${summary.case_id}:${pair.repetition}:learned`
      await expect(panel.locator(`[data-candidate-combined-false-safe="${key}"]`)).toHaveText(String(pair.oracle_audit.learned.combined_false_safe_count))
      await expect(panel.locator(`[data-candidate-combined-unverifiable="${key}"]`)).toHaveText(String(pair.oracle_audit.learned.combined_predicted_safe_unverifiable_count))
      await expect(panel.locator(`[data-candidate-combined-false-safe="${summary.case_id}:${pair.repetition}:deterministic"]`)).toHaveText('Not applicable')
    }
    const requestedBeforeDownload = requests.length
    const pending = page.waitForEvent('download')
    await panel.getByRole('button', { name: 'Download whole search JSON', exact: true }).click()
    const stream = await (await pending).createReadStream()
    expect(stream).not.toBeNull()
    const chunks: Buffer[] = []
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
    expect(Buffer.concat(chunks)).toEqual(Buffer.from(fixture.files.get('suite.json')!))
    expect(requests.length).toBe(requestedBeforeDownload)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
  })
})
