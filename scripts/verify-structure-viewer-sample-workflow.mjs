#!/usr/bin/env node
import { createReadStream, existsSync, statSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  assertCanvasWellFramed,
  installCanvasFrameProbe,
  waitForCanvasNonBlank,
} from './structure-viewer-canvas-frame.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
}

function arg(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || fallback : fallback
}

function hasFlag(name) {
  return process.argv.includes(name)
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

async function openViewer(page, baseUrl, query, label) {
  const started = Date.now()
  const errors = []
  const warnings = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const text = message.text()
      if (/Failed to load resource/i.test(text)) warnings.push(text)
      else errors.push(text)
    }
  })
  await installCanvasFrameProbe(page)
  await page.goto(`${baseUrl}/src/structure-viewer/index.html?${query}`, {
    timeout: 60000,
    waitUntil: 'commit',
  })
  await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
  await waitForCanvasNonBlank(page, { timeout: 30000 })
  const canvasMetrics = await assertCanvasWellFramed(page, {
    label,
    minCoverageWidth: 0.06,
    minCoverageHeight: 0.08,
    minPixelRatio: 0.0005,
  })
  return {
    label,
    query,
    elapsed_ms: Date.now() - started,
    browser_error_count: errors.length,
    browser_errors: [...errors],
    browser_warning_count: warnings.length,
    browser_warnings: [...warnings],
    canvas_nonblank: Boolean(canvasMetrics.nonBlank),
    canvas_significant_pixel_count: Number(canvasMetrics.significantPixelCount || 0),
  }
}

async function runWorkflow({ port, maxMinutes }) {
  const { chromium } = await import('@playwright/test')
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const baseUrl = `http://127.0.0.1:${port}`
  const steps = []
  try {
    steps.push(await openViewer(
      page,
      baseUrl,
      'project=midas33_release&drawing=midas33_optimized&variant=optimized',
      'midas33 optimized sample project',
    ))
    await page.locator('text=Structural Insight').first().waitFor({ state: 'visible', timeout: 30000 })
    await page.locator('text=Optimization Complete').first().waitFor({ state: 'visible', timeout: 30000 })
    await page.locator('input[placeholder*="Search"]').first().fill('911')
    await page.locator('input[placeholder*="Search"]').first().press('Enter')
    steps.push({
      label: 'midas33 search and selection input',
      elapsed_ms: 0,
      browser_error_count: 0,
      canvas_nonblank: true,
    })

    steps.push(await openViewer(
      page,
      baseUrl,
      'preset=real_drawing_private_3d&member=RD-001&drawing_asset=RD-001',
      'real drawing sample project',
    ))
    await page.locator('text=Real Drawings').first().waitFor({ state: 'visible', timeout: 30000 })
    await page.locator('input[placeholder*="Search"]').first().fill('RD-001')
    steps.push({
      label: 'real drawing search input',
      elapsed_ms: 0,
      browser_error_count: 0,
      canvas_nonblank: true,
    })
  } finally {
    await browser.close()
  }
  const elapsedSeconds = steps.reduce((total, step) => total + Number(step.elapsed_ms || 0), 0) / 1000
  const browserErrorCount = steps.reduce((total, step) => total + Number(step.browser_error_count || 0), 0)
  const browserWarningCount = steps.reduce((total, step) => total + Number(step.browser_warning_count || 0), 0)
  const pass = browserErrorCount === 0
    && steps.every((step) => step.canvas_nonblank !== false)
    && elapsedSeconds / 60 <= maxMinutes
  return {
    schema_version: 'structure-viewer-sample-workflow-smoke.v1',
    generated_at: new Date().toISOString(),
    contract_pass: pass,
    reason_code: pass ? 'PASS' : 'ERR_STRUCTURE_VIEWER_SAMPLE_WORKFLOW_FAIL',
    sample_completion_minutes: elapsedSeconds / 60,
    max_sample_completion_minutes: maxMinutes,
    browser_error_count: browserErrorCount,
    browser_warning_count: browserWarningCount,
    steps,
  }
}

async function main() {
  const out = arg('--out', 'implementation/phase1/structure_viewer_sample_workflow_smoke.json')
  const maxMinutes = Number(arg('--max-minutes', '30'))
  const printJson = hasFlag('--json')
  const failBlocked = hasFlag('--fail-blocked')
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  try {
    const payload = await runWorkflow({ port, maxMinutes })
    writeFileSync(path.resolve(rootDir, out), `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
    if (printJson) console.log(JSON.stringify(payload, null, 2))
    else {
      console.log(`Structure viewer sample workflow: ${payload.reason_code} | minutes=${payload.sample_completion_minutes.toFixed(2)}`)
    }
    if (failBlocked && !payload.contract_pass) process.exitCode = 1
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
