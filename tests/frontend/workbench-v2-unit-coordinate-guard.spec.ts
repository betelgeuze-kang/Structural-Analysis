import { expect, test, type Page } from '@playwright/test'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

function liveCase(modelOverrides: Record<string, unknown>): Record<string, unknown> {
  return {
    schemaVersion: 'workbench-case.v2',
    provenance: {
      sourcePath: 'tests/live-case.json',
      sourceSha256: 'sha256:test',
      sourceCommitSha: 'test-commit',
      engineVersion: 'test-engine',
      generatedAt: '2026-07-10T00:00:00Z',
    },
    model: {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
      nodeCount: 2,
      elementCount: 1,
      dofCount: 12,
      ...modelOverrides,
    },
    analysis: {
      type: 'linear_static',
      solver: 'test-solver',
      converged: true,
      loadScale: 1,
      iterationCount: 1,
      residualTolerance: 1e-8,
      finalNormalizedResidual: 0,
      finalRelativeIncrement: 0,
      status: 'converged',
    },
    residualHistory: [
      { iteration: 1, residual: 0, relativeIncrement: 0, alpha: 1 },
    ],
  }
}

async function openLiveCase(page: Page, payload: Record<string, unknown>): Promise<void> {
  await page.route('**/evidence/workbench-case.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json; charset=utf-8',
      body: JSON.stringify(payload),
    })
  })
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
  await page.locator('[data-wb2-provider="live"]').click()
}

test.describe('Workbench v2 — engineering semantics guard', () => {
  test('rejects non-SI live cases instead of coercing them to SI', async ({ page }) => {
    await openLiveCase(page, liveCase({ unitSystem: 'US' }))

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /unsupported model\.unitSystem: US \(expected SI\)/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })

  test('rejects unsupported coordinate systems instead of coercing them to global_xyz', async ({ page }) => {
    await openLiveCase(page, liveCase({ coordinateSystem: 'local_y_up' }))

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /unsupported model\.coordinateSystem: local_y_up \(expected global_xyz\)/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })
})
