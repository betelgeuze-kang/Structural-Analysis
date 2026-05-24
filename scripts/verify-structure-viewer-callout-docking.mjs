import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from '@playwright/test'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const viewerPath = '/src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized'

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml; charset=utf-8',
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

async function verify(port) {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  try {
    await page.goto(`http://127.0.0.1:${port}${viewerPath}`, { timeout: 90000, waitUntil: 'commit' })
    await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
    const criticalCallout = page.locator('[data-stage-callout-focus-member]').first()
    await criticalCallout.waitFor({ state: 'visible', timeout: 30000 })
    await criticalCallout.click({ timeout: 10000 })

    await page.waitForFunction(() => {
      const badge = document.querySelector('[data-viewport-selection-focus-badge]')
      return Boolean(badge?.classList.contains('is-visible'))
    }, { timeout: 10000 })

    const state = await page.evaluate(() => {
      const panel = document.querySelector('[data-stage-result-callouts]')
      const badge = document.querySelector('[data-viewport-selection-focus-badge]')
      const viewport = document.querySelector('#viewport')
      if (!(panel instanceof HTMLElement) || !(badge instanceof HTMLElement) || !(viewport instanceof HTMLElement)) {
        return { ok: false, reason: 'missing required viewport nodes' }
      }
      const viewportWidth = viewport.clientWidth || 900
      badge.style.left = `${Math.max(220, viewportWidth - 124)}px`
      badge.style.top = '74px'
      badge.classList.add('is-visible')
      window.positionStageResultCalloutDock?.()
      const panelRect = panel.getBoundingClientRect()
      const badgeRect = badge.getBoundingClientRect()
      const overlapLeft = Math.max(panelRect.left, badgeRect.left - 8)
      const overlapRight = Math.min(panelRect.right, badgeRect.right + 8)
      const overlapTop = Math.max(panelRect.top, badgeRect.top - 8)
      const overlapBottom = Math.min(panelRect.bottom, badgeRect.bottom + 8)
      const overlapArea = Math.max(0, overlapRight - overlapLeft) * Math.max(0, overlapBottom - overlapTop)
      return {
        ok: overlapArea === 0,
        dock: panel.getAttribute('data-stage-callout-dock') || '',
        overlapState: panel.getAttribute('data-stage-callout-overlap') || '',
        overlapArea,
        panelRect: {
          left: Math.round(panelRect.left),
          top: Math.round(panelRect.top),
          right: Math.round(panelRect.right),
          bottom: Math.round(panelRect.bottom),
        },
        badgeRect: {
          left: Math.round(badgeRect.left),
          top: Math.round(badgeRect.top),
          right: Math.round(badgeRect.right),
          bottom: Math.round(badgeRect.bottom),
        },
      }
    })

    if (!state.ok || state.overlapState !== 'clear') {
      state.errors = errors
      throw new Error(`Stage result callouts still overlap selection HUD.\n${JSON.stringify(state, null, 2)}`)
    }

    if (errors.length > 0) {
      throw new Error(`Viewer console/page errors while verifying callout docking:\n${errors.join('\n')}`)
    }

    console.log(`Stage callout docking: PASS | dock=${state.dock}`)
  } finally {
    await browser.close()
  }
}

async function main() {
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  try {
    await verify(port)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
