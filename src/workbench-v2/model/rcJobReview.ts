import { admitRcReviewArtifacts } from './rcJobReviewBudget'
import type { WorkbenchJobView } from './jobSchema'
import { JobArtifactError, readBoundedJobBytes, type JobReadTransport } from './jobTransport'
import type { RcArtifacts, RcJobSummary, RcObject } from './rcJobSchema'
import type { RcQuantityReportReference, RcQuantityReportReview } from './rcQuantityReportSchema'

export interface RcJobReview {
  summary: RcJobSummary
  epoch(index: number): Promise<RcObject>
  material(memberId: string, integrationPoint: number, fiberIndex: number): Promise<RcObject[]>
  materialPage?(memberId: string, integrationPoint: number, fiberIndex: number, start: number, count: number): Promise<RcObject[]>
  download(role: string): Promise<Blob>
  verifyQuantityReport?(bytes: Uint8Array, reference?: RcQuantityReportReference): Promise<RcQuantityReportReview>
  downloadQuantityReport?(reportId: string): Promise<Blob>
  onFailure(listener: (message: string) => void): () => void
  dispose(): void
}

export async function loadRcJobReview(
  job: WorkbenchJobView, transport: JobReadTransport, signal?: AbortSignal, resultMaximum?: number,
): Promise<RcJobReview> {
  const limits = admitRcReviewArtifacts(job, resultMaximum)
  const artifacts: RcArtifacts = {}
  for (const role of ['request', 'checkpoint', 'result', 'evidence'] as const) {
    const reference = job[role]
    if (!reference) continue
    const maximum = limits[role]
    const response = await transport.get(role, reference.media_type)
    if (!response.ok) throw new JobArtifactError(`rc_${role}_HTTP_${response.status}`)
    artifacts[role] = await readBoundedJobBytes(response, maximum, `rc ${role}`, reference.byte_length)
  }
  signal?.throwIfAborted()
  const worker = new Worker(new URL('./rcJobReview.worker.ts', import.meta.url), { type: 'module' })
  const pending = new Map<number, { type: string; resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const listeners = new Set<(message: string) => void>()
  let sequence = 0, failure: string | null = null
  function stop(message = 'rc_review_disposed'): void {
    if (failure) return
    failure = message
    worker.terminate()
    signal?.removeEventListener('abort', abort)
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new JobArtifactError(message)) }
    pending.clear()
    for (const listener of listeners) listener(message)
    listeners.clear()
  }
  const abort = () => stop()
  signal?.addEventListener('abort', abort, { once: true })
  worker.onerror = () => stop('rc_review_worker_failed')
  worker.onmessageerror = () => stop('rc_review_worker_message_invalid')
  worker.onmessage = ({ data }) => {
    const item = pending.get(data.id)
    if (!item) return
    if (data.error) { stop(/^rc_review_[a-z_]+$/.test(data.error) ? data.error : 'rc_review_worker_failed'); return }
    if (data.quantityError && ['quantityReport', 'quantityDownload'].includes(item.type)) {
      pending.delete(data.id); clearTimeout(item.timer)
      item.reject(new JobArtifactError(/^rc_review_[a-z_]+$/.test(data.quantityError) ? data.quantityError : 'rc_review_quantity_contract_invalid'))
      return
    }
    pending.delete(data.id); clearTimeout(item.timer); item.resolve(data.value)
  }
  function call<T>(type: string, payload: object, transfer: Transferable[] = []): Promise<T> {
    if (failure) return Promise.reject(new JobArtifactError(failure))
    const id = ++sequence
    return new Promise<T>((resolve, reject) => {
      pending.set(id, { type, resolve, reject, timer: setTimeout(() => {
        if (type === 'quantityReport' || type === 'quantityDownload') {
          pending.delete(id); reject(new JobArtifactError('rc_review_quantity_timeout'))
        } else stop('rc_review_worker_timeout')
      }, 60000) })
      try { worker.postMessage({ id, type, ...payload }, transfer) } catch {
        if (type === 'quantityReport' || type === 'quantityDownload') {
          const item = pending.get(id)
          if (item) clearTimeout(item.timer)
          pending.delete(id); reject(new JobArtifactError('rc_review_quantity_message_invalid'))
        } else stop('rc_review_worker_failed')
      }
    })
  }
  try {
    const summary = await call<RcJobSummary>('initialize', { job, artifacts, tenantId: (transport as JobReadTransport & { tenantId?: string }).tenantId }, Object.values(artifacts).map((bytes) => bytes.buffer))
    return {
      summary,
      epoch: (index) => call('epoch', { index }),
      material: (memberId, integrationPoint, fiberIndex) => call('material', { memberId, integrationPoint, fiberIndex }),
      download: (role) => call('download', { role }),
      verifyQuantityReport: (bytes, reference) => {
        // Copy only the bounded companion so its caller can retain the received
        // bytes; never copy or retransmit the original numerical result arrays.
        if (!(bytes instanceof Uint8Array) || bytes.byteLength === 0) return Promise.reject(new JobArtifactError('rc_review_quantity_report_invalid'))
        if (bytes.byteLength > 4 * 1024 * 1024) return Promise.reject(new JobArtifactError('rc_review_quantity_report_too_large'))
        const transfer = bytes.slice()
        return call('quantityReport', { bytes: transfer, reference }, [transfer.buffer])
      },
      downloadQuantityReport: (reportId) => call('quantityDownload', { reportId }),
      onFailure(listener) {
        if (failure) listener(failure)
        else listeners.add(listener)
        return () => { listeners.delete(listener) }
      },
      dispose: stop,
    }
  } catch (error) { stop(); throw error }
}
