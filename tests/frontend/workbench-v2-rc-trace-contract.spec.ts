import { test } from '@playwright/test'
import assert from 'node:assert/strict'
import { beginRcPhaseSession, bindRcPhase, traceRcPhase } from '../../src/workbench-v2/model/rcWorkflowTrace'
import type { RcPhaseMarker, RcPhaseName } from '../../src/workbench-v2/model/rcWorkflowTrace'

// Node-only metadata contracts: no page/browser fixture, service or model inputs.
// Synthetic globals exist only during synchronous module calls and Node assertions.
// Restore them before returning to any Playwright matcher, step or runner boundary.
const hookName = '__RC_INITIAL_READY_MARKER_HOOK__'
type Rows = Readonly<RcPhaseMarker>[]

function restore(name: string, descriptor: PropertyDescriptor | undefined) {
  if (descriptor) Object.defineProperty(globalThis, name, descriptor)
  else Reflect.deleteProperty(globalThis, name)
}
function setHook(value: unknown) {
  Object.defineProperty(globalThis, hookName, { configurable: true, value })
}
function setClock(value: unknown) {
  Object.defineProperty(globalThis, 'performance', { configurable: true, value })
}
function clock() {
  let stamp = 0
  setClock({ now: () => ++stamp })
}
function session(generation: number, rows: Rows) {
  const signal = new AbortController().signal
  setHook((marker: Readonly<RcPhaseMarker>) => rows.push(marker))
  beginRcPhaseSession(signal, generation)
  return signal
}
function withSyntheticGlobals(control: () => void): void {
  const originalHook = Object.getOwnPropertyDescriptor(globalThis, hookName)
  const originalPerformance = Object.getOwnPropertyDescriptor(globalThis, 'performance')
  try {
    Reflect.deleteProperty(globalThis, hookName)
    clock()
    control()
  } finally {
    try { restore(hookName, originalHook) }
    finally { restore('performance', originalPerformance) }
  }
}

test.describe('bounded RC phase observer metadata', () => {
  test.describe.configure({ mode: 'serial' })

  test('absent and nonfunction hooks stay inactive without clock access', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    let reads = 0
    Object.defineProperty(globalThis, 'performance', {
      configurable: true,
      get() { reads++; throw new Error('synthetic clock') },
    })
    for (const value of [undefined, null, false, 1, 'observer', {}, []]) {
      if (value === undefined) Reflect.deleteProperty(globalThis, hookName)
      else setHook(value)
      const signal = new AbortController().signal
      assert.doesNotThrow(() => beginRcPhaseSession(signal, 1))
      setHook((marker: Readonly<RcPhaseMarker>) => rows.push(marker))
      assert.doesNotThrow(() => traceRcPhase(signal, 'effect.setup'))
    }
    assert.strictEqual(reads, 0)
    assert.deepStrictEqual(rows, [])
  }))

  test('throwing hook getter and invalid generations create no context', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    let hookReads = 0
    Object.defineProperty(globalThis, hookName, {
      configurable: true,
      get() { hookReads++; throw new Error('synthetic observer') },
    })
    const signal = new AbortController().signal
    assert.doesNotThrow(() => beginRcPhaseSession(signal, 1))
    setHook((marker: Readonly<RcPhaseMarker>) => rows.push(marker))
    traceRcPhase(signal, 'effect.setup')
    assert.strictEqual(hookReads, 1)
    for (const generation of [-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
      const invalid = new AbortController().signal
      beginRcPhaseSession(invalid, generation)
      traceRcPhase(invalid, 'effect.setup')
    }
    assert.deepStrictEqual(rows, [])
  }))

  test('ordinary strict function receives no private context and only a frozen public record', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    let receiver: unknown = 'not called'
    setHook(function (this: unknown, marker: Readonly<RcPhaseMarker>) {
      receiver = this
      if (this && typeof this === 'object') Object.assign(this, {
        session: 'synthetic overwrite', generation: 'synthetic overwrite', sequence: -10, stopped: false,
      })
      rows.push(marker)
    })
    const signal = new AbortController().signal
    beginRcPhaseSession(signal, 0)
    for (let count = 0; count < 300; count++) traceRcPhase(signal, 'effect.setup')
    assert.strictEqual(receiver, undefined)
    assert.strictEqual(rows.length, 256)
    for (const [index, row] of rows.entries()) {
      assert.deepStrictEqual(Object.keys(row).sort(), ['generation', 'monotonic_ms', 'phase', 'schema', 'sequence', 'session'])
      assert.strictEqual(Object.isFrozen(row), true)
      assert.strictEqual(row.schema, 1)
      assert.strictEqual(row.generation, 0)
      assert.strictEqual(Number.isSafeInteger(row.session), true)
      assert.ok(row.session > 0)
      assert.strictEqual(row.sequence, index + 1)
      assert.strictEqual(Number.isFinite(row.monotonic_ms), true)
      assert.ok(row.monotonic_ms >= 0)
    }
    assert.strictEqual(rows[255].phase, 'trace.cap')
  }))

  test('throwing observer disables its aliases and releases the global delivery guard', () => withSyntheticGlobals(() => {
    const signal = new AbortController().signal
    let calls = 0
    setHook(() => { calls++; throw new Error('synthetic observer') })
    beginRcPhaseSession(signal, 2)
    const alias = bindRcPhase({}, signal)
    assert.doesNotThrow(() => traceRcPhase(signal, 'effect.setup'))
    traceRcPhase(signal, 'poll.begin')
    traceRcPhase(alias, 'scope.begin')
    const rows: Rows = []
    const other = session(3, rows)
    traceRcPhase(other, 'effect.setup')
    assert.strictEqual(calls, 1)
    assert.strictEqual(rows.length, 1)
    assert.strictEqual(rows[0].generation, 3)
  }))

  test('the generated cap is terminal after exactly 256 rows and aliases cannot bypass it', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    const signal = session(4, rows)
    const alias = bindRcPhase({}, signal)
    for (let count = 0; count < 400; count++) traceRcPhase(count % 2 ? alias : signal, 'poll.begin')
    assert.strictEqual(rows.length, 256)
    assert.strictEqual(rows.slice(0, 255).every(row => row.phase === 'poll.begin'), true)
    assert.strictEqual(rows[255].sequence, 256)
    assert.strictEqual(rows[255].phase, 'trace.cap')
    assert.strictEqual(rows[255].generation, 4)
    const nextRows: Rows = []
    traceRcPhase(session(5, nextRows), 'effect.setup')
    assert.strictEqual(nextRows.length, 1)
    assert.strictEqual(nextRows[0].sequence, 1)
  }))

  test('callback reentrance into the same and another context emits no nested rows', () => withSyntheticGlobals(() => {
    const rowsA: Rows = []
    const rowsB: Rows = []
    const signalB = session(7, rowsB)
    const signalA = new AbortController().signal
    setHook((marker: Readonly<RcPhaseMarker>) => {
      rowsA.push(marker)
      traceRcPhase(signalA, 'poll.begin')
      traceRcPhase(signalB, 'poll.begin')
    })
    beginRcPhaseSession(signalA, 6)
    traceRcPhase(signalA, 'effect.setup')
    assert.strictEqual(rowsA.length, 1)
    assert.deepStrictEqual(rowsB, [])
    traceRcPhase(signalB, 'effect.setup')
    assert.strictEqual(rowsB.length, 1)
    assert.strictEqual(rowsB[0].sequence, 1)
  }))

  for (const stage of ['performance getter', 'now getter', 'now function'] as const) {
    test(`${stage} reentrance is blocked before any nested delivery`, () => withSyntheticGlobals(() => {
      const rowsA: Rows = []
      const rowsB: Rows = []
      const signalA = session(8, rowsA)
      const signalB = session(9, rowsB)
      let accesses = 0
      const reenter = () => {
        accesses++
        traceRcPhase(signalA, 'poll.begin')
        traceRcPhase(signalB, 'poll.begin')
      }
      if (stage === 'performance getter') {
        Object.defineProperty(globalThis, 'performance', {
          configurable: true,
          get() { reenter(); return { now: () => 10 } },
        })
      } else if (stage === 'now getter') {
        const value = {}
        Object.defineProperty(value, 'now', { get() { reenter(); return () => 10 } })
        setClock(value)
      } else setClock({ now() { reenter(); return 10 } })
      traceRcPhase(signalA, 'effect.setup')
      assert.strictEqual(accesses, 1)
      assert.strictEqual(rowsA.length, 1)
      assert.deepStrictEqual(rowsB, [])
      traceRcPhase(signalB, 'effect.setup')
      assert.strictEqual(accesses, 2)
      assert.strictEqual(rowsB.length, 1)
    }))
  }

  for (const stage of ['performance getter', 'now getter', 'now function'] as const) {
    test(`${stage} throw stops only its context and clears the delivery guard`, () => withSyntheticGlobals(() => {
      const rows: Rows = []
      const signal = session(10, rows)
      if (stage === 'performance getter') {
        Object.defineProperty(globalThis, 'performance', {
          configurable: true, get() { throw new Error('synthetic clock') },
        })
      } else if (stage === 'now getter') {
        const value = {}
        Object.defineProperty(value, 'now', { get() { throw new Error('synthetic clock') } })
        setClock(value)
      } else setClock({ now() { throw new Error('synthetic clock') } })
      assert.doesNotThrow(() => traceRcPhase(signal, 'effect.setup'))
      clock()
      traceRcPhase(signal, 'poll.begin')
      assert.deepStrictEqual(rows, [])
      const otherRows: Rows = []
      traceRcPhase(session(11, otherRows), 'effect.setup')
      assert.strictEqual(otherRows.length, 1)
    }))
  }

  test('nonfinite, negative and missing clock values stop their context', () => withSyntheticGlobals(() => {
    for (const value of [NaN, Infinity, -1, undefined]) {
      const rows: Rows = []
      const signal = session(12, rows)
      setClock({ now: () => value })
      assert.doesNotThrow(() => traceRcPhase(signal, 'effect.setup'))
      clock()
      traceRcPhase(signal, 'poll.begin')
      assert.deepStrictEqual(rows, [])
    }
    for (const value of [0, 0.5]) {
      const rows: Rows = []
      const signal = session(13, rows)
      setClock({ now: () => value })
      traceRcPhase(signal, 'effect.setup')
      assert.strictEqual(rows.length, 1)
      assert.strictEqual(rows[0].monotonic_ms, value)
    }
  }))

  test('unknown phase and caller-supplied cap are ignored before clock access', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    const signal = session(14, rows)
    let reads = 0
    setClock({ now() { reads++; return 1 } })
    traceRcPhase(signal, 'synthetic.invalid' as RcPhaseName)
    traceRcPhase(signal, 'trace.cap')
    traceRcPhase(undefined, 'effect.setup')
    traceRcPhase({}, 'effect.setup')
    assert.strictEqual(reads, 0)
    assert.deepStrictEqual(rows, [])
    traceRcPhase(signal, 'effect.setup')
    assert.strictEqual(reads, 1)
    assert.strictEqual(rows[0].sequence, 1)
  }))

  test('binding preserves target identity and source wins over fallback', () => withSyntheticGlobals(() => {
    const sourceRows: Rows = []
    const fallbackRows: Rows = []
    const source = session(15, sourceRows)
    const fallback = session(16, fallbackRows)
    const target = Object.freeze({ sentinel: 1 })
    const keys = Object.getOwnPropertyNames(target)
    assert.strictEqual(bindRcPhase(target, source, fallback), target)
    assert.deepStrictEqual(Object.getOwnPropertyNames(target), keys)
    traceRcPhase(target, 'scope.begin')
    assert.strictEqual(sourceRows.length, 1)
    assert.deepStrictEqual(fallbackRows, [])
    const fallbackTarget = {}
    assert.strictEqual(bindRcPhase(fallbackTarget, {}, fallback), fallbackTarget)
    traceRcPhase(fallbackTarget, 'scope.begin')
    assert.strictEqual(fallbackRows.length, 1)
    const unbound = {}
    assert.strictEqual(bindRcPhase(unbound), unbound)
    traceRcPhase(unbound, 'scope.begin')
    assert.strictEqual(sourceRows.length, 1)
    assert.strictEqual(fallbackRows.length, 1)
  }))

  test('stopped source context cannot fall back to a live context', () => withSyntheticGlobals(() => {
    const stopped = new AbortController().signal
    setHook(() => { throw new Error('synthetic observer') })
    beginRcPhaseSession(stopped, 17)
    traceRcPhase(stopped, 'effect.setup')
    const rows: Rows = []
    const fallback = session(18, rows)
    traceRcPhase(bindRcPhase({}, stopped, fallback), 'scope.begin')
    assert.deepStrictEqual(rows, [])
    traceRcPhase(fallback, 'scope.begin')
    assert.strictEqual(rows.length, 1)
  }))

  test('reused signal becoming unobserved loses only its current mapping', () => withSyntheticGlobals(() => {
    for (const reason of ['absent', 'nonfunction', 'throwing getter', 'invalid generation'] as const) {
      const rows: Rows = []
      const signal = session(21, rows)
      const oldAlias = bindRcPhase({}, signal)
      traceRcPhase(signal, 'effect.setup')
      if (reason === 'absent') Reflect.deleteProperty(globalThis, hookName)
      else if (reason === 'nonfunction') setHook(null)
      else if (reason === 'throwing getter') Object.defineProperty(globalThis, hookName, {
        configurable: true, get() { throw new Error('synthetic observer') },
      })
      assert.doesNotThrow(() => beginRcPhaseSession(signal, reason === 'invalid generation' ? -1 : 22))
      traceRcPhase(signal, 'poll.begin')
      const reusedTarget = bindRcPhase({}, signal)
      traceRcPhase(reusedTarget, 'scope.begin')
      assert.strictEqual(rows.length, 1)
      // An already captured old alias remains attributed to its existing old session.
      traceRcPhase(oldAlias, 'scope.begin')
      assert.deepStrictEqual(rows.map(row => [row.generation, row.sequence]), [[21, 1], [21, 2]])
    }
  }))

  test('rebound observed transport and empty Response do not retain an unobserved source context', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    const observed = session(23, rows)
    const transport = Object.freeze({ sentinel: 1 })
    const response = new Response(null)
    const transportKeys = Object.getOwnPropertyNames(transport)
    const responseKeys = Object.getOwnPropertyNames(response)
    bindRcPhase(transport, observed)
    bindRcPhase(response, transport)
    traceRcPhase(response, 'body.read.begin')
    assert.strictEqual(rows.length, 1)
    const unobserved = new AbortController().signal
    assert.strictEqual(bindRcPhase(transport, unobserved), transport)
    assert.strictEqual(bindRcPhase(response, transport), response)
    traceRcPhase(transport, 'http.fetch.begin')
    traceRcPhase(response, 'body.read.begin')
    assert.strictEqual(rows.length, 1)
    assert.deepStrictEqual(Object.getOwnPropertyNames(transport), transportKeys)
    assert.deepStrictEqual(Object.getOwnPropertyNames(response), responseKeys)
  }))

  test('AbortSignal, linked signal, transport and empty Response identities share only the selected context', () => withSyntheticGlobals(() => {
    const rows: Rows = []
    const signal = session(24, rows)
    const linked = new AbortController().signal
    const transport = Object.freeze({ sentinel: 1 })
    const response = new Response(null)
    assert.strictEqual(bindRcPhase(linked, signal), linked)
    assert.strictEqual(bindRcPhase(transport, linked), transport)
    assert.strictEqual(bindRcPhase(response, undefined, transport), response)
    traceRcPhase(linked, 'scope.begin')
    traceRcPhase(transport, 'http.fetch.begin')
    traceRcPhase(response, 'body.read.begin')
    assert.deepStrictEqual(rows.map(row => [row.generation, row.sequence]), [[24, 1], [24, 2], [24, 3]])
    assert.strictEqual(new Set(rows.map(row => row.session)).size, 1)
  }))

  test('new generation preserves old alias attribution and captured hook', () => withSyntheticGlobals(() => {
    const rowsA: Rows = []
    const rowsB: Rows = []
    const signal = session(19, rowsA)
    const oldAlias = bindRcPhase({}, signal)
    traceRcPhase(oldAlias, 'effect.setup')
    setHook((marker: Readonly<RcPhaseMarker>) => rowsB.push(marker))
    beginRcPhaseSession(signal, 20)
    const newAlias = bindRcPhase({}, signal)
    traceRcPhase(oldAlias, 'poll.begin')
    traceRcPhase(newAlias, 'effect.setup')
    traceRcPhase(signal, 'poll.begin')
    assert.deepStrictEqual(rowsA.map(row => [row.generation, row.sequence]), [[19, 1], [19, 2]])
    assert.deepStrictEqual(rowsB.map(row => [row.generation, row.sequence]), [[20, 1], [20, 2]])
    assert.strictEqual(rowsA[0].session, rowsA[1].session)
    assert.strictEqual(rowsB[0].session, rowsB[1].session)
    assert.notStrictEqual(rowsA[0].session, rowsB[0].session)
  }))
})
