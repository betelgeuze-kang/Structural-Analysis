import { createHash } from 'node:crypto'
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  assertCanvasWellFramed,
  installCanvasFrameProbe,
  readCanvasFrameMetrics,
  waitForCanvasNonBlank,
} from './structure-viewer-canvas-frame.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const schemaVersion = 'structure-viewer-browser-performance-probe.v1'

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.ts': 'text/plain; charset=utf-8',
}

function readArg(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || fallback : fallback
}

function hasFlag(name) {
  return process.argv.includes(name)
}

function numberArg(name, fallback) {
  const value = Number(readArg(name, String(fallback)))
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Invalid ${name} value: ${value}`)
  }
  return value
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

function sha256Path(relativePath) {
  const absolutePath = path.join(rootDir, relativePath)
  if (!existsSync(absolutePath)) return ''
  return createHash('sha256').update(readFileSync(absolutePath)).digest('hex')
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

async function sampleRaf(page, sampleMs) {
  return page.evaluate(async ({ sampleMs: durationMs }) => new Promise((resolve) => {
    const frames = []
    const startedAt = performance.now()
    function step(now) {
      frames.push(now)
      if (now - startedAt >= durationMs) {
        const intervals = frames.slice(1).map((value, index) => value - frames[index])
        const elapsedMs = Math.max(1, frames[frames.length - 1] - frames[0])
        resolve({
          frameCount: frames.length,
          elapsedMs,
          averageFps: intervals.length ? (intervals.length * 1000) / elapsedMs : 0,
          averageFrameMs: intervals.length
            ? intervals.reduce((total, value) => total + value, 0) / intervals.length
            : 0,
          p95FrameMs: intervals.length
            ? [...intervals].sort((left, right) => left - right)[Math.ceil(intervals.length * 0.95) - 1]
            : 0,
          maxFrameMs: intervals.length ? Math.max(...intervals) : 0,
        })
        return
      }
      requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }), { sampleMs })
}

async function runBrowserProbe({ port, query, sampleMs, viewport, maxReadyMs }) {
  const { chromium } = await import('@playwright/test')
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport })
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text())
  })

  try {
    await installCanvasFrameProbe(page)
    const startedAtEpochMs = Date.now()
    const url = `http://127.0.0.1:${port}/src/structure-viewer/index.html?${query}`
    await page.goto(url, { timeout: maxReadyMs, waitUntil: 'commit' })
    await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: maxReadyMs })
    await waitForCanvasNonBlank(page, { timeout: maxReadyMs })
    const canvasMetrics = await assertCanvasWellFramed(page, {
      label: 'structure viewer performance probe canvas',
      minCoverageWidth: 0.08,
      minCoverageHeight: 0.1,
      minPixelRatio: 0.001,
    })
    const readyMs = Date.now() - startedAtEpochMs
    const rafSample = await sampleRaf(page, sampleMs)
    const navigationTiming = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')?.[0]
      return nav
        ? {
            domContentLoadedMs: nav.domContentLoadedEventEnd,
            loadEventEndMs: nav.loadEventEnd,
            responseEndMs: nav.responseEnd,
          }
        : {}
    })
    const viewerState = await page.evaluate(() => ({
      title: document.title,
      stageVariant: document.querySelector('#stage-variant-chip')?.textContent?.trim() || '',
      projectStatus: document.querySelector('#project-workspace-status')?.textContent?.trim() || '',
      statsText: document.querySelector('#stats-panel')?.textContent?.trim().slice(0, 400) || '',
    }))
    return {
      url,
      readyMs,
      viewport,
      canvasMetrics,
      rafSample,
      navigationTiming,
      viewerState,
      browserErrors,
    }
  } finally {
    await browser.close()
  }
}

function buildPayload({
  query,
  out,
  sampleMs,
  maxReadyMs,
  minAverageFps,
  probe,
  error = '',
}) {
  const measured = Boolean(probe && !error)
  const blockers = [
    ...(error ? [`browser_probe_failed:${error}`] : []),
    ...(probe?.browserErrors?.length ? ['browser_console_errors_present'] : []),
    ...(measured && probe.readyMs > maxReadyMs ? ['viewer_ready_budget_exceeded'] : []),
    ...(measured && probe.rafSample.averageFps < minAverageFps ? ['viewer_average_fps_below_budget'] : []),
    ...(measured && !probe.canvasMetrics?.nonBlank ? ['viewer_canvas_blank'] : []),
  ]
  const pass = blockers.length === 0
  return {
    schema_version: schemaVersion,
    generated_at: new Date().toISOString(),
    contract_pass: pass,
    reason_code: pass ? 'PASS' : 'ERR_STRUCTURE_VIEWER_BROWSER_PERFORMANCE_PENDING',
    summary_line: pass
      ? `Structure viewer browser performance probe: PASS | ready=${probe.readyMs}ms | fps=${probe.rafSample.averageFps.toFixed(1)} | mode=local_browser_probe`
      : `Structure viewer browser performance probe: BLOCKED | blockers=${blockers.length} | mode=local_browser_probe`,
    probe_mode: 'local_browser_probe',
    measured_browser_probe: measured,
    live_performance_claim: false,
    independent_product_claim: false,
    claim_boundary: 'Local browser performance smoke only; not a normalized customer hardware FPS claim.',
    query,
    output_path: out,
    budgets: {
      max_ready_ms: maxReadyMs,
      min_average_fps: minAverageFps,
      sample_ms: sampleMs,
    },
    probe: probe || {},
    source_rows: [
      sourceRow('src/structure-viewer/index.html', 'viewer_index'),
      sourceRow('scripts/measure-structure-viewer-performance.mjs', 'browser_performance_probe'),
      sourceRow('scripts/structure-viewer-canvas-frame.mjs', 'canvas_frame_probe'),
      sourceRow('tests/frontend/structure-viewer-smoke.spec.ts', 'frontend_smoke_spec'),
    ],
    residual_live_work: [
      'Run the same probe across a defined browser/device/GPU matrix.',
      'Promote customer-hardware FPS and interaction latency budgets only after repeatable lab baselines exist.',
      'Attach screenshot visual regression baselines for the same query and view modes.',
    ],
    blockers,
  }
}

async function main() {
  const query = readArg('--query', 'project=midas33_release&drawing=midas33_optimized&variant=optimized')
  const verifyMode = hasFlag('--verify')
  const defaultOut = verifyMode
    ? path.join(os.tmpdir(), 'structure_viewer_browser_performance_probe.json')
    : 'implementation/phase1/structure_viewer_browser_performance_probe.json'
  const out = readArg('--out', defaultOut)
  const sampleMs = numberArg('--sample-ms', 1500)
  const maxReadyMs = numberArg('--max-ready-ms', 60000)
  const minAverageFps = numberArg('--min-fps', 5)
  const failBlocked = hasFlag('--fail-blocked')
  const dryRun = hasFlag('--dry-run')
  const viewport = {
    width: Number(readArg('--width', '1440')),
    height: Number(readArg('--height', '1000')),
  }
  const command = [
    process.execPath,
    'scripts/measure-structure-viewer-performance.mjs',
    ...(verifyMode ? ['--verify'] : []),
    '--query',
    query,
    '--out',
    out,
    '--sample-ms',
    String(sampleMs),
    '--max-ready-ms',
    String(maxReadyMs),
    '--min-fps',
    String(minAverageFps),
    '--width',
    String(viewport.width),
    '--height',
    String(viewport.height),
  ]
  if (dryRun) {
    console.log(command.join(' '))
    return
  }

  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  let payload
  try {
    const probe = await runBrowserProbe({ port, query, sampleMs, viewport, maxReadyMs })
    payload = buildPayload({ query, out, sampleMs, maxReadyMs, minAverageFps, probe })
  } catch (error) {
    payload = buildPayload({
      query,
      out,
      sampleMs,
      maxReadyMs,
      minAverageFps,
      probe: null,
      error: error?.message || String(error),
    })
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
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
