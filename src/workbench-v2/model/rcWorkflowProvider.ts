import { sha256Bytes } from './checksum'
import { readWorkbenchJobViewResponse } from './jobProvider'
import { validateWorkbenchJobView, type WorkbenchJobView } from './jobSchema'
import { JobArtifactError, readBoundedJobBytes, type RcJobTransport, type RcReportPage } from './jobTransport'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { fields, rawValues } from './rcJobSchema'
import {
  parseRcDeclaredPrices, parseRcQuantityReportIndex, parseRcQuantityReportReference,
  type RcDeclaredPrices, type RcQuantityReportIndex, type RcQuantityReportReference,
} from './rcQuantityReportSchema'

export { SUBMIT_MAX_BYTES } from './jobTransport'
export const REQUEST_MAX_BYTES = 16 * 1024 * 1024
export const QUANTITY_REPORT_MAX_BYTES = 4 * 1024 * 1024
const REPORT_INDEX_MAX_BYTES = 256 * 1024

function validatedJob(job: WorkbenchJobView): WorkbenchJobView {
  const validation = validateWorkbenchJobView(job)
  if (!validation.ok || !validation.value) throw new JobArtifactError('job_view_invalid')
  return validation.value
}

function reportScope(transport: RcJobTransport, job: WorkbenchJobView): { tenant_id: string; job_id: string } {
  validatedJob(job)
  if (!transport.tenantId) throw new JobArtifactError('job_authorization_required')
  if (job.status !== 'succeeded' || !job.result || !job.evidence
    || job.result.media_type !== 'application/vnd.structural-analysis.rc-fiber-job-result+json') {
    throw new JobArtifactError('rc_report_source_not_succeeded')
  }
  return { tenant_id: transport.tenantId, job_id: job.job_id }
}

function parseJson(bytes: Uint8Array, label: string): unknown {
  function finite(value: unknown, depth = 0): void {
    if (depth > 64 || (typeof value === 'number' && !Number.isFinite(value))) throw new Error('invalid')
    if (Array.isArray(value)) value.forEach((entry) => finite(entry, depth + 1))
    else if (value && typeof value === 'object') Object.values(value).forEach((entry) => finite(entry, depth + 1))
  }
  try {
    const value = parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
    finite(value)
    return value
  } catch {
    throw new JobArtifactError(`${label}_json_invalid`)
  }
}

async function jsonResponse(response: Response, maximum: number, label: string): Promise<unknown> {
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  return parseJson(await readBoundedJobBytes(response, maximum, label), label)
}

function safeSchema<T>(parse: () => T, label: string): T {
  try { return parse() } catch { throw new JobArtifactError(`${label}_invalid`) }
}

/** The caller retains these exact original bytes and key for an uncertain retry. */
export async function submitRcJob(transport: RcJobTransport, bytes: Uint8Array, idempotencyKey: string): Promise<WorkbenchJobView> {
  return readWorkbenchJobViewResponse(await transport.submit(bytes, idempotencyKey))
}

/** Compare Python JSON values after service key/whitespace/number normalization.
 * Keep integers exact with BigInt, and floating tokens as their finite binary64
 * values. Do not reconstruct raw bytes or compare a local raw SHA to the
 * service's canonical request SHA.
 */
function sameSubmittedValues(leftRaw: string, rightRaw: string): boolean {
  const left = leftRaw.trim(), right = rightRaw.trim()
  if (left[0] === '{' && right[0] === '{') {
    const a = left.slice(1, -1).trim() ? fields(left) : new Map()
    const b = right.slice(1, -1).trim() ? fields(right) : new Map()
    return a.size === b.size && [...a].every(([key, row]) => b.has(key) && sameSubmittedValues(row.value, b.get(key)!.value))
  }
  if (left[0] === '[' && right[0] === '[') {
    const a = left.slice(1, -1).trim() ? rawValues(left) : []
    const b = right.slice(1, -1).trim() ? rawValues(right) : []
    return a.length === b.length && a.every((value, index) => sameSubmittedValues(value, b[index]))
  }
  const integer = /^-?(?:0|[1-9]\d*)$/
  if (integer.test(left) || integer.test(right)) return integer.test(left) && integer.test(right) && BigInt(left) === BigInt(right)
  const a = JSON.parse(left), b = JSON.parse(right)
  return typeof a === typeof b && (typeof a === 'number' ? Number.isFinite(a) && Object.is(a, b) : a === b)
}

export async function verifyRcSubmissionBinding(transport: RcJobTransport, job: WorkbenchJobView, submittedBytes: Uint8Array): Promise<void> {
  try {
    parseJson(submittedBytes, 'rc_submit')
    const stored = await loadRcJobRequest(transport, job)
    if (!sameSubmittedValues(new TextDecoder('utf-8', { fatal: true }).decode(submittedBytes), new TextDecoder('utf-8', { fatal: true }).decode(stored.bytes))) {
      throw new JobArtifactError('rc_submission_source_mismatch')
    }
  } catch (error) {
    if (error instanceof JobArtifactError) throw error
    throw new JobArtifactError('rc_submission_source_mismatch')
  }
}

export async function refreshRcJob(transport: RcJobTransport, jobId: string): Promise<WorkbenchJobView> {
  return readWorkbenchJobViewResponse(await transport.getJob(jobId), jobId)
}

export async function loadRcJobRequest(transport: RcJobTransport, job: WorkbenchJobView): Promise<{ bytes: Uint8Array; value: Record<string, unknown> }> {
  validatedJob(job)
  if (job.request.byte_length > REQUEST_MAX_BYTES) throw new JobArtifactError('request_too_large')
  const response = await transport.getRequest(job.job_id)
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  const bytes = await readBoundedJobBytes(response, REQUEST_MAX_BYTES, 'request', job.request.byte_length)
  const hash = await sha256Bytes(bytes)
  if (hash === null) throw new JobArtifactError('request_integrity_unavailable')
  if (hash !== job.request.content_hash) throw new JobArtifactError('request_hash_mismatch')
  const value = parseJson(bytes, 'request')
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new JobArtifactError('request_json_invalid')
  return { bytes, value: value as Record<string, unknown> }
}

/** Checkpointed is an in-progress continuation; only explicit failed-job retry is legal. */
export async function resumeRcJob(transport: RcJobTransport, job: WorkbenchJobView): Promise<WorkbenchJobView> {
  validatedJob(job)
  if (job.status !== 'failed') throw new JobArtifactError('job_resume_state_invalid')
  const resumed = await readWorkbenchJobViewResponse(await transport.resume(
    job.job_id, job.request.content_hash, job.checkpoint?.content_hash ?? null,
  ), job.job_id)
  if (resumed.request.content_hash !== job.request.content_hash) throw new JobArtifactError('job_resume_request_mismatch')
  return resumed
}

/** Price declarations have no structural authority; the service binds the saved source. */
export async function createRcQuantityReport(transport: RcJobTransport, job: WorkbenchJobView, prices: RcDeclaredPrices | null): Promise<RcQuantityReportReference> {
  const expected = reportScope(transport, job)
  const declared = safeSchema(() => parseRcDeclaredPrices(prices), 'rc_report_declaration')
  const response = await transport.createQuantityReport(job.job_id, {
    expected_request_hash: job.request.content_hash,
    expected_result_artifact_hash: job.result!.content_hash,
    declared_prices: declared,
  })
  const value = await jsonResponse(response, REPORT_INDEX_MAX_BYTES, 'rc_report_reference')
  return safeSchema(() => parseRcQuantityReportReference(value, expected), 'rc_report_reference')
}

export async function listRcQuantityReports(transport: RcJobTransport, job: WorkbenchJobView, page: RcReportPage = {}): Promise<RcQuantityReportIndex> {
  const expected = reportScope(transport, job)
  const value = await jsonResponse(await transport.listQuantityReports(job.job_id, page), REPORT_INDEX_MAX_BYTES, 'rc_report_index')
  return safeSchema(() => parseRcQuantityReportIndex(value, {
    ...expected, after_revision: page.afterRevision ?? 0, limit: page.limit ?? 20,
  }), 'rc_report_index')
}

/** Byte identity only. The caller must also use the original RC review's semantic RPC. */
export async function loadRcQuantityReportBytes(transport: RcJobTransport, job: WorkbenchJobView, reference: RcQuantityReportReference): Promise<{ reference: RcQuantityReportReference; bytes: Uint8Array }> {
  const expected = reportScope(transport, job)
  const admitted = safeSchema(() => parseRcQuantityReportReference(reference, expected), 'rc_report_reference')
  const response = await transport.getQuantityReport(job.job_id, admitted.report_id)
  if (!response.ok) throw new JobArtifactError(`job_api_http_${response.status}`)
  if (response.headers.get('x-structural-report-sha256') !== admitted.content_hash) {
    try { await response.body?.cancel() } catch { /* Preserve the safe binding error. */ }
    throw new JobArtifactError('rc_report_hash_header_mismatch')
  }
  const bytes = await readBoundedJobBytes(response, QUANTITY_REPORT_MAX_BYTES, 'rc_report', admitted.byte_length)
  const hash = await sha256Bytes(bytes)
  if (hash === null) throw new JobArtifactError('rc_report_integrity_unavailable')
  if (hash !== admitted.content_hash || admitted.report_id !== `rcq_${hash.slice(7)}`) throw new JobArtifactError('rc_report_hash_mismatch')
  return { reference: admitted, bytes }
}
