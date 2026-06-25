import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// Serves the Structural Workbench prototype directory and runs its Playwright
// smoke spec. Serving the prototype folder as root keeps ./demo-case.json and
// ./styles/* resolving the same way as static hosting.

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const serveRoot = path.join(repoRoot, 'prototype', 'structural-workbench')
const specRelative = 'tests/frontend/workbench-prototype-smoke.spec.ts'
const passthroughArgs = process.argv.slice(2)

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
}

function sendText(response, status, text) {
  const body = Buffer.from(text)
  response.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', 'Content-Length': String(body.length) })
  response.end(body)
}

function createStaticServer() {
  return http.createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1')
    const decodedPath = decodeURIComponent(requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname)
    const target = path.resolve(serveRoot, `.${decodedPath}`)
    if (!target.startsWith(serveRoot)) {
      sendText(response, 403, 'Forbidden')
      return
    }
    if (!existsSync(target) || !statSync(target).isFile()) {
      sendText(response, 404, 'Not found')
      return
    }
    response.writeHead(200, { 'Content-Type': mimeTypes[path.extname(target)] || 'application/octet-stream' })
    createReadStream(target).pipe(response)
  })
}

function runPlaywright(playwrightBin, port) {
  return new Promise((resolve) => {
    const child = spawn(playwrightBin, ['test', specRelative, '--reporter=line', ...passthroughArgs], {
      cwd: repoRoot,
      stdio: 'inherit',
      env: { ...process.env, WORKBENCH_PROTOTYPE_BASE_URL: `http://127.0.0.1:${port}` },
    })
    child.on('error', () => resolve(1))
    child.on('close', (code) => resolve(code ?? 1))
  })
}

async function main() {
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  const playwrightBin = path.join(
    repoRoot,
    'node_modules',
    '.bin',
    process.platform === 'win32' ? 'playwright.cmd' : 'playwright',
  )
  try {
    process.exitCode = await runPlaywright(playwrightBin, port)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
