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
    const memberId = await criticalCallout.getAttribute('data-stage-callout-focus-member')
    if (!memberId) throw new Error('Stage critical callout did not expose data-stage-callout-focus-member.')

    await criticalCallout.click({ timeout: 10000 })
    const tableRow = page.locator(`[data-critical-member-id="${memberId}"]`).first()
    await tableRow.waitFor({ state: 'visible', timeout: 10000 })
    try {
      await page.waitForFunction((id) => {
        const row = document.querySelector(`[data-critical-member-id="${id}"]`)
        const callout = document.querySelector(`[data-stage-callout-focus-member="${id}"]`)
        const badge = document.querySelector('[data-viewport-selection-focus-badge]')
        return Boolean(
          row?.classList.contains('is-selected')
          && row.getAttribute('aria-selected') === 'true'
          && callout?.classList.contains('is-selected')
          && callout.getAttribute('aria-pressed') === 'true'
          && badge?.classList.contains('is-visible')
          && badge.getAttribute('data-viewport-selection-focus-member') === id
          && badge.textContent.includes(id)
        )
      }, memberId, { timeout: 10000 })
    } catch (error) {
      const focusState = await page.evaluate((id) => {
        const row = document.querySelector(`[data-critical-member-id="${id}"]`)
        const callout = document.querySelector(`[data-stage-callout-focus-member="${id}"]`)
        const badge = document.querySelector('[data-viewport-selection-focus-badge]')
        return {
          memberId: id,
          rowClass: row?.className || '',
          rowSelected: row?.getAttribute('aria-selected') || '',
          calloutClass: callout?.className || '',
          calloutPressed: callout?.getAttribute('aria-pressed') || '',
          badgeClass: badge?.className || '',
          badgeMember: badge?.getAttribute('data-viewport-selection-focus-member') || '',
          badgeText: badge?.textContent?.trim() || '',
          badgeStyle: badge instanceof HTMLElement ? { left: badge.style.left, top: badge.style.top } : {},
          propertyText: document.querySelector('#prop-panel')?.textContent?.replace(/\s+/g, ' ').trim() || '',
        }
      }, memberId)
      focusState.errors = errors
      throw new Error(`${error.message}\n${JSON.stringify(focusState, null, 2)}`)
    }

    if (errors.length > 0) {
      throw new Error(`Viewer console/page errors while verifying critical callout focus:\n${errors.join('\n')}`)
    }

    console.log(`Critical member callout focus: PASS | member=${memberId}`)
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
