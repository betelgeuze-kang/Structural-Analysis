import { spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isDryRun = process.argv.includes('--dry-run')

function formatCommand(parts) {
  return parts.join(' ')
}

function runCommand(parts, options = {}) {
  console.log(`${isDryRun ? '[dry-run] ' : ''}${formatCommand(parts)}`)
  if (isDryRun) {
    return
  }

  const [command, ...args] = parts
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? rootDir,
    env: options.env ?? process.env,
    stdio: 'inherit',
  })

  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const nullDevice = process.platform === 'win32' ? 'NUL' : '/dev/null'

function sanitizedNpmEnvironment(cacheDir, userConfig, globalConfig) {
  const environment = {}
  for (const [key, value] of Object.entries(process.env)) {
    const lowered = key.toLowerCase()
    if (lowered.startsWith('npm_config_') || ['http_proxy', 'https_proxy', 'all_proxy'].includes(lowered)) {
      continue
    }
    environment[key] = value
  }
  environment.NPM_CONFIG_USERCONFIG = userConfig
  environment.NPM_CONFIG_GLOBALCONFIG = globalConfig
  environment.NPM_CONFIG_CACHE = cacheDir
  return environment
}

const registryArgs = [
  '--registry=https://registry.npmjs.org/',
  '--strict-ssl=true',
  '--include=prod',
  '--include=dev',
  '--include=optional',
  '--include=peer',
]
const installArgs = [npmCommand, 'ci', '--ignore-scripts', '--engine-strict', ...registryArgs]
let temporaryRoot
try {
  if (!isDryRun) {
    temporaryRoot = mkdtempSync(path.join(os.tmpdir(), 'frontend-clean-smoke-'))
    const cleanCopy = path.join(temporaryRoot, 'workspace')
    mkdirSync(cleanCopy, { mode: 0o700 })
    copyFileSync(path.join(rootDir, 'package.json'), path.join(cleanCopy, 'package.json'))
    copyFileSync(path.join(rootDir, 'package-lock.json'), path.join(cleanCopy, 'package-lock.json'))
  }
  const cleanCopy = temporaryRoot ? path.join(temporaryRoot, 'workspace') : '<isolated-clean-copy>'
  const cleanCache = temporaryRoot ? path.join(temporaryRoot, 'cache') : '<isolated-npm-cache>'
  const configRoot = temporaryRoot ? path.join(temporaryRoot, 'config') : '<dev-null-config-aliases>'
  let userConfig = '<user-dev-null-alias>'
  let globalConfig = '<global-dev-null-alias>'
  if (temporaryRoot) {
    mkdirSync(configRoot, { mode: 0o700 })
    userConfig = path.join(configRoot, 'user.npmrc')
    globalConfig = path.join(configRoot, 'global.npmrc')
    if (process.platform === 'win32') {
      writeFileSync(userConfig, '')
      writeFileSync(globalConfig, '')
    } else {
      symlinkSync(nullDevice, userConfig)
      symlinkSync(nullDevice, globalConfig)
    }
  }
  const cleanEnvironment = sanitizedNpmEnvironment(cleanCache, userConfig, globalConfig)
  runCommand(installArgs, { cwd: cleanCopy, env: cleanEnvironment })
  runCommand([npmCommand, 'audit', '--json', '--audit-level=info', ...registryArgs], {
    cwd: cleanCopy,
    env: cleanEnvironment,
  })
  runCommand([npmCommand, 'audit', 'signatures', '--json', ...registryArgs], {
    cwd: cleanCopy,
    env: cleanEnvironment,
  })
  runCommand(['node', './scripts/verify-frontend-build-contract.mjs'])
  runCommand(installArgs, {
    env: cleanEnvironment,
  })
  runCommand([npmCommand, 'run', 'build'])
} finally {
  if (temporaryRoot) {
    rmSync(temporaryRoot, { force: true, recursive: true })
  }
}
