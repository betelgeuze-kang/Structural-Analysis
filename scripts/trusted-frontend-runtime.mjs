import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const expectedNodeVersion = 'v24.20.0'
export const expectedNodeSha = '89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7'

const allowedExtraEnvironment = new Set([
  'STRUCTURE_VIEWER_BASE_URL',
  'STRUCTURE_VIEWER_BROWSER_SMOKE_MODE',
  'VITE_BASE_PATH',
  'WORKBENCH_PROTOTYPE_BASE_URL',
  'WORKBENCH_V2_BASE_URL',
])

export function sha256(file) {
  return createHash('sha256').update(readFileSync(file)).digest('hex')
}

function assertAbsoluteRegularRealFile(file, label) {
  if (!path.isAbsolute(file) || !existsSync(file)) throw new Error(`${label}_missing`)
  const stat = lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink() || realpathSync(file) !== file) {
    throw new Error(`${label}_unsafe`)
  }
  return file
}

export function trustedNode({ dryRun = false } = {}) {
  if (!path.isAbsolute(process.execPath)) throw new Error('trusted_node_path_not_absolute')
  const node = realpathSync(process.execPath)
  if (path.resolve(process.execPath) !== node) throw new Error('trusted_node_path_not_real')
  assertAbsoluteRegularRealFile(node, 'trusted_node')
  if (!dryRun && (process.version !== expectedNodeVersion || sha256(node) !== expectedNodeSha)) {
    throw new Error('trusted_node_identity_mismatch')
  }
  return node
}

export function trustedRepoTool(rootDir, relative, label) {
  const root = realpathSync(rootDir)
  const candidate = path.resolve(root, relative)
  if (!candidate.startsWith(`${root}${path.sep}`)) throw new Error(`${label}_outside_repository`)
  return assertAbsoluteRegularRealFile(candidate, label)
}

function absoluteRuntimeDirectory(name, fallback) {
  const candidate = process.env[name] || fallback
  if (!path.isAbsolute(candidate)) throw new Error(`${name.toLowerCase()}_not_absolute`)
  return candidate
}

export function sanitizedFrontendEnvironment(node, extra = {}) {
  for (const [name, value] of Object.entries(extra)) {
    if (!allowedExtraEnvironment.has(name) || typeof value !== 'string') {
      throw new Error(`frontend_environment_key_not_allowed:${name}`)
    }
  }
  return {
    HOME: absoluteRuntimeDirectory('HOME', '/nonexistent'),
    LANG: 'C.UTF-8',
    LC_ALL: 'C.UTF-8',
    PATH: `${path.dirname(node)}:/usr/bin:/bin`,
    TMPDIR: absoluteRuntimeDirectory('TMPDIR', os.tmpdir()),
    ...extra,
  }
}
