import { expect, test } from '@playwright/test'
import { openRcReviewWorker } from '../../src/workbench-v2/model/rcReviewWorker'

function fakeWorker() {
  const worker = {
    onmessage: null as ((event: MessageEvent) => void) | null,
    onerror: null as ((event: ErrorEvent) => void) | null,
    onmessageerror: null as ((event: MessageEvent) => void) | null,
    terminated: false,
    postMessage(_value: unknown) {},
    terminate() { this.terminated = true },
  }
  return { worker, emit(data: unknown) { worker.onmessage?.({ data } as MessageEvent) } }
}

function fakeClock() {
  const realSetTimeout = globalThis.setTimeout, realClearTimeout = globalThis.clearTimeout
  const previousNow = Object.getOwnPropertyDescriptor(performance, 'now')
  let now = 0, nextId = 0
  const timers = new Map<number, { due: number; callback: () => void }>()
  Object.defineProperty(performance, 'now', { configurable: true, value: () => now })
  globalThis.setTimeout = ((callback: () => void, delay: number) => {
    const id = ++nextId
    timers.set(id, { due: now + delay, callback })
    return id
  }) as typeof setTimeout
  globalThis.clearTimeout = ((id: number) => { timers.delete(id) }) as typeof clearTimeout
  return {
    advance(milliseconds: number) {
      const target = now + milliseconds
      while (true) {
        const next = [...timers.entries()].filter(([, timer]) => timer.due <= target)
          .sort(([leftId, left], [rightId, right]) => left.due - right.due || leftId - rightId)[0]
        if (!next) break
        now = next[1].due; timers.delete(next[0]); next[1].callback()
      }
      now = target
    },
    restore() {
      globalThis.setTimeout = realSetTimeout; globalThis.clearTimeout = realClearTimeout
      if (previousNow) Object.defineProperty(performance, 'now', previousNow)
      else delete (performance as any).now
    },
  }
}

async function connection() {
  const previousLocation = (globalThis as any).location
  ;(globalThis as any).location = new URL('http://localhost/')
  const fake = fakeWorker(), controller = new AbortController()
  try {
    const opened = await openRcReviewWorker(() => fake.worker as unknown as Worker,
      'http://localhost/result.json', controller.signal, undefined, 'bounded-search-artifact-progress')
    return { ...fake, controller, opened, restoreLocation() {
      if (previousLocation === undefined) delete (globalThis as any).location
      else (globalThis as any).location = previousLocation
    } }
  } catch (error) {
    if (previousLocation === undefined) delete (globalThis as any).location
    else (globalThis as any).location = previousLocation
    throw error
  }
}

test('search initialization keeps 60-second idle failure despite prior artifact progress', async () => {
  const review = await connection(), clock = fakeClock()
  let pending: Promise<unknown>
  try {
    pending = review.opened.initialize()
    clock.advance(59000); review.emit({ id: 1, progress: 'artifact_read' })
    clock.advance(59999); expect(review.worker.terminated).toBe(false)
    clock.advance(1); expect(review.worker.terminated).toBe(true)
  } finally { clock.restore(); review.restoreLocation() }
  await expect(pending!).rejects.toThrow('rc_design_unavailable')
})

test('search initialization has a five-minute total limit even with continuing reads', async () => {
  const review = await connection(), clock = fakeClock()
  let pending: Promise<unknown>
  try {
    pending = review.opened.initialize()
    for (let i = 0; i < 5; i += 1) {
      clock.advance(59000); review.emit({ id: 1, progress: 'artifact_read' })
      expect(review.worker.terminated).toBe(false)
    }
    clock.advance(4999); expect(review.worker.terminated).toBe(false)
    clock.advance(1); expect(review.worker.terminated).toBe(true)
  } finally { clock.restore(); review.restoreLocation() }
  await expect(pending!).rejects.toThrow('rc_design_unavailable')
})

test('progress is accepted only during initialization; abort and later calls fail closed', async () => {
  const review = await connection()
  try {
    const initialized = review.opened.initialize<{ status: string }>()
    review.emit({ id: 1, progress: 'artifact_read' })
    review.emit({ id: 1, value: { status: 'checked' } })
    await expect(initialized).resolves.toEqual({ status: 'checked' })
    const later = review.opened.call('metadata', { role: 'result' })
    review.emit({ id: 2, progress: 'artifact_read' })
    await expect(later).rejects.toThrow('rc_design_unavailable')
    expect(review.worker.terminated).toBe(true)
  } finally { review.opened.dispose(); review.restoreLocation() }
  const aborted = await connection()
  try {
    const pending = aborted.opened.initialize()
    aborted.emit({ id: 1, progress: 'artifact_read' })
    aborted.controller.abort()
    await expect(pending).rejects.toThrow('rc_design_unavailable')
    expect(aborted.worker.terminated).toBe(true)
  } finally { aborted.opened.dispose(); aborted.restoreLocation() }
})

test('later download keeps the ordinary 60-second limit', async () => {
  const review = await connection()
  try {
    const initialized = review.opened.initialize()
    review.emit({ id: 1, value: { status: 'checked' } })
    await initialized
    const clock = fakeClock()
    let pending: Promise<unknown>
    try {
      pending = review.opened.call('metadata', { role: 'result' })
      clock.advance(59999); expect(review.worker.terminated).toBe(false)
      clock.advance(1); expect(review.worker.terminated).toBe(true)
    } finally { clock.restore() }
    await expect(pending!).rejects.toThrow('rc_design_unavailable')
  } finally { review.opened.dispose(); review.restoreLocation() }
})

test('malformed progress and terminal messages cannot publish a review', async () => {
  for (const malformed of [{ id: 1, progress: 'artifact_read', value: {} }, { id: 1 }]) {
    const review = await connection()
    try {
      const pending = review.opened.initialize()
      review.emit(malformed)
      await expect(pending).rejects.toThrow('rc_design_unavailable')
      expect(review.worker.terminated).toBe(true)
    } finally { review.opened.dispose(); review.restoreLocation() }
  }
})
