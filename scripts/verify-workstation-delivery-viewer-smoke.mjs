import { createReadStream, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import zlib from 'node:zlib'

import {
  installCanvasFrameProbe,
  readCanvasFrameMetrics,
  waitForCanvasNonBlank,
} from './structure-viewer-canvas-frame.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const DEFAULT_PACKAGE = 'implementation/phase1/release/workstation_delivery/project_package.zip'
const DEFAULT_OUT = 'implementation/phase1/workstation_delivery_viewer_smoke.json'
const DEFAULT_SCREENSHOT = '/tmp/workstation-delivery-viewer-smoke.png'

const CLAIM_BOUNDARY = [
  'Local customer-open browser smoke for the workstation delivery package only.',
  'This is not a customer-device FPS claim and not independent structural-solver approval.',
].join(' ')

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.pdf': 'application/pdf',
  '.svg': 'image/svg+xml; charset=utf-8',
}

function parseArgs(argv) {
  const args = {
    packagePath: path.resolve(rootDir, DEFAULT_PACKAGE),
    outPath: path.resolve(rootDir, DEFAULT_OUT),
    screenshotPath: DEFAULT_SCREENSHOT,
    json: false,
    failBlocked: false,
    staticOnly: false,
    keepExtract: false,
  }
  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--package') args.packagePath = path.resolve(rootDir, argv[++index] || DEFAULT_PACKAGE)
    else if (arg === '--out') args.outPath = path.resolve(rootDir, argv[++index] || DEFAULT_OUT)
    else if (arg === '--screenshot') args.screenshotPath = argv[++index] || DEFAULT_SCREENSHOT
    else if (arg === '--json') args.json = true
    else if (arg === '--fail-blocked') args.failBlocked = true
    else if (arg === '--static-only') args.staticOnly = true
    else if (arg === '--keep-extract') args.keepExtract = true
    else throw new Error(`Unknown argument: ${arg}`)
  }
  return args
}

function nowIso() {
  return new Date().toISOString()
}

function sha256Path(filePath) {
  return crypto.createHash('sha256').update(readFileSync(filePath)).digest('hex')
}

function safeReadText(filePath) {
  if (!existsSync(filePath) || !statSync(filePath).isFile()) return ''
  return readFileSync(filePath, 'utf8')
}

function safeReadJson(filePath) {
  try {
    return JSON.parse(safeReadText(filePath))
  } catch {
    return {}
  }
}

function extractZip(packagePath) {
  const extractRoot = mkdtempSync(path.join(os.tmpdir(), 'workstation-delivery-viewer-smoke-'))
  const result = spawnSync('python3', ['-m', 'zipfile', '-e', packagePath, extractRoot], {
    cwd: rootDir,
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`zip extract failed: ${result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return extractRoot
}

function verifyChecksums(extractRoot) {
  const checksumPath = path.join(extractRoot, 'checksums.sha256')
  const mismatches = []
  let checkedRows = 0
  if (!existsSync(checksumPath)) {
    return { pass: false, reason: 'checksums_file_missing', checked_rows: 0, mismatches: ['checksums.sha256'] }
  }
  for (const line of safeReadText(checksumPath).split(/\r?\n/)) {
    if (!line.trim()) continue
    const separator = line.indexOf('  ')
    const expected = separator >= 0 ? line.slice(0, separator) : ''
    const relativePath = separator >= 0 ? line.slice(separator + 2) : ''
    const target = path.resolve(extractRoot, relativePath)
    checkedRows += 1
    if (!target.startsWith(extractRoot) || !existsSync(target)) {
      mismatches.push(`missing:${relativePath}`)
    } else if (sha256Path(target) !== expected) {
      mismatches.push(`sha256_mismatch:${relativePath}`)
    }
  }
  return {
    pass: checkedRows > 0 && mismatches.length === 0,
    reason: checkedRows > 0 && mismatches.length === 0 ? 'PASS' : 'checksum_mismatch',
    checked_rows: checkedRows,
    mismatches,
  }
}

function staticViewerChecks(extractRoot, packagePath) {
  const viewerPath = path.join(extractRoot, 'viewer.html')
  const manifestPath = path.join(extractRoot, 'manifest.json')
  const viewerText = safeReadText(viewerPath)
  const manifest = safeReadJson(manifestPath)
  const outputRows = Array.isArray(manifest.output_rows) ? manifest.output_rows : []
  const outputPaths = new Set(outputRows.map((row) => String(row?.path || '')))
  const checksums = verifyChecksums(extractRoot)
  const required = {
    package_zip: existsSync(packagePath),
    viewer_html: existsSync(viewerPath),
    manifest_json: existsSync(manifestPath),
    checksums_sha256: existsSync(path.join(extractRoot, 'checksums.sha256')),
  }
  const viewerMarkers = {
    has_html_shell: /<html[\s>]/i.test(viewerText),
    has_viewport_region: viewerText.includes('id="viewport"') || viewerText.includes("id='viewport'") || viewerText.includes('#viewport'),
    has_canvas_contract: viewerText.includes('canvas'),
    has_three_runtime: viewerText.includes('THREE') || viewerText.includes('three'),
    has_render_controls: viewerText.includes('setRenderMode') || viewerText.includes('Render Mode'),
  }
  const manifestMarkers = {
    references_viewer: outputPaths.has('viewer.html'),
    references_report: outputPaths.has('report.pdf'),
    claim_boundary_present: String(manifest.package_claim_boundary || '').toLowerCase().includes('structural engineer review'),
  }
  const commercialMarkers = {
    structural_insight_title: viewerText.includes('Structural Insight Viewer'),
    cockpit_polish_css: viewerText.includes('commercial-cockpit-polish'),
    workflow_tabs: viewerText.includes('workflow-tab') || viewerText.includes('Model') && viewerText.includes('Optimization'),
    top_project_selector: viewerText.includes('data-shell-project-select') && viewerText.includes('setTopbarWorkspaceSelection') && viewerText.includes('renderTopbarProjectSelector'),
    top_run_control: viewerText.includes('data-top-run-control') && viewerText.includes('data-top-run-action') && viewerText.includes('startNewReviewRun'),
    model_overview: viewerText.includes('data-model-overview-panel') && viewerText.includes('data-source-adapter-matrix') && viewerText.includes('structure-viewer-source-adapter-matrix.v1') && viewerText.includes('renderSourceAdapterMatrix'),
    stage_review_controls: viewerText.includes('data-stage-review-controls') && viewerText.includes('data-stage-model-stack'),
    deformation_scale_control: viewerText.includes('data-stage-deformation-control') && viewerText.includes('structure-viewer-deformation-control.v1') && viewerText.includes('updateDeformDisplayScale') && viewerText.includes('formatDeformDisplayScale'),
    kpi_full_label_readout: viewerText.includes('data-kpi-full-label') && viewerText.includes('kpi-card__label') && (viewerText.includes('title="${escapeHtml(card.label)}"') || viewerText.includes('Max Displacement')),
    kpi_full_value_readout: viewerText.includes('data-kpi-full-value') && viewerText.includes('kpi-card__value-number') && viewerText.includes('kpi-card__value-unit') && viewerText.includes('renderKpiReadout'),
    analysis_result_evidence: viewerText.includes('data-analysis-result-evidence') && viewerText.includes('renderAnalysisResultEvidence') && viewerText.includes('analysis-result-evidence-row'),
    optimization_delta_strip: viewerText.includes('data-optimization-delta-strip') && viewerText.includes('data-optimization-delta-row') && viewerText.includes('renderOptimizationDeltaStrip') && viewerText.includes('structure-viewer-optimization-delta-strip.v1'),
    contour_scale_evidence: viewerText.includes('data-contour-scale-evidence') && viewerText.includes('data-contour-scale-ticks'),
    stage_result_scale_priority: viewerText.includes('data-stage-results-priority="first-stage-viewport"') && viewerText.includes('data-stage-loadcases-priority="after-results"') && viewerText.indexOf('id="contour-section"') >= 0 && viewerText.indexOf('id="contour-section"') < viewerText.indexOf('id="loadcases-section"'),
    load_case_evidence_rows: viewerText.includes('load-case-evidence-row') && viewerText.includes('data-load-case-status'),
    utilization_heatmap_evidence: viewerText.includes('data-utilization-heatmap-evidence') && viewerText.includes('analysis-heatmap-receipt'),
    viewport_tool_rail: viewerText.includes('data-viewport-tool-rail') && viewerText.includes('data-viewport-tool-render-mode'),
    analysis_overlay_receipt: viewerText.includes('data-stage-overlay-receipt') && viewerText.includes('__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__'),
    analysis_overlay_visual_evidence: viewerText.includes('data-stage-overlay-visual-evidence') && viewerText.includes('stage-overlay-legend-swatch--load') && viewerText.includes('stage-overlay-legend-swatch--support'),
    analysis_overlay_projected_glyphs: viewerText.includes('data-stage-load-support-glyphs') && viewerText.includes('renderStageLoadSupportGlyphs') && viewerText.includes('positionStageLoadSupportGlyphs') && viewerText.includes('structure-viewer-stage-load-support-glyphs.v1'),
    stage_overlay_occlusion_budget: viewerText.includes('data-stage-overlay-occlusion-budget="dense-model-protagonist"') && viewerText.includes('stage-critical-hotspot small') && viewerText.includes('panel-zone-stage-badge__leader'),
    stage_dominance_budget: viewerText.includes('data-stage-dominance-budget="dense-stage-primary"') && viewerText.includes('grid-template-columns:minmax(154px,164px) minmax(0,1fr) 32px'),
    stage_result_callouts: viewerText.includes('data-stage-callout-focus-member'),
    stage_story_ruler: viewerText.includes('data-stage-story-ruler') && viewerText.includes('renderStageStoryRuler') && viewerText.includes('positionStageStoryRuler') && viewerText.includes('structure-viewer-stage-story-ruler.v1'),
    stage_drift_bands: viewerText.includes('data-stage-drift-bands') && viewerText.includes('renderStageDriftBands') && viewerText.includes('positionStageDriftBands') && viewerText.includes('structure-viewer-stage-drift-bands.v1'),
    stage_critical_hotspots: viewerText.includes('data-stage-critical-hotspots') && viewerText.includes('renderStageCriticalHotspots') && viewerText.includes('positionStageCriticalHotspots') && viewerText.includes('structure-viewer-stage-critical-hotspots.v1'),
    stage_result_receipt: viewerText.includes('data-stage-result-receipt') || viewerText.includes('stage-result-receipt'),
    result_step_schedule: viewerText.includes('data-result-step-schedule') && viewerText.includes('data-result-step-row') && viewerText.includes('renderResultStepSchedule') && viewerText.includes('structure-viewer-result-step-schedule.v1'),
    result_envelope: viewerText.includes('data-result-envelope') && viewerText.includes('data-result-envelope-row') && viewerText.includes('renderResultEnvelope') && viewerText.includes('structure-viewer-result-envelope.v1'),
    critical_triage: viewerText.includes('data-critical-triage') && viewerText.includes('data-critical-triage-row') && viewerText.includes('renderCriticalTriagePanel') && viewerText.includes('structure-viewer-critical-triage.v1'),
    panel_zone_evidence: viewerText.includes('data-panel-zone-evidence') && viewerText.includes('data-panel-zone-member-row') && viewerText.includes('renderPanelZoneEvidencePanel') && viewerText.includes('structure-viewer-panel-zone-evidence.v1'),
    panel_zone_stage_badge: viewerText.includes('data-panel-zone-stage-badge') && viewerText.includes('renderPanelZoneStageBadge') && viewerText.includes('positionPanelZoneStageBadge') && viewerText.includes('structure-viewer-panel-zone-stage-badge.v1'),
    delivery_review_receipt: viewerText.includes('data-delivery-review-receipt') && viewerText.includes('renderDeliveryReviewReceipt') && viewerText.includes('structure-viewer-delivery-review-receipt.v1'),
    material_member_catalog: viewerText.includes('data-material-member-catalog') && viewerText.includes('renderMaterialMemberCatalogPanel') && viewerText.includes('structure-viewer-material-member-catalog.v1'),
    material_family_coverage: viewerText.includes('data-material-family-coverage') && viewerText.includes('data-material-family-chip') && viewerText.includes('MATERIAL_FAMILY_ONTOLOGY'),
    material_ontology_breadth: viewerText.includes('data-material-family-ontology-count') && viewerText.includes('material_family_ontology_count') && viewerText.includes('rail_steel') && viewerText.includes('seismic_isolator') && viewerText.includes('spring_link') && viewerText.includes('fireproofing') && viewerText.includes('waterproofing') && viewerText.includes('insulation') && viewerText.includes('expansion_joint'),
    material_section_schedule: viewerText.includes('data-material-section-schedule') && viewerText.includes('data-material-section-row') && viewerText.includes('material_section_schedule_count'),
    section_member_schedule: viewerText.includes('data-section-schedule') && viewerText.includes('data-section-schedule-row') && viewerText.includes('section_material_schedule_count'),
    critical_members: viewerText.includes('Critical Members'),
    optimization_summary: viewerText.includes('Optimization Summary'),
    drawing_handoff_panel: viewerText.includes('data-drawing-handoff-panel') || viewerText.includes('buildDrawingHandoffPanelHtml'),
  }
  const commercialMarkerCount = Object.values(commercialMarkers).filter(Boolean).length
  const requiredCommercialMarkerCount = Object.keys(commercialMarkers).length
  const commercialCockpitCurrent = commercialMarkerCount >= requiredCommercialMarkerCount
  const staticPass = (
    Object.values(required).every(Boolean)
    && Object.values(viewerMarkers).every(Boolean)
    && Object.values(manifestMarkers).every(Boolean)
    && commercialCockpitCurrent
    && checksums.pass
  )
  return {
    pass: staticPass,
    reason: staticPass ? 'PASS' : 'static_delivery_viewer_contract_failed',
    required_paths: required,
    checksum_self_test: checksums,
    viewer_markers: viewerMarkers,
    manifest_markers: manifestMarkers,
    commercial_cockpit_alignment: {
      status: commercialCockpitCurrent ? 'current_cockpit_delivery' : 'legacy_singlefile_delivery_gap',
      marker_count: commercialMarkerCount,
      required_marker_count_for_current_cockpit: requiredCommercialMarkerCount,
      markers: commercialMarkers,
      note: 'Current cockpit alignment is required for workstation delivery handoff acceptance.',
    },
  }
}

function sendText(response, status, text) {
  const body = Buffer.from(text)
  response.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': String(body.length),
  })
  response.end(body)
}

function createStaticServer(extractRoot) {
  return http.createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1')
    const decodedPath = decodeURIComponent(requestUrl.pathname === '/' ? '/viewer.html' : requestUrl.pathname)
    const target = path.resolve(extractRoot, `.${decodedPath}`)
    if (!target.startsWith(extractRoot)) {
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

function paethPredictor(left, up, upLeft) {
  const p = left + up - upLeft
  const pa = Math.abs(p - left)
  const pb = Math.abs(p - up)
  const pc = Math.abs(p - upLeft)
  if (pa <= pb && pa <= pc) return left
  if (pb <= pc) return up
  return upLeft
}

function analyzePngPixels(buffer) {
  const signature = buffer.subarray(0, 8).toString('hex')
  if (signature !== '89504e470d0a1a0a') {
    return { nonBlank: false, reason: 'not_png' }
  }
  let offset = 8
  let width = 0
  let height = 0
  let bitDepth = 0
  let colorType = 0
  const idatChunks = []
  while (offset + 12 <= buffer.length) {
    const length = buffer.readUInt32BE(offset)
    const type = buffer.subarray(offset + 4, offset + 8).toString('ascii')
    const data = buffer.subarray(offset + 8, offset + 8 + length)
    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      bitDepth = data[8]
      colorType = data[9]
    } else if (type === 'IDAT') {
      idatChunks.push(data)
    } else if (type === 'IEND') {
      break
    }
    offset += 12 + length
  }
  const bytesPerPixel = colorType === 6 ? 4 : colorType === 2 ? 3 : 0
  if (!width || !height || bitDepth !== 8 || !bytesPerPixel) {
    return { nonBlank: false, reason: 'unsupported_png_format', width, height, bitDepth, colorType }
  }
  const inflated = zlib.inflateSync(Buffer.concat(idatChunks))
  const stride = width * bytesPerPixel
  let sourceOffset = 0
  let previous = Buffer.alloc(stride)
  const current = Buffer.alloc(stride)
  let significantPixelCount = 0
  let minX = width
  let minY = height
  let maxX = -1
  let maxY = -1
  for (let y = 0; y < height; y += 1) {
    const filter = inflated[sourceOffset]
    sourceOffset += 1
    for (let xByte = 0; xByte < stride; xByte += 1) {
      const raw = inflated[sourceOffset + xByte]
      const left = xByte >= bytesPerPixel ? current[xByte - bytesPerPixel] : 0
      const up = previous[xByte]
      const upLeft = xByte >= bytesPerPixel ? previous[xByte - bytesPerPixel] : 0
      let value = raw
      if (filter === 1) value = raw + left
      else if (filter === 2) value = raw + up
      else if (filter === 3) value = raw + Math.floor((left + up) / 2)
      else if (filter === 4) value = raw + paethPredictor(left, up, upLeft)
      current[xByte] = value & 0xff
    }
    for (let x = 0; x < width; x += 1) {
      const base = x * bytesPerPixel
      const red = current[base]
      const green = current[base + 1]
      const blue = current[base + 2]
      const alpha = bytesPerPixel === 4 ? current[base + 3] : 255
      const maxChannel = Math.max(red, green, blue)
      const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722
      if (alpha > 0 && (maxChannel >= 44 || luminance >= 40)) {
        significantPixelCount += 1
        minX = Math.min(minX, x)
        minY = Math.min(minY, y)
        maxX = Math.max(maxX, x)
        maxY = Math.max(maxY, y)
      }
    }
    sourceOffset += stride
    previous = Buffer.from(current)
  }
  if (significantPixelCount <= 0) {
    return { nonBlank: false, reason: 'no_significant_pixels', width, height, significantPixelCount }
  }
  const bboxWidth = maxX - minX + 1
  const bboxHeight = maxY - minY + 1
  return {
    nonBlank: true,
    width,
    height,
    significantPixelCount,
    significantPixelRatio: significantPixelCount / (width * height),
    bbox: { minX, minY, maxX, maxY, width: bboxWidth, height: bboxHeight },
    coverageWidth: bboxWidth / width,
    coverageHeight: bboxHeight / height,
    bboxAspectRatio: bboxWidth / Math.max(1, bboxHeight),
    centerX: (minX + maxX + 1) / 2 / width,
    centerY: (minY + maxY + 1) / 2 / height,
  }
}

async function runBrowserChecks(extractRoot, screenshotPath) {
  const { chromium } = await import('@playwright/test')
  const server = createStaticServer(extractRoot)
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  const url = `http://127.0.0.1:${port}/viewer.html`
  const errors = []
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  await installCanvasFrameProbe(page)
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  try {
    await page.goto(url, { timeout: 90000, waitUntil: 'domcontentloaded' })
    await page.locator('#viewport').waitFor({ state: 'visible', timeout: 30000 })
    await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 60000 })
    await page.waitForFunction(() => {
      const loading = document.querySelector('#loading')
      return !loading || getComputedStyle(loading).display === 'none'
    }, { timeout: 45000 }).catch(() => undefined)
    await page.waitForTimeout(1000)
    let canvasProbeWait = { pass: true, reason: 'PASS' }
    try {
      await waitForCanvasNonBlank(page, {
        timeout: 3000,
        variedPixelThreshold: 8,
      })
    } catch (error) {
      canvasProbeWait = { pass: false, reason: String(error?.message || error) }
    }
    const canvasMetrics = await readCanvasFrameMetrics(page)
    const browserState = await page.evaluate(() => {
      const canvas = document.querySelector('#viewport canvas')
      const loading = document.querySelector('#loading')
      return {
        title: document.title,
        viewport_present: Boolean(document.querySelector('#viewport')),
        canvas_present: Boolean(canvas),
        canvas_width: canvas instanceof HTMLCanvasElement ? canvas.width : 0,
        canvas_height: canvas instanceof HTMLCanvasElement ? canvas.height : 0,
        loading_display: loading instanceof HTMLElement ? getComputedStyle(loading).display : '',
        loading_text: document.querySelector('#loading-message')?.textContent?.trim() || '',
        stats_text: document.querySelector('#stats-panel')?.textContent?.replace(/\s+/g, ' ').trim() || '',
        model_tree_text: document.querySelector('#model-tree')?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 160) || '',
        contour_button_present: Boolean(document.querySelector('#btn-contour')),
        render_mode_button_present: Boolean(document.querySelector('#btn-wireframe') || document.querySelector('[data-render-mode]')),
        scalar_select_present: Boolean(document.querySelector('#scalar-select')),
        footer_present: Boolean(document.querySelector('footer')),
      }
    })
    if (browserState.contour_button_present) {
      await page.locator('#btn-contour').click({ timeout: 10000 })
    }
    const canvasScreenshot = await page.locator('#viewport canvas').screenshot({ path: screenshotPath })
    const canvasScreenshotMetrics = analyzePngPixels(canvasScreenshot)
    const screenshotPass = (
      canvasScreenshotMetrics.nonBlank
      && (canvasScreenshotMetrics.significantPixelRatio || 0) >= 0.0002
      && (canvasScreenshotMetrics.coverageWidth || 0) >= 0.01
      && (canvasScreenshotMetrics.coverageHeight || 0) >= 0.01
    )
    return {
      pass: errors.length === 0 && screenshotPass,
      reason: errors.length === 0 && screenshotPass ? 'PASS' : 'browser_canvas_screenshot_or_console_failed',
      opened_url: url,
      viewport: { width: 1440, height: 1000 },
      screenshot_path: screenshotPath,
      browser_state: browserState,
      canvas_probe_wait: canvasProbeWait,
      canvas_metrics: canvasMetrics,
      canvas_screenshot_metrics: canvasScreenshotMetrics,
      errors,
    }
  } finally {
    await browser.close()
    await new Promise((resolve) => server.close(resolve))
  }
}

function buildPayload({ packagePath, extractRoot, staticChecks, browserChecks, browserSkipped }) {
  const blockers = [
    ...(!staticChecks.pass ? ['static_delivery_viewer_contract_failed'] : []),
    ...(staticChecks.commercial_cockpit_alignment.status !== 'current_cockpit_delivery'
      ? ['delivery_viewer_is_not_current_commercial_cockpit_source']
      : []),
    ...(!browserSkipped && !browserChecks.pass ? ['browser_delivery_viewer_open_failed'] : []),
  ]
  const warnings = [
    ...(browserSkipped ? ['browser_smoke_skipped_static_only'] : []),
  ]
  const contractPass = blockers.length === 0
  return {
    schema_version: 'workstation-delivery-viewer-smoke.v1',
    generated_at: nowIso(),
    contract_pass: contractPass,
    reason_code: contractPass ? 'PASS' : 'ERR_WORKSTATION_DELIVERY_VIEWER_SMOKE_BLOCKED',
    status: contractPass ? 'ready' : 'blocked',
    summary_line: (
      `Workstation delivery viewer smoke: ${contractPass ? 'PASS' : 'BLOCKED'} | `
      + `static=${staticChecks.pass} | browser=${browserSkipped ? 'skipped' : browserChecks.pass}`
    ),
    package_path: packagePath,
    extract_mode: 'temporary_zip_restore',
    static_checks: staticChecks,
    browser_checks: browserChecks,
    browser_skipped: browserSkipped,
    claim_boundary: CLAIM_BOUNDARY,
    warnings,
    blockers,
  }
}

async function main() {
  const args = parseArgs(process.argv)
  let extractRoot = ''
  let payload
  try {
    if (!existsSync(args.packagePath)) {
      throw new Error(`Package not found: ${args.packagePath}`)
    }
    extractRoot = extractZip(args.packagePath)
    const staticChecks = staticViewerChecks(extractRoot, args.packagePath)
    const browserChecks = args.staticOnly
      ? { pass: true, reason: 'SKIPPED_STATIC_ONLY' }
      : await runBrowserChecks(extractRoot, args.screenshotPath)
    payload = buildPayload({
      packagePath: path.relative(rootDir, args.packagePath),
      extractRoot,
      staticChecks,
      browserChecks,
      browserSkipped: args.staticOnly,
    })
  } catch (error) {
    payload = {
      schema_version: 'workstation-delivery-viewer-smoke.v1',
      generated_at: nowIso(),
      contract_pass: false,
      reason_code: 'ERR_WORKSTATION_DELIVERY_VIEWER_SMOKE_EXCEPTION',
      status: 'blocked',
      summary_line: 'Workstation delivery viewer smoke: BLOCKED | exception=true',
      package_path: path.relative(rootDir, args.packagePath),
      extract_mode: 'temporary_zip_restore',
      static_checks: {},
      browser_checks: {},
      browser_skipped: args.staticOnly,
      claim_boundary: CLAIM_BOUNDARY,
      warnings: [],
      blockers: [String(error?.message || error)],
    }
  } finally {
    if (extractRoot && !args.keepExtract) {
      rmSync(extractRoot, { recursive: true, force: true })
    }
  }

  mkdirSync(path.dirname(args.outPath), { recursive: true })
  writeFileSync(args.outPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
  console.log(args.json ? JSON.stringify(payload, null, 2) : payload.summary_line)
  if (args.failBlocked && !payload.contract_pass) {
    process.exitCode = 1
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
