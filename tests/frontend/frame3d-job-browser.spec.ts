import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'

// GET routes emulate an authenticated same-origin read endpoint. The bytes come
// from the recorded Python execution; this browser test executes no solver.
const fixtureDirectory = 'tests/frontend/fixtures/frame3d-durable-job/'
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
function fixture(directory = fixtureDirectory) {
  const jobBytes = readFileSync(`${directory}job.json`)
  const resultBytes = readFileSync(`${directory}result.json`)
  return {
    jobBytes,
    job: JSON.parse(jobBytes.toString('utf8')),
    resultBytes,
    result: JSON.parse(resultBytes.toString('utf8')),
    evidenceBytes: readFileSync(`${directory}evidence.json`),
    checkpointBytes: readFileSync(`${directory}checkpoint.json`),
  }
}
const cyclic = fixture()
const { job, result, resultBytes, evidenceBytes, checkpointBytes } = cyclic
const statusPath = `/api/v1/jobs/${job.job_id}`
const sessionCookie = 'frame3d-review-session=test-authenticated-session'

test.setTimeout(60000)

async function mockPublishedJob(
  page: Page,
  context: BrowserContext,
  options: { tamperResult?: boolean; source?: ReturnType<typeof fixture> } = {},
): Promise<string[]> {
  const source = options.source ?? cyclic
  const { job, jobBytes, resultBytes, evidenceBytes } = source
  const statusPath = `/api/v1/jobs/${job.job_id}`
  const requests: string[] = []
  await context.addCookies([{
    name: 'frame3d-review-session',
    value: 'test-authenticated-session',
    url: baseUrl,
  }])
  await page.addInitScript((url) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: url }
  }, statusPath)
  await page.route('**/api/v1/jobs/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    requests.push(path)
    expect(request.method()).toBe('GET')
    expect(await request.headerValue('cookie')).toContain(sessionCookie)
    if (path === statusPath) {
      expect(await request.headerValue('accept')).toBe('application/json')
      await route.fulfill({
        contentType: 'application/json',
        body: jobBytes,
      })
    } else if (path === `${statusPath}/result`) {
      expect(await request.headerValue('accept')).toBe(job.result.media_type)
      await route.fulfill({
        contentType: job.result.media_type,
        body: options.tamperResult ? Buffer.concat([resultBytes, Buffer.from('\n')]) : resultBytes,
      })
    } else if (path === `${statusPath}/evidence`) {
      expect(await request.headerValue('accept')).toBe(job.evidence.media_type)
      await route.fulfill({ contentType: job.evidence.media_type, body: evidenceBytes })
    } else {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    }
  })
  return requests
}

async function open(page: Page): Promise<void> {
  await page.goto(`${baseUrl}/#/workbench-v2`, { waitUntil: 'load' })
  await expect(page.locator('[data-wb2-root]')).toBeVisible()
}

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test.describe(`persisted Frame3D review on ${name}`, () => {
    test.use({ viewport })

    test('inspects first/middle/last targets and downloads all three exact artifacts', async ({ page, context }) => {
      const requests = await mockPublishedJob(page, context)
      await open(page)
      const panel = page.locator('[data-frame3d-job-review="verified"]')
      await expect(panel).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Bounded 3D candidate result' })).toBeVisible()
      await expect(panel.locator('[data-frame3d-progress]')).toHaveText('5 of 5 targets completed')
      await expect(panel.locator('[data-frame3d-reserved]')).toHaveText('6')
      await expect(panel.locator('[data-frame3d-confirmed]')).toHaveText('5')
      await expect(panel.locator('[data-frame3d-reservation-gap]')).toContainText('1 reservations without retained confirmation')
      await expect(panel.locator('[data-frame3d-source]')).toHaveText(result.source_revision)

      const selector = panel.getByRole('combobox', { name: 'Authored target to inspect', exact: true })
      await expect(selector).toHaveValue('4')
      await expect(selector.locator('option')).toHaveCount(5)
      const nodeTable = panel.locator('[data-frame3d-node-displacements]')
      await expect(nodeTable.locator('thead th')).toHaveText([
        'Node', 'UX (m)', 'UY (m)', 'UZ (m)', 'RX (rad)', 'RY (rad)', 'RZ (rad)',
      ])
      // Keep the short entity headings readable as words on narrow screens;
      // wide physical tables can scroll inside their own region.
      for (const table of [nodeTable, panel.locator('[data-frame3d-material-states]')]) {
        const headingLines = await table.locator('thead th').first().evaluate((heading) => {
          const range = document.createRange()
          range.selectNodeContents(heading)
          return range.getClientRects().length
        })
        expect(headingLines).toBe(1)
      }
      for (const index of [0, 2, 4]) {
        await selector.selectOption(String(index))
        const receipt = result.receipts[index]
        const selectedResult = receipt.api_result
        await expect(panel.locator('[data-frame3d-selected-target]'))
          .toContainText(`Inspecting target ${index + 1}: ${receipt.authored_target} m`)
        await expect(nodeTable.locator('caption')).toHaveText(`Node displacements · target ${index + 1}`)
        await expect(nodeTable.locator('tbody tr')).toHaveCount(selectedResult.node_displacements.length)
        const controlledNode = selectedResult.node_displacements.find((row: { node_id: string }) => row.node_id === 'N2')
        const controlledRow = nodeTable.locator('tbody tr').filter({ has: page.getByRole('rowheader', { name: 'N2', exact: true }) })
        expect(Number(await controlledRow.locator('td').first().innerText())).toBe(controlledNode.UX_m)

        const reactionTable = panel.locator('[data-frame3d-support-reactions]')
        await expect(reactionTable.locator('caption')).toHaveText(`Support reactions · target ${index + 1}`)
        await expect(reactionTable.locator('tbody tr')).toHaveCount(selectedResult.support_reactions.length)
        for (let rowIndex = 0; rowIndex < selectedResult.support_reactions.length; rowIndex += 1) {
          const expected = selectedResult.support_reactions[rowIndex]
          const row = reactionTable.locator('tbody tr').nth(rowIndex)
          await expect(row.locator('th')).toHaveText(expected.node_id)
          await expect(row.locator('td').nth(0)).toHaveText(expected.dof)
          await expect(row.locator('td').nth(2)).toHaveText(expected.unit)
          const displayed = Number(await row.locator('td').nth(1).innerText())
          // The shared engineering formatter rounds displayed values. Identity
          // and unit assertions remain exact, while values allow display rounding.
          const magnitude = Math.abs(expected.value)
          const displayTolerance = magnitude === 0 ? 0
            : magnitude < 0.001 || magnitude >= 1e6 ? magnitude * 0.00051 : 0.000051
          expect(Math.abs(displayed - expected.value)).toBeLessThanOrEqual(displayTolerance)
        }
        const materials = panel.locator('[data-frame3d-material-states]')
        await expect(materials.locator('caption')).toHaveText(`Material states · target ${index + 1}`)
        for (const material of selectedResult.material_states) {
          await expect(materials).toContainText(material.state_hash)
          await expect(materials).toContainText(material.material_id)
        }
      }

      await expect(panel.locator('[data-frame3d-authority]')).toContainText('false')
      await expect(panel).toContainText('Read-only inspection does not grant Workbench execution authority.')
      await expect(panel.getByRole('button')).toHaveCount(3)
      await expect(panel.locator('input')).toHaveCount(0)
      const bounds = await panel.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1)

      // Inspecting an early receipt must never change the terminal downloads.
      await selector.selectOption('0')
      for (const [label, suffix, expectedBytes] of [
        ['Download result JSON', 'frame3d-result.json', resultBytes],
        ['Download evidence JSON', 'frame3d-evidence.json', evidenceBytes],
        ['Download terminal checkpoint', 'frame3d-terminal-checkpoint.json', checkpointBytes],
      ] as const) {
        const downloaded = page.waitForEvent('download')
        await panel.getByRole('button', { name: label, exact: true }).click()
        const download = await downloaded
        expect(download.suggestedFilename()).toBe(`${job.job_id}-${suffix}`)
        const path = await download.path()
        expect(path).not.toBeNull()
        expect(await readFile(path!)).toEqual(expectedBytes)
      }
      expect(requests.sort()).toEqual([statusPath, `${statusPath}/result`, `${statusPath}/evidence`].sort())
    })

    test('rotational target retains rad units and the RX displacement column', async ({ page, context }) => {
      const source = fixture(`${fixtureDirectory}rotational/`)
      await mockPublishedJob(page, context, { source })
      await open(page)
      const panel = page.locator('[data-frame3d-job-review="verified"]')
      await expect(panel).toBeVisible()
      await expect(panel.locator('[data-frame3d-progress]')).toHaveText('1 of 1 targets completed')
      await expect(panel.getByRole('combobox', { name: 'Authored target to inspect', exact: true })).toHaveValue('0')
      await expect(panel.locator('[data-frame3d-selected-target]')).toContainText('Inspecting target 1: 1.000e-6 rad')
      const nodeTable = panel.locator('[data-frame3d-node-displacements]')
      await expect(nodeTable.locator('thead th').nth(4)).toHaveText('RX (rad)')
      const controlledRow = nodeTable.locator('tbody tr').filter({ has: page.getByRole('rowheader', { name: 'N2', exact: true }) })
      const expected = source.result.receipts[0].api_result.node_displacements
        .find((row: { node_id: string }) => row.node_id === 'N2')
      expect(Number(await controlledRow.locator('td').nth(3).innerText())).toBe(expected.RX_rad)
      expect(expected.RX_rad).toBe(0.000001)
      await expect(panel.locator('[data-frame3d-support-reactions]')).toContainText('kN_m')
      await expect(panel.getByRole('button')).toHaveCount(3)
    })

    test('a changed raw artifact exposes unavailable state without physical tables or downloads', async ({ page, context }) => {
      await mockPublishedJob(page, context, { tamperResult: true })
      await open(page)
      const jobPanel = page.locator('[data-job-service="invalid"]')
      await expect(jobPanel).toBeVisible()
      await expect(jobPanel).toContainText('Durable job status unavailable')
      await expect(jobPanel.locator('[data-state="UNAVAILABLE"]')).toBeVisible()
      await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
      await expect(jobPanel.locator('table')).toHaveCount(0)
      await expect(jobPanel.getByRole('button', { name: /Download/ })).toHaveCount(0)
    })
  })
}
