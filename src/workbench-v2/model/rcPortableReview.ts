import type { RcCorotationalReportSummary, RcCorotationalStateChoice } from './rcCorotationalReportReview'
import type { RcCorotationalReportResponse } from './rcCorotationalReportSchema'
import type { RcResultGeometry } from './rcResultVisualization'
import { RC_PORTABLE_REVIEW_MAX_BYTES } from './rcPortableReviewSchema'

export { RC_PORTABLE_REVIEW_MAX_BYTES } from './rcPortableReviewSchema'
export interface RcPortableReview {
  custody: 'portable_unverified_origin'
  summary: RcCorotationalReportSummary
  state(index: number): Promise<RcCorotationalReportResponse>
  statePage(start: number, count: number): Promise<RcCorotationalStateChoice[]>
  geometry(): Promise<RcResultGeometry>
  requestDownload(): Promise<Blob>
  reportDownload(): Promise<Blob>
  onFailure(listener: (message: string) => void): () => void
  dispose(): void
}

/** Opens only supplied bytes. The isolated worker has no transport, account or
 * execution interface. Ownership of an exact input buffer is transferred.
 */
export async function openRcPortableReview(bytes: Uint8Array, signal?: AbortSignal): Promise<RcPortableReview> {
  signal?.throwIfAborted()
  if (!(bytes instanceof Uint8Array) || !bytes.byteLength || bytes.byteLength > RC_PORTABLE_REVIEW_MAX_BYTES) throw new Error('rc_portable_review_file_too_large')
  const worker = new Worker(new URL('./rcPortableReview.worker.ts', import.meta.url), { type: 'module' })
  const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const listeners = new Set<(message: string) => void>()
  let sequence = 0, failure: string | null = null
  const abort = () => stop('rc_portable_review_disposed')
  function stop(message = 'rc_portable_review_disposed'): void {
    if (failure) return
    failure = message; worker.terminate(); signal?.removeEventListener('abort', abort)
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error(message)) }
    pending.clear()
    for (const listener of listeners) listener(message)
    listeners.clear()
  }
  signal?.addEventListener('abort', abort, { once: true })
  worker.onerror = () => stop('rc_portable_review_worker_failed')
  worker.onmessageerror = () => stop('rc_portable_review_worker_message_invalid')
  worker.onmessage = ({ data }) => {
    if (!data || !Number.isSafeInteger(data.id)) { stop('rc_portable_review_worker_message_invalid'); return }
    const item = pending.get(data.id)
    if (!item) return
    if (data.error) { stop(typeof data.error === 'string' && /^rc_portable_review_[a-z_]+$/.test(data.error) ? data.error : 'rc_portable_review_worker_failed'); return }
    pending.delete(data.id); clearTimeout(item.timer)
    if (data.operationError) item.reject(new Error(typeof data.operationError === 'string' && /^rc_portable_review_[a-z_]+$/.test(data.operationError)
      ? data.operationError : 'rc_portable_review_operation_invalid'))
    else item.resolve(data.value)
  }
  function call<T>(type: string, payload: object = {}, transfer: Transferable[] = []): Promise<T> {
    if (failure) return Promise.reject(new Error(failure))
    if (pending.size >= 16) return Promise.reject(new Error('rc_portable_review_rpc_limit'))
    const id = ++sequence
    return new Promise<T>((resolve, reject) => {
      pending.set(id, { resolve, reject, timer: setTimeout(() => stop('rc_portable_review_worker_timeout'), 60000) })
      try { worker.postMessage({ id, type, ...payload }, transfer) } catch { stop('rc_portable_review_worker_failed') }
    })
  }
  try {
    // Never transfer unrelated bytes outside a caller-provided subarray.
    const input = bytes.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength ? bytes : bytes.slice()
    const summary = await call<RcCorotationalReportSummary>('initialize', { bytes: input }, [input.buffer])
    signal?.throwIfAborted()
    return {
      custody: 'portable_unverified_origin', summary,
      state: index => call('state', { index }),
      statePage: (start, count) => call('statePage', { start, count }),
      geometry: () => call('geometry'),
      requestDownload: () => call('requestDownload'),
      reportDownload: () => call('reportDownload'),
      onFailure(listener) { if (failure) listener(failure); else listeners.add(listener); return () => { listeners.delete(listener) } },
      dispose: stop,
    }
  } catch (error) { stop(); throw error }
}
