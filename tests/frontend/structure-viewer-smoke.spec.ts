import { expect, test, type Page } from '@playwright/test'
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
    if (message.type() !== 'error') return
    const url = message.location()?.url ?? ''
    // Release-visualization data under implementation/phase1/release/ is hosted
    // at deploy time and is intentionally gitignored, so it 404s on clean
    // checkouts (CI). Ignore only those benign resource 404s; every other
    // console error and all pageerrors still fail the smoke.
    const isDeployTimeData404 =
      /Failed to load resource/.test(message.text()) &&
      /status of 404/.test(message.text()) &&
      url.includes('/implementation/phase1/release/')
    if (isDeployTimeData404) return
    errors.push(message.text())
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

type RenderMode = 'wireframe' | 'solid' | 'contour'
type ViewPreset = 'review' | 'frame' | 'plan' | 'fit'

async function expectRenderMode(page: Page, mode: RenderMode) {
  const toolButton = page.locator(`[data-viewport-tool-render-mode="${mode}"]`).first()
  await expect(toolButton).toHaveAttribute('aria-pressed', 'true', { timeout: 30000 })
  await expect(page.locator(`#btn-${mode}`)).toHaveClass(/active/, { timeout: 30000 })
}

async function clickRenderMode(page: Page, mode: RenderMode) {
  const toolButton = page.locator(`[data-viewport-tool-render-mode="${mode}"]`).first()
  if (await toolButton.isVisible()) {
    await toolButton.click()
  } else {
    await page.locator(`#btn-${mode}`).click()
  }
  await expectRenderMode(page, mode)
}

async function expectViewPreset(page: Page, preset: ViewPreset) {
  if (preset !== 'fit') {
    await expect(page.locator(`[data-viewport-view-preset="${preset}"]`).first()).toHaveAttribute('aria-pressed', 'true', {
      timeout: 30000,
    })
  }
  await expect(page.locator(`#btn-view-${preset}`)).toHaveClass(/active/, { timeout: 30000 })
}

async function clickViewPreset(page: Page, preset: ViewPreset) {
  const toolButton =
    preset === 'fit'
      ? page.locator('[data-viewport-tool="fit-all"]').first()
      : page.locator(`[data-viewport-view-preset="${preset}"]`).first()
  if (await toolButton.isVisible()) {
    await toolButton.click()
  } else {
    await page.locator(`#btn-view-${preset}`).click()
  }
  await expectViewPreset(page, preset)
}

async function clickViewportTool(page: Page, tool: string) {
  const toolButton = page.locator(`[data-viewport-tool="${tool}"]`).first()
  await expect(toolButton).toBeVisible({ timeout: 30000 })
  await toolButton.click()
}

async function openWorkspaceChrome(page: Page) {
  if ((await page.locator('body').getAttribute('data-si-shell')) !== 'workspace') {
    await page.locator('#toggle-workspace-chrome').click()
  }
  await expect(page.locator('body')).toHaveAttribute('data-si-shell', 'workspace', { timeout: 30000 })
  await expect(page.locator('#project-workspace-section')).toBeVisible({ timeout: 30000 })
}

async function openProductShell(page: Page) {
  await page.locator('#member-search-input').fill('')
  if ((await page.locator('body').getAttribute('data-si-shell')) !== 'product') {
    await page.locator('#toggle-workspace-chrome').click()
  }
  await expect(page.locator('body')).toHaveAttribute('data-si-shell', 'product', { timeout: 30000 })
  await page.evaluate(() => {
    ;['left-panel', 'right-panel'].forEach((panelId) => {
      const panel = document.getElementById(panelId)
      if (panel instanceof HTMLElement && !panel.classList.contains('is-collapsed')) {
        window.togglePanelRailCollapse?.(panelId)
      }
    })
  })
  await expect(page.locator('#app')).toHaveAttribute('data-left-rail-collapsed', 'true', { timeout: 30000 })
  await expect(page.locator('#app')).toHaveAttribute('data-right-rail-collapsed', 'true', { timeout: 30000 })
}

async function focusFirstAvailableMember(page: Page, fallbackQuery = '911') {
  const callout = page.locator('[data-stage-callout-focus-member]').first()
  if ((await callout.count()) > 0 && (await callout.isVisible())) {
    await callout.click()
  } else {
    await page.locator('#member-search-input').fill(fallbackQuery)
    const firstSearchResult = page.locator('[data-search-focus]').first()
    await expect(firstSearchResult).toBeVisible({ timeout: 10000 })
    await firstSearchResult.click()
  }
  await page.waitForFunction(() => {
    const badge = document.querySelector('[data-viewport-selection-focus-badge]')
    return Boolean(badge?.classList.contains('is-visible'))
  }, null, { timeout: 10000 })
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
  await expect(page.locator('[data-viewport-view-preset="review"]').first()).toBeVisible({ timeout: 30000 })
  await openWorkspaceChrome(page)
  await expect(page.locator('#project-workspace-select')).toContainText('Release Visualization Entries (8)', { timeout: 30000 })
  await expect(page.locator('[data-shell-project-select]')).toHaveValue('midas33_release::midas33_optimized', { timeout: 30000 })
  await expect(page.locator('[data-shell-project-receipt]')).toContainText('optimized', { timeout: 30000 })
  await expect(page.locator('#project-drawing-list')).toContainText('MIDAS33', { timeout: 30000 })
  await expect(page.locator('#stage-variant-chip')).toContainText('Variant optimized', { timeout: 30000 })
  await expect(page.locator('#stage-quality-chip')).toContainText('Review ready', { timeout: 30000 })
  await expectViewPreset(page, 'review')
  await expectRenderMode(page, 'contour')
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
  await clickRenderMode(page, 'solid')
  await clickViewportTool(page, 'fit-all')
  await clickViewportTool(page, 'reset-view')
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

  await clickViewPreset(page, 'frame')
  await expectCanvasReady(page)

  await clickViewPreset(page, 'plan')
  await expectRenderMode(page, 'wireframe')
  await waitForCanvasNonBlank(page)

  await clickViewPreset(page, 'fit')
  await waitForCanvasNonBlank(page)

  await clickViewPreset(page, 'review')
  await expectRenderMode(page, 'contour')
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
  await focusFirstAvailableMember(page)
  const firstScheduleStep = page.locator('[data-result-step-schedule] [data-result-step-row]').first()
  await expect(firstScheduleStep).toBeVisible({ timeout: 10000 })
  const clickedStep = await firstScheduleStep.getAttribute('data-result-step')
  await firstScheduleStep.click()
  if (clickedStep) {
    await expect(page.locator('[data-result-step-schedule] [data-result-step-active="true"]')).toHaveAttribute('data-result-step', clickedStep)
  }
  if (await page.locator('[data-drawing-handoff-sheet]').count() > 1) {
    await page.locator('[data-drawing-handoff-sheet]').nth(1).focus()
  }
  const loadCombinationSteps = page.locator('[data-load-combination-force-step-combination]')
  await expect(loadCombinationSteps.first()).toBeVisible({ timeout: 10000 })
  const stepCount = await loadCombinationSteps.count()
  const stepIndex = Math.min(1, Math.max(0, stepCount - 1))
  const clickedCombination = await loadCombinationSteps.nth(stepIndex).getAttribute('data-load-combination-force-step-combination')
  let activeCombinationForPreview = clickedCombination || ''
  await loadCombinationSteps.nth(stepIndex).click()
  if (clickedCombination) {
    await expect(page.locator('[data-load-combination-force-matrix]')).toHaveAttribute('data-load-combination-force-selected-combination', clickedCombination)
    await expect(page.locator('[data-force-flow-lens]')).toHaveAttribute('data-force-flow-selected-combination', clickedCombination)
    await expect(page.locator('[data-story-force-flow-ledger]')).toHaveAttribute('data-story-force-flow-selected-combination', clickedCombination)
    await expect(page.locator('[data-member-force-envelope]')).toHaveAttribute('data-member-force-envelope-selected-combination', clickedCombination)
    await expect(page.locator('[data-member-force-history]')).toHaveAttribute('data-member-force-history-selected-combination', clickedCombination)
    await expect(page.locator('#member-material-nonlinear-state-panel')).toHaveAttribute('data-member-material-nonlinear-selected-combination', clickedCombination)
    await expect(page.locator('[data-member-section-capacity]')).toHaveAttribute('data-member-section-capacity-selected-combination', clickedCombination)
  }
  const playbackNext = page.locator('[data-member-force-playback-action="next"]')
  await expect(playbackNext).toBeVisible({ timeout: 10000 })
  await playbackNext.click()
  const playbackCombination = await page.locator('[data-member-force-playback]').getAttribute('data-member-force-playback-active-combination')
  if (playbackCombination) {
    activeCombinationForPreview = playbackCombination
    await expect(page.locator('[data-load-combination-force-matrix]')).toHaveAttribute('data-load-combination-force-selected-combination', playbackCombination)
    await expect(page.locator('[data-member-force-diagram]')).toHaveAttribute('data-member-force-diagram-selected-combination', playbackCombination)
    await expect(page.locator('[data-story-force-flow-ledger]')).toHaveAttribute('data-story-force-flow-selected-combination', playbackCombination)
    await expect(page.locator('[data-member-force-history]')).toHaveAttribute('data-member-force-history-selected-combination', playbackCombination)
    await expect(page.locator('#member-material-nonlinear-state-panel')).toHaveAttribute('data-member-material-nonlinear-selected-combination', playbackCombination)
    await expect(page.locator('[data-member-section-capacity]')).toHaveAttribute('data-member-section-capacity-selected-combination', playbackCombination)
  }
  await page.locator('#integrated-review-map-button').click()
  await expect(page.locator('[data-integrated-review-navigator]')).toHaveAttribute('data-integrated-review-open', 'true')
  await expect(page.locator('[data-integrated-review-drawing]').first()).toBeVisible({ timeout: 10000 })
  await expect(page.locator('[data-integrated-review-section]').first()).toBeVisible({ timeout: 10000 })
  await page.locator('[data-integrated-review-section-key="loads"]').focus()
  await expect(page.locator('[data-integrated-review-preview]')).toHaveAttribute('data-integrated-review-preview-section', 'loads')
  const reviewMapSnapshot = await page.evaluate(() => ({
    schema: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-schema') || '',
    status: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-status') || '',
    activeSection: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-active-section') || '',
    drawingCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-drawing-count') || '0'),
    allDrawingCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-all-drawing-count') || '0'),
    sectionCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-section-count') || '0'),
    drawingButtonCount: document.querySelectorAll('[data-integrated-review-drawing]').length,
    sectionButtonCount: document.querySelectorAll('[data-integrated-review-section]').length,
    previewSchema: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-schema') || '',
    previewStatus: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-status') || '',
    previewSection: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-section') || '',
    previewTarget: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-target') || '',
    previewRowCount: Number(document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-row-count') || '0'),
    previewRenderedRowCount: document.querySelectorAll('[data-integrated-review-preview-row]').length,
    previewOpenTarget: document.querySelector('[data-integrated-review-preview-open]')?.getAttribute('data-integrated-review-target') || '',
    previewText: document.querySelector('[data-integrated-review-preview]')?.textContent || '',
    windowState: window.__STRUCTURE_VIEWER_INTEGRATED_REVIEW_NAVIGATOR_STATE__ || null,
    overflowCount: [...document.querySelectorAll('[data-integrated-review-navigator] button, [data-integrated-review-navigator] strong, [data-integrated-review-navigator] small, [data-integrated-review-navigator] em')].filter((node) => {
      if (!(node instanceof HTMLElement)) return false
      return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
    }).length,
  }))
  expect(reviewMapSnapshot.schema).toBe('structure-viewer-integrated-review-navigator.v1')
  expect(reviewMapSnapshot.status).toBe('ready')
  expect(reviewMapSnapshot.activeSection).toBe('loads')
  expect(reviewMapSnapshot.drawingCount).toBeGreaterThanOrEqual(2)
  expect(reviewMapSnapshot.allDrawingCount).toBeGreaterThanOrEqual(reviewMapSnapshot.drawingCount)
  expect(reviewMapSnapshot.sectionCount).toBeGreaterThanOrEqual(8)
  expect(reviewMapSnapshot.drawingButtonCount).toBe(reviewMapSnapshot.drawingCount)
  expect(reviewMapSnapshot.sectionButtonCount).toBe(reviewMapSnapshot.sectionCount)
  expect(reviewMapSnapshot.previewSchema).toBe('structure-viewer-integrated-review-preview.v1')
  expect(reviewMapSnapshot.previewStatus).toBe('ready')
  expect(reviewMapSnapshot.previewSection).toBe('loads')
  expect(reviewMapSnapshot.previewTarget).toBe('loadcomb-section')
  expect(reviewMapSnapshot.previewRowCount).toBeGreaterThanOrEqual(4)
  expect(reviewMapSnapshot.previewRenderedRowCount).toBe(reviewMapSnapshot.previewRowCount)
  expect(reviewMapSnapshot.previewOpenTarget).toBe('loadcomb-section')
  expect(reviewMapSnapshot.previewText).toContain('Selected Combination')
  if (activeCombinationForPreview) expect(reviewMapSnapshot.previewText).toContain(activeCombinationForPreview)
  expect(reviewMapSnapshot.windowState?.open).toBe(true)
  expect(reviewMapSnapshot.windowState?.previewSchemaVersion).toBe('structure-viewer-integrated-review-preview.v1')
  expect(reviewMapSnapshot.windowState?.activePreviewSectionKey).toBe('loads')
  expect(reviewMapSnapshot.windowState?.previewRowCount).toBe(reviewMapSnapshot.previewRowCount)
  expect(reviewMapSnapshot.overflowCount).toBe(0)
  await page.locator('[data-integrated-review-close]').click()
  await expect(page.locator('[data-integrated-review-navigator]')).toHaveAttribute('data-integrated-review-open', 'false')
  await page.locator('#member-search-input').fill('')

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
    const calloutAnchors = rectFor('[data-stage-result-callout-anchors]')
    const stageReceipt = rectFor('#stage-result-receipt')
    const stageOverlayReceipt = rectFor('[data-stage-overlay-receipt]')
    const stageLoadSupportGlyphs = rectFor('[data-stage-load-support-glyphs]')
    const stageReviewControls = rectFor('[data-stage-review-controls]')
    const stageModelStack = rectFor('[data-stage-model-stack]')
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
      '[data-stage-result-callout-anchor]',
      '[data-stage-drift-band]',
      '[data-stage-critical-hotspot]',
      '[data-panel-zone-stage-badge]',
      '[data-stage-member-force-playback-trail-frame]',
      '[data-stage-member-force-vector]',
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
      stageDominanceBudget: document.querySelector('#viewport')?.getAttribute('data-stage-dominance-budget') || '',
      stageOverlayBudgetNodeCount: overlayBudgetRects.length,
      stageOverlayViewportOcclusionRatio: viewport ? overlayViewportArea / Math.max(1, viewport.width * viewport.height) : 1,
      stageOverlayCentralOcclusionRatio: stageCentralClearRect ? overlayCentralArea / Math.max(1, stageCentralClearRect.width * stageCentralClearRect.height) : 1,
      stageViewportWidthRatio: viewport && stageFrame ? viewport.width / Math.max(1, stageFrame.width) : 0,
      stageViewportAreaRatio: viewport && stageFrame ? (viewport.width * viewport.height) / Math.max(1, stageFrame.width * stageFrame.height) : 0,
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
      integratedReviewOpenerCount: document.querySelectorAll('[data-integrated-review-open]').length,
      integratedReviewSchema: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-schema') || '',
      integratedReviewOpen: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-open') || '',
      integratedReviewDrawingCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-drawing-count') || '0'),
      integratedReviewAllDrawingCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-all-drawing-count') || '0'),
      integratedReviewSectionCount: Number(document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-section-count') || '0'),
      integratedReviewActiveSection: document.querySelector('[data-integrated-review-navigator]')?.getAttribute('data-integrated-review-active-section') || '',
      integratedReviewPreviewSchema: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-schema') || '',
      integratedReviewPreviewSection: document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-section') || '',
      integratedReviewPreviewRowCount: Number(document.querySelector('[data-integrated-review-preview]')?.getAttribute('data-integrated-review-preview-row-count') || '0'),
      integratedReviewWindowState: window.__STRUCTURE_VIEWER_INTEGRATED_REVIEW_NAVIGATOR_STATE__ || null,
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
      viewerWorkflow: document.body.getAttribute('data-viewer-workflow') || '',
      drawingsTabHref: document.querySelector('[data-viewer-workflow-tab="drawings"]')?.getAttribute('href') || '',
      layerToggleCount: document.querySelectorAll('[data-layer-toggle-row]').length,
      layerGroupText: [...document.querySelectorAll('.layer-toggle-group')].map((node) => node.textContent?.trim() || '').join(' '),
      materialFamilyLayerCount: document.querySelectorAll('[data-layer-toggle-group="Material families"]').length,
      materialLawLayerCount: document.querySelectorAll('[data-layer-toggle-group="Material laws"]').length,
      layerToggleText: document.querySelector('#layer-toggles')?.textContent || '',
      layerToggleOverflowCount: [...document.querySelectorAll('[data-layer-toggle-row], [data-layer-toggle-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      viewport,
      footer,
      chartStrip,
      rightPanel,
      stageFrame,
      callouts,
      calloutAnchors,
      focusBadge,
      toolRail,
      stageOverlayReceipt,
      stageOverlayPanel,
      stageReviewControls,
      stageModelStack,
      stageReviewModeValue: (document.querySelector('[data-stage-view-mode-select]') as HTMLSelectElement | null)?.value || '',
      stageReviewPresetValue: (document.querySelector('[data-stage-view-preset-select]') as HTMLSelectElement | null)?.value || '',
      stageReviewSelectCount: document.querySelectorAll('[data-stage-review-controls] select').length,
      stageReviewModelSchema: document.querySelector('[data-stage-model-stack]')?.getAttribute('data-stage-model-stack-schema') || '',
      stageReviewModelStatus: document.querySelector('[data-stage-model-stack]')?.getAttribute('data-stage-model-stack-status') || '',
      stageReviewModelRowCount: document.querySelectorAll('[data-stage-model-stack] [data-stage-model-layer]').length,
      stageReviewModelSwatchCount: document.querySelectorAll('[data-stage-model-stack] .stage-model-stack__swatch').length,
      stageReviewOptimizedLayerStatus: document.querySelector('[data-stage-model-layer="optimized"]')?.getAttribute('data-stage-model-layer-status') || '',
      stageReviewOriginalLayerStatus: document.querySelector('[data-stage-model-layer="original"]')?.getAttribute('data-stage-model-layer-status') || '',
      stageReviewDeformedLayerStatus: document.querySelector('[data-stage-model-layer="deformed"]')?.getAttribute('data-stage-model-layer-status') || '',
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
      kpiChipCount: document.querySelectorAll('#kpi-summary-panel [data-kpi-chip]').length,
      kpiChipFullLabelCount: document.querySelectorAll('#kpi-summary-panel [data-kpi-chip-full-label]').length,
      kpiChipShortLabelCount: document.querySelectorAll('#kpi-summary-panel [data-kpi-chip-short-label]').length,
      kpiChipText: [...document.querySelectorAll('#kpi-summary-panel [data-kpi-chip]')].map((node) => node.textContent || '').join(' '),
      kpiChipOverflowCount: [...document.querySelectorAll('#kpi-summary-panel [data-kpi-chip]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
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
      analysisTimelineFooterStatus: document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-status') || '',
      analysisTimelineFooterSchema: document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-schema') || '',
      analysisTimelineFooterActiveStep: Number(document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-active-step') || '0'),
      analysisTimelineFooterTotalSteps: Number(document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-total-steps') || '0'),
      analysisTimelineFooterTickCount: document.querySelectorAll('[data-analysis-timeline-step-tick]').length,
      analysisTimelineFooterActiveTickCount: document.querySelectorAll('[data-analysis-timeline-step-tick][aria-current="step"]').length,
      analysisTimelineFooterSolvedTickCount: document.querySelectorAll('[data-analysis-timeline-step-tick][data-analysis-timeline-tick-status="solved"]').length,
      analysisTimelineFooterLoadCase: document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-load-case') || '',
      analysisTimelineFooterSolver: document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-solver') || '',
      analysisTimelineFooterConvergence: document.querySelector('[data-analysis-timeline-footer]')?.getAttribute('data-analysis-timeline-convergence') || '',
      analysisTimelineFooterWindowState: window.__STRUCTURE_VIEWER_ANALYSIS_TIMELINE_FOOTER_STATE__ || null,
      analysisTimelineFooterOverflowCount: [...document.querySelectorAll('[data-analysis-timeline-footer], [data-analysis-timeline-footer] .analysis-timeline-field strong, [data-analysis-timeline-footer] .analysis-timeline-slider, [data-analysis-timeline-footer] [data-analysis-timeline-step-tick]')].filter((node) => {
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
      forceFlowStatus: document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-status') || '',
      forceFlowSchema: document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-schema') || '',
      forceFlowRowCount: Number(document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-row-count') || '0'),
      forceFlowSourceBackedCount: Number(document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-source-backed-count') || '0'),
      forceFlowBaseReaction: Number(document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-base-reaction-kn') || '0'),
      forceFlowGoverningMember: document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-governing-member') || '',
      forceFlowLoadCase: document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-load-case') || '',
      forceFlowSelectedCombination: document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-selected-combination') || '',
      forceFlowActiveStep: Number(document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-active-step') || '0'),
      forceFlowTotalSteps: Number(document.querySelector('[data-force-flow-lens]')?.getAttribute('data-force-flow-total-steps') || '0'),
      forceFlowRenderedRowCount: document.querySelectorAll('[data-force-flow-lens] [data-force-flow-row]').length,
      forceFlowMemberRowCount: document.querySelectorAll('[data-force-flow-lens] [data-force-flow-member-id]').length,
      forceFlowWindowState: window.__STRUCTURE_VIEWER_FORCE_FLOW_LENS_STATE__ || null,
      forceFlowOverflowCount: [...document.querySelectorAll('[data-force-flow-lens], [data-force-flow-lens] [data-force-flow-row], [data-force-flow-lens] [data-force-flow-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      storyForceFlowStatus: document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-status') || '',
      storyForceFlowSchema: document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-schema') || '',
      storyForceFlowRowCount: Number(document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-row-count') || '0'),
      storyForceFlowStoryCount: Number(document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-story-count') || '0'),
      storyForceFlowForceRowCount: Number(document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-force-row-count') || '0'),
      storyForceFlowSourceBackedCount: Number(document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-source-backed-count') || '0'),
      storyForceFlowSelectedCombination: document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-selected-combination') || '',
      storyForceFlowGoverningStory: document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-governing-story') || '',
      storyForceFlowMaxDcr: Number(document.querySelector('[data-story-force-flow-ledger]')?.getAttribute('data-story-force-flow-max-dcr') || '0'),
      storyForceFlowRenderedRowCount: document.querySelectorAll('[data-story-force-flow-ledger] [data-story-force-flow-row]').length,
      storyForceFlowBarCount: document.querySelectorAll('[data-story-force-flow-ledger] .story-force-flow-bar').length,
      storyForceFlowWindowState: window.__STRUCTURE_VIEWER_STORY_FORCE_FLOW_LEDGER_STATE__ || null,
      storyForceFlowText: document.querySelector('[data-story-force-flow-ledger]')?.textContent || '',
      storyForceFlowOverflowCount: [...document.querySelectorAll('[data-story-force-flow-ledger], [data-story-force-flow-ledger] [data-story-force-flow-row], [data-story-force-flow-ledger] [data-story-force-flow-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      loadCombinationForceStatus: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-status') || '',
      loadCombinationForceSchema: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-schema') || '',
      loadCombinationForceRowCount: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-row-count') || '0'),
      loadCombinationForceCombinationCount: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-combination-count') || '0'),
      loadCombinationForceForceRowCount: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-force-row-count') || '0'),
      loadCombinationForceSourceBackedCount: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-source-backed-count') || '0'),
      loadCombinationForceMaxDcr: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-max-dcr') || '0'),
      loadCombinationForceGoverningCombination: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-governing-combination') || '',
      loadCombinationForceGoverningMember: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-governing-member') || '',
      loadCombinationForceStepperSchema: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-stepper-schema') || '',
      loadCombinationForceStepperCount: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-stepper-count') || '0'),
      loadCombinationForceSelectedCombination: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-selected-combination') || '',
      loadCombinationForceSelectedMember: document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-selected-member') || '',
      loadCombinationForceSelectedDcr: Number(document.querySelector('[data-load-combination-force-matrix]')?.getAttribute('data-load-combination-force-selected-dcr') || '0'),
      loadCombinationForceRenderedRowCount: document.querySelectorAll('[data-load-combination-force-matrix] [data-load-combination-force-row]').length,
      loadCombinationForceMemberRowCount: document.querySelectorAll('[data-load-combination-force-matrix] [data-load-combination-force-member-id]').length,
      loadCombinationForceStepButtonCount: document.querySelectorAll('[data-load-combination-force-step-combination]').length,
      loadCombinationForceActiveStepCount: document.querySelectorAll('[data-load-combination-force-step-combination][aria-pressed="true"]').length,
      loadCombinationForceActiveRowCount: document.querySelectorAll('[data-load-combination-force-row][data-load-combination-force-active="true"]').length,
      loadCombinationForceWindowState: window.__STRUCTURE_VIEWER_LOAD_COMBINATION_FORCE_MATRIX_STATE__ || null,
      loadCombinationForceOverflowCount: [...document.querySelectorAll('[data-load-combination-force-matrix], [data-load-combination-force-matrix] [data-load-combination-force-row], [data-load-combination-force-matrix] [data-load-combination-force-step], [data-load-combination-force-matrix] [data-load-combination-force-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberForceDiagramStatus: document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-status') || '',
      memberForceDiagramSchema: document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-schema') || '',
      memberForceDiagramRowCount: Number(document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-row-count') || '0'),
      memberForceDiagramDiagramCount: Number(document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-diagram-count') || '0'),
      memberForceDiagramSourceBackedCount: Number(document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-source-backed-count') || '0'),
      memberForceDiagramMaxDcr: Number(document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-max-dcr') || '0'),
      memberForceDiagramSelectedCombination: document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-selected-combination') || '',
      memberForceDiagramSelectedMember: document.querySelector('[data-member-force-diagram]')?.getAttribute('data-member-force-diagram-selected-member') || '',
      memberForceDiagramRenderedRowCount: document.querySelectorAll('[data-member-force-diagram] [data-member-force-diagram-row]').length,
      memberForceDiagramSvgCount: document.querySelectorAll('[data-member-force-diagram] [data-member-force-diagram-svg]').length,
      memberForceDiagramKindCount: new Set([...document.querySelectorAll('[data-member-force-diagram-row]')].map((node) => node.getAttribute('data-member-force-diagram-kind') || '')).size,
      memberForceDiagramWindowState: window.__STRUCTURE_VIEWER_MEMBER_FORCE_DIAGRAM_STATE__ || null,
      memberForceDiagramText: document.querySelector('[data-member-force-diagram]')?.textContent || '',
      memberForceDiagramOverflowCount: [...document.querySelectorAll('[data-member-force-diagram], [data-member-force-diagram] [data-member-force-diagram-row], [data-member-force-diagram] [data-member-force-diagram-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberForceEnvelopeStatus: document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-status') || '',
      memberForceEnvelopeSchema: document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-schema') || '',
      memberForceEnvelopeRowCount: Number(document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-row-count') || '0'),
      memberForceEnvelopeSampleCount: Number(document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-sample-count') || '0'),
      memberForceEnvelopeSourceBackedCount: Number(document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-source-backed-count') || '0'),
      memberForceEnvelopeMaxDcr: Number(document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-max-dcr') || '0'),
      memberForceEnvelopeSelectedCombination: document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-selected-combination') || '',
      memberForceEnvelopeSelectedMember: document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-selected-member') || '',
      memberForceEnvelopeGoverningCombination: document.querySelector('[data-member-force-envelope]')?.getAttribute('data-member-force-envelope-governing-combination') || '',
      memberForceEnvelopeRenderedRowCount: document.querySelectorAll('[data-member-force-envelope] [data-member-force-envelope-row]').length,
      memberForceEnvelopeSvgCount: document.querySelectorAll('[data-member-force-envelope] [data-member-force-envelope-svg]').length,
      memberForceEnvelopePointCount: document.querySelectorAll('[data-member-force-envelope] [data-member-force-envelope-point]').length,
      memberForceEnvelopeSelectedPointCount: document.querySelectorAll('[data-member-force-envelope] [data-member-force-envelope-point].is-selected').length,
      memberForceEnvelopeWindowState: window.__STRUCTURE_VIEWER_MEMBER_FORCE_ENVELOPE_STATE__ || null,
      memberForceEnvelopeText: document.querySelector('[data-member-force-envelope]')?.textContent || '',
      memberForceEnvelopeOverflowCount: [...document.querySelectorAll('[data-member-force-envelope], [data-member-force-envelope] [data-member-force-envelope-row], [data-member-force-envelope] [data-member-force-envelope-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberForceHistoryStatus: document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-status') || '',
      memberForceHistorySchema: document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-schema') || '',
      memberForceHistoryRowCount: Number(document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-row-count') || '0'),
      memberForceHistorySampleCount: Number(document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-sample-count') || '0'),
      memberForceHistorySourceBackedCount: Number(document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-source-backed-count') || '0'),
      memberForceHistoryMaxDcr: Number(document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-max-dcr') || '0'),
      memberForceHistorySelectedCombination: document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-selected-combination') || '',
      memberForceHistorySelectedMember: document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-selected-member') || '',
      memberForceHistoryGoverningCombination: document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-governing-combination') || '',
      memberForceHistoryActiveFrame: Number(document.querySelector('[data-member-force-history]')?.getAttribute('data-member-force-history-active-frame') || '0'),
      memberForceHistoryRenderedRowCount: document.querySelectorAll('[data-member-force-history] [data-member-force-history-row]').length,
      memberForceHistorySvgCount: document.querySelectorAll('[data-member-force-history] [data-member-force-history-svg]').length,
      memberForceHistoryPointCount: document.querySelectorAll('[data-member-force-history] [data-member-force-history-point]').length,
      memberForceHistorySelectedPointCount: document.querySelectorAll('[data-member-force-history] [data-member-force-history-point].is-selected').length,
      memberForceHistoryWindowState: window.__STRUCTURE_VIEWER_MEMBER_FORCE_HISTORY_STATE__ || null,
      memberForceHistoryText: document.querySelector('[data-member-force-history]')?.textContent || '',
      memberForceHistoryOverflowCount: [...document.querySelectorAll('[data-member-force-history], [data-member-force-history] [data-member-force-history-row], [data-member-force-history] [data-member-force-history-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberMaterialNonlinearStatus: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-status') || '',
      memberMaterialNonlinearSchema: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-schema') || '',
      memberMaterialNonlinearRowCount: Number(document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-row-count') || '0'),
      memberMaterialNonlinearSourceBackedCount: Number(document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-source-backed-count') || '0'),
      memberMaterialNonlinearSelectedCombination: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-selected-combination') || '',
      memberMaterialNonlinearSelectedMember: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-selected-member') || '',
      memberMaterialNonlinearGoverningCombination: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-governing-combination') || '',
      memberMaterialNonlinearMaterialId: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-material-id') || '',
      memberMaterialNonlinearSectionId: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-section-id') || '',
      memberMaterialNonlinearDemandRatio: Number(document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-demand-ratio') || '0'),
      memberMaterialNonlinearState: document.querySelector('[data-member-material-nonlinear-state]')?.getAttribute('data-member-material-nonlinear-state') || '',
      memberMaterialNonlinearRenderedRowCount: document.querySelectorAll('[data-member-material-nonlinear-state] [data-member-material-nonlinear-row]').length,
      memberMaterialNonlinearSvgCount: document.querySelectorAll('[data-member-material-nonlinear-state] [data-member-material-nonlinear-svg]').length,
      memberMaterialNonlinearDemandMarkerCount: document.querySelectorAll('[data-member-material-nonlinear-state] [data-member-material-nonlinear-demand-marker]').length,
      memberMaterialNonlinearYieldMarkerCount: document.querySelectorAll('[data-member-material-nonlinear-state] [data-member-material-nonlinear-yield-marker]').length,
      memberMaterialNonlinearForceRowCount: document.querySelectorAll('[data-member-material-nonlinear-state] [data-member-material-nonlinear-force-row]').length,
      memberMaterialNonlinearWindowState: window.__STRUCTURE_VIEWER_MEMBER_MATERIAL_NONLINEAR_STATE__ || null,
      memberMaterialNonlinearText: document.querySelector('[data-member-material-nonlinear-state]')?.textContent || '',
      memberMaterialNonlinearOverflowCount: [...document.querySelectorAll('[data-member-material-nonlinear-state], [data-member-material-nonlinear-state] [data-member-material-nonlinear-row], [data-member-material-nonlinear-state] [data-member-material-nonlinear-force-row], [data-member-material-nonlinear-state] [data-member-material-nonlinear-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberSectionCapacityStatus: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-status') || '',
      memberSectionCapacitySchema: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-schema') || '',
      memberSectionCapacityRowCount: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-row-count') || '0'),
      memberSectionCapacitySelectedCombination: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-selected-combination') || '',
      memberSectionCapacitySelectedMember: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-selected-member') || '',
      memberSectionCapacityMaterialId: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-material-id') || '',
      memberSectionCapacitySectionId: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-section-id') || '',
      memberSectionCapacitySourceBackedCount: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-source-backed-count') || '0'),
      memberSectionCapacitySourceCapacityCount: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-source-capacity-count') || '0'),
      memberSectionCapacityEstimatedCapacityCount: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-estimated-capacity-count') || '0'),
      memberSectionCapacityEvidenceCount: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-evidence-count') || '0'),
      memberSectionCapacityMaxDcr: Number(document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-max-dcr') || '0'),
      memberSectionCapacityGeometryReady: document.querySelector('[data-member-section-capacity]')?.getAttribute('data-member-section-capacity-geometry-ready') || '',
      memberSectionCapacityRenderedRowCount: document.querySelectorAll('[data-member-section-capacity] [data-member-section-capacity-row]').length,
      memberSectionCapacityBarCount: document.querySelectorAll('[data-member-section-capacity] .member-section-capacity-row__bar').length,
      memberSectionCapacityWindowState: window.__STRUCTURE_VIEWER_MEMBER_SECTION_CAPACITY_STATE__ || null,
      memberSectionCapacityText: document.querySelector('[data-member-section-capacity]')?.textContent || '',
      memberSectionCapacityOverflowCount: [...document.querySelectorAll('[data-member-section-capacity], [data-member-section-capacity] [data-member-section-capacity-row], [data-member-section-capacity] [data-member-section-capacity-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      memberForcePlaybackStatus: document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-status') || '',
      memberForcePlaybackSchema: document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-schema') || '',
      memberForcePlaybackFrameCount: Number(document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-frame-count') || '0'),
      memberForcePlaybackActiveFrame: Number(document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-active-frame') || '0'),
      memberForcePlaybackActiveCombination: document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-active-combination') || '',
      memberForcePlaybackSelectedMember: document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-selected-member') || '',
      memberForcePlaybackMaxDcr: Number(document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-max-dcr') || '0'),
      memberForcePlaybackSourceBackedCount: Number(document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-source-backed-count') || '0'),
      memberForcePlaybackPlaying: document.querySelector('[data-member-force-playback]')?.getAttribute('data-member-force-playback-playing') || '',
      memberForcePlaybackRenderedFrameCount: document.querySelectorAll('[data-member-force-playback] [data-member-force-playback-frame]').length,
      memberForcePlaybackActionCount: document.querySelectorAll('[data-member-force-playback] [data-member-force-playback-action]').length,
      memberForcePlaybackActiveButtonCount: document.querySelectorAll('[data-member-force-playback] [data-member-force-playback-frame][aria-pressed="true"]').length,
      memberForcePlaybackWindowState: window.__STRUCTURE_VIEWER_MEMBER_FORCE_PLAYBACK_STATE__ || null,
      memberForcePlaybackText: document.querySelector('[data-member-force-playback]')?.textContent || '',
      memberForcePlaybackOverflowCount: [...document.querySelectorAll('[data-member-force-playback], [data-member-force-playback] [data-member-force-playback-frame], [data-member-force-playback] [data-member-force-playback-summary] span, [data-member-force-playback] [data-member-force-playback-controls] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMemberForcePlaybackTrailStatus: document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-status') || '',
      stageMemberForcePlaybackTrailSchema: document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-schema') || '',
      stageMemberForcePlaybackTrailFrameCount: Number(document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-frame-count') || '0'),
      stageMemberForcePlaybackTrailRenderedFrameCount: Number(document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-rendered-frame-count') || '0'),
      stageMemberForcePlaybackTrailActiveFrame: Number(document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-active-frame') || '0'),
      stageMemberForcePlaybackTrailActiveCombination: document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-active-combination') || '',
      stageMemberForcePlaybackTrailSelectedMember: document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-selected-member') || '',
      stageMemberForcePlaybackTrailMaxDcr: Number(document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-max-dcr') || '0'),
      stageMemberForcePlaybackTrailProjectedCount: Number(document.querySelector('[data-stage-member-force-playback-trail]')?.getAttribute('data-stage-member-force-playback-trail-projected-count') || '0'),
      stageMemberForcePlaybackTrailFrameButtonCount: document.querySelectorAll('[data-stage-member-force-playback-trail-frame]').length,
      stageMemberForcePlaybackTrailActiveFrameCount: document.querySelectorAll('[data-stage-member-force-playback-trail-frame][aria-pressed="true"]').length,
      stageMemberForcePlaybackTrailProjectionCount: document.querySelectorAll('[data-stage-member-force-playback-trail-projection]').length,
      stageMemberForcePlaybackTrailVisible: Boolean(document.querySelector('[data-stage-member-force-playback-trail]')?.classList.contains('is-visible')),
      stageMemberForcePlaybackTrailWindowState: window.__STRUCTURE_VIEWER_STAGE_MEMBER_FORCE_PLAYBACK_TRAIL_STATE__ || null,
      stageMemberForcePlaybackTrailText: document.querySelector('[data-stage-member-force-playback-trail]')?.textContent || '',
      stageMemberForcePlaybackTrailOverlapFocus: [...document.querySelectorAll('[data-stage-member-force-playback-trail-frame]')].reduce((total, node) => {
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
      stageMemberForcePlaybackTrailOverflowCount: [...document.querySelectorAll('[data-stage-member-force-playback-trail-frame], [data-stage-member-force-playback-trail-frame] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMemberForceVectorFieldStatus: document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-field-status') || '',
      stageMemberForceVectorFieldSchema: document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-field-schema') || '',
      stageMemberForceVectorCount: Number(document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-count') || '0'),
      stageMemberForceVectorSourceBackedCount: Number(document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-source-backed-count') || '0'),
      stageMemberForceVectorActiveFrame: Number(document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-active-frame') || '0'),
      stageMemberForceVectorActiveCombination: document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-active-combination') || '',
      stageMemberForceVectorSelectedMember: document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-selected-member') || '',
      stageMemberForceVectorMaxDcr: Number(document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-max-dcr') || '0'),
      stageMemberForceVectorProjectedCount: Number(document.querySelector('[data-stage-member-force-vector-field]')?.getAttribute('data-stage-member-force-vector-projected-count') || '0'),
      stageMemberForceVectorButtonCount: document.querySelectorAll('[data-stage-member-force-vector]').length,
      stageMemberForceVectorProjectionCount: document.querySelectorAll('[data-stage-member-force-vector-projection]').length,
      stageMemberForceVectorKindText: [...document.querySelectorAll('[data-stage-member-force-vector-kind]')].map((node) => node.getAttribute('data-stage-member-force-vector-kind') || '').join(' '),
      stageMemberForceVectorVisible: Boolean(document.querySelector('[data-stage-member-force-vector-field]')?.classList.contains('is-visible')),
      stageMemberForceVectorWindowState: window.__STRUCTURE_VIEWER_STAGE_MEMBER_FORCE_VECTOR_FIELD_STATE__ || null,
      stageMemberForceVectorText: document.querySelector('[data-stage-member-force-vector-field]')?.textContent || '',
      stageMemberForceVectorOverlapFocus: [...document.querySelectorAll('[data-stage-member-force-vector]')].reduce((total, node) => {
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
      stageMemberForceVectorOverflowCount: [...document.querySelectorAll('[data-stage-member-force-vector], [data-stage-member-force-vector] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMemberMaterialStateBadgeStatus: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-badge-status') || '',
      stageMemberMaterialStateBadgeSchema: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-badge-schema') || '',
      stageMemberMaterialStateMember: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-member') || '',
      stageMemberMaterialStateCombination: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-combination') || '',
      stageMemberMaterialStateMaterialId: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-material-id') || '',
      stageMemberMaterialStateSectionId: document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-section-id') || '',
      stageMemberMaterialStateDemandRatio: Number(document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-demand-ratio') || '0'),
      stageMemberMaterialStateMaxDcr: Number(document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-max-dcr') || '0'),
      stageMemberMaterialStateSourceBackedCount: Number(document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-source-backed-count') || '0'),
      stageMemberMaterialStateProjectedCount: Number(document.querySelector('[data-stage-member-material-state-badge]')?.getAttribute('data-stage-member-material-state-projected-count') || '0'),
      stageMemberMaterialStateCardCount: document.querySelectorAll('[data-stage-member-material-state-card]').length,
      stageMemberMaterialStateProjectionCount: document.querySelectorAll('[data-stage-member-material-state-projection]').length,
      stageMemberMaterialStateVisible: Boolean(document.querySelector('[data-stage-member-material-state-badge]')?.classList.contains('is-visible')),
      stageMemberMaterialStateText: document.querySelector('[data-stage-member-material-state-badge]')?.textContent || '',
      stageMemberMaterialStateWindowState: window.__STRUCTURE_VIEWER_STAGE_MEMBER_MATERIAL_STATE_BADGE_STATE__ || null,
      stageMemberMaterialStateOverlapFocus: [...document.querySelectorAll('[data-stage-member-material-state-card]')].reduce((total, node) => {
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
      stageMemberMaterialStateOverflowCount: [...document.querySelectorAll('[data-stage-member-material-state-card], [data-stage-member-material-state-card] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageLoadCombinationForceGlyphsStatus: document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-glyphs-status') || '',
      stageLoadCombinationForceGlyphsSchema: document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-glyphs-schema') || '',
      stageLoadCombinationForceGlyphCount: Number(document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-glyph-count') || '0'),
      stageLoadCombinationForceProjectedCount: Number(document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-projected-count') || '0'),
      stageLoadCombinationForceSelectedCombination: document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-selected-combination') || '',
      stageLoadCombinationForceSelectedMember: document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-selected-member') || '',
      stageLoadCombinationForceMaxDcr: Number(document.querySelector('[data-stage-load-combination-force-glyphs]')?.getAttribute('data-stage-load-combination-force-max-dcr') || '0'),
      stageLoadCombinationForceMemberCount: document.querySelectorAll('[data-stage-load-combination-force-glyph-member]').length,
      stageLoadCombinationForceProjectionCount: document.querySelectorAll('[data-stage-load-combination-force-glyph-projection]').length,
      stageLoadCombinationForceVisible: Boolean(document.querySelector('[data-stage-load-combination-force-glyphs]')?.classList.contains('is-visible')),
      stageLoadCombinationForceText: document.querySelector('[data-stage-load-combination-force-glyphs]')?.textContent || '',
      stageLoadCombinationForceWindowState: window.__STRUCTURE_VIEWER_STAGE_LOAD_COMBINATION_FORCE_GLYPHS_STATE__ || null,
      stageLoadCombinationForceOverlapFocus: [...document.querySelectorAll('[data-stage-load-combination-force-glyph]')].reduce((total, node) => {
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
      stageLoadCombinationForceOverflowCount: [...document.querySelectorAll('[data-stage-load-combination-force-glyph], [data-stage-load-combination-force-glyph] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageForceDemandContourStatus: document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-status') || '',
      stageForceDemandContourSchema: document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-schema') || '',
      stageForceDemandContourCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-count') || '0'),
      stageForceDemandContourRenderedCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-rendered-count') || '0'),
      stageForceDemandContourProjectedCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-projected-count') || '0'),
      stageForceDemandContourForceRowCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-force-row-count') || '0'),
      stageForceDemandContourMappedForceRowCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-mapped-force-row-count') || '0'),
      stageForceDemandContourSourceBackedCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-source-backed-count') || '0'),
      stageForceDemandContourSelectedCombination: document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-selected-combination') || '',
      stageForceDemandContourMaxDcr: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-max-dcr') || '0'),
      stageForceDemandContourMaterialLockStatus: document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-material-lock-status') || '',
      stageForceDemandContourMaterialModelCount: Number(document.querySelector('[data-stage-force-demand-contour]')?.getAttribute('data-stage-force-demand-contour-material-model-count') || '0'),
      stageForceDemandContourMarkerCount: document.querySelectorAll('[data-stage-force-demand-contour-marker]').length,
      stageForceDemandContourProjectionCount: document.querySelectorAll('[data-stage-force-demand-projection]').length,
      stageForceDemandContourMaterialModelText: [...document.querySelectorAll('[data-stage-force-demand-material-model]')].map((node) => node.getAttribute('data-stage-force-demand-material-model') || '').join(' '),
      stageForceDemandContourVisible: Boolean(document.querySelector('[data-stage-force-demand-contour]')?.classList.contains('is-visible')),
      stageForceDemandContourText: document.querySelector('[data-stage-force-demand-contour]')?.textContent || '',
      stageForceDemandContourWindowState: window.__STRUCTURE_VIEWER_STAGE_FORCE_DEMAND_CONTOUR_STATE__ || null,
      stageForceDemandContourOverflowCount: [...document.querySelectorAll('[data-stage-force-demand-contour], [data-stage-force-demand-contour] *, [data-stage-force-demand-contour-marker], [data-stage-force-demand-contour-marker] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMaterialModelDemandBadgesStatus: document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-badges-status') || '',
      stageMaterialModelDemandBadgesSchema: document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-badges-schema') || '',
      stageMaterialModelDemandBadgesCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-badge-count') || '0'),
      stageMaterialModelDemandBadgesRenderedCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-rendered-count') || '0'),
      stageMaterialModelDemandBadgesProjectedCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-projected-count') || '0'),
      stageMaterialModelDemandBadgesEdgePinnedCount: document.querySelectorAll('[data-stage-material-model-demand-badge].is-edge-pinned').length,
      stageMaterialModelDemandBadgesDockedCount: document.querySelectorAll('[data-stage-material-model-demand-projection="docked"]').length,
      stageMaterialModelDemandBadgesMaterialCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-material-count') || '0'),
      stageMaterialModelDemandBadgesForceBackedMaterialCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-force-backed-material-count') || '0'),
      stageMaterialModelDemandBadgesForceRowCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-force-row-count') || '0'),
      stageMaterialModelDemandBadgesMappedForceRowCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-mapped-force-row-count') || '0'),
      stageMaterialModelDemandBadgesSourceBackedCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-source-backed-count') || '0'),
      stageMaterialModelDemandBadgesSelectedCombination: document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-selected-combination') || '',
      stageMaterialModelDemandBadgesMaxDcr: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-max-dcr') || '0'),
      stageMaterialModelDemandBadgesLockStatus: document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-lock-status') || '',
      stageMaterialModelDemandBadgesLockedCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-locked-count') || '0'),
      stageMaterialModelDemandBadgesChangedCount: Number(document.querySelector('[data-stage-material-model-demand-badges]')?.getAttribute('data-stage-material-model-demand-changed-count') || '0'),
      stageMaterialModelDemandBadgesBadgeCount: document.querySelectorAll('[data-stage-material-model-demand-badge]').length,
      stageMaterialModelDemandBadgesProjectionCount: document.querySelectorAll('[data-stage-material-model-demand-projection]').length,
      stageMaterialModelDemandBadgesForceBackedBadgeCount: document.querySelectorAll('[data-stage-material-model-demand-force-backed="true"]').length,
      stageMaterialModelDemandBadgesVisible: Boolean(document.querySelector('[data-stage-material-model-demand-badges]')?.classList.contains('is-visible')),
      stageMaterialModelDemandBadgesText: document.querySelector('[data-stage-material-model-demand-badges]')?.textContent || '',
      stageMaterialModelDemandBadgesWindowState: window.__STRUCTURE_VIEWER_STAGE_MATERIAL_MODEL_DEMAND_BADGES_STATE__ || null,
      stageMaterialModelDemandBadgesOverflowCount: [...document.querySelectorAll('[data-stage-material-model-demand-badges], [data-stage-material-model-demand-badges] *, [data-stage-material-model-demand-badge], [data-stage-material-model-demand-badge] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMaterialForceRibbonsStatus: document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-ribbons-status') || '',
      stageMaterialForceRibbonsSchema: document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-ribbons-schema') || '',
      stageMaterialForceRibbonCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-ribbon-count') || '0'),
      stageMaterialForceRenderedCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-rendered-count') || '0'),
      stageMaterialForceProjectedCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-projected-count') || '0'),
      stageMaterialForceEdgePinnedCount: document.querySelectorAll('[data-stage-material-force-ribbon].is-edge-pinned').length,
      stageMaterialForceMaterialCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-material-count') || '0'),
      stageMaterialForceForceRowCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-force-row-count') || '0'),
      stageMaterialForceMappedForceRowCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-mapped-force-row-count') || '0'),
      stageMaterialForceSourceBackedCount: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-source-backed-count') || '0'),
      stageMaterialForceSelectedCombination: document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-selected-combination') || '',
      stageMaterialForceGoverningMaterial: document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-governing-material') || '',
      stageMaterialForceMaxDcr: Number(document.querySelector('[data-stage-material-force-ribbons]')?.getAttribute('data-stage-material-force-max-dcr') || '0'),
      stageMaterialForceRibbonButtonCount: document.querySelectorAll('[data-stage-material-force-ribbon]').length,
      stageMaterialForceProjectionCount: document.querySelectorAll('[data-stage-material-force-projection]').length,
      stageMaterialForceBarCount: document.querySelectorAll('[data-stage-material-force-ribbons] .stage-material-force-ribbon__bar').length,
      stageMaterialForceVisible: Boolean(document.querySelector('[data-stage-material-force-ribbons]')?.classList.contains('is-visible')),
      stageMaterialForceText: document.querySelector('[data-stage-material-force-ribbons]')?.textContent || '',
      stageMaterialForceWindowState: window.__STRUCTURE_VIEWER_STAGE_MATERIAL_FORCE_RIBBONS_STATE__ || null,
      stageMaterialForceOverflowCount: [...document.querySelectorAll('[data-stage-material-force-ribbons], [data-stage-material-force-ribbons] *, [data-stage-material-force-ribbon], [data-stage-material-force-ribbon] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMaterialForceEnvelopeStatus: document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-status') || '',
      stageMaterialForceEnvelopeSchema: document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-schema') || '',
      stageMaterialForceEnvelopeCardCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-card-count') || '0'),
      stageMaterialForceEnvelopeRenderedCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-rendered-count') || '0'),
      stageMaterialForceEnvelopeProjectedCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-projected-count') || '0'),
      stageMaterialForceEnvelopeEdgePinnedCount: document.querySelectorAll('[data-stage-material-force-envelope-card].is-edge-pinned').length,
      stageMaterialForceEnvelopeSourceRowCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-source-row-count') || '0'),
      stageMaterialForceEnvelopeMaterialCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-material-count') || '0'),
      stageMaterialForceEnvelopeCombinationCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-combination-count') || '0'),
      stageMaterialForceEnvelopeForceBackedMaterialCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-force-backed-material-count') || '0'),
      stageMaterialForceEnvelopeForceRowCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-force-row-count') || '0'),
      stageMaterialForceEnvelopeMappedForceRowCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-mapped-force-row-count') || '0'),
      stageMaterialForceEnvelopeSourceBackedCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-source-backed-count') || '0'),
      stageMaterialForceEnvelopeSelectedCombination: document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-selected-combination') || '',
      stageMaterialForceEnvelopeGoverningMaterial: document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-governing-material') || '',
      stageMaterialForceEnvelopeLockedCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-locked-count') || '0'),
      stageMaterialForceEnvelopeChangedCount: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-changed-count') || '0'),
      stageMaterialForceEnvelopeLockStatus: document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-lock-status') || '',
      stageMaterialForceEnvelopeMaterialMatchPercent: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-material-match-percent') || '0'),
      stageMaterialForceEnvelopeMemberAssignmentMatchPercent: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-member-assignment-match-percent') || '0'),
      stageMaterialForceEnvelopeMaxDcr: Number(document.querySelector('[data-stage-material-force-envelope]')?.getAttribute('data-stage-material-force-envelope-max-dcr') || '0'),
      stageMaterialForceEnvelopeButtonCount: document.querySelectorAll('[data-stage-material-force-envelope-card]').length,
      stageMaterialForceEnvelopeProjectionCount: document.querySelectorAll('[data-stage-material-force-envelope-projection]').length,
      stageMaterialForceEnvelopeForceBackedCardCount: document.querySelectorAll('[data-stage-material-force-envelope-force-backed="true"]').length,
      stageMaterialForceEnvelopeSvgCount: document.querySelectorAll('[data-stage-material-force-envelope] [data-stage-material-force-envelope-svg]').length,
      stageMaterialForceEnvelopePointCount: document.querySelectorAll('[data-stage-material-force-envelope] [data-stage-material-force-envelope-point]').length,
      stageMaterialForceEnvelopeBarCount: document.querySelectorAll('[data-stage-material-force-envelope] .stage-material-force-envelope-card__bar').length,
      stageMaterialForceEnvelopeVisible: Boolean(document.querySelector('[data-stage-material-force-envelope]')?.classList.contains('is-visible')),
      stageMaterialForceEnvelopeText: document.querySelector('[data-stage-material-force-envelope]')?.textContent || '',
      stageMaterialForceEnvelopeWindowState: window.__STRUCTURE_VIEWER_STAGE_MATERIAL_FORCE_ENVELOPE_STATE__ || null,
      stageMaterialForceEnvelopeOverflowCount: [...document.querySelectorAll('[data-stage-material-force-envelope], [data-stage-material-force-envelope] *, [data-stage-material-force-envelope-card], [data-stage-material-force-envelope-card] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageMaterialCapacityEnvelopeStatus: document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-status') || '',
      stageMaterialCapacityEnvelopeSchema: document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-schema') || '',
      stageMaterialCapacityEnvelopeCardCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-card-count') || '0'),
      stageMaterialCapacityEnvelopeRenderedCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-rendered-count') || '0'),
      stageMaterialCapacityEnvelopeProjectedCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-projected-count') || '0'),
      stageMaterialCapacityEnvelopeEdgePinnedCount: document.querySelectorAll('[data-stage-material-capacity-envelope-card].is-edge-pinned').length,
      stageMaterialCapacityEnvelopeSourceRowCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-source-row-count') || '0'),
      stageMaterialCapacityEnvelopeMaterialCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-material-count') || '0'),
      stageMaterialCapacityEnvelopeCombinationCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-combination-count') || '0'),
      stageMaterialCapacityEnvelopeForceRowCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-force-row-count') || '0'),
      stageMaterialCapacityEnvelopeMappedForceRowCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-mapped-force-row-count') || '0'),
      stageMaterialCapacityEnvelopeSourceBackedCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-source-backed-count') || '0'),
      stageMaterialCapacityEnvelopeSourceCapacityCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-source-capacity-count') || '0'),
      stageMaterialCapacityEnvelopeEstimatedCapacityCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-estimated-capacity-count') || '0'),
      stageMaterialCapacityEnvelopeCapacityBackedMaterialCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-capacity-backed-material-count') || '0'),
      stageMaterialCapacityEnvelopeSelectedCombination: document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-selected-combination') || '',
      stageMaterialCapacityEnvelopeGoverningMaterial: document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-governing-material') || '',
      stageMaterialCapacityEnvelopeLockedCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-locked-count') || '0'),
      stageMaterialCapacityEnvelopeChangedCount: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-changed-count') || '0'),
      stageMaterialCapacityEnvelopeLockStatus: document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-lock-status') || '',
      stageMaterialCapacityEnvelopeMaterialMatchPercent: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-material-match-percent') || '0'),
      stageMaterialCapacityEnvelopeMemberAssignmentMatchPercent: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-member-assignment-match-percent') || '0'),
      stageMaterialCapacityEnvelopeMaxDcr: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-max-dcr') || '0'),
      stageMaterialCapacityEnvelopeMinMarginPercent: Number(document.querySelector('[data-stage-material-capacity-envelope]')?.getAttribute('data-stage-material-capacity-envelope-min-margin-percent') || '0'),
      stageMaterialCapacityEnvelopeButtonCount: document.querySelectorAll('[data-stage-material-capacity-envelope-card]').length,
      stageMaterialCapacityEnvelopeProjectionCount: document.querySelectorAll('[data-stage-material-capacity-envelope-projection]').length,
      stageMaterialCapacityEnvelopeCapacityBackedCardCount: document.querySelectorAll('[data-stage-material-capacity-envelope-capacity-backed="true"]').length,
      stageMaterialCapacityEnvelopeSourceCapacityCardCount: document.querySelectorAll('[data-stage-material-capacity-envelope-card][data-stage-material-capacity-envelope-source-capacity-count]').length,
      stageMaterialCapacityEnvelopeEstimatedCapacityCardCount: document.querySelectorAll('[data-stage-material-capacity-envelope-card][data-stage-material-capacity-envelope-estimated-capacity-count]').length,
      stageMaterialCapacityEnvelopeSvgCount: document.querySelectorAll('[data-stage-material-capacity-envelope] [data-stage-material-capacity-envelope-svg]').length,
      stageMaterialCapacityEnvelopePointCount: document.querySelectorAll('[data-stage-material-capacity-envelope] [data-stage-material-capacity-envelope-point]').length,
      stageMaterialCapacityEnvelopeBarCount: document.querySelectorAll('[data-stage-material-capacity-envelope] .stage-material-capacity-envelope-card__bar').length,
      stageMaterialCapacityEnvelopeVisible: Boolean(document.querySelector('[data-stage-material-capacity-envelope]')?.classList.contains('is-visible')),
      stageMaterialCapacityEnvelopeText: document.querySelector('[data-stage-material-capacity-envelope]')?.textContent || '',
      stageMaterialCapacityEnvelopeWindowState: window.__STRUCTURE_VIEWER_STAGE_MATERIAL_CAPACITY_ENVELOPE_STATE__ || null,
      stageMaterialCapacityEnvelopeOverflowCount: [...document.querySelectorAll('[data-stage-material-capacity-envelope], [data-stage-material-capacity-envelope] *, [data-stage-material-capacity-envelope-card], [data-stage-material-capacity-envelope-card] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      criticalTriage,
      criticalTriageStatus: document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-status') || '',
      criticalTriageSchema: document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-triage-schema') || '',
      criticalMembersCompactSchema: document.querySelector('[data-critical-triage]')?.getAttribute('data-critical-members-compact-table-schema') || '',
      criticalMembersCompactHeadCount: document.querySelectorAll('[data-critical-members-compact-head] span').length,
      criticalMembersCompactTableCount: document.querySelectorAll('[data-critical-members-compact-table]').length,
      criticalMembersCompactRowCount: document.querySelectorAll('[data-critical-members-compact-row]').length,
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
      criticalTriageOverflowCount: [...document.querySelectorAll('[data-critical-triage], [data-critical-triage] [data-critical-triage-row], [data-critical-triage] .critical-triage__head, [data-critical-members-compact-head]')].filter((node) => {
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
      stageStoryForceFlowStatus: document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-bands-status') || '',
      stageStoryForceFlowSchema: document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-bands-schema') || '',
      stageStoryForceFlowBandCount: Number(document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-band-count') || '0'),
      stageStoryForceFlowProjectedCount: Number(document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-projected-count') || '0'),
      stageStoryForceFlowSelectedCombination: document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-selected-combination') || '',
      stageStoryForceFlowMaxDcr: Number(document.querySelector('[data-stage-story-force-flow-bands]')?.getAttribute('data-stage-story-force-flow-max-dcr') || '0'),
      stageStoryForceFlowVisible: Boolean(document.querySelector('[data-stage-story-force-flow-bands]')?.classList.contains('is-visible')),
      stageStoryForceFlowWindowState: window.__STRUCTURE_VIEWER_STAGE_STORY_FORCE_FLOW_BANDS_STATE__ || null,
      stageStoryForceFlowText: document.querySelector('[data-stage-story-force-flow-bands]')?.textContent || '',
      stageStoryForceFlowRenderedBandCount: document.querySelectorAll('[data-stage-story-force-flow-band]').length,
      stageStoryForceFlowBarCount: document.querySelectorAll('[data-stage-story-force-flow-bands] .stage-story-force-flow-bar').length,
      stageStoryForceFlowOverflowCount: [...document.querySelectorAll('[data-stage-story-force-flow-bands], [data-stage-story-force-flow-bands] *, [data-stage-story-force-flow-band], [data-stage-story-force-flow-band] *')].filter((node) => {
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
      drawingHandoffStatus: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-status') || '',
      drawingHandoffSchema: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-schema') || '',
      drawingHandoffSheetCount: Number(document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-sheet-count') || '0'),
      drawingHandoffActiveSheet: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-active-sheet') || '',
      drawingHandoffActiveCallout: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-active-callout') || '',
      drawingHandoffSelectedMember: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-selected-member') || '',
      drawingHandoffRevision: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-revision') || '',
      drawingHandoffDeepLinkReady: document.querySelector('[data-drawing-handoff-panel]')?.getAttribute('data-drawing-handoff-deep-link-ready') || '',
      drawingHandoffReceiptRowCount: document.querySelectorAll('[data-drawing-handoff-receipt] [data-drawing-handoff-receipt-row]').length,
      drawingHandoffSheetLinkCount: document.querySelectorAll('[data-drawing-handoff-sheet]').length,
      drawingHandoffActiveSheetCount: document.querySelectorAll('[data-drawing-handoff-sheet][aria-current="true"]').length,
      drawingHandoffPreviewSheet: document.querySelector('[data-drawing-handoff-preview]')?.getAttribute('data-drawing-handoff-preview-sheet') || '',
      drawingHandoffPreviewCallout: document.querySelector('[data-drawing-handoff-preview]')?.getAttribute('data-drawing-handoff-preview-callout') || '',
      drawingHandoffOpenSheetName: document.querySelector('[data-drawing-handoff-active-sheet-open]')?.getAttribute('data-drawing-handoff-active-sheet-name') || '',
      drawingMaterialParitySchema: document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-schema') || '',
      drawingMaterialParityStatus: document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-status') || '',
      drawingMaterialParityMaterialMatchPercent: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-material-match-percent') || '0'),
      drawingMaterialParityMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-member-assignment-match-percent') || '0'),
      drawingMaterialParityMaterialMismatchCount: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-material-mismatch-count') || '0'),
      drawingMaterialParityMemberMaterialMismatchCount: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-member-material-mismatch-count') || '0'),
      drawingMaterialParitySectionAssignmentChangeCount: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-section-assignment-change-count') || '0'),
      drawingMaterialParitySheetCount: Number(document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-sheet-count') || '0'),
      drawingMaterialParityActiveSheet: document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-active-sheet') || '',
      drawingMaterialParityLocked: document.querySelector('[data-drawing-material-parity-ledger]')?.getAttribute('data-drawing-material-parity-locked') || '',
      drawingMaterialParityRowCount: document.querySelectorAll('[data-drawing-material-parity-ledger] [data-drawing-material-parity-row]').length,
      drawingMaterialParityText: document.querySelector('[data-drawing-material-parity-ledger]')?.textContent || '',
      drawingMaterialParityWindowState: window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_STATE__ || null,
      drawingMaterialParityOverflowCount: [...document.querySelectorAll('[data-drawing-material-parity-ledger], [data-drawing-material-parity-ledger] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingSourceDetailSchema: document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-schema') || '',
      drawingSourceDetailStatus: document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-status') || '',
      drawingSourceDetailActiveSheet: document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-active-sheet') || '',
      drawingSourceDetailSheetCount: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-sheet-count') || '0'),
      drawingSourceDetailSourceLinkedCount: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-source-linked-count') || '0'),
      drawingSourceDetailDetailCount: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-detail-count') || '0'),
      drawingSourceDetailMaterialLocked: document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-material-locked') || '',
      drawingSourceDetailDrawingOnlyOptimized: document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-drawing-only-optimized') || '',
      drawingSourceDetailSectionEditCount: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-section-edit-count') || '0'),
      drawingSourceDetailMaterialMatchPercent: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-material-match-percent') || '0'),
      drawingSourceDetailMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-source-detail-ledger]')?.getAttribute('data-drawing-source-detail-member-assignment-match-percent') || '0'),
      drawingSourceDetailRowCount: document.querySelectorAll('[data-drawing-source-detail-ledger] [data-drawing-source-detail-row]').length,
      drawingSourceDetailText: document.querySelector('[data-drawing-source-detail-ledger]')?.textContent || '',
      drawingSourceDetailWindowState: window.__STRUCTURE_VIEWER_DRAWING_SOURCE_DETAIL_LEDGER_STATE__ || null,
      drawingSourceDetailOverflowCount: [...document.querySelectorAll('[data-drawing-source-detail-ledger], [data-drawing-source-detail-ledger] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingSheetDetailSchema: document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-schema') || '',
      drawingSheetDetailStatus: document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-status') || '',
      drawingSheetDetailActiveSheet: document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-active-sheet') || '',
      drawingSheetDetailSheetCount: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-sheet-count') || '0'),
      drawingSheetDetailSourceLinkedCount: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-source-linked-count') || '0'),
      drawingSheetDetailMaterialLocked: document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-material-locked') || '',
      drawingSheetDetailDrawingOnlyOptimized: document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-drawing-only-optimized') || '',
      drawingSheetDetailSectionEditCount: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-section-edit-count') || '0'),
      drawingSheetDetailMaterialMatchPercent: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-material-match-percent') || '0'),
      drawingSheetDetailMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-member-assignment-match-percent') || '0'),
      drawingSheetDetailMaxDcr: Number(document.querySelector('[data-drawing-sheet-detail-matrix]')?.getAttribute('data-drawing-sheet-detail-max-dcr') || '0'),
      drawingSheetDetailRowCount: document.querySelectorAll('[data-drawing-sheet-detail-matrix] [data-drawing-sheet-detail-row]').length,
      drawingSheetDetailActiveRowCount: document.querySelectorAll('[data-drawing-sheet-detail-matrix] [data-drawing-sheet-detail-row-active="true"]').length,
      drawingSheetDetailSourceLinkedRowCount: document.querySelectorAll('[data-drawing-sheet-detail-matrix] [data-drawing-sheet-detail-row-source-linked="true"]').length,
      drawingSheetDetailText: document.querySelector('[data-drawing-sheet-detail-matrix]')?.textContent || '',
      drawingSheetDetailWindowState: window.__STRUCTURE_VIEWER_DRAWING_SHEET_DETAIL_MATRIX_STATE__ || null,
      drawingSheetDetailOverflowCount: [...document.querySelectorAll('[data-drawing-sheet-detail-matrix], [data-drawing-sheet-detail-matrix] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingMaterialModelMatrixSchema: document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-schema') || '',
      drawingMaterialModelMatrixStatus: document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-status') || '',
      drawingMaterialModelMatrixActiveSheet: document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-active-sheet') || '',
      drawingMaterialModelMatrixSelectedCombination: document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-selected-combination') || '',
      drawingMaterialModelMatrixRowCount: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-row-count') || '0'),
      drawingMaterialModelMatrixMaterialCount: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-material-count') || '0'),
      drawingMaterialModelMatrixLockedCount: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-locked-count') || '0'),
      drawingMaterialModelMatrixChangedCount: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-changed-count') || '0'),
      drawingMaterialModelMatrixForceBackedMaterialCount: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-force-backed-material-count') || '0'),
      drawingMaterialModelMatrixMaterialMatchPercent: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-material-match-percent') || '0'),
      drawingMaterialModelMatrixMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-material-model-matrix]')?.getAttribute('data-drawing-material-model-matrix-member-assignment-match-percent') || '0'),
      drawingMaterialModelMatrixRenderedRowCount: document.querySelectorAll('[data-drawing-material-model-matrix] [data-drawing-material-model-row]').length,
      drawingMaterialModelMatrixForceBackedRowCount: document.querySelectorAll('[data-drawing-material-model-matrix] [data-drawing-material-model-row-force-backed="true"]').length,
      drawingMaterialModelMatrixText: document.querySelector('[data-drawing-material-model-matrix]')?.textContent || '',
      drawingMaterialModelMatrixWindowState: window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_MODEL_MATRIX_STATE__ || null,
      drawingMaterialModelMatrixOverflowCount: [...document.querySelectorAll('[data-drawing-material-model-matrix], [data-drawing-material-model-matrix] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingMaterialConstitutiveRegisterSchema: document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-schema') || '',
      drawingMaterialConstitutiveRegisterStatus: document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-status') || '',
      drawingMaterialConstitutiveRegisterActiveSheet: document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-active-sheet') || '',
      drawingMaterialConstitutiveRegisterSelectedCombination: document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-selected-combination') || '',
      drawingMaterialConstitutiveRegisterRowCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-row-count') || '0'),
      drawingMaterialConstitutiveRegisterMaterialCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-material-count') || '0'),
      drawingMaterialConstitutiveRegisterSourceBackedCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-source-backed-count') || '0'),
      drawingMaterialConstitutiveRegisterNonlinearCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-nonlinear-count') || '0'),
      drawingMaterialConstitutiveRegisterCurveRowCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-curve-row-count') || '0'),
      drawingMaterialConstitutiveRegisterCapacityBackedMaterialCount: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-capacity-backed-material-count') || '0'),
      drawingMaterialConstitutiveRegisterMaterialLocked: document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-material-locked') || '',
      drawingMaterialConstitutiveRegisterMaterialMatchPercent: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-material-match-percent') || '0'),
      drawingMaterialConstitutiveRegisterMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-material-constitutive-register]')?.getAttribute('data-drawing-material-constitutive-register-member-assignment-match-percent') || '0'),
      drawingMaterialConstitutiveRegisterRenderedRowCount: document.querySelectorAll('[data-drawing-material-constitutive-register] [data-drawing-material-constitutive-row]').length,
      drawingMaterialConstitutiveRegisterCurveBackedRowCount: document.querySelectorAll('[data-drawing-material-constitutive-register] [data-drawing-material-constitutive-row-curve-backed="true"]').length,
      drawingMaterialConstitutiveRegisterCapacityBackedRowCount: document.querySelectorAll('[data-drawing-material-constitutive-register] [data-drawing-material-constitutive-row-capacity-backed="true"]').length,
      drawingMaterialConstitutiveRegisterText: document.querySelector('[data-drawing-material-constitutive-register]')?.textContent || '',
      drawingMaterialConstitutiveRegisterWindowState: window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_CONSTITUTIVE_REGISTER_STATE__ || null,
      drawingMaterialConstitutiveRegisterOverflowCount: [...document.querySelectorAll('[data-drawing-material-constitutive-register], [data-drawing-material-constitutive-register] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingMaterialCurveEvidenceSchema: document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-schema') || '',
      drawingMaterialCurveEvidenceStatus: document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-status') || '',
      drawingMaterialCurveEvidenceActiveSheet: document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-active-sheet') || '',
      drawingMaterialCurveEvidenceSelectedCombination: document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-selected-combination') || '',
      drawingMaterialCurveEvidenceCurveCount: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-curve-count') || '0'),
      drawingMaterialCurveEvidenceSourceBackedCount: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-source-backed-count') || '0'),
      drawingMaterialCurveEvidenceNonlinearCount: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-nonlinear-count') || '0'),
      drawingMaterialCurveEvidenceCapacityBackedCount: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-capacity-backed-count') || '0'),
      drawingMaterialCurveEvidenceMaterialLocked: document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-material-locked') || '',
      drawingMaterialCurveEvidenceMaterialMatchPercent: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-material-match-percent') || '0'),
      drawingMaterialCurveEvidenceMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-material-curve-evidence]')?.getAttribute('data-drawing-material-curve-evidence-member-assignment-match-percent') || '0'),
      drawingMaterialCurveEvidenceRenderedRowCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-row]').length,
      drawingMaterialCurveEvidenceSvgCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-svg]').length,
      drawingMaterialCurveEvidenceYieldMarkerCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-yield-marker]').length,
      drawingMaterialCurveEvidenceDemandMarkerCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-demand-marker]').length,
      drawingMaterialCurveEvidenceSourceBackedRowCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-row-source-backed="true"]').length,
      drawingMaterialCurveEvidenceCapacityBackedRowCount: document.querySelectorAll('[data-drawing-material-curve-evidence] [data-drawing-material-curve-row-capacity-backed="true"]').length,
      drawingMaterialCurveEvidenceText: document.querySelector('[data-drawing-material-curve-evidence]')?.textContent || '',
      drawingMaterialCurveEvidenceWindowState: window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_CURVE_EVIDENCE_STATE__ || null,
      drawingMaterialCurveEvidenceOverflowCount: [...document.querySelectorAll('[data-drawing-material-curve-evidence], [data-drawing-material-curve-evidence] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingForceHandoffSchema: document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-schema') || '',
      drawingForceHandoffStatus: document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-status') || '',
      drawingForceHandoffSelectedCombination: document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-selected-combination') || '',
      drawingForceHandoffSelectedMember: document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-selected-member') || '',
      drawingForceHandoffActiveSheet: document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-active-sheet') || '',
      drawingForceHandoffRowCount: Number(document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-row-count') || '0'),
      drawingForceHandoffForceRowCount: Number(document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-force-row-count') || '0'),
      drawingForceHandoffSourceBackedCount: Number(document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-source-backed-count') || '0'),
      drawingForceHandoffMaxDcr: Number(document.querySelector('[data-drawing-force-handoff-ledger]')?.getAttribute('data-drawing-force-handoff-max-dcr') || '0'),
      drawingForceHandoffText: document.querySelector('[data-drawing-force-handoff-ledger]')?.textContent || '',
      drawingForceHandoffWindowState: window.__STRUCTURE_VIEWER_DRAWING_FORCE_HANDOFF_LEDGER_STATE__ || null,
      drawingForceHandoffOverflowCount: [...document.querySelectorAll('[data-drawing-force-handoff-ledger], [data-drawing-force-handoff-ledger] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingForceVectorEvidenceSchema: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-schema') || '',
      drawingForceVectorEvidenceStatus: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-status') || '',
      drawingForceVectorEvidenceActiveSheet: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-active-sheet') || '',
      drawingForceVectorEvidenceSelectedCombination: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-selected-combination') || '',
      drawingForceVectorEvidenceSelectedMember: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-selected-member') || '',
      drawingForceVectorEvidenceRowCount: Number(document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-row-count') || '0'),
      drawingForceVectorEvidenceForceRowCount: Number(document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-force-row-count') || '0'),
      drawingForceVectorEvidenceSourceBackedCount: Number(document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-source-backed-count') || '0'),
      drawingForceVectorEvidenceMaxDcr: Number(document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-max-dcr') || '0'),
      drawingForceVectorEvidenceMaterialLocked: document.querySelector('[data-drawing-force-vector-evidence]')?.getAttribute('data-drawing-force-vector-material-locked') || '',
      drawingForceVectorEvidenceRenderedRowCount: document.querySelectorAll('[data-drawing-force-vector-evidence] [data-drawing-force-vector-row]').length,
      drawingForceVectorEvidenceSvgCount: document.querySelectorAll('[data-drawing-force-vector-evidence] [data-drawing-force-vector-svg]').length,
      drawingForceVectorEvidenceSourceBackedRowCount: document.querySelectorAll('[data-drawing-force-vector-evidence] [data-drawing-force-vector-row-source-backed="true"]').length,
      drawingForceVectorEvidenceKinds: [...document.querySelectorAll('[data-drawing-force-vector-evidence] [data-drawing-force-vector-row-vector-kind]')].map((node) => node.getAttribute('data-drawing-force-vector-row-vector-kind') || ''),
      drawingForceVectorEvidenceText: document.querySelector('[data-drawing-force-vector-evidence]')?.textContent || '',
      drawingForceVectorEvidenceWindowState: window.__STRUCTURE_VIEWER_DRAWING_FORCE_VECTOR_EVIDENCE_STATE__ || null,
      drawingForceVectorEvidenceOverflowCount: [...document.querySelectorAll('[data-drawing-force-vector-evidence], [data-drawing-force-vector-evidence] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingSheetForceOverlaySchema: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-schema') || '',
      drawingSheetForceOverlayStatus: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-status') || '',
      drawingSheetForceOverlayActiveSheet: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-active-sheet') || '',
      drawingSheetForceOverlaySelectedCombination: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-selected-combination') || '',
      drawingSheetForceOverlaySelectedMember: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-selected-member') || '',
      drawingSheetForceOverlayRowCount: Number(document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-row-count') || '0'),
      drawingSheetForceOverlayVectorCount: Number(document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-vector-count') || '0'),
      drawingSheetForceOverlayForceRowCount: Number(document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-force-row-count') || '0'),
      drawingSheetForceOverlaySourceBackedCount: Number(document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-source-backed-count') || '0'),
      drawingSheetForceOverlayMaxDcr: Number(document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-max-dcr') || '0'),
      drawingSheetForceOverlayMaterialLocked: document.querySelector('[data-drawing-sheet-force-overlay]')?.getAttribute('data-drawing-sheet-force-overlay-material-locked') || '',
      drawingSheetForceOverlayRenderedRowCount: document.querySelectorAll('[data-drawing-sheet-force-overlay] [data-drawing-sheet-force-overlay-row]').length,
      drawingSheetForceOverlaySvgCount: document.querySelectorAll('[data-drawing-sheet-force-overlay] [data-drawing-sheet-force-overlay-svg]').length,
      drawingSheetForceOverlayRenderedVectorCount: document.querySelectorAll('[data-drawing-sheet-force-overlay] [data-drawing-sheet-force-overlay-vector]').length,
      drawingSheetForceOverlayMomentCount: document.querySelectorAll('[data-drawing-sheet-force-overlay] [data-drawing-sheet-force-overlay-moment]').length,
      drawingSheetForceOverlayKinds: [...document.querySelectorAll('[data-drawing-sheet-force-overlay] [data-drawing-sheet-force-overlay-vector-kind]')].map((node) => node.getAttribute('data-drawing-sheet-force-overlay-vector-kind') || ''),
      drawingSheetForceOverlayText: document.querySelector('[data-drawing-sheet-force-overlay]')?.textContent || '',
      drawingSheetForceOverlayWindowState: window.__STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_OVERLAY_STATE__ || null,
      drawingSheetForceOverlayOverflowCount: [...document.querySelectorAll('[data-drawing-sheet-force-overlay], [data-drawing-sheet-force-overlay] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingCapacityHandoffSchema: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-schema') || '',
      drawingCapacityHandoffStatus: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-status') || '',
      drawingCapacityHandoffActiveSheet: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-active-sheet') || '',
      drawingCapacityHandoffSelectedCombination: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-selected-combination') || '',
      drawingCapacityHandoffSelectedMember: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-selected-member') || '',
      drawingCapacityHandoffSelectedSection: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-selected-section') || '',
      drawingCapacityHandoffRowCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-row-count') || '0'),
      drawingCapacityHandoffMaterialCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-material-count') || '0'),
      drawingCapacityHandoffSourceCapacityCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-source-capacity-count') || '0'),
      drawingCapacityHandoffEstimatedCapacityCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-estimated-capacity-count') || '0'),
      drawingCapacityHandoffCapacityBackedMaterialCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-capacity-backed-material-count') || '0'),
      drawingCapacityHandoffForceRowCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-force-row-count') || '0'),
      drawingCapacityHandoffMappedForceRowCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-mapped-force-row-count') || '0'),
      drawingCapacityHandoffSourceBackedCount: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-source-backed-count') || '0'),
      drawingCapacityHandoffMaxDcr: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-max-dcr') || '0'),
      drawingCapacityHandoffMinMarginPercent: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-min-margin-percent') || '0'),
      drawingCapacityHandoffMaterialLocked: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-material-locked') || '',
      drawingCapacityHandoffMaterialMatchPercent: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-material-match-percent') || '0'),
      drawingCapacityHandoffMemberAssignmentMatchPercent: Number(document.querySelector('[data-drawing-capacity-handoff-ledger]')?.getAttribute('data-drawing-capacity-handoff-member-assignment-match-percent') || '0'),
      drawingCapacityHandoffRenderedRowCount: document.querySelectorAll('[data-drawing-capacity-handoff-ledger] [data-drawing-capacity-handoff-row]').length,
      drawingCapacityHandoffSourceCapacityRowCount: document.querySelectorAll('[data-drawing-capacity-handoff-ledger] [data-drawing-capacity-handoff-row-source-capacity-count]').length,
      drawingCapacityHandoffEstimatedCapacityRowCount: document.querySelectorAll('[data-drawing-capacity-handoff-ledger] [data-drawing-capacity-handoff-row-estimated-capacity-count]').length,
      drawingCapacityHandoffText: document.querySelector('[data-drawing-capacity-handoff-ledger]')?.textContent || '',
      drawingCapacityHandoffWindowState: window.__STRUCTURE_VIEWER_DRAWING_CAPACITY_HANDOFF_LEDGER_STATE__ || null,
      drawingCapacityHandoffOverflowCount: [...document.querySelectorAll('[data-drawing-capacity-handoff-ledger], [data-drawing-capacity-handoff-ledger] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingSheetForceMatrixSchema: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-schema') || '',
      drawingSheetForceMatrixStatus: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-status') || '',
      drawingSheetForceMatrixActiveSheet: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-active-sheet') || '',
      drawingSheetForceMatrixSheetCount: Number(document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-sheet-count') || '0'),
      drawingSheetForceMatrixSelectedCombination: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-selected-combination') || '',
      drawingSheetForceMatrixSelectedMember: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-selected-member') || '',
      drawingSheetForceMatrixSourceBackedCount: Number(document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-source-backed-count') || '0'),
      drawingSheetForceMatrixForceRowCount: Number(document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-force-row-count') || '0'),
      drawingSheetForceMatrixMaxDcr: Number(document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-max-dcr') || '0'),
      drawingSheetForceMatrixMaterialLocked: document.querySelector('[data-drawing-sheet-force-matrix]')?.getAttribute('data-drawing-sheet-force-matrix-material-locked') || '',
      drawingSheetForceMatrixRowCount: document.querySelectorAll('[data-drawing-sheet-force-matrix] [data-drawing-sheet-force-row]').length,
      drawingSheetForceMatrixActiveRowCount: document.querySelectorAll('[data-drawing-sheet-force-matrix] [data-drawing-sheet-force-row-active="true"]').length,
      drawingSheetForceMatrixText: document.querySelector('[data-drawing-sheet-force-matrix]')?.textContent || '',
      drawingSheetForceMatrixWindowState: window.__STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_MATRIX_STATE__ || null,
      drawingSheetForceMatrixOverflowCount: [...document.querySelectorAll('[data-drawing-sheet-force-matrix], [data-drawing-sheet-force-matrix] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      drawingHandoffReceiptOverflowCount: [...document.querySelectorAll('[data-drawing-handoff-panel], [data-drawing-handoff-receipt] [data-drawing-handoff-receipt-row], [data-drawing-handoff-receipt] strong, [data-drawing-handoff-receipt] em, [data-drawing-handoff-sheet], [data-drawing-handoff-preview]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialCatalogStatus: document.querySelector('[data-material-member-catalog]')?.getAttribute('data-material-catalog-status') || '',
      materialCoverageStatus: document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-coverage-status') || '',
      materialCoverageSchema: document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-coverage-schema') || '',
      materialCoverageScore: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-coverage-score') || '0'),
      materialCoverageReviewQueueCount: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-review-queue-count') || '0'),
      materialCoverageSourceCount: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-source-count') || '0'),
      materialCoverageInferredCount: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-inferred-count') || '0'),
      materialCoverageMissingDefinitionCount: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-missing-definition-count') || '0'),
      materialCoverageUnclassifiedCount: Number(document.querySelector('[data-material-coverage-readiness]')?.getAttribute('data-material-unclassified-count') || '0'),
      materialCoverageCheckCount: document.querySelectorAll('[data-material-coverage-readiness] [data-material-coverage-check]').length,
      materialCoveragePassCheckCount: document.querySelectorAll('[data-material-coverage-readiness] [data-material-coverage-check-status="pass"]').length,
      materialCoverageQueueEmptyCount: document.querySelectorAll('[data-material-coverage-readiness] [data-material-review-queue-empty]').length,
      materialModelParityStatus: document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-status') || '',
      materialModelParitySchema: document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-schema') || '',
      materialModelParityMaterialCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-material-count') || '0'),
      materialModelParityReferenceMaterialCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-reference-material-count') || '0'),
      materialModelParityMaterialMismatchCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-material-mismatch-count') || '0'),
      materialModelParityMemberAssignmentCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-member-assignment-count') || '0'),
      materialModelParityMemberMaterialMismatchCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-member-material-mismatch-count') || '0'),
      materialModelParitySectionAssignmentChangeCount: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-section-assignment-change-count') || '0'),
      materialModelParityMaterialMatchPercent: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-material-match-percent') || '0'),
      materialModelParityMemberAssignmentMatchPercent: Number(document.querySelector('[data-material-model-parity]')?.getAttribute('data-material-model-parity-member-assignment-match-percent') || '0'),
      materialModelParityRowCount: document.querySelectorAll('[data-material-model-parity] [data-material-model-parity-row]').length,
      materialModelParityWindowState: window.__STRUCTURE_VIEWER_MATERIAL_MODEL_PARITY_STATE__ || null,
      materialModelParityText: document.querySelector('[data-material-model-parity]')?.textContent || '',
      materialModelParityOverflowCount: [...document.querySelectorAll('[data-material-model-parity], [data-material-model-parity] [data-material-model-parity-row], [data-material-model-parity] [data-material-model-parity-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialModelSignatureStatus: document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-status') || '',
      materialModelSignatureSchema: document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-schema') || '',
      materialModelSignatureRowCount: Number(document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-row-count') || '0'),
      materialModelSignatureMaterialCount: Number(document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-material-count') || '0'),
      materialModelSignatureLockedCount: Number(document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-locked-count') || '0'),
      materialModelSignatureChangedCount: Number(document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-changed-count') || '0'),
      materialModelSignatureRawTokenCount: Number(document.querySelector('[data-material-model-signature-ledger]')?.getAttribute('data-material-model-signature-ledger-raw-token-count') || '0'),
      materialModelSignatureRenderedRowCount: document.querySelectorAll('[data-material-model-signature-ledger] [data-material-model-signature-row]').length,
      materialModelSignatureWindowState: window.__STRUCTURE_VIEWER_MATERIAL_MODEL_SIGNATURE_LEDGER_STATE__ || null,
      materialModelSignatureText: document.querySelector('[data-material-model-signature-ledger]')?.textContent || '',
      materialModelSignatureOverflowCount: [...document.querySelectorAll('[data-material-model-signature-ledger], [data-material-model-signature-ledger] [data-material-model-signature-row], [data-material-model-signature-ledger] [data-material-model-signature-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialModelDemandAtlasStatus: document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-status') || '',
      materialModelDemandAtlasSchema: document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-schema') || '',
      materialModelDemandAtlasRowCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-row-count') || '0'),
      materialModelDemandAtlasMaterialCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-material-count') || '0'),
      materialModelDemandAtlasForceBackedMaterialCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-force-backed-material-count') || '0'),
      materialModelDemandAtlasForceRowCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-force-row-count') || '0'),
      materialModelDemandAtlasMappedForceRowCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-mapped-force-row-count') || '0'),
      materialModelDemandAtlasSourceBackedCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-source-backed-count') || '0'),
      materialModelDemandAtlasSelectedCombination: document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-selected-combination') || '',
      materialModelDemandAtlasMaxDcr: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-max-dcr') || '0'),
      materialModelDemandAtlasLockedCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-locked-count') || '0'),
      materialModelDemandAtlasChangedCount: Number(document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-changed-count') || '0'),
      materialModelDemandAtlasLockStatus: document.querySelector('[data-material-model-demand-atlas]')?.getAttribute('data-material-model-demand-atlas-lock-status') || '',
      materialModelDemandAtlasRenderedRowCount: document.querySelectorAll('[data-material-model-demand-atlas] [data-material-model-demand-row]').length,
      materialModelDemandAtlasForceBackedRowCount: document.querySelectorAll('[data-material-model-demand-atlas] [data-material-model-force-backed="true"]').length,
      materialModelDemandAtlasBarCount: document.querySelectorAll('[data-material-model-demand-atlas] .material-model-demand-row__bar').length,
      materialModelDemandAtlasWindowState: window.__STRUCTURE_VIEWER_MATERIAL_MODEL_DEMAND_ATLAS_STATE__ || null,
      materialModelDemandAtlasText: document.querySelector('[data-material-model-demand-atlas]')?.textContent || '',
      materialModelDemandAtlasOverflowCount: [...document.querySelectorAll('[data-material-model-demand-atlas], [data-material-model-demand-atlas] [data-material-model-demand-row], [data-material-model-demand-atlas] [data-material-model-demand-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialModelForceEnvelopeStatus: document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-status') || '',
      materialModelForceEnvelopeSchema: document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-schema') || '',
      materialModelForceEnvelopeRowCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-row-count') || '0'),
      materialModelForceEnvelopeMaterialCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-material-count') || '0'),
      materialModelForceEnvelopeCombinationCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-combination-count') || '0'),
      materialModelForceEnvelopeForceRowCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-force-row-count') || '0'),
      materialModelForceEnvelopeMappedForceRowCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-mapped-force-row-count') || '0'),
      materialModelForceEnvelopeSourceBackedCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-source-backed-count') || '0'),
      materialModelForceEnvelopeForceBackedMaterialCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-force-backed-material-count') || '0'),
      materialModelForceEnvelopeSelectedCombination: document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-selected-combination') || '',
      materialModelForceEnvelopeGoverningMaterial: document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-governing-material') || '',
      materialModelForceEnvelopeLockedCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-locked-count') || '0'),
      materialModelForceEnvelopeChangedCount: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-changed-count') || '0'),
      materialModelForceEnvelopeLockStatus: document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-lock-status') || '',
      materialModelForceEnvelopeMaterialMatchPercent: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-material-match-percent') || '0'),
      materialModelForceEnvelopeMemberAssignmentMatchPercent: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-member-assignment-match-percent') || '0'),
      materialModelForceEnvelopeMaxDcr: Number(document.querySelector('[data-material-model-force-envelope]')?.getAttribute('data-material-model-force-envelope-max-dcr') || '0'),
      materialModelForceEnvelopeRenderedRowCount: document.querySelectorAll('[data-material-model-force-envelope] [data-material-model-force-envelope-row]').length,
      materialModelForceEnvelopeForceBackedRowCount: document.querySelectorAll('[data-material-model-force-envelope] [data-material-model-force-envelope-row-force-backed="true"]').length,
      materialModelForceEnvelopeSvgCount: document.querySelectorAll('[data-material-model-force-envelope] [data-material-model-force-envelope-svg]').length,
      materialModelForceEnvelopePointCount: document.querySelectorAll('[data-material-model-force-envelope] [data-material-model-force-envelope-point]').length,
      materialModelForceEnvelopeBarCount: document.querySelectorAll('[data-material-model-force-envelope] .material-model-force-envelope-row__bar').length,
      materialModelForceEnvelopeWindowState: window.__STRUCTURE_VIEWER_MATERIAL_MODEL_FORCE_ENVELOPE_STATE__ || null,
      materialModelForceEnvelopeText: document.querySelector('[data-material-model-force-envelope]')?.textContent || '',
      materialModelForceEnvelopeOverflowCount: [...document.querySelectorAll('[data-material-model-force-envelope], [data-material-model-force-envelope] [data-material-model-force-envelope-row], [data-material-model-force-envelope] [data-material-model-force-envelope-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialModelCapacityEnvelopeStatus: document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-status') || '',
      materialModelCapacityEnvelopeSchema: document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-schema') || '',
      materialModelCapacityEnvelopeRowCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-row-count') || '0'),
      materialModelCapacityEnvelopeMaterialCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-material-count') || '0'),
      materialModelCapacityEnvelopeCombinationCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-combination-count') || '0'),
      materialModelCapacityEnvelopeForceRowCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-force-row-count') || '0'),
      materialModelCapacityEnvelopeMappedForceRowCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-mapped-force-row-count') || '0'),
      materialModelCapacityEnvelopeSourceBackedCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-source-backed-count') || '0'),
      materialModelCapacityEnvelopeSourceCapacityCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-source-capacity-count') || '0'),
      materialModelCapacityEnvelopeEstimatedCapacityCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-estimated-capacity-count') || '0'),
      materialModelCapacityEnvelopeCapacityBackedMaterialCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-capacity-backed-material-count') || '0'),
      materialModelCapacityEnvelopeSelectedCombination: document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-selected-combination') || '',
      materialModelCapacityEnvelopeGoverningMaterial: document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-governing-material') || '',
      materialModelCapacityEnvelopeLockedCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-locked-count') || '0'),
      materialModelCapacityEnvelopeChangedCount: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-changed-count') || '0'),
      materialModelCapacityEnvelopeLockStatus: document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-lock-status') || '',
      materialModelCapacityEnvelopeMaterialMatchPercent: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-material-match-percent') || '0'),
      materialModelCapacityEnvelopeMemberAssignmentMatchPercent: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-member-assignment-match-percent') || '0'),
      materialModelCapacityEnvelopeMaxDcr: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-max-dcr') || '0'),
      materialModelCapacityEnvelopeMinMarginPercent: Number(document.querySelector('[data-material-model-capacity-envelope]')?.getAttribute('data-material-model-capacity-envelope-min-margin-percent') || '0'),
      materialModelCapacityEnvelopeRenderedRowCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row]').length,
      materialModelCapacityEnvelopeCapacityBackedRowCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row-capacity-backed="true"]').length,
      materialModelCapacityEnvelopeSourceCapacityRowCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row-source-capacity]').length,
      materialModelCapacityEnvelopeEstimatedCapacityRowCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row-estimated-capacity]').length,
      materialModelCapacityEnvelopeSvgCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-svg]').length,
      materialModelCapacityEnvelopePointCount: document.querySelectorAll('[data-material-model-capacity-envelope] [data-material-model-capacity-envelope-point]').length,
      materialModelCapacityEnvelopeBarCount: document.querySelectorAll('[data-material-model-capacity-envelope] .material-model-capacity-envelope-row__bar').length,
      materialModelCapacityEnvelopeWindowState: window.__STRUCTURE_VIEWER_MATERIAL_MODEL_CAPACITY_ENVELOPE_STATE__ || null,
      materialModelCapacityEnvelopeText: document.querySelector('[data-material-model-capacity-envelope]')?.textContent || '',
      materialModelCapacityEnvelopeOverflowCount: [...document.querySelectorAll('[data-material-model-capacity-envelope], [data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row], [data-material-model-capacity-envelope] [data-material-model-capacity-envelope-row] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialForceInteractionStatus: document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-status') || '',
      materialForceInteractionSchema: document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-schema') || '',
      materialForceInteractionRowCount: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-row-count') || '0'),
      materialForceInteractionForceRowCount: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-force-row-count') || '0'),
      materialForceInteractionMappedForceRowCount: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-mapped-force-row-count') || '0'),
      materialForceInteractionSourceBackedCount: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-source-backed-count') || '0'),
      materialForceInteractionUnmatchedForceRowCount: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-unmatched-force-row-count') || '0'),
      materialForceInteractionSelectedCombination: document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-selected-combination') || '',
      materialForceInteractionGoverningMaterial: document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-governing-material') || '',
      materialForceInteractionMaxDcr: Number(document.querySelector('[data-material-force-interaction]')?.getAttribute('data-material-force-interaction-max-dcr') || '0'),
      materialForceInteractionRenderedRowCount: document.querySelectorAll('[data-material-force-interaction] [data-material-force-row]').length,
      materialForceInteractionBarCount: document.querySelectorAll('[data-material-force-interaction] .material-force-row__bar').length,
      materialForceInteractionWindowState: window.__STRUCTURE_VIEWER_MATERIAL_FORCE_INTERACTION_STATE__ || null,
      materialForceInteractionText: document.querySelector('[data-material-force-interaction]')?.textContent || '',
      materialForceInteractionOverflowCount: [...document.querySelectorAll('[data-material-force-interaction], [data-material-force-interaction] [data-material-force-row], [data-material-force-interaction] [data-material-force-interaction-summary] span')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialConstitutiveStatus: document.querySelector('[data-material-constitutive-lens]')?.getAttribute('data-material-constitutive-status') || '',
      materialConstitutiveSchema: document.querySelector('[data-material-constitutive-lens]')?.getAttribute('data-material-constitutive-schema') || '',
      materialConstitutiveRowCount: Number(document.querySelector('[data-material-constitutive-lens]')?.getAttribute('data-material-constitutive-row-count') || '0'),
      materialConstitutiveNonlinearCount: Number(document.querySelector('[data-material-constitutive-lens]')?.getAttribute('data-material-constitutive-nonlinear-count') || '0'),
      materialConstitutiveSourceBackedCount: Number(document.querySelector('[data-material-constitutive-lens]')?.getAttribute('data-material-constitutive-source-backed-count') || '0'),
      materialConstitutiveRenderedRowCount: document.querySelectorAll('[data-material-constitutive-lens] [data-material-constitutive-row]').length,
      materialConstitutiveHasSteelModel: (document.querySelector('[data-material-constitutive-lens]')?.textContent || '').includes('Steel bilinear'),
      materialConstitutiveHasConcreteModel: (document.querySelector('[data-material-constitutive-lens]')?.textContent || '').includes('Concrete damage-plasticity'),
      materialConstitutiveHasCompositeModel: (document.querySelector('[data-material-constitutive-lens]')?.textContent || '').includes('Composite steel-concrete interaction'),
      materialConstitutiveHasRigidModel: (document.querySelector('[data-material-constitutive-lens]')?.textContent || '').includes('Rigid link constraint'),
      materialStressStrainStatus: document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-curves-status') || '',
      materialStressStrainSchema: document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-curves-schema') || '',
      materialStressStrainCurveCount: Number(document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-curve-count') || '0'),
      materialStressStrainRenderedCurveCount: document.querySelectorAll('[data-material-stress-strain-curve-row]').length,
      materialStressStrainSvgCount: document.querySelectorAll('[data-material-stress-strain-svg]').length,
      materialStressStrainSourceBackedCount: Number(document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-source-backed-count') || '0'),
      materialStressStrainNonlinearCount: Number(document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-nonlinear-count') || '0'),
      materialStressStrainMaxDemandRatio: Number(document.querySelector('[data-material-stress-strain-curves]')?.getAttribute('data-material-stress-strain-max-demand-ratio') || '0'),
      materialStressStrainDemandMarkerCount: document.querySelectorAll('[data-material-stress-strain-curves] .material-stress-strain-row__demand').length,
      materialStressStrainYieldMarkerCount: document.querySelectorAll('[data-material-stress-strain-curves] .material-stress-strain-row__yield').length,
      materialStressStrainWindowState: window.__STRUCTURE_VIEWER_MATERIAL_STRESS_STRAIN_CURVES_STATE__ || null,
      materialStressStrainText: document.querySelector('[data-material-stress-strain-curves]')?.textContent || '',
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
      materialCoverageOverflowCount: [...document.querySelectorAll('[data-material-coverage-readiness], [data-material-coverage-readiness] [data-material-coverage-check], [data-material-coverage-readiness] .material-coverage-readiness__headline, [data-material-coverage-readiness] [data-material-review-queue]')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      materialStressStrainOverflowCount: [...document.querySelectorAll('[data-material-stress-strain-curves], [data-material-stress-strain-curves] [data-material-stress-strain-curve-row], [data-material-stress-strain-curves] .material-stress-strain-curves__head')].filter((node) => {
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
      lowerChartEvidenceSchemaCount: document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-evidence-schema="structure-viewer-lower-chart-evidence.v1"]').length,
      lowerChartReadyCount: document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-evidence-status="ready"]').length,
      lowerChartAxisReceiptCount: document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-axis-receipt]').length,
      lowerChartAxisReceiptSchemaCount: document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-axis-receipt][data-lower-chart-schema="structure-viewer-lower-chart-evidence.v1"]').length,
      lowerChartSharedScaleCount: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-scale-mode]')]
        .filter((node) => (node.getAttribute('data-lower-chart-scale-mode') || '').includes('shared')).length,
      lowerChartSvgSharedScaleCount: document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-svg][data-lower-chart-shared-scale="true"]').length,
      lowerChartKindText: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-kind]')]
        .map((node) => node.getAttribute('data-lower-chart-kind') || '').join(' '),
      lowerChartAxisText: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-axis-receipt]')]
        .map((node) => `${node.getAttribute('data-lower-chart-x-axis') || ''} ${node.getAttribute('data-lower-chart-y-axis') || ''} ${node.getAttribute('data-lower-chart-unit') || ''}`).join(' '),
      lowerChartPeakCount: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-peak]')]
        .filter((node) => (node.getAttribute('data-lower-chart-peak') || '').trim()).length,
      lowerChartActiveCount: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-active]')]
        .filter((node) => (node.getAttribute('data-lower-chart-active') || '').trim()).length,
      lowerChartReceiptOverflowCount: [...document.querySelectorAll('#analysis-cockpit-chart-strip [data-lower-chart-axis-receipt], #analysis-cockpit-chart-strip [data-lower-chart-axis-receipt] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
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
      stageResultCalloutsStatus: document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callouts-status') || '',
      stageResultCalloutsSchema: document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callouts-schema') || '',
      stageResultCalloutCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-count') || '0'),
      stageResultCalloutSourceCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-source-count') || '0'),
      stageResultCalloutEstimateCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-estimate-count') || '0'),
      stageResultCalloutLoadCase: document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-load-case') || '',
      stageResultCalloutStep: document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-step') || '',
      stageResultCalloutEvidenceCount: document.querySelectorAll('[data-stage-result-callout-evidence]').length,
      stageResultCalloutFullLabelCount: document.querySelectorAll('[data-stage-result-callout-full-label]').length,
      stageResultCalloutFullValueCount: document.querySelectorAll('[data-stage-result-callout-full-value]').length,
      stageResultCalloutSourceTypeCount: document.querySelectorAll('[data-stage-result-callout-source-type]').length,
      stageResultCalloutMemberCount: document.querySelectorAll('[data-stage-result-callout-member]').length,
      stageResultCalloutProjectionCount: document.querySelectorAll('[data-stage-result-callout-projection]').length,
      stageResultCalloutAnchorKindCount: document.querySelectorAll('[data-stage-result-callout-anchor-kind]').length,
      stageResultCalloutAnchorLabelCount: document.querySelectorAll('[data-stage-result-callout-anchor-label]').length,
      stageResultCalloutAnchorCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-anchor-count') || '0'),
      stageResultCalloutProjectedCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-projected-count') || '0'),
      stageResultCalloutSemanticCount: Number(document.querySelector('[data-stage-result-callouts]')?.getAttribute('data-stage-result-callout-semantic-count') || '0'),
      stageResultCalloutAnchorLayerStatus: document.querySelector('[data-stage-result-callout-anchors]')?.getAttribute('data-stage-result-callout-anchor-status') || '',
      stageResultCalloutAnchorLayerSchema: document.querySelector('[data-stage-result-callout-anchors]')?.getAttribute('data-stage-result-callout-anchor-schema') || '',
      stageResultCalloutAnchorLayerCount: Number(document.querySelector('[data-stage-result-callout-anchors]')?.getAttribute('data-stage-result-callout-anchor-count') || '0'),
      stageResultCalloutAnchorLayerProjectedCount: Number(document.querySelector('[data-stage-result-callout-anchors]')?.getAttribute('data-stage-result-callout-anchor-projected-count') || '0'),
      stageResultCalloutAnchorLayerSemanticCount: Number(document.querySelector('[data-stage-result-callout-anchors]')?.getAttribute('data-stage-result-callout-anchor-semantic-count') || '0'),
      stageResultCalloutAnchorNodeCount: document.querySelectorAll('[data-stage-result-callout-anchor]').length,
      stageResultCalloutAnchorKindText: [...document.querySelectorAll('[data-stage-result-callout-anchor-kind], [data-stage-result-callout-anchor]')].map((node) => node.getAttribute('data-stage-result-callout-anchor-kind') || '').join(' '),
      stageResultCalloutAnchorProjectionText: [...document.querySelectorAll('[data-stage-result-callout-anchor-projection], [data-stage-result-callout-projection]')].map((node) => node.getAttribute('data-stage-result-callout-anchor-projection') || node.getAttribute('data-stage-result-callout-projection') || '').join(' '),
      stageResultCalloutWindowState: window.__STRUCTURE_VIEWER_STAGE_RESULT_CALLOUTS_STATE__ || null,
      stageResultCalloutAnchorOverflowCount: [...document.querySelectorAll('[data-stage-result-callout-anchor], [data-stage-result-callout-anchor] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
      stageResultCalloutSourceText: [...document.querySelectorAll('[data-stage-result-callout-source]')].map((node) => node.getAttribute('data-stage-result-callout-source') || '').join(' '),
      stageResultCalloutKeyText: [...document.querySelectorAll('[data-stage-result-callout-key]')].map((node) => node.getAttribute('data-stage-result-callout-key') || '').join(' '),
      stageResultCalloutOverflowCount: [...document.querySelectorAll('[data-stage-result-callout], [data-stage-result-callout] *')].filter((node) => {
        if (!(node instanceof HTMLElement)) return false
        return node.scrollWidth - node.clientWidth > 2 || node.scrollHeight - node.clientHeight > 2
      }).length,
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
  expect(layout.integratedReviewOpenerCount).toBeGreaterThanOrEqual(2)
  expect(layout.integratedReviewSchema).toBe('structure-viewer-integrated-review-navigator.v1')
  expect(layout.integratedReviewOpen).toBe('false')
  expect(layout.integratedReviewDrawingCount).toBeGreaterThanOrEqual(2)
  expect(layout.integratedReviewAllDrawingCount).toBeGreaterThanOrEqual(layout.integratedReviewDrawingCount)
  expect(layout.integratedReviewSectionCount).toBeGreaterThanOrEqual(8)
  expect(layout.integratedReviewActiveSection).toBe('loads')
  expect(layout.integratedReviewPreviewSchema).toBe('structure-viewer-integrated-review-preview.v1')
  expect(layout.integratedReviewPreviewSection).toBe('loads')
  expect(layout.integratedReviewPreviewRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.integratedReviewWindowState?.schemaVersion).toBe('structure-viewer-integrated-review-navigator.v1')
  expect(layout.integratedReviewWindowState?.previewSchemaVersion).toBe('structure-viewer-integrated-review-preview.v1')
  expect(layout.integratedReviewWindowState?.activePreviewSectionKey).toBe('loads')
  expect(layout.integratedReviewWindowState?.open).toBe(false)
  expect(layout.integratedReviewWindowState?.sectionCount).toBe(layout.integratedReviewSectionCount)
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
  expect(layout.viewerWorkflow).toBe('model')
  expect(layout.drawingsTabHref).toBe('#drawing-handoff-section')
  expect(layout.layerToggleCount).toBeGreaterThan(2)
  expect(layout.materialFamilyLayerCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialLawLayerCount).toBeGreaterThanOrEqual(1)
  expect(layout.layerGroupText).toContain('Material families')
  expect(layout.layerGroupText).toContain('Material laws')
  expect(layout.layerToggleText).toContain('Concrete')
  expect(layout.layerToggleText).toMatch(/Steel|Bilinear|damage-plasticity/)
  expect(layout.layerToggleOverflowCount).toBe(0)
  expect(layout.viewport?.width || 0).toBeGreaterThanOrEqual(540)
  expect(layout.viewport?.height || 0).toBeGreaterThanOrEqual(398)
  expect(layout.stageOverlayOcclusionBudget).toBe('dense-model-protagonist')
  expect(layout.stageDominanceBudget).toBe('dense-stage-primary')
  expect(layout.viewport?.width || 0).toBeGreaterThanOrEqual(640)
  expect(layout.stageViewportWidthRatio).toBeGreaterThanOrEqual(0.74)
  expect(layout.stageViewportAreaRatio).toBeGreaterThanOrEqual(0.72)
  expect(layout.stageOverlayBudgetNodeCount).toBeGreaterThanOrEqual(8)
  expect(layout.stageOverlayViewportOcclusionRatio).toBeLessThanOrEqual(0.40)
  expect(layout.stageOverlayCentralOcclusionRatio).toBeLessThanOrEqual(0.18)
  expect(layout.stageResultCalloutsStatus).toBe('ready')
  expect(layout.stageResultCalloutsSchema).toBe('structure-viewer-stage-result-callouts.v3')
  expect(layout.stageResultCalloutCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutSourceCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageResultCalloutEstimateCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageResultCalloutLoadCase).not.toBe('')
  expect(layout.stageResultCalloutStep).toContain('/')
  expect(layout.stageResultCalloutEvidenceCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutFullLabelCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutFullValueCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutSourceTypeCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutMemberCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageResultCalloutProjectionCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorKindCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorLabelCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutSemanticCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageResultCalloutAnchorLayerStatus).toBe('ready')
  expect(layout.stageResultCalloutAnchorLayerSchema).toBe('structure-viewer-stage-result-callouts.v3')
  expect(layout.stageResultCalloutAnchorLayerCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorLayerSemanticCount).toBeGreaterThanOrEqual(3)
  expect(layout.stageResultCalloutAnchorNodeCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorKindText).toContain('roof-displacement')
  expect(layout.stageResultCalloutAnchorKindText).toContain('governing-drift-story')
  expect(layout.stageResultCalloutAnchorKindText).toContain('base-reaction')
  expect(layout.stageResultCalloutAnchorKindText).toContain('critical-member')
  expect(layout.stageResultCalloutAnchorProjectionText).toContain('semantic')
  expect(layout.stageResultCalloutWindowState?.schemaVersion).toBe('structure-viewer-stage-result-callouts.v3')
  expect(layout.stageResultCalloutWindowState?.calloutCount || 0).toBeGreaterThanOrEqual(4)
  expect(layout.stageResultCalloutAnchorOverflowCount).toBe(0)
  expect(layout.stageResultCalloutSourceText).toContain('Model')
  expect(layout.stageResultCalloutKeyText).toContain('max-displacement')
  expect(layout.stageResultCalloutKeyText).toContain('max-drift')
  expect(layout.stageResultCalloutKeyText).toContain('base-shear')
  expect(layout.stageResultCalloutKeyText).toContain('critical-member')
  expect(layout.stageResultCalloutOverflowCount).toBe(0)
  expect(layout.rightPanel?.width || 0).toBeGreaterThanOrEqual(360)
  expect(layout.toolRail?.width || 0).toBeGreaterThanOrEqual(30)
  expect(layout.toolRailGroupCount).toBeGreaterThanOrEqual(3)
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
  expect(layout.stageModelStack?.width || 0).toBeGreaterThan(120)
  expect(layout.stageReviewModelSchema).toBe('structure-viewer-stage-model-stack.v1')
  expect(layout.stageReviewModelStatus).toBe('ready')
  expect(layout.stageReviewModelRowCount).toBe(3)
  expect(layout.stageReviewModelSwatchCount).toBe(3)
  expect(layout.stageReviewOptimizedLayerStatus).toBe('visible')
  expect(layout.stageReviewOriginalLayerStatus).toBe('off')
  expect(layout.stageReviewDeformedLayerStatus).toBe('ready')
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
  expect(layout.kpiChipCount).toBeGreaterThanOrEqual(24)
  expect(layout.kpiChipFullLabelCount).toBe(layout.kpiChipCount)
  expect(layout.kpiChipShortLabelCount).toBe(layout.kpiChipCount)
  expect(layout.kpiChipText).toContain('Model est.')
  expect(layout.kpiChipOverflowCount).toBe(0)
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
  expect(layout.analysisTimelineFooterStatus).toBe('ready')
  expect(layout.analysisTimelineFooterSchema).toBe('structure-viewer-analysis-timeline-footer.v1')
  expect(layout.analysisTimelineFooterActiveStep).toBe(layout.resultStepScheduleActiveStep)
  expect(layout.analysisTimelineFooterTotalSteps).toBe(layout.resultStepScheduleTotal)
  expect(layout.analysisTimelineFooterTickCount).toBeGreaterThanOrEqual(5)
  expect(layout.analysisTimelineFooterActiveTickCount).toBe(1)
  expect(layout.analysisTimelineFooterSolvedTickCount).toBeGreaterThanOrEqual(1)
  expect(layout.analysisTimelineFooterLoadCase).toBe(layout.resultStepScheduleLoadCase)
  expect(layout.analysisTimelineFooterSolver).toBe(layout.resultStepScheduleSolver)
  expect(layout.analysisTimelineFooterConvergence).toBe(layout.resultStepScheduleConvergence)
  expect(layout.analysisTimelineFooterWindowState?.schemaVersion).toBe('structure-viewer-analysis-timeline-footer.v1')
  expect(layout.analysisTimelineFooterWindowState?.status).toBe('ready')
  expect(layout.analysisTimelineFooterWindowState?.tickCount).toBe(layout.analysisTimelineFooterTickCount)
  expect(layout.analysisTimelineFooterOverflowCount).toBe(0)
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
  expect(['ready', 'estimate']).toContain(layout.forceFlowStatus)
  expect(layout.forceFlowSchema).toBe('structure-viewer-force-flow-lens.v1')
  expect(layout.forceFlowRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.forceFlowRenderedRowCount).toBe(layout.forceFlowRowCount)
  expect(layout.forceFlowMemberRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.forceFlowBaseReaction).toBeGreaterThan(0)
  expect(layout.forceFlowGoverningMember).not.toBe('')
  expect(layout.forceFlowLoadCase).not.toBe('')
  expect(layout.forceFlowSelectedCombination).not.toBe('')
  expect(layout.forceFlowActiveStep).toBeGreaterThan(0)
  expect(layout.forceFlowTotalSteps).toBeGreaterThanOrEqual(layout.forceFlowActiveStep)
  expect(layout.forceFlowWindowState?.schemaVersion).toBe('structure-viewer-force-flow-lens.v1')
  expect(layout.forceFlowWindowState?.rowCount).toBe(layout.forceFlowRowCount)
  expect(layout.forceFlowOverflowCount).toBe(0)
  expect(layout.storyForceFlowStatus).toBe('ready')
  expect(layout.storyForceFlowSchema).toBe('structure-viewer-story-force-flow-ledger.v1')
  expect(layout.storyForceFlowRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.storyForceFlowRenderedRowCount).toBe(layout.storyForceFlowRowCount)
  expect(layout.storyForceFlowStoryCount).toBeGreaterThanOrEqual(layout.storyForceFlowRowCount)
  expect(layout.storyForceFlowForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.storyForceFlowSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.storyForceFlowSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.storyForceFlowGoverningStory).not.toBe('')
  expect(layout.storyForceFlowMaxDcr).toBeGreaterThan(0)
  expect(layout.storyForceFlowBarCount).toBeGreaterThanOrEqual(layout.storyForceFlowRowCount * 3)
  expect(layout.storyForceFlowText).toContain('Story Force Ledger')
  expect(layout.storyForceFlowText).toContain('source rows')
  expect(layout.storyForceFlowWindowState?.schemaVersion).toBe('structure-viewer-story-force-flow-ledger.v1')
  expect(layout.storyForceFlowWindowState?.rowCount).toBe(layout.storyForceFlowRowCount)
  expect(layout.storyForceFlowWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.storyForceFlowOverflowCount).toBe(0)
  expect(layout.loadCombinationForceStatus).toBe('ready')
  expect(layout.loadCombinationForceSchema).toBe('structure-viewer-load-combination-force-matrix.v1')
  expect(layout.loadCombinationForceRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.loadCombinationForceRenderedRowCount).toBe(layout.loadCombinationForceRowCount)
  expect(layout.loadCombinationForceCombinationCount).toBeGreaterThanOrEqual(8)
  expect(layout.loadCombinationForceForceRowCount).toBeGreaterThanOrEqual(40)
  expect(layout.loadCombinationForceSourceBackedCount).toBe(layout.loadCombinationForceForceRowCount)
  expect(layout.loadCombinationForceMaxDcr).toBeGreaterThan(0.8)
  expect(layout.loadCombinationForceGoverningCombination).not.toBe('')
  expect(layout.loadCombinationForceGoverningMember).not.toBe('')
  expect(layout.loadCombinationForceStepperSchema).toBe('structure-viewer-load-combination-force-stepper.v1')
  expect(layout.loadCombinationForceStepperCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCombinationForceStepButtonCount).toBeGreaterThanOrEqual(2)
  expect(layout.loadCombinationForceActiveStepCount).toBe(1)
  expect(layout.loadCombinationForceActiveRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.loadCombinationForceSelectedCombination).not.toBe('')
  expect(layout.loadCombinationForceSelectedMember).not.toBe('')
  expect(layout.loadCombinationForceSelectedDcr).toBeGreaterThan(0)
  expect(layout.forceFlowSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.loadCombinationForceMemberRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.loadCombinationForceWindowState?.schemaVersion).toBe('structure-viewer-load-combination-force-matrix.v1')
  expect(layout.loadCombinationForceWindowState?.stepperSchemaVersion).toBe('structure-viewer-load-combination-force-stepper.v1')
  expect(layout.loadCombinationForceWindowState?.rowCount).toBe(layout.loadCombinationForceRowCount)
  expect(layout.loadCombinationForceWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.loadCombinationForceOverflowCount).toBe(0)
  expect(layout.memberForceDiagramStatus).toBe('ready')
  expect(layout.memberForceDiagramSchema).toBe('structure-viewer-member-force-diagram.v1')
  expect(layout.memberForceDiagramRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceDiagramRenderedRowCount).toBe(layout.memberForceDiagramRowCount)
  expect(layout.memberForceDiagramDiagramCount).toBe(layout.memberForceDiagramRowCount)
  expect(layout.memberForceDiagramSvgCount).toBe(layout.memberForceDiagramRowCount)
  expect(layout.memberForceDiagramKindCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceDiagramSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceDiagramMaxDcr).toBeGreaterThan(0)
  expect(layout.memberForceDiagramSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceDiagramSelectedMember).not.toBe('')
  expect(layout.memberForceDiagramText).toContain('Member Force Diagram')
  expect(layout.memberForceDiagramText).toContain('D/C')
  expect(layout.memberForceDiagramWindowState?.schemaVersion).toBe('structure-viewer-member-force-diagram.v1')
  expect(layout.memberForceDiagramWindowState?.rowCount).toBe(layout.memberForceDiagramRowCount)
  expect(layout.memberForceDiagramWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceDiagramOverflowCount).toBe(0)
  expect(layout.memberForceEnvelopeStatus).toBe('ready')
  expect(layout.memberForceEnvelopeSchema).toBe('structure-viewer-member-force-envelope.v1')
  expect(layout.memberForceEnvelopeRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceEnvelopeRenderedRowCount).toBe(layout.memberForceEnvelopeRowCount)
  expect(layout.memberForceEnvelopeSvgCount).toBe(layout.memberForceEnvelopeRowCount)
  expect(layout.memberForceEnvelopeSampleCount).toBeGreaterThanOrEqual(2)
  expect(layout.memberForceEnvelopePointCount).toBeGreaterThanOrEqual(layout.memberForceEnvelopeSampleCount)
  expect(layout.memberForceEnvelopeSelectedPointCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceEnvelopeSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceEnvelopeMaxDcr).toBeGreaterThan(0)
  expect(layout.memberForceEnvelopeSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceEnvelopeSelectedMember).not.toBe('')
  expect(layout.memberForceEnvelopeGoverningCombination).not.toBe('')
  expect(layout.memberForceEnvelopeText).toContain('Member Force Envelope')
  expect(layout.memberForceEnvelopeText).toContain('selected / max D/C')
  expect(layout.memberForceEnvelopeWindowState?.schemaVersion).toBe('structure-viewer-member-force-envelope.v1')
  expect(layout.memberForceEnvelopeWindowState?.rowCount).toBe(layout.memberForceEnvelopeRowCount)
  expect(layout.memberForceEnvelopeWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceEnvelopeOverflowCount).toBe(0)
  expect(layout.memberForceHistoryStatus).toBe('ready')
  expect(layout.memberForceHistorySchema).toBe('structure-viewer-member-force-history.v1')
  expect(layout.memberForceHistoryRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceHistoryRenderedRowCount).toBe(layout.memberForceHistoryRowCount)
  expect(layout.memberForceHistorySvgCount).toBe(layout.memberForceHistoryRowCount)
  expect(layout.memberForceHistorySampleCount).toBeGreaterThanOrEqual(2)
  expect(layout.memberForceHistoryPointCount).toBeGreaterThanOrEqual(layout.memberForceHistorySampleCount)
  expect(layout.memberForceHistorySelectedPointCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceHistorySourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForceHistoryMaxDcr).toBeGreaterThan(0)
  expect(layout.memberForceHistorySelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceHistorySelectedMember).toBe(layout.memberForceEnvelopeSelectedMember)
  expect(layout.memberForceHistoryGoverningCombination).not.toBe('')
  expect(layout.memberForceHistoryText).toContain('Member Force History')
  expect(layout.memberForceHistoryText).toContain('current / max D/C')
  expect(layout.memberForceHistoryWindowState?.schemaVersion).toBe('structure-viewer-member-force-history.v1')
  expect(layout.memberForceHistoryWindowState?.rowCount).toBe(layout.memberForceHistoryRowCount)
  expect(layout.memberForceHistoryWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForceHistoryOverflowCount).toBe(0)
  expect(layout.memberMaterialNonlinearStatus).toBe('ready')
  expect(layout.memberMaterialNonlinearSchema).toBe('structure-viewer-member-material-nonlinear-state.v1')
  expect(layout.memberMaterialNonlinearRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberMaterialNonlinearSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberMaterialNonlinearSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberMaterialNonlinearSelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.memberMaterialNonlinearGoverningCombination).not.toBe('')
  expect(layout.memberMaterialNonlinearMaterialId).not.toBe('')
  expect(layout.memberMaterialNonlinearSectionId).not.toBe('')
  expect(layout.memberMaterialNonlinearDemandRatio).toBeGreaterThan(0)
  expect(layout.memberMaterialNonlinearState).not.toBe('')
  expect(layout.memberMaterialNonlinearRenderedRowCount).toBe(1)
  expect(layout.memberMaterialNonlinearSvgCount).toBe(1)
  expect(layout.memberMaterialNonlinearDemandMarkerCount).toBe(1)
  expect(layout.memberMaterialNonlinearYieldMarkerCount).toBe(1)
  expect(layout.memberMaterialNonlinearForceRowCount).toBe(layout.memberMaterialNonlinearRowCount)
  expect(layout.memberMaterialNonlinearText).toContain('Member Material State')
  expect(layout.memberMaterialNonlinearText).toContain('fy/fc')
  expect(layout.memberMaterialNonlinearWindowState?.schemaVersion).toBe('structure-viewer-member-material-nonlinear-state.v1')
  expect(layout.memberMaterialNonlinearWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberMaterialNonlinearWindowState?.selectedMemberId).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.memberMaterialNonlinearWindowState?.rowCount).toBe(layout.memberMaterialNonlinearRowCount)
  expect(layout.memberMaterialNonlinearOverflowCount).toBe(0)
  expect(layout.memberSectionCapacityStatus).toBe('ready')
  expect(layout.memberSectionCapacitySchema).toBe('structure-viewer-member-section-capacity.v1')
  expect(layout.memberSectionCapacityRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberSectionCapacityRenderedRowCount).toBe(layout.memberSectionCapacityRowCount)
  expect(layout.memberSectionCapacitySelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberSectionCapacitySelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.memberSectionCapacityMaterialId).toBe(layout.memberMaterialNonlinearMaterialId)
  expect(layout.memberSectionCapacitySectionId).toBe(layout.memberMaterialNonlinearSectionId)
  expect(layout.memberSectionCapacitySourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberSectionCapacitySourceCapacityCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberSectionCapacityEvidenceCount).toBeGreaterThanOrEqual(layout.memberSectionCapacityRowCount)
  expect(layout.memberSectionCapacityMaxDcr).toBeGreaterThan(0)
  expect(layout.memberSectionCapacityGeometryReady).toBe('true')
  expect(layout.memberSectionCapacityBarCount).toBeGreaterThanOrEqual(layout.memberSectionCapacityRowCount * 2)
  expect(layout.memberSectionCapacityText).toContain('Section Capacity Check')
  expect(layout.memberSectionCapacityText).toContain('KDS source capacity')
  expect(layout.memberSectionCapacityWindowState?.schemaVersion).toBe('structure-viewer-member-section-capacity.v1')
  expect(layout.memberSectionCapacityWindowState?.rowCount).toBe(layout.memberSectionCapacityRowCount)
  expect(layout.memberSectionCapacityWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberSectionCapacityWindowState?.sectionId).toBe(layout.memberMaterialNonlinearSectionId)
  expect(layout.memberSectionCapacityWindowState?.capacityEvidenceCount).toBe(layout.memberSectionCapacityEvidenceCount)
  expect(layout.memberSectionCapacityOverflowCount).toBe(0)
  expect(layout.memberForcePlaybackStatus).toBe('ready')
  expect(layout.memberForcePlaybackSchema).toBe('structure-viewer-member-force-playback.v1')
  expect(layout.memberForcePlaybackFrameCount).toBeGreaterThanOrEqual(2)
  expect(layout.memberForcePlaybackRenderedFrameCount).toBeGreaterThanOrEqual(2)
  expect(layout.memberForcePlaybackRenderedFrameCount).toBeLessThanOrEqual(layout.memberForcePlaybackFrameCount)
  expect(layout.memberForcePlaybackActionCount).toBeGreaterThanOrEqual(3)
  expect(layout.memberForcePlaybackActiveButtonCount).toBe(1)
  expect(layout.memberForcePlaybackActiveFrame).toBeGreaterThanOrEqual(0)
  expect(layout.memberForcePlaybackActiveCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForcePlaybackSelectedMember).not.toBe('')
  expect(layout.memberForcePlaybackMaxDcr).toBeGreaterThan(0)
  expect(layout.memberForcePlaybackSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.memberForcePlaybackPlaying).toBe('false')
  expect(layout.memberForcePlaybackText).toContain('Member Force Playback')
  expect(layout.memberForcePlaybackText).toContain('frames')
  expect(layout.memberForcePlaybackWindowState?.schemaVersion).toBe('structure-viewer-member-force-playback.v1')
  expect(layout.memberForcePlaybackWindowState?.frameCount).toBe(layout.memberForcePlaybackFrameCount)
  expect(layout.memberForcePlaybackWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.memberForcePlaybackOverflowCount).toBe(0)
  expect(layout.stageMemberForcePlaybackTrailStatus).toBe('ready')
  expect(layout.stageMemberForcePlaybackTrailSchema).toBe('structure-viewer-stage-member-force-playback-trail.v1')
  expect(layout.stageMemberForcePlaybackTrailFrameCount).toBe(layout.memberForcePlaybackFrameCount)
  expect(layout.stageMemberForcePlaybackTrailRenderedFrameCount).toBeGreaterThanOrEqual(2)
  expect(layout.stageMemberForcePlaybackTrailFrameButtonCount).toBe(layout.stageMemberForcePlaybackTrailRenderedFrameCount)
  expect(layout.stageMemberForcePlaybackTrailActiveFrame).toBe(layout.memberForcePlaybackActiveFrame)
  expect(layout.stageMemberForcePlaybackTrailActiveFrameCount).toBe(1)
  expect(layout.stageMemberForcePlaybackTrailProjectionCount).toBe(layout.stageMemberForcePlaybackTrailFrameButtonCount)
  expect(layout.stageMemberForcePlaybackTrailVisible).toBe(true)
  expect(layout.stageMemberForcePlaybackTrailActiveCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberForcePlaybackTrailSelectedMember).toBe(layout.memberForcePlaybackSelectedMember)
  expect(layout.stageMemberForcePlaybackTrailMaxDcr).toBeGreaterThan(0)
  expect(layout.stageMemberForcePlaybackTrailText).toContain('D/C')
  expect(layout.stageMemberForcePlaybackTrailWindowState?.schemaVersion).toBe('structure-viewer-stage-member-force-playback-trail.v1')
  expect(layout.stageMemberForcePlaybackTrailWindowState?.frameCount).toBe(layout.memberForcePlaybackFrameCount)
  expect(layout.stageMemberForcePlaybackTrailWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberForcePlaybackTrailOverlapFocus).toBe(0)
  expect(layout.stageMemberForcePlaybackTrailOverflowCount).toBe(0)
  expect(layout.stageMemberForceVectorFieldStatus).toBe('ready')
  expect(layout.stageMemberForceVectorFieldSchema).toBe('structure-viewer-stage-member-force-vector-field.v1')
  expect(layout.stageMemberForceVectorCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMemberForceVectorButtonCount).toBe(layout.stageMemberForceVectorCount)
  expect(layout.stageMemberForceVectorProjectionCount).toBe(layout.stageMemberForceVectorCount)
  expect(layout.stageMemberForceVectorSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMemberForceVectorActiveFrame).toBe(layout.memberForcePlaybackActiveFrame)
  expect(layout.stageMemberForceVectorActiveCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberForceVectorSelectedMember).toBe(layout.memberForcePlaybackSelectedMember)
  expect(layout.stageMemberForceVectorMaxDcr).toBeGreaterThan(0)
  expect(layout.stageMemberForceVectorKindText).not.toBe('')
  expect(layout.stageMemberForceVectorVisible).toBe(true)
  expect(layout.stageMemberForceVectorText).toContain('D/C')
  expect(layout.stageMemberForceVectorWindowState?.schemaVersion).toBe('structure-viewer-stage-member-force-vector-field.v1')
  expect(layout.stageMemberForceVectorWindowState?.vectorCount).toBe(layout.stageMemberForceVectorCount)
  expect(layout.stageMemberForceVectorWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberForceVectorOverlapFocus).toBe(0)
  expect(layout.stageMemberForceVectorOverflowCount).toBe(0)
  expect(layout.stageMemberMaterialStateBadgeStatus).toBe('ready')
  expect(layout.stageMemberMaterialStateBadgeSchema).toBe('structure-viewer-stage-member-material-state-badge.v1')
  expect(layout.stageMemberMaterialStateCardCount).toBe(1)
  expect(layout.stageMemberMaterialStateProjectionCount).toBe(1)
  expect(layout.stageMemberMaterialStateVisible).toBe(true)
  expect(layout.stageMemberMaterialStateCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberMaterialStateMember).toBe(layout.memberMaterialNonlinearSelectedMember)
  expect(layout.stageMemberMaterialStateMaterialId).toBe(layout.memberMaterialNonlinearMaterialId)
  expect(layout.stageMemberMaterialStateSectionId).toBe(layout.memberMaterialNonlinearSectionId)
  expect(layout.stageMemberMaterialStateDemandRatio).toBeGreaterThan(0)
  expect(layout.stageMemberMaterialStateMaxDcr).toBeGreaterThan(0)
  expect(layout.stageMemberMaterialStateSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMemberMaterialStateText).toContain('Material State')
  expect(layout.stageMemberMaterialStateText).toContain('D/C')
  expect(layout.stageMemberMaterialStateWindowState?.schemaVersion).toBe('structure-viewer-stage-member-material-state-badge.v1')
  expect(layout.stageMemberMaterialStateWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMemberMaterialStateWindowState?.materialId).toBe(layout.memberMaterialNonlinearMaterialId)
  expect(layout.stageMemberMaterialStateOverlapFocus).toBe(0)
  expect(layout.stageMemberMaterialStateOverflowCount).toBe(0)
  expect(layout.stageLoadCombinationForceGlyphsStatus).toBe('ready')
  expect(layout.stageLoadCombinationForceGlyphsSchema).toBe('structure-viewer-stage-load-combination-force-glyphs.v1')
  expect(layout.stageLoadCombinationForceGlyphCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageLoadCombinationForceMemberCount).toBe(layout.stageLoadCombinationForceGlyphCount)
  expect(layout.stageLoadCombinationForceProjectionCount).toBe(layout.stageLoadCombinationForceGlyphCount)
  expect(layout.stageLoadCombinationForceVisible).toBe(true)
  expect(layout.stageLoadCombinationForceSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageLoadCombinationForceSelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.stageLoadCombinationForceMaxDcr).toBeGreaterThan(0)
  expect(layout.stageLoadCombinationForceText).toContain(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageLoadCombinationForceText).toContain('D/C')
  expect(layout.stageLoadCombinationForceWindowState?.schemaVersion).toBe('structure-viewer-stage-load-combination-force-glyphs.v1')
  expect(layout.stageLoadCombinationForceWindowState?.glyphCount).toBe(layout.stageLoadCombinationForceGlyphCount)
  expect(layout.stageLoadCombinationForceWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageLoadCombinationForceOverlapFocus).toBe(0)
  expect(layout.stageLoadCombinationForceOverflowCount).toBe(0)
  expect(layout.stageForceDemandContourStatus).toBe('ready')
  expect(layout.stageForceDemandContourSchema).toBe('structure-viewer-stage-force-demand-contour.v1')
  expect(layout.stageForceDemandContourCount).toBeGreaterThanOrEqual(4)
  expect(layout.stageForceDemandContourMarkerCount).toBe(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourRenderedCount).toBe(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourProjectionCount).toBe(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourProjectedCount).toBeGreaterThan(0)
  expect(layout.stageForceDemandContourSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageForceDemandContourForceRowCount).toBeGreaterThanOrEqual(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourSourceBackedCount).toBeGreaterThanOrEqual(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourMappedForceRowCount).toBeGreaterThanOrEqual(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourMaxDcr).toBeGreaterThan(0)
  expect(layout.stageForceDemandContourMaterialLockStatus).toBe('locked')
  expect(layout.stageForceDemandContourMaterialModelCount).toBeGreaterThanOrEqual(6)
  expect(layout.stageForceDemandContourMaterialModelText).not.toBe('')
  expect(layout.stageForceDemandContourVisible).toBe(true)
  expect(layout.stageForceDemandContourText).toContain('Force Demand Contour')
  expect(layout.stageForceDemandContourText).toContain('D/C')
  expect(layout.stageForceDemandContourWindowState?.schemaVersion).toBe('structure-viewer-stage-force-demand-contour.v1')
  expect(layout.stageForceDemandContourWindowState?.status).toBe('ready')
  expect(layout.stageForceDemandContourWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageForceDemandContourWindowState?.contourCount).toBe(layout.stageForceDemandContourCount)
  expect(layout.stageForceDemandContourOverflowCount).toBe(0)
  expect(layout.stageMaterialModelDemandBadgesStatus).toBe('ready')
  expect(layout.stageMaterialModelDemandBadgesSchema).toBe('structure-viewer-stage-material-model-demand-badges.v1')
  expect(layout.stageMaterialModelDemandBadgesCount).toBeGreaterThanOrEqual(6)
  expect(layout.stageMaterialModelDemandBadgesBadgeCount).toBe(layout.stageMaterialModelDemandBadgesCount)
  expect(layout.stageMaterialModelDemandBadgesRenderedCount).toBe(layout.stageMaterialModelDemandBadgesCount)
  expect(layout.stageMaterialModelDemandBadgesProjectionCount).toBe(layout.stageMaterialModelDemandBadgesCount)
  expect(layout.stageMaterialModelDemandBadgesProjectedCount + layout.stageMaterialModelDemandBadgesEdgePinnedCount).toBeGreaterThan(0)
  expect(layout.stageMaterialModelDemandBadgesSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialModelDemandBadgesMaterialCount).toBeGreaterThanOrEqual(layout.stageMaterialModelDemandBadgesCount)
  expect(layout.stageMaterialModelDemandBadgesForceBackedMaterialCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMaterialModelDemandBadgesForceBackedBadgeCount).toBe(layout.stageMaterialModelDemandBadgesForceBackedMaterialCount)
  expect(layout.stageMaterialModelDemandBadgesForceRowCount).toBeGreaterThanOrEqual(layout.stageMaterialModelDemandBadgesForceBackedMaterialCount)
  expect(layout.stageMaterialModelDemandBadgesMappedForceRowCount).toBeGreaterThanOrEqual(layout.stageMaterialModelDemandBadgesForceBackedMaterialCount)
  expect(layout.stageMaterialModelDemandBadgesSourceBackedCount).toBeGreaterThanOrEqual(layout.stageMaterialModelDemandBadgesForceBackedMaterialCount)
  expect(layout.stageMaterialModelDemandBadgesMaxDcr).toBeGreaterThan(0)
  expect(layout.stageMaterialModelDemandBadgesLockStatus).toBe('locked')
  expect(layout.stageMaterialModelDemandBadgesLockedCount).toBe(layout.stageMaterialModelDemandBadgesCount)
  expect(layout.stageMaterialModelDemandBadgesChangedCount).toBe(0)
  expect(layout.stageMaterialModelDemandBadgesVisible).toBe(true)
  expect(layout.stageMaterialModelDemandBadgesText).toContain('Material Demand')
  expect(layout.stageMaterialModelDemandBadgesText).toContain('D/C')
  expect(layout.stageMaterialModelDemandBadgesWindowState?.schemaVersion).toBe('structure-viewer-stage-material-model-demand-badges.v1')
  expect(layout.stageMaterialModelDemandBadgesWindowState?.status).toBe('ready')
  expect(layout.stageMaterialModelDemandBadgesWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialModelDemandBadgesWindowState?.rowCount).toBe(layout.stageMaterialModelDemandBadgesCount)
  expect((layout.stageMaterialModelDemandBadgesWindowState?.projectedCount || 0) + (layout.stageMaterialModelDemandBadgesWindowState?.edgePinnedCount || 0)).toBeGreaterThan(0)
  expect(layout.stageMaterialModelDemandBadgesOverflowCount).toBe(0)
  expect(layout.stageMaterialForceRibbonsStatus).toBe('ready')
  expect(layout.stageMaterialForceRibbonsSchema).toBe('structure-viewer-stage-material-force-ribbons.v1')
  expect(layout.stageMaterialForceRibbonCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMaterialForceRibbonButtonCount).toBe(layout.stageMaterialForceRibbonCount)
  expect(layout.stageMaterialForceRenderedCount).toBe(layout.stageMaterialForceRibbonCount)
  expect(layout.stageMaterialForceProjectionCount).toBe(layout.stageMaterialForceRibbonCount)
  expect(layout.stageMaterialForceProjectedCount + layout.stageMaterialForceEdgePinnedCount).toBeGreaterThan(0)
  expect(layout.stageMaterialForceSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialForceMaterialCount).toBe(layout.stageMaterialForceRibbonCount)
  expect(layout.stageMaterialForceForceRowCount).toBeGreaterThanOrEqual(layout.stageMaterialForceSourceBackedCount)
  expect(layout.stageMaterialForceMappedForceRowCount).toBeGreaterThanOrEqual(layout.stageMaterialForceSourceBackedCount)
  expect(layout.stageMaterialForceSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMaterialForceGoverningMaterial).not.toBe('')
  expect(layout.stageMaterialForceMaxDcr).toBeGreaterThan(0)
  expect(layout.stageMaterialForceBarCount).toBe(layout.stageMaterialForceRibbonCount * 3)
  expect(layout.stageMaterialForceVisible).toBe(true)
  expect(layout.stageMaterialForceText).toContain('Material Forces')
  expect(layout.stageMaterialForceText).toContain('D/C')
  expect(layout.stageMaterialForceWindowState?.schemaVersion).toBe('structure-viewer-stage-material-force-ribbons.v1')
  expect(layout.stageMaterialForceWindowState?.status).toBe('ready')
  expect(layout.stageMaterialForceWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialForceWindowState?.rowCount).toBe(layout.stageMaterialForceRibbonCount)
  expect((layout.stageMaterialForceWindowState?.projectedCount || 0) + (layout.stageMaterialForceWindowState?.edgePinnedCount || 0)).toBeGreaterThan(0)
  expect(layout.stageMaterialForceOverflowCount).toBe(0)
  expect(layout.stageMaterialForceEnvelopeStatus).toBe('ready')
  expect(layout.stageMaterialForceEnvelopeSchema).toBe('structure-viewer-stage-material-force-envelope.v1')
  expect(layout.stageMaterialForceEnvelopeCardCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMaterialForceEnvelopeButtonCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopeRenderedCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopeProjectionCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopeProjectedCount + layout.stageMaterialForceEnvelopeEdgePinnedCount).toBeGreaterThan(0)
  expect(layout.stageMaterialForceEnvelopeSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialForceEnvelopeSourceRowCount).toBe(layout.materialModelForceEnvelopeRowCount)
  expect(layout.stageMaterialForceEnvelopeMaterialCount).toBe(layout.materialModelForceEnvelopeMaterialCount)
  expect(layout.stageMaterialForceEnvelopeCombinationCount).toBe(layout.materialModelForceEnvelopeCombinationCount)
  expect(layout.stageMaterialForceEnvelopeForceBackedMaterialCount).toBe(layout.materialModelForceEnvelopeForceBackedMaterialCount)
  expect(layout.stageMaterialForceEnvelopeForceBackedCardCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopeForceRowCount).toBe(layout.materialModelForceEnvelopeForceRowCount)
  expect(layout.stageMaterialForceEnvelopeMappedForceRowCount).toBe(layout.materialModelForceEnvelopeMappedForceRowCount)
  expect(layout.stageMaterialForceEnvelopeSourceBackedCount).toBe(layout.materialModelForceEnvelopeSourceBackedCount)
  expect(layout.stageMaterialForceEnvelopeGoverningMaterial).toBe(layout.materialModelForceEnvelopeGoverningMaterial)
  expect(layout.stageMaterialForceEnvelopeLockedCount).toBe(layout.materialModelForceEnvelopeLockedCount)
  expect(layout.stageMaterialForceEnvelopeChangedCount).toBe(0)
  expect(layout.stageMaterialForceEnvelopeLockStatus).toBe('locked')
  expect(layout.stageMaterialForceEnvelopeMaterialMatchPercent).toBe(100)
  expect(layout.stageMaterialForceEnvelopeMemberAssignmentMatchPercent).toBe(100)
  expect(layout.stageMaterialForceEnvelopeMaxDcr).toBe(layout.materialModelForceEnvelopeMaxDcr)
  expect(layout.stageMaterialForceEnvelopeSvgCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopePointCount).toBeGreaterThanOrEqual(layout.stageMaterialForceEnvelopeCardCount * 2)
  expect(layout.stageMaterialForceEnvelopeBarCount).toBe(layout.stageMaterialForceEnvelopeCardCount * 3)
  expect(layout.stageMaterialForceEnvelopeVisible).toBe(true)
  expect(layout.stageMaterialForceEnvelopeText).toContain('Material Envelope')
  expect(layout.stageMaterialForceEnvelopeText).toContain('combos')
  expect(layout.stageMaterialForceEnvelopeText).toContain('D/C')
  expect(layout.stageMaterialForceEnvelopeWindowState?.schemaVersion).toBe('structure-viewer-stage-material-force-envelope.v1')
  expect(layout.stageMaterialForceEnvelopeWindowState?.status).toBe('ready')
  expect(layout.stageMaterialForceEnvelopeWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialForceEnvelopeWindowState?.rowCount).toBe(layout.stageMaterialForceEnvelopeCardCount)
  expect(layout.stageMaterialForceEnvelopeWindowState?.materialMatchPercent).toBe(100)
  expect(layout.stageMaterialForceEnvelopeWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect((layout.stageMaterialForceEnvelopeWindowState?.projectedCount || 0) + (layout.stageMaterialForceEnvelopeWindowState?.edgePinnedCount || 0)).toBeGreaterThan(0)
  expect(layout.stageMaterialForceEnvelopeOverflowCount).toBe(0)
  expect(layout.stageMaterialCapacityEnvelopeStatus).toBe('ready')
  expect(layout.stageMaterialCapacityEnvelopeSchema).toBe('structure-viewer-stage-material-capacity-envelope.v1')
  expect(layout.stageMaterialCapacityEnvelopeCardCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageMaterialCapacityEnvelopeButtonCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeRenderedCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeProjectionCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeProjectedCount + layout.stageMaterialCapacityEnvelopeEdgePinnedCount).toBeGreaterThan(0)
  expect(layout.stageMaterialCapacityEnvelopeSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialCapacityEnvelopeSourceRowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.stageMaterialCapacityEnvelopeMaterialCount).toBe(layout.materialModelCapacityEnvelopeMaterialCount)
  expect(layout.stageMaterialCapacityEnvelopeCombinationCount).toBe(layout.materialModelCapacityEnvelopeCombinationCount)
  expect(layout.stageMaterialCapacityEnvelopeForceRowCount).toBe(layout.materialModelCapacityEnvelopeForceRowCount)
  expect(layout.stageMaterialCapacityEnvelopeMappedForceRowCount).toBe(layout.materialModelCapacityEnvelopeMappedForceRowCount)
  expect(layout.stageMaterialCapacityEnvelopeSourceBackedCount).toBe(layout.materialModelCapacityEnvelopeSourceBackedCount)
  expect(layout.stageMaterialCapacityEnvelopeSourceCapacityCount).toBe(layout.materialModelCapacityEnvelopeSourceCapacityCount)
  expect(layout.stageMaterialCapacityEnvelopeEstimatedCapacityCount).toBe(layout.materialModelCapacityEnvelopeEstimatedCapacityCount)
  expect(layout.stageMaterialCapacityEnvelopeCapacityBackedMaterialCount).toBe(layout.materialModelCapacityEnvelopeCapacityBackedMaterialCount)
  expect(layout.stageMaterialCapacityEnvelopeCapacityBackedCardCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeSourceCapacityCardCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeEstimatedCapacityCardCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeGoverningMaterial).toBe(layout.materialModelCapacityEnvelopeGoverningMaterial)
  expect(layout.stageMaterialCapacityEnvelopeLockedCount).toBe(layout.materialModelCapacityEnvelopeLockedCount)
  expect(layout.stageMaterialCapacityEnvelopeChangedCount).toBe(0)
  expect(layout.stageMaterialCapacityEnvelopeLockStatus).toBe('locked')
  expect(layout.stageMaterialCapacityEnvelopeMaterialMatchPercent).toBe(100)
  expect(layout.stageMaterialCapacityEnvelopeMemberAssignmentMatchPercent).toBe(100)
  expect(layout.stageMaterialCapacityEnvelopeMaxDcr).toBe(layout.materialModelCapacityEnvelopeMaxDcr)
  expect(layout.stageMaterialCapacityEnvelopeMinMarginPercent).toBe(layout.materialModelCapacityEnvelopeMinMarginPercent)
  expect(layout.stageMaterialCapacityEnvelopeSvgCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopePointCount).toBeGreaterThanOrEqual(layout.stageMaterialCapacityEnvelopeCardCount * 2)
  expect(layout.stageMaterialCapacityEnvelopeBarCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount * 3)
  expect(layout.stageMaterialCapacityEnvelopeVisible).toBe(true)
  expect(layout.stageMaterialCapacityEnvelopeText).toContain('Capacity Envelope')
  expect(layout.stageMaterialCapacityEnvelopeText).toContain('margin')
  expect(layout.stageMaterialCapacityEnvelopeText).toContain('D/C')
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.schemaVersion).toBe('structure-viewer-stage-material-capacity-envelope.v1')
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.status).toBe('ready')
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.rowCount).toBe(layout.stageMaterialCapacityEnvelopeCardCount)
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.sourceCapacityCount).toBe(layout.materialModelCapacityEnvelopeSourceCapacityCount)
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.estimatedCapacityCount).toBe(layout.materialModelCapacityEnvelopeEstimatedCapacityCount)
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.materialMatchPercent).toBe(100)
  expect(layout.stageMaterialCapacityEnvelopeWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect((layout.stageMaterialCapacityEnvelopeWindowState?.projectedCount || 0) + (layout.stageMaterialCapacityEnvelopeWindowState?.edgePinnedCount || 0)).toBeGreaterThan(0)
  expect(layout.stageMaterialCapacityEnvelopeOverflowCount).toBe(0)
  expect(layout.criticalTriage?.top || 9999).toBeLessThanOrEqual((layout.rightPanel?.bottom || 0) + 1)
  expect(layout.criticalTriageStatus).toBe('ready')
  expect(layout.criticalTriageSchema).toBe('structure-viewer-critical-triage.v1')
  expect(layout.criticalMembersCompactSchema).toBe('structure-viewer-critical-members-compact-table.v1')
  expect(layout.criticalMembersCompactHeadCount).toBe(5)
  expect(layout.criticalMembersCompactTableCount).toBeGreaterThanOrEqual(2)
  expect(layout.criticalMembersCompactRowCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.criticalTriageRows).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageMemberRows).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageSourceCount).toBeGreaterThanOrEqual(layout.criticalTriageRowCount)
  expect(layout.criticalTriageHighCount).toBeGreaterThanOrEqual(1)
  expect(layout.criticalTriageMaxRatio).toBeGreaterThan(0)
  expect(layout.criticalTriageStatusCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageActionCount).toBe(layout.criticalTriageRowCount)
  expect(layout.criticalTriageText).toContain('Critical Members')
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
  expect(layout.stageStoryForceFlowStatus).toBe('ready')
  expect(layout.stageStoryForceFlowSchema).toBe('structure-viewer-stage-story-force-flow-bands.v1')
  expect(layout.stageStoryForceFlowBandCount).toBeGreaterThanOrEqual(1)
  expect(layout.stageStoryForceFlowRenderedBandCount).toBe(layout.stageStoryForceFlowBandCount)
  expect(layout.stageStoryForceFlowProjectedCount).toBeGreaterThan(0)
  expect(layout.stageStoryForceFlowSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.stageStoryForceFlowMaxDcr).toBeGreaterThan(0)
  expect(layout.stageStoryForceFlowVisible).toBe(true)
  expect(layout.stageStoryForceFlowBarCount).toBeGreaterThanOrEqual(layout.stageStoryForceFlowBandCount * 3)
  expect(layout.stageStoryForceFlowWindowState?.schemaVersion).toBe('structure-viewer-stage-story-force-flow-bands.v1')
  expect(layout.stageStoryForceFlowWindowState?.status).toBe('ready')
  expect(layout.stageStoryForceFlowWindowState?.bandCount).toBe(layout.stageStoryForceFlowBandCount)
  expect(layout.stageStoryForceFlowText).toContain('Story Forces')
  expect(layout.stageStoryForceFlowText).toContain('D/C')
  expect(layout.stageStoryForceFlowOverflowCount).toBe(0)
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
  expect(layout.drawingHandoffStatus).toBe('linked')
  expect(layout.drawingHandoffSchema).toBe('structure-viewer-drawing-handoff-panel.v2')
  expect(layout.drawingHandoffSheetCount).toBeGreaterThanOrEqual(4)
  expect(layout.drawingHandoffSheetLinkCount).toBeGreaterThanOrEqual(4)
  expect(layout.drawingHandoffActiveSheetCount).toBe(1)
  expect(layout.drawingHandoffDeepLinkReady).toBe('true')
  expect(layout.drawingHandoffReceiptRowCount).toBe(4)
  expect(layout.drawingHandoffActiveSheet).not.toBe('')
  expect(layout.drawingHandoffActiveCallout).not.toBe('')
  expect(layout.drawingHandoffSelectedMember).not.toBe('')
  expect(layout.drawingHandoffSelectedMember).not.toBe('--')
  expect(layout.drawingHandoffRevision).not.toBe('')
  expect(layout.drawingHandoffPreviewSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingHandoffPreviewCallout).toBe(layout.drawingHandoffActiveCallout)
  expect(layout.drawingHandoffOpenSheetName).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingHandoffReceiptOverflowCount).toBe(0)
  expect(layout.drawingMaterialParityStatus).toBe('ready')
  expect(layout.drawingMaterialParitySchema).toBe('structure-viewer-drawing-material-parity-ledger.v1')
  expect(layout.drawingMaterialParityMaterialMatchPercent).toBe(100)
  expect(layout.drawingMaterialParityMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialParityMaterialMismatchCount).toBe(0)
  expect(layout.drawingMaterialParityMemberMaterialMismatchCount).toBe(0)
  expect(layout.drawingMaterialParitySectionAssignmentChangeCount).toBeGreaterThan(0)
  expect(layout.drawingMaterialParitySheetCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingMaterialParityActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingMaterialParityLocked).toBe('true')
  expect(layout.drawingMaterialParityRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.drawingMaterialParityText).toContain('Drawing Material Parity')
  expect(layout.drawingMaterialParityText).toContain('section/drawing assignment only')
  expect(layout.drawingMaterialParityWindowState?.schemaVersion).toBe('structure-viewer-drawing-material-parity-ledger.v1')
  expect(layout.drawingMaterialParityWindowState?.status).toBe('ready')
  expect(layout.drawingMaterialParityWindowState?.materialMismatchCount).toBe(0)
  expect(layout.drawingMaterialParityWindowState?.memberMaterialMismatchCount).toBe(0)
  expect(layout.drawingMaterialParityWindowState?.drawingOnlyOptimized).toBe(true)
  expect(layout.drawingMaterialParityOverflowCount).toBe(0)
  expect(layout.drawingSourceDetailStatus).toBe('ready')
  expect(layout.drawingSourceDetailSchema).toBe('structure-viewer-drawing-source-detail-ledger.v1')
  expect(layout.drawingSourceDetailActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSourceDetailSheetCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingSourceDetailSourceLinkedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSourceDetailSourceLinkedCount).toBeLessThanOrEqual(layout.drawingSourceDetailSheetCount)
  expect(layout.drawingSourceDetailDetailCount).toBeGreaterThanOrEqual(5)
  expect(layout.drawingSourceDetailRowCount).toBe(layout.drawingSourceDetailDetailCount)
  expect(layout.drawingSourceDetailMaterialLocked).toBe('true')
  expect(layout.drawingSourceDetailDrawingOnlyOptimized).toBe('true')
  expect(layout.drawingSourceDetailSectionEditCount).toBeGreaterThan(0)
  expect(layout.drawingSourceDetailMaterialMatchPercent).toBe(100)
  expect(layout.drawingSourceDetailMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingSourceDetailText).toContain('Original Drawing Detail')
  expect(layout.drawingSourceDetailText).toContain('section/drawing only')
  expect(layout.drawingSourceDetailWindowState?.schemaVersion).toBe('structure-viewer-drawing-source-detail-ledger.v1')
  expect(layout.drawingSourceDetailWindowState?.status).toBe('ready')
  expect(layout.drawingSourceDetailWindowState?.activeSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSourceDetailWindowState?.materialLocked).toBe(true)
  expect(layout.drawingSourceDetailWindowState?.drawingOnlyOptimized).toBe(true)
  expect(layout.drawingSourceDetailOverflowCount).toBe(0)
  expect(layout.drawingSheetDetailStatus).toBe('ready')
  expect(layout.drawingSheetDetailSchema).toBe('structure-viewer-drawing-sheet-detail-matrix.v1')
  expect(layout.drawingSheetDetailActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSheetDetailSheetCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingSheetDetailRowCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingSheetDetailActiveRowCount).toBe(1)
  expect(layout.drawingSheetDetailSourceLinkedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSheetDetailSourceLinkedRowCount).toBe(layout.drawingSheetDetailSourceLinkedCount)
  expect(layout.drawingSheetDetailMaterialLocked).toBe('true')
  expect(layout.drawingSheetDetailDrawingOnlyOptimized).toBe('true')
  expect(layout.drawingSheetDetailSectionEditCount).toBeGreaterThan(0)
  expect(layout.drawingSheetDetailMaterialMatchPercent).toBe(100)
  expect(layout.drawingSheetDetailMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingSheetDetailMaxDcr).toBeGreaterThan(0)
  expect(layout.drawingSheetDetailText).toContain('Drawing Sheet Details')
  expect(layout.drawingSheetDetailText).toContain('source sheets')
  expect(layout.drawingSheetDetailWindowState?.schemaVersion).toBe('structure-viewer-drawing-sheet-detail-matrix.v1')
  expect(layout.drawingSheetDetailWindowState?.status).toBe('ready')
  expect(layout.drawingSheetDetailWindowState?.activeSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSheetDetailWindowState?.rows?.length).toBe(layout.drawingSheetDetailRowCount)
  expect(layout.drawingSheetDetailOverflowCount).toBe(0)
  expect(layout.drawingMaterialModelMatrixStatus).toBe('ready')
  expect(layout.drawingMaterialModelMatrixSchema).toBe('structure-viewer-drawing-material-model-matrix.v1')
  expect(layout.drawingMaterialModelMatrixActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingMaterialModelMatrixSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialModelMatrixRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.drawingMaterialModelMatrixRenderedRowCount).toBe(layout.drawingMaterialModelMatrixRowCount)
  expect(layout.drawingMaterialModelMatrixMaterialCount).toBeGreaterThanOrEqual(layout.drawingMaterialModelMatrixRowCount)
  expect(layout.drawingMaterialModelMatrixLockedCount).toBe(layout.drawingMaterialModelMatrixRowCount)
  expect(layout.drawingMaterialModelMatrixChangedCount).toBe(0)
  expect(layout.drawingMaterialModelMatrixForceBackedMaterialCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingMaterialModelMatrixForceBackedRowCount).toBe(layout.drawingMaterialModelMatrixForceBackedMaterialCount)
  expect(layout.drawingMaterialModelMatrixMaterialMatchPercent).toBe(100)
  expect(layout.drawingMaterialModelMatrixMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialModelMatrixText).toContain('Drawing Material Models')
  expect(layout.drawingMaterialModelMatrixText).toContain('100% material lock target')
  expect(layout.drawingMaterialModelMatrixWindowState?.schemaVersion).toBe('structure-viewer-drawing-material-model-matrix.v1')
  expect(layout.drawingMaterialModelMatrixWindowState?.rowCount).toBe(layout.drawingMaterialModelMatrixRowCount)
  expect(layout.drawingMaterialModelMatrixWindowState?.lockedCount).toBe(layout.drawingMaterialModelMatrixLockedCount)
  expect(layout.drawingMaterialModelMatrixWindowState?.changedCount).toBe(0)
  expect(layout.drawingMaterialModelMatrixWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialModelMatrixOverflowCount).toBe(0)
  expect(layout.drawingMaterialConstitutiveRegisterStatus).toBe('ready')
  expect(layout.drawingMaterialConstitutiveRegisterSchema).toBe('structure-viewer-drawing-material-constitutive-register.v1')
  expect(layout.drawingMaterialConstitutiveRegisterActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingMaterialConstitutiveRegisterSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialConstitutiveRegisterRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.drawingMaterialConstitutiveRegisterRenderedRowCount).toBe(layout.drawingMaterialConstitutiveRegisterRowCount)
  expect(layout.drawingMaterialConstitutiveRegisterMaterialCount).toBeGreaterThanOrEqual(layout.drawingMaterialConstitutiveRegisterRowCount)
  expect(layout.drawingMaterialConstitutiveRegisterSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingMaterialConstitutiveRegisterCurveRowCount).toBe(layout.drawingMaterialConstitutiveRegisterCurveBackedRowCount)
  expect(layout.drawingMaterialConstitutiveRegisterCapacityBackedMaterialCount).toBe(layout.drawingMaterialConstitutiveRegisterCapacityBackedRowCount)
  expect(layout.drawingMaterialConstitutiveRegisterMaterialLocked).toBe('true')
  expect(layout.drawingMaterialConstitutiveRegisterMaterialMatchPercent).toBe(100)
  expect(layout.drawingMaterialConstitutiveRegisterMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialConstitutiveRegisterText).toContain('Drawing Material Constitutive Register')
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.schemaVersion).toBe('structure-viewer-drawing-material-constitutive-register.v1')
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.rowCount).toBe(layout.drawingMaterialConstitutiveRegisterRowCount)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.materialLocked).toBe(true)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.materialMatchPercent).toBe(100)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.rows?.some((row: any) => row.model === 'Concrete damage-plasticity')).toBe(true)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.rows?.some((row: any) => row.model === 'Steel bilinear')).toBe(true)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.rows?.some((row: any) => row.model === 'Composite steel-concrete interaction')).toBe(true)
  expect(layout.drawingMaterialConstitutiveRegisterWindowState?.rows?.some((row: any) => row.model === 'Rigid link constraint')).toBe(true)
  expect(layout.drawingMaterialConstitutiveRegisterOverflowCount).toBe(0)
  expect(layout.drawingMaterialCurveEvidenceStatus).toBe('ready')
  expect(layout.drawingMaterialCurveEvidenceSchema).toBe('structure-viewer-drawing-material-curve-evidence.v1')
  expect(layout.drawingMaterialCurveEvidenceActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingMaterialCurveEvidenceSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialCurveEvidenceCurveCount).toBe(layout.drawingMaterialConstitutiveRegisterCurveRowCount)
  expect(layout.drawingMaterialCurveEvidenceRenderedRowCount).toBe(layout.drawingMaterialCurveEvidenceCurveCount)
  expect(layout.drawingMaterialCurveEvidenceSvgCount).toBe(layout.drawingMaterialCurveEvidenceCurveCount)
  expect(layout.drawingMaterialCurveEvidenceYieldMarkerCount).toBe(layout.drawingMaterialCurveEvidenceCurveCount)
  expect(layout.drawingMaterialCurveEvidenceDemandMarkerCount).toBe(layout.drawingMaterialCurveEvidenceCurveCount)
  expect(layout.drawingMaterialCurveEvidenceSourceBackedCount).toBe(layout.drawingMaterialCurveEvidenceSourceBackedRowCount)
  expect(layout.drawingMaterialCurveEvidenceCapacityBackedCount).toBe(layout.drawingMaterialCurveEvidenceCapacityBackedRowCount)
  expect(layout.drawingMaterialCurveEvidenceCurveCount).toBeGreaterThanOrEqual(4)
  expect(layout.drawingMaterialCurveEvidenceMaterialLocked).toBe('true')
  expect(layout.drawingMaterialCurveEvidenceMaterialMatchPercent).toBe(100)
  expect(layout.drawingMaterialCurveEvidenceMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialCurveEvidenceText).toContain('Drawing Material Curve Evidence')
  expect(layout.drawingMaterialCurveEvidenceWindowState?.schemaVersion).toBe('structure-viewer-drawing-material-curve-evidence.v1')
  expect(layout.drawingMaterialCurveEvidenceWindowState?.curveCount).toBe(layout.drawingMaterialCurveEvidenceCurveCount)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.materialLocked).toBe(true)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.materialMatchPercent).toBe(100)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.rows?.some((row: any) => row.model === 'Concrete damage-plasticity')).toBe(true)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.rows?.some((row: any) => row.model === 'Steel bilinear')).toBe(true)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.rows?.some((row: any) => row.model === 'Composite steel-concrete interaction')).toBe(true)
  expect(layout.drawingMaterialCurveEvidenceWindowState?.rows?.some((row: any) => row.model === 'Rigid link constraint')).toBe(true)
  expect(layout.drawingMaterialCurveEvidenceOverflowCount).toBe(0)
  expect(layout.drawingForceHandoffStatus).toBe('ready')
  expect(layout.drawingForceHandoffSchema).toBe('structure-viewer-drawing-force-handoff-ledger.v1')
  expect(layout.drawingForceHandoffSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingForceHandoffSelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingForceHandoffActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingForceHandoffRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingForceHandoffForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingForceHandoffSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingForceHandoffMaxDcr).toBeGreaterThan(0)
  expect(layout.drawingForceHandoffText).toContain('Drawing Force Handoff')
  expect(layout.drawingForceHandoffText).toContain('D/C')
  expect(layout.drawingForceHandoffWindowState?.schemaVersion).toBe('structure-viewer-drawing-force-handoff-ledger.v1')
  expect(layout.drawingForceHandoffWindowState?.status).toBe('ready')
  expect(layout.drawingForceHandoffWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingForceHandoffWindowState?.selectedMemberId).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingForceHandoffOverflowCount).toBe(0)
  expect(layout.drawingForceVectorEvidenceStatus).toBe('ready')
  expect(layout.drawingForceVectorEvidenceSchema).toBe('structure-viewer-drawing-force-vector-evidence.v1')
  expect(layout.drawingForceVectorEvidenceActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingForceVectorEvidenceSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingForceVectorEvidenceSelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingForceVectorEvidenceRowCount).toBeGreaterThanOrEqual(3)
  expect(layout.drawingForceVectorEvidenceRenderedRowCount).toBe(layout.drawingForceVectorEvidenceRowCount)
  expect(layout.drawingForceVectorEvidenceSvgCount).toBe(layout.drawingForceVectorEvidenceRowCount)
  expect(layout.drawingForceVectorEvidenceForceRowCount).toBeGreaterThanOrEqual(layout.drawingForceVectorEvidenceRowCount)
  expect(layout.drawingForceVectorEvidenceSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingForceVectorEvidenceSourceBackedRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingForceVectorEvidenceMaxDcr).toBeGreaterThan(0)
  expect(layout.drawingForceVectorEvidenceMaterialLocked).toBe('true')
  expect(layout.drawingForceVectorEvidenceText).toContain('Drawing Force Vector Evidence')
  expect(layout.drawingForceVectorEvidenceKinds).toEqual(expect.arrayContaining(['axial', 'shear', 'moment']))
  expect(layout.drawingForceVectorEvidenceWindowState?.schemaVersion).toBe('structure-viewer-drawing-force-vector-evidence.v1')
  expect(layout.drawingForceVectorEvidenceWindowState?.status).toBe('ready')
  expect(layout.drawingForceVectorEvidenceWindowState?.rowCount).toBe(layout.drawingForceVectorEvidenceRowCount)
  expect(layout.drawingForceVectorEvidenceWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingForceVectorEvidenceWindowState?.selectedMemberId).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingForceVectorEvidenceWindowState?.materialLocked).toBe(true)
  expect(layout.drawingForceVectorEvidenceOverflowCount).toBe(0)
  expect(layout.drawingSheetForceOverlayStatus).toBe('ready')
  expect(layout.drawingSheetForceOverlaySchema).toBe('structure-viewer-drawing-sheet-force-overlay.v1')
  expect(layout.drawingSheetForceOverlayActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSheetForceOverlaySelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingSheetForceOverlaySelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingSheetForceOverlayRowCount).toBe(layout.drawingForceVectorEvidenceRowCount)
  expect(layout.drawingSheetForceOverlayRenderedRowCount).toBe(layout.drawingSheetForceOverlayRowCount)
  expect(layout.drawingSheetForceOverlaySvgCount).toBe(1)
  expect(layout.drawingSheetForceOverlayRenderedVectorCount).toBe(layout.drawingSheetForceOverlayVectorCount)
  expect(layout.drawingSheetForceOverlayVectorCount).toBe(layout.drawingSheetForceOverlayRowCount)
  expect(layout.drawingSheetForceOverlayForceRowCount).toBeGreaterThanOrEqual(layout.drawingSheetForceOverlayRowCount)
  expect(layout.drawingSheetForceOverlaySourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSheetForceOverlayMaxDcr).toBeGreaterThan(0)
  expect(layout.drawingSheetForceOverlayMaterialLocked).toBe('true')
  expect(layout.drawingSheetForceOverlayText).toContain('Drawing Sheet Force Overlay')
  expect(layout.drawingSheetForceOverlayKinds).toEqual(expect.arrayContaining(['axial', 'shear', 'moment']))
  expect(layout.drawingSheetForceOverlayMomentCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSheetForceOverlayWindowState?.schemaVersion).toBe('structure-viewer-drawing-sheet-force-overlay.v1')
  expect(layout.drawingSheetForceOverlayWindowState?.status).toBe('ready')
  expect(layout.drawingSheetForceOverlayWindowState?.rowCount).toBe(layout.drawingSheetForceOverlayRowCount)
  expect(layout.drawingSheetForceOverlayWindowState?.materialLocked).toBe(true)
  expect(layout.drawingSheetForceOverlayOverflowCount).toBe(0)
  expect(layout.drawingCapacityHandoffStatus).toBe('ready')
  expect(layout.drawingCapacityHandoffSchema).toBe('structure-viewer-drawing-capacity-handoff-ledger.v1')
  expect(layout.drawingCapacityHandoffActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingCapacityHandoffSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingCapacityHandoffSelectedMember).not.toBe('')
  expect(layout.drawingCapacityHandoffSelectedSection).not.toBe('')
  expect(layout.drawingCapacityHandoffRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingCapacityHandoffRenderedRowCount).toBe(layout.drawingCapacityHandoffRowCount)
  expect(layout.drawingCapacityHandoffSourceCapacityRowCount).toBe(layout.drawingCapacityHandoffRowCount)
  expect(layout.drawingCapacityHandoffEstimatedCapacityRowCount).toBe(layout.drawingCapacityHandoffRowCount)
  expect(layout.drawingCapacityHandoffMaterialCount).toBe(layout.materialModelCapacityEnvelopeMaterialCount)
  expect(layout.drawingCapacityHandoffSourceCapacityCount).toBe(layout.materialModelCapacityEnvelopeSourceCapacityCount)
  expect(layout.drawingCapacityHandoffEstimatedCapacityCount).toBe(layout.materialModelCapacityEnvelopeEstimatedCapacityCount)
  expect(layout.drawingCapacityHandoffCapacityBackedMaterialCount).toBe(layout.materialModelCapacityEnvelopeCapacityBackedMaterialCount)
  expect(layout.drawingCapacityHandoffForceRowCount).toBe(layout.materialModelCapacityEnvelopeForceRowCount)
  expect(layout.drawingCapacityHandoffMappedForceRowCount).toBe(layout.materialModelCapacityEnvelopeMappedForceRowCount)
  expect(layout.drawingCapacityHandoffSourceBackedCount).toBe(layout.materialModelCapacityEnvelopeSourceBackedCount)
  expect(layout.drawingCapacityHandoffMaxDcr).toBe(layout.materialModelCapacityEnvelopeMaxDcr)
  expect(layout.drawingCapacityHandoffMinMarginPercent).toBe(layout.materialModelCapacityEnvelopeMinMarginPercent)
  expect(layout.drawingCapacityHandoffMaterialLocked).toBe('true')
  expect(layout.drawingCapacityHandoffMaterialMatchPercent).toBe(100)
  expect(layout.drawingCapacityHandoffMemberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingCapacityHandoffText).toContain('Drawing Capacity Handoff')
  expect(layout.drawingCapacityHandoffText).toContain('capacity')
  expect(layout.drawingCapacityHandoffText).toContain('margin')
  expect(layout.drawingCapacityHandoffWindowState?.schemaVersion).toBe('structure-viewer-drawing-capacity-handoff-ledger.v1')
  expect(layout.drawingCapacityHandoffWindowState?.status).toBe('ready')
  expect(layout.drawingCapacityHandoffWindowState?.activeSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingCapacityHandoffWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingCapacityHandoffWindowState?.rowCount).toBe(layout.drawingCapacityHandoffRowCount)
  expect(layout.drawingCapacityHandoffWindowState?.sourceCapacityCount).toBe(layout.materialModelCapacityEnvelopeSourceCapacityCount)
  expect(layout.drawingCapacityHandoffWindowState?.estimatedCapacityCount).toBe(layout.materialModelCapacityEnvelopeEstimatedCapacityCount)
  expect(layout.drawingCapacityHandoffWindowState?.materialMatchPercent).toBe(100)
  expect(layout.drawingCapacityHandoffWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect(layout.drawingCapacityHandoffOverflowCount).toBe(0)
  expect(layout.drawingSheetForceMatrixStatus).toBe('ready')
  expect(layout.drawingSheetForceMatrixSchema).toBe('structure-viewer-drawing-sheet-force-matrix.v1')
  expect(layout.drawingSheetForceMatrixActiveSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSheetForceMatrixSheetCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingSheetForceMatrixRowCount).toBe(layout.drawingHandoffSheetCount)
  expect(layout.drawingSheetForceMatrixActiveRowCount).toBe(1)
  expect(layout.drawingSheetForceMatrixSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingSheetForceMatrixSelectedMember).toBe(layout.loadCombinationForceSelectedMember)
  expect(layout.drawingSheetForceMatrixSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSheetForceMatrixForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.drawingSheetForceMatrixMaxDcr).toBeGreaterThan(0)
  expect(layout.drawingSheetForceMatrixMaterialLocked).toBe('true')
  expect(layout.drawingSheetForceMatrixText).toContain('Drawing Sheet Force Matrix')
  expect(layout.drawingSheetForceMatrixText).toContain('material locked')
  expect(layout.drawingSheetForceMatrixWindowState?.schemaVersion).toBe('structure-viewer-drawing-sheet-force-matrix.v1')
  expect(layout.drawingSheetForceMatrixWindowState?.status).toBe('ready')
  expect(layout.drawingSheetForceMatrixWindowState?.activeSheet).toBe(layout.drawingHandoffActiveSheet)
  expect(layout.drawingSheetForceMatrixWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.drawingSheetForceMatrixOverflowCount).toBe(0)
  expect(layout.materialCatalogStatus).toBe('ready')
  expect(['ready', 'needs_review']).toContain(layout.materialCoverageStatus)
  expect(layout.materialCoverageSchema).toBe('structure-viewer-material-coverage-readiness.v1')
  expect(layout.materialCoverageScore).toBeGreaterThanOrEqual(80)
  expect(layout.materialCoverageReviewQueueCount).toBeGreaterThanOrEqual(layout.materialCoverageUnclassifiedCount)
  expect(layout.materialCoverageSourceCount + layout.materialCoverageInferredCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCoverageMissingDefinitionCount).toBe(0)
  expect(layout.materialCoverageCheckCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialCoveragePassCheckCount).toBeGreaterThanOrEqual(layout.materialCoverageCheckCount - 1)
  expect(layout.materialCoverageQueueEmptyCount).toBe(layout.materialCoverageReviewQueueCount === 0 ? 1 : 0)
  expect(layout.materialModelParityStatus).toBe('ready')
  expect(layout.materialModelParitySchema).toBe('structure-viewer-material-model-parity.v1')
  expect(layout.materialModelParityMaterialCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialModelParityReferenceMaterialCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialModelParityMaterialMismatchCount).toBe(0)
  expect(layout.materialModelParityMemberAssignmentCount).toBeGreaterThanOrEqual(12000)
  expect(layout.materialModelParityMemberMaterialMismatchCount).toBe(0)
  expect(layout.materialModelParitySectionAssignmentChangeCount).toBeGreaterThan(0)
  expect(layout.materialModelParityMaterialMatchPercent).toBe(100)
  expect(layout.materialModelParityMemberAssignmentMatchPercent).toBe(100)
  expect(layout.materialModelParityRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.materialModelParityText).toContain('Material Model Lock')
  expect(layout.materialModelParityText).toContain('section/drawing edits')
  expect(layout.materialModelParityWindowState?.schemaVersion).toBe('structure-viewer-material-model-parity.v1')
  expect(layout.materialModelParityWindowState?.materialMismatchCount).toBe(0)
  expect(layout.materialModelParityWindowState?.memberMaterialMismatchCount).toBe(0)
  expect(layout.materialModelParityWindowState?.materialMatchPercent).toBe(100)
  expect(layout.materialModelParityWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect(layout.materialModelParityOverflowCount).toBe(0)
  expect(layout.materialModelSignatureStatus).toBe('ready')
  expect(layout.materialModelSignatureSchema).toBe('structure-viewer-material-model-signature-ledger.v1')
  expect(layout.materialModelSignatureMaterialCount).toBe(layout.materialModelParityMaterialCount)
  expect(layout.materialModelSignatureRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialModelSignatureRenderedRowCount).toBe(layout.materialModelSignatureRowCount)
  expect(layout.materialModelSignatureLockedCount).toBe(layout.materialModelSignatureRowCount)
  expect(layout.materialModelSignatureChangedCount).toBe(0)
  expect(layout.materialModelSignatureRawTokenCount).toBeGreaterThan(0)
  expect(layout.materialModelSignatureText).toContain('All Material Models')
  expect(layout.materialModelSignatureText).toContain('raw signature tokens')
  expect(layout.materialModelSignatureWindowState?.schemaVersion).toBe('structure-viewer-material-model-signature-ledger.v1')
  expect(layout.materialModelSignatureWindowState?.rowCount).toBe(layout.materialModelSignatureRowCount)
  expect(layout.materialModelSignatureWindowState?.lockedCount).toBe(layout.materialModelSignatureLockedCount)
  expect(layout.materialModelSignatureOverflowCount).toBe(0)
  expect(layout.materialModelDemandAtlasStatus).toBe('ready')
  expect(layout.materialModelDemandAtlasSchema).toBe('structure-viewer-material-model-demand-atlas.v1')
  expect(layout.materialModelDemandAtlasRowCount).toBeGreaterThanOrEqual(6)
  expect(layout.materialModelDemandAtlasRenderedRowCount).toBe(layout.materialModelDemandAtlasRowCount)
  expect(layout.materialModelDemandAtlasMaterialCount).toBeGreaterThanOrEqual(layout.materialModelSignatureMaterialCount)
  expect(layout.materialModelDemandAtlasLockedCount).toBe(layout.materialModelDemandAtlasRowCount)
  expect(layout.materialModelDemandAtlasChangedCount).toBe(0)
  expect(layout.materialModelDemandAtlasLockStatus).toBe('locked')
  expect(layout.materialModelDemandAtlasForceBackedMaterialCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelDemandAtlasForceBackedRowCount).toBe(layout.materialModelDemandAtlasForceBackedMaterialCount)
  expect(layout.materialModelDemandAtlasForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelDemandAtlasMappedForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelDemandAtlasSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelDemandAtlasSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelDemandAtlasMaxDcr).toBeGreaterThan(0)
  expect(layout.materialModelDemandAtlasBarCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasRowCount * 2)
  expect(layout.materialModelDemandAtlasText).toContain('Material Model Demand Atlas')
  expect(layout.materialModelDemandAtlasText).toContain('material models')
  expect(layout.materialModelDemandAtlasWindowState?.schemaVersion).toBe('structure-viewer-material-model-demand-atlas.v1')
  expect(layout.materialModelDemandAtlasWindowState?.rowCount).toBe(layout.materialModelDemandAtlasRowCount)
  expect(layout.materialModelDemandAtlasWindowState?.lockedCount).toBe(layout.materialModelDemandAtlasLockedCount)
  expect(layout.materialModelDemandAtlasWindowState?.changedCount).toBe(0)
  expect(layout.materialModelDemandAtlasWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelDemandAtlasOverflowCount).toBe(0)
  expect(layout.materialModelForceEnvelopeStatus).toBe('ready')
  expect(layout.materialModelForceEnvelopeSchema).toBe('structure-viewer-material-model-force-envelope.v1')
  expect(layout.materialModelForceEnvelopeRowCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasRowCount)
  expect(layout.materialModelForceEnvelopeRenderedRowCount).toBe(layout.materialModelForceEnvelopeRowCount)
  expect(layout.materialModelForceEnvelopeMaterialCount).toBeGreaterThanOrEqual(layout.materialModelSignatureMaterialCount)
  expect(layout.materialModelForceEnvelopeCombinationCount).toBeGreaterThanOrEqual(2)
  expect(layout.materialModelForceEnvelopeForceRowCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasForceRowCount)
  expect(layout.materialModelForceEnvelopeMappedForceRowCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasMappedForceRowCount)
  expect(layout.materialModelForceEnvelopeSourceBackedCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasSourceBackedCount)
  expect(layout.materialModelForceEnvelopeForceBackedMaterialCount).toBeGreaterThanOrEqual(layout.materialModelDemandAtlasForceBackedMaterialCount)
  expect(layout.materialModelForceEnvelopeForceBackedRowCount).toBe(layout.materialModelForceEnvelopeForceBackedMaterialCount)
  expect(layout.materialModelForceEnvelopeSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelForceEnvelopeGoverningMaterial).not.toBe('')
  expect(layout.materialModelForceEnvelopeLockedCount).toBe(layout.materialModelForceEnvelopeRowCount)
  expect(layout.materialModelForceEnvelopeChangedCount).toBe(0)
  expect(layout.materialModelForceEnvelopeLockStatus).toBe('locked')
  expect(layout.materialModelForceEnvelopeMaterialMatchPercent).toBe(100)
  expect(layout.materialModelForceEnvelopeMemberAssignmentMatchPercent).toBe(100)
  expect(layout.materialModelForceEnvelopeMaxDcr).toBeGreaterThan(0)
  expect(layout.materialModelForceEnvelopeSvgCount).toBe(layout.materialModelForceEnvelopeRowCount)
  expect(layout.materialModelForceEnvelopePointCount).toBeGreaterThanOrEqual(layout.materialModelForceEnvelopeRowCount * 2)
  expect(layout.materialModelForceEnvelopeBarCount).toBeGreaterThanOrEqual(layout.materialModelForceEnvelopeRowCount * 3)
  expect(layout.materialModelForceEnvelopeText).toContain('Material Model Force Envelope')
  expect(layout.materialModelForceEnvelopeText).toContain('all combinations')
  expect(layout.materialModelForceEnvelopeWindowState?.schemaVersion).toBe('structure-viewer-material-model-force-envelope.v1')
  expect(layout.materialModelForceEnvelopeWindowState?.rowCount).toBe(layout.materialModelForceEnvelopeRowCount)
  expect(layout.materialModelForceEnvelopeWindowState?.combinationCount).toBe(layout.materialModelForceEnvelopeCombinationCount)
  expect(layout.materialModelForceEnvelopeWindowState?.mappedForceRowCount).toBe(layout.materialModelForceEnvelopeMappedForceRowCount)
  expect(layout.materialModelForceEnvelopeWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelForceEnvelopeOverflowCount).toBe(0)
  expect(layout.materialModelCapacityEnvelopeStatus).toBe('ready')
  expect(layout.materialModelCapacityEnvelopeSchema).toBe('structure-viewer-material-model-capacity-envelope.v1')
  expect(layout.materialModelCapacityEnvelopeRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelCapacityEnvelopeRenderedRowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeMaterialCount).toBeGreaterThanOrEqual(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeCombinationCount).toBe(layout.materialModelForceEnvelopeCombinationCount)
  expect(layout.materialModelCapacityEnvelopeForceRowCount).toBe(layout.materialModelForceEnvelopeForceRowCount)
  expect(layout.materialModelCapacityEnvelopeMappedForceRowCount).toBe(layout.materialModelForceEnvelopeMappedForceRowCount)
  expect(layout.materialModelCapacityEnvelopeSourceBackedCount).toBe(layout.materialModelForceEnvelopeSourceBackedCount)
  expect(layout.materialModelCapacityEnvelopeSourceCapacityCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelCapacityEnvelopeEstimatedCapacityCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialModelCapacityEnvelopeCapacityBackedMaterialCount).toBe(layout.materialModelCapacityEnvelopeCapacityBackedRowCount)
  expect(layout.materialModelCapacityEnvelopeCapacityBackedRowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeSourceCapacityRowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeEstimatedCapacityRowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelCapacityEnvelopeGoverningMaterial).toBe(layout.materialModelForceEnvelopeGoverningMaterial)
  expect(layout.materialModelCapacityEnvelopeLockedCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeChangedCount).toBe(0)
  expect(layout.materialModelCapacityEnvelopeLockStatus).toBe('locked')
  expect(layout.materialModelCapacityEnvelopeMaterialMatchPercent).toBe(100)
  expect(layout.materialModelCapacityEnvelopeMemberAssignmentMatchPercent).toBe(100)
  expect(layout.materialModelCapacityEnvelopeMaxDcr).toBe(layout.materialModelForceEnvelopeMaxDcr)
  expect(layout.materialModelCapacityEnvelopeSvgCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopePointCount).toBeGreaterThanOrEqual(layout.materialModelCapacityEnvelopeRowCount * 2)
  expect(layout.materialModelCapacityEnvelopeBarCount).toBe(layout.materialModelCapacityEnvelopeRowCount * 3)
  expect(layout.materialModelCapacityEnvelopeText).toContain('Material Model Capacity Envelope')
  expect(layout.materialModelCapacityEnvelopeText).toContain('demand / capacity')
  expect(layout.materialModelCapacityEnvelopeText).toContain('margin')
  expect(layout.materialModelCapacityEnvelopeWindowState?.schemaVersion).toBe('structure-viewer-material-model-capacity-envelope.v1')
  expect(layout.materialModelCapacityEnvelopeWindowState?.rowCount).toBe(layout.materialModelCapacityEnvelopeRowCount)
  expect(layout.materialModelCapacityEnvelopeWindowState?.combinationCount).toBe(layout.materialModelCapacityEnvelopeCombinationCount)
  expect(layout.materialModelCapacityEnvelopeWindowState?.mappedForceRowCount).toBe(layout.materialModelCapacityEnvelopeMappedForceRowCount)
  expect(layout.materialModelCapacityEnvelopeWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialModelCapacityEnvelopeWindowState?.materialMatchPercent).toBe(100)
  expect(layout.materialModelCapacityEnvelopeWindowState?.memberAssignmentMatchPercent).toBe(100)
  expect(layout.materialModelCapacityEnvelopeOverflowCount).toBe(0)
  expect(layout.materialForceInteractionStatus).toBe('ready')
  expect(layout.materialForceInteractionSchema).toBe('structure-viewer-material-force-interaction.v1')
  expect(layout.materialForceInteractionRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialForceInteractionRenderedRowCount).toBe(layout.materialForceInteractionRowCount)
  expect(layout.materialForceInteractionForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialForceInteractionMappedForceRowCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialForceInteractionSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialForceInteractionSelectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialForceInteractionGoverningMaterial).not.toBe('')
  expect(layout.materialForceInteractionMaxDcr).toBeGreaterThan(0)
  expect(layout.materialForceInteractionBarCount).toBeGreaterThanOrEqual(layout.materialForceInteractionRowCount * 3)
  expect(layout.materialForceInteractionText).toContain('Material-Force Interaction')
  expect(layout.materialForceInteractionText).toContain('mapped force rows')
  expect(layout.materialForceInteractionWindowState?.schemaVersion).toBe('structure-viewer-material-force-interaction.v1')
  expect(layout.materialForceInteractionWindowState?.rowCount).toBe(layout.materialForceInteractionRowCount)
  expect(layout.materialForceInteractionWindowState?.mappedForceRowCount).toBe(layout.materialForceInteractionMappedForceRowCount)
  expect(layout.materialForceInteractionWindowState?.selectedCombination).toBe(layout.loadCombinationForceSelectedCombination)
  expect(layout.materialForceInteractionOverflowCount).toBe(0)
  expect(layout.materialConstitutiveStatus).toBe('ready')
  expect(layout.materialConstitutiveSchema).toBe('structure-viewer-material-constitutive-lens.v1')
  expect(layout.materialConstitutiveRowCount).toBeGreaterThanOrEqual(4)
  expect(layout.materialConstitutiveRenderedRowCount).toBe(layout.materialConstitutiveRowCount)
  expect(layout.materialConstitutiveSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialConstitutiveHasSteelModel || layout.materialConstitutiveHasConcreteModel).toBe(true)
  expect(layout.materialConstitutiveHasCompositeModel).toBe(true)
  expect(layout.materialConstitutiveHasRigidModel).toBe(true)
  expect(layout.materialStressStrainStatus).toBe('ready')
  expect(layout.materialStressStrainSchema).toBe('structure-viewer-material-stress-strain-curves.v1')
  expect(layout.materialStressStrainCurveCount).toBeGreaterThanOrEqual(4)
  expect(layout.materialStressStrainRenderedCurveCount).toBe(layout.materialStressStrainCurveCount)
  expect(layout.materialStressStrainSvgCount).toBe(layout.materialStressStrainCurveCount)
  expect(layout.materialStressStrainDemandMarkerCount).toBe(layout.materialStressStrainCurveCount)
  expect(layout.materialStressStrainYieldMarkerCount).toBe(layout.materialStressStrainCurveCount)
  expect(layout.materialStressStrainSourceBackedCount).toBeGreaterThanOrEqual(1)
  expect(layout.materialStressStrainMaxDemandRatio).toBeGreaterThanOrEqual(0)
  expect(layout.materialStressStrainText).toContain('Stress-Strain Curves')
  expect(layout.materialStressStrainText).toContain('fy/fc')
  expect(layout.materialStressStrainWindowState?.schemaVersion).toBe('structure-viewer-material-stress-strain-curves.v1')
  expect(layout.materialStressStrainWindowState?.rowCount).toBe(layout.materialStressStrainCurveCount)
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
  expect(layout.materialCoverageOverflowCount).toBe(0)
  expect(layout.materialStressStrainOverflowCount).toBe(0)
  expect(layout.optimizationCardCount).toBe(4)
  expect(layout.optimizationSourceCount).toBe(4)
  expect(layout.optimizationAfterBarCount).toBe(4)
  expect(layout.optimizationSavedCount).toBe(4)
  expect(layout.optimizationDetailsLinkCount).toBe(1)
  expect(layout.optimizationOverflowCount).toBe(0)
  expect(layout.chartCount).toBe(4)
  expect(layout.lowerChartEvidenceSchemaCount).toBe(4)
  expect(layout.lowerChartReadyCount).toBe(4)
  expect(layout.lowerChartAxisReceiptCount).toBe(4)
  expect(layout.lowerChartAxisReceiptSchemaCount).toBe(4)
  expect(layout.lowerChartSharedScaleCount).toBeGreaterThanOrEqual(4)
  expect(layout.lowerChartSvgSharedScaleCount).toBeGreaterThanOrEqual(4)
  expect(layout.lowerChartKindText).toContain('story-drift')
  expect(layout.lowerChartKindText).toContain('load-step-displacement')
  expect(layout.lowerChartKindText).toContain('material-quantity')
  expect(layout.lowerChartKindText).toContain('utilization-heatmap')
  expect(layout.lowerChartAxisText).toContain('Drift (%)')
  expect(layout.lowerChartAxisText).toContain('Height (m)')
  expect(layout.lowerChartAxisText).toContain('Displacement (mm)')
  expect(layout.lowerChartAxisText).toContain('D/C')
  expect(layout.lowerChartPeakCount).toBeGreaterThanOrEqual(3)
  expect(layout.lowerChartActiveCount).toBeGreaterThanOrEqual(3)
  expect(layout.lowerChartReceiptOverflowCount).toBe(0)
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
  await page.locator('[data-viewer-workflow-tab="drawings"]').first().click()
  const drawingWorkflow = await page.evaluate(() => {
    const readDisplay = (selector: string) => {
      const node = document.querySelector(selector)
      return node instanceof HTMLElement ? window.getComputedStyle(node).display : ''
    }
    const drawingSection = document.querySelector('#drawing-handoff-section')
    const drawingRect = drawingSection instanceof HTMLElement ? drawingSection.getBoundingClientRect() : null
    return {
      workflow: document.body.getAttribute('data-viewer-workflow') || '',
      overlayDensity: document.body.getAttribute('data-stage-overlay-density') || '',
      hash: window.location.hash,
      activeDrawingsTabCount: document.querySelectorAll('[data-viewer-workflow-tab="drawings"].is-active').length,
      stageResultDisplay: readDisplay('#stage-result-callouts'),
      stageOverlayReceiptDisplay: readDisplay('#stage-overlay-receipt'),
      loadGlyphDisplay: readDisplay('#stage-load-support-glyphs'),
      contourSectionDisplay: readDisplay('#contour-section'),
      drawingSectionTop: drawingRect?.top ?? 9999,
      drawingSectionHeight: drawingRect?.height ?? 0,
    }
  })
  expect(drawingWorkflow.workflow).toBe('drawings')
  expect(drawingWorkflow.overlayDensity).toBe('drawing-clean')
  expect(drawingWorkflow.hash).toBe('#drawing-handoff-section')
  expect(drawingWorkflow.activeDrawingsTabCount).toBeGreaterThanOrEqual(1)
  expect(drawingWorkflow.stageResultDisplay).toBe('none')
  expect(drawingWorkflow.stageOverlayReceiptDisplay).toBe('none')
  expect(drawingWorkflow.loadGlyphDisplay).toBe('none')
  expect(drawingWorkflow.contourSectionDisplay).toBe('none')
  expect(drawingWorkflow.drawingSectionHeight).toBeGreaterThan(0)
  await expectNoBrowserErrors(errors)
})

test('structure viewer keeps the mobile real drawing workflow usable', async ({ page }) => {
  test.skip(mode === 'minimal', 'minimal smoke runs only the desktop browser paths')
  const errors = await openRealDrawingViewer(page, { width: 390, height: 844 })
  await waitForCanvasNonBlank(page)
  await expect(page.locator('#stage-panel')).toBeVisible()
  await expect(page.locator('#real-drawing-quality-panel')).toContainText('RD-')
  await clickRenderMode(page, 'wireframe')
  await expectNoBrowserErrors(errors)
})

test('structure viewer keeps the mobile MIDAS33 optimized workflow usable', async ({ page }) => {
  test.skip(mode === 'minimal', 'minimal smoke runs only the desktop browser paths')
  const errors = await openMidas33OptimizedViewer(page, { width: 390, height: 844 })
  await expectCanvasReady(page)
  await clickViewPreset(page, 'plan')
  await expectRenderMode(page, 'wireframe')
  await page.locator('#member-search-input').fill('903')
  await expect(page.locator('#search-results')).toContainText('903', { timeout: 30000 })
  await expectNoBrowserErrors(errors)
})
