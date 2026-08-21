import { parseNativeJsonStrict, validateNativeFrameJobView } from './nativeFrameProvider'

const MODEL_MAX_BYTES = 2 * 1024 * 1024
const RESPONSE_MAX_BYTES = 64 * 1024
const POLL_INTERVAL_MS = 100
const STABLE_ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const JOB_ID = /^job_[0-9a-f]{32}$/
const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i

export type NativeFrameRunStatus = 'succeeded' | 'failed' | 'cancelled'

export interface NativeFrameRunRequest {
  submissionUrl: string
  jobId: string
  modelIrJson: string
  loadSource: { kind: 'pattern' | 'combination'; id: string }
  resultId: string
  reportId: string
  onQueued?: (jobViewUrl: string) => void
}

export interface NativeFrameRunOutcome {
  status: NativeFrameRunStatus
  jobId: string
  jobViewUrl: string
  error: { code: string; detail: string } | null
}

export function createNativeFrameJobId(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return `job_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`
}

export async function readModelIrFile(file: File): Promise<string> {
  if (file.size < 2 || file.size > MODEL_MAX_BYTES) {
    throw new Error('ModelIR file is empty or exceeds the 2 MiB limit')
  }
  const bytes = new Uint8Array(await file.arrayBuffer())
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new Error('ModelIR file is not valid UTF-8')
  }
}

export async function submitAndRunNativeFrameJob(
  request: NativeFrameRunRequest,
  signal?: AbortSignal,
): Promise<NativeFrameRunOutcome> {
  const submissionUrl = new URL(request.submissionUrl, window.location.href)
  if (submissionUrl.origin !== window.location.origin || !JOB_ID.test(request.jobId)) {
    throw new Error('Native workstation submission origin or job identity is invalid')
  }
  for (const [label, value] of [
    ['load source', request.loadSource.id],
    ['result', request.resultId],
    ['report', request.reportId],
  ] as const) {
    if (!STABLE_ID.test(value)) throw new Error(`${label} identity is invalid`)
  }
  const modelBytes = new TextEncoder().encode(request.modelIrJson)
  if (modelBytes.byteLength < 2 || modelBytes.byteLength > MODEL_MAX_BYTES) {
    throw new Error('ModelIR text is empty or exceeds the 2 MiB limit')
  }
  const submission = {
    schema_version: 'structural-native-linear-frame3d-job-submission.v1',
    job_id: request.jobId,
    load_source: request.loadSource,
    result_id: request.resultId,
    report_id: request.reportId,
    model_ir_json: request.modelIrJson,
    claim_boundary: 'browser_submission_to_bounded_loopback_native_job_not_result_design_or_release_authority',
  }
  const queued = await postJson(submissionUrl, submission, signal)
  if (queued.job_id !== request.jobId || queued.status !== 'queued') {
    throw new Error('Native workstation did not return the exact queued job identity')
  }
  const runUrl = new URL(`${submissionUrl.pathname.replace(/\/$/, '')}/${request.jobId}/run`, submissionUrl)
  const jobViewUrl = new URL(
    `${submissionUrl.pathname.replace(/\/$/, '')}/${request.jobId}/view.json`,
    submissionUrl,
  ).toString()
  request.onQueued?.(jobViewUrl)
  let runSettled = false
  const runCompletion = postJson(runUrl, {}, signal).then(
    (view) => {
      runSettled = true
      return { view, error: null }
    },
    (error: unknown) => {
      runSettled = true
      return { view: null, error }
    },
  )
  while (!runSettled) {
    await waitForPoll(signal)
    if (runSettled) break
    const polled = await getJson(new URL(jobViewUrl), signal)
    if (polled.job_id !== request.jobId) {
      throw new Error('Native workstation polled a different job identity')
    }
    if (polled.status === 'succeeded' || polled.status === 'failed' || polled.status === 'cancelled') break
  }
  const completed = await runCompletion
  if (completed.error) throw completed.error
  const terminal = completed.view
  if (!terminal) throw new Error('Native workstation run ended without a terminal response')
  if (terminal.job_id !== request.jobId
    || (terminal.status !== 'succeeded' && terminal.status !== 'failed' && terminal.status !== 'cancelled')) {
    throw new Error('Native workstation did not return a terminal view for the submitted job')
  }
  if (terminal.status === 'succeeded') {
    return { status: 'succeeded', jobId: request.jobId, jobViewUrl, error: null }
  }
  return terminal.status === 'failed'
    ? { status: 'failed', jobId: request.jobId, jobViewUrl, error: terminal.error }
    : { status: 'cancelled', jobId: request.jobId, jobViewUrl, error: terminal.cancellation }
}

export async function cancelNativeFrameJob(
  submissionUrlValue: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<NativeFrameRunOutcome> {
  const submissionUrl = new URL(submissionUrlValue, window.location.href)
  if (submissionUrl.origin !== window.location.origin || !JOB_ID.test(jobId)) {
    throw new Error('Native workstation cancellation origin or job identity is invalid')
  }
  const cancelUrl = new URL(`${submissionUrl.pathname.replace(/\/$/, '')}/${jobId}/cancel`, submissionUrl)
  const jobViewUrl = new URL(
    `${submissionUrl.pathname.replace(/\/$/, '')}/${jobId}/view.json`,
    submissionUrl,
  ).toString()
  const terminal = await postJson(cancelUrl, {}, signal)
  if (terminal.job_id !== jobId || terminal.status !== 'cancelled') {
    throw new Error('Native workstation did not return the cancelled submitted job')
  }
  return {
    status: 'cancelled',
    jobId,
    jobViewUrl,
    error: terminal.cancellation,
  }
}

async function postJson(url: URL, body: unknown, signal?: AbortSignal) {
  return requestJobView(url, {
    method: 'POST',
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, signal)
}

async function getJson(url: URL, signal?: AbortSignal) {
  return requestJobView(url, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  }, signal)
}

async function requestJobView(url: URL, init: RequestInit, signal?: AbortSignal) {
  const response = await fetch(url, { ...init, signal })
  const contentType = response.headers.get('content-type') ?? ''
  if (!JSON_CONTENT_TYPE.test(contentType)) {
    throw new Error('Native workstation response content type is invalid')
  }
  const declared = Number(response.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > RESPONSE_MAX_BYTES) {
    throw new Error('Native workstation response exceeds the size limit')
  }
  const bytes = new Uint8Array(await response.arrayBuffer())
  if (bytes.byteLength > RESPONSE_MAX_BYTES) {
    throw new Error('Native workstation response exceeds the size limit')
  }
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new Error('Native workstation response is not valid UTF-8')
  }
  if (!response.ok) {
    throw new Error(`Native workstation returned HTTP ${response.status}`)
  }
  return validateNativeFrameJobView(parseNativeJsonStrict(text))
}

function waitForPoll(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    const error = new Error('Native workstation polling was aborted')
    error.name = 'AbortError'
    return Promise.reject(error)
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener('abort', abort)
      resolve()
    }, POLL_INTERVAL_MS)
    const abort = () => {
      window.clearTimeout(timeout)
      const error = new Error('Native workstation polling was aborted')
      error.name = 'AbortError'
      reject(error)
    }
    signal?.addEventListener('abort', abort, { once: true })
  })
}
