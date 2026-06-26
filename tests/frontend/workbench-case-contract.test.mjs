import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const source = fs.readFileSync(path.join(root, 'src/workbench-v2/model/caseSchema.ts'), 'utf8')

function assignmentLine(name) {
  const line = source.split('\n').find((entry) => entry.trim().startsWith(name + ':'))
  assert.ok(line, 'assignment line exists for ' + name)
  return line.trim()
}

test('Workbench Case v2 hard-blocks unsupported units instead of silently defaulting to SI', () => {
  assert.match(source, /unsupported model\.unitSystem/)
  assert.match(source, /expected SI/)

  const line = assignmentLine('unitSystem')
  assert.equal(line, 'unitSystem: unitSystem as UnitSystem,')
})

test('Workbench Case v2 hard-blocks unsupported coordinate systems instead of silently defaulting to global_xyz', () => {
  assert.match(source, /model\.coordinateSystem is missing/)
  assert.match(source, /unsupported model\.coordinateSystem/)
  assert.match(source, /expected global_xyz/)

  const line = assignmentLine('coordinateSystem')
  assert.equal(line, 'coordinateSystem: coordinateSystem as CoordinateSystem,')
})

test('Workbench Case v2 still treats missing convergence as unavailable, not inferred', () => {
  assert.match(source, /analysis\.converged is missing/)
  assert.doesNotMatch(source, /residualHistory\.length\s*>\s*0\s*\?\s*'converged'/)
})
