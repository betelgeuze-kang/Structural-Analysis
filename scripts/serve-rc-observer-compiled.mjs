import http from 'node:http'
import { createHash } from 'node:crypto'
import { existsSync, lstatSync, realpathSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const maxFiles = 64
const maxBytes = 64 * 1024 * 1024
const maxManifestBytes = 128 * 1024
const closeMilliseconds = 10000
const hash = bytes => createHash('sha256').update(bytes).digest('hex')
const count = value => Math.min(value + 1, 1000000)
const validRelative = relative => typeof relative === 'string' && /^[A-Za-z0-9._/-]+$/.test(relative)
  && relative.split('/').every(part => part && part !== '.' && part !== '..'
    && part !== '.env' && !part.startsWith('.env.') && !part.endsWith('.env') && !part.includes('.env.'))

function canonical(file, directory = false) {
  const stat = lstatSync(file)
  if (stat.isSymbolicLink() || realpathSync(file) !== file
    || !(directory ? stat.isDirectory() : stat.isFile())) throw new Error('rc_observer_compiled_input_not_canonical')
  return stat
}

function ownedDirectory(directory) {
  const temporary = os.tmpdir()
  if (typeof directory !== 'string' || !path.isAbsolute(directory) || !path.isAbsolute(temporary)
    || path.dirname(directory) !== temporary
    || !/^rc-observer-controls-[1-9][0-9]*-[1-9][0-9]*$/.test(path.basename(directory))) {
    throw new Error('rc_observer_owned_directory_invalid')
  }
  canonical(temporary, true)
  canonical(directory, true)
  return directory
}

// The controlled caller creates the exclusive directory and owns this factory's listener.
// Importing this module starts no listener and installs no process-wide signal handlers.
export async function startRcObserverCompiled({ directory, manifestSha256 }) {
  ownedDirectory(directory)
  if (!/^[a-f0-9]{64}$/.test(manifestSha256 ?? '')) throw new Error('rc_observer_manifest_sha_invalid')
  const root = path.join(directory, 'compiled')
  const manifestPath = path.join(directory, 'compiled-manifest.json')
  const startPath = path.join(directory, 'listener-start.json')
  const cleanupPath = path.join(directory, 'listener-cleanup.json')
  if (existsSync(startPath) || existsSync(cleanupPath)) throw new Error('rc_observer_new_listener_receipts_required')
  canonical(root, true)
  const manifestStat = canonical(manifestPath)
  if (manifestStat.size > maxManifestBytes) throw new Error('rc_observer_manifest_oversize')
  const manifestBytes = readFileSync(manifestPath)
  if (manifestBytes.length !== manifestStat.size || manifestBytes.length > maxManifestBytes
    || hash(manifestBytes) !== manifestSha256) throw new Error('rc_observer_manifest_pin_mismatch')
  const manifest = JSON.parse(manifestBytes.toString('utf8'))
  if (manifest.schema !== 1 || !Array.isArray(manifest.files)
    || manifest.files.length < 1 || manifest.files.length > maxFiles) throw new Error('rc_observer_manifest_shape')
  const pins = new Map()
  let totalBytes = 0
  for (const member of manifest.files) {
    if (!validRelative(member.path) || pins.has(member.path) || !Number.isSafeInteger(member.bytes)
      || member.bytes < 0 || !/^[a-f0-9]{64}$/.test(member.sha256 ?? '')
      || totalBytes + member.bytes > maxBytes) throw new Error('rc_observer_compiled_member_invalid')
    pins.set(member.path, member)
    totalBytes += member.bytes
  }
  if (totalBytes !== manifest.totalBytes) throw new Error('rc_observer_compiled_total_mismatch')
  const found = new Set()
  function visit(current) {
    canonical(current, true)
    for (const name of readdirSync(current)) {
      const file = path.join(current, name), stat = lstatSync(file)
      if (stat.isSymbolicLink()) throw new Error('rc_observer_compiled_output_symlink')
      if (stat.isDirectory()) { visit(file); continue }
      const relative = path.relative(root, file), pin = pins.get(relative)
      if (!pin || !stat.isFile() || found.size >= maxFiles || stat.size !== pin.bytes) throw new Error('rc_observer_compiled_tree_mismatch')
      canonical(file)
      const bytes = readFileSync(file)
      if (bytes.length !== pin.bytes || hash(bytes) !== pin.sha256) throw new Error('rc_observer_compiled_member_pin_mismatch')
      found.add(relative)
    }
  }
  visit(root)
  if (found.size !== pins.size) throw new Error('rc_observer_compiled_tree_incomplete')

  const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }
  let requests = 0, pinRefusals = 0, errors = 0, listenerErrors = 0
  const server = http.createServer((request, response) => {
    requests = count(requests)
    if (request.method !== 'GET' && request.method !== 'HEAD') { response.writeHead(405).end(); return }
    try {
      const pathname = decodeURIComponent(new URL(request.url || '/', 'http://127.0.0.1').pathname)
      let relative = pathname === '/' ? 'index.html' : pathname.slice(1)
      if (!validRelative(relative)) { response.writeHead(403).end(); return }
      // Only a pinned index can serve an extensionless fallback; harness-only output need not have one.
      if (!pins.has(relative) && !path.extname(relative)) relative = 'index.html'
      const pin = pins.get(relative)
      if (!pin) { response.writeHead(404).end(); return }
      const file = path.join(root, relative)
      const stat = canonical(file)
      if (stat.size !== pin.bytes) {
        pinRefusals = count(pinRefusals); response.writeHead(409).end(); return
      }
      const bytes = readFileSync(file)
      if (bytes.length !== pin.bytes || hash(bytes) !== pin.sha256) {
        pinRefusals = count(pinRefusals); response.writeHead(409).end(); return
      }
      response.writeHead(200, {
        'Content-Type': mime[path.extname(relative)] || 'application/octet-stream',
        'Content-Length': bytes.length,
      })
      response.end(request.method === 'HEAD' ? undefined : bytes)
    } catch {
      errors = count(errors); response.writeHead(500).end()
    }
  })
  server.on('error', () => { listenerErrors = count(listenerErrors) })
  let port = null, closePromise
  const close = () => {
    if (closePromise) return closePromise
    closePromise = new Promise((resolve, reject) => {
      let settled = false
      const timer = setTimeout(() => finish(new Error('rc_observer_listener_close_timeout'), true), closeMilliseconds)
      function finish(error, timedOut = false) {
        if (settled) return
        settled = true
        clearTimeout(timer)
        const receipt = {
          schema: 1, pid: process.pid, bind: '127.0.0.1', port, manifestSha256,
          closed: !timedOut && !error && !server.listening, closeError: Boolean(error) && !timedOut,
          timedOut, requests, pinRefusals, errors, listenerErrors,
          production_or_R2_qualified: false, whole_job_resource_budget_guaranteed: false,
        }
        try {
          ownedDirectory(directory)
          writeFileSync(cleanupPath, JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
        } catch (writeError) { reject(writeError); return }
        if (error) reject(error)
        else resolve(receipt)
      }
      try {
        server.close(error => finish(error?.code === 'ERR_SERVER_NOT_RUNNING' ? undefined : error))
        server.closeAllConnections()
      } catch (error) {
        finish(error)
      }
    })
    return closePromise
  }

  try {
    await new Promise((resolve, reject) => {
      server.once('error', reject)
      server.listen(0, '127.0.0.1', () => { server.removeListener('error', reject); resolve() })
    })
    port = server.address().port
    ownedDirectory(directory)
    writeFileSync(startPath, JSON.stringify({
      schema: 1, pid: process.pid, bind: '127.0.0.1', port,
      compiledRoot: root, manifestSha256, compiledFiles: pins.size, totalBytes, started: true,
      production_or_R2_qualified: false, whole_job_resource_budget_guaranteed: false,
    }, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
  } catch (error) {
    try { await close() } catch (cleanupError) { throw new AggregateError([error, cleanupError], 'rc_observer_listener_start_and_cleanup_failed') }
    throw error
  }
  return { port, pid: process.pid, manifestSha256, close }
}
