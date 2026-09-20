import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { validateWorkbenchTestRegistration } from '../scripts/workbench-test-registration.mjs'

test('new Workbench tests cannot silently escape both execution lanes', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'workbench-registration-'))
  try {
    mkdirSync(path.join(root, 'tests/frontend'), { recursive: true })
    const base = 'tests/frontend/workbench-v2-local.spec.ts'
    const python = 'tests/frontend/workbench-v2-service.spec.ts'
    for (const spec of [base, python]) writeFileSync(path.join(root, spec), '')
    assert.throws(() => validateWorkbenchTestRegistration(root, [base], []), /Unregistered.*service/)
    validateWorkbenchTestRegistration(root, [base], [python])
    assert.throws(() => validateWorkbenchTestRegistration(root, [base, python], [python]), /Duplicate/)
    assert.throws(() => validateWorkbenchTestRegistration(root, [base], ['tests/frontend/missing.spec.ts']), /missing/)
    assert.throws(() => validateWorkbenchTestRegistration(root, [base], ['../outside.spec.ts']), /Invalid/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
