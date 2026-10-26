import { sha256Bytes } from './checksum'
import { validateWorkbenchJobView, type WorkbenchJobView } from './jobSchema'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { document, validateRcCorotationalRequestProfile, type RcObject } from './rcJobSchema'
import { parseRcCorotationalReport, type RcCorotationalReport } from './rcCorotationalReportSchema'
import type { RcCorotationalReportSummary } from './rcCorotationalReportReview'
import { parseRcCorotationalDetailReport, type RcCorotationalDetailReport, type RcCorotationalDetailSummary } from './rcCorotationalDetailReport'

export const RC_PORTABLE_REVIEW_MAX_BYTES = 200 * 1024 * 1024
export const RC_PORTABLE_REVIEW_V1_MAX_BYTES = 112 * 1024 * 1024
export const RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES = 16 * 1024 * 1024
export const RC_PORTABLE_REVIEW_REPORT_MAX_BYTES = 64 * 1024 * 1024
export const RC_PORTABLE_REVIEW_DETAIL_MAX_BYTES = 64 * 1024 * 1024
const JOB_MAX_BYTES = 64 * 1024
const SCHEMA_V1 = 'rc-portable-nodal-review.v1'
const SCHEMA_V2 = 'rc-portable-nodal-review.v2'
const CUSTODY = 'portable_unverified_origin'
const HASH = /^sha256:[0-9a-f]{64}$/
const CHUNK = 48 * 1024 // Divisible by three: only the final base64 chunk is padded.
const encoder = new TextEncoder()

export interface RcPortableReviewSource {
  job: WorkbenchJobView
  tenantId: string
  requestBytes: Uint8Array
  reportBytes: Uint8Array
  reportId: string
  contentHash: string
  detailReport?: { bytes: Uint8Array; reportId: string; contentHash: string }
}
export interface RcPortableReviewDocument extends RcPortableReviewSource {
  request: RcObject
  report: RcCorotationalReport
  summary: RcCorotationalReportSummary
  detail: RcCorotationalDetailReport | null
  detailSummary: RcCorotationalDetailSummary | null
}
interface EncodedArtifact { encoding: 'base64'; byte_length: number; content_hash: string; body_base64: string }

function check(condition: unknown, code: string): asserts condition {
  if (!condition) throw new Error(`rc_portable_review_${code}`)
}
function exact(value: unknown, keys: string[], code: string): Record<string, unknown> {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), code)
  const row = value as Record<string, unknown>, actual = Object.keys(row)
  check(actual.length === keys.length && actual.every(key => keys.includes(key)), code)
  return row
}
function admittedJob(value: unknown): WorkbenchJobView {
  const checked = validateWorkbenchJobView(value)
  check(checked.ok && checked.value, 'job_invalid')
  const job = checked.value
  check(job.schema_version === 'structural-analysis-job-view.v2' && job.status === 'succeeded'
    && job.result && job.evidence && job.progress.unit === 'control_solver_attempts', 'job_unsupported')
  for (const value of [job.revision, job.attempt, job.progress.completed_steps, job.progress.total_steps,
    job.request.byte_length, job.checkpoint?.byte_length ?? 0, job.result.byte_length, job.evidence.byte_length]) {
    check(Number.isSafeInteger(value) && value >= 0, 'job_invalid')
  }
  check([job.created_at, job.updated_at, job.claim_boundary, job.error_code ?? ''].every(value => value.length <= 4096)
    && [job.request, job.checkpoint, job.result, job.evidence].every(ref => ref === null || ref.media_type.length <= 256)
    && encoder.encode(JSON.stringify(job)).byteLength <= JOB_MAX_BYTES, 'job_too_large')
  return job
}
function admittedTenant(value: unknown): string {
  check(typeof value === 'string' && /^[\x21-\x7e]{1,256}$/.test(value), 'tenant_invalid')
  return value
}
function bytesWithin(bytes: unknown, maximum: number): asserts bytes is Uint8Array {
  check(bytes instanceof Uint8Array && bytes.byteLength > 0 && bytes.byteLength <= maximum, 'artifact_size_invalid')
}
async function hash(bytes: Uint8Array): Promise<string> {
  const digest = await sha256Bytes(bytes)
  check(digest !== null, 'integrity_unavailable')
  return digest
}
function encode(bytes: Uint8Array): string {
  const chunks: string[] = []
  for (let start = 0; start < bytes.byteLength; start += CHUNK) {
    const end = Math.min(start + CHUNK, bytes.byteLength)
    let binary = ''
    for (let index = start; index < end; index++) binary += String.fromCharCode(bytes[index])
    chunks.push(btoa(binary))
  }
  return chunks.join('')
}
function encoded(value: unknown, maximum: number): EncodedArtifact {
  const row = exact(value, ['encoding', 'byte_length', 'content_hash', 'body_base64'], 'artifact_fields_invalid')
  check(row.encoding === 'base64' && Number.isSafeInteger(row.byte_length)
    && (row.byte_length as number) > 0 && (row.byte_length as number) <= maximum, 'artifact_size_invalid')
  check(typeof row.content_hash === 'string' && HASH.test(row.content_hash), 'artifact_hash_invalid')
  check(typeof row.body_base64 === 'string' && row.body_base64.length === 4 * Math.ceil((row.byte_length as number) / 3), 'base64_invalid')
  return row as unknown as EncodedArtifact
}
function decode(row: EncodedArtifact): Uint8Array {
  const text = row.body_base64, bytes = new Uint8Array(row.byte_length)
  let cursor = 0
  for (let start = 0; start < text.length; start += CHUNK) {
    const part = text.slice(start, start + CHUNK), last = start + CHUNK >= text.length
    // Validate each bounded chunk, including canonical padding bits. No full
    // report-sized binary string or regular-expression stack is allocated.
    check((last ? /^[A-Za-z0-9+/]*={0,2}$/ : /^[A-Za-z0-9+/]+$/).test(part), 'base64_invalid')
    let binary: string
    try { binary = atob(part) } catch { throw new Error('rc_portable_review_base64_invalid') }
    check(btoa(binary) === part && cursor + binary.length <= bytes.length, 'base64_invalid')
    for (let index = 0; index < binary.length; index++) bytes[cursor++] = binary.charCodeAt(index)
  }
  check(cursor === bytes.length, 'base64_invalid')
  return bytes
}

export function rcPortableReviewSummary(report: RcCorotationalReport, reportId: string, contentHash: string): RcCorotationalReportSummary {
  return {
    jobId: report.bindings.job_id, reportId, contentHash, reportHash: report.report_hash,
    caseId: report.bindings.case_id, sourceRevision: report.bindings.source_revision,
    control: report.declarations.control, targets: report.declarations.targets_m,
    stateCount: report.progress.accepted_response_states, nodeCount: report.responses[0].nodes.length,
    attemptProgress: report.progress.control_solver_attempts, targetProgress: report.progress.authored_targets,
    reservedInvocations: report.execution.budget.reserved_attempts, maximumInvocations: report.execution.budget.maximum_attempts,
    recordedInvocations: report.execution.recorded_invocation_count, pendingInvocations: report.execution.pending_ordinals.length,
    unknownWork: report.execution.unknown_execution_work, knownWork: report.execution.known_work,
    constantLoads: report.declarations.fixed_nodal_loads,
  }
}

export function rcPortableDetailSummary(detail: RcCorotationalDetailReport, reportId: string, contentHash: string): RcCorotationalDetailSummary {
  return { reportId, contentHash, reportHash: detail.report_hash, stateCount: detail.responses.length,
    members: detail.responses[0].members.map(member => ({ member_id: member.member_id, node_i: member.node_i,
      node_j: member.node_j, sectionCount: member.sections.length })) }
}

/** Called by the authenticated worker using already validated original custody.
 * This envelope records provenance; its contents never carry authentication.
 */
export async function createRcPortableReviewBlob(source: RcPortableReviewSource): Promise<Blob> {
  const job = admittedJob(source.job), tenantId = admittedTenant(source.tenantId)
  bytesWithin(source.requestBytes, RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES)
  bytesWithin(source.reportBytes, RC_PORTABLE_REVIEW_REPORT_MAX_BYTES)
  const requestHash = await hash(source.requestBytes), reportHash = await hash(source.reportBytes)
  check(source.requestBytes.byteLength === job.request.byte_length && requestHash === job.request.content_hash, 'request_binding_invalid')
  check(reportHash === source.contentHash && source.reportId === `rcc_${reportHash.slice(7)}`, 'report_binding_invalid')
  const detail = source.detailReport
  let detailHash: string | null = null
  if (detail) {
    bytesWithin(detail.bytes, RC_PORTABLE_REVIEW_DETAIL_MAX_BYTES)
    detailHash = await hash(detail.bytes)
    check(detailHash === detail.contentHash && detail.reportId === `rcd_${detailHash.slice(7)}`, 'detail_binding_invalid')
  }
  const jobBytes = encoder.encode(JSON.stringify(job)), jobHash = await hash(jobBytes)
  const artifact = (bytes: Uint8Array, content_hash: string) => ({ encoding: 'base64', byte_length: bytes.byteLength, content_hash, body_base64: encode(bytes) })
  // Blob parts avoid a second complete JSON string containing both base64 bodies.
  const blob = new Blob([
    `{"schema_version":"${detail ? SCHEMA_V2 : SCHEMA_V1}","custody":"${CUSTODY}","recorded_tenant_id":${JSON.stringify(tenantId)},"job":`,
    JSON.stringify(artifact(jobBytes, jobHash)), `,"report_id":${JSON.stringify(source.reportId)},"request":`,
    JSON.stringify(artifact(source.requestBytes, requestHash)), ',"report":', JSON.stringify(artifact(source.reportBytes, reportHash)),
    ...(detail && detailHash ? [',"detail_report_id":', JSON.stringify(detail.reportId), ',"detail_report":', JSON.stringify(artifact(detail.bytes, detailHash))] : []), '}',
  ], { type: 'application/json' })
  check(blob.size <= (detail ? RC_PORTABLE_REVIEW_MAX_BYTES : RC_PORTABLE_REVIEW_V1_MAX_BYTES), 'file_too_large')
  return blob
}

/** Parse only recorded files. Hashes establish internal integrity, never the
 * identity of the original service, source execution or scientific validity.
 */
export async function parseRcPortableReview(bytes: Uint8Array): Promise<RcPortableReviewDocument> {
  try {
    check(bytes instanceof Uint8Array && bytes.byteLength > 0 && bytes.byteLength <= RC_PORTABLE_REVIEW_MAX_BYTES, 'file_too_large')
    check(!(bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf), 'encoding_invalid')
    const value = parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
    check(value !== null && typeof value === 'object' && !Array.isArray(value), 'file_fields_invalid')
    const schema = (value as Record<string, unknown>).schema_version
    check(schema === SCHEMA_V1 || schema === SCHEMA_V2, 'schema_unsupported')
    check(schema !== SCHEMA_V1 || bytes.byteLength <= RC_PORTABLE_REVIEW_V1_MAX_BYTES, 'file_too_large')
    const row = exact(value, ['schema_version', 'custody', 'recorded_tenant_id', 'job', 'report_id', 'request', 'report',
      ...(schema === SCHEMA_V2 ? ['detail_report_id', 'detail_report'] : [])], 'file_fields_invalid')
    check(row.custody === CUSTODY, 'custody_invalid')
    const tenantId = admittedTenant(row.recorded_tenant_id), jobRef = encoded(row.job, JOB_MAX_BYTES)
    const jobBytes = decode(jobRef)
    check(await hash(jobBytes) === jobRef.content_hash, 'job_hash_mismatch')
    const job = admittedJob(document(jobBytes).value)
    const requestRef = encoded(row.request, RC_PORTABLE_REVIEW_REQUEST_MAX_BYTES)
    const reportRef = encoded(row.report, RC_PORTABLE_REVIEW_REPORT_MAX_BYTES)
    check(requestRef.byte_length === job.request.byte_length && requestRef.content_hash === job.request.content_hash, 'request_binding_invalid')
    check(typeof row.report_id === 'string' && row.report_id === `rcc_${reportRef.content_hash.slice(7)}`, 'report_binding_invalid')
    const requestBytes = decode(requestRef)
    check(await hash(requestBytes) === requestRef.content_hash, 'request_hash_mismatch')
    const request = document(requestBytes).value
    validateRcCorotationalRequestProfile(request)
    const reportBytes = decode(reportRef)
    check(await hash(reportBytes) === reportRef.content_hash, 'report_hash_mismatch')
    const expected = { job, tenantId, request }
    const report = await parseRcCorotationalReport(reportBytes, expected)
    let detail: RcCorotationalDetailReport | null = null, detailSummary: RcCorotationalDetailSummary | null = null
    let detailReport: RcPortableReviewSource['detailReport']
    if (schema === SCHEMA_V2) {
      const ref = encoded(row.detail_report, RC_PORTABLE_REVIEW_DETAIL_MAX_BYTES)
      check(typeof row.detail_report_id === 'string' && row.detail_report_id === `rcd_${ref.content_hash.slice(7)}`, 'detail_binding_invalid')
      const detailBytes = decode(ref)
      check(await hash(detailBytes) === ref.content_hash, 'detail_hash_mismatch')
      detail = await parseRcCorotationalDetailReport(detailBytes, expected, report)
      detailReport = { bytes: detailBytes, reportId: row.detail_report_id, contentHash: ref.content_hash }
      detailSummary = rcPortableDetailSummary(detail, row.detail_report_id, ref.content_hash)
    }
    return { job, tenantId, requestBytes, reportBytes, request, report, reportId: row.report_id,
      contentHash: reportRef.content_hash, summary: rcPortableReviewSummary(report, row.report_id, reportRef.content_hash),
      detailReport, detail, detailSummary }
  } catch (error) {
    if (error instanceof Error && /^rc_portable_review_[a-z_]+$/.test(error.message)) throw error
    throw new Error('rc_portable_review_contract_invalid')
  }
}
