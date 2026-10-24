import Ajv2020 from 'ajv/dist/2020.js'
import detailSchema from '../../structural_analysis/schemas/rc_corotational_detail_report_v1.schema.json' assert { type: 'json' }
import { document, same, selfHash, type RcObject } from './rcJobSchema'
import { corotationalIntegerTokens, corotationalUnicodeScalars, type RcCorotationalReport,
  type RcCorotationalReportBindings, type RcCorotationalReportExpected } from './rcCorotationalReportSchema'

export interface RcCorotationalDetailFiber {
  fiber_index: number; material_kind: 'concrete' | 'steel'; strain: number; stress_mpa: number; state_hash: string
}
export interface RcCorotationalDetailSection {
  integration_point_index: number; xi: number; weight: number; section_id: string; section_contract_hash: string
  state_hash: string; step_index: number; axial_strain: number; curvature_z_per_m: number
  axial_force_kn: number; moment_z_kn_m: number; fibers: RcCorotationalDetailFiber[]
}
export interface RcCorotationalDetailMember {
  member_index: number; member_id: string; node_i: string; node_j: string
  element_contract_hash: string; member_feature_contract_hash: string; member_feature_response_hash: string
  initial_length_m: number; current_length_m: number; current_direction: [number, number]
  end_force_global_kn_knm: [number, number, number, number, number, number]
  end_force_local_kn_knm: [number, number, number, number, number, number]
  sections: RcCorotationalDetailSection[]
}
export interface RcCorotationalDetailResponse {
  state_index: number; phase: 'preload' | 'control'; checkpoint_hash: string; parent_checkpoint_hash: string
  load_factor: number; members: RcCorotationalDetailMember[]
}
/** Kept inside the reviewer worker; UI methods project one selection or page. */
export interface RcCorotationalDetailReport {
  schema_version: 'durable-rc-corotational-detail-report.v1'
  bindings: RcCorotationalReportBindings; nodal_report_hash: string; units: Record<string, unknown>
  responses: RcCorotationalDetailResponse[]; structural_authority: RcCorotationalReport['structural_authority']
  derivation: Record<string, unknown>; claim_boundary: string; report_hash: string
}
export interface RcCorotationalDetailSummary {
  reportId: string; contentHash: string; reportHash: string; stateCount: number
  members: Array<{ member_id: string; node_i: string; node_j: string; sectionCount: number }>
}
export type RcCorotationalDetailMemberView = Omit<RcCorotationalDetailMember, 'sections'> & {
  sections: Array<{ integration_point_index: number; xi: number; section_id: string; fiberCount: number }>
}
export type RcCorotationalDetailSectionView = Omit<RcCorotationalDetailSection, 'fibers'> & { fiberCount: number }
export type RcCorotationalSectionHistory = RcCorotationalDetailSectionView & { state_index: number; phase: 'preload' | 'control' }
export type RcCorotationalFiberHistory = RcCorotationalDetailFiber & { state_index: number; phase: 'preload' | 'control' }

const validate = new Ajv2020({ allErrors: false, strict: true, strictTypes: false }).compile(detailSchema)
const index = (value: number) => Number.isSafeInteger(value) && value >= 0
function check(value: unknown, code: string): asserts value { if (!value) throw new Error(`rc_corotational_report_detail_${code}`) }

/** This verifies saved identity, ordering and projections; it never calls a solver. */
export async function parseRcCorotationalDetailReport(bytes: Uint8Array, expected: RcCorotationalReportExpected, nodal: RcCorotationalReport): Promise<RcCorotationalDetailReport> {
  try {
    check(bytes instanceof Uint8Array && bytes.byteLength > 0 && bytes.byteLength <= 64 * 1024 * 1024, 'size_invalid')
    check(!(bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf), 'encoding_invalid')
    const { raw, value } = document(bytes)
    corotationalUnicodeScalars(value)
    check(validate(value), 'schema_invalid')
    corotationalIntegerTokens(value, raw, detailSchema)
    await selfHash(raw, value, 'report_hash')
    const report = value as unknown as RcCorotationalDetailReport
    check(same(report.bindings, nodal.bindings) && report.nodal_report_hash === nodal.report_hash
      && same(report.structural_authority, nodal.structural_authority), 'binding_invalid')
    check(report.responses.length === nodal.responses.length, 'state_binding_invalid')
    const members = (expected.request.model as RcObject).elements as RcObject[]
    check(members.length > 0 && members.length <= 256, 'member_bound_invalid')
    for (const [stateIndex, response] of report.responses.entries()) {
      const state = nodal.responses[stateIndex]
      check(response.state_index === state.state_index && response.phase === state.phase
        && response.checkpoint_hash === state.checkpoint_hash && response.parent_checkpoint_hash === state.parent_checkpoint_hash
        && response.load_factor === state.load_factor && response.members.length === members.length, 'state_binding_invalid')
      for (const [memberIndex, member] of response.members.entries()) {
        const authored = members[memberIndex], first = report.responses[0].members[memberIndex]
        check(member.member_index === memberIndex && member.member_id === authored.id
          && member.node_i === authored.nodes[0] && member.node_j === authored.nodes[1]
          && member.sections.length === (authored.integration_order ?? 3), 'member_binding_invalid')
        check(member.element_contract_hash === first.element_contract_hash
          && member.member_feature_contract_hash === first.member_feature_contract_hash
          && member.initial_length_m === first.initial_length_m, 'member_identity_invalid')
        const [c, s] = member.current_direction
        check(Math.abs(c * c + s * s - 1) <= 1e-12, 'direction_invalid')
        for (const offset of [0, 3]) {
          const global = member.end_force_global_kn_knm, local = member.end_force_local_kn_knm
          check(local[offset] === c * global[offset] + s * global[offset + 1]
            && local[offset + 1] === -s * global[offset] + c * global[offset + 1]
            && local[offset + 2] === global[offset + 2], 'local_projection_invalid')
        }
        for (const [point, section] of member.sections.entries()) {
          const initial = first.sections[point]
          check(section.integration_point_index === point && section.section_id === authored.section
            && section.xi === initial.xi && section.weight === initial.weight
            && section.section_contract_hash === initial.section_contract_hash
            && section.fibers.length === initial.fibers.length, 'section_binding_invalid')
          for (const [fiberIndex, fiber] of section.fibers.entries()) check(fiber.fiber_index === fiberIndex
            && fiber.material_kind === initial.fibers[fiberIndex].material_kind, 'fiber_binding_invalid')
        }
      }
    }
    return report
  } catch (error) {
    if (error instanceof Error && /^rc_corotational_report_detail_[a-z_]+$/.test(error.message)) throw error
    throw new Error('rc_corotational_report_detail_invalid')
  }
}

function selectedMember(report: RcCorotationalDetailReport, state: number, memberId: string): RcCorotationalDetailMember {
  check(index(state) && state < report.responses.length, 'state_invalid')
  const found = report.responses[state].members.filter(member => member.member_id === memberId)
  check(found.length === 1, 'member_invalid')
  return found[0]
}
function selectedSection(report: RcCorotationalDetailReport, state: number, memberId: string, point: number): RcCorotationalDetailSection {
  const member = selectedMember(report, state, memberId)
  check(index(point) && point < member.sections.length, 'section_invalid')
  return member.sections[point]
}
export function corotationalDetailMember(report: RcCorotationalDetailReport, state: number, memberId: string): RcCorotationalDetailMemberView {
  const { sections, ...member } = selectedMember(report, state, memberId)
  return { ...member, sections: sections.map(section => ({ integration_point_index: section.integration_point_index,
    xi: section.xi, section_id: section.section_id, fiberCount: section.fibers.length })) }
}
export function corotationalDetailSection(report: RcCorotationalDetailReport, state: number, memberId: string, point: number): RcCorotationalDetailSectionView {
  const { fibers, ...section } = selectedSection(report, state, memberId, point)
  return { ...section, fiberCount: fibers.length }
}
export function corotationalDetailFiber(report: RcCorotationalDetailReport, state: number, memberId: string, point: number, fiberIndex: number): RcCorotationalDetailFiber {
  const section = selectedSection(report, state, memberId, point)
  check(index(fiberIndex) && fiberIndex < section.fibers.length, 'fiber_invalid')
  return section.fibers[fiberIndex]
}
function page(report: RcCorotationalDetailReport, start: number, count: number): RcCorotationalDetailResponse[] {
  check(index(start) && start < report.responses.length && Number.isSafeInteger(count) && count >= 1 && count <= 50, 'page_invalid')
  return report.responses.slice(start, start + count)
}
export function corotationalDetailSectionPage(report: RcCorotationalDetailReport, memberId: string, point: number, start: number, count: number): RcCorotationalSectionHistory[] {
  return page(report, start, count).map(row => ({ state_index: row.state_index, phase: row.phase,
    ...corotationalDetailSection(report, row.state_index, memberId, point) }))
}
export function corotationalDetailFiberPage(report: RcCorotationalDetailReport, memberId: string, point: number, fiber: number, start: number, count: number): RcCorotationalFiberHistory[] {
  return page(report, start, count).map(row => ({ state_index: row.state_index, phase: row.phase,
    ...corotationalDetailFiber(report, row.state_index, memberId, point, fiber) }))
}
