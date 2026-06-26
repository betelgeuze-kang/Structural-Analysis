import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const source = fs.readFileSync(path.join(root, 'src/workbench-v2/model/caseSchema.ts'), 'utf8')

test('Workbench Case v2 hard-blocks unsupported units instead of silently coercing to SI', () => {
  assert.match(source, /unsupported model\.unitSystem/)
  assert.match(source, /expected SI/)
  assert.doesNotMatch(source, /unitSystem:\s*'SI'\s+as UnitSystem/)
  assert.match(source, /unitSystem:\s*unitSystem as UnitSystem/)
})

test('Workbench Case v2 hard-blocks unsupported coordinate systems instead of silently coercing to global_xyz', () => {
  assert.match(source, /model\.coordinateSystem is missing/)
  assert.match(source, /unsupported model\.coordinateSystem/)
  assert.match(source, /expected global_xyz/)
  assert.doesNotMatch(source, /coordinateSystem:\s*\(str\(model\.coordinateSystem\) \?\? 'global_xyz'\) as CoordinateSystem/)
  assert.match(source, /coordinateSystem:\s*coordinateSystem as CoordinateSystem/)
})

test('Workbench Case v2 still treats missing convergence as unavailable, not inferred', () => {
  assert.match(source, /analysis\.converged is missing — convergence is UNAVAILABLE, not inferred/)
  assert.doesNotMatch(source, /residualHistory\.length\s*>\s*0\s*\?\s*'converged'/)
})
