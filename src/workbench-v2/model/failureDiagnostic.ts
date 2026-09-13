import { sha256Bytes, sha256Hex } from './checksum'
import { document, fields, rawValues, selfHash, same } from './rcJobSchema'
import { JobArtifactError, readBoundedJobBytes, type JobReadTransport } from './jobTransport'
import type { WorkbenchJobView } from './jobSchema'

export interface FailureStep {
  target: number
  committed: boolean
  historyRows: number
  reason: string | null
  rollbackExact: boolean | null
}
export interface FailureDiagnosticReview {
  attempt: number
  sourceRevision: string | null
  resultHash: string
  inputChecksum: string
  modelIdentityVerification: 'browser_raw_neutral_model' | 'service_normalized_model_ir'
  observed: null | { attempted: number; committed: number; replayed: number; newlyAttempted: number; historyRows: number; steps: FailureStep[] }
  diagnosticBytes: Uint8Array
  resultBytes: Uint8Array
}

const AUTHORITY = {
  convergence: 'not_authoritative', displacement: 'not_authoritative', reaction: 'not_authoritative',
  member_force: 'not_authoritative', member_features: 'not_authoritative', section_resultant: 'not_authoritative',
  fiber_result: 'not_authoritative', fallback: 'not_authoritative', public_api: 'not_promoted',
  external_vv: 'not_attached', engineering_design: 'not_authoritative', release_readiness: 'not_authoritative',
}
function ensure(value: unknown): asserts value {
  if (!value) throw new JobArtifactError('nonlinear_failure_diagnostic_invalid')
}
function object(value: unknown): Record<string, any> {
  ensure(value && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, any>
}
function exact(value: Record<string, any>, keys: string[]): void {
  ensure(same(Object.keys(value).sort(), [...keys].sort()))
}
function count(value: unknown, token?: string): number {
  ensure(typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)
  if (token !== undefined) ensure(/^(0|[1-9][0-9]*)$/.test(token))
  return value
}
function hash(value: unknown): value is string { return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value) }

/** Validate diagnostic transport and observed counts, never accepted solver results.
 * The current local worker produces compact key-sorted Python JSON; raw token
 * hashes preserve its float spellings. ModelIR normalization remains server-owned.
 */
export async function validateFailureDiagnostic(
  diagnosticBytes: Uint8Array, requestBytes: Uint8Array, job: WorkbenchJobView, attempt = job.attempt,
): Promise<FailureDiagnosticReview> {
  ensure(Number.isSafeInteger(attempt) && attempt > 0 && attempt <= job.attempt)
  ensure(attempt < job.attempt || (job.status === 'failed' && job.result === null && job.evidence === null))
  ensure(diagnosticBytes.byteLength <= 12 * 1024 * 1024 && requestBytes.byteLength <= 16 * 1024 * 1024)
  ensure(requestBytes.byteLength === job.request.byte_length && await sha256Bytes(requestBytes) === job.request.content_hash)
  const requestDoc = document(requestBytes), request = requestDoc.value
  ensure(request.schema_version === 'structural-analysis-job-request.v1' && request.operation === 'nonlinear_frame')
  const envelopeDoc = document(diagnosticBytes), envelope = envelopeDoc.value
  exact(envelope, ['schema_version', 'binding', 'result_bytes_base64', 'result_artifact_hash', 'result_byte_length', 'source_result_hash', 'authority'])
  ensure(envelope.schema_version === 'nonlinear-frame-failure-diagnostic.v1')
  ensure(envelope.authority === 'diagnostic_only_no_numerical_design_or_release_authority')
  const binding = object(envelope.binding)
  exact(binding, ['job_id', 'request_hash', 'attempt', 'source_revision', 'input_checksum', 'configuration_hash'])
  ensure(binding.job_id === job.job_id && binding.request_hash === job.request.content_hash
    && count(binding.attempt, fields(fields(envelopeDoc.raw).get('binding')!.value).get('attempt')!.value) === attempt && binding.source_revision === (request.source_revision ?? null))
  ensure(binding.source_revision === null || (typeof binding.source_revision === 'string' && /^[0-9a-f]{40}$/.test(binding.source_revision)))
  ensure(hash(binding.input_checksum) && hash(binding.configuration_hash))
  ensure(typeof envelope.result_bytes_base64 === 'string' && envelope.result_bytes_base64.length <= 11184812)
  const binary = atob(envelope.result_bytes_base64)
  ensure(btoa(binary) === envelope.result_bytes_base64)
  const resultBytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  ensure(resultBytes.byteLength <= 8 * 1024 * 1024 && count(envelope.result_byte_length, fields(envelopeDoc.raw).get('result_byte_length')!.value) === resultBytes.byteLength)
  ensure(hash(envelope.result_artifact_hash) && await sha256Bytes(resultBytes) === envelope.result_artifact_hash)
  const sourceDoc = document(resultBytes), source = sourceDoc.value
  await selfHash(sourceDoc.raw, source, 'result_hash')
  ensure(source.result_hash === envelope.source_result_hash && source.input_checksum === binding.input_checksum)
  ensure(source.schema_version === 'unified-nonlinear-frame-result.v1' && source.status === 'blocked' && source.contract_pass === false)
  ensure(['corotational_one_bay_portal.v1', 'corotational_connected_frame2d.v1'].includes(source.profile))
  ensure(source.source_result_hash === null && source.engineering_result_ir === null
    && same(source.checkpoint, { available: false }) && same(source.authority, AUTHORITY))
  for (const key of ['node_displacements', 'support_reactions', 'member_end_forces', 'section_results', 'fiber_results', 'convergence_history']) ensure(same(source[key], []))
  const configuration = object(source.configuration), authored = object(request.config)
  ensure(authored.control_mode === 'load_control' && source.profile === authored.profile && configuration.profile === authored.profile)
  const authoredFields = fields(fields(requestDoc.raw).get('config')!.value)
  const total = count(authored.load_steps, authoredFields.get('load_steps')!.value)
  const iterations = count(authored.maximum_iterations, authoredFields.get('maximum_iterations')!.value)
  ensure(iterations >= 1 && iterations <= 200)
  for (const key of ['residual_tolerance', 'increment_tolerance_m']) ensure(typeof authored[key] === 'number' && Number.isFinite(authored[key]) && authored[key] > 0)
  ensure(['numpy_linalg_solve_dense', 'scipy_sparse_spsolve_cpu', 'scipy_sparse_splu_cpu_exact_1536'].includes(authored.matrix_backend))
  ensure(total >= 2 && total <= 64 && configuration.load_steps === total)
  const targets = Array.from({ length: total }, (_, index) => (index + 1) / total)
  ensure(same(configuration.target_load_factors, targets))
  for (const [key, authoredKey] of [
    ['scaled_residual_tolerance', 'residual_tolerance'], ['solver_coordinate_increment_tolerance_m', 'increment_tolerance_m'],
    ['maximum_iterations', 'maximum_iterations'], ['matrix_backend', 'matrix_backend'],
  ]) ensure(configuration[key] === authored[authoredKey])
  ensure(configuration.restart_supplied === (job.checkpoint !== null)
    && configuration.restart_checkpoint_artifact_hash === (job.checkpoint?.content_hash ?? null))
  ensure(await sha256Hex(fields(sourceDoc.raw).get('configuration')!.value) === binding.configuration_hash)
  const model = object(request.model)
  const modelIR = model.schema_version === 'structural-analysis-model-ir.v2'
  if (modelIR) {
    const adapter = object(object(source.contract_bindings).source_model_ir_adapter)
    ensure(adapter.model_ir_content_hash === source.input_checksum)
  } else {
    ensure(model.schema_version === 'structural-analysis-canonical-model.v1')
    ensure(await sha256Hex(fields(requestDoc.raw).get('model')!.value) === source.input_checksum)
  }
  const observedValue = object(source.metrics).observed_load_path
  let observed: FailureDiagnosticReview['observed'] = null
  if (observedValue !== undefined && observedValue !== null) {
    const path = object(observedValue)
    const observedRaw = fields(fields(sourceDoc.raw).get('metrics')!.value).get('observed_load_path')!.value
    const pathFields = fields(observedRaw)
    const pathCount = (key: string): number => count(path[key], pathFields.get(key)!.value)
    exact(path, ['scope', 'total_api_work_accounted', 'attempted_step_count', 'committed_step_count', 'replayed_prefix_step_count', 'newly_attempted_step_count', 'convergence_history_row_count', 'steps'])
    ensure(path.scope === 'returned_load_path_including_replayed_prefix' && path.total_api_work_accounted === false)
    const attempted = pathCount('attempted_step_count'), committed = pathCount('committed_step_count')
    const replayed = pathCount('replayed_prefix_step_count'), newlyAttempted = pathCount('newly_attempted_step_count')
    const historyRows = pathCount('convergence_history_row_count')
    ensure(Array.isArray(path.steps) && path.steps.length === attempted && attempted <= total
      && replayed + newlyAttempted === attempted && replayed <= committed && (!replayed || configuration.restart_supplied))
    const rawSteps = rawValues(pathFields.get('steps')!.value)
    const steps: FailureStep[] = path.steps.map((value: unknown, index: number) => {
      const step = object(value)
      exact(step, ['target_load_factor', 'committed', 'terminal_reason', 'convergence_history_row_count', 'failed_step_rollback_exact'])
      ensure(typeof step.target_load_factor === 'number' && step.target_load_factor === targets[index] && typeof step.committed === 'boolean')
      ensure(step.terminal_reason === null || (typeof step.terminal_reason === 'string' && step.terminal_reason.length > 0 && step.terminal_reason.length <= 512))
      ensure(step.committed ? step.failed_step_rollback_exact === null : index === attempted - 1 && typeof step.failed_step_rollback_exact === 'boolean')
      return { target: step.target_load_factor, committed: step.committed, historyRows: count(step.convergence_history_row_count, fields(rawSteps[index]).get('convergence_history_row_count')!.value), reason: step.terminal_reason, rollbackExact: step.failed_step_rollback_exact }
    })
    ensure(steps.filter(step => step.committed).length === committed && count(steps.reduce((sum, step) => sum + step.historyRows, 0)) === historyRows)
    observed = { attempted, committed, replayed, newlyAttempted, historyRows, steps }
  }
  return { attempt, sourceRevision: binding.source_revision, resultHash: source.result_hash,
    inputChecksum: source.input_checksum, modelIdentityVerification: modelIR ? 'service_normalized_model_ir' : 'browser_raw_neutral_model',
    observed, diagnosticBytes: diagnosticBytes.slice(), resultBytes }
}

export async function loadFailureDiagnostic(job: WorkbenchJobView, transport: JobReadTransport, attempt = job.attempt): Promise<FailureDiagnosticReview | undefined> {
  if (!Number.isSafeInteger(attempt) || attempt < 1 || attempt > job.attempt) throw new JobArtifactError('failure_attempt_invalid')
  const response = await transport.get(`failure-diagnostics/${attempt}`)
  if (response.status === 404) return undefined
  if (!response.ok) throw new JobArtifactError(`failure_diagnostic_HTTP_${response.status}`)
  const diagnostic = await readBoundedJobBytes(response, 12 * 1024 * 1024, 'failure diagnostic')
  const requestResponse = await transport.get('request', job.request.media_type)
  if (!requestResponse.ok) throw new JobArtifactError(`failure_request_HTTP_${requestResponse.status}`)
  const request = await readBoundedJobBytes(requestResponse, 16 * 1024 * 1024, 'failure request', job.request.byte_length)
  try { return await validateFailureDiagnostic(diagnostic, request, job, attempt) }
  catch { throw new JobArtifactError('nonlinear_failure_diagnostic_invalid') }
}
