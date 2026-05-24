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

    const sheetButtons = page.locator('[data-drawing-handoff-sheet]')
    await page.waitForFunction(() => document.querySelectorAll('[data-drawing-handoff-sheet]').length >= 2, {
      timeout: 10000,
    })
    const targetSheet = sheetButtons.nth(1)
    const targetData = await targetSheet.evaluate((sheet) => ({
      sheetName: sheet.getAttribute('data-drawing-handoff-sheet') || '',
      callout: sheet.getAttribute('data-drawing-handoff-sheet-callout') || '',
      href: sheet.getAttribute('data-drawing-handoff-sheet-href') || '',
    }))
    if (!targetData.sheetName) throw new Error('Drawing handoff sheet button did not expose a sheet name.')
    if (!targetData.href) throw new Error(`Drawing handoff sheet ${targetData.sheetName} did not expose an SVG href.`)

    await targetSheet.hover({ timeout: 10000 })
    try {
      await page.waitForFunction((expected) => {
        const preview = document.querySelector('[data-drawing-handoff-preview]')
        const activeOpen = document.querySelector('[data-drawing-handoff-active-sheet-open]')
        const sheet = [...document.querySelectorAll('[data-drawing-handoff-sheet]')]
          .find((entry) => entry.getAttribute('data-drawing-handoff-sheet') === expected.sheetName)
        return Boolean(
          preview?.getAttribute('data-drawing-handoff-preview-sheet') === expected.sheetName
          && preview.getAttribute('data-drawing-handoff-preview-callout') === expected.callout
          && preview.getAttribute('aria-disabled') === 'false'
          && activeOpen?.getAttribute('data-drawing-handoff-active-sheet-name') === expected.sheetName
          && activeOpen.getAttribute('aria-disabled') === 'false'
          && activeOpen.getAttribute('href')?.includes(expected.href)
          && sheet?.classList.contains('is-active')
          && sheet.getAttribute('aria-current') === 'true'
        )
      }, targetData, { timeout: 10000 })
    } catch (error) {
      const state = await page.evaluate((expected) => {
        const preview = document.querySelector('[data-drawing-handoff-preview]')
        const activeOpen = document.querySelector('[data-drawing-handoff-active-sheet-open]')
        const sheet = [...document.querySelectorAll('[data-drawing-handoff-sheet]')]
          .find((entry) => entry.getAttribute('data-drawing-handoff-sheet') === expected.sheetName)
        return {
          expected,
          previewSheet: preview?.getAttribute('data-drawing-handoff-preview-sheet') || '',
          previewCallout: preview?.getAttribute('data-drawing-handoff-preview-callout') || '',
          previewDisabled: preview?.getAttribute('aria-disabled') || '',
          activeOpenName: activeOpen?.getAttribute('data-drawing-handoff-active-sheet-name') || '',
          activeOpenHref: activeOpen?.getAttribute('href') || '',
          activeOpenDisabled: activeOpen?.getAttribute('aria-disabled') || '',
          sheetClass: sheet?.className || '',
          sheetCurrent: sheet?.getAttribute('aria-current') || '',
          panelText: document.querySelector('[data-drawing-handoff-panel]')?.textContent?.replace(/\s+/g, ' ').trim() || '',
        }
      }, targetData)
      state.errors = errors
      throw new Error(`${error.message}\n${JSON.stringify(state, null, 2)}`)
    }

    if (errors.length > 0) {
      throw new Error(`Viewer console/page errors while verifying drawing handoff preview:\n${errors.join('\n')}`)
    }

    console.log(`Drawing handoff preview interaction: PASS | sheet=${targetData.sheetName}`)
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
