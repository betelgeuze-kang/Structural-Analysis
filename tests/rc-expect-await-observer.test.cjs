'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { createHash } = require('node:crypto')
const { transform, ORIGINAL_SHA256 } = require('../scripts/rc-expect-await-observer.cjs')
const core = path.dirname(require.resolve('playwright-core/package.json'))
const source = fs.readFileSync(path.join(core, 'lib/server/frames.js'), 'utf8')
const sha = value => createHash('sha256').update(value).digest('hex')

test('exact source is admitted; any source drift is rejected before compilation', () => {
  assert.equal(sha(source), ORIGINAL_SHA256)
  assert.throws(() => transform(source + '\n'), /source_mismatch/)
  assert.throws(() => transform(source.replace('timeoutIndex++', 'timeoutIndex')), /source_mismatch/)
  const result = transform(source)
  assert.ok(result.source.startsWith('"use strict";\n'))
  assert.equal(result.identity.originalSha256, ORIGINAL_SHA256)
  assert.equal(fs.readFileSync(path.join(core, 'lib/server/frames.js'), 'utf8'), source)
})

test('removing diagnostic-only statements restores the entire original syntax tree', () => {
  const parse = value => ts.createSourceFile('frames.js', value, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
  const original = parse(source), instrumented = parse(transform(source).source)
  const cleaned = ts.transform(instrumented, [context => {
    const visit = node => {
      if (ts.isVariableStatement(node) && node.declarationList.declarations.length === 1
        && node.declarationList.declarations[0].name.getText(instrumented) === 'rcAwaitObserver') return undefined
      if (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression)
        && ts.isPropertyAccessExpression(node.expression.expression)
        && node.expression.expression.expression.getText(instrumented) === 'rcAwaitObserver') return undefined
      return ts.visitEachChild(node, visit, context)
    }
    return root => ts.visitNode(root, visit)
  }])
  try {
    const printer = ts.createPrinter({ removeComments: true })
    assert.equal(printer.printFile(cleaned.transformed[0]), printer.printFile(original))
  } finally { cleaned.dispose() }
})

function runtime() {
  const transformed = transform(source).source
  const prefix = transformed.slice(0, transformed.indexOf('var __create ='))
  const context = vm.createContext({ performance: { now: () => 123 } })
  vm.runInContext(prefix + '\nglobalThis.controls = rcAwaitObserver;', context)
  return { api: vm.runInContext('globalThis[Symbol.for("structural.rc.expect-await.v1")]', context), mark: context.controls }
}
const selector = '[data-rc-workflow="project"] >> [data-job-service="ready"]'
const options = { expression: 'to.have.attribute.value', expressionArg: 'data-job-status',
  isNot: false, expectedText: [{ string: 'failed' }] }

test('off, unrelated selector, and unexpected status never bind a capture', () => {
  const { api, mark } = runtime(), progress = {}
  mark.bind(progress, selector, options); mark.mark(progress, 'expect.begin')
  const token = api.begin('failed')
  mark.bind(progress, 'body', options); mark.mark(progress, 'expect.begin')
  mark.bind(progress, selector, { ...options, expectedText: [{ string: 'queued' }] })
  mark.mark(progress, 'expect.begin')
  const capture = api.end(token)
  assert.equal(capture.rows.length, 0); assert.equal(capture.bound, false)
})

test('only one matching assertion binds, and late completion cannot leak into the next capture', () => {
  const { api, mark } = runtime(), first = {}, other = {}
  const token = api.begin('failed')
  assert.equal(api.begin('failed'), undefined)
  mark.bind(first, selector, options); mark.bind(other, selector, options)
  mark.mark(first, 'resolve.begin'); mark.mark(other, 'resolve.begin')
  const capture = api.end(token)
  assert.equal(capture.bound, true); assert.equal(capture.rows.length, 1)
  const next = api.begin('failed')
  mark.mark(first, 'resolve.end')
  assert.equal(api.end(next).rows.length, 0)
  assert.equal(capture.rows.length, 1)
  assert.equal(api.end(token), undefined)
})

test('bounded overflow is explicit and keeps the original 512 rows', () => {
  const { api, mark } = runtime(), progress = {}, token = api.begin('failed')
  mark.bind(progress, selector, options)
  for (let i = 0; i < 600; i++) mark.mark(progress, 'evaluate.begin')
  const capture = api.end(token)
  assert.equal(capture.rows.length, 512); assert.equal(capture.overflow, true)
  assert.equal(capture.rows[511].sequence, 512)
})
