import { createHash } from 'node:crypto'
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  assertCanvasWellFramed,
  installCanvasFrameProbe,
  waitForCanvasNonBlank,
} from './structure-viewer-canvas-frame.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const schemaVersion = 'structure-viewer-visual-regression-baseline.v1'
const defaultBaseline = 'implementation/phase1/structure_viewer_visual_regression_baseline.json'

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.ts': 'text/plain; charset=utf-8',
}

const defaultCases = [
  {
    id: 'desktop_midas33_optimized',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'wireframe',
    workflowState: 'optimized_wireframe',
  },
  {
    id: 'mobile_midas33_optimized',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 390, height: 844 },
    renderMode: 'wireframe',
    workflowState: 'optimized_mobile',
  },
  {
    id: 'desktop_midas33_solid',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    workflowState: 'optimized_solid',
  },
  {
    id: 'desktop_midas33_contour',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'contour',
    workflowState: 'optimized_contour',
  },
  {
    id: 'desktop_midas33_plan_wireframe',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'wireframe',
    viewPreset: 'plan',
    workflowState: 'plan_view',
    canvasFrame: { minCoverageHeight: 0.08, maxAspectRatio: 12 },
  },
  {
    id: 'desktop_midas33_review_member',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    memberSearch: '911',
    reviewStatus: 'approved',
    workflowState: 'review_member_selection',
  },
  {
    id: 'desktop_midas33_compare_risk_overlay',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=compare',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    comparisonOverlay: 'risk_up',
    workflowState: 'compare_overlay',
  },
  {
    id: 'desktop_midas33_evidence_ingest_csv',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    memberSearch: '911',
    evidenceIngest: 'csv',
    workflowState: 'evidence_ingest_csv',
  },
  {
    id: 'desktop_midas33_renderable_json_ingest',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    evidenceIngest: 'renderable_json',
    workflowState: 'renderable_json_ingest',
  },
  {
    id: 'desktop_midas33_section_edit_apply',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized&member=2911&member_set=2911',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    memberSearch: '2911',
    sectionEditTarget: 'VISUAL-REGRESSION-H400',
    workflowState: 'section_edit_apply',
  },
  {
    id: 'desktop_midas33_loadcomb_draft',
    query: 'project=midas33_release&drawing=midas33_optimized&variant=optimized',
    viewport: { width: 1440, height: 1000 },
    renderMode: 'solid',
    viewPreset: 'review',
    evidenceIngest: 'loadcomb_json',
    loadcombDraftTarget: 'VISUAL_REGRESSION_LCB_085',
    workflowState: 'loadcomb_draft',
  },
]

function readArg(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || fallback : fallback
}

function hasFlag(name) {
  return process.argv.includes(name)
}

function parseCaseIdFilter(value = '') {
  return new Set(String(value || '').split(',').map(item => item.trim()).filter(Boolean))
}

function selectCases(caseFilter) {
  if (!caseFilter.size) return defaultCases
  return defaultCases.filter(testCase => caseFilter.has(testCase.id))
}

function sendText(response, status, text) {
  const body = Buffer.from(text)
  response.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': String(body.length),
  })
  response.end(body)
}

function createStaticServer() {
  return http.createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1')
    const decodedPath = decodeURIComponent(requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname)
    const target = path.resolve(rootDir, `.${decodedPath}`)
    if (!target.startsWith(rootDir)) {
      sendText(response, 403, 'Forbidden')
      return
    }
    if (!existsSync(target) || !statSync(target).isFile()) {
      sendText(response, 404, 'Not found')
      return
    }
    response.writeHead(200, {
      'Content-Type': mimeTypes[path.extname(target)] || 'application/octet-stream',
    })
    createReadStream(target).pipe(response)
  })
}

function sha256Buffer(buffer) {
  return createHash('sha256').update(buffer).digest('hex')
}

function sha256Path(relativePath) {
  const absolutePath = path.join(rootDir, relativePath)
  if (!existsSync(absolutePath)) return ''
  return sha256Buffer(readFileSync(absolutePath))
}

function sourceRow(relativePath, label) {
  const absolutePath = path.join(rootDir, relativePath)
  return {
    label,
    path: relativePath,
    available: existsSync(absolutePath),
    bytes: existsSync(absolutePath) ? statSync(absolutePath).size : 0,
    sha256: sha256Path(relativePath),
  }
}

function signatureHash(signature) {
  return sha256Buffer(Buffer.from(JSON.stringify(signature.values || [])))
}

function compareSignatures(left, right) {
  const leftValues = Array.isArray(left?.values) ? left.values : []
  const rightValues = Array.isArray(right?.values) ? right.values : []
  const count = Math.min(leftValues.length, rightValues.length)
  if (!count || leftValues.length !== rightValues.length) {
    return { comparable: false, mean_abs_diff: Infinity, max_abs_diff: Infinity }
  }
  let total = 0
  let max = 0
  for (let index = 0; index < count; index += 1) {
    const diff = Math.abs(Number(leftValues[index]) - Number(rightValues[index]))
    total += diff
    max = Math.max(max, diff)
  }
  return { comparable: true, mean_abs_diff: total / count, max_abs_diff: max }
}

async function readCanvasSignature(page, { selector = '#viewport canvas', width = 24, height = 18 } = {}) {
  return page.evaluate(
    ({ selector: canvasSelector, width: sampleWidth, height: sampleHeight }) => {
      const canvas = document.querySelector(canvasSelector)
      if (!(canvas instanceof HTMLCanvasElement)) {
        return { available: false, reason: 'canvas_missing', width: sampleWidth, height: sampleHeight, values: [] }
      }
      const probe = document.createElement('canvas')
      probe.width = sampleWidth
      probe.height = sampleHeight
      const context = probe.getContext('2d')
      if (!context) {
        return { available: false, reason: 'no_2d_context', width: sampleWidth, height: sampleHeight, values: [] }
      }
      context.drawImage(canvas, 0, 0, sampleWidth, sampleHeight)
      const pixels = context.getImageData(0, 0, sampleWidth, sampleHeight).data
      const values = []
      for (let index = 0; index < pixels.length; index += 4) {
        const red = pixels[index]
        const green = pixels[index + 1]
        const blue = pixels[index + 2]
        const alpha = pixels[index + 3]
        values.push(alpha > 0 ? Math.round(red * 0.2126 + green * 0.7152 + blue * 0.0722) : 0)
      }
      return { available: true, width: sampleWidth, height: sampleHeight, values }
    },
    { selector, width, height },
  )
}

async function settleAnimationFrames(page) {
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve))
  }))
}

async function activateButton(page, selector, timeoutMs) {
  const button = page.locator(selector)
  await button.waitFor({ state: 'visible', timeout: timeoutMs })
  await button.click()
  await page.waitForFunction(
    (buttonSelector) => document.querySelector(buttonSelector)?.classList.contains('active') === true,
    selector,
    { timeout: timeoutMs },
  )
}

async function selectMember(page, memberSearch, timeoutMs) {
  const normalizedSearch = String(memberSearch || '').trim()
  if (!normalizedSearch) return ''
  await page.locator('#member-search-input').fill(normalizedSearch)
  await page.waitForFunction(
    (search) => document.querySelector('#search-results')?.textContent?.includes(search) === true,
    normalizedSearch,
    { timeout: timeoutMs },
  )
  const firstSearchResult = page.locator('[data-search-focus]').first()
  await firstSearchResult.waitFor({ state: 'visible', timeout: timeoutMs })
  const selectedMember = await firstSearchResult.getAttribute('data-search-focus')
  await firstSearchResult.click()
  if (selectedMember) {
    await page.waitForFunction(
      (member) => document.querySelector('#stage-selection-chip')?.textContent?.includes(member) === true,
      selectedMember,
      { timeout: timeoutMs },
    )
  }
  return selectedMember || normalizedSearch
}

async function applyReviewState(page, testCase, timeoutMs) {
  if (!testCase.reviewStatus) return ''
  const status = String(testCase.reviewStatus)
  await page.locator('#review-task-status-select').selectOption(status)
  await page.getByRole('button', { name: 'Save Task' }).click()
  await page.waitForFunction(
    () => document.querySelector('#viewer-report-export-panel')?.textContent?.includes('Review Task') === true,
    null,
    { timeout: timeoutMs },
  )
  return status
}

async function applyComparisonOverlay(page, comparisonOverlay, timeoutMs) {
  const filter = String(comparisonOverlay || '').trim()
  if (!filter) return ''
  await page.locator(`[data-member-comparison-overlay="${filter}"]`).first().click()
  await page.waitForFunction(
    (expectedFilter) => window.__STRUCTURE_VIEWER_COMPARISON_HIGHLIGHT_STATE__?.filter === expectedFilter,
    filter,
    { timeout: timeoutMs },
  )
  return filter
}

async function applyEvidenceIngest(page, testCase, selectedMember, timeoutMs) {
  const ingestMode = String(testCase.evidenceIngest || '').trim()
  if (!ingestMode) return { evidenceIngest: '', renderablePayloadKind: '' }
  const memberId = selectedMember || String(testCase.memberSearch || '911')
  const isRenderableJson = ingestMode === 'renderable_json' || ingestMode === 'loadcomb_json'
  const isLoadcombJson = ingestMode === 'loadcomb_json'
  const drawingId = isLoadcombJson ? 'visual_regression_loadcomb' : 'visual_regression_renderable'
  await page.locator('#evidence-ingest-source-select').selectOption(isRenderableJson ? 'json' : 'csv')
  const filePayload = isRenderableJson
    ? {
        name: isLoadcombJson ? 'visual-regression-loadcomb.json' : 'visual-regression-renderable.json',
        mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify({
          drawing_id: drawingId,
          drawing_title: isLoadcombJson ? 'Visual Regression Load Combination' : 'Visual Regression Renderable',
          artifact_path: isLoadcombJson ? 'visual-regression-loadcomb.json' : 'visual-regression-renderable.json',
          member_count: 3,
          node_count: 4,
          element_count: 3,
          model: {
            nodes: [
              { id: 1, x: 0, y: 0, z: 0 },
              { id: 2, x: 8, y: 0, z: 0 },
              { id: 3, x: 0, y: 0, z: 8 },
              { id: 4, x: 8, y: 0, z: 8 },
            ],
            elements: [
              { id: 'VR-1', member_id: 'VR-1', type: 'beam', node_ids: [1, 2], section: 'VR-B1', dcr: 0.62 },
              { id: 'VR-2', member_id: 'VR-2', type: 'column', node_ids: [1, 3], section: 'VR-C1', dcr: 0.74 },
              { id: 'VR-3', member_id: 'VR-3', type: 'beam', node_ids: [3, 4], section: 'VR-B1', dcr: 0.69 },
            ],
            loads: isLoadcombJson
              ? {
                  load_combinations: [
                    {
                      name: 'VR_BASE_COMBO',
                      combination_type: 'GEN',
                      limit_state: 'ACTIVE',
                      expression: '1.000(DEAD) + 0.500(LIVE)',
                      entry_rows: [
                        { reference_kind: 'ST', reference_name: 'DEAD', factor: 1.0 },
                        { reference_kind: 'ST', reference_name: 'LIVE', factor: 0.5 },
                      ],
                    },
                  ],
                }
              : undefined,
          },
        })),
      }
    : {
        name: 'visual-regression-evidence.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(
          [
            'drawing_id,artifact_path,member_count,node_count,element_count,member_id,source_tool,story,frame_section,dcr_after,receipt_path,status',
            `midas33_optimized,visual-regression-evidence.csv,4,6,4,${memberId},ETABS 22,L33,SRC-900,0.93,receipt-visual.json,verified`,
            `midas33_optimized,visual-regression-evidence.csv,4,6,4,${memberId},ETABS 22,L33,FORCED-MISMATCH,0.99,receipt-visual-mismatch.json,verified`,
            '',
          ].join('\n'),
        ),
      }
  await page.locator('#evidence-ingest-input').setInputFiles(filePayload)
  await page.waitForFunction(
    () => window.__STRUCTURE_VIEWER_LAST_INGEST_PREVIEW__?.drawing_count >= 1
      && document.querySelector('#viewer-report-export-panel')?.textContent?.includes('Evidence Ingest') === true,
    null,
    { timeout: timeoutMs },
  )
  if (isRenderableJson) {
    await page.waitForFunction(
      () => window.__STRUCTURE_VIEWER_LAST_INGEST_RENDERABLE_PAYLOAD__?.payload_kind === 'direct_model'
        && document.querySelector('#viewer-report-export-panel')?.textContent?.includes('renderable direct_model') === true,
      null,
      { timeout: timeoutMs },
    )
  }
  return {
    evidenceIngest: ingestMode === 'loadcomb_json' ? '' : (isRenderableJson ? 'json' : 'csv'),
    renderablePayloadKind: ingestMode === 'loadcomb_json' ? '' : (isRenderableJson ? 'direct_model' : ''),
    previewDrawingId: drawingId,
  }
}

async function applySectionEdit(page, testCase, selectedMember, timeoutMs) {
  const targetSection = String(testCase.sectionEditTarget || '').trim()
  if (!targetSection) return ''
  if (!selectedMember) {
    throw new Error(`${testCase.id} requires selectedMember before section edit`)
  }
  await page.locator('#edit-preview-section-input').fill(targetSection)
  await page.locator('#edit-preview-note-input').fill('visual regression section edit')
  await page.evaluate(() => window.stageSectionEditPreview?.())
  try {
    await page.waitForFunction(
      (target) => {
        const status = document.querySelector('#edit-preview-status')?.textContent || ''
        return status.includes('Draft staged') && status.includes(target)
      },
      targetSection,
      { timeout: Math.min(timeoutMs, 10000) },
    )
  } catch (error) {
    const debug = await page.evaluate(() => ({
      status: document.querySelector('#edit-preview-status')?.textContent?.trim() || '',
      list: document.querySelector('#edit-preview-list')?.textContent?.trim().slice(0, 500) || '',
      selectedText: document.querySelector('#stage-selection-chip')?.textContent?.trim() || '',
      stageDisabled: document.querySelector('#edit-preview-stage-button')?.disabled ?? null,
      applyDisabled: document.querySelector('#edit-preview-apply-button')?.disabled ?? null,
      sectionInput: document.querySelector('#edit-preview-section-input')?.value || '',
    }))
    throw new Error(`${testCase.id} section edit draft did not stage: ${JSON.stringify(debug)} | ${error.message}`)
  }
  await page.evaluate(() => window.applySectionEditPreview?.())
  try {
    await page.waitForFunction(
      (target) => document.querySelector('#edit-preview-status')?.textContent?.includes('Applied staged') === true
        && document.querySelector('#edit-preview-list')?.textContent?.includes(target) === true,
      targetSection,
      { timeout: Math.min(timeoutMs, 10000) },
    )
  } catch (error) {
    const debug = await page.evaluate(() => ({
      status: document.querySelector('#edit-preview-status')?.textContent?.trim() || '',
      list: document.querySelector('#edit-preview-list')?.textContent?.trim().slice(0, 500) || '',
      propertyPanel: document.querySelector('#prop-panel')?.textContent?.trim().slice(0, 500) || '',
      selectedText: document.querySelector('#stage-selection-chip')?.textContent?.trim() || '',
      applyDisabled: document.querySelector('#edit-preview-apply-button')?.disabled ?? null,
    }))
    throw new Error(`${testCase.id} section edit apply did not render: ${JSON.stringify(debug)} | ${error.message}`)
  }
  return targetSection
}

async function getFirstLoadcombBaseName(page) {
  return page.locator('#loadcomb-edit-base-select option').evaluateAll((options) => {
    const option = options.find(item => item instanceof HTMLOptionElement && item.value)
    return option?.value || ''
  })
}

async function applyLoadcombDraft(page, testCase, timeoutMs, evidenceState = {}) {
  const targetName = String(testCase.loadcombDraftTarget || '').trim()
  if (!targetName) return ''
  let baseName = await getFirstLoadcombBaseName(page)
  if (!baseName && evidenceState.previewDrawingId) {
    const origin = new URL(page.url()).origin
    await page.goto(
      `${origin}/src/structure-viewer/index.html?project=evidence_ingest_preview&drawing=${evidenceState.previewDrawingId}&variant=optimized`,
      { timeout: timeoutMs, waitUntil: 'commit' },
    )
    await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: timeoutMs })
    await waitForCanvasNonBlank(page, { timeout: timeoutMs })
    await activateButton(page, `#btn-${String(testCase.renderMode || 'solid').trim().toLowerCase()}`, timeoutMs)
    baseName = await getFirstLoadcombBaseName(page)
  }
  if (!baseName) {
    throw new Error(`${testCase.id} requires a load-combination catalog option`)
  }
  await page.locator('#loadcomb-edit-base-select').selectOption(baseName)
  await page.locator('#loadcomb-edit-name-input').fill(targetName)
  await page.locator('#loadcomb-edit-scale-input').fill('0.85')
  await page.locator('#loadcomb-edit-note-input').fill('visual regression loadcomb draft')
  await page.locator('#loadcomb-edit-stage-button').click()
  await page.waitForFunction(
    (target) => document.querySelector('#loadcomb-edit-status')?.textContent?.includes(target) === true
      && document.querySelector('#loadcomb-edit-list')?.textContent?.includes(target) === true,
    targetName,
    { timeout: timeoutMs },
  )
  return targetName
}

async function applyCaseState(page, testCase, timeoutMs) {
  const viewPreset = String(testCase.viewPreset || '').trim().toLowerCase()
  if (viewPreset) {
    await activateButton(page, `#btn-view-${viewPreset}`, timeoutMs)
  }

  const renderMode = String(testCase.renderMode || 'wireframe').trim().toLowerCase()
  await activateButton(page, `#btn-${renderMode}`, timeoutMs)

  const selectedMember = await selectMember(page, testCase.memberSearch, timeoutMs)
  const reviewStatus = await applyReviewState(page, testCase, timeoutMs)
  const comparisonOverlay = await applyComparisonOverlay(page, testCase.comparisonOverlay, timeoutMs)
  const evidenceState = await applyEvidenceIngest(page, testCase, selectedMember, timeoutMs)
  const { evidenceIngest, renderablePayloadKind } = evidenceState
  const sectionEditTarget = await applySectionEdit(page, testCase, selectedMember, timeoutMs)
  const loadcombDraftTarget = await applyLoadcombDraft(page, testCase, timeoutMs, evidenceState)
  await settleAnimationFrames(page)
  return {
    renderMode,
    viewPreset,
    workflowState: String(testCase.workflowState || '').trim(),
    selectedMember,
    reviewStatus,
    comparisonOverlay,
    evidenceIngest,
    renderablePayloadKind,
    sectionEditTarget,
    loadcombDraftTarget,
  }
}

async function captureCase(page, baseUrl, testCase, timeoutMs) {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await installCanvasFrameProbe(page)
  await page.setViewportSize(testCase.viewport)
  const url = `${baseUrl}/src/structure-viewer/index.html?${testCase.query}`
  await page.goto(url, { timeout: timeoutMs, waitUntil: 'commit' })
  await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: timeoutMs })
  await waitForCanvasNonBlank(page, { timeout: timeoutMs })
  const appliedState = await applyCaseState(page, testCase, timeoutMs)
  await waitForCanvasNonBlank(page, { timeout: timeoutMs })
  const canvasMetrics = await assertCanvasWellFramed(page, {
    label: `${testCase.id} canvas`,
    minCoverageWidth: 0.08,
    minCoverageHeight: 0.1,
    minPixelRatio: 0.001,
    ...(testCase.canvasFrame || {}),
  })
  const signature = await readCanvasSignature(page)
  const screenshot = await page.screenshot({ fullPage: false })
  const markers = await page.evaluate(() => ({
    title: document.title,
    stageVariant: document.querySelector('#stage-variant-chip')?.textContent?.trim() || '',
    workspaceStatus: document.querySelector('#project-workspace-status')?.textContent?.trim() || '',
    renderMode: document.querySelector('[data-render-mode-button].active')?.id?.replace('btn-', '') || '',
    viewPreset: document.querySelector('[data-view-preset-button].active')?.id?.replace('btn-view-', '') || '',
    legendVisible: window.getComputedStyle(document.querySelector('#legend-container')).display !== 'none',
    selectedText: document.querySelector('#stage-selection-chip')?.textContent?.trim() || '',
    comparisonFilter: window.__STRUCTURE_VIEWER_COMPARISON_HIGHLIGHT_STATE__?.filter || '',
    evidenceIngestKind: window.__STRUCTURE_VIEWER_LAST_INGEST_PREVIEW__?.source_type || '',
    evidenceIngestDrawingCount: window.__STRUCTURE_VIEWER_LAST_INGEST_PREVIEW__?.drawing_count || 0,
    renderablePayloadKind: window.__STRUCTURE_VIEWER_LAST_INGEST_RENDERABLE_PAYLOAD__?.payload_kind || '',
    sectionEditStatus: document.querySelector('#edit-preview-status')?.textContent?.trim() || '',
    sectionEditList: document.querySelector('#edit-preview-list')?.textContent?.trim().slice(0, 500) || '',
    loadcombEditStatus: document.querySelector('#loadcomb-edit-status')?.textContent?.trim() || '',
    loadcombEditList: document.querySelector('#loadcomb-edit-list')?.textContent?.trim().slice(0, 500) || '',
    reportPanel: document.querySelector('#viewer-report-export-panel')?.textContent?.trim().slice(0, 500) || '',
  }))
  return {
    id: testCase.id,
    query: testCase.query,
    viewport: testCase.viewport,
    expected_render_mode: appliedState.renderMode,
    expected_view_preset: appliedState.viewPreset,
    expected_workflow_state: appliedState.workflowState,
    expected_selected_member: appliedState.selectedMember,
    expected_review_status: appliedState.reviewStatus,
    expected_comparison_filter: appliedState.comparisonOverlay,
    expected_evidence_ingest_kind: appliedState.evidenceIngest,
    expected_renderable_payload_kind: appliedState.renderablePayloadKind,
    expected_section_edit_target: appliedState.sectionEditTarget,
    expected_loadcomb_draft_target: appliedState.loadcombDraftTarget,
    url,
    canvas_metrics: canvasMetrics,
    canvas_signature: {
      ...signature,
      sha256: signatureHash(signature),
    },
    viewport_screenshot_sha256: sha256Buffer(screenshot),
    markers,
    browser_errors: errors,
  }
}

function compareRows(currentRows, baselineRows, tolerances) {
  const baselineById = new Map(baselineRows.map(row => [row.id, row]))
  return currentRows.map((row) => {
    const baseline = baselineById.get(row.id)
    const signatureDelta = compareSignatures(row.canvas_signature, baseline?.canvas_signature)
    const coverageWidthDelta = Math.abs(
      Number(row.canvas_metrics?.coverageWidth || 0) - Number(baseline?.canvas_metrics?.coverageWidth || 0),
    )
    const coverageHeightDelta = Math.abs(
      Number(row.canvas_metrics?.coverageHeight || 0) - Number(baseline?.canvas_metrics?.coverageHeight || 0),
    )
    const centerXDelta = Math.abs(Number(row.canvas_metrics?.centerX || 0) - Number(baseline?.canvas_metrics?.centerX || 0))
    const centerYDelta = Math.abs(Number(row.canvas_metrics?.centerY || 0) - Number(baseline?.canvas_metrics?.centerY || 0))
    const markerMissing = [
      ...(row.markers?.stageVariant ? [] : ['stage_variant_missing']),
      ...(row.markers?.workspaceStatus ? [] : ['workspace_status_missing']),
      ...(row.markers?.renderMode ? [] : ['render_mode_missing']),
    ]
    const expectedRenderMode = String(row.expected_render_mode || '').trim()
    const expectedViewPreset = String(row.expected_view_preset || '').trim()
    const expectedSelectedMember = String(row.expected_selected_member || '').trim()
    const expectedComparisonFilter = String(row.expected_comparison_filter || '').trim()
    const expectedEvidenceIngestKind = String(row.expected_evidence_ingest_kind || '').trim()
    const expectedRenderablePayloadKind = String(row.expected_renderable_payload_kind || '').trim()
    const expectedSectionEditTarget = String(row.expected_section_edit_target || '').trim()
    const expectedLoadcombDraftTarget = String(row.expected_loadcomb_draft_target || '').trim()
    const renderModeMismatch = expectedRenderMode && row.markers?.renderMode !== expectedRenderMode
    const viewPresetMismatch = expectedViewPreset && row.markers?.viewPreset !== expectedViewPreset
    const selectedMemberMissing = expectedSelectedMember
      && !String(row.markers?.selectedText || '').includes(expectedSelectedMember)
    const comparisonFilterMismatch = expectedComparisonFilter
      && row.markers?.comparisonFilter !== expectedComparisonFilter
    const evidenceIngestMissing = expectedEvidenceIngestKind
      && (row.markers?.evidenceIngestKind !== expectedEvidenceIngestKind
        || Number(row.markers?.evidenceIngestDrawingCount || 0) < 1)
    const renderablePayloadMissing = expectedRenderablePayloadKind
      && row.markers?.renderablePayloadKind !== expectedRenderablePayloadKind
    const sectionEditStatusText = String(row.markers?.sectionEditStatus || '')
    const sectionEditListText = String(row.markers?.sectionEditList || '')
    const sectionEditMissing = expectedSectionEditTarget
      && !(sectionEditStatusText.includes('Applied staged draft')
        && sectionEditListText.includes(expectedSectionEditTarget))
    const loadcombDraftMissing = expectedLoadcombDraftTarget
      && !(String(row.markers?.loadcombEditStatus || '').includes(expectedLoadcombDraftTarget)
        && String(row.markers?.loadcombEditList || '').includes(expectedLoadcombDraftTarget))
    const blockers = [
      ...(!baseline ? ['baseline_case_missing'] : []),
      ...(row.browser_errors?.length ? ['browser_console_errors_present'] : []),
      ...(!row.canvas_metrics?.nonBlank ? ['canvas_blank'] : []),
      ...(renderModeMismatch ? ['render_mode_mismatch'] : []),
      ...(viewPresetMismatch ? ['view_preset_mismatch'] : []),
      ...(selectedMemberMissing ? ['selected_member_missing'] : []),
      ...(comparisonFilterMismatch ? ['comparison_filter_mismatch'] : []),
      ...(evidenceIngestMissing ? ['evidence_ingest_missing'] : []),
      ...(renderablePayloadMissing ? ['renderable_payload_missing'] : []),
      ...(sectionEditMissing ? ['section_edit_missing'] : []),
      ...(loadcombDraftMissing ? ['loadcomb_draft_missing'] : []),
      ...(!signatureDelta.comparable ? ['signature_not_comparable'] : []),
      ...(signatureDelta.mean_abs_diff > tolerances.maxMeanAbsDiff ? ['signature_mean_abs_diff_exceeded'] : []),
      ...(signatureDelta.max_abs_diff > tolerances.maxMaxAbsDiff ? ['signature_max_abs_diff_exceeded'] : []),
      ...(coverageWidthDelta > tolerances.maxCoverageDelta ? ['coverage_width_delta_exceeded'] : []),
      ...(coverageHeightDelta > tolerances.maxCoverageDelta ? ['coverage_height_delta_exceeded'] : []),
      ...(centerXDelta > tolerances.maxCenterDelta ? ['center_x_delta_exceeded'] : []),
      ...(centerYDelta > tolerances.maxCenterDelta ? ['center_y_delta_exceeded'] : []),
      ...markerMissing,
    ]
    return {
      id: row.id,
      status: blockers.length ? 'blocked' : 'pass',
      blockers,
      signature_delta: signatureDelta,
      coverage_width_delta: coverageWidthDelta,
      coverage_height_delta: coverageHeightDelta,
      center_x_delta: centerXDelta,
      center_y_delta: centerYDelta,
      expected_render_mode: expectedRenderMode,
      actual_render_mode: row.markers?.renderMode || '',
      expected_view_preset: expectedViewPreset,
      actual_view_preset: row.markers?.viewPreset || '',
      expected_workflow_state: row.expected_workflow_state || '',
      expected_selected_member: expectedSelectedMember,
      actual_selected_text: row.markers?.selectedText || '',
      expected_comparison_filter: expectedComparisonFilter,
      actual_comparison_filter: row.markers?.comparisonFilter || '',
      expected_evidence_ingest_kind: expectedEvidenceIngestKind,
      actual_evidence_ingest_kind: row.markers?.evidenceIngestKind || '',
      expected_renderable_payload_kind: expectedRenderablePayloadKind,
      actual_renderable_payload_kind: row.markers?.renderablePayloadKind || '',
      expected_section_edit_target: expectedSectionEditTarget,
      actual_section_edit_status: row.markers?.sectionEditStatus || '',
      expected_loadcomb_draft_target: expectedLoadcombDraftTarget,
      actual_loadcomb_edit_status: row.markers?.loadcombEditStatus || '',
    }
  })
}

function buildPayload({ rows, baselinePath, baselinePayload = null, mode, tolerances }) {
  const compare_rows = baselinePayload ? compareRows(rows, baselinePayload.case_rows || [], tolerances) : []
  const blockers = [
    ...(rows.flatMap(row => (row.browser_errors || []).map(error => `browser_error:${row.id}:${error}`))),
    ...(mode === 'verify' && !baselinePayload ? ['baseline_missing'] : []),
    ...compare_rows.flatMap(row => row.blockers.map(blocker => `${row.id}:${blocker}`)),
  ]
  const pass = blockers.length === 0
  return {
    schema_version: schemaVersion,
    generated_at: new Date().toISOString(),
    contract_pass: pass,
    reason_code: pass ? 'PASS' : 'ERR_STRUCTURE_VIEWER_VISUAL_REGRESSION_PENDING',
    summary_line: pass
      ? `Structure viewer visual regression: PASS | cases=${rows.length}/${rows.length} | mode=${mode}`
      : `Structure viewer visual regression: BLOCKED | blockers=${blockers.length} | mode=${mode}`,
    mode,
    visual_regression_mode: 'local_canvas_signature_baseline',
    live_visual_claim: false,
    independent_product_claim: false,
    claim_boundary: 'Local visual signature regression only; not a pixel-perfect customer-device rendering claim.',
    baseline_path: baselinePath,
    tolerances,
    case_rows: rows,
    compare_rows,
    visual_case_scope: {
      cases: rows.length,
      render_modes: [...new Set(rows.map(row => row.expected_render_mode).filter(Boolean))],
      view_presets: [...new Set(rows.map(row => row.expected_view_preset).filter(Boolean))],
      workflow_states: [...new Set(rows.map(row => row.expected_workflow_state).filter(Boolean))],
      viewports: [...new Set(rows.map(row => `${row.viewport?.width || 0}x${row.viewport?.height || 0}`))],
    },
    source_rows: [
      sourceRow('src/structure-viewer/index.html', 'viewer_index'),
      sourceRow('scripts/measure-structure-viewer-visual-regression.mjs', 'visual_regression_probe'),
      sourceRow('scripts/structure-viewer-canvas-frame.mjs', 'canvas_frame_probe'),
      sourceRow('tests/frontend/structure-viewer-smoke.spec.ts', 'frontend_smoke_spec'),
    ],
    residual_live_work: [
      'Add screenshot image artifacts only when storage and review policy are defined.',
      'Run the same visual baseline across the customer browser/device matrix.',
      'Expand visual baselines to customer browser/device matrix and low-memory profiles.',
    ],
    blockers,
  }
}

async function captureRows(cases, timeoutMs) {
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  const { chromium } = await import('@playwright/test')
  const browser = await chromium.launch({ headless: true })
  try {
    const rows = []
    for (const testCase of cases) {
      const page = await browser.newPage({ viewport: testCase.viewport })
      try {
        rows.push(await captureCase(page, `http://127.0.0.1:${port}`, testCase, timeoutMs))
      } finally {
        await page.close()
      }
    }
    return rows
  } finally {
    await browser.close()
    await new Promise((resolve) => server.close(resolve))
  }
}

async function main() {
  const verifyMode = hasFlag('--verify')
  const updateBaseline = hasFlag('--update-baseline') || (!verifyMode && !hasFlag('--report-only'))
  const dryRun = hasFlag('--dry-run')
  const failBlocked = hasFlag('--fail-blocked')
  const timeoutMs = Number(readArg('--timeout-ms', '60000'))
  const baselinePath = readArg('--baseline', defaultBaseline)
  const caseFilter = parseCaseIdFilter(readArg('--case-id', ''))
  const selectedCases = selectCases(caseFilter)
  if (!selectedCases.length) {
    throw new Error(`No visual regression cases matched --case-id=${[...caseFilter].join(',')}`)
  }
  const defaultOut = verifyMode
    ? path.join(os.tmpdir(), 'structure_viewer_visual_regression_report.json')
    : baselinePath
  const out = readArg('--out', defaultOut)
  const tolerances = {
    maxMeanAbsDiff: Number(readArg('--max-mean-abs-diff', '32')),
    maxMaxAbsDiff: Number(readArg('--max-max-abs-diff', '150')),
    maxCoverageDelta: Number(readArg('--max-coverage-delta', '0.16')),
    maxCenterDelta: Number(readArg('--max-center-delta', '0.12')),
  }
  const command = [
    process.execPath,
    'scripts/measure-structure-viewer-visual-regression.mjs',
    ...(verifyMode ? ['--verify'] : []),
    ...(updateBaseline ? ['--update-baseline'] : []),
    ...(caseFilter.size ? ['--case-id', [...caseFilter].join(',')] : []),
    '--baseline',
    baselinePath,
    '--out',
    out,
  ]
  if (dryRun) {
    console.log(command.join(' '))
    return
  }
  const rows = await captureRows(selectedCases, timeoutMs)
  const baselinePayload = existsSync(path.resolve(rootDir, baselinePath))
    ? JSON.parse(readFileSync(path.resolve(rootDir, baselinePath), 'utf8'))
    : null
  const mode = updateBaseline ? 'baseline_update' : 'verify'
  const payload = buildPayload({ rows, baselinePath, baselinePayload: updateBaseline ? null : baselinePayload, mode, tolerances })
  const absoluteOut = path.resolve(rootDir, out)
  mkdirSync(path.dirname(absoluteOut), { recursive: true })
  writeFileSync(absoluteOut, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
  console.log(payload.summary_line)
  if (failBlocked && !payload.contract_pass) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
