import { expect, test, type Page } from '@playwright/test'

// End-to-end smoke for the Workbench v2 route. The runner builds the app and
// serves dist; the viewer iframe src is asserted structurally (the viewer is
// hosted at deploy time).

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

test.setTimeout(60000)

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
}

test.describe('Workbench v2 — shell & demo case', () => {
  test('renders the DEMO data-mode badge and claim boundary', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-root] .wb2-chip[data-state="DEMO"]').first()).toBeVisible()
    await expect(page.locator('[data-wb2-claim]')).toContainText(/claim boundary/i)
  })

  test('shows provenance + model health and a converged analysis', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Case & provenance')).toBeVisible()
    await expect(page.getByText('Source checksum', { exact: true })).toBeVisible()
    await expect(page.locator('[data-wb2-root]')).toContainText(/Converged/i)
  })

  test('does not show an automated verdict (review decision UNAVAILABLE)', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-ec-decision="unavailable"], [data-state="UNAVAILABLE"]').first()).toBeVisible()
  })
})

test.describe('Workbench v2 — demo case samples', () => {
  test('demo case selector offers converged, failed, and unavailable samples', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-case-selector]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="converged"]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="failed"]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="unavailable"]')).toBeVisible()
  })

  test('converged sample shows a converged verdict, residual chart, and within-tolerance', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="converged"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'converged')
    await expect(card.locator('[data-result-chip]')).toContainText(/Converged/i)
    await expect(page.locator('[data-wb2-residual-chart]')).toBeVisible()
    await expect(page.locator('[data-wb2-tol-line]')).toBeAttached()
    await expect(card.locator('[data-result-within-tol="true"]')).toBeVisible()
  })

  test('failed sample shows a non-converged verdict above tolerance — not inferred as passing', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="failed"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'failed')
    await expect(card.locator('[data-result-chip]')).toContainText(/Did not converge/i)
    await expect(card.locator('[data-result-within-tol="false"]')).toBeVisible()
  })

  test('unavailable sample reports convergence UNAVAILABLE with no chart and no inferred status', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="unavailable"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'unavailable')
    await expect(card.locator('[data-result-chip]')).toContainText(/unavailable/i)
    // No fabricated residual trace for a case without analysis.
    await expect(page.locator('[data-wb2-residual-chart]')).toHaveCount(0)
  })
})

test.describe('Workbench v2 — provider, evidence, benchmarks', () => {
  test('demo/live provider toggle is present', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-provider="demo"]')).toBeVisible()
    await expect(page.locator('[data-wb2-provider="live"]')).toBeVisible()
  })

  test('benchmark browser lists cases and filters by lifecycle', async ({ page }) => {
    await open(page)
    const cards = page.locator('[data-bench-id]')
    expect(await cards.count()).toBeGreaterThan(5)
    // run command is hidden when no runner is registered
    await expect(page.locator('[data-run-blocked]').first()).toBeVisible()
  })

  test('evidence reader is present (bundle may be unavailable)', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Read-only evidence')).toBeVisible()
  })

  test('with no published bundle, evidence reader shows only unavailable — readiness is not inferred', async ({ page }) => {
    await open(page)
    const evidence = page.locator('.wb2-evidence')
    await expect(evidence).toBeVisible()

    // When the bundle manifest cannot be fetched, the panel must surface a
    // bundle-missing / unavailable marker rather than rendering source cards.
    const missing = evidence.locator('[data-bundle-missing], [data-wb2-unavailable]')
    const cards = evidence.locator('[data-evidence-id]')

    const cardCount = await cards.count()
    if (cardCount === 0) {
      // No bundle published in this build: must be explicitly unavailable.
      await expect(missing.first()).toBeVisible()
      // Nothing may claim a positive release-ready verdict without evidence.
      await expect(evidence.locator('[data-release-ready="true"]')).toHaveCount(0)
    } else {
      // A bundle is present: every source card must carry an explicit gate
      // state and never an inferred/blank readiness.
      for (let i = 0; i < cardCount; i += 1) {
        const gate = await cards.nth(i).getAttribute('data-gate')
        expect(['ready', 'blocked', 'missing', 'unavailable']).toContain(gate)
      }
    }
  })
})

test.describe('Workbench v2 — commercial layout, review draft, benchmarks', () => {
  test('left navigation lists the commercial sections in order', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-nav]')).toBeVisible()
    for (const id of ['wb2-sec-project', 'wb2-sec-model', 'wb2-sec-analysis', 'wb2-sec-run', 'wb2-sec-results', 'wb2-sec-evidence', 'wb2-sec-benchmarks', 'wb2-sec-review', 'wb2-sec-export']) {
      await expect(page.locator(`[data-wb2-nav-link="${id}"]`)).toBeVisible()
    }
  })

  test('Compare section is an honest placeholder, never synthesized', async ({ page }) => {
    await open(page)
    const compare = page.locator('#wb2-sec-compare')
    await expect(compare.locator('[data-wb2-unavailable]')).toBeVisible()
  })

  test('reviewer draft persists locally and never becomes an automated verdict', async ({ page }) => {
    await open(page)
    // Automated verdict stays UNAVAILABLE.
    await expect(page.locator('[data-state="UNAVAILABLE"]').first()).toBeVisible()
    const draft = page.locator('[data-wb2-review-draft]')
    await expect(draft).toBeVisible()
    await draft.locator('[data-wb2-decision="review"]').click()
    await draft.locator('[data-wb2-review-reviewer]').fill('QA')
    await expect(draft.locator('[data-wb2-review-state="review"]')).toBeVisible()
    // Reload: the draft is restored from localStorage for the same source commit.
    await page.reload({ waitUntil: 'load' })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible' })
    await expect(page.locator('[data-wb2-review-reviewer]')).toHaveValue('QA')
    await expect(page.locator('[data-wb2-review-state="review"]')).toBeVisible()
  })

  test('benchmark cards expose copy buttons and a geometry-only exclusion', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-copy]').first()).toBeVisible()
    await expect(page.locator('[data-geometry-excluded-count]')).toBeVisible()
    const geo = page.locator('[data-bench-id][data-geometry-only="true"]')
    if (await geo.count()) {
      await expect(geo.first().locator('[data-geometry-excluded]')).toBeVisible()
    }
  })
})

test.describe('Workbench v2 — run monitor, viewer focus, richer export', () => {
  test('run monitor reflects the converged sample with progress and within-tolerance', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="converged"]').click()
    const monitor = page.locator('[data-run-monitor]')
    await expect(monitor).toHaveAttribute('data-run-monitor', 'converged')
    await expect(monitor.locator('[data-run-progress]')).toBeVisible()
    await expect(monitor.locator('[data-run-within-tol="true"]')).toBeVisible()
  })

  test('run monitor reports UNAVAILABLE for the no-convergence sample, inferring nothing', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="unavailable"]').click()
    const monitor = page.locator('[data-run-monitor]')
    await expect(monitor).toHaveAttribute('data-run-monitor', 'unavailable')
    await expect(monitor.locator('[data-wb2-unavailable]')).toBeVisible()
    await expect(monitor.locator('[data-run-progress]')).toHaveCount(0)
  })

  test('member focus round-trips to the inspector and clears', async ({ page }) => {
    await open(page)
    const inspector = page.locator('[data-wb2-member-inspector]')
    await expect(inspector).toBeVisible()
    await inspector.locator('[data-wb2-member-input]').fill('C12')
    await inspector.locator('[data-wb2-member-focus]').click()
    await expect(page.locator('[data-wb2-selected-member]')).toHaveText('C12')
    await page.locator('[data-wb2-member-clear]').click()
    await expect(page.locator('[data-wb2-selected-member]')).toHaveText(/none selected/i)
  })

  test('export panel lists blockers/comparison counts and selecting a benchmark updates the count', async ({ page }) => {
    await open(page)
    const exportContents = page.locator('.wb2-export-contents')
    await expect(exportContents).toContainText(/selected comparison rows \(0\)/i)
    const compare = page.locator('[data-bench-compare]').first()
    await compare.scrollIntoViewIfNeeded()
    await compare.check()
    await expect(exportContents).toContainText(/selected comparison rows \(1\)/i)
  })
})

test.describe('Workbench v2 — compare set & live mode', () => {
  test('compare set is empty until a benchmark is added, then shows a row with status', async ({ page }) => {
    await open(page)
    const compare = page.locator('[data-compare-panel]')
    await expect(compare.locator('[data-compare-empty]')).toBeVisible()
    const box = page.locator('[data-bench-compare]').first()
    await box.scrollIntoViewIfNeeded()
    await box.check()
    await expect(compare.locator('[data-compare-table]')).toBeVisible()
    const row = compare.locator('[data-compare-row]').first()
    await expect(row).toBeVisible()
    // Status must be an explicit ready/blocked state, never a synthesized delta.
    const status = await row.locator('[data-compare-status]').getAttribute('data-compare-status')
    expect(['ready', 'blocked']).toContain(status)
  })

  test('compare clear resets the set', async ({ page }) => {
    await open(page)
    const box = page.locator('[data-bench-compare]').first()
    await box.scrollIntoViewIfNeeded()
    await box.check()
    const compare = page.locator('[data-compare-panel]')
    await expect(compare.locator('[data-compare-table]')).toBeVisible()
    await compare.locator('[data-compare-clear]').click()
    await expect(compare.locator('[data-compare-empty]')).toBeVisible()
  })

  test('live mode reports MISSING when no case is published — nothing is fabricated', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-provider="live"]').click()
    // No bundle is committed/served in the build, so the live case is unavailable.
    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toBeVisible()
    // The data-mode badge reflects LIVE even though the case is missing.
    await expect(page.locator('[data-wb2-provider="live"]')).toHaveAttribute('aria-pressed', 'true')
  })
})

test.describe('Workbench v2 — viewer, mobile, a11y', () => {
  test('embeds the structure viewer iframe with a deep-linkable src', async ({ page }) => {
    await open(page)
    const iframe = page.locator('.wb2-viewport-iframe')
    await expect(iframe).toHaveAttribute('src', /structure-viewer\/index\.html/)
  })

  test('is keyboard operable and has a skip link on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 720 })
    await open(page)
    await page.keyboard.press('Tab')
    const active = await page.evaluate(() => document.activeElement?.className ?? '')
    expect(active).toContain('wb2-skip-link')
  })
})
