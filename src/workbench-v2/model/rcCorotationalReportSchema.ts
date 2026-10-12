import Ajv2020 from 'ajv/dist/2020.js'
import reportSchema from '../../structural_analysis/schemas/rc_corotational_report_v1.schema.json' assert { type: 'json' }
import { sha256Hex } from './checksum'
import { document, fields, object, rawValues, same, selfHash, type RcObject } from './rcJobSchema'
import { validateWorkbenchJobView, type JobArtifactReference, type WorkbenchJobView } from './jobSchema'

export const RC_COROTATIONAL_REPORT_MAX_BYTES = 64 * 1024 * 1024
export const RC_COROTATIONAL_REPORT_SCHEMA = 'durable-rc-corotational-report.v1'
export const RC_COROTATIONAL_REPORT_CLAIM_BOUNDARY = 'Saved experimental corotational RC nodal accepted-history and recorded execution observations only. Preload and accepted subdivision states are separate from authored targets and spent control attempts. Source revision is a caller declaration; recorded source hashes establish integrity, not independent execution authentication. Pending reservations and unavailable work remain unknown. No fresh analysis, verification or source fingerprint is performed; no independent physical validation, design approval, material quantity/price qualification, or release readiness is granted.'

type ThreeVector = [number, number, number]
export interface RcCorotationalReportNode {
  node_id: string
  displacements_m_rad: ThreeVector
  external_loads_kn_knm: ThreeVector
  reactions_kn_knm: ThreeVector
}
export interface RcCorotationalReportResponse {
  state_index: number
  phase: 'preload' | 'control'
  checkpoint_hash: string
  parent_checkpoint_hash: string
  load_factor: number
  control_displacement_m: number
  nodes: RcCorotationalReportNode[]
}
export interface RcCorotationalPhasePolicy {
  schema_version: 'bounded-rc-corotational-phase-execution-policy.v1'
  analysis_timeout_ms: number
  verification_timeout_ms: number
  termination_grace_ms: number
}
export interface RcCorotationalReportWork {
  preload_solver_calls: number
  restart_replay_solver_calls: number
  control_solver_calls: number
}
export interface RcCorotationalReportInvocation {
  schema_version: 'bounded-rc-corotational-job-invocation.v1' | 'bounded-rc-corotational-job-invocation.v2'
  phase: 'analysis' | 'verification'
  status: 'returned' | 'raised'
  job_request_hash: string
  chunk_request_hash: string
  completed_before: number
  completed_after: number
  restart_input_sha256: string | null
  timing: { wall_ns: number; process_cpu_ns: number | null }
  unavailable_execution_work: boolean
  ordinal: number
  content_hash: string
  byte_length: number
  work: (RcCorotationalReportWork & { unavailable_execution_work: boolean }) | null
  phase_supervision: {
    schema_version: 'bounded-rc-corotational-phase-supervision.v1'
    phase: 'analysis' | 'verification'
    job_request_hash: string
    chunk_request_hash: string
    completed_before: number
    planned_after: number
    restart_input_sha256: string | null
    policy: RcCorotationalPhasePolicy
    status: 'returned' | 'raised' | 'unaccounted'
    supervisor: Record<string, unknown>
    cleanup: Record<string, unknown>
  } | null
}
export interface RcCorotationalReportBindings {
  tenant_id: string
  job_id: string
  completed_job_revision: number
  terminal_event_hash: string
  original_artifacts: {
    request: JobArtifactReference
    checkpoint: JobArtifactReference | null
    result: JobArtifactReference
    evidence: JobArtifactReference
  }
  case_id: string
  request_schema_version: 'structural-analysis-job-request.v6' | 'structural-analysis-job-request.v7'
  source_revision: string
  source_revision_is_execution_attestation: false
  recorded_source_identity: string
  canonical_model_checksum: string
  model_input_checksum: string
  problem_contract_hash: string
  resume_contract_hash: string
  durable_result_hash: string
  terminal_api_artifact_sha256: string
  terminal_native_checkpoint_sha256: string
  terminal_native_checkpoint_byte_length: number
  worker_validator_id: 'structural_analysis.execution.rc_corotational_job_contract.validate_rc_corotational_job_result'
  worker_validation_report_hash: string
  receipt_hashes: string[]
  invocation_artifact_hashes: Record<string, string>
}
export interface RcCorotationalReportDeclarations {
  control: { node_id: string; component: 'UX' | 'UY'; unit: 'm' }
  targets_m: number[]
  fixed_nodal_loads: [string, 'FX' | 'FY' | 'MZ', number][]
  reference_loads: Record<string, unknown>[]
  supports: Record<string, unknown>[]
  model_units: { length: string; force: string }
  coordinate_system: { axis_order: [string, string, string]; up_axis: string }
  model_metadata: Record<string, unknown>
  config: {
    control_node_id: string
    control_component: 'UX' | 'UY'
    targets_m: number[]
    fixed_nodal_loads: [string, 'FX' | 'FY' | 'MZ', number][]
    config: {
      residual_tolerance: number
      control_tolerance_m: number
      increment_tolerance_m: number
      load_factor_increment_tolerance: number
      load_factor_coordinate_scale_m: number
      maximum_iterations: number
      line_search_alphas: number[]
      matrix_backend: string
    }
    preload_config: {
      residual_tolerance: number
      increment_tolerance: number
      max_iterations: number
      line_search_alphas: number[]
      matrix_backend: string
    }
    maximum_attempt_count: number
    maximum_subdivision_depth: number
    experimental_pin_roller_beam: boolean
    experimental_fixed_guided_axial: boolean
  }
  execution_config: {
    attempt_limit_per_call: number
    maximum_api_invocations: number
    phase_execution_policy?: RcCorotationalPhasePolicy
  }
}
/** This complete document, including its arrays, stays inside the reviewer worker. */
export interface RcCorotationalReport {
  schema_version: 'durable-rc-corotational-report.v1'
  bindings: RcCorotationalReportBindings
  declarations: RcCorotationalReportDeclarations
  progress: {
    control_solver_attempts: { completed: number; maximum: number }
    authored_targets: { completed: number; total: number }
    accepted_response_states: number
  }
  units: {
    frame: 'global'
    displacement_components: ['UX', 'UY', 'RZ']
    displacement_units: ['m', 'm', 'rad']
    load_components: ['FX', 'FY', 'MZ']
    load_units: ['kN', 'kN', 'kN*m']
    load_factor: '1'
    reaction_definition: 'internal_minus_external_on_constrained_dofs;free_dofs_zero'
  }
  responses: RcCorotationalReportResponse[]
  execution: {
    unit: 'reserved_api_invocations'
    budget: { maximum_attempts: number; reserved_attempts: number; remaining_attempts: number }
    recorded_invocation_count: number
    pending_ordinals: number[]
    unknown_execution_work: boolean
    known_work: RcCorotationalReportWork
    invocations: RcCorotationalReportInvocation[]
  }
  structural_authority: {
    experimental_corotational_rc_control: true
    trusted_worker_verification_attestation: true
    service_numerical_verification_performed: false
    independent_execution_authentication: false
    independent_physical_validation: false
    design_authority: false
    release_approved: false
    production_promotion_eligible: false
  }
  derivation: {
    version: 'rc_corotational_nodal_report.v1'
    fresh_analysis_invocations: 0
    fresh_verification_invocations: 0
    source_fingerprint_invocations: 0
    new_structural_authority: false
  }
  claim_boundary: string
  report_hash: string
}
export interface RcCorotationalReportExpected {
  job: WorkbenchJobView
  tenantId: string
  request: Record<string, unknown>
}

const validateShape = new Ajv2020({ allErrors: false, strict: true, strictTypes: false }).compile(reportSchema)
const COUNT_MAX = Number.MAX_SAFE_INTEGER
const WORK_KEYS = ['preload_solver_calls', 'restart_replay_solver_calls', 'control_solver_calls'] as const
const DOFS = ['UX', 'UY', 'RZ'] as const
function requireReport(value: unknown, code: string): asserts value {
  if (!value) throw new Error(`rc_corotational_report_${code}`)
}
function count(value: unknown, minimum: number, maximum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum
}

/** AJV sees 1, 1.0 and 1e0 as the same JS integer. Retain Python's exact int contract. */
function integerTokens(value: unknown, raw: string, schema: RcObject): void {
  if (schema.type === 'integer' && typeof value !== 'number') return
  if (schema.type === 'object' && (value === null || typeof value !== 'object' || Array.isArray(value))) return
  if (schema.type === 'array' && !Array.isArray(value)) return
  if (schema.type === 'null' && value !== null) return
  if (schema.type === 'integer' || schema.const === 0) requireReport(count(value, 0, COUNT_MAX)
    && /^(?:0|[1-9]\d*)$/.test(raw), 'integer_token_invalid')
  for (const alternatives of [schema.anyOf, schema.oneOf]) {
    if (Array.isArray(alternatives)) {
      for (const branch of alternatives) integerTokens(value, raw, branch)
    }
  }
  if (Array.isArray(value)) {
    const tokens = rawValues(raw)
    for (let i = 0; i < value.length; i++) {
      const child = schema.prefixItems?.[i] ?? schema.items
      if (child && typeof child === 'object') integerTokens(value[i], tokens[i].trim(), child)
    }
  } else if (value && typeof value === 'object') {
    const members = fields(raw)
    for (const [key, childValue] of Object.entries(value)) {
      const child = schema.properties?.[key] ?? schema.additionalProperties
      if (child && typeof child === 'object') integerTokens(childValue, members.get(key)!.value, child)
    }
  }
}

/** Python's UTF-8 producer cannot emit lone escaped UTF-16 surrogates. */
function unicodeScalars(value: unknown): void {
  if (typeof value === 'string') {
    for (let i = 0; i < value.length; i++) {
      const code = value.charCodeAt(i)
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(++i)
        requireReport(next >= 0xdc00 && next <= 0xdfff, 'unicode_invalid')
      } else requireReport(code < 0xdc00 || code > 0xdfff, 'unicode_invalid')
    }
  } else if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      unicodeScalars(key)
      unicodeScalars(item)
    }
  }
}

function policy(value: RcCorotationalPhasePolicy): void {
  requireReport(count(value.analysis_timeout_ms, 1, 3600000)
    && count(value.verification_timeout_ms, 1, 3600000)
    && count(value.termination_grace_ms, 1, 5000), 'phase_policy_invalid')
}

function requestBindings(report: RcCorotationalReport, expected: RcCorotationalReportExpected): RcObject {
  const job = expected.job, request = object(expected.request), model = object(request.model)
  requireReport(validateWorkbenchJobView(job).ok && job.schema_version === 'structural-analysis-job-view.v2'
    && job.status === 'succeeded' && job.progress.unit === 'control_solver_attempts'
    && job.result !== null && job.evidence !== null
    && count(job.revision, 0, COUNT_MAX) && count(job.attempt, 1, COUNT_MAX), 'job_invalid')
  requireReport(typeof expected.tenantId === 'string' && /^[\x21-\x7e]{1,256}$/.test(expected.tenantId), 'tenant_invalid')
  const binding = report.bindings
  requireReport(binding.tenant_id === expected.tenantId && binding.job_id === job.job_id
    && binding.completed_job_revision === job.revision && binding.terminal_event_hash === job.terminal_event_hash
    && same(binding.original_artifacts, {
      request: job.request, checkpoint: job.checkpoint, result: job.result, evidence: job.evidence,
    }) && binding.resume_contract_hash === job.resume_contract_hash, 'source_binding_invalid')
  for (const [role, reference] of Object.entries(binding.original_artifacts)) {
    if (reference === null) continue
    requireReport(reference.role === role && count(reference.byte_length, 1, 96 * 1024 * 1024), 'artifact_reference_invalid')
  }
  requireReport(count(binding.terminal_native_checkpoint_byte_length, 1, 16 * 1024 * 1024)
    && binding.receipt_hashes.length <= 50000
    && new Set(binding.receipt_hashes).size === binding.receipt_hashes.length, 'receipt_binding_invalid')
  requireReport(request.schema_version === binding.request_schema_version
    && request.operation === 'bounded_rc_corotational_control'
    && request.result_contract === 'bounded-rc-corotational-job-result.v1'
    && binding.case_id === request.case_id && binding.source_revision === request.source_revision,
  'request_binding_invalid')
  const config = object(request.config), declarations = report.declarations
  requireReport(same(declarations, {
    control: { node_id: config.control_node_id, component: config.control_component, unit: 'm' },
    targets_m: config.targets_m, fixed_nodal_loads: config.fixed_nodal_loads,
    reference_loads: model.loads, supports: model.supports, model_units: model.units,
    coordinate_system: model.coordinate_system, model_metadata: model.metadata,
    config: request.config, execution_config: request.execution_config,
  }), 'declaration_binding_invalid')
  const declared = declarations.config, execution = declarations.execution_config
  requireReport(count(execution.attempt_limit_per_call, 1, 4096)
    && count(execution.maximum_api_invocations, 1, 100000)
    && !(declared.experimental_pin_roller_beam && declared.experimental_fixed_guided_axial), 'request_budget_invalid')
  for (const solver of [declared.config, declared.preload_config]) {
    const row = solver as unknown as RcObject
    for (const [key, value] of Object.entries(row)) {
      if (key.includes('tolerance') || key === 'load_factor_coordinate_scale_m') {
        requireReport(typeof value === 'number' && Number.isFinite(value) && value > 0, 'solver_config_invalid')
      }
    }
    requireReport(count(row.maximum_iterations ?? row.max_iterations, 0, 200)
      && ['numpy_linalg_solve_dense', 'scipy_sparse_spsolve_cpu'].includes(row.matrix_backend)
      && row.line_search_alphas.every((value: number, index: number, values: number[]) =>
        value > 0 && value <= 1 && (index === 0 || value < values[index - 1])), 'solver_config_invalid')
  }
  requireReport(declared.config.matrix_backend === 'numpy_linalg_solve_dense', 'solver_config_invalid')
  const isolated = binding.request_schema_version === 'structural-analysis-job-request.v7'
  requireReport(isolated === (execution.phase_execution_policy !== undefined), 'phase_profile_invalid')
  if (execution.phase_execution_policy) policy(execution.phase_execution_policy)
  return model
}

function responses(report: RcCorotationalReport, job: WorkbenchJobView, model: RcObject): void {
  const declarations = report.declarations, progress = report.progress
  const attempts = progress.control_solver_attempts, authored = progress.authored_targets
  requireReport(attempts.completed === job.progress.completed_steps && attempts.maximum === job.progress.total_steps
    && attempts.maximum === declarations.config.maximum_attempt_count
    && count(attempts.completed, 1, attempts.maximum)
    && authored.completed === declarations.targets_m.length && authored.total === declarations.targets_m.length
    && progress.accepted_response_states === report.responses.length
    && report.responses.length <= attempts.completed + 1
    && report.responses.length >= authored.total + 1, 'progress_binding_invalid')
  requireReport(Array.isArray(model.nodes) && model.nodes.length >= 2 && model.nodes.length <= 16, 'model_nodes_invalid')
  const nodeIds = model.nodes.map((node: unknown) => object(node).id)
  requireReport(nodeIds.every((id: unknown) => typeof id === 'string' && id.length > 0 && id.length <= 256)
    && new Set(nodeIds).size === nodeIds.length, 'model_nodes_invalid')
  const controlIndex = nodeIds.indexOf(declarations.control.node_id)
  requireReport(controlIndex >= 0, 'control_node_invalid')
  const componentIndex = declarations.control.component === 'UX' ? 0 : 1
  const constrained = new Set<string>()
  for (const supportValue of declarations.supports) {
    const support = object(supportValue)
    requireReport(nodeIds.includes(support.node) && Array.isArray(support.dofs)
      && support.dofs.every((dof: unknown) => typeof dof === 'string'), 'supports_invalid')
    for (const dof of support.dofs) if (DOFS.includes(dof)) constrained.add(`${support.node}:${dof}`)
  }
  requireReport(declarations.model_units.length === 'm' && declarations.model_units.force === 'kN', 'model_units_invalid')
  const referenceLoads = new Map<string, ThreeVector>(nodeIds.map(id => [id, [0, 0, 0]]))
  const fixedLoads = new Map<string, ThreeVector>(nodeIds.map(id => [id, [0, 0, 0]]))
  const loadedNodes = new Set<string>(), fixedDofs = new Set<string>()
  for (const value of declarations.reference_loads) {
    const load = object(value), components = object(load.components)
    requireReport(nodeIds.includes(load.node) && !loadedNodes.has(load.node)
      && same(Object.keys(load).sort(), ['components', 'node'])
      && same(Object.keys(components).sort(), ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'])
      && Object.values(components).every(item => typeof item === 'number' && Number.isFinite(item))
      && components.FZ === 0 && components.MX === 0 && components.MY === 0, 'reference_load_invalid')
    loadedNodes.add(load.node)
    referenceLoads.set(load.node, [components.FX, components.FY, components.MZ])
  }
  const loadComponents = ['FX', 'FY', 'MZ']
  for (const [node, component, value] of declarations.fixed_nodal_loads) {
    const identity = `${node}:${component}`
    requireReport(nodeIds.includes(node) && !fixedDofs.has(identity), 'fixed_load_invalid')
    fixedDofs.add(identity)
    fixedLoads.get(node)![loadComponents.indexOf(component)] = value
  }
  requireReport(!constrained.has(`${declarations.control.node_id}:${declarations.control.component}`), 'control_support_invalid')
  const hashes = new Set<string>(), tolerance = declarations.config.config.control_tolerance_m
  const initialParent = report.responses[0].parent_checkpoint_hash
  let previous = report.responses[0].control_displacement_m
  let possibleTargets = new Set([0])
  for (const [index, row] of report.responses.entries()) {
    requireReport(row.state_index === index && row.phase === (index === 0 ? 'preload' : 'control')
      && !hashes.has(row.checkpoint_hash) && row.checkpoint_hash !== initialParent
      && row.checkpoint_hash !== row.parent_checkpoint_hash
      && (index === 0 || row.parent_checkpoint_hash === report.responses[index - 1].checkpoint_hash), 'response_chain_invalid')
    hashes.add(row.checkpoint_hash)
    requireReport(row.nodes.length === nodeIds.length
      && row.nodes.every((node, i) => node.node_id === nodeIds[i]), 'response_node_binding_invalid')
    requireReport(row.control_displacement_m === row.nodes[controlIndex].displacements_m_rad[componentIndex], 'response_control_invalid')
    for (const node of row.nodes) {
      const reference = referenceLoads.get(node.node_id)!, fixed = fixedLoads.get(node.node_id)!
      for (let dof = 0; dof < 3; dof++) {
        const expectedLoad = row.load_factor * reference[dof] + fixed[dof]
        requireReport(Number.isFinite(expectedLoad) && node.external_loads_kn_knm[dof] === expectedLoad, 'external_load_invalid')
        if (constrained.has(`${node.node_id}:${DOFS[dof]}`)) {
          requireReport(node.displacements_m_rad[dof] === 0, 'restrained_displacement_invalid')
        } else requireReport(node.reactions_kn_knm[dof] === 0, 'free_reaction_invalid')
      }
    }
    if (index === 0) requireReport(row.load_factor === 0, 'preload_invalid')
    else {
      const value = row.control_displacement_m, next = new Set<number>()
      // The nodal projection omits each attempted target. A subdivision state
      // can already lie within tolerance of its authored goal; keep both
      // assignments until subsequent states establish a complete target path.
      for (const targetIndex of possibleTargets) {
        if (targetIndex >= declarations.targets_m.length) continue
        const target = declarations.targets_m[targetIndex]
        if (value < Math.min(previous, target) - tolerance
          || value > Math.max(previous, target) + tolerance) continue
        next.add(targetIndex)
        if (Math.abs(value - target) <= tolerance) next.add(targetIndex + 1)
      }
      requireReport(next.size > 0, 'response_target_invalid')
      possibleTargets = next
      previous = value
    }
  }
  requireReport(possibleTargets.has(declarations.targets_m.length), 'terminal_target_invalid')
}

function supervision(row: RcCorotationalReportInvocation, report: RcCorotationalReport): void {
  const expectedPolicy = report.declarations.execution_config.phase_execution_policy
  const isolated = report.bindings.request_schema_version === 'structural-analysis-job-request.v7'
  requireReport(row.schema_version === `bounded-rc-corotational-job-invocation.v${isolated ? 2 : 1}`
    && isolated === (row.phase_supervision !== null), 'invocation_profile_invalid')
  if (!row.phase_supervision) {
    requireReport(row.timing.process_cpu_ns !== null, 'invocation_timing_invalid')
    return
  }
  const item = row.phase_supervision, summary = item.supervisor
  requireReport(same(item.policy, expectedPolicy) && item.phase === row.phase
    && item.job_request_hash === row.job_request_hash && item.chunk_request_hash === row.chunk_request_hash
    && item.completed_before === row.completed_before && item.planned_after === row.completed_after
    && item.restart_input_sha256 === row.restart_input_sha256, 'supervision_binding_invalid')
  if (item.status === 'unaccounted') {
    requireReport(row.status === 'raised' && row.timing.process_cpu_ns === null
      && same(Object.keys(summary).sort(), ['scope', 'wall_ns'])
      && summary.scope === 'parent phase failure; child CPU unavailable'
      && summary.wall_ns === row.timing.wall_ns, 'supervision_unknown_invalid')
    return
  }
  requireReport(item.status === row.status && row.timing.process_cpu_ns !== null
    && same(Object.keys(summary).sort(), ['child_pid', 'child_returncode', 'direct_child_reaped', 'scope',
      'stderr_byte_count', 'stderr_retained_bytes', 'stderr_truncated', 'wall_ns'])
    && summary.scope === 'parent launch/request/import/API/export/IPC/reap; contains child API scope'
    && count(summary.child_pid, 1, COUNT_MAX) && summary.child_returncode === 0
    && summary.direct_child_reaped === true && count(summary.wall_ns, row.timing.wall_ns, COUNT_MAX)
    && count(summary.stderr_byte_count, 0, COUNT_MAX) && count(summary.stderr_retained_bytes, 0, 65536)
    && summary.stderr_retained_bytes === Math.min(summary.stderr_byte_count as number, 65536)
    && summary.stderr_truncated === ((summary.stderr_byte_count as number) > (summary.stderr_retained_bytes as number))
    && Object.keys(item.cleanup).length === 0, 'supervision_measured_invalid')
  const timeout = row.phase === 'analysis' ? item.policy.analysis_timeout_ms : item.policy.verification_timeout_ms
  requireReport((summary.wall_ns as number) <= timeout * 1000000, 'supervision_timeout_invalid')
}

async function execution(report: RcCorotationalReport, raw: string): Promise<void> {
  const execution = report.execution, budget = execution.budget
  requireReport(budget.maximum_attempts === report.declarations.execution_config.maximum_api_invocations
    && count(budget.reserved_attempts, 2, budget.maximum_attempts)
    && budget.remaining_attempts === budget.maximum_attempts - budget.reserved_attempts
    && execution.recorded_invocation_count === execution.invocations.length
    && execution.invocations.length <= budget.reserved_attempts, 'execution_budget_invalid')
  const known = { preload_solver_calls: 0, restart_replay_solver_calls: 0, control_solver_calls: 0 }
  const present = new Set<number>()
  const invocationRaw = rawValues(fields(fields(raw).get('execution')!.value).get('invocations')!.value)
  const chunkHashes = new Map<string, string | null>()
  let ordinal = 0, unknown = execution.pending_ordinals.length > 0
  const maximum = report.progress.control_solver_attempts.maximum
  for (const [index, row] of execution.invocations.entries()) {
    requireReport(count(row.ordinal, ordinal + 1, budget.reserved_attempts)
      && row.job_request_hash === report.bindings.original_artifacts.request.content_hash
      && report.bindings.invocation_artifact_hashes[String(row.ordinal)] === row.content_hash
      && count(row.byte_length, 1, 96 * 1024 * 1024)
      && count(row.completed_before, 0, maximum - 1)
      && row.completed_after === Math.min(maximum, row.completed_before + report.declarations.execution_config.attempt_limit_per_call)
      && (row.completed_before === 0) === (row.restart_input_sha256 === null), 'invocation_binding_invalid')
    ordinal = row.ordinal; present.add(ordinal)
    const members = fields(invocationRaw[index])
    // This immutable binding contains integer counters and hash strings only.
    // Preserve its original tokens rather than serializing parsed JS numbers.
    const chunkRaw = `{"completed_before":${members.get('completed_before')!.value},"job_request_hash":${members.get('job_request_hash')!.value},"planned_after":${members.get('completed_after')!.value},"restart_input_sha256":${members.get('restart_input_sha256')!.value},"schema_version":"bounded-rc-corotational-job-chunk.v1"}`
    if (!chunkHashes.has(chunkRaw)) chunkHashes.set(chunkRaw, await sha256Hex(chunkRaw))
    requireReport(chunkHashes.get(chunkRaw) === row.chunk_request_hash, 'chunk_hash_invalid')
    if (row.status === 'raised') requireReport(row.work === null && row.unavailable_execution_work, 'raised_work_invalid')
    else requireReport(row.work !== null, 'returned_work_invalid')
    unknown ||= row.unavailable_execution_work
    if (row.work) {
      requireReport(!row.work.unavailable_execution_work || row.unavailable_execution_work, 'unknown_work_invalid')
      unknown ||= row.work.unavailable_execution_work
      for (const key of WORK_KEYS) {
        requireReport(count(row.work[key], 0, 4096), 'invocation_work_invalid')
        known[key] += row.work[key]
      }
    }
    supervision(row, report)
    if (row.phase_supervision) {
      const phaseRaw = fields(invocationRaw[index]).get('phase_supervision')!.value
      const summaryRaw = fields(fields(phaseRaw).get('supervisor')!.value)
      for (const key of ['wall_ns', 'child_pid', 'child_returncode', 'stderr_byte_count', 'stderr_retained_bytes']) {
        const token = summaryRaw.get(key)
        if (token) requireReport(/^(?:0|[1-9]\d*)$/.test(token.value), 'integer_token_invalid')
      }
    }
  }
  const pending: number[] = []
  for (let i = 1; i <= budget.reserved_attempts; i++) if (!present.has(i)) pending.push(i)
  requireReport(same(execution.pending_ordinals, pending) && execution.unknown_execution_work === unknown
    && same(execution.known_work, known)
    && Object.keys(report.bindings.invocation_artifact_hashes).length === present.size,
  'execution_accounting_invalid')
}

/** Validate saved declarations and integrity only; never run numerical analysis. */
export async function parseRcCorotationalReport(bytes: Uint8Array, expected: RcCorotationalReportExpected): Promise<RcCorotationalReport> {
  try {
    requireReport(bytes instanceof Uint8Array && bytes.byteLength > 0
      && bytes.byteLength <= RC_COROTATIONAL_REPORT_MAX_BYTES, 'size_invalid')
    requireReport(!(bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf), 'encoding_invalid')
    const { raw, value } = document(bytes)
    unicodeScalars(value)
    requireReport(validateShape(value), 'schema_invalid')
    integerTokens(value, raw, reportSchema)
    await selfHash(raw, value, 'report_hash')
    const report = value as unknown as RcCorotationalReport
    requireReport(report.claim_boundary === RC_COROTATIONAL_REPORT_CLAIM_BOUNDARY, 'claim_boundary_invalid')
    const model = requestBindings(report, expected)
    responses(report, expected.job, model)
    await execution(report, raw)
    return report
  } catch (error) {
    if (error instanceof Error && /^rc_corotational_report_[a-z_]+$/.test(error.message)) throw error
    throw new Error('rc_corotational_report_invalid')
  }
}
