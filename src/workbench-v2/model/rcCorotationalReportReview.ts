import { JobArtifactError, readBoundedJobBytes, type JobReadTransport } from './jobTransport'
import type { WorkbenchJobView } from './jobSchema'
import { RC_REVIEW_DEFAULT_RESULT_BYTES, RC_REVIEW_MAX_RESULT_BYTES } from './rcJobReviewBudget'
import type { RcCorotationalReportResponse } from './rcCorotationalReportSchema'

export interface RcCorotationalStateChoice {
  state_index: number; phase: 'preload' | 'control'; control_displacement_m: number; load_factor: number; checkpoint_hash: string
}
export interface RcCorotationalReportSummary {
  jobId: string; reportId: string; contentHash: string; reportHash: string; caseId: string; sourceRevision: string
  targets: number[]; control: { node_id: string; component: 'UX' | 'UY'; unit: 'm' }; stateCount: number; nodeCount: number
  attemptProgress: { completed: number; maximum: number }; targetProgress: { completed: number; total: number }
  reservedInvocations: number; maximumInvocations: number; recordedInvocations: number; pendingInvocations: number
  unknownWork: boolean; knownWork: { preload_solver_calls: number; restart_replay_solver_calls: number; control_solver_calls: number }
  constantLoads: Array<[string, string, number]>
}
export interface RcCorotationalReportReview {
  summary: RcCorotationalReportSummary
  maximumBytes: number
  state(index: number): Promise<RcCorotationalReportResponse>
  statePage(start: number, count: number): Promise<RcCorotationalStateChoice[]>
  download(): Promise<Blob>
  reopen(bytes: Uint8Array): Promise<RcCorotationalReportSummary>
  onFailure(listener: (message: string) => void): () => void
  dispose(): void
}
export function corotationalReportByteLimit(maximum = RC_REVIEW_DEFAULT_RESULT_BYTES): number {
  if (!Number.isSafeInteger(maximum) || maximum <= 0 || maximum > RC_REVIEW_MAX_RESULT_BYTES) throw new JobArtifactError('rc_review_budget_invalid')
  // The saved report endpoint has its own 64 MiB ceiling, independently of the original result.
  return Math.min(maximum, RC_REVIEW_DEFAULT_RESULT_BYTES)
}

/** Authenticate the service snapshot and retain all parsed response arrays inside one worker.
 * The report is a derived read. Original result/evidence bytes are service custody,
 * not an independently replayed browser result pair.
 */
export async function loadRcCorotationalReportReview(
  job: WorkbenchJobView, transport: JobReadTransport, signal?: AbortSignal, maximum?: number,
): Promise<RcCorotationalReportReview> {
  const limit = corotationalReportByteLimit(maximum)
  if (job.status !== 'succeeded' || !job.result || !job.evidence || !transport.tenantId || !transport.getCorotationalReport) throw new JobArtifactError('rc_corotational_report_source_unavailable')
  if (job.request.byte_length > 16 * 1024 * 1024) throw new JobArtifactError('rc_request_too_large')
  signal?.throwIfAborted()
  await transport.verifyAuthorizationScope?.()
  const requestResponse = await transport.get('request', job.request.media_type)
  if (!requestResponse.ok) throw new JobArtifactError(`rc_request_HTTP_${requestResponse.status}`)
  const requestBytes = await readBoundedJobBytes(requestResponse, 16 * 1024 * 1024, 'rc request', job.request.byte_length)
  signal?.throwIfAborted()
  const response = await transport.getCorotationalReport({ requestHash: job.request.content_hash, resultHash: job.result.content_hash, evidenceHash: job.evidence.content_hash })
  if (!response.ok) throw new JobArtifactError(`rc_corotational_report_HTTP_${response.status}`)
  const contentHash = response.headers.get('x-structural-report-sha256'), reportId = response.headers.get('x-structural-report-id')
  if (!contentHash || !/^sha256:[0-9a-f]{64}$/.test(contentHash) || reportId !== `rcc_${contentHash.slice(7)}`) {
    try { await response.body?.cancel() } catch { /* Preserve header failure. */ }
    throw new JobArtifactError('rc_corotational_report_headers_invalid')
  }
  const bytes = await readBoundedJobBytes(response, limit, 'rc_corotational_report')
  signal?.throwIfAborted()
  const worker = new Worker(new URL('./rcCorotationalReportReview.worker.ts', import.meta.url), { type: 'module' })
  const pending = new Map<number, { type: string; resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const listeners = new Set<(message: string) => void>()
  let sequence = 0, failure: string | null = null, reopening = false
  const abort = () => stop('rc_corotational_report_disposed')
  function stop(message = 'rc_corotational_report_disposed'): void {
    if (failure) return
    failure = message; worker.terminate(); signal?.removeEventListener('abort', abort)
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new JobArtifactError(message)) }
    pending.clear(); for (const listener of listeners) listener(message); listeners.clear()
  }
  signal?.addEventListener('abort', abort, { once: true })
  worker.onerror = () => stop('rc_corotational_report_worker_failed')
  worker.onmessageerror = () => stop('rc_corotational_report_worker_message_invalid')
  worker.onmessage = ({ data }) => {
    if (!data || !Number.isSafeInteger(data.id)) { stop('rc_corotational_report_worker_message_invalid'); return }
    const item = pending.get(data.id); if (!item) return
    if (data.error) { stop(/^rc_corotational_report_[a-z_]+$/.test(data.error) ? data.error : 'rc_corotational_report_worker_failed'); return }
    pending.delete(data.id); clearTimeout(item.timer)
    if (data.operationError) item.reject(new JobArtifactError(/^rc_corotational_report_[a-z_]+$/.test(data.operationError) ? data.operationError : 'rc_corotational_report_reopen_invalid'))
    else item.resolve(data.value)
  }
  function call<T>(type: string, payload: object = {}, transfer: Transferable[] = []): Promise<T> {
    if (failure) return Promise.reject(new JobArtifactError(failure))
    if (pending.size >= 16) return Promise.reject(new JobArtifactError('rc_corotational_report_rpc_limit'))
    const id = ++sequence
    return new Promise<T>((resolve, reject) => {
      pending.set(id, { type, resolve, reject, timer: setTimeout(() => stop('rc_corotational_report_worker_timeout'), 60000) })
      try { worker.postMessage({ id, type, ...payload }, transfer) } catch { stop('rc_corotational_report_worker_failed') }
    })
  }
  try {
    const summary = await call<RcCorotationalReportSummary>('initialize', { job, tenantId: transport.tenantId, requestBytes, bytes, reportId, contentHash, maximumBytes: limit }, [requestBytes.buffer, bytes.buffer])
    await transport.verifyAuthorizationScope?.()
    signal?.throwIfAborted()
    const authorized = async <T,>(operation: () => Promise<T>): Promise<T> => {
      try {
        await transport.verifyAuthorizationScope?.()
        signal?.throwIfAborted()
        const result = await operation()
        await transport.verifyAuthorizationScope?.()
        signal?.throwIfAborted()
        return result
      } catch (error) {
        if (error instanceof Error && /authorization_|AbortError/.test(error.message + error.name)) stop('rc_corotational_report_authorization_changed')
        throw error
      }
    }
    return {
      summary, maximumBytes: limit,
      state: (index) => authorized(() => call('state', { index })),
      statePage: (start, count) => authorized(() => call('statePage', { start, count })),
      download: () => authorized(() => call('download')),
      reopen: (fileBytes) => {
        if (!(fileBytes instanceof Uint8Array) || fileBytes.byteLength === 0 || fileBytes.byteLength > limit) return Promise.reject(new JobArtifactError('rc_corotational_report_too_large'))
        if (reopening) return Promise.reject(new JobArtifactError('rc_corotational_report_rpc_busy'))
        reopening = true
        const transfer = fileBytes.slice()
        return authorized<RcCorotationalReportSummary>(() => call('reopen', { bytes: transfer }, [transfer.buffer])).finally(() => { reopening = false })
      },
      onFailure(listener) { if (failure) listener(failure); else listeners.add(listener); return () => { listeners.delete(listener) } },
      dispose: stop,
    }
  } catch (error) { stop(); throw error }
}
