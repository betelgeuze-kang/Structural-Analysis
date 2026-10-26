import type { RcJobSummary, RcObject } from './rcJobSchema'
import type { WorkbenchJobView } from './jobSchema'
import type { RcCorotationalReport } from './rcCorotationalReportSchema'
import type { RcJobDiagnostics } from './rcJobDiagnostics'

export const RC_SCENARIO_LIMIT = 4
export const RC_SCENARIO_VALUE_LIMIT = 512
export const RC_SCENARIO_CURVE_LIMIT = 512
export interface RcScenarioMeasure {
  key: string
  kind: 'displacement' | 'reaction' | 'member_force'
  entity: string
  component: string
  unit: 'm' | 'rad' | 'N' | 'N*m'
  value: number
}
export interface RcScenarioSummary {
  schema: 'rc-scenario-summary.v1'
  sourceRevision: string
  profile: string
  compatibility: string
  targetIndex: number
  targetM: number
  targetsM: number[]
  values: RcScenarioMeasure[]
  curve: Array<{ state: number; displacementM: number; loadFactor: number }>
  bindings: { jobId: string; requestHash: string; resultHash: string; evidenceHash: string; checkpointHash: string | null; revision: number; terminalEventHash: string }
  reviewKind: 'original_artifacts' | 'authenticated_saved_nodal_report'
  memberForcesAvailable: boolean
  unknownWork: boolean
  recordedPhaseWallSeconds: number | null
}
export interface RcScenarioDelta {
  key: string; kind: RcScenarioMeasure['kind']; entity: string; component: string; unit: RcScenarioMeasure['unit']
  baseline: number | null; variant: number | null; delta: number | null
}
export interface RcScenarioComparison {
  compatible: boolean; reason: string; rows: RcScenarioDelta[]
  recordedPhaseWallTimeSeconds?: { baseline: number | null; variant: number | null; delta: number | null }
}
export interface RcScenarioIntent { readonly id: string; readonly name: string; readonly serialized: string; readonly idempotencyKey: string }

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, row]) => `${JSON.stringify(key)}:${stable(row)}`).join(',')}}`
  return JSON.stringify(value) ?? 'null'
}
function sorted(rows: unknown[]): unknown[] { return [...rows].sort((a, b) => stable(a).localeCompare(stable(b))) }

/** Physical comparison scope, not a model equality or execution attestation.
 * Geometry, section and material declarations may differ between designs.
 * Source, control, target occurrence order, loading, units, topology and supports
 * must match so a numerical delta has a defined entity and physical meaning.
 */
function compatibilityProjection(request: RcObject): RcObject {
  const config = request.config, model = request.model
  return {
    schema: request.schema_version, operation: request.operation, resultContract: request.result_contract,
    source: request.source_revision, configSchema: config.schema_version ?? null,
    control: config.control_observation ?? (config.control_node_id !== undefined
      ? { node: config.control_node_id, component: config.control_component }
      : { globalDof: config.control_global_dof, nodeOrder: model.nodes.map((node: RcObject) => node.id) }),
    targets: config.targets_m, units: model.units, coordinates: model.coordinate_system,
    nodes: sorted(model.nodes.map((node: RcObject) => node.id)),
    members: sorted(model.elements.map((member: RcObject) => ({ id: member.id, nodes: member.nodes, node_i: member.node_i, node_j: member.node_j, type: member.type }))),
    supports: sorted(model.supports.map((support: RcObject) => ({ ...support, dofs: sorted(support.dofs) }))),
    loads: sorted(model.loads), constantLoads: sorted(config.fixed_nodal_loads ?? config.constant_nodal_loads ?? []),
    pinRoller: config.experimental_pin_roller_beam ?? null, fixedGuided: config.experimental_fixed_guided_axial ?? null,
    portal: config.experimental_portal_frame ?? null,
  }
}

export function rcScenarioCompatibility(request: RcObject): string { return stable(compatibilityProjection(request)) }

/** Named views of the same numerical-comparison contract; these are not model equality. */
export function rcScenarioCompatibilityFields(request: RcObject): Array<{ key: string; label: string; signature: string }> {
  const labels: Record<string, string> = {
    schema: 'Request profile', operation: 'Analysis operation', resultContract: 'Result contract', source: 'Caller-declared source revision',
    configSchema: 'Control configuration profile', control: 'Control definition and indexed node order', targets: 'Target occurrence order',
    units: 'Model units', coordinates: 'Coordinate convention', nodes: 'Node identities', members: 'Member connectivity and authored direction',
    supports: 'Support restraints', loads: 'Reference loads', constantLoads: 'Fixed preload', pinRoller: 'Pin/roller profile opt-in',
    fixedGuided: 'Fixed/guided profile opt-in', portal: 'Portal profile opt-in',
  }
  return Object.entries(compatibilityProjection(request)).map(([key, value]) => ({ key, label: labels[key], signature: stable(value) }))
}


function bindings(job: WorkbenchJobView): RcScenarioSummary['bindings'] {
  if (job.status !== 'succeeded' || !job.result || !job.evidence) throw new Error('rc_scenario_source_not_succeeded')
  return { jobId: job.job_id, requestHash: job.request.content_hash, resultHash: job.result.content_hash,
    evidenceHash: job.evidence.content_hash, checkpointHash: job.checkpoint?.content_hash ?? null, revision: job.revision, terminalEventHash: job.terminal_event_hash }
}
function measure(kind: RcScenarioMeasure['kind'], entity: string, component: string, unit: RcScenarioMeasure['unit'], value: number): RcScenarioMeasure {
  if (typeof entity !== 'string' || !entity || entity.length > 512 || typeof value !== 'number' || !Number.isFinite(value)) throw new Error('rc_scenario_value_invalid')
  return { key: JSON.stringify([kind, entity, component, unit]), kind, entity, component, unit, value }
}
function bounded(values: RcScenarioMeasure[], curve: RcScenarioSummary['curve']): void {
  if (values.length > RC_SCENARIO_VALUE_LIMIT || curve.length > RC_SCENARIO_CURVE_LIMIT) throw new Error('rc_scenario_summary_limit')
  if (new Set(values.map(row => row.key)).size !== values.length
    || !values.every(row => Number.isFinite(row.value) && row.key === JSON.stringify([row.kind, row.entity, row.component, row.unit])
      && ['displacement', 'reaction', 'member_force'].includes(row.kind) && ['m', 'rad', 'N', 'N*m'].includes(row.unit))
    || !curve.every(row => Number.isFinite(row.displacementM) && Number.isFinite(row.loadFactor))) throw new Error('rc_scenario_value_invalid')
}

/** Called only after original artifact verification, inside the reviewer worker.
 * Final authored target values and a bounded scalar curve leave that worker;
 * section, material and full epoch arrays remain there.
 */
export function fixedRcScenarioSummary(request: RcObject, job: WorkbenchJobView, summary: RcJobSummary, history: RcObject[]): RcScenarioSummary {
  const final = history[history.length - 1]
  if (!final || final.node_displacements.length * 3 + final.support_reactions.length + final.member_end_forces.length * 6 > RC_SCENARIO_VALUE_LIMIT
    || history.length - (summary.hasPreload ? 1 : 0) > RC_SCENARIO_CURVE_LIMIT) throw new Error('rc_scenario_summary_limit')
  const values: RcScenarioMeasure[] = []
  for (const node of final.node_displacements) for (const component of ['UX', 'UY', 'RZ']) values.push(measure('displacement', node.node_id, component, component === 'RZ' ? 'rad' : 'm', node[component === 'RZ' ? 'RZ_rad' : `${component}_m`]))
  for (const row of final.support_reactions) values.push(measure('reaction', row.node_id, row.dof, row.unit, row.value_si))
  for (const member of final.member_end_forces) for (const end of ['i', 'j']) for (const [component, unit] of [['FX', 'N'], ['FY', 'N'], ['MZ', 'N*m']] as const) values.push(measure('member_force', member.member_id, `${end}:${component}`, unit, member[`local_end_${end}`][component === 'MZ' ? 'MZ_Nm' : `${component}_N`]))
  const controlled = history.slice(summary.hasPreload ? 1 : 0)
  const curve = controlled.map((row, index) => {
    const node = row.node_displacements.find((value: RcObject) => value.node_id === summary.control.node_id)
    return { state: index, displacementM: node?.[`${summary.control.component}_m`], loadFactor: row.load_factor }
  })
  bounded(values, curve)
  return { schema: 'rc-scenario-summary.v1', sourceRevision: summary.sourceRevision, profile: request.operation,
    compatibility: rcScenarioCompatibility(request), targetIndex: summary.targets.length - 1, targetM: summary.targets[summary.targets.length - 1], targetsM: [...summary.targets],
    values, curve, bindings: bindings(job), reviewKind: 'original_artifacts', memberForcesAvailable: true, unknownWork: summary.unknownWork, recordedPhaseWallSeconds: null }
}

/** Saved corotational reports expose nodal quantities only. Their accepted
 * subdivision states cannot be relabelled as authored target occurrences.
 * Compare only the terminal authored target; graph the actual accepted states.
 */
export function corotationalRcScenarioSummary(request: RcObject, job: WorkbenchJobView, report: RcCorotationalReport): RcScenarioSummary {
  const final = report.responses[report.responses.length - 1], values: RcScenarioMeasure[] = []
  if (!final || final.nodes.length * 6 > RC_SCENARIO_VALUE_LIMIT || report.responses.length - 1 > RC_SCENARIO_CURVE_LIMIT) throw new Error('rc_scenario_summary_limit')
  for (const node of final.nodes) for (let index = 0; index < 3; index++) {
    const component = ['UX', 'UY', 'RZ'][index]
    values.push(measure('displacement', node.node_id, component, index === 2 ? 'rad' : 'm', node.displacements_m_rad[index]))
    values.push(measure('reaction', node.node_id, component, index === 2 ? 'N*m' : 'N', node.reactions_kn_knm[index] * 1000))
  }
  const curve = report.responses.filter(row => row.phase === 'control').map(row => ({ state: row.state_index, displacementM: row.control_displacement_m, loadFactor: row.load_factor }))
  bounded(values, curve)
  const targets = report.declarations.targets_m
  return { schema: 'rc-scenario-summary.v1', sourceRevision: report.bindings.source_revision, profile: request.operation,
    compatibility: rcScenarioCompatibility(request), targetIndex: targets.length - 1, targetM: targets[targets.length - 1], targetsM: [...targets],
    values, curve, bindings: bindings(job), reviewKind: 'authenticated_saved_nodal_report', memberForcesAvailable: false,
    unknownWork: report.execution.unknown_execution_work,
    recordedPhaseWallSeconds: report.execution.unknown_execution_work ? null : report.execution.invocations.reduce((sum, row) => sum + row.timing.wall_ns / 1e9, 0) }
}

export function compareRcScenarios(baseline: RcScenarioSummary, variant: RcScenarioSummary): RcScenarioComparison {
  if (baseline.compatibility !== variant.compatibility || baseline.profile !== variant.profile || baseline.sourceRevision !== variant.sourceRevision
    || baseline.targetIndex !== variant.targetIndex || baseline.targetM !== variant.targetM || stable(baseline.targetsM) !== stable(variant.targetsM)) {
    return { compatible: false, reason: 'Source, profile, control, target occurrence order, loading, units, topology or supports differ.', rows: [] }
  }
  bounded(baseline.values, baseline.curve); bounded(variant.values, variant.curve)
  const left = new Map(baseline.values.map(row => [row.key, row])), right = new Map(variant.values.map(row => [row.key, row]))
  const rows = [...new Set([...left.keys(), ...right.keys()])].sort().map(key => {
    const a = left.get(key), b = right.get(key), row = a ?? b!
    const delta = a && b ? b.value - a.value : null
    if (delta !== null && !Number.isFinite(delta)) throw new Error('rc_scenario_delta_invalid')
    return { key, kind: row.kind, entity: row.entity, component: row.component, unit: row.unit, baseline: a?.value ?? null, variant: b?.value ?? null, delta }
  })
  const baselineTime = baseline.recordedPhaseWallSeconds, variantTime = variant.recordedPhaseWallSeconds
  const timeDelta = baselineTime === null || variantTime === null ? null : variantTime - baselineTime
  return { compatible: true, reason: 'Variant minus baseline at the final authored target. Unavailable entities stay unknown.', rows,
    recordedPhaseWallTimeSeconds: { baseline: baselineTime, variant: variantTime, delta: timeDelta !== null && Number.isFinite(timeDelta) ? timeDelta : null } }
}

export function rcScenarioSafeMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : ''
  if (rcScenarioAuthorizationFailure(error)) return 'Authorization changed or became unavailable. Reopen this workspace to start a new session.'
  if (/unconfirmed/.test(message)) return 'Submission outcome is unconfirmed. The queue stopped; retry uses the same original request and key.'
  if (/summary_limit/.test(message)) return 'The saved result exceeds the bounded comparison summary size. Open the individual job.'
  if (/http_400|http_409|http_413/.test(message)) return 'The service rejected this request. Review its original job and input.'
  return 'This scenario result is unavailable. Open the individual job or refresh its stored state.'
}

export function rcScenarioAuthorizationFailure(error: unknown): boolean {
  return error instanceof Error && /authorization|scope_changed|(?:HTTP|http)_(?:401|403)(?:\b|$)/.test(error.message)
}

/** Complete recorded phase pairs only. Pending, unavailable or unmatched work
 * cannot become a total elapsed-time estimate or an inferred zero duration.
 */
export function rcScenarioRecordedWallSeconds(summary: RcScenarioSummary, diagnostics: RcJobDiagnostics): number | null {
  if (summary.unknownWork || diagnostics.unknownWork || diagnostics.pending.length
    || diagnostics.jobId !== summary.bindings.jobId || diagnostics.requestHash !== summary.bindings.requestHash
    || diagnostics.analysisWallSeconds === null || diagnostics.verificationWallSeconds === null) return null
  const phases = new Map<string, Set<string>>()
  for (const row of diagnostics.invocations) {
    if (row.status !== 'returned' || row.unavailable_execution_work) return null
    const key = stable([row.chunk_request_hash, row.completed_before, row.completed_after, row.restart_input_sha256])
    const found = phases.get(key) ?? new Set<string>()
    if (found.has(row.phase)) return null
    found.add(row.phase); phases.set(key, found)
  }
  if (!phases.size || [...phases.values()].some(row => row.size !== 2)) return null
  const total = diagnostics.analysisWallSeconds + diagnostics.verificationWallSeconds
  return Number.isFinite(total) ? total : null
}


export function exportRcScenarios(rows: Array<{ name: string; status: string; jobId?: string; summary?: RcScenarioSummary }>, baselineId: string | null): string {
  if (rows.length > RC_SCENARIO_LIMIT) throw new Error('rc_scenario_export_limit')
  for (const row of rows) if (row.summary) bounded(row.summary.values, row.summary.curve)
  const baseline = rows.find(row => row.summary?.bindings.jobId === baselineId)?.summary
  const comparisons = baseline ? rows.filter(row => row.summary).map(row => ({ jobId: row.summary!.bindings.jobId, ...compareRcScenarios(baseline, row.summary!) })) : []
  const value = JSON.stringify({ schema: 'rc-scenario-comparison.v1', baselineJobId: baselineId,
    meaning: 'Derived scenario differences only. Source revision is a caller declaration. No benchmark accuracy, independent physical validation, design authority, inferred financial cost or release qualification.',
    scenarios: rows, comparisons }, null, 2)
  if (new TextEncoder().encode(value).byteLength > 2 * 1024 * 1024) throw new Error('rc_scenario_export_limit')
  return value
}
