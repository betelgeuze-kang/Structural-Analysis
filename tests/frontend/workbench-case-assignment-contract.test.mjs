import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const source = fs.readFileSync(path.join(root, 'src/workbench-v2/model/caseSchema.ts'), 'utf8')

function assignment(name) {
  const line = source.split('\n').find((entry) => entry.trim().startsWith(name + ':'))
  assert.ok(line, 'assignment line exists for ' + name)
  return line.trim()
}

test('unit assignment uses validated input variable only', () => {
  const line = assignment('unitSystem')
  assert.equal(line, 'unitSystem: unitSystem as UnitSystem,')
})

test('coordinate assignment uses validated input variable only', () => {
  const line = assignment('coordinateSystem')
  assert.equal(line, 'coordinateSystem: coordinateSystem as CoordinateSystem,')
})
