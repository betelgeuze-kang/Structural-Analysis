import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { validateDesignComparisonManifest, validateDesignComparisonReport } from '../../src/workbench-v2/model/designComparisonSchema'

for (const width of [1440, 390]) test(`actual centroid-change solve is verified and visible at ${width}px`, async ({ page }) => {
  const raw = gunzipSync(readFileSync('tests/frontend/fixtures/centroid-distance-comparison.json.gz'))
  const report = JSON.parse(raw.toString())
  const manifest = validateDesignComparisonManifest({
    schema_version: 'rc-fiber-design-comparison-bundle.v1', source_revision: report.identity.source_revision,
    report_file: 'comparison.json', report_byte_length: raw.length,
    report_sha256: `sha256:${createHash('sha256').update(raw).digest('hex')}`,
    report_hash: report.report_hash, experiment_identity_hash: report.experiment_identity_hash,
  })
  const checked = validateDesignComparisonReport(report, manifest)
  expect(checked.rows[1].full_reference_verification_pass).toBe(true)
  expect(checked.rows[1].quantities?.totals).toEqual(checked.rows[0].quantities?.totals)
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    Object.defineProperty(window, '__STRUCTURAL_WORKBENCH_CONFIG__', { value: { designComparisonUrl: '/comparisons/manifest.json' } })
  })
  await page.route('**/comparisons/manifest.json', route => route.fulfill({ json: manifest }))
  await page.route('**/comparisons/comparison.json', route => route.fulfill({ contentType: 'application/json', body: raw }))
  await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
  const panel = page.locator('[data-design-comparison="verified"]')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('face-to-steel centroid top/bottom 0.04/0.06 m')
  const description = panel.locator('[data-design-candidate="centroids"] [data-design-section-description]')
  const bounds = await description.boundingBox()
  expect(bounds).not.toBeNull()
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
  await panel.screenshot({ path: `test-results/centroid-distance-${width}.png` })
})
