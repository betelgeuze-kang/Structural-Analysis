import { spawnSync } from 'node:child_process'
import {
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  symlinkSync,
} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  expectedNodeVersion,
  sha256,
  trustedNode,
  trustedRepoTool,
} from './trusted-frontend-runtime.mjs'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isDryRun = process.argv.includes('--dry-run')
const expectedNpmVersion = '11.19.0'
const expectedNpmCliSha = '8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7'
const forbiddenNames = new Set([
  '.npmrc', '.pnpmfile.cjs', '.yarn', '.yarnrc', '.yarnrc.yml',
  'bun.lock', 'bun.lockb', 'bunfig.toml', 'npm-shrinkwrap.json',
  'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'yarn.lock',
])
const ignoredTraversalNames = new Set(['.git', 'dist', 'node_modules'])
const unsupportedManifestFields = new Set([
  'bundleDependencies', 'bundledDependencies', 'devEngines', 'overrides', 'workspaces',
])

function fail(reason) {
  console.error(`frontend smoke failed: ${reason}`)
  process.exit(2)
}

function lexists(file) {
  try {
    lstatSync(file)
    return true
  } catch (error) {
    if (error && error.code === 'ENOENT') return false
    throw error
  }
}

function assertRegularRealFile(file, label) {
  if (!path.isAbsolute(file) || !existsSync(file)) fail(`${label}_missing`)
  const stat = lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink() || realpathSync(file) !== file) {
    fail(`${label}_unsafe`)
  }
}

function loadJson(file, label) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    fail(`${label}_json_invalid`)
  }
}

function preflightDependencySurface() {
  for (const file of ['package.json', 'package-lock.json']) {
    const candidate = path.join(rootDir, file)
    if (!existsSync(candidate)) fail(`${file}_missing`)
    const stat = lstatSync(candidate)
    if (!stat.isFile() || stat.isSymbolicLink()) fail(`${file}_unsafe`)
  }
  let ancestor = rootDir
  while (true) {
    if (lexists(path.join(ancestor, '.npmrc'))) fail('forbidden_ancestor_npmrc')
    const parent = path.dirname(ancestor)
    if (parent === ancestor) break
    ancestor = parent
  }
  const pending = [rootDir]
  while (pending.length > 0) {
    const directory = pending.pop()
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (forbiddenNames.has(entry.name)) fail(`forbidden_dependency_surface:${entry.name}`)
      if (entry.isSymbolicLink()) continue
      if (entry.isDirectory() && !ignoredTraversalNames.has(entry.name)) {
        pending.push(path.join(directory, entry.name))
      }
    }
  }
  const manifest = loadJson(path.join(rootDir, 'package.json'), 'package_manifest')
  const lock = loadJson(path.join(rootDir, 'package-lock.json'), 'package_lock')
  if (Object.keys(manifest).some((key) => unsupportedManifestFields.has(key))) {
    fail('unsupported_package_manifest_surface')
  }
  if (manifest.packageManager !== 'npm@11.19.0') fail('package_manager_mismatch')
  if (JSON.stringify(manifest.engines) !== JSON.stringify({ node: '24.20.0', npm: '11.19.0' })) {
    fail('package_engines_mismatch')
  }
  if (lock.lockfileVersion !== 3 || lock.requires !== true || typeof lock.packages !== 'object') {
    fail('package_lock_contract_mismatch')
  }
  const lockRoot = lock.packages['']
  if (!lockRoot || lock.name !== manifest.name || lock.version !== manifest.version ||
      lockRoot.name !== manifest.name || lockRoot.version !== manifest.version ||
      JSON.stringify(lockRoot.engines) !== JSON.stringify(manifest.engines)) {
    fail('package_lock_root_mismatch')
  }
}

function trustedToolchain() {
  let node
  try {
    node = trustedNode({ dryRun: isDryRun })
  } catch (error) {
    fail(error instanceof Error ? error.message : 'trusted_node_identity_mismatch')
  }
  const npmCli = path.join(
    path.dirname(path.dirname(node)), 'lib', 'node_modules', 'npm', 'bin', 'npm-cli.js',
  )
  assertRegularRealFile(node, 'trusted_node')
  assertRegularRealFile(npmCli, 'trusted_npm_cli')
  if (!isDryRun) {
    if (sha256(npmCli) !== expectedNpmCliSha) fail('trusted_npm_cli_hash_mismatch')
    const version = spawnSync(node, [npmCli, '--version'], {
      env: { HOME: '/nonexistent', LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', PATH: '/usr/bin:/bin' },
      encoding: 'utf8',
    })
    if (version.status !== 0 || version.stdout.trim() !== expectedNpmVersion) {
      fail('trusted_npm_cli_version_mismatch')
    }
  }
  return { node, npmCli }
}

function runCommand(parts, options = {}) {
  console.log(`${isDryRun ? '[dry-run] ' : ''}${parts.join(' ')}`)
  if (isDryRun) return
  const [command, ...args] = parts
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? rootDir,
    env: options.env,
    stdio: 'inherit',
  })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

function repoTool(relative, label) {
  return isDryRun ? path.join(rootDir, relative) : trustedRepoTool(rootDir, relative, label)
}

function isolatedNpmEnvironment(root, cache, userConfig, globalConfig, node) {
  const home = path.join(root, 'home')
  const tmp = path.join(root, 'tmp')
  mkdirSync(home, { mode: 0o700 })
  mkdirSync(tmp, { mode: 0o700 })
  return {
    HOME: home,
    LANG: 'C.UTF-8',
    LC_ALL: 'C.UTF-8',
    NPM_CONFIG_CACHE: cache,
    NPM_CONFIG_GLOBALCONFIG: globalConfig,
    NPM_CONFIG_USERCONFIG: userConfig,
    PATH: `${path.dirname(node)}:/usr/bin:/bin`,
    TMPDIR: tmp,
  }
}

preflightDependencySurface()
const { node, npmCli } = trustedToolchain()
const registryArgs = [
  '--registry=https://registry.npmjs.org/', '--strict-ssl=true', '--include=prod',
  '--include=dev', '--include=optional', '--include=peer',
]
let temporaryRoot
try {
  if (!isDryRun) temporaryRoot = mkdtempSync(path.join(os.tmpdir(), 'frontend-clean-smoke-'))
  const temp = temporaryRoot ?? '<isolated-root>'
  const cleanCopy = path.join(temp, 'workspace')
  const configRoot = path.join(temp, 'config')
  if (!isDryRun) {
    mkdirSync(cleanCopy, { mode: 0o700 })
    mkdirSync(configRoot, { mode: 0o700 })
    copyFileSync(path.join(rootDir, 'package.json'), path.join(cleanCopy, 'package.json'))
    copyFileSync(path.join(rootDir, 'package-lock.json'), path.join(cleanCopy, 'package-lock.json'))
    symlinkSync('/dev/null', path.join(configRoot, 'user.npmrc'))
    symlinkSync('/dev/null', path.join(configRoot, 'global.npmrc'))
  }
  const userConfig = path.join(configRoot, 'user.npmrc')
  const globalConfig = path.join(configRoot, 'global.npmrc')
  const cleanEnvironment = isDryRun ? {} : isolatedNpmEnvironment(
    temp, path.join(temp, 'cache'), userConfig, globalConfig, node,
  )
  const npm = (...args) => [node, npmCli, ...args]
  runCommand(npm('ci', '--ignore-scripts', '--engine-strict', ...registryArgs), {
    cwd: cleanCopy, env: cleanEnvironment,
  })
  runCommand(npm('audit', '--json', '--audit-level=info', ...registryArgs), {
    cwd: cleanCopy, env: cleanEnvironment,
  })
  runCommand(npm('audit', 'signatures', '--json', ...registryArgs), {
    cwd: cleanCopy, env: cleanEnvironment,
  })
  runCommand(npm('ci', '--ignore-scripts', '--engine-strict', ...registryArgs), {
    env: cleanEnvironment,
  })
  const contract = repoTool(
    'scripts/verify-frontend-build-contract.mjs',
    'frontend_build_contract',
  )
  runCommand([node, contract], { env: cleanEnvironment })
  const typescript = repoTool('node_modules/typescript/bin/tsc', 'typescript_cli')
  const vite = repoTool('node_modules/vite/bin/vite.js', 'vite_cli')
  const delivery = repoTool(
    'scripts/verify-workbench-viewer-delivery.mjs',
    'viewer_delivery_contract',
  )
  runCommand([node, typescript, '--noEmit'], { env: cleanEnvironment })
  runCommand([node, vite, 'build'], { env: cleanEnvironment })
  runCommand([node, delivery], { env: cleanEnvironment })
} finally {
  if (temporaryRoot) rmSync(temporaryRoot, { force: true, recursive: true })
}
