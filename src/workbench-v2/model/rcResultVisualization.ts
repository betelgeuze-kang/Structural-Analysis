import type { RcObject } from './rcJobSchema'

export interface RcResultGeometry {
  nodes: Array<{ id: string; x: number; y: number }>
  members: Array<{ id: string; nodeI: string; nodeJ: string }>
}

const identifier = (value: unknown): value is string => typeof value === 'string'
  && value.length > 0 && value.length <= 512 && !/[\u0000-\u001f\u007f]/.test(value)
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const index = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
function check(condition: unknown, message: string): asserts condition { if (!condition) throw new Error(`rc_review_${message}`) }

/** Called inside the original reviewer only after request/artifact validation.
 * Coordinates are the original model's metre-valued XY coordinates, never an
 * editable draft or a fitted shape. Array and endpoint order stay authored.
 */
export function rcResultGeometry(request: RcObject): RcResultGeometry {
  const model = request?.model
  check(model && Array.isArray(model.nodes) && model.nodes.length >= 2 && model.nodes.length <= 16
    && Array.isArray(model.elements) && model.elements.length > 0 && model.elements.length <= 256, 'geometry_bound_invalid')
  const nodes = model.nodes.map((node: RcObject) => {
    check(node && identifier(node.id) && Array.isArray(node.coordinates) && node.coordinates.length === 3
      && node.coordinates.every(finite) && node.coordinates[2] === 0, 'geometry_node_invalid')
    return { id: node.id, x: node.coordinates[0] as number, y: node.coordinates[1] as number }
  }) as RcResultGeometry['nodes']
  check(new Set(nodes.map(node => node.id)).size === nodes.length, 'geometry_node_invalid')
  const width = Math.max(...nodes.map(node => node.x)) - Math.min(...nodes.map(node => node.x))
  const height = Math.max(...nodes.map(node => node.y)) - Math.min(...nodes.map(node => node.y))
  check(Number.isFinite(width) && Number.isFinite(height) && Math.max(width, height) > 0, 'geometry_extent_invalid')
  const byId = new Map(nodes.map(node => [node.id, node]))
  const members = model.elements.map((member: RcObject) => {
    check(member && identifier(member.id) && Array.isArray(member.nodes) && member.nodes.length === 2
      && member.nodes.every(identifier) && member.nodes[0] !== member.nodes[1], 'geometry_member_invalid')
    const from = byId.get(member.nodes[0]), to = byId.get(member.nodes[1])
    check(from && to, 'geometry_member_invalid')
    const length = Math.hypot(to.x - from.x, to.y - from.y)
    check(Number.isFinite(length) && length > 0, 'geometry_extent_invalid')
    return { id: member.id, nodeI: member.nodes[0] as string, nodeJ: member.nodes[1] as string }
  }) as RcResultGeometry['members']
  check(new Set(members.map(member => member.id)).size === members.length, 'geometry_member_invalid')
  return { nodes, members }
}

function page(history: RcObject[], memberId: string, integrationPoint: number, start: number, count: number): RcObject[] {
  check(Array.isArray(history) && index(start) && start < history.length
    && Number.isSafeInteger(count) && count >= 1 && count <= 50, 'history_page_invalid')
  check(identifier(memberId) && index(integrationPoint), 'history_selection_invalid')
  return history.slice(start, start + count)
}
function point(row: RcObject, collection: 'section_results' | 'fiber_results', memberId: string, integrationPoint: number, fiberIndex?: number): RcObject {
  check(row && Number.isSafeInteger(row.epoch) && row.epoch >= 1 && Array.isArray(row[collection]) && row[collection].length <= 100000, 'history_row_invalid')
  const matches = row[collection].filter((candidate: RcObject) => candidate && candidate.member_id === memberId
    && candidate.integration_point_index === integrationPoint && (fiberIndex === undefined || candidate.fiber_index === fiberIndex))
  check(matches.length === 1, 'history_selection_missing_or_ambiguous')
  return matches[0]
}

/** Bounded projections retain accepted-state order, including preload/reversals.
 * A missing or ambiguous physical selector is an error, never a neighboring
 * member, point or fiber substituted to complete the plot.
 */
export function rcMaterialHistoryPage(history: RcObject[], memberId: string, integrationPoint: number, fiberIndex: number, start: number, count: number): RcObject[] {
  check(index(fiberIndex), 'history_selection_invalid')
  return page(history, memberId, integrationPoint, start, count).map(row => {
    const selected = point(row, 'fiber_results', memberId, integrationPoint, fiberIndex)
    check(finite(selected.strain) && finite(selected.stress_MPa) && selected.material_state
      && typeof selected.material_state === 'object' && !Array.isArray(selected.material_state), 'history_value_invalid')
    return { epoch: row.epoch, strain: selected.strain, stress_MPa: selected.stress_MPa, material_state: selected.material_state }
  })
}

export function rcSectionHistoryPage(history: RcObject[], memberId: string, integrationPoint: number, start: number, count: number): RcObject[] {
  return page(history, memberId, integrationPoint, start, count).map(row => {
    const selected = point(row, 'section_results', memberId, integrationPoint)
    check(['axial_strain', 'curvature_z_per_m', 'axial_force_N', 'moment_z_Nm'].every(key => finite(selected[key])), 'history_value_invalid')
    return { epoch: row.epoch, axial_strain: selected.axial_strain, curvature_z_per_m: selected.curvature_z_per_m,
      axial_force_N: selected.axial_force_N, moment_z_Nm: selected.moment_z_Nm }
  })
}
