import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const distDir = path.join(rootDir, 'dist')
const jsonLoader = pathToFileURL(path.join(rootDir, 'scripts', 'json-module-loader.mjs')).href
const spec = 'tests/frontend/workbench-v2-product-replay.spec.ts'

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

function run(cmd, args, env = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: rootDir,
      stdio: 'inherit',
      env: { ...process.env, ...env },
    })
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
      target = path.join(distDir, 'index.html')
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
  if (!process.env.WORKBENCH_PRODUCT_REPLAY_CASE || !process.env.WORKBENCH_PRODUCT_REPLAY_RECEIPT) {
    throw new Error('WORKBENCH_PRODUCT_REPLAY_CASE and WORKBENCH_PRODUCT_REPLAY_RECEIPT are required')
  }
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
  const playwrightBin = path.join(
    rootDir,
    'node_modules',
    '.bin',
    process.platform === 'win32' ? 'playwright.cmd' : 'playwright',
  )
  const existingOptions = process.env.NODE_OPTIONS?.trim()
  const loaderOption = `--loader=${jsonLoader}`
  try {
    process.exitCode = await run(
      playwrightBin,
      ['test', spec, '--reporter=line'],
      {
        WORKBENCH_V2_BASE_URL: `http://127.0.0.1:${port}`,
        NODE_OPTIONS: existingOptions ? `${existingOptions} ${loaderOption}` : loaderOption,
      },
    )
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
