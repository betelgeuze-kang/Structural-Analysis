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
  await expect(page.locator('[data-shell-project-select]')).toHaveValue('midas33_release::midas33_optimized', { timeout: 30000 })
  await expect(page.locator('[data-shell-project-receipt]')).toContainText('optimized', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('MIDAS33', { timeout: 30000 })
  await expect(page.locator('#stage-variant-chip')).toContainText('Variant optimized', { timeout: 30000 })
  await expect(page.locator('#stage-quality-chip')).toContainText('Review ready', { timeout: 30000 })
  await expect(page.locator('#btn-view-review')).toHaveClass(/active/, { timeout: 30000 })
  await expect(page.locator('#btn-contour')).toHaveClass(/active/, { timeout: 30000 })
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
  await expect(page.locator('#btn-contour')).toHaveClass(/active/)
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

test('structure viewer keeps dense desktop cockpit regions readable', async ({ page }) => {
  const errors = await openMidas33OptimizedViewer(page, { width: 1600, height: 900 })
  await expectCanvasReady(page)
  await page.locator('[data-stage-callout-focus-member]').first().click()
  await page.waitForFunction(() => {
    const badge = document.querySelector('[data-viewport-selection-focus-badge]')
    return Boolean(badge?.classList.contains('is-visible'))
  }, null, { timeout: 10000 })
  const firstScheduleStep = page.locator('[data-result-step-schedule] [data-result-step-row]').first()
  await expect(firstScheduleStep).toBeVisible({ timeout: 10000 })
  const clickedStep = await firstScheduleStep.getAttribute('data-result-step')
  await firstScheduleStep.click()
  if (clickedStep) {
    await expect(page.locator('[data-result-step-schedule] [data-result-step-active="true"]')).toHaveAttribute('data-result-step', clickedStep)
  }

  const layout = await page.evaluate(() => {
    const rectFor = (selector: string) => {
      const node = document.querySelector(selector)
      if (!(node instanceof HTMLElement)) return null
      const rect = node.getBoundingClientRect()
      return {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      }
    }
    const overlapArea = (a: ReturnType<typeof rectFor>, b: ReturnType<typeof rectFor>) => {
      if (!a || !b) return 0
      return Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
        * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
    }
    const viewport = rectFor('#viewport')
    const footer = rectFor('.instrument-footer')
    const chartStrip = rectFor('#analysis-cockpit-chart-strip')
    const rightPanel = rectFor('#right-panel')
    const stageFrame = rectFor('.stage-frame')
    const callouts = rectFor('[data-stage-result-callouts]')
    const stageReceipt = rectFor('#stage-result-receipt')
    const stageOverlayReceipt = rectFor('[data-stage-overlay-receipt]')
    const stageLoadSupportGlyphs = rectFor('[data-stage-load-support-glyphs]')
    const stageReviewControls = rectFor('[data-stage-review-controls]')
    const stageOverlayPanel = rectFor('.stage-overlay-panel--left')
    const contourSection = rectFor('#contour-section')
    const contourScale = rectFor('[data-contour-scale-evidence]')
    const loadCasesSection = rectFor('#loadcases-section')
    const stageStoryRuler = rectFor('[data-stage-story-ruler]')
    const stageDriftBands = rectFor('[data-stage-drift-bands]')
    const stageCriticalHotspots = rectFor('[data-stage-critical-hotspots]')
    const focusBadge = rectFor('[data-viewport-selection-focus-badge]')
    const optimizationDeltaStrip = rectFor('[data-optimization-delta-strip]')
    const criticalTriage = rectFor('[data-critical-triage]')
    const panelZoneStageBadge = rectFor('[data-panel-zone-stage-badge]')
    const toolRail = rectFor('[data-viewport-tool-rail]')
    const topRunControl = rectFor('[data-top-run-control]')
    const topProjectSelect = document.querySelector('[data-shell-project-select]') as HTMLSelectElement | null
    const stageOverlayBudgetSelectors = [
      '[data-stage-result-callouts]',
      '[data-stage-drift-band]',
      '[data-stage-critical-hotspot]',
      '[data-panel-zone-stage-badge]',
      '[data-stage-story-ruler-row]',
      '[data-stage-overlay-receipt]',
      '[data-viewport-selection-focus-badge].is-visible',
    ]
    const overlayBudgetRects = stageOverlayBudgetSelectors.flatMap((selector) => {
      return [...document.querySelectorAll(selector)].flatMap((node) => {
        if (!(node instanceof HTMLElement)) return []
        const style = getComputedStyle(node)
        const rect = node.getBoundingClientRect()
        if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) return []
        return [{
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        }]
      })
    })
    const stageCentralClearRect = viewport
      ? {
        left: viewport.left + viewport.width * 0.25,
        right: viewport.left + viewport.width * 0.75,
        top: viewport.top + viewport.height * 0.18,
        bottom: viewport.top + viewport.height * 0.82,
        width: viewport.width * 0.5,
        height: viewport.height * 0.64,
      }
      : null
    const overlayViewportArea = overlayBudgetRects.reduce((total, rect) => total + overlapArea(rect, viewport), 0)
    const overlayCentralArea = overlayBudgetRects.reduce((total, rect) => total + overlapArea(rect, stageCentralClearRect), 0)
    return {
      appOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      stageOverlayOcclusionBudget: document.querySelector('#viewport')?.getAttribute('data-stage-overlay-occlusion-budget') || '',
      stageOverlayBudgetNodeCount: overlayBudgetRects.length,
      stageOverlayViewportOcclusionRatio: viewport ? overlayViewportArea / Math.max(1, viewport.width * viewport.height) : 1,
      stageOverlayCentralOcclusionRatio: stageCentralClearRect ? overlayCentralArea / Math.max(1, stageCentralClearRect.width * stageCentralClearRect.height) : 1,
      topbar: rectFor('.app-topbar'),
      topProjectSelect: rectFor('[data-shell-project-select]'),
      topProjectOptionCount: topProjectSelect?.options.length || 0,
      topProjectValue: topProjectSelect?.value || '',
      topProjectProjectId: topProjectSelect?.dataset.projectId || '',
      topProjectDrawingId: topProjectSelect?.dataset.drawingId || '',
      topProjectVariant: topProjectSelect?.dataset.variant || '',
      topProjectReceipt: document.querySelector('[data-shell-project-receipt]')?.textContent || '',
      topProjectOverflow: [...document.querySelectorAll('[data-topbar-project-selector], .topbar-context-strip')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      topRunControl,
      topRunActionCount: document.querySelectorAll('[data-top-run-control] [data-top-run-action]').length,
      topRunVisibleActionCount: [...document.querySelectorAll('[data-top-run-control] [data-top-run-action]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return getComputedStyle(node).display !== 'none' && node.offsetParent !== null
      }).length,
      topRunReceiptRowCount: document.querySelectorAll('[data-top-run-receipt] span').length,
      topRunStatus: document.querySelector('[data-top-run-control]')?.getAttribute('data-run-status') || '',
      topRunLoadCase: document.querySelector('[data-top-run-control]')?.getAttribute('data-run-load-case') || '',
      topRunStep: document.querySelector('[data-top-run-control]')?.getAttribute('data-run-step') || '',
      topRunSolver: document.querySelector('[data-top-run-control]')?.getAttribute('data-run-solver') || '',
      topRunComparePressed: document.querySelector('#top-run-compare-button')?.getAttribute('aria-pressed') || '',
      topRunPrimaryStatus: document.querySelector('#top-run-new-button')?.getAttribute('data-run-status') || '',
      topRunOverflowCount: [...document.querySelectorAll('[data-top-run-control], [data-top-run-control] [data-top-run-action], [data-top-run-receipt] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      modelOverviewStatus: document.querySelector('[data-model-overview-panel]')?.getAttribute('data-model-overview-status') || '',
      modelOverviewHeightM: Number(document.querySelector('[data-model-overview-panel]')?.getAttribute('data-model-height-m') || '0'),
      modelOverviewUnits: document.querySelector('[data-model-overview-panel]')?.getAttribute('data-model-units') || '',
      modelOverviewAnalysisType: document.querySelector('[data-model-overview-panel]')?.getAttribute('data-model-analysis-type') || '',
      modelOverviewLastRun: document.querySelector('[data-model-overview-panel]')?.getAttribute('data-model-last-run') || '',
      sourceAdapterStatus: document.querySelector('[data-source-adapter-matrix]')?.getAttribute('data-source-adapter-status') || '',
      sourceAdapterSchema: document.querySelector('[data-source-adapter-matrix]')?.getAttribute('data-source-adapter-schema') || '',
      sourceAdapterCount: document.querySelectorAll('[data-source-adapter-row]').length,
      sourceAdapterCurrentCount: document.querySelectorAll('[data-source-adapter-row][data-source-adapter-status="current"]').length,
      sourceAdapterActiveKey: document.querySelector('[data-source-adapter-matrix]')?.getAttribute('data-active-source-adapter') || '',
      sourceAdapterHasMidas: Boolean(document.querySelector('[data-source-adapter-row][data-source-adapter-key="midas"]')),
      modelInfoRowCount: document.querySelectorAll('[data-model-info-grid] span:nth-child(odd)').length,
      modelInfoHasHeight: (document.querySelector('#shell-meta-height')?.textContent || '').includes('m'),
      modelInfoHasUnits: (document.querySelector('#shell-meta-units')?.textContent || '').trim().length > 0,
      modelInfoHasAnalysis: (document.querySelector('#shell-meta-analysis-type')?.textContent || '').trim().length > 0,
      modelOverviewOverflowCount: [...document.querySelectorAll('[data-model-overview-panel], [data-source-adapter-row], [data-model-info-grid] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      viewport,
      footer,
      chartStrip,
      rightPanel,
      stageFrame,
      callouts,
      focusBadge,
      toolRail,
      stageOverlayReceipt,
      stageOverlayPanel,
      stageReviewControls,
      stageReviewModeValue: (document.querySelector('[data-stage-view-mode-select]') as HTMLSelectElement | null)?.value || '',
      stageReviewPresetValue: (document.querySelector('[data-stage-view-preset-select]') as HTMLSelectElement | null)?.value || '',
      stageReviewSelectCount: document.querySelectorAll('[data-stage-review-controls] select').length,
      stageReviewModelRowCount: document.querySelectorAll('[data-stage-model-stack] [data-stage-model-layer]').length,
      stageReviewComparePressed: document.querySelector('#stage-model-compare-toggle')?.getAttribute('aria-pressed') || '',
      stageDeformationStatus: document.querySelector('[data-stage-deformation-control]')?.getAttribute('data-deformation-control-status') || '',
      stageDeformationSchema: document.querySelector('[data-stage-deformation-control]')?.getAttribute('data-deformation-control-schema') || '',
      stageDeformationDisplayScale: Number(document.querySelector('[data-stage-deformation-control]')?.getAttribute('data-deformation-display-scale') || '0'),
      stageDeformationInternalScale: Number(document.querySelector('[data-stage-deformation-control]')?.getAttribute('data-deformation-internal-scale') || '0'),
      stageDeformationSliderValue: Number((document.querySelector('[data-stage-deformation-scale-slider]') as HTMLInputElement | null)?.value || '0'),
      stageDeformationLabel: (document.querySelector('[data-stage-deformation-control]')?.textContent || '').trim(),
      stageDeformationOverflowCount: [...document.querySelectorAll('[data-stage-deformation-control], [data-stage-deformation-control] span, [data-stage-deformation-control] strong')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageReviewReceiptRowCount: document.querySelectorAll('[data-stage-review-control-receipt] .stage-review-control-receipt__row').length,
      stageReviewReceiptHasScale: (document.querySelector('[data-stage-review-control-receipt]')?.textContent || '').includes('Scale'),
      stageReviewOverflow: (() => {
        const node = document.querySelector('[data-stage-review-controls]')
        if (!(node instanceof HTMLElement)) return 1
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2 ? 1 : 0
      })(),
      contourScaleTickCount: document.querySelectorAll('[data-contour-scale-ticks] [data-contour-scale-tick]').length,
      contourSection,
      contourScale,
      loadCasesSection,
      contourScalePriority: document.querySelector('#contour-section')?.getAttribute('data-stage-results-priority') || '',
      loadCasesPriority: document.querySelector('#loadcases-section')?.getAttribute('data-stage-loadcases-priority') || '',
      contourScaleVisibleArea: overlapArea(contourScale, stageFrame),
      contourScalePanelVisibleArea: overlapArea(contourScale, stageOverlayPanel),
      contourScaleUnit: document.querySelector('[data-contour-scale-evidence]')?.getAttribute('data-contour-unit') || '',
      contourScaleSource: document.querySelector('[data-contour-scale-evidence]')?.getAttribute('data-scalar-source') || '',
      contourScaleMin: Number(document.querySelector('[data-contour-scale-evidence]')?.getAttribute('data-contour-min') || '0'),
      contourScaleMax: Number(document.querySelector('[data-contour-scale-evidence]')?.getAttribute('data-contour-max') || '0'),
      contourScaleGradientPresent: Boolean((document.querySelector('[data-contour-colorbar]') as HTMLElement | null)?.style.background),
      contourScaleOverflow: (() => {
        const node = document.querySelector('[data-contour-scale-evidence]')
        if (!(node instanceof HTMLElement)) return 1
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2 ? 1 : 0
      })(),
      stageOverlayStatus: document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-overlay-status') || '',
      stageOverlayArrowCount: Number(document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-load-arrow-count') || '0'),
      stageOverlaySupportCount: Number(document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-support-marker-count') || '0'),
      stageOverlaySource: document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-overlay-source') || '',
      stageOverlayLoadCase: document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-overlay-load-case') || '',
      stageOverlayVisibleEvidenceCount: Number(document.querySelector('[data-stage-overlay-receipt]')?.getAttribute('data-visible-evidence-count') || '0'),
      stageOverlayVisualArrowCount: Number(document.querySelector('[data-stage-overlay-visual-evidence]')?.getAttribute('data-load-arrow-visible-count') || '0'),
      stageOverlayVisualSupportCount: Number(document.querySelector('[data-stage-overlay-visual-evidence]')?.getAttribute('data-support-marker-visible-count') || '0'),
      stageOverlayVisualItemCount: document.querySelectorAll('[data-stage-overlay-visual-evidence] .stage-overlay-visual-evidence__item').length,
      stageOverlayLoadSwatchCount: document.querySelectorAll('[data-stage-overlay-load-key] .stage-overlay-legend-swatch--load').length,
      stageOverlaySupportSwatchCount: document.querySelectorAll('[data-stage-overlay-support-key] .stage-overlay-legend-swatch--support').length,
      stageOverlayWindowState: window.__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__ || null,
      stageLoadSupportGlyphs,
      stageLoadSupportGlyphStatus: document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-load-support-glyphs-status') || '',
      stageLoadSupportGlyphSchema: document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-load-support-glyphs-schema') || '',
      stageLoadGlyphCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-load-glyph-count') || '0'),
      stageSupportGlyphCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-support-glyph-count') || '0'),
      stageSupportGlyphSourceCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-support-source-count') || '0'),
      stageLoadProjectedCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-load-projected-count') || '0'),
      stageSupportProjectedCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-support-projected-count') || '0'),
      stageLoadSupportProjectedCount: Number(document.querySelector('[data-stage-load-support-glyphs]')?.getAttribute('data-stage-load-support-projected-count') || '0'),
      stageLoadGlyphVisibleCount: [...document.querySelectorAll('[data-stage-load-glyph]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        const rect = node.getBoundingClientRect()
        return rect.width > 0 && rect.height > 0 && getComputedStyle(node).display !== 'none'
      }).length,
      stageSupportGlyphVisibleCount: [...document.querySelectorAll('[data-stage-support-glyph]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        const rect = node.getBoundingClientRect()
        return rect.width > 0 && rect.height > 0 && getComputedStyle(node).display !== 'none'
      }).length,
      stageLoadGlyphProjectionCount: document.querySelectorAll('[data-stage-load-glyph-projection]').length,
      stageSupportGlyphProjectionCount: document.querySelectorAll('[data-stage-support-glyph-projection]').length,
      stageLoadSupportGlyphVisible: Boolean(document.querySelector('[data-stage-load-support-glyphs]')?.classList.contains('is-visible')),
      stageLoadSupportGlyphWindowState: window.__STRUCTURE_VIEWER_STAGE_LOAD_SUPPORT_GLYPHS_STATE__ || null,
      stageLoadSupportGlyphOverflowCount: [...document.querySelectorAll('[data-stage-load-glyph], [data-stage-support-glyph], [data-stage-load-glyph] b')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageOverlayVisualOverflow: (() => {
        const node = document.querySelector('[data-stage-overlay-visual-evidence]')
        if (!(node instanceof HTMLElement)) return 1
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2 ? 1 : 0
      })(),
      stageOverlayOverflow: (() => {
        const node = document.querySelector('[data-stage-overlay-receipt]')
        if (!(node instanceof HTMLElement)) return 1
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2 ? 1 : 0
      })(),
      toolRailGroupCount: document.querySelectorAll('[data-viewport-tool-group]').length,
      toolRailButtonCount: document.querySelectorAll('[data-viewport-tool]').length,
      toolRailTooltipCount: document.querySelectorAll('[data-viewport-tool][data-tooltip]').length,
      toolRailRenderModeCount: document.querySelectorAll('[data-viewport-tool-render-mode]').length,
      toolRailViewPresetCount: document.querySelectorAll('[data-viewport-view-preset]').length,
      toolRailPressedCount: document.querySelectorAll('[data-viewport-tool][aria-pressed="true"]').length,
      toolRailContourActive: Boolean(document.querySelector('[data-viewport-tool-render-mode="contour"].is-active')),
      toolRailReviewActive: Boolean(document.querySelector('[data-viewport-view-preset="review"].is-active')),
      toolRailOverflowCount: [...document.querySelectorAll('[data-viewport-tool]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      kpiCount: document.querySelectorAll('#kpi-summary-panel .kpi-card').length,
      kpiEvidenceCount: document.querySelectorAll('#kpi-summary-panel .kpi-card__evidence').length,
      kpiReferenceCount: document.querySelectorAll('#kpi-summary-panel .kpi-card__reference').length,
      kpiTrendCount: document.querySelectorAll('#kpi-summary-panel .kpi-card__trend').length,
      kpiSparkAreaCount: document.querySelectorAll('#kpi-summary-panel .kpi-sparkline__area').length,
      kpiSparkDotCount: document.querySelectorAll('#kpi-summary-panel .kpi-sparkline__dot').length,
      kpiFullLabelCount: document.querySelectorAll('#kpi-summary-panel [data-kpi-full-label]').length,
      kpiLabelEllipsisCount: [...document.querySelectorAll('#kpi-summary-panel .kpi-card__label')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return window.getComputedStyle(node).textOverflow === 'ellipsis'
      }).length,
      kpiLabelOverflowCount: [...document.querySelectorAll('#kpi-summary-panel .kpi-card__label')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      kpiFullLabelText: [...document.querySelectorAll('#kpi-summary-panel [data-kpi-full-label]')]
        .map((node) => node.getAttribute('data-kpi-full-label') || '')
        .join(' | '),
      kpiFullValueCount: document.querySelectorAll('#kpi-summary-panel [data-kpi-full-value]').length,
      kpiValueNumberCount: document.querySelectorAll('#kpi-summary-panel .kpi-card__value-number').length,
      kpiValueUnitCount: document.querySelectorAll('#kpi-summary-panel .kpi-card__value-unit').length,
      kpiValueEllipsisCount: [...document.querySelectorAll('#kpi-summary-panel .kpi-card__value')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return window.getComputedStyle(node).textOverflow === 'ellipsis'
      }).length,
      kpiValueOverflowCount: [...document.querySelectorAll('#kpi-summary-panel .kpi-card__value, #kpi-summary-panel .kpi-card__value-number, #kpi-summary-panel .kpi-card__value-unit')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      kpiOverflowCount: [...document.querySelectorAll('#kpi-summary-panel .kpi-card')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      resultEvidenceStatus: document.querySelector('[data-analysis-result-evidence]')?.getAttribute('data-result-evidence-status') || '',
      resultEvidenceSourceMetricCount: Number(document.querySelector('[data-analysis-result-evidence]')?.getAttribute('data-source-metric-count') || '0'),
      resultEvidenceEstimateMetricCount: Number(document.querySelector('[data-analysis-result-evidence]')?.getAttribute('data-estimate-metric-count') || '0'),
      resultEvidenceTotalMetricCount: Number(document.querySelector('[data-analysis-result-evidence]')?.getAttribute('data-total-metric-count') || '0'),
      resultEvidenceCoveragePct: Number(document.querySelector('[data-analysis-result-evidence]')?.getAttribute('data-source-coverage-pct') || '0'),
      resultEvidenceRowCount: document.querySelectorAll('[data-analysis-result-evidence] [data-result-evidence-row]').length,
      resultEvidenceOverflowCount: [...document.querySelectorAll('[data-analysis-result-evidence], [data-analysis-result-evidence] [data-result-evidence-row]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      optimizationDeltaStrip,
      optimizationDeltaStripStatus: document.querySelector('[data-optimization-delta-strip]')?.getAttribute('data-optimization-delta-strip-status') || '',
      optimizationDeltaStripSchema: document.querySelector('[data-optimization-delta-strip]')?.getAttribute('data-optimization-delta-strip-schema') || '',
      optimizationDeltaStripRowCount: Number(document.querySelector('[data-optimization-delta-strip]')?.getAttribute('data-optimization-delta-strip-row-count') || '0'),
      optimizationDeltaStripReductionCount: Number(document.querySelector('[data-optimization-delta-strip]')?.getAttribute('data-optimization-delta-strip-reduction-count') || '0'),
      optimizationDeltaStripMaxReductionPct: Number(document.querySelector('[data-optimization-delta-strip]')?.getAttribute('data-optimization-delta-strip-max-reduction-pct') || '0'),
      optimizationDeltaStripRows: document.querySelectorAll('[data-optimization-delta-strip] [data-optimization-delta-row]').length,
      optimizationDeltaStripAfterBarCount: document.querySelectorAll('[data-optimization-delta-strip] .optimization-delta-tile__bar-after').length,
      optimizationDeltaStripDeltaCount: document.querySelectorAll('[data-optimization-delta-strip] .optimization-delta-tile__foot strong').length,
      optimizationDeltaStripText: document.querySelector('[data-optimization-delta-strip]')?.textContent || '',
      optimizationDeltaStripWindowState: window.__STRUCTURE_VIEWER_OPTIMIZATION_DELTA_STRIP_STATE__ || null,
      optimizationDeltaStripOverflowCount: [...document.querySelectorAll('[data-optimization-delta-strip], [data-optimization-delta-strip] [data-optimization-delta-row], [data-optimization-delta-strip] .optimization-delta-strip__head')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      resultStepScheduleStatus: document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-schedule-status') || '',
      resultStepScheduleRowCount: document.querySelectorAll('[data-result-step-schedule] [data-result-step-row]').length,
      resultStepScheduleActiveCount: document.querySelectorAll('[data-result-step-schedule] [data-result-step-active="true"]').length,
      resultStepScheduleActiveStep: Number(document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-active') || '0'),
      resultStepScheduleTotal: Number(document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-total') || '0'),
      resultStepScheduleLoadCase: document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-load-case') || '',
      resultStepScheduleConvergence: document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-convergence') || '',
      resultStepScheduleSolver: document.querySelector('[data-result-step-schedule]')?.getAttribute('data-result-step-solver') || '',
      resultStepScheduleCurrentStep: document.querySelector('[data-result-step-schedule] [aria-current="step"]')?.getAttribute('data-result-step') || '',
      resultStepScheduleOverflowCount: [...document.querySelectorAll('[data-result-step-schedule], [data-result-step-schedule] [data-result-step-row], [data-result-step-schedule] .result-step-schedule__head span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      resultEnvelopeStatus: document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-status') || '',
      resultEnvelopeRowCount: document.querySelectorAll('[data-result-envelope] [data-result-envelope-row]').length,
      resultEnvelopeLoadCase: document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-load-case') || '',
      resultEnvelopeActiveStep: Number(document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-active-step') || '0'),
      resultEnvelopeTotalSteps: Number(document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-total-steps') || '0'),
      resultEnvelopeGoverningMember: document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-governing-member') || '',
      resultEnvelopeSourceMetricCount: Number(document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-source-metric-count') || '0'),
      resultEnvelopeTotalMetricCount: Number(document.querySelector('[data-result-envelope]')?.getAttribute('data-result-envelope-total-metric-count') || '0'),
      resultEnvelopeHasDisplacement: Boolean(document.querySelector('[data-result-envelope-key="displacement"]')),
      resultEnvelopeHasDrift: Boolean(document.querySelector('[data-result-envelope-key="drift"]')),
      resultEnvelopeHasBaseShear: Boolean(document.querySelector('[data-result-envelope-key="base-shear"]')),
      resultEnvelopeHasUtilization: Boolean(document.querySelector('[data-result-envelope-key="utilization"]')),
      resultEnvelopeMemberRowCount: document.querySelectorAll('[data-result-envelope] [data-result-envelope-member-id]').length,
      resultEnvelopeOverflowCount: [...document.querySelectorAll('[data-result-envelope], [data-result-envelope] [data-result-envelope-row], [data-result-envelope] .result-envelope__head')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      criticalTriage,
      criticalTriageStatus: document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-status') || '',
      criticalTriageSchema: document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-schema') || '',
      criticalTriageRowCount: Number(document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-row-count') || '0'),
      criticalTriageSourceCount: Number(document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-source-count') || '0'),
      criticalTriageHighCount: Number(document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-high-count') || '0'),
      criticalTriageMaxRatio: Number(document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-max-ratio') || '0'),
      criticalTriageRows: document.querySelectorAll('[data-critical-triage] [data-critical-triage-row]').length,
      criticalTriageMemberRows: document.querySelectorAll('[data-critical-triage] [data-critical-triage-member-id]').length,
      criticalTriageStatusCount: document.querySelectorAll('[data-critical-triage] .critical-triage-row__status').length,
      criticalTriageActionCount: document.querySelectorAll('[data-critical-triage] .critical-triage-row__action').length,
      criticalTriageText: document.querySelector('[data-critical-triage]')?.textContent || '',
      criticalTriageWindowState: window.__STRUCTURE_VIEWER_CRITICAL_TRIAGE_STATE__ || null,
      criticalTriageOverflowCount: [...document.querySelectorAll('[data-critical-triage], [data-critical-triage] [data-critical-triage-row], [data-critical-triage] .critical-triage__head')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageStoryRuler,
      stageStoryRulerStatus: document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-ruler-status') || '',
      stageStoryRulerSchema: document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-ruler-schema') || '',
      stageStoryRulerRowCount: Number(document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-ruler-row-count') || '0'),
      stageStoryRulerStoryCount: Number(document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-count') || '0'),
      stageStoryRulerHeightM: Number(document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-height-m') || '0'),
      stageStoryRulerProjectedCount: Number(document.querySelector('[data-stage-story-ruler]')?.getAttribute('data-stage-story-projected-count') || '0'),
      stageStoryRulerVisible: Boolean(document.querySelector('[data-stage-story-ruler]')?.classList.contains('is-visible')),
      stageStoryRulerWindowState: window.__STRUCTURE_VIEWER_STAGE_STORY_RULER_STATE__ || null,
      stageStoryRulerText: document.querySelector('[data-stage-story-ruler]')?.textContent || '',
      stageStoryRulerOverflowCount: [...document.querySelectorAll('[data-stage-story-ruler], [data-stage-story-ruler] *, [data-stage-story-ruler-row], [data-stage-story-ruler-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageDriftBands,
      stageDriftBandsStatus: document.querySelector('[data-stage-drift-bands]')?.getAttribute('data-stage-drift-bands-status') || '',
      stageDriftBandsSchema: document.querySelector('[data-stage-drift-bands]')?.getAttribute('data-stage-drift-bands-schema') || '',
      stageDriftBandCount: Number(document.querySelector('[data-stage-drift-bands]')?.getAttribute('data-stage-drift-band-count') || '0'),
      stageDriftLimitPct: Number(document.querySelector('[data-stage-drift-bands]')?.getAttribute('data-stage-drift-limit-pct') || '0'),
      stageDriftProjectedCount: Number(document.querySelector('[data-stage-drift-bands]')?.getAttribute('data-stage-drift-projected-count') || '0'),
      stageDriftBandToneCount: document.querySelectorAll('[data-stage-drift-band].stage-drift-band--success, [data-stage-drift-band].stage-drift-band--warn, [data-stage-drift-band].stage-drift-band--danger').length,
      stageDriftBandsVisible: Boolean(document.querySelector('[data-stage-drift-bands]')?.classList.contains('is-visible')),
      stageDriftBandsWindowState: window.__STRUCTURE_VIEWER_STAGE_DRIFT_BANDS_STATE__ || null,
      stageDriftBandsText: document.querySelector('[data-stage-drift-bands]')?.textContent || '',
      stageDriftBandsOverflowCount: [...document.querySelectorAll('[data-stage-drift-bands], [data-stage-drift-bands] *, [data-stage-drift-band], [data-stage-drift-band] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageCriticalHotspots,
      stageCriticalHotspotsStatus: document.querySelector('[data-stage-critical-hotspots]')?.getAttribute('data-stage-critical-hotspots-status') || '',
      stageCriticalHotspotsSchema: document.querySelector('[data-stage-critical-hotspots]')?.getAttribute('data-stage-critical-hotspots-schema') || '',
      stageCriticalHotspotCount: Number(document.querySelector('[data-stage-critical-hotspots]')?.getAttribute('data-stage-critical-hotspot-count') || '0'),
      stageCriticalHotspotMemberCount: document.querySelectorAll('[data-stage-critical-hotspot-member]').length,
      stageCriticalHotspotSelectedCount: document.querySelectorAll('[data-stage-critical-hotspot-member].is-selected').length,
      stageCriticalHotspotProjectedCount: document.querySelectorAll('[data-stage-critical-hotspot-projection="projected"]').length,
      stageCriticalHotspotProjectionCount: document.querySelectorAll('[data-stage-critical-hotspot-projection]').length,
      stageCriticalHotspotWindowState: window.__STRUCTURE_VIEWER_STAGE_CRITICAL_HOTSPOTS_STATE__ || null,
      stageCriticalHotspotText: document.querySelector('[data-stage-critical-hotspots]')?.textContent || '',
      stageCriticalHotspotVisible: Boolean(document.querySelector('[data-stage-critical-hotspots]')?.classList.contains('is-visible')),
      stageCriticalHotspotOverlapFocus: [...document.querySelectorAll('[data-stage-critical-hotspot]')].reduce((total, node) => {
        if (!(node instanceof HTMLElement)) return total
        const rect = node.getBoundingClientRect()
        return total + overlapArea({
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        }, focusBadge)
      }, 0),
      stageCriticalHotspotOverflowCount: [...document.querySelectorAll('[data-stage-critical-hotspot], [data-stage-critical-hotspot] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      panelZoneStatus: document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-status') || '',
      panelZoneSchema: document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-schema') || '',
      panelZoneSourceCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-source-count') || '0'),
      panelZoneValidatedSourceCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-validated-source-count') || '0'),
      panelZoneExactSourceCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-exact-source-count') || '0'),
      panelZoneFallbackSourceCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-fallback-source-count') || '0'),
      panelZoneCandidateMemberCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-candidate-member-count') || '0'),
      panelZoneValidatedMemberCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-validated-member-count') || '0'),
      panelZoneValidatedRowCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-validated-row-count') || '0'),
      panelZoneInterferenceRowCount: Number(document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-interference-row-count') || '0'),
      panelZoneBoundary: document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-boundary') || '',
      panelZoneSourcePath: document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-source-path') || '',
      panelZonePrimaryMember: document.querySelector('[data-panel-zone-evidence]')?.getAttribute('data-panel-zone-primary-member') || '',
      panelZoneRowCount: document.querySelectorAll('[data-panel-zone-evidence] [data-panel-zone-row]').length,
      panelZoneMemberRowCount: document.querySelectorAll('[data-panel-zone-evidence] [data-panel-zone-member-row]').length,
      panelZoneHasJoint: Boolean(document.querySelector('[data-panel-zone-row-key="joint-geometry"]')),
      panelZoneHasAnchorage: Boolean(document.querySelector('[data-panel-zone-row-key="rebar-anchorage"]')),
      panelZoneHasClash: Boolean(document.querySelector('[data-panel-zone-row-key="clash"]')),
      panelZoneWindowState: window.__STRUCTURE_VIEWER_PANEL_ZONE_EVIDENCE_STATE__ || null,
      panelZoneStageBadge,
      panelZoneStageStatus: document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-status') || '',
      panelZoneStageSchema: document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-schema') || '',
      panelZoneStageMember: document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-member') || '',
      panelZoneStageSourceCount: Number(document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-source-count') || '0'),
      panelZoneStageValidatedSourceCount: Number(document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-validated-source-count') || '0'),
      panelZoneStageFallbackCount: Number(document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-fallback-count') || '0'),
      panelZoneStageInterferenceCount: Number(document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-interference-count') || '0'),
      panelZoneStageProjection: document.querySelector('[data-panel-zone-stage-badge]')?.getAttribute('data-panel-zone-stage-projection') || '',
      panelZoneStageText: document.querySelector('[data-panel-zone-stage-badge]')?.textContent || '',
      panelZoneStageVisible: Boolean(document.querySelector('[data-panel-zone-stage-badge]')?.classList.contains('is-visible')),
      panelZoneStageWindowState: window.__STRUCTURE_VIEWER_PANEL_ZONE_STAGE_BADGE_STATE__ || null,
      panelZoneStageOverlapFocus: overlapArea(panelZoneStageBadge, focusBadge),
      panelZoneStageOverflowCount: [...document.querySelectorAll('[data-panel-zone-stage-badge], [data-panel-zone-stage-badge] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      panelZoneOverflowCount: [...document.querySelectorAll('[data-panel-zone-evidence], [data-panel-zone-evidence] [data-panel-zone-row], [data-panel-zone-evidence] [data-panel-zone-member-row], [data-panel-zone-evidence] .panel-zone-evidence__head')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      deliveryStatus: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-status') || '',
      deliverySheetStatus: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-sheet-status') || '',
      deliverySheetCount: Number(document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-sheet-count') || '0'),
      deliveryViewerLinkReady: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-viewer-link-ready') || '',
      deliveryReportReady: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-report-ready') || '',
      deliveryDataReady: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-data-ready') || '',
      deliveryEvidenceReady: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-evidence-ready') || '',
      deliveryDrawingReview: document.querySelector('[data-delivery-review-receipt]')?.getAttribute('data-delivery-drawing-review') || '',
      deliveryRowCount: document.querySelectorAll('[data-delivery-review-receipt] [data-delivery-review-row]').length,
      deliveryOverflowCount: [...document.querySelectorAll('[data-delivery-review-receipt], [data-delivery-review-receipt] [data-delivery-review-row]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialCatalogStatus: document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-catalog-status') || '',
      materialCatalogMaterialCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-count') || '0'),
      materialCatalogUsedMaterialCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-used-material-count') || '0'),
      materialCatalogMissingMaterialCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-missing-material-count') || '0'),
      materialCatalogFamilyCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-family-count') || '0'),
      materialCatalogKnownFamilyCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-known-material-family-count') || '0'),
      materialCatalogOntologyFamilyCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-family-ontology-count') || '0'),
      materialCatalogUnclassifiedCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-unclassified-material-count') || '0'),
      materialCatalogSectionCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-section-count') || '0'),
      materialCatalogUsedSectionCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-used-section-count') || '0'),
      materialCatalogThicknessCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-thickness-count') || '0'),
      materialCatalogScheduleCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-section-schedule-count') || '0'),
      materialCatalogSectionScheduleCount: Number(document.querySelector('[data-material-member-catalog]')?.getAttribute('data-section-material-schedule-count') || '0'),
      materialCatalogRowCount: document.querySelectorAll('[data-material-member-catalog] [data-material-catalog-row]').length,
      materialCatalogScheduleRowCount: document.querySelectorAll('[data-material-member-catalog] [data-material-section-row]').length,
      materialCatalogSectionScheduleRowCount: document.querySelectorAll('[data-material-member-catalog] [data-section-schedule-row]').length,
      materialCatalogFamilyChipCount: document.querySelectorAll('[data-material-family-coverage] [data-material-family-chip]').length,
      materialCatalogSectionFamilyCount: document.querySelectorAll('[data-material-member-catalog] [data-material-section-family-summary] span').length,
      materialCatalogThicknessPreviewCount: document.querySelectorAll('[data-material-member-catalog] [data-material-thickness-summary] span').length,
      materialCatalogRebarSummaryCount: document.querySelectorAll('[data-material-member-catalog] [data-material-rebar-summary] span').length,
      materialCatalogSteelVisible: (document.querySelector('[data-material-member-catalog]')?.textContent || '').includes('STEEL')
        || (document.querySelector('[data-material-member-catalog]')?.textContent || '').includes('Q235'),
      materialCatalogConcreteVisible: (document.querySelector('[data-material-member-catalog]')?.textContent || '').includes('CONC')
        || (document.querySelector('[data-material-member-catalog]')?.textContent || '').includes('C40'),
      materialCatalogScheduleHasSteelConcrete: (() => {
        const text = document.querySelector('[data-material-section-schedule]')?.textContent || ''
        return (text.includes('STEEL') || text.includes('Q235')) && (text.includes('CONC') || text.includes('C40'))
      })(),
      materialCatalogSectionScheduleHasSectionAndMaterial: (() => {
        const text = document.querySelector('[data-section-schedule]')?.textContent || ''
        return text.includes('H-') || text.includes('RECT') || text.includes('CONC') || text.includes('STEEL') || text.includes('C40')
      })(),
      materialCatalogOverflowCount: [...document.querySelectorAll('[data-material-member-catalog], [data-material-member-catalog] [data-material-catalog-row], [data-material-member-catalog] .material-catalog-summary span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialCatalogScheduleOverflowCount: [...document.querySelectorAll('[data-material-section-schedule], [data-material-section-schedule] [data-material-section-row]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialCatalogSectionScheduleOverflowCount: [...document.querySelectorAll('[data-section-schedule], [data-section-schedule] [data-section-schedule-row]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialCatalogFamilyOverflowCount: [...document.querySelectorAll('[data-material-family-coverage], [data-material-family-coverage] [data-material-family-chip]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      optimizationCardCount: document.querySelectorAll('#optimization-summary-panel .optimization-summary-card').length,
      optimizationSourceCount: document.querySelectorAll('#optimization-summary-panel .optimization-summary-card__source').length,
      optimizationAfterBarCount: document.querySelectorAll('#optimization-summary-panel .optimization-summary-bar--after').length,
      optimizationSavedCount: document.querySelectorAll('#optimization-summary-panel .optimization-summary-saved').length,
      optimizationDetailsLinkCount: document.querySelectorAll('[data-optimization-summary-details-link]').length,
      optimizationOverflowCount: [...document.querySelectorAll('#optimization-summary-panel .optimization-summary-card')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      chartCount: document.querySelectorAll('#analysis-cockpit-chart-strip .analysis-chart-panel').length,
      driftLineCount: document.querySelectorAll('#story-drift-chart-panel .analysis-chart-line').length,
      driftLimitCount: document.querySelectorAll('#story-drift-chart-panel .analysis-chart-limit').length,
      driftTickCount: document.querySelectorAll('#story-drift-chart-panel .analysis-chart-ticks text').length,
      driftPeakLabelCount: document.querySelectorAll('#story-drift-chart-panel .analysis-chart-peak-label').length,
      driftLegendHasComparison: (document.querySelector('#story-drift-chart-panel .analysis-chart-legend--drift')?.textContent || '').includes('Original')
        && (document.querySelector('#story-drift-chart-panel .analysis-chart-legend--drift')?.textContent || '').includes('Optimized')
        && (document.querySelector('#story-drift-chart-panel .analysis-chart-legend--drift')?.textContent || '').includes('Limit'),
      loadStepTickCount: document.querySelectorAll('#load-step-chart-panel .analysis-chart-ticks text').length,
      loadStepMarkerLabelCount: document.querySelectorAll('#load-step-chart-panel .analysis-chart-step-label').length,
      loadStepMarkerLabelText: document.querySelector('#load-step-chart-panel .analysis-chart-step-label')?.textContent || '',
      materialGroupCount: document.querySelectorAll('#material-quantity-chart-panel .analysis-material-group').length,
      materialOptimizedBarCount: document.querySelectorAll('#material-quantity-chart-panel .analysis-material-bar--optimized').length,
      materialDeltaCount: [...document.querySelectorAll('#material-quantity-chart-panel .analysis-material-label span')]
        .filter((node) => (node.textContent || '').includes('%')).length,
      heatmapEvidenceCount: document.querySelectorAll('#utilization-heatmap-panel [data-utilization-heatmap-evidence]').length,
      heatmapReceiptRowCount: document.querySelectorAll('#utilization-heatmap-panel [data-heatmap-receipt] span').length,
      heatmapHotspotCount: document.querySelectorAll('#utilization-heatmap-panel .analysis-heatmap-hotspot').length,
      heatmapGradientCount: document.querySelectorAll('#utilization-heatmap-panel .analysis-heatmap-gradient').length,
      heatmapLevelChipCount: document.querySelectorAll('#utilization-heatmap-panel [data-heatmap-level-chip]').length,
      heatmapMaxValue: Number(document.querySelector('#utilization-heatmap-panel [data-utilization-heatmap-evidence]')?.getAttribute('data-heatmap-max') || '0'),
      heatmapHotCellCount: Number(document.querySelector('#utilization-heatmap-panel [data-utilization-heatmap-evidence]')?.getAttribute('data-heatmap-hot-cells') || '0'),
      heatmapOverflowCount: [...document.querySelectorAll('#utilization-heatmap-panel [data-heatmap-receipt] span, #utilization-heatmap-panel .analysis-chart-title__chip')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      loadCaseEvidenceCount: document.querySelectorAll('#load-case-list .load-case-evidence-row').length,
      loadCaseStatusCount: document.querySelectorAll('#load-case-list [data-load-case-status]').length,
      loadCaseKindCount: document.querySelectorAll('#load-case-list [data-load-case-kind]').length,
      loadCaseProgressCount: document.querySelectorAll('#load-case-list .load-case-evidence-row__bar i').length,
      loadCaseActiveCount: document.querySelectorAll('#load-case-list .load-case-evidence-row.selected').length,
      loadCaseOverflowCount: [...document.querySelectorAll('#load-case-list .load-case-evidence-row')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      criticalRows: document.querySelectorAll('#critical-members-panel [data-critical-member-id]').length,
      criticalRatioTrackCount: document.querySelectorAll('#critical-members-panel .critical-member-ratio__track').length,
      criticalRatioLimitCount: document.querySelectorAll('#critical-members-panel .critical-member-ratio__track em').length,
      criticalDriftBarCount: document.querySelectorAll('#critical-members-panel .critical-member-drift i em').length,
      criticalStatusChipCount: document.querySelectorAll('#critical-members-panel .critical-member-status').length,
      criticalActionChipCount: document.querySelectorAll('#critical-members-panel .critical-member-action').length,
      criticalHighRows: document.querySelectorAll('#critical-members-panel [data-critical-status="high"]').length,
      stageReceipt,
      stageReceiptRowCount: document.querySelectorAll('#stage-result-receipt .stage-result-receipt__row').length,
      stageReceiptHasContour: (document.querySelector('#stage-result-receipt')?.textContent || '').includes('Contour result'),
      stageReceiptHasRange: (document.querySelector('#stage-result-receipt')?.textContent || '').includes('Range'),
      stageReceiptSource: document.querySelector('#stage-result-receipt')?.getAttribute('data-scalar-source') || '',
      stageReceiptOverflow: (() => {
        const node = document.querySelector('#stage-result-receipt')
        if (!(node instanceof HTMLElement)) return 0
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2 ? 1 : 0
      })(),
      calloutCount: document.querySelectorAll('[data-stage-result-callout-key]').length,
      chartFooterOverlap: overlapArea(chartStrip, footer),
      calloutBadgeOverlap: overlapArea(callouts, focusBadge),
    }
  })

  expect(layout.appOverflowX).toBeLessThanOrEqual(2)
  expect(layout.topbar?.height || 999).toBeLessThanOrEqual(102)
  expect(layout.topProjectSelect?.width || 0).toBeGreaterThanOrEqual(140)
  expect(layout.topProjectOptionCount).toBeGreaterThanOrEqual(3)
  expect(layout.topProjectValue).toBe('midas33_release::midas33_optimized')
  expect(layout.topProjectProjectId).toBe('midas33_release')
  expect(layout.topProjectDrawingId).toBe('midas33_optimized')
  expect(layout.topProjectVariant).toBe('optimized')
  expect(layout.topProjectReceipt).toContain('optimized')
  expect(layout.topProjectOverflow).toBe(0)
  expect(layout.topRunControl?.width || 0).toBeGreaterThanOrEqual(360)
  expect(layout.topRunActionCount).toBeGreaterThanOrEqual(7)
  expect(layout.topRunVisibleActionCount).toBeGreaterThanOrEqual(5)
  expect(layout.topRunReceiptRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.topRunStatus).toBe('ready')
  expect(layout.topRunPrimaryStatus).toBe('ready')
  expect(layout.topRunLoadCase).not.toBe('')
  expect(layout.topRunStep).toContain('/')
  expect(layout.topRunSolver).not.toBe('')
  expect(layout.topRunComparePressed).toBe('false')
  expect(layout.topRunOverflowCount).toBe(0)
  expect(layout.modelOverviewStatus).toBe('ready')
  expect(layout.modelOverviewHeightM).toBeGreaterThan(0)
  expect(layout.modelOverviewUnits).not.toBe('')
  expect(layout.modelOverviewAnalysisType).not.toBe('')
  expect(layout.modelOverviewLastRun).not.toBe('--')
  expect(layout.sourceAdapterStatus).toBe('ready')
  expect(layout.sourceAdapterSchema).toBe('structure-viewer-source-adapter-matrix.v1')
  expect(layout.sourceAdapterCount).toBe(3)
  expect(layout.sourceAdapterCurrentCount).toBe(1)
  expect(layout.sourceAdapterActiveKey).toBe('midas')
  expect(layout.sourceAdapterHasMidas).toBe(true)
  expect(layout.modelInfoRowCount).toBeGreaterThanOrEqual(10)
  expect(layout.modelInfoHasHeight).toBe(true)
  expect(layout.modelInfoHasUnits).toBe(true)
  expect(layout.modelInfoHasAnalysis).toBe(true)
  expect(layout.modelOverviewOverflowCount).toBe(0)
  expect(layout.viewport?.width || 0).toBeGreaterThanOrEqual(540)
  expect(layout.viewport?.height || 0).toBeGreaterThanOrEqual(398)
  expect(layout.stageOverlayOcclusionBudget).toBe('dense-model-protagonist')
  expect(layout.stageOverlayBudgetNodeCount).toBeGreaterThanOrEqual(8)
  expect(layout.stageOverlayViewportOcclusionRatio).toBeLessThanOrEqual(0.40)
  expect(layout.stageOverlayCentralOcclusionRatio).toBeLessThanOrEqual(0.18)
  expect(layout.rightPanel?.width || 0).toBeGreaterThanOrEqual(360)
  expect(layout.toolRail?.width || 0).toBeGreaterThanOrEqual(30)
  expect(layout.toolRailGroupCount).toBe(3)
  expect(layout.toolRailButtonCount).toBeGreaterThanOrEqual(10)
  expect(layout.toolRailTooltipCount).toBeGreaterThanOrEqual(10)
  expect(layout.toolRailRenderModeCount).toBe(3)
  expect(layout.toolRailViewPresetCount).toBeGreaterThanOrEqual(3)
  expect(layout.toolRailPressedCount).toBeGreaterThanOrEqual(2)
  expect(layout.toolRailContourActive).toBe(true)
  expect(layout.toolRailReviewActive).toBe(true)
  expect(layout.toolRailOverflowCount).toBe(0)
  expect(layout.stageReviewControls?.width || 0).toBeGreaterThan(140)
  expect(layout.stageReviewModeValue).toBe('contour')
  expect(layout.stageReviewPresetValue).toBe('review')
  expect(layout.stageReviewSelectCount).toBe(2)
  expect(layout.stageReviewModelRowCount).toBe(2)
  expect(layout.stageReviewComparePressed).toBe('false')
  expect(layout.stageDeformationStatus).toBe('ready')
  expect(layout.stageDeformationSchema).toBe('structure-viewer-deformation-control.v1')
  expect(layout.stageDeformationDisplayScale).toBeCloseTo(1, 1)
  expect(layout.stageDeformationInternalScale).toBe(100)
  expect(layout.stageDeformationSliderValue).toBeCloseTo(1, 1)
  expect(layout.stageDeformationLabel).toContain('Deformation Scale')
  expect(layout.stageDeformationLabel).toContain('1.0x')
  expect(layout.stageDeformationOverflowCount).toBe(0)
  expect(layout.stageReviewReceiptRowCount).toBe(3)
  expect(layout.stageReviewReceiptHasScale).toBe(true)
  expect(layout.stageReviewOverflow).toBe(0)
  expect(layout.contourScaleTickCount).toBe(5)
  expect(layout.contourScalePriority).toBe('first-stage-viewport')
  expect(layout.loadCasesPriority).toBe('after-results')
  expect(layout.contourSection?.top || 9999).toBeLessThan(layout.loadCasesSection?.top || 99999)
  expect(layout.contourScaleVisibleArea).toBeGreaterThan(1200)
  expect(layout.contourScalePanelVisibleArea).toBeGreaterThan(1200)
  expect(layout.contourScale?.bottom || 9999).toBeLessThanOrEqual((layout.stageFrame?.bottom || 0) + 1)
  expect(layout.contourScaleUnit).toBe('mm')
  expect(layout.contourScaleSource).not.toBe('')
  expect(layout.contourScaleMax).toBeGreaterThan(layout.contourScaleMin)
  expect(layout.contourScaleGradientPresent).toBe(true)
  expect(layout.contourScaleOverflow).toBe(0)
  expect(layout.kpiCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiEvidenceCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiReferenceCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiTrendCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiSparkAreaCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiSparkDotCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiFullLabelCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiFullLabelText).toContain('Max Displacement')
  expect(layout.kpiFullLabelText).toContain('Estimated Material Cost')
  expect(layout.kpiLabelEllipsisCount).toBe(0)
  expect(layout.kpiLabelOverflowCount).toBe(0)
  expect(layout.kpiFullValueCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiValueNumberCount).toBeGreaterThanOrEqual(8)
  expect(layout.kpiValueUnitCount).toBeGreaterThanOrEqual(6)
  expect(layout.kpiValueEllipsisCount).toBe(0)
  expect(layout.kpiValueOverflowCount).toBe(0)
  expect(layout.kpiOverflowCount).toBe(0)
  expect(layout.resultEvidenceStatus).not.toBe('pending')
  expect(layout.resultEvidenceSourceMetricCount).toBeGreaterThan(0)
  expect(layout.resultEvidenceEstimateMetricCount).toBeGreaterThan(0)
  expect(layout.resultEvidenceTotalMetricCount).toBe(8)
  expect(layout.resultEvidenceCoveragePct).toBeGreaterThan(0)
  expect(layout.resultEvidenceRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.resultEvidenceOverflowCount).toBe(0)
  expect(layout.optimizationDeltaStrip?.top || 9999).toBeLessThan(layout.criticalTriage?.top || 99999)
  expect(layout.optimizationDeltaStripStatus).toBe('ready')
  expect(layout.optimizationDeltaStripSchema).toBe('structure-viewer-optimization-delta-strip.v1')
  expect(layout.optimizationDeltaStripRowCount).toBe(4)
  expect(layout.optimizationDeltaStripRows).toBe(4)
  expect(layout.optimizationDeltaStripReductionCount).toBeGreaterThanOrEqual(3)
  expect(layout.optimizationDeltaStripMaxReductionPct).toBeGreaterThan(0)
  expect(layout.optimizationDeltaStripAfterBarCount).toBe(4)
  expect(layout.optimizationDeltaStripDeltaCount).toBe(4)
  expect(layout.optimizationDeltaStripText).toContain('Optimization Summary')
  expect(layout.optimizationDeltaStripText).toContain('After')
  expect(layout.optimizationDeltaStripWindowState?.schemaVersion).toBe('structure-viewer-optimization-delta-strip.v1')
  expect(layout.optimizationDeltaStripWindowState?.status).toBe('ready')
  expect(layout.optimizationDeltaStripWindowState?.rowCount).toBe(4)
  expect(layout.optimizationDeltaStripOverflowCount).toBe(0)
  expect(layout.resultStepScheduleStatus).toBe('ready')
  expect(layout.resultStepScheduleRowCount).toBeGreaterThanOrEqual(5)
  expect(layout.resultStepScheduleActiveCount).toBe(1)
  expect(layout.resultStepScheduleActiveStep).toBeGreaterThan(0)
  expect(layout.resultStepScheduleTotal).toBeGreaterThanOrEqual(20)
  expect(layout.resultStepScheduleCurrentStep).toBe(String(layout.resultStepScheduleActiveStep))
  expect(layout.resultStepScheduleLoadCase).not.toBe('')
  expect(layout.resultStepScheduleConvergence).not.toBe('')
  expect(layout.resultStepScheduleSolver).not.toBe('')
  expect(layout.resultStepScheduleOverflowCount).toBe(0)
  expect(layout.resultEnvelopeStatus).toBe('ready')
  expect(layout.resultEnvelopeRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.resultEnvelopeLoadCase).not.toBe('')
  expect(layout.resultEnvelopeActiveStep).toBeGreaterThan(0)
  expect(layout.resultEnvelopeTotalSteps).toBeGreaterThanOrEqual(20)
  expect(layout.resultEnvelopeGoverningMember).not.toBe('')
  expect(layout.resultEnvelopeSourceMetricCount).toBeGreaterThan(0)
  expect(layout.resultEnvelopeTotalMetricCount).toBe(8)
  expect(layout.resultEnvelopeHasDisplacement).toBe(true)
  expect(layout.resultEnvelopeHasDrift).toBe(true)
  expect(layout.resultEnvelopeHasBaseShear).toBe(true)
  expect(layout.resultEnvelopeHasUtilization).toBe(true)
  expect(layout.resultEnvelopeMemberRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.resultEnvelopeOverflowCount).toBe(0)
  expect(layout.criticalTriage?.top || 9999).toBeLessThanOrEqual((layout.rightPanel?.bottom || 0) + 1)
  expect(layout.criticalTriageStatus).toBe('ready')
  expect(layout.criticalTriageSchema).toBe('structure-viewer-critical-triage.v1')
  expect(layout.criticalTriageRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalTriageRows).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageMemberRows).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageSourceCount).toBeGreaterThanOrEqual(layout.criticalTriageRowCount)
  expect(layout.criticalTriageHighCount).toBeGreaterThanOrEqual(1)
  expect(layout.criticalTriageMaxRatio).toBeGreaterThan(0)
  expect(layout.criticalTriageStatusCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageActionCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageText).toContain('Critical Triage')
  expect(layout.criticalTriageText).toContain('D/C')
  expect(layout.criticalTriageWindowState?.schemaVersion).toBe('structure-viewer-critical-triage.v1')
  expect(layout.criticalTriageWindowState?.status).toBe('ready')
  expect(layout.criticalTriageWindowState?.rowCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageOverflowCount).toBe(0)
  expect(layout.stageStoryRulerStatus).toBe('ready')
  expect(layout.stageStoryRulerSchema).toBe('structure-viewer-stage-story-ruler.v1')
  expect(layout.stageStoryRulerRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.stageStoryRulerStoryCount).toBeGreaterThanOrEqual(layout.stageStoryRulerRowCount)
  expect(layout.stageStoryRulerHeightM).toBeGreaterThan(0)
  expect(layout.stageStoryRulerProjectedCount).toBeGreaterThan(0)
  expect(layout.stageStoryRulerVisible).toBe(true)
  expect(layout.stageStoryRulerWindowState?.schemaVersion).toBe('structure-viewer-stage-story-ruler.v1')
  expect(layout.stageStoryRulerWindowState?.status).toBe('ready')
  expect(layout.stageStoryRulerWindowState?.rowCount).toBeGreaterThanOrEqual(6)
  expect(layout.stageStoryRulerText).toContain('Story Levels')
  expect(layout.stageStoryRulerText).toContain('drift')
  expect(layout.stageStoryRulerOverflowCount).toBe(0)
  expect(layout.stageDriftBandsStatus).toBe('ready')
  expect(layout.stageDriftBandsSchema).toBe('structure-viewer-stage-drift-bands.v1')
  expect(layout.stageDriftBandCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageDriftLimitPct).toBeGreaterThan(0)
  expect(layout.stageDriftProjectedCount).toBeGreaterThan(0)
  expect(layout.stageDriftBandToneCount).toBeGreaterThanOrEqual(layout.stageDriftBandCount)
  expect(layout.stageDriftBandsVisible).toBe(true)
  expect(layout.stageDriftBandsWindowState?.schemaVersion).toBe('structure-viewer-stage-drift-bands.v1')
  expect(layout.stageDriftBandsWindowState?.status).toBe('ready')
  expect(layout.stageDriftBandsWindowState?.bandCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageDriftBandsText).toContain('Drift Bands')
  expect(layout.stageDriftBandsText).toContain('Limit')
  expect(layout.stageDriftBandsOverflowCount).toBe(0)
  expect(layout.stageCriticalHotspotsStatus).toBe('ready')
  expect(layout.stageCriticalHotspotsSchema).toBe('structure-viewer-stage-critical-hotspots.v1')
  expect(layout.stageCriticalHotspotCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageCriticalHotspotMemberCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageCriticalHotspotSelectedCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageCriticalHotspotProjectionCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageCriticalHotspotWindowState?.schemaVersion).toBe('structure-viewer-stage-critical-hotspots.v1')
  expect(layout.stageCriticalHotspotWindowState?.status).toBe('ready')
  expect(layout.stageCriticalHotspotWindowState?.hotspotCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageCriticalHotspotText).toContain('Critical 1')
  expect(layout.stageCriticalHotspotText).toContain('D/C')
  expect(layout.stageCriticalHotspotVisible).toBe(true)
  expect(layout.stageCriticalHotspotOverlapFocus).toBe(0)
  expect(layout.stageCriticalHotspotOverflowCount).toBe(0)
  expect(layout.panelZoneStatus).toBe('ready')
  expect(layout.panelZoneSchema).toBe('structure-viewer-panel-zone-evidence.v1')
  expect(layout.panelZoneSourceCount).toBe(3)
  expect(layout.panelZoneValidatedSourceCount).toBe(3)
  expect(layout.panelZoneExactSourceCount).toBe(3)
  expect(layout.panelZoneFallbackSourceCount).toBe(0)
  expect(layout.panelZoneCandidateMemberCount).toBeGreaterThanOrEqual(45)
  expect(layout.panelZoneValidatedMemberCount).toBeGreaterThanOrEqual(1)
  expect(layout.panelZoneValidatedRowCount).toBeGreaterThanOrEqual(3)
  expect(layout.panelZoneInterferenceRowCount).toBeGreaterThanOrEqual(45)
  expect(layout.panelZoneBoundary).toContain('solver')
  expect(layout.panelZoneSourcePath).toContain('panel_zone_clash_artifact')
  expect(layout.panelZonePrimaryMember).not.toBe('')
  expect(layout.panelZoneRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.panelZoneMemberRowCount).toBeGreaterThanOrEqual(3)
  expect(layout.panelZoneHasJoint).toBe(true)
  expect(layout.panelZoneHasAnchorage).toBe(true)
  expect(layout.panelZoneHasClash).toBe(true)
  expect(layout.panelZoneWindowState?.status).toBe('ready')
  expect(layout.panelZoneStageStatus).toBe('ready')
  expect(layout.panelZoneStageSchema).toBe('structure-viewer-panel-zone-stage-badge.v1')
  expect(layout.panelZoneStageMember).not.toBe('')
  expect(layout.panelZoneStageSourceCount).toBe(3)
  expect(layout.panelZoneStageValidatedSourceCount).toBe(3)
  expect(layout.panelZoneStageFallbackCount).toBe(0)
  expect(layout.panelZoneStageInterferenceCount).toBeGreaterThanOrEqual(45)
  expect(['projected', 'edge-pinned', 'docked']).toContain(layout.panelZoneStageProjection)
  expect(layout.panelZoneStageText).toContain('Panel Zone')
  expect(layout.panelZoneStageText).toContain('Solver verified')
  expect(layout.panelZoneStageVisible).toBe(true)
  expect(layout.panelZoneStageWindowState?.schemaVersion).toBe('structure-viewer-panel-zone-stage-badge.v1')
  expect(layout.panelZoneStageWindowState?.status).toBe('ready')
  expect(layout.panelZoneStageWindowState?.memberId).toBe(layout.panelZoneStageMember)
  expect(layout.panelZoneStageOverlapFocus).toBe(0)
  expect(layout.panelZoneStageOverflowCount).toBe(0)
  expect(layout.panelZoneOverflowCount).toBe(0)
  expect(layout.deliveryStatus).not.toBe('pending')
  expect(layout.deliveryStatus).not.toBe('blocked')
  expect(layout.deliverySheetStatus).toBe('linked')
  expect(layout.deliverySheetCount).toBeGreaterThanOrEqual(4)
  expect(layout.deliveryViewerLinkReady).toBe('true')
  expect(layout.deliveryReportReady).toBe('true')
  expect(layout.deliveryDataReady).toBe('true')
  expect(layout.deliveryEvidenceReady).toBe('true')
  expect(layout.deliveryDrawingReview).not.toBe('blocked')
  expect(layout.deliveryRowCount).toBeGreaterThanOrEqual(5)
  expect(layout.deliveryOverflowCount).toBe(0)
  expect(layout.materialCatalogStatus).toBe('ready')
  expect(layout.materialCatalogMaterialCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogUsedMaterialCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogMissingMaterialCount).toBe(0)
  expect(layout.materialCatalogFamilyCount).toBeGreaterThanOrEqual(2)
  expect(layout.materialCatalogKnownFamilyCount).toBeGreaterThanOrEqual(2)
  expect(layout.materialCatalogOntologyFamilyCount).toBeGreaterThanOrEqual(45)
  expect(layout.materialCatalogFamilyChipCount).toBeGreaterThanOrEqual(2)
  expect(layout.materialCatalogUnclassifiedCount).toBeLessThanOrEqual(layout.materialCatalogMaterialCount)
  expect(layout.materialCatalogSectionCount).toBeGreaterThanOrEqual(180)
  expect(layout.materialCatalogUsedSectionCount).toBeGreaterThanOrEqual(80)
  expect(layout.materialCatalogThicknessCount).toBeGreaterThanOrEqual(30)
  expect(layout.materialCatalogScheduleCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogSectionScheduleCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogScheduleRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogSectionScheduleRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCatalogSectionFamilyCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialCatalogThicknessPreviewCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialCatalogRebarSummaryCount).toBe(1)
  expect(layout.materialCatalogSteelVisible).toBe(true)
  expect(layout.materialCatalogConcreteVisible).toBe(true)
  expect(layout.materialCatalogScheduleHasSteelConcrete).toBe(true)
  expect(layout.materialCatalogSectionScheduleHasSectionAndMaterial).toBe(true)
  expect(layout.materialCatalogOverflowCount).toBe(0)
  expect(layout.materialCatalogScheduleOverflowCount).toBe(0)
  expect(layout.materialCatalogSectionScheduleOverflowCount).toBe(0)
  expect(layout.materialCatalogFamilyOverflowCount).toBe(0)
  expect(layout.optimizationCardCount).toBe(4)
  expect(layout.optimizationSourceCount).toBe(4)
  expect(layout.optimizationAfterBarCount).toBe(4)
  expect(layout.optimizationSavedCount).toBe(4)
  expect(layout.optimizationDetailsLinkCount).toBe(1)
  expect(layout.optimizationOverflowCount).toBe(0)
  expect(layout.chartCount).toBe(4)
  expect(layout.driftLineCount).toBeGreaterThanOrEqual(2)
  expect(layout.driftLimitCount).toBe(1)
  expect(layout.driftTickCount).toBeGreaterThanOrEqual(4)
  expect(layout.driftPeakLabelCount).toBe(1)
  expect(layout.driftLegendHasComparison).toBe(true)
  expect(layout.loadStepTickCount).toBeGreaterThanOrEqual(4)
  expect(layout.loadStepMarkerLabelCount).toBe(1)
  expect(layout.loadStepMarkerLabelText).toContain(`Step ${layout.resultStepScheduleActiveStep}`)
  expect(layout.materialGroupCount).toBe(3)
  expect(layout.materialOptimizedBarCount).toBe(3)
  expect(layout.materialDeltaCount).toBe(3)
  expect(layout.heatmapEvidenceCount).toBe(1)
  expect(layout.heatmapReceiptRowCount).toBeGreaterThanOrEqual(5)
  expect(layout.heatmapHotspotCount).toBeGreaterThan(0)
  expect(layout.heatmapGradientCount).toBe(1)
  expect(layout.heatmapLevelChipCount).toBe(1)
  expect(layout.heatmapMaxValue).toBeGreaterThan(0)
  expect(layout.heatmapHotCellCount).toBeGreaterThan(0)
  expect(layout.heatmapOverflowCount).toBe(0)
  expect(layout.loadCaseEvidenceCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCaseStatusCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCaseKindCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCaseProgressCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCaseActiveCount).toBeGreaterThanOrEqual(1)
  expect(layout.loadCaseOverflowCount).toBe(0)
  expect(layout.criticalRows).toBeGreaterThanOrEqual(4)
  expect(layout.criticalRatioTrackCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalRatioLimitCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalDriftBarCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalStatusChipCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalActionChipCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalHighRows).toBeGreaterThanOrEqual(1)
  expect(layout.stageReceipt?.width || 0).toBeGreaterThan(120)
  expect(layout.stageReceiptRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.stageReceiptHasContour).toBe(true)
  expect(layout.stageReceiptHasRange).toBe(true)
  expect(layout.stageReceiptSource).not.toBe('')
  expect(layout.stageReceiptOverflow).toBe(0)
  expect(layout.stageOverlayReceipt?.width || 0).toBeGreaterThan(120)
  expect(layout.stageOverlayStatus).toBe('ready')
  expect(layout.stageOverlayArrowCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageOverlaySupportCount).toBeGreaterThanOrEqual(8)
  expect(layout.stageOverlaySource).toContain('base nodes')
  expect(layout.stageOverlayLoadCase).not.toBe('')
  expect(layout.stageOverlayVisibleEvidenceCount).toBeGreaterThanOrEqual(2)
  expect(layout.stageOverlayVisualArrowCount).toBe(layout.stageOverlayArrowCount)
  expect(layout.stageOverlayVisualSupportCount).toBe(layout.stageOverlaySupportCount)
  expect(layout.stageOverlayVisualItemCount).toBeGreaterThanOrEqual(2)
  expect(layout.stageOverlayLoadSwatchCount).toBe(1)
  expect(layout.stageOverlaySupportSwatchCount).toBe(1)
  expect(layout.stageOverlayWindowState?.loadArrowCount || 0).toBe(layout.stageOverlayArrowCount)
  expect(layout.stageOverlayWindowState?.supportMarkerCount || 0).toBe(layout.stageOverlaySupportCount)
  expect(layout.stageOverlayWindowState?.visibleEvidenceCount || 0).toBe(layout.stageOverlayVisibleEvidenceCount)
  expect(layout.stageOverlayVisualOverflow).toBe(0)
  expect(layout.stageOverlayOverflow).toBe(0)
  expect(layout.stageLoadSupportGlyphs?.width || 0).toBeGreaterThanOrEqual((layout.viewport?.width || 0) - 4)
  expect(layout.stageLoadSupportGlyphStatus).toBe('ready')
  expect(layout.stageLoadSupportGlyphSchema).toBe('structure-viewer-stage-load-support-glyphs.v1')
  expect(layout.stageLoadGlyphCount).toBe(layout.stageOverlayArrowCount)
  expect(layout.stageLoadGlyphCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageSupportGlyphSourceCount).toBe(layout.stageOverlaySupportCount)
  expect(layout.stageSupportGlyphCount).toBeGreaterThanOrEqual(8)
  expect(layout.stageSupportGlyphCount).toBeLessThanOrEqual(layout.stageOverlaySupportCount)
  expect(layout.stageLoadGlyphVisibleCount).toBe(layout.stageLoadGlyphCount)
  expect(layout.stageSupportGlyphVisibleCount).toBe(layout.stageSupportGlyphCount)
  expect(layout.stageLoadGlyphProjectionCount).toBe(layout.stageLoadGlyphCount)
  expect(layout.stageSupportGlyphProjectionCount).toBe(layout.stageSupportGlyphCount)
  expect(layout.stageLoadSupportProjectedCount).toBeGreaterThan(0)
  expect(layout.stageLoadProjectedCount + layout.stageSupportProjectedCount).toBe(layout.stageLoadSupportProjectedCount)
  expect(layout.stageLoadSupportGlyphVisible).toBe(true)
  expect(layout.stageLoadSupportGlyphWindowState?.schemaVersion).toBe('structure-viewer-stage-load-support-glyphs.v1')
  expect(layout.stageLoadSupportGlyphWindowState?.status).toBe('ready')
  expect(layout.stageLoadSupportGlyphWindowState?.loadGlyphCount).toBe(layout.stageLoadGlyphCount)
  expect(layout.stageLoadSupportGlyphWindowState?.supportGlyphCount).toBe(layout.stageSupportGlyphCount)
  expect(layout.stageLoadSupportGlyphWindowState?.supportSourceCount).toBe(layout.stageOverlaySupportCount)
  expect(layout.stageLoadSupportGlyphWindowState?.projectedCount).toBe(layout.stageLoadSupportProjectedCount)
  expect(layout.stageLoadSupportGlyphOverflowCount).toBe(0)
  expect(layout.calloutCount).toBeGreaterThanOrEqual(4)
  expect(layout.chartFooterOverlap).toBe(0)
  expect(layout.calloutBadgeOverlap).toBe(0)
  await expectNoBrowserErrors(errors)
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
