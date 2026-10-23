import { expect, test } from '@playwright/test'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import { rcMaterialHistoryPage, rcResultGeometry, rcSectionHistoryPage } from '../../src/workbench-v2/model/rcResultVisualization'
import type { RcObject } from '../../src/workbench-v2/model/rcJobSchema'

function request(): RcObject { return createRcEditorExample('a'.repeat(40)) }
function history(): RcObject[] {
  // Projection-only fixture: the first row represents a preload state and
  // subsequent signed/repeated values deliberately reverse. No solver claim.
  return [0, 0.002, -0.001, 0.002].map((value, i) => ({ epoch: i + 1, untouched: { large: 'not projected' },
    section_results: [
      { member_id: 'OTHER', integration_point_index: 1, axial_strain: 99, curvature_z_per_m: 99, axial_force_N: 99, moment_z_Nm: 99 },
      { member_id: 'M1', integration_point_index: 1, axial_strain: value / 2, curvature_z_per_m: value, axial_force_N: value * 100, moment_z_Nm: value * 200 },
    ],
    fiber_results: [
      { member_id: 'M1', integration_point_index: 0, fiber_index: 2, strain: 99, stress_MPa: 99, material_state: { state_hash: 'wrong point' } },
      { member_id: 'M1', integration_point_index: 1, fiber_index: 2, strain: value, stress_MPa: value * 1000, material_state: { state_hash: `state-${i}`, plastic_strain: i / 1000 } },
      { member_id: 'M1', integration_point_index: 1, fiber_index: 3, strain: 99, stress_MPa: 99, material_state: { state_hash: 'wrong fiber' } },
    ],
  }))
}

test('geometry projects original node order, identifiers and member endpoint direction without editable metadata', () => {
  const original = request()
  original.model.nodes = [{ id: 'N:z', coordinates: [4, 2, 0] }, { id: 'N:a', coordinates: [-2, -3, 0] }]
  original.model.elements[0].nodes = ['N:a', 'N:z']
  original.model.elements[0].id = 'Member:exact'
  const snapshot = JSON.stringify(original), geometry = rcResultGeometry(original)
  expect(geometry).toEqual({ nodes: [{ id: 'N:z', x: 4, y: 2 }, { id: 'N:a', x: -2, y: -3 }],
    members: [{ id: 'Member:exact', nodeI: 'N:a', nodeJ: 'N:z' }] })
  expect(JSON.stringify(original)).toBe(snapshot)
  original.model.nodes[0].coordinates[0] = 999
  expect(geometry.nodes[0].x).toBe(4)
  expect(JSON.stringify(geometry)).not.toContain('materials')
})

for (const [name, mutate, error] of [
  ['duplicate nodes', (r: RcObject) => { r.model.nodes[1].id = r.model.nodes[0].id }, 'geometry_node_invalid'],
  ['missing member endpoint', (r: RcObject) => { r.model.elements[0].nodes[1] = 'n2' }, 'geometry_member_invalid'],
  ['repeated member endpoint', (r: RcObject) => { r.model.elements[0].nodes[1] = 'N1' }, 'geometry_member_invalid'],
  ['duplicate member IDs', (r: RcObject) => { r.model.elements.push(structuredClone(r.model.elements[0])) }, 'geometry_member_invalid'],
  ['nonplanar coordinates', (r: RcObject) => { r.model.nodes[0].coordinates[2] = 1 }, 'geometry_node_invalid'],
  ['nonfinite coordinates', (r: RcObject) => { r.model.nodes[0].coordinates[0] = Infinity }, 'geometry_node_invalid'],
  ['overflowing extent', (r: RcObject) => { r.model.nodes[0].coordinates[0] = -1e308; r.model.nodes[1].coordinates[0] = 1e308 }, 'geometry_extent_invalid'],
  ['overflowing diagonal', (r: RcObject) => { r.model.nodes[1].coordinates = [1.7e308, 1.7e308, 0] }, 'geometry_extent_invalid'],
  ['zero length member', (r: RcObject) => { r.model.nodes[1].coordinates = [...r.model.nodes[0].coordinates] }, 'geometry_extent_invalid'],
  ['too many nodes', (r: RcObject) => { r.model.nodes = Array.from({ length: 17 }, (_, i) => ({ id: `N${i}`, coordinates: [i, 0, 0] })) }, 'geometry_bound_invalid'],
  ['too many members', (r: RcObject) => { r.model.elements = Array.from({ length: 257 }, (_, i) => ({ ...r.model.elements[0], id: `M${i}` })) }, 'geometry_bound_invalid'],
] as const) {
  test(`geometry rejects ${name} instead of producing misleading drawing coordinates`, () => {
    const value = request(); mutate(value)
    expect(() => rcResultGeometry(value)).toThrow(error)
  })
}

test('geometry accepts the full bounded node count without sorting its input', () => {
  const value = request()
  value.model.nodes = Array.from({ length: 16 }, (_, i) => ({ id: `N${15 - i}`, coordinates: [15 - i, 0, 0] }))
  value.model.elements = Array.from({ length: 15 }, (_, i) => ({ id: `M${i}`, nodes: [`N${15 - i}`, `N${14 - i}`] }))
  const geometry = rcResultGeometry(value)
  expect(geometry.nodes).toHaveLength(16)
  expect(geometry.nodes.map(node => node.x)).toEqual(Array.from({ length: 16 }, (_, i) => 15 - i))
  expect(geometry.members[0]).toEqual({ id: 'M0', nodeI: 'N15', nodeJ: 'N14' })
})

test('material pages preserve preload, reversals, repeated coordinates and exact fiber selection in stored order', () => {
  const rows = history(), snapshot = JSON.stringify(rows)
  const projected = rcMaterialHistoryPage(rows, 'M1', 1, 2, 0, 50)
  expect(projected.map(row => [row.epoch, row.strain, row.stress_MPa])).toEqual([
    [1, 0, 0], [2, 0.002, 2], [3, -0.001, -1], [4, 0.002, 2],
  ])
  expect(projected[2].material_state).toEqual({ state_hash: 'state-2', plastic_strain: 0.002 })
  expect(rcMaterialHistoryPage(rows, 'M1', 1, 2, 2, 2)).toEqual(projected.slice(2))
  expect(Object.keys(projected[0]).sort()).toEqual(['epoch', 'material_state', 'strain', 'stress_MPa'])
  expect(JSON.stringify(rows)).toBe(snapshot)
})

test('section pages preserve coupled stored forces and strains without normalizing moment or curvature', () => {
  const rows = history(), projected = rcSectionHistoryPage(rows, 'M1', 1, 1, 3)
  expect(projected).toEqual([
    { epoch: 2, axial_strain: 0.001, curvature_z_per_m: 0.002, axial_force_N: 0.2, moment_z_Nm: 0.4 },
    { epoch: 3, axial_strain: -0.0005, curvature_z_per_m: -0.001, axial_force_N: -0.1, moment_z_Nm: -0.2 },
    { epoch: 4, axial_strain: 0.001, curvature_z_per_m: 0.002, axial_force_N: 0.2, moment_z_Nm: 0.4 },
  ])
  expect(rcSectionHistoryPage(rows, 'M1', 1, 3, 50)).toEqual([projected[2]])
})

test('paging bounds reject empty, fractional, negative, nonfinite and oversized requests', () => {
  for (const [start, count] of [[-1, 1], [0.5, 1], [4, 1], [Infinity, 1], [0, 0], [0, -1], [0, 1.5], [0, 51], [0, NaN]]) {
    expect(() => rcSectionHistoryPage(history(), 'M1', 1, start, count)).toThrow('history_page_invalid')
    expect(() => rcMaterialHistoryPage(history(), 'M1', 1, 2, start, count)).toThrow('history_page_invalid')
  }
  expect(() => rcSectionHistoryPage([], 'M1', 1, 0, 1)).toThrow('history_page_invalid')
})

test('selection uses exact member, integration point and fiber indices without string coercion or fallback', () => {
  for (const member of ['m1', 'M1 ', 'OTHER']) {
    expect(() => rcMaterialHistoryPage(history(), member, 1, 2, 0, 1)).toThrow('history_selection_missing_or_ambiguous')
  }
  expect(() => rcSectionHistoryPage(history(), 'm1', 1, 0, 1)).toThrow('history_selection_missing_or_ambiguous')
  expect(() => rcSectionHistoryPage(history(), 'M1', 0, 0, 1)).toThrow('history_selection_missing_or_ambiguous')
  for (const invalid of [-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '1' as unknown as number]) {
    expect(() => rcSectionHistoryPage(history(), 'M1', invalid, 0, 1)).toThrow('history_selection_invalid')
    expect(() => rcMaterialHistoryPage(history(), 'M1', 1, invalid, 0, 1)).toThrow('history_selection_invalid')
  }
})

test('missing or ambiguous physical rows remain unavailable rather than selecting a neighboring result', () => {
  const section = history(); section[1].section_results.push({ ...section[1].section_results[1], moment_z_Nm: 999 })
  expect(() => rcSectionHistoryPage(section, 'M1', 1, 0, 4)).toThrow('history_selection_missing_or_ambiguous')
  const material = history(); material[1].fiber_results.push({ ...material[1].fiber_results[1], stress_MPa: 999 })
  expect(() => rcMaterialHistoryPage(material, 'M1', 1, 2, 0, 4)).toThrow('history_selection_missing_or_ambiguous')
  const missing = history(); missing[2].fiber_results.splice(1, 1)
  expect(() => rcMaterialHistoryPage(missing, 'M1', 1, 2, 0, 4)).toThrow('history_selection_missing_or_ambiguous')
})

test('pages reject nonfinite scalars and malformed epochs while leaving valid neighboring pages available', () => {
  const rows = history(); rows[2].section_results[1].moment_z_Nm = Infinity
  expect(() => rcSectionHistoryPage(rows, 'M1', 1, 2, 1)).toThrow('history_value_invalid')
  expect(rcSectionHistoryPage(rows, 'M1', 1, 0, 2)).toHaveLength(2)
  rows[2].fiber_results[1].strain = NaN
  expect(() => rcMaterialHistoryPage(rows, 'M1', 1, 2, 2, 1)).toThrow('history_value_invalid')
  rows[0].epoch = 0
  expect(() => rcMaterialHistoryPage(rows, 'M1', 1, 2, 0, 1)).toThrow('history_row_invalid')
})
