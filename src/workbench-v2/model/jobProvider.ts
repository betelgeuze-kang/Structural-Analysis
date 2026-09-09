import { canonicalJson, sha256Bytes, sha256Hex } from './checksum'
import { validateFrame3DJobResult, type Frame3DJobReview } from './frame3dJobSchema'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import {
  createJobReadTransport, JobArtifactError, readBoundedJobBytes,
  type JobAuthorizationProvider, type JobReadTransport,
} from './jobTransport'
import {
  validateWorkbenchJobView,
  type JobArtifactReference,
  type WorkbenchJobView,
} from './jobSchema'

export type JobLoadStatus = 'unconfigured' | 'loading' | 'ready' | 'missing' | 'invalid' | 'error'

export interface JobLoadResult {
  status: JobLoadStatus
  job: WorkbenchJobView | null
  errors: string[]
  artifactStatus?: 'not_published' | 'verified' | 'integrity_unavailable' | 'invalid'
  engineeringResultIr?: EngineeringResultIrManifest
  frame3dResult?: Frame3DJobReview
  frame3dArtifacts?: Frame3DJobArtifacts
}

export interface Frame3DJobArtifacts {
  resultBytes: Uint8Array
  evidenceBytes: Uint8Array
  checkpointBytes: Uint8Array
}

export interface EngineeringResultIrManifest {
  schema_version: 'corotational-fiber-frame2d-engineering-result-ir.v1'
  engineering_result_id: string
  engineering_result_hash: string
  result_kind: string
  recovery_profile: string
  authority_profile: string
  compiler_hash: string
  source_adapter_hash: string
  model_content_hash: string
  problem_contract_hash: string
  terminal_checkpoint_hash: string
  terminal_assembly_hash: string
  array_bundle_hash: string
  quantity_catalog_hash: string
  load_factor: 1
  counts: {
    node: number
    member: number
    section: number
    fiber: number
  }
  member_ids: string[]
  metrics: Record<string, number | boolean>
  authority_axes: Record<string, string>
  limitations: string[]
  array_descriptors: EngineeringArrayDescriptor[]
}

export interface EngineeringArrayDescriptor {
  name: string
  dtype: '<f8' | '<i8'
  shape: number[]
  unit: string
  quantity_ids: string[]
  order_scope: 'node' | 'member' | 'section' | 'fiber'
  authority_role: 'output' | 'mapping'
  order_hash: string
  data_hash: string
  content_hash: string
}

const JOB_VIEW_MAX_BYTES = 256 * 1024
const RESULT_MAX_BYTES = 64 * 1024 * 1024
const EVIDENCE_MAX_BYTES = 16 * 1024 * 1024
// Python SparseFactorizationPolicy canonical hashes: unchanged diagnostic gates,
// with only the explicitly selected exact-condition equation limit differing.
const PLANAR_SPARSE_POLICIES: Record<string, { maximumEquations: number; hash: string }> = {
  scipy_sparse_spsolve_cpu: {
    maximumEquations: 256,
    hash: 'sha256:ed5b57b4fc1cf30c4d9cc8bb3e1201e92d7d9b2de510488d3dcf2e609a2f3347',
  },
  scipy_sparse_splu_cpu_exact_1536: {
    maximumEquations: 1536,
    hash: 'sha256:dd4755cbb4469dff802b102b506b2a67f07272104931eb96b37b0fefa4d326b1',
  },
}
export async function loadWorkbenchJob(
  url: string, signal?: AbortSignal, authorize?: JobAuthorizationProvider,
): Promise<JobLoadResult> {
  if (!url || signal?.aborted) return { status: 'unconfigured', job: null, errors: [] }
  const callerSignal = signal
  const controller = new AbortController()
  const abort = () => controller.abort()
  callerSignal?.addEventListener('abort', abort, { once: true })
  signal = controller.signal
  let job: WorkbenchJobView | null = null
  try {
    const transport = await createJobReadTransport(url, signal, authorize)
    const response = await transport.get()
    if (response.status === 404) return { status: 'missing', job: null, errors: ['job not found'] }
    if (!response.ok) return { status: 'error', job: null, errors: [`job API returned HTTP ${response.status}`] }
    const viewBytes = await readBoundedJobBytes(response, JOB_VIEW_MAX_BYTES, 'job view')
    const validation = validateWorkbenchJobView(parseJson(viewBytes, 'job view'))
    if (!validation.ok || !validation.value) {
      return { status: 'invalid', job: null, errors: validation.errors, artifactStatus: 'invalid' }
    }
    job = validation.value
    if (job.status !== 'succeeded' || !job.result || !job.evidence) {
      return { status: 'ready', job, errors: [], artifactStatus: 'not_published' }
    }
    const [result, evidence] = await Promise.all([
      fetchArtifact(transport, job.result, RESULT_MAX_BYTES),
      fetchArtifact(transport, job.evidence, EVIDENCE_MAX_BYTES),
    ])
    const artifactErrors = [...result.errors, ...evidence.errors]
    if (artifactErrors.length) {
      return { status: 'invalid', job, errors: artifactErrors, artifactStatus: 'invalid' }
    }
    const resultPayload = result.value
    const evidencePayload = evidence.value
    if (
      !record(evidencePayload)
      || evidencePayload.schema_version !== 'structural-analysis-job-completion-evidence.v1'
      || evidencePayload.job_id !== job.job_id
      || evidencePayload.request_hash !== job.request.content_hash
      || evidencePayload.checkpoint_hash !== (job.checkpoint?.content_hash ?? null)
      || evidencePayload.result_artifact_hash !== job.result.content_hash
      || evidencePayload.contract_pass !== true
      || evidencePayload.solver_truth_owner !== 'structural_analysis_core'
    ) {
      artifactErrors.push('published completion evidence binding is invalid')
    }
    if (artifactErrors.length) {
      return { status: 'invalid', job, errors: artifactErrors, artifactStatus: 'invalid' }
    }
    if (record(resultPayload) && resultPayload.schema_version === 'bounded-frame3d-job-result.v1') {
      if (result.integrityUnavailable || evidence.integrityUnavailable) {
        return { status: 'invalid', job, errors: ['3D artifact integrity verification is unavailable'], artifactStatus: 'integrity_unavailable' }
      }
      try {
        const frame3dResult = await validateFrame3DJobResult(resultPayload, evidencePayload, job)
        if (signal?.aborted) return { status: 'unconfigured', job: null, errors: [] }
        if (!result.bytes || !evidence.bytes) throw new JobArtifactError('3D original artifact bytes are unavailable')
        return {
          status: 'ready', job, errors: [], artifactStatus: 'verified', frame3dResult,
          frame3dArtifacts: {
            resultBytes: result.bytes.slice(),
            evidenceBytes: evidence.bytes.slice(),
            checkpointBytes: frame3dResult.terminalCheckpointBytes.slice(),
          },
        }
      } catch (error: unknown) {
        if (signal?.aborted) return { status: 'unconfigured', job: null, errors: [] }
        return { status: 'invalid', job, errors: [(error as Error)?.message || 'published 3D result contract is invalid'], artifactStatus: 'invalid' }
      }
    }
    const resultValidation = await validatePublishedEngineeringResultIr(resultPayload, artifactErrors)
    const resultIr = resultValidation.value
    if (
      !record(evidencePayload)
      || evidencePayload.validator_id !== 'structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result'
      || !validCoreValidationReport(evidencePayload.validation_report, resultPayload)
    ) artifactErrors.push('published completion evidence binding is invalid')
    if (artifactErrors.length) {
      return { status: 'invalid', job, errors: artifactErrors, artifactStatus: 'invalid' }
    }
    if (signal?.aborted) return { status: 'unconfigured', job: null, errors: [] }
    return {
      status: 'ready',
      job,
      errors: [],
      artifactStatus: result.integrityUnavailable || evidence.integrityUnavailable || resultValidation.integrityUnavailable
        ? 'integrity_unavailable'
        : 'verified',
      engineeringResultIr: resultIr ?? undefined,
    }
  } catch (error: unknown) {
    if (signal?.aborted || (error as Error)?.name === 'AbortError') return { status: 'unconfigured', job: null, errors: [] }
    if (error instanceof JobArtifactError) return { status: 'invalid', job, errors: [error.message], artifactStatus: 'invalid' }
    return { status: 'error', job: null, errors: ['job API request failed'] }
  } finally {
    // Stop sibling reads on any terminal outcome and release the caller link.
    callerSignal?.removeEventListener('abort', abort)
    controller.abort()
  }
}

async function fetchArtifact(
  transport: JobReadTransport,
  reference: JobArtifactReference,
  maximumBytes: number,
): Promise<{ value: unknown; bytes: Uint8Array | null; errors: string[]; integrityUnavailable: boolean }> {
  if (reference.byte_length > maximumBytes) throw new JobArtifactError(`${reference.role}_too_large`)
  const response = await transport.get(reference.role, reference.media_type)
  if (!response.ok) return { value: null, bytes: null, errors: [`${reference.role} HTTP ${response.status}`], integrityUnavailable: false }
  const bytes = await readBoundedJobBytes(response, maximumBytes, reference.role, reference.byte_length)
  if (bytes.byteLength !== reference.byte_length) {
    return { value: null, bytes: null, errors: [`${reference.role} byte length mismatch`], integrityUnavailable: false }
  }
  const digest = await sha256Bytes(bytes)
  if (digest !== null && digest !== reference.content_hash) {
    return { value: null, bytes: null, errors: [`${reference.role} sha256 mismatch`], integrityUnavailable: false }
  }
  return { value: parseJson(bytes, reference.role), bytes, errors: [], integrityUnavailable: digest === null }
}

function parseJson(bytes: Uint8Array, label: string): unknown {
  try {
    const value = parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
    finiteJsonTree(value)
    return value
  } catch {
    throw new JobArtifactError(`${label.replace(' ', '_')}_json_invalid`)
  }
}

function finiteJsonTree(value: unknown, depth = 0): void {
  if (depth > 64 || (typeof value === 'number' && !Number.isFinite(value))) throw new JobArtifactError('job_json_invalid')
  if (Array.isArray(value)) value.forEach((item) => finiteJsonTree(item, depth + 1))
  else if (record(value)) Object.values(value).forEach((item) => finiteJsonTree(item, depth + 1))
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

async function validatePublishedEngineeringResultIr(
  value: unknown,
  errors: string[],
): Promise<{ value: EngineeringResultIrManifest | null; integrityUnavailable: boolean }> {
  if (
    !record(value)
    || value.schema_version !== 'unified-nonlinear-frame-result.v1'
    || value.status !== 'ready'
    || value.contract_pass !== true
    || (
      value.profile !== 'corotational_one_bay_portal.v1'
      && value.profile !== 'corotational_connected_frame2d.v1'
    )
  ) {
    errors.push('published result contract is unsupported')
    return { value: null, integrityUnavailable: false }
  }
  if (!validPublishedPlanarBackend(value)) {
    errors.push('published planar backend contract is invalid')
    return { value: null, integrityUnavailable: false }
  }
  const ir = value.engineering_result_ir
  const bindings = value.contract_bindings
  const authority = value.authority
  if (
    !validEngineeringResultIrShape(ir)
    || !record(bindings)
    || !record(authority)
    || !hash(value.result_hash)
    || value.source_result_hash !== ir.engineering_result_hash
    || bindings.engineering_result_hash !== ir.engineering_result_hash
    || bindings.engineering_array_bundle_hash !== ir.array_bundle_hash
    || bindings.quantity_catalog_hash !== ir.quantity_catalog_hash
  ) {
    errors.push('published engineering ResultIR binding is invalid')
    return { value: null, integrityUnavailable: false }
  }
  const irAuthority = ir.authority_axes
  if (!record(irAuthority)) {
    errors.push('published engineering ResultIR authority axes are invalid')
    return { value: null, integrityUnavailable: false }
  }
  for (const axis of [
    'convergence',
    'displacement',
    'reaction',
    'member_force',
    'member_features',
    'section_resultant',
    'fiber_result',
    'fallback',
    'external_vv',
    'engineering_design',
    'release_readiness',
  ]) {
    if (authority[axis] !== irAuthority[axis]) {
      errors.push(`published engineering ResultIR authority axis is invalid: ${axis}`)
      return { value: null, integrityUnavailable: false }
    }
  }
  const manifest = ir as unknown as EngineeringResultIrManifest
  // The Python producer's canonical float spelling (for example 1.0 and -0.0)
  // cannot be recovered after browser JSON parsing. The raw artifact SHA and
  // core validation report bind the full manifest/result. Array descriptors
  // contain only strings and integers, so their bundle hash is safe to replay.
  const arrayBundleHash = await sha256Hex(canonicalJson(ir.array_descriptors))
  const integrityUnavailable = arrayBundleHash === null
  if (arrayBundleHash !== null && arrayBundleHash !== ir.array_bundle_hash) {
    errors.push('published engineering ResultIR array bundle hash is invalid')
    return { value: null, integrityUnavailable }
  }
  return { value: manifest, integrityUnavailable }
}

function validPublishedPlanarBackend(value: Record<string, unknown>): boolean {
  // Typed API results must retain the complete execution declaration; deleting
  // backend metadata cannot turn an invalid solver contract into a projection.
  const config = value.configuration
  const metrics = value.metrics
  const history = value.convergence_history
  if (!record(config) || !record(metrics) || !Array.isArray(history) || config.profile !== value.profile) return false
  const backend = config.matrix_backend
  const hashes = metrics.sparse_factorization_diagnostic_hashes
  const count = metrics.sparse_factorization_count
  const noSparseExecution = metrics.sparse_backend_used === false
    && metrics.native_sparse_assembly_used === false
    && count === 0
    && Array.isArray(hashes) && hashes.length === 0
    && metrics.sparse_factorization_policy_hash === null
  if (backend === 'numpy_linalg_solve_dense') {
    return config.stiffness_storage === 'numpy_dense_ndarray' && noSparseExecution
  }
  if (typeof backend !== 'string' || !Object.prototype.hasOwnProperty.call(PLANAR_SPARSE_POLICIES, backend)
    || config.stiffness_storage !== 'scipy_sparse_csr') return false
  if (metrics.solver_executed === false && metrics.no_solve_contract_pass === true) {
    const bindings = value.contract_bindings
    if (!record(bindings)) return false
    const plan = bindings.bounded_planar_execution_plan
    return noSparseExecution
      && metrics.sparse_factorization_diagnostics_passed === false
      && ['sparse_factorization_max_condition_number_1', 'sparse_factorization_min_normalized_absolute_pivot', 'sparse_factorization_max_backward_error']
        .every((name) => metrics[name] === null)
      && history.length === 0
      && metrics.terminal_physical_residual_trace_status === 'unavailable'
      && metrics.terminal_physical_residual_trace_reason === 'no_free_equations_no_convergence_claim'
      && metrics.terminal_physical_residual_trace_hash === null
      && record(config.equation_scaling) && config.equation_scaling.status === 'unavailable'
      && !('physical_equation_scaling_binding_hash' in bindings)
      && !('terminal_physical_residual_trace_hash' in bindings)
      && (plan === undefined || plan === null || (record(plan) && plan.equation_scaling_status === 'unavailable'))
  }
  const policy = PLANAR_SPARSE_POLICIES[backend]
  if (metrics.solver_executed !== true || metrics.sparse_backend_used !== true
    || metrics.native_sparse_assembly_used !== true || metrics.sparse_factorization_diagnostics_passed !== true
    || !integerInRange(count, 1) || count !== history.length
    || !Array.isArray(hashes) || hashes.length !== count || !hashes.every(hash)
    || metrics.sparse_factorization_policy_hash !== policy.hash) return false
  let equationCount: number | undefined
  for (const row of history) {
    if (!record(row)) return false
    for (const name of ['free_displacements_m', 'residual_kn', 'newton_increment_m']) {
      const vector = row[name]
      if (!Array.isArray(vector)) return false
      equationCount ??= vector.length
      if (vector.length !== equationCount || !vector.every((number) => typeof number === 'number' && Number.isFinite(number))) return false
    }
  }
  return integerInRange(equationCount, 1, policy.maximumEquations)
    && finiteInRange(metrics.sparse_factorization_max_condition_number_1, 0, 1e12)
    && finiteInRange(metrics.sparse_factorization_min_normalized_absolute_pivot, 1e-14, 1)
    && finiteInRange(metrics.sparse_factorization_max_backward_error, 0, 1e-12)
}

function finiteInRange(value: unknown, minimum: number, maximum: number): boolean {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
}

function validEngineeringResultIrShape(value: unknown): value is Record<string, unknown> {
  if (!record(value)) return false
  const requiredHashes = [
    'engineering_result_hash',
    'compiler_hash',
    'source_adapter_hash',
    'model_content_hash',
    'problem_contract_hash',
    'terminal_checkpoint_hash',
    'terminal_assembly_hash',
    'quantity_catalog_hash',
    'array_bundle_hash',
  ]
  const counts = value.counts
  const descriptors = value.array_descriptors
  return value.schema_version === 'corotational-fiber-frame2d-engineering-result-ir.v1'
    && typeof value.engineering_result_id === 'string'
    && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(value.engineering_result_id)
    && typeof value.result_kind === 'string'
    && typeof value.recovery_profile === 'string'
    && typeof value.authority_profile === 'string'
    && requiredHashes.every((key) => hash(value[key]))
    && value.load_factor === 1
    && record(counts)
    && integerInRange(counts.node, 2, 128)
    && integerInRange(counts.member, 1, 256)
    && integerInRange(counts.section, 1)
    && integerInRange(counts.fiber, 1)
    && stringArray(value.member_ids, 1, 256, true)
    && (value.member_ids as string[]).length === counts.member
    && record(value.metrics)
    && record(value.authority_axes)
    && stringArray(value.limitations, 1)
    && Array.isArray(descriptors)
    && descriptors.length === 18
    && descriptors.every(validArrayDescriptor)
}

function validArrayDescriptor(value: unknown): boolean {
  if (!record(value)) return false
  return typeof value.name === 'string'
    && value.name.length > 0
    && (value.dtype === '<f8' || value.dtype === '<i8')
    && Array.isArray(value.shape)
    && value.shape.length > 0
    && value.shape.every((item) => integerInRange(item, 0))
    && typeof value.unit === 'string'
    && value.unit.length > 0
    && stringArray(value.quantity_ids, 0, undefined, true)
    && ['node', 'member', 'section', 'fiber'].includes(String(value.order_scope))
    && (value.authority_role === 'output' || value.authority_role === 'mapping')
    && hash(value.order_hash)
    && hash(value.data_hash)
    && hash(value.content_hash)
}

function validCoreValidationReport(report: unknown, result: unknown): boolean {
  if (!record(report) || !record(result)) return false
  return report.schema_version === 'unified-nonlinear-frame-validation-report.v1'
    && report.status === 'ready'
    && report.contract_pass === true
    && report.result_hash === result.result_hash
    && report.profile === result.profile
    && report.exact_engineering_recovery === true
    && report.exact_checkpoint_chain_replay === true
    && report.checkpoint_available === true
    && report.unsupported_feature_count === 0
    && report.fallback_count === 0
    && report.regularization_count === 0
}

function integerInRange(value: unknown, minimum: number, maximum?: number): value is number {
  return typeof value === 'number'
    && Number.isInteger(value)
    && value >= minimum
    && (maximum === undefined || value <= maximum)
}

function stringArray(
  value: unknown,
  minimum: number,
  maximum?: number,
  unique = false,
): value is string[] {
  if (!Array.isArray(value) || value.length < minimum || (maximum !== undefined && value.length > maximum)) return false
  if (!value.every((item) => typeof item === 'string' && item.length > 0)) return false
  return !unique || new Set(value).size === value.length
}

function hash(value: unknown): value is string {
  return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value)
}
