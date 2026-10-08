import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { trustedNode, trustedRepoTool } from './trusted-frontend-runtime.mjs'

const maxFiles = 64
const maxBytes = 64 * 1024 * 1024
const expectedViteApiSha = '9b3e72282cfda2f0e60ad5b123e2c8a89e27b9b7cc7c892ae7b34036db5f92ef'
const hash = bytes => createHash('sha256').update(bytes).digest('hex')

function canonical(file, directory = false) {
  const stat = lstatSync(file)
  if (stat.isSymbolicLink() || realpathSync(file) !== file
    || !(directory ? stat.isDirectory() : stat.isFile())) throw new Error('rc_observer_input_not_canonical')
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

const args = process.argv.slice(2)
if (args.length !== 2 || !path.isAbsolute(args[0])) throw new Error('rc_observer_build_arguments_invalid')
trustedNode()
const root = args[0], directory = ownedDirectory(args[1])
canonical(root, true)
if (directory === root || directory.startsWith(root + path.sep)) throw new Error('rc_observer_output_inside_source')
const output = path.join(directory, 'compiled')
const manifestPath = path.join(directory, 'compiled-manifest.json')
if (existsSync(output) || existsSync(manifestPath)) throw new Error('rc_observer_new_output_required')
const api = trustedRepoTool(root, 'node_modules/vite/dist/node/index.js', 'rc_observer_vite_api')
if (hash(readFileSync(api)) !== expectedViteApiSha) throw new Error('rc_observer_vite_api_pin_mismatch')
const { build } = await import(pathToFileURL(api).href)
await build({
  root, configFile: false, envDir: false, base: '/', mode: 'development',
  define: { 'process.env.NODE_ENV': '"development"' },
  build: {
    outDir: output, emptyOutDir: false, sourcemap: false,
    rollupOptions: { input: path.join(root, 'tests/frontend/rc-observer-harness.html') },
  },
})

const files = []
let totalBytes = 0
const validRelative = relative => /^[A-Za-z0-9._/-]+$/.test(relative)
  && relative.split('/').every(part => part && part !== '.' && part !== '..'
    && part !== '.env' && !part.startsWith('.env.') && !part.endsWith('.env') && !part.includes('.env.'))
function visit(current) {
  canonical(current, true)
  for (const name of readdirSync(current).sort()) {
    const file = path.join(current, name), stat = lstatSync(file)
    if (stat.isSymbolicLink()) throw new Error('rc_observer_compiled_symlink')
    if (stat.isDirectory()) { visit(file); continue }
    const relative = path.relative(output, file)
    if (!stat.isFile() || !validRelative(relative) || !Number.isSafeInteger(stat.size) || stat.size < 0
      || files.length >= maxFiles || totalBytes + stat.size > maxBytes) throw new Error('rc_observer_output_budget_or_member_invalid')
    canonical(file)
    const bytes = readFileSync(file)
    if (bytes.length !== stat.size) throw new Error('rc_observer_output_changed')
    files.push({ path: relative, bytes: bytes.length, sha256: hash(bytes) })
    totalBytes += bytes.length
  }
}
visit(output)
if (!files.length) throw new Error('rc_observer_empty_output')
// These are post-build output bounds, not whole-process memory or raw-write limits.
writeFileSync(manifestPath, JSON.stringify({
  schema: 1, files, totalBytes, buildMode: 'development-test-harness',
  actualStrictMode_doubleEffect_verified: false, production_app_qualified: false,
}, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
