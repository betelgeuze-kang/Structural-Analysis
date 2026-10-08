'use strict'

// Diagnostic-only instrumentation of the exact installed Playwright 1.56.1 source.
// Never writes node_modules or adds promises to the assertion's await chain.
const { createHash } = require('node:crypto')
const { readFileSync, realpathSync } = require('node:fs')
const { createRequire } = require('node:module')
const Module = require('node:module')
const path = require('node:path')
const ORIGINAL_SHA256 = 'd87bb39dc8ff2c7efd7b925bab405e70f925fdc6e666880ef8dee41a31502e47'
const hash = value => createHash('sha256').update(value).digest('hex')

function observerRuntime(identity) {
  const key = Symbol.for('structural.rc.expect-await.v1')
  const captures = new WeakMap(), calls = new WeakMap()
  let active
  const api = Object.freeze({
    begin(expected) {
      if (active || !['queued', 'failed', 'checkpointed', 'cancelled'].includes(expected)) return undefined
      const token = Object.freeze({})
      active = { expected, rows: [], overflow: false, open: true, bound: false }
      captures.set(token, active)
      return token
    },
    end(token) {
      const capture = captures.get(token)
      if (!capture) return undefined
      captures.delete(token); capture.open = false
      if (active === capture) active = undefined
      return { schema: 1, identity, rows: capture.rows, overflow: capture.overflow, bound: capture.bound }
    },
  })
  Object.defineProperty(globalThis, key, { value: api, configurable: false, writable: false })
  return {
    bind(progress, selector, options) {
      try {
        if (!active?.open || active.bound
          || selector !== '[data-rc-workflow="project"] >> [data-job-service="ready"]'
          || options.expression !== 'to.have.attribute.value' || options.expressionArg !== 'data-job-status'
          || options.isNot !== false || options.expectedText?.length !== 1
          || options.expectedText[0].string !== active.expected) return
        active.bound = true; calls.set(progress, active)
      } catch { /* Optional observation cannot replace an assertion outcome. */ }
    },
    mark(progress, phase) {
      try {
        const capture = calls.get(progress)
        if (!capture?.open) return
        if (capture.rows.length >= 512) { capture.overflow = true; return }
        capture.rows.push({ sequence: capture.rows.length + 1, phase, monotonicMs: performance.now() })
      } catch { /* Optional observation cannot replace an assertion outcome. */ }
    },
  }
}

function replaceOnce(source, from, to) {
  if (source.split(from).length !== 2) throw new Error('rc_expect_observer_anchor_mismatch')
  return source.replace(from, to)
}

function transform(source) {
  if (hash(source) !== ORIGINAL_SHA256) throw new Error('rc_expect_observer_source_mismatch')
  let result = replaceOnce(source, '  async expect(progress, selector, options, timeout) {',
    '  async expect(progress, selector, options, timeout) {\n    rcAwaitObserver.bind(progress, selector, options);\n    rcAwaitObserver.mark(progress, "expect.begin");')
  const start = result.indexOf('  async expect('), end = result.indexOf('  async waitForFunctionExpression(', start)
  let section = result.slice(start, end)
  const precheck = 'await this._page.performActionPreChecks(progress);'
  if (section.split(precheck).length !== 3) throw new Error('rc_expect_observer_precheck_mismatch')
  section = section.split(precheck).join('rcAwaitObserver.mark(progress, "prechecks.begin");\n      ' + precheck + '\n      rcAwaitObserver.mark(progress, "prechecks.end");')
  for (const [anchor, phase] of [
    ['    const selectorInFrame =', 'resolve'], ['    const context = await race(frame._context(world));', 'context'],
    ['    const injected = await race(context.injectedScript());', 'injected'],
    ['    const { log, matches, received, missingReceived } = await race(injected.evaluate', 'evaluate'],
  ]) section = replaceOnce(section, anchor, `    rcAwaitObserver.mark(progress, "${phase}.begin");\n${anchor}`)
  for (const [anchor, phase] of [
    ['    const { frame, info }', 'resolve'], ['    rcAwaitObserver.mark(progress, "injected.begin");', 'context'],
    ['    rcAwaitObserver.mark(progress, "evaluate.begin");', 'injected'], ['    if (log)\n', 'evaluate'],
  ]) section = replaceOnce(section, anchor, `    rcAwaitObserver.mark(progress, "${phase}.end");\n${anchor}`)
  section = replaceOnce(section, '    } catch (e) {\n      const result =',
    '    } catch (e) {\n      rcAwaitObserver.mark(progress, "expect.catch");\n      const result =')
  result = result.slice(0, start) + section + result.slice(end)
  result = replaceOnce(result, '        const actionPromise = new Promise((f) => setTimeout(f, timeout));',
    '        rcAwaitObserver.mark(progress, "retry.sleep.begin");\n        const actionPromise = new Promise((f) => setTimeout(f, timeout));')
  result = replaceOnce(result, '        ], actionPromise));',
    '        ], actionPromise));\n        rcAwaitObserver.mark(progress, "retry.sleep.end");')
  // Preserve the original strict-mode directive. The template digest excludes only
  // its own identity literal, whose recursive digest would be undefined.
  const template = replaceOnce(result, '"use strict";\n',
    '"use strict";\nconst rcAwaitObserver = (' + observerRuntime.toString() + ')(__RC_OBSERVER_IDENTITY__);\n')
  const identity = { playwrightVersion: '1.56.1', originalSha256: ORIGINAL_SHA256,
    templateSha256: hash(template), observerSha256: hash(readFileSync(__filename)),
    interpretation: 'instrumented_diagnostic_not_original_dependency_execution' }
  return { source: replaceOnce(template, '__RC_OBSERVER_IDENTITY__', JSON.stringify(identity)), identity }
}

function install(root = process.cwd()) {
  const resolve = createRequire(path.join(root, 'package.json'))
  const packageFile = realpathSync(resolve.resolve('playwright-core/package.json'))
  if (JSON.parse(readFileSync(packageFile, 'utf8')).version !== '1.56.1') throw new Error('rc_expect_observer_version_mismatch')
  const target = realpathSync(path.join(path.dirname(packageFile), 'lib/server/frames.js'))
  if (require.cache[target]) throw new Error('rc_expect_observer_already_loaded')
  const originalLoader = Module._extensions['.js']
  Module._extensions['.js'] = function (module, filename) {
    if (filename !== target) return originalLoader(module, filename)
    Module._extensions['.js'] = originalLoader
    const transformed = transform(readFileSync(target, 'utf8'))
    return module._compile(transformed.source, filename)
  }
}

module.exports = { ORIGINAL_SHA256, transform, install }
