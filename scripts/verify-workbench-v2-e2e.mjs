import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// Builds the app (Vite) and serves dist/, then runs the Workbench v2 E2E spec.
// SPA: unknown paths fall back to index.html (the route uses a hash, so this is
// mostly a safety net). Extra args are forwarded to Playwright.

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const distDir = path.join(rootDir, 'dist')
const spec = 'tests/frontend/workbench-v2-e2e.spec.ts'
const passthrough = process.argv.slice(2)

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

function run(cmd, args, env) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd: rootDir, stdio: 'inherit', env: { ...process.env, ...env } })
    child.on('error', () => resolve(1))
    child.on('close', (code) => resolve(code ?? 1))
  })
}

function serveDist() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://127.0.0.1')
    let target = path.resolve(distDir, `.${decodeURIComponent(url.pathname)}`)
    if (!target.startsWith(distDir)) {
      res.writeHead(403).end('Forbidden')
      return
    }
    if (!existsSync(target) || !statSync(target).isFile()) {
      target = path.join(distDir, 'index.html') // SPA fallback
    }
    if (!existsSync(target)) {
      res.writeHead(404).end('Not found')
      return
    }
    res.writeHead(200, { 'Content-Type': mime[path.extname(target)] || 'application/octet-stream' })
    createReadStream(target).pipe(res)
  })
  return server
}

async function main() {
  // Build with base '/' for local serving.
  const buildCode = await run('npm', ['run', 'build'], { VITE_BASE_PATH: '/' })
  if (buildCode !== 0) {
    process.exitCode = buildCode
    return
  }

  const server = serveDist()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  const playwrightBin = path.join(rootDir, 'node_modules', '.bin', process.platform === 'win32' ? 'playwright.cmd' : 'playwright')
  try {
    process.exitCode = await run(playwrightBin, ['test', spec, '--reporter=line', ...passthrough], {
      WORKBENCH_V2_BASE_URL: `http://127.0.0.1:${port}`,
    })
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
