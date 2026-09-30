import type { RcJobReview } from './rcJobReview'
import type { RcJobSummary } from './rcJobSchema'

export async function loadRcHistoryFileReview(file: File, signal: AbortSignal, progress: (count: number) => void): Promise<RcJobReview> {
  signal.throwIfAborted()
  const worker = new Worker(new URL('./rcHistoryFile.worker.ts', import.meta.url), { type: 'module' })
  const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const listeners = new Set<(message: string) => void>()
  let sequence = 0, failure: string | null = null
  function stop(message = 'rc_review_history_disposed'): void {
    if (failure) return
    failure = message; worker.terminate(); signal.removeEventListener('abort', abort)
    for (const call of pending.values()) { clearTimeout(call.timer); call.reject(new Error(message)) }
    pending.clear()
    for (const listener of listeners) listener(message)
    listeners.clear()
  }
  const abort = () => stop()
  signal.addEventListener('abort', abort, { once: true })
  worker.onerror = () => stop('rc_review_history_worker_failed')
  worker.onmessageerror = () => stop('rc_review_history_worker_message_invalid')
  worker.onmessage = ({ data }) => {
    const call = pending.get(data.id)
    if (!call) return
    if (data.progress !== undefined) { progress(data.progress); return }
    if (data.error) { stop('rc_review_history_invalid'); return }
    pending.delete(data.id); clearTimeout(call.timer); call.resolve(data.value)
  }
  function call<T>(type: string, payload: object): Promise<T> {
    if (failure) return Promise.reject(new Error(failure))
    const id = ++sequence
    return new Promise<T>((resolve, reject) => {
      pending.set(id, { resolve, reject, timer: setTimeout(() => stop('rc_review_history_timeout'), 120000) })
      try { worker.postMessage({ id, type, ...payload }) } catch { stop('rc_review_history_worker_failed') }
    })
  }
  try {
    const summary = await call<RcJobSummary>('initialize', { file })
    return {
      summary, epoch: index => call('epoch', { index }),
      material: () => Promise.reject(new Error('rc_review_history_requires_material_page')),
      materialPage: (memberId, integrationPoint, fiberIndex, start, count) => call('materialPage', { memberId, integrationPoint, fiberIndex, start, count }),
      download: role => call('download', { role }),
      onFailure(listener) { if (failure) listener(failure); else listeners.add(listener); return () => { listeners.delete(listener) } },
      dispose: stop,
    }
  } catch (error) { stop(); throw error }
}
