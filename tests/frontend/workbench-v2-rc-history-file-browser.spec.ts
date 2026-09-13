import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { gunzipSync } from 'node:zlib'

const original = gunzipSync(readFileSync('tests/frontend/fixtures/rc-fiber-history-stream/history.ndjson.gz'))
const rows = original.toString().trimEnd().split('\n')
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`RC history file browser ${viewport.width}`, () => {
    test.use({ viewport })
    test('opens 1010 targets locally, pages material states and downloads exact original bytes', async ({ page }, info) => {
      test.setTimeout(120000)
      const writes: string[] = []
      page.on('request', request => { if (request.method() !== 'GET') writes.push(request.url()) })
      await page.goto(`${baseUrl}/#/workbench-v2`)
      const section = page.locator('[data-rc-history-file]')
      await section.locator('summary').click()
      await section.getByLabel('RC history file (.ndjson, up to 512 MiB)').setInputFiles({ name: 'authored-cyclic.ndjson', mimeType: 'application/x-ndjson', buffer: original })
      await expect(section).toHaveAttribute('data-rc-history-file', 'verified', { timeout: 60000 })
      const panel = section.locator('[data-rc-review="verified"]')
      await expect(panel).toBeVisible()
      await expect(panel.locator('[data-rc-history-status]')).toContainText('complete · 1010/1010')
      await expect(panel.locator('[data-rc-core]')).toHaveText('1011')
      await expect(panel.locator('[data-rc-unknown]')).toContainText('Earlier runs, repeated work')
      await expect(panel.locator('[data-rc-authority]')).toContainText('does not rerun the solver')
      const selector = panel.getByRole('combobox', { name: 'RC target to inspect', exact: true })
      await expect(selector.locator('option')).toHaveCount(1011)
      for (const index of [0, 254, 255, 256, 1010]) {
        await selector.selectOption(String(index))
        const expected = JSON.parse(rows[index + 1]).response
        await expect(panel.locator('[data-rc-selected]')).toContainText(index === 0 ? 'Preload' : `Step ${index + 1}`)
        await expect(panel.locator('[data-rc-table="nodes"] tbody tr').nth(1).locator('td').nth(1)).toHaveText(String(expected.node_displacements[1].UY_m))
        await expect(panel.locator('[data-rc-table="reactions"] tbody tr').first().locator('td').nth(1)).toHaveText(String(expected.support_reactions[0].value_si))
        await expect(panel.locator('[data-rc-table="fibers"] tbody tr')).toHaveCount(expected.fiber_results.length)
      }
      const points = JSON.parse(rows[1]).response.fiber_results
      const materials = panel.getByRole('combobox', { name: 'RC material point history', exact: true })
      const pages = panel.getByRole('combobox', { name: 'Material history steps', exact: true })
      for (const kind of ['steel', 'concrete']) {
        const point = points.find((p: any) => p.material_kind === kind)
        await materials.selectOption(JSON.stringify([point.member_id, point.integration_point_index, point.fiber_index]))
        for (const p of [0, 12, 50]) {
          await expect(pages).toBeVisible()
          await pages.selectOption(String(p))
          const table = panel.locator('[data-rc-table="material-history"] tbody tr')
          const count = Math.min(20, 1011 - p * 20)
          await expect(table).toHaveCount(count)
          for (const local of [0, count - 1]) {
            const expected = JSON.parse(rows[p * 20 + local + 1]).response.fiber_results.find((f: any) => f.member_id === point.member_id
              && f.integration_point_index === point.integration_point_index && f.fiber_index === point.fiber_index)
            await expect(table.nth(local)).toContainText(expected.material_state.state_hash)
          }
        }
      }
      await selector.selectOption('255')
      await expect(panel.locator('[data-rc-selected]')).toContainText('Step 256')
      await selector.scrollIntoViewIfNeeded()
      await page.screenshot({ path: info.outputPath(`history-file-${viewport.width}.png`) })
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1)
      const promise = page.waitForEvent('download')
      await panel.getByRole('button', { name: 'Download RC history', exact: true }).click()
      const download = await promise
      expect(download.suggestedFilename()).toBe('local-history-rc-history.ndjson')
      // Buffer.equals compares the original bytes without enumerating 45 million
      // array properties in the test runner's generic deep-equality matcher.
      expect((await readFile((await download.path())!)).equals(original)).toBe(true)
      expect(writes).toEqual([])
    })
  })
}
test('RC history file browser distinguishes a stored prefix and clears stale results on corrupt replacement', async ({ page }) => {
  await page.goto(`${baseUrl}/#/workbench-v2`)
  const section = page.locator('[data-rc-history-file]')
  await section.locator('summary').click()
  const input = section.getByLabel('RC history file (.ndjson, up to 512 MiB)')
  await input.setInputFiles({ name: 'prefix.ndjson', mimeType: 'application/x-ndjson', buffer: Buffer.from(rows.slice(0, 4).join('\n') + '\n') })
  await expect(section).toHaveAttribute('data-rc-history-file', 'verified')
  await expect(section.locator('[data-rc-history-status]')).toContainText('prefix · 2/1010')
  await input.setInputFiles({ name: 'truncated.ndjson', mimeType: 'application/x-ndjson', buffer: Buffer.from(rows[0] + '\n' + rows[1].slice(0, -10)) })
  await expect(section).toHaveAttribute('data-rc-history-file', 'invalid')
  await expect(section.locator('[data-rc-review="verified"]')).toHaveCount(0)
  await expect(section.getByRole('alert')).toContainText('RC history unavailable')
})
