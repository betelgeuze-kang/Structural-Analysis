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
    await page.waitForFunction(() => document.querySelectorAll('[data-critical-member-id]').length >= 2, {
      timeout: 30000,
    })

    const firstRow = page.locator('[data-critical-member-id]').nth(0)
    const secondRow = page.locator('[data-critical-member-id]').nth(1)
    const firstMember = await firstRow.getAttribute('data-critical-member-id')
    const secondMember = await secondRow.getAttribute('data-critical-member-id')
    if (!firstMember || !secondMember || firstMember === secondMember) {
      throw new Error(`Expected two unique critical members, got first=${firstMember} second=${secondMember}`)
    }

    await firstRow.click({ timeout: 10000 })
    await secondRow.click({ modifiers: ['Control'], timeout: 10000 })

    try {
      await page.waitForFunction((expected) => {
        const rows = [...document.querySelectorAll('[data-critical-member-id]')]
        const first = rows.find((row) => row.getAttribute('data-critical-member-id') === expected.firstMember)
        const second = rows.find((row) => row.getAttribute('data-critical-member-id') === expected.secondMember)
        const badge = document.querySelector('[data-viewport-selection-focus-badge]')
        const selectionRaw = localStorage.getItem('structural-viewer-selection-v1') || '{}'
        let selection = {}
        try {
          selection = JSON.parse(selectionRaw)
        } catch (_error) {
          selection = {}
        }
        const params = new URLSearchParams(window.location.search)
        const memberSet = params.get('member_set') || ''
        return Boolean(
          first?.getAttribute('aria-selected') === 'true'
          && second?.getAttribute('aria-selected') === 'true'
          && second.classList.contains('is-primary')
          && badge?.classList.contains('is-visible')
          && badge.getAttribute('data-viewport-selection-focus-count') === '2'
          && badge.getAttribute('data-viewport-selection-focus-member') === expected.secondMember
          && badge.getAttribute('data-viewport-selection-focus-edge')
          && badge.textContent.includes('2 members selected')
          && Array.isArray(selection.memberIds)
          && selection.memberIds.includes(expected.firstMember)
          && selection.memberIds.includes(expected.secondMember)
          && selection.selectionSetCount === 2
          && memberSet.includes(expected.firstMember)
          && memberSet.includes(expected.secondMember)
        )
      }, { firstMember, secondMember }, { timeout: 10000 })
    } catch (error) {
      const state = await page.evaluate((expected) => {
        const rows = [...document.querySelectorAll('[data-critical-member-id]')]
        const first = rows.find((row) => row.getAttribute('data-critical-member-id') === expected.firstMember)
        const second = rows.find((row) => row.getAttribute('data-critical-member-id') === expected.secondMember)
        const badge = document.querySelector('[data-viewport-selection-focus-badge]')
        const selectionRaw = localStorage.getItem('structural-viewer-selection-v1') || '{}'
        return {
          expected,
          firstSelected: first?.getAttribute('aria-selected') || '',
          firstClass: first?.className || '',
          secondSelected: second?.getAttribute('aria-selected') || '',
          secondClass: second?.className || '',
          badgeClass: badge?.className || '',
          badgeMember: badge?.getAttribute('data-viewport-selection-focus-member') || '',
          badgeCount: badge?.getAttribute('data-viewport-selection-focus-count') || '',
          badgeEdge: badge?.getAttribute('data-viewport-selection-focus-edge') || '',
          badgeText: badge?.textContent?.replace(/\s+/g, ' ').trim() || '',
          search: window.location.search,
          selectionRaw,
        }
      }, { firstMember, secondMember })
      state.errors = errors
      throw new Error(`${error.message}\n${JSON.stringify(state, null, 2)}`)
    }

    if (errors.length > 0) {
      throw new Error(`Viewer console/page errors while verifying multi-selection HUD:\n${errors.join('\n')}`)
    }

    console.log(`Multi-selection viewport HUD: PASS | members=${firstMember},${secondMember}`)
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
