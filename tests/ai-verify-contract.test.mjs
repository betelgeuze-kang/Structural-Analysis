import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8')
}

test('package exposes contract and full AI verify modes', () => {
  const pkg = JSON.parse(read('package.json'))
  assert.equal(pkg.scripts['ai:verify'], 'bash scripts/ai-verify.sh')
  assert.equal(pkg.scripts['ai:verify:contract'], 'bash scripts/ai-verify.sh --contract')
  assert.equal(pkg.scripts['ai:verify:full'], 'bash scripts/ai-verify.sh --full')
  assert.equal(pkg.scripts['ai:preflight'], 'bash scripts/ai-preflight.sh')
})

test('AI verify supports machine-readable receipts and web-safe script invocation', () => {
  const source = read('scripts/ai-verify.sh')
  assert.match(source, /--json-out/)
  assert.match(source, /ai-verify-result\.v1/)
  assert.match(source, /--contract/)
  assert.match(source, /--full/)
  assert.match(source, /is not executable; invoke it with bash/)
  assert.doesNotMatch(source, /test -x scripts\/ai-/)
})

test('preflight invokes AI verify through bash instead of executable-bit dependency', () => {
  const source = read('scripts/ai-preflight.sh')
  assert.match(source, /bash scripts\/ai-verify\.sh/)
  assert.doesNotMatch(source, /\.\/scripts\/ai-verify\.sh/)
})

test('dedicated workflow runs contract verify and retains its JSON receipt', () => {
  const workflow = read('.github/workflows/ai-contract-verify.yml')
  assert.match(workflow, /name: AI Contract Verify/)
  assert.match(workflow, /npm run ai:verify:contract/)
  assert.match(workflow, /--json-out/)
  assert.match(workflow, /actions\/upload-artifact@v4/)
  assert.match(workflow, /STRUCTURAL_AI_RUNNER_LABELS/)
  assert.doesNotMatch(workflow, /runs-on:\s*ubuntu-latest/)
})
