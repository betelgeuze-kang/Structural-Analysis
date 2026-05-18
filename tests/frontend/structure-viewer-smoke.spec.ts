import { expect, test } from '@playwright/test'
import {
  assertCanvasWellFramed,
  installCanvasFrameProbe,
  waitForCanvasNonBlank,
} from '../../scripts/structure-viewer-canvas-frame.mjs'

const baseUrl = process.env.STRUCTURE_VIEWER_BASE_URL ?? 'http://127.0.0.1:4173'
const mode = process.env.STRUCTURE_VIEWER_BROWSER_SMOKE_MODE ?? 'full'

test.setTimeout(120000)

type Viewport = { width: number; height: number }

async function openViewer(page, viewport: Viewport, query: string) {
  await installCanvasFrameProbe(page)
  await page.setViewportSize(viewport)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text())
    }
  })
  await page.goto(`${baseUrl}/src/structure-viewer/index.html?${query}`, {
    timeout: 90000,
    waitUntil: 'commit',
  })
  await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
  await expect(page.locator('#provenance-source-label')).not.toHaveText('--', { timeout: 30000 })
  await page.waitForFunction(() => {
    const canvas = document.querySelector('#viewport canvas') as HTMLCanvasElement | null
    return Boolean(canvas && canvas.width > 10 && canvas.height > 10)
  })
  return errors
}

async function expectNoBrowserErrors(errors: string[]) {
  expect(errors).toEqual([])
}

async function expectCanvasReady(page) {
  await waitForCanvasNonBlank(page)
  const metrics = await assertCanvasWellFramed(page, {
    label: 'structure viewer canvas',
    minCoverageWidth: 0.08,
    minCoverageHeight: 0.1,
    minPixelRatio: 0.001,
  })
  expect(metrics.significantPixelCount).toBeGreaterThan(32)
}

async function openRealDrawingViewer(page, viewport: Viewport) {
  const errors = await openViewer(
    page,
    viewport,
    'preset=real_drawing_private_3d&member=RD-001&drawing_asset=RD-001',
  )
  await expect(page.locator('#real-drawing-quality-panel')).toContainText('RD-', { timeout: 30000 })
  return errors
}

async function openMidas33OptimizedViewer(page, viewport: Viewport) {
  const errors = await openViewer(page, viewport, 'project=midas33_release&drawing=midas33_optimized&variant=optimized')
  await expect(page.locator('#midas33-view-toolbar')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('#project-workspace-section')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('#project-workspace-select')).toContainText('Release Visualization Entries (8)', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('MIDAS33', { timeout: 30000 })
  await expect(page.locator('#stage-variant-chip')).toContainText('Variant optimized', { timeout: 30000 })
  await expect(page.locator('#stage-quality-chip')).toContainText('Review ready', { timeout: 30000 })
  await expect(page.locator('#btn-view-review')).toHaveClass(/active/, { timeout: 30000 })
  await expect(page.locator('#btn-solid')).toHaveClass(/active/, { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('0 issues', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('상용 검토 가능', { timeout: 30000 })
  await expect(page.locator('#before-after-comparison-panel')).toContainText('Member reduction', { timeout: 30000 })
  await expect(page.locator('#before-after-comparison-panel')).toContainText('3D highlight', { timeout: 30000 })
  return errors
}

test('structure viewer renders real drawing stage and supports core controls', async ({ page }) => {
  const errors = await openRealDrawingViewer(page, { width: 1440, height: 1000 })
  await waitForCanvasNonBlank(page)

  await page.locator('#member-search-input').fill('RD-001')
  await expect(page.locator('#search-results')).toContainText('RD-001')
  await page.locator('#btn-solid').click()
  await expect(page.locator('#btn-solid')).toHaveClass(/active/)
  await page.getByRole('button', { name: 'Fit All' }).click()
  await page.getByRole('button', { name: 'Reset' }).click()
  await expect(page.locator('#stage-selection-chip')).toContainText('RD-001')
  await expect(page.locator('#footer-selection-context')).toContainText('selected')
  await expectNoBrowserErrors(errors)
})

test('structure viewer renders MIDAS33 optimized model with view presets and selection', async ({ page }) => {
  const errors = await openMidas33OptimizedViewer(page, { width: 1440, height: 1000 })
  await expectCanvasReady(page)
  await expect(page.locator('#btn-variant-baseline')).toBeEnabled()
  await expect(page.locator('#btn-variant-optimized')).toHaveClass(/is-active/)
  await page.locator('#btn-variant-compare').click()
  await page.waitForURL(/variant=compare/, { timeout: 30000 })
  await expect(page.locator('#btn-variant-compare')).toHaveClass(/is-active/, { timeout: 30000 })
  await expect(page.locator('#project-workspace-status')).toContainText('MIDAS33', { timeout: 30000 })
  await page.locator('#project-workspace-query').fill('roundtrip')
  await expect(page.locator('#project-drawing-list')).toContainText('MIDAS33 Optimized', { timeout: 30000 })
  await expect(page.locator('#project-workspace-status')).toContainText('visible 1/', { timeout: 30000 })
  await page.locator('#project-workspace-query').fill('')
  await expectCanvasReady(page)

  await page.locator('#btn-view-frame').click()
  await expect(page.locator('#btn-view-frame')).toHaveClass(/active/)
  await expectCanvasReady(page)

  await page.locator('#btn-view-plan').click()
  await expect(page.locator('#btn-view-plan')).toHaveClass(/active/)
  await expect(page.locator('#btn-wireframe')).toHaveClass(/active/)
  await waitForCanvasNonBlank(page)

  await page.locator('#btn-view-fit').click()
  await expect(page.locator('#btn-view-fit')).toHaveClass(/active/)
  await waitForCanvasNonBlank(page)

  await page.locator('#btn-view-review').click()
  await expect(page.locator('#btn-view-review')).toHaveClass(/active/)
  await expect(page.locator('#btn-solid')).toHaveClass(/active/)
  await expectCanvasReady(page)

  await page.locator('#member-search-input').fill('911')
  await expect(page.locator('#search-results')).toContainText('911', { timeout: 30000 })
  const firstSearchResult = page.locator('[data-search-focus]').first()
  const selectedMember = await firstSearchResult.getAttribute('data-search-focus')
  await firstSearchResult.click()
  await expect(page.locator('#stage-selection-chip')).toContainText(selectedMember || '911', { timeout: 30000 })
  await expect(page.locator('#footer-selection-context')).toContainText('selected')
  await expect(page.locator('#explainability-panel')).toContainText('Optimization delta', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('MIDAS33', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Members 11,334', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Review Card', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Artifact count verified', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('midas33_optimized_roundtrip.json', { timeout: 30000 })
  await expect(page.locator('#explainability-panel')).toContainText('단면 변경 확인', { timeout: 30000 })
  await expect(page.locator('#explainability-panel')).toContainText('Solver receipt', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Solver Receipt', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText(/solver receipt (verified|pending)/, { timeout: 30000 })
  await page.locator('[data-member-comparison-filter="reduced"]').click()
  await expect(page.locator('#before-after-comparison-panel')).toContainText('Manifest member count delta', { timeout: 30000 })
  await expect(page.locator('#before-after-comparison-panel')).toContainText('active reduced', { timeout: 30000 })
  await expect(page.locator('#before-after-comparison-panel')).toContainText('overlay layer count', { timeout: 30000 })
  await expect(page.locator('.member-comparison-highlight-status')).toHaveAttribute('data-member-comparison-highlight-count', /\d+/, { timeout: 30000 })
  await expect.poll(async () => page.evaluate(() => window.__STRUCTURE_VIEWER_COMPARISON_HIGHLIGHT_STATE__?.filter)).toBe('reduced')
  await expect(page).toHaveURL(/comparison_filter=reduced/)
  await page.locator('[data-member-comparison-overlay="risk_up"]').click()
  await expect.poll(async () => page.evaluate(() => window.__STRUCTURE_VIEWER_COMPARISON_HIGHLIGHT_STATE__?.filter)).toBe('risk_up')
  await expect(page).toHaveURL(/overlay=risk_up/)
  await expect(page.locator('#project-recent-list')).toContainText('member')
  await page.locator('#review-task-status-select').selectOption('approved')
  await page.locator('#review-note-input').fill('smoke review note')
  await page.getByRole('button', { name: 'Save Task' }).click()
  await expect(page.locator('#viewer-report-export-panel')).toContainText('승인', { timeout: 30000 })
  await page.getByRole('button', { name: 'Save Note' }).click()
  await expect(page.locator('#review-note-input')).toHaveValue('smoke review note', { timeout: 30000 })
  await page.locator('#evidence-ingest-source-select').selectOption('csv')
  await page.locator('#evidence-ingest-input').setInputFiles({
    name: 'viewer-evidence.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(`drawing_id,artifact_path,member_count,node_count,element_count,member_id,source_tool,story,frame_section,dcr_after,receipt_path,status\nmidas33_optimized,viewer-evidence.csv,4,6,4,${selectedMember || '911'},ETABS 22,L33,SRC-900,0.93,receipt-911.json,verified\nmidas33_optimized,viewer-evidence.csv,4,6,4,${selectedMember || '911'},ETABS 22,L33,FORCED-MISMATCH,0.99,receipt-912.json,verified\n`),
  })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Evidence Ingest', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('csv · 2 drawings · 0 blocked', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Tool Crosswalk', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('ETABS/SAP2000 2', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('CSV Mapper', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('frame / frame_id / object_id', { timeout: 30000 })
  await expect(page.locator('#viewer-report-export-panel')).toContainText(/section_mismatch|missing_viewer_member|dcr_mismatch/, { timeout: 30000 })
  await page.locator('[data-commercial-crosswalk-member]:not([disabled])').first().click()
  await expect(page.locator('#stage-selection-chip')).toContainText(selectedMember || '911', { timeout: 30000 })
  await page.getByRole('button', { name: 'Isolate Mismatch' }).click()
  await expect(page).toHaveURL(/isolate_kind=member/, { timeout: 30000 })
  await expect(page.locator('#clear-isolate-button')).toBeVisible({ timeout: 30000 })
  await expect.poll(async () => page.evaluate(() => window.__STRUCTURE_VIEWER_LAST_INGEST_PREVIEW__?.drawing_count)).toBe(2)
  await expect(page.locator('#project-workspace-select')).toContainText('Evidence Ingest Preview', { timeout: 30000 })
  await page.getByRole('button', { name: 'Attach Ingest' }).click()
  await expect(page.locator('#viewer-report-export-panel')).toContainText('Evidence Ingest', { timeout: 30000 })
  await expect(page.locator('#project-workspace-select')).toContainText('Evidence Ingest Preview', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('-80.2%', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('verified counts', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('MIDAS33 Optimized Roundtrip', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('Count source', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('midas33_optimized_roundtrip.json', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('Optimized', { timeout: 30000 })
  await page.locator('#evidence-ingest-source-select').selectOption('json')
  await page.locator('#evidence-ingest-input').setInputFiles({
    name: 'viewer-renderable.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({
      drawing_id: 'renderable_json_evidence',
      drawing_title: 'Renderable JSON Evidence',
      artifact_path: 'viewer-renderable.json',
      member_count: 7,
      node_count: 8,
      element_count: 7,
      model: {
        nodes: [
          { id: 1, x: 0, y: 0, z: 0 },
          { id: 2, x: 6, y: 0, z: 0 },
          { id: 3, x: 0, y: 0, z: 8 },
          { id: 4, x: 6, y: 0, z: 8 },
          { id: 5, x: 0, y: 5, z: 0 },
          { id: 6, x: 6, y: 5, z: 0 },
          { id: 7, x: 0, y: 5, z: 8 },
          { id: 8, x: 6, y: 5, z: 8 },
        ],
        elements: [
          {
            id: 'R-1',
            member_id: 'R-1',
            type: 'beam',
            node_ids: [1, 2],
            section: 'JSON-B1',
            material: 'SM490',
            dcr: 0.72,
            before_section: 'JSON-B2',
            after_section: 'JSON-B1',
          },
          {
            id: 'R-2',
            member_id: 'R-2',
            type: 'column',
            node_ids: [2, 4],
            section: 'JSON-C1',
            material: 'SM490',
            dcr: 0.88,
          },
          { id: 'R-3', member_id: 'R-3', type: 'column', node_ids: [1, 3], section: 'JSON-C1', material: 'SM490', dcr: 0.81 },
          { id: 'R-4', member_id: 'R-4', type: 'beam', node_ids: [3, 4], section: 'JSON-B1', material: 'SM490', dcr: 0.67 },
          { id: 'R-5', member_id: 'R-5', type: 'beam', node_ids: [5, 6], section: 'JSON-B1', material: 'SM490', dcr: 0.62 },
          { id: 'R-6', member_id: 'R-6', type: 'column', node_ids: [6, 8], section: 'JSON-C1', material: 'SM490', dcr: 0.91 },
          { id: 'R-7', member_id: 'R-7', type: 'beam', node_ids: [7, 8], section: 'JSON-B1', material: 'SM490', dcr: 0.74 },
        ],
      },
    })),
  })
  await expect(page.locator('#viewer-report-export-panel')).toContainText('renderable direct_model', { timeout: 30000 })
  await expect.poll(async () => page.evaluate(() => window.__STRUCTURE_VIEWER_LAST_INGEST_RENDERABLE_PAYLOAD__?.payload_kind)).toBe('direct_model')
  const downloadPromise = page.waitForEvent('download')
  await page.locator('#report-panel-export-html-button').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toContain('structure_viewer_report_midas33_release_midas33_optimized_compare.html')
  const auditDownloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export Audit' }).click()
  const auditDownload = await auditDownloadPromise
  expect(auditDownload.suggestedFilename()).toContain('structure_viewer_audit_midas33_release_midas33_optimized.jsonl')
  const ingestErrors = await openViewer(
    page,
    { width: 1440, height: 1000 },
    'project=evidence_ingest_preview&drawing=renderable_json_evidence&variant=optimized',
  )
  await expectCanvasReady(page)
  await expect(page.locator('#project-workspace-status')).toContainText('Evidence Ingest Preview', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('Renderable JSON Evidence', { timeout: 30000 })
  await expect(page.locator('#project-drawing-evidence-panel')).toContainText('local evidence ingest preview', { timeout: 30000 })
  await page.locator('#member-search-input').fill('R-1')
  await expect(page.locator('#search-results')).toContainText('R-1', { timeout: 30000 })
  await expect(page.locator('#data-source')).toContainText('viewer-renderable.json', { timeout: 30000 })
  await expectNoBrowserErrors([...errors, ...ingestErrors])
})

test('structure viewer keeps the mobile real drawing workflow usable', async ({ page }) => {
  test.skip(mode === 'minimal', 'minimal smoke runs only the desktop browser paths')
  const errors = await openRealDrawingViewer(page, { width: 390, height: 844 })
  await waitForCanvasNonBlank(page)
  await expect(page.locator('#stage-panel')).toBeVisible()
  await expect(page.locator('#real-drawing-quality-panel')).toContainText('RD-')
  await page.locator('#btn-wireframe').click()
  await expect(page.locator('#btn-wireframe')).toHaveClass(/active/)
  await expectNoBrowserErrors(errors)
})

test('structure viewer keeps the mobile MIDAS33 optimized workflow usable', async ({ page }) => {
  test.skip(mode === 'minimal', 'minimal smoke runs only the desktop browser paths')
  const errors = await openMidas33OptimizedViewer(page, { width: 390, height: 844 })
  await expectCanvasReady(page)
  await page.locator('#btn-view-plan').click()
  await expect(page.locator('#btn-view-plan')).toHaveClass(/active/)
  await expect(page.locator('#btn-wireframe')).toHaveClass(/active/)
  await page.locator('#member-search-input').fill('903')
  await expect(page.locator('#search-results')).toContainText('903', { timeout: 30000 })
  await expectNoBrowserErrors(errors)
})
