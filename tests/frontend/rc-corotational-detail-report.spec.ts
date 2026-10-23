import { expect, test } from '@playwright/test'
import {
  corotationalDetailMember, corotationalDetailSection, corotationalDetailFiber,
  corotationalDetailSectionPage, corotationalDetailFiberPage, parseRcCorotationalDetailReport,
  type RcCorotationalDetailReport,
} from '../../src/workbench-v2/model/rcCorotationalDetailReport'
import type { RcCorotationalReport, RcCorotationalReportExpected } from '../../src/workbench-v2/model/rcCorotationalReportSchema'

// Synthetic stored samples exercise projection contracts only. They do not run
// a model or substitute for the actual portal HTTP/browser integration test.
function stored(fiberCount = 34, stateCount = 23): RcCorotationalDetailReport {
  return { responses: Array.from({ length: stateCount }, (_, state) => ({
    state_index: state, phase: state === 0 ? 'preload' : 'control', checkpoint_hash: `checkpoint-${state}`,
    parent_checkpoint_hash: `checkpoint-${state - 1}`, load_factor: state % 2 ? -state : state,
    members: ['column-left', 'beam-top', 'column-right'].map((member, memberIndex) => ({
      member_index: memberIndex, member_id: member, node_i: ['N1', 'N3', 'N4'][memberIndex], node_j: ['N3', 'N4', 'N2'][memberIndex],
      element_contract_hash: `element-${member}`, member_feature_contract_hash: `feature-${member}`,
      member_feature_response_hash: `response-${state}-${member}`, initial_length_m: memberIndex === 1 ? 4 : 3,
      current_length_m: memberIndex === 1 ? 4 : 3, current_direction: memberIndex === 1 ? [1, 0] : [0, memberIndex === 0 ? 1 : -1],
      end_force_global_kn_knm: [state, -state, memberIndex, -state, state, -memberIndex],
      end_force_local_kn_knm: [-state, state, memberIndex, state, -state, -memberIndex],
      sections: [-0.75, 0, 0.75].map((xi, point) => ({
        integration_point_index: point, xi, weight: point === 1 ? 0.9 : 0.55, section_id: 'RC1',
        section_contract_hash: 'section-RC1', state_hash: `section-${state}-${point}`, step_index: state + 1,
        axial_strain: state / 1000, curvature_z_per_m: (state % 2 ? -1 : 1) * state / 100,
        axial_force_kn: memberIndex * 10 + state, moment_z_kn_m: state % 2 ? -state : state,
        fibers: Array.from({ length: fiberCount }, (_, fiber) => ({
          fiber_index: fiber, material_kind: fiber < 32 ? 'concrete' : 'steel',
          strain: (state % 2 ? -1 : 1) * state / 1000 + fiber / 1e6,
          stress_mpa: state * 2 + fiber / 100, state_hash: `fiber-${state}-${fiber}`,
        })),
      })),
    })),
  })) } as RcCorotationalDetailReport
}

test('detail projections retain member endpoint/source order without transferring fiber arrays', () => {
  const report = stored(2080, 3), before = JSON.stringify(report)
  const member = corotationalDetailMember(report, 2, 'column-right')
  expect(member.node_i).toBe('N4'); expect(member.node_j).toBe('N2')
  expect(member.end_force_global_kn_knm).toEqual(report.responses[2].members[2].end_force_global_kn_knm)
  expect(member.end_force_local_kn_knm).toEqual(report.responses[2].members[2].end_force_local_kn_knm)
  expect(member.sections).toEqual([-0.75, 0, 0.75].map((xi, integration_point_index) => ({ integration_point_index, xi, section_id: 'RC1', fiberCount: 2080 })))
  expect(JSON.stringify(member)).not.toContain('"fibers"')
  const section = corotationalDetailSection(report, 2, 'column-right', 1)
  expect(section.fiberCount).toBe(2080)
  expect(section).not.toHaveProperty('fibers')
  expect(corotationalDetailFiber(report, 2, 'column-right', 1, 2079)).toEqual(report.responses[2].members[2].sections[1].fibers[2079])
  expect(JSON.stringify(report)).toBe(before)
})

test('detail history pages preserve preload, reversals and raw values with no sorting or zero shift', () => {
  const report = stored()
  const section = corotationalDetailSectionPage(report, 'beam-top', 2, 0, 20)
  expect(section).toHaveLength(20)
  expect(section.map(row => row.state_index)).toEqual(Array.from({ length: 20 }, (_, index) => index))
  expect(section[0].phase).toBe('preload')
  expect(section.map(row => row.curvature_z_per_m)).toEqual(report.responses.slice(0, 20).map(row => row.members[1].sections[2].curvature_z_per_m))
  expect(section.every(row => !('fibers' in row))).toBe(true)
  const tail = corotationalDetailFiberPage(report, 'column-right', 0, 32, 20, 20)
  expect(tail.map(row => [row.state_index, row.strain, row.stress_mpa])).toEqual(report.responses.slice(20).map(row => {
    const fiber = row.members[2].sections[0].fibers[32]
    return [row.state_index, fiber.strain, fiber.stress_mpa]
  }))
  expect(tail).toHaveLength(3)
})

test('detail selection and page bounds reject missing, ambiguous and fractional indices', () => {
  const report = stored()
  for (const state of [-1, 0.5, 23, NaN, Infinity]) expect(() => corotationalDetailMember(report, state, 'column-left')).toThrow('detail_state_invalid')
  expect(() => corotationalDetailMember(report, 0, 'missing')).toThrow('detail_member_invalid')
  for (const point of [-1, 0.5, 3]) expect(() => corotationalDetailSection(report, 0, 'column-left', point)).toThrow('detail_section_invalid')
  for (const fiber of [-1, 0.5, 2080]) expect(() => corotationalDetailFiber(report, 0, 'column-left', 0, fiber)).toThrow('detail_fiber_invalid')
  for (const [start, count] of [[-1, 1], [23, 1], [0, 0], [0, 51], [0, 1.5], [0.5, 1]]) {
    expect(() => corotationalDetailSectionPage(report, 'column-left', 0, start, count)).toThrow('detail_page_invalid')
    expect(() => corotationalDetailFiberPage(report, 'column-left', 0, 0, start, count)).toThrow('detail_page_invalid')
  }
  report.responses[0].members.push(report.responses[0].members[0])
  expect(() => corotationalDetailMember(report, 0, 'column-left')).toThrow('detail_member_invalid')
})

test('malformed detail documents fail locally before any saved nodal binding is consumed', async () => {
  for (const raw of ['', '{}', '{"schema_version":"durable-rc-corotational-detail-report.v999"}', '{"responses": [NaN]}', '\ufeff{}']) {
    await expect(parseRcCorotationalDetailReport(new TextEncoder().encode(raw), {} as RcCorotationalReportExpected, {} as RcCorotationalReport)).rejects.toThrow(/^rc_corotational_report_detail_/)
  }
})
