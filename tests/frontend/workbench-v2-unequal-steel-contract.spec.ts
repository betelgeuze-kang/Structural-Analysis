import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { longitudinalSteelArea, longitudinalSteelDescription } from '../../src/workbench-v2/model/rcSteelLayers'
import { validateDesignComparisonManifest, validateDesignComparisonReport } from '../../src/workbench-v2/model/designComparisonSchema'

const section = { depth_m: 0.4, cover_m: 0.04, top_bar_count: 2, bottom_bar_count: 2, bar_area_m2: 0.00005 }
test('outer areas and intermediate bars retain distinct quantities and descriptions', () => {
  const unequal = { ...section, bottom_bar_area_m2: 0.0002, intermediate_steel_layers: [{ y_m: 0, bar_count: 3 }] }
  expect(longitudinalSteelArea(unequal)).toBeCloseTo(0.00065, 12)
  expect(longitudinalSteelDescription(unequal)).toBe('top 2 × 0.00005 m²; bottom 2 × 0.0002 m²; intermediate 3 × 0.00005 m²')
  expect(longitudinalSteelArea({ ...section, top_bar_area_m2: section.bar_area_m2 })).toBe(longitudinalSteelArea(section))
})
for (const field of ['top_bar_area_m2', 'bottom_bar_area_m2']) {
  for (const value of [null, true, 0, -1, '0.0002', NaN, Infinity]) {
    test(`${field} rejects ${String(value)}`, () => {
      expect(() => longitudinalSteelArea({ ...section, [field]: value })).toThrow()
    })
  }
}
function fixture() {
  const raw = gunzipSync(readFileSync('tests/frontend/fixtures/unequal-steel-comparison.json.gz'))
  const report = JSON.parse(raw.toString())
  const manifest = validateDesignComparisonManifest({
    schema_version: 'rc-fiber-design-comparison-bundle.v1', source_revision: report.identity.source_revision,
    report_file: 'comparison.json', report_byte_length: raw.length,
    report_sha256: `sha256:${createHash('sha256').update(raw).digest('hex')}`,
    report_hash: report.report_hash, experiment_identity_hash: report.experiment_identity_hash,
  })
  return { report, manifest, raw }
}
for (const width of [1440, 390]) test(`actual solver report renders unequal steel at ${width}px`, async ({ page }) => {
  const { report, manifest, raw } = fixture()
  const checked = validateDesignComparisonReport(report, manifest)
  expect(checked.rows[1].quantities?.totals.longitudinal_rebar_mass_kg).toBeCloseTo(56.52, 9)
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    Object.defineProperty(window, '__STRUCTURAL_WORKBENCH_CONFIG__', { value: { designComparisonUrl: '/comparisons/manifest.json' } })
  })
  await page.route('**/comparisons/manifest.json', route => route.fulfill({ json: manifest }))
  await page.route('**/comparisons/comparison.json', route => route.fulfill({ contentType: 'application/json', body: raw }))
  await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
  const panel = page.locator('[data-design-comparison="verified"]')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('top 4 × 0.0002 m²; bottom 4 × 0.0004 m²')
  await panel.screenshot({ path: `test-results/unequal-steel-${width}.png` })
})
test('stale common-area quantity is rejected even when numeric totals agree with each other', () => {
  const { report, manifest } = fixture()
  const q = report.rows[1].quantities
  q.members[0].longitudinal_rebar_volume_m3 = 8 * 0.000387 * 3
  q.members[0].longitudinal_rebar_mass_kg = q.members[0].longitudinal_rebar_volume_m3 * 7850
  q.totals.longitudinal_rebar_volume_m3 = q.members[0].longitudinal_rebar_volume_m3
  q.totals.longitudinal_rebar_mass_kg = q.members[0].longitudinal_rebar_mass_kg
  expect(() => validateDesignComparisonReport(report, manifest)).toThrow()
})

test('distinct face-to-centroid distances retain quantities and bound intermediate bars', () => {
  const asymmetric = { ...section, top_cover_m: 0.08, bottom_cover_m: 0.06 }
  expect(longitudinalSteelArea(asymmetric)).toBe(longitudinalSteelArea(section))
  expect(longitudinalSteelDescription(asymmetric)).toContain('face-to-steel centroid top/bottom 0.08/0.06 m')
  expect(() => longitudinalSteelArea({ ...asymmetric, intermediate_steel_layers: [{ y_m: 0.14, bar_count: 2 }] })).toThrow()
  expect(() => longitudinalSteelArea({ ...asymmetric, intermediate_steel_layers: [{ y_m: -0.15, bar_count: 2 }] })).toThrow()
  expect(longitudinalSteelArea({ ...asymmetric, intermediate_steel_layers: [{ y_m: 0.1, bar_count: 2 }] })).toBeCloseTo(0.0003, 12)
})
for (const field of ['top_cover_m', 'bottom_cover_m']) {
  for (const value of [null, true, 0, -1, '0.04', 0.2, NaN, Infinity]) {
    test(`${field} rejects ${String(value)}`, () => {
      expect(() => longitudinalSteelArea({ ...section, [field]: value })).toThrow()
    })
  }
}
