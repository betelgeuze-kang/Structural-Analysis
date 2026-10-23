import { sha256Bytes } from './checksum'
import { document, validateRcRequestProfile } from './rcJobSchema'
import { parseRcCorotationalReport, type RcCorotationalReport, type RcCorotationalReportExpected } from './rcCorotationalReportSchema'
import type { RcCorotationalReportSummary } from './rcCorotationalReportReview'
import { corotationalRcScenarioSummary } from './rcScenarioComparison'
import { rcResultGeometry } from './rcResultVisualization'

let report: RcCorotationalReport | null = null
let bytes: Uint8Array | null = null
let expected: RcCorotationalReportExpected | null = null
let summary: RcCorotationalReportSummary | null = null
let maximumBytes = 0
const safe = (error: unknown) => error instanceof Error && /^rc_corotational_report_[a-z_]+$/.test(error.message) ? error.message : 'rc_corotational_report_contract_invalid'
function unavailable(): never { throw new Error('rc_corotational_report_unavailable') }
self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      if (report || bytes || expected || summary) throw new Error('rc_corotational_report_already_initialized')
      if (!(data.requestBytes instanceof Uint8Array) || !(data.bytes instanceof Uint8Array)) throw new Error('rc_corotational_report_bytes_invalid')
      if (!Number.isSafeInteger(data.maximumBytes) || data.maximumBytes <= 0 || data.maximumBytes > 64 * 1024 * 1024 || data.bytes.byteLength > data.maximumBytes) throw new Error('rc_corotational_report_too_large')
      maximumBytes = data.maximumBytes
      if (await sha256Bytes(data.requestBytes) !== data.job.request.content_hash) throw new Error('rc_corotational_report_request_hash_mismatch')
      const request = document(data.requestBytes).value
      validateRcRequestProfile(request)
      if (await sha256Bytes(data.bytes) !== data.contentHash || data.reportId !== `rcc_${data.contentHash.slice(7)}`) throw new Error('rc_corotational_report_raw_hash_mismatch')
      expected = { job: data.job, tenantId: data.tenantId, request }
      report = await parseRcCorotationalReport(data.bytes, expected); bytes = data.bytes
      summary = {
        jobId: report.bindings.job_id, reportId: data.reportId, contentHash: data.contentHash, reportHash: report.report_hash,
        caseId: report.bindings.case_id, sourceRevision: report.bindings.source_revision,
        control: report.declarations.control, targets: report.declarations.targets_m,
        stateCount: report.progress.accepted_response_states, nodeCount: report.responses[0].nodes.length,
        attemptProgress: report.progress.control_solver_attempts, targetProgress: report.progress.authored_targets,
        reservedInvocations: report.execution.budget.reserved_attempts, maximumInvocations: report.execution.budget.maximum_attempts,
        recordedInvocations: report.execution.recorded_invocation_count, pendingInvocations: report.execution.pending_ordinals.length,
        unknownWork: report.execution.unknown_execution_work, knownWork: report.execution.known_work,
        constantLoads: report.declarations.fixed_nodal_loads,
      }
      self.postMessage({ id, value: summary }); return
    }
    if (!report || !bytes || !expected || !summary) unavailable()
    if (type === 'geometry') {
      try { self.postMessage({ id, value: rcResultGeometry(expected.request) }) }
      catch { self.postMessage({ id, operationError: 'rc_corotational_report_geometry_invalid' }) }
      return
    }
    if (type === 'reopen') {
      try {
        if (!(data.bytes instanceof Uint8Array) || !data.bytes.byteLength || data.bytes.byteLength > maximumBytes) throw new Error('rc_corotational_report_too_large')
        // A downloaded self-hash is not authentication. Reopen only the exact
        // raw report already authenticated by this service session.
        if (await sha256Bytes(data.bytes) !== summary.contentHash) throw new Error('rc_corotational_report_raw_hash_mismatch')
        await parseRcCorotationalReport(data.bytes, expected)
        self.postMessage({ id, value: summary })
      } catch (error) { self.postMessage({ id, operationError: safe(error) }) }
      return
    }
    if (type === 'comparisonSummary') {
      self.postMessage({ id, value: corotationalRcScenarioSummary(expected.request, expected.job, report) })
    } else if (type === 'state') {
      if (!Number.isSafeInteger(data.index) || data.index < 0 || data.index >= report.responses.length) throw new Error('rc_corotational_report_state_invalid')
      self.postMessage({ id, value: report.responses[data.index] })
    } else if (type === 'statePage') {
      if (!Number.isSafeInteger(data.start) || data.start < 0 || data.start >= report.responses.length || !Number.isSafeInteger(data.count) || data.count < 1 || data.count > 50) throw new Error('rc_corotational_report_page_invalid')
      self.postMessage({ id, value: report.responses.slice(data.start, data.start + data.count).map(row => ({ state_index: row.state_index, phase: row.phase, control_displacement_m: row.control_displacement_m, load_factor: row.load_factor, checkpoint_hash: row.checkpoint_hash })) })
    } else if (type === 'download') self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    else throw new Error('rc_corotational_report_operation_invalid')
  } catch (error) {
    report = null; bytes = null; expected = null; summary = null; maximumBytes = 0
    self.postMessage({ id, error: safe(error) })
  }
}
