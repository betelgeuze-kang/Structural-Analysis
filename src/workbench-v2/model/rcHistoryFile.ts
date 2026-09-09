import { sha256Bytes, sha256Hex } from './checksum'
import { check, CLAIMS, document, fields, object, same, selfHash, type RcObject } from './rcJobSchema'

export const RC_HISTORY_RECORD_LIMIT = 16 * 1024 * 1024
export const RC_HISTORY_FILE_LIMIT = 512 * 1024 * 1024
const CHUNK = 256 * 1024
const hash = (v: unknown) => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)
const nat = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0
const numbers = (v: unknown): v is number[] => Array.isArray(v) && v.every(n => typeof n === 'number' && Number.isFinite(n))
export interface RcHistoryOffset { start: number; end: number; hash: string }
export interface RcHistoryIndex {
  header: RcObject
  records: RcHistoryOffset[] // Includes the header; response bodies are not retained.
  acceptedCount: number
  hasPreload: boolean
  status: 'complete' | 'prefix' | 'blocked'
  control: { node_id: string; component: string; unit: string }
  knownCalls: number
  knownNewton: number
  unknownCalls: number
  lastRecordHash: string
}

async function* lines(file: Blob): AsyncGenerator<{ raw: Uint8Array; start: number; end: number }> {
  check(file.size > 0 && file.size <= RC_HISTORY_FILE_LIMIT, 'history_file_size_invalid')
  let carry = new Uint8Array(0), lineStart = 0
  for (let offset = 0; offset < file.size; offset += CHUNK) {
    const chunk = new Uint8Array(await file.slice(offset, Math.min(file.size, offset + CHUNK)).arrayBuffer())
    const joined = new Uint8Array(carry.length + chunk.length)
    joined.set(carry); joined.set(chunk, carry.length)
    let start = 0
    for (let end = 0; end < joined.length; end += 1) {
      if (joined[end] !== 10) continue
      const length = end - start
      check(length > 0 && length <= RC_HISTORY_RECORD_LIMIT, 'history_record_size_invalid')
      yield { raw: joined.slice(start, end), start: lineStart, end: lineStart + length }
      lineStart += length + 1; start = end + 1
    }
    carry = joined.slice(start)
    check(carry.length <= RC_HISTORY_RECORD_LIMIT, 'history_record_size_invalid')
  }
  check(carry.length === 0, 'history_incomplete_record')
}

function validateHeader(h: RcObject): void {
  const r = object(h.request), cfg = object(r.solver_config), n = object(cfg.newton)
  check(h.schema_version === 'rc-fiber-control-history-header.v1'
    && r.schema_version === 'rc-fiber-control-history-request.v1'
    && same(h.claims, CLAIMS) && h.record_max_bytes === RC_HISTORY_RECORD_LIMIT
    && hash(h.canonical_model_checksum) && hash(h.input_checksum) && hash(h.problem_contract_hash), 'history_header_invalid')
  check(numbers(r.targets_m) && r.targets_m.length > 0 && r.targets_m.length <= 4096
    && nat(r.maximum_targets) && r.maximum_targets >= r.targets_m.length && r.maximum_targets <= 4096
    && nat(r.maximum_reversals) && r.maximum_reversals < 4096 && typeof r.allow_reversals === 'boolean'
    && (r.allow_reversals || r.maximum_reversals === 0)
    && r.targets_m.every((v: number, i: number) => i === 0 || v !== r.targets_m[i - 1])
    && nat(r.control_global_dof) && r.control_global_dof < 48 && r.control_global_dof % 3 !== 2,
  'history_request_invalid')
  check(typeof cfg.control_tolerance_m === 'number' && cfg.control_tolerance_m > 0
    && typeof cfg.load_factor_coordinate_scale_m === 'number' && cfg.load_factor_coordinate_scale_m > 0
    && typeof n.residual_tolerance === 'number' && n.residual_tolerance > 0
    && nat(n.max_iterations) && n.max_iterations <= 200, 'history_configuration_invalid')
  if (r.constant_nodal_loads !== undefined) {
    check(Array.isArray(r.constant_nodal_loads) && r.constant_nodal_loads.length > 0
      && r.constant_nodal_loads.length <= 16, 'history_constants_invalid')
    const ids = new Set<string>()
    for (const load of r.constant_nodal_loads) {
      check(typeof load.node_id === 'string' && load.node_id.length > 0 && !ids.has(load.node_id)
        && numbers([load.FX_kN, load.FY_kN, load.MZ_kNm])
        && [load.FX_kN, load.FY_kN, load.MZ_kNm].some(v => v !== 0), 'history_constants_invalid')
      ids.add(load.node_id)
    }
  }
}

/** Compare displayed physical values to the same record's original assembly.
 * This is a stored representation check, not a constitutive reanalysis.
 */
function physical(row: RcObject, a: RcObject, child: RcObject, identity: string | null): string {
  const nodes = row.node_displacements, members = row.member_end_forces
  check(Array.isArray(nodes) && nodes.length > 0 && nodes.length <= 16
    && Array.isArray(members) && members.length > 0 && members.length <= 15
    && Array.isArray(row.section_results) && Array.isArray(row.fiber_results)
    && row.fiber_results.length > 0 && row.fiber_results.length <= 100000
    && row.material_point_count === row.fiber_results.length, 'history_physical_rows_invalid')
  const ids = nodes.map((n: RcObject) => n.node_id)
  check(ids.every((id: unknown) => typeof id === 'string' && id.length > 0) && new Set(ids).size === ids.length
    && numbers(a.global_displacements) && a.global_displacements.length === nodes.length * 3
    && same(a.global_displacements, child.global_displacements)
    && numbers(a.reactions_global) && a.reactions_global.length === nodes.length * 3
    && Array.isArray(a.free_global_dofs) && new Set(a.free_global_dofs).size === a.free_global_dofs.length
    && a.free_global_dofs.every((d: unknown) => nat(d) && Number(d) < nodes.length * 3), 'history_coordinates_invalid')
  const reactions: RcObject[] = []
  nodes.forEach((n: RcObject, i: number) => {
    check(n.UX_m === a.global_displacements[3 * i] && n.UY_m === a.global_displacements[3 * i + 1]
      && n.RZ_rad === a.global_displacements[3 * i + 2] && n.UZ_m === 0 && n.RX_rad === 0 && n.RY_rad === 0,
    'history_displacement_projection_invalid')
    for (let d = 0; d < 3; d += 1) if (!a.free_global_dofs.includes(3 * i + d)) reactions.push({
      node_id: n.node_id, dof: ['UX', 'UY', 'RZ'][d], unit: d === 2 ? 'N*m' : 'N', value_si: a.reactions_global[3 * i + d] * 1000,
    })
  })
  check(same(reactions, row.support_reactions) && Array.isArray(a.member_assemblies)
    && a.member_assemblies.length === members.length && child.element_states.length === members.length,
  'history_reaction_projection_invalid')
  let sectionCount = 0, fiberCount = 0
  const memberIds = new Set<string>()
  for (const [i, m] of members.entries()) {
    const source = object(a.member_assemblies[i]), e = object(source.element_response), dofs = source.global_dofs
    check(typeof m.member_id === 'string' && !memberIds.has(m.member_id) && m.member_id === source.member_id
      && Array.isArray(dofs) && dofs.length === 6 && dofs.every((d: unknown) => nat(d) && Number(d) < nodes.length * 3)
      && m.node_i === ids[dofs[0] / 3] && m.node_j === ids[dofs[3] / 3]
      && numbers(e.internal_force_local) && e.internal_force_local.length === 6
      && same(child.element_states[i], e.trial_state), 'history_member_binding_invalid')
    memberIds.add(m.member_id)
    for (const [j, name] of ['local_end_i', 'local_end_j'].entries()) {
      for (const [d, field] of ['FX_N', 'FY_N', 'MZ_Nm'].entries()) {
        check(m[name][field] === e.internal_force_local[j * 3 + d] * 1000, 'history_force_projection_invalid')
      }
    }
    check(m.dissipated_energy_MJ === e.dissipated_energy_mj, 'history_energy_projection_invalid')
    for (const [ip, s] of e.section_responses.entries()) {
      const projected = object(row.section_results[sectionCount++]), state = object(s.trial_state)
      check(projected.member_id === m.member_id && projected.integration_point_index === ip
        && projected.xi === e.integration_point_xi[ip] && projected.weight === e.integration_point_weights[ip]
        && projected.axial_strain === state.axial_strain && projected.curvature_z_per_m === state.curvature_z_per_m
        && projected.axial_force_N === s.resultants.axial_force_kn * 1000 && projected.moment_z_Nm === s.resultants.moment_z_kn_m * 1000
        && projected.section_state_hash === state.state_hash
        && projected.dissipated_energy_MJ_per_m === s.dissipated_energy_mj_per_m
        && same(e.trial_state.integration_point_states[ip], state), 'history_section_projection_invalid')
      for (const [fi, material] of state.fiber_states.entries()) {
        const f = object(row.fiber_results[fiberCount++])
        check(f.member_id === m.member_id && f.integration_point_index === ip && f.fiber_index === fi
          && typeof f.fiber_id === 'string' && ['steel', 'concrete'].includes(f.material_kind)
          && typeof f.y_m === 'number' && typeof f.area_m2 === 'number' && f.area_m2 > 0
          && f.strain === s.fiber_strains[fi] && f.stress_MPa === s.fiber_stresses_mpa[fi]
          && f.dissipated_energy_density_MJ_per_m3 === material.dissipated_energy_density_mj_per_m3
          && same(f.material_state, material) && hash(material.state_hash), 'history_fiber_projection_invalid')
      }
    }
  }
  check(sectionCount === row.section_results.length && fiberCount === row.fiber_results.length, 'history_projection_count_invalid')
  const signature = JSON.stringify([ids, members.map((m: RcObject) => [m.member_id, m.node_i, m.node_j]),
    row.fiber_results.map((f: RcObject) => [f.member_id, f.integration_point_index, f.fiber_index, f.fiber_id, f.material_kind, f.y_m, f.area_m2])])
  check(identity === null || identity === signature, 'history_entity_identity_changed')
  return signature
}

export async function scanRcHistoryFile(file: Blob, progress?: (count: number) => void): Promise<RcHistoryIndex> {
  let index: RcHistoryIndex | null = null, parent: RcObject | null = null, identity: string | null = null
  let priorHash = '', targets = 0, direction = 0, reversals = 0, origin = 0, stopped = false
  for await (const line of lines(file)) {
    const { raw, value } = document(line.raw), digest = await sha256Bytes(line.raw)
    check(typeof digest === 'string', 'history_hash_unavailable')
    if (!index) {
      validateHeader(value)
      priorHash = digest
      index = { header: value, records: [], acceptedCount: 0, hasPreload: !!value.request.constant_nodal_loads,
        status: 'prefix', control: { node_id: 'unavailable', component: value.request.control_global_dof % 3 === 0 ? 'UX' : 'UY', unit: 'm' },
        knownCalls: 0, knownNewton: 0, unknownCalls: 0, lastRecordHash: digest }
    } else {
      const h = index.header, r = h.request, count = index.records.length - 1
      check(!stopped && count < r.targets_m.length + Number(index.hasPreload), 'history_extra_record')
      check(value.schema_version === 'rc-fiber-control-history-transition.v1' && value.sequence === count
        && value.header_sha256 === index.records[0].hash && value.previous_record_hash === priorHash,
      'history_sequence_invalid')
      await selfHash(raw, value, 'record_hash')
      const preload = index.hasPreload && count === 0
      check(value.kind === (preload ? 'preload' : 'control') && value.target_index === (preload ? null : targets)
        && value.target_m === (preload ? null : r.targets_m[targets]), 'history_target_binding_invalid')
      const attempt = object(value.attempt), child = object(value.accepted_checkpoint), step = attempt.step
      check(child.schema_version === 'stateful-fiber-frame2d-checkpoint.v1' && child.role === 'committed'
        && child.problem_contract_hash === h.problem_contract_hash && hash(child.state_hash), 'history_checkpoint_invalid')
      check(step ? same(attempt.solver_work, step.trial_solution.metrics) : attempt.solver_work === null, 'history_work_binding_invalid')
      if (!preload && (step === null || step.committed === false)) {
        check(parent !== null && same(child, parent) && value.response === null && attempt.committed === false
          && attempt.rollback_exact === true && attempt.parent_checkpoint_hash === parent.state_hash
          && attempt.accepted_checkpoint_hash === parent.state_hash, 'history_rollback_invalid')
        if (step) check(same(step.accepted_checkpoint, child) && same(step.parent_checkpoint, child), 'history_failed_step_invalid')
        stopped = true
      } else {
        check(step && step.committed === true && step.status === 'ready'
          && same(step.accepted_checkpoint, child) && same(attempt.solver_work, step.trial_solution.metrics)
          && child.epoch === count + 1 && child.step_index === count + 1
          && child.parent_state_hash === step.parent_checkpoint.state_hash
          && step.parent_checkpoint.problem_contract_hash === h.problem_contract_hash
          && step.parent_checkpoint.case_id === child.case_id
          && (parent ? same(step.parent_checkpoint, parent) : step.parent_checkpoint.epoch === 0), 'history_ancestry_invalid')
        const row = object(value.response), a = object(step.trial_assembly)
        const stepRaw = fields(fields(raw).get('attempt')!.value).get('step')!.value
        check(row.epoch === child.epoch && row.step_index === child.step_index && row.load_factor === child.load_factor
          && row.checkpoint_hash === child.state_hash && row.parent_checkpoint_hash === child.parent_state_hash
          && a.parent_checkpoint_hash === child.parent_state_hash && a.target_load_factor === child.load_factor
          && row.recovery_scope === 'exact_previous_parent_original_newton_coordinates_constitutive_transition'
          && row.replayed_assembly_hash === await sha256Hex(fields(stepRaw).get('trial_assembly')!.value), 'history_response_binding_invalid')
        if (preload) check(attempt.phase === 'constant_load_preload' && child.load_factor === 0
          && row.source_step_hash === await sha256Hex(stepRaw), 'history_preload_invalid')
        else check(step.schema_version === 'small-displacement-rc-fiber-control-step.v1'
          && hash(step.step_hash) && row.source_step_hash === step.step_hash && attempt.committed === true
          && attempt.parent_checkpoint_hash === child.parent_state_hash && attempt.accepted_checkpoint_hash === child.state_hash
          && attempt.target_control_displacement_m === value.target_m, 'history_control_step_invalid')
        identity = physical(row, a, child, identity)
        if (preload) {
          const constants = Array(row.node_displacements.length * 3).fill(0)
          for (const load of r.constant_nodal_loads) {
            const node = row.node_displacements.findIndex((n: RcObject) => n.node_id === load.node_id)
            check(node >= 0, 'history_constant_node_invalid')
            constants.splice(node * 3, 3, load.FX_kN, load.FY_kN, load.MZ_kNm)
          }
          check(same(constants, a.external_loads_global), 'history_constant_load_binding_invalid')
        }
        const controlled = row.node_displacements[Math.floor(r.control_global_dof / 3)]
        check(controlled, 'history_control_node_invalid')
        index.control.node_id = controlled.node_id
        if (preload) origin = child.global_displacements[r.control_global_dof]
        else {
          const next = Math.sign(value.target_m - origin)
          check(next !== 0 && Math.abs(child.global_displacements[r.control_global_dof] - value.target_m) <= r.solver_config.control_tolerance_m,
            'history_control_target_invalid')
          if (direction && direction !== next) reversals += 1
          check(reversals <= r.maximum_reversals, 'history_reversal_budget_invalid')
          direction = next; origin = value.target_m; targets += 1
        }
        parent = child; index.acceptedCount += 1
      }
      const metrics = attempt.solver_work
      if (step && metrics && nat(metrics.linear_solve_count) && nat(metrics.iteration_count)) {
        index.knownCalls += 1; index.knownNewton += metrics.iteration_count
      } else index.unknownCalls += 1
      priorHash = value.record_hash; index.lastRecordHash = priorHash
    }
    check(index, 'history_header_missing')
    index.records.push({ start: line.start, end: line.end, hash: digest })
    if (index.records.length % 20 === 0) progress?.(index.records.length - 1)
  }
  check(index && index.acceptedCount > 0, 'history_no_accepted_response')
  index.status = stopped ? 'blocked' : targets === index.header.request.targets_m.length ? 'complete' : 'prefix'
  progress?.(index.records.length - 1)
  return index
}

export async function readRcHistoryRecord(file: Blob, index: RcHistoryIndex, recordIndex: number): Promise<Uint8Array> {
  check(nat(recordIndex) && recordIndex < index.records.length, 'history_index_invalid')
  const entry = index.records[recordIndex]
  const framed = new Uint8Array(await file.slice(entry.start, entry.end + 1).arrayBuffer())
  check(framed.length === entry.end - entry.start + 1 && framed[framed.length - 1] === 10, 'history_record_changed')
  const raw = framed.slice(0, -1)
  check(await sha256Bytes(raw) === entry.hash, 'history_record_changed')
  return raw
}
