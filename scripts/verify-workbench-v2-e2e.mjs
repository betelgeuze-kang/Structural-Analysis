import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import {
  sanitizedFrontendEnvironment,
  trustedNode,
  trustedRepoTool,
} from './trusted-frontend-runtime.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const distDir = path.join(rootDir, 'dist')
const jsonLoader = pathToFileURL(path.join(rootDir, 'scripts', 'json-module-loader.mjs')).href
const specs = [
  'tests/frontend/workbench-v2-e2e.spec.ts',
  'tests/frontend/workbench-v2-import-health.spec.ts',
  'tests/frontend/workbench-v2-unit-coordinate-guard.spec.ts',
  'tests/frontend/workbench-v2-live-provider-guard.spec.ts',
  'tests/frontend/workbench-v2-job-contract.spec.ts',
  'tests/frontend/workbench-v2-native-frame-contract.spec.ts',
  'tests/frontend/workbench-v2-engineering-value-state.spec.ts',
  'tests/frontend/workbench-v2-status-taxonomy.spec.ts',
]
const passthrough = process.argv.slice(2)

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

function run(node, args, env) {
  return new Promise((resolve) => {
    const child = spawn(node, args, { cwd: rootDir, stdio: 'inherit', env })
    child.on('error', () => resolve(1))
    child.on('close', (code) => resolve(code ?? 1))
  })
}

function serveDist() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://127.0.0.1')
    let target = path.resolve(distDir, `.${decodeURIComponent(url.pathname)}`)
    if (target !== distDir && !target.startsWith(`${distDir}${path.sep}`)) {
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
  const node = trustedNode()
  const typescript = trustedRepoTool(rootDir, 'node_modules/typescript/bin/tsc', 'typescript_cli')
  const vite = trustedRepoTool(rootDir, 'node_modules/vite/bin/vite.js', 'vite_cli')
  const delivery = trustedRepoTool(
    rootDir,
    'scripts/verify-workbench-viewer-delivery.mjs',
    'viewer_delivery_contract',
  )
  const playwright = trustedRepoTool(rootDir, 'node_modules/playwright/cli.js', 'playwright_cli')
  // Build with base '/' for local serving.
  for (const [args, extraEnvironment] of [
    [[typescript, '--noEmit'], {}],
    [[vite, 'build'], { VITE_BASE_PATH: '/' }],
    [[delivery], {}],
  ]) {
    const buildCode = await run(
      node,
      args,
      sanitizedFrontendEnvironment(node, extraEnvironment),
    )
    if (buildCode !== 0) {
      process.exitCode = buildCode
      return
    }
  }

  const server = serveDist()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  try {
    const loaderOption = `--loader=${jsonLoader}`
    process.exitCode = await run(
      node,
      [loaderOption, playwright, 'test', ...specs, '--reporter=line', ...passthrough],
      sanitizedFrontendEnvironment(node, {
        WORKBENCH_V2_BASE_URL: `http://127.0.0.1:${port}`,
      }),
    )
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
