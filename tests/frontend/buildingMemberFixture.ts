import { readFile } from 'node:fs/promises'
import { canonicalNativeJson, nativeFrameModelIdentity } from '../../src/workbench-v2/model/nativeFrameProvider'
import type { BuildingMemberMapping } from '../../src/workbench-v2/model/buildingMemberReview'
import { fixtureHash, nativeFrameResultFixture } from './nativeFrameFixture'

export const buildingFixtureBytes = (value: unknown): Uint8Array => new TextEncoder().encode(canonicalNativeJson(value))

/** Synthetic contract data only: no solver, design, calibration, or physical validation. */
export async function buildingMemberFixture(options: { remesh?: boolean; combination?: boolean } = {}) {
  const model = JSON.parse(await readFile('native/distribution/frame-alpha-cantilever.model-ir.json', 'utf8'))
  const result = nativeFrameResultFixture()
  const firstId = options.remesh ? 'REMESH_A' : 'E1'
  const secondId = options.remesh ? 'REMESH_B' : 'E2'
  model.model_id = options.remesh ? 'synthetic-building-remesh' : 'synthetic-building'
  model.nodes.push({ ...structuredClone(model.nodes[1]), id: 'N3', index: 2, coordinates_m: [4, 0, 0], source_id: 'synthetic:N3' })
  model.elements[0].id = firstId
  model.elements[0].index = 7
  const second = { ...structuredClone(model.elements[0]), id: secondId, index: 2, node_ids: ['N3', 'N2'], source_id: 'synthetic:reversed' }
  model.elements.unshift(second)
  if (options.remesh) {
    model.nodes.push({ ...structuredClone(model.nodes[1]), id: 'N4', index: 3, coordinates_m: [1, 0, 0], source_id: 'synthetic:N4' })
    model.elements[0].node_ids = ['N2', 'N4']
    model.elements[1].node_ids = ['N1', 'N4']
    model.elements.unshift({ ...structuredClone(second), id: 'REMESH_C', index: 11, node_ids: ['N2', 'N3'], source_id: 'synthetic:REMESH_C' })
  }
  model.load_patterns[0].id = 'LC1'
  model.load_patterns[0].uniform_member_loads[0].member_id = firstId
  if (options.combination) {
    model.load_combinations = [{
      id: 'COMB1', index: 0, combination_type: 'linear',
      terms: [{ ref_kind: 'load_pattern', ref_id: 'LC1', factor: -1.25 }],
      source_id: 'synthetic:COMB1', extensions: {},
    }]
  }
  const binding = result.bindings as Record<string, unknown>
  binding.model_id = model.model_id
  Object.assign(binding, await nativeFrameModelIdentity(model))
  if (options.combination) { binding.load_pattern_id = null; binding.load_combination_id = 'COMB1' }
  const resultNodes = result.nodes as Array<Record<string, unknown>>
  resultNodes.push({ node_id: 'N3', displacement_m_rad: [0, 0, 0, 0, 0, 0], reaction_n_nm: [0, 0, 0, 0, 0, 0] })
  if (options.remesh) resultNodes.push({ node_id: 'N4', displacement_m_rad: [0, 0, 0, 0, 0, 0], reaction_n_nm: [0, 0, 0, 0, 0, 0] })
  result.members = [
    { member_id: firstId, end_i_force_n_nm: [-11, 12, -13, 14, -15, 16], end_j_force_n_nm: [21, -22, 23, -24, 25, -26] },
    { member_id: secondId, end_i_force_n_nm: [-31, 32, -33, 34, -35, 36], end_j_force_n_nm: [41, -42, 43, -44, 45, -46] },
  ]
  if (options.remesh) (result.members as unknown[]).push({ member_id: 'REMESH_C', end_i_force_n_nm: [-51, 52, -53, 54, -55, 56], end_j_force_n_nm: [61, -62, 63, -64, 65, -66] })
  result.result_id = options.remesh ? 'synthetic.remesh' : 'synthetic.result'
  const resultBody = { ...result }
  delete resultBody.result_hash
  result.result_hash = fixtureHash(resultBody)
  const mapping: BuildingMemberMapping = {
    schema_version: 'structural-building-member-mapping.v1', mapping_id: 'synthetic.mapping',
    bindings: {
      model_id: String(binding.model_id),
      model_content_hash: String(binding.model_content_hash),
      model_semantic_hash: String(binding.model_semantic_hash),
      model_provenance_hash: String(binding.model_provenance_hash),
      result_id: String(result.result_id), result_hash: String(result.result_hash),
    },
    storeys: [{ storey_id: 'STOREY_1', label: 'Declared first storey', elevation_m: 3 }],
    members: [{
      member_id: 'PHYSICAL_B7', label: 'Beam B7', storey_id: 'STOREY_1',
      segments: [
        { segment_id: 'SEGMENT_B', element_id: secondId, member_start: 0.5, member_end: 1, orientation: 'j_to_i' },
        { segment_id: 'SEGMENT_A', element_id: firstId, member_start: 0, member_end: 0.5, orientation: 'i_to_j' },
      ],
      review_locations: [
        { location_id: 'B7_LEFT', element_id: firstId, end: 'i' },
        { location_id: 'B7_JUNCTION_LEFT', element_id: firstId, end: 'j' },
        { location_id: 'B7_JUNCTION_RIGHT', element_id: secondId, end: 'j' },
        { location_id: 'B7_RIGHT', element_id: secondId, end: 'i' },
      ],
    }],
  }
  if (options.remesh) {
    mapping.members[0].segments[0].member_start = 0.25
    mapping.members[0].segments[0].member_end = 0.5
    mapping.members[0].segments[1].member_end = 0.25
    mapping.members[0].segments.push({ segment_id: 'SEGMENT_C', element_id: 'REMESH_C', member_start: 0.5, member_end: 1, orientation: 'i_to_j' })
  }
  return { model, result, mapping, modelBytes: buildingFixtureBytes(model), resultBytes: buildingFixtureBytes(result) }
}
