import { createReadStream, existsSync, statSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function readArg(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || fallback : fallback
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
  const mimeTypes = {
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
  }
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

async function main() {
  const out = readArg('--out', 'structure_viewer_report.pdf')
  const htmlOut = readArg('--html-out', '')
  const query = readArg('--query', 'project=midas33_release&drawing=midas33_optimized&variant=optimized')
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  const browser = await chromium.launch()
  try {
    const viewerPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await viewerPage.goto(`http://127.0.0.1:${port}/src/structure-viewer/index.html?${query}`, {
      waitUntil: 'commit',
      timeout: 90000,
    })
    await viewerPage.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
    await viewerPage.waitForFunction(() => typeof window.buildCurrentStructureViewerReportHtml === 'function')
    const report = await viewerPage.evaluate(() => window.buildCurrentStructureViewerReportHtml())
    if (htmlOut) {
      writeFileSync(htmlOut, report.html, 'utf8')
    }
    const reportPage = await browser.newPage()
    await reportPage.setContent(report.html, { waitUntil: 'load' })
    await reportPage.pdf({
      path: out,
      format: 'A4',
      printBackground: true,
      margin: { top: '18mm', right: '14mm', bottom: '18mm', left: '14mm' },
    })
    console.log(out)
  } finally {
    await browser.close()
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
