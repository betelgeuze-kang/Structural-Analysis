import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isDryRun = process.argv.includes('--dry-run')

function formatCommand(parts) {
  return parts.join(' ')
}

function runCommand(parts) {
  console.log(`${isDryRun ? '[dry-run] ' : ''}${formatCommand(parts)}`)
  if (isDryRun) {
    return
  }

  const [command, ...args] = parts
  const result = spawnSync(command, args, {
    cwd: rootDir,
    stdio: 'inherit',
  })

  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'

runCommand(['node', './scripts/verify-frontend-build-contract.mjs'])
runCommand([npmCommand, 'ci'])
runCommand([npmCommand, 'run', 'build'])
